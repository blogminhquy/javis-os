"""Real private socket ingress; no native process, account or authority claim."""
from _paths import ROOT, SERVER  # noqa: F401

import asyncio
import socket
import unittest

from improvement_private_channel import PrivateWorkerChannelV2
import test_improvement_native_transport_v2 as fixture


class ClosingObservationTests(unittest.IsolatedAsyncioTestCase):
    owner = fixture.HostGuardianFlowTests.owner
    local_owner = fixture.HostGuardianFlowTests.local_owner

    async def test_validated_usage_rejected_before_account_ack_stays_in_closing_evidence(self):
        owner = self.local_owner()
        owner._invocations = [{'purpose': purpose, 'nonce': str(index + 2) * 64}
            for index, purpose in enumerate(('adapter_version', 'auth_status', 'sdk_version', 'query'))]
        identity = {'trial_id': 'closing-trial', 'attempt': 1, 'input_hash': 'b' * 64}
        binding = dict(kind='trial', launch_nonce=owner._nonce, worker_pid=123, worker_birth=456,
                       identity=identity, invocations=owner._invocations)
        owner._worker_identity = {'worker_pid': 123, 'worker_birth': 456}
        owner._endpoint_event = asyncio.Event(); owner._endpoint_event.set()
        left, right = socket.socketpair()
        host = PrivateWorkerChannelV2(left, binding=binding, role='host', lifetime_timeout=5)
        worker = PrivateWorkerChannelV2(right, binding=binding, role='worker', lifetime_timeout=5)
        owner._private = host
        body = {'type': 'engine_event', **identity,
                'event': {'type': 'usage', 'usage': {'input_tokens': 7, 'output_tokens': None}}}
        try:
            owner._worker_task = owner._task(owner._worker_loop())
            await worker.send(body)
            await asyncio.wait_for(asyncio.shield(owner._worker_task), 1)
            self.assertTrue(owner._stopped)
            self.assertFalse(owner._accounting_acknowledged)
            self.assertIsNotNone(owner._failure)
            self.assertFalse(owner._packets, 'rejected phase must not enter live delivery')
            observations = owner.closing_observations
            self.assertEqual(len(observations), 1, 'received usage was discarded by phase rejection')
            self.assertEqual(observations[0]['body'], body)
            self.assertEqual((observations[0]['source'], observations[0]['source_sequence']), ('worker', 1))
            observations[0]['body']['event']['usage']['input_tokens'] = 999
            self.assertEqual(owner.closing_observations[0]['body']['event']['usage']['input_tokens'], 7)
            await owner.aclose()
            self.assertEqual(len(owner.closing_observations), 1)
        finally:
            await owner.aclose()
            await worker.aclose()


if __name__ == '__main__': unittest.main()
