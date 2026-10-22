"""Chatbot and channel-account filters match every spelling of one brain (issue #716).

    python tests/run.py brain_filter_spellings      (no network)

A bot saved with brain "/brains/Brain Default" vanished from the Chatbot page, because the
dashboard asks with the short alias "brain" and the filter compared the strings directly.
These checks pin the fix: "brain", "path:<dir>", the absolute path and a trailing slash all
name the same brain, while an unknown or other brain is never folded into Brain Default.
"""
from _paths import ROOT, SERVER  # noqa: F401
import os
import tempfile
from pathlib import Path

_STATE = tempfile.mkdtemp(prefix="javis-brain-filter-")
os.environ["JAVIS_STATE_DIR"] = _STATE
os.environ["BRAINS_DIR"] = str(Path(_STATE) / "brains")
os.environ["JAVIS_SESSIONS_DB"] = str(Path(_STATE) / "sessions.db")

import main  # noqa: E402
import brain_ident  # noqa: E402
import channel_accounts  # noqa: E402
import chatbot_store  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

_fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)


DEFAULT = str(main._default_brain_dir())
OTHER = Path(_STATE) / "brains" / "Shop"
OTHER.mkdir(parents=True, exist_ok=True)
GONE = str(Path(_STATE) / "brains" / "Deleted")

# 1. The helper itself.
check("alias and absolute path are the same brain", brain_ident.same_brain("brain", DEFAULT))
check("path: prefix is understood", brain_ident.same_brain(f"path:{DEFAULT}", "brain"))
check("trailing slash is the same brain", brain_ident.same_brain(DEFAULT + "/", "brain"))
check("another brain is not the default", not brain_ident.same_brain(str(OTHER), "brain"))
check("a missing path is not folded into the default", not brain_ident.same_brain(GONE, "brain"))
check("empty never matches", not brain_ident.same_brain("", "brain") and not brain_ident.same_brain("", ""))
check("main uses the same default brain", brain_ident.default_dir() == main._default_brain_dir())

# 2. Channel accounts filtered by brain.
a_abs, _ = channel_accounts.create_account({"channel": "telegram", "token": "1:a", "external_id": "abs_bot",
                                            "brain": DEFAULT})
a_alias, _ = channel_accounts.create_account({"channel": "telegram", "token": "2:b", "external_id": "alias_bot",
                                              "brain": "brain"})
a_other, _ = channel_accounts.create_account({"channel": "telegram", "token": "3:c", "external_id": "other_bot",
                                              "brain": str(OTHER)})
a_free, _ = channel_accounts.create_account({"channel": "telegram", "token": "4:d", "external_id": "free_bot"})
ids = {a["id"] for a in channel_accounts.list_accounts(brain="brain")}
check("account saved with the absolute path shows under 'brain'", a_abs in ids)
check("account saved with the alias shows under 'brain'", a_alias in ids)
check("unassigned account still shows everywhere", a_free in ids)
check("another brain's account stays hidden", a_other not in ids)
ids = {a["id"] for a in channel_accounts.list_accounts(brain=str(OTHER))}
check("other brain sees its own account, not the default's", a_other in ids and a_abs not in ids and a_alias not in ids)

# 3. GET /chatbots?brain=... through the real endpoint.
bot_id, err = chatbot_store.create_bot({"name": "Shop bot", "agent_slug": "cskh", "brain": DEFAULT,
                                        "account_ids": [a_abs]})
check("bot created with an absolute brain path", bool(bot_id) and not err)
other_bot, err = chatbot_store.create_bot({"name": "Other bot", "agent_slug": "cskh", "brain": str(OTHER),
                                           "account_ids": [a_other]})
check("bot created in another brain", bool(other_bot) and not err)

app = FastAPI()
app.get("/chatbots")(main.chatbots_list)
client = TestClient(app)


def bots(brain):
    r = client.get("/chatbots", params={"brain": brain})
    return {b["id"] for b in r.json().get("bots", [])} if r.status_code == 200 else None


got = bots("brain")
check("/chatbots?brain=brain returns the bot saved with the absolute path", got is not None and bot_id in got)
check("/chatbots?brain=brain hides the other brain's bot", got is not None and other_bot not in got)
got = bots(DEFAULT)
check("/chatbots with the absolute path returns the same bot", got is not None and bot_id in got)
got = bots(str(OTHER))
check("/chatbots for the other brain returns only its bot", got == {other_bot})
got = bots(GONE)
check("/chatbots for a missing brain returns nothing", got == set())
got = bots("")
check("/chatbots with no filter returns every bot", got is not None and {bot_id, other_bot} <= got)

# 4. The agent-delete guard sees bots whichever way the agent's brain was written.
# Both bots point at agent "cskh" of the default brain (stored as the alias "brain").
check("bots_using_agent matches the alias against an absolute path",
      {b["id"] for b in chatbot_store.bots_using_agent(DEFAULT, "cskh")} == {bot_id, other_bot})
check("bots_using_agent does not match another brain",
      chatbot_store.bots_using_agent(str(OTHER), "cskh") == [])

if _fails:
    print(f"\n{len(_fails)} FAIL")
    raise SystemExit(1)
print("\nAll passed")
