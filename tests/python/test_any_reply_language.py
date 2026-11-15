"""Javis works in ANY language, not only Vietnamese and English.

    python tests/run.py any_reply_language      (no network)

Owner, 2026-11-15: "the interface defaults to English, but switch to any language and Javis must work
and talk in that language, like Claude or ChatGPT." The model already followed whatever language the
person wrote. What stayed locked to vi/en were the places where a language is NAMED:

1. the reply language in Settings and a customer bot's language offered only Vietnamese and English;
2. "reply in Japanese" / "tiếng Nhật nhé" in the chat matched no command;
3. a pinned language other than vi/en fell back to Vietnamese in the prompt (`lang_registry.get`);
4. Kanban tasks, reminders, loops and learning built their prompt with no language, which named
   Vietnamese, so every background report of an English or Japanese owner came in Vietnamese;
5. a reply in Japanese, Korean or Thai was read aloud by the Vietnamese voice the owner picked.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import os
import sys
import tempfile
from pathlib import Path

SCRATCH = Path(tempfile.mkdtemp(prefix="javis-any-lang-"))
for key, relative in {"JAVIS_STATE_DIR": "state", "BRAINS_DIR": "brains", "OBSIDIAN_VAULT_PATH": "vault",
                      "BRAIN_PATH": "brain", "SOURCES_PATH": "sources", "JAVIS_SESSIONS_DB": "sessions.sqlite3"}.items():
    os.environ[key] = str(SCRATCH / relative)

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import chatbot_runtime  # noqa: E402
import chatbot_store  # noqa: E402
import config as cfgmod  # noqa: E402
import context_compiler  # noqa: E402
import lang  # noqa: E402
import lang_registry as R  # noqa: E402
import main  # noqa: E402
import phien_am as P  # noqa: E402

fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (f"  [{extra}]" if (extra and not cond) else ""))
    if not cond:
        fails.append(name)


# ---- 1. the catalog ----
codes = R.reply_codes()
check("at least 30 nameable reply languages", len(codes) >= 30, len(codes))
check("vi and en are reply languages too", "vi" in codes and "en" in codes)
for code in codes:
    info = R.reply_info(code)
    check(f"{code}: has names and a nudge", bool(info.english and info.native and info.nudge))
    check(f"{code}: no em or en dash", "—" not in info.nudge + info.native and "–" not in info.nudge)
    # The full entries (vi, en) carry accented spellings too; matching strips accents first, so only the
    # catalog's own words must already be in matched form.
    for w in (info.request_words if code not in R.LANGS else ()):
        check(f"{code}: request word {w!r} is written the way it is matched (lowercase, no accents)",
              lang._bo_dau(w) == w)
check("Edge locale for the voice list", R.reply_info("ja").edge == "ja-JP" and R.reply_info("vi").edge == "vi-VN")
for raw, want in (("ja-JP", "ja"), ("ZH_hant", "zh-tw"), ("zh-HK", "zh-tw"), ("zh-CN", "zh"), ("pt-BR", "pt"),
                  ("fil", "tl"), ("nb", "no"), ("EN-us", "en"), ("xx", ""), ("", ""), ("auto", "")):
    check(f"reply_code({raw!r}) == {want!r}", R.reply_code(raw) == want, R.reply_code(raw))
choices = R.reply_choices()
check("picker lists vi and en first", [c["ma"] for c in choices[:2]] == ["vi", "en"])
check("picker shows native names", any(c["ten"] == "日本語" for c in choices))
check("an unknown code still falls back to the default language", R.get("xx").code == R.MAC_DINH)
check("a reply-only language reads its clock in English, not Vietnamese", R.get("ja").code == "en")

# ---- 2. asking for a language in the chat ----
PINS = {"tiếng Nhật nhé": "ja", "reply in Japanese": "ja", "Japanese please": "ja", "nói tiếng Hàn đi em": "ko",
        "auf Deutsch bitte": "de", "en español por favor": "es", "en français s'il vous plaît": "fr",
        "French pls": "fr", "traditional chinese pls": "zh-tw", "Chinese please": "zh",
        "trả lời bằng tiếng Pháp": "fr", "tiếng Ý nhé": "it", "polski pls": "pl", "speak Thai with me": "th",
        "tiếng Indonesia nha": "id", "English pls": "en", "nói tiếng Việt đi": "vi"}
for text, want in PINS.items():
    got = lang.conversation_pin_update(text, "")
    check(f"pins {want}: {text}", got == want, got)
for text in ("viết caption bằng tiếng Nhật", "translate this to Japanese please", "dịch sang tiếng Hàn đi",
             "Japanese", "tiếng Nhật", "Polish pls", "reply to this customer in French",
             "khách này nói tiếng Hàn, soạn giúp anh câu trả lời"):
    check(f"does not pin the chat: {text}", lang.conversation_pin_update(text, "") is None,
          lang.conversation_pin_update(text, ""))
check("a complaint about the pinned Japanese clears it",
      lang.conversation_pin_update("why are you replying in Japanese?", "ja") == "")
check("'viết caption bằng tiếng Nhật' still steers its own turn",
      lang.resolve(turn_text="viết caption bằng tiếng Nhật").lang == "ja")

# ---- 3. every pin names the right language ----
for kw in ({"conversation_pin": "ja"}, {"reply_pref": "ja"}, {"chatbot_pin": "ja"}, {"brain_pin": "ja"},
           {"channel_default": "ja"}):
    d = lang.resolve(turn_text="cho anh xem doanh thu tháng này", **kw)
    check(f"{list(kw)[0]}=ja pins Japanese", d.lang == "ja" and not d.theo_nguoi_dung, d)
d = lang.resolve(turn_text="cho anh xem doanh thu tháng này", conversation_pin="ja")
block = lang.khoi_ngon_ngu(d)
check("block names Japanese with its native name", "Reply language: Japanese (日本語, ja)" in block, block)
check("block ends with the nudge in Japanese", block.rstrip().endswith("日本語で答えてください。"))
check("no Vietnamese pin hides behind a Japanese one", "Vietnamese" not in block.split("\n")[3])
check("turn line in Japanese", lang.turn_line(d) == "[日本語で答えてください。]")
check("capsule sentence names Japanese", "Japanese (ja)" in context_compiler._cau_ngon_ngu("ja")
      and "日本語で答えてください。" in context_compiler._cau_ngon_ngu("ja"))
auto = lang.resolve(turn_text="今日の売上はいくらですか")
check("a Japanese message is followed, and named for the capsule",
      auto.theo_nguoi_dung and auto.lang == "ja" and auto.capsule_lang == "ja", auto)
check("a voice call in Japanese pins Japanese", lang.call_language("今日の売上はいくらですか", "ja-JP") == "ja")
check("a call recognised as Korean with no text pins Korean", lang.call_language("", "ko-KR") == "ko")

# ---- 4. Settings, customer bots ----
SRC = (Path(SERVER) / "main.py").read_text(encoding="utf-8")
check("Settings save any nameable reply language",
      'lc["reply_lang"] = "auto" if v in ("", "auto") else (lang_registry.reply_code(v) or "auto")' in SRC)
check("Settings send the reply picker its own list", 'safe["reply_lang_list"] = lang_registry.reply_choices()' in SRC)
check("the bot page gets the same list", '"reply_lang_list": lang_registry.reply_choices()' in SRC)
CONSOLE = (ROOT / "dashboard" / "console.js").read_text(encoding="utf-8")
BOTS = (ROOT / "dashboard" / "chatbots.js").read_text(encoding="utf-8")
check("Settings reply picker reads reply_lang_list", "s.reply_lang_list || s.lang_list" in CONSOLE)
check("the interface picker keeps the interface list", "s.ui_lang_list || s.lang_list" in CONSOLE)
check("bot picker reads reply_lang_list", "d.reply_lang_list || d.lang_list" in BOTS)
check("a bot can be pinned to Japanese", chatbot_store._clean_ngon_ngu("ja-JP") == "ja")
check("an unknown bot language still means auto", chatbot_store._clean_ngon_ngu("xx") == "auto")
bot_prompt = chatbot_runtime.build_bot_prompt({"name": "Shop", "ngon_ngu": "ja"})
check("a Japanese bot is told to answer in Japanese, in Japanese",
      "Japanese (日本語)" in bot_prompt and "日本語で答えてください。" in bot_prompt, bot_prompt[-200:])

# ---- 5. background work ----
check("all four background features use the language-aware prompt",
      SRC.count("build_system_prompt=_background_system_prompt") == 4
      and "build_system_prompt=build_system_prompt" not in SRC)
cfg = cfgmod.read_settings()
cfg.setdefault("locale", {})["reply_lang"] = "auto"
cfgmod.write_settings(cfg)
bg = main._background_lang_decision()
check("no pin: background work follows the task's own language", bg.theo_nguoi_dung, bg)
check("...and the prompt says so instead of pinning Vietnamese",
      "language of the user's latest message" in main._background_system_prompt("brain")
      and "Reply language: Vietnamese" not in main._background_system_prompt("brain"))
cfg["locale"]["reply_lang"] = "ja"
cfgmod.write_settings(cfg)
bg = main._background_lang_decision()
check("Settings pinned to Japanese: background work answers in Japanese",
      bg.lang == "ja" and not bg.theo_nguoi_dung and "Reply language: Japanese" in main._background_system_prompt("brain"))
cfg["locale"]["reply_lang"] = "auto"
cfgmod.write_settings(cfg)

# ---- 6. the voice can read it ----
HOAIMY, NAMMINH, EMMA = "vi-VN-HoaiMyNeural", "vi-VN-NamMinhNeural", "en-US-EmmaMultilingualNeural"
check("Japanese with a Vietnamese voice: Nanami", P.speech_plan("今日は晴れです。", HOAIMY)[1] == "ja-JP-NanamiNeural")
check("...with a male Vietnamese voice: Keita", P.speech_plan("今日は晴れです。", NAMMINH)[1] == "ja-JP-KeitaNeural")
check("Korean: SunHi", P.speech_plan("안녕하세요 반갑습니다", HOAIMY)[1] == "ko-KR-SunHiNeural")
check("Thai: Premwadee", P.speech_plan("สวัสดีครับ ยินดีต้อนรับ", HOAIMY)[1] == "th-TH-PremwadeeNeural")
check("Chinese: Xiaoxiao", P.speech_plan("你好，今天天气很好", HOAIMY)[1] == "zh-CN-XiaoxiaoNeural")
check("Russian: Svetlana", P.speech_plan("Привет, как дела у тебя", HOAIMY)[1] == "ru-RU-SvetlanaNeural")
check("French with a Vietnamese voice: the multilingual voice",
      P.speech_plan("Ça va très bien, merci.", HOAIMY)[1] == EMMA)
check("a multilingual voice is kept for any language",
      P.speech_plan("今日は晴れです。", EMMA)[1] == EMMA and P.speech_plan("Ça va très bien, merci.", EMMA)[1] == EMMA)
check("a voice picked for that language is kept",
      P.speech_plan("Ça va très bien, merci.", "fr-FR-DeniseNeural")[1] == "fr-FR-DeniseNeural")
check("a non-Edge voice is never swapped", P.speech_plan("Hola, ¿cómo estás hoy?", "alloy")[1] == "alloy")
check("the text of another language is never respelled",
      P.speech_plan("今日は晴れです。", HOAIMY)[0] == "今日は晴れです。")

print()
if fails:
    print(f"FAIL: {len(fails)} check(s)")
    sys.exit(1)
print("All checks passed.")
