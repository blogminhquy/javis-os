"""Tầng CRM trên kho hội thoại khách (0.60.1): hàm mà gói javis.khach-hang-crm cắm vào.

    python tests/run.py hoi_thoai_crm      (KHÔNG mạng)

Gói ở Kho cài đặt gọi đúng các hàm này chứ không tự viết SQL, nên hợp đồng của chúng là thứ
phải canh: danh sách khách (lọc kênh / tag / chữ / ngày), hồ sơ một khách kèm mọi hội thoại
họ có mặt (cả nhóm), tag chuẩn hoá và khớp nguyên từ, ghi chú, tìm tin, chờ trả lời, thống kê
khách mới theo ngày. Và hai hàm ghi không được làm đổi thứ tự "mới hoạt động trước".
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import os
import sys
import tempfile
import time

_STATE = tempfile.mkdtemp(prefix="javis-crm-")
os.environ["JAVIS_STATE_DIR"] = _STATE

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import conversations as cs  # noqa: E402

_fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)


if _STATE not in str(cs.DB_PATH):
    print(f"FAIL kho không nằm trong thư mục tạm: {cs.DB_PATH}. DỪNG.")
    sys.exit(1)


def ev(**k):
    d = {"channel": "telegram", "account_id": "bot_1", "account_name": "Bot Giày", "bot_id": "bot_1",
         "chat_type": "private", "sender_type": "customer"}
    d.update(k)
    return cs.ghi_su_kien(d)


t0 = time.time() - 3 * 86400
a = ev(external_chat_id="11", sender_id="11", sender_name="Nguyễn Lan", text="còn màu be không?",
       external_message_id="a1", created_at=t0)
ev(external_chat_id="11", sender_type="ai", sender_name="Bot Giày", text="Dạ còn ạ", created_at=t0 + 60)
b = ev(external_chat_id="22", sender_id="22", sender_name="Trần Nam", text="giá sỉ bao nhiêu",
       external_message_id="b1", created_at=time.time() - 3 * 3600)
# Lan nhắn cả trong nhóm: khách ở nhóm là NGƯỜI GỬI
g = ev(external_chat_id="-9", chat_type="supergroup", chat_title="Nhóm khách sỉ", sender_id="11",
       sender_name="Nguyễn Lan", text="cho em hỏi size 42", external_message_id="g1")
z = cs.ghi_su_kien({"channel": "zalo_personal", "account_id": "conn1", "account_name": "Zalo Quý",
                    "external_chat_id": "u5", "sender_type": "customer", "sender_id": "u5",
                    "sender_name": "Phạm Hoa", "text": "alo shop", "external_message_id": "z1"})

ds = cs.danh_sach_khach()
check("3 khách, mới hoạt động trước", [c["name"] for c in ds] == ["Phạm Hoa", "Nguyễn Lan", "Trần Nam"])
lan = [c for c in ds if c["name"] == "Nguyễn Lan"][0]
check("mỗi khách kèm kênh, tài khoản, số tin khách (Lan: 2 tin), first/last seen",
      lan["channel_label"] == "Telegram" and lan["account_name"] == "Bot Giày" and lan["so_tin"] == 2
      and lan["first_seen_at"] and lan["last_seen_at"] >= lan["first_seen_at"])
check("lọc theo kênh zalo_personal -> 1", [c["name"] for c in cs.danh_sach_khach(channel="zalo_personal")] == ["Phạm Hoa"])
check("lọc chữ theo tên -> Nam", [c["name"] for c in cs.danh_sach_khach(q="nam")] == ["Trần Nam"])
check("lọc N ngày: Lan mới nhắn nhóm (hôm nay) nên vẫn còn; days=1 -> 3", len(cs.danh_sach_khach(days=1)) == 3)

k = cs.khach(lan["id"])
check("hồ sơ một khách", k and k["name"] == "Nguyễn Lan" and k["tags"] == [] and k["note"] == "")
check("khách không có -> None", cs.khach(99999) is None)
ht = cs.hoi_thoai_cua_khach(lan["id"])
check("hội thoại của Lan gồm chat riêng VÀ nhóm", {h["chat_type"] for h in ht} == {"private", "group"} and len(ht) == 2)
check("hội thoại của Nam chỉ có chat riêng", len(cs.hoi_thoai_cua_khach(b["customer_id"])) == 1)

tags = cs.dat_tag_khach(lan["id"], ["VIP", "vip", " Đã hỏi giá ", "VIP", ""])
check("tag chuẩn hoá: bỏ trùng, cắt khoảng trắng, giữ hoa thường", tags == ["VIP", "vip", "Đã hỏi giá"])
check("khách không có -> None khi gắn tag", cs.dat_tag_khach(99999, ["x"]) is None)
check("lọc tag khớp nguyên từ", [c["id"] for c in cs.danh_sach_khach(tag="VIP")] == [lan["id"]]
      and cs.danh_sach_khach(tag="VI") == [])
check("ghi chú lưu được và không đổi thứ tự hoạt động",
      cs.dat_ghi_chu_khach(lan["id"], "thích màu be, hẹn gọi chiều") and "màu be" in cs.khach(lan["id"])["note"]
      and [c["name"] for c in cs.danh_sach_khach()][0] == "Phạm Hoa")
check("lọc chữ theo ghi chú", [c["id"] for c in cs.danh_sach_khach(q="hẹn gọi")] == [lan["id"]])
check("chi_tiet hội thoại mang tag của khách", cs.chi_tiet(a["conversation_id"])["customer_tags"] == tags)
check("chuan_hoa_tag cắt trần 30 tag", len(cs.chuan_hoa_tag([f"t{i}" for i in range(50)])) == 30)

tim = cs.tim_tin("size 42")
check("tìm tin: ra tin trong nhóm kèm kênh và tiêu đề", len(tim) == 1 and tim[0]["title"] == "Nhóm khách sỉ"
      and tim[0]["channel"] == "telegram")
check("tìm tin theo kênh khác -> rỗng; chuỗi rỗng -> rỗng", cs.tim_tin("size 42", channel="zalo") == [] and cs.tim_tin("") == [])

cho = cs.cho_tra_loi(2)
check("chờ trả lời > 2 giờ: Nam (3 giờ) có, Lan chat riêng (bot đã đáp) không, Lan nhóm và Hoa (vừa nhắn) không",
      [c["customer_name"] for c in cho] == ["Trần Nam"])
check("ngưỡng 0 giờ -> cả 3 hội thoại chưa được đáp, cũ nhất trước",
      [c["external_chat_id"] for c in cs.cho_tra_loi(0)] == ["22", "-9", "u5"])
cs.dat_che_do(b["conversation_id"], "closed")
check("hội thoại đã đóng không còn trong chờ trả lời", all(c["customer_name"] != "Trần Nam" for c in cs.cho_tra_loi(0)))

tk = cs.thong_ke_khach(7)
check("thống kê: 3 khách, khách mới theo ngày có hôm nay (tất cả tạo hôm nay), tag VIP=1, chờ 2",
      tk["khach"] == 3 and sum(tk["khach_moi_theo_ngay"].values()) == 3 and tk["theo_tag"].get("VIP") == 1
      and tk["cho_tra_loi"] == 2)
check("thống kê theo kênh", cs.thong_ke_khach(7, channel="telegram")["khach"] == 2)

print()
if _fails:
    print(f"ĐỎ: {len(_fails)}: {', '.join(_fails)}")
    sys.exit(1)
print("Tất cả xanh.")
