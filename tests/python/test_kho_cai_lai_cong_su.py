"""A Store agent can always come back: rename, delete, uninstall, install again (owner report 2026-11-04).

    python tests/run.py kho_cai_lai_cong_su

No network, no real brain, no real STATE_DIR.

The report: install "Linh Hồn Javis Vũ" from the Store, rename it (or delete it) on the Partners page.
After a delete the Store still said "Installed". After Uninstall + Install the agent never showed up
again. Two causes, both guarded here end to end through the real installer:

1. Install skipped, without a word, any item whose name the brain already had and the pack's ledger did
   not know (the user's renamed copy, kept on uninstall by design). Now the pack's copy goes in beside it
   under a free name and the result names it.
2. The Store's "installed" state read only the install ledger. A pack that is only brain items, all of
   them deleted, now reads as not installed, so the card offers Install.
"""
from _paths import ROOT, SERVER, DASHBOARD  # noqa: E402,F401
import asyncio
import io
import json
import os
import tempfile
import zipfile
from pathlib import Path

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-kho-cai-lai-")

import pack_install  # noqa: E402
import pack_vault  # noqa: E402
from routes import packs as packs_route  # noqa: E402

fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(extra)[:300] + "]") if extra and not cond else ""))
    if not cond:
        fails.append(name)


PID = "acme.soul"
MANIFEST = f"""format: javis-pack
spec: 1
id: {PID}
version: 1.0.0
name: {{vi: "Linh hồn", en: "Soul"}}
description: {{vi: "Thử"}}
compat: {{app: ">=0.1.0"}}
provides:
  agents: [vu]
"""
AGENT = "---\ntype: agent\nname: Linh Hồn Vũ\nslug: vu\nrole: CSKH\n---\nBạn là Vũ.\n"
CATALOG = {"id": PID, "kind": "agent", "provides": {"agents": ["vu"]}}


def zip_bytes() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr(f"{PID}/javis-pack.yaml", MANIFEST)
        z.writestr(f"{PID}/agents/vu.md", AGENT)
    return buf.getvalue()


def install(brain: Path) -> dict:
    s = pack_install.soi(zip_bytes(), "soul.zip")
    assert s.get("ok"), s
    return pack_install.cai(s["staging_id"], s["sha256"], brain_root=str(brain))


def uninstall() -> dict:
    return asyncio.run(pack_install.go(PID))


def store_says_installed() -> bool:
    hang = pack_install.doc_so().get(PID)
    return bool(hang) and not packs_route._gone_from_brain(PID, hang, CATALOG)


brain = Path(tempfile.mkdtemp(prefix="javis-kho-brain-"))
agents = brain / "agents"

r = install(brain)
check("install puts the agent in the brain", r.get("ok") and (agents / "vu.md").is_file(), r)
check("and the Store says installed", store_says_installed())

# ── Delete on the Partners page ──
(agents / "vu.md").unlink()
check("after deleting the agent in the app the Store no longer says installed", not store_says_installed())
r = install(brain)
check("Install from that card puts it back under its name", (agents / "vu.md").is_file()
      and not (r.get("vault") or {}).get("doi_ten"), r.get("vault"))
check("and the Store says installed again", store_says_installed())

# ── Rename on the Partners page, uninstall, install again (the reported dead end) ──
f = agents / "vu.md"
f.write_text(f.read_text(encoding="utf-8").replace("name: Linh Hồn Vũ", "name: Bống"), encoding="utf-8")
g = uninstall()
check("uninstall keeps the renamed copy", f.is_file() and (g.get("vault") or {}).get("giu_lai") == ["agents/vu"], g)
check("and the Store no longer lists it as installed", PID not in pack_install.doc_so())
r = install(brain)
ren = (r.get("vault") or {}).get("doi_ten") or []
check("install again adds the pack's agent under a new name", (agents / "vu-2.md").is_file()
      and [x.get("slug") for x in ren] == ["vu-2"], r.get("vault"))
check("the user's renamed agent is untouched", "name: Bống" in f.read_text(encoding="utf-8"))
check("the new copy is the pack's original", "name: Linh Hồn Vũ" in (agents / "vu-2.md").read_text(encoding="utf-8"))
check("its frontmatter slug matches its file name", "slug: vu-2" in (agents / "vu-2.md").read_text(encoding="utf-8"))
check("the Store says installed", store_says_installed())

# ── A pack with a connector or plugin stays installed whatever happens in the brain ──
check("a pack that brings a connector is never flipped by the brain",
      not packs_route._gone_from_brain(PID, {"connectors": ["x"]}, CATALOG))
check("a pack that provides no brain items is never flipped",
      not packs_route._gone_from_brain("acme.none", {}, {"provides": {}}))

# ── The UI says what happened ──
src = (DASHBOARD / "packs.js").read_text(encoding="utf-8")
vi = json.loads((DASHBOARD / "i18n" / "vi.json").read_text(encoding="utf-8"))
en = json.loads((DASHBOARD / "i18n" / "en.json").read_text(encoding="utf-8"))
check("the card explains why it offers Install again", 'tw("store.removed_from_brain")' in src
      and "removed_from_brain" in (SERVER / "routes" / "packs.py").read_text(encoding="utf-8"))
check("after install a renamed item is named on screen", "baoDoiTen(d, r)" in src
      and 'tw("store.installed_renamed.row"' in src)
check("both languages carry the new strings", all(k in vi and k in en for k in (
    "store.removed_from_brain", "store.installed_renamed.title", "store.installed_renamed.body",
    "store.installed_renamed.row")))

# ── Workflow delete validates its slug (found during this audit) ──
main_src = (SERVER / "main.py").read_text(encoding="utf-8")
i = main_src.index("async def delete_workflow(")
check("workflow delete rejects a path-like slug", "valid_file_slug(slug)" in main_src[i:i + 600])

if fails:
    raise SystemExit(f"FAIL - test_kho_cai_lai_cong_su: {len(fails)} lỗi: {fails}")
print("PASS test_kho_cai_lai_cong_su")
