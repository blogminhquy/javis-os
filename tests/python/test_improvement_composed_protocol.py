"""Closed compose-arm transport and real paired arithmetic, no host authority."""
from _paths import ROOT, SERVER  # noqa: F401

import copy
import unittest

import improvement_experiment_protocol as P
from improvement_comparison_results import aggregate
from improvement_experiment_requests import validate
from improvement_trial_requests import TrialRequestError
from improvement_view_protocol import view_manifest
from improvement_view_trial_protocol import validate_request_v4
import test_improvement_comparison_results as arithmetic
from test_improvement_experiment_protocol import request_v2
from test_improvement_views import manifest


class ComposedProtocolTests(unittest.TestCase):
    def accept(self, function, *arguments):
        try:
            return function(*arguments)
        except (ValueError, TrialRequestError) as error:
            self.fail('Closed reserved compose-arm input is refused: ' + str(error))

    def test_actual_owner_request_validator_accepts_only_explicit_create_policy_and_bounded_ordinals(self):
        old = {'experiment_id': 'experiment', 'contract_id': 'contract', 'case_set_id': 'cases',
            'base_bundle_id': 'bundle', 'expected_context_generation': 1, 'repeat_policy': 'pilot',
            'timeout_seconds': 120, 'event_key': 'explicit-compose-budget'}
        self.assertEqual(validate(old, 'create'), old)
        request = {**old, 'candidate_policy': 'two_proposals_and_one_compose'}
        accepted = self.accept(validate, request, 'create')
        self.assertEqual(accepted, request)
        for extra in ({'candidate_policy': True}, {'candidate_policy': 'three_proposals'},
                      {'multiple_tests': 3}, {'native_ready': True}):
            with self.subTest(extra=extra), self.assertRaises(TrialRequestError):
                validate({**request, **extra}, 'create')
        for operation, fields in (
                ('freeze', {'kind': 'tuning'}), ('freeze', {'kind': 'final'}), ('select', {'choice': 'candidate'})):
            value = {**fields, 'ordinal': 3, 'expected_generation': 2, 'event_key': 'explicit-third-arm-wire'}
            self.assertEqual(self.accept(validate, value, operation), value)
            for bad in (True, 0, 4, 3.0):
                with self.subTest(operation=operation, bad=bad), self.assertRaises(TrialRequestError):
                    validate({**value, 'ordinal': bad}, operation)

    def test_matrix_requires_reserved_budget_for_three_and_keeps_complete_independent_pairs(self):
        definition = arithmetic.dataset()[0]
        with self.assertRaises(ValueError):
            P.comparison_matrix(definition, 'c' * 64, 3, 'tuning', ['case-a', 'case-b'], 812)
        definition['decision_policy']['multiple_tests'] = 3
        matrices = []
        for ordinal in (1, 2, 3):
            matrix = self.accept(P.comparison_matrix, definition, 'c' * 64, ordinal, 'tuning', ['case-a', 'case-b'], 812)
            cells = [P.matrix_cell(matrix, position) for position in range(8)]
            self.assertEqual({(cell['case_id'], cell['repeat'], cell['variant']) for cell in cells},
                {(case, repeat, variant) for case in ('case-a', 'case-b') for repeat in (1, 2)
                 for variant in ('baseline', 'candidate')})
            matrices.append(matrix)
        self.assertEqual(len({matrix['schedule_seed'] for matrix in matrices}), 3)
        self.assertEqual(len({pair['pair_id'] for matrix in matrices for pair in matrix['pairs']}), 12)
        for bad in (True, 0, 4, 3.0):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                P.comparison_matrix(definition, 'c' * 64, bad, 'tuning', ['case-a'], 812)

    def test_new_trial_and_manifest_shape_retains_typed_three_without_readiness_fields(self):
        request = request_v2()
        request['lineage']['arm_ordinal'] = 3
        normalized = self.accept(P.validate_request_v2, request)
        self.assertEqual(normalized['lineage']['arm_ordinal'], 3)
        request4 = {**request, 'version': 4,
            'view': {'view_id': 'view-composed', 'view_hash': 'a' * 64, 'binding_hash': 'b' * 64}}
        self.assertEqual(self.accept(validate_request_v4, request4)['lineage']['arm_ordinal'], 3)
        value = {**manifest('candidate'), 'arm_ordinal': 3}
        self.assertEqual(self.accept(view_manifest, value)['assets'][0]['content_hash'], 'c' * 64)
        for bad in (True, 0, 4, 3.0):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                P.validate_lineage({**request['lineage'], 'arm_ordinal': bad})
            with self.subTest(manifest_bad=bad), self.assertRaises(ValueError):
                view_manifest({**value, 'arm_ordinal': bad})
        with self.assertRaises(ValueError):
            view_manifest({**value, 'native_ready': True})

    def test_reserved_three_applies_actual_corrected_threshold_to_every_arm(self):
        original = arithmetic.dataset(qualification=20, wins=8)
        arithmetic.ComparisonArithmeticTests.change(original, 'qualification-8', 'candidate', criterion='content', verdict='fail')
        two = aggregate(*original)
        self.assertEqual(two['statistics']['tail_numerator'], '10')
        self.assertEqual(two['statistics']['tail_denominator'], '512')
        self.assertEqual(two['statistics']['threshold_denominator'], 40)
        self.assertIs(two['statistics']['significant'], True)
        self.assertIs(two['pilot']['numeric_gate'], True)
        self.assertEqual(two['mechanical_verdict'], 'eligible')
        value, _, contract, cases, _ = original
        selected = [case['id'] for case in cases['cases'] if case['split'] in ('qualification', 'regression')]
        value = copy.deepcopy(value)
        value['decision_policy']['multiple_tests'] = 3
        for ordinal in (1, 2, 3):
            matrix = self.accept(P.comparison_matrix, value, 'c' * 64, ordinal, 'final', selected, cases['seed'])
            evidence = []
            for position in range(2 * len(matrix['pairs'])):
                cell = P.matrix_cell(matrix, position)
                criterion = 'pass'
                if cell['case_id'].startswith('qualification-'):
                    index = int(cell['case_id'].rsplit('-', 1)[1])
                    if (index < 8 and cell['variant'] == 'baseline') or (index == 8 and cell['variant'] == 'candidate'):
                        criterion = 'fail'
                evidence.append({'position': position, 'integrity': 'pass',
                    'criteria': {'shape': 'pass', 'protected': 'pass', 'content': criterion}})
            result = aggregate(value, matrix, contract, cases, evidence)
            self.assertEqual(result['outcomes']['qualification'], {'win': 8, 'loss': 1, 'tie': 11, 'unknown': 0})
            self.assertEqual(result['statistics']['tail_numerator'], '10')
            self.assertEqual(result['statistics']['tail_denominator'], '512')
            self.assertEqual(result['statistics']['threshold_denominator'], 60)
            self.assertIs(result['statistics']['significant'], False)
            self.assertIs(result['pilot']['numeric_gate'], False)
            self.assertEqual(result['mechanical_verdict'], 'inconclusive')
            self.assertEqual(result['business_eligibility'], 'unverified')


if __name__ == '__main__':
    unittest.main()
