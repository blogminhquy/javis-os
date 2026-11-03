"""The Claude Code chat prompt is byte-identical across new chats, so its cache is read, not rewritten (#975).

    python tests/run.py stable_prompt_cache      (no network)

Field report 0.441.0 (issue #975): each new Claude Code chat read ~9k tokens from the prompt cache
and WROTE 48-57k, about 30% of a day's usage. Claude Code gets Javis's prompt through
`--append-system-prompt-file`, cached as ONE block, so a single changed character rewrites all of it.
Before 0.445.0 that block held the clock (to the minute), today's token usage, the dashboard
session id and the latest workflow run.

With `stable=True` (Claude Code dashboard lane) those four leave the system prompt and travel in
`_turn_facts_header` at the head of the user message. This test pins:
1. two chats with different session ids, at different times, with different usage and workflow
   runs, get the SAME system prompt;
2. the facts are still there for the model, in the header;
3. every other lane (stable=False) is unchanged: clock, usage, session id and last run stay in;
4. the Claude Code lane really uses the stable prompt and the header.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import os
import sys
import tempfile
from pathlib import Path

SCRATCH = Path(tempfile.mkdtemp(prefix="javis-stable-prompt-"))
for key, relative in {"JAVIS_STATE_DIR": "state", "BRAINS_DIR": "brains", "OBSIDIAN_VAULT_PATH": "vault",
                      "BRAIN_PATH": "brain", "SOURCES_PATH": "sources", "JAVIS_SESSIONS_DB": "sessions.sqlite3"}.items():
    os.environ[key] = str(SCRATCH / relative)

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import channel_context  # noqa: E402
import context_compiler  # noqa: E402
import main  # noqa: E402
import usage_store  # noqa: E402

fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (f"  [{extra}]" if extra and not cond else ""))
    if not cond:
        fails.append(name)


STATE = {"clock": "Bây giờ là 09:01 Thứ Hai 02/11/2026.", "usage": 1000, "run": "Lần chạy quy trình gần nhất: A lúc 09:00 02/11 (xong)."}
context_compiler.dong_ho = lambda now=None, lang="": STATE["clock"]
main._dong_lan_chay_gan_nhat = lambda brain: STATE["run"]
usage_store.summary = lambda *a, **k: {"today": {"total": {"in": STATE["usage"], "out": 50, "turns": 3}}}


def chat_prompt(sid, stable):
    """What the Claude Code dashboard lane sends: build_system_prompt + the dashboard channel block."""
    return main.build_system_prompt("brain", session_id=sid, stable=stable) + channel_context.build_channel_block(
        "dashboard", {"session_id": sid}, port=7777, brain_root="/brains/brain", session_in_turn=stable)


# ---- 1. stable: identical across chats, times, usage and runs ----
a = chat_prompt("sess-aaa111", True)
STATE.update(clock="Bây giờ là 23:59 Chủ Nhật 08/11/2026.", usage=987654,
             run="Lần chạy quy trình gần nhất: B lúc 23:00 08/11 (lỗi).")
b = chat_prompt("sess-bbb222", True)
check("stable prompt is byte-identical across two new chats", a == b,
      next((f"first diff at {i}: {a[i:i+60]!r} vs {b[i:i+60]!r}" for i in range(min(len(a), len(b))) if a[i] != b[i]), "length"))
check("no session id in the stable prompt", "sess-aaa111" not in a and "sess-bbb222" not in b)
check("no clock text in the stable prompt", "09:01" not in a and "23:59" not in b)
check("no usage block in the stable prompt", "MỨC DÙNG HÔM NAY" not in a and "987,654" not in b)
check("no latest workflow run in the stable prompt", "Lần chạy quy trình gần nhất" not in a)
check("the clock heading stays and points at the message header",
      "# === BÂY GIỜ ===" in a and "[Giờ gửi tin này: ...]" in a)
check("the chat_id rule now points at the session line",
      "[Phiên chat: web:<mã>]" in a and '"chat_id":"web:<mã>"' in a and 'owner_chat: "web:<mã>"' in a)
check("the clock block still comes before the channel block",
      a.index("# === BÂY GIỜ ===") < a.index("# === KÊNH HỘI THOẠI HIỆN TẠI"))

# ---- 2. the facts travel in the header ----
STATE.update(usage=1234)
h1 = main._turn_facts_header("brain", "sess-aaa111", "vi", first=True)
check("header has the send time", h1.startswith("[Giờ gửi tin này:"), h1)
check("header has the session id as web:<id>", "[Phiên chat: web:sess-aaa111]" in h1, h1)
check("first turn header has the latest workflow run", "Lần chạy quy trình gần nhất: B" in h1, h1)
check("first turn header has today's usage", "1,234 token vào" in h1, h1)
h2 = main._turn_facts_header("brain", "sess-aaa111", "vi", first=False)
check("resumed turn header keeps time and session id", "[Giờ gửi tin này:" in h2 and "web:sess-aaa111" in h2, h2)
check("resumed turn header drops run and usage", "Lần chạy" not in h2 and "token vào" not in h2, h2)
check("header uses no em dash", "—" not in h1)
check("English header label follows the language", main._turn_facts_header("brain", "", "en").startswith("[This message was sent at"))

# ---- 3. every other lane is unchanged ----
c = chat_prompt("sess-ccc333", False)
check("default prompt still has the clock", STATE["clock"] in c)
check("default prompt still has the usage block", "MỨC DÙNG HÔM NAY" in c)
check("default prompt still has the latest workflow run", "Lần chạy quy trình gần nhất: B" in c)
check("default channel block still names the session id",
      "Mã phiên chat hiện tại: `sess-ccc333`" in c and 'web:sess-ccc333' in c)

# ---- 4. the Claude Code lane uses it ----
SRC = (Path(SERVER) / "main.py").read_text(encoding="utf-8")
check("Claude Code lane asks for the stable prompt",
      '"cli", cli.model or mcfg.get("claude_model") or "mặc định", kind, stable=_stable_sp)' in SRC)
check("Claude Code lane prefixes the turn facts header",
      "_turn_facts_header(brain, conv_sid or \"\", _lang_qd.lang, first=not cli.session_id)" in SRC)
check("agent DMs keep their own prompt", "_stable_sp = not _persona" in SRC)
check("Codex, Grok and Antigravity lanes are untouched",
      all(f'_subscription_system_prompt("{p}"' in SRC or f'_subscription_system_prompt(\n                    "{p}"' in SRC
          for p in ("codex", "grok-cli", "antigravity-cli")) and SRC.count("stable=_stable_sp") == 1)

print()
if fails:
    print(f"FAIL: {len(fails)} check(s)")
    sys.exit(1)
print("All checks passed.")
