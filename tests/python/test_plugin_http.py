"""Đường HTTP của plugin (0.64.22): `ctx.register_http` và `ctx.register_well_known`.

    python tests/run.py plugin_http      (KHÔNG mạng)

Sinh ra để "Javis trong ChatGPT" rời lõi thành một gói trong kho, nên file này khoá đúng những
ranh giới lõi phải giữ hộ mọi gói, kể cả gói viết ẩu:

1. Mặc định một đường phải đăng nhập bằng TRÌNH DUYỆT (cookie), token API không mở được.
2. `public=True` thì vào không cần đăng nhập, nhưng chỉ đúng method đã khai.
3. `no_cookie=True` được miễn CSRF, và lõi GỠ cookie trước khi giao cho plugin: miễn CSRF mà
   còn cookie là cho trang lạ mượn phiên của chủ.
4. `/.well-known/<tên>` công khai, không cookie, chỉ GET.
5. Plugin trong BRAIN không mở được đường nào: model ghi được vào brain.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import os
import tempfile
from pathlib import Path

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-plughttp-")
os.environ["JAVIS_REQUIRE_LOGIN"] = "1"
os.environ["JAVIS_ENABLE_USER_PLUGINS"] = "true"

from fastapi.testclient import TestClient   # noqa: E402
import config as cfg   # noqa: E402
import main            # noqa: E402
import plugins_host    # noqa: E402

_fails = []


def check(name, cond, them=""):
    print(("ok   " if cond else "FAIL ") + name + (f"  [{them}]" if them and not cond else ""))
    if not cond:
        _fails.append(name)


def viet_plugin(goc: Path, slug: str, than: str, yaml_them: str = ""):
    d = goc / slug
    d.mkdir(parents=True, exist_ok=True)
    (d / "plugin.yaml").write_text(f"name: {slug}\nslug: {slug}\nenabled: true\n"
                                   f"min_mode: readonly\n{yaml_them}", encoding="utf-8")
    (d / "plugin.py").write_text(than, encoding="utf-8")


viet_plugin(plugins_host.GLOBAL_DIR, "demo-http", '''
from starlette.responses import PlainTextResponse

def register(ctx):
    ctx.register_http("", lambda r, c: "<h1>trang cai dat</h1>")
    ctx.register_http("status", lambda r, c: {"ok": True, "slug": c.slug}, public=True)
    ctx.register_http("status", lambda r, c: {"ghi": True}, methods=("POST",))

    async def hook(r, c):
        return {"cookie": r.headers.get("cookie", ""), "body": (await r.body()).decode()}
    ctx.register_http("hook", hook, methods=("POST",), public=True, no_cookie=True)
    ctx.register_http("loi", lambda r, c: 1 / 0, public=True)
    ctx.register_well_known("demo-meta", lambda r, c: PlainTextResponse("meta:" + r.url.path))
''', "page: \"\"\n")

vault = Path(tempfile.mkdtemp(prefix="javis-plughttp-vault-"))
viet_plugin(vault / "plugins", "vault-http", '''
def register(ctx):
    ctx.register_http("x", lambda r, c: {"lot": True}, public=True)
    ctx.register_well_known("vault-meta", lambda r, c: {"lot": True})
''')
plugins_host.invalidate()

_s = cfg.read_settings()
_s["auth"] = {"username": "admin", **dict(zip(("password_hash", "salt"),
                                              cfg.hash_password("matkhau123")))}
cfg.write_settings(_s)

la = TestClient(main.app)            # người lạ, không cookie
chu = TestClient(main.app)           # chủ, đăng nhập bằng trình duyệt
r = chu.post("/auth/login", data={"username": "admin", "password": "matkhau123"})
check("chủ đăng nhập được", r.status_code == 200 and r.json().get("ok"))

# ---- 1. mặc định: phải đăng nhập ----
check("người lạ mở trang cài đặt của plugin -> 401", la.get("/ext/demo-http/").status_code == 401)
r = chu.get("/ext/demo-http/")
check("chủ mở được trang cài đặt, chuỗi trả về thành HTML",
      r.status_code == 200 and "trang cai dat" in r.text and r.headers["content-type"].startswith("text/html"))
check("cả /ext/<slug> không gạch cuối cũng tới trang gốc", chu.get("/ext/demo-http").status_code == 200)

# ---- 2. public theo method ----
r = la.get("/ext/demo-http/status")
check("GET public: người lạ vào được, dict thành JSON", r.status_code == 200 and r.json() == {"ok": True, "slug": "demo-http"})
check("POST cùng đường nhưng KHÔNG public -> người lạ bị chặn",
      la.post("/ext/demo-http/status").status_code == 401)
r = chu.post("/ext/demo-http/status", headers={"Origin": "http://testserver"})
check("chủ POST được đường không public", r.status_code == 200 and r.json() == {"ghi": True}, r.text)
check("method không khai -> 404", chu.delete("/ext/demo-http/status",
                                              headers={"Origin": "http://testserver"}).status_code == 404)
check("đường không tồn tại -> 404 (sau đăng nhập)", chu.get("/ext/demo-http/khong-co").status_code == 404)
check("plugin không tồn tại, người lạ -> 401 (không dò được plugin nào đang cài)",
      la.get("/ext/khong-co/x").status_code == 401)

# ---- 3. no_cookie: miễn CSRF + gỡ cookie ----
r = chu.post("/ext/demo-http/hook", content=b"ping", headers={"Origin": "https://trang-la.example"})
check("no_cookie: Origin lạ vẫn qua (máy chủ ngoài gọi vào)", r.status_code == 200, r.text)
check("no_cookie: plugin KHÔNG thấy cookie phiên của chủ", r.json().get("cookie") == "", r.text)
check("no_cookie: thân request tới plugin nguyên vẹn", r.json().get("body") == "ping")
r = chu.post("/ext/demo-http/status", headers={"Origin": "https://trang-la.example"})
check("đường KHÔNG no_cookie: Origin lạ bị CSRF chặn", r.status_code == 403, r.status_code)

# ---- lỗi trong plugin ----
r = la.get("/ext/demo-http/loi")
check("plugin ném lỗi -> 500 gọn, không lộ traceback", r.status_code == 500 and "Traceback" not in r.text)

# ---- 4. well-known ----
r = la.get("/.well-known/demo-meta")
check("well-known: người lạ đọc được", r.status_code == 200 and r.text == "meta:/.well-known/demo-meta")
r = la.get("/.well-known/demo-meta/con/duong")
check("well-known: phần đuôi sau tên vẫn tới cùng plugin",
      r.status_code == 200 and r.text.endswith("/con/duong"))
check("well-known không ai khai -> không công khai", la.get("/.well-known/khong-co").status_code == 401)
check("well-known chỉ GET", la.post("/.well-known/demo-meta").status_code in (401, 405))

# ---- 5. plugin trong brain không có đường ----
check("plugin trong brain: không mở được /ext", la.get("/ext/vault-http/x").status_code == 401
      and chu.get("/ext/vault-http/x").status_code == 404)
check("plugin trong brain: không chiếm được well-known", la.get("/.well-known/vault-meta").status_code == 401)

# ---- nút "Mở trang" ----
d = {x["slug"]: x for x in plugins_host.describe(None)}
check("describe đưa ra trang của plugin có khai page", d["demo-http"].get("page") == "/ext/demo-http/")

# ---- kiểm đầu vào register_http ----
ctx = plugins_host.PluginContext("x", "user", Path("."), None)
for sai in (dict(path="../a"), dict(path="a//b"), dict(path="a", methods=("TRACE",)),
            dict(path="a", no_cookie=True)):
    try:
        ctx.register_http(handler=lambda r, c: "", **sai)
        check(f"register_http từ chối {sai}", False)
    except ValueError:
        check(f"register_http từ chối {sai}", True)
try:
    ctx.register_well_known("../x", lambda r, c: "")
    check("register_well_known từ chối tên có ../", False)
except ValueError:
    check("register_well_known từ chối tên có ../", True)

print()
if _fails:
    print(f"ĐỎ {len(_fails)} ca")
    raise SystemExit(1)
print("xanh hết")
