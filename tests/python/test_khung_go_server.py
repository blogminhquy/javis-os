"""New composer (0.153.0): the Fast mode settings key and resolving a file already in the brain.

    python tests/run.py khung_go_server
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import json
import shutil
import uuid
import os
import sys
import tempfile
from pathlib import Path

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-khunggo-")
from fastapi.testclient import TestClient  # noqa: E402
import main  # noqa: E402
import config as cfgmod  # noqa: E402

fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(extra) + "]") if extra and not cond else ""))
    if not cond:
        fails.append(name)


client = TestClient(main.app, base_url="http://localhost")   # fresh STATE_DIR: no account yet, so no login needed (like test_messenger)

# 1. fast is saved and only accepts a boolean
s = cfgmod.read_settings()
check("fast is off by default", (s.get("model") or {}).get("fast") is False, s.get("model"))
r = client.post("/settings", data={"section": "model", "data": json.dumps({"fast": True})})
check("POST /settings saves fast=true", r.status_code == 200 and cfgmod.read_settings()["model"]["fast"] is True, r.text)
client.post("/settings", data={"section": "model", "data": json.dumps({"fast": "yes"})})
check("a non-boolean value is read as false", cfgmod.read_settings()["model"]["fast"] is False)

# 2. /files/resolve
# _brain_root points at the checkout's REAL brain: use a randomly named folder and always remove it.
brain = Path(main._brain_root("brain"))
TMPDIR = brain / ("_test-khung-go-" + uuid.uuid4().hex[:8])
TMPDIR.mkdir(parents=True, exist_ok=True)
outside_dir = Path(tempfile.mkdtemp(prefix="outside-"))
try:
    f = TMPDIR / "bao-cao.md"
    f.write_text("doanh thu", encoding="utf-8")
    root = Path(main._files_root("brain")).resolve()
    rel = f.resolve().relative_to(root).as_posix()
    r = client.get("/files/resolve", params={"brain": "brain", "path": rel})
    d = r.json()
    check("resolve returns the absolute path inside the brain", r.status_code == 200 and d.get("ok")
          and Path(d["path"]) == f.resolve() and d["name"] == "bao-cao.md" and d["kind"] == "file", d)
    for bad in ("../../etc/passwd", str(f.resolve()), "", TMPDIR.relative_to(root).as_posix() + "/missing.md"):
        r = client.get("/files/resolve", params={"brain": "brain", "path": bad})
        check(f"resolve rejects {bad!r}", r.status_code == 400 and r.json().get("ok") is False, r.text)
    outside = outside_dir / "x.txt"
    outside.write_text("x", encoding="utf-8")
    try:
        (TMPDIR / "link-out.txt").symlink_to(outside)
        r = client.get("/files/resolve", params={"brain": "brain", "path": (TMPDIR / "link-out.txt").relative_to(root).as_posix()})
        check("resolve rejects a symlink pointing outside the brain", r.status_code == 400, r.text)
    except OSError:
        print("skip symlink (this machine cannot create symlinks)")
finally:
    shutil.rmtree(TMPDIR, ignore_errors=True)
    shutil.rmtree(outside_dir, ignore_errors=True)

if fails:
    print("\nFAIL - test_khung_go_server: " + ", ".join(fails))
    sys.exit(1)
print("\nOK - test_khung_go_server: all pass")
