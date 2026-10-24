"""One explicit owner admission; native availability precedes atomic reservation.

This synchronous component does not dispatch, resume or retry a query. Its caller
must retain the entire off-loop operation through cancellation and shutdown, then
hand the returned exact request to TrialTasks. Only IDs/hashes enter owner events.
M1 supports identical captured baseline/candidate bytes; changed candidates need
a later trusted body-only authoring path and are unavailable here.
"""
from __future__ import annotations

import hashlib
import json
import time
from contextlib import closing
from dataclasses import dataclass

import improvement_cases as IC
import improvement_store as IM
from improvement_claude import ClaudeTrialAdapter
from improvement_trial_associations import TrialCaseAssociations, _association, _FIELDS
from improvement_trial_host import HostContextStore, _brain
from improvement_trial_requests import validate_body, MAX_TIMEOUT_SECONDS
from improvement_trials import TrialStore, _request

_START = "trial_owner_start"
_PLAN = "trial_owner_plan"
_MANIFEST = {"kind", "canonical_ref", "source_hash", "protected_hash", "enabled", "ownership", "identity", "agent_key"}


@dataclass(frozen=True)
class AdmittedTrial:
    """Host-internal handoff; never serialize the raw request as an HTTP result."""
    trial_id: str
    request: dict
    reserve_event_key: str


class TrialAdmission:
    def __init__(self, host, *, checker_registry=None):
        if type(host) is not HostContextStore:
            raise TypeError("concrete_trial_admission_host_required")
        self.host, self.assets, self.store = host, host.assets, host.store
        self.associations = TrialCaseAssociations(host, checker_registry=checker_registry)
        self.trials = TrialStore(self.assets, native_host=host)

    @staticmethod
    def _reserve_key(brain, event_key):
        return "owner-trial-reserve-" + IM._hash([brain, event_key])

    @staticmethod
    def _plan_key(brain, experiment):
        return "owner-trial-plan-" + IM._hash([brain, experiment])

    def _replay(self, connection, principal, public):
        brain = _brain(principal)
        result = self.assets._replay(connection, brain, public["event_key"], _START, public)
        if result is None:
            return None
        IC._fields(result, {"trial_id", "reserve_event_key", "plan_hash"})
        IC._digest(result["plan_hash"])
        if result["reserve_event_key"] != self._reserve_key(brain, public["event_key"]):
            raise IM.ConflictError("trial_owner_start_changed")
        row = self.trials._row(connection, brain, result["trial_id"])
        request = _request(json.loads(row["request_json"]))
        if IM._hash(request) != row["request_hash"]:
            raise IM.ConflictError("trial_owner_start_changed")
        event = connection.execute("SELECT request_hash,result_json FROM improvement_events "
            "WHERE brain_id=? AND event_key=? AND operation=?",
            (brain, self._plan_key(brain, public["experiment_id"]), _PLAN)).fetchone()
        if event is None:
            raise IM.ConflictError("trial_owner_start_changed")
        saved = json.loads(event["result_json"])
        IC._fields(saved, {"plan", "plan_hash"})
        plan = saved["plan"]
        if (IM._hash(plan) != saved["plan_hash"] or saved["plan_hash"] != result["plan_hash"]
                or event["request_hash"] != saved["plan_hash"]
                or any(plan[key] != public[key] for key in ("contract_id", "case_set_id", "base_bundle_id",
                                                          "candidate_bundle_id", "timeout_seconds"))
                or any(plan[key] != request[key] for key in ("pins", "baseline_context_hash", "target_generations"))):
            raise IM.ConflictError("trial_owner_start_changed")
        reserved = self.assets._replay(connection, brain, result["reserve_event_key"], "trial_reserve", request)
        if reserved is None or reserved["trial_id"] != row["id"]:
            raise IM.ConflictError("trial_owner_start_changed")
        return AdmittedTrial(row["id"], request, result["reserve_event_key"])

    def _registry(self, refs):
        return tuple((ref, self.associations.registry[ref]["version"], self.associations.registry[ref]["hash"],
                      id(self.associations.registry[ref]["check"])) for ref in refs)

    def _bundle(self, connection, brain, identifier, targets, *, baseline, blobs):
        unavailable = "trial_baseline_revision_unavailable" if baseline else "trial_candidate_revision_unavailable"
        row = IC.CaseStore._row(connection, "improvement_bundles", brain, identifier)
        manifest = json.loads(row["manifest_json"])
        if (type(manifest) is not list or len(manifest) != len(targets)
                or IM._hash(manifest) != row["manifest_hash"]):
            raise PermissionError(unavailable)
        seen = set()
        for item in manifest:
            IC._fields(item, {"id", "target_id", "manifest_hash", "content_hash"})
            target = targets.get(item["target_id"])
            if target is None or item["target_id"] in seen:
                raise PermissionError(unavailable)
            seen.add(item["target_id"])
            revision = IC.CaseStore._row(connection, "improvement_revisions", brain, item["id"])
            source = json.loads(revision["manifest_json"])
            IC._fields(source, _MANIFEST)
            expected = {key: target[key] for key in ("kind", "canonical_ref", "source_hash", "protected_hash", "ownership", "identity")}
            expected.update(enabled=True, agent_key="")
            if (IM._json(source) != IM._json(expected) or revision["target_id"] != item["target_id"]
                    or {key: revision[key] for key in ("id", "target_id", "manifest_hash", "content_hash")} != item
                    or IM._hash(source) != revision["manifest_hash"]
                    or revision["content_hash"] != target["source_hash"]):
                raise PermissionError(unavailable)
            if baseline:
                current = IM.ImprovementStore._target(connection, brain, item["target_id"])
                if current["current_revision_id"] != item["id"]:
                    raise PermissionError(unavailable)
            digest = revision["content_hash"]
            if digest not in blobs:
                blobs[digest] = self.host.blobs.read(brain, digest)
            if (not isinstance(blobs[digest], bytes) or hashlib.sha256(blobs[digest]).hexdigest() != digest):
                raise PermissionError(unavailable)
        return row["manifest_hash"]

    def _prepare(self, connection, principal, public):
        brain = _brain(principal)
        row, binding, contract_hash, refs = self.associations._authority(connection, principal,
            public["experiment_id"], public["contract_id"])
        grant = self.host._grant(connection, row)
        if grant["generation"] != public["expected_context_generation"]:
            raise IM.ConflictError("trial_context_grant_stale")
        associated = _association(connection, brain, public["case_set_id"])
        if associated is None:
            raise PermissionError("trial_case_set_unassociated")
        IC._fields(associated, _FIELDS)
        if any(associated[key] != value for key, value in {
                "context_id": row["id"], "experiment_id": public["experiment_id"],
                "contract_id": public["contract_id"], "contract_hash": contract_hash,
                "grant_hash": row["grant_hash"]}.items()):
            raise PermissionError("trial_case_set_association_changed")
        case_set = self.associations.cases._row(connection, "improvement_case_sets", brain, public["case_set_id"])
        manifest = json.loads(case_set["manifest_json"])
        if (case_set["manifest_hash"] != associated["manifest_hash"] or IM._hash(manifest) != case_set["manifest_hash"]):
            raise IM.ConflictError("trial_case_set_association_changed")
        case = self.associations.cases._case(connection, brain, public["case_set_id"], public["case_id"])
        if [item for item in manifest["cases"] if item["id"] == public["case_id"]] != [case]:
            raise IM.ConflictError("trial_case_set_association_changed")
        targets = {target["id"]: target for target in binding["targets"]}
        if len(targets) != len(binding["targets"]) or any(target["kind"] != "skill" for target in targets.values()):
            raise PermissionError("trial_target_unavailable")
        blobs = {}
        base = self._bundle(connection, brain, public["base_bundle_id"], targets, baseline=True, blobs=blobs)
        candidate = self._bundle(connection, brain, public["candidate_bundle_id"], targets, baseline=False, blobs=blobs)
        pins = {"experiment_id": row["experiment_id"], "base_bundle_hash": base, "candidate_bundle_hash": candidate,
                "contract_hash": contract_hash, "case_set_hash": case_set["manifest_hash"],
                **{key: row[key] for key in ("engine_config_hash", "grant_hash", "policy_version", "scope_hash")}}
        IC.CaseStore._pin_shape(pins)
        request = {"version": 1, "pins": pins, "case_set_id": public["case_set_id"], "case_id": public["case_id"],
            "variant": public["variant"], "repeat": public["repeat"], "engine_config": binding["engine_config"],
            "baseline_context_hash": row["context_hash"], "target_generations": json.loads(row["target_generations_json"])}
        plan = {"version": 1, "context_id": row["id"], "contract_id": public["contract_id"],
            "case_set_id": public["case_set_id"], "base_bundle_id": public["base_bundle_id"],
            "candidate_bundle_id": public["candidate_bundle_id"], "pins": pins,
            "baseline_context_hash": request["baseline_context_hash"], "target_generations": request["target_generations"],
            "timeout_seconds": public["timeout_seconds"], "timeout_policy": {"id": "explicit-owner-trial", "version": 1,
                "maximum_seconds": MAX_TIMEOUT_SECONDS}}
        return plan, request, case["split"], self._registry(refs)

    def _available(self, connection, brain, public, plan, request):
        saved = self.assets._replay(connection, brain, self._plan_key(brain, public["experiment_id"]), _PLAN, plan)
        if saved is not None and saved != {"plan": plan, "plan_hash": IM._hash(plan)}:
            raise IM.ConflictError("trial_owner_plan_changed")
        logical = IM._hash([public["experiment_id"], public["variant"], public["case_set_id"], public["case_id"], public["repeat"]])
        if connection.execute("SELECT 1 FROM improvement_trials WHERE brain_id=? AND logical_key=?", (brain, logical)).fetchone():
            raise IM.ConflictError("trial_identity_conflict")

    def admit(self, principal, public_start_request):
        return self._admit(principal, public_start_request)

    def admit_qualification(self, session, principal, public_start_request):
        from improvement_qualification_session import QualificationSession
        if type(session) is not QualificationSession: raise TypeError('concrete_qualification_session_required')
        session._assert_trial_owner(self, principal)
        session._require_preflight()
        return self._admit(principal, public_start_request, session=session)

    def _admit(self, principal, public_start_request, *, session=None):
        brain = _brain(principal)
        public = validate_body(public_start_request, "start_trial")
        def current(connection):
            if session is not None:
                session._assert_trial_owner(self, principal)
                session._assert_native_current(connection=connection)
                prepared = self._prepare(connection, principal, public)
                if prepared[1]['engine_config'] != session._pin: raise PermissionError('qualification_pin_changed')
                self.host.live_guard(principal, prepared[1])
                session._require_preflight()
                session._assert_native_current(connection=connection)
        if IM._schema_version(self.store) < 3:
            raise PermissionError("trial_context_unavailable")
        with closing(self.store._conn()) as connection:
            current(connection)
            replay = self._replay(connection, principal, public)
            if replay is not None:
                return replay
            from improvement_experiment_lineage import require_experiment_version
            require_experiment_version(connection, brain, {"version": 1, "case_set_id": public["case_set_id"],
                "pins": {"experiment_id": public["experiment_id"]}})
            prepared = self._prepare(connection, principal, public)
            plan, request, split, registry = prepared
            self._available(connection, brain, public, plan, request)
        self.host.live_guard(principal, IC._frozen(request))
        def native_current(connection, joined):
            # The preflight owns no attempt yet. Keep the original admission
            # plan, available slot and actual source authority current instead.
            for _ in range(2):
                if self._prepare(connection, principal, public) != prepared:
                    raise IM.ConflictError("trial_admission_authority_changed")
                self._available(connection, brain, public, plan, request)
                self.host.live_guard(principal, IC._frozen(request))
            return "allow"

        if session is None:
            self._verify_native(principal, public, prepared, native_current)
        self.host.live_guard(principal, IC._frozen(request))
        with closing(self.store._conn()) as connection:
            current(connection)
            if self._prepare(connection, principal, public) != prepared:
                raise IM.ConflictError("trial_admission_authority_changed")
        reserve_key = self._reserve_key(brain, public["event_key"])
        with self.store._Tx(self.store) as connection:
            current(connection)
            replay = self._replay(connection, principal, public)
            if replay is not None:
                return replay
            if self._prepare(connection, principal, public) != prepared:
                raise IM.ConflictError("trial_admission_authority_changed")
            self._available(connection, brain, public, plan, request)
            self.host.live_guard(principal, IC._frozen(request))
            plan_hash = IM._hash(plan)
            if self.assets._replay(connection, brain, self._plan_key(brain, public["experiment_id"]), _PLAN, plan) is None:
                self.assets._event(connection, principal, self._plan_key(brain, public["experiment_id"]), _PLAN, plan,
                                   {"plan": plan, "plan_hash": plan_hash})
            if split == "qualification":
                qualification = self.associations.cases._reserve_qualification_in(connection, principal,
                    public["case_set_id"], request["pins"],
                    event_key="owner-trial-qualification-" + IM._hash([brain, request["pins"]]))
                request = {**request, "qualification_id": qualification["reservation_id"]}
            request = {**request, "deadline_at": time.time() + public["timeout_seconds"]}
            row = self.trials._reserve_in(connection, principal, request, event_key=reserve_key)
            self.host.live_guard(principal, IC._frozen(request))
            if self._prepare(connection, principal, public) != prepared:
                raise IM.ConflictError("trial_admission_authority_changed")
            self.assets._event(connection, principal, public["event_key"], _START, public,
                {"trial_id": row["trial_id"], "reserve_event_key": reserve_key, "plan_hash": plan_hash})
            current(connection)
            return AdmittedTrial(row["trial_id"], IC._frozen(row["request"]), reserve_key)

    def _verify_native(self, principal, public, prepared, native_current):
        brain = _brain(principal)
        request = prepared[1]
        try:
            adapter = ClaudeTrialAdapter(request["engine_config"])
            adapter.bind_native_authority(self.assets, principal, scope_hash=IM._hash({
                "version": 1, "kind": "trial_owner_admission", "brain_id": brain,
                "request_hash": IM._hash(public), "authority_hash": IM._hash(prepared)}), current=native_current)
            verified = adapter.verify()
            if (type(verified) is not dict or verified.get("supported") is not True
                    or verified.get("account_ready") is False or verified.get("domain") == "qualification"):
                raise ValueError("trial_native_unavailable")
            IC._digest(verified.get("capability_hash"))
        except (OSError, ValueError, RuntimeError):
            raise ValueError("trial_native_unavailable") from None
