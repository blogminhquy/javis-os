"""Stamping a memory's source and editing a memory keep its frontmatter readable (#1165).

    python tests/run.py memory_frontmatter_quotes

The bug: `memory_control._join` wrote `key: value` with no quoting. After a chat turn, `stamp_new_facts` rebuilt the
frontmatter of a memory whose `description` held a colon, the YAML no longer parsed, and a later stamp (or an owner
edit) read it as {} and wrote back only its own keys: `type`, `description`, `tags` and `created` were gone, silently.

Pinned here:
  1. stamp adds `source` to a valid memory without touching its other lines, and the file still parses
  2. stamping again changes nothing (the source is there)
  3. a memory already broken by the old writer is left alone by stamp, never rewritten as {}
  4. editing that broken memory repairs it: every key the old writer left is read back and quoted properly
  5. editing a frontmatter that cannot be read at all refuses, and the file is unchanged
  6. editing a valid memory keeps a description with a colon and a list of tags
  7. a memory with no frontmatter gets one holding the source
  8. a CRLF file still parses after the stamp, with its source
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import datetime
import os
import tempfile
from pathlib import Path

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-mem-fm-"))

import fastyaml  # noqa: E402
import memory_control as mc  # noqa: E402

fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (f"  {str(extra)[:400]}" if extra and not cond else ""))
    if not cond:
        fails.append(name)


def meta_of(path):
    parts = fastyaml.split_frontmatter(path.read_text(encoding="utf-8"))
    try:
        return fastyaml.safe_load(parts[0]) if parts else None
    except Exception as e:  # noqa: BLE001
        return f"YAML error: {type(e).__name__}"


mem = Path(tempfile.mkdtemp(prefix="javis-mem-fm-dir-")) / "memory"
facts = mem / "facts"
facts.mkdir(parents=True)

VALID = ('---\n'
         'type: preference\n'
         'description: "Ghi chú: ví dụ có dấu hai chấm"\n'
         'tags: [vi-du]\n'
         'created: 2026-11-08\n'
         '---\n'
         'Nội dung ký ức.\n')

# 1. stamp keeps every other line byte for byte
f1 = facts / "vi-du.md"
f1.write_text(VALID, encoding="utf-8")
stamped = mc.stamp_new_facts(mem, source="chat 2026-11-08 (abc12345)", since=0)
text1 = f1.read_text(encoding="utf-8")
m1 = meta_of(f1)
check("1. the memory was stamped", "vi-du" in stamped, stamped)
check("1. the frontmatter still parses", isinstance(m1, dict), m1)
m1 = m1 if isinstance(m1, dict) else {}
check("1. description with a colon survives", m1.get("description") == "Ghi chú: ví dụ có dấu hai chấm", m1)
check("1. tags stay a list", m1.get("tags") == ["vi-du"], m1)
check("1. type and created stay", m1.get("type") == "preference" and m1.get("created") == datetime.date(2026, 11, 8), m1)
check("1. source added", m1.get("source") == "chat 2026-11-08 (abc12345)", m1)
check("1. the original lines are untouched",
      all(line in text1 for line in VALID.splitlines()), text1)
check("1. the body is untouched", text1.endswith("---\nNội dung ký ức.\n"), text1)

# 2. a second stamp is a no-op
before = f1.read_text(encoding="utf-8")
again = mc.stamp_new_facts(mem, source="chat 2026-11-09 (def67890)", since=0)
check("2. a stamped memory is not stamped again", "vi-du" not in again and f1.read_text(encoding="utf-8") == before)

# 3. a memory the old writer broke is left alone by stamp
BROKEN_BY_OLD_WRITER = ('---\n'
                        'type: preference\n'
                        'description: Ghi chú: ví dụ có dấu hai chấm\n'
                        "tags: ['vi-du']\n"
                        'created: 2026-11-08\n'
                        '---\n'
                        'Ký ức bị hỏng.\n')
f3 = facts / "hong.md"
f3.write_text(BROKEN_BY_OLD_WRITER, encoding="utf-8")
check("3. the old writer's output is not valid YAML", isinstance(meta_of(f3), str), meta_of(f3))
mc.stamp_new_facts(mem, source="chat 2026-11-09 (def67890)", since=0)
check("3. stamp leaves a broken frontmatter as it is", f3.read_text(encoding="utf-8") == BROKEN_BY_OLD_WRITER,
      f3.read_text(encoding="utf-8"))

# 4. editing it repairs it
mc.edit_memory(mem, "hong", "Ký ức đã sửa.")
m4 = meta_of(f3)
check("4. after an edit the frontmatter parses", isinstance(m4, dict), m4)
m4 = m4 if isinstance(m4, dict) else {}
check("4. description read back whole", m4.get("description") == "Ghi chú: ví dụ có dấu hai chấm", m4)
check("4. tags read back as a list", m4.get("tags") == ["vi-du"], m4)
check("4. type and created kept", m4.get("type") == "preference" and m4.get("created") == datetime.date(2026, 11, 8), m4)
check("4. marked as edited by the owner", m4.get("origin") == "owner-edited" and m4.get("status") == "confirmed", m4)
check("4. new body written", f3.read_text(encoding="utf-8").endswith("---\nKý ức đã sửa.\n"))
listed = {it["slug"]: it for it in mc.list_memories(mem)}
check("4. the list shows its type", listed.get("hong", {}).get("type") == "preference", listed.get("hong"))

# 5. a frontmatter that cannot be read at all: refuse, change nothing
UNREADABLE = ('---\n'
              'type: preference\n'
              '  description: [unclosed\n'
              '---\n'
              'Không đọc được.\n')
f5 = facts / "khong-doc-duoc.md"
f5.write_text(UNREADABLE, encoding="utf-8")
try:
    mc.edit_memory(mem, "khong-doc-duoc", "Ghi đè?")
    raised = False
except ValueError:
    raised = True
check("5. editing an unreadable frontmatter refuses", raised)
check("5. the file is unchanged", f5.read_text(encoding="utf-8") == UNREADABLE)
mc.stamp_new_facts(mem, source="chat x", since=0)
check("5. stamp leaves it unchanged too", f5.read_text(encoding="utf-8") == UNREADABLE)

# 6. editing a valid memory round-trips its values
f6 = facts / "hop-le.md"
f6.write_text(VALID.replace("Nội dung ký ức.", "Cũ."), encoding="utf-8")
mc.edit_memory(mem, "hop-le", "Mới.", type_="business")
m6 = meta_of(f6)
check("6. still parses after an edit", isinstance(m6, dict), m6)
m6 = m6 if isinstance(m6, dict) else {}
check("6. description with a colon kept", m6.get("description") == "Ghi chú: ví dụ có dấu hai chấm", m6)
check("6. tags kept as a list", m6.get("tags") == ["vi-du"], m6)
check("6. new type written", m6.get("type") == "business", m6)

# 7. no frontmatter: one is created with the source
f7 = facts / "tran.md"
f7.write_text("Chỉ có nội dung.\n", encoding="utf-8")
mc.stamp_new_facts(mem, source="chat: có dấu hai chấm", since=0)
m7 = meta_of(f7)
check("7. a frontmatter is created", isinstance(m7, dict) and m7.get("source") == "chat: có dấu hai chấm", m7)
check("7. the body is kept", f7.read_text(encoding="utf-8").endswith("---\nChỉ có nội dung.\n"))

# 8. CRLF
f8 = facts / "crlf.md"
f8.write_bytes(VALID.replace("\n", "\r\n").encode("utf-8"))
mc.stamp_new_facts(mem, source="chat crlf", since=0)
m8 = meta_of(f8)
check("8. CRLF file still parses with the source", isinstance(m8, dict) and m8.get("source") == "chat crlf"
      and m8.get("description") == "Ghi chú: ví dụ có dấu hai chấm", m8)

if fails:
    raise SystemExit(f"{len(fails)} check(s) failed: {fails}")
print("all ok")
