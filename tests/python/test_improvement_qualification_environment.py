"""Pure local dummy environment, no I/O/runtime/account/launch capability."""
from _paths import ROOT, SERVER  # noqa: F401

import copy
import importlib
import importlib.util
import unittest
from unittest.mock import patch

from improvement_native_protocol import _ENV_FIXED, _ENV_PATHS


class QualificationEnvironmentTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('improvement_qualification_environment'), 'canonical dummy-only environment helper missing')
        self.m = importlib.import_module('improvement_qualification_environment')
        self.base = {**dict.fromkeys(_ENV_PATHS, 'C:\\isolated\\qualification'), **_ENV_FIXED}
        self.endpoint = 'http://127.0.0.1:15432'

    def test_exact_literal_dummy_augmentation_and_defensive_validation_without_ambient_environment(self):
        before = copy.deepcopy(self.base)
        with patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'ambient-must-never-read', 'HTTPS_PROXY': 'ambient-proxy'}, clear=True):
            result = self.m.dummy_environment(self.base, endpoint=self.endpoint)
            checked = self.m.validate_dummy_environment(result)
        self.assertEqual(self.base, before)
        self.assertEqual(result, {**before, 'ANTHROPIC_API_KEY': 'javis-native-qualification-dummy', 'ANTHROPIC_BASE_URL': self.endpoint})
        self.assertEqual(checked, result); self.assertIsNot(checked, result)
        checked['HOME'] = 'caller-mutation'
        self.assertNotEqual(result['HOME'], checked['HOME'])

    def test_only_canonical_numeric_ipv4_loopback_http_endpoint_and_port_are_allowed(self):
        bad = ('https://127.0.0.1:15432', 'http://localhost:15432', 'http://127.1:15432', 'http://2130706433:15432',
            'http://127.0.0.2:15432', 'http://[::1]:15432', 'http://0.0.0.0:15432', 'http://example.com:15432',
            'http://127.0.0.1', 'http://127.0.0.1:0', 'http://127.0.0.1:65536', 'http://127.0.0.1:015432',
            'http://127.0.0.1:+15432', 'http://127.0.0.1:15432/', 'http://127.0.0.1:15432/v1',
            'http://127.0.0.1:15432?query', 'http://127.0.0.1:15432#fragment', 'http://user@127.0.0.1:15432',
            'http://user:password@127.0.0.1:15432', 'HTTP://127.0.0.1:15432', 'http://127.0.0.1:15432\n',
            'http://127.0.0.1:15432\x00', None, True, 15432)
        for value in bad:
            with self.subTest(endpoint=value), self.assertRaises(ValueError): self.m.dummy_environment(self.base, endpoint=value)
        for port in (1, 80, 65535):
            value = self.m.dummy_environment(self.base, endpoint='http://127.0.0.1:' + str(port))
            self.assertEqual(value['ANTHROPIC_BASE_URL'], 'http://127.0.0.1:' + str(port))

    def test_base_rejects_secrets_auth_proxy_mode_knobs_and_malformed_fixed_values(self):
        for name in ('ANTHROPIC_API_KEY', 'ANTHROPIC_BASE_URL', 'CLAUDE_CONFIG_DIR', 'HTTP_PROXY', 'HTTPS_PROXY',
                'ALL_PROXY', 'NO_PROXY', 'JAVIS_NATIVE_QUALIFICATION', 'PYTHONPATH'):
            with self.subTest(name=name), self.assertRaises(ValueError): self.m.dummy_environment({**self.base, name: 'foreign'}, endpoint=self.endpoint)
        for changes in ({'ENABLE_TOOL_SEARCH': 'true'}, {'DISABLE_TELEMETRY': True}, {'HOME': ''}, {'TMP': 'bad\x00path'}):
            with self.subTest(changes=changes), self.assertRaises(ValueError): self.m.dummy_environment({**self.base, **changes}, endpoint=self.endpoint)
        for name in self.base:
            broken = dict(self.base); broken.pop(name)
            with self.subTest(missing=name), self.assertRaises(ValueError): self.m.dummy_environment(broken, endpoint=self.endpoint)

    def test_final_environment_cannot_substitute_key_endpoint_or_add_auth_authority(self):
        result = self.m.dummy_environment(self.base, endpoint=self.endpoint)
        for changes in ({'ANTHROPIC_API_KEY': 'real-key'}, {'ANTHROPIC_BASE_URL': 'http://external.example:15432'},
                {'CLAUDE_CONFIG_DIR': 'foreign'}, {'HTTPS_PROXY': 'foreign'}):
            with self.subTest(changes=changes), self.assertRaises(ValueError): self.m.validate_dummy_environment({**result, **changes})
        for name in ('ANTHROPIC_API_KEY', 'ANTHROPIC_BASE_URL'):
            broken = dict(result); broken.pop(name)
            with self.subTest(missing=name), self.assertRaises(ValueError): self.m.validate_dummy_environment(broken)

    def test_production_startup2_still_refuses_dummy_environment_without_an_explicit_new_protocol(self):
        from improvement_native_protocol import validate_startup2
        import test_improvement_native_protocol as wire
        value = wire.startup('trial')
        value['environment'] = self.m.dummy_environment(self.base, endpoint=self.endpoint)
        with self.assertRaises(ValueError): validate_startup2(value)


if __name__ == '__main__': unittest.main()
