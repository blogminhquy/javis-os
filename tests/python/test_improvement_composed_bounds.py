"""Structural stop/drain scope for compose, without execution/readiness claims.

The existing in-memory cardinality fixture supplies SQL rows only. Real Records
request parsing remains active; no operation, provider or qualification runs.
"""
from _paths import ROOT, SERVER  # noqa: F401

import unittest
from types import SimpleNamespace

import improvement_store as IM
from improvement_experiment_service import ExperimentService
from improvement_operation_records import OperationRecords
import test_improvement_experiment_bounds as fixtures


class ComposedBoundsTests(unittest.TestCase):
    def fixture(self):
        fixture = fixtures.ExperimentBoundsTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        return fixture

    def test_stop_scope_keeps_all_three_tuning_comparisons_and_selected_final(self):
        fixture = self.fixture()
        # Four independent comparisons of at most 4000 cells plus preparation.
        fixture.load(comparison=16000, preparation=2000)
        try:
            links, attempts, roles, role_attempts = fixture.snapshot()
        except IM.ConflictError:
            self.fail('Valid three tuning plus selected-final scope is refused before drain')
        self.assertEqual(len(links), 18000)
        self.assertEqual(len({row['trial_id'] for row in links}), 18000)
        self.assertEqual(len(attempts), 36000)
        self.assertEqual((roles, role_attempts), ([], []))
        fixture.connection.execute("INSERT INTO improvement_experiment_trial_links VALUES('extra','brain','experiment',?,0,'extra')", ('a' * 64,))
        fixture.connection.execute("INSERT INTO improvement_trials VALUES('extra','brain','cancelled',2,0,?)", ('a' * 64,))
        with self.assertRaises(IM.ConflictError):
            fixture.snapshot()

    def test_stop_scope_reads_six_roles_without_truncation_and_refuses_seventh(self):
        fixture = self.fixture()
        connection = fixture.connection
        # Complete fields actually consumed by the unchanged Records parser.
        for name, declaration in (
                ('request_json', 'TEXT'), ('request_hash', 'TEXT'), ('context_id', 'TEXT'),
                ('kind', 'TEXT'), ('role', 'TEXT'), ('purpose', 'TEXT'), ('candidate_id', 'TEXT'),
                ('parent_id', 'TEXT'), ('input_hash', 'TEXT'), ('input_blob_hash', 'TEXT'),
                ('status', 'TEXT'), ('generation', 'INTEGER'), ('attempt', 'INTEGER'), ('created_at', 'REAL')):
            connection.execute('ALTER TABLE improvement_operations ADD COLUMN ' + name + ' ' + declaration)
        kinds = [('propose', 'improver', 'improve_propose'), ('repair', 'improver', 'improve_propose'),
                 ('compose', 'composer', 'improve_compose')]
        kinds += [('semantic', 'semantic_reviewer', 'improve_evaluate')] * 4

        def insert(index):
            kind, role, purpose = kinds[index]
            request = {'version': 2 if kind == 'compose' else 1, 'experiment_id': 'experiment',
                'context_id': 'context', 'definition_hash': 'b' * 64, 'kind': kind, 'role': role,
                'purpose': purpose, 'candidate_id': 'candidate_' + str(index) if kind == 'semantic' else None,
                'parent_id': 'operation_0' if kind == 'repair' else None, 'input_hash': 'a' * 64}
            if kind == 'compose':
                request['compose_authorization_id'] = 'synthetic_sql_consent'
            row = {'id': 'operation_' + str(index), 'brain_id': 'brain', 'experiment_id': 'experiment',
                'request_json': IM._json(request), 'request_hash': IM._hash(request),
                **{key: request[key] for key in ('context_id', 'kind', 'role', 'purpose', 'candidate_id', 'parent_id', 'input_hash')},
                'input_blob_hash': 'a' * 64, 'status': 'pending', 'generation': 1, 'attempt': 0, 'created_at': 1.0}
            connection.execute('INSERT INTO improvement_operations(' + ','.join(row) + ') VALUES('
                + ','.join('?' for _ in row) + ')', tuple(row.values()))

        for index in range(6):
            insert(index)
        # _snapshot uses the real parser; no external executor is involved for
        # these pending, zero-attempt structural rows.
        service = SimpleNamespace(execution=SimpleNamespace(records=OperationRecords))
        try:
            snapshot = ExperimentService._snapshot(service, connection, 'brain', 'experiment')
        except IM.ConflictError:
            self.fail('Propose, repair, compose and three reviewers cannot all reach drain')
        self.assertEqual([row['id'] for row in snapshot[2]], ['operation_' + str(index) for index in range(6)])
        self.assertEqual(snapshot[3], [])
        insert(6)
        with self.assertRaises(IM.ConflictError):
            ExperimentService._snapshot(service, connection, 'brain', 'experiment')


if __name__ == '__main__':
    unittest.main()
