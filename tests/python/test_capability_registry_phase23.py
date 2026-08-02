from _paths import ROOT, SERVER  # noqa: E402,F401

import json
import sqlite3
import time

from capability_registry import CapabilityRegistry, brain_scope
from capability_resolver import ActorPolicy, DeterministicResolver
from context_runtime import ObserveRuntime
import mcp_hub


def _tool(name, description, aliases=()):
    return {
        "fn": name,
        "server": "synthetic",
        "name": name,
        "description": description,
        "aliases": list(aliases),
        "schema": {"type": "object", "properties": {"q": {"type": "string"}}},
    }


def _snapshot():
    tools = [
        _tool("calendar_list", "Xem lịch và danh sách sự kiện hôm nay", ["xem lịch", "đọc lịch"]),
        _tool("calendar_delete", "Xóa sự kiện khỏi lịch", ["xóa lịch", "hủy sự kiện"]),
        _tool("vault_write", "Ghi note vào vault", ["ghi note"]),
    ]
    route = {
        "calendar_list": {
            "source_type": "mcp", "source_id": "calendar-demo", "effect": "read",
            "required_mode": "readonly", "health": "healthy",
        },
        "calendar_delete": {
            "source_type": "mcp", "source_id": "calendar-demo", "effect": "danger",
            "required_mode": "full", "health": "healthy",
        },
        "vault_write": {
            "source_type": "builtin", "source_id": "javis-core", "effect": "write",
            "required_mode": "safe", "health": "healthy",
        },
    }
    return tools, route


def _runtime_settings():
    return {"context_runtime": {"mode": "shadow", "retention_days": 14}}


def test_registry_refresh_is_incremental_stable_and_brain_scoped(tmp_path):
    registry = CapabilityRegistry(tmp_path)
    tools, route = _snapshot()
    first = registry.refresh_tools("brain-a", tools, route)
    assert first["capability_count"] == 3
    assert first["source_count"] == 2
    assert first["changed_sources"] == 2
    ids_before = [x["capability_id"] for x in registry.search("lịch", "brain-a")]
    revision_before = first["revision"]

    second = registry.refresh_tools("brain-a", tools, route)
    assert second["changed_sources"] == 0
    assert second["revision"] == revision_before
    registry.close()

    reopened = CapabilityRegistry(tmp_path)
    assert [x["capability_id"] for x in reopened.search("lịch", "brain-a")] == ids_before
    assert reopened.revision("brain-a") == revision_before
    assert reopened.search("lịch", "brain-b") == []

    changed = [dict(x) for x in tools]
    changed[2] = dict(changed[2], description="Ghi note hoặc báo cáo vào vault")
    update = reopened.refresh_tools("brain-a", changed, route)
    assert update["changed_sources"] == 1
    assert update["revision"] != revision_before
    check = reopened.integrity_check("brain-a")
    assert check["ok"] is True
    assert check["capabilities"] == 3
    assert check["duplicate_names"] == 0


def test_builtin_source_adapter_matches_hub_snapshot(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    tools, route = mcp_hub._builtin_tools("full", str(vault))
    assert tools
    assert set(route) == {tool["fn"] for tool in tools}
    assert all(route[name]["source_type"] == "builtin" for name in route)
    assert route["javis_write_file"]["effect"] == "write"
    registry = CapabilityRegistry(tmp_path / "state")
    result = registry.refresh_tools(str(vault), tools, route)
    assert result["capability_count"] == len(tools)
    assert registry.integrity_check(str(vault))["capabilities"] == len(tools)


def test_removed_source_is_deactivated_without_touching_other_scope(tmp_path):
    registry = CapabilityRegistry(tmp_path)
    tools, route = _snapshot()
    registry.refresh_tools("brain-a", tools, route)
    registry.refresh_tools("brain-b", tools, route)
    only_builtin = [x for x in tools if x["fn"] == "vault_write"]
    registry.refresh_tools("brain-a", only_builtin, {"vault_write": route["vault_write"]})
    assert registry.search("lịch", "brain-a") == []
    assert registry.search("lịch", "brain-b")


def test_model_profile_revision_is_stable_until_metadata_changes(tmp_path):
    registry = CapabilityRegistry(tmp_path)
    a = registry.refresh_model_profile("groq", "llama-demo", "api", True, {"supports_tools": True})
    b = registry.refresh_model_profile("groq", "llama-demo", "api", True, {"supports_tools": True})
    assert a == b
    old = registry.model_revision()
    registry.refresh_model_profile("groq", "llama-demo", "api", True, {"supports_tools": False})
    assert registry.model_revision() != old


def test_resolver_gold_hard_filters_and_is_deterministic(tmp_path):
    registry = CapabilityRegistry(tmp_path)
    tools, route = _snapshot()
    registry.refresh_tools("brain-a", tools, route)
    resolver = DeterministicResolver(registry)
    fixture = json.loads(
        (ROOT / "tests/fixtures/capability_resolver_gold.json").read_text(encoding="utf-8")
    )
    for case in fixture["cases"]:
        actor = ActorPolicy(mode=case["actor_mode"], channel="dashboard")
        one = resolver.resolve(case["query"], "brain-a", actor)
        two = resolver.resolve(case["query"], "brain-a", actor)
        names = [x["name"] for x in one["selected"]]
        assert names == [x["name"] for x in two["selected"]], case["id"]
        for expected in case.get("expected", []):
            assert expected in names, case["id"]
        for forbidden in case.get("forbidden", []):
            assert forbidden not in names, case["id"]
        if case.get("expected_miss"):
            assert one["miss_class"] == case["expected_miss"], case["id"]
        assert one["query_hash"] and case["query"] not in json.dumps(one, ensure_ascii=False)


def test_resolver_has_no_popularity_bias_and_reports_embedding_overlap(tmp_path):
    registry = CapabilityRegistry(tmp_path)
    tools, route = _snapshot()
    registry.refresh_tools("brain-a", tools, route)
    target = registry.search("ghi note", "brain-a")[0]["capability_id"]

    class FakeEmbedding:
        def search(self, query, brain, limit):
            return [(target, 0.99), ("cap_missing", 0.8)]

    resolver = DeterministicResolver(registry, embedding=FakeEmbedding())
    report = resolver.resolve("ghi note vào vault", "brain-a", ActorPolicy(mode="safe"))
    assert report["selected"][0]["name"] == "vault_write"
    assert report["embedding_candidate_count"] == 2
    assert report["embedding_lexical_overlap"] == 1


def test_hard_filters_cover_health_effect_and_source_type(tmp_path):
    registry = CapabilityRegistry(tmp_path)
    tools, route = _snapshot()
    unhealthy_route = {name: dict(meta) for name, meta in route.items()}
    unhealthy_route["calendar_list"]["health"] = "degraded"
    registry.refresh_tools("brain-a", tools, unhealthy_route)
    resolver = DeterministicResolver(registry)

    health = resolver.resolve("xem lịch", "brain-a", ActorPolicy(mode="full"))
    assert health["miss_class"] == "health"
    effect = resolver.resolve(
        "xóa lịch", "brain-a",
        ActorPolicy(mode="full", allowed_effects=frozenset({"none", "read"})),
    )
    assert effect["miss_class"] == "side_effect"
    source = resolver.resolve(
        "xóa lịch", "brain-a",
        ActorPolicy(mode="full", allowed_source_types=frozenset({"builtin"})),
    )
    assert source["miss_class"] == "source_type"


def test_shadow_refresh_is_off_hot_path_and_resolver_latency_is_bounded(tmp_path):
    main_source = (SERVER / "main.py").read_text(encoding="utf-8")
    assert "_track_shadow_task(_job())" in main_source
    assert "await asyncio.to_thread(" in main_source

    registry = CapabilityRegistry(tmp_path)
    tools, route = _snapshot()
    # Nhiều capability không liên quan không được làm đổi top hit hoặc tạo popularity bias.
    for i in range(250):
        name = f"unrelated_{i:03d}"
        tools.append(_tool(name, f"Synthetic unrelated capability number {i}"))
        route[name] = {"source_type": "plugin", "source_id": f"p{i}", "effect": "read",
                       "required_mode": "readonly", "health": "healthy"}
    registry.refresh_tools("brain-a", tools, route)
    resolver = DeterministicResolver(registry)
    started = time.perf_counter()
    reports = [resolver.resolve("ghi note vào vault", "brain-a", ActorPolicy(mode="safe"))
               for _ in range(30)]
    elapsed = time.perf_counter() - started
    assert all(r["selected"][0]["name"] == "vault_write" for r in reports)
    assert elapsed < 2.0


def test_shadow_report_persists_no_query_or_schema(tmp_path):
    registry = CapabilityRegistry(tmp_path / "registry")
    tools, route = _snapshot()
    registry.refresh_tools("brain-a", tools, route)
    report = DeterministicResolver(registry).resolve(
        "PRIVATE QUERY MUST NOT PERSIST ghi note", "brain-a", ActorPolicy(mode="safe")
    )
    runtime = ObserveRuntime(tmp_path / "runtime", settings_reader=_runtime_settings)
    trace = runtime.start_turn("sid", "brain-a", "dashboard")
    runtime.record_shadow_resolution(trace, report)
    runtime.finish(trace)
    runtime.close()
    raw = (tmp_path / "runtime" / "runtime.db").read_bytes()
    assert b"PRIVATE QUERY MUST NOT PERSIST" not in raw
    assert b'"properties"' not in raw
    db = sqlite3.connect(tmp_path / "runtime" / "runtime.db")
    payload = db.execute(
        "SELECT payload_json FROM runtime_events WHERE event_type='resolver.shadow'"
    ).fetchone()[0]
    assert "query_hash" in payload
    assert "selected_ids" in payload


def test_corrupt_registry_is_quarantined_and_rebuilt(tmp_path):
    path = tmp_path / "capability_registry.db"
    path.write_bytes(b"not-a-sqlite-database")
    registry = CapabilityRegistry(tmp_path)
    check = registry.integrity_check("brain-a")
    assert check["ok"] is True
    assert list(tmp_path.glob("capability_registry.db.corrupt-*"))


if __name__ == "__main__":
    # CI chạy TỪNG FILE như script (`python tests/python/test_x.py`), không gọi pytest.
    # Thiếu block này thì file chỉ định nghĩa hàm rồi thoát 0 - test "xanh" mà chưa
    # từng chạy một assertion nào.
    import sys
    try:
        import pytest
    except ImportError:
        print("bỏ qua: chưa cài pytest")
        sys.exit(0)
    sys.exit(pytest.main([__file__, "-q"]))
