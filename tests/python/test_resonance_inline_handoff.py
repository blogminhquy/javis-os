"""Resonance: tiếp nhận bản bộ não viết trong lượt chat (review pilot lần 3). Kho SQLite thật, engine GIẢ.

    python tests/run.py resonance_inline_handoff -v

Pilot lần 3: bộ não Write bản đầu rồi lập mục tiêu; việc nền vẫn tiêu một lượt viết lại, không đăng được (xung đột),
thẻ trỏ bản chat còn receipt mô tả bản việc nền. Sửa: host tự lập biên nhận ghi từ sự kiện Write (toàn văn), bàn
giao cuối lượt tiếp nhận đúng bản đó, đánh giá rồi mới chọn bước tiếp theo. Thiết kế:
docs/dev/resonance-inline-artifact-handoff.md. Các ca theo mục "Kiểm chứng trước pilot tiếp theo" của review.
Không gọi model thật.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import hashlib
import os
import tempfile
from pathlib import Path

_STATE = Path(tempfile.mkdtemp(prefix="javis-res-handoff-"))
os.environ["JAVIS_STATE_DIR"] = str(_STATE)
os.environ.pop("JAVIS_RESONANCE_CALL_CEILING", None)

import resonance as R  # noqa: E402
import resonance_store as RS  # noqa: E402

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
        self.items[eid] = {"text": text, "content_hash": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                           "meta": dict(metadata or {})}
        return eid

    def valid(self, evidence_id):
        return self.items.get(evidence_id)


EVIDENCE = FakeEvidence()


async def _notes(goal, kind, text, card=""):
    return True


_n = {"mid": 0}


def world(name):
    brain = Path(tempfile.mkdtemp(prefix=f"brain-{name}-")).resolve()
    (brain / "Javis").mkdir(parents=True)
    (brain / "Javis" / "resonance.json").write_text('{"enabled": true}', encoding="utf-8")
    store = RS.GoalStore(_STATE / f"{name}.sqlite3")
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


def create(brain, store, p, clock, mid, ref, hold=True, **kw):
    deps0 = R.GoalDeps(engine_factory=lambda s, t: (None, {"blocked": "không gọi"}), budget=R.CallBudget(0),
                       store=store)
    return asyncio.run(R.form_goal(ref, {
        "principal": p, "brain_root": brain, "session_id": "s-hand", "message_id": mid, "user_text": USER,
        "constraints": [], "budget_calls": 4, "proposal": proposal(**kw),
        "hold_until": clock() + R.HANDOFF_HOLD_S if hold else None}, deps0))


def write_event(brain, rel, content, absolute=True, name="Write"):
    path = str(Path(brain) / rel) if absolute else rel
    key = "file_path" if name == "Write" else "path"
    return {"type": "tool_call", "name": name, "input": {key: path, "content": content}}


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


# ═══════════ 1. Write rồi lập mục tiêu: tiếp nhận, không gọi việc nền, chờ người dùng ═══════════
b, st, P = world("c1")
clk = Clock()
mid, ref = mref()
R.note_turn_write(ref, b, write_event(b, DELIV, A))
put_file(b, DELIV, A, crlf=True)                      # engine ghi xuống đĩa với CRLF
g = create(b, st, P, clk, mid, ref)
check("1 lập trong lượt chat: lịch việc nền bị GIỮ tới khi bàn giao", (wake_due(st, P, g.id) or 0) >= clk() + 800)
eng = FakeEngine()
deps = deps_for(b, st, eng, clk)
check("1 bàn giao: tiếp nhận bản chat (khớp sau khi chuẩn hoá xuống dòng)", R.handoff_after_turn(g.id, ref, deps)
      == "adopted")
ev = [e for e in st.events(P, g.id) if e["kind"] == "artifact_adopted"]
data = (Path(b) / DELIV).read_bytes()
check("1 sự kiện artifact_adopted ghi đúng file, hash bytes thật, tin nhắn",
      len(ev) == 1 and ev[0]["payload"]["path"] == DELIV and ev[0]["payload"]["sha256"] == R._sha(data)
      and ev[0]["message_ref"] == ref)
check("1 bằng chứng chat_output của đúng revision, bản chụp đúng nội dung",
      [x["kind"] for x in st.evidence_for(P, g.id, g.revision)] == ["chat_output"]
      and EVIDENCE.items[ev[0]["payload"]["evidence_id"]]["text"] == data.decode("utf-8"))
check("1 mốc đăng nguồn chat, hash bytes thật", (st.published(P, g.id, DELIV) or {}).get("sha256") == R._sha(data)
      and str((st.published(P, g.id, DELIV) or {}).get("action_id")).startswith("chat:"))
check("1 nhả lịch giữ chỗ để đánh giá ngay", (wake_due(st, P, g.id) or 1e18) <= clk())
a = adv(g.id, deps)
check("1 đánh giá: KHÔNG gọi việc nền, chờ người dùng xác nhận",
      eng.queries == 0 and rs(st, P, g.id).get("block_reason") == "human_confirmation" and a.verdict == "unknown")
check("1 không có receipt việc nền giả", not [x for x in st.actions(P, g.id) if x["kind"] == "work"])
check("1 thẻ trỏ đúng bản chat (artifact_ref = hash bytes trên đĩa)",
      R._artifact_ref_of(st, P, st.get(P, g.id), b) == R._sha(data))
check("1 bàn giao lặp: không tiếp nhận lần hai", st.adopt_artifact(P, g.id, g.revision, DELIV, R._sha(data), ref,
                                                                    "ev_x") == "already"
      and len([e for e in st.events(P, g.id) if e["kind"] == "artifact_adopted"]) == 1)
G1 = (b, st, P, clk, g, eng, deps)

# ═══════════ 2. Lập mục tiêu rồi mới Write: scheduler không chạy trước bàn giao ═══════════
b, st, P = world("c2")
clk = Clock()
mid, ref = mref()
g = create(b, st, P, clk, mid, ref)
eng = FakeEngine()
deps = deps_for(b, st, eng, clk)
n = asyncio.run(R.tick(st, clk(), lambda bid: deps))
check("2 nhịp scheduler giữa lượt: không nhận lịch đang giữ, không gọi engine", n == 0 and eng.queries == 0)
R.note_turn_write(ref, b, write_event(b, DELIV, A))
put_file(b, DELIV, A)
check("2 Write sau khi lập: vẫn tiếp nhận ở bàn giao", R.handoff_after_turn(g.id, ref, deps) == "adopted")
asyncio.run(R.tick(st, clk(), lambda bid: deps))
check("2 sau bàn giao: chờ người dùng, 0 lượt engine",
      eng.queries == 0 and rs(st, P, g.id).get("block_reason") == "human_confirmation")

# ═══════════ 3. Không tự cấp quyền thay file ═══════════
# 3a. File có sẵn từ trước, lượt này không Write
b, st, P = world("c3a")
clk = Clock()
put_file(b, DELIV, A)
mid, ref = mref()
g = create(b, st, P, clk, mid, ref)
eng = FakeEngine()
deps = deps_for(b, st, eng, clk)
check("3a file có sẵn, không biên nhận: không tiếp nhận", R.handoff_after_turn(g.id, ref, deps) == "no_receipt"
      and st.published(P, g.id, DELIV) is None)
adv(g.id, deps)
conf = [e for e in st.events(P, g.id) if e["kind"] == "publish_conflict"]
check("3a việc nền chạy như cũ, không ghi đè file có sẵn, báo đúng nguyên nhân",
      eng.queries == 1 and (Path(b) / DELIV).read_text(encoding="utf-8") == A and bool(conf)
      and any(r["kind"] == "goal.publish_conflict" and r["payload"].get("had_baseline") is False
              for r in st.outbox_pending(200) if r["goal_id"] == g.id))
# 3b. Biên nhận của tin nhắn khác
b, st, P = world("c3b")
clk = Clock()
_, ref_other = mref()
R.note_turn_write(ref_other, b, write_event(b, DELIV, A))
put_file(b, DELIV, A)
mid, ref = mref()
g = create(b, st, P, clk, mid, ref)
deps = deps_for(b, st, FakeEngine(), clk)
check("3b biên nhận của lượt khác không dùng cho lượt này", R.handoff_after_turn(g.id, ref, deps) == "no_receipt")
R.drop_turn_writes(ref_other)
# 3c. Write rồi Edit (file khác lần Write cuối)
b, st, P = world("c3c")
clk = Clock()
mid, ref = mref()
R.note_turn_write(ref, b, write_event(b, DELIV, A))
R.note_turn_write(ref, b, {"type": "tool_call", "name": "Edit", "input": {"file_path": str(Path(b) / DELIV)}})
put_file(b, DELIV, A.replace("Đếm kiện", "Đếm kiện kỹ"))
g = create(b, st, P, clk, mid, ref)
deps = deps_for(b, st, FakeEngine(), clk)
check("3c Edit sau Write: bytes khác lần Write cuối, không tiếp nhận",
      R.handoff_after_turn(g.id, ref, deps) == "changed_after_write" and st.published(P, g.id, DELIV) is None)
# 3d. Đường dẫn ngoài brain hay vào vùng cấm không lập biên nhận
check("3d Write ra ngoài brain: không lập biên nhận",
      not R.note_turn_write("msg:x:1", b, {"name": "Write", "input": {"file_path": str(_STATE / "x.md"),
                                                                       "content": "x"}}))
check("3d công cụ không có toàn văn (Edit, Bash) không lập biên nhận",
      not R.note_turn_write("msg:x:2", b, {"name": "Edit", "input": {"file_path": str(Path(b) / DELIV)}})
      and not R.note_turn_write("msg:x:3", b, {"name": "Bash", "input": {"command": "echo > x"}}))
check("3d javis_write_file (đường dẫn tương đối trong brain) lập được biên nhận",
      R.note_turn_write("msg:x:4", b, write_event(b, DELIV, A, absolute=False, name="javis_write_file")))
R.drop_turn_writes("msg:x:4")
# 3e. Ghi bằng chứng lỗi: không công bố đã tiếp nhận
b, st, P = world("c3e")
clk = Clock()
mid, ref = mref()
R.note_turn_write(ref, b, write_event(b, DELIV, A))
put_file(b, DELIV, A)
g = create(b, st, P, clk, mid, ref)
deps = deps_for(b, st, FakeEngine(), clk)
EVIDENCE.fail = True
check("3e không lưu được bằng chứng: không tiếp nhận, không mốc đăng",
      R.handoff_after_turn(g.id, ref, deps) == "evidence_failed" and st.published(P, g.id, DELIV) is None
      and not [e for e in st.events(P, g.id) if e["kind"] == "artifact_adopted"])
EVIDENCE.fail = False

# ═══════════ 4. Bản chat chưa đạt tiêu chí khách quan: việc nền sửa TỪ bản đó ═══════════
b, st, P = world("c4")
clk = Clock()
mid, ref = mref()
R.note_turn_write(ref, b, write_event(b, DELIV, BAD))
put_file(b, DELIV, BAD)
g = create(b, st, P, clk, mid, ref)
eng = FakeEngine(WORKER)
deps = deps_for(b, st, eng, clk)
check("4 tiếp nhận bản chat chưa đạt", R.handoff_after_turn(g.id, ref, deps) == "adopted")
a = adv(g.id, deps)
check("4 chưa đạt thì KHÔNG coi là đủ để chờ duyệt: việc nền chạy một lượt", eng.queries == 1)
check("4 prompt việc nền có đúng bản chat làm bản trước", BAD in eng.prompts[0])
check("4 bản việc nền thay được file (mốc tiếp nhận cấp quyền), không xung đột",
      (Path(b) / DELIV).read_text(encoding="utf-8") == WORKER
      and not [e for e in st.events(P, g.id) if e["kind"] == "publish_conflict"])
check("4 sau bản sửa: chờ người dùng", rs(st, P, g.id).get("block_reason") == "human_confirmation")
# Tạm dừng: không tiếp nhận
b, st, P = world("c4p")
clk = Clock()
mid, ref = mref()
R.note_turn_write(ref, b, write_event(b, DELIV, A))
put_file(b, DELIV, A)
g = create(b, st, P, clk, mid, ref)
OWNER = RS.Principal("owner", "owner", b)
st.command(OWNER, g.id, "pause", g.revision) if hasattr(st, "command") else None
_paused = (st.get(P, g.id) or g).paused
if not _paused:
    import sqlite3
    _c = sqlite3.connect(str(_STATE / "c4p.sqlite3"))
    _c.execute("UPDATE goals SET paused=1 WHERE id=?", (g.id,))
    _c.commit()
    _c.close()
deps = deps_for(b, st, FakeEngine(), clk)
check("4 mục tiêu tạm dừng: không tiếp nhận", R.handoff_after_turn(g.id, ref, deps) == "gate_closed"
      and st.published(P, g.id, DELIV) is None)
# Tắt tính năng
b, st, P = world("c4o")
clk = Clock()
mid, ref = mref()
R.note_turn_write(ref, b, write_event(b, DELIV, A))
put_file(b, DELIV, A)
g = create(b, st, P, clk, mid, ref)
(Path(b) / "Javis" / "resonance.json").write_text('{"enabled": false}', encoding="utf-8")
deps = deps_for(b, st, FakeEngine(), clk)
check("4 tắt tính năng: không tiếp nhận", R.handoff_after_turn(g.id, ref, deps) == "gate_closed")

# ═══════════ 5. Góp ý: việc nền sửa từ bản anh đã xem; hoặc chat tự sửa thì tiếp nhận ═══════════
b, st, P, clk, g, eng, deps = G1
g1 = st.get(P, g.id)
mid2, ref2 = mref()
g2, rel2, _ = R.revise_goal(st, P, g.id, g1.revision,
                            {"constraints": ["Bước đối chiếu có một ví dụ cụ thể"],
                             "relevant_quote": "em thêm một ví dụ cụ thể"},
                            {"message_ref": ref2, "session_id": "s-hand", "message_id": mid2, "user_text": FEEDBACK,
                             "constraints": [], "user_unsure": False, "reason": "góp ý",
                             "hold_until": clk() + R.HANDOFF_HOLD_S})
check("5 góp ý trong lượt chat: revision mới, lịch giữ tới bàn giao",
      g2.revision == g1.revision + 1 and (wake_due(st, P, g.id) or 0) >= clk() + 800)
check("5a lượt góp ý không Write: không tiếp nhận, nhả lịch", R.handoff_after_turn(g.id, ref2, deps) == "no_receipt")
seen = (Path(b) / DELIV).read_text(encoding="utf-8")
adv(g.id, deps)
check("5a việc nền sửa từ ĐÚNG bản anh đã xem (bản chat đã tiếp nhận)",
      eng.queries == 1 and seen in eng.prompts[0] and FEEDBACK in eng.prompts[0])
check("5a bản sửa thay được bản chat, chờ người dùng",
      (Path(b) / DELIV).read_text(encoding="utf-8") == WORKER
      and rs(st, P, g.id).get("block_reason") == "human_confirmation")
check("5a bản cũ không tự thành sản phẩm đạt của revision mới: thẻ trỏ bản của revision mới",
      R._artifact_ref_of(st, P, st.get(P, g.id), b) == R._sha((Path(b) / DELIV).read_bytes()))
# 5b. Lượt góp ý mà chat tự Write bản sửa: tiếp nhận cho revision mới, không gọi việc nền
b, st, P = world("c5b")
clk = Clock()
mid, ref = mref()
R.note_turn_write(ref, b, write_event(b, DELIV, A))
put_file(b, DELIV, A)
g = create(b, st, P, clk, mid, ref)
eng = FakeEngine()
deps = deps_for(b, st, eng, clk)
R.handoff_after_turn(g.id, ref, deps)
adv(g.id, deps)
mid2, ref2 = mref()
R.note_turn_write(ref2, b, write_event(b, DELIV, A2))
put_file(b, DELIV, A2)
g2, _, _ = R.revise_goal(st, P, g.id, g.revision, {"constraints": ["Có ví dụ"], "relevant_quote": "em thêm một ví dụ"},
                         {"message_ref": ref2, "session_id": "s-hand", "message_id": mid2, "user_text": FEEDBACK,
                          "constraints": [], "user_unsure": False, "reason": "góp ý",
                          "hold_until": clk() + R.HANDOFF_HOLD_S})
check("5b chat tự Write bản sửa: tiếp nhận cho revision mới", R.handoff_after_turn(g.id, ref2, deps) == "adopted"
      and [x["kind"] for x in st.evidence_for(P, g.id, g2.revision)] == ["chat_output"])
adv(g.id, deps)
check("5b không gọi việc nền viết lại, chờ người dùng xác nhận bản mới",
      eng.queries == 0 and rs(st, P, g.id).get("block_reason") == "human_confirmation"
      and R._artifact_ref_of(st, P, st.get(P, g.id), b) == R._sha((Path(b) / DELIV).read_bytes()))

# ═══════════ 6. Revision đổi giữa chừng, bàn giao lặp, restart ═══════════
b, st, P = world("c6")
clk = Clock()
mid, ref = mref()
R.note_turn_write(ref, b, write_event(b, DELIV, A))
put_file(b, DELIV, A)
g = create(b, st, P, clk, mid, ref)
mid2, ref2 = mref()
R.revise_goal(st, P, g.id, g.revision, {"constraints": ["Có ví dụ"], "relevant_quote": "em thêm một ví dụ"},
              {"message_ref": ref2, "session_id": "s-hand", "message_id": mid2, "user_text": FEEDBACK,
               "constraints": [], "user_unsure": False, "reason": "góp ý", "hold_until": clk() + R.HANDOFF_HOLD_S})
deps = deps_for(b, st, FakeEngine(), clk)
due_before = wake_due(st, P, g.id)
check("6 revision đã sang tin khác: bàn giao của lượt cũ không tiếp nhận, không đụng lịch của tin mới",
      R.handoff_after_turn(g.id, ref, deps) == "not_this_turn" and wake_due(st, P, g.id) == due_before
      and st.published(P, g.id, DELIV) is None)
# Restart: sổ biên nhận trong bộ nhớ mất, lịch giữ chỗ vẫn tự tới hạn và chạy như cũ (an toàn, chỉ chậm).
b, st, P = world("c6r")
clk = Clock()
mid, ref = mref()
put_file(b, DELIV, A)
g = create(b, st, P, clk, mid, ref)
eng = FakeEngine()
deps = deps_for(b, st, eng, clk)
asyncio.run(R.tick(st, clk(), lambda bid: deps))
check("6 restart giữa lượt (không bàn giao): chưa tới hạn thì không chạy", eng.queries == 0)
clk.t += R.HANDOFF_HOLD_S + 1
asyncio.run(R.tick(st, clk(), lambda bid: deps))
check("6 quá hạn giữ chỗ: chạy như trước, không ghi đè file chưa tiếp nhận",
      eng.queries == 1 and (Path(b) / DELIV).read_text(encoding="utf-8") == A)

# ═══════════ 7. Xác nhận cũ không áp cho bản hay revision mới ═══════════
b, st, P, clk, g, eng, deps = G1
gcur = st.get(P, g.id)
check("7 sau góp ý: tiêu chí người dùng của revision mới chưa đạt dù revision cũ từng có bản chờ duyệt",
      gcur.status == "active" and rs(st, P, g.id).get("block_reason") == "human_confirmation")
check("7 bản tiếp nhận không tạo receipt việc nền: chỉ lượt việc nền thật có receipt",
      len([x for x in st.actions(P, g.id) if x["kind"] == "work"]) == 1)

print(f"\n{'FAIL' if _fails else 'OK'}: {len(_fails)} lỗi")
raise SystemExit(1 if _fails else 0)
