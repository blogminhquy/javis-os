"""Real private DB boundaries; SQL controls do not claim compose execution.

Uses the actual existing labelled synthetic storage fixture, not an account or
native model. Pending compose rows here test only schema/permission constraints.
"""
from _paths import ROOT, SERVER  # noqa: F401

import sqlite3
import time
import unittest
from contextlib import closing
from unittest.mock import patch

import improvement_compose_schema as schema
import improvement_store as IM
import agent_ledger as ledger_module
import test_improvement_compose_schema as migration
import test_improvement_experiment_selection as selections


class ComposeSchemaBoundaryTests(unittest.TestCase):
    def fixture(self):
        f = selections.ExperimentSelectionTests()
        f.setUp()
        self.addCleanup(lambda: self.assertTrue(f.doCleanups(), 'Fixture cleanup failed'))
        return f

    def authorization(self, f, identifier='ica_schema_only'):
        with f.store._Tx(f.store) as connection:
            row = dict(connection.execute('SELECT * FROM improvement_experiments').fetchone())
            generation = connection.execute('SELECT generation FROM improvement_trial_context_grants WHERE context_id=?',
                                            (row['context_id'],)).fetchone()[0]
            connection.execute('INSERT INTO improvement_compose_authorizations VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                (identifier, f.owner.brain_id, row['id'], row['context_id'], row['definition_hash'], 'a' * 64,
                 'b' * 64, generation, 0, f.owner.by, time.time()))
        return row

    @staticmethod
    def grant(f, identifier='ica_schema_only'):
        with f.store._Tx(f.store) as connection:
            connection.execute("INSERT INTO improvement_compose_grants VALUES(?,?,1,'active',NULL)",
                               (identifier, f.owner.brain_id))

    @staticmethod
    def operation(f, row, *, identifier='io_schema_only', permission='ica_schema_only', **changes):
        value = {'definition_hash': row['definition_hash'], 'compose_authorization_id': permission}
        values = dict(id=identifier, brain_id=f.owner.brain_id, experiment_id=row['id'], context_id=row['context_id'],
            kind='compose', role='composer', purpose='improve_compose', candidate_id=None, parent_id=None,
            request_hash=IM._hash(value), request_json=IM._json(value), input_hash='a' * 64, input_blob_hash='a' * 64,
            status='pending', generation=1, attempt=0, created_at=time.time(), updated_at=time.time())
        values.update(changes)
        with f.store._Tx(f.store) as connection:
            connection.execute('INSERT INTO improvement_operations (' + ','.join(values) + ') VALUES(' +
                ','.join('?' for _ in values) + ')', list(values.values()))

    def test_pending_composer_requires_exact_active_permission_and_cannot_be_a_proposal(self):
        f = self.fixture()
        row = self.authorization(f)
        with self.assertRaisesRegex(sqlite3.IntegrityError, 'compose_permission_required'):
            self.operation(f, row)
        self.grant(f)
        for changes in ({'permission': 'ica_foreign'}, {'input_hash': 'c' * 64, 'input_blob_hash': 'c' * 64},
                        {'role': 'improver'}, {'purpose': 'improve_propose'}):
            with self.subTest(changes=changes), self.assertRaises(sqlite3.IntegrityError):
                self.operation(f, row, **changes)
        self.operation(f, row)
        with self.assertRaises(sqlite3.IntegrityError): self.operation(f, row, identifier='io_second_compose')
        with closing(f.store._conn()) as connection:
            saved = connection.execute("SELECT * FROM improvement_operations WHERE kind='compose'").fetchone()
            self.assertEqual((saved['kind'], saved['role'], saved['purpose'], saved['attempt']),
                             ('compose', 'composer', 'improve_compose', 0))
            self.assertEqual(connection.execute('SELECT count(*) FROM improvement_operation_attempts WHERE operation_id=?',
                                               (saved['id'],)).fetchone()[0], 0)

    def test_revoked_compose_permission_cannot_reactivate_rebind_delete_or_admit_an_operation(self):
        f = self.fixture()
        row = self.authorization(f)
        self.grant(f)
        with f.store._Tx(f.store) as connection:
            connection.execute("UPDATE improvement_compose_grants SET status='revoked',generation=2,revoked_at=?",
                               (time.time(),))
        for sql in ("UPDATE improvement_compose_grants SET status='active',generation=1,revoked_at=NULL",
                    "UPDATE improvement_compose_grants SET authorization_id='ica_foreign'",
                    'DELETE FROM improvement_compose_grants', 'DELETE FROM improvement_compose_authorizations'):
            with self.subTest(sql=sql), self.assertRaises(sqlite3.IntegrityError), f.store._Tx(f.store) as connection:
                connection.execute(sql)
        with self.assertRaisesRegex(sqlite3.IntegrityError, 'compose_permission_required'):
            self.operation(f, row)

    def test_sealed_selection_cannot_gain_a_new_compose_authorization(self):
        f = self.fixture()
        f.select()
        with self.assertRaisesRegex(sqlite3.IntegrityError, 'compose_authorization_scope_mismatch'):
            self.authorization(f)

    def test_final_composition_rechecks_the_actual_call_identity_after_settlement(self):
        f = self.fixture()
        row = self.authorization(f)
        self.grant(f)
        self.operation(f, row)
        ledger = ledger_module.CallLedger(f.store)
        stamp = time.time()
        output = f.assets.blobs.write(f.owner.brain_id, IM._json({'evidence_origin': 'synthetic_storage_fixture',
            'business_proof': False, 'model_executed': False}).encode())
        # This schema-only control seeds a labelled completed storage graph via
        # actual ledger/state constraints. The purpose allowlist is patched only
        # here; no runner/profile/model invocation is claimed or exercised.
        with patch.object(ledger_module, 'PURPOSES', (*ledger_module.PURPOSES, 'improve_compose')), f.store._Tx(f.store) as c:
            call = ledger.reserve(purpose='improve_compose', reason_ref='improvement_operation:io_schema_only:attempt:1',
                brain_id=f.owner.brain_id, context_ref='improvement:' + row['id'], mirror_ref='improvement_operation:io_schema_only',
                obligation=True, attempt=1, now=stamp, c=c)
            self.assertIsNotNone(call)
            c.execute("INSERT INTO improvement_operation_attempts(operation_id,brain_id,attempt,status,call_id,created_at,updated_at) "
                      "VALUES('io_schema_only',?,1,'reserved',?,?,?)", (f.owner.brain_id, call, stamp, stamp))
            c.execute("UPDATE improvement_operations SET status='reserved',generation=generation+1,attempt=1 WHERE id='io_schema_only'")
            c.execute("UPDATE improvement_operations SET status='prepared',generation=generation+1 WHERE id='io_schema_only'")
            self.assertTrue(ledger._mark_engine_in(c, call, 'synthetic_storage_fixture', 'unexecuted', stamp))
            c.execute("UPDATE improvement_operation_attempts SET status='running',engine_at=? WHERE operation_id='io_schema_only'", (stamp,))
            c.execute("UPDATE improvement_operations SET status='running',generation=generation+1 WHERE id='io_schema_only'")
            self.assertTrue(ledger._settle_in(c, call, 'ok', None, None, None, stamp))
            c.execute("UPDATE improvement_operation_attempts SET status='completed' WHERE operation_id='io_schema_only'")
            c.execute("UPDATE improvement_operations SET status='completed',generation=generation+1 WHERE id='io_schema_only'")
            c.execute("INSERT INTO improvement_operation_results VALUES('ior_schema_only','io_schema_only',?,1,?,?,?)",
                      (f.owner.brain_id, output, output, stamp))
        values = ('ic_schema_only', f.owner.brain_id, row['id'], 'io_schema_only', 'ior_schema_only', 'ica_schema_only',
                  'a' * 64, 'b' * 64, output, 'd' * 64, 'd' * 64, 'keep_base', None, None, None, None, stamp)
        # The closed table definition has 17 columns; make the placeholders from
        # the actual typed values rather than relaxing any graph constraint.
        sql = 'INSERT INTO improvement_compositions VALUES(' + ','.join('?' for _ in values) + ')'
        class RollbackPositive(Exception): pass
        with self.assertRaises(RollbackPositive), f.store._Tx(f.store) as c:
            c.execute(sql, values)
            raise RollbackPositive()
        for field, foreign in (('attempt', 2), ('context_ref', 'improvement:foreign'),
                               ('mirror_ref', 'improvement_operation:foreign'), ('reason_ref', 'foreign_attempt')):
            with self.subTest(field=field), self.assertRaisesRegex(sqlite3.IntegrityError, 'composition_scope_mismatch'):
                with f.store._Tx(f.store) as c:
                    c.execute('UPDATE agent_calls SET ' + field + '=? WHERE id=?', (foreign, call))
                    c.execute(sql, values)
                    self.fail('Foreign settled call identity admitted a composition publication')

    def test_foreign_key_failure_after_real_copy_refuses_commit_and_restores_history(self):
        old = migration.ComposeSchemaTests()
        old.setUp()
        self.addCleanup(lambda: self.assertTrue(old.doCleanups(), 'Historical fixture cleanup failed'))
        f, service, row, token, receipt = old.operation_fixture()
        before, definitions = old.history(f.store), old.definitions(f.store)
        actual = schema._rebuild_table
        changed = []
        def corrupt_child(connection, *args, **kwargs):
            result = actual(connection, *args, **kwargs)
            if not changed:
                connection.execute("UPDATE improvement_operation_attempts SET operation_id='io_missing_parent'")
                changed.append(True)
            return result
        with patch.object(schema, '_rebuild_table', side_effect=corrupt_child), \
                self.assertRaisesRegex(IM.SchemaError, 'compose_migration_foreign_key_violation'):
            IM.ensure(f.store)
        self.assertEqual(changed, [True])
        self.assertEqual(IM._schema_version(f.store), 7)
        self.assertEqual(old.history(f.store), before)
        self.assertEqual(old.definitions(f.store), definitions)
        old.assert_foreign_keys(f.store)


if __name__ == '__main__': unittest.main()
