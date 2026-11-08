"""Nhập tin cũ của Zalo cá nhân vào Hộp thư (0.174.0).

    python tests/run.py zalo_nhap_lich_su      (KHÔNG mạng, MCP giả)

Chủ repo hỏi 16/10/2026: đăng nhập Zalo vào Javis lần đầu thì có đồng bộ được tin nhắn cũ không, làm thành một tuỳ chọn riêng.
javis-zalo đã tự kéo khoảng 2 tuần tin cũ về mỗi lần kết nối (`zalo_search_history`); nút "Nhập tin cũ" đổ chúng vào Hộp thư.

Các rào file này canh:
  1. Cuộc chat đã có tin chỉ nhận các tin cũ hơn tin đầu của nó, và chúng hiện TRÊN tin đó dù id mới hơn (`seq`,
     conversations.ORDER_KEY). Chủ báo 08/11/2026: trước đây cuộc chat đã có tin bị bỏ qua hẳn, nên tài khoản đã bật Ghi hội thoại
     bấm nhập không được gì. Thứ tự đó phải đúng ở mọi chỗ đọc: khung tin (trang đầu, cuộn lên, nhịp 5 giây), ngữ cảnh bot, tin khách
     cuối, cắt nhóm.
  2. Không tính chưa đọc, đánh dấu `lich_su`, tin của chính chủ là tin người thật.
  3. Đọc đủ các trang (mới trước, lùi dần bằng `before`), có trần, bấm lại không nhân đôi.
  4. MCP hỏng thì báo rõ, không ném.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import os
import sys
import tempfile
import time

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-znhap-")
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import channels  # noqa: E402
import conversations  # noqa: E402
import zalo_personal_channel as zc  # noqa: E402

_fails = []


def check(name, cond, them=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(them) + "]") if them and not cond else ""))
    if not cond:
        _fails.append(name)


NOW = int(time.time() * 1000)


def tin(mid, thread, text, phut_truoc, self_=False, ttype="dm", sender="u-khach", ten="Khách A"):
    return {"msgId": str(mid), "threadId": thread, "threadType": ttype, "senderId": sender, "senderName": ten,
            "isSelf": self_, "text": text, "timestamp": NOW - phut_truoc * 60_000, "type": "text"}


# Kho lịch sử giả, xếp cũ trước mới sau như javis-zalo; query trả trang MỚI NHẤT trước, `cursor` = id tin cũ nhất của trang.
KHO = [
    tin(1, "u1", "Chào shop, còn nước mắm 500ml không ạ?", 600),
    tin(2, "u1", "Dạ còn ạ, 120 nghìn một chai.", 590, self_=True, sender="me", ten="Chủ"),
    tin(3, "u2", "Cho em hỏi giá sỉ", 500, sender="u-b", ten="Khách B"),
    tin(4, "g1", "Mai họp lớp nhé", 400, ttype="group", sender="u-c", ten="Bạn C"),
    tin(5, "u1", "Em lấy 2 chai nhé", 300),
    tin(6, "u3", "Shop ơi", 200, sender="u-d", ten="Khách D"),
]
GOI = []
HONG = {"v": False}


def _query(since, limit, before):
    ds = [m for m in KHO if m["timestamp"] >= since]
    if before:
        idx = next((i for i, m in enumerate(ds) if m["msgId"] == before), -1)
        ds = ds[:idx] if idx >= 0 else []
    page = ds[max(0, len(ds) - limit):]
    return {"count": len(page), "messages": [dict(m) for m in page],
            "cursor": page[0]["msgId"] if page else None, "hasMore": len(ds) > len(page)}


async def _goi_gia(conn, tool, args):
    GOI.append((tool, dict(args)))
    if tool == "zalo_search_history":
        if HONG["v"]:
            raise RuntimeError("Unknown tool: zalo_search_history")
        return _query(args.get("since") or 0, int(args.get("limit") or 50), args.get("before"))
    if tool == "zalo_list_threads":
        return {"threads": [{"threadId": "u1", "name": "Khách A", "threadType": "dm"},
                            {"threadId": "u2", "name": "Khách B", "threadType": "dm"},
                            {"threadId": "u3", "name": "Khách D", "threadType": "dm"},
                            {"threadId": "g1", "name": "Lớp 12A", "threadType": "group"}]}
    return {}


zc._ket_noi = lambda: [{"id": "zalo-1", "label": "Zalo của tôi", "connector_id": "zalo"}]
zc._goi = _goi_gia
zc.NHAP_TRANG = 2       # trang nhỏ để chắc chắn đọc nhiều trang

# ---- 0. Năng lực: chỉ kênh có hàm mới hiện nút
check("Zalo cá nhân có năng lực nhập tin cũ", channels.spec("zalo_personal").nl("nhap_lich_su"))
check("Telegram không có", not channels.spec("telegram").nl("nhap_lich_su"))

# ---- 1. Cuộc chat u2 ĐÃ có tin (vòng đọc ghi từ trước): tin cũ hơn được thêm lên TRÊN nó
conversations.ghi_su_kien({"channel": "zalo_personal", "account_id": "zalo-1", "external_chat_id": "u2",
                           "chat_type": "private", "sender_type": "customer", "sender_id": "u-b",
                           "sender_name": "Khách B", "message_type": "text", "text": "Tin mới hôm nay",
                           "external_message_id": "99", "created_at": time.time()})

r = asyncio.run(zc.nhap_lich_su("zalo-1"))
check("nhập chạy được", r.get("ok"), r)
check("đọc hết các trang (mới trước, lùi bằng before)",
      sum(1 for t, a in GOI if t == "zalo_search_history") >= 3 and any(a.get("before") for t, a in GOI), GOI)
check("chỉ lấy trong NHAP_NGAY ngày",
      all(a.get("since", 0) >= NOW - (zc.NHAP_NGAY + 1) * 86400_000 for t, a in GOI if t == "zalo_search_history"))
check("nhập đúng 6 tin vào 4 cuộc chat, kể cả u2 đã có tin", r.get("so_tin") == 6 and r.get("so_cuoc_chat") == 4, r)

ds = {c["external_chat_id"]: c for c in conversations.danh_sach(limit=50)}
u1 = ds.get("u1") or {}
check("CANARY: tin cũ KHÔNG tính chưa đọc", int(u1.get("unread_count") or 0) == 0, u1)
check("cuộc chat u1 có tiêu đề tên khách", u1.get("title") == "Khách A", u1)
check("nhóm g1 vào đúng loại nhóm", (ds.get("g1") or {}).get("chat_type") == "group", ds.get("g1"))
u2 = ds.get("u2") or {}
check("u2 có thêm tin cũ của nó", int(u2.get("message_count") or 0) == 2, u2)
check("u2: tin cuối vẫn là tin mới hôm nay, không bị tin cũ đè", u2.get("last_message") == "Tin mới hôm nay", u2)
check("u2: tin cũ không tính chưa đọc", int(u2.get("unread_count") or 0) == 1, u2)
m2 = conversations.tin_nhan(int(u2["id"]))
check("u2: tin cũ đứng TRÊN tin đã có dù id mới hơn", [m["text"] for m in m2] == ["Cho em hỏi giá sỉ", "Tin mới hôm nay"]
      and m2[0]["id"] > m2[1]["id"], [(m["id"], m["text"]) for m in m2])
check("u2: tin đã có còn tin cũ hơn nó (has_more)", conversations.co_tin_cu(int(u2["id"]), m2[1]["id"]))
check("u2: tin cũ nhất thì hết", not conversations.co_tin_cu(int(u2["id"]), m2[0]["id"]))
check("u2: cuộn lên từ tin đã có ra đúng tin cũ",
      [m["text"] for m in conversations.tin_nhan(int(u2["id"]), before_id=m2[1]["id"])] == ["Cho em hỏi giá sỉ"])
check("u2: nhịp 5 giây (after = tin cuối khung) không nối tin cũ vừa nhập vào cuối",
      conversations.tin_nhan(int(u2["id"]), after_id=m2[1]["id"]) == [])
check("u2: ngữ cảnh bot xếp cũ trước mới sau",
      [m["text"] for m in conversations.tin_gan_day("zalo_personal", "zalo-1", "u2")] == ["Cho em hỏi giá sỉ", "Tin mới hôm nay"])
check("u2: tin khách cuối là tin mới hôm nay, không phải tin cũ vừa nhập",
      conversations.last_customer_message_id(int(u2["id"])) == m2[1]["id"])
# A live message after the import still goes at the bottom, and the 5-second tick brings it.
conversations.ghi_su_kien({"channel": "zalo_personal", "account_id": "zalo-1", "external_chat_id": "u2",
                           "chat_type": "private", "sender_type": "customer", "sender_id": "u-b",
                           "sender_name": "Khách B", "message_type": "text", "text": "Tin sau khi nhập",
                           "external_message_id": "100", "created_at": time.time()})
check("u2: tin sống ghi sau lần nhập vẫn xuống cuối",
      [m["text"] for m in conversations.tin_nhan(int(u2["id"]))][-1] == "Tin sau khi nhập")
check("u2: nhịp 5 giây lấy được tin sống đó",
      [m["text"] for m in conversations.tin_nhan(int(u2["id"]), after_id=m2[1]["id"])] == ["Tin sau khi nhập"])

ms = conversations.tin_nhan(int(u1["id"]))
check("tin trong cuộc chat xếp cũ trước mới sau", [m["text"] for m in ms] ==
      ["Chào shop, còn nước mắm 500ml không ạ?", "Dạ còn ạ, 120 nghìn một chai.", "Em lấy 2 chai nhé"], [m["text"] for m in ms])
check("tin của chính chủ (isSelf) là tin người thật, không phải khách", ms[1]["sender_type"] == "human", ms[1])
check("mọi tin nhập được đánh dấu lich_su", all((m.get("metadata") or {}).get("lich_su") for m in ms), ms)
check("tin cuối của cuộc chat là tin mới nhất", u1.get("last_message", "").startswith("Em lấy 2 chai"), u1)

# ---- 2. Bấm lại: không nhân đôi (cuộc chat giờ đã có tin)
r2 = asyncio.run(zc.nhap_lich_su("zalo-1"))
check("bấm lại không nhập thêm tin nào", r2.get("ok") and r2.get("so_tin") == 0 and r2.get("so_cuoc_chat") == 0, r2)

# ---- 2b. Nhóm đã có tin, nhận tin cũ, rồi bị cắt: tin cũ nhất (tin nhập) đi trước, tin mới ở lại
conversations.ghi_su_kien({"channel": "zalo_personal", "account_id": "zalo-1", "external_chat_id": "g2",
                           "chat_type": "group", "sender_type": "customer", "sender_id": "u-x", "sender_name": "X",
                           "message_type": "text", "text": "Nhóm: tin mới", "external_message_id": "g2-new",
                           "created_at": time.time()})
dau = conversations.first_order("zalo_personal", "zalo-1", "g2")
for i, (mid, chu) in enumerate([("g2-a", "Nhóm: cũ 1"), ("g2-b", "Nhóm: cũ 2")]):
    conversations.ghi_su_kien({"channel": "zalo_personal", "account_id": "zalo-1", "external_chat_id": "g2",
                               "chat_type": "group", "sender_type": "customer", "sender_id": "u-x", "sender_name": "X",
                               "message_type": "text", "text": chu, "external_message_id": mid,
                               "created_at": time.time() - 3600 + i}, dem_chua_doc=False, late=True, seq=dau["key"] - (2 - i))
g2 = {c["external_chat_id"]: c for c in conversations.danh_sach(limit=50)}["g2"]
check("nhóm g2 xếp đúng thứ tự trước khi cắt",
      [m["text"] for m in conversations.tin_nhan(int(g2["id"]))] == ["Nhóm: cũ 1", "Nhóm: cũ 2", "Nhóm: tin mới"])
with conversations._lock:
    db = conversations._conn()
    db.execute("BEGIN IMMEDIATE")
    xoa = conversations._cat_nhom_mot_cuoc(db, int(g2["id"]), 2)
    db.execute("COMMIT")
check("cắt nhóm còn 2 tin: xoá tin cũ nhất, không xoá tin mới có id nhỏ hơn",
      xoa == 1 and [m["text"] for m in conversations.tin_nhan(int(g2["id"]))] == ["Nhóm: cũ 2", "Nhóm: tin mới"])
dau = conversations.first_order("zalo_personal", "zalo-1", "g2")
conversations.ghi_su_kien({"channel": "zalo_personal", "account_id": "zalo-1", "external_chat_id": "g2",
                           "chat_type": "group", "sender_type": "customer", "sender_id": "u-x", "sender_name": "X",
                           "message_type": "text", "text": "Nhóm: cũ 0", "external_message_id": "g2-0",
                           "created_at": time.time() - 7200}, dem_chua_doc=False, late=True, seq=dau["key"] - 1000)
check("tin nhập có thể mang thứ tự âm", conversations.first_order("zalo_personal", "zalo-1", "g2")["key"] < 0)
with conversations._lock:
    db = conversations._conn()
    db.execute("BEGIN IMMEDIATE")
    xoa = conversations._cat_nhom_mot_cuoc(db, int(g2["id"]), 5)
    db.execute("COMMIT")
check("nhóm chưa tới mức thì không xoá gì (kể cả tin có thứ tự âm)", xoa == 0)

# ---- 3. Trần số tin
zc.NHAP_TOI_DA = 3
r3 = asyncio.run(zc.nhap_lich_su("zalo-1"))
check("chạm trần thì báo het_tran", r3.get("het_tran") is True, r3)
zc.NHAP_TOI_DA = 5000

# ---- 4. MCP cũ không có tool lịch sử: báo rõ, không ném
HONG["v"] = True
r4 = asyncio.run(zc.nhap_lich_su("zalo-1"))
check("MCP không có zalo_search_history: trả lỗi rõ ràng", not r4.get("ok") and "javis-zalo" in (r4.get("loi") or ""), r4)
HONG["v"] = False

r5 = asyncio.run(zc.nhap_lich_su("khong-co"))
check("tài khoản không còn ở trang Kết nối: báo lỗi", not r5.get("ok") and r5.get("loi"), r5)

# ---- 5. Không chạy chồng
zc._DANG_NHAP.add("zalo-1")
r6 = asyncio.run(zc.nhap_lich_su("zalo-1"))
zc._DANG_NHAP.discard("zalo-1")
check("đang nhập thì lần bấm thứ hai được báo, không chạy chồng", not r6.get("ok"), r6)

check("no em dash", chr(0x2014) not in open(__file__, encoding="utf-8").read())

print()
if _fails:
    print(f"{len(_fails)} FAIL: " + ", ".join(_fails))
    sys.exit(1)
print("ALL PASS")
