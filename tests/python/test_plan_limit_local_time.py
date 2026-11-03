"""Plan-limit notice "You've hit your 5-hour limit · resets 5:20pm (UTC)" (PR #961, @hwangrin).

    python tests/run.py plan_limit_local_time      (no network)

Before 0.444.0 this wording matched no pattern, so the chat showed the raw UTC clock with no
reset card and no auto re-run. The reset card already converts reset_epoch to the viewer's local
time, so recognising the sentence is enough there. The server hint now formats the time in the
owner's configured time zone (localefmt.tz) instead of the OS clock (a VPS usually runs UTC), and
adds the date when the reset falls on another day.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401  - puts server/ on sys.path
import os
import sys
import tempfile
from datetime import datetime, timezone

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-limit-tz-"))
os.environ["TZ"] = "UTC"   # the VPS case: OS clock on UTC, owner in Vietnam
if hasattr(__import__("time"), "tzset"):
    __import__("time").tzset()

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import limit_learner  # noqa: E402
import localefmt      # noqa: E402
import model_limits   # noqa: E402

fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (f"  [{extra}]" if extra and not cond else ""))
    if not cond:
        fails.append(name)


def utc(*a) -> float:
    return datetime(*a, tzinfo=timezone.utc).timestamp()


NOW = utc(2026, 11, 1, 15, 0)   # 22:00 in Vietnam
MSG = "You've hit your 5-hour limit · resets 5:20pm (UTC)"

lim = limit_learner.parse_subscription_limit(MSG, engine_hint="claude-code", now=NOW)
check("5-hour 'hit your' notice is recognised", lim is not None)
check("engine comes from the caller's hint", lim is not None and lim.engine == "claude-code", repr(lim))
check("scope is the 5-hour window", lim is not None and lim.scope == "5 giờ", repr(lim))
check("reset epoch is 17:20 UTC the same day",
      lim is not None and abs(lim.reset_epoch - utc(2026, 11, 1, 17, 20)) < 1, repr(lim))

check("ordinary prose about limits is not a plan limit",
      limit_learner.parse_subscription_limit("The 5-hour window is a soft limit for most users.",
                                             engine_hint="codex", now=NOW) is None)

# Owner in Vietnam (default tz), server clock on UTC: 17:20 UTC is 00:20 the next day.
localefmt._cau_hinh = lambda: {"tz": "Asia/Ho_Chi_Minh"}
hint = model_limits.subscription_blocked_hint(lim, now=NOW)
check("hint uses the configured time zone and the next-day date", "00:20 ngày 02/11" in hint, hint)
check("hint keeps the provider's own words", "5:20pm (UTC)" in hint, hint)

# Same day in the configured zone: no date.
localefmt._cau_hinh = lambda: {"tz": "UTC"}
hint = model_limits.subscription_blocked_hint(lim, now=NOW)
check("same-day reset shows the clock only", "tầm 17:20," in hint or "tầm 17:20)" in hint, hint)

print()
if fails:
    print(f"FAIL: {len(fails)} check(s)")
    sys.exit(1)
print("All checks passed.")
