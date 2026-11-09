# -*- coding: utf-8 -*-
"""Markets background refresh, history archive, signal accuracy; Real estate quarterly drafts.

    python tests/run.py market_live

No network: sources are faked. Checks the tail merge, the section cache, live prices, the scheduler's clock, the
SQLite archive, the backtest and the accuracy grading, then the real-estate draft, validation and approval flow.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import importlib.util
import json
import math
import os
import sys
import tempfile
import time

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-market-live-"))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import market_data as md  # noqa: E402
import market_live as ml  # noqa: E402
import market_store as ms  # noqa: E402
import realestate_store as rs  # noqa: E402

_fails = []


def check(name, cond, detail=""):
    print(("ok   " if cond else "FAIL ") + name + (f"  ({detail})" if detail and not cond else ""))
    if not cond:
        _fails.append(name)


DAY = 86400
T0 = 1_760_000_000 // DAY * DAY + 7200  # 02:00 UTC, like DNSE


def bars(n=320, drift=0.002, start=100.0, t0=T0):
    c = [start * math.exp(drift * i) * (1 + 0.012 * ((-1) ** i)) for i in range(n)]
    return {"t": [t0 + i * DAY for i in range(n)], "o": list(c), "h": [x * 1.01 for x in c], "l": [x * 0.99 for x in c],
            "c": c, "v": [1000.0] * n}


# ---------------------------------------------------------------- tail merge
long = bars(10)
tail = {"t": long["t"][-2:] + [long["t"][-1] + DAY], "o": [1, 2, 3], "h": [1, 2, 3], "l": [1, 2, 3], "c": [11, 12, 13], "v": [5, 6, 7]}
m = md._merge(long, tail)
check("tail replaces the last bars and appends the new one", len(m["c"]) == 11 and m["c"][-3:] == [11, 12, 13])
check("history before the tail is untouched", m["c"][:8] == long["c"][:8])
check("merge without a tail keeps the history", md._merge(long, None) is long)
old_tail = {"t": [long["t"][0] - DAY], "o": [1], "h": [1], "l": [1], "c": [1], "v": [1]}
check("a tail bar older than the history is ignored", len(md._merge(long, old_tail)["c"]) == 10)

# ---------------------------------------------------------------- session clock
import datetime as dt  # noqa: E402


def at_vn(y, mo, d, h, mi):
    return dt.datetime(y, mo, d, h, mi, tzinfo=dt.timezone.utc).timestamp() - md.VN_TZ


check("VN session: Monday 10:00 trades", md.vn_in_session(at_vn(2026, 11, 9, 10, 0)))
check("VN session: lunch break is closed", not md.vn_in_session(at_vn(2026, 11, 9, 12, 0)))
check("VN session: 14:30 trades", md.vn_in_session(at_vn(2026, 11, 9, 14, 30)))
check("VN session: Saturday is closed", not md.vn_in_session(at_vn(2026, 11, 14, 10, 0)))
md.LAST_VIEW = 0
check("scheduler: VN every 60 s in session, 30 min outside",
      ml.interval("vn", at_vn(2026, 11, 9, 10, 0)) == 60 and ml.interval("vn", at_vn(2026, 11, 9, 20, 0)) == 1800)
md.LAST_VIEW = at_vn(2026, 11, 9, 10, 0)
check("scheduler: faster while someone watches", ml.interval("vn", at_vn(2026, 11, 9, 10, 0)) == 30)
md.LAST_VIEW = 0
check("tests keep the background loop off", ml.env_off() and not ml.enabled())
check("settings toggle", ml.save_settings({"background": False})["background"] is False and ml.settings()["background"] is False)
ml.save_settings({"background": True})

# ---------------------------------------------------------------- data layer with fake sources
CALLS = []


async def fake_get_json(url, params=None):
    CALLS.append(url)
    p = params or {}
    if "entrade" in url:
        days = (p["to"] - p["from"]) // DAY
        b = bars(drift=0.003 if p["symbol"] in ("FPT", "VNINDEX") else -0.002)
        k = min(len(b["c"]), days if days < 30 else len(b["c"]))
        return {key: b[key][-k:] for key in ("t", "o", "h", "l", "c", "v")}
    if "yahoo" in url:
        b = bars(t0=T0 + 11 * 3600)
        n = 5 if p.get("range") == "5d" else len(b["c"])
        return {"chart": {"result": [{"meta": {"currency": "USD", "gmtoffset": -18000}, "timestamp": b["t"][-n:],
                                       "indicators": {"quote": [{k: b[x][-n:] for k, x in (("open", "o"), ("high", "h"), ("low", "l"), ("close", "c"), ("volume", "v"))}]}}]}}
    if "exchangeInfo" in url:
        return {"symbols": [{"baseAsset": "BTC", "quoteAsset": "USDT", "status": "TRADING"}]}
    if "ticker/24hr" in url:
        return [{"symbol": "BTCUSDT", "lastPrice": "70000", "openPrice": "68000"}]
    if "klines" in url:
        b = bars(start=50000.0, t0=T0 - 7200)
        n = int(p.get("limit") or 400)
        return [[t * 1000, o, h, low, c, 0, 0, v] for t, o, h, low, c, v in list(zip(b["t"], b["o"], b["h"], b["l"], b["c"], b["v"]))[-n:]]
    if "coins/markets" in url:
        return [{"id": "bitcoin", "symbol": "btc", "name": "Bitcoin", "current_price": 69000, "market_cap": 1e12, "total_volume": 1e10,
                 "market_cap_rank": 1, "price_change_percentage_24h_in_currency": 1.0, "price_change_percentage_7d_in_currency": 3.0,
                 "price_change_percentage_30d_in_currency": 9.0, "sparkline_in_7d": {"price": [69000.0] * 168}}]
    if url.endswith("/global"):
        return {"data": {}}
    if "trending" in url:
        return {"coins": []}
    if "alternative.me" in url:
        return {"data": []}
    raise AssertionError("unexpected " + url)


md._get_json = fake_get_json
md.VN_STOCKS = {"FPT": ("tech", "HOSE"), "HPG": ("materials", "HOSE"), "VNM": ("consumer", "HOSE"), "SSI": ("broker", "HOSE")}
md.VN_INDICES = [("VNINDEX", "VN-Index")]
md.WORLD = {"^GSPC": ("S&P 500", "index", "us"), "AAPL": ("Apple", "stock", "us"), "MSFT": ("Microsoft", "stock", "us")}


async def run():
    d = await md.refresh_section("vn")
    check("section has rows with a bar date", len(d["rows"]) == 4 and all(r.get("bar_date") for r in d["rows"]))
    check("private series never reach the page", "_series" not in d and "_meta" not in d)
    n = len(CALLS)
    d2 = await md.section("vn")
    check("a fresh section is served from the cache", len(CALLS) == n and d2 is d)
    check("the section survives a restart (disk copy)", md._section_file("vn").exists())
    md._SECTION.clear()
    d3 = await md.section("vn")
    check("disk copy is used after a restart", len(CALLS) == n and d3["rows"][0]["symbol"] == d["rows"][0]["symbol"])
    md._MEM.pop("vnt_FPT", None)
    await md.vn_bars("FPT")
    check("only the short tail is refetched once the history is cached", CALLS[-1].endswith("/stock") and len(CALLS) == n + 1)

    w = await md.refresh_section("world")
    check("Yahoo bars keep the exchange offset", w["rows"][0]["bar_date"] and md.yahoo_bars)
    c = await md.refresh_section("crypto")
    btc = c["rows"][0]
    check("crypto rows know their Binance pair", btc.get("pair") == "BTCUSDT")
    lv = await md.live(["crypto", "vn"])
    check("live crypto price comes from Binance", lv["prices"]["crypto"]["bitcoin"][0] == 70000.0
          and abs(lv["prices"]["crypto"]["bitcoin"][1] - 2.94) < 0.01)
    check("live VN prices come from the section", "FPT" in lv["prices"]["vn"] and "VNINDEX" in lv["prices"]["vn"])
    check("a live poll marks the page as watched", time.time() - md.LAST_VIEW < 5)

    # archive hook runs in a thread; wait for it
    for _ in range(200):
        if not ml._PENDING:
            break
        await asyncio.sleep(0.05)
    st = ms.stats()
    check("bars archived for every market", all(st["bars"].get(k, 0) > 300 for k in ("vn", "world", "crypto")), st)
    check("60 sessions backfilled per market", st["snapshots"].get("vn", 0) >= 55, st)
    check("backtest runs once per day", ms.meta_get("bt_vn") == ml._today_utc())
    a = ms.accuracy("vn")
    check("accuracy grades the backfilled sessions", a["graded"] > 50 and a["days"] >= 50, a.get("graded"))
    check("uptrend stock shows up as a potential pick that rose", a["potential"]["n"] > 0 and a["potential"]["avg"] > 0, a.get("potential"))
    check("falling stocks graded as risk picks that fell", a["risk"]["n"] > 0 and a["risk"]["avg"] < 0, a.get("risk"))
    check("accuracy has a per-day series and score buckets", len(a["series"]) == a["days"] and len(a["buckets"]) == 5)
    check("an empty market grades nothing", ms.accuracy("nope")["graded"] == 0)

    # live snapshot wins over the backfill and is written once per closed session
    snap = "2099-01-01"
    rows = [dict(r, bar_date=r["bar_date"]) for r in d["rows"]]
    ms.save_snapshot("vn", snap, rows, md._pick(rows, "vn"), source="live")
    check("live snapshot stored", ms.has_snapshot("vn", snap))
    # snapshot date: VN closed after 15:05, still open at 10:00
    data = {"bench": "VNINDEX", "indices": [{"symbol": "VNINDEX", "bar_date": "2026-11-09"}], "rows": []}
    check("no VN snapshot while the session trades", ml.snapshot_date("vn", data, at_vn(2026, 11, 9, 10, 0)) == "")
    check("VN snapshot after the close", ml.snapshot_date("vn", data, at_vn(2026, 11, 9, 15, 30)) == "2026-11-09")

asyncio.run(run())

# a ticker Binance cannot parse must not sink the whole batch
_seen = {}


async def _capture(url, params=None):
    _seen.update(params or {})
    return []
md._get_json = _capture
md._MEM.pop("bn_live", None)
asyncio.run(md.binance_live(["BTCUSDT", "币安USDT", "ETHUSDT"]))
check("non-ASCII Binance pairs are left out of the live batch", json.loads(_seen.get("symbols", "[]")) == ["BTCUSDT", "ETHUSDT"], _seen)

# ---------------------------------------------------------------- real estate drafts
data, source, _ = rs.current()
check("bundled data is the default", source == "bundled" and len(data["regions"]) >= 3)
rid = data["regions"][0]["id"]
res = rs.set_region(rid, {"as_of": "Q4/2026"}, note="test", updated="2027-01")
check("a partial region update becomes a draft", res["ok"] and res["draft"]["changed"] == [rid])
check("the live data is unchanged until approval", rs.current()[1] == "bundled")
bad = rs.set_region(rid, {"kpis": "not a list"})
check("a field with the wrong type is refused", not bad["ok"] and any("kpis" in e for e in bad["errors"]), bad)
bad2 = rs.set_region(rid, "{not json")
check("invalid JSON is refused", not bad2["ok"])
check("draft keeps the other fields", rs.draft()["data"]["regions"][0].get("kpis") == data["regions"][0].get("kpis"))
ok = rs.approve()
cur, source, _ = rs.current()
check("approve publishes the draft", ok["ok"] and source == "updated" and cur["regions"][0]["as_of"] == "Q4/2026" and cur["updated"] == "2027-01")
check("approve keeps the previous version", any(h.startswith("data-") for h in rs.history()))
check("no draft left after approval", rs.draft() is None and not rs.approve()["ok"])
rs.set_region(rid, {"as_of": "Q1/2027"})
rs.discard()
check("discard drops the draft", rs.draft() is None and rs.current()[0]["regions"][0]["as_of"] == "Q4/2026")
check("summary text names regions and sources", rid in rs.summary(cur) and "nguồn" in rs.summary(cur))

# plugin
spec = importlib.util.spec_from_file_location("javis_re_plugin", os.path.join(ROOT, "system", "plugins", "javis-realestate", "plugin.py"))
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
tools = {}


class Ctx:
    def register_tool(self, **kw):
        tools[kw["name"]] = kw


mod.register(Ctx())
check("read tool is readonly, draft tool is safe, no approve tool",
      tools["javis_realestate"]["min_mode"] == "readonly" and tools["javis_realestate_draft"]["min_mode"] == "safe" and len(tools) == 2)


async def plug():
    t = await tools["javis_realestate"]["handler"]({"op": "region", "region": rid, "fields": ["as_of", "id"]}, {})
    check("region read with selected fields", json.loads(t) == {"as_of": "Q4/2026", "id": rid}, t[:100])
    t = await tools["javis_realestate_draft"]["handler"]({"op": "set", "region": rid, "fields": {"as_of": "Q1/2027"}, "note": "n"}, {})
    check("draft tool writes a draft and says it is not published", "CHƯA" in t and rs.draft() is not None, t)
    t = await tools["javis_realestate_draft"]["handler"]({"op": "set", "region": rid, "fields": {"kpis": 5}}, {})
    check("draft tool reports a breaking change", t.startswith("ERROR"))
    t = await tools["javis_realestate"]["handler"]({"op": "summary"}, {})
    check("summary mentions the waiting draft", "bản nháp" in t)

asyncio.run(plug())

# routes
import main  # noqa: E402
from _paths import moi_duong_dan  # noqa: E402
paths = set(moi_duong_dan(main.app))
for p in ("/market/live", "/market/accuracy", "/market/settings", "/realestate/data", "/realestate/approve", "/realestate/discard"):
    check("route " + p, p in paths)

if _fails:
    print(f"\n{len(_fails)} FAIL")
    sys.exit(1)
print("\nall ok")
