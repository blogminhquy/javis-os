"""Native record consistency using synthetic captures; no native/provider use."""
from _paths import ROOT, SERVER  # noqa: F401

import copy
import hashlib
import importlib
import json
import subprocess
import unittest

from improvement_store import _hash, _json
import test_improvement_native_observation as G

try:
    trace_checks = importlib.import_module('improvement_native_trace_checks')
except ModuleNotFoundError as error:
    if error.name != 'improvement_native_trace_checks': raise
    trace_checks = None

PURPOSES = ('adapter_version', 'auth_status', 'sdk_version', 'query')
TOOLS = ['mcp__fixture__fixture_read', 'mcp__skill__skill_asset_read']


def sha(text): return hashlib.sha256(text.encode()).hexdigest()


def pin():
    return {'version': 1, 'provider': 'anthropic-cli', 'engine_id': 'claude-sdk', 'model': 'selected-model',
        'reasoning': 'high', 'cli_path': 'C:\\selected\\claude.exe', 'cli_hash': 'b' * 64,
        'cli_version': '2.1.309', 'sdk_version': '0.2.116', 'profile_version': 'engineering', 'profile_hash': 'e' * 64}


def query_policy(kind, configuration, workspace, system_prompt):
    return {'version': 2, **{key: configuration[key] for key in ('cli_path', 'model', 'reasoning')},
        'prompt_hash': sha(system_prompt), 'cwd': workspace['path'],
        'tools': TOOLS if kind == 'trial' else TOOLS[:1], 'tool_policy': 'pinned_skill' if kind == 'trial' else 'fixture_only'}


def dispatch(purpose, kind, configuration, workspace, system_prompt):
    from improvement_native_protocol import _ENV_FIXED, _ENV_PATHS
    environment = {**dict.fromkeys(_ENV_PATHS, 'engineering-private-path'), **_ENV_FIXED}
    if purpose == 'query':
        environment.update(CLAUDE_CODE_ENTRYPOINT='sdk-py', CLAUDE_AGENT_SDK_VERSION=configuration['sdk_version'], PWD=workspace['path'])
    policy = query_policy(kind, configuration, workspace, system_prompt)
    consistency = {'version': 1, 'argv_hash': 'a' * 64, 'command_line_hash': 'c' * 64,
        'cwd_hash': sha(workspace['path']), 'creationflags': 0x08000006}
    if purpose == 'query':
        consistency.update(version=2, verdict='pass', basis='query_argument_consistency',
            **{key: policy[key] for key in ('model', 'reasoning', 'prompt_hash', 'tools', 'tool_policy')},
            cli_path_hash=sha(configuration['cli_path']), settings_hash=_hash({'fastMode': False, 'disableAllHooks': True}),
            mcp_config_hash=_hash({'mcpServers': {name: {'type': 'sdk', 'name': name} for name in
                (('fixture', 'skill') if kind == 'trial' else ('fixture',))}}), expected_hash=_hash(policy),
            coverage=dict.fromkeys(('os_boundary', 'image', 'provider_acceptance', 'internal_reasoning'), 'unknown'))
    else:
        argv = [configuration['cli_path'], *{'adapter_version': ['--version'], 'auth_status': ['auth', 'status', '--json'],
            'sdk_version': ['-v']}[purpose]]
        consistency.update(argv_hash=_hash(argv), command_line_hash=sha(subprocess.list2cmdline(argv)))
    return {'version': 1, 'purpose': purpose, 'basis': 'native_argument_consistency',
        'argument_consistency': consistency, 'environment_hash': _hash(environment), 'source_policy_hash': configuration['profile_hash']}


def trace(kind='trial', workspace=None, configuration=None, events=None, system_prompt='system\r\n日本語'):
    workspace = workspace or {**G.receipt(kind), 'path': 'C:\\scratch\\attempt'}
    configuration = configuration or pin()
    identity = {key: workspace[key] for key in (('trial_id', 'attempt', 'input_hash') if kind == 'trial'
        else ('operation_id', 'attempt', 'role', 'purpose', 'input_hash'))}
    values, counters = [], {'guardian': 0, 'worker': 0}
    def add(source, body):
        counters[source] += 1
        value = G.packet(copy.deepcopy(body), sequence=len(values) + 1, source=source, source_sequence=counters[source])
        values.append(value)
        return value
    add('guardian', G.offer()['body'])
    add('guardian', {'type': 'stdio_sealed', 'all_data_pipes_closed': True})
    add('worker', {'type': 'endpoints_adopted'})
    for index, purpose in enumerate(PURPOSES):
        invocation = G.invocations()[index]
        observed = G.image()['body']; observed.update(purpose=purpose, nonce=invocation['nonce'],
            native_pid=500 + index, native_birth=600 + index, native_tid=700 + index, native_thread_birth=800 + index)
        observed['comparison']['selected']['sha256'] = configuration['cli_hash']
        observed['comparison']['actual']['sha256'] = configuration['cli_hash']
        material = {key: values[0][key] for key in ('launch_nonce', 'worker_pid', 'worker_birth')}
        material.update({key: item for key, item in observed.items() if key not in ('type', 'observation_hash')})
        observed['observation_hash'] = hashlib.sha256(G.canonical(material, ascii=True)).hexdigest()
        # Guardian is intentionally published before the matching worker dispatch.
        add('guardian', observed)
        selected = dispatch(purpose, kind, configuration, workspace, system_prompt)
        add('worker', {'type': 'dispatch_observed', 'purpose': purpose, 'nonce': invocation['nonce'],
            'native_pid': observed['native_pid'], 'native_birth': observed['native_birth'],
            'dispatch_hash': _hash(selected), 'dispatch': selected})
        if index == 1: add('worker', {'type': 'worker_ready', **identity, 'capability_hash': 'd' * 64})
    add('worker', {'type': 'engine_start_requested', **identity})
    for event in events or []: add('worker', {'type': 'engine_event', **identity, 'event': event})
    add('worker', {'type': 'worker_complete', **identity, 'tool_denials': [], **({'fixture_events': []} if kind == 'trial' else {})})
    add('guardian', {'type': 'drained', 'root_terminal': True, 'debug_exit': True, 'job_active': 0,
        'guards_closed': True, 'reason': 'completed'})
    return values


def delivery(kind, workspace, packets, user_prompt='user\r\n日本語', data_hash='c' * 64):
    from improvement_native_profile import _frame
    query = next(value['body'] for value in packets if value['body']['type'] == 'dispatch_observed' and value['body']['purpose'] == 'query')
    identity = {key: workspace[key] for key in (('trial_id', 'attempt', 'input_hash') if kind == 'trial'
        else ('operation_id', 'attempt', 'role', 'purpose', 'input_hash'))}
    return {'version': 1, 'basis': 'qualified_original_stdin_write', 'kind': kind, 'identity': identity,
        'data_hash': data_hash, 'user_prompt_hash': sha(user_prompt), 'user_frame_hash': sha(_frame(user_prompt)),
        'write_nonce': '9' * 64, 'wire_session_id': 'default', 'native_pid': query['native_pid'],
        'native_birth': query['native_birth'], 'dispatch_nonce': query['nonce'], 'dispatch_hash': query['dispatch_hash'],
        'coverage': {'stdin': 'completed_original_stream_write', 'native_read_ack': 'unknown',
            'provider_acceptance': 'unknown', 'comprehension': 'unknown'}}


class NativeTraceChecksTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(trace_checks, 'independent native trace consumer missing')
        self.workspace = {**G.receipt(), 'path': 'C:\\scratch\\attempt'}
        self.packets = trace()

    def check(self, packets=None, reader=lambda joined: {'decision': 'allow', 'durable_evidence_hash': 'a' * 64}):
        return trace_checks.validate_native_trace(self.packets if packets is None else packets, kind='trial',
            receipt=self.workspace, pin=pin(), capability_hash='d' * 64, system_prompt='system\r\n日本語',
            user_prompt='user\r\n日本語', data_hash='c' * 64, read_decision=reader)

    def test_complete_trace_joins_actual_source_sequences_and_keeps_unknown_qualification(self):
        result = self.check()
        self.assertEqual(len(result['joins']), 4)
        images = [value for value in self.packets if value['body']['type'] == 'image_observed']
        self.assertEqual([value['image']['sequence'] for value in result['joins']], [value['source_sequence'] for value in images])
        self.assertEqual(result['worker_bodies'][0], {'type': 'endpoints_adopted'})
        self.assertEqual(next(row for row in result['checks'] if row['id'] == 'native_qualification')['verdict'], 'unknown')
        result['worker_bodies'].clear(); self.assertTrue(self.check()['worker_bodies'])

    def test_missing_denied_or_unread_decision_never_becomes_native_gate_pass(self):
        for reader in (None, lambda _: {'decision': 'deny', 'durable_evidence_hash': 'a' * 64}):
            result = self.check(reader=reader)
            self.assertNotEqual(next(row for row in result['checks'] if row['id'] == 'native_authorization')['verdict'], 'pass')
        def missing(_): raise PermissionError('missing')
        with self.assertRaises(PermissionError): self.check(reader=missing)

    def test_global_source_incarnation_replay_and_version_mix_refuse(self):
        for index, key, value in ((2, 'source_sequence', 7), (3, 'worker_birth', 401), (4, 'sequence', 2), (4, 'version', 1)):
            packets = copy.deepcopy(self.packets); packets[index][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError): self.check(packets)

    def test_startup_and_terminal_gates_refuse_missing_seal_ready_complete_or_drain(self):
        for kind in ('stdio_sealed', 'endpoints_adopted', 'worker_ready', 'worker_complete', 'drained'):
            packets = [copy.deepcopy(value) for value in self.packets if value['body']['type'] != kind]
            counters = {'guardian': 0, 'worker': 0}
            for number, value in enumerate(packets, 1):
                counters[value['source']] += 1; value.update(sequence=number, source_sequence=counters[value['source']])
            with self.subTest(kind=kind), self.assertRaises(ValueError): self.check(packets)

    def test_foreign_image_dispatch_and_query_pin_drift_refuse_even_rehashed(self):
        for key, value in (('model', 'foreign'), ('reasoning', 'medium'), ('prompt_hash', 'f' * 64), ('expected_hash', 'f' * 64)):
            packets = copy.deepcopy(self.packets)
            query = next(p['body'] for p in packets if p['body']['type'] == 'dispatch_observed' and p['body']['purpose'] == 'query')
            query['dispatch']['argument_consistency'][key] = value; query['dispatch_hash'] = _hash(query['dispatch'])
            with self.subTest(key=key), self.assertRaises(ValueError): self.check(packets)
        packets = copy.deepcopy(self.packets)
        next(p['body'] for p in packets if p['body']['type'] == 'dispatch_observed')['native_birth'] += 1
        with self.assertRaises(ValueError): self.check(packets)

    def test_input_delivery_requires_matching_query_incarnation_not_a_consistent_foreign_write(self):
        proof = delivery('trial', self.workspace, self.packets)
        event = {'type': 'installation_receipt', 'receipt': {'native_input_delivery': proof}}
        packets = trace(events=[event]); result = self.check(packets)
        self.assertEqual(next(row for row in result['checks'] if row['id'] == 'native_input_delivery')['verdict'], 'pass')
        proof['native_birth'] += 1
        with self.assertRaises(ValueError): self.check(trace(events=[event]))

    def test_consistent_wrong_source_policy_cannot_replace_selected_profile_pin(self):
        packets = copy.deepcopy(self.packets)
        for packet in packets:
            if packet['body']['type'] == 'dispatch_observed':
                packet['body']['dispatch']['source_policy_hash'] = 'f' * 64
                packet['body']['dispatch_hash'] = _hash(packet['body']['dispatch'])
        with self.assertRaises(ValueError): self.check(packets)

    def test_sdk_query_environment_hash_may_differ_from_frozen_preflight_environment(self):
        dispatches = [packet['body']['dispatch'] for packet in self.packets if packet['body']['type'] == 'dispatch_observed']
        self.assertEqual(len({value['environment_hash'] for value in dispatches[:3]}), 1)
        self.assertNotEqual(dispatches[0]['environment_hash'], dispatches[3]['environment_hash'])
        result = self.check()
        row = next(item for item in result['checks'] if item['id'] == 'native_trace')
        self.assertEqual(row['verdict'], 'pass')
        self.assertEqual(row['evidence']['query_environment_relation'], 'unknown')
        self.assertEqual(row['evidence']['query_environment_required_basis'], 'qualified_parent_frozen_environment_check')

    def test_first_three_environment_hash_mismatch_is_still_refused(self):
        packets = copy.deepcopy(self.packets)
        value = next(packet['body'] for packet in packets if packet['body']['type'] == 'dispatch_observed'
            and packet['body']['purpose'] == 'sdk_version')
        value['dispatch']['environment_hash'] = 'f' * 64; value['dispatch_hash'] = _hash(value['dispatch'])
        with self.assertRaises(ValueError): self.check(packets)


class TrialFourConsumerTests(unittest.TestCase):
    def records(self):
        from test_improvement_trial_checks import TrialChecksTests
        from improvement_sandbox import _effective_hash, trial_system_prompt
        from improvement_read_outcome_broker import PinnedReadOutcomeBroker
        from improvement_read_outcome_proof import correlate_read_outcomes
        record = TrialChecksTests(); record.setUp()
        view = {'view_id': 'view-a', 'view_hash': 'a' * 64, 'binding_hash': 'b' * 64}
        record.manifest.update(version=4, effective_view=view)
        record.request.update(version=4, view=view, lineage={
            'version': 1, 'context_id': 'context-a', 'definition_hash': 'd' * 64,
            'comparison_id': 'comparison-a', 'comparison_hash': 'e' * 64, 'matrix_hash': 'f' * 64,
            'arm_ordinal': 1, 'arm_hash': record.request['pins']['candidate_bundle_hash'],
            'candidate_id': 'candidate-a', 'pair_id': '1' * 64, 'cell_position': 0})
        configuration = pin(); record.request['engine_config'] = configuration
        record.request['pins']['engine_config_hash'] = record.manifest['engine_config_hash'] = _hash(configuration)
        record.workspace.update(input_hash=_hash(record.manifest), effective_hash=_effective_hash(record.manifest))
        receipt = record.receipt
        receipt.update(version=4, effective_view=view, input_hash=record.workspace['input_hash'],
            effective_hash=record.workspace['effective_hash'], engine_config_hash=_hash(configuration),
            expected_system_prompt_hash=sha(trial_system_prompt(record.manifest)), system_prompt_hash=sha(trial_system_prompt(record.manifest)),
            tool_inventory_hash=_hash(TOOLS), observed_tool_inventory_hash=_hash(TOOLS), actual_models=[configuration['model']])
        receipt['requested'] = {key: configuration[key] for key in ('provider', 'model', 'reasoning')}
        receipt['asset_revisions'][0]['observed_use'] = 'observed'
        record.events[0]['data']['tools'] = TOOLS
        record.events[1]['model'] = configuration['model']; record.events[-1]['actual_models'] = [configuration['model']]
        broker = PinnedReadOutcomeBroker(record.manifest, **{key: record.workspace[key] for key in ('trial_id', 'attempt', 'input_hash')})
        asset = record.manifest['assets'][0]
        args = {'view_id': view['view_id'], 'view_hash': view['view_hash'], 'asset_id': asset['id'], 'content_hash': asset['hash']}
        response = broker.read(TOOLS[1], args)
        record.events[2:2] = [
            {'type': 'tool_call', 'id': 'native-read', 'name': TOOLS[1], 'input': args, 'session_id': 'session-1'},
            {'type': 'trial_read_broker_observation', 'observation': broker.observations[-1], 'session_id': 'session-1'},
            {'type': 'tool_result', 'id': 'native-read', 'content': [{'type': 'text', 'text': _json(response)}],
                'is_error': None, 'native_is_error': None, 'session_id': 'session-1'}]
        receipt['read_outcome_proofs'] = correlate_read_outcomes(record.manifest, record.workspace, record.events)['proofs']
        record.rebuild_packets(fixture=[])
        prompt = _json({'task': record.manifest['case']['task'], 'fixtures': [
            {key: item[key] for key in ('snapshot_id', 'source')} for item in record.manifest['case']['fixtures']]})
        packets = trace(workspace=record.workspace, configuration=configuration, events=record.events,
            system_prompt=trial_system_prompt(record.manifest))
        # This profile capability is part of both ready and receipt pins.
        next(p['body'] for p in packets if p['body']['type'] == 'worker_ready')['capability_hash'] = record.capability
        receipt['native_input_delivery'] = delivery('trial', record.workspace, packets, prompt, record.workspace['input_hash'])
        event = next(p['body']['event'] for p in packets if p['body'].get('event', {}).get('type') == 'installation_receipt')
        event.update(receipt=copy.deepcopy(receipt), hash=_hash(receipt))
        return record, packets

    def test_actual_trial_checks_consume_four_raw_read_outcomes_without_rewriting_optional_error(self):
        from improvement_trial_checks import execution_invariants
        record, packets = self.records()
        checks = {row['id']: row for row in execution_invariants(record.request, record.manifest, record.workspace,
            packets, record.capability, contract=record.contract, read_decision=lambda _: {'decision': 'allow', 'durable_evidence_hash': 'a' * 64})}
        for name in ('worker_protocol', 'installation', 'asset_observed_use', 'native_input_delivery', 'completion'):
            self.assertEqual(checks[name]['verdict'], 'pass', checks)
        self.assertEqual(checks['actual_reasoning']['verdict'], 'unknown')
        self.assertEqual(checks['native_qualification']['verdict'], 'unknown')
        self.assertIs(next(p['body']['event'] for p in packets if p['body'].get('event', {}).get('type') == 'tool_result')['is_error'], None)

    def test_manifest_four_legacy_worker_envelope_cannot_pass_without_native_guards(self):
        from improvement_trial_checks import execution_invariants
        record, _ = self.records()
        checks = execution_invariants(record.request, record.manifest, record.workspace, record.packets,
            record.capability, contract=record.contract)
        self.assertTrue(any(row['verdict'] == 'fail' for row in checks))

    def test_receipt_four_summary_cannot_replace_contradictory_raw_native_outcome(self):
        from improvement_trial_checks import execution_invariants
        record, packets = self.records()
        event = next(p['body']['event'] for p in packets if p['body'].get('event', {}).get('type') == 'tool_result')
        event['is_error'] = event['native_is_error'] = True
        checks = {row['id']: row for row in execution_invariants(record.request, record.manifest, record.workspace,
            packets, record.capability, contract=record.contract, read_decision=lambda _: {'decision': 'allow', 'durable_evidence_hash': 'a' * 64})}
        self.assertEqual(checks['asset_observed_use']['verdict'], 'fail')
        self.assertIs(event['native_is_error'], True)


if __name__ == '__main__': unittest.main()
