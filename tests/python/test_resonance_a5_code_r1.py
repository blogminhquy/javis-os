"""Resonance A5: hồi quy cho ba P2 của review mã vòng 1 (PR #616, head d22b6c66).

    python tests/run.py resonance_a5_code_r1 -v

- R1: lỗi trong pha chuẩn bị SAU khi giữ chỗ và TRƯỚC lời gọi engine được hoàn đúng hành động đó theo đường not-run
  (lượt tổng và vai, `charged`, lý do chờ) trong một giao dịch, kể cả khi lỗi đi cùng huỷ lặp, và khi chính lần hoàn
  cũng lỗi (đối soát sau khi hết khoá hoàn nhờ mốc `engine_at`). Đối chứng: lượt đã qua mốc gọi engine vẫn tính.
- R2: nút "Bật lại người review" trên thẻ gửi mã bền; thẻ cũ không bật được agent mới cùng slug (409).
- R3: mục tiêu duy trì và bước khám phá có đội cũng review bản đã đạt kiểm khách quan, rồi mới sang trạng thái của
  mode/stage; không review lặp cùng bộ ghim theo lịch định kỳ.

Kho SQLite thật, `form_goal`, `_gate`, `R.advance` và lịch thật; chỉ engine là giả (hai vai). Request của nút dựng bằng
`teamHtml` và `requestFor` thật (node) rồi gửi tới route FastAPI thật. Không gọi model thật.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import json
import os
import sqlite3
import subprocess
import tempfile
import threading
import time
from pathlib import Path

_STATE = Path(tempfile.mkdtemp(prefix="javis-res-a5r1-"))
os.environ["JAVIS_STATE_DIR"] = str(_STATE)
os.environ.pop("JAVIS_RESONANCE_CALL_CEILING", None)

import resonance as R  # noqa: E402
import resonance_heartbeat as HB  # noqa: E402
import resonance_store as RS  # noqa: E402
import _resonance_agent as RA  # noqa: E402
import _resonance_team as T  # noqa: E402

_fails = []


def check(name, cond, detail=""):
    print(("ok   " if cond else "FAIL ") + name + ("" if cond or not detail else f"  [{str(detail)[:500]}]"))
    if not cond:
        _fails.append(name)


ERR = {"error": "engine giả báo lỗi"}
GOOD2 = T.GOOD.replace("Xong.", "Xong, bản sửa theo góp ý.")
GOOD3 = T.GOOD.replace("Xong.", "Xong, bản sửa lần hai.")
RECHECK = R.REVIEW_ENGINE_RECHECK_S


def rows(t, g):
    return [(x["seq"], x["status"], x["verdict"], x["reason_code"], x["charged"]) for x in t.reviews(g)]


def codes(t, g):
    return sorted(r["code"] for r in t.store.reasons(t.owner, g.id))


def ready_for_review(name, **kw):
    t = T.Team(_STATE, name, **kw)
    g = t.create()
    t.wake(g)                               # vai làm: lượt 1 đạt kiểm; hẹn review
    return t, g


def one_shot(obj, name, exc=None, before=None):
    """Thay `obj.name` bằng hàm ném lỗi ĐÚNG MỘT lần (lần gọi đầu), rồi gọi bản gốc. Trả dict ghi đã chèn chưa."""
    orig = getattr(obj, name)
    st = {"hit": 0}

    def f(*a, **kw):
        if st["hit"] == 0:
            st["hit"] = 1
            if before is not None:
                before()
            raise exc or sqlite3.OperationalError(f"lỗi chèn một lần ở {name}")
        return orig(*a, **kw)
    setattr(obj, name, f)
    st["restore"] = lambda: setattr(obj, name, orig)
    return st


# ═════════════════════════ R1: lỗi pha chuẩn bị của lượt review ═════════════════════════
# R1a: lỗi thường ngay ở bước cuối pha chuẩn bị (mốc gọi engine), sau khi đã giữ chỗ.
t, g = ready_for_review("r1a")
f = one_shot(t.store, "mark_engine")
t.wake(g)
f["restore"]()
act = t.actions(g, "review")[0]
pend = t.store.reasons(t.owner, g.id)
check("R1a lỗi sau giữ chỗ, trước engine: engine review không chạy; lượt hoàn đúng vai (1, 0, 1)",
      f["hit"] == 1 and t.rev.queries == 0 and t.calls(g) == (1, 0, 1), (t.calls(g), t.rev.queries))
check("R1a hàng review cancelled, charged=0, lý do prepare_error; hành động cancelled/not_run (không running)",
      rows(t, g) == [(1, "cancelled", None, "prepare_error", 0)] and act["status"] == "cancelled"
      and act["receipt"].get("error_code") == "not_run" and act["receipt"].get("not_run_reason") == "prepare_error",
      (rows(t, g), act["status"], act["receipt"]))
check("R1a cùng giao dịch: review_due trở lại chờ, gác blocked/review_engine, hẹn review_recheck sau một khoảng",
      t.st(g) == {"run_state": "blocked", "block_reason": "review_engine"}
      and {r["code"] for r in pend} == {"review_due", "review_recheck"}
      and all(abs(float(r["due_at"]) - (t.clock() + RECHECK)) < 2 for r in pend if r["code"] == "review_recheck"),
      (t.st(g), [(r["code"], r["due_at"]) for r in pend]))
w = [x for x in t.store.wakes(t.owner, g.id) if x["kind"] == "work"]
check("R1a lịch vật lý chỉ còn hẹn kiểm lại (lý do vừa trả về không kéo lịch về quá khứ)",
      len(w) == 1 and float(w[0]["due_at"]) >= t.clock() + RECHECK - 2, w)
t.wake(g)
check("R1a thức trước hạn kiểm lại: không giữ chỗ lần nữa, không gọi engine", len(rows(t, g)) == 1 and t.rev.queries == 0)
t.reopen()
t.clock.t += 1200
t.wake(g)
check("R1a mở lại kho: không biến lượt chắc chắn chưa chạy thành `interrupted` có tính",
      rows(t, g) == [(1, "cancelled", None, "prepare_error", 0)] and t.calls(g) == (1, 0, 1), rows(t, g))
t.run(g, n=10, step=1)
check("R1a tới hạn kiểm lại: review chạy, pass, succeeded; một lần tính duy nhất (1, 1, 2)",
      t.g(g).status == "succeeded" and [r[4] for r in rows(t, g)] == [0, 1] and t.calls(g) == (1, 1, 2)
      and t.rev.queries == 1, (t.st(g), rows(t, g), t.calls(g)))

# R1b: lỗi ở điểm khác của pha chuẩn bị (đọc mô tả vai của reviewer).
t, g = ready_for_review("r1b")
f = one_shot(R, "_reviewer_role_text", OSError("đọc file agent lỗi"))
t.wake(g)
f["restore"]()
check("R1b lỗi khi đọc vai reviewer: cùng đường hoàn (1, 0, 1), hàng cancelled/prepare_error charged=0",
      f["hit"] == 1 and t.calls(g) == (1, 0, 1) and rows(t, g) == [(1, "cancelled", None, "prepare_error", 0)]
      and t.rev.queries == 0, (t.calls(g), rows(t, g)))

# R1c: lỗi đi cùng huỷ lặp. Pha chuẩn bị ở luồng phụ đang chạy (chờ trong mốc engine rồi ném lỗi) thì lần thức bị huỷ
# hai lần. Lease chỉ được nhả SAU khi pha đó đã xử lý xong (hoàn đã ghi).
t, g = ready_for_review("r1c")
entered, go = threading.Event(), threading.Event()


def _slow_fail():
    entered.set()
    go.wait(5)


f = one_shot(t.store, "mark_engine", before=_slow_fail)
seen_at_release = []
_orig_release = t.store.release_lease


def _release(p, gid, owner):
    seen_at_release.append(rows(t, g))
    return _orig_release(p, gid, owner)


t.store.release_lease = _release


async def _cancel_twice():
    task = asyncio.ensure_future(R.advance(g.id, {"kind": "wake"}, t.deps()))
    while not entered.is_set():
        await asyncio.sleep(0.005)
    task.cancel()
    await asyncio.sleep(0.01)
    task.cancel()
    await asyncio.sleep(0.01)
    go.set()
    try:
        await task
        return False
    except asyncio.CancelledError:
        return True


_cx = asyncio.run(_cancel_twice())
f["restore"]()
t.store.release_lease = _orig_release
lease = sqlite3.connect(str(_STATE / "r1c.sqlite3")).execute("SELECT lease_owner FROM goals WHERE id=?",
                                                              (g.id,)).fetchone()[0]
check("R1c lỗi kèm huỷ lặp: lời huỷ vẫn đi ra; lượt hoàn đúng một lần (1, 0, 1); hàng cancelled charged=0",
      _cx and t.calls(g) == (1, 0, 1) and rows(t, g) == [(1, "cancelled", None, "prepare_error", 0)]
      and t.rev.queries == 0, (_cx, t.calls(g), rows(t, g)))
check("R1c chỉ nhả lease SAU khi pha đang chạy đã hoàn xong; lease đã nhả",
      seen_at_release and seen_at_release[-1] == [(1, "cancelled", None, "prepare_error", 0)] and lease is None,
      (seen_at_release, lease))

# R1d: chính lần hoàn cũng lỗi. Hành động còn `running` nhưng chưa có mốc `engine_at`: đối soát sau khi hết khoá hoàn
# đúng (không `interrupted`, không tính lần), rồi review chạy bình thường.
t, g = ready_for_review("r1d")
f1 = one_shot(t.store, "mark_engine")
f2 = one_shot(t.store, "abort_action", sqlite3.OperationalError("hoàn cũng lỗi"))
t.wake(g)
f1["restore"]()
f2["restore"]()
act = t.actions(g, "review")[0]
check("R1d hoàn cũng lỗi: không gọi engine; hành động còn running và KHÔNG có mốc engine_at (dấu vết để đối soát)",
      f1["hit"] == 1 and f2["hit"] == 1 and t.rev.queries == 0 and act["status"] == "running"
      and act["intent"].get("engine_mark") == 1 and not act["intent"].get("engine_at"), act)
t.reopen()
t.clock.t += 3600
t.wake(g)
r1 = t.reviews(g)[0]
check("R1d đối soát sau khi hết khoá: hàng đầu cancelled/prepare_error charged=0 (không interrupted); lượt reviewer "
      "đúng bằng số lần engine chạy", (r1["status"], r1["reason_code"], r1["charged"]) == ("cancelled", "prepare_error", 0)
      and not any(x["reason_code"] == "interrupted" for x in t.reviews(g)) and t.calls(g)[1] == t.rev.queries,
      (rows(t, g), t.calls(g), t.rev.queries))
t.run(g, n=10, step=1)
check("R1d sau đó review chạy, pass, succeeded; (1, 1, 2)", t.g(g).status == "succeeded" and t.calls(g) == (1, 1, 2)
      and t.rev.queries == 1, (t.st(g), rows(t, g)))

# R1e đối chứng: lượt ĐÃ QUA mốc gọi engine rồi tiến trình chết (engine có thể đã chạy) vẫn tính lượt và tính lần.
t, g = ready_for_review("r1e")
deps = t.deps()
ctx = R._advance_prepare(g.id, "wake", {}, deps, t.clock())
pre = R._review_pre(ctx.goal, ctx, deps, t.clock())
act = t.store.get_action(t.owner, pre[0]["id"])
check("R1e pha chuẩn bị xong: mốc engine_at đã ghi, mục tiêu running", bool(act["intent"].get("engine_at"))
      and t.st(g)["run_state"] == "running", (act["intent"], t.st(g)))
t.reopen()
t.clock.t += 3600
t.wake(g)
check("R1e chết sau mốc gọi engine: đối soát ghi failed/interrupted charged=1; lượt reviewer vẫn tính",
      rows(t, g)[0] == (1, "failed", "unknown", "interrupted", 1) and t.calls(g)[1] >= 1, (rows(t, g), t.calls(g)))

# R1f: hành động CŨ (trước 0.109.0, không mang giao thức mốc) còn dở: luật đối soát cũ giữ nguyên (coi như có thể đã chạy).
t = T.Team(_STATE, "r1f", pair=False)
g = t.create()
held = R._agent_intent(t.store.get(t.owner, g.id), t.deps())
old = t.store.begin_action(t.owner, g.id, g.revision, "work", lease_until=t.clock() + 5, now=t.clock(),
                           intent={"prompt_kind": "work", **held})
with sqlite3.connect(str(_STATE / "r1f.sqlite3")) as c:     # mô phỏng hàng của bản cũ: không có cờ engine_mark
    it = json.loads(c.execute("SELECT intent_json FROM actions WHERE id=?", (old["id"],)).fetchone()[0])
    it.pop("engine_mark", None)
    c.execute("UPDATE actions SET intent_json=? WHERE id=?", (json.dumps(it), old["id"]))
t.reopen()
t.clock.t += 3600
t.wake(g)
rec = t.store.get_action(t.owner, old["id"])
check("R1f hành động cũ không có mốc: đối soát vẫn ghi interrupted (không suy mọi lượt gián đoạn là chưa gọi)",
      rec["status"] == "failed" and rec["receipt"].get("error_code") == "interrupted", rec)

# ═════════════════════════ R1: lỗi pha chuẩn bị của lượt VIỆC (vai làm) ═════════════════════════
t = T.Team(_STATE, "r1w")
g = t.create()
f = one_shot(t.store, "mark_engine")
t.wake(g)
f["restore"]()
act = t.actions(g, "work")[0]
check("R1w lỗi sau giữ chỗ lượt việc: engine làm không chạy; lượt maker và tổng được hoàn (0, 0, 0)",
      f["hit"] == 1 and t.work.queries == 0 and t.calls(g) == (0, 0, 0)
      and act["status"] == "cancelled" and act["receipt"].get("not_run_reason") == "prepare_error",
      (t.calls(g), act["status"], act["receipt"]))
check("R1w lý do bước đầu trở lại chờ; gác blocked/prepare_error kèm hẹn prepare_recheck",
      t.st(g) == {"run_state": "blocked", "block_reason": "prepare_error"} and "prepare_recheck" in codes(t, g)
      and "created" in codes(t, g), (t.st(g), codes(t, g)))
t.wake(g)
check("R1w thức trước hạn: không giữ chỗ lại", len(t.actions(g, "work")) == 1 and t.work.queries == 0)
t.run(g, n=12, step=1)
check("R1w tới hạn kiểm lại: làm, review, succeeded; (1, 1, 2)", t.g(g).status == "succeeded"
      and t.calls(g) == (1, 1, 2) and t.work.queries == 1, (t.st(g), t.calls(g)))

t = T.Team(_STATE, "r1wn")
g = t.create()
f = one_shot(t.store, "mark_engine")
t.wake(g)
f["restore"]()
t.store.add_reason_event(t.owner, g.id, "feedback", "fb:r1wn")
t.wake(g)
check("R1w tin mới của người dùng trong lúc chờ kiểm lại: vẫn mở lượt làm ngay (không bị gác)",
      t.work.queries == 1 and t.calls(g)[0] == 1, (t.st(g), t.calls(g), t.work.queries))

t = T.Team(_STATE, "r1w2")
g = t.create()
f1 = one_shot(t.store, "mark_engine")
f2 = one_shot(t.store, "abort_action", sqlite3.OperationalError("hoàn cũng lỗi"))
t.wake(g)
f1["restore"]()
f2["restore"]()
check("R1w2 lượt việc, hoàn cũng lỗi: hành động running chưa có mốc; lượt đang giữ (1, 0, 1)",
      t.actions(g, "work")[0]["status"] == "running" and t.calls(g) == (1, 0, 1) and t.work.queries == 0)
t.reopen()
t.clock.t += 3600
t.wake(g)
first = t.actions(g, "work")[0]
check("R1w2 đối soát: lượt việc chưa tới mốc được hoàn (not_run/prepare_error), không ghi lượt lỗi interrupted",
      first["status"] == "cancelled" and first["receipt"].get("not_run_reason") == "prepare_error"
      and not [x for x in t.store.wake_log(t.owner, g.id) if x.get("error_code") == "interrupted"], first)
t.run(g, n=12, step=1)
check("R1w2 sau đó làm, review, succeeded; lượt maker đúng bằng số lần engine làm chạy",
      t.g(g).status == "succeeded" and t.calls(g)[0] == t.work.queries == 1 and t.calls(g) == (1, 1, 2),
      (t.st(g), t.calls(g), t.work.queries))

# ═════════════════════════ R2: nút Bật lại người review ghim mã bền ═════════════════════════
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
import resonance_api as API  # noqa: E402

_JS = """const r=require(process.argv[1]), g=JSON.parse(process.argv[2]);
const h=r.teamHtml(g), m=h.match(/<button[^>]*data-act="reviewer_enable"[^>]*>/);
if(!m){console.log("null");process.exit(0);}
const d={}; for(const x of m[0].matchAll(/data-([a-z-]+)="([^"]*)"/g)) d[x[1]]=x[2];
console.log(JSON.stringify(r.requestFor('reviewer_enable',g,'',d,'t')));"""


def ui_request(t, g):
    """Request mà nút trên thẻ ĐANG HIỆN sẽ gửi: goal view thật, teamHtml và requestFor thật."""
    card = R.goal_view(t.store, t.owner, g.id, t.brain)
    out = subprocess.check_output(["node", "-e", _JS, str(Path(ROOT) / "dashboard" / "chat-resonance.js"),
                                   json.dumps(card, ensure_ascii=False)], text=True, encoding="utf-8")
    return json.loads(out)


def client(t):
    app = FastAPI()
    deps = API.ResonanceApiDeps(store=lambda: t.store, brain_key=lambda b: t.brain,
                                engine_factory=lambda s, tag: (None, {}), session_store=lambda: None,
                                agent_file=lambda root, slug: Path(root) / "agents" / f"{slug}.md")
    API.register(app, deps)
    API.register_agents(app, deps)
    API.register_a5(app, deps)
    return TestClient(app)


def team_ledger(t, g):
    tm = t.team(g)
    return (json.dumps(tm["calls"], sort_keys=True), t.store.review_rounds(t.owner, g.id, t.g(g).revision),
            t.g(g).calls_used, tm["reviewer_agent_key"])


# Tên kho "resonance": route đọc kho mặc định của JAVIS_STATE_DIR.
t, g = ready_for_review("resonance")
RA.disable(t.store, t.brain, T.REVIEWER)
t.wake(g)
old_key = t.reviewer["agent_key"]
req = ui_request(t, g)
check("R2 thẻ cũ: nút gửi mã bền của reviewer đang hiện, tới route của thẻ",
      req and req["url"] == f"/goals/{g.id}/reviewer/enable" and req["body"].get("agent_key") == old_key, req)
t.store.agent_retire(t.owner, T.REVIEWER)
new = RA.enable(t.store, t.brain, T.REVIEWER)
RA.disable(t.store, t.brain, T.REVIEWER)
before = team_ledger(t, g)
cl = client(t)
r = cl.post(req["url"], json=req["body"])
check("R2 thẻ cũ, agent mới cùng slug: 409, agent mới KHÔNG được bật, mục tiêu vẫn ghim mã cũ; trả trạng thái mới",
      r.status_code == 409 and not t.ag(T.REVIEWER)["enabled"] and new["agent_key"] != old_key
      and t.team(g)["reviewer_agent_key"] == old_key and (r.json().get("goal") or {}).get("goal_id") == g.id,
      (r.status_code, r.json().get("error"), t.ag(T.REVIEWER)))
check("R2 409 không đổi sổ vai, vòng hay tổng lượt", team_ledger(t, g) == before, (before, team_ledger(t, g)))
r = cl.post("/resonance/agents/toggle", json={"slug": T.REVIEWER, "enabled": True})
check("R2 nút bật thông thường ở trang trợ lý giữ hành vi cũ: bật agent hiện tại của slug",
      r.status_code == 200 and t.ag(T.REVIEWER)["enabled"] and t.ag(T.REVIEWER)["agent_key"] == new["agent_key"],
      (r.status_code, r.json()))

# Ca hợp lệ qua request thật của thẻ tới route thật (cùng kho "resonance", brain khác).
t, g = ready_for_review("resonance")
RA.disable(t.store, t.brain, T.REVIEWER)
t.wake(g)
key = t.reviewer["agent_key"]
req = ui_request(t, g)
before = team_ledger(t, g)
r = client(t).post(req["url"], json=req["body"])
check("R2 qua route: cùng mã A thì 200, bật lại đúng mã đó, không đổi lượt, vòng hay ghim; trả goal view mới",
      r.status_code == 200 and r.json()["agent"]["agent_key"] == key and t.ag(T.REVIEWER)["agent_key"] == key
      and t.ag(T.REVIEWER)["enabled"] and team_ledger(t, g) == before
      and (r.json().get("goal") or {}).get("goal_id") == g.id, (r.status_code, r.json(), before, team_ledger(t, g)))
r = client(t).post(req["url"], json=req["body"])
check("R2 bấm lại lần hai: 200, không tăng version lần nữa", r.status_code == 200
      and r.json()["agent"]["config_version"] == t.ag(T.REVIEWER)["config_version"])

t, g = ready_for_review("r2ok")
RA.disable(t.store, t.brain, T.REVIEWER)
t.wake(g)
key = t.reviewer["agent_key"]
req = ui_request(t, g)
before = team_ledger(t, g)
st0 = t.st(g)
a = t.store.team_reviewer_enable(t.owner, g.id, req["body"]["agent_key"])
check("R2 cùng mã A: host bật lại đúng mã đó (cùng agent_key), không đổi lượt, vòng hay ghim",
      st0["block_reason"] == "reviewer_off" and a["agent_key"] == key and a["enabled"]
      and team_ledger(t, g) == before, (st0, a, before, team_ledger(t, g)))
t.store.wake_agent_goals(t.brain, key)
t.run(g, n=10, step=1)
check("R2 sau khi bật lại: review chạy, pass, succeeded; (1, 1, 2)", t.g(g).status == "succeeded"
      and t.calls(g) == (1, 1, 2), (t.st(g), t.calls(g)))

t, g = ready_for_review("r2d")
RA.disable(t.store, t.brain, T.REVIEWER)
t.wake(g)
req = ui_request(t, g)
t.store.team_detach(t.owner, g.id)
try:
    t.store.team_reviewer_enable(t.owner, g.id, req["body"]["agent_key"])
    _ok = False
except RS.ConflictError:
    _ok = True
check("R2 đội đã bỏ: nút từ thẻ cũ bị từ chối, không bật ai", _ok and not t.ag(T.REVIEWER)["enabled"])
try:
    t.store.team_reviewer_enable(t.owner, g.id, t.maker["agent_key"])
    _ok = False
except RS.ConflictError:
    _ok = True
check("R2 mã không phải reviewer của đội (ví dụ mã người làm): bị từ chối", _ok)
try:
    t.store.team_reviewer_enable(RS.Principal("agent", t.maker["agent_key"], t.brain), g.id, req["body"]["agent_key"])
    _ok = False
except Exception:  # noqa: BLE001
    _ok = True
check("R2 chỉ chủ dự án gọi được (agent không tự bật người review)", _ok)


# ═════════════════════════ R3: duy trì và khám phá cũng review bản đã đạt ═════════════════════════
def with_mode(t, mode, stage):
    orig = t.proposal

    def proposal(human=False, path=T.DELIV):
        return dict(orig(human, path), mode=mode, stage=stage)
    t.proposal = proposal
    return t


def outbox(t, g, kind):
    return [x for x in t.store.outbox_pending(500) if x["goal_id"] == g.id and x["kind"] == kind]


t = with_mode(T.Team(_STATE, "r3m"), "maintain", "delivery")
g = t.create()
t.wake(g)
check("R3 duy trì: sau lượt làm đạt kiểm, CHƯA báo cập nhật, chờ review (review_pending)",
      t.st(g)["block_reason"] == "review_pending" and not outbox(t, g, "goal.maintained"), (t.st(g),))
t.run(g, n=10, step=1)
check("R3 duy trì: review pass; mục tiêu vẫn active/healthy; (1, 1, 2); báo cập nhật đúng một lần sau pass",
      t.g(g).status == "active" and t.st(g) == {"run_state": "waiting", "block_reason": "healthy"}
      and t.calls(g) == (1, 1, 2) and rows(t, g) == [(1, "done", "pass", "", 1)] and len(outbox(t, g, "goal.maintained")) == 1,
      (t.g(g).status, t.st(g), t.calls(g), rows(t, g)))
for _ in range(4):
    t.run(g, n=6, step=1)
    t.clock.t += 7 * 86400
t.run(g, n=6, step=1)
check("R3 duy trì: nhiều nhịp kiểm định kỳ trên cùng bộ ghim không review lại; không thêm lượt model",
      t.rev.queries == 1 and len(rows(t, g)) == 1 and t.calls(g) == (1, 1, 2) and t.g(g).status == "active",
      (t.rev.queries, rows(t, g), t.calls(g), t.st(g)))
t.target().write_text(T.GOOD + "\nSửa tay.\n", encoding="utf-8", newline="\n")
t.clock.t += 7 * 86400
t.run(g, n=6, step=1)
check("R3 duy trì, file sửa tay sau pass: chờ source_drift, không gọi model, không ghi đè (phương án A)",
      t.st(g)["block_reason"] == "source_drift" and t.calls(g) == (1, 1, 2)
      and t.target().read_text(encoding="utf-8").endswith("Sửa tay.\n"), (t.st(g), t.calls(g)))

t = with_mode(T.Team(_STATE, "r3d"), "achieve", "discovery")
g = t.create()
t.run(g, n=10, step=1)
check("R3 khám phá: review pass rồi mới waiting/discovery_done; mục tiêu vẫn active; (1, 1, 2); báo xong bước khám phá",
      t.g(g).status == "active" and t.st(g) == {"run_state": "waiting", "block_reason": "discovery_done"}
      and t.calls(g) == (1, 1, 2) and rows(t, g) == [(1, "done", "pass", "", 1)]
      and len(outbox(t, g, "goal.discovery_done")) == 1, (t.st(g), t.calls(g), rows(t, g)))

t = with_mode(T.Team(_STATE, "r3dc"), "achieve", "discovery")
t.rev.script = [T.CHANGES, T.PASS]
t.work.script = [T.GOOD, GOOD2]
g = t.create()
t.run(g, n=12, step=1)
check("R3 khám phá cần sửa: vòng 1 sửa theo góp ý, pass, discovery_done; (2, 2, 4)",
      t.st(g)["block_reason"] == "discovery_done" and t.calls(g) == (2, 2, 4)
      and [r[2] for r in rows(t, g)] == ["needs_changes", "pass"] and "góp ý" in t.work.prompts[1].lower(),
      (t.st(g), t.calls(g), rows(t, g)))

t = with_mode(T.Team(_STATE, "r3mc"), "maintain", "delivery")
t.rev.script = [T.CHANGES, T.CHANGES, T.CHANGES]
t.work.script = [T.GOOD, GOOD2, GOOD3]
g = t.create()
t.run(g, n=16, step=1)
check("R3 duy trì cần sửa ba lần: hai vòng sửa rồi blocked/review_rounds; (3, 3, 6); không báo cập nhật",
      t.st(g) == {"run_state": "blocked", "block_reason": "review_rounds"} and t.calls(g) == (3, 3, 6)
      and not outbox(t, g, "goal.maintained"), (t.st(g), t.calls(g), rows(t, g)))

t = with_mode(T.Team(_STATE, "r3mu"), "maintain", "delivery")
t.rev.script = [ERR]
g = t.create()
t.run(g, n=20, step=1)
check("R3 duy trì, review không đọc được: thử lại theo luật rồi blocked/review_unknown; lượt reviewer trong phần vai",
      t.st(g)["block_reason"] == "review_unknown" and 1 <= t.calls(g)[1] <= 4 and t.g(g).calls_used <= 8
      and sum(r[4] for r in rows(t, g)) <= HB.REVIEW_MAX_CHARGED, (t.st(g), t.calls(g), rows(t, g)))

t = with_mode(T.Team(_STATE, "r3mo"), "maintain", "delivery")
g = t.create()
RA.disable(t.store, t.brain, T.REVIEWER)
t.run(g, n=10, step=1)
check("R3 duy trì, người review tắt: blocked/reviewer_off, 0 lượt model, không báo cập nhật",
      t.st(g)["block_reason"] == "reviewer_off" and t.calls(g) == (0, 0, 0) and not outbox(t, g, "goal.maintained"),
      (t.st(g), t.calls(g)))

t = with_mode(T.Team(_STATE, "r3a"), "achieve", "delivery")
g = t.create()
t.run(g, n=10, step=1)
check("R3 đối chứng achieve/delivery giữ nguyên: succeeded; (1, 1, 2)", t.g(g).status == "succeeded"
      and t.calls(g) == (1, 1, 2))

print(f"\n{len(_fails)} FAIL: {_fails}" if _fails else "\nOK")
raise SystemExit(1 if _fails else 0)
