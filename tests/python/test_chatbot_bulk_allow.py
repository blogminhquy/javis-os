"""The waiting list of a bot card is settled in one request (owner, 13/11/2026).

    python tests/run.py chatbot_bulk_allow      (no network)

A bot with nine waiting groups took nine rounds of "open the popup, press Allow this group, the popup closes". The
popup now ticks rows and sends them together, so `/chatbots/{bot_id}/groups` and `/people` take `chat_ids` (a JSON
list) next to the old single `chat_id`. What this file guards:

  1. PARSING. One id, many ids, both; blanks and repeats dropped; a broken list is an error, not an empty success.
  2. ONE WRITE. The whole batch lands in one `update_bot`, on the right list, keeping what was there.
  3. THE ROUTES. Both go through one shared body that also clears every id from the approval queue.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import os
import sys
import tempfile

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-bulk-allow-")
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import chatbot_store  # noqa: E402

_fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(extra) + "]") if extra and not cond else ""))
    if not cond:
        _fails.append(name)


# ============================================================
# 1. Parsing the form
# ============================================================
parse = chatbot_store.parse_chat_ids
check("one id, the form the old button sent", parse("-1001", "") == (["-1001"], ""))
check("many ids as a JSON list, order kept", parse("", '["-1001", "-1002", "77"]') == (["-1001", "-1002", "77"], ""))
check("blanks and repeats are dropped", parse("", '["-1001", " ", "-1001", " -1002 "]') == (["-1001", "-1002"], ""))
check("both fields together are merged", parse("-1003", '["-1001"]') == (["-1001", "-1003"], ""))
check("numbers in the list are read as ids", parse("", "[5550001, 5550002]") == (["5550001", "5550002"], ""))
ids, err = parse("", "not json")
check("a list that is not JSON is an error", ids == [] and bool(err), (ids, err))
ids, err = parse("", '{"a": 1}')
check("JSON that is not a list is an error", ids == [] and bool(err), (ids, err))
ids, err = parse("", "")
check("no id at all is an error", ids == [] and bool(err), (ids, err))
ids, err = parse("", '[[1], {"x": 2}, ""]')
check("a list with nothing usable is an error, not an empty success", ids == [] and bool(err), (ids, err))

# ============================================================
# 2. One write for the whole batch
# ============================================================
G1, G2, G3, P1, P2 = "5550001", "5550002", "5550003", "5550011", "5550012"
bid, loi = chatbot_store.create_bot({"name": "Bulk", "agent_slug": "bulk", "brain": "b", "groups": G1,
                                     "audience": "chon", "people": P1})
check("bot created", not loi, loi)

writes = []
_real_update = chatbot_store.update_bot


def _counting_update(bot_id, patch):
    writes.append(dict(patch))
    return _real_update(bot_id, patch)


chatbot_store.update_bot = _counting_update
ok, err = chatbot_store.set_listed(bid, "groups", [G2, G3, G1], True)
check("allowing three groups succeeds", ok, err)
check("in ONE write", len(writes) == 1, writes)
check("the groups already allowed stay, the new ones are added once",
      chatbot_store.get_bot(bid)["groups"] == [G1, G2, G3], chatbot_store.get_bot(bid)["groups"])
check("people are untouched by a groups batch", chatbot_store.get_bot(bid)["people"] == [P1])

writes.clear()
ok, err = chatbot_store.set_listed(bid, "people", [P2], True)
check("people go onto the people list", ok and chatbot_store.get_bot(bid)["people"] == [P1, P2], err)

ok, err = chatbot_store.set_listed(bid, "groups", [G1, G3], False)
check("ignoring takes the ids off the list and keeps the rest",
      ok and chatbot_store.get_bot(bid)["groups"] == [G2], chatbot_store.get_bot(bid)["groups"])
ok, err = chatbot_store.set_listed(bid, "groups", ["5559999"], False)
check("ignoring a chat that was never allowed changes nothing", ok and chatbot_store.get_bot(bid)["groups"] == [G2])
chatbot_store.update_bot = _real_update

ok, err = chatbot_store.set_listed(bid, "blocked", [G1], True)
check("only the two allow lists can be written this way", not ok and bool(err))
ok, err = chatbot_store.set_listed("no-such-bot", "groups", [G1], True)
check("an unknown bot is refused", not ok and err == chatbot_store.LOI_KHONG_CO_BOT, err)

# ============================================================
# 3. The routes
# ============================================================
_SRC = (ROOT / "server" / "main.py").read_text(encoding="utf-8")
check("both routes take chat_ids next to chat_id, and neither field is required on its own",
      'async def chatbots_groups(bot_id: str, chat_id: str = Form(""), chat_ids: str = Form(""), on: str = Form("1")):' in _SRC
      and 'async def chatbots_people(bot_id: str, chat_id: str = Form(""), chat_ids: str = Form(""), on: str = Form("1")):' in _SRC)
check("both routes share one body",
      'return _chatbots_set_listed(bot_id, "groups", chat_id, chat_ids, on)' in _SRC
      and 'return _chatbots_set_listed(bot_id, "people", chat_id, chat_ids, on)' in _SRC)
body = _SRC[_SRC.index("def _chatbots_set_listed("):_SRC.index('@app.post("/chatbots/{bot_id}/people")')]
check("the shared body parses the ids, writes once and answers 400 on a bad list",
      "chatbot_store.parse_chat_ids(chat_id, chat_ids)" in body
      and "chatbot_store.set_listed(bot_id, key, ids, bat)" in body and "status_code=400" in body)
check("every id of the batch leaves the approval queue",
      "for cid in ids:\n        chatbot_runtime.bo_nhom_cho(bot_id, cid)" in body)
check("an unknown bot is still a 404", "status_code=404" in body)

if _fails:
    print(f"\nFAIL {len(_fails)}: " + ", ".join(_fails))
    sys.exit(1)
print("\nOK - test_chatbot_bulk_allow: all pass")
