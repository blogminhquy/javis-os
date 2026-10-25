"""Closed host-issued role request metadata, never model or HTTP authority."""
from improvement_experiment_protocol import _freeze, _id, _digest
from improvement_store import _hash, _json
from improvement_blobs import MAX_ASSET_BYTES

_FIELDS = {"version", "experiment_id", "context_id", "definition_hash", "kind", "role", "purpose",
           "candidate_id", "parent_id", "input_hash"}
_ROLES = {"propose": ("improver", "improve_propose"), "repair": ("improver", "improve_propose"),
          "semantic": ("semantic_reviewer", "improve_evaluate"), "compose": ("composer", "improve_compose")}


def operation_request(value):
    value = _freeze(value)
    if type(value) is not dict:
        raise ValueError("invalid_operation_request")
    composed = value.get('kind') == 'compose'
    if set(value) != (_FIELDS | {'compose_authorization_id'} if composed else _FIELDS):
        raise ValueError("invalid_operation_request")
    if (type(value["version"]) is not int or value["version"] != (2 if composed else 1)
            or type(value["kind"]) is not str or value["kind"] not in _ROLES
            or (value["role"], value["purpose"]) != _ROLES[value["kind"]]):
        raise ValueError("invalid_operation_role")
    for key in ("experiment_id", "context_id"):
        _id(value[key])
    for key in ("definition_hash", "input_hash"):
        _digest(value[key])
    if composed:
        _id(value['compose_authorization_id'])
    for key, required in (("candidate_id", value["kind"] == "semantic"), ("parent_id", value["kind"] == "repair")):
        if required:
            _id(value[key])
        elif value[key] is not None:
            raise ValueError("invalid_operation_identity")
    return value


def operation_materialization(value):
    """Actual operation input, distinct from solver bundles and Trial manifests."""
    value = _freeze(value)
    if type(value) is not dict or set(value) != {
            "version", "brain_id", "operation_id", "request", "engine_config_hash", "data", "learning_origin"}:
        raise ValueError("invalid_operation_materialization")
    if (type(value["version"]) is not int or value["version"] not in (1, 2) or value["learning_origin"] != "compose"
            or type(value["brain_id"]) is not str or not 1 <= len(value["brain_id"]) <= 1000 or "\x00" in value["brain_id"]
            or type(value["data"]) is not dict):
        raise ValueError("invalid_operation_materialization")
    _id(value["operation_id"])
    _digest(value["engine_config_hash"])
    request = operation_request(value["request"])
    if request['kind'] == 'compose' and value['version'] != 2:
        raise ValueError('compose_native_input2_required')
    if _hash(value["data"]) != request["input_hash"]:
        raise ValueError("operation_input_changed")
    if len(_json(value["data"]).encode("utf-8")) > MAX_ASSET_BYTES:
        raise ValueError("operation_input_too_large")
    from evidence_store import redact
    if redact(value) != value:
        raise ValueError("operation_input_contains_credentials")
    return value


def operation_packet(value):
    """Bounded real worker envelope; native event payloads remain raw evidence."""
    packet = _freeze(value)
    if type(packet) is not dict:
        raise ValueError("invalid_operation_worker_packet")
    kind = packet.get("type")
    if kind == "worker_error":
        fields = {"version", "sequence", "type", "reason", "error_type"}
        for key in ("reason", "error_type"):
            if type(packet.get(key)) is not str or not 1 <= len(packet[key]) <= 1000:
                raise ValueError("invalid_operation_worker_packet")
    else:
        extras = {"worker_ready": {"capability_hash"}, "engine_start_requested": set(),
                  "engine_event": {"event"}, "worker_complete": {"tool_denials"}}
        if type(kind) is not str or kind not in extras:
            raise ValueError("invalid_operation_worker_packet")
        fields = {"version", "sequence", "type", "operation_id", "attempt", "role", "purpose", "input_hash", *extras[kind]}
        _id(packet.get("operation_id"))
        _digest(packet.get("input_hash"))
        if (type(packet.get("attempt")) is not int or packet["attempt"] not in (1, 2)
                or (packet.get("role"), packet.get("purpose")) not in _ROLES.values()):
            raise ValueError("invalid_operation_worker_identity")
        if kind == "worker_ready":
            _digest(packet.get("capability_hash"))
        if kind == "engine_event" and (type(packet.get("event")) is not dict
                or type(packet["event"].get("type")) is not str or not 1 <= len(packet["event"]["type"]) <= 128):
            raise ValueError("invalid_operation_engine_event")
        if kind == "worker_complete" and type(packet.get("tool_denials")) is not list:
            raise ValueError("invalid_operation_worker_packet")
    if (set(packet) != fields or type(packet.get("version")) is not int or packet["version"] != 1
            or type(packet.get("sequence")) is not int or not 1 <= packet["sequence"] < 2 ** 63):
        raise ValueError("invalid_operation_worker_packet")
    raw = _json(packet).encode("utf-8")
    if len(raw) > 8 * MAX_ASSET_BYTES:
        raise ValueError("operation_worker_packet_too_large")
    return packet, raw
