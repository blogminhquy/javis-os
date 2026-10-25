"""Isolated stdlib-only persisted observation grammar; no application setup."""
import copy
import hashlib
import importlib
import json
import sys
import unittest
from pathlib import Path

# Only the server directory on the path: this grammar must import without application setup.
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'server'))

try:
    codec = importlib.import_module('improvement_native_observation')
except ModuleNotFoundError as error:
    if error.name != 'improvement_native_observation': raise
    codec = None


def canonical(value, ascii=False):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=ascii, allow_nan=False).encode('utf-8')


def comparison():
    identity = {'volume_serial_64': 7, 'file_id_128': 'a' * 32, 'sha256': 'b' * 64, 'size': 100}
    return {'matches': True, 'selected': dict(identity), 'actual': dict(identity),
        'proof_basis': 'observed_borrowed_file_identity_and_reopened_sha256',
        **dict.fromkeys(('metadata_mutation_exclusion', 'debug_event_origin', 'loaded_image_identity', 'comprehension'), 'unknown')}


def invocations():
    return [{'purpose': purpose, 'nonce': str(index + 2) * 64} for index, purpose in
            enumerate(('adapter_version', 'auth_status', 'sdk_version', 'query'))]


def packet(body, *, sequence=1, source='guardian', source_sequence=1):
    return {'version': 2, 'sequence': sequence, 'source': source, 'source_sequence': source_sequence,
            'launch_nonce': '1' * 64, 'worker_pid': 300, 'worker_birth': 400, 'body': body}


def offer():
    return packet({'type': 'launch_offer', 'worker_tid': 301, 'worker_thread_birth': 401,
        'root_image': comparison(), 'bootstrap_count': 1, 'images': invocations(), 'offer_hash': 'f' * 64})


def receipt(kind='trial'):
    common = {'attempt': 1, 'input_hash': 'c' * 64, 'path': 'stored-workspace', 'version': 1}
    return {**common, 'trial_id': 'trial-a'} if kind == 'trial' else {
        **common, 'operation_id': 'operation-a', 'role': 'improver', 'purpose': 'improve_propose'}


def image():
    body = {'type': 'image_observed', 'purpose': 'query', 'nonce': '5' * 64,
        'native_pid': 500, 'native_birth': 600, 'native_tid': 501, 'native_thread_birth': 601,
        'comparison': comparison(), 'source_worker_incarnation_verified': True, 'exact_outer_job': True,
        'association_basis': 'qualified_worker_create_capture_and_guardian_object_checks'}
    material = {'launch_nonce': '1' * 64, 'worker_pid': 300, 'worker_birth': 400,
                **{key: value for key, value in body.items() if key != 'type'}}
    body['observation_hash'] = hashlib.sha256(canonical(material, ascii=True)).hexdigest()
    return packet(body, sequence=3, source_sequence=2)


class ObservationTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(codec, 'pure native observation codec missing')
        self.binding = codec.observation_binding(offer(), kind='trial', receipt=receipt())

    def validate(self, value, binding=None):
        return codec.validate_observation2(value, binding=self.binding if binding is None else binding,
            expected_sequence=value['sequence'], expected_source_sequence=value['source_sequence'])

    def test_first_offer_derives_trial_and_operation_binding_without_authority_fields(self):
        for kind in ('trial', 'operation'):
            binding = codec.observation_binding(offer(), kind=kind, receipt=receipt(kind))
            self.assertEqual(set(binding), {'kind', 'launch_nonce', 'worker_pid', 'worker_birth', 'identity', 'invocations'})
            self.assertEqual(binding['kind'], kind)
            self.assertEqual(binding['identity']['input_hash'], 'c' * 64)
            self.assertEqual(binding['invocations'], invocations())
            self.assertEqual(self.validate(offer(), binding), offer())

    def test_first_offer_exact_sequence_source_kind_and_receipt_identity(self):
        for changes in ({'sequence': 2}, {'source_sequence': 2}, {'source': 'worker'}, {'version': 1}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                codec.observation_binding({**offer(), **changes}, kind='trial', receipt=receipt())
        for kind, identity in (('preflight', receipt()), ('trial', {**receipt(), 'attempt': True}),
                ('operation', {**receipt('operation'), 'role': 'owner'})):
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                codec.observation_binding(offer(), kind=kind, receipt=identity)

    def test_projected_offer_refuses_all_live_capability_fields(self):
        for field in ('process', 'stdio', 'share', 'control_share', 'private_share'):
            value = offer(); value['body'][field] = {'handle': 300}
            with self.subTest(field=field), self.assertRaises(ValueError): self.validate(value)
        value = offer(); value['body']['images'][0]['share'] = 'secret'
        with self.assertRaises(ValueError): self.validate(value)

    def test_ordered_purposes_unique_nonces_and_offer_hash_are_closed(self):
        mutations = [lambda b: b['images'].reverse(), lambda b: b['images'].pop(),
            lambda b: b['images'][1].update(nonce=b['images'][0]['nonce']),
            lambda b: b['images'][0].update(nonce='1' * 64), lambda b: b.update(offer_hash='F' * 64),
            lambda b: b.update(bootstrap_count=True)]
        for mutate in mutations:
            value = offer(); mutate(value['body'])
            with self.subTest(mutate=mutate), self.assertRaises(ValueError): self.validate(value)

    def test_image_observation_matches_actual_ascii_hash_recipe(self):
        self.assertEqual(self.validate(image()), image())
        for key, replacement in (('native_pid', 501), ('native_birth', 601), ('nonce', '4' * 64),
                ('observation_hash', '0' * 64), ('source_worker_incarnation_verified', 1), ('exact_outer_job', False)):
            value = image(); value['body'][key] = replacement
            with self.subTest(key=key), self.assertRaises(ValueError): self.validate(value)

    def test_comparison_semantics_and_unknown_coverage_do_not_become_authorization(self):
        for key, replacement in (('matches', False), ('loaded_image_identity', 'proved'), ('debug_event_origin', True)):
            value = offer(); value['body']['root_image'][key] = replacement
            with self.subTest(key=key), self.assertRaises(ValueError): self.validate(value)
        value = image(); body = value['body']; body['comparison']['actual']['sha256'] = 'd' * 64
        body['comparison']['matches'] = False
        material = {key: value[key] for key in ('launch_nonce', 'worker_pid', 'worker_birth')}
        material.update({key: item for key, item in body.items() if key not in ('type', 'observation_hash')})
        body['observation_hash'] = hashlib.sha256(canonical(material, ascii=True)).hexdigest()
        self.assertFalse(self.validate(value)['body']['comparison']['matches'])
        self.assertNotIn('decision', self.validate(value)['body'])

    def test_sequences_incarnations_replays_and_binding_extra_fields_refuse(self):
        value = image()
        for options in ({'expected_sequence': 2, 'expected_source_sequence': 2},
                        {'expected_sequence': 3, 'expected_source_sequence': 1},
                        {'expected_sequence': True, 'expected_source_sequence': 2}):
            with self.subTest(options=options), self.assertRaises(ValueError):
                codec.validate_observation2(value, binding=self.binding, **options)
        for key, replacement in (('launch_nonce', '9' * 64), ('worker_pid', 301), ('worker_birth', 401), ('version', True)):
            with self.subTest(key=key), self.assertRaises(ValueError): self.validate({**value, key: replacement})
        with self.assertRaises(ValueError): self.validate(value, {**self.binding, 'authorized': True})
        value = offer(); value.update(sequence=2, source_sequence=2)
        with self.assertRaises(ValueError): self.validate(value)

    def test_worker_trial_and_operation_preserve_raw_unicode_crlf_null_and_float(self):
        event = {'type': 'usage', 'content': 'Tiếng Việt 😀 "quoted"\r\n\x00', 'usage': None, 'ratio': 0.25}
        for kind in ('trial', 'operation'):
            binding = codec.observation_binding(offer(), kind=kind, receipt=receipt(kind))
            value = packet({'type': 'engine_event', **binding['identity'], 'event': event}, sequence=7, source='worker', source_sequence=3)
            options = {'binding': binding, 'expected_sequence': 7, 'expected_source_sequence': 3}
            raw = codec.encode_observation2(value, **options)
            self.assertEqual(raw, canonical(value)); self.assertFalse(raw.startswith(b'\x00'))
            self.assertEqual(codec.decode_observation2(raw, **options), value)
            self.assertEqual(codec.decode_observation2(raw, **options)['body']['event'], event)

    def test_no_cross_source_phase_order_is_invented(self):
        self.validate(image())
        value = packet({'type': 'endpoints_adopted'}, sequence=4, source='worker', source_sequence=1)
        self.assertEqual(self.validate(value), value)
        value = packet({'type': 'dispatch_observed', 'purpose': 'query', 'nonce': '5' * 64,
            'native_pid': 500, 'native_birth': 600, 'dispatch': {'basis': 'query_argument_consistency'},
            'dispatch_hash': hashlib.sha256(canonical({'basis': 'query_argument_consistency'})).hexdigest()},
            sequence=5, source='worker', source_sequence=2)
        self.assertEqual(self.validate(value), value)

    def test_guardian_sealed_and_drained_have_exact_terminal_literals(self):
        sealed = packet({'type': 'stdio_sealed', 'all_data_pipes_closed': True}, sequence=2, source_sequence=2)
        self.assertEqual(self.validate(sealed), sealed)
        body = {'type': 'drained', 'root_terminal': True, 'debug_exit': True, 'job_active': 0,
                'guards_closed': True, 'reason': 'completed'}
        value = packet(body, sequence=8, source_sequence=4); self.validate(value)
        for key, replacement in (('root_terminal', 1), ('debug_exit', False), ('job_active', False),
                                  ('guards_closed', 'true'), ('reason', 'assumed')):
            broken = copy.deepcopy(value); broken['body'][key] = replacement
            with self.subTest(key=key), self.assertRaises(ValueError): self.validate(broken)

    def test_v1_mixed_source_bodies_and_foreign_worker_identity_refuse(self):
        for value in (packet({'version': 1, 'type': 'worker_ready'}, source='worker', sequence=2),
                packet({'type': 'image_authorize'}, sequence=2, source_sequence=2),
                packet({'type': 'endpoints_adopted'}, sequence=2, source_sequence=2),
                packet({'type': 'engine_event', **self.binding['identity'], 'trial_id': 'foreign',
                        'event': {'type': 'usage'}}, source='worker', sequence=2)):
            with self.subTest(value=value), self.assertRaises(ValueError): self.validate(value)

    def test_inputs_and_all_returned_bindings_and_packets_are_defensive(self):
        first, identity = offer(), receipt()
        binding = codec.observation_binding(first, kind='trial', receipt=identity)
        first['body']['images'].clear(); identity['trial_id'] = 'mutated'
        self.assertEqual(binding['identity']['trial_id'], 'trial-a'); self.assertEqual(len(binding['invocations']), 4)
        value = image(); validated = self.validate(value)
        validated['body']['comparison']['selected'].clear()
        self.assertEqual(value, image()); self.assertEqual(self.binding['invocations'], invocations())

    def test_canonical_parser_duplicate_builtin_depth_nodes_and_size_limits(self):
        options = {'binding': self.binding, 'expected_sequence': 1, 'expected_source_sequence': 1}
        raw = canonical(offer())
        invalid = [b' ' + raw, raw + b'\n', raw[:-1] + b',"version":2}', raw.replace(b'"bootstrap_count":1', b'"bootstrap_count":1.0'),
            b'{"x":' + b'[' * 34 + b'0' + b']' * 34 + b'}', b'x' * (8 * 1024 * 1024 + 1), b'\xff', b'NaN']
        for data in invalid:
            with self.subTest(prefix=data[:20]), self.assertRaises(ValueError): codec.decode_observation2(data, **options)
        class Integer(int): pass
        for extra in (Integer(2), object(), float('nan'), '\ud800', [None] * 131073):
            value = packet({'type': 'engine_event', **self.binding['identity'], 'event': {'type': 'usage', 'extra': extra}},
                           sequence=2, source='worker')
            with self.subTest(extra=type(extra)), self.assertRaises(ValueError): self.validate(value)

    def test_import_closure_is_only_pure_protocol_and_stdlib(self):
        self.assertNotIn('improvement_native_transport', sys.modules)
        self.assertNotIn('claude_agent_sdk', sys.modules)
        self.assertNotIn('sqlite3', sys.modules)


if __name__ == '__main__': unittest.main()
