"""Pinned folders and folders open by default in the Vault tree (server/vault_tree_prefs.py, 2026-11-11).

    python tests/run.py vault_tree_prefs
"""
import os
import sys
import tempfile
from pathlib import Path

import _paths  # noqa: F401  (puts server/ on sys.path)

# The routes write settings.json: point the whole process at a throwaway state folder before config is imported.
_state = tempfile.mkdtemp(prefix="javis-tree-prefs-")
os.environ["JAVIS_STATE_DIR"] = _state
os.environ["BRAINS_DIR"] = os.path.join(_state, "brains")
os.environ["JAVIS_SESSIONS_DB"] = os.path.join(_state, "sessions.db")

import vault_tree_prefs as vt  # noqa: E402

fails = 0


def check(name, ok, detail=""):
    global fails
    print(("ok   " if ok else "FAIL ") + name + ("" if ok else "  " + str(detail)))
    if not ok:
        fails += 1


got = vt.clean_paths(["03 - Wiki", "/projects/shop/", "a\\b", "03 - Wiki", "", "../x", "a/../b", "a//b", ".", 5, None])
check("clean_paths keeps brain-relative folders, POSIX style, once each",
      got == ["03 - Wiki", "projects/shop", "a/b"], got)
check("clean_paths refuses a non-list", vt.clean_paths("abc") == [] and vt.clean_paths(None) == [])
check("clean_paths caps the list", len(vt.clean_paths([f"d{i}" for i in range(vt.MAX_ITEMS + 20)])) == vt.MAX_ITEMS)
check("clean always answers both lists", vt.clean(None) == {"pinned": [], "open": []}
      and vt.clean({"pinned": ["a"], "open": "x", "other": 1}) == {"pinned": ["a"], "open": []})

with tempfile.TemporaryDirectory() as tmp:
    brain = Path(tmp) / "brain"
    (brain / "03 - Wiki").mkdir(parents=True)
    (brain / "projects" / "shop").mkdir(parents=True)
    (brain / "note.md").write_text("x", encoding="utf-8")
    other = Path(tmp) / "other"
    other.mkdir()

    patch = vt.patch(brain, {"pinned": ["03 - Wiki", "gone", "note.md"], "open": ["projects/shop", "../other"]})
    key = vt.brain_key(brain)
    check("patch stores the cleaned pair under the brain's resolved root",
          patch == {vt.SETTINGS_KEY: {key: {"pinned": ["03 - Wiki", "gone", "note.md"], "open": ["projects/shop"]}}}, patch)

    got = vt.read(patch, brain)
    check("read leaves out folders that are gone and anything that is not a folder",
          got == {"pinned": ["03 - Wiki"], "open": ["projects/shop"]}, got)
    check("read answers empty lists for a brain with nothing saved", vt.read(patch, other) == {"pinned": [], "open": []})
    check("read survives a missing or broken store",
          vt.read({}, brain) == {"pinned": [], "open": []} and vt.read({vt.SETTINGS_KEY: "x"}, brain) == {"pinned": [], "open": []})

    # A rename or a delete through Javis takes the saved entries along.
    saved = vt.patch(brain, {"pinned": ["projects", "03 - Wiki"], "open": ["projects/shop", "projects-old"]})
    got = vt.moved(saved, brain, brain / "projects", brain / "work")
    check("a renamed folder keeps its entries, and so do the folders inside it",
          got == vt.patch(brain, {"pinned": ["work", "03 - Wiki"], "open": ["work/shop", "projects-old"]}), got)
    got = vt.moved(saved, brain, brain / "projects", None)
    check("a deleted folder drops its entries and those inside it",
          got == vt.patch(brain, {"pinned": ["03 - Wiki"], "open": ["projects-old"]}), got)
    check("a folder nobody saved changes nothing", vt.moved(saved, brain, brain / "inbox", brain / "in") is None)
    check("the brain root itself and paths outside it change nothing",
          vt.moved(saved, brain, brain, None) is None and vt.moved(saved, brain, other, None) is None)

    # A symlink that leaves the brain must not be answered as a folder of the brain.
    try:
        (brain / "leak").symlink_to(other, target_is_directory=True)
        got = vt.read(vt.patch(brain, {"pinned": ["leak"], "open": []}), brain)
        check("a link pointing outside the brain is not listed", got["pinned"] == [], got)
    except (OSError, NotImplementedError):
        print("skip a link pointing outside the brain (no symlink support here)")

    # The two routes, end to end, on a bare app (main.app adds the login and host guards, which are not under test).
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    import main

    app = FastAPI()
    app.get("/files/tree-prefs")(main.files_tree_prefs)
    app.post("/files/tree-prefs")(main.files_tree_prefs_save)
    client = TestClient(app)
    r = client.get("/files/tree-prefs", params={"brain": str(brain)})
    check("GET answers empty lists before anything is saved",
          r.status_code == 200 and r.json() == {"ok": True, "pinned": [], "open": []}, r.text)
    r = client.post("/files/tree-prefs", data={"brain": str(brain), "pinned": '["03 - Wiki"]',
                                               "open": '["03 - Wiki", "projects/shop"]'})
    check("POST saves both lists", r.status_code == 200 and r.json() == {
        "ok": True, "pinned": ["03 - Wiki"], "open": ["03 - Wiki", "projects/shop"]}, r.text)
    r = client.get("/files/tree-prefs", params={"brain": str(brain)})
    check("GET reads them back", r.json() == {"ok": True, "pinned": ["03 - Wiki"], "open": ["03 - Wiki", "projects/shop"]}, r.text)
    r = client.get("/files/tree-prefs", params={"brain": str(other)})
    check("another brain keeps its own lists", r.json() == {"ok": True, "pinned": [], "open": []}, r.text)
    r = client.post("/files/tree-prefs", data={"brain": str(brain), "pinned": "[]", "open": '["projects/shop"]'})
    r = client.get("/files/tree-prefs", params={"brain": str(brain)})
    check("saving an empty list unpins", r.json() == {"ok": True, "pinned": [], "open": ["projects/shop"]}, r.text)
    app.post("/files/rename")(main.files_rename)
    app.post("/files/delete")(main.files_delete)
    r = client.post("/files/rename", data={"brain": str(brain), "path": main._files_rel(main._files_root(str(brain)),
                    (brain / "projects").resolve()), "newname": "work"})
    got = client.get("/files/tree-prefs", params={"brain": str(brain)}).json()
    check("renaming a folder in the file browser keeps the folder inside it open by default",
          r.status_code == 200 and got == {"ok": True, "pinned": [], "open": ["work/shop"]}, (r.text, got))
    r = client.post("/files/delete", data={"brain": str(brain), "path": main._files_rel(main._files_root(str(brain)),
                    (brain / "work").resolve())})
    stored = main.cfgmod.read_settings()[vt.SETTINGS_KEY][vt.brain_key(brain)]
    check("deleting it removes the entry from the store", r.status_code == 200 and stored == {"pinned": [], "open": []},
          (r.text, stored))
    r = client.post("/files/tree-prefs", data={"brain": str(brain), "pinned": "{oops", "open": "[]"})
    check("a broken list is refused with 400", r.status_code == 400 and r.json().get("ok") is False, r.text)

if fails:
    print(f"FAIL - test_vault_tree_prefs: {fails}")
    sys.exit(1)
print("OK - test_vault_tree_prefs: all pass")
