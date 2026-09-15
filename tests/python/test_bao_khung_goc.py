"""Kết quả của cộng sự phải quay VỀ khung Trò chuyện đã gọi nó bằng lệnh "/".

    python tests/run.py bao_khung_goc

Chuyện thật (chủ dự án báo 15/09): gõ "/quy-trinh" ở khung Trò chuyện thì trang nhảy hẳn sang
Cộng sự, việc chạy ở đó, và khung vừa rời đi không bao giờ biết kết quả ra sao. Nay mỗi lần
chạy xong (hoặc hỏng) đẩy một tin ngược về đúng khung đó, kèm link mở lại hội thoại đã làm việc.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import os
import tempfile
from pathlib import Path

_TMP = tempfile.mkdtemp(prefix="javis-goc-")
os.environ["JAVIS_STATE_DIR"] = _TMP
os.environ["JAVIS_SESSIONS_DB"] = str(Path(_TMP) / "conv.db")

import main  # noqa: E402

fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        fails.append(name)


store = main.get_store()
goc = store.create_session(brain=main._brain_key("brain"), engine="cli", channel="web")
phien_wf = store.create_session(brain=main._brain_key("brain"), engine="cli",
                                channel="workflow:viet-bai")


def tin_cuoi(sid):
    ds = store.get_messages(sid) or []
    return ds[-1]["content"] if ds else ""


ok = asyncio.run(main._bao_ve_khung_goc(goc, "brain", "workflow", "viet-bai", phien_wf, "BÀI 1"))
cuoi = tin_cuoi(goc)
check("day duoc tin ve khung goc", ok is True and bool(cuoi))
check("co ten loai va ket qua", "Quy trình" in cuoi and cuoi.rstrip().endswith("BÀI 1"))
check("co link mo dung cong su VA dung phien",
      f"(#cs=workflow:viet-bai:{phien_wf})" in cuoi)

# Không có khung gốc (mở thẳng trang Cộng sự) thì KHÔNG đẩy đi đâu cả: đẩy bừa về một phiên
# nào đó là nhét kết quả vào cuộc trò chuyện người dùng không hề gọi nó.
check("khong co khung goc thi khong day",
      asyncio.run(main._bao_ve_khung_goc("", "brain", "workflow", "viet-bai", phien_wf, "X")) is False)
check("ket qua rong thi khong day",
      asyncio.run(main._bao_ve_khung_goc(goc, "brain", "agent", "ai-do", phien_wf, "  ")) is False)
# Tự trỏ về chính mình = vòng lặp: phiên cộng sự nhận lại đúng tin nó vừa sinh ra.
check("khung goc trung phien dang chay thi khong day",
      asyncio.run(main._bao_ve_khung_goc(phien_wf, "brain", "workflow", "viet-bai", phien_wf, "X")) is False)

# Kết quả dài phải CẮT và nói là đã cắt - bản đủ nằm trong hội thoại mà link ở trên trỏ tới.
dai = "x" * (main.TRAN_BAO_KHUNG_GOC + 500)
asyncio.run(main._bao_ve_khung_goc(goc, "brain", "workflow", "viet-bai", phien_wf, dai))
cuoi = tin_cuoi(goc)
check("ket qua dai bi cat va noi ra la da cat",
      len(cuoi) < len(dai) and "còn nữa" in cuoi)

if fails:
    print("\nFAIL:", len(fails), fails)
    raise SystemExit(1)
print("\nOK - bao ve khung goc")
