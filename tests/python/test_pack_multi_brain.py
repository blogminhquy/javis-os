"""One Store pack installed in several brains (owner, 16/11/2026).

    python tests/run.py pack_multi_brain      (no network)

Community report: a pack installed in brain A showed "Installed" in brain B with only Turn off and Uninstall, so its
assistants and skills could never reach B. The ledger now keeps one entry per brain: installing from B adds B, an
update refreshes every brain, uninstalling clears every brain, and the old one-brain ledger is still read.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import json
import os
import tempfile
from pathlib import Path

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-pack-multi-"))

import improvement_assets  # noqa: E402
import pack_vault  # noqa: E402

fails = []


def check(name, cond, extra=None):
    print(("ok   " if cond else "FAIL ") + name + ("" if cond or extra is None else f"  [{extra}]"))
    if not cond:
        fails.append(name)


def make_pack(root: Path, version: str) -> Path:
    pack = root / "javis.humanizer"
    (pack / "skills" / "humanizer").mkdir(parents=True, exist_ok=True)
    (pack / "skills" / "humanizer" / "SKILL.md").write_text(
        f"---\nname: humanizer\ndescription: v{version}\n---\nBody {version}\n", encoding="utf-8")
    (pack / "agents").mkdir(exist_ok=True)
    (pack / "agents" / "bien-tap.md").write_text(f"---\nname: Bien tap\nslug: bien-tap\n---\nv{version}\n",
                                                 encoding="utf-8")
    return pack


tmp = Path(tempfile.mkdtemp(prefix="javis-pack-multi-fs-"))
saved_dir = pack_vault.HIEU_UNG_DIR
pack_vault.HIEU_UNG_DIR = tmp / "packs-state"
pack_vault.HIEU_UNG_DIR.mkdir(parents=True)
pid = "javis.humanizer"
try:
    brain_a, brain_b = tmp / "Thao M-Mola", tmp / "EMBA"
    for b in (brain_a, brain_b):
        (b / "agents").mkdir(parents=True)
        (b / "skills").mkdir()
    pack = make_pack(tmp / "packs-v1", "1")

    pack_vault.cai_moi_brain(pid, pack, str(brain_a))
    w = pack_vault.brain_of(pid, str(brain_b))
    check("installed in A, seen from B: offered for B", w["other"] is True and w["here"] == 0 and w["name"] == "Thao M-Mola", w)

    bao = pack_vault.cai(pid, pack, str(brain_b))
    check("installing from B puts the items in B", (brain_b / "skills" / "humanizer" / "SKILL.md").is_file()
          and (brain_b / "agents" / "bien-tap.md").is_file() and len(bao["them"]) == 2, bao)
    check("and keeps them in A", (brain_a / "skills" / "humanizer" / "SKILL.md").is_file())
    check("the ledger lists both brains", len(pack_vault.brains(pid)) == 2, pack_vault.brains(pid))
    check("from B nothing is flagged any more", pack_vault.brain_of(pid, str(brain_b))["other"] is False)
    check("both brains count", pack_vault.con_lai(pid)["present"] == 4
          and pack_vault.con_lai(pid, str(brain_a))["present"] == 2)
    so = pack_vault.doc_so(pid)
    check("the old top-level keys mirror the first brain for an older Javis",
          so.get("brain") == str(brain_a) and "skills/humanizer" in (so.get("items") or {}), so.keys())
    check("the Auto registry sees the pack's agent in each brain",
          pack_vault.agent_packs(str(brain_a)).get("bien-tap") == pid
          and pack_vault.agent_packs(str(brain_b)).get("bien-tap") == pid)
    try:
        improvement_assets.capture_source(brain_b, "skill", "humanizer", pack_state_dir=pack_vault.HIEU_UNG_DIR)
        check("a pack skill in the second brain is still protected from self-improvement", False)
    except improvement_assets.SourceError as e:
        check("a pack skill in the second brain is still protected from self-improvement",
              str(e) == "pack_source_protected", str(e))

    # The user edits the agent in B, then the pack is updated from A.
    edited = brain_b / "agents" / "bien-tap.md"
    edited.write_text("---\nname: Bien tap\nslug: bien-tap\n---\nmy own text\n", encoding="utf-8")
    pack2 = make_pack(tmp / "packs-v2", "2")
    bao = pack_vault.cai_moi_brain(pid, pack2, str(brain_a))
    check("an update refreshes the other brain too", "Body 2" in (brain_b / "skills" / "humanizer" / "SKILL.md")
          .read_text(encoding="utf-8") and bao["brains_khac"] == ["EMBA"], bao)
    check("but never overwrites what the user edited there", "my own text" in edited.read_text(encoding="utf-8"))

    plan = pack_vault.ke_hoach_go(pid)
    check("the uninstall plan covers both brains", set(plan["brains"]) == {str(brain_a), str(brain_b)}
          and all(x.get("brain") for x in plan["xoa"] + plan["giu"]), plan)
    pack_vault.go(pid)
    check("uninstall clears every brain, keeping the edited file",
          not (brain_a / "skills" / "humanizer").exists() and not (brain_b / "skills" / "humanizer").exists()
          and edited.is_file() and not pack_vault.doc_so(pid))

    # A ledger written by an older Javis (one brain) is read as before.
    pack_vault.cai(pid, pack, str(brain_a))
    items = pack_vault.doc_so(pid)["items"]
    pack_vault._ghi_so(pid, {"brain": str(brain_a), "items": items})
    check("an old one-brain ledger still reads", pack_vault.brains(pid) == [str(brain_a)]
          and pack_vault.con_lai(pid, str(brain_a))["present"] == 2)
    pack_vault.cai(pid, pack, str(brain_b))
    check("and gains a second brain without losing the first", len(pack_vault.brains(pid)) == 2)

    # A brain whose items the user deleted is dropped on the next update instead of being filled again.
    for p in (brain_b / "skills" / "humanizer", brain_b / "agents" / "bien-tap-2.md", brain_b / "agents" / "bien-tap.md"):
        if p.is_dir():
            import shutil
            shutil.rmtree(p)
        elif p.is_file() and "my own text" not in p.read_text(encoding="utf-8"):
            p.unlink()
    pack_vault.cai_moi_brain(pid, pack2, str(brain_a))
    check("a brain the user emptied is not filled again by an update from another brain",
          pack_vault.brains(pid) == [str(brain_a)] and not (brain_b / "skills" / "humanizer").exists(),
          pack_vault.brains(pid))
finally:
    pack_vault.HIEU_UNG_DIR = saved_dir

routes = (ROOT / "server" / "routes" / "packs.py").read_text(encoding="utf-8")
check("the add-to-brain route copies from the installed pack folder, nothing downloaded",
      '@router.post("/packs/add-to-brain")' in routes and "pack_vault.cai, pid, thu_muc, root" in routes)
check("uninstall tells the Auto registry about every brain", "for root in roots:" in routes)
inst = (ROOT / "server" / "pack_install.py").read_text(encoding="utf-8")
check("install and update go through cai_moi_brain", "pack_vault.cai_moi_brain(pid, dich, brain_root)" in inst)
js = (ROOT / "dashboard" / "packs.js").read_text(encoding="utf-8")
check("the card offers Install in this brain", 'act: "addbrain"' in js and '"/packs/add-to-brain"' in js)
for lang in ("vi", "en"):
    d = json.loads((ROOT / "dashboard" / "i18n" / f"{lang}.json").read_text(encoding="utf-8"))
    check(f"{lang}.json has the button and error strings",
          all(d.get(k) for k in ("store.btn.add_to_brain", "store.add_to_brain_failed")))

print()
if fails:
    print(f"FAIL - test_pack_multi_brain: {len(fails)}: " + ", ".join(fails))
    raise SystemExit(1)
print("OK - test_pack_multi_brain: all pass")
