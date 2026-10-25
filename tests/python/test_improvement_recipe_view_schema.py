"""Trigger-only v10 migration controls; synthetic fixtures are not native proof."""
from _paths import ROOT, SERVER  # noqa: F401

import sqlite3
import subprocess
import sys
import threading
import types
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from unittest.mock import patch

import improvement_store as IM
import improvement_recipe_schema as nine
import test_improvement_recipe_schema as historical


class RecipeViewSchemaTests(unittest.TestCase):
    history = staticmethod(historical.RecipeSchemaTests.history)
    definitions = staticmethod(historical.RecipeSchemaTests.definitions)
    blobs = staticmethod(historical.RecipeSchemaTests.blobs)
    backups = staticmethod(historical.RecipeSchemaTests.backups)
    insert = historical.RecipeSchemaTests.insert
    recipe = historical.RecipeSchemaTests.recipe
    ref = historical.RecipeSchemaTests.ref
    seal = historical.RecipeSchemaTests.seal
    transition = historical.RecipeSchemaTests.transition

    @classmethod
    def setUpClass(cls):
        historical.RecipeSchemaTests.setUpClass()
        import _improvement_history
        cls.old = _improvement_history.load('c93cb718', 'improvement_store', '_recipe_official9_store')
        cls.old_schema = _improvement_history.load('c93cb718', 'improvement_recipe_schema', '_recipe_official9_schema')

    def test_nine_literals_and_every_unmodified_recipe_definition_stay_exact(self):
        import improvement_recipe_view_schema as ten
        from improvement_compose_schema import _name
        self.assertEqual(nine.SCHEMA, self.old_schema.SCHEMA)
        self.assertEqual(nine.IMMUTABLE, self.old_schema.IMMUTABLE)
        self.assertEqual(nine.statements(), self.old_schema.statements())
        historical_sql, current_sql = self.old_schema.statements(), ten.statements()
        self.assertEqual(len(historical_sql), len(current_sql))
        self.assertEqual([_name(old) for old, current in zip(historical_sql, current_sql) if old != current],
                         ['improvement_recipe_trial_scope'])

    def fixture(self, *, prepared=False, compose=False):
        helper = historical.RecipeSchemaTests()
        helper.old = historical.RecipeSchemaTests.old
        fixture = helper.fixture(prepared=prepared, compose=compose)
        self.addCleanup(lambda: self.assertTrue(helper.doCleanups(), 'Actual fixture cleanup failed'))
        self.old.ensure(fixture.store)
        self.assertEqual(IM._schema_version(fixture.store), 9)
        return fixture

    def populated(self):
        fixture = self.fixture()
        self.insert(fixture.store, 'improvement_recipes', self.recipe(fixture))
        self.insert(fixture.store, 'improvement_recipe_trial_refs', self.ref(fixture))
        self.seal(fixture)
        self.transition(fixture, status='erased', generation=2, reason='owner_erased', changed_at=102)
        return fixture

    def test_populated_nine_trigger_only_migration_preserves_history_ciphertext_and_backup(self):
        fixture = self.populated()
        before, definitions, ciphertext = self.history(fixture.store), self.definitions(fixture.store), self.blobs(fixture.assets)
        backups = self.backups(fixture.store)
        with patch.object(nine, 'migrate', side_effect=AssertionError('Installed9 must not recreate recipes')):
            IM.ensure(fixture.store)
        self.assertEqual(IM._schema_version(fixture.store), IM.SCHEMA_VERSION)
        self.assertEqual({key: self.history(fixture.store)[key] for key in before}, before)
        self.assertEqual(self.blobs(fixture.assets), ciphertext)
        after = {row[1]: row for row in self.definitions(fixture.store)}
        changed = [row[1] for row in definitions if after[row[1]] != row]
        self.assertEqual(changed, ['improvement_recipe_trial_scope'])
        created = set(self.backups(fixture.store)) - set(backups)
        self.assertEqual(len(created), 1)
        backup = created.pop()
        self.assertTrue(str(backup).endswith('.pre-improvement-m2-recipe-views.bak'))
        with closing(sqlite3.connect(backup)) as connection:
            self.assertEqual(connection.execute('SELECT version FROM improvement_schema').fetchone()[0], 9)
            connection.row_factory = sqlite3.Row
            nine.assert_installed(connection)
            for table, rows in before.items():
                self.assertEqual([tuple(row) for row in connection.execute('SELECT * FROM '+table+' ORDER BY rowid')], rows)
        saved = self.backups(fixture.store)
        with patch.object(fixture.store, '_backup_before', side_effect=AssertionError('Repeated10 cannot back up')):
            IM.ensure(fixture.store)
        self.assertEqual(self.backups(fixture.store), saved)
        with self.assertRaises(self.old.SchemaError):
            self.old.ensure(fixture.store)

    def test_prepared_lease_call_and_workspace_survive_nine_to_ten(self):
        fixture = self.fixture(prepared=True)
        before, ciphertext = self.history(fixture.store), self.blobs(fixture.assets)
        IM.ensure(fixture.store)
        self.assertEqual(IM._schema_version(fixture.store), IM.SCHEMA_VERSION)
        self.assertEqual({key: self.history(fixture.store)[key] for key in before}, before)
        self.assertEqual(ciphertext, self.blobs(fixture.assets))
        self.assertEqual(fixture.prepared_service.workspace.validate(fixture.prepared_receipt)['data'], fixture.data)

    def test_actual_encrypted_nine_recipe_and_revocation_event_survive_trigger_migration(self):
        import test_improvement_recipe_archive as archives
        from improvement_recipe_records import RecipeRecords
        fixture = archives.RecipeArchiveTests()
        with patch.object(IM, 'ensure', side_effect=self.old.ensure):
            fixture.setUp()
            self.addCleanup(lambda: self.assertTrue(fixture.doCleanups(), 'Actual archive cleanup failed'))
            saved = fixture.capture()
            records = RecipeRecords(fixture.assets)
            revoked = records.revoke(fixture.owner, saved['recipe_id'], expected_generation=1, event_key='nine-recipe-owner-revoke')
            fixture.assets.set_policy(fixture.owner, 'off', expected_version=0, event_key='nine-recipe-owner-off')
        self.assertEqual(IM._schema_version(fixture.store), 9)
        before, ciphertext, backups = self.history(fixture.store), self.blobs(fixture.assets), self.backups(fixture.store)
        self.assertTrue(fixture.assets.blobs._path(fixture.owner.brain_id, saved['manifest_hash']).read_bytes().startswith(b'enc:'))
        IM.ensure(fixture.store)
        self.assertEqual(IM._schema_version(fixture.store), IM.SCHEMA_VERSION)
        # Version11 only adds the empty activation table; every historical row is unchanged.
        self.assertEqual({key: self.history(fixture.store)[key] for key in before}, before)
        self.assertEqual(self.blobs(fixture.assets), ciphertext)
        self.assertEqual(len(set(self.backups(fixture.store)) - set(backups)), 1)
        with patch.object(fixture.assets.blobs, 'read', side_effect=AssertionError('Historical control cannot decrypt')):
            self.assertEqual(records.get(fixture.owner, saved['recipe_id'])['record_status'], 'revoked')
            self.assertEqual(records.revoke(fixture.owner, saved['recipe_id'], expected_generation=1,
                event_key='nine-recipe-owner-revoke'), revoked)

    def test_interrupted_trigger_replacement_rolls_back_nine_and_retry_preserves_backup(self):
        import improvement_recipe_view_schema as ten
        fixture = self.populated()
        before, definitions = self.history(fixture.store), self.definitions(fixture.store)
        actual = ten.statements()
        trigger = next(sql for sql in actual if sql.startswith('CREATE TRIGGER improvement_recipe_trial_scope '))
        with patch.object(ten, 'statements', return_value=tuple(sql.replace(' BEFORE INSERT ', ' INVALID INSERT ') if sql == trigger else sql for sql in actual)), \
                self.assertRaises(sqlite3.OperationalError):
            IM.ensure(fixture.store)
        self.assertEqual(IM._schema_version(fixture.store), 9)
        self.assertEqual(self.history(fixture.store), before)
        self.assertEqual(self.definitions(fixture.store), definitions)
        saved = self.backups(fixture.store)
        IM.ensure(fixture.store)
        self.assertEqual(IM._schema_version(fixture.store), IM.SCHEMA_VERSION)
        self.assertEqual(self.backups(fixture.store), saved)

    def test_two_first_writers_publish_one_ten_and_preserve_exact_nine_backup(self):
        fixture = self.populated()
        before, backups = self.history(fixture.store), self.backups(fixture.store)
        barrier = threading.Barrier(2)
        def write(_):
            barrier.wait(timeout=10)
            IM.ensure(fixture.store)
            with closing(fixture.store._conn()) as connection:
                return connection.execute('PRAGMA foreign_keys').fetchone()[0]
        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual(list(pool.map(write, (1, 2))), [1, 1])
        self.assertEqual(IM._schema_version(fixture.store), IM.SCHEMA_VERSION)
        self.assertEqual(len(set(self.backups(fixture.store)) - set(backups)), 1)
        self.assertEqual({key: self.history(fixture.store)[key] for key in before}, before)

    def test_altered_nine_partial_ten_reserved_collision_and_future_refuse_before_backup(self):
        for mutation in ('altered9', 'partial10', 'reserved', 'foreign_artifact', 'future'):
            with self.subTest(mutation=mutation):
                fixture = self.fixture()
                with fixture.store._Tx(fixture.store) as connection:
                    if mutation == 'altered9':
                        connection.execute('DROP TRIGGER improvement_recipe_trial_scope')
                        connection.execute('CREATE TRIGGER improvement_recipe_trial_scope BEFORE INSERT ON improvement_recipe_trial_refs BEGIN SELECT 1; END')
                    elif mutation == 'reserved':
                        connection.execute('CREATE TABLE improvement_recipe_view_scope(private TEXT)')
                    elif mutation == 'foreign_artifact':
                        connection.execute('CREATE TRIGGER IMPROVEMENT_RECIPE_PRIVATE BEFORE INSERT ON improvement_events BEGIN SELECT 1; END')
                    else:
                        connection.execute('UPDATE improvement_schema SET version=?', (10 if mutation == 'partial10' else IM.SCHEMA_VERSION + 1,))
                before, definitions, backups = self.history(fixture.store), self.definitions(fixture.store), self.backups(fixture.store)
                with self.assertRaises((IM.ConflictError, IM.SchemaError)):
                    IM.ensure(fixture.store)
                self.assertEqual(self.history(fixture.store), before)
                self.assertEqual(self.definitions(fixture.store), definitions)
                self.assertEqual(self.backups(fixture.store), backups)

    def test_current_ten_role_and_compose_guards_refuse_changed_effective_recipe_family(self):
        import improvement_operation_schema as roles
        import improvement_recipe_view_schema as ten
        fixture = self.fixture(compose=True)
        with closing(fixture.store._conn()) as connection:
            fixture.service._connection(connection)
            roles.assert_installed(connection)
        IM.ensure(fixture.store)
        with closing(fixture.store._conn()) as connection:
            roles.assert_installed(connection)
            fixture.service._connection(connection)
            ten.assert_installed(connection)
            self.assertEqual(connection.execute('PRAGMA foreign_key_check').fetchall(), [])
            with self.assertRaises(IM.ConflictError):
                nine.assert_installed(connection)
        with fixture.store._Tx(fixture.store) as connection:
            connection.execute('DROP TRIGGER improvement_recipe_trial_scope')
            connection.execute('CREATE TRIGGER improvement_recipe_trial_scope BEFORE INSERT ON improvement_recipe_trial_refs BEGIN SELECT 1; END')
        with closing(fixture.store._conn()) as connection:
            with self.assertRaisesRegex(IM.ConflictError, 'operation_schema_changed'):
                roles.assert_installed(connection)
            with self.assertRaisesRegex(IM.ConflictError, 'operation_schema_changed'):
                fixture.service._connection(connection)
            with self.assertRaises(IM.ConflictError):
                ten.assert_installed(connection)


if __name__ == '__main__':
    unittest.main()
