"""Hòm thư bot tìm theo số điện thoại (0.216.0).

    python tests/run.py hoi_thoai_tim_sdt      (KHÔNG mạng, Zalo giả)

Chủ dự án (2026-10-18): "Ở phần tìm kiếm của bên hòm thư bot, em xem có làm được tìm theo sđt hay không? Zalo người ta
có sđt là tìm đc". Tin Zalo không mang số của người kia, nên kho phải tự giữ số, và hỏi Zalo khi chưa biết:
  1. Chuẩn hoá số: 0912..., 84912..., +84 912 345 678 về một dạng; số gõ dở không được coi là số đầy đủ.
  2. Kho cũ được thêm cột `phone`, không mất dữ liệu.
  3. Ô tìm khớp số đã lưu theo cả dạng 0 lẫn 84, và id chat của kênh lấy số làm id (WhatsApp).
  4. Gõ đủ một số chưa có trong kho: hỏi Zalo (`friend find`), gắn số vào khách, cuộc chat hiện ra; người chưa từng
     nhắn thì báo "chưa có cuộc chat"; không có Zalo thì báo rõ. Kết quả được nhớ, không hỏi Zalo lặp; có trần số lần.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

_STATE = tempfile.mkdtemp(prefix="javis-htsdt-")
os.environ["JAVIS_STATE_DIR"] = _STATE
os.environ["JAVIS_ALLOWED_HOSTS"] = "testserver"
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import conversations  # noqa: E402
import zalo_cli  # noqa: E402
import zalo_personal_channel as zc  # noqa: E402
import zalo_phone_lookup as zpl  # noqa: E402

_fails = []


def check(name, cond, them=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(them) + "]") if them and not cond else ""))
    if not cond:
        _fails.append(name)


if _STATE not in str(conversations.DB_PATH):
    print(f"FAIL kho không nằm trong thư mục tạm: {conversations.DB_PATH}. DỪNG.")
    sys.exit(1)

# ---- 1. Chuẩn hoá số ----
ch = conversations.chuan_hoa_sdt
check("0912345678 giữ nguyên", ch("0912345678") == "0912345678")
check("84912345678 về dạng 0", ch("84912345678") == "0912345678")
check("+84 912 345 678 về dạng 0", ch("+84 912 345 678") == "0912345678")
check("0912.345.678 và 0912-345-678 cũng nhận", ch("0912.345.678") == ch("0912-345-678") == "0912345678")
check("số gõ dở không phải số đầy đủ", ch("091234567") == "" and ch("849123456") == "" and ch("8491234567") == "")
check("chữ, số bàn (02...), số thừa chữ số: không nhận",
      ch("Lan 0912345678") == "" and ch("0243456789") == "" and ch("09123456789") == "" and ch("") == "")
check("dạng 84 cho Zalo", conversations.sdt_84("0912 345 678") == "84912345678")
bt = conversations.bien_the_sdt
check("biến thể tìm: dãy 0 thêm dạng 84", bt("0912 345") == ["0912345", "84912345"])
check("biến thể tìm: dãy 84 thêm dạng 0", bt("+84912") == ["84912", "0912"])
check("chữ thường và dãy quá ngắn không tìm vào cột số", bt("Lan") == [] and bt("091") == [] and bt("a0912345") == [])

# ---- 2. Kho cũ được thêm cột phone ----
_cu = Path(_STATE) / "kho-cu.db"
db = sqlite3.connect(str(_cu))
db.executescript(conversations._SCHEMA)      # bảng gốc chưa có cột phone: cột đó chỉ thêm bằng _nang_cap
db.execute("INSERT INTO customers(channel_account_id, external_user_id, name, created_at, updated_at) VALUES('x:1','u','Cũ',1,1)")
db.commit()
db.close()
_goc = conversations.DB_PATH
conversations.DB_PATH = _cu
try:
    cot = {r[1] for r in conversations._conn().execute("PRAGMA table_info(customers)").fetchall()}
    giu = conversations._conn().execute("SELECT name, phone FROM customers").fetchone()
    check("kho cũ có thêm cột phone", "phone" in cot, cot)
    check("dữ liệu cũ còn nguyên, số rỗng", giu and giu["name"] == "Cũ" and giu["phone"] == "", giu and dict(giu))
finally:
    conversations.close()
    conversations.DB_PATH = _goc


# ---- 3. Tìm theo số đã lưu ----
def tin(kenh, tk, chat, gui, text, ten=""):
    return conversations.ghi_su_kien({
        "channel": kenh, "account_id": tk, "account_name": "Nick " + tk, "external_chat_id": chat, "chat_type": "private",
        "sender_type": gui, "sender_id": chat if gui == "customer" else "", "sender_name": ten, "text": text})


lan = tin("zalo_personal", "zp1", "uid_lan", "customer", "chị hỏi giá nước mắm", "Lan")
khach_lan = lan["customer_id"]
wa = tin("whatsapp", "wa1", "84987654321", "customer", "hello", "Mai")
check("(chuẩn bị) hai cuộc chat", lan["ok"] and wa["ok"])


def ids(q, **kw):
    return {x["id"] for x in conversations.danh_sach(q=q, **kw)}


check("chưa có số thì tìm số không ra Lan", lan["conversation_id"] not in ids("0912345678"))
kid = conversations.gan_sdt_khach("zalo_personal", "zp1", "uid_lan", "84 912 345 678", "Lan")
check("gắn số cho khách đã có", kid == khach_lan)
check("tìm đủ số dạng 0 ra Lan", lan["conversation_id"] in ids("0912345678"))
check("tìm dạng 84 cũng ra", lan["conversation_id"] in ids("84912345678"))
check("tìm một phần số (đuôi) cũng ra", lan["conversation_id"] in ids("345 678"))
check("hàng danh sách mang số của khách", conversations.danh_sach(q="0912345678")[0]["customer_phone"] == "0912345678")
check("WhatsApp lấy số làm id: gõ dạng 0 vẫn ra", wa["conversation_id"] in ids("0987654321"))
check("tìm chữ vẫn như cũ", ids("nước mắm") == {lan["conversation_id"]})
check("trang Khách cũng tìm theo số",
      [k["id"] for k in conversations.danh_sach_khach(q="0912 345 678")] == [khach_lan])

# Chỉ chủ nhắn đi, khách chưa nhắn lại: chưa có khách. Gắn số thì tạo khách và nối vào cuộc chat.
chu = tin("zalo_personal", "zp1", "uid_hoa", "human", "chào chị Hoa")
check("(chuẩn bị) cuộc chat chưa có khách", chu["customer_id"] is None)
kid = conversations.gan_sdt_khach("zalo_personal", "zp1", "uid_hoa", "0901112223", "Hoa")
check("gắn số tạo khách và nối vào cuộc chat", kid and conversations.chi_tiet(chu["conversation_id"])["customer_id"] == kid)
check("rồi tìm số ra cuộc chat đó", chu["conversation_id"] in ids("0901112223"))
check("không có khách lẫn cuộc chat thì không tạo gì",
      conversations.gan_sdt_khach("zalo_personal", "zp1", "uid_la", "0933333333") is None)
check("số không hợp lệ thì không gắn", conversations.gan_sdt_khach("zalo_personal", "zp1", "uid_lan", "123") is None)

# ---- 4. Hỏi Zalo ----
CONNS = [{"id": "zp1", "label": "Zalo Shop", "env": {"HOME": _STATE}}]
zc._ket_noi = lambda: CONNS
GOI = []
TRA = {}


async def _gia_run_cli(sess, command, positionals=None, options=None, timeout=0):
    GOI.append((sess.get("home"), list(command), list(positionals or [])))
    so = (positionals or [""])[0]
    return TRA.get(so, (False, None, f'No Zalo user found for "{so}". User may not exist'))


zalo_cli.run_cli = _gia_run_cli

# Người chưa từng nhắn: Zalo biết số, trong kho không có cuộc chat.
TRA["84977777777"] = (True, {"uid": "uid_moi", "display_name": "Chị Ngọc"}, "")
r = asyncio.run(zpl.lookup("0977777777"))
check("hỏi Zalo đúng lệnh friend find, số dạng 84, trong phiên của tài khoản",
      GOI == [(_STATE, ["friend", "find"], ["84977777777"])], GOI)
x = r["results"][0]
check("biết số là Zalo của ai", r["phone"] == "0977777777" and x["uid"] == "uid_moi" and x["name"] == "Chị Ngọc"
      and x["account_id"] == "zalo_personal:zp1" and x["account_label"] == "Zalo Shop", r)
GOI.clear()
r = asyncio.run(zpl.lookup("0977 777 777"))
check("hỏi lại cùng số: dùng kết quả đã nhớ, không gọi Zalo", GOI == [] and r["results"][0]["cached"], GOI)
check("chữ không phải số đầy đủ thì không hỏi", asyncio.run(zpl.lookup("09777")) == {"phone": "", "results": []} and not GOI)
check("lọc theo tài khoản kênh khác thì không hỏi Zalo",
      asyncio.run(zpl.lookup("0977777777", account_id="whatsapp:wa1"))["results"] == [])

# Không có Zalo: nhớ kết quả âm.
GOI.clear()
r = asyncio.run(zpl.lookup("0966666666"))
check("không có Zalo: không uid, không lỗi", r["results"][0]["uid"] == "" and r["results"][0]["error"] == "", r)
asyncio.run(zpl.lookup("0966666666"))
check("kết quả âm cũng được nhớ", len(GOI) == 1, GOI)
check("kết quả âm hết hạn sau một ngày", zpl._cached("zp1", "0966666666", __import__("time").time() + zpl.NEG_TTL + 5) is None)

# Lỗi khác (phiên Zalo hỏng): báo lỗi, nhớ ngắn.
TRA["84955555555"] = (False, None, "Find user failed: Not logged in")
r = asyncio.run(zpl.lookup("0955555555"))
check("lỗi khác thì báo đúng lỗi", "Not logged in" in r["results"][0]["error"], r)

# Trần số lần hỏi mỗi giờ.
zpl._live[:] = [__import__("time").time()] * zpl.MAX_LIVE_PER_HOUR
GOI.clear()
r = asyncio.run(zpl.lookup("0944444444"))
check("quá trần mỗi giờ: không gọi Zalo, báo rõ", GOI == [] and "giới hạn" in r["results"][0]["error"], r)
check("lỗi quá trần không bị nhớ (hết giờ là hỏi được)", zpl._cached("zp1", "0944444444", __import__("time").time()) is None)
zpl._live.clear()

# Đọc kết quả friend find dạng bọc {data: {...}}.
check("đọc được kết quả bọc data", zpl.parse_find({"data": {"uid": "u9", "zaloName": "Tú"}}) == ("u9", "Tú"))
check("không có uid thì rỗng", zpl.parse_find({"error": 1}) == ("", ""))

# ---- 5. Endpoint ----
from fastapi.testclient import TestClient  # noqa: E402
import main  # noqa: E402

cl = TestClient(main.app)
# Lan đã nhắn nhưng kho chưa biết số mới của chị: Zalo trả uid của Lan, số được gắn và cuộc chat hiện ra.
TRA["84922222222"] = (True, {"uid": "uid_lan", "display_name": "Lan"}, "")
GOI.clear()
r = cl.get("/conversations", params={"q": "0922 222 222"}).json()
check("gõ đủ số chưa biết: hỏi Zalo rồi hiện cuộc chat của Lan",
      [x["id"] for x in r["items"]] == [lan["conversation_id"]] and len(GOI) == 1, (r.get("items"), GOI))
pl = r["phone_lookup"]["results"][0]
check("phone_lookup báo có cuộc chat và đang hiện", pl["has_chat"] and pl["shown"], pl)
GOI.clear()
r = cl.get("/conversations", params={"q": "0922222222"}).json()
check("lần sau khớp ngay trong kho, không hỏi Zalo", r["phone_lookup"] is None and GOI == []
      and [x["id"] for x in r["items"]] == [lan["conversation_id"]], (r.get("phone_lookup"), GOI))
r = cl.get("/conversations", params={"q": "0977777777"}).json()
pl = r["phone_lookup"]["results"][0]
check("người chưa từng nhắn: danh sách trống, báo tên và chưa có chat",
      r["items"] == [] and pl["name"] == "Chị Ngọc" and not pl["has_chat"], r)
r = cl.get("/conversations", params={"q": "0912345678", "account_id": "whatsapp:wa1"}).json()
check("lọc theo tài khoản WhatsApp: không hỏi Zalo", r["phone_lookup"] is None)
GOI.clear()
r = cl.get("/conversations", params={"q": "nước mắm"}).json()
check("tìm chữ không đụng tới Zalo", r["phone_lookup"] is None and GOI == [])

# ---- 6. Giao diện ----
js = (ROOT / "dashboard" / "conversations.js").read_text(encoding="utf-8")
check("ô tìm có dòng báo kết quả hỏi Zalo", 'class="ht-sdt"' in js and "function veSdt(" in js)
check("kết quả cũ không đè kết quả mới khi gõ tiếp", "if (hoi !== _q) return;" in js)
check("luật nhận số của giao diện khớp server", "84[35789]\\d{8}|0[35789]\\d{8}" in js)
import json  # noqa: E402

for lang in ("vi", "en"):
    d = json.loads((ROOT / "dashboard" / "i18n" / f"{lang}.json").read_text(encoding="utf-8"))
    check(f"{lang}: đủ chữ", all(d.get("ht." + k) for k in
                                ("sdt_dang_tim", "sdt_chua_chat", "sdt_bi_loc", "sdt_khong_co", "sdt_loi", "sdt_nguoi")))
    check(f"{lang}: ô tìm nhắc tìm được theo số", ("số điện thoại" if lang == "vi" else "phone") in d["ht.tim_ph"])
css = (ROOT / "dashboard" / "console.css").read_text(encoding="utf-8")
check("dòng báo chữ 16px", ".ht-sdt { margin: 0 4px 6px; padding: 8px 10px; border-radius: 9px; background: var(--accent-wash);"
      " color: var(--text);\n  font-size: 16px;" in css)

if _fails:
    print(f"\nFAIL {len(_fails)}: " + ", ".join(_fails))
    sys.exit(1)
print("\nOK - test_hoi_thoai_tim_sdt: all pass")
