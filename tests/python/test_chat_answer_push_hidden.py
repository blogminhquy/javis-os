"""A chat answer kept out of the bell still rings the phone (owner, 2026-11-21: "đang bị mất thông báo đẩy").

    python tests/python/test_chat_answer_push_hidden.py

0.602.0 keeps a notice out of the bell when its content sits in a chat with its own red dot. The push went with it, so
a long answer, a background job's follow-up and a Gate task stopped ringing a phone in a pocket, where no red dot can be
seen. With "notify every answer" on, a short answer rang and a long one did not.

- a chat turn's answer (push_if_away) pushes when the notice would have rung, or when "notify every answer" is on;
- it still leaves nothing in the bell, names its chat (the device showing that chat stays quiet) and opens it on a tap;
- the default (only urgent notices ring, switch off) is unchanged: no push;
- a job result reported into a chat (no push_if_away) and a muted partner stay as 0.602.0 left them: no push.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import os
import tempfile

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-chat-answer-push-")

import inbox  # noqa: E402
import main  # noqa: E402
import notify_policy  # noqa: E402
import webpush  # noqa: E402

fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(extra)[:300] + "]") if extra and not cond else ""))
    if not cond:
        fails.append(name)


pushes = []


async def fake_push(*a, **k):
    pushes.append((a, k))
    return 1, 0, []


main.webpush.gui_het = fake_push
webpush.so_sub = lambda: 1
main.cfgmod.gate_active = lambda: False
store = main.get_store()
FOLLOWUP = main.turn_done_notice.FOLLOWUP_HEAD


def set_push(**kv):
    st = main.cfgmod.read_settings()
    p = dict(st.get("push") or {})
    for k, v in kv.items():
        if v is None:
            p.pop(k, None)
        else:
            p[k] = v
    st["push"] = p
    main.cfgmod.write_settings(st)


async def run():
    sid = store.create_session("Chat", channel="web")
    sid = sid["id"] if isinstance(sid, dict) else sid
    store.rename(sid, "Video render")

    async def turn(tag, question, answer, seconds, fresh=True):
        if fresh:
            main.push_policy.reset()   # one buzz per chat per 10 minutes (2026-11-23): each scenario starts clean
        pushes.clear()
        await main._bao_luot_dai_xong(sid, "brain", tag, question, answer, seconds)
        await asyncio.sleep(0.05)
        return list(pushes)

    # 1. Default: only urgent notices ring and "notify every answer" is off.
    got = await turn("t1", "render the video", "The video is done.", 400)
    check("default: a long answer does not push", got == [], got)

    # 2. "Notify every answer" on: the long answer and the job follow-up ring, as a short answer already did.
    set_push(turn_done="all")
    bell_before = len(inbox.danh_sach(50))
    got = await turn("t2", "render the video again", "The second video is done.", 400)
    check("every answer: a long answer pushes once", len(got) == 1, got)
    a, k = got[0] if got else ((), {})
    check("the push names its chat and stays quiet where that chat is on screen",
          k.get("quiet_if_visible") is True and k.get("session_id") == sid, k)
    check("a tap opens the chat", len(a) > 2 and a[2] == f"/?mo_phien={sid}", a)
    check("the push carries the answer", len(a) > 1 and "second video" in a[1], a)
    check("nothing is added to the bell", len(inbox.danh_sach(50)) == bell_before)
    got = await turn("t2b", "one more thing", "Done too.", 400, fresh=False)
    check("a second answer in the same chat within 10 minutes stays quiet", got == [], got)
    got = await turn("t3", FOLLOWUP + " ffmpeg", "The audio is added.", 5)
    check("every answer: a background job's follow-up pushes", len(got) == 1, got)
    check("the push is titled with the chat, not 'Javis'", got and got[0][0][0] == "Video render", got)
    got = await turn("t3", FOLLOWUP + " ffmpeg", "The audio is added.", 5)
    check("the same turn does not push twice", got == [], got)
    notify_policy.set_mode("answer", "off")
    got = await turn("t3b", "render once more", "Another video is done.", 400)
    check("chat answers turned off in the filter: no push", got == [], got)
    notify_policy.set_mode("answer", "all")

    set_push(preview="hidden")
    got = await turn("t4", "render a third", "A secret result.", 400)
    check("hidden preview: the push does not carry the text",
          len(got) == 1 and "secret" not in got[0][0][1], got)
    set_push(preview=None, turn_done=None)

    # 3. Switch off, but the owner lets job results ring: a long answer pushes, as before 0.602.0.
    for g in notify_policy.GROUPS:
        notify_policy.set_mode(g, "important")
    got = await turn("t5", "render a fourth", "The fourth video is done.", 400)
    check("job results ring: a long answer pushes", len(got) == 1, got)

    # 4. Unchanged: a job result reported into a chat has its red dot, no push.
    pushes.clear()
    await main._notify_owner(main.WEB_CHAT_PREFIX + sid, "Job 'Price list' is done.")
    await asyncio.sleep(0.05)
    check("a job result reported into a chat still does not push", pushes == [], pushes)
    pushes.clear()
    await main._notify_owner(main.WEB_CHAT_PREFIX + sid, "Job 'Budget ramp' is blocked.", level="urgent")
    await asyncio.sleep(0.05)
    check("an urgent notice still pushes", len(pushes) == 1, pushes)

    # 5. A muted partner stays quiet.
    agent_sid = store.create_session("Partner", channel="agent:writer")
    agent_sid = agent_sid["id"] if isinstance(agent_sid, dict) else agent_sid
    real = main._partner_muted
    main._partner_muted = lambda row: True
    try:
        pushes.clear()
        await main._bo_vao_hom_thu(main.WEB_CHAT_PREFIX + agent_sid, "The draft is done.", kind="answer",
                                   source="job", push_if_away=True)
        await asyncio.sleep(0.05)
        check("a muted partner's answer does not push", pushes == [], pushes)
    finally:
        main._partner_muted = real


asyncio.run(run())

if fails:
    print(f"\nFAIL - test_chat_answer_push_hidden: {len(fails)}: {', '.join(fails)}")
    raise SystemExit(1)
print("\nOK - test_chat_answer_push_hidden: all pass")
