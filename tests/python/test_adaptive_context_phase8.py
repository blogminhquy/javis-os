import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SERVER = ROOT / "server"
if str(SERVER) not in sys.path:
    sys.path.insert(0, str(SERVER))

import config
import skill_router
from adaptive_context_runtime import AdaptiveContextCanary
from capability_registry import CapabilityRegistry
from capability_resolver import DeterministicResolver
from context_compiler import CompileRequest, ContextCompiler
from context_runtime import ObserveRuntime
from conversation_state import ConversationStateStore
from lazy_skill_runtime import LazySkillSource
from memory_index import MemoryIndex


def _write(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _settings(*features):
    runtime = {
        "mode": "canary",
        "context_sources": {"quota_profiles": [{
            "id": "test", "provider": "groq", "model_pattern": "llama-*",
            "rolling_tpm": 12000, "max_input_tokens": 10000,
            "reserved_output_tokens": 1000,
        }]},
    }
    defaults = {
        "conversation_state_canary": {"allocation_basis_points": 0},
        "memory_canary": {"allocation_basis_points": 0},
        "lazy_skill_canary": {"allocation_basis_points": 0},
    }
    for key, value in defaults.items():
        runtime[key] = {"policy_version": key + "-test", "salt": key + "-test",
                        "channels": ["dashboard"], "provider_kinds": ["api"], **value}
    for feature in features:
        runtime[feature]["allocation_basis_points"] = 10_000
    return {"context_runtime": runtime}


def _messages():
    return [
        {"id": 1, "role": "user", "content": "Anh muốn làm Phase 8 và phải giữ rollback riêng."},
        {"id": 2, "role": "assistant", "content": "Đã hoàn thành Phase 7 trong server/runtime.py."},
        {"id": 3, "role": "user", "content": "Chốt dùng memory có source. Câu hỏi còn lại là rollout bao nhiêu?"},
        {"id": 4, "role": "user", "content": "Làm tiếp Phase 8."},
    ]


def test_memory_index_rebuild_retrieval_sources_conflict_and_fallback(tmp_path):
    brain = tmp_path / "brain"
    identity = brain / "memory" / "identity.md"
    first = brain / "memory" / "facts" / "contact-old.md"
    second = brain / "memory" / "facts" / "contact-new.md"
    linked = brain / "memory" / "facts" / "project.md"
    _write(identity, "---\nalways_on: true\ntitle: Identity\n---\n# Identity\nTên người dùng: Anh Bình")
    _write(first, "# Contact\nEmail liên hệ: old@example.com. Khách hàng [[Acme]].")
    _write(second, "# Contact\nEmail liên hệ: new@example.com. Khách hàng [[Acme]].")
    _write(linked, "# Dự án Acme\nNgân sách quảng cáo cho [[Acme]] là 20 triệu.")
    original = first.read_bytes()

    index = MemoryIndex(tmp_path / "state")
    built = index.rebuild(brain)
    assert built["rebuilt"] is True and built["record_count"] >= 4
    assert index.rebuild(brain)["rebuilt"] is False
    result = index.retrieve(brain, "Email liên hệ của Acme là gì?", limit=8)
    assert result.fallback_required is False
    assert "exact_keyword_entity" in result.stages
    assert "source_file_read" in result.stages
    assert any("file:memory/facts/contact" in ref
               for record in result.records for ref in record["source_refs"])
    assert result.conflicts
    assert all(item.source_ref.startswith("file:") for item in result.context_items())
    assert first.read_bytes() == original
    assert index.integrity_check(brain)["ok"] is True

    miss = index.retrieve(brain, "Anh có nhớ màu xe của anh không?")
    assert miss.fallback_required is True
    assert miss.fallback_reason == "no_relevant_memory"


def test_phase8_synthetic_gold_memory_recall_and_skill_triggers(tmp_path):
    fixture = json.loads(
        (ROOT / "tests" / "fixtures" / "phase8_context_gold.json").read_text(encoding="utf-8")
    )
    brain = tmp_path / "brain"
    for relative, content in fixture["memory_files"].items():
        _write(brain / relative, content)
    for slug, skill in fixture["skills"].items():
        _write(
            brain / "skills" / slug / "SKILL.md",
            f"---\nname: {slug}\ndescription: {skill['description']}\n---\nBODY_{slug}",
        )

    index = MemoryIndex(tmp_path / "state")
    recalled = 0
    for case in fixture["memory_cases"]:
        result = index.retrieve(brain, case["query"], limit=6)
        refs = [ref for record in result.records for ref in record["source_refs"]]
        recalled += int(any(case["source"] in ref for ref in refs))
    assert recalled == len(fixture["memory_cases"])

    source = LazySkillSource(CapabilityRegistry(tmp_path / "state"))
    triggered = 0
    for slug, skill in fixture["skills"].items():
        selected = source.resolve(brain, skill["query"])
        triggered += int(selected.action == "load" and selected.slug == slug)
    assert triggered == len(fixture["skills"])


def test_conversation_state_is_bounded_traceable_and_rebuildable(tmp_path):
    store = ConversationStateStore(tmp_path / "state")
    messages = _messages()
    original = json.loads(json.dumps(messages))
    state = store.rebuild("session-1", tmp_path / "brain", messages)
    assert state.goals and state.constraints and state.decisions
    assert state.open_questions
    assert state.artifacts
    assert state.last_completed_step
    for group in (state.goals, state.decisions, state.constraints, state.artifacts):
        assert all(x["source_ref"].startswith("session:session-1:message:") for x in group)
    again = store.rebuild("session-1", tmp_path / "brain", messages)
    assert again.revision == state.revision
    rebuilt = store.rebuild("session-1", tmp_path / "brain", messages, force=True)
    assert rebuilt.as_dict() == state.as_dict()
    assert messages == original
    assert store.integrity_check()["ok"] is True


def test_skill_source_registers_manifest_only_and_loads_one_body(tmp_path):
    brain = tmp_path / "brain"
    skill = brain / "skills" / "webcake" / "SKILL.md"
    secret_body = "BODY_MARKER_9f2c Hãy xuất landing page đúng schema Webcake."
    _write(skill, "---\nname: Webcake Export\ndescription: Xuất landing page sang Webcake\ngroup: Web\n---\n" + secret_body)
    _write(brain / "skills" / "email" / "SKILL.md",
           "---\nname: Email Writer\ndescription: Viết email bán hàng\n---\nEMAIL_BODY")

    manifests = skill_router.list_skill_manifests(brain)
    assert len(manifests) == 2
    assert secret_body not in json.dumps(manifests, ensure_ascii=False)
    registry = CapabilityRegistry(tmp_path / "state")
    source = LazySkillSource(registry)
    refreshed = source.refresh(brain)
    assert refreshed["body_loaded_count"] == 0
    rows = [x for x in registry.search("xuất landing page Webcake", brain) if x["kind"] == "skill"]
    assert rows and secret_body not in json.dumps(rows, ensure_ascii=False)

    selected = source.resolve(brain, "Hãy xuất landing page sang Webcake")
    assert selected.action == "load" and selected.slug == "webcake"
    assert secret_body in selected.context_item.content
    assert "EMAIL_BODY" not in selected.context_item.content

    # Tool resolver sees shared Registry but never treats a skill manifest as executable.
    resolution = DeterministicResolver(registry).resolve("xuất landing page Webcake", str(brain))
    assert resolution["selected_count"] == 0
    assert resolution["filtered"].get("capability_kind")


def test_compiler_budgets_phase8_items_and_keeps_source_map(tmp_path):
    registry = CapabilityRegistry(tmp_path / "state")
    compiler = ContextCompiler(registry)
    state = ConversationStateStore(tmp_path / "state").rebuild(
        "s", tmp_path / "brain", _messages()
    )
    result = compiler.compile_canary(CompileRequest(
        task_id="t", step_id="s", objective="Làm tiếp Phase 8", brain=str(tmp_path / "brain"),
        channel="dashboard", provider="groq", model="llama-test", model_kind="api",
        hard_max_input_tokens=5000, rolling_tpm_remaining=12000,
        reserved_output_tokens=1000, context_items=(state.context_item(),),
    ), {"selected": [], "miss_class": ""})
    assert result.status == "compiled"
    assert result.trace_report["selected_context_ids"] == ["conversation_state"]
    assert "conversation_state" in result.capsule.source_map
    assert result.capsule.source_map["conversation_state"]["trust"] == "transcript_projection"


@pytest.mark.parametrize("feature,expected_flags", [
    ("conversation_state_canary", (True, True)),
    ("memory_canary", (False, True)),
    ("lazy_skill_canary", (True, False)),
])
def test_three_phase8_canaries_are_independent(tmp_path, feature, expected_flags):
    brain = tmp_path / "brain"
    _write(brain / "memory" / "facts" / "contact.md", "# Contact\nEmail Acme: hello@acme.test")
    _write(brain / "skills" / "webcake" / "SKILL.md",
           "---\nname: Webcake\ndescription: Xuất landing page Webcake\n---\nLàm đúng schema Webcake.")
    registry = CapabilityRegistry(tmp_path / "state")
    compiler = ContextCompiler(registry)
    runtime = ObserveRuntime(tmp_path / "state", settings_reader=lambda: _settings(feature))
    canary = AdaptiveContextCanary(
        tmp_path / "state", registry, compiler, runtime, lambda: _settings(feature)
    )
    objective = {
        "conversation_state_canary": "Làm tiếp Phase 8",
        "memory_canary": "Email Acme là gì?",
        "lazy_skill_canary": "Xuất landing page Webcake",
    }[feature]
    calls = []

    def base(include_memory, include_skills):
        calls.append((include_memory, include_skills))
        return "Javis base contract"

    plan = canary.prepare(None, objective, brain, "session-1", _messages(),
                          "dashboard", "groq", "llama-test", "api", base)
    assert plan.action == "use", plan
    assert calls[-1] == expected_flags
    applied = {"conversation_state_canary": plan.state_applied,
               "memory_canary": plan.memory_applied,
               "lazy_skill_canary": plan.skill_applied}
    assert applied[feature] is True
    assert sum(bool(x) for x in applied.values()) == 1


def test_phase8_defaults_are_zero_and_do_not_open_sources(tmp_path):
    runtime_cfg = config._DEFAULT["context_runtime"]
    for key in ("conversation_state_canary", "memory_canary", "lazy_skill_canary"):
        assert runtime_cfg[key]["allocation_basis_points"] == 0
    registry = CapabilityRegistry(tmp_path / "state")
    runtime = ObserveRuntime(tmp_path / "state", settings_reader=lambda: {"context_runtime": {"mode": "shadow"}})
    canary = AdaptiveContextCanary(
        tmp_path / "state", registry, ContextCompiler(registry), runtime,
        lambda: {"context_runtime": {"mode": "shadow"}},
    )
    plan = canary.prepare(None, "hello", tmp_path / "brain", "s", [], "dashboard",
                          "groq", "llama-test", "api", lambda _m, _s: "base")
    assert plan.action == "legacy"
    assert not (tmp_path / "state" / "memory_index.db").exists()
    assert not (tmp_path / "state" / "conversation_state.db").exists()


def test_phase8_small_base_does_not_wrap_full_claude_prompt(tmp_path, monkeypatch):
    import main

    brain = tmp_path / "brain"
    brain.mkdir()
    fake_claude = tmp_path / "CLAUDE.md"
    fake_claude.write_text("FULL_CLAUDE_MARKER_MUST_NOT_LOAD", encoding="utf-8")
    monkeypatch.setattr(main, "CLAUDE_MD_PATH", fake_claude)
    prompt = main.build_adaptive_source_prompt(str(brain), False, False)
    assert "# Javis adaptive source contract" in prompt
    assert "FULL_CLAUDE_MARKER_MUST_NOT_LOAD" not in prompt


def test_phase8_small_base_size_does_not_scale_with_legacy_prompt(tmp_path, monkeypatch):
    import main

    brain = tmp_path / "brain"
    brain.mkdir()
    fake_claude = tmp_path / "CLAUDE.md"
    fake_claude.write_text("LEGACY_INSTRUCTION " * 2500, encoding="utf-8")
    _write(brain / "memory" / "MEMORY.md", "- [Fact](facts/a.md) - " + "chi tiết " * 1000)
    monkeypatch.setattr(main, "CLAUDE_MD_PATH", fake_claude)
    monkeypatch.setattr(main.system_sync, "ensure_synced", lambda _root: None)
    monkeypatch.setattr(main.system_sync, "mirror_skills", lambda _root: None)
    legacy = main.build_system_prompt(str(brain))
    adaptive = main.build_adaptive_source_prompt(str(brain), False, False)
    assert len(adaptive) < len(legacy) * 0.05
