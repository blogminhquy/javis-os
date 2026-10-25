"""Pure v4 identity; fixture shapes are never grants, Trial rows or readiness."""
from _paths import ROOT, SERVER  # noqa: F401

import copy
import importlib
import importlib.util
import unittest

import improvement_store as IM
from improvement_experiment_protocol import validate_request_v2, logical_key_v2


def request(variant='baseline'):
    engine = {'version': 1, 'provider': 'anthropic-cli', 'engine_id': 'claude-sdk', 'model': 'shape-only-model',
        'reasoning': 'medium', 'cli_path': 'C:/synthetic/never.exe', 'cli_hash': 'a' * 64,
        'cli_version': 'shape-only', 'sdk_version': 'shape-only', 'profile_version': 'shape-only', 'profile_hash': 'b' * 64}
    return {'version': 4, 'pins': {'experiment_id': 'view_experiment', 'base_bundle_hash': 'c' * 64,
        'candidate_bundle_hash': 'd' * 64, 'contract_hash': 'e' * 64, 'case_set_hash': 'f' * 64,
        'engine_config_hash': IM._hash(engine), 'grant_hash': '0' * 64, 'scope_hash': '1' * 64, 'policy_version': 0},
        'case_set_id': 'view_cases', 'case_id': 'case_tuning', 'variant': variant, 'repeat': 1,
        'engine_config': engine, 'baseline_context_hash': '2' * 64, 'target_generations': {'view_target': 1},
        'deadline_at': 2_000_000_000.0, 'lineage': {'version': 1, 'context_id': 'view_context',
            'definition_hash': '3' * 64, 'comparison_id': 'view_comparison', 'comparison_hash': '4' * 64,
            'matrix_hash': '5' * 64, 'arm_ordinal': 1, 'arm_hash': 'd' * 64, 'candidate_id': 'view_candidate',
            'pair_id': '6' * 64, 'cell_position': 0 if variant == 'baseline' else 1},
        'view': {'view_id': 'view_' + variant, 'view_hash': ('7' if variant == 'baseline' else '8') * 64,
            'binding_hash': '9' * 64}}


class ViewTrialProtocolTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('improvement_view_trial_protocol'), 'Explicit v4 trial protocol is absent')
        self.protocol = importlib.import_module('improvement_view_trial_protocol')

    def reject(self, value):
        with self.assertRaises((ValueError, TypeError)):
            self.protocol.validate_request_v4(value)

    def test_exact_full_v4_normalization_preserves_both_variants_without_aliasing(self):
        for variant in ('baseline', 'candidate'):
            value = request(variant)
            before = copy.deepcopy(value)
            normalized = self.protocol.validate_request_v4(value)
            self.assertEqual(normalized, before)
            self.assertEqual(normalized['version'], 4)
            normalized['view']['view_hash'] = '0' * 64
            self.assertEqual(value, before)

    def test_closed_view_and_root_fields_never_accept_readiness_or_approval_flags(self):
        for field in ('allow_unknown', 'owner_approved', 'candidate_ready', 'native_ready', 'trial_id'):
            self.reject({**request(), field: True})
            value = request()
            value['view'][field] = True
            self.reject(value)
        for field in ('view_id', 'view_hash', 'binding_hash'):
            value = request()
            del value['view'][field]
            self.reject(value)
        value = request()
        del value['view']
        self.reject(value)

    def test_view_ids_and_hashes_are_exact_bounded_values(self):
        for bad in ('../view', '', None, True, 'v' * 129):
            value = request()
            value['view']['view_id'] = bad
            self.reject(value)
        for field in ('view_hash', 'binding_hash'):
            for bad in ('A' * 64, 'a' * 63, None, True):
                value = request()
                value['view'][field] = bad
                self.reject(value)

    def test_shared_pins_types_and_lineage_keep_existing_exact_validation(self):
        for changes in ({'version': True}, {'version': 2}, {'version': 3}, {'repeat': True}, {'variant': 'live'},
                {'deadline_at': float('inf')}, {'deadline_at': True}):
            self.reject({**request(), **changes})
        for changes in ({'cell_position': 4000}, {'cell_position': True}, {'arm_ordinal': 4}, {'arm_hash': 'a' * 64}):
            value = request()
            value['lineage'].update(changes)
            self.reject(value)

    def test_v4_logical_identity_cannot_collide_with_v2_or_changed_view_binding(self):
        value = request()
        projected = {key: child for key, child in value.items() if key != 'view'} | {'version': 2}
        expected = self.protocol.logical_key_v4(value)
        self.assertNotEqual(expected, logical_key_v2(projected))
        for changes in ({'view_id': 'different_view'}, {'view_hash': 'a' * 64}, {'binding_hash': 'b' * 64}):
            changed = copy.deepcopy(value)
            changed['view'].update(changes)
            self.assertNotEqual(expected, self.protocol.logical_key_v4(changed))
        self.assertNotEqual(expected, self.protocol.logical_key_v4(request('candidate')))
        later = {**value, 'deadline_at': value['deadline_at'] + 1}
        self.assertEqual(expected, self.protocol.logical_key_v4(later))
        self.assertNotEqual(IM._hash(value), IM._hash(later))

    def test_qualification_identity_is_shape_only_and_v2_does_not_accept_v4(self):
        value = {**request('candidate'), 'qualification_id': 'qualified_shape_only'}
        self.assertEqual(self.protocol.validate_request_v4(value), value)
        with self.assertRaises(ValueError):
            validate_request_v2(value)
        projected = {key: child for key, child in value.items() if key != 'view'} | {'version': 2}
        self.assertEqual(validate_request_v2(projected), projected)
        self.reject({**value, 'qualification_id': True})


if __name__ == '__main__':
    unittest.main()
