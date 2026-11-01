"""Subscription 5-hour limit notice: parse the real provider wording and use Javis time zone.

No network, live keys, temp directories or configuration writes.
    python tests/python/test_plan_limit_local_time.py
"""
from _paths import SERVER  # noqa: F401
from datetime import datetime, timezone, timedelta
import limit_learner
import localefmt
import model_limits

notice = "You've hit your 5-hour limit · resets 5:20pm (UTC)"
now = datetime(2026, 11, 1, 15, 10, tzinfo=timezone.utc).timestamp()
expected = datetime(2026, 11, 1, 17, 20, tzinfo=timezone.utc).timestamp()

hit = limit_learner.parse_subscription_limit(notice, engine_hint="codex", now=now)
assert hit is not None, "provider wording must be recognized as plan-limit error"
assert hit.engine == "codex" and hit.scope == "5 giờ", hit
assert hit.reset_epoch == expected, hit
assert "5:20pm (UTC)" in hit.reset_text, hit
assert limit_learner.subscription_dominates(notice), "short CLI notice must be classified"

# Even on a server whose OS clock is UTC, the hint follows the owner's timezone
# setting. Stub only the time-zone accessor; do not change shared system settings.
original = localefmt.tz
localefmt.tz = lambda: timezone(timedelta(hours=7))
try:
    shown = model_limits.subscription_blocked_hint(hit, now=now)
    assert "00:20 ngày 02/11" in shown, shown
    assert "5:20pm (UTC)" in shown, "keep provider's raw clock as diagnostic evidence"
finally:
    localefmt.tz = original

assert limit_learner.parse_subscription_limit("The project has a 5-hour limit", now=now) is None
print("PASS subscription reset: 17:20 UTC = 00:20 next day at UTC+7")
