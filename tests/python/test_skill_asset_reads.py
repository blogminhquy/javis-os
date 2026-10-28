"""Ordinary hub/lazy reads authenticate one stable source without edit authority."""
from _paths import ROOT, SERVER  # noqa: F401

import asyncio
import hashlib
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

_STATE = tempfile.TemporaryDirectory(prefix='skill-read-import-')
os.environ['JAVIS_STATE_DIR'] = _STATE.name
os.environ['BRAIN_PATH'] = str(Path(_STATE.name) / 'brain')
os.environ['BRAINS_DIR'] = str(Path(_STATE.name) / 'brains')

import skill_router
import skill_usage
import mcp_hub
from capability_registry import CapabilityRegistry
from lazy_skill_runtime import LazySkillSource


class SkillAssetReadTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='skill-asset-read-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.slug = 'reconcile'

    def write(self, base='skills', body=b'COUNT_ALL_ROWS', extra=b''):
        path = self.root / base / self.slug / 'SKILL.md'
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b'---\r\nname: reconcile\r\ndescription: Reconcile authorized amount rows.\r\n'
                         + extra + b'---\r\n' + body)
        return path

    def lazy(self):
        registry = CapabilityRegistry(self.root / 'state')
        self.addCleanup(registry.close)
        return LazySkillSource(registry)

    def handler(self):
        _, routes = mcp_hub._builtin_tools('auto', str(self.root))
        return routes['javis_use_skill']['call']

    def read_mutation(self, source, mutation):
        """Change the real source after bytes arrive but before its final stat."""
        original = os.fdopen

        class ObservedRead:
            def __init__(self, inner): self.inner = inner
            def __enter__(self): return self
            def __exit__(self, *args): return self.inner.__exit__(*args)
            def fileno(self): return self.inner.fileno()
            def read(self, *args):
                raw = self.inner.read(*args)
                mutation()
                return raw

        def opening(descriptor, *args, **kwargs):
            handle = original(descriptor, *args, **kwargs)
            mode = args[0] if args else kwargs.get('mode', 'r')
            return ObservedRead(handle) if mode == 'rb' else handle

        return patch.object(os, 'fdopen', opening)

    def test_precedence_and_raw_byte_receipt_preserve_crlf(self):
        for base, body in (('.agents', b'LEGACY'), ('.claude/skills', b'MIRROR'), ('skills', b'CANONICAL')):
            path = self.write(base, body)
            raw = path.read_bytes()
            asset = skill_router.read_skill_asset(self.root, self.slug)
            self.assertEqual(asset.content, raw)
            self.assertEqual(asset.content_hash, hashlib.sha256(raw).hexdigest())
            self.assertEqual(asset.relative_path, path.relative_to(self.root).as_posix())
            self.assertEqual(asset.frontmatter_hash, skill_router.read_frontmatter_only(path)[1])
            self.assertNotIn('\r', asset.text)
            path.write_bytes(b'OWNER_EDIT_AFTER_RETURN')
            self.assertEqual(asset.content, raw)

    def test_skill_with_its_own_files_names_its_folder(self):
        # 0.370.0: SKILL.md alone gets no extra line; once the folder holds scripts/ or rules/, the hub says
        # where the folder is, as Claude Code's own loader does, so `scripts/setup.sh` can be found.
        path = self.write()
        call = self.handler()
        alone = asyncio.run(call({'name': self.slug}))
        self.assertTrue(alone.startswith('---'), alone[:80])
        (path.parent / 'scripts').mkdir()
        (path.parent / 'scripts' / 'setup.sh').write_text('echo 1\n')
        out = asyncio.run(call({'name': self.slug}))
        self.assertTrue(out.startswith(f'Base directory for this skill: {path.parent.resolve()}\n\n'), out[:200])
        self.assertTrue(out.endswith('COUNT_ALL_ROWS'))

    def test_ordinary_learning_locked_source_is_readable_without_edit_permission(self):
        self.write(extra=b'learn_lock: true\r\nmanaged_by: system\r\n')
        self.assertIn('COUNT_ALL_ROWS', skill_router.read_skill_asset(self.root, self.slug).text)

    def test_disabled_during_read_refuses_bytes_and_stale_mirror(self):
        source = self.write()
        self.write('.claude/skills', b'STALE_MIRROR')
        def disable(): self.write('skills/.disabled', b'OWNER_DISABLED')
        with self.read_mutation(source, disable):
            self.assertIsNone(skill_router.read_skill_asset(self.root, self.slug))

    def test_same_size_rewrite_during_read_is_refused(self):
        source = self.write(body=b'ORIGINAL_BODY')
        raw = source.read_bytes()
        before = source.stat()
        def rewrite():
            source.write_bytes(raw.replace(b'ORIGINAL_BODY', b'MODIFIED_BODY'))
            os.utime(source, ns=(before.st_atime_ns, before.st_mtime_ns + 10_000_000))
        with self.read_mutation(source, rewrite):
            self.assertIsNone(skill_router.read_skill_asset(self.root, self.slug))

    def test_exact_bound_and_oversized_source_never_promotes_mirror(self):
        path = self.write()
        maximum = 1024 * 1024
        raw = path.read_bytes()
        path.write_bytes(raw + b'x' * (maximum - len(raw)))
        self.assertEqual(len(skill_router.read_skill_asset(self.root, self.slug).content), maximum)
        path.write_bytes(path.read_bytes() + b'x')
        self.write('.claude/skills', b'STALE_MIRROR')
        self.assertIsNone(skill_router.read_skill_asset(self.root, self.slug))
        self.assertIsNone(skill_router.read_skill_asset(self.root, '../reconcile'))

    def test_linked_source_stays_inside_brain(self):
        path = self.write()
        inside = self.root / 'shared.md'
        inside.write_bytes(path.read_bytes())
        outside = self.root.parent / (self.root.name + '-outside.md')
        self.addCleanup(lambda: outside.unlink(missing_ok=True))
        outside.write_bytes(b'PRIVATE_OUTSIDE_MARKER')
        path.unlink()
        try:
            path.symlink_to(inside)
        except OSError as error:
            self.skipTest('OS cannot create this symlink fixture: ' + str(error))
        self.assertIn('COUNT_ALL_ROWS', skill_router.read_skill_asset(self.root, self.slug).text)
        path.unlink()
        path.symlink_to(outside)
        self.assertIsNone(skill_router.read_skill_asset(self.root, self.slug))

    def test_warm_lazy_refuses_frontmatter_changed_after_scoring(self):
        path = self.write()
        source = self.lazy()
        self.assertEqual(source.resolve(self.root, self.slug).action, 'load')
        search = source.registry.search
        def changed(*args, **kwargs):
            rows = search(*args, **kwargs)
            path.write_bytes(path.read_bytes().replace(b'Reconcile authorized amount rows.', b'Create a document from a brief.'))
            return rows
        with patch.object(source.registry, 'search', changed):
            result = source.resolve(self.root, self.slug)
        self.assertEqual(result.action, 'fallback')
        self.assertEqual(result.reason, 'source_manifest_changed')
        self.assertIsNone(result.context_item)

    @unittest.skipUnless(os.name == 'nt', 'Windows directory junction fixture')
    def test_windows_directory_junction_cannot_read_outside_brain(self):
        outside = tempfile.TemporaryDirectory(prefix='skill-outside-junction-')
        self.addCleanup(outside.cleanup)
        target = Path(outside.name)
        (target/'SKILL.md').write_bytes(b'PRIVATE_OUTSIDE_MARKER')
        (self.root/'skills').mkdir()
        linked = self.root/'skills'/self.slug
        result = subprocess.run(['cmd', '/c', 'mklink', '/J', str(linked), str(target)],
                                capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.addCleanup(linked.rmdir)
        self.assertIsNone(skill_router.read_skill_asset(self.root, self.slug))

    @unittest.skipUnless(os.name == 'nt', 'Windows directory junction fixture')
    def test_windows_inside_directory_junction_remains_readable(self):
        target = self.root/'shared'
        target.mkdir()
        (target/'SKILL.md').write_bytes(b'AUTHORIZED_INSIDE_LINK')
        (self.root/'skills').mkdir()
        linked = self.root/'skills'/self.slug
        result = subprocess.run(['cmd', '/c', 'mklink', '/J', str(linked), str(target)],
                                capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.addCleanup(linked.rmdir)
        asset = skill_router.read_skill_asset(self.root, self.slug)
        self.assertEqual(asset.content, b'AUTHORIZED_INSIDE_LINK')
        self.assertEqual(asset.relative_path, 'shared/SKILL.md')

    @unittest.skipUnless(os.name == 'nt', 'Windows handle verification')
    def test_failed_descriptor_verification_closes_before_buffered_read(self):
        import skill_asset_io
        self.write()
        descriptors = []
        def unavailable(descriptor):
            descriptors.append(descriptor)
            raise OSError('Synthetic handle path query unavailable')
        with patch.object(skill_asset_io, '_windows_descriptor_path', unavailable), \
                patch.object(os, 'fdopen', side_effect=AssertionError('Unverified descriptor cannot read')):
            self.assertIsNone(skill_router.read_skill_asset(self.root, self.slug))
        self.assertEqual(len(descriptors), 1)
        with self.assertRaises(OSError):
            os.fstat(descriptors[0])

    @unittest.skipUnless(os.name == 'posix', 'POSIX nonblocking FIFO fixture')
    def test_swapped_fifo_is_refused_before_read_without_hanging(self):
        completed = subprocess.run([sys.executable, str(Path(__file__).resolve()), '--fifo-probe'],
                                   capture_output=True, text=True, timeout=8)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn('FIFO_REFUSED_BEFORE_READ', completed.stdout)

    def test_transient_parent_link_refuses_external_opened_descriptor(self):
        path = self.write()
        outside = tempfile.TemporaryDirectory(prefix='transient-skill-outside-')
        self.addCleanup(outside.cleanup)
        target = Path(outside.name)
        (target/'SKILL.md').write_bytes(b'PRIVATE_TRANSIENT_OUTSIDE_MARKER')
        held = self.root/'held'
        parent = path.parent
        original_resolve, original_stat = Path.resolve, Path.stat
        state = {'active': False, 'swapped': False, 'stats': 0}

        def restore():
            if state['active']:
                os.rmdir(parent) if os.name == 'nt' else parent.unlink()
                held.rename(parent)
                state['active'] = False

        self.addCleanup(restore)

        def resolved(candidate, *args, **kwargs):
            result = original_resolve(candidate, *args, **kwargs)
            if candidate == path and not state['swapped']:
                parent.rename(held)
                if os.name == 'nt':
                    result_link = subprocess.run(['cmd', '/c', 'mklink', '/J', str(parent), str(target)],
                                                 capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
                    if result_link.returncode:
                        held.rename(parent)
                        self.fail('Could not create real transient junction fixture')
                else:
                    parent.symlink_to(target, target_is_directory=True)
                state.update(active=True, swapped=True)
            return result

        def observed_stat(candidate, *args, **kwargs):
            result = original_stat(candidate, *args, **kwargs)
            if candidate == path and state['active']:
                state['stats'] += 1
                if state['stats'] == 2:
                    restore()
            return result

        with patch.object(Path, 'resolve', resolved), patch.object(Path, 'stat', observed_stat):
            result = skill_router.read_skill_asset(self.root, self.slug)
        self.assertTrue(state['swapped'], 'The actual parent must change after initial resolve')
        self.assertIsNone(result, 'An opened external descriptor cannot become an inside skill receipt')

    def test_hub_read_disabled_mid_load_does_not_count_a_use(self):
        path = self.write()
        handler = self.handler()
        with self.read_mutation(path, lambda: self.write('skills/.disabled', b'OWNER_DISABLED')):
            result = asyncio.run(handler({'name': self.slug}))
        self.assertTrue((self.root/'skills/.disabled/reconcile/SKILL.md').is_file())
        self.assertTrue(result.startswith('ERROR'), result)
        self.assertNotIn('COUNT_ALL_ROWS', result)
        self.assertEqual(skill_usage.read_usage(self.root), {})

    def test_real_hub_and_lazy_share_reader_and_exact_receipt(self):
        path = self.write(body='Đối soát mọi dòng.'.encode())
        source = self.lazy()
        handler = self.handler()
        actual = skill_router.read_skill_asset
        with patch.object(skill_router, 'read_skill_asset', wraps=actual) as reads:
            result = source.resolve(self.root, self.slug)
            hub = asyncio.run(handler({'name': self.slug}))
        self.assertEqual(reads.call_count, 2)
        self.assertIn('Đối soát mọi dòng.', hub)
        self.assertIn('Đối soát mọi dòng.', result.context_item.content)
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        self.assertEqual(result.context_item.source_ref, 'file:skills/reconcile/SKILL.md:' + digest)
        self.assertEqual(result.context_item.metadata['policy_version'], 'lazy-skill-source-v2')
        self.assertEqual(skill_usage.read_usage(self.root)[self.slug]['use_count'], 1)


def fifo_probe():
    with tempfile.TemporaryDirectory(prefix='skill-fifo-probe-') as name:
        root = Path(name).resolve()
        source = root/'skills/reconcile/SKILL.md'
        source.parent.mkdir(parents=True)
        source.write_bytes(b'AUTHORIZED_BEFORE_FIFO_SWAP')
        stat_original, resolve_original = Path.stat, Path.resolve
        state = {'resolved': False, 'swapped': False}
        def resolved(path, *args, **kwargs):
            result = resolve_original(path, *args, **kwargs)
            if path == source:
                state['resolved'] = True
            return result
        def observed_stat(path, *args, **kwargs):
            info = stat_original(path, *args, **kwargs)
            if path == source and state['resolved'] and not state['swapped']:
                source.unlink()
                os.mkfifo(source)
                state['swapped'] = True
            return info
        with patch.object(Path, 'resolve', resolved), patch.object(Path, 'stat', observed_stat), \
                patch.object(os, 'fdopen', side_effect=AssertionError('FIFO cannot reach a buffered read')):
            result = skill_router.read_skill_asset(root, 'reconcile')
        assert state['swapped'] and result is None
        print('FIFO_REFUSED_BEFORE_READ')


if __name__ == '__main__':
    fifo_probe() if sys.argv[1:] == ['--fifo-probe'] else unittest.main()
