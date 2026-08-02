"""Chiều phản ứng khi vượt hạn mức: KHÔNG được rơi về legacy.

    python tests/run.py quota_direction

Lỗi thiết kế được sửa ở đây: khi preflight từ chối, phản xạ mặc định của canary là rơi về
legacy. Với lý do "câu này không hợp fast path" thì đúng. Nhưng với lý do NGÂN SÁCH thì sai
chiều, vì legacy chính là đường gửi NHIỀU token hơn - phát hiện request quá to rồi đáp lại
bằng một request còn to hơn, và provider trả lỗi.

Đây đúng là tình huống đã chặn Javis với gói Groq 12.000 TPM khi một lượt cần 21.446 token.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import os
import sys
import tempfile

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-quotadir-")

import context_compiler  # noqa: E402
import model_limits  # noqa: E402

_fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)


# ---- 1. quota_block_reason: phân biệt "hết ngân sách" với "không hợp đường này" ----
check("would_allow → không phải chuyện quota",
      context_compiler.quota_block_reason(
          {"preflight_decision": "would_allow", "preflight_reasons": []}) == "")
check("vượt TPM → nhận ra là quota",
      context_compiler.quota_block_reason(
          {"preflight_decision": "would_reject",
           "preflight_reasons": ["rolling_tpm"]}) == "rolling_tpm")
check("vượt cửa sổ ngữ cảnh → nhận ra là quota",
      context_compiler.quota_block_reason(
          {"preflight_decision": "would_reject",
           "preflight_reasons": ["input_budget"]}) == "input_budget")
check("vượt ngân sách task → nhận ra là quota",
      context_compiler.quota_block_reason(
          {"preflight_decision": "would_reject",
           "preflight_reasons": ["task_budget"]}) == "task_budget")
check("riêng phần bắt buộc đã không vừa → nhận ra là quota (nén thêm vô ích)",
      context_compiler.quota_block_reason(
          {"preflight_decision": "would_reject",
           "preflight_reasons": ["required_items"]}) == "required_items")
check("lý do KHÁC quota → trả rỗng để còn rơi về legacy cho đúng",
      context_compiler.quota_block_reason(
          {"preflight_decision": "would_reject",
           "preflight_reasons": ["ly_do_la"]}) == "")
check("would_allow thắng kể cả khi có mã lý do thừa",
      context_compiler.quota_block_reason(
          {"preflight_decision": "would_allow",
           "preflight_reasons": ["rolling_tpm"]}) == "")
check("report rỗng không nổ", context_compiler.quota_block_reason({}) == "")
check("report None không nổ", context_compiler.quota_block_reason(None) == "")

# ---- 2. fits_within: chưa biết KHÁC không vừa ----
check("Groq 12k không chứa nổi 21.446 token (đúng ca gốc)",
      model_limits.fits_within("groq", "llama-3.3-70b-versatile", 21446) is False)
check("Groq 12k chứa được 5.000 token",
      model_limits.fits_within("groq", "llama-3.3-70b-versatile", 5000) is True)
check("provider chưa tra → None (chưa biết), KHÔNG phải False",
      model_limits.fits_within("provider-la", "m", 21446) is None)

# ---- 3. Câu báo cho người dùng phải NÊU SỐ và NÊU LỐI RA ----
_hint = model_limits.blocked_hint("groq", "llama-3.3-70b-versatile", 21446,
                                  ("groq", "openai", "gemini"))
check("báo lỗi nêu số token cần", "21,446" in _hint)
check("báo lỗi nêu hạn mức thật", "12,000" in _hint)
check("báo lỗi gợi ý provider người dùng ĐANG có", "openai" in _hint and "gemini" in _hint)
check("báo lỗi KHÔNG gợi ý lại chính provider đang bị chặn",
      _hint.count("groq") == 1)
# Ca phân biệt thật: provider bị chặn vì CỬA SỔ NGỮ CẢNH nhưng vẫn vừa TPM. Nếu chỉ lọc
# bằng fits_within thì groq lọt vào danh sách "đổi sang" - tức là bảo người dùng đổi sang
# đúng cái vừa từ chối họ.
_hint3 = model_limits.blocked_hint("groq", "llama-3.3-70b-versatile", 5000,
                                   ("groq", "openai"))
check("provider bị chặn nhưng vẫn vừa TPM cũng KHÔNG được gợi ý lại",
      "đổi sang" in _hint3 and "groq" not in _hint3.split("đổi sang", 1)[1])
check("báo lỗi luôn nêu lối ra không cần đổi provider", "rút gọn" in _hint)

_hint2 = model_limits.blocked_hint("groq", "llama-3.3-70b-versatile", 21446, ())
check("chưa cấu hình provider nào khác → không bịa ra lựa chọn",
      "đổi sang" not in _hint2)

# ---- 4. Đường THẬT bị hỏng là Phase 8, không phải fast path ----
#
# Đính chính cho chính mình: fast path và readonly path ĐÃ từ chối-và-nói từ trước
# (compile_rejected → reject kèm message), nên chúng không có lỗi này. Đường sai chiều là
# Phase 8 (context_sources): nó tồn tại để THAY CLAUDE.md bằng capsule nhỏ, mà khi compiler
# từ chối vì quá to thì nó rơi về legacy - đường gửi nguyên CLAUDE.md cộng MEMORY.md, tức
# là còn to hơn hẳn cái vừa bị từ chối.
import shutil  # noqa: E402
from pathlib import Path  # noqa: E402

from adaptive_context_runtime import AdaptiveContextCanary  # noqa: E402
from capability_registry import CapabilityRegistry  # noqa: E402
from context_compiler import ContextCompiler  # noqa: E402
from context_runtime import ObserveRuntime  # noqa: E402


def _p8_settings(rolling_tpm, max_input, providers=("groq", "openai", "gemini")):
    keys = {"groq": "groq_api_key", "openai": "openai_api_key", "gemini": "gemini_api_key"}
    feature = {
        "allocation_basis_points": 10_000, "channels": ["dashboard"],
        "provider_kinds": ["api"],
    }
    return {
        "model": {keys[p]: "khoa-gia" for p in providers},
        "context_runtime": {
            "mode": "canary", "retention_days": 14,
            "conversation_state_canary": dict(feature, policy_version="cs-v1", salt="cs"),
            "memory_canary": dict(feature, policy_version="mem-v1", salt="mem"),
            "lazy_skill_canary": dict(feature, policy_version="sk-v1", salt="sk"),
            "context_sources": {
                "quota_profiles": [{
                    "id": "groq-test", "provider": "groq", "model_pattern": "llama-*",
                    "rolling_tpm": rolling_tpm, "max_input_tokens": max_input,
                    "reserved_output_tokens": 600, "window_seconds": 60,
                }],
            },
        },
    }


def _p8_run(tmp, settings, objective="Giải thích entropy là gì"):
    brain = Path(tmp) / "brain"
    brain.mkdir(parents=True, exist_ok=True)
    registry = CapabilityRegistry(Path(tmp) / "registry")
    registry.refresh_tools(brain, [], {})
    runtime = ObserveRuntime(Path(tmp) / "runtime", settings_reader=lambda: settings)
    trace = runtime.start_turn("session-quota", str(brain), "dashboard")
    trace.registry_revision = registry.revision(brain)
    canary = AdaptiveContextCanary(Path(tmp) / "state", registry,
                                   ContextCompiler(registry), runtime,
                                   settings_reader=lambda: settings)
    return canary.prepare(trace, objective, brain, "session-quota", [], "dashboard",
                          "groq", "llama-3.3-70b-versatile", "api",
                          lambda memory, skills: "PROMPT LÕI")


# Hạn mức rộng: phải chạy bình thường, để biết harness dựng đúng.
_tmp = tempfile.mkdtemp(prefix="javis-p8-ok-")
_plan = _p8_run(_tmp, _p8_settings(rolling_tpm=12_000, max_input=8_000))
check("hạn mức rộng: Phase 8 không từ chối", _plan.action != "reject")
shutil.rmtree(_tmp, ignore_errors=True)

# Hạn mức siết tới mức không đủ cho cả phần BẮT BUỘC. Đây là toàn bộ lý do của Việc 5.
_tmp = tempfile.mkdtemp(prefix="javis-p8-tight-")
_plan = _p8_run(_tmp, _p8_settings(rolling_tpm=60, max_input=50))
check("hạn mức siết: KHÔNG rơi về legacy (legacy còn to hơn)", _plan.action != "legacy")
check("hạn mức siết: từ chối hẳn", _plan.action == "reject")
check("hạn mức siết: nêu đúng mã lý do quota",
      _plan.reason in context_compiler.QUOTA_REASON_CODES)
check("hạn mức siết: có câu giải thích cho người dùng",
      bool((_plan.rejection_message or "").strip()))
check("hạn mức siết: nói rõ là CHƯA gửi request đi",
      "chưa gửi" in (_plan.rejection_message or "").lower())
check("hạn mức siết: gợi ý provider người dùng đang có",
      "openai" in _plan.rejection_message or "gemini" in _plan.rejection_message)
shutil.rmtree(_tmp, ignore_errors=True)

# Đường gọi trong main phải THẬT SỰ xử lý action reject, nếu không thì mọi thứ trên vô
# nghĩa: plan trả reject mà chỗ gọi vẫn coi "khác use thì dùng legacy".
import inspect  # noqa: E402

import main  # noqa: E402

_ws_src = inspect.getsource(main)
_i_reject = _ws_src.find('_phase8_plan.action == "reject"')
_i_use = _ws_src.find('_phase8_plan.system_prompt')
check("main có nhánh riêng cho action reject", _i_reject != -1)
check("nhánh reject đứng TRƯỚC nhánh rơi về legacy",
      _i_reject != -1 and _i_use != -1 and _i_reject < _i_use)

print()
if _fails:
    print(f"THẤT BẠI {len(_fails)}: {_fails}")
    sys.exit(1)
print("OK - test_quota_direction: tất cả pass")
