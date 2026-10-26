"""M7 Team trials and recipe transfer (spec 16.4, 15.3, 22 T01, T02).

Team arms are compared only on pinned ground. A pin is the host's snapshot of what a Team arm runs with: team,
leader, leader mode and work mode, the job's acceptance criteria when a job is named, roster and roles, and per
member the agent file and owner-rule hashes, the procedure overlay served on the team surface, the content hash of
each granted skill, and the provider/model the team runner would really use (main-model fallback included). The
member prompt as a whole is not hashed: it embeds self-learned lessons that grow during any arm.

Two pins are comparable when they differ only in the one declared change: one member's procedure overlay, or one
skill's content. A roster, role, leader, mode, contract, model or agent-file difference is another experiment
(T01); a declared change that is not observed is reported as such.

A Team trial report is stored apart from Team work: this module has no dependency on the team runner, its
messages, steps or acceptance writes, so recording a trial cannot accept production work or send output (T02).
Lessons written while arms run are not frozen here (no Team trial runner exists yet); the report says so.

A recipe moved to another assistant, team or engine is a new untested candidate there; its verdict and evidence
never travel. Listing filters the exact target and an active, unexpired source before anything is ranked.
"""
from __future__ import annotations

import json
import re
import secrets
import time
from contextlib import closing
from typing import Callable

import improvement_store as IM

CHANGE_KINDS = ("procedure", "skill")
TARGET_KINDS = ("agent", "team", "engine")
ARM_VERDICTS = ("win", "tie", "loss", "unknown")
_REF = re.compile(r"[A-Za-z0-9_.:@/-]{1,160}")
_PIN = re.compile(r"itp_[0-9a-f]{32}")
_MEMBER_KEYS = ("slug", "agent_hash", "owner_rules_hash", "procedure", "skills", "provider", "model", "reasoning")


def pin_manifest(team: dict, members: list, member_info: Callable[[str], dict], contract: str) -> dict:
    """Pure: the comparable ground of one Team arm. `member_info(agent_key)` -> the host's member view with the
    `_MEMBER_KEYS` fields; a missing member makes the team unpinnable."""
    roster = []
    for member in sorted(members, key=lambda m: m["agent_key"]):
        info = member_info(member["agent_key"])
        if not info:
            raise PermissionError("team_member_unavailable")
        skills = info.get("skills") or {}
        if type(skills) is not dict:
            raise ValueError("invalid_member_skills")
        roster.append({"agent_key": member["agent_key"], "role": str(member.get("role") or "member"),
                       **{k: str(info.get(k) or "") for k in _MEMBER_KEYS if k != "skills"},
                       "skills": {str(k): str(v or "") for k, v in sorted(skills.items())}})
    if not roster:
        raise PermissionError("team_has_no_members")
    return {"team_id": team["team_id"], "leader_key": str(team.get("leader_key") or ""),
            "leader_mode": str(team.get("leader_mode") or ""), "work_mode": str(team.get("work_mode") or ""),
            "contract": str(contract or ""), "members": roster}


def validate_change(change) -> dict:
    if (type(change) is not dict or set(change) != {"kind", "ref"} or change["kind"] not in CHANGE_KINDS
            or type(change["ref"]) is not str or not _REF.fullmatch(change["ref"])):
        raise ValueError("invalid_team_change")
    return dict(change)


def compare(baseline: dict, candidate: dict, change: dict) -> dict:
    """Pure T01 check over two pins of one team."""
    change = validate_change(change)
    shape = lambda pin: (pin["team_id"], pin["leader_key"], pin["leader_mode"], pin["work_mode"], pin["contract"],
                         [(m["agent_key"], m["role"], m["slug"]) for m in pin["members"]])
    if shape(baseline) != shape(candidate):
        return {"comparable": False, "reason": "topology_changed"}
    procedures, skills = [], set()
    for before, after in zip(baseline["members"], candidate["members"]):
        if (before["provider"], before["model"], before["reasoning"]) != (after["provider"], after["model"], after["reasoning"]):
            return {"comparable": False, "reason": "model_changed", "agent_key": before["agent_key"]}
        if (before["agent_hash"], before["owner_rules_hash"]) != (after["agent_hash"], after["owner_rules_hash"]):
            return {"comparable": False, "reason": "agent_changed", "agent_key": before["agent_key"]}
        if set(before["skills"]) != set(after["skills"]):
            return {"comparable": False, "reason": "skill_grant_changed", "agent_key": before["agent_key"]}
        if before["procedure"] != after["procedure"]:
            procedures.append(before["agent_key"])
        skills |= {slug for slug in before["skills"] if before["skills"][slug] != after["skills"][slug]}
    expected_procedures = [change["ref"]] if change["kind"] == "procedure" else []
    expected_skills = {change["ref"]} if change["kind"] == "skill" else set()
    if not procedures and not skills:
        return {"comparable": False, "reason": "change_not_observed"}
    if procedures != expected_procedures or skills != expected_skills:
        return {"comparable": False, "reason": "unexpected_change", "procedures": procedures, "skills": sorted(skills)}
    return {"comparable": True, "reason": ""}


def report(comparison: dict, change: dict, arms: dict) -> dict:
    """Pure: what this Team trial may claim. `arms`: {"candidate": win|tie|loss|unknown} against the baseline."""
    change = validate_change(change)
    if type(arms) is not dict or set(arms) != {"candidate"} or arms["candidate"] not in ARM_VERDICTS:
        raise ValueError("invalid_team_arms")
    verdict = arms["candidate"] if comparison.get("comparable") else "incomparable"
    return {"verdict": verdict, "comparison": comparison, "change": change,
            # Evidence for this team and this change only (16.4): not for the member alone, not for other teams,
            # not a production acceptance. Lessons learned while arms ran are not frozen by any runner yet.
            "scope": "team", "transfer": "untested", "production_effects": [], "learning_frozen": False}


def target(value) -> dict:
    if (type(value) is not dict or set(value) != {"kind", "ref"} or value["kind"] not in TARGET_KINDS
            or type(value["ref"]) is not str or not _REF.fullmatch(value["ref"])):
        raise ValueError("invalid_transfer_target")
    return dict(value)


class TeamTrials:
    """Pins and Team trial reports over the improvement store; reads Team state through injected readers."""

    def __init__(self, assets, *, read_team: Callable, member_info: Callable, contract: Callable,
                 clock: Callable[[], float] = time.time):
        """`read_team(brain, team_id)` -> (team, active members) of this brain or raises PermissionError;
        `member_info(brain, agent_key)` -> member view; `contract(brain, team_id, task_id)` -> the job's acceptance
        digest ("" without a job), PermissionError when the job is not this team's."""
        if type(assets) is not IM.ImprovementStore:
            raise TypeError("concrete_team_assets_required")
        self.assets, self.store, self.clock = assets, assets.store, clock
        self.read_team, self.member_info, self.contract = read_team, member_info, contract

    def _available(self) -> bool:
        return IM._schema_version(self.store) >= 16

    def pin(self, principal, team_id: str, *, task_id: str = "", event_key: str) -> dict:
        brain = IM._brain(principal)
        if type(team_id) is not str or not _REF.fullmatch(team_id):
            raise ValueError("invalid_team")
        if type(task_id) is not str or (task_id and not _REF.fullmatch(task_id)):
            raise ValueError("invalid_team_task")
        if not self._available():
            raise PermissionError("team_trials_unavailable")
        payload = {"team_id": team_id, "task_id": task_id}
        # A retry with the same key returns the first pin even if the ground moved since (no live reads first).
        with closing(self.store._conn()) as connection:
            replay = self.assets._replay(connection, brain, event_key, "team_pin", payload)
            if replay is not None:
                return replay
        team, members = self.read_team(brain, team_id)
        if str(team.get("brain_id") or "") != brain:
            raise PermissionError("team_unavailable")
        manifest = pin_manifest(team, members, lambda key: self.member_info(brain, key),
                                self.contract(brain, team_id, task_id) if task_id else "")
        digest = IM._hash(manifest)
        with self.store._Tx(self.store) as connection:
            replay = self.assets._replay(connection, brain, event_key, "team_pin", payload)
            if replay is not None:
                return replay
            existing = connection.execute("SELECT id FROM improvement_team_pins WHERE brain_id=? AND manifest_hash=?",
                                          (brain, digest)).fetchone()
            identifier = existing["id"] if existing else "itp_" + secrets.token_hex(16)
            if existing is None:
                connection.execute("INSERT INTO improvement_team_pins VALUES(?,?,?,?,?,?,?)",
                                   (identifier, brain, team_id, IM._json(manifest), digest, principal.by, self.clock()))
            result = {"pin_id": identifier, "manifest_hash": digest, "manifest": manifest}
            self.assets._event(connection, principal, event_key, "team_pin", payload, result)
            return result

    def trials(self, principal, team_id: str) -> list:
        brain = IM._brain(principal)
        if not self._available():
            return []
        with closing(self.store._conn()) as connection:
            rows = connection.execute(
                "SELECT t.* FROM improvement_team_trials t JOIN improvement_team_pins p ON p.id=t.baseline_pin_id "
                "AND p.brain_id=t.brain_id WHERE t.brain_id=? AND p.team_id=? ORDER BY t.created_at DESC LIMIT 50",
                (brain, team_id)).fetchall()
        return [{**json.loads(r["report_json"]), "trial_id": r["id"], "baseline_pin_id": r["baseline_pin_id"],
                 "candidate_pin_id": r["candidate_pin_id"], "created_at": r["created_at"]} for r in rows]

    def _pin(self, connection, brain, pin_id):
        row = connection.execute("SELECT manifest_json FROM improvement_team_pins WHERE id=? AND brain_id=?",
                                 (pin_id, brain)).fetchone()
        if row is None:
            raise PermissionError("team_pin_unavailable")
        return json.loads(row["manifest_json"])

    def record(self, principal, baseline_pin_id: str, candidate_pin_id: str, change, arms, *, event_key: str) -> dict:
        """Store the comparison of two arms the owner ran. Nothing else changes: no message, step or acceptance."""
        brain = IM._brain(principal)
        change = validate_change(change)
        if any(type(p) is not str or not _PIN.fullmatch(p) for p in (baseline_pin_id, candidate_pin_id)):
            raise ValueError("invalid_team_pin")
        if baseline_pin_id == candidate_pin_id:
            raise ValueError("team_trial_needs_two_pins")
        if not self._available():
            raise PermissionError("team_trials_unavailable")
        payload = {"baseline": baseline_pin_id, "candidate": candidate_pin_id, "change": change, "arms": arms}
        with self.store._Tx(self.store) as connection:
            replay = self.assets._replay(connection, brain, event_key, "team_trial", payload)
            if replay is not None:
                return replay
            baseline, candidate = self._pin(connection, brain, baseline_pin_id), self._pin(connection, brain, candidate_pin_id)
            if baseline["team_id"] != candidate["team_id"]:
                raise ValueError("team_trial_pins_of_different_teams")
            result = report(compare(baseline, candidate, change), change, arms)
            identifier = "itt_" + secrets.token_hex(16)
            connection.execute("INSERT INTO improvement_team_trials VALUES(?,?,?,?,?,?,?,?,?)",
                               (identifier, brain, baseline_pin_id, candidate_pin_id, IM._json(change), IM._json(result),
                                result["verdict"], principal.by, self.clock()))
            result = {**result, "trial_id": identifier}
            self.assets._event(connection, principal, event_key, "team_trial", payload, result)
            return result


class RecipeTransfers:
    """A recipe proposed elsewhere is an untested candidate there (L02); retrieval filters scope first (L01)."""

    def __init__(self, assets, *, clock: Callable[[], float] = time.time):
        if type(assets) is not IM.ImprovementStore:
            raise TypeError("concrete_transfer_assets_required")
        self.assets, self.store, self.clock = assets, assets.store, clock

    def _available(self) -> bool:
        return IM._schema_version(self.store) >= 16

    def propose(self, principal, recipe_id: str, to, *, event_key: str) -> dict:
        brain = IM._brain(principal)
        to = target(to)
        if type(recipe_id) is not str or not _REF.fullmatch(recipe_id):
            raise ValueError("invalid_recipe")
        if not self._available():
            raise PermissionError("recipe_transfers_unavailable")
        digest = IM._hash(to)
        payload = {"recipe_id": recipe_id, "target": to}
        with self.store._Tx(self.store) as connection:
            replay = self.assets._replay(connection, brain, event_key, "recipe_transfer", payload)
            if replay is not None:
                return replay
            recipe = connection.execute(
                "SELECT r.scope_hash,r.expires_at,s.status FROM improvement_recipes r JOIN improvement_recipe_states s "
                "ON s.recipe_id=r.id AND s.brain_id=r.brain_id WHERE r.id=? AND r.brain_id=?", (recipe_id, brain)).fetchone()
            if recipe is None or recipe["status"] != "active" or recipe["expires_at"] <= self.clock():
                raise PermissionError("recipe_unavailable")
            existing = connection.execute("SELECT id FROM improvement_transfers WHERE brain_id=? AND recipe_id=? "
                                          "AND target_hash=?", (brain, recipe_id, digest)).fetchone()
            identifier = existing["id"] if existing else "irt_" + secrets.token_hex(16)
            if existing is None:
                connection.execute("INSERT INTO improvement_transfers VALUES(?,?,?,?,?,?,?,?)",
                                   (identifier, brain, recipe_id, recipe["scope_hash"], IM._json(to), digest,
                                    principal.by, self.clock()))
            result = {"transfer_id": identifier, "recipe_id": recipe_id, "target": to, "evidence": "untested"}
            self.assets._event(connection, principal, event_key, "recipe_transfer", payload, result)
            return result

    def for_target(self, principal, to, *, limit: int = 3) -> list:
        """Candidates for exactly this target, source recipe still active and unexpired; at most `limit` (15.3)."""
        brain = IM._brain(principal)
        to = target(to)
        if not self._available():
            return []
        with closing(self.store._conn()) as connection:
            rows = connection.execute(
                "SELECT t.id,t.recipe_id,t.created_at FROM improvement_transfers t JOIN improvement_recipes r "
                "ON r.id=t.recipe_id AND r.brain_id=t.brain_id JOIN improvement_recipe_states s ON s.recipe_id=r.id "
                "AND s.brain_id=r.brain_id WHERE t.brain_id=? AND t.target_hash=? AND s.status='active' AND r.expires_at>? "
                "ORDER BY t.created_at DESC LIMIT ?", (brain, IM._hash(to), self.clock(), max(0, min(int(limit), 3)))).fetchall()
        return [{"transfer_id": r["id"], "recipe_id": r["recipe_id"], "target": to, "evidence": "untested"} for r in rows]
