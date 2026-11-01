"""Team usage projections: real files/index, fake providers, no model calls."""
from _paths import ROOT, SERVER  # noqa: F401
import asyncio
import json
import os
import tempfile
import sqlite3
import unittest
from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import patch
from unittest.mock import AsyncMock

TMP = Path(tempfile.mkdtemp(prefix="team-quality-usage-"))
os.environ["JAVIS_STATE_DIR"] = str(TMP)
os.environ["JAVIS_CLAUDE_PROJECTS_DIR"] = str(TMP / "claude")
os.environ["JAVIS_CODEX_SESSIONS_DIR"] = str(TMP / "codex")
os.environ["JAVIS_NO_REAL_TEAM_ENGINE"] = "1"

import usage_store as us
import usage_index as ui
import turn_context as tc
import team_usage


class UsageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(dir=TMP))
        self.patches = [patch.object(us, "_PATH", self.tmp / "usage.json"),
                        patch.object(us, "_TELEMETRY_ERRORS", {}),
                        patch.object(us, "_EVENTS_PATH", self.tmp / "events.jsonl"),
                        patch.object(ui, "_EVENTS_PATH", self.tmp / "events.jsonl"),
                        patch.object(ui, "DB_PATH", self.tmp / "index.db")]
        for p in self.patches:
            p.start()
        self.addCleanup(lambda: [p.stop() for p in reversed(self.patches)])

    def execution(self, turn="turn-1", **kw):
        return dict(team_id="team-1", task_id="task-1", step_id="step-1", turn_id=turn,
                    execution_id=turn, attempt=1, role="work", job_revision=1, **kw)

    def record(self, tin=100, tout=20, **kw):
        us.record("deepseek", "deepseek-flash", tin, tout,
                  execution=kw.pop("execution", self.execution()), **kw)

    def summary(self):
        return team_usage.task_usage("team-1", "task-1")

    def test_internal_requests_retry_and_replay(self):
        self.record(event_id="request-a")
        self.record(tin=50, event_id="request-b")
        self.record(event_id="request-a")
        self.record(event_id="request-a", execution=self.execution("turn-2"))
        got = self.summary()
        self.assertEqual((got["attempts"], got["requests"], got["tokens_in"]), (2, 3, 250))
        self.assertEqual(got["cost_behavior"], "observe_only")
        self.assertEqual(got["roles"]["work"]["requests"], 3)
        ui.refresh()
        self.assertEqual(self.summary()["tokens_in"], 250)
        self.assertEqual(us.summary()["today"]["total"]["in"], 250)
        self.assertEqual(ui.summary("today", provider="api")["kpi"]["input"], 250)

    def test_provenance_unknown_zero_and_subscription(self):
        self.record(cost=0.0, event_id="reported-zero")
        us.record("openai", "unknown-model", 10, 5, execution=self.execution(), event_id="unknown")
        us.record("anthropic-cli", "claude-sonnet-5", 20, 10, cost=3.0,
                  execution=self.execution("cli"), event_id="fallback", event_kind="cli_fallback")
        got = self.summary()
        self.assertEqual(got["money"]["reported_usd"], 0.0)
        self.assertIsNone(got["money"]["estimated_usd"])
        self.assertEqual(got["money"]["subscription_equivalent_usd"], 3.0)
        self.assertEqual(got["money"]["unknown_requests"], 1)
        self.assertFalse(got["coverage"]["money_complete"])
        self.assertIsNone(got["requests"])

    def test_delayed_detail_replaces_fallback(self):
        ex = self.execution("cli")
        us.record("anthropic-cli", "claude-sonnet-5", 300, 30, cost=2,
                  execution=ex, event_id="total", event_kind="cli_fallback")
        self.assertIsNone(self.summary()["requests"])
        for i, tin in enumerate((100, 200)):
            us.record("anthropic-cli", "claude-sonnet-5", tin, 15, execution=ex,
                      event_id=f"detail-{i}", event_kind="cli_detail")
        got = self.summary()
        self.assertEqual((got["tokens_in"], got["tokens_out"], got["requests"]), (300, 30, 2))
        self.assertEqual(got["money"]["subscription_equivalent_usd"], 2)
        self.assertEqual(got["coverage"]["unresolved_events"], 0)
        self.assertEqual(us.summary()["today"]["total"]["in"], 300)

    def test_unlinked_or_partial_detail_never_adds_to_fallback(self):
        ex = self.execution("cli")
        us.record("codex", "gpt-5", 300, 30, execution=ex, event_kind="cli_fallback")
        us.record("codex", "gpt-5", 100, 10, execution=ex, event_kind="cli_detail")
        got = self.summary()
        self.assertEqual(got["tokens_in"], 300)
        self.assertGreater(got["coverage"]["unresolved_events"], 0)

    def test_interrupted_unknown_tokens_and_background(self):
        us.record("openai", "unknown", None, None, execution=self.execution(),
                  event_kind="execution", status="cancelled")
        self.assertIsNone(self.summary()["tokens_in"])
        self.assertEqual(self.summary()["coverage"]["unobserved_attempts"], 1)
        shared = self.execution("shared")
        shared["task_id"] = None
        us.record("openai", "unknown", 20, 10, execution=shared)
        self.assertEqual(team_usage.team_usage("team-1")["shared"]["tokens_in"], 20)
        self.assertIsNone(self.summary()["tokens_in"])

    def test_context_survives_async_thread_and_key_without_aliasing(self):
        token = tc.bind(tc.make("team", execution=self.execution()))
        try:
            async def read():
                return await asyncio.to_thread(tc.current)
            got = asyncio.run(read())
            self.assertEqual(got["execution"]["task_id"], "task-1")
            key = tc.issue_key()
            got["execution"]["task_id"] = "tampered"
            self.assertEqual(tc.resolve_key(key)["execution"]["task_id"], "task-1")
        finally:
            tc.reset(token)

    def test_fake_api_multiple_requests_and_telemetry_failure_do_not_stop_work(self):
        import aux_engine
        import engine
        async def provider(*args, **kwargs):
            yield {"type": "usage", "input": 10, "output": 2}
            yield {"type": "usage", "input": 20, "output": 3}
            yield {"type": "text", "content": "Finished"}
        eng = aux_engine._ApiAuxEngine("deepseek", "deepseek-flash")
        eng.no_tools = True
        async def collect():
            return [ev async for ev in eng.query("test")]
        token = tc.bind(tc.make("team", execution=self.execution()))
        try:
            with patch.object(aux_engine, "api_key_for", return_value="fake"), \
                    patch.object(engine, "deepseek_stream", provider):
                self.assertEqual(asyncio.run(collect())[-1]["content"], "Finished")
                self.assertEqual(self.summary()["requests"], 2)
                with patch.object(us, "_append_event", side_effect=OSError("telemetry unavailable")):
                    self.assertEqual(asyncio.run(collect())[-1]["content"], "Finished")
                self.assertEqual(eng.model, "deepseek-flash")
                self.assertGreater(self.summary()["coverage"]["telemetry_errors"], 0)
        finally:
            tc.reset(token)

    def test_host_factory_binds_text_turn_and_keeps_cancelled_usage(self):
        import main
        import team_engine
        captured = []
        class Fake:
            model = "claude-sonnet-5"
            session_id = "new-session"
            def is_available(self):
                captured.append(tc.current())
                return True
            async def query(self, prompt):
                captured.append(tc.current())
                yield {"type": "usage", "input_tokens": 15, "output_tokens": 4}
                raise asyncio.CancelledError()
        spec = {"provider": "anthropic-cli", "model": "claude-sonnet-5", "note": ""}
        team = {"team_id": "team-1", "brain_id": str(self.tmp), "session_id": ""}
        async def started(*args):
            return None
        with patch.object(main, "_team_agent_info", return_value={"slug": "one"}), \
                patch.object(team_engine, "choose_spec", return_value=spec), \
                patch.object(team_engine, "build", return_value=Fake()), \
                patch.object(main.claude_cli, "cancel_all"):
            _, _, run = main._team_engine_for(team, "one", "plan")
            with self.assertRaises(asyncio.CancelledError):
                asyncio.run(run(dict(team_id="team-1", task_id="task-1", step_id="step-1", turn_id="turn-1",
                                     attempt=2, job_revision=3, system="system", prompt="prompt",
                                     tool_turn=False, engine_started=started)))
        self.assertEqual(captured[0]["execution"]["job_revision"], 3)
        self.assertEqual(captured[1]["execution"]["role"], "plan")
        got = self.summary()
        self.assertEqual((got["tokens_in"], got["tokens_out"]), (15, 4))
        self.assertEqual(got["statuses"].get("cancelled"), 1)
        self.assertIsNone(tc.current())

    def test_real_api_tool_loop_counts_http_retry_and_each_internal_request(self):
        import aux_engine
        import engine
        import mcp_hub
        import mcp_client
        import httpx
        responses = [httpx.ReadError("connection cut"),
                     {"id": "req-1", "usage": {"prompt_tokens": 100, "completion_tokens": 10, "cost": 0.5},
                      "choices": [{"message": {"tool_calls": [{"id": "call-1", "type": "function",
                          "function": {"name": "read_fixture", "arguments": "{}"}}]}}]},
                     {"id": "req-2", "usage": {"prompt_tokens": 150, "completion_tokens": 20},
                      "choices": [{"message": {"content": "Verified"}}]}]
        calls = []
        class Client:
            def __init__(self, **kwargs):
                pass
            async def __aenter__(self):
                return self
            async def __aexit__(self, *args):
                return False
            async def post(self, url, **kwargs):
                calls.append(kwargs["json"])
                result = responses.pop(0)
                if isinstance(result, Exception):
                    raise result
                return httpx.Response(200, json=result)

            # 0.438.5: tool-loop rounds stream by default, so the same replies also come as SSE chunks.
            # Every attempt must still count as one request, the dropped one included.
            @asynccontextmanager
            async def stream(self, method, url, **kwargs):
                calls.append(kwargs["json"])
                result = responses.pop(0)
                if isinstance(result, Exception):
                    raise result
                msg = result["choices"][0]["message"]
                delta = {"content": msg["content"]} if msg.get("content") else {
                    "tool_calls": [dict(tc, index=i) for i, tc in enumerate(msg.get("tool_calls") or [])]}
                chunks = [{"id": result["id"], "choices": [{"index": 0, "delta": delta}]},
                          {"id": result["id"], "choices": [], "usage": result["usage"]}]
                body = "".join(f"data: {json.dumps(c)}\n\n" for c in chunks) + "data: [DONE]\n\n"
                yield httpx.Response(200, headers={"content-type": "text/event-stream"}, content=body.encode())

            async def aclose(self):
                return None
        eng = aux_engine._ApiAuxEngine("deepseek", "deepseek-flash")
        tools = [{"fn": "read_fixture", "description": "Read fixture", "schema": {"type": "object"}}]
        async def collect():
            return [e async for e in eng.query("Check the fixture")]
        token = tc.bind(tc.make("team", execution=self.execution()))
        try:
            with patch.object(aux_engine, "api_key_for", return_value="fake"), \
                    patch.object(mcp_hub, "discover_all", AsyncMock(return_value=(tools, {}))), \
                    patch.object(mcp_client, "call_route", AsyncMock(return_value="fixture")), \
                    patch.object(engine.httpx, "AsyncClient", Client), \
                    patch.object(engine, "_jittered_backoff", return_value=0):
                self.assertEqual(asyncio.run(collect())[-1]["content"], "Verified")
        finally:
            tc.reset(token)
        got = self.summary()
        self.assertEqual(len(calls), 3)
        self.assertEqual(got["requests"], 3)
        self.assertEqual((got["tokens_in"], got["tokens_out"]), (250, 30))
        self.assertFalse(got["coverage"]["tokens_complete"])
        self.assertEqual(got["money"]["reported_usd"], 0.5)

    def test_partial_token_fields_are_not_invented_as_zero(self):
        self.record(tin=10, tout=None)
        got = self.summary()
        self.assertEqual(got["tokens_in"], 10)
        self.assertIsNone(got["tokens_out"])
        self.assertFalse(got["coverage"]["tokens_complete"])
        self.assertEqual(got["money"]["unknown_requests"], 1)

    def test_delayed_raw_claude_detail_reconciles_only_new_sessions(self):
        rawdir = self.tmp / "claude"
        rawdir.mkdir()
        with patch.dict(os.environ, {"JAVIS_CLAUDE_PROJECTS_DIR": str(rawdir)}):
            ex = self.execution("cli", cli_session_id="fresh", cli_session_new=True)
            us.record("anthropic-cli", "claude-sonnet-5", 300, 30, cost=2,
                      execution=ex, event_kind="cli_fallback")
            self.assertIsNone(self.summary()["requests"])
            rows = [{"type": "assistant", "sessionId": "fresh", "entrypoint": "sdk",
                     "timestamp": "2026-10-22T12:00:00Z", "message": {
                         "id": f"msg-{n}", "model": "claude-sonnet-5", "usage": {
                             "input_tokens": tin, "output_tokens": 15}}} for n, tin in enumerate((100, 200))]
            (rawdir / "session.jsonl").write_text("".join(json.dumps(x) + "\n" for x in rows), encoding="utf-8")
            ui.refresh()
            got = self.summary()
            self.assertEqual((got["tokens_in"], got["requests"]), (300, 2))
            ui.refresh()
            self.assertEqual(self.summary()["tokens_in"], 300)

    def test_streaming_preserves_reported_cost_and_missing_output(self):
        import aux_engine
        import engine
        class Response:
            status_code = 200
            async def aiter_lines(self):
                yield 'data: {"choices":[{"delta":{"content":"Finished"}}]}'
                yield 'data: {"id":"stream-1","usage":{"prompt_tokens":10,"cost":0.125},"choices":[]}'
                yield "data: [DONE]"
        class Client:
            def __init__(self, **kwargs):
                pass
            async def __aenter__(self):
                return self
            async def __aexit__(self, *args):
                return False
            @asynccontextmanager
            async def stream(self, *args, **kwargs):
                yield Response()
        eng = aux_engine._ApiAuxEngine("deepseek", "deepseek-flash")
        eng.no_tools = True
        async def collect():
            return [e async for e in eng.query("test")]
        token = tc.bind(tc.make("team", execution=self.execution()))
        try:
            with patch.object(aux_engine, "api_key_for", return_value="fake"), \
                    patch.object(engine.httpx, "AsyncClient", Client):
                self.assertEqual(asyncio.run(collect())[-1]["content"], "Finished")
                eng.provider = "openrouter"
                self.assertEqual(asyncio.run(collect())[-1]["content"], "Finished")
        finally:
            tc.reset(token)
        got = self.summary()
        self.assertEqual(got["requests"], 2)
        self.assertEqual(got["tokens_in"], 20)
        self.assertIsNone(got["tokens_out"])
        self.assertEqual(got["money"]["reported_usd"], 0.25)

    def test_execution_ledgers_are_coverage_references_never_added_bills(self):
        self.record(cost=0.5)
        with sqlite3.connect(self.tmp / "team.sqlite3") as c:
            c.execute("CREATE TABLE team_turns(turn_id,team_id,task_id,role,engine_at,tokens_in,cost_usd)")
            c.execute("INSERT INTO team_turns VALUES('turn-1','team-1','task-1','work',1,999,9)")
            c.execute("INSERT INTO team_turns VALUES('missing','team-1','task-1','work',1,888,8)")
        with sqlite3.connect(self.tmp / "resonance.sqlite3") as c:
            c.execute("CREATE TABLE agent_calls(id,context_ref,purpose,reason_ref,mirror_ref,attempt,engine_at)")
            c.execute("INSERT INTO agent_calls VALUES(1,'team:team-1','reply','team_turn:turn-1','team_turn:turn-1',1,1)")
            c.execute("INSERT INTO agent_calls VALUES(2,'team:team-1','judge_batch','judge-ref','',1,1)")
        got = self.summary()
        self.assertEqual(got["tokens_in"], 100)
        self.assertEqual(got["money"]["reported_usd"], 0.5)
        self.assertEqual(got["coverage"]["unobserved_attempts"], 1)
        self.assertEqual(got["attempts"], 2)
        team = team_usage.team_usage("team-1")
        self.assertEqual(team["attempts"], 3)
        self.assertEqual(team["coverage"]["unobserved_attempts"], 2)
        self.assertEqual(team["coverage"]["unobserved_by_role"]["judge_batch"], 1)

    def test_persisted_telemetry_gap_survives_process_error_memory_reset(self):
        self.record()
        us.record("deepseek", "deepseek-flash", None, None, execution=self.execution(),
                  event_kind="execution", status="completed", expected_requests=2, telemetry_errors=1)
        us._TELEMETRY_ERRORS.clear()
        got = self.summary()
        self.assertIsNone(got["requests"])
        self.assertEqual(got["coverage"]["missing_requests"], 1)
        self.assertEqual(got["coverage"]["telemetry_errors"], 1)

    def test_host_cli_preserves_each_missing_token_direction(self):
        import main
        import team_engine
        scenarios = [
            ([{"type": "final", "content": "Finished", "tokens_in": 15}], (15, None)),
            ([{"type": "final", "content": "Finished", "tokens_out": 4}], (None, 4)),
            ([{"type": "final", "content": "Finished", "tokens_in": 15, "tokens_out": 0}], (15, 0)),
            ([{"type": "usage", "input_tokens": 15}, {"type": "final", "content": "Finished"}], (15, None)),
            ([{"type": "usage", "output_tokens": 4}, {"type": "final", "content": "Finished"}], (None, 4)),
            ([{"type": "usage", "input_tokens": None, "output_tokens": 0},
              {"type": "final", "content": "Finished"}], (None, 0)),
        ]
        spec = {"provider": "anthropic-cli", "model": "claude-sonnet-5", "note": ""}
        team = {"team_id": "team-1", "brain_id": str(self.tmp), "session_id": ""}
        async def started(*args):
            return None
        for n, (events, expected) in enumerate(scenarios):
            with self.subTest(events=events):
                class Fake:
                    model = "claude-sonnet-5"
                    def is_available(self):
                        return True
                    async def query(self, prompt):
                        for event in events:
                            yield event
                with patch.object(main, "_team_agent_info", return_value={"slug": "one"}), \
                        patch.object(team_engine, "choose_spec", return_value=spec), \
                        patch.object(team_engine, "build", return_value=Fake()):
                    _, _, run = main._team_engine_for(team, "one", "plan")
                    result = asyncio.run(run(dict(team_id="team-1", task_id=f"partial-{n}",
                        turn_id=f"partial-{n}", system="system", prompt="prompt", tool_turn=False,
                        engine_started=started)))
                got = team_usage.task_usage("team-1", f"partial-{n}")
                self.assertEqual((result["tokens_in"], result["tokens_out"]), expected)
                self.assertEqual((got["tokens_in"], got["tokens_out"]), expected)
                self.assertEqual(got["coverage"]["tokens_complete"], None not in expected)
                self.assertEqual(got["statuses"], {"completed": 1})

    def test_outcome_api_adds_complete_directions_and_keeps_incomplete_totals_unknown(self):
        import team_runner
        for events, expected in [
            ([{"input": 10, "output": 2}, {"input": 5, "output": 3}], (15, 5)),
            ([{"input": 10}, {"input": 5, "output": 3}], (15, None)),
            ([{"output": 2}, {"input": 5, "output": 3}], (None, 5)),
            ([{"input": 0, "output": 0}, {"input": 5, "output": 3}], (5, 3)),
        ]:
            with self.subTest(events=events):
                outcome = team_runner.TextOnlyOutcome()
                for event in events:
                    outcome.note({"type": "usage", **event})
                outcome.note({"type": "final", "content": "Finished"})
                result = outcome.result()
                self.assertEqual((result["tokens_in"], result["tokens_out"]), expected)

    def test_host_records_invalid_final_outcomes_as_errors_and_keeps_usage(self):
        import main
        import team_engine
        import team_runner
        spec = {"provider": "anthropic-cli", "model": "claude-sonnet-5", "note": ""}
        team = {"team_id": "team-1", "brain_id": str(self.tmp), "session_id": ""}
        async def started(*args):
            return None
        scenarios = [(None, "no_final"), ({"type": "final", "content": ""}, "empty"),
                     ({"type": "final", "content": "Refresh", "auth_refresh_race": True}, "auth")]
        for n, (final, kind) in enumerate(scenarios):
            with self.subTest(kind=kind):
                class Fake:
                    model = "claude-sonnet-5"
                    def is_available(self):
                        return True
                    async def query(self, prompt):
                        yield {"type": "usage", "input_tokens": 15, "output_tokens": 4}
                        if final is not None:
                            yield final
                with patch.object(main, "_team_agent_info", return_value={"slug": "one"}), \
                        patch.object(team_engine, "choose_spec", return_value=spec), \
                        patch.object(team_engine, "build", return_value=Fake()):
                    _, _, run = main._team_engine_for(team, "one", "plan")
                    with self.assertRaises(team_runner.EngineOutcomeError) as error:
                        asyncio.run(run(dict(team_id="team-1", task_id=f"invalid-{n}",
                            turn_id=f"invalid-{n}", system="system", prompt="prompt", tool_turn=False,
                            engine_started=started)))
                    self.assertEqual(error.exception.kind, kind)
                got = team_usage.task_usage("team-1", f"invalid-{n}")
                self.assertEqual((got["tokens_in"], got["tokens_out"]), (15, 4))
                self.assertEqual(got["statuses"], {"error": 1})


if __name__ == "__main__":
    unittest.main()
