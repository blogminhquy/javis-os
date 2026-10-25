"""Pure checks of host trial records, without filesystem access or engine execution.

These checks establish consistency of recorded evidence, not live authorization or
business quality. The runner must separately validate its workspace and current
source/grant/policy/target authority. No text from a solver becomes an instruction.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

from improvement_blobs import MAX_ASSET_BYTES
from improvement_cases import CaseStore, _ID, _contract, _digest, _fields, _frozen, public_contract
from improvement_sandbox import _effective_hash, _manifest, trial_system_prompt
from improvement_store import _hash
from improvement_skill_asset_proof import OBSERVATION_TYPE, TOOL_NAME, correlate_asset_reads

_TOOLS = ["mcp__fixture__fixture_read"]
_EVENTS = {"native_system", "observation", "usage", "artifact", "installation_receipt", "terminal", "tool_call",
           "tool_result", "tool_denied", "error", "text", "thinking", "delta", "final"}
_EFFECTS = {"side_effect", "production_write", "canonical_write", "lesson_created", "task_created", "message_sent"}
_RECEIPT_FIELDS = {"version", "trial_id", "attempt", "session_id", "input_hash", "effective_hash", "bundle_hash",
    "contract_hash", "public_contract_hash", "engine_config_hash", "grant_hash", "capability_hash", "baseline_context_hash",
    "expected_system_prompt_hash", "system_prompt_hash", "tool_inventory_hash", "observed_tool_inventory_hash",
    "fixture_inventory_hash", "asset_revisions", "requested", "actual_models", "actual_reasoning", "coverage"}


def _row(identifier, verdict, reason, **evidence):
    return {"id": identifier, "verdict": verdict, "reason": reason,
            "evidence": {"coverage": "record_checks_only", "business_proof": False, **evidence}}


def _equal(identifier, expected, actual, reason):
    mismatches = sorted(key for key, value in expected.items() if actual.get(key) != value)
    return _row(identifier, "fail" if mismatches else "pass", reason if mismatches else "record_pins_match", fields=mismatches)


def _valid_event(event, *, asset_reads=False, read_outcomes=False):
    kind = event.get("type")
    supported = _EVENTS | _EFFECTS | ({OBSERVATION_TYPE} if asset_reads else set()) | ({'trial_read_broker_observation'} if read_outcomes else set())
    if not isinstance(kind, str) or kind not in supported:
        return False
    if "session_id" in event and event["session_id"] is not None and not isinstance(event["session_id"], str):
        return False
    if kind == "native_system":
        return isinstance(event.get("subtype"), str) and isinstance(event.get("data"), dict)
    if kind in (OBSERVATION_TYPE, 'trial_read_broker_observation'):
        return isinstance(event.get('observation'), dict)
    if kind in ("tool_call", "tool_result"):
        return (isinstance(event.get("id"), str) and bool(event["id"])
                and (isinstance(event.get("name"), str) if kind == "tool_call" else
                    type(event.get("is_error")) is bool or (read_outcomes and 'is_error' in event and event['is_error'] is None)))
    if kind == "tool_denied":
        return isinstance(event.get("name"), str) and isinstance(event.get("reason"), str)
    if kind == "observation":
        return event.get("model") is None or isinstance(event["model"], str)
    if kind == "artifact":
        return isinstance(event.get("content"), str) and isinstance(event.get("hash"), str)
    return True


def _protocol(packets, workspace, capability):
    identity = {key: workspace[key] for key in ("trial_id", "attempt", "input_hash")}
    state, failure = "starting", None
    extras = {"worker_ready": {"capability_hash"}, "engine_start_requested": set(), "engine_event": {"event"},
              "fixture_event": {"event"}, "worker_complete": {"fixture_events", "tool_denials"}}
    for sequence, packet in enumerate(packets, 1):
        if not isinstance(packet, dict) or type(packet.get("version")) is not int or packet.get("version") != 1:
            failure = "invalid_worker_packet"
            break
        if type(packet.get("sequence")) is not int or packet["sequence"] != sequence:
            failure = "worker_sequence_mismatch"
            break
        kind = packet.get("type")
        if kind == "worker_error":
            failure = "worker_error"
            break
        if not isinstance(kind, str) or kind not in extras:
            failure = "unsupported_worker_packet"
            break
        if (set(packet) != {"version", "sequence", "type", *identity, *extras[kind]}
                or type(packet.get("attempt")) is not int or any(packet.get(key) != value for key, value in identity.items())):
            failure = "worker_identity_mismatch"
            break
        if kind == "worker_ready":
            if state != "starting" or packet["capability_hash"] != capability:
                failure = "worker_capability_mismatch"
                break
            state = "ready"
        elif kind == "engine_start_requested":
            if state != "ready":
                failure = "worker_start_order_mismatch"
                break
            state = "running"
        elif state != "running":
            failure = "worker_event_order_mismatch"
            break
        elif kind == "worker_complete":
            state = "complete"
    if failure:
        return _row("worker_protocol", "fail", failure)
    return _row("worker_protocol", "pass" if state == "complete" else "unknown",
                "worker_protocol_complete" if state == "complete" else "worker_protocol_incomplete")


def _receipt(events, workspace, manifest, request, capability):
    records = [event for event in events if event.get("type") == "installation_receipt"]
    if len(records) != 1:
        return None, _row("installation", "fail" if records else "unknown",
                          "multiple_installation_receipts" if records else "missing_installation_receipt")
    event, receipt = records[0], records[0].get("receipt")
    try:
        view_trial = request.get('version') == 4
        asset_reads = manifest['version'] == 3
        native_reads = manifest['version'] == 4
        native_baseline = manifest['version'] == 5
        _fields(receipt, _RECEIPT_FIELDS | ({'effective_view'} if view_trial else set())
                | ({'asset_read_proofs'} if asset_reads else set())
                | ({'read_outcome_proofs'} if native_reads else set())
                | ({'native_input_delivery'} if native_reads or native_baseline else set()))
        if (type(receipt["version"]) is not int or receipt["version"] != (5 if native_baseline else 4 if native_reads else 3 if asset_reads else 2 if view_trial else 1)
                or type(receipt["attempt"]) is not int or event.get("hash") != _hash(receipt)
                or (receipt["session_id"] is not None and not isinstance(receipt["session_id"], str))
                or (asset_reads and type(receipt['asset_read_proofs']) is not list)
                or (native_reads and type(receipt['read_outcome_proofs']) is not list)):
            raise ValueError("invalid_installation_receipt")
        expected = {key: workspace[key] for key in ("trial_id", "attempt", "input_hash", "effective_hash")}
        expected.update({key: manifest[key] for key in ("bundle_hash", "contract_hash", "engine_config_hash", "grant_hash")})
        if view_trial:
            expected['effective_view'] = request['view']
        expected.update(public_contract_hash=manifest["public_contract"]["hash"], capability_hash=capability,
            baseline_context_hash=manifest["baseline_context"]["hash"], expected_system_prompt_hash=_sha(trial_system_prompt(manifest)),
            fixture_inventory_hash=_hash([{key: item[key] for key in ("snapshot_id", "hash", "source")}
                                          for item in manifest["case"]["fixtures"]]), tool_inventory_hash=_hash(_tools(manifest)),
            requested={key: request["engine_config"][key] for key in ("provider", "model", "reasoning")})
        result = _equal("installation", expected, receipt, "installation_pin_mismatch")
        coverage = receipt["coverage"]
        _fields(coverage, {"input", "runtime", "context", "prompt", "tool_inventory", "model", "reasoning"})
        if result["verdict"] == "pass" and any(coverage[key] != "host_verified" for key in ("input", "runtime")):
            result = _row("installation", "unknown", "installation_not_host_verified")
        return receipt, result
    except (ValueError, TypeError, KeyError):
        return None, _row("installation", "fail", "invalid_installation_receipt")


def _sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _tools(manifest):
    return _TOOLS + ([TOOL_NAME] if manifest['version'] in (3, 4) else [])


def _inventory(receipt, inits, tools_expected=_TOOLS):
    if (not receipt or len(inits) != 1 or not isinstance(inits[0].get("data"), dict)
            or "tools" not in inits[0]["data"]):
        return _row("tool_inventory", "unknown", "native_inventory_unobserved")
    tools = inits[0]["data"]["tools"]
    if tools != tools_expected or receipt["observed_tool_inventory_hash"] != _hash(tools):
        return _row("tool_inventory", "fail", "native_tool_inventory_mismatch")
    if receipt["coverage"]["tool_inventory"] != "observed":
        return _row("tool_inventory", "unknown", "native_inventory_unobserved")
    return _row("tool_inventory", "pass", "fixture_only_inventory_observed" if tools_expected == _TOOLS
                else "pinned_readonly_inventory_observed")


def _asset_use(manifest, workspace, events, receipt):
    if manifest['version'] == 4:
        from improvement_read_outcome_proof import correlate_read_outcomes, SKILL_TOOL
        result = correlate_read_outcomes(manifest, workspace, events)
        if receipt is None:
            return _row('asset_observed_use', 'unknown', 'read_outcome_receipt_unavailable')
        if _hash(receipt['read_outcome_proofs']) != _hash(result['proofs']):
            return _row('asset_observed_use', 'fail', 'read_outcome_summary_mismatch')
        skill_hit = any(item['tool_name'] == SKILL_TOOL and item['outcome'] == 'hit' for item in result['proofs'])
        assets = receipt.get('asset_revisions')
        expected = 'observed' if result['verdict'] == 'pass' and skill_hit else 'unknown'
        if (type(assets) is not list or len(assets) != 1 or type(assets[0]) is not dict
                or assets[0].get('observed_use') != expected):
            return _row('asset_observed_use', 'fail', 'read_outcome_coverage_mismatch')
        verdict = result['verdict'] if result['verdict'] != 'pass' or skill_hit else 'unknown'
        return _row('asset_observed_use', verdict, result['reason'], proof_count=len(result['proofs']), comprehension='unobserved')
    if manifest['version'] != 3:
        return _row('asset_observed_use', 'unknown', 'native_asset_use_unobserved')
    result = correlate_asset_reads(manifest, workspace, events)
    if receipt is None:
        return _row('asset_observed_use', 'unknown', 'asset_read_receipt_unavailable')
    if _hash(receipt['asset_read_proofs']) != _hash(result['proofs']):
        return _row('asset_observed_use', 'fail', 'asset_read_summary_mismatch')
    assets = receipt.get('asset_revisions')
    expected = 'observed' if result['verdict'] == 'pass' else 'unknown'
    if (type(assets) is not list or len(assets) != 1 or type(assets[0]) is not dict
            or assets[0].get('observed_use') != expected):
        return _row('asset_observed_use', 'fail', 'asset_read_coverage_mismatch')
    return _row('asset_observed_use', result['verdict'], result['reason'],
                proof_count=len(result['proofs']), comprehension='unobserved')


def _sources(manifest, packets, complete):
    streamed = [packet.get("event") for packet in packets if packet.get("type") == "fixture_event"]
    if complete is None:
        return _row("source_coverage", "unknown", "fixture_observations_incomplete")
    summarized = complete.get("fixture_events")
    if not isinstance(summarized, list) or streamed != summarized:
        return _row("source_coverage", "fail", "fixture_summary_mismatch")
    snapshots = {item["snapshot_id"] for item in manifest["case"]["fixtures"]}
    hit = False
    for sequence, event in enumerate(streamed, 1):
        if (not isinstance(event, dict) or set(event) not in (
                {"sequence", "status", "snapshot_id", "capability_id"},
                {"sequence", "status", "snapshot_id", "capability_id", "reason"})
                or type(event.get("sequence")) is not int or event["sequence"] != sequence
                or event.get("status") not in ("fixture_hit", "fixture_miss")):
            return _row("source_coverage", "fail", "invalid_fixture_observation")
        if event["status"] == "fixture_miss":
            return _row("source_coverage", "unknown", "fixture_miss")
        if (event.get("capability_id") != "fixture.read" or not isinstance(event.get("snapshot_id"), str)
                or event["snapshot_id"] not in snapshots):
            return _row("source_coverage", "fail", "fixture_reference_mismatch")
        hit = True
    return _row("source_coverage", "pass" if hit else "unknown",
                "fixture_read_observed" if hit else "source_read_unobserved", authorization="checked_separately_by_runner")


def _effects(events, complete, inventory, *, tools=_TOOLS, asset_reads=False, read_outcomes=False):
    calls, results, denials = {}, {}, []
    uncertain = False
    for event in events:
        if not _valid_event(event, asset_reads=asset_reads, read_outcomes=read_outcomes):
            uncertain = True
            continue
        kind = event.get("type")
        if kind in _EFFECTS or (kind == "native_system" and isinstance(event.get("subtype"), str)
                               and event["subtype"].startswith(("hook_", "task_"))):
            return _row("side_effects", "fail", "forbidden_side_effect_observed")
        if kind == "tool_call":
            identifier, name = event.get("id"), event.get("name")
            if not isinstance(identifier, str) or not identifier or not isinstance(name, str) or identifier in calls:
                uncertain = True
            else:
                calls[identifier] = name
        elif kind == "tool_result":
            identifier = event.get("id")
            if (not isinstance(identifier, str) or identifier in results or (type(event.get("is_error")) is not bool
                    and not (read_outcomes and 'is_error' in event and event['is_error'] is None))):
                uncertain = True
            elif identifier not in calls:
                uncertain = True
            else:
                results[identifier] = event["is_error"]
        elif kind == "tool_denied":
            denials.append(event)
    summary = complete.get("tool_denials") if complete else None
    if (not isinstance(summary, list) or any(not isinstance(item, dict) or item.get("type") != "tool_denied"
            or not _valid_event(item) for item in summary)):
        uncertain = True
        summary = []
    if any(denial not in summary for denial in denials):
        return _row("side_effects", "fail", "tool_denial_summary_mismatch")
    for identifier, name in calls.items():
        if name in tools:
            if identifier not in results:
                uncertain = True
            continue
        if results.get(identifier) is False:
            return _row("side_effects", "fail", "forbidden_tool_succeeded")
        matched = any(item.get("name") == name and item.get("tool_use_id", identifier) == identifier for item in summary)
        if results.get(identifier) is not True or not matched:
            uncertain = True
    if uncertain or complete is None or inventory["verdict"] != "pass":
        return _row("side_effects", "unknown", "tool_outcome_or_boundary_unobserved")
    return _row("side_effects", "pass", "recorded_tools_within_boundary")


def _completion(events, packets, complete):
    if any(packet.get("type") == "worker_error" for packet in packets) or any(event.get("type") == "error" for event in events):
        return _row("completion", "fail", "worker_or_engine_error")
    terminal = [event for event in events if event.get("type") == "terminal"]
    artifacts = [event for event in events if event.get("type") == "artifact"]
    if len(terminal) > 1 or len(artifacts) > 1:
        return _row("completion", "fail", "duplicate_terminal_or_artifact")
    if not terminal or complete is None:
        return _row("completion", "unknown", "terminal_or_worker_completion_missing")
    last = terminal[0]
    if last.get("is_error") is True or last.get("api_error_status") is not None or last.get("errors"):
        return _row("completion", "fail", "terminal_execution_error")
    if last.get("is_error") is not False or last.get("subtype") != "success" or last.get("artifact_status") != "observed" or not artifacts:
        return _row("completion", "unknown", "terminal_success_unverified")
    artifact = artifacts[0]
    try:
        valid_artifact = (isinstance(artifact.get("content"), str)
            and len(artifact["content"].encode("utf-8")) <= MAX_ASSET_BYTES and artifact.get("hash") == _sha(artifact["content"]))
    except UnicodeError:
        valid_artifact = False
    if not valid_artifact:
        return _row("completion", "fail", "artifact_hash_mismatch")
    if events[-1] is not last:
        return _row("completion", "fail", "events_after_terminal")
    return _row("completion", "pass", "terminal_artifact_and_worker_complete", output_hash=artifact["hash"])


def execution_invariants(request, manifest, workspace_receipt, packets, capability_hash, *, contract=None, read_decision=None) -> list[dict]:
    """Check trusted immutable host records; omitted full contract stays unknown.

    Pass means the supplied observations agree. It does not mean the filesystem,
    live authorization, model understanding, business quality, or pilot is proven.
    The current native profile never observes actual effort or semantic asset use.
    """
    try:
        request, manifest, workspace, packets = map(_frozen, (request, manifest, workspace_receipt, packets))
        _manifest(manifest)
        if request.get('version') == 4:
            from improvement_view_trial_protocol import validate_request_v4
            request = validate_request_v4(request)
            if manifest['version'] not in (2, 3, 4):
                raise ValueError('view_workspace_required')
        elif request.get("version") == 3:
            from improvement_preparation_protocol import validate_preparation_request_v3
            request = validate_preparation_request_v3(request)
        elif request.get("version") == 2:
            from improvement_experiment_protocol import validate_request_v2
            request = validate_request_v2(request)
            if request["variant"] != "baseline":
                raise ValueError("unsupported_experiment_candidate")
        else:
            _fields(request, {"version", "pins", "case_set_id", "case_id", "variant", "repeat", "engine_config",
                "baseline_context_hash", "target_generations", "deadline_at"}, {"qualification_id"})
        if request.get("version") != 3:
            CaseStore._pin_shape(request["pins"])
        if request['version'] != 4 and manifest['version'] not in (1, 5):
            raise ValueError('legacy_workspace_required')
        if manifest['version'] == 5 and request['variant'] != 'baseline':
            raise ValueError('native_baseline_variant_required')
        _digest(capability_hash)
        _fields(workspace, {"trial_id", "attempt", "path", "input_path", "output_root", "input_hash", "effective_hash"})
        if (type(request["version"]) is not int or request["version"] not in (1, 2, 3, 4) or request["variant"] not in ("baseline", "candidate")
                or type(workspace["attempt"]) is not int or workspace["attempt"] < 1 or not isinstance(workspace["trial_id"], str)
                or not _ID.fullmatch(workspace["trial_id"]) or not isinstance(packets, list) or len(packets) > 100000
                or any(not isinstance(packet, dict) for packet in packets)):
            raise ValueError("invalid_execution_records")
        engine, pins = request["engine_config"], request["pins"]
        for key in ("provider", "model", "reasoning"):
            if not isinstance(engine.get(key), str) or not engine[key]:
                raise ValueError("invalid_execution_configuration")
        native = None
        if manifest['version'] in (4, 5):
            from improvement_native_trace_checks import validate_native_trace
            from improvement_store import _json
            prompt = _json({'task': manifest['case']['task'], 'fixtures': [
                {key: item[key] for key in ('snapshot_id', 'source')} for item in manifest['case']['fixtures']]})
            native = validate_native_trace(packets, kind='trial', receipt=workspace, pin=engine,
                capability_hash=capability_hash, system_prompt=trial_system_prompt(manifest), user_prompt=prompt,
                data_hash=workspace['input_hash'], read_decision=read_decision,
                tool_policy='baseline_inline' if manifest['version'] == 5 else 'pinned_skill')
            packets = native['worker_bodies']
        elif any(packet.get('version') == 2 for packet in packets):
            raise ValueError('legacy_workspace_native_trace_mismatch')
    except (ValueError, TypeError, KeyError, AttributeError):
        return [_row("execution_records", "fail", "invalid_execution_records")]
    rows = [] if native is None else list(native['checks'])
    bundle = pins["base_bundle_hash" if request["variant"] == "baseline" else "candidate_bundle_hash"]
    expected = {"bundle_hash": bundle, "contract_hash": pins["contract_hash"], "engine_config_hash": _hash(engine),
                "grant_hash": pins["grant_hash"]}
    if request['version'] == 4:
        expected['effective_view'] = request['view']
    materialization = _equal("materialization", expected, manifest, "materialization_pin_mismatch")
    if (manifest["case"]["id"] != request["case_id"] or _hash(manifest["baseline_context"]) != request["baseline_context_hash"]
            or _hash(engine) != pins["engine_config_hash"]):
        materialization = _row("materialization", "fail", "case_context_or_configuration_mismatch")
    if (request['version'] == 4 and request['variant'] == 'candidate'
            and manifest['assets'][0]['id'] != request['lineage']['candidate_id']):
        materialization = _row('materialization', 'fail', 'candidate_identity_mismatch')
    rows.append(materialization)
    if contract is None:
        rows.append(_row("contract_projection", "unknown", "full_contract_unavailable"))
    else:
        try:
            contract = _frozen(contract)
            _contract(contract)
            matches = _hash(contract) == pins["contract_hash"] and public_contract(contract) == manifest["public_contract"]["content"]
            rows.append(_row("contract_projection", "pass" if matches else "fail",
                             "public_full_contract_match" if matches else "contract_projection_mismatch"))
        except (ValueError, TypeError):
            rows.append(_row("contract_projection", "fail", "invalid_full_contract"))
    try:
        path = Path(workspace["path"])
        valid_path = path.is_absolute() and ".." not in path.parts
        expected = {"input_hash": _hash(manifest), "effective_hash": _effective_hash(manifest),
                    "input_path": str(path / "input.json"), "output_root": str(path / "outputs")}
        row = _equal("workspace_binding", expected, workspace, "workspace_record_mismatch")
        rows.append(row if valid_path else _row("workspace_binding", "fail", "workspace_path_record_invalid"))
    except (TypeError, ValueError):
        rows.append(_row("workspace_binding", "fail", "workspace_path_record_invalid"))
    rows.append(_protocol(packets, workspace, capability_hash) if native is None else
        _row('worker_protocol', 'pass', 'native_worker_protocol_complete'))
    events = [packet["event"] for packet in packets if packet.get("type") == "engine_event" and isinstance(packet.get("event"), dict)]
    completes = [packet for packet in packets if packet.get("type") == "worker_complete"]
    complete = completes[0] if len(completes) == 1 else None
    receipt, installation = _receipt(events, workspace, manifest, request, capability_hash)
    rows.append(installation)
    inits = [event for event in events if event.get("type") == "native_system" and event.get("subtype") == "init"]
    inventory = _inventory(receipt, inits, _tools(manifest))
    rows.append(inventory)
    expected_prompt = _sha(trial_system_prompt(manifest))
    if not receipt or receipt.get("system_prompt_hash") is None or receipt["coverage"]["prompt"] != "host_attested":
        rows.append(_row("prompt_installation", "unknown", "prompt_selection_unobserved"))
    else:
        rows.append(_row("prompt_installation", "pass" if receipt["system_prompt_hash"] == expected_prompt else "fail",
                         "prompt_attested" if receipt["system_prompt_hash"] == expected_prompt else "prompt_hash_mismatch"))
    expected_assets = [{key: item[key] for key in ("id", "path", "hash")} for item in manifest["assets"]]
    if not receipt:
        rows.append(_row("asset_installation", "unknown", "revision_installation_unobserved"))
    else:
        assets = receipt.get("asset_revisions")
        valid = (isinstance(assets, list) and all(isinstance(item, dict) and set(item) == {
            "id", "path", "hash", "available", "selected", "observed_use"} for item in assets))
        if not valid or [{key: item[key] for key in ("id", "path", "hash")} for item in assets] != expected_assets:
            rows.append(_row("asset_installation", "fail", "revision_inventory_mismatch"))
        elif any(item["available"] is not True or item["selected"] is not True for item in assets):
            rows.append(_row("asset_installation", "unknown", "revision_availability_or_selection_unobserved"))
        else:
            rows.append(_row("asset_installation", "pass", "exact_revisions_available_and_selected"))
    rows.append(_asset_use(manifest, workspace, events, receipt))
    rows.append(_row("actual_reasoning", "fail" if receipt and receipt["actual_reasoning"] not in (None, engine["reasoning"]) else "unknown",
                     "actual_reasoning_mismatch" if receipt and receipt["actual_reasoning"] not in (None, engine["reasoning"]) else "native_reasoning_unobserved"))
    context_known = manifest["baseline_context"]["coverage"] == "complete" and receipt and receipt["coverage"]["context"] == "complete"
    rows.append(_row("context_coverage", "pass" if context_known else "unknown",
                     "complete_context_declared_and_installed" if context_known else "context_coverage_unknown"))
    rows.append(_row("fixture_inventory", installation["verdict"], installation["reason"]))
    rows.append(_sources(manifest, packets, complete))
    observations = [event.get("model") for event in events if event.get("type") == "observation" and event.get("model")]
    if any(model != engine["model"] for model in observations):
        rows.append(_row("actual_model", "fail", "actual_model_mismatch"))
    elif not observations or not receipt or receipt["coverage"]["model"] != "observed":
        rows.append(_row("actual_model", "unknown", "actual_model_unobserved"))
    elif receipt["actual_models"] != [engine["model"]] or any(event.get("actual_models") != [engine["model"]]
            for event in events if event.get("type") == "terminal"):
        rows.append(_row("actual_model", "fail", "model_observation_summary_mismatch"))
    else:
        rows.append(_row("actual_model", "pass", "exact_model_observed"))
    session_ids = [event.get("session_id") for event in events if event.get("type") in ("terminal", "usage", "observation")]
    init_sessions = [item["data"].get("session_id") for item in inits if isinstance(item.get("data"), dict)]
    session_ids += init_sessions
    observed_sessions = {item for item in session_ids if isinstance(item, str) and item}
    if len(observed_sessions) > 1 or (receipt and observed_sessions and receipt.get("session_id") not in observed_sessions):
        rows.append(_row("session_binding", "fail", "native_session_mismatch"))
    elif (not receipt or not observed_sessions or len(init_sessions) != 1
            or not isinstance(init_sessions[0], str) or not init_sessions[0] or not receipt.get("session_id")):
        rows.append(_row("session_binding", "unknown", "native_session_unobserved"))
    else:
        rows.append(_row("session_binding", "pass", "single_native_session_bound"))
    rows.append(_effects(events, complete, inventory, tools=_tools(manifest), asset_reads=manifest['version'] == 3,
        read_outcomes=manifest['version'] == 4))
    completion = _completion(events, packets, complete)
    if native is not None and any(row['verdict'] != 'pass' for row in native['checks'] if row['id'] == 'native_authorization'):
        completion = _row('completion', 'unknown', 'native_durable_allow_unverified')
    rows.append(completion)
    known = all(_valid_event(event, asset_reads=manifest['version'] == 3, read_outcomes=manifest['version'] == 4) for event in events)
    known = known and all(isinstance(packet.get("event"), dict) for packet in packets if packet.get("type") in ("engine_event", "fixture_event"))
    rows.append(_row("event_coverage", "pass" if known else "unknown", "known_event_shapes" if known else "unrecognized_event"))
    return rows
