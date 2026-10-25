"""Actual readonly ASGI outcomes; native packets are unexecuted storage controls."""
from _paths import ROOT, SERVER  # noqa: F401
import asyncio
import sqlite3
from contextlib import closing
from unittest.mock import patch
import unittest
from test_improvement_compose_api import ComposeApiTests


class ComposeOutcomeTests(ComposeApiTests):
    async def cold(self):
        self.live_service_allowed = False
        self.calls.clear()
        with patch.object(self.assets.blobs, 'read', side_effect=AssertionError('Cold cannot decrypt')), \
                patch('improvement_store.ensure', side_effect=AssertionError('Cold cannot migrate')), \
                patch('improvement_operation_adapter.ClaudeOperationAdapter.verify', side_effect=AssertionError('Cold cannot probe')):
            response = await self.request('GET', '/compose-outcomes')
        self.assertEqual(response.status_code, 200, response.text)
        self.assertNotIn('service', self.calls)
        self.assertNotIn('write', self.calls)
        self.assertNotIn(self.owner.brain_id, response.text)
        return response.json()['outcomes']

    async def test_empty_off_old_schema_and_foreign_reads_are_cold(self):
        self.assets.set_policy(self.owner, 'off', expected_version=0, event_key='outcomes-off-policy')
        self.assertEqual(await self.cold(), [])
        for version in (5, 6, 7):
            with closing(self.h.store._conn()) as connection:
                connection.execute('UPDATE improvement_schema SET version=? WHERE id=1', (version,))
                connection.commit()
            self.assertEqual(await self.cold(), [])
        self.assertEqual((await self.request('GET', '/compose-outcomes?brain=other')).status_code, 403)
        self.assertEqual((await self.client.get(self.base + '/compose-outcomes')).status_code, 403)
        self.assertEqual((await self.client.get('/improvement-experiments/unknown/compose-outcomes', headers={'cookie':'owner=yes'})).status_code, 403)

    async def test_interrupted_pending_start_is_recorded_without_replay(self):
        self.synthetic_native()
        payload = {'authorization_id': self.saved['authorization_id'], 'expected_generation': self.generation}
        begun = await asyncio.to_thread(self.service.composer._begin, self.owner, payload, 'cold-outcomes-interrupted')
        row, = await self.cold()
        self.assertEqual((row['status'], row['operation_status']), ('operation_recorded', 'pending'))
        self.assertEqual(row['operation_id'], begun['operation_id'])
        self.assertEqual(row['authority_status'], 'not_checked')
        self.assertFalse(row['business_proof'])
        self.assertEqual(self.h.queries, 0)
        current = self.service.records.get(self.owner, self.experiment)
        await self.service.cancel(self.owner, self.experiment, expected_generation=current['generation'],
                                  event_key='outcomes-stop-interrupted-start')
        stopped, = await self.cold()
        self.assertEqual((stopped['status'], stopped['operation_status']), ('operation_recorded', 'cancelled'))

    async def test_invalid_output_has_outcome_without_publication_and_current_revoked_grant(self):
        self.synthetic_native()
        self.h.raw = 'Malformed synthetic output'
        result = await self.control('compose', authorization_id=self.saved['authorization_id'])
        self.assertEqual(result['status'], 'invalid_output')
        await self.control('compose-revoke', authorization_id=self.saved['authorization_id'], expected_generation=1,
                           event_key='outcomes-revoke-after-invalid')
        self.assets.set_policy(self.owner, 'off', expected_version=0, event_key='outcomes-off-after-invalid')
        row, = await self.cold()
        self.assertEqual((row['status'], row['authorization_status']), ('invalid_output', 'revoked'))
        self.assertEqual(row['operation_id'], result['operation_id'])
        self.assertNotIn('candidates', row)
        self.assertEqual((await self.request('GET', '/compositions')).json()['compositions'], [])

    async def test_unknown_native_incomplete_is_not_qualified(self):
        self.synthetic_native(qualified=False)
        result = await self.control('compose', authorization_id=self.saved['authorization_id'])
        self.assertEqual(result['status'], 'native_incomplete')
        row, = await self.cold()
        self.assertEqual(row['status'], 'native_incomplete')
        self.assertFalse(row['business_proof'])

    async def test_keep_base_links_publication_and_rejects_ambiguous_history(self):
        self.synthetic_native()
        result = await self.control('compose', authorization_id=self.saved['authorization_id'])
        row, = await self.cold()
        self.assertEqual(row['status'], 'keep_base')
        self.assertEqual(row['composition_id'], result['composition_id'])
        with closing(self.h.store._conn()) as connection:
            with self.assertRaisesRegex(sqlite3.IntegrityError, 'immutable_improvement_history'):
                connection.execute("UPDATE improvement_events SET request_hash='bad' WHERE operation='compose_generate'")
            self.assets._event(connection, self.owner, 'outcomes-ambiguous-start', 'compose_generate_start',
                {'authorization_id': self.saved['authorization_id'], 'expected_generation': self.generation},
                {'experiment_id': self.experiment})
            connection.commit()
        response = await self.request('GET', '/compose-outcomes')
        self.assertEqual(response.status_code, 409, response.text)


for _base in ComposeApiTests.__mro__:
    for _name in vars(_base):
        if _name.startswith('test_') and _name not in vars(ComposeOutcomeTests):
            setattr(ComposeOutcomeTests, _name, None)
del ComposeApiTests

if __name__ == '__main__':
    unittest.main()
