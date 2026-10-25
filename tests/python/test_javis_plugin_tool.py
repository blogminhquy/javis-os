"""javis_plugin: Javis creates, reads and edits user plugins in place from chat (2026-10-25).

    python tests/run.py javis_plugin_tool

No network. Drives the tool through the same route every engine uses (plugins_host.plugin_tools),
so the per-op permission levels are tested on the real call path.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-ptool-")
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import plugins_host  # noqa: E402
import plugin_authoring  # noqa: E402

fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (f"  [{extra}]" if extra and not cond else ""))
    if not cond:
        fails.append(name)


VAULT = tempfile.mkdtemp(prefix="javis-ptool-vault-")
GLOBAL = plugins_host.global_plugins_dir()


def call(mode, args):
    _tools, route = plugins_host.plugin_tools(mode, VAULT)
    return asyncio.run(route["javis_plugin"]["call"](args))


def jcall(mode, args):
    out = call(mode, args)
    try:
        return json.loads(out)
    except ValueError:
        return {"_raw": out}


def desc(slug):
    return next((d for d in plugins_host.describe(VAULT) if d["slug"] == slug), None)


YAML = ("name: Tinh VAT\nslug: vat-calc\nversion: 1.0.0\ndescription: Tinh thue VAT 10 phan tram\n"
        "author: Javis\nenabled: true\nmin_mode: readonly\ntools: [vat_calc]\nhooks: []\n")
PY = ("def register(ctx):\n"
      "    def handler(args, ctx):\n"
      "        return str(round(float(args.get('amount') or 0) * 1.1, 2))\n"
      "    ctx.register_tool(name='vat_calc', description='VAT', handler=handler, min_mode='readonly')\n")

# ---- 0. the tool exists, everywhere, owner only ----
tools, route = plugins_host.plugin_tools("suggest", VAULT)
check("javis_plugin is listed even at the read-only level", any(t["fn"] == "javis_plugin" for t in tools))
check("route metadata says it can write", route["javis_plugin"]["effect"] == "write"
      and route["javis_plugin"]["required_mode"] == "safe")
import mcp_hub  # noqa: E402
check("javis_plugin is owner-only (a customer bot never sees it)", "javis_plugin" in mcp_hub.OWNER_ONLY_TOOLS)

# ---- 1. list/read work at every level; write/delete need safe ----
for mode in ("suggest", "auto", "full"):
    r = jcall(mode, {"op": "list"})
    check(f"list works in {mode}", "user_plugins" in r, r)
    ro = {x["slug"] for x in r.get("system_and_pack_plugins_read_only", [])}
    check(f"list marks system plugins read-only in {mode}", "datetime-vn" in ro and "javis-plugin" in ro)

out = call("suggest", {"op": "write", "slug": "vat-calc", "files": {"plugin.yaml": YAML, "plugin.py": PY}})
check("suggest mode cannot write", out.startswith("ERROR") and not (GLOBAL / "vat-calc").exists(), out)
out = call("suggest", {"op": "delete", "slug": "vat-calc"})
check("suggest mode cannot delete", out.startswith("ERROR"))
out = call("suggest", {"op": "bogus"})
check("an unknown op needs the strongest level (no typo slips past the gate)", "safe" in out and out.startswith("ERROR"))

# ---- 2. create installs OFF in the global dir, even when the yaml says enabled: true ----
r = jcall("auto", {"op": "write", "slug": "vat-calc", "files": {"plugin.yaml": YAML, "plugin.py": PY}})
check("create ok", r.get("ok") is True and r.get("created") is True, r)
check("create lands in the global dir", Path(r.get("path", "")) == GLOBAL / "vat-calc"
      and (GLOBAL / "vat-calc" / "plugin.py").is_file())
check("create is OFF despite enabled: true in the yaml", r.get("enabled") is False)
d = desc("vat-calc")
check("describe() shows it as a user plugin, off", d and d["source"] == "user" and d["enabled"] is False
      and d["loaded"] is False, d)
check("manifest on disk says enabled: false", plugins_host._read_manifest(GLOBAL / "vat-calc")[0].get("enabled") is False)
check("result tells the owner to turn it on", bool(r.get("tell_owner")))
check("its tool is not served while off", "vat_calc" not in {t["fn"] for t in plugins_host.plugin_tools("full", VAULT)[0]})
check("no staging leftovers are scanned as plugins",
      all(not x["slug"].startswith(".") for x in plugins_host.describe(VAULT)))

import main  # noqa: E402  (GET /plugins and the operations index)
lst = asyncio.run(main.plugins_list(brain=VAULT))
check("GET /plugins lists it", any(p["slug"] == "vat-calc" and p["source"] == "user" for p in lst["plugins"]))
plugin_authoring.rebuild_index(VAULT)
idx = Path(VAULT) / "Javis" / "index.md"
check("operations index rebuilt with the plugin", idx.is_file() and "vat-calc" in idx.read_text(encoding="utf-8"))

# ---- 3. read ----
r = jcall("suggest", {"op": "read", "slug": "vat-calc"})
check("read returns the files", set(r.get("files", {})) == {"plugin.py", "plugin.yaml"} and "def register" in r["files"]["plugin.py"], r)
out = call("suggest", {"op": "read", "slug": "datetime-vn"})
check("read refuses a system plugin", out.startswith("ERROR"))

# ---- 4. owner enables it; a code update switches it OFF again ----
check("owner enables it", plugins_host.set_enabled("vat-calc", True, VAULT)["ok"])
check("served once on", "vat_calc" in {t["fn"] for t in plugins_host.plugin_tools("full", VAULT)[0]})
r = jcall("auto", {"op": "write", "slug": "vat-calc", "files": {"README.md": "# VAT\nHow to use it.\n"}})
check("docs-only update keeps it ON", r.get("ok") and r.get("enabled") is True and desc("vat-calc")["enabled"], r)
y2 = YAML.replace("Tinh thue VAT 10 phan tram", "Tinh thue VAT (10%)")
r = jcall("auto", {"op": "write", "slug": "vat-calc", "files": {"plugin.yaml": y2}})
check("description-only yaml change keeps it ON", r.get("enabled") is True and r.get("declarations_changed") is False, r)
r = jcall("auto", {"op": "write", "slug": "vat-calc", "files": {"plugin.py": PY.replace("1.1", "1.08")}})
check("code update switches it OFF", r.get("ok") and r.get("enabled") is False and r.get("switched_off") is True, r)
check("code update OFF on disk", desc("vat-calc")["enabled"] is False)
check("code update is really applied", "1.08" in (GLOBAL / "vat-calc" / "plugin.py").read_text(encoding="utf-8"))
check("previous version kept as backup", "1.1" in (GLOBAL / plugin_authoring.STAGING / "bak" / "vat-calc"
                                                   / "plugin.py").read_text(encoding="utf-8"))
check("README carried over", (GLOBAL / "vat-calc" / "README.md").is_file())
plugins_host.set_enabled("vat-calc", True, VAULT)
y3 = y2.replace("min_mode: readonly", "min_mode: full")
r = jcall("auto", {"op": "write", "slug": "vat-calc", "files": {"plugin.yaml": y3}})
check("min_mode change switches it OFF", r.get("enabled") is False and r.get("declarations_changed") is True, r)
plugins_host.set_enabled("vat-calc", True, VAULT)
r = jcall("auto", {"op": "write", "slug": "vat-calc", "remove": ["README.md"]})
check("removing a doc file keeps it ON", r.get("ok") and r.get("enabled") is True
      and not (GLOBAL / "vat-calc" / "README.md").exists(), r)

# ---- 5. refused inputs (nothing changes on disk) ----
before = (GLOBAL / "vat-calc" / "plugin.py").read_text(encoding="utf-8")


def refused(label, files, slug="vat-calc", scope=None, extra=None):
    args = {"op": "write", "slug": slug, "files": files}
    if scope:
        args["scope"] = scope
    args.update(extra or {})
    out = call("full", args)
    check(label, out.startswith("ERROR"), out)
    return out


refused("traversal '..' refused", {"../evil.py": "x = 1\n"})
refused("nested traversal refused", {"lib/../../evil.py": "x = 1\n"})
refused("absolute path refused", {"/etc/evil.py": "x = 1\n"})
refused("windows drive path refused", {"C:/evil.py": "x = 1\n"})
refused("backslash path refused", {"lib\\evil.py": "x = 1\n"})
refused("hidden file refused", {".env.txt": "x"})
refused("bad extension refused", {"run.sh": "rm -rf /\n"})
refused("binary-ish extension refused", {"blob.so": "x"})
refused("oversize file refused", {"big.txt": "a" * (plugin_authoring.MAX_FILE_BYTES + 1)})
refused("oversize manifest refused", {"plugin.yaml": YAML + "# " + "a" * plugin_authoring.MAX_MANIFEST_BYTES + "\n"})
refused("bad slug refused", {"plugin.yaml": YAML, "plugin.py": PY}, slug="../x")
refused("uppercase slug refused", {"plugin.yaml": YAML, "plugin.py": PY}, slug="VatCalc")
refused("system slug collision refused", {"plugin.yaml": YAML, "plugin.py": PY}, slug="datetime-vn")
refused("own system slug collision refused", {"plugin.yaml": YAML, "plugin.py": PY}, slug="javis-plugin")
out = refused("syntax error refused", {"plugin.py": "def register(ctx)\n    pass\n"})
check("syntax error names file and line", "plugin.py" in out and "1" in out, out)
check("syntax error leaves the old code untouched", (GLOBAL / "vat-calc" / "plugin.py").read_text(encoding="utf-8") == before)
refused("syntax error in a helper module refused", {"helpers.py": "x = = 1\n"})
refused("create without plugin.py refused", {"plugin.yaml": YAML}, slug="half")
refused("missing min_mode refused", {"plugin.yaml": YAML.replace("min_mode: readonly\n", ""), "plugin.py": PY}, slug="nomode")
refused("invalid min_mode refused", {"plugin.yaml": YAML.replace("min_mode: readonly", "min_mode: root"), "plugin.py": PY}, slug="badmode")
refused("tool name of the core refused", {"plugin.yaml": YAML.replace("[vat_calc]", "[javis_read_file]"), "plugin.py": PY}, slug="shadow1")
refused("tool name of a system plugin refused", {"plugin.yaml": YAML.replace("[vat_calc]", "[javis_task]"), "plugin.py": PY}, slug="shadow2")
refused("unsafe yaml tag refused", {"plugin.yaml": "!!python/object/apply:os.system ['true']\n", "plugin.py": PY}, slug="yamlbomb")
refused("non-mapping yaml refused", {"plugin.yaml": "- a\n- b\n", "plugin.py": PY}, slug="yamllist")
refused("files must be a map", ["plugin.py"], slug="notamap")
refused("non-text content refused", {"plugin.py": 42}, slug="nottext")
refused("too many files refused", {f"f{i}.txt": "x" for i in range(plugin_authoring.MAX_FILES + 1)})
refused("bad scope refused", {"plugin.yaml": YAML, "plugin.py": PY}, slug="scoped", scope="system")
refused("cannot remove plugin.py", {}, extra={"remove": ["plugin.py"]})
check("nothing half-written for refused creates",
      not any((GLOBAL / s).exists() for s in ("half", "nomode", "badmode", "shadow1", "shadow2", "yamlbomb", "scoped")))

# symlinked plugin folder is never written through
real = Path(tempfile.mkdtemp(prefix="javis-ptool-elsewhere-"))
(real / "plugin.py").write_text(PY, encoding="utf-8")
(real / "plugin.yaml").write_text(YAML, encoding="utf-8")
link = GLOBAL / "linked"
try:
    os.symlink(real, link, target_is_directory=True)
    out = refused("symlinked plugin folder refused", {"plugin.py": PY + "\n# x\n"}, slug="linked")
    check("symlinked folder untouched", "# x" not in (real / "plugin.py").read_text(encoding="utf-8"))
except (OSError, NotImplementedError):
    print("skip symlink checks (no symlink support)")

# ---- 6. brain scope ----
r = jcall("auto", {"op": "write", "slug": "brain-only", "scope": "brain",
                   "files": {"plugin.yaml": YAML.replace("vat_calc", "brain_calc"),
                             "plugin.py": PY.replace("vat_calc", "brain_calc")}})
check("brain scope lands in <vault>/plugins", r.get("ok") and Path(r["path"]) == Path(VAULT) / "plugins" / "brain-only", r)
check("brain plugin is off and listed as vault", (desc("brain-only") or {}).get("source") == "vault"
      and desc("brain-only")["enabled"] is False)

r = jcall("auto", {"op": "write", "slug": "as-text", "files": json.dumps({"plugin.yaml": YAML.replace("vat_calc", "text_calc"),
                                                                        "plugin.py": PY.replace("vat_calc", "text_calc")})})
check("files sent as JSON text are accepted", r.get("ok") is True and r.get("enabled") is False, r)

# ---- 7. warnings: manifest tools vs registered names ----
r = jcall("auto", {"op": "write", "slug": "mismatch",
                   "files": {"plugin.yaml": YAML.replace("[vat_calc]", "[other_tool]"), "plugin.py": PY}})
check("mismatched tool names saved with a warning", r.get("ok") and any("other_tool" in w for w in r.get("warnings", [])), r)

# ---- 8. delete: only what this tool created, only when off ----
plugins_host.set_enabled("vat-calc", True, VAULT)
out = call("auto", {"op": "delete", "slug": "vat-calc"})
check("delete refuses a plugin that is ON", out.startswith("ERROR"), out)
plugins_host.set_enabled("vat-calc", False, VAULT)
r = jcall("auto", {"op": "delete", "slug": "vat-calc"})
check("delete removes an off plugin it created", r.get("ok") and not (GLOBAL / "vat-calc").exists()
      and desc("vat-calc") is None, r)
check("delete keeps a backup", (GLOBAL / plugin_authoring.STAGING / "bak" / "vat-calc" / "plugin.py").is_file())
hand = GLOBAL / "hand-made"
hand.mkdir(parents=True)
(hand / "plugin.yaml").write_text(YAML.replace("vat_calc", "hand_tool"), encoding="utf-8")
(hand / "plugin.py").write_text(PY.replace("vat_calc", "hand_tool"), encoding="utf-8")
plugins_host.set_enabled("hand-made", False, VAULT)
out = call("auto", {"op": "delete", "slug": "hand-made"})
check("delete refuses a plugin the owner installed", out.startswith("ERROR") and hand.is_dir(), out)
out = call("auto", {"op": "delete", "slug": "datetime-vn"})
check("delete refuses a system plugin", out.startswith("ERROR"))

# ---- 9. hub: the owner's session has it, a bot does not ----
_lazy_on = mcp_hub._lazy_on
mcp_hub._lazy_on = lambda n, chars: False
_t, r_owner = asyncio.run(mcp_hub.discover_all("full", vault_root=VAULT, force_refresh=True))
_t, r_bot = asyncio.run(mcp_hub.discover_all("full", vault_root=VAULT, force_refresh=True, for_bot=True))
mcp_hub._lazy_on = _lazy_on
check("hub serves javis_plugin to the owner", "javis_plugin" in r_owner)
check("hub hides javis_plugin from a bot", "javis_plugin" not in r_bot)

# ---- 10. text rules ----
for f in (SERVER / "plugin_authoring.py", ROOT / "system" / "plugins" / "javis-plugin" / "plugin.py",
          ROOT / "system" / "plugins" / "javis-plugin" / "plugin.yaml"):
    t = f.read_text(encoding="utf-8")
    check(f"no em/en dash in {f.name}", "\u2014" not in t and "\u2013" not in t)
skill = (ROOT / ".claude" / "skills" / "javis-builder" / "SKILL.md").read_text(encoding="utf-8")
check("javis-builder teaches javis_plugin op=write", "javis_plugin" in skill and "op=write" in skill)

print()
if fails:
    print(f"FAILED {len(fails)}: " + "; ".join(fails))
    sys.exit(1)
print("PASS")
