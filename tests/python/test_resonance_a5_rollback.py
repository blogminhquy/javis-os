"""Resonance A5: nâng từ 0.108.0, hạ về 0.108.0 bằng snapshot (thiết kế A5 mục 13; ca T30).

    python tests/run.py resonance_a5_rollback -v

Nạp `server/resonance*.py` của commit phát hành 0.108.0 (`c4fb614d` trên main, bản cuối trước A5) qua `git show`:
1. mã 0.108.0 THẬT lập kho và một mục tiêu có trợ lý và đường sản phẩm;
2. mã A5 mở kho đó: snapshot `.pre-0.109.0` đúng một bản, không có bảng A5; mục tiêu cũ không có đội, chạy như A4;
   mục tiêu mới có đội dừng ở chờ review;
3. hạ KHÔNG khôi phục: mã 0.108.0 chốt đạt mục tiêu có đội mà không có review (giới hạn đã công bố là đúng sự thật);
4. script khôi phục giữ bản kho hiện tại `post-0.109.0-*` rồi ghi snapshot; mã 0.108.0 mở được;
5. nâng lại: snapshot đã có thì không chép lại.
Engine giả, không model thật. Máy không có lịch sử git của commit đó thì in SKIP; trên CI (biến CI) thì ĐỎ.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import hashlib
import importlib.util
import os
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

_STATE = tempfile.mkdtemp(prefix="javis-resonance-a5rb-")
os.environ["JAVIS_STATE_DIR"] = _STATE
os.environ.pop("JAVIS_RESONANCE_CALL_CEILING", None)

import resonance as R  # noqa: E402
import resonance_store as RS  # noqa: E402
import _resonance_agent as RA  # noqa: E402
import _resonance_team as T  # noqa: E402

sys.path.insert(0, str(ROOT / "tools"))
import resonance_restore_pre_a5 as RESTORE  # noqa: E402

OLD_SHA = "c4fb614d30b63e592e66a8f943cf2749bb33a412"
_fails = []


def check(name, cond, info=None):
    print(("ok   " if cond else "FAIL ") + name + ("" if cond or info is None else f"  ({str(info)[:300]})"))
    if not cond:
        _fails.append(name)


def _show(path):
    return subprocess.check_output(["git", "-C", str(ROOT), "show", f"{OLD_SHA}:{path}"],
                                   stderr=subprocess.DEVNULL).decode("utf-8")


try:
    srcs = {n: _show(f"server/{n}.py") for n in ("resonance_heartbeat", "resonance_learning", "resonance",
                                                  "resonance_store")}
except (subprocess.CalledProcessError, OSError):
    if os.environ.get("CI"):
        print(f"FAIL không đọc được mã của {OLD_SHA[:8]}: CI phải fetch commit này trước")
        sys.exit(1)
    print(f"SKIP máy này không có lịch sử git của {OLD_SHA[:8]}")
    sys.exit(0)

_dir = Path(tempfile.mkdtemp(prefix="old-0100-"))


def _load(name, src):
    f = _dir / f"{name}.py"
    f.write_text(src, encoding="utf-8", newline="\n")
    spec = importlib.util.spec_from_file_location(name, f)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


_saved = {k: sys.modules[k] for k in ("resonance", "resonance_heartbeat", "resonance_learning")}
try:
    OLD_HB = _load("resonance_heartbeat_0100", srcs["resonance_heartbeat"])
    sys.modules["resonance_heartbeat"] = OLD_HB
    OLD_L = _load("resonance_learning_0100", srcs["resonance_learning"])
    sys.modules["resonance_learning"] = OLD_L
    OLD_R = _load("resonance_0100", srcs["resonance"])
    sys.modules["resonance"] = OLD_R
    OLD_S = _load("resonance_store_0100", srcs["resonance_store"])
finally:
    sys.modules.update(_saved)
check("nạp đúng mã 0.108.0: kho cũ không biết bảng A5", not hasattr(OLD_S, "A5_TABLES") and hasattr(RS, "A5_TABLES"))

BRAIN = str(Path(tempfile.mkdtemp(prefix="brain-a5rb-")).resolve())
(Path(BRAIN) / "Javis").mkdir(parents=True)


class Evidence:
    def __init__(self):
        self.items = {}

    def put(self, goal, label, text, meta):
        eid = f"ev_{len(self.items) + 1}"
        self.items[eid] = {"text": text, "content_hash": hashlib.sha256(text.encode("utf-8")).hexdigest()}
        return eid

    def valid(self, eid):
        return self.items.get(eid)


EV = Evidence()
WORK, REV = T.Engine(T.GOOD), T.Engine(T.PASS)


async def _nt(goal, kind, text, card="", quiet=False):
    return True


def deps(mod, store, clock):
    P = OLD_S.Principal if isinstance(store, OLD_S.GoalStore) else RS.Principal

    def factory(s, t):
        return (REV if s == getattr(mod, "REVIEW_SYSTEM", None) else WORK), {"provider": "fake", "model": "fake-1",
                                                                             "text_only": True}
    return mod.GoalDeps(engine_factory=factory, budget=mod.CallBudget(0), clock=lambda: clock[0], store=store,
                        principal=P("agent", "javis", BRAIN), brain_root=BRAIN, evidence=EV, notify=_nt)


def proposal(path):
    return {"understanding": "Bản tóm tắt cuộc họp", "relevant_quote": "Em lo giúp anh bản tóm tắt cuộc họp",
            "criteria": [{"description": "Có mục Kết luận", "evaluator": "artifact_contract",
                          "params": {"path": path, "must_contain": ["Kết luận"]}}],
            "horizon": {"kind": "review", "at_iso": "2027-01-20T09:00:00+07:00"}, "stage": "delivery", "mode": "achieve"}


def form(mod, store, agent, mid, path):
    P = OLD_S.Principal if isinstance(store, OLD_S.GoalStore) else RS.Principal
    return asyncio.run(mod.form_goal(mod.message_ref("s", mid), {
        "principal": P("agent", agent["agent_key"], BRAIN), "brain_root": BRAIN, "session_id": "s", "message_id": mid,
        "user_text": T.USER, "constraints": [], "budget_calls": 4, "proposal": proposal(path),
        "agent_key": agent["agent_key"], "agent_version": agent["config_version"]},
        mod.GoalDeps(engine_factory=lambda s, t: (None, {}), budget=mod.CallBudget(0), store=store)))


state_dir = Path(tempfile.mkdtemp(prefix="state-a5rb-"))
db = state_dir / "resonance.sqlite3"
clock = [1_800_000_000.0]

# 1. Mã 0.108.0 lập kho và một mục tiêu.
old = OLD_S.GoalStore(db)
maker = RA.enable(old, BRAIN, T.MAKER)
g_old = form(OLD_R, old, maker, 1, "Inbox/cu.md")
RA.approve(old, BRAIN, g_old.id)
check("0.108.0 lập mục tiêu có trợ lý và đường sản phẩm", g_old.agent_key == maker["agent_key"])
del old

# 2. Mã A5 mở kho: snapshot một lần; mục tiêu cũ không có đội. (0.142.0 bỏ người review cố định cho mục tiêu mới: bật
# lại việc gắn đội để dựng đúng kho của thời A5 mà phép thử hạ phiên bản cần.)
new = RS.GoalStore(db)
new.attach_reviewer_teams = True
snap = db.with_name(db.name + RS.A5_BACKUP_SUFFIX)
with sqlite3.connect(str(snap)) as c:
    snap_tables = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
snap_mtime = snap.stat().st_mtime_ns
check("T30 nâng lên: snapshot .pre-0.109.0 có dữ liệu trước nâng, không có bảng A5",
      snap.is_file() and "goals" in snap_tables and not (set(RS.A5_TABLES) & snap_tables))
owner = RS.Principal("owner", "owner", BRAIN)
reviewer = RA.enable(new, BRAIN, T.REVIEWER)
new.team_pair_set(owner, maker["agent_key"], reviewer["agent_key"])
check("T30 mục tiêu có từ trước không có đội", new.goal_team(owner, g_old.id) is None)
asyncio.run(R.advance(g_old.id, {"kind": "wake"}, deps(R, new, clock)))
check("T30 mục tiêu cũ chạy như A4: đạt không qua review", new.get(owner, g_old.id).status == "succeeded"
      and REV.queries == 0, new.get(owner, g_old.id).status)
g_team = form(R, new, new.agent(BRAIN, T.MAKER), 2, "Inbox/doi.md")
RA.approve(new, BRAIN, g_team.id)
asyncio.run(R.advance(g_team.id, {"kind": "wake"}, deps(R, new, clock)))
check("T30 mục tiêu mới có đội dừng ở chờ review", new.goal_team(owner, g_team.id)["status"] == "active"
      and (new.run_state(owner, g_team.id) or {}).get("block_reason") == "review_pending")
calls_after = new.get(owner, g_team.id).calls_used

# 3. Hạ KHÔNG khôi phục (không hỗ trợ): mã 0.108.0 trên BẢN SAO kho A5.
copy = state_dir / "copy.sqlite3"
with sqlite3.connect(str(db)) as s, sqlite3.connect(str(copy)) as d:
    s.backup(d)
old_c = OLD_S.GoalStore(copy)
asyncio.run(OLD_R.advance(g_team.id, {"kind": "wake"}, deps(OLD_R, old_c, clock)))
check("T30 không hỗ trợ: mã 0.108.0 chốt đạt mục tiêu có đội mà không có review (giới hạn đã công bố là đúng sự thật)",
      old_c.get(OLD_S.Principal("owner", "owner", BRAIN), g_team.id).status == "succeeded" and REV.queries == 0)
del old_c

# 4. Script khôi phục, rồi chạy 0.108.0.
del new
r = RESTORE.restore(str(state_dir))
kept = Path(r.get("kept") or "")
with sqlite3.connect(str(kept)) as c:
    kept_tables = {x[0] for x in c.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    kept_calls = c.execute("SELECT calls_used FROM goals WHERE id=?", (g_team.id,)).fetchone()[0]
check("T30 script: giữ bản kho hiện tại (post-0.109.0, có bảng A5 và lượt đã chạy) trước khi khôi phục",
      r["ok"] and kept.is_file() and set(RS.A5_TABLES) <= kept_tables and kept_calls == calls_after, r)
old2 = OLD_S.GoalStore(db)
o2 = OLD_S.Principal("owner", "owner", BRAIN)
with sqlite3.connect(str(db)) as c:
    tables_now = {x[0] for x in c.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
check("T30 khôi phục rồi chạy 0.108.0: kho mở được, ở trạng thái lúc nâng (chỉ có mục tiêu cũ, chưa chạy), không có "
      "bảng A5", old2.get(o2, g_old.id) is not None and old2.get(o2, g_old.id).calls_used == 0
      and old2.get(o2, g_team.id) is None and not (set(RS.A5_TABLES) & tables_now), tables_now)
del old2

# 5. Nâng lại sau khi mã cũ đã chạy: snapshot đã có thì không chép lại.
again = RS.GoalStore(db)
check("T30 nâng lại: không chép lại snapshot; bảng A5 tạo lại rỗng; mục tiêu cũ không có đội",
      snap.stat().st_mtime_ns == snap_mtime and again.goal_team(owner, g_old.id) is None)
check("script không có snapshot: báo rõ, không ghi gì", RESTORE.restore(tempfile.mkdtemp())["ok"] is False)

if _fails:
    print(f"\n{len(_fails)} FAIL: {_fails}")
raise SystemExit(1 if _fails else 0)
