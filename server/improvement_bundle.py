"""M6 agent-skill bundle: one owner-applied pointer over a skill-body overlay and a procedure for one assistant.

The members are the existing M2E skill activation (the assistant's chat) and the M5 procedure overlay. Each
keeps its own checks; the bundle adds what a group needs (spec 14.3, 16.3):

- Validation before anything is written (A04): unique member keys and kinds, dependencies only between members,
  no cycle, members of this brain and assistant, and the procedure only on surfaces the skill overlay reaches
  (the M2E skill overlay serves the assistant's private chat only), so the procedure never refers to steps the
  assistant cannot see.
- All or nothing at read time (S02): while a bundle is applying, every overlay of that assistant stays canonical;
  a bundle member is served only while the bundle is active and every member pointer is still active and on its
  ground. A per-kind revert or a member drift therefore takes the whole bundle down.
- Recovery: an apply interrupted mid-way is rolled back from the members' deterministic event keys and the
  bundle is marked failed; nothing half new is ever served.

Attribution (Q06, Q07) is a pure report over arms the owner ran; it never runs trials itself.
"""
from __future__ import annotations

import json
import re
import secrets
import sqlite3
import sys
import time
from contextlib import closing
from pathlib import Path

import improvement_store as IM

KINDS = ("skill", "procedure")
SKILL_SURFACES = ("dm",)  # where the M2E skill overlay is served
RECOVER_AFTER_S = 120.0
_KEY = re.compile(r"[a-z][a-z0-9_-]{0,31}")


def validate(manifest) -> dict:
    """Closed manifest -> normalized manifest with `order` (dependencies first). Raises ValueError."""
    if type(manifest) is not dict or set(manifest) - {"agent", "members", "depends_on"} or "members" not in manifest:
        raise ValueError("invalid_bundle_manifest")
    members = manifest["members"]
    if type(members) is not list or not 2 <= len(members) <= len(KINDS):
        raise ValueError("bundle_needs_two_members")
    clean, kinds = {}, set()
    for member in members:
        if type(member) is not dict or type(member.get("key")) is not str or not _KEY.fullmatch(member["key"]):
            raise ValueError("invalid_bundle_member")
        kind = member.get("kind")
        allowed = {"key", "kind", "candidate_id"} if kind == "skill" else {"key", "kind", "procedure_id", "surfaces"}
        if kind not in KINDS or set(member) != allowed or member["key"] in clean:
            raise ValueError("invalid_bundle_member")
        if kind in kinds:
            raise ValueError("bundle_member_kind_repeated")
        kinds.add(kind)
        if kind == "skill" and (type(member["candidate_id"]) is not str
                                or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}", member["candidate_id"])):
            raise ValueError("invalid_bundle_member")
        if kind == "procedure":
            if type(member["procedure_id"]) is not str or not re.fullmatch(r"iap_[0-9a-f]{32}", member["procedure_id"]):
                raise ValueError("invalid_bundle_member")
            import improvement_agent
            surfaces = improvement_agent.surfaces(member["surfaces"])
            if set(surfaces) - set(SKILL_SURFACES):
                # The skill half would be missing there: the assistant would follow steps it cannot load.
                raise ValueError("bundle_surface_not_covered")
            member = {**member, "surfaces": surfaces}
        clean[member["key"]] = member
    depends = manifest.get("depends_on", {})
    if type(depends) is not dict or any(type(v) is not list for v in depends.values()):
        raise ValueError("invalid_bundle_dependencies")
    for key, needs in depends.items():
        if key not in clean or any(type(n) is not str or n not in clean or n == key for n in needs) or len(set(needs)) != len(needs):
            raise ValueError("bundle_dependency_unknown")
    order, state = [], {}

    def visit(key):
        if state.get(key) == "done":
            return
        if state.get(key) == "open":
            raise ValueError("bundle_dependency_cycle")
        state[key] = "open"
        for need in sorted(depends.get(key, [])):
            visit(need)
        state[key] = "done"
        order.append(key)
    for key in sorted(clean):
        visit(key)
    return {"members": [clean[k] for k in sorted(clean)], "depends_on": {k: sorted(v) for k, v in sorted(depends.items())},
            "order": order}


def attribution(arms: dict) -> dict:
    """Arms the owner ran -> what may be claimed. Each value: win|tie|loss|unknown against baseline.

    Only baseline vs combined: the bundle as a whole is compared, components are confounded (Q07). A combined
    result never inherits a single arm's pass (Q06): good alone but broken together is `conflict`."""
    if type(arms) is not dict or set(arms) - {"agent_only", "skill_only", "combined"} or "combined" not in arms:
        raise ValueError("invalid_bundle_arms")
    if any(v not in ("win", "tie", "loss", "unknown") for v in arms.values()):
        raise ValueError("invalid_bundle_arms")
    combined = arms["combined"]
    if not {"agent_only", "skill_only"} <= set(arms):
        return {"bundle": combined, "agent": "confounded", "skill": "confounded", "interaction": "not_measured"}
    singles = (arms["agent_only"], arms["skill_only"])
    if "unknown" in singles or combined == "unknown":
        interaction = "unknown"
    elif combined == "win" and "win" not in singles:
        interaction = "synergy"
    elif combined != "win" and "win" in singles:
        interaction = "conflict"
    else:
        interaction = "consistent"
    return {"bundle": combined, "agent": arms["agent_only"], "skill": arms["skill_only"], "interaction": interaction}


def _public(row, members) -> dict:
    keys = ("agent_key", "agent_slug", "manifest_hash", "state", "reason", "generation", "created_at", "updated_at")
    # No bundle has its own qualification yet (real combined/ablation arms need engine runs): a manual trial.
    return {**{k: row[k] for k in keys}, "bundle_id": row["id"], "manifest": json.loads(row["manifest_json"]),
            "evidence_level": "manual_trial", "attribution": "not_measured",
            "members": [{"member_key": m["member_key"], "kind": m["kind"], "pointer_id": m["pointer_id"]} for m in members]}


class Bundles:
    """Owner commands over bundle pointers; members go through their own services."""

    def __init__(self, assets, *, activations, procedures, clock=time.time):
        if type(assets) is not IM.ImprovementStore:
            raise TypeError("concrete_bundle_assets_required")
        self.assets, self.store, self.clock = assets, assets.store, clock
        self.activations, self.procedures = activations, procedures

    def _available(self) -> bool:
        return IM._schema_version(self.store) >= 15

    def _row(self, connection, brain, bundle_id):
        row = connection.execute("SELECT * FROM improvement_bundle_activations WHERE id=? AND brain_id=?",
                                 (bundle_id, brain)).fetchone()
        if row is None:
            raise PermissionError("bundle_unavailable")
        members = connection.execute("SELECT * FROM improvement_bundle_members WHERE bundle_id=? AND brain_id=? "
                                     "ORDER BY member_key", (bundle_id, brain)).fetchall()
        return row, members

    def member_of(self, principal, kind: str, pointer_id: str) -> str:
        """The applying or active bundle a member pointer belongs to, or "". Members of a finished bundle can be
        reverted on their own, so nothing stays stuck if a bundle revert stopped half way."""
        brain = IM._brain(principal)
        if not self._available():
            return ""
        with closing(self.store._conn()) as connection:
            row = connection.execute("SELECT m.bundle_id FROM improvement_bundle_members m JOIN improvement_bundle_activations b "
                                     "ON b.id=m.bundle_id AND b.brain_id=m.brain_id WHERE m.brain_id=? AND m.kind=? AND "
                                     "m.pointer_id=? AND b.state IN ('applying','active')", (brain, kind, pointer_id)).fetchone()
        return row["bundle_id"] if row else ""

    def list(self, principal, *, agent_key: str | None = None) -> list:
        brain = IM._brain(principal)
        if not self._available():
            return []
        query, args = "SELECT id FROM improvement_bundle_activations WHERE brain_id=?", [brain]
        if agent_key is not None:
            query, args = query + " AND agent_key=?", args + [agent_key]
        with closing(self.store._conn()) as connection:
            ids = [r["id"] for r in connection.execute(query + " ORDER BY created_at DESC LIMIT 50", args)]
            return [_public(*self._row(connection, brain, i)) for i in ids]

    def apply(self, principal, agent_slug: str, manifest, *, owner_confirmed: bool, event_key: str) -> dict:
        brain = IM._brain(principal)
        clean = validate(manifest)
        if type(manifest) is dict and "agent" in manifest and manifest["agent"] != agent_slug:
            raise ValueError("bundle_agent_mismatch")
        if owner_confirmed is not True:
            raise PermissionError("bundle_owner_confirmation_required")
        if not self._available():
            raise PermissionError("bundle_unavailable")
        key = self.procedures.key(principal, agent_slug)
        if not key:
            raise PermissionError("agent_unavailable")
        payload = {"agent": agent_slug, "manifest": clean}
        digest = IM._hash(payload)
        with self.store._Tx(self.store) as connection:
            replay = self.assets._replay(connection, brain, event_key, "bundle_apply", payload)
            if replay is not None:
                return replay
            if self.assets._policy(connection, brain)["mode"] == "off":
                raise PermissionError("improvement_disabled")
            for member in clean["members"]:
                if member["kind"] == "procedure":
                    owner = connection.execute("SELECT agent_key FROM improvement_agent_procedures WHERE id=? AND brain_id=?",
                                               (member["procedure_id"], brain)).fetchone()
                    if owner is None or owner["agent_key"] != key:
                        raise PermissionError("bundle_member_unavailable")
            if connection.execute("SELECT 1 FROM improvement_bundle_activations WHERE brain_id=? AND agent_key=? "
                                  "AND state IN ('applying','active')", (brain, key)).fetchone():
                raise IM.ConflictError("bundle_busy")
            identifier, now = "iba_" + secrets.token_hex(16), self.clock()
            connection.execute("INSERT INTO improvement_bundle_activations VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                               (identifier, brain, key, agent_slug, IM._json(clean), digest, "applying", "owner_apply",
                                1, principal.by, now, now))
        generation = 1
        # Each member through its own service, dependencies first. The assistant stays canonical meanwhile. Before
        # each member the bundle proves it still owns the apply (CAS heartbeat); a reconcile that took over wins.
        try:
            for member_key in clean["order"]:
                generation = self._heartbeat(identifier, generation)
                self._apply_member(principal, identifier, agent_slug, clean, member_key)
            with self.store._Tx(self.store) as connection:
                if not connection.execute("UPDATE improvement_bundle_activations SET state='active',generation=generation+1,"
                                          "updated_at=? WHERE id=? AND state='applying' AND generation=?",
                                          (self.clock(), identifier, generation)).rowcount:
                    raise IM.ConflictError("bundle_apply_interrupted")
                result = _public(*self._row(connection, brain, identifier))
                self.assets._event(connection, principal, event_key, "bundle_apply", payload, result)
                return result
        except Exception:
            self._fail(principal, identifier, "member_apply_failed", expected_generation=generation)
            self._revert_all(principal, identifier, "rollback")
            raise

    def _heartbeat(self, bundle_id, generation) -> int:
        with self.store._Tx(self.store) as connection:
            if not connection.execute("UPDATE improvement_bundle_activations SET generation=generation+1,updated_at=? "
                                      "WHERE id=? AND state='applying' AND generation=?",
                                      (self.clock(), bundle_id, generation)).rowcount:
                raise IM.ConflictError("bundle_apply_interrupted")
        return generation + 1

    @staticmethod
    def _member_key(bundle_id, member_key) -> str:
        return f"bundle-{bundle_id}-{member_key}"

    def _apply_member(self, principal, bundle_id, agent_slug, clean, member_key):
        member = next(m for m in clean["members"] if m["key"] == member_key)
        event = self._member_key(bundle_id, member_key)
        if member["kind"] == "skill":
            pointer = self.activations.apply(principal, member["candidate_id"], agent_slug, event_key=event)["activation_id"]
        else:
            pointer = self.procedures.apply(principal, member["procedure_id"], member["surfaces"], owner_confirmed=True,
                                            event_key=event)["overlay_id"]
        with self.store._Tx(self.store) as connection:
            connection.execute("INSERT OR IGNORE INTO improvement_bundle_members VALUES(?,?,?,?,?)",
                               (bundle_id, IM._brain(principal), member_key, member["kind"], pointer))

    def _pointer_from_event(self, connection, brain, bundle_id, member) -> str:
        row = connection.execute("SELECT result_json FROM improvement_events WHERE brain_id=? AND event_key=?",
                                 (brain, self._member_key(bundle_id, member["key"]))).fetchone()
        if row is None:
            return ""
        result = json.loads(row["result_json"])
        return str(result.get("activation_id") or result.get("overlay_id") or "")

    def _revert_member(self, principal, bundle_id, kind, pointer, reason) -> bool:
        """True when the pointer is no longer active afterwards."""
        table = "improvement_activations" if kind == "skill" else "improvement_agent_overlays"
        with closing(self.store._conn()) as connection:
            row = connection.execute(f"SELECT state,generation FROM {table} WHERE id=? AND brain_id=?",
                                     (pointer, IM._brain(principal))).fetchone()
        if row is None or row["state"] != "active":
            return True
        service = self.activations if kind == "skill" else self.procedures
        try:
            service.revert(principal, pointer, expected_generation=row["generation"],
                           event_key=f"bundle-{bundle_id}-{reason}-{pointer}-{row['generation']}")
            return True
        except (IM.ConflictError, PermissionError, ValueError, sqlite3.Error) as error:
            # Left active: the sweep in reconcile retries, and the per-kind revert is open again (bundle finished).
            print(f"[improvement bundle] member {pointer}: {error}", file=sys.stderr)
            return False

    def _members(self, connection, brain, bundle_id, clean) -> list:
        """(kind, pointer) of every member that may exist, recorded or only applied (crash before recording)."""
        recorded = {m["member_key"]: (m["kind"], m["pointer_id"]) for m in connection.execute(
            "SELECT * FROM improvement_bundle_members WHERE bundle_id=? AND brain_id=?", (bundle_id, brain))}
        out = []
        for member in clean["members"]:
            pointer = recorded.get(member["key"], (None, ""))[1] or self._pointer_from_event(connection, brain, bundle_id, member)
            if pointer:
                out.append((member["kind"], pointer))
        return out

    def _fail(self, principal, bundle_id, reason, *, expected_generation=None, older_than=None) -> bool:
        """CAS applying -> failed; only the winner reverts members, so a live apply and a reconcile never both act."""
        query = "UPDATE improvement_bundle_activations SET state='failed',reason=?,generation=generation+1,updated_at=? " \
                "WHERE id=? AND state='applying'"
        args = [reason, self.clock(), bundle_id]
        if expected_generation is not None:
            query, args = query + " AND generation=?", args + [expected_generation]
        if older_than is not None:
            query, args = query + " AND updated_at<=?", args + [older_than]
        with self.store._Tx(self.store) as connection:
            return bool(connection.execute(query, args).rowcount)

    def _revert_all(self, principal, bundle_id, reason) -> bool:
        brain = IM._brain(principal)
        with closing(self.store._conn()) as connection:
            row = connection.execute("SELECT manifest_json FROM improvement_bundle_activations WHERE id=? AND brain_id=?",
                                     (bundle_id, brain)).fetchone()
            members = self._members(connection, brain, bundle_id, json.loads(row["manifest_json"])) if row else []
        return all([self._revert_member(principal, bundle_id, kind, pointer, reason) for kind, pointer in members])

    def revert(self, principal, bundle_id: str, *, expected_generation: int, event_key: str) -> dict:
        """The bundle leaves service first (one transaction), then each member pointer is moved back."""
        brain = IM._brain(principal)
        if type(bundle_id) is not str or not re.fullmatch(r"iba_[0-9a-f]{32}", bundle_id):
            raise ValueError("invalid_bundle")
        if type(expected_generation) is not int or expected_generation < 1:
            raise ValueError("invalid_bundle")
        if not self._available():
            raise PermissionError("bundle_unavailable")
        payload = {"bundle_id": bundle_id, "expected_generation": expected_generation}
        with self.store._Tx(self.store) as connection:
            replay = self.assets._replay(connection, brain, event_key, "bundle_revert", payload)
            if replay is not None:
                return replay
            row, _members = self._row(connection, brain, bundle_id)
            if row["generation"] != expected_generation:
                raise IM.ConflictError("stale_bundle")
            if row["state"] != "active":
                raise IM.ConflictError("bundle_not_active")
            connection.execute("UPDATE improvement_bundle_activations SET state='reverted',reason='owner_revert',"
                               "generation=generation+1,updated_at=? WHERE id=?", (self.clock(), bundle_id))
            result = _public(*self._row(connection, brain, bundle_id))
            self.assets._event(connection, principal, event_key, "bundle_revert", payload, result)
        self._revert_all(principal, bundle_id, "revert")
        return result

    def reconcile(self, principal) -> list:
        """Suspend an active bundle whose member left service (incl. drift), roll back an apply that stopped half
        way, and sweep active member pointers left behind by a finished bundle."""
        brain = IM._brain(principal)
        if not self._available():
            return []
        # Members' own drift first (skill bytes, edit authority, owner rules), so a drifted member is recorded.
        for service in (self.activations, self.procedures):
            try:
                service.reconcile(principal)
            except Exception as error:  # noqa: BLE001 - the bundle check below still reads the real files
                print(f"[improvement bundle] member reconcile: {type(error).__name__}: {error}", file=sys.stderr)
        out, now = [], self.clock()
        with closing(self.store._conn()) as connection:
            rows = connection.execute("SELECT * FROM improvement_bundle_activations WHERE brain_id=?", (brain,)).fetchall()
        for row in rows:
            if row["state"] == "applying":
                if now - row["updated_at"] >= RECOVER_AFTER_S and self._fail(
                        principal, row["id"], "interrupted", expected_generation=row["generation"],
                        older_than=now - RECOVER_AFTER_S):
                    self._revert_all(principal, row["id"], "rollback")
                    out.append({"bundle_id": row["id"], "reason": "interrupted"})
                continue
            if row["state"] == "active":
                with closing(self.store._conn()) as connection:
                    if _members_active(connection, brain, row["id"], Path(brain)):
                        continue
                with self.store._Tx(self.store) as connection:
                    if not connection.execute("UPDATE improvement_bundle_activations SET state='suspended',"
                                              "reason='member_unavailable',generation=generation+1,updated_at=? "
                                              "WHERE id=? AND state='active' AND generation=?",
                                              (now, row["id"], row["generation"])).rowcount:
                        continue
                out.append({"bundle_id": row["id"], "reason": "member_unavailable"})
            self._revert_all(principal, row["id"], "suspend" if row["state"] == "active" else "sweep")
        return out


def _members_active(connection, brain, bundle_id, root=None) -> bool:
    """Every member pointer is active and, with `root`, still servable on the same grounds as its own resolver."""
    members = connection.execute("SELECT kind,pointer_id FROM improvement_bundle_members WHERE bundle_id=? AND brain_id=?",
                                 (bundle_id, brain)).fetchall()
    if not members:
        return False
    for member in members:
        if member["kind"] == "skill":
            row = connection.execute(
                "SELECT a.state,a.canonical_ref,a.base_hash,a.frontmatter_hash,t.identity,t.status FROM improvement_activations a "
                "JOIN improvement_targets t ON t.id=a.target_id AND t.brain_id=a.brain_id WHERE a.id=? AND a.brain_id=? "
                "AND EXISTS(SELECT 1 FROM improvement_candidate_authorities c JOIN improvement_candidate_authority_grants g "
                "ON g.authority_id=c.id AND g.brain_id=c.brain_id WHERE c.brain_id=a.brain_id "
                "AND c.candidate_id=a.candidate_id AND c.kind='exact_diff' AND g.status='active')",
                (member["pointer_id"], brain)).fetchone()
            if row is None or row["state"] != "active" or row["status"] != "live":
                return False
            if root is not None:
                import skill_router as SR
                from improvement_activation import _file_identity
                canonical = SR.read_skill_asset(Path(root), row["canonical_ref"].split("/")[1])
                if (canonical is None or canonical.content_hash != row["base_hash"]
                        or canonical.frontmatter_hash != row["frontmatter_hash"]
                        or _file_identity(root, row["canonical_ref"]) != row["identity"]):
                    return False
        else:
            row = connection.execute("SELECT state FROM improvement_agent_overlays WHERE id=? AND brain_id=?",
                                     (member["pointer_id"], brain)).fetchone()
            if row is None or row["state"] != "active":
                return False
    return True


def membership(connection, brain: str, kind: str, pointer_id: str):
    """The bundle row a pointer belongs to, or None (read-only connection)."""
    if not connection.execute("SELECT 1 FROM sqlite_master WHERE name='improvement_bundle_activations'").fetchone():
        return None
    return connection.execute("SELECT b.id,b.state FROM improvement_bundle_members m JOIN improvement_bundle_activations b "
                              "ON b.id=m.bundle_id AND b.brain_id=m.brain_id WHERE m.brain_id=? AND m.kind=? "
                              "AND m.pointer_id=?", (brain, kind, pointer_id)).fetchone()


def allows(connection, root, brain: str, agent_key: str, kind: str, pointer_id: str, *, skill_served: bool = True) -> bool:
    """Read-time gate shared by the skill and procedure resolvers (read-only connection).

    `skill_served`: for a procedure member, whether this turn can read the bundle's skill overlay at all (the
    assistant's dashboard chat on an in-process API engine). Elsewhere a bundled procedure would arrive without
    its skill, so it stays canonical too."""
    try:
        if not connection.execute("SELECT 1 FROM sqlite_master WHERE name='improvement_bundle_activations'").fetchone():
            return True
        if connection.execute("SELECT 1 FROM improvement_bundle_activations WHERE brain_id=? AND agent_key=? "
                              "AND state='applying'", (brain, agent_key)).fetchone():
            return False  # a bundle is being applied or rolled back: nothing half new
        member = membership(connection, brain, kind, pointer_id)
        if member is None:
            return True
        if kind == "procedure" and not skill_served:
            return False
        return member["state"] == "active" and _members_active(connection, brain, member["id"], root)
    except (OSError, ValueError, sqlite3.Error) as error:
        print(f"[improvement bundle] {type(error).__name__}: {error}", file=sys.stderr)
        return False
