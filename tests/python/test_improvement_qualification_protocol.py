"""Pure engineering wire consistency; no authority, filesystem or native calls."""
from _paths import ROOT, SERVER  # noqa: F401

import copy
import hashlib
import importlib
import importlib.util
import unittest

import test_improvement_native_protocol as P
import test_improvement_native_sdk as N
from improvement_qualification_environment import dummy_environment


def digest(value): return hashlib.sha256(P.canonical(value)).hexdigest()


def startup(kind='trial'):
    value = P.startup(kind)
    value.update(version=3, type='startup3')
    pin = N.pin(); pin['profile_version'] = 'claude-owned-images-v3'
    value['request']['config_pin'] = pin
    home = r'C:\private\homes\fixture'
    value['environment'].update(HOME=home, USERPROFILE=home,
        APPDATA=home + r'\AppData\Roaming', LOCALAPPDATA=home + r'\AppData\Local')
    value['environment'] = dummy_environment(value['environment'], endpoint='http://127.0.0.1:15432')
    scope = {'version': 1, 'domain': 'qualification', 'account_ready': False, 'run_nonce': '9' * 64,
        'root': r'C:\private', 'brain_id': r'C:\private\brain', 'pin_hash': digest(pin),
        'release_fingerprint': '8' * 64, 'review_hash': '7' * 64, 'endpoint': 'http://127.0.0.1:15432',
        'maximum_queries': 4, 'created_at': 1000.0, 'deadline_at': 1300.0}
    run_hash = digest(scope)
    link = None
    if kind != 'preflight':
        receipt = value['request']['receipt']
        identity = receipt[kind + '_id']
        link = {'version': 1, 'domain': 'qualification', 'run_hash': run_hash, 'brain_id': scope['brain_id'],
            'kind': kind, 'subject_id': identity, 'attempt': receipt['attempt'], 'request_hash': '6' * 64,
            'workspace_hash': digest(receipt), 'materialization_hash': receipt['input_hash'],
            'engine_config_hash': digest(pin), 'capability_hash': value['request']['capability_hash'], 'call_id': 1,
            'call_binding': {'brain_id': scope['brain_id'], 'purpose': 'improve_probe' if kind == 'trial' else receipt['purpose'],
                'context_ref': 'improvement:fixture-experiment', 'mirror_ref': 'improvement_' + kind + ':' + identity,
                'reason_ref': 'improvement_' + kind + ':' + identity + ':attempt:1', 'attempt': 1}}
    value['qualification'] = {'version': 1, 'run_hash': run_hash, 'scope': scope,
        'environment_hash': digest(value['environment']), 'attempt_link': link}
    return value


class QualificationProtocolTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('improvement_qualification_protocol'), 'explicit startup3 grammar missing')
        self.protocol = importlib.import_module('improvement_qualification_protocol')

    def validate(self, value): return self.protocol.validate_startup3(value)

    def test_all_three_kinds_roundtrip_defensively_with_same_actual_channel_binding_shape(self):
        for kind in ('trial', 'operation', 'preflight'):
            with self.subTest(kind=kind):
                value = startup(kind); actual = self.validate(value)
                self.assertEqual(actual, value)
                actual['qualification']['scope']['domain'] = 'caller-mutation'
                self.assertNotEqual(actual, value)
                raw = self.protocol.encode_startup3(value)
                self.assertEqual(self.protocol.decode_startup3(raw), value)
                original = P.startup(kind)
                self.assertEqual(self.protocol.worker_binding3(value), P.protocol.worker_binding(original))
                with self.assertRaises(ValueError): self.protocol.decode_startup3(raw + raw)

    def test_default_startup2_still_refuses_even_well_formed_engineering_envelope(self):
        value = startup()
        with self.assertRaises(ValueError): P.protocol.validate_startup2(value)
        value.update(version=2, type='startup2'); value.pop('qualification')
        with self.assertRaises(ValueError): P.protocol.validate_startup2(value)

    def test_rehashed_scope_cannot_claim_account_or_foreign_pin_or_open_bounds(self):
        mutations = (('domain', 'production'), ('account_ready', True), ('maximum_queries', True),
            ('maximum_queries', 33), ('created_at', float('inf')), ('deadline_at', 1000.0),
            ('deadline_at', 4601.0), ('pin_hash', 'f' * 64), ('root', r'C:\private\..\foreign'))
        for name, change in mutations:
            with self.subTest(name=name, change=change):
                value = startup(); q = value['qualification']; q['scope'][name] = change
                if change != float('inf'): q['run_hash'] = digest(q['scope'])
                with self.assertRaises(ValueError): self.validate(value)

    def test_rehashed_environment_cannot_supply_real_auth_foreign_endpoint_or_home(self):
        for name, change in (('ANTHROPIC_API_KEY', 'real-host-key'), ('ANTHROPIC_BASE_URL', 'http://localhost:15432'),
                ('ANTHROPIC_BASE_URL', 'http://127.0.0.1:15433'), ('HTTPS_PROXY', 'http://127.0.0.1:8888'),
                ('HOME', r'C:\outside'), ('HOME', r'C:\private\..\outside'), ('USERPROFILE', r'C:\outside'),
                ('APPDATA', r'C:\outside'), ('TEMP', r'C:\outside')):
            with self.subTest(name=name, change=change):
                value = startup(); value['environment'][name] = change
                value['qualification']['environment_hash'] = digest(value['environment'])
                with self.assertRaises(ValueError): self.validate(value)

    def test_query_requires_exact_run_kind_receipt_config_capability_and_actual_call_join_data(self):
        changes = {'run_hash': 'f' * 64, 'brain_id': 'foreign', 'kind': 'operation', 'subject_id': 'foreign',
            'attempt': 2, 'workspace_hash': 'f' * 64, 'materialization_hash': 'f' * 64,
            'engine_config_hash': 'f' * 64, 'capability_hash': 'f' * 64, 'call_id': True, 'request_hash': 'bad'}
        for field, change in changes.items():
            with self.subTest(field=field):
                value = startup(); value['qualification']['attempt_link'][field] = change
                with self.assertRaises(ValueError): self.validate(value)
        for field, change in (('brain_id', 'foreign'), ('purpose', 'improve_propose'), ('attempt', True),
                ('mirror_ref', 'foreign'), ('reason_ref', 'foreign'), ('context_ref', 'unscoped')):
            with self.subTest(call_field=field):
                value = startup(); value['qualification']['attempt_link']['call_binding'][field] = change
                with self.assertRaises(ValueError): self.validate(value)

    def test_missing_extra_oversize_and_preflight_attempt_links_refuse(self):
        for key in ('scope', 'run_hash', 'environment_hash', 'attempt_link'):
            value = startup(); value['qualification'].pop(key)
            with self.subTest(key=key), self.assertRaises(ValueError): self.validate(value)
        for level in ('envelope', 'qualification', 'link'):
            value = startup()
            target = value if level == 'envelope' else value['qualification'] if level == 'qualification' else value['qualification']['attempt_link']
            target['extra'] = True
            with self.subTest(level=level), self.assertRaises(ValueError): self.validate(value)
        value = startup(); value['qualification']['attempt_link'] = None
        with self.assertRaises(ValueError): self.validate(value)
        value = startup('preflight'); value['qualification']['attempt_link'] = startup()['qualification']['attempt_link']
        with self.assertRaises(ValueError): self.validate(value)
        value = startup(); value['request']['receipt'].pop('path')
        with self.assertRaises(ValueError): self.validate(value)
        with self.assertRaises(ValueError): self.protocol.decode_startup3(b'x' * (P.protocol.MAX_PRIVATE_BYTES + 1))

    def test_run_environment_hashes_and_ordered_image_nonces_cannot_be_forged_by_presence(self):
        for change in ('run_hash', 'environment_hash', 'image_nonce', 'image_order', 'workspace', 'pin'):
            with self.subTest(change=change):
                value = startup()
                if change in ('run_hash', 'environment_hash'): value['qualification'][change] = 'f' * 64
                elif change == 'image_nonce': value['images'][1]['nonce'] = value['images'][0]['nonce']
                elif change == 'image_order': value['images'].reverse()
                elif change == 'workspace': value['request']['receipt']['path'] = r'C:\outside'
                else: value['request']['config_pin']['model'] = 'foreign-model'
                with self.assertRaises(ValueError): self.validate(value)


if __name__ == '__main__': unittest.main()
