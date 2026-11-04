"""Javis Core's own name and style in one brain (owner, 04/11/2026: "add a button so people can rename Javis Core, and on
the first chat it asks for its name, keeps a style that suits the user and learns, instead of always Javis Core").

    python tests/run.py javis_core_name

No network, no model.
- identity(): empty by default; set_identity() cleans the name (one line, no long dashes, 40 characters) and saves it
  in <brain>/Javis/core.json, one file per brain.
- The role block: no name and never asked = ask once and call op=asked; asked = no asking again; a name = speak as it.
- POST /javis-core/name renames it for that brain only; GET /agents?system=1 shows the name, keeps the slug.
- The chat tool `javis_core_name` (bundled plugin) writes the same file, owner only.
- The agent routes still refuse to delete or edit Javis Core, and no longer say it cannot be renamed.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import importlib.util
import os
import sys
import tempfile
from pathlib import Path

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-core-name-")
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (f"  [{str(extra)[:300]}]" if extra and not cond else ""))
    if not cond:
        fails.append(name)


import javis_core  # noqa: E402

# ---- 1. the identity file ----
A = Path(tempfile.mkdtemp(prefix="core-name-a-"))
B = Path(tempfile.mkdtemp(prefix="core-name-b-"))
check("no name by default", javis_core.identity(A) == {"name": "", "style": "", "asked": False})
check("...so it is still called Javis Core", javis_core.display_name(A) == "Javis Core")
me = javis_core.set_identity(A, name="  Mây " + chr(0x2014) + " bé\n xinh  ")
check("the name is cleaned: one line, no long dash, spaces collapsed", me["name"] == "Mây bé xinh", me)
check("a name counts as asked", me["asked"] is True)
check("saved in the brain's Javis folder", (A / "Javis" / "core.json").is_file())
check("another brain keeps its own (none)", javis_core.identity(B)["name"] == "")
check("40 characters at most", len(javis_core.set_identity(B, name="x" * 99)["name"]) == 40)
javis_core.set_identity(B, name="")
check("an empty name goes back to Javis Core", javis_core.display_name(B) == "Javis Core")
javis_core.set_identity(A, style="thân thiện, ngắn gọn")
check("style is kept apart from the name", javis_core.identity(A)["name"] == "Mây bé xinh"
      and javis_core.identity(A)["style"] == "thân thiện, ngắn gọn")

# ---- 2. what the role block tells the model ----
C = Path(tempfile.mkdtemp(prefix="core-name-c-"))
blk = javis_core.prompt_block(C)
check("no name, never asked: ask once and record it", "CHƯA có tên riêng" in blk and "op=asked" in blk)
javis_core.set_identity(C, asked=True)
blk = javis_core.prompt_block(C)
check("asked already: no asking again", "op=asked" not in blk and "chưa có tên riêng" in blk)
blk = javis_core.prompt_block(A)
check("named: speaks as that name, with the agreed style",
      "**Mây bé xinh**" in blk and "thân thiện, ngắn gọn" in blk and "op=asked" not in blk)
check("without a brain the block is the plain role block", javis_core.prompt_block() == javis_core.prompt_block(None)
      and "tên riêng" not in javis_core.prompt_block().split("# === JAVIS CORE ===")[-1].split("Tên và phong cách")[0])
check("the block stays small with a name and a style", len(javis_core.prompt_block(A)) < 3000, len(javis_core.prompt_block(A)))
check("the role body tells it to fit its style to the user and save it with the tool",
      "javis_core_name" in javis_core.definition()["body"] and "style" in javis_core.definition()["body"])

# ---- 3. the server: rename button and the Partners list ----
import config as cfgmod  # noqa: E402
import main  # noqa: E402
import mcp_hub  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

if os.environ["JAVIS_STATE_DIR"] not in str(cfgmod.STATE_DIR):
    print(f"FAIL state dir is not the temp dir: {cfgmod.STATE_DIR}. STOP.")
    sys.exit(1)

client = TestClient(main.app, base_url="http://127.0.0.1:8080")
D = Path(tempfile.mkdtemp(prefix="core-name-d-"))
(D / "agents").mkdir()
r = client.post("/javis-core/name", data={"name": "Sky", "brain": str(D)})
check("POST /javis-core/name renames it", r.status_code == 200 and r.json().get("name") == "Sky", r.text)
check("...in that brain's file", javis_core.identity(D)["name"] == "Sky")
ds = client.get("/agents", params={"brain": str(D), "prompt": 0, "system": 1}).json()["agents"]
core = ds[0]
check("the Partners list shows the new name, same slug and system flags",
      core["slug"] == "javis-core" and core["name"] == "Sky" and core["custom_name"] == "Sky"
      and core["system_name"] == "Javis Core" and core["system"] is True, core)
sid = main.get_store().create_session(brain=main._brain_key(str(D)), channel=javis_core.CHANNEL)
check("a Core chat of that brain is told its name", "**Sky**" in main._javis_core_block(sid))
r = client.post("/javis-core/name", data={"name": "", "brain": str(D)})
check("an empty name goes back to Javis Core", r.json().get("name") == "Javis Core" and r.json().get("custom_name") == "")
r = client.post("/agents/delete", data={"slug": "javis-core", "brain": str(D)})
check("deleting it is still refused", r.status_code == 403)
check("...and the refusal no longer says it cannot be renamed", "renamed" not in r.json().get("error", "")
      and "đổi tên," not in r.json().get("error", ""), r.text)

# ---- 4. the chat tool ----
check("the tool is the owner's only (a customer bot never renames the owner's assistant)",
      "javis_core_name" in mcp_hub.OWNER_ONLY_TOOLS)
yml = (ROOT / "system/plugins/javis-core-name/plugin.yaml").read_text(encoding="utf-8")
check("the plugin ships enabled at the safe level",
      "slug: javis-core-name" in yml and "enabled: true" in yml and "min_mode: safe" in yml and "javis_core_name" in yml)
spec = importlib.util.spec_from_file_location("javis_core_name_plugin", ROOT / "system/plugins/javis-core-name/plugin.py")
plug = importlib.util.module_from_spec(spec)
spec.loader.exec_module(plug)
reg = {}


class _Reg:
    def register_tool(self, name, desc, fn, **kw):
        reg[name] = fn


plug.register(_Reg())
run = reg["javis_core_name"]


class _Ctx:
    vault_root = str(Path(tempfile.mkdtemp(prefix="core-name-e-")))


ctx = _Ctx()
check("op=get with no name", "chưa đặt" in run({"op": "get"}, ctx))
run({"op": "asked"}, ctx)
check("op=asked records it", javis_core.identity(ctx.vault_root)["asked"] is True)
out = run({"op": "set", "name": "Bé Na", "style": "vui vẻ"}, ctx)
check("op=set saves name and style", javis_core.identity(ctx.vault_root)["name"] == "Bé Na"
      and javis_core.identity(ctx.vault_root)["style"] == "vui vẻ" and "Bé Na" in out, out)
check("op=set with nothing to set is an error", run({"op": "set"}, ctx).startswith("ERROR"))
run({"op": "reset"}, ctx)
check("op=reset goes back to Javis Core", javis_core.identity(ctx.vault_root)["name"] == ""
      and javis_core.identity(ctx.vault_root)["style"] == "")
check("no brain: refused, nothing written", run({"op": "set", "name": "X"}, type("C", (), {"vault_root": ""})()).startswith("ERROR"))

# ---- 5. the card ----
ws = (ROOT / "dashboard/workspace.js").read_text(encoding="utf-8")
check("the Core card has a rename button that saves through the endpoint",
      'id="wsCoreRename"' in ws and '"/javis-core/name"' in ws and "ganDoiTenCore(host, item)" in ws)
import json  # noqa: E402
vi = json.loads((ROOT / "dashboard/i18n/vi.json").read_text(encoding="utf-8"))
en = json.loads((ROOT / "dashboard/i18n/en.json").read_text(encoding="utf-8"))
keys = ("ws.core_rename", "ws.core_rename_err", "ws.core_name_note")
check("i18n vi/en", all(vi.get(k) and en.get(k) for k in keys))

dashes = [chr(0x2014), chr(0x2013)]
for f in (Path(__file__), ROOT / "system/plugins/javis-core-name/plugin.py", ROOT / "system/plugins/javis-core-name/plugin.yaml",
          ROOT / "server/javis_core.py", ROOT / "system/agents/javis-core.md"):
    check(f"no em or en dash in {f.name}", not any(d in f.read_text(encoding="utf-8") for d in dashes))
check("no em or en dash in the new screen text", not any(d in vi[k] + en[k] for k in keys for d in dashes))

print()
if fails:
    raise SystemExit(f"FAIL {len(fails)}: " + "; ".join(fails[:6]))
print("ALL PASS")
