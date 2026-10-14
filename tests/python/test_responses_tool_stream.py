"""Regression coverage for completed Codex streams with empty output."""
from _paths import ROOT, SERVER
import asyncio
import copy
import json
import unittest
from unittest.mock import patch
import engine
import mcp_client

CALL = {"type": "function_call", "id": "fc1", "call_id": "call1",
        "name": "search", "arguments": '{"query":"BC CHI PHÍ ECOCHIC"}'}
MESSAGE = {"type": "message", "content": [{"type": "output_text", "text": "summary"}]}
def done(item):
    return {"type": "response.output_item.done", "output_index": 0, "item": item}
def completed(output):
    return {"type": "response.completed", "response": {"output": output}}

class Response:
    status_code = 200
    def __init__(self, events): self.events = events
    async def __aenter__(self): return self
    async def __aexit__(self, *args): pass
    async def aiter_lines(self):
        for event in self.events:
            yield 'data: ' + json.dumps(event)

class Client:
    def __init__(self, rounds): self.rounds = iter(rounds); self.inputs = []
    async def __aenter__(self): return self
    async def __aexit__(self, *args): pass
    def stream(self, *args, **kwargs):
        self.inputs.append(copy.deepcopy(kwargs['json']['input']))
        return Response(next(self.rounds))

class ToolStreamTests(unittest.IsolatedAsyncioTestCase):
    async def run_stream(self, rounds):
        client, calls = Client(rounds), []
        async def route(route, name, args):
            calls.append((name, args)); return 'source data'
        with patch.object(engine.httpx, 'AsyncClient', return_value=client), patch.object(mcp_client, 'call_route', side_effect=route):
            events = [event async for event in engine.responses_with_mcp(
                'test', '', 'test', [{"role": "user", "content": "summarize"}],
                'off', [{"fn": "search"}], {})]
        return events, calls, client

    async def test_empty_completed_preserves_tool_and_summary(self):
        events, calls, client = await self.run_stream([
            [done(CALL), done(CALL), completed([])], [done(MESSAGE), completed([])]])
        self.assertEqual(len(calls), 1)
        self.assertEqual(events[-1], {"type": "text", "content": "summary"})
        self.assertTrue(any(i.get('type') == 'function_call_output' for i in client.inputs[1]))

    async def test_completed_output_is_authoritative_and_deduplicated(self):
        other = dict(CALL, name='history')
        events, calls, _ = await self.run_stream([
            [done(CALL), completed([other, other])], [completed([MESSAGE])]])
        self.assertEqual([c[0] for c in calls], ['history'])
        self.assertEqual(events[-1]['content'], 'summary')

    async def test_truncated_stream_cannot_execute_tool(self):
        events, calls, _ = await self.run_stream([[done(CALL)]])
        self.assertFalse(calls)
        self.assertEqual(events[-1]['type'], 'error')

    async def test_truncated_stream_is_retryable(self):
        # A cut stream before anything went out is temporary: the retry wrapper may run it again.
        events, calls, _ = await self.run_stream([[done(CALL)]])
        self.assertTrue(events[-1].get('tam_thoi'))

    async def test_streamed_reasoning_without_encrypted_content_is_not_replayed(self):
        reasoning = {"type": "reasoning", "id": "rs1", "summary": []}
        events, calls, client = await self.run_stream([
            [done(reasoning), done(CALL), completed([])], [completed([MESSAGE])]])
        self.assertEqual(len(calls), 1)
        self.assertFalse(any(i.get('type') == 'reasoning' for i in client.inputs[1]))

    async def test_failed_stream_cannot_execute_tool(self):
        events, calls, _ = await self.run_stream([[done(CALL), {"type": "response.failed", "error": {"message": "failed"}}]])
        self.assertFalse(calls)
        self.assertEqual(events[-1]['type'], 'error')

    async def test_multiple_read_rounds(self):
        history = dict(CALL, id='fc2', call_id='call2', name='history')
        events, calls, _ = await self.run_stream([
            [done(CALL), completed([])], [done(history), completed([])], [completed([MESSAGE])]])
        self.assertEqual([c[0] for c in calls], ['search', 'history'])
        self.assertEqual(events[-1]['content'], 'summary')

if __name__ == '__main__': unittest.main()
