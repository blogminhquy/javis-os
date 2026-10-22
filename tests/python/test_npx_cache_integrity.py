"""The npx folder check that runs before a stdio session spawns `npx -y <package>`.

    python tests/run.py npx_cache_integrity      (no network; uses a fake `npx` on PATH)

Field report 2026-10-13 (VPS): `npx -y mcp-server-gsc@latest` failed on every start with
MODULE_NOT_FOUND. Its folder `~/.npm/_npx/fe1c444f68b53df6` had `node_modules/ajv` and
`node_modules/hono` without package.json, left by an install that was killed half way. npx kept
reusing that folder, so Check never helped. The fix moves such a folder aside before spawning.

Locked here: the folder name matches npm's own hash (real values from a live npm 10.9.9 cache),
the npx command line is parsed or refused (never guessed), the broken shapes are found and the
healthy ones are not, and a folder is never moved while it may still be written to.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import json
import os
import stat
import sys
import tempfile
import time
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="javis-npx-cache-"))
os.environ["JAVIS_STATE_DIR"] = str(_TMP / "state")
os.environ["HOME"] = str(_TMP / "home")
for _d in ("state", "home"):
    (_TMP / _d).mkdir(parents=True, exist_ok=True)
os.environ.pop("npm_config_cache", None)
os.environ.pop("NPM_CONFIG_CACHE", None)

import npx_cache  # noqa: E402

fails = []


def check(name, cond, detail=""):
    print(("ok   " if cond else "FAIL ") + name + (f"  [{detail}]" if detail and not cond else ""))
    if not cond:
        fails.append(name)


def write(path, data=""):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(data if isinstance(data, str) else json.dumps(data), encoding="utf-8")


def age(folder, seconds):
    old = time.time() - seconds
    for dp, dns, fns in os.walk(folder):
        for n in dns + fns:
            os.utime(os.path.join(dp, n), (old, old))
    os.utime(folder, (old, old))


def tree(folder, broken=False):
    """A small npx folder shaped like the real one: root package.json, the connector, deps."""
    write(folder / "package.json", {"dependencies": {"conn-pkg": "^1.0.0"}})
    write(folder / "node_modules/conn-pkg/package.json",
          {"name": "conn-pkg", "dependencies": {"ajv-formats": "^3", "ajv": "^8"},
           "optionalDependencies": {"fsevents": "^2"}})
    write(folder / "node_modules/ajv-formats/package.json", {"name": "ajv-formats", "dependencies": {"ajv": "^8"}})
    write(folder / "node_modules/@scope/lib/package.json", {"name": "@scope/lib", "dependencies": {"nested": "1"}})
    write(folder / "node_modules/@scope/lib/node_modules/nested/package.json", {"name": "nested"})
    write(folder / "node_modules/ajv/dist/index.js", "module.exports = {}")
    if not broken:
        write(folder / "node_modules/ajv/package.json", {"name": "ajv"})


# ---------- 1. The folder name npx uses ----------
root = Path("/x/_npx")
check("hash: mcp-server-gsc@latest -> fe1c444f68b53df6 (live npm 10.9.9 cache)",
      npx_cache.install_dir(["mcp-server-gsc@latest"], root).name == "fe1c444f68b53df6")
check("hash: @playwright/mcp@latest -> 9833c18b2d85bc59 (live npm 10.9.9 cache)",
      npx_cache.install_dir(["@playwright/mcp@latest"], root).name == "9833c18b2d85bc59")
check("hash: hostinger-api-mcp@latest -> a7204b5813574340 (live npm 10.9.9 cache)",
      npx_cache.install_dir(["hostinger-api-mcp@latest"], root).name == "a7204b5813574340")
check("hash: several packages are sorted like npm (node localeCompare 'en')",
      npx_cache.install_dir(["b-pkg", "@a/pkg", "A-pkg"], root).name == "0518b90eb3b76f21")

# ---------- 2. Reading the command line, or refusing to guess ----------
ps = npx_cache.package_specs
check("parse: npx -y pkg@latest", ps("npx", ["-y", "pkg@latest"]) == (["pkg@latest"], None))
check("parse: npx.cmd with a Windows-style path name", ps("npx.cmd", ["--yes", "pkg"]) == (["pkg"], None))
check("parse: --package twice, the positional is the bin", ps("npx", ["-y", "-p", "a", "--package=b", "run-me"]) == (["a", "b"], None))
check("parse: --cache is honoured", ps("npx", ["-y", "--cache", "/c", "pkg"]) == (["pkg"], "/c"))
check("parse: --key=value options are skipped", ps("npx", ["-y", "--registry=https://r", "pkg", "--port", "1"]) == (["pkg"], None))
check("parse: an unknown option that may take a value -> refuse", ps("npx", ["-y", "--registry", "https://r", "pkg"]) is None)
check("parse: a local directory spec -> refuse", ps("npx", ["-y", "./tool"]) is None)
check("parse: --call -> refuse", ps("npx", ["-c", "echo hi"]) is None)
check("parse: not npx -> None", ps("uvx", ["some-mcp"]) is None and ps("node", ["x.js"]) is None)

# ---------- 3. Where the npm cache is ----------
home = _TMP / "home"
check("cache root: ~/.npm/_npx by default", npx_cache.npx_root({"HOME": str(home)}) == home / ".npm" / "_npx")
check("cache root: npm_config_cache wins", npx_cache.npx_root({"HOME": str(home), "npm_config_cache": "/c"}) == Path("/c/_npx"))
write(home / ".npmrc", "registry=https://r\ncache=/from-npmrc\n")
check("cache root: cache= in ~/.npmrc", npx_cache.npx_root({"HOME": str(home)}) == Path("/from-npmrc/_npx"))
(home / ".npmrc").unlink()

# ---------- 4. What counts as broken ----------
ok_dir = _TMP / "t-ok"
tree(ok_dir)
check("healthy tree: no problem (optional dep absent is fine, nested resolution works)",
      npx_cache.inspect_tree(ok_dir) == [], npx_cache.inspect_tree(ok_dir))
bad_dir = _TMP / "t-bad"
tree(bad_dir, broken=True)
probs = npx_cache.inspect_tree(bad_dir)
check("the 2026-10-13 shape: a package folder without package.json",
      "node_modules/ajv: no package.json" in probs, probs)
check("and its dependents are reported too",
      any(p.startswith("node_modules/ajv-formats: dependency ajv") for p in probs), probs)
miss_dir = _TMP / "t-miss"
tree(miss_dir)
write(miss_dir / "node_modules/conn-pkg/package.json", {"name": "conn-pkg", "dependencies": {"gone": "1"}})
check("a declared dependency that is not there at all", npx_cache.inspect_tree(miss_dir) == ["node_modules/conn-pkg: dependency gone missing"],
      npx_cache.inspect_tree(miss_dir))
check("nothing installed yet: no problem to report", npx_cache.inspect_tree(_TMP / "nowhere") == [])

# ---------- 5. prepare(): repair only what nobody is writing ----------
env = {"HOME": str(home)}
npx_root = home / ".npm" / "_npx"
folder = npx_root / npx_cache.install_dir(["fake-mcp@latest"], npx_root).name
r = npx_cache.prepare("npx", ["-y", "fake-mcp@latest"], env)
check("absent folder: a cold start, nothing touched", r.get("state") == "absent" and r.get("dir") == str(folder), r)
tree(folder)
age(folder, 3600)
check("healthy folder: ok, left alone", npx_cache.prepare("npx", ["-y", "fake-mcp@latest"], env).get("state") == "ok" and folder.is_dir())
(folder / "node_modules/ajv/package.json").unlink()
os.utime(folder / "node_modules/ajv", None)
r = npx_cache.prepare("npx", ["-y", "fake-mcp@latest"], env)
check("broken but just written to: busy, not moved (another install may be running)",
      r.get("state") == "busy" and folder.is_dir(), r)
age(folder, 3600)
npx_cache.claim(str(folder))
r = npx_cache.prepare("npx", ["-y", "fake-mcp@latest"], env)
check("broken but claimed by a starting session: busy, not moved", r.get("state") == "busy" and folder.is_dir(), r)
npx_cache.release(str(folder))
r = npx_cache.prepare("npx", ["-y", "fake-mcp@latest"], env)
check("broken and quiet: repaired, folder moved out of the way", r.get("state") == "repaired" and not folder.exists(), r)
check("nothing left beside it", sorted(p.name for p in npx_root.iterdir()) == [], sorted(p.name for p in npx_root.iterdir()))
check("the next start is a cold start", npx_cache.prepare("npx", ["-y", "fake-mcp@latest"], env).get("state") == "absent")
check("not npx: skipped", npx_cache.prepare(sys.executable, ["x.py"], env).get("state") == "skipped")

# ---------- 5b. A symlink cycle in node_modules does not send the walk round in circles ----------
if os.name != "nt":
    loop_dir = _TMP / "t-loop"
    tree(loop_dir)
    nm = loop_dir / "node_modules"
    plain = sorted(p.relative_to(loop_dir).as_posix() for p in npx_cache._package_dirs(nm))
    # conn-pkg/node_modules/cycle -> conn-pkg, and a scoped one: @scope/lib/node_modules/@in/cyc -> @scope/lib
    (nm / "conn-pkg/node_modules").mkdir(parents=True)
    os.symlink("..", nm / "conn-pkg/node_modules/cycle")
    (nm / "@scope/lib/node_modules/@in").mkdir(parents=True)
    os.symlink("../..", nm / "@scope/lib/node_modules/@in/cyc")
    os.symlink(".", nm / "self-link")
    t0 = time.time()
    walked = sorted(p.relative_to(loop_dir).as_posix() for p in npx_cache._package_dirs(nm))
    check("symlink cycle: the package walk skips symlinked entries and ends",
          walked == plain and time.time() - t0 < 5, walked)
    check("symlink cycle: inspect_tree returns normally (healthy tree, no problem)",
          npx_cache.inspect_tree(loop_dir) == [], npx_cache.inspect_tree(loop_dir))
    loop_folder = npx_root / npx_cache.install_dir(["loop-mcp@latest"], npx_root).name
    tree(loop_folder)
    lnm = loop_folder / "node_modules"
    (lnm / "conn-pkg/node_modules").mkdir(parents=True)
    os.symlink("..", lnm / "conn-pkg/node_modules/cycle")
    age(loop_folder, 3600)
    r = npx_cache.prepare("npx", ["-y", "loop-mcp@latest"], env)
    check("symlink cycle: prepare returns normally on a healthy folder", r.get("state") == "ok", r)
    (lnm / "ajv/package.json").unlink()
    age(loop_folder, 3600)
    r = npx_cache.prepare("npx", ["-y", "loop-mcp@latest"], env)
    check("symlink cycle: prepare still repairs a broken folder",
          r.get("state") == "repaired" and not loop_folder.exists(), r)
else:
    print("skip symlink cycle check on Windows (symlinks need extra rights)")

# ---------- 6. A real session: the broken folder is gone before npx runs ----------
import mcp_client  # noqa: E402

bin_dir = _TMP / "bin"
bin_dir.mkdir()
helper = Path(__file__).resolve().parent / "_slow_start_mcp_server.py"
marker = _TMP / "marker"
marker.mkdir()
fake_npx = bin_dir / "npx"
fake_npx.write_text(f"#!/bin/sh\nexec \"{sys.executable}\" \"{helper}\" --delay 0 --marker \"{marker}\"\n")
fake_npx.chmod(fake_npx.stat().st_mode | stat.S_IEXEC)
tree(folder, broken=True)
age(folder, 3600)
if os.name != "nt":
    # Absolute path: `_argv` searches the venv bin before PATH, and a real npx there would go
    # to the network for "fake-mcp". The check keys on the file name, which is still "npx".
    conn = {"id": "npx1", "transport": "stdio", "command": str(fake_npx), "args": ["-y", "fake-mcp@latest"],
            "env": {"HOME": str(home)}, "label": "fake npx source"}
    spec = mcp_client._conn_spec(conn)

    async def _session():
        sess = mcp_client.pool._get(spec)[1]
        try:
            tools = await sess.list_tools()
        finally:
            await mcp_client.pool.close_all()     # same loop that owns the subprocess
        return sess, tools

    sess, tools = asyncio.run(_session())
    check("session start moved the broken folder aside before spawning npx",
          sess.npx_check.get("state") == "repaired" and not folder.exists(), sess.npx_check)
    check("and treated the start as cold (install budget)", sess._cold_start is True)
    check("the server behind npx then started normally", [t["name"] for t in tools] == ["echo"], tools)
else:
    print("skip session check on Windows (needs a shell script on PATH)")

print()
if fails:
    print(f"RED {len(fails)}: " + "; ".join(fails[:4]))
    raise SystemExit(1)
print("All green.")
