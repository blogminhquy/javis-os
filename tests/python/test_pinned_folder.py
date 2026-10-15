"""Pinned working folder for normal chats (0.158.0).

    python tests/run.py pinned_folder
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import os
import shutil
import sys
import tempfile

STATE = tempfile.mkdtemp(prefix="javis-pin-")
os.environ["JAVIS_STATE_DIR"] = STATE
from fastapi.testclient import TestClient  # noqa: E402
import coding_store  # noqa: E402
import main  # noqa: E402

fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(extra) + "]") if extra and not cond else ""))
    if not cond:
        fails.append(name)


def real(p):
    return os.path.realpath(p)


brain = tempfile.mkdtemp(prefix="javis-pin-brain-")
outside = tempfile.mkdtemp(prefix="javis-pin-out-")
try:
    proj = os.path.join(brain, "projects", "shop-site")
    os.makedirs(proj)

    # 1. Prompt block for a normal chat with a pinned folder.
    rec = coding_store.them_thu_muc(proj, brain=brain)
    coding_store.dat_rang_buoc("s-in", thu_muc_id=rec["id"])
    block = coding_store.pinned_folder_prompt("s-in", brain)
    check("block names the absolute working folder", real(proj) in block, block)
    check("block gives the brain-relative path for API brains", "projects/shop-site" in block, block)
    check("block never states a permission level",
          "Toàn quyền" not in block and "Tự động" not in block and "Plan" not in block, block)

    rec2 = coding_store.them_thu_muc(outside, brain=brain)
    coding_store.dat_rang_buoc("s-out", thu_muc_id=rec2["id"])
    block2 = coding_store.pinned_folder_prompt("s-out", brain)
    check("outside folder: absolute path, no brain-relative line",
          real(outside) in block2 and "nằm trong brain" not in block2, block2)
    check("no folder: empty block", coding_store.pinned_folder_prompt("s-none", brain) == "")

    # 2. main wires the block for normal chats and keeps the coding block and permission level.
    row_chat = {"id": "s-in", "channel": "web"}
    row_code = {"id": "s-in", "channel": "coding:phien"}
    check("normal chat with a pin gets the pinned block", "projects/shop-site" in main._khoi_coding(row_chat, brain))
    check("coding session still gets the coding block",
          main._khoi_coding(row_code, brain) == coding_store.khoi_prompt("s-in"))
    check("normal chat with a pin still runs at full", main._muc_quyen_luot_chat(row_chat) == "full")
    check("turn cwd follows the pin for a normal chat", main._cwd_luot_chat(row_chat, brain) == real(proj))

    # 3. One-call pin endpoint.
    c = TestClient(main.app, base_url="http://localhost")
    r = c.post("/coding/session/s-api/pin", data={"path": proj, "brain": brain})
    j = r.json()
    check("pin by absolute path binds the folder",
          r.status_code == 200 and j.get("ok") and (j.get("folder") or {}).get("name") == "shop-site", j)
    check("pin reports in_brain and brain_rel",
          j.get("in_brain") is True and j.get("brain_rel") == "projects/shop-site", j)
    check("folder view is English", set((j.get("folder") or {}).keys()) == {"id", "name", "path", "exists", "is_git"}, j)
    check("session cwd follows the pin", coding_store.cwd_cua_phien("s-api") == real(proj))
    g = c.get("/coding/session/s-api", params={"brain": brain}).json()
    check("GET session with brain returns folder and in_brain",
          (g.get("folder") or {}).get("name") == "shop-site" and g.get("in_brain") is True, g)

    bad = c.post("/coding/session/s-api/pin", data={"path": "../../../../no-such-place-xyz", "brain": brain})
    check("relative path escaping the ceiling or missing is rejected", bad.status_code == 400, bad.text)
    check("rejected pin keeps the previous folder", coding_store.cwd_cua_phien("s-api") == real(proj))

    rel = c.post("/coding/session/s-rel/pin", data={"path": "projects/shop-site", "brain": brain})
    check("pin by a brain-relative path works", rel.status_code == 200 and coding_store.cwd_cua_phien("s-rel") == real(proj), rel.text)

    # Re-pinning the folder that is already pinned must not drop the worktree, branch or extra folders.
    coding_store.dat_rang_buoc("s-api", worktree=outside, nhanh="feature-x",
                               thu_muc_ids=[coding_store.rang_buoc("s-api")["thu_muc"], rec2["id"]])
    again = c.post("/coding/session/s-api/pin", data={"path": proj, "brain": brain})
    rb = coding_store.rang_buoc("s-api")
    check("re-pinning the same folder keeps worktree, branch and extra folders",
          again.status_code == 200 and rb.get("worktree") == outside and rb.get("nhanh") == "feature-x"
          and len(rb.get("thu_mucs") or []) == 2, rb)
    coding_store.dat_rang_buoc("s-api", worktree="", thu_muc_ids=[rb["thu_muc"]])

    off = c.post("/coding/session/s-api/pin", data={"path": "", "brain": brain}).json()
    check("empty path unpins", off.get("ok") and off.get("folder") is None and coding_store.cwd_cua_phien("s-api") == "", off)

    # 3b. Small follow-ups (0.159.0).
    for i in range(40):
        open(os.path.join(brain, "shop-note-%d.md" % i), "w", encoding="utf-8").write("x")
    s = c.get("/files/search", params={"brain": brain, "q": "shop", "mode": "name", "only_dirs": "true", "limit": 30}).json()
    items = s.get("items") or []
    check("folder search with only_dirs lists folders even when many files match",
          items and all(x.get("type") == "dir" for x in items) and any(x.get("name") == "shop-site" for x in items), items[:3])

    extra_dir = os.path.join(brain, "docs-extra")
    os.makedirs(extra_dir)
    rec3 = coding_store.them_thu_muc(extra_dir, brain=brain)
    c.post("/coding/session/s-x/pin", data={"path": proj, "brain": brain})
    coding_store.dat_rang_buoc("s-x", thu_muc_ids=[coding_store.rang_buoc("s-x")["thu_muc"], rec3["id"]])
    gx = c.get("/coding/session/s-x", params={"brain": brain}).json()
    check("session reports its extra folders so the chip can show +N",
          gx.get("extra_folders") == ["docs-extra"], gx.get("extra_folders"))

    solo = os.path.join(brain, "solo")
    os.makedirs(solo)
    js = c.post("/coding/session/s-solo/pin", data={"path": solo, "brain": brain}).json()
    solo_id = (js.get("folder") or {}).get("id")
    c.post("/coding/session/s-solo/pin", data={"path": "", "brain": brain})
    check("unpinning a folder no other conversation uses forgets it from the registry",
          solo_id and coding_store.thu_muc(solo_id) is None, solo_id)
    proj_id = coding_store.rang_buoc("s-in")["thu_muc"]
    c.post("/coding/session/s-rel/pin", data={"path": "", "brain": brain})
    check("a folder still used by another conversation stays registered", coding_store.thu_muc(proj_id) is not None)

    c.post("/coding/session/s-x/pin", data={"path": "", "brain": brain})
    check("unpinning also forgets extra folders nobody else uses", coding_store.thu_muc(rec3["id"]) is None)
    check("but keeps a folder another conversation still uses", coding_store.thu_muc(proj_id) is not None)

    import routes.coding as coding_routes  # noqa: E402
    keep = coding_routes._DEPS.resolve_path

    def _outside(b, rel):
        raise ValueError("outside the browse ceiling")
    coding_routes._DEPS.resolve_path = _outside
    try:
        r_out = c.post("/coding/session/s-y/pin", data={"path": "anything", "brain": brain})
    finally:
        coding_routes._DEPS.resolve_path = keep
    check("a path the ceiling rejects returns 400 with that message",
          r_out.status_code == 400 and "outside the browse ceiling" in r_out.text, r_out.text)
    src = open(os.path.join(SERVER, "routes", "coding.py"), encoding="utf-8").read()
    check("GET session and /pin run git and disk work off the event loop", src.count("run_in_threadpool(") >= 2)

    # 4. Folder deleted from disk: the turn falls back to the brain, the block disappears.
    shutil.rmtree(outside)
    check("folder deleted from disk: empty block", coding_store.pinned_folder_prompt("s-out", brain) == "")
finally:
    shutil.rmtree(brain, ignore_errors=True)
    shutil.rmtree(outside, ignore_errors=True)
    shutil.rmtree(STATE, ignore_errors=True)

if fails:
    print("\nFAIL - test_pinned_folder: %d" % len(fails))
    sys.exit(1)
print("\nOK - test_pinned_folder: all pass")
