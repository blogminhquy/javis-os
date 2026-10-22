"""Mốc khôi phục tự động và Hoàn tác an toàn của phiên Coding (0.256.0).

    python tests/run.py coding_checkpoint

Bốn lời hứa:
  - Tạo mốc KHÔNG chạm vào repo của người dùng: không đổi index, không thêm commit, ref, tag,
    stash nào vào `.git` của họ. Chạy được cả ở thư mục không phải git.
  - Mỗi lượt tối đa một mốc cho mỗi thư mục.
  - Hoàn tác an toàn trả lại file model đã đụng, GIỮ file người dùng tự sửa sau lần cuối model
    làm việc, và chụp trạng thái hiện tại trước khi trả (hoàn tác được cả lần hoàn tác).
  - Thư mục quá lớn hay là gốc ổ đĩa thì không chụp, và nói lý do thay vì treo.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

_TMP = tempfile.mkdtemp(prefix="javis-checkpoint-")
os.environ["JAVIS_STATE_DIR"] = _TMP

import coding_checkpoint as cc  # noqa: E402

_fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)


if not shutil.which("git"):
    print("bỏ qua: máy không có git")
    print("OK - test_coding_checkpoint: bỏ qua trên máy không có git")
    sys.exit(0)


def git(ws, *args):
    return subprocess.run(["git", "-C", str(ws)] + list(args), capture_output=True, text=True).stdout


WS = Path(_TMP) / "du-an"
WS.mkdir()
(WS / "a.py").write_text("A1\n", encoding="utf-8")
(WS / "b.py").write_text("B1\n", encoding="utf-8")
(WS / "node_modules").mkdir()
(WS / "node_modules" / "rac.js").write_text("x", encoding="utf-8")
git(WS, "init", "-q")
git(WS, "-c", "user.email=a@b", "-c", "user.name=a", "add", "a.py")
git(WS, "-c", "user.email=a@b", "-c", "user.name=a", "commit", "-q", "-m", "dau")
truoc = (git(WS, "status", "--porcelain"), git(WS, "rev-parse", "HEAD"), git(WS, "for-each-ref"),
         git(WS, "stash", "list"), (WS / ".git" / "index").read_bytes())

# ---- 1. Tạo mốc, một lần mỗi lượt ----
cc.luot_moi("s")
check("tạo mốc lần đầu không báo lỗi", cc.tao_neu_can("s", str(WS), "thử") == "")
cc.tao_neu_can("s", str(WS), "lần hai cùng lượt")
check("cùng lượt chỉ một mốc", len(cc.danh_sach("s")) == 1)
sau = (git(WS, "status", "--porcelain"), git(WS, "rev-parse", "HEAD"), git(WS, "for-each-ref"),
       git(WS, "stash", "list"), (WS / ".git" / "index").read_bytes())
check("không chạm vào repo người dùng (status, HEAD, ref, stash, index)", truoc == sau)

# ---- 2. Model sửa, người dùng sửa, rồi hoàn tác an toàn ----
mid = cc.danh_sach("s")[0]["id"]
(WS / "a.py").write_text("A2 model\n", encoding="utf-8")
cc.ghi_nhan_hoat_dong("s", WS / "a.py")
(WS / "moi.py").write_text("model tạo\n", encoding="utf-8")
(WS / "b.py").unlink()
cc.ghi_nhan_hoat_dong("s")
time.sleep(2.2)
(WS / "nguoi.py").write_text("người dùng tạo\n", encoding="utf-8")
os.utime(WS / "nguoi.py", (time.time() + 5, time.time() + 5))
td = {x["file"]: x["trang_thai"] for x in cc.thay_doi("s", mid)["file"]}
check("thấy file sửa, file mới, file xoá", td.get("a.py") == "M" and td.get("moi.py") == "A" and td.get("b.py") == "D")
check("không theo dõi node_modules", not any(k.startswith("node_modules") for k in td))
check("diff một file", "-A1" in cc.diff_file("s", mid, "a.py") and "+A2 model" in cc.diff_file("s", mid, "a.py"))
kq = cc.khoi_phuc("s", mid)
check("trả lại file model sửa", (WS / "a.py").read_text() == "A1\n")
check("xoá file model tạo", not (WS / "moi.py").exists())
check("khôi phục file bị xoá", (WS / "b.py").read_text() == "B1\n")
check("giữ file người dùng tạo sau lần cuối model làm việc", (WS / "nguoi.py").exists()
      and "nguoi.py" in kq["giu_nguyen"])
check("chụp trạng thái trước khi hoàn tác", bool(kq["moc_truoc_khi_hoan_tac"]))

# ---- 3. Hoàn tác cả lần hoàn tác ----
kq2 = cc.khoi_phuc("s", kq["moc_truoc_khi_hoan_tac"], an_toan=False)
check("hoàn tác lần hoàn tác đưa sửa của model trở lại", (WS / "a.py").read_text() == "A2 model\n"
      and (WS / "moi.py").exists())
kq3 = cc.khoi_phuc("s", mid, chi_file="a.py")
check("khôi phục đúng một file", (WS / "a.py").read_text() == "A1\n" and (WS / "moi.py").exists()
      and kq3["da_tra"] == ["a.py"])

# ---- 4. Không phải git vẫn chụp được ----
TM = Path(_TMP) / "thu-muc-thuong"
TM.mkdir()
(TM / "x.txt").write_text("1", encoding="utf-8")
cc.luot_moi("s2")
check("thư mục không phải git vẫn tạo mốc", cc.tao_neu_can("s2", str(TM)) == "" and len(cc.danh_sach("s2")) == 1)

# ---- 5. Từ chối có lý do ----
cu = cc.FILE_TOI_DA_SO
cc.FILE_TOI_DA_SO = 3
for i in range(5):
    (TM / f"f{i}.txt").write_text(str(i), encoding="utf-8")
cc.luot_moi("s2")
canh_bao = cc.tao_neu_can("s2", str(TM))
check("thư mục quá nhiều file thì không chụp, nói lý do", "hơn" in canh_bao and "file" in canh_bao)
cc.FILE_TOI_DA_SO = cu
check("thư mục home thì không chụp", "home" in cc._quet(str(Path.home()))[2])
try:
    cc.thay_doi("s", "khong-co")
    check("mốc lạ bị từ chối", False)
except cc.LoiMoc:
    check("mốc lạ bị từ chối", True)
try:
    cc.thay_doi("s2", mid)
    check("mốc của phiên khác bị từ chối", False)
except cc.LoiMoc:
    check("mốc của phiên khác bị từ chối", True)

# ---- 6. Giữ tối đa GIU_MOC mốc mỗi thư mục, xoá phiên thì bỏ hết ----
cu = cc.GIU_MOC
cc.GIU_MOC = 3
for i in range(5):
    cc.luot_moi("s4")
    cc.tao_neu_can("s4", str(TM))
check("chỉ giữ GIU_MOC mốc gần nhất", len(cc.danh_sach("s4")) == 3)
cc.GIU_MOC = cu
cc.don_phien("s4")
check("xoá phiên thì bỏ mọi mốc của nó", cc.danh_sach("s4") == [])

print()
if _fails:
    print(f"THẤT BẠI {len(_fails)}: {_fails}")
    sys.exit(1)
print("OK - test_coding_checkpoint: tất cả pass")
