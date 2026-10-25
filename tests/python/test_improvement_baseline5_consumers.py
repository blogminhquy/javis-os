"""Native baseline5 consumers with synthetic captures, no native/provider use."""
from _paths import ROOT, SERVER  # noqa: F401

import copy
import json
import unittest
from contextlib import closing
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import patch

import improvement_store as IM
import improvement_trial_checks as checks
from improvement_sandbox import trial_system_prompt, _effective_hash, FixtureBroker
from improvement_native_trace_checks import validate_native_trace
from improvement_native_decisions import NativeImageDecisionStore, attempt_scope
from improvement_trial_evidence import TrialEvidence
from improvement_trial_results import TrialResults
from improvement_claude import TrialProfile
from improvement_blobs import AssetUnavailable
import test_improvement_native_trace_checks as N
import test_improvement_trial_checks as C
import test_improvement_trial_profile4 as P
import test_improvement_trials as T
import test_improvement_native_runner_evidence as R


def baseline_trace(workspace, pin, system_prompt, events=None):
    packets = N.trace('trial', workspace, pin, events, system_prompt)
    query = next(p['body'] for p in packets if p['body']['type'] == 'dispatch_observed' and p['body']['purpose'] == 'query')
    policy = {**N.query_policy('trial', pin, workspace, system_prompt),
        'tool_policy': 'baseline_inline', 'tools': N.TOOLS[:1]}
    query['dispatch']['argument_consistency'].update(tool_policy='baseline_inline', tools=N.TOOLS[:1],
        expected_hash=IM._hash(policy), mcp_config_hash=IM._hash({'mcpServers': {'fixture': {'type': 'sdk', 'name': 'fixture'}}}))
    query['dispatch_hash'] = IM._hash(query['dispatch'])
    return packets


class BaselineRecordChecksTests(unittest.TestCase):
    def setUp(self):
        fixture = C.TrialChecksTests(); fixture.setUp()
        self.fixture = fixture
        fixture.manifest['version'] = 5
        fixture.workspace.update(input_hash=IM._hash(fixture.manifest), effective_hash=_effective_hash(fixture.manifest))
        fixture.receipt.update(version=5, **{k: fixture.workspace[k] for k in ('input_hash', 'effective_hash')})
        prompt = IM._json({'task': fixture.manifest['case']['task'], 'fixtures': [
            {k: item[k] for k in ('snapshot_id', 'source')} for item in fixture.manifest['case']['fixtures']]})
        packets = baseline_trace(fixture.workspace, fixture.request['engine_config'], trial_system_prompt(fixture.manifest))
        fixture.receipt['native_input_delivery'] = N.delivery('trial', fixture.workspace, packets, prompt, fixture.workspace['input_hash'])
        self.rebuild()

    def rebuild(self):
        f = self.fixture
        f.events = [({**e, 'receipt': f.receipt, 'hash': IM._hash(f.receipt)} if e['type'] == 'installation_receipt' else e)
            for e in f.events]
        self.packets = baseline_trace(f.workspace, f.request['engine_config'], trial_system_prompt(f.manifest), f.events)
        next(p['body'] for p in self.packets if p['body']['type'] == 'worker_ready')['capability_hash'] = f.capability

    def check(self, reader=lambda _: {'decision': 'allow', 'durable_evidence_hash': 'a' * 64}):
        f = self.fixture
        return {r['id']: r for r in checks.execution_invariants(f.request, f.manifest, f.workspace, self.packets,
            f.capability, contract=f.contract, read_decision=reader)}

    def test_baseline5_records_require_exact_receipt_and_delivery_without_claiming_read_or_reasoning(self):
        rows = self.check()
        for name in ('materialization', 'workspace_binding', 'installation', 'tool_inventory', 'native_trace',
                'native_authorization', 'native_input_delivery', 'completion'):
            self.assertEqual(rows[name]['verdict'], 'pass', rows)
        for name in ('asset_observed_use', 'actual_reasoning', 'native_qualification'):
            self.assertEqual(rows[name]['verdict'], 'unknown')
        self.assertEqual(rows['native_input_delivery']['evidence']['provider_acceptance'], 'unknown')

    def test_baseline_policy_requires_explicit_trial_selection_and_refuses_operation_or_pinned_default(self):
        f = self.fixture
        kwargs = dict(kind='trial', receipt=f.workspace, pin=f.request['engine_config'], capability_hash=f.capability,
            system_prompt=trial_system_prompt(f.manifest), user_prompt='unused', data_hash=f.workspace['input_hash'])
        with self.assertRaises(ValueError): validate_native_trace(self.packets, **kwargs)
        # No installation event avoids a different delivery error hiding policy validation.
        packets = baseline_trace(f.workspace, f.request['engine_config'], trial_system_prompt(f.manifest))
        next(p['body'] for p in packets if p['body']['type'] == 'worker_ready')['capability_hash'] = f.capability
        self.assertEqual(len(validate_native_trace(packets, **kwargs, tool_policy='baseline_inline')['joins']), 4)
        with self.assertRaises(ValueError): validate_native_trace(packets, **{**kwargs, 'kind': 'operation'}, tool_policy='baseline_inline')
        with self.assertRaises(ValueError): validate_native_trace(packets, **kwargs, tool_policy='arbitrary')

    def test_rehashed_foreign_delivery_and_fake_view_receipts_cannot_pass(self):
        f = self.fixture
        f.receipt['native_input_delivery']['native_birth'] += 1; self.rebuild()
        self.assertEqual(self.check()['execution_records']['verdict'], 'fail')
        f.receipt['native_input_delivery']['native_birth'] -= 1
        for field, value in (('effective_view', {}), ('read_outcome_proofs', [])):
            f.receipt[field] = value; self.rebuild()
            self.assertEqual(self.check()['installation']['verdict'], 'fail')
            f.receipt.pop(field)

    def test_missing_delivery_and_unread_decisions_remain_unknown_and_candidate5_refuses(self):
        f = self.fixture
        f.receipt['native_input_delivery'] = None; self.rebuild()
        rows = self.check(reader=None)
        self.assertEqual(rows['native_input_delivery']['verdict'], 'unknown')
        self.assertEqual(rows['native_authorization']['verdict'], 'unknown')
        self.assertEqual(rows['completion']['verdict'], 'unknown')
        f.request['variant'] = 'candidate'
        self.assertEqual(self.check()['execution_records']['verdict'], 'fail')


class BaselineResultTests(unittest.TestCase):
    def setUp(self):
        f = T.TrialStoreTests(); f.setUp(); self.addCleanup(f.doCleanups)
        self.f, self.trials, self.owner = f, f.trials, f.owner
        original = self.trials._materialization
        self.enterContext(patch.object(self.trials, '_materialization', side_effect=lambda *a, **kw: {**original(*a, **kw), 'version': 5}))
        self.row, self.token = f.prepared()
        self.identifier = self.row['trial_id']
        with closing(self.trials.store._conn()) as connection:
            self.workspace = json.loads(connection.execute('SELECT workspace_json FROM improvement_trial_attempts WHERE trial_id=? AND attempt=1',
                (self.identifier,)).fetchone()[0])
        self.manifest = self.trials.workspace.validate(self.workspace)
        self.pin = f.request['engine_config']
        self.profile = TrialProfile({k: self.pin[k] for k in ('provider', 'model', 'reasoning', 'cli_path', 'sdk_version')},
            FixtureBroker(self.manifest['case']['fixtures'], self.manifest['grant_hash']), trial_system_prompt(self.manifest))
        self.profile.bind_installation(self.manifest, self.workspace, 'c' * 64)
        self.prompt = IM._json({'task': self.manifest['case']['task'], 'fixtures': [
            {k: item[k] for k in ('snapshot_id', 'source')} for item in self.manifest['case']['fixtures']]})
        with patch('improvement_native_profile.NativeProfileBinding', P.EngineeringBinding):
            self.profile.bind_native_runtime(object(), environment={}, user_prompt=self.prompt)
        self.profile.options(SimpleNamespace(cwd=self.workspace['path'], session_id=None, _on_stderr=lambda _: None))
        self.results = TrialResults(self.trials)

    def prepare_trace(self, persist=True):
        from claude_agent_sdk import SystemMessage, AssistantMessage, ResultMessage
        provisional = baseline_trace(self.workspace, self.pin, self.profile.system_prompt)
        self.profile._native_binding.delivery = N.delivery('trial', self.workspace, provisional, self.prompt, self.workspace['input_hash'])
        self.content = '{"value":"baseline 日本語"}\r\n'
        events = self.profile.observe(SystemMessage('init', {'session_id': 'baseline-session', 'tools': N.TOOLS[:1]}))
        events += self.profile.observe(AssistantMessage([], model=self.pin['model'], session_id='baseline-session'))
        events += self.profile.observe(ResultMessage('success', 1, 1, False, 1, 'baseline-session', result=self.content))
        self.packets = baseline_trace(self.workspace, self.pin, self.profile.system_prompt, events)
        next(p['body'] for p in self.packets if p['body']['type'] == 'worker_ready')['capability_hash'] = 'c' * 64
        self.validated = validate_native_trace(self.packets, kind='trial', receipt=self.workspace, pin=self.pin,
            capability_hash='c' * 64, system_prompt=self.profile.system_prompt, user_prompt=self.prompt,
            data_hash=self.workspace['input_hash'], tool_policy='baseline_inline')
        self.scope = attempt_scope(kind='trial', brain_id=self.owner.brain_id, receipt=self.workspace,
            config_pin=self.pin, capability_hash='c' * 64)
        self.row = self.trials.start_engine(self.owner, self.identifier, expected_generation=self.row['generation'], lease_token=self.token)
        evidence = TrialEvidence(self.trials)
        for packet in self.packets:
            evidence.append(self.owner, self.identifier, packet, expected_generation=self.row['generation'], lease_token=self.token)
        if persist:
            for joined in self.validated['joins']:
                NativeImageDecisionStore(self.trials.assets).persist(self.owner, joined, scope_hash=self.scope, current=lambda c, v: 'allow')

    def stage(self):
        self.row = self.trials.stage_evaluation(self.owner, self.identifier, expected_generation=self.row['generation'], lease_token=self.token)

    def finish(self):
        return self.results.finish(self.owner, self.identifier, expected_generation=self.row['generation'], lease_token=self.token,
            capability_hash='c' * 64, live_guard=lambda: {
                **{k: self.f.request[k] for k in ('baseline_context_hash', 'target_generations')},
                **{k: self.f.request['pins'][k] for k in ('scope_hash', 'grant_hash', 'engine_config_hash')}}, checker_registry={})

    def test_actual_baseline_products_results_and_cold_history_authenticate_all_four_decisions(self):
        self.prepare_trace(); self.stage(); result = self.finish()
        self.assertEqual(result['status'], 'completed')
        self.assertEqual(self.trials.read_artifact(self.owner, self.identifier, 1).decode(), self.content)
        self.assertFalse(Path(self.workspace['path']).exists())
        report = self.results.read(self.owner, self.identifier, 1)
        rows = {r['id']: r for r in report['mandatory']}
        for key in ('installation', 'completion', 'native_authorization', 'native_input_delivery'):
            self.assertEqual(rows[key]['verdict'], 'pass', rows)
        self.assertEqual(rows['asset_observed_use']['verdict'], 'unknown')
        self.assertEqual(rows['actual_reasoning']['verdict'], 'unknown')
        self.assertEqual(report['version'], 1); self.assertEqual(len(report['native_decisions']), 4)
        with closing(self.trials.store._conn()) as connection:
            row = connection.execute("SELECT result_json FROM improvement_events WHERE operation='native_image_decision' ORDER BY id DESC LIMIT 1").fetchone()
        self.trials.blobs._path(self.owner.brain_id, json.loads(row[0])['blob_hashes'][0]).unlink()
        with self.assertRaises(AssetUnavailable): self.results.read(self.owner, self.identifier, 1)

    def test_missing_actual_baseline_decisions_refuses_products_and_keeps_call_running(self):
        self.prepare_trace(persist=False)
        with self.assertRaises(PermissionError): self.stage()
        self.assertEqual(self.trials.ledger.get(self.row['attempts'][-1]['call_id'])['status'], 'running')

    def test_final_baseline_publication_rereads_original_decisions(self):
        self.prepare_trace(); self.stage()
        import improvement_trial_results as results_module
        original = results_module.EVAL.evaluate_trial; once = [False]
        def corrupt_after_check(*args, **kwargs):
            value = original(*args, **kwargs)
            if not once[0]:
                once[0] = True
                joined = self.validated['joins'][-1]
                key = 'native-image:' + IM._hash([self.scope, joined['launch_nonce'], 'query'])
                with self.trials.store._Tx(self.trials.store) as connection:
                    connection.execute('DROP TRIGGER improvement_events_update')
                    stored = connection.execute('SELECT result_json FROM improvement_events WHERE event_key=?', (key,)).fetchone()
                    data = json.loads(stored[0]); data['decision'] = 'deny'
                    connection.execute('UPDATE improvement_events SET result_json=? WHERE event_key=?', (IM._json(data), key))
            return value
        with patch.object(results_module.EVAL, 'evaluate_trial', side_effect=corrupt_after_check), self.assertRaises((PermissionError, AssetUnavailable, IM.ConflictError)):
            self.finish()
        self.assertTrue(once[0])


class BaselineRunnerTests(unittest.IsolatedAsyncioTestCase):
    kind = 'trial'
    def setUp(self):
        R.RunnerEvidenceCases.setUp(self)
        # Replace the prior engineering view4 emitter with baseline5 using its
        # original wrapped materializer, preserving every actual owner check.
        original = type(self.execution)._materialization.__get__(self.execution)
        self.enterContext(patch.object(self.execution, '_materialization', side_effect=lambda *a, **kw: {**original(*a, **kw), 'version': 5}))
    guard = R.RunnerEvidenceCases.guard
    recorder = R.RunnerEvidenceCases.recorder
    adapter = R.RunnerEvidenceCases.adapter
    run_attempt = R.RunnerEvidenceCases.run_attempt
    rows = R.RunnerEvidenceCases.rows
    read = R.RunnerEvidenceCases.read
    call = R.RunnerEvidenceCases.call
    test_closing_global_sequence_and_usage = R.RunnerEvidenceCases.test_active_raw_envelopes_and_closing_terminal_use_original_global_sequence
    test_repeated_cancel_retains_original_closing_usage = R.RunnerEvidenceCases.test_cancel_waits_for_closing_callback_and_keeps_usage_before_lock_release
    test_revoked_closing_is_late_and_counted = R.RunnerEvidenceCases.test_revoked_closing_batch_is_late_original_writer_history_not_current_success


if __name__ == '__main__': unittest.main()
