"""M8 adaptive prioritisation and library governance (spec 8.1, 15.3, 16.5, 18.2, 23 M8).

- Needs are ranked only from the sources spec 8.1 accepts (owner request, the same failure in at least two
  independent tasks, owner feedback naming the fault, a review trace). Reactions, agreement, usage, elapsed time
  never open work; no source means an empty queue and no model call. Cost is not an objective.
- Refinement is bounded: at most two consecutive steps per failure family in a cycle; a third needs new evidence
  or the owner. Three tuning pairs with no behaviour change end the family with `no_progress`. A consumed
  holdout is never iterated on.
- Export carries only what the owner chose to share: procedure texts, dependency versions and filtered verdict
  summaries, secrets scrubbed; never raw conversations, owner rules, customer data or tokens. Import yields
  untested candidates only: no activation, permission or score travels.
- Governance lists every live improvement pointer of a brain and suspends them all on the owner's command
  (spec 18.2 "tạm ngừng"): state in the database, so it holds across restarts and processes.
"""
from __future__ import annotations

import json
import math
import re
import secrets
import sys
import time
from contextlib import closing
from typing import Callable

import improvement_store as IM

SOURCES = ("owner_request", "repeated_failure", "owner_feedback", "review_trace")
SEVERITY = {"critical": 3, "high": 2, "normal": 1}
MAX_STEPS = 2
NO_PROGRESS_PAIRS = 3
EXPORT_VERSION = 1
_FAMILY = re.compile(r"[A-Za-z0-9_.:-]{1,80}")
_FORBIDDEN_EXPORT = ("owner_rules", "messages", "conversation", "transcript", "customer", "token", "secret",
                     "password", "api_key", "phone", "email", "address")


def rank_needs(signals, *, now: float, half_life_s: float = 7 * 86400) -> list:
    """Accepted signals -> ordered needs. Each signal: {family, source, severity, independent_tasks, last_at}.
    A repeated failure needs at least two independent tasks; anything else from an unaccepted source is dropped."""
    if type(signals) is not list:
        raise ValueError("invalid_signals")
    needs = {}
    for signal in signals:
        if type(signal) is not dict or signal.get("source") not in SOURCES:
            continue  # emoji, agreement, usage, "long time no change": never a reason to start
        family = signal.get("family")
        if type(family) is not str or not _FAMILY.fullmatch(family):
            continue
        try:
            tasks = int(signal.get("independent_tasks") or 0)
            last = float(signal.get("last_at") or 0)
        except (TypeError, ValueError, OverflowError):
            continue  # a malformed signal is dropped, never a reason to stop ranking the rest
        if signal["source"] == "repeated_failure" and tasks < 2 or not math.isfinite(last):
            continue
        fresh = 10 * 0.5 ** (max(0.0, float(now) - last) / half_life_s)
        score = SEVERITY.get(signal.get("severity"), 1) * 10 + min(max(tasks, 0), 10) + fresh
        if signal["source"] == "owner_request":
            score += 100  # the owner asked: first, but still one item, never a brain-wide sweep
        item = needs.setdefault(family, {"family": family, "score": 0.0, "sources": set()})
        item["score"] = max(item["score"], score)
        item["sources"].add(signal["source"])
    out = [{"family": f, "score": round(v["score"], 4), "sources": sorted(v["sources"])} for f, v in needs.items()]
    return sorted(out, key=lambda x: (-x["score"], x["family"]))


def refinement_decision(steps: list, *, new_evidence: bool, owner_assigned: bool, holdout_consumed: bool) -> dict:
    """Whether one more refinement step may run for a family in this cycle.
    `steps`: earlier steps of this cycle, oldest first, each {"changed": bool} (behaviour or metric moved)."""
    if holdout_consumed:
        return {"allowed": False, "reason": "holdout_consumed"}
    if len(steps) >= NO_PROGRESS_PAIRS and not any(s.get("changed") for s in steps[-NO_PROGRESS_PAIRS:]):
        return {"allowed": False, "reason": "no_progress"}
    if len(steps) >= MAX_STEPS and not (new_evidence or owner_assigned):
        return {"allowed": False, "reason": "refinement_limit"}
    return {"allowed": True, "reason": ""}


def _scrub(text: str) -> str:
    from team_bundle import scrub
    return scrub(text)


# Private data a procedure must not carry out of the brain: phone numbers, e-mail addresses, long opaque tokens.
_PRIVATE = re.compile(r"(?:\+?84|\b0)\d{9,10}\b|[\w.+-]+@[\w-]+(?:\.[\w-]+)+|\b[A-Fa-f0-9]{24,}\b|"
                      r"\b(?=[A-Za-z0-9_-]*\d)(?=[A-Za-z0-9_-]*[A-Za-z])[A-Za-z0-9_-]{32,}\b")


def _shareable(text: str) -> str:
    """Refuse rather than rewrite: the owner sees why, and a rewrite could grow the text past its limit."""
    if _scrub(text) != text:
        raise ValueError("export_secret_detected")
    if _PRIVATE.search(text):
        raise ValueError("export_private_data_detected")
    return text


def export_package(procedures: list, dependencies: dict, reports: list) -> dict:
    """Owner-chosen items -> a shareable package. Raises on any field outside the closed shapes."""
    clean_procedures = []
    for item in procedures:
        if type(item) is not dict or set(item) != {"agent_slug", "text"}:
            raise ValueError("invalid_export_procedure")
        import improvement_agent
        clean_procedures.append({"agent_slug": str(item["agent_slug"]),
                                 "text": _shareable(improvement_agent.validate_procedure(item["text"]))})
    if type(dependencies) is not dict or any(type(k) is not str or type(v) is not str for k, v in dependencies.items()):
        raise ValueError("invalid_export_dependencies")
    clean_reports = []
    for report in reports:
        if type(report) is not dict or set(report) - {"family", "verdict", "cases", "evidence_level"}:
            raise ValueError("invalid_export_report")
        clean_reports.append({k: report[k] for k in ("family", "verdict", "cases", "evidence_level") if k in report})
    # Shapes are closed; the only free names are dependency keys, which must not smuggle private data in.
    if any(word in key.lower() for key in dependencies for word in _FORBIDDEN_EXPORT):
        raise ValueError("export_forbidden_field")
    package = {"format": "javis-improvement-package", "version": EXPORT_VERSION, "procedures": clean_procedures,
               "dependencies": dict(sorted(dependencies.items())), "reports": clean_reports}
    return {**package, "package_hash": IM._hash(package)}


def import_package(package) -> list:
    """An untrusted package -> untested candidates. Activation, grants, verdicts and scores never come along."""
    if type(package) is not dict or package.get("format") != "javis-improvement-package" or package.get("version") != EXPORT_VERSION:
        raise ValueError("invalid_import_package")
    body = {k: package[k] for k in ("format", "version", "procedures", "dependencies", "reports") if k in package}
    if package.get("package_hash") != IM._hash(body):
        raise ValueError("import_package_hash_mismatch")
    import improvement_agent
    import skill_router
    procedures = package.get("procedures") or []
    if type(procedures) is not list or len(procedures) > 20:
        raise ValueError("import_package_too_large")
    out = []
    for item in procedures:
        if (type(item) is not dict or set(item) != {"agent_slug", "text"} or type(item["agent_slug"]) is not str
                or not skill_router.valid_file_slug(item["agent_slug"])):
            raise ValueError("invalid_import_procedure")
        out.append({"kind": "procedure", "agent_slug": item["agent_slug"],
                    "text": _shareable(improvement_agent.validate_procedure(item["text"])), "evidence": "untested"})
    return out


class Governance:
    """Brain-wide view and pause of live improvement pointers (spec 18.2 "tạm ngừng").

    Pause moves every live pointer to `suspended` with reason `owner_pause`, so the record tells a governance pause
    from single owner reverts; new work uses the baseline at once. Bundles in flight are failed by CAS first (their
    running apply loses its heartbeat and rolls itself back), active bundles are suspended with their members, and
    active auto-scope grants are revoked so no canary opens on its own afterwards. Everything is database state, so
    it holds across restarts and processes; new owner applies stay possible (pause is not policy `off`)."""

    _TABLES = {"bundle": "improvement_bundle_activations", "skill": "improvement_activations",
               "procedure": "improvement_agent_overlays", "routing": "improvement_routing_overlays"}

    def __init__(self, assets, *, activations=None, procedures=None, routing=None, bundles=None, canaries=None,
                 clock: Callable[[], float] = time.time):
        if type(assets) is not IM.ImprovementStore:
            raise TypeError("concrete_governance_assets_required")
        self.assets, self.store, self.clock = assets, assets.store, clock
        self.activations, self.procedures, self.routing, self.bundles, self.canaries = (
            activations, procedures, routing, bundles, canaries)

    def _tables(self, connection) -> set:
        return {r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}

    def reconcile(self, principal) -> None:
        """Record drift first, so the live list is what the next turn would really serve."""
        for service in (self.bundles, self.activations, self.procedures, self.routing):
            if service is None:
                continue
            try:
                service.reconcile(principal)
            except Exception as error:  # noqa: BLE001 - a view must still answer
                print(f"[improvement governance] reconcile: {type(error).__name__}: {error}", file=sys.stderr)

    def live(self, principal) -> list:
        """Live pointers; a member of a live bundle is listed under its bundle, not on its own."""
        brain = IM._brain(principal)
        out = []
        with closing(self.store._conn()) as connection:
            tables = self._tables(connection)
            members = set()
            if "improvement_bundle_members" in tables:
                members = {(r["kind"], r["pointer_id"]) for r in connection.execute(
                    "SELECT m.kind,m.pointer_id FROM improvement_bundle_members m JOIN improvement_bundle_activations b "
                    "ON b.id=m.bundle_id AND b.brain_id=m.brain_id WHERE m.brain_id=? AND b.state IN ('applying','active')",
                    (brain,))}
            for kind, table in self._TABLES.items():
                if table not in tables:
                    continue
                states = "('applying','active')" if kind == "bundle" else "('active')"
                for r in connection.execute(f"SELECT id,generation,state FROM {table} WHERE brain_id=? AND state IN {states}",
                                            (brain,)):
                    if (kind, r["id"]) not in members:
                        out.append({"kind": kind, "pointer_id": r["id"], "generation": r["generation"], "state": r["state"]})
        return out

    def grants(self, principal) -> list:
        if self.canaries is None:
            return []
        return [g for g in self.canaries.grants(principal) if g.get("status") == "active"]

    @staticmethod
    def _key(event_key, *parts) -> str:
        # A fixed-length derived key: any accepted outer key stays within the event-key limit.
        return "gov-" + IM._hash([event_key, *parts])[:48]

    def _suspend(self, principal, kind, pointer_id, generation) -> bool:
        brain = IM._brain(principal)
        if kind == "skill":
            with closing(self.store._conn()) as connection:
                row = connection.execute("SELECT * FROM improvement_activations WHERE id=? AND brain_id=?",
                                         (pointer_id, brain)).fetchone()
            if row is None or row["state"] != "active" or row["generation"] != generation:
                return False
            return self.activations._suspend(brain, row, "owner_pause")  # also ends a running canary
        with self.store._Tx(self.store) as connection:
            return bool(connection.execute(
                f"UPDATE {self._TABLES[kind]} SET state='suspended',reason='owner_pause',generation=generation+1,"
                "updated_at=? WHERE id=? AND brain_id=? AND state='active' AND generation=?",
                (self.clock(), pointer_id, brain, generation)).rowcount)

    def suspend_all(self, principal, *, event_key: str) -> dict:
        brain = IM._brain(principal)
        if type(event_key) is not str or not 8 <= len(event_key) <= 160:
            raise ValueError("invalid_event_key")
        done, skipped = [], []
        # 1. Bundles: in flight -> failed (CAS), live -> suspended; then their members leave with them.
        for item in [i for i in self.live(principal) if i["kind"] == "bundle"]:
            if item["state"] == "applying":
                won = self.bundles._fail(principal, item["pointer_id"], "owner_pause", expected_generation=item["generation"])
            else:
                won = self._suspend(principal, "bundle", item["pointer_id"], item["generation"])
            if not won:
                skipped.append({**item, "reason": "changed_meanwhile"})
                continue
            with closing(self.store._conn()) as connection:
                row = connection.execute("SELECT manifest_json FROM improvement_bundle_activations WHERE id=? AND brain_id=?",
                                         (item["pointer_id"], brain)).fetchone()
                members = self.bundles._members(connection, brain, item["pointer_id"], json.loads(row["manifest_json"]))
            for kind, pointer in members:
                with closing(self.store._conn()) as connection:
                    member = connection.execute(f"SELECT generation,state FROM {self._TABLES[kind]} WHERE id=? AND brain_id=?",
                                                (pointer, brain)).fetchone()
                if member is not None and member["state"] == "active":
                    self._suspend(principal, kind, pointer, member["generation"])
            done.append(item)
        # 2. Everything else that is live now (members of finished bundles included).
        for item in self.live(principal):
            if item["kind"] == "bundle":
                skipped.append({**item, "reason": "bundle_started_meanwhile"})
            elif self._suspend(principal, item["kind"], item["pointer_id"], item["generation"]):
                done.append(item)
            else:
                skipped.append({**item, "reason": "changed_meanwhile"})
        # 3. No canary may open on its own after a pause.
        revoked = []
        for grant in self.grants(principal):
            try:
                self.canaries.revoke_grant(principal, grant["grant_id"], expected_generation=grant["generation"],
                                           event_key=self._key(event_key, "grant", grant["grant_id"]))
                revoked.append(grant["grant_id"])
            except (IM.ConflictError, PermissionError, ValueError) as error:
                skipped.append({"kind": "grant", "pointer_id": grant["grant_id"], "reason": str(error)})
        # The audit record of this pause (each pointer row already says `owner_pause`).
        payload = {"paused": [[i["kind"], i["pointer_id"]] for i in done], "grants": revoked}
        with self.store._Tx(self.store) as connection:
            self.assets._event(connection, principal, self._key(event_key, "summary", repr(self.clock())),
                               "governance_pause", payload, {"paused": len(done), "grants": len(revoked)})
        return {"suspended": done, "revoked_grants": revoked, "skipped": skipped, "remaining": self.live(principal)}


class Refinements:
    """The refinement ledger: one row per step of a failure family in a cycle, checked before it is written."""

    def __init__(self, assets, *, clock: Callable[[], float] = time.time):
        if type(assets) is not IM.ImprovementStore:
            raise TypeError("concrete_refinement_assets_required")
        self.assets, self.store, self.clock = assets, assets.store, clock

    def _available(self) -> bool:
        return IM._schema_version(self.store) >= 17

    def steps(self, principal, family: str, cycle: str) -> list:
        brain = IM._brain(principal)
        if not self._available():
            return []
        with closing(self.store._conn()) as connection:
            return [{"step": r["step"], "changed": bool(r["changed"]), "evidence_ref": r["evidence_ref"],
                     "owner_assigned": bool(r["owner_assigned"])} for r in connection.execute(
                "SELECT * FROM improvement_refinements WHERE brain_id=? AND family=? AND cycle=? ORDER BY step",
                (brain, family, cycle))]

    def record(self, principal, family: str, cycle: str, *, changed: bool, evidence_ref: str = "",
               owner_assigned: bool = False, holdout_consumed: bool = False, event_key: str) -> dict:
        """Record the next step only if `refinement_decision` allows it; a refused step writes nothing."""
        brain = IM._brain(principal)
        for value in (family, cycle):
            if type(value) is not str or not _FAMILY.fullmatch(value):
                raise ValueError("invalid_refinement")
        if (type(changed) is not bool or type(owner_assigned) is not bool or type(holdout_consumed) is not bool
                or type(evidence_ref) is not str or len(evidence_ref) > 128):
            raise ValueError("invalid_refinement")
        IM.ensure(self.store)
        if not self._available():
            raise PermissionError("refinements_unavailable")
        payload = {"family": family, "cycle": cycle, "changed": changed, "evidence_ref": evidence_ref,
                   "owner_assigned": owner_assigned, "holdout_consumed": holdout_consumed}
        with self.store._Tx(self.store) as connection:
            replay = self.assets._replay(connection, brain, event_key, "refinement", payload)
            if replay is not None:
                return replay
            rows = connection.execute("SELECT step,changed,evidence_ref FROM improvement_refinements WHERE brain_id=? "
                                      "AND family=? AND cycle=? ORDER BY step", (brain, family, cycle)).fetchall()
            seen = {r["evidence_ref"] for r in rows}
            # New evidence is a trial or comparison report of this brain not used before in this cycle; free text
            # never counts, so the two-step bound cannot be walked around with invented references.
            known = bool(evidence_ref) and any(connection.execute(
                f"SELECT 1 FROM {table} WHERE id=? AND brain_id=?", (evidence_ref, brain)).fetchone()
                for table in ("improvement_trials", "improvement_comparison_reports"))
            new_evidence = known and evidence_ref not in seen
            decision = refinement_decision([{"changed": bool(r["changed"])} for r in rows], new_evidence=new_evidence,
                                           owner_assigned=owner_assigned, holdout_consumed=holdout_consumed)
            if not decision["allowed"]:
                raise PermissionError(decision["reason"])
            step = len(rows) + 1
            connection.execute("INSERT INTO improvement_refinements VALUES(?,?,?,?,?,?,?,?,?,?)",
                               ("irf_" + secrets.token_hex(16), brain, family, cycle, step, int(changed),
                                evidence_ref, int(owner_assigned), principal.by, self.clock()))
            result = {"family": family, "cycle": cycle, "step": step}
            self.assets._event(connection, principal, event_key, "refinement", payload, result)
            return result


def export_procedures(assets, principal, procedure_ids, *, version: str) -> dict:
    """The owner-chosen procedures of this brain as a package (host-read texts, no reports, no owner rules)."""
    brain = IM._brain(principal)
    if type(procedure_ids) is not list or not 1 <= len(procedure_ids) <= 20 or len(set(procedure_ids)) != len(procedure_ids):
        raise ValueError("invalid_export_selection")
    if any(type(i) is not str or not re.fullmatch(r"iap_[0-9a-f]{32}", i) for i in procedure_ids):
        raise ValueError("invalid_export_selection")
    if IM._schema_version(assets.store) < 14:
        raise PermissionError("export_unavailable")
    with closing(assets.store._conn()) as connection:
        rows = {r["id"]: r for r in connection.execute(
            "SELECT id,agent_slug,text FROM improvement_agent_procedures WHERE brain_id=? AND id IN (%s)"
            % ",".join("?" * len(procedure_ids)), (brain, *procedure_ids))}
    if set(rows) != set(procedure_ids):
        raise PermissionError("export_procedure_unavailable")
    return export_package([{"agent_slug": rows[i]["agent_slug"], "text": rows[i]["text"]} for i in procedure_ids],
                          {"javis": str(version)}, [])


class Imports:
    """An untrusted package's items stored as untested candidates; nothing is applied or granted."""

    def __init__(self, assets, *, clock: Callable[[], float] = time.time):
        if type(assets) is not IM.ImprovementStore:
            raise TypeError("concrete_import_assets_required")
        self.assets, self.store, self.clock = assets, assets.store, clock

    def stage(self, principal, package, *, event_key: str) -> list:
        brain = IM._brain(principal)
        items = import_package(package)
        IM.ensure(self.store)
        if IM._schema_version(self.store) < 17:
            raise PermissionError("imports_unavailable")
        payload = {"package_hash": package["package_hash"]}
        with self.store._Tx(self.store) as connection:
            replay = self.assets._replay(connection, brain, event_key, "import", payload)
            if replay is not None:
                return replay["items"]
            for position, item in enumerate(items):
                connection.execute("INSERT OR IGNORE INTO improvement_imports VALUES(?,?,?,?,?,?,?)",
                                   ("iim_" + secrets.token_hex(16), brain, package["package_hash"], position,
                                    IM._json(item), principal.by, self.clock()))
            self.assets._event(connection, principal, event_key, "import", payload, {"items": items})
            return items

    def list(self, principal) -> list:
        brain = IM._brain(principal)
        if IM._schema_version(self.store) < 17:
            return []
        with closing(self.store._conn()) as connection:
            return [{**json.loads(r["item_json"]), "import_id": r["id"], "package_hash": r["package_hash"]}
                    for r in connection.execute("SELECT * FROM improvement_imports WHERE brain_id=? ORDER BY created_at DESC "
                                                "LIMIT 50", (brain,))]
