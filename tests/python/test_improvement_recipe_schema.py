"""Real SQLite/Fernet archive controls; synthetic result fixtures grant no retrieval."""
from _paths import ROOT, SERVER  # noqa: F401

import importlib
import hashlib
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
from resonance_store import GoalStore, Principal
import test_improvement_compose_schema as historical
import test_improvement_compose_permissions as permissions
import test_improvement_experiment_selection as selections


class RecipeSchemaTests(unittest.TestCase):
    history = staticmethod(historical.ComposeSchemaTests.history)
    definitions = staticmethod(historical.ComposeSchemaTests.definitions)
    blobs = staticmethod(historical.ComposeSchemaTests.blobs)
    backups = staticmethod(historical.ComposeSchemaTests.backups)

    @classmethod
    def setUpClass(cls):
        import _improvement_history
        raw = _improvement_history.source('3fad8de8', 'improvement_store')
        cls.old_raw_hash = hashlib.sha256(raw).hexdigest()
        cls.old = _improvement_history.load('3fad8de8', 'improvement_store', '_recipe_official8_store')

    def fixture(self, *, compose=False, prepared=False):
        if prepared:
            fixture = historical.operations.OperationExecutionTests()
        elif compose:
            fixture = permissions.ComposePermissionTests()
        else:
            fixture = selections.ExperimentSelectionTests()
        with patch.object(IM, 'ensure', side_effect=self.old.ensure):
            fixture.setUp()
            self.addCleanup(lambda: self.assertTrue(fixture.doCleanups(), 'Actual fixture cleanup failed'))
            if prepared:
                service = fixture.execution()
                fixture.prepared_receipt = fixture.prepared(service)[-1]
                fixture.prepared_service = service
            if compose:
                fixture.authorize()
        self.assertEqual(IM._schema_version(fixture.store), 8)
        return fixture

    def insert(self, store, table, row):
        with store._Tx(store) as connection:
            connection.execute('INSERT INTO ' + table + '(' + ','.join(row) + ') VALUES(' +
                               ','.join('?' for _ in row) + ')', list(row.values()))

    def recipe(self, fixture, identifier='recipe-a', **changes):
        with closing(fixture.store._conn()) as connection:
            candidate = connection.execute('SELECT * FROM improvement_skill_candidates ORDER BY ordinal').fetchone()
            context = connection.execute('SELECT * FROM improvement_trial_contexts WHERE id=?', (candidate['context_id'],)).fetchone()
            target = connection.execute('SELECT * FROM improvement_targets WHERE id=?', (candidate['target_id'],)).fetchone()
            report = connection.execute('SELECT * FROM improvement_comparison_reports ORDER BY rowid').fetchone()
        digest = hashlib.sha256(identifier.encode()).hexdigest()
        row = dict(id=identifier, brain_id=candidate['brain_id'], experiment_id=candidate['experiment_id'],
                   context_id=candidate['context_id'], target_id=candidate['target_id'],
                   base_revision_id=candidate['base_revision_id'], candidate_id=candidate['id'],
                   comparison_report_id=report['id'], manifest_hash=digest, manifest_blob_hash=digest,
                   source_basis_hash='1'*64, scope_hash=context['scope_hash'], engine_config_hash=context['engine_config_hash'],
                   owner_rule_hash='2'*64, target_protected_hash=target['protected_hash'], source_authority_hash='3'*64,
                   language='en', verdict='untested', checked_at=100.0, created_at=101.0, expires_at=201.0, actor='fixture-owner')
        row.update(changes)
        return row

    def ref(self, fixture, recipe_id='recipe-a', **changes):
        with closing(fixture.store._conn()) as connection:
            result = connection.execute('SELECT * FROM improvement_trial_results ORDER BY rowid').fetchone()
        row = dict(recipe_id=recipe_id, brain_id=result['brain_id'], position=0, trial_id=result['trial_id'],
                   attempt=result['attempt'], result_id=result['id'], result_hash=result['result_hash'], trace_hash='4'*64, trace_count=1)
        row.update(changes)
        return row

    def seal(self, fixture, identifier='recipe-a', **changes):
        row = dict(recipe_id=identifier, brain_id=fixture.owner.brain_id, status='active', generation=1,
                   reason=None, successor_id=None, changed_at=101.0)
        row.update(changes)
        self.insert(fixture.store, 'improvement_recipe_states', row)

    def transition(self, fixture, identifier='recipe-a', **changes):
        with fixture.store._Tx(fixture.store) as connection:
            connection.execute('UPDATE improvement_recipe_states SET ' + ','.join(key+'=?' for key in changes) +
                               ' WHERE recipe_id=?', [*changes.values(), identifier])

    def test_fresh_store_installs_actual_archive_and_exact_version_ten(self):
        with tempfile.TemporaryDirectory(prefix='recipe-fresh-') as directory:
            store = GoalStore(Path(directory) / 'resonance.sqlite3')
            IM.ensure(store)
            self.assertEqual(IM._schema_version(store), IM.SCHEMA_VERSION, 'Actual additive recipe migration is absent')
            with closing(store._conn()) as connection:
                importlib.import_module('improvement_recipe_view_schema').assert_installed(connection)
                self.assertEqual(connection.execute('PRAGMA foreign_key_check').fetchall(), [])

    def test_official_nonempty_eight_is_additive_preserves_compose_history_and_ciphertext(self):
        fixture = self.fixture(compose=True)
        before, definitions, ciphertext, backups = self.history(fixture.store), self.definitions(fixture.store), self.blobs(fixture.assets), self.backups(fixture.store)
        self.assertTrue(before['improvement_compose_authorizations'])
        self.assertTrue(before['improvement_comparison_reports'])
        import improvement_compose_schema as compose
        with patch.object(compose, 'migrate', side_effect=AssertionError('Installed8 must never rebuild')):
            IM.ensure(fixture.store)
        after = self.history(fixture.store)
        self.assertEqual({key: after[key] for key in before}, before)
        new_definitions = {row[1]: row for row in self.definitions(fixture.store)}
        self.assertEqual([new_definitions[row[1]] for row in definitions], definitions)
        self.assertEqual(ciphertext, self.blobs(fixture.assets))
        created = set(self.backups(fixture.store)) - set(backups)
        self.assertEqual(len(created), 1)
        backup = created.pop()
        self.assertTrue(str(backup).endswith('.pre-improvement-m2-recipes.bak'))
        with closing(sqlite3.connect(backup)) as connection:
            self.assertEqual(connection.execute('SELECT version FROM improvement_schema').fetchone()[0], 8)
            for table, rows in before.items():
                self.assertEqual(connection.execute('SELECT * FROM '+table+' ORDER BY rowid').fetchall(), rows)
        saved = self.backups(fixture.store)
        with patch.object(fixture.store, '_backup_before', side_effect=AssertionError('Repeated9 cannot back up')):
            IM.ensure(fixture.store)
        self.assertEqual(self.backups(fixture.store), saved)
        with self.assertRaises(self.old.SchemaError): self.old.ensure(fixture.store)

    def test_actual_prepared_lease_workspace_and_call_remain_unchanged(self):
        fixture = self.fixture(prepared=True)
        before, ciphertext = self.history(fixture.store), self.blobs(fixture.assets)
        IM.ensure(fixture.store)
        self.assertEqual({key: self.history(fixture.store)[key] for key in before}, before)
        self.assertEqual(self.blobs(fixture.assets), ciphertext)
        self.assertEqual(fixture.prepared_service.workspace.validate(fixture.prepared_receipt)['data'], fixture.data)

    def test_known_eight_cold_reader_neither_migrates_nor_decrypts(self):
        fixture = self.fixture()
        before = self.definitions(fixture.store)
        with patch.object(IM, 'ensure', side_effect=AssertionError('Cold read cannot migrate')), \
                patch.object(fixture.assets.blobs, 'read', side_effect=AssertionError('Metadata cannot decrypt')):
            reader = IM.read_existing(fixture.store.path, fixture.assets.blobs)
            self.assertTrue(reader.targets(fixture.owner))
        self.assertEqual(IM._schema_version(fixture.store), 8)
        self.assertEqual(self.definitions(fixture.store), before)

    def predecessor(self, version):
        directory = tempfile.TemporaryDirectory(prefix='recipe-older-')
        self.addCleanup(directory.cleanup)
        store = GoalStore(Path(directory.name) / 'resonance.sqlite3')
        blocks = ['case', 'trial', 'candidate', 'experiment', 'operation', 'view']
        with store._Tx(store) as connection:
            for sql in IM._SCHEMA: connection.execute(sql)
            IM._immutable_triggers(connection, ('improvement_revisions', 'improvement_bundles', 'improvement_bundle_assets', 'improvement_events'))
            for name in blocks[:version-1]:
                block = importlib.import_module('improvement_'+name+'_schema')
                for sql in block.SCHEMA: connection.execute(sql)
                IM._immutable_triggers(connection, block.IMMUTABLE)
            connection.execute('INSERT INTO improvement_schema VALUES(1,?)', (version,))
        return store

    def test_known_one_through_seven_follow_actual_predecessor_sql(self):
        import improvement_compose_schema as compose
        for version in range(1, 8):
            with self.subTest(version=version):
                store = self.predecessor(version)
                IM.ensure(store)
                self.assertEqual(IM._schema_version(store), IM.SCHEMA_VERSION)
                with closing(store._conn()) as connection:
                    compose.assert_installed(connection)
                    importlib.import_module('improvement_recipe_view_schema').assert_installed(connection)
                    self.assertEqual(connection.execute('PRAGMA foreign_keys').fetchone()[0], 1)

    def test_drafts_collisions_partial_nine_and_future_refuse_before_backup(self):
        for mutation in ('missing', 'changed', 'collision', 'partial9', 'future11'):
            with self.subTest(mutation=mutation):
                fixture = self.fixture()
                with fixture.store._Tx(fixture.store) as connection:
                    if mutation in ('missing', 'changed'):
                        connection.execute('DROP TRIGGER improvement_composer_permission')
                        if mutation == 'changed':
                            connection.execute('CREATE TRIGGER improvement_composer_permission BEFORE INSERT ON improvement_operations BEGIN SELECT 1; END')
                    elif mutation == 'collision': connection.execute('CREATE TABLE improvement_recipe_private(secret TEXT)')
                    else: connection.execute('UPDATE improvement_schema SET version=?', (9 if mutation == 'partial9' else 11,))
                before, definitions, backups = self.history(fixture.store), self.definitions(fixture.store), self.backups(fixture.store)
                with self.assertRaises((IM.SchemaError, IM.ConflictError)): IM.ensure(fixture.store)
                self.assertEqual(self.history(fixture.store), before)
                self.assertEqual(self.definitions(fixture.store), definitions)
                self.assertEqual(self.backups(fixture.store), backups)

    def test_interrupted_middle_ddl_rolls_back_complete_eight_and_retry_keeps_backup(self):
        fixture = self.fixture()
        schema = importlib.import_module('improvement_recipe_schema')
        before, definitions = self.history(fixture.store), self.definitions(fixture.store)
        actual = schema.statements()
        with patch.object(schema, 'statements', return_value=(*actual[:2], 'INVALID INJECTED SQL', *actual[2:])), self.assertRaises(sqlite3.OperationalError):
            IM.ensure(fixture.store)
        self.assertEqual(IM._schema_version(fixture.store), 8)
        self.assertEqual(self.history(fixture.store), before)
        self.assertEqual(self.definitions(fixture.store), definitions)
        backups = self.backups(fixture.store)
        IM.ensure(fixture.store)
        self.assertEqual(self.backups(fixture.store), backups)
        with closing(fixture.store._conn()) as connection:
            self.assertEqual(connection.execute('PRAGMA foreign_keys').fetchone()[0], 1)
            self.assertEqual(connection.execute('PRAGMA foreign_key_check').fetchall(), [])

    def test_case_insensitive_private_table_collision_refuses_before_backup(self):
        fixture = self.fixture()
        with fixture.store._Tx(fixture.store) as connection:
            connection.execute('CREATE TABLE IMPROVEMENT_RECIPES(private TEXT)')
        definitions, backups = self.definitions(fixture.store), self.backups(fixture.store)
        with self.assertRaises((IM.SchemaError, IM.ConflictError, sqlite3.OperationalError)): IM.ensure(fixture.store)
        self.assertEqual(IM._schema_version(fixture.store), 8)
        self.assertEqual(self.definitions(fixture.store), definitions)
        self.assertEqual(self.backups(fixture.store), backups, 'SQLite identifiers collide regardless of case; refuse before backup')

    def test_two_connections_first_writers_publish_one_nine_and_one_preserved_backup(self):
        fixture = self.fixture()
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
        self.assertEqual(len(set(self.backups(fixture.store))-set(backups)), 1)
        self.assertEqual({key: self.history(fixture.store)[key] for key in before}, before)

    def test_real_recipe_refs_seal_and_history_immutable(self):
        fixture = self.fixture()
        IM.ensure(fixture.store)
        self.insert(fixture.store, 'improvement_recipes', self.recipe(fixture))
        self.insert(fixture.store, 'improvement_recipe_trial_refs', self.ref(fixture))
        self.seal(fixture)
        for table in ('improvement_recipes', 'improvement_recipe_trial_refs'):
            for action in ('DELETE FROM '+table, 'UPDATE '+table+' SET brain_id=brain_id'):
                with self.subTest(action=action), self.assertRaises(sqlite3.IntegrityError), fixture.store._Tx(fixture.store) as connection:
                    connection.execute(action)
        with self.assertRaises(sqlite3.IntegrityError):
            self.insert(fixture.store, 'improvement_recipe_trial_refs', self.ref(fixture, position=1))

    def test_recipe_identity_scope_hash_dates_report_and_candidate_mismatches_fail_sql(self):
        fixture = self.fixture(compose=True)
        IM.ensure(fixture.store)
        with closing(fixture.store._conn()) as connection:
            second = connection.execute('SELECT id FROM improvement_skill_candidates WHERE ordinal=2').fetchone()[0]
            other_target = connection.execute('SELECT id FROM improvement_targets WHERE id!=?', (self.recipe(fixture)['target_id'],)).fetchone()
        changes = [dict(brain_id='other-brain'), dict(context_id='missing'), dict(experiment_id='missing'),
                   dict(base_revision_id='missing'), dict(target_id='missing'), dict(candidate_id=second),
                   dict(scope_hash='a'*64), dict(engine_config_hash='a'*64), dict(target_protected_hash='a'*64),
                   dict(manifest_hash='A'*64), dict(manifest_hash='g'*64), dict(manifest_blob_hash='a'*64),
                   dict(source_basis_hash='1'*63), dict(owner_rule_hash=''), dict(source_authority_hash='z'*64),
                   dict(language='fr'), dict(verdict='eligible'), dict(actor=''), dict(id=''), dict(checked_at=-1),
                   dict(checked_at=102), dict(created_at=2**53), dict(expires_at=101), dict(expires_at=2592102),
                   dict(created_at='tomorrow'), dict(checked_at=None), dict(comparison_report_id='missing')]
        if other_target: changes.append(dict(target_id=other_target[0]))
        for change in changes:
            with self.subTest(change=change), self.assertRaises(sqlite3.IntegrityError):
                self.insert(fixture.store, 'improvement_recipes', self.recipe(fixture, **change))
        # SQL pins owner-rule metadata but does not authenticate its host derivation.
        self.insert(fixture.store, 'improvement_recipes', self.recipe(fixture, owner_rule_hash='a'*64, comparison_report_id=None))

    def test_trial_refs_require_actual_same_trial_attempt_result_and_owned_experiment(self):
        fixture = self.fixture()
        IM.ensure(fixture.store)
        self.insert(fixture.store, 'improvement_recipes', self.recipe(fixture))
        with closing(fixture.store._conn()) as connection:
            other = connection.execute('SELECT id FROM improvement_trial_results ORDER BY rowid DESC').fetchone()[0]
        for change in (dict(brain_id='other'), dict(result_id=other), dict(result_hash='a'*64), dict(trial_id='missing'),
                       dict(attempt=2), dict(attempt=3), dict(position=-1), dict(position=4000), dict(position=0.5),
                       dict(trace_count=0), dict(trace_count=1.5), dict(trace_hash='A'*64)):
            with self.subTest(change=change), self.assertRaises(sqlite3.IntegrityError):
                self.insert(fixture.store, 'improvement_recipe_trial_refs', self.ref(fixture, **change))
        self.insert(fixture.store, 'improvement_recipe_trial_refs', self.ref(fixture))

    def test_existing_foreign_and_unrelated_context_base_experiment_and_trial_cannot_be_rebound(self):
        fixture = self.fixture()
        IM.ensure(fixture.store)
        original = self.recipe(fixture)
        content = b'---\nname: foreign\n---\nPreserve foreign owner rules.\n'
        digest = hashlib.sha256(content).hexdigest()
        foreign = fixture.assets.capture(Principal('owner', 'other-owner', 'foreign-brain'),
            IM.SourceSnapshot('skill', 'skills/foreign/SKILL.md', digest, digest, True, 'user_protected', 'foreign-inode'),
            content, event_key='fixture-foreign-source')
        with closing(fixture.store._conn()) as connection:
            context = dict(connection.execute('SELECT * FROM improvement_trial_contexts WHERE id=?', (original['context_id'],)).fetchone())
            revision = dict(connection.execute('SELECT * FROM improvement_revisions WHERE id=?', (original['base_revision_id'],)).fetchone())
            experiment = dict(connection.execute('SELECT * FROM improvement_experiments').fetchone())
            result = dict(connection.execute('SELECT * FROM improvement_trial_results ORDER BY rowid').fetchone())
            trial = dict(connection.execute('SELECT * FROM improvement_trials WHERE id=?', (result['trial_id'],)).fetchone())
        context.update(id='unrelated-context', experiment_id='unrelated-experiment')
        self.insert(fixture.store, 'improvement_trial_contexts', context)
        revision.update(id='unrelated-base', manifest_hash='d'*64)
        self.insert(fixture.store, 'improvement_revisions', revision)
        fixture.h.h.plans().records.begin_stop(fixture.owner, original['experiment_id'], kind='cancelled',
            reason='owner_requested', expected_generation=fixture.saved['generation'], event_key='fixture-stop-for-other-experiment')
        with fixture.store._Tx(fixture.store) as connection:
            connection.execute("UPDATE improvement_experiments SET phase='cancelled',generation=generation+1 WHERE id=?", (original['experiment_id'],))
        self.insert(fixture.store, 'improvement_trial_context_grants', dict(context_id=context['id'], brain_id=context['brain_id'], generation=1, status='active', revoked_at=None))
        experiment.update(id='unrelated-experiment', context_id=context['id'], phase='proposed', generation=1)
        self.insert(fixture.store, 'improvement_experiments', experiment)
        for change in (dict(brain_id='foreign-brain'), dict(target_id=foreign['target_id']), dict(base_revision_id=foreign['revision_id']),
                       dict(base_revision_id=revision['id']), dict(context_id=context['id']), dict(experiment_id=experiment['id'])):
            with self.subTest(change=change), self.assertRaises(sqlite3.IntegrityError):
                self.insert(fixture.store, 'improvement_recipes', self.recipe(fixture, **change))
        self.insert(fixture.store, 'improvement_recipes', original)
        # Real completed result/attempt exists, but this extra trial has no owned
        # preparation/comparison link. Result ids alone cannot grant membership.
        trial.update(id='unlinked-trial', logical_key='unlinked-logical')
        self.insert(fixture.store, 'improvement_trials', trial)
        from agent_ledger import CallLedger
        with fixture.store._Tx(fixture.store) as connection:
            call = CallLedger(fixture.store).reserve(purpose='improve_probe', reason_ref='fixture-unlinked', brain_id=fixture.owner.brain_id,
                context_ref='fixture-unlinked', obligation=True, mirror_ref='fixture-unlinked', attempt=1, now=101, c=connection)
        self.insert(fixture.store, 'improvement_trial_attempts', dict(trial_id=trial['id'], brain_id=trial['brain_id'], attempt=1,
            status='completed', call_id=call, created_at=101, updated_at=101))
        result.update(id='unlinked-result', trial_id=trial['id'])
        self.insert(fixture.store, 'improvement_trial_results', result)
        with self.assertRaises(sqlite3.IntegrityError):
            self.insert(fixture.store, 'improvement_recipe_trial_refs', self.ref(fixture, trial_id=trial['id'], result_id=result['id']))

    def test_availability_cas_revoke_expiry_supersession_and_terminal_erasure(self):
        fixture = self.fixture()
        IM.ensure(fixture.store)
        identifiers = ('recipe-a', 'recipe-b', 'recipe-c', 'recipe-d', 'recipe-other', 'recipe-vi')
        for identifier in identifiers:
            self.insert(fixture.store, 'improvement_recipes', self.recipe(fixture, identifier,
                owner_rule_hash='a'*64 if identifier=='recipe-other' else '2'*64, language='vi' if identifier=='recipe-vi' else 'en'))
        for change in (dict(status='revoked'), dict(generation=2), dict(reason='owner_revoked'), dict(successor_id='recipe-b'), dict(changed_at=102)):
            with self.subTest(initial=change), self.assertRaises(sqlite3.IntegrityError): self.seal(fixture, **change)
        for identifier in identifiers: self.seal(fixture, identifier)
        for change in (dict(status='active', generation=2), dict(status='revoked', reason=None, generation=2),
                       dict(status='revoked', reason='owner_revoked', generation=1), dict(status='revoked', reason='owner_revoked', generation=2, changed_at=100),
                       dict(status='expired', reason='retention_expired', generation=2, changed_at=200),
                       dict(status='superseded', reason='superseded', successor_id='recipe-a', generation=2),
                       dict(status='superseded', reason='superseded', successor_id='recipe-other', generation=2),
                       dict(status='superseded', reason='superseded', successor_id='recipe-vi', generation=2),
                       dict(recipe_id='recipe-b', generation=2), dict(brain_id='foreign-brain', generation=2),
                       dict(status='erased', reason='owner_erased', generation=2, changed_at=2**53),
                       dict(status='revoked', reason='owner_revoked', successor_id='recipe-b', generation=2)):
            with self.subTest(update=change), self.assertRaises(sqlite3.IntegrityError): self.transition(fixture, **change)
        self.transition(fixture, status='revoked', reason='owner_revoked', generation=2, changed_at=102)
        with self.assertRaises(sqlite3.IntegrityError): self.transition(fixture, status='active', reason=None, generation=3)
        self.transition(fixture, status='erased', reason='source_erased', generation=3, changed_at=103)
        with self.assertRaises(sqlite3.IntegrityError): self.transition(fixture, status='erased', reason='owner_erased', generation=4, changed_at=104)
        self.transition(fixture, 'recipe-b', status='expired', reason='retention_expired', generation=2, changed_at=201)
        with self.assertRaises(sqlite3.IntegrityError):
            self.transition(fixture, 'recipe-c', status='superseded', reason='superseded', successor_id='recipe-b', generation=2)
        self.transition(fixture, 'recipe-b', status='erased', reason='owner_erased', generation=3, changed_at=202)
        self.transition(fixture, 'recipe-c', status='superseded', reason='superseded', successor_id='recipe-d', generation=2, changed_at=102)
        self.transition(fixture, 'recipe-c', status='erased', reason='owner_erased', successor_id=None, generation=3, changed_at=103)
        with self.assertRaises(sqlite3.IntegrityError), fixture.store._Tx(fixture.store) as connection: connection.execute('DELETE FROM improvement_recipe_states')

    def test_sql_replace_cannot_rewrite_history_or_remove_a_revocation_tombstone(self):
        fixture = self.fixture()
        IM.ensure(fixture.store)
        recipe = self.recipe(fixture)
        ref = self.ref(fixture)
        self.insert(fixture.store, 'improvement_recipes', recipe)
        self.insert(fixture.store, 'improvement_recipe_trial_refs', ref)
        for table, row in (('improvement_recipes', dict(recipe, verdict='helped')),
                           ('improvement_recipes', dict(recipe, id='recipe-replacement')),
                           ('improvement_recipe_trial_refs', dict(ref, trace_hash='e'*64)),
                           ('improvement_recipe_trial_refs', dict(ref, position=1))):
            with self.subTest(table=table), self.assertRaises(sqlite3.IntegrityError), fixture.store._Tx(fixture.store) as connection:
                connection.execute('INSERT OR REPLACE INTO '+table+'('+','.join(row)+') VALUES('+','.join('?' for _ in row)+')', list(row.values()))
        self.seal(fixture)
        self.transition(fixture, status='revoked', reason='owner_revoked', generation=2, changed_at=102)
        with self.assertRaises(sqlite3.IntegrityError), fixture.store._Tx(fixture.store) as connection:
            connection.execute("INSERT OR REPLACE INTO improvement_recipe_states VALUES(?,?,'active',1,NULL,NULL,101)", ('recipe-a', fixture.owner.brain_id))

    def test_embedded_nul_suffix_cannot_extend_any_archive_digest(self):
        fixture = self.fixture()
        IM.ensure(fixture.store)
        recipe = self.recipe(fixture)
        fields = ('source_basis_hash', 'scope_hash', 'engine_config_hash', 'owner_rule_hash',
                  'target_protected_hash', 'source_authority_hash')
        def malformed(value):
            return value+'\0suffix', value+'\0', value[:32]+'\0'+value[32:]
        changes = [{field: value} for field in fields for value in malformed(recipe[field])]
        changes.extend(dict(manifest_hash=value, manifest_blob_hash=value) for value in malformed(recipe['manifest_hash']))
        for change in changes:
            row = dict(recipe, **change)
            with self.subTest(recipe_digests=tuple(change)), closing(fixture.store._conn()) as connection:
                connection.execute('BEGIN IMMEDIATE')
                try:
                    with self.assertRaises(sqlite3.IntegrityError):
                        connection.execute('INSERT INTO improvement_recipes('+','.join(row)+') VALUES('+','.join('?' for _ in row)+')', list(row.values()))
                finally:
                    connection.rollback()
        self.insert(fixture.store, 'improvement_recipes', recipe)
        for field in ('result_hash', 'trace_hash'):
            for value in malformed(self.ref(fixture)[field]):
                ref = self.ref(fixture, **{field: value})
                with self.subTest(ref_digest=field, value=value), closing(fixture.store._conn()) as connection:
                    connection.execute('BEGIN IMMEDIATE')
                    try:
                        with self.assertRaises(sqlite3.IntegrityError):
                            connection.execute('INSERT INTO improvement_recipe_trial_refs('+','.join(ref)+') VALUES('+','.join('?' for _ in ref)+')', list(ref.values()))
                    finally:
                        connection.rollback()

    def test_nine_role_and_concrete_compose_connection_authenticate_both_guard_families(self):
        fixture = self.fixture(compose=True)
        IM.ensure(fixture.store)
        import improvement_operation_schema as operations
        with closing(fixture.store._conn()) as connection:
            fixture.service._connection(connection)
            operations.assert_installed(connection)
        for trigger in ('improvement_composer_permission', 'improvement_recipe_states_update'):
            with fixture.store._Tx(fixture.store) as connection: connection.execute('DROP TRIGGER '+trigger)
            for validate in (fixture.service._connection, operations.assert_installed):
                with closing(fixture.store._conn()) as connection, self.assertRaises((IM.ConflictError, IM.SchemaError)): validate(connection)
            if trigger=='improvement_composer_permission':
                import improvement_compose_schema as compose
                sql = next(sql for sql in compose.statements() if sql.startswith('CREATE TRIGGER '+trigger+' '))
                with fixture.store._Tx(fixture.store) as connection: connection.execute(sql)


if __name__ == '__main__': unittest.main()
