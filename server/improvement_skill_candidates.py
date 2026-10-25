"""Explicit owner skill authoring outside canonical files and executable bundles.

Every new write observes the actual source and its native permissions before and
after slow encrypted publication. Historical event replay grants nothing anew.
"""
from __future__ import annotations

import json
import secrets
import time
from contextlib import closing
from dataclasses import asdict
from pathlib import Path

import improvement_assets as IA
import improvement_cases as IC
import improvement_store as IM
from evidence_store import redact
from improvement_blobs import AssetUnavailable
from improvement_candidate_records import CandidateRecords, identifier
from improvement_skill_patch import body_layout, validate_body_patch, _boundary
from improvement_trial_file_sources import _root, _authority
from improvement_trial_records import HostContextRecords, _brain


def _generation(value):
    if type(value) is not int or not 1 <= value < 2 ** 63:
        raise ValueError("invalid_candidate_generation")


class SkillCandidates:
    def __init__(self, assets, *, pack_state_dir):
        self.records = CandidateRecords(assets)
        self.assets, self.store, self.blobs = assets, assets.store, assets.blobs
        self.pack_state_dir = Path(pack_state_dir).absolute()

    @staticmethod
    def _edit_open(connection, brain, experiment_id):
        # Released schema4 authoring still works; B adds an irreversible write fence.
        if connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='improvement_experiments'").fetchone():
            row = connection.execute("SELECT e.phase,EXISTS(SELECT 1 FROM improvement_experiment_selections s "
                "WHERE s.experiment_id=e.id AND s.brain_id=e.brain_id) AS sealed FROM improvement_experiments e "
                "WHERE e.id=? AND e.brain_id=?", (experiment_id, brain)).fetchone()
            if row is not None and (row["sealed"] or row["phase"] in
                    ("stopping", "completed", "rejected", "inconclusive", "cancelled", "stale")):
                raise IM.ConflictError("experiment_sealed")

    def _state(self, connection, principal, experiment_id, target_id, base_revision_id, before_hash=None, *, _private_read=False):
        brain = _brain(principal)
        context = HostContextRecords._row(connection, brain, experiment_id)
        grant = HostContextRecords._grant(connection, context)
        policy = self.assets._policy(connection, brain)
        if not _private_read and policy["mode"] == "off":
            raise PermissionError("improvement_disabled")
        if grant["status"] != "active":
            raise PermissionError("trial_source_grant_revoked")
        if not _private_read and policy["version"] != context["policy_version"]:
            raise IM.ConflictError("candidate_context_changed")
        target = self.assets._target(connection, brain, target_id)
        generations = json.loads(context["target_generations_json"])
        revision = connection.execute("SELECT * FROM improvement_revisions WHERE id=? AND brain_id=?",
                                      (base_revision_id, brain)).fetchone()
        if (target["kind"] != "skill" or target["status"] != "live" or target["ownership"] not in ("user_protected", "user_managed")
                or generations.get(target_id) != target["generation"] or target["current_revision_id"] != base_revision_id
                or revision is None or revision["target_id"] != target_id or revision["content_hash"] != target["source_hash"]
                or (before_hash is not None and target["source_hash"] != before_hash)):
            raise IM.ConflictError("candidate_base_changed")
        manifest = json.loads(revision["manifest_json"])
        if IM._hash(manifest) != revision["manifest_hash"]:
            raise AssetUnavailable("candidate_baseline_unavailable")
        expected = {key: target[key] for key in ("kind", "canonical_ref", "source_hash", "protected_hash", "ownership", "identity")}
        expected.update(enabled=True, agent_key="")
        if manifest != expected:
            raise IM.ConflictError("candidate_base_changed")
        return {"context": dict(context), "grant": dict(grant), "policy": policy, "target": dict(target)}

    def observe(self, principal, target):
        """Host-private exact source observation; caller first resolves its DB scope."""
        root = _root(principal)
        ref = target["canonical_ref"]
        if (type(ref) is not str or not IM._SOURCE.fullmatch(ref) or not ref.startswith("skills/")
                or target["brain_id"] != _brain(principal)):
            raise PermissionError("candidate_source_unavailable")
        before = _authority(root, ref)
        source, raw = IA.capture_source(root, "skill", ref.split("/")[1], pack_state_dir=self.pack_state_dir)
        expected = {key: target[key] for key in ("kind", "canonical_ref", "source_hash", "protected_hash", "ownership", "identity")}
        expected.update(enabled=True, agent_key="")
        if asdict(source) != expected:
            raise IM.ConflictError("candidate_source_changed")
        if self.blobs.read(_brain(principal), target["source_hash"]) != raw:
            raise AssetUnavailable("candidate_baseline_unavailable")
        if _root(principal) != root or _authority(root, ref) != before:
            raise IM.ConflictError("candidate_source_authority_changed")
        observed = {"source": asdict(source), "source_authority_hash": IM._hash({"source": asdict(source), "authority": before})}
        return observed, raw

    def _guard(self, connection, principal, state, observed):
        target, context = state["target"], state["context"]
        current = self._state(connection, principal, context["experiment_id"], target["id"], target["current_revision_id"], target["source_hash"])
        if current != state or self.observe(principal, current["target"])[0] != observed:
            raise IM.ConflictError("candidate_authority_changed")

    def read_proposal(self, connection, principal, candidate, state, observed, base_raw):
        """Verify immutable authoring evidence before private review or a new edit grant."""
        from cryptography.fernet import InvalidToken

        brain = _brain(principal)
        try:
            provenance = json.loads(self.blobs.read(brain, candidate["provenance_hash"]))
            patch = json.loads(self.blobs.read(brain, candidate["patch_hash"]))
            after = self.blobs.read(brain, candidate["content_hash"])
            composed = candidate['ordinal'] == 3
            fields = {"version", "context_id", "experiment_id", "target_id", "base_revision_id", "before_hash",
                "after_hash", "patch_hash", "ordinal", "source_authority_hash", "context_generation", "authority_id",
                "authority_generation", "owner_request_event", "evidence_refs", "semantic_status", "reference_inventory", "dependency_status"}
            IC._fields(provenance, fields | ({'composition_id'} if composed else set()))
            expected = {"context_id": candidate["context_id"], "experiment_id": candidate["experiment_id"],
                "target_id": candidate["target_id"], "base_revision_id": candidate["base_revision_id"],
                "before_hash": candidate["base_hash"], "after_hash": candidate["content_hash"], "patch_hash": candidate["patch_hash"],
                "ordinal": candidate["ordinal"], "authority_id": candidate["authority_id"], "authority_generation": candidate["authority_generation"],
                "semantic_status": "unreviewed", "dependency_status": "unresolved",
                "owner_request_event": None if composed else "candidate-owner-" + IM._hash([brain, candidate["owner_event_key"]])}
            if (type(provenance["version"]) is not int or provenance["version"] != (2 if composed else 1)
                    or any(provenance[key] != value for key, value in expected.items())
                    or len(after) != candidate["byte_size"] or provenance["evidence_refs"] != patch["evidence_refs"]):
                raise AssetUnavailable("candidate_provenance_mismatch")
            if (provenance["source_authority_hash"] != observed["source_authority_hash"]
                    or provenance["context_generation"] != state["grant"]["generation"]):
                raise IM.ConflictError("candidate_source_authority_changed")
            region = None
            if candidate["authority_id"] is not None:
                authority = self.records._authority(connection, brain, candidate["authority_id"])
                if (authority["source_authority_hash"] != provenance["source_authority_hash"]
                        or authority["context_id"] != candidate["context_id"] or authority["target_id"] != candidate["target_id"]
                        or authority["kind"] != "editable_region" or authority["base_revision_id"] != candidate["base_revision_id"]):
                    raise AssetUnavailable("candidate_provenance_mismatch")
                region = {"start": authority["start"], "end": authority["end"], "before_hash": authority["before_hash"]}
            validated = validate_body_patch(base_raw, patch, region)
            if (validated["content"] != after or validated["content_hash"] != candidate["content_hash"]
                    or validated["patch_hash"] != candidate["patch_hash"] or validated["reference_inventory"] != provenance["reference_inventory"]
                    or patch["target_id"] != candidate["target_id"] or patch["base_revision_id"] != candidate["base_revision_id"]):
                raise AssetUnavailable("candidate_provenance_mismatch")
            if composed:
                from improvement_compose_candidates import read_provenance
                read_provenance(self, connection, principal, candidate, provenance, patch, after)
            else:
                owner = connection.execute("SELECT result_json FROM improvement_events WHERE brain_id=? AND event_key=? "
                    "AND operation='skill_candidate_owner_request'", (brain, provenance["owner_request_event"])).fetchone()
                if owner is None:
                    raise AssetUnavailable("candidate_provenance_mismatch")
                owner = json.loads(owner[0])
                if any(owner.get(key) != value for key, value in {"context_id": candidate["context_id"],
                    "experiment_id": candidate["experiment_id"], "target_id": candidate["target_id"],
                    "patch_hash": candidate["patch_hash"], "candidate_id": candidate["id"]}.items()):
                    raise AssetUnavailable("candidate_provenance_mismatch")
            return {"before": base_raw, "after": after, "patch": patch, "provenance": provenance}
        except (IM.ConflictError, PermissionError):
            raise
        except (InvalidToken, ValueError, TypeError, KeyError, UnicodeError, RecursionError) as error:
            raise AssetUnavailable("candidate_provenance_unavailable") from error

    @staticmethod
    def _evidence(connection, brain, context, refs):
        resolved = []
        for ref in refs:
            if ref["kind"] == "owner_request":
                row = connection.execute("SELECT result_json FROM improvement_events WHERE brain_id=? AND event_key=? "
                    "AND operation='skill_candidate_owner_request'", (brain, ref["id"])).fetchone()
                if row is None or json.loads(row[0]).get("context_id") != context["id"]:
                    raise PermissionError("candidate_evidence_unavailable")
                resolved.append(dict(ref))
                continue
            row = connection.execute("SELECT * FROM improvement_trials WHERE brain_id=? AND id=?", (brain, ref["id"])).fetchone()
            if row is None or row["status"] != "completed":
                raise PermissionError("candidate_evidence_unavailable")
            request = json.loads(row["request_json"])
            pins = request["pins"]
            if (IM._hash(request) != row["request_hash"] or not row["attempt"]
                    or pins["experiment_id"] != context["experiment_id"]
                    or any(pins[key] != context[key] for key in ("scope_hash", "grant_hash", "engine_config_hash", "policy_version"))):
                raise PermissionError("candidate_evidence_unavailable")
            case = connection.execute("SELECT split FROM improvement_cases WHERE brain_id=? AND case_set_id=? AND id=?",
                                      (brain, request["case_set_id"], request["case_id"])).fetchone()
            if case is None or case["split"] != "tuning":
                raise PermissionError("candidate_evidence_unavailable")
            from improvement_trial_associations import _association
            association = _association(connection, brain, request["case_set_id"])
            if (association is None or association["context_id"] != context["id"]
                    or association["grant_hash"] != context["grant_hash"] or association["manifest_hash"] != pins["case_set_hash"]):
                raise PermissionError("candidate_evidence_unavailable")
            result = connection.execute("SELECT result_json FROM improvement_trial_attempts WHERE trial_id=? AND brain_id=? AND attempt=?",
                                       (row["id"], brain, row["attempt"])).fetchone()
            if result is None or not result[0]:
                raise PermissionError("candidate_evidence_unavailable")
            resolved.append(dict(ref))
        return resolved

    def _insert_authority(self, connection, principal, state, observed, *, kind, start=None, end=None, candidate=None):
        target, context = state["target"], state["context"]
        authority_id = "ica_" + secrets.token_hex(12)
        connection.execute("INSERT INTO improvement_candidate_authorities "
            "(id,brain_id,context_id,target_id,base_revision_id,base_hash,base_generation,context_generation,kind,start,end,"
            "before_hash,after_hash,candidate_id,source_authority_hash,actor,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (
                authority_id, _brain(principal), context["id"], target["id"], target["current_revision_id"], target["source_hash"],
                target["generation"], state["grant"]["generation"], kind, start, end, target["source_hash"],
                candidate["content_hash"] if candidate is not None else None,
                candidate["id"] if candidate is not None else None, observed["source_authority_hash"], principal.by, time.time()))
        connection.execute("INSERT INTO improvement_candidate_authority_grants VALUES(?,?,1,'active',NULL)",
                           (authority_id, _brain(principal)))
        return self.records._authority_public(self.records._authority(connection, _brain(principal), authority_id))

    def declare_region(self, principal, experiment_id, base_revision_id, start, end, *, expected_target_generation, event_key):
        brain = _brain(principal)
        identifier(experiment_id)
        identifier(base_revision_id)
        _generation(expected_target_generation)
        if type(start) is not int or type(end) is not int or not 0 <= start <= end <= 1048576:
            raise ValueError("invalid_candidate_region")
        if IM._schema_version(self.store) < 3:
            raise PermissionError("trial_context_unavailable")
        payload = {"experiment_id": experiment_id, "base_revision_id": base_revision_id, "start": start, "end": end,
                   "expected_target_generation": expected_target_generation}
        with closing(self.store._conn()) as connection:
            connection.execute("BEGIN")
            replay = self.assets._replay(connection, brain, event_key, "candidate_region_declare", payload)
            if replay is not None:
                return replay
            self._edit_open(connection, brain, experiment_id)
            revision = IC.CaseStore._row(connection, "improvement_revisions", brain, base_revision_id)
            state = self._state(connection, principal, experiment_id, revision["target_id"], base_revision_id)
        if state["target"]["generation"] != expected_target_generation:
            raise IM.ConflictError("candidate_base_changed")
        observed, raw = self.observe(principal, state["target"])
        layout = body_layout(raw)
        _boundary(raw, start)
        _boundary(raw, end)
        if start < layout["editable_start"]:
            raise ValueError("candidate_protected_region")
        IM.ensure(self.store)
        with self.store._Tx(self.store) as connection:
            replay = self.assets._replay(connection, brain, event_key, "candidate_region_declare", payload)
            if replay is not None:
                return replay
            self._edit_open(connection, brain, experiment_id)
            self._guard(connection, principal, state, observed)
            result = self._insert_authority(connection, principal, state, observed, kind="editable_region", start=start, end=end)
            self.assets._event(connection, principal, event_key, "candidate_region_declare", payload, result)
            return result

    def _region(self, connection, brain, state, observed, patch):
        rows = connection.execute("SELECT a.* FROM improvement_candidate_authorities a JOIN improvement_candidate_authority_grants g "
            "ON g.authority_id=a.id AND g.brain_id=a.brain_id WHERE a.brain_id=? AND a.context_id=? AND a.target_id=? "
            "AND a.base_revision_id=? AND a.kind='editable_region' AND g.status='active' AND g.generation=1 "
            "AND a.start<=? AND a.end>=? ORDER BY a.created_at DESC,a.id DESC", (
                brain, state["context"]["id"], state["target"]["id"], patch["base_revision_id"], patch["start"], patch["end"])).fetchall()
        for row in rows:
            if (row["source_authority_hash"] == observed["source_authority_hash"]
                    and row["context_generation"] == state["grant"]["generation"]):
                return row
        if rows:
            raise IM.ConflictError("candidate_edit_authority_changed")
        return None

    def stage(self, principal, experiment_id, patch, *, event_key):
        brain = _brain(principal)
        identifier(experiment_id)
        patch = IC._frozen(patch)
        if type(patch) is not dict:
            raise ValueError("invalid_candidate_patch")
        for field in ("target_id", "base_revision_id"):
            identifier(patch.get(field))
        if IM._schema_version(self.store) < 3:
            raise PermissionError("trial_context_unavailable")
        payload = {"experiment_id": experiment_id, "patch_hash": IM._hash(patch)}
        with closing(self.store._conn()) as connection:
            connection.execute("BEGIN")
            replay = self.assets._replay(connection, brain, event_key, "skill_candidate_stage", payload)
            if replay is not None:
                return replay
            self._edit_open(connection, brain, experiment_id)
            state = self._state(connection, principal, experiment_id, patch["target_id"], patch["base_revision_id"], patch.get("before_hash"))
        observed, raw = self.observe(principal, state["target"])
        validated = validate_body_patch(raw, patch, None)
        if redact(patch) != patch or redact(validated["content"].decode("utf-8")) != validated["content"].decode("utf-8"):
            raise ValueError("candidate_sensitive_content")
        IM.ensure(self.store)
        with self.store._Tx(self.store) as connection:
            return self._stage_in(connection, principal, experiment_id, patch, event_key=event_key,
                                  state=state, observed=observed, raw=raw)

    def _stage_in(self, connection, principal, experiment_id, patch, *, event_key, state, observed, raw):
        """Actual owner staging inside the caller's writer, including batch rollback."""
        IC.CaseStore(self.assets)._own_transaction(connection)
        brain = _brain(principal)
        if (state['context']['experiment_id'] != experiment_id or state['target']['id'] != patch['target_id']
                or state['target']['current_revision_id'] != patch['base_revision_id']
                or state['target']['source_hash'] != patch['before_hash']):
            raise IM.ConflictError('candidate_stage_scope_changed')
        payload = {"experiment_id": experiment_id, "patch_hash": IM._hash(patch)}
        validated = validate_body_patch(raw, patch, None)
        if redact(patch) != patch or redact(validated["content"].decode("utf-8")) != validated["content"].decode("utf-8"):
            raise ValueError("candidate_sensitive_content")
        replay = self.assets._replay(connection, brain, event_key, "skill_candidate_stage", payload)
        if replay is not None:
            return replay
        self._edit_open(connection, brain, experiment_id)
        self._guard(connection, principal, state, observed)
        candidates = connection.execute("SELECT target_id,base_revision_id,ordinal FROM improvement_skill_candidates "
            "WHERE brain_id=? AND experiment_id=? ORDER BY ordinal", (brain, experiment_id)).fetchall()
        if len(candidates) >= 2:
            raise IM.ConflictError("candidate_slots_full")
        if any(row["target_id"] != patch["target_id"] or row["base_revision_id"] != patch["base_revision_id"] for row in candidates):
            raise IM.ConflictError("candidate_primary_component_changed")
        ordinal = len(candidates) + 1
        region = self._region(connection, brain, state, observed, patch)
        if region is not None:
            validated = validate_body_patch(raw, patch, {"start": region["start"], "end": region["end"], "before_hash": region["before_hash"]})
        evidence = self._evidence(connection, brain, state["context"], patch["evidence_refs"])
        owner_key = "candidate-owner-" + IM._hash([brain, event_key])
        provenance = {"version": 1, "context_id": state["context"]["id"], "experiment_id": experiment_id,
            "target_id": patch["target_id"], "base_revision_id": patch["base_revision_id"], "before_hash": patch["before_hash"],
            "after_hash": validated["content_hash"], "patch_hash": validated["patch_hash"], "ordinal": ordinal,
            "source_authority_hash": observed["source_authority_hash"], "context_generation": state["grant"]["generation"],
            "authority_id": region["id"] if region is not None else None,
            "authority_generation": 1 if region is not None else None,
            "owner_request_event": owner_key, "evidence_refs": evidence,
            "semantic_status": "unreviewed", "reference_inventory": validated["reference_inventory"], "dependency_status": "unresolved"}
        content_hash = self.blobs.write(brain, validated["content"])
        patch_hash = self.blobs.write(brain, IM._json(patch).encode("utf-8"))
        provenance_hash = self.blobs.write(brain, IM._json(provenance).encode("utf-8"))
        if content_hash != validated["content_hash"] or patch_hash != validated["patch_hash"]:
            raise AssetUnavailable("candidate_publication_mismatch")
        self._guard(connection, principal, state, observed)
        self._evidence(connection, brain, state["context"], patch["evidence_refs"])
        if region is not None:
            current_region = self._region(connection, brain, state, observed, patch)
            if current_region is None or dict(current_region) != dict(region):
                raise IM.ConflictError("candidate_edit_authority_changed")
        candidate_id = "isc_" + secrets.token_hex(12)
        connection.execute("INSERT INTO improvement_skill_candidates "
            "(id,brain_id,context_id,experiment_id,target_id,base_revision_id,base_hash,base_generation,ordinal,content_hash,"
            "byte_size,patch_hash,provenance_hash,authority_id,authority_generation,semantic_status,owner_event_key,created_at) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (
                candidate_id, brain, state["context"]["id"], experiment_id, patch["target_id"], patch["base_revision_id"],
                patch["before_hash"], state["target"]["generation"], ordinal, content_hash, validated["byte_size"], patch_hash,
                provenance_hash, region["id"] if region is not None else None, 1 if region is not None else None,
                "unreviewed", event_key, time.time()))
        owner_result = {"context_id": state["context"]["id"], "experiment_id": experiment_id,
                        "target_id": patch["target_id"], "patch_hash": patch_hash, "candidate_id": candidate_id}
        self.assets._event(connection, principal, owner_key, "skill_candidate_owner_request", payload, owner_result)
        result = self.records._public(connection, self.records._row(connection, brain, candidate_id))
        self.assets._event(connection, principal, event_key, "skill_candidate_stage", payload, result)
        return result

    def authorize_diff(self, principal, candidate_id, *, expected_generation, before_hash, after_hash, event_key):
        brain = _brain(principal)
        identifier(candidate_id)
        _generation(expected_generation)
        IC._digest(before_hash)
        IC._digest(after_hash)
        if IM._schema_version(self.store) < 4:
            raise PermissionError("candidate_unavailable")
        payload = {"candidate_id": candidate_id, "expected_generation": expected_generation,
                   "before_hash": before_hash, "after_hash": after_hash}
        with closing(self.store._conn()) as connection:
            connection.execute("BEGIN")
            replay = self.assets._replay(connection, brain, event_key, "candidate_diff_authorize", payload)
            if replay is not None:
                return replay
            candidate = self.records._row(connection, brain, candidate_id)
            self._edit_open(connection, brain, candidate["experiment_id"])
            if candidate["base_hash"] != before_hash or candidate["content_hash"] != after_hash:
                raise IM.ConflictError("candidate_diff_changed")
            state = self._state(connection, principal, candidate["experiment_id"], candidate["target_id"], candidate["base_revision_id"], before_hash)
        if state["target"]["generation"] != expected_generation:
            raise IM.ConflictError("candidate_base_changed")
        observed, base_raw = self.observe(principal, state["target"])
        with closing(self.store._conn()) as connection:
            self.read_proposal(connection, principal, candidate, state, observed, base_raw)
        with self.store._Tx(self.store) as connection:
            replay = self.assets._replay(connection, brain, event_key, "candidate_diff_authorize", payload)
            if replay is not None:
                return replay
            self._edit_open(connection, brain, candidate["experiment_id"])
            self._guard(connection, principal, state, observed)
            self.read_proposal(connection, principal, candidate, state, observed, base_raw)
            self._guard(connection, principal, state, observed)
            result = self._insert_authority(connection, principal, state, observed, kind="exact_diff", candidate=candidate)
            self.assets._event(connection, principal, event_key, "candidate_diff_authorize", payload, result)
            return result
