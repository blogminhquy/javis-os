"""`javis_scout`: hand a data-heavy read to the background model and get back only the findings.

The idea, measured in the session that designed it: a sub-run that read real shop, sheet and site
data used about 242,000 tokens; what came back to the main conversation was one page. A scout
does that for any brain. It runs on the model the owner already chose for background work (the
Models page), so there is no new setting; with an Automatic background model, a "quick" scout
takes the light pick and a "careful" one the mid pick (aux_engine.tier_for_tag).

The main model decides WHEN to send a scout and WHAT to ask. It never picks the model: it cannot
know prices, what is left of a plan, or which sign-in is broken.

Hard rules, enforced here and at the hub, not by the prompt:
  - Read only. The scout runs at the `suggest` level: the hub refuses every write and every
    outside action, whatever the scout's prompt says.
  - No nesting. A scout cannot send a scout (turn context for engines that carry it, and a small
    cap on scouts running at once for the others).
  - Bounded. A wall-clock limit, a limit on scouts at once, a limit on the answer's size (a long
    answer is stored whole and shown as a view with a reference).
  - Never worse than before. Unavailable, busy, slow or empty: the tool says so in one line and
    tells the main model to do the reading itself, which is exactly what it did before this tool.
"""
from __future__ import annotations

import asyncio
import os
import secrets
import time
from typing import Awaitable, Callable, Optional

import turn_context

TOOL = "javis_scout"
TAG_CAREFUL = "scout"            # mid tier on an Automatic background model
TAG_QUICK = "scout-quick"        # light tier (listed in aux_engine.LIGHT_TAGS)
JOB_PREFIX = "scout:"
WALL_S_DEFAULT = 300
MAX_PARALLEL_DEFAULT = 2
ANSWER_CHARS = 7000
MIN_TASK_CHARS = 30

SYSTEM_PROMPT = (
    "You are a research scout working for Javis, a personal assistant. Another model sent you to gather facts "
    "from the owner's connected data sources and files, and will write the final answer from what you report. "
    "The owner never reads your text.\n\n"
    "Rules:\n"
    "- You can only READ. Writes and outside actions are refused by the system; do not try them.\n"
    "- Find the right tool with the tool search, then read real data. Never invent a number.\n"
    "- For every total, count, average, grouping or top-N use javis_query with sql: the code computes over ALL "
    "records. Never add numbers by reading records. A large result arrives as a partial view with a ref; query "
    "that ref instead of calling the source again. To cover a whole period, give javis_query the source `tool` "
    "and `pages`.\n"
    "- You cannot send another scout and you cannot ask questions. If something is missing, say exactly what.\n\n"
    "Report format, in the language of the task, at most about 600 words, no preamble:\n"
    "FINDINGS: the facts asked for, each number with its unit, period and the source tool it came from.\n"
    "REFS: any javis_query ref that holds the underlying records, with one line on what it contains.\n"
    "GAPS: what you could not get and why (not connected, permission, error text, incomplete pages).\n"
    "Report what the data says, not what would be nice to hear.")

DESCRIPTION = (
    "Send a read-only scout (the background model) to gather facts from connected sources and files, and get "
    "back only its findings. Use it for a data-heavy read: several sources, many pages, or a long report period, "
    "so the raw data never enters this conversation. Do NOT use it for a quick single lookup (doing it yourself "
    "is cheaper) or for anything that writes, sends or publishes (it cannot). The scout knows nothing about this "
    "conversation: write `task` so it stands alone (which shop or source, exact period, what numbers to return). "
    "It answers in one turn; if it reports a problem, do the reading yourself.")

SCHEMA = {
    "type": "object",
    "properties": {
        "task": {"type": "string", "description": "Self-contained brief: sources, exact period, what to return."},
        "effort": {"type": "string", "enum": ["quick", "careful"],
                   "description": "quick = lighter model for simple gathering; careful (default) for analysis."},
    },
    "required": ["task"],
}

# async runner(vault_root, task, tag, wall_s) -> {"text": str, "error": str, "model": str, "usage": dict}
_runner: Optional[Callable[..., Awaitable[dict]]] = None
_active = 0


def configure(runner) -> None:
    """The host (main.py) hands over the function that really runs an engine. None = no scout."""
    global _runner
    _runner = runner


def available() -> bool:
    return _runner is not None and enabled()


def enabled() -> bool:
    """`mcp.scout`: true (default) | false. JAVIS_SCOUT=0|1 wins."""
    v = (os.getenv("JAVIS_SCOUT") or "").strip().lower()
    if v in ("0", "false", "off", "no"):
        return False
    if v in ("1", "true", "on", "yes"):
        return True
    try:
        import config
        return (config.read_settings().get("mcp") or {}).get("scout", True) is not False
    except Exception:  # noqa: BLE001
        return True


def _env_int(name: str, default: int, low: int, high: int) -> int:
    try:
        return max(low, min(high, int(os.getenv(name, "") or default)))
    except (TypeError, ValueError):
        return default


def wall_seconds() -> int:
    return _env_int("JAVIS_SCOUT_MAX_WALL_S", WALL_S_DEFAULT, 30, 3600)


def max_parallel() -> int:
    return _env_int("JAVIS_SCOUT_MAX_PARALLEL", MAX_PARALLEL_DEFAULT, 1, 16)


def in_scout() -> bool:
    return str((turn_context.current() or {}).get("job") or "").startswith(JOB_PREFIX)


def _fallback(why: str) -> str:
    return (f"ERROR: the scout did not run ({why}). Do this reading yourself with your own tools; nothing was "
            "changed and nothing was read on your behalf.")


def build_prompt(task: str) -> str:
    return ("TASK FROM THE MAIN MODEL (it is your only context):\n" + task.strip()
            + "\n\nGather what is asked, then write the report in the format you were given.")


def _bound_answer(text: str, scope: str) -> str:
    """A long report is kept whole in the result store and shown as a view with a reference."""
    if len(text) <= ANSWER_CHARS:
        return text
    try:
        import tool_result_shaper
        import tool_result_store
        ref = tool_result_store.put(text, scope=scope, tool=TOOL, kind="text")
        if ref:
            return tool_result_shaper.build_text_preview(text, ref, ANSWER_CHARS)
    except Exception:  # noqa: BLE001
        pass
    cut = text.rfind("\n", 0, ANSWER_CHARS)
    return text[:cut if cut > ANSWER_CHARS // 2 else ANSWER_CHARS] + "\n[report cut here: it was longer than the limit]"


async def run(vault_root: str, task: str, effort: str = "careful") -> str:
    """One scout run, start to finish. Always returns text for the calling model, never raises."""
    global _active
    task = str(task or "").strip()
    if len(task) < MIN_TASK_CHARS:
        return ("ERROR: `task` is too short. The scout knows nothing about this conversation: say which source, "
                "the exact period and what to return.")
    if _runner is None or not enabled():
        return _fallback("scouts are switched off on this install")
    if in_scout():
        return _fallback("a scout cannot send another scout")
    if _active >= max_parallel():
        return _fallback(f"{_active} scouts are already running")
    tag = TAG_QUICK if str(effort or "").strip().lower() == "quick" else TAG_CAREFUL
    turn = dict(turn_context.current() or turn_context.make("scout"))
    turn["job"] = JOB_PREFIX + secrets.token_hex(6)
    token = turn_context.bind(turn)
    wall = wall_seconds()
    started = time.time()
    _active += 1
    try:
        try:
            out = await asyncio.wait_for(_runner(str(vault_root or ""), build_prompt(task), tag, wall), timeout=wall + 20)
        except asyncio.TimeoutError:
            return _fallback(f"it was still working after {wall} seconds")
        except Exception as e:  # noqa: BLE001 - whatever broke, the main model can still do the job itself
            return _fallback(f"{type(e).__name__}: {str(e)[:200]}")
    finally:
        _active -= 1
        turn_context.reset(token)
    out = out if isinstance(out, dict) else {}
    text, error = str(out.get("text") or "").strip(), str(out.get("error") or "").strip()
    if not text:
        return _fallback(error[:300] or "it returned nothing")
    usage = out.get("usage") if isinstance(out.get("usage"), dict) else {}
    bits = [f"model={out.get('model') or 'background model'}", f"{int(time.time() - started)}s"]
    if usage.get("input") or usage.get("output"):
        bits.append(f"tokens in={int(usage.get('input') or 0)} out={int(usage.get('output') or 0)}")
    note = ("Scout report (" + ", ".join(bits) + "). It read the data on a separate model; check any number you "
            "will quote that looks off by querying its REFS with javis_query.")
    return note + "\n\n" + await asyncio.to_thread(_bound_answer, text, str(vault_root or ""))


def build(vault_root, mode: str) -> tuple:
    """(tool spec, route entry) for one tool list."""

    async def _call(args):
        args = args if isinstance(args, dict) else {}
        return await run(str(vault_root or ""), args.get("task"), args.get("effort") or "careful")

    spec = {"fn": TOOL, "server": "javis", "name": TOOL, "namespace": "javis", "description": DESCRIPTION,
            "schema": SCHEMA}
    # Not a core tool: a scout is for the occasional heavy read, so it lives behind the tool search like any other
    # tool, and the search tool's description names it in one short line (mcp_hub.SCOUT_HINT).
    entry = {"call": _call, "source_type": "builtin", "source_id": "javis",
             "effect": "read", "required_mode": "readonly", "health": "healthy"}
    return spec, entry
