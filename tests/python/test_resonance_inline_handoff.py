"""Resonance: tiếp nhận bản bộ não viết trong lượt chat (review pilot lần 3, review mã bàn giao). Kho SQLite thật, engine
GIẢ, mapper SDK thật cho sự kiện công cụ.

    python tests/run.py resonance_inline_handoff -v

Pilot lần 3: bộ não Write bản đầu rồi lập mục tiêu; việc nền vẫn tiêu một lượt viết lại, không đăng được, thẻ trỏ bản
chat còn receipt mô tả bản việc nền. Sửa:
- biên nhận ghi do host lập: lời gọi Write chỉ là ứng viên, chỉ kết quả THÀNH CÔNG đúng id mới xác nhận; công cụ không
  chắc là chỉ đọc gọi sau Write làm Write đó mất hiệu lực (P1-1 của review mã);
- bàn giao có TRẠNG THÁI trong kho, không dựa vào thời gian: việc nền chỉ làm khi lượt chat đã bàn giao, không còn chạy,
  hay tiến trình sở hữu đã chết; bàn giao muộn sau khi việc nền nhận quyền bị từ chối; đầu ra cũ không đăng đè bản tiếp
  nhận mới hơn (P1-2).
Thiết kế: docs/dev/resonance-inline-artifact-handoff.md. Không gọi model thật.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import hashlib
import os
import sqlite3
import tempfile
from pathlib import Path

_STATE = Path(tempfile.mkdtemp(prefix="javis-res-handoff-"))
os.environ["JAVIS_STATE_DIR"] = str(_STATE)
os.environ.pop("JAVIS_RESONANCE_CALL_CEILING", None)

import claude_sdk_engine  # noqa: E402
import luot_dang_chay  # noqa: E402
import resonance as R  # noqa: E402
import resonance_store as RS  # noqa: E402
import _resonance_agent as RA  # noqa: E402  - A1: Cộng hưởng bật theo trợ lý
from claude_agent_sdk import AssistantMessage, ToolResultBlock, ToolUseBlock, UserMessage  # noqa: E402

_fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)


DELIV = "Docs/huong-dan.md"
USER = "Em lo giúp anh bản hướng dẫn nhận hàng tới khi anh thấy dùng được thì thôi. Lưu ở Docs/huong-dan.md."
FEEDBACK = "Bước đối chiếu khó hiểu quá, em thêm một ví dụ cụ thể."
A = "# Hướng dẫn\n\n1. Đếm kiện.\n2. Đối chiếu phiếu.\n\n## Lỗi hay gặp\n\n- Ký trước khi đếm.\n"
A2 = A + "\nVí dụ: phiếu ghi 10 thùng, đếm được 9 thì ghi thiếu 1.\n"
BAD = "# Hướng dẫn\n\n1. Đếm kiện.\n"
WORKER = A + "\nBản việc nền.\n"


class Clock:
    def __init__(self, t=1_800_000_000.0):
        self.t = t

    def __call__(self):
        return self.t


class FakeEngine:
    def __init__(self, text=WORKER):
        self.text, self.queries, self.prompts, self.max_wall_s = text, 0, [], None

    def is_available(self):
        return True

    async def query(self, prompt):
        self.queries += 1
        self.prompts.append(prompt)
        yield {"type": "final", "content": self.text, "tokens_in": 10, "tokens_out": 20}


class FakeEvidence:
    def __init__(self):
        self.items, self.fail = {}, False

    def put(self, goal, action_id, text, metadata):
        if self.fail:
            raise RuntimeError("evidence_encryption_unavailable")
        eid = f"ev_{len(self.items) + 1}"
        self.items[eid] = {"text": text, "content_hash": hashlib.sha256(text.encode("utf-8")).hexdigest()}
        return eid

    def valid(self, evidence_id):
        return self.items.get(evidence_id)


EVIDENCE = FakeEvidence()


async def _notes(goal, kind, text, card=""):
    return True


_n = {"mid": 0, "call": 0}


def world(name):
    brain = Path(tempfile.mkdtemp(prefix=f"brain-{name}-")).resolve()
    (brain / "Javis").mkdir(parents=True)
    store = RS.GoalStore(_STATE / f"{name}.sqlite3")
    RA.enable(store, brain)       # A1: mục tiêu thuộc một trợ lý đang bật trong kho của thế giới này
    return str(brain), store, RS.Principal("agent", "javis", str(brain))


def deps_for(brain, store, eng, clock):
    def _factory(system_prompt, tag):
        return eng, {"provider": "fake", "model": "fake-1", "text_only": True}
    return R.GoalDeps(engine_factory=_factory, budget=R.CallBudget(0), clock=clock, store=store,
                      principal=RS.Principal("agent", "javis", brain), brain_root=brain, evidence=EVIDENCE,
                      notify=_notes)


def mref():
    _n["mid"] += 1
    return _n["mid"], R.message_ref("s-hand", _n["mid"])


def proposal(**kw):
    p = {"understanding": "Bản hướng dẫn nhận hàng, sửa theo góp ý tới khi anh dùng được",
         "criteria": [{"description": "Có mục Lỗi hay gặp", "evaluator": "artifact_contract",
                       "params": {"path": DELIV, "must_contain": ["Lỗi hay gặp"]}},
                      {"description": "Anh xác nhận dùng được", "evaluator": "human_confirmation"}],
         "relevant_quote": "Em lo giúp anh bản hướng dẫn nhận hàng",
         "horizon": {"kind": "review", "at_iso": "2027-01-20T09:00:00+07:00"}, "stage": "delivery", "mode": "achieve"}
    p.update(kw)
    return p


def create(brain, store, p, clock, mid, ref):
    deps0 = R.GoalDeps(engine_factory=lambda s, t: (None, {"blocked": "không gọi"}), budget=R.CallBudget(0),
                       store=store)
    return asyncio.run(R.form_goal(ref, {
        "principal": p, "brain_root": brain, "session_id": "s-hand", "message_id": mid, "user_text": USER,
        "constraints": [], "budget_calls": 4, "proposal": proposal(),
        "hold_until": clock() + R.HANDOFF_HOLD_S, **RA.ctx(store.agent(brain, RA.SLUG))}, deps0))


def revise(store, p, gid, rev, clock, mid, ref, text=FEEDBACK):
    return R.revise_goal(store, p, gid, rev, {"constraints": ["Có ví dụ"], "relevant_quote": "em thêm một ví dụ"},
                         {"message_ref": ref, "session_id": "s-hand", "message_id": mid, "user_text": text,
                          "constraints": [], "user_unsure": False, "reason": "góp ý",
                          "hold_until": clock() + R.HANDOFF_HOLD_S,
                          **RA.ctx(store.agent(p.brain_id, RA.SLUG))})[0]


def sdk_events(blocks_msgs):
    """Sự kiện công cụ đi qua mapper SDK THẬT (claude_sdk_engine.map_message), như nhánh Claude trong main."""
    out = []
    for m in blocks_msgs:
        out += claude_sdk_engine.map_message(m)[0]
    return out


def feed(ref, brain, events):
    return [R.note_turn_event(ref, brain, e) for e in events]


def call_id():
    _n["call"] += 1
    return f"toolu_{_n['call']}"


def write_msgs(brain, rel, content, ok=True, result=True, other_id=False):
    cid = call_id()
    msgs = [AssistantMessage(content=[ToolUseBlock(id=cid, name="Write",
                                                   input={"file_path": str(Path(brain) / rel), "content": content})],
                             model="fake")]
    if result:
        msgs.append(UserMessage(content=[ToolResultBlock(tool_use_id=("other" if other_id else cid),
                                                         content="File created" if ok else "Permission denied",
                                                         is_error=not ok)]))
    return msgs


def tool_msgs(name, inp):
    cid = call_id()
    return [AssistantMessage(content=[ToolUseBlock(id=cid, name=name, input=inp)], model="fake"),
            UserMessage(content=[ToolResultBlock(tool_use_id=cid, content="ok", is_error=False)])]


def put_file(brain, rel, content, crlf=False):
    f = Path(brain) / rel
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_bytes((content.replace("\n", "\r\n") if crlf else content).encode("utf-8"))
    return f


def adv(gid, deps, kind="wake"):
    return asyncio.run(R.advance(gid, {"kind": kind}, deps))


def rs(store, p, gid):
    return store.run_state(p, gid) or {}


def wake_due(store, p, gid):
    w = [x for x in store.wakes(p, gid) if x["kind"] == "work"]
    return w[0]["due_at"] if w else None


def adopted(store, p, gid):
    return [e for e in store.events(p, gid) if e["kind"] == "artifact_adopted"]


def scenario(name, msgs, file_text=None, crlf=False):
    """Một lượt: sự kiện công cụ qua mapper thật, file trên đĩa, rồi lập mục tiêu và bàn giao. Trả (trạng thái, ...)."""
    b, st, P = world(name)
    clk = Clock()
    mid, ref = mref()
    feed(ref, b, sdk_events(msgs(b)))
    if file_text is not None:
        put_file(b, DELIV, file_text, crlf)
    g = create(b, st, P, clk, mid, ref)
    eng = FakeEngine()
    deps = deps_for(b, st, eng, clk)
    return R.handoff_after_turn(g.id, ref, deps), b, st, P, clk, g, eng, deps


# ═══════════ Mapper SDK giữ id lời gọi và cờ lỗi ═══════════
_ev = sdk_events(write_msgs("/brain", DELIV, A, ok=False))
check("mapper SDK: lời gọi mang id, kết quả mang tool_use_id và is_error",
      _ev[0]["type"] == "tool_call" and _ev[0]["id"] and _ev[1]["tool_use_id"] == _ev[0]["id"]
      and _ev[1]["is_error"] is True)

# ═══════════ 1. Write thành công rồi lập mục tiêu: tiếp nhận, không gọi việc nền ═══════════
st_, b, st, P, clk, g, eng, deps = scenario("c1", lambda b: write_msgs(b, DELIV, A), A, crlf=True)
check("1 Write có kết quả thành công đúng id: tiếp nhận (khớp sau khi chuẩn hoá xuống dòng)", st_ == "adopted")
data = (Path(b) / DELIV).read_bytes()
ev = adopted(st, P, g.id)
check("1 sự kiện artifact_adopted: đúng file, hash BYTES THẬT, tin nhắn",
      len(ev) == 1 and ev[0]["payload"]["path"] == DELIV and ev[0]["payload"]["sha256"] == R._sha(data))
check("1 mốc đăng nguồn chat bằng hash bytes thật", (st.published(P, g.id, DELIV) or {}).get("sha256") == R._sha(data)
      and str((st.published(P, g.id, DELIV) or {}).get("action_id")).startswith("chat:"))
check("1 bàn giao xong, lịch nhả về ngay", (st.handoff(P, g.id, g.revision) or {}).get("status") == "done"
      and (wake_due(st, P, g.id) or 1e18) <= clk())
a = adv(g.id, deps)
check("1 đánh giá: KHÔNG gọi việc nền, chờ người dùng xác nhận",
      eng.queries == 0 and rs(st, P, g.id).get("block_reason") == "human_confirmation")
check("1 không có receipt việc nền giả", not [x for x in st.actions(P, g.id) if x["kind"] == "work"])
check("1 thẻ trỏ đúng bản chat", R._artifact_ref_of(st, P, st.get(P, g.id), b) == R._sha(data))
_, ref1 = [(e["revision"], e["message_ref"]) for e in st.events(P, g.id) if e["kind"] == "created"][0]
check("1 bàn giao lặp: không tiếp nhận lần hai", R.handoff_after_turn(g.id, ref1, deps) != "adopted"
      and len(adopted(st, P, g.id)) == 1)
G1 = (b, st, P, clk, g, eng, deps)

# ═══════════ P1-1: chỉ Write THÀNH CÔNG đúng lời gọi mới là biên nhận ═══════════
check("P1-1 Write lỗi (Permission denied), file cũ trùng nội dung: KHÔNG tiếp nhận, không mốc thay file",
      scenario("p11a", lambda b: write_msgs(b, DELIV, A, ok=False), A)[0] == "no_receipt")
r = scenario("p11b", lambda b: write_msgs(b, DELIV, A, result=False), A)
check("P1-1 Write không có kết quả: không tiếp nhận", r[0] == "no_receipt" and r[2].published(r[3], r[5].id, DELIV) is None)
check("P1-1 kết quả của lời gọi khác: không tiếp nhận",
      scenario("p11c", lambda b: write_msgs(b, DELIV, A, other_id=True), A)[0] == "no_receipt")
check("P1-1 Write thành công rồi Bash: Write mất hiệu lực",
      scenario("p11d", lambda b: write_msgs(b, DELIV, A) + tool_msgs("Bash", {"command": "echo"}), A)[0]
      == "no_receipt")
check("P1-1 Write rồi Edit rồi nội dung hoàn lại như cũ: vẫn KHÔNG tiếp nhận (hash không bắt được)",
      scenario("p11e", lambda b: write_msgs(b, DELIV, A) + tool_msgs("Edit", {"file_path": str(Path(b) / DELIV)}),
               A)[0] == "no_receipt")
check("P1-1 shell chạy nền ở bất kỳ đâu trong lượt: cả lượt không tiếp nhận",
      scenario("p11f", lambda b: tool_msgs("Bash", {"command": "sleep 1", "run_in_background": True})
               + write_msgs(b, DELIV, A), A)[0] == "no_receipt")
check("P1-1 Bash TRƯỚC Write (xem thư mục): Write sau vẫn là biên nhận",
      scenario("p11g", lambda b: tool_msgs("Bash", {"command": "ls"}) + write_msgs(b, DELIV, A), A)[0] == "adopted")
check("P1-1 Write rồi ToolSearch, javis_goal (chỉ đọc hay lập mục tiêu, như pilot lần 3): vẫn tiếp nhận",
      scenario("p11h", lambda b: write_msgs(b, DELIV, A) + tool_msgs("ToolSearch", {"query": "x"})
               + tool_msgs("mcp__javis-plugins__javis_goal", {"op": "create"}), A)[0] == "adopted")
check("P1-1 Write thành công, Write sau cùng file bị lỗi: bản thành công trước vẫn là biên nhận",
      scenario("p11i", lambda b: write_msgs(b, DELIV, A) + write_msgs(b, DELIV, A2, ok=False), A)[0] == "adopted")
check("P1-1 Write thành công nhưng file bị sửa ngoài công cụ: không tiếp nhận",
      scenario("p11j", lambda b: write_msgs(b, DELIV, A), A.replace("Đếm kiện", "Đếm kiện kỹ"))[0]
      == "changed_after_write")
check("vòng 2 P1-1 MCP mang đuôi Write (mcp__remote__Write) báo thành công, không có lần ghi local: KHÔNG tiếp nhận",
      scenario("r2a", lambda b: [AssistantMessage(content=[ToolUseBlock(
          id="remote-write", name="mcp__remote__Write",
          input={"file_path": str(Path(b) / DELIV), "content": A})], model="fake"),
          UserMessage(content=[ToolResultBlock(tool_use_id="remote-write", content="Remote record accepted",
                                               is_error=False)])], A)[0] == "no_receipt")
check("vòng 2 P1-1 Write gốc rồi MCP lạ mang đuôi Read (mcp__untrusted__Read): Write mất hiệu lực",
      scenario("r2b", lambda b: write_msgs(b, DELIV, A)
               + tool_msgs("mcp__untrusted__Read", {"file_path": str(Path(b) / DELIV)}), A)[0] == "no_receipt")
check("vòng 2 P1-1 đối chứng: Write gốc rồi đúng tool Javis đã biết (mcp__javis__javis_read_file): vẫn tiếp nhận",
      scenario("r2c", lambda b: write_msgs(b, DELIV, A)
               + tool_msgs("mcp__javis__javis_read_file", {"path": DELIV}), A)[0] == "adopted")
check("P1-1 javis_write_file (chưa có kết quả ghi gắn đúng lời gọi): không lập biên nhận",
      R.note_turn_event("msg:x:1", b, {"type": "tool_call", "name": "javis_write_file", "id": "c",
                                       "input": {"path": DELIV, "content": A}}) != "candidate")
check("P1-1 Write ra ngoài brain: bỏ qua, không lập biên nhận",
      R.note_turn_event("msg:x:2", b, {"type": "tool_call", "name": "Write", "id": "c",
                                       "input": {"file_path": str(_STATE / "x.md"), "content": "x"}}) == "ignored")
R.drop_turn_writes("msg:x:1")
R.drop_turn_writes("msg:x:2")

# ═══════════ P1-2: bàn giao có trạng thái, không dựa vào thời gian ═══════════
b, st, P = world("p12")
clk = Clock()
mid, ref = mref()
k = luot_dang_chay.bat_dau("web:s-hand", b, msg_id=mid, user_text=USER)
feed(ref, b, sdk_events(write_msgs(b, DELIV, A)))
put_file(b, DELIV, A)
g = create(b, st, P, clk, mid, ref)
eng = FakeEngine()
deps = deps_for(b, st, eng, clk)
clk.t += R.HANDOFF_HOLD_S + 1
asyncio.run(R.tick(st, clk(), lambda bid: deps))
check("P1-2 quá 900 giây mà lượt chat VẪN CHẠY: tick thật không gọi việc nền", eng.queries == 0
      and (st.handoff(P, g.id, g.revision) or {}).get("status") == "pending")
check("P1-2 lúc chờ: lịch được đánh thức lại sau HANDOFF_POLL_S", (wake_due(st, P, g.id) or 0) == clk() + R.HANDOFF_POLL_S)
check("P1-2 lượt chat bàn giao (vẫn đang chạy): tiếp nhận", R.handoff_after_turn(g.id, ref, deps) == "adopted")
luot_dang_chay.ket_thuc(k)
clk.t += 60
asyncio.run(R.tick(st, clk(), lambda bid: deps))
check("P1-2 sau bàn giao: chờ người dùng, 0 lượt việc nền", eng.queries == 0
      and rs(st, P, g.id).get("block_reason") == "human_confirmation")
# Vòng 2 P2-1: lượt chat còn sống quá ba giờ (mục đoán người giao việc bị dọn theo tuổi) vẫn giữ quyền.
b, st, P = world("p12l")
clk = Clock()
mid, ref = mref()
k = luot_dang_chay.bat_dau("web:s-hand", b, msg_id=mid, user_text=USER)
feed(ref, b, sdk_events(write_msgs(b, DELIV, A)))
put_file(b, DELIV, A)
g = create(b, st, P, clk, mid, ref)
luot_dang_chay._DANG[k]["at"] -= 4 * 3600
luot_dang_chay.doan_chat_id(b)               # dọn mục đoán quá tuổi, như mọi lần tool hỏi người giao việc
eng = FakeEngine()
deps = deps_for(b, st, eng, clk)
clk.t += R.HANDOFF_HOLD_S + 1
asyncio.run(R.tick(st, clk(), lambda bid: deps))
check("vòng 2 P2-1 lượt chat còn sống sau ba giờ: KHÔNG mất quyền, việc nền không chạy",
      k not in luot_dang_chay._DANG and eng.queries == 0
      and (st.handoff(P, g.id, g.revision) or {}).get("status") == "pending")
check("vòng 2 P2-1 bàn giao của lượt vẫn sống được nhận", R.handoff_after_turn(g.id, ref, deps) == "adopted")
luot_dang_chay.ket_thuc(k)
check("vòng 2 P2-1 lượt kết thúc thật: sổ sống gỡ đúng lượt", not luot_dang_chay.dang_chay("web:s-hand", mid))

# Lượt chat kết thúc mà KHÔNG bàn giao (lỗi giữa lượt): quyền chuyển cho việc nền; bàn giao muộn bị từ chối.
b, st, P = world("p12b")
clk = Clock()
mid, ref = mref()
k = luot_dang_chay.bat_dau("web:s-hand", b, msg_id=mid, user_text=USER)
feed(ref, b, sdk_events(write_msgs(b, DELIV, A)))
put_file(b, DELIV, A)
g = create(b, st, P, clk, mid, ref)
luot_dang_chay.ket_thuc(k)
eng = FakeEngine()
deps = deps_for(b, st, eng, clk)
clk.t += R.HANDOFF_HOLD_S + 1
asyncio.run(R.tick(st, clk(), lambda bid: deps))
check("P1-2 lượt đã kết thúc không bàn giao: quyền chuyển cho việc nền (expired), việc nền chạy",
      eng.queries == 1 and (st.handoff(P, g.id, g.revision) or {}).get("status") == "expired")
check("P1-2 bản việc nền không đè file chưa tiếp nhận", (Path(b) / DELIV).read_text(encoding="utf-8") == A)
check("P1-2 bàn giao đến MUỘN sau khi việc nền nhận quyền: bị từ chối, không tiếp nhận, không mốc",
      R.handoff_after_turn(g.id, ref, deps) == "handoff_expired" and not adopted(st, P, g.id)
      and st.published(P, g.id, DELIV) is None)
clk.t += 3600
adv(g.id, deps)
check("P1-2 lần chạy kế tiếp: đầu ra việc nền cũ KHÔNG đè bản chat", (Path(b) / DELIV).read_text(encoding="utf-8") == A)
# Tiến trình sở hữu đã chết (khởi động lại): không chờ lượt chat của tiến trình cũ.
b, st, P = world("p12c")
clk = Clock()
mid, ref = mref()
k = luot_dang_chay.bat_dau("web:s-hand", b, msg_id=mid, user_text=USER)
g = create(b, st, P, clk, mid, ref)
_boot = R.BOOT_ID
R.BOOT_ID = "tien-trinh-moi"
eng = FakeEngine()
deps = deps_for(b, st, eng, clk)
clk.t += R.HANDOFF_HOLD_S + 1
asyncio.run(R.tick(st, clk(), lambda bid: deps))
check("P1-2 khởi động lại (BOOT_ID khác): bàn giao của tiến trình cũ hết hiệu lực, việc nền chạy",
      eng.queries == 1 and (st.handoff(P, g.id, g.revision) or {}).get("status") == "expired")
R.BOOT_ID = _boot
luot_dang_chay.ket_thuc(k)
# Phòng thủ thêm: đầu ra việc nền CŨ hơn một bản tiếp nhận không được đăng đè.
b, st, P = world("p12d")
clk = Clock()
mid, ref = mref()
put_file(b, DELIV, A)
deps0 = R.GoalDeps(engine_factory=lambda s, t: (None, {}), budget=R.CallBudget(0), store=st)
g = asyncio.run(R.form_goal(ref, {"principal": P, "brain_root": b, "session_id": "s-hand", "message_id": mid,
                                  "user_text": USER, "constraints": [], "budget_calls": 4, "proposal": proposal(),
                                  **RA.ctx(st.agent(b, RA.SLUG))}, deps0))
eng = FakeEngine()
deps = deps_for(b, st, eng, clk)
adv(g.id, deps)          # việc nền chạy, xung đột với file có sẵn: đầu ra nằm ở vùng làm việc
st.link_evidence(P, g.id, g.revision, "chat:x", "ev_y", "chat_output", R._sha(A.encode()))
_c = sqlite3.connect(str(_STATE / "p12d.sqlite3"))
_c.execute("UPDATE evidence_links SET created_at=? WHERE kind='chat_output'", (9e18,))
_c.execute("INSERT OR REPLACE INTO published VALUES(?,?,?,?,?)", (g.id, DELIV, R._sha(A.encode()), "chat:x", 0))
_c.commit()
_c.close()
check("P1-2 đầu ra việc nền cũ hơn bản tiếp nhận: _publish_latest không đăng đè",
      R._publish_latest(st.get(P, g.id), deps, clk())["status"] == "superseded"
      and (Path(b) / DELIV).read_text(encoding="utf-8") == A)

# ═══════════ 3. Không tự cấp quyền thay file ═══════════
r = scenario("c3a", lambda b: [], A)
check("3a file có sẵn, lượt này không Write: không tiếp nhận", r[0] == "no_receipt")
adv(r[5].id, r[7])
check("3a việc nền chạy như cũ, không ghi đè, báo đúng nguyên nhân (had_baseline=False)",
      r[6].queries == 1 and (Path(r[1]) / DELIV).read_text(encoding="utf-8") == A
      and any(x["kind"] == "goal.publish_conflict" and x["payload"].get("had_baseline") is False
              for x in r[2].outbox_pending(200) if x["goal_id"] == r[5].id))
b, st, P = world("c3b")
clk = Clock()
_, ref_other = mref()
feed(ref_other, b, sdk_events(write_msgs(b, DELIV, A)))
put_file(b, DELIV, A)
mid, ref = mref()
g = create(b, st, P, clk, mid, ref)
check("3b biên nhận của lượt khác không dùng cho lượt này",
      R.handoff_after_turn(g.id, ref, deps_for(b, st, FakeEngine(), clk)) == "no_receipt")
R.drop_turn_writes(ref_other)
EVIDENCE.fail = True
r = scenario("c3e", lambda b: write_msgs(b, DELIV, A), A)
EVIDENCE.fail = False
check("3e không lưu được bằng chứng: không tiếp nhận, không mốc đăng",
      r[0] == "evidence_failed" and r[2].published(r[3], r[5].id, DELIV) is None and not adopted(r[2], r[3], r[5].id))

# ═══════════ 4. Bản chat chưa đạt: việc nền sửa TỪ bản đó; tạm dừng, tắt tính năng ═══════════
r = scenario("c4", lambda b: write_msgs(b, DELIV, BAD), BAD)
check("4 tiếp nhận bản chat chưa đạt", r[0] == "adopted")
adv(r[5].id, r[7])
check("4 chưa đạt: việc nền chạy một lượt, prompt có bản chat, thay được file, chờ người dùng",
      r[6].queries == 1 and BAD in r[6].prompts[0] and (Path(r[1]) / DELIV).read_text(encoding="utf-8") == WORKER
      and rs(r[2], r[3], r[5].id).get("block_reason") == "human_confirmation")
b, st, P = world("c4p")
clk = Clock()
mid, ref = mref()
feed(ref, b, sdk_events(write_msgs(b, DELIV, A)))
put_file(b, DELIV, A)
g = create(b, st, P, clk, mid, ref)
_c = sqlite3.connect(str(_STATE / "c4p.sqlite3"))
_c.execute("UPDATE goals SET paused=1 WHERE id=?", (g.id,))
_c.commit()
_c.close()
check("4 mục tiêu tạm dừng: không tiếp nhận",
      R.handoff_after_turn(g.id, ref, deps_for(b, st, FakeEngine(), clk)) == "gate_closed"
      and st.published(P, g.id, DELIV) is None)
b, st, P = world("c4o")
clk = Clock()
mid, ref = mref()
feed(ref, b, sdk_events(write_msgs(b, DELIV, A)))
put_file(b, DELIV, A)
g = create(b, st, P, clk, mid, ref)
RA.disable(st, b)
check("4 tắt Cộng hưởng của trợ lý: không tiếp nhận",
      R.handoff_after_turn(g.id, ref, deps_for(b, st, FakeEngine(), clk)) == "gate_closed")

# ═══════════ 5. Góp ý: việc nền sửa từ bản anh đã xem; chat tự sửa thì tiếp nhận ═══════════
b, st, P, clk, g, eng, deps = G1
mid2, ref2 = mref()
g2 = revise(st, P, g.id, st.get(P, g.id).revision, clk, mid2, ref2)
check("5 góp ý trong lượt chat: revision mới có dòng bàn giao pending",
      (st.handoff(P, g.id, g2.revision) or {}).get("status") == "pending")
check("5a lượt góp ý không Write: không tiếp nhận, nhả lịch", R.handoff_after_turn(g.id, ref2, deps) == "no_receipt")
seen = (Path(b) / DELIV).read_text(encoding="utf-8")
adv(g.id, deps)
check("5a việc nền sửa từ ĐÚNG bản anh đã xem, kèm lời góp ý",
      eng.queries == 1 and seen in eng.prompts[0] and FEEDBACK in eng.prompts[0])
check("5a bản sửa thay được bản chat, chờ người dùng",
      (Path(b) / DELIV).read_text(encoding="utf-8") == WORKER
      and rs(st, P, g.id).get("block_reason") == "human_confirmation")
r = scenario("c5b", lambda b: write_msgs(b, DELIV, A), A)
adv(r[5].id, r[7])
mid2, ref2 = mref()
feed(ref2, r[1], sdk_events(write_msgs(r[1], DELIV, A2)))
put_file(r[1], DELIV, A2)
g2 = revise(r[2], r[3], r[5].id, r[2].get(r[3], r[5].id).revision, r[4], mid2, ref2)
check("5b chat tự Write bản sửa: tiếp nhận cho revision mới", R.handoff_after_turn(r[5].id, ref2, r[7]) == "adopted"
      and [x["kind"] for x in r[2].evidence_for(r[3], r[5].id, g2.revision)] == ["chat_output"])
adv(r[5].id, r[7])
check("5b không gọi việc nền viết lại, chờ người dùng xác nhận bản mới",
      r[6].queries == 0 and rs(r[2], r[3], r[5].id).get("block_reason") == "human_confirmation")

# ═══════════ 6. Revision đổi giữa chừng ═══════════
b, st, P = world("c6")
clk = Clock()
mid, ref = mref()
feed(ref, b, sdk_events(write_msgs(b, DELIV, A)))
put_file(b, DELIV, A)
g = create(b, st, P, clk, mid, ref)
mid2, ref2 = mref()
revise(st, P, g.id, g.revision, clk, mid2, ref2)
due_before = wake_due(st, P, g.id)
check("6 revision đã sang tin khác: bàn giao của lượt cũ không tiếp nhận, không đụng bàn giao của tin mới",
      R.handoff_after_turn(g.id, ref, deps_for(b, st, FakeEngine(), clk)) == "not_this_turn"
      and wake_due(st, P, g.id) == due_before and st.published(P, g.id, DELIV) is None)

# ═══════════ 7. Bản tiếp nhận không tạo receipt việc nền ═══════════
b, st, P, clk, g, eng, deps = G1
check("7 chỉ lượt việc nền thật có receipt", len([x for x in st.actions(P, g.id) if x["kind"] == "work"]) == 1)

print(f"\n{'FAIL' if _fails else 'OK'}: {len(_fails)} lỗi")
raise SystemExit(1 if _fails else 0)
