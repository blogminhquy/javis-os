"""Links to files OUTSIDE the brain open with the owner's own app, only from this machine.

    python tests/python/test_open_local.py

Owner request 2026-11-09: Javis builds teaching decks in ~/Documents and names them in chat, but the
chat only linked brain files, so the name was dead text. POST /files/open-local asks the OS to open
the file. These checks pin the guard rails: no tunnel or proxy, only inside the home folder, only
document types are opened, programs and scripts are only revealed. No network, nothing is launched.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import os
import tempfile
from pathlib import Path

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-openlocal-")

import main  # noqa: E402
import local_open  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

_fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + ("" if cond or not extra else "  " + str(extra)))
    if not cond:
        _fails.append(name)


home = Path(tempfile.mkdtemp(prefix="javis-home-")).resolve()
outside = Path(tempfile.mkdtemp(prefix="javis-outside-")).resolve()
(home / "Documents").mkdir()
deck = home / "Documents" / "06 Vocab.html"
deck.write_text("<h1>x</h1>")
script = home / "Documents" / "run.command"
script.write_text("echo hi")
app_dir = home / "Applications" / "Thing.app"
app_dir.mkdir(parents=True)
secret = outside / "a.html"
secret.write_text("x")
(home / "link-out.html").symlink_to(secret)

# ---- resolve_target / plan ----
check("absolute file in home resolves", local_open.resolve_target(str(deck), [home]) == deck)
check("file:// URI with %20 resolves", local_open.resolve_target("file://" + str(deck).replace(" ", "%20"), [home]) == deck)
for bad, code in (("Documents/06 Vocab.html", "not_absolute"), (str(secret), "outside"),
                  (str(home / "link-out.html"), "outside"), (str(home / "nope.html"), "missing"),
                  (str(home / "Documents" / ".." / ".." / secret.name), "outside")):
    try:
        local_open.resolve_target(bad, [home])
        got = "none"
    except local_open.LocalOpenError as e:
        got = e.code
    check(f"refuses {bad!r} as {code}", got == code, got)
check("html opens", local_open.plan(deck) == "open")
check(".command is only revealed", local_open.plan(script) == "reveal")
check(".app bundle is only revealed", local_open.plan(app_dir) == "reveal")
check("plain folder opens", local_open.plan(home / "Documents") == "open")

# ---- endpoint ----
launched = []
local_open.launch = lambda action, target: launched.append((action, target))
main.Path.home = staticmethod(lambda: home)
main.cfgmod.gate_active = lambda: False
main.cfgmod.auth_enabled = lambda: False
main.cfgmod.require_login = lambda: False

local = TestClient(main.app, base_url="http://127.0.0.1:7777", client=("127.0.0.1", 50000))
remote = TestClient(main.app, base_url="http://127.0.0.1:7777", client=("203.0.113.9", 50000))

r = local.post("/files/open-local", data={"path": str(deck)})
check("local click opens the deck", r.status_code == 200 and r.json().get("action") == "open"
      and launched[-1] == ("open", deck), (r.status_code, r.text))
r = local.post("/files/open-local", data={"path": str(script)})
check("local click on a script only reveals it", r.status_code == 200 and launched[-1] == ("reveal", script))
n = len(launched)
r = local.post("/files/open-local", data={"path": str(deck)}, headers={"cf-connecting-ip": "198.51.100.7"})
check("through a tunnel: 403", r.status_code == 403 and len(launched) == n, r.status_code)
r = remote.post("/files/open-local", data={"path": str(deck)})
check("from another machine: 403", r.status_code == 403 and len(launched) == n, r.status_code)
r = local.post("/files/open-local", data={"path": str(secret)})
check("outside home: 400, nothing launched", r.status_code == 400 and len(launched) == n, r.status_code)
r = local.post("/files/open-local", data={"path": str(home / "gone.html")})
check("missing file: 404", r.status_code == 404 and r.json().get("code") == "missing", r.status_code)
r = local.post("/files/open-local", data={"path": str(deck)}, headers={"origin": "http://evil.example"})
check("cross-origin POST is blocked", r.status_code == 403 and len(launched) == n, r.status_code)

# ---- GET: is the link worth drawing for this browser? ----
local_open.can_launch = lambda: True
tunnel = {"cf-connecting-ip": "198.51.100.7"}
check("on this machine: available", local.get("/files/open-local").json() == {"available": True})
check("through a tunnel: not available", local.get("/files/open-local", headers=tunnel).json() == {"available": False})
check("from another machine: not available", remote.get("/files/open-local").json() == {"available": False})
local_open.can_launch = lambda: False
check("a machine with nothing to open files with: not available",
      local.get("/files/open-local").json() == {"available": False})
real_exists = main.os.path.exists
main.os.path.exists = lambda p: True if str(p) == "/.dockerenv" else real_exists(p)
local_open.can_launch = lambda: True
try:
    check("inside Docker: not available", local.get("/files/open-local").json() == {"available": False})
    r = local.post("/files/open-local", data={"path": str(deck)})
    check("inside Docker: a click is refused too", r.status_code == 403 and len(launched) == n, r.status_code)
finally:
    main.os.path.exists = real_exists
check("asking never launched anything", len(launched) == n)

if _fails:
    raise SystemExit(f"\nFAIL - test_open_local: {len(_fails)} check(s) failed")
print("\nOK - test_open_local: all pass")
