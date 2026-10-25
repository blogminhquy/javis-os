"""Actual admission SQL/source fences; engineering verification, no CLI/model."""
from _paths import ROOT, SERVER  # noqa: F401

import unittest
from contextlib import closing
from unittest.mock import patch

import improvement_store as IM
from improvement_claude import ClaudeTrialAdapter
from improvement_operation_adapter import ClaudeOperationAdapter
import test_improvement_trial_admission as trial_fixture
import test_improvement_operation_execution as operation_fixture


class TrialAdmissionAuthorityTests(unittest.TestCase):
    def setUp(self):
        self.f = trial_fixture.AdmissionTests()
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        self.f.verify_patch.stop()

    def check(self, *, revoke=False):
        seen = []
        def verify(adapter):
            boundary = adapter._native_boundary
            self.assertIsNotNone(boundary, 'actual owner admission must bind before native verification')
            self.assertIs(boundary.assets, self.f.assets)
            self.assertIs(boundary.principal, self.f.owner)
            self.f.assert_no_admission()
            with self.f.store._Tx(self.f.store) as connection:
                self.assertEqual(boundary.current(connection, None), 'allow')
            if revoke:
                self.f.assets.set_policy(self.f.owner, 'off', expected_version=0, event_key='native-admission-revoke')
            with self.f.store._Tx(self.f.store) as connection:
                self.assertEqual(boundary.current(connection, None), 'allow')
            seen.append(boundary.scope_hash)
            return self.f.verified
        with patch.object(ClaudeTrialAdapter, 'verify', verify):
            if revoke:
                with self.assertRaisesRegex(ValueError, 'trial_native_unavailable'): self.f.admit()
                self.f.assert_no_admission()
            else:
                result = self.f.admit()
                self.assertEqual(self.f.count('agent_calls'), 1)
                with patch.object(ClaudeTrialAdapter, 'verify', side_effect=AssertionError('historical replay probed')):
                    self.assertEqual(self.f.admit(), result)
        return seen

    def test_actual_owner_admission_binds_fresh_authority_before_reservation_and_replay_stays_historical(self):
        self.assertEqual(len(self.check()), 1)

    def test_policy_revocation_between_preflight_image_decisions_cannot_reserve_trial_or_call(self):
        self.assertEqual(self.check(revoke=True), [])


class OperationAdmissionAuthorityTests(unittest.TestCase):
    def setUp(self):
        self.f = operation_fixture.OperationExecutionTests()
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        self.execution = self.f.execution()

    def reserve(self, generation=1):
        return self.execution.reserve(self.f.owner, self.f.operation['operation_id'],
                                      expected_generation=generation, event_key='native-operation-admission')

    def assert_unreserved(self):
        with closing(self.f.store._conn()) as connection:
            self.assertEqual(connection.execute('SELECT COUNT(*) FROM improvement_operation_attempts').fetchone()[0], 0)
            self.assertEqual(connection.execute('SELECT COUNT(*) FROM agent_calls').fetchone()[0], 0)

    def check(self, *, revoke=False):
        seen = []
        def verify(adapter):
            boundary = adapter._native._native_boundary
            self.assertIsNotNone(boundary, 'actual operation reserve must bind before native verification')
            self.assertIs(boundary.assets, self.f.assets)
            self.assertIs(boundary.principal, self.f.owner)
            self.assert_unreserved()
            with self.f.store._Tx(self.f.store) as connection:
                self.assertEqual(boundary.current(connection, None), 'allow')
            if revoke:
                self.f.assets.set_policy(self.f.owner, 'off', expected_version=0, event_key='native-operation-revoke')
            with self.f.store._Tx(self.f.store) as connection:
                self.assertEqual(boundary.current(connection, None), 'allow')
            seen.append(boundary.scope_hash)
            return {'supported': True, 'capability_hash': 'c' * 64}
        with patch.object(ClaudeOperationAdapter, 'verify', verify):
            if revoke:
                with self.assertRaises(PermissionError): self.reserve()
                self.assert_unreserved()
            else:
                result = self.reserve()
                self.assertEqual(len(result['attempts']), 1)
                with patch.object(ClaudeOperationAdapter, 'verify', side_effect=AssertionError('historical replay probed')):
                    self.assertEqual(self.reserve(), result)
        return seen

    def test_actual_operation_reservation_binds_fresh_authority_before_attempt_and_call(self):
        self.assertEqual(len(self.check()), 1)

    def test_policy_revocation_between_operation_preflight_images_cannot_reserve(self):
        self.assertEqual(self.check(revoke=True), [])

    def test_stale_operation_generation_refuses_before_any_native_preflight(self):
        with patch.object(ClaudeOperationAdapter, 'verify', side_effect=AssertionError('stale generation probed native')):
            with self.assertRaisesRegex(IM.ConflictError, 'operation_state_stale'):
                self.reserve(generation=2)
        self.assert_unreserved()


if __name__ == '__main__': unittest.main()
