"""Bộ lọc của Hộp thư hội thoại (0.65.3): theo bot, tình trạng, loại chat, và số đếm cho dropdown.

    python tests/run.py hoi_thoai_bo_loc      (KHÔNG mạng)

Chủ dự án (2026-09-30): chạy ba bot khác lĩnh vực thì hộp thư lẫn vào nhau, mà bộ lọc cũ chỉ có chip kênh và
một ô chọn bot bị ẩn khi có dưới hai bot. Bản này canh phía server của bộ lọc mới:
  1. `danh_sach` lọc đúng theo `status` (chưa đọc / cần trả lời / đang tiếp quản), `chat_type`, `bot_id`, và tổ hợp.
  2. Giá trị lạ thì BỎ QUA bộ lọc đó (giá trị cũ còn lưu ở trình duyệt không làm hòm thư trống trơn).
  3. `dem_bo_loc` đếm trên toàn hòm thư, không phụ thuộc bộ lọc đang chọn.
  4. Endpoint trả `bot_name` cho từng hàng, `facets`, và danh sách `bots` kèm tên; bot đã xoá không lòi id thô.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import os
import sys
import tempfile

_STATE = tempfile.mkdtemp(prefix="javis-htloc-")
os.environ["JAVIS_STATE_DIR"] = _STATE
os.environ["JAVIS_ALLOWED_HOSTS"] = "testserver"
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import time  # noqa: E402

import chatbot_reply_policy_store as rps  # noqa: E402
import chatbot_store  # noqa: E402
import conversations  # noqa: E402

_fails = []


def check(name, cond, them=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(them) + "]") if them and not cond else ""))
    if not cond:
        _fails.append(name)


if _STATE not in str(conversations.DB_PATH):
    print(f"FAIL kho không nằm trong thư mục tạm: {conversations.DB_PATH}. DỪNG.")
    sys.exit(1)

bot_a, _ = chatbot_store.create_bot({"name": "Javis Vũ", "agent_slug": "a", "brain": "brain"})
bot_b, _ = chatbot_store.create_bot({"name": "Nhi Mai", "agent_slug": "b", "brain": "brain"})
check("(chuẩn bị) có hai bot", bool(bot_a and bot_b))


def tin(bot, chat, loai, gui, text, title=""):
    r = conversations.ghi_su_kien({
        "channel": "zalo_personal", "account_id": "zp1", "account_name": "Nick", "bot_id": bot,
        "external_chat_id": chat, "chat_type": loai, "chat_title": title,
        "sender_type": gui, "sender_id": "u" + chat if gui == "customer" else "", "sender_name": "Khách " + chat,
        "text": text})
    return r["conversation_id"]


c1 = tin(bot_a, "g1", "group", "customer", "hỏi giá", "Nhóm A")                    # chưa đọc, khách nhắn cuối
c2 = tin(bot_a, "p2", "private", "customer", "chào")
conversations.ghi_su_kien({"channel": "zalo_personal", "account_id": "zp1", "bot_id": bot_a, "external_chat_id": "p2",
                           "sender_type": "ai", "text": "dạ chào anh"})           # bot đã đáp
conversations.danh_dau_da_doc(c2)
c3 = tin(bot_b, "g3", "group", "customer", "ai biết đặt lịch không", "Nhóm B")
conversations.dat_che_do(c3, "human")                                             # người tiếp quản
c4 = tin(bot_b, "p4", "private", "customer", "bao giờ có hàng")
conversations.danh_dau_da_doc(c4)                                                 # đã đọc nhưng chưa ai đáp
c5 = tin("", "p5", "private", "customer", "không có bot nào trực")                 # cuộc chat không bot
c6 = tin("bot_da_xoa", "p6", "private", "customer", "bot cũ đã xoá")


def ids(**kw):
    return {x["id"] for x in conversations.danh_sach(**kw)}


allc = {c1, c2, c3, c4, c5, c6}
check("không lọc: đủ 6 hội thoại", ids() == allc, ids())
check("lọc chưa đọc", ids(status="unread") == {c1, c3, c5, c6}, ids(status="unread"))
check("lọc cần trả lời khi bot chưa cân nhắc nhóm nào: chỉ chat riêng khách nhắn cuối chưa ai đáp (không tính cuộc bot đã đáp, "
      "không tính cuộc đã tiếp quản, KHÔNG tính nhóm vì bot chỉ nói khi được gọi)",
      ids(status="need_reply") == {c4, c5, c6}, ids(status="need_reply"))

# Bộ phán xử ghi lại: bot cân nhắc nói ở nhóm Nhóm A rồi im vì chưa chắc, chưa ai gắn nhãn.
NOW = time.time()
rps.log_decision({"bot_id": bot_a, "chat_id": "g1", "ts": NOW - 600, "text": "hỏi giá", "verdict": "silent", "candidate": True,
                  "silence_code": "below_threshold", "mode": "on", "score": 0.5, "threshold": 0.6}, NOW - 600)
hes = rps.hesitant_chats(NOW - 86400)
check("kho bộ phán xử: nhóm bot vừa cân nhắc rồi im", hes == [(bot_a, "g1")], hes)
check("lọc cần trả lời có nhóm bot cân nhắc rồi im", ids(status="need_reply", hesitant=hes) == {c1, c4, c5, c6},
      ids(status="need_reply", hesitant=hes))
check("hàng danh sách biết nó cần trả lời (nhóm thì phải có dấu bot cân nhắc)",
      conversations.can_tra_loi(conversations.chi_tiet(c1), hes) and not conversations.can_tra_loi(conversations.chi_tiet(c1), [])
      and conversations.can_tra_loi(conversations.chi_tiet(c4), []) and not conversations.can_tra_loi(conversations.chi_tiet(c2), hes)
      and not conversations.can_tra_loi(conversations.chi_tiet(c3), hes))
check("lọc đang tiếp quản", ids(status="human") == {c3}, ids(status="human"))
check("lọc nhóm", ids(chat_type="group") == {c1, c3}, ids(chat_type="group"))
check("lọc chat riêng", ids(chat_type="private") == {c2, c4, c5, c6}, ids(chat_type="private"))
check("lọc theo bot", ids(bot_id=bot_a) == {c1, c2} and ids(bot_id=bot_b) == {c3, c4})
check("bot_id='-' chỉ lấy cuộc chat KHÔNG có bot trực", ids(bot_id=conversations.BOT_KHONG_CO) == {c5}, ids(bot_id="-"))
check("tổ hợp bot + tình trạng", ids(bot_id=bot_b, status="need_reply") == {c4})
check("tổ hợp bot + tình trạng + loại", ids(bot_id=bot_a, status="unread", chat_type="group") == {c1})
check("tổ hợp không khớp thì rỗng, không lỗi", ids(bot_id=bot_a, status="human") == set())
check("giá trị lạ của tình trạng hoặc loại thì BỎ QUA bộ lọc đó, không làm hòm thư trống",
      ids(status="khong-co") == allc and ids(chat_type="?") == allc and ids(status="'; DROP TABLE conversations;--") == allc)
check("tham số cũ `mode` vẫn chạy", ids(mode="human") == {c3})

f = conversations.dem_bo_loc(hes)
check("số đếm: tổng và theo tình trạng", f["tong"] == 6 and f["status"] == {"unread": 4, "need_reply": 4, "human": 1}, f)
check("số đếm: theo loại", f["type"] == {"group": 2, "private": 4}, f["type"])
check("số đếm: theo bot, có cả khoá '' cho cuộc chat không bot",
      f["bots"][bot_a]["tong"] == 2 and f["bots"][bot_b]["tong"] == 2 and f["bots"][""]["tong"] == 1
      and f["bots"][bot_a]["unread"] == 1 and f["bots"][bot_b]["human"] == 1 and f["bots"][bot_b]["need_reply"] == 1, f["bots"])

# ---- endpoint ----
from fastapi.testclient import TestClient  # noqa: E402
import main  # noqa: E402

cl = TestClient(main.app)
r = cl.get("/conversations", params={"limit": 50}).json()
check("endpoint trả items, facets, bots, stats", r["ok"] and len(r["items"]) == 6 and "facets" in r and "bots" in r and "stats" in r)
byid = {x["id"]: x for x in r["items"]}
check("mỗi hàng có bot_name", byid[c1]["bot_name"] == "Javis Vũ" and byid[c3]["bot_name"] == "Nhi Mai" and byid[c5]["bot_name"] == "",
      {k: v["bot_name"] for k, v in byid.items()})
check("bot đã xoá thì hiện 'Bot đã xoá', không lòi id thô", byid[c6]["bot_name"] == "Bot đã xoá" and "bot_da_xoa" not in byid[c6]["bot_name"])
names = {b["id"]: b["name"] for b in r["bots"]}
check("danh sách bot cho dropdown: chỉ bot có hội thoại, kèm tên và số đếm",
      names.get(bot_a) == "Javis Vũ" and names.get(bot_b) == "Nhi Mai" and "" not in names and "bot_da_xoa" in names, names)
r = cl.get("/conversations", params={"bot_id": bot_b, "status": "need_reply", "chat_type": "private"}).json()
check("endpoint lọc theo tổ hợp", [x["id"] for x in r["items"]] == [c4], [x["id"] for x in r["items"]])
allr = cl.get("/conversations", params={"limit": 50}).json()
need = {x["id"] for x in allr["items"] if x["need_reply"]}
check("endpoint đánh dấu need_reply từng hàng, gồm cả nhóm bot cân nhắc rồi im", need == {c1, c4, c5, c6}, need)
check("và lọc status=need_reply khớp đúng các hàng đó",
      {x["id"] for x in cl.get("/conversations", params={"status": "need_reply"}).json()["items"]} == need)
check("facets không đổi khi lọc (con số ở dropdown ổn định)", r["facets"]["tong"] == 6 and r["facets"]["status"]["human"] == 1)
check("thống kê đầu trang vẫn theo bộ lọc bot", r["stats"]["tong"] == 2, r["stats"])

# ---- các trường hợp nhóm KHÔNG được tính là cần trả lời ----
g7 = tin(bot_b, "g7", "group", "customer", "chuyện của thành viên", "Nhóm 7")       # Agent chọn im có chủ ý
g8 = tin(bot_b, "g8", "group", "customer", "đã được chủ gắn nhãn", "Nhóm 8")        # chủ đã bấm Đúng/Sai
g9 = tin(bot_b, "g9", "group", "customer", "quyết định đã cũ", "Nhóm 9")            # quá 24 giờ
g10 = tin(bot_b, "g10", "group", "customer", "chưa qua cổng thô", "Nhóm 10")        # không phải ứng viên
d8 = rps.log_decision({"bot_id": bot_b, "chat_id": "g8", "ts": NOW - 300, "text": "x", "verdict": "silent", "candidate": True,
                       "silence_code": "judge_silent", "mode": "on"}, NOW - 300)
rps.force_label(d8, "missed", 1.5, NOW - 200)
rps.log_decision({"bot_id": bot_b, "chat_id": "g7", "ts": NOW - 300, "text": "x", "verdict": "silent", "candidate": True,
                  "silence_code": "agent_silent", "mode": "on"}, NOW - 300)
rps.log_decision({"bot_id": bot_b, "chat_id": "g9", "ts": NOW - 90000, "text": "x", "verdict": "silent", "candidate": True,
                  "silence_code": "below_threshold", "mode": "on"}, NOW - 90000)
rps.log_decision({"bot_id": bot_b, "chat_id": "g10", "ts": NOW - 300, "text": "x", "verdict": "silent", "candidate": False,
                  "silence_code": "no_signal", "mode": "on"}, NOW - 300)
hes2 = rps.hesitant_chats(NOW - 86400)
check("chỉ nhóm chưa gắn nhãn, còn trong 24 giờ, là ứng viên và im vì chưa chắc mới tính (agent_silent, có nhãn, quá cũ, "
      "không phải ứng viên đều không)", hes2 == [(bot_a, "g1")], hes2)
check("nên các nhóm đó không vào danh sách cần trả lời", not ({g7, g8, g9, g10} & ids(status="need_reply", hesitant=hes2)))
rps.log_decision({"bot_id": bot_b, "chat_id": "g7", "ts": NOW - 100, "text": "y", "verdict": "silent", "candidate": True,
                  "silence_code": "rate_limited", "mode": "on"}, NOW - 100)
check("hết hạn mức tự nói cũng là bot muốn nói mà bị chặn, đáng xem lại",
      g7 in ids(status="need_reply", hesitant=rps.hesitant_chats(NOW - 86400)))
check("kho bộ phán xử chưa có file thì trả rỗng và KHÔNG tạo file", (lambda p: (p.unlink(), rps.hesitant_chats(0) == [] and not p.exists())[1])(rps.db_path()))

print()
if _fails:
    print(f"{len(_fails)} FAIL")
    sys.exit(1)
print("ALL PASS")
