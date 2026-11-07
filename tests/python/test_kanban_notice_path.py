"""Characterize the real Kanban question producer through inbox and mocked delivery.

No production data or network; recovery after a partial delivery remains a diagnostic gap.
Run: python tests/python/test_kanban_notice_path.py
"""
# isort: off
from _paths import ROOT, SERVER  # noqa: F401
import asyncio
import importlib
import os
import tempfile
from pathlib import Path
from unittest.mock import patch
# isort: on

STATE = Path(tempfile.mkdtemp(prefix="notice-path-"))
os.environ["JAVIS_STATE_DIR"] = str(STATE)

import inbox
import main
import notify_policy
from test_kanban_hoi_dap import _feature, _new_task, _run_once

assert STATE in inbox.STORE.parents, "inbox must be isolated"
assert STATE in notify_policy.STORE.parents, "policy must be isolated"

sent, pushes, broadcasts = [], [], []


async def channel(chat, text, **kwargs):
    sent.append((chat, text, kwargs))
    return True, ""


async def push(*args, **kwargs):
    pushes.append((args, kwargs))
    return 1, 0, []


async def publish(event):
    broadcasts.append(event)


async def report(*args, **kwargs):
    result = await main._notify_owner(*args, **kwargs)
    if main._PUSH_TASKS:
        await asyncio.gather(*list(main._PUSH_TASKS))
    return result


def run():
    feature, brain = _feature(STATE, report)
    session = main.get_store().create_session(brain=main._brain_key(str(brain)))
    origin = "web:" + session
    tid = _new_task(feature, brain, chat_id=origin)
    task = _run_once(feature, tid, "[[NEEDS_INPUT]] Which synthetic option: A or B?")
    assert task["status"] == "blocked" and task["block_kind"] == "needs_input"
    notices = inbox.danh_sach(300)
    assert len(notices) == 1
    notice = notices[0]
    assert notice["group"] == "question" and notice["level"] == "urgent"
    assert not notice.get("filtered") and not notice["read"]
    assert notice["session_id"] == session and tid in notice["body"]
    assert len(sent) == len(pushes) == 1 and sent[0][0] == origin
    assert broadcasts[-1] == {"type": "inbox", "session_id": session}
    assert notify_policy.DEFAULT_MODE == "urgent"
    print("PASS real needs_input transition -> urgent inbox, source chat, mocked bell/push")

    # Reload durable inbox state, then replay the same producer report.
    importlib.reload(inbox)
    asyncio.run(feature._report(task))
    assert len(inbox.danh_sach(300)) == len(sent) == len(pushes) == 1
    print("PASS persisted dedup survives inbox reload (not a whole-server restart test)")

    # A distinct unanswered question on the same task must ring again.
    next_task = dict(task)
    next_task["metadata"] = {**task["metadata"], "qa": [
        *task["metadata"]["qa"], {"q": "Which synthetic date?"}]}
    asyncio.run(feature._report(next_task))
    assert len(inbox.danh_sach(300)) == len(sent) == len(pushes) == 2
    assert sent[-1][0] == origin
    print("PASS a new question creates a separate notice, without a different recipient")

    notify_policy.set_rule("question", notify_policy.signature(notice["title"]),
                           "mute", set_by="owner")
    muted_task = dict(next_task)
    muted_task["metadata"] = {"qa": [{"q": "Synthetic muted question?"}]}
    asyncio.run(feature._report(muted_task))
    assert len(pushes) == 2
    assert inbox.danh_sach(300)[0].get("why") == "muted"
    print("PASS explicit owner mute suppresses ringing")

    notify_policy.set_mode("question", "off", set_by="owner")
    off_task = dict(next_task)
    off_task["metadata"] = {"qa": [{"q": "Synthetic owner-off question?"}]}
    asyncio.run(feature._report(off_task))
    assert len(pushes) == 2 and len(inbox.danh_sach(300)) == 3
    print("PASS explicit owner off suppresses ringing")

    done = {**task, "status": "done", "block_kind": "", "result": "Synthetic result"}
    asyncio.run(feature._report(done))
    assert len(pushes) == 2
    assert inbox.danh_sach(300)[0]["read"]
    assert sent[-1][0] == origin
    print("PASS normal completion stays quiet and reaches only its source chat")
    feature.store.close()


# Mock both external channel delivery and push before executing any transition.
with patch.object(main, "_gui_qua_kenh", channel), \
        patch.object(main.webpush, "gui_het", push), \
        patch.object(main._CHAT_RUNTIME, "publish", publish):
    run()
