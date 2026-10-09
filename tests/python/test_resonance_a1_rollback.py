"""Resonance A1: quay về 0.86.1 trên kho đã nâng, chạy bằng MÃ 0.86.1 THẬT (review PR #590, P1-2).

    python tests/run.py resonance_a1_rollback -v

Nạp `server/resonance_store.py` của commit phát hành 0.86.1 (`09f254d0`) qua `git show`, rồi đi vòng:
kho tạo bằng 0.86.1 → mở bằng A1 (nâng, sao lưu, ghi dữ liệu A1) → chạy lại các đường GHI của 0.86.1 (tạo mục
tiêu có bàn giao, sửa cách hiểu, sổ hành động, đăng sản phẩm, huỷ) → mở lại bằng A1. Không gọi model.

Máy không có lịch sử git của `09f254d0` thì in SKIP; trên CI (biến CI) thì ĐỎ, vì CI phải lấy commit đó trước.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import importlib.util
import os
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path

_STATE = tempfile.mkdtemp(prefix="javis-resonance-a1rb-")
os.environ["JAVIS_STATE_DIR"] = _STATE

import resonance_store as RS  # noqa: E402

OLD_SHA = "09f254d0e4d009451dc58cb2e97788631c5acc1a"
_fails = []


def check(name, cond, info=None):
    print(("ok   " if cond else "FAIL ") + name + ("" if cond or info is None else f"  ({info})"))
    if not cond:
        _fails.append(name)


try:
    old_src = subprocess.check_output(["git", "-C", str(ROOT), "show", f"{OLD_SHA}:server/resonance_store.py"],
                                      stderr=subprocess.DEVNULL).decode("utf-8")
except (subprocess.CalledProcessError, OSError):
    if os.environ.get("CI"):
        print(f"FAIL không đọc được server/resonance_store.py của {OLD_SHA[:8]}: CI phải fetch commit này trước")
        sys.exit(1)
    print(f"SKIP máy này không có lịch sử git của {OLD_SHA[:8]}")
    sys.exit(0)

_old_file = Path(tempfile.mkdtemp(prefix="old-store-")) / "resonance_store_0861.py"
_old_file.write_text(old_src, encoding="utf-8", newline="\n")
_spec = importlib.util.spec_from_file_location("resonance_store_0861", _old_file)
OLD = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = OLD
_spec.loader.exec_module(OLD)

BRAIN = str(Path(tempfile.mkdtemp(prefix="brain-rb-")).resolve())
DB = Path(_STATE) / "rollback" / "resonance.sqlite3"
FRAME = {"understanding": "Ví dụ", "constraints": [], "criteria": [], "guards": [], "mode": "achieve"}
op = OLD.Principal("agent", "javis", BRAIN)
oo = OLD.Principal("owner", "owner", BRAIN)


def old_write_paths(store, tag):
    """Các đường GHI chính của 0.86.1. Trả mã mục tiêu, hay ném lỗi của mã cũ."""
    it = store.add_intent(op, "s1", int(time.time() * 1000) % 100000, f"Việc {tag}")
    g, created = store.create(op, it["id"], FRAME, f"k-{tag}", session_id="s1", handoff_owner="boot-old",
                              budget_calls=3)
    assert created and store.handoff(op, g.id, 1)
    g2 = store.revise(op, g.id, 1, dict(FRAME, understanding=f"Ví dụ {tag} v2"), "sửa", handoff_owner="boot-old")
    assert g2.revision == 2 and store.handoff(op, g.id, 2)
    a = store.begin_action(op, g.id, 2, "work", time.time() + 60)
    store.finish_action(op, a["id"], "done", {"ok": True})
    store.set_published(op, g.id, "out/bai.md", "0" * 64, a["id"])
    assert store.cancel(oo, g.id, 2)
    return g.id


# 1. Kho do 0.86.1 tạo, có mục tiêu và bàn giao.
legacy = OLD.GoalStore(DB)
g_before = old_write_paths(legacy, "truoc")
check("0.86.1 ghi được trên kho của chính nó (đối chứng)", bool(g_before))

# 2. Mở bằng A1: nâng, sao lưu, ghi dữ liệu A1.
a1 = RS.GoalStore(DB)
bak = DB.with_name(DB.name + ".pre-a1.bak")
check("mở bằng A1: có bản sao .pre-a1.bak", bak.is_file())
ow = RS.Principal("owner", "owner", BRAIN)
ag = a1.agent_set_enabled(ow, "viet-bai", True)
a1.session_agent(BRAIN, "s-agent", "viet-bai", time.time())
# Một mục tiêu A1 THẬT (review vòng 2): gắn trợ lý (goal_agents) và mở bàn giao có version (handoff_agents).
_ap = RS.Principal("agent", ag["agent_key"], BRAIN)
_it = a1.add_intent(_ap, "s-agent", 7, "Việc của trợ lý")
g_a1, _ = a1.create(_ap, _it["id"], FRAME, "k-a1", session_id="s-agent", handoff_owner="boot-a1", budget_calls=3,
                    agent_key=ag["agent_key"], agent_version=ag["config_version"])
check("A1 tạo mục tiêu gắn trợ lý, có handoff_agents", g_a1.agent_key == ag["agent_key"]
      and a1.handoff_agent(_ap, g_a1.id, 1) is not None)

# 3. Quay về: mã 0.86.1 thật chạy lại mọi đường ghi trên kho đã nâng.
legacy = OLD.GoalStore(DB)
try:
    g_after = old_write_paths(legacy, "sau")
    err = ""
except Exception as e:  # noqa: BLE001
    g_after, err = None, f"{type(e).__name__}: {e}"
check("quay về 0.86.1: tạo mục tiêu có bàn giao, sửa, sổ hành động, đăng, huỷ đều chạy", bool(g_after), err)
check("quay về 0.86.1: đọc được mục tiêu tạo trước lúc nâng và lúc quay về",
      legacy.get(oo, g_before) is not None and (g_after is None or legacy.get(oo, g_after) is not None))
try:
    _g = legacy.get(oo, g_a1.id)
    _r = legacy.revise(op, g_a1.id, 1, dict(FRAME, understanding="Sửa dưới 0.86.1"), "sửa", handoff_owner="boot-old")
    _a = legacy.begin_action(op, g_a1.id, 2, "work", time.time() + 60)
    legacy.finish_action(op, _a["id"], "done", {"ok": True})
    err_a1 = "" if _g is not None and _r.revision == 2 else "không đọc hay sửa được"
except Exception as e:  # noqa: BLE001
    err_a1 = f"{type(e).__name__}: {e}"
check("quay về 0.86.1: mã cũ đọc, sửa có bàn giao, giữ lượt được trên mục tiêu do A1 tạo", not err_a1, err_a1)

# 4. Nâng lại lên A1: dữ liệu A1 còn, mục tiêu tạo lúc quay về chưa gán agent nào, bản sao không bị ghi đè.
mt = bak.stat().st_mtime_ns
a1 = RS.GoalStore(DB)
check("nâng lại: sổ đăng ký và liên kết phiên còn nguyên",
      a1.agent(BRAIN, "viet-bai")["agent_key"] == ag["agent_key"]
      and a1.session_pin("s-agent")["agent_key"] == ag["agent_key"])
with sqlite3.connect(str(DB)) as con:
    bound = {r[0] for r in con.execute("SELECT goal_id FROM goal_agents")}
check("nâng lại: mục tiêu tạo bằng 0.86.1 không tự gán agent", g_before not in bound and g_after not in bound)
check("nâng lại: mục tiêu A1 vẫn gắn đúng trợ lý; bàn giao mở dưới 0.86.1 không có version A1",
      a1.get(ow, g_a1.id).agent_key == ag["agent_key"] and a1.handoff_agent(ow, g_a1.id, 1) is not None
      and a1.handoff_agent(ow, g_a1.id, 2) is None)
check("nâng lại: không chép đè bản sao pre-a1", bak.stat().st_mtime_ns == mt)
with sqlite3.connect(str(bak)) as con:
    ids = {r[0] for r in con.execute("SELECT id FROM goals")}
check("bản sao pre-a1 chỉ có dữ liệu TRƯỚC lúc nâng (phục hồi bằng nó mất phần sau)",
      g_before in ids and g_after not in ids)

if _fails:
    print(f"\n{len(_fails)} FAIL:", _fails)
    sys.exit(1)
print("\nOK")
