"""Resonance A2: quay về 0.87.0 trên kho đã nâng, chạy bằng MÃ 0.87.0 THẬT (thiết kế A2 mục 12).

    python tests/run.py resonance_a2_rollback -v

Nạp `server/resonance.py` và `server/resonance_store.py` của commit 0.87.0 (A1, `077bcf73`) qua `git show`, rồi đi
vòng: kho mở bằng A2 (sao lưu pre-a2, ghi lý do, sổ thức) → mã 0.87.0 thật tạo mục tiêu và chạy một nhịp có lượt việc
(engine giả) → mở lại bằng A2: bảng A2 còn nguyên, sự kiện mà lượt của 0.87 đã có thể thấy được đối soát, không gọi
model thừa. Không gọi model thật.

Máy không có lịch sử git của commit đó thì in SKIP; trên CI (biến CI) thì ĐỎ, vì CI phải lấy commit đó trước.
Khi A1 merge vào main bằng squash, đổi OLD_SHA sang commit 0.87.0 trên main.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import importlib.util
import os
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path

_STATE = tempfile.mkdtemp(prefix="javis-resonance-a2rb-")
os.environ["JAVIS_STATE_DIR"] = _STATE

import resonance as R  # noqa: E402
import resonance_store as RS  # noqa: E402
import _resonance_agent as RA  # noqa: E402

OLD_SHA = "077bcf73a5c02f90b38bb663698d98f8236dbc86"
_fails = []


def check(name, cond, info=None):
    print(("ok   " if cond else "FAIL ") + name + ("" if cond or info is None else f"  ({info})"))
    if not cond:
        _fails.append(name)


def _show(path):
    return subprocess.check_output(["git", "-C", str(ROOT), "show", f"{OLD_SHA}:{path}"],
                                   stderr=subprocess.DEVNULL).decode("utf-8")


try:
    old_r_src, old_s_src = _show("server/resonance.py"), _show("server/resonance_store.py")
except (subprocess.CalledProcessError, OSError):
    if os.environ.get("CI"):
        print(f"FAIL không đọc được mã của {OLD_SHA[:8]}: CI phải fetch commit này trước")
        sys.exit(1)
    print(f"SKIP máy này không có lịch sử git của {OLD_SHA[:8]}")
    sys.exit(0)

_dir = Path(tempfile.mkdtemp(prefix="old-087-"))


def _load(name, src):
    f = _dir / f"{name}.py"
    f.write_text(src, encoding="utf-8", newline="\n")
    spec = importlib.util.spec_from_file_location(name, f)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


# Mã 0.87 nạp với tên riêng; kho cũ phải thấy resonance CŨ khi `import resonance as R`.
OLD_R = _load("resonance_087", old_r_src)
_saved = sys.modules["resonance"]
sys.modules["resonance"] = OLD_R
try:
    OLD_S = _load("resonance_store_087", old_s_src)
finally:
    sys.modules["resonance"] = _saved

BRAIN = str(Path(tempfile.mkdtemp(prefix="brain-a2rb-")).resolve())
(Path(BRAIN) / "Inbox").mkdir(parents=True)
DB = Path(_STATE) / "rb" / "resonance.sqlite3"
T0 = 1_800_000_000.0
USER = "Viết giúp anh một ghi chú tổng hợp trong Inbox gồm báo cáo quý."
GOOD = "# Ghi chú\n\nBáo cáo quý đã có.\n"


class Engine:
    def __init__(self):
        self.queries = 0
        self.max_wall_s = None

    def is_available(self):
        return True

    async def query(self, prompt):
        self.queries += 1
        yield {"type": "final", "content": GOOD, "tokens_in": 1, "tokens_out": 1}


class Evidence:
    def __init__(self):
        self.items = {}

    def put(self, goal, action_id, text, metadata):
        eid = f"ev_{len(self.items) + 1}"
        self.items[eid] = {"text": text}
        return eid

    def valid(self, evidence_id):
        return self.items.get(evidence_id)


async def _nt(goal, kind, text, card=""):
    return True


def proposal(path):
    return {"understanding": "Ghi chú tổng hợp", "relevant_quote": "Viết giúp anh một ghi chú tổng hợp trong Inbox",
            "criteria": [{"description": "Có báo cáo quý", "evaluator": "artifact_contract",
                          "params": {"path": path, "must_contain": ["báo cáo quý"]}}],
            "horizon": {"kind": "review", "at_iso": "2027-02-20T09:00:00+07:00"}, "stage": "delivery",
            "mode": "achieve"}


def make(mod_r, store, agent, mid, path):
    p = mod_r.GoalDeps.__module__  # noqa: F841 - chỉ để chắc module đúng
    deps0 = mod_r.GoalDeps(engine_factory=lambda s, t: (None, {"blocked": "không gọi"}),
                           budget=mod_r.CallBudget(0), store=store)
    return asyncio.run(mod_r.form_goal(mod_r.message_ref("s-rb", mid), {
        "principal": store_principal(store), "brain_root": BRAIN, "session_id": "s-rb", "message_id": mid,
        "user_text": USER, "constraints": [], "budget_calls": 4, "proposal": proposal(path),
        "agent_key": agent["agent_key"], "agent_version": agent["config_version"]}, deps0))


def store_principal(store):
    return (OLD_S if isinstance(store, OLD_S.GoalStore) else RS).Principal("agent", "javis", BRAIN)


def deps(mod_r, store, eng, clock):
    return mod_r.GoalDeps(engine_factory=lambda s, t: (eng, {"provider": "fake", "model": "f", "text_only": True}),
                          budget=mod_r.CallBudget(0), clock=lambda: clock, store=store,
                          principal=store_principal(store), brain_root=BRAIN, evidence=Evidence(), notify=_nt)


# 1. Kho có từ 0.87 (A1): tạo mục tiêu bằng mã cũ, chưa chạy.
old = OLD_S.GoalStore(DB)
ag_old = old.agent_set_enabled(OLD_S.Principal("owner", "owner", BRAIN), RA.SLUG, True)
RA.enable(old, BRAIN)            # tạo file agent trong brain (đã bật ở trên, gọi lại không đổi gì)
g_old = make(OLD_R, old, ag_old, 1, "Inbox/rb-1.md")
check("0.87 tạo mục tiêu trên kho của chính nó (đối chứng)", bool(g_old.id))

# 2. Mở bằng A2: sao lưu, dựng lý do từ goal_events, chạy một nhịp có lượt việc.
a2 = RS.GoalStore(DB)
bak = DB.with_name(DB.name + ".pre-a2.bak")
check("mở bằng A2: có bản sao .pre-a2.bak", bak.is_file())
P = RS.Principal("agent", "javis", BRAIN)
check("mở bằng A2: mục tiêu của 0.87 có lý do created dựng từ goal_events",
      any(r["code"] == "created" for r in a2.reasons(P, g_old.id)))
eng = Engine()
asyncio.run(R.tick(a2, T0, lambda b: deps(R, a2, eng, T0), limit=5))
check("A2 chạy mục tiêu của 0.87: một lượt, có sổ thức", eng.queries == 1 and a2.wake_log(P, g_old.id))
ag = a2.agent(BRAIN, RA.SLUG)
g_a2 = make(R, a2, ag, 2, "Inbox/rb-2.md")
check("A2 tạo mục tiêu mới có lý do", any(r["code"] == "created" for r in a2.reasons(P, g_a2.id)))

# 3. Quay về: mã 0.87 thật chạy trên kho đã nâng.
old = OLD_S.GoalStore(DB)
eng_old = Engine()
try:
    asyncio.run(OLD_R.tick(old, T0 + 10, lambda b: deps(OLD_R, old, eng_old, T0 + 10), limit=5))
    g3 = make(OLD_R, old, ag_old, 3, "Inbox/rb-3.md")
    asyncio.run(OLD_R.advance(g3.id, {"kind": "start"}, deps(OLD_R, old, eng_old, T0 + 20)))
    err = ""
except Exception as e:  # noqa: BLE001
    err = f"{type(e).__name__}: {e}"
check("quay về 0.87: nhịp, tạo mục tiêu, lượt việc đều chạy trên kho đã nâng", not err, err)
check("quay về 0.87: mã cũ bỏ qua bảng A2 nhưng vẫn làm được việc", eng_old.queries >= 1)
with sqlite3.connect(str(DB)) as c:
    names = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
check("quay về 0.87: bảng A2 còn nguyên", set(RS.A2_TABLES) <= names)

# 4. Nâng lại lên A2: sự kiện mà lượt của 0.87 đã có thể thấy được chốt, không gọi model thừa.
a2 = RS.GoalStore(DB)
pend = [r for r in a2.reasons(P, g_a2.id) if r["code"] == "created"]
check("nâng lại: created của mục tiêu A2 đã được 0.87 làm thì đối soát là đã phục vụ",
      not pend and any(r["settled_by"].startswith("reconciled:") for r in a2.reasons(P, g_a2.id, state=None)))
eng2 = Engine()
asyncio.run(R.tick(a2, T0 + 30, lambda b: deps(R, a2, eng2, T0 + 30), limit=10))
check("nâng lại: nhịp đầu không gọi model cho việc 0.87 đã làm", eng2.queries == 0)
mt = bak.stat().st_mtime_ns
RS.GoalStore(DB)
check("nâng lại: không chép đè bản sao pre-a2", bak.stat().st_mtime_ns == mt)

if _fails:
    print(f"\n{len(_fails)} FAIL:", _fails)
    sys.exit(1)
print("\nOK")
