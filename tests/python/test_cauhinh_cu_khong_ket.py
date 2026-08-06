"""Máy đã chạy Javis từ trước nâng cấp lên: mức tiết kiệm phải chạy được ngay.

    python tests/run.py cauhinh_cu_khong_ket

Vì sao có file này. Chủ repo bật mức tiết kiệm trên gói ChatGPT rồi chat, mà dòng dưới câu
trả lời vẫn ghi "Đầy đủ". Máy anh cài Javis từ trước, và đó chính là cả vấn đề:

  - `write_settings` ghi lại TOÀN BỘ config đã trộn, nên mặc định của ngày hôm đó bị đóng
    băng vào settings.json ngay lần đầu người dùng bấm bất cứ thứ gì.
  - `read_settings` trộn file ĐÈ LÊN mặc định, nên sau này sửa mặc định cho rộng ra thì máy
    đã cài rồi KHÔNG BAO GIỜ thấy. Mặc định mới chỉ tới được máy cài mới.
  - Trước 0.12.4, `memory_canary` và `lazy_skill_canary` chỉ cho `provider_kinds: ["api"]`.
    Mọi máy chạy từ trước mốc đó ghim cứng `["api"]` trong settings.json.

Ghép lại: chủ máy nâng cấp, bấm mức Tối ưu, trang báo xanh "đã bật, có hiệu lực ngay", rồi
mọi lượt trên gói ChatGPT hay gói Claude vẫn gửi nguyên CLAUDE.md vì cả ba nguồn bị loại với
lý do `provider_kind_not_allowed`. Không lỗi, không cảnh báo, chỉ có dòng "Đầy đủ" dưới mỗi
câu trả lời và hoá đơn token không giảm. Test ở tầng dưới không thấy được vì chúng chạy trên
máy sạch, nơi mặc định mới luôn đúng.

File này dựng ĐÚNG một máy cũ: ghi settings.json kiểu trước 0.12.4 TRƯỚC khi nạp config, rồi
bấm mức như người dùng bấm.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path

# PHẢI ghi file trước khi import config: config đọc JAVIS_STATE_DIR lúc nạp module.
_STATE = Path(tempfile.mkdtemp(prefix="javis-cu-"))
os.environ["JAVIS_STATE_DIR"] = str(_STATE)
(_STATE / "settings.json").write_text(json.dumps({
    "model": {"main": {"provider": "openai-oauth", "model": "gpt-5.6-luna"}},
    "context_runtime": {
        "mode": "shadow",
        # Đúng hình dạng settings.json của một máy cài trước 0.12.4.
        "conversation_state_canary": {"allocation_basis_points": 0,
                                      "provider_kinds": ["api"], "channels": ["dashboard"]},
        "memory_canary": {"allocation_basis_points": 0,
                          "provider_kinds": ["api"], "channels": ["dashboard"]},
        "lazy_skill_canary": {"allocation_basis_points": 0,
                              "provider_kinds": ["api"], "channels": ["dashboard"]},
    },
}, ensure_ascii=False), encoding="utf-8")

import config as cfg  # noqa: E402
import main  # noqa: E402

_fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)


BRAIN = Path(tempfile.mkdtemp(prefix="javis-cu-brain-"))
(BRAIN / "Memory" / "facts").mkdir(parents=True, exist_ok=True)
(BRAIN / "Memory" / "MEMORY.md").write_text("- [user] Chu ho nuoc mam\n", encoding="utf-8")
(BRAIN / "Memory" / "facts" / "a.md").write_text(
    "---\ntype: user\n---\nChu ho kinh doanh nuoc mam.\n", encoding="utf-8")
(BRAIN / "skills").mkdir(exist_ok=True)


# ============================================================
# 1. File cũ ghim ["api"], đọc ra phải đã được nới
# ============================================================
_rc = cfg.read_settings()["context_runtime"]
check("mảng bộ nhớ được nới cho cả gói thuê bao",
      set(_rc["memory_canary"]["provider_kinds"]) >= {"api", "cli", "oauth"})
check("mảng skill cũng vậy",
      set(_rc["lazy_skill_canary"]["provider_kinds"]) >= {"api", "cli", "oauth"})
# Mảng nào CỐ Ý chỉ chạy trên engine API thì không được nới bừa: Claude Code và Codex tự nhớ
# mạch hội thoại của chúng, nhét thêm transcript vào system prompt là gửi HAI LẦN.
check("CANARY: mảng gửi lại lịch sử vẫn chỉ dành cho engine API",
      _rc["conversation_state_canary"]["provider_kinds"] == ["api"])
# Người vận hành tự thêm loại bộ não lạ thì phải giữ nguyên: hàm này chỉ NỚI.
#
# `channels` phải khai ĐỦ theo mặc định hiện tại, nếu không thì chính nó là thứ được nới và
# hàm trả True - lúc đó phép thử không còn kiểm được điều nó định kiểm. Bản trước ghi cứng
# ["dashboard"] và hoá đỏ khi mặc định mở thêm telegram (0.24.0).
_ch_mac_dinh = list(cfg._DEFAULT["context_runtime"]["memory_canary"]["channels"])
_rieng = {"context_runtime": {"memory_canary": {
    "provider_kinds": ["api", "cli", "oauth", "loai-rieng"], "channels": _ch_mac_dinh}}}
check("chỉ nới, không bao giờ thu hẹp",
      cfg._no_rong_pham_vi_bo_nao(_rieng) is False
      and _rieng["context_runtime"]["memory_canary"]["provider_kinds"][-1] == "loai-rieng")
check("và báo lại là có sửa hay không",
      cfg._no_rong_pham_vi_bo_nao({"context_runtime": {
          "memory_canary": {"provider_kinds": ["api"]}}}) is True)
check("cấu hình không có context_runtime thì bỏ qua êm",
      cfg._no_rong_pham_vi_bo_nao({}) is False)


# ============================================================
# 2. Bấm mức Tối ưu trên máy cũ đó thì phải tiết kiệm THẬT
# ============================================================
_r = asyncio.run(main.runtime_preset_set(level="saving"))
check("bấm mức Tối ưu thì mode sang canary", _r.get("mode") == "canary")

_ke = main._get_adaptive_context().prepare(
    None, "javis tiet kiem token the nao", BRAIN, "s-cu",
    [{"role": "user", "content": "javis tiet kiem token the nao", "id": 1}],
    "dashboard", "openai-oauth", "gpt-5.6-luna", "oauth", lambda a, b: "BO LUAT DAI " * 60)
check("CANARY: máy cài từ trước, bấm Tối ưu trên gói ChatGPT là tiết kiệm thật",
      _ke.action == "use" and _ke.reason == "compiled")
if _ke.action != "use":
    print(f"     -> action={_ke.action} reason={_ke.reason}")
    for _n, _v in (_ke.feature_status or {}).items():
        print(f"        {_n}: assigned={_v.get('assigned')} reason={_v.get('reason')}")

_ke_cli = main._get_adaptive_context().prepare(
    None, "javis tiet kiem token the nao", BRAIN, "s-cu-cli",
    [{"role": "user", "content": "javis tiet kiem token the nao", "id": 1}],
    "dashboard", "anthropic-cli", "opus", "cli", lambda a, b: "BO LUAT DAI " * 60)
check("gói Claude Code trên máy cũ cũng vậy", _ke_cli.action == "use")

# Sau khi bấm mức, chính FILE settings.json cũng phải được chữa - để người mở file ra đọc
# không thấy một con số đã chết, và để lần sau khỏi phải chữa lại trong bộ nhớ.
_tren_dia = json.loads((_STATE / "settings.json").read_text(encoding="utf-8"))
_kinds = ((_tren_dia.get("context_runtime") or {}).get("memory_canary") or {}
          ).get("provider_kinds") or []
check("và bản ghi trên đĩa cũng được chữa luôn",
      set(_kinds) >= {"api", "cli", "oauth"})

print(("\nFAILED: " + ", ".join(_fails)) if _fails else "\nAll passed")
sys.exit(1 if _fails else 0)
