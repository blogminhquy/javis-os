"""Closed immutable view identity; shape and hashes never grant runtime authority."""
from __future__ import annotations

import json
import re

from improvement_blobs import MAX_ASSET_BYTES
from improvement_store import _hash, _json

_ID = re.compile(r'[A-Za-z0-9][A-Za-z0-9_-]{0,127}\Z')
_HASH = re.compile(r'[0-9a-f]{64}\Z')
_SKILL = re.compile(r'skills/([a-z0-9][a-z0-9_-]{0,127})/SKILL\.md\Z')
_DEVICES = {'con', 'prn', 'aux', 'nul', *(f'com{i}' for i in range(1, 10)), *(f'lpt{i}' for i in range(1, 10))}
_FIELDS = {'version', 'evidence_class', 'brain_id', 'experiment_id', 'context_id', 'context_generation',
    'comparison_id', 'comparison_hash', 'definition_hash', 'arm_ordinal', 'arm_hash', 'candidate_id', 'variant',
    'target', 'engine_config_hash', 'baseline_context_hash', 'contract_hash', 'case_set_hash', 'grant_hash',
    'scope_hash', 'policy_version', 'source_authority_hash', 'semantic', 'assets'}
_HASH_FIELDS = {'comparison_hash', 'definition_hash', 'arm_hash', 'engine_config_hash', 'baseline_context_hash',
    'contract_hash', 'case_set_hash', 'grant_hash', 'scope_hash', 'source_authority_hash'}
_TARGET = {'target_id', 'base_revision_id', 'base_hash', 'base_generation', 'canonical_ref', 'identity',
    'protected_hash', 'ownership'}
_SEMANTIC = {'receipt_id', 'binding_hash', 'assessment_hash', 'dependency_hash', 'owner_event_key'}
_ASSET = {'id', 'canonical_ref', 'before_hash', 'content_hash', 'identity', 'authority_hash', 'origin'}


def _require(condition):
    if not condition:
        raise ValueError('invalid_effective_view')


def _fields(value, expected):
    _require(type(value) is dict and value.keys() == expected)


def _identifier(value):
    _require(type(value) is str and _ID.fullmatch(value) is not None)


def _digest(value):
    _require(type(value) is str and _HASH.fullmatch(value) is not None)


def _integer(value, minimum=1, maximum=2 ** 63 - 1):
    _require(type(value) is int and minimum <= value <= maximum)


def _text(value, maximum):
    _require(type(value) is str and 1 <= len(value) <= maximum and value == value.strip()
        and not any(ord(char) < 32 or ord(char) == 127 for char in value))


def view_manifest(value):
    """Validate detached metadata only; the host still verifies every actual binding."""
    try:
        raw = _json(value).encode('utf-8')
        _require(len(raw) <= MAX_ASSET_BYTES)
        value = json.loads(raw)
    except (TypeError, UnicodeError, RecursionError) as error:
        raise ValueError('invalid_effective_view') from error
    _fields(value, _FIELDS)
    _integer(value['version'], 1, 1)
    _require(value['evidence_class'] == 'technical' and value['variant'] in ('baseline', 'candidate'))
    _text(value['brain_id'], 1000)
    for key in ('experiment_id', 'context_id', 'comparison_id', 'candidate_id'):
        _identifier(value[key])
    for key in _HASH_FIELDS:
        _digest(value[key])
    _integer(value['context_generation'])
    _integer(value['policy_version'], 0)
    _integer(value['arm_ordinal'], 1, 3)

    target = value['target']
    _fields(target, _TARGET)
    for key in ('target_id', 'base_revision_id'):
        _identifier(target[key])
    for key in ('base_hash', 'identity', 'protected_hash'):
        _digest(target[key])
    _integer(target['base_generation'])
    _require(target['ownership'] in ('user_protected', 'user_managed'))
    path = target['canonical_ref']
    match = _SKILL.fullmatch(path) if type(path) is str else None
    _require(match is not None and match[1] not in _DEVICES)

    semantic = value['semantic']
    _fields(semantic, _SEMANTIC)
    _identifier(semantic['receipt_id'])
    for key in ('binding_hash', 'assessment_hash', 'dependency_hash'):
        _digest(semantic[key])
    if semantic['owner_event_key'] is not None:
        _text(semantic['owner_event_key'], 160)
        _require(len(semantic['owner_event_key']) >= 8)

    assets = value['assets']
    _require(type(assets) is list and len(assets) == 1)
    asset = assets[0]
    _fields(asset, _ASSET)
    _identifier(asset['id'])
    for key in ('before_hash', 'content_hash', 'identity', 'authority_hash'):
        _digest(asset[key])
    baseline = value['variant'] == 'baseline'
    _require(asset['id'] == (target['base_revision_id'] if baseline else value['candidate_id'])
        and asset['canonical_ref'] == path and asset['before_hash'] == target['base_hash']
        and asset['identity'] == target['identity'] and asset['authority_hash'] == value['source_authority_hash']
        and asset['origin'] == value['variant'])
    if baseline:
        _require(asset['content_hash'] == target['base_hash'])
    return value


def view_hash(value):
    """Hash the validated canonical projection without IDs or a self-referential hash."""
    return _hash(view_manifest(value))
