"""Agent run logs and text under attachments never reach the GitHub backup (customer report 0.270, code 14).

The brain .gitignore ignores both, but it is only written when learning is on, so a brain without it pushed
`memory/agents/<slug>/runs/*.md` and the text Javis extracts from Team attachments. The backup filter now keeps them
out by itself, and treats copies an older version already pushed as out of scope (not overwritten, not deleted, not
applied back), so a machine still on an older version never loses its local copies.

Run: python tests/python/test_backup_raw_kept_out.py (needs git, uses a local file:// remote, no network).
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import subprocess
import sys
import tempfile
from pathlib import Path

import git_brain as gb  # noqa: E402

_fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)


# ---- the filter itself ----
skip = gb._backup_skip
check("run log skipped", skip("b/memory/agents/viet-email/runs/2026-10-18.md"))
check("run log skipped (capital Memory)", skip("b/Memory/agents/x/runs/2026-10-18.md"))
check("run log skipped (nested under runs)", skip("b/memory/agents/x/runs/sub/a.json"))
check("agent MEMORY.md still backed up", not skip("b/memory/agents/x/MEMORY.md"))
check("other agent file still backed up", not skip("b/memory/agents/x/notes.md"))
check("a folder named runs elsewhere still backed up", not skip("b/projects/runs/plan.md"))
check("team attachment text skipped", skip("b/attachments/teams/T1/hop-dong.txt"))
check("numbered Attachments text skipped", skip("b/05 - Attachments/bang-gia.csv"))
check("attachment image still follows sync_images (on)", not skip("b/attachments/sp.jpg", sync_images=True))
check("attachment image still follows sync_images (off)", skip("b/attachments/sp.jpg"))
check("ordinary note still backed up", not skip("b/wiki/note.md"))
check("file merely named attachments.md still backed up", not skip("b/wiki/attachments.md"))

if not gb.has_git():
    print("SKIP integration: git is not installed")
    sys.exit(1 if _fails else 0)

TMP = Path(tempfile.mkdtemp(prefix="jv-rawout-")).resolve()
REMOTE = TMP / "remote.git"
subprocess.run(["git", "init", "--bare", str(REMOTE)], capture_output=True)
URL = "file:///" + str(REMOTE).replace("\\", "/").lstrip("/")


def machine(tag):
    b, m, t = TMP / tag / "brains", TMP / tag / "mirror", TMP / tag / "trash"
    b.mkdir(parents=True, exist_ok=True)
    return str(b), str(m), str(t)


def w(path, text):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(text, encoding="utf-8")


def sync(b, m, t):
    return gb.sync_brains(b, m, URL, "x", "main", trash_dir=t, protected_names=set())


def remote_files():
    r = subprocess.run(["git", "--git-dir", str(REMOTE), "ls-tree", "-r", "--name-only", "main"],
                       capture_output=True, text=True)
    return set((r.stdout or "").split())


def remote_show(rel):
    r = subprocess.run(["git", "--git-dir", str(REMOTE), "show", f"main:{rel}"], capture_output=True, text=True)
    return r.stdout if r.returncode == 0 else None


RUN = "Shop/memory/agents/viet-email/runs/2026-10-18.md"
TXT = "Shop/attachments/teams/T1/hop-dong.txt"

# ---- a brain WITHOUT .gitignore (learning off): only knowledge goes up ----
Ab, Am, At = machine("A")
w(Path(Ab) / "Shop/wiki/note.md", "knowledge")
w(Path(Ab) / "Shop/memory/agents/viet-email/MEMORY.md", "lessons")
w(Path(Ab) / RUN, "raw run log with a customer phone number")
w(Path(Ab) / TXT, "text extracted from a contract")
check("brain has no .gitignore (the case in the report)", not (Path(Ab) / "Shop/.gitignore").exists())
r = sync(Ab, Am, At)
files = remote_files()
check("A: sync ok", r.get("ok") and r.get("pushed"))
check("A: note pushed", "Shop/wiki/note.md" in files)
check("A: agent MEMORY.md pushed", "Shop/memory/agents/viet-email/MEMORY.md" in files)
check("A: run log NOT pushed", RUN not in files)
check("A: attachment text NOT pushed", TXT not in files)
check("A: local raw files untouched", (Path(Ab) / RUN).exists() and (Path(Ab) / TXT).exists())

# ---- an older version (no filter) already pushed raw files ----
Ob, Om, Ot = machine("Old")
w(Path(Ob) / RUN, "old machine run log")
_orig = gb._raw_kept_out
gb._raw_kept_out = lambda rel: False
try:
    r = sync(Ob, Om, Ot)
finally:
    gb._raw_kept_out = _orig
check("old version: raw run log reached the remote", r.get("ok") and RUN in remote_files())

# The updated machine A syncs again with its own, different run log.
w(Path(Ab) / RUN, "raw run log, appended")
w(Path(Ab) / "Shop/wiki/note2.md", "more knowledge")
r = sync(Ab, Am, At)
files = remote_files()
check("A again: sync ok", r.get("ok") and r.get("pushed"))
check("A again: new note pushed", "Shop/wiki/note2.md" in files)
check("A again: does NOT delete the old version's run log from the repo", RUN in files)
check("A again: does NOT overwrite it with its own run log", remote_show(RUN) == "old machine run log")
check("A again: its own local run log is not replaced by the repo copy",
      (Path(Ab) / RUN).read_text(encoding="utf-8") == "raw run log, appended")

# The older machine syncs: nothing it pushed was deleted, so its local copy survives.
r = sync(Ob, Om, Ot)
check("old version: local run log still there", r.get("ok") and (Path(Ob) / RUN).exists())

# A fresh updated machine restoring from the repo does not pull raw files back.
Nb, Nm, Nt = machine("New")
r = sync(Nb, Nm, Nt)
check("new machine: knowledge restored", r.get("ok") and (Path(Nb) / "Shop/wiki/note.md").exists())
check("new machine: raw run log not restored", not (Path(Nb) / RUN).exists())

# ---- deleting a brain on purpose also clears the raw leftovers in the mirror ----
# An older version copied the run log into the mirror; the brain's .gitignore kept it untracked there, and the
# updated version never prunes it, so only the tombstone step can clean it up.
w(Path(Ab) / "Gone/wiki/a.md", "x")
w(Path(Ab) / "Gone/memory/agents/x/runs/2026-10-18.md", "raw")
gb._ensure_gitignore_lines(str(Path(Ab) / "Gone"))
gb._raw_kept_out = lambda rel: False
try:
    sync(Ab, Am, At)
finally:
    gb._raw_kept_out = _orig
sync(Ab, Am, At)
check("Gone: untracked raw leftover sits in the mirror",
      (Path(Am) / "Gone/memory/agents/x/runs/2026-10-18.md").exists()
      and "Gone/memory/agents/x/runs/2026-10-18.md" not in remote_files())
gb.move_to_trash(str(Path(Ab) / "Gone"), At, "Gone")
gb.write_tombstone(Ab, "Gone")
r = sync(Ab, Am, At)
check("Gone: sync ok", r.get("ok"))
check("Gone: mirror folder removed, so it cannot come back after the tombstone expires",
      not (Path(Am) / "Gone").exists())

print()
print("ALL PASS" if not _fails else f"{len(_fails)} FAIL: {_fails}")
sys.exit(1 if _fails else 0)
