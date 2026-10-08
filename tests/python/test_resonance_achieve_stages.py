"""Resonance pilot lần 3: hạn mức chia theo GIAI ĐOẠN cho mục tiêu achieve sửa qua phản hồi (engine giả).

    python tests/run.py resonance_achieve_stages -v

Review đường công cụ (PR #579, điểm 1): trần tổng JAVIS_RESONANCE_CALL_CEILING=2 không biết lượt nào là bản đầu, lượt
nào là bản sửa; bản đầu chưa đạt thì runtime tự hẹn làm lại và tiêu luôn lượt của bản sửa. Bộ chạy lần 3 vì thế đặt trần
TÍCH LUỸ theo giai đoạn: 1 cho tới khi góp ý hợp lệ được nối vào mục tiêu, rồi 2. Sổ không bị đặt lại.

Test này kiểm đúng cơ chế đó trên kho SQLite thật, đường advance thật, engine GIẢ:
- trần 1: bản đầu chưa đạt thì lần đánh thức sau KHÔNG gọi engine lần hai (bị chặn trước lượt gọi), kể cả sau khi
  "khởi động lại" (đối tượng kho mới trên cùng file);
- bản đầu đạt phần tự kiểm thì mục tiêu chờ người dùng, đánh thức lại không gọi model;
- góp ý nối vào mục tiêu (revise_goal, như op=update) rồi nâng trần lên 2: thêm ĐÚNG một lượt, prompt có góp ý và
  bản trước; lần đánh thức sau không gọi thêm.
Không gọi model thật.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import hashlib
import os
import tempfile
from pathlib import Path

_STATE = Path(tempfile.mkdtemp(prefix="javis-res-stages-"))
os.environ["JAVIS_STATE_DIR"] = str(_STATE)

import resonance as R  # noqa: E402
import resonance_store as RS  # noqa: E402

_fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)


DELIV = "Docs/huong-dan-nhan-hang.md"
USER = ("Anh cần một bản hướng dẫn nhận hàng ở kho cho nhân viên mới. Em lo việc này giúp anh tới khi anh thấy dùng "
        "được thì thôi. Lưu ở Docs/huong-dan-nhan-hang.md. Có mục \"Lỗi hay gặp\".")
FEEDBACK = "Bước đối chiếu phiếu giao khó hiểu quá, em thêm một ví dụ cụ thể."
GOOD = "# Hướng dẫn nhận hàng\n\n1. Đếm số kiện.\n2. Đối chiếu phiếu giao.\n\n## Lỗi hay gặp\n\n- Ký trước khi đếm.\n"
BAD = "# Hướng dẫn nhận hàng\n\n1. Đếm số kiện.\n"
REVISED = GOOD + "\nVí dụ đối chiếu: phiếu ghi 10 thùng mã A12, thực nhận 9 thì ghi thiếu 1 cạnh chữ ký.\n"


class Clock:
    def __init__(self, t=1_800_000_000.0):
        self.t = t

    def __call__(self):
        return self.t


class FakeEngine:
    def __init__(self, texts):
        self.texts, self.queries, self.prompts, self.max_wall_s = list(texts), 0, [], None

    def is_available(self):
        return True

    async def query(self, prompt):
        self.queries += 1
        self.prompts.append(prompt)
        text = self.texts[min(self.queries - 1, len(self.texts) - 1)]
        yield {"type": "final", "content": text, "tokens_in": 10, "tokens_out": 20}


class FakeEvidence:
    def __init__(self):
        self.items = {}

    def put(self, goal, action_id, text, metadata):
        eid = f"ev_{len(self.items) + 1}"
        self.items[eid] = {"text": text, "content_hash": hashlib.sha256(text.encode("utf-8")).hexdigest()}
        return eid

    def valid(self, evidence_id):
        return self.items.get(evidence_id)


# MỘT kho bằng chứng giả dùng chung: id bằng chứng phải duy nhất như EvidenceStore thật, kho mới mỗi lần sẽ cấp
# trùng id và lần gắn thứ hai bị bỏ qua.
EVIDENCE = FakeEvidence()


async def _notes(goal, kind, text, card=""):
    return True


def world(name):
    """Một kho và một brain riêng: trần là trần TỔNG trên cả kho, hai ca không được tiêu chung."""
    brain = Path(tempfile.mkdtemp(prefix=f"brain-{name}-")).resolve()
    (brain / "Javis").mkdir(parents=True)
    (brain / "Javis" / "resonance.json").write_text('{"enabled": true}', encoding="utf-8")
    return str(brain), _STATE / f"{name}.sqlite3"


def make_goal(brain, db, mid=1):
    store = RS.GoalStore(db)
    p = RS.Principal("agent", "javis", brain)
    deps0 = R.GoalDeps(engine_factory=lambda s, t: (None, {"blocked": "không gọi"}), budget=R.CallBudget(0),
                       store=store)
    prop = {"understanding": "Bản hướng dẫn nhận hàng cho nhân viên mới, sửa theo góp ý tới khi anh dùng được",
            "criteria": [{"description": "Bản hướng dẫn có mục Lỗi hay gặp", "evaluator": "artifact_contract",
                          "params": {"path": DELIV, "must_contain": ["Lỗi hay gặp"]}},
                         {"description": "Anh xác nhận bản hướng dẫn dùng được", "evaluator": "human_confirmation"}],
            "relevant_quote": "Em lo việc này giúp anh tới khi anh thấy dùng được thì thôi",
            "horizon": {"kind": "review", "at_iso": "2027-01-20T09:00:00+07:00"}, "stage": "delivery",
            "mode": "achieve"}
    g = asyncio.run(R.form_goal(R.message_ref("s-stages", mid), {
        "principal": p, "brain_root": brain, "session_id": "s-stages", "message_id": mid, "user_text": USER,
        "constraints": [], "budget_calls": 4, "proposal": prop}, deps0))
    return g, p


def deps_for(brain, db, eng, clock):
    def _factory(system_prompt, tag):
        return eng, {"provider": "fake", "model": "fake-1", "text_only": True}
    return R.GoalDeps(engine_factory=_factory, budget=R.CallBudget(0), clock=clock, store=RS.GoalStore(db),
                      principal=RS.Principal("agent", "javis", brain), brain_root=brain, evidence=EVIDENCE,
                      notify=_notes)


def adv(gid, deps, kind="wake"):
    return asyncio.run(R.advance(gid, {"kind": kind}, deps))


def ledger_used(db):
    import sqlite3
    c = sqlite3.connect(str(db))
    n = int(c.execute("SELECT COALESCE(SUM(calls_used),0) FROM goals").fetchone()[0])
    c.close()
    return n


def ceiling(n):
    os.environ["JAVIS_RESONANCE_CALL_CEILING"] = str(n)


# ═══════════ Ca 1: bản đầu CHƯA đạt, trần giai đoạn 1 chặn lượt làm lại ═══════════
b1, db1 = world("retry")
g1, p1 = make_goal(b1, db1)
ceiling(1)
clk1 = Clock()
e1 = FakeEngine([BAD, GOOD])
a = adv(g1.id, deps_for(b1, db1, e1, clk1), "start")
check("trần 1: bản đầu một lượt engine, thiếu mục bắt buộc nên not_met", e1.queries == 1 and a.verdict == "not_met")
check("runtime tự hẹn làm lại (đúng rủi ro review nêu)",
      any(w["kind"] == "work" for w in RS.GoalStore(db1).wakes(p1, g1.id)))
clk1.t += 7 * 24 * 3600
adv(g1.id, deps_for(b1, db1, e1, clk1))
check("trần 1: lần đánh thức làm lại KHÔNG gọi engine lần hai", e1.queries == 1 and ledger_used(db1) == 1)
check("trần 1: mục tiêu bị chặn vì hết hạn mức, không còn lịch làm việc",
      (RS.GoalStore(db1).run_state(p1, g1.id) or {}).get("block_reason") == "budget"
      and not any(w["kind"] == "work" for w in RS.GoalStore(db1).wakes(p1, g1.id)))
clk1.t += 3600
adv(g1.id, deps_for(b1, db1, e1, clk1))          # kho mới trên cùng file: như server dựng lại
check("trần 1, sau khi dựng lại kho: vẫn không gọi thêm, sổ giữ nguyên", e1.queries == 1 and ledger_used(db1) == 1)

# ═══════════ Ca 2: đường thuận lợi, bản đầu, chờ người dùng, góp ý, bản sửa ═══════════
b2, db2 = world("happy")
g2, p2 = make_goal(b2, db2)
ceiling(1)
clk2 = Clock()
e2 = FakeEngine([GOOD, REVISED, REVISED])
a = adv(g2.id, deps_for(b2, db2, e2, clk2), "start")
st = RS.GoalStore(db2)
check("bản đầu: một lượt, tự kiểm đạt, chờ người dùng xác nhận",
      e2.queries == 1 and a.verdict == "unknown"
      and (st.run_state(p2, g2.id) or {}).get("block_reason") == "human_confirmation")
draft1 = (Path(b2) / DELIV).read_bytes()
clk2.t += 3600
adv(g2.id, deps_for(b2, db2, e2, clk2))
check("đang chờ người dùng: đánh thức lại không gọi model", e2.queries == 1 and ledger_used(db2) == 1)

# Góp ý đến trong lượt chat (như javis_goal op=update): đổi một trường thật, nối ý định vào chuỗi.
g_prev = st.get(p2, g2.id)
g_new, relation, kept = R.revise_goal(st, p2, g2.id, g_prev.revision,
                                      {"constraints": ["Bước đối chiếu phiếu giao có một ví dụ cụ thể"],
                                       "relevant_quote": "em thêm một ví dụ cụ thể"},
                                      {"message_ref": R.message_ref("s-stages", 2), "session_id": "s-stages",
                                       "message_id": 2, "user_text": FEEDBACK, "constraints": [],
                                       "user_unsure": False, "reason": "góp ý của người dùng"})
check("góp ý: cùng mục tiêu, revision tăng đúng 1", g_new.id == g2.id and g_new.revision == g_prev.revision + 1
      and relation != "none")
it = st.get_intent(p2, g_new.intent_id) or {}
check("góp ý: ý định mới là lời góp ý, nối về ý định trước",
      it.get("text") == FEEDBACK and it.get("prev_intent_id") == g_prev.intent_id)
check("góp ý: giữ tiêu chí người dùng xác nhận và đường dẫn sản phẩm",
      any(c.get("evaluator") == "human_confirmation" for c in g_new.criteria) and R._deliverable_rel(g_new) == DELIV)
check("góp ý: có lịch làm lại cho revision mới", any(w["kind"] == "work" for w in st.wakes(p2, g2.id)))

# Chuyển giai đoạn: nâng trần TÍCH LUỸ lên 2, không đặt lại sổ. Trong bộ chạy, lượt chat góp ý chạy trên server có
# nhịp TẠM DỪNG, nên lịch làm lại chưa bị ai nhận trước khi server giai đoạn 2 lên. Nếu nhịp chạy với trần 1 thì lịch
# đó bị chặn vì hạn mức (như ca 1) và giai đoạn 2 không tự đi tiếp: bộ chạy không được sửa kho để gỡ.
ceiling(2)
clk2.t += 60
adv(g2.id, deps_for(b2, db2, e2, clk2))
check("giai đoạn 2 (trần 2): thêm ĐÚNG một lượt cho bản sửa", e2.queries == 2 and ledger_used(db2) == 2)
p_rev = e2.prompts[-1] if e2.prompts else ""
check("prompt bản sửa có lời góp ý và bản trước", FEEDBACK in p_rev and "Đối chiếu phiếu giao" in p_rev)
check("bản sửa thay bản đầu trên đĩa", (Path(b2) / DELIV).read_bytes() != draft1)
check("bản sửa: lại chờ người dùng xác nhận",
      (st.run_state(p2, g2.id) or {}).get("block_reason") == "human_confirmation")
clk2.t += 3600
adv(g2.id, deps_for(b2, db2, e2, clk2))
check("giai đoạn 2: đánh thức lại không gọi thêm (tổng 2)", e2.queries == 2 and ledger_used(db2) == 2)
check("giai đoạn 2: lượt thứ ba không giữ được chỗ trước lượt gọi", RS.GoalStore(db2).begin_action(
    p2, g2.id, st.get(p2, g2.id).revision, "work", lease_until=clk2() + 60, now=clk2()) is None)

# ═══════════ Sổ lượt chat của bộ chạy ═══════════
import sys  # noqa: E402
sys.path.insert(0, str(Path(__file__).parent))
import _e2e_pilot_guard as G  # noqa: E402

lp = _STATE / "chat-turns.json"
L = G.TurnLedger(lp, 2)
check("sổ chat: giữ chỗ lượt 1", L.reserve("s1"))


def _send_that_times_out():
    raise TimeoutError("hết giờ")


try:
    _send_that_times_out()
except TimeoutError:
    L.settle("s1", "timeout")
check("sổ chat: lượt hết giờ vẫn được tính", L.used() == 1 and L.entries()[0]["status"] == "timeout")
check("sổ chat: không giữ lại cùng lượt (không thử lại)", not L.reserve("s1"))
check("sổ chat: đối tượng mới đọc lại đúng số đã giữ", G.TurnLedger(lp, 2).used() == 1)
check("sổ chat: giữ được lượt 2", G.TurnLedger(lp, 2).reserve("s4"))
check("sổ chat: hết chỗ thì từ chối lượt thứ ba", not G.TurnLedger(lp, 2).reserve("s7"))

os.environ.pop("JAVIS_RESONANCE_CALL_CEILING", None)
print(f"\n{'FAIL' if _fails else 'OK'}: {len(_fails)} lỗi")
raise SystemExit(1 if _fails else 0)
