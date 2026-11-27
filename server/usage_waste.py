"""Where Claude Code input tokens were spent for nothing: the "waste" block of the Usage page (2026-11-27).

The owner looked at a third-party "save tokens" kit and asked which of its ideas Javis lacked. The Usage page already
shows how much the prompt cache SAVED; it never said how much was LOST and why. This module answers that from data
Javis already keeps: every Claude Code request, one row per request in `usage_cli_requests` (usage_index.py), with its
time, model and the tokens it wrote to the cache.

Three causes, each measured, none estimated:

- **cold**: a request that rewrote a large prefix after the conversation sat idle longer than the cache lives. On a
  Claude plan the prompt cache lives one hour after its last use, so the next message re-writes the whole thread
  (system prompt, tools, every earlier turn) at write price instead of reading it at a tenth of the price.
- **model_switch**: a large rewrite right after the model changed inside the same conversation. Every model has its
  own cache, so a switch throws the warm one away.
- **long**: requests whose context was already over LONG_CONTEXT_TOKENS. Not waste by itself (the work may need it),
  but it is where most of the bill sits, and the share tells whether rotating long threads would pay.

Rules that keep the numbers honest:
- Only writes of at least MIN_REWRITE_TOKENS count as a rebuild. A new tool result or a new question also writes to
  the cache; a few thousand tokens of that is ordinary growth, not a rebuild.
- The first request of a conversation is never a rebuild: there was nothing to keep warm.
- Sub-agent requests (`activity == "subagent"`) share the parent's session id but have their own cache, so they are
  left out of the sequence; mixing them in would read every switch between parent and sub-agent as a model switch.
- The idle gap is one hour, the plan cache's lifetime. A Claude Code run on an API key has a five-minute cache, so its
  cold rebuilds between five and sixty minutes are not counted: the page under-reports rather than over-reports.
"""
from __future__ import annotations

from typing import Iterable

MIN_REWRITE_TOKENS = 20_000
COLD_GAP_S = 60 * 60
LONG_CONTEXT_TOKENS = 200_000


def _num(value) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _context(event: dict) -> int:
    return _num(event.get("input")) + _num(event.get("cache_read")) + _num(event.get("cache_create"))


def classify(events: Iterable[dict], start_day: str = "", end_day: str = "") -> dict:
    """Sort Claude Code requests into the three causes above.

    `events` are request payloads as usage_index stores them (`ts`, `day`, `model`, `session_id`, `activity`, `input`,
    `cache_read`, `cache_create`). Requests outside [start_day, end_day] still serve as the PREVIOUS request of the
    first one inside it, so a rebuild just after midnight on the first day of the period is not lost; they are never
    counted themselves. Empty bounds mean no bound.
    """
    def in_range(day: str) -> bool:
        return (not start_day or day >= start_day) and (not end_day or day <= end_day)

    by_session: dict = {}
    for ev in events or ():
        if not isinstance(ev, dict) or ev.get("activity") == "subagent":
            continue
        sid = str(ev.get("session_id") or "")
        if not sid or _num(ev.get("ts")) <= 0:
            continue
        by_session.setdefault(sid, []).append(ev)

    total = 0
    requests = 0
    cold = {"count": 0, "tokens": 0}
    switch = {"count": 0, "tokens": 0}
    long_ctx = {"count": 0, "tokens": 0}
    for items in by_session.values():
        items.sort(key=lambda e: _num(e.get("ts")))
        prev = None
        for ev in items:
            counted = in_range(str(ev.get("day") or ""))
            ctx = _context(ev)
            if counted:
                requests += 1
                total += ctx
                if ctx > LONG_CONTEXT_TOKENS:
                    long_ctx["count"] += 1
                    long_ctx["tokens"] += ctx
            write = _num(ev.get("cache_create"))
            if counted and prev is not None and write >= MIN_REWRITE_TOKENS:
                if str(ev.get("model") or "") != str(prev.get("model") or ""):
                    switch["count"] += 1
                    switch["tokens"] += write
                elif _num(ev.get("ts")) - _num(prev.get("ts")) > COLD_GAP_S:
                    cold["count"] += 1
                    cold["tokens"] += write
            prev = ev

    def share(part: int) -> float:
        return round(part * 100.0 / total, 1) if total else 0.0

    for bucket in (cold, switch, long_ctx):
        bucket["pct"] = share(bucket["tokens"])
    return {"requests": requests, "input_tokens": total,
            "cold": cold, "model_switch": switch, "long": long_ctx,
            "rules": {"min_rewrite_tokens": MIN_REWRITE_TOKENS, "cold_gap_min": COLD_GAP_S // 60,
                      "long_context_tokens": LONG_CONTEXT_TOKENS}}
