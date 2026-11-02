"""Javis Gate (0.440.0): AI bên ngoài đọc và nhắn vào hội thoại của Javis như chủ gõ tay.

    python tests/run.py javis_gate_chat -v      (KHÔNG mạng)

Người dùng báo 02/11: ChatGPT giao việc cho Javis qua Kanban nên không ai biết việc chạy tới đâu, và Javis không học
được gì vì trao đổi không đi qua khung chat. File này chạy THẬT vòng chat web (`main._chat_socket`) với engine API giả
(HTTP của nhà cung cấp giả lập), và khoá:

1. Tin gửi qua Gate chạy thành một lượt chat bình thường: lưu tin chủ (kèm khối nguồn), lưu câu trả lời, ghi nhật ký
   hội thoại (thứ vòng tự học đọc), báo `external_message` cho tab đang mở.
2. Phiên đang trả lời thì tin thành tin GÕ THÊM, không bị từ chối, và vẫn được trả lời.
3. Không đọc, không gửi vào hội thoại của khách (bot) hay phiên nhóm.
4. Bốn tool chỉ có ở cửa Gate; tool GỬI chỉ ở mức Toàn quyền.
5. Khối nguồn không lọt ra tên hội thoại, trang chia sẻ, bong bóng.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import json
import os
os.environ["JAVIS_API_STREAM_TOOLS"] = "0"
import tempfile
from pathlib import Path

_STATE = tempfile.mkdtemp(prefix="javis-gate-chat-")
os.environ["JAVIS_STATE_DIR"] = _STATE

import main  # noqa: E402
import engine  # noqa: E402
import chat_bridge as CB  # noqa: E402
import mcp_hub  # noqa: E402
import sessions  # noqa: E402
import share_render  # noqa: E402
from chat_runtime import ChatRuntime  # noqa: E402

_fails = []


def check(name, cond, info=None):
    print(("ok   " if cond else "FAIL ") + name + ("" if cond or info is None else f"  ({info})"))
    if not cond:
        _fails.append(name)


class _Resp:
    def __init__(self, data):
        self.status_code, self._data, self.text, self.headers = 200, data, json.dumps(data), {}

    def json(self):
        return self._data


CHAM = {"s": 0.02}


class _FakeClient:
    """Như OpenRouter: trả lời bằng chữ, nhắc lại câu cuối của chủ để test biết lượt nào trả lời tin nào."""

    def __init__(self, *a, **kw):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def post(self, url, headers=None, json=None):
        msgs = (json or {}).get("messages") or []
        cuoi = next((m.get("content") for m in reversed(msgs) if m.get("role") == "user"), "")
        await asyncio.sleep(CHAM["s"])
        dong = str(cuoi or "").strip().splitlines()[-1] if str(cuoi or "").strip() else ""
        return _Resp({"choices": [{"message": {"content": "ĐÃ LÀM: " + dong[:120]}}],
                      "usage": {"prompt_tokens": 1, "completion_tokens": 1}})


RUNTIME = ChatRuntime()
main._CHAT_RUNTIME = RUNTIME
main.cfgmod.gate_active = lambda: False
main._chat_provider = lambda _cfg: ("openrouter", "api", "test-key", "test-model")
main._reasoning_level = lambda _cfg: "off"
NHAT_KY = []
main.log_conversation = lambda brain, u, j: NHAT_KY.append((u, j))
main.usage_store.record = lambda *a, **k: None
engine.httpx.AsyncClient = _FakeClient


async def _none(*a, **k):
    return None


async def _false(*a, **k):
    return False
main._schedule_cancel_action = _none
main.compaction.maybe_compact = _false
main.learn_feature.enqueue = _none

BRAIN = main._brain_key(str(Path(tempfile.mkdtemp(prefix="brain-gate-")).resolve()))
ss = main.get_store()
WEB = ss.create_session(brain=BRAIN, engine="test", model="test", title="Viết Web bán nước mắm")
ss.append_message(WEB, "user", "Làm trang web bán nước mắm giúp anh")
ss.append_message(WEB, "assistant", "Em đã dựng xong bản nháp trang chủ.")
BOT = ss.create_session(brain=BRAIN, engine="test", model="test", title="Viết web khách hỏi", channel="bot:shop")
ss.append_message(BOT, "user", "khách hỏi giá web")
DOI_TAC = ss.create_session(brain=BRAIN, engine="test", model="test", title="Cộng sự viết bài", channel="agent:viet-bai")

SU_KIEN = []


async def _nghe(ev):
    SU_KIEN.append(ev)
RUNTIME.add_client("test-tab", _nghe)


def chay(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


asyncio.set_event_loop(asyncio.new_event_loop())

# ============================================================
# 1. Tìm và đọc
# ============================================================
kq = CB.tim("viet web")
ids = [r["id"] for r in kq["results"]]
check("tìm theo tên, không phân biệt dấu: 'viet web' ra 'Viết Web bán nước mắm'", WEB in ids, kq)
check("hội thoại của khách (bot) không bao giờ hiện ra", BOT not in ids, ids)
check("tìm theo nội dung tin cũng ra", WEB in [r["id"] for r in CB.tim("nước mắm")["results"]])
check("không từ khoá thì trả hội thoại mới nhất", WEB in [r["id"] for r in CB.tim("")["results"]])
d = CB.doc(WEB, 10)
check("đọc hội thoại trả tin cũ trước, đủ vai", d["ok"] and [m["role"] for m in d["messages"]] == ["user", "assistant"], d)
check("đọc hội thoại của khách bị từ chối", not CB.doc(BOT)["ok"])

# ============================================================
# 2. Gửi: chạy thành một lượt chat thật
# ============================================================
SU_KIEN.clear()
r = chay(CB.gui(WEB, "Anh đã duyệt màu cam. Làm tiếp trang giỏ hàng.", "ChatGPT"))
check("gửi vào khung Trò chuyện: lượt bắt đầu", r.get("ok") and r.get("mode") == "started", r)
kq = chay(CB.ket_qua(WEB, r["after_id"], 10))
check("đọc kết quả: Javis trả lời đúng tin vừa gửi", kq.get("status") == "done"
      and "trang giỏ hàng" in kq.get("answer", ""), kq)
tin = ss.get_messages(WEB)
chu = [m for m in tin if m["role"] == "user"][-1]["content"]
check("tin lưu kèm khối nguồn ở đầu", chu.startswith(CB.KHOI_GATE) and "ChatGPT" in chu, chu[:120])
check("nguon_cua đọc lại đúng tên", CB.nguon_cua(chu) == "ChatGPT")
check("câu trả lời lưu vào kho phiên", tin[-1]["role"] == "assistant" and "ĐÃ LÀM" in tin[-1]["content"])
check("lượt ghi nhật ký hội thoại (đầu vào của vòng tự học)",
      any("trang giỏ hàng" in u for u, _ in NHAT_KY), NHAT_KY[-1:] if NHAT_KY else None)
ext = [e for e in SU_KIEN if e.get("type") == "external_message"]
check("tab đang mở nhận external_message kèm nguồn, trước khi chữ trả lời chạy",
      ext and ext[0]["session_id"] == WEB and ext[0]["source"] == "ChatGPT"
      and SU_KIEN.index(ext[0]) < next((i for i, e in enumerate(SU_KIEN) if e.get("type") in ("stream", "response")),
                                       len(SU_KIEN)), [e.get("type") for e in SU_KIEN][:8])
check("lượt phát sự kiện lượt chat cho tab đang xem (chữ chạy, turn_done)",
      any(e.get("type") == "turn_done" and e.get("session_id") == WEB for e in SU_KIEN),
      sorted({e.get("type") for e in SU_KIEN}))
d = CB.doc(WEB, 4)
check("đọc lại: tin qua Gate có 'via' và chữ đã gỡ khối",
      any(m.get("via") == "ChatGPT" and not m["text"].startswith("[") for m in d["messages"]), d["messages"])

# ============================================================
# 3. Phiên đang bận: tin thành tin gõ thêm
# ============================================================
CHAM["s"] = 0.6


async def _hai_tin():
    r1 = await CB.gui(WEB, "Việc A: viết mô tả sản phẩm.", "Claude")
    await asyncio.sleep(0.1)
    r2 = await CB.gui(WEB, "Việc B: thêm nút đặt hàng.", "Claude")
    kq = await CB.ket_qua(WEB, r1["after_id"], 20)
    return r1, r2, kq
r1, r2, kq = chay(_hai_tin())
check("tin thứ hai lúc đang trả lời: nhận, thành tin gõ thêm", r1.get("mode") == "started" and r2.get("ok")
      and r2.get("mode") == "queued", (r1, r2))
check("chờ qua cả lượt gõ thêm: cả hai việc đều có trả lời", kq.get("status") == "done"
      and "Việc B" in kq.get("answer", ""), kq)
CHAM["s"] = 0.02

# ============================================================
# 4. Ranh giới kênh và nội dung
# ============================================================
check("không gửi vào hội thoại của khách", not chay(CB.gui(BOT, "xin chào", "ChatGPT"))["ok"])
check("không gửi vào hội thoại không tồn tại", not chay(CB.gui("khong-co", "x", "ChatGPT"))["ok"])
check("không gửi tin rỗng", not chay(CB.gui(WEB, "   ", "ChatGPT"))["ok"])
check("không gửi tin quá dài", not chay(CB.gui(WEB, "a" * (CB.MAX_TIN + 1), "ChatGPT"))["ok"])
check("chat với Cộng sự thì gửi được", CB.gui_duoc("agent:viet-bai") and CB.gui_duoc("web"))
check("phiên nhóm và quy trình thì không", not CB.gui_duoc("team:x") and not CB.gui_duoc("workflow:x")
      and not CB.gui_duoc("telegram"))
check("tên nguồn bị làm sạch: không phá được khối", CB.ten_nguon("Evil] [x.\nhack") == "Evil x hack")
check("tên nguồn trống thì là 'AI'", CB.ten_nguon("") == "AI")

# ============================================================
# 5. Cửa Gate của hub
# ============================================================
GATE = {"source": "ChatGPT"}


def ten_tool(mode, gate):
    res = chay(mcp_hub._handle_one({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}, mode, gate=gate))
    return [t["name"] for t in res["result"]["tools"]]


full = ten_tool("full", GATE)
check("Toàn quyền: đủ bốn tool chat", all(t in full for t in CB.TOOLS), [t for t in full if "chat" in t])
sug = ten_tool("suggest", GATE)
check("Chỉ đọc: không có tool gửi, vẫn tìm và đọc được",
      "javis_chat_send" not in sug and "javis_chat_find" in sug and "javis_chat_read" in sug)
khong = ten_tool("full", None)
check("không qua cửa Gate (engine của chính Javis): không có tool chat nào",
      not any(t in khong for t in CB.TOOLS))


def goi(name, args, mode="full", gate=GATE):
    res = chay(mcp_hub._handle_one({"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                                    "params": {"name": name, "arguments": args}}, mode, gate=gate))
    return res["result"]["content"][0]["text"], res["result"]["isError"]


txt, loi = goi("javis_chat_send", {"id": WEB, "message": "thử"}, mode="suggest")
check("gọi tool gửi ở mức Chỉ đọc: báo lỗi rõ, không gửi", loi and "Full access" in txt, txt)
txt, loi = goi("javis_chat_find", {"query": "viet web"})
check("tool tìm qua hub trả JSON có hội thoại", not loi and WEB in txt, txt[:200])
txt, loi = goi("javis_chat_send", {"id": WEB, "message": "Gửi qua hub nhé.", "wait_seconds": 10})
kq = json.loads(txt) if not loi else {}
check("tool gửi qua hub: chờ luôn câu trả lời trong cùng một lần gọi",
      kq.get("ok") and (kq.get("result") or {}).get("status") == "done"
      and "Gửi qua hub" in (kq.get("result") or {}).get("answer", ""), txt[:300])
check("nguồn lấy từ cửa Gate", CB.nguon_cua([m for m in ss.get_messages(WEB) if m["role"] == "user"][-1]["content"])
      == "ChatGPT")
txt, loi = goi("javis_chat_result", {"id": WEB, "after_id": kq.get("after_id", 0), "wait_seconds": 0})
check("tool đọc kết quả gọi lại được", not loi and '"done"' in txt, txt[:200])

# ============================================================
# 6. Khối nguồn không lọt ra chỗ người đọc
# ============================================================
tho = CB.khoi("ChatGPT") + "làm tiếp trang giỏ hàng"
check("tên hội thoại bỏ khối Gate", sessions.title_from_message(tho) == "làm tiếp trang giỏ hàng",
      sessions.title_from_message(tho))
check("trang chia sẻ bỏ khối Gate", share_render.chu_nguoi_go(tho) == "làm tiếp trang giỏ hàng")
app = (ROOT / "dashboard" / "app.js").read_text(encoding="utf-8")
check("dashboard gỡ khối Gate như các khối ngữ cảnh khác", '"[GỬI QUA JAVIS GATE:"' in app)
check("dashboard vẽ bong bóng khi nhận external_message", 'data.type === "external_message"' in app)
check("bong bóng tin cũ đọc nhãn nguồn từ chữ gốc", "appendUserMessage(m.content || \"\", _atts, ts)" in app)
for f in ("vi", "en"):
    d = json.loads((ROOT / "dashboard" / "i18n" / f"{f}.json").read_text(encoding="utf-8"))
    check(f"i18n {f}: có chat.via_gate với {{src}}", "{src}" in d.get("chat.via_gate", ""))

print()
print("ALL PASS" if not _fails else f"{len(_fails)} FAIL: {_fails}")
raise SystemExit(1 if _fails else 0)
