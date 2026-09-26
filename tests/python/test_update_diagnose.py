"""Human-readable diagnosis for the release fetch/merge updater."""
from _paths import ROOT, SERVER  # noqa: E402,F401
import os
import sys
import tempfile

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-upd-"))
import updater  # noqa: E402

fails = []


def check(name, condition):
    print(("ok   " if condition else "FAIL ") + name)
    if not condition:
        fails.append(name)


message = updater.chan_doan_pull("Already up to date.")
check("đã mới nhất: nêu đúng nguồn phát hành chính thức",
      "github.com/blogminhquy/javis-os.git/main" in message)
check("đã mới nhất: hướng dẫn Docker nếu cần", "Docker" in message)
check("không khuyên bỏ nhánh riêng", "checkout main" not in message and "reset --hard" not in message)

message = updater.chan_doan_pull("Merge made by the 'ort' strategy.")
check("merge rồi mà VERSION không tăng: nói rõ phiên bản", "VERSION" in message)
for output in ("", None, "   "):
    check("đầu vào rỗng vẫn có chẩn đoán", bool(updater.chan_doan_pull(output)))

conflict = ("Auto-merging dashboard/app.js\n"
            "CONFLICT (content): Merge conflict in dashboard/app.js\n"
            "CONFLICT (content): Merge conflict in dashboard/style.css\n"
            "Automatic merge failed; fix conflicts and then commit the result.")
message = updater.chan_doan_pull_hong(conflict, nhanh="fix/local", theo_doi="fork/fix/local")
check("xung đột: gọi tên file", "dashboard/app.js" in message and "dashboard/style.css" in message)
check("xung đột: xác nhận đã hủy merge", "đã hủy" in message)
check("xung đột: không khuyên bỏ commit riêng", "checkout main" not in message and "reset --hard" not in message)
message_unsafe = updater.chan_doan_pull_hong(conflict, merge_aborted=False)
check("hủy merge thất bại: không khẳng định code giữ nguyên", "Chưa hủy được" in message_unsafe)

check("mất mạng: báo đúng nguyên nhân",
      "mạng" in updater.chan_doan_pull_hong(
          "fatal: unable to access: Could not resolve host: github.com"))
check("GitHub từ chối quyền: báo đúng nguyên nhân",
      "quyền" in updater.chan_doan_pull_hong("fatal: Authentication failed"))
check("file cục bộ chặn merge: hướng dẫn kiểm tra",
      "git status" in updater.chan_doan_pull_hong(
          "error: Your local changes would be overwritten by merge"))
check("lỗi lạ không bịa nguyên nhân",
      updater.chan_doan_pull_hong("fatal: một lỗi chưa từng gặp") == "")

os.environ["JAVIS_UPDATE_REMOTE"] = "some-fork"
os.environ["JAVIS_UPDATE_BRANCH"] = "stable"
check("nút cập nhật luôn dùng cùng nguồn với /version",
      updater.release_source() == ("https://github.com/blogminhquy/javis-os.git", "main"))
os.environ.pop("JAVIS_UPDATE_REMOTE", None)
os.environ.pop("JAVIS_UPDATE_BRANCH", None)

if fails:
    print(f"THẤT BẠI {len(fails)}: {fails}")
    sys.exit(1)
print("OK - test_update_diagnose: tất cả pass")
