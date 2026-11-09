# -*- coding: utf-8 -*-
"""Bundled plugin: market data for every engine.

`javis_market` (readonly) reads the same data as the Markets page (server/market_data.py): Vietnam
stocks and indices, world indices, commodities, FX, rates, big global stocks and crypto, with
technical indicators, a trend score, a chance-of-strong-move score and the expected 5-day range.
`javis_market_watch` (safe) adds or removes a symbol on the page's watchlist.

The tool returns compact Vietnamese text for the model (tool text sent to models stays Vietnamese,
see docs/dev/them-mot-ngon-ngu.md). It never returns advice: the scores are statistics of past
prices and the description tells the model to say so.
"""
from __future__ import annotations

import time

import market_data as md

_MARKETS = ("vn", "world", "crypto")
_LABEL = {"vn": "Chứng khoán Việt Nam", "world": "Thế giới", "crypto": "Tiền số"}
_REGIME = {"risk_on": "ưa rủi ro (tích cực)", "neutral": "trung tính", "risk_off": "né rủi ro (tiêu cực)",
           "unknown": "chưa đủ dữ liệu"}


def _f(v, nd=2, pct=False):
    if v is None:
        return "-"
    return (f"{v:+.{nd}f}%" if pct else f"{v:,.{nd}f}")


def _regime_line(name: str, s: dict) -> str:
    r = s.get("regime") or {}
    bits = [f"{_LABEL[name]}: trạng thái {_REGIME.get(r.get('label'), r.get('label'))} (điểm {r.get('score')})",
            f"tăng/giảm phiên gần nhất {r.get('advancers')}/{r.get('decliners')} mã",
            f"độ rộng trên MA50 {r.get('breadth50')}%, trên MA200 {r.get('breadth200')}%",
            f"{r.get('hot')} mã có khả năng biến động mạnh"]
    if r.get("vix") is not None:
        bits.append(f"VIX {r['vix']} ({r.get('vix_level')})")
    if r.get("fng") is not None:
        bits.append(f"Fear & Greed {r['fng']} ({r.get('fng_label')})")
    if r.get("vol_trend"):
        bits.append(f"biến động chỉ số chuẩn: {r['vol_trend']}")
    return "; ".join(bits)


def _list(title: str, rows: list) -> str:
    if not rows:
        return f"{title}: (không có mã nào đạt tiêu chí)"
    return title + ":\n" + "\n".join("  - " + md.digest_row(r) for r in rows)


async def _overview(markets) -> str:
    o = await md.overview()
    out = [f"Số liệu lúc {time.strftime('%Y-%m-%d %H:%M', time.localtime(o.get('at') or time.time()))}."]
    for name in markets:
        s = (o.get("sections") or {}).get(name) or {}
        if s.get("error"):
            out.append(f"{_LABEL[name]}: lỗi nguồn dữ liệu ({s['error']}).")
            continue
        out.append(_regime_line(name, s) + (" [dữ liệu cũ do nguồn lỗi]" if s.get("stale") else ""))
        if name == "vn":
            out.append("Chỉ số: " + "; ".join(f"{i['symbol']} {_f(i.get('price'))} ({_f(i.get('chg_1d'), pct=True)})"
                                              for i in s.get("indices") or []))
            secs = s.get("sectors") or []
            out.append("Ngành (TB % 1 phiên): " + "; ".join(f"{x['sector']} {_f(x.get('chg_1d'), pct=True)}" for x in secs))
        if name in ("world", "crypto"):
            out.append("Chính: " + "; ".join(f"{k.get('name') or k['symbol']} {_f(k.get('price'))} ({_f(k.get('chg_1d'), pct=True)})"
                                             for k in s.get("key") or []))
        if name == "crypto" and s.get("global"):
            g = s["global"]
            out.append(f"Vốn hoá tổng {_f((g.get('mcap') or 0) / 1e9, 0)} tỷ USD ({_f(g.get('mcap_chg_24h'), pct=True)} 24h), "
                       f"BTC dominance {g.get('btc_dom')}%")
        out.append("Tăng mạnh nhất: " + ", ".join(f"{r['symbol']} {_f(r.get('chg_1d'), pct=True)}" for r in s.get("top_up") or []))
        out.append("Giảm mạnh nhất: " + ", ".join(f"{r['symbol']} {_f(r.get('chg_1d'), pct=True)}" for r in s.get("top_down") or []))
    return "\n".join(out)


async def _outlook(markets) -> str:
    o = await md.overview()
    out = []
    for name in markets:
        s = (o.get("sections") or {}).get(name) or {}
        ol = s.get("outlook") or {}
        out.append(f"== {_LABEL[name]} == {_regime_line(name, s)}")
        out.append(_list("Xu hướng tích cực, chưa quá mua (tiềm năng)", ol.get("potential")))
        out.append(_list("Khả năng biến động mạnh (không chỉ hướng)", ol.get("movers")))
        out.append(_list("Rủi ro (xu hướng xấu hoặc quá mua)", ol.get("risk")))
        out.append(_list("Quá bán trong xu hướng dài còn giữ (có thể hồi)", ol.get("rebound")))
    return "\n".join(out)


async def _section(name: str, limit: int, sort: str) -> str:
    s = await md.section(name)
    rows = s.get("rows") or []
    key = {"score": lambda r: -(r.get("score") or 0), "change": lambda r: -(r.get("chg_1d") or 0),
           "move": lambda r: -(r.get("move_score") or 0), "drop": lambda r: (r.get("chg_1d") or 0)}.get(sort)
    if key:
        rows = sorted(rows, key=key)
    head = _regime_line(name, s)
    if name == "vn":
        head += "\nChỉ số: " + "; ".join(md.digest_row(i) for i in s.get("indices") or [])
    return head + "\n" + _list(f"{len(rows)} mã, hiện {min(limit, len(rows))}", rows[:limit])


async def _symbol(name: str, symbol: str) -> str:
    h = await md.history(name, symbol)
    if not h.get("ok"):
        return f"Không tìm thấy mã '{symbol}' trong {_LABEL[name]}. Với tiền số dùng ticker (btc) hoặc id CoinGecko; với thế giới dùng mã Yahoo (AAPL, ^GSPC, GC=F)."
    a = h["analysis"]
    a["symbol"] = h["symbol"]
    lines = [f"{h['name']} ({h['symbol']}, {_LABEL[name]}, {h.get('currency')}) - {len(h['bars']['c'])} phiên dữ liệu ngày",
             md.digest_row(a),
             f"MA20 {_f(a.get('sma20'))}, MA50 {_f(a.get('sma50'))}, MA200 {_f(a.get('sma200'))}; MACD hist {_f(a.get('macd_hist'), 4)}; "
             f"Bollinger {_f(a.get('bb_low'))} - {_f(a.get('bb_up'))} (độ rộng xếp hạng {a.get('bb_rank')}/100)",
             f"Biến động lịch sử 20 phiên {_f(a.get('hv20'))}%/năm, 120 phiên {_f(a.get('hv120'))}%/năm; ATR {_f(a.get('atr_pct'))}%",
             f"Đỉnh/đáy 52 tuần {_f(a.get('high_52w'))}/{_f(a.get('low_52w'))} (cách đỉnh {_f(a.get('from_high'), pct=True)}); "
             f"sụt giảm tối đa 1 năm {_f(a.get('drawdown_1y'), pct=True)}",
             f"Khoảng giá 5 phiên tới theo biến động hiện tại (~68%): {_f((a.get('range_5d') or [None])[0])} - {_f((a.get('range_5d') or [None, None])[1])}",
             f"Khối lượng so với TB 20 phiên: {_f(a.get('vol_ratio'))} lần; 3 tháng {_f(a.get('chg_3m'), pct=True)}, 1 năm {_f(a.get('chg_1y'), pct=True)}"]
    return "\n".join(lines)


async def _accuracy(markets) -> str:
    import asyncio
    import market_store as ms
    out = []
    for name in markets:
        a = await asyncio.to_thread(ms.accuracy, name)
        if not a.get("graded"):
            out.append(f"{_LABEL[name]}: chưa đủ dữ liệu để chấm (cần ít nhất 5 phiên sau lần chụp đầu tiên).")
            continue
        p, r, mv = a.get("potential") or {}, a.get("risk") or {}, a.get("movers") or {}
        out.append(
            f"{_LABEL[name]} ({a['days']} phiên đã chấm, {a.get('live_days', 0)} phiên chụp thật, còn lại dựng lại từ lịch sử giá): "
            f"toàn thị trường TB {_f(a.get('market_avg'), pct=True)} sau 5 phiên. "
            f"Nhóm tiềm năng: {p.get('hit', '-')}% tăng, TB {_f(p.get('avg'), pct=True)} (hơn thị trường {_f(p.get('excess'), pct=True)}). "
            f"Nhóm rủi ro: {r.get('hit', '-')}% giảm, TB {_f(r.get('avg'), pct=True)}. "
            f"Nhóm sắp biến động: biên độ {mv.get('ratio', '-')} lần mức chung. "
            f"Giá nằm trong khoảng dự kiến {a.get('range_hit', '-')}% số lần (mục tiêu 68%).")
    return "\n".join(out)


async def _portfolio(markets) -> str:
    import asyncio
    import market_paper as mp
    out = ["Tài khoản đầu tư ẢO (giao dịch giả lập bằng giá thật, không có tiền thật):"]
    for name in markets:
        try:
            data = await md.section(name)
        except Exception:
            data = {}
        rep = await asyncio.to_thread(mp.report, name, data)
        ccy = mp.PARAMS[name]["ccy"]
        if not rep.get("started"):
            out.append(f"{_LABEL[name]}: chưa bắt đầu (bấm Bắt đầu ở tab Đầu tư ảo của trang Thị trường).")
            continue
        st = rep["stats"]
        out.append(
            f"== {_LABEL[name]} ({'đang chạy' if rep['running'] else 'tạm dừng'}, {st['days']:.0f} ngày) == "
            f"giá trị {_f(st['equity'], 0)} {ccy}, lãi/lỗ {_f(st['pnl'], 0)} {ccy} ({_f(st['pnl_pct'], pct=True)}), "
            f"chỉ số chuẩn {_f(st['bench_return'], pct=True)}, tiền mặt {_f(st['cash'], 0)}, đang đầu tư {st['exposure']:.0f}%, "
            f"{st['closed']} lệnh đã đóng, tỉ lệ thắng {_f(st['win_rate'], 0)}%, sụt giảm tối đa {_f(st['max_drawdown'], pct=True)}, "
            f"phí {_f(st['fees'], 0)} {ccy}.")
        for x in rep["positions"][:10]:
            out.append(f"  - giữ {x['symbol_label']}: {x['qty']:g} @ {_f(x['avg'])} -> {_f(x['price'])} "
                       f"({_f(x['pnl_pct'], pct=True)}), tỷ trọng {x['weight']:.1f}%, cắt lỗ {_f(x['stop'])}")
        for t in rep["trades"][:6]:
            out.append(f"  - lệnh {t['side']} {t['symbol']} {t['qty']:g} @ {_f(t['price'])} ({t['reason']})"
                       + (f", lãi/lỗ {_f(t['pnl'], 0)} {ccy}" if t.get("pnl") is not None else ""))
        if rep["log"]:
            w = rep["log"][0].get("watch") or []
            if w:
                out.append("  Đang chờ điểm mua: " + ", ".join(
                    f"{x['symbol']} ({x['why']}" + (f", vùng {_f(x['zone'][0])}-{_f(x['zone'][1])}" if x.get("zone") else "") + ")"
                    for x in w[:8]))
    out.append("Đây là mô phỏng theo quy tắc cố định; không bảo đảm lợi nhuận.")
    return "\n".join(out)


def register(ctx):
    async def _market(args, cctx):
        args = args or {}
        op = str(args.get("op") or "overview").strip().lower()
        market = str(args.get("market") or "").strip().lower()
        markets = [market] if market in _MARKETS else list(_MARKETS)
        try:
            if op == "overview":
                return await _overview(markets)
            if op == "outlook":
                return await _outlook(markets)
            if op == "section":
                if market not in _MARKETS:
                    return "ERROR: op=section cần market là vn, world hoặc crypto."
                return await _section(market, max(5, min(int(args.get("limit") or 30), 150)),
                                      str(args.get("sort") or "score"))
            if op == "symbol":
                sym = str(args.get("symbol") or "").strip()
                if not sym or market not in _MARKETS:
                    return "ERROR: op=symbol cần symbol và market (vn, world, crypto)."
                return await _symbol(market, sym)
            if op == "accuracy":
                return await _accuracy(markets)
            if op == "portfolio":
                return await _portfolio(markets)
            if op == "watchlist":
                wl = md.watchlist()
                return "Danh sách theo dõi: " + "; ".join(f"{_LABEL[k]}: {', '.join(v) or '(trống)'}" for k, v in wl.items())
        except Exception as e:
            return f"ERROR: không lấy được dữ liệu thị trường ({str(e)[:160]}). Thử lại sau ít phút."
        return "ERROR: op phải là overview, outlook, section, symbol hoặc watchlist."

    ctx.register_tool(
        name="javis_market",
        description=(
            "Số liệu thị trường THẬT (cập nhật vài phút một lần) của trang Thị trường: chứng khoán Việt Nam "
            "(VN-Index, VN30, HNX, UPCoM, ~75 mã lớn theo ngành), chỉ số thế giới, vàng, dầu, tỷ giá, lợi suất, "
            "cổ phiếu lớn toàn cầu, và top 100 tiền số. GỌI TOOL NÀY khi người dùng hỏi giá, diễn biến, mã nào "
            "tăng/giảm, mã nào tiềm năng hay sắp biến động. "
            "op: overview (tổng hợp), outlook (danh sách tiềm năng / dễ biến động mạnh / rủi ro / có thể hồi), "
            "section (bảng một thị trường, sort=score|change|drop|move), symbol (phân tích kỹ một mã), "
            "accuracy (tín hiệu các phiên trước đúng tới đâu sau 5 phiên: nêu kèm khi đưa ra nhận định), "
            "portfolio (tài khoản ĐẦU TƯ ẢO: VN 1 tỷ đ, coin 20.000 USD, thế giới 20.000 USD; giá trị, lãi lỗ, so với "
            "chỉ số chuẩn, vị thế, lệnh gần nhất kèm lý do), watchlist. "
            "market: vn | world | crypto. symbol: mã VN (FPT), mã Yahoo (AAPL, ^GSPC, GC=F) hoặc ticker coin (btc). "
            "Điểm xu hướng (-100..100) và 'khả năng biến động mạnh' (0..100) là THỐNG KÊ từ giá quá khứ, không phải "
            "dự báo chắc chắn: khi trả lời phải nói rõ đây là tín hiệu kỹ thuật, không phải khuyến nghị đầu tư."),
        handler=_market, min_mode="readonly", emoji="📈",
        schema={"type": "object", "properties": {
            "op": {"type": "string", "enum": ["overview", "outlook", "section", "symbol", "accuracy", "portfolio", "watchlist"]},
            "market": {"type": "string", "enum": ["vn", "world", "crypto"]},
            "symbol": {"type": "string", "description": "Mã cần xem khi op=symbol"},
            "sort": {"type": "string", "enum": ["score", "change", "drop", "move"]},
            "limit": {"type": "integer", "description": "Số dòng khi op=section (mặc định 30)"}},
            "required": ["op"]},
    )

    async def _watch(args, cctx):
        args = args or {}
        kind = str(args.get("market") or "").strip().lower()
        sym = str(args.get("symbol") or "").strip()
        if kind not in _MARKETS or not sym:
            return "ERROR: cần market (vn, world, crypto) và symbol."
        if str(args.get("op") or "add").lower() == "remove":
            md.watchlist_remove(kind, sym)
            return f"Đã bỏ {sym} khỏi danh sách theo dõi {_LABEL[kind]}."
        res = await md.watchlist_add(kind, sym)
        if not res.get("ok"):
            return f"ERROR: không tìm thấy mã '{sym}' ở nguồn dữ liệu {_LABEL[kind]}."
        return f"Đã thêm {res['symbol']} vào danh sách theo dõi {_LABEL[kind]}; trang Thị trường hiện nó ở đầu bảng."

    ctx.register_tool(
        name="javis_market_watch",
        description=("Thêm hoặc bỏ một mã khỏi danh sách theo dõi của trang Thị trường. Chỉ gọi khi người dùng "
                     "yêu cầu theo dõi / bỏ theo dõi một mã. op: add | remove; market: vn | world | crypto; symbol."),
        handler=_watch, min_mode="safe", emoji="⭐",
        schema={"type": "object", "properties": {
            "op": {"type": "string", "enum": ["add", "remove"]},
            "market": {"type": "string", "enum": ["vn", "world", "crypto"]},
            "symbol": {"type": "string"}},
            "required": ["market", "symbol"]},
    )
