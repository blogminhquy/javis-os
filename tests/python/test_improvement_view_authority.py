"""Disposable actual file/owner authority integration for immutable skill views."""
from _paths import ROOT, SERVER  # noqa: F401

import json
import os
import stat
import subprocess
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

import improvement_assets as IA
import improvement_store as IM
from improvement_trial_file_sources import _acl_hash
from resonance_store import Principal
from test_improvement_experiment_execution import _REAL_RUN, _REAL_POPEN
import test_improvement_view_sources as sources


def restore_native_dacl(path, original_hash):
    """Snapshot/restore only this owned temporary file's DACL, without /restore privilege."""
    import ctypes
    from ctypes import wintypes
    api = ctypes.WinDLL('advapi32', use_last_error=True)
    get = api.GetFileSecurityW
    get.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.LPVOID, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
    get.restype = wintypes.BOOL
    size = wintypes.DWORD()
    get(str(path), 7, None, 0, ctypes.byref(size))
    if not 1 <= size.value <= 1048576:
        raise OSError('Cannot snapshot owned temporary DACL')
    descriptor = ctypes.create_string_buffer(size.value)
    if not get(str(path), 7, descriptor, size.value, ctypes.byref(size)):
        raise ctypes.WinError(ctypes.get_last_error())
    control, revision = wintypes.WORD(), wintypes.DWORD()
    read_control = api.GetSecurityDescriptorControl
    read_control.argtypes = [wintypes.LPVOID, ctypes.POINTER(wintypes.WORD), ctypes.POINTER(wintypes.DWORD)]
    read_control.restype = wintypes.BOOL
    if not read_control(descriptor, ctypes.byref(control), ctypes.byref(revision)):
        raise ctypes.WinError(ctypes.get_last_error())
    flags = 4 | (0x80000000 if control.value & 0x1000 else 0x20000000)
    put = api.SetFileSecurityW
    put.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.LPVOID]
    put.restype = wintypes.BOOL

    def restore():
        if not put(str(path), flags, descriptor):
            raise ctypes.WinError(ctypes.get_last_error())
        if _acl_hash(path) != original_hash:
            raise AssertionError('Owned temporary DACL did not restore exactly')

    return restore


class FileAuthorityTests(sources.SourceFixture, unittest.IsolatedAsyncioTestCase):
    async def test_native_file_permissions_change_invalidates_frozen_view(self):
        subject = self.views_service()
        self.freeze(subject)
        path = self.f.f.f.skill
        before = path.read_bytes()
        if os.name == 'nt':
            original_acl = _acl_hash(path)
            self.addCleanup(restore_native_dacl(path, original_acl))
            subprocess.run(['icacls', str(path), '/grant', '*S-1-5-32-545:(R)'], check=True, capture_output=True)
            self.assertNotEqual(_acl_hash(path), original_acl, 'Actual Windows DACL did not change')
        else:
            mode = stat.S_IMODE(path.stat().st_mode)
            self.addCleanup(path.chmod, mode)
            path.chmod(mode & ~stat.S_IWUSR)
        self.assertEqual(path.read_bytes(), before)
        with self.assertRaises((IM.ConflictError, PermissionError, IA.SourceError)):
            subject.load_current(self.owner, self.comparison['id'], 'candidate')

    async def test_parent_directory_replacement_is_detected_even_with_same_file_inode_and_bytes(self):
        subject = self.views_service()
        self.freeze(subject)
        path, root = self.f.f.f.skill, self.f.f.f.root.resolve()
        moved = root / 'moved-original-skill'
        self.assertTrue(path.parent.resolve().is_relative_to(root))
        self.assertTrue(moved.absolute().is_relative_to(root))
        before = path.stat().st_ino
        path.parent.rename(moved)
        path.parent.mkdir()
        (moved / path.name).rename(path)
        self.assertEqual(path.stat().st_ino, before)
        with self.assertRaises((IM.ConflictError, PermissionError)):
            subject.load_current(self.owner, self.comparison['id'], 'candidate')

    async def test_actual_directory_symlink_or_windows_junction_cannot_resolve_a_view(self):
        subject = self.views_service()
        self.freeze(subject)
        directory, root = self.f.f.f.skill.parent, self.f.f.f.root.resolve()
        moved = root / 'linked-original-skill'
        self.assertTrue(directory.resolve().is_relative_to(root))
        self.assertTrue(moved.absolute().is_relative_to(root))
        directory.rename(moved)

        def restore():
            self.assertTrue(moved.resolve().is_relative_to(root))
            if directory.is_symlink():
                directory.unlink()
            elif os.name == 'nt' and directory.is_junction():
                os.rmdir(directory)
            self.assertFalse(directory.exists(), 'Unexpected real directory must not be removed')
            moved.rename(directory)

        self.addCleanup(restore)
        if os.name == 'nt':
            with patch.object(subprocess, 'Popen', _REAL_POPEN):
                _REAL_RUN(['cmd.exe', '/c', 'mklink', '/J', str(directory), str(moved)], check=True, capture_output=True)
            self.assertTrue(directory.is_junction())
        else:
            directory.symlink_to(moved, target_is_directory=True)
            self.assertTrue(directory.is_symlink())
        with self.assertRaises((IM.ConflictError, PermissionError, IA.SourceError)):
            subject.load_current(self.owner, self.comparison['id'], 'candidate')

    async def test_case_distinct_or_case_alias_brain_cannot_read_another_brains_views(self):
        subject = self.views_service()
        self.freeze(subject)
        brain = Path(self.owner.brain_id)
        other = brain.with_name('Brain')
        if os.name != 'nt':
            other.mkdir()
            other_skill = other / 'skills' / 'report' / 'SKILL.md'
            other_skill.parent.mkdir(parents=True)
            other_skill.write_bytes(self.f.f.f.skill.read_bytes())
            self.assertNotEqual(other.stat().st_ino, brain.stat().st_ino)
        foreign = Principal('owner', 'owner', str(other))
        with patch.object(self.assets.blobs, 'read', side_effect=AssertionError('Foreign brain cannot decrypt')):
            self.assertIsNone(subject.read_existing(foreign, self.comparison['id']))
            with self.assertRaises(PermissionError):
                subject.load_current(foreign, self.comparison['id'], 'candidate')

    def deny_during_binding_write(self, change):
        subject, counts, generation = self.views_service(), self.counts(), self.generation()
        write, changed = self.assets.blobs.write, False

        def mutate(brain, raw):
            nonlocal changed
            digest = write(brain, raw)
            value = json.loads(raw)
            if value.get('evidence_class') == 'technical' and 'views' in value and not changed:
                changed = True
                change()
            return digest

        with patch.object(self.assets.blobs, 'write', side_effect=mutate), \
                self.assertRaises((IM.ConflictError, PermissionError, IA.SourceError)):
            self.freeze(subject, generation=generation)
        self.assertTrue(changed)
        self.assertEqual(self.counts(), counts)
        self.assertEqual(self.generation(), generation)

    async def test_revocation_during_binding_write_leaves_no_pair_or_new_call(self):
        self.deny_during_binding_write(lambda: self.host.revoke(self.owner, 'association-experiment',
            expected_generation=1, event_key='views-revoke-during-binding-write'))

    async def test_disabling_canonical_source_during_binding_write_leaves_no_pair(self):
        self.deny_during_binding_write(lambda: (Path(self.owner.brain_id) / 'skills' / '.disabled' / 'report').mkdir(parents=True))

    async def test_protected_owner_source_change_during_manifest_read_is_rejected(self):
        subject = self.views_service()
        self.freeze(subject)
        digest = subject.read_existing(self.owner, self.comparison['id'])['views']['baseline']['manifest_hash']
        read, changed = self.assets.blobs.read, False

        def mutate(brain, reference):
            nonlocal changed
            raw = read(brain, reference)
            if reference == digest and not changed:
                changed = True
                self.f.f.f.protected.write_bytes(b'Changed actual owner instructions during view read.\n')
            return raw

        with patch.object(self.assets.blobs, 'read', side_effect=mutate), self.assertRaises((IM.ConflictError, PermissionError)):
            subject.load_current(self.owner, self.comparison['id'], 'candidate')
        self.assertTrue(changed)

    async def test_actual_existing_legacy_trial_link_prevents_retrospective_view_binding(self):
        from improvement_claude import ClaudeTrialAdapter
        from improvement_experiment_admission import ExperimentAdmission
        from improvement_experiment_protocol import matrix_cell
        matrix = json.loads(self.assets.blobs.read(self.owner.brain_id, self.comparison['matrix_blob_hash']))
        position = next(index for index in range(self.comparison['cell_count']) if matrix_cell(matrix, index)['variant'] == 'baseline')
        with patch.object(ClaudeTrialAdapter, 'verify', return_value={'supported': True, 'capability_hash': 'c' * 64}):
            admitted = ExperimentAdmission(self.f.plans).admit(self.owner, self.comparison['experiment_id'], self.comparison['id'],
                position, expected_generation=self.generation(), event_key='views-actual-legacy-baseline-slot')
        with closing(self.assets.store._conn()) as connection:
            self.assertIsNotNone(connection.execute('SELECT 1 FROM improvement_experiment_trial_links WHERE trial_id=?',
                (admitted.trial_id,)).fetchone())
        subject, counts = self.views_service(), self.counts()
        with patch.object(self.assets.blobs, 'read', side_effect=AssertionError('Legacy cell must deny before decryption')), \
                self.assertRaisesRegex(IM.ConflictError, 'runtime_already_started'):
            self.freeze(subject)
        self.assertEqual(self.counts(), counts)


class MeaningFixture(sources.SourceFixture):
    semantic_verdict = 'owner_required'

    async def service(self):
        return await sources.SourceFixture.service(self, verdict=self.semantic_verdict)


class OwnerMeaningTests(MeaningFixture, unittest.IsolatedAsyncioTestCase):
    async def test_unresolved_meaning_denies_until_actual_exact_synthetic_owner_event(self):
        subject, counts = self.views_service(), self.counts()
        with self.assertRaisesRegex(PermissionError, 'owner_required'):
            self.freeze(subject)
        self.assertEqual(self.counts(), counts)
        evidence = self.semantic_subject.current_evidence(self.owner, self.proposal['id'])
        key = 'views-synthetic-exact-owner-meaning'
        self.semantic_subject.arbitrate(self.owner, self.proposal['id'], evidence['receipt_id'], verdict='pass',
            reason='Synthetic disposable owner meaning fixture; no business or live acceptance.',
            expected_binding_hash=evidence['binding_hash'], expected_generation=self.generation(), event_key=key)
        self.freeze(subject)
        resolved = subject.load_current(self.owner, self.comparison['id'], 'candidate')
        self.assertEqual(resolved.manifest['semantic']['owner_event_key'], key)
        current = self.semantic_subject.current_evidence(self.owner, self.proposal['id'])
        self.assertEqual((current['assessment']['verdict'], current['verdict']), ('owner_required', 'unknown'))
        self.assertEqual(self.counts()[-1], counts[-1])


class NegativeMeaningTests(MeaningFixture, unittest.IsolatedAsyncioTestCase):
    semantic_verdict = 'fail'

    async def test_actual_negative_model_assessment_cannot_be_erased_by_owner_pass(self):
        subject, counts = self.views_service(), self.counts()
        evidence = self.semantic_subject.current_evidence(self.owner, self.proposal['id'])
        self.semantic_subject.arbitrate(self.owner, self.proposal['id'], evidence['receipt_id'], verdict='pass',
            reason='Synthetic disagreement cannot erase a negative model assessment.', expected_binding_hash=evidence['binding_hash'],
            expected_generation=self.generation(), event_key='views-owner-cannot-erase-model-negative')
        with self.assertRaisesRegex(PermissionError, 'semantic_rejected'):
            self.freeze(subject)
        self.assertEqual(self.counts(), counts)


class ExactBytesTests(sources.SourceFixture, unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        write = Path.write_bytes

        def initial(path, raw):
            if path.name == 'SKILL.md' and raw.startswith(b'---\nname: Owner report\n'):
                raw = raw.replace(b'\n', b'\r\n')
            return write(path, raw)

        with patch.object(Path, 'write_bytes', initial):
            sources.SourceFixture.setUp(self)

    async def test_actual_crlf_and_protected_frontmatter_bytes_survive_the_view_pipeline(self):
        subject = self.views_service()
        self.freeze(subject)
        baseline = subject.load_current(self.owner, self.comparison['id'], 'baseline')
        candidate = subject.load_current(self.owner, self.comparison['id'], 'candidate')
        self.assertTrue(baseline.content.startswith(b'---\r\n'))
        start = baseline.content.index(b'Retain owner rules.')
        self.assertEqual(baseline.content[:start], candidate.content[:start])
        self.assertEqual(baseline.content, self.f.f.f.skill.read_bytes())


class PlainBomBytesTests(sources.SourceFixture, unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        write = Path.write_bytes

        def initial(path, raw):
            if path.name == 'SKILL.md' and raw.startswith(b'---\nname: Owner report\n'):
                raw = b'\xef\xbb\xbfOwner report description.\r\nRetain owner rules.\r\n'
            return write(path, raw)

        with patch.object(Path, 'write_bytes', initial):
            sources.SourceFixture.setUp(self)

    async def test_supported_plain_bom_crlf_keeps_exact_implicit_description_prefix(self):
        subject = self.views_service()
        self.freeze(subject)
        baseline = subject.load_current(self.owner, self.comparison['id'], 'baseline')
        candidate = subject.load_current(self.owner, self.comparison['id'], 'candidate')
        self.assertTrue(baseline.content.startswith(b'\xef\xbb\xbfOwner report description.\r\n'))
        start = baseline.content.index(b'Retain owner rules.')
        self.assertEqual(baseline.content[:start], candidate.content[:start])
        self.assertEqual(baseline.content, self.f.f.f.skill.read_bytes())


class DependencyFixture(sources.SourceFixture):
    dependency_ref = 'references/checks.md'
    grant_dependency = True

    def setUp(self):
        import test_improvement_host_snapshots as host
        from improvement_trial_context import ContextSource, capture_context
        capture = host.capture_source

        def with_reference(root, kind, slug, **kwargs):
            if kind == 'skill' and slug == 'report':
                path = Path(root) / 'skills/report/SKILL.md'
                marker = ('Use ' + self.dependency_ref + '\n').encode()
                raw = path.read_bytes()
                if marker not in raw:
                    helper = path.parent / self.dependency_ref
                    helper.parent.mkdir(parents=True)
                    helper.write_bytes(b'Declared helper data; never execute this fixture.\n')
                    path.write_bytes(raw + marker)
            return capture(root, kind, slug, **kwargs)

        def context(fixture, principal, surface, targets):
            selected = [ContextSource('owner', Path(principal.brain_id), 'owner.md')]
            if self.grant_dependency:
                selected.append(ContextSource('declared-checks', Path(principal.brain_id), 'skills/report/' + self.dependency_ref))
            return capture_context(selected, surface=surface, complete_plan=True)

        self.enterContext(patch.object(host, 'capture_source', side_effect=with_reference))
        self.enterContext(patch.object(host.HostSnapshotTests, 'context_capture', context))
        sources.SourceFixture.setUp(self)

    def body_patch(self, replacement=None):
        if replacement is None:
            replacement = 'Retain owner rules.\nCheck the subtotal.\nUse ' + self.dependency_ref + '\n'
        return sources.SourceFixture.body_patch(self, replacement)


class GrantedDependencyTests(DependencyFixture, unittest.IsolatedAsyncioTestCase):
    async def test_actual_granted_markdown_dependency_is_pinned_and_change_denies_resolution(self):
        subject = self.views_service()
        self.freeze(subject)
        resolved = subject.load_current(self.owner, self.comparison['id'], 'candidate')
        evidence = self.semantic_subject.current_evidence(self.owner, self.proposal['id'])
        self.assertEqual(evidence['dependencies']['verdict'], 'pass')
        self.assertEqual(resolved.manifest['semantic']['dependency_hash'], IM._hash(evidence['dependencies']))
        self.assertEqual(len(resolved.manifest['assets']), 1)
        (self.f.f.f.skill.parent / self.dependency_ref).write_bytes(b'Unreviewed dependency data change.\n')
        with self.assertRaises((IM.ConflictError, PermissionError)):
            subject.load_current(self.owner, self.comparison['id'], 'candidate')


class UngrantedDependencyTests(DependencyFixture, unittest.IsolatedAsyncioTestCase):
    grant_dependency = False

    async def test_existing_ungranted_dependency_is_not_followed_or_accepted(self):
        subject, counts = self.views_service(), self.counts()
        helper, read = self.f.f.f.skill.parent / self.dependency_ref, Path.read_bytes

        def guarded(path):
            if path == helper:
                raise AssertionError('View resolver cannot follow an ungranted dependency')
            return read(path)

        with patch.object(Path, 'read_bytes', guarded), self.assertRaisesRegex(PermissionError, 'dependencies_unresolved'):
            self.freeze(subject)
        self.assertEqual(self.counts(), counts)


class ExecutableDependencyTests(DependencyFixture, unittest.IsolatedAsyncioTestCase):
    dependency_ref = 'helpers/checks.py'

    async def test_declared_executable_reference_still_blocks_a_body_only_probe(self):
        subject, counts = self.views_service(), self.counts()
        with self.assertRaisesRegex(PermissionError, 'dependencies_unresolved'):
            self.freeze(subject)
        self.assertEqual(self.counts(), counts)


if __name__ == '__main__':
    unittest.main()
