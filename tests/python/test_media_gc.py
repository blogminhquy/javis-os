"""Test media_gc (dọn media quá hạn trong vùng cache của brain). Chạy tay / CI:

    python tests/run.py media_gc

plan_deletions là hàm THUẦN nên phần lớn test không chạm đĩa; phần quét/xoá dùng thư mục tạm.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401  - nạp server/ vào sys.path
import sys
import time

import media_gc   # noqa: E402

_fails = []


def check(name, cond):
    print(("ok  " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)


NOW = 1_800_000_000.0
DAY = 86400.0
MB = 1024 * 1024


def muc(path, mb, tuoi_ngay):
    """Một mục (path, size, mtime) với mtime cách NOW đúng tuoi_ngay ngày."""
    return (path, int(mb * MB), NOW - tuoi_ngay * DAY)


# ---- 1. Còn mới và tổng dưới trần: không xoá gì ----
r = media_gc.plan_deletions([muc("a.png", 1, 1), muc("b.png", 2, 5)], NOW, 30, 300)
check("moi + duoi tran -> khong xoa gi", r == [])

# ---- 2. Quá hạn tuổi thì xoá, trong hạn thì giữ ----
r = media_gc.plan_deletions([muc("cu.png", 1, 40), muc("moi.png", 1, 5)], NOW, 30, 300)
check("qua han tuoi -> chi xoa file cu", r == ["cu.png"])

# ---- 3. Vượt trần dù mọi file còn trong hạn: xoá từ cũ tới mới, dừng đúng lúc ----
r = media_gc.plan_deletions(
    [muc("x3.png", 200, 3), muc("x2.png", 200, 2), muc("x1.png", 200, 1)], NOW, 30, 300)
check("vuot tran -> xoa cu truoc, dung khi du", r == ["x3.png", "x2.png"])

# ---- 4. Vừa quá hạn vừa vượt trần: cộng dồn, không đếm trùng ----
r = media_gc.plan_deletions(
    [muc("cu.png", 10, 40), muc("y2.png", 200, 3), muc("y1.png", 200, 1)], NOW, 30, 300)
check("qua han + vuot tran -> cong don, khong trung",
      r == ["cu.png", "y2.png"] and len(r) == len(set(r)))

# ---- 5. File .md không bao giờ bị xoá ----
r = media_gc.plan_deletions([muc("ghi-chu.md", 400, 99), muc("anh.png", 1, 40)], NOW, 30, 300)
check("chua file .md", r == ["anh.png"])

# ---- 6. Tắt từng luật bằng 0 / số âm ----
check("max_age_days=0 -> tat luat tuoi",
      media_gc.plan_deletions([muc("cu.png", 1, 999)], NOW, 0, 300) == [])
check("max_mb=0 -> tat luat tran",
      media_gc.plan_deletions([muc("to.png", 999, 1)], NOW, 30, 0) == [])
check("tat ca hai -> khong xoa gi",
      media_gc.plan_deletions([muc("cu-va-to.png", 999, 999)], NOW, -1, -1) == [])

# ---- 7. Danh sách rỗng ----
check("danh sach rong", media_gc.plan_deletions([], NOW, 30, 300) == [])

# ---- 8. Quét đĩa + xoá thật (thư mục tạm) ----
import os        # noqa: E402
import tempfile  # noqa: E402

import config    # noqa: E402

_brain = tempfile.mkdtemp(prefix="javis-mediagc-")


def _tao(rel, mb, tuoi_ngay):
    """Tạo file thật với dung lượng và mtime mong muốn."""
    p = os.path.join(_brain, rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "wb") as f:
        f.write(b"\0" * int(mb * MB))
    t = time.time() - tuoi_ngay * DAY
    os.utime(p, (t, t))
    return p


_cu = _tao("05 - attachments/cu.png", 0.001, 40)          # biến thể tên có số thứ tự
_moi = _tao("05 - attachments/moi.png", 0.001, 1)
_note = _tao("05 - attachments/ghi-chu.md", 0.001, 999)
_tg = _tao("inbox/telegram/photo_1.jpg", 0.001, 40)
_wiki = _tao("Wiki/khai-niem.md", 0.001, 999)             # ngoài vùng cache -> không được đụng

d = media_gc.media_dirs(_brain)
check("media_dirs bat dung 2 thu muc", len(d) == 2 and any("attachments" in x for x in d)
      and any(x.endswith("inbox") for x in d))
check("media_dirs bo qua thu muc khac", not any("Wiki" in x for x in d))

check("scan duyet de quy", len(media_gc.scan(d)) == 4)

kq = media_gc.sweep(_brain, max_age_days=30, max_mb=300)
check("sweep xoa dung so file", kq["files"] == 2)
check("sweep tra so byte da don", kq["bytes"] > 0)
check("sweep xoa file qua han", not os.path.exists(_cu) and not os.path.exists(_tg))
check("sweep giu file moi", os.path.exists(_moi))
check("sweep giu file .md trong vung cache", os.path.exists(_note))
check("sweep khong dung file ngoai vung cache", os.path.exists(_wiki))

kq2 = media_gc.sweep(_brain, max_age_days=30, max_mb=300)
check("sweep chay lai khong xoa them", kq2["files"] == 0)

check("sweep brain khong ton tai khong no",
      media_gc.sweep(os.path.join(_brain, "khong-co-that")) == {"files": 0, "bytes": 0})

# ---- 9. Mặc định cấu hình ----
_m = config._DEFAULT.get("media") or {}
check("config mac dinh media.enabled", _m.get("enabled") is True)
check("config mac dinh 30 ngay", _m.get("max_age_days") == 30)
check("config mac dinh tran 300MB", _m.get("max_mb") == 300)
check("config mac dinh staging 3 ngay", _m.get("staging_days") == 3)

# ---- 9b. Staging: khong chua .md, chi co luat tuoi ----
check("keep_md=False thi .md cung bi xoa",
      media_gc.plan_deletions([muc("rac.md", 1, 40)], NOW, 30, 300, keep_md=False) == ["rac.md"])
check("keep_md mac dinh van chua .md",
      media_gc.plan_deletions([muc("rac.md", 1, 40)], NOW, 30, 300) == [])

_stg = tempfile.mkdtemp(prefix="javis-staging-")


def _tao_stg(ten, tuoi_ngay):
    p = os.path.join(_stg, ten)
    with open(p, "wb") as f:
        f.write(b"\0" * 1024)
    t = time.time() - tuoi_ngay * DAY
    os.utime(p, (t, t))
    return p


_s_cu = _tao_stg("paste-cu.png", 5)
_s_cu_md = _tao_stg("dan-vao.md", 5)
_s_moi = _tao_stg("paste-moi.png", 1)

kqs = media_gc.sweep_staging(_stg, max_age_days=3)
check("staging xoa file qua 3 ngay", not os.path.exists(_s_cu))
check("staging xoa ca .md qua han", not os.path.exists(_s_cu_md))
check("staging giu file trong han", os.path.exists(_s_moi))
check("staging dem dung so file", kqs["files"] == 2)
check("staging giu lai chinh thu muc", os.path.isdir(_stg))
check("staging chay lai khong xoa them", media_gc.sweep_staging(_stg, 3)["files"] == 0)
check("staging khong ton tai khong no",
      media_gc.sweep_staging(os.path.join(_stg, "khong-co")) == {"files": 0, "bytes": 0})

# ---- 10. Gitignore + gỡ index ----
import subprocess   # noqa: E402

import git_brain    # noqa: E402

for _dong in ("attachments/", "Attachments/", "*attachments/", "*Attachments/", "inbox/"):
    check(f"gitignore co dong {_dong}", _dong + "\n" in git_brain._GITIGNORE)

if git_brain.has_git():
    _repo = tempfile.mkdtemp(prefix="javis-mediagit-")

    def _g(*a):
        return subprocess.run(["git", "-C", _repo, *a], capture_output=True, text=True,
                              encoding="utf-8", errors="replace")

    _g("init")
    _g("config", "user.email", "t@t"); _g("config", "user.name", "T")
    os.makedirs(os.path.join(_repo, "attachments"), exist_ok=True)
    os.makedirs(os.path.join(_repo, "inbox", "telegram"), exist_ok=True)
    os.makedirs(os.path.join(_repo, "Wiki"), exist_ok=True)
    for _p, _noi_dung in ((("attachments", "a.png"), b"x"),
                          (("inbox", "telegram", "b.jpg"), b"x"),
                          (("Wiki", "note.md"), b"x")):
        with open(os.path.join(_repo, *_p), "wb") as _f:
            _f.write(_noi_dung)
    _g("add", "-A"); _g("commit", "-m", "seed")

    _truoc = (_g("ls-files").stdout or "")
    check("seed co theo doi media", "attachments/a.png" in _truoc)

    n = git_brain.untrack_media(_repo)
    _sau = (_g("ls-files").stdout or "")
    check("untrack_media go attachments", "attachments/a.png" not in _sau)
    check("untrack_media go inbox", "inbox/telegram/b.jpg" not in _sau)
    check("untrack_media khong dung file khac", "Wiki/note.md" in _sau)
    check("untrack_media giu file tren dia",
          os.path.exists(os.path.join(_repo, "attachments", "a.png")))
    check("untrack_media dem dung so thu muc", n == 2)

    _g("commit", "-m", "untrack")
    check("untrack_media chay lai khong lam gi", git_brain.untrack_media(_repo) == 0)

    # Brain cũ đã có .gitignore riêng: merge thêm dòng mới, KHÔNG mất dòng user tự đặt.
    with open(os.path.join(_repo, ".gitignore"), "w", encoding="utf-8") as _f:
        _f.write("# luat rieng cua user\nrac-cua-toi/\n")
    git_brain._ensure_gitignore_lines(_repo)
    with open(os.path.join(_repo, ".gitignore"), encoding="utf-8") as _f:
        _gi = _f.read()
    check("merge gitignore giu dong cu", "rac-cua-toi/" in _gi)
    check("merge gitignore them dong media", "attachments/" in _gi and "inbox/" in _gi)
else:
    print("BỎ QUA test git: máy không có git trong PATH")

# ── Tài liệu gắn vào project không bao giờ bị dọn (chủ repo báo 02/09) ────────────────
# Vùng cache "cái gì cũng biến mất được" chỉ đúng khi KHÔNG AI trỏ vào nó. Một file gắn vào
# project thì có người trỏ: xoá đi là để lại một hàng trong khung Project dẫn tới hư không.
_cu = [("/b/attachments/bao-cao.pdf", 1 * MB, NOW - 90 * DAY),
       ("/b/attachments/anh-cu.jpg", 1 * MB, NOW - 90 * DAY)]
check("chưa giữ gì thì cả hai file quá hạn đều bị dọn",
      set(media_gc.plan_deletions(_cu, NOW, 30, 0)) == {"/b/attachments/bao-cao.pdf",
                                                        "/b/attachments/anh-cu.jpg"})
check("file đang gắn vào project thì KHÔNG bị dọn dù quá hạn 90 ngày",
      media_gc.plan_deletions(_cu, NOW, 30, 0, giu_path={"/b/attachments/bao-cao.pdf"})
      == ["/b/attachments/anh-cu.jpg"])
# Trần dung lượng là đường xoá THỨ HAI, độc lập với luật tuổi. Vá mỗi luật tuổi mà quên trần
# thì file vẫn mất, chỉ là mất lúc brain đầy chứ không phải lúc đủ 30 ngày - khó thấy hơn.
_moi = [("/b/attachments/bao-cao.pdf", 10 * MB, NOW - 1 * DAY),
        ("/b/attachments/anh-moi.jpg", 10 * MB, NOW - 2 * DAY)]
check("CANARY: trần dung lượng cũng phải chừa file của project",
      media_gc.plan_deletions(_moi, NOW, 0, 1, giu_path={"/b/attachments/bao-cao.pdf"})
      == ["/b/attachments/anh-moi.jpg"])
check("giu_path rỗng thì hành vi y như cũ",
      media_gc.plan_deletions(_cu, NOW, 30, 0, giu_path=set())
      == media_gc.plan_deletions(_cu, NOW, 30, 0))

print()
if _fails:
    print(f"{len(_fails)} test ĐỎ: " + ", ".join(_fails))
    sys.exit(1)
print("Tất cả test media_gc xanh.")
