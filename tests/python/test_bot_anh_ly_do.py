"""Bot không xem được ảnh khách gửi thì nhật ký bot ghi rõ VÌ SAO (0.89.2).

    python tests/run.py bot_anh_ly_do      (KHÔNG mạng)

Chủ repo báo 10/10/2026: bot nhóm Zalo vẫn trả lời "Em không xem được ảnh kèm tin này", sau cả bản 0.88.3. Câu đó là nhãn
`_KEM_ANH`, tức Javis biết tin có ảnh nhưng không có ảnh nào tới model. Bốn khả năng: tin không kèm link ảnh, tải ảnh hỏng,
bộ não của bot không nhận ảnh (Antigravity, Grok Build), hoặc model từ chối ảnh. Trước bản này lý do chỉ in ra stderr của
server, mà bot chạy trên VPS nên không ai đọc được. Giờ lý do đi vào trường `canh_bao` của nhật ký bot.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import os
import sys
import tempfile
from pathlib import Path

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-anhlydo-")
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import chatbot_runtime as cr  # noqa: E402
import image_vision  # noqa: E402

_fails = []


def check(name, cond, detail=""):
    print(("ok   " if cond else "FAIL ") + name + ("" if cond else f"  [{str(detail)[:300]}]"))
    if not cond:
        _fails.append(name)


BRAIN = Path(tempfile.mkdtemp(prefix="javis-brain-anhlydo-"))
cr._deps["brain_root"] = lambda b: BRAIN
META = {"chat_id": "g1", "chat_type": "group", "user_id": "u1", "co_anh": True, "message_id": "m1"}


async def _nhanh(_s):
    return None


goc_fetch, goc_sleep = image_vision.fetch_image, cr.asyncio.sleep
cr.asyncio.sleep = _nhanh
try:
    async def _hong(url, folder, msg):
        return None, "máy chủ ảnh trả HTTP 403 (link có thể đã hết hạn)"
    image_vision.fetch_image = _hong
    cfg = {"brain": str(BRAIN)}
    text, paths = asyncio.run(cr.anh_cho_bot("@bot xem", dict(META, image_url="https://f1.zdn.vn/a.jpg"), cfg))
    check("tải ảnh hỏng: lượt mang nhãn không xem được", paths == [] and text.startswith(cr._KEM_ANH), text)
    check("tải ảnh hỏng: lý do vào cfg cho nhật ký", "HTTP 403" in cfg.get("_anh_loi", ""), cfg)

    cfg = {"brain": str(BRAIN)}
    asyncio.run(cr.anh_cho_bot("@bot xem", dict(META, image_url=""), cfg))
    check("tin ảnh không kèm link: ghi rõ là thiếu link", "không kèm link" in cfg.get("_anh_loi", ""), cfg)

    async def _tot(url, folder, msg):
        p = Path(folder)
        p.mkdir(parents=True, exist_ok=True)
        f = p / "ok.png"
        f.write_bytes(b"\x89PNG\r\n\x1a\n")
        return f, ""
    image_vision.fetch_image = _tot
    cfg = {"brain": str(BRAIN)}
    _t, paths = asyncio.run(cr.anh_cho_bot("@bot xem", dict(META, image_url="https://f1.zdn.vn/b.jpg", message_id="m2"), cfg))
    check("tải được ảnh: không ghi lý do nào", len(paths) == 1 and "_anh_loi" not in cfg, cfg)
finally:
    image_vision.fetch_image, cr.asyncio.sleep = goc_fetch, goc_sleep

# ---- nối vào nhật ký và vào hai đường trả lời của bot ----
RT = (SERVER / "chatbot_runtime.py").read_text(encoding="utf-8")
MAIN = (SERVER / "main.py").read_text(encoding="utf-8")
check("nhật ký bot gộp lý do ảnh vào canh_bao", 'tl.get("canh_bao_link"), cfg.get("_anh_loi")) if x)' in RT)
check("mỗi lượt xoá lý do của lượt trước", 'cfg.pop("_anh_loi", None)\n        text_engine, cfg["_anh"] = await anh_cho_bot(' in RT)
check("bộ não không nhận ảnh: cả hai đường trả lời ghi cảnh báo",
      MAIN.count('canh_bao_anh = _anh_khong_gui_duoc(prov) if images and not co_anh else ""') == 2)
check("model từ chối ảnh: cả hai đường trả lời ghi cảnh báo", MAIN.count("từ chối ảnh, đã trả lời chỉ bằng chữ.") == 2)

import main  # noqa: E402
check("câu cảnh báo bộ não không nhận ảnh chỉ đường đổi model", "không nhận ảnh" in main._anh_khong_gui_duoc("antigravity-cli")
      and "Đổi model" in main._anh_khong_gui_duoc("antigravity-cli"))

print()
if _fails:
    print(f"ĐỎ {len(_fails)} mục: " + ", ".join(_fails))
    sys.exit(1)
print("Tất cả xanh.")
