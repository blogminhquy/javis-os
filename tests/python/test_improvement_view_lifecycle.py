"""Stop/next consumers must own genuine v4 reservations, without native queries."""
from _paths import ROOT, SERVER  # noqa: F401

import json
import unittest
from contextlib import closing
from unittest.mock import patch

import improvement_store as IM
from improvement_experiment_service import ExperimentService
from improvement_experiment_admission import ExperimentAdmission
from improvement_experiment_protocol import matrix_cell
from improvement_claude import ClaudeTrialAdapter
from improvement_trial_service import OwnerTrialService
import test_improvement_view_reservations as reservations
import test_improvement_view_sources as sources


class ViewLifecycleTests(sources.SourceFixture, unittest.IsolatedAsyncioTestCase):
    request = reservations.ViewReservationTests.request
    load = reservations.ViewReservationTests.load
    bound = reservations.ViewReservationTests.bound
    live_request = reservations.ViewReservationTests.live_request

    def lifecycle(self):
        trials, metadata = self.bound()
        owner_service = OwnerTrialService(self.host)
        self.addAsyncCleanup(owner_service.close)
        service = ExperimentService(self.f.plans, owner_service)
        self.addAsyncCleanup(service.close)
        return trials, metadata, service

    async def test_stop_cancels_and_refunds_actual_view_trial_before_finishing_experiment(self):
        trials, metadata, service = self.lifecycle()
        request = self.live_request(metadata)
        reserved = trials.reserve(self.owner, request, event_key='view-lifecycle-genuine-reserve')
        self.host.revoke(self.owner, self.comparison['experiment_id'], expected_generation=1, event_key='view-lifecycle-revoke')
        self.assets.set_policy(self.owner, 'off', expected_version=0, event_key='view-lifecycle-off')
        with patch.object(self.host, '_snapshot_observe', side_effect=AssertionError('Stop cannot observe revoked sources')):
            stopped = await service.cancel(self.owner, self.comparison['experiment_id'],
                expected_generation=self.generation(), event_key='view-lifecycle-owner-stop')
        self.assertEqual(stopped['current']['phase'], 'cancelled')
        self.assertEqual(trials.get(self.owner, reserved['trial_id'])['status'], 'cancelled')
        with closing(self.assets.store._conn()) as connection:
            call = connection.execute('SELECT c.* FROM agent_calls c JOIN improvement_trial_attempts a ON a.call_id=c.id '
                'WHERE a.trial_id=? AND a.brain_id=?', (reserved['trial_id'], self.owner.brain_id)).fetchone()
        self.assertIsNone(call['engine_at'])
        self.assertEqual(call['status'], 'refunded')

    async def test_pending_actual_view_cell_cannot_be_omitted_by_next_slot_reader(self):
        trials, metadata, service = self.lifecycle()
        trials.reserve(self.owner, self.live_request(metadata), event_key='view-lifecycle-pending-reserve')
        with self.assertRaisesRegex(IM.ConflictError, 'pending|incomplete'):
            service._next_slot(self.owner, self.comparison['experiment_id'], self.comparison['id'],
                self.generation(), 'view-lifecycle-next-while-pending')

    async def test_terminal_actual_view_without_published_result_cannot_burn_next_cell(self):
        trials, metadata, service = self.lifecycle()
        reserved = trials.reserve(self.owner, self.live_request(metadata), event_key='view-lifecycle-cancel-before-query')
        trials.cancel(self.owner, reserved['trial_id'], expected_generation=reserved['generation'], event_key='view-lifecycle-cancel-one')
        with self.assertRaisesRegex(IM.ConflictError, 'pending|incomplete'):
            service._next_slot(self.owner, self.comparison['experiment_id'], self.comparison['id'],
                self.generation(), 'view-lifecycle-next-terminal-no-result')

    async def test_legacy_and_view_comparisons_share_one_actual_snapshot_budget(self):
        trials, metadata, service = self.lifecycle()
        plans = self.f.plans
        candidate = plans.authoring.stage(self.owner, self.comparison['experiment_id'],
            self.body_patch('Retain owner rules.\nCheck all unmatched rows in a second approach.\n'),
            event_key='view-lifecycle-second-genuine-draft')
        authority = plans.authoring.authorize_diff(self.owner, candidate['candidate_id'], expected_generation=1,
            before_hash=candidate['base_hash'], after_hash=candidate['content_hash'], event_key='view-lifecycle-second-exact-diff')
        arm = plans.bind_arm(self.owner, self.comparison['experiment_id'], candidate['candidate_id'], authority['authority_id'],
            expected_generation=self.generation(), event_key='view-lifecycle-second-arm')
        second = plans.freeze(self.owner, self.comparison['experiment_id'], arm['ordinal'], 'tuning',
            expected_generation=arm['generation'], event_key='view-lifecycle-second-legacy-comparison')
        matrix = json.loads(self.assets.blobs.read(self.owner.brain_id, second['matrix_hash']))
        position = next(index for index in range(second['cell_count']) if matrix_cell(matrix, index)['variant'] == 'baseline')
        with patch.object(ClaudeTrialAdapter, 'verify', return_value={'supported': True, 'capability_hash': 'c' * 64}):
            ExperimentAdmission(plans).admit(self.owner, self.comparison['experiment_id'], second['comparison_id'], position,
                expected_generation=self.generation(), event_key='view-lifecycle-genuine-legacy-reservation')
        trials.reserve(self.owner, self.live_request(metadata), event_key='view-lifecycle-genuine-view-reservation')
        with closing(self.assets.store._conn()) as connection:
            self.assertEqual(connection.execute('SELECT count(*) FROM improvement_experiment_trial_links').fetchone()[0], 1)
            self.assertEqual(connection.execute('SELECT count(*) FROM improvement_view_trial_links').fetchone()[0], 1)
            actual = service._snapshot(connection, self.owner.brain_id, self.comparison['experiment_id'])
            self.assertEqual({row['comparison_id'] for row in actual[0] if 'comparison_id' in row},
                {self.comparison['id'], second['comparison_id']})
            with patch('improvement_experiment_service.MAX_COMPARISON_TRIALS', 1), \
                    self.assertRaisesRegex(IM.ConflictError, 'experiment_trial_history_changed'):
                service._snapshot(connection, self.owner.brain_id, self.comparison['experiment_id'])


if __name__ == '__main__':
    unittest.main()
