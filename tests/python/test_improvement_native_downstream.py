"""Actual downstream native contracts, engineering captures only; no CLI."""
from _paths import ROOT, SERVER  # noqa: F401

import copy
import unittest
from contextlib import closing
from unittest.mock import patch

import improvement_role_workflow as role
import improvement_view_sources as views
import improvement_improver_inputs as inputs
import improvement_semantic_review as semantic
import test_improvement_native_result_consumers as operation
import test_improvement_comparison_results as comparison
import test_improvement_view_sources as probe
import test_improvement_native_trace_checks as native

NATIVE = ('native_trace', 'native_authorization', 'native_qualification', 'native_input_delivery')


class NativeDownstreamChecksTests(unittest.TestCase):
    def role_report(self):
        return {'version': 2, 'checks': [{'id': key, 'verdict': 'pass'} for key in sorted(role._REQUIRED | role._UNOBSERVED)] +
            [{'id': key, 'verdict': 'pass'} for key in NATIVE]}

    def check_role(self, report):
        function = getattr(role, '_product_checks', None)
        self.assertTrue(callable(function), 'explicit role report format inventory missing')
        return function(report)

    def test_native_role_requires_exact_old10_and_four_new_passes(self):
        report = self.role_report()
        for row in report['checks']:
            if row['id'] in role._UNOBSERVED: row['verdict'] = 'unknown'
        self.check_role(report)
        for identifier in role._REQUIRED | set(NATIVE):
            for verdict in ('unknown', 'fail'):
                changed = copy.deepcopy(report)
                next(r for r in changed['checks'] if r['id'] == identifier)['verdict'] = verdict
                with self.subTest(identifier=identifier, verdict=verdict), self.assertRaises(PermissionError): self.check_role(changed)

    def test_role_legacy_inventory_stays_exact_and_unknown_versions_duplicates_or_extras_refuse(self):
        legacy = self.role_report(); legacy['version'] = 1; legacy['checks'] = legacy['checks'][:-4]
        self.check_role(legacy)
        for report in ({**legacy, 'version': True}, {**legacy, 'version': 3}, self.role_report() | {'checks': legacy['checks']},
                {**legacy, 'checks': legacy['checks'] + [legacy['checks'][0]]},
                {**legacy, 'checks': legacy['checks'] + [{'id': 'extra', 'verdict': 'pass'}]}):
            with self.subTest(report=report), self.assertRaises(PermissionError): self.check_role(report)

    def test_semantic_native14_preserves_two_observational_unknowns_and_rejects_new_gate_unknown(self):
        fixture = probe.ProbeObservationPolicyTests(); fixture.setUp()
        evidence = copy.deepcopy(fixture.evidence)
        evidence.update(native_result_version=2)
        evidence['native_checks'] += [{'id': key, 'verdict': 'pass', 'reason': 'native_records_checked'} for key in NATIVE]
        before = copy.deepcopy(evidence)
        self.assertEqual(views._probe_observations(evidence), ('actual_input_use', 'actual_reasoning'))
        self.assertEqual(evidence, before)
        for identifier in NATIVE:
            changed = copy.deepcopy(evidence)
            next(r for r in changed['native_checks'] if r['id'] == identifier)['verdict'] = 'unknown'
            with self.subTest(identifier=identifier), self.assertRaises(PermissionError): views._probe_observations(changed)
        with self.assertRaises(PermissionError): views._probe_observations({**evidence, 'native_result_version': True})
        changed = copy.deepcopy(evidence); changed.pop('native_result_version')
        with self.assertRaises(PermissionError): views._probe_observations(changed)

    def test_semantic_evidence_projection_binds_exact_actual_report_format_and_preserves_verdict(self):
        function = getattr(semantic, '_native_report_evidence', None)
        self.assertTrue(callable(function), 'semantic evidence lacks authenticated actual report format projection')
        report = self.role_report() | {'verdict': 'unknown'}
        value = function(report)
        self.assertEqual(value, {'native_result_version': 2, 'native_verdict': 'unknown', 'native_checks': report['checks']})
        report['version'] = 1; report['checks'] = report['checks'][:-4]
        self.assertEqual(function(report), {'native_verdict': 'unknown', 'native_checks': report['checks']})
        with self.assertRaises(PermissionError): function({**report, 'execution_domain': None})

    def test_native_comparison_keeps_all_old18_and_requires_all_four_native_gates(self):
        fixture = comparison.ResultProjectionTests()
        value = fixture.fixture(); report = value[3]
        report['native_decisions'] = [{'decision': 'allow', 'durable_evidence_hash': str(i + 1) * 64} for i in range(4)]
        report['mandatory'] += [{'id': key, 'verdict': 'pass'} for key in NATIVE]
        self.assertEqual(fixture.project(value)['integrity'], 'pass')
        self.assertEqual(len(report['mandatory']), 22)
        for index in range(22):
            changed = copy.deepcopy(value); changed[3]['mandatory'][index]['verdict'] = 'unknown'
            with self.subTest(index=index): self.assertEqual(fixture.project(changed)['integrity'], 'unknown')
        changed = copy.deepcopy(value); changed[3]['mandatory'].pop()
        self.assertEqual(fixture.project(changed)['integrity'], 'unknown')
        changed = copy.deepcopy(value); changed[3].pop('native_decisions')
        self.assertEqual(fixture.project(changed)['integrity'], 'unknown')

    def test_explicit_engineering_domain_never_becomes_comparison_role_or_improver_input(self):
        fixture = comparison.ResultProjectionTests()
        for domain in (None, {}, {'kind': 'qualification', 'run_hash': 'a' * 64}, 'production', False):
            report = self.role_report() | {'execution_domain': domain}
            with self.subTest(domain=domain), self.assertRaises(PermissionError): self.check_role(report)
            value = fixture.fixture(); value[3]['execution_domain'] = domain
            with self.subTest(domain=domain), self.assertRaises(PermissionError): fixture.project(value)
            with self.subTest(domain=domain), self.assertRaises(PermissionError): inputs._assessment({'execution_domain': domain})

    def test_native_trace_projection_keeps_source_sequences_and_withholds_guardian_control(self):
        packets = native.trace(events=[{'type': 'text', 'content': 'private reasoning should never be projected'},
            {'type': 'tool_call', 'id': 'call-1', 'name': 'mcp__fixture__fixture_read', 'input': {'private': 'payload'}}])
        before = copy.deepcopy(packets)
        projected = [inputs.project_packet(p) for p in packets]
        self.assertEqual(packets, before)
        for packet, result in zip(packets, projected):
            self.assertEqual(result['type'], 'native_observation2_projection')
            self.assertEqual(result['sequence'], packet['sequence'])
            self.assertEqual(result['source_sequence'], packet['source_sequence'])
            self.assertEqual(result['source'], packet['source'])
            if packet['source'] == 'guardian': self.assertEqual(result['observation']['type'], 'withheld')
        self.assertNotIn('private reasoning', str(projected)); self.assertNotIn('payload', str(projected))
        tool = next(r for r in projected if r['observation'].get('event', {}).get('type') == 'tool_call')
        self.assertEqual(tool['observation']['event'], {'type': 'tool_call', 'id': 'call-1', 'name': 'mcp__fixture__fixture_read'})
        self.assertEqual(inputs.project_packet({'type': 'engine_event', 'event': {'type': 'tool_call', 'id': 'old', 'name': 'fixture', 'input': {}}}),
            {'type': 'engine_event', 'event': {'type': 'tool_call', 'id': 'old', 'name': 'fixture'}})


class ActualNativeRoleProductTests(unittest.TestCase):
    def test_actual_encrypted_native_operation2_product_is_consumable_with_four_registered_engineering_gates(self):
        f = operation.NativeOperationResultTests(); f.setUp(); self.addCleanup(f.doCleanups)
        # Explicit engineering registration seam only, never native qualification.
        with patch('improvement_native_qualifications.profile_qualification', return_value='a' * 64):
            f.prepare_trace(); f.finish()
        class Workflow(role.RoleWorkflow): _product_kinds = frozenset(('propose',))
        subject = Workflow.__new__(Workflow)
        subject.execution, subject.plans = f.execution, f.execution.plans
        subject.assets, subject.store, subject.blobs = f.execution.assets, f.execution.store, f.execution.blobs
        subject.products = f.results
        with closing(f.execution.store._conn()) as connection:
            product = subject._product(connection, f.owner, f.identifier)
        self.assertEqual(product['raw'], f.content)
        self.assertEqual(product['report']['version'], 2)
        self.assertEqual(len(product['report']['checks']), 14)
        self.assertEqual(len(product['report']['native_decisions']), 4)


if __name__ == '__main__': unittest.main()
