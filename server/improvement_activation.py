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
SUSPEND_REASONS = ("canonical_changed", "source_unavailable", "authority_revoked", "target_retired")


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


def _has_table(connection) -> bool:
    return connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='improvement_activations'"
                              ).fetchone() is not None


class Activations:
    """Owner commands over activation pointers; every write is CAS + idempotent by event key."""

    def __init__(self, assets, *, agent_key: Callable[[str, str], str]):
        if type(assets) is not IM.ImprovementStore:
            raise TypeError("concrete_activation_assets_required")
        self.assets, self.store, self.blobs = assets, assets.store, assets.blobs
        self.agent_key = agent_key

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
        return [_public(row) for row in rows]

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
    def _authority_active(connection, brain, candidate_id) -> bool:
        return connection.execute(
            "SELECT 1 FROM improvement_candidate_authorities a JOIN improvement_candidate_authority_grants g "
            "ON g.authority_id=a.id AND g.brain_id=a.brain_id WHERE a.brain_id=? AND a.candidate_id=? "
            "AND a.kind='exact_diff' AND g.status='active'", (brain, candidate_id)).fetchone() is not None

    # -- commands --------------------------------------------------------------------------------

    def apply(self, principal, candidate_id: str, agent_slug: str, *, event_key: str) -> dict:
        import skill_router as SR
        brain = IM._brain(principal)
        if type(candidate_id) is not str or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}", candidate_id):
            raise ValueError("invalid_candidate")
        if type(agent_slug) is not str or not 0 < len(agent_slug) <= 128:
            raise ValueError("invalid_activation_agent")
        payload = {"candidate_id": candidate_id, "agent_slug": agent_slug}
        IM.ensure(self.store)
        with closing(self.store._conn()) as connection:
            replay = self.assets._replay(connection, brain, event_key, "activation_apply", payload)
            if replay is not None:
                return replay
        agent_key = str(self.agent_key(brain, agent_slug) or "")
        chosen = selector(agent_key, agent_slug)
        scope = scope_hash(agent_key)
        with closing(self.store._conn()) as connection:
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
            level, evidence = apply_evidence(self._reports(connection, brain, candidate))
        slug = _slug(target["canonical_ref"])
        canonical = SR.read_skill_asset(Path(brain), slug)
        if canonical is None or canonical.relative_path != target["canonical_ref"]:
            raise PermissionError("skill_unavailable")
        if canonical.content_hash != candidate["base_hash"]:
            # The owner edited the skill since the candidate was built: rebase, never merge.
            raise IM.ConflictError("candidate_base_changed")
        overlay = self.blobs.read(brain, candidate["content_hash"])
        if SR._frontmatter_header(overlay[:16384])[1] != canonical.frontmatter_hash:
            raise PermissionError("activation_surface_body_only")
        with self.store._Tx(self.store) as connection:
            replay = self.assets._replay(connection, brain, event_key, "activation_apply", payload)
            if replay is not None:
                return replay
            if self.assets._policy(connection, brain)["mode"] == "off":
                raise PermissionError("improvement_disabled")
            current = self.assets._target(connection, brain, candidate["target_id"])
            if current["status"] != "live" or not self._authority_active(connection, brain, candidate_id):
                raise IM.ConflictError("activation_basis_changed")
            busy = connection.execute("SELECT id FROM improvement_activations WHERE brain_id=? AND target_id=? "
                                      "AND scope_hash=? AND state='active'", (brain, target["id"], scope)).fetchone()
            if busy is not None:
                raise IM.ConflictError("activation_scope_busy")
            now = time.time()
            identifier = "iac_" + secrets.token_hex(16)
            connection.execute(
                "INSERT INTO improvement_activations VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (identifier, brain, target["id"], candidate_id, candidate["experiment_id"], target["canonical_ref"],
                 candidate["base_hash"], candidate["content_hash"], canonical.frontmatter_hash, IM._json(chosen), scope,
                 level, IM._json(evidence), "active", "owner_apply", 1, principal.by, now, now))
            row = connection.execute("SELECT * FROM improvement_activations WHERE id=?", (identifier,)).fetchone()
            result = _public(row)
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
            connection.execute("UPDATE improvement_activations SET state='reverted',reason='owner_revert',"
                               "generation=generation+1,updated_at=? WHERE id=? AND brain_id=?",
                               (time.time(), activation_id, brain))
            result = _public(connection.execute("SELECT * FROM improvement_activations WHERE id=?",
                                                (activation_id,)).fetchone())
            self.assets._event(connection, principal, event_key, "activation_revert", payload, result)
            return result

    def reconcile(self, principal) -> list:
        """Record suspensions for pointers whose basis changed. Read time already refuses them."""
        import skill_router as SR
        brain = IM._brain(principal)
        if not self._available():
            return []
        with closing(self.store._conn()) as connection:
            rows = connection.execute("SELECT a.*,t.status AS target_status FROM improvement_activations a "
                "JOIN improvement_targets t ON t.id=a.target_id AND t.brain_id=a.brain_id "
                "WHERE a.brain_id=? AND a.state='active'", (brain,)).fetchall()
            pending = []
            for row in rows:
                if row["target_status"] != "live":
                    pending.append((row, "target_retired"))
                elif not self._authority_active(connection, brain, row["candidate_id"]):
                    pending.append((row, "authority_revoked"))
                else:
                    canonical = SR.read_skill_asset(Path(brain), _slug(row["canonical_ref"]))
                    if canonical is None or canonical.relative_path != row["canonical_ref"]:
                        pending.append((row, "source_unavailable"))
                    elif canonical.content_hash != row["base_hash"]:
                        pending.append((row, "canonical_changed"))
        suspended = []
        for row, reason in pending:
            with self.store._Tx(self.store) as connection:
                changed = connection.execute(
                    "UPDATE improvement_activations SET state='suspended',reason=?,generation=generation+1,updated_at=? "
                    "WHERE id=? AND brain_id=? AND state='active' AND generation=?",
                    (reason, time.time(), row["id"], brain, row["generation"])).rowcount
            if changed:
                suspended.append({"activation_id": row["id"], "reason": reason})
        return suspended


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


def _turn_agent_key() -> str:
    import turn_context
    turn = turn_context.current() or {}
    agent = turn.get("agent") or {}
    return str(agent.get("key") or "")


def _overlay(root, slug, canonical):
    sources = _SOURCES[0]
    if sources is None or _CLI_TRANSPORT.get():
        return None
    agent_key = _turn_agent_key()
    if not agent_key or not _AGENT_KEY.fullmatch(agent_key):
        return None
    database, blobs = sources
    if not database.is_file():
        return None
    brain = str(Path(root).resolve(strict=True))
    canonical_ref = f"skills/{slug}/SKILL.md"
    if canonical.relative_path != canonical_ref:
        return None
    connection = sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True, timeout=5)
    connection.row_factory = sqlite3.Row
    with closing(connection):
        if not _has_table(connection):
            return None
        row = connection.execute(
            "SELECT a.* FROM improvement_activations a JOIN improvement_targets t "
            "ON t.id=a.target_id AND t.brain_id=a.brain_id WHERE a.brain_id=? AND a.canonical_ref=? "
            "AND a.scope_hash=? AND a.state='active' AND t.status='live' AND EXISTS("
            "SELECT 1 FROM improvement_candidate_authorities c JOIN improvement_candidate_authority_grants g "
            "ON g.authority_id=c.id AND g.brain_id=c.brain_id WHERE c.brain_id=a.brain_id "
            "AND c.candidate_id=a.candidate_id AND c.kind='exact_diff' AND g.status='active')",
            (brain, canonical_ref, scope_hash(agent_key))).fetchone()
    if row is None or row["base_hash"] != canonical.content_hash or row["frontmatter_hash"] != canonical.frontmatter_hash:
        return None
    raw = blobs.read(brain, row["content_hash"])
    import skill_router as SR
    return SR.SkillAsset(canonical.slug, canonical.relative_path, raw, row["content_hash"], canonical.frontmatter_hash)


def effective_skill_asset(root, slug):
    """The skill bytes this turn should see: the scope's active overlay, else the canonical read."""
    import skill_router as SR
    canonical = SR.read_skill_asset(root, slug)
    if canonical is None:
        return None
    try:
        return _overlay(root, slug, canonical) or canonical
    except (OSError, ValueError, sqlite3.Error, AssetUnavailable, RuntimeError) as error:
        # An unreadable pointer falls back to the canonical skill: never worse than baseline.
        print(f"[improvement activation] {type(error).__name__}: {error}", file=sys.stderr)
        return canonical
