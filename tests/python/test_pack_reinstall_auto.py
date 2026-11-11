"""A Store pack installed again gives its assistants back to Auto without asking (owner report 2026-11-11).

    python tests/run.py pack_reinstall_auto

No network, no model, no real brain. Through the real routes, installer and registry.

The report: brain "PSC Advisor", pack "ECC: Engineering team" (17 assistants). Uninstall the pack and install it
again: all 17 cards say "Auto: needs confirmation" and each one has to be opened and answered. The next reinstall
does it again. Three things asked for, all guarded here:

1. The same pack putting its own assistant back under the same name is the same assistant: no question.
   A file the USER wrote under an old name still asks.
2. When the question does have to be asked, one button answers it for a whole pack.
3. An assistant with Auto off and no open goal is never a question: nothing would start whichever way it is answered.
"""
from _paths import ROOT, SERVER, DASHBOARD  # noqa: E402,F401
import io
import os
import sqlite3
import tempfile
import zipfile
from pathlib import Path

STATE = tempfile.mkdtemp(prefix="javis-pack-auto-")
os.environ["JAVIS_STATE_DIR"] = STATE
BR = Path(tempfile.mkdtemp(prefix="javis-pack-auto-brain-")).resolve()
(BR / "agents").mkdir()

import main  # noqa: E402
import agent_presence  # noqa: E402
import pack_install  # noqa: E402
import pack_vault  # noqa: E402
import resonance_store as RS  # noqa: E402
from routes import packs as packs_route  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(extra)[:400] + "]") if extra and not cond else ""))
    if not cond:
        fails.append(name)


sent = []


async def fake_publish(ev):
    sent.append(ev)


main._CHAT_RUNTIME.publish = fake_publish
packs_route._DEPS.co_phien = lambda request: True     # the pack routes want a signed-in session
c = TestClient(main.app, base_url="http://127.0.0.1:8080")
store = main._resonance_store()
OWNER = RS.Principal("owner", "owner", str(BR))


def pack_zip(pid: str, name: str, agents: dict) -> bytes:
    manifest = (f"format: javis-pack\nspec: 1\nid: {pid}\nversion: 1.0.0\n"
                f'name: {{vi: "{name}", en: "{name} EN"}}\ndescription: {{vi: "Thử"}}\n'
                f"compat: {{app: \">=0.1.0\"}}\nprovides:\n  agents: [{', '.join(agents)}]\n")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr(f"{pid}/javis-pack.yaml", manifest)
        for slug, body in agents.items():
            z.writestr(f"{pid}/agents/{slug}.md", f"---\ntype: agent\nname: {slug}\nslug: {slug}\n---\n{body}\n")
    return buf.getvalue()


TEAM = "acme.team"
TEAM_ZIP = pack_zip(TEAM, "Đội thử", {"plan": "You plan.", "review": "You review.", "clean": "You clean."})


def install(data: bytes) -> dict:
    s = pack_install.soi(data, "pack.zip")
    assert s.get("ok"), s
    r = c.post("/packs/install", json={"staging_id": s["staging_id"], "consent_sha256": s["sha256"], "brain": str(BR)})
    assert r.status_code == 200, r.text
    return r.json()


def uninstall(pid: str) -> dict:
    r = c.post("/packs/uninstall", json={"id": pid})
    assert r.status_code == 200, r.text
    return r.json()


def listing() -> dict:
    return {a["slug"]: a for a in c.get(f"/resonance/agents?brain={BR}").json()["agents"]}


def auto(slug: str, on: bool) -> dict:
    r = c.post(f"/resonance/agents/toggle?brain={BR}", json={"slug": slug, "enabled": on})
    assert r.status_code == 200, r.text
    return r.json()["agent"]


def kinds(key: str) -> list:
    return [(e["kind"], e["payload"].get("reason") or e["payload"].get("origin") or "")
            for e in store.agent_events(str(BR), key)]


def open_goal(agent: dict, tag: str) -> str:
    """An open goal of `agent`, written the way the host writes one (no model)."""
    intent = store.add_intent(OWNER, f"s-{tag}", 1, "Lo giúp bản hướng dẫn")
    intent_id = intent["id"] if isinstance(intent, dict) else intent
    g, _new = store.create(OWNER, intent_id, {"understanding": "Bản hướng dẫn", "constraints": [], "criteria": []},
                           f"key-{tag}", session_id=f"s-{tag}", agent_key=agent["agent_key"],
                           agent_version=agent["config_version"])
    return g.id


# ═══════════ 1. the reported case: uninstall, install again, nobody is asked ═══════════
install(TEAM_ZIP)
plan = auto("plan", True)
review = auto("review", True)
clean = store.agent_register(OWNER, "clean")          # known to the host (it chatted), Auto never turned on
goal = open_goal(store.agent(str(BR), "plan"), "plan")
rows = listing()
check("the list says which Store pack an assistant's file comes from, by id and by its name",
      rows["plan"]["pack"] == TEAM and rows["plan"]["pack_name"] in ("Đội thử", "Đội thử EN")
      and rows["clean"]["pack"] == TEAM, rows["plan"])
check("a pack that is switched off still has its name (its assistants are still in the brain)",
      pack_install.doc_so()[TEAM].get("enabled") is False and agent_presence.pack_name(TEAM) in ("Đội thử", "Đội thử EN"))
check("an unknown or path-like pack id falls back to the id itself",
      agent_presence.pack_name("acme.nothing") == "acme.nothing" and agent_presence.pack_name("../x") == "../x")
check("the origin is recorded while the assistant is active",
      store.agent_origins(str(BR)).get(plan["agent_key"]) == "pack:" + TEAM)

for turn in (1, 2):
    sent.clear()
    uninstall(TEAM)
    gone = {s: store.agent(str(BR), s)["status"] for s in ("plan", "review", "clean")}
    check(f"round {turn}: uninstall leaves the three keys missing, at once",
          set(gone.values()) == {"missing"} and not (BR / "agents" / "plan.md").exists(), gone)
    check(f"round {turn}: open tabs are told", {"type": "resonance_agents"} in sent, sent)
    sent.clear()
    install(TEAM_ZIP)
    back = {s: store.agent(str(BR), s) for s in ("plan", "review", "clean")}
    check(f"round {turn}: install again restores all three without a click",
          all(a["status"] == "active" for a in back.values()), back)
    check(f"round {turn}: same keys, so goals and conversations stay with them",
          back["plan"]["agent_key"] == plan["agent_key"] and back["review"]["agent_key"] == review["agent_key"]
          and back["clean"]["agent_key"] == clean["agent_key"])
    check(f"round {turn}: the Auto switch is as it was", back["plan"]["enabled"] and back["review"]["enabled"]
          and not back["clean"]["enabled"])
    check(f"round {turn}: open tabs are told again", {"type": "resonance_agents"} in sent, sent)
    rows = listing()
    check(f"round {turn}: the Partners page shows no card waiting",
          not [s for s, a in rows.items() if a["status"] == "missing"], {s: a["status"] for s, a in rows.items()})

check("the restore is in the audit trail, with its reason", ("restored", "same_origin") in kinds(plan["agent_key"]),
      kinds(plan["agent_key"]))
check("the open goal is still the assistant's",
      [g.id for g in store.list_open(OWNER, agent_key=plan["agent_key"])] == [goal])
check("every state change still raises config_version (gates see it)",
      store.agent(str(BR), "plan")["config_version"] > plan["config_version"])

# ═══════════ 2. a file the USER wrote under an old name still asks ═══════════
own = BR / "agents" / "own.md"
own.write_text("---\nname: Own\n---\nMy first assistant.\n", encoding="utf-8")
mine = auto("own", True)
own.unlink()
check("own assistant, file deleted by hand: missing", listing().get("own") is None
      and store.agent(str(BR), "own")["status"] == "missing")
own.write_text("---\nname: Own\n---\nA different assistant under the old name.\n", encoding="utf-8")
row = listing()["own"]
check("own assistant with Auto on, a file is back: the owner is still asked",
      row["status"] == "missing" and row["pack"] == "", row)

# A pack file that lands on the name of the user's own lost assistant is not "the pack putting its own back".
own.unlink()
listing()
OTHER = "acme.other"
install(pack_zip(OTHER, "Gói khác", {"own": "The pack's assistant called own."}))
row = listing()["own"]
check("a pack file taking the name of the user's lost assistant still asks",
      row["status"] == "missing" and row["pack"] == OTHER and store.agent(str(BR), "own")["agent_key"] == mine["agent_key"],
      row)
r = c.post(f"/resonance/agents/confirm?brain={BR}", json={"agent_key": mine["agent_key"], "same": False})
check("and the owner can still say it is a new assistant", r.status_code == 200
      and r.json()["agent"]["agent_key"] != mine["agent_key"] and not r.json()["agent"]["enabled"], r.text)

# ═══════════ 3. Auto off and nothing open: never a question ═══════════
note = BR / "agents" / "note.md"
note.write_text("---\nname: Note\n---\nTakes notes.\n", encoding="utf-8")
n0 = store.agent_register(OWNER, "note")
note.unlink()
listing()
check("Auto off: the key still goes missing with its file", store.agent(str(BR), "note")["status"] == "missing")
note.write_text("---\nname: Note\n---\nTakes notes, rewritten.\n", encoding="utf-8")
row = listing()["note"]
check("Auto off, no open goal, file back: restored without asking, switch still off",
      row["status"] == "active" and not row["enabled"] and row["agent_key"] == n0["agent_key"], row)
check("with its own reason in the audit trail", ("restored", "nothing_open") in kinds(n0["agent_key"]),
      kinds(n0["agent_key"]))

busy = BR / "agents" / "busy.md"
busy.write_text("---\nname: Busy\n---\nHas work.\n", encoding="utf-8")
b0 = auto("busy", True)
open_goal(store.agent(str(BR), "busy"), "busy")
auto("busy", False)
busy.unlink()
listing()
busy.write_text("---\nname: Busy\n---\nHas work, rewritten.\n", encoding="utf-8")
row = listing()["busy"]
check("Auto off but a goal is open: the owner is still asked", row["status"] == "missing" and row["goals_open"] == 1
      and row["agent_key"] == b0["agent_key"], row)
check("a store-level restore refuses it too", store.agent_restore(str(BR), b0["agent_key"]) is None)
check("and refuses a key that is not missing", store.agent_restore(str(BR), n0["agent_key"]) is None)

# ═══════════ 4. one button for a whole pack, for the cards that do wait ═══════════
# The state of a machine upgraded from an older version: keys that went missing before any origin was recorded.
uninstall(TEAM)
con = sqlite3.connect(str(Path(STATE) / "resonance.sqlite3"))
con.execute("DELETE FROM resonance_agent_events WHERE kind='origin'")
con.commit()
con.close()
install(TEAM_ZIP)
rows = listing()
check("no origin on record: Auto-on assistants wait, the Auto-off one without goals does not",
      rows["plan"]["status"] == "missing" and rows["review"]["status"] == "missing"
      and rows["clean"]["status"] == "active", {s: rows[s]["status"] for s in ("plan", "review", "clean")})
check("the waiting rows name their pack, so the page can group them",
      rows["plan"]["pack"] == TEAM and rows["review"]["pack"] == TEAM and rows["busy"]["pack"] == "")
sent.clear()
r = c.post(f"/resonance/agents/confirm?brain={BR}", json={"pack": TEAM, "same": True})
check("one request confirms the whole pack", r.status_code == 200 and r.json().get("confirmed") == 2, r.text)
check("and tells the open tabs once", sent == [{"type": "resonance_agents"}], sent)
rows = listing()
check("both are the old assistants again, Auto on", all(rows[s]["status"] == "active" and rows[s]["enabled"] for s in
                                                        ("plan", "review"))
      and rows["plan"]["agent_key"] == plan["agent_key"])
check("an assistant outside that pack is not touched", rows["busy"]["status"] == "missing")
r = c.post(f"/resonance/agents/confirm?brain={BR}", json={"pack": "acme.nothing", "same": True})
check("an unknown pack confirms nothing", r.status_code == 200 and r.json().get("confirmed") == 0, r.text)
check("after that confirmation the origin is on record, so the next reinstall asks nobody",
      store.agent_origins(str(BR)).get(plan["agent_key"]) == "pack:" + TEAM)
uninstall(TEAM)
install(TEAM_ZIP)
check("and it does not", store.agent(str(BR), "plan")["status"] == "active"
      and store.agent(str(BR), "review")["status"] == "active")

# ═══════════ 5. only an untouched pack file counts as the pack's ═══════════
packs = pack_vault.agent_packs(str(BR))
check("pack files are mapped to their pack", packs.get("plan") == TEAM and packs.get("clean") == TEAM, packs)
f = BR / "agents" / "plan.md"
f.write_text(f.read_text(encoding="utf-8") + "\nMy own extra instruction.\n", encoding="utf-8")
check("a pack file the user edited is the user's", "plan" not in pack_vault.agent_packs(str(BR)))
listing()
check("and its origin is dropped", plan["agent_key"] not in store.agent_origins(str(BR)))
check("a brain that holds none of the pack's files maps nothing",
      pack_vault.agent_packs(tempfile.mkdtemp(prefix="javis-pack-auto-other-")) == {})
check("sync reports what it changed", agent_presence.sync(store, str(BR), [m for m in listing()]) ==
      {"missing": [], "restored": []})

# ═══════════ 6. wiring ═══════════
api_src = (SERVER / "resonance_api.py").read_text(encoding="utf-8")
routes_src = (SERVER / "routes" / "packs.py").read_text(encoding="utf-8")
check("the Auto list goes through the one sync", "agent_presence.sync(store, root, have, packs)" in api_src)
check("uninstall records origins BEFORE the files go and syncs after",
      routes_src.index("await _agents_changed(root)\n        r = await pack_install.go(") > 0
      and routes_src.count("await _agents_changed(root)") == 3)

if fails:
    raise SystemExit(f"FAIL - test_pack_reinstall_auto: {len(fails)}: {fails}")
print("PASS test_pack_reinstall_auto")
