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

import localefmt
import glob
import json
import os
import sqlite3
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from config import STATE_DIR
import session_brain   # {session_id: brain} - nhan du an dung cho phien Javis (cwd luon la goc project)
import usage_parsers as up

# Múi giờ để cắt NGÀY của thống kê. Đọc từ cấu hình qua `localefmt`, KHÔNG còn là hằng số.
#
# Đổi múi giờ là DỊCH RANH GIỚI NGÀY, nên phải nói rõ hợp đồng: dữ liệu đã ghi giữ nguyên
# chuỗi ngày của nó, chỉ dữ liệu MỚI mới theo múi giờ mới. Không viết lại lịch sử - một bản
# ghi "2026-08-14" được tạo ra dưới UTC+7 vẫn là ngày đó, kể cả sau khi người dùng chuyển
# sang UTC+9. Đổi lại, ngay lúc chuyển sẽ có một chỗ gợn trong chuỗi ngày; đó là hệ quả không
# tránh được của việc đổi múi giờ, và viết lại lịch sử để làm nó phẳng còn tệ hơn nhiều.
#
# Là HÀM chứ không phải hằng: người dùng đổi múi giờ ở trang Cài đặt là ăn ngay, không phải
# khởi động lại server.
def _tz():
    return localefmt.tz()
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
# Provider API = nhung duong TRA TIEN THEO TOKEN. Danh sach nay phai khop PROVIDER_DEFS ben
# main.py; thieu mot ten la moi dong cua provider do bi VUT IM LANG (chuoi if/elif ben duoi
# khong co else), va o "tien mat thang nay" bao 0 trong khi vi van voi di. 'groq' va 'gemini'
# tung thieu dung nhu vay.
_API_PROVIDERS = {"openrouter", "openai", "anthropic", "anthropic-api", "oauth", "ollama",
                  "groq", "gemini"}


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
                 "input INTEGER, output INTEGER, cache_read INTEGER, cache_create INTEGER,"
                 "turns INTEGER DEFAULT 0)")
    # Grain GIO, tach bang rieng. Vi sao khong nhet 'hour' vao file_daily: _insert_events gom
    # theo (day,provider,source,activity,model,project) nen them mot chieu nua la nhan so dong
    # len ~24 lan cho MOI to hop - trong khi cua so truot chi can (gio, provider). Bang rieng
    # giu file_daily nguyen kich thuoc va cau truy van cua so khong phai loc qua 6 chieu.
    conn.execute("CREATE TABLE IF NOT EXISTS file_hourly("
                 "path TEXT, hour TEXT, provider TEXT, tokens INTEGER, turns INTEGER)")
    # ALTER cho DB da ton tai: CREATE TABLE IF NOT EXISTS im lang bo qua bang cu, nen khong co
    # khoi nay thi moi INSERT co liet ke 'turns' se nem "no such column" tren may da cai lau.
    # Xem sessions.py:262-289 cho cung mot idiom (va luu y: CREATE INDEX phai chay SAU ALTER).
    try:
        co = {r[1] for r in conn.execute("PRAGMA table_info(file_daily)")}
        if "turns" not in co:
            conn.execute("ALTER TABLE file_daily ADD COLUMN turns INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass
    conn.execute("CREATE INDEX IF NOT EXISTS idx_fd_day ON file_daily(day)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_fd_path ON file_daily(path)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_fh_hour ON file_hourly(hour)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_fh_path ON file_hourly(path)")
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
    conn.execute("DELETE FROM file_hourly WHERE path=?", (path,))


def _gio(ev) -> str:
    """Moc gio dia phuong 'YYYY-MM-DDTHH' cua mot su kien. Khong co ts -> '' (bo qua)."""
    ts = int(ev.get("ts") or 0)
    if ts <= 0:
        return ""
    return datetime.fromtimestamp(ts, _tz()).strftime("%Y-%m-%dT%H")


def _insert_events(conn, path, events) -> None:
    """Gop events cua 1 file theo khoa (day,provider,source,activity,model,project) roi insert.

    Gop THEM mot lan nua theo (gio, provider) vao file_hourly. Hai bang, hai grain, cung mot
    lan doc file - cua so truot 5 gio khong the dung file_daily vi grain nho nhat cua no la
    NGAY, ma "toi con bao nhieu trong cua so nay" thi ngay la vo nghia.
    """
    groups = {}
    theo_gio = {}
    for ev in events:
        k = (ev.get("day") or "", ev["provider"], ev["source"], ev["activity"], ev["model"], ev["project"])
        g = groups.setdefault(k, [0, 0, 0, 0, 0])
        g[0] += ev["input"]
        g[1] += ev["output"]
        g[2] += ev["cache_read"]
        g[3] += ev["cache_create"]
        g[4] += int(ev.get("turns") or 0)
        gio = _gio(ev)
        if gio:
            h = theo_gio.setdefault((gio, ev["provider"]), [0, 0])
            h[0] += ev["input"] + ev["output"] + ev["cache_read"] + ev["cache_create"]
            h[1] += int(ev.get("turns") or 0)
    if groups:
        conn.executemany(
            "INSERT INTO file_daily(path,day,provider,source,activity,model,project,input,output,cache_read,cache_create,turns)"
            " VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            [(path,) + k + tuple(g) for k, g in groups.items()])
    if theo_gio:
        conn.executemany(
            "INSERT INTO file_hourly(path,hour,provider,tokens,turns) VALUES(?,?,?,?,?)",
            [(path,) + k + tuple(v) for k, v in theo_gio.items()])


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
# Grok Build CLI (goi SuperGrok / X Premium+). Cot rieng chu KHONG gom vao 'api': mot API key
# xAI la duong TRA TIEN theo luot goi, con day la duong THUE BAO - hai thu khac hoan toan ve
# hoa don du cung ten model.
_EVENT_GROK_CLI = {"grok-cli", "grok_cli", "grok"}


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
        # Phai don CA HAI bang. Don moi file_daily roi doc lai tu dong 0 thi file_hourly giu
        # nguyen dong cu VA nhan them dong moi -> cua so 5 gio va dinh phong len vinh vien,
        # khong co gi xoa chung nua.
        _clear_file(conn, path)
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
        # Moi dong = mot lan usage_store.record() = mot lan goi model, va no mang theo ts thuc.
        # Do la thu log tho khong cho voi nhanh API, nen cung la nguon duy nhat dung duoc cho
        # "so luot" va "cua so truot" cua nhung nhanh do.
        chung = {"day": day, "ts": int(e.get("ts") or 0), "model": model,
                 "input": tin, "output": tout, "cache_read": 0, "cache_create": 0, "turns": 1}
        if prov in _API_PROVIDERS:
            events.append({**chung, "provider": "api", "source": "javis", "activity": "chat",
                           "project": "(api)"})
        elif prov in _EVENT_CLAUDE:
            events.append({**chung, "provider": "claude", "source": "javis", "activity": "chat",
                           "project": "(events)"})
        elif prov in _EVENT_CODEX:
            events.append({**chung, "provider": "codex", "source": "javis", "activity": "chat",
                           "project": "(events)"})
        elif prov in _EVENT_GROK_CLI:
            events.append({**chung, "provider": "grok-cli", "source": "javis",
                           "activity": "chat", "project": "(events)"})
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
    gop dong nao -> khong co gi bi xoa -> event duoc giu, dung y do du phong.

    PHAI don CA HAI bang. file_hourly la nguon cua cua so truot, va mot luot Claude Code duoc ghi
    HAI LAN: mot lan trong log tho (~/.claude/projects), mot lan trong usage-events.jsonl do
    usage_store.record() ghi. Chi don file_daily thi bang ngay dung con cua so 5 gio bao GAP DOI -
    va do la con so dung de doan xem sap cham tran gia chua, tuc la sai ve dung huong nguy hiem
    nhat. Do duoc bang kich ban: 1 luot 1000 token -> file_daily 1000, file_hourly 2000.

    Doi chieu theo NGAY (substr(hour,1,10)) chu khong theo gio: log tho va event ghi cung mot luot
    o hai moc thoi gian hoi lech nhau (mot cai la timestamp cua dong assistant, mot cai la luc
    record() chay), nen doi chieu theo gio se truot o cac luot vat qua ranh gioi gio.
    """
    ev = str(_EVENTS_PATH)
    for prov in ("claude", "codex"):
        conn.execute(
            "DELETE FROM file_daily WHERE path=? AND provider=? AND day IN "
            "(SELECT DISTINCT day FROM file_daily WHERE provider=? AND path<>?)",
            (ev, prov, prov, ev))
        conn.execute(
            "DELETE FROM file_hourly WHERE path=? AND provider=? AND substr(hour,1,10) IN "
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


# Ban truoc khong co cot `turns` va khong co bang theo gio. Cot moi mac dinh 0, va _unchanged()
# bo qua moi file da quet - nghia la neu chi them cot roi thoi thi so luot se dung 0 mai mai
# cho toan bo lich su, va trang bao "0 luot" trong khi 560 trieu token nam so so ra do. Nen
# doi schema thi phai QUET LAI: xoa sach dau vet da-quet mot lan duy nhat, refresh ke tiep tu
# dung lai het. Ton mot lan (vai giay toi vai chuc giay tuy so file), sau do lai tang dan.
_SCHEMA_MARK = "__schema_v3_turns__"


def _migrate_schema_once(conn) -> bool:
    """Doi grain -> quet lai toan bo mot lan. Tra True neu vua don dep (de log biet)."""
    row = conn.execute("SELECT offset FROM files_seen WHERE path=?", (_SCHEMA_MARK,)).fetchone()
    if row:
        return False
    # KHONG xoa file_daily. Claude Code tu don transcript trong ~/.claude/projects sau
    # `cleanupPeriodDays` (mac dinh 30 ngay), nen dong nao co file goc da bi don thi xoa di la
    # MAT VINH VIEN - quet lai khong dung lai duoc. Chi xoa dau vet DA-QUET (files_seen) de
    # moi file CON TREN DIA duoc parse lai; luc parse lai, _clear_file tu xoa dong cu cua
    # chinh file do nen khong dem trung. Dong mo coi (file goc khong con) o lai voi turns=0:
    # thieu so luot cua ky cu con hon mat sach token cua ky cu.
    ev = str(_EVENTS_PATH)
    conn.execute("DELETE FROM file_daily WHERE path=?", (ev,))
    conn.execute("DELETE FROM file_hourly WHERE path=?", (ev,))
    conn.execute("DELETE FROM files_seen")
    conn.execute("INSERT INTO files_seen(path,size,mtime,offset) VALUES(?,0,0,1)", (_SCHEMA_MARK,))
    # Xoa sach files_seen cung xoa luon dau migrate v2 o tren; ghi lai ngay de lan refresh sau
    # no khong nap lai usage-events.jsonl tu dau lan nua (se dem trung voi lan quet nay).
    # Rieng file event thi offset da ve 0 va dong cu cua no vua bi xoa o tren, nen no duoc nap
    # lai tron ven mot lan - dung y do, vi day la nguon DUY NHAT cua nhanh API.
    conn.execute("INSERT INTO files_seen(path,size,mtime,offset) VALUES(?,0,0,1) "
                 "ON CONFLICT(path) DO NOTHING", (_EVENTS_MIGRATE_MARK,))
    return True


def refresh() -> dict:
    """Quet tang dan ca 3 nguon. Tra so file/event thuc su xu ly lan nay."""
    res = {"claude_files": 0, "codex_files": 0, "api_events": 0, "quet_lai": False}
    conn = _connect()
    try:
        res["quet_lai"] = _migrate_schema_once(conn)   # 1 lan khi doi schema: quet lai tat ca
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
    return datetime.now(_tz()).date()


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


# Cot moi NOI VAO CUOI, sau 'path'. _tot() va _group() doc bang chi so vi tri (r[6]..r[10]),
# nen chen vao giua la lam lech im lang moi con so cua trang.
_ROW_COLS = "day,provider,source,activity,model,project,input,output,cache_read,cache_create,path,turns"
_DIM_IDX = {"day": 0, "provider": 1, "source": 2, "activity": 3, "model": 4, "project": 5}
_I_TURNS = 11


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
                                 "cache_read": 0, "cache_create": 0, "cost": 0.0,
                                 "turns": 0, "_paths": set()})
        e["tokens"] += _tot(r)
        e["input"] += r[6] or 0
        e["output"] += r[7] or 0
        e["cache_read"] += r[8] or 0
        e["cache_create"] += r[9] or 0
        e["turns"] += r[_I_TURNS] or 0
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
    turns = sum(r[_I_TURNS] or 0 for r in rows)
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
        series[dd.isoformat()] = {"day": dd.isoformat(), "claude": 0, "codex": 0, "api": 0,
                                  "total": 0, "turns": 0}
        dd += timedelta(days=1)
    for r in rows:
        cell = series.get(r[0])
        if cell is None:
            continue
        prov = r[1] if r[1] in ("claude", "codex", "api") else "api"
        cell[prov] += _tot(r)
        cell["total"] += _tot(r)
        cell["turns"] += r[_I_TURNS] or 0

    return {
        "period": period, "range": [cs_s, ce_s], "range_prev": [ps_s, pe_s],
        "filter": {"provider": provider, "project": project},
        "kpi": {
            "tokens": tokens, "tokens_prev": tokens_prev, "delta_pct": delta,
            "per_day_avg": round(tokens / n_days, 1) if n_days else 0,
            "sessions": sessions,
            # So LUOT goi model trong ky, va token trung binh moi luot. Day la mau so cua moi
            # phep tinh tiet kiem: phan ngu canh tiet kiem duoc la thu tra theo TUNG LUOT.
            "turns": turns,
            "avg_per_turn": round(tokens / turns) if turns else 0,
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


def nhip_engine(period: str = "this_month", today: date = None) -> list:
    """Token MOI LUOT cua tung provider, tach theo loai hoat dong. Sap xep dat -> re.

    Cau hoi no tra loi: "cung mot loai viec, bo nao nao dat hon?". Tong token khong tra loi
    duoc vi bo nao chay nhieu viec hon thi dĩ nhien ton nhieu hon; phai chia cho SO LUOT moi
    so sanh duoc. Va phai tach theo hoat dong vi mot luot chat va mot luot chay nen la hai
    thu khac han ve co ngu canh.
    """
    (cs, ce), _prev = resolve_period(period, today)
    prices = up.load_prices()
    conn = _connect()
    try:
        rows = _fetch_rows(conn, cs.isoformat(), ce.isoformat())
    finally:
        conn.close()
    agg = {}
    for r in rows:
        k = (r[1] or "?", r[3] or "?")          # (provider, activity)
        e = agg.setdefault(k, {"provider": k[0], "activity": k[1], "tokens": 0,
                               "turns": 0, "cost": 0.0})
        e["tokens"] += _tot(r)
        e["turns"] += r[_I_TURNS] or 0
        e["cost"] += up.estimate_cost({"model": r[4], "input": r[6] or 0, "output": r[7] or 0,
                                       "cache_read": r[8] or 0, "cache_create": r[9] or 0}, prices)
    out = []
    for e in agg.values():
        if e["turns"] <= 0:
            continue                            # khong co mau so thi khong so sanh duoc
        e["moi_luot"] = round(e["tokens"] / e["turns"])
        e["cost_moi_luot"] = round(e["cost"] / e["turns"], 6)
        e["cost"] = round(e["cost"], 4)
        out.append(e)
    out.sort(key=lambda x: -x["moi_luot"])
    return out


def cua_so(gio: float = 5.0, provider: str = None, now: datetime = None) -> dict:
    """Muc dung trong CUA SO TRUOT `gio` gio gan nhat: {tokens, turns, gio, tu, den}.

    Vi sao khong dung file_daily: hoi "toi con bao nhieu trong cua so nay" ma tra loi theo
    NGAY thi 8 gio sang mung 1 se bao gan bang 0 du 5 gio truoc do vua dot het han muc. Gia
    goi Claude/ChatGPT deu tinh theo cua so truot vai gio, nen day moi la don vi dung.

    Grain la GIO nen bien cua so lam tron len dau gio - tuc con so nay hoi ROI RONG hon thuc
    te (om them phan dau gio cu). Tha bao dang dung nhieu hon thuc te con hon nguoc lai.
    """
    gio = max(1.0, min(float(gio or 5.0), 24 * 7.0))
    now = now or datetime.now(_tz())
    # Dem dung `n` MOC GIO, khop y het `dinh_cua_so`. Truoc day ham nay lay now-5h roi BETWEEN
    # tron ca hai dau -> 6 moc, trong khi dinh truot dung 5 moc. Chia hai so do cho nhau (main
    # lam dung vay de ra ty_le) thi ty le luon phong ~20%, va tren mot nhip dung deu no bao
    # "120% muc cao nhat" - mot con so khong the dung.
    n = max(1, int(round(gio)))
    tu = now - timedelta(hours=n - 1)
    h_tu, h_den = tu.strftime("%Y-%m-%dT%H"), now.strftime("%Y-%m-%dT%H")
    where, args = ["hour BETWEEN ? AND ?"], [h_tu, h_den]
    if provider:
        where.append("provider=?")
        args.append(provider)
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT COALESCE(SUM(tokens),0), COALESCE(SUM(turns),0) FROM file_hourly WHERE "
            + " AND ".join(where), args).fetchone()
    finally:
        conn.close()
    return {"tokens": row[0] or 0, "turns": row[1] or 0, "gio": gio,
            "tu": h_tu, "den": h_den, "moc_reset": (tu + timedelta(hours=n)).isoformat()}


def luot_theo_ngay(period: str = "this_month", nguon: tuple = ("javis",),
                   bo_subagent: bool = True, today: date = None) -> list:
    """[{day, turns}] cua rieng nhung luot DO JAVIS chay. Dung lam mau so tinh tiet kiem.

    Vi sao khong dung thang `summary()["timeseries"]["turns"]`: no cong turns cua MOI dong,
    trong do co source='manual' - la nhung phien nguoi dung tu mo `claude` trong terminal o
    bat ky repo nao tren cung may. Nhung luot do KHONG di qua prompt cua Javis, nen che do
    tiet kiem cua Javis khong he lam chung re di. Nhan chung vao la thoi phong con so tiet
    kiem len nhieu lan, va tren mot may vua dung Javis vua dung Claude Code tay thi phan thoi
    phong con lon hon phan that.

    Bo luon 'subagent': agent con do engine tu de ra mang prompt rieng cua no, khong phai goi
    ngu canh ma muc tiet kiem cua Javis cat. Tha dem thieu con hon khoe thua.
    """
    (cs, ce), _prev = resolve_period(period, today)
    where = ["day BETWEEN ? AND ?"]
    args = [cs.isoformat(), ce.isoformat()]
    if nguon:
        where.append("source IN (%s)" % ",".join("?" for _ in nguon))
        args.extend(list(nguon))
    if bo_subagent:
        where.append("activity<>'subagent'")
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT day, COALESCE(SUM(turns),0) FROM file_daily WHERE %s GROUP BY day ORDER BY day"
            % " AND ".join(where), args).fetchall()
    finally:
        conn.close()
    return [{"day": r[0], "turns": r[1] or 0} for r in rows]


def dinh_cua_so(gio: float = 5.0, ngay_gan_day: int = 60, now: datetime = None) -> dict:
    """Cua so `gio` gio NANG NHAT tung do duoc trong `ngay_gan_day` ngay. Tra {tokens, hour}.

    Day la cach duy nhat noi duoc "ban dang o dau so voi chinh minh" khi nha cung cap KHONG
    cong bo han muc bang so. Muc cao nhat tung cham ma chua bi chan la mot can duoi that -
    kem chinh xac hon mot con so chinh thuc, nhung that va rieng cua tung nguoi.
    """
    gio = max(1.0, min(float(gio or 5.0), 24 * 7.0))
    now = now or datetime.now(_tz())
    tu = (now - timedelta(days=max(1, int(ngay_gan_day)))).strftime("%Y-%m-%dT%H")
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT hour, SUM(tokens) FROM file_hourly WHERE hour>=? GROUP BY hour ORDER BY hour",
            (tu,)).fetchall()
    finally:
        conn.close()
    if not rows:
        return {"tokens": 0, "hour": "", "gio": gio}
    # Cua so truot tren chuoi gio LIEN TUC: chuoi tu DB co lo hong (gio khong dung thi khong
    # co dong), nen phai lap day truoc, khong thi "5 gio" thanh 5 gio-co-hoat-dong rai rac
    # ca tuan va con dinh do bi thoi len vo ly.
    theo_gio = {r[0]: (r[1] or 0) for r in rows}
    moc = datetime.strptime(rows[0][0], "%Y-%m-%dT%H").replace(tzinfo=_tz())
    het = datetime.strptime(rows[-1][0], "%Y-%m-%dT%H").replace(tzinfo=_tz())
    day, nhan = [], []
    while moc <= het:
        k = moc.strftime("%Y-%m-%dT%H")
        day.append(theo_gio.get(k, 0))
        nhan.append(k)
        moc += timedelta(hours=1)
    n = max(1, int(round(gio)))
    tong, dinh, dinh_moc = 0, 0, ""
    for i, v in enumerate(day):
        tong += v
        if i >= n:
            tong -= day[i - n]
        if tong > dinh:
            dinh, dinh_moc = tong, nhan[i]
    return {"tokens": dinh, "hour": dinh_moc, "gio": gio}


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
