"""T4 (0.170.0): kiểm vận hành xuyên T1-T3 qua host thật (thiết kế 2026-10-15 mục 11, GOAL mục 10).

    python tests/run.py team_t4_ops -v

main.app qua TestClient, engine GIẢ cho lượt nhóm, lô phán xử và lượt quét (chốt chặn engine thật trong _t4_host). Các ca:
nhiều tab, mất kết nối rồi nối lại, khởi động lại (mở lại kho), huỷ, thử lại, thành viên rời nhóm, đổi trưởng nhóm, tắt/bật
Auto (Cộng hưởng), thu hồi Toàn quyền, lỗi kho khi chiếu tác động, lệch đồng hồ, nhóm bị chặn hay agent ngủ không chiếm suất
của nhóm có việc. Ca nào đã có test chuyên sâu ở T1-T3 thì ở đây chỉ kiểm lại MỘT lần qua đường host đầy đủ sau khi ghép.
"""
from _t4_host import (BR, Q, api, c, check, dispatch, drain, fakes, finish, main, new_team, send, sent,  # noqa: E402
                      toggle_auto)
import asyncio  # noqa: E402
import sqlite3  # noqa: E402
import time  # noqa: E402
from pathlib import Path  # noqa: E402

import agent_pulse as AP  # noqa: E402
import config as cfgmod  # noqa: E402
import sessions as SS  # noqa: E402
import team_store as TS  # noqa: E402

STATE = Path(cfgmod.STATE_DIR)
toggle_auto("minh", True)
toggle_auto("hoa", True)
T, K = new_team("Vận hành")
TID, SID = T["team_id"], T["session_id"]

# ═════ nhiều tab ═════
send(TID, "Minh viết giúp mô tả sản phẩm", mentions=[K["minh"]], cm="tab-1")
msgs = c.get(f"/teams/{TID}/messages{Q}").json()["messages"]
ans = [m for m in msgs if m["author_kind"] == "agent" and m["author_ref"] == K["minh"]]
check("lượt trả lời bằng engine giả đã lưu", len(ans) == 1 and fakes.team_calls >= 1, msgs)
mid = ans[-1]["id"]
before = len(sent)
r1 = c.post(f"/teams/{TID}/messages/{mid}/reaction{Q}", json={"value": "love", "nonce": "tab-a-1"})
r2 = c.post(f"/teams/{TID}/messages/{mid}/reaction{Q}", json={"value": "love", "nonce": "tab-a-1"})
check("tab A thả, gửi lại cùng nonce (tab rớt mạng thử lại): cùng trạng thái, 200", r1.status_code == r2.status_code == 200
      and r1.json()["reaction"]["revision"] == r2.json()["reaction"]["revision"], (r1.text, r2.text))
with sqlite3.connect(STATE / "team.sqlite3") as db:
    n_log = db.execute("SELECT COUNT(*) FROM team_reaction_log WHERE message_id=?", (mid,)).fetchone()[0]
check("gửi lại cùng nonce không thêm dòng nhật ký", n_log == 1, n_log)
drain()
pk = [e for e in sent[before:] if e.get("type") == "team_message" and (e.get("message") or {}).get("id") == mid]
check("mọi tab nhận gói team_message mang reaction mới (phát cho mọi tab)", pk and pk[-1]["message"]["reaction"]["value"]
      == "love", sent[before:])
v1 = c.get(f"/teams/{TID}/messages{Q}").json()["messages"]
v2 = c.get(f"/teams/{TID}/messages{Q}").json()["messages"]
check("hai tab tải lại thấy cùng trạng thái", [m.get("reaction") for m in v1] == [m.get("reaction") for m in v2])
# Hai tab thật đăng ký vào ChatRuntime (đường fan-out thật, không phải gói bắt ở chỗ publish) và một tab có socket đã chết.
fake_publish = main._CHAT_RUNTIME.publish
del main._CHAT_RUNTIME.publish   # dùng lại phương thức thật của lớp
tab_a, tab_b = [], []


async def writer_a(ev):
    tab_a.append(ev)


async def writer_b(ev):
    tab_b.append(ev)


async def writer_dead(ev):
    raise ConnectionResetError("tab đã đóng")


main._CHAT_RUNTIME.add_client("tab-a", writer_a)
main._CHAT_RUNTIME.add_client("tab-b", writer_b)
main._CHAT_RUNTIME.add_client("tab-dead", writer_dead)
try:
    r3 = c.post(f"/teams/{TID}/messages/{mid}/reaction{Q}", json={"value": "wow", "nonce": "tab-b-1"})
    drain()
finally:
    for cid in ("tab-a", "tab-b", "tab-dead"):
        main._CHAT_RUNTIME.remove_client(cid)
    main._CHAT_RUNTIME.publish = fake_publish


def team_msg_for(tab):
    return [e for e in tab if e.get("type") == "team_message" and (e.get("message") or {}).get("id") == mid]


ga, gb = team_msg_for(tab_a), team_msg_for(tab_b)
check("tab B đổi sang wow: tab A và tab B đều NHẬN gói team_message mang wow (dù một tab khác đã chết)",
      r3.status_code == 200 and ga and gb and ga[-1]["message"]["reaction"]["value"] == "wow"
      and gb[-1]["message"]["reaction"]["value"] == "wow", (len(tab_a), len(tab_b)))
check("hai tab nhận cùng nội dung gói (cùng content_sha, cùng revision)",
      ga and gb and ga[-1]["message"].get("content_sha") == gb[-1]["message"].get("content_sha")
      and ga[-1]["message"]["reaction"]["revision"] == gb[-1]["message"]["reaction"]["revision"])
check("tab A tải lại thấy wow", next(
    m for m in c.get(f"/teams/{TID}/messages{Q}").json()["messages"] if m["id"] == mid)["reaction"]["value"] == "wow")

# ═════ mất kết nối rồi nối lại ═════


async def broken_publish(ev):
    raise ConnectionError("socket đã đóng")

main._CHAT_RUNTIME.publish = broken_publish
r = c.post(f"/teams/{TID}/messages/{mid}/reaction{Q}", json={"value": "like", "reasons": ["too_long"], "nonce": "dc-1"})
errs = drain(tolerate=True)
check("gói WS gửi lỗi (mất kết nối): thao tác vẫn 200, lỗi chỉ ở việc gửi gói", r.status_code == 200 and errs
      and all(isinstance(e, ConnectionError) for e in errs), (r.text, errs))


async def ok_publish(ev):
    sent.append(ev)

main._CHAT_RUNTIME.publish = ok_publish
got = next(m for m in c.get(f"/teams/{TID}/messages{Q}").json()["messages"] if m["id"] == mid)
check("nối lại và tải lại trang (team_resync): thấy trạng thái đã lưu trong lúc mất kết nối",
      got["reaction"]["value"] == "like" and got["reaction"]["reasons"] == ["too_long"], got.get("reaction"))
rep = [m for m in c.get(f"/teams/{TID}/messages{Q}").json()["messages"] if m.get("replies")]
check("kết cục lượt trả lời đi kèm tin của chủ (tải lại vẫn thấy)", rep and rep[0]["replies"][0]["status"] == "done", rep)

# ═════ khởi động lại: mở lại kho ═════
tm2 = TS.TeamStore(STATE / "team.sqlite3")
check("khởi động lại: reaction còn nguyên sau khi mở lại kho nhóm",
      (tm2.reaction_of(SID, mid) or {}).get("value") == "like")
ps = main._pulse_store()
AP.ensure(ps)
AP.wake(ps, K["minh"], f"team:{TID}", "direct")
import resonance_store as RS  # noqa: E402
gs2 = RS.GoalStore(STATE / "resonance.sqlite3")
AP.ensure(gs2, force=True)
v = AP.view(gs2, K["minh"])
check("khởi động lại: trạng thái nhịp theo ngữ cảnh còn sau khi mở lại kho", any(
    x.get("context_ref") == f"team:{TID}" for x in (v.get("contexts") or [])), v)

# Khởi động lại thật: bộ chạy MỚI (như tiến trình mới) trên một việc đang chạy chưa tới engine và một việc có lượt đã
# tới mốc engine. Việc thứ nhất chạy tiếp tới xong; việc thứ hai bị chặn "interrupted", lượt tính một lần.
import team_runner as TRM  # noqa: E402
tsx = main.tasks_feature.store
RT, RK = new_team("Khởi động lại", members=("lan", "minh"), leader="lan")
j_resume = send(RT["team_id"], "Việc dở trước khi tắt", mentions=[RK["minh"]], as_job=True, cm="rs-1", run=False)
tsx.claim_team_next(RT["team_id"], "tien-trinh-cu")
# Tiến trình cũ đã nhận việc và tạo bước đầu (như _claim_batch) rồi chết trước khi lượt tới engine.
api.teams().add_step(j_resume["task_id"], RT["team_id"], "work", RK["minh"], 1, "làm phần dở", [])
R2, RK2 = new_team("Khởi động lại 2", members=("lan", "minh"), leader="lan")
j_int = send(R2["team_id"], "Việc đang ở engine khi tắt", mentions=[RK2["minh"]], as_job=True, cm="rs-2", run=False)
tsx.claim_team_next(R2["team_id"], "tien-trinh-cu")
st_int = api.teams().add_step(j_int["task_id"], R2["team_id"], "work", RK2["minh"], 1, "làm", [])
turn_int = api.teams().reserve_turn(R2["team_id"], j_int["task_id"], st_int["step_id"], RK2["minh"], "work")
api.teams().mark_engine(turn_int, "fake", "fake-model")
old_runner = api.runner()
api._runner = None                       # tiến trình mới: bộ chạy dựng lại từ deps
new_runner = api.runner()
check("khởi động lại: bộ chạy mới là đối tượng khác, pool trống", new_runner is not old_runner and not new_runner._pool)
rep = new_runner.recover()
check("phục hồi: việc chưa tới engine được nhận lại để chạy tiếp", j_resume["task_id"] in rep["resumed"], rep)
# 16/11/2026 (owner: "sau mỗi lần cập nhật thì các team tự khởi động lại để tiếp tục công việc"): such a job is no longer
# blocked for the owner to press Continue; it carries on with a new step (tests/python/test_team_resume_after_restart.py).
check("phục hồi: việc có lượt đã tới engine tự làm tiếp bằng một bước mới", j_int["task_id"] in rep["resumed"]
      and tsx.get_task(j_int["task_id"])["status"] == "team_running", (rep, tsx.get_task(j_int["task_id"])["status"]))
check("phục hồi: lượt đã tới engine chốt interrupted (tính một lần, không hoàn)",
      next(t for t in api.teams().turns(R2["team_id"]) if t["turn_id"] == turn_int)["status"] == "interrupted")
calls_rs = fakes.team_calls


async def _resume():
    new_runner._bind_loop()
    await new_runner.resume_jobs(rep["resumed"])
    await new_runner.wait_jobs()

asyncio.run(_resume())
drain()
check("bộ chạy mới chạy tiếp việc dở tới xong bằng engine giả", tsx.get_task(j_resume["task_id"])["status"] == "done"
      and fakes.team_calls > calls_rs, ({k: tsx.get_task(j_resume["task_id"])[k] for k in
                                         ("status", "block_kind", "block_reason")}, calls_rs, fakes.team_calls))
check("khởi động lại không để khoá bận nào treo", api.teams().busy_of(RK2["minh"]) is None
      and api.teams().busy_of(RK["minh"]) is None)

# ═════ huỷ ═════
job = send(TID, "Việc dài: lập báo cáo quý", mentions=[K["hoa"]], as_job=True, cm="job-cancel", run=False)
calls0 = fakes.team_calls
r = c.post(f"/teams/{TID}/tasks/{job['task_id']}/cancel{Q}", json={})
check("huỷ việc đang chờ: 200, việc thành cancelled", r.status_code == 200
      and main.tasks_feature.store.get_task(job["task_id"])["status"] == "cancelled", r.text)
dispatch()
check("việc đã huỷ không mở lượt model nào", fakes.team_calls == calls0, (calls0, fakes.team_calls))
r = c.post(f"/teams/{TID}/tasks/{job['task_id']}/cancel{Q}", json={})
check("huỷ lặp lại không làm hỏng gì (không 500)", r.status_code < 500, r.status_code)

# ═════ thử lại ═════
fakes.team_error = RuntimeError("engine giả lỗi")
sub = send(TID, "Hoa trả lời giúp câu này", mentions=[K["hoa"]], cm="retry-1")
fakes.team_error = None
rows = api.teams().replies_for(TID, [sub["message_id"]]).get(sub["message_id"]) or []
check("lượt lỗi ghi kết cục error", rows and rows[0]["status"] == "error", rows)
calls0 = fakes.team_calls
r = c.post(f"/teams/{TID}/messages/{sub['message_id']}/replies/{K['hoa']}/retry{Q}", json={})
drain()
rows = api.teams().replies_for(TID, [sub["message_id"]]).get(sub["message_id"]) or []
check("Thử lại: đúng một lượt mới, kết cục done", r.status_code == 200 and rows and rows[0]["status"] == "done"
      and fakes.team_calls == calls0 + 1, (r.text, rows, calls0, fakes.team_calls))

# ═════ thành viên rời nhóm ═════
r = c.delete(f"/teams/{TID}/members/{K['hoa']}{Q}")
check("bỏ thành viên: 200", r.status_code == 200, r.text)
JS = main._agent_judge().store(True)
hoa0 = len(JS.decisions(K["hoa"], f"team:{TID}", 500))
minh0 = len(JS.decisions(K["minh"], f"team:{TID}", 500))
send(TID, "Cả nhóm ơi, ai xem giúp kế hoạch nhập hàng được không?", cm="after-leave")
check("người đã rời không còn được phán xử cho tin mới (thành viên còn lại thì có)",
      len(JS.decisions(K["hoa"], f"team:{TID}", 500)) == hoa0
      and len(JS.decisions(K["minh"], f"team:{TID}", 500)) > minh0,
      (hoa0, len(JS.decisions(K["hoa"], f"team:{TID}", 500)), minh0))

# ═════ đổi trưởng nhóm ═════
r = c.post(f"/teams/{TID}/leader{Q}", json={"agent_key": K["minh"]})
check("đổi trưởng nhóm sang Minh: 200", r.status_code == 200 and r.json()["team"]["leader_key"] == K["minh"], r.text)
send(TID, "Trưởng nhóm tóm tắt giúp tiến độ", mentions=[], cm="new-leader")
msgs = c.get(f"/teams/{TID}/messages{Q}").json()["messages"]
last_agent = [m for m in msgs if m["author_kind"] == "agent"][-1]
check("tin không @ do trưởng nhóm MỚI trả lời", last_agent["author_ref"] == K["minh"], last_agent)

# ═════ tắt/bật Auto ═════
toggle_auto("minh", False)
r = c.post(f"/teams/{TID}/messages/{last_agent['id']}/reaction{Q}", json={"value": "love", "nonce": "auto-off-1"})
drain()
asyncio.run(main._feedback_pulse_tick())
st = next(m for m in c.get(f"/teams/{TID}/messages{Q}").json()["messages"] if m["id"] == last_agent["id"])["reaction"]
check("Auto tắt: phản hồi chỉ lưu (stored_only)", st["status"] == "stored_only", st)
toggle_auto("minh", True)
asyncio.run(main._feedback_pulse_tick())
st2 = next(m for m in c.get(f"/teams/{TID}/messages{Q}").json()["messages"] if m["id"] == last_agent["id"])["reaction"]
check("bật lại Auto: phản hồi cũ không bị phát lại (vẫn stored_only)", st2["status"] == "stored_only", st2)

# ═════ thu hồi Toàn quyền ═════
grant = {"caps": {}, "ceilings": {"daily_turns": 150}, "providers_unlimited": [], "can_interrupt": False}
r = c.post(f"/teams/{TID}/authority{Q}", json={"mode": "full", "grant": grant})
check("cấp Toàn quyền: 200", r.status_code == 200, r.text)
check("trưởng nhóm có Toàn quyền: lượt quét được phép xếp việc", main._pulse_can_enqueue(K["minh"], f"team:{TID}"))
r = c.post(f"/teams/{TID}/authority{Q}", json={"mode": "limited", "reason": "thử thu hồi"})
check("thu hồi: 200, không còn Toàn quyền", r.status_code == 200 and api.teams().active_authority(TID) is None, r.text)
check("sau thu hồi: lượt quét chỉ còn đề xuất (không xếp việc)", not main._pulse_can_enqueue(K["minh"], f"team:{TID}"))

# ═════ lỗi kho khi chiếu tác động (outbox) ═════
runner = api.runner()
real_project = runner.projector.project
box = {"n": 0}


def flaky(kind, log_id):
    box["n"] += 1
    raise sqlite3.OperationalError("database is locked (giả)")


runner.projector.project = flaky
r = c.post(f"/teams/{TID}/messages/{mid}/reaction{Q}", json={"value": "haha", "nonce": "store-err-1"})
runner.projector.project = real_project
check("kho lỗi lúc chiếu: thao tác vẫn 200, reaction đã lưu", r.status_code == 200
      and r.json()["reaction"]["value"] == "haha" and box["n"] == 1, r.text)
with sqlite3.connect(STATE / "team.sqlite3") as db:
    eff = db.execute("SELECT effect_state FROM team_reaction_log WHERE nonce='store-err-1'").fetchone()[0]
check("dòng nhật ký giữ pending để chiếu lại", eff == "pending", eff)
asyncio.run(main._feedback_pulse_tick())
with sqlite3.connect(STATE / "team.sqlite3") as db:
    eff2 = db.execute("SELECT effect_state FROM team_reaction_log WHERE nonce='store-err-1'").fetchone()[0]
check("nhịp chiếu lại: dòng nhật ký hết pending (không mất, không tác động kép)", eff2 != "pending", eff2)

# ═════ lệch đồng hồ ═════
t0 = time.time()
AP.wake(ps, K["minh"], f"team:{TID}", "direct", at=t0)
try:
    out = AP.evaluate(ps, K["minh"], f"team:{TID}", at=t0 - 3600)
    ok = out["tier"] in range(0, 10) and out["state"] in AP.STATES
except Exception as ex:  # noqa: BLE001
    ok, out = False, f"{type(ex).__name__}: {ex}"
check("đồng hồ lùi 1 giờ: đánh giá nhịp không lỗi, bậc và trạng thái hợp lệ", ok, out)
saved = runner.clock
runner.clock = lambda: t0 - 2 * 86400
try:
    ctx = runner._context(api.teams().get(TID), K["minh"], "member_reply", None, None)
finally:
    runner.clock = saved
fb_block = ctx.split("## Phản hồi gần đây của chủ nhóm")[1].split("\n## ")[0] if "## Phản hồi gần đây của chủ nhóm" in ctx else ""
check("đồng hồ bộ chạy lùi 2 ngày: khối phản hồi vẫn có đúng dòng của tin đó (phản hồi không biến mất)",
      f"[#{mid}]" in fb_block and "cảm xúc:" in fb_block, ctx[-1500:])

# ═════ nhóm bị chặn / agent ngủ không chiếm suất ═════
runner = api.runner()
runner.max_parallel_teams = 1
A, KA = new_team("Bị chặn A", members=("tuan",), leader="tuan")
B, KB = new_team("Bị chặn B", members=("tuan",), leader="tuan")
C, KC = new_team("Có việc C", members=("lan",), leader="lan")
ts = main.tasks_feature.store
# A và B bị chặn NGAY TRONG lượt của bộ chạy (engine giả lỗi), mỗi lần pool chỉ một chỗ.
for tm_, kk in ((A, KA), (B, KB)):
    j = send(tm_["team_id"], "Việc sẽ bị chặn", mentions=[kk["tuan"]], as_job=True, cm=f"blk-{tm_['team_id']}",
             run=False)
    fakes.team_error = RuntimeError("engine giả lỗi giữa lượt")
    try:
        got_claim = asyncio.run(runner.dispatch_once(wait=True))
        drain()
    finally:
        fakes.team_error = None
    check(f"{tm_['name']}: bộ chạy nhận việc, lượt lỗi giữa chừng thì việc bị chặn", j["task_id"] in got_claim
          and ts.get_task(j["task_id"])["status"] == "team_blocked", (got_claim, ts.get_task(j["task_id"])["status"]))
    check(f"{tm_['name']}: việc bị chặn trả chỗ pool ngay", not runner._pool, runner._pool)
# Agent của nhóm C đang ngủ đông ở ngữ cảnh nhóm C: việc được giao vẫn chạy (nghĩa vụ không theo nhịp chủ động).
toggle_auto("lan", True)
AP.ensure_row(ps, KC["lan"], f"team:{C['team_id']}")
with ps._Tx(ps) as cx:
    cx.execute("UPDATE agent_pulse SET state='hibernating', tier=?, next_due_at=NULL WHERE agent_key=? AND context_ref=?",
               (AP.HIBERNATE, KC["lan"], f"team:{C['team_id']}"))
jc = send(C["team_id"], "Việc thật của nhóm C", mentions=[KC["lan"]], as_job=True, cm="c-job", run=False)
claimed = asyncio.run(runner.dispatch_once(wait=True))
drain()
check("pool một chỗ, hai nhóm vừa bị chặn trong lượt: nhóm C có việc vẫn được nhận và chạy", jc["task_id"] in claimed,
      claimed)
check("việc của agent đang ngủ đông vẫn chạy xong (nghĩa vụ giữ)", ts.get_task(jc["task_id"])["status"] == "done",
      ts.get_task(jc["task_id"])["status"])
check("không nhóm bị chặn nào giữ chỗ trong pool sau lượt", not runner._pool, runner._pool)
check("pulse ngủ đông không giữ khoá bận của agent", api.teams().busy_of(KC["lan"]) is None)

# ═════ kịch bản đo VPS: chuẩn bị sẵn, không tự chạy ═════
import subprocess  # noqa: E402
import sys  # noqa: E402
VPS = Path(__file__).resolve().parents[2] / "tools" / "team_adaptive_vps_measure.py"
p1 = subprocess.run([sys.executable, "-X", "utf8", str(VPS)], capture_output=True, text=True, encoding="utf-8", timeout=60)
check("kịch bản VPS không có duyệt của chủ: dừng mã 2, không đo gì", p1.returncode == 2 and "duyệt" in p1.stderr,
      p1.stderr[-300:])
p2 = subprocess.run([sys.executable, "-X", "utf8", str(VPS), "--owner-approved", "x", "--base-url", "https://vps.example"],
                    capture_output=True, text=True, encoding="utf-8", timeout=60)
check("kịch bản VPS trỏ ra ngoài container: dừng mã 2 trước khi kết nối", p2.returncode == 2 and "127.0.0.1" in p2.stderr,
      p2.stderr[-300:])
check("kịch bản VPS ghi rõ CHƯA CHẠY và chỉ GET", VPS.read_text(encoding="utf-8").startswith('"""CHƯA CHẠY')
      and 'method="GET"' in VPS.read_text(encoding="utf-8"))

finish()
