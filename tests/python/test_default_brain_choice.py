"""The default brain is a choice (2026-11-09): make another brain the default, then the old one can be deleted.

Owner: "liệu có thể cho quyền xóa default brain không" then "đặt làm mặc định cái khác thì xóa được cái mặc định hiện
tại". Covers server/default_brain.py, POST /brains/default, GET /brains/ties and what follows the default.

    python tests/run.py default_brain_choice
"""
from _paths import ROOT, SERVER  # noqa: E402,F401  - puts server/ on sys.path (tests/python/_paths.py)
import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="jv-defbrain-state-"))
BR = Path(tempfile.mkdtemp(prefix="jv-defbrain-brains-")).resolve()
os.environ["BRAINS_DIR"] = str(BR)

import main  # noqa: E402
import brain_ident  # noqa: E402
import default_brain  # noqa: E402
import git_brain as gb  # noqa: E402
import mcp_hub  # noqa: E402
import image_gen  # noqa: E402

_fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)


main.BRAINS_DIR = str(BR)
old = BR / "Brain Default"
old.mkdir(parents=True, exist_ok=True)
(old / "n.md").write_text("old", encoding="utf-8")
shop = BR / "Shop"
shop.mkdir(parents=True)
(shop / "n.md").write_text("shop", encoding="utf-8")


def body(r):
    return json.loads(r.body) if hasattr(r, "body") else r


# ---- the module on its own ----
check("no choice yet: the default is Brain Default", default_brain.folder(BR) == "Brain Default")
check("valid_folder refuses path tricks and hidden names",
      not any(default_brain.valid_folder(n) for n in ("", ".", "..", "../x", "a/b", ".hidden", " pad", "a\\b")))
check("valid_folder takes a plain name with spaces and accents", default_brain.valid_folder("Ngọc Thu Phạm"))
check("set_folder refuses a missing folder", default_brain.set_folder(BR, "Nope") == (False, "missing"))
check("set_folder refuses a bad name", default_brain.set_folder(BR, "../Shop") == (False, "invalid"))
check("a refused choice leaves no file", not default_brain.pointer_path(BR).exists())
(BR / default_brain.POINTER_FILE).write_text("{not json", encoding="utf-8")
check("an unreadable pointer falls back to Brain Default", default_brain.folder(BR) == "Brain Default")
(BR / default_brain.POINTER_FILE).write_text(json.dumps({"folder": "../etc"}), encoding="utf-8")
check("a pointer with a bad name falls back to Brain Default", default_brain.folder(BR) == "Brain Default")
(BR / default_brain.POINTER_FILE).unlink()

# ---- the old default cannot be deleted while it is the default ----
r = asyncio.run(main.delete_brain(name="Brain Default", confirm="Brain Default"))
check("deleting the current default is refused", getattr(r, "status_code", 0) == 400)
_err = body(r).get("error", "")
check("the refusal says how to get there", "mặc định trước" in _err or "default first" in _err)

# ---- make Shop the default ----
r = asyncio.run(main.brain_set_default(brain="path:" + str(shop)))
d = body(r)
check("POST /brains/default answers ok", d.get("ok") is True and d.get("name") == "Shop")
check("it names the previous default", d.get("previous") == "Brain Default")
ptr = json.loads((BR / default_brain.POINTER_FILE).read_text(encoding="utf-8"))
check("the choice is a file at the top of BRAINS_DIR", ptr.get("folder") == "Shop")
check("the pointer is text the GitHub backup carries", gb.la_file_chu(default_brain.POINTER_FILE)
      and not gb._backup_skip(default_brain.POINTER_FILE))
check("_default_brain_dir follows the choice", main._default_brain_dir().resolve() == shop)
check("the short name 'brain' resolves to Shop", Path(main._brain_root("brain")).resolve() == shop)
check("brain_ident agrees", brain_ident.same_brain("brain", str(shop)) and not brain_ident.same_brain("brain", str(old)))
check("the MCP hub's 'brain' is Shop", mcp_hub._brain_tu_phien("brain") == str(shop))
check("image generation's fallback vault is Shop", Path(image_gen._default_vault()).resolve() == shop)

lst = main._list_brains_sync()["brains"]
flags = {b["name"]: b["is_default"] for b in lst}
check("the brain list marks Shop as the default and only Shop", flags == {"Brain Default": False, "Shop": True})
check("the pointer file is not listed as a brain", all(not b["name"].startswith(".") for b in lst))

r = asyncio.run(main.brain_set_default(brain="Shop"))
check("making the default the default again is a no-op", body(r).get("unchanged") is True)
r = asyncio.run(main.brain_set_default(brain="path:/etc"))
check("a folder outside BRAINS_DIR cannot be the default", getattr(r, "status_code", 0) == 404)
(shop / "sub").mkdir()
r = asyncio.run(main.brain_set_default(brain="path:" + str(shop / "sub")))
check("a folder nested inside a brain cannot be the default", getattr(r, "status_code", 0) == 404)

# ---- the old default keeps its loops running: the scheduler now needs it registered ----
known = {str(Path(main._brain_root(b)).resolve()) for b in main.loop_feature.scheduler_brains()}
check("the old default stays on the loop scheduler's list", str(old) in known)

# ---- now the old default deletes like any brain ----
r = asyncio.run(main.brain_ties(brain="path:" + str(old)))
d = body(r)
check("GET /brains/ties answers for the old default", d.get("ok") is True and "bots" in d and "loops" in d)
r = asyncio.run(main.delete_brain(name="Brain Default", confirm="Brain Default"))
check("the old default can be deleted now", body(r).get("ok") is True)
check("it left BRAINS_DIR", not old.exists())
check("a tombstone spreads the delete", (BR / gb.TOMBSTONE_DIR / "Brain Default.json").exists())
main._default_brain_dir()
main._ensure_default_brain()
check("nothing brings Brain Default back on the next call or at startup", not old.exists())
check("the backup no longer protects it", main._default_brain_dir().name == "Shop")

r = asyncio.run(main.delete_brain(name="Shop", confirm="Shop"))
check("the new default cannot be deleted", getattr(r, "status_code", 0) == 400 and shop.is_dir())

# ---- a sync restores the CHOSEN default, not the old one ----
mirror = Path(tempfile.mkdtemp(prefix="jv-defbrain-mirror-"))
gb._git(str(mirror), "init")
(mirror / "Brain Default").mkdir()
(mirror / "Brain Default" / "n.md").write_text("old", encoding="utf-8")
gb._restore_missing_brains(str(BR), str(mirror), {main._default_brain_dir().name})
check("a tombstoned old default is not restored from the backup", not old.exists())

# ---- ties: a bot that answers from a brain is named before a delete ----
team = BR / "Team"
team.mkdir()
_orig = main.chatbot_store.list_bots
main.chatbot_store.list_bots = lambda: [
    {"id": "b1", "name": "Zalo Shop", "brain": str(team)},
    {"id": "b2", "name": "Uses an agent", "brain": "brain", "agent": {"brain": str(team), "slug": "x"}},
    {"id": "b3", "name": "Elsewhere", "brain": "brain"},
]
try:
    d = body(asyncio.run(main.brain_ties(brain="Team")))
finally:
    main.chatbot_store.list_bots = _orig
check("ties list the bots answering from the brain or using its agent",
      sorted(b["name"] for b in d.get("bots", [])) == ["Uses an agent", "Zalo Shop"])
r = asyncio.run(main.brain_ties(brain="path:/etc"))
check("ties refuse a folder outside BRAINS_DIR", getattr(r, "status_code", 0) == 404)

print()
print("ALL PASS" if not _fails else f"{len(_fails)} FAIL: {_fails}")
sys.exit(1 if _fails else 0)
