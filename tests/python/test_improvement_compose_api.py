"""Real ASGI owner routes and cold metadata, with no live factory on GET/revoke."""
from _paths import ROOT, SERVER  # noqa: F401
import asyncio
import json
import threading
import unittest
from contextlib import closing, aclosing
from unittest.mock import patch
import httpx
from fastapi import FastAPI
from fastapi.responses import JSONResponse
import improvement_store as IM
from improvement_experiment_api import register, ExperimentApiDeps
import test_improvement_compose_controls as controls


class ComposeApiTests(controls.ComposeControlsTests):
    # Only API tests are collected here; base tests run in their own module.
    async def asyncSetUp(self):
        await super().asyncSetUp()
        self.calls = []
        self.live_service_allowed = True
        self.app = FastAPI()
        def read():
            self.calls.append('read')
            return IM.read_existing(self.assets.store.path, self.assets.blobs)
        def write():
            self.calls.append('write')
            return self.assets
        def service():
            self.calls.append('service')
            if not self.live_service_allowed:
                raise AssertionError('Cold replay cannot construct a live service')
            return self.service
        def resolve(brain):
            self.calls.append('brain')
            return self.owner.brain_id if brain == 'brain' else self.h.f.f.f.host_files.other.brain_id
        def owner(request):
            self.calls.append('owner')
            if request.cookies.get('owner') != 'yes':
                return JSONResponse({'reason': 'owner_session_required'}, status_code=403)
        register(self.app, ExperimentApiDeps(read_store=read, resolve_brain=resolve, owner_session=owner, service=service, write_store=write))
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url='http://test')
        self.addAsyncCleanup(self.client.aclose)
        self.base = '/improvement-experiments/' + self.experiment

    async def request(self, method, route, **kwargs):
        return await self.client.request(method, self.base + route, headers={'cookie': 'owner=yes'}, **kwargs)

    async def test_api_closed_routes_owner_limits_and_path_scope(self):
        for operation in ('compose-preview', 'compose-authorize', 'compose', 'compose-revoke'):
            value = self.payload()
            if operation in ('compose', 'compose-revoke'):
                value['authorization_id'] = self.saved['authorization_id']
            denied = await self.client.post(self.base + '/' + operation + '?brain=other', json=value)
            self.assertEqual(denied.status_code, 403, denied.text)
            self.calls.clear()
            invalid = await self.request('POST', '/' + operation, json={**value, 'input_hash': 'a' * 64})
            self.assertEqual(invalid.status_code, 400, invalid.text)
            self.assertNotIn('service', self.calls)
        too_large = await self.request('POST', '/compose-preview', content=b' ' * (2 * 1024 * 1024 + 1))
        self.assertEqual(too_large.status_code, 413)
        self.assertEqual((await self.request('POST', '/compose-arbitrary', json=self.payload())).status_code, 404)
        self.assertEqual(self.h.rows('improvement_operations'), [])

    async def test_api_preview_authorize_revoke_and_separate_cold_policy_history(self):
        preview = await self.request('POST', '/compose-preview', json=self.payload())
        self.assertEqual(preview.status_code, 200, preview.text)
        consent = await self.request('POST', '/compose-authorize', json=self.payload(event_key='http-explicit-compose-consent'))
        self.assertEqual(consent.status_code, 200, consent.text)
        saved = consent.json()['result']
        before = self.service.records.get(self.owner, self.experiment)
        self.live_service_allowed = False
        self.assets.set_policy(self.owner, 'off', expected_version=0, event_key='http-off-before-cold-metadata')
        self.calls.clear()
        with patch.object(self.assets.blobs, 'read', side_effect=AssertionError('GET cannot decrypt')), \
                patch('improvement_experiment_service.ExperimentService.__init__', side_effect=AssertionError('GET cannot construct service')), \
                patch('improvement_store.ensure', side_effect=AssertionError('GET cannot migrate')):
            for route, key in (('/compose-consents', 'consents'), ('/compositions', 'compositions'), ('/policy', 'policy')):
                response = await self.request('GET', route)
                self.assertEqual(response.status_code, 200, response.text)
                self.assertIn(key, response.json())
                self.assertNotIn(self.owner.brain_id, response.text)
            revoked = await self.request('POST', '/compose-revoke', json=self.payload(
                authorization_id=saved['authorization_id'], expected_generation=1, event_key='http-cold-revoke-compose'))
            self.assertEqual(revoked.status_code, 200, revoked.text)
            self.assertEqual(revoked.json()['result']['status'], 'revoked')
            replay = await self.request('POST', '/compose-authorize', json=self.payload(event_key='http-explicit-compose-consent'))
            self.assertEqual(replay.status_code, 200, replay.text)
            self.assertEqual((replay.json()['result']['generation'], replay.json()['result']['status']), (2, 'revoked'))
        self.assertNotIn('service', self.calls)
        self.assertEqual(self.calls.count('write'), 1)
        self.assertEqual(self.service.records.get(self.owner, self.experiment), before)
        with closing(self.h.store._conn()) as connection:
            connection.execute('UPDATE improvement_schema SET version=7 WHERE id=1')
            connection.commit()
        for route, key in (('/compose-consents', 'consents'), ('/compositions', 'compositions')):
            response = await self.request('GET', route)
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.json()[key], [])
        self.calls.clear()
        response = await self.request('POST', '/compose-revoke', json=self.payload(
            authorization_id=self.saved['authorization_id'], expected_generation=1, event_key='old-schema-cannot-revoke'))
        self.assertEqual(response.status_code, 403)
        self.assertNotIn('write', self.calls)
        response = await self.request('GET', '/compose-consents?brain=other')
        self.assertEqual(response.status_code, 403)

    async def test_api_actual_publication_and_cold_composition_metadata(self):
        self.synthetic_native()
        response = await self.request('POST', '/compose', json=self.payload(authorization_id=self.saved['authorization_id']))
        self.assertEqual(response.status_code, 200, response.text)
        result = response.json()['result']
        self.assertEqual(result['status'], 'keep_base')
        self.calls.clear()
        self.live_service_allowed = False
        with patch.object(self.assets.blobs, 'read', side_effect=AssertionError('History cannot decrypt')):
            replay = await self.request('POST', '/compose', json=self.payload(authorization_id=self.saved['authorization_id']))
            self.assertEqual(replay.status_code, 200, replay.text)
            self.assertEqual(replay.json()['result'], result)
            response = await self.request('GET', '/compositions')
        self.assertEqual(response.status_code, 200, response.text)
        row, = response.json()['compositions']
        self.assertEqual(row['composition_id'], result['composition_id'])
        self.assertEqual(row['outcome'], 'keep_base')
        self.assertFalse(row['business_proof'])
        self.assertNotIn('service', self.calls)
        self.assertEqual(self.h.queries, 1)


    async def test_api_same_event_joins_live_owner_instead_of_returning_interrupted_start(self):
        self.synthetic_native()
        entered, release = asyncio.Event(), asyncio.Event()
        start_replayed = threading.Event()
        from improvement_compose_permissions import ComposePermissions
        original_adapter = self.service.operation_tasks.runner.adapter_factory
        original_replay = ComposePermissions.replay_control
        def replay(metadata, *args, **kwargs):
            result = original_replay(metadata, *args, **kwargs)
            if result[0] and result[1].get('status') == 'operation_recorded':
                start_replayed.set()
            return result
        def blocking(pin, *, workspace, before_engine_start):
            inner = original_adapter(pin, workspace=workspace, before_engine_start=before_engine_start)
            class Adapter:
                def verify(self):
                    return inner.verify()
                async def execute(self, request, receipt, *, on_closing_observations=None):
                    async with aclosing(inner.execute(request, receipt, on_closing_observations=on_closing_observations)) as packets:
                        async for packet in packets:
                            yield packet
                            if packet['body']['type'] == 'worker_ready':
                                entered.set()
                                await release.wait()
            return Adapter()
        self.service.operation_tasks.runner.adapter_factory = blocking
        data = self.payload(authorization_id=self.saved['authorization_id'])
        with patch.object(ComposePermissions, 'replay_control', replay):
            first = asyncio.create_task(self.request('POST', '/compose', json=data))
            await asyncio.wait_for(entered.wait(), 20)
            second = asyncio.create_task(self.request('POST', '/compose', json=data))
            try:
                self.assertTrue(await asyncio.to_thread(start_replayed.wait, 5))
                await asyncio.sleep(0.05)
                finished_before_release = second.done()
            finally:
                release.set()
            first_response, second_response = await asyncio.gather(first, second)
        self.assertFalse(finished_before_release, 'An actual live owner must join the identical request')
        self.assertEqual(first_response.status_code, 200, first_response.text)
        self.assertEqual(second_response.json(), first_response.json())
        self.assertEqual(first_response.json()['result']['status'], 'keep_base')
        self.assertEqual(self.h.queries, 1)

    async def test_api_interrupted_start_replay_never_constructs_live_service(self):
        self.synthetic_native()
        payload = {'authorization_id': self.saved['authorization_id'], 'expected_generation': self.generation}
        begun = await asyncio.to_thread(self.service.composer._begin, self.owner, payload, 'owner-compose-facade')
        self.live_service_allowed = False
        self.calls.clear()
        with patch.object(self.assets.blobs, 'read', side_effect=AssertionError('Cold interrupted replay cannot decrypt')):
            response = await self.request('POST', '/compose', json=self.payload(authorization_id=self.saved['authorization_id']))
        self.assertEqual(response.status_code, 200, response.text)
        result = response.json()['result']
        self.assertEqual((result['status'], result['operation_status']), ('operation_recorded', 'pending'))
        self.assertEqual(result['operation_id'], begun['operation_id'])
        self.assertNotIn('service', self.calls)
        self.assertNotIn('write', self.calls)
        self.assertEqual(self.h.queries, 0)
        self.assertEqual(len(self.h.rows('improvement_operations')), 1)


# Avoid inherited service tests being collected for the second time.
for _name in tuple(vars(controls.ComposeControlsTests)):
    if _name.startswith('test_') and _name not in vars(ComposeApiTests):
        setattr(ComposeApiTests, _name, None)

if __name__ == '__main__':
    unittest.main()
