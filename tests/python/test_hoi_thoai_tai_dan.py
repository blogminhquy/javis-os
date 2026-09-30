"""Hòm thư tải dần (0.65.11): tin nhắn theo con trỏ trước/sau và danh sách theo trang.

    python tests/run.py hoi_thoai_tai_dan      (KHÔNG mạng)

Chủ dự án (30/09/2026): khung tin tải 200 tin mỗi 5 giây rồi vẽ lại toàn bộ khiến máy nặng, và danh sách chỉ lấy đúng 60 dòng. Phía server cần:
  1. `GET /conversations/{id}/messages?limit=N` lấy N tin MỚI NHẤT, cũ trước mới sau, kèm `has_more` (còn tin cũ hơn không).
  2. `?before=<id>` lấy các tin cũ hơn id đó, liền mạch với trang trước (không sót, không trùng) cho tới khi `has_more` hết.
  3. `?after=<id>` chỉ lấy tin MỚI hơn id đó (nhịp 5 giây), rỗng thì vẫn trả đủ `conversation` và `bot_silence`.
  4. Trang thứ hai của danh sách (`offset > 0`) chỉ trả các dòng, không tính lại số đếm và bộ lọc.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import os
import sys
import tempfile
import time

_STATE = tempfile.mkdtemp(prefix="javis-taidan-")
os.environ["JAVIS_STATE_DIR"] = _STATE
os.environ["JAVIS_ALLOWED_HOSTS"] = "testserver"
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import conversations  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
import main  # noqa: E402

fails = []


def check(name, cond, them=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(them) + "]") if them and not cond else ""))
    if not cond:
        fails.append(name)


NOW = time.time()


def ghi(chat, i, khach=True, typ="group"):
    r = conversations.ghi_su_kien({
        "channel": "zalo_personal", "account_id": "zp1", "account_name": "Nick", "bot_id": "",
        "external_chat_id": chat, "chat_type": typ, "chat_title": "Nhóm " + chat if typ == "group" else "",
        "sender_type": "customer" if khach else "ai", "sender_id": "u1" if khach else "", "sender_name": "Lan" if khach else "Bot",
        "text": f"tin {i}", "external_message_id": f"{chat}-{i}", "created_at": NOW - 1000 + i})
    return r["conversation_id"]


CID = 0
for i in range(1, 101):
    CID = ghi("dai", i)
for k in range(1, 8):
    ghi(f"c{k}", 1, typ="private")

cl = TestClient(main.app)


def tin(**qs):
    d = cl.get(f"/conversations/{CID}/messages", params=qs).json()
    return d, [m["text"] for m in d["messages"]], [m["id"] for m in d["messages"]]


# ---------------------------------------------------------------- 1. trang mới nhất
d, text, ids = tin(limit=40)
check("mặc định lấy tin MỚI NHẤT, cũ trước mới sau", text[0] == "tin 61" and text[-1] == "tin 100" and ids == sorted(ids), (text[0], text[-1]))
check("has_more: còn tin cũ hơn", d["has_more"] is True)
check("vẫn trả conversation, bot_silence và bot_running như cũ", "conversation" in d and "bot_silence" in d and "bot_running" in d)

# ---------------------------------------------------------------- 2. kéo lùi, liền mạch
tat_ca = list(text)
truoc = ids[0]
vong = 0
while True:
    d, t2, i2 = tin(limit=40, before=truoc)
    vong += 1
    if not t2:
        break
    check(f"trang cũ {vong}: toàn tin CŨ hơn con trỏ", all(x < truoc for x in i2))
    tat_ca = t2 + tat_ca
    truoc = i2[0]
    if not d["has_more"]:
        break
check("kéo lùi qua 3 trang thì đủ 100 tin, không sót không trùng, đúng thứ tự",
      tat_ca == [f"tin {i}" for i in range(1, 101)], (len(tat_ca), tat_ca[:3]))
check("trang cuối cùng báo hết tin cũ (has_more sai) và không lặp vô hạn", d["has_more"] is False and vong == 2, vong)
d, t3, _ = tin(limit=40, before=1)
check("con trỏ trước tin đầu tiên thì rỗng và has_more sai", t3 == [] and d["has_more"] is False)

# ---------------------------------------------------------------- 3. nhịp chỉ hỏi tin mới
_, _, ids_moi_nhat = tin(limit=40)
cuoi = ids_moi_nhat[-1]
d, t4, _ = tin(after=cuoi, limit=200)
check("CANARY: không có tin mới thì `after` trả rỗng nhưng VẪN đủ conversation (khung còn cập nhật chế độ, lý do bot im)",
      t4 == [] and d["conversation"]["id"] == CID and "bot_silence" in d and "bot_running" in d)
ghi("dai", 101)
ghi("dai", 102, khach=False)
d, t5, i5 = tin(after=cuoi, limit=200)
check("`after` chỉ trả các tin MỚI hơn con trỏ, cũ trước mới sau", t5 == ["tin 101", "tin 102"] and i5 == sorted(i5) and all(x > cuoi for x in i5), t5)
check("`after` không mang has_more (đây không phải trang lùi)", d["has_more"] is False)
d, t6, _ = tin(after=i5[-1], limit=200)
check("đã theo kịp thì lại rỗng", t6 == [])
d, t7, _ = tin(after=cuoi, limit=1)
check("`after` tôn trọng limit và trả tin ngay SAU con trỏ trước", t7 == ["tin 101"], t7)

# ---------------------------------------------------------------- 4. danh sách theo trang
p1 = cl.get("/conversations", params={"limit": 3}).json()
check("trang đầu có đủ số đếm, bộ lọc, danh sách bot", set(("items", "stats", "facets", "bots", "channels")) <= set(p1), sorted(p1))
p2 = cl.get("/conversations", params={"limit": 3, "offset": 3}).json()
check("CANARY: trang thứ hai (offset > 0) chỉ trả các dòng, không tính lại số đếm", set(p2) == {"ok", "items"}, sorted(p2))
check("các dòng của trang hai vẫn đủ trường để vẽ (tên bot, cần trả lời)", all("bot_name" in x and "need_reply" in x for x in p2["items"]))
tat = cl.get("/conversations", params={"limit": 50}).json()["items"]
ghep = p1["items"] + p2["items"] + cl.get("/conversations", params={"limit": 3, "offset": 6}).json()["items"]
check("ghép các trang lại thì đúng danh sách đầy đủ, không sót không trùng", [x["id"] for x in ghep] == [x["id"] for x in tat][:len(ghep)] and len(tat) == 8,
      ([x["id"] for x in ghep], [x["id"] for x in tat]))
check("offset quá cuối thì rỗng", cl.get("/conversations", params={"limit": 3, "offset": 50}).json()["items"] == [])

check("không dùng em dash trong file này", chr(0x2014) not in open(__file__, encoding="utf-8").read())

if fails:
    print("\nFAIL - test_hoi_thoai_tai_dan: " + str(len(fails)) + " lỗi: " + ", ".join(fails))
    sys.exit(1)
print("\nOK - test_hoi_thoai_tai_dan: tất cả pass")
