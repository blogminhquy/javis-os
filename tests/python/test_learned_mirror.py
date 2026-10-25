"""Learned-knowledge mirror inside the brain folder (owner request 2026-10-25, server/learned_mirror.py).

    python tests/run.py learned_mirror      (no network; uses git for one check when it is installed)

What a chatbot's reply-policy judge and the agents learned lives in STATE_DIR SQLite stores keyed by machine-local
random ids. This test checks that it is mirrored into `<brain>/Javis/learned/`, split by privacy (customer chat text
only in `*.private.json`, which the GitHub backup never takes), and restored on a "fresh machine" (new STATE_DIR, same
brain folder, new bot id and new agent key), once only.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

STATE_A = tempfile.mkdtemp(prefix="javis-lm-a-")
BRAINS = tempfile.mkdtemp(prefix="javis-lm-brains-")
os.environ["JAVIS_STATE_DIR"] = STATE_A
os.environ["BRAINS_DIR"] = BRAINS
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import config as cfgmod  # noqa: E402
import chatbot_store  # noqa: E402
import chatbot_reply_policy_store as rps  # noqa: E402
import resonance_store  # noqa: E402
import agent_lessons as AL  # noqa: E402
import agent_judge_store  # noqa: E402
import team_store  # noqa: E402
import git_brain  # noqa: E402
import learned_mirror as LM  # noqa: E402

_fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(extra) + "]") if extra and not cond else ""))
    if not cond:
        _fails.append(name)


def use_state(d):
    """Point every store at another STATE_DIR (a different machine)."""
    cfgmod.STATE_DIR = Path(d)
    chatbot_store.STORE_PATH = Path(d) / "chatbots.json"
    LM._cache.clear()


def sha(p):
    import hashlib
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


BRAIN = Path(BRAINS) / "Shop"
BRAIN.mkdir(parents=True)
ROOT_B = str(BRAIN.resolve())
LEARNED = BRAIN / "Javis" / "learned"
NOW = 1_800_000_000.0
CHAT_TEXT = "customer asks about shipping price to Hanoi"


def make_bot(name="Shop Bot"):
    bid, err = chatbot_store.create_bot({"name": name, "agent_slug": "sales", "brain": ROOT_B})
    assert bid, err
    return bid


def stores_in(d):
    return sorted(n for n in os.listdir(d) if n.endswith(".sqlite3"))


# ---- 1. a bot that learned nothing: no file, no store ----
bot_a = make_bot()
LM.sync_all()
check("bot with no learned data: no Javis/learned folder", not LEARNED.exists())
check("bot with no learned data: no SQLite store created", stores_in(STATE_A) == [], stores_in(STATE_A))
check("bot with no learned data: no mirror state file", not (Path(STATE_A) / LM.STATE_NAME).exists())

# ---- 2. bot knowledge is split by privacy ----
rps.set_role_profile(bot_a, "Sales role written from the Agent text", "hash1", NOW)
rps.set_tuning(bot_a, "threshold", "0.6", NOW)
rps.add_lesson(bot_a, "Stay quiet when two customers talk to each other", NOW, source="")
rps.set_offset(bot_a, "group-1", 0.9, NOW)          # clamped to 0.25 by the store
rps.add_case(bot_a, "", "bootstrap example from the agent", {"q": 1}, "reply", "role", "bootstrap", 1.0, now=NOW)
rps.add_case(bot_a, "group-1", CHAT_TEXT, {"q": 1}, "reply", "missed", "auto", 1.0, now=NOW)
rps.add_case(bot_a, "group-1", "owner taught: answer price questions", {}, "reply", "owner", "owner", 1.5, now=NOW)
rep = LM.sync_all()
pub_p, priv_p = LEARNED / "bots" / "shop-bot.json", LEARNED / "bots" / "shop-bot.private.json"
check("export writes the backed-up bot file", pub_p.is_file(), rep)
check("export writes the private bot file", priv_p.is_file(), rep)
pub = json.loads(pub_p.read_text(encoding="utf-8"))
priv = json.loads(priv_p.read_text(encoding="utf-8"))
check("bot file: role profile, tuning, lessons, offsets",
      pub["role_profile"]["agent_hash"] == "hash1" and pub["tuning"] == {"threshold": "0.6"}
      and [x["text"] for x in pub["lessons"]] == ["Stay quiet when two customers talk to each other"]
      and pub["threshold_offsets"][0]["chat_id"] == "group-1" and pub["threshold_offsets"][0]["offset"] == 0.25)
check("bot file: only the bootstrap case", [c["source"] for c in pub["cases"]] == ["bootstrap"], pub["cases"])
check("bot file carries no customer chat text", CHAT_TEXT not in pub_p.read_text(encoding="utf-8"))
check("private file: the chat cases (auto and owner), not the bootstrap one",
      sorted(c["source"] for c in priv["cases"]) == ["auto", "owner"]
      and CHAT_TEXT in [c["text"] for c in priv["cases"]])
check("bot file keeps no machine-local bot id", bot_a not in pub_p.read_text(encoding="utf-8"))

# ---- 3. unchanged data: no rewrite ----
s1, s2 = sha(pub_p), sha(priv_p)
m1 = pub_p.stat().st_mtime_ns
rep = LM.sync_all()
check("unchanged data: nothing written", not rep.get("wrote"), rep)
check("unchanged data: files byte-identical", sha(pub_p) == s1 and sha(priv_p) == s2 and pub_p.stat().st_mtime_ns == m1)

# ---- 4. agent knowledge ----
rs = resonance_store.GoalStore(Path(STATE_A) / "resonance.sqlite3")
ts = team_store.TeamStore(Path(STATE_A) / "team.sqlite3")
team_a = ts.create_team(ROOT_B, "Launch", "", "sess-a")["team_id"]
key_a = rs.agent_register(resonance_store.Principal("owner", "owner", ROOT_B), "sales")["agent_key"]
AL.add(rs, agent_key=key_a, scope=f"dm:{key_a}", kind="method", text="Answer in short bullets", source="self", at=NOW)
gone = AL.add(rs, agent_key=key_a, scope=f"dm:{key_a}", kind="method", text="Use a formal tone", source="self",
              at=NOW + 1)
AL.revoke(rs, gone, by="owner", reason="owner disliked it", at=NOW + 2)
AL.add(rs, agent_key=key_a, scope=f"team:{team_a}", kind="collab", text="Wait for the leader in Launch",
       source="self", at=NOW + 3)
with rs._Tx(rs) as c:
    rs._insert_lesson(c, ROOT_B, key_a, "presentation", "length", "full", "short", "active", NOW)
js = agent_judge_store.JudgeStore(Path(STATE_A) / agent_judge_store.STORE_NAME)
js.upsert_profile(key_a, role_text="Sales helper", eagerness="high", source="owner", now=NOW)
js.set_offset(key_a, f"dm:{key_a}", 0.1, now=NOW)
js.add_case(key_a, f"team:{team_a}", text_sha="abc123", features={"excerpt": "team chat line"}, label="speak",
            weight=1.0, decision_id=None, source="owner", now=NOW)
LM.sync_all()
apub_p, apriv_p = LEARNED / "agents" / "sales.json", LEARNED / "agents" / "sales.private.json"
check("export writes the agent file", apub_p.is_file())
apub = json.loads(apub_p.read_text(encoding="utf-8"))
scopes = sorted((x["scope"], x["status"]) for x in apub["lessons"])
check("agent file: dm and team scopes remapped, revoked kept",
      scopes == [("dm", "active"), ("dm", "revoked"), ("team-name:Launch", "active")], scopes)
check("agent file keeps no agent key or team id",
      key_a not in apub_p.read_text(encoding="utf-8") and team_a not in apub_p.read_text(encoding="utf-8"))
check("agent file: presentation and judge profile",
      apub["presentation"][0]["to_value"] == "short" and apub["judge"]["profile"]["eagerness"] == "high")
check("agent judge cases (chat excerpt) only in the private file",
      apriv_p.is_file() and "team chat line" in apriv_p.read_text(encoding="utf-8")
      and "team chat line" not in apub_p.read_text(encoding="utf-8"))

# ---- 5. two bots with the same slug in one brain: not mirrored ----
twin1, twin2 = make_bot("Twin"), make_bot("Twin")
rps.add_lesson(twin1, "twin lesson", NOW)
LM.sync_all()
check("ambiguous bot slug: no file", not (LEARNED / "bots" / "twin.json").exists())
chatbot_store.delete_bot(twin2)
chatbot_store.delete_bot(twin1)
pub_before_restore = pub_p.read_bytes()

# ---- 6. a fresh machine: new STATE_DIR, same brain folder ----
STATE_B = tempfile.mkdtemp(prefix="javis-lm-b-")
use_state(STATE_B)
LM.sync_all()
check("fresh machine, nothing local yet: no store created", stores_in(STATE_B) == [], stores_in(STATE_B))
check("fresh machine: mirror files left alone", pub_p.read_bytes() == pub_before_restore and priv_p.is_file())
ts_b = team_store.TeamStore(Path(STATE_B) / "team.sqlite3")
team_b = ts_b.create_team(ROOT_B, "Launch", "", "sess-b")["team_id"]
bot_b = make_bot()                                    # imports at creation
check("new bot has a different id", bot_b != bot_a)
check("import: lessons", [x["text"] for x in rps.list_lessons(bot_b)] == [
    "Stay quiet when two customers talk to each other"])
check("import: tuning", rps.get_tuning(bot_b) == {"threshold": "0.6"})
offs = rps.list_offsets(bot_b)
check("import: threshold offset with its age", len(offs) == 1 and offs[0]["chat_id"] == "group-1"
      and offs[0]["offset"] == 0.25 and offs[0]["updated_ts"] == NOW, offs)
check("import: role profile", (rps.get_role_profile(bot_b) or {}).get("agent_hash") == "hash1")
check("import: bootstrap and private cases",
      rps.count_cases(bot_b, "bootstrap") == 1 and rps.count_cases(bot_b, "auto") == 1
      and rps.count_cases(bot_b, "owner") == 1)
rs_b = resonance_store.GoalStore(Path(STATE_B) / "resonance.sqlite3")
key_b = rs_b.agent_register(resonance_store.Principal("owner", "owner", ROOT_B), "sales")["agent_key"]
check("new agent key", key_b != key_a)
rows = AL.lessons(rs_b, key_b, status=None)
got = sorted((r["scope"], r["status"], r["text"]) for r in rows)
check("import: agent lessons remapped to the new key and team",
      got == [(f"dm:{key_b}", "active", "Answer in short bullets"), (f"dm:{key_b}", "revoked", "Use a formal tone"),
              (f"team:{team_b}", "active", "Wait for the leader in Launch")], got)
blocked = AL.add(rs_b, agent_key=key_b, scope=f"dm:{key_b}", kind="method", text="Use a formal tone", source="self")
check("import: a revoked lesson still blocks re-learning", AL.get(rs_b, blocked)["status"] == "revoked")
check("import: presentation lesson", rs_b.presentation(ROOT_B, key_b) == {"length": "short"})
js_b = agent_judge_store.JudgeStore(Path(STATE_B) / agent_judge_store.STORE_NAME)
check("import: agent judge profile", js_b.profile(key_b)["eagerness"] == "high"
      and js_b.profile(key_b)["role_text"] == "Sales helper")
check("import: agent judge offset", abs(js_b.offsets(key_b, now=NOW).get(f"dm:{key_b}", 0) - 0.1) < 1e-9)
check("import: agent judge case in the remapped team", len(js_b.cases(key_b, f"team:{team_b}")) == 1)

# ---- 7. import runs once ----
with sqlite3.connect(str(rps.db_path())) as con:
    con.execute("DELETE FROM lessons WHERE bot_id=?", (bot_b,))
rep = LM.sync_all()
check("import runs once: an emptied store is not refilled from the same file",
      not rep.get("imported") and rps.list_lessons(bot_b) == [], rep)
state = json.loads((Path(STATE_B) / LM.STATE_NAME).read_text(encoding="utf-8"))
check("import recorded in STATE_DIR", any(v.get("imported") for v in state["files"].values()))

# ---- 8. forget and delete reach the mirror ----
rps.forget(bot_b)
LM.sync_bot(bot_b, force=True)
check("forget: private file removed", not priv_p.exists())
pub = json.loads(pub_p.read_text(encoding="utf-8"))
check("forget: bot file keeps only what forget keeps", pub["lessons"] == [] and pub["tuning"] == {}
      and [c["source"] for c in pub["cases"]] == ["bootstrap"])
chatbot_store.delete_bot(bot_b)
check("delete bot: bot files removed", not pub_p.exists() and not priv_p.exists())
AL.revoke(rs_b, [r for r in rows if r["text"] == "Answer in short bullets"][0]["id"], by="owner")
LM.sync_all()
apub = json.loads(apub_p.read_text(encoding="utf-8"))
check("agent revoke shows in the next export",
      {x["text"]: x["status"] for x in apub["lessons"]}.get("Answer in short bullets") == "revoked")

# ---- 9. backup and .gitignore keep private files out ----
check("backup skips Javis/learned/bots/x.private.json",
      git_brain._backup_skip("Shop/Javis/learned/bots/x.private.json") is True)
check("backup skips Javis/learned/agents/x.private.json",
      git_brain._backup_skip("Shop/Javis/learned/agents/x.private.json") is True)
check("backup keeps Javis/learned/bots/x.json", git_brain._backup_skip("Shop/Javis/learned/bots/x.json") is False)
check("backup keeps a .private.json outside Javis/learned", git_brain._backup_skip("Shop/notes/a.private.json") is False)
check("managed .gitignore names the private learned files", "Javis/learned/**/*.private.json" in git_brain._GITIGNORE)
if shutil.which("git"):
    repo = Path(tempfile.mkdtemp(prefix="javis-lm-git-"))
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    git_brain._ensure_gitignore_lines(str(repo))

    def ignored(rel):
        return subprocess.run(["git", "-C", str(repo), "check-ignore", "-q", rel]).returncode == 0

    check("git ignores Javis/learned/bots/x.private.json", ignored("Javis/learned/bots/x.private.json"))
    check("git keeps Javis/learned/bots/x.json", not ignored("Javis/learned/bots/x.json"))

if _fails:
    print(f"\n{len(_fails)} FAIL")
    sys.exit(1)
print("\nall ok")
