"""Refusal controls at actual compose SQL and final source boundaries.

All positive consent/operation history comes from the actual owner fixture.
Injected history/state changes are rollback-only negative controls, never native
qualification, a provider call or business evidence.
"""
from _paths import ROOT, SERVER  # noqa: F401

import unittest
from contextlib import closing
from unittest.mock import patch

from improvement_compose_permissions import ComposePermissions
import test_improvement_compose_admission as admission


class ComposeAdmissionRaceTests(unittest.TestCase):
    def setUp(self):
        self.f = admission.ComposeAdmissionTests()
        self.f.setUp()
        self.addCleanup(lambda: self.assertTrue(self.f.doCleanups()))

    def test_metadata_owner_rejects_foreign_consent_and_revoked_direct_reservation_without_host_wrapper(self):
        f = self.f
        with self.assertRaises(admission.DENIED), f.store._Tx(f.store) as connection:
            request = f.request(compose_authorization_id='icpa_foreign')
            f.records._create_in(connection, f.owner, request, request['input_hash'],
                expected_generation=f.saved['experiment_generation'], event_key='direct-foreign-compose')
        self.assertEqual(f.f.rows('improvement_operations'), [])
        operation = f.create()
        f.f.service.revoke(f.owner, f.saved['authorization_id'], expected_generation=1, event_key='direct-reserve-revoked')
        with self.assertRaises(admission.DENIED), f.store._Tx(f.store) as connection:
            f.records._reserve_attempt_in(connection, f.owner, operation['operation_id'],
                expected_generation=1, event_key='direct-reserve-no-call')
        f.assert_no_new_call()

    def test_sql_forbids_same_generation_state_drift_and_current_refuses_forged_operation_row(self):
        f = self.f
        operation = f.create()
        class RollbackControl(Exception): pass
        for mutation in ('UPDATE improvement_experiments SET updated_at=updated_at+1',
                         "UPDATE improvement_experiments SET phase=CASE WHEN phase='probing' THEN 'comparing' ELSE 'probing' END"):
            with self.subTest(mutation=mutation), self.assertRaises(RollbackControl), f.store._Tx(f.store) as connection:
                # The existing immutable-state trigger rejects these controls
                # before the current guard; do not bypass that real boundary.
                with self.assertRaises(admission.sqlite3.IntegrityError):
                    connection.execute(mutation)
                raise RollbackControl()
        with closing(f.store._conn()) as connection:
            raw = dict(f.raw_operation(connection, operation['operation_id']))
            with self.assertRaises(admission.DENIED):
                f.f.service.current(connection, f.owner, f.saved['authorization_id'], operation={**raw, 'created_at': raw['created_at'] + 1})
        f.execution.guard(f.owner, operation['operation_id'])

    def test_creation_history_mutation_after_full_source_fence_is_refused_by_final_sql_check(self):
        f = self.f
        operation = f.create()
        original = ComposePermissions._fence
        def duplicate_after_source(service, connection, principal, before, observed):
            original(service, connection, principal, before, observed)
            payload = {'request': f.request(), 'input_blob_hash': f.saved['input_hash'],
                       'expected_generation': f.saved['experiment_generation']}
            f.assets._event(connection, principal, 'late-duplicate-compose-negative', 'operation_create', payload, operation)
        with self.assertRaises(admission.DENIED), f.store._Tx(f.store) as connection:
            with patch.object(ComposePermissions, '_fence', duplicate_after_source):
                f.f.service.current(connection, f.owner, f.saved['authorization_id'],
                    operation=f.raw_operation(connection, operation['operation_id']))
        self.assertFalse(any(row['event_key'] == 'late-duplicate-compose-negative' for row in f.f.rows('improvement_events')))
        f.execution.guard(f.owner, operation['operation_id'])


if __name__ == '__main__': unittest.main()
