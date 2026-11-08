"""Dashboard-only dictionaries (a community `dashboard/i18n/xx.json`) are offered in the language pickers (0.99.0).

    python tests/run.py tu_dien_chi_giao_dien      (NO network)

German came in as just `dashboard/i18n/de.json` (PR #618 by @sirschnake) and was removed on 2026-11-08 (owner: English and
Vietnamese only). The mechanism stays and is tested with temporary files below. The server
registry only speaks vi and en, so:
  1. GET /settings keeps `lang_list` = what the server speaks (reply language, voice), and adds `ui_lang_list` = that plus
     every dashboard dictionary the server does not know, so the pickers can offer "Deutsch";
  2. a broken file or an odd file name is never offered;
  3. an unknown `ui_lang` saved on the server still turns into the registry default, which is why the dashboard saves
     English for a dashboard-only language (pinned in tests/js/test_i18n_theo_trinh_duyet.js).
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import json
import os
import sys
import tempfile
from pathlib import Path

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-tudien-")
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import lang_registry as L  # noqa: E402

_fails = []


def check(name, cond, detail=""):
    print(("ok   " if cond else "FAIL ") + name + ("" if cond else f"  [{str(detail)[:300]}]"))
    if not cond:
        _fails.append(name)


# ---- 1. the real dictionaries in the repo ----
real = L.dashboard_only_languages(ROOT / "dashboard" / "i18n")
# Owner, 2026-11-08: the interface ships in English and Vietnamese only, German was removed.
check("no dashboard-only dictionary ships (interface is English and Vietnamese only)", real == [], real)
check("de.json is gone", not (ROOT / "dashboard" / "i18n" / "de.json").exists())

# ---- 2. odd files are never offered ----
d = Path(tempfile.mkdtemp(prefix="javis-i18n-"))
(d / "fr.json").write_text(json.dumps({"_meta.name": "Français", "nav.x": "y"}), encoding="utf-8")
(d / "pt-br.json").write_text(json.dumps({"nav.x": "y"}), encoding="utf-8")
(d / "ja.json").write_text("{ broken", encoding="utf-8")
(d / "x_evil.json").write_text("{}", encoding="utf-8")
(d / "en.json").write_text("{}", encoding="utf-8")
(d / "index.js").write_text("", encoding="utf-8")
got = {x["ma"]: x["ten"] for x in L.dashboard_only_languages(d)}
check("valid files offered, a file without _meta.name shows its code",
      got.get("fr") == "Français" and got.get("pt-br") == "pt-br", got)
check("a broken JSON file, an odd file name and the server's own languages are not offered",
      "ja" not in got and "x_evil" not in got and "en" not in got, got)
check("a missing folder is an empty list, not a crash", L.dashboard_only_languages(d / "nope") == [])

# ---- 3. unknown ui_lang on the server still becomes the registry default ----
check("the server normalises an unknown code to its default (so the dashboard must send English)",
      L.chuan_hoa("de") == "" and L.MAC_DINH == "vi")

# ---- 4. GET /settings ----
import main  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

r = TestClient(main.app, base_url="http://127.0.0.1:7777").get("/settings")
s = r.json()
check(f"GET /settings answers ({r.status_code})", r.status_code == 200)
check("lang_list stays the languages the server speaks", [x["ma"] for x in s.get("lang_list", [])] == list(L.LANGS),
      s.get("lang_list"))
check("ui_lang_list = lang_list (no dashboard-only language)", [x["ma"] for x in s.get("ui_lang_list", [])] == list(L.LANGS),
      s.get("ui_lang_list"))

for f in (SERVER / "lang_registry.py", Path(__file__)):
    check(f"no em dash in {f.name}", chr(0x2014) not in f.read_text(encoding="utf-8"))

print()
if _fails:
    print(f"ĐỎ {len(_fails)} mục: " + ", ".join(_fails))
    sys.exit(1)
print("Tất cả xanh.")
