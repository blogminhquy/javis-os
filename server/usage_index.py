"""
usage_index.py - Indexer + query cho dashboard token.

Quet log THO Claude (~/.claude/projects/**/*.jsonl) + Codex (~/.codex/sessions/**/rollout-*.jsonl),
parse TANG DAN (bo file chua doi theo size+mtime), phan loai hoat dong (chat vs nen) bang join
conversations.db, gop vao SQLite STATE_DIR/usage_index.db.

Nhanh API (openrouter/openai/anthropic) khong co log tho -> doc tu STATE_DIR/usage-events.jsonl
ma usage_store.record() ghi them (Task 5). Query: summary()/insights() (Task 6-7).

Grain luu: 1 file = 1 phien. Moi file dong gop nhieu dong file_daily theo
(day, provider, source, activity, model, project). File doi -> XOA het dong cu cua file roi
parse lai (idempotent, khong can offset). Rieng usage-events.jsonl la append-only nen dung offset.
"""
from __future__ import annotations

import glob
import json
import os
import sqlite3
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from config import STATE_DIR
import session_brain   # {session_id: brain} - nhan du an dung cho phien Javis (cwd luon la goc project)
import usage_parsers as up

_TZ = timezone(timedelta(hours=7))
PERIODS = ("today", "yesterday", "this_week", "last_week",
           "this_month", "last_month", "last_3_months", "this_year")

# Nguong sinh insight (chinh duoc)
CACHE_LOW = 0.5                 # cache hit duoi nguong = dang nap lai context nhieu
MIN_BILLABLE_FOR_CACHE = 200_000   # chi canh bao cache khi ky du lon (tranh nhieu)
BACKGROUND_SHARE = 0.25         # hoat dong ngam chiem qua % token
EXPENSIVE_SHARE = 0.5           # opus chiem qua % token
SESSION_BLOAT = 1_000_000       # 1 phien nap qua ngan nay token input
SPIKE_RATIO = 1.5               # token/ngay ky nay gap prev qua ngan nay lan

DB_PATH = STATE_DIR / "usage_index.db"
_EVENTS_PATH = STATE_DIR / "usage-events.jsonl"

_DIMS = {"provider", "source", "activity", "model", "project", "day"}
# provider API (chi nhung nay lay tu usage-events.jsonl; claude/codex lay tu log tho)
_API_PROVIDERS = {"openrouter", "openai", "anthropic", "anthropic-api", "oauth", "ollama"}


def _claude_dir() -> str:
    return os.getenv("JAVIS_CLAUDE_PROJECTS_DIR") or os.path.expanduser("~/.claude/projects")


def _codex_dir() -> str:
    return os.getenv("JAVIS_CODEX_SESSIONS_DIR") or os.path.expanduser("~/.codex/sessions")


def _conversations_db() -> Path:
    return STATE_DIR / "conversations.db"


def _connect() -> sqlite3.Connection:
    # WAL + busy_timeout: KHÔNG phải để nhanh (đo được _connect chỉ tốn 1,14ms trong 65ms
    # của summary(), tức DDL lặp lại chưa tới 1,5% - bỏ nó đi cũng chẳng đáng). Đây là chuyện
    # ĐÚNG SAI: từ 0.9.237 summary/insights chạy trong asyncio.to_thread, nên chúng đọc SONG
    # SONG với refresh() đang ghi. Chế độ journal mặc định cho người đọc và người ghi khoá lẫn
    # nhau -> "database is locked" ngay giữa lúc user mở trang Mức dùng. sessions.py:100-118 và
    # task_store.py:61-65 đều đã làm đúng, riêng kho này thì chưa.
    conn = sqlite3.connect(str(DB_PATH), timeout=5.0)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
    except sqlite3.OperationalError:
        pass   # ổ đĩa mạng / hệ tệp không hỗ trợ WAL -> chạy chế độ mặc định, vẫn đúng
    conn.execute("CREATE TABLE IF NOT EXISTS files_seen("
                 "path TEXT PRIMARY KEY, size INTEGER, mtime REAL, offset INTEGER DEFAULT 0)")
    conn.execute("CREATE TABLE IF NOT EXISTS file_daily("
                 "path TEXT, day TEXT, provider TEXT, source TEXT, activity TEXT, model TEXT, project TEXT,"
                 "input INTEGER, output INTEGER, cache_read INTEGER, cache_create INTEGER)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_fd_day ON file_daily(day)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_fd_path ON file_daily(path)")
    return conn


def _chat_sessions() -> set:
    """Tap cli_session_id trong conversations.db = cac phien do NGUOI DUNG mo (chat).
    Thieu file / loi -> set() (khong chan)."""
    p = _conversations_db()
    out = set()
    try:
        if p.exists():
            c = sqlite3.connect("file:%s?mode=ro" % p, uri=True)
            try:
                for (sid,) in c.execute(
                        "SELECT cli_session_id FROM sessions WHERE cli_session_id IS NOT NULL AND cli_session_id<>''"):
                    if sid:
                        out.add(sid)
            finally:
                c.close()
    except Exception:
        pass
    return out


def _unchanged(conn, path, size, mtime) -> bool:
    row = conn.execute("SELECT size, mtime FROM files_seen WHERE path=?", (path,)).fetchone()
    return bool(row) and row[0] == size and abs((row[1] or 0) - mtime) < 1e-6


def _mark(conn, path, size, mtime, offset=0) -> None:
    conn.execute("INSERT INTO files_seen(path,size,mtime,offset) VALUES(?,?,?,?) "
                 "ON CONFLICT(path) DO UPDATE SET size=excluded.size, mtime=excluded.mtime, offset=excluded.offset",
                 (path, size, mtime, offset))


def _clear_file(conn, path) -> None:
    conn.execute("DELETE FROM file_daily WHERE path=?", (path,))


def _insert_events(conn, path, events) -> None:
    """Gop events cua 1 file theo khoa (day,provider,source,activity,model,project) roi insert."""
    groups = {}
    for ev in events:
        k = (ev.get("day") or "", ev["provider"], ev["source"], ev["activity"], ev["model"], ev["project"])
        g = groups.setdefault(k, [0, 0, 0, 0])
        g[0] += ev["input"]
        g[1] += ev["output"]
        g[2] += ev["cache_read"]
        g[3] += ev["cache_create"]
    if groups:
        conn.executemany(
            "INSERT INTO file_daily(path,day,provider,source,activity,model,project,input,output,cache_read,cache_create)"
            " VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            [(path,) + k + tuple(g) for k, g in groups.items()])


def _scan_claude(conn, chat, brains) -> int:
    n = 0
    for path in glob.glob(os.path.join(_claude_dir(), "**", "*.jsonl"), recursive=True):
        try:
            st = os.stat(path)
        except OSError:
            continue
        if _unchanged(conn, path, st.st_size, st.st_mtime):
            continue
        _clear_file(conn, path)
        events = []
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                    except Exception:
                        continue
                    ev = up.parse_claude_line(obj, chat, brains)
                    if ev:
                        events.append(ev)
        except OSError:
            continue
        _insert_events(conn, path, events)
        _mark(conn, path, st.st_size, st.st_mtime)
        n += 1
    return n


def _scan_codex(conn) -> int:
    n = 0
    for path in glob.glob(os.path.join(_codex_dir(), "**", "rollout-*.jsonl"), recursive=True):
        try:
            st = os.stat(path)
        except OSError:
            continue
        if _unchanged(conn, path, st.st_size, st.st_mtime):
            continue
        _clear_file(conn, path)
        ev = up.parse_codex_file(path)
        if ev:
            _insert_events(conn, path, [ev])
        _mark(conn, path, st.st_size, st.st_mtime)
        n += 1
    return n


# Map provider trong usage-events.jsonl -> provider chuan cua index. cli = engine Claude (SDK),
# codex/openai-oauth = engine ChatGPT. Gom ve 'claude'/'codex' de tron dung cot voi log tho.
_EVENT_CLAUDE = {"cli", "claude", "anthropic-cli"}
_EVENT_CODEX = {"codex", "openai-oauth", "chatgpt", "oauth"}


def _ingest_events(conn) -> int:
    """Nap tu usage-events.jsonl (append-only, doc theo offset trong files_seen.offset).

    - Provider API (openrouter/openai/anthropic...) -> provider='api': day la NGUON DUY NHAT
      cho chung (khong co log tho).
    - cli/codex CUNG nap vao day (provider 'claude'/'codex') lam NGUON DU PHONG: engine ghi so
      token that vao usage-events moi luot, nen khi log tho KHONG co / khong doc duoc (ban Docker/
      VPS, doi HOME, volume moi...) thi bao cao van co so thay vi 0. Chong dem trung: sau moi
      refresh, _dedup_events_vs_raw() xoa dong-tu-event o NGAY da co log tho phu -> log tho luon
      thang, event chi lap cho phan log tho thieu.

    Tra so event moi nap lan nay."""
    path = str(_EVENTS_PATH)
    if not _EVENTS_PATH.exists():
        return 0
    try:
        raw = _EVENTS_PATH.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return 0
    lines = raw.splitlines()
    complete = len(lines)
    if raw and not raw.endswith("\n"):
        complete -= 1                       # dong cuoi con dang ghi do -> de lan sau

    row = conn.execute("SELECT offset FROM files_seen WHERE path=?", (path,)).fetchone()
    start = row[0] if row else 0
    if start > complete:                    # file bi cat/xoay -> nap lai tu dau
        conn.execute("DELETE FROM file_daily WHERE path=?", (path,))
        start = 0

    events = []
    for ln in lines[start:complete]:
        ln = ln.strip()
        if not ln:
            continue
        try:
            e = json.loads(ln)
        except Exception:
            continue
        prov = (e.get("provider") or "").lower()
        tin = int(e.get("in") or 0)
        tout = int(e.get("out") or 0)
        if tin + tout <= 0:
            continue
        day, model = e.get("day") or "", e.get("model") or "?"
        if prov in _API_PROVIDERS:
            events.append({"day": day, "provider": "api", "source": "javis", "activity": "chat",
                           "model": model, "project": "(api)",
                           "input": tin, "output": tout, "cache_read": 0, "cache_create": 0})
        elif prov in _EVENT_CLAUDE:
            events.append({"day": day, "provider": "claude", "source": "javis", "activity": "chat",
                           "model": model, "project": "(events)",
                           "input": tin, "output": tout, "cache_read": 0, "cache_create": 0})
        elif prov in _EVENT_CODEX:
            events.append({"day": day, "provider": "codex", "source": "javis", "activity": "chat",
                           "model": model, "project": "(events)",
                           "input": tin, "output": tout, "cache_read": 0, "cache_create": 0})
    if events:
        _insert_events(conn, path, events)
    conn.execute("INSERT INTO files_seen(path,size,mtime,offset) VALUES(?,?,?,?) "
                 "ON CONFLICT(path) DO UPDATE SET offset=excluded.offset",
                 (path, 0, 0, complete))
    return len(events)


def _dedup_events_vs_raw(conn) -> None:
    """Log tho LUON thang: xoa cac dong nguon-event (path=usage-events.jsonl) cua claude/codex o
    nhung NGAY da co log tho phu (dong provider do nhung path KHAC file event). Chay moi refresh
    nen tu lanh du event den truoc hay log tho den truoc. Neu bao cao dang 0 vi log tho khong dong
    gop dong nao -> khong co gi bi xoa -> event duoc giu, dung y do du phong."""
    ev = str(_EVENTS_PATH)
    for prov in ("claude", "codex"):
        conn.execute(
            "DELETE FROM file_daily WHERE path=? AND provider=? AND day IN "
            "(SELECT DISTINCT day FROM file_daily WHERE provider=? AND path<>?)",
            (ev, prov, prov, ev))


# Marker migration: ban cu chi nap provider API tu usage-events.jsonl (bo cli/codex) va da day
# offset qua het cac dong cli cu. Sau khi len ban moi, doc lai events tu DAU MOT LAN de backfill
# lich su cli/codex; xoa row+offset cu cua events truoc nen API khong bi dem trung.
_EVENTS_MIGRATE_MARK = "__events_migrate_v2__"


def _migrate_events_once(conn) -> None:
    row = conn.execute("SELECT offset FROM files_seen WHERE path=?", (_EVENTS_MIGRATE_MARK,)).fetchone()
    if row:
        return
    ep = str(_EVENTS_PATH)
    conn.execute("DELETE FROM file_daily WHERE path=?", (ep,))
    conn.execute("DELETE FROM files_seen WHERE path=?", (ep,))
    conn.execute("INSERT INTO files_seen(path,size,mtime,offset) VALUES(?,0,0,1) "
                 "ON CONFLICT(path) DO NOTHING", (_EVENTS_MIGRATE_MARK,))


def refresh() -> dict:
    """Quet tang dan ca 3 nguon. Tra so file/event thuc su xu ly lan nay."""
    res = {"claude_files": 0, "codex_files": 0, "api_events": 0}
    conn = _connect()
    try:
        _migrate_events_once(conn)                  # 1 lan: backfill cli/codex tu events cu
        chat = _chat_sessions()
        brains = session_brain.mapping()   # phien nao thuoc brain nao -> nhan du an dung
        res["claude_files"] = _scan_claude(conn, chat, brains)
        res["codex_files"] = _scan_codex(conn)
        res["api_events"] = _ingest_events(conn)   # API + du phong cli/codex tu usage-events.jsonl
        _dedup_events_vs_raw(conn)                  # log tho phu ngay nao thi xoa event ngay do
        conn.commit()
    finally:
        conn.close()
    return res


# ============================================================
# Truy van: giai ky + so sanh + summary (Task 6)
# ============================================================
def _today_local() -> date:
    return datetime.now(_TZ).date()


def _month_first(d: date) -> date:
    return d.replace(day=1)


def _month_last(d: date) -> date:
    nxt = (d.replace(day=28) + timedelta(days=4)).replace(day=1)
    return nxt - timedelta(days=1)


def _prev_month_first(d: date) -> date:
    return (d.replace(day=1) - timedelta(days=1)).replace(day=1)


def resolve_period(period: str, today: date = None):
    """Tra ((cur_start, cur_end), (prev_start, prev_end)) - cac object date, theo gio dia phuong.
    prev = ky tuong duong lien truoc de so sanh."""
    d = today or _today_local()
    if period == "today":
        return (d, d), (d - timedelta(days=1), d - timedelta(days=1))
    if period == "yesterday":
        y = d - timedelta(days=1)
        return (y, y), (y - timedelta(days=1), y - timedelta(days=1))
    if period == "this_week":
        mon = d - timedelta(days=d.weekday())
        return (mon, d), (mon - timedelta(days=7), d - timedelta(days=7))
    if period == "last_week":
        mon = d - timedelta(days=d.weekday())
        ls, le = mon - timedelta(days=7), mon - timedelta(days=1)
        return (ls, le), (ls - timedelta(days=7), le - timedelta(days=7))
    if period == "this_month":
        f = _month_first(d)
        off = (d - f).days
        pf = _prev_month_first(d)
        pe = min(pf + timedelta(days=off), _month_last(pf))
        return (f, d), (pf, pe)
    if period == "last_month":
        pf = _prev_month_first(d)
        pl = _month_last(pf)
        ppf = _prev_month_first(pf)
        return (pf, pl), (ppf, _month_last(ppf))
    if period == "last_3_months":
        s = d - timedelta(days=89)
        return (s, d), (s - timedelta(days=90), s - timedelta(days=1))
    if period == "this_year":
        jan = date(d.year, 1, 1)
        try:
            pd = d.replace(year=d.year - 1)
        except ValueError:
            pd = d.replace(year=d.year - 1, day=28)
        return (jan, d), (date(d.year - 1, 1, 1), pd)
    raise ValueError("period khong hop le: %s" % period)


_ROW_COLS = "day,provider,source,activity,model,project,input,output,cache_read,cache_create,path"
_DIM_IDX = {"day": 0, "provider": 1, "source": 2, "activity": 3, "model": 4, "project": 5}


def _tot(r) -> int:
    return (r[6] or 0) + (r[7] or 0) + (r[8] or 0) + (r[9] or 0)


def _fetch_rows(conn, start, end, provider=None, project=None):
    where = ["day BETWEEN ? AND ?"]
    args = [start, end]
    if provider:
        where.append("provider=?")
        args.append(provider)
    if project:
        where.append("project=?")
        args.append(project)
    return conn.execute("SELECT %s FROM file_daily WHERE %s" % (_ROW_COLS, " AND ".join(where)), args).fetchall()


def _sum_tokens(conn, start, end, provider=None, project=None) -> int:
    where = ["day BETWEEN ? AND ?"]
    args = [start, end]
    if provider:
        where.append("provider=?")
        args.append(provider)
    if project:
        where.append("project=?")
        args.append(project)
    q = "SELECT COALESCE(SUM(input+output+cache_read+cache_create),0) FROM file_daily WHERE " + " AND ".join(where)
    return conn.execute(q, args).fetchone()[0] or 0


def _group(rows, dim, prices):
    """Gop rows theo mot chieu -> list {key,tokens,input,output,cache_read,cache_create,sessions,cost} desc."""
    idx = _DIM_IDX[dim]
    agg = {}
    for r in rows:
        key = r[idx] or "(?)"
        e = agg.setdefault(key, {"key": key, "tokens": 0, "input": 0, "output": 0,
                                 "cache_read": 0, "cache_create": 0, "cost": 0.0, "_paths": set()})
        e["tokens"] += _tot(r)
        e["input"] += r[6] or 0
        e["output"] += r[7] or 0
        e["cache_read"] += r[8] or 0
        e["cache_create"] += r[9] or 0
        e["cost"] += up.estimate_cost({"model": r[4], "input": r[6] or 0, "output": r[7] or 0,
                                        "cache_read": r[8] or 0, "cache_create": r[9] or 0}, prices)
        e["_paths"].add(r[10])
    out = []
    for e in agg.values():
        e["sessions"] = len(e.pop("_paths"))
        e["cost"] = round(e["cost"], 4)
        out.append(e)
    out.sort(key=lambda x: -x["tokens"])
    return out


def summary(period: str = "this_month", provider: str = None, project: str = None, today: date = None) -> dict:
    """Bao cao token cho mot ky: KPI + breakdowns + timeseries, kem so sanh ky truoc."""
    (cs, ce), (ps, pe) = resolve_period(period, today)
    cs_s, ce_s, ps_s, pe_s = cs.isoformat(), ce.isoformat(), ps.isoformat(), pe.isoformat()
    prices = up.load_prices()
    conn = _connect()
    try:
        rows = _fetch_rows(conn, cs_s, ce_s, provider, project)
        tokens_prev = _sum_tokens(conn, ps_s, pe_s, provider, project)
    finally:
        conn.close()

    tokens = sum(_tot(r) for r in rows)
    inp = sum(r[6] or 0 for r in rows)
    out = sum(r[7] or 0 for r in rows)
    cread = sum(r[8] or 0 for r in rows)
    ccreate = sum(r[9] or 0 for r in rows)
    billable_in = inp + cread + ccreate
    sessions = len({r[10] for r in rows})
    cost = round(sum(up.estimate_cost({"model": r[4], "input": r[6] or 0, "output": r[7] or 0,
                                       "cache_read": r[8] or 0, "cache_create": r[9] or 0}, prices) for r in rows), 4)
    n_days = (ce - cs).days + 1
    delta = None
    if tokens_prev > 0:
        delta = round((tokens - tokens_prev) * 100.0 / tokens_prev, 1)

    # timeseries: lap day tu cs -> ce, tach theo provider
    series = {}
    dd = cs
    while dd <= ce:
        series[dd.isoformat()] = {"day": dd.isoformat(), "claude": 0, "codex": 0, "api": 0, "total": 0}
        dd += timedelta(days=1)
    for r in rows:
        cell = series.get(r[0])
        if cell is None:
            continue
        prov = r[1] if r[1] in ("claude", "codex", "api") else "api"
        cell[prov] += _tot(r)
        cell["total"] += _tot(r)

    return {
        "period": period, "range": [cs_s, ce_s], "range_prev": [ps_s, pe_s],
        "filter": {"provider": provider, "project": project},
        "kpi": {
            "tokens": tokens, "tokens_prev": tokens_prev, "delta_pct": delta,
            "per_day_avg": round(tokens / n_days, 1) if n_days else 0,
            "sessions": sessions,
            "avg_per_session": round(tokens / sessions) if sessions else 0,
            "cache_hit": round(cread / billable_in, 4) if billable_in else 0,
            "out_in_ratio": round(out / inp, 3) if inp else None,
            "cost_est": cost,
            "input": inp, "output": out, "cache_read": cread, "cache_create": ccreate,
        },
        "by_provider": _group(rows, "provider", prices),
        "by_source": _group(rows, "source", prices),
        "by_activity": _group(rows, "activity", prices),
        "by_model": _group(rows, "model", prices),
        "by_project": _group(rows, "project", prices),
        "timeseries": [series[k] for k in sorted(series)],
    }


def _fmt_tok(n: int) -> str:
    n = int(n or 0)
    if n >= 1_000_000:
        return "%.1fM" % (n / 1_000_000)
    if n >= 1_000:
        return "%.0fk" % (n / 1_000)
    return str(n)


def insights(period: str = "this_month", today: date = None) -> list:
    """Sinh danh sach de xuat hanh dong tu du lieu ky. Moi item {code, level, title, detail}.
    warn (can lam) xep truoc info (goi y)."""
    s = summary(period, today=today)
    k = s["kpi"]
    total = k["tokens"]
    billable = k["input"] + k["cache_read"] + k["cache_create"]
    out = []

    if billable >= MIN_BILLABLE_FOR_CACHE and k["cache_hit"] < CACHE_LOW:
        out.append({"code": "cache_low", "level": "warn",
                    "title": "Cache hit thấp (%.0f%%)" % (k["cache_hit"] * 100),
                    "detail": "Đang nạp lại ngữ cảnh nhiều, tốn token. Cân nhắc /compact hoặc chia phiên để tận dụng cache."})

    bg = next((x["tokens"] for x in s["by_activity"] if x["key"] == "background"), 0)
    if total > 0 and bg / total >= BACKGROUND_SHARE:
        out.append({"code": "background_heavy", "level": "warn",
                    "title": "Hoạt động ngầm chiếm %.0f%% token" % (bg / total * 100),
                    "detail": "Loop/lịch chạy nền đang ngốn nhiều (%s). Xem lại tần suất các loop hoặc tắt bớt." % _fmt_tok(bg)})

    opus = sum(x["tokens"] for x in s["by_model"] if str(x["key"]).startswith("claude-opus"))
    if total > 0 and opus / total >= EXPENSIVE_SHARE:
        out.append({"code": "expensive_model", "level": "info",
                    "title": "Opus chiếm %.0f%% token" % (opus / total * 100),
                    "detail": "Opus đắt gấp nhiều lần sonnet/haiku. Việc nhẹ cân nhắc hạ model ở trang Model."})

    cs, ce = s["range"]
    conn = _connect()
    try:
        row = conn.execute("SELECT path, SUM(input+cache_read+cache_create) t FROM file_daily "
                           "WHERE day BETWEEN ? AND ? GROUP BY path ORDER BY t DESC LIMIT 1", (cs, ce)).fetchone()
    finally:
        conn.close()
    if row and (row[1] or 0) >= SESSION_BLOAT:
        out.append({"code": "session_bloat", "level": "warn",
                    "title": "Có phiên phình to (%s token vào)" % _fmt_tok(row[1]),
                    "detail": "Một phiên nạp %s token đầu vào. Cân nhắc tách phiên để giảm chi phí ngữ cảnh." % _fmt_tok(row[1])})

    prev = k["tokens_prev"]
    if prev > 0 and total > 0:
        cs_d, ce_d = date.fromisoformat(s["range"][0]), date.fromisoformat(s["range"][1])
        ps_d, pe_d = date.fromisoformat(s["range_prev"][0]), date.fromisoformat(s["range_prev"][1])
        cur_pd = total / max(1, (ce_d - cs_d).days + 1)
        prev_pd = prev / max(1, (pe_d - ps_d).days + 1)
        if prev_pd > 0 and cur_pd / prev_pd >= SPIKE_RATIO:
            out.append({"code": "spike", "level": "warn",
                        "title": "Token/ngày tăng %.0f%% so kỳ trước" % ((cur_pd / prev_pd - 1) * 100),
                        "detail": "Mức tiêu thụ tăng đột biến. Kiểm tra nguồn tăng chính ở phần breakdown."})

    out.sort(key=lambda x: 0 if x["level"] == "warn" else 1)
    return out


def totals_by(dim: str, provider: str = None) -> dict:
    """Tong token theo mot chieu (khong loc ky), dung cho kiem thu + breakdown tho.
    Tra {gia_tri: {input,output,cache_read,cache_create,sessions}}."""
    if dim not in _DIMS:
        raise ValueError("dim khong hop le: %s" % dim)
    conn = _connect()
    try:
        where, args = "", []
        if provider:
            where, args = "WHERE provider=?", [provider]
        rows = conn.execute(
            "SELECT %s, SUM(input), SUM(output), SUM(cache_read), SUM(cache_create), COUNT(DISTINCT path) "
            "FROM file_daily %s GROUP BY %s" % (dim, where, dim), args).fetchall()
    finally:
        conn.close()
    return {r[0]: {"input": r[1] or 0, "output": r[2] or 0, "cache_read": r[3] or 0,
                   "cache_create": r[4] or 0, "sessions": r[5] or 0} for r in rows}
