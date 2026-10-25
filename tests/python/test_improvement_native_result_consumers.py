"""Actual encrypted SQLite result publication with synthetic native evidence."""
from _paths import ROOT, SERVER  # noqa: F401

import asyncio
import copy
import json
import unittest
from contextlib import closing
from types import SimpleNamespace
from unittest.mock import patch

import improvement_store as IM
from improvement_blobs import AssetUnavailable
from improvement_native_decisions import NativeImageDecisionStore, attempt_scope
from improvement_operation_evidence import OperationEvidence
from improvement_operation_profile import OperationProfile
from improvement_operation_results import OperationResults
import test_improvement_operation_execution as O
import test_improvement_operation_profile2 as B
import test_improvement_native_trace_checks as N


class NativeOperationResultTests(unittest.TestCase):
    def setUp(self):
        self.fixture = O.OperationExecutionTests(); self.fixture.setUp(); self.addCleanup(self.fixture.doCleanups)
        self.execution = self.fixture.execution(); original = self.execution.materialize
        # Explicit engineering input2, never an emitter upgrade in product code.
        self.enterContext(patch.object(self.execution, 'materialize', side_effect=lambda *a, **kw: {**original(*a, **kw), 'version': 2}))
        self.row, self.token, self.workspace = self.fixture.prepared(self.execution)
        self.owner, self.identifier = self.fixture.owner, self.row['operation_id']
        self.pin = self.execution.guard(self.owner, self.identifier)[1]['engine_config']
        self.manifest = self.execution.workspace.validate(self.workspace)
        self.evidence, self.results = OperationEvidence(self.execution), OperationResults(self.execution)
        async def before():
            self.row = self.execution.start_engine(self.owner, self.identifier,
                expected_generation=self.row['generation'], lease_token=self.token)
        self.profile = OperationProfile(self.pin, self.execution.workspace, self.workspace, 'c' * 64, before_query=before)
        with patch('improvement_native_profile.NativeProfileBinding', B.EngineeringOperationBinding):
            self.profile.bind_native_runtime(object(), environment={'engineering': 'binding seam only'})
        self.profile.options(SimpleNamespace(cwd=self.workspace['path'], session_id=None, _on_stderr=lambda _: None))
        asyncio.run(self.profile.before_query())

    def prepare_trace(self, *, denied=False, persist=True):
        from claude_agent_sdk import SystemMessage, AssistantMessage, ResultMessage
        provisional = N.trace('operation', self.workspace, self.pin, system_prompt=self.profile.system_prompt)
        self.profile._native_binding.delivery = N.delivery('operation', self.workspace, provisional,
            self.profile.user_prompt(), self.manifest['request']['input_hash'])
        self.content = '{"value":"日本語\\r\\n"}\r\n'
        events = self.profile.observe(SystemMessage('init', {'session_id': 'session-a', 'tools': N.TOOLS[:1]}))
        events += self.profile.observe(AssistantMessage([], model=self.pin['model'], session_id='session-a'))
        events += self.profile.observe(ResultMessage('success', 1, 1, False, 1, 'session-a', result=self.content))
        self.packets = N.trace('operation', self.workspace, self.pin, events, self.profile.system_prompt)
        next(p['body'] for p in self.packets if p['body']['type'] == 'worker_ready')['capability_hash'] = 'c' * 64
        self.scope = attempt_scope(kind='operation', brain_id=self.owner.brain_id, receipt=self.workspace,
            config_pin=self.pin, capability_hash='c' * 64)
        from improvement_native_trace_checks import validate_native_trace
        self.validated = validate_native_trace(self.packets, kind='operation', receipt=self.workspace, pin=self.pin,
            capability_hash='c' * 64, system_prompt=self.profile.system_prompt, user_prompt=self.profile.user_prompt(),
            data_hash=self.manifest['request']['input_hash'])
        if persist:
            decision_store = NativeImageDecisionStore(self.execution.assets)
            def current(connection, joined):
                self.execution._leased(connection, self.owner, self.identifier, self.row['generation'], self.token, __import__('time').time())
                return 'deny' if denied and joined['purpose'] == 'query' else 'allow'
            for joined in self.validated['joins']: decision_store.persist(self.owner, joined, scope_hash=self.scope, current=current)
        for packet in self.packets:
            self.evidence.append(self.owner, self.identifier, packet, expected_generation=self.row['generation'], lease_token=self.token)

    def finish(self):
        return self.results.finish(self.owner, self.identifier, expected_generation=self.row['generation'],
            lease_token=self.token, capability_hash='c' * 64)

    def test_actual_operation_result_consumes_drained_history_and_four_cold_durable_allows(self):
        self.prepare_trace(); finished = self.finish(); report = self.results.read(self.owner, self.identifier, 1)
        self.assertEqual(finished['status'], 'completed'); self.assertEqual(report['version'], 2)
        self.assertEqual(self.results.artifact(self.owner, self.identifier, 1).decode(), self.content)
        checks = {row['id']: row for row in report['checks']}
        for key in ('completion', 'installation', 'native_authorization', 'native_input_delivery'):
            self.assertEqual(checks[key]['verdict'], 'pass', checks)
        self.assertEqual(checks['actual_reasoning']['verdict'], 'unknown')
        self.assertEqual(checks['native_qualification']['verdict'], 'unknown')

    def test_missing_actual_durable_decision_refuses_publication_without_settling_call(self):
        self.prepare_trace(persist=False)
        with self.assertRaises(PermissionError): self.finish()
        self.assertEqual(self.execution.ledger.get(self.row['attempts'][-1]['call_id'])['status'], 'running')

    def test_denied_actual_durable_query_refuses_successful_publication(self):
        self.prepare_trace(denied=True)
        with self.assertRaises(PermissionError): self.finish()

    def test_final_transaction_rereads_actual_encrypted_decisions(self):
        self.prepare_trace(); original = self.execution.blobs.write; once = [False]
        def revoke_after_check(brain, raw):
            value = original(brain, raw)
            if b'"trace_hashes"' in raw and not once[0]:
                once[0] = True
                record = self.validated['joins'][-1]
                key = 'native-image:' + IM._hash([self.scope, record['launch_nonce'], 'query'])
                with self.execution.store._Tx(self.execution.store) as connection:
                    # Controlled SQL corruption outside the actual immutable owner.
                    connection.execute('DROP TRIGGER improvement_events_update')
                    row = connection.execute('SELECT result_json FROM improvement_events WHERE event_key=?', (key,)).fetchone()
                    data = json.loads(row[0]); data['decision'] = 'deny'
                    connection.execute('UPDATE improvement_events SET result_json=? WHERE event_key=?', (IM._json(data), key))
            return value
        with patch.object(self.execution.blobs, 'write', side_effect=revoke_after_check), self.assertRaises((PermissionError, AssetUnavailable, IM.ConflictError)):
            self.finish()
        self.assertTrue(once[0], 'control must reach the post-check publication boundary')

    def test_historical_read_is_cold_after_cleanup_but_still_authenticates_encrypted_history(self):
        self.prepare_trace(); self.finish()
        self.execution.workspace.cleanup_proven(self.identifier, 1, self.workspace)
        with patch.object(self.execution.host, '_snapshot_observe', side_effect=AssertionError('cold history cannot warm sources')):
            report = self.results.read(self.owner, self.identifier, 1)
        self.assertEqual(report['version'], 2)
        with closing(self.execution.store._conn()) as connection:
            record = connection.execute('SELECT blob_hashes_json FROM improvement_operation_observations WHERE operation_id=? ORDER BY sequence LIMIT 1',
                (self.identifier,)).fetchone()
        self.execution.blobs._path(self.owner.brain_id, json.loads(record[0])[0]).unlink()
        with self.assertRaises(AssetUnavailable): self.results.read(self.owner, self.identifier, 1)


class LegacyProductStreamingTests(unittest.TestCase):
    def test_legacy_product_refusal_precedes_decrypting_later_events(self):
        import test_improvement_trials as T
        from improvement_trial_evidence import TrialEvidence
        from improvement_trial_products import TrialProducts
        fixture = T.TrialStoreTests(); fixture.setUp(); self.addCleanup(fixture.doCleanups)
        row, _, _, _ = fixture.product_trace()
        decode = TrialEvidence._decode
        def bounded(reader, brain, record):
            if record['sequence'] > 3: raise AssertionError('legacy owner buffered future decrypted packets')
            packet = decode(reader, brain, record)
            if record['sequence'] == 3: packet['event']['hash'] = '0' * 64
            return packet
        with patch.object(TrialEvidence, '_decode', bounded), closing(fixture.rs._conn()) as connection:
            stored = fixture.trials._row(connection, fixture.owner.brain_id, row['trial_id'])
            with self.assertRaisesRegex(IM.ConflictError, 'trial_artifact_hash_mismatch'):
                TrialProducts(fixture.trials)._products(connection, stored)


import test_improvement_view_sources as V
import test_improvement_view_next as VN


class NativeTrialResultTests(V.SourceFixture, unittest.IsolatedAsyncioTestCase):
    owned_service, admit = VN.ViewNextTests.owned_service, VN.ViewNextTests.admit

    async def test_actual_trial4_products_finish_and_cold_read_authenticate_durable_native_history(self):
        from improvement_claude import ClaudeTrialAdapter, TrialProfile
        from improvement_sandbox import FixtureBroker, trial_system_prompt
        from improvement_trial_evidence import TrialEvidence
        from improvement_trial_results import TrialResults
        from improvement_native_trace_checks import validate_native_trace
        from test_improvement_trial_profile4 import EngineeringBinding
        from claude_agent_sdk import SystemMessage, AssistantMessage, ResultMessage
        service, _ = self.owned_service(); trials = service.trials
        with patch.object(ClaudeTrialAdapter, 'verify', return_value={'supported': True, 'capability_hash': 'd' * 64}):
            admitted = self.admit(service)
        row = trials.claim(self.owner, admitted.trial_id, expected_generation=1)
        token = row['lease_token']
        materialize = trials._materialization
        self.enterContext(patch.object(trials, '_materialization', side_effect=lambda *args, **kwargs:
            {**materialize(*args, **kwargs), 'version': 4}))
        manifest = trials.materialize(self.owner, admitted.trial_id, expected_generation=row['generation'], lease_token=token,
            baseline_context=self.host.context_loader(self.owner, admitted.request))
        workspace = trials.workspace.prepare(admitted.trial_id, 1, manifest)
        row = trials.prepared(self.owner, admitted.trial_id, expected_generation=row['generation'], lease_token=token, receipt=workspace)
        configuration = admitted.request['engine_config']
        profile = TrialProfile({key: configuration[key] for key in ('provider', 'model', 'reasoning', 'cli_path', 'sdk_version')},
            FixtureBroker(manifest['case']['fixtures'], manifest['grant_hash']), trial_system_prompt(manifest))
        profile.bind_installation(manifest, workspace, 'd' * 64)
        prompt = IM._json({'task': manifest['case']['task'], 'fixtures': [
            {key: item[key] for key in ('snapshot_id', 'source')} for item in manifest['case']['fixtures']]})
        with patch('improvement_native_profile.NativeProfileBinding', EngineeringBinding):
            profile.bind_native_runtime(object(), environment={}, user_prompt=prompt)
        profile.options(SimpleNamespace(cwd=workspace['path'], session_id=None, _on_stderr=lambda _: None))
        provisional = N.trace(workspace=workspace, configuration=configuration, system_prompt=profile.system_prompt)
        profile._native_binding.delivery = N.delivery('trial', workspace, provisional, prompt, workspace['input_hash'])
        events = profile.observe(SystemMessage('init', {'session_id': 'trial-session', 'tools': N.TOOLS}))
        events += profile.observe(AssistantMessage([], model=configuration['model'], session_id='trial-session'))
        content = '{"value":"trial Unicode 日本語"}\r\n'
        events += profile.observe(ResultMessage('success', 1, 1, False, 1, 'trial-session', result=content))
        packets = N.trace(workspace=workspace, configuration=configuration, events=events, system_prompt=profile.system_prompt)
        native = validate_native_trace(packets, kind='trial', receipt=workspace, pin=configuration, capability_hash='d' * 64,
            system_prompt=profile.system_prompt, user_prompt=prompt, data_hash=workspace['input_hash'])
        decisions = NativeImageDecisionStore(self.assets)
        scope = attempt_scope(kind='trial', brain_id=self.owner.brain_id, receipt=workspace, config_pin=configuration, capability_hash='d' * 64)
        row = trials.start_engine(self.owner, admitted.trial_id, expected_generation=row['generation'], lease_token=token)
        evidence = TrialEvidence(trials)
        for packet in packets: evidence.append(self.owner, admitted.trial_id, packet, expected_generation=row['generation'], lease_token=token)
        with self.assertRaises(PermissionError):
            trials.stage_evaluation(self.owner, admitted.trial_id, expected_generation=row['generation'], lease_token=token)
        for joined in native['joins']: decisions.persist(self.owner, joined, scope_hash=scope, current=lambda connection, value: 'allow')
        row = trials.stage_evaluation(self.owner, admitted.trial_id, expected_generation=row['generation'], lease_token=token)
        results = TrialResults(trials)
        guard = lambda: self.host.live_guard(self.owner, admitted.request)
        result = results.finish(self.owner, admitted.trial_id, expected_generation=row['generation'], lease_token=token,
            capability_hash='d' * 64, live_guard=guard, checker_registry={})
        self.assertEqual(result['status'], 'completed')
        self.assertEqual(trials.read_artifact(self.owner, admitted.trial_id, 1).decode(), content)
        with patch.object(self.host, '_snapshot_observe', side_effect=AssertionError('cold history cannot warm sources')):
            report = results.read(self.owner, admitted.trial_id, 1)
        checks = {item['id']: item for item in report['mandatory']}
        self.assertEqual(checks['completion']['verdict'], 'pass')
        self.assertEqual(checks['native_authorization']['verdict'], 'pass')
        self.assertEqual(checks['actual_reasoning']['verdict'], 'unknown')
        self.assertEqual(checks['native_qualification']['verdict'], 'unknown')
        with closing(self.assets.store._conn()) as connection:
            record = connection.execute("SELECT result_json FROM improvement_events WHERE operation='native_image_decision' ORDER BY id DESC LIMIT 1").fetchone()
        self.assets.blobs._path(self.owner.brain_id, json.loads(record[0])['blob_hashes'][0]).unlink()
        with self.assertRaises(AssetUnavailable): results.read(self.owner, admitted.trial_id, 1)


if __name__ == '__main__': unittest.main()
