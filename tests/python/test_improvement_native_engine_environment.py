"""Actual engine setup must not alter an owned client's sealed environment."""
from _paths import ROOT, SERVER  # noqa: F401

import asyncio
import os
import unittest
from unittest.mock import patch

import test_improvement_claude as fixture


class EngineEnvironmentTests(unittest.TestCase):
    setUp = fixture.ProfileTests.setUp
    profile = fixture.ProfileTests.profile
    engine = fixture.ProfileTests.engine

    def test_owned_factory_observes_exact_environment_before_any_connection(self):
        class ConstructionReached(Exception): pass
        for configured in (None, '900'):
            with self.subTest(configured=configured), patch.dict(os.environ):
                os.environ.pop('CLAUDE_CODE_STREAM_CLOSE_TIMEOUT', None)
                os.environ.pop('JAVIS_CLAUDE_INIT_TIMEOUT', None)
                if configured is not None: os.environ['JAVIS_CLAUDE_INIT_TIMEOUT'] = configured
                expected, observed = dict(os.environ), []
                profile = self.profile()
                def create_client(options):
                    observed.append(dict(os.environ))
                    raise ConstructionReached()
                profile.create_client = create_client
                engine = self.engine(profile)
                async def run():
                    with patch.object(engine, 'is_available', return_value=True), \
                            patch('claude_agent_sdk.ClaudeSDKClient', side_effect=AssertionError('factory bypass')):
                        return [event async for event in engine.query('Pinned input')]
                with self.assertRaises(ConstructionReached): asyncio.run(run())
                self.assertEqual(len(observed), 1)
                # Failure output may name changed keys, never ambient values.
                for snapshot in (observed[0], dict(os.environ)):
                    changed = sorted(key for key in snapshot.keys() | expected.keys()
                                     if snapshot.get(key) != expected.get(key))
                    self.assertEqual(changed, [], 'engine altered environment before owned transport construction')

    def test_legacy_profile_retains_startup_timeout_before_default_constructor(self):
        class ConstructionReached(Exception): pass
        with patch.dict(os.environ):
            os.environ.pop('CLAUDE_CODE_STREAM_CLOSE_TIMEOUT', None)
            os.environ.pop('JAVIS_CLAUDE_INIT_TIMEOUT', None)
            observed = []
            def default_client(*, options):
                observed.append(os.environ.get('CLAUDE_CODE_STREAM_CLOSE_TIMEOUT'))
                raise ConstructionReached()
            engine = self.engine(self.profile())
            async def run():
                with patch.object(engine, 'is_available', return_value=True), \
                        patch('claude_agent_sdk.ClaudeSDKClient', side_effect=default_client):
                    return [event async for event in engine.query('Pinned input')]
            with self.assertRaises(ConstructionReached): asyncio.run(run())
            self.assertEqual(observed, ['300000'])


if __name__ == '__main__': unittest.main()
