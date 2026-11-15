"""Javis works in ANY language, not only Vietnamese and English.

    python tests/run.py any_reply_language      (no network)

Owner, 2026-11-15: "switch to any language and Javis must work and talk in that language, like Claude
or ChatGPT", "let the model handle the language", and "the language setting only sets the interface".
So the model follows whoever writes; nothing in Settings or on a bot names a reply language. Fixed:

1. Kanban tasks, reminders, loops and learning built their prompt with no language, which NAMED
   Vietnamese, so every background report of an English or Japanese owner came in Vietnamese;
2. the "Javis replies in" picker (Settings) and the bot language picker are gone; a pin saved before
   moves into the person's profile, where the model reads it, and the key goes back to "auto";
3. where a language still has to be named (a voice call, "answer in Japanese" in the message), any of
   35 languages is named properly instead of falling back to Vietnamese (`lang_registry.get`);
4. a reply in Japanese, Korean or Thai was read aloud by the Vietnamese voice the owner picked.
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
import config as cfgmod  # noqa: E402
import context_compiler  # noqa: E402
import lang  # noqa: E402
import lang_registry as R  # noqa: E402
import main  # noqa: E402
import memory_control  # noqa: E402
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
check("Edge locale for the voice list", R.reply_info("ja").edge == "ja-JP" and R.reply_info("vi").edge == "vi-VN")
for raw, want in (("ja-JP", "ja"), ("ZH_hant", "zh-tw"), ("zh-HK", "zh-tw"), ("zh-CN", "zh"), ("pt-BR", "pt"),
                  ("fil", "tl"), ("nb", "no"), ("EN-us", "en"), ("xx", ""), ("", ""), ("auto", "")):
    check(f"reply_code({raw!r}) == {want!r}", R.reply_code(raw) == want, R.reply_code(raw))
check("an unknown code still falls back to the default language", R.get("xx").code == R.MAC_DINH)
check("a reply-only language reads its clock in English, not Vietnamese", R.get("ja").code == "en")

# ---- 2. asking for a language in the chat: the model handles it, the server pins nothing ----
for text in ("tiếng Nhật nhé", "Japanese please", "nói tiếng Hàn đi em", "auf Deutsch bitte", "en español por favor",
             "French pls", "trả lời bằng tiếng Pháp", "viết caption bằng tiếng Nhật"):
    d = lang.resolve(turn_text=text)
    check(f"followed by the model, not pinned: {text}", d.theo_nguoi_dung and d.capsule_lang == "", d)

# ---- 3. every pin names the right language ----
for kw in ({"channel_default": "ja"}, {"brain_pin": "ja"}):
    d = lang.resolve(turn_text="cho anh xem doanh thu tháng này", **kw)
    check(f"{list(kw)[0]}=ja pins Japanese", d.lang == "ja" and not d.theo_nguoi_dung, d)
d = lang.resolve(turn_text="cho anh xem doanh thu tháng này", channel_default=lang.call_language("今日の売上はいくらですか", ""))
block = lang.khoi_ngon_ngu(d)
check("a call in Japanese names Japanese with its native name",
      "Reply language: Japanese (日本語, ja), the language of this channel or call." in block, block)
check("block ends with the nudge in Japanese", block.rstrip().endswith("日本語で答えてください。"))
check("no Vietnamese pin hides behind a Japanese one", "Vietnamese" not in block.split("\n")[3])
check("capsule sentence names Japanese", "Japanese (ja)" in context_compiler._cau_ngon_ngu("ja")
      and "日本語で答えてください。" in context_compiler._cau_ngon_ngu("ja"))
auto = lang.resolve(turn_text="今日の売上はいくらですか")
check("a Japanese message is followed by the model, nothing named for it",
      auto.theo_nguoi_dung and auto.capsule_lang == "", auto)
check("a voice call in Japanese pins Japanese", lang.call_language("今日の売上はいくらですか", "ja-JP") == "ja")
check("a call recognised as Korean with no text pins Korean", lang.call_language("", "ko-KR") == "ko")

# ---- 4. Settings set the interface only; bots follow their customer ----
SRC = (Path(SERVER) / "main.py").read_text(encoding="utf-8")
CONSOLE = (ROOT / "dashboard" / "console.js").read_text(encoding="utf-8")
BOTS = (ROOT / "dashboard" / "chatbots.js").read_text(encoding="utf-8")
check("no reply-language picker in Settings", "vpReplyLang" not in CONSOLE and "reply_lang:" not in CONSOLE)
check("no language picker on the bot form", "cbNgonNgu" not in BOTS and "ngon_ngu:" not in BOTS)
check("the server sends no reply-language list", "reply_lang_list" not in SRC)
check("a cached page that still sends a pin cannot store it", 'lc["reply_lang"] = "auto"' in SRC)
check("no turn reads a reply language from Settings",
      'reply_pref=_lc.get("reply_lang")' not in SRC and '_lc_kenh.get("reply_lang")' not in SRC)
check("no turn reads a bot's language pin", '(bot or {}).get("ngon_ngu")' not in SRC)
bot_prompt = chatbot_runtime.build_bot_prompt({"name": "Shop", "ngon_ngu": "ja"})
check("an older bot record pinned to Japanese now follows its customer",
      "ngôn ngữ khách đang nhắn" in bot_prompt and "日本語" not in bot_prompt, bot_prompt[-200:])

# A pin saved before moves into the profile, once, and the key goes back to "auto".
memory_control.write_profile("Call me Mai.")
cfg = cfgmod.read_settings()
cfg.setdefault("locale", {})["reply_lang"] = "en"
cfgmod.write_settings(cfg)
check("migration moves an English pin", main.migrate_reply_lang_to_profile() == "en")
prof = memory_control.read_profile()
check("...into the profile, after what the person wrote",
      prof.startswith("Call me Mai.") and "Always reply to me in English, whatever language I write in." in prof, prof)
check("...and the setting is back to auto", (cfgmod.read_settings().get("locale") or {}).get("reply_lang") == "auto")
check("running it again changes nothing", main.migrate_reply_lang_to_profile() == "" and memory_control.read_profile() == prof)
cfg = cfgmod.read_settings()
cfg["locale"]["reply_lang"] = "ja"
cfgmod.write_settings(cfg)
main.migrate_reply_lang_to_profile()
check("a Japanese pin is written with its English name", "Always reply to me in Japanese" in memory_control.read_profile())
check("the profile is read every turn", "Always reply to me in Japanese" in main.build_system_prompt("brain"))
memory_control.write_profile("")
check("startup runs the migration", "await asyncio.to_thread(migrate_reply_lang_to_profile)" in SRC)

# ---- 5. background work ----
check("all four background features use the language-aware prompt",
      SRC.count("build_system_prompt=_background_system_prompt") == 4
      and "build_system_prompt=build_system_prompt" not in SRC)
bg = main._background_lang_decision()
check("background work follows the task's own language", bg.theo_nguoi_dung, bg)
check("...and the prompt says so instead of pinning Vietnamese",
      "language of the user's latest message" in main._background_system_prompt("brain")
      and "Reply language:" not in main._background_system_prompt("brain"))

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
