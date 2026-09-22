"""Sổ THƯ MỤC của trang Coding: thêm/bỏ thư mục, ràng buộc phiên, worktree, điểm hồi.

    python tests/run.py coding_store      (KHÔNG mạng, cần git trên máy)

Bốn thứ file này canh, đều là loại hỏng lặng lẽ hoặc hỏng đắt:

1. **Thư mục KHÔNG phải repo git vẫn nhận.** Bản 0.63.0 từ chối kèm câu "chạy git init trước
   đi"; chủ dự án chỉ ra đó là bắt người dùng làm việc vặt cho vừa mô hình dữ liệu của Javis.
   Nay git là thuộc tính ĐỌC RA, và ba thứ phụ thuộc git từ chối RIÊNG chúng kèm lời chỉ đường,
   chứ không chặn ở cửa vào.

2. **Bỏ thư mục KHÔNG được đụng đĩa.** Đây là kiểu mất mát không hoàn tác được. Test này là hàng
   rào cuối: ai đó thêm `shutil.rmtree` cho "sạch sẽ" là đỏ ngay.

3. **`cwd_cua_phien` phải suy biến êm.** Phiên chưa gắn thư mục trả "" (nơi gọi giữ cwd=brain,
   nên vào trang là chat được ngay); worktree bị xoá tay thì về lại thư mục gốc chứ không ném
   lỗi giữa lượt chat.

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

# ---- 1. Thêm thư mục ----
khong_git = tempfile.mkdtemp(prefix="javis-khonggit-")
tm_thuong = coding_store.them_thu_muc(khong_git, brain="b1")
check("THƯ MỤC THƯỜNG (không git) vẫn thêm được", bool(tm_thuong.get("id")))
check("và đọc ra đúng là không phải git", coding_store.la_git(khong_git) is False)
check("thư mục không git thì không đọc được nhánh", coding_store.nhanh_hien_tai(khong_git) == "")
check("và danh sách nhánh rỗng chứ không nổ", coding_store.danh_sach_nhanh(khong_git) == [])

try:
    coding_store.them_thu_muc(str(Path(khong_git) / "khong-ton-tai"))
    check("đường dẫn không có thật bị từ chối", False)
except coding_store.LoiCoding:
    check("đường dẫn không có thật bị từ chối", True)

try:
    coding_store.them_thu_muc("")
    check("đường dẫn rỗng bị từ chối", False)
except coding_store.LoiCoding:
    check("đường dẫn rỗng bị từ chối", True)

r = coding_store.them_thu_muc(REPO, brain="b1")
check("thêm thư mục có git thành công", bool(r.get("id")) and r["duong_dan"] == str(Path(REPO).resolve()))
check("tên mặc định lấy từ tên thư mục", r["ten"] == Path(REPO).name)
check("nhánh đọc LIVE từ git", coding_store.nhanh_hien_tai(REPO) == "main")

r2 = coding_store.them_thu_muc(REPO, brain="b1")
check("thêm lại cùng đường dẫn không tạo bản ghi thứ hai", r2["id"] == r["id"])
check("sổ có hai thư mục của brain b1", len(coding_store.danh_sach_thu_muc("b1")) == 2)
check("lọc theo brain khác trả rỗng", coding_store.danh_sach_thu_muc("b2") == [])

# ---- 2. Ràng buộc phiên ----
SID = "phien0123456789"
check("phiên chưa gắn gì thì cwd rỗng (vào trang là chat được ngay, cwd=brain)",
      coding_store.cwd_cua_phien(SID) == "")
check("mức quyền mặc định là auto", coding_store.muc_quyen_cua_phien(SID) == "auto")

# Thư mục thường: gắn được, chat được, chỉ ba thứ cần git là từ chối RIÊNG chúng.
coding_store.dat_rang_buoc(SID, thu_muc_id=tm_thuong["id"])
check("gắn thư mục thường thì cwd là chính nó",
      coding_store.cwd_cua_phien(SID) == str(Path(khong_git).resolve()))
for ten_viec, ham in (("điểm hồi", lambda: coding_store.tao_diem_hoi(SID)),
                      ("worktree", lambda: coding_store.tao_worktree(SID))):
    try:
        ham()
        check(f"{ten_viec} trên thư mục không git bị từ chối", False)
    except coding_store.LoiCoding as e:
        check(f"{ten_viec} trên thư mục không git bị từ chối, kèm cách khắc phục",
              "git init" in str(e))

coding_store.dat_rang_buoc(SID, thu_muc_id=r["id"])
check("gắn thư mục có git thì cwd là chính nó", coding_store.cwd_cua_phien(SID) == str(Path(REPO).resolve()))

try:
    coding_store.dat_rang_buoc(SID, muc_quyen="toan-quyen-nhe")
    check("mức quyền lạ bị từ chối", False)
except coding_store.LoiCoding:
    check("mức quyền lạ bị từ chối", True)

coding_store.dat_rang_buoc(SID, muc_quyen="full")
check("đổi mức quyền có hiệu lực", coding_store.muc_quyen_cua_phien(SID) == "full")

try:
    coding_store.dat_rang_buoc("phienkhac", thu_muc_id="khong-co-id-nay")
    check("gắn thư mục không có trong sổ bị từ chối", False)
except coding_store.LoiCoding:
    check("gắn thư mục không có trong sổ bị từ chối", True)

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

# ---- 5. Đổi thư mục giữa chừng ----
# 0.63.0 nhét id thư mục vào TÊN KÊNH của phiên nên đổi thư mục là phiên vẫn nằm dưới thư mục
# cũ. Nay thư mục chỉ là ràng buộc, đổi được, và worktree của thư mục cũ phải bị buông ra.
coding_store.dat_rang_buoc(SID, thu_muc_id=r["id"])
coding_store.tao_worktree(SID)
check("đang có worktree", bool(coding_store.rang_buoc(SID).get("worktree")))
coding_store.dat_rang_buoc(SID, thu_muc_id=tm_thuong["id"])
check("đổi thư mục thì buông worktree cũ", coding_store.rang_buoc(SID).get("worktree") == "")
check("và cwd theo thư mục mới",
      coding_store.cwd_cua_phien(SID) == str(Path(khong_git).resolve()))
coding_store.dat_rang_buoc(SID, thu_muc_id="")
check("gỡ hẳn thư mục thì cwd rỗng, phiên vẫn chat được", coding_store.cwd_cua_phien(SID) == "")

# ---- 6. Bỏ thư mục khỏi sổ KHÔNG đụng đĩa ----
check("bỏ thư mục trả True", coding_store.bo_thu_muc(r["id"]) is True)
check("MÃ NGUỒN TRÊN ĐĨA VẪN CÒN", Path(REPO, "README.md").is_file())
check("bỏ lại id đã bỏ trả False", coding_store.bo_thu_muc(r["id"]) is False)

# ---- 7. Khối prompt gắn vào lượt chat ----
coding_store.dat_rang_buoc(SID, thu_muc_id=tm_thuong["id"], muc_quyen="auto")
k = coding_store.khoi_prompt(SID)
check("khối prompt nói rõ thư mục làm việc", str(Path(khong_git).resolve()) in k)
check("mức Tự động nói KHÔNG commit/push/deploy", "KHÔNG commit" in k)
coding_store.dat_rang_buoc(SID, muc_quyen="suggest")
k2 = coding_store.khoi_prompt(SID)
check("chế độ Plan BẢO engine trả về kế hoạch rồi dừng",
      "KHÔNG sửa file" in k2 and "KẾ HOẠCH" in k2.upper())
coding_store.dat_rang_buoc(SID, muc_quyen="full")
check("mức Toàn quyền nói rõ được commit/push/deploy", "Toàn quyền" in coding_store.khoi_prompt(SID))
coding_store.dat_rang_buoc(SID, thu_muc_id="")
check("phiên chưa gắn thư mục thì KHÔNG chèn khối nào vào prompt",
      coding_store.khoi_prompt(SID) == "")

# ---- 8. Di trú sổ 0.63.0 (khoá `repos` / ràng buộc `repo`) ----
import json as _json
coding_store.STORE_PATH.write_text(_json.dumps({
    "version": 1,
    "repos": [{"id": "cu1", "ten": "du-an-cu", "duong_dan": REPO, "brain": "b1"}],
    "phien": {"phiencu": {"repo": "cu1", "muc_quyen": "full"}},
}, ensure_ascii=False), encoding="utf-8")
ds_cu = coding_store.danh_sach_thu_muc("b1")
check("sổ 0.63.0 đọc lên vẫn thấy thư mục cũ", len(ds_cu) == 1 and ds_cu[0]["id"] == "cu1")
check("ràng buộc cũ (`repo`) di trú sang `thu_muc`",
      coding_store.rang_buoc("phiencu").get("thu_muc") == "cu1")
check("và phiên cũ vẫn ra đúng cwd", coding_store.cwd_cua_phien("phiencu") == str(Path(REPO).resolve()))

# ---- 9. Sổ hỏng không giết cả trang ----
coding_store.STORE_PATH.write_text("{ khong phai json", encoding="utf-8")
check("sổ hỏng đọc ra sổ rỗng thay vì ném lỗi", coding_store.danh_sach_thu_muc() == [])
check("sổ hỏng được đổi tên để còn xem lại",
      coding_store.STORE_PATH.with_suffix(".json.hong").is_file())

print()
if _fails:
    print(f"FAIL {len(_fails)} test: " + ", ".join(_fails))
    sys.exit(1)
print("TẤT CẢ PASS")
