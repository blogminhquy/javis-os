"""The Store says which brain holds a pack's assistants and skills (#1308).

    python tests/run.py pack_items_brain      (no network)

A pack is installed for the whole machine (connector, plugin, the "Installed" mark), but its assistants, workflows
and skills are placed in ONE brain, the one open at install time. Seen from another brain the card said "Installed"
although nothing of the pack was there, and Uninstall removed the items from a brain the user was not looking at,
with a confirmation that listed them without saying where they were.

The first fix (10/11/2026) only named the brain. On 16/11/2026, after a community report ("installed in one brain, the
other brain says installed but I cannot install it there"), the owner opened packs to several brains: the card offers
"Install in this brain", an update refreshes every brain, and uninstalling clears them all
(test_pack_multi_brain.py covers that part).
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import json
import os
import tempfile
from pathlib import Path

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-pack-brain-"))

import pack_vault  # noqa: E402

fails = []


def check(name, cond, extra=None):
    print(("ok   " if cond else "FAIL ") + name + ("" if cond or extra is None else f"  [{extra}]"))
    if not cond:
        fails.append(name)


tmp = Path(tempfile.mkdtemp(prefix="javis-pack-brain-fs-"))
saved_dir = pack_vault.HIEU_UNG_DIR
pack_vault.HIEU_UNG_DIR = tmp / "packs-state"
pack_vault.HIEU_UNG_DIR.mkdir(parents=True)
try:
    brain_a = tmp / "Brain Trịnh Lan Anh"
    brain_b = tmp / "Brain Looptours"
    (brain_a / "agents").mkdir(parents=True)
    brain_b.mkdir()
    agent = brain_a / "agents" / "javis-vu.md"
    agent.write_text("---\nname: Javis Vũ\n---\n", encoding="utf-8")
    pack_vault._ghi_so("javis.demo", {"brain": str(brain_a), "items": {
        "agents/javis-vu": {"loai": "agents", "slug": "javis-vu", "duong": str(agent), "hash": pack_vault._hash(agent)}}})

    w = pack_vault.brain_of("javis.demo", str(brain_a))
    check("in the brain that holds the items: named, not 'other'",
          w["brain"] == str(brain_a) and w["name"] == "Brain Trịnh Lan Anh" and w["present"] == 1
          and w["here"] == 1 and w["other"] is False, w)
    w = pack_vault.brain_of("javis.demo", str(brain_b))
    check("from another brain: the same name, flagged as another brain",
          w["name"] == "Brain Trịnh Lan Anh" and w["present"] == 1 and w["other"] is True, w)
    check("with no open brain given nothing is flagged", pack_vault.brain_of("javis.demo")["other"] is False)
    check("a path spelled differently is still the same brain",
          pack_vault.brain_of("javis.demo", str(brain_a) + os.sep)["other"] is False)

    agent.unlink()
    w = pack_vault.brain_of("javis.demo", str(brain_b))
    check("once the items are gone there is nothing in 'another brain' to warn about",
          w["present"] == 0 and w["other"] is False, w)
    w = pack_vault.brain_of("javis.unknown", str(brain_b))
    check("a pack with no ledger (connector only) is never flagged",
          w["brain"] == "" and w["present"] == 0 and w["other"] is False, w)
finally:
    pack_vault.HIEU_UNG_DIR = saved_dir

routes = (ROOT / "server" / "routes" / "packs.py").read_text(encoding="utf-8")
check("the uninstall plan names every brain and whether one is not the open brain",
      'plan["vault"]["brain_name"] = ", ".join(w.get("names") or []) or w["name"]' in routes
      and 'plan["vault"]["other_brain"]' in routes)
check("the Store list marks a pack whose items are in another brain, and offers to add it here",
      'g["items_brain"] = w["name"]' in routes and 'g["add_to_brain"] = True' in routes)
check("a pack whose items the user deleted keeps its own state (Install again), not this one",
      routes.index('g["removed_from_brain"] = True') < routes.index('g["items_brain"] = w["name"]')
      and "            elif hang:" in routes)

js = (ROOT / "dashboard" / "packs.js").read_text(encoding="utf-8")
check("the dashboard sends the open brain to both routes",
      js.count('brainQuery(') >= 5 and '"/packs/uninstall-plan?id=" + encodeURIComponent(pid) + brainQuery("&")' in js)
check("the uninstall confirmation names the brain and warns when it is another one",
      'tw("store.rm.vault_in", { count: xoa.length, brain: esc(vaultBrain) })' in js
      and 'tw("store.rm.vault_other")' in js and "other_brain" in js)
check("the card says where the items are", 'tw("store.items_other_brain", { brain: esc(g.items_brain) })' in js)
for lang in ("vi", "en"):
    d = json.loads((ROOT / "dashboard" / "i18n" / f"{lang}.json").read_text(encoding="utf-8"))
    check(f"{lang}.json has the three strings, each short enough to stand outside an (i)",
          all(0 < len(d.get(k, "")) <= 100 for k in ("store.items_other_brain", "store.rm.vault_in", "store.rm.vault_other"))
          and "{brain}" in d["store.items_other_brain"] and "{brain}" in d["store.rm.vault_in"])

print()
if fails:
    print(f"FAIL - test_pack_items_brain: {len(fails)}: " + ", ".join(fails))
    raise SystemExit(1)
print("OK - test_pack_items_brain: all pass")
