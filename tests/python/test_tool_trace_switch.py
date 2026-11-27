"""One switch hides the tool trail on every owner chat channel (issue #1893).

    python tests/run.py tool_trace_switch      (no network)

Checks:
  1. `with_trace` adds the trail when on and leaves the answer alone when off; a broken source keeps it on;
  2. main.py points the switch at settings.chat.tool_trace (default on) and the settings route saves it;
  3. every owner channel that drew a trail now goes through the switch, Telegram and Slack send no status
     message when it is off;
  4. the Channels page has the switch and both dictionaries have its words.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import json
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import bot_gateway  # noqa: E402

_fails = []


def check(name, cond, detail=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(detail) + "]") if detail and not cond else ""))
    if not cond:
        _fails.append(name)


# ---- 1. the helper -------------------------------------------------------------------------------------
bot_gateway.set_trace_source(lambda: True)
on = bot_gateway.with_trace("Xong rồi", ["javis_search_tools"], 31)
check("on: the trail goes under the answer", on.startswith("Xong rồi\n\n⚙ ") and on.endswith("31s"), on)
check("on, empty answer: the trail alone", bot_gateway.with_trace("", [], 2) == "✓ Trả lời trực tiếp · 2s")
bot_gateway.set_trace_source(lambda: False)
check("off: the answer alone", bot_gateway.with_trace("Xong rồi", ["x"], 31) == "Xong rồi")
check("off: trace_wanted says so", bot_gateway.trace_wanted() is False)


def _broken():
    raise RuntimeError("settings unreadable")


bot_gateway.set_trace_source(_broken)
check("a broken source keeps the trail", bot_gateway.trace_wanted() is True)
bot_gateway.set_trace_source(None)
check("no source: on", bot_gateway.trace_wanted() is True)

# ---- 2. wiring -----------------------------------------------------------------------------------------
main_src = (SERVER / "main.py").read_text(encoding="utf-8")
check("main.py wires the switch", "bot_gateway.set_trace_source(tool_trace_on)" in main_src)
check("default on, only an explicit false turns it off",
      '(s.get("chat") or {}).get("tool_trace", True) is not False' in main_src)
check("the settings route saves it", 'cfg.setdefault("chat", {})["tool_trace"] = bool(patch["tool_trace"])' in main_src)

# ---- 3. every channel ----------------------------------------------------------------------------------
for name in ("messenger_bot", "wechat_bot", "whatsapp_bot", "threads_bot", "zalo_oa_bot", "zalo_bot"):
    src = (SERVER / f"{name}.py").read_text(encoding="utf-8")
    check(f"{name}: the trail goes through with_trace", "with_trace(reply, tools" in src and "dong_vet(" not in src)
for name in ("discord_bot", "lark_bot"):
    src = (SERVER / f"{name}.py").read_text(encoding="utf-8")
    check(f"{name}: the trail asks the switch", "not self.giau_trang_thai and trace_wanted()" in src)
tg = (SERVER / "telegram_bot.py").read_text(encoding="utf-8")
check("telegram: no status message when off", "quiet_status = self.giau_trang_thai or not trace_wanted()" in tg)
sl = (SERVER / "slack_bot.py").read_text(encoding="utf-8")
check("slack: no status message when off", "if not self.giau_trang_thai and trace_wanted():" in sl)

# ---- 4. dashboard --------------------------------------------------------------------------------------
js = (ROOT / "dashboard" / "console.js").read_text(encoding="utf-8")
check("Channels page: the switch is drawn and saved", 'id="achTrace"' in js and 'saveSetting("chat", { tool_trace: c.checked })' in js)
for lang in ("vi", "en"):
    d = json.loads((ROOT / "dashboard" / "i18n" / f"{lang}.json").read_text(encoding="utf-8"))
    check(f"i18n {lang}: the switch's words exist",
          all(d.get(k) for k in ("ach.tool_trace", "ach.tool_trace_h", "ach.tool_trace_saved", "ach.tool_trace_fail")))

check("no em dash in this file", chr(0x2014) not in open(__file__, encoding="utf-8").read())

if _fails:
    print(f"\n{len(_fails)} FAIL")
    sys.exit(1)
print("\nPASS")
