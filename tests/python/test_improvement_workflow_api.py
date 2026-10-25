"""Owner controls use actual experiment C services; metadata reads stay cold."""
from _paths import ROOT, SERVER  # noqa: F401

import asyncio
import json
import threading
import unittest
from unittest.mock import patch

import httpx
from fastapi import FastAPI
from fastapi.responses import JSONResponse

import improvement_experiment_api as API
import improvement_store as IM
from improvement_experiment_service import ExperimentService
from improvement_trial_service import OwnerTrialService
import test_improvement_preparation as fixtures
import test_improvement_preparation_execution as execution
import test_improvement_proposals as roles


CONTROLS = ('preparation-freeze', 'preparation-next', 'preparation-complete', 'propose',
            'semantic-review', 'semantic-arbitrate', 'semantic-evidence')


class WorkflowApiTests(unittest.IsolatedAsyncioTestCase):
    factory = execution.PreparationExecutionTests.factory

    def setUp(self):
        self.f = fixtures.PreparationTests()
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        # Retain the fixture's prohibition on native/auth/model commands while
        # allowing the real disposable-workspace Windows ACL metadata commands.
        self.enterContext(patch('subprocess.run', side_effect=lambda *a, **kw: execution._acl_only(execution._REAL_RUN, *a, **kw)))
        self.enterContext(patch('subprocess.Popen', side_effect=lambda *a, **kw: execution._acl_only(execution._REAL_POPEN, *a, **kw)))
        self.owner, self.assets, self.host = self.f.owner, self.f.assets, self.f.host
        state = self.f.f.f.root / 'workflow-api-usage'
        state.mkdir()
        for obj, name, value in ((execution.US, '_PATH', state / 'usage.json'),
                (execution.US, '_EVENTS_PATH', state / 'events.jsonl'), (execution.US, '_TELEMETRY_ERRORS', {}),
                (execution.UI, '_EVENTS_PATH', state / 'events.jsonl'), (execution.UI, 'DB_PATH', state / 'index.db'),
                (execution.UI, '_claude_dir', lambda: str(state / 'empty-native')),
                (execution.UI, '_codex_dir', lambda: str(state / 'empty-codex'))):
            self.enterContext(patch.object(obj, name, value))
        self.mount()

    def mount(self):
        self.owner_calls, self.factory_calls = [], []
        self.loop_thread = threading.get_ident()
        self.trial_service = OwnerTrialService(self.host)
        self.addAsyncCleanup(self.trial_service.close)
        self.service = ExperimentService(self.f.plans, self.trial_service)
        self.addAsyncCleanup(self.service.close)
        self.trials = self.service.trials
        self.app = FastAPI()
        API.register(self.app, API.ExperimentApiDeps(read_store=self.read_store, resolve_brain=self.resolve_brain,
            owner_session=self.owner_session, service=self.service_factory))
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url='http://test')
        self.addAsyncCleanup(self.client.aclose)

    def owner_session(self, request):
        self.owner_calls.append(threading.get_ident())
        if request.cookies.get('owner') != 'yes':
            return JSONResponse({'ok': False, 'reason': 'owner_session_required'}, status_code=403)

    def service_factory(self):
        self.factory_calls.append(('service', threading.get_ident()))
        return self.service

    def read_store(self):
        self.factory_calls.append(('read', threading.get_ident()))
        return IM.read_existing(self.assets.store.path, self.assets.blobs)

    def resolve_brain(self, brain):
        self.factory_calls.append(('brain', threading.get_ident()))
        return self.owner.brain_id if brain == 'brain' else self.f.f.f.other.brain_id

    async def request(self, method, path, **kwargs):
        return await self.client.request(method, path, headers={'cookie': 'owner=yes'}, **kwargs)

    async def post(self, action, **data):
        return await self.request('POST', '/improvement-experiments/association-experiment/' + action, json=data)

    async def test_every_new_control_rejects_token_before_brain_body_or_factory(self):
        for action in CONTROLS:
            self.factory_calls.clear()
            response = await self.client.post('/improvement-experiments/invalid/' + action + '?brain=foreign',
                content=b'invalid', headers={'authorization': 'Bearer synthetic-full-token'})
            self.assertEqual(response.status_code, 403, action)
            self.assertEqual(self.factory_calls, [])
        self.assertEqual(self.owner_calls, [self.loop_thread] * len(CONTROLS))

    async def test_closed_body_rejects_native_grants_and_slots_before_service(self):
        for action in CONTROLS:
            self.factory_calls.clear()
            response = await self.post(action, event_key='caller-minted-native-proof', expected_generation=1,
                ready=True, native_verdict='pass', cell_position=0, capability_hash='a' * 64)
            self.assertEqual(response.status_code, 400, (action, response.text))
            self.assertNotIn('service', [name for name, _ in self.factory_calls])

    async def test_preparation_freeze_is_real_cas_and_foreign_brain_cannot_observe_it(self):
        frozen = await self.post('preparation-freeze', expected_generation=1, event_key='http-freeze-real-preparation')
        self.assertEqual(frozen.status_code, 200, frozen.text)
        saved = frozen.json()['result']
        self.assertEqual(saved['cell_count'], 1)
        self.assertEqual(saved['generation'], 2)
        replay = await self.post('preparation-freeze', expected_generation=1, event_key='http-freeze-real-preparation')
        self.assertEqual(replay.json(), frozen.json())
        stale = await self.post('preparation-freeze', expected_generation=1, event_key='http-stale-freeze-preparation')
        self.assertEqual(stale.status_code, 409)
        foreign = await self.request('GET', '/improvement-experiments/association-experiment/preparation?brain=other')
        self.assertEqual(foreign.status_code, 403)
        self.assertTrue(all(thread != self.loop_thread for _, thread in self.factory_calls))
        stopped = await self.post('cancel', expected_generation=2, event_key='http-stop-before-freeze-replay')
        self.assertEqual(stopped.status_code, 200, stopped.text)
        with patch.object(self.assets.blobs, 'read', side_effect=AssertionError('Stop replay cannot decrypt')):
            replay = await self.post('preparation-freeze', expected_generation=1, event_key='http-freeze-real-preparation')
        self.assertEqual(replay.status_code, 200, replay.text)
        self.assertEqual(replay.json(), frozen.json())
        rebuilt_trials = OwnerTrialService(self.host)
        self.addAsyncCleanup(rebuilt_trials.close)
        self.service = ExperimentService(self.f.plans, rebuilt_trials)
        self.addAsyncCleanup(self.service.close)
        with patch.object(self.assets.blobs, 'read', side_effect=AssertionError('Restart replay cannot decrypt')):
            rebuilt = await self.post('preparation-freeze', expected_generation=1, event_key='http-freeze-real-preparation')
            fresh = await self.post('propose', expected_generation=2, event_key='http-no-new-native-work-after-stop')
        self.assertEqual(rebuilt.json(), frozen.json())
        self.assertEqual(fresh.status_code, 409)

    async def test_cold_preparation_and_role_history_never_constructs_execution_or_decrypts(self):
        self.f.freeze()
        self.factory_calls.clear()
        with patch.object(self.assets.blobs, 'read', side_effect=AssertionError('Cold history cannot decrypt')), \
             patch.object(self.host, '_snapshot_observe', side_effect=AssertionError('Cold history cannot capture')), \
             patch.object(self.service.execution, 'guard', side_effect=AssertionError('Cold history cannot probe')):
            preparation = await self.request('GET', '/improvement-experiments/association-experiment/preparation')
            operations = await self.request('GET', '/improvement-experiments/association-experiment/operations')
            missing = await self.request('GET', '/improvement-operations/missing')
            semantic = await self.request('GET', '/improvement-candidates/missing/semantic-history')
        self.assertEqual(preparation.status_code, 200, preparation.text)
        self.assertEqual(len(preparation.json()['preparations']), 1)
        self.assertEqual(operations.json()['operations'], [])
        self.assertEqual(missing.status_code, 403)
        self.assertEqual(semantic.status_code, 403)
        self.assertNotIn('service', [name for name, _ in self.factory_calls])
        self.assertNotIn(self.owner.brain_id, preparation.text + operations.text + missing.text + semantic.text)

    async def test_preparation_next_hands_off_to_shared_real_trial_supervisor_and_stop_drains_it(self):
        self.f.freeze()
        self.closed, self.starts, self.pause_before_start = False, 0, True
        self.start_entered, self.start_release = asyncio.Event(), asyncio.Event()
        self.trial_service.tasks.runner.adapter_factory = self.factory
        with patch('improvement_preparation.ClaudeTrialAdapter.verify',
                   return_value={'supported': True, 'capability_hash': 'c' * 64}):
            response = await self.post('preparation-next', expected_generation=2, event_key='http-real-preparation-next')
        self.assertEqual(response.status_code, 200, response.text)
        identifier = response.json()['result']['trial_id']
        # The worker is held before its durable engine marker. Cancellation must
        # terminate that real owned lifetime, not a mocked start/readiness method.
        self.admitted = type('Identity', (), {'trial_id': identifier})()
        await asyncio.wait_for(self.start_entered.wait(), 10)
        stopped = await self.post('cancel', expected_generation=2, event_key='http-cancel-preparation-worker')
        self.assertEqual(stopped.status_code, 200, stopped.text)
        self.assertEqual(stopped.json()['result']['current']['phase'], 'cancelled')
        self.assertTrue(self.closed)
        self.assertEqual(self.starts, 0)
        self.assertNotIn((self.owner.brain_id, identifier), self.service.tasks._tasks)
        with patch.object(self.assets.blobs, 'read', side_effect=AssertionError('Admission replay cannot decrypt')), \
             patch.object(self.service.tasks, 'start', side_effect=AssertionError('Replay cannot redispatch')):
            replay = await self.post('preparation-next', expected_generation=2, event_key='http-real-preparation-next')
        self.assertEqual(replay.status_code, 200, replay.text)
        self.assertEqual(replay.json()['result']['trial_id'], identifier)
        self.assertEqual(replay.json()['result']['status'], 'cancelled')

    async def test_complete_requires_and_seals_the_actual_http_baseline_result(self):
        frozen = await self.post('preparation-freeze', expected_generation=1, event_key='http-freeze-before-complete')
        self.assertEqual(frozen.status_code, 200, frozen.text)
        self.closed, self.starts, self.pause_before_start = False, 0, True
        self.start_entered, self.start_release = asyncio.Event(), asyncio.Event()
        self.service.tasks.runner.adapter_factory = self.factory
        with patch('improvement_preparation.ClaudeTrialAdapter.verify',
                   return_value={'supported': True, 'capability_hash': 'c' * 64}):
            response = await self.post('preparation-next', expected_generation=2, event_key='http-start-before-complete')
        self.assertEqual(response.status_code, 200, response.text)
        identifier = response.json()['result']['trial_id']
        self.admitted = type('Identity', (), {'trial_id': identifier})()
        await asyncio.wait_for(self.start_entered.wait(), 10)
        pending = self.service.tasks._tasks[(self.owner.brain_id, identifier)][1]
        early = await self.post('preparation-complete', expected_generation=2, event_key='http-complete-before-terminal-result')
        self.assertEqual(early.status_code, 409)
        self.start_release.set()
        await self.service.tasks._join(pending)
        self.assertEqual(self.trials.get(self.owner, identifier)['status'], 'completed')
        complete = await self.post('preparation-complete', expected_generation=2, event_key='http-complete-after-terminal-result')
        self.assertEqual(complete.status_code, 200, complete.text)
        self.assertEqual(complete.json()['result']['phase'], 'proposing')
        self.assertEqual(complete.json()['result']['result_refs'][0]['trial_id'], identifier)
        self.assertEqual(self.starts, 1)
        self.assertTrue(self.closed)


class RoleWorkflowApiTests(unittest.IsolatedAsyncioTestCase):
    prepare = roles.ProposalTests.prepare
    factory = roles.ProposalTests.factory
    adapter = roles.ProposalTests.adapter
    body_patch = roles.ProposalTests.body_patch
    mount = WorkflowApiTests.mount
    owner_session = WorkflowApiTests.owner_session
    service_factory = WorkflowApiTests.service_factory
    read_store = WorkflowApiTests.read_store
    resolve_brain = WorkflowApiTests.resolve_brain
    request = WorkflowApiTests.request
    post = WorkflowApiTests.post

    def setUp(self):
        roles.ProposalTests.setUp(self)
        self.mount()

    async def test_http_invalid_semantic_output_is_explicit_and_replays_cold_after_stop(self):
        await self.prepare()
        candidate = self.f.plans.authoring.stage(self.owner, 'association-experiment', self.body_patch(),
            event_key='http-manual-invalid-semantic-candidate')
        self.acked, self.closed, self.hang = asyncio.Event(), asyncio.Event(), False
        self.body = '```json\n{"version":1,"verdict":"pass","summary":"Synthetic assessment."}\n```'
        self.service.operation_tasks.runner.adapter_factory = self.adapter
        payload = {'candidate_id': candidate['candidate_id'], 'expected_generation': 3,
                   'event_key': 'http-invalid-semantic-output'}
        with patch('improvement_operation_adapter.ClaudeOperationAdapter.verify',
                   return_value={'supported': True, 'capability_hash': 'c' * 64}):
            response = await self.post('semantic-review', **payload)
        self.assertEqual(response.status_code, 200, response.text)
        result = response.json()['result']
        self.assertEqual(result['status'], 'invalid_output')
        self.assertNotIn('receipt_id', result)
        self.assertEqual(self.native_queries, 1)
        generation = self.f.plans.records.get(self.owner, 'association-experiment')['generation']
        self.host.revoke(self.owner, 'association-experiment', expected_generation=1, event_key='http-invalid-output-revoke')
        self.assets.set_policy(self.owner, 'off', expected_version=0, event_key='http-invalid-output-off')
        stopped = await self.post('cancel', expected_generation=generation, event_key='http-invalid-output-stop')
        self.assertEqual(stopped.status_code, 200, stopped.text)
        with patch.object(self.assets.blobs, 'read', side_effect=AssertionError('Stopped invalid-output history stays cold')), \
             patch.object(self.host, '_snapshot_observe', side_effect=AssertionError('No source capture on replay')):
            replay = await self.post('semantic-review', **payload)
        self.assertEqual(replay.status_code, 200, replay.text)
        self.assertEqual(replay.json()['result'], result)
        self.assertEqual(self.native_queries, 1)

    async def test_actual_http_proposer_reviewer_owner_decision_and_revoked_cold_history(self):
        await self.prepare()
        self.acked, self.closed, self.hang = asyncio.Event(), asyncio.Event(), False
        self.body = IM._json({'version': 1, 'kind': 'patches', 'patches': [self.body_patch()]})
        self.service.operation_tasks.runner.adapter_factory = self.adapter
        with patch('improvement_operation_adapter.ClaudeOperationAdapter.verify',
                   return_value={'supported': True, 'capability_hash': 'c' * 64}):
            generated = await self.post('propose', expected_generation=3, event_key='http-propose-real-native-product')
            self.assertEqual(generated.status_code, 200, generated.text)
            proposal = generated.json()['result']
            candidate_id = proposal['candidates'][0]['candidate_id']
            self.body = IM._json({'version': 1, 'verdict': 'owner_required', 'summary': 'Owner meaning needs confirmation.',
                'findings': [{'kind': 'uncertainty', 'verdict': 'owner_required',
                    'rationale': 'Confirm the exact intended meaning.', 'source_refs': [{'kind': 'candidate', 'id': candidate_id}]}]})
            reviewed = await self.post('semantic-review', candidate_id=candidate_id,
                expected_generation=proposal['generation'], event_key='http-semantic-real-native-product')
        self.assertEqual(reviewed.status_code, 200, reviewed.text)
        review = reviewed.json()['result']
        self.assertEqual(review['verdict'], 'owner_required')
        generation = self.f.plans.records.get(self.owner, 'association-experiment')['generation']
        foreign_scope = await self.request('POST', '/improvement-experiments/another-experiment/semantic-evidence',
            json={'candidate_id': candidate_id, 'expected_generation': generation, 'event_key': 'http-wrong-candidate-experiment'})
        self.assertEqual(foreign_scope.status_code, 403)
        decision = {'candidate_id': candidate_id, 'receipt_id': review['receipt_id'], 'verdict': 'pass',
            'reason': 'Owner confirms this exact intended meaning.', 'expected_binding_hash': review['binding_hash']}
        stale = await self.post('semantic-arbitrate', **decision, expected_generation=generation - 1, event_key='http-stale-owner-semantic-cas')
        self.assertEqual(stale.status_code, 409)
        accepted = await self.post('semantic-arbitrate', **decision, expected_generation=generation, event_key='http-owner-semantic-cas')
        self.assertEqual(accepted.status_code, 200, accepted.text)
        current = await self.post('semantic-evidence', candidate_id=candidate_id,
            expected_generation=generation, event_key='http-current-semantic-evidence')
        self.assertEqual(current.status_code, 200, current.text)
        self.assertEqual(current.json()['result']['owner_assessment']['verdict'], 'pass')
        self.assertEqual(current.json()['result']['verdict'], 'unknown')
        self.assertFalse(current.json()['result']['business_proof'])
        self.assertNotIn('engine_config', current.text)
        self.assertNotIn('before', current.json()['result'])
        self.assertEqual(self.native_queries, 2)
        self.host.revoke(self.owner, 'association-experiment', expected_generation=1, event_key='http-revoke-after-role-evidence')
        with patch.object(self.assets.blobs, 'read', side_effect=AssertionError('Revoked history must not decrypt')):
            history = await self.request('GET', '/improvement-candidates/' + candidate_id + '/semantic-history')
            operations = await self.request('GET', '/improvement-experiments/association-experiment/operations')
        self.assertEqual(history.status_code, 200, history.text)
        self.assertEqual(history.json()['receipts'][0]['receipt_id'], review['receipt_id'])
        self.assertEqual(len(operations.json()['operations']), 2)
        refused = await self.post('semantic-evidence', candidate_id=candidate_id,
            expected_generation=generation, event_key='http-revoked-semantic-evidence')
        self.assertEqual(refused.status_code, 403)
        stopped = await self.post('cancel', expected_generation=generation, event_key='http-stop-before-historical-role-retries')
        self.assertEqual(stopped.status_code, 200, stopped.text)
        with patch.object(self.assets.blobs, 'read', side_effect=AssertionError('Historical role replay cannot decrypt')), \
             patch.object(self.host, '_snapshot_observe', side_effect=AssertionError('Historical replay cannot capture')):
            generated_again = await self.post('propose', expected_generation=3, event_key='http-propose-real-native-product')
            reviewed_again = await self.post('semantic-review', candidate_id=candidate_id,
                expected_generation=proposal['generation'], event_key='http-semantic-real-native-product')
            decision_again = await self.post('semantic-arbitrate', **decision,
                expected_generation=generation, event_key='http-owner-semantic-cas')
        self.assertEqual(generated_again.json(), generated.json())
        self.assertEqual(reviewed_again.json(), reviewed.json())
        self.assertEqual(decision_again.json(), accepted.json())
        self.assertEqual(self.native_queries, 2)

    async def test_stop_and_repeated_http_cancel_join_owner_arbitration_reason_thread(self):
        await self.prepare()
        self.acked, self.closed, self.hang = asyncio.Event(), asyncio.Event(), False
        candidate = self.f.plans.authoring.stage(self.owner, 'association-experiment', self.body_patch(),
            event_key='http-stage-candidate-for-owner-arbitration-stop')
        self.body = IM._json({'version': 1, 'verdict': 'owner_required', 'summary': 'Confirm exact owner meaning.',
            'findings': [{'kind': 'uncertainty', 'verdict': 'owner_required', 'rationale': 'Owner interpretation needed.',
                'source_refs': [{'kind': 'candidate', 'id': candidate['candidate_id']}]}]})
        self.service.operation_tasks.runner.adapter_factory = self.adapter
        with patch('improvement_operation_adapter.ClaudeOperationAdapter.verify',
                   return_value={'supported': True, 'capability_hash': 'c' * 64}):
            response = await self.post('semantic-review', candidate_id=candidate['candidate_id'],
                expected_generation=3, event_key='http-semantic-before-arbitration-stop')
        self.assertEqual(response.status_code, 200, response.text)
        receipt = response.json()['result']
        generation = self.f.plans.records.get(self.owner, 'association-experiment')['generation']
        entered, release = threading.Event(), threading.Event()
        write = self.assets.blobs.write

        def delayed(brain, raw):
            if json.loads(raw) == {'reason': 'Owner exact meaning while stopping.'}:
                entered.set()
                if not release.wait(10):
                    raise AssertionError('Reason thread was not released')
            return write(brain, raw)

        with patch.object(self.assets.blobs, 'write', side_effect=delayed):
            decision = asyncio.create_task(self.post('semantic-arbitrate', candidate_id=candidate['candidate_id'],
                receipt_id=receipt['receipt_id'], expected_generation=generation, expected_binding_hash=receipt['binding_hash'],
                verdict='pass', reason='Owner exact meaning while stopping.', event_key='http-owner-reason-before-stop'))
            stopped = None
            try:
                self.assertTrue(await asyncio.to_thread(entered.wait, 10))
                stopped = asyncio.create_task(self.post('cancel', expected_generation=generation, event_key='http-stop-owner-reason-thread'))
                for _ in range(200):
                    if self.f.plans.records.get(self.owner, 'association-experiment')['phase'] == 'stopping':
                        break
                    await asyncio.sleep(.005)
                self.assertEqual(self.f.plans.records.get(self.owner, 'association-experiment')['phase'], 'stopping')
                decision.cancel()
                decision.cancel()
                await asyncio.sleep(.02)
                self.assertFalse(decision.done())
                self.assertFalse(stopped.done())
                release.set()
                with self.assertRaises(asyncio.CancelledError):
                    await decision
                result = await stopped
                self.assertEqual(result.status_code, 200, result.text)
                self.assertEqual(result.json()['result']['current']['phase'], 'cancelled')
                from contextlib import closing
                with closing(self.assets.store._conn()) as connection:
                    self.assertEqual(connection.execute("SELECT count(*) FROM improvement_events WHERE operation='semantic_owner_arbitration'").fetchone()[0], 0)
            finally:
                release.set()
                await asyncio.gather(decision, *([] if stopped is None else [stopped]), return_exceptions=True)


if __name__ == '__main__':
    unittest.main()
