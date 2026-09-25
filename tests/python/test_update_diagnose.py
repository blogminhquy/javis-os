"""Cập nhật xong mà phiên bản không đổi thì phải NÓI RA vì sao.

    python tests/run.py update_diagnose

Lỗi thật chủ repo gặp trên máy Windows đang chạy v0.9.293:

    "Server lên nhưng phiên bản chưa đổi (pull chưa áp?). Xem update.log."

Câu đó biết có chuyện bất thường mà không nói ra chuyện gì, rồi đẩy người dùng đi đọc một
file log mà bản Windows/Docker gần như không với tới được. Cùng một kiểu hỏng với dải báo đỏ
"mở terminal gõ /login": báo lỗi mà không dẫn được tới việc cần làm.

Điểm mấu chốt: `git pull` TRẢ VỀ 0 (nếu nó lỗi thì đã rơi nhánh pull_failed từ trước), nên
nguyên nhân gần như luôn là "Already up to date" - máy đang theo dõi một nhánh KHÔNG có bản
mới. Đó là thông tin chẩn đoán được, không cần đoán.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import os
import sys
import tempfile

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-upd-"))

import updater  # noqa: E402

_fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)


class _R:
    def __init__(self, out="", rc=0):
        self.stdout, self.stderr, self.returncode = out, "", rc


def _gia_lap(nhanh, upstream_rc=0, upstream=""):
    """Thay updater.run để mô phỏng trạng thái git, không đụng repo thật."""
    def fake(cmd):
        if cmd[:3] == ["git", "rev-parse", "--abbrev-ref"] and cmd[-1] == "HEAD":
            return _R(nhanh)
        if "@{u}" in cmd:
            return _R(upstream, upstream_rc)
        return _R("")
    return fake


_that = updater.run

# ---- 1. Ca hay gặp nhất: đứng nhánh khác, git báo đã mới nhất ----
updater.run = _gia_lap("claude/mot-nhanh-nao-do", 0, "origin/claude/mot-nhanh-nao-do")
_msg = updater.chan_doan_pull("Already up to date.")
check("nêu rõ đang đứng ở nhánh nào", "claude/mot-nhanh-nao-do" in _msg)
check("nói bản mới nằm ở main", "main" in _msg)
check("đưa ra LỆNH cụ thể để sửa, không nói chung chung",
      "git checkout main" in _msg)

# ---- 2. Nhánh không theo dõi gì: git không có gì để tải ----
updater.run = _gia_lap("main", 128, "")
_msg = updater.chan_doan_pull("Already up to date.")
check("nhận ra nhánh chưa theo dõi remote", "không theo dõi" in _msg)
check("và đưa lệnh set upstream", "--set-upstream-to=origin/main" in _msg)

# ---- 3. Đang ở main, theo dõi đúng, mà version vẫn không đổi ----
# Gần như chắc chắn là bản đóng gói sẵn (Docker) chứ không chạy từ mã nguồn.
updater.run = _gia_lap("main", 0, "origin/main")
_msg = updater.chan_doan_pull("Already up to date.")
check("nghi đúng hướng: bản đóng gói sẵn", "Docker" in _msg or "image" in _msg)

# ---- 4. detached HEAD ----
updater.run = _gia_lap("HEAD", 128, "")
_msg = updater.chan_doan_pull("You are in 'detached HEAD' state.")
check("nhận ra detached HEAD", "detached" in _msg.lower())
check("và đưa lệnh thoát ra", "git checkout main" in _msg)

# ---- 5. Trường hợp khác: vẫn phải nêu ngữ cảnh, không nói trống không ----
updater.run = _gia_lap("main", 0, "origin/main")
_msg = updater.chan_doan_pull("Updating abc123..def456\nFast-forward")
check("ca lạ vẫn nêu tên nhánh", "main" in _msg)
check("ca lạ không nổ", isinstance(_msg, str) and len(_msg) > 20)

# Không bao giờ được trả về câu rỗng: câu rỗng là quay lại đúng lỗi cũ.
for _out in ("", None, "   "):
    updater.run = _gia_lap("main", 0, "origin/main")
    check(f"đầu vào {_out!r} vẫn cho ra lời giải thích",
          len(updater.chan_doan_pull(_out) or "") > 20)

updater.run = _that

# ---- 6. Thông báo cuối cùng phải nêu CẢ HAI phiên bản ----
_src = (ROOT / "server" / "updater.py").read_text(encoding="utf-8")
check("thông báo lỗi nêu phiên bản đang chạy và phiên bản đích",
      'f"Vẫn đang chạy {current}, chưa lên {target}.' in _src)
check("và đính kèm chẩn đoán chứ không bảo đi đọc log",
      "chan_doan_pull(pull.stdout" in _src)
# Câu cũ còn xuất hiện trong docstring (trích lại để giải thích), nên chỉ được kiểm ở chỗ
# THẬT SỰ ghi thông báo cho người dùng.
_ghi = _src[_src.find('if outcome == "version_mismatch":'):][:600]
check("câu cũ mơ hồ không còn ở chỗ ghi thông báo",
      "(pull chưa áp?)" not in _ghi)
check("chỗ ghi thông báo có dùng chẩn đoán", "ly_do" in _ghi)

# ============================================================
# 7. `git pull` CHẾT HẲN thì cũng phải nói bằng tiếng người
# ============================================================
# Lỗi thật chủ dự án gặp trên máy mình 15/09, nguyên văn những gì hiện ra:
#
#   hint: Diverging branches can't be fast-forwarded, you need to either:
#   hint:   git merge --no-ff ... or: git rebase
#   fatal: Not possible to fast-forward, aborting.
#
# Nguyên nhân: máy đang đứng trên một nhánh phụ cũ (feat/...) chứ không phải main, và nhánh đó
# đã rẽ khác đường với bản của nó trên máy chủ. Git nói đúng, nhưng nói với lập trình viên.
_DIVERGE = ("hint: Diverging branches can't be fast-forwarded, you need to either:\n"
            "hint:   git merge --no-ff\nfatal: Not possible to fast-forward, aborting.")

updater.run = _gia_lap("feat/cong-su-cay-thu-muc", 0, "origin/feat/cong-su-cay-thu-muc")
_msg = updater.chan_doan_pull_hong(_DIVERGE)
check("rẽ nhánh + đứng nhầm nhánh: gọi tên nhánh đang đứng",
      "feat/cong-su-cay-thu-muc" in _msg)
check("nói rõ đó không phải nhánh main", "không phải nhánh main" in _msg)
check("đưa LỆNH cụ thể để về đúng chỗ", "git checkout main" in _msg)
check("không ném lời git thô ra màn hình", "fast-forward" not in _msg and "hint:" not in _msg)

# Đang ở ĐÚNG main mà vẫn rẽ đôi: lời khuyên phải khác hẳn - ở đây không checkout đi đâu được.
updater.run = _gia_lap("main", 0, "origin/main")
_msg = updater.chan_doan_pull_hong(_DIVERGE)
check("main rẽ đôi: chỉ cách lấy lại đúng bản máy chủ", "reset --hard origin/main" in _msg)
check("và nói rõ cái giá: bỏ commit riêng", "BỎ commit riêng" in _msg)

# Mấy ca còn lại: mỗi ca một lời khuyên KHÁC nhau, không phải một câu chung chung.
updater.run = _gia_lap("main", 128, "")
check("chưa theo dõi remote", "chưa theo dõi" in updater.chan_doan_pull_hong("There is no tracking information for the current branch."))
updater.run = _gia_lap("HEAD", 128, "")
check("detached HEAD", "detached" in updater.chan_doan_pull_hong("You are not currently on a branch.").lower())
updater.run = _gia_lap("main", 0, "origin/main")
check("mất mạng", "mạng" in updater.chan_doan_pull_hong("fatal: unable to access 'https://github.com/...': Could not resolve host: github.com"))
check("sửa đổi cục bộ chặn đường", "git stash" in updater.chan_doan_pull_hong("error: Your local changes to the following files would be overwritten by merge:"))
# Lỗi lạ hoắc trên ĐÚNG nhánh main: thà trả rỗng (để nơi gọi in lời git thô) còn hơn bịa ra
# một nguyên nhân sai.
check("lỗi lạ trên main thì không bịa nguyên nhân",
      updater.chan_doan_pull_hong("fatal: một lỗi chưa từng gặp") == "")


# Vụ 25/09/2026 trên máy Mac: updater tải origin/main rồi `git merge`, và merge chết vì
# commit sửa riêng trên nhánh máy đụng đúng dòng bản mới cũng sửa. Chẩn đoán cũ không nhận ra
# chữ CONFLICT, rơi xuống câu mặc định "không phải nhánh main, chạy git checkout main" - vừa
# sai nguyên nhân, vừa xui người dùng bỏ nhánh có 12 commit riêng chưa lên main.
_CONFLICT = ("Auto-merging dashboard/app.js\n"
             "CONFLICT (content): Merge conflict in dashboard/app.js\n"
             "Auto-merging dashboard/style.css\n"
             "CONFLICT (content): Merge conflict in dashboard/style.css\n"
             "Automatic merge failed; fix conflicts and then commit the result.")
updater.run = _gia_lap("fix/chat-ime-enter-residue", 0, "fork/fix/chat-ime-enter-residue")
_msg = updater.chan_doan_pull_hong(_CONFLICT)
check("xung đột merge: nói đúng là xung đột", "xung đột" in _msg.lower())
check("xung đột merge: gọi tên đúng file vướng",
      "dashboard/app.js" in _msg and "dashboard/style.css" in _msg)
check("xung đột merge: KHÔNG xui checkout main (mất commit riêng)", "checkout main" not in _msg)
check("xung đột merge: nói rõ code đang chạy giữ nguyên", "giữ nguyên" in _msg)
updater.run = _gia_lap("main", 0, "origin/main")
check("xung đột merge ngay trên main cũng nói là xung đột",
      "xung đột" in updater.chan_doan_pull_hong(_CONFLICT).lower())

updater.run = _that

_hong = _src[_src.find("pull = run([\"git\", \"pull\", \"--ff-only\"])"):][:1200]
check("nhánh pull hỏng có gọi chẩn đoán", "chan_doan_pull_hong(" in _hong)
check("và ưu tiên lời giải thích hơn lời git thô", "ly_do + " in _hong)

print()
if _fails:
    print(f"THẤT BẠI {len(_fails)}: {_fails}")
    sys.exit(1)
print("OK - test_update_diagnose: tất cả pass")
