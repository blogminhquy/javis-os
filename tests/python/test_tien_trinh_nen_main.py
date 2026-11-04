"""Phần nối của việc chạy nền vào main.py: báo xong đúng kênh, mở lượt nối tiếp, có trần (0.64.66).

    python tests/run.py tien_trinh_nen_main
"""
import os
import tempfile
import time

from _paths import ROOT, SERVER  # noqa: E402,F401

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-ttnm-"))
import asyncio  # noqa: E402

import main  # noqa: E402
import tien_trinh_nen as T  # noqa: E402

fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (f"  [{extra}]" if extra and not cond else ""))
    if not cond:
        fails.append(name)


bao = []


async def gia_notify(owner, text, **kw):
    bao.append((owner, text, kw))
    return True, ""

main._notify_owner = gia_notify

chay_tiep = []


async def runner(text, do_sau):
    chay_tiep.append((text, do_sau))

brain_root = tempfile.mkdtemp(prefix="javis-ttnm-brain-")
os.makedirs(os.path.join(brain_root, "exports"))
video = os.path.join(brain_root, "exports", "gioi-thieu.mp4")
open(video, "w").close()


def viec(**kw):
    v = {"id": "j1", "pgid": 1, "mo_ta": "ffmpeg -i in.mp4 out.mp4", "cwd": brain_root,
         "brain_root": brain_root, "chat_id": "web:s1", "bat_dau": time.time() - 250,
         "ket_thuc": time.time(), "trang_thai": "xong", "sau_khi_xong": "ghép tiếng, gửi video",
         "noi_tiep": True, "do_sau": 0, "file_moi": [video]}
    v.update(kw)
    return v


async def chay(v):
    await main._khi_tien_trinh_xong(v)
    await asyncio.sleep(0.05)      # lượt nối tiếp đi bằng create_task

main._NOI_TIEP_WEB["s1"] = runner

# 1. Xong + có lời dặn + khung chat web: báo và mở lượt nối tiếp
asyncio.run(chay(viec()))
check("báo xong về đúng khung chat đã giao", bao and bao[-1][0] == "web:s1")
kw = bao[-1][2] if bao else {}
check("báo xong mang thẻ việc chạy nền (kind job, done)",
      (kw.get("viec") or {}).get("kind") == "job" and (kw.get("viec") or {}).get("status") == "done")
check("báo xong có link file mới, đường dẫn tương đối trong brain",
      bool(bao) and "[gioi-thieu.mp4](exports/gioi-thieu.mp4)" in bao[-1][1], bao[-1][1] if bao else "")
check("báo xong nói thời gian chạy", bool(bao) and "4 phút" in bao[-1][1], bao[-1][1] if bao else "")
check("mở lượt nối tiếp đúng một lần", len(chay_tiep) == 1)
check("lượt nối tiếp mang lời dặn và độ sâu +1",
      bool(chay_tiep) and "Làm tiếp: ghép tiếng, gửi video" in chay_tiep[0][0] and chay_tiep[0][1] == 1)

# 2. Chạm trần độ sâu: chỉ báo, mời nhắn "làm tiếp"
bao.clear(); chay_tiep.clear()
asyncio.run(chay(viec(do_sau=T.TRAN_NOI_TIEP)))
check("chạm trần độ sâu thì không tự mở lượt nữa", chay_tiep == [])
check("chạm trần thì mời nhắn 'làm tiếp'", bool(bao) and "làm tiếp" in bao[-1][1])

# 3. Không dặn, không hứa: chỉ báo
bao.clear(); chay_tiep.clear()
asyncio.run(chay(viec(noi_tiep=False, sau_khi_xong="")))
check("không dặn không hứa thì chỉ báo, không mở lượt", len(bao) == 1 and chay_tiep == [])

# 4. Telegram: không có lượt nối tiếp tự động, mời nhắn "làm tiếp"
bao.clear(); chay_tiep.clear()
asyncio.run(chay(viec(chat_id="12345")))
check("Telegram: báo về đúng chat_id", bool(bao) and bao[-1][0] == "12345")
check("Telegram: không tự mở lượt, mời nhắn 'làm tiếp'",
      chay_tiep == [] and "làm tiếp" in bao[-1][1])

# 5. Bị dừng: báo 'đã dừng', không nối tiếp
bao.clear(); chay_tiep.clear()
asyncio.run(chay(viec(trang_thai="huy")))
check("bị dừng thì thẻ cancelled và không nối tiếp",
      (bao[-1][2].get("viec") or {}).get("status") == "cancelled" and chay_tiep == [])

# 6. Câu báo nhận theo dõi: không có gì chạy ngầm thì rỗng
cau = asyncio.run(main._nhan_nuoi_tien_trinh("chat:khong-co:1", "brain", "web:s9", "xong"))
check("không có gì chạy ngầm thì không báo gì", cau == "")

# 7. Khối xử lý Telegram không tự hứa làm tiếp
src = (SERVER / "main.py").read_text(encoding="utf-8")
check("Telegram nhận theo dõi với tu_lam_tiep=False", "tu_lam_tiep=False" in src)

# 8. A long chat turn (or a background job's follow-up) rings the bell when it ends (owner report 2026-11-04)
hom = []


async def gia_hom(owner, text, **kw):
    hom.append((owner, text, kw))
    return {"id": "i1"}

main._bo_vao_hom_thu = gia_hom
os.environ.pop("JAVIS_LONG_TURN_NOTIFY_S", None)
asyncio.run(main._bao_luot_dai_xong("s1", "brain", "chat:s1:1", "hi", "Hello", 12))
check("a short turn does not ring the bell", hom == [])
asyncio.run(main._bao_luot_dai_xong("s1", "brain", "chat:s1:2", "make the video",
                                    "**Video is ready**\n[video.mp4](exports/video.mp4)", 640))
check("a long turn leaves its answer in the bell of its own chat", bool(hom) and hom[-1][0] == "web:s1")
kw = hom[-1][2] if hom else {}
check("the notice pushes only where Javis is not on screen, once per turn",
      kw.get("push_if_away") is True and kw.get("dedup") == "turn:chat:s1:2")
check("the notice says how long it took", "10" in str(kw.get("label") or ""), kw.get("label"))
hom.clear()
asyncio.run(main._bao_luot_dai_xong("s1", "brain", "chat:s1:3", main.turn_done_notice.FOLLOWUP_HEAD + " ffmpeg",
                                    "Added the audio, here it is", 20))
check("a background job's follow-up rings however short", len(hom) == 1)

if fails:
    raise SystemExit(f"\nFAIL - test_tien_trinh_nen_main: {len(fails)} lỗi")
print("\nOK - test_tien_trinh_nen_main: tất cả pass")
