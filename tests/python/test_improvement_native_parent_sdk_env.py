"""Actual SDK116 builder/owned transport with fake capture/IO, no native child."""
from _paths import ROOT, SERVER  # noqa: F401

import copy
import os
import sys
import unittest

import test_improvement_native_sdk as fixture


@unittest.skipUnless(os.name == 'nt' and sys.flags.isolated,
                     'actual owned SDK builder requires isolated Windows driver')
class ParentSDKEnvironmentTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = fixture.NativeSDKTests.asyncSetUp
    asyncTearDown = fixture.NativeSDKTests.asyncTearDown
    preflight = fixture.NativeSDKTests.preflight
    options = fixture.NativeSDKTests.options
    policy = fixture.NativeSDKTests.policy
    connect = fixture.NativeSDKTests.connect

    async def test_actual_owned_sdk_query_dispatch_matches_purpose_specific_parent_environment(self):
        from improvement_native_parent import _dispatch
        await self.preflight()
        async def completed(*args, **kwargs): pass
        transport = self.owner.transport(self.options(), query_policy=self.policy(), on_user_write=completed)
        await self.connect(transport)
        actual = next(item for item in self.owner._entries if item['purpose'] == 'query')
        # The borrowed component fixture declares source policy independently
        # from its runtime pin. Align only that parent consistency input; the
        # actual SDK-generated argv/environment and captured dispatch stay raw.
        configuration = {**self.owner._pin, 'profile_hash': self.owner._source_hash}
        joined = {'purpose': 'query', 'dispatch': copy.deepcopy(actual['dispatch']),
                  'image': {'comparison': {'selected': {'sha256': configuration['cli_hash']}}}}
        self.assertNotEqual(actual['dispatch']['environment_hash'], self.m._hash(self.env))
        self.assertEqual(actual['environment']['CLAUDE_CODE_ENTRYPOINT'], 'sdk-py')
        self.assertEqual(actual['environment']['PWD'], self.cwd)
        self.assertIsNone(_dispatch(joined, configuration, self.env, self.cwd, self.policy()))


if __name__ == '__main__': unittest.main()
