"""M2E manual skill activation: apply or revert one owner-chosen scope, resolve it at read time.

The owner applies the exact bytes of an authorized skill candidate to one context: the
assistant's own chat (`dm:<agent_key>`). Nothing is written to the canonical file. The
pointer lives in `improvement_activations`; the bytes are the candidate's encrypted,
content-addressed blob, so a committed pointer can never see half-written content.

Read time (`effective_skill_asset`) serves the overlay only when all of these still hold:
the turn belongs to that assistant, the read comes from an in-process engine (CLI engines
also read `.claude/skills` natively, which this cannot cover), the target is live, the
owner's exact-diff authority is still active, and the canonical file still has the exact
bytes the candidate was built on. Any drift serves the canonical skill; `reconcile` then
records the suspension. A disabled or deleted skill is never revived by an overlay.

Evidence level: `qualified` only when a final comparison passed the pinned numeric gate;
otherwise `manual_trial`, which the UI labels as an unproven manual try. A candidate any
comparison rejected cannot be applied.
"""
from __future__ import annotations

import contextvars
import hashlib
import json
import re
import secrets
import sqlite3
import sys
import time
from contextlib import closing, contextmanager
from pathlib import Path
from typing import Callable

import improvement_store as IM
from improvement_blobs import AssetUnavailable

SELECTOR_CONTEXT = "dm"
_AGENT_KEY = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}")
_IDENTIFIER = re.compile(r"iac_[0-9a-f]{32}")
_CANONICAL = re.compile(r"skills/([a-z0-9][a-z0-9_-]{0,127})/SKILL\.md")
SUSPEND_REASONS = ("canonical_changed", "source_unavailable", "authority_revoked", "target_retired",
                   "candidate_rejected")


def selector(agent_key: str, agent_slug: str = "") -> dict:
    if type(agent_key) is not str or not _AGENT_KEY.fullmatch(agent_key):
        raise ValueError("invalid_activation_agent")
    return {"context": SELECTOR_CONTEXT, "agent_key": agent_key, "agent_slug": str(agent_slug or "")[:128]}


def scope_hash(agent_key: str) -> str:
    """The scope is the assistant identity alone; the display slug never changes it."""
    return IM._hash({"context": SELECTOR_CONTEXT, "agent_key": selector(agent_key)["agent_key"]})


def apply_evidence(reports: list) -> tuple[str, dict]:
    """Pure evidence policy for one candidate arm. Rows are host-read report summaries."""
    level, refs = "manual_trial", []
    for row in reports:
        summary = row["summary"]
        refs.append({"report_id": row["report_id"], "kind": row["kind"],
                     "mechanical_verdict": summary.get("mechanical_verdict"), "complete": bool(summary.get("complete"))})
        if summary.get("mechanical_verdict") == "rejected":
            raise PermissionError("candidate_rejected_by_evidence")
        if (row["kind"] == "final" and summary.get("mechanical_verdict") == "eligible"
                and (summary.get("pilot") or {}).get("numeric_gate") is True):
            level = "qualified"
    # Business acceptance is a separate owner decision; a numeric gate never claims it.
    return level, {"reports": refs, "business_eligibility": "unverified"}


def _canary(connection, activation_id):
    if not connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='improvement_canaries'").fetchone():
        return None
    row = connection.execute("SELECT allocation_pct,started_at,state,reason,generation FROM improvement_canaries "
                             "WHERE activation_id=?", (activation_id,)).fetchone()
    return dict(row) if row is not None else None


def _end_canary(connection, brain, activation_id, reason, now):
    if connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='improvement_canaries'").fetchone():
        connection.execute("UPDATE improvement_canaries SET state='ended',reason=?,generation=generation+1,updated_at=? "
                           "WHERE activation_id=? AND brain_id=? AND state='canary'", (reason, now, activation_id, brain))


def _public(row) -> dict:
    result = {key: row[key] for key in ("target_id", "candidate_id", "experiment_id", "canonical_ref", "base_hash",
              "content_hash", "scope_hash", "evidence_level", "state", "reason", "generation", "created_at", "updated_at")}
    result["activation_id"] = row["id"]
    result["selector"] = json.loads(row["selector_json"])
    result["evidence"] = json.loads(row["evidence_json"])
    return result


def _slug(canonical_ref: str) -> str:
    match = _CANONICAL.fullmatch(canonical_ref or "")
    if not match:
        raise PermissionError("activation_target_unsupported")
    return match.group(1)


def _file_identity(root, canonical_ref: str) -> str:
    """Same identity improvement_assets.capture_source pins: a recreated file is a new target."""
    info = (Path(root) / canonical_ref).stat()
    return hashlib.sha256(f":{info.st_dev}:{info.st_ino}".encode("utf-8")).hexdigest()


def _source_gone(root, slug: str) -> bool:
    """Stable absence only: the disabled marker exists or the canonical file is missing.
    A transient read failure (an editor save, a Windows lock) is not proof of anything."""
    root = Path(root)
    return ((root / "skills" / ".disabled" / slug / "SKILL.md").is_file()
            or not (root / "skills" / slug / "SKILL.md").exists())


def _has_table(connection) -> bool:
    return connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='improvement_activations'"
                              ).fetchone() is not None


class Activations:
    """Owner commands over activation pointers; every write is CAS + idempotent by event key."""

    def __init__(self, assets, *, agent_key: Callable[[str, str], str], clock: Callable[[], float] = time.time):
        if type(assets) is not IM.ImprovementStore:
            raise TypeError("concrete_activation_assets_required")
        self.assets, self.store, self.blobs = assets, assets.store, assets.blobs
        self.agent_key, self.clock = agent_key, clock

    # -- reads -----------------------------------------------------------------------------------

    def _available(self) -> bool:
        return IM._schema_version(self.store) >= 11

    def list(self, principal, *, target_id: str | None = None) -> list:
        brain = IM._brain(principal)
        if not self._available():
            return []
        query, args = "SELECT * FROM improvement_activations WHERE brain_id=?", [brain]
        if target_id is not None:
            query, args = query + " AND target_id=?", args + [str(target_id)]
        with closing(self.store._conn()) as connection:
            rows = connection.execute(query + " ORDER BY created_at DESC,id DESC LIMIT 200", args).fetchall()
            return [{**_public(row), "canary": _canary(connection, row["id"])} for row in rows]

    def _reports(self, connection, brain, candidate) -> list:
        arm = connection.execute("SELECT ordinal FROM improvement_experiment_arms WHERE brain_id=? AND candidate_id=?",
                                 (brain, candidate["id"])).fetchone()
        if arm is None:
            return []
        rows = connection.execute(
            "SELECT r.id,r.report_hash,r.blob_hash,c.kind FROM improvement_comparison_reports r "
            "JOIN improvement_comparisons c ON c.id=r.comparison_id AND c.brain_id=r.brain_id "
            "WHERE r.brain_id=? AND c.experiment_id=? AND c.ordinal=? ORDER BY r.created_at,r.id",
            (brain, candidate["experiment_id"], arm["ordinal"])).fetchall()
        reports = []
        for row in rows:
            report = json.loads(self.blobs.read(brain, row["blob_hash"]).decode("utf-8"))
            if IM._hash(report) != row["report_hash"]:
                raise AssetUnavailable("activation_report_changed")
            reports.append({"report_id": row["id"], "kind": row["kind"], "summary": report["summary"]})
        return reports

    @staticmethod
    def _report_refs(connection, brain, candidate) -> list:
        """Cheap SQL-only fingerprint of the arm's published reports, for in-transaction rechecks."""
        return [tuple(row) for row in connection.execute(
            "SELECT r.id,r.report_hash FROM improvement_comparison_reports r "
            "JOIN improvement_comparisons c ON c.id=r.comparison_id AND c.brain_id=r.brain_id "
            "JOIN improvement_experiment_arms a ON a.experiment_id=c.experiment_id AND a.brain_id=c.brain_id "
            "AND a.ordinal=c.ordinal WHERE r.brain_id=? AND a.candidate_id=? ORDER BY r.id", (brain, candidate["id"]))]

    @staticmethod
    def _selection_refuses(connection, brain, candidate) -> bool:
        """The owner already closed the experiment on another choice (keep_base or the other arm)."""
        row = connection.execute("SELECT s.choice,a.candidate_id FROM improvement_experiment_selections s "
            "LEFT JOIN improvement_experiment_arms a ON a.experiment_id=s.experiment_id AND a.brain_id=s.brain_id "
            "AND a.ordinal=s.ordinal WHERE s.experiment_id=? AND s.brain_id=?",
            (candidate["experiment_id"], brain)).fetchone()
        return row is not None and (row["choice"] != "candidate" or row["candidate_id"] != candidate["id"])

    @staticmethod
    def _authority_active(connection, brain, candidate_id) -> bool:
        return connection.execute(
            "SELECT 1 FROM improvement_candidate_authorities a JOIN improvement_candidate_authority_grants g "
            "ON g.authority_id=a.id AND g.brain_id=a.brain_id WHERE a.brain_id=? AND a.candidate_id=? "
            "AND a.kind='exact_diff' AND g.status='active'", (brain, candidate_id)).fetchone() is not None

    # -- commands --------------------------------------------------------------------------------

    def apply(self, principal, candidate_id: str, agent_slug: str, *, event_key: str,
              allocation_pct: int | None = None) -> dict:
        """Apply to one assistant chat. With `allocation_pct` (1..99) it is an M3 canary: only that share
        of the assistant's chat sessions sees the candidate; the rest is the matched control group."""
        import skill_router as SR
        brain = IM._brain(principal)
        if type(candidate_id) is not str or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}", candidate_id):
            raise ValueError("invalid_candidate")
        if type(agent_slug) is not str or not SR.valid_file_slug(agent_slug):
            raise ValueError("invalid_activation_agent")
        if allocation_pct is not None and (type(allocation_pct) is not int or not 1 <= allocation_pct <= 99):
            raise ValueError("invalid_canary_allocation")
        payload = {"candidate_id": candidate_id, "agent_slug": agent_slug}
        if allocation_pct is not None:
            payload["allocation_pct"] = allocation_pct
        IM.ensure(self.store)
        with closing(self.store._conn()) as connection:
            replay = self.assets._replay(connection, brain, event_key, "activation_apply", payload)
            if replay is not None:
                return replay
            if self.assets._policy(connection, brain)["mode"] == "off":
                raise PermissionError("improvement_disabled")
            candidate = connection.execute("SELECT * FROM improvement_skill_candidates WHERE id=? AND brain_id=?",
                                           (candidate_id, brain)).fetchone()
            if candidate is None:
                raise PermissionError("candidate_unavailable")
            if candidate["content_hash"] == candidate["base_hash"]:
                raise ValueError("keep_base_not_applicable")
            if not self._authority_active(connection, brain, candidate_id):
                raise PermissionError("candidate_authority_required")
            target = self.assets._target(connection, brain, candidate["target_id"])
            if target["kind"] != "skill" or target["status"] != "live":
                raise PermissionError("target_unavailable")
            if self._selection_refuses(connection, brain, candidate):
                raise PermissionError("experiment_closed_on_other_choice")
            refs = self._report_refs(connection, brain, candidate)
            level, evidence = apply_evidence(self._reports(connection, brain, candidate))
        # Resolve the assistant only after the cheap checks: the host resolver never mints an
        # identity for a slug without an agent file.
        agent_key = str(self.agent_key(brain, agent_slug) or "")
        chosen = selector(agent_key, agent_slug)
        scope = scope_hash(agent_key)
        slug = _slug(target["canonical_ref"])
        overlay = self.blobs.read(brain, candidate["content_hash"])
        canonical = SR.read_skill_asset(Path(brain), slug)
        if canonical is None or canonical.relative_path != target["canonical_ref"]:
            raise PermissionError("skill_unavailable")
        if (canonical.content_hash != candidate["base_hash"]
                or _file_identity(brain, target["canonical_ref"]) != target["identity"]):
            # The owner edited or replaced the skill since the candidate was built: rebase, never merge.
            raise IM.ConflictError("candidate_base_changed")
        if SR._frontmatter_header(overlay[:16384])[1] != canonical.frontmatter_hash:
            raise PermissionError("activation_surface_body_only")
        with self.store._Tx(self.store) as connection:
            replay = self.assets._replay(connection, brain, event_key, "activation_apply", payload)
            if replay is not None:
                return replay
            if self.assets._policy(connection, brain)["mode"] == "off":
                raise PermissionError("improvement_disabled")
            current = self.assets._target(connection, brain, candidate["target_id"])
            if (current["status"] != "live" or not self._authority_active(connection, brain, candidate_id)
                    or self._report_refs(connection, brain, candidate) != refs
                    or self._selection_refuses(connection, brain, candidate)):
                raise IM.ConflictError("activation_basis_changed")
            # Last observation inside the write transaction: a stale pointer is never committed.
            final = SR.read_skill_asset(Path(brain), slug)
            if final is None or final.content_hash != candidate["base_hash"]:
                raise IM.ConflictError("candidate_base_changed")
            busy = connection.execute("SELECT id FROM improvement_activations WHERE brain_id=? AND target_id=? "
                                      "AND scope_hash=? AND state='active'", (brain, target["id"], scope)).fetchone()
            if busy is not None:
                raise IM.ConflictError("activation_scope_busy")
            now = self.clock()
            identifier = "iac_" + secrets.token_hex(16)
            connection.execute(
                "INSERT INTO improvement_activations VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (identifier, brain, target["id"], candidate_id, candidate["experiment_id"], target["canonical_ref"],
                 candidate["base_hash"], candidate["content_hash"], canonical.frontmatter_hash, IM._json(chosen), scope,
                 level, IM._json(evidence), "active", "owner_apply", 1, principal.by, now, now))
            if allocation_pct is not None:
                connection.execute("INSERT INTO improvement_canaries VALUES(?,?,?,?,?,?,?,?,?)",
                                   (identifier, brain, allocation_pct, secrets.token_hex(16), now, "canary", "started", 1, now))
            row = connection.execute("SELECT * FROM improvement_activations WHERE id=?", (identifier,)).fetchone()
            result = {**_public(row), "canary": _canary(connection, identifier)}
            self.assets._event(connection, principal, event_key, "activation_apply", payload, result)
            return result

    def revert(self, principal, activation_id: str, *, expected_generation: int, event_key: str) -> dict:
        brain = IM._brain(principal)
        if type(activation_id) is not str or not _IDENTIFIER.fullmatch(activation_id):
            raise ValueError("invalid_activation")
        if type(expected_generation) is not int or expected_generation < 1:
            raise ValueError("invalid_activation_generation")
        if not self._available():
            raise PermissionError("activation_unavailable")
        payload = {"activation_id": activation_id, "expected_generation": expected_generation}
        with self.store._Tx(self.store) as connection:
            replay = self.assets._replay(connection, brain, event_key, "activation_revert", payload)
            if replay is not None:
                return replay
            row = connection.execute("SELECT * FROM improvement_activations WHERE id=? AND brain_id=?",
                                     (activation_id, brain)).fetchone()
            if row is None:
                raise PermissionError("activation_unavailable")
            if row["generation"] != expected_generation:
                raise IM.ConflictError("stale_activation")
            if row["state"] != "active":
                raise IM.ConflictError("activation_not_active")
            # Revert only moves the pointer: the canonical file was never touched, so the
            # owner's own later edits survive and nothing is replayed.
            now = time.time()
            connection.execute("UPDATE improvement_activations SET state='reverted',reason='owner_revert',"
                               "generation=generation+1,updated_at=? WHERE id=? AND brain_id=?",
                               (now, activation_id, brain))
            _end_canary(connection, brain, activation_id, "owner_revert", now)
            result = _public(connection.execute("SELECT * FROM improvement_activations WHERE id=?",
                                                (activation_id,)).fetchone())
            self.assets._event(connection, principal, event_key, "activation_revert", payload, result)
            return result

    def _suspend(self, brain, row, reason) -> bool:
        with self.store._Tx(self.store) as connection:
            now = time.time()
            changed = bool(connection.execute(
                "UPDATE improvement_activations SET state='suspended',reason=?,generation=generation+1,updated_at=? "
                "WHERE id=? AND brain_id=? AND state='active' AND generation=?",
                (reason, now, row["id"], brain, row["generation"])).rowcount)
            if changed:
                _end_canary(connection, brain, row["id"], reason, now)
            return changed

    def reconcile(self, principal) -> list:
        """Record suspensions for pointers whose basis changed for good. Read time already refuses
        them; a transient read failure suspends nothing (the next reconcile decides again)."""
        import skill_router as SR
        brain = IM._brain(principal)
        if not self._available():
            return []
        with closing(self.store._conn()) as connection:
            rows = connection.execute("SELECT a.*,t.status AS target_status,t.identity FROM improvement_activations a "
                "JOIN improvement_targets t ON t.id=a.target_id AND t.brain_id=a.brain_id "
                "WHERE a.brain_id=? AND a.state='active'", (brain,)).fetchall()
            pending = []
            for row in rows:
                candidate = {"id": row["candidate_id"], "experiment_id": row["experiment_id"]}
                slug = _slug(row["canonical_ref"])
                if row["target_status"] != "live":
                    pending.append((row, "target_retired"))
                elif not self._authority_active(connection, brain, row["candidate_id"]):
                    pending.append((row, "authority_revoked"))
                elif _source_gone(brain, slug):
                    pending.append((row, "source_unavailable"))
                else:
                    try:
                        apply_evidence(self._reports(connection, brain, candidate))
                    except PermissionError:
                        pending.append((row, "candidate_rejected"))
                        continue
                    canonical = SR.read_skill_asset(Path(brain), slug)
                    if canonical is None:
                        continue  # transient: neither proof of change nor of absence
                    try:
                        replaced = _file_identity(brain, row["canonical_ref"]) != row["identity"]
                    except OSError:
                        continue
                    if canonical.content_hash != row["base_hash"] or replaced:
                        pending.append((row, "canonical_changed"))
        return [{"activation_id": row["id"], "reason": reason}
                for row, reason in pending if self._suspend(brain, row, reason)]

    def suspend_source(self, principal, slug: str, reason: str = "source_unavailable") -> list:
        """Called by the skill toggle/delete routes: disabling a skill invalidates its overlays at once,
        so turning it back on later never revives them."""
        brain = IM._brain(principal)
        if reason not in SUSPEND_REASONS or not self._available():
            return []
        with closing(self.store._conn()) as connection:
            rows = connection.execute("SELECT * FROM improvement_activations WHERE brain_id=? AND canonical_ref=? "
                                      "AND state='active'", (brain, f"skills/{slug}/SKILL.md")).fetchall()
        return [{"activation_id": row["id"], "reason": reason} for row in rows if self._suspend(brain, row, reason)]


# -- read time -----------------------------------------------------------------------------------

_SOURCES: list = [None]
_CLI_TRANSPORT: contextvars.ContextVar[bool] = contextvars.ContextVar("improvement_activation_cli", default=False)


def configure(database, blobs) -> None:
    """Point read-time resolution at the runtime database and blob store. Unconfigured means canonical only."""
    _SOURCES[0] = None if database is None else (Path(database), blobs)


@contextmanager
def cli_transport():
    """Mark hub requests from CLI engines: they also load skills natively, so no overlay is served."""
    token = _CLI_TRANSPORT.set(True)
    try:
        yield
    finally:
        _CLI_TRANSPORT.reset(token)


def _turn() -> tuple[str, str, int]:
    """(agent key, session id, message id) of a dashboard chat turn; nested Team or Kanban work
    never inherits the chat's assistant."""
    import turn_context
    turn = turn_context.current() or {}
    if turn.get("kenh") != "dashboard" or turn.get("team_gate") or turn.get("job"):
        return "", "", 0
    agent = turn.get("agent") or {}
    return str(agent.get("key") or ""), str(turn.get("session_id") or ""), int(turn.get("message_id") or 0)


_EXPOSURE_SQL = "INSERT OR IGNORE INTO improvement_canary_exposures VALUES(?,?,?,?,?,?,?)"


def _record_exposure(database, brain, activation_id, session_id, message_id, chosen, content_hash, connection=None) -> bool:
    """One row per chat message for both arms; a duplicate read of the same message never counts twice.

    A caller that already holds a write transaction on this database passes its connection: a second
    writer would only wait on that same lock and lose the row. Returns whether the row is durable or
    will be with the caller's commit; the resolver serves the candidate only when it is."""
    row = (activation_id, brain, session_id, message_id, chosen, content_hash, time.time())
    if connection is not None:
        databases = connection.execute("PRAGMA database_list").fetchall()
        if not databases or not databases[0][2] or Path(databases[0][2]).resolve() != Path(database).resolve():
            return False
        connection.execute(_EXPOSURE_SQL, row)
        return True
    own = sqlite3.connect(database, timeout=1)
    with closing(own):
        own.execute("PRAGMA foreign_keys=ON")
        own.execute(_EXPOSURE_SQL, row)
        own.commit()
    return True


def _overlay(root, slug, canonical, connection=None):
    sources = _SOURCES[0]
    if sources is None or _CLI_TRANSPORT.get():
        return None
    agent_key, session_id, message_id = _turn()
    if not agent_key or not _AGENT_KEY.fullmatch(agent_key):
        return None
    database, blobs = sources
    if not database.is_file():
        return None
    brain = str(Path(root).resolve(strict=True))
    canonical_ref = f"skills/{slug}/SKILL.md"
    if canonical.relative_path != canonical_ref:
        return None
    writer = connection
    connection = sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True, timeout=5)
    connection.row_factory = sqlite3.Row
    with closing(connection):
        if not _has_table(connection):
            return None
        row = connection.execute(
            "SELECT a.*,t.identity FROM improvement_activations a JOIN improvement_targets t "
            "ON t.id=a.target_id AND t.brain_id=a.brain_id WHERE a.brain_id=? AND a.canonical_ref=? "
            "AND a.scope_hash=? AND a.state='active' AND t.status='live' AND EXISTS("
            "SELECT 1 FROM improvement_candidate_authorities c JOIN improvement_candidate_authority_grants g "
            "ON g.authority_id=c.id AND g.brain_id=c.brain_id WHERE c.brain_id=a.brain_id "
            "AND c.candidate_id=a.candidate_id AND c.kind='exact_diff' AND g.status='active')",
            (brain, canonical_ref, scope_hash(agent_key))).fetchone()
        if row is not None:
            import improvement_bundle
            if not improvement_bundle.allows(connection, root, brain, agent_key, "skill", row["id"]):
                return None  # M6: a bundle member serves only with its whole bundle
        canary = _canary(connection, row["id"]) if row is not None else None
    if (row is None or row["base_hash"] != canonical.content_hash or row["frontmatter_hash"] != canonical.frontmatter_hash
            or _file_identity(root, canonical_ref) != row["identity"]):
        return None
    if canary is not None and canary["state"] != "promoted":
        if canary["state"] != "canary":
            return None
        from improvement_canary import arm
        if not session_id or message_id <= 0:
            return None  # no message to judge: fail closed to the control arm, record nothing
        salt = _canary_salt(database, row["id"])
        chosen = arm(canary["allocation_pct"], salt, session_id)
        try:
            recorded = _record_exposure(database, brain, row["id"], session_id, message_id, chosen,
                                        row["content_hash"] if chosen == "canary" else canonical.content_hash,
                                        connection=writer)
        except sqlite3.Error as error:
            print(f"[improvement canary] exposure not recorded: {error}", file=sys.stderr)
            recorded = False
        # The candidate reaches a canary message only together with its exposure row.
        if chosen != "canary" or not recorded:
            return None
    raw = blobs.read(brain, row["content_hash"])
    import skill_router as SR
    return SR.SkillAsset(canonical.slug, canonical.relative_path, raw, row["content_hash"], canonical.frontmatter_hash)


def _canary_salt(database, activation_id) -> str:
    connection = sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True, timeout=5)
    with closing(connection):
        return connection.execute("SELECT salt FROM improvement_canaries WHERE activation_id=?",
                                  (activation_id,)).fetchone()[0]


def effective_skill_asset(root, slug, *, connection=None):
    """The skill bytes this turn should see: the scope's active overlay, else the canonical read.
    `connection`: the caller's open write transaction on the runtime database, if any."""
    import skill_router as SR
    canonical = SR.read_skill_asset(root, slug)
    if canonical is None:
        return None
    try:
        return _overlay(root, slug, canonical, connection) or canonical
    except (OSError, ValueError, sqlite3.Error, AssetUnavailable, RuntimeError) as error:
        # An unreadable pointer falls back to the canonical skill: never worse than baseline.
        print(f"[improvement activation] {type(error).__name__}: {error}", file=sys.stderr)
        return canonical
