"""Automatic retry of a team job step that failed for a temporary reason (0.436.0).

Before this, every engine error in a step (provider overloaded, rate limit, a dropped connection, the plan running out)
marked the step failed and blocked the whole job until the owner pressed Retry. A job started in the evening could sit
there all night because of one 529. The retry chain with a circuit breaker follows stablyai/orca's orchestration
(`--retry-of`, the Dispatch breaks after three failed starts); the plan-limit wait reuses the chat and Kanban detector
(`limit_learner`) instead of a second set of patterns.

Rules (each one keeps cost and side effects bounded):
- Only an error a later attempt can fix: overload, rate limit, network trouble, or the subscription plan out of quota
  (then the step waits for the reset time the provider gave).
- Never a timeout (the step already ran up to `STEP_TIMEOUT_S`; running it again doubles the cost), never a login error,
  never an error raised before the model was called (configuration: the owner has to fix something first).
- Never a step that may already have acted: a Work/Help step (tools on) retries only when it is KNOWN to have made zero
  tool calls. Plan and Synthesize steps have no tools, so they may always retry.
- At most `max_retries()` failures in one chain (same kind, member, brief and job revision). After that the job blocks as
  before and the owner decides. The owner can switch it off with JAVIS_TEAM_AUTO_RETRIES=0.
"""
from __future__ import annotations

import os
import re
import time
from datetime import datetime
from typing import Optional

import limit_learner
import limit_resume
import localefmt

BLOCK_KIND = "auto_retry"
DEFAULT_MAX_RETRIES = 3
# Wait before attempt 2, 3, 4 of a temporary error (seconds). Short first: most overloads clear in a minute.
BACKOFF_S = (60, 300, 900)
LIMIT_GRACE_S = limit_resume.GRACE_SECONDS
LIMIT_MAX_WAIT_S = limit_resume.MAX_WAIT_SECONDS
LIMIT_UNKNOWN_WAIT_S = 30 * 60      # same as a Kanban job when the provider gives no reset time
# Error reasons `TeamRunner._turn` sets that must never retry on their own.
NO_RETRY_REASONS = ("timeout", "auth", "internal")
# Words of a temporary provider or network failure. Matched on the engine's error text (English, from the provider),
# never on the model's answer. The step timeout is excluded by reason above, not by these words.
TRANSIENT_RE = re.compile(
    r"overloaded|rate[\s_-]?limit|too many requests|\b(?:429|502|503|504|529)\b|temporar(?:y|ily)"
    r"|service unavailable|bad gateway|gateway time-?out|server error|api_error|internal error"
    r"|connection (?:reset|refused|error|aborted|closed|lost)|econnreset|econnrefused|network|socket hang up"
    r"|read timed out|timed out while|try again", re.I)
PLAN_NAMES = {"claude-code": "Claude", "codex": "ChatGPT", "grok-cli": "SuperGrok", "antigravity-cli": "Google"}


def max_retries() -> int:
    try:
        return max(0, min(10, int(os.environ.get("JAVIS_TEAM_AUTO_RETRIES", str(DEFAULT_MAX_RETRIES)))))
    except ValueError:
        return DEFAULT_MAX_RETRIES


def chain_failures(steps: list, step: dict) -> int:
    """Failed steps of the same chain as `step` (same kind, member, brief and job revision), `step` included once it is
    marked failed. A retry adds a new step with the same four fields, so this counts the attempts so far."""
    key = (step.get("kind"), step.get("agent_key"), step.get("brief") or "", step.get("job_revision"))
    return sum(1 for s in steps if s.get("status") == "failed"
               and (s.get("kind"), s.get("agent_key"), s.get("brief") or "", s.get("job_revision")) == key)


def plan(out: dict, *, role: str, tool_roles: tuple, failures: int, provider: str = "",
         now: Optional[float] = None) -> Optional[dict]:
    """When the failed step should run again on its own: {"kind": "limit" | "transient", "at": epoch, "attempt": n,
    "of": max, "plan": plan name, "reset_text": provider's words}. None: block the job as before."""
    limit = max_retries()
    if limit <= 0 or failures < 1 or failures > limit:
        return None
    if str(out.get("status") or "") != "error" or out.get("before_engine"):
        return None
    if str(out.get("reason") or "") in NO_RETRY_REASONS:
        return None
    if role in tool_roles and out.get("tool_calls") != 0:
        return None
    ts = time.time() if now is None else float(now)
    text = f"{out.get('error') or ''}\n{out.get('detail') or ''}"
    hint = limit_learner.ENGINE_HINT_BY_PROVIDER.get(str(provider or ""), "")
    try:
        hit = limit_learner.parse_subscription_limit(text, engine_hint=hint, now=ts)
    except Exception:  # noqa: BLE001 - the detector must never turn one failure into two
        hit = None
    base = {"attempt": failures + 1, "of": limit + 1}
    if hit is not None:
        reset = float(getattr(hit, "reset_epoch", 0) or 0)
        at = reset + LIMIT_GRACE_S if reset > ts else ts + LIMIT_UNKNOWN_WAIT_S
        if at - ts > LIMIT_MAX_WAIT_S:
            return None
        return dict(base, kind="limit", at=at, plan=PLAN_NAMES.get(str(getattr(hit, "engine", "") or ""), ""),
                    reset_text=str(getattr(hit, "reset_text", "") or "").strip()[:80])
    if TRANSIENT_RE.search(text):
        return dict(base, kind="transient", at=ts + BACKOFF_S[min(failures, len(BACKOFF_S)) - 1])
    return None


def clock_text(at: float) -> str:
    """The retry time in the OWNER's time zone (a VPS usually runs UTC)."""
    try:
        return datetime.fromtimestamp(at, localefmt.tz()).strftime("%H:%M %d/%m")
    except Exception:  # noqa: BLE001
        return time.strftime("%H:%M %d/%m", time.localtime(at))


def reason_text(retry: dict, who: str, error: str) -> str:
    """The line on the job card and in the team chat. Calm: nothing for the owner to do."""
    when = clock_text(float(retry["at"]))
    n, of = int(retry["attempt"]), int(retry["of"])
    if retry["kind"] == "limit":
        said = retry.get("reset_text") or ""
        return localefmt.chu(
            "Gói {p} hết lượt{s}. Tự chạy lại bước của {w} lúc {t} (lần {n}/{m}).",
            "The {p} plan is out of quota{s}. {w}'s step runs again on its own at {t} (attempt {n}/{m}).",
            p=retry.get("plan") or localefmt.chu("thuê bao", "subscription"),
            s=(f" ({said})" if said else ""), w=who, t=when, n=n, m=of)
    return localefmt.chu(
        "{w} gặp lỗi tạm thời ({e}). Tự chạy lại lúc {t} (lần {n}/{m}).",
        "{w} hit a temporary error ({e}). Running again on its own at {t} (attempt {n}/{m}).",
        w=who, e=str(error or "").strip()[:160] or "-", t=when, n=n, m=of)
