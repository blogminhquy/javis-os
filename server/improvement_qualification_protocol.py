"""Closed engineering startup3 consistency, never launch or account authority.

No filesystem, environment, clock, registry or process observation occurs here.
The authenticated native owner must supply this exact startup and prove source,
private-channel provenance, empty HOME, active scope, budget and M0 joins.
Production startup2 continues to reject every engineering extension.
"""
from __future__ import annotations

import hashlib
import math
from pathlib import PurePosixPath, PureWindowsPath
import re

from improvement_native_protocol import (_canonical, _digest, _fields, _parse,
    _text, _tree, validate_startup2, worker_binding, MAX_PRIVATE_BYTES)
from improvement_qualification_environment import _endpoint, validate_dummy_environment


def _hash(value): return hashlib.sha256(_canonical(value)).hexdigest()


def _path(value):
    _text(value, 4000)
    parts = value.replace('\\', '/').split('/')
    if any(part in ('.', '..') for part in parts): raise ValueError('qualification_path_invalid')
    candidate = PureWindowsPath(value)
    if candidate.is_absolute():
        if re.fullmatch('[A-Za-z]:', candidate.drive) is None:
            raise ValueError('qualification_path_invalid')
    else:
        candidate = PurePosixPath(value)
        if '\\' in value or not candidate.is_absolute(): raise ValueError('qualification_path_invalid')
    if str(candidate) != value: raise ValueError('qualification_path_invalid')
    return candidate


def _within(value, root):
    path = _path(value)
    if type(path) is not type(root) or not path.is_relative_to(root):
        raise ValueError('qualification_path_foreign')
    return path


def validate_scope(value):
    """Only closed, bounded scope data. A matching hash is not authority."""
    _tree(value)
    _fields(value, {'version', 'domain', 'account_ready', 'run_nonce', 'root', 'brain_id', 'pin_hash',
        'release_fingerprint', 'review_hash', 'endpoint', 'maximum_queries', 'created_at', 'deadline_at'})
    if (type(value['version']) is not int or value['version'] != 1 or value['domain'] != 'qualification'
            or value['account_ready'] is not False or type(value['maximum_queries']) is not int
            or not 1 <= value['maximum_queries'] <= 32):
        raise ValueError('qualification_scope_invalid')
    for name in ('run_nonce', 'pin_hash', 'release_fingerprint', 'review_hash'): _digest(value[name])
    _endpoint(value['endpoint'])
    for name in ('created_at', 'deadline_at'):
        if type(value[name]) not in (int, float) or not math.isfinite(value[name]):
            raise ValueError('qualification_scope_invalid')
    if not 0 < value['deadline_at'] - value['created_at'] <= 3600:
        raise ValueError('qualification_scope_invalid')
    root = _path(value['root'])
    if _within(value['brain_id'], root) != root / 'brain': raise ValueError('qualification_brain_invalid')
    return _parse(_canonical(value))


def _pin(value):
    _fields(value, {'version', 'provider', 'engine_id', 'model', 'reasoning', 'cli_path', 'cli_hash',
        'cli_version', 'sdk_version', 'profile_version', 'profile_hash'})
    if (type(value['version']) is not int or value['version'] != 1 or value['provider'] != 'anthropic-cli'
            or value['engine_id'] != 'claude-sdk' or value['sdk_version'] != '0.2.116'
            or value['profile_version'] != 'claude-owned-images-v3'
            or value['reasoning'] not in ('low', 'medium', 'high', 'xhigh', 'max')):
        raise ValueError('qualification_pin_invalid')
    for name, item in value.items():
        if name != 'version': _text(item)
    for name in ('cli_hash', 'profile_hash'): _digest(value[name])
    _path(value['cli_path'])
    if re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+', value['cli_version']) is None:
        raise ValueError('qualification_pin_invalid')


def _link(value, *, kind, request, scope, run_hash):
    _fields(value, {'version', 'domain', 'run_hash', 'brain_id', 'kind', 'subject_id', 'attempt',
        'request_hash', 'workspace_hash', 'materialization_hash', 'engine_config_hash', 'capability_hash',
        'call_id', 'call_binding'})
    if (type(value['version']) is not int or value['version'] != 1 or value['domain'] != 'qualification'
            or type(value['call_id']) is not int or not 1 <= value['call_id'] < 2 ** 63):
        raise ValueError('qualification_link_invalid')
    for name in ('run_hash', 'request_hash', 'workspace_hash', 'materialization_hash', 'engine_config_hash', 'capability_hash'):
        _digest(value[name])
    receipt = request['receipt']
    identifier = receipt[kind + '_id']
    if (value['run_hash'] != run_hash or value['brain_id'] != scope['brain_id'] or value['kind'] != kind
            or value['subject_id'] != identifier or type(value['attempt']) is not int
            or value['attempt'] != receipt['attempt'] or value['workspace_hash'] != _hash(receipt)
            or value['materialization_hash'] != receipt['input_hash'] or value['engine_config_hash'] != scope['pin_hash']
            or value['capability_hash'] != request['capability_hash']):
        raise ValueError('qualification_link_inconsistent')
    call = value['call_binding']
    _fields(call, {'brain_id', 'purpose', 'context_ref', 'mirror_ref', 'reason_ref', 'attempt'})
    expected = {'brain_id': scope['brain_id'], 'purpose': 'improve_probe' if kind == 'trial' else receipt['purpose'],
        'mirror_ref': 'improvement_' + kind + ':' + identifier,
        'reason_ref': 'improvement_' + kind + ':' + identifier + ':attempt:' + str(receipt['attempt'])}
    if (any(call[name] != item for name, item in expected.items()) or type(call['attempt']) is not int
            or call['attempt'] != receipt['attempt']):
        raise ValueError('qualification_call_inconsistent')
    _text(call['context_ref'], 1000)
    if re.fullmatch(r'improvement:[A-Za-z0-9_.:-]{1,160}', call['context_ref']) is None:
        raise ValueError('qualification_call_inconsistent')


def _base(value):
    environment = validate_dummy_environment(value['environment'])
    return {**{name: item for name, item in value.items() if name != 'qualification'},
        'version': 2, 'type': 'startup2', 'environment': {name: item for name, item in environment.items()
            if name not in ('ANTHROPIC_API_KEY', 'ANTHROPIC_BASE_URL')}}


def validate_startup3(value):
    _tree(value)
    _fields(value, {'version', 'type', 'kind', 'launch_nonce', 'worker_pid', 'worker_birth',
        'private_share', 'images', 'request', 'environment', 'qualification'})
    if type(value['version']) is not int or value['version'] != 3 or value['type'] != 'startup3':
        raise ValueError('invalid_qualification_startup')
    # Deliberate translation only inside this explicit engineering parser. The
    # production parser never sees or admits the extra environment/scope fields.
    validate_startup2(_base(value))
    q = value['qualification']
    fields = {'version', 'run_hash', 'scope', 'environment_hash', 'attempt_link'}
    if q.get('version') == 2: fields |= {'preflight_hash', 'query_binding'}
    _fields(q, fields)
    if type(q['version']) is not int or q['version'] not in (1, 2): raise ValueError('invalid_qualification_startup')
    _digest(q['run_hash']); _digest(q['environment_hash'])
    scope = validate_scope(q['scope']); pin = value['request']['config_pin']; _pin(pin)
    if (q['run_hash'] != _hash(scope) or scope['pin_hash'] != _hash(pin)
            or q['environment_hash'] != _hash(value['environment'])
            or value['environment']['ANTHROPIC_BASE_URL'] != scope['endpoint']):
        raise ValueError('qualification_startup_inconsistent')
    root = _path(scope['root']); env = value['environment']
    home = _within(env['HOME'], root)
    if (home == root or env['USERPROFILE'] != str(home)
            or _within(env['APPDATA'], root) != home / 'AppData' / 'Roaming'
            or _within(env['LOCALAPPDATA'], root) != home / 'AppData' / 'Local'):
        raise ValueError('qualification_home_inconsistent')
    for name in ('TEMP', 'TMP', 'JAVIS_STATE_DIR', 'BRAINS_DIR', 'OBSIDIAN_VAULT_PATH', 'BRAIN_PATH', 'SOURCES_PATH'):
        _within(env[name], root)
    if value['kind'] == 'preflight':
        if q['version'] != 1 or q['attempt_link'] is not None: raise ValueError('qualification_preflight_link_forbidden')
    else:
        _within(value['request']['workspace_root'], root)
        _within(value['request']['receipt'].get('path'), root)
        _link(q['attempt_link'], kind=value['kind'], request=value['request'], scope=scope, run_hash=q['run_hash'])
        if q['version'] == 2:
            validate_query_binding(q['query_binding'], link=q['attempt_link'], preflight_hash=q['preflight_hash'])
    return _parse(_canonical(value))


def validate_query_binding(value, *, link, preflight_hash):
    _fields(value, {'version', 'domain', 'supported', 'account_ready', 'run_hash', 'preflight_hash',
        'kind', 'subject_id', 'attempt', 'request_hash', 'workspace_hash', 'materialization_hash',
        'engine_config_hash', 'authority_hash'})
    _digest(preflight_hash)
    if (type(value['version']) is not int or value['version'] != 1 or value['domain'] != 'qualification'
            or value['supported'] is not False or value['account_ready'] is not False
            or type(value['attempt']) is not int or value['attempt'] != link['attempt']
            or value['preflight_hash'] != preflight_hash
            or any(value[name] != link[name] for name in ('run_hash', 'kind', 'subject_id', 'request_hash',
                'workspace_hash', 'materialization_hash', 'engine_config_hash'))
            or value['authority_hash'] != link['capability_hash']
            or _hash({name: item for name, item in value.items() if name != 'authority_hash'}) != value['authority_hash']):
        raise ValueError('qualification_query_binding_inconsistent')
    for name in ('run_hash', 'preflight_hash', 'request_hash', 'workspace_hash', 'materialization_hash',
            'engine_config_hash', 'authority_hash'): _digest(value[name])
    return _parse(_canonical(value))


def encode_startup3(value):
    raw = _canonical(validate_startup3(value)) + b'\n'
    if len(raw) > MAX_PRIVATE_BYTES: raise ValueError('qualification_startup_too_large')
    return raw


def decode_startup3(raw):
    if type(raw) is not bytes or not raw.endswith(b'\n') or len(raw) > MAX_PRIVATE_BYTES:
        raise ValueError('invalid_qualification_startup')
    return validate_startup3(_parse(raw[:-1]))


def worker_binding3(value):
    """Reuse actual private channel incarnation/nonces; data adds no provenance."""
    return worker_binding(_base(validate_startup3(value)))


def validate_technical_observation(value, *, pin):
    """Check fixed diagnostic observations, granting no account capability."""
    _pin(pin); _tree(value)
    _fields(value, {'platform', 'cli_hash', 'sdk_version', 'profile_hash', 'managed_policy', 'cli_version', 'auth'})
    if (value['platform'] != 'win32' or value['managed_policy'] != 'absent'
            or any(value[name] != pin[name] for name in ('cli_hash', 'sdk_version', 'profile_hash', 'cli_version'))):
        raise ValueError('qualification_observation_drift')
    auth = value['auth']; _fields(auth, {'logged_in', 'method', 'provider', 'plan'})
    if type(auth['logged_in']) is not bool: raise ValueError('qualification_auth_invalid')
    for name in ('method', 'provider', 'plan'):
        if auth[name] is not None: _text(auth[name], 128)
    if auth['method'] == 'claude.ai' or auth['plan'] is not None:
        raise PermissionError('qualification_subscription_forbidden')
    return _parse(_canonical(value))
