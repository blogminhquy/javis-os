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
        tasks = int(signal.get("independent_tasks") or 0)
        if signal["source"] == "repeated_failure" and tasks < 2:
            continue
        age = max(0.0, float(now) - float(signal.get("last_at") or 0))
        score = SEVERITY.get(signal.get("severity"), 1) * 10 + min(tasks, 10) + 10 * 0.5 ** (age / half_life_s)
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


def export_package(procedures: list, dependencies: dict, reports: list) -> dict:
    """Owner-chosen items -> a shareable package. Raises on any field outside the closed shapes."""
    clean_procedures = []
    for item in procedures:
        if type(item) is not dict or set(item) != {"agent_slug", "text"}:
            raise ValueError("invalid_export_procedure")
        import improvement_agent
        clean_procedures.append({"agent_slug": str(item["agent_slug"]),
                                 "text": improvement_agent.validate_procedure(_scrub(item["text"]))})
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
    out = []
    for item in package.get("procedures") or []:
        if type(item) is not dict or set(item) != {"agent_slug", "text"}:
            raise ValueError("invalid_import_procedure")
        out.append({"kind": "procedure", "agent_slug": str(item["agent_slug"]),
                    "text": improvement_agent.validate_procedure(_scrub(item["text"])), "evidence": "untested"})
    return out


class Governance:
    """Brain-wide view and suspension of live improvement pointers, through each kind's own service."""

    def __init__(self, assets, *, activations=None, procedures=None, routing=None, bundles=None,
                 clock: Callable[[], float] = time.time):
        if type(assets) is not IM.ImprovementStore:
            raise TypeError("concrete_governance_assets_required")
        self.assets, self.store, self.clock = assets, assets.store, clock
        self.services = {"bundle": bundles, "skill": activations, "procedure": procedures, "routing": routing}

    def live(self, principal) -> list:
        brain = IM._brain(principal)
        queries = {"bundle": "SELECT id,generation FROM improvement_bundle_activations WHERE brain_id=? AND state='active'",
                   "skill": "SELECT id,generation FROM improvement_activations WHERE brain_id=? AND state='active'",
                   "procedure": "SELECT id,generation FROM improvement_agent_overlays WHERE brain_id=? AND state='active'",
                   "routing": "SELECT id,generation FROM improvement_routing_overlays WHERE brain_id=? AND state='active'"}
        out = []
        with closing(self.store._conn()) as connection:
            tables = {r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            for kind, query in queries.items():
                table = query.split(" FROM ")[1].split()[0]
                if table in tables:
                    out += [{"kind": kind, "pointer_id": r["id"], "generation": r["generation"]}
                            for r in connection.execute(query, (brain,))]
        return out

    def suspend_all(self, principal, *, event_key: str) -> dict:
        """Owner's "pause every improvement": bundles first (so members leave together), then the rest. Each
        revert is its own CAS; a pointer that changed meanwhile is reported, not forced."""
        IM._brain(principal)
        if type(event_key) is not str or not 8 <= len(event_key) <= 120:
            raise ValueError("invalid_event_key")
        done, skipped = [], []
        # Bundles first so their members leave together; then read again for what is still live.
        self._each(principal, [i for i in self.live(principal) if i["kind"] == "bundle"], event_key, done, skipped)
        self._each(principal, [i for i in self.live(principal) if i["kind"] != "bundle"], event_key, done, skipped)
        return {"suspended": done, "skipped": skipped, "remaining": self.live(principal)}

    def _each(self, principal, items, event_key, done, skipped):
        for item in items:
            service = self.services.get(item["kind"])
            if service is None:
                skipped.append({**item, "reason": "service_unavailable"})
                continue
            try:
                service.revert(principal, item["pointer_id"], expected_generation=item["generation"],
                               event_key=f"{event_key}-{item['kind']}-{item['pointer_id']}")
                done.append(item)
            except (IM.ConflictError, PermissionError, ValueError) as error:
                # A member already left with its bundle, or someone acted first: nothing to force.
                skipped.append({**item, "reason": str(error)})
            except Exception as error:  # noqa: BLE001
                print(f"[improvement governance] {item['kind']} {item['pointer_id']}: {error}", file=sys.stderr)
                skipped.append({**item, "reason": "storage_unavailable"})


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
        if type(changed) is not bool or type(owner_assigned) is not bool or type(evidence_ref) is not str:
            raise ValueError("invalid_refinement")
        IM.ensure(self.store)
        if not self._available():
            raise PermissionError("refinements_unavailable")
        payload = {"family": family, "cycle": cycle, "changed": changed, "evidence_ref": evidence_ref,
                   "owner_assigned": owner_assigned}
        with self.store._Tx(self.store) as connection:
            replay = self.assets._replay(connection, brain, event_key, "refinement", payload)
            if replay is not None:
                return replay
            rows = connection.execute("SELECT step,changed,evidence_ref FROM improvement_refinements WHERE brain_id=? "
                                      "AND family=? AND cycle=? ORDER BY step", (brain, family, cycle)).fetchall()
            seen = {r["evidence_ref"] for r in rows}
            new_evidence = bool(evidence_ref) and evidence_ref not in seen
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
