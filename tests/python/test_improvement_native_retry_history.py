"""Actual bounded retry consumes stored observation2 infrastructure evidence."""
from _paths import ROOT, SERVER  # noqa: F401

import asyncio
from contextlib import closing
import unittest
from unittest.mock import patch

from improvement_operation_adapter import ClaudeOperationAdapter
import test_improvement_native_runner_evidence as fixture
import test_improvement_operation_execution as legacy_fixture


class NativeRetryHistoryTests(unittest.IsolatedAsyncioTestCase):
    kind = 'operation'
    setUp = fixture.RunnerEvidenceCases.setUp
    guard = fixture.RunnerEvidenceCases.guard
    recorder = fixture.RunnerEvidenceCases.recorder
    adapter = fixture.RunnerEvidenceCases.adapter
    run_attempt = fixture.RunnerEvidenceCases.run_attempt
    rows = fixture.RunnerEvidenceCases.rows
    call = fixture.RunnerEvidenceCases.call

    async def test_actual_observation2_transient_terminal_reserves_only_one_bounded_retry(self):
        self.mode = 'transient'
        first = await self.run_attempt()
        self.assertEqual(first['attempts'][-1]['failure_reason'], 'native_transient_error')
        self.assertTrue(all(self.read_raw(row)['version'] == 2 for row in self.rows()))
        original = self.call()
        self.assertEqual(original['status'], 'interrupted')
        self.assertIsNotNone(original['engine_at'])
        with patch.object(ClaudeOperationAdapter, 'verify', return_value={'supported': True, 'capability_hash': 'c' * 64}):
            second = await asyncio.to_thread(self.execution.retry, self.owner, self.identifier,
                expected_generation=first['generation'], event_key='native-v2-bounded-retry')
        self.assertEqual((second['status'], second['attempt']), ('reserved', 2))
        self.assertEqual(second['deadline_at'], first['deadline_at'])
        self.assertNotEqual(second['attempts'][-1]['call_id'], original['id'])
        self.assertEqual(self.execution.ledger.get(original['id'])['status'], 'interrupted')
        with patch.object(ClaudeOperationAdapter, 'verify', side_effect=AssertionError('retry replay probed')):
            self.assertEqual(await asyncio.to_thread(self.execution.retry, self.owner, self.identifier,
                expected_generation=first['generation'], event_key='native-v2-bounded-retry'), second)

    def read_raw(self, row):
        from improvement_trial_evidence import decode_trace
        return decode_trace(self.execution.blobs, self.owner.brain_id, row)


class LegacyRetryHistoryTests(unittest.TestCase):
    def test_legacy_transient_proof_does_not_eagerly_decrypt_non_engine_records(self):
        from improvement_operation_evidence import OperationEvidence
        import improvement_operation_retry as retry
        fixture = legacy_fixture.OperationExecutionTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        execution = fixture.execution()
        row, token, receipt = fixture.prepared(execution)
        evidence = OperationEvidence(execution)
        identity = {key: receipt[key] for key in ('operation_id', 'attempt', 'role', 'purpose', 'input_hash')}
        def append(sequence, kind, **extra):
            evidence.append(fixture.owner, row['operation_id'], {'version': 1, 'sequence': sequence,
                'type': kind, **identity, **extra}, expected_generation=row['generation'], lease_token=token)
        append(1, 'worker_ready', capability_hash='c' * 64)
        row = execution.start_engine(fixture.owner, row['operation_id'], expected_generation=row['generation'], lease_token=token)
        append(2, 'engine_start_requested')
        append(3, 'engine_event', event={'type': 'error', 'status_code': 503, 'error_type': 'ConnectionError'})
        with closing(execution.store._conn()) as connection:
            operation = execution._row(connection, fixture.owner, row['operation_id'])
            attempt = execution._attempt(connection, operation)
            trace = connection.execute('SELECT * FROM improvement_operation_observations WHERE operation_id=? ORDER BY sequence',
                                       (row['operation_id'],)).fetchall()
        original = retry.decode_trace
        def decode(blobs, brain, item):
            self.assertEqual(item['kind'], 'engine_event', 'legacy retry newly decrypted a non-engine record')
            return original(blobs, brain, item)
        with patch.object(retry, 'decode_trace', side_effect=decode):
            proof = retry.OperationRetry(execution)._native_proof(operation, attempt, trace)
        self.assertEqual(proof, [trace[2]['payload_hash']])


if __name__ == '__main__': unittest.main()
