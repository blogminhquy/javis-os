"""Đường tắt tiết kiệm token KHÔNG được nuốt những lượt cần bộ não.

    python tests/run.py duong_tat_khong_nuot_viec

Ca thật đã đo được (chủ repo báo 21/09/2026, brain TN88). Mức "Siêu tiết kiệm" là mặc định
xuất xưởng từ 0.24.7, tức `canary.allocation_basis_points = 10000`: MỌI lượt chat đều đi qua
cổng này. Đường tắt cố ý không phát tool, không đọc ký ức, không đọc lịch sử hội thoại - nên
mỗi lượt nó nhận nhầm là một lượt Javis trả lời như thể không có bộ não.

Ba lượt trong cùng một hội thoại, ba kiểu hỏng khác nhau, cùng một gốc:

    "viết bài ... dùng dữ liệu dự án TN88 ... dùng workflow viết bài chuyên sâu"
        -> ALLOW khớp chữ "là gì" trong TIÊU ĐỀ bài -> đi tắt -> Javis trả lời "chưa có dữ
           liệu dự án TN88 và chưa được cấp công cụ", rồi đòi người dùng tự dán tài liệu vào.

    "uh, vậy viết bài đi"
        -> ALLOW khớp "viết" -> đi tắt -> không có lịch sử -> "bạn muốn viết bài về chủ đề
           gì? Mình chưa có nội dung trao đổi trước đó."

    (workflow có thật trong sổ đăng ký, người dùng gọi đúng tên)
        -> resolver hard-filter kind `workflow`/`skill` khỏi `ranked`, nên điểm của chúng
           KHÔNG tới được cổng. Gọi đúng tên một workflow của chính mình vẫn đi tắt.

Luật chốt ở đây: trỏ vào BỘ NÃO (dữ liệu, dự án, ghi chú), trỏ vào NĂNG LỰC CỦA JAVIS
(workflow, skill, agent, plugin), hoặc trỏ vào LƯỢT TRƯỚC (câu nối) thì đi đường đầy đủ. Trả
giá bằng token, không trả giá bằng một câu trả lời rỗng.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401

from capability_registry import CapabilityRegistry
from capability_resolver import ActorPolicy, DeterministicResolver
from context_compiler import ContextCompiler
from context_runtime import ObserveRuntime
from fast_path_runtime import FastIntentClassifier, FastPathCanary


def _settings(allocation=10_000):
    return {
        "context_runtime": {
            "mode": "canary",
            "retention_days": 14,
            "canary": {
                "policy_version": "test-nuot-viec-v1",
                "allocation_basis_points": allocation,
                "salt": "test-salt-v1",
                "channels": ["dashboard"],
                "provider_kinds": ["api"],
                "registry_max_age_seconds": 900,
                "estimator_safety_factor": 1.35,
                "min_resolver_score": 0.45,
                "quota_profiles": [{
                    "id": "groq-test",
                    "provider": "groq",
                    "model_pattern": "llama-*",
                    "rolling_tpm": 12_000,
                    "max_input_tokens": 8000,
                    "reserved_output_tokens": 600,
                    "window_seconds": 60,
                }],
            },
        }
    }


def _stack(tmp_path, workflows=(), skills=()):
    """Sổ đăng ký nạp workflow/skill TRƯỚC khi ghim revision vào trace.

    Nạp sau thì `prepare` trả `registry_revision_changed` và ca kiểm chứng đi nhầm nhánh -
    xanh vì lý do khác, không phải vì cổng làm đúng việc.
    """
    settings = _settings()
    brain = tmp_path / "brain"
    registry = CapabilityRegistry(tmp_path / "registry")
    registry.refresh_tools(brain, [], {})
    if workflows:
        registry.refresh_workflows(brain, workflows)
    if skills:
        registry.refresh_skills(brain, skills)
    resolver = DeterministicResolver(registry)
    compiler = ContextCompiler(registry)
    runtime = ObserveRuntime(tmp_path / "runtime", settings_reader=lambda: settings)
    trace = runtime.start_turn("session-nuot-viec", str(brain), "dashboard")
    trace.registry_revision = registry.revision(brain)
    canary = FastPathCanary(registry, resolver, compiler, runtime,
                            settings_reader=lambda: settings)
    return brain, registry, resolver, runtime, trace, canary


# --- 1. Trỏ vào bộ não / năng lực của Javis thì không được đi tắt --------------------

BAI_TN88 = (
    'viết cho tôi bài viết chuyên sâu với tiêu đề " Gà Khét Là Gì? Tìm Hiểu Đặc Điểm Và '
    'Giá Trị Của Chiến Kê " sử dụng dữ liệu dự án TN88 để viết bài. Sử dụng workflows '
    "viết bài chuyên sâu để hoàn thành bài viết."
)


def test_cau_tro_vao_bo_nao_va_nang_luc_khong_di_tat():
    gate = FastIntentClassifier()
    for prompt in (
        BAI_TN88,
        "viết lại đoạn này theo skill salepage",
        "dùng agent biên tập để viết lại giúp anh",
        "viết bài dựa trên dữ liệu bên mình",
        "tóm tắt ghi chú trong bộ não",
        "viết bài theo quy trình sẵn có",
    ):
        assert not gate.classify(prompt, lang="vi").eligible, prompt
    for prompt in (
        "write a deep dive article using the TN88 project data",
        "rewrite this with my salepage skill",
        "summarize the notes in my second brain",
    ):
        assert not gate.classify(prompt, lang="en").eligible, prompt


# --- 2. Câu nối tiếp lượt trước thì không được đi tắt --------------------------------

def test_cau_noi_tiep_luot_truoc_khong_di_tat():
    gate = FastIntentClassifier()
    for prompt in (
        "uh, vậy viết bài đi",
        "ok viết đi",
        "thế tóm tắt lại đi",
        "rồi, dịch nốt đoạn còn lại",
        "viết tiếp đi",
    ):
        assert not gate.classify(prompt, lang="vi").eligible, prompt
    for prompt in ("ok, write it then", "go on, summarize it"):
        assert not gate.classify(prompt, lang="en").eligible, prompt


# --- 3. Câu tự chứa thật thì VẪN đi tắt (không được siết quá tay) --------------------

def test_cau_tu_chua_van_di_tat():
    gate = FastIntentClassifier()
    for prompt in (
        "Giải thích entropy là gì",
        "Viết cho anh 5 tiêu đề về học tập",
        "Dịch câu này sang tiếng Anh: cảm ơn anh",
    ):
        assert gate.classify(prompt, lang="vi").eligible, prompt
    for prompt in ("Explain what entropy is", "Draft five headlines about learning"):
        assert gate.classify(prompt, lang="en").eligible, prompt


# --- 4. Gọi đúng tên workflow/skill của chính mình thì phải nhường đường thường ------

_WF = [{
    "slug": "dat-tieu-de-hap-dan",
    "name": "Đặt tiêu đề hấp dẫn",
    "description": "Đặt tiêu đề hấp dẫn cho bài viết theo khung đã chốt",
}]


def test_resolver_bao_ra_diem_cua_thu_bi_hard_filter(tmp_path):
    """`ranked` không có workflow/skill, nên cổng phải đọc được điểm bị chặn ở chỗ khác."""
    _brain, _reg, resolver, _rt, _tr, _cn = _stack(tmp_path, workflows=_WF)
    ra = resolver.resolve("đặt tiêu đề hấp dẫn cho bài này", str(tmp_path / "brain"),
                          ActorPolicy(mode="full", channel="dashboard"))
    assert ra["selected_count"] == 0
    assert ra["filtered"].get("capability_kind"), "workflow phải bị hard-filter như cũ"
    blocked = ra.get("blocked_best") or {}
    assert blocked.get("capability_kind", 0) >= 0.45, blocked


def test_goi_dung_ten_workflow_thi_khong_di_tat(tmp_path):
    brain, _reg, _rs, _rt, trace, canary = _stack(tmp_path, workflows=_WF)
    gate = FastIntentClassifier()
    objective = "đặt tiêu đề hấp dẫn cho bài này"
    # Câu này KHÔNG chứa từ khoá nào của cổng từ vựng - nếu nó tự bị DENY thì ca kiểm chứng
    # không còn kiểm chứng tầng resolver nữa.
    assert gate.classify(objective, lang="vi").eligible
    plan = canary.prepare(trace, objective, str(brain), "dashboard", "groq", "llama-3.3",
                          "api", lang="vi", lang_tra_loi="vi")
    assert plan.action == "legacy", (plan.action, plan.reason)
    assert plan.reason == "capability_kind_blocked", plan.reason


if __name__ == "__main__":
    import sys
    try:
        import pytest
    except ImportError:
        print("bỏ qua: chưa cài pytest")
        sys.exit(0)
    sys.exit(pytest.main([__file__, "-q"]))
