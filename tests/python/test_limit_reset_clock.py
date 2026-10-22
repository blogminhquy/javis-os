"""Regression (field report 0.270, code 25): a plan limit that names a CLOCK time.

Claude on the Pro plan prints "You've hit your limit · resets 1:50am (Asia/Bangkok)". Javis only
read delays ("resets in 2 hours"), so the card said the provider did not say when it reopens and
no automatic retry was scheduled. The clock time is now read in the tz in parentheses (zoneinfo),
or in local time without one, and the NEXT occurrence of that time is the reset.

Run:
    python tests/python/test_limit_reset_clock.py
"""
from _paths import ROOT, SERVER  # noqa: E402,F401  - puts server/ on sys.path (see tests/python/_paths.py)
import os
import sys
import time
from datetime import datetime, timedelta, timezone

# Local time for the "no time zone" samples. tzset does not exist on Windows; there the expected
# values below are computed from the machine's own local time instead.
os.environ["TZ"] = "Asia/Ho_Chi_Minh"
if hasattr(time, "tzset"):
    time.tzset()

import limit_learner  # noqa: E402
import limit_resume  # noqa: E402
import model_limits  # noqa: E402

fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        fails.append(name)


def utc(*a) -> float:
    return datetime(*a, tzinfo=timezone.utc).timestamp()


def local(*a) -> float:
    return datetime(*a).timestamp()   # naive = this machine's local time, same rule as the parser


CUSTOMER = "You've hit your limit · resets 1:50am (Asia/Bangkok)"
NOW = utc(2026, 10, 22, 18, 0)          # 01:00 on 23/10 in Bangkok (UTC+7)
clock = limit_learner._reset_clock_epoch

# ── the exact customer sample ──
check("customer sample: 1:50am Bangkok, 50 minutes later",
      clock(CUSTOMER, NOW) == utc(2026, 10, 22, 18, 50))
check("customer sample after 1:50 Bangkok: tomorrow's 1:50",
      clock(CUSTOMER, utc(2026, 10, 22, 19, 0)) == utc(2026, 10, 23, 18, 50))
hit = limit_learner.parse_subscription_limit(CUSTOMER, engine_hint="claude-code", now=NOW)
check("customer sample is a subscription limit", hit is not None and hit.engine == "claude-code")
check("customer sample has a reset time (not 'unknown')", hit is not None and hit.reset_epoch == utc(2026, 10, 22, 18, 50))
check("customer sample keeps the provider's words", hit is not None and hit.reset_text == "resets 1:50am (Asia/Bangkok)")

# ── more forms ──
check("12pm (UTC)", clock("You've hit your session limit · resets 12pm (UTC)", NOW) == utc(2026, 10, 23, 12, 0))
check("reset at 5pm (America/New_York), DST-aware",
      clock("Your limit will reset at 5pm (America/New_York).", NOW) == utc(2026, 10, 22, 21, 0))
check("a.m. with dots", clock("resets 9:05 a.m. (UTC)", NOW) == utc(2026, 10, 23, 9, 5))
check("midnight (UTC)", clock("resets midnight (UTC)", NOW) == utc(2026, 10, 23, 0, 0))
check("weekly form with a date", clock("Weekly limit reached ∙ resets Oct 24, 1am (UTC)", NOW) == utc(2026, 10, 24, 1, 0))
check("a past date means next year", clock("resets Jan 2 at 3pm (UTC)", NOW) == utc(2027, 1, 2, 15, 0))
check("GMT+7 offset form", clock("resets 1:50am (GMT+7)", NOW) == utc(2026, 10, 22, 18, 50))

# ── no time zone: local time ──
now_local = local(2026, 10, 23, 0, 30)
check("1am, no tz: local, later tonight", clock("resets 1am", now_local) == local(2026, 10, 23, 1, 0))
check("13:50, no tz: local, today", clock("5-hour limit reached ∙ resets 13:50", now_local) == local(2026, 10, 23, 13, 50))
check("1am, no tz, already past: tomorrow", clock("resets 1am", local(2026, 10, 23, 2, 0)) == local(2026, 10, 24, 1, 0))
check("unknown tz name falls back to local time",
      clock("resets 1am (Mars/Olympus)", now_local) == local(2026, 10, 23, 1, 0))

# ── not clock times ──
check("'resets 5 hours' is not a clock time", clock("resets 5 hours", NOW) == 0.0)
check("'reset your API key' is not a clock time", clock("Please reset your API key at console.anthropic.com", NOW) == 0.0)
check("13pm is rejected", clock("resets 13pm", NOW) == 0.0)
check("25:00 is rejected", clock("resets 25:00", NOW) == 0.0)
check("Feb 30 is rejected, not guessed", clock("resets Feb 30, 1am (UTC)", NOW) == 0.0)
d = limit_learner.parse_subscription_limit("Claude usage limit reached. Try again in 2 hours 15 minutes", now=NOW)
check("delay form still wins", d is not None and d.reset_epoch == NOW + 2 * 3600 + 15 * 60)

# ── what the owner sees ──
reg = limit_resume.LimitResumeRegistry()


async def _noop(_attempt):
    return None

item = reg.schedule("s1", hit.reset_epoch, _noop, engine=hit.engine, now=NOW, auto_default=False)
check("the resume card no longer reports 'no_reset'", item.reason != "no_reset" and item.resume_at == hit.reset_epoch)
reg.cancel("s1")
noi = model_limits.subscription_blocked_hint(hit, now=NOW)
check("the hint gives the wait and keeps the provider's tz",
      "50 phút" in noi and "Asia/Bangkok" in noi and "không nói lúc nào" not in noi)

if fails:
    print(f"\nFAIL - test_limit_reset_clock: {len(fails)} failed: {fails}")
    sys.exit(1)
print("\nOK - test_limit_reset_clock: all pass")
