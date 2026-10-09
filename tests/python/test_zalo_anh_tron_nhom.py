"""Nhóm Zalo: gửi ẢNH TRƠN rồi gọi bot thì bot thấy ảnh, không còn "lúc thấy lúc không" (0.88.3).

    python tests/run.py zalo_anh_tron_nhom      (KHÔNG mạng)

Chủ repo báo 09/10/2026: trong nhóm Zalo, bot thỉnh thoảng nói chưa thấy ảnh. Không phải do trả lời quá nhanh:
`Transport.xu_ly` bỏ ảnh KHÔNG chú thích ngay ở đầu, trước bước nhớ ảnh (nằm trong precheck). Nên cách gửi hay
gặp nhất, ảnh trơn rồi "@bot xem giúp", không bao giờ chạy; ảnh có vài chữ chú thích thì lại chạy. Kèm hai chỗ
hở: chế độ Tự đánh giá trả lời "xem giúp ảnh trên" không tag nhưng không đưa ảnh, và tải ảnh lỗi thoáng qua
không thử lại lần nào.

Điều được ghim:
  1. Ảnh trơn trong nhóm được NHỚ (qua PolicyHooks.nho_anh), không trả lời, không tốn lượt model; chạy trước mọi
     await nên ảnh về cùng nhịp đọc với câu tag đã được nhớ trước khi lượt kia cần.
  2. Không nhớ ảnh của chính nick bot, ảnh quá cũ, ảnh trong chat riêng.
  3. Lượt bot TRẢ LỜI người đó (có tag hay không) được gắn ảnh vừa nhớ.
  4. Tải ảnh lỗi tạm thì thử lại đúng một lần; lỗi vĩnh viễn (không phải ảnh) thì không.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import os
import sys
import tempfile
import time
from pathlib import Path

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-anhtron-")
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import chatbot_runtime as cr  # noqa: E402
import image_vision  # noqa: E402
import zalo_personal_channel as zc  # noqa: E402
from channels.zalo_personal import Transport  # noqa: E402

_fails = []


def check(name, cond, detail=""):
    print(("ok   " if cond else "FAIL ") + name + ("" if cond else f"  [{str(detail)[:300]}]"))
    if not cond:
        _fails.append(name)


class _Policy:
    def __init__(self):
        self.nho = []

    def nho_anh(self, meta):
        self.nho.append(meta)

    def prepare(self, text, meta):
        raise AssertionError("ảnh trơn không được đi tới bộ phán xử")


goi = []


async def _answer(text, meta, _p):
    goi.append(text)
    return {"text": "x"}


def _pre(text, meta):
    goi.append("precheck:" + text)


def bot():
    pol = _Policy()
    return Transport("conn-1", [], _answer, precheck_fn=_pre, policy=pol), pol


def anh(**kw):
    ev = {"chat_type": "group", "message_type": "image", "text": "https://f21-zpc.zdn.vn/jpg/abc.jpg",
          "external_chat_id": "g1", "external_message_id": "m1", "sender_id": "u7", "sender_name": "Lan",
          "created_at": time.time(), "metadata": {"image_url": "https://f21-zpc.zdn.vn/jpg/abc.jpg"}}
    ev.update(kw)
    return ev


# ---- 1. Ảnh trơn trong nhóm được nhớ, không trả lời ----
t, pol = bot()
asyncio.run(t.xu_ly(anh()))
check("ảnh trơn trong nhóm được nhớ", len(pol.nho) == 1 and pol.nho[0]["image_url"].endswith("abc.jpg")
      and pol.nho[0]["user_id"] == "u7" and pol.nho[0]["chat_id"] == "g1", pol.nho)
check("ảnh trơn không tốn lượt trả lời, không qua precheck", goi == [], goi)
t, pol = bot()
asyncio.run(t.xu_ly(anh(text="[chat.photo]")))
check("ảnh trơn dạng [chat.photo] cũng được nhớ", len(pol.nho) == 1)

# ---- 2. Những ảnh không được nhớ ----
zc._ID_MINH["conn-1"] = {"uid": "u-bot"}
t, pol = bot()
asyncio.run(t.xu_ly(anh(sender_id="u-bot")))
check("không nhớ ảnh của chính nick bot", pol.nho == [])
t, pol = bot()
asyncio.run(t.xu_ly(anh(created_at=time.time() - zc.TUOI_TOI_DA - 5)))
check("không nhớ ảnh quá cũ", pol.nho == [])
t, pol = bot()
asyncio.run(t.xu_ly(anh(chat_type="private")))
check("chat riêng không nhớ (không có ai để gọi bot sau)", pol.nho == [])

# ---- 3. Lượt bot trả lời được gắn ảnh vừa nhớ ----
BRAIN = Path(tempfile.mkdtemp(prefix="javis-brain-anhtron-"))
cr.chatbot_store.get_bot = lambda b: {"brain": str(BRAIN), "enabled": True}
cr._nhom_duoc_phep = lambda cfg, cid: True
cr._deps["brain_root"] = lambda b: BRAIN
G = {"chat_id": "g1", "chat_type": "group", "user_id": "u7"}
cr.PolicyHooks("bot1").nho_anh(dict(G, co_anh=True, image_url="https://f21-zpc.zdn.vn/jpg/abc.jpg", message_id="m1"))
m = cr.gan_anh_cho("bot1", dict(G, mentioned=True), "@bot xem giúp")
check("gọi bot ngay sau ảnh trơn: lượt có ảnh", m.get("_anh_cho_url", "").endswith("abc.jpg"), m)
cr.PolicyHooks("bot1").nho_anh(dict(G, co_anh=True, image_url="https://f21-zpc.zdn.vn/jpg/b.jpg", message_id="m2"))
m = cr.gan_anh_cho("bot1", dict(G), "xem giúp ảnh trên")
check("Tự đánh giá trả lời câu không tag: lượt vẫn có ảnh", m.get("_anh_cho_url", "").endswith("b.jpg"), m)
cr.PolicyHooks("bot1").nho_anh(dict(G, co_anh=True, image_url="https://f21-zpc.zdn.vn/jpg/c.jpg", message_id="m3"))
m = cr.gan_anh_cho("bot1", dict(G, user_id="u8", mentioned=True), "@bot ?")
check("người KHÁC gọi bot thì không lấy ảnh của người này", "_anh_cho_url" not in m, m)

# ---- 4. Thử lại khi tải ảnh lỗi tạm ----
lan = []


def _fake(ly_do_dau):
    async def fetch(url, folder, msg):
        lan.append(url)
        if len(lan) == 1:
            return None, ly_do_dau
        p = Path(folder)
        p.mkdir(parents=True, exist_ok=True)
        f = p / "x.png"
        f.write_bytes(b"\x89PNG\r\n\x1a\n")
        return str(f), ""
    return fetch


goc_fetch, goc_sleep = image_vision.fetch_image, cr.asyncio.sleep


async def _nhanh(_s):
    return None

try:
    cr.asyncio.sleep = _nhanh
    image_vision.fetch_image = _fake("tải ảnh lỗi: ReadTimeout: ")
    _t, paths = asyncio.run(cr.anh_cho_bot("@bot xem", dict(G, co_anh=True, image_url="https://f1.zdn.vn/a.jpg",
                                                              message_id="z9"), {"brain": str(BRAIN)}))
    check("lỗi tạm (hết giờ): thử lại một lần rồi có ảnh", len(lan) == 2 and len(paths) == 1, (lan, paths))
    lan.clear()
    image_vision.fetch_image = _fake("link không phải ảnh (text/html)")
    _t, paths = asyncio.run(cr.anh_cho_bot("@bot xem", dict(G, co_anh=True, image_url="https://f1.zdn.vn/b.jpg",
                                                              message_id="z8"), {"brain": str(BRAIN)}))
    check("lỗi vĩnh viễn (không phải ảnh): không thử lại", len(lan) == 1 and paths == [], (lan, paths))
finally:
    image_vision.fetch_image, cr.asyncio.sleep = goc_fetch, goc_sleep

print()
if _fails:
    print(f"ĐỎ {len(_fails)} mục: " + ", ".join(_fails))
    sys.exit(1)
print("Tất cả xanh.")
