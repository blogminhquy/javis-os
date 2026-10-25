"""Actual SQL/usage runner ownership with synthetic observation2 adapters only."""
from _paths import ROOT, SERVER  # noqa: F401

import asyncio
import copy
import unittest
from contextlib import closing
from unittest.mock import patch

import improvement_store as IM
from improvement_operation_runner import OperationRunner
from improvement_telemetry import NativeUsageRecorder
from improvement_trial_runner import TrialRunner
from improvement_claude import ClaudeTrialAdapter
from improvement_operation_adapter import ClaudeOperationAdapter
import test_improvement_trials as T
import test_improvement_operation_execution as O
import test_improvement_native_observation as G
import usage_store as US
import usage_index as UI


class RunnerEvidenceCases:
    def setUp(self):
        self.fixture = T.TrialStoreTests() if self.kind == 'trial' else O.OperationExecutionTests()
        self.fixture.setUp(); self.addCleanup(self.fixture.doCleanups)
        self.owner = self.fixture.owner
        if self.kind == 'trial':
            self.execution = self.fixture.trials
            self.row = self.fixture.reserve()
            original = self.execution._materialization
            def native_manifest(*args, **kwargs):
                value = original(*args, **kwargs)
                return {**value, 'version': 4, 'effective_view': {
                    'view_id': 'engineering-view', 'view_hash': '8' * 64, 'binding_hash': '9' * 64}}
            self.enterContext(patch.object(self.execution, '_materialization', side_effect=native_manifest))
        else:
            self.execution = self.fixture.execution(); self.row = self.fixture.reserve(self.execution)
            original = self.execution.materialize
            self.enterContext(patch.object(self.execution, 'materialize',
                side_effect=lambda *args, **kwargs: {**original(*args, **kwargs), 'version': 2}))
        self.identifier = self.row[self.kind + '_id']
        self.assets = self.execution.assets
        self.observed, self.finished, self.sent = [], [], []
        self.mode, self.revoked, self.mutate_interpretation = 'normal', False, False
        self.entered, self.release = asyncio.Event(), asyncio.Event()
        self.closing_entered, self.closing_release = asyncio.Event(), asyncio.Event()
        self.closing_release.set()
        self.closed = False
        root = self.assets.store.path.parent
        for obj, name, value in ((US, '_PATH', root / 'native-runner-usage.json'),
                (US, '_EVENTS_PATH', root / 'native-runner-events.jsonl'), (US, '_TELEMETRY_ERRORS', {}),
                (UI, '_EVENTS_PATH', root / 'native-runner-events.jsonl'), (UI, 'DB_PATH', root / 'native-runner-index.db'),
                (UI, '_claude_dir', lambda: str(root / 'empty-native')), (UI, '_codex_dir', lambda: str(root / 'empty-codex'))):
            self.enterContext(patch.object(obj, name, value))
        if self.kind == 'trial':
            self.runner = TrialRunner(self.execution, context_loader=lambda p, r: copy.deepcopy(self.fixture.context),
                live_guard=self.guard, adapter_factory=self.adapter, recorder_factory=self.recorder)
        else:
            self.runner = OperationRunner(self.execution, adapter_factory=self.adapter, recorder_factory=self.recorder)

    def guard(self, principal, request):
        value = {key: request[key] for key in ('baseline_context_hash', 'target_generations')}
        value.update({key: request['pins'][key] for key in ('scope_hash', 'grant_hash', 'engine_config_hash')})
        return {**value, 'grant_hash': 'f' * 64} if self.revoked else value

    def recorder(self, *args, **kwargs):
        real, test = NativeUsageRecorder(*args, **kwargs), self
        class Recorder:
            def observe(self, event, *, sequence):
                real.observe(event, sequence=sequence)
                if test.mutate_interpretation and event.get('type') == 'usage':
                    event['usage']['input_tokens'] = 999
                test.observed.append((sequence, copy.deepcopy(event)))
            def finish(self, status):
                real.finish(status); test.finished.append(status)
        return Recorder()

    def adapter(self, pin, *, before_engine_start, **kwargs):
        test = self
        class Adapter:
            def verify(self): return {'supported': True, 'capability_hash': 'c' * 64}
            async def execute(self, request, receipt, *, on_closing_observations=None):
                test.assertTrue(callable(on_closing_observations), 'native closing evidence callback missing')
                identity = {key: receipt[key] for key in (('trial_id', 'attempt', 'input_hash') if test.kind == 'trial'
                    else ('operation_id', 'attempt', 'role', 'purpose', 'input_hash'))}
                def worker(number, source_number, body):
                    return G.packet({**identity, **body}, sequence=number, source='worker', source_sequence=source_number)
                def usage(tokens):
                    return {'type': 'usage', 'usage': {'input_tokens': tokens, 'output_tokens': None,
                        'cache_read_input_tokens': 0, 'cache_creation_input_tokens': 0}, 'session_id': 'runner-session'}
                closing_packets = []
                try:
                    if test.mode != 'missing_anchor':
                        first = G.offer(); test.sent.append(first); yield first
                        ready = worker(2, 1, {'type': 'worker_ready', 'capability_hash': 'c' * 64})
                        test.sent.append(ready); yield ready
                    await before_engine_start(); test.entered.set()
                    if test.mode == 'missing_anchor':
                        closing_packets = [worker(9, 7, {'type': 'engine_event', 'event': usage(19)})]
                        return
                    started = worker(3, 2, {'type': 'engine_start_requested'})
                    test.sent.append(started); yield started
                    event = worker(4, 3, {'type': 'engine_event', 'event': usage(11)})
                    test.sent.append(event); yield event
                    if test.mode == 'cancel': await test.release.wait()
                    if test.mode == 'timeout':
                        closing_packets = [worker(5, 4, {'type': 'engine_event', 'event': usage(19)})]
                        raise TimeoutError('controlled adapter deadline')
                    if test.mode in ('revoked', 'policy_off'):
                        test.revoked = test.mode == 'revoked'
                        test.assets.set_policy(test.owner, 'off', expected_version=0, event_key='native-runner-off')
                    error = test.mode == 'transient'
                    terminal = worker(6, 5, {'type': 'engine_event', 'event': {
                        'type': 'terminal', 'is_error': error, 'api_error_status': 503 if error else None,
                        'subtype': 'error_during_execution' if error else 'success'}})
                    complete = worker(7, 6, {'type': 'worker_complete', 'tool_denials': [],
                        **({'fixture_events': []} if test.kind == 'trial' else {})})
                    closing_packets = [worker(5, 4, {'type': 'engine_event', 'event': usage(19)}), terminal, complete,
                        G.packet({'type': 'drained', 'root_terminal': True, 'debug_exit': True,
                            'job_active': 0, 'guards_closed': True, 'reason': 'completed'}, sequence=8, source_sequence=2)]
                finally:
                    if not closing_packets and test.mode != 'missing_anchor':
                        closing_packets = [worker(5, 4, {'type': 'engine_event', 'event': usage(19)})]
                    test.closing_entered.set()
                    await test.closing_release.wait()
                    test.sent.extend(copy.deepcopy(closing_packets))
                    test.closed = True
                    await on_closing_observations(tuple(closing_packets))
        return Adapter()

    async def run_attempt(self): return await self.runner.run(self.owner, self.identifier)

    def rows(self):
        with closing(self.execution.store._conn()) as connection:
            return connection.execute('SELECT * FROM improvement_' + self.kind + '_observations WHERE ' +
                self.kind + '_id=? ORDER BY sequence', (self.identifier,)).fetchall()

    def read(self, sequence):
        if self.kind == 'trial': return self.execution.read_observation(self.owner, self.identifier, 1, sequence)
        return self.runner.evidence.read(self.owner, self.identifier, 1, sequence)

    def call(self): return self.execution.ledger.get(self.row['attempts'][0]['call_id'])

    async def test_active_raw_envelopes_and_closing_terminal_use_original_global_sequence(self):
        result = await self.run_attempt()
        self.assertTrue(self.closed)
        self.assertEqual([number for number, _ in self.observed], [4, 5, 6])
        self.assertIn('completed', self.finished, 'closing terminal was not consumed before evaluation')
        self.assertEqual([row['sequence'] for row in self.rows()], list(range(1, 9)))
        self.assertTrue(all(row['late'] == 0 for row in self.rows()))
        self.assertEqual(self.read(5), next(packet for packet in self.sent if packet['sequence'] == 5))
        self.assertEqual(self.read(5)['body']['event']['usage']['output_tokens'], None)
        self.assertNotEqual(result.get('result', {}).get('verdict') if result.get('result') else None, 'pass')

    async def test_cancel_waits_for_closing_callback_and_keeps_usage_before_lock_release(self):
        self.mode = 'cancel'; self.closing_release.clear()
        task = asyncio.create_task(self.run_attempt())
        try:
            await asyncio.wait_for(self.entered.wait(), 15)
            task.cancel()
            await asyncio.wait_for(self.closing_entered.wait(), 15)
            task.cancel(); await asyncio.sleep(.05)
            self.assertFalse(task.done())
        finally:
            self.closing_release.set(); await asyncio.gather(task, return_exceptions=True)
        with self.assertRaises(asyncio.CancelledError): await task
        self.assertIn(5, [number for number, _ in self.observed])
        self.assertIsNotNone(self.call()['engine_at']); self.assertEqual(self.call()['counted'], 1)

    async def test_revoked_closing_batch_is_late_original_writer_history_not_current_success(self):
        self.mode = 'revoked'
        result = await self.run_attempt()
        self.assertNotEqual(result['status'], 'completed')
        self.assertEqual([number for number, _ in self.observed], [4, 5, 6])
        self.assertEqual([(row['sequence'], row['late']) for row in self.rows() if row['sequence'] >= 5],
                         [(5, 1), (6, 1), (7, 1), (8, 1)])
        self.assertEqual(self.read(5), next(packet for packet in self.sent if packet['sequence'] == 5))
        self.assertEqual(self.call()['status'], 'interrupted'); self.assertEqual(self.call()['counted'], 1)

    async def test_sql_policy_off_with_unchanged_live_hashes_still_makes_closing_evidence_late(self):
        self.mode = 'policy_off'
        result = await self.run_attempt()
        self.assertFalse(self.revoked, 'fixture must retain unchanged live-guard hashes')
        self.assertNotEqual(result['status'], 'completed')
        self.assertEqual([(row['sequence'], row['late']) for row in self.rows() if row['sequence'] >= 5],
                         [(5, 1), (6, 1), (7, 1), (8, 1)])
        self.assertIn(5, [number for number, _ in self.observed])

    async def test_active_storage_failure_retains_packet_and_all_closing_usage_then_late(self):
        append = self.execution.append_observation if self.kind == 'trial' else self.runner.evidence.append
        failed = []
        def fail_once(principal, identifier, value, **kwargs):
            if value['sequence'] == 4 and not kwargs.get('late') and not failed:
                failed.append(True); raise OSError('controlled actual writer unavailable')
            return append(principal, identifier, value, **kwargs)
        target, method = (self.execution, 'append_observation') if self.kind == 'trial' else (self.runner.evidence, 'append')
        with patch.object(target, method, side_effect=fail_once): result = await self.run_attempt()
        self.assertEqual(failed, [True]); self.assertNotEqual(result['status'], 'completed')
        self.assertIn(4, [number for number, _ in self.observed]); self.assertIn(5, [number for number, _ in self.observed])
        self.assertEqual(self.read(4), next(packet for packet in self.sent if packet['sequence'] == 4))
        self.assertEqual([(row['sequence'], row['late']) for row in self.rows() if row['sequence'] >= 4], [(4, 1), (5, 1)])

    async def test_missing_anchor_never_invents_history_but_preserves_marked_usage(self):
        self.mode = 'missing_anchor'
        result = await self.run_attempt()
        self.assertEqual(self.rows(), []); self.assertNotEqual(result['status'], 'completed')
        self.assertEqual([(number, event['usage']['input_tokens']) for number, event in self.observed], [(9, 19)])
        self.assertEqual(self.call()['counted'], 1); self.assertEqual(self.call()['status'], 'interrupted')

    async def test_recorder_mutation_cannot_change_original_pending_late_bytes(self):
        self.mutate_interpretation = True
        await self.test_active_storage_failure_retains_packet_and_all_closing_usage_then_late()

    async def test_adapter_timeout_settles_closing_usage_without_refund_or_success(self):
        self.mode = 'timeout'
        result = await self.run_attempt()
        self.assertEqual(result['attempts'][-1]['failure_reason'], 'timeout')
        self.assertEqual([number for number, _ in self.observed], [4, 5])
        self.assertEqual(self.read(5)['body']['event']['usage']['input_tokens'], 19)
        self.assertEqual(self.call()['counted'], 1); self.assertEqual(self.call()['status'], 'interrupted')

    async def test_concrete_adapter_uses_same_loop_async_verify_and_real_current_authority(self):
        adapter_type = ClaudeTrialAdapter if self.kind == 'trial' else ClaudeOperationAdapter
        captured, expected_loop = {}, asyncio.get_running_loop()
        test = self
        def bind(adapter, assets, principal, *, scope_hash, current, lock=None):
            captured.update(assets=assets, principal=principal, scope=scope_hash, current=current, lock=lock)
        async def verify_async(adapter):
            test.assertIs(asyncio.get_running_loop(), expected_loop)
            captured['same_loop'] = True
            async with captured['lock']:
                with test.execution.store._Tx(test.execution.store) as connection:
                    captured['decision'] = captured['current'](connection, None)
                test.assets.set_policy(test.owner, 'off', expected_version=0, event_key='native-callback-policy-off')
                with test.execution.store._Tx(test.execution.store) as connection:
                    try: captured['current'](connection, {'engineering': 'host validated elsewhere'})
                    except (PermissionError, IM.ConflictError): captured['revoked_refused'] = True
            raise OSError('stop after actual authority callback contract')
        self.runner.adapter_factory = lambda *args, **kwargs: adapter_type(*args, **kwargs)
        with patch.object(adapter_type, 'bind_native_authority', bind, create=True), \
                patch.object(adapter_type, 'verify_async', verify_async, create=True), \
                patch.object(adapter_type, 'verify', side_effect=AssertionError('concrete runner used sync verifier')):
            result = await self.run_attempt()
        self.assertTrue(captured.get('same_loop'), 'concrete adapter async verification not used')
        self.assertIs(captured['assets'], self.assets); self.assertIs(captured['principal'], self.owner)
        self.assertEqual(captured['decision'], 'allow'); self.assertTrue(captured.get('revoked_refused'))
        with closing(self.execution.store._conn()) as connection:
            row = connection.execute('SELECT request_hash FROM improvement_' + ('trials' if self.kind == 'trial' else 'operations')
                + ' WHERE id=?', (self.identifier,)).fetchone()
        config = self.fixture.request['engine_config'] if self.kind == 'trial' else self.execution.host.selected_engine()
        expected = IM._hash({'version': 1, 'kind': self.kind, 'brain_id': self.owner.brain_id,
            'subject_id': self.identifier, 'attempt': 1, 'request_hash': row['request_hash'],
            'engine_config_hash': IM._hash(config)})
        self.assertEqual(captured['scope'], expected)
        self.assertEqual(result['status'], 'not_run'); self.assertEqual(self.call()['status'], 'refunded')


class TrialNativeRunnerEvidenceTests(RunnerEvidenceCases, unittest.IsolatedAsyncioTestCase):
    kind = 'trial'


class OperationNativeRunnerEvidenceTests(RunnerEvidenceCases, unittest.IsolatedAsyncioTestCase):
    kind = 'operation'

    async def test_closing_transient_terminal_keeps_original_infrastructure_failure(self):
        self.mode = 'transient'
        result = await self.run_attempt()
        self.assertEqual(result['status'], 'interrupted')
        self.assertEqual(result['attempts'][-1]['failure_reason'], 'native_transient_error')
        self.assertEqual(self.read(6)['body']['event']['api_error_status'], 503)


if __name__ == '__main__': unittest.main()
