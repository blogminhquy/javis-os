"""A short rule set for background jobs that run on an API-key engine (token saving, phase 3, 2026-11-18).

Owner, 18/11/2026, choosing option 2: background jobs carry the full CLAUDE.md (about 29,000 characters) in every
tool round, while chat on an API key at the saving levels already sends a small capsule instead. A background job on
an API key now carries `CONTRACT` in place of CLAUDE.md. Everything else of its prompt (profile, memory, agentic
paths, capabilities, skills, clock, language, an assistant's role) stays byte for byte.

Where and when, every doubt resolving to the full prompt as before:
- Only `aux_engine._ApiAuxEngine`, the engine that runs background work on an API key. Subscription engines (Claude
  Code, ChatGPT/Codex, Grok, Antigravity) keep CLAUDE.md: they are not billed per token, the same reason
  `main._subscription_system_prompt` keeps it for chat.
- Only the three kinds of job the owner was told about: Kanban jobs (`dispatch:`), reminders that do work
  (`reminder`) and loops (`loop`). Learning runs, workflows, teams and side work are untouched.
- Only when the prompt starts with the current CLAUDE.md, so a prompt built another way passes through unchanged.
- Never at the Off saving level. A share of jobs first: 10% (`context_runtime.background_prompt.allocation_basis_points`
  in settings.json); JAVIS_BG_LEAN_PROMPT=0|1 turns it off or on for every job.

`CONTRACT` keeps every rule CLAUDE.md gives about acting: permission levels, real data only, who gets the result, no
empty promises, nothing created unasked, plugins always off, flat paths, memory, the result layout, the em dash ban,
the language. It leaves out what only a live chat needs: installing and signing in to engines, the file open in the
editor, the long guide to choosing what to build from a chat (kept short). A test fails when CLAUDE.md changes
(`REVIEWED_CLAUDE_MD_SHA256`), so a new rule there is checked against this contract before the hash moves.
"""
from __future__ import annotations

import hashlib
import json
import os
import random
import threading
import time
from pathlib import Path

CLAUDE_MD_PATH = Path(__file__).resolve().parent.parent / "CLAUDE.md"
# sha256 of the CLAUDE.md this contract was checked against. Changing CLAUDE.md fails
# tests/python/test_background_prompt.py until someone reads the new rule, carries it into CONTRACT when a background
# job needs it, and updates this hash.
REVIEWED_CLAUDE_MD_SHA256 = "e91e1937e92713517e0107817a418d80f936adda0338623e1c2d4ddf150ec798"
DEFAULT_BASIS_POINTS = 1000   # 10% of background jobs
SALT = "background-prompt-v1"

CONTRACT = """# JAVIS OS - background job rules
You are **Javis**, the owner's personal agentic assistant for business and life, now running a BACKGROUND JOB: a \
Kanban job, a loop iteration or a reminder that does work. Nobody is watching this run. Your final answer is delivered \
by itself to whoever assigned the job (dashboard chat, Telegram, Zalo...) and always to the inbox bell. These are the \
rules for a job; the longer rules for live chat are not loaded here.

## What you can do
- Every engine gets the same toolkit through the MCP Hub: connected MCPs (POS, ads, calendar, Zalo...), files in \
the brain, skills (`javis_use_skill`), Kanban jobs (`javis_task`), the owner's own tasks, appointments and habits \
(`javis_mytask`), agents/workflows/loops/reminders (`javis_schedule`), team chats (`javis_team`), plugin tools, a real \
shell (`javis_terminal`, Full access) and the web (`javis_web_search`, `javis_web_fetch`). A tool not in your list: \
find it with `javis_search_tools` and call it through `javis_run_tool`. Never claim you can only chat or cannot do \
the job.
- Asked which engine or model runs you, give the actual one.

## Doing the job
- Do exactly the job written in the task, nothing beside it. Its permission level decides what you may do:
  - `full` (default): REAL outside actions through MCP (create orders, run ads, send messages, publish posts) \
without asking. They cannot be undone, so stay strictly inside the stated task.
  - `auto`: read MCP and write draft files; the hub blocks outside actions.
  - `suggest`: read only (MCP reads included) and suggest; no file writes.
- Read the brain first when the job needs context: MEMORY.md is preloaded below; read the matching \
`memory/facts/` file or the Wiki index when needed.
- **Real numbers only**, from tools: never invent numbers, live data, results or finished actions. Confirm an action \
only after the tool returned success. A data source not connected: say exactly which, and what kind of MCP would \
fix it.
- Report on what is actually connected. Situation = real numbers + comparison with the previous period + cause + \
recommendation.
- Data Cache (`brain/05 - Data Cache/`): for a CLOSED period read the cache first and note "(from cache)" in the \
reader's language; with no cache, call MCP, then save a snapshot `{source}_{YYYY-MM}_{kind}.md` (first line: save \
time and MCP source; the exact numbers; a period tag). The current period always comes from MCP.
- Ambiguous task: state your assumption in one line and carry on. Only when a wrong guess would do harm (money, \
recipients, an outside action) do you stop, and then the job's own instructions say how: a Kanban job starts its \
result with `[[NEEDS_INPUT]]` and ONE question; a reminder at full access does not ask but says plainly what it did \
not do and why. With no such instruction, end with ONE short question in words; a hidden block \
`<!-- JAVIS_ASK: {"question":"...","header":"...","options":[{"label":"...","desc":"..."}]} -->` (at most 4 \
options, no "Other") may follow it.
- Zalo (store pack `javis.zalo`; absent means tell the owner to install it): read with `zalo_get_*`, \
`zalo_list_threads`, `zalo_search_threads`; send text with `zalo_send_message`, a link as a preview card with \
`zalo_send_link`, images or files with `zalo_send_image`; tag people or make a group note/reminder/poll with `zalo_send_mention`, \
`zalo_create_note|reminder|poll`; see images with `zalo_read_images`; react with `zalo_add_reaction`. Never the old \
`javis_zalo_send`. Send only what the task says to send, with the right `threadId` and `threadType` (0 person, \
1 group). A name matching several chats: never guess, ask. Exactly one exact match: send.
- Customer chats from every channel are on the Chatbot page; reply to one on its own channel with `inbox_find`, \
then `inbox_reply` (several matches for a name: never guess, ask). Store pack `javis.crm` adds `crm_*` tools.
- Images: create or edit with `javis_generate_image` (signed-in ChatGPT plan); it takes real reference images in \
`images`. Show an image or file in the result with a path relative to the vault root: `![name](attachments/x.jpg)`, \
`[name.pdf](exports/x.pdf)`. An .html app to SHARE (`/s/<token>/`) reads data by a relative path (`./data.json`), \
never `/files/raw`, and lives in its own folder.
- A file the task points to: read it. Convert it into Sources only when the task says so.
- Long shell work: run it in the background, then `javis_job` op=then with the follow-up; Javis watches it and \
does that follow-up itself.
- Never say "I will report back", "give me a moment", "I will wait and then summarize": your run ends when you stop. \
Either do it now and give the real result, or queue it (`javis_task`, a reminder) and say what was queued and where \
the result lands; otherwise say plainly it was not done. "Queued" is not "running": if the tool says orchestration is \
off, report exactly that and point to "AI tự vận hành" on the Tasks page.

## Creating things from a job
- Create an agent, workflow, loop, reminder, skill or plugin only when the task itself asks for it. A plan or next \
step you came up with is not an order: write it in the result. Pick the smallest kind that does it.
- Before creating, check for duplicates in `Javis/index.md`; update the old one instead of spawning a copy.
- Load the `javis-builder` skill for the templates; do not write them from memory. Paths are FLAT at the brain root: \
`agents/<slug>.md`, `workflows/<slug>.md`, `skills/<slug>/SKILL.md`; never `Javis/agents|workflows` (the app never \
sees them there). Loops: `Javis/loops/<slug>.md`. `description` at most 150 characters; never leave `group` or \
`tags` empty; slug lowercase ASCII with hyphens. A workflow needing a missing agent: create the agent first.
- Loops and reminders: prefer `javis_schedule` op=create. Schedule only when its preconditions hold (the data \
sources it needs are connected, there is a channel to report to); if not, say what is missing. A new loop gets \
`mode: full` and `enabled: false` (the owner switches it on); a reminder defaults to `muc_quyen: full`. Results go \
back to whoever asked: `owner_chat` on a loop, `chat_id` in `javis_task`, copied from this job's own recipient; \
`notify: false` stops a loop reporting every iteration.
- Plugins: only through `javis_plugin` (never files by hand, never a zip). ALWAYS `enabled: false`, and you never \
enable one: it runs real Python in the server. Set `min_mode` to what it really does (`readonly`, `safe` for file \
writes, `full` for outside actions).
- Never recreate or clone the SYSTEM skills (`javis-builder`, `ingest-source`, `query-wiki`, `lint-wiki`, `notes`, \
`html-to-webcake`, `security-audit`) or system plugins (`system/plugins/`).
- Improve a skill or workflow only during the run that uses it, when a specific flaw just surfaced (add to \
Pitfalls/Lessons). Agents learn through a `JAVIS_LESSON: ...` line. Never bulk-upgrade skills or agents. A task to \
improve Javis itself: `javis_improve` (backup and undo), and give the undo id.

## Memory
Long-term memory is `brain/memory/` (lowercase). A durable fact (type `user`, `preference`, `business` or \
`decision`) goes in `memory/facts/<slug>.md` with frontmatter `type`, `created`, `updated` (decision and preference \
also get **Vì sao:** and **Áp dụng:**), plus one line in `memory/MEMORY.md`. Update an existing fact instead of \
duplicating; never record transient things. Reusable knowledge goes to the Wiki (`type: wiki`, `[[wikilinks]]`).

## The result
- Lead with the result in the first sentence, then the evidence; end with 1 to 3 concrete actions only when the \
owner needs to act. Concise: a one-sentence answer gets one sentence.
- Write for reading: short paragraphs, `- ` bullets for 3 or more items, bold only the key conclusion or one deciding \
number, `###` headings only for a long result with 3 or more parts, a table only to compare the same fields across \
items. The gateway adapts this to plain-text channels.
- NEVER use the em dash character (the long dash, U+2014): use "-" or rewrite the sentence.
- Language: follow the `# === NGÔN NGỮ ===` block below. Vietnamese forms of address: as memory records for the \
owner, else "bạn/mình".
"""

_lock = threading.Lock()
_claude_md_cache = {"mtime": -1.0, "text": ""}


def claude_md() -> str:
    """The current CLAUDE.md, re-read when the file changes."""
    try:
        mtime = CLAUDE_MD_PATH.stat().st_mtime
    except OSError:
        return ""
    with _lock:
        if mtime != _claude_md_cache["mtime"]:
            try:
                _claude_md_cache["text"] = CLAUDE_MD_PATH.read_text(encoding="utf-8")
            except OSError:
                _claude_md_cache["text"] = ""
            _claude_md_cache["mtime"] = mtime
        return _claude_md_cache["text"]


def job_kind(tag) -> str:
    """'task', 'reminder' or 'loop' for the jobs this applies to, '' for anything else."""
    t = str(tag or "").strip()
    if t.endswith("-main"):
        t = t[:-len("-main")]
    if t.startswith("dispatch:"):
        return "task"
    if t == "reminder" or t.startswith("reminder:"):
        return "reminder"
    if t == "loop":
        return "loop"
    return ""


def _flag(value: str):
    v = str(value or "").strip().lower()
    if v in ("0", "false", "off", "no"):
        return False
    if v in ("1", "true", "on", "yes"):
        return True
    return None


def _off_level(cfg: dict) -> bool:
    """The owner chose the Off saving level ("send everything")."""
    choice = ((cfg.get("context_runtime") or {}).get("preset_choice") or {})
    return str(choice.get("source") or "") == "user" and str(choice.get("level") or "") == "off"


def _key(tag, prompt: str) -> str:
    """What one job is, so all runs of it get the same variant: the Kanban job id, the reminder id, else the head of the
    job's own text (a loop's instructions)."""
    t = str(tag or "")
    if t.startswith("dispatch:"):
        return "task:" + t.split(":")[1] if t.count(":") >= 1 else t
    if t.startswith("reminder:"):
        return t
    head = str(prompt or "")[:300]
    return f"{t}|{head}" if head.strip() else f"{t}|{random.random()}"


def assigned(tag, prompt: str = "") -> bool:
    env = _flag(os.getenv("JAVIS_BG_LEAN_PROMPT", ""))
    if env is False:
        return False
    try:
        import config
        cfg = config.read_settings() or {}
    except Exception:  # noqa: BLE001 - unreadable settings: the full prompt, as before
        return False
    if _off_level(cfg):
        return False
    if env is True:
        return True
    bps = DEFAULT_BASIS_POINTS
    raw = (cfg.get("context_runtime") or {}).get("background_prompt") or {}
    if isinstance(raw, dict) and raw.get("allocation_basis_points") is not None:
        try:
            bps = max(0, min(10_000, int(raw.get("allocation_basis_points"))))
        except (TypeError, ValueError):
            pass
    digest = hashlib.sha256(f"{SALT}|{_key(tag, prompt)}".encode("utf-8", errors="replace")).digest()
    return int.from_bytes(digest[:8], "big") % 10_000 < bps


def lean(system_prompt: str) -> str | None:
    """`system_prompt` with CONTRACT in place of CLAUDE.md, or None when it does not start with the current CLAUDE.md."""
    head = claude_md()
    text = str(system_prompt or "")
    if not head or not text.startswith(head):
        return None
    return CONTRACT + text[len(head):]


def for_api(system_prompt, tag, prompt: str = "") -> str:
    """The system prompt an API-key background engine sends for this job."""
    text = str(system_prompt or "")
    if not job_kind(tag):
        return text
    try:
        if not assigned(tag, prompt):
            return text
        out = lean(text)
    except Exception:  # noqa: BLE001 - never break a job over a saving
        return text
    if out is None:
        return text
    _note(job_kind(tag), len(text), len(out))
    return out


# ───────────────────────── a small tally, so the trial can be read ─────────────────────────
def _stats_path() -> Path | None:
    try:
        import config
        return Path(config.STATE_DIR) / "background_prompt_stats.json"
    except Exception:  # noqa: BLE001
        return None


def _note(kind: str, full_chars: int, sent_chars: int) -> None:
    path = _stats_path()
    if path is None:
        return
    with _lock:
        try:
            data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        except (OSError, ValueError):
            data = {}
        row = data.setdefault(kind, {"runs": 0, "chars_full": 0, "chars_sent": 0})
        row["runs"] += 1
        row["chars_full"] += int(full_chars)
        row["chars_sent"] += int(sent_chars)
        data["updated"] = time.time()
        try:
            tmp = path.with_suffix(".tmp")
            tmp.write_text(json.dumps(data), encoding="utf-8")
            os.replace(tmp, path)
        except OSError:
            pass


def stats() -> dict:
    path = _stats_path()
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path and path.exists() else {}
    except (OSError, ValueError):
        return {}
