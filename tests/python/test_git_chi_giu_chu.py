"""Git chỉ giữ CHỮ, không giữ media - và luật phải đúng THỨ TỰ.

    python tests/run.py git_chi_giu_chu      (KHÔNG mạng; có dựng repo git thật nếu máy có git)

Chủ repo chốt 2026-08-08: "chỉ lưu các file dạng văn bản, text, html, .md chứ không lưu dạng
media để tiết kiệm cho git".

Lý do là tính chất của chính git chứ không phải sở thích: git được thiết kế để NHỚ MÃI MÃI.
Nội dung mỗi file commit vào thành một blob nằm vĩnh viễn trong .git/objects; xoá file về sau
chỉ ghi thêm một dòng "từ đây không còn file này", còn blob vẫn phải giữ để quay ngược về
commit cũ được, và `git gc` cũng không dọn được vì nó vẫn có chủ. Với CHỮ thì đó là ưu điểm
(git nén + lưu chênh lệch, sửa cả trăm lượt vẫn nhẹ). Với MEDIA thì ngược hẳn: mp4/jpg đã nén
sẵn bằng codec nên git không nén thêm được và hai bản render là hai file khác hẳn nhau, mỗi
lượt xuất lại là thêm nguyên một cục, vĩnh viễn.

BẪY CHÍNH mà test này canh: luật allowlist CHỈ ĐÚNG KHI ĐÚNG THỨ TỰ - chặn hết, mở lại cho
chữ, rồi chặn lần nữa mấy thư mục cấm. Bản `_ensure_gitignore_lines` cũ chỉ NỐI THÊM dòng
thiếu vào cuối file, nên với một brain cũ thì mấy dòng "chặn lại" nằm TRƯỚC dòng "mở cho chữ"
và git hiểu ngược: `Javis/learn-log/*.json` được mở lại. Log thô có thể chứa secret, nên đó
không phải lỗi thẩm mỹ.
"""
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-gitchu-"))

from _paths import ROOT, SERVER  # noqa: E402,F401

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import git_brain as G  # noqa: E402

_fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)


# ---- 1. Luật nhận diện file chữ ----
for f in ("ghi-chu.md", "note.MD", "bang-gia.csv", "trang.html", "so-do.svg", "du-lieu.json",
          "script.py", "luat.yaml", "bang.canvas", ".gitignore", "LICENSE"):
    check(f"giữ file chữ: {f}", G.la_file_chu(f))
for f in ("anh.jpg", "anh.PNG", "clip.mp4", "clip.MOV", "am-thanh.mp3", "tai-lieu.pdf",
          "goi.zip", "font.woff2", "khong-co-duoi", "anh.webp", "video.mkv"):
    check(f"bỏ file media/nhị phân: {f}", not G.la_file_chu(f))
check("đường dẫn nhiều cấp vẫn xét ĐÚNG phần tên file",
      G.la_file_chu("wiki/2026/ghi-chu.md") and not G.la_file_chu("wiki/2026/clip.mp4"))
check("thư mục tên giống media không làm lệch phép thử",
      not G.la_file_chu("video/clip.mp4") and G.la_file_chu("video/mo-ta.md"))


# ---- 2. Bước chụp sang mirror dùng CHUNG một luật với .gitignore ----
check("mirror bỏ media", G._backup_skip("wiki/anh.jpg") and G._backup_skip("clip.mp4"))
check("mirror giữ chữ", not G._backup_skip("wiki/ghi-chu.md"))
check("mirror vẫn bỏ file nhạy cảm dù là chữ",
      G._backup_skip("brain/Javis/learn-log/log.json")
      and G._backup_skip("brain/memory/conversations/2026-08-08.md")
      and G._backup_skip("brain/x.tmp"))
SRC = (SERVER / "git_brain.py").read_text(encoding="utf-8")
check("_backup_skip gọi đúng hàm chung, không chép lại danh sách đuôi",
      "if la_file_chu(name):" in SRC and "sync_images and la_anh(name)" in SRC)
# Cùng một predicate lọc CẢ hai chiều: nhờ vậy khi mirror dọn media đi và đẩy việc xoá đó lên
# repo, máy khác kéo về cũng KHÔNG xoá media thật trên đĩa của nó.
check("áp-về cũng lọc bằng chính predicate đó (máy khác không bị xoá mất media thật)",
      "todo = [p for p in sorted(changed) if p and not _backup_skip(p, sync_images)]" in SRC)


# ---- 3. .gitignore sinh ra: đúng nội dung và ĐÚNG THỨ TỰ ----
def _gi(tmp):
    G._ensure_gitignore_lines(tmp)
    return (Path(tmp) / ".gitignore").read_text(encoding="utf-8")


d1 = tempfile.mkdtemp()
gi = _gi(d1)
check("brain mới: có khối của Javis, có mốc mở/đóng", G._GI_MO in gi and G._GI_DONG in gi)
check("brain mới: chặn tất cả trước", "\n*\n" in gi)
check("brain mới: mở lại cho thư mục và cho .md", "\n!*/\n" in gi and "\n!*.md\n" in gi)
i_chan, i_mo, i_camlai = gi.index("\n*\n"), gi.index("\n!*.md\n"), gi.index("Javis/learn-log/")
check("THỨ TỰ: chặn hết → mở cho chữ → chặn lại thư mục cấm", i_chan < i_mo < i_camlai)
check("gọi lần hai không ghi lại vô ích (idempotent)", G._ensure_gitignore_lines(d1) is False)


# ---- 4. Nâng cấp một brain CŨ: giữ luật riêng của user, dọn template cũ ----
d2 = tempfile.mkdtemp()
(Path(d2) / ".gitignore").write_text(
    "# Javis brain - KHÔNG commit: khoá, log thô (có thể chứa secret), nhật ký nền.\n"
    ".javis-learn.lock\nJavis/learn-log/\nattachments/\ninbox/\n*.tmp\n\n"
    "# luat rieng cua toi\nbao-mat/\n", encoding="utf-8")
gi2 = _gi(d2)
check("nâng cấp: giữ nguyên luật riêng của user", "bao-mat/" in gi2)
check("nâng cấp: giữ luôn cả dòng chú thích của user", "# luat rieng cua toi" in gi2)
check("nâng cấp: dòng template CŨ không nằm lẫn ngoài khối nữa",
      gi2.count("Javis/learn-log/") == 1 and gi2.count("inbox/") == 1)
check("nâng cấp: luật riêng của user nằm SAU khối Javis (user đè lên được)",
      gi2.index(G._GI_DONG) < gi2.index("bao-mat/"))
check("nâng cấp: THỨ TỰ trong khối vẫn đúng",
      gi2.index("\n*\n") < gi2.index("\n!*.md\n") < gi2.index("Javis/learn-log/"))


# ---- 5. Thử trên git THẬT: lời nói phải khớp với việc git làm ----
if shutil.which("git"):
    d3 = tempfile.mkdtemp()
    for sub in ("Javis/learn-log", "attachments", "wiki", "bao-mat"):
        os.makedirs(os.path.join(d3, sub), exist_ok=True)
    subprocess.run(["git", "init", "-q", "."], cwd=d3, capture_output=True)
    G._ensure_gitignore_lines(d3)
    with open(os.path.join(d3, ".gitignore"), "a", encoding="utf-8") as f:
        f.write("\nbao-mat/\n")
    ghi = {
        "wiki/ghi-chu.md": "tri thuc", "wiki/bang.csv": "a,b",
        "wiki/anh.jpg": "x", "clip.mp4": "x", "am-thanh.mp3": "x",
        "Javis/learn-log/log.json": '{"secret":"abc"}',
        "attachments/note.md": "x", "attachments/anh.png": "x",
        "bao-mat/key.md": "x",
    }
    for rel, noi_dung in ghi.items():
        p = Path(d3) / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(noi_dung, encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=d3, capture_output=True)
    r = subprocess.run(["git", "diff", "--cached", "--name-only"], cwd=d3,
                       capture_output=True, text=True)
    theo_doi = set((r.stdout or "").split())
    check("git THẬT: commit ghi chú .md", "wiki/ghi-chu.md" in theo_doi)
    check("git THẬT: commit bảng .csv", "wiki/bang.csv" in theo_doi)
    check("git THẬT: KHÔNG commit ảnh", "wiki/anh.jpg" not in theo_doi)
    check("git THẬT: KHÔNG commit video", "clip.mp4" not in theo_doi)
    check("git THẬT: KHÔNG commit âm thanh", "am-thanh.mp3" not in theo_doi)
    check("git THẬT: KHÔNG commit log thô dù nó là .json (bẫy thứ tự luật)",
          "Javis/learn-log/log.json" not in theo_doi)
    check("git THẬT: KHÔNG commit thứ trong attachments dù là .md",
          "attachments/note.md" not in theo_doi)
    check("git THẬT: luật riêng của user vẫn có tác dụng", "bao-mat/key.md" not in theo_doi)
else:
    print("BỎ QUA phần git thật: không tìm thấy git trong PATH")


# ---- 6. Người dùng phải ĐƯỢC BÁO là media không lên, không im lặng ----
check("báo cáo đồng bộ có chỗ đếm media bỏ qua",
      '"media_bo_qua": 0, "media_bytes": 0' in SRC)
check("_sync_mirror trả về con số đó chứ không nuốt", 'return {"media_bo_qua"' in SRC)
JS = (ROOT / "dashboard" / "console.js").read_text(encoding="utf-8")
check("giao diện đồng bộ nói rõ chỉ lưu thông tin, không lưu media",
      "Mặc định chỉ đồng bộ THÔNG TIN, không đồng bộ media" in JS)
check("giao diện nói media vẫn nằm trên máy, không phải bị xoá",
      "vẫn nằm nguyên trên máy" in JS)
check("giao diện chỉ chỗ sao lưu media thay thế", "Drive" in JS)
check("sau mỗi lần đồng bộ có báo số file media bị bỏ qua", "r.media_bo_qua" in JS)
DOC = (ROOT / "docs" / "18-sao-luu-github.md").read_text(encoding="utf-8")
check("tài liệu có mục riêng về chuyện này",
      "## Chỉ đồng bộ THÔNG TIN, không đồng bộ media" in DOC)
check("tài liệu giải thích vì sao xoá không đòi lại được dung lượng",
      "không đòi lại được dung lượng" in DOC)
check("tài liệu KHÔNG còn câu cũ 'ảnh vẫn lên repo'", "Ảnh và file VẪN lên repo" not in DOC)


if _fails:
    raise SystemExit(f"\nFAIL - test_git_chi_giu_chu: {len(_fails)} lỗi: {_fails}")
print("\nOK - test_git_chi_giu_chu: tất cả pass")
