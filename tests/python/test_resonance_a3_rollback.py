"""Resonance A3: chu trình A3 -> mã 0.88.1 THẬT -> A3 trên cùng kho (thiết kế A3 mục 6.8, 7.3; ca A12, R6a tới R6d).

    python tests/run.py resonance_a3_rollback -v

Nạp `server/resonance.py`, `server/resonance_store.py` và `server/resonance_heartbeat.py` của commit phát hành 0.88.1
(`83bff6bc` trên main) qua `git show`. Mỗi ca:
1. A3 chạy tới khi phép thử thắng và đã áp dụng: lượt giữ làm sản phẩm `held`, lý do `method_followup` đang chờ;
2. mã 0.88.1 thật mở kho đó và chạy (nhịp tim, hay huỷ, sửa cách hiểu, quay lại cách cũ);
3. mở lại bằng A3: đối soát lượt giữ dựng lại đúng một lý do, hay trả lượt đúng một lần.
Mỗi ca kiểm lượt giữ và `gen`, action, `calls_used`, lý do đang chờ và số lượt engine. Engine giả, không model thật.

Máy không có lịch sử git của commit đó thì in SKIP; trên CI (biến CI) thì ĐỎ, vì CI phải lấy commit đó trước.
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

_STATE = tempfile.mkdtemp(prefix="javis-resonance-a3rb-")
os.environ["JAVIS_STATE_DIR"] = _STATE
os.environ.pop("JAVIS_RESONANCE_CALL_CEILING", None)

import resonance as R  # noqa: E402
import resonance_heartbeat as HB  # noqa: E402
import resonance_store as RS  # noqa: E402
import _resonance_agent as RA  # noqa: E402

OLD_SHA = "83bff6bcf5927c4f6ba83bff576a674f2269c0e5"
_fails = []


def check(name, cond, info=None):
    print(("ok   " if cond else "FAIL ") + name + ("" if cond or info is None else f"  ({info})"))
    if not cond:
        _fails.append(name)


def _show(path):
    return subprocess.check_output(["git", "-C", str(ROOT), "show", f"{OLD_SHA}:{path}"],
                                   stderr=subprocess.DEVNULL).decode("utf-8")


try:
    srcs = {n: _show(f"server/{n}.py") for n in ("resonance_heartbeat", "resonance", "resonance_store")}
except (subprocess.CalledProcessError, OSError):
    if os.environ.get("CI"):
        print(f"FAIL không đọc được mã của {OLD_SHA[:8]}: CI phải fetch commit này trước")
        sys.exit(1)
    print(f"SKIP máy này không có lịch sử git của {OLD_SHA[:8]}")
    sys.exit(0)

_dir = Path(tempfile.mkdtemp(prefix="old-0881-"))


def _load(name, src):
    f = _dir / f"{name}.py"
    f.write_text(src, encoding="utf-8", newline="\n")
    spec = importlib.util.spec_from_file_location(name, f)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


# Mã 0.88.1 nạp với tên riêng; trong lúc nạp, `import resonance` và `import resonance_heartbeat` phải thấy bản CŨ.
_saved = {k: sys.modules[k] for k in ("resonance", "resonance_heartbeat")}
try:
    OLD_HB = _load("resonance_heartbeat_0881", srcs["resonance_heartbeat"])
    sys.modules["resonance_heartbeat"] = OLD_HB
    OLD_R = _load("resonance_0881", srcs["resonance"])
    sys.modules["resonance"] = OLD_R
    OLD_S = _load("resonance_store_0881", srcs["resonance_store"])
finally:
    sys.modules.update(_saved)
check("nạp đúng mã 0.88.1: chính sách heartbeat.v1, không biết lớp FOLLOWUP",
      OLD_HB.POLICY_VERSION == "heartbeat.v1" and OLD_HB.classify("method_followup") == OLD_HB.CHECK
      and HB.classify("method_followup") == HB.FOLLOWUP)

BRAIN = str(Path(tempfile.mkdtemp(prefix="brain-a3rb-")).resolve())
(Path(BRAIN) / "Inbox").mkdir(parents=True)
P = RS.Principal("agent", "javis", BRAIN)
OWNER = RS.Principal("owner", "owner", BRAIN)
T0 = 1_800_000_000.0
DELIV = "Inbox/a3rb.md"
USER = "Viết giúp anh một ghi chú tổng hợp trong Inbox gồm báo cáo quý và máy lạnh, giữ tiêu đề Sample."
USER2 = "Làm lại ghi chú tổng hợp cho tuần sau, vẫn đủ báo cáo quý và máy lạnh, giữ tiêu đề Sample."
GOOD = "# Sample\n\nBáo cáo quý, máy lạnh.\n"
HALF = "# Sample\n\nBáo cáo quý thôi.\n"
MARK = R.METHODS["work.checklist.v1"]["addendum"][:40]
CRIT = [{"description": "Có báo cáo quý", "evaluator": "artifact_contract",
         "params": {"path": DELIV, "must_contain": ["báo cáo quý"]}},
        {"description": "Có máy lạnh", "evaluator": "artifact_contract",
         "params": {"path": DELIV, "must_contain": ["máy lạnh"]}}]


class Engine:
    def __init__(self):
        self.queries, self.max_wall_s = 0, None

    def is_available(self):
        return True

    async def query(self, prompt):
        self.queries += 1
        yield {"type": "final", "content": GOOD if MARK in prompt else HALF, "tokens_in": 1, "tokens_out": 1}


class Evidence:
    def __init__(self):
        self.items = {}

    def put(self, goal, action_id, text, metadata):
        eid = f"ev_{len(self.items) + 1}"
        self.items[eid] = {"text": text, "content_hash": hashlib.sha256(text.encode("utf-8")).hexdigest()}
        return eid

    def valid(self, evidence_id):
        return self.items.get(evidence_id)


async def _nt(goal, kind, text, card="", quiet=False):
    return True


_n = [0]


class Case:
    """Một kho riêng. `t` là đồng hồ giả dùng chung cho mã mới và mã cũ."""

    def __init__(self, name):
        _n[0] += 1
        self.path = Path(_STATE) / f"{name}-{_n[0]}.sqlite3"
        self.store = RS.GoalStore(self.path)
        self.agent = RA.enable(self.store, BRAIN)
        self.t = T0
        self.eng = Engine()
        self.ev = Evidence()

    def deps(self, mod_r, store, principal):
        return mod_r.GoalDeps(engine_factory=lambda s, t: (self.eng, {"provider": "fake", "model": "f",
                                                                       "text_only": True}),
                              budget=mod_r.CallBudget(0), clock=lambda: self.t, store=store, principal=principal,
                              brain_root=BRAIN, evidence=self.ev, notify=_nt)

    def tick(self, mod_r, store, principal):
        asyncio.run(mod_r.tick(store, self.t, lambda b: self.deps(mod_r, store, principal), limit=5))

    def run(self, mod_r, store, principal, gid, pred, steps=40):
        for _ in range(steps):
            if pred():
                return True
            dues = [w["due_at"] for w in store.wakes(principal, gid)]
            if not dues:
                return pred()
            self.t = max(self.t, min(dues))
            self.tick(mod_r, store, principal)
        return pred()

    def applied(self):
        """A3 tới khi phép thử thắng và áp dụng (mục tiêu có revision 2 khác thật để có tình huống giữ riêng)."""
        _n[0] += 1
        deps0 = R.GoalDeps(engine_factory=lambda s, t: (None, {"blocked": "không gọi"}), budget=R.CallBudget(0),
                           store=self.store)
        prop = {"understanding": "Ghi chú tổng hợp hai việc trong Inbox", "criteria": CRIT,
                "relevant_quote": "Viết giúp anh một ghi chú tổng hợp trong Inbox",
                "horizon": {"kind": "review", "at_iso": "2027-02-20T09:00:00+07:00"}, "stage": "delivery",
                "mode": "achieve"}
        g = asyncio.run(R.form_goal(R.message_ref("s-rb", 40_000 + _n[0]), {
            "principal": P, "brain_root": BRAIN, "session_id": "s-rb", "message_id": 40_000 + _n[0],
            "user_text": USER, "constraints": [], "budget_calls": 9, "proposal": prop,
            **RA.ctx(self.agent)}, deps0))
        (Path(BRAIN) / DELIV).unlink(missing_ok=True)
        fr = dict(self.store.get_revision(P, g.id, 1), understanding="Ghi chú tổng hợp cho tuần sau")
        iid = self.store.add_intent(P, "s-rb", 41_000 + _n[0], USER2, [], relation="replace")["id"]
        self.store.revise(P, g.id, 1, fr, "người dùng nói lại", intent_id=iid)
        self.gid = g.id
        self.run(R, self.store, P, g.id, lambda: bool(self.store.holds(P, g.id))
                 and self.store.holds(P, g.id)[-1]["status"] == "held"
                 and self.store.experiments(P, g.id)[0]["status"] == "finished")
        return g.id

    def hold(self):
        return self.store.holds(P, self.gid)[-1]

    def follow_pending(self, store=None):
        st = store or self.store
        return [r for r in st.reasons(P, self.gid) if r["code"] == "method_followup"]

    def calls(self):
        return self.store.get(P, self.gid).calls_used

    def lesson(self):
        return self.store.method_lessons(P, self.gid)[-1]


OP = OLD_S.Principal("agent", "javis", BRAIN)
OOWNER = OLD_S.Principal("owner", "owner", BRAIN)

# ═══ R6a: mã cũ chạy nhịp tim, chốt lý do lạ mà không gọi model và không đụng lượt giữ; A3 dựng lại ═══
c = Case("r6a")
c.applied()
h0 = c.hold()
check("R6a trước khi quay về: lượt giữ held gen 1, lý do chờ, calls 8, 7 lượt engine",
      h0["status"] == "held" and h0["gen"] == 1 and len(c.follow_pending()) == 1 and c.calls() == 8
      and c.eng.queries == 7, (h0["status"], h0["gen"], c.calls(), c.eng.queries))
old = OLD_S.GoalStore(c.path)
err = ""
try:
    c.tick(OLD_R, old, OP)
except Exception as e:  # noqa: BLE001
    err = f"{type(e).__name__}: {e}"
with sqlite3.connect(str(c.path)) as db:
    hst = db.execute("SELECT status, gen FROM call_holds").fetchone()
    pend = db.execute("SELECT COUNT(*) FROM wake_reasons WHERE goal_id=? AND code='method_followup' AND "
                      "state='pending'", (c.gid,)).fetchone()[0]
    calls = db.execute("SELECT calls_used FROM goals WHERE id=?", (c.gid,)).fetchone()[0]
check("R6a mã 0.88.1 chạy được trên kho A3, chốt lý do method_followup, 0 lượt engine, không đụng lượt giữ",
      not err and pend == 0 and c.eng.queries == 7 and tuple(hst) == ("held", 1) and calls == 8,
      (err, pend, c.eng.queries, hst, calls))
c.store = RS.GoalStore(c.path)
h1 = c.hold()
check("R6a mở lại bằng A3: dựng đúng một lý do mới (gen 2, source_ref mới), lượt giữ vẫn held",
      h1["status"] == "held" and h1["gen"] == 2 and len(c.follow_pending()) == 1
      and c.follow_pending()[0]["source_ref"] == f"hold:{h1['id']}:2")
c.run(R, c.store, P, c.gid, lambda: c.hold()["status"] == "used")
check("R6a A3 chạy lượt làm sản phẩm đúng một lần bằng lượt giữ: 8 lượt engine, calls 8",
      c.eng.queries == 8 and c.hold()["status"] == "used" and c.calls() == 8, (c.eng.queries, c.calls()))
c.store = RS.GoalStore(c.path)
c.t += 3 * 86400
c.tick(R, c.store, P)
check("R6a mở lại lần ba: không lý do mới, không lượt engine", not c.follow_pending() and c.eng.queries == 8)

# ═══ R6b: mã cũ huỷ mục tiêu ═══
c = Case("r6b")
c.applied()
old = OLD_S.GoalStore(c.path)
old.cancel(OOWNER, c.gid)
c.store = RS.GoalStore(c.path)
check("R6b mã cũ huỷ: mở bằng A3 trả lượt giữ một lần (calls 7), không lý do chờ, 0 lượt engine",
      c.hold()["status"] == "released" and c.calls() == 7 and not c.follow_pending() and c.eng.queries == 7)
c.store = RS.GoalStore(c.path)
check("R6b mở lại lần nữa: không trả lần hai", c.calls() == 7 and c.hold()["status"] == "released")

# ═══ R6c: mã cũ sửa cách hiểu ═══
c = Case("r6c")
c.applied()
old = OLD_S.GoalStore(c.path)
fr = dict(old.get_revision(OP, c.gid, 2), understanding="Cách hiểu thứ ba")
iid = old.add_intent(OP, "s-rb", 49_001, "Thêm ý thứ ba cho ghi chú, giữ tiêu đề Sample.", [], relation="replace")["id"]
old.revise(OP, c.gid, 2, fr, "mã cũ sửa cách hiểu", intent_id=iid)
c.store = RS.GoalStore(c.path)
check("R6c mã cũ sửa cách hiểu: A3 trả lượt giữ, bài học out_of_scope, cách làm mặc định, 0 lượt engine",
      c.hold()["status"] == "released" and c.lesson()["status"] == "out_of_scope"
      and R.effective_method(c.store.get(P, c.gid)) == "work.v1" and c.calls() == 7 and c.eng.queries == 7)

# ═══ R6d: mã cũ quay lại cách cũ ═══
c = Case("r6d")
c.applied()
old = OLD_S.GoalStore(c.path)
old.revert_method(OOWNER, c.gid)
c.store = RS.GoalStore(c.path)
check("R6d mã cũ quay lại cách cũ: A3 trả lượt giữ, bài học revoked/reverted_outside, 0 lượt engine",
      c.hold()["status"] == "released" and c.lesson()["status"] == "revoked"
      and c.lesson()["status_reason"] == "reverted_outside" and c.calls() == 7 and c.eng.queries == 7)

# ═══ A12: bảng A3 còn nguyên sau khi mã cũ chạy ═══
with sqlite3.connect(str(c.path)) as db:
    names = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
check("A12 bảng A3 còn nguyên sau khi mã 0.88.1 mở và ghi kho", set(RS.A3_TABLES) <= names)

if _fails:
    print(f"\n{len(_fails)} FAIL:", _fails)
    sys.exit(1)
print("\nOK")
