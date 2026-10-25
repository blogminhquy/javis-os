"""Encrypted observation2 history checks shared by the two existing owners.

No schema, lease or completion authority lives here. Late gaps remain gaps, and
late completion/drain never closes an active successful trace. Legacy target reads
retain their existing semantics; they do not newly authenticate an entire history
that was injected through SQL outside these append owners.
"""
import hashlib

import improvement_store as IM
from improvement_blobs import AssetUnavailable
from improvement_native_observation import observation_binding, validate_observation2
from improvement_native_protocol import _canonical, _parse


def is_observation2(value):
    return type(value) is dict and type(value.get('version')) is int and value['version'] == 2


def candidate(value):
    raw = _canonical(value)
    packet = _parse(raw)
    if (not is_observation2(packet) or type(packet.get('sequence')) is not int
            or not 1 <= packet['sequence'] < 2 ** 63 or type(packet.get('body')) is not dict
            or type(packet['body'].get('type')) is not str):
        raise ValueError('invalid_native_trace_packet')
    return packet, raw


def reject_v2_history(rows, decode):
    # V1 serialization/validation is intentionally unchanged. Only detect the
    # newly forbidden version mix, including before returning a V1 replay.
    for row in rows:
        if is_observation2(decode(row)):
            raise IM.ConflictError('native_trace_version_mixed')


def validate_history(rows, decode, *, kind, receipt, incoming=None, raw=None, late=False, selected=None):
    """Validate one packet at a time; never retain the full decrypted stream.

    Incoming late packets may fill gaps if both global and per-source order stay
    strict. Source counters never infer authorization or cross-source phase order.
    """
    metadata = {row['sequence']: row for row in rows}
    replay = metadata.get(incoming['sequence']) if incoming is not None else None
    if replay is not None and replay['payload_hash'] != hashlib.sha256(raw).hexdigest():
        raise IM.ConflictError('native_trace_payload_conflict')
    sequence = sorted(set(metadata) | ({incoming['sequence']} if incoming is not None else set()))
    if not sequence or sequence[0] != 1 or receipt is None:
        raise IM.ConflictError('native_trace_binding_anchor_missing')
    binding = None
    last, sources, frozen, result = 0, {'guardian': 0, 'worker': 0}, False, None
    for number in sequence:
        row = metadata.get(number)
        stored = row is not None
        value = decode(row) if stored else incoming
        if not is_observation2(value):
            raise IM.ConflictError('native_trace_version_mixed')
        try:
            actual_raw = _canonical(value)
            if stored and (hashlib.sha256(actual_raw).hexdigest() != row['payload_hash']
                    or type(row['late']) is not int or row['late'] not in (0, 1)
                    or value.get('sequence') != number):
                raise AssetUnavailable('native_trace_metadata_mismatch')
            if number == 1:
                binding = observation_binding(value, kind=kind, receipt=receipt)
            source = value.get('source')
            if source not in sources: raise ValueError('invalid_native_trace_source')
            is_late = bool(row['late']) if stored else late
            if number <= last or (not is_late and number != last + 1):
                raise IM.ConflictError('native_trace_sequence_gap')
            source_number = value.get('source_sequence')
            if (type(source_number) is not int or source_number <= sources[source]
                    or (not is_late and source_number != sources[source] + 1)):
                raise IM.ConflictError('native_trace_source_sequence_gap')
            packet = validate_observation2(value, binding=binding,
                expected_sequence=number, expected_source_sequence=source_number)
            if stored and row['kind'] != packet['body']['type']:
                raise AssetUnavailable('native_trace_metadata_mismatch')
            if frozen and not is_late: raise IM.ConflictError('native_trace_frozen')
            if not is_late and source == 'guardian' and packet['body']['type'] == 'drained': frozen = True
            last, sources[source] = number, source_number
            if number == selected: result = packet
        except (ValueError, TypeError, KeyError) as error:
            if stored: raise AssetUnavailable('native_trace_history_unavailable') from error
            raise
    return result
