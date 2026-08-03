"""Bật mức tiết kiệm thì nó phải CHẠY THẬT, trên MỌI bộ não, và phải TỰ KHAI đúng.

    python tests/run.py tiet_kiem_chay_that

Vì sao có file này. Trang Tiết kiệm token đã nói được nó tiết kiệm bao nhiêu (0.13.0) và đặt
tên chế độ cho dễ hiểu (0.13.1), nhưng chưa ai kiểm chuyện cơ bản nhất: bấm vào rồi thì có
thật sự tiết kiệm không. Rà lại thì thủng ở bốn chỗ, và cả bốn đều IM LẶNG - trang vẫn báo
xanh, người dùng vẫn trả tiền như cũ:

  1. `_quota` fail-closed đòi hạn mức khai tay, mà bảng gợi ý `model_limits.KNOWN_LIMITS`
     hiện CHỈ có Groq. Nên OpenRouter, OpenAI, Gemini, Anthropic API bấm mức Tối ưu là bật
     một đường chết: mọi lượt trả về `hard_quota_unknown` rồi gửi nguyên CLAUDE.md. Bốn trên
     năm engine API key dính.
  2. `/runtime/preset` chỉ khai hạn mức khi danh sách còn TRỐNG. Đổi bộ não - đúng thứ Javis
     mời chào - là kẹt lại với hạn mức của bộ não cũ, `_quota` lọc theo provider nên không
     khớp cái nào, và mức tiết kiệm lặng lẽ ngừng chạy.
  3. `pin_execution_path` cho ai ghim trước thắng. Trên engine API, các tầng Phase 9/7/6/5
     chạy TRƯỚC Phase 8 và tầng nào không nhận lượt thì ghim luôn "legacy". Phase 8 nhận
     lượt, gói ngữ cảnh nhỏ lại thật, nhưng ghim "sources" tới nơi thì đã muộn: dòng dưới
     câu trả lời ghi "Đầy đủ" và bảng đo 24 giờ xếp lượt đó vào cột đường cũ.
  4. Mức "Siêu tiết kiệm" hơn "Tối ưu" ở đúng đường tắt cho câu hỏi đơn giản, mà đường đó
     chỉ chạy trên engine API key. Bộ não gói thuê bao bấm vào thì y hệt mức Tối ưu, trong
     khi trang vẫn khoe giảm 96%.

File này chạy THẬT: dựng máy sạch, bấm mức như người dùng bấm, rồi hỏi thẳng lớp quyết định
xem lượt này đi đường nào.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-tkct-")

import adaptive_context_runtime as acr  # noqa: E402
import config as cfg  # noqa: E402
import context_runtime  # noqa: E402
import main  # noqa: E402

_fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)


# Brain tối thiểu nhưng THẬT: có bộ nhớ để Phase 8 còn thứ mà chọn lọc.
BRAIN = Path(tempfile.mkdtemp(prefix="javis-tkct-brain-"))
(BRAIN / "Memory" / "facts").mkdir(parents=True, exist_ok=True)
(BRAIN / "Memory" / "MEMORY.md").write_text(
    "- [user] Chu ho kinh doanh nuoc mam\n", encoding="utf-8")
(BRAIN / "Memory" / "facts" / "chu.md").write_text(
    "---\ntype: user\n---\nChu ho kinh doanh nuoc mam truyen thong.\n", encoding="utf-8")
(BRAIN / "skills").mkdir(exist_ok=True)


def dat_bo_nao(provider, model, key_field=None):
    s = cfg.read_settings()
    m = s.setdefault("model", {})
    m["main"] = {"provider": provider, "model": model}
    if key_field:
        m[key_field] = "test-key"
    cfg.write_settings(s)


def bam_muc(level):
    return asyncio.run(main.runtime_preset_set(level=level))


def quyet_dinh(provider, model, kind, phien="s"):
    """Hỏi thẳng lớp quyết định: lượt này đi đường tiết kiệm hay đường cũ."""
    return main._get_adaptive_context().prepare(
        None, "doanh thu hom nay the nao", BRAIN, phien,
        [{"role": "user", "content": "doanh thu hom nay the nao", "id": 1}],
        "dashboard", provider, model, kind, lambda mem, sk: "BO LUAT DAI " * 60)


# ============================================================
# 1. MỌI bộ não bấm mức Tối ưu đều phải tiết kiệm thật
# ============================================================
# Đây là phần thủng nặng nhất và im lặng nhất: bốn trên năm engine API key.
BO_NAO = [
    ("Groq", "groq", "llama-3.3-70b-versatile", "groq_api_key", "api"),
    ("OpenRouter", "openrouter", "openai/gpt-4o-mini", "openrouter_key", "api"),
    ("OpenAI", "openai", "gpt-4o-mini", "openai_api_key", "api"),
    ("Gemini", "gemini", "gemini-2.0-flash", "gemini_api_key", "api"),
    ("Anthropic API", "anthropic-api", "claude-sonnet-4", "anthropic_api_key", "api"),
    ("ChatGPT (gói)", "openai-oauth", "gpt-5.6-luna", None, "oauth"),
    ("Claude Code (gói)", "anthropic-cli", "opus", None, "cli"),
]
for nhan, prov, model, kf, kind in BO_NAO:
    dat_bo_nao(prov, model, kf)
    bam_muc("saving")
    ke = quyet_dinh(prov, model, kind, f"s-{prov}")
    check(f"'{nhan}' bấm Tối ưu thì đi đường tiết kiệm thật",
          ke.action == "use" and ke.reason == "compiled")
    if ke.action != "use":
        print(f"     -> action={ke.action} reason={ke.reason}")

# Và trần mặc định cho engine API phải có thật trong config, không thì mọi thứ trên chỉ
# đang chạy nhờ một mặc định ngầm ở đâu đó.
_rt_mac_dinh = (cfg._DEFAULT.get("context_runtime") or {})
check("config có trần ngữ cảnh mặc định cho engine API key",
      isinstance(_rt_mac_dinh.get("api_context"), dict)
      and int(_rt_mac_dinh["api_context"].get("context_window") or 0) > 0)
_q = acr.AdaptiveContextCanary._api_context_quota({"context_runtime": _rt_mac_dinh})
check("trần đó dựng được thành ngân sách dùng ngay", bool(_q) and _q["hard_input"] > 0)
# SOFT là điểm mấu chốt: đây là con số của CHÍNH TA, không phải lời nhà cung cấp. Lấy nó ra
# từ chối lượt chat của người dùng là vượt quyền.
check("CANARY: trần tự khai phải là SOFT, không được dùng để chặn lượt chat",
      _q.get("soft") is True)
check("trần thuê bao cũng vậy",
      (acr.AdaptiveContextCanary._subscription_quota(
          {"context_runtime": _rt_mac_dinh}) or {}).get("soft") is True)
_src = (SERVER / "adaptive_context_runtime.py").read_text(encoding="utf-8")
_i = _src.find("quota_reason = context_compiler.quota_block_reason(report)")
_khoi = _src[_i:_i + 1800]
check("CANARY: vượt ngân sách SOFT thì về đường cũ, KHÔNG reject",
      'quota.get("soft")' in _khoi and '"legacy", "self_declared_soft_over_budget"' in _khoi)
check("nhánh reject cho hạn mức THẬT vẫn còn nguyên", '"reject", quota_reason' in _khoi)
check("xét nhánh soft TRƯỚC nhánh reject",
      _khoi.find('quota.get("soft")') < _khoi.find('"reject", quota_reason'))
# Hạn mức khai tay và hạn mức HỌC ĐƯỢC là số thật, phải xét trước mọi trần tự khai.
_i2 = _src.find("quota = self._quota(settings, provider, model)")
_thu_tu = _src[_i2:_i2 + 700]
check("CANARY: khai tay > học được > trần thuê bao > trần API mặc định",
      _thu_tu.find("self._quota(") < _thu_tu.find("self._learned_quota(")
      < _thu_tu.find("self._subscription_quota(") < _thu_tu.find("self._api_context_quota("))


# ============================================================
# 2. Đổi bộ não thì hạn mức phải theo, không kẹt lại ở bộ não cũ
# ============================================================
dat_bo_nao("groq", "llama-3.3-70b-versatile", "groq_api_key")
bam_muc("saving")
_qp1 = ((cfg.read_settings().get("context_runtime") or {}).get("context_sources") or {}
        ).get("quota_profiles") or []
check("bấm mức trên Groq thì khai được hạn mức Groq",
      any(str(x.get("provider")) == "groq" for x in _qp1))
# Đổi sang một model Groq khác: hạn mức mới phải được THÊM, không phải bị bỏ qua.
dat_bo_nao("groq", "qwen3-32b", "groq_api_key")
bam_muc("saving")
_qp2 = ((cfg.read_settings().get("context_runtime") or {}).get("context_sources") or {}
        ).get("quota_profiles") or []
check("CANARY: đổi model thì hạn mức mới được BỔ SUNG, không bị bỏ qua",
      len(_qp2) > len(_qp1))
check("và hạn mức cũ vẫn còn (không xoá của người vận hành)",
      {str(x.get("id")) for x in _qp1} <= {str(x.get("id")) for x in _qp2})
check("bấm lại lần nữa không đẻ bản sao", (bam_muc("saving") or True) and len(
    ((cfg.read_settings().get("context_runtime") or {}).get("context_sources") or {}
     ).get("quota_profiles") or []) == len(_qp2))
# Và sau khi đã có hạn mức của Groq, đổi sang provider khác vẫn phải tiết kiệm được.
dat_bo_nao("openrouter", "openai/gpt-4o-mini", "openrouter_key")
bam_muc("saving")
check("CANARY: đổi hẳn sang bộ não khác vẫn tiết kiệm được",
      quyet_dinh("openrouter", "openai/gpt-4o-mini", "api", "s-doi").action == "use")


# ============================================================
# 3. Lượt đi đường tiết kiệm phải được GHI NHẬN là đường tiết kiệm
# ============================================================
# Trên engine API, các tầng Phase 9/7/6/5 chạy trước và tầng nào không nhận lượt thì ghim
# "legacy". Ai ghim trước thắng, nên Phase 8 nhận lượt rồi mà nhãn vẫn là đường cũ.
_rt = context_runtime.ObserveRuntime(
    Path(tempfile.mkdtemp(prefix="javis-tkct-rt-")), lambda: cfg.read_settings())
_tr = _rt.start_turn("phien-ghim", "brain", "dashboard")
_rt.pin_execution_path(_tr, "legacy", 1, "fast-path-canary-v1", "outside_allocation")
check("tầng không nhận lượt thì ghim đường cũ", _tr.execution_path == "legacy")
_sau = _rt.pin_execution_path(_tr, "sources", None, "adaptive-context-sources-v1", "ctx")
check("CANARY: tầng sau NHẬN lượt thì nhãn phải đổi thành đường tiết kiệm",
      _sau == "sources" and _tr.execution_path == "sources")
# Đường thật không được ghi đè đường thật: nếu không thì nhãn thành cái cuối cùng gọi tới,
# chứ không phải cái đã thật sự chạy.
_rt.pin_execution_path(_tr, "fast", None, "fast-path-canary-v1", "sau")
check("CANARY: đường thật KHÔNG ghi đè đường thật", _tr.execution_path == "sources")
# Và đường cũ không bao giờ ghi đè ngược lại.
_rt.pin_execution_path(_tr, "legacy", None, "write-single-step-v1", "sau")
check("CANARY: đường cũ không ghi đè ngược lại đường thật", _tr.execution_path == "sources")

# Bất biến cũ vẫn phải giữ: CÙNG một tầng ghim lại là do allocation bị sửa giữa lượt, và
# một lượt đang chạy không được đổi đường vì ai đó vừa xoay knob.
_tr2 = _rt.start_turn("phien-knob", "brain", "dashboard")
_rt.pin_execution_path(_tr2, "legacy", 1, "fast-path-canary-v1", "outside_allocation")
_rt.pin_execution_path(_tr2, "fast", 1, "fast-path-canary-v1", "assigned")
check("CANARY: cùng một tầng ghim lại giữa lượt thì KHÔNG đổi đường",
      _tr2.execution_path == "legacy")


# ============================================================
# 4. Mức "Siêu tiết kiệm" không được khoe con số bộ não này không với tới
# ============================================================
# Từ 0.14.0 đường tắt mở cho gói ChatGPT, nên bộ não KHÔNG ăn được mức này giờ chỉ còn gói
# Claude Code - và đó là rào CỨNG trong mã, không phải cấu hình: đường tắt gọi model bằng
# đường cần API key, thứ gói Claude Code không có.
dat_bo_nao("anthropic-cli", "opus", None)
_uoc_sub = asyncio.run(main._uoc_tinh_tiet_kiem("brain"))
_m_sub = _uoc_sub.get("muc") or {}
check("gói Claude Code: Siêu tiết kiệm bị đánh dấu không áp dụng",
      _m_sub.get("max", {}).get("ap_dung") is False)
check("CANARY: và KHÔNG được khoe tốn ít token hơn mức Tối ưu",
      _m_sub["max"]["token_moi_request"] == _m_sub["saving"]["token_moi_request"])
check("có câu nói rõ vì sao", "chưa mở" in (_m_sub["max"].get("ghi_chu") or ""))

# Còn gói ChatGPT thì ăn được. Nhãn này từng gõ cứng kind=="api" nên dán "không áp" lên đúng
# mức vừa được mở cho nó, và chủ repo bấm vào rồi tưởng mình bấm nhầm.
dat_bo_nao("openai-oauth", "gpt-5.6-luna", None)
check("CANARY: gói ChatGPT ĂN được mức Siêu tiết kiệm",
      (asyncio.run(main._uoc_tinh_tiet_kiem("brain"))["muc"]["max"]).get("ap_dung") is True)

dat_bo_nao("groq", "llama-3.3-70b-versatile", "groq_api_key")
_uoc_api = asyncio.run(main._uoc_tinh_tiet_kiem("brain"))
_m_api = _uoc_api.get("muc") or {}
check("bộ não API key: Siêu tiết kiệm áp dụng được",
      _m_api.get("max", {}).get("ap_dung") is True)
check("và thật sự tốn ít token hơn mức Tối ưu",
      _m_api["max"]["token_moi_request"] < _m_api["saving"]["token_moi_request"])

# Giao diện phải VẼ được chuyện đó ra, không thì con số đúng nằm trong JSON mà người dùng
# vẫn đọc nhầm.
_CONSOLE = (ROOT / "dashboard" / "console.js").read_text(encoding="utf-8")
check("trang có vẽ dấu 'không áp cho bộ não đang dùng'",
      "presetKhongAp" in _CONSOLE and "rt-preset-na" in _CONSOLE)
check("CANARY: và THẬT SỰ gọi khi vẽ nút", "${presetKhongAp(p.id)}" in _CONSOLE)
check("có CSS cho dấu đó",
      ".rt-preset-na" in (ROOT / "dashboard" / "console.css").read_text(encoding="utf-8"))


# ============================================================
# 5. Cảnh báo của máy chủ không được nuốt
# ============================================================
# Máy chủ trả `canh_bao` từ 0.13.0, nhưng giao diện chưa bao giờ hiện nó: người dùng chỉ
# thấy một dòng xanh "đã bật, có hiệu lực ngay" kể cả khi máy chủ vừa nói ngược lại.
check("CANARY: giao diện đọc canh_bao từ máy chủ", "body.canh_bao" in _CONSOLE)
_i3 = _CONSOLE.find("body.canh_bao")
check("CANARY: và ghép nó vào đúng thông báo hiện ra",
      "cb" in _CONSOLE[_i3:_i3 + 600] and "_rtToast" in _CONSOLE[_i3:_i3 + 600])

print(("\nFAILED: " + ", ".join(_fails)) if _fails else "\nAll passed")
sys.exit(1 if _fails else 0)
