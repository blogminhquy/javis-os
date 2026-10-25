"""M3 canary: partial allocation, owner verdicts, monitoring, promotion and auto-scoped grants.

A canary is an M2E activation with a partial allocation. Each assistant chat session is hashed
with the canary salt into a bucket 0..99: below the allocation it sees the candidate, otherwise
the canonical skill. A conversation therefore stays in one arm for its whole life.

Observation counts only explicit owner verdicts ("Đạt" / "Chưa đạt") on recorded exposures of
both arms. Emoji reactions are feelings, not acceptance, and never count. The window is
sufficient at 7 days AND 10 canary verdicts; until then the canary is insufficient_observation and
it never becomes active just because time passed. Two failing canary sessions suspend the
activation at once (the prior compatible version is the canonical skill).

A fake clock can drive these rules in tests; that is a technical check, never a live window.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import secrets
import time
from contextlib import closing
from typing import Callable

import improvement_store as IM
from improvement_activation import Activations, apply_evidence, selector, scope_hash

MIN_DAYS = 7
MIN_CANARY_VERDICTS = 10
FAIL_SESSIONS_TO_SUSPEND = 2
DEFAULT_ALLOCATION = 10
_IDENTIFIER = re.compile(r"iac_[0-9a-f]{32}")
_GRANT = re.compile(r"ias_[0-9a-f]{32}")


def bucket(salt: str, session_id: str) -> int:
    return int(hashlib.sha256(f"{salt}:{session_id}".encode("utf-8")).hexdigest()[:8], 16) % 100


def arm(allocation_pct: int, salt: str, session_id: str) -> str:
    return "canary" if session_id and bucket(salt, session_id) < allocation_pct else "control"


def allocation(value) -> int:
    if type(value) is not int or not 1 <= value <= 99:
        raise ValueError("invalid_canary_allocation")
    return value


def observation(exposures: list, verdicts: list, *, started_at: float, now: float) -> dict:
    """Pure counts per arm; verdicts are (session_id, message_id, arm, verdict) rows."""
    arms = {name: {"exposures": 0, "pass": 0, "fail": 0} for name in ("canary", "control")}
    for row in exposures:
        arms[row["arm"]]["exposures"] += 1
    fail_sessions = set()
    for row in verdicts:
        arms[row["arm"]][row["verdict"]] += 1
        if row["arm"] == "canary" and row["verdict"] == "fail":
            fail_sessions.add(row["session_id"])
    days = max(0.0, (now - started_at) / 86400)
    canary_verdicts = arms["canary"]["pass"] + arms["canary"]["fail"]
    return {"days": round(days, 3), "arms": arms, "canary_fail_sessions": len(fail_sessions),
            "sufficient": days >= MIN_DAYS and canary_verdicts >= MIN_CANARY_VERDICTS,
            "required": {"days": MIN_DAYS, "canary_verdicts": MIN_CANARY_VERDICTS}}


def wilson(successes: int, trials: int, z: float = 1.96):
    if trials <= 0:
        return None
    phat = successes / trials
    denominator = 1 + z * z / trials
    centre = (phat + z * z / (2 * trials)) / denominator
    half = z * math.sqrt(phat * (1 - phat) / trials + z * z / (4 * trials * trials)) / denominator
    return [round(max(0.0, centre - half), 4), round(min(1.0, centre + half), 4)]


def pilot_conclusion(summary: dict, kind: str) -> dict:
    """Honest per-business conclusion from one comparison summary (spec 24.3)."""
    outcomes = summary.get("outcomes", {}).get("qualification" if kind == "final" else "tuning", {})
    wins, losses = outcomes.get("win", 0), outcomes.get("loss", 0)
    if summary.get("mechanical_verdict") == "rejected":
        conclusion = "worse"
    elif kind == "final" and (summary.get("pilot") or {}).get("numeric_gate") is True:
        conclusion = "improved_in_scope"
    elif summary.get("complete") and wins + losses == 0:
        conclusion = "equivalent"
    else:
        conclusion = "insufficient_evidence"
    return {"conclusion": conclusion, "kind": kind, "discordant": wins + losses, "wins": wins, "losses": losses,
            "ties": outcomes.get("tie", 0), "unknown": outcomes.get("unknown", 0),
            "win_rate_interval": wilson(wins, wins + losses), "p_value": (summary.get("statistics") or {}).get("p_value"),
            "business_eligibility": "unverified"}


class Canaries:
    def __init__(self, activations: Activations, *, clock: Callable[[], float] = time.time):
        if type(activations) is not Activations:
            raise TypeError("concrete_activations_required")
        self.activations, self.assets, self.store = activations, activations.assets, activations.store
        self.clock = clock

    # -- reads -----------------------------------------------------------------------------------

    def _row(self, connection, brain, activation_id):
        if type(activation_id) is not str or not _IDENTIFIER.fullmatch(activation_id):
            raise ValueError("invalid_activation")
        row = connection.execute("SELECT c.*,a.state AS activation_state,a.generation AS activation_generation "
            "FROM improvement_canaries c JOIN improvement_activations a ON a.id=c.activation_id AND a.brain_id=c.brain_id "
            "WHERE c.activation_id=? AND c.brain_id=?", (activation_id, brain)).fetchone()
        if row is None:
            raise PermissionError("canary_unavailable")
        return row

    def _observe(self, connection, brain, row) -> dict:
        exposures = connection.execute("SELECT arm FROM improvement_canary_exposures WHERE activation_id=? AND brain_id=?",
                                       (row["activation_id"], brain)).fetchall()
        verdicts = connection.execute("SELECT v.session_id,v.message_id,v.verdict,e.arm FROM improvement_canary_verdicts v "
            "JOIN improvement_canary_exposures e ON e.activation_id=v.activation_id AND e.session_id=v.session_id "
            "AND e.message_id=v.message_id WHERE v.activation_id=? AND v.brain_id=?",
            (row["activation_id"], brain)).fetchall()
        return observation([dict(x) for x in exposures], [dict(x) for x in verdicts],
                           started_at=row["started_at"], now=self.clock())

    def summary(self, principal, activation_id: str) -> dict:
        brain = IM._brain(principal)
        with closing(self.store._conn()) as connection:
            row = self._row(connection, brain, activation_id)
            result = {key: row[key] for key in ("activation_id", "allocation_pct", "started_at", "state", "reason", "generation")}
            result["activation_state"] = row["activation_state"]
            result["observation"] = self._observe(connection, brain, row)
            result["exposures"] = [dict(x) for x in connection.execute(
                "SELECT e.session_id,e.message_id,e.arm,e.at,v.verdict FROM improvement_canary_exposures e "
                "LEFT JOIN improvement_canary_verdicts v ON v.activation_id=e.activation_id AND v.session_id=e.session_id "
                "AND v.message_id=e.message_id WHERE e.activation_id=? AND e.brain_id=? "
                "ORDER BY (v.verdict IS NULL) DESC,e.at DESC LIMIT 100",
                (activation_id, brain))]
        return result

    def pilot_report(self, principal, report_id: str) -> dict:
        """The honest per-business conclusion of one published comparison report (spec 24.3)."""
        brain = IM._brain(principal)
        if type(report_id) is not str or not re.fullmatch(r"icr_[0-9a-f]{32}", report_id):
            raise ValueError("invalid_report")
        with closing(self.store._conn()) as connection:
            row = connection.execute("SELECT r.report_hash,r.blob_hash,c.kind,c.ordinal,c.experiment_id "
                "FROM improvement_comparison_reports r JOIN improvement_comparisons c ON c.id=r.comparison_id "
                "AND c.brain_id=r.brain_id WHERE r.id=? AND r.brain_id=?", (report_id, brain)).fetchone()
        if row is None:
            raise PermissionError("report_unavailable")
        report = json.loads(self.assets.blobs.read(brain, row["blob_hash"]).decode("utf-8"))
        if IM._hash(report) != row["report_hash"]:
            raise IM.ConflictError("report_changed")
        return {"report_id": report_id, "experiment_id": row["experiment_id"], "ordinal": row["ordinal"],
                **pilot_conclusion(report["summary"], row["kind"]),
                "evidence_class": report["summary"].get("evidence_class")}

    # -- owner verdicts and monitoring -------------------------------------------------------------

    def verdict(self, principal, activation_id: str, session_id: str, message_id: int, verdict: str, *,
                reason: str = "", event_key: str) -> dict:
        brain = IM._brain(principal)
        if verdict not in ("pass", "fail") or type(message_id) is not int or message_id <= 0:
            raise ValueError("invalid_canary_verdict")
        if type(session_id) is not str or not 0 < len(session_id) <= 200 or type(reason) is not str or len(reason) > 500:
            raise ValueError("invalid_canary_verdict")
        payload = {"activation_id": activation_id, "session_id": session_id, "message_id": message_id,
                   "verdict": verdict, "reason": reason}
        with self.store._Tx(self.store) as connection:
            replay = self.assets._replay(connection, brain, event_key, "canary_verdict", payload)
            if replay is not None:
                return replay
            row = self._row(connection, brain, activation_id)
            if row["state"] != "canary" or row["activation_state"] != "active":
                raise IM.ConflictError("canary_not_running")
            exposure = connection.execute("SELECT arm FROM improvement_canary_exposures WHERE activation_id=? AND brain_id=? "
                "AND session_id=? AND message_id=?", (activation_id, brain, session_id, message_id)).fetchone()
            if exposure is None:
                raise PermissionError("canary_exposure_unavailable")
            if connection.execute("SELECT 1 FROM improvement_canary_verdicts WHERE activation_id=? AND session_id=? "
                                  "AND message_id=?", (activation_id, session_id, message_id)).fetchone():
                raise IM.ConflictError("canary_verdict_recorded")
            connection.execute("INSERT INTO improvement_canary_verdicts VALUES(?,?,?,?,?,?,?,?)",
                               (activation_id, brain, session_id, message_id, verdict, reason, principal.by, self.clock()))
            observed = self._observe(connection, brain, row)
            suspended = False
            if (row["state"] == "canary" and row["activation_state"] == "active"
                    and observed["canary_fail_sessions"] >= FAIL_SESSIONS_TO_SUSPEND):
                # Two independent failing canary sessions: stop serving the candidate right now.
                now = self.clock()
                connection.execute("UPDATE improvement_activations SET state='suspended',reason='canary_regression',"
                                   "generation=generation+1,updated_at=? WHERE id=? AND brain_id=? AND state='active'",
                                   (now, activation_id, brain))
                connection.execute("UPDATE improvement_canaries SET state='ended',reason='canary_regression',"
                                   "generation=generation+1,updated_at=? WHERE activation_id=? AND brain_id=?",
                                   (now, activation_id, brain))
                suspended = True
            result = {"activation_id": activation_id, "arm": exposure["arm"], "verdict": verdict,
                      "suspended": suspended, "observation": observed}
            self.assets._event(connection, principal, event_key, "canary_verdict", payload, result)
            return result

    # -- promotion -----------------------------------------------------------------------------------

    def promote(self, principal, activation_id: str, *, expected_generation: int, event_key: str) -> dict:
        import skill_router as SR
        from pathlib import Path
        from improvement_activation import _file_identity, _slug
        brain = IM._brain(principal)
        if type(expected_generation) is not int or expected_generation < 1:
            raise ValueError("invalid_canary_generation")
        payload = {"activation_id": activation_id, "expected_generation": expected_generation}
        with closing(self.store._conn()) as connection:
            replay = self.assets._replay(connection, brain, event_key, "canary_promote", payload)
            if replay is not None:
                return replay
            row = self._row(connection, brain, activation_id)
            activation = connection.execute("SELECT * FROM improvement_activations WHERE id=?", (activation_id,)).fetchone()
            candidate = {"id": activation["candidate_id"], "experiment_id": activation["experiment_id"]}
            refs = self.activations._report_refs(connection, brain, candidate)
            apply_evidence(self.activations._reports(connection, brain, candidate))
        canonical = SR.read_skill_asset(Path(brain), _slug(activation["canonical_ref"]))
        with self.store._Tx(self.store) as connection:
            replay = self.assets._replay(connection, brain, event_key, "canary_promote", payload)
            if replay is not None:
                return replay
            row = self._row(connection, brain, activation_id)
            if row["generation"] != expected_generation:
                raise IM.ConflictError("stale_canary")
            if row["state"] != "canary" or row["activation_state"] != "active":
                raise IM.ConflictError("canary_not_running")
            observed = self._observe(connection, brain, row)
            if not observed["sufficient"]:
                raise PermissionError("canary_insufficient_observation")
            target = self.assets._target(connection, brain, activation["target_id"])
            final = SR.read_skill_asset(Path(brain), _slug(activation["canonical_ref"]))
            if (not self.activations._authority_active(connection, brain, activation["candidate_id"])
                    or self.activations._report_refs(connection, brain, candidate) != refs
                    or self.activations._selection_refuses(connection, brain, candidate)
                    or target["status"] != "live" or canonical is None or final is None
                    or canonical.content_hash != activation["base_hash"] or final.content_hash != activation["base_hash"]
                    or _file_identity(brain, activation["canonical_ref"]) != target["identity"]):
                raise IM.ConflictError("activation_basis_changed")
            connection.execute("UPDATE improvement_canaries SET state='promoted',reason='owner_promote',"
                               "generation=generation+1,updated_at=? WHERE activation_id=? AND brain_id=?",
                               (self.clock(), activation_id, brain))
            result = {"activation_id": activation_id, "state": "promoted", "generation": expected_generation + 1,
                      "observation": observed}
            self.assets._event(connection, principal, event_key, "canary_promote", payload, result)
            return result

    # -- conditional activation grants -----------------------------------------------------------------

    def grants(self, principal, *, target_id: str | None = None) -> list:
        brain = IM._brain(principal)
        if IM._schema_version(self.store) < 12:
            return []
        query, args = "SELECT * FROM improvement_auto_scopes WHERE brain_id=?", [brain]
        if target_id is not None:
            query, args = query + " AND target_id=?", args + [target_id]
        with closing(self.store._conn()) as connection:
            rows = connection.execute(query + " ORDER BY granted_at DESC LIMIT 100", args).fetchall()
        return [{**{k: row[k] for k in ("target_id", "scope_hash", "surface", "allocation_pct", "status", "generation",
                                         "granted_at", "revoked_at")}, "grant_id": row["id"],
                 "selector": json.loads(row["selector_json"])} for row in rows]

    def grant(self, principal, target_id: str, agent_slug: str, allocation_pct: int, *, event_key: str) -> dict:
        import skill_router as SR
        brain = IM._brain(principal)
        allocation(allocation_pct)
        if type(agent_slug) is not str or not SR.valid_file_slug(agent_slug):
            raise ValueError("invalid_activation_agent")
        payload = {"target_id": target_id, "agent_slug": agent_slug, "allocation_pct": allocation_pct}
        IM.ensure(self.store)
        with closing(self.store._conn()) as connection:
            replay = self.assets._replay(connection, brain, event_key, "auto_scope_grant", payload)
            if replay is not None:
                return replay
            target = self.assets._target(connection, brain, target_id)
            if target["kind"] != "skill" or target["status"] != "live":
                raise PermissionError("target_unavailable")
        agent_key = str(self.activations.agent_key(brain, agent_slug) or "")
        chosen, scope = selector(agent_key, agent_slug), scope_hash(agent_key)
        with self.store._Tx(self.store) as connection:
            replay = self.assets._replay(connection, brain, event_key, "auto_scope_grant", payload)
            if replay is not None:
                return replay
            if connection.execute("SELECT 1 FROM improvement_auto_scopes WHERE brain_id=? AND target_id=? AND scope_hash=? "
                                  "AND status='active'", (brain, target_id, scope)).fetchone():
                raise IM.ConflictError("auto_scope_exists")
            identifier = "ias_" + secrets.token_hex(16)
            connection.execute("INSERT INTO improvement_auto_scopes VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                               (identifier, brain, target_id, scope, IM._json(chosen), "skill_body", allocation_pct,
                                "active", 1, principal.by, self.clock(), None))
            result = {"grant_id": identifier, "target_id": target_id, "scope_hash": scope, "selector": chosen,
                      "allocation_pct": allocation_pct, "status": "active", "generation": 1}
            self.assets._event(connection, principal, event_key, "auto_scope_grant", payload, result)
            return result

    def revoke_grant(self, principal, grant_id: str, *, expected_generation: int, event_key: str) -> dict:
        brain = IM._brain(principal)
        if type(grant_id) is not str or not _GRANT.fullmatch(grant_id) or expected_generation != 1:
            raise ValueError("invalid_auto_scope")
        payload = {"grant_id": grant_id, "expected_generation": expected_generation}
        with self.store._Tx(self.store) as connection:
            replay = self.assets._replay(connection, brain, event_key, "auto_scope_revoke", payload)
            if replay is not None:
                return replay
            changed = connection.execute("UPDATE improvement_auto_scopes SET status='revoked',generation=2,revoked_at=? "
                "WHERE id=? AND brain_id=? AND status='active'", (self.clock(), grant_id, brain)).rowcount
            if not changed:
                raise IM.ConflictError("auto_scope_not_active")
            # Canaries the grant already opened stay: revocation stops new automatic ones (spec 18.2).
            result = {"grant_id": grant_id, "status": "revoked", "generation": 2}
            self.assets._event(connection, principal, event_key, "auto_scope_revoke", payload, result)
            return result

    def auto_apply_for_report(self, principal, report_id: str) -> list:
        """After a final report: open a canary in every granted scope, only for a qualified candidate."""
        brain = IM._brain(principal)
        if IM._schema_version(self.store) < 12:
            return []
        with closing(self.store._conn()) as connection:
            report = connection.execute("SELECT r.id,c.experiment_id,c.ordinal,c.kind FROM improvement_comparison_reports r "
                "JOIN improvement_comparisons c ON c.id=r.comparison_id AND c.brain_id=r.brain_id WHERE r.id=? AND r.brain_id=?",
                (report_id, brain)).fetchone()
            if report is None or report["kind"] != "final" or not self._report_qualifies(brain, report_id):
                return []
            arm = connection.execute("SELECT candidate_id FROM improvement_experiment_arms WHERE experiment_id=? AND brain_id=? "
                                     "AND ordinal=?", (report["experiment_id"], brain, report["ordinal"])).fetchone()
            if arm is None:
                return []
            candidate = connection.execute("SELECT * FROM improvement_skill_candidates WHERE id=? AND brain_id=?",
                                           (arm["candidate_id"], brain)).fetchone()
            try:
                level, _ = apply_evidence(self.activations._reports(connection, brain, candidate))
            except PermissionError:
                return []
            if level != "qualified":
                return []
        return self.open_granted(principal, candidate)

    def _report_qualifies(self, brain, report_id) -> bool:
        """The report just published must itself be an eligible final that passed the numeric gate."""
        with closing(self.store._conn()) as connection:
            row = connection.execute("SELECT report_hash,blob_hash FROM improvement_comparison_reports WHERE id=? AND brain_id=?",
                                     (report_id, brain)).fetchone()
        if row is None:
            return False
        report = json.loads(self.assets.blobs.read(brain, row["blob_hash"]).decode("utf-8"))
        summary = report.get("summary") or {}
        return (IM._hash(report) == row["report_hash"] and summary.get("mechanical_verdict") == "eligible"
                and (summary.get("pilot") or {}).get("numeric_gate") is True)

    def open_granted(self, principal, candidate) -> list:
        """Open the granted canaries for one qualified candidate (caller established the evidence)."""
        brain = IM._brain(principal)
        with closing(self.store._conn()) as connection:
            grants = connection.execute("SELECT * FROM improvement_auto_scopes WHERE brain_id=? AND target_id=? "
                                        "AND status='active'", (brain, candidate["target_id"])).fetchall()
        opened = []
        for grant in grants:
            slug = json.loads(grant["selector_json"]).get("agent_slug") or ""
            try:
                if scope_hash(str(self.activations.agent_key(brain, slug) or "")) != grant["scope_hash"]:
                    raise IM.ConflictError("auto_scope_identity_changed")
                opened.append(self.activations.apply(principal, candidate["id"], slug,
                    event_key=f"auto-canary:{grant['id']}:{candidate['id']}", allocation_pct=grant["allocation_pct"]))
            except (PermissionError, ValueError, IM.ConflictError) as error:
                opened.append({"grant_id": grant["id"], "skipped": str(error)})
        return opened

