"""Pure grammar for durable host packet2 observations; no execution authority.

observation_binding(first_packet, *, kind, receipt) derives a lexical binding
from the first projected guardian offer and receipt identity. validate_observation2
returns a defensive snapshot. encode_observation2/decode_observation2 use canonical
UTF8 storage JSON, without a wire length prefix; both take the same binding and
expected_sequence/expected_source_sequence keywords as the validator.

The caller owns source authentication, stored workspace/receipt validation,
per-source/global counters, actual peers/incarnations and current lease authority.
offer_hash is lexical only: the full raw capability offer is deliberately absent.
An image_observed record never proves an allow ACK. No cross-source phase order,
image authorization, loaded-section identity or native execution is inferred.
"""
from __future__ import annotations

import hashlib
import json
import re

import improvement_native_protocol as _protocol

MAX_OBSERVATION_BYTES = _protocol.MAX_PRIVATE_BYTES
_ENVELOPE = {'version', 'sequence', 'source', 'source_sequence', 'launch_nonce', 'worker_pid', 'worker_birth', 'body'}
_OFFER = {'type', 'worker_tid', 'worker_thread_birth', 'root_image', 'bootstrap_count', 'images', 'offer_hash'}
_IMAGE = {'type', 'purpose', 'nonce', 'native_pid', 'native_birth', 'native_tid', 'native_thread_birth',
    'comparison', 'source_worker_incarnation_verified', 'exact_outer_job', 'association_basis', 'observation_hash'}


def _invalid():
    raise ValueError('invalid_native_observation')


def _envelope(value):
    _protocol._tree(value)
    _protocol._fields(value, _ENVELOPE)
    if (type(value['version']) is not int or value['version'] != 2 or type(value['source']) is not str
            or value['source'] not in ('guardian', 'worker')): _invalid()
    _protocol._uint(value['sequence'], 63); _protocol._uint(value['source_sequence'], 63)
    _protocol._digest(value['launch_nonce']); _protocol._uint(value['worker_pid'], 32)
    _protocol._uint(value['worker_birth'])
    if type(value['body']) is not dict or type(value['body'].get('type')) is not str: _invalid()


def _binding(value):
    _protocol._binding(value)
    if value['kind'] not in ('trial', 'operation'): _invalid()
    if any(item['nonce'] == value['launch_nonce'] for item in value['invocations']): _invalid()


def _comparison(value):
    _protocol._fields(value, {'matches', 'selected', 'actual', 'proof_basis', 'metadata_mutation_exclusion',
        'debug_event_origin', 'loaded_image_identity', 'comprehension'})
    if type(value['matches']) is not bool: _invalid()
    for name in ('selected', 'actual'):
        item = value[name]
        _protocol._fields(item, {'volume_serial_64', 'file_id_128', 'sha256', 'size'})
        _protocol._uint(item['volume_serial_64']); _protocol._digest(item['sha256'])
        if (type(item['file_id_128']) is not str or re.fullmatch('[0-9a-f]{32}', item['file_id_128']) is None
                or type(item['size']) is not int or not 0 < item['size'] <= 512 * 1024 * 1024): _invalid()
    if (value['matches'] != (value['selected'] == value['actual']) or type(value['proof_basis']) is not str
            or value['proof_basis'] != 'observed_borrowed_file_identity_and_reopened_sha256'
            or any(type(value[key]) is not str or value[key] != 'unknown' for key in
                ('metadata_mutation_exclusion', 'debug_event_origin', 'loaded_image_identity', 'comprehension'))): _invalid()


def _offer(body, *, kind, launch_nonce):
    _protocol._fields(body, _OFFER)
    _protocol._uint(body['worker_tid'], 32); _protocol._uint(body['worker_thread_birth'])
    _protocol._digest(body['offer_hash']); _comparison(body['root_image'])
    if type(body['bootstrap_count']) is not int or body['bootstrap_count'] != 1: _invalid()
    _protocol._invocations(kind, body['images'], shares=False)
    if any(item['nonce'] == launch_nonce for item in body['images']): _invalid()


def _guardian(value, binding):
    body, kind = value['body'], value['body']['type']
    if kind == 'launch_offer':
        if value['sequence'] != 1 or value['source_sequence'] != 1: _invalid()
        _offer(body, kind=binding['kind'], launch_nonce=binding['launch_nonce'])
        if body['images'] != binding['invocations']: _invalid()
    elif kind == 'stdio_sealed':
        _protocol._fields(body, {'type', 'all_data_pipes_closed'})
        if body['all_data_pipes_closed'] is not True: _invalid()
    elif kind == 'image_observed':
        _protocol._fields(body, _IMAGE)
        _comparison(body['comparison']); _protocol._digest(body['observation_hash'])
        if (type(body['purpose']) is not str or type(body['nonce']) is not str
                or not any(body['purpose'] == item['purpose'] and body['nonce'] == item['nonce']
                           for item in binding['invocations'])
                or body['source_worker_incarnation_verified'] is not True or body['exact_outer_job'] is not True
                or type(body['association_basis']) is not str
                or body['association_basis'] != 'qualified_worker_create_capture_and_guardian_object_checks'): _invalid()
        for key in ('native_pid', 'native_tid'): _protocol._uint(body[key], 32)
        for key in ('native_birth', 'native_thread_birth'): _protocol._uint(body[key])
        material = {key: value[key] for key in ('launch_nonce', 'worker_pid', 'worker_birth')}
        material.update({key: item for key, item in body.items() if key not in ('type', 'observation_hash')})
        # The actual guardian wire/hash recipe is ASCII JSON, unlike storage's
        # UTF8 JSON. Neither host sequence nor source sequence is in this hash.
        raw = json.dumps(material, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False).encode('ascii')
        if hashlib.sha256(raw).hexdigest() != body['observation_hash']: _invalid()
    elif kind == 'drained':
        _protocol._fields(body, {'type', 'root_terminal', 'debug_exit', 'job_active', 'guards_closed', 'reason'})
        if (any(body[key] is not True for key in ('root_terminal', 'debug_exit', 'guards_closed'))
                or type(body['job_active']) is not int or body['job_active'] != 0 or type(body['reason']) is not str
                or body['reason'] not in ('completed', 'host_stop', 'image_denied', 'cancelled', 'refused')): _invalid()
    else: _invalid()


def observation_binding(first_packet, *, kind, receipt):
    """Derive grammar/identity only; the first offer is not peer authority."""
    if type(kind) is not str or kind not in ('trial', 'operation'): _invalid()
    _envelope(first_packet); _protocol._tree(receipt)
    if (first_packet['sequence'] != 1 or first_packet['source_sequence'] != 1
            or first_packet['source'] != 'guardian' or first_packet['body']['type'] != 'launch_offer'): _invalid()
    _offer(first_packet['body'], kind=kind, launch_nonce=first_packet['launch_nonce'])
    binding = {key: first_packet[key] for key in ('launch_nonce', 'worker_pid', 'worker_birth')}
    binding.update(kind=kind, identity=_protocol._identity(kind, receipt), invocations=first_packet['body']['images'])
    validate_observation2(first_packet, binding=binding, expected_sequence=1, expected_source_sequence=1)
    return _protocol._parse(_protocol._canonical(binding))


def validate_observation2(value, *, binding, expected_sequence, expected_source_sequence):
    """Check caller-supplied counters independently; do not infer phase order."""
    _binding(binding); _envelope(value)
    _protocol._uint(expected_sequence, 63); _protocol._uint(expected_source_sequence, 63)
    if value['sequence'] != expected_sequence or value['source_sequence'] != expected_source_sequence: _invalid()
    for key in ('launch_nonce', 'worker_pid', 'worker_birth'):
        if type(value[key]) is not type(binding[key]) or value[key] != binding[key]: _invalid()
    if value['sequence'] == 1 and (value['source'] != 'guardian' or value['body']['type'] != 'launch_offer'): _invalid()
    if value['source'] == 'guardian':
        _guardian(value, binding)
    else:
        wire = {key: value[key] for key in ('version', 'launch_nonce', 'worker_pid', 'worker_birth', 'body')}
        wire['sequence'] = value['source_sequence']
        _protocol.validate_private_packet2(wire, binding=binding, direction='worker', expected_sequence=expected_source_sequence)
    return _protocol._parse(_protocol._canonical(value))


def encode_observation2(value, *, binding, expected_sequence, expected_source_sequence):
    return _protocol._canonical(validate_observation2(value, binding=binding,
        expected_sequence=expected_sequence, expected_source_sequence=expected_source_sequence))


def decode_observation2(raw, *, binding, expected_sequence, expected_source_sequence):
    return validate_observation2(_protocol._parse(raw), binding=binding,
        expected_sequence=expected_sequence, expected_source_sequence=expected_source_sequence)
