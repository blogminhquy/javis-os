"""Auto toàn quyền (2026-11-14): lượt tự thức có công cụ, mốc tự hẹn, gợi ý và nhắc nhở.

    python tests/run.py pulse_auto_full -v

Chủ repo 14/11/2026: "bật auto là chấp nhận cho full quyền, kể cả quyền hành động"; agent "sẽ quét các tool, tự đặt lịch
nhắc, và tìm những gì hữu ích"; tin là "gợi ý và nhắc nhở", ngắn, dễ hiểu. Kho thật (resonance.sqlite3), đồng hồ GIẢ,
engine GIẢ. Không model thật:
- ngữ cảnh có lượt có công cụ: quét MỌI lần thức (không đợi 3 lần, không trần một lần mỗi ngày), yêu cầu `tool_turn`,
  hướng dẫn LẦN TỰ THỨC và khối ngữ cảnh của host; ngữ cảnh khác giữ lượt chỉ chữ như T3;
- mốc tự hẹn: ghi theo múi giờ của chủ, kẹp, bỏ trùng, trần; tới giờ thì một lần thức riêng, mốc là cơ hội của lần đó và
  đóng khi lượt chạy xong; lượt lỗi không kích hoạt lại mỗi nhịp; huỷ mốc chỉ của chính ngữ cảnh;
- việc đã tự làm (`did`) luôn được báo, không qua bộ phán xử; tin không kèm việc vẫn qua bộ phán xử; loại tin đi kèm;
- nhóm "Gợi ý của trợ lý" của bộ điều phối thông báo mặc định rung từ mức đáng chú ý, nhóm khác giữ mặc định cũ.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import os
import tempfile
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-pulse-auto-")
os.environ.pop("JAVIS_RESONANCE_CALL_CEILING", None)
TEMP = Path(tempfile.mkdtemp(prefix="javis-pulse-auto-w-"))

import agent_pulse as AP  # noqa: E402
import agent_pulse_host as H  # noqa: E402
import notify_policy  # noqa: E402
import resonance_store as RS  # noqa: E402

fails = []
D = 86400.0
T0 = 2_000_000_000.0
TZ = timezone(timedelta(hours=7))


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (f"  {str(extra)[:400]}" if extra and not cond else ""))
    if not cond:
        fails.append(name)


def run(coro):
    return asyncio.run(coro)


def local(ts):
    return datetime.fromtimestamp(ts, tz=TZ).strftime("%Y-%m-%d %H:%M")


class Clock:
    def __init__(self, t):
        self.t = t

    def __call__(self):
        return self.t


class Engine:
    def __init__(self, text):
        self.text = text
        self.calls = []
        self.fail = None

    def engine_for(self, key, ctx, purpose):
        async def run_(req):
            # Lượt có công cụ báo (provider, model) như `_team_engine_for`; lượt chỉ chữ không truyền gì.
            if req.get("tool_turn"):
                await req["engine_started"]("fake", "fake-model")
            else:
                await req["engine_started"]()
            self.calls.append(req)
            if self.fail:
                raise self.fail
            t = self.text(req) if callable(self.text) else self.text
            return {"text": t, "tokens_in": 3, "tokens_out": 4}
        return "fake", "fake-model", run_


class Judge:
    def __init__(self, verdict="speak"):
        self.verdict = verdict
        self.calls = []

    async def __call__(self, **kw):
        self.calls.append(kw)
        return {"verdict": self.verdict, "reason": "test", "decision_id": 5}


_n = [0]


def world(text='{"action": "none"}', tools=lambda key, ctx: ctx.startswith("dm:"), ctx_text="## Giờ hiện tại\nX",
          judge=None):
    _n[0] += 1
    d = TEMP / f"{_n[0]:02d}"
    d.mkdir()
    st = RS.GoalStore(d / "resonance.sqlite3")
    owner = RS.Principal("owner", "owner", str(d))
    k = st.agent_set_enabled(owner, "a0", True)["agent_key"]
    AP.set_state(st, k, "*", "on", at=T0)
    clock = Clock(T0)
    eng = Engine(text)
    box = {"busy": set(), "sent": [], "contexts": {}}

    def scan_context(key, ctx, now):
        if isinstance(ctx_text, Exception):
            raise ctx_text
        return ctx_text

    deps = H.PulseHostDeps(
        store=lambda: st, agents=lambda: [{"agent_key": k, "brain_id": str(d)}],
        contexts=lambda key: box["contexts"].get(key, [f"dm:{key}"]), busy=lambda key: key in box["busy"],
        try_busy=lambda key, tok: key not in box["busy"], release_busy=lambda key, tok: None,
        opportunities=lambda key, ctx, iv: [], persona=lambda key: "Bạn là trợ lý.",
        engine_for=eng.engine_for, can_enqueue=lambda key, ctx: False,
        propose=lambda key, ctx, item, src: "msg:9",
        send=lambda key, ctx, text, meta: box["sent"].append((key, ctx, text, dict(meta))) or {
            "session_id": "s1", "message_id": 70 + len(box["sent"])},
        interacted=lambda p: False, clock=clock, spawn=asyncio.ensure_future,
        tool_scan=tools, scan_context=scan_context, tz=lambda: TZ)
    j = judge or Judge()
    host = H.PulseHost(deps, judge=j, budget=lambda key, purpose, at=None: (True, ""))
    return st, k, clock, eng, box, host, j


def due_now(st, key, ctx, t):
    with st._Tx(st) as c:
        c.execute("UPDATE agent_pulse SET next_due_at=? WHERE agent_key=? AND context_ref=?", (t, key, ctx))


async def tick_all(host):
    await host.tick()
    await host.wait_idle()


def followups(st, key, ctx, status=None):
    with closing(st._conn()) as c:
        q = "SELECT * FROM pulse_followups WHERE agent_key=? AND context_ref=?"
        args = [key, ctx]
        if status:
            q += " AND status=?"
            args.append(status)
        return [dict(r) for r in c.execute(q + " ORDER BY id", args).fetchall()]


# ═════ lượt có công cụ: quét mọi lần thức, đủ hướng dẫn và ngữ cảnh ═════
st, k, clock, eng, box, host, judge = world()
ctx = f"dm:{k}"
AP.ensure_row(st, k, ctx, at=T0)
clock.t = T0 + D + 1
run(tick_all(host))
check("chat riêng, Auto bật: lần thức đầu đã quét (không đợi 3 lần thức)", len(eng.calls) == 1, len(eng.calls))
req = eng.calls[0] if eng.calls else {}
check("lượt quét xin công cụ (tool_turn)", req.get("tool_turn") is True, req)
check("hướng dẫn LẦN TỰ THỨC: toàn quyền, tự hẹn mốc, ngưỡng nhắn cao, gợi ý và nhắc nhở",
      "LẦN TỰ THỨC" in req.get("system", "") and "toàn quyền" in req.get("system", "")
      and "follow_ups" in req.get("system", "") and "reminder" in req.get("system", ""), req.get("system", "")[-600:])
check("khối ngữ cảnh của host vào lời nhắc, kèm lý do thức", "## Giờ hiện tại" in req.get("prompt", "")
      and "Lý do thức lần này" in req.get("prompt", ""), req.get("prompt"))
check("hướng dẫn không có ký tự gạch ngang dài", "\u2014" not in H.TOOL_SCAN_RULES and "\u2013" not in H.TOOL_SCAN_RULES)
clock.t += D + 1
due_now(st, k, ctx, clock.t - 1)
run(tick_all(host))
check("lần thức kế tiếp trong ngày vẫn quét (không còn trần một lần mỗi ngày)", len(eng.calls) == 2, len(eng.calls))
check("sổ lượt: mỗi lượt có công cụ ghi engine thật đã báo", all(
    r["engine"] == "fake" for r in __import__("agent_ledger").CallLedger(st).rows()), "")

# Ngữ cảnh lỗi: vẫn quét bằng công cụ.
st, k, clock, eng, box, host, judge = world(ctx_text=RuntimeError("hỏng"))
ctx = f"dm:{k}"
AP.ensure_row(st, k, ctx, at=T0)
clock.t = T0 + D + 1
run(tick_all(host))
check("khối ngữ cảnh lỗi: lượt vẫn chạy, lời nhắc vẫn có lý do thức", len(eng.calls) == 1
      and "Lý do thức lần này" in eng.calls[0]["prompt"], eng.calls)

# Ngữ cảnh nhóm: giữ lượt chỉ chữ, luật quét giới hạn như T3.
st, k, clock, eng, box, host, judge = world()
ctx = "team:tA"
box["contexts"][k] = [ctx]
AP.ensure_row(st, k, ctx, at=T0)
clock.t = T0 + D + 1
run(tick_all(host))
check("ngữ cảnh nhóm: không có cơ hội thì lần thức đầu không gọi model (lượt chỉ chữ như T3)", eng.calls == [],
      eng.calls)
st, k, clock, eng, box, host, judge = world(tools=lambda key, ctx: False)
ctx = f"dm:{k}"
AP.ensure_row(st, k, ctx, at=T0)
clock.t = T0 + D + 1
run(tick_all(host))
check("tắt lượt có công cụ (JAVIS_PULSE_TOOLS=0): chat riêng về lượt chỉ chữ như T3", eng.calls == [], eng.calls)

# ═════ mốc tự hẹn ═════
st, k, clock, eng, box, host, judge = world()
ctx = f"dm:{k}"
now = T0
got = AP.add_followups(st, k, ctx, [
    {"at": local(now + 5 * 3600), "note": "Kiểm bãi gửi xe trước giải chạy"},
    {"at": local(now + 60), "note": "Quá sớm thì kẹp 10 phút"},
    {"at": local(now + 90 * D), "note": "Quá xa"},
    {"at": "không phải giờ", "note": "Sai dạng"},
], tz=TZ, by="call:1", at=now)
check("mốc theo múi giờ của chủ: 19:00 giờ VN đúng epoch", abs(got["added"][0]["due_at"] - (now + 5 * 3600)) < 60,
      got)
check("mốc quá sớm bị kẹp về 10 phút", abs(got["added"][1]["due_at"] - (now + AP.FOLLOWUP_MIN_S)) < 1, got)
check("mốc quá xa và sai dạng bị bỏ có lý do", got["dropped"] == ["too_far", "bad_time"], got)
dup = AP.add_followups(st, k, ctx, [{"at": local(now + 5 * 3600 + 600), "note": "Kiểm bãi gửi xe trước giải chạy"}],
                       tz=TZ, at=now)
check("mốc trùng (cùng ghi chú, cách dưới 30 phút) bị bỏ", dup["added"] == [] and dup["dropped"] == ["duplicate"], dup)
many = AP.add_followups(st, k, ctx, [{"at": now + (i + 2) * 3600, "note": f"m{i}"} for i in range(5)], at=now)
check("một lượt hẹn tối đa 3 mốc", len(many["added"]) == 3 and many["dropped"] == ["per_scan", "per_scan"], many)
more = AP.add_followups(st, k, ctx, [{"at": now + (i + 20) * 3600, "note": f"n{i}"} for i in range(3)], at=now)
check("mỗi ngữ cảnh giữ tối đa 8 mốc đang chờ", len(more["added"]) == 3 and
      len(followups(st, k, ctx, "pending")) == AP.FOLLOWUP_MAX_PENDING, more)
k2 = st.agent_set_enabled(RS.Principal("owner", "owner", "x"), "a9", True)["agent_key"]
first = followups(st, k, ctx, "pending")[0]["id"]
check("huỷ mốc của ngữ cảnh khác: không có tác dụng", AP.cancel_followups(st, k2, f"dm:{k2}", [first], at=now) == 0)
vf = AP.view(st, k).get("followups") or []
check("khung bảng Nhịp có mốc đang chờ (giờ, ghi chú, ngữ cảnh), xếp theo giờ", len(vf) == AP.FOLLOWUP_MAX_PENDING
      and vf[0]["context_ref"] == ctx and vf == sorted(vf, key=lambda f: f["due_at"]), vf[:2])
check("huỷ mốc của chính mình", AP.cancel_followups(st, k, ctx, [first, "x"], at=now) == 1
      and followups(st, k, ctx)[0]["status"] == "cancelled")

# Lượt quét hẹn mốc, tới giờ thì thức riêng, mốc là cơ hội và đóng khi chạy xong.
text = {"n": 0}


def scripted(req):
    text["n"] += 1
    if text["n"] == 1:
        return ('Đã xem lịch.\n```json\n{"action": "none", "follow_ups": [{"at": "' + local(T0 + D + 3 * 3600) +
                '", "note": "Kiểm lại lịch lấy BIB"}]}\n```')
    return '{"action": "none"}'


st, k, clock, eng, box, host, judge = world(text=scripted)
ctx = f"dm:{k}"
AP.ensure_row(st, k, ctx, at=T0)
clock.t = T0 + D + 1
run(tick_all(host))
fu = followups(st, k, ctx, "pending")
check("lượt quét trả follow_ups: mốc được ghi (kể cả khi action none)", len(fu) == 1
      and fu[0]["note"] == "Kiểm lại lịch lấy BIB" and abs(fu[0]["due_at"] - (T0 + D + 3 * 3600)) < 60, fu)
scan_ev = AP.events(st, k, ctx, kinds=("scan",))[0]
check("sự kiện quét ghi mốc đã hẹn", (scan_ev["payload"]["result"].get("followups") or {}).get("added"), scan_ev)
row = AP.row(st, k, ctx)
check("lịch theo bậc vẫn ở 1 ngày sau (mốc không đổi bậc)", row["next_due_at"] > T0 + 2 * D - 10, row)
clock.t = T0 + D + 3 * 3600 + 5
run(tick_all(host))
check("tới mốc: một lần thức riêng, không đợi lịch theo bậc", len(eng.calls) == 2, len(eng.calls))
check("mốc là lý do của lần thức đó", "followup:" in eng.calls[-1]["prompt"]
      and "Kiểm lại lịch lấy BIB" in eng.calls[-1]["prompt"], eng.calls[-1]["prompt"][-300:])
check("mốc đóng khi lượt quét chạy xong", followups(st, k, ctx)[0]["status"] == "done", followups(st, k, ctx))
clock.t += 60
run(tick_all(host))
check("mốc đã đóng không kích hoạt lại", len(eng.calls) == 2, len(eng.calls))

# Lượt lỗi: mốc đã kích hoạt không gọi lại mỗi nhịp, chờ lần thức theo bậc.
st, k, clock, eng, box, host, judge = world()
ctx = f"dm:{k}"
AP.ensure_row(st, k, ctx, at=T0)
AP.add_followups(st, k, ctx, [{"at": T0 + 3600, "note": "Xem email BTC"}], at=T0)
eng.fail = RuntimeError("engine hỏng")
clock.t = T0 + 3600 + 5
run(tick_all(host))
check("mốc tới giờ: thức và gọi engine", len(eng.calls) == 1, len(eng.calls))
for _ in range(3):
    clock.t += 30
    run(tick_all(host))
check("lượt lỗi: mốc không kích hoạt lại mỗi nhịp", len(eng.calls) == 1, len(eng.calls))
fu = followups(st, k, ctx)
check("lượt lỗi: mốc vẫn chờ (đã đánh dấu kích hoạt)", fu[0]["status"] == "pending" and fu[0]["fired_at"], fu)
eng.fail = None
clock.t = AP.row(st, k, ctx)["next_due_at"] + 1
run(tick_all(host))
check("lần thức theo bậc kế tiếp: mốc còn chờ vẫn là lý do, rồi đóng", len(eng.calls) == 2
      and "Xem email BTC" in eng.calls[-1]["prompt"] and followups(st, k, ctx)[0]["status"] == "done", eng.calls[-1:])

# Bận lúc mốc tới giờ: không ghi gì, nhịp sau mới nhận.
st, k, clock, eng, box, host, judge = world()
ctx = f"dm:{k}"
AP.ensure_row(st, k, ctx, at=T0)
AP.add_followups(st, k, ctx, [{"at": T0 + 3600, "note": "x"}], at=T0)
box["busy"].add(k)
clock.t = T0 + 3600 + 5
run(tick_all(host))
check("bận lúc mốc tới giờ: không thức", eng.calls == [] and followups(st, k, ctx)[0]["fired_at"] is None)
box["busy"].clear()
clock.t += 30
run(tick_all(host))
check("hết bận: nhịp sau thức theo mốc", len(eng.calls) == 1, len(eng.calls))

# Tạm dừng: mốc không kích hoạt.
st, k, clock, eng, box, host, judge = world()
ctx = f"dm:{k}"
AP.ensure_row(st, k, ctx, at=T0)
AP.add_followups(st, k, ctx, [{"at": T0 + 3600, "note": "x"}], at=T0)
AP.set_state(st, k, ctx, "paused", at=T0)
clock.t = T0 + 3600 + 5
run(tick_all(host))
check("tạm dừng: mốc tới giờ không đánh thức", eng.calls == [], eng.calls)

# Lượt quét huỷ mốc của mình.
st, k, clock, eng, box, host, judge = world()
ctx = f"dm:{k}"
AP.ensure_row(st, k, ctx, at=T0)
fid = AP.add_followups(st, k, ctx, [{"at": T0 + 5 * D, "note": "Hết ý nghĩa"}], at=T0)["added"][0]["id"]
eng.text = '{"action": "none", "cancel_follow_ups": [%d]}' % fid
clock.t = T0 + D + 1
run(tick_all(host))
check("lượt quét huỷ mốc qua cancel_follow_ups", followups(st, k, ctx)[0]["status"] == "cancelled",
      followups(st, k, ctx))

# ═════ tin: gợi ý và nhắc nhở; việc đã làm luôn được báo ═════
st, k, clock, eng, box, host, judge = world(
    text='{"action": "say", "kind": "reminder", "text": "Anh ơi, mai 5h45 xuất phát.", "did": ["Thêm lịch lấy BIB"]}')
ctx = f"dm:{k}"
AP.ensure_row(st, k, ctx, at=T0)
clock.t = T0 + D + 1
run(tick_all(host))
check("đã tự làm việc thật: tin gửi KHÔNG qua bộ phán xử", judge.calls == [] and len(box["sent"]) == 1, box["sent"])
meta = box["sent"][0][3] if box["sent"] else {}
check("tin mang loại nhắc nhở và danh sách việc đã làm", meta.get("kind") == "reminder"
      and meta.get("did") == ["Thêm lịch lấy BIB"], meta)
said = AP.events(st, k, ctx, kinds=("said",))
check("sự kiện said ghi loại và việc đã làm", said and said[0]["payload"].get("kind") == "reminder"
      and said[0]["payload"].get("did"), said)
with closing(st._conn()) as c:
    n_pro = c.execute("SELECT COUNT(*) FROM pulse_proactive").fetchone()[0]
check("tin đã gửi vào sổ tin chủ động (để học từ phản hồi)", n_pro == 1)

st, k, clock, eng, box, host, judge = world(text='{"action": "none", "did": ["Trả lời email xác nhận phòng"]}')
ctx = f"dm:{k}"
AP.ensure_row(st, k, ctx, at=T0)
clock.t = T0 + D + 1
run(tick_all(host))
check("đã làm mà chọn none: vẫn báo đúng việc đã làm", len(box["sent"]) == 1
      and "Trả lời email xác nhận phòng" in box["sent"][0][2] and judge.calls == [], box["sent"])

st, k, clock, eng, box, host, judge = world(
    text='{"action": "say", "kind": "suggestion", "text": "Anh xem điều khoản referral trước khi chạy ads."}',
    judge=Judge("silent"))
ctx = f"dm:{k}"
AP.ensure_row(st, k, ctx, at=T0)
clock.t = T0 + D + 1
run(tick_all(host))
check("tin không kèm việc đã làm: qua bộ phán xử, phán im thì không gửi", len(judge.calls) == 1 and box["sent"] == [],
      (judge.calls, box["sent"]))
judge.verdict = "speak"
clock.t += D + 1
due_now(st, k, ctx, clock.t - 1)
run(tick_all(host))
check("phán nói: gửi, mang loại gợi ý", len(box["sent"]) == 1 and box["sent"][0][3].get("kind") == "suggestion"
      and box["sent"][0][3].get("decision_id") == 5, box["sent"])

st, k, clock, eng, box, host, judge = world(text='{"action": "say", "kind": "lạ", "text": "Tin"}')
ctx = f"dm:{k}"
AP.ensure_row(st, k, ctx, at=T0)
clock.t = T0 + D + 1
run(tick_all(host))
check("loại tin lạ thành gợi ý", box["sent"] and box["sent"][0][3].get("kind") == "suggestion", box["sent"])

# ═════ đọc đầu ra ═════
check("đọc khối JSON cuối khi trước đó có chữ và ngoặc nhọn", H.parse_action(
    'Đã xem {email} và lịch.\n```json\n{"action": "say", "text": "a {b}", "follow_ups": [{"at": "2026-11-14 19:00"}]}'
    '\n```') == {"action": "say", "text": "a {b}", "follow_ups": [{"at": "2026-11-14 19:00"}]})
check("không có JSON hợp lệ: None", H.parse_action("Không có gì {đáng} báo") is None)
check("parse_when: chuỗi không múi giờ theo tz, có múi giờ thì giữ", AP.parse_when("2026-11-14 19:00", TZ)
      == datetime(2026, 11, 14, 19, 0, tzinfo=TZ).timestamp() and AP.parse_when("2026-11-14T12:00+00:00", TZ)
      == datetime(2026, 11, 14, 12, 0, tzinfo=timezone.utc).timestamp())
check("say_kind: chỉ nhắc nhở khi nói rõ", H.say_kind("reminder") == "reminder" and H.say_kind("nhắc") == "reminder"
      and H.say_kind("") == "suggestion" and H.say_kind(None) == "suggestion")

# ═════ bộ điều phối thông báo: nhóm gợi ý ═════
notify_policy.STORE = Path(os.environ["JAVIS_STATE_DIR"]) / "notify_policy_test.json"
check("nhóm Gợi ý của trợ lý có trong danh sách nhóm", "suggest" in notify_policy.GROUPS
      and notify_policy.group_name("suggest") in ("Gợi ý của trợ lý", "Assistant suggestions"))
check("nhóm gợi ý mặc định rung từ mức đáng chú ý", notify_policy.mode_of("suggest")["mode"] == "important")
check("gợi ý mức đáng chú ý: rung", notify_policy.decide("suggest", "important", "Gợi ý một", record=False)["verdict"]
      == "loud")
check("nhóm khác giữ mặc định cũ: chỉ tin khẩn", notify_policy.mode_of("agent")["mode"] == notify_policy.DEFAULT_MODE
      == "urgent" and notify_policy.decide("agent", "important", "x", record=False)["verdict"] == "quiet")
check("nhắc nhở của trợ lý (nhóm Nhắc lịch) là tin khẩn", notify_policy.level_of(group="reminder") == "urgent")
notify_policy.set_mode("suggest", "urgent")
check("chủ hạ nhóm gợi ý xuống chỉ tin khẩn: gợi ý thường không rung",
      notify_policy.decide("suggest", "important", "Gợi ý hai", record=False)["verdict"] == "quiet")

if fails:
    print(f"\n{len(fails)} FAIL")
    raise SystemExit(1)
print("\nTẤT CẢ OK")
