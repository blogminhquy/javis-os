"""Closed private startup/wire grammar; no I/O or execution authority.

The host authenticates source, runtime, environment and retained incarnations.
This module checks bounded serialization and binding only. Dispatch proof meaning,
actual socket provenance, phase order and durable ACK authority remain consumers'
responsibility. Guardian metadata never uses this private data channel.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import json
import math
import re
import struct

MAX_PRIVATE_BYTES = 8 * 1024 * 1024
_PURPOSES = ('adapter_version', 'auth_status', 'sdk_version', 'query')
_ENV_PATHS = frozenset(('PATH', 'HOME', 'USERPROFILE', 'TEMP', 'TMP', 'JAVIS_STATE_DIR',
    'BRAINS_DIR', 'OBSIDIAN_VAULT_PATH', 'BRAIN_PATH', 'SOURCES_PATH', 'APPDATA', 'LOCALAPPDATA'))
_ENV_FIXED = {'ENABLE_TOOL_SEARCH': 'false', 'DISABLE_TELEMETRY': '1', 'DISABLE_ERROR_REPORTING': '1',
    'DISABLE_NON_ESSENTIAL_MODEL_CALLS': '1', 'CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC': '1', 'PYTHONIOENCODING': 'utf-8'}
_ENV_OPTIONAL = frozenset(('SYSTEMROOT', 'WINDIR', 'COMSPEC', 'PATHEXT'))


def _invalid():
    raise ValueError('invalid_private_native_protocol')


def _fields(value, fields):
    if type(value) is not dict or any(type(key) is not str for key in value) or set(value) != set(fields):
        _invalid()


def _text(value, maximum=32768):
    if type(value) is not str or not value or len(value) > maximum or '\x00' in value:
        _invalid()


def _digest(value):
    if type(value) is not str or re.fullmatch('[0-9a-f]{64}', value) is None:
        _invalid()


def _uint(value, bits=64):
    if type(value) is not int or not 0 < value < (1 << bits):
        _invalid()


def _tree(value, depth=0, budget=None):
    # Reject builtin subclasses before copying can erase equality hooks.
    if budget is None: budget = [131072]
    budget[0] -= 1
    if depth > 32 or budget[0] < 0: _invalid()
    kind = type(value)
    if kind is dict:
        if any(type(key) is not str for key in value): _invalid()
        for key, item in value.items():
            if len(key) > 32768: _invalid()
            _tree(item, depth + 1, budget)
    elif kind is list:
        for item in value: _tree(item, depth + 1, budget)
    elif kind is str:
        if len(value) > MAX_PRIVATE_BYTES: _invalid()
    elif kind is int:
        if not -(1 << 64) < value < (1 << 64): _invalid()
    elif kind is float:
        if not math.isfinite(value): _invalid()
    elif value is not None and kind is not bool:
        _invalid()


def _canonical(value):
    _tree(value)
    try:
        raw = json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode('utf-8')
    except (ValueError, TypeError, UnicodeError, RecursionError):
        _invalid()
    if not 0 < len(raw) <= MAX_PRIVATE_BYTES: _invalid()
    return raw


def _parse(raw):
    if type(raw) is not bytes or not 0 < len(raw) <= MAX_PRIVATE_BYTES: _invalid()
    # Bound structural depth before invoking the recursive JSON decoder.
    quoted = escaped = False
    depth = 0
    for char in raw:
        if quoted:
            if escaped: escaped = False
            elif char == 92: escaped = True
            elif char == 34: quoted = False
        elif char == 34: quoted = True
        elif char in (123, 91):
            depth += 1
            if depth > 33: _invalid()
        elif char in (125, 93):
            depth -= 1
            if depth < 0: _invalid()
    if quoted or depth: _invalid()
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result: _invalid()
            result[key] = value
        return result
    def integer(value):
        if len(value.lstrip('-')) > 20: _invalid()
        return int(value)
    def reject(value): _invalid()
    try:
        result = json.loads(raw.decode('utf-8'), object_pairs_hook=pairs, parse_int=integer, parse_constant=reject)
    except (ValueError, UnicodeError, RecursionError):
        _invalid()
    if _canonical(result) != raw: _invalid()
    return result


def _share(value):
    _text(value, 4096)
    try:
        raw = base64.b64decode(value, validate=True)
    except (ValueError, binascii.Error):
        _invalid()
    if not raw or base64.b64encode(raw).decode('ascii') != value: _invalid()


def _identity(kind, receipt):
    keys = ('trial_id', 'attempt', 'input_hash') if kind == 'trial' else ('operation_id', 'attempt', 'role', 'purpose', 'input_hash')
    if type(receipt) is not dict or any(key not in receipt for key in keys): _invalid()
    identity = {key: receipt[key] for key in keys}
    _digest(identity['input_hash'])
    identifier = identity['trial_id' if kind == 'trial' else 'operation_id']
    if type(identifier) is not str or re.fullmatch('[a-zA-Z0-9][a-zA-Z0-9_-]{0,127}', identifier) is None: _invalid()
    if type(identity['attempt']) is not int or not 1 <= identity['attempt'] < (1 << 63): _invalid()
    if kind == 'operation':
        if identity['attempt'] not in (1, 2) or (identity['role'], identity['purpose']) not in (
                ('improver', 'improve_propose'), ('semantic_reviewer', 'improve_evaluate'),
                ('composer', 'improve_compose')): _invalid()
    return identity


def _invocations(kind, values, *, shares):
    purposes = _PURPOSES[:2] if kind == 'preflight' else _PURPOSES
    if type(values) is not list or len(values) != len(purposes): _invalid()
    nonces = set()
    for purpose, item in zip(purposes, values):
        _fields(item, {'purpose', 'nonce', 'share'} if shares else {'purpose', 'nonce'})
        if type(item['purpose']) is not str or item['purpose'] != purpose: _invalid()
        _digest(item['nonce'])
        if item['nonce'] in nonces: _invalid()
        nonces.add(item['nonce'])
        if shares: _share(item['share'])


def validate_startup2(value):
    _tree(value)
    _fields(value, {'version', 'type', 'kind', 'launch_nonce', 'worker_pid', 'worker_birth',
                    'private_share', 'images', 'request', 'environment'})
    if (type(value['version']) is not int or value['version'] != 2 or type(value['type']) is not str
            or value['type'] != 'startup2' or type(value['kind']) is not str
            or value['kind'] not in ('trial', 'operation', 'preflight')): _invalid()
    _digest(value['launch_nonce']); _uint(value['worker_pid'], 32); _uint(value['worker_birth'])
    _share(value['private_share']); _invocations(value['kind'], value['images'], shares=True)
    request = value['request']
    _fields(request, {'version', 'config_pin'} if value['kind'] == 'preflight' else {
        'version', 'config_pin', 'workspace_root', 'receipt', 'capability_hash'})
    if type(request['version']) is not int or request['version'] != 1 or type(request['config_pin']) is not dict: _invalid()
    if value['kind'] != 'preflight':
        _text(request['workspace_root']); _digest(request['capability_hash']); _identity(value['kind'], request['receipt'])
    environment = value['environment']
    if (type(environment) is not dict or not _ENV_PATHS | _ENV_FIXED.keys() <= environment.keys()
            or not environment.keys() <= _ENV_PATHS | _ENV_FIXED.keys() | _ENV_OPTIONAL): _invalid()
    for key, item in environment.items():
        _text(item)
        if key in _ENV_FIXED and item != _ENV_FIXED[key]: _invalid()
    return _parse(_canonical(value))


def encode_startup2(value):
    raw = _canonical(validate_startup2(value)) + b'\n'
    if len(raw) > MAX_PRIVATE_BYTES: _invalid()
    return raw


def decode_startup2(raw):
    if type(raw) is not bytes or not raw.endswith(b'\n') or len(raw) > MAX_PRIVATE_BYTES: _invalid()
    return validate_startup2(_parse(raw[:-1]))


def worker_binding(startup):
    value = validate_startup2(startup)
    return {key: value[key] for key in ('kind', 'launch_nonce', 'worker_pid', 'worker_birth')} | {
        'identity': {} if value['kind'] == 'preflight' else _identity(value['kind'], value['request']['receipt']),
        'invocations': [{key: item[key] for key in ('purpose', 'nonce')} for item in value['images']]}


def _binding(value):
    _tree(value)
    _fields(value, {'kind', 'launch_nonce', 'worker_pid', 'worker_birth', 'identity', 'invocations'})
    if type(value['kind']) is not str or value['kind'] not in ('trial', 'operation', 'preflight'): _invalid()
    _digest(value['launch_nonce']); _uint(value['worker_pid'], 32); _uint(value['worker_birth'])
    _invocations(value['kind'], value['invocations'], shares=False)
    if value['kind'] == 'preflight':
        _fields(value['identity'], set())
    else:
        identity = _identity(value['kind'], value['identity'])
        _fields(value['identity'], identity.keys())


def _body(body, binding, direction):
    if type(body) is not dict or type(body.get('type')) is not str: _invalid()
    kind, identity, purpose = binding['kind'], binding['identity'], body['type']
    if direction == 'host':
        if purpose != 'engine_start_ack' or kind == 'preflight': _invalid()
        _fields(body, {'type', *identity})
    elif purpose == 'endpoints_adopted':
        _fields(body, {'type'})
        return
    elif purpose == 'worker_error':
        _fields(body, {'type', 'reason', 'error_type'})
        if (type(body['reason']) is not str or body['reason'] != kind + '_worker_failed'
                or type(body['error_type']) is not str or re.fullmatch('[A-Za-z_][A-Za-z0-9_]{0,127}', body['error_type']) is None): _invalid()
        return
    elif purpose == 'dispatch_observed':
        _fields(body, {'type', 'purpose', 'nonce', 'native_pid', 'native_birth', 'dispatch_hash', 'dispatch'})
        if type(body['purpose']) is not str or type(body['nonce']) is not str or not any(
                item['purpose'] == body['purpose'] and item['nonce'] == body['nonce'] for item in binding['invocations']): _invalid()
        _uint(body['native_pid'], 32); _uint(body['native_birth']); _digest(body['dispatch_hash'])
        if type(body['dispatch']) is not dict or body['dispatch_hash'] != hashlib.sha256(_canonical(body['dispatch'])).hexdigest(): _invalid()
        return
    elif purpose == 'preflight_complete':
        if kind != 'preflight': _invalid()
        _fields(body, {'type', 'runtime'})
        runtime = body['runtime']
        _fields(runtime, {'platform', 'cli_hash', 'sdk_version', 'profile_hash', 'managed_policy', 'cli_version', 'auth'})
        if type(runtime['platform']) is not str or runtime['platform'] != 'win32': _invalid()
        _digest(runtime['cli_hash']); _digest(runtime['profile_hash'])
        for key in ('sdk_version', 'cli_version'): _text(runtime[key], 128)
        if type(runtime['managed_policy']) is not str or runtime['managed_policy'] not in ('absent', 'present', 'unknown'): _invalid()
        auth = runtime['auth']
        _fields(auth, {'logged_in', 'method', 'provider', 'plan'})
        if type(auth['logged_in']) is not bool: _invalid()
        for key in ('method', 'provider', 'plan'):
            if auth[key] is not None: _text(auth[key], 128)
        return
    else:
        extras = {'worker_ready': {'capability_hash'}, 'engine_start_requested': set(), 'engine_event': {'event'},
                  'worker_complete': {'fixture_events', 'tool_denials'} if kind == 'trial' else {'tool_denials'}}
        if kind == 'trial': extras['fixture_event'] = {'event'}
        if kind == 'preflight' or purpose not in extras: _invalid()
        _fields(body, {'type', *identity, *extras[purpose]})
        if purpose == 'worker_ready': _digest(body['capability_hash'])
        if purpose in ('engine_event', 'fixture_event'):
            if type(body['event']) is not dict: _invalid()
            if purpose == 'engine_event' and type(body['event'].get('type')) is not str: _invalid()
        if purpose == 'worker_complete':
            if type(body['tool_denials']) is not list or (kind == 'trial' and type(body['fixture_events']) is not list): _invalid()
    for key, item in identity.items():
        if type(body[key]) is not type(item) or body[key] != item: _invalid()


def validate_private_packet2(value, *, binding, direction, expected_sequence):
    _binding(binding); _tree(value)
    if type(direction) is not str or direction not in ('worker', 'host'): _invalid()
    _uint(expected_sequence, 63)
    _fields(value, {'version', 'sequence', 'launch_nonce', 'worker_pid', 'worker_birth', 'body'})
    if type(value['version']) is not int or value['version'] != 2: _invalid()
    _uint(value['sequence'], 63)
    if value['sequence'] != expected_sequence: _invalid()
    for key in ('launch_nonce', 'worker_pid', 'worker_birth'):
        if type(value[key]) is not type(binding[key]) or value[key] != binding[key]: _invalid()
    _body(value['body'], binding, direction)
    return _parse(_canonical(value))


def encode_private_packet2(value, *, binding, direction, expected_sequence):
    raw = _canonical(validate_private_packet2(value, binding=binding, direction=direction, expected_sequence=expected_sequence))
    return struct.pack('!I', len(raw)) + raw


def decode_private_packet2(frame, *, binding, direction, expected_sequence):
    if type(frame) is not bytes or len(frame) < 4: _invalid()
    size, = struct.unpack('!I', frame[:4])
    if not 0 < size <= MAX_PRIVATE_BYTES or len(frame) != size + 4: _invalid()
    return validate_private_packet2(_parse(frame[4:]), binding=binding, direction=direction, expected_sequence=expected_sequence)
