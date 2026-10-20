"""Tiến trình nền của terminal engine API: bật, xem, chờ, dừng, dọn (0.256.0).

    python tests/run.py coding_process

Dev server và lệnh build dài không thể chạy tiền cảnh trong một lượt chat. Phải giữ:
  - Dừng là dừng CẢ NHÓM (dev server hay đẻ tiến trình con; giết mỗi cha là để con mồ côi).
  - Có trần số tiến trình mỗi phiên.
  - Xoá phiên thì mọi tiến trình nền của nó chết theo, thư mục trạng thái bị dọn.
  - Phiên này không thấy, không dừng được tiến trình của phiên khác.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import os
import sys
import tempfile
import time
from pathlib import Path

_TMP = tempfile.mkdtemp(prefix="javis-process-")
os.environ["JAVIS_STATE_DIR"] = _TMP

import coding_terminal as ct  # noqa: E402

_fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)


def ma(ra):
    return next(w for w in ra.replace(",", " ").replace("(", " ").split() if w.startswith("proc_"))


def song(pid):
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


if os.name == "nt" or not ct._git_bash():
    print("bỏ qua: tiến trình nền thật cần bash (Windows CI)")
    print("OK - test_coding_process: bỏ qua trên máy không có bash")
    sys.exit(0)

WS = Path(_TMP) / "du-an"
WS.mkdir(parents=True)
G = [str(WS.resolve())]

# ---- 1. Bật, chờ, đọc log ----
ra = ct.chay_nen("for i in 1 2 3; do echo nhip $i; sleep 0.2; done", "s1", G)
check("bật nền trả mã proc_", "proc_" in ra and "javis_process" in ra)
p1 = ma(ra)
ra = ct.quan_ly("wait", "s1", p1, timeout=10)
check("wait chờ tới khi xong, kèm mã thoát", "đã xong (exit=0)" in ra and "nhip 3" in ra)
ra = ct.quan_ly("log", "s1", p1, limit=2)
check("log lấy N dòng cuối", "nhip 3" in ra and "nhip 1" not in ra)
ra = ct.quan_ly("log", "s1", p1, offset=1, limit=1)
check("log theo offset", "nhip 2" in ra and "nhip 3" not in ra)
check("nhận tiền tố duy nhất của mã", "đã xong" in ct.quan_ly("poll", "s1", p1[:10]))

# ---- 2. Dừng cả nhóm ----
ra = ct.chay_nen("sleep 300 & sleep 300 & wait", "s1", G)
p2 = ma(ra)
time.sleep(0.5)
tt = ct._NEN[p2]
nhom = tt.p.pid
ra = ct.quan_ly("kill", "s1", p2)
check("kill báo đã dừng", ra.startswith("Đã dừng"))
time.sleep(0.5)


def thanh_vien_song(pgid):
    """Tiến trình còn CHẠY trong nhóm (bỏ qua zombie: trong container, init không phải lúc nào
    cũng gặt con mồ côi, nhưng zombie là đã chết). Dùng /proc; máy không có /proc thì None."""
    if not Path("/proc").is_dir():
        return None
    ra = []
    for d in Path("/proc").iterdir():
        if not d.name.isdigit():
            continue
        try:
            st = (d / "stat").read_text()
        except OSError:
            continue
        sau = st[st.rindex(")") + 2:].split()
        if int(sau[2]) == pgid and sau[0] != "Z":
            ra.append(int(d.name))
    return ra


_con = thanh_vien_song(nhom)
check("kill giết cả nhóm, không để con mồ côi", _con is None or _con == [])

# ---- 3. Cách ly giữa phiên ----
ra = ct.chay_nen("sleep 300", "s2", G)
p3 = ma(ra)
check("phiên khác không thấy tiến trình", p3 not in ct.quan_ly("list", "s1"))
check("phiên khác không dừng được", ct.quan_ly("kill", "s1", p3).startswith("ERROR"))
check("action sai thì nói rõ", ct.quan_ly("abc", "s2", p3).startswith("ERROR"))

# ---- 4. Trần mỗi phiên ----
cu = ct.NEN_MOI_PHIEN
ct.NEN_MOI_PHIEN = 2
ct.chay_nen("sleep 300", "s3", G)
ct.chay_nen("sleep 300", "s3", G)
check("quá trần tiến trình mỗi phiên thì từ chối", ct.chay_nen("sleep 300", "s3", G).startswith("ERROR"))
ct.NEN_MOI_PHIEN = cu
check("rào cứng cũng áp cho chạy nền", ct.chay_nen("sudo sleep 1", "s3", G).startswith("ERROR"))

# ---- 5. Xoá phiên thì dọn ----
pids = [v.p.pid for v in ct._NEN.values() if v.sid in ("s2", "s3")]
ct.don_phien("s2")
ct.don_phien("s3")
time.sleep(0.5)
check("xoá phiên: mọi tiến trình nền của phiên chết theo", not any(song(p) for p in pids))
check("xoá phiên: thư mục trạng thái bị dọn", not (ct.THU_MUC / "s2").exists())
check("xoá phiên: không còn trong sổ", not any(v.sid in ("s2", "s3") for v in ct._NEN.values()))

print()
if _fails:
    print(f"THẤT BẠI {len(_fails)}: {_fails}")
    sys.exit(1)
print("OK - test_coding_process: tất cả pass")
