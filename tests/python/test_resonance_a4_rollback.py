"""Resonance A4: nâng từ 0.89.0, hạ về 0.89.0 bằng snapshot (thiết kế A4 mục 7.4, D11; ca G47, G48, G50).

    python tests/run.py resonance_a4_rollback -v

Nạp `server/resonance*.py` của commit phát hành 0.89.0 (`33a3c1aa` trên main) qua `git show`:
1. mã 0.89.0 THẬT lập kho và một mục tiêu có trợ lý và đường sản phẩm;
2. mã A4 mở kho đó: snapshot `.pre-0.90.0` đúng một bản, đóng băng legacy; chạy, đăng, rồi thu hồi;
3. G48: mã 0.89.0 chạy `resume` trên kho A4 KHÔNG khôi phục: ghi nhận đúng giới hạn đã công bố (mã cũ gỡ tạm dừng,
   không biết thu hồi). Test này chứng minh tài liệu nói thật, KHÔNG chứng minh đã chặn được;
4. G50: script khôi phục chép kho hiện tại sang bản `post-0.90.0-*` rồi ghi snapshot vào; mã 0.89.0 mở được, mục tiêu
   ở trạng thái lúc nâng.
Engine giả, không model thật. Máy không có lịch sử git của commit đó thì in SKIP; trên CI (biến CI) thì ĐỎ.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import hashlib
import importlib.util
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

_STATE = tempfile.mkdtemp(prefix="javis-resonance-a4rb-")
os.environ["JAVIS_STATE_DIR"] = _STATE
os.environ.pop("JAVIS_RESONANCE_CALL_CEILING", None)

import resonance as R  # noqa: E402
import resonance_store as RS  # noqa: E402
import _resonance_agent as RA  # noqa: E402

sys.path.insert(0, str(ROOT / "tools"))
import resonance_restore_pre_a4 as RESTORE  # noqa: E402

OLD_SHA = "33a3c1aa"
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
        print(f"FAIL không đọc được mã của {OLD_SHA}: CI phải fetch commit này trước")
        sys.exit(1)
    print(f"SKIP máy này không có lịch sử git của {OLD_SHA}")
    sys.exit(0)

_dir = Path(tempfile.mkdtemp(prefix="old-0890-"))


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
    OLD_HB = _load("resonance_heartbeat_0890", srcs["resonance_heartbeat"])
    sys.modules["resonance_heartbeat"] = OLD_HB
    OLD_L = _load("resonance_learning_0890", srcs["resonance_learning"])
    sys.modules["resonance_learning"] = OLD_L
    OLD_R = _load("resonance_0890", srcs["resonance"])
    sys.modules["resonance"] = OLD_R
    OLD_S = _load("resonance_store_0890", srcs["resonance_store"])
finally:
    sys.modules.update(_saved)
check("nạp đúng mã 0.89.0: kho cũ không biết bảng quyền A4", not hasattr(OLD_S, "A4_TABLES")
      and hasattr(RS, "A4_TABLES"))

BRAIN = str(Path(tempfile.mkdtemp(prefix="brain-a4rb-")).resolve())
(Path(BRAIN) / "Inbox").mkdir(parents=True)
(Path(BRAIN) / "Javis").mkdir(parents=True)
DELIV = "Inbox/a4rb.md"
GOOD = "# Ghi chú\n\nBáo cáo quý, máy lạnh.\n"
USER = "Viết giúp anh một ghi chú tổng hợp trong Inbox gồm báo cáo quý và máy lạnh."
PROPOSAL = {"understanding": "Ghi chú tổng hợp", "relevant_quote": "Viết giúp anh một ghi chú tổng hợp",
            "criteria": [{"description": "Có báo cáo quý", "evaluator": "artifact_contract",
                          "params": {"path": DELIV, "must_contain": ["báo cáo quý"]}}],
            "horizon": {"kind": "review", "at_iso": "2027-01-20T09:00:00+07:00"}, "stage": "delivery",
            "mode": "achieve"}


class Engine:
    def __init__(self):
        self.queries, self.max_wall_s = 0, None

    def is_available(self):
        return True

    async def query(self, prompt):
        self.queries += 1
        yield {"type": "final", "content": GOOD, "tokens_in": 1, "tokens_out": 1}


class Evidence:
    def __init__(self):
        self.items = {}

    def put(self, goal, label, text, meta):
        eid = f"ev_{len(self.items) + 1}"
        self.items[eid] = {"text": text, "content_hash": hashlib.sha256(text.encode("utf-8")).hexdigest()}
        return eid

    def valid(self, eid):
        return self.items.get(eid)


async def _nt(goal, kind, text, card="", quiet=False):
    return True


def deps(mod, store, eng, clock):
    return mod.GoalDeps(engine_factory=lambda s, t: (eng, {"provider": "fake", "model": "fake-1", "text_only": True}),
                        budget=mod.CallBudget(0), clock=lambda: clock[0], store=store,
                        principal=mod_principal(store)("agent", "javis", BRAIN), brain_root=BRAIN,
                        evidence=Evidence(), notify=_nt)


def mod_principal(store):
    return OLD_S.Principal if isinstance(store, OLD_S.GoalStore) else RS.Principal


state_dir = Path(tempfile.mkdtemp(prefix="state-a4rb-"))
db = state_dir / "resonance.sqlite3"

# 1. Mã 0.89.0 lập kho và mục tiêu.
old = OLD_S.GoalStore(db)
ag = RA.enable(old, BRAIN)
op = OLD_S.Principal("agent", ag["agent_key"], BRAIN)
g = asyncio.run(OLD_R.form_goal(OLD_R.message_ref("s", 1), {
    "principal": op, "brain_root": BRAIN, "session_id": "s", "message_id": 1, "user_text": USER, "constraints": [],
    "budget_calls": 4, "proposal": PROPOSAL, "agent_key": ag["agent_key"], "agent_version": ag["config_version"]},
    OLD_R.GoalDeps(engine_factory=lambda s, t: (None, {}), budget=OLD_R.CallBudget(0), store=old)))
check("0.89.0 lập mục tiêu có trợ lý và đường sản phẩm", g.agent_key == ag["agent_key"] and g.revision == 1)
del old

# 2. Mã A4 mở kho: snapshot một lần, đóng băng legacy; chạy, đăng.
new = RS.GoalStore(db)
snap = db.with_name(db.name + RS.A4_BACKUP_SUFFIX)
with sqlite3.connect(str(snap)) as c:
    snap_tables = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
owner = RS.Principal("owner", "owner", BRAIN)
sc = new.scope_state(owner, g.id)
check("G47 nâng lên: snapshot .pre-0.90.0 có đúng dữ liệu trước nâng, không có bảng A4",
      snap.is_file() and "goals" in snap_tables and "grants" not in snap_tables)
check("G28 mục tiêu 0.89.0 được đóng băng legacy_frozen đúng đường sản phẩm",
      sc["state"] == "granted" and sc["root"]["source"] == "legacy_frozen")
clock = [1_800_000_000.0]
eng = Engine()
asyncio.run(R.tick(new, clock[0], lambda b: deps(R, new, eng, clock)))
check("A4 làm việc dưới quyền legacy: đăng sản phẩm", (Path(BRAIN) / DELIV).read_text(encoding="utf-8") == GOOD
      and eng.queries == 1)
calls_after_a4 = new.get(owner, g.id).calls_used
R.apply_command(new, owner, g.id, "revoke_grant", {"expected_revision": g.revision}, BRAIN)
check("A4 thu hồi: gốc revoked, mục tiêu tạm dừng", new.scope_state(owner, g.id)["state"] == "revoked"
      and new.get(owner, g.id).paused)

# 3. G48: chạy mã 0.89.0 trên BẢN SAO kho A4, không khôi phục snapshot.
copy = state_dir / "copy.sqlite3"
with sqlite3.connect(str(db)) as s, sqlite3.connect(str(copy)) as d:
    s.backup(d)
old_c = OLD_S.GoalStore(copy)
oowner = OLD_S.Principal("owner", "owner", BRAIN)
res = OLD_R.apply_command(old_c, oowner, g.id, "resume", {}, BRAIN)
check("G48 không hỗ trợ: mã 0.89.0 gỡ tạm dừng mục tiêu đã thu hồi (giới hạn đã công bố là đúng sự thật)",
      res.get("ok") and not old_c.get(oowner, g.id).paused, res)
del old_c

# 4. G50: script khôi phục, rồi chạy 0.89.0.
del new
r = RESTORE.restore(str(state_dir))
kept = Path(r.get("kept") or "")
with sqlite3.connect(str(kept)) as c:
    kept_tables = {r_[0] for r_ in c.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    kept_calls = c.execute("SELECT calls_used FROM goals WHERE id=?", (g.id,)).fetchone()[0]
check("G50 script: giữ bản kho hiện tại (post-0.90.0, có bảng quyền và lượt đã chạy) trước khi khôi phục",
      r["ok"] and kept.is_file() and "grants" in kept_tables and kept_calls == calls_after_a4, r)
old2 = OLD_S.GoalStore(db)
g_old = old2.get(OLD_S.Principal("owner", "owner", BRAIN), g.id)
with sqlite3.connect(str(db)) as c:
    tables_now = {r_[0] for r_ in c.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
check("G50 khôi phục rồi chạy 0.89.0: kho mở được, mục tiêu ở trạng thái lúc nâng (revision 1, chưa dùng lượt, không tạm "
      "dừng, không có bảng A4)", g_old is not None and g_old.revision == 1 and g_old.calls_used == 0
      and not g_old.paused and "grants" not in tables_now, (g_old, tables_now))
check("G50 file đã đăng trong brain vẫn còn (0.89.0 thấy là drift so với mốc cũ)",
      (Path(BRAIN) / DELIV).is_file())
check("script không có snapshot: báo rõ, không ghi gì", RESTORE.restore(tempfile.mkdtemp())["ok"] is False)

if _fails:
    print(f"\n{len(_fails)} FAIL: {_fails}")
raise SystemExit(1 if _fails else 0)
