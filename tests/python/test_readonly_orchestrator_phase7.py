from _paths import SERVER  # noqa: E402,F401

import asyncio
import inspect
import json
import sqlite3
import time

from cryptography.fernet import Fernet

import engine
from capability_executor import CapabilityExecutor
from capability_registry import CapabilityRegistry
from capability_resolver import DeterministicResolver
from context_compiler import ContextCompiler, DeterministicQualityGate
from context_runtime import ObserveRuntime
from evidence_store import EvidenceStore
from readonly_orchestrator import ReadonlyOrchestrator


def _settings(allocation=10_000, rolling=500_000, max_parallel=2,
              max_task_input=100_000, profiles=None, min_gain=0.20):
    return {
        "context_runtime": {
            "mode": "canary",
            "orchestrator_canary": {
                "policy_version": "test-orchestrator-v1",
                "allocation_basis_points": allocation,
                "channels": ["dashboard"], "provider_kinds": ["api"],
                "min_resolver_score": 0.18, "max_candidate_manifests": 8,
                "max_cycles": 2, "max_total_steps": 4,
                "max_parallel": max_parallel, "max_model_rounds": 8,
                "max_evidence": 4, "max_task_input_tokens": max_task_input,
                "max_task_output_tokens": 5000, "max_cost_usd": 1.0,
                "deadline_seconds": 60, "planner_output_tokens": 200,
                "argument_output_tokens": 150, "per_evidence_excerpt_chars": 800,
                "min_information_gain": min_gain,
                "quota_profiles": [{
                    "id": "groq-priced-test", "provider": "groq",
                    "model_pattern": "llama-*", "rolling_tpm": rolling,
                    "max_input_tokens": 20_000, "reserved_output_tokens": 500,
                    "window_seconds": 60, "input_cost_per_million": 0.10,
                    "output_cost_per_million": 0.20,
                }],
                "capability_profiles": profiles if profiles is not None else [{
                    "id": "read-lists", "source_type": "mcp",
                    "name_pattern": "*_list", "excerpt_chars": 800,
                    "lease_ttl_seconds": 60, "timeout_seconds": 10,
                }],
            },
        }
    }


def _tools():
    schema = {
        "type": "object", "properties": {"query": {"type": "string"}},
        "required": ["query"], "additionalProperties": False,
    }
    return [
        {"fn": "calendar_list", "name": "calendar_list", "server": "calendar",
         "description": "calendar project review status schedule list", "schema": schema},
        {"fn": "tasks_list", "name": "tasks_list", "server": "tasks",
         "description": "tasks project review status todo list", "schema": schema},
        {"fn": "notes_list", "name": "notes_list", "server": "notes",
         "description": "notes project review status document list", "schema": schema},
    ]


def _crypto():
    fernet = Fernet(Fernet.generate_key())
    encrypt = lambda value: "enc:" + fernet.encrypt(value.encode()).decode()
    decrypt = lambda value: fernet.decrypt(value[4:].encode()).decode()
    return encrypt, decrypt


def _stack(tmp_path, settings=None, route_call=None, crypto=None):
    settings = settings or _settings()
    brain = tmp_path / "brain"
    tools = _tools()
    calls = []

    async def default_call(name, args):
        calls.append((name, dict(args)))
        return {"source": name, "items": [f"{name}:{args.get('query')}"]}

    routes = {}
    for tool in tools:
        name = tool["name"]

        async def call(args, current=name):
            if route_call:
                return await route_call(current, args, calls)
            return await default_call(current, args)

        routes[name] = {
            "source_type": "mcp", "source_id": tool["server"], "effect": "read",
            "required_mode": "readonly", "health": "healthy", "call": call,
        }
    registry = CapabilityRegistry(tmp_path / "registry")
    registry.refresh_tools(brain, tools, routes)
    runtime = ObserveRuntime(tmp_path / "runtime", settings_reader=lambda: settings)
    trace = runtime.start_turn("phase7-session", str(brain), "dashboard")
    trace.registry_revision = registry.revision(brain)
    encrypt, decrypt = crypto or _crypto()
    store = EvidenceStore(
        runtime, tmp_path / "runtime", encryptor=encrypt, decryptor=decrypt,
        ready_check=lambda: True,
    )
    executor = CapabilityExecutor(registry, runtime, store)

    async def discover(mode, root):
        return tools, routes

    orchestrator = ReadonlyOrchestrator(
        registry, DeterministicResolver(registry), ContextCompiler(registry), runtime,
        executor, lambda: settings, discover, DeterministicQualityGate(),
        state_encryptor=encrypt, state_decryptor=decrypt,
    )
    return {
        "brain": brain, "tools": tools, "routes": routes, "registry": registry,
        "runtime": runtime, "trace": trace, "store": store, "executor": executor,
        "orchestrator": orchestrator, "calls": calls, "encrypt": encrypt,
        "decrypt": decrypt, "settings": settings,
    }


async def _prepare(stack, actor="actor-7"):
    return await stack["orchestrator"].prepare(
        stack["trace"], "calendar tasks project review status",
        str(stack["brain"]), "dashboard", "groq", "llama-test", "api", actor,
    )


def _model_stub(plan_steps=None, invalid=False, call_log=None):
    plan_steps = plan_steps or [
        {"id": "calendar", "capability_id": "", "objective": "calendar review",
         "depends_on": []},
        {"id": "tasks", "capability_id": "", "objective": "tasks review",
         "depends_on": []},
    ]

    async def fake(provider, api_key, model, messages, reasoning, spec):
        name = spec["function"]["name"]
        if call_log is not None:
            call_log.append(name)
        if name == "submit_read_plan":
            enum = spec["function"]["parameters"]["properties"]["steps"]["items"][
                "properties"]["capability_id"]["enum"]
            if invalid:
                args = {"steps": [{
                    "id": "bad", "capability_id": enum[0], "objective": "bad",
                    "depends_on": ["missing"],
                }], "completion_criteria": "invalid dependency"}
            else:
                steps = []
                for index, template in enumerate(plan_steps[:len(enum)]):
                    steps.append({**template, "capability_id": enum[index]})
                args = {"steps": steps, "completion_criteria": "all reads returned"}
            return {"status": "ok", "arguments": args, "model": model,
                    "input": 40, "output": 10}
        return {"status": "ok", "arguments": {"query": name}, "model": model,
                "input": 30, "output": 8}

    return fake


def _final_generator(*args):
    async def events():
        yield {"type": "meta", "model": args[2]}
        yield {"type": "usage", "input": 60, "output": 20}
        yield {"type": "text", "content": "Tổng hợp project review từ các nguồn đã đọc."}
    return events()


def test_phase7_defaults_and_migration_are_non_impacting(tmp_path):
    source = (SERVER / "config.py").read_text(encoding="utf-8")
    block = source.split('"orchestrator_canary":', 1)[1]
    assert '"allocation_basis_points": 0' in block
    assert '"capability_profiles": []' in block
    runtime = ObserveRuntime(tmp_path, settings_reader=lambda: _settings())
    runtime._conn()
    db = sqlite3.connect(tmp_path / "runtime.db")
    tables = {row[0] for row in db.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    )}
    assert "runtime_checkpoints" in tables
    task_columns = {row[1] for row in db.execute("PRAGMA table_info(runtime_tasks)")}
    assert {"objective_encrypted", "active_state_encrypted", "orchestration_status"} <= task_columns


def test_prepare_requires_multiple_allowlisted_reads_and_keeps_schemas_lazy(tmp_path):
    stack = _stack(tmp_path)
    plan = asyncio.run(_prepare(stack))
    assert plan.action == "execute" and plan.execution_path == "orchestrator"
    assert len(plan.candidates) >= 2 and plan.estimated_input_tokens > 0
    assert plan.estimated_cost_usd <= plan.policy.max_cost_usd
    assert not stack["calls"]
    manifests = [{k: x.get(k) for k in (
        "capability_id", "name", "summary", "capability_revision", "score"
    )} for x in plan.candidates]
    compiled = stack["orchestrator"].compiler.compile_orchestrator_plan(
        plan.compile_request, manifests, [], 2
    )
    wire = json.dumps(compiled.capsule.rendered_request, ensure_ascii=False)
    assert "submit_read_plan" in wire
    assert '"query"' not in wire  # exact MCP argument schema chưa nạp ở planner round


def test_parallel_read_dag_checkpoints_and_returns_provenance(tmp_path, monkeypatch):
    active = {"now": 0, "max": 0}

    async def route(name, args, calls):
        calls.append((name, dict(args)))
        active["now"] += 1
        active["max"] = max(active["max"], active["now"])
        await asyncio.sleep(0.03)
        active["now"] -= 1
        return {"source": name, "items": [name + " result"]}

    stack = _stack(tmp_path, route_call=route)
    monkeypatch.setattr(engine, "single_tool_plan", _model_stub())
    plan = asyncio.run(_prepare(stack))
    emitted = []

    async def emit(kind, payload):
        emitted.append((kind, payload))

    result = asyncio.run(stack["orchestrator"].run(
        plan, "secret", "off", emit, _final_generator
    ))
    assert result.status == "COMPLETED"
    assert result.model_rounds == 4
    assert len(stack["calls"]) == 2 and active["max"] == 2
    assert len(result.evidence_refs) == 2 and all(
        ref in result.text for ref in result.evidence_refs
    )
    assert [x[0] for x in emitted].count("tool_call") == 2
    checkpoint = stack["runtime"].load_orchestrator_checkpoint(plan.trace.task_id)
    state = json.loads(stack["decrypt"](checkpoint["checkpoint"]["state_encrypted"]))
    assert state["status"] == "COMPLETED" and state["model_rounds"] == 4
    assert state["budget"]["used_cost_usd"] > 0


def test_checkpoint_encrypts_objective_state_and_tool_arguments(tmp_path, monkeypatch):
    stack = _stack(tmp_path)
    monkeypatch.setattr(engine, "single_tool_plan", _model_stub())
    plan = asyncio.run(_prepare(stack, actor="private-actor"))
    asyncio.run(stack["orchestrator"].run(
        plan, "secret", "off", None, _final_generator
    ))
    raw = (tmp_path / "runtime" / "runtime.db").read_bytes()
    assert b"calendar tasks project review status" not in raw
    assert b'"query":"calendar_list"' not in raw
    task = stack["runtime"].get_task(plan.trace.task_id)
    assert task["objective_encrypted"].startswith("enc:")
    assert task["active_state_encrypted"].startswith("enc:")


def test_resume_reconciles_successful_read_without_repeating_tool(tmp_path, monkeypatch):
    crypto = _crypto()
    stack = _stack(tmp_path, crypto=crypto)
    plan = asyncio.run(_prepare(stack, actor="resume-actor"))
    state = stack["orchestrator"]._initial_state(plan)
    assert stack["orchestrator"]._checkpoint(plan.trace, state, initialize=True)
    capability = plan.candidates[0]
    child = stack["runtime"].create_child_step(
        plan.trace, "read", "objective-hash"
    )
    state["cycle"] = 1
    state["status"] = "EXECUTING"
    state["used_capability_ids"] = [capability["capability_id"]]
    state["steps"] = [{
        "id": "resume-read", "capability_id": capability["capability_id"],
        "objective": "calendar review", "depends_on": [], "status": "RUNNING",
        "child_step_id": child.step_id, "evidence_ref": "", "error_code": "",
        "attempt": 1,
    }]
    assert stack["orchestrator"]._checkpoint(plan.trace, state)
    lease = stack["executor"].issue_lease(
        child, "resume-actor", str(stack["brain"]), capability,
        plan.profiles[capability["capability_id"]],
    )
    invocation = asyncio.run(stack["executor"].invoke(
        child, "resume-actor", lease, {"query": "calendar_list"},
        plan.routes[capability["capability_id"]]["call"],
    ))
    assert invocation.status == "SUCCEEDED" and len(stack["calls"]) == 1
    task_id = plan.trace.task_id
    stack["runtime"].close()

    runtime2 = ObserveRuntime(tmp_path / "runtime", settings_reader=lambda: stack["settings"])
    store2 = EvidenceStore(
        runtime2, tmp_path / "runtime", encryptor=crypto[0], decryptor=crypto[1],
        ready_check=lambda: True,
    )
    executor2 = CapabilityExecutor(stack["registry"], runtime2, store2)

    async def discover(mode, root):
        return stack["tools"], stack["routes"]

    orchestrator2 = ReadonlyOrchestrator(
        stack["registry"], DeterministicResolver(stack["registry"]),
        ContextCompiler(stack["registry"]), runtime2, executor2,
        lambda: stack["settings"], discover, DeterministicQualityGate(),
        state_encryptor=crypto[0], state_decryptor=crypto[1],
    )
    monkeypatch.setattr(engine, "single_tool_plan", _model_stub(call_log=[]))
    result = asyncio.run(orchestrator2.resume(
        task_id, "resume-actor", "groq", "llama-test", "secret", "off", None,
        _final_generator
    ))
    assert result.status == "COMPLETED" and len(stack["calls"]) == 1
    events = runtime2.list_events(task_id)
    reconciled = [x for x in events if x["event_type"] == "orchestrator.resume_reconciled"]
    assert reconciled and reconciled[-1]["payload"]["recovered_steps"] == 1


def test_repeated_invalid_plan_stops_bounded_without_tool_call(tmp_path, monkeypatch):
    stack = _stack(tmp_path)
    calls = []
    monkeypatch.setattr(engine, "single_tool_plan", _model_stub(invalid=True, call_log=calls))
    plan = asyncio.run(_prepare(stack))
    result = asyncio.run(stack["orchestrator"].run(
        plan, "secret", "off", None, _final_generator
    ))
    assert result.status == "FAILED"
    assert result.stop_reason == "repeated_failure"
    assert calls == ["submit_read_plan", "submit_read_plan"]
    assert not stack["calls"] and not result.evidence_refs


def test_task_budget_rejects_before_model_or_tool(tmp_path, monkeypatch):
    stack = _stack(tmp_path, settings=_settings(max_task_input=1000))
    model_calls = []
    monkeypatch.setattr(engine, "single_tool_plan", _model_stub(call_log=model_calls))
    plan = asyncio.run(_prepare(stack))
    assert plan.action == "reject" and plan.reason == "task_budget_preflight_rejected"
    assert not model_calls and not stack["calls"]
    db = sqlite3.connect(tmp_path / "runtime" / "runtime.db")
    assert db.execute("SELECT COUNT(*) FROM runtime_checkpoints").fetchone()[0] == 0


def test_low_marginal_information_gain_stops_without_opening_another_cycle(
        tmp_path, monkeypatch):
    async def duplicate_result(name, args, calls):
        calls.append((name, dict(args)))
        return {"same_verified_fact": True}

    stack = _stack(
        tmp_path, settings=_settings(min_gain=0.75), route_call=duplicate_result
    )
    model_calls = []
    monkeypatch.setattr(engine, "single_tool_plan", _model_stub(call_log=model_calls))
    plan = asyncio.run(_prepare(stack))
    result = asyncio.run(stack["orchestrator"].run(
        plan, "secret", "off", None, _final_generator
    ))
    assert result.stop_reason == "marginal_information_gain"
    assert model_calls.count("submit_read_plan") == 1
    assert len(stack["calls"]) == 2


def test_write_intent_and_missing_price_metadata_never_enter_orchestrator(tmp_path):
    stack = _stack(tmp_path / "write")
    write = asyncio.run(stack["orchestrator"].prepare(
        stack["trace"], "delete calendar and tasks", str(stack["brain"]),
        "dashboard", "groq", "llama-test", "api", "actor",
    ))
    assert write.action == "legacy"

    settings = _settings()
    settings["context_runtime"]["orchestrator_canary"]["quota_profiles"][0].pop(
        "input_cost_per_million"
    )
    stack2 = _stack(tmp_path / "price", settings=settings)
    no_price = asyncio.run(_prepare(stack2))
    assert no_price.action == "legacy" and no_price.reason == "task_budget_metadata_unknown"


def test_parallel_and_sequential_reads_produce_equivalent_evidence(tmp_path, monkeypatch):
    monkeypatch.setattr(engine, "single_tool_plan", _model_stub())
    outputs = []
    for parallel in (1, 2):
        stack = _stack(tmp_path / str(parallel), settings=_settings(max_parallel=parallel))
        plan = asyncio.run(_prepare(stack))
        result = asyncio.run(stack["orchestrator"].run(
            plan, "secret", "off", None, _final_generator
        ))
        checkpoint = stack["runtime"].load_orchestrator_checkpoint(result.task_id)
        state = json.loads(stack["decrypt"](checkpoint["checkpoint"]["state_encrypted"]))
        outputs.append(sorted(x["content_hash"] for x in state["evidence"]))
    assert outputs[0] == outputs[1] and len(outputs[0]) == 2


def test_main_phase7_adapter_buffers_final_and_exposes_task_id(tmp_path, monkeypatch):
    import main

    stack = _stack(tmp_path)
    monkeypatch.setattr(engine, "single_tool_plan", _model_stub())
    plan = asyncio.run(_prepare(stack))
    monkeypatch.setattr(main, "_READONLY_ORCHESTRATOR", stack["orchestrator"])
    monkeypatch.setattr(main, "_api_stream", _final_generator)
    monkeypatch.setattr(main, "_CONTEXT_RUNTIME", stack["runtime"])
    monkeypatch.setattr(main.usage_store, "record", lambda *args, **kwargs: None)

    class WS:
        def __init__(self):
            self.events = []

        async def send_text(self, raw):
            self.events.append(json.loads(raw))

    ws = WS()
    text, model = asyncio.run(main._execute_readonly_orchestrator(
        plan, "groq", "secret", "llama-test", "off", ws, "session", stack["trace"]
    ))
    responses = [x for x in ws.events if x["type"] == "response"]
    assert text and model == "llama-test" and len(responses) == 1
    assert responses[0]["task_id"] == stack["trace"].task_id
    assert len(responses[0]["evidence_refs"]) == 2
    source = inspect.getsource(main._execute_readonly_orchestrator)
    assert "_api_stream_mcp" not in source and "compaction." not in source
