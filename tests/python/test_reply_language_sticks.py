"""A reply language the owner asked for STAYS, and Vietnamese around an English chat does not pull it back.

    python tests/run.py reply_language_sticks      (no network)

Field report 2026-11-15 (community member, Claude Code engine, Sonnet): "I set from the start that it must
answer me in English, and since yesterday I had to remind it more than ten times." Screenshot: an English
chat, Javis answers in Vietnamese with mình/bạn, she writes "Shit. English pls!".

Causes found, each pinned here:
1. "English pls" matched no command at all, and a recognised command only held for its own turn.
2. Claude Code and the Codex app-server keep the system prompt of a thread's FIRST turn, so a language asked
   for later (or set in Settings while the chat was open) never reached a resumed thread.
3. The language block was Vietnamese and said "follow the last message", with nothing about a language the
   owner had STATED in the profile or memory; ~10,000 characters of Vietnamese channel rules came after it.
4. The dashboard's Vietnamese context blocks ([FILE ĐANG MỞ ...], [NGỮ CẢNH GIAO DIỆN: ...]) made the detector
   call an English message Vietnamese.
5. The token-saving capsule of API engines never got a language set in Settings, and the fast path named the
   interface language for a message too short to detect.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import os
import sys
import tempfile
from pathlib import Path

SCRATCH = Path(tempfile.mkdtemp(prefix="javis-reply-lang-"))
for key, relative in {"JAVIS_STATE_DIR": "state", "BRAINS_DIR": "brains", "OBSIDIAN_VAULT_PATH": "vault",
                      "BRAIN_PATH": "brain", "SOURCES_PATH": "sources", "JAVIS_SESSIONS_DB": "sessions.sqlite3"}.items():
    os.environ[key] = str(SCRATCH / relative)

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import channel_context  # noqa: E402
import context_compiler  # noqa: E402
import lang  # noqa: E402
import main  # noqa: E402
import sessions  # noqa: E402

fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (f"  [{extra}]" if (extra and not cond) else ""))
    if not cond:
        fails.append(name)


# ---- 1. which messages pin the conversation ----
PINS_EN = ("English pls!", "Shit. English pls!", "English please", "Eng pls", "English only", "tiếng Anh nhé",
           "tiếng Anh đi em", "answer me in English", "from now on reply in English", "always answer me in English",
           "speak English with me", "em trả lời bằng tiếng Anh được không")
for text in PINS_EN:
    check(f"pins English: {text}", lang.conversation_pin_update(text) == "en", lang.conversation_pin_update(text))
for text in ("nói tiếng Việt đi", "tiếng Việt nha", "Vietnamese please"):
    check(f"pins Vietnamese: {text}", lang.conversation_pin_update(text, "en") == "vi")

# A job about CONTENT steers one turn at most; pinning the whole chat on it would be wrong.
for text in ("reply to this email in English", "trả lời khách này bằng tiếng Anh", "viết 10 hook bằng tiếng Anh",
             "Write 10 hooks in English please", "dịch bài này sang tiếng Anh nhé", "English", "tiếng Anh",
             "in English", "File hợp đồng bằng tiếng Anh nằm ở đâu trong brain", "anh dùng app học tiếng Anh nào tốt",
             "ok do both", "Tôi muốn đặt tên shop là Eng Coffee"):
    check(f"does not pin: {text}", lang.conversation_pin_update(text, "") is None, lang.conversation_pin_update(text))
check("a translate request never pins, even short", lang.conversation_pin_update("dịch sang tiếng Anh đi") is None)

# Complaints: about the pinned language they clear it; about another language they keep it.
check("complaint about the pinned language clears it",
      lang.conversation_pin_update("sao em lại trả lời bằng tiếng Anh vậy?", "en") == "")
check("complaint in English clears it too", lang.conversation_pin_update("why did you reply in English?", "en") == "")
check("complaint about ANOTHER language keeps the pin",
      lang.conversation_pin_update("why are you answering in Vietnamese?", "en") is None)
check("complaint plus a new choice pins the choice",
      lang.conversation_pin_update(
          "Ý là em trả lời anh bằng tiếng Việt chứ sao em lại trả lời bằng tiếng Anh vậy?", "en") == "vi")

# The short form is a command for its own turn too (before: nothing matched "English pls").
check("'English pls' is a command for this turn", lang.resolve(turn_text="Shit. English pls!").source == "turn")

# ---- 2. where the conversation pin ranks ----
d = lang.resolve(turn_text="anh muốn xem doanh thu tháng này", conversation_pin="en", reply_pref="vi")
check("conversation pin beats Settings", d.lang == "en" and d.source == "conversation" and not d.theo_nguoi_dung)
check("a direct command this turn beats the conversation pin",
      lang.resolve(turn_text="nói tiếng Việt đi", conversation_pin="en").lang == "vi")
check("a bot's own language beats the conversation pin",
      lang.resolve(turn_text="hello there my friend", chatbot_pin="vi", conversation_pin="en").lang == "vi")
check("no pin anywhere still lets the model follow",
      lang.resolve(turn_text="please show me the cost breakdown").theo_nguoi_dung)

# ---- 3. the block the model reads ----
auto = lang.khoi_ngon_ngu(lang.resolve(turn_text="show me the revenue by channel"))
pinned = lang.khoi_ngon_ngu(d)
check("block keeps its header (CLAUDE.md and the token meter name it)", "# === NGÔN NGỮ ===" in auto and "# === NGÔN NGỮ ===" in pinned)
check("follow-the-user block says a STATED language wins", "has STATED wins over that rule" in auto, auto)
check("it names the profile, memory and the conversation", all(w in auto for w in ("profile", "memory", "earlier in this conversation")))
check("it says the Vietnamese around it is no hint", "NEVER a hint about the reply language" in auto)
check("pinned block names the language and why", "Reply language: English (en), asked for earlier in this conversation." in pinned)
check("pinned block quotes what the user writes and keeps the pin", "The user is writing in: vi" in pinned)
check("pinned block ends with the nudge in the target language", pinned.rstrip().endswith("Answer in English."))
for name, text in (("auto", auto), ("pinned", pinned)):
    check(f"{name} block has no em or en dash", "\u2014" not in text and "\u2013" not in text)

# ---- 4. the per-turn line (frozen system prompt of a resumed thread) ----
check("no line when nobody pinned", lang.turn_line(lang.resolve(turn_text="show me the revenue by channel")) == "")
check("no line for background work naming the interface language", lang.turn_line(lang.resolve(turn_text="", ui_lang="en")) == "")
check("pinned conversation gives the nudge line", lang.turn_line(d) == "[Answer in English.]")
check("Settings pin gives the nudge line", lang.turn_line(lang.resolve(turn_text="cho anh xem", reply_pref="en")) == "[Answer in English.]")

h = main._turn_facts_header("brain", "sess-1", "en", first=False, lang_line="[Answer in English.]")
check("Claude Code header ends with the language line, right above the person's words",
      h.splitlines()[-1] == "[Answer in English.]", h)
check("header without a pin has no language line", "[Answer in" not in main._turn_facts_header("brain", "sess-1", "en", first=False))


class _Cli:
    def __init__(self, sid):
        self.session_id = sid


r = main._gio_luot_noi_mach(_Cli("abc"), "ok do 2", "en", lang_line="[Answer in English.]")
check("resumed Claude Code turn carries the line between clock and message",
      r.splitlines()[1] == "[Answer in English.]" and r.endswith("\nok do 2"), r)

# The usage line of a first turn no longer drops Vietnamese into an English message.
main.usage_store.summary = lambda *a, **k: {"today": {"total": {"in": 1000, "out": 50, "turns": 3}}}
check("usage line in English for an English turn", "Usage today" in main._turn_facts_header("brain", "", "en", first=True))
check("usage line stays Vietnamese for a Vietnamese turn", "Mức dùng hôm nay" in main._turn_facts_header("brain", "", "vi", first=True))

# ---- 5. Javis's own context blocks do not decide the language ----
for block in ("[FILE ĐANG MỞ trong trình sửa của Javis: notes/x.md]\n\n",
              "[NGỮ CẢNH GIAO DIỆN: trang=tasks]\n\n",
              "[File đính kèm để ĐỌC (đường dẫn):\n- /tmp/a.png\n]\n\n"):
    msg = block + "Can you summarize these tasks for me?"
    check(f"raw message with {block[:18]!r} used to read as Vietnamese", lang.detect(msg)[0] == "vi")
    check(f"the person's own words read as English: {block[:18]!r}",
          lang.detect(main._lang_turn_text(msg))[0] == "en", main._lang_turn_text(msg))
check("a message that is only a block keeps its text", main._lang_turn_text("[NGỮ CẢNH GIAO DIỆN: trang=x]") != "")

# ---- 6. the pin is stored on the conversation and survives the next turns ----
store = sessions.SessionStore(SCRATCH / "pin.sqlite3")
sid = store.create_session(brain="brain")
row = store.get_session(sid)
check("a new conversation has no pin", not (row.get("reply_lang") or ""))
now = main._update_conversation_lang(store, sid, row, "Shit. English pls!")
check("'English pls' pins and returns English", now == "en" and store.get_session(sid)["reply_lang"] == "en")
row = store.get_session(sid)
now = main._update_conversation_lang(store, sid, row, "ok viết tiếp 10 hook nữa đi")
d2 = lang.resolve(turn_text="ok viết tiếp 10 hook nữa đi", conversation_pin=now)
check("next turn typed in Vietnamese still answers English", d2.lang == "en" and lang.turn_line(d2) == "[Answer in English.]")
now = main._update_conversation_lang(store, sid, store.get_session(sid), "sao em lại trả lời bằng tiếng Anh vậy?")
check("a complaint clears the stored pin", now == "" and not store.get_session(sid)["reply_lang"])
check("set_reply_lang on a missing conversation is a no-op", store.set_reply_lang("nope", "en") is False)

# ---- 7. capsules and the closing line ----
check("capsule names the pin", lang.resolve(turn_text="cho anh xem", reply_pref="en").capsule_lang == "en")
check("capsule names a detected language", lang.resolve(turn_text="please show me the cost breakdown").capsule_lang == "en")
check("capsule follows when nothing was detected (was: the interface language)",
      lang.resolve(turn_text="ok do 2", ui_lang="vi").capsule_lang == "")
check("capsule follow sentence lets a stated language win",
      "one they asked for earlier" in context_compiler._cau_ngon_ngu(""))
block = channel_context.build_channel_block("dashboard", {"session_id": "s"}, brain_root="/tmp/b", session_in_turn=True)
check("channel block ends with the language line", block.rstrip().endswith(channel_context.LANGUAGE_LAST_WORD))
check("the closing line is the same for every chat (prompt cache)",
      channel_context.LANGUAGE_LAST_WORD in channel_context.build_channel_block("telegram", {"chat_id": 1}))

# ---- 8. the turn handlers use all of it ----
SRC = (Path(SERVER) / "main.py").read_text(encoding="utf-8")
check("dashboard and owner channels resolve with the conversation pin", SRC.count("conversation_pin=_conv_lang,") == 2)
check("both detect on the person's own words", SRC.count("turn_text=_own_words,") == 2)
check("Codex turns carry the language line", "_codex_current = _codex_lang + " in SRC)
check("both Claude Code lanes carry the language line", SRC.count("lang_line=lang_mod.turn_line(_lang_qd)") == 3)
check("both Phase 8 prepares get the pin", SRC.count('lang="" if _lang_qd.theo_nguoi_dung else _lang_qd.lang') == 2)
check("fast paths name the capsule language, not the interface", SRC.count("_lang_qd.capsule_lang") == 3)

print()
if fails:
    print(f"FAIL: {len(fails)} check(s)")
    sys.exit(1)
print("All checks passed.")
