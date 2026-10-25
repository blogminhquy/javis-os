"""Pure correlation of immutable broker returns and native skill-tool records.

This proves an observed read only. Authorization, native image/configuration,
tool isolation and business correctness remain separate checks.
"""
from __future__ import annotations

import json
import re

from improvement_cases import _fields, _frozen
from improvement_sandbox import _manifest
from improvement_store import _hash, _json

TOOL_NAME = 'mcp__skill__skill_asset_read'
OBSERVATION_TYPE = 'skill_asset_broker_observation'
_OBSERVATION_FIELDS = {'observation_id', 'trial_id', 'attempt', 'input_hash', 'effective_view',
    'asset_id', 'content_hash', 'request', 'response_text', 'response_hash'}
_RESPONSE_FIELDS = {'status', 'observation_id', 'trial_id', 'attempt', 'input_hash',
    'effective_view', 'asset_id', 'content_hash', 'content'}


def _out(verdict, reason, proofs=None):
    return {'verdict': verdict, 'reason': reason, 'proofs': _frozen(proofs or [])}


def _result_text(content):
    if type(content) is str:
        return content
    if (type(content) is list and len(content) == 1 and type(content[0]) is dict
            and set(content[0]) == {'type', 'text'} and content[0]['type'] == 'text'
            and type(content[0]['text']) is str):
        return content[0]['text']
    return None


def correlate_asset_reads(manifest, workspace, events):
    """Derive exact native reads from raw records, without timing/FIFO joins.

    A broker-only observation or receipt summary cannot pass. Each unpredictable
    response must join exactly one completed native tool call/result in the one
    initialized session, with exact input, emitted response text and host pins.
    Optional/missing native error telemetry stays unknown in this validator.
    """
    try:
        return _correlate(_manifest(manifest), _frozen(workspace), _frozen(events))
    except (ValueError, TypeError, KeyError, UnicodeError):
        return _out('fail', 'invalid_asset_read_evidence')


def _correlate(manifest, workspace, events):
    if manifest['version'] not in (2, 3):
        return _out('unknown', 'legacy_asset_use_unobserved')
    if (type(workspace) is not dict or type(workspace.get('trial_id')) is not str
            or type(workspace.get('attempt')) is not int or workspace['attempt'] < 1
            or workspace.get('input_hash') != _hash(manifest) or type(events) is not list
            or any(type(event) is not dict for event in events)):
        return _out('fail', 'asset_read_input_binding_mismatch')
    inits = [(index, event) for index, event in enumerate(events)
             if event.get('type') == 'native_system' and event.get('subtype') == 'init']
    if len(inits) != 1:
        return _out('fail' if inits else 'unknown', 'asset_read_session_init_unavailable')
    init_index, init = inits[0]
    data = init.get('data')
    session = data.get('session_id') if type(data) is dict else None
    if type(session) is not str or not session:
        return _out('unknown', 'asset_read_session_unobserved')
    asset, view = manifest['assets'][0], manifest['effective_view']
    request = {'view_id': view['view_id'], 'view_hash': view['view_hash'],
               'asset_id': asset['id'], 'content_hash': asset['hash']}
    binding = {key: workspace[key] for key in ('trial_id', 'attempt', 'input_hash')}
    binding.update(effective_view=view, asset_id=asset['id'], content_hash=asset['hash'])
    observations, texts, calls, results = {}, {}, {}, {}
    for index, event in enumerate(events):
        kind = event.get('type')
        if kind in ('tool_call', 'tool_result'):
            identifier = event.get('id')
            table = calls if kind == 'tool_call' else results
            if type(identifier) is not str or not identifier or identifier in table:
                return _out('fail', 'duplicate_or_invalid_native_tool_identity')
            table[identifier] = (index, event)
        elif kind == OBSERVATION_TYPE:
            if event.get('session_id') != session:
                return _out('unknown' if event.get('session_id') is None else 'fail', 'asset_read_session_mismatch')
            observation = event.get('observation')
            _fields(observation, _OBSERVATION_FIELDS)
            identifier = observation['observation_id']
            if (type(identifier) is not str or re.fullmatch('[0-9a-f]{64}', identifier) is None
                    or identifier in observations or type(observation['attempt']) is not int):
                return _out('fail', 'duplicate_or_invalid_broker_identity')
            if (any(observation.get(key) != value for key, value in binding.items())
                    or observation['request'] != request):
                return _out('fail', 'broker_asset_binding_mismatch')
            text = observation['response_text']
            if type(text) is not str:
                return _out('fail', 'invalid_broker_response')
            response = json.loads(text)
            _fields(response, _RESPONSE_FIELDS)
            if (type(response['attempt']) is not int or response['status'] != 'skill_asset_hit'
                    or response['observation_id'] != identifier or response['content'] != asset['content']
                    or any(response.get(key) != value for key, value in binding.items())
                    or _json(response) != text or _hash(response) != observation['response_hash']):
                return _out('fail', 'broker_response_mismatch')
            if text in texts:
                return _out('fail', 'ambiguous_broker_response')
            observations[identifier] = observation
            texts[text] = identifier
    for identifier, (_, result) in results.items():
        if identifier not in calls:
            return _out('fail', 'orphan_native_tool_result')
        text = _result_text(result.get('content'))
        if text in texts and calls[identifier][1].get('name') != TOOL_NAME:
            return _out('fail', 'native_asset_response_wrong_tool')
    asset_calls = [(identifier, item) for identifier, item in calls.items() if item[1].get('name') == TOOL_NAME]
    if not asset_calls or not observations:
        return _out('unknown', 'native_asset_read_unobserved')
    used, proofs = set(), []
    for identifier, (call_index, call) in asset_calls:
        if identifier not in results:
            return _out('unknown', 'native_asset_result_missing')
        result_index, result = results[identifier]
        if not init_index < call_index < result_index:
            return _out('fail', 'native_asset_read_order_mismatch')
        for event in (call, result):
            if event.get('session_id') != session:
                return _out('unknown' if event.get('session_id') is None else 'fail', 'asset_read_session_mismatch')
        if call.get('input') != request:
            return _out('fail', 'native_asset_request_mismatch')
        if result.get('is_error') is True or result.get('native_is_error') is True:
            return _out('fail', 'native_asset_read_error')
        if result.get('is_error') is not False or result.get('native_is_error') is not False:
            return _out('unknown', 'native_asset_error_telemetry_unobserved')
        text = _result_text(result.get('content'))
        observation_id = texts.get(text) if text is not None else None
        if observation_id is None:
            return _out('unknown', 'native_asset_response_unmatched')
        if observation_id in used:
            return _out('fail', 'native_asset_response_replayed')
        used.add(observation_id)
        observation = observations[observation_id]
        proofs.append({**binding, 'effective_view': _frozen(view), 'observation_id': observation_id,
            'tool_use_id': identifier, 'session_id': session, 'request_hash': _hash(request),
            'response_hash': observation['response_hash']})
    if used != set(observations):
        return _out('unknown', 'broker_read_without_native_result')
    return _out('pass', 'exact_immutable_native_asset_read', proofs)
