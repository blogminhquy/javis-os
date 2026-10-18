"""0.217.0: lượt tự học không được xoá trang wiki (owner, 2026-10-18).

    python tests/run.py learn_khong_xoa_wiki      (KHÔNG mạng, git thật trong thư mục tạm)

Ảnh chụp của chủ: bot báo "trang wiki [[Bố Trí Nguồn Laser UV Mở Buồng Theo Ảnh Chủ Gửi]] tạo lúc nãy đã bị mất", còn
`_open-questions.md` có dòng "mâu thuẫn" về nó. Đường đi:
  1. Chat tạo trang trong `wiki/` (chữ thường, như mọi brain mới). Chat không commit, nên trang chưa có trong git.
  2. Lượt học thấy mâu thuẫn, thêm mục `## Mâu thuẫn` vào trang và một dòng vào `_open-questions.md`.
  3. Scope guard chỉ cho phép tiền tố "Wiki" viết hoa, nên mọi path `wiki/...` bị coi là ngoài phạm vi.
  4. `hard_reset_paths` chạy `git checkout HEAD -- <cả lô>` (hỏng cả lệnh vì trang chưa có trong HEAD) rồi
     `git clean -fd`: trang bị xoá trắng, dòng câu hỏi mở vẫn còn. Đúng như ảnh.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import os
import subprocess
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-learnwiki-"))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import git_brain  # noqa: E402
from learn import LearnDeps, LearnFeature  # noqa: E402
import main  # noqa: E402  - dùng ĐÚNG hàm tìm thư mục con thật (không phân biệt hoa thường), là một nửa của lỗi

_fails = []


def check(name, cond, them=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(them) + "]") if them and not cond else ""))
    if not cond:
        _fails.append(name)


def git(root, *a):
    return subprocess.run(["git", "-C", str(root), *a], capture_output=True, text=True)


def _write(path, text):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(text, encoding="utf-8")


def brain(wiki_name="wiki"):
    root = Path(tempfile.mkdtemp(prefix="javis-brain-"))
    git(root, "init", "-q")
    git(root, "config", "user.email", "t@t")
    git(root, "config", "user.name", "t")
    _write(root / wiki_name / "_open-questions.md", "# Open Questions\n")
    _write(root / wiki_name / "index.md", "# Index\n")
    _write(root / "memory" / "MEMORY.md", "# Memory\n")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "seed")
    return root


def feature(root):
    deps = LearnDeps(
        build_system_prompt=lambda b: "",
        brain_root=lambda b: str(root),
        brain_memory_dir=lambda b: root / "memory",
        resolve_subfolder=main._resolve_subfolder,
        aux_model=lambda: None,
        atomic_write_text=_write,
        sessions_store=None,
        state_dir=Path(tempfile.mkdtemp(prefix="javis-learnstate-")),
        readonly_tools=["Read"],
    )
    return LearnFeature(deps)


CAPS = {"memory": False, "wiki": True, "skill": False, "task": False, "agent": False, "workflow": False}
TEN = "Bố Trí Nguồn Laser UV Mở Buồng Theo Ảnh Chủ Gửi"
THAN_CHAT = "---\ntype: wiki\n---\n# Bố trí nguồn laser\n\nĐầu SMA chỉ đi vào bộ Q, không vào cái nào khác.\n"


def chay(f, wiki):
    return f._promote_sync("brain", {"wiki": wiki}, f.read_config(), CAPS, allow_write=True)


# ---- 1. Đúng ca của chủ: trang chat vừa tạo, lượt học báo mâu thuẫn ----
for wiki_name in ("wiki", "07 - Wiki"):
    root = brain(wiki_name)
    trang = root / wiki_name / f"{TEN}.md"
    _write(trang, THAN_CHAT)                     # chat tạo, KHÔNG commit
    rep = chay(feature(root), [{"title": "Laser UV", "body": "Quan điểm khác: đầu SMA đi cả bộ R.",
                                "density": 3, "provenance": "user", "conflict_with": TEN}])
    con = trang.exists()
    check(f"[{wiki_name}] trang chat vừa tạo KHÔNG bị xoá sau lượt học báo mâu thuẫn", con, rep.get("blocked"))
    text = trang.read_text(encoding="utf-8") if con else ""
    check(f"[{wiki_name}] nội dung chat còn nguyên", "Đầu SMA chỉ đi vào bộ Q" in text)
    check(f"[{wiki_name}] và có thêm mục Mâu thuẫn", "## Mâu thuẫn" in text and "bộ R" in text)
    oq = (root / wiki_name / "_open-questions.md").read_text(encoding="utf-8")
    check(f"[{wiki_name}] câu hỏi mở trỏ đúng trang", f"[[{TEN}]]: mâu thuẫn" in oq, oq)
    check(f"[{wiki_name}] không path nào bị coi là ngoài phạm vi",
          not any("ngoài scope" in b for b in rep.get("blocked", [])), rep.get("blocked"))
    check(f"[{wiki_name}] lượt học được commit (có thể hoàn tác như mọi lượt học)", bool(rep.get("commit")), rep)

# ---- 2. Trang mới do lượt học tạo trong wiki/ thường: không bị dọn mất ----
root = brain("wiki")
rep = chay(feature(root), [{"title": "Đầu nối SMA", "body": "Đầu SMA nối bộ Q với nguồn laser.", "density": 3,
                            "provenance": "user"}])
check("trang lượt học vừa tạo trong wiki/ thường còn trên đĩa", (root / "wiki" / "Đầu nối SMA.md").exists(), rep)
check("và đã commit", "Đầu nối SMA.md" in git(root, "-c", "core.quotepath=false", "show", "--name-only", "HEAD").stdout)

# ---- 3. Dòng câu hỏi mở dùng tên trang THẬT khi tên model đưa khớp gần đúng ----
root = brain("wiki")
_write(root / "wiki" / "Phễu bán hàng 8 + 2.md", "---\ntype: wiki\n---\nPhễu.\n")
git(root, "add", "-A")
git(root, "commit", "-qm", "phễu")
rep = chay(feature(root), [{"title": "Phễu", "body": "Ý khác về phễu.", "density": 3, "provenance": "user",
                            "conflict_with": "phễu bán hàng 8+2"}])
oq = (root / "wiki" / "_open-questions.md").read_text(encoding="utf-8")
check("câu hỏi mở ghi tên trang thật, không phải chuỗi model đưa", "[[Phễu bán hàng 8 + 2]]" in oq, oq)

# ---- 4. hard_reset_paths không bao giờ xoá file chưa có trong git ----
root = brain("wiki")
_write(root / "ngoai" / "moi.md", "file chưa theo dõi\n")
_write(root / "wiki" / "index.md", "# Index\nđã sửa\n")
xong = git_brain.hard_reset_paths(str(root), ["ngoai/moi.md", "wiki/index.md"])
check("file chưa có trong git: để nguyên trên đĩa", (root / "ngoai" / "moi.md").exists())
check("file đã có trong git vẫn được đưa về HEAD, dù cùng lô có file chưa theo dõi",
      (root / "wiki" / "index.md").read_text(encoding="utf-8") == "# Index\n" and xong == ["wiki/index.md"], xong)

# ---- 5. Danh sách phạm vi lấy đúng thư mục thật ----
root = brain("wiki")
sc = LearnFeature._scope_cho_phep(str(root), root / "memory", root / "wiki", None)
check("phạm vi có wiki/ thường của brain này", "wiki" in sc and "memory" in sc, sc)
check("thư mục ngoài brain không được thêm vào phạm vi", "tmp" not in " ".join(
    LearnFeature._scope_cho_phep(str(root), Path(tempfile.gettempdir()))), sc)

if _fails:
    print(f"\nFAIL {len(_fails)}: " + ", ".join(_fails))
    sys.exit(1)
print("\nOK - test_learn_khong_xoa_wiki: all pass")
