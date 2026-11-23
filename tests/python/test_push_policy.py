"""What earns a buzz on the phone (owner, 2026-11-23): learning from taps, a daily budget, a digest, a checked "urgent",
one buzz per chat per 10 minutes, and two push lines that say something.

    python tests/run.py push_policy
"""
import asyncio
import os
import tempfile
from datetime import datetime

from _paths import ROOT, SERVER  # noqa: E402,F401

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-pushpol-")

import notice_text as NT  # noqa: E402
import notify_policy as NP  # noqa: E402
import push_policy as PP  # noqa: E402
import turn_done_notice as T  # noqa: E402

fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (f"  [{extra}]" if extra and not cond else ""))
    if not cond:
        fails.append(name)


DAY = 86400
T0 = datetime(2026, 11, 23, 9, 0).timestamp()

# --- C. budget ---
PP.reset()
check("default budget is 8", PP.budget({}) == 8)
check("budget 0 means no limit", PP.budget({"push": {"daily_budget": 0}}) == 0)
check("a broken budget falls back", PP.budget({"push": {"daily_budget": "x"}}) == 8)
for i in range(8):
    PP.record_push("job|x", "bell", now=T0 + i)
check("8 buzzes spend the day", PP.over_budget("important", {}, now=T0 + 10))
check("urgent still rings past the budget", not PP.over_budget("urgent", {}, now=T0 + 10))
check("no limit never blocks", not PP.over_budget("important", {"push": {"daily_budget": 0}}, now=T0 + 10))
check("a new day starts again", not PP.over_budget("important", {}, now=T0 + DAY))

# --- chat answers: one buzz per chat per 10 minutes ---
PP.reset()
PP.record_push(PP.ANSWER_KEY, "answer", sid="s1", now=T0)
check("a second answer within 10 minutes stays quiet", PP.chat_throttled("s1", now=T0 + 300))
check("another chat is not throttled", not PP.chat_throttled("s2", now=T0 + 300))
check("after 10 minutes it may ring again", not PP.chat_throttled("s1", now=T0 + 601))

# --- A. learning ---
PP.reset()
ids = [PP.record_push("job|daily report", "bell", label="Daily report", now=T0 + i * 3600) for i in range(5)]
check("too early to judge", PP.learn(now=T0 + 5 * 3600) == [])
cands = PP.learn(now=T0 + 3 * DAY)
check("5 ignored in a row: mute candidate", [c["key"] for c in cands] == ["job|daily report"], cands)
PP.engage(ids[-1], "open")
check("opening the last one clears it", PP.learn(now=T0 + 3 * DAY) == [])
PP.engage(ids[-1], "close")
check("a swipe never overwrites a tap", PP.learn(now=T0 + 3 * DAY) == [])
PP.mark_learned("job|daily report", now=T0 + 3 * DAY)
check("pushes before a decision do not count again", PP.learn(now=T0 + 3 * DAY) == [])

PP.reset()
for i in range(5):
    PP.record_push("reminder|meeting", "bell", label="Meeting", level="urgent", now=T0 + i)
check("urgent kinds are never learned away", PP.learn(now=T0 + 3 * DAY) == [])

PP.reset()
ids = [PP.record_push("job|sales", "bell", label="Sales", now=T0 + i * 60) for i in range(10)]
PP.engage(ids[0], "open")
for n in ids[1:]:
    PP.engage(n, "close")
c = PP.learn(now=T0 + 3 * DAY)
check("opened 1 of 10: mute candidate", c and c[0]["key"] == "job|sales", c)

PP.reset()
for i in range(6):
    PP.record_push(PP.ANSWER_KEY, "answer", sid="s1", now=T0 + i * 700)
check("answers read on the computer afterwards are neutral",
      PP.learn(now=T0 + 3 * DAY, seen=lambda s: s.get("sid") == "s1") == [])
check("answers nobody read are learned", [x["key"] for x in PP.learn(now=T0 + 3 * DAY)] == [PP.ANSWER_KEY])

# --- stats ---
PP.reset()
a = PP.record_push("job|a", "bell", label="A", now=T0)
PP.record_push("job|a", "bell", label="A", now=T0 + 1)
PP.record_push("job|a", "bell", label="A", now=T0 + 2)
PP.engage(a, "open")
st = PP.stats(now=T0 + 10, settings={})
check("stats count sent and opened", st["sent"] == 3 and st["opened"] == 1 and st["open_rate"] == 0.33, st)
check("stats name the kind opened least", st["least_opened"] and st["least_opened"][0]["label"] == "A", st)
check("stats carry today's budget", st["today"] == 3 and st["budget"] == 8 and st["digest"] is True, st)

# --- D. digest ---
PP.reset()
morning = datetime(2026, 11, 23, 10, 0).timestamp()
noon = datetime(2026, 11, 23, 11, 31).timestamp()
check("no digest before its time", PP.digest_due(now=morning) == "")
PP.queue_digest("i1", "job", "Report A", now=morning)
PP.queue_digest("i2", "job", "Report B", now=morning)
PP.queue_digest("i2", "job", "Report B", now=morning)
PP.queue_digest("i3", "suggest", "Idea", now=morning)
slot = PP.digest_due(now=noon)
check("the 11:30 slot is due", slot == "2026-11-23 11:30", slot)
items = PP.take_digest(slot, now=noon)
check("the digest holds each notice once", len(items) == 3, items)
check("a slot is sent once", PP.digest_due(now=noon + 60) == "")
title, body = PP.digest_text(items)
check("digest title counts", title.startswith("3 "), title)
check("digest body names the groups by count", body.startswith(NP.group_name("job") + " 2"), body)
check("digest can be turned off", not PP.digest_on({"push": {"digest": "off"}}) and PP.digest_on({}))

# --- E. urgent needs a reason ---
PP.reset()
check("urgent with a valid reason stands", PP.act_check("job|x", True, "money"))
check("urgent without a reason is lowered", not PP.act_check("job|y", True, ""))
check("urgent with an unknown reason is lowered", not PP.act_check("job|y", True, "important"))
PP.reset()
for _ in range(6):
    PP.act_check("loop|wolf", True, "error")
check("a job that claims urgent on every run loses it", not PP.act_check("loop|wolf", True, "error"))
PP.reset()
for i in range(7):
    PP.act_check("loop|calm", False)
check("a calm job keeps a rare urgent claim", PP.act_check("loop|calm", True, "customer"))
meta = NT.split_block('Done <!-- JAVIS_NOTIFY: {"title": "Order cancelled", "line": "Call back", "act": true, "why": "Money"} -->')[1]
check("the block carries its reason", meta.get("why") == "money" and meta.get("line") == "Call back", meta)
meta = NT.split_block('Done <!-- JAVIS_NOTIFY: {"title": "x", "line": "", "act": true, "why": "because"} -->')[1]
check("an unknown reason is dropped", meta.get("why") == "", meta)
check("the prompt asks for the reason and the next step", '"why"' in NT.PROMPT and "the one thing the owner should do" in NT.PROMPT)

# --- B. the chat-answer push line ---
got = T.push_line("### Kết quả\nEm kiểm tra lại danh sách khách.\nDưới đây là tóm tắt:\n**3 khách** cần gọi lại hôm nay.\n- ý")
check("the answer's first reporting line", got == "3 khách cần gọi lại hôm nay.", got)
check("a long line is cut", len(T.push_line("x " * 200)) <= T.PUSH_LINE)

# --- the "answer" group in the bell's filter ---
check("answer is a group", "answer" in NP.GROUPS and NP.default_mode("answer") == "all")
d = NP.decide("answer", "important", "chat answer", record=False)
check("answers ring by default", d["verdict"] == "loud", d)
NP.set_rule("answer", NP.signature("chat answer"), "mute", set_by="core", label="Chat answers")
check("a learned mute silences answers", NP.decide("answer", "important", "chat answer", record=False)["verdict"] == "quiet")
check("the answer key matches the policy key", PP.ANSWER_KEY == "answer|" + NP.signature("chat answer"))

# --- wiring ---
main = (SERVER / "main.py").read_text(encoding="utf-8")
sw = (ROOT / "dashboard" / "sw.js").read_text(encoding="utf-8")
noti = (ROOT / "dashboard" / "notifications.js").read_text(encoding="utf-8")
check("sw reports taps and swipes", "/push/engage" in sw and "notificationclose" in sw and "nid" in sw)
check("server takes the reports", '@app.post("/push/engage")' in main and '@app.get("/push/stats")' in main)
check("budget lowers the verdict", 'why="budget"' in main)
check("filtered important notices wait for the digest", "push_policy.queue_digest(" in main)
check("chat answers pass the filter and the throttle", 'notify_policy.decide("answer"' in main and "chat_throttled" in main)
check("the push body is the next step, not the report cut", 'push_body' in main and '(item.get("summary") or item["body"])' not in main)
check("chat answers no longer title themselves Javis", "title, body, f\"/?mo_phien={conv_sid}\"" in main)
check("the bell shows the week and the controls", "/push/stats" in noti and "data-push-budget" in noti and "data-push-digest" in noti)
check("settings keep budget and digest", '["daily_budget"] = ' in main and '["digest"] = "off" if' in main)

if fails:
    print(f"\nFAIL - test_push_policy: {len(fails)}: {', '.join(fails)}")
    raise SystemExit(1)
print("\nOK - test_push_policy: all pass")
