"""Test usage_index (indexer SQLite + query). Chay tay:

    python tests/run.py usage_index

Tu co lap: JAVIS_STATE_DIR + thu muc nguon (Claude/Codex) tro vao temp. Khong mang.
Exit code != 0 neu fail.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401  - nạp server/ vào sys.path (xem tests/python/_paths.py)
import json
import os
import sys
import tempfile
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="javis-uidx-"))
os.environ["JAVIS_STATE_DIR"] = str(_TMP / "state")
os.environ["JAVIS_CLAUDE_PROJECTS_DIR"] = str(_TMP / "claude")
os.environ["JAVIS_CODEX_SESSIONS_DIR"] = str(_TMP / "codex")
(_TMP / "state").mkdir(parents=True, exist_ok=True)

import usage_index as ui  # noqa: E402

_fails = []


def check(name, cond):
    print(("OK   " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)


def _write_lines(path: Path, lines):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(x) for x in lines), encoding="utf-8")


# --- nguon Claude: 1 file, 2 dong (background + subagent, cung session S1) ---
_claude_file = _TMP / "claude" / "D--Project-Demo" / "sess.jsonl"
_line_bg = {"type": "assistant", "entrypoint": "sdk-cli", "isSidechain": False, "sessionId": "S1",
            "cwd": "D:/Project/Demo", "timestamp": "2026-07-05T03:00:00.000Z",
            "message": {"model": "claude-opus-4-8", "usage": {"input_tokens": 100, "output_tokens": 200}}}
_line_sub = {"type": "assistant", "entrypoint": "sdk-cli", "isSidechain": True, "sessionId": "S1",
             "cwd": "D:/Project/Demo", "timestamp": "2026-07-05T03:05:00.000Z",
             "message": {"model": "claude-opus-4-8", "usage": {"input_tokens": 50, "output_tokens": 80}}}
_write_lines(_claude_file, [_line_bg, _line_sub])

# --- nguon Codex: 1 rollout ---
_codex_file = _TMP / "codex" / "2026" / "07" / "05" / "rollout-2026-07-05T03-00-00-x.jsonl"
_write_lines(_codex_file, [
    {"timestamp": "2026-07-05T03:00:00.000Z", "type": "session_meta", "payload": {"cwd": "D:/Project/Demo"}},
    {"timestamp": "2026-07-05T03:00:05.000Z", "type": "turn_context", "payload": {"model": "gpt-5.5"}},
    {"timestamp": "2026-07-05T03:10:00.000Z", "type": "event_msg", "payload": {"type": "token_count",
     "info": {"total_token_usage": {"input_tokens": 3000, "cached_input_tokens": 800, "output_tokens": 150, "total_tokens": 3150}}}},
])

# --- refresh lan 1 ---
r1 = ui.refresh()
check("refresh: co xu ly file claude", r1["claude_files"] >= 1)
check("refresh: co xu ly file codex", r1["codex_files"] >= 1)

by_act = ui.totals_by("activity")
check("activity: background = dong khong sidechain", by_act.get("background", {}).get("input") == 100 and by_act["background"]["output"] == 200)
check("activity: subagent = dong sidechain", by_act.get("subagent", {}).get("input") == 50 and by_act["subagent"]["output"] == 80)
check("activity: chat = codex", by_act.get("chat", {}).get("input") == 2200 and by_act["chat"]["cache_read"] == 800)

by_prov = ui.totals_by("provider")
check("provider: claude gop 2 dong", by_prov["claude"]["input"] == 150 and by_prov["claude"]["output"] == 280)
check("provider: claude 1 phien (1 file)", by_prov["claude"]["sessions"] == 1)
check("provider: codex", by_prov["codex"]["input"] == 2200 and by_prov["codex"]["output"] == 150)

# --- refresh lan 2: idempotent (khong file nao xu ly lai, tong khong doi) ---
r2 = ui.refresh()
check("refresh2: khong xu ly lai claude (idempotent)", r2["claude_files"] == 0)
check("refresh2: khong xu ly lai codex (idempotent)", r2["codex_files"] == 0)
check("refresh2: tong claude khong doi", ui.totals_by("provider")["claude"]["input"] == 150)

# --- file doi (append 1 dong) -> chi cong phan moi ---
_write_lines(_claude_file, [_line_bg, _line_sub,
             {"type": "assistant", "entrypoint": "sdk-cli", "isSidechain": False, "sessionId": "S1",
              "cwd": "D:/Project/Demo", "timestamp": "2026-07-05T04:00:00.000Z",
              "message": {"model": "claude-opus-4-8", "usage": {"input_tokens": 10, "output_tokens": 20}}}])
r3 = ui.refresh()
check("refresh3: file doi duoc xu ly lai", r3["claude_files"] == 1)
check("refresh3: claude tang dung phan moi (150+10)", ui.totals_by("provider")["claude"]["input"] == 160)
check("refresh3: van 1 phien (cung file)", ui.totals_by("provider")["claude"]["sessions"] == 1)


# ============================================================
# Task 5: usage_store forward-log + nap nhanh API (khong dem trung)
# ============================================================
import usage_store  # noqa: E402  (dung chung JAVIS_STATE_DIR temp)

_evp = Path(os.environ["JAVIS_STATE_DIR"]) / "usage-events.jsonl"
usage_store.record("openrouter", "deepseek/x", 100, 50, 0)
check("events: record ghi 1 dong usage-events.jsonl", _evp.exists() and len(_evp.read_text(encoding="utf-8").strip().splitlines()) >= 1)

r_api = ui.refresh()
_api = ui.totals_by("provider").get("api", {})
check("api: xuat hien sau refresh (100/50)", _api.get("input") == 100 and _api.get("output") == 50)
check("api: refresh dem api_events", r_api["api_events"] >= 1)

usage_store.record("openrouter", "deepseek/x", 10, 5, 0)
ui.refresh()
_api2 = ui.totals_by("provider")["api"]
check("api: chi cong phan moi (110/55)", _api2["input"] == 110 and _api2["output"] == 55)

ui.refresh()
check("api: idempotent (offset khong nap lai)", ui.totals_by("provider")["api"]["input"] == 110)

# dong codex trong events KHONG lot vao nhom "api" (no la engine ChatGPT, gom rieng provider codex)
usage_store.record("codex", "gpt-5.5", 999, 999, 0)
ui.refresh()
check("api: dong codex trong events KHONG lan vao api", ui.totals_by("provider")["api"]["input"] == 110)


# ============================================================
# Task 5b: cli/codex events lam NGUON DU PHONG khi THIEU log tho (fix VPS bao cao 0 token)
# ============================================================
from datetime import datetime as _dt, timezone as _tz, timedelta as _td  # noqa: E402
_today_vn = _dt.now(_tz(_td(hours=7))).strftime("%Y-%m-%d")
# luot Claude qua SDK ghi provider "cli" vao usage-events; ngay HOM NAY khong co log tho claude
_claude_before = ui.totals_by("provider")["claude"]["input"]        # 150 (log tho 2026-07-05)
usage_store.record("cli", "sonnet", 700, 30, 0)
ui.refresh()
check("events: luot cli (Claude SDK) dem vao claude khi ngay do THIEU log tho",
      ui.totals_by("provider")["claude"]["input"] == _claude_before + 700)

# dedup: them log tho claude CUNG NGAY -> luot cli ngay do bi go, log tho thang, KHONG dem trung
_c = ui._connect()
_c.execute("INSERT INTO file_daily(path,day,provider,source,activity,model,project,input,output,cache_read,cache_create)"
           " VALUES(?,?,?,?,?,?,?,?,?,?,?)",
           ("/raw/today.jsonl", _today_vn, "claude", "javis", "chat", "sonnet", "Demo", 1000, 40, 0, 0))
_c.commit(); _c.close()
ui.refresh()   # refresh chay _dedup_events_vs_raw
check("events: dedup - log tho phu ngay nao thi go event ngay do (khong dem trung)",
      ui.totals_by("provider")["claude"]["input"] == _claude_before + 1000)


# ============================================================
# Task 6: summary() - ky + so sanh + breakdowns
# ============================================================
import sqlite3 as _sq  # noqa: E402
from datetime import date as _date  # noqa: E402


def _seed(path, day, provider, model, inp, out, cread=0, ccreate=0, source="javis", activity="chat", project="Demo"):
    c = _sq.connect(str(ui.DB_PATH))
    c.execute("INSERT INTO file_daily(path,day,provider,source,activity,model,project,input,output,cache_read,cache_create)"
              " VALUES(?,?,?,?,?,?,?,?,?,?,?)", (path, day, provider, source, activity, model, project, inp, out, cread, ccreate))
    c.commit()
    c.close()


# Seed thang 3/thang 2 (tach biet fixture thang 7) voi today co dinh = 2026-03-15.
_seed("p_mar_cl", "2026-03-15", "claude", "claude-opus-4-8", 1000, 500)
_seed("p_mar_api", "2026-03-15", "api", "?", 200, 100)
_seed("p_mar_y", "2026-03-14", "claude", "claude-opus-4-8", 400, 200)
_seed("p_feb", "2026-02-10", "claude", "claude-opus-4-8", 300, 0)
_T = _date(2026, 3, 15)

s_today = ui.summary("today", today=_T)
check("summary today: tokens = 1800 (claude 1500 + api 300)", s_today["kpi"]["tokens"] == 1800)
check("summary today: tokens_prev = 600 (hom qua)", s_today["kpi"]["tokens_prev"] == 600)
check("summary today: delta = 200%", s_today["kpi"]["delta_pct"] == 200.0)
check("summary today: sessions = 2 file", s_today["kpi"]["sessions"] == 2)
_prov = {x["key"]: x for x in s_today["by_provider"]}
check("summary today: by_provider claude=1500", _prov["claude"]["tokens"] == 1500)
check("summary today: by_provider api=300", _prov["api"]["tokens"] == 300)
check("summary today: cost opus > 0 (quy doi)", s_today["kpi"]["cost_est"] > 0)

s_month = ui.summary("this_month", today=_T)
check("summary this_month: gom 14+15 = 2400", s_month["kpi"]["tokens"] == 2400)
check("summary this_month: prev = thang 2 (02-10 = 300)", s_month["kpi"]["tokens_prev"] == 300)
check("summary this_month: timeseries 15 ngay", len(s_month["timeseries"]) == 15)

s_lastm = ui.summary("last_month", today=_T)
check("summary last_month: thang 2 = 300", s_lastm["kpi"]["tokens"] == 300)

# bien ky: 'today' KHONG gom hom qua
check("summary today: khong lan hom qua (1800 != 2400)", s_today["kpi"]["tokens"] == 1800)

# loc provider
s_cl = ui.summary("today", provider="claude", today=_T)
check("summary loc provider=claude: chi 1500", s_cl["kpi"]["tokens"] == 1500)


# ============================================================
# Task 7: insights()
# ============================================================
def _codes(period, t):
    return {i["code"] for i in ui.insights(period, today=t)}


# Fixture 5b o tren ghi vai dong theo NGAY THAT (_today_vn) de test nhanh du phong khi thieu
# log tho. Insight ben duoi lai so ky hien tai voi ky LIEN TRUOC theo ngay CO DINH, nen khi
# ngay that roi vao cua so so sanh cua mot moc co dinh thi dong rac do lam no canh bao oan.
# Vu that: 00:07 ngay 2026-08-01 gio VN, dong ngay-that nam trong ky truoc cua thang 9
# (01-15/08) -> "insight Sep: sach" do, dù chua ai sua gi. Don sach truoc khi vao phan insight.
_c = ui._connect()
_c.execute("DELETE FROM file_daily WHERE day=?", (_today_vn,))
_c.commit()
ui.refresh()

# May: cache_low + background_heavy + expensive_model (opus, khong cache, ngam nhieu)
_seed("p_may_bg", "2026-05-15", "claude", "claude-opus-4-8", 500000, 10000, cread=0, activity="background")
_seed("p_may_chat", "2026-05-15", "claude", "claude-opus-4-8", 100000, 5000, cread=0, activity="chat")
_cm = _codes("this_month", _date(2026, 5, 15))
check("insight May: co cache_low", "cache_low" in _cm)
check("insight May: co background_heavy", "background_heavy" in _cm)
check("insight May: co expensive_model (opus)", "expensive_model" in _cm)

# Sep: sach (sonnet, cache cao, toan chat, prev thang 8 rong)
_seed("p_sep", "2026-09-15", "claude", "claude-sonnet-4-6", 10000, 5000, cread=90000, activity="chat")
_cs = _codes("this_month", _date(2026, 9, 15))
check("insight Sep: khong canh bao nao (sach)", len(_cs) == 0)

# Oct: session_bloat + spike (1 phien 2M input, prev Sep nho)
_seed("p_oct", "2026-10-15", "claude", "claude-sonnet-4-6", 2000000, 10000, cread=0, activity="chat")
_co = _codes("this_month", _date(2026, 10, 15))
check("insight Oct: co session_bloat", "session_bloat" in _co)
check("insight Oct: co spike", "spike" in _co)


if _fails:
    print("\n%d FAIL" % len(_fails))
    sys.exit(1)
print("\nALL PASS")
