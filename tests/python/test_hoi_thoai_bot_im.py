"""Dòng "Bot im: lý do" của Hộp thư (0.65.4): GET /conversations/{id}/messages trả `bot_silence` và `bot_name`.

    python tests/run.py hoi_thoai_bot_im      (KHÔNG mạng)

Chủ dự án hay hỏi "sao bot im ở tin này". Dữ liệu vốn đã có ở nhật ký bộ phán xử, nhưng phải mở menu mới thấy. Test này canh
ĐIỀU KIỆN để dòng đó hiện, vì hiện sai chỗ còn tệ hơn không hiện:
  - chỉ khi cuộc chat ở chế độ AI, tin cuối là của khách, và quyết định gần nhất là `silent` cho đúng tin đó;
  - không hiện khi bot đã đáp, người thật đang tiếp quản, quyết định là của tin cũ hơn, hay quyết định là `reply`;
  - kho bộ phán xử chưa có thì không hiện và KHÔNG tạo file; lỗi kho không làm hỏng việc đọc hội thoại.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import os
import sys
import tempfile
import time

_STATE = tempfile.mkdtemp(prefix="javis-htim-")
os.environ["JAVIS_STATE_DIR"] = _STATE
os.environ["JAVIS_ALLOWED_HOSTS"] = "testserver"
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import chatbot_reply_policy_store as rps  # noqa: E402
import chatbot_store  # noqa: E402
import conversations  # noqa: E402

_fails = []


def check(name, cond, them=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(them) + "]") if them and not cond else ""))
    if not cond:
        _fails.append(name)


bot, _ = chatbot_store.create_bot({"name": "Nhi Mai", "agent_slug": "a", "brain": "brain"})
NOW = time.time()


def tin(chat, gui, text, bot_id=None, dt=0):
    r = conversations.ghi_su_kien({
        "channel": "zalo_personal", "account_id": "zp1", "bot_id": bot if bot_id is None else bot_id,
        "external_chat_id": chat, "chat_type": "group", "chat_title": "Nhóm " + chat,
        "sender_type": gui, "sender_id": "u" + chat if gui == "customer" else "", "sender_name": "Lan", "text": text,
        "created_at": NOW - dt})
    return r["conversation_id"]


def quyet(chat, verdict="silent", code="below_threshold", dt=0, **kw):
    return rps.log_decision({"bot_id": bot, "chat_id": chat, "ts": NOW - dt, "text": "x", "verdict": verdict,
                             "candidate": True, "silence_code": code, "mode": "on", "score": 0.52, "threshold": 0.6, **kw}, NOW - dt)


from fastapi.testclient import TestClient  # noqa: E402
import main  # noqa: E402

cl = TestClient(main.app)


def doc(cid):
    return cl.get(f"/conversations/{cid}/messages").json()


c_chua = tin("g0", "customer", "hỏi giá")
check("kho bộ phán xử chưa có: không có dòng bot im và KHÔNG tạo file", doc(c_chua)["bot_silence"] is None and not rps.db_path().exists())
check("nhưng vẫn trả tên bot", doc(c_chua)["conversation"]["bot_name"] == "Nhi Mai")

c1 = tin("g1", "customer", "gói tháng bao nhiêu")
quyet("g1", dt=-1)
s = doc(c1)["bot_silence"]
check("tin khách cuối + quyết định im cho đúng tin đó: có dòng bot im, kèm mã, điểm và ngưỡng",
      s and s["code"] == "below_threshold" and abs(s["score"] - 0.52) < 1e-9 and abs(s["threshold"] - 0.6) < 1e-9, s)

c2 = tin("g2", "customer", "chào")
quyet("g2", dt=-1)
tin("g2", "ai", "dạ chào chị")
check("bot đã đáp (tin cuối là của bot): không có dòng bot im", doc(c2)["bot_silence"] is None)

c3 = tin("g3", "customer", "ai biết đặt lịch")
quyet("g3", dt=-1)
conversations.dat_che_do(c3, "human")
check("người thật đang tiếp quản: không có dòng bot im (im là hiển nhiên)", doc(c3)["bot_silence"] is None)

c4 = tin("g4", "customer", "tin mới hơn quyết định", dt=0)
quyet("g4", dt=300)
check("quyết định cũ hơn tin cuối hơn 60 giây (thuộc tin trước): không hiện", doc(c4)["bot_silence"] is None)

c5 = tin("g5", "customer", "được gọi tên")
quyet("g5", verdict="reply", code="", dt=-1)
check("quyết định là reply: không hiện", doc(c5)["bot_silence"] is None)

c6 = tin("g6", "customer", "không bot trực", bot_id="")
check("cuộc chat không có bot: không hiện", doc(c6)["bot_silence"] is None and doc(c6)["conversation"]["bot_name"] == "")

c7 = tin("g7", "customer", "chuyện phiếm")
quyet("g7", code="no_signal", dt=-1, score=None, threshold=None)
s7 = doc(c7)["bot_silence"]
check("im vì luật cứng (no_signal, không có điểm): vẫn hiện, điểm là null", s7 and s7["code"] == "no_signal" and s7["score"] is None, s7)

c8 = tin("g8", "customer", "cuộc chat khác không bị lẫn")
check("quyết định của cuộc chat khác không lẫn sang", doc(c8)["bot_silence"] is None)

# lỗi kho không làm hỏng việc đọc hội thoại
orig = rps.last_decision
rps.last_decision = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("kho hỏng"))
d = doc(c1)
rps.last_decision = orig
check("kho lỗi: hội thoại vẫn đọc được, chỉ mất dòng bot im", d["ok"] and d["bot_silence"] is None and len(d["messages"]) == 1)

# giao diện dùng đúng khoá
js = (ROOT / "dashboard" / "conversations.js").read_text(encoding="utf-8")
check("giao diện đọc bot_silence từ server và vẽ dưới tin cuối", "d.bot_silence" in js and "veBotIm(c)" in js)

print()
if _fails:
    print(f"{len(_fails)} FAIL")
    sys.exit(1)
print("ALL PASS")
