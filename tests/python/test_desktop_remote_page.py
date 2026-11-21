"""Remote control page of the desktop-apps plugin (/ext/desktop-apps/), for the owner's phone.

    python tests/run.py desktop_remote_page

Nothing real runs: every system function in remote.py (volume, screen, clipboard, lock, power,
folders) and the plugin's process functions are swapped for fakes. Locks:
  1. Through the real server: the page needs the owner's login, power is POST only, and a
     cross-origin POST is stopped by CSRF before the plugin sees it.
  2. Docker / not ready -> every action route answers with the reason and calls nothing.
  3. Files: only names directly inside Desktop / Downloads / Documents; no climbing out.
  4. Clipboard text is handed over as data (never built into a command); too long is refused.
  5. Power needs op AND confirm=true; apps reuse the plugin's open/close outcome words, and
     [unverified] is never reported as done; protected processes are not listed.
  6. The page renders in both languages with no leftover placeholder.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import importlib.util
import os
import tempfile
from pathlib import Path

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-remote-")
os.environ["JAVIS_REQUIRE_LOGIN"] = "1"

from fastapi.testclient import TestClient   # noqa: E402
from starlette.applications import Starlette  # noqa: E402
from starlette.routing import Route  # noqa: E402

_fails = []


def check(name, cond, them=""):
    print(("ok   " if cond else "FAIL ") + name + (f"  [{them}]" if them and not cond else ""))
    if not cond:
        _fails.append(name)


# ---- 1. through the real server ----
import config as cfg   # noqa: E402
import main            # noqa: E402
import plugins_host    # noqa: E402

_s = cfg.read_settings()
_s["auth"] = {"username": "admin", **dict(zip(("password_hash", "salt"), cfg.hash_password("matkhau123")))}
cfg.write_settings(_s)
la = TestClient(main.app)
chu = TestClient(main.app)
chu.post("/auth/login", data={"username": "admin", "password": "matkhau123"})

check("stranger -> 401 on the page", la.get("/ext/desktop-apps/").status_code == 401)
check("stranger -> 401 on an action", la.post("/ext/desktop-apps/api/lock").status_code == 401)
r = chu.get("/ext/desktop-apps/")
check("owner gets the HTML page", r.status_code == 200 and r.headers["content-type"].startswith("text/html")
      and "api/power" in r.text, r.status_code)
check("power is POST only (GET -> 404)", chu.get("/ext/desktop-apps/api/power").status_code == 404)
r = chu.post("/ext/desktop-apps/api/power", json={"op": "shutdown", "confirm": True},
             headers={"Origin": "https://trang-la.example"})
check("cross-origin power POST blocked by CSRF", r.status_code == 403, r.status_code)
d = {x["slug"]: x for x in plugins_host.describe(None)}
check("Plugin page shows an Open page button", d.get("desktop-apps", {}).get("page") == "/ext/desktop-apps/")

# ---- load the plugin on its own, with fakes ----
spec = importlib.util.spec_from_file_location(
    "desktop_apps_remote_test", ROOT / "system" / "plugins" / "desktop-apps" / "plugin.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class FakeCtx:
    def __init__(self):
        self.routes = []
        self.data_dir = Path(tempfile.mkdtemp(prefix="javis-remote-data-"))
        self.vault_root = None

    def register_tool(self, **kw):
        pass

    def register_http(self, path, handler, methods=("GET",), public=False, no_cookie=False):
        self.routes.append((path, handler, methods))


ctx = FakeCtx()
m.register(ctx)
R = m._REMOTE
check("register() adds the remote routes", {p for p, _, _ in ctx.routes} >= {
    "", "api/status", "api/apps", "api/app", "api/lock", "api/volume", "api/screen",
    "api/clipboard", "api/files", "api/file", "api/power", "api/favorites"})
check("every mutating route is POST only",
      all(meth == ("POST",) for p, _, meth in ctx.routes if p in ("api/app", "api/lock", "api/power", "api/favorites")))

calls = []
R.IS_WIN = True
R.volume = lambda op="": calls.append(("volume", op)) or {"level": 42, "muted": op == "mute"}
R.capture_screen = lambda: calls.append(("shot",)) or b"\x89PNGfake"
R.clipboard_get = lambda: calls.append(("clip_get",)) or "chu tren may"
R.clipboard_set = lambda t: calls.append(("clip_set", t))
R.lock_screen = lambda: calls.append(("lock",))
R.power = lambda op: calls.append(("power", op))
R.ps = lambda *a, **k: (_ for _ in ()).throw(AssertionError("real PowerShell called"))
R.spawn = lambda *a, **k: (_ for _ in ()).throw(AssertionError("real process spawned"))

roots_dir = Path(tempfile.mkdtemp(prefix="javis-remote-roots-"))
for k in ("desktop", "downloads", "documents"):
    (roots_dir / k).mkdir()
(roots_dir / "desktop" / "bao-cao.txt").write_text("hello", encoding="utf-8")
(roots_dir / "desktop" / "sub").mkdir()
(roots_dir / "desktop" / "sub" / "an.txt").write_text("x", encoding="utf-8")
(roots_dir / "secret.txt").write_text("secret", encoding="utf-8")
R.folder_roots = lambda: {k: str(roots_dir / k) for k in ("desktop", "downloads", "documents")}

m.check_ready = lambda: None
m._installed = lambda: [{"name": "Google Chrome", "path": "x"}, {"name": "Excel", "path": "y"}]
m._list_running = lambda: [
    {"image": "chrome.exe", "pid": "1", "title": "YouTube - Google Chrome"},
    {"image": "chrome.exe", "pid": "2", "title": ""},
    {"image": "explorer.exe", "pid": "4", "title": "Downloads"},
    {"image": "python.exe", "pid": "6", "title": "Javis"},
    {"image": "svchost.exe", "pid": "7", "title": ""},
]
m._open = lambda args, c: calls.append(("open", args["name"])) or "[unverified] Đã gửi lệnh mở Excel."
m._close = lambda args, c: calls.append(("close", args["name"])) or "[done] Đã đóng chrome.exe."

def _endpoint(h):
    async def ep(req):
        from starlette.responses import JSONResponse, Response
        out = await h(req, ctx)
        return out if isinstance(out, Response) else JSONResponse(out)
    return ep


app = Starlette(routes=[Route("/" + p, _endpoint(h), methods=list(meth)) for p, h, meth in ctx.routes])


c = TestClient(app)

# ---- 2. not ready ----
m.check_ready = lambda: "Javis đang chạy trong Docker"
calls.clear()
for meth, path, body in (("post", "/api/lock", {}), ("post", "/api/power", {"op": "sleep", "confirm": True}),
                         ("get", "/api/volume", None), ("post", "/api/clipboard", {"text": "x"}),
                         ("get", "/api/screen", None), ("get", "/api/files?root=desktop", None),
                         ("post", "/api/app", {"op": "open", "name": "excel"})):
    r = getattr(c, meth)(path, json=body) if body is not None else getattr(c, meth)(path)
    j = r.json()
    check(f"docker: {path} answers with the reason", j.get("ok") is False and "Docker" in j.get("error", ""), r.text)
check("docker: nothing was called", calls == [], calls)
r = c.get("/api/status").json()
check("docker: status says not ready, with the reason", r["ok"] is False and "Docker" in r["error"])
m.check_ready = lambda: None
R.IS_WIN = False
check("non-Windows: blocked with a clear reason", c.post("/api/lock", json={}).json()["ok"] is False)
R.IS_WIN = True

# ---- 3. files ----
r = c.get("/api/files?root=desktop").json()
check("files: lists files only, not folders", [f["name"] for f in r["files"]] == ["bao-cao.txt"], r)
check("files: unknown root refused", c.get("/api/files?root=system32").json()["ok"] is False)
r = c.get("/api/file", params={"root": "desktop", "name": "bao-cao.txt"})
check("file download works", r.status_code == 200 and r.content == b"hello")
for bad in ("../secret.txt", "..\\secret.txt", "sub/an.txt", "sub", "..", "C:\\Windows\\win.ini", ""):
    r = c.get("/api/file", params={"root": "desktop", "name": bad})
    check(f"file download refuses {bad!r}", r.status_code == 404, r.status_code)
check("safe_file refuses an unknown root", R.safe_file(R.folder_roots(), "x", "bao-cao.txt") is None)

# ---- 4. clipboard ----
calls.clear()
nasty = "a'; Remove-Item C:\\ -Recurse; $(calc) `\"x"
r = c.post("/api/clipboard", json={"text": nasty}).json()
check("clipboard set passes the text as data", r["ok"] and calls == [("clip_set", nasty)], calls)
check("clipboard: too long refused", c.post("/api/clipboard", json={"text": "x" * (R.CLIP_MAX + 1)}).json()["ok"] is False)
check("clipboard: empty refused", c.post("/api/clipboard", json={"text": ""}).json()["ok"] is False)
check("clipboard get", c.get("/api/clipboard").json().get("text") == "chu tren may")
check("clipboard set never builds a command from the text",
      "JAVIS_RC_TEXT" not in R._VOLUME_PS and "$env:JAVIS_RC_TEXT" not in R._FOLDERS_PS)

# ---- 5. power, volume, apps ----
calls.clear()
check("power without confirm refused", c.post("/api/power", json={"op": "shutdown"}).json()["ok"] is False)
check("power confirm must be true, not truthy", c.post("/api/power", json={"op": "shutdown", "confirm": "yes"}).json()["ok"] is False)
check("unknown power op refused", c.post("/api/power", json={"op": "format", "confirm": True}).json()["ok"] is False)
check("refused power ops called nothing", calls == [], calls)
r = c.post("/api/power", json={"op": "restart", "confirm": True}).json()
check("power restart: scheduled and reported as sent, not done",
      r["ok"] and r["state"] == "unverified" and calls == [("power", "restart")], r)

r = c.get("/api/volume").json()
check("volume read shows the read-back level", r["ok"] and r["level"] == 42)
check("volume op validated", c.post("/api/volume", json={"op": "max"}).json()["ok"] is False)
r = c.post("/api/volume", json={"op": "mute"}).json()
check("volume mute", r["muted"] is True)

r = c.get("/api/apps").json()
imgs = [a["image"] for a in r["running"]]
check("apps: windowed apps only, one per image", imgs == ["chrome.exe"], imgs)
check("apps: installed names offered", "Excel" in r["installed"])
calls.clear()
r = c.post("/api/app", json={"op": "open", "name": "excel"}).json()
check("open reuses the plugin and keeps [unverified] apart from done",
      calls == [("open", "excel")] and r["ok"] and r["state"] == "unverified", r)
r = c.post("/api/app", json={"op": "close", "name": "chrome.exe"}).json()
check("close reuses the plugin, [done] -> done", r["state"] == "done")
check("unknown app op refused", c.post("/api/app", json={"op": "kill", "name": "x"}).json()["ok"] is False)
check("outcome: failed is not ok", R.outcome("ERROR: [failed] không mở được")["ok"] is False)
check("outcome: ask is not ok", R.outcome("[ask] Chưa mở gì")["ok"] is False)

r = c.post("/api/favorites", json={"op": "add", "name": "Excel"}).json()
check("favorites: add", r["favorites"] == ["Excel"])
c.post("/api/favorites", json={"op": "add", "name": "excel"})
check("favorites: no duplicates", R.load_favorites(ctx.data_dir) == ["Excel"])
check("favorites live in the plugin data dir", (ctx.data_dir / "favorites.json").is_file())
r = c.post("/api/favorites", json={"op": "remove", "name": "EXCEL"}).json()
check("favorites: remove", r["favorites"] == [])

r = c.get("/api/screen")
check("screen: image bytes, not cached", r.status_code == 200 and r.content.startswith(b"\x89PNG")
      and r.headers["content-type"] == "image/png" and "no-store" in r.headers.get("cache-control", ""))
R.capture_screen = lambda: (_ for _ in ()).throw(RuntimeError("screen unavailable"))
r = c.get("/api/screen")
check("screen: locked or off -> clear message", r.status_code == 409 and r.json()["ok"] is False)

# ---- PNG encoder ----
png = R._png(2, 1, bytes([255, 0, 0, 0, 0, 255]))
check("png encoder writes a valid header", png.startswith(b"\x89PNG\r\n\x1a\n") and b"IHDR" in png and png.endswith(b"IEND\xaeB`\x82"))

# ---- 6. page in both languages ----
for lang, word in (("vi", "Tắt máy"), ("en", "Shut down")):
    html = R.render_page(lang)
    check(f"page {lang}: strings filled in", word in html and "__STRINGS__" not in html and "__LANG__" not in html
          and f'lang="{lang}"' in html)
check("every string has vi and en", all(isinstance(v, tuple) and len(v) == 2 and all(v) for v in R.STRINGS.values()))
src = (ROOT / "system" / "plugins" / "desktop-apps" / "page.html").read_text(encoding="utf-8")
used = set(__import__("re").findall(r'data-t[lp]?="(\w+)"', src))
check("every data-t key exists", used <= set(R.STRINGS), used - set(R.STRINGS))
for path in ("page.html", "remote.py"):
    t = (ROOT / "system" / "plugins" / "desktop-apps" / path).read_text(encoding="utf-8")
    check(f"{path}: no em or en dash", "\u2014" not in t and "\u2013" not in t)

if _fails:
    raise SystemExit(f"\nFAIL - test_desktop_remote_page: {len(_fails)} lỗi")
print("\nOK - test_desktop_remote_page: tất cả pass")
