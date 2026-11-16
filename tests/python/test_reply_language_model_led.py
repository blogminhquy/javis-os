"""The MODEL picks the reply language; Javis only stops pushing Vietnamese at it.

    python tests/run.py reply_language_model_led      (no network)

Field report 2026-11-15 (community member, Claude Code engine, Sonnet): "I set from the start that it
must answer me in English, and since yesterday I had to remind it more than ten times." Screenshot: an
English chat, Javis answers in Vietnamese with mình/bạn, she writes "Shit. English pls!".

Owner's decision the same day: "Claude and ChatGPT already follow the user's language, so do not pass
a language variable, let the model handle it." So the server reads no "English pls" command and pins
nothing on its own. What was fixed instead is everything that pushed Vietnamese at the model:

1. The language block was Vietnamese, said "follow the last message" and nothing about a language
   the person had STATED (profile, memory, earlier in the chat). It is English now and says so.
2. ~10,000 characters of Vietnamese channel rules, with mình/bạn examples, came after it. One
   constant English line now closes that block and points back to the language rule (and the same
   day the rules themselves became English: tests/python/test_core_prompt_english.py).
3. The dashboard's Vietnamese context blocks ([FILE ĐANG MỞ ...]) made the detector call an English
   message Vietnamese. Detection reads the person's own words.
4. The fast-path capsule named a GUESS (the interface language for "ok do 2"); it names only a pin.
5. The first-turn usage line in the message was Vietnamese for every reader.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import inspect
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

fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (f"  [{extra}]" if (extra and not cond) else ""))
    if not cond:
        fails.append(name)


SRC = (Path(SERVER) / "main.py").read_text(encoding="utf-8")

# ---- 1. nothing is pinned on the server's own reading ----
for text in ("Shit. English pls!", "English please", "tiếng Anh nhé", "ok do 2",
             "please show me the cost breakdown in detail", "anh muốn xem doanh thu tháng này"):
    d = lang.resolve(turn_text=text)
    check(f"the model follows, nothing pinned: {text}", d.theo_nguoi_dung and d.capsule_lang == "", d)
# Unchanged since 0.35.0: an explicit "answer in English" steers ITS OWN turn (it beats a Settings pin for
# that turn); nothing is stored, the next turn is decided afresh.
d = lang.resolve(turn_text="always answer me in English please", reply_pref="vi")
check("a direct command steers its own turn only, as before", d.source == "turn" and d.lang == "en", d)
check("no conversation pin in the language decision", "conversation_pin" not in inspect.signature(lang.resolve).parameters)
check("no per-chat language store or per-turn language line",
      "conversation_pin" not in SRC and "turn_line" not in SRC and "reply_lang" not in
      (Path(SERVER) / "sessions.py").read_text(encoding="utf-8"))
h = main._turn_facts_header("brain", "sess-1", "en", first=False)
check("the Claude Code header carries no language line", "[Answer in" not in h and "Trả lời bằng" not in h, h)

# ---- 2. the rule the model reads ----
auto = lang.khoi_ngon_ngu(lang.resolve(turn_text="show me the revenue by channel"))
check("block keeps its header (CLAUDE.md and the token meter name it)", "# === NGÔN NGỮ ===" in auto)
check("it follows the latest message", "language of the user's latest message" in auto)
check("a STATED language wins over the last message", "has STATED wins over that rule" in auto, auto)
check("it names the profile, memory and the conversation",
      all(w in auto for w in ("profile", "memory", "earlier in this conversation")))
check("it says the Vietnamese around it is no hint", "NEVER a hint about the reply language" in auto)
check("it asks to save an ALWAYS language as a preference memory", "`preference` memory" in auto)
check("it names no language", "Reply language:" not in auto)
pinned = lang.khoi_ngon_ngu(lang.resolve(turn_text="please answer in English", ui_lang="vi"))
check("a direct command is named, with why", "Reply language: English (en), asked for in this message." in pinned, pinned)
check("...and the person can still switch", "If the user now asks for another language, use that one." in pinned)
check("...ending with the nudge in that language", pinned.rstrip().endswith("Answer in English."))
# 2026-11-16, owner's screenshot: a Vietnamese user's Claude Code turn wrote its notes between tool calls in English.
for name, text in (("auto", auto), ("pinned", pinned)):
    check(f"{name} block has no em or en dash", "—" not in text and "–" not in text)
    check(f"{name} block covers the notes written between tool calls",
          "the notes you write between tool calls" in text and "Code, logs and tool results" in text, text)
check("the closing line of the channel block says the same",
      "your notes between tool calls included" in channel_context.LANGUAGE_LAST_WORD)

# ---- 3. the Vietnamese tail ends with the language rule ----
block = channel_context.build_channel_block("dashboard", {"session_id": "s"}, brain_root="/tmp/b", session_in_turn=True)
check("channel block ends with the language line", block.rstrip().endswith(channel_context.LANGUAGE_LAST_WORD))
check("the closing line is the same for every chat (prompt cache)",
      channel_context.LANGUAGE_LAST_WORD in channel_context.build_channel_block("telegram", {"chat_id": 1}))

# ---- 4. Javis's own context blocks do not decide the detected language ----
for prefix in ("[FILE ĐANG MỞ trong trình sửa của Javis: notes/x.md]\n\n",
               "[NGỮ CẢNH GIAO DIỆN: trang=tasks]\n\n",
               "[File đính kèm để ĐỌC (đường dẫn):\n- /tmp/a.png\n]\n\n"):
    msg = prefix + "Can you summarize these tasks for me?"
    check(f"raw message with {prefix[:18]!r} used to read as Vietnamese", lang.detect(msg)[0] == "vi")
    check(f"the person's own words read as English: {prefix[:18]!r}",
          lang.detect(main._lang_turn_text(msg))[0] == "en", main._lang_turn_text(msg))
check("a message that is only a block keeps its text", main._lang_turn_text("[NGỮ CẢNH GIAO DIỆN: trang=x]") != "")
check("both turn handlers detect on the person's own words", SRC.count("turn_text=_lang_turn_text(") == 2)

# ---- 5. capsules name a pin, never a guess ----
check("capsule: a direct command is named", lang.resolve(turn_text="please answer in English").capsule_lang == "en")
check("capsule: a short message on a Vietnamese interface is not forced into Vietnamese",
      lang.resolve(turn_text="ok do 2", ui_lang="vi").capsule_lang == "")
check("capsule follow sentence", context_compiler._cau_ngon_ngu("") ==
      "Reply in the user's language, or in one they asked for earlier.")
check("fast paths pass the capsule language", SRC.count("_lang_qd.capsule_lang") == 3)
check("both Phase 8 prepares carry a pin only", SRC.count('lang="" if _lang_qd.theo_nguoi_dung else _lang_qd.lang') == 2)

# ---- 6. the first-turn usage line ----
main.usage_store.summary = lambda *a, **k: {"today": {"total": {"in": 1000, "out": 50, "turns": 3}}}
check("usage line in English for an English turn", "Usage today" in main._turn_facts_header("brain", "", "en", first=True))
check("usage line stays Vietnamese for a Vietnamese turn", "Mức dùng hôm nay" in main._turn_facts_header("brain", "", "vi", first=True))

print()
if fails:
    print(f"FAIL: {len(fails)} check(s)")
    sys.exit(1)
print("All checks passed.")
