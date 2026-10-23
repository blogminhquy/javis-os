"""Actual owner view controls expose metadata only; current evidence is never a grant."""
from _paths import ROOT, SERVER  # noqa: F401

import asyncio
import json
import threading
import unittest
from unittest.mock import patch

import test_improvement_view_sources as sources
import test_improvement_workflow_api as api_fixtures
from improvement_claude import ClaudeTrialAdapter


class ViewApiTests(sources.SourceFixture, unittest.IsolatedAsyncioTestCase):
    mount = api_fixtures.WorkflowApiTests.mount
    owner_session = api_fixtures.WorkflowApiTests.owner_session
    service_factory = api_fixtures.WorkflowApiTests.service_factory
    read_store = api_fixtures.WorkflowApiTests.read_store
    request = api_fixtures.WorkflowApiTests.request
    post = api_fixtures.WorkflowApiTests.post

    def resolve_brain(self, brain):
        self.factory_calls.append(('brain', threading.get_ident()))
        return self.owner.brain_id if brain == 'brain' else self.owner.brain_id + '-ungranted'

    async def asyncSetUp(self):
        await sources.SourceFixture.asyncSetUp(self)
        self.mount()

    def payload(self, key, generation=None):
        return {'comparison_id': self.comparison['id'], 'expected_generation': self.generation() if generation is None else generation,
            'event_key': key}

    async def test_view_routes_deny_token_before_brain_body_or_service_factory(self):
        paths = [('POST', '/improvement-experiments/invalid/' + action) for action in ('view-freeze', 'view-evidence')]
        paths.append(('GET', '/improvement-experiments/invalid/views/invalid'))
        for method, path in paths:
            self.factory_calls.clear()
            result = await self.client.request(method, path + '?brain=foreign', content=b'invalid',
                headers={'authorization': 'Bearer synthetic-full-token'})
            self.assertEqual(result.status_code, 403, (path, result.text))
            self.assertEqual(self.factory_calls, [])

    async def test_closed_view_controls_reject_caller_proofs_before_service(self):
        for action in ('view-freeze', 'view-evidence'):
            self.factory_calls.clear()
            result = await self.post(action, **(self.payload('deny-view-caller-proof') | {
                'allow_unknown': True, 'native_ready': True, 'variant': 'candidate', 'view_hash': 'a' * 64}))
            self.assertEqual(result.status_code, 400, result.text)
            self.assertNotIn('service', [name for name, _ in self.factory_calls])

    async def test_actual_publication_current_projection_and_cold_history_after_revoke_and_off(self):
        original, counts, generation = self.f.f.f.skill.read_bytes(), self.counts(), self.generation()
        payload = self.payload('http-publish-exact-views', generation)
        with patch.object(ClaudeTrialAdapter, 'verify', side_effect=AssertionError('View controls cannot probe/query native')):
            frozen = await self.post('view-freeze', **payload)
            self.assertEqual(frozen.status_code, 200, frozen.text)
            saved = frozen.json()['result']
            self.assertEqual(saved['generation'], generation + 1)
            self.assertEqual(self.counts(), (2, 2, 1, counts[-1]))
            evidence_payload = self.payload('http-check-current-views')
            current = await self.post('view-evidence', **evidence_payload)
            self.assertEqual(current.status_code, 200, current.text)
        metadata = self.service.views.read_existing(self.owner, self.comparison['id'])
        projection = current.json()['result']
        self.assertEqual(projection['view_binding'], metadata)
        self.assertEqual(projection['evidence_scope'], 'current_view_sources_and_semantics')
        self.assertEqual(set(projection['observational_unknowns']), {'actual_reasoning', 'actual_input_use'})
        for private in ('cli_path', 'private-owner-answer', 'protected_content', '"content"', 'native_ready'):
            self.assertNotIn(private, json.dumps(projection))
        self.assertEqual(self.f.f.f.skill.read_bytes(), original)
        self.host.revoke(self.owner, self.comparison['experiment_id'], expected_generation=1, event_key='http-revoke-view-grant')
        self.assets.set_policy(self.owner, 'off', expected_version=0, event_key='http-view-policy-off')
        with patch.object(self.assets.blobs, 'read', side_effect=AssertionError('Historical freeze replay cannot decrypt')):
            replay = await self.post('view-freeze', **payload)
            self.assertEqual(replay.json(), frozen.json())
        refused = await self.post('view-evidence', **evidence_payload)
        self.assertEqual(refused.status_code, 403, refused.text)
        with patch.object(self.assets.blobs, 'read', side_effect=AssertionError('Cold metadata cannot decrypt')):
            self.factory_calls.clear()
            history = await self.request('GET', '/improvement-experiments/' + self.comparison['experiment_id'] + '/views/' + self.comparison['id'])
            self.assertEqual(history.status_code, 200, history.text)
            self.assertEqual(history.json()['view_binding'], metadata)
            self.assertNotIn('service', [name for name, _ in self.factory_calls])

    async def test_foreign_url_or_brain_cannot_freeze_a_valid_comparison(self):
        counts = self.counts()
        with patch.object(self.assets.blobs, 'read', side_effect=AssertionError('Foreign scope cannot decrypt')):
            for path in ('/improvement-experiments/missing-experiment/view-freeze',
                    '/improvement-experiments/' + self.comparison['experiment_id'] + '/view-freeze?brain=other'):
                result = await self.request('POST', path, json=self.payload('deny-foreign-view-scope'))
                self.assertEqual(result.status_code, 403, (path, result.text))
        self.assertEqual(self.counts(), counts)

    async def test_cancelled_http_publication_stays_owned_and_stop_waits_for_source_thread(self):
        entered, release, settled = threading.Event(), threading.Event(), threading.Event()
        freeze, finish = self.service.views.freeze_comparison, self.service._finish_stop
        generation = self.generation()

        def blocked(*args, **kwargs):
            entered.set()
            try:
                if not release.wait(15):
                    raise AssertionError('Test source thread was not released')
                return freeze(*args, **kwargs)
            finally:
                settled.set()

        def finish_after_source(*args, **kwargs):
            self.assertTrue(settled.is_set(), 'Stop must join its owned view source thread before final settlement')
            return finish(*args, **kwargs)

        with patch.object(self.service.views, 'freeze_comparison', side_effect=blocked), \
                patch.object(self.service, '_finish_stop', side_effect=finish_after_source):
            request = asyncio.create_task(self.post('view-freeze', **self.payload('http-owned-blocked-view-freeze', generation)))
            stopper = None
            try:
                self.assertTrue(await asyncio.to_thread(entered.wait, 5))
                request.cancel()
                stopper = asyncio.create_task(self.service.cancel(self.owner, self.comparison['experiment_id'],
                    expected_generation=generation, event_key='stop-during-owned-view-freeze'))
                with self.assertRaises(asyncio.TimeoutError):
                    await asyncio.wait_for(asyncio.shield(stopper), 5)
            finally:
                release.set()
            with self.assertRaises(asyncio.CancelledError):
                await request
            stopped = await stopper
            self.assertEqual(stopped['current']['phase'], 'cancelled')
        self.assertTrue(settled.is_set())
        self.assertEqual(self.counts()[:3], (0, 0, 0))


if __name__ == '__main__':
    unittest.main()
