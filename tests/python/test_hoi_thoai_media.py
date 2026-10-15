"""Ảnh và file khách gửi trong Hộp thư bot: đường `/conversations/{id}/media` (0.171.0).

    python tests/run.py hoi_thoai_media

Chủ repo 15/10/2026: khách gửi ảnh thì Hộp thư chỉ hiện "image https://...jpg"; muốn ảnh hiện thẳng, file bấm tải về.
Kênh bot (Telegram, Zalo Bot, Slack, WhatsApp...) tải file khách về brain của bot và ghi đường dẫn vào tin, nên giao diện
cần một đường phát file đó. Đường này đọc đĩa theo một tham số người gọi đưa vào, nên test chủ yếu là test an toàn:
chỉ file nằm THẬT trong inbox/ hoặc attachments/ của brain của CHÍNH hội thoại đó.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import os
import sys
import tempfile

_STATE = tempfile.mkdtemp(prefix="javis-ht-media-")
_BRAINS = tempfile.mkdtemp(prefix="javis-ht-media-brains-")
os.environ["JAVIS_STATE_DIR"] = _STATE
os.environ["BRAINS_DIR"] = _BRAINS

BRAIN = os.path.join(_BRAINS, "brain")
KHAC = os.path.join(_BRAINS, "khac")
for d in (os.path.join(BRAIN, "inbox", "khach"), os.path.join(BRAIN, "attachments"), os.path.join(KHAC, "inbox", "khach")):
    os.makedirs(d, exist_ok=True)
ANH = os.path.join(BRAIN, "inbox", "khach", "tg_anh.jpg")
FILE = os.path.join(BRAIN, "inbox", "khach", "bao-gia.xlsx")
GHI_CHU = os.path.join(BRAIN, "bi-mat.md")
CUA_BRAIN_KHAC = os.path.join(KHAC, "inbox", "khach", "cua-nguoi-khac.jpg")
for f, b in ((ANH, b"\xff\xd8\xff" + b"0" * 40), (FILE, b"PK" + b"0" * 40), (GHI_CHU, b"khong duoc lo"),
             (CUA_BRAIN_KHAC, b"\xff\xd8\xff" + b"1" * 40)):
    with open(f, "wb") as fh:
        fh.write(b)

from fastapi.testclient import TestClient   # noqa: E402
import chatbot_store                        # noqa: E402
import conversations                        # noqa: E402
import main                                 # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

_fails = []


def check(name, cond, extra=None):
    print(("ok   " if cond else "FAIL ") + name + ("" if cond or extra is None else f"  [{extra}]"))
    if not cond:
        _fails.append(name)


cl = TestClient(main.app, base_url="http://localhost")
bid, loi = chatbot_store.create_bot({"name": "Bot Áo", "agent_slug": "cskh", "brain": BRAIN, "token": "1:x"})
check("tạo được bot", bool(bid) and not loi, loi)
r = conversations.ghi_su_kien({
    "channel": "telegram", "account_id": "1", "account_name": "Bot Áo", "bot_id": bid,
    "external_chat_id": "777", "chat_type": "private", "sender_type": "customer", "sender_id": "777",
    "sender_name": "Lan", "message_type": "image",
    "text": f"[Người dùng gửi ảnh qua Telegram, đã tải về: {ANH}]\nÁo này size M còn không?"})
CID = r.get("conversation_id")
check("ghi được tin ảnh", r.get("ok") and CID, r)


def lay(p, **kw):
    return cl.get(f"/conversations/{CID}/media", params=dict(p=p, **kw))


g = lay(ANH)
check("ảnh khách gửi xem được ngay (inline)", g.status_code == 200 and g.headers.get("content-disposition") == "inline",
      (g.status_code, g.headers.get("content-disposition")))
check("đúng nội dung ảnh", g.content.startswith(b"\xff\xd8\xff"))
g = lay(FILE)
check("file khách gửi tải về (attachment)", g.status_code == 200 and "attachment" in (g.headers.get("content-disposition") or ""),
      g.headers.get("content-disposition"))
check("ảnh với dl=1 cũng tải về", "attachment" in (lay(ANH, dl=1).headers.get("content-disposition") or ""))

check("CANARY: ghi chú ngoài inbox/attachments KHÔNG đọc được", lay(GHI_CHU).status_code == 404)
check("CANARY: leo thư mục bằng .. không được",
      lay(os.path.join(BRAIN, "inbox", "khach", "..", "..", "bi-mat.md")).status_code == 404)
check("CANARY: file trong brain KHÁC không đọc được", lay(CUA_BRAIN_KHAC).status_code == 404)
check("CANARY: file hệ thống không đọc được", lay("/etc/passwd").status_code == 404)
check("hội thoại không tồn tại: 404", cl.get("/conversations/999999/media", params={"p": ANH}).status_code == 404)

# Liên kết tượng trưng trong inbox trỏ ra ngoài: resolve trước khi so nên cũng bị chặn.
lien_ket = os.path.join(BRAIN, "inbox", "khach", "lien-ket.md")
try:
    os.symlink(GHI_CHU, lien_ket)
    check("CANARY: symlink trong inbox trỏ ra ngoài không đọc được", lay(lien_ket).status_code == 404)
except (OSError, NotImplementedError):
    print("bỏ qua: máy không tạo được symlink")

print()
if _fails:
    print(f"ĐỎ {len(_fails)} mục: " + ", ".join(_fails))
    sys.exit(1)
print("Tất cả xanh.")
