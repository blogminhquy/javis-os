"""A chatbot below Full access cannot leave AI-run work for later (security, 2026-11-10).

    python tests/run.py chatbot_queue_guard

What was wrong: a dedicated bot at the "can write" level sees javis_schedule, javis_task and javis_job. The 2026-11-05
fix capped the LEVEL of the work they queue, but that work then ran as one of the owner's background jobs: outside the
bot's brain, with the tools a bot never gets. A customer's message was enough to leave the bot's sandbox.

Pinned here: on a chatbot turn below Full access the three tools only list, and javis_schedule only creates a reminder
that says its text (`notify_only`). The owner's turns and a bot at Full access are unchanged.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import os
import sys
import tempfile

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-botq-")

import plugins_host  # noqa: E402
import turn_context  # noqa: E402

_fails = []


def check(name, cond, extra=None):
    print(("ok   " if cond else "FAIL ") + name + ("" if cond or extra is None else f"  [{extra}]"))
    if not cond:
        _fails.append(name)


cap = plugins_host._cap_job_level


def as_bot(fn):
    turn = turn_context.make("telegram", sender_id="u1", chat_id="c1", la_chu=False)
    turn["bot_id"] = "bot_abc"
    tok = turn_context.bind(turn)
    try:
        return fn()
    finally:
        turn_context.reset(tok)


def as_owner(fn):
    tok = turn_context.bind(turn_context.make("dashboard", la_chu=True, session_id="s1"))
    try:
        return fn()
    finally:
        turn_context.reset(tok)


CREATE = {"op": "create", "name": "n", "prompt": "write plugins/x/plugin.py", "schedule": "1 phút nữa"}

for level in ("auto", "suggest"):
    _a, why = as_bot(lambda: cap("javis_schedule", dict(CREATE), level))
    check(f"bot at {level}: an AI-run scheduled job is refused", why.startswith("ERROR"), why)
    _a, why = as_bot(lambda: cap("javis_schedule", {**CREATE, "muc_quyen": "suggest"}, level))
    check(f"bot at {level}: asking for a lighter level does not help", why.startswith("ERROR"), why)
    _a, why = as_bot(lambda: cap("javis_schedule", {"name": "n", "prompt": "p", "schedule": "mỗi 5 phút"}, level))
    check(f"bot at {level}: op defaults to create, a loop is refused", why.startswith("ERROR"), why)
    a, why = as_bot(lambda: cap("javis_schedule", {**CREATE, "notify_only": True}, level))
    check(f"bot at {level}: a reminder that only says its text is allowed", not why, why)
    _a, why = as_bot(lambda: cap("javis_schedule", {**CREATE, "notify_only": "false"}, level))
    check(f"bot at {level}: notify_only as the string 'false' is not a yes", why.startswith("ERROR"), why)
    for op in ("update", "cancel"):
        _a, why = as_bot(lambda: cap("javis_schedule", {"op": op, "id": "r1"}, level))
        check(f"bot at {level}: javis_schedule {op} is refused", why.startswith("ERROR"), why)
    _a, why = as_bot(lambda: cap("javis_schedule", {"op": "list"}, level))
    check(f"bot at {level}: javis_schedule list still works", not why, why)
    for op in ("add", "answer", "accept", "fix"):
        _a, why = as_bot(lambda: cap("javis_task", {"op": op, "title": "t", "id": "k1"}, level))
        check(f"bot at {level}: javis_task {op} is refused", why.startswith("ERROR"), why)
    _a, why = as_bot(lambda: cap("javis_task", {"op": "list"}, level))
    check(f"bot at {level}: javis_task list still works", not why, why)
    for op in ("then", "cancel"):
        _a, why = as_bot(lambda: cap("javis_job", {"op": op, "then": "do x"}, level))
        check(f"bot at {level}: javis_job {op} is refused", why.startswith("ERROR"), why)
    a, why = as_bot(lambda: cap("javis_web_search", {"q": "x"}, level))
    check(f"bot at {level}: other tools are untouched", a == {"q": "x"} and not why, (a, why))

a, why = as_bot(lambda: cap("javis_schedule", dict(CREATE), "full"))
check("bot at Full access: queueing is unchanged", not why and "muc_quyen" not in a, (a, why))
a, why = as_bot(lambda: cap("javis_schedule", dict(CREATE), "gated"))
check("a gated Team step keeps its own approval path", not why, why)

a, why = as_owner(lambda: cap("javis_schedule", dict(CREATE), "auto"))
check("owner turn at auto: still allowed, level capped at auto", not why and a.get("muc_quyen") == "auto", (a, why))
a, why = as_owner(lambda: cap("javis_task", {"op": "add", "title": "t"}, "auto"))
check("owner turn at auto: javis_task add still allowed", not why and a.get("mode") == "auto", (a, why))
a, why = cap("javis_schedule", dict(CREATE), "auto")
check("no turn bound (background loop): old rule only", not why and a.get("muc_quyen") == "auto", (a, why))

if _fails:
    print(f"\nFAIL - {len(_fails)}: " + ", ".join(_fails))
    sys.exit(1)
print("\nOK - test_chatbot_queue_guard")
