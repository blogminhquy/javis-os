"""Rewind button under a question in the chat (0.349.0).

    python tests/run.py tua_lai_chat      (no network)

Owner, 27/10/2026: pressing it deletes that question and everything below it, puts the question back in the
composer, and the conversation goes on from there. Pinned here (the server half; the button is in chat-acts.js and
app.js, see tests/js/test_chat_acts.js):
  1. The store deletes from that user message to the end, nothing before it, and fixes msg_count.
  2. The endpoint finds the question by its text counted from the end (`nth` for repeated text), also when the stored
     content carries context blocks or attachment lines; "ok" never matches a later "ok làm đi".
  3. The engines' native threads are dropped (they still hold the deleted turns), a compaction summary that covers
     deleted turns is dropped, one that covers only kept turns stays.
  4. Refused while the chat is answering; an unknown text deletes nothing.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import os
import sys
import tempfile
from pathlib import Path

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-tualai-")
os.environ["JAVIS_ALLOWED_HOSTS"] = "testserver"
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import sessions  # noqa: E402

_fails = []


def check(name, cond, them=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(them) + "]") if them and not cond else ""))
    if not cond:
        _fails.append(name)


def noi_dung(st, sid):
    return [(m["role"], m["content"]) for m in st.get_messages(sid)]


# ---- 1. The store ----
store = sessions.SessionStore(Path(tempfile.mkdtemp(prefix="sess-")) / "s.db")
sid = store.create_session(brain="brain", engine="cli", title="t", channel="web")
ids = [store.append_message(sid, r, c) for r, c in
       (("user", "một"), ("assistant", "đáp một"), ("user", "hai"), ("assistant", "đáp hai"),
        ("user", "ba"), ("assistant", "đáp ba"))]
check("a non-user message is not a rewind point", store.rewind_from(sid, ids[1]) == 0
      and len(store.get_messages(sid)) == 6)
check("another session's message is not a rewind point",
      store.rewind_from(store.create_session(brain="brain"), ids[2]) == 0 and len(store.get_messages(sid)) == 6)
n = store.rewind_from(sid, ids[2])
check("rewinding to 'hai' deletes it and everything after", n == 4, n)
check("...and keeps everything before it", noi_dung(store, sid) == [("user", "một"), ("assistant", "đáp một")],
      noi_dung(store, sid))
check("...msg_count follows", int(store.get_session(sid)["msg_count"]) == 2, store.get_session(sid)["msg_count"])

# ---- 2-4. The endpoint ----
import main  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

cl = TestClient(main.app)
ms = main.get_store()


def phien(tin, **cot):
    s = ms.create_session(brain="brain", engine="cli", title="t", channel="web")
    for r, c in tin:
        ms.append_message(s, r, c)
    if cot.get("cli"):
        ms.set_cli_session_id(s, cot["cli"])
    if cot.get("codex"):
        ms.set_codex_thread_id(s, cot["codex"])
    if cot.get("compact"):
        ms.set_compact(s, "tóm tắt", cot["compact"])
    return s


HOI = [("user", "[FILE ĐANG MỞ trong trình sửa của Javis: notes/a.md]\n\nviết lại đoạn mở bài"),
       ("assistant", "bản một"), ("user", "ok"), ("assistant", "xong"),
       ("user", "viết lại đoạn mở bài"), ("assistant", "bản hai"), ("user", "ok"), ("assistant", "xong hai")]

s1 = phien(HOI, cli="mach-claude", codex="mach-codex", compact=6)
r = cl.post(f"/sessions/{s1}/rewind", data={"text": "ok", "nth": "0"})
check("rewind to the LAST 'ok' answers ok", r.status_code == 200 and r.json().get("ok"), r.text)
check("...deletes that question and its answer only", r.json().get("deleted") == 2
      and [c for _, c in noi_dung(ms, s1)][-1] == "bản hai", noi_dung(ms, s1))
row = ms.get_session(s1)
check("...drops the Claude Code and Codex threads", not row.get("cli_session_id") and not row.get("codex_thread_id"),
      (row.get("cli_session_id"), row.get("codex_thread_id")))
check("...a summary covering only kept turns stays", int(row.get("compact_count") or 0) == 6
      and (row.get("compact_summary") or "") == "tóm tắt", (row.get("compact_count"), row.get("compact_summary")))
check("...the context meter goes back to 0", int(row.get("last_input_tokens") or 0) == 0)

s2 = phien(HOI, compact=6)
r = cl.post(f"/sessions/{s2}/rewind", data={"text": "viết lại đoạn mở bài", "nth": "1"})
check("nth=1 finds the EARLIER copy, inside its context block", r.status_code == 200
      and r.json().get("deleted") == 8 and noi_dung(ms, s2) == [], (r.text, noi_dung(ms, s2)))
row = ms.get_session(s2)
check("...a summary covering deleted turns is dropped", int(row.get("compact_count") or 0) == 0
      and not (row.get("compact_summary") or ""), (row.get("compact_count"), row.get("compact_summary")))

s4 = phien([("user", "ok"), ("assistant", "a"), ("user", "ok làm đi"), ("assistant", "b"),
            ("user", "gửi kèm ảnh\n\n\U0001F4CE uploads/x.png"), ("assistant", "c")])
r = cl.post(f"/sessions/{s4}/rewind", data={"text": "ok"})
check("'ok' never matches a later 'ok làm đi'", r.status_code == 200 and r.json().get("deleted") == 6
      and noi_dung(ms, s4) == [], (r.text, noi_dung(ms, s4)))
s5 = phien([("user", "a"), ("assistant", "b"), ("user", "gửi kèm ảnh\n\n\U0001F4CE uploads/x.png"), ("assistant", "c")])
r = cl.post(f"/sessions/{s5}/rewind", data={"text": "gửi kèm ảnh"})
check("a message sent with attachment lines is found by its typed text", r.status_code == 200
      and r.json().get("deleted") == 2, r.text)

s3 = phien(HOI)
r = cl.post(f"/sessions/{s3}/rewind", data={"text": "câu chưa từng hỏi"})
check("unknown text: 404 and nothing deleted", r.status_code == 404 and r.json().get("ly_do") == "khong_thay"
      and len(ms.get_messages(s3)) == 8, r.text)
r = cl.post(f"/sessions/{s3}/rewind", data={"text": "bản hai"})
check("an answer's text is never a rewind point", r.status_code == 404 and len(ms.get_messages(s3)) == 8, r.text)
r = cl.post("/sessions/khong-co/rewind", data={"text": "ok"})
check("unknown session: 404", r.status_code == 404, r.text)

_goc = main._CHAT_RUNTIME.get_job
main._CHAT_RUNTIME.get_job = lambda s: object() if s == s3 else None
try:
    r = cl.post(f"/sessions/{s3}/rewind", data={"text": "ok"})
finally:
    main._CHAT_RUNTIME.get_job = _goc
check("refused while the chat is answering", r.status_code == 409 and r.json().get("ly_do") == "dang_chay"
      and len(ms.get_messages(s3)) == 8, r.text)

print()
if _fails:
    raise SystemExit(f"FAIL {len(_fails)}: " + "; ".join(_fails[:4]))
print("All green.")
