"""Closed child observations reuse qualification; never launch CLI or an engine."""
from _paths import ROOT, SERVER  # noqa: F401

from contextlib import contextmanager
import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

TEST_ROOT = Path(tempfile.mkdtemp(prefix='observed-verify-'))
for key, name in {'JAVIS_STATE_DIR': 'state', 'BRAINS_DIR': 'brains', 'OBSIDIAN_VAULT_PATH': 'vault',
                 'BRAIN_PATH': 'brain', 'SOURCES_PATH': 'sources'}.items():
    os.environ[key] = str(TEST_ROOT / name)

import improvement_claude as adapter


class ObservedVerificationTests(unittest.TestCase):
    def setUp(self):
        self.pin = dict(version=1, provider='anthropic-cli', engine_id='claude-sdk',
            model='claude-opus-5-5', reasoning='medium', cli_path=str(TEST_ROOT / 'claude.exe'),
            cli_hash='a' * 64, cli_version='2.1.304', sdk_version='0.2.116',
            profile_version=adapter.PROFILE_VERSION, profile_hash='b' * 64)
        self.observed = dict(platform='win32', cli_hash='a' * 64, cli_version='2.1.304',
            sdk_version='0.2.116', profile_hash='b' * 64, managed_policy='absent',
            auth=dict(logged_in=True, method='claude.ai', provider='firstParty', plan='max'))

    @contextmanager
    def registered(self, qualification='c' * 64):
        with patch.object(adapter, '_profile_qualification', return_value=qualification), \
                patch.object(adapter, 'VERIFIED_NATIVE_RUNTIMES', {('win32', '2.1.304', 'a' * 64, '0.2.116')}), \
                patch.object(adapter, 'profile_hash', return_value='b' * 64), \
                patch.object(adapter.importlib.metadata, 'version', return_value='0.2.116'), \
                patch.object(adapter.subprocess, 'run', side_effect=AssertionError('unexpected CLI call')):
            yield

    def verify_observation(self, value=None):
        subject = adapter.ClaudeTrialAdapter(self.pin)
        self.assertTrue(callable(getattr(subject, 'verify_observed', None)), 'closed observed-runtime verifier missing')
        with patch.object(adapter, '_runtime_observation', side_effect=AssertionError('repeated native preflight')):
            return subject.verify_observed(self.observed if value is None else value)

    def test_same_capability_as_legacy_without_repeating_preflight_and_defensive_result(self):
        with self.registered(), patch.object(adapter, '_runtime_observation', return_value=copy.deepcopy(self.observed)):
            legacy = adapter.ClaudeTrialAdapter(self.pin).verify()
        with self.registered():
            result = self.verify_observation()
        self.assertTrue(result['supported'])
        self.assertEqual(result, legacy)
        self.observed['auth']['plan'] = 'changed'
        self.assertEqual(result['runtime']['auth']['plan'], 'max')

    def test_no_registration_never_creates_capability(self):
        with self.registered(None):
            result = self.verify_observation()
        self.assertEqual(result['reason'], 'native_profile_unqualified')
        self.assertNotIn('capability_hash', result)

    def test_runtime_drift_never_switches_requested_configuration(self):
        for key, value in (('cli_hash', 'd' * 64), ('cli_version', '9.9.9'), ('sdk_version', '9.9.9'),
                           ('profile_hash', 'd' * 64), ('platform', 'linux')):
            with self.subTest(key=key), self.registered():
                result = self.verify_observation({**self.observed, key: value})
                self.assertFalse(result['supported'])
                self.assertEqual(result['requested'], {k: self.pin[k] for k in ('provider', 'engine_id', 'model', 'reasoning')})

    def test_managed_policy_and_auth_uncertainty_are_not_supported(self):
        variants = [{**self.observed, 'managed_policy': state} for state in ('present', 'unknown')]
        variants += [{**self.observed, 'auth': {**self.observed['auth'], key: value}} for key, value in
                     (('logged_in', False), ('method', None), ('provider', 'other'), ('plan', 'enterprise'))]
        for value in variants:
            with self.subTest(value=value), self.registered(): self.assertFalse(self.verify_observation(value)['supported'])

    def test_closed_observation_refuses_private_extra_fields_and_bad_types(self):
        class Foreign(dict): pass
        variants = [Foreign(self.observed), {**self.observed, 'nonce': 'sensitive-sentinel'},
            {k: v for k, v in self.observed.items() if k != 'cli_version'},
            {**self.observed, 'auth': {**self.observed['auth'], 'token': 'sensitive-sentinel'}},
            {**self.observed, 'auth': {**self.observed['auth'], 'logged_in': 1}},
            {**self.observed, 'cli_hash': True}]
        for value in variants:
            with self.subTest(value=value), self.registered():
                result = self.verify_observation(value)
                self.assertFalse(result['supported'])
                self.assertNotIn('capability_hash', result)
                self.assertNotIn('sensitive-sentinel', json.dumps(result))

    def test_unsupported_pin_never_uses_observation_to_bypass_policy(self):
        self.pin['provider'] = 'unselected-provider'
        with self.registered(): result = self.verify_observation()
        self.assertEqual(result['reason'], 'unsupported_trial_configuration')
        self.assertNotIn('capability_hash', result)

    def test_asserted_pin_metadata_cannot_hide_actual_local_source_or_sdk_drift(self):
        for kind in ('source', 'sdk_version', 'sdk_unavailable'):
            with self.subTest(kind=kind), self.registered():
                if kind == 'source':
                    fault = patch.object(adapter, 'profile_hash', return_value='d' * 64)
                elif kind == 'sdk_version':
                    fault = patch.object(adapter.importlib.metadata, 'version', return_value='9.9.9')
                else:
                    fault = patch.object(adapter.importlib.metadata, 'version',
                        side_effect=adapter.importlib.metadata.PackageNotFoundError('claude-agent-sdk'))
                with fault: result = self.verify_observation()
                self.assertFalse(result['supported'])
                self.assertNotIn('capability_hash', result)


if __name__ == '__main__': unittest.main()
