"""Real Runner/ledger/products/cleanup with a clearly simulated engine adapter."""
from _paths import ROOT, SERVER  # noqa: F401

import asyncio
import hashlib
import unittest
from unittest.mock import patch

from agent_ledger import CallLedger
import improvement_claude as native
import improvement_sandbox as SB
import improvement_store as IM
from improvement_trial_runner import TrialRunner
from improvement_comparison_results import _NATIVE_CHECKS, ComparisonResults
import test_improvement_view_sources as sources
import test_improvement_view_next as next_fixtures


class ViewExecutionTests(sources.SourceFixture, unittest.IsolatedAsyncioTestCase):
    owned_service = next_fixtures.ViewNextTests.owned_service
    admit = next_fixtures.ViewNextTests.admit

    def view_adapter_factory(self, pin, *, workspace_root, before_engine_start):
        test = self

        class SimulatedAdapter:
            def verify(self):
                return {'supported': True, 'capability_hash': 'd' * 64}

            async def execute(self, native_request, workspace):
                test.executed += 1
                identity = {key: workspace[key] for key in ('trial_id', 'attempt', 'input_hash')}

                def packet(sequence, kind, **fields):
                    return {'version': 1, 'sequence': sequence, 'type': kind, **identity, **fields}

                try:
                    test.workspaces[native_request['trial_id']] = workspace
                    manifest = test.trials.workspace.validate(workspace)
                    current = test.trials.get(test.owner, native_request['trial_id'])
                    test.assertEqual(manifest['effective_view'], current['request']['view'])
                    profile = native.TrialProfile({key: pin[key] for key in ('provider', 'model', 'reasoning', 'cli_path', 'sdk_version')},
                        SB.FixtureBroker(manifest['case']['fixtures'], manifest['grant_hash']), SB.trial_system_prompt(manifest))
                    profile.bind_installation(manifest, workspace, 'd' * 64)
                    receipt = profile.installation_receipt('simulated-view-' + str(test.executed))
                    yield packet(1, 'worker_ready', capability_hash='d' * 64)
                    await before_engine_start()
                    current = await asyncio.to_thread(test.trials.get, test.owner, native_request['trial_id'])
                    test.assertIsNotNone(CallLedger(test.assets.store).get(current['attempts'][0]['call_id'])['engine_at'])
                    yield packet(2, 'engine_start_requested')
                    artifact = '{"value":"simulated view result"}\r\n'
                    events = [
                        {'type': 'native_system', 'subtype': 'init', 'data': {'session_id': receipt['session_id']}},
                        {'type': 'observation', 'model': pin['model'], 'message_id': 'simulated-view-' + native_request['trial_id'],
                            'session_id': receipt['session_id'], 'usage': {'input_tokens': 3, 'output_tokens': 2,
                                'cache_read_input_tokens': 0, 'cache_creation_input_tokens': 0}},
                        {'type': 'artifact', 'content': artifact, 'hash': hashlib.sha256(artifact.encode()).hexdigest()},
                        {'type': 'installation_receipt', 'receipt': receipt, 'hash': IM._hash(receipt)},
                        {'type': 'terminal', 'subtype': 'success', 'is_error': False, 'artifact_status': 'observed'}]
                    for sequence, event in enumerate(events, 3):
                        yield packet(sequence, 'engine_event', event=event)
                    yield packet(8, 'worker_complete', fixture_events=[], tool_denials=[])
                finally:
                    test.closed += 1

        return SimulatedAdapter()

    async def test_owned_pair_runs_real_pipeline_and_pins_v4_results_without_promoting_simulated_evidence(self):
        service, metadata = self.owned_service()
        self.trials, self.executed, self.closed, self.workspaces = service.trials, 0, 0, {}
        original, reports = self.f.f.f.skill.read_bytes(), []
        before = self.counts()[-1]
        for position in (0, 1):
            with patch.object(native.ClaudeTrialAdapter, 'verify', return_value={'supported': True, 'capability_hash': 'd' * 64}):
                admitted = self.admit(service, key='simulated-view-owned-next-' + str(position))
            runner = TrialRunner(self.trials, context_loader=self.host.context_loader,
                live_guard=self.host.live_guard, adapter_factory=self.view_adapter_factory)
            result = await runner.run(self.owner, admitted.trial_id)
            self.assertEqual(result['status'], 'completed', result)
            report = result['result']
            self.assertEqual(report['version'], 4)
            self.assertEqual(report['request_hash'], IM._hash(admitted.request))
            self.assertEqual(report['experiment_lineage'], admitted.request['lineage'])
            self.assertEqual(report['effective_view'], admitted.request['view'])
            self.assertEqual({row['id'] for row in report['mandatory']}, set(_NATIVE_CHECKS))
            self.assertNotEqual(report['verdict'], 'pass')
            for identifier in ('actual_reasoning', 'asset_observed_use'):
                self.assertEqual(next(row for row in report['mandatory'] if row['id'] == identifier)['verdict'], 'unknown')
            self.assertEqual((report['usage']['tokens_in'], report['usage']['tokens_out']), (3, 2))
            self.assertIsNone(report['usage']['requests'])
            self.assertTrue(self.trials.workspace.cleanup_proven(admitted.trial_id, 1, self.workspaces[admitted.trial_id]))
            with patch.object(self.host, '_snapshot_observe', side_effect=AssertionError('History cannot warm sources')):
                self.assertEqual(self.trials.read_result(self.owner, admitted.trial_id, 1), report)
            reports.append(report)
        self.assertEqual((self.executed, self.closed), (2, 2))
        self.assertEqual(self.counts()[-1], before + 2)
        self.assertEqual(self.f.f.f.skill.read_bytes(), original)
        self.assertNotEqual(reports[0]['effective_view']['view_hash'], reports[1]['effective_view']['view_hash'])
        comparison = ComparisonResults(self.f.plans)
        saved = comparison.create(self.owner, self.comparison['id'], expected_generation=self.generation(),
            event_key='simulated-view-comparison-report')
        combined = comparison.read(self.owner, saved['report_id'])
        self.assertFalse(combined['summary']['selection_supported'])
        self.host.revoke(self.owner, self.comparison['experiment_id'], expected_generation=1,
            event_key='simulated-view-history-revoke')
        self.assets.set_policy(self.owner, 'off', expected_version=0, event_key='simulated-view-history-off')
        with patch.object(self.host, '_snapshot_observe', side_effect=AssertionError('Revoked history cannot warm sources')):
            for report in reports:
                self.assertEqual(self.trials.read_result(self.owner, report['trial_id'], 1), report)
            self.assertEqual(comparison.read(self.owner, saved['report_id']), combined)


if __name__ == '__main__':
    unittest.main()
