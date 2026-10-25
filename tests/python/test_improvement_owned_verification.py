"""Actual adapter verification must settle before cancellation leaves the call."""
from _paths import ROOT, SERVER  # noqa: F401

import asyncio
from pathlib import Path
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from improvement_claude import ClaudeTrialAdapter
from improvement_operation_adapter import ClaudeOperationAdapter
from improvement_store import _hash


class OwnedVerificationTests(unittest.IsolatedAsyncioTestCase):
    async def _cancel(self, operation):
        kind = ClaudeOperationAdapter if operation else ClaudeTrialAdapter
        adapter = object.__new__(kind)
        adapter.pin = {"fixture": "no native runtime"}
        adapter.before_engine_start = lambda: None
        # Legacy manifest versions (trial 3, operation 1): the owned-verification path, not the native parent.
        manifest = {"version": 1 if operation else 3, "engine_config_hash": _hash(adapter.pin), "brain_id": "synthetic"}
        adapter._native_boundary = None
        adapter._native = SimpleNamespace(_native_boundary=None)
        adapter.workspace_root = Path("synthetic-unread-workspace")
        adapter.workspace = SimpleNamespace(root=adapter.workspace_root, validate=lambda receipt: manifest)
        entered, release = threading.Event(), threading.Event()

        def verify():
            entered.set()
            if not release.wait(10):
                raise RuntimeError("synthetic verification barrier expired")
            return {"supported": True, "capability_hash": "c" * 64}

        adapter.verify = verify
        identity = {"operation_id": "synthetic-operation", "attempt": 1, "role": "proposer", "purpose": "compose"} if operation else {"trial_id": "synthetic-trial", "attempt": 1}
        request = {"version": 1, **identity, "deadline_at": time.time() + 30,
                   "engine_config_hash": manifest["engine_config_hash"], "capability_hash": "c" * 64}
        receipt = {**identity}
        # Validation is outside this case; run the real adapter generator through
        # its actual preflight boundary without files, SDK or a native launch.
        with patch("improvement_sandbox.TrialWorkspace", return_value=adapter.workspace), patch("improvement_native_transport.execute_worker") as launch:
            stream = adapter.execute(request, receipt)
            task = asyncio.create_task(anext(stream))
            try:
                self.assertTrue(await asyncio.to_thread(entered.wait, 10))
                task.cancel()
                await asyncio.sleep(.05)
                task.cancel()
                await asyncio.sleep(.05)
                self.assertFalse(task.done(), "adapter abandoned its running verification")
                launch.assert_not_called()
            finally:
                release.set()
                await asyncio.gather(task, return_exceptions=True)
                await stream.aclose()
            with self.assertRaises(asyncio.CancelledError):
                await task
            launch.assert_not_called()

    async def test_trial_adapter_repeated_cancel_waits_for_verification(self):
        await self._cancel(False)

    async def test_operation_adapter_repeated_cancel_waits_for_verification(self):
        await self._cancel(True)


if __name__ == "__main__":
    unittest.main()
