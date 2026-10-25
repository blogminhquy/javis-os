"""Independent observation2 record checks used by actual result owners.

These checks join stored observations and durable decisions, not live peers or
loaded pages. An accounting ACK remains the existing attempt/call owner's duty.
Qualification is separate from consistent records; input delivery never proves
native reading, provider acceptance, reasoning or comprehension.
"""
from __future__ import annotations

import hashlib
import subprocess
import sys

from improvement_native_observation import observation_binding, validate_observation2
from improvement_native_protocol import _canonical, _parse, _fields, _digest
from improvement_store import _hash, _json

PURPOSES = ('adapter_version', 'auth_status', 'sdk_version', 'query')
_FLAGS = 0x08000006


def _sha(value): return hashlib.sha256(value.encode('utf-8')).hexdigest()
def _copy(value): return _parse(_canonical(value))


def _row(identifier, verdict, reason, **evidence):
    return {'id': identifier, 'verdict': verdict, 'reason': reason,
        'evidence': {'coverage': 'record_checks_only', 'business_proof': False, **evidence}}


def _refuse(): raise ValueError('invalid_native_execution_trace')


def _dispatch(value, *, purpose, kind, pin, receipt, system_prompt, tool_policy):
    _fields(value, {'version', 'purpose', 'basis', 'argument_consistency', 'environment_hash', 'source_policy_hash'})
    if (type(value['version']) is not int or value['version'] != 1 or value['purpose'] != purpose
            or value['basis'] != 'native_argument_consistency'): _refuse()
    _digest(value['environment_hash']); _digest(value['source_policy_hash'])
    if value['source_policy_hash'] != pin['profile_hash']: _refuse()
    actual = value['argument_consistency']
    common = {'version', 'argv_hash', 'command_line_hash', 'cwd_hash', 'creationflags'}
    if purpose != 'query':
        _fields(actual, common)
        argv = [pin['cli_path'], *{'adapter_version': ['--version'], 'auth_status': ['auth', 'status', '--json'],
            'sdk_version': ['-v']}[purpose]]
        expected = {'version': 1, 'argv_hash': _hash(argv), 'command_line_hash': _sha(subprocess.list2cmdline(argv)),
            'cwd_hash': _sha(receipt['path']), 'creationflags': _FLAGS}
    else:
        _fields(actual, common | {'verdict', 'basis', 'model', 'reasoning', 'prompt_hash', 'tools', 'tool_policy',
            'cli_path_hash', 'settings_hash', 'mcp_config_hash', 'expected_hash', 'coverage'})
        tools = ['mcp__fixture__fixture_read'] + (['mcp__skill__skill_asset_read'] if tool_policy == 'pinned_skill' else [])
        servers = ('fixture', 'skill') if tool_policy == 'pinned_skill' else ('fixture',)
        policy = {'version': 2, **{key: pin[key] for key in ('cli_path', 'model', 'reasoning')},
            'prompt_hash': _sha(system_prompt), 'cwd': receipt['path'], 'tools': tools,
            'tool_policy': tool_policy}
        expected = {'version': 2, 'verdict': 'pass', 'basis': 'query_argument_consistency',
            **{key: policy[key] for key in ('model', 'reasoning', 'prompt_hash', 'tools', 'tool_policy')},
            'cli_path_hash': _sha(pin['cli_path']), 'cwd_hash': _sha(receipt['path']),
            'expected_hash': _hash(policy), 'creationflags': _FLAGS,
            'settings_hash': _hash({'fastMode': False, 'disableAllHooks': True}),
            'mcp_config_hash': _hash({'mcpServers': {name: {'type': 'sdk', 'name': name} for name in servers}}),
            'coverage': dict.fromkeys(('os_boundary', 'image', 'provider_acceptance', 'internal_reasoning'), 'unknown')}
    for key, item in expected.items():
        if _json(actual.get(key)) != _json(item): _refuse()
    for key in ('argv_hash', 'command_line_hash'): _digest(actual[key])


def validate_native_trace(packets, *, kind, receipt, pin, capability_hash, system_prompt,
        user_prompt, data_hash, read_decision=None, tool_policy=None):
    """Validate complete raw V2 records and return defensive bodies/joins/checks.

    ``read_decision(joined)`` must independently reread the actual durable M0
    decision for this exact attempt scope. Omitting it yields UNKNOWN, never an
    allow. Result/product owners must require all returned decisions to allow
    and reread them in the final publication transaction. No packet is converted
    to a legacy envelope; global and per-source counters are checked separately.
    Query adds SDK environment keys; only the three fixed preflight environment
    hashes must agree. Hashes alone cannot reconstruct the query derivation:
    the qualified parent must check its actual frozen values before persisting.
    """
    if tool_policy is None: tool_policy = 'pinned_skill' if kind == 'trial' else 'fixture_only'
    if (type(kind) is not str or type(tool_policy) is not str or not (
            (kind == 'trial' and tool_policy in ('pinned_skill', 'baseline_inline'))
            or (kind == 'operation' and tool_policy == 'fixture_only'))): _refuse()
    if type(packets) is not list or not 1 <= len(packets) <= 100000: _refuse()
    _digest(capability_hash); _digest(data_hash)
    binding = observation_binding(packets[0], kind=kind, receipt=receipt)
    counters, images, dispatches, bodies = {'guardian': 0, 'worker': 0}, {}, {}, []
    sealed, endpoints, ready, started, completed, drained = False, False, False, False, False, False
    environment = source_policy = None
    for number, original in enumerate(packets, 1):
        source = original.get('source') if type(original) is dict else None
        if source not in counters: _refuse()
        counters[source] += 1
        packet = validate_observation2(original, binding=binding, expected_sequence=number,
            expected_source_sequence=counters[source])
        body, event = packet['body'], packet['body']['type']
        if drained: _refuse()
        if source == 'guardian':
            if event == 'launch_offer':
                if number != 1 or body['root_image']['matches'] is not True: _refuse()
            elif event == 'stdio_sealed':
                if sealed: _refuse()
                sealed = True
            elif event == 'image_observed':
                purpose = body['purpose']
                if (not sealed or purpose in images or body['comparison']['matches'] is not True
                        or body['comparison']['selected']['sha256'] != pin['cli_hash']): _refuse()
                images[purpose] = packet
            elif event == 'drained':
                if not completed or body['reason'] not in ('completed', 'host_stop'): _refuse()
                drained = True
            continue
        bodies.append(body)
        if not sealed or completed: _refuse()
        if event == 'endpoints_adopted':
            if endpoints or len(bodies) != 1: _refuse()
            endpoints = True
        elif not endpoints: _refuse()
        elif event == 'dispatch_observed':
            purpose = body['purpose']
            if len(dispatches) >= 4 or purpose != PURPOSES[len(dispatches)]: _refuse()
            _dispatch(body['dispatch'], purpose=purpose, kind=kind, pin=pin, receipt=receipt,
                system_prompt=system_prompt, tool_policy=tool_policy)
            current = body['dispatch']
            if environment is None: environment, source_policy = current['environment_hash'], current['source_policy_hash']
            if (purpose != 'query' and current['environment_hash'] != environment) or current['source_policy_hash'] != source_policy:
                _refuse()
            dispatches[purpose] = packet
        elif event == 'worker_ready':
            if (ready or started or body['capability_hash'] != capability_hash
                    or not set(PURPOSES[:2]) <= images.keys() or tuple(dispatches) != PURPOSES[:2]): _refuse()
            ready = True
        elif event == 'engine_start_requested':
            if not ready or started or tuple(dispatches) != PURPOSES or set(images) != set(PURPOSES): _refuse()
            started = True
        elif event in ('engine_event', 'fixture_event', 'worker_complete'):
            if not started: _refuse()
            if event == 'worker_complete': completed = True
        else: _refuse()
    if not all((sealed, endpoints, ready, started, completed, drained)): _refuse()
    joins, decisions, incarnations = [], [], set()
    for purpose in PURPOSES:
        dispatch_packet, image_packet = dispatches[purpose], images[purpose]
        dispatch, image = dispatch_packet['body'], image_packet['body']
        if any(dispatch[key] != image[key] for key in ('nonce', 'native_pid', 'native_birth')): _refuse()
        incarnation = image['native_pid'], image['native_birth']
        if incarnation in incarnations or image['native_pid'] == binding['worker_pid']: _refuse()
        incarnations.add(incarnation)
        wire = {'version': 2, 'sequence': image_packet['source_sequence'],
            **{key: binding[key] for key in ('launch_nonce', 'worker_pid', 'worker_birth')}, **image}
        joined = {'version': 2, **{key: binding[key] for key in ('launch_nonce', 'worker_pid', 'worker_birth')},
            'purpose': purpose, **{key: dispatch[key] for key in ('nonce', 'native_pid', 'native_birth', 'dispatch_hash')},
            'observation_hash': image['observation_hash'], 'dispatch': dispatch['dispatch'], 'image': wire}
        joins.append(joined)
        if read_decision is not None:
            decision = _copy(read_decision(_copy(joined)))
            _fields(decision, {'decision', 'durable_evidence_hash'}); _digest(decision['durable_evidence_hash'])
            if type(decision['decision']) is not str or decision['decision'] not in ('allow', 'deny'): _refuse()
            decisions.append(decision)
    authorization = 'unknown' if not decisions else 'pass' if all(item['decision'] == 'allow' for item in decisions) else 'fail'
    checks = [_row('native_trace', 'pass', 'native_records_consistent', query_environment_relation='unknown',
        query_environment_required_basis='qualified_parent_frozen_environment_check'),
        _row('native_authorization', authorization, 'durable_image_decisions_' + ('unread' if not decisions else 'checked'))]
    from improvement_native_qualifications import profile_qualification
    qualification = profile_qualification(pin, sys.platform)
    checks.append(_row('native_qualification', 'pass' if qualification else 'unknown',
        'qualified_source_record_consistency' if qualification else 'native_profile_unqualified',
        qualification_hash=qualification, loaded_pages='unknown', comprehension='unknown'))
    receipts = [body['event'].get('receipt') for body in bodies if body['type'] == 'engine_event'
        and body['event'].get('type') == ('installation_receipt' if kind == 'trial' else 'operation_installation_receipt')]
    proof = receipts[0].get('native_input_delivery') if len(receipts) == 1 and type(receipts[0]) is dict else None
    if proof is not None:
        from improvement_native_profile import validate_input_delivery
        proof = validate_input_delivery(proof, kind=kind, identity=binding['identity'], data_hash=data_hash, user_prompt=user_prompt)
        query = dispatches['query']['body']
        if (proof['native_pid'] != query['native_pid'] or proof['native_birth'] != query['native_birth']
                or proof['dispatch_nonce'] != query['nonce'] or proof['dispatch_hash'] != query['dispatch_hash']): _refuse()
    checks.append(_row('native_input_delivery', 'pass' if proof is not None else 'unknown',
        'original_stream_write_consistency' if proof is not None else 'native_input_delivery_missing',
        native_read_ack='unknown', provider_acceptance='unknown', comprehension='unknown'))
    return {'binding': _copy(binding), 'worker_bodies': bodies, 'joins': joins, 'decisions': decisions, 'checks': checks}


def require_durable_allow(result):
    """Publication requires all four independently reread stored allows."""
    if len(result['decisions']) != 4 or any(item['decision'] != 'allow' for item in result['decisions']):
        raise PermissionError('native_durable_allow_missing')


def validated_history(rows, decode, *, kind, receipt):
    """Decode complete encrypted history through the existing strict owner API."""
    from improvement_observation_history import validate_history
    packets = [decode(row) for row in rows]
    if not rows or any(row['late'] or row['sequence'] != number for number, row in enumerate(rows, 1)):
        _refuse()
    by_sequence = {row['sequence']: packet for row, packet in zip(rows, packets)}
    validate_history(rows, lambda row: by_sequence[row['sequence']], kind=kind, receipt=receipt)
    return packets


def reread_native_decisions(packets, *, kind, receipt, read_decision):
    """Cold historical join over already authenticated complete encrypted history.

    The result owner must match its immutable published trace fingerprint first.
    Raw prompts are not reconstructed after workspace cleanup. Publication's
    original semantic checks remain bound by that exact trace, while this read
    independently authenticates actual durable decisions again.
    """
    binding = observation_binding(packets[0], kind=kind, receipt=receipt)
    dispatches, images = {}, {}
    for packet in packets:
        body = packet['body']
        if body['type'] in ('dispatch_observed', 'image_observed'):
            table = dispatches if body['type'] == 'dispatch_observed' else images
            if body['purpose'] in table: _refuse()
            table[body['purpose']] = packet
    if set(dispatches) != set(PURPOSES) or set(images) != set(PURPOSES): _refuse()
    actual = []
    for purpose in PURPOSES:
        dispatch, image_packet = dispatches[purpose]['body'], images[purpose]
        image = image_packet['body']
        if any(dispatch[key] != image[key] for key in ('nonce', 'native_pid', 'native_birth')): _refuse()
        wire = {'version': 2, 'sequence': image_packet['source_sequence'],
            **{key: binding[key] for key in ('launch_nonce', 'worker_pid', 'worker_birth')}, **image}
        joined = {'version': 2, **{key: binding[key] for key in ('launch_nonce', 'worker_pid', 'worker_birth')},
            'purpose': purpose, **{key: dispatch[key] for key in ('nonce', 'native_pid', 'native_birth', 'dispatch_hash')},
            'observation_hash': image['observation_hash'], 'dispatch': dispatch['dispatch'], 'image': wire}
        result = _copy(read_decision(joined))
        _fields(result, {'decision', 'durable_evidence_hash'}); _digest(result['durable_evidence_hash'])
        if type(result['decision']) is not str or result['decision'] not in ('allow', 'deny'): _refuse()
        actual.append(result)
    require_durable_allow({'decisions': actual})
    return actual
