"""Actual private schema7 histories migrate atomically; no compose runtime proof.

Pinned old ensure builds the real SQL/Fernet host fixtures, not hand-written
replacement schema. Operation fixture has a real PREPARED lease/workspace/call,
with its declared synthetic verifier and ACL-only process controls; no query or
engine marker. Selection fixture's complete results are explicitly labelled
synthetic_storage_fixture controls, never native/account/business evidence.
"""
from _paths import ROOT, SERVER  # noqa: F401

import hashlib
import importlib
import importlib.util
import sqlite3
import subprocess
import sys
import tempfile
import threading
import types
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

import improvement_store as IM
from resonance_store import GoalStore
import test_improvement_operation_execution as operations
import test_improvement_experiment_selection as selections


HISTORICAL = '79e5985c'
SCHEMA_MODULES = ('improvement_case_schema', 'improvement_trial_schema', 'improvement_candidate_schema',
                  'improvement_experiment_schema', 'improvement_operation_schema', 'improvement_view_schema')


class ComposeSchemaTests(unittest.TestCase):
    def setUp(self):
        # Missing schema unit fails before any private fixture, git loader or DB.
        self.assertIsNotNone(importlib.util.find_spec('improvement_compose_schema'),
                             'Actual backed-up schema8 composition migration is absent')
        self.schema = importlib.import_module('improvement_compose_schema')
        if not hasattr(type(self), 'old'):
            type(self).old = self.load_historical('improvement_store')
            type(self).old_blocks = {name: self.load_historical(name) for name in SCHEMA_MODULES}

    @staticmethod
    def load_historical(name):
        import _improvement_history
        return _improvement_history.load(HISTORICAL, name, '_compose_historical7_' + name)

    def operation_fixture(self):
        fixture = operations.OperationExecutionTests()
        with patch.object(IM, 'ensure', side_effect=self.old.ensure):
            fixture.setUp()
            self.addCleanup(lambda: self.assertTrue(fixture.doCleanups(), 'Operation fixture cleanup failed'))
            service = fixture.execution()
            row, token, receipt = fixture.prepared(service)
        self.assertEqual(self.old._schema_version(fixture.store), 7)
        self.assertEqual(row['status'], 'prepared')
        self.assertIsNone(service.ledger.get(row['attempts'][-1]['call_id'])['engine_at'])
        return fixture, service, row, token, receipt

    def selection_fixture(self):
        fixture = selections.ExperimentSelectionTests()
        with patch.object(IM, 'ensure', side_effect=self.old.ensure):
            fixture.setUp()
            self.addCleanup(lambda: self.assertTrue(fixture.doCleanups(), 'Selection fixture cleanup failed'))
            fixture.select()
        self.assertEqual(self.old._schema_version(fixture.store), 7)
        return fixture

    def empty_old_store(self):
        directory = tempfile.TemporaryDirectory(prefix='compose-schema7-')
        self.addCleanup(directory.cleanup)
        store = GoalStore(Path(directory.name) / 'resonance.sqlite3')
        self.old.ensure(store)
        self.assertEqual(self.old._schema_version(store), 7)
        return store

    @staticmethod
    def history(store):
        with closing(store._conn()) as connection:
            tables = [row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table' "
                "AND (name LIKE 'improvement_%' OR name='agent_calls') ORDER BY name") if row[0] != 'improvement_schema']
            return {name: [tuple(row) for row in connection.execute('SELECT * FROM "' + name + '" ORDER BY rowid')]
                    for name in tables}

    @staticmethod
    def definitions(store):
        with closing(store._conn()) as connection:
            return [tuple(row) for row in connection.execute("SELECT type,name,tbl_name,sql FROM sqlite_master "
                "WHERE name LIKE 'improvement_%' ORDER BY type,name")]

    @staticmethod
    def blobs(assets):
        return {str(path.relative_to(assets.blobs.root)): path.read_bytes()
                for path in assets.blobs.root.rglob('*.enc')}

    @staticmethod
    def backups(store):
        return {path: hashlib.sha256(path.read_bytes()).hexdigest()
                for path in store.path.parent.glob(store.path.name + '*.bak')}

    def assert_old_rows(self, store, before):
        after = self.history(store)
        self.assertEqual({name: after[name] for name in before}, before)

    def assert_foreign_keys(self, store):
        with closing(store._conn()) as connection:
            self.assertEqual(connection.execute('PRAGMA foreign_keys').fetchone()[0], 1)
            self.assertEqual(connection.execute('PRAGMA foreign_key_check').fetchall(), [])

    def assert_new_backup(self, store, before_backups, before_rows):
        after = self.backups(store)
        self.assertEqual({path: after[path] for path in before_backups}, before_backups)
        created = set(after) - set(before_backups)
        self.assertEqual(len(created), 1, 'one serialized schema7 backup, no existing backup overwritten')
        backup = created.pop()
        with closing(sqlite3.connect(backup)) as connection:
            self.assertEqual(connection.execute('SELECT version FROM improvement_schema').fetchone()[0], 7)
            self.assertEqual(connection.execute('PRAGMA foreign_key_check').fetchall(), [])
            for name, rows in before_rows.items():
                self.assertEqual(connection.execute('SELECT * FROM "' + name + '" ORDER BY rowid').fetchall(), rows)
        return after

    def test_real_prepared_operation_children_call_ledger_blobs_guards_and_schema7_backup_survive(self):
        fixture, service, row, token, receipt = self.operation_fixture()
        before, ciphertext, backups = self.history(fixture.store), self.blobs(fixture.assets), self.backups(fixture.store)
        self.assertTrue(before['improvement_operations'])
        self.assertTrue(before['improvement_operation_attempts'])
        self.assertTrue(before['agent_calls'])
        IM.ensure(fixture.store)
        self.assertEqual(IM._schema_version(fixture.store), IM.SCHEMA_VERSION)
        self.assert_old_rows(fixture.store, before)
        self.assertEqual(self.blobs(fixture.assets), ciphertext)
        self.assertEqual(service.workspace.validate(receipt)['data'], fixture.data)
        self.assert_foreign_keys(fixture.store)
        saved_backups = self.assert_new_backup(fixture.store, backups, before)
        with closing(fixture.store._conn()) as connection:
            names = {item[0] for item in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertTrue({'improvement_compose_authorizations', 'improvement_compose_grants', 'improvement_compositions'} <= names)
        with self.assertRaises(sqlite3.IntegrityError), fixture.store._Tx(fixture.store) as connection:
            connection.execute('DELETE FROM improvement_operations WHERE id=?', (row['operation_id'],))
        with patch.object(fixture.store, '_backup_before', side_effect=AssertionError('Old reader cannot back up')):
            with self.assertRaises(self.old.SchemaError): self.old.ensure(fixture.store)
        IM.ensure(fixture.store)
        self.assert_old_rows(fixture.store, before)
        self.assertEqual(self.backups(fixture.store), saved_backups)
        self.assertEqual(IM._SCHEMA, self.old._SCHEMA)
        for name, historical in self.old_blocks.items():
            current = importlib.import_module(name)
            self.assertEqual(current.SCHEMA, historical.SCHEMA, name + ' old schema constants must be preserved')
            self.assertEqual(current.IMMUTABLE, historical.IMMUTABLE, name + ' historical immutable inventory must be preserved')

    def test_real_nonempty_candidate_arm_selection_and_result_children_survive(self):
        fixture = self.selection_fixture()
        before, ciphertext = self.history(fixture.store), self.blobs(fixture.assets)
        for name in ('improvement_skill_candidates', 'improvement_experiment_arms', 'improvement_experiment_selections',
                     'improvement_comparisons', 'improvement_experiment_trial_links', 'improvement_trial_results'):
            self.assertTrue(before[name], name)
        IM.ensure(fixture.store)
        self.assertEqual(IM._schema_version(fixture.store), IM.SCHEMA_VERSION)
        self.assert_old_rows(fixture.store, before)
        self.assertEqual(self.blobs(fixture.assets), ciphertext)
        self.assert_foreign_keys(fixture.store)
        for table in ('improvement_skill_candidates', 'improvement_experiment_arms', 'improvement_experiment_selections'):
            with self.subTest(table=table), self.assertRaises(sqlite3.IntegrityError), fixture.store._Tx(fixture.store) as connection:
                connection.execute('DELETE FROM ' + table)
        self.assert_old_rows(fixture.store, before)

    def test_failure_after_actual_first_table_rebuild_rolls_back_schema7_rows_and_guards(self):
        fixture, service, row, token, receipt = self.operation_fixture()
        before, definitions, ciphertext = self.history(fixture.store), self.definitions(fixture.store), self.blobs(fixture.assets)
        actual = self.schema._rebuild_table
        rebuilt = []
        def fail_after_rebuild(*args, **kwargs):
            result = actual(*args, **kwargs)
            rebuilt.append(True)
            raise OSError('injected after actual table-copy/drop/rename boundary')
        with patch.object(self.schema, '_rebuild_table', side_effect=fail_after_rebuild), self.assertRaises(OSError):
            IM.ensure(fixture.store)
        self.assertEqual(rebuilt, [True])
        self.assertEqual(self.old._schema_version(fixture.store), 7)
        self.assertEqual(self.history(fixture.store), before)
        self.assertEqual(self.definitions(fixture.store), definitions)
        self.assertEqual(self.blobs(fixture.assets), ciphertext)
        self.assert_foreign_keys(fixture.store)
        with self.assertRaises(sqlite3.IntegrityError), fixture.store._Tx(fixture.store) as connection:
            connection.execute('DELETE FROM improvement_operations WHERE id=?', (row['operation_id'],))

    def test_missing_or_changed_actual_schema7_operation_guard_is_not_silently_repaired(self):
        for altered in (False, True):
            with self.subTest(altered=altered):
                store = self.empty_old_store()
                with store._Tx(store) as connection:
                    connection.execute('DROP TRIGGER improvement_operation_delete')
                    if altered:
                        connection.execute('CREATE TRIGGER improvement_operation_delete BEFORE DELETE ON improvement_operations '
                                           "BEGIN SELECT RAISE(ABORT,'different unknown guard'); END")
                before, definitions, backups = self.history(store), self.definitions(store), self.backups(store)
                with self.assertRaises((IM.SchemaError, IM.ConflictError)): IM.ensure(store)
                self.assertEqual(self.old._schema_version(store), 7)
                self.assertEqual(self.history(store), before)
                self.assertEqual(self.definitions(store), definitions)
                self.assertEqual(self.backups(store), backups, 'refuse unknown schema before making a migration backup')

    def test_two_actual_writers_serialize_one_schema7_backup_and_leave_ordinary_connections_fk_on(self):
        fixture = self.selection_fixture()
        before, backups = self.history(fixture.store), self.backups(fixture.store)
        barrier = threading.Barrier(2)
        def migrate(_):
            barrier.wait(timeout=10)
            IM.ensure(fixture.store)
            with closing(fixture.store._conn()) as connection:
                return connection.execute('PRAGMA foreign_keys').fetchone()[0]
        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual(list(pool.map(migrate, (1, 2))), [1, 1])
        self.assertEqual(IM._schema_version(fixture.store), IM.SCHEMA_VERSION)
        self.assert_old_rows(fixture.store, before)
        self.assert_new_backup(fixture.store, backups, before)
        self.assert_foreign_keys(fixture.store)

    def test_direct_ordinary_ordinal_three_cannot_bypass_typed_composition_publication(self):
        fixture = self.selection_fixture()
        IM.ensure(fixture.store)
        before = self.history(fixture.store)
        with closing(fixture.store._conn()) as connection:
            original = dict(connection.execute('SELECT * FROM improvement_skill_candidates LIMIT 1').fetchone())
        original.update(id='isc_unproven_direct_ordinal3', ordinal=3)
        columns = list(original)
        with self.assertRaises(sqlite3.IntegrityError), fixture.store._Tx(fixture.store) as connection:
            connection.execute('INSERT INTO improvement_skill_candidates (' + ','.join(columns) + ') VALUES(' +
                ','.join('?' for _ in columns) + ')', [original[key] for key in columns])
        self.assert_old_rows(fixture.store, before)
        self.assert_foreign_keys(fixture.store)


if __name__ == '__main__': unittest.main()
