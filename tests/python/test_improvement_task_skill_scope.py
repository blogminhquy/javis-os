"""Real ordinary owner/runtime/M0 task snapshots; no provider/native process."""
from _paths import ROOT, SERVER  # noqa: F401

import contextvars
import copy
import hashlib
import importlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing, contextmanager
from unittest.mock import patch

from cryptography.fernet import Fernet
from capability_registry import CapabilityRegistry
import context_runtime as CR
import improvement_store as IM
from improvement_blobs import AssetUnavailable, RevisionBlobs
from resonance_store import GoalStore, Principal
import skill_router
import turn_context as TC


class TaskSkillScopeTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('improvement_task_skill_scope'),
            'actual owned ordinary task skill snapshot missing')
        self.m = importlib.import_module('improvement_task_skill_scope')
        directory = tempfile.TemporaryDirectory(prefix='tss-')
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.brain = self.root / 'brain'; self.brain.mkdir()
        self.owner = Principal('owner', 'owner', str(self.brain))
        codec = Fernet(Fernet.generate_key())
        blobs = RevisionBlobs(self.root / 'assets',
            encrypt=lambda value: 'enc:' + codec.encrypt(value.encode()).decode(),
            decrypt=lambda value: codec.decrypt(value.removeprefix('enc:').encode()).decode())
        self.assets = IM.ImprovementStore(GoalStore(self.root / 'm0.db'), blobs)
        IM.ensure(self.assets.store)
        self.registry = CapabilityRegistry(self.root / 'registry')
        self.addCleanup(self.registry.close)
        self.enterContext(patch('capability_registry.get_registry', return_value=self.registry))
        self.runtime = CR.ObserveRuntime(self.root / 'runtime',
            settings_reader=lambda: {'context_runtime': {'mode': 'observe'}})
        self.addCleanup(self.runtime.close)
        self.path = self.brain / 'skills' / 'report' / 'SKILL.md'
        self.path.parent.mkdir(parents=True)
        self.header = (b'---\r\nname: Owner report\r\nname_en: English report\r\n'
            b'description: Bao cao du lieu\r\ndescription_en: Summarize selected rows\r\n'
            b'group: Reports\r\nlearn_lock: true\r\n---\r\n')
        self.original = self.header + b'Private original body.\r\n'
        self.path.write_bytes(self.original)
        self.turns = []
        self.trace, self.turn = self.new_turn()
        self.scopes = []
        self.addCleanup(self.close_scopes)
        self.addCleanup(self.reset_turns)
        self.enterContext(patch('subprocess.run', side_effect=AssertionError('No native/model/account commands')))
        self.enterContext(patch('subprocess.Popen', side_effect=AssertionError('No native/model/account commands')))

    def new_turn(self):
        trace = self.runtime.start_turn('session-owner', str(self.brain), 'dashboard')
        self.assertIsNotNone(trace)
        trace_token = CR.bind_trace(trace)
        turn = TC.bind(TC.make('dashboard', chat_id='session-owner', la_chu=True,
            session_id='session-owner', message_id=len(self.turns) + 1))
        self.turns.append((turn, trace_token))
        return trace, turn

    def reset_turns(self):
        for turn, trace in reversed(self.turns):
            TC.reset(turn); CR.reset_trace(trace)
        self.turns.clear()

    def close_scopes(self):
        for scope in self.scopes: scope.close()

    def open(self, **changes):
        scope = self.m.TaskSkillScope.open(changes.pop('assets', self.assets), changes.pop('principal', self.owner),
            **{'turn_token': self.turn, 'runtime': self.runtime, 'trace': self.trace, **changes})
        self.scopes.append(scope)
        return scope

    def events(self, operation):
        with closing(self.assets.store._conn()) as connection:
            return [dict(row) for row in connection.execute(
                'SELECT * FROM improvement_events WHERE operation=?', (operation,))]

    def test_real_factory_freezes_translations_and_defensive_private_projection_without_registry_write(self):
        before = self.registry.revision(self.brain)
        scope = self.open()
        first = scope.manifests(lang='en')
        self.assertEqual(first[0]['name'], 'English report')
        self.assertEqual(first[0]['description'], 'Summarize selected rows')
        self.assertEqual(scope.manifests()[0]['description'], 'Bao cao du lieu')
        first[0]['name'] = 'caller mutation'
        self.assertEqual(scope.manifests(lang='en')[0]['name'], 'English report')
        self.assertEqual(len(scope.inventory_hash), 64)
        self.assertIn(scope.inventory_hash, scope.registry_revision)
        self.assertEqual(self.registry.revision(self.brain), before)
        self.assertEqual(len(self.events('ordinary_task_skill_scope')), 1)
        self.assertEqual(self.events('ordinary_task_skill_asset'), [], 'discovery must not pin any body')

    def test_factory_refuses_public_dict_fake_token_foreign_owner_and_noncurrent_trace(self):
        fake = TC.Token(None, self.turn._binding)
        for changes in ({'turn_token': TC.current()}, {'turn_token': fake},
                {'trace': copy.copy(self.trace)}, {'principal': Principal('agent', 'owner', str(self.brain))},
                {'principal': Principal('owner', 'owner', str(self.root / 'foreign'))}):
            with self.subTest(changes=list(changes)), self.assertRaises(self.m.ScopeUnavailable):
                self.open(**changes)
        self.assertEqual(self.events('ordinary_task_skill_scope'), [])

    def test_actual_running_task_step_brain_session_rows_are_required(self):
        for table, identity, column, foreign in (
                ('runtime_tasks', self.trace.task_id, 'status', 'COMPLETED'),
                ('runtime_tasks', self.trace.task_id, 'brain', str(self.root / 'foreign')),
                ('runtime_tasks', self.trace.task_id, 'session_id', 'foreign'),
                ('runtime_steps', self.trace.step_id, 'status', 'COMPLETED'),
                ('runtime_steps', self.trace.step_id, 'task_id', 'foreign')):
            with self.runtime._lock:
                db = self.runtime._conn()
                original = db.execute(f'SELECT {column} FROM {table} WHERE id=?', (identity,)).fetchone()[0]
                # Foreign task_id must remain a real FK for this metadata mutation.
                if column == 'task_id': foreign = self.runtime.start_turn('other', str(self.brain), 'dashboard').task_id
                with db: db.execute(f'UPDATE {table} SET {column}=? WHERE id=?', (foreign, identity))
            try:
                with self.subTest(table=table, column=column), self.assertRaises(self.m.ScopeUnavailable): self.open()
            finally:
                with self.runtime._lock, db:
                    db.execute(f'UPDATE {table} SET {column}=? WHERE id=?', (original, identity))

    def test_selected_body_edit_keeps_exact_first_bytes_and_next_actual_task_reads_new_bytes(self):
        scope = self.open(); asset = scope.read('report')
        self.assertEqual(asset.content, self.original)
        self.assertEqual(asset.content_hash, hashlib.sha256(self.original).hexdigest())
        replacement = self.header + b'New ordinary baseline body.\r\n'
        self.path.write_bytes(replacement)
        self.assertEqual(scope.read('report'), asset)
        self.assertEqual(self.open().read('report'), asset, 'second facade of same actual task shares durable first pin')
        self.trace, self.turn = self.new_turn()
        self.assertEqual(self.open().read('report').content, replacement)

    def test_unselected_header_drift_or_expected_manifest_mismatch_refuses_without_body_pin(self):
        scope = self.open(); expected = scope.manifests()[0]
        with self.assertRaises(self.m.ScopeUnavailable): scope.read('report', expected_manifest={**expected, 'frontmatter_hash': 'f' * 64})
        self.path.write_bytes(self.original.replace(b'Bao cao du lieu', b'Changed objective'))
        with self.assertRaises(self.m.ScopeUnavailable): scope.read('report')
        self.assertEqual(self.events('ordinary_task_skill_asset'), [])

    def test_disabled_and_source_precedence_changes_refuse_even_after_body_was_pinned(self):
        scope = self.open(); scope.read('report')
        disabled = self.brain / 'skills' / '.disabled' / 'report'
        disabled.mkdir(parents=True); self.path.replace(disabled / 'SKILL.md')
        mirror = self.brain / '.claude' / 'skills' / 'report'; mirror.mkdir(parents=True)
        (mirror / 'SKILL.md').write_bytes(self.original)
        with self.assertRaises(self.m.ScopeUnavailable): scope.read('report')

    def test_dead_turn_completed_runtime_and_mutated_trace_cannot_read_bound_scope(self):
        scope = self.open(); scope.read('report')
        self.runtime.finish(self.trace)
        with self.assertRaises(self.m.ScopeUnavailable): scope.read('report')
        self.trace, self.turn = self.new_turn(); second = self.open()
        saved = self.trace.session_id; self.trace.session_id = 'foreign'
        try:
            with self.assertRaises(self.m.ScopeUnavailable): second.manifests()
        finally: self.trace.session_id = saved
        self.turn._binding.alive = False
        with self.assertRaises(self.m.ScopeUnavailable): second.read('report')

    def test_private_binding_is_foreign_closed_or_dead_not_unbound_fallback(self):
        self.assertIsNone(self.m.current(self.brain))
        scope = self.open(); token = self.m.bind(scope)
        try:
            self.assertIs(self.m.current(self.brain), scope)
            with self.assertRaises(self.m.ScopeUnavailable): self.m.current(self.root / 'other')
            copied = contextvars.copy_context(); scope.close()
            with self.assertRaises(self.m.ScopeUnavailable): copied.run(self.m.current, self.brain)
        finally: self.m.reset(token)
        self.assertIsNone(self.m.current(self.brain))

    def test_same_scope_concurrent_reads_commit_one_encrypted_pin_and_cold_receipt_authenticates_blob(self):
        scope = self.open()
        contexts = [contextvars.copy_context(), contextvars.copy_context()]
        with ThreadPoolExecutor(max_workers=2) as pool:
            actual = list(pool.map(lambda ctx: ctx.run(scope.read, 'report'), contexts))
        self.assertEqual(actual[0], actual[1])
        rows = self.events('ordinary_task_skill_asset'); self.assertEqual(len(rows), 1)
        self.assertNotIn('Private original body', rows[0]['result_json'])
        envelope = json.loads(rows[0]['result_json'])
        encrypted = self.assets.blobs._path(self.owner.brain_id, envelope['blob_hash']).read_text()
        self.assertTrue(encrypted.startswith('enc:')); self.assertNotIn('Private original body', encrypted)
        scope.close()
        receipt = self.m.TaskSkillScope.read_receipt(self.assets, self.owner, scope.scope_id, 'report')
        self.assertEqual(receipt['content_hash'], actual[0].content_hash)
        self.assets.blobs._path(self.owner.brain_id, receipt['content_hash']).unlink()
        with self.assertRaises(AssetUnavailable):
            self.m.TaskSkillScope.read_receipt(self.assets, self.owner, scope.scope_id, 'report')

    def test_inventory_reads_only_bounded_descriptor_header_without_pinning_body(self):
        self.path.write_bytes(self.header + b'SECRET_BODY_' * 10000)
        calls = []
        original = self.m.open_skill_source
        @contextmanager
        def watch(*args):
            with original(*args) as handle:
                class HeaderReader:
                    def fileno(self): return handle.fileno()
                    def read(self, count=-1):
                        calls.append(count)
                        return handle.read(count)
                yield HeaderReader()
        with patch.object(self.m, 'open_skill_source', watch): self.open()
        self.assertTrue(calls)
        self.assertTrue(all(0 < count <= 16384 for count in calls), calls)
        self.assertEqual(self.events('ordinary_task_skill_asset'), [])

    def test_actual_external_skill_symlink_refuses_scope_capture(self):
        outside = self.root / 'outside.md'; outside.write_bytes(self.original)
        self.path.unlink()
        try: self.path.symlink_to(outside)
        except OSError as error: self.skipTest('file symlink unavailable: ' + str(getattr(error, 'winerror', None)))
        with self.assertRaises(self.m.ScopeUnavailable): self.open()
        self.assertEqual(self.events('ordinary_task_skill_scope'), [])

    def test_turn_revoked_during_pin_encryption_cannot_publish_asset_event(self):
        scope = self.open(); original = self.assets.blobs.write
        def revoke(brain, content):
            digest = original(brain, content)
            if content == self.original: self.turn._binding.alive = False
            return digest
        with patch.object(self.assets.blobs, 'write', side_effect=revoke):
            with self.assertRaises(self.m.ScopeUnavailable): scope.read('report')
        self.assertEqual(self.events('ordinary_task_skill_asset'), [])

    def test_interleaved_task_languages_have_distinct_private_revisions_without_global_refresh(self):
        first = self.open(); first_context = contextvars.copy_context()
        self.path.write_bytes(self.original.replace(b'English report', b'Other English name'))
        self.trace, self.turn = self.new_turn(); second = self.open()
        self.assertNotEqual(first.inventory_hash, second.inventory_hash)
        self.assertEqual(first_context.run(first.manifests, lang='en')[0]['name'], 'English report')
        self.assertEqual(second.manifests(lang='en')[0]['name'], 'Other English name')
        self.assertEqual(first_context.run(first.manifests)[0]['description'], second.manifests()[0]['description'])


if __name__ == '__main__': unittest.main()
