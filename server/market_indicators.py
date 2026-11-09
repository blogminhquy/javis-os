"""market_indicators.py - pure technical-analysis maths for the Markets page.

No I/O and no third-party libraries (numpy is not a Javis dependency), so every function here is
testable on plain lists. Input series are oldest-first lists of floats.

`analyze(bars)` is the one entry point the data layer uses: it turns daily OHLCV bars into one flat
dict of indicators, a trend score, a volatility outlook and machine-readable reason codes. The
dashboard turns the codes into words through i18n, so nothing here is user-facing text.

These are statistical signals computed from past prices. They describe the current state of a
chart; they are not forecasts of price and not investment advice. The UI says so next to them.
"""
from __future__ import annotations

import math
from typing import Iterable

TRADING_DAYS = {"stock": 252, "crypto": 365}


def _clean(xs: Iterable) -> list[float]:
    out = []
    for x in xs:
        try:
            v = float(x)
        except (TypeError, ValueError):
            continue
        if math.isfinite(v):
            out.append(v)
    return out


def sma(xs: list[float], n: int) -> list[float | None]:
    out: list[float | None] = [None] * len(xs)
    s = 0.0
    for i, x in enumerate(xs):
        s += x
        if i >= n:
            s -= xs[i - n]
        if i >= n - 1:
            out[i] = s / n
    return out


def ema(xs: list[float], n: int) -> list[float | None]:
    out: list[float | None] = [None] * len(xs)
    if len(xs) < n:
        return out
    k = 2.0 / (n + 1)
    e = sum(xs[:n]) / n
    out[n - 1] = e
    for i in range(n, len(xs)):
        e = xs[i] * k + e * (1 - k)
        out[i] = e
    return out


def rsi(xs: list[float], n: int = 14) -> list[float | None]:
    """Wilder's RSI."""
    out: list[float | None] = [None] * len(xs)
    if len(xs) <= n:
        return out
    gain = loss = 0.0
    for i in range(1, n + 1):
        d = xs[i] - xs[i - 1]
        gain += max(d, 0.0)
        loss += max(-d, 0.0)
    gain /= n
    loss /= n
    out[n] = 100.0 if loss == 0 else 100 - 100 / (1 + gain / loss)
    for i in range(n + 1, len(xs)):
        d = xs[i] - xs[i - 1]
        gain = (gain * (n - 1) + max(d, 0.0)) / n
        loss = (loss * (n - 1) + max(-d, 0.0)) / n
        out[i] = 100.0 if loss == 0 else 100 - 100 / (1 + gain / loss)
    return out


def macd(xs: list[float], fast: int = 12, slow: int = 26, sig: int = 9):
    ef, es = ema(xs, fast), ema(xs, slow)
    line: list[float | None] = [(a - b) if (a is not None and b is not None) else None for a, b in zip(ef, es)]
    start = next((i for i, v in enumerate(line) if v is not None), None)
    signal: list[float | None] = [None] * len(xs)
    if start is not None:
        seg = ema([v for v in line[start:] if v is not None], sig)
        for j, v in enumerate(seg):
            signal[start + j] = v
    hist = [(a - b) if (a is not None and b is not None) else None for a, b in zip(line, signal)]
    return line, signal, hist


def bollinger(xs: list[float], n: int = 20, k: float = 2.0):
    mid = sma(xs, n)
    up: list[float | None] = [None] * len(xs)
    lo: list[float | None] = [None] * len(xs)
    width: list[float | None] = [None] * len(xs)
    for i in range(n - 1, len(xs)):
        w = xs[i - n + 1:i + 1]
        m = mid[i]
        sd = math.sqrt(sum((x - m) ** 2 for x in w) / n)
        up[i], lo[i] = m + k * sd, m - k * sd
        width[i] = (up[i] - lo[i]) / m if m else None
    return mid, up, lo, width


def atr(h: list[float], low: list[float], c: list[float], n: int = 14) -> list[float | None]:
    out: list[float | None] = [None] * len(c)
    if len(c) <= n:
        return out
    trs = [h[0] - low[0]]
    for i in range(1, len(c)):
        trs.append(max(h[i] - low[i], abs(h[i] - c[i - 1]), abs(low[i] - c[i - 1])))
    a = sum(trs[1:n + 1]) / n
    out[n] = a
    for i in range(n + 1, len(c)):
        a = (a * (n - 1) + trs[i]) / n
        out[i] = a
    return out


def log_returns(xs: list[float]) -> list[float]:
    return [math.log(xs[i] / xs[i - 1]) for i in range(1, len(xs)) if xs[i - 1] > 0 and xs[i] > 0]


def stdev(xs: list[float]) -> float:
    if len(xs) < 2:
        return 0.0
    m = sum(xs) / len(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1))


def ewma_vol(rets: list[float], lam: float = 0.94) -> float:
    """RiskMetrics EWMA daily volatility (fraction, not %)."""
    if len(rets) < 10:
        return stdev(rets)
    var = sum(r * r for r in rets[:20]) / min(20, len(rets))
    for r in rets[20:]:
        var = lam * var + (1 - lam) * r * r
    return math.sqrt(var)


def max_drawdown(xs: list[float]) -> float:
    peak, mdd = -math.inf, 0.0
    for x in xs:
        peak = max(peak, x)
        if peak > 0:
            mdd = min(mdd, x / peak - 1)
    return mdd


def pct_rank(window: list[float], value: float) -> float:
    """Share of `window` at or below `value`, 0..1."""
    if not window:
        return 0.5
    return sum(1 for w in window if w <= value) / len(window)


def _chg(c: list[float], n: int) -> float | None:
    if len(c) > n and c[-1 - n]:
        return (c[-1] / c[-1 - n] - 1) * 100
    return None


def _r(v, nd=2):
    return None if v is None else round(v, nd)


def score_label(score: float) -> str:
    if score >= 50:
        return "strong_pos"
    if score >= 20:
        return "pos"
    if score > -20:
        return "neutral"
    if score > -50:
        return "neg"
    return "strong_neg"


def analyze(bars: dict, kind: str = "stock") -> dict:
    """Indicators + signal for one instrument.

    `bars` is {"t": [...], "o": [...], "h": [...], "l": [...], "c": [...], "v": [...]}, oldest first,
    daily. Missing o/h/l fall back to the close. Returns {} when there are fewer than 2 closes.
    """
    c = _clean(bars.get("c") or [])
    n = len(c)
    if n < 2:
        return {}

    def _ser(key):
        s = _clean(bars.get(key) or [])
        return s if len(s) == n else list(c)

    h, low, o = _ser("h"), _ser("l"), _ser("o")
    v = _clean(bars.get("v") or [])
    if len(v) != n:
        v = [0.0] * n
    year = TRADING_DAYS.get(kind, 252)
    last = c[-1]
    out: dict = {"price": last, "prev": c[-2], "bars": n}

    out["chg_1d"] = _r(_chg(c, 1))
    out["chg_5d"] = _r(_chg(c, 5))
    out["chg_1m"] = _r(_chg(c, 21 if kind == "stock" else 30))
    out["chg_3m"] = _r(_chg(c, 63 if kind == "stock" else 90))
    out["chg_1y"] = _r(_chg(c, min(year, n - 1))) if n > 60 else None

    win = c[-year:]
    hi52, lo52 = max(win), min(win)
    out["high_52w"], out["low_52w"] = hi52, lo52
    out["from_high"] = _r((last / hi52 - 1) * 100) if hi52 else None
    out["from_low"] = _r((last / lo52 - 1) * 100) if lo52 else None
    out["drawdown_1y"] = _r(max_drawdown(win) * 100)

    s20, s50, s200 = sma(c, 20)[-1], sma(c, 50)[-1], sma(c, 200)[-1]
    out["sma20"], out["sma50"], out["sma200"] = _r(s20, 4), _r(s50, 4), _r(s200, 4)
    r = rsi(c, 14)
    out["rsi"] = _r(r[-1], 1)
    ml, ms, mh = macd(c)
    out["macd"], out["macd_signal"], out["macd_hist"] = _r(ml[-1], 4), _r(ms[-1], 4), _r(mh[-1], 4)

    _, bu, bl, bw = bollinger(c)
    out["bb_up"], out["bb_low"] = _r(bu[-1], 4), _r(bl[-1], 4)
    bw_hist = [x for x in bw[-120:] if x is not None]
    out["bb_width"] = _r(bw[-1] * 100 if bw[-1] is not None else None)
    out["bb_rank"] = _r(pct_rank(bw_hist, bw[-1]) * 100, 0) if bw[-1] is not None and len(bw_hist) >= 30 else None

    a14 = atr(h, low, c, 14)
    a5 = atr(h, low, c, 5)
    out["atr_pct"] = _r(a14[-1] / last * 100) if a14[-1] and last else None
    atr_exp = (a5[-1] / a14[-1]) if (a5[-1] and a14[-1]) else None
    out["atr_expansion"] = _r(atr_exp)

    rets = log_returns(c)
    hv20 = stdev(rets[-20:]) * math.sqrt(year) * 100 if len(rets) >= 20 else None
    hv120 = stdev(rets[-120:]) * math.sqrt(year) * 100 if len(rets) >= 60 else None
    ew = ewma_vol(rets[-250:])
    out["hv20"], out["hv120"] = _r(hv20), _r(hv120)
    out["vol_daily"] = _r(ew * 100)
    out["exp_move_1d"] = _r(ew * 100)
    out["exp_move_5d"] = _r(ew * math.sqrt(5) * 100)
    out["exp_move_20d"] = _r(ew * math.sqrt(20) * 100)
    out["range_5d"] = [_r(last * math.exp(-ew * math.sqrt(5)), 4), _r(last * math.exp(ew * math.sqrt(5)), 4)]

    vol_avg20 = (sum(v[-21:-1]) / 20) if n > 21 and any(v[-21:-1]) else None
    out["volume"] = v[-1]
    out["vol_avg20"] = _r(vol_avg20, 0)
    out["vol_ratio"] = _r(v[-1] / vol_avg20) if vol_avg20 else None
    out["value"] = _r(v[-1] * last, 0) if v[-1] else None

    # ---- trend score, -100..100 ----
    sc = 0.0
    reasons: list[str] = []
    if s20:
        sc += 8 if last > s20 else -8
    if s50:
        sc += 12 if last > s50 else -12
    if s200:
        sc += 12 if last > s200 else -12
        reasons.append("above_sma200" if last > s200 else "below_sma200")
    if s50 and s200:
        sc += 8 if s50 > s200 else -8
        s50p, s200p = sma(c[:-5], 50)[-1], sma(c[:-5], 200)[-1] if n > 205 else None
        if s50p and s200p:
            if s50p <= s200p and s50 > s200:
                reasons.append("golden_cross")
            elif s50p >= s200p and s50 < s200:
                reasons.append("death_cross")
    m1, m3 = out["chg_1m"], out["chg_3m"]
    if m1 is not None:
        sc += math.tanh(m1 / 10) * 12
    if m3 is not None:
        sc += math.tanh(m3 / 20) * 10
    if mh[-1] is not None:
        sc += 8 if mh[-1] > 0 else -8
        if len(mh) > 3 and mh[-4] is not None:
            if mh[-4] <= 0 < mh[-1]:
                reasons.append("macd_bull_cross")
            elif mh[-4] >= 0 > mh[-1]:
                reasons.append("macd_bear_cross")
    rv = r[-1]
    if rv is not None:
        if rv >= 75:
            sc -= 5
            reasons.append("rsi_overbought")
        elif rv >= 50:
            sc += 10
        elif rv <= 25:
            sc += 5
            reasons.append("rsi_oversold")
        else:
            sc -= 5
    vr = out["vol_ratio"]
    if vr is not None and vr >= 1.5 and out["chg_1d"] is not None:
        if out["chg_1d"] > 0:
            sc += 10
            reasons.append("volume_up")
        elif out["chg_1d"] < 0:
            sc -= 10
            reasons.append("volume_down")
    if out["from_high"] is not None and out["from_high"] >= -1.0 and n > 120:
        reasons.append("near_52w_high")
    if out["from_low"] is not None and out["from_low"] <= 1.0 and n > 120:
        reasons.append("near_52w_low")
    sc = max(-100.0, min(100.0, sc))
    out["score"] = round(sc)
    out["signal"] = score_label(sc)
    if s20 and s50:
        out["trend"] = "up" if last > s20 > s50 else ("down" if last < s20 < s50 else "side")
    else:
        out["trend"] = "side"

    # ---- chance of a strong move, 0..100 (direction-free) ----
    mv = 0.0
    if out["bb_rank"] is not None and out["bb_rank"] <= 20:
        mv += 35
        reasons.append("squeeze")
    elif out["bb_rank"] is not None and out["bb_rank"] <= 35:
        mv += 15
    if vr is not None:
        mv += 30 if vr >= 2.5 else (20 if vr >= 1.5 else 0)
    if atr_exp is not None and atr_exp >= 1.3:
        mv += 20
        reasons.append("atr_expanding")
    if (out["from_high"] is not None and out["from_high"] >= -3) or (out["from_low"] is not None and out["from_low"] <= 3):
        mv += 15
    if hv20 and hv120 and hv20 > hv120 * 1.25:
        mv += 10
        reasons.append("vol_rising")
    out["move_score"] = int(min(100, mv))
    out["vol_regime"] = ("squeeze" if "squeeze" in reasons else
                         "expanding" if ("atr_expanding" in reasons or "vol_rising" in reasons) else "normal")
    out["reasons"] = reasons
    out["spark"] = [round(x, 6) for x in c[-60:]]
    return out


def series_for_chart(bars: dict) -> dict:
    """Full indicator lines for the detail chart, aligned with bars["t"]."""
    c = _clean(bars.get("c") or [])
    n = len(c)
    h = _clean(bars.get("h") or [])
    low = _clean(bars.get("l") or [])
    if len(h) != n:
        h = list(c)
    if len(low) != n:
        low = list(c)

    def rr(xs, nd=4):
        return [None if x is None else round(x, nd) for x in xs]

    mid, up, lo, _ = bollinger(c)
    ml, ms, mh = macd(c)
    return {
        "sma20": rr(sma(c, 20)), "sma50": rr(sma(c, 50)), "sma200": rr(sma(c, 200)),
        "bb_up": rr(up), "bb_low": rr(lo), "rsi": rr(rsi(c, 14), 2),
        "macd": rr(ml, 5), "macd_signal": rr(ms, 5), "macd_hist": rr(mh, 5),
    }


def regime(rows: list[dict], bench: dict | None = None) -> dict:
    """Market-wide state from many analyzed rows."""
    rows = [r for r in rows if r]
    if not rows:
        return {"label": "unknown", "count": 0}
    k = len(rows)
    up = sum(1 for r in rows if (r.get("chg_1d") or 0) > 0)
    down = sum(1 for r in rows if (r.get("chg_1d") or 0) < 0)
    a50 = [r for r in rows if r.get("sma50")]
    a200 = [r for r in rows if r.get("sma200")]
    br50 = sum(1 for r in a50 if r["price"] > r["sma50"]) / len(a50) * 100 if a50 else None
    br200 = sum(1 for r in a200 if r["price"] > r["sma200"]) / len(a200) * 100 if a200 else None
    avg_score = sum(r.get("score", 0) for r in rows) / k
    avg_move = sum(r.get("move_score", 0) for r in rows) / k
    hot = sum(1 for r in rows if r.get("move_score", 0) >= 50)
    comp = avg_score * 0.6
    if br50 is not None:
        comp += (br50 - 50) * 0.5
    if bench and bench.get("score") is not None:
        comp += bench["score"] * 0.3
    comp = max(-100.0, min(100.0, comp))
    label = "risk_on" if comp >= 20 else ("risk_off" if comp <= -20 else "neutral")
    bench_vol = None
    if bench and bench.get("hv20") and bench.get("hv120"):
        ratio = bench["hv20"] / bench["hv120"]
        bench_vol = "rising" if ratio >= 1.2 else ("falling" if ratio <= 0.8 else "stable")
    return {
        "label": label, "score": round(comp), "count": k, "advancers": up, "decliners": down,
        "breadth50": _r(br50, 0), "breadth200": _r(br200, 0), "avg_score": round(avg_score),
        "avg_move": round(avg_move), "hot": hot, "vol_trend": bench_vol,
    }
