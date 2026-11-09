"""market_store.py - long-term market history for the Markets page (SQLite in STATE_DIR/market/market.db).

Three tables:
  bars     daily OHLCV per (kind, symbol, date). The live fetch only keeps ~420 days; this archive keeps every
           bar it has ever seen, so history grows past the source window over time.
  signals  one row per (kind, snapshot date, symbol): price, trend score, move score, expected 5-day move, RSI and
           which Outlook list the symbol was in. Written once per closed session ("live") and backfilled from
           price history for the last 60 sessions ("backtest"), so the accuracy card has numbers on day one.
  meta     small key/value pairs (last backtest day per market).

`accuracy()` grades past snapshots against what happened next: did "potential" picks rise, did "risk" picks fall,
did "movers" move more than the rest, and how often the price stayed inside the expected range (68% when
calibrated). Everything here is blocking sqlite; callers run it in a thread.
"""
from __future__ import annotations

import datetime as _dt
import json
import math
import os
import sqlite3
import threading
from pathlib import Path

import market_indicators as mi

HORIZON = 5
_LOCK = threading.Lock()
_KNOWN: dict[str, set] = {}


def _path() -> Path:
    try:
        import config
        base = Path(config.STATE_DIR)
    except Exception:
        base = Path(os.getenv("JAVIS_STATE_DIR", str(Path(__file__).parent)))
    d = base / "market"
    d.mkdir(parents=True, exist_ok=True)
    return d / "market.db"


def _db() -> sqlite3.Connection:
    con = sqlite3.connect(str(_path()), timeout=15)
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA synchronous=NORMAL")
    con.executescript("""
        CREATE TABLE IF NOT EXISTS bars (kind TEXT, symbol TEXT, date TEXT, o REAL, h REAL, l REAL, c REAL, v REAL,
            PRIMARY KEY (kind, symbol, date));
        CREATE TABLE IF NOT EXISTS signals (kind TEXT, snap TEXT, symbol TEXT, bar_date TEXT, price REAL, score REAL,
            move REAL, exp5 REAL, rsi REAL, list TEXT, source TEXT, PRIMARY KEY (kind, snap, symbol));
        CREATE INDEX IF NOT EXISTS signals_kind_snap ON signals (kind, snap);
        CREATE TABLE IF NOT EXISTS meta (k TEXT PRIMARY KEY, v TEXT);
    """)
    return con


def bar_date(t: float, tz_off: float = 0) -> str:
    return _dt.datetime.fromtimestamp(float(t) + float(tz_off or 0), _dt.timezone.utc).strftime("%Y-%m-%d")


# ---------------------------------------------------------------- bars

def upsert_bars(kind: str, series: dict) -> int:
    """series: {symbol: bars}. Bars carry "t" (unix seconds) and optional "tz_off" (seconds, Yahoo exchange offset).
    A symbol seen for the first time is written in full; afterwards only its last 7 bars (the ones that can change)."""
    rows = []
    known = _KNOWN.setdefault(kind, set())
    with _LOCK:
        con = _db()
        try:
            if not known:
                known.update(r[0] for r in con.execute("SELECT DISTINCT symbol FROM bars WHERE kind=?", (kind,)))
            for sym, b in series.items():
                if not b or not b.get("c"):
                    continue
                n = len(b["c"])
                start = 0 if sym not in known else max(0, n - 7)
                off = b.get("tz_off") or 0
                for i in range(start, n):
                    try:
                        rows.append((kind, sym, bar_date(b["t"][i], off), float(b["o"][i]), float(b["h"][i]),
                                     float(b["l"][i]), float(b["c"][i]), float(b["v"][i] or 0)))
                    except (TypeError, ValueError, IndexError):
                        continue
                known.add(sym)
            con.executemany("INSERT OR REPLACE INTO bars VALUES (?,?,?,?,?,?,?,?)", rows)
            con.commit()
        finally:
            con.close()
    return len(rows)


def closes(kind: str) -> dict:
    """{symbol: (dates, closes)} oldest first."""
    out: dict = {}
    with _LOCK:
        con = _db()
        try:
            for sym, d, c in con.execute("SELECT symbol, date, c FROM bars WHERE kind=? ORDER BY symbol, date", (kind,)):
                ds, cs = out.setdefault(sym, ([], []))
                ds.append(d)
                cs.append(c)
        finally:
            con.close()
    return out


# ---------------------------------------------------------------- signals

def _lists_by_symbol(outlook: dict) -> dict:
    tag = {}
    for name in ("potential", "movers", "risk", "rebound"):
        for r in (outlook or {}).get(name) or []:
            tag.setdefault(r.get("id") or r.get("symbol"), name)
    return tag


def has_snapshot(kind: str, snap: str) -> bool:
    with _LOCK:
        con = _db()
        try:
            return con.execute("SELECT 1 FROM signals WHERE kind=? AND snap=? LIMIT 1", (kind, snap)).fetchone() is not None
        finally:
            con.close()


def save_snapshot(kind: str, snap: str, rows: list, outlook: dict, source: str = "live") -> int:
    tag = _lists_by_symbol(outlook)
    data = []
    for r in rows:
        key = r.get("id") or r.get("symbol")
        if not key or r.get("price") is None or not r.get("sma50"):
            continue
        data.append((kind, snap, key, r.get("bar_date") or snap, r.get("price"), r.get("score"), r.get("move_score"),
                     r.get("exp_move_5d"), r.get("rsi"), tag.get(key, ""), source))
    with _LOCK:
        con = _db()
        try:
            if source == "live":
                con.execute("DELETE FROM signals WHERE kind=? AND snap=?", (kind, snap))
                con.executemany("INSERT INTO signals VALUES (?,?,?,?,?,?,?,?,?,?,?)", data)
            else:
                con.executemany("INSERT OR IGNORE INTO signals VALUES (?,?,?,?,?,?,?,?,?,?,?)", data)
            con.commit()
        finally:
            con.close()
    return len(data)


def meta_get(k: str, default: str = "") -> str:
    with _LOCK:
        con = _db()
        try:
            r = con.execute("SELECT v FROM meta WHERE k=?", (k,)).fetchone()
            return r[0] if r else default
        finally:
            con.close()


def meta_set(k: str, v: str) -> None:
    with _LOCK:
        con = _db()
        try:
            con.execute("INSERT OR REPLACE INTO meta VALUES (?,?)", (k, v))
            con.commit()
        finally:
            con.close()


def backtest(kind: str, series: dict, meta: dict, pick, days: int = 60, kind_analyze: str = "stock") -> int:
    """Rebuild what the Outlook would have said on each of the last `days` sessions, from price history alone.

    series: {symbol: bars}; meta: {symbol: extra row fields (name, sector, group, id...)}; pick: market_data._pick.
    Sessions that already have a snapshot are skipped, so a live snapshot always wins over a reconstructed one."""
    dates_by = {}
    for sym, b in series.items():
        if b and b.get("c"):
            off = b.get("tz_off") or 0
            dates_by[sym] = [bar_date(t, off) for t in b["t"]]
    all_dates = sorted({d for ds in dates_by.values() for d in ds[-(days + 1):]})
    with _LOCK:
        con = _db()
        try:
            have = {r[0] for r in con.execute("SELECT DISTINCT snap FROM signals WHERE kind=?", (kind,))}
        finally:
            con.close()
    todo = [d for d in all_dates[-days:] if d not in have]
    written = 0
    for snap in todo:
        rows = []
        for sym, b in series.items():
            ds = dates_by.get(sym)
            if not ds:
                continue
            # last bar at or before the snapshot date
            k = _bisect_right(ds, snap) - 1
            if k < 60 or ds[k] != snap:
                continue
            cut = {key: (b[key][:k + 1] if isinstance(b.get(key), list) else b.get(key)) for key in ("t", "o", "h", "l", "c", "v")}
            a = mi.analyze(cut, kind_analyze)
            if not a:
                continue
            row = dict(meta.get(sym) or {})
            row.update(a)
            row.setdefault("symbol", sym)
            row["bar_date"] = snap
            rows.append(row)
        if len(rows) >= 3:
            written += save_snapshot(kind, snap, rows, pick(rows, kind), source="backtest")
    return written


def _bisect_right(a: list, x: str) -> int:
    lo, hi = 0, len(a)
    while lo < hi:
        mid = (lo + hi) // 2
        if x < a[mid]:
            hi = mid
        else:
            lo = mid + 1
    return lo


# ---------------------------------------------------------------- accuracy

def accuracy(kind: str, horizon: int = HORIZON, days: int = 90) -> dict:
    """Grade snapshots against the close `horizon` sessions later. Pure statistics, no advice."""
    cl = closes(kind)
    with _LOCK:
        con = _db()
        try:
            snaps = [r[0] for r in con.execute(
                "SELECT DISTINCT snap FROM signals WHERE kind=? ORDER BY snap DESC LIMIT ?", (kind, days))]
            rows = list(con.execute(
                "SELECT snap, symbol, bar_date, price, score, move, exp5, rsi, list, source FROM signals "
                "WHERE kind=? AND snap>=?", (kind, min(snaps) if snaps else "9999")))
        finally:
            con.close()
    graded = []
    pending = 0
    for snap, sym, bd, price, score, move, exp5, rsi, lst, src in rows:
        series = cl.get(sym)
        if not series or not price:
            continue
        ds, cs = series
        k = _bisect_right(ds, bd) - 1
        if k < 0 or ds[k] != bd:
            continue
        if k + horizon >= len(cs):
            pending += 1
            continue
        fwd = (cs[k + horizon] / price - 1) * 100
        graded.append({"snap": snap, "symbol": sym, "fwd": fwd, "list": lst, "exp5": exp5, "move": move,
                       "score": score, "source": src})
    out = {"kind": kind, "horizon": horizon, "graded": len(graded), "pending": pending,
           "days": len({g["snap"] for g in graded}), "snapshots": len(snaps),
           "live_days": len({g["snap"] for g in graded if g["source"] == "live"})}
    if not graded:
        return out

    def mean(xs):
        return sum(xs) / len(xs) if xs else None

    market = [g["fwd"] for g in graded]
    out["market_avg"] = round(mean(market), 2)
    out["market_up"] = round(sum(1 for x in market if x > 0) / len(market) * 100, 1)

    def grade(name, want_up):
        xs = [g["fwd"] for g in graded if g["list"] == name]
        if not xs:
            return {"n": 0}
        hit = sum(1 for x in xs if (x > 0 if want_up else x < 0)) / len(xs) * 100
        return {"n": len(xs), "hit": round(hit, 1), "avg": round(mean(xs), 2),
                "excess": round(mean(xs) - out["market_avg"], 2)}

    out["potential"] = grade("potential", True)
    out["rebound"] = grade("rebound", True)
    out["risk"] = grade("risk", False)
    mv = [abs(g["fwd"]) for g in graded if g["list"] == "movers"]
    allabs = mean([abs(x) for x in market])
    out["movers"] = {"n": len(mv), "avg_abs": round(mean(mv), 2) if mv else None, "market_abs": round(allabs, 2),
                     "ratio": round(mean(mv) / allabs, 2) if mv and allabs else None}
    rng = [g for g in graded if g["exp5"]]
    out["range_hit"] = round(sum(1 for g in rng if abs(g["fwd"]) <= g["exp5"]) / len(rng) * 100, 1) if rng else None
    # score buckets: does a higher trend score come with a better next 5 sessions?
    buckets = []
    for lo, hi, key in ((-101, -50, "strong_neg"), (-50, -20, "neg"), (-20, 20, "neutral"), (20, 50, "pos"), (50, 101, "strong_pos")):
        xs = [g["fwd"] for g in graded if g["score"] is not None and lo <= g["score"] < hi]
        buckets.append({"band": key, "n": len(xs), "avg": round(mean(xs), 2) if xs else None})
    out["buckets"] = buckets
    # per-snapshot series for the chart, oldest first
    by_day = {}
    for g in graded:
        by_day.setdefault(g["snap"], []).append(g)
    series = []
    for d in sorted(by_day):
        gs = by_day[d]
        pot = [g["fwd"] for g in gs if g["list"] == "potential"]
        series.append({"d": d, "market": round(mean([g["fwd"] for g in gs]), 2),
                       "potential": round(mean(pot), 2) if pot else None,
                       "live": any(g["source"] == "live" for g in gs)})
    out["series"] = series
    return out


def stats() -> dict:
    with _LOCK:
        con = _db()
        try:
            b = dict(con.execute("SELECT kind, COUNT(*) FROM bars GROUP BY kind").fetchall())
            s = dict(con.execute("SELECT kind, COUNT(DISTINCT snap) FROM signals GROUP BY kind").fetchall())
            first = dict(con.execute("SELECT kind, MIN(date) FROM bars GROUP BY kind").fetchall())
        finally:
            con.close()
    try:
        size = _path().stat().st_size
    except Exception:
        size = 0
    return {"bars": b, "snapshots": s, "first_bar": first, "size": size}


def _json(o) -> str:
    return json.dumps(o, ensure_ascii=False, default=lambda x: None if isinstance(x, float) and math.isnan(x) else str(x))
