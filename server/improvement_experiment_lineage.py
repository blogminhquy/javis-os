"""Scoped immutable SQL/blob lineage, without host/authoring/trial-store backedges.

This reader never observes native sources or interprets proposal content. Current
SQL fences and immutable historical integrity are explicit separate modes.
"""
from __future__ import annotations

import json

import improvement_store as IM
from improvement_blobs import AssetUnavailable
from improvement_experiment_protocol import definition, validate_request_v2, comparison_matrix, matrix_cell, comparison_hash


def _row(connection, table, brain, identifier):
    # Every table name is a module literal, never an owner request.
    row = connection.execute(f"SELECT * FROM {table} WHERE id=? AND brain_id=?", (identifier, brain)).fetchone()
    if row is None:
        raise PermissionError("experiment_lineage_unavailable")
    return row


def _same(expected, actual):
    if any(actual[key] != value for key, value in expected.items()):
        raise IM.ConflictError("experiment_lineage_changed")


def require_experiment_version(connection, brain, request):
    """A legacy shape cannot erase ownership by an existing B experiment."""
    if request.get('version') == 2:
        from improvement_comparison_links import require_legacy_comparison
        lineage = request.get('lineage')
        if type(lineage) is not dict or 'comparison_id' not in lineage:
            raise ValueError('invalid_experiment_request')
        require_legacy_comparison(connection, brain, lineage['comparison_id'])
    if request.get("version") not in (2, 3, 4):
        from improvement_experiment_qualification import experiment_owned
        if experiment_owned(connection, brain, request.get("case_set_id"), request["pins"]):
            raise PermissionError("experiment_request_version_required")


def current_fences(connection, brain, proof):
    """SQL-only final refresh after ALL slow source/blob work; opens no transaction."""
    from improvement_evaluation import EVALUATOR_PIN
    frozen, envelope, comparison = proof["definition"], proof["arm"], proof["comparison"]
    experiment = _row(connection, "improvement_experiments", brain, frozen["experiment_id"])
    if experiment["phase"] not in ("probing", "comparing", "qualifying"):
        raise PermissionError("experiment_execution_unavailable")
    if experiment["definition_hash"] != IM._hash(frozen) or frozen["evaluator"] != EVALUATOR_PIN:
        raise PermissionError("experiment_definition_unavailable")
    if comparison["kind"] == "tuning" and connection.execute(
            "SELECT 1 FROM improvement_experiment_selections WHERE experiment_id=? AND brain_id=?", (experiment["id"], brain)).fetchone():
        raise PermissionError("experiment_tuning_sealed")
    authority = connection.execute("SELECT a.*,g.generation,g.status,g.revoked_at FROM improvement_candidate_authorities a "
        "JOIN improvement_candidate_authority_grants g ON g.authority_id=a.id AND g.brain_id=a.brain_id "
        "WHERE a.id=? AND a.brain_id=?", (envelope["authority_id"], brain)).fetchone()
    if authority is None or IM._hash(dict(authority)) != envelope["authority_hash"]:
        raise PermissionError("experiment_arm_authority_changed")
    grant = connection.execute("SELECT * FROM improvement_trial_context_grants WHERE context_id=? AND brain_id=?",
                               (frozen["context_id"], brain)).fetchone()
    policy = IM.ImprovementStore._policy(connection, brain)
    if grant is None or grant["status"] != "active" or authority["status"] != "active":
        raise PermissionError("experiment_authority_revoked")
    if (grant["generation"] != frozen["context_generation"] or authority["generation"] != envelope["authority_generation"]
            or policy["mode"] == "off" or policy["version"] != frozen["policy_version"]):
        raise PermissionError("experiment_authority_changed")
    target = _row(connection, "improvement_targets", brain, frozen["target_id"])
    if (target["status"] != "live" or target["generation"] != frozen["base_generation"]
            or target["current_revision_id"] != frozen["base_revision_id"] or target["source_hash"] != frozen["base_hash"]):
        raise IM.ConflictError("experiment_base_changed")
    if comparison['kind'] == 'tuning':
        from improvement_experiment_qualification import require_tuning_families
        require_tuning_families(connection, brain, frozen['case_set_id'])


def _composed_owner(connection, brain, candidate, value):
    """Historical SQL ownership only; current proposal/native reads stay at host.

    Consent to generate may later be revoked. Execution still requires the
    separate exact-diff grant and independently checked view for these bytes.
    """
    from improvement_operation_protocol import operation_request
    if (value['decision_policy']['multiple_tests'] != 3 or candidate['authority_id'] is not None
            or candidate['authority_generation'] is not None):
        raise PermissionError('experiment_composed_arm_budget_unreserved')
    publication = connection.execute('SELECT * FROM improvement_compositions WHERE candidate_id=? AND brain_id=?',
        (candidate['id'], brain)).fetchone()
    if publication is None:
        raise PermissionError('experiment_composed_publication_unavailable')
    _same({'outcome': 'candidate', **{key: candidate[key] for key in
        ('experiment_id', 'content_hash', 'patch_hash', 'provenance_hash')}}, publication)
    authorization = _row(connection, 'improvement_compose_authorizations', brain, publication['authorization_id'])
    _same({'experiment_id': candidate['experiment_id'], 'context_id': candidate['context_id'],
        'definition_hash': IM._hash(value), 'context_generation': value['context_generation'],
        'policy_version': value['policy_version'], **{key: publication[key] for key in ('input_hash', 'basis_hash')}}, authorization)
    consent = list(connection.execute("SELECT * FROM improvement_events WHERE brain_id=? AND operation='compose_authorize' "
        "AND json_extract(result_json,'$.authorization_id')=? LIMIT 2", (brain, authorization['id'])))
    if len(consent) != 1:
        raise PermissionError('experiment_composed_consent_unavailable')
    metadata = json.loads(consent[0]['result_json'])
    _same({'authorization_id': authorization['id'], 'generation': 1, 'status': 'active',
        **{key: authorization[key] for key in ('experiment_id', 'context_id', 'input_hash', 'basis_hash')}}, metadata)
    generation = metadata['experiment_generation']
    if (type(generation) is not int or generation < 1 or consent[0]['actor'] != authorization['actor']
            or consent[0]['request_hash'] != IM._hash({'experiment_id': candidate['experiment_id'], 'expected_generation': generation})):
        raise IM.ConflictError('experiment_composed_consent_changed')
    operation = _row(connection, 'improvement_operations', brain, publication['operation_id'])
    request = operation_request(json.loads(operation['request_json']))
    _same({'kind': 'compose', 'role': 'composer', 'purpose': 'improve_compose', 'candidate_id': None, 'parent_id': None,
        **{key: authorization[key] for key in ('experiment_id', 'context_id', 'input_hash')}}, operation)
    _same({'definition_hash': authorization['definition_hash'], 'compose_authorization_id': authorization['id'],
        **{key: operation[key] for key in ('kind', 'role', 'purpose', 'candidate_id', 'parent_id', 'experiment_id', 'context_id', 'input_hash')}}, request)
    if (operation['request_hash'] != IM._hash(request) or operation['input_blob_hash'] != authorization['input_hash']
            or operation['status'] != 'completed' or operation['attempt'] not in (1, 2)):
        raise IM.ConflictError('experiment_composed_operation_changed')
    created = list(connection.execute("SELECT * FROM improvement_events WHERE brain_id=? AND operation='operation_create' "
        "AND json_extract(result_json,'$.operation_id')=? LIMIT 2", (brain, operation['id'])))
    initial = {'operation_id': operation['id'], **{key: operation[key] for key in
        ('experiment_id', 'context_id', 'kind', 'role', 'purpose', 'candidate_id', 'parent_id',
         'request_hash', 'input_hash', 'created_at')}, 'status': 'pending', 'generation': 1, 'attempt': 0}
    if (len(created) != 1 or json.loads(created[0]['result_json']) != initial
            or created[0]['request_hash'] != IM._hash({'request': request, 'input_blob_hash': operation['input_hash'],
                                                     'expected_generation': generation})):
        raise IM.ConflictError('experiment_composed_creation_changed')
    result = _row(connection, 'improvement_operation_results', brain, publication['result_id'])
    _same({'operation_id': operation['id'], 'attempt': operation['attempt'], 'blob_hash': publication['output_hash']}, result)
    attempt = connection.execute('SELECT * FROM improvement_operation_attempts WHERE operation_id=? AND brain_id=? AND attempt=?',
        (operation['id'], brain, operation['attempt'])).fetchone()
    if attempt is None or attempt['status'] != 'completed' or attempt['engine_at'] is None:
        raise PermissionError('experiment_composed_attempt_unavailable')
    report = json.loads(attempt['result_json'])
    if report.get('version') != 2 or IM._hash(report) != result['result_hash'] or result['blob_hash'] != result['result_hash']:
        raise IM.ConflictError('experiment_composed_result_changed')
    call = connection.execute('SELECT * FROM agent_calls WHERE id=?', (attempt['call_id'],)).fetchone()
    if call is None:
        raise PermissionError('experiment_composed_call_unavailable')
    _same({'brain_id': brain, 'status': 'ok', 'engine_at': attempt['engine_at'], 'purpose': 'improve_compose',
        'attempt': operation['attempt'], 'context_ref': 'improvement:' + candidate['experiment_id'],
        'mirror_ref': 'improvement_operation:' + operation['id'],
        'reason_ref': 'improvement_operation:' + operation['id'] + ':attempt:' + str(operation['attempt'])}, call)
    owner = connection.execute("SELECT * FROM improvement_events WHERE brain_id=? AND event_key=? AND operation='compose_generate'",
        (brain, candidate['owner_event_key'])).fetchone()
    # The trusted host may grant several owner identities access to one brain.
    # Consent and execution keep their actual actors; do not invent an actor
    # equality policy after an otherwise authorized operation has completed.
    if (owner is None or owner['actor'] != created[0]['actor'] or owner['request_hash'] != IM._hash({
            'authorization_id': authorization['id'], 'expected_generation': generation})):
        raise PermissionError('experiment_composed_owner_event_unavailable')
    outcome = json.loads(owner['result_json'])
    _same({'authorization_id': authorization['id'], 'experiment_id': candidate['experiment_id'], 'operation_id': operation['id'],
        'result_id': result['id'], 'composition_id': publication['id'], 'status': 'candidate_staged',
        'generation': generation + 2, 'business_proof': False}, outcome)
    if type(outcome['candidates']) is not list or len(outcome['candidates']) != 1:
        raise IM.ConflictError('experiment_composed_owner_event_changed')
    _same({'candidate_id': candidate['id'], 'edit_authority': None, **{key: candidate[key] for key in
        ('context_id', 'experiment_id', 'target_id', 'base_revision_id', 'base_hash', 'base_generation',
         'ordinal', 'content_hash', 'byte_size', 'patch_hash', 'provenance_hash', 'semantic_status')}}, outcome['candidates'][0])


def _arm(connection, brain, experiment, value, lineage):
    saved = connection.execute("SELECT * FROM improvement_experiment_arms WHERE experiment_id=? AND brain_id=? AND ordinal=?",
                               (experiment["id"], brain, lineage["arm_ordinal"])).fetchone()
    if saved is None:
        raise PermissionError("experiment_arm_unavailable")
    envelope = json.loads(saved["envelope_json"])
    if type(envelope) is not dict or IM._hash(envelope) != saved["envelope_hash"]:
        raise IM.ConflictError("experiment_arm_changed")
    _same({"candidate_id": lineage["candidate_id"], "envelope_hash": lineage["arm_hash"]}, saved)
    expected = {key: value[key] for key in ("experiment_id", "context_id", "target_id", "base_revision_id", "base_hash", "base_generation")}
    expected.update(definition_hash=experiment["definition_hash"], candidate_id=saved["candidate_id"], ordinal=saved["ordinal"],
                    authority_id=saved["authority_id"], authority_generation=saved["authority_generation"], version=1)
    _same(expected, envelope)
    candidate = _row(connection, "improvement_skill_candidates", brain, saved["candidate_id"])
    _same({key: value[key] for key in ("experiment_id", "context_id", "target_id", "base_revision_id", "base_hash", "base_generation")}, candidate)
    _same({key: candidate[key] for key in ("content_hash", "byte_size", "patch_hash", "provenance_hash", "semantic_status", "ordinal", "owner_event_key")}, envelope)
    if candidate['ordinal'] == 3:
        _composed_owner(connection, brain, candidate, value)
    else:
        owner = connection.execute("SELECT result_json FROM improvement_events WHERE brain_id=? AND event_key=? "
            "AND operation='skill_candidate_owner_request'",
            (brain, "candidate-owner-" + IM._hash([brain, candidate["owner_event_key"]]))).fetchone()
        if owner is None:
            raise PermissionError("experiment_arm_owner_event_unavailable")
        _same({"context_id": candidate["context_id"], "experiment_id": candidate["experiment_id"], "target_id": candidate["target_id"],
               "patch_hash": candidate["patch_hash"], "candidate_id": candidate["id"]}, json.loads(owner[0]))
    authority = connection.execute("SELECT a.*,g.generation,g.status,g.revoked_at FROM improvement_candidate_authorities a "
        "JOIN improvement_candidate_authority_grants g ON g.authority_id=a.id AND g.brain_id=a.brain_id "
        "WHERE a.id=? AND a.brain_id=?", (saved["authority_id"], brain)).fetchone()
    if authority is None:
        raise PermissionError("experiment_arm_authority_unavailable")
    _same({key: value[key] for key in ("context_id", "target_id", "base_revision_id", "base_hash", "base_generation", "context_generation")}, authority)
    _same({"before_hash": value["base_hash"], "source_authority_hash": envelope["source_authority_hash"]}, authority)
    if not ((authority["kind"] == "editable_region" and authority["id"] == candidate["authority_id"])
            or (authority["kind"] == "exact_diff" and authority["candidate_id"] == candidate["id"]
                and authority["after_hash"] == candidate["content_hash"])):
        raise PermissionError("experiment_arm_authority_changed")
    # Historical integrity checks the original active-grant pin, never reactivates it.
    original = dict(authority) | {"generation": saved["authority_generation"], "status": "active", "revoked_at": None}
    if saved["authority_generation"] != 1 or IM._hash(original) != envelope["authority_hash"]:
        raise IM.ConflictError("experiment_arm_authority_changed")
    return saved, envelope, authority


def load_lineage(connection, brain, value, *, blobs, current, require_link, trial_id=None):
    if type(current) is not bool or type(require_link) is not bool or (trial_id is not None and not require_link):
        raise ValueError("explicit_experiment_lineage_mode_required")
    request = validate_request_v2(value)
    try:
        return _load_lineage(connection, brain, request, blobs=blobs, current=current, require_link=require_link, trial_id=trial_id)
    except (IM.ConflictError, PermissionError):
        raise
    except (TypeError, ValueError, KeyError, UnicodeError, RecursionError) as error:
        raise AssetUnavailable("experiment_lineage_corrupt") from error


def _load_lineage(connection, brain, request, *, blobs, current, require_link, trial_id):
    from improvement_comparison_links import require_legacy_comparison
    require_legacy_comparison(connection, brain, request['lineage']['comparison_id'])
    proof = _comparison_proof(connection, brain, request, blobs=blobs, current=current)
    if require_link:
        link = connection.execute("SELECT * FROM improvement_experiment_trial_links WHERE comparison_id=? AND brain_id=? AND cell_position=?",
            (proof['comparison']['id'], brain, request['lineage']['cell_position'])).fetchone()
        if link is None:
            raise PermissionError("experiment_trial_link_unavailable")
        trial = _row(connection, "improvement_trials", brain, link["trial_id"])
        _same({"experiment_id": proof['definition']['experiment_id'], "request_hash": IM._hash(request), **proof['cell']}, link)
        if (trial["request_hash"] != link["request_hash"] or trial["request_json"] != IM._json(request)
                or (trial_id is not None and trial["id"] != trial_id)):
            raise IM.ConflictError("experiment_trial_link_changed")
    return proof


def _comparison_proof(connection, brain, request, *, blobs, current):
    """Common immutable proof after an explicit v2 or v4 validator, with full request."""
    pins, lineage = request["pins"], request["lineage"]
    experiment = _row(connection, "improvement_experiments", brain, pins["experiment_id"])
    if current and experiment["phase"] not in ("probing", "comparing", "qualifying"):
        raise PermissionError("experiment_execution_unavailable")
    frozen = definition(json.loads(experiment["definition_json"]))
    if IM._hash(frozen) != experiment["definition_hash"]:
        raise IM.ConflictError("experiment_definition_changed")
    _same({"id": frozen["experiment_id"], "context_id": frozen["context_id"], "target_id": frozen["target_id"]}, experiment)
    _same({"context_id": frozen["context_id"], "definition_hash": experiment["definition_hash"]}, lineage)
    _same({key: frozen[key] for key in ("experiment_id", "base_bundle_hash", "contract_hash", "case_set_hash", "engine_config_hash",
                                      "grant_hash", "scope_hash", "policy_version")}, pins)
    if (request["case_set_id"] != frozen["case_set_id"] or request["baseline_context_hash"] != frozen["baseline_context_hash"]
            or request["target_generations"] != {frozen["target_id"]: frozen["base_generation"]}):
        raise IM.ConflictError("experiment_request_changed")
    context = _row(connection, "improvement_trial_contexts", brain, frozen["context_id"])
    _same({key: frozen[key] for key in ("experiment_id", "binding_hash", "engine_config_hash", "grant_hash", "scope_hash", "policy_version")}, context)
    if context["context_hash"] != frozen["baseline_context_hash"] or json.loads(context["target_generations_json"]) != request["target_generations"]:
        raise IM.ConflictError("experiment_context_changed")
    bundle = _row(connection, "improvement_bundles", brain, frozen["base_bundle_id"])
    revision = _row(connection, "improvement_revisions", brain, frozen["base_revision_id"])
    manifest = json.loads(bundle["manifest_json"])
    if (bundle["manifest_hash"] != frozen["base_bundle_hash"] or IM._hash(manifest) != frozen["base_bundle_hash"]
            or manifest != [{key: revision[key] for key in ("id", "target_id", "manifest_hash", "content_hash")}]
            or revision["target_id"] != frozen["target_id"] or revision["content_hash"] != frozen["base_hash"]
            or IM._hash(json.loads(revision["manifest_json"])) != revision["manifest_hash"]):
        raise IM.ConflictError("experiment_baseline_changed")
    contract = _row(connection, "improvement_contracts", brain, frozen["contract_id"])
    contract_value = json.loads(contract["contract_json"])
    if (contract["manifest_hash"] != frozen["contract_hash"] or IM._hash(contract_value) != frozen["contract_hash"]
            or contract_value["evaluator"] != frozen["evaluator"] or contract_value["primary_metric"] != {
                "criterion_id": frozen["endpoint"]["criterion_id"], "direction": "higher", "aggregation": "all_pass"}):
        raise IM.ConflictError("experiment_contract_changed")
    comparison = _row(connection, "improvement_comparisons", brain, lineage["comparison_id"])
    _same({"experiment_id": experiment["id"], "definition_hash": lineage["definition_hash"], "ordinal": lineage["arm_ordinal"],
           "arm_hash": lineage["arm_hash"], "matrix_hash": lineage["matrix_hash"]}, comparison)
    if comparison_hash(comparison) != lineage["comparison_hash"]:
        raise IM.ConflictError("experiment_comparison_changed")
    arm, envelope, authority = _arm(connection, brain, experiment, frozen, lineage)
    case_set = _row(connection, "improvement_case_sets", brain, frozen["case_set_id"])
    manifest = json.loads(case_set["manifest_json"])
    if case_set["manifest_hash"] != frozen["case_set_hash"] or IM._hash(manifest) != frozen["case_set_hash"]:
        raise IM.ConflictError("experiment_case_set_changed")
    associated = [json.loads(row[0]) for row in connection.execute(
        "SELECT result_json FROM improvement_events WHERE brain_id=? AND operation='owner_trial_case_set' ORDER BY id", (brain,))]
    associated = [item for item in associated if item.get("case_set_id") == frozen["case_set_id"]]
    if not associated or any(item != associated[0] for item in associated):
        raise PermissionError("experiment_case_set_unassociated")
    _same({key: frozen[key] for key in ("context_id", "experiment_id", "contract_id", "contract_hash", "case_set_id", "grant_hash")}, associated[0])
    if associated[0]["manifest_hash"] != frozen["case_set_hash"]:
        raise IM.ConflictError("experiment_case_set_changed")
    rows = [json.loads(row[0]) for row in connection.execute(
        "SELECT case_json FROM improvement_cases WHERE brain_id=? AND case_set_id=? ORDER BY id", (brain, frozen["case_set_id"]))]
    if sorted(rows, key=lambda row: row["id"]) != sorted(manifest["cases"], key=lambda row: row["id"]):
        raise IM.ConflictError("experiment_case_set_changed")
    splits = ("tuning",) if comparison["kind"] == "tuning" else ("qualification", "regression")
    expected = comparison_matrix(frozen, arm["envelope_hash"], arm["ordinal"], comparison["kind"],
        [case["id"] for case in rows if case["split"] in splits], manifest["seed"])
    raw = blobs.read(brain, comparison["matrix_blob_hash"])
    if (type(raw) is not bytes or len(raw) > 1048576 or comparison["matrix_blob_hash"] != comparison["matrix_hash"]
            or raw != IM._json(expected).encode("utf-8") or IM._hash(expected) != comparison["matrix_hash"]
            or comparison["cell_count"] != 2 * len(expected["pairs"])):
        raise IM.ConflictError("experiment_matrix_changed")
    cell = matrix_cell(expected, lineage["cell_position"])
    _same({key: request[key] for key in ("case_id", "repeat", "variant")}, cell)
    if cell["pair_id"] != lineage["pair_id"]:
        raise IM.ConflictError("experiment_pair_changed")
    if comparison["kind"] == "final":
        selection = connection.execute("SELECT * FROM improvement_experiment_selections WHERE brain_id=? AND experiment_id=?",
                                       (brain, experiment["id"])).fetchone()
        if (selection is None or selection["choice"] != "candidate" or selection["ordinal"] != arm["ordinal"]
                or selection["definition_hash"] != experiment["definition_hash"]):
            raise PermissionError("experiment_final_selection_unavailable")
    proof = {"definition": frozen, "arm": envelope, "comparison": dict(comparison), "cell": cell}
    if current:
        current_fences(connection, brain, proof)
    return proof
