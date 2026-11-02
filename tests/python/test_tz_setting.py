"""The timezone is a real setting (0.443.0), not something only the datetime-vn plugin knows about.

    python tests/run.py tz_setting

The owner (2026-11-02): the timezone only showed through a plugin. It now has a picker in Settings and in the first-run
setup, the server refuses names it cannot load (localefmt used to fall back to UTC+7 in silence), and the clock line in
every prompt names yesterday and tomorrow in that timezone so "revenue yesterday" asks the MCP for the right day.
"""
from _paths import ROOT, SERVER  # noqa: F401
import asyncio
import json
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-tz-")

import config as cfgmod  # noqa: E402
import context_compiler as cc  # noqa: E402
import localefmt  # noqa: E402
import main  # noqa: E402

_fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)


def save(patch):
    r = asyncio.run(main.settings_set("locale", json.dumps(patch)))
    if hasattr(r, "body"):
        return r.status_code, json.loads(r.body)
    return 200, r


# ---- 1. valid_tz ----
check("a real IANA name passes", localefmt.valid_tz("America/New_York") == "America/New_York")
check("UTC passes", localefmt.valid_tz("UTC") == "UTC")
check("surrounding spaces are trimmed", localefmt.valid_tz("  Asia/Tokyo ") == "Asia/Tokyo")
check("a misspelt name is refused", localefmt.valid_tz("Asia/Hanoi_City") == "")
check("a path is refused", localefmt.valid_tz("../../etc/passwd") == "")
check("empty is refused", localefmt.valid_tz("") == "")

# ---- 2. Saving through /settings ----
code, body = save({"tz": "America/New_York"})
check("a valid timezone saves", code == 200 and body.get("ok") is not False)
check("and is stored", cfgmod.read_settings()["locale"]["tz"] == "America/New_York")
check("localefmt follows at once", localefmt.ten_tz() == "America/New_York")
check("/settings reports it to the dashboard", main.settings_get()["locale_fmt"]["tz"] == "America/New_York")

code, body = save({"tz": "Mars/Olympus_Mons"})
check("an unknown timezone is refused with 400", code == 400 and body.get("ok") is False)
check("the refusal names the timezone", "Mars/Olympus_Mons" in (body.get("error") or ""))
check("and the saved timezone is unchanged", cfgmod.read_settings()["locale"]["tz"] == "America/New_York")

code, body = save({"tz": ""})
check("empty resets to the default", code == 200 and cfgmod.read_settings()["locale"]["tz"] == "Asia/Ho_Chi_Minh")

# ---- 3. The clock line uses the saved timezone, with yesterday and tomorrow ----
save({"tz": "America/Los_Angeles"})
# 2026-11-02 03:30 UTC is still 1 November in Los Angeles: the day a report must use is the owner's, not UTC's.
moc = datetime(2026, 11, 2, 3, 30, tzinfo=timezone.utc).astimezone(localefmt.tz())
line = cc.dong_ho(moc)
check("clock shows the local date, not the UTC one", "01/11/2026" in line)
check("clock names yesterday", "31/10/2026" in line)
check("clock names tomorrow", "02/11/2026" in line)
check("clock names the timezone", "America/Los_Angeles" in line and "UTC-8" in line)
check("clock says report ranges follow this timezone", "MCP" in line)
check("no em dash in the clock line", "—" not in line and "–" not in line)
en = cc.dong_ho(moc, lang="en")
check("English clock names yesterday and tomorrow", "Yesterday 31/10/2026" in en and "tomorrow 02/11/2026" in en)

real = cc.dong_ho()
today_la = datetime.now(ZoneInfo("America/Los_Angeles"))
check("unpinned clock uses the saved timezone", today_la.strftime("%d/%m/%Y") in real
      or (today_la + timedelta(minutes=1)).strftime("%d/%m/%Y") in real)

# ---- 4. Local MCP servers get the owner's timezone as TZ ----
import mcp_client  # noqa: E402

if os.name != "nt":
    check("a local MCP gets TZ from Settings", mcp_client._owner_tz_env({}) == {"TZ": "America/Los_Angeles"})
    check("a connector's own TZ wins", mcp_client._owner_tz_env({"TZ": "UTC"}) == {})
    _old_ten_tz = localefmt.ten_tz
    try:
        localefmt.ten_tz = lambda: "Not/A_Zone"
        check("a broken setting adds no TZ at all", mcp_client._owner_tz_env({}) == {})
    finally:
        localefmt.ten_tz = _old_ten_tz

# ---- 5. The dashboard has the pickers ----
html = (ROOT / "dashboard" / "index.html").read_text(encoding="utf-8")
app = (ROOT / "dashboard" / "app.js").read_text(encoding="utf-8")
con = (ROOT / "dashboard" / "console.js").read_text(encoding="utf-8")
check("index.html loads tz-picker.js before app.js",
      0 < html.find("/static/tz-picker.js") < html.find("/static/app.js"))
check("the first-run setup has a timezone picker", 'id="wzTz"' in html)
check("the setup saves it to locale.tz", 'section: "locale"' in app and "wzTz" in app)
check("Settings has a timezone picker that saves locale.tz",
      'id="vpTz"' in con and 'saveSetting("locale", { tz:' in con)
for lang in ("vi", "en"):
    d = json.loads((ROOT / "dashboard" / "i18n" / f"{lang}.json").read_text(encoding="utf-8"))
    check(f"{lang}.json has the timezone strings",
          all(k in d for k in ("settings.tz.title", "settings.tz.hint", "settings.tz.saved", "tz.now_there",
                               "tz.group_suggested", "tz.group_all", "wz.s4", "wz.tz_note")))

print()
if _fails:
    print(f"FAILED {len(_fails)}: {_fails}")
    sys.exit(1)
print("OK - test_tz_setting: all pass")
