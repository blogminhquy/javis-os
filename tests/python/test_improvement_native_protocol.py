"""Pure wire grammar: stdlib only, no app imports, I/O, environment or native calls."""
import base64
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import unittest

SOURCE = Path(__file__).resolve().parents[2] / 'server' / 'improvement_native_protocol.py'
if SOURCE.exists():
    spec = importlib.util.spec_from_file_location('native_protocol_under_test', SOURCE)
    protocol = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(protocol)
else:
    protocol = None

HASH = 'a' * 64
SHARE = base64.b64encode(b'inert-share-not-a-real-socket').decode('ascii')
PURPOSES = ('adapter_version', 'auth_status', 'sdk_version', 'query')


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode('utf-8')


def startup(kind='trial'):
    environment = {key: r'C:\private' for key in ('PATH', 'HOME', 'USERPROFILE', 'TEMP', 'TMP',
        'JAVIS_STATE_DIR', 'BRAINS_DIR', 'OBSIDIAN_VAULT_PATH', 'BRAIN_PATH', 'SOURCES_PATH', 'APPDATA', 'LOCALAPPDATA')}
    environment.update(ENABLE_TOOL_SEARCH='false', DISABLE_TELEMETRY='1', DISABLE_ERROR_REPORTING='1',
        DISABLE_NON_ESSENTIAL_MODEL_CALLS='1', CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC='1', PYTHONIOENCODING='utf-8')
    request = {'version': 1, 'config_pin': {'fixture': 'no credentials'}}
    if kind != 'preflight':
        identity = {'trial_id': 'trial-a', 'attempt': 1, 'input_hash': HASH} if kind == 'trial' else {
            'operation_id': 'operation-a', 'attempt': 1, 'role': 'improver', 'purpose': 'improve_propose', 'input_hash': HASH}
        request.update(workspace_root=r'C:\private', receipt=identity | {'path': r'C:\private\attempt'}, capability_hash=HASH)
    return {'version': 2, 'type': 'startup2', 'kind': kind, 'launch_nonce': HASH,
        'worker_pid': 123, 'worker_birth': 456, 'private_share': SHARE,
        'images': [{'purpose': purpose, 'nonce': str(index + 1) * 64, 'share': SHARE}
                   for index, purpose in enumerate(PURPOSES[:2] if kind == 'preflight' else PURPOSES)],
        'request': request, 'environment': environment}


class ProtocolTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(protocol, 'private native protocol is absent')
        self.value = startup()
        self.binding = protocol.worker_binding(self.value)

    def packet(self, body, sequence=1):
        return {'version': 2, 'sequence': sequence, 'launch_nonce': HASH, 'worker_pid': 123,
                'worker_birth': 456, 'body': body}

    def validate(self, value, direction='worker', sequence=1):
        return protocol.validate_private_packet2(value, binding=self.binding, direction=direction, expected_sequence=sequence)

    def test_three_startup_kinds_are_defensive_and_frame_without_overread(self):
        for kind in ('trial', 'operation', 'preflight'):
            value = startup(kind)
            result = protocol.validate_startup2(value)
            self.assertEqual(result, value)
            result['environment']['HOME'] = 'changed-copy'
            self.assertNotEqual(result, value)
            raw = protocol.encode_startup2(value)
            self.assertEqual(raw, canonical(value) + b'\n')
            self.assertEqual(protocol.decode_startup2(raw), value)
            with self.assertRaises(ValueError):
                protocol.decode_startup2(raw + raw)

    def test_startup_refuses_credentials_unknown_fields_and_unsafe_environment(self):
        for field, value in (('ANTHROPIC_API_KEY', 'secret'), ('CLAUDE_CONFIG_DIR', 'override'),
                             ('DISABLE_TELEMETRY', '0'), ('HOME', 'x\x00y')):
            bad = copy.deepcopy(self.value)
            bad['environment'][field] = value
            with self.assertRaises(ValueError): protocol.validate_startup2(bad)
        bad = copy.deepcopy(self.value); bad['extra'] = True
        with self.assertRaises(ValueError): protocol.validate_startup2(bad)

    def test_startup_requires_exact_ordered_unique_purposes_and_canonical_shares(self):
        variants = []
        for change in ('order', 'missing', 'replay_nonce', 'bad_share', 'unknown_purpose'):
            bad = copy.deepcopy(self.value)
            if change == 'order': bad['images'].reverse()
            elif change == 'missing': bad['images'].pop()
            elif change == 'replay_nonce': bad['images'][1]['nonce'] = bad['images'][0]['nonce']
            elif change == 'bad_share': bad['private_share'] = SHARE + '\n'
            else: bad['images'][0]['purpose'] = 'arbitrary_shell'
            variants.append(bad)
        for bad in variants:
            with self.assertRaises(ValueError): protocol.validate_startup2(bad)

    def test_builtin_types_survive_validation_without_equality_spoofing(self):
        class Text(str): pass
        class Number(int): pass
        for field, value in (('version', True), ('worker_pid', True), ('worker_birth', Number(456)),
                             ('launch_nonce', Text(HASH)), ('kind', Text('trial'))):
            bad = copy.deepcopy(self.value); bad[field] = value
            with self.assertRaises(ValueError): protocol.validate_startup2(bad)
        bad = copy.deepcopy(self.value); bad['request']['receipt']['attempt'] = True
        with self.assertRaises(ValueError): protocol.validate_startup2(bad)

    def test_private_engine_bytes_and_raw_optional_values_round_trip(self):
        identity = self.binding['identity']
        body = {'type': 'engine_event', **identity, 'event': {'type': 'tool_result', 'is_error': None,
                'content': 'Tiếng Việt\r\n', 'cost': 0.125}}
        packet = self.packet(body)
        wire = protocol.encode_private_packet2(packet, binding=self.binding, direction='worker', expected_sequence=1)
        self.assertEqual(wire, struct.pack('!I', len(canonical(packet))) + canonical(packet))
        self.assertEqual(protocol.decode_private_packet2(wire, binding=self.binding, direction='worker', expected_sequence=1), packet)
        copy_packet = self.validate(packet); copy_packet['body']['event']['content'] = 'copy'
        self.assertNotEqual(copy_packet, packet)

    def test_binding_sequence_direction_and_identity_mismatch_refuse(self):
        packet = self.packet({'type': 'engine_start_requested', **self.binding['identity']})
        for field, value in (('sequence', 2), ('worker_pid', 124), ('worker_birth', 457), ('launch_nonce', 'b' * 64)):
            bad = copy.deepcopy(packet); bad[field] = value
            with self.assertRaises(ValueError): self.validate(bad)
        with self.assertRaises(ValueError): self.validate(packet, direction='host')
        bad = copy.deepcopy(packet); bad['body']['attempt'] = 2
        with self.assertRaises(ValueError): self.validate(bad)
        ack = self.packet({'type': 'engine_start_ack', **self.binding['identity']})
        self.assertEqual(self.validate(ack, direction='host'), ack)

    def test_dispatch_must_bind_purpose_native_incarnation_and_exact_proof_hash(self):
        proof = {'version': 1, 'basis': 'query_argument_consistency', 'argv_hash': HASH}
        body = {'type': 'dispatch_observed', 'purpose': 'query', 'nonce': '4' * 64,
                'native_pid': 321, 'native_birth': 654, 'dispatch': proof,
                'dispatch_hash': hashlib.sha256(canonical(proof)).hexdigest()}
        packet = self.packet(body)
        self.assertEqual(self.validate(packet), packet)
        for field, value in (('purpose', 'arbitrary'), ('nonce', HASH), ('native_pid', False), ('dispatch_hash', HASH)):
            bad = copy.deepcopy(packet); bad['body'][field] = value
            with self.assertRaises(ValueError): self.validate(bad)

    def test_only_closed_adoption_and_bounded_public_errors_before_ready(self):
        self.assertEqual(self.validate(self.packet({'type': 'endpoints_adopted'}))['body']['type'], 'endpoints_adopted')
        error = self.packet({'type': 'worker_error', 'reason': 'trial_worker_failed', 'error_type': 'ValueError'})
        self.assertEqual(self.validate(error), error)
        for body in ({'type': 'endpoints_adopted', 'private_input': 'leak'}, {'type': 'future_generic_payload'},
                     {'type': 'worker_error', 'reason': 'raw input: secret', 'error_type': 'ValueError'}):
            with self.assertRaises(ValueError): self.validate(self.packet(body))

    def test_existing_fixture_broker_observation_needs_no_invented_type(self):
        event = {'sequence': 1, 'status': 'fixture_hit', 'snapshot_id': 'snapshot-a', 'capability_id': 'fixture.read'}
        packet = self.packet({'type': 'fixture_event', **self.binding['identity'], 'event': event})
        self.assertEqual(self.validate(packet), packet)

    def test_preflight_complete_carries_only_stable_closed_runtime_observations(self):
        self.binding = protocol.worker_binding(startup('preflight'))
        runtime = {'platform': 'win32', 'cli_hash': HASH, 'sdk_version': '0.2.116', 'profile_hash': HASH,
            'managed_policy': 'absent', 'cli_version': '2.1.309',
            'auth': {'logged_in': True, 'method': 'subscription', 'provider': 'anthropic', 'plan': None}}
        packet = self.packet({'type': 'preflight_complete', 'runtime': runtime})
        self.assertEqual(self.validate(packet), packet)
        for extra in ('pid', 'nonce', 'auth_token'):
            bad = copy.deepcopy(packet); bad['body']['runtime'][extra] = 'forbidden'
            with self.assertRaises(ValueError): self.validate(bad)

    def test_decode_rejects_duplicate_noncanonical_partial_oversize_and_nested_frames(self):
        packet = self.packet({'type': 'endpoints_adopted'})
        raw = canonical(packet)
        invalid = [b'', struct.pack('!I', len(raw) + 1) + raw, struct.pack('!I', 8 * 1024 * 1024 + 1),
                   struct.pack('!I', len(raw)) + raw + b'x']
        for content in (raw.replace(b'"version":2', b'"version":2,"version":2'), json.dumps(packet).encode(), b'[' * 40 + b'0' + b']' * 40):
            invalid.append(struct.pack('!I', len(content)) + content)
        for wire in invalid:
            with self.assertRaises(ValueError):
                protocol.decode_private_packet2(wire, binding=self.binding, direction='worker', expected_sequence=1)


if __name__ == '__main__':
    unittest.main()
