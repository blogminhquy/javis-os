"""A bot finds its Agent's documents whatever folder their stored path starts from (field report #1699).

    python tests/run.py bot_agent_doc_paths      (no network)

#1699 (0.620.0, Windows, no login): the bot's Agent had its schedule and price file in its Documents section, stored
as "dự án web/javis/brains/Brain Default/wiki/chu-de/lich-hoc-gia-ban-bke.md", yet the bot told the customer it had no
information. The Documents drawer stores a path from the BROWSE CEILING (`main._files_ceiling`), which is the whole
drive on a computer without a login, while `chatbot_runtime.bot_doc_files` read it from the brain root: a file that
does not exist, so the bot had no document at all (`chatbot_grounding._ung_vien` drops a path that is not a file).

This file guards: a path from the drive, a path from the brain (as before), Windows separators, a brain copied to
another place, a brain folder name in another Unicode form, and that nothing outside the bot's brain gets in.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import os
import sys
import tempfile
import unicodedata
from pathlib import Path

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-docpaths-")
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import chatbot_grounding  # noqa: E402
import chatbot_runtime  # noqa: E402

_fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(extra) + "]") if extra and not cond else ""))
    if not cond:
        _fails.append(name)


DRIVE = Path(tempfile.mkdtemp(prefix="drive-")).resolve()       # stands for "D:/"
BRAIN = DRIVE / "dự án web" / "javis" / "brains" / "Brain Default"
FILE = "wiki/chu-de/lich-hoc-gia-ban-bke.md"
(BRAIN / FILE).parent.mkdir(parents=True)
(BRAIN / FILE).write_text("# Lịch học và giá bán\nLớp BKE học tối thứ hai và thứ năm, học phí 2.500.000 đồng một khoá.\n",
                          encoding="utf-8")
(BRAIN / "sources").mkdir()
(BRAIN / "sources" / "bang-gia.md").write_text("# Bảng giá\nGiá sỉ từ 100 chai.\n", encoding="utf-8")
(DRIVE / "secret.md").write_text("# Ngoài brain\nkhông được thấy\n", encoding="utf-8")
(BRAIN.parent / "Other Brain").mkdir()
(BRAIN.parent / "Other Brain" / "note.md").write_text("# Brain khác\n", encoding="utf-8")

META = {}
chatbot_runtime._deps["read_agent"] = lambda brain, slug: (META, "")
chatbot_runtime._deps["brain_root"] = lambda brain: str(BRAIN)
CFG = {"id": "b1", "brain": "Brain Default", "agent": {"brain": "Brain Default", "slug": "tu-van"}}


def docs(*paths):
    META.clear()
    META["assets"] = {"files": [{"id": str(i), "path": p, "pinned": True} for i, p in enumerate(paths)]}
    return chatbot_runtime.bot_doc_files(CFG)


ceiling_path = "dự án web/javis/brains/Brain Default/" + FILE
check("#1699: a path from the drive (the browse ceiling) finds the file in the brain", docs(ceiling_path) == (FILE,),
      docs(ceiling_path))
check("a path from the brain still works", docs(FILE) == (FILE,), docs(FILE))
check("Windows separators", docs(ceiling_path.replace("/", "\\")) == (FILE,), docs(ceiling_path.replace("/", "\\")))
check("an absolute path inside the brain", docs(str(BRAIN / FILE)) == (FILE,), docs(str(BRAIN / FILE)))
check("a brain copied to another place: the part after the brain's folder name",
      docs("old laptop/brains/Brain Default/" + FILE) == (FILE,), docs("old laptop/brains/Brain Default/" + FILE))
check("the brain folder name in another Unicode form or case",
      docs(unicodedata.normalize("NFD", "Dự án web/javis/brains/brain default/") + FILE) == (FILE,))
check("several documents keep their order", docs(ceiling_path, "sources/bang-gia.md") == (FILE, "sources/bang-gia.md"))

outside = docs("Brain Default/../../secret.md", "../secret.md", "dự án web/javis/brains/Other Brain/note.md",
               "Brain Default/../Other Brain/note.md", str(DRIVE / "secret.md"))
# What comes back stays inside the brain and leads to no file there: the outside files are never reached.
check("nothing outside the bot's brain gets in",
      all(BRAIN in (BRAIN / p).resolve().parents and not (BRAIN / p).is_file() for p in outside), outside)
missing = docs("dự án web/javis/brains/Brain Default/wiki/gone.md")
check("a file that is gone stays a path that leads nowhere (as before)",
      all(not (BRAIN / p).is_file() for p in missing), missing)

# End to end: the bot's search now reaches the pinned schedule file.
chatbot_grounding.xoa_cache()
hit = chatbot_grounding.thu_thap(BRAIN, "lịch học lớp BKE học phí bao nhiêu", files=docs(ceiling_path))
check("#1699: the bot's search finds the schedule and price", hit.get("co") and hit.get("nguon") == [FILE], hit)
chatbot_grounding.xoa_cache()
before = chatbot_grounding.thu_thap(BRAIN, "lịch học lớp BKE học phí bao nhiêu",
                                    files=(ceiling_path,))      # what the bot was given before the fix
check("CANARY: read from the brain root, the stored path found nothing", not before.get("co"), before)

check("no em dash or en dash", not any(c in open(__file__, encoding="utf-8").read() for c in (chr(0x2014), chr(0x2013))))

print()
if _fails:
    print(f"{len(_fails)} FAIL: " + ", ".join(_fails))
    sys.exit(1)
print("ALL PASS")
