"""Actual owned compose publication, with explicitly synthetic storage controls.

Positive cases use real consent/Records/Execution/Runner/Tasks/Profile/evidence/
Results/M0/Fernet/candidate readers. The two-arm fixture's completed cells, the
fake adapter's native packets, verifier availability, format2 selector and narrow
profile_qualification predicate are UNEXECUTED STORAGE CONTROLS. They prove no
actual CLI, image ACK, account/model/config readiness or business improvement.
The default UNKNOWN qualification case uses the same complete workflow without
that predicate and must publish no composition. No product/read gate is bypassed.
"""
from _paths import ROOT, SERVER  # noqa: F401

import asyncio
import copy
import importlib
import importlib.util
import json
import time
import unittest
from contextlib import closing
from types import SimpleNamespace
from unittest.mock import patch

import improvement_store as IM
from improvement_native_decisions import NativeImageDecisionStore, attempt_scope
from improvement_native_trace_checks import validate_native_trace
from improvement_operation_adapter import ClaudeOperationAdapter
from improvement_operation_profile import OperationProfile
from improvement_operation_runner import OperationRunner
from improvement_operation_tasks import OperationTasks
import usage_index as UI
import usage_store as US
import test_improvement_compose_admission as admission
import test_improvement_native_trace_checks as N
from test_improvement_operation_profile2 import EngineeringOperationBinding


class CompositionTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        # This assertion deliberately precedes all private DB/source fixtures.
        self.assertIsNotNone(importlib.util.find_spec('improvement_compositions'),
                             'Actual owned ComposerService publication is absent')
        self.module = importlib.import_module('improvement_compositions')
        self.services = []
        self.addAsyncCleanup(self.close_services)
        self.new_fixture()

    async def close_services(self):
        for service in reversed(self.services):
            await service.close()

    def new_fixture(self):
        self.f = admission.ComposeAdmissionTests()
        self.f.setUp()
        self.addCleanup(lambda fixture=self.f: self.assertTrue(fixture.doCleanups(), 'Actual owner fixture cleanup failed'))
        self.owner, self.assets, self.store, self.execution = self.f.owner, self.f.assets, self.f.store, self.f.execution
        self.saved, self.permissions = self.f.saved, self.f.f.service
        with closing(self.store._conn()) as connection:
            self.data = json.loads(self.assets.blobs.read(self.owner.brain_id, self.saved['input_hash']))
        self.pin = copy.deepcopy(self.f.f.f.host_files.engine)
        self.queries, self.adapter_closes, self.receipts = 0, 0, []
        self.raw = json.dumps(self.output(keep=True), ensure_ascii=False)
        root = self.store.path.parent
        # Actual usage recorder, redirected to this actual isolated fixture only.
        for obj, key, value in ((US, '_PATH', root / 'compose-usage.json'),
                (US, '_EVENTS_PATH', root / 'compose-usage.jsonl'), (US, '_TELEMETRY_ERRORS', {}),
                (UI, '_EVENTS_PATH', root / 'compose-usage.jsonl'), (UI, 'DB_PATH', root / 'compose-usage.db'),
                (UI, '_claude_dir', lambda: str(root / 'empty-claude')),
                (UI, '_codex_dir', lambda: str(root / 'empty-codex'))):
            self.enterContext(patch.object(obj, key, value))

    def output(self, *, keep=False):
        decisions = []
        for candidate in self.data['candidates']:
            group = next(group for group in self.data['tuning'] if group['variant'] == candidate['candidate_id'])
            observation = group['observations'][0]
            decisions.append({'candidate_id': candidate['candidate_id'], 'target_id': self.data['baseline']['target_id'],
                'status': 'dropped' if keep else 'revised', 'reason': 'Synthetic unexecuted composition hypothesis.',
                'observations': [{key: observation[key] for key in ('ref', 'location')}]})
        value = {'version': 1, 'kind': 'keep_base' if keep else 'compose', 'decisions': decisions}
        if not keep:
            patch_value = copy.deepcopy(self.data['candidates'][0]['patch'])
            patch_value.update(replacement='Retain owner rules.\nCheck every subtotal against its controlling source.\n',
                               evidence_refs=[copy.deepcopy(self.data['tuning'][0]['observations'][0]['ref'])])
            value['patch'] = patch_value
        return value

    def adapter(self, pin, *, workspace, before_engine_start):
        test = self
        test.assertEqual(pin, self.pin)
        class SyntheticAdapter:
            def verify(self):
                return {'supported': True, 'capability_hash': 'c' * 64}

            async def execute(self, request, receipt, *, on_closing_observations=None):
                from claude_agent_sdk import AssistantMessage, ResultMessage, SystemMessage
                manifest = workspace.validate(receipt)
                test.assertEqual(manifest['version'], 2)
                test.assertEqual(manifest['request']['kind'], 'compose')
                test.assertTrue(callable(on_closing_observations))
                test.receipts.append(copy.deepcopy(receipt))
                profile = OperationProfile(pin, workspace, receipt, 'c' * 64, before_query=before_engine_start)
                with patch('improvement_native_profile.NativeProfileBinding', EngineeringOperationBinding):
                    profile.bind_native_runtime(object(), environment={'engineering': 'unexecuted binding seam only'})
                profile.options(SimpleNamespace(cwd=receipt['path'], session_id=None, _on_stderr=lambda _: None))
                # Existing actual owner records the accounting marker. This is
                # not an actual native ACK or SDKClient/provider invocation.
                await profile.before_query()
                test.queries += 1
                try:
                    provisional = N.trace('operation', receipt, pin, system_prompt=profile.system_prompt)
                    profile._native_binding.delivery = N.delivery('operation', receipt, provisional,
                        profile.user_prompt(), manifest['request']['input_hash'])
                    events = profile.observe(SystemMessage('init', {'session_id': 'synthetic-compose-storage', 'tools': N.TOOLS[:1]}))
                    events += profile.observe(AssistantMessage([], model=pin['model'], session_id='synthetic-compose-storage'))
                    events += profile.observe(ResultMessage('success', 1, 1, False, 1, 'synthetic-compose-storage', result=test.raw))
                    packets = N.trace('operation', receipt, pin, events, profile.system_prompt)
                    next(p['body'] for p in packets if p['body']['type'] == 'worker_ready')['capability_hash'] = 'c' * 64
                    validated = validate_native_trace(packets, kind='operation', receipt=receipt, pin=pin,
                        capability_hash='c' * 64, system_prompt=profile.system_prompt, user_prompt=profile.user_prompt(),
                        data_hash=manifest['request']['input_hash'])
                    scope = attempt_scope(kind='operation', brain_id=test.owner.brain_id, receipt=receipt,
                                          config_pin=pin, capability_hash='c' * 64)
                    def current(connection, joined):
                        row = test.execution._row(connection, test.owner, receipt['operation_id'])
                        attempt = test.execution._attempt(connection, row)
                        test.execution._leased(connection, test.owner, row['id'], row['generation'],
                                               attempt['lease_token'], time.time())
                        test.execution._current(connection, test.owner, row)
                        return 'allow'
                    decisions = NativeImageDecisionStore(test.assets)
                    for joined in validated['joins']:
                        decisions.persist(test.owner, joined, scope_hash=scope, current=current)
                    for packet in packets:
                        yield packet
                    # Exercise the real closing callback without fabricating a
                    # second copy of any packet already delivered to the runner.
                    await on_closing_observations(())
                finally:
                    test.adapter_closes += 1
        return SyntheticAdapter()

    def service(self, *, qualified_storage=True, format2=True):
        if format2:
            self.enterContext(patch('improvement_native_formats.input_version', return_value=2))
        self.enterContext(patch.object(ClaudeOperationAdapter, 'verify',
            return_value={'supported': True, 'capability_hash': 'c' * 64}))
        if qualified_storage:
            # Narrow deterministic predicate only. No actual registry entry,
            # capability mutation, observer substitution or product bypass.
            def storage_qualification(pin, platform):
                self.assertEqual(pin, self.pin)
                self.assertIn(platform, ('win32', 'linux', 'darwin'))
                return 'f' * 64
            self.enterContext(patch('improvement_native_qualifications.profile_qualification', side_effect=storage_qualification))
        runner = OperationRunner(self.execution, adapter_factory=self.adapter)
        tasks = OperationTasks(self.execution, runner)
        service = self.module.ComposerService(self.execution, tasks)
        self.services.append(service)
        return service

    async def compose(self, service, *, key='owner-compose-publication', owner=None, authorization=None):
        return await service.compose(self.owner if owner is None else owner,
            self.saved['authorization_id'] if authorization is None else authorization,
            expected_generation=self.saved['experiment_generation'], event_key=key)

    def rows(self, table):
        return self.f.f.rows(table)

    def assert_no_composition(self):
        self.assertEqual(self.rows('improvement_compositions'), [])
        self.assertEqual([row['ordinal'] for row in self.rows('improvement_skill_candidates')], [1, 2])

    async def test_false_verification_legacy_format_foreign_owner_and_off_refuse_before_operation_or_call(self):
        service = self.service(format2=False)
        with patch.object(ClaudeOperationAdapter, 'verify', side_effect=AssertionError('Legacy format reached verifier')):
            with self.assertRaisesRegex(ValueError, 'compose_native_input2_required'):
                await self.compose(service, key='compose-legacy-format-refused')
        with patch('improvement_native_formats.input_version', return_value=2):
            with patch.object(ClaudeOperationAdapter, 'verify', return_value={'supported': False}):
                with self.assertRaisesRegex(ValueError, 'operation_native_unavailable'):
                    await self.compose(service, key='compose-false-verification-refused')
            with self.assertRaises(admission.DENIED):
                await self.compose(service, key='compose-foreign-refused', owner=self.f.f.f.host_files.other)
            self.assets.set_policy(self.owner, 'off', expected_version=0, event_key='compose-disabled-before-admission')
            with patch.object(ClaudeOperationAdapter, 'verify', side_effect=AssertionError('Off reached verifier')):
                with self.assertRaises(admission.DENIED):
                    await self.compose(service, key='compose-off-refused')
        self.assertEqual(self.rows('improvement_operations'), [])
        self.assertEqual(self.queries, 0)
        self.f.assert_no_new_call()
        self.assert_no_composition()

    async def test_default_unknown_native_qualification_refuses_full_workflow_publication(self):
        service = self.service(qualified_storage=False)
        try:
            result = await self.compose(service)
        except admission.DENIED:
            result = None
        if result is not None:
            self.assertEqual(result['status'], 'native_incomplete', result)
        operations = self.rows('improvement_operations')
        self.assertEqual(len(operations), 1)
        self.assertEqual(operations[0]['status'], 'completed')
        report = service.products.read(self.owner, operations[0]['id'], 1)
        self.assertEqual(report['version'], 2)
        self.assertEqual(next(row['verdict'] for row in report['checks'] if row['id'] == 'native_qualification'), 'unknown')
        self.assertEqual(self.queries, 1)
        self.assert_no_composition()

    async def test_actual_one_shot_keep_base_cold_replay_and_new_event_cannot_compose_again(self):
        service = self.service()
        baseline = self.f.f.f.host_files.skill.read_bytes()
        result = await self.compose(service)
        self.assertEqual(result['status'], 'keep_base', result)
        self.assertEqual(result['candidates'], [])
        self.assertIs(result['business_proof'], False)
        composition, = self.rows('improvement_compositions')
        self.assertEqual(composition['id'], result['composition_id'])
        self.assertEqual(composition['outcome'], 'keep_base')
        self.assertIsNone(composition['candidate_id'])
        self.assertEqual(self.queries, 1)
        self.assertEqual(self.adapter_closes, 1)
        self.assertEqual(self.f.f.f.host_files.skill.read_bytes(), baseline)
        self.assertEqual(len(self.rows('improvement_operations')), 1)
        self.assets.set_policy(self.owner, 'off', expected_version=0, event_key='compose-off-after-published-outcome')
        # New service over the same actual tasks/execution proves durable cold
        # replay rather than relying on the first service's in-memory join.
        cold = self.module.ComposerService(self.execution, service.tasks)
        self.services.append(cold)
        with patch.object(self.assets.blobs, 'read', side_effect=AssertionError('Cold replay must not decrypt')):
            self.assertEqual(await self.compose(cold), result)
        self.assertEqual(self.queries, 1)
        with self.assertRaises(admission.DENIED):
            await self.compose(service, key='compose-second-event-is-not-new-consent')
        self.assertEqual(len(self.rows('improvement_compositions')), 1)

    async def test_actual_candidate_three_has_typed_v2_provenance_without_edit_or_semantic_authority(self):
        service = self.service()
        self.raw = json.dumps(self.output(), ensure_ascii=False)
        baseline = self.f.f.f.host_files.skill.read_bytes()
        result = await self.compose(service)
        self.assertEqual(result['status'], 'candidate_staged', result)
        self.assertEqual(len(result['candidates']), 1)
        self.assertFalse(result['business_proof'])
        candidates = self.rows('improvement_skill_candidates')
        self.assertEqual([row['ordinal'] for row in candidates], [1, 2, 3])
        candidate = candidates[-1]
        self.assertEqual(candidate['id'], result['candidates'][0]['candidate_id'])
        self.assertEqual(candidate['semantic_status'], 'unreviewed')
        self.assertIsNone(candidate['authority_id'])
        self.assertIsNone(candidate['authority_generation'])
        composition, = self.rows('improvement_compositions')
        for key, expected in {'authorization_id': self.saved['authorization_id'], 'input_hash': self.saved['input_hash'],
                              'basis_hash': self.saved['basis_hash'], 'candidate_id': candidate['id'], 'outcome': 'candidate'}.items():
            self.assertEqual(composition[key], expected)
        actual_report = service.products.read(self.owner, result['operation_id'], 1)
        self.assertEqual(actual_report['version'], 2)
        checks = {row['id']: row['verdict'] for row in actual_report['checks']}
        self.assertEqual(checks['native_qualification'], 'pass', 'Explicit synthetic qualification predicate only')
        self.assertEqual(checks['actual_reasoning'], 'unknown')
        self.assertEqual(checks['actual_input_use'], 'unknown')
        self.assertEqual(service.products.artifact(self.owner, result['operation_id'], 1).decode(), self.raw)
        with closing(self.store._conn()) as connection:
            result_row = connection.execute('SELECT * FROM improvement_operation_results WHERE id=?', (composition['result_id'],)).fetchone()
            self.assertEqual(composition['output_hash'], result_row['blob_hash'], 'Output link names the report, not raw artifact')
            authoring = self.execution.plans.authoring
            state = authoring._state(connection, self.owner, candidate['experiment_id'], candidate['target_id'],
                                     candidate['base_revision_id'], candidate['base_hash'])
            observed, raw = authoring.observe(self.owner, state['target'])
            proposal = authoring.read_proposal(connection, self.owner, candidate, state, observed, raw)
        provenance = proposal['provenance']
        self.assertEqual(provenance['version'], 2)
        self.assertEqual(provenance['composition_id'], composition['id'])
        self.assertIsNone(provenance['owner_request_event'])
        self.assertEqual(provenance['dependency_status'], 'unresolved')
        self.assertEqual(proposal['patch'], self.output()['patch'])
        self.assertEqual(self.f.f.f.host_files.skill.read_bytes(), baseline)
        self.assertEqual((self.queries, self.adapter_closes), (1, 1))
        self.assertEqual(len(self.rows('improvement_generated_candidates')), 0, 'Compose is not a forged third proposal')

    async def test_malformed_output_has_no_repair_second_compose_or_partial_candidate(self):
        service = self.service()
        self.raw = '```json\n{"version":1,"kind":"compose"}\n```'
        result = await self.compose(service)
        self.assertEqual(result['status'], 'invalid_output', result)
        self.assertEqual(result['candidates'], [])
        self.assertEqual(self.queries, 1)
        self.assertEqual([row['kind'] for row in self.rows('improvement_operations')], ['compose'])
        self.assert_no_composition()
        self.assertEqual(await self.compose(service), result)
        with self.assertRaises(admission.DENIED):
            await self.compose(service, key='invalid-compose-cannot-resample')
        self.assertEqual(self.queries, 1)

    async def test_revoke_pending_before_verification_cannot_create_or_restore_a_compose(self):
        service = self.service()
        self.permissions.revoke(self.owner, self.saved['authorization_id'], expected_generation=1,
                                event_key='compose-consent-revoked-before-service')
        with patch.object(ClaudeOperationAdapter, 'verify', side_effect=AssertionError('Revoked consent reached verifier')):
            with self.assertRaises(admission.DENIED):
                await self.compose(service)
        self.assertEqual(self.rows('improvement_operations'), [])
        self.assertEqual(self.queries, 0)
        self.f.assert_no_new_call()
        self.assert_no_composition()

    async def test_late_grant_source_domain_or_actual_product_drift_rolls_back_publication(self):
        for index, control in enumerate(('grant', 'source', 'domain', 'product')):
            with self.subTest(control=control):
                if index:
                    self.new_fixture()
                service = self.service()
                self.raw = json.dumps(self.output(), ensure_ascii=False)
                original = service._product_fence
                protected = self.f.f.f.host_files.protected
                original_bytes, changed = protected.read_bytes(), []
                def late(connection, principal, product):
                    result = original(connection, principal, product)
                    if changed:
                        return result
                    changed.append(control)
                    if control == 'grant':
                        connection.execute("UPDATE improvement_compose_grants SET status='revoked',generation=2,revoked_at=? WHERE authorization_id=?",
                                           (time.time(), self.saved['authorization_id']))
                    elif control == 'source':
                        protected.write_bytes(original_bytes + b'\nLate protected owner-source refusal control.\n')
                    elif control == 'domain':
                        self.assets._event(connection, self.owner, 'native-qualification:' + 'a' * 64,
                            'native_qualification_session', {'run_hash': 'a' * 64}, {'unanchored_control_fixture': True})
                    else:
                        connection.execute("UPDATE agent_calls SET mirror_ref='foreign-compose-product' WHERE id=?", (product['call']['id'],))
                    return result
                try:
                    with patch.object(service, '_product_fence', side_effect=late), self.assertRaises(admission.DENIED):
                        await self.compose(service)
                    self.assertEqual(changed, [control], 'Control must reach the actual product/final-Tx boundary')
                    self.assertEqual(self.queries, 1)
                    self.assert_no_composition()
                    self.assertEqual(self.permissions.get(self.owner, self.saved['authorization_id'])['status'], 'active',
                                     'Injected SQL authority mutation must roll back with publication')
                    self.assertFalse(any(row['operation'] == 'native_qualification_session' for row in self.rows('improvement_events')))
                    self.assertNotIn('foreign-compose-product', [row['mirror_ref'] for row in self.rows('agent_calls')])
                finally:
                    protected.write_bytes(original_bytes)
                    await service.close()


if __name__ == '__main__':
    unittest.main()
