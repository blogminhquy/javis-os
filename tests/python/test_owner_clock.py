"""Clock times a person reads follow the timezone in Settings, never the server clock (2026-11-09).

    python tests/run.py owner_clock      (no network)

The owner saw a security notice "09/11 14:47" in the bell and on the "System notice" card in Javis Core, while it was
21:47 in Vietnam. The VPS runs on UTC and both texts used `datetime.fromtimestamp(ts)` with no zone, so they printed
the server's clock. Settings has a timezone (`locale.tz`) for exactly this.

What this file pins:
  1. `localefmt.format_ts` prints an epoch in the configured timezone, and follows the setting when it changes.
  2. The security alert and the Javis Core notice card print the owner's time on a UTC server.
  3. The webhook event prompt and the Javis Gate chat reader do the same.
  4. No server code calls `fromtimestamp(x)` without a zone, except as the fallback of an `except` block or on a
     line marked "# server clock on purpose".
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import ast
import os
import sys
import tempfile
import time
from datetime import datetime, timezone

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-owner-clock-")
# Act like a VPS: the process clock is UTC. Windows has no tzset; the checks still hold there because the owner's
# timezone is applied explicitly, only the "server is on UTC" part is not simulated.
os.environ["TZ"] = "UTC"
if hasattr(time, "tzset"):
    time.tzset()
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import localefmt  # noqa: E402

_fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(extra)[:300] + "]") if extra and not cond else ""))
    if not cond:
        _fails.append(name)


_zone = {"tz": "Asia/Ho_Chi_Minh"}
localefmt._cau_hinh = lambda: dict(_zone)

# 14:47 UTC on 9 November 2026 = 21:47 in Vietnam = 09:47 in New York (EST, DST ended 1 November).
TS = datetime(2026, 11, 9, 14, 47, tzinfo=timezone.utc).timestamp()

# ---- 1. the helper ----
check("format_ts prints the owner's time, not UTC", localefmt.format_ts(TS, "%d/%m %H:%M") == "09/11 21:47",
      localefmt.format_ts(TS, "%d/%m %H:%M"))
_zone["tz"] = "America/New_York"
check("it follows the timezone in Settings when it changes", localefmt.format_ts(TS, "%H:%M") == "09:47",
      localefmt.format_ts(TS, "%H:%M"))
_zone["tz"] = "Asia/Ho_Chi_Minh"
check("a string timestamp works too", localefmt.format_ts(str(TS), "%H:%M") == "21:47")
check("an empty or broken value gives an empty string, never an exception",
      localefmt.format_ts(None, "%H:%M") == "" and localefmt.format_ts("x", "%H:%M") == ""
      and localefmt.format_ts(1e30, "%H:%M") == "")

# ---- 2. the security alert and the notice card ----
import main  # noqa: E402

ev = {"event": "login_new_network", "ts": TS, "ip": "172.71.210.136",
      "ua": "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) Safari/604.1", "detail": "password+2fa"}
txt = main._security_alert_text(ev)
check("security alert: the owner's time (21:47), not the server's (14:47)", "09/11 21:47" in txt and "14:47" not in txt,
      txt)
card = main._cite_text("inbox", {"id": "n1", "ts": TS, "title": "[Bảo mật] Đăng nhập", "body": "chi tiết",
                                 "kind": "system", "label": "Thông báo hệ thống"}, "brain")
check("notice card in Javis Core: the owner's date and time", "09/11/2026 21:47" in card and "14:47" not in card, card)
news = main._cite_text("news", {"id": "release:1", "published_at": "2026-11-09", "title": "v1", "summary": "s"}, "brain")
check("a news item keeps its published date as written", "2026-11-09" in news, news)

# ---- 3. webhook prompt and the chat reader ----
import chat_bridge  # noqa: E402
import webhook_triggers  # noqa: E402

prompt = webhook_triggers.event_prompt({"name": "Đơn mới"}, "{}", TS)
check("webhook event prompt: the time it arrived on the owner's clock", "lúc 2026-11-09 21:47" in prompt, prompt[:200])
check("chat reader (Javis Gate): message times on the owner's clock", chat_bridge._gio(TS) == "2026-11-09 21:47",
      chat_bridge._gio(TS))
check("chat reader: a missing time stays empty", chat_bridge._gio(None) == "")

# ---- 4. guard: no zone-less fromtimestamp left in server code ----


def _inside_except(node, parents) -> bool:
    p = parents.get(node)
    while p is not None:
        if isinstance(p, ast.ExceptHandler):
            return True
        p = parents.get(p)
    return False


# A line may opt out with the comment "# server clock on purpose" when the machine clock is the right one, e.g.
# limit_learner reads a reset time a CLI printed in the machine's local time. Text a person reads never qualifies.
OPT_OUT = "# server clock on purpose"
offenders = []
for path in sorted(SERVER.rglob("*.py")):
    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
    except (SyntaxError, UnicodeDecodeError):
        continue
    lines = source.splitlines()
    parents = {child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr == "fromtimestamp" and len(node.args) == 1
                and not any(k.arg == "tz" for k in node.keywords) and not _inside_except(node, parents)
                and OPT_OUT not in lines[node.lineno - 1]):
            offenders.append(f"{path.relative_to(ROOT)}:{node.lineno}")
check("no server code calls fromtimestamp(x) without a zone (use localefmt.format_ts or pass localefmt.tz())",
      not offenders, offenders)

print()
if _fails:
    print(f"{len(_fails)} FAILED: {_fails}")
    sys.exit(1)
print("all passed")
