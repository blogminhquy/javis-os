"""Durable isolated trial references and leases in the existing shared execution database."""
from __future__ import annotations

import json
import hashlib
import math
import secrets
import time
from contextlib import closing

from agent_ledger import CallLedger
import improvement_cases as IC
import improvement_store as IM

TERMINAL = frozenset({"completed", "failed", "unknown", "interrupted", "cancelled", "not_run"})
FAILURE_REASONS = frozenset({"unsupported_configuration", "authority_changed", "worker_failed", "evidence_failed",
                             "telemetry_failed", "evaluation_failed", "timeout", "cancelled", "runner_failed", "capacity_unavailable"})


def _request(value):
    if type(value) is dict and type(value.get('version')) is int and value['version'] == 4:
        from improvement_view_trial_protocol import validate_request_v4
        from improvement_claude import ClaudeTrialAdapter
        request = validate_request_v4(value)
        ClaudeTrialAdapter(request['engine_config'])
        return request
    if type(value) is dict and type(value.get("version")) is int and value["version"] == 3:
        from improvement_preparation_protocol import validate_preparation_request_v3
        request = validate_preparation_request_v3(value)
        from improvement_claude import ClaudeTrialAdapter
        ClaudeTrialAdapter(request["engine_config"])
        return request
    if type(value) is dict and type(value.get("version")) is int and value["version"] == 2:
        from improvement_experiment_protocol import validate_request_v2
        request = validate_request_v2(value)
        from improvement_claude import ClaudeTrialAdapter
        ClaudeTrialAdapter(request["engine_config"])  # Same actual schema, never a query or v1 projection.
        return request
    request = IC._frozen(value)
    IC._fields(request, {"version", "pins", "case_set_id", "case_id", "variant", "repeat", "engine_config",
        "baseline_context_hash", "target_generations", "deadline_at"}, {"qualification_id"})
    if (type(request["version"]) is not int or request["version"] != 1
            or request["variant"] not in {"baseline", "candidate"}
            or type(request["repeat"]) is not int or not 1 <= request["repeat"] <= 1_000_000):
        raise ValueError("invalid_trial_request")
    for key in ("case_set_id", "case_id"):
        if not isinstance(request[key], str) or not IC._ID.fullmatch(request[key]):
            raise ValueError("invalid_trial_identity")
    IC.CaseStore._pin_shape(request["pins"])
    import turn_context
    if turn_context.execution_metadata({"experiment_id": request["pins"]["experiment_id"], "trial_id": "pending",
            "case_id": request["case_id"], "variant": request["variant"], "repeat": request["repeat"], "attempt": 1,
            "execution_id": "improvement_trial:pending", "role": "solver", "purpose": "improve_probe",
            "learning_origin": "trial"}) is None:
        raise ValueError("invalid_trial_execution_identity")
    IC._digest(request["baseline_context_hash"])
    from improvement_claude import ClaudeTrialAdapter
    ClaudeTrialAdapter(request["engine_config"])  # Schema validation only; never invokes a binary.
    if request["engine_config"]["provider"] != "anthropic-cli" or request["engine_config"]["engine_id"] != "claude-sdk":
        raise ValueError("unsupported_trial_configuration")
    if request["pins"]["engine_config_hash"] != IM._hash(request["engine_config"]):
        raise IM.ConflictError("trial_configuration_drift")
    generations = request["target_generations"]
    if (not isinstance(generations, dict) or not generations
            or any(not isinstance(key, str) or type(value) is not int or value < 1 for key, value in generations.items())):
        raise ValueError("invalid_trial_target_generations")
    deadline = request["deadline_at"]
    if type(deadline) not in (int, float) or not math.isfinite(deadline) or deadline <= 0:
        raise ValueError("invalid_trial_deadline")
    return request


class TrialStore:
    def __init__(self, improvement_store, *, native_host=None):
        self.assets = improvement_store
        self.store, self.blobs = improvement_store.store, improvement_store.blobs
        self.cases = IC.CaseStore(improvement_store)
        self.ledger = CallLedger(self.store)
        from improvement_sandbox import TrialWorkspace
        self.workspace = TrialWorkspace(self.blobs.root.parent / "trials")
        self._views = None
        if native_host is not None:
            from improvement_trial_host import HostContextStore
            if (type(native_host) is not HostContextStore or native_host.assets is not self.assets
                    or native_host.store is not self.store):
                raise TypeError('concrete_same_store_native_host_required')
        self._native_host = native_host

    def bind_views(self, views):
        from improvement_views import EffectiveViews, _retired
        if (type(views) is not EffectiveViews or views.assets is not self.assets or views.store is not self.store
                or views.plans.admission.trials.workspace.root != self.workspace.root):
            raise TypeError('concrete_same_store_views_required')
        if self._views is not None and self._views is not views and not _retired(self._views):
            raise IM.ConflictError('view_resolver_already_bound')
        self._views = views

    @staticmethod
    def _row(connection, brain, identifier):
        row = connection.execute("SELECT * FROM improvement_trials WHERE id=? AND brain_id=?", (identifier, brain)).fetchone()
        if not row:
            raise PermissionError("trial_record_unavailable")
        return row

    def _current(self, connection, brain, request, *, trial_id=None, allow_unlinked=False, principal=None):
        from improvement_experiment_lineage import require_experiment_version
        require_experiment_version(connection, brain, request)
        pins = request["pins"]
        experiment = request.get("version") == 2
        preparation = request.get("version") == 3
        view_trial = request.get('version') == 4
        view = None
        if view_trial:
            from improvement_trial_records import _brain
            if self._views is None:
                raise PermissionError('view_resolver_unavailable')
            if _brain(principal) != brain:
                raise PermissionError('view_principal_unavailable')
            view, _ = self._views.resolve_request(principal, request, connection=connection,
                require_link=not allow_unlinked, trial_id=trial_id)
        if preparation:
            from improvement_preparation_lineage import load_preparation_lineage
            load_preparation_lineage(connection, brain, request, blobs=self.blobs,
                current=True, require_link=not allow_unlinked, trial_id=trial_id)
        if experiment:
            from improvement_experiment_qualification import require_tuning_families
            require_tuning_families(connection, brain, request['case_set_id'])
            from improvement_experiment_lineage import load_lineage
            if request["variant"] == "candidate":
                raise PermissionError("experiment_candidate_execution_unavailable")
            lineage = load_lineage(connection, brain, request, blobs=self.blobs,
                current=True, require_link=not allow_unlinked, trial_id=trial_id)
            if lineage["comparison"]["kind"] != "tuning" or request.get("qualification_id"):
                raise PermissionError("experiment_final_execution_unavailable")
        self.cases._enabled(connection, brain)
        if IM.ImprovementStore._policy(connection, brain)["version"] != pins["policy_version"]:
            raise IM.ConflictError("stale_trial_policy")
        case_set = self.cases._row(connection, "improvement_case_sets", brain, request["case_set_id"])
        if case_set["manifest_hash"] != pins["case_set_hash"]:
            raise IM.ConflictError("stale_trial_case_set")
        if not connection.execute("SELECT 1 FROM improvement_contracts WHERE brain_id=? AND manifest_hash=?",
                                  (brain, pins["contract_hash"])).fetchone():
            raise PermissionError("trial_record_unavailable")
        case = self.cases._case(connection, brain, request["case_set_id"], request["case_id"])
        for identifier in case["snapshot_ids"]:
            snapshot = self.cases._row(connection, "improvement_snapshots", brain, identifier)
            if snapshot["status"] != "sufficient" or json.loads(snapshot["manifest_json"])["grant_hash"] != pins["grant_hash"]:
                raise IM.ConflictError("stale_trial_source")
        bundle = None
        for variant, field in (("baseline", "base_bundle_hash"), ("candidate", "candidate_bundle_hash")):
            if (experiment or preparation or view_trial) and variant == "candidate":
                continue  # Typed A envelope pin; never look it up as an installed bundle.
            row = connection.execute("SELECT * FROM improvement_bundles WHERE brain_id=? AND manifest_hash=?",
                                     (brain, pins[field])).fetchone()
            if not row:
                raise PermissionError("trial_record_unavailable")
            if variant == request["variant"]:
                bundle = json.loads(row["manifest_json"])
        generations = request["target_generations"]
        expected_targets = {view.manifest['target']['target_id']} if view_trial else {asset['target_id'] for asset in bundle}
        if set(generations) != expected_targets:
            raise IM.ConflictError("stale_trial_targets")
        for target, generation in generations.items():
            row = IM.ImprovementStore._target(connection, brain, target)
            if row["status"] != "live" or row["generation"] != generation:
                raise IM.ConflictError("stale_trial_target")
        if case["split"] == "qualification":
            claim = self.cases._row(connection, "improvement_qualification", brain, request.get("qualification_id"))
            if claim["case_set_id"] != request["case_set_id"] or claim["pins_hash"] != IM._hash(pins):
                raise IM.ConflictError("stale_qualification_pin")
        elif request.get("qualification_id"):
            raise ValueError("unexpected_qualification_claim")
        return case

    @staticmethod
    def _public(connection, row):
        attempts = [dict(item) for item in connection.execute(
            "SELECT attempt,status,call_id,engine_at,failure_reason,created_at,updated_at FROM improvement_trial_attempts "
            "WHERE trial_id=? ORDER BY attempt", (row["id"],))]
        return {"trial_id": row["id"], "brain_id": row["brain_id"], "status": row["status"],
                "generation": row["generation"], "attempt": row["attempt"],
                "request": json.loads(row["request_json"]), "attempts": attempts}

    def get(self, principal, identifier):
        brain = IM._brain(principal)
        if IM._schema_version(self.store) < 3:
            raise PermissionError("trial_record_unavailable")
        with closing(self.store._conn()) as connection:
            return self._public(connection, self._row(connection, brain, identifier))

    def reserve(self, principal, request, *, event_key):
        brain = IM._brain(principal)
        request = _request(request)
        IM.ensure(self.store)
        with self.store._Tx(self.store) as connection:
            return self._reserve_in(connection, principal, request, event_key=event_key)

    def _reserve_in(self, connection, principal, request, *, event_key):
        self.cases._own_transaction(connection)
        brain = IM._brain(principal)
        request = _request(request)
        logical = IM._hash([request["pins"]["experiment_id"], request["variant"], request["case_set_id"],
                            request["case_id"], request["repeat"]])
        if request["version"] == 2:
            from improvement_experiment_protocol import logical_key_v2
            logical = logical_key_v2(request)
        elif request["version"] == 3:
            from improvement_preparation_protocol import logical_key_v3
            logical = logical_key_v3(request)
        elif request['version'] == 4:
            from improvement_view_trial_protocol import logical_key_v4
            logical = logical_key_v4(request)
        replay = self.assets._replay(connection, brain, event_key, "trial_reserve", request)
        if replay is not None:
            return replay
        self._current(connection, brain, request, allow_unlinked=request["version"] in (2, 3, 4), principal=principal)
        old = connection.execute("SELECT * FROM improvement_trials WHERE brain_id=? AND logical_key=?", (brain, logical)).fetchone()
        if old:
            if old["request_hash"] != IM._hash(request):
                raise IM.ConflictError("trial_identity_conflict")
            if request["version"] in (2, 3, 4):
                self._current(connection, brain, request, trial_id=old["id"], principal=principal)
            result = self._public(connection, old)
        else:
            now = time.time()
            if request["deadline_at"] <= now:
                raise ValueError("trial_deadline_expired")
            identifier = "it_" + secrets.token_hex(12)
            connection.execute("INSERT INTO improvement_trials VALUES(?,?,?,?,?,?,?,?,?,?)", (
                identifier, brain, logical, IM._hash(request), IM._json(request), "reserved", 1, 1, now, now))
            call = self.ledger.reserve(purpose="improve_probe", reason_ref=f"improvement_trial:{identifier}:attempt:1",
                brain_id=brain, context_ref="improvement:" + request["pins"]["experiment_id"], obligation=True,
                mirror_ref="improvement_trial:" + identifier, attempt=1, now=now, c=connection)
            if call is None:
                raise IM.ConflictError("trial_call_capacity_unavailable")
            connection.execute("INSERT INTO improvement_trial_attempts(trial_id,brain_id,attempt,status,call_id,created_at,updated_at) "
                               "VALUES(?,?,1,'reserved',?,?,?)", (identifier, brain, call, now, now))
            if request["version"] == 2:
                lineage = request["lineage"]
                connection.execute("INSERT INTO improvement_experiment_trial_links VALUES(?,?,?,?,?,?,?,?,?,?,?)", (
                    lineage["comparison_id"], brain, request["pins"]["experiment_id"], lineage["cell_position"], identifier,
                    IM._hash(request), lineage["pair_id"], request["case_id"], request["repeat"], request["variant"], now))
                self._current(connection, brain, request, trial_id=identifier, principal=principal)
            elif request["version"] == 3:
                lineage = request["preparation"]
                connection.execute("INSERT INTO improvement_preparation_trial_links VALUES(?,?,?,?,?,?,?,?,?)", (
                    lineage["preparation_id"], brain, request["pins"]["experiment_id"], lineage["cell_position"], identifier,
                    IM._hash(request), request["case_id"], request["repeat"], now))
                self._current(connection, brain, request, trial_id=identifier, principal=principal)
            elif request['version'] == 4:
                lineage, view = request['lineage'], request['view']
                connection.execute('INSERT INTO improvement_view_trial_links VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)', (
                    lineage['comparison_id'], brain, request['pins']['experiment_id'], lineage['cell_position'], identifier,
                    IM._hash(request), lineage['pair_id'], request['case_id'], request['repeat'], request['variant'],
                    view['view_id'], view['view_hash'], view['binding_hash'], now))
                self._current(connection, brain, request, trial_id=identifier, principal=principal)
            result = self._public(connection, self._row(connection, brain, identifier))
        self.assets._event(connection, principal, event_key, "trial_reserve", request, result)
        return result

    def claim(self, principal, identifier, *, expected_generation, now=None, lease_seconds=60):
        brain = IM._brain(principal)
        if type(lease_seconds) not in (int, float) or not 1 <= lease_seconds <= 3600:
            raise ValueError("invalid_trial_lease")
        with self.store._Tx(self.store) as connection:
            row = self._row(connection, brain, identifier)
            request = json.loads(row["request_json"])
            self._current(connection, brain, request, trial_id=row["id"], principal=principal)
            now = time.time() if now is None else now
            attempt = connection.execute("SELECT * FROM improvement_trial_attempts WHERE trial_id=? AND attempt=?",
                                         (identifier, row["attempt"])).fetchone()
            if (type(expected_generation) is not int or row["generation"] != expected_generation
                    or row["status"] != "reserved" or attempt["lease_token"]
                    or request["deadline_at"] <= now):
                raise IM.ConflictError("trial_claim_stale")
            token = secrets.token_urlsafe(32)
            connection.execute("UPDATE improvement_trial_attempts SET lease_token=?,lease_until=?,writer_hash=?,updated_at=? "
                               "WHERE trial_id=? AND attempt=?", (token, min(now + lease_seconds, request["deadline_at"]),
                                                                  hashlib.sha256(token.encode()).hexdigest(), now,
                                                                  identifier, row["attempt"]))
            connection.execute("UPDATE improvement_trials SET generation=generation+1,updated_at=? WHERE id=?", (now, identifier))
            return {**self._public(connection, self._row(connection, brain, identifier)), "lease_token": token}

    def _leased(self, connection, principal, identifier, expected_generation, lease_token, now):
        brain = IM._brain(principal)
        row = self._row(connection, brain, identifier)
        attempt = connection.execute("SELECT * FROM improvement_trial_attempts WHERE trial_id=? AND attempt=?",
                                     (identifier, row["attempt"])).fetchone()
        if (type(expected_generation) is not int or row["generation"] != expected_generation
                or row["status"] in TERMINAL or not lease_token or attempt["lease_token"] != lease_token
                or attempt["lease_until"] is None or attempt["lease_until"] <= now):
            raise IM.ConflictError("trial_lease_stale")
        return row, attempt

    def heartbeat(self, principal, identifier, *, expected_generation, lease_token, now=None, lease_seconds=60):
        if type(lease_seconds) not in (int, float) or not 1 <= lease_seconds <= 3600:
            raise ValueError("invalid_trial_lease")
        with self.store._Tx(self.store) as connection:
            observed_at = time.time() if now is None else now
            row, _ = self._leased(connection, principal, identifier, expected_generation, lease_token, observed_at)
            request = json.loads(row["request_json"])
            self._current(connection, row["brain_id"], request, trial_id=row["id"], principal=principal)
            observed_at = time.time() if now is None else now
            self._leased(connection, principal, identifier, expected_generation, lease_token, observed_at)
            until = min(observed_at + lease_seconds, request["deadline_at"])
            connection.execute("UPDATE improvement_trial_attempts SET lease_until=?,updated_at=? WHERE trial_id=? AND attempt=?",
                               (until, observed_at, identifier, row["attempt"]))
            return {"trial_id": identifier, "generation": row["generation"], "lease_until": until}

    def append_observation(self, principal, identifier, packet, **options):
        from improvement_trial_evidence import TrialEvidence
        return TrialEvidence(self).append(principal, identifier, packet, **options)

    def read_observation(self, principal, identifier, attempt, sequence):
        from improvement_trial_evidence import TrialEvidence
        return TrialEvidence(self).read(principal, identifier, attempt, sequence)

    def stage_evaluation(self, principal, identifier, **options):
        from improvement_trial_products import TrialProducts
        return TrialProducts(self).stage(principal, identifier, **options)

    def read_artifact(self, principal, identifier, attempt):
        from improvement_trial_products import TrialProducts
        return TrialProducts(self).artifact(principal, identifier, attempt)

    def read_receipt(self, principal, identifier, attempt):
        from improvement_trial_products import TrialProducts
        return TrialProducts(self).receipt(principal, identifier, attempt)

    def finish(self, principal, identifier, **options):
        from improvement_trial_results import TrialResults
        return TrialResults(self).finish(principal, identifier, **options)

    def finish_qualification(self, session, principal, identifier, *, expected_generation, lease_token, evidence):
        from improvement_qualification_session import QualificationSession
        from improvement_qualification_results import _StagedEvidence, _authenticate, _key, _EVIDENCE
        from improvement_native_protocol import _parse
        if (type(session) is not QualificationSession or type(evidence) is not _StagedEvidence
                or evidence.session is not session or evidence.context['stage'] is not evidence
                or evidence.context['owner'] is not self or principal is not session.principal
                or evidence.context['identifier'] != identifier or evidence.context['lease_token'] != lease_token):
            raise PermissionError('qualification_staged_evidence_foreign')
        value = _parse(evidence.raw)
        binding = evidence.context['binding']
        with self.store._Tx(self.store) as connection:
            session._query_current(binding, connection=connection)
            row, attempt = self._leased(connection, principal, identifier, expected_generation, lease_token, time.time())
            if row['status'] != 'running' or attempt['engine_at'] is None:
                raise IM.ConflictError('qualification_settlement_stale')
            _authenticate(self.assets, principal, connection, value, terminal=False)
            self.assets._event(connection, principal, _key(_EVIDENCE, value['identity']), _EVIDENCE,
                value['identity'], _parse(evidence.envelope))
            session._query_current(binding, connection=connection)
            _authenticate(self.assets, principal, connection, value, terminal=False)
            now = time.time()
            self._leased(connection, principal, identifier, expected_generation, lease_token, now)
            status = value['execution_status']
            if not self.ledger._settle_in(connection, attempt['call_id'], 'error' if status == 'failed' else 'ok', None, None, None, now):
                raise IM.ConflictError('trial_call_state_stale')
            connection.execute('UPDATE improvement_trial_attempts SET status=?,lease_token=NULL,lease_until=NULL,updated_at=? '
                'WHERE trial_id=? AND attempt=? AND lease_token=?', (status, now, identifier, binding.attempt, lease_token))
            connection.execute('UPDATE improvement_trials SET status=?,generation=generation+1,updated_at=? WHERE id=? AND generation=?',
                (status, now, identifier, expected_generation))
            session._assert_native_current(connection=connection)
            return self._public(connection, self._row(connection, principal.brain_id, identifier))

    def read_result(self, principal, identifier, attempt, **options):
        from improvement_trial_results import TrialResults
        return TrialResults(self).read(principal, identifier, attempt, **options)

    def reevaluate(self, principal, identifier, attempt, **options):
        from improvement_trial_results import TrialResults
        return TrialResults(self).reevaluate(principal, identifier, attempt, **options)

    def record_owner_decision(self, principal, identifier, attempt, criterion_id, verdict, **options):
        from improvement_trial_decisions import OwnerDecisionStore
        return OwnerDecisionStore(self).record(principal, identifier, attempt, criterion_id, verdict, **options)

    def _materialization(self, connection, row, baseline_context, *, principal=None):
        request = json.loads(row["request_json"])
        if request.get('version') == 4:
            from improvement_view_materialization import materialize_view
            return materialize_view(self, connection, row, baseline_context, principal)
        from improvement_native_formats import input_version
        version = input_version(request['engine_config'], 'baseline')
        if version == 5 and request['variant'] != 'baseline':
            raise ValueError('native_unpaired_candidate_unsupported')
        if version == 5:
            if self._native_host is None:
                raise PermissionError('trial_native_host_unbound')
            _, binding = self._native_host._bound(connection, principal, request)
            self._native_host._snapshot_observe(principal, binding)
            self._native_host._bound(connection, principal, request)
        if IM._hash(baseline_context) != request["baseline_context_hash"]:
            raise IM.ConflictError("trial_context_drift")
        brain = row["brain_id"]
        case = self._current(connection, brain, request, trial_id=row["id"], principal=principal)
        pins = request["pins"]
        field = "base_bundle_hash" if request["variant"] == "baseline" else "candidate_bundle_hash"
        bundle = connection.execute("SELECT manifest_json FROM improvement_bundles WHERE brain_id=? AND manifest_hash=?",
                                     (brain, pins[field])).fetchone()
        assets = []
        for item in json.loads(bundle[0]):
            revision = connection.execute("SELECT * FROM improvement_revisions WHERE id=? AND brain_id=?",
                                          (item["id"], brain)).fetchone()
            manifest = json.loads(revision["manifest_json"])
            assets.append({"id": item["id"], "path": manifest["canonical_ref"], "hash": revision["content_hash"],
                           "content": self.blobs.read(brain, revision["content_hash"]).decode("utf-8")})
        contract = json.loads(connection.execute("SELECT contract_json FROM improvement_contracts WHERE brain_id=? AND manifest_hash=?",
                                                 (brain, pins["contract_hash"])).fetchone()[0])
        public = IC.public_contract(contract)
        from improvement_sandbox import _manifest
        result = _manifest({"version": version, "brain_id": brain, "bundle_hash": pins[field],
            "engine_config_hash": pins["engine_config_hash"], "contract_hash": pins["contract_hash"],
            "grant_hash": pins["grant_hash"], "baseline_context": baseline_context,
            "public_contract": {"content": public, "hash": IM._hash(public)}, "assets": assets,
            "case": self.cases._solver(connection, brain, case),
            "learning_origin": "qualification" if case["split"] == "qualification" else "trial"})
        if version == 5:
            # Decrypted solver inputs may race an actual owner/source edit.
            # Exposure is committed by the caller only after this fresh check.
            _, binding = self._native_host._bound(connection, principal, request)
            self._native_host._snapshot_observe(principal, binding)
            self._native_host._bound(connection, principal, request)
            self._current(connection, brain, request, trial_id=row['id'], principal=principal)
        return result

    def materialize(self, principal, identifier, *, expected_generation, lease_token, baseline_context):
        baseline_context = IC._frozen(baseline_context)
        with self.store._Tx(self.store) as connection:
            now = time.time()
            row, _ = self._leased(connection, principal, identifier, expected_generation, lease_token, now)
            if row["status"] != "reserved":
                raise IM.ConflictError("trial_materialization_stale")
            # Validate every public byte before consuming a holdout or returning any input.
            manifest = self._materialization(connection, row, baseline_context, principal=principal)
            now = time.time()
            self._leased(connection, principal, identifier, expected_generation, lease_token, now)
            request = json.loads(row["request_json"])
            if request.get("qualification_id"):
                if request.get('version') == 4:
                    from improvement_view_qualification import ViewQualification
                    ViewQualification(self._views.plans, self._views).consume_in(connection, principal, request)
                else:
                    # A bare legacy pin cannot consume a later B-owned holdout.
                    from improvement_experiment_qualification import require_legacy_qualification
                    require_legacy_qualification(connection, row["brain_id"], request["case_set_id"], request["pins"])
                    connection.execute("UPDATE improvement_qualification SET status='consumed',consumed_at=? "
                                       "WHERE id=? AND brain_id=? AND status='reserved'",
                                       (now, request["qualification_id"], row["brain_id"]))
            else:
                case = self.cases._case(connection, row["brain_id"], request["case_set_id"], request["case_id"])
                for fingerprint in case["fingerprints"]:
                    qualification = connection.execute("SELECT 1 FROM improvement_case_families WHERE brain_id=? "
                        "AND fingerprint=? AND split='qualification' LIMIT 1", (row["brain_id"], fingerprint)).fetchone()
                    claim = connection.execute("SELECT q.status FROM improvement_qualification_claims c JOIN improvement_qualification q "
                        "ON q.id=c.reservation_id AND q.brain_id=c.brain_id WHERE c.brain_id=? AND c.fingerprint=?",
                        (row["brain_id"], fingerprint)).fetchone()
                    if qualification and (not claim or claim["status"] != "consumed"):
                        raise IM.ConflictError("qualification_exposure_denied")
                    connection.execute("INSERT OR IGNORE INTO improvement_case_exposures VALUES(?,?,?,?)",
                                       (row["brain_id"], fingerprint, request["case_set_id"], now))
            connection.execute("UPDATE improvement_trial_attempts SET materialization_hash=?,updated_at=? "
                               "WHERE trial_id=? AND attempt=?", (IM._hash(manifest), now, identifier, row["attempt"]))
            return manifest

    def prepared(self, principal, identifier, *, expected_generation, lease_token, receipt):
        receipt = IC._frozen(receipt)
        manifest = self.workspace.validate(receipt)
        with self.store._Tx(self.store) as connection:
            now = time.time()
            row, attempt = self._leased(connection, principal, identifier, expected_generation, lease_token, now)
            if row["status"] != "reserved" or receipt["trial_id"] != identifier or receipt["attempt"] != row["attempt"]:
                raise IM.ConflictError("trial_preparation_stale")
            if attempt["materialization_hash"] != IM._hash(manifest):
                raise IM.ConflictError("trial_exposure_not_committed")
            expected = self._materialization(connection, row, manifest["baseline_context"], principal=principal)
            if IM._hash(expected) != IM._hash(manifest):
                raise IM.ConflictError("trial_materialization_drift")
            request = json.loads(row["request_json"])
            if request.get("qualification_id"):
                claim = self.cases._row(connection, "improvement_qualification", row["brain_id"], request["qualification_id"])
                if claim["status"] != "consumed":
                    raise IM.ConflictError("qualification_not_consumed")
            now = time.time()
            self._leased(connection, principal, identifier, expected_generation, lease_token, now)
            connection.execute("UPDATE improvement_trial_attempts SET status='prepared',workspace_json=?,updated_at=? "
                               "WHERE trial_id=? AND attempt=?", (IM._json(receipt), now, identifier, row["attempt"]))
            connection.execute("UPDATE improvement_trials SET status='prepared',generation=generation+1,updated_at=? WHERE id=?", (now, identifier))
            return self._public(connection, self._row(connection, row["brain_id"], identifier))

    def start_engine(self, principal, identifier, *, expected_generation, lease_token, now=None):
        with self.store._Tx(self.store) as connection:
            marker_now = time.time() if now is None else now
            row, attempt = self._leased(connection, principal, identifier, expected_generation, lease_token, marker_now)
            if row["status"] != "prepared":
                raise IM.ConflictError("trial_not_prepared")
            request = json.loads(row["request_json"])
            self._current(connection, row["brain_id"], request, trial_id=row["id"], principal=principal)
            engine = request["engine_config"]
            marker_now = time.time() if now is None else now
            self._leased(connection, principal, identifier, expected_generation, lease_token, marker_now)
            if connection.execute("SELECT 1 FROM improvement_trials WHERE brain_id=? AND id<>? "
                                  "AND status IN ('running','evaluating') LIMIT 1",
                                  (row["brain_id"], identifier)).fetchone():
                raise IM.ConflictError("trial_brain_capacity_unavailable")
            if not self.ledger._mark_engine_in(connection, attempt["call_id"], engine["provider"], engine["model"], marker_now):
                raise IM.ConflictError("trial_engine_marker_stale")
            connection.execute("UPDATE improvement_trial_attempts SET status='running',engine_at=?,updated_at=? "
                               "WHERE trial_id=? AND attempt=?", (marker_now, marker_now, identifier, row["attempt"]))
            connection.execute("UPDATE improvement_trials SET status='running',generation=generation+1,updated_at=? WHERE id=?", (marker_now, identifier))
            return self._public(connection, self._row(connection, row["brain_id"], identifier))

    def _stop(self, connection, row, status, now, reason=None):
        attempt = connection.execute("SELECT * FROM improvement_trial_attempts WHERE trial_id=? AND attempt=?",
                                     (row["id"], row["attempt"])).fetchone()
        call = connection.execute("SELECT * FROM agent_calls WHERE id=?", (attempt["call_id"],)).fetchone()
        if call["engine_at"] is None:
            if not self.ledger._refund_in(connection, call["id"], now):
                raise IM.ConflictError("trial_call_state_stale")
        else:
            self.ledger._settle_in(connection, call["id"], "interrupted", None, None, None, now)
        connection.execute("UPDATE improvement_trial_attempts SET status=?,lease_token=NULL,lease_until=NULL,failure_reason=?,updated_at=? "
                           "WHERE trial_id=? AND attempt=?", (status, reason, now, row["id"], row["attempt"]))
        connection.execute("UPDATE improvement_trials SET status=?,generation=generation+1,updated_at=? WHERE id=?", (status, now, row["id"]))
        return self._public(connection, self._row(connection, row["brain_id"], row["id"]))

    def abort(self, principal, identifier, *, expected_generation, lease_token, reason):
        """Close only the owned host attempt, including expired leases, without a retry."""
        brain = IM._brain(principal)
        if not isinstance(reason, str) or reason not in FAILURE_REASONS:
            raise ValueError("invalid_trial_failure_reason")
        if not isinstance(lease_token, str) or not 1 <= len(lease_token) <= 256:
            raise IM.ConflictError("trial_abort_writer_unbound")
        with self.store._Tx(self.store) as connection:
            row = self._row(connection, brain, identifier)
            attempt = connection.execute("SELECT * FROM improvement_trial_attempts WHERE trial_id=? AND attempt=?",
                                         (identifier, row["attempt"])).fetchone()
            writer = hashlib.sha256(lease_token.encode()).hexdigest()
            if not attempt["writer_hash"] or not secrets.compare_digest(writer, attempt["writer_hash"]):
                raise IM.ConflictError("trial_abort_writer_unbound")
            if row["status"] in TERMINAL:
                result = self._public(connection, row)
            else:
                if (type(expected_generation) is not int or row["generation"] != expected_generation
                        or attempt["lease_token"] != lease_token):
                    raise IM.ConflictError("trial_abort_stale")
                status = "not_run" if attempt["engine_at"] is None else "unknown"
                result = self._stop(connection, row, status, time.time(), reason)
                payload = {"trial_id": identifier, "attempt": row["attempt"], "reason": reason}
                self.assets._event(connection, principal, "trial-abort:" + identifier + ":" + str(row["attempt"]),
                                   "trial_abort", payload, result)
        self.cleanup_terminal(principal, identifier)
        return result

    def reject_unclaimed(self, principal, identifier, *, expected_generation, reason):
        """Refund a stale reservation only if no host has acquired its lease."""
        brain = IM._brain(principal)
        if not isinstance(reason, str) or reason not in FAILURE_REASONS:
            raise ValueError("invalid_trial_failure_reason")
        with self.store._Tx(self.store) as connection:
            row = self._row(connection, brain, identifier)
            if row["status"] in TERMINAL:
                return self._public(connection, row)
            attempt = connection.execute("SELECT * FROM improvement_trial_attempts WHERE trial_id=? AND attempt=?",
                                         (identifier, row["attempt"])).fetchone()
            if (type(expected_generation) is not int or row["generation"] != expected_generation
                    or row["status"] != "reserved" or attempt["status"] != "reserved"
                    or attempt["lease_token"] is not None or attempt["writer_hash"] is not None
                    or attempt["engine_at"] is not None):
                raise IM.ConflictError("trial_reservation_owned")
            result = self._stop(connection, row, "not_run", time.time(), reason)
            payload = {"trial_id": identifier, "attempt": row["attempt"], "reason": reason}
            self.assets._event(connection, principal, "trial-reject:" + identifier + ":" + str(row["attempt"]),
                               "trial_reject", payload, result)
            return result

    def cancel(self, principal, identifier, *, expected_generation, event_key):
        brain = IM._brain(principal)
        payload = {"trial_id": identifier, "expected_generation": expected_generation}
        with self.store._Tx(self.store) as connection:
            replay = self.assets._replay(connection, brain, event_key, "trial_cancel", payload)
            if replay is not None:
                result = replay
            else:
                row = self._row(connection, brain, identifier)
                if type(expected_generation) is not int or row["generation"] != expected_generation or row["status"] in TERMINAL:
                    raise IM.ConflictError("trial_cancel_stale")
                result = self._stop(connection, row, "cancelled", time.time())
                self.assets._event(connection, principal, event_key, "trial_cancel", payload, result)
        self.cleanup_terminal(principal, identifier)
        return result

    def cleanup_terminal(self, principal, identifier=None):
        """Retry only this brain's terminal attempts, outside any writer transaction.

        The lifetime lock, not an expired database lease, proves no live runner
        still needs those bytes. Untracked paths and other brains are untouched.
        """
        brain = IM._brain(principal)
        with closing(self.store._conn()) as connection:
            if identifier is not None:
                self._row(connection, brain, identifier)
            rows = list(connection.execute("SELECT a.trial_id,a.attempt FROM improvement_trial_attempts a "
                "JOIN improvement_trials t ON t.id=a.trial_id WHERE a.brain_id=? AND t.brain_id=? "
                "AND a.status IN ('completed','failed','unknown','interrupted','cancelled','not_run') "
                + ("AND t.id=? " if identifier is not None else ""),
                (brain, brain, identifier) if identifier is not None else (brain, brain)))
        return sum(self.workspace.try_cleanup(row["trial_id"], row["attempt"]) for row in rows)

    def recover(self, principal, *, now=None):
        brain = IM._brain(principal)
        if IM._schema_version(self.store) < 3:
            return {"not_run": 0, "unknown": 0}
        with self.store._Tx(self.store) as connection:
            result = self._recover_in(connection, principal, now=now)
        self.cleanup_terminal(principal)
        return result

    def _recover_in(self, connection, principal, *, now=None, trial_ids=None):
        self.cases._own_transaction(connection)
        brain = IM._brain(principal)
        if trial_ids is not None:
            from improvement_execution_limits import MAX_TRIALS
            if (type(trial_ids) is not list or len(trial_ids) > MAX_TRIALS
                    or any(type(identifier) is not str or not IC._ID.fullmatch(identifier) for identifier in trial_ids)
                    or len(set(trial_ids)) != len(trial_ids)):
                raise ValueError("invalid_trial_recovery_selection")
            trial_ids = frozenset(trial_ids)
        result = {"not_run": 0, "unknown": 0}
        now = time.time() if now is None else now
        rows = list(connection.execute("SELECT t.* FROM improvement_trials t JOIN improvement_trial_attempts a "
            "ON t.id=a.trial_id AND t.attempt=a.attempt WHERE t.brain_id=? "
            "AND t.status IN ('reserved','prepared','running','evaluating') AND "
            "((a.lease_until IS NOT NULL AND a.lease_until<=?) OR "
            "(a.lease_until IS NULL AND json_extract(t.request_json,'$.deadline_at')<=?))", (brain, now, now)))
        for row in rows:
            if trial_ids is not None and row["id"] not in trial_ids:
                continue
            call = connection.execute("SELECT c.engine_at FROM agent_calls c JOIN improvement_trial_attempts a "
                "ON c.id=a.call_id WHERE a.trial_id=? AND a.attempt=?", (row["id"], row["attempt"])).fetchone()
            status = "not_run" if call["engine_at"] is None else "unknown"
            self._stop(connection, row, status, now)
            result[status] += 1
        return result
