# -*- coding: utf-8 -*-
"""Paper trading (server/market_paper.py): rules, order book, report and historical simulation.

    python tests/run.py market_paper

No network. Rows are hand-made indicator dicts; the simulation runs on synthetic bars written to the archive.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import math
import os
import sys
import tempfile
import time

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-paper-"))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import market_paper as mp  # noqa: E402
import market_store as ms  # noqa: E402

_fails = []


def check(name, cond, detail=""):
    print(("ok   " if cond else "FAIL ") + name + (f"  ({detail})" if detail and not cond else ""))
    if not cond:
        _fails.append(name)


def row(sym, price=100.0, **kw):
    r = {"symbol": sym, "price": price, "sma20": price * 0.99, "sma50": price * 0.95, "sma200": price * 0.85, "score": 50,
         "rsi": 48, "atr_pct": 2.0, "chg_1d": 0.5, "chg_3m": 10, "value": 50e6, "sector": "bank"}
    r.update(kw)
    return r


ON = {"label": "risk_on", "score": 40, "bench_up": True}
NOW = 1_800_000_000.0

# ---------------------------------------------------------------- entries
st = {"cash": 1_000_000_000, "positions": {}, "recent_sells": {}}
res = mp.decide("vn", st, [row("AAA"), row("BBB", score=-10)], ON, NOW, True)
buys = [o for o in res["orders"] if o["side"] == "buy"]
check("buys a symbol that meets the rules", [o["symbol"] for o in buys] == ["AAA"], res["log"])
b = buys[0]
check("VN quantity is a multiple of 100", b["qty"] % 100 == 0 and b["qty"] > 0)
risk = b["qty"] * (b["price"] * 1.001 - b["stop"]) * 1000
check("risk per order is at most 1% of capital", 0 < risk <= 0.0105e9, risk)
check("position is at most 15% of capital", b["qty"] * b["price"] * 1000 <= 0.15e9 * 1.001)
check("stop sits 5-12% under the entry", 0.88 <= b["stop"] / 100 <= 0.95, b["stop"])
check("the order carries its analysis", b["analysis"]["score"] == 50 and b["analysis"]["regime"] == "risk_on" and "risk_amount" in b["analysis"])

res = mp.decide("vn", st, [row("AAA", price=110, sma20=100)], ON, NOW, True)
check("no chasing: an extended price waits on the watch list",
      not [o for o in res["orders"] if o["side"] == "buy"] and res["log"]["watch"][0]["why"] == "extended" and res["log"]["watch"][0]["zone"])
res = mp.decide("vn", st, [row("AAA", chg_1d=-0.4)], ON, NOW, True)
check("pullback style waits for a green day", res["log"]["watch"] and res["log"]["watch"][0]["why"] == "falling_today")
res = mp.decide("vn", st, [row("AAA")], {"label": "risk_off"}, NOW, True)
check("no new buys when the market is risk-off", not res["orders"] and res["log"]["skipped"][0]["why"] == "regime")
res = mp.decide("vn", st, [row("AAA")], {"label": "neutral", "bench_up": False}, NOW, True)
check("no new buys when the benchmark is under its MA50", not res["orders"] and res["log"]["skipped"][0]["why"] == "bench_down")
res = mp.decide("vn", st, [row("AAA", value=1e6)], ON, NOW, True)
check("thin VN stocks are skipped", not res["orders"])
res = mp.decide("vn", st, [row("AAA")], ON, NOW, False)
check("outside the decision window nothing is bought", not res["orders"])
many = [row(f"S{i:02d}", score=60 - i) for i in range(12)]
res = mp.decide("vn", st, many, ON, NOW, True)
check("at most 8 positions", len([o for o in res["orders"] if o["side"] == "buy"]) <= 8)
res = mp.decide("vn", {"cash": 1e9, "positions": {}, "recent_sells": {"AAA": NOW - 86400}}, [row("AAA")], ON, NOW, True)
check("a symbol sold in the last 5 days is not bought back", not res["orders"])

# ---------------------------------------------------------------- exits
pos = {"qty": 1000, "avg": 100.0, "opened": NOW - 10 * 86400, "stop": 93.0, "high": 100.0, "risk0": 7.0, "partial": False, "sellable": 0}
res = mp.decide("vn", {"cash": 0, "positions": {"AAA": dict(pos)}}, [row("AAA", price=92)], ON, NOW, False)
check("stop hit sells everything", res["orders"][0]["side"] == "sell" and res["orders"][0]["reason"] == "stop" and res["orders"][0]["qty"] == 1000)
res = mp.decide("vn", {"cash": 0, "positions": {"AAA": dict(pos, high=130.0)}}, [row("AAA", price=120, atr_pct=2.0)], ON, NOW, False)
check("trailing stop under the high locks a gain", res["orders"][0]["reason"] == "trail", res["orders"])
res = mp.decide("vn", {"cash": 0, "positions": {"AAA": dict(pos)}}, [row("AAA", price=122, sma50=100)], ON, NOW, False)
check("half the position goes at +3R", res["orders"][0]["reason"] == "take_profit" and res["orders"][0]["qty"] == 500)
res = mp.decide("vn", {"cash": 0, "positions": {"AAA": dict(pos)}}, [row("AAA", price=101, score=-30)], ON, NOW, False)
check("a broken trend closes the position", res["orders"][0]["reason"] == "trend")
res = mp.decide("vn", {"cash": 0, "positions": {"AAA": dict(pos, sellable=NOW + 3600)}}, [row("AAA", price=90)], ON, NOW, False)
check("T+2: unsettled shares are not sold", not [o for o in res["orders"] if o["side"] == "sell"] and res["log"]["skipped"][0]["why"] == "t_plus")
res = mp.decide("vn", {"cash": 0, "positions": {"AAA": dict(pos)}}, [row("AAA", price=105)], ON, NOW, False)
check("a rising position moves its high up", res["orders"] and res["orders"][0]["side"] == "update" and res["orders"][0]["high"] == 105)
check("T+2 settles two weekdays later", mp._add_weekdays(1794193200, 2) - 1794193200 >= 2 * 86400 - 12 * 3600)  # a Monday

# ---------------------------------------------------------------- world core
spy = row("SPY", price=500, group="etf", sma200=450)
res = mp.decide("world", {"cash": 20000, "positions": {}, "recent_sells": {}}, [spy, row("AAA", group="stock")], {"label": "risk_off"}, NOW, True)
core = [o for o in res["orders"] if o["side"] == "buy" and o["reason"] == "core"]
check("world core buys the index ETF even when stock picking is off", [o["symbol"] for o in core] == ["SPY"] and core[0]["qty"] == math.floor(20000 * 0.45 / 500.25))
res = mp.decide("world", {"cash": 0, "positions": {"SPY": dict(pos, avg=500, stop=441)}}, [dict(spy, price=430)], ON, NOW, False)
check("core leaves when the ETF breaks its MA200", res["orders"][0]["reason"] == "core_exit")
check("crypto quantities can be fractional", mp._lot("crypto", 0.1234567) == 0.123456)

# ---------------------------------------------------------------- order book, report
data = {"rows": [row("AAA"), row("BBB", score=-10)], "indices": [{"symbol": "VNINDEX", "price": 1700, "sma50": 1650}], "regime": {"label": "risk_on"}}
mp.start("vn", 1700)
mp.run("vn", data, now=NOW, force=True)
rep = mp.report("vn", data)
check("a forced run buys and records the trade", rep["started"] and len(rep["trades"]) == 1 and rep["positions"][0]["symbol"] == "AAA")
check("cash plus positions equals the starting capital minus fees", abs(rep["stats"]["equity"] - (1e9 - rep["stats"]["fees"] - rep["positions"][0]["qty"] * 100 * 1000 * 0.001)) < 1)
check("the decision log keeps what was considered", rep["log"] and rep["log"][0]["considered"])
data2 = {"rows": [row("AAA", price=90), row("BBB", score=-10)], "indices": [{"symbol": "VNINDEX", "price": 1600, "sma50": 1650}], "regime": {"label": "neutral"}}
try:
    mp.close_position("vn", "AAA", 90, now=NOW + 60)
    check("T+2 blocks a manual sell too", False)
except ValueError:
    check("T+2 blocks a manual sell too", True)
mp.run("vn", data2, now=NOW + 5 * 86400, force=True)
rep = mp.report("vn", data2)
sell = [t for t in rep["trades"] if t["side"] == "sell"]
check("the stop sells after settlement", sell and sell[0]["reason"] == "stop" and sell[0]["pnl"] < 0)
check("the loss stays near the planned risk (a gap through the stop can add to it)", -0.02e9 < sell[0]["pnl"] < 0, sell[0]["pnl"])
check("report: win rate, drawdown and benchmark", rep["stats"]["win_rate"] == 0 and rep["stats"]["max_drawdown"] <= 0
      and round(rep["stats"]["bench_return"], 2) == round((1600 / 1700 - 1) * 100, 2))
check("the sell keeps its R multiple and holding time", sell[0]["analysis"]["r_multiple"] < 0 and sell[0]["analysis"]["held_days"] >= 5)
mp.set_running("vn", False)
check("a paused account does not trade", mp.run("vn", data, now=NOW + 6 * 86400, force=True) == {})
mp.reset("vn")
check("reset clears the account", not mp.report("vn", data)["started"])

# ---------------------------------------------------------------- simulation on synthetic history
DAY = 86400
T0 = 1_760_000_000 // DAY * DAY + 7200


def series(n, drift, wave):
    c = [100 * math.exp(drift * i) * (1 + wave * math.sin(i / 6)) for i in range(n)]
    return {"t": [T0 + i * DAY for i in range(n)], "o": [x * 0.999 for x in c], "h": [x * 1.01 for x in c],
            "l": [x * 0.99 for x in c], "c": c, "v": [1e6] * n}


ms.upsert_bars("vn", {"UPA": series(320, 0.002, 0.04), "UPB": series(320, 0.0015, 0.05), "DNC": series(320, -0.002, 0.03),
                      "VNINDEX": series(320, 0.001, 0.01)})
sim = mp.simulate("vn", 120)
check("simulation runs on the archive", sim["ok"] and sim["days"] == 121, sim.get("error"))
check("simulation trades and reports against the benchmark", sim["trades"] > 0 and sim["bench_return"] is not None)
check("simulation never trades the index itself", all(t["symbol"] != "VNINDEX" for t in sim["last_trades"]))
check("simulation curve starts at the capital", abs(sim["curve"][0]["equity"] - 1e9) < 1)
check("an empty archive cannot be simulated", not mp.simulate("crypto", 120)["ok"])

if _fails:
    print(f"\n{len(_fails)} FAIL")
    sys.exit(1)
print("\nall ok")
