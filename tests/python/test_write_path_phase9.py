"""Phase 9: tool write theo từng capability group.

Tiêu chí nghiệm thu của phase (spec mục 24): duplicate write bằng 0, resume sau
restart không chạy lại action đã hoàn thành, UNKNOWN được reconcile hoặc dừng an
toàn, tool không reconcile được thì về legacy, và audit nối được task/step/
capability revision/provider request id.
"""
from _paths import SERVER  # noqa: E402,F401

import asyncio
import inspect
import json
import sqlite3

from cryptography.fernet import Fernet

import write_path_runtime
from capability_executor import CapabilityExecutor, idempotency_key
from capability_registry import CapabilityRegistry
from capability_resolver import DeterministicResolver
from context_compiler import ContextCompiler
from context_runtime import ObserveRuntime
from evidence_store import EvidenceStore
from write_path_runtime import WritePathCanary, WritePolicy, parse_confirmation


def _profile(**overrides):
    profile = {
        "id": "calendar-write", "source_type": "mcp",
        "name_pattern": "calendar_create", "timeout_seconds": 5,
        "lease_ttl_seconds": 300, "resource_lock_fields": ["calendar_id", "start"],
        "reconcile_capability_id": "", "reconcile_success_marker": "review 09:00",
    }
    profile.update(overrides)
    return profile


def _settings(allocation=10_000, rolling=200_000, profiles=None, mode="canary"):
    return {
        "context_runtime": {
            "mode": mode,
            "canary": {"quota_profiles": [{
                "id": "groq-test", "provider": "groq", "model_pattern": "llama-*",
                "rolling_tpm": rolling, "max_input_tokens": 8000,
                "reserved_output_tokens": 600, "window_seconds": 60,
            }]},
            "write_canary": {
                "policy_version": "test-write-v1",
                "allocation_basis_points": allocation,
                "channels": ["dashboard"], "provider_kinds": ["api"],
                "min_resolver_score": 0.40,
                "capability_profiles": ([_profile(allow_unreconcilable=True)]
                                        if profiles is None else profiles),
            },
        }
    }


def _write_tool(schema=None):
    return {
        "fn": "calendar_create", "name": "calendar_create", "server": "calendar",
        "description": "calendar create event tạo sự kiện lịch",
        "schema": schema or {
            "type": "object",
            "properties": {"calendar_id": {"type": "string"},
                           "start": {"type": "string"},
                           "title": {"type": "string"}},
            "required": ["calendar_id", "start", "title"],
            "additionalProperties": False,
        },
    }


def _read_tool():
    return {
        "fn": "calendar_list", "name": "calendar_list", "server": "calendar",
        "description": "calendar list đọc danh sách sự kiện",
        "schema": {"type": "object", "properties": {}},
    }


def _stack(tmp_path, settings=None, tools=None, routes=None, calls=None):
    settings = settings or _settings()
    brain = tmp_path / "brain"
    calls = calls if calls is not None else []

    async def write_call(args):
        calls.append(dict(args))
        return {"event_id": "evt_1", "title": args.get("title")}

    tools = tools if tools is not None else [_write_tool()]
    routes = routes if routes is not None else {
        "calendar_create": {
            "source_type": "mcp", "source_id": "calendar", "effect": "write",
            "required_mode": "safe", "health": "healthy", "call": write_call,
        }
    }
    registry = CapabilityRegistry(tmp_path / "registry")
    registry.refresh_tools(brain, tools, routes)
    runtime = ObserveRuntime(tmp_path / "runtime", settings_reader=lambda: settings)
    trace = runtime.start_turn("session-phase9", str(brain), "dashboard")
    trace.registry_revision = registry.revision(brain)
    fernet = Fernet(Fernet.generate_key())
    store = EvidenceStore(
        runtime, tmp_path / "runtime",
        encryptor=lambda v: "enc:" + fernet.encrypt(v.encode()).decode(),
        decryptor=lambda v: fernet.decrypt(v[4:].encode()).decode(),
        ready_check=lambda: True,
    )
    executor = CapabilityExecutor(registry, runtime, store)

    async def discover(mode, root):
        return tools, routes

    canary = WritePathCanary(
        registry, DeterministicResolver(registry), ContextCompiler(registry), runtime,
        executor, lambda: settings, discover,
    )
    return brain, registry, runtime, trace, store, executor, canary, calls, routes


def _prepare(stack, objective="tạo sự kiện lịch calendar create event"):
    brain, _registry, _runtime, trace, _store, _executor, canary, _calls, _routes = stack
    return asyncio.run(canary.prepare(
        trace, objective, str(brain), "dashboard", "groq", "llama-3.3", "api", "actor-1"))


# ------------------------------------------------------------------ admission

def test_defaults_ship_disabled_and_fail_closed():
    source = (SERVER / "config.py").read_text(encoding="utf-8")
    block = source.split('"write_canary":', 1)[1]
    assert '"allocation_basis_points": 0' in block
    assert '"capability_profiles": []' in block
    policy = WritePolicy.from_settings({"context_runtime": {"mode": "canary"}})
    assert policy.allocation_basis_points == 0
    assert policy.capability_profiles == ()


def test_no_write_group_enabled_means_no_write(tmp_path):
    stack = _stack(tmp_path, _settings(profiles=[]))
    plan = _prepare(stack)
    assert plan.action == "not_applicable" and plan.reason == "no_write_group_enabled"
    assert not stack[7]


def test_capability_outside_allowlist_falls_back_to_legacy(tmp_path):
    profiles = [_profile(name_pattern="mail_*", allow_unreconcilable=True)]
    stack = _stack(tmp_path, _settings(profiles=profiles))
    plan = _prepare(stack)
    assert plan.action == "legacy" and plan.reason == "capability_not_allowlisted"
    assert not stack[7]


def test_capability_without_reconcile_path_stays_on_legacy(tmp_path):
    """Spec: tool không reconcile được thì dùng legacy, trừ khi operator chấp nhận rõ."""
    stack = _stack(tmp_path, _settings(profiles=[_profile()]))
    plan = _prepare(stack)
    assert plan.action == "legacy" and plan.reason == "capability_cannot_reconcile"


def test_dangerous_and_readonly_capabilities_never_get_a_write_lease(tmp_path):
    danger_routes = {"calendar_create": {
        "source_type": "mcp", "source_id": "calendar", "effect": "dangerous",
        "required_mode": "full", "health": "healthy", "call": lambda args: None,
    }}
    stack = _stack(tmp_path / "danger", routes=danger_routes)
    assert _prepare(stack).action != "propose"

    read_routes = {"calendar_create": {
        "source_type": "mcp", "source_id": "calendar", "effect": "read",
        "required_mode": "readonly", "health": "healthy", "call": lambda args: None,
    }}
    stack2 = _stack(tmp_path / "read", routes=read_routes)
    assert _prepare(stack2).action != "propose"


def test_admission_exposes_one_exact_schema_and_reserves_quota(tmp_path):
    stack = _stack(tmp_path)
    plan = _prepare(stack)
    assert plan.action == "propose" and plan.execution_path == "write"
    assert plan.tool_spec["function"]["name"] == "calendar_create"
    assert plan.tool_spec["function"]["parameters"] == _write_tool()["schema"]
    assert plan.lease.allowed_effect == "write"
    assert plan.reservation_id.startswith("qa_")
    assert not stack[7], "admission tuyệt đối không được gọi tool"


# --------------------------------------------------------------- confirmation

def test_proposal_never_executes_and_requires_an_exact_code(tmp_path):
    stack = _stack(tmp_path)
    brain, _registry, runtime, trace, _store, _executor, canary, calls, _routes = stack
    plan = _prepare(stack)
    args = {"calendar_id": "primary", "start": "2026-08-05T09:00", "title": "Review"}
    registered = canary.register_proposal(trace, plan, args, "session-phase9")
    assert registered["status"] == "prepared"
    assert not calls, "đề xuất không được chạm tool"

    for vague in ("ok", "đồng ý", "ừ làm đi", "yes", "xác nhận"):
        assert canary.pending_for("session-phase9", vague).action != "execute", vague
    confirmed = canary.pending_for(
        "session-phase9", f"XAC NHAN {registered['confirmation_code']}")
    assert confirmed.action == "execute"
    assert confirmed.invocation["status"] == "PREPARED"


def test_confirmation_executes_exactly_once_and_replay_is_refused(tmp_path):
    stack = _stack(tmp_path)
    brain, _registry, runtime, trace, _store, _executor, canary, calls, routes = stack
    plan = _prepare(stack)
    args = {"calendar_id": "primary", "start": "2026-08-05T09:00", "title": "Review"}
    registered = canary.register_proposal(trace, plan, args, "session-phase9")
    call = routes["calendar_create"]["call"]

    first = asyncio.run(canary.execute_confirmed(
        trace, runtime.get_invocation(registered["invocation_id"]), call, args, 5,
        plan.lease.actor_hash))
    assert first["status"] == "SUCCEEDED" and len(calls) == 1

    # Người dùng gõ lại mã lần hai: ledger đã CONSUMED nên không có gì để chạy.
    assert canary.pending_for(
        "session-phase9", f"XAC NHAN {registered['confirmation_code']}"
    ).action != "execute"
    replay = asyncio.run(canary.execute_confirmed(
        trace, runtime.get_invocation(registered["invocation_id"]), call, args, 5,
        plan.lease.actor_hash))
    assert replay["status"] == "REJECTED" and len(calls) == 1


def test_same_intent_twice_reuses_one_idempotency_row(tmp_path):
    stack = _stack(tmp_path)
    brain, _registry, runtime, trace, _store, _executor, canary, calls, _routes = stack
    plan = _prepare(stack)
    args = {"calendar_id": "primary", "start": "2026-08-05T09:00", "title": "Review"}
    first = canary.register_proposal(trace, plan, args, "session-phase9")
    second = canary.register_proposal(trace, plan, args, "session-phase9")
    assert first["status"] == "prepared" and second["status"] == "duplicate"
    assert second["invocation_id"] == first["invocation_id"]
    db = sqlite3.connect(tmp_path / "runtime" / "runtime.db")
    assert db.execute(
        "SELECT COUNT(*) FROM runtime_invocations WHERE effect='write'").fetchone()[0] == 1


def test_second_write_on_the_same_resource_is_locked_out(tmp_path):
    stack = _stack(tmp_path)
    brain, _registry, runtime, trace, _store, _executor, canary, calls, _routes = stack
    plan = _prepare(stack)
    base = {"calendar_id": "primary", "start": "2026-08-05T09:00", "title": "Review"}
    assert canary.register_proposal(trace, plan, base, "session-phase9")["status"] == "prepared"
    other_title = {**base, "title": "Review lần hai"}
    blocked = canary.register_proposal(trace, plan, other_title, "session-phase9")
    assert blocked["status"] == "locked"
    # Tài nguyên khác (slot khác) vẫn đi được.
    other_slot = {**base, "start": "2026-08-06T09:00"}
    assert canary.register_proposal(
        trace, plan, other_slot, "session-phase9")["status"] == "prepared"


def test_arguments_changed_after_approval_are_refused(tmp_path):
    stack = _stack(tmp_path)
    brain, _registry, runtime, trace, _store, _executor, canary, calls, routes = stack
    plan = _prepare(stack)
    args = {"calendar_id": "primary", "start": "2026-08-05T09:00", "title": "Review"}
    registered = canary.register_proposal(trace, plan, args, "session-phase9")
    tampered = {**args, "title": "Chuyển tiền"}
    result = asyncio.run(canary.execute_confirmed(
        trace, runtime.get_invocation(registered["invocation_id"]),
        routes["calendar_create"]["call"], tampered, 5, plan.lease.actor_hash))
    assert result["status"] == "FAILED_VALIDATION" and not calls


# -------------------------------------------------------- UNKNOWN + reconcile

def test_timeout_becomes_unknown_and_is_never_retried(tmp_path):
    stack = _stack(tmp_path)
    brain, _registry, runtime, trace, _store, _executor, canary, calls, _routes = stack
    plan = _prepare(stack)
    args = {"calendar_id": "primary", "start": "2026-08-05T09:00", "title": "Review"}
    registered = canary.register_proposal(trace, plan, args, "session-phase9")

    async def hang(_args):
        calls.append(dict(_args))
        await asyncio.sleep(5)

    result = asyncio.run(canary.execute_confirmed(
        trace, runtime.get_invocation(registered["invocation_id"]), hang, args, 1,
        plan.lease.actor_hash))
    assert result["status"] == "UNKNOWN"
    row = runtime.get_invocation(registered["invocation_id"])
    assert row["status"] == "UNKNOWN" and row["error_code"] == "write_timeout"
    # Lock được GIỮ: không write mới nào được đè lên cùng tài nguyên.
    assert canary.register_proposal(
        trace, plan, {**args, "title": "khác"}, "session-phase9")["status"] == "locked"
    assert len(calls) == 1, "UNKNOWN không bao giờ được chạy lại"


def test_unknown_is_resolved_by_a_read_not_by_rerunning_the_write(tmp_path):
    read_route = {
        "source_type": "mcp", "source_id": "calendar", "effect": "read",
        "required_mode": "readonly", "health": "healthy",
        "call": None,
    }
    calls = []

    async def write_call(args):
        calls.append(dict(args))
        await asyncio.sleep(5)

    async def read_call(_args):
        return {"events": ["review 09:00"]}

    read_route["call"] = read_call
    routes = {
        "calendar_create": {
            "source_type": "mcp", "source_id": "calendar", "effect": "write",
            "required_mode": "safe", "health": "healthy", "call": write_call,
        },
        "calendar_list": read_route,
    }
    tools = [_write_tool(), _read_tool()]
    registry_probe = CapabilityRegistry(tmp_path / "probe")
    registry_probe.refresh_tools(tmp_path / "brain", tools, routes)
    read_id = [x["capability_id"] for x in registry_probe.search("đọc danh sách", tmp_path / "brain", 10)
               if x["name"] == "calendar_list"][0]
    profiles = [_profile(reconcile_capability_id=read_id,
                         reconcile_success_marker="review 09:00")]
    stack = _stack(tmp_path, _settings(profiles=profiles), tools=tools, routes=routes,
                   calls=calls)
    brain, _registry, runtime, trace, _store, _executor, canary, calls, _routes = stack
    plan = _prepare(stack)
    args = {"calendar_id": "primary", "start": "2026-08-05T09:00", "title": "Review"}
    registered = canary.register_proposal(trace, plan, args, "session-phase9")
    result = asyncio.run(canary.execute_confirmed(
        trace, runtime.get_invocation(registered["invocation_id"]),
        write_call, args, 1, plan.lease.actor_hash))
    assert result["status"] == "UNKNOWN"

    reconciled = asyncio.run(canary.reconcile_unknown(
        trace, runtime.get_invocation(registered["invocation_id"]), str(brain),
        profiles[0]))
    assert reconciled["status"] == "SUCCEEDED" and reconciled["landed"] is True
    assert len(calls) == 1, "reconcile chỉ được ĐỌC, không chạy lại write"
    assert runtime.get_invocation(registered["invocation_id"])["status"] == "SUCCEEDED"


def test_restart_marks_running_writes_unknown_without_rerunning(tmp_path):
    stack = _stack(tmp_path)
    brain, registry, runtime, trace, _store, _executor, canary, calls, _routes = stack
    plan = _prepare(stack)
    args = {"calendar_id": "primary", "start": "2026-08-05T09:00", "title": "Review"}
    registered = canary.register_proposal(trace, plan, args, "session-phase9")
    runtime.start_write_invocation(trace, registered["invocation_id"], plan.lease.actor_hash)
    runtime.close()

    # Tiến trình mới trên cùng file DB.
    settings = _settings()
    restarted = ObserveRuntime(tmp_path / "runtime", settings_reader=lambda: settings)
    stale = restarted.sweep_stale_writes(max_running_seconds=0)
    assert [x["id"] for x in stale] == [registered["invocation_id"]]
    row = restarted.get_invocation(registered["invocation_id"])
    assert row["status"] == "UNKNOWN" and row["error_code"] == "process_restart"
    assert not calls, "restart không bao giờ được tự chạy lại write"


def test_completed_write_survives_restart_and_is_not_repeated(tmp_path):
    stack = _stack(tmp_path)
    brain, _registry, runtime, trace, _store, _executor, canary, calls, routes = stack
    plan = _prepare(stack)
    args = {"calendar_id": "primary", "start": "2026-08-05T09:00", "title": "Review"}
    registered = canary.register_proposal(trace, plan, args, "session-phase9")
    asyncio.run(canary.execute_confirmed(
        trace, runtime.get_invocation(registered["invocation_id"]),
        routes["calendar_create"]["call"], args, 5, plan.lease.actor_hash))
    runtime.close()

    settings = _settings()
    restarted = ObserveRuntime(tmp_path / "runtime", settings_reader=lambda: settings)
    assert restarted.sweep_stale_writes(max_running_seconds=0) == []
    assert restarted.get_invocation(registered["invocation_id"])["status"] == "SUCCEEDED"
    # Cùng ý định sau restart vẫn cho ra cùng idempotency key.
    key = idempotency_key(trace.task_id, plan.logical_action_id,
                          plan.lease.capability_id, plan.lease.revision, args)
    assert key == restarted.get_invocation(registered["invocation_id"])["idempotency_key"]
    assert len(calls) == 1


def test_tool_error_is_a_definitive_not_executed_result(tmp_path):
    async def failing(args):
        return "ERROR: calendar rejected the event"

    routes = {"calendar_create": {
        "source_type": "mcp", "source_id": "calendar", "effect": "write",
        "required_mode": "safe", "health": "healthy", "call": failing,
    }}
    stack = _stack(tmp_path, routes=routes)
    brain, _registry, runtime, trace, _store, _executor, canary, _calls, _routes = stack
    plan = _prepare(stack)
    args = {"calendar_id": "primary", "start": "2026-08-05T09:00", "title": "Review"}
    registered = canary.register_proposal(trace, plan, args, "session-phase9")
    result = asyncio.run(canary.execute_confirmed(
        trace, runtime.get_invocation(registered["invocation_id"]), failing, args, 5,
        plan.lease.actor_hash))
    assert result["status"] == "FAILED_FINAL"
    # Lỗi tường minh = chưa chạy, nên lock được nhả và ý định mới đi được.
    assert canary.register_proposal(
        trace, plan, {**args, "title": "thử lại"}, "session-phase9")["status"] == "prepared"


# ------------------------------------------------------------------- audit

def test_audit_links_task_step_revision_and_evidence(tmp_path):
    stack = _stack(tmp_path)
    brain, _registry, runtime, trace, _store, _executor, canary, _calls, routes = stack
    plan = _prepare(stack)
    args = {"calendar_id": "primary", "start": "2026-08-05T09:00", "title": "Review"}
    registered = canary.register_proposal(trace, plan, args, "session-phase9")
    asyncio.run(canary.execute_confirmed(
        trace, runtime.get_invocation(registered["invocation_id"]),
        routes["calendar_create"]["call"], args, 5, plan.lease.actor_hash))
    row = runtime.get_invocation(registered["invocation_id"])
    assert row["task_id"] == trace.task_id and row["step_id"] == trace.step_id
    assert row["capability_revision"] == plan.lease.revision
    assert row["result_evidence_id"] and row["idempotency_key"]
    events = {e["event_type"] for e in runtime.list_events(trace.task_id)}
    assert {"write.prepared", "write.started", "write.finished"} <= events


def test_write_ledger_stores_no_raw_arguments(tmp_path):
    stack = _stack(tmp_path)
    brain, _registry, runtime, trace, _store, _executor, canary, _calls, routes = stack
    plan = _prepare(stack)
    secret_title = "Bí mật không được lưu thô"
    args = {"calendar_id": "primary", "start": "2026-08-05T09:00", "title": secret_title}
    registered = canary.register_proposal(trace, plan, args, "session-phase9")
    asyncio.run(canary.execute_confirmed(
        trace, runtime.get_invocation(registered["invocation_id"]),
        routes["calendar_create"]["call"], args, 5, plan.lease.actor_hash))
    runtime.close()
    raw = (tmp_path / "runtime" / "runtime.db").read_bytes()
    assert secret_title.encode("utf-8") not in raw


def test_confirmation_parser_only_accepts_the_exact_token():
    assert parse_confirmation("XAC NHAN A1B2C3") == ("confirm", "A1B2C3")
    assert parse_confirmation("xác nhận a1b2c3") == ("confirm", "A1B2C3")
    assert parse_confirmation("huỷ") == ("cancel", "")
    assert parse_confirmation("ok em làm đi") == ("", "")
    assert parse_confirmation("xac nhan") == ("", "")


def test_main_confirmation_turn_makes_no_model_call():
    import main
    source = inspect.getsource(main._execute_write_confirmation)
    assert "_api_stream" not in source and "single_tool_plan" not in source
    proposal = inspect.getsource(main._execute_write_proposal)
    assert proposal.count("single_tool_plan") == 1
    assert "route_call" not in proposal, "vòng đề xuất không được gọi tool"


# ------------------------------------------------------------------- chaos

def test_concurrent_confirmations_execute_the_write_exactly_once(tmp_path):
    """Chaos: nhiều lượt xác nhận đồng thời cho cùng ý định."""
    stack = _stack(tmp_path)
    brain, _registry, runtime, trace, _store, _executor, canary, calls, routes = stack
    plan = _prepare(stack)
    args = {"calendar_id": "primary", "start": "2026-08-05T09:00", "title": "Review"}
    registered = canary.register_proposal(trace, plan, args, "session-phase9")
    invocation = runtime.get_invocation(registered["invocation_id"])

    async def race():
        return await asyncio.gather(*[
            canary.execute_confirmed(trace, invocation, routes["calendar_create"]["call"],
                                     args, 5, plan.lease.actor_hash)
            for _ in range(8)
        ], return_exceptions=True)

    results = asyncio.run(race())
    succeeded = [r for r in results if isinstance(r, dict) and r.get("status") == "SUCCEEDED"]
    assert len(succeeded) == 1, results
    assert len(calls) == 1, "duplicate write phải bằng 0"


def test_many_proposals_for_the_same_intent_yield_one_ledger_row(tmp_path):
    """Chaos: người dùng bấm gửi lại nhiều lần cùng một yêu cầu."""
    stack = _stack(tmp_path)
    brain, _registry, runtime, trace, _store, _executor, canary, calls, _routes = stack
    plan = _prepare(stack)
    args = {"calendar_id": "primary", "start": "2026-08-05T09:00", "title": "Review"}
    statuses = [canary.register_proposal(trace, plan, args, "session-phase9")["status"]
                for _ in range(6)]
    assert statuses[0] == "prepared" and set(statuses[1:]) == {"duplicate"}
    db = sqlite3.connect(tmp_path / "runtime" / "runtime.db")
    assert db.execute(
        "SELECT COUNT(*) FROM runtime_invocations WHERE effect='write'").fetchone()[0] == 1
    assert not calls


def test_expired_confirmation_cannot_be_used_and_releases_the_lock(tmp_path):
    settings = _settings()
    settings["context_runtime"]["write_canary"]["confirmation_ttl_seconds"] = 60
    stack = _stack(tmp_path, settings)
    brain, _registry, runtime, trace, _store, _executor, canary, calls, _routes = stack
    plan = _prepare(stack)
    args = {"calendar_id": "primary", "start": "2026-08-05T09:00", "title": "Review"}
    registered = canary.register_proposal(trace, plan, args, "session-phase9")
    with runtime._lock:
        db = runtime._conn()
        with db:
            db.execute("UPDATE runtime_invocations SET expires_at=? WHERE id=?",
                       (1.0, registered["invocation_id"]))
    assert canary.pending_for(
        "session-phase9", f"XAC NHAN {registered['confirmation_code']}"
    ).action != "execute"
    runtime.sweep_stale_writes(max_running_seconds=0)
    assert runtime.get_invocation(registered["invocation_id"])["status"] == "FAILED_FINAL"
    # Lock đã nhả nên ý định mới đi được.
    assert canary.register_proposal(
        trace, plan, {**args, "title": "lần sau"}, "session-phase9")["status"] == "prepared"
    assert not calls


if __name__ == "__main__":
    import sys
    try:
        import pytest
    except ImportError:
        print("bỏ qua: chưa cài pytest")
        sys.exit(0)
    sys.exit(pytest.main([__file__, "-q"]))
