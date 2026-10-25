"""Plugins page "Install from .zip": inspect first, install only the inspected sha256, always OFF.

    python tests/run.py plugin_zip

No pytest, no network, isolated JAVIS_STATE_DIR. What must hold:

1. The zip rules are the PACK rules (one shared extractor): traversal, symlink, ratio bomb and
   oversize are refused here too.
2. Plugin rules: plugin.yaml + plugin.py at the root or in one folder, a valid slug, no clash with a
   bundled plugin or a store-pack plugin, no compiled code.
3. The installed plugin lands in STATE_DIR/plugins/<slug>/ with `enabled: false` even when the zip
   says true, loads nothing until it is switched on, and replacing an existing one needs `replace`.
4. A full store pack zip is reported as `kind: pack` and goes to the pack inspector.
5. The routes need a real session.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import io
import os
import stat
import sys
import tempfile
import zipfile

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-pzip-")
os.environ.pop("JAVIS_ENABLE_USER_PLUGINS", None)
os.environ.pop("JAVIS_ENABLE_VAULT_PLUGINS", None)

import fastyaml  # noqa: E402
import pack_install  # noqa: E402
import plugin_install  # noqa: E402
import plugins_host  # noqa: E402

_fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (f"  [{extra}]" if not cond and extra else ""))
    if not cond:
        _fails.append(name)


MANIFEST = ("name: Zip demo\nslug: {slug}\nversion: 1.2.0\ndescription: Echo tool for tests.\n"
            "author: Test\nenabled: {enabled}\nmin_mode: readonly\ntools: [{tool}]\nhooks: []\n")
CODE = ("def register(ctx):\n"
        "    ctx.register_tool(name='{tool}', description='echo', min_mode='safe',\n"
        "                      handler=lambda args, ctx: 'hi')\n")


def make_zip(slug="zip-demo", tool="zip_demo_echo", enabled="true", wrap="", extra=None,
             manifest=None, code=None, skip=()):
    b = io.BytesIO()
    pre = (wrap + "/") if wrap else ""
    with zipfile.ZipFile(b, "w", zipfile.ZIP_DEFLATED) as z:
        if "plugin.yaml" not in skip:
            z.writestr(pre + "plugin.yaml", manifest if manifest is not None
                       else MANIFEST.format(slug=slug, enabled=enabled, tool=tool))
        if "plugin.py" not in skip:
            z.writestr(pre + "plugin.py", code if code is not None else CODE.format(tool=tool))
        for name, body in (extra or {}).items():
            z.writestr(name if name.startswith(("/", "..")) else pre + name, body)
    return b.getvalue()


def tools_of(slug):
    plugins_host.invalidate()
    tools, _ = plugins_host.plugin_tools("full", None)
    return {t["fn"] for t in tools}


def described(slug):
    return next((p for p in plugins_host.describe(None) if p["slug"] == slug), None)


# ---------- 1. happy path: bare plugin at the root, zip says enabled: true ----------
r = plugin_install.inspect(make_zip(enabled="true"), "zip-demo.zip")
check("inspect: bare plugin ok", r.get("ok") and r.get("kind") == "plugin", r)
check("inspect: slug from manifest", r.get("slug") == "zip-demo")
check("inspect: version + name", r.get("version") == "1.2.0" and r.get("name") == "Zip demo")
check("inspect: tool min_mode read from register_tool", r.get("tools") == [{"name": "zip_demo_echo", "min_mode": "safe"}], r.get("tools"))
check("inspect: file list", sorted(f["path"] for f in r.get("files") or []) == ["plugin.py", "plugin.yaml"])
check("inspect: says the zip asked for enabled", r.get("enabled_in_zip") is True)
check("inspect: nothing in the plugins folder yet", not (plugins_host.GLOBAL_DIR / "zip-demo").exists())
check("inspect: staging outside the plugins folder", plugins_host.GLOBAL_DIR not in plugin_install.STAGING.parents)

bad = plugin_install.install(r["staging_id"], "0" * 64)
check("install: sha256 mismatch refused", not bad.get("ok"))
check("install: still nothing installed", not (plugins_host.GLOBAL_DIR / "zip-demo").exists())

ok = plugin_install.install(r["staging_id"], r["sha256"])
dest = plugins_host.GLOBAL_DIR / "zip-demo"
check("install: ok", ok.get("ok") and ok.get("enabled") is False, ok)
check("install: lands in STATE_DIR/plugins/<slug>", (dest / "plugin.py").is_file() and (dest / "plugin.yaml").is_file())
m = fastyaml.safe_load((dest / "plugin.yaml").read_text(encoding="utf-8"))
check("install: forced enabled: false although the zip said true", m.get("enabled") is False, m)
check("install: staging cleaned", not (plugin_install.STAGING / r["sha256"]).exists())
mode = stat.S_IMODE((dest / "plugin.py").stat().st_mode)
check("install: archive modes ignored (0644)", mode == 0o644, oct(mode))

d = described("zip-demo")
check("listed as a user plugin, off, not loaded",
      d is not None and d["source"] == "user" and not d["enabled"] and not d["loaded"], d)
check("tool absent while off", "zip_demo_echo" not in tools_of("zip-demo"))
plugins_host.set_enabled("zip-demo", True)
check("tool loads only after switching on", "zip_demo_echo" in tools_of("zip-demo"))
plugins_host.set_enabled("zip-demo", False)

# ---------- 2. replace an existing user plugin ----------
r2 = plugin_install.inspect(make_zip(manifest=MANIFEST.format(slug="zip-demo", enabled="false", tool="zip_demo_echo").replace("1.2.0", "1.3.0")))
check("inspect: reports the installed version", (r2.get("existing") or {}).get("version") == "1.2.0", r2.get("existing"))
no = plugin_install.install(r2["staging_id"], r2["sha256"])
check("replace refused without confirmation", not no.get("ok") and no.get("code") == "exists", no)
check("old version untouched", "1.2.0" in (dest / "plugin.yaml").read_text(encoding="utf-8"))
yes = plugin_install.install(r2["staging_id"], r2["sha256"], replace=True)
check("replace with confirmation", yes.get("ok") and yes.get("replaced") is True, yes)
check("new version in place", "1.3.0" in (dest / "plugin.yaml").read_text(encoding="utf-8"))
check("no trash left behind", not [p for p in plugins_host.GLOBAL_DIR.parent.iterdir() if p.name.startswith(".plugin-trash-")])

# ---------- 3. wrapper folder, slug from folder name when the manifest has none ----------
mf_noslug = "name: Wrapped\nversion: 0.1.0\nenabled: false\n"
r3 = plugin_install.inspect(make_zip(wrap="wrapped-one", manifest=mf_noslug, tool="wrapped_tool"))
check("wrapped zip: slug from the folder", r3.get("ok") and r3.get("slug") == "wrapped-one", r3)
check("wrapped zip: tool and its min_mode found in the code",
      r3.get("tools") == [{"name": "wrapped_tool", "min_mode": "safe"}], r3.get("tools"))

dt = plugin_install.declared_tools({"min_mode": "full", "tools": ["a", {"name": "b", "min_mode": "safe"}, 3]},
                                   {"p.py": "ctx.register_tool('c', 'd', h)\nnot python ((("})
check("declared_tools: manifest min_mode fallback, dict entries, code-only tools, bad source ignored",
      dt == [{"name": "a", "min_mode": "full"}, {"name": "b", "min_mode": "safe"}], dt)
dt2 = plugin_install.declared_tools({}, {"p.py": "def register(ctx):\n    ctx.register_tool('c', 'd', h, None, None, 'full')\n"})
check("declared_tools: positional name and min_mode", dt2 == [{"name": "c", "min_mode": "full"}], dt2)

# ---------- 4. refusals ----------
def refused(label, data, needle=""):
    rr = plugin_install.inspect(data, "x.zip")
    cond = not rr.get("ok") and (needle.lower() in (rr.get("error") or "").lower())
    check(label, cond, rr)
    return rr


refused("traversal refused", make_zip(extra={"../evil.py": "x"}))
refused("absolute path refused", make_zip(extra={"/etc/evil": "x"}))
b = io.BytesIO()
with zipfile.ZipFile(b, "w") as z:
    z.writestr("plugin.yaml", MANIFEST.format(slug="lnk", enabled="false", tool="t"))
    z.writestr("plugin.py", CODE.format(tool="t"))
    zi = zipfile.ZipInfo("data.txt")
    zi.external_attr = (stat.S_IFLNK | 0o777) << 16
    z.writestr(zi, "/etc/passwd")
refused("symlink refused", b.getvalue())
refused("compression bomb refused", make_zip(extra={"big.txt": "0" * (3 * 1024 * 1024)}))
old_max = pack_install.MAX_ZIP
pack_install.MAX_ZIP = 1024
refused("oversize zip refused", make_zip(extra={"pad.bin": os.urandom(4096)}))
pack_install.MAX_ZIP = old_max
refused("missing plugin.py refused", make_zip(skip=("plugin.py",)), "plugin.py")
refused("missing plugin.yaml refused", make_zip(skip=("plugin.yaml",)), "plugin.yaml")
refused("bad slug refused", make_zip(slug="Bad Slug!"), "slug")
bundled = sorted(plugins_host._slug_bundled())[0]
rb = refused("bundled slug collision refused", make_zip(slug=bundled))
check("bundled collision code", rb.get("code") == "bundled")
refused("compiled code refused", make_zip(extra={"__pycache__/helper.cpython-312.pyc": b"\x00" * 16}))
refused("native module refused", make_zip(extra={"fast.so": b"\x7fELF"}))
refused("sensitive file refused", make_zip(extra={".env": "SECRET=1"}))
refused("not a zip refused", b"this is not a zip")
refused("huge manifest refused", make_zip(manifest="name: x\nslug: big-mf\n# " + "a" * (pack_install.MAX_MANIFEST + 10) + "\n"), "plugin.yaml")

# store-pack plugin slug collision
pack_install._ghi_so({"acme.demo": {"version": "1", "enabled": True, "plugins": ["pack-owned"]}})
rp = refused("store-pack plugin slug refused", make_zip(slug="pack-owned"))
check("pack collision code", rp.get("code") == "pack")
pack_install._ghi_so({})

# ---------- 5. a full store pack zip is routed to the pack installer ----------
b = io.BytesIO()
with zipfile.ZipFile(b, "w") as z:
    z.writestr("javis-pack.yaml", "format: javis-pack\nspec: 1\nid: acme.pz\nversion: 1.0.0\nname: {en: Pz}\n")
    z.writestr("plugins/pz/plugin.yaml", "name: pz\n")
    z.writestr("plugins/pz/plugin.py", "def register(ctx):\n    pass\n")
rk = plugin_install.inspect(b.getvalue(), "pack.zip")
check("pack zip reported as kind=pack", rk == {"ok": True, "kind": "pack"}, rk)
import hashlib  # noqa: E402
check("pack zip leaves no plugin staging", not (plugin_install.STAGING / hashlib.sha256(b.getvalue()).hexdigest()).exists())

# ---------- 6. JAVIS_ENABLE_USER_PLUGINS=false is reported ----------
os.environ["JAVIS_ENABLE_USER_PLUGINS"] = "false"
rg = plugin_install.inspect(make_zip(slug="gated-one"))
check("inspect reports user plugins globally off", rg.get("ok") and rg.get("user_gate") is False, rg)
ig = plugin_install.install(rg["staging_id"], rg["sha256"])
check("install still ok, says gated", ig.get("ok") and ig.get("user_gate") is False, ig)
os.environ.pop("JAVIS_ENABLE_USER_PLUGINS", None)

# ---------- 7. routes: real session only, pack zips go to the pack inspector ----------
try:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    import routes.plugin_zip as pz

    refreshed = []
    app = FastAPI()
    pz.register(app, pz.PluginZipDeps(co_phien=lambda req: req.cookies.get("javis_session") == "good",
                                      brain_root=lambda b: "", after_install=refreshed.append))
    c = TestClient(app)
    data = make_zip(slug="route-demo", tool="route_demo_tool")
    r401 = c.post("/plugins/inspect", files={"file": ("p.zip", data, "application/zip")})
    check("route: inspect needs a session", r401.status_code == 401)
    r401b = c.post("/plugins/install", json={"staging_id": "x", "consent_sha256": "x"})
    check("route: install needs a session", r401b.status_code == 401)
    c.cookies.set("javis_session", "good")
    ri = c.post("/plugins/inspect", files={"file": ("p.zip", data, "application/zip")}, data={"brain": "brain"}).json()
    check("route: inspect ok", ri.get("ok") and ri.get("slug") == "route-demo", ri)
    rn = c.post("/plugins/install", json={"staging_id": ri["staging_id"], "consent_sha256": ri["sha256"],
                                          "replace": "yes", "brain": "brain"})
    check("route: install ok and refresh called", rn.status_code == 200 and refreshed == ["brain"], rn.text)
    ri2 = c.post("/plugins/inspect", files={"file": ("p.zip", data, "application/zip")}).json()
    rr = c.post("/plugins/install", json={"staging_id": ri2["staging_id"], "consent_sha256": ri2["sha256"], "replace": "yes"})
    check("route: replace needs replace === true, not a truthy string", rr.status_code == 400)
    pack_install.STAGING = plugin_install.STAGING.parent / "packs-staging"
    rk2 = c.post("/plugins/inspect", files={"file": ("pack.zip", b.getvalue(), "application/zip")}).json()
    check("route: pack zip answered by the pack inspector", rk2.get("kind") == "pack" and rk2.get("id") == "acme.pz", rk2)
except ImportError as e:
    check(f"fastapi test client available ({e})", False)

print()
if _fails:
    print(f"{len(_fails)} FAIL")
    sys.exit(1)
print("all ok")
