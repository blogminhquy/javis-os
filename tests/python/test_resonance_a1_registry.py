"""Resonance A1: sổ đăng ký agent trong kho và bản sao lưu trước A1.

    python tests/run.py resonance_a1_registry -v

Chỉ kiểm tầng kho (SQLite thật, không gọi model): cấp mã độc lập slug, công tắc chỉ của chủ dự án,
config_version, xoá rồi tạo lại cùng slug, file biến mất rồi xuất hiện lại, hai brain cùng slug,
dấu vết sự kiện, và bản `.pre-a1.bak` khi mã A1 mở một kho có từ trước.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

_STATE = tempfile.mkdtemp(prefix="javis-resonance-a1-")
os.environ["JAVIS_STATE_DIR"] = _STATE

import resonance_store as RS  # noqa: E402

_fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)


def raises(exc, fn):
    try:
        fn()
    except exc:
        return True
    except Exception as e:  # noqa: BLE001
        print(f"     (ném sai loại: {type(e).__name__}: {e})")
        return False
    return False


BRAIN = str(Path(tempfile.mkdtemp(prefix="brain-a-")).resolve())
OTHER = str(Path(tempfile.mkdtemp(prefix="brain-b-")).resolve())
OWNER = RS.Principal(kind="owner", id="owner", brain_id=BRAIN)
OWNER_B = RS.Principal(kind="owner", id="owner", brain_id=OTHER)
AGENT = RS.Principal(kind="agent", id="javis", brain_id=BRAIN)

store = RS.GoalStore(Path(_STATE) / "resonance.sqlite3")

# ───────────────────────────── cấp mã và công tắc ─────────────────────────────
check("agent chưa đăng ký thì không có dòng", store.agent(BRAIN, "viet-bai") is None)
check("tắt agent chưa đăng ký: không tạo dòng", store.agent_set_enabled(OWNER, "viet-bai", False) is None
      and store.agent(BRAIN, "viet-bai") is None)
check("agent không đổi được công tắc", raises(PermissionError, lambda: store.agent_set_enabled(AGENT, "viet-bai", True)))
check("agent không cho nghỉ được agent khác", raises(PermissionError, lambda: store.agent_retire(AGENT, "viet-bai")))

a = store.agent_set_enabled(OWNER, "viet-bai", True)
check("bật lần đầu cấp mã ag_ độc lập slug", a["agent_key"].startswith("ag_") and "viet-bai" not in a["agent_key"]
      and len(a["agent_key"]) == 19)
check("dòng mới: active, bật, version 1", a["status"] == "active" and a["enabled"] and a["config_version"] == 1)
same = store.agent_set_enabled(OWNER, "viet-bai", True)
check("bật lại khi đang bật: không tăng version", same["config_version"] == 1 and same["agent_key"] == a["agent_key"])
off = store.agent_set_enabled(OWNER, "viet-bai", False)
check("tắt: giữ mã, version tăng", off["agent_key"] == a["agent_key"] and not off["enabled"] and off["config_version"] == 2)
on = store.agent_set_enabled(OWNER, "viet-bai", True)
check("bật lại: vẫn mã cũ, version 3", on["agent_key"] == a["agent_key"] and on["enabled"] and on["config_version"] == 3)
check("đọc theo mã trong đúng brain", store.agent_by_key(BRAIN, a["agent_key"])["slug"] == "viet-bai")
check("mã của brain khác coi như không có", store.agent_by_key(OTHER, a["agent_key"]) is None)
check("slug rỗng bị từ chối", raises(RS.AgentStateError, lambda: store.agent_set_enabled(OWNER, "  ", True)))

# ───────────────────────────── hai brain cùng slug ─────────────────────────────
b = store.agent_set_enabled(OWNER_B, "viet-bai", True)
check("hai brain cùng slug: hai mã khác nhau", b["agent_key"] != a["agent_key"] and b["brain_id"] == OTHER)
check("danh sách theo brain không lẫn", [x["agent_key"] for x in store.agents(BRAIN)] == [a["agent_key"]]
      and [x["agent_key"] for x in store.agents(OTHER)] == [b["agent_key"]])
check("tắt ở brain A không đụng brain B", store.agent_set_enabled(OWNER, "viet-bai", False)["enabled"] is False
      and store.agent(OTHER, "viet-bai")["enabled"] is True)
store.agent_set_enabled(OWNER, "viet-bai", True)

# ───────────────────────────── xoá rồi tạo lại cùng slug ─────────────────────────────
r = store.agent_retire(OWNER, "viet-bai")
check("xoá qua host: retired, tắt, version tăng", r["status"] == "retired" and not r["enabled"]
      and r["config_version"] == on["config_version"] + 3)
check("sau khi nghỉ: không còn dòng sống cho slug", store.agent(BRAIN, "viet-bai") is None)
check("đọc theo mã cũ vẫn thấy lịch sử", store.agent_by_key(BRAIN, a["agent_key"])["status"] == "retired")
check("danh sách mặc định bỏ agent đã nghỉ, có cờ để xem", store.agents(BRAIN) == []
      and len(store.agents(BRAIN, include_retired=True)) == 1)
a2 = store.agent_set_enabled(OWNER, "viet-bai", True)
check("tạo lại cùng slug: mã MỚI, version 1", a2["agent_key"] != a["agent_key"] and a2["config_version"] == 1)
check("mã cũ vẫn retired, không sống lại", store.agent_by_key(BRAIN, a["agent_key"])["status"] == "retired")
check("cho nghỉ agent chưa đăng ký: không làm gì", store.agent_retire(OWNER, "khong-co") is None)

# ───────────────────────────── file biến mất rồi xuất hiện lại ─────────────────────────────
m = store.agent_mark_missing(BRAIN, a2["agent_key"])
check("file biến mất: missing, giữ công tắc, version tăng", m["status"] == "missing" and m["enabled"]
      and m["config_version"] == 2)
check("đánh dấu missing lặp lại không tăng version", store.agent_mark_missing(BRAIN, a2["agent_key"])["config_version"] == 2)
check("missing vẫn là dòng sống của slug", store.agent(BRAIN, "viet-bai")["agent_key"] == a2["agent_key"])
store.agent_set_enabled(OWNER, "viet-bai", False)
check("agent missing: tắt được", store.agent(BRAIN, "viet-bai")["enabled"] is False)
check("agent missing: không bật được khi chưa xác nhận",
      raises(RS.AgentStateError, lambda: store.agent_set_enabled(OWNER, "viet-bai", True)))
check("agent không tự xác nhận được", raises(PermissionError, lambda: store.agent_confirm(AGENT, a2["agent_key"], True)))
check("xác nhận mã của brain khác: không thấy", raises(RS.ScopeError, lambda: store.agent_confirm(OWNER_B, a2["agent_key"], True)))
c1 = store.agent_confirm(OWNER, a2["agent_key"], True)
check("xác nhận đúng trợ lý cũ: active, giữ mã", c1["status"] == "active" and c1["agent_key"] == a2["agent_key"])
check("xác nhận khi không missing bị từ chối",
      raises(RS.AgentStateError, lambda: store.agent_confirm(OWNER, a2["agent_key"], True)))
store.agent_set_enabled(OWNER, "viet-bai", True)
store.agent_mark_missing(BRAIN, a2["agent_key"])
c2 = store.agent_confirm(OWNER, a2["agent_key"], False)
check("trợ lý mới: mã mới, tắt, active", c2["agent_key"] != a2["agent_key"] and not c2["enabled"]
      and c2["status"] == "active")
check("mã cũ nghỉ khi chọn trợ lý mới", store.agent_by_key(BRAIN, a2["agent_key"])["status"] == "retired")
check("mỗi (brain, slug) chỉ một dòng sống",
      [x["agent_key"] for x in store.agents(BRAIN)] == [c2["agent_key"]])

# ───────────────────────────── dấu vết ─────────────────────────────
ev = store.agent_events(BRAIN, a2["agent_key"])
kinds = [e["kind"] for e in ev]
check("sự kiện đủ chuỗi đổi", kinds == ["registered", "missing", "disabled", "confirmed_same", "enabled",
                                        "missing", "retired"])
check("sự kiện ghi version trước và sau", all(e["version_after"] == (e["version_before"] or 0) + 1 for e in ev))
check("sự kiện ghi người đổi", ev[0]["by"] == "owner:owner" and ev[1]["by"] == "host")
check("mã mới ghi nó thay mã nào", store.agent_events(BRAIN, c2["agent_key"])[0]["payload"].get("replaces")
      == a2["agent_key"])
check("đọc sự kiện theo brain khác: rỗng", store.agent_events(OTHER, a2["agent_key"]) == [])

# ───────────────────────────── schema thêm cột, không xoá ─────────────────────────────
with sqlite3.connect(str(store.path)) as con:
    gcols = {r[1] for r in con.execute("PRAGMA table_info(goals)")}
    hcols = {r[1] for r in con.execute("PRAGMA table_info(handoffs)")}
check("goals có cột agent_key", "agent_key" in gcols and "calls_used" in gcols)
check("handoffs có agent_key và agent_config_version", {"agent_key", "agent_config_version"} <= hcols)
check("kho mới tinh không sinh bản sao pre-a1", not (Path(_STATE) / "resonance.sqlite3.pre-a1.bak").exists())

# ───────────────────────────── bản sao lưu trước A1 ─────────────────────────────
OLD_DIR = Path(tempfile.mkdtemp(prefix="javis-resonance-old-"))
old = OLD_DIR / "resonance.sqlite3"
with sqlite3.connect(str(old)) as con:
    # Mô phỏng kho của bản 0.86.x: có goals và một mục tiêu, chưa có bảng sổ đăng ký.
    con.executescript(RS._SCHEMA.split("CREATE TABLE IF NOT EXISTS resonance_agents")[0])
    con.execute("INSERT INTO goals(id,brain_id,owner,revision,status,session_id,request_ref,idempotency_key,"
                "output_root,user_constraints_json,budget_calls,calls_used,paused,created_at,updated_at) "
                "VALUES('g_old',?, 'javis',1,'active','s1','m1','k1','/tmp/x','[]',3,1,0,1,1)", (BRAIN,))
RS.GoalStore(old)
bak = OLD_DIR / "resonance.sqlite3.pre-a1.bak"
check("kho có từ trước: sinh bản .pre-a1.bak", bak.is_file())
with sqlite3.connect(str(bak)) as con:
    names = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    rows = con.execute("SELECT id, calls_used FROM goals").fetchall()
    bcols = {r[1] for r in con.execute("PRAGMA table_info(goals)")}
check("bản sao giữ nguyên dữ liệu cũ, chưa có schema A1", rows == [("g_old", 1)] and "resonance_agents" not in names
      and "agent_key" not in bcols)
with sqlite3.connect(str(old)) as con:
    live = con.execute("SELECT id, agent_key FROM goals").fetchall()
check("kho gốc sau nâng cấp: mục tiêu cũ còn, agent_key rỗng", live == [("g_old", None)])
mtime = bak.stat().st_mtime_ns
RS.GoalStore(old)
check("mở lại không chép đè bản sao", bak.stat().st_mtime_ns == mtime)
check("không để lại file tạm", not (OLD_DIR / "resonance.sqlite3.pre-a1.bak.tmp").exists())

if _fails:
    print(f"\n{len(_fails)} FAIL:", _fails)
    sys.exit(1)
print("\nOK")
