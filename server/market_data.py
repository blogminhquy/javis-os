"""market_data.py - market data for the Markets page and the `javis_market` tool.

Sources, all public and key-free:
  - Vietnam stocks and indices: DNSE (services.entrade.com.vn chart API), VNDirect dchart as fallback.
  - World indices, commodities, FX, rates, US/global stocks: Yahoo Finance chart API.
  - Crypto: CoinGecko (markets, global, trending), Binance daily klines (history for indicators),
    alternative.me Fear & Greed index.

Every fetch goes through `_cached()`: an in-memory TTL cache mirrored to STATE_DIR/market/cache so a
restart does not refetch everything, and a failed fetch serves the last good copy marked `stale`.
Indicators come from `market_indicators.analyze()`.

The watchlist (extra symbols the owner adds) lives in STATE_DIR/market/watchlist.json.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import time
from pathlib import Path
from typing import Any

import market_indicators as mi

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/124.0 Safari/537.36")
TIMEOUT = 15.0
HISTORY_DAYS = 420          # enough daily bars for SMA200 plus a 52-week window

# ---------------------------------------------------------------- universes
VN_INDICES = [
    ("VNINDEX", "VN-Index"), ("VN30", "VN30"), ("HNX", "HNX-Index"), ("UPCOM", "UPCoM-Index"),
    ("VN100", "VN100"), ("HNX30", "HNX30"),
]

# Ticker -> (sector key, exchange). Sector keys are translated in the dashboard (mk.sector.*).
VN_STOCKS: dict[str, tuple[str, str]] = {
    # banks
    "ACB": ("bank", "HOSE"), "BID": ("bank", "HOSE"), "CTG": ("bank", "HOSE"), "HDB": ("bank", "HOSE"),
    "LPB": ("bank", "HOSE"), "MBB": ("bank", "HOSE"), "SHB": ("bank", "HOSE"), "SSB": ("bank", "HOSE"),
    "STB": ("bank", "HOSE"), "TCB": ("bank", "HOSE"), "TPB": ("bank", "HOSE"), "VCB": ("bank", "HOSE"),
    "VIB": ("bank", "HOSE"), "VPB": ("bank", "HOSE"), "EIB": ("bank", "HOSE"), "MSB": ("bank", "HOSE"),
    "OCB": ("bank", "HOSE"),
    # securities
    "SSI": ("broker", "HOSE"), "VND": ("broker", "HOSE"), "VCI": ("broker", "HOSE"), "HCM": ("broker", "HOSE"),
    "VIX": ("broker", "HOSE"), "SHS": ("broker", "HNX"), "MBS": ("broker", "HNX"),
    # real estate
    "VHM": ("realestate", "HOSE"), "VIC": ("realestate", "HOSE"), "VRE": ("realestate", "HOSE"),
    "NVL": ("realestate", "HOSE"), "KDH": ("realestate", "HOSE"), "NLG": ("realestate", "HOSE"),
    "DXG": ("realestate", "HOSE"), "DIG": ("realestate", "HOSE"), "PDR": ("realestate", "HOSE"),
    "CEO": ("realestate", "HNX"),
    # industrial parks
    "BCM": ("indpark", "HOSE"), "KBC": ("indpark", "HOSE"), "IDC": ("indpark", "HNX"), "SZC": ("indpark", "HOSE"),
    # steel and materials
    "HPG": ("materials", "HOSE"), "HSG": ("materials", "HOSE"), "NKG": ("materials", "HOSE"),
    "DGC": ("materials", "HOSE"), "DCM": ("materials", "HOSE"), "DPM": ("materials", "HOSE"),
    "GVR": ("materials", "HOSE"),
    # energy and utilities
    "GAS": ("energy", "HOSE"), "PLX": ("energy", "HOSE"), "POW": ("energy", "HOSE"), "PVD": ("energy", "HOSE"),
    "PVS": ("energy", "HNX"), "BSR": ("energy", "HOSE"), "REE": ("energy", "HOSE"), "PC1": ("energy", "HOSE"),
    "GEX": ("energy", "HOSE"),
    # retail and consumer
    "MWG": ("consumer", "HOSE"), "MSN": ("consumer", "HOSE"), "VNM": ("consumer", "HOSE"),
    "SAB": ("consumer", "HOSE"), "PNJ": ("consumer", "HOSE"), "FRT": ("consumer", "HOSE"),
    "DGW": ("consumer", "HOSE"),
    # technology
    "FPT": ("tech", "HOSE"), "CMG": ("tech", "HOSE"),
    # transport and logistics
    "VJC": ("transport", "HOSE"), "HVN": ("transport", "HOSE"), "GMD": ("transport", "HOSE"),
    "VSC": ("transport", "HOSE"),
    # construction
    "CTD": ("construction", "HOSE"), "HHV": ("construction", "HOSE"), "VCG": ("construction", "HOSE"),
    # seafood and agriculture
    "VHC": ("agri", "HOSE"), "ANV": ("agri", "HOSE"), "DBC": ("agri", "HOSE"),
    # insurance
    "BVH": ("insurance", "HOSE"), "BMI": ("insurance", "HOSE"),
}

# Yahoo symbol -> (name, group, region). Group keys: index, commodity, fx, rate, stock.
WORLD: dict[str, tuple[str, str, str]] = {
    "^GSPC": ("S&P 500", "index", "us"), "^DJI": ("Dow Jones", "index", "us"), "^IXIC": ("Nasdaq", "index", "us"),
    "^RUT": ("Russell 2000", "index", "us"), "^VIX": ("VIX", "index", "us"),
    "^STOXX50E": ("Euro Stoxx 50", "index", "eu"), "^FTSE": ("FTSE 100", "index", "eu"),
    "^GDAXI": ("DAX", "index", "eu"), "^FCHI": ("CAC 40", "index", "eu"),
    "^N225": ("Nikkei 225", "index", "asia"), "^HSI": ("Hang Seng", "index", "asia"),
    "000001.SS": ("Shanghai", "index", "asia"), "^KS11": ("KOSPI", "index", "asia"),
    "^TWII": ("Taiwan", "index", "asia"), "^BSESN": ("Sensex", "index", "asia"), "^STI": ("STI", "index", "asia"),
    "^AXJO": ("ASX 200", "index", "asia"),
    "GC=F": ("Gold", "commodity", "global"), "SI=F": ("Silver", "commodity", "global"),
    "CL=F": ("WTI Oil", "commodity", "global"), "BZ=F": ("Brent Oil", "commodity", "global"),
    "NG=F": ("Natural Gas", "commodity", "global"), "HG=F": ("Copper", "commodity", "global"),
    "DX-Y.NYB": ("US Dollar Index", "fx", "global"), "EURUSD=X": ("EUR/USD", "fx", "global"),
    "USDJPY=X": ("USD/JPY", "fx", "global"), "USDCNY=X": ("USD/CNY", "fx", "global"),
    "USDVND=X": ("USD/VND", "fx", "global"),
    "^TNX": ("US 10Y yield", "rate", "us"), "^IRX": ("US 3M yield", "rate", "us"),
    "AAPL": ("Apple", "stock", "us"), "MSFT": ("Microsoft", "stock", "us"), "NVDA": ("Nvidia", "stock", "us"),
    "GOOGL": ("Alphabet", "stock", "us"), "AMZN": ("Amazon", "stock", "us"), "META": ("Meta", "stock", "us"),
    "TSLA": ("Tesla", "stock", "us"), "AVGO": ("Broadcom", "stock", "us"), "AMD": ("AMD", "stock", "us"),
    "NFLX": ("Netflix", "stock", "us"), "JPM": ("JPMorgan", "stock", "us"), "V": ("Visa", "stock", "us"),
    "BRK-B": ("Berkshire", "stock", "us"), "LLY": ("Eli Lilly", "stock", "us"), "XOM": ("Exxon", "stock", "us"),
    "COST": ("Costco", "stock", "us"), "PLTR": ("Palantir", "stock", "us"), "COIN": ("Coinbase", "stock", "us"),
    "TSM": ("TSMC", "stock", "asia"), "ASML": ("ASML", "stock", "eu"), "BABA": ("Alibaba", "stock", "asia"),
    "005930.KS": ("Samsung", "stock", "asia"), "7203.T": ("Toyota", "stock", "asia"),
}
WORLD_BENCH = "^GSPC"
VN_BENCH = "VNINDEX"

# CoinGecko id -> Binance base asset, only where the ticker differs from CoinGecko's symbol.
BINANCE_BASE_OVERRIDE = {"render-token": "RENDER", "polygon-ecosystem-token": "POL"}
STABLES = {"tether", "usd-coin", "dai", "first-digital-usd", "ethena-usde", "usds", "true-usd", "paypal-usd",
           "binance-usd", "frax", "usdd", "susds", "usd1-wlfi", "blackrock-usd-institutional-digital-liquidity-fund"}
CRYPTO_BENCH = "bitcoin"

# ---------------------------------------------------------------- state paths

def _dir() -> Path:
    try:
        import config
        base = Path(config.STATE_DIR)
    except Exception:
        base = Path(os.getenv("JAVIS_STATE_DIR", str(Path(__file__).parent)))
    d = base / "market"
    (d / "cache").mkdir(parents=True, exist_ok=True)
    return d


# ---------------------------------------------------------------- cache
_MEM: dict[str, tuple[float, Any]] = {}
_LOCKS: dict[str, asyncio.Lock] = {}
_SEM: asyncio.Semaphore | None = None


def _sem() -> asyncio.Semaphore:
    global _SEM
    if _SEM is None:
        _SEM = asyncio.Semaphore(8)
    return _SEM


def _key_file(key: str) -> Path:
    return _dir() / "cache" / (re.sub(r"[^A-Za-z0-9_.-]", "_", key)[:120] + ".json")


async def _cached(key: str, ttl: float, fetch, persist: bool | None = None):
    """Return (data, fetched_at, stale). Serves the last good copy when a fetch fails."""
    now = time.time()
    hit = _MEM.get(key)
    if hit and now - hit[0] < ttl:
        return hit[1], hit[0], False
    lock = _LOCKS.setdefault(key, asyncio.Lock())
    async with lock:
        hit = _MEM.get(key)
        if hit and time.time() - hit[0] < ttl:
            return hit[1], hit[0], False
        if not hit:
            try:
                disk = json.loads(_key_file(key).read_text(encoding="utf-8"))
                hit = (float(disk["at"]), disk["data"])
                _MEM[key] = hit
                if time.time() - hit[0] < ttl:
                    return hit[1], hit[0], False
            except Exception:
                hit = None
        try:
            data = await fetch()
            if data is None:
                raise ValueError("empty")
        except Exception:
            if hit:
                return hit[1], hit[0], True
            return None, 0.0, True
        at = time.time()
        _MEM[key] = (at, data)
        if persist is False or (persist is None and key[:4] in ("vnt_", "yht_", "bnt_")):
            return data, at, False
        try:
            _key_file(key).write_text(json.dumps({"at": at, "data": data}), encoding="utf-8")
        except Exception:
            pass
        return data, at, False


def clear_cache() -> int:
    n = len(_MEM)
    _MEM.clear()
    _SECTION.clear()
    try:
        for f in (_dir() / "cache").glob("*.json"):
            f.unlink()
    except Exception:
        pass
    return n


async def _get_json(url: str, params: dict | None = None):
    import httpx
    async with _sem():
        async with httpx.AsyncClient(timeout=TIMEOUT, headers={"User-Agent": UA, "Accept": "application/json"},
                                     follow_redirects=True) as cli:
            r = await cli.get(url, params=params)
            r.raise_for_status()
            return r.json()


# ---------------------------------------------------------------- fetchers (raw bars)

def _bars_from_udf(d: dict) -> dict | None:
    if not isinstance(d, dict) or not d.get("t") or not d.get("c"):
        return None
    n = len(d["c"])
    return {"t": [int(x) for x in d["t"]][:n], "o": d.get("o") or d["c"], "h": d.get("h") or d["c"],
            "l": d.get("l") or d["c"], "c": d["c"], "v": d.get("v") or [0] * n}


# ---- session clock and live tails
#
# Each instrument keeps a long daily history (refetched every 6 hours) plus a short "tail" of the last few sessions
# that is refetched often (25 seconds while the Vietnam market trades). The tail is merged over the history, so a
# page refresh or the background scheduler only moves a few hundred bytes per symbol.
LONG_TTL = 6 * 3600
VN_TZ = 7 * 3600


def vn_now(now: float | None = None):
    import datetime as _dt
    return _dt.datetime.fromtimestamp((now or time.time()) + VN_TZ, _dt.timezone.utc)


def vn_in_session(now: float | None = None) -> bool:
    """HOSE/HNX hours: 9:00-11:30 and 13:00-14:45 (ATC to 15:00), Monday to Friday, Vietnam time."""
    d = vn_now(now)
    if d.weekday() >= 5:
        return False
    m = d.hour * 60 + d.minute
    return 9 * 60 - 5 <= m <= 11 * 60 + 35 or 13 * 60 - 5 <= m <= 15 * 60 + 5


def _tail_ttl(kind: str) -> float:
    if kind == "vn":
        return 25 if vn_in_session() else 1800
    if kind == "world":
        return 120
    return 30


def _merge(long: dict | None, tail: dict | None) -> dict | None:
    """Tail bars replace history bars with the same timestamp and extend past its end."""
    if not long:
        return tail
    if not tail or not tail.get("t"):
        return long
    out = {k: (list(v) if isinstance(v, list) else v) for k, v in long.items()}
    pos = {t: i for i, t in enumerate(out["t"])}
    for j, t in enumerate(tail["t"]):
        i = pos.get(t)
        if i is None:
            if t < out["t"][-1]:
                continue
            for k in ("t", "o", "h", "l", "c", "v"):
                out[k].append(tail[k][j])
            pos[t] = len(out["t"]) - 1
        else:
            for k in ("o", "h", "l", "c", "v"):
                out[k][i] = tail[k][j]
    return out


def _join(long_res, tail_res):
    (ld, lat, lst), (td, tat, tst) = long_res, tail_res
    data = _merge(ld, td)
    if not data:
        return None
    if ld and td:
        for k in ("currency", "name", "tz_off"):
            if td.get(k) is not None:
                data[k] = td[k]
    return _stamp(data, max(lat, tat if td else 0), bool(lst and (tst or not td)))


async def vn_bars(symbol: str, is_index: bool | None = None) -> dict | None:
    symbol = symbol.upper().strip()
    if is_index is None:
        is_index = symbol in dict(VN_INDICES)
    kind = "index" if is_index else "stock"

    async def fetch(days):
        now = int(time.time())
        frm = now - days * 86400
        try:
            d = await _get_json(f"https://services.entrade.com.vn/chart-api/v2/ohlcs/{kind}",
                                {"from": frm, "to": now, "symbol": symbol, "resolution": "1D"})
            b = _bars_from_udf(d)
            if b and b["c"]:
                return b
        except Exception:
            pass
        d = await _get_json("https://dchart-api.vndirect.com.vn/dchart/history",
                            {"resolution": "D", "symbol": symbol, "from": frm, "to": now})
        b = _bars_from_udf(d)
        if b:  # VNDirect stamps bars at 00:00 UTC; shift to DNSE's 02:00 UTC so the two sources merge cleanly
            b["t"] = [int(t // 86400 * 86400 + 7200) for t in b["t"]]
        return b

    long_res = await _cached(f"vn_{symbol}", LONG_TTL, lambda: fetch(HISTORY_DAYS))
    if not long_res[0] or len(long_res[0].get("c") or []) < 6:
        return _stamp(*long_res) if long_res[0] else None
    tail_res = await _cached(f"vnt_{symbol}", _tail_ttl("vn"), lambda: fetch(8))
    return _join(long_res, tail_res)


def _yahoo_parse(d: dict) -> dict | None:
    res = (d.get("chart") or {}).get("result") or []
    if not res:
        return None
    r0 = res[0]
    q = ((r0.get("indicators") or {}).get("quote") or [{}])[0]
    ts = r0.get("timestamp") or []
    n = len(ts)

    def col(k):
        v = q.get(k) or []
        return v if len(v) == n else [None] * n
    o, h, low, c, v = col("open"), col("high"), col("low"), col("close"), col("volume")
    rows = [(ts[i], o[i], h[i], low[i], c[i], v[i]) for i in range(n) if c[i] is not None]
    meta = r0.get("meta") or {}
    live = meta.get("regularMarketPrice")
    if live and rows:
        t_live = int(meta.get("regularMarketTime") or rows[-1][0])
        if t_live - rows[-1][0] > 20 * 3600:
            rows.append((t_live, live, live, live, live, 0))
        else:
            t, oo, hh, ll, _, vv = rows[-1]
            rows[-1] = (t, oo, max(hh or live, live), min(ll or live, live), live, vv)
    if not rows:
        return None
    return {"t": [r[0] for r in rows], "o": [r[1] or r[4] for r in rows], "h": [r[2] or r[4] for r in rows],
            "l": [r[3] or r[4] for r in rows], "c": [r[4] for r in rows], "v": [r[5] or 0 for r in rows],
            "currency": meta.get("currency") or "", "name": meta.get("shortName") or meta.get("longName") or "",
            "tz_off": int(meta.get("gmtoffset") or 0)}


async def yahoo_bars(symbol: str) -> dict | None:
    async def fetch(rng):
        d = await _get_json(f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}",
                            {"range": rng, "interval": "1d", "includePrePost": "false"})
        return _yahoo_parse(d)

    long_res = await _cached(f"yh_{symbol}", LONG_TTL, lambda: fetch("2y"))
    if not long_res[0]:
        return None
    tail_res = await _cached(f"yht_{symbol}", _tail_ttl("world"), lambda: fetch("5d"))
    return _join(long_res, tail_res)


async def binance_bars(pair: str) -> dict | None:
    async def fetch(limit):
        d = await _get_json("https://api.binance.com/api/v3/klines", {"symbol": pair, "interval": "1d", "limit": limit})
        if not isinstance(d, list) or not d:
            return None
        return {"t": [int(k[0] // 1000) for k in d], "o": [float(k[1]) for k in d], "h": [float(k[2]) for k in d],
                "l": [float(k[3]) for k in d], "c": [float(k[4]) for k in d], "v": [float(k[7]) for k in d]}

    long_res = await _cached(f"bn_{pair}", LONG_TTL, lambda: fetch(400))
    if not long_res[0]:
        return None
    tail_res = await _cached(f"bnt_{pair}", _tail_ttl("crypto"), lambda: fetch(3))
    return _join(long_res, tail_res)


async def binance_usdt_bases() -> set:
    """Base assets with a TRADING USDT pair on Binance (refreshed daily)."""
    async def fetch():
        d = await _get_json("https://api.binance.com/api/v3/exchangeInfo", {"permissions": "SPOT"})
        return sorted({s["baseAsset"] for s in (d.get("symbols") or [])
                       if s.get("quoteAsset") == "USDT" and s.get("status") == "TRADING"})
    data, _, _ = await _cached("bn_bases", 86400, fetch)
    return set(data or [])


async def coin_symbol(coin_id: str) -> str:
    for c in await cg_markets():
        if c.get("id") == coin_id:
            return (c.get("symbol") or "").upper()
    try:
        d = await _get_json("https://api.coingecko.com/api/v3/search", {"query": coin_id})
        hit = next((c for c in d.get("coins") or [] if c.get("id") == coin_id), None)
        return (hit.get("symbol") or "").upper() if hit else ""
    except Exception:
        return ""


async def coin_bars(coin_id: str, symbol: str | None = None, bases: set | None = None) -> dict | None:
    """Daily bars for a coin: Binance USDT pair when one trades, otherwise CoinGecko (closes only)."""
    base = BINANCE_BASE_OVERRIDE.get(coin_id) or (symbol or await coin_symbol(coin_id)).upper()
    if bases is None:
        bases = await binance_usdt_bases()
    if base and base in bases:
        b = await binance_bars(base + "USDT")
        if b and len(b.get("c") or []) > 30:
            return b
    return await coingecko_chart(coin_id)


def _looks_stable(c: dict) -> bool:
    """Stablecoins and pegged tokens: a price near $1 that barely moves. They have no trend to rank."""
    if c.get("id") in STABLES:
        return True
    # Wrapped, staked and bridged copies only mirror another coin; listing them twice skews breadth.
    name = (c.get("name") or "").lower()
    if any(w in name for w in ("wrapped", "staked", "bridged", "liquid staking")) or c.get("id") in ("weth", "wbtc", "steth", "wsteth", "weeth", "cbbtc"):
        return True
    p = c.get("current_price") or 0
    w = c.get("price_change_percentage_7d_in_currency")
    m = c.get("price_change_percentage_30d_in_currency")
    if 0.97 <= p <= 1.03 and w is not None and abs(w) < 1.0 and (m is None or abs(m) < 2.0):
        return True
    # Tokenised T-bills, euro coins and similar pegs trade at other prices but hardly move.
    if w is not None and m is not None and abs(w) < 0.6 and abs(m) < 1.5:
        return True
    return False


async def coingecko_chart(coin_id: str) -> dict | None:
    async def fetch():
        d = await _get_json(f"https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart",
                            {"vs_currency": "usd", "days": "365", "interval": "daily"})
        p = d.get("prices") or []
        if not p:
            return None
        vols = {int(x[0] // 86400000): x[1] for x in (d.get("total_volumes") or [])}
        t = [int(x[0] // 1000) for x in p]
        c = [float(x[1]) for x in p]
        return {"t": t, "o": c, "h": c, "l": c, "c": c, "v": [float(vols.get(int(x[0] // 86400000), 0)) for x in p]}

    data, at, stale = await _cached(f"cg_chart_{coin_id}", 1800, fetch)
    return _stamp(data, at, stale)


def _stamp(data, at, stale):
    if not data:
        return None
    out = dict(data)
    out["_at"] = at
    out["_stale"] = stale
    return out


async def cg_markets() -> list:
    async def fetch():
        return await _get_json("https://api.coingecko.com/api/v3/coins/markets", {
            "vs_currency": "usd", "order": "market_cap_desc", "per_page": 150, "page": 1,
            "sparkline": "true", "price_change_percentage": "1h,24h,7d,30d,1y"})
    data, _, _ = await _cached("cg_markets", 180, fetch)
    return data or []


async def cg_global() -> dict:
    async def fetch():
        return (await _get_json("https://api.coingecko.com/api/v3/global")).get("data")
    data, _, _ = await _cached("cg_global", 300, fetch)
    return data or {}


async def cg_trending() -> list:
    async def fetch():
        d = await _get_json("https://api.coingecko.com/api/v3/search/trending")
        out = []
        for c in (d.get("coins") or [])[:15]:
            it = c.get("item") or {}
            data = it.get("data") or {}
            pc = (data.get("price_change_percentage_24h") or {}).get("usd")
            out.append({"id": it.get("id"), "symbol": (it.get("symbol") or "").upper(), "name": it.get("name"),
                        "rank": it.get("market_cap_rank"), "thumb": it.get("thumb") or it.get("small"),
                        "price": data.get("price"), "chg_24h": round(pc, 2) if isinstance(pc, (int, float)) else None})
        return out
    data, _, _ = await _cached("cg_trending", 900, fetch)
    return data or []


async def fear_greed() -> dict:
    async def fetch():
        d = await _get_json("https://api.alternative.me/fng/", {"limit": 90})
        pts = [{"t": int(x["timestamp"]), "v": int(x["value"]), "label": x.get("value_classification", "")}
               for x in (d.get("data") or [])]
        return list(reversed(pts)) or None
    data, _, _ = await _cached("fng", 3600, fetch)
    pts = data or []
    if not pts:
        return {}
    last = pts[-1]
    prev_w = pts[-8]["v"] if len(pts) >= 8 else None
    prev_m = pts[-31]["v"] if len(pts) >= 31 else None
    return {"value": last["v"], "label": last["label"], "week_ago": prev_w, "month_ago": prev_m,
            "history": pts}


# ---------------------------------------------------------------- watchlist

def _wl_path() -> Path:
    return _dir() / "watchlist.json"


def watchlist() -> dict:
    try:
        d = json.loads(_wl_path().read_text(encoding="utf-8"))
    except Exception:
        d = {}
    return {k: [str(x) for x in (d.get(k) or [])][:60] for k in ("vn", "world", "crypto")}


def _save_watchlist(d: dict) -> None:
    _wl_path().write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")


def normalize_symbol(kind: str, symbol: str) -> str:
    s = str(symbol or "").strip()
    if kind == "vn":
        return re.sub(r"[^A-Z0-9]", "", s.upper())[:12]
    if kind == "world":
        return re.sub(r"[^A-Za-z0-9^=.\-]", "", s).upper()[:20]
    return re.sub(r"[^a-z0-9\-]", "", s.lower())[:60]


async def resolve_crypto(q: str) -> str | None:
    """Coin id from an id, a ticker or a name ('btc' -> 'bitcoin')."""
    q = q.strip().lower()
    for c in await cg_markets():
        if q in (c.get("id"), (c.get("symbol") or "").lower(), (c.get("name") or "").lower()):
            return c["id"]
    try:
        d = await _get_json("https://api.coingecko.com/api/v3/search", {"query": q})
        coins = d.get("coins") or []
        exact = [c for c in coins if (c.get("symbol") or "").lower() == q or c.get("id") == q]
        hit = (exact or coins)[:1]
        return hit[0]["id"] if hit else None
    except Exception:
        return None


async def watchlist_add(kind: str, symbol: str) -> dict:
    if kind not in ("vn", "world", "crypto"):
        return {"ok": False, "error": "kind"}
    sym = normalize_symbol(kind, symbol)
    if kind == "crypto" and sym:
        sym = await resolve_crypto(sym) or ""
    if not sym:
        return {"ok": False, "error": "symbol"}
    bars = None
    if kind == "vn":
        bars = await vn_bars(sym)
    elif kind == "world":
        bars = await yahoo_bars(sym)
    else:
        bars = await coin_bars(sym)
    if not bars or len(bars.get("c") or []) < 2:
        return {"ok": False, "error": "not_found", "symbol": sym}
    wl = watchlist()
    if sym not in wl[kind]:
        wl[kind].insert(0, sym)
        _save_watchlist(wl)
    _expire_section(kind)
    return {"ok": True, "symbol": sym, "watchlist": wl}


def _expire_section(kind: str) -> None:
    """The watchlist changed: the next read of that market recomputes it instead of serving the cached copy."""
    hit = _SECTION.get(kind)
    if hit:
        _SECTION[kind] = (0.0, hit[1])
    try:
        _section_file(kind).unlink()
    except Exception:
        pass


def watchlist_remove(kind: str, symbol: str) -> dict:
    wl = watchlist()
    if kind in wl:
        sym = normalize_symbol(kind, symbol)
        wl[kind] = [x for x in wl[kind] if x != sym]
        _save_watchlist(wl)
        _expire_section(kind)
    return {"ok": True, "watchlist": wl}


# ---------------------------------------------------------------- sections

def _bar_date(b: dict | None) -> str:
    import market_store
    if not b or not b.get("t"):
        return ""
    return market_store.bar_date(b["t"][-1], b.get("tz_off") or 0)


def _meta(bars: dict | None) -> tuple[float, bool]:
    if not bars:
        return 0.0, True
    return float(bars.get("_at") or 0), bool(bars.get("_stale"))


async def section_vn() -> dict:
    wl = watchlist()["vn"]
    stocks = list(dict.fromkeys(wl + list(VN_STOCKS)))
    idx_syms = [s for s, _ in VN_INDICES]
    all_bars = await asyncio.gather(*[vn_bars(s, True) for s in idx_syms],
                                    *[vn_bars(s, False) for s in stocks])
    indices, rows, newest, stale = [], [], 0.0, False
    series, meta = {}, {}
    for (sym, name), b in zip(VN_INDICES, all_bars[:len(idx_syms)]):
        a = mi.analyze(b, "stock") if b else {}
        if a:
            indices.append({"symbol": sym, "name": name, "bar_date": _bar_date(b), **a})
            series[sym] = b
            meta[sym] = {"symbol": sym, "name": name, "group": "index"}
            at, st = _meta(b)
            newest, stale = max(newest, at), stale or st
    for sym, b in zip(stocks, all_bars[len(idx_syms):]):
        a = mi.analyze(b, "stock") if b else {}
        if not a:
            continue
        sector, exch = VN_STOCKS.get(sym, ("other", ""))
        rows.append({"symbol": sym, "name": sym, "sector": sector, "exchange": exch, "watch": sym in wl,
                     "bar_date": _bar_date(b), **a})
        series[sym] = b
        meta[sym] = {"symbol": sym, "name": sym, "sector": sector}
        at, st = _meta(b)
        newest, stale = max(newest, at), stale or st
    bench = next((i for i in indices if i["symbol"] == VN_BENCH), None)
    sectors = _sector_table(rows)
    return {"kind": "vn", "indices": indices, "rows": rows, "sectors": sectors,
            "regime": mi.regime(rows, bench), "bench": VN_BENCH, "at": newest, "stale": stale,
            "currency": "VND", "unit": 1000, "_series": series, "_meta": meta}


def _sector_table(rows: list[dict]) -> list[dict]:
    by: dict[str, list[dict]] = {}
    for r in rows:
        by.setdefault(r.get("sector") or "other", []).append(r)
    out = []
    for k, rs in by.items():
        def avg(f):
            vals = [r[f] for r in rs if r.get(f) is not None]
            return round(sum(vals) / len(vals), 2) if vals else None
        out.append({"sector": k, "count": len(rs), "chg_1d": avg("chg_1d"), "chg_5d": avg("chg_5d"),
                    "chg_1m": avg("chg_1m"), "score": avg("score"),
                    "value": sum(r.get("value") or 0 for r in rs),
                    "members": [r["symbol"] for r in sorted(rs, key=lambda r: -(r.get("value") or 0))]})
    out.sort(key=lambda s: -(s["value"] or 0))
    return out


async def section_world() -> dict:
    wl = watchlist()["world"]
    syms = list(dict.fromkeys(list(WORLD) + wl))
    all_bars = await asyncio.gather(*[yahoo_bars(s) for s in syms])
    rows, newest, stale = [], 0.0, False
    series, meta = {}, {}
    for sym, b in zip(syms, all_bars):
        a = mi.analyze(b, "stock") if b else {}
        if not a:
            continue
        name, group, region = WORLD.get(sym, (b.get("name") or sym, "stock", "other"))
        rows.append({"symbol": sym, "name": name, "group": group, "region": region,
                     "currency": b.get("currency") or "", "watch": sym in wl, "bar_date": _bar_date(b), **a})
        series[sym] = b
        meta[sym] = {"symbol": sym, "name": name, "group": group, "region": region}
        at, st = _meta(b)
        newest, stale = max(newest, at), stale or st
    bench = next((r for r in rows if r["symbol"] == WORLD_BENCH), None)
    vix = next((r for r in rows if r["symbol"] == "^VIX"), None)
    risky = [r for r in rows if r["group"] in ("index", "stock") and r["symbol"] != "^VIX"]
    reg = mi.regime(risky, bench)
    if vix:
        v = vix["price"]
        reg["vix"] = round(v, 2)
        reg["vix_level"] = "calm" if v < 15 else ("normal" if v < 20 else ("elevated" if v < 30 else "stress"))
    return {"kind": "world", "rows": rows, "regime": reg, "bench": WORLD_BENCH, "at": newest, "stale": stale,
            "_series": series, "_meta": meta}


def _from_spark(spark: list) -> dict:
    """CoinGecko's 7-day hourly sparkline as pseudo-daily bars when no daily history is available."""
    s = [x for x in (spark or []) if isinstance(x, (int, float))]
    if len(s) < 24:
        return {}
    daily = s[::24] + ([s[-1]] if (len(s) - 1) % 24 else [])
    return {"t": list(range(len(daily))), "c": daily}


async def section_crypto() -> dict:
    wl = watchlist()["crypto"]
    mk, glob, trend, fng = await asyncio.gather(cg_markets(), cg_global(), cg_trending(), fear_greed())
    coins = [c for c in mk if not _looks_stable(c)][:100]
    have = {c["id"] for c in coins}
    extra_ids = [w for w in wl if w not in have]
    bases = await binance_usdt_bases()
    # Top coins: Binance history when the pair trades there (no rate limit worth worrying about);
    # the rest rank on CoinGecko's 7-day data so the page never fires 60 CoinGecko calls at once.
    deep_ids = [c["id"] for c in coins
                if (BINANCE_BASE_OVERRIDE.get(c["id"]) or (c.get("symbol") or "").upper()) in bases]
    sym_of = {c["id"]: (c.get("symbol") or "").upper() for c in coins}
    hist = await asyncio.gather(*[coin_bars(i, sym_of.get(i), bases) for i in deep_ids + extra_ids])
    hist_by = dict(zip(deep_ids + extra_ids, hist))
    rows = []
    for c in coins:
        b = hist_by.get(c["id"])
        deep = bool(b and len(b.get("c") or []) > 30)
        a = mi.analyze(b, "crypto") if deep else mi.analyze(_from_spark((c.get("sparkline_in_7d") or {}).get("price")), "crypto")
        price = c.get("current_price")
        if price is not None and a:
            a["price"] = price
        row = _coin_row(c, a, deep, c["id"] in wl)
        if deep:
            row["bar_date"] = _bar_date(b)
            if c["id"] in deep_ids:
                row["pair"] = (BINANCE_BASE_OVERRIDE.get(c["id"]) or sym_of.get(c["id"], "")) + "USDT"
        rows.append(row)
    for cid in extra_ids:
        b = hist_by.get(cid)
        a = mi.analyze(b, "crypto") if b else {}
        if a:
            rows.append({"symbol": cid.upper(), "id": cid, "name": cid, "rank": None, "image": "",
                         "deep": True, "watch": True, "bar_date": _bar_date(b), **a})
    bench = next((r for r in rows if r.get("id") == CRYPTO_BENCH), None)
    deep_rows = [r for r in rows if r.get("deep")]
    reg = mi.regime(deep_rows or rows, bench)
    if fng:
        reg["fng"] = fng.get("value")
        reg["fng_label"] = fng.get("label")
    g = {}
    if glob:
        g = {"mcap": (glob.get("total_market_cap") or {}).get("usd"),
             "volume": (glob.get("total_volume") or {}).get("usd"),
             "mcap_chg_24h": round(glob.get("market_cap_change_percentage_24h_usd") or 0, 2),
             "btc_dom": round((glob.get("market_cap_percentage") or {}).get("btc") or 0, 2),
             "eth_dom": round((glob.get("market_cap_percentage") or {}).get("eth") or 0, 2),
             "coins": glob.get("active_cryptocurrencies")}
    series = {r["id"]: hist_by[r["id"]] for r in rows if r.get("deep") and hist_by.get(r["id"])}
    meta = {r["id"]: {"symbol": r["symbol"], "id": r["id"], "name": r.get("name"), "image": r.get("image"),
                      "rank": r.get("rank")} for r in rows if r["id"] in series}
    return {"kind": "crypto", "rows": rows, "global": g, "trending": trend, "fng": fng, "regime": reg,
            "bench": CRYPTO_BENCH, "at": time.time(), "stale": not mk, "_series": series, "_meta": meta}


def _coin_row(c: dict, a: dict, deep: bool, watch: bool) -> dict:
    def pc(k):
        v = c.get(k)
        return round(v, 2) if isinstance(v, (int, float)) else None
    row = {"symbol": (c.get("symbol") or "").upper(), "id": c.get("id"), "name": c.get("name"),
           "rank": c.get("market_cap_rank"), "image": c.get("image") or "", "deep": deep, "watch": watch,
           "mcap": c.get("market_cap"), "volume_24h": c.get("total_volume"),
           "turnover": round(c["total_volume"] / c["market_cap"] * 100, 2) if c.get("total_volume") and c.get("market_cap") else None,
           "ath_from": pc("ath_change_percentage"), "circ": c.get("circulating_supply"), "max_supply": c.get("max_supply"),
           **(a or {})}
    row["price"] = c.get("current_price")
    row["chg_1h"] = pc("price_change_percentage_1h_in_currency")
    # CoinGecko's rolling changes are live; prefer them over changes computed from daily closes.
    for field, key in (("chg_1d", "price_change_percentage_24h_in_currency"),
                       ("chg_5d", "price_change_percentage_7d_in_currency"),
                       ("chg_1m", "price_change_percentage_30d_in_currency"),
                       ("chg_1y", "price_change_percentage_1y_in_currency")):
        if c.get(key) is not None:
            row[field] = pc(key)
    sp = (c.get("sparkline_in_7d") or {}).get("price") or []
    if sp:
        row["spark7d"] = [round(x, 8) for x in sp[::4]]
    return row


SECTIONS = {"vn": section_vn, "world": section_world, "crypto": section_crypto}


# Computed sections, kept so the page opens instantly. The background loop (market_live.py) refreshes them; a
# request only recomputes when the copy is older than SECTION_TTL (the loop is off, or the server just started).
SECTION_TTL = {"vn": 90, "world": 360, "crypto": 90}
_SECTION: dict = {}
_SECTION_LOCKS: dict = {}
LAST_VIEW = 0.0


def _section_file(name: str) -> Path:
    return _dir() / f"section_{name}.json"


async def refresh_section(name: str) -> dict:
    fn = SECTIONS.get(name)
    if not fn:
        raise ValueError(name)
    lock = _SECTION_LOCKS.setdefault(name, asyncio.Lock())
    async with lock:
        data = await fn()
        series = data.pop("_series", {}) or {}
        meta = data.pop("_meta", {}) or {}
        if not data.get("rows"):
            hit = _SECTION.get(name)
            if hit:  # every source failed: keep serving the last good copy
                return hit[1]
        data["computed_at"] = time.time()
        _SECTION[name] = (data["computed_at"], data)
        try:
            await asyncio.to_thread(_section_file(name).write_text, json.dumps(data), "utf-8")
        except Exception:
            pass
    try:
        import market_live
        market_live.after_refresh(name, data, series, meta)
    except Exception:
        pass
    return data


async def section(name: str, max_age: float | None = None) -> dict:
    if name not in SECTIONS:
        raise ValueError(name)
    hit = _SECTION.get(name)
    if not hit:
        try:
            d = json.loads(_section_file(name).read_text(encoding="utf-8"))
            hit = (float(d.get("computed_at") or 0), d)
            _SECTION[name] = hit
        except Exception:
            hit = None
    ttl = SECTION_TTL[name] if max_age is None else max_age
    if hit and time.time() - hit[0] < ttl:
        return hit[1]
    if hit and _SECTION_LOCKS.get(name) and _SECTION_LOCKS[name].locked():
        return hit[1]  # a refresh is already running; serve what we have
    return await refresh_section(name)


def mark_view() -> None:
    global LAST_VIEW
    LAST_VIEW = time.time()


async def binance_live(pairs: list) -> dict:
    """{pair: [last, open 24h ago]} from one Binance call, cached 4 seconds."""
    # Binance rejects the whole batch when one symbol has characters outside A-Z, 0-9 and -._ (some tickers are Chinese).
    pairs = sorted({p for p in pairs if p and re.fullmatch(r"[A-Z0-9._-]{1,50}", p)})[:100]
    if not pairs:
        return {}

    async def fetch():
        d = await _get_json("https://api.binance.com/api/v3/ticker/24hr",
                            {"symbols": json.dumps(pairs, separators=(",", ":")), "type": "MINI"})
        return {x["symbol"]: [float(x["lastPrice"]), float(x["openPrice"])] for x in d or []}
    data, _, _ = await _cached("bn_live", 4, fetch, persist=False)
    return data or {}


async def live(kinds: list) -> dict:
    """Latest prices for the open page. Crypto comes straight from Binance (seconds old); Vietnam and world come
    from the computed sections, which the background loop keeps within 30 s to 2 min while someone is watching."""
    mark_view()
    out: dict = {"at": time.time(), "sections": {}, "prices": {}}
    for k in kinds:
        if k not in SECTIONS:
            continue
        hit = _SECTION.get(k)
        if not hit:
            continue
        data = hit[1]
        out["sections"][k] = hit[0]
        prices = {}
        for r in (data.get("indices") or []) + (data.get("rows") or []):
            key = r.get("id") or r.get("symbol")
            prices[key] = [r.get("price"), r.get("chg_1d")]
        if k == "crypto":
            pair_of = {r["pair"]: r["id"] for r in data.get("rows") or [] if r.get("pair")}
            try:
                tick = await binance_live(list(pair_of))
            except Exception:
                tick = {}
            for pair, (last, opn) in tick.items():
                cid = pair_of.get(pair)
                if cid and last:
                    prices[cid] = [last, round((last / opn - 1) * 100, 2) if opn else None]
        out["prices"][k] = prices
    return out


# ---------------------------------------------------------------- outlook

def _pick(rows: list[dict], kind: str) -> dict:
    """Ranked lists for the Outlook tab. Rows need enough history for SMA50 to be ranked."""
    ok = [r for r in rows if r.get("sma50") and r.get("price")]
    if kind == "world":
        ok = [r for r in ok if r.get("group") == "stock" or r.get("group") == "index" and r["symbol"] != "^VIX"]

    def slim(r):
        keys = ("symbol", "id", "name", "sector", "group", "region", "price", "chg_1d", "chg_5d", "chg_1m", "chg_3m",
                "rsi", "score", "signal", "move_score", "exp_move_5d", "range_5d", "vol_ratio", "reasons", "trend",
                "vol_regime", "image", "rank", "spark", "from_high")
        return {k: r.get(k) for k in keys if k in r}

    potential = sorted(
        [r for r in ok if r.get("score", 0) >= 30 and (r.get("rsi") or 50) < 72
         and (not r.get("sma200") or r["price"] > r["sma200"])],
        key=lambda r: -(r["score"] + (r.get("chg_3m") or 0) * 0.3))
    movers = sorted([r for r in ok if r.get("move_score", 0) >= 35],
                    key=lambda r: -(r["move_score"] * 1.0 + (r.get("exp_move_5d") or 0)))
    risk = sorted([r for r in ok if r.get("score", 0) <= -30 or (r.get("rsi") or 0) >= 78],
                  key=lambda r: (r.get("score", 0), -(r.get("rsi") or 0)))
    rebound = sorted([r for r in ok if (r.get("rsi") or 50) <= 32 and r.get("sma200") and r["price"] > r["sma200"] * 0.9],
                     key=lambda r: r.get("rsi") or 50)
    return {"potential": [slim(r) for r in potential[:12]], "movers": [slim(r) for r in movers[:12]],
            "risk": [slim(r) for r in risk[:12]], "rebound": [slim(r) for r in rebound[:8]]}


async def overview() -> dict:
    vn, world, crypto = await asyncio.gather(section("vn"), section("world"), section("crypto"), return_exceptions=True)
    out: dict = {"at": time.time(), "sections": {}}
    for name, s in (("vn", vn), ("world", world), ("crypto", crypto)):
        if isinstance(s, Exception) or not s:
            out["sections"][name] = {"error": str(s)[:200] if isinstance(s, Exception) else "empty"}
            continue
        rows = s.get("rows") or []
        movers = [r for r in rows if r.get("chg_1d") is not None]
        if name == "world":
            movers = [r for r in movers if r.get("group") == "stock"]
        top_up = sorted(movers, key=lambda r: -r["chg_1d"])[:6]
        top_dn = sorted(movers, key=lambda r: r["chg_1d"])[:6]

        def mini(r):
            return {k: r.get(k) for k in ("symbol", "id", "name", "price", "chg_1d", "chg_5d", "score", "signal",
                                          "image", "sector", "group", "spark")}
        sec = {"regime": s.get("regime"), "at": s.get("at"), "stale": s.get("stale"), "computed_at": s.get("computed_at"),
               "top_up": [mini(r) for r in top_up], "top_down": [mini(r) for r in top_dn],
               "outlook": _pick(rows, name)}
        if name == "vn":
            sec["indices"] = [mini(i) | {"exp_move_5d": i.get("exp_move_5d"), "rsi": i.get("rsi"),
                                         "hv20": i.get("hv20"), "trend": i.get("trend")} for i in s.get("indices") or []]
            sec["sectors"] = s.get("sectors")
        if name == "world":
            sec["key"] = [mini(r) | {"exp_move_5d": r.get("exp_move_5d"), "trend": r.get("trend")} for r in rows
                          if r["symbol"] in ("^GSPC", "^IXIC", "^DJI", "^N225", "^HSI", "^GDAXI", "GC=F", "CL=F",
                                             "DX-Y.NYB", "^TNX", "^VIX", "USDVND=X")]
        if name == "crypto":
            sec["global"] = s.get("global")
            sec["fng"] = {k: v for k, v in (s.get("fng") or {}).items() if k != "history"}
            sec["key"] = [mini(r) | {"exp_move_5d": r.get("exp_move_5d"), "trend": r.get("trend")} for r in rows[:6]]
            sec["trending"] = (s.get("trending") or [])[:8]
        out["sections"][name] = sec
    return out


async def history(kind: str, symbol: str) -> dict:
    """Bars + indicator lines + analysis for the detail chart."""
    sym = normalize_symbol(kind, symbol)
    if kind == "vn":
        b = await vn_bars(sym)
        name = dict(VN_INDICES).get(sym, sym)
        k = "stock"
    elif kind == "world":
        b = await yahoo_bars(sym)
        name = WORLD.get(sym, (b.get("name") if b else sym,))[0] if b else sym
        k = "stock"
    elif kind == "crypto":
        if sym not in {c.get("id") for c in await cg_markets()}:
            sym = await resolve_crypto(sym) or sym
        b = await coin_bars(sym)
        name = next((c.get("name") for c in await cg_markets() if c.get("id") == sym), sym)
        k = "crypto"
    else:
        raise ValueError(kind)
    if not b:
        return {"ok": False, "symbol": sym}
    bars = {key: b[key] for key in ("t", "o", "h", "l", "c", "v")}
    return {"ok": True, "kind": kind, "symbol": sym, "name": name, "bars": bars,
            "lines": mi.series_for_chart(bars), "analysis": mi.analyze(bars, k),
            "at": b.get("_at"), "stale": b.get("_stale"), "currency": b.get("currency") or ("VND" if kind == "vn" else "USD")}


# ---------------------------------------------------------------- text digest for the chat tool

def _fmt(v, nd=2, pct=False):
    if v is None:
        return "-"
    s = f"{v:+.{nd}f}" if pct else (f"{v:,.{nd}f}")
    return s + ("%" if pct else "")


def digest_row(r: dict) -> str:
    return (f"{r.get('symbol')}: giá {_fmt(r.get('price'), 2)} | 1N {_fmt(r.get('chg_1d'), pct=True)} | "
            f"1T {_fmt(r.get('chg_5d'), pct=True)} | 1Th {_fmt(r.get('chg_1m'), pct=True)} | RSI {_fmt(r.get('rsi'), 0)} | "
            f"điểm xu hướng {r.get('score')} ({r.get('signal')}) | khả năng biến động mạnh {r.get('move_score')}/100 | "
            f"biên độ dự kiến 5 phiên ±{_fmt(r.get('exp_move_5d'))}% | tín hiệu: {', '.join(r.get('reasons') or []) or '-'}")
