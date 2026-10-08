"""Bot chuyên trách gửi được ẢNH (0.84.3).

    python tests/run.py bot_gui_anh      (KHÔNG mạng, MCP và CLI giả)

Trước bản này mọi lượt bot trả `"files": []`, nên không bot nào trên kênh nào gửi được ảnh, dù Telegram, Slack,
WhatsApp đã biết gửi `files`. Javis cố ý KHÔNG tự đính kèm file mới sinh ra (người lạ đang lái model, file vừa xuất
hiện là đường rò). Nay Agent CHỦ ĐỘNG viết `![mô tả](đường-dẫn)` và Javis chỉ gửi khi qua đủ rào.

File này canh:
  1. RÀO: chỉ ảnh có thật, trong brain của chính bot (kể cả symlink), không quá cỡ, tối đa 4 ảnh. Đường dẫn trượt rào
     giữ nguyên trong chữ, không bị nuốt mất.
  2. Kênh: chỉ kênh gửi được file mới tách ảnh và mới dạy Agent cách gửi.
  3. Zalo cá nhân gửi ảnh thật bằng CLI `msg send-image`, sau câu chữ đã gỡ phần ảnh.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import os
import sys
import tempfile
import time
from pathlib import Path

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-botanh-")
os.environ["JAVIS_REPLY_POLICY_SHADOW"] = "1"
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import bot_images  # noqa: E402
import chatbot_runtime  # noqa: E402
import chatbot_store  # noqa: E402
import zalo_cli  # noqa: E402
import zalo_personal_channel as zc  # noqa: E402

_fails = []


def check(name, cond, them=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(them) + "]") if them and not cond else ""))
    if not cond:
        _fails.append(name)


BRAIN = Path(tempfile.mkdtemp(prefix="brain-botanh-")).resolve()
(BRAIN / "attachments").mkdir()
for ten in ("a.jpg", "b.png", "c.webp", "d.gif", "e.jpeg", "mau moi.jpg"):
    (BRAIN / "attachments" / ten).write_bytes(b"\xff\xd8\xff" + b"0" * 100)
(BRAIN / "bang-gia.pdf").write_bytes(b"%PDF")
(BRAIN / "ghi-chu.md").write_text("bí mật", encoding="utf-8")
NGOAI = Path(tempfile.mkdtemp(prefix="ngoai-botanh-")).resolve()
(NGOAI / "x.jpg").write_bytes(b"\xff\xd8\xff")
B = str(BRAIN)


def P(rel):
    return str((BRAIN / rel).resolve())


# ============================================================
# 1. Rào của bot_images.pick
# ============================================================
t, f = bot_images.pick("Mẫu đây ạ ![Mẫu A](attachments/a.jpg)\nCòn gì nữa không ạ?", B)
check("ảnh trong brain: tách ra gửi riêng, kèm chú thích", f == [{"path": P("attachments/a.jpg"), "caption": "Mẫu A"}], f)
check("và gỡ khỏi câu chữ", t == "Mẫu đây ạ\nCòn gì nữa không ạ?", t)
t, f = bot_images.pick("![](attachments/mau%20moi.jpg)", B)
check("tên có khoảng trắng viết dạng %20 vẫn nhận", [x["path"] for x in f] == [P("attachments/mau moi.jpg")] and t == "", (t, f))
t, f = bot_images.pick("![](<attachments/mau moi.jpg>)", B)
check("dạng <đường dẫn có khoảng trắng> vẫn nhận", len(f) == 1, f)
t, f = bot_images.pick(f"![]({BRAIN.as_posix()}/attachments/b.png)", B)
check("đường dẫn tuyệt đối NẰM TRONG brain thì nhận", [x["path"] for x in f] == [P("attachments/b.png")], f)

for nhan, cau in (("ngoài brain bằng ../", "![](../" + NGOAI.name + "/x.jpg)"),
                  ("ngoài brain bằng đường dẫn tuyệt đối", f"![]({NGOAI.as_posix()}/x.jpg)"),
                  ("không phải ảnh (pdf)", "![](bang-gia.pdf)"),
                  ("không phải ảnh (ghi chú .md)", "![](ghi-chu.md)"),
                  ("file không có thật", "![](attachments/khong-co.jpg)"),
                  ("ảnh trên web", "![](https://a.vn/x.jpg)"),
                  ("link thường, không phải ảnh", "[xem](attachments/a.jpg)")):
    t, f = bot_images.pick("Đây ạ " + cau, B)
    check(f"CANARY: {nhan} thì KHÔNG gửi, và câu chữ giữ nguyên", f == [] and t == "Đây ạ " + cau, (t, f))

goc = bot_images.MAX_BYTES
bot_images.MAX_BYTES = 10
t, f = bot_images.pick("![](attachments/a.jpg)", B)
bot_images.MAX_BYTES = goc
check("ảnh quá cỡ thì không gửi", f == [], f)

nhieu = " ".join(f"![](attachments/{x})" for x in ("a.jpg", "b.png", "c.webp", "d.gif", "e.jpeg"))
t, f = bot_images.pick(nhieu, B)
check("tối đa 4 ảnh mỗi lần, ảnh thứ 5 ở lại trong chữ",
      len(f) == bot_images.MAX_IMAGES == 4 and t == "![](attachments/e.jpeg)", (t, len(f)))
t, f = bot_images.pick("![](attachments/a.jpg) ![](attachments/a.jpg)", B)
check("cùng một ảnh viết hai lần chỉ gửi một lần", len(f) == 1 and t == "", (t, f))

lien_ket = BRAIN / "attachments" / "tro-ra-ngoai.jpg"
try:
    os.symlink(NGOAI / "x.jpg", lien_ket)
    co_symlink = True
except (OSError, NotImplementedError):
    co_symlink = False      # Windows không có quyền tạo symlink: CI Linux vẫn canh
if co_symlink:
    t, f = bot_images.pick("![](attachments/tro-ra-ngoai.jpg)", B)
    check("CANARY: symlink trong brain trỏ ra ngoài thì không gửi", f == [], f)

# ============================================================
# 2. Kênh nào gửi được file
# ============================================================
check("Telegram và Zalo cá nhân gửi được file, Zalo Bot thì chưa",
      bot_images.channel_sends_files("telegram") and bot_images.channel_sends_files("zalo_personal")
      and not bot_images.channel_sends_files("zalo"))
cfg_p = {"name": "Lan", "agent_slug": "lan", "brain": "b"}
chatbot_runtime.wire(answer=None, brain_root=lambda b: B,
                     read_agent=lambda br, slug: ({"name": "Lan", "role": "Bán hàng"}, "Trả lời khách."))
check("prompt dạy Agent cách gửi ảnh ở kênh gửi được file",
      "GỬI ẢNH" in chatbot_runtime.build_bot_prompt(dict(cfg_p, _kenh_luot="zalo_personal")))
check("kênh không gửi được file thì không dạy (khỏi hứa điều không làm được)",
      "GỬI ẢNH" not in chatbot_runtime.build_bot_prompt(dict(cfg_p, _kenh_luot="zalo")))

# ============================================================
# 3. Zalo cá nhân gửi ảnh thật (MCP và CLI giả)
# ============================================================
CONN = {"id": "zalo-1", "label": "Shop", "connector_id": "zalo", "env": {"HOME": "/state/zalo-1"}}
KHACH = "8880001"
GUI, KHO_TIN, CLI = [], [], []
TRA_LOI = {"v": ""}


async def _goi_gia(conn, tool, args):
    if tool == "zalo_send_message":
        GUI.append(dict(args))
        return {"success": True}
    if tool == "zalo_list_threads":
        return {"threads": [{"threadId": KHACH, "name": "Khách A", "type": "user"}]}
    if tool == "zalo_get_messages":
        tin = list(KHO_TIN)
        KHO_TIN.clear()
        return {"messages": tin, "nextCursor": "c" + str(time.time())}
    return {}


async def _cli_gia(conn, command, positionals=None, options=None, timeout=120):
    CLI.append({"conn": dict(conn), "command": list(command), "pos": list(positionals or []), "opts": list(options or [])})
    return True, {"msgId": "m1"}, ""


async def _engine(text, meta, progress, *, channel="", bot=None):
    return {"text": TRA_LOI["v"], "files": []}


zc._ket_noi = lambda: [dict(CONN)]
zc._goi = _goi_gia
zc.THU_LAI_TEN_GIAY = 0
zalo_cli.run_cli = _cli_gia
chatbot_runtime.wire(answer=_engine, brain_root=lambda b: B,
                     read_agent=lambda br, slug: ({"name": "Lan", "role": "Bán hàng"}, "Trả lời khách."))

bid, loi = chatbot_store.create_bot({"name": "Lan", "agent_slug": "lan", "brain": "b", "account_ids": ["zalo-1"],
                                     "muc_quyen": "suggest"})
check("tạo được bot", bool(bid) and not loi, loi)


def tin(text, mid):
    return {"threadId": KHACH, "from": KHACH, "senderName": "Khách A", "type": "text", "text": text,
            "id": mid, "ts": int((time.time() - 2) * 1000), "threadType": 0}


async def doc():
    await zc.doc_mot_lan(dict(CONN))
    t0 = time.time()
    while zc._VIEC and time.time() - t0 < 6:
        await asyncio.sleep(0.02)
    await asyncio.sleep(0.1)


async def chay():
    ok, err = chatbot_runtime.start_bot(bid)
    check("bật bot chạy được", ok, err)

    TRA_LOI["v"] = "Dạ mẫu mới đây ạ ![Mẫu A](attachments/a.jpg)"
    KHO_TIN.append(tin("cho xem mẫu mới", "k1"))
    await doc()
    check("câu chữ đi qua MCP, KHÔNG còn cú pháp ảnh", [g["text"] for g in GUI] == ["Dạ mẫu mới đây ạ"], GUI)
    check("ảnh đi bằng CLI msg send-image, đúng cuộc chat, chat riêng (-t 0), đúng phiên Zalo",
          len(CLI) == 1 and CLI[0]["command"] == ["msg", "send-image"]
          and CLI[0]["pos"] == [KHACH, P("attachments/a.jpg")] and CLI[0]["opts"] == ["-t", "0"]
          and CLI[0]["conn"].get("home") == "/state/zalo-1", CLI)

    GUI.clear()
    CLI.clear()
    TRA_LOI["v"] = "![](attachments/b.png)"
    KHO_TIN.append(tin("ảnh thôi", "k2"))
    await doc()
    check("câu trả lời CHỈ có ảnh: gửi ảnh, không gửi tin chữ rỗng", GUI == [] and len(CLI) == 1, (GUI, CLI))

    GUI.clear()
    CLI.clear()
    TRA_LOI["v"] = "Dạ đây ạ ![](../ghi-chu.md)"
    KHO_TIN.append(tin("gửi file bí mật", "k3"))
    await doc()
    check("CANARY: đường dẫn trượt rào thì không gửi file nào, câu chữ đi nguyên văn",
          CLI == [] and [g["text"] for g in GUI] == ["Dạ đây ạ ![](../ghi-chu.md)"], (GUI, CLI))
    chatbot_runtime.stop_bot(bid)


asyncio.run(chay())

if _fails:
    print(f"\nFAIL - test_bot_gui_anh: {len(_fails)} lỗi: {_fails}")
    raise SystemExit(1)
print("\nOK - test_bot_gui_anh: tất cả pass")
