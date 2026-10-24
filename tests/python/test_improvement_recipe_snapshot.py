"""Actual extracted Library behavior inside a disposable, checked owner root."""
from _paths import ROOT, SERVER  # noqa: F401

import ast
import copy
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

TEST_ROOT = Path(tempfile.mkdtemp(prefix='recipe-tests-'))
for key, name in {'JAVIS_STATE_DIR': 'state', 'BRAINS_DIR': 'brains', 'OBSIDIAN_VAULT_PATH': 'vault',
                  'BRAIN_PATH': 'brain', 'SOURCES_PATH': 'sources'}.items():
    os.environ[key] = str(TEST_ROOT / name)

if importlib.util.find_spec('improvement_recipe_snapshot'):
    import improvement_recipe_snapshot as RS
else:
    RS = None


def digest(value):
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def entry(number=1, verdict='untested'):
    return {'recipe_id': f'recipe_{number}', 'manifest_hash': digest(str(number)),
            'cue': 'Khi cần kiểm tra', 'procedure': 'Đọc đầu vào.\nGiữ bằng chứng.\r\nXong.\n',
            'evidence_summary': 'Only the supplied observation.', 'verdict': verdict,
            'confidence_basis': 'Fixture observation; no causal upgrade.'}


class SnapshotTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(RS, 'The actual Library private snapshot is not implemented')
        self.snapshot = RS.RecipeSnapshot(brain_id='private-brain-name', scope_hash=digest('scope'),
                                          engine_config_hash=digest('engine'), language='vi')
        self.addCleanup(self.snapshot.close)

    def test_actual_add_tree_index_and_unicode_are_read_back(self):
        item = entry()
        result = self.snapshot.replace([item])
        self.assertEqual(result, self.snapshot.read())
        self.assertEqual(set(result), {'snapshot_hash', 'entries', 'index_text', 'coverage',
                                       'authority_status', 'business_proof'})
        self.assertEqual(result['coverage'], 'derived_snapshot')
        self.assertEqual(result['authority_status'], 'not_checked')
        self.assertIs(result['business_proof'], False)
        stored = result['entries'][0]
        self.assertEqual({key: stored[key] for key in item}, item)
        self.assertEqual(list(stored['tree'].values()), [item['procedure']])
        self.assertIn('## Transferable lesson', stored['experience_text'])
        self.assertIn('- **lesson**: Procedure:\nĐọc đầu vào.\nGiữ bằng chứng.\nXong.\n',
                      stored['experience_text'])
        self.assertIn('untested', stored['experience_text'])
        self.assertIn('1 skills; 0 always-on chars', result['index_text'])
        self.assertIn(item['cue'], result['index_text'])
        self.assertNotIn('private-brain-name', json.dumps(result))
        self.assertNotIn(str(self.snapshot._root), json.dumps(result))
        self.assertTrue(all(path.startswith('procedures/recipe-') and path.endswith('/SKILL.md')
                            for path in stored['tree']))

    def test_retain_one_forget_all_and_no_entry(self):
        items = [entry(n) for n in range(3)]
        self.snapshot.replace(items)
        self.assertEqual(len(self.snapshot.read()['entries']), 3)
        result = self.snapshot.replace([items[1]])
        self.assertEqual([e['recipe_id'] for e in result['entries']], ['recipe_1'])
        self.assertEqual(len(self.snapshot._library.entries()), 1)
        empty = self.snapshot.replace([])
        self.assertEqual(empty['entries'], [])
        self.assertEqual(self.snapshot._library.entries(), [])
        self.assertIsNone(self.snapshot._library.context_dir())
        self.assertIn('empty', empty['index_text'])
        self.assertEqual(empty, self.snapshot.read())

    def test_negative_and_confounded_verdicts_never_upgrade(self):
        for verdict in ('helped', 'hurt', 'no_observed_effect', 'confounded', 'untested'):
            result = self.snapshot.replace([entry(verdict=verdict)])
            self.assertEqual(result['entries'][0]['verdict'], verdict)
            self.assertIn('verdict: ' + verdict, result['entries'][0]['experience_text'])

    def test_caller_and_result_mutation_cannot_change_snapshot(self):
        items = [entry()]
        result = self.snapshot.replace(items)
        expected = copy.deepcopy(result)
        items[0]['procedure'] = 'Changed'
        items.clear()
        result['entries'][0]['tree'].clear()
        result['entries'][0]['cue'] = 'Changed'
        self.assertEqual(self.snapshot.read(), expected)

    def test_identity_is_fixed_deterministic_and_scope_separated(self):
        with RS.RecipeSnapshot(brain_id='private-brain-name', scope_hash=digest('scope'),
                               engine_config_hash=digest('engine'), language='vi') as same:
            self.assertNotEqual(same._root, self.snapshot._root)
            self.assertEqual(same.replace([entry()]), self.snapshot.replace([entry()]))
        for changed in ({'brain_id': 'other'}, {'scope_hash': digest('other')},
                        {'engine_config_hash': digest('other')}, {'language': 'en'}):
            args = dict(brain_id='private-brain-name', scope_hash=digest('scope'),
                        engine_config_hash=digest('engine'), language='vi')
            args.update(changed)
            with RS.RecipeSnapshot(**args) as other:
                self.assertNotEqual(other.replace([entry()])['snapshot_hash'],
                                    self.snapshot.read()['snapshot_hash'])

    def test_rejected_projection_leaves_previous_snapshot_intact(self):
        expected = self.snapshot.replace([entry()])
        bad_entries = ['NO_ENTRY', 'Use a method', {}, [entry()] * 2,
                       [entry(n) for n in range(4)], [dict(entry(), manifest_hash='A' * 64)],
                       [dict(entry(), verdict='proved')], [dict(entry(), surface={})],
                       [dict(entry(), root='C:/outside')], [dict(entry(), cue='\0')],
                       [dict(entry(), cue='é' * 501)], [dict(entry(), procedure='a' * 16385)],
                       [dict(entry(), evidence_summary='a' * 8193)],
                       [dict(entry(), confidence_basis='a' * 4097)],
                       [dict(entry(), procedure='Bearer abcdefghijklmnop')],
                       [dict(entry(), cue='deterministic_eval_summary')],
                       [dict(entry(), evidence_summary='"passed_count"')]]
        for identifier in ('../out', 'C:\\escape', '\\\\host\\share', 'x:ads', '\\\\?\\C:\\x', '/tmp/x'):
            bad_entries.append([dict(entry(), recipe_id=identifier)])
        for invalid in bad_entries:
            with self.subTest(invalid=repr(invalid)[:100]):
                with self.assertRaises((TypeError, ValueError)):
                    self.snapshot.replace(invalid)
                self.assertEqual(self.snapshot.read(), expected)

    def test_engineering_byte_bounds_and_empty_strings_are_literal(self):
        item = dict(entry(), cue='é' * 500, procedure='x' * 16384,
                    evidence_summary='x' * 8192, confidence_basis='x' * 4096)
        self.assertEqual(len(self.snapshot.replace([item])['entries']), 1)
        empty = dict(entry(), cue='', procedure='', evidence_summary='', confidence_basis='')
        self.assertEqual(self.snapshot.replace([empty])['entries'][0]['procedure'], '')

    def test_generated_prefix_collision_rejects_before_vendor_mutation(self):
        expected = self.snapshot.replace([entry()])
        with patch.object(RS, '_name', return_value='a' * 32):
            with patch.object(RS.Library, 'retain', side_effect=AssertionError('vendor reached')):
                with self.assertRaises(ValueError):
                    self.snapshot.replace([entry(2), entry(3)])
        self.assertEqual(self.snapshot.read(), expected)

    def test_combined_serialized_bound_rejects_escaped_control_expansion(self):
        expected = self.snapshot.replace([entry()])
        items = [dict(entry(n), procedure='\n' * 16384) for n in range(3)]
        with self.assertRaises(ValueError):
            self.snapshot.replace(items)
        self.assertEqual(self.snapshot.read(), expected)

    def test_invalid_identity_and_public_path_or_surface_are_rejected(self):
        args = dict(brain_id='brain', scope_hash=digest('scope'), engine_config_hash=digest('engine'), language='en')
        for changed in ({'brain_id': ''}, {'brain_id': 'é' * 501}, {'brain_id': '\0'},
                        {'scope_hash': '0' * 63}, {'engine_config_hash': 'A' * 64},
                        {'language': 'fr'}, {'root': 'C:/outside'}, {'surface': object()}):
            with self.subTest(changed=changed), self.assertRaises((ValueError, TypeError)):
                RS.RecipeSnapshot(**dict(args, **changed))

    def test_real_library_methods_are_used(self):
        calls = []
        patches = []
        for name in ('add', 'rebuild_index', 'tree_of', 'retain', 'forget'):
            original = getattr(RS.Library, name)
            def observed(instance, *args, _original=original, _name=name, **kwargs):
                calls.append(_name)
                return _original(instance, *args, **kwargs)
            patches.append(patch.object(RS.Library, name, observed))
        for active in patches:
            active.start()
            self.addCleanup(active.stop)
        self.snapshot.replace([entry(1), entry(2), entry(3)])
        self.snapshot.replace([entry(2)])
        self.snapshot.replace([])
        self.assertEqual(set(calls), {'add', 'rebuild_index', 'tree_of', 'retain', 'forget'})

    def test_actual_library_marker_tripwire_and_no_experience_keep_inventory(self):
        from improvement_harness2_context import GRADER_VERDICT_MARKERS
        before = self.snapshot.read()
        name = RS._name(entry())
        path = f'procedures/recipe-{name}/SKILL.md'
        for marker in GRADER_VERDICT_MARKERS:
            with self.subTest(marker=marker), self.assertRaises(ValueError):
                self.snapshot._library.add(name, {path: marker},
                                           experience={'cue': 'cue', 'lesson': 'lesson', 'evidence': 'evidence'})
        self.assertIsNone(self.snapshot._library.add(name, {path: 'plain'}, experience='NO_ENTRY'))
        self.assertIsNone(self.snapshot._library.add(name, {path: 'plain'}, experience={}))
        self.assertEqual(self.snapshot.read(), before)
        self.assertEqual(self.snapshot._library.entries(), [])

    def test_mutating_vendor_failure_poisons_and_clears_projection(self):
        self.snapshot.replace([entry()])
        original = RS.Library.add
        def broken(instance, *args, **kwargs):
            original(instance, *args, **kwargs)
            raise OSError('injected after real vendor mutation')
        with patch.object(RS.Library, 'add', broken), self.assertRaises(OSError):
            self.snapshot.replace([entry(2)])
        self.assertEqual(self.snapshot._entries, [])
        for method in (self.snapshot.read, lambda: self.snapshot.replace([])):
            with self.assertRaises(RuntimeError):
                method()

    def test_unexpected_mutation_during_vendor_read_never_publishes(self):
        self.snapshot.replace([entry()])
        index = self.snapshot._library.index
        original_index = index.read_bytes()
        original = RS.Library.tree_of
        def changed(instance, *args, **kwargs):
            result = original(instance, *args, **kwargs)
            index.write_text('unexpected index mutation', encoding='utf-8')
            return result
        try:
            with patch.object(RS.Library, 'tree_of', changed):
                with self.assertRaises(RuntimeError):
                    self.snapshot.read()
        finally:
            index.write_bytes(original_index)
        self.assertEqual(self.snapshot._entries, [])

    def test_suppressed_upstream_forget_failure_never_publishes_mixed_inventory(self):
        self.snapshot.replace([entry(1), entry(2)])
        prior_paths = self.snapshot._paths([entry(1), entry(2)])
        original = RS.shutil.rmtree
        def refuse_vendor_delete(path, *args, **kwargs):
            if kwargs.get('ignore_errors'):
                return
            return original(path, *args, **kwargs)
        try:
            with patch.object(RS.shutil, 'rmtree', refuse_vendor_delete):
                with self.assertRaises(RuntimeError):
                    self.snapshot.replace([entry(3)])
            self.assertEqual(self.snapshot._entries, [])
            with self.assertRaises(RuntimeError):
                self.snapshot.read()
            self.snapshot.close()
            self.assertFalse(self.snapshot._root.exists())
        finally:
            # Repair the fixture whitelist on RED so the test owner can clean up.
            if self.snapshot._root.exists():
                self.snapshot._allowed |= prior_paths

    def test_actual_tree_reader_refuses_non_utf8_bytes(self):
        import improvement_harness2_tree as tree
        self.snapshot.replace([entry()])
        procedure = next(self.snapshot._root.rglob('SKILL.md'))
        original = procedure.read_bytes()
        procedure.write_bytes(b'\xff')
        try:
            with self.assertRaises(UnicodeDecodeError):
                tree.read_tree(RS._SURFACE, self.snapshot._library.entry_dir(RS._name(entry())) / 'harness')
        finally:
            procedure.write_bytes(original)

    def test_allowed_file_tampering_and_unexpected_child_poison(self):
        self.snapshot.replace([entry()])
        procedure = next(self.snapshot._root.rglob('SKILL.md'))
        procedure.write_text('unexpected mutation', encoding='utf-8')
        with patch.object(RS.Library, 'add', side_effect=AssertionError('must reject before vendor')):
            with self.assertRaises(RuntimeError):
                self.snapshot.replace([entry(2)])
        with self.assertRaises(RuntimeError):
            self.snapshot.read()
        # Cleanup also refuses unexpected content until the owner repairs the fixture.
        with self.assertRaises(RuntimeError):
            self.snapshot.close()
        procedure.write_bytes(entry()['procedure'].encode('utf-8'))

    def test_unexpected_file_refuses_read_and_cleanup_without_deleting_it(self):
        unexpected = self.snapshot._root / 'unexpected.txt'
        unexpected.write_text('outside planned inventory', encoding='utf-8')
        with self.assertRaises(RuntimeError):
            self.snapshot.read()
        with self.assertRaises(RuntimeError):
            self.snapshot.close()
        self.assertTrue(unexpected.exists())
        unexpected.unlink()

    def test_private_permissions_precede_vendor_plaintext(self):
        original = RS._private_directory
        seen = []
        def permissions(path):
            self.assertFalse(any(path.iterdir()))
            seen.append(path)
            return original(path)
        with patch.object(RS, '_private_directory', permissions):
            with RS.RecipeSnapshot(brain_id='permissions', scope_hash=digest('scope'),
                                   engine_config_hash=digest('engine'), language='en') as owner:
                owner.replace([entry()])
                if os.name != 'nt':
                    self.assertEqual(owner._root.stat().st_mode & 0o777, 0o700)
        self.assertEqual(len(seen), 1)
        denied_roots = []
        def denied(path):
            self.assertFalse(any(path.iterdir()))
            denied_roots.append(path)
            raise OSError('permissions denied')
        with patch.object(RS, '_private_directory', denied):
            with self.assertRaises(OSError):
                RS.RecipeSnapshot(brain_id='permissions', scope_hash=digest('scope'),
                                  engine_config_hash=digest('engine'), language='en')
        self.assertEqual(len(denied_roots), 1)
        self.assertFalse(denied_roots[0].exists())

    def test_replaced_root_identity_refuses_cleanup_and_keeps_sentinel(self):
        root = self.snapshot._root
        moved = root.with_name(root.name + '-saved')
        root.rename(moved)
        root.mkdir()
        sentinel = root / 'sentinel.txt'
        sentinel.write_text('keep', encoding='utf-8')
        try:
            with self.assertRaises(RuntimeError):
                self.snapshot.read()
            with self.assertRaises(RuntimeError):
                self.snapshot.close()
            self.assertEqual(sentinel.read_text(encoding='utf-8'), 'keep')
        finally:
            sentinel.unlink()
            root.rmdir()
            moved.rename(root)

    def test_cleanup_failure_is_honest_and_retryable(self):
        self.snapshot.replace([entry()])
        owned = self.snapshot._root
        with patch.object(RS.shutil, 'rmtree', side_effect=OSError('cleanup denied')):
            with self.assertRaises(OSError):
                self.snapshot.close()
        self.assertTrue(owned.exists())
        with self.assertRaises(RuntimeError):
            self.snapshot.read()
        self.snapshot.close()
        self.assertFalse(owned.exists())
        self.snapshot.close()

    def test_partial_cleanup_failure_keeps_safe_remainder_retryable(self):
        self.snapshot.replace([entry()])
        index = self.snapshot._library.index
        content = index.read_bytes()
        def partially_removed(root):
            self.assertEqual(root, self.snapshot._root)
            index.unlink()
            raise OSError('injected partial cleanup')
        try:
            with patch.object(RS.shutil, 'rmtree', partially_removed):
                with self.assertRaises(OSError):
                    self.snapshot.close()
            with self.assertRaises(RuntimeError):
                self.snapshot.read()
            self.snapshot.close()
            self.assertFalse(self.snapshot._root.exists())
        finally:
            if self.snapshot._root.exists() and not index.exists():
                index.write_bytes(content)

    def test_close_serializes_with_blocked_checked_vendor_operation(self):
        entered, release, closed = threading.Event(), threading.Event(), threading.Event()
        results, failures = [], []
        original = RS.Library.add
        def blocked(instance, *args, **kwargs):
            entered.set()
            if not release.wait(15):
                raise AssertionError('test release not received')
            return original(instance, *args, **kwargs)
        def replace():
            try:
                results.append(self.snapshot.replace([entry()]))
            except BaseException as error:
                failures.append(error)
        def close():
            try:
                self.snapshot.close()
                closed.set()
            except BaseException as error:
                failures.append(error)
        with patch.object(RS.Library, 'add', blocked):
            writer = threading.Thread(target=replace)
            closer = threading.Thread(target=close)
            writer.start()
            try:
                self.assertTrue(entered.wait(15))
                closer.start()
                self.assertFalse(closed.wait(0.1))
            finally:
                release.set()
                writer.join(20)
                if closer.ident:
                    closer.join(20)
        self.assertFalse(writer.is_alive())
        self.assertFalse(closer.is_alive())
        self.assertEqual(failures, [])
        self.assertEqual(len(results), 1)
        self.assertTrue(closed.is_set())
        self.assertFalse(self.snapshot._root.exists())
        for method in (self.snapshot.read, lambda: self.snapshot.replace([])):
            with self.assertRaises(RuntimeError):
                method()

    def _link_escape(self, junction):
        self.snapshot.replace([entry()])
        with tempfile.TemporaryDirectory(prefix='outside-') as outside:
            sentinel = Path(outside) / 'sentinel.txt'
            sentinel.write_text('keep', encoding='utf-8')
            link = self.snapshot._root / 'escape'
            if junction:
                result = subprocess.run(['cmd', '/c', 'mklink', '/J', str(link), outside],
                                        capture_output=True, text=True, check=False)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            else:
                link.symlink_to(outside, target_is_directory=True)
            try:
                with patch.object(RS.Library, 'retain', side_effect=AssertionError('vendor reached')):
                    with self.assertRaises(RuntimeError):
                        self.snapshot.replace([])
                with self.assertRaises(RuntimeError):
                    self.snapshot.close()
                self.assertEqual(sentinel.read_text(encoding='utf-8'), 'keep')
            finally:
                if junction:
                    link.rmdir()
                else:
                    link.unlink()

    @unittest.skipUnless(os.name == 'nt', 'Windows junction coverage unavailable on POSIX')
    def test_actual_windows_junction_escape_is_rejected(self):
        self._link_escape(True)

    @unittest.skipIf(os.name == 'nt', 'POSIX symlink coverage unavailable on Windows')
    def test_actual_posix_symlink_escape_is_rejected(self):
        self._link_escape(False)

    def test_extracted_definitions_match_raw_and_ast_provenance(self):
        manifest = json.loads((ROOT / 'third_party/harness2/LIBRARY-PROVENANCE.json').read_text(encoding='utf-8'))
        for module in manifest['modules']:
            target = (ROOT / module['target']).read_bytes()
            self.assertEqual(hashlib.sha256(target).hexdigest(), module['target_sha256'])
            parsed = ast.parse(target.decode('utf-8'))
            lines = target.splitlines(keepends=True)
            nodes = {node.name: node for node in parsed.body if isinstance(node, (ast.FunctionDef, ast.ClassDef))}
            nodes.update({node.targets[0].id: node for node in parsed.body
                          if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name)})
            nodes.update({node.target.id: node for node in parsed.body
                          if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name)})
            for definition in module['definitions']:
                node = nodes[definition['name']]
                start = min([node.lineno] + [d.lineno for d in getattr(node, 'decorator_list', [])])
                raw = b''.join(lines[start - 1:node.end_lineno])
                self.assertEqual(hashlib.sha256(raw).hexdigest(), definition['adapted_raw_sha256'])
                tree_hash = digest(ast.dump(node, include_attributes=False))
                self.assertEqual(tree_hash, definition['adapted_ast_sha256'])
                if not definition['boundary_diffs']:
                    self.assertEqual(definition['source_raw_sha256'], definition['adapted_raw_sha256'])
                    self.assertEqual(definition['source_ast_sha256'], tree_hash)
        diffs = [diff for module in manifest['modules'] for definition in module['definitions']
                 for diff in definition['boundary_diffs']]
        self.assertEqual(len(diffs), 3)


if __name__ == '__main__':
    unittest.main()
