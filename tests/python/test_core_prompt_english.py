"""The rules Javis writes for the model are English; people still talk to it in any language.

    python tests/run.py core_prompt_english      (no network)

Owner, 2026-11-15: "translate the rest of the Javis core into English, carefully, without breaking anything".
CLAUDE.md was already English, but about 10,000 characters of channel rules, the token-saving capsule, the
agentic paths, the skill router, the Javis Core role and a dozen smaller blocks were still Vietnamese, and
they are what the model reads last before it writes. An English speaker got a prompt that was a quarter
Vietnamese, with mình/bạn examples, and Javis drifted into Vietnamese.

What stays Vietnamese on purpose, and is allowed below:
- the `# === ... ===` block headers: `context_runtime` measures blocks by them and CLAUDE.md names them;
- names the program itself writes or reads: `[Phiên chat: ...]`, `[Giờ gửi tin này: ...]`,
  `[NGỮ CẢNH GIAO DIỆN: ...]` with `trang=`, `chọn=`, `ngắt_lời=`, `kênh=giọng`;
- the Vietnamese page names next to the English ones ("the Tasks page (Nhiệm vụ)"), because the
  interface can be in either language.
Data is not rules: memory, profiles, skill descriptions and tool results stay in whatever language they are.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import os
import re
import sys
import tempfile
from pathlib import Path

SCRATCH = Path(tempfile.mkdtemp(prefix="javis-core-english-"))
for key, relative in {"JAVIS_STATE_DIR": "state", "BRAINS_DIR": "brains", "OBSIDIAN_VAULT_PATH": "vault",
                      "BRAIN_PATH": "brain", "SOURCES_PATH": "sources", "JAVIS_SESSIONS_DB": "sessions.sqlite3"}.items():
    os.environ[key] = str(SCRATCH / relative)

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import channel_context  # noqa: E402
import compaction  # noqa: E402
import context_compiler as cc  # noqa: E402
import context_runtime  # noqa: E402
import javis_core  # noqa: E402
import lang  # noqa: E402
import main_attachment_rendering as A  # noqa: E402
import main_prompt_rendering as R  # noqa: E402
import memory_control  # noqa: E402
import project_context  # noqa: E402

fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (f"  [{extra}]" if (extra and not cond) else ""))
    if not cond:
        fails.append(name)


VI = re.compile(r"[àáạảãâầấậẩẫăằắặẳẵèéẹẻẽêềếệểễìíịỉĩòóọỏõôồốộổỗơờớợởỡùúụủũưừứựửữỳýỵỷỹđ]", re.I)
ALLOWED = ("`# === NGÔN NGỮ ===`", "(Nhiệm vụ)", "(Kết nối)", "\"AI tự vận hành\"", "`[NGỮ CẢNH GIAO DIỆN: ...]`",
           "`[Phiên chat: web:<id>]`", "`trang=`", "`chọn=`", "`ngắt_lời=`", "`kênh=giọng`",
           "`[Giờ gửi tin này: ...]`")


def vietnamese_words(text: str) -> list:
    """Vietnamese words left once headers and the allowed program names are taken out."""
    body = "\n".join(line for line in text.splitlines() if not line.startswith("# ==="))
    for phrase in ALLOWED:
        body = body.replace(phrase, " ")
    return [w for w in re.findall(r"\S+", body) if VI.search(w)]


def english(name: str, text: str):
    left = vietnamese_words(text)
    check(f"{name}: written in English", bool(text.strip()) and not left, left[:12])
    check(f"{name}: no em or en dash", "—" not in text and "–" not in text)


# ---- 1. the channel block, every channel, both ways of carrying the session id ----
for src, meta in (("telegram", {"chat_id": 7, "chat_type": "group", "chat_title": "Shop", "user_name": "An"}),
                  ("telegram", {"chat_id": 7}), ("zalo", {"chat_id": "zalo:1", "chat_type": "group"}),
                  ("zalo", {"chat_id": "zalo:1"}), ("slack", {"chat_id": "slack:1", "chat_type": "group"}),
                  ("whatsapp", {"chat_id": "whatsapp:1"}), ("discord", {"chat_id": "discord:1"}),
                  ("lark", {"chat_id": "lark:1"}), ("cli", {"host": "mac"}), ("dashboard", {"session_id": "s1"})):
    for session_in_turn in (False, True):
        for brain in ("/b", None):
            block = channel_context.build_channel_block(src, meta, telegram_running=True, brain_root=brain,
                                                        session_in_turn=session_in_turn)
            english(f"channel {src} (session line {session_in_turn}, brain {bool(brain)})", block)
block = channel_context.build_channel_block("dashboard", {"session_id": "s1"})
check("the channel header stays (context_runtime measures it)", "# === KÊNH HỘI THOẠI HIỆN TẠI" in block)
check("the closing line says the language of the rules is no hint",
      block.rstrip().endswith(channel_context.LANGUAGE_LAST_WORD)
      and "their language is no hint" in channel_context.LANGUAGE_LAST_WORD)
check("reminders follow the owner's time zone, not a fixed Vietnam time",
      "owner's time zone" in channel_context.build_channel_block("telegram", {"chat_id": 1})
      and "Vietnam time" not in channel_context.build_channel_block("telegram", {"chat_id": 1}))

# ---- 2. the token-saving capsule ----
english("Core Contract", cc.CORE_CONTRACT)
english("stable clock note", cc.STABLE_CLOCK_NOTE)
check("the clock note names both header labels", "[Giờ gửi tin này:" in cc.STABLE_CLOCK_NOTE
      and "[This message was sent at:" in cc.STABLE_CLOCK_NOTE)
for ch in ("dashboard", "telegram", "cli", "slack", "whatsapp", "discord", "lark", "web"):
    english(f"capsule channel contract {ch}", cc.ContextCompiler._channel_contract(ch))
    english(f"capsule output contract {ch}", cc.ContextCompiler._output_contract_text(ch))
# The capsule's own estimator counts characters (HeuristicTokenizer: 3 per token) and its required items have
# a tight budget (a 12,000 TPM Groq plan). The English text must not cost more than the Vietnamese it replaced.
required = (len(cc.CORE_CONTRACT) + len(cc.ContextCompiler._channel_contract("dashboard"))
            + len(cc.ContextCompiler._output_contract_text("dashboard")) + len(cc.STABLE_CLOCK_NOTE))
check("the capsule's required text is no longer than the Vietnamese one (1,737 characters)", required <= 1737, required)
SRC = (Path(SERVER) / "context_compiler.py").read_text(encoding="utf-8")
for said in ("Current objective:", "This is a read-only planner.", "This is the final synthesis round of a read-only",
             "This is the final synthesis round of a multi-step", "Planner contract: this is an argument-filling round.",
             "The sources below CONTRADICT each other"):
    check(f"capsule round in English: {said[:40]}", said in SRC)
check("no Vietnamese round text left in the compiler", "Mục tiêu hiện tại" not in SRC and "Đây là vòng tổng hợp" not in SRC)

# ---- 3. the blocks of the main prompt ----
english("agentic paths", R.render_agentic_paths("/b", "/b/agents", "/b/workflows", "/b/Javis/loops", "/b/skills"))
english("capability summary", R.render_capability_summary({
    "agents": [{"name": "Writer"}], "skills": [{"group": "Sales", "enabled": True}], "workflows": [],
    "loops": [{"name": "Daily", "enabled": True}], "plugins": [{"name": "Clock", "loaded": True, "tools": ["now"]}]}))
english("skill router", R.render_skill_router([{"slug": "mail", "name": "Mail", "description": "Write email"}],
                                              skills_dir="/b/skills", hidden_count=3))
english("usage block", R.render_usage_block({"in": 10, "out": 2, "turns": 1, "cost": 0.1}))
english("profile block", R.render_profile_block("Call me Mai."))
english("memory index notes", R.render_memory_block("- [Fact](facts/fact.md) - detail\n" * 400, memory_cap=600))
english("memory shortened note", R.fit_memory_index("- [Fact](facts/fact.md) - " + "long detail " * 30 + "\n", 120))
english("learning off note", memory_control.LEARNING_OFF_NOTE)
for header, block in (("BỘ NHỚ DÀI HẠN", R.render_memory_block("x", memory_cap=10)),
                      ("LỚP AGENTIC", R.render_agentic_paths("/b", "a", "w", "l", "s")),
                      ("SKILL KHẢ DỤNG", R.render_skill_router([], skills_dir="/s", hidden_count=1)),
                      ("MỨC DÙNG HÔM NAY", R.render_usage_block({"in": 1}))):
    check(f"header '{header}' still starts its block", f"# === {header}" in block)
    check(f"header '{header}' is still a measured marker",
          any(marker == f"# === {header}" for _, marker in context_runtime._SYSTEM_MARKERS))

# ---- 4. attachments, project lessons, Javis Core, compaction ----
lines, sections = A.render_attachment_lists(
    [{"name": "a", "path": "a.md", "pinned": True}, {"name": "d", "path": "d/"}, {"name": "b", "path": "b.png", "pinned": True}],
    [{"url": "https://x.y", "pinned": True}], ["text"], list_max=10, allowed_suffixes={".md"}, file_max=100, total_max=100)
english("project documents", A.render_project_assets(lines, sections))
english("chat documents", A.render_session_assets(lines, sections))
english("project lessons guide", project_context.LEARN_GUIDE + project_context.BLOCK_NOTE + project_context.AGENT_GUIDE)
check("the project lessons guide stays short", len(project_context.LEARN_GUIDE) <= 650, len(project_context.LEARN_GUIDE))
english("Javis Core role", javis_core.definition()["body"])
check("the Javis Core role stays small", len(javis_core.prompt_block()) < 2600, len(javis_core.prompt_block()))
english("Javis Core naming lines", javis_core.identity_block(None))
english("resume wrapper", compaction.bootstrap_prompt(
    [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "hello"}] * 3, "next", max_chars=1000)
    .replace("[KHÔI PHỤC NGỮ CẢNH HỘI THOẠI]", "").replace("[HẾT LỊCH SỬ]", "")
    .replace(compaction.CURRENT_REQUEST_MARKER, ""))
check("the resume markers other code looks for are unchanged",
      compaction.CURRENT_REQUEST_MARKER == "[YÊU CẦU HIỆN TẠI]"
      and compaction.bootstrap_prompt([{"role": "user", "content": "x"}], "y").startswith("[KHÔI PHỤC NGỮ CẢNH HỘI THOẠI]"))

# ---- 5. the language block knows the rules are English now ----
auto = lang.khoi_ngon_ngu(lang.resolve(turn_text="show me the revenue"))
check("the language block no longer calls the prompt Vietnamese",
      "These rules are in English" in auto and "Much of this prompt" not in auto)

print()
if fails:
    print(f"FAIL: {len(fails)} check(s)")
    sys.exit(1)
print("All checks passed.")
