"""Resonance A5: cổng chi phí của bộ chạy pilot (sổ lượt theo vai `_a5_pilot_ledger.py`), không cần server hay model.

    python tests/run.py resonance_a5_pilot_gate -v

Kiểm đúng mã sổ mà launcher `_a5_pilot_server.py` dùng: giữ chỗ và ghi xuống đĩa trước khi dựng engine; trần vai, trần
tổng, trần giai đoạn; vai khác bị chặn; lượt giữ chỗ chưa có kết cục và mọi kết cục khác `ok` đóng sổ (kể cả sau khi
"tiến trình" mới mở lại sổ); sổ hỏng, thiếu hay sai cấu trúc không cấp lượt và không bị ghi đè; bị chặn thì không chạm
hàm dựng thật; kết cục của lượt (final, lỗi, ngoại lệ, huỷ, không có final) chốt đúng và chốt NGAY khi thấy khung kết
thúc; `max_wall_s` chuyển xuống engine thật; phân nhánh và đếm lượt của bộ chạy. Engine ở đây là engine giả.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import json
import tempfile
from pathlib import Path

import _a5_pilot_ledger as PL

_fails = []
CAPS = {"maker": 2, "reviewer": 2, "total": 4}
TMP = Path(tempfile.mkdtemp(prefix="a5pg-"))


def check(name, cond, detail=""):
    print(("ok   " if cond else "FAIL ") + name + ("" if cond or not detail else f"  [{str(detail)[:300]}]"))
    if not cond:
        _fails.append(name)


def fresh(name, caps=CAPS, phase=None):
    p = TMP / f"{name}.json"
    p.write_text(json.dumps({"run_id": name, "caps": caps, "calls": [], "events": []}), encoding="utf-8")
    return PL.RoleLedger(p, phase if phase is not None else {"maker": caps["maker"], "reviewer": caps["reviewer"]})


def calls(led):
    return [(c["role"], c["status"]) for c in led.load()[0]["calls"]]


def refused(led):
    return [e["why"] for e in led.load()[0]["events"] if e["kind"] == "refused"]


# ───── giữ chỗ, trần ─────
led = fresh("basic")
n1, w1 = led.reserve("maker")
on_disk = json.loads(led.path.read_text(encoding="utf-8"))["calls"]
check("giữ chỗ ghi xuống đĩa TRƯỚC khi trả (dòng reserved đã có trên đĩa)", n1 == 1 and not w1
      and on_disk == [{**on_disk[0], "role": "maker", "status": "reserved"}])
led.settle(1, "ok")
led.settle(1, "engine_error")
check("chốt lần hai không đổi kết cục đã chốt", calls(led) == [("maker", "ok")])
n2, _ = led.reserve("reviewer")
led.settle(n2, "ok")
n3, _ = led.reserve("maker")
led.settle(n3, "ok")
n4, w4 = led.reserve("maker")
check("hết trần vai làm (2): bị chặn cap_maker, không thêm dòng, ghi sự kiện refused",
      n4 == 0 and w4 == "cap_maker" and len(calls(led)) == 3 and refused(led) == ["cap_maker"])
n5, _ = led.reserve("reviewer")
led.settle(n5, "ok")
n6, w6 = led.reserve("reviewer")
check("trần tổng (4) và trần vai review (2) chặn lượt thứ năm", n6 == 0 and w6 in ("cap_reviewer", "cap_total")
      and len(calls(led)) == 4)

led = fresh("total", caps={"maker": 3, "reviewer": 3, "total": 2}, phase={"maker": 3, "reviewer": 3})
for r in ("maker", "reviewer"):
    n, _ = led.reserve(r)
    led.settle(n, "ok")
check("trần tổng chặn dù vai còn phần", led.reserve("maker") == (0, "cap_total"))

led = fresh("phase", phase={"maker": 0, "reviewer": 0})
check("trần giai đoạn 0 (dựng, dựng lại): mọi vai bị chặn, có sự kiện refused",
      led.reserve("maker") == (0, "cap_maker") and led.reserve("reviewer") == (0, "cap_reviewer")
      and calls(led) == [] and refused(led) == ["cap_maker", "cap_reviewer"])
check("vai khác (bộ lập mục tiêu, lời dặn lạ) luôn bị chặn", fresh("other").reserve("other") == (0, "role_other"))

# ───── sổ đóng ─────
led = fresh("crash")
led.reserve("maker")
again = PL.RoleLedger(led.path, {"maker": 2, "reviewer": 2})          # "tiến trình mới" mở lại sổ
check("lượt giữ chỗ chưa có kết cục (chết giữa lượt) đóng sổ, kể cả ở tiến trình mới",
      again.reserve("reviewer") == (0, "reserved_without_outcome"))
for st in ("engine_error", "cancelled", "exception", "not_built", "no_final"):
    led = fresh("halt-" + st)
    n, _ = led.reserve("maker")
    led.settle(n, st)
    check(f"kết cục {st}: lượt vẫn tính, sổ đóng", calls(led) == [("maker", st)]
          and led.reserve("reviewer") == (0, f"halted_after_{st}"))

for name, body in (("corrupt", "{hỏng"), ("shape", json.dumps({"calls": [], "events": []})),
                   ("badcall", json.dumps({"caps": CAPS, "events": [], "calls": [{"n": 2, "role": "maker",
                                                                                  "status": "ok"}]})),
                   ("badcap", json.dumps({"caps": {"maker": "2", "reviewer": 2, "total": 4}, "calls": [],
                                          "events": []}))):
    p = TMP / f"{name}.json"
    p.write_text(body, encoding="utf-8")
    n, why = PL.RoleLedger(p, {"maker": 2, "reviewer": 2}).reserve("maker")
    check(f"sổ {name}: không cấp lượt, không ghi đè (giữ nguyên làm bằng chứng)", n == 0 and why.startswith("ledger_")
          and p.read_text(encoding="utf-8") == body, why)
n, why = PL.RoleLedger(TMP / "khong-co.json", {"maker": 2}).reserve("maker")
check("thiếu sổ: không cấp lượt", n == 0 and why.startswith("ledger_unreadable"))


# ───── hàm dựng bọc sổ và kết cục của lượt ─────
class Eng:
    def __init__(self, events, raise_at=None):
        self.events, self.raise_at, self.max_wall_s = events, raise_at, None

    def is_available(self):
        return True

    async def query(self, prompt):
        for i, ev in enumerate(self.events):
            if self.raise_at == i:
                raise RuntimeError("engine giả lỗi giữa chừng")
            if ev == "sleep":
                await asyncio.sleep(10)
                continue
            yield ev


def role_of(sp):
    return {"R": "reviewer", "W": "maker"}.get(sp, "other")


built = []


def real(eng):
    def f(sp, tag="resonance"):
        built.append(sp)
        return eng, {"provider": "fake", "model": "fake-1"}
    return f


led = fresh("wrap-block", phase={"maker": 0, "reviewer": 0})
built.clear()
e, info = PL.wrap_factory(real(Eng([])), led, role_of)("W")
check("bị chặn: trả (None, lý do) và KHÔNG gọi hàm dựng thật", e is None and built == []
      and "pilot_ledger:cap_maker" in info["blocked"])


async def consume(eng, stop_after_final=True):
    out = []
    async for ev in eng.query("p"):
        out.append(ev)
        if stop_after_final and ev.get("type") in ("final", "error"):
            break
    return out


led = fresh("wrap-ok")
f = PL.wrap_factory(real(Eng([{"type": "stream", "content": "x"}, {"type": "final", "content": "y",
                                                                     "tokens_in": 3}])), led, role_of)
e, info = f("W")
e.max_wall_s = 120
check("max_wall_s đặt lên engine bọc được chuyển xuống engine thật", e.inner.max_wall_s == 120)
asyncio.run(consume(e))
check("khung final: chốt ok NGAY (host ngừng đọc sau final), ghi engine và token",
      calls(led) == [("maker", "ok")] and led.load()[0]["calls"][0].get("engine") == {"provider": "fake",
                                                                                     "model": "fake-1"}
      and led.load()[0]["calls"][0].get("tokens_in") == 3)

led = fresh("wrap-err")
asyncio.run(consume(PL.wrap_factory(real(Eng([{"type": "error", "content": "x"}])), led, role_of)("R")[0]))
check("khung lỗi: engine_error, sổ đóng", calls(led) == [("reviewer", "engine_error")])

led = fresh("wrap-exc")
try:
    asyncio.run(consume(PL.wrap_factory(real(Eng([{"type": "stream"}, {"type": "final", "content": "y"}], raise_at=1)),
                                        led, role_of)("W")[0]))
except RuntimeError:
    pass
check("ngoại lệ giữa lượt: exception, vẫn tính", calls(led) == [("maker", "exception")])


async def cancel_mid():
    led = fresh("wrap-cancel")
    e, _ = PL.wrap_factory(real(Eng(["sleep"])), led, role_of)("R")
    t = asyncio.ensure_future(consume(e))
    await asyncio.sleep(0.05)
    t.cancel()
    try:
        await t
    except asyncio.CancelledError:
        pass
    return led


led = asyncio.run(cancel_mid())
check("huỷ trong lúc engine chạy: cancelled, vẫn tính", calls(led) == [("reviewer", "cancelled")])


async def no_final():
    led = fresh("wrap-nofinal")
    e, _ = PL.wrap_factory(real(Eng([{"type": "stream"}])), led, role_of)("W")
    gen = e.query("p")
    async for _ev in gen:
        pass
    return led


led = asyncio.run(no_final())
check("hết khung mà không có final: no_final, vẫn tính", calls(led) == [("maker", "no_final")])


def boom(sp, tag="resonance"):
    raise RuntimeError("không dựng được")


led = fresh("wrap-build")
try:
    PL.wrap_factory(boom, led, role_of)("W")
except RuntimeError:
    pass
check("hàm dựng thật ném lỗi: lượt đã giữ chỗ chốt not_built (bảo thủ, vẫn tính), sổ đóng",
      calls(led) == [("maker", "not_built")] and led.reserve("reviewer")[0] == 0)
led = fresh("wrap-none")
e, info = PL.wrap_factory(lambda sp, tag="r": (None, {"blocked": "sai provider"}), led, role_of)("W")
check("hàm dựng thật trả None: not_built, trả nguyên lý do cho host", e is None and calls(led) == [("maker", "not_built")]
      and info == {"blocked": "sai provider"})

# ───── phân nhánh và đếm của bộ chạy ─────
check("nhánh: đạt ngay", PL.classify("succeeded", ["pass"], ["succeeded"], []) == "pass_first")
check("nhánh: một vòng sửa rồi đạt", PL.classify("succeeded", ["needs_changes", "pass"], ["succeeded", "succeeded"],
                                                 []) == "one_fix_then_pass")
check("nhánh: hai lần cần sửa rồi chạm trần pilot", PL.classify(
    "active", ["needs_changes", "needs_changes"], ["succeeded", "succeeded", "failed"], ["cap_maker"])
    == "pilot_cap_after_two_reviews")
check("nhánh: hai lần cần sửa, lượt sửa bị trần kho của pilot chặn lúc giữ chỗ (blocked/budget, sổ không thấy gì)",
      PL.classify("active", ["needs_changes", "needs_changes"], ["succeeded", "succeeded"], [], "budget")
      == "pilot_cap_after_two_reviews")
check("nhánh: review không đọc được", PL.classify("active", ["unknown"], ["succeeded"], []) == "review_unknown")
check("nhánh: lượt làm đầu lỗi", PL.classify("active", [], ["failed"], []) == "maker_error")
check("nhánh: hai lần cần sửa mà KHÔNG do trần pilot thì không gán nhầm nhánh trần",
      PL.classify("active", ["needs_changes", "needs_changes"], ["succeeded", "succeeded"], []) == "other")
st = {"calls": [{"n": 1, "role": "maker", "status": "ok"}, {"n": 2, "role": "reviewer", "status": "engine_error"}],
      "events": [{"kind": "refused", "why": "cap_maker"}, {"kind": "tripwire"}], "caps": CAPS}
check("đếm: mọi kết cục đều tính theo vai; liệt kê kết cục khác ok, lần bị chặn, bẫy",
      PL.ledger_counts(st) == {"maker": 1, "reviewer": 1, "total": 2, "not_ok": ["engine_error"],
                               "not_ok_roles": ["reviewer"], "refused": ["cap_maker"], "tripwire": 1})
check("nhánh: lỗi engine của vai review khác với review không đọc được",
      PL.classify("active", ["unknown"], ["succeeded"], [], "", reviewer_failed=True) == "reviewer_error")
check("nhánh: bản làm chưa đạt kiểm khách quan, chưa có review",
      PL.classify("active", [], ["succeeded"], []) == "maker_not_met")

# ═════════ R1 (review cổng pilot vòng 1): kết cục của lượt theo đúng luật lỗi của host ═════════
import resonance as R  # noqa: E402


def through_host(name, events, verdict=PL.host_text_verdict, wrap_ask=False):
    """Chạy MỘT lượt qua `GoalDeps._ask` THẬT của host với engine giả bọc sổ; trả (lỗi host, dòng sổ, lượt kế được
    giữ chỗ không)."""
    led = fresh(name)
    factory = PL.wrap_factory(lambda s, t: (Eng(events), {"provider": "fake", "model": "fake"}), led, role_of, verdict)
    deps = R.GoalDeps(factory, R.CallBudget(4))
    ask = PL.wrap_ask(R.GoalDeps._ask, led) if wrap_ask else R.GoalDeps._ask
    turn = asyncio.run(ask(deps, "W", "p"))
    row = led.load()[0]["calls"][0]
    nxt, _w = led.reserve("reviewer")
    return turn.error_code, row, nxt


code, row, nxt = through_host("h-ok", [{"type": "final", "content": "Một kết quả hợp lệ."}])
check("đối chứng: final hợp lệ, host không lỗi, sổ ok, lượt kế được cấp", not code and row["status"] == "ok"
      and nxt == 2, (code, row, nxt))
for name, events, want in (
        ("h-is-error", [{"type": "final", "is_error": True, "subtype": "error_during_execution", "content": "x"}],
         "engine_result_error"),
        ("h-race", [{"type": "final", "dua_token": True, "content": "Failed to refresh OAuth token"}],
         "engine_session_race"),
        ("h-final-error", [{"type": "final", "content": "Bản dở"}, {"type": "error", "content": "lỗi muộn"}],
         "engine_error"),
        ("h-tool-final", [{"type": "tool_call", "name": "Read"}, {"type": "final", "content": "Có gọi công cụ"}],
         "tool_call_in_text_only"),
        ("h-final-tool", [{"type": "final", "content": "Xong"}, {"type": "tool_call", "name": "Read"}],
         "tool_call_in_text_only"),
        ("h-empty", [{"type": "final", "content": "   "}], "empty_output")):
    code, row, nxt = through_host(name, events)
    check(f"{name}: host báo {code}; sổ ghi {row['status']} (không phải ok), lượt vẫn tính, sổ đóng",
          code == want and row["status"] == want and nxt == 0, (code, row, nxt))
code, row, nxt = through_host("h-final-error-row", [{"type": "final", "content": "Bản dở"},
                                                    {"type": "error", "content": "lỗi muộn"}])
check("ok tạm bị hạ khi lỗi đến sau final, có ghi downgraded_from", row.get("downgraded_from") == "ok", row)


async def final_then(kind):
    led = fresh("after-" + kind)
    events = [{"type": "final", "content": "Xong"}, "sleep"] if kind != "exception" else \
        [{"type": "final", "content": "Xong"}, {"type": "stream"}]
    e, _ = PL.wrap_factory(real(Eng(events, raise_at=1 if kind == "exception" else None)), led, role_of)("W")
    gen = e.query("p")
    await gen.__anext__()                                    # host đã nhận final
    if kind == "cancel":
        # Host còn đọc (chờ khung kế) thì bị huỷ, như hết giờ của `_ask`.
        t = asyncio.ensure_future(gen.__anext__())
        await asyncio.sleep(0.05)
        t.cancel()
        try:
            await t
        except asyncio.CancelledError:
            pass
    elif kind == "exception":
        # Host còn đọc thì engine ném lỗi sau final.
        try:
            await gen.__anext__()
        except RuntimeError:
            pass
    else:                                                    # host ngừng đọc sau final (đối chứng)
        pass
    return led


for kind, want in (("cancel", "cancelled"), ("exception", "exception"), ("stop", "ok")):
    led = asyncio.run(final_then(kind))
    check(f"final rồi {kind}: sổ {want}" + ("; host ngừng đọc thì ok vẫn giữ và cấp lượt kế" if kind == "stop" else
                                             "; lỗi thắng ok tạm, sổ đóng"),
          calls(led) == [("maker", want)] and (led.reserve("reviewer")[0] == (2 if want == "ok" else 0)), calls(led))

led = fresh("no-upgrade")
n, _ = led.reserve("maker")
led.mark_bad(n, "engine_error")
led.settle(n, "ok")
led.mark_bad(n, "cancelled")
check("không bao giờ nâng lỗi thành ok, không đổi lỗi này sang lỗi khác", calls(led) == [("maker", "engine_error")])
code, row, nxt = through_host("h-ask", [{"type": "final", "content": "   "}], verdict=lambda t: "ok", wrap_ask=True)
check("lớp hai: host báo lỗi mà luồng khung không thấy (bộ kiểm chữ bị thay), đối chiếu `_ask` vẫn hạ dòng sổ",
      code == "empty_output" and row["status"] == "host_empty_output" and nxt == 0, (code, row))

# ═════════ R2: kết luận của một lần chạy ═════════
GOOD_REP = {"phase_B_started": True, "phase_B": {"stop": "goal_succeeded"}, "ledger_status": "verified",
            "ledger_final_counts": {"maker": 1, "reviewer": 1, "total": 2, "not_ok": [], "tripwire": 0},
            "engine_turns_status": "verified", "restart": {"ok": True}, "preserve": {"ok": True},
            "branch": "pass_first",
            "store_B": {"goal": {"status": "succeeded"}, "team_calls": {"maker": {"used": 1}, "reviewer": {"used": 1}}},
            "saved": [{"role": "maker", "ok": True}, {"role": "reviewer", "ok": True},
                      {"role": "deliverable", "ok": True}],
            "snapshot_hash_ok": [True]}


def with_(**kw):
    r = json.loads(json.dumps(GOOD_REP))
    for k, v in kw.items():
        if v is None:
            r.pop(k, None)
        else:
            r[k] = v
    return r


check("kết luận: đủ bằng chứng nhánh pass_first: chờ duyệt nội dung",
      PL.decide_acceptance(GOOD_REP, [], "real") == ("pending_content_review", []))
for label, rep, fails in (
        ("có kiểm hỏng", GOOD_REP, ["x"]),
        ("lượt lỗi engine (maker_error)", with_(branch="maker_error", ledger_final_counts={
            "maker": 1, "reviewer": 0, "total": 1, "not_ok": ["engine_error"], "tripwire": 0}), []),
        ("hết giờ, không lượt, không đầu ra", with_(phase_B={"stop": "wall"}, branch="no_review",
                                                    ledger_final_counts={"maker": 0, "reviewer": 0, "total": 0,
                                                                         "not_ok": [], "tripwire": 0}, saved=[]), []),
        ("sổ mất ở lần đọc cuối", with_(ledger_status="unverified: missing", ledger_final_counts=None), []),
        ("sổ usage không xác minh", with_(engine_turns_status="unverified: x"), []),
        ("thiếu đầu ra lượt làm", with_(saved=[{"role": "reviewer", "ok": True}, {"role": "deliverable", "ok": True}]),
         []),
        ("thiếu file đích khi chốt", with_(saved=[{"role": "maker", "ok": True}, {"role": "reviewer", "ok": True}]), []),
        ("ảnh chụp review chưa băm lại", with_(snapshot_hash_ok=[]), []),
        ("chưa kiểm dựng lại", with_(restart=None), []),
        ("bảo toàn bằng chứng lỗi", with_(preserve={"ok": False}), []),
        ("sổ lệch số của nhánh", with_(ledger_final_counts={"maker": 2, "reviewer": 1, "total": 3, "not_ok": [],
                                                           "tripwire": 0}), []),
        ("sổ vai của kho lệch", with_(store_B={"goal": {"status": "succeeded"},
                                               "team_calls": {"maker": {"used": 2}, "reviewer": {"used": 1}}}), []),
        ("dừng sau khi việc nền đã bắt đầu", with_(stopped="dừng: x"), []),
        ("nhánh lạ", with_(branch="other"), []),
        ("báo cáo rỗng (đóng khi lỗi)", {"phase_B_started": True}, [])):
    got = PL.decide_acceptance(rep, fails, "real")
    check(f"kết luận real: {label}: technical_failed, có lý do", got[0] == "technical_failed" and got[1], got)
check("kết luận: dừng ở cổng trước việc nền: stopped",
      PL.decide_acceptance({"stopped": "dừng trước mọi lượt"}, ["x"], "real")[0] == "stopped")
for br, calls_, goal in (("pilot_cap_after_two_reviews", (2, 2), "active"), ("review_unknown", (1, 1), "active"),
                         ("maker_not_met", (1, 0), "active")):
    rep = with_(branch=br, phase_B={"stop": "quiet"},
                ledger_final_counts={"maker": calls_[0], "reviewer": calls_[1], "total": sum(calls_), "not_ok": [],
                                     "tripwire": 0},
                store_B={"goal": {"status": goal}, "team_calls": {"maker": {"used": calls_[0]},
                                                                  "reviewer": {"used": calls_[1]}}},
                saved=[{"role": "maker", "ok": True}] * calls_[0] + [{"role": "reviewer", "ok": True}] * calls_[1],
                snapshot_hash_ok=[True] * calls_[1])
    check(f"kết luận: nhánh nghiệp vụ {br} chạy đúng: business_incomplete, không gộp với lỗi kỹ thuật",
          PL.decide_acceptance(rep, [], "real") == ("business_incomplete", []))
check("mã thoát: chỉ duyệt nội dung là 0; nhánh nghiệp vụ 2; còn lại khác 0",
      PL.EXIT_CODES == {"pending_content_review": 0, "business_incomplete": 2}
      and PL.EXIT_CODES.get("technical_failed", 1) == 1)

# ═════════ R3: bảo toàn bằng chứng và quyền dọn ═════════
import sqlite3  # noqa: E402


def sandbox(name):
    b = TMP / f"sb-{name}"
    (b / "state").mkdir(parents=True)
    (b / "brains" / "Brain Default" / "Inbox").mkdir(parents=True)
    c = sqlite3.connect(str(b / "state" / "resonance.sqlite3"))
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("CREATE TABLE goals(id TEXT)")
    c.execute("INSERT INTO goals VALUES('g1')")
    c.commit()
    c.close()
    (b / "state" / "usage.json").write_text('{"total": {}}', encoding="utf-8")
    (b / "server-1-A.log").write_text("khởi động\nauthorization: Bearer abc.def.ghi\nsk-ant-oat01-XYZ\nxong\n",
                                      encoding="utf-8")
    (b / "brains" / "Brain Default" / "Inbox" / "f.md").write_text("bản", encoding="utf-8")
    return b


b = sandbox("ok")
out = TMP / "out-ok"
out.mkdir()
(out / "sandbox").mkdir()                                     # đã có: không ghi đè, dùng thư mục mới
src_before = (b / "state" / "resonance.sqlite3").read_bytes()
pr = PL.preserve_sandbox(b, out, required=["resonance.sqlite3", "server-1-A.log"])
dest = Path(pr["dest"])
log_copy = (dest / "logs" / "server-1-A.log").read_text(encoding="utf-8")
c = sqlite3.connect(str(dest / "state" / "resonance.sqlite3"))
rows = c.execute("SELECT id FROM goals").fetchall()
c.close()
check("bảo toàn: thư mục MỚI (không ghi đè thư mục có sẵn), kho chép bằng backup đọc được, brain và sổ usage",
      pr["ok"] and dest.name == "sandbox-2" and rows == [("g1",)]
      and (dest / "brains" / "Brain Default" / "Inbox" / "f.md").is_file() and (dest / "state" / "usage.json").is_file(),
      pr)
check("bảo toàn: log che khoá và token, giữ nội dung khác", "Bearer abc" not in log_copy and "sk-ant" not in log_copy
      and "khởi động" in log_copy and "xong" in log_copy, log_copy)
check("bảo toàn: nguồn không bị sửa hay xoá", (b / "state" / "resonance.sqlite3").read_bytes() == src_before
      and (b / "server-1-A.log").is_file())
b2 = sandbox("fault")
out2 = TMP / "out-fault"
out2.mkdir()
pr2 = PL.preserve_sandbox(b2, out2, required=["resonance.sqlite3"], fault=lambda n: n == "resonance.sqlite3")
check("lỗi trong bước lưu: ok=False, ghi lỗi của mục đó, nguồn còn nguyên",
      pr2["ok"] is False and any(it["name"] == "resonance.sqlite3" and it.get("error") for it in pr2["items"])
      and (b2 / "state" / "resonance.sqlite3").is_file(), pr2)
b3 = sandbox("missing")
(b3 / "state" / "resonance.sqlite3").unlink()
pr3 = PL.preserve_sandbox(b3, TMP / "out-missing", required=["resonance.sqlite3"]) if (TMP / "out-missing").mkdir() \
    is None else None
check("thiếu mục bắt buộc (kho): ok=False", pr3["ok"] is False)
b4 = sandbox("corrupt")
(b4 / "state" / "usage.json").write_bytes(b"{h\xc6\xa1ng")
(TMP / "out-corrupt").mkdir()
pr4 = PL.preserve_sandbox(b4, TMP / "out-corrupt")
check("file hỏng chép NGUYÊN bytes, không sửa", (Path(pr4["dest"]) / "state" / "usage.json").read_bytes()
      == b"{h\xc6\xa1ng")

b5 = sandbox("deep")
deep = TMP / ("hs-" + "d" * 60) / ("thu-muc-ho-so-" + "x" * 60) / ("con-" + "y" * 60) / ("chau-" + "z" * 60)
import os  # noqa: E402
os.makedirs(PL._xp(deep), exist_ok=True)
pr5 = PL.preserve_sandbox(b5, deep, required=["resonance.sqlite3", "server-1-A.log"])
check(f"bảo toàn khi thư mục hồ sơ sâu (đường dẫn {len(str(deep)) + 60} ký tự, vượt 260 của Windows)",
      pr5["ok"] is True and os.path.isfile(PL._xp(Path(pr5["dest"]) / "state" / "resonance.sqlite3")), pr5)

ok_pres = {"ok": True}
outside, inside = TMP / "hs", b / "out"
check("dọn sandbox: chỉ khi dry, kỹ thuật đạt, bảo toàn đủ, hồ sơ ngoài sandbox",
      PL.may_delete_sandbox("dry", "pending_content_review", ok_pres, b, outside) is True)
for label, args in (("real luôn giữ", ("real", "pending_content_review", ok_pres, b, outside)),
                    ("technical_failed giữ", ("dry", "technical_failed", ok_pres, b, outside)),
                    ("nhánh nghiệp vụ chưa đạt giữ", ("dry", "business_incomplete", ok_pres, b, outside)),
                    ("bảo toàn lỗi giữ", ("dry", "pending_content_review", {"ok": False}, b, outside)),
                    ("hồ sơ nằm trong sandbox giữ", ("dry", "pending_content_review", ok_pres, b, inside))):
    check(f"không dọn: {label}", PL.may_delete_sandbox(*args) is False)

# ═════════ Review cổng vòng 2: ghi hồ sơ cuối là một phần của kết luận ═════════
import contextlib  # noqa: E402
import io  # noqa: E402
from unittest.mock import patch  # noqa: E402


def finish(name, mode, acceptance, fault=None, branch="pass_first", delete=None, patch_write=None, no_out=False):
    """Chạy `finalize_record` thật trên fixture pha kết thúc (không engine). Trả kết quả và các kênh."""
    root = TMP / f"fin-{name}"
    base, out = root / "sandbox", root / "hs"
    base.mkdir(parents=True)
    if not no_out:
        out.mkdir()
    (base / "keep.txt").write_text("bằng chứng", encoding="utf-8")
    rep = {"mode": mode, "scenario": "main", "acceptance": acceptance, "acceptance_why": [], "branch": branch,
           "ledger_status": "verified", "engine_turns_logged": 0, "engine_turns_status": "verified",
           "model_turns": {"background_real": 0}}
    pres = {"ok": True, "dest": str(out / "sandbox")}
    if delete is None:
        delete = PL.may_delete_sandbox(mode, acceptance, pres, base, out)
    so, se = io.StringIO(), io.StringIO()
    ctx = patch.object(Path, "write_text", patch_write) if patch_write else contextlib.nullcontext()
    with ctx, contextlib.redirect_stdout(so), contextlib.redirect_stderr(se):
        deleted = PL.finalize_record(rep, mode, "main", base, out, pres, delete, {"maker": 1, "reviewer": 1},
                                     fault=fault)
    report = out / f"a5-pilot-{mode}-main.json"
    saved = json.loads(report.read_text(encoding="utf-8")) if report.exists() else None
    rec = (out / "a5-pilot-recovery.txt").read_text(encoding="utf-8") if (out / "a5-pilot-recovery.txt").exists() \
        else None
    line = next((x for x in so.getvalue().splitlines() if x.startswith("A5_PILOT ")), "")
    head = json.loads(line[len("A5_PILOT "):].partition(" PRESERVE ")[0]) if line else {}
    return {"rep": rep, "exit": PL.EXIT_CODES.get(rep["acceptance"], 1), "deleted": deleted, "saved": saved,
            "rec": rec, "line": head, "stdout": so.getvalue(), "stderr": se.getvalue(), "base": base}


r = finish("real-ok", "real", "pending_content_review")
check("đối chứng real: lưu đủ: giữ kết luận và mã thoát 0; real giữ sandbox, ghi đường khôi phục; báo cáo khớp dòng",
      r["exit"] == 0 and r["saved"]["acceptance"] == "pending_content_review" and r["deleted"] is False
      and r["rec"] and r["line"]["acceptance"] == "pending_content_review" and r["line"]["sandbox_kept"] is True
      and r["saved"]["sandbox_kept"] is True and r["saved"]["report_saved"] is True, r["rep"])
r = finish("dry-ok", "dry", "pending_content_review")
check("đối chứng dry: lưu đủ: mã thoát 0, được dọn, không cần đường khôi phục", r["exit"] == 0 and r["deleted"] is True
      and r["rec"] is None and r["saved"]["sandbox_kept"] is False and r["line"]["sandbox_kept"] is False)
for mode in ("real", "dry"):
    r = finish(f"{mode}-report", mode, "pending_content_review", fault="report")
    check(f"{mode}: ghi báo cáo cuối lỗi sau kết quả đạt: technical_failed, mã thoát 1, giữ sandbox, không có báo cáo "
          "nói đạt, đường khôi phục ghi lại với kết luận mới, stdout và stderr báo kèm đường sandbox",
          r["exit"] == 1 and r["rep"]["acceptance"] == "technical_failed" and r["deleted"] is False
          and r["rep"]["sandbox_kept"] is True and r["saved"] is None and "technical_failed" in (r["rec"] or "")
          and str(r["base"]) in r["stdout"] and str(r["base"]) in r["stderr"]
          and "KHÔNG GHI ĐƯỢC HỒ SƠ CUỐI" in r["stderr"] and r["line"]["acceptance"] == "technical_failed"
          and r["line"]["sandbox_kept"] is True and r["line"]["report_saved"] is False
          and r["rep"]["branch"] == "pass_first" and any("báo cáo cuối" in w for w in r["rep"]["acceptance_why"]),
          r["rep"])
r = finish("real-recovery", "real", "pending_content_review", fault="recovery")
check("real: ghi đường khôi phục lỗi: technical_failed, mã thoát 1; báo cáo (ghi SAU) nói technical_failed, không nói đạt",
      r["exit"] == 1 and r["saved"]["acceptance"] == "technical_failed" and r["deleted"] is False
      and any("đường khôi phục" in w for w in r["saved"]["acceptance_why"]), r["saved"])
r = finish("biz-recovery", "real", "business_incomplete", fault="recovery", branch="review_unknown")
check("nghiệp vụ chưa đạt + ghi đường khôi phục lỗi: không giữ mã thoát 2, thành technical_failed mã 1, nhánh giữ nguyên",
      r["exit"] == 1 and r["saved"]["acceptance"] == "technical_failed" and r["saved"]["branch"] == "review_unknown")
r = finish("tech-report", "dry", "technical_failed", fault="report", branch="maker_error")
check("lỗi kỹ thuật vốn có + ghi báo cáo lỗi: vẫn thất bại, mã thoát 1, giữ sandbox", r["exit"] == 1
      and r["deleted"] is False and r["rep"]["acceptance"] == "technical_failed" and r["rep"]["branch"] == "maker_error")
_orig_wt = Path.write_text
_seen = {"n": 0}


def _flaky(path, *a, **kw):
    if path.name == "a5-pilot-dry-main.json" and _seen["n"] == 0:
        _seen["n"] = 1
        raise OSError("ổ đĩa tạm khoá")
    return _orig_wt(path, *a, **kw)


r = finish("flaky", "dry", "pending_content_review", patch_write=_flaky)
check("ghi báo cáo lỗi một lần rồi được: báo cáo lần hai ghi technical_failed (lỗi đã xảy ra), không bao giờ nói đạt",
      r["saved"] and r["saved"]["acceptance"] == "technical_failed" and r["exit"] == 1 and r["deleted"] is False
      and "technical_failed" in (r["rec"] or ""), r["saved"])
r = finish("no-out", "real", "pending_content_review", no_out=True)
check("nơi lưu hồ sơ không ghi được: technical_failed, mã thoát 1, stdout và stderr có đường sandbox để khôi phục",
      r["exit"] == 1 and r["saved"] is None and str(r["base"]) in r["stderr"] and r["deleted"] is False)
check("ca dry chèn lỗi ghi: chỉ ở dry, đúng ba ca", PL.dry_fault("real", "report_fault") is None
      and PL.dry_fault("dry", "report_fault") == "report" and PL.dry_fault("dry", "recovery_fault") == "recovery"
      and PL.dry_fault("dry", "main_pass") is None)

# ═════════ Lưu ý 2: kiểm nguồn trước khi có thể gọi model ═════════
import subprocess  # noqa: E402

repo = TMP / "repo"
repo.mkdir()


def git(*a):
    return subprocess.run(["git", *a], cwd=str(repo), capture_output=True, text=True).stdout.strip()


git("init", "-q")
git("config", "user.email", "t@example.com")
git("config", "user.name", "t")
(repo / "a.txt").write_text("a", encoding="utf-8")
git("add", "a.txt")
git("commit", "-q", "-m", "a")
head = git("rev-parse", "HEAD")
check("nguồn: đúng SHA, cây sạch: đạt", PL.preflight_source(repo, head)["ok"] is True)
check("nguồn: SHA khác: không đạt", PL.preflight_source(repo, "0" * 40)["ok"] is False)
check("nguồn: thiếu SHA đã duyệt: không đạt", PL.preflight_source(repo, "")["ok"] is False)
(repo / "a.txt").write_text("b", encoding="utf-8")
check("nguồn: file đã track bị sửa (kể cả chính bộ chạy): không đạt", PL.preflight_source(repo, head)["ok"] is False)
git("checkout", "--", "a.txt")
(repo / "la.txt").write_text("x", encoding="utf-8")
check("nguồn: file lạ chưa track: không đạt", PL.preflight_source(repo, head)["ok"] is False)
check("nguồn: không phải git: không đạt", PL.preflight_source(TMP / "khong-phai-git", head)["ok"] is False)

print(f"\n{len(_fails)} FAIL: {_fails}" if _fails else "\nOK")
raise SystemExit(1 if _fails else 0)
