"""Frontmatter delimiters are lines of their own, not any "---" in the text.

    python tests/run.py frontmatter_delimiter      (no network)

2026-10-15: workflow mtm-chien-dich-tong-luc had 16 steps but the server read 14. Its `task:`
said "phần đầu giữa hai dòng --- gồm", and every frontmatter reader cut the YAML with
`text.split("---", 2)`, so the header ended mid-sentence, YAML failed or truncated, and the
later steps vanished without an error. This test pins:

1. A "---" inside a sentence of the frontmatter keeps every step (all readers).
2. For valid files the new splitter is byte-identical to the old split, checked on the real
   corpus of the repo, so nothing that worked changes.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401  - puts server/ on sys.path
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-fm-state-"))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import fastyaml      # noqa: E402
import share_bundle  # noqa: E402
import skill_router  # noqa: E402
import system_sync   # noqa: E402
import main          # noqa: E402

_fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (f"  [{extra}]" if extra and not cond else ""))
    if not cond:
        _fails.append(name)


def old_split(text):
    """The behaviour before 0.172.0 (`text.split("---", 2)`), kept here as the reference for valid files."""
    if not text.startswith("---"):
        return None
    parts = text.split("---", 2)
    return (parts[1], parts[2]) if len(parts) >= 3 else None


# ---- 1. The incident: "---" mid-sentence inside the frontmatter ----
STEPS = 16
steps_yaml = "".join(f"  - agent: a{i}\n    task: buoc {i}\n" for i in range(1, STEPS + 1))
WF = ("---\n"
      "name: Chiến dịch tổng lực\n"
      "task: Viết file theo mẫu, phần đầu giữa hai dòng --- gồm name, steps; xong thì báo.\n"
      "group: Marketing\n"
      "steps:\n" + steps_yaml +
      "---\n\nThân workflow.\n")

with tempfile.TemporaryDirectory() as d:
    p = Path(d) / "wf.md"
    p.write_bytes(WF.encode("utf-8"))
    meta, body = main._read_md(p)
    check(f"main._read_md keeps all {STEPS} steps", len(meta.get("steps") or []) == STEPS,
          len(meta.get("steps") or []))
    check("main._read_md keeps the sentence with --- intact",
          "giữa hai dòng --- gồm" in str(meta.get("task")), meta.get("task"))
    check("main._read_md body is the real body", body == "Thân workflow.", repr(body))

    # Same file through _sua_meta_file: must not be flagged unreadable, must keep all steps.
    out = main._sua_meta_file(p, lambda m: m.__setitem__("group", "Sales"))
    meta2, _ = main._read_md(p)
    check("_sua_meta_file rewrites without losing steps",
          len(meta2.get("steps") or []) == STEPS and meta2.get("group") == "Sales")

for mod_name, fn in (("share_bundle._parse", share_bundle._parse),
                     ("skill_router.split_frontmatter", skill_router.split_frontmatter),
                     ("system_sync._split_frontmatter", system_sync._split_frontmatter)):
    meta, body = fn(WF)
    check(f"{mod_name} keeps all {STEPS} steps", len(meta.get("steps") or []) == STEPS,
          len(meta.get("steps") or []))
    check(f"{mod_name} body starts after the closing line", body.strip() == "Thân workflow.",
          repr(body))

fm, tags, tasks = main._scan_note_md(WF)
check("_scan_note_md reads the full frontmatter", len(fm.get("steps") or []) == STEPS)

# ---- 2. Edge cases of the delimiter itself ----
check("no frontmatter -> None", fastyaml.split_frontmatter("hello\n---\nx\n") is None)
check("unclosed frontmatter -> None", fastyaml.split_frontmatter("---\na: 1\n") is None)
check("empty string -> None", fastyaml.split_frontmatter("") is None)
check("'---title' on line one is not a delimiter",
      fastyaml.split_frontmatter("---title\na: 1\n---\n") is None)
check("CRLF file splits", fastyaml.split_frontmatter("---\r\na: 1\r\n---\r\nbody") == ("\r\na: 1\r\n", "\r\nbody"))
check("trailing spaces on the delimiter lines are fine",
      fastyaml.split_frontmatter("---  \na: 1\n--- \nbody") == ("  \na: 1\n", " \nbody"))
check("empty frontmatter", fastyaml.split_frontmatter("---\n---\nbody") == ("\n", "\nbody"))
check("closing line at end of file", fastyaml.split_frontmatter("---\na: 1\n---") == ("\na: 1\n", ""))
check("'----' line is not a closing delimiter",
      fastyaml.split_frontmatter("---\na: |\n  x\n----\nb: 2\n---\nbody")[0].endswith("b: 2\n"))
check("a '---' line inside the BODY stays in the body",
      fastyaml.split_frontmatter("---\na: 1\n---\nx\n---\ny") == ("\na: 1\n", "\nx\n---\ny"))

# ---- 3. Valid files: byte-identical to the old split on the real repo corpus ----
_SKIP = {".git", ".venv", "node_modules", "__pycache__"}
corpus = sorted(f for f in ROOT.rglob("*.md") if not _SKIP & set(f.relative_to(ROOT).parts))[:3000]
texts = []
for f in corpus:
    try:
        texts.append((f.relative_to(ROOT).as_posix(), f.read_text(encoding="utf-8", errors="replace")))
    except OSError:
        pass
# The repo ships few frontmatter files, so add the shapes Javis itself writes (_write_md).
for i, (meta, body) in enumerate((
        ({"name": "a", "steps": [{"agent": "x", "task": "y"}]}, "Body\n\n---\n\nAfter a rule."),
        ({"description": "dài: có dấu hai chấm", "tags": ["Sales", "AI"]}, ""),
        ({"name": "Viết email"}, "# Tiêu đề\n- [ ] việc\n"))):
    p = Path(tempfile.mkdtemp(prefix="javis-fm-")) / f"s{i}.md"
    main._write_md(p, meta, body)
    texts.append((f"synthetic-{i}", p.read_text(encoding="utf-8")))
n_same, differ = 0, []
for name, text in texts:
    new, old = fastyaml.split_frontmatter(text), old_split(text)
    if new is None and old is None:
        continue
    if new == old:
        n_same += 1
        continue
    # Allowed difference only when the old header was cut by a "---" that is NOT a line of its own.
    if old is not None and new is not None and len(new[0]) > len(old[0]):
        continue
    differ.append(name)
check(f"{n_same} frontmatter files split exactly as before", not differ, differ[:5])
check("corpus is not empty (the comparison above actually ran)", n_same >= 10, n_same)

print()
if _fails:
    print(f"FAIL {len(_fails)} check(s)")
    sys.exit(1)
print("ALL OK")
