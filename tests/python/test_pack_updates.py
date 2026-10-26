"""Store packs with a newer version ring the bell (0.335.0).

    python tests/run.py pack_updates      (no network: fake catalog, temporary state)

Owner 26/10/2026: "những bản plugin có phiên bản mới trong store thì phải báo về thông báo nhé". Guards: only installed
packs, a real newer number (numeric compare), one notice per new version, a stale catalog never used, the scheduler
keeps its own rhythm, and the bell item opens the Store.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import os
import tempfile

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-pack-updates-")

import pack_install  # noqa: E402
import pack_updates as PU  # noqa: E402
import packs_store  # noqa: E402

fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(extra)[:300] + "]") if extra and not cond else ""))
    if not cond:
        fails.append(name)


STORE = [
    {"id": "javis.zalo", "name": {"vi": "Zalo cá nhân", "en": "Personal Zalo"}, "version": "1.4.0"},
    {"id": "javis.crm", "name": {"en": "Customer CRM"}, "version": "1.10.0"},
    {"id": "javis.old", "name": {"en": "Old"}, "version": "0.9.0"},
    {"id": "javis.not-installed", "name": {"en": "Other"}, "version": "2.0.0"},
]
INSTALLED = {"javis.zalo": {"version": "1.3.0"}, "javis.crm": {"version": "1.9.0"}, "javis.old": {"version": "1.0.0"}}

ups = PU.find_updates(STORE, INSTALLED)
ids = {u["id"]: u for u in ups}
check("an installed pack with a newer Store version is an update", "javis.zalo" in ids
      and ids["javis.zalo"]["from"] == "1.3.0" and ids["javis.zalo"]["to"] == "1.4.0", ups)
check("versions compare as numbers: 1.10.0 is newer than 1.9.0", "javis.crm" in ids)
check("an older Store number is never an update", "javis.old" not in ids)
check("a pack that is not installed is not an update", "javis.not-installed" not in ids)

item = PU.notify(ups)
check("one bell notice for all new versions", item and item.get("kind") == "system" and item.get("channel") == PU.CHANNEL,
      item)
check("it names each pack with old and new version", item and "1.3.0 → 1.4.0" in item["body"]
      and "1.9.0 → 1.10.0" in item["body"], item and item["body"])
check("it says Javis never updates on its own", item and ("không tự cập nhật" in item["body"]
                                                       or "never updates on its own" in item["body"]))
check("the same versions do not ring again", PU.notify(ups) is None)
again = PU.notify([dict(ids["javis.zalo"], to="1.5.0")])
check("the next version of a pack rings again", again is not None and "1.5.0" in again["body"], again)

# The scheduler rhythm and the stale-catalog rule.
CALLS = []


async def fake_lay(lam_moi=False):
    CALLS.append(1)
    return {"ok": True, "stale": STALE[0], "packs": [dict(STORE[0], version=VER[0])]}


STALE, VER = [False], ["1.6.0"]
packs_store.lay = fake_lay
pack_install.doc_so = lambda: {"javis.zalo": {"version": "1.3.0"}}
t0 = 1_900_000_000.0
asyncio.run(PU.on_open(t0))
check("opening the dashboard checks and announces", len(CALLS) == 1 and PU._load().get("javis.zalo") == "1.6.0",
      PU._load())
asyncio.run(PU.on_open(t0 + 60))
check("opening it again within six hours does nothing", len(CALLS) == 1)
STALE[0], VER[0] = True, "1.7.0"
asyncio.run(PU.on_open(t0 + PU.INTERVAL + 5))
check("a stale catalog is read but never announced", len(CALLS) == 2 and PU._load().get("javis.zalo") == "1.6.0",
      (len(CALLS), PU._load()))

# 0.340.0, owner 2026-10-26: no background scan. Nothing on the scheduler loop; the dashboard opening drives it.
src = (ROOT / "server" / "main.py").read_text(encoding="utf-8")
check("no timer runs the Store check any more", "pack_updates.tick" not in src and not hasattr(PU, "tick"))
check("the check rides on the dashboard opening (/version)",
      "asyncio.create_task(pack_updates.on_open())" in src[src.index('@app.get("/version")'):][:800])
nj = (ROOT / "dashboard" / "notifications.js").read_text(encoding="utf-8")
check("pressing the notice opens the Javis Store",
      'item.channel === "store:updates"' in nj and "window.JavisPacks.moKho(\"\")" in nj)
import json  # noqa: E402
vi = json.loads((ROOT / "dashboard" / "i18n" / "vi.json").read_text(encoding="utf-8"))
en = json.loads((ROOT / "dashboard" / "i18n" / "en.json").read_text(encoding="utf-8"))
check("noti.open_store in vi and en", vi.get("noti.open_store") and en.get("noti.open_store"))
check("no em dash in the new files", all(chr(0x2014) not in p.read_text(encoding="utf-8")
                                         for p in (ROOT / "server" / "pack_updates.py", ROOT / "tests" / "python" / "test_pack_updates.py")))

if fails:
    print(f"\nFAIL - test_pack_updates: {len(fails)}: " + "; ".join(fails))
    raise SystemExit(1)
print("\nOK - test_pack_updates: all pass")
