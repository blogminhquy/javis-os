"""Phase 12: chọn model theo từng bước.

Luật nặng nhất của spec mục 9.3: không đổi model chỉ để tiết kiệm nếu việc đổi làm
mất năng lực cần thiết. Mọi hàng rào dưới đây đều được kiểm chứng ngược.
"""
from _paths import SERVER  # noqa: E402,F401

from model_router import (ModelRouter, RouterPolicy, RoutingRequest,
                          requirements_for)


def _settings(models=None, allocation=10_000, allow_downgrade=False):
    return {
        "context_runtime": {
            "mode": "canary",
            "model_router_canary": {
                "policy_version": "test-router-v1",
                "allocation_basis_points": allocation,
                "allow_downgrade_on_risk": allow_downgrade,
                "models": models if models is not None else [
                    {"id": "re", "provider": "groq", "model": "llama-re",
                     "supports": [], "context_window": 100_000,
                     "input_cost_per_million": 0.05, "output_cost_per_million": 0.08},
                    {"id": "manh", "provider": "anthropic-api", "model": "claude-manh",
                     "supports": ["tools", "vision", "reasoning"],
                     "context_window": 200_000,
                     "input_cost_per_million": 3.0, "output_cost_per_million": 15.0},
                ],
            },
        }
    }


def _router(settings=None):
    settings = settings or _settings()
    return ModelRouter(lambda: settings)


# ----------------------------------------------- lọc năng lực trước, giá sau

def test_cheaper_model_never_wins_when_it_lacks_a_required_capability():
    """Luật trung tâm của mục 9.3."""
    router = _router()
    # Bước không cần gì: chọn model rẻ.
    plain = router.route(RoutingRequest(estimated_input_tokens=1000,
                                        reserved_output_tokens=500), "sid")
    assert plain.action == "route" and plain.model == "llama-re"

    # Bước cần tool: model rẻ KHÔNG có tool nên bị loại hẳn dù rẻ hơn 60 lần.
    with_tools = router.route(RoutingRequest(
        requires=requirements_for("model_step", needs_tools=True),
        estimated_input_tokens=1000, reserved_output_tokens=500), "sid")
    assert with_tools.action == "route" and with_tools.model == "claude-manh"
    assert with_tools.rejected["re"].startswith("missing_capability:tools")


def test_vision_requirement_is_not_guessed_from_the_model_name():
    """Model không KHAI vision thì không bao giờ nhận ảnh, dù tên nghe có vẻ xịn."""
    router = _router(_settings(models=[
        {"id": "nghe-xin", "provider": "openai", "model": "gpt-4o-super-vision-pro",
         "supports": [], "context_window": 100_000,
         "input_cost_per_million": 1.0, "output_cost_per_million": 2.0},
    ]))
    decision = router.route(RoutingRequest(
        requires=requirements_for("model_step", needs_vision=True),
        estimated_input_tokens=100, reserved_output_tokens=100), "sid")
    assert decision.action == "keep" and decision.reason == "no_eligible_model"
    assert "missing_capability:vision" in decision.rejected["nghe-xin"]


def test_no_eligible_model_keeps_the_user_choice_instead_of_lowering_the_bar():
    router = _router()
    decision = router.route(RoutingRequest(
        requires=frozenset({"tools", "vision", "reasoning", "parallel_tools"}),
        estimated_input_tokens=100, reserved_output_tokens=100), "sid",
        current_provider="groq", current_model="model-cua-user")
    assert decision.action == "keep"
    assert decision.reason == "no_eligible_model"
    assert decision.model == "model-cua-user"


# ----------------------------------------------- chính sách dữ liệu

def test_data_class_is_enforced_even_for_the_only_candidate():
    router = _router(_settings(models=[
        {"id": "duy-nhat", "provider": "groq", "model": "llama-re", "supports": [],
         "context_window": 100_000, "input_cost_per_million": 0.01,
         "output_cost_per_million": 0.02},
    ]))
    decision = router.route(RoutingRequest(
        data_class="y-te", estimated_input_tokens=100, reserved_output_tokens=50), "sid")
    assert decision.action == "keep"
    assert "data_class_not_allowed" in decision.rejected["duy-nhat"]

    allowed = _router(_settings(models=[
        {"id": "duy-nhat", "provider": "groq", "model": "llama-re", "supports": [],
         "context_window": 100_000, "input_cost_per_million": 0.01,
         "output_cost_per_million": 0.02, "data_classes": ["y-te"]},
    ]))
    ok = allowed.route(RoutingRequest(
        data_class="y-te", estimated_input_tokens=100, reserved_output_tokens=50), "sid")
    assert ok.action == "route" and ok.model == "llama-re"


# ----------------------------------------------- các ràng buộc còn lại

def test_context_window_deadline_and_cost_are_hard_filters():
    router = _router()
    too_big = router.route(RoutingRequest(
        estimated_input_tokens=150_000, reserved_output_tokens=1000), "sid")
    assert too_big.action == "route" and too_big.model == "claude-manh"
    assert too_big.rejected["re"] == "context_window_too_small"

    slow = _router(_settings(models=[
        {"id": "cham", "provider": "groq", "model": "llama-cham", "supports": [],
         "context_window": 100_000, "input_cost_per_million": 0.01,
         "output_cost_per_million": 0.02, "latency_hint_ms": 9000},
    ]))
    late = slow.route(RoutingRequest(deadline_ms=2000, estimated_input_tokens=10,
                                     reserved_output_tokens=10), "sid")
    assert late.action == "keep"
    assert late.rejected["cham"] == "latency_hint_exceeds_deadline"

    # Vừa cửa sổ context nhưng vượt ngân sách tiền của bước.
    pricey = router.route(RoutingRequest(
        requires=frozenset({"tools"}), estimated_input_tokens=100_000,
        reserved_output_tokens=10_000, max_cost_usd=0.01), "sid")
    assert pricey.action == "keep"
    assert pricey.rejected["manh"] == "cost_above_step_budget"


def test_risky_step_does_not_get_downgraded_by_default():
    models = [
        {"id": "re-yeu", "provider": "groq", "model": "llama-re", "supports": ["tools"],
         "context_window": 100_000, "input_cost_per_million": 0.01,
         "output_cost_per_million": 0.02, "downgrade": True},
        {"id": "manh", "provider": "anthropic-api", "model": "claude-manh",
         "supports": ["tools"], "context_window": 200_000,
         "input_cost_per_million": 3.0, "output_cost_per_million": 15.0},
    ]
    strict = _router(_settings(models=models))
    decision = strict.route(RoutingRequest(
        requires=frozenset({"tools"}), risk="write",
        estimated_input_tokens=100, reserved_output_tokens=100), "sid")
    assert decision.model == "claude-manh"
    assert decision.rejected["re-yeu"] == "downgrade_not_allowed_for_risky_step"

    # Chỉ khi người vận hành khai rõ mới cho hạ.
    lenient = _router(_settings(models=models, allow_downgrade=True))
    allowed = lenient.route(RoutingRequest(
        requires=frozenset({"tools"}), risk="write",
        estimated_input_tokens=100, reserved_output_tokens=100), "sid")
    assert allowed.model == "llama-re"


def test_ranking_is_deterministic_and_priority_beats_price():
    models = [
        {"id": "b", "provider": "groq", "model": "m-b", "supports": [],
         "context_window": 10_000, "input_cost_per_million": 1.0,
         "output_cost_per_million": 1.0},
        {"id": "a", "provider": "groq", "model": "m-a", "supports": [],
         "context_window": 10_000, "input_cost_per_million": 1.0,
         "output_cost_per_million": 1.0},
    ]
    router = _router(_settings(models=models))
    request = RoutingRequest(estimated_input_tokens=100, reserved_output_tokens=100)
    first = router.route(request, "sid")
    # Giá bằng nhau -> tie-break bằng id, ổn định qua nhiều lần gọi.
    assert first.model == "m-a"
    assert all(router.route(request, "sid").model == "m-a" for _ in range(5))

    with_priority = _router(_settings(models=[
        {**models[0], "priority": 5}, models[1],
    ]))
    assert with_priority.route(request, "sid").model == "m-b"


def test_already_on_the_best_model_is_reported_as_keep():
    router = _router()
    decision = router.route(
        RoutingRequest(estimated_input_tokens=100, reserved_output_tokens=100),
        "sid", current_provider="groq", current_model="llama-re")
    assert decision.action == "keep" and decision.reason == "already_on_best_model"


# ----------------------------------------------- khai báo thiếu là fail-closed

def test_rules_without_real_price_or_context_are_dropped():
    for bad in (
        {"id": "x", "provider": "groq", "model": "m", "context_window": 1000},
        {"id": "x", "provider": "groq", "model": "m", "input_cost_per_million": 1.0,
         "output_cost_per_million": 1.0},
        {"id": "x", "provider": "", "model": "m", "context_window": 1000,
         "input_cost_per_million": 1.0, "output_cost_per_million": 1.0},
    ):
        policy = RouterPolicy.from_settings(_settings(models=[bad]))
        assert policy.candidates == (), bad
    decision = _router(_settings(models=[
        {"id": "x", "provider": "groq", "model": "m", "context_window": 1000},
    ])).route(RoutingRequest(), "sid", current_model="cua-user")
    assert decision.action == "keep" and decision.reason == "no_model_rules_declared"


def test_defaults_never_route(tmp_path):
    import copy
    import config as cfgmod

    settings = copy.deepcopy(cfgmod._DEFAULT)
    policy = RouterPolicy.from_settings(settings)
    assert policy.allocation_basis_points == 0 and policy.candidates == ()
    decision = ModelRouter(lambda: settings).route(
        RoutingRequest(), "phiên bất kỳ", "groq", "llama-3.3")
    assert decision.action == "keep" and decision.model == "llama-3.3"


def test_malformed_settings_fall_back_to_keeping_the_current_model():
    for broken in ({"context_runtime": "off"}, {"context_runtime": {"model_router_canary": 5}},
                   {}, None):
        decision = ModelRouter(lambda: broken).route(
            RoutingRequest(), "sid", "groq", "llama-3.3")
        assert decision.action == "keep" and decision.model == "llama-3.3"


if __name__ == "__main__":
    import sys
    import pytest
    sys.exit(pytest.main([__file__, "-q"]))
