"""Independent cold-lineage and owner lifetime controls; no native readiness.

The borrowed positive stream is explicitly the unexecuted storage control from
CompositionTests. No account/model/CLI invocation or registry is introduced.
"""
from _paths import ROOT, SERVER  # noqa: F401

import asyncio
import json
import threading
import unittest
from contextlib import closing
from unittest.mock import patch

from improvement_operation_adapter import ClaudeOperationAdapter
import test_improvement_compositions as source
import test_improvement_compose_admission as admission
import turn_context


class ComposeMetadataTests(unittest.TestCase):
    def test_actual_usage_identity_accepts_only_the_closed_composer_purpose_pair(self):
        value = {'experiment_id': 'compose-experiment', 'operation_id': 'compose-operation', 'attempt': 1,
            'execution_id': 'improvement_operation:compose-operation', 'role': 'composer',
            'purpose': 'improve_compose', 'learning_origin': 'compose'}
        self.assertEqual(turn_context.execution_metadata(value), value)
        for change in ({'purpose': 'improve_propose'}, {'purpose': 'improve_evaluate'}, {'role': 'improver'},
                       {'trial_id': 'foreign-trial'}, {'native_ready': True}):
            with self.subTest(change=change):
                self.assertIsNone(turn_context.execution_metadata({**value, **change}))


class CompositionBoundaryTests(unittest.IsolatedAsyncioTestCase):
    setUp = source.CompositionTests.setUp
    close_services = source.CompositionTests.close_services
    new_fixture = source.CompositionTests.new_fixture
    output = source.CompositionTests.output
    adapter = source.CompositionTests.adapter
    service = source.CompositionTests.service
    compose = source.CompositionTests.compose
    rows = source.CompositionTests.rows
    assert_no_composition = source.CompositionTests.assert_no_composition

    def read_draft(self, candidate):
        with closing(self.store._conn()) as connection:
            return self.read_draft_in(connection, candidate)

    def read_draft_in(self, connection, candidate):
        authoring = self.execution.plans.authoring
        state = authoring._state(connection, self.owner, candidate['experiment_id'], candidate['target_id'],
            candidate['base_revision_id'], candidate['base_hash'])
        observed, raw = authoring.observe(self.owner, state['target'])
        return authoring.read_proposal(connection, self.owner, candidate, state, observed, raw)

    async def test_missing_durable_decision_or_observation_refuses_the_composed_proposal_reader(self):
        service = self.service()
        self.raw = json.dumps(self.output(), ensure_ascii=False)
        result = await self.compose(service)
        self.assertEqual(result['status'], 'candidate_staged', result)
        candidate = self.rows('improvement_skill_candidates')[-1]
        self.read_draft(candidate)
        with closing(self.store._conn()) as connection:
            event = connection.execute("SELECT result_json FROM improvement_events WHERE operation='native_image_decision' LIMIT 1").fetchone()
            decision = json.loads(event[0])['blob_hashes'][0]
            observation = connection.execute('SELECT blob_hashes_json FROM improvement_operation_observations '
                'WHERE operation_id=? ORDER BY sequence LIMIT 1', (result['operation_id'],)).fetchone()
            observation = json.loads(observation[0])[0]
        for kind, digest in (('decision', decision), ('observation', observation)):
            path = self.assets.blobs._path(self.owner.brain_id, digest)
            ciphertext = path.read_bytes()
            try:
                path.unlink()
                with self.subTest(kind=kind):
                    # Control proves that the original native result reader
                    # actually detects this removed original encrypted record.
                    with self.assertRaises(admission.DENIED):
                        service.products.read(self.owner, result['operation_id'], 1)
                    with self.assertRaises(admission.DENIED):
                        self.read_draft(candidate)
            finally:
                path.write_bytes(ciphertext)
        self.read_draft(candidate)
        class RollbackControl(Exception): pass
        for column, value in (('mirror_ref', 'foreign-compose-call'), ('model', 'foreign-compose-model')):
            with self.subTest(column=column), self.assertRaises(RollbackControl), self.store._Tx(self.store) as connection:
                connection.execute('UPDATE agent_calls SET ' + column + '=? WHERE purpose=?', (value, 'improve_compose'))
                with self.assertRaises(admission.DENIED):
                    self.read_draft_in(connection, candidate)
                raise RollbackControl()
        self.read_draft(candidate)
        self.assertEqual(self.queries, 1)

    async def test_same_event_concurrent_callers_share_one_actual_owned_compose(self):
        service = self.service()
        left, right = await asyncio.gather(self.compose(service), self.compose(service))
        self.assertEqual(left, right)
        self.assertEqual(left['status'], 'keep_base', left)
        self.assertEqual((self.queries, self.adapter_closes), (1, 1))
        self.assertEqual(len(self.rows('improvement_operations')), 1)
        self.assertEqual(len(self.rows('improvement_compositions')), 1)

    async def test_close_drains_cancelled_slow_verifier_and_refuses_post_close_creation(self):
        service = self.service()
        entered, release, exited = threading.Event(), threading.Event(), threading.Event()
        def slow_verifier(adapter):
            entered.set()
            try:
                if not release.wait(10):
                    raise AssertionError('Synthetic verifier was not released')
                return {'supported': True, 'capability_hash': 'c' * 64}
            finally:
                exited.set()
        with patch.object(ClaudeOperationAdapter, 'verify', slow_verifier):
            task = asyncio.create_task(self.compose(service))
            try:
                self.assertTrue(await asyncio.to_thread(entered.wait, 5), 'Actual admission must reach verifier seam')
                task.cancel()
                closing_task = asyncio.create_task(service.close())
                await asyncio.sleep(0.05)
                self.assertFalse(closing_task.done(), 'Close must retain the actual blocked verifier owner')
                self.assertFalse(exited.is_set())
            finally:
                release.set()
            result = await asyncio.gather(task, closing_task, return_exceptions=True)
        self.assertIsInstance(result[0], asyncio.CancelledError)
        self.assertIs(result[1], True)
        self.assertTrue(exited.is_set(), 'Verifier thread must settle before close returns')
        self.assertEqual(self.rows('improvement_operations'), [])
        self.assertEqual(self.queries, 0)
        self.f.assert_no_new_call()
        self.assert_no_composition()


if __name__ == '__main__': unittest.main()
