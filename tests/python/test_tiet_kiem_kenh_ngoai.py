"""Hệ Tiết kiệm phải chạy trên MỌI kênh, không riêng dashboard.

    python tests/run.py tiet_kiem_kenh_ngoai      (KHÔNG mạng)

Lỗ hổng chủ repo chỉ ra (2026-08-05): "Toàn bộ hệ thống Tiết kiệm hiện chỉ được nối vào ĐÚNG
một chỗ: handler WebSocket của trang dashboard."

Đúng. Mọi lệnh gọi `prepare(...)` trong `websocket_endpoint` đều truyền cứng chữ "dashboard",
`_tg_answer_engine` không có một dòng nào chạm tới chúng, và `channels` trong config cũng chỉ
khai `["dashboard"]`. Ba thứ khớp nhau hoàn toàn - nên người dùng bấm mức Siêu tiết kiệm, trang
Cài đặt báo xanh "đã bật, có hiệu lực ngay", rồi mỗi lượt Telegram vẫn gửi nguyên CLAUDE.md +
MEMORY.md.

Đây là kiểu hỏng tệ nhất trong nhóm này: **không lỗi, không cảnh báo, chỉ có hoá đơn token
không giảm** - và giảm token lại đúng là thứ duy nhất tính năng đó hứa. Cùng họ với con bệnh
`provider_kinds` hồi 0.12.4 (xem `config._no_rong_pham_vi_bo_nao`), lần này rơi vào KÊNH thay
vì rơi vào loại bộ não.

File này canh ba tầng, và tầng cuối là tầng thật:
  1. Config có khai kênh không.
  2. Máy ĐÃ CÀI có được nới không (settings.json cũ ghim cứng ["dashboard"]).
  3. Chạy THẬT một lượt Telegram, xem nó có đi đường tắt và có dùng prompt gọn không.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401  - nạp server/ vào sys.path
import asyncio
import json
import os
import sys
import tempfile

_STATE = tempfile.mkdtemp(prefix="javis-tkkn-")
os.environ["JAVIS_STATE_DIR"] = _STATE
os.environ["BRAINS_DIR"] = tempfile.mkdtemp(prefix="javis-tkkn-brains-")

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import config as cfgmod  # noqa: E402
import fast_path_runtime  # noqa: E402
import adaptive_context_runtime  # noqa: E402
import main  # noqa: E402

_fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)


# ============================================================
# 1. Config khai kênh nào
# ============================================================
_D = cfgmod._DEFAULT["context_runtime"]
for ten, nhan in (("canary", "đường tắt (Siêu tiết kiệm)"),
                  ("memory_canary", "bộ nhớ chọn lọc"),
                  ("lazy_skill_canary", "skill nạp khi cần")):
    ch = _D[ten].get("channels") or []
    check(f"{nhan}: mở cho telegram", "telegram" in ch)
    check(f"{nhan}: vẫn giữ dashboard", "dashboard" in ch)

# conversation_state CỐ Ý không mở: phiên Telegram đã giữ mạch hội thoại riêng (sess["or"] cho
# engine API, session/thread cho hai gói thuê bao). Đưa thêm transcript vào system prompt là
# gửi lịch sử HAI LẦN - vừa tốn token vừa dễ làm model lẫn thứ tự.
check("trạng thái hội thoại KHÔNG mở cho telegram (tránh gửi lịch sử hai lần)",
      "telegram" not in (_D["conversation_state_canary"].get("channels") or []))


# ============================================================
# 2. Máy ĐÃ CÀI cũng phải được nới
# ============================================================
# Đây là nửa dễ quên nhất. `write_settings` ghi lại TOÀN BỘ config đã trộn, nên giá trị mặc
# định của ngày cài bị đóng băng vào settings.json; `read_settings` lại trộn file ĐÈ LÊN mặc
# định. Sửa mặc định mà quên nới thì bản vá này chỉ tới được máy cài mới tinh, còn máy đang
# chạy thật thì không bao giờ thấy - đúng cách con bệnh 0.12.4 đã diễn ra.
_cu = {"context_runtime": {
    "canary": {"channels": ["dashboard"], "provider_kinds": ["api"]},
    "memory_canary": {"channels": ["dashboard"], "provider_kinds": ["api"]},
    "lazy_skill_canary": {"channels": ["dashboard"], "provider_kinds": ["api"]},
}}
check("hàm nới báo có sửa", cfgmod._no_rong_pham_vi_bo_nao(_cu) is True)
for ten in ("canary", "memory_canary", "lazy_skill_canary"):
    check(f"settings.json cũ được nới thêm telegram - {ten}",
          "telegram" in _cu["context_runtime"][ten]["channels"])
check("nới KHÔNG xoá kênh người dùng đang có",
      "dashboard" in _cu["context_runtime"]["canary"]["channels"])


# ============================================================
# 3. Chạy THẬT một lượt Telegram
# ============================================================
# Hai mục trên chỉ chứng minh cấu hình đúng. Cấu hình đúng mà không ai gọi prepare() thì vẫn
# hỏng y như cũ - đó CHÍNH LÀ lỗi đang sửa. Nên mục này chạy lượt thật và xem nó đi đường nào.
_goi = {"fast_prepare": [], "p8_prepare": [], "stream": [], "stream_mcp": []}


class _FastGia:
    def __init__(self, action):
        self.action = action

    def prepare(self, trace, objective, brain, channel, provider, model, kind, co_dinh_kem):
        _goi["fast_prepare"].append({"channel": channel, "objective": objective})
        if self.action != "execute":
            return fast_path_runtime.FastPathPlan("legacy", "test", "legacy")
        return fast_path_runtime.FastPathPlan(
            "execute", "test", "fast",
            messages=({"role": "system", "content": "CAPSULE NHỎ"},
                      {"role": "user", "content": objective}),
            reservation_id="r1", capsule_hash="h1")


class _P8Gia:
    def __init__(self, action, prompt=""):
        self.action, self.prompt = action, prompt

    def prepare(self, trace, objective, brain, session_id, messages, channel,
                provider, model, kind, base_builder):
        _goi["p8_prepare"].append({"channel": channel, "messages": list(messages)})
        return adaptive_context_runtime.AdaptiveContextPlan(
            self.action, "test", system_prompt=self.prompt)


def _stream_gia(prov, key, model, messages, reasoning="off"):
    _goi["stream"].append([dict(m) for m in messages])

    async def g():
        yield {"type": "text", "content": "4 ạ."}
        yield {"type": "usage", "input": 12, "output": 3}
    return g()


async def _stream_mcp_gia(prov, key, model, messages, reasoning="off", brain=None,
                          force_lazy=False, mode="full"):
    _goi["stream_mcp"].append([dict(m) for m in messages])

    async def g():
        yield {"type": "text", "content": "Đường đầy đủ."}
        yield {"type": "usage", "input": 900, "output": 5}
    return g()


main._api_stream = _stream_gia
main._api_stream_mcp = _stream_mcp_gia
main._QUALITY_GATE.evaluate = lambda *a, **k: type(
    "D", (), {"status": "ok", "trace_report": lambda self=None: {}})()


def chay(sess=None, hoi="2+2 bằng mấy"):
    return asyncio.run(main._tg_answer_engine(
        hoi, {"chat_id": "1", "chat_type": "private"}, None,
        chat_id="1", sess=sess if sess is not None else {"last": None, "sent": set(), "or": None},
        brain="brain", mcfg={}, prov="openrouter", kind="api", api_key="k", api_model="m"))


# --- 3a. Đường tắt NHẬN lượt -> chỉ một vòng gọi model, không đụng tool ---
_goi["fast_prepare"].clear(); _goi["stream"].clear(); _goi["stream_mcp"].clear()
main._FAST_PATH = _FastGia("execute")
main._ADAPTIVE_CONTEXT = _P8Gia("legacy")
ra = chay()

check("CANARY: lượt Telegram CÓ hỏi đường tắt", len(_goi["fast_prepare"]) == 1)
check("CANARY: hỏi với kênh 'telegram', không phải 'dashboard'",
      _goi["fast_prepare"] and _goi["fast_prepare"][0]["channel"] == "telegram")
check("đi đường tắt thì trả lời luôn", isinstance(ra, dict) and "4 ạ." in ra["text"])
check("đường tắt chạy ĐÚNG một vòng gọi model", len(_goi["stream"]) == 1)
check("đường tắt dùng capsule nhỏ, không phải CLAUDE.md",
      _goi["stream"] and _goi["stream"][0][0]["content"] == "CAPSULE NHỎ")
check("CANARY: đi tắt thì KHÔNG chạm engine đầy đủ", _goi["stream_mcp"] == [])


# --- 3b. Đường tắt TỪ CHỐI -> lui về engine đầy đủ, không mất câu trả lời ---
_goi["fast_prepare"].clear(); _goi["stream"].clear(); _goi["stream_mcp"].clear()
main._FAST_PATH = _FastGia("legacy")
ra = chay()
check("đường tắt không nhận -> vẫn có câu trả lời",
      isinstance(ra, dict) and "Đường đầy đủ." in ra["text"])
check("lúc đó mới dùng engine đầy đủ", len(_goi["stream_mcp"]) == 1)


# --- 3c. Phase 8 thay prompt đầy đủ bằng nguồn chọn lọc ---
_goi["p8_prepare"].clear(); _goi["stream_mcp"].clear()
main._FAST_PATH = _FastGia("legacy")
main._ADAPTIVE_CONTEXT = _P8Gia("use", "PROMPT GỌN CỦA PHASE 8")
chay(sess={"last": None, "sent": set(), "or": None})

check("CANARY: lượt Telegram CÓ hỏi Phase 8", len(_goi["p8_prepare"]) == 1)
check("Phase 8 cũng nhận kênh 'telegram'",
      _goi["p8_prepare"] and _goi["p8_prepare"][0]["channel"] == "telegram")
check("prompt gọn được dùng thật",
      _goi["stream_mcp"] and "PROMPT GỌN CỦA PHASE 8" in _goi["stream_mcp"][0][0]["content"])
check("CANARY: KHÔNG còn gửi kèm CLAUDE.md",
      _goi["stream_mcp"] and "Nguyên tắc phản hồi" not in _goi["stream_mcp"][0][0]["content"])
# Không truyền transcript xuống Phase 8: phiên Telegram đã giữ mạch riêng.
check("không đẩy lịch sử sang Phase 8 (tránh gửi hai lần)",
      _goi["p8_prepare"] and _goi["p8_prepare"][0]["messages"] == [])


# --- 3d. Phase 8 từ chối -> vẫn chạy, không chặn lượt ---
_goi["stream_mcp"].clear()
main._ADAPTIVE_CONTEXT = _P8Gia("legacy")
ra = chay()
check("Phase 8 không nhận -> lượt vẫn chạy bằng prompt đầy đủ",
      isinstance(ra, dict) and "Đường đầy đủ." in ra["text"])


# --- 3e. Lệnh lịch KHÔNG bị đường tắt cướp lượt ---
_goi["fast_prepare"].clear()
main._FAST_PATH = _FastGia("execute")
_that = main._schedule_cancel_action


async def _lich_gia(text, brain):
    # Đúng hình dạng _schedule_cancel_reply đọc: handled + result, không phải "reply".
    return {"calls": ["javis_schedule:huy"], "handled": True, "result": "Đã huỷ lịch."}


main._schedule_cancel_action = _lich_gia
ra = chay(hoi="huỷ lịch nhắc sáng mai")
check("CANARY: câu điều khiển lịch do gateway lịch trả lời, không phải đường tắt",
      isinstance(ra, dict) and "huỷ" in ra["text"].lower())
check("và đường tắt KHÔNG được hỏi tới cho lượt đó", _goi["fast_prepare"] == [])
main._schedule_cancel_action = _that


# ============================================================
# 4. Mã nguồn: không còn chỗ nào ghim cứng "dashboard" cho kênh khác
# ============================================================
_SRC = (SERVER / "main.py").read_text(encoding="utf-8")
_than = _SRC[_SRC.index("async def _tg_answer_engine"):]
check("lượt kênh ngoài truyền BIẾN channel xuống đường tắt",
      "_FAST_PATH.prepare, runtime_trace, text, _brain_root(brain), channel, prov" in _than)
check("lượt kênh ngoài truyền BIẾN channel xuống Phase 8",
      "str(conv_sid or chat_id), [], channel, prov" in _than)
# Lõi đường tắt phải TÁCH khỏi WebSocket, không thì kênh khác không dùng lại được.
check("lõi đường tắt không dính ws", "async def _fast_path_core(" in _SRC
      and "ws" not in _SRC[_SRC.index("async def _fast_path_core("):
                           _SRC.index("async def _execute_fast_path(")].replace("gui_stream", ""))

print()
if _fails:
    print(f"ĐỎ {len(_fails)} mục: " + ", ".join(_fails))
    sys.exit(1)
print("Tất cả xanh.")
