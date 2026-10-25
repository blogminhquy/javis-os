"""Standalone exact host/native read delivery, preserving raw optional errors.

This new observation protocol has no execution caller. It must not replace the
legacy receipt3 correlator; version4 integration/qualification is separate.
"""
from __future__ import annotations

import json
import re

from improvement_cases import _fields, _frozen
from improvement_sandbox import _IDENTITY, _manifest
from improvement_skill_asset_proof import _result_text
from improvement_store import _hash, _json

SKILL_TOOL = 'mcp__skill__skill_asset_read'
FIXTURE_TOOL = 'mcp__fixture__fixture_read'
OBSERVATION_TYPE = 'trial_read_broker_observation'
_TOOLS = (SKILL_TOOL, FIXTURE_TOOL)
_OBSERVATION = {'version', 'observation_id', 'trial_id', 'attempt', 'input_hash',
                'effective_view', 'tool_name', 'request', 'response_text', 'response_hash'}
_RESPONSE = {'version', 'observation_id', 'trial_id', 'attempt', 'input_hash',
             'effective_view', 'tool_name', 'request_hash', 'outcome', 'result'}
_SKILL_RESULT = {'status', 'observation_id', 'trial_id', 'attempt', 'input_hash',
                 'effective_view', 'asset_id', 'content_hash', 'content'}
_FIXTURE_RESULT = {'sequence', 'status', 'snapshot_id', 'capability_id', 'content', 'hash', 'source'}
_MISS = {'status': 'read_miss', 'reason': 'read_miss'}


def _out(verdict, reason, proofs=None):
    return {'verdict': verdict, 'reason': reason, 'proofs': _frozen(proofs or [])}


def _same(first, second):
    # JSON preserves bool/int/float distinctions which Python equality merges.
    return _json(first) == _json(second)


def _nonce(value):
    return type(value) is str and re.fullmatch('[0-9a-f]{64}', value) is not None


def _payload(manifest, binding, tool, request, response):
    """Validate the actual underlying decision/payload against pinned inputs."""
    result, asset, view = response['result'], manifest['assets'][0], manifest['effective_view']
    if tool == SKILL_TOOL:
        expected_request = {'view_id': view['view_id'], 'view_hash': view['view_hash'],
                            'asset_id': asset['id'], 'content_hash': asset['hash']}
        hit = type(request) is dict and _same(request, expected_request)
        expected = {**binding, 'status': 'skill_asset_hit', 'asset_id': asset['id'],
                    'content_hash': asset['hash'], 'content': asset['content']}
        if hit:
            _fields(result, _SKILL_RESULT)
            if not _nonce(result['observation_id']) or not _same(
                    {key: result[key] for key in expected}, expected):
                raise ValueError('pinned_skill_payload_mismatch')
            unique = ('skill', result['observation_id'])
            resource, content_hash = asset['id'], asset['hash']
    else:
        valid = (type(request) is dict and set(request) == {'snapshot_id', 'source_version'}
                 and all(type(value) is str for value in request.values()))
        fixtures = {item['snapshot_id']: item for item in manifest['case']['fixtures']}
        fixture = fixtures.get(request['snapshot_id']) if valid else None
        hit = bool(fixture and request['source_version'] == fixture['source']['source_version'])
        if hit:
            _fields(result, _FIXTURE_RESULT)
            expected = {'status': 'fixture_hit', 'capability_id': 'fixture.read',
                        **{key: fixture[key] for key in ('snapshot_id', 'content', 'hash', 'source')}}
            if (type(result['sequence']) is not int or result['sequence'] < 1
                    or not _same({key: result[key] for key in expected}, expected)):
                raise ValueError('pinned_fixture_payload_mismatch')
            unique = ('fixture', result['sequence'])
            resource, content_hash = fixture['snapshot_id'], fixture['hash']
    if response['outcome'] != ('hit' if hit else 'miss'):
        raise ValueError('pinned_read_decision_mismatch')
    if not hit:
        if not _same(result, _MISS):
            raise ValueError('invalid_read_miss_payload')
        return None, None, None
    return unique, resource, content_hash


def correlate_read_outcomes(manifest, workspace, events):
    """Correlate new envelopes; None is never substituted for absent telemetry.

    Exact successful host bytes delivered in the actual native call/result may
    establish a read despite the SDK's optional None error value. This is an
    explicit derived basis, not a fabricated raw false flag or comprehension.
    Denial requires both the actual host miss and an explicit native error.
    """
    try:
        return _correlate(_manifest(manifest), _frozen(workspace), _frozen(events))
    except (ValueError, TypeError, KeyError, UnicodeError, RecursionError):
        return _out('fail', 'invalid_read_outcome_evidence')


def _correlate(manifest, workspace, events):
    if manifest['version'] not in (2, 3, 4):
        return _out('unknown', 'read_outcome_protocol_unavailable')
    if (type(workspace) is not dict or type(workspace.get('trial_id')) is not str
            or not _IDENTITY.fullmatch(workspace['trial_id']) or type(workspace.get('attempt')) is not int
            or not 1 <= workspace['attempt'] <= 1_000_000 or workspace.get('input_hash') != _hash(manifest)
            or type(events) is not list or len(events) > 100000 or any(type(event) is not dict for event in events)):
        return _out('fail', 'read_outcome_input_mismatch')
    inits = [(index, event) for index, event in enumerate(events)
             if event.get('type') == 'native_system' and event.get('subtype') == 'init']
    if len(inits) != 1:
        return _out('fail' if inits else 'unknown', 'read_outcome_init_unavailable')
    init_index, init = inits[0]
    data = init.get('data')
    session = data.get('session_id') if type(data) is dict else None
    if type(session) is not str or not session:
        return _out('unknown', 'read_outcome_session_unavailable')
    binding = {**{key: workspace[key] for key in ('trial_id', 'attempt', 'input_hash')},
               'effective_view': manifest['effective_view']}
    observations, texts, calls, results, payload_ids = {}, {}, {}, {}, set()
    for index, event in enumerate(events):
        kind = event.get('type')
        if kind in ('tool_call', 'tool_result'):
            identifier = event.get('id')
            table = calls if kind == 'tool_call' else results
            if type(identifier) is not str or not identifier or identifier in table:
                return _out('fail', 'duplicate_or_invalid_native_read_identity')
            table[identifier] = (index, event)
        elif kind == OBSERVATION_TYPE:
            if event.get('session_id') != session:
                return _out('unknown' if event.get('session_id') is None else 'fail', 'read_outcome_session_mismatch')
            observation = event.get('observation')
            _fields(observation, _OBSERVATION)
            identifier, tool = observation['observation_id'], observation['tool_name']
            if (type(observation['version']) is not int or observation['version'] != 1 or not _nonce(identifier)
                    or identifier in observations or type(tool) is not str or tool not in _TOOLS
                    or not _same({key: observation[key] for key in binding}, binding)):
                return _out('fail', 'invalid_host_read_binding')
            text = observation['response_text']
            if type(text) is not str:
                return _out('fail', 'invalid_host_read_response')
            response = json.loads(text)
            _fields(response, _RESPONSE)
            if (type(response['version']) is not int or response['version'] != 1
                    or response['observation_id'] != identifier or response['tool_name'] != tool
                    or not _same({key: response[key] for key in binding}, binding)
                    or response['request_hash'] != _hash(observation['request'])
                    or _json(response) != text or _hash(response) != observation['response_hash'] or text in texts):
                return _out('fail', 'host_read_response_mismatch')
            unique, resource, content_hash = _payload(manifest, binding, tool, observation['request'], response)
            if unique is not None:
                if unique in payload_ids:
                    return _out('fail', 'underlying_read_identity_replayed')
                payload_ids.add(unique)
            observations[identifier] = (observation, response, resource, content_hash)
            texts[text] = identifier
    for identifier, (_, result) in results.items():
        if identifier not in calls:
            return _out('fail', 'orphan_native_read_result')
        text = _result_text(result.get('content'))
        if text in texts and calls[identifier][1].get('name') not in _TOOLS:
            return _out('fail', 'host_read_response_wrong_tool')
    reads = [(identifier, item) for identifier, item in calls.items() if item[1].get('name') in _TOOLS]
    if not reads or not observations:
        return _out('unknown', 'host_or_native_read_unobserved')
    used, proofs = set(), []
    for identifier, (call_index, call) in reads:
        if identifier not in results:
            return _out('unknown', 'native_read_result_missing')
        result_index, result = results[identifier]
        if not init_index < call_index < result_index:
            return _out('fail', 'native_read_order_mismatch')
        for event in (call, result):
            if event.get('session_id') != session:
                return _out('unknown' if event.get('session_id') is None else 'fail', 'read_outcome_session_mismatch')
        text = _result_text(result.get('content'))
        observation_id = texts.get(text) if text is not None else None
        if observation_id is None:
            return _out('unknown', 'native_read_response_unmatched')
        if observation_id in used:
            return _out('fail', 'native_read_response_replayed')
        observation, response, resource, content_hash = observations[observation_id]
        if call.get('name') != observation['tool_name'] or not _same(call.get('input'), observation['request']):
            return _out('fail', 'native_read_request_mismatch')
        if 'is_error' not in result or 'native_is_error' not in result:
            return _out('unknown', 'native_read_error_field_absent')
        flag, raw_flag = result['is_error'], result['native_is_error']
        if ((flag is not None and type(flag) is not bool) or (raw_flag is not None and type(raw_flag) is not bool)
                or not _same(flag, raw_flag)):
            return _out('fail', 'native_read_error_fields_invalid')
        if response['outcome'] == 'hit':
            if raw_flag is True:
                return _out('fail', 'native_error_contradicts_host_success')
            basis = 'exact_host_success_and_native_delivery'
        else:
            if raw_flag is False:
                return _out('fail', 'native_success_contradicts_host_denial')
            if raw_flag is None:
                return _out('unknown', 'native_denial_error_unobserved')
            basis = 'exact_host_denial_and_native_error'
        used.add(observation_id)
        proofs.append({'version': 1, **binding, 'tool_name': call['name'], 'tool_use_id': identifier,
            'session_id': session, 'observation_id': observation_id, 'request_hash': response['request_hash'],
            'response_hash': observation['response_hash'], 'outcome': response['outcome'], 'basis': basis,
            'native_error_value': raw_flag, 'resource_id': resource, 'content_hash': content_hash})
    if used != set(observations):
        return _out('unknown', 'host_read_without_native_delivery')
    return _out('pass', 'exact_pinned_read_outcomes_observed', proofs)
