"""Current static admission precedes any guarded native preflight command."""
from _paths import ROOT, SERVER  # noqa: F401

import hashlib
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

import test_improvement_observed_verification as fixture

adapter = fixture.adapter


class PreflightAdmissionTests(unittest.TestCase):
    def setUp(self):
        base = fixture.ObservedVerificationTests(); base.setUp()
        self.pin = base.pin
        self.directory = tempfile.TemporaryDirectory(prefix='preflight-admission-')
        self.addCleanup(self.directory.cleanup)
        binary = Path(self.directory.name) / 'inert-cli.exe'
        binary.write_bytes(b'INERT_BINARY_BYTES_NEVER_EXECUTED')
        self.pin.update(cli_path=str(binary), cli_hash=hashlib.sha256(binary.read_bytes()).hexdigest())

    @contextmanager
    def admitted_metadata(self):
        with patch.object(adapter, '_profile_qualification', return_value='c' * 64), \
                patch.object(adapter, 'profile_hash', return_value=self.pin['profile_hash']), \
                patch.object(adapter.importlib.metadata, 'version', return_value=self.pin['sdk_version']), \
                patch.object(adapter, '_managed_policy', return_value='absent'), \
                patch.object(adapter, 'VERIFIED_NATIVE_RUNTIMES', {(adapter.sys.platform,
                    self.pin['cli_version'], self.pin['cli_hash'], self.pin['sdk_version'])}), \
                patch.object(adapter.subprocess, 'run', side_effect=AssertionError('CLI ran during static admission')):
            yield

    def admit(self):
        owner = adapter.ClaudeTrialAdapter(self.pin)
        self.assertTrue(callable(getattr(owner, 'admit_preflight', None)), 'native preflight admission missing')
        return owner.admit_preflight()

    def test_unregistered_source_refuses_before_binary_sdk_or_policy_observation(self):
        with patch.object(adapter, '_profile_qualification', return_value=None), \
                patch.object(adapter, 'profile_hash', side_effect=AssertionError('unregistered source observed')), \
                patch.object(adapter.importlib.metadata, 'version', side_effect=AssertionError('unregistered SDK observed')), \
                patch.object(adapter, '_managed_policy', side_effect=AssertionError('unregistered policy observed')), \
                patch.object(Path, 'open', side_effect=AssertionError('unregistered binary opened')):
            result = self.admit()
        self.assertEqual(result, {'admitted': False, 'reason': 'native_profile_unqualified'})

    def test_current_static_admission_reads_real_bytes_without_auth_or_live_capability(self):
        with self.admitted_metadata(): result = self.admit()
        self.assertEqual(set(result), {'admitted', 'reason', 'runtime', 'profile_qualification_hash'})
        self.assertTrue(result['admitted'])
        self.assertIsNone(result['reason'])
        self.assertEqual(result['runtime']['cli_hash'], self.pin['cli_hash'])
        self.assertEqual(result['runtime']['profile_hash'], self.pin['profile_hash'])
        self.assertNotIn('auth', result['runtime'])
        self.assertNotIn('cli_version', result['runtime'])
        self.assertNotIn('supported', result)
        self.assertNotIn('capability_hash', result)

    def test_configuration_source_sdk_policy_binary_and_known_runtime_drift_refuse(self):
        faults = {
            'configuration': lambda: patch.dict(self.pin, provider='unselected-provider'),
            'source': lambda: patch.object(adapter, 'profile_hash', return_value='d' * 64),
            'sdk': lambda: patch.object(adapter.importlib.metadata, 'version', return_value='9.9.9'),
            'sdk_missing': lambda: patch.object(adapter.importlib.metadata, 'version',
                side_effect=adapter.importlib.metadata.PackageNotFoundError('claude-agent-sdk')),
            'policy_present': lambda: patch.object(adapter, '_managed_policy', return_value='present'),
            'policy_unknown': lambda: patch.object(adapter, '_managed_policy', return_value='unknown'),
            'binary': lambda: patch.dict(self.pin, cli_hash='d' * 64),
            'known_runtime': lambda: patch.object(adapter, 'VERIFIED_NATIVE_RUNTIMES', set()),
        }
        for name, fault in faults.items():
            with self.subTest(name=name), self.admitted_metadata(), fault():
                result = self.admit()
                self.assertFalse(result['admitted'])
                self.assertNotIn('runtime', result)
                self.assertNotIn('capability_hash', result)


if __name__ == '__main__': unittest.main()
