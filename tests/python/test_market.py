# -*- coding: utf-8 -*-
"""Markets page: indicator maths, the data layer and the javis_market plugin.

    python tests/run.py market

No network: every fetch is replaced by synthetic price series, so this checks Javis's own code (indicators, scores,
regime, outlook lists, cache fallback, watchlist, routes, tool text), not whether DNSE, Yahoo or CoinGecko are up.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import importlib.util
import json
import math
import os
import sys
import tempfile

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-market-test-"))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import market_indicators as mi  # noqa: E402
import market_data as md  # noqa: E402

_fails = []


def check(name, cond, detail=""):
    print(("ok   " if cond else "FAIL ") + name + (f"  ({detail})" if detail and not cond else ""))
    if not cond:
        _fails.append(name)


def series(n=300, start=100.0, drift=0.001, wave=0.02, vol=1000.0, last_vol=None):
    t0 = 1_700_000_000
    c = [start * math.exp(drift * i) * (1 + wave * math.sin(i / 7)) for i in range(n)]
    v = [vol] * n
    if last_vol is not None:
        v[-1] = last_vol
    return {"t": [t0 + i * 86400 for i in range(n)], "o": [x * 0.998 for x in c], "h": [x * 1.01 for x in c],
            "l": [x * 0.99 for x in c], "c": c, "v": v}


def healthy_uptrend(n=300):
    """A rise with alternating up and down days: trend score high, RSI near 55 (not overbought)."""
    b = series(n=n)
    b["c"] = [100 * math.exp(0.003 * i) * (1 + 0.012 * ((-1) ** i)) for i in range(n)]
    b["o"], b["h"], b["l"] = list(b["c"]), [x * 1.01 for x in b["c"]], [x * 0.99 for x in b["c"]]
    return b


# ---------------------------------------------------------------- pure maths
check("sma of 1..5 over 3", mi.sma([1, 2, 3, 4, 5], 3) == [None, None, 2.0, 3.0, 4.0])
e = mi.ema([1.0] * 30, 10)
check("ema of a flat series is flat", all(abs(x - 1) < 1e-12 for x in e[9:]) and e[8] is None)
r_up = mi.rsi(list(range(1, 40)), 14)
check("rsi of a straight rise is 100", r_up[-1] == 100.0)
r_dn = mi.rsi(list(range(40, 1, -1)), 14)
check("rsi of a straight fall is 0", abs(r_dn[-1]) < 1e-9)
line, sig, hist = mi.macd([float(i) for i in range(1, 80)])
check("macd positive on a steady rise", line[-1] > 0 and sig[-1] is not None and hist[-1] is not None)
mid, up, lo, w = mi.bollinger([10.0] * 25)
check("bollinger width is 0 on a flat series", up[-1] == lo[-1] == 10.0 and w[-1] == 0)
check("max drawdown", abs(mi.max_drawdown([100, 120, 60, 130]) + 0.5) < 1e-12)
check("ewma vol of zero returns is zero", mi.ewma_vol([0.0] * 40) == 0)
check("score labels", [mi.score_label(s) for s in (80, 30, 0, -30, -80)] == ["strong_pos", "pos", "neutral", "neg", "strong_neg"])

up_a = mi.analyze(series(drift=0.004), "stock")
dn_a = mi.analyze(series(drift=-0.004), "stock")
check("uptrend scores positive", up_a["score"] > 20, up_a.get("score"))
check("downtrend scores negative", dn_a["score"] < -20, dn_a.get("score"))
check("uptrend sits above its MA200", "above_sma200" in up_a["reasons"] and up_a["trend"] in ("up", "side"))
check("downtrend sits below its MA200", "below_sma200" in dn_a["reasons"])
check("expected 5-day move is sqrt(5) x 1-day", abs(up_a["exp_move_5d"] - up_a["exp_move_1d"] * math.sqrt(5)) < 0.02)
lo5, hi5 = up_a["range_5d"]
check("price sits inside its 5-day range", lo5 < up_a["price"] < hi5)
spike = mi.analyze(series(last_vol=5000.0), "stock")
check("a 5x volume day is reported and lifts the move score", spike["vol_ratio"] >= 4.9 and spike["move_score"] >= 30)
check("spark keeps the last 60 closes", len(up_a["spark"]) == 60)
check("too little data gives an empty result", mi.analyze({"c": [1.0]}) == {})
check("missing o/h/l fall back to the close", mi.analyze({"c": [1.0 + i * 0.01 for i in range(60)]}).get("price") is not None)
lines = mi.series_for_chart(series(n=120))
check("chart lines are aligned with the bars", all(len(v) == 120 for v in lines.values()))

reg_up = mi.regime([up_a] * 5, up_a)
reg_dn = mi.regime([dn_a] * 5, dn_a)
check("regime of uptrends is risk_on", reg_up["label"] == "risk_on" and reg_up["breadth50"] == 100)
check("regime of downtrends is risk_off", reg_dn["label"] == "risk_off")
check("empty regime", mi.regime([])["label"] == "unknown")

# ---------------------------------------------------------------- data layer, sources faked
FAIL_URLS = set()


async def fake_get_json(url, params=None):
    if any(f in url for f in FAIL_URLS):
        raise RuntimeError("source down")
    p = params or {}
    if "entrade" in url:
        sym = p.get("symbol")
        if sym == "NOPE":
            return {"t": [], "c": []}
        b = healthy_uptrend() if sym in ("FPT", "VNINDEX") else series(drift=-0.002)
        return {k: b[k] for k in ("t", "o", "h", "l", "c", "v")}
    if "vndirect" in url:
        return {"t": [], "c": []}
    if "yahoo" in url:
        sym = url.rsplit("/", 1)[-1]
        if sym == "ZZZZ":
            return {"chart": {"result": []}}
        b = series(start=20.0 if sym == "^VIX" else 100.0)
        return {"chart": {"result": [{"meta": {"currency": "USD", "regularMarketPrice": b["c"][-1],
                                                "regularMarketTime": b["t"][-1]},
                                       "timestamp": b["t"], "indicators": {"quote": [
                                           {"open": b["o"], "high": b["h"], "low": b["l"], "close": b["c"], "volume": b["v"]}]}}]}}
    if "exchangeInfo" in url:
        return {"symbols": [{"baseAsset": "BTC", "quoteAsset": "USDT", "status": "TRADING"},
                            {"baseAsset": "ETH", "quoteAsset": "USDT", "status": "TRADING"}]}
    if "klines" in url:
        b = series(start=50000.0, drift=0.002)
        return [[t * 1000, o, h, low, c, 0, 0, v] for t, o, h, low, c, v in zip(b["t"], b["o"], b["h"], b["l"], b["c"], b["v"])]
    if "coins/markets" in url:
        def coin(i, sym, price, w=3.0, m=8.0):
            return {"id": i, "symbol": sym, "name": i.title(), "current_price": price, "market_cap": 1e9, "total_volume": 1e8,
                    "market_cap_rank": 1, "price_change_percentage_24h_in_currency": 1.0,
                    "price_change_percentage_7d_in_currency": w, "price_change_percentage_30d_in_currency": m,
                    "sparkline_in_7d": {"price": [price * (1 + 0.01 * math.sin(k / 9)) for k in range(168)]}}
        return [coin("bitcoin", "btc", 60000), coin("ethereum", "eth", 3000), coin("tether", "usdt", 1.0, 0.01, 0.02),
                coin("some-euro", "eurx", 1.16, 0.2, 0.5), coin("wrapped-bitcoin", "wbtc", 60000), coin("tinycoin", "tiny", 0.5)]
    if "market_chart" in url:
        b = series(start=0.5)
        return {"prices": [[t * 1000, c] for t, c in zip(b["t"], b["c"])], "total_volumes": []}
    if url.endswith("/global"):
        return {"data": {"total_market_cap": {"usd": 2.5e12}, "total_volume": {"usd": 9e10},
                         "market_cap_change_percentage_24h_usd": -1.2, "market_cap_percentage": {"btc": 58.0, "eth": 11.0},
                         "active_cryptocurrencies": 20000}}
    if "trending" in url:
        return {"coins": [{"item": {"id": "tinycoin", "symbol": "tiny", "name": "Tiny", "market_cap_rank": 300,
                                    "data": {"price": 0.5, "price_change_percentage_24h": {"usd": 12.3}}}}]}
    if "/search" in url:
        return {"coins": [{"id": "tinycoin", "symbol": "tiny"}]}
    if "alternative.me" in url:
        return {"data": [{"value": str(30 + i % 5), "value_classification": "Fear", "timestamp": str(1_700_000_000 - i * 86400)}
                         for i in range(40)]}
    raise AssertionError("unexpected url " + url)


md._get_json = fake_get_json


async def run():
    vn = await md.section("vn")
    check("vn: every listed stock is analysed", len(vn["rows"]) == len(md.VN_STOCKS), len(vn["rows"]))
    check("vn: indices come first", [i["symbol"] for i in vn["indices"]][:2] == ["VNINDEX", "VN30"])
    check("vn: sector table covers every sector", {s["sector"] for s in vn["sectors"]} == {v[0] for v in md.VN_STOCKS.values()})
    check("vn: rows carry sector and exchange", all(r.get("sector") and r.get("exchange") for r in vn["rows"]))
    w = await md.section("world")
    check("world: every symbol analysed", len(w["rows"]) == len(md.WORLD))
    check("world: VIX level read", w["regime"].get("vix_level") in ("calm", "normal", "elevated", "stress"))
    c = await md.section("crypto")
    ids = [r["id"] for r in c["rows"]]
    check("crypto: stablecoins, pegs and wrapped coins are dropped",
          "tether" not in ids and "some-euro" not in ids and "wrapped-bitcoin" not in ids, ids)
    check("crypto: Binance history where a pair trades", next(r for r in c["rows"] if r["id"] == "bitcoin")["deep"] is True)
    check("crypto: 7-day fallback where none trades", next(r for r in c["rows"] if r["id"] == "tinycoin")["deep"] is False)
    check("crypto: live price from CoinGecko", next(r for r in c["rows"] if r["id"] == "bitcoin")["price"] == 60000)
    check("crypto: fear and greed", c["fng"]["value"] == 30 and len(c["fng"]["history"]) == 40)

    o = await md.overview()
    secs = o["sections"]
    check("overview has all three markets", set(secs) == {"vn", "world", "crypto"} and not any("error" in s for s in secs.values()))
    ol = secs["vn"]["outlook"]
    check("outlook has four lists", set(ol) == {"potential", "movers", "risk", "rebound"})
    check("FPT (uptrend) is a potential pick", any(r["symbol"] == "FPT" for r in ol["potential"]))
    check("falling stocks land in the risk list", len(ol["risk"]) > 0 and all(r["score"] <= -30 or (r.get("rsi") or 0) >= 78 for r in ol["risk"]))

    h = await md.history("vn", "fpt")
    check("history normalises the symbol", h["ok"] and h["symbol"] == "FPT" and len(h["lines"]["sma20"]) == len(h["bars"]["c"]))
    hc = await md.history("crypto", "tiny")
    check("crypto history resolves a ticker to an id", hc["ok"] and hc["symbol"] == "tinycoin")

    # cache: a source that goes down serves the last good copy, marked stale
    md._MEM.clear()
    b1 = await md.vn_bars("HPG")
    FAIL_URLS.update({"entrade", "vndirect"})
    md._MEM["vn_HPG"] = (0.0, md._MEM["vn_HPG"][1])  # expire the history and the live tail
    md._MEM["vnt_HPG"] = (0.0, md._MEM["vnt_HPG"][1])
    b2 = await md.vn_bars("HPG")
    FAIL_URLS.clear()
    check("a failed fetch serves the cached copy as stale", b2 and b2["_stale"] and b2["c"] == b1["c"])

    res = await md.watchlist_add("vn", " hag ")
    check("watchlist add normalises and stores", res["ok"] and res["symbol"] == "HAG" and md.watchlist()["vn"] == ["HAG"])
    bad = await md.watchlist_add("world", "ZZZZ")
    check("watchlist refuses an unknown symbol", not bad["ok"] and bad["error"] == "not_found")
    check("watchlist refuses an unknown market", (await md.watchlist_add("bonds", "X"))["error"] == "kind")
    vn2 = await md.section("vn")
    check("a watched stock joins the table, flagged", any(r["symbol"] == "HAG" and r["watch"] for r in vn2["rows"]))
    md.watchlist_remove("vn", "HAG")
    check("watchlist remove", md.watchlist()["vn"] == [])

    # plugin text
    spec = importlib.util.spec_from_file_location("javis_market_plugin", os.path.join(ROOT, "system", "plugins", "javis-market", "plugin.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    tools = {}

    class Ctx:
        def register_tool(self, **kw):
            tools[kw["name"]] = kw
    mod.register(Ctx())
    check("plugin registers both tools with the right modes",
          tools["javis_market"]["min_mode"] == "readonly" and tools["javis_market_watch"]["min_mode"] == "safe")
    txt = await tools["javis_market"]["handler"]({"op": "overview"}, {})
    check("tool overview covers the three markets", "Việt Nam" in txt and "Thế giới" in txt and "Tiền số" in txt, txt[:200])
    txt = await tools["javis_market"]["handler"]({"op": "symbol", "market": "vn", "symbol": "FPT"}, {})
    check("tool symbol analysis", "FPT" in txt and "MA200" in txt and "RSI" in txt, txt[:200])
    txt = await tools["javis_market"]["handler"]({"op": "outlook", "market": "vn"}, {})
    check("tool outlook lists potential picks", "tiềm năng" in txt and "FPT" in txt)
    txt = await tools["javis_market"]["handler"]({"op": "section"}, {})
    check("tool asks for a market on op=section", txt.startswith("ERROR"))
    txt = await tools["javis_market_watch"]["handler"]({"market": "vn", "symbol": "NOPE"}, {})
    check("watch tool reports an unknown symbol", txt.startswith("ERROR"))
    check("the tool description warns it is not advice", "không phải khuyến nghị" in tools["javis_market"]["description"])

asyncio.run(run())

# ---------------------------------------------------------------- routes
import main  # noqa: E402
paths = {getattr(r, "path", None) for r in main.app.routes}
try:
    from _paths import moi_duong_dan
    paths = set(moi_duong_dan(main.app))
except Exception:
    pass
for p in ("/market/overview", "/market/section", "/market/history", "/market/watchlist", "/market/refresh"):
    check("route " + p, p in paths)
check("import main does not load market_data eagerly (it is imported inside handlers)",
      "import market_data" not in open(os.path.join(SERVER, "main.py"), encoding="utf-8").read().split("def _market_err")[0])

if _fails:
    print(f"\n{len(_fails)} FAIL")
    sys.exit(1)
print("\nall ok")
