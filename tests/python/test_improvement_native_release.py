"""Private inventory fixtures and real runtime file handles; no native child."""
from _paths import ROOT, SERVER  # noqa: F401

import base64
import csv
import hashlib
import importlib
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


def pin():
    return dict(version=1, provider='anthropic-cli', engine_id='claude-sdk', model='selected', reasoning='high',
        cli_path=r'C:\selected\cli.exe', cli_hash='a' * 64, cli_version='2.1.309', sdk_version='0.2.116',
        profile_version='claude-isolated-roles-v2', profile_hash='b' * 64)


class NativeReleaseTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('improvement_native_release'), 'native release builder missing')
        self.m = importlib.import_module('improvement_native_release')
        self.tmp = tempfile.TemporaryDirectory(prefix='native-release-'); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name); self.source = self.root / 's'; self.packages = self.root / 'p'
        self.source.mkdir(); self.packages.mkdir()
        self.write_source('entry.py', 'import helper\nimport claude_agent_sdk\n')
        self.write_source('helper.py', "import entry\nVALUE='private actual source'\n")
        self.wheel('claude-agent-sdk', '0.2.116', {'claude_agent_sdk/__init__.py': b'VALUE=1\n'},
                   requires=['dep>=1; sys_platform == "win32"', 'absent-extra; extra == "dev"'])
        self.wheel('pywin32', '312', {'win32/lib/pywintypes.py': b'VALUE=2\n',
                   'pywin32_system32/pywintypes312.dll': b'INERT_DLL_NEVER_LOADED', 'pywin32.pth': b'import PRIVATE_MUST_NOT_EXECUTE\n'})
        self.wheel('dep', '1.0', {'dep/__init__.py': b'VALUE=3\n', 'dep/data/schema.json': b'{"type":"object"}',
                   'dep/__pycache__/ignored.pyc': b'IGNORED', 'dep/tests/test_unused.py': b'IGNORED',
                   'dep/_bundled/claude.exe': b'INERT_NEVER_EXECUTED'})

    def write_source(self, name, text):
        path = self.source / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_text(text, encoding='utf-8')

    def wheel(self, name, version, files, requires=()):
        directory = name.replace('-', '_') + '-' + version + '.dist-info'
        files = {**files, directory + '/METADATA': ('Metadata-Version: 2.1\nName: ' + name + '\nVersion: ' + version
                + '\n' + ''.join('Requires-Dist: ' + value + '\n' for value in requires)).encode()}
        rows = []
        for relative, raw in files.items():
            path = self.packages / relative; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(raw)
            digest = base64.urlsafe_b64encode(hashlib.sha256(raw).digest()).decode().rstrip('=')
            rows.append((relative, 'sha256=' + digest, str(len(raw))))
        output = io.StringIO(); writer = csv.writer(output, lineterminator='\n'); writer.writerows(rows)
        writer.writerow((directory + '/RECORD', '', ''))
        (self.packages / directory / 'RECORD').write_text(output.getvalue(), encoding='utf-8')

    def inventory(self): return self.m._inventory(self.source, self.packages, ('entry.py',))

    def test_wheel_manual_and_shell_completion_records_are_omitted_without_following_outside_import_root(self):
        ancillary = ('../../share/man/man1/segno.1', '../../share/bash-completion/completions/yt-dlp',
            '../../share/doc/yt_dlp/README.txt', '../../share/fish/vendor_completions.d/yt-dlp.fish',
            '../../share/man/man1/yt-dlp.1', '../../share/zsh/site-functions/_yt-dlp')
        record = self.packages / 'dep-1.0.dist-info/RECORD'
        with record.open('a', encoding='utf-8', newline='') as output:
            csv.writer(output, lineterminator='\n').writerows((name, '', '0') for name in ancillary)
        before = {path.relative_to(self.root).as_posix() for path in self.root.rglob('*')}
        sources, imports = self.inventory()
        self.assertEqual(set(sources), {'entry.py', 'helper.py'})
        self.assertIn('dep-1.0.dist-info/RECORD', imports)
        self.assertEqual(before, {path.relative_to(self.root).as_posix() for path in self.root.rglob('*')})
        for name in ancillary:
            self.assertIsNone(self.m._record_path(name))
        for name in ('../../share/dep.py', '../../share/man/../dep.py', '../../share/doc/../../dep.py',
                '../../share//man/man1/dep.1', '../../share/man/./man1/dep.1', '/share/man/man1/dep.1',
                r'../../share/man/..\dep.py', '../../share/doc/C:dep.py',
                '../../share/man/man1/dep.1.', '../../share/man/man1/dep.1 '):
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, 'native_release_path'):
                self.m._record_path(name)

    def test_recursive_actual_source_and_windows_metadata_closure_without_executing_imports(self):
        sources, imports = self.inventory()
        self.assertEqual(set(sources), {'entry.py', 'helper.py'})
        self.assertIn('dep/data/schema.json', imports)
        self.assertIn('pywin32_system32/pywintypes312.dll', imports)
        self.assertIn('pywin32.pth', imports)
        self.assertFalse(any('__pycache__' in name or '/tests/' in name or '/_bundled/' in name for name in imports))
        self.assertEqual(imports['claude_agent_sdk/__init__.py'], hashlib.sha256(b'VALUE=1\n').hexdigest())
        with self.assertRaises(ValueError): self.m._inventory(self.source, self.packages, ('entry.py',), sdk_version='0.0.0')

    def test_actual_import_byte_tampering_missing_dependency_and_authority_source_exclusion(self):
        self.write_source('entry.py', 'import helper\nimport improvement_native_qualifications\nimport claude_agent_sdk\n')
        self.write_source('improvement_native_qualifications.py', 'PRIVATE_AUTHORITY=1\n')
        sources, unused = self.inventory(); self.assertNotIn('improvement_native_qualifications.py', sources)
        (self.packages / 'dep/__init__.py').write_bytes(b'CHANGED')
        with self.assertRaises((ValueError, OSError)): self.inventory()
        self.wheel('dep', '1.0', {'dep/__init__.py': b'VALUE=3\n'})
        self.write_source('helper.py', 'import unavailable_required_distribution\n')
        with self.assertRaises((ValueError, OSError)): self.inventory()

    def test_record_mutation_after_catalog_cannot_pin_a_different_dependency_inventory(self):
        original = self.m._read
        changed = []
        def mutate_after_catalog(path, *args):
            raw = original(path, *args)
            if path == self.packages / 'dep-1.0.dist-info/RECORD' and not changed:
                changed.append(True)
                payload = b'VALUE=4\n'
                (self.packages / 'dep/late.py').write_bytes(payload)
                digest = base64.urlsafe_b64encode(hashlib.sha256(payload).digest()).decode().rstrip('=')
                path.write_bytes(raw + ('dep/late.py,sha256=' + digest + ',' + str(len(payload)) + '\n').encode())
            return raw
        failure = None
        with patch.object(self.m, '_read', side_effect=mutate_after_catalog):
            try: self.inventory()
            except (ValueError, OSError) as error: failure = error
        self.assertEqual(changed, [True])
        self.assertIsNotNone(failure, 'changed RECORD was accepted with the stale resolved file inventory')

    def test_parsed_metadata_mutation_cannot_drop_an_installed_dependency(self):
        original = self.m._read
        metadata = self.packages / 'claude_agent_sdk-0.2.116.dist-info/METADATA'
        original_metadata = metadata.read_bytes()
        record = self.packages / 'claude_agent_sdk-0.2.116.dist-info/RECORD'
        original_record = record.read_bytes()
        changed, result, failure = [], None, None
        def temporary_metadata(path, *args):
            if path == metadata and not changed:
                changed.append(True)
                metadata.write_bytes(b'\n'.join(line for line in original_metadata.split(b'\n')
                                              if not line.startswith(b'Requires-Dist: dep')))
                try: return original(path, *args)
                finally: metadata.write_bytes(original_metadata)
            return original(path, *args)
        with patch.object(self.m, '_read', side_effect=temporary_metadata):
            try: result = self.inventory()
            except (ValueError, OSError) as error: failure = error
        self.assertEqual(changed, [True])
        self.assertEqual(metadata.read_bytes(), original_metadata)
        self.assertEqual(record.read_bytes(), original_record)
        if failure is None: self.assertNotIn('dep/__init__.py', result[1], 'mutation did not exercise dependency omission')
        self.assertIsNotNone(failure, 'restored METADATA/RECORD accepted a closure that dropped its declared dependency')

    def test_collision_escape_missing_source_and_total_file_limit_fail_closed(self):
        with self.assertRaises((ValueError, OSError)):
            self.m._inventory(self.source, self.packages, ('entry.py', 'ENTRY.py'))
        with self.assertRaises((ValueError, OSError)): self.m._inventory(self.source, self.packages, ('missing.py',))
        with patch.object(self.m, '_MAX_FILES', 5):
            with self.assertRaises((ValueError, OSError)): self.inventory()
        record = self.packages / 'dep-1.0.dist-info/RECORD'
        with record.open('a', encoding='utf-8') as writer: writer.write('../escape.py,sha256=invalid,1\n')
        with self.assertRaises((ValueError, OSError)): self.inventory()

    def test_path_independent_content_fingerprint_changes_on_actual_content_not_local_ids(self):
        content = {'version': 1, 'runtime': {'executable': '1' * 64, 'dll': '2' * 64},
                   'source': {'entry.py': '3' * 64}, 'imports': {'dep/__init__.py': '4' * 64}}
        expected = hashlib.sha256(json.dumps(content, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()).hexdigest()
        self.assertEqual(self.m._fingerprint(content), expected)
        changed = {**content, 'runtime': {**content['runtime'], 'dll': '5' * 64}}
        self.assertNotEqual(self.m._fingerprint(changed), expected)

    def test_empty_external_registry_refuses_before_observation_and_never_self_registers(self):
        import improvement_native_qualifications as authority
        self.assertEqual(authority.REVIEWED_RELEASES, {})
        with patch.object(self.m, 'observe_release', side_effect=AssertionError('unregistered installation observed')):
            with self.assertRaises((ValueError, PermissionError)):
                self.m.qualified_launch(pin(), kind='trial', scratch=r'C:\private\scratch')
        self.assertEqual(authority.REVIEWED_RELEASES, {})

    def test_reviewed_fingerprint_required_and_local_manifest_paths_are_not_authority(self):
        import improvement_native_qualifications as authority
        value = pin()
        key = ('win32', value['cli_version'], value['cli_hash'], value['sdk_version'], value['profile_version'], value['profile_hash'], 'c' * 64)
        def manifest(kind):
            runtime = {'path': r'C:\Python\python.exe', 'sha256': '1' * 64, 'volume_serial_64': 1, 'file_id_128': '2' * 32}
            target = {'guardian': 'improvement_native_lifetime.py', 'trial': 'improvement_worker.py',
                      'operation': 'improvement_operation_worker.py'}[kind]
            return {'version': 1, 'entrypoint': kind, 'runtime': {'executable': runtime,
                'dll': {**runtime, 'path': r'C:\Python\python312.dll'}},
                'source': {'root': r'C:\server', 'files': dict.fromkeys(('improvement_native_bootstrap.py',
                    'improvement_native_image.py', target), '3' * 64)},
                'imports': {'site_packages': r'C:\packages', 'files': {}}}
        observed = {'version': 1, 'fingerprint': 'c' * 64, 'content': {}, 'manifests': {
            kind: manifest(kind) for kind in ('guardian', 'trial', 'operation')},
            'coverage': {'authority': 'unknown'}}
        # Explicit engineering authority/observation seams; no real launch or qualification.
        with patch.dict(authority.REVIEWED_RELEASES, {key: 'd' * 64}, clear=True), \
                patch.object(self.m.sys, 'platform', 'win32'), patch.object(self.m, 'observe_release', return_value=observed):
            result = self.m.qualified_launch(value, kind='preflight', scratch=r'C:\private\scratch')
            self.assertEqual(result['policy'], {'version': 1, 'bootstrap': manifest('trial'), 'scratch': r'C:\private\scratch'})
            self.assertEqual(result['qualification_hash'], 'd' * 64)
            observed['fingerprint'] = 'e' * 64
            with self.assertRaises((ValueError, PermissionError)): self.m.qualified_launch(value, kind='operation', scratch=r'C:\private\scratch')

    def test_bad_pin_kind_scratch_and_registry_values_refuse(self):
        import improvement_native_qualifications as authority
        for value in ({**pin(), 'version': True}, {**pin(), 'extra': 'private'}, {**pin(), 'cli_hash': False}):
            with self.subTest(value=value), self.assertRaises((ValueError, TypeError)): self.m.observe_release(value)
        for kind, scratch in ((True, r'C:\scratch'), ('query', r'C:\scratch'), ('trial', 'relative')):
            with self.subTest(kind=kind), self.assertRaises((ValueError, TypeError)):
                self.m.qualified_launch(pin(), kind=kind, scratch=scratch)

    @unittest.skipUnless(os.name == 'nt', 'actual base-Python runtime file handles, no process launch')
    def test_actual_base_runtime_file_identity_and_current_bytes_are_manifest_observations(self):
        import improvement_claude as profile
        mandatory = ('improvement_native_bootstrap.py', 'improvement_native_image.py',
                     'improvement_native_lifetime.py', 'improvement_worker.py', 'improvement_operation_worker.py')
        for name in mandatory: self.write_source(name, 'VALUE=1\n')
        value = pin()
        value['profile_hash'] = hashlib.sha256(json.dumps({name: hashlib.sha256((self.source / name).read_bytes()).hexdigest()
            for name in ('entry.py', 'helper.py')}, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        with patch.object(profile, 'PROFILE_SOURCES', ('entry.py', 'helper.py')), patch.object(self.m, '_SEEDS', mandatory):
            observed = self.m.observe_release(value, source_root=self.source, site_packages=self.packages)
            observed['manifests']['trial']['source']['files']['entry.py'] = '0' * 64
            repeated = self.m.observe_release(value, source_root=self.source, site_packages=self.packages)
        self.assertEqual(observed['fingerprint'], repeated['fingerprint'])
        self.assertNotEqual(repeated['manifests']['trial']['source']['files']['entry.py'], '0' * 64)
        self.assertEqual(repeated['coverage']['authority'], 'unknown')
        self.assertEqual(repeated['fingerprint'], self.m._fingerprint(repeated['content']))
        runtime = repeated['manifests']['guardian']['runtime']
        self.assertEqual(set(runtime), {'executable', 'dll'})
        for value in runtime.values():
            self.assertEqual(set(value), {'path', 'sha256', 'volume_serial_64', 'file_id_128'})
            self.assertEqual(hashlib.sha256(Path(value['path']).read_bytes()).hexdigest(), value['sha256'])
            self.assertGreater(value['volume_serial_64'], 0); self.assertEqual(len(value['file_id_128']), 32)
        self.assertEqual(repeated['content']['runtime'], {name: value['sha256'] for name, value in runtime.items()})


if __name__ == '__main__': unittest.main()
