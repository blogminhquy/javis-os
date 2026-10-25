"""Pure checks of genuine role records; never semantic or live authority."""
from __future__ import annotations

import hashlib

from improvement_operation_protocol import operation_materialization, operation_packet
from improvement_operation_profile import RECEIPT_FIELDS, operation_system_prompt, operation_user_prompt
from improvement_store import _hash, _json
from improvement_trial_checks import _row, _inventory, _effects, _completion


def _sha(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def execution_checks(pin, manifest, workspace, packets, capability, *, read_decision=None):
    try:
        manifest = operation_materialization(manifest)
        if type(packets) is not list or not 1 <= len(packets) <= 100000:
            raise ValueError("invalid_operation_trace")
        native = None
        if manifest['version'] == 2:
            from improvement_native_trace_checks import validate_native_trace
            native = validate_native_trace(packets, kind='operation', receipt=workspace, pin=pin,
                capability_hash=capability, system_prompt=operation_system_prompt(manifest), user_prompt=operation_user_prompt(manifest),
                data_hash=manifest['request']['input_hash'], read_decision=read_decision)
            packets = native['worker_bodies']
        else:
            packets = [operation_packet(packet)[0] for packet in packets]
        expected = {"operation_id": manifest["operation_id"], "role": manifest["request"]["role"],
                    "purpose": manifest["request"]["purpose"], "request_hash": _hash(manifest["request"]),
                    "input_hash": _sha(_json(manifest))}
        valid = (manifest["engine_config_hash"] == _hash(pin)
                 and all(workspace.get(key) == value for key, value in expected.items()))
        rows = ([] if native is None else list(native['checks'])) + [_row("materialization", "pass" if valid else "fail", "record_pins_match" if valid else "materialization_pin_mismatch")]
        state, failure = "starting", None
        identity = {key: workspace[key] for key in ("operation_id", "attempt", "role", "purpose", "input_hash")}
        for sequence, packet in enumerate(packets if native is None else [], 1):
            kind = packet["type"]
            if (kind == "worker_error" or packet["sequence"] != sequence
                    or _json({key: packet.get(key) for key in identity}) != _json(identity)):
                failure = "worker_identity_sequence_or_error"
                break
            if kind == "worker_ready" and state == "starting" and packet["capability_hash"] == capability:
                state = "ready"
            elif kind == "engine_start_requested" and state == "ready":
                state = "running"
            elif kind == "engine_event" and state == "running":
                pass
            elif kind == "worker_complete" and state == "running":
                state = "complete"
            else:
                failure = "worker_event_order_mismatch"
                break
        if native is not None: state = 'complete'
        rows.append(_row("worker_protocol", "fail" if failure else "pass" if state == "complete" else "unknown",
                         failure or ("worker_protocol_complete" if state == "complete" else "worker_protocol_incomplete")))
        events = [packet["event"] for packet in packets if packet["type"] == "engine_event"]
        complete = packets[-1] if packets[-1]["type"] == "worker_complete" else None
        receipts = [event for event in events if event.get("type") == "operation_installation_receipt"]
        receipt = receipts[0].get("receipt") if len(receipts) == 1 else None
        installation = _row("installation", "unknown" if not receipts else "fail", "missing_or_ambiguous_operation_receipt")
        if receipt is not None:
            expected_receipt = {**identity, "version": 2 if native is not None else 1, "request_hash": _hash(manifest["request"]),
                "data_hash": manifest["request"]["input_hash"], "engine_config_hash": _hash(pin), "capability_hash": capability,
                "expected_system_prompt_hash": _sha(operation_system_prompt(manifest)),
                "system_prompt_hash": _sha(operation_system_prompt(manifest)), "user_prompt_hash": _sha(operation_user_prompt(manifest)),
                "tool_inventory_hash": _hash(["mcp__fixture__fixture_read"]),
                "requested": {key: pin[key] for key in ("provider", "model", "reasoning")}}
            coverage = receipt.get("coverage") if type(receipt) is dict else None
            valid = (type(receipt) is dict and set(receipt) == RECEIPT_FIELDS | ({'native_input_delivery'} if native is not None else set())
                and type(receipt.get("version")) is int and type(receipt.get("attempt")) is int
                and type(receipt.get("session_id")) is str and 1 <= len(receipt["session_id"]) <= 1000
                and receipts[0].get("hash") == _hash(receipt)
                and all(_json(receipt.get(key)) == _json(value) for key, value in expected_receipt.items())
                and type(coverage) is dict and set(coverage) == {"input", "prompt", "tool_inventory", "model", "reasoning"}
                and coverage["input"] == "host_verified" and coverage["prompt"] == "host_attested")
            installation = _row("installation", "pass" if valid else "fail", "operation_pins_match" if valid else "operation_receipt_mismatch")
        rows.append(installation)
        inits = [event for event in events if event.get("type") == "native_system" and event.get("subtype") == "init"]
        inventory = _inventory(receipt, inits)
        rows.append(inventory)
        # These existing pure checks do not require or invent a Trial identity.
        boundary_events = [event for event in events if event.get("type") != "operation_installation_receipt"]
        rows.extend((_effects(boundary_events, complete, inventory), _completion(events, packets, complete)))
        if native is not None and any(row['verdict'] != 'pass' for row in native['checks'] if row['id'] == 'native_authorization'):
            rows[-1] = _row('completion', 'unknown', 'native_durable_allow_unverified')
        observations = [event for event in events if event.get("type") == "observation"]
        terminals = [event for event in events if event.get("type") == "terminal"]
        models = [event.get("model") for event in observations]
        model = "unknown" if not receipt or not models or any(value is None for value in models) else (
            "pass" if models and set(models) == {pin["model"]} and receipt.get("actual_models") == [pin["model"]]
            and terminals and all(event.get("actual_models") == [pin["model"]] for event in terminals)
            and receipt.get("coverage", {}).get("model") == "observed" else "fail")
        rows.append(_row("actual_model", model, "native_model_records_match" if model == "pass" else "native_model_missing_or_mismatched"))
        reasoning_mismatch = bool(receipt and receipt.get("actual_reasoning") not in (None, pin["reasoning"]))
        rows.append(_row("actual_reasoning", "fail" if reasoning_mismatch else "unknown",
                         "native_reasoning_mismatch" if reasoning_mismatch else "native_reasoning_unobserved"))
        sessions = {event.get("session_id") for event in events if event.get("type") in ("observation", "terminal", "usage")
                    and event.get("session_id") is not None}
        init_sessions = [event.get("data", {}).get("session_id") for event in inits]
        valid_sessions = bool(receipt and len(sessions) == 1 and len(init_sessions) == 1
                              and type(init_sessions[0]) is str and init_sessions[0]
                              and sessions == {init_sessions[0]} == {receipt.get("session_id")})
        rows.append(_row("native_session", "pass" if valid_sessions else "unknown" if not receipt or not sessions or not init_sessions else "fail",
                         "native_session_records_match" if valid_sessions else "native_session_missing_or_mismatched"))
        rows.append(_row("actual_input_use", "unknown", "semantic_input_use_unobserved"))
        return rows
    except (ValueError, TypeError, KeyError, AttributeError):
        return [_row("execution_records", "fail", "invalid_operation_execution_records")]
