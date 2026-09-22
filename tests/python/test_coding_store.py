"""Sổ repo của trang Coding: thêm/xoá repo, ràng buộc phiên, worktree, điểm hồi.

    python tests/run.py coding_store      (KHÔNG mạng, cần git trên máy)

Bốn thứ file này canh, đều là loại hỏng lặng lẽ hoặc hỏng đắt:

1. **Thêm thư mục không phải repo git phải TỪ CHỐI ngay.** Nhận vào thì mọi thứ còn lại của
   trang (nhánh, worktree, điểm hồi) hỏng ở tận sau, xa chỗ gây lỗi, và người dùng không nối
   được hai đầu.

2. **Xoá repo KHÔNG được đụng đĩa.** Đây là kiểu mất mát không hoàn tác được. Test này là hàng
   rào cuối: ai đó thêm `shutil.rmtree` cho "sạch sẽ" là đỏ ngay.

3. **`cwd_cua_phien` phải suy biến êm.** Phiên chat thường trả "" (nơi gọi giữ cwd=brain);
   worktree bị xoá tay thì về lại repo chứ không ném lỗi giữa lượt chat.

4. **Rollback chỉ nhận điểm hồi CỦA CHÍNH phiên đó.** `git reset --hard` không hỏi lại và
   không hoàn tác được; nhận tag của phiên khác là một cú bấm nhầm kéo cả repo đi.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401  - nạp server/ vào sys.path
import os
import subprocess
import sys
import tempfile
from pathlib import Path

_STATE = tempfile.mkdtemp(prefix="javis-coding-")
os.environ["JAVIS_STATE_DIR"] = _STATE

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import coding_store  # noqa: E402

_fails = []


def check(ten, dieu_kien):
    print(("ok   " if dieu_kien else "FAIL ") + ten)
    if not dieu_kien:
        _fails.append(ten)


def git(args, cwd):
    subprocess.run(["git"] + args, cwd=cwd, check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def repo_moi(ten):
    d = tempfile.mkdtemp(prefix=f"javis-{ten}-")
    git(["init", "-q", "-b", "main"], d)
    git(["config", "user.email", "test@javis.local"], d)
    git(["config", "user.name", "Javis Test"], d)
    Path(d, "README.md").write_text("xin chao\n", encoding="utf-8")
    git(["add", "-A"], d)
    git(["commit", "-q", "-m", "khoi tao"], d)
    return d


co_git = True
try:
    subprocess.run(["git", "--version"], check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
except Exception:
    co_git = False

if not co_git:
    print("BỎ QUA: máy này chưa cài git")
    sys.exit(0)

REPO = repo_moi("repo")

# ---- 1. Thêm repo ----
khong_git = tempfile.mkdtemp(prefix="javis-khonggit-")
try:
    coding_store.add_repo(khong_git)
    check("thư mục không phải repo git bị từ chối", False)
except coding_store.LoiCoding as e:
    check("thư mục không phải repo git bị từ chối", "git" in str(e).lower())

try:
    coding_store.add_repo(str(Path(khong_git) / "khong-ton-tai"))
    check("đường dẫn không có thật bị từ chối", False)
except coding_store.LoiCoding:
    check("đường dẫn không có thật bị từ chối", True)

r = coding_store.add_repo(REPO, brain="b1")
check("thêm repo git thành công", bool(r.get("id")) and r["duong_dan"] == str(Path(REPO).resolve()))
check("tên mặc định lấy từ tên thư mục", r["ten"] == Path(REPO).name)
check("nhánh gốc đọc được từ git", r["nhanh_goc"] == "main")

r2 = coding_store.add_repo(REPO, brain="b1")
check("thêm lại cùng đường dẫn không tạo bản ghi thứ hai", r2["id"] == r["id"])
check("sổ chỉ có một repo", len(coding_store.list_repos("b1")) == 1)
check("lọc theo brain khác trả rỗng", coding_store.list_repos("b2") == [])

# ---- 2. Ràng buộc phiên ----
SID = "phien0123456789"
check("phiên chưa gắn gì thì cwd rỗng (chat thường giữ nguyên cwd=brain)",
      coding_store.cwd_cua_phien(SID) == "")
check("mức quyền mặc định là auto", coding_store.muc_quyen_cua_phien(SID) == "auto")

coding_store.dat_rang_buoc(SID, repo=r["id"])
check("gắn repo xong thì cwd là chính repo", coding_store.cwd_cua_phien(SID) == str(Path(REPO).resolve()))

try:
    coding_store.dat_rang_buoc(SID, muc_quyen="toan-quyen-nhe")
    check("mức quyền lạ bị từ chối", False)
except coding_store.LoiCoding:
    check("mức quyền lạ bị từ chối", True)

coding_store.dat_rang_buoc(SID, muc_quyen="full")
check("đổi mức quyền có hiệu lực", coding_store.muc_quyen_cua_phien(SID) == "full")

try:
    coding_store.dat_rang_buoc("phienkhac", repo="khong-co-id-nay")
    check("gắn repo không có trong sổ bị từ chối", False)
except coding_store.LoiCoding:
    check("gắn repo không có trong sổ bị từ chối", True)

# ---- 3. Worktree ----
wt = coding_store.tao_worktree(SID)
check("worktree được tạo", Path(wt["worktree"]).is_dir())
check("worktree mở NHÁNH MỚI chứ không checkout nhánh gốc",
      wt["nhanh"].startswith("javis/") and wt["nhanh"] != "main")
check("cwd của phiên chuyển sang worktree", coding_store.cwd_cua_phien(SID) == wt["worktree"])
check("nhánh gốc vẫn đang được checkout ở cây chính", coding_store.nhanh_hien_tai(REPO) == "main")

lai = coding_store.tao_worktree(SID)
check("gọi lần hai không tạo worktree thứ hai", lai.get("da_co") is True)

# Worktree còn sửa đổi chưa commit: gỡ phải TỪ CHỐI và nói rõ đang giữ ở đâu.
Path(wt["worktree"], "dang-lam-do.txt").write_text("viết dở", encoding="utf-8")
ra = coding_store.go_worktree(SID)
check("worktree còn việc dở thì không gỡ", ra.get("da_go") is False and ra.get("giu_tai"))
check("worktree vẫn còn trên đĩa", Path(wt["worktree"]).is_dir())

ra2 = coding_store.go_worktree(SID, ep=True)
check("gỡ được khi ép", ra2.get("da_go") is True)
check("gỡ xong thì cwd về lại repo", coding_store.cwd_cua_phien(SID) == str(Path(REPO).resolve()))

# ---- 4. Điểm hồi ----
d1 = coding_store.tao_diem_hoi(SID)
check("điểm hồi đầu tiên đánh số 1", d1["tag"].endswith("/1"))
Path(REPO, "README.md").write_text("đã sửa\n", encoding="utf-8")
git(["commit", "-qam", "sua"], REPO)
d2 = coding_store.tao_diem_hoi(SID)
check("điểm hồi thứ hai đánh số 2", d2["tag"].endswith("/2"))
check("sổ giữ cả hai mốc", len(coding_store.danh_sach_diem_hoi(SID)) == 2)

try:
    coding_store.rollback(SID, "javis/phienkhac/1")
    check("rollback bằng tag của phiên khác bị từ chối", False)
except coding_store.LoiCoding:
    check("rollback bằng tag của phiên khác bị từ chối", True)

coding_store.rollback(SID, d1["tag"])
check("rollback kéo nội dung file về đúng mốc",
      Path(REPO, "README.md").read_text(encoding="utf-8") == "xin chao\n")

# ---- 5. Xoá repo khỏi sổ KHÔNG đụng đĩa ----
check("xoá repo trả True", coding_store.remove_repo(r["id"]) is True)
check("sổ rỗng sau khi xoá", coding_store.list_repos("b1") == [])
check("MÃ NGUỒN TRÊN ĐĨA VẪN CÒN", Path(REPO, "README.md").is_file())
check("xoá lại id đã xoá trả False", coding_store.remove_repo(r["id"]) is False)
check("phiên trỏ vào repo đã xoá thì cwd rỗng, không ném lỗi",
      coding_store.cwd_cua_phien(SID) == "")

# ---- 6. Sổ hỏng không giết cả trang ----
coding_store.STORE_PATH.write_text("{ khong phai json", encoding="utf-8")
check("sổ hỏng đọc ra sổ rỗng thay vì ném lỗi", coding_store.list_repos() == [])
check("sổ hỏng được đổi tên để còn xem lại",
      coding_store.STORE_PATH.with_suffix(".json.hong").is_file())

print()
if _fails:
    print(f"FAIL {len(_fails)} test: " + ", ".join(_fails))
    sys.exit(1)
print("TẤT CẢ PASS")
