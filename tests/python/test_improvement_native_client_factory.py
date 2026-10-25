"""Actual engine query with a trusted profile factory; no native/client request."""
from _paths import ROOT, SERVER  # noqa: F401

import asyncio
import unittest
from unittest.mock import AsyncMock, patch

import test_improvement_claude as fixture


class NativeClientFactoryTests(unittest.TestCase):
    setUp = fixture.ProfileTests.setUp
    profile = fixture.ProfileTests.profile
    engine = fixture.ProfileTests.engine

    def run_query(self, profile):
        async def run():
            engine = self.engine(profile)
            with patch.object(engine, 'is_available', return_value=True), \
                    patch('claude_agent_sdk.ClaudeSDKClient', side_effect=AssertionError('default client bypassed native factory')), \
                    patch('claude_token_gate.xep_hang', new=AsyncMock(return_value='')):
                return [event async for event in engine.query('Pinned input')]
        return asyncio.run(run())

    def test_actual_query_uses_profile_factory_before_connect_and_accounting_ack(self):
        from claude_agent_sdk import ResultMessage
        order, supplied = [], []

        class Client:
            async def connect(self): order.append('connect')
            async def query(self, prompt): order.append(('query', prompt))
            async def receive_response(self):
                yield ResultMessage('success', 0, 0, False, 1, 'session', result='Exact final\r\n')
            async def disconnect(self): order.append('disconnect')

        async def acknowledge(): order.append('accounting_ack')
        def create_client(options):
            order.append('factory')
            supplied.append(options)
            return Client()

        profile = self.profile(acknowledge)
        profile.create_client = create_client
        events = self.run_query(profile)
        self.assertEqual(order, ['factory', 'connect', 'accounting_ack', ('query', 'Pinned input'), 'disconnect'])
        self.assertEqual(len(supplied), 1)
        self.assertEqual((supplied[0].model, supplied[0].effort, supplied[0].system_prompt),
                         (profile.pin['model'], profile.pin['reasoning'], profile.system_prompt))
        self.assertEqual([item['content'] for item in events if item['type'] == 'artifact'], ['Exact final\r\n'])
        self.assertIsNone(next(item for item in events if item['type'] == 'usage')['usage'])

    def test_factory_failure_never_falls_back_or_starts_accounted_query(self):
        order = []
        class FactoryFailure(Exception): pass
        async def acknowledge(): order.append('accounting_ack')
        def create_client(options):
            order.append('factory')
            raise FactoryFailure('owned native transport unavailable')
        profile = self.profile(acknowledge)
        profile.create_client = create_client
        with self.assertRaises(FactoryFailure): self.run_query(profile)
        self.assertEqual(order, ['factory'])


if __name__ == '__main__': unittest.main()
