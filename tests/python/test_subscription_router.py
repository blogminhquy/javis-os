"""Bộ định tuyến phải dùng được cho GÓI THUÊ BAO, không chỉ API key.

    python tests/run.py subscription_router

Yêu cầu của chủ repo: "anh muốn bộ định tuyến mới phải dùng được tất cho cả claude lẫn
chatgpt subcription chứ không chỉ API key".

Trước bản này, ba thứ khoá chặt đường thuê bao lại, và cả ba đều IM LẶNG:

  1. `provider_kinds: ["api"]` - Claude Code (kind=cli) và Codex (kind=oauth) bị loại ngay ở
     bước phân bổ canary, lý do "provider_kind_not_allowed".
  2. Kể cả mở cổng đó ra, `_quota()` vẫn trả None vì gói thuê bao không có hạn mức
     token-mỗi-phút để khai -> fail-closed -> legacy mãi mãi.
  3. Và hai nhánh engine trong main.py không hề GỌI prepare(), chúng gọi thẳng
     `_legacy_system_prompt()`. Đây đúng họ lỗi "code đúng, test xanh, mà không nối vào
     đường thật" đã lặp lại năm lần trong nhánh này - nên có hẳn một mục kiểm cái nối.

Cộng thêm một lỗi ngân sách phát hiện lúc làm: mức "Tiết kiệm" khai hạn mức theo TÊN ĐƯỜNG,
mà ba đường Phase 8 lại đọc hạn mức ké từ `context_sources`, nên bấm mức xong vẫn không có
gì chạy - đúng câu "ấn vào đặt thì không có gì diễn ra".
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import json
import os
import sys
import tempfile
import time

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-sub-")

import adaptive_context_runtime as acr  # noqa: E402
import config as cfg  # noqa: E402
import limit_learner  # noqa: E402
import main  # noqa: E402
import model_limits  # noqa: E402

_fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)


_MAIN_SRC = (ROOT / "server" / "main.py").read_text(encoding="utf-8")

# ============================================================
# 1. Cổng provider_kinds
# ============================================================
_rt = cfg._DEFAULT["context_runtime"]
for _p in ("memory_canary", "lazy_skill_canary"):
    _kinds = set(_rt[_p]["provider_kinds"])
    check(f"'{_p}' cho phép Claude Code (cli)", "cli" in _kinds)
    check(f"'{_p}' cho phép ChatGPT/Codex (oauth)", "oauth" in _kinds)
    check(f"'{_p}' vẫn giữ engine API", "api" in _kinds)

# conversation_state CỐ Ý chỉ chạy trên API. Claude Code (--resume) và Codex (exec resume) tự
# nối mạch hội thoại, nên nhét thêm cửa sổ transcript vào system prompt là gửi lịch sử HAI
# LẦN. Đây là lựa chọn, không phải sót - nên khoá lại để lần sau ai mở cũng phải đọc lý do.
check("CANARY: conversation_state KHÔNG mở cho engine tự resume",
      set(_rt["conversation_state_canary"]["provider_kinds"]) == {"api"})

# Và FeaturePolicy phải thật sự đọc được cổng đó, không phải chỉ có trong file cấu hình.
_pol = acr.FeaturePolicy.from_settings({"context_runtime": cfg._DEFAULT["context_runtime"]},
                                       "memory_canary")
check("policy đọc đúng provider_kinds từ settings", "cli" in _pol.provider_kinds)
_ok, _bucket, _ly_do = _pol.assigned("canary", "phien-1", "dashboard", "cli")
check("cli không còn bị chặn ở bước phân bổ", _ly_do != "provider_kind_not_allowed")

# ============================================================
# 2. Ngân sách ngữ cảnh cho thuê bao
# ============================================================
check("config có khai trần ngữ cảnh cho thuê bao",
      isinstance(_rt.get("subscription_context"), dict))
_sub = _rt["subscription_context"]
check("trần ngữ cảnh là số dương", int(_sub.get("context_window") or 0) > 0)
check("có chừa chỗ cho câu trả lời", int(_sub.get("reserved_output_tokens") or 0) > 0)

_q = acr.AdaptiveContextCanary._subscription_quota({"context_runtime": _rt})
check("dựng được ngân sách từ trần ngữ cảnh", isinstance(_q, dict))
check("ngân sách vào = trần - phần chừa cho câu trả lời",
      _q["hard_input"] == int(_sub["context_window"]) - int(_sub["reserved_output_tokens"]))
# rolling_tpm là hạn mức token-mỗi-phút. Gói thuê bao KHÔNG công bố con số đó, nên tuyệt đối
# không được bịa một số nhỏ vào đây - bịa nhỏ là tự chặn chính mình mà không ai hiểu vì sao.
check("CANARY: không bịa hạn mức mỗi phút (đặt rộng để nó không ràng buộc)",
      _q["rolling_tpm"] >= _q["hard_input"])

# Khai hỏng thì trả None chứ không được nổ giữa lượt chat, cũng không được đoán bừa.
for _hong in ({}, {"context_runtime": {}},
              {"context_runtime": {"subscription_context": "abc"}},
              {"context_runtime": {"subscription_context": {"context_window": "x"}}},
              {"context_runtime": {"subscription_context": {"context_window": 0}}},
              {"context_runtime": {"subscription_context": {"context_window": 10,
                                                            "reserved_output_tokens": 99}}}):
    check(f"khai hỏng {json.dumps(_hong, ensure_ascii=False)[:52]} → None, không đoán",
          acr.AdaptiveContextCanary._subscription_quota(_hong) is None)

# Và engine API KHÔNG được ăn ké ngân sách này - nó chỉ dành cho thuê bao. Ăn ké nghĩa là
# admission cho qua đúng cái request lẽ ra phải chặn vì vượt TPM thật.
_src_acr = (ROOT / "server" / "adaptive_context_runtime.py").read_text(encoding="utf-8")
check("CANARY: ngân sách thuê bao chỉ dùng khi provider_kind là cli/oauth",
      "if quota is None and subscription:" in _src_acr
      and 'provider_kind or "").strip().casefold() in ("cli", "oauth")' in _src_acr)

# ============================================================
# 3. Chiều fail-closed: thuê bao vượt ngân sách thì KHÔNG được chặn lượt chat
# ============================================================
# Con số vừa vượt là trần TA TỰ KHAI, không phải hạn mức nhà cung cấp nói ra. Lấy số của
# chính mình để từ chối lượt chat của người dùng là vượt quyền - khai nhầm thấp một lần là
# chết cả đường Claude Code, mà lỗi đó lại im lặng.
_i = _src_acr.find("quota_reason = context_compiler.quota_block_reason(report)")
_khoi = _src_acr[_i:_i + 1600]
check("CANARY: thuê bao vượt ngân sách → về legacy, KHÔNG reject",
      "if quota_reason and subscription:" in _khoi
      and '"legacy", "subscription_soft_over_budget"' in _khoi)
check("nhánh reject cho engine API vẫn còn nguyên",
      '"reject", quota_reason' in _khoi)
# Thứ tự quan trọng: xét thuê bao TRƯỚC, nếu không nhánh reject nuốt mất.
check("xét nhánh thuê bao TRƯỚC nhánh reject",
      _khoi.find("and subscription:") < _khoi.find('"reject", quota_reason'))

# ============================================================
# 4. NỐI VÀO ĐƯỜNG THẬT - phần hay bị sót nhất
# ============================================================
check("có hàm dựng prompt riêng cho engine thuê bao",
      "async def _subscription_system_prompt(" in _MAIN_SRC)
# Cắt đúng THÂN hàm: đếm ký tự thì sửa vài dòng là cửa sổ trượt sang code khác, và assertion
# "không có build_adaptive_source_prompt" sẽ đỏ/xanh vì lý do chẳng liên quan.
_than = _MAIN_SRC.split("async def _subscription_system_prompt(")[1]
_than = _than[:_than.find('\n            final_text = ""')]
check("cắt được đúng thân hàm", 0 < len(_than) < 4000)
check("hàm đó thật sự gọi prepare() của Phase 8",
      "_get_adaptive_context().prepare," in _than)

# Nền phải là build_system_prompt (GIỮ CLAUDE.md), không phải build_adaptive_source_prompt.
# Bỏ CLAUDE.md là bỏ 21.500 ký tự luật hành xử của Javis để tiết kiệm thứ gói thuê bao không
# tính tiền - đổi hành vi lấy một khoản không cần.
check("CANARY: nền vẫn là build_system_prompt (giữ CLAUDE.md)",
      "build_system_prompt(" in _than)
# Soi lời GỌI (có dấu mở ngoặc), không soi cái TÊN: docstring của hàm có nhắc tên đó để
# giải thích vì sao KHÔNG dùng nó, quét tên trần là bắt nhầm chính lời giải thích.
check("CANARY: KHÔNG dùng nền rút gọn vốn bỏ CLAUDE.md",
      "build_adaptive_source_prompt(" not in _than)
check("lỗi ở Phase 8 thì rơi về prompt cũ, không phá lượt chat",
      "_legacy_system_prompt()" in _than)

# Hai nhánh engine phải GỌI nó. Đây là chỗ mà bốn lần trước code đúng mà không ai gọi.
check("CANARY: nhánh Claude Code gọi hàm mới",
      '_subscription_system_prompt(\n                    "cli"' in _MAIN_SRC)
check("CANARY: nhánh Codex gọi hàm mới",
      '_subscription_system_prompt("codex"' in _MAIN_SRC)
# Và không được còn nhánh nào lặng lẽ quay về đường cũ.
_cli_khoi = _MAIN_SRC[_MAIN_SRC.find("# ===== PROVIDER anthropic-cli"):][:600]
check("nhánh Claude Code không còn gán thẳng prompt cũ",
      "sysprompt = _legacy_system_prompt()" not in _cli_khoi)
_codex_khoi = _MAIN_SRC[_MAIN_SRC.find("# ===== ChatGPT subscription qua CODEX CLI"):][:600]
check("nhánh Codex không còn gán thẳng prompt cũ",
      "sysprompt = _legacy_system_prompt()" not in _codex_khoi)

# ============================================================
# 5. Mirror skill KHÔNG được tắt theo cờ tiết kiệm token
# ============================================================
# include_skills chỉ nói "có chèn khối ROUTER SKILL vào prompt không" - chuyện về CHỮ. Mirror
# là tác dụng phụ lên ĐĨA mà Claude Code/Codex dựa vào để tự tìm skill. Gộp hai chuyện là bật
# tiết kiệm token cho Claude Code = tắt luôn skill native của nó, và lỗi đó im lặng hoàn toàn.
_bsp = _MAIN_SRC[_MAIN_SRC.find("def build_system_prompt("):]
_bsp = _bsp[:_bsp.find("def build_adaptive_source_prompt(")]
check("CANARY: mirror skill chạy vô điều kiện", "system_sync.mirror_skills(root)" in _bsp)
_i_mirror = _bsp.find("system_sync.mirror_skills(root)")
check("CANARY: mirror KHÔNG nằm trong nhánh if include_skills",
      "if include_skills:\n            system_sync.mirror_skills" not in _bsp)
# Chỉ mục năng lực vẫn phải nói ĐÚNG số skill, kể cả khi bỏ khối router: đưa cho nó danh sách
# rỗng là Javis tự khai mình không có skill nào rồi đi tạo lại thứ đã có.
check("CANARY: quét skill không phụ thuộc include_skills (chỉ mục phải nói thật)",
      "if include_skills" not in _bsp[:_bsp.find("_skills = skill_router.list_skills(root")]
      and "_skills = skill_router.list_skills(root" in _bsp)
check("khối ROUTER SKILL dài mới là thứ bị gập lại",
      "if include_skills:\n            base += _skill_router_block(" in _bsp)

# Cố ý KHÔNG gọi build_system_prompt() thật ở đây: nó quét brains/ của chính người dùng (dữ
# liệu cá nhân, đã gitignore) và còn ghi mirror vào đó. Test không được đụng vào chỗ đó.
check("khối ROUTER SKILL nằm SAU khối chỉ mục năng lực (bỏ cái dài, giữ cái ngắn)",
      _bsp.find("_javis_capability_summary(") < _bsp.find("_skill_router_block("))

# ============================================================
# 6. Nhận ra lỗi HẾT LƯỢT của gói thuê bao
# ============================================================
_now = 1_700_000_000.0

# Dạng máy đọc được mà Claude Code in ra.
_h = limit_learner.parse_subscription_limit(
    f"Claude AI usage limit reached|{int(_now) + 3600}", now=_now)
check("nhận ra dạng máy của Claude Code", _h is not None and _h.engine == "claude-code")
check("đọc đúng mốc reset từ epoch", _h and int(_h.reset_epoch) == int(_now) + 3600)

_h = limit_learner.parse_subscription_limit(
    "You've reached your usage limit. Resets in 2 hours 30 minutes.", now=_now)
check("nhận ra dạng chữ", _h is not None)
check("tính được mốc reset từ 'resets in 2 hours 30 minutes'",
      _h and abs(_h.reset_epoch - (_now + 2 * 3600 + 30 * 60)) < 1)
check("giữ nguyên văn câu nói về reset để còn hiện lại",
      _h and "2 hours 30 minutes" in _h.reset_text)

_h = limit_learner.parse_subscription_limit("5-hour limit reached", now=_now)
check("nhận ra cửa sổ 5 giờ", _h is not None and _h.scope == "5 giờ")
_h = limit_learner.parse_subscription_limit("You've reached your weekly limit", now=_now)
check("nhận ra cửa sổ tuần", _h is not None and _h.scope == "tuần")

_h = limit_learner.parse_subscription_limit("You've hit your usage limit.",
                                            engine_hint="codex", now=_now)
check("nhận ra lỗi phía Codex", _h is not None and _h.engine == "codex")
# Không nói lúc nào reset thì reset_epoch phải là 0 = KHÔNG BIẾT, không được đoán một mốc.
check("CANARY: không nói lúc nào reset thì reset_epoch = 0 (không bịa mốc)",
      _h is not None and _h.reset_epoch == 0.0)
# Mốc đã trôi qua cũng là không biết, chứ không phải "reset ở quá khứ".
_h = limit_learner.parse_subscription_limit(
    f"Claude AI usage limit reached|{int(_now) - 500}", now=_now)
check("mốc đã trôi qua thì coi như không biết", _h is not None and _h.reset_epoch == 0.0)

# KHÔNG được nhận nhầm. Ba loại lỗi khác nhau, ba cách xử lý khác nhau.
for _khac in ("", None, "Không tìm thấy Codex CLI", "invalid api key",
              "on tokens per minute (TPM): Limit 12000, Used 8812, Requested 4701"):
    check(f"KHÔNG nhận nhầm {str(_khac)[:38]!r} là hết lượt thuê bao",
          limit_learner.parse_subscription_limit(_khac) is None)
# Và chiều ngược lại: hết lượt thuê bao không được rơi vào đường co-nhỏ-prompt.
check("CANARY: lỗi hết lượt thuê bao KHÔNG bị đọc thành hạn mức token",
      limit_learner.parse_limit_error(
          429, f"Claude AI usage limit reached|{int(_now) + 60}") is None)

# ============================================================
# 7. Câu nói cho người dùng
# ============================================================
_h = limit_learner.parse_subscription_limit(
    f"Claude AI usage limit reached|{int(time.time()) + 5400}")
_noi = model_limits.subscription_blocked_hint(_h, ("Groq (API)",))
check("nói rõ là hết lượt gói Claude", "Claude" in _noi)
check("nói còn bao lâu nữa", "giờ" in _noi or "phút" in _noi)
check("chỉ ra bộ não đang sẵn sàng để chạy tạm", "Groq (API)" in _noi)
# Chỗ này dễ sai nhất: hạn mức thuê bao đếm LƯỢT theo giờ, rút gọn câu hỏi không giúp gì.
# Khuyên "rút gọn yêu cầu" ở đây là chỉ sai đường cho người đang bí.
check("CANARY: KHÔNG khuyên rút gọn yêu cầu (rút gọn không giải được hạn mức theo giờ)",
      "KHÔNG giúp" in _noi)
check("không dùng em dash", "—" not in _noi)

_h2 = limit_learner.parse_subscription_limit("You've hit your usage limit.",
                                             engine_hint="codex")
_noi2 = model_limits.subscription_blocked_hint(_h2, ())
check("không biết mốc reset thì NÓI là chưa biết", "chưa biết" in _noi2)
check("chưa có bộ não dự phòng thì gợi ý cắm thêm", "Models" in _noi2)

# Và main.py phải thật sự DÙNG câu đó ở cả hai nhánh, thay cho chuỗi lỗi thô.
check("có hàm dịch lỗi thô sang câu nói được",
      "def _subscription_limit_message(" in _MAIN_SRC)
check("CANARY: nhánh Claude Code dùng câu đã dịch",
      '_subscription_limit_message(event.get("content") or "", "claude-code")' in _MAIN_SRC)
check("CANARY: nhánh Codex dùng câu đã dịch",
      '_subscription_limit_message(ev.get("content") or "", "codex")' in _MAIN_SRC)
# Antigravity CLI cũng chạy bằng gói Google nên cùng luật: hết lượt phải ra
# câu tiếng Việt, không phải nguyên văn của Google.
check("CANARY: nhánh Antigravity CLI dùng câu đã dịch",
      '"antigravity-cli")' in _MAIN_SRC and _MAIN_SRC.count("_subscription_limit_message(") >= 5)
# Bộ não thứ 11 (Grok Build CLI) chạy bằng gói SuperGrok / X Premium+ nên cùng luật: hết lượt
# phải ra câu tiếng Việt, không phải nguyên văn của xAI.
check("CANARY: nhánh Grok Build CLI dùng câu đã dịch",
      '"grok-cli")' in _MAIN_SRC and _MAIN_SRC.count("_subscription_limit_message(") >= 7)
check("không nhận ra thì vẫn trả nguyên văn lỗi gốc, không nuốt mất",
      _MAIN_SRC.count('"content": _noi or ') == 4)
check("hàm dịch nuốt mọi lỗi của chính nó (câu báo lỗi không được tự nổ)",
      main._subscription_limit_message(None, "claude-code") == ""
      and main._subscription_limit_message(12345, "codex") == "")

# TUYỆT ĐỐI không tự đổi engine hộ: đó là tiêu hạn mức của một tài khoản khác, có khi mất
# tiền thật. Việc của Javis là nói rõ, không phải quyết thay.
check("CANARY: không tự đổi bộ não hộ người dùng",
      "_set_main_model" not in _MAIN_SRC.split("def _subscription_limit_message(")[1][:1400])

# ============================================================
# 8. Mức "Tiết kiệm" phải khai hạn mức vào ĐÚNG chỗ Phase 8 đọc
# ============================================================
check("có bảng nói rõ đường nào đọc hạn mức ở đâu", hasattr(main, "QUOTA_OWNER_OF"))
for _p in ("conversation_state_canary", "memory_canary", "lazy_skill_canary"):
    check(f"'{_p}' đọc hạn mức ké từ context_sources",
          main.QUOTA_OWNER_OF.get(_p) == "context_sources")


async def _thu_preset():
    _cfg = cfg.read_settings()
    _cfg.setdefault("model", {})["main"] = {"provider": "groq",
                                            "model": "llama-3.3-70b-versatile"}
    _cfg["model"]["groq_api_key"] = "gsk_test"
    cfg.write_settings(_cfg)

    r = await main.runtime_preset_set(level="saving")
    check("bấm mức Tiết kiệm → ok", isinstance(r, dict) and r.get("ok"))
    _rt_sau = cfg.read_settings()["context_runtime"]
    # ĐÂY là lỗi cũ: ba đường Phase 8 bật lên, mode sang canary, mà chỗ chúng ĐỌC hạn mức
    # vẫn rỗng nên _quota() trả None và mọi lượt rơi về legacy.
    check("CANARY: hạn mức được khai vào context_sources (chỗ Phase 8 thật sự đọc)",
          len((_rt_sau.get("context_sources") or {}).get("quota_profiles") or []) > 0)
    check("và Phase 8 dựng được ngân sách từ đó",
          acr.AdaptiveContextCanary._quota(
              {"context_runtime": _rt_sau}, "groq", "llama-3.3-70b-versatile") is not None)

    # Gói thuê bao thì không có hạn mức token để khai - và KHÔNG được cảnh báo oan về việc đó,
    # vì Phase 8 dùng trần ngữ cảnh chứ không cần quota profile.
    _cfg = cfg.read_settings()
    _cfg["model"]["main"] = {"provider": "anthropic-cli", "model": "opus"}
    _cfg["context_runtime"]["context_sources"]["quota_profiles"] = []
    cfg.write_settings(_cfg)
    r = await main.runtime_preset_set(level="saving")
    check("dùng Claude Code bấm mức Tiết kiệm cũng ok", isinstance(r, dict) and r.get("ok"))
    check("CANARY: không cảnh báo oan về hạn mức cho gói thuê bao",
          not (r.get("canh_bao") or []))
    _rt_sau = cfg.read_settings()["context_runtime"]
    check("và Phase 8 vẫn có ngân sách (trần ngữ cảnh của thuê bao)",
          acr.AdaptiveContextCanary._subscription_quota(
              {"context_runtime": _rt_sau}) is not None)


asyncio.run(_thu_preset())

print()
if _fails:
    print(f"THẤT BẠI {len(_fails)}: {_fails}")
    sys.exit(1)
print("OK - test_subscription_router: tất cả pass")
