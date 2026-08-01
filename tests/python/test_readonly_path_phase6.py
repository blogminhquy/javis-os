from _paths import SERVER  # noqa: E402,F401

import asyncio
import inspect
import json
import sqlite3

from cryptography.fernet import Fernet

from capability_executor import CapabilityExecutor
from capability_registry import CapabilityRegistry
from capability_resolver import DeterministicResolver
from context_compiler import CompileRequest, ContextCompiler, DeterministicQualityGate
from context_runtime import ObserveRuntime
from evidence_store import EvidenceStore
from readonly_path_runtime import ReadonlyPathCanary


def _settings(allocation=10_000, rolling=200_000, profiles=None):
    return {
        "context_runtime": {
            "mode": "canary",
            "canary": {"quota_profiles": [{
                "id": "groq-test", "provider": "groq", "model_pattern": "llama-*",
                "rolling_tpm": rolling, "max_input_tokens": 8000,
                "reserved_output_tokens": 600, "window_seconds": 60,
            }]},
            "readonly_canary": {
                "policy_version": "test-readonly-v1",
                "allocation_basis_points": allocation,
                "channels": ["dashboard"], "provider_kinds": ["api"],
                "min_resolver_score": 0.40,
                "capability_profiles": profiles if profiles is not None else [{
                    "id": "calendar-read", "source_type": "mcp",
                    "name_pattern": "calendar_list", "excerpt_chars": 1200,
                    "lease_ttl_seconds": 60,
                }],
            },
        }
    }


def _tool(schema=None):
    return {
        "fn": "calendar_list", "name": "calendar_list", "server": "calendar",
        "description": "calendar list today events",
        "schema": schema or {
            "type": "object", "properties": {"date": {"type": "string"}},
            "required": ["date"], "additionalProperties": False,
        },
    }


def _fernet_store(runtime, state_dir):
    fernet = Fernet(Fernet.generate_key())
    return EvidenceStore(
        runtime, state_dir,
        encryptor=lambda value: "enc:" + fernet.encrypt(value.encode()).decode(),
        decryptor=lambda value: fernet.decrypt(value[4:].encode()).decode(),
        ready_check=lambda: True,
    )


def _stack(tmp_path, settings=None, tools=None, routes=None, discoverer=None):
    settings = settings or _settings()
    brain = tmp_path / "brain"
    tools = list(tools or [_tool()])
    calls = []

    async def call(args):
        calls.append(dict(args))
        return {"date": args.get("date"), "events": ["review at 09:00"]}

    routes = routes or {
        "calendar_list": {
            "source_type": "mcp", "source_id": "calendar", "effect": "read",
            "required_mode": "readonly", "health": "healthy", "call": call,
        }
    }
    registry = CapabilityRegistry(tmp_path / "registry")
    registry.refresh_tools(brain, tools, routes)
    runtime = ObserveRuntime(tmp_path / "runtime", settings_reader=lambda: settings)
    trace = runtime.start_turn("session-phase6", str(brain), "dashboard")
    trace.registry_revision = registry.revision(brain)
    store = _fernet_store(runtime, tmp_path / "runtime")
    executor = CapabilityExecutor(registry, runtime, store)

    async def default_discover(mode, root):
        return tools, routes

    canary = ReadonlyPathCanary(
        registry, DeterministicResolver(registry), ContextCompiler(registry), runtime,
        executor, lambda: settings, discoverer or default_discover,
    )
    return brain, registry, runtime, trace, store, executor, canary, calls


def test_admission_exposes_one_exact_schema_and_reserves_two_rounds(tmp_path):
    brain, registry, runtime, trace, store, executor, canary, calls = _stack(tmp_path)
    plan = asyncio.run(canary.prepare(
        trace, "calendar list today events", str(brain), "dashboard",
        "groq", "llama-3.3", "api", "actor-1",
    ))
    assert plan.action == "execute" and plan.execution_path == "readonly"
    assert plan.tool_spec["function"]["name"] == "calendar_list"
    assert plan.tool_spec["function"]["parameters"] == _tool()["schema"]
    assert plan.lease.allowed_effect == "read"
    assert plan.lease.schema_hash == registry.schema_hash(_tool()["schema"])
    assert plan.reserved_output_tokens == 1200
    assert plan.reservation_id.startswith("qa_")
    assert plan.estimated_input_tokens < 4000
    assert not calls
    assert runtime.get_task(trace.task_id)["execution_path"] == "readonly"


def test_over_quota_rejects_before_model_tool_or_lease(tmp_path):
    stack = _stack(tmp_path, _settings(rolling=100))
    plan = asyncio.run(stack[6].prepare(
        stack[3], "calendar list today events", str(stack[0]), "dashboard",
        "groq", "llama-3.3", "api", "actor-1",
    ))
    assert plan.action == "reject" and not plan.messages and plan.lease is None
    assert not stack[7]
    db = sqlite3.connect(tmp_path / "runtime" / "runtime.db")
    assert db.execute("SELECT COUNT(*) FROM runtime_capability_leases").fetchone()[0] == 0


def test_conversation_reference_and_write_intent_stay_on_legacy(tmp_path):
    for index, objective in enumerate((
        "calendar list like last time", "delete calendar event today",
    )):
        stack = _stack(tmp_path / str(index))
        plan = asyncio.run(stack[6].prepare(
            stack[3], objective, str(stack[0]), "dashboard",
            "groq", "llama-3.3", "api", "actor-1",
        ))
        assert plan.action == "legacy" and plan.lease is None


def test_schema_validation_one_use_and_encrypted_evidence(tmp_path):
    brain, registry, runtime, trace, store, executor, canary, calls = _stack(tmp_path)
    plan = asyncio.run(canary.prepare(
        trace, "calendar list today events", str(brain), "dashboard",
        "groq", "llama-3.3", "api", "actor-1",
    ))
    invalid = asyncio.run(executor.invoke(
        trace, "actor-1", plan.lease, {"unexpected": True}, plan.route_call
    ))
    assert invalid.status == "FAILED_VALIDATION" and not calls
    assert runtime.get_capability_lease(plan.lease.lease_id)["status"] == "REVOKED"

    # Lease mới cho lượt hợp lệ.
    trace2 = runtime.start_turn("session-phase6-b", str(brain), "dashboard")
    trace2.registry_revision = registry.revision(brain)
    plan2 = asyncio.run(canary.prepare(
        trace2, "calendar list today events", str(brain), "dashboard",
        "groq", "llama-3.3", "api", "actor-2",
    ))

    async def secret_result(args):
        calls.append(dict(args))
        return {"events": ["review"], "api_key": "sk_secret_should_never_persist"}

    result = asyncio.run(executor.invoke(
        trace2, "actor-2", plan2.lease, {"date": "2026-08-01"}, secret_result
    ))
    assert result.status == "SUCCEEDED"
    assert result.evidence.ref.startswith("evidence://task/")
    assert json.loads(store.read_artifact(result.evidence.id))["api_key"] == "[REDACTED]"
    raw_db = (tmp_path / "runtime" / "runtime.db").read_bytes()
    raw_artifact = (tmp_path / "runtime" / result.evidence.artifact_path).read_bytes()
    assert b"sk_secret_should_never_persist" not in raw_db + raw_artifact
    second = asyncio.run(executor.invoke(
        trace2, "actor-2", plan2.lease, {"date": "2026-08-02"}, secret_result
    ))
    assert second.status == "REJECTED"


def test_timeout_persists_invocation_and_keeps_task_state(tmp_path):
    profiles = [{
        "id": "calendar-read", "source_type": "mcp", "name_pattern": "calendar_list",
        "timeout_seconds": 1, "lease_ttl_seconds": 60,
    }]
    brain, registry, runtime, trace, store, executor, canary, calls = _stack(
        tmp_path, _settings(profiles=profiles)
    )
    plan = asyncio.run(canary.prepare(
        trace, "calendar list today events", str(brain), "dashboard",
        "groq", "llama-3.3", "api", "actor-1",
    ))

    async def timeout_call(args):
        await asyncio.sleep(2)

    result = asyncio.run(executor.invoke(
        trace, "actor-1", plan.lease, {"date": "2026-08-01"}, timeout_call
    ))
    assert result.status == "TIMEOUT"
    db = sqlite3.connect(tmp_path / "runtime" / "runtime.db")
    assert db.execute("SELECT status FROM runtime_invocations").fetchone()[0] == "TIMEOUT"
    assert runtime.get_task(trace.task_id)["status"] == "RUNNING"


def test_schema_change_refreshes_and_reresolves_before_any_tool_call(tmp_path):
    old_tool = _tool()
    new_tool = _tool({
        "type": "object", "properties": {"day": {"type": "string"}},
        "required": ["day"], "additionalProperties": False,
    })
    calls = []

    async def live_call(args):
        calls.append(args)
        return {"ok": True}

    new_route = {"calendar_list": {
        "source_type": "mcp", "source_id": "calendar", "effect": "read",
        "required_mode": "readonly", "health": "healthy", "call": live_call,
    }}

    async def discover(mode, root):
        return [new_tool], new_route

    brain, registry, runtime, trace, store, executor, canary, _ = _stack(
        tmp_path, tools=[old_tool], discoverer=discover
    )
    plan = asyncio.run(canary.prepare(
        trace, "calendar list today events", str(brain), "dashboard",
        "groq", "llama-3.3", "api", "actor-1",
    ))
    assert plan.action == "execute"
    assert plan.tool_spec["function"]["parameters"] == new_tool["schema"]
    assert plan.lease.schema_hash == registry.schema_hash(new_tool["schema"])
    assert not calls
    assert any(e["event_type"] == "registry.rebased" for e in runtime.list_events(trace.task_id))


def test_write_and_unconstrained_multiplexed_tools_never_get_a_lease(tmp_path):
    write_tool = _tool()
    write_route = {"calendar_list": {
        "source_type": "mcp", "source_id": "calendar", "effect": "write",
        "required_mode": "safe", "health": "healthy", "call": lambda args: None,
    }}
    stack = _stack(tmp_path / "write", tools=[write_tool], routes=write_route)
    plan = asyncio.run(stack[6].prepare(
        stack[3], "calendar list today events", str(stack[0]), "dashboard",
        "groq", "llama-3.3", "api", "actor",
    ))
    assert plan.action != "execute" and plan.lease is None

    multiplex_route = {"calendar_list": {
        "source_type": "mcp", "source_id": "calendar", "effect": "read",
        "required_mode": "readonly", "health": "healthy", "multiplexed": True,
        "call": lambda args: None,
    }}
    stack2 = _stack(tmp_path / "multi", routes=multiplex_route)
    plan2 = asyncio.run(stack2[6].prepare(
        stack2[3], "calendar list today events", str(stack2[0]), "dashboard",
        "groq", "llama-3.3", "api", "actor",
    ))
    assert plan2.action == "reject" and plan2.reason == "lease_issue_failed"


def test_single_tool_planner_enforces_exact_contract(monkeypatch):
    import engine

    captured = {}

    class Response:
        status_code = 200

        def json(self):
            return {
                "model": "llama-test", "usage": {"prompt_tokens": 10, "completion_tokens": 4},
                "choices": [{"message": {"tool_calls": [{
                    "id": "one", "function": {
                        "name": "calendar_list", "arguments": '{"date":"2026-08-01"}',
                    },
                }]}}],
            }

    class Client:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def post(self, url, headers=None, json=None):
            captured["payload"] = json
            return Response()

    monkeypatch.setattr(engine.httpx, "AsyncClient", Client)
    spec = {"type": "function", "function": {
        "name": "calendar_list", "description": "read calendar",
        "parameters": _tool()["schema"],
    }}
    result = asyncio.run(engine.single_tool_plan(
        "groq", "secret", "llama-test", [{"role": "user", "content": "today"}],
        "off", spec,
    ))
    assert result["status"] == "ok" and result["arguments"]["date"] == "2026-08-01"
    assert captured["payload"]["tools"] == [spec]
    assert captured["payload"]["parallel_tool_calls"] is False
    assert captured["payload"]["tool_choice"]["function"]["name"] == "calendar_list"


def test_anthropic_planner_uses_native_exact_tool_contract(monkeypatch):
    import engine

    captured = {}

    class Response:
        status_code = 200

        def json(self):
            return {
                "model": "claude-test", "usage": {"input_tokens": 8, "output_tokens": 3},
                "content": [{"type": "tool_use", "id": "one", "name": "calendar_list",
                             "input": {"date": "2026-08-01"}}],
            }

    class Client:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def post(self, url, headers=None, json=None):
            captured["payload"] = json
            return Response()

    monkeypatch.setattr(engine.httpx, "AsyncClient", Client)
    spec = {"type": "function", "function": {
        "name": "calendar_list", "description": "read calendar",
        "parameters": _tool()["schema"],
    }}
    result = asyncio.run(engine.single_tool_plan(
        "anthropic-api", "secret", "claude-test",
        [{"role": "system", "content": "core"}, {"role": "user", "content": "today"}],
        "off", spec,
    ))
    assert result["status"] == "ok"
    assert captured["payload"]["tools"][0]["input_schema"] == _tool()["schema"]
    assert captured["payload"]["tool_choice"] == {
        "type": "tool", "name": "calendar_list", "disable_parallel_tool_use": True,
    }


def test_main_executor_uses_two_model_rounds_one_tool_and_provenance(tmp_path, monkeypatch):
    import main

    brain, registry, runtime, trace, store, executor, canary, calls = _stack(tmp_path)
    plan = asyncio.run(canary.prepare(
        trace, "calendar list today events", str(brain), "dashboard",
        "groq", "llama-3.3", "api", "actor-1",
    ))
    planner_calls = []
    final_calls = []

    async def fake_plan(*args):
        planner_calls.append(args)
        return {"status": "ok", "arguments": {"date": "2026-08-01"},
                "model": "llama-3.3", "input": 100, "output": 10}

    async def final_events():
        yield {"type": "meta", "model": "llama-3.3"}
        yield {"type": "usage", "input": 120, "output": 30}
        yield {"type": "text", "content": "Anh có một lịch review lúc 09:00."}

    def fake_stream(*args):
        final_calls.append(args)
        return final_events()

    class WS:
        def __init__(self):
            self.events = []

        async def send_text(self, raw):
            self.events.append(json.loads(raw))

    monkeypatch.setattr(main.engine, "single_tool_plan", fake_plan)
    monkeypatch.setattr(main, "_api_stream", fake_stream)
    monkeypatch.setattr(main, "_CAPABILITY_EXECUTOR", executor)
    monkeypatch.setattr(main, "_CONTEXT_COMPILER", canary.compiler)
    monkeypatch.setattr(main, "_CONTEXT_RUNTIME", runtime)
    monkeypatch.setattr(main, "_QUALITY_GATE", DeterministicQualityGate())
    monkeypatch.setattr(main.usage_store, "record", lambda *args, **kwargs: None)
    ws = WS()
    text, _ = asyncio.run(main._execute_readonly_path(
        plan, "groq", "secret", "llama-3.3", "off", ws, "sid", trace,
        "calendar list today events", "actor-1",
    ))
    assert len(planner_calls) == 1 and len(final_calls) == 1 and len(calls) == 1
    assert "evidence://" in text
    assert [x["type"] for x in ws.events].count("tool_call") == 1
    completed = [e for e in runtime.list_events(trace.task_id)
                 if e["event_type"] == "readonly_path.completed"]
    assert completed and completed[0]["payload"]["model_rounds"] == 2
    source = inspect.getsource(main._execute_readonly_path)
    assert "_api_stream_mcp" not in source and "compaction." not in source


def test_phase6_defaults_and_migration_are_non_impacting(tmp_path):
    source = (SERVER / "config.py").read_text(encoding="utf-8")
    assert '"mode": "shadow"' in source
    block = source.split('"readonly_canary":', 1)[1]
    assert '"allocation_basis_points": 0' in block
    assert '"capability_profiles": []' in block

    runtime = ObserveRuntime(tmp_path, settings_reader=lambda: _settings())
    runtime._conn()
    db = sqlite3.connect(tmp_path / "runtime.db")
    tables = {row[0] for row in db.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    )}
    assert {"runtime_capability_leases", "runtime_invocations", "runtime_evidence"} <= tables


def test_quality_gate_requires_provenance_and_rejects_false_action_claim():
    gate = DeterministicQualityGate()
    ref = "evidence://task/t/step/s/ev_x"
    missing = gate.evaluate("x", "Có một sự kiện.", "dashboard",
                            expected_evidence_ref=ref, read_only=True)
    assert "evidence_ref_missing" in missing.reasons
    false_action = gate.evaluate(
        "x", f"Đã gửi email. {ref}", "dashboard",
        expected_evidence_ref=ref, read_only=True,
    )
    assert "false_action_claim" in false_action.reasons
