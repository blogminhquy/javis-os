"""Actual resume/proposal/review/retry preflight fences without a native query."""
from _paths import ROOT, SERVER  # noqa: F401

from contextlib import closing
import unittest
from unittest.mock import patch

from improvement_claude import ClaudeTrialAdapter
from improvement_operation_adapter import ClaudeOperationAdapter
import test_improvement_experiment_service as resume_fixture
import test_improvement_proposals as proposal_fixture
import test_improvement_semantic_review as semantic_fixture
import test_improvement_operation_retry as retry_fixture


def counts(assets):
    with closing(assets.store._conn()) as connection:
        return tuple(connection.execute('SELECT COUNT(*) FROM ' + name).fetchone()[0]
                     for name in ('improvement_operations', 'improvement_operation_attempts', 'agent_calls'))


def revoked_verifier(test, assets, owner, *, trial=False):
    before = counts(assets)
    def verify(adapter):
        boundary = adapter._native_boundary if trial else adapter._native._native_boundary
        test.assertIsNotNone(boundary, 'actual role/resume preflight must bind current authority')
        test.assertIs(boundary.assets, assets)
        test.assertIs(boundary.principal, owner)
        test.assertEqual(counts(assets), before)
        with assets.store._Tx(assets.store) as connection:
            test.assertEqual(boundary.current(connection, None), 'allow')
        assets.set_policy(owner, 'off', expected_version=0, event_key='native-role-policy-revoked')
        with assets.store._Tx(assets.store) as connection:
            with test.assertRaises(PermissionError):
                boundary.current(connection, None)
        # The engineering verifier stops at the observed denial. No process is
        # created; the actual outer service retains its normal failure cleanup.
        raise PermissionError('engineering_observed_current_authority_denial')
    return verify


class ResumeAuthorityTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = resume_fixture.ExperimentServiceTests.asyncSetUp
    blocked = resume_fixture.ExperimentServiceTests.blocked
    current = resume_fixture.ExperimentServiceTests.current

    async def test_blocked_experiment_resume_rechecks_current_authority_without_transition_or_call(self):
        blocked = self.blocked()
        before = counts(self.assets)
        with patch.object(ClaudeTrialAdapter, 'verify', revoked_verifier(self, self.assets, self.owner, trial=True)):
            with self.assertRaisesRegex(PermissionError, 'engineering_observed_current_authority_denial'):
                await self.service.resume(self.owner, 'association-experiment', expected_generation=blocked['generation'],
                                          event_key='native-owner-resume')
        self.assertEqual(self.current()['phase'], 'blocked')
        self.assertEqual(self.current()['generation'], blocked['generation'])
        self.assertEqual(counts(self.assets), before)


class ProposalAuthorityTests(unittest.IsolatedAsyncioTestCase):
    setUp = proposal_fixture.ProposalTests.setUp
    factory = proposal_fixture.ProposalTests.factory
    prepare = proposal_fixture.ProposalTests.prepare
    adapter = proposal_fixture.ProposalTests.adapter
    body_patch = proposal_fixture.ProposalTests.body_patch
    service = proposal_fixture.ProposalTests.service
    generate = proposal_fixture.ProposalTests.generate

    async def test_proposal_preflight_rechecks_actual_snapshot_before_role_or_call_creation(self):
        subject = await self.service()
        before = counts(self.assets)
        with patch.object(ClaudeOperationAdapter, 'verify', revoked_verifier(self, self.assets, self.owner)):
            with self.assertRaisesRegex(PermissionError, 'engineering_observed_current_authority_denial'):
                await self.generate(subject)
        self.assertEqual(counts(self.assets), before)


class SemanticAuthorityTests(unittest.IsolatedAsyncioTestCase):
    setUp = semantic_fixture.SemanticReviewTests.setUp
    factory = semantic_fixture.SemanticReviewTests.factory
    prepare = semantic_fixture.SemanticReviewTests.prepare
    adapter = semantic_fixture.SemanticReviewTests.adapter
    body_patch = semantic_fixture.SemanticReviewTests.body_patch
    service = semantic_fixture.SemanticReviewTests.service
    review = semantic_fixture.SemanticReviewTests.review

    async def test_semantic_preflight_rechecks_candidate_source_before_role_or_call_creation(self):
        subject = await self.service()
        before = counts(self.assets)
        with patch.object(ClaudeOperationAdapter, 'verify', revoked_verifier(self, self.assets, self.owner)):
            with self.assertRaisesRegex(PermissionError, 'engineering_observed_current_authority_denial'):
                await self.review(subject)
        self.assertEqual(counts(self.assets), before)
        self.assertEqual(subject.history(self.owner, self.candidate['candidate_id']), [])


class RetryAuthorityTests(unittest.TestCase):
    def setUp(self):
        self.f = retry_fixture.OperationRetryTests()
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)

    def test_retry_preflight_rechecks_original_eligible_attempt_without_second_call(self):
        first = self.f.capacity_failure()
        assets, owner = self.f.execution.assets, self.f.owner
        before = counts(assets)
        with patch.object(ClaudeOperationAdapter, 'verify', revoked_verifier(self, assets, owner)):
            with self.assertRaisesRegex(PermissionError, 'engineering_observed_current_authority_denial'):
                self.f.execution.retry(owner, first['operation_id'], expected_generation=first['generation'],
                                       event_key='native-owner-infra-retry')
        self.assertEqual(counts(assets), before)
        self.assertEqual(self.f.execution.get(owner, first['operation_id'])['attempt'], 1)

    def test_retry_deadline_crossing_last_source_observation_refuses_image_allow(self):
        import improvement_operation_retry as retry
        import improvement_store as IM
        first = self.f.capacity_failure()
        execution, owner = self.f.execution, self.f.owner
        before = counts(execution.assets)
        clock = [first['deadline_at'] - 1]
        source = execution.host._snapshot_observe
        def verify(adapter):
            boundary = adapter._native._native_boundary
            self.assertIsNotNone(boundary)
            observations = []
            def observe(*args, **kwargs):
                value = source(*args, **kwargs)
                observations.append(True)
                if len(observations) == 2: clock[0] = first['deadline_at'] + 1
                return value
            with patch.object(retry.time, 'time', side_effect=lambda: clock[0]), \
                    patch.object(execution.host, '_snapshot_observe', side_effect=observe):
                with execution.store._Tx(execution.store) as connection:
                    with self.assertRaisesRegex(IM.ConflictError, 'operation_retry_unavailable'):
                        boundary.current(connection, None)
            self.assertEqual(len(observations), 2)
            raise PermissionError('engineering_expired_retry_refused')
        with patch.object(ClaudeOperationAdapter, 'verify', verify):
            with self.assertRaisesRegex(PermissionError, 'engineering_expired_retry_refused'):
                execution.retry(owner, first['operation_id'], expected_generation=first['generation'],
                                event_key='native-expiring-infra-retry')
        self.assertEqual(counts(execution.assets), before)


if __name__ == '__main__': unittest.main()
