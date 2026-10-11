"""Resonance A4: nộp sản phẩm qua một hợp đồng host, kèm phạm vi do chủ dự án cho phép (thiết kế chốt, D1).

    python tests/run.py resonance_a4_grants -v

Kho SQLite thật, engine GIẢ, đồng hồ giả; không gọi model thật. Mỗi ca chạy trên kho và brain riêng. Tên ca theo ma trận
nghiệm thu mục 12 của docs/superpowers/specs/2026-10-10-resonance-a4-handoff-grants-design.md. Ca âm kiểm đủ ba mặt khi
liên quan: không có gốc, không đọc đích vào prompt, không đăng, không giữ lượt nền.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import hashlib
import json
import os
import sqlite3
import tempfile
import time
from pathlib import Path

_STATE = Path(tempfile.mkdtemp(prefix="javis-res-a4-"))
os.environ["JAVIS_STATE_DIR"] = str(_STATE)
os.environ.pop("JAVIS_RESONANCE_CALL_CEILING", None)

import resonance as R  # noqa: E402
import resonance_grants as G  # noqa: E402
import resonance_store as RS  # noqa: E402
import turn_context  # noqa: E402
import _resonance_agent as RA  # noqa: E402

_fails = []


def check(name, cond, detail=""):
    print(("ok   " if cond else "FAIL ") + name + ("" if cond or not detail else f"  [{str(detail)[:300]}]"))
    if not cond:
        _fails.append(name)


DELIV = "Inbox/ban-tom-tat.md"
GOOD = "# Tóm tắt\n\nMột bản tóm tắt đủ dài để qua tiêu chí, có mục Kết luận.\n\n## Kết luận\n\nXong.\n"
USER = "Em lo giúp anh bản tóm tắt cuộc họp tới khi anh thấy dùng được. Ghi vào Inbox/ban-tom-tat.md."


class Clock:
    def __init__(self, t=1_800_000_000.0):
        self.t = t

    def __call__(self):
        return self.t


class Engine:
    def __init__(self, text=GOOD):
        self.text, self.queries, self.prompts, self.max_wall_s = text, 0, [], None

    def is_available(self):
        return True

    async def query(self, prompt):
        self.queries += 1
        self.prompts.append(prompt)
        yield {"type": "final", "content": self.text, "tokens_in": 1, "tokens_out": 1}


class Evidence:
    def __init__(self):
        self.items = {}

    def put(self, goal, label, text, meta):
        eid = f"ev_{len(self.items) + 1}"
        self.items[eid] = {"text": text, "content_hash": hashlib.sha256(text.encode("utf-8")).hexdigest()}
        return eid

    def valid(self, eid):
        return self.items.get(eid)


EV = Evidence()


async def _notes(goal, kind, text, card=""):
    return True


class World:
    """Một kho, một brain, một trợ lý đang bật."""
    n = 0

    def __init__(self, name):
        World.n += 1
        self.brain = str(Path(tempfile.mkdtemp(prefix=f"brain-a4-{name}-")).resolve())
        (Path(self.brain) / "Javis").mkdir(parents=True)
        self.store = RS.GoalStore(_STATE / f"{name}.sqlite3")
        self.agent = RA.enable(self.store, self.brain)
        self.p = RS.Principal("agent", self.agent["agent_key"], self.brain)
        self.owner = RA.owner(self.brain)
        self.clock = Clock()
        self.eng = Engine()
        self.mid = 0
        self.sid = f"s-{name}"

    def deps(self, eng=None):
        e = eng or self.eng
        return R.GoalDeps(engine_factory=lambda s, t: (e, {"provider": "fake", "model": "fake-1", "text_only": True}),
                          budget=R.CallBudget(0), clock=self.clock, store=self.store,
                          principal=RS.Principal("agent", "javis", self.brain), brain_root=self.brain,
                          evidence=EV, notify=_notes)

    def next(self):
        self.mid += 1
        return self.mid, R.message_ref(self.sid, self.mid)

    def ag(self):
        return self.store.agent(self.brain, RA.SLUG)

    def proposal(self, path=DELIV, **kw):
        p = {"understanding": "Bản tóm tắt cuộc họp", "relevant_quote": "Em lo giúp anh bản tóm tắt cuộc họp",
             "criteria": [{"description": "Có mục Kết luận", "evaluator": "artifact_contract",
                           "params": {"path": path, "must_contain": ["Kết luận"]}}],
             "horizon": {"kind": "review", "at_iso": "2027-01-20T09:00:00+07:00"}, "stage": "delivery",
             "mode": "achieve"}
        p.update(kw)
        return p

    def create(self, mid, ref, text=USER, path=DELIV, hold=True, seq=None):
        d0 = R.GoalDeps(engine_factory=lambda s, t: (None, {}), budget=R.CallBudget(0), store=self.store)
        return asyncio.run(R.form_goal(ref, {
            "principal": self.p, "brain_root": self.brain, "session_id": self.sid, "message_id": mid,
            "user_text": text, "constraints": [], "budget_calls": 4, "proposal": self.proposal(path),
            "hold_until": (self.clock() + R.HANDOFF_HOLD_S) if hold else None,
            "authority_seq": self.store.authority_seq() if seq is None else seq, **RA.ctx(self.ag())}, d0))

    def revise(self, g, mid, ref, path=DELIV, understanding="Bản tóm tắt cuộc họp, bản sửa", seq=None):
        return R.revise_goal(self.store, self.p, g.id, g.revision,
                             {"understanding": understanding, "relevant_quote": "Em lo giúp anh bản tóm tắt cuộc họp",
                              "criteria": self.proposal(path)["criteria"]},
                             {"message_ref": ref, "session_id": self.sid, "message_id": mid, "user_text": USER,
                              "constraints": [], "user_unsure": False, "reason": "góp ý",
                              "hold_until": self.clock() + R.HANDOFF_HOLD_S,
                              "authority_seq": self.store.authority_seq() if seq is None else seq,
                              **RA.ctx(self.ag())})[0]

    def turn(self, mid, seq=None, text=USER):
        return RA.turn(self.ag(), self.sid, mid, text, self.brain, store=self.store, seq=seq)

    def submit(self, content=GOOD, path=DELIV, **kw):
        return R.submit_deliverable(turn_context.current(), {"path": path, "content": content, **kw}, self.deps())

    def adv(self, kind="wake", eng=None):
        return asyncio.run(R.tick(self.store, self.clock(), lambda bid: self.deps(eng)))

    def wake(self, g, eng=None):
        return asyncio.run(R.advance(g.id, {"kind": "wake"}, self.deps(eng)))

    def approve(self, g, **over):
        sc = self.store.scope_state(self.owner, g.id)
        cur = self.store.get(self.owner, g.id)
        drafts = self.store.submissions(self.owner, g.id, limit=1, statuses=("awaiting_scope",), revision=cur.revision)
        body = {"request_id": (sc.get("request") or {}).get("id", ""), "path": R._deliverable_rel(cur)}
        if drafts:
            body.update(submission_id=drafts[0]["id"], sha256=drafts[0]["sha256"])
        body.update(over)
        return R.apply_command(self.store, self.owner, g.id, "approve_scope", body, self.brain)

    def target(self):
        return Path(self.brain) / DELIV

    def scope(self, g):
        return self.store.scope_state(self.owner, g.id)

    def subs(self, g):
        return self.store.submissions(self.owner, g.id, limit=50)

    def events(self, g, kind):
        return [e for e in self.store.events(self.owner, g.id) if e["kind"] == kind]


def stale_err(fn):
    try:
        fn()
    except RS.ConflictError as e:
        return "scope_request_stale" in str(e)
    return False


# ═══════════ G1, G2: narrow chỉ thu hẹp ═══════════
par = {"goal_id": "g", "brain_id": "b", "actions": ["read_deliverable", "submit", "publish"],
       "write_paths": ["a.md"], "read_paths": ["a.md"], "recipients": []}
got, why = G.narrow(par, {"goal_id": "g", "brain_id": "b", "actions": ["submit", "publish"], "write_paths": ["a.md", "b.md"],
                          "read_paths": [], "recipients": ["tro-ly-khac"]})
check("G1 narrow: phần giao, người nhận không có ở cha thì rỗng", got["actions"] == ["publish", "submit"]
      and got["write_paths"] == ["a.md"] and got["recipients"] == [] and got["read_paths"] == [], got)
check("G2 narrow: mục tiêu khác thì từ chối", G.narrow(par, {**par, "goal_id": "khac"}) == (None, "scope_mismatch"))
check("G2 narrow: thao tác lạ thì phần giao thao tác rỗng",
      G.narrow(par, {**par, "actions": ["publish", "communicate"]})[0]["actions"] == [])

# ═══════════ G13, G45: khoá đường (D15) ═══════════
_b = str(Path(tempfile.mkdtemp(prefix="brain-a4-path-")).resolve())
(Path(_b) / "Inbox").mkdir()
check("G45 _brain_file hiện tại nhận a/../a (đính chính vòng 3), khoá đường A4 thì từ chối",
      R._brain_file(_b, "Inbox/../Inbox/x.md") is not None and G.path_key(_b, "Inbox/../Inbox/x.md") is None)
check("G45 từ chối đoạn `.`", G.path_key(_b, "./Inbox/x.md") is None)
check("G13 từ chối `..` thoát brain, đường tuyệt đối, ký tự điều khiển",
      G.path_key(_b, "../x.md") is None and G.path_key(_b, str(Path(_b) / "Inbox" / "x.md")) is None
      and G.path_key(_b, "Inbox/x\x01.md") is None)
check("G13 từ chối đuôi lạ và thư mục cấm",
      G.path_key(_b, "Inbox/x.py") is None and G.path_key(_b, "agents/x.md") is None
      and G.path_key(_b, "memory/facts/x.md") is None and G.path_key(_b, ".claude/x.md") is None)
if os.name == "nt":
    check("G45 Windows: chữ hoa thường về cùng khoá", G.path_key(_b, "INBOX/X.md") == G.path_key(_b, "Inbox/x.md")
          == "inbox/x.md")
else:
    check("G45 POSIX: khoá giữ đúng chữ", G.path_key(_b, "Inbox/x.md") == "Inbox/x.md")

# ═══════════ G22: bảng khả năng engine ═══════════
check("G22 Claude: khoá lượt, nộp qua công cụ, biên nhận Write", G.engine_caps("anthropic-cli") ==
      {"turn_key": True, "submit_tool": True, "observed_write": True})
check("G22 Codex, engine API: nộp qua công cụ, không có biên nhận Write",
      G.engine_caps("openai-oauth")["submit_tool"] and not G.engine_caps("openai-oauth")["observed_write"]
      and G.engine_caps("openrouter")["submit_tool"])
check("G22 Grok, Antigravity: không có khoá lượt, không nhận bàn giao chat",
      not G.engine_caps("grok-cli")["turn_key"] and not G.engine_caps("antigravity-cli")["submit_tool"])

# ═══════════ G27, G51 tới G55, G73 tới G79: không cấp quyền từ lời chat (D1) ═══════════
TEXTS = {
    "G54 lệnh trực tiếp": "Ghi vào Inbox/ban-tom-tat.md bản tóm tắt. Em lo giúp anh bản tóm tắt cuộc họp.",
    "G51 phủ định": "Em lo giúp anh bản tóm tắt cuộc họp, đừng ghi vào Inbox/ban-tom-tat.md.",
    "G73 điều kiện": "Em lo giúp anh bản tóm tắt cuộc họp. Nếu anh duyệt sau, ghi vào Inbox/ban-tom-tat.md.",
    "G74 câu hỏi": "Em lo giúp anh bản tóm tắt cuộc họp. Có nên ghi vào Inbox/ban-tom-tat.md?",
    "G79 ví dụ minh họa": "Em lo giúp anh bản tóm tắt cuộc họp. Đây là ví dụ minh họa. Ghi vào Inbox/ban-tom-tat.md.",
    "G79 câu cần dịch": "Em lo giúp anh bản tóm tắt cuộc họp. Ghi vào Inbox/ban-tom-tat.md là câu cần dịch.",
}
for label, text in TEXTS.items():
    w = World("d1-" + label.split()[0].lower())
    mid, ref = w.next()
    with w.turn(mid, text=text):
        g = w.create(mid, ref, text=text)
    sc = w.scope(g)
    w.clock.t += R.HANDOFF_HOLD_S + 1
    w.adv()
    check(f"{label}: chờ chủ dự án cho phép, không có gốc, không gọi model, không ghi file",
          sc["state"] == "pending" and sc["root"] is None and w.eng.queries == 0 and not w.target().exists()
          and w.store.get(w.owner, g.id).calls_used == 0
          and (w.store.run_state(w.owner, g.id) or {}).get("block_reason") == "scope_pending", sc)
try:
    w.store.begin_action(w.p, g.id, g.revision, "work", lease_until=9e18, now=1.0, intent=RA.pin(w.store, w.brain))
    _held = True
except RS.GrantError as e:
    _held = str(e) == "scope_pending"
check("G15 giữ lượt khi chưa có phạm vi: GrantError(scope_pending), không giữ lượt",
      _held is True and w.store.get(w.owner, g.id).calls_used == 0)

# ═══════════ G57: lập, nộp nháp, kết thúc chat, chủ dự án cho phép: đăng đúng bản, 0 lượt model ═══════════
w = World("g57")
mid, ref = w.next()
with w.turn(mid):
    g = w.create(mid, ref)
    r = w.submit()
check("G57 nộp khi chưa có phạm vi: giữ làm nháp awaiting_scope, chưa ghi file",
      r.get("ok") and r["status"] == "awaiting_scope" and not w.target().exists(), r)
check("G61 bản nháp không đăng được (publish_intent chỉ nhận candidate)",
      w.store.publish_intent(w.p, r["submission_id"], DELIV, None, {})["status"] == "not_candidate")
ho = R.handoff_after_turn(g.id, ref, w.deps())
b0 = w.store.turn_binding(w.owner, g.id, g.revision, ref)
check("G57 cuối lượt: liên kết draft niêm, không đăng, không giữ lượt", b0["authority"] == "draft"
      and b0["status"] == "sealed" and not w.target().exists() and w.eng.queries == 0, (ho, b0))
res = w.approve(g)
subs = {s["source"]: s for s in w.subs(g)}
sc = w.scope(g)
check("G57 Cho phép: đăng đúng bản nháp, 0 lượt model",
      res.get("ok") and res.get("publish") == "succeeded" and w.target().read_text(encoding="utf-8") == GOOD
      and w.eng.queries == 0 and w.store.get(w.owner, g.id).calls_used == 0, res)
check("G57 sổ: bản nháp promoted, bản approved_draft published và đã tiếp nhận, gốc owner_approved",
      subs["submit_tool"]["status"] == "promoted" and subs["approved_draft"]["status"] == "published"
      and subs["approved_draft"]["adopted_at"] and sc["state"] == "granted" and sc["root"]["source"] == "owner_approved",
      (subs, sc))
check("G57 tiếp nhận đúng một lần (sự kiện artifact_adopted nguồn owner_approval)",
      [e["source"] for e in w.events(g, "artifact_adopted")] == ["owner_approval"])
check("G57 liên kết approval ghim gốc mới, liên kết draft đã đóng",
      w.store.turn_binding(w.owner, g.id, g.revision, ref)["status"] == "closed")
check("G59 bấm lại thẻ đã duyệt: scope_request_stale, không tạo gốc mới",
      stale_err(lambda: w.approve(g)) and len([x for x in [w.scope(g)["root"]] if x]) == 1)

# ═══════════ G58: Không ═══════════
w = World("g58")
mid, ref = w.next()
with w.turn(mid):
    g = w.create(mid, ref)
    w.submit()
R.handoff_after_turn(g.id, ref, w.deps())
req = w.scope(g)["request"]
R.apply_command(w.store, w.owner, g.id, "deny_scope", {"request_id": req["id"]}, w.brain)
w.clock.t += 60
w.adv()
check("G58 Không: bản nháp rejected, không gốc, không đăng, không gọi model",
      [s["status"] for s in w.subs(g)] == ["rejected"] and w.scope(g)["root"] is None
      and w.scope(g)["state"] == "denied" and not w.target().exists() and w.eng.queries == 0)
check("G58 sau Không: host không tự tạo lại yêu cầu cho cùng revision và đường", w.scope(g)["request"] is None)

# ═══════════ G59: thẻ cũ ═══════════
w = World("g59")
mid, ref = w.next()
with w.turn(mid):
    g = w.create(mid, ref)
    w.submit()
old_req = w.scope(g)["request"]
old_draft = w.subs(g)[0]
with w.turn(mid):
    w.submit(content=GOOD + "\nBản thứ hai.\n", submission_key="v2")
check("G59 có bản nháp mới hơn: thẻ gửi bản cũ bị từ chối",
      stale_err(lambda: w.approve(g, submission_id=old_draft["id"], sha256=old_draft["sha256"])))
check("G59 thẻ không gửi bản nháp khi đã có bản nháp: từ chối",
      stale_err(lambda: w.approve(g, submission_id="", sha256="")))
check("G25 đường gửi lên khác đường của yêu cầu: từ chối", stale_err(lambda: w.approve(g, path="Inbox/khac.md")))
mid2, ref2 = w.next()
with w.turn(mid2):
    g2 = w.revise(g, mid2, ref2)
check("G59 sau revision mới: yêu cầu cũ superseded, bấm thẻ cũ không cấp gốc",
      stale_err(lambda: w.approve(g, request_id=old_req["id"])) and w.scope(g2)["root"] is None)

# ═══════════ G24, G23: revision cùng đích tự có quyền; khác đích chờ ═══════════
w = World("g24")
mid, ref = w.next()
with w.turn(mid):
    g = w.create(mid, ref, hold=False)
w.approve(g)
mid2, ref2 = w.next()
with w.turn(mid2):
    g2 = w.revise(g, mid2, ref2)
    b2 = w.store.turn_binding(w.owner, g2.id, g2.revision, ref2)
check("G24 revision mới cùng đích: quyền revision tự cấp, không hỏi, lượt nhận liên kết grant",
      w.scope(g2)["state"] == "granted" and w.scope(g2)["request"] is None and b2["authority"] == "grant")
mid3, ref3 = w.next()
with w.turn(mid3):
    g3 = w.revise(g2, mid3, ref3, path="Inbox/dich-moi.md")
w.clock.t += R.HANDOFF_HOLD_S + 1
w.adv()
sc3 = w.scope(g3)
check("G23 đổi đích (có câu trích hợp lệ): không cấp quyền, ghi yêu cầu expand, không gọi model, không ghi file mới",
      sc3["state"] == "pending" and sc3["request"]["kind"] == "expand" and w.eng.queries == 0
      and not (Path(w.brain) / "Inbox/dich-moi.md").exists(), sc3)

# ═══════════ G17, G36: việc nền trong phạm vi: nộp, đăng, đúng một lần ═══════════
w = World("g17")
mid, ref = w.next()
with w.turn(mid):
    g = w.create(mid, ref, hold=False)
w.approve(g)
w.adv()
pubs = [x for x in w.store.actions(w.owner, g.id) if x["kind"] == "publish"]
bg = [s for s in w.subs(g) if s["source"] == "background_text"]
check("G36/G17 việc nền: một lượt model, file được tạo, mốc đúng sha, bản nộp published",
      w.eng.queries == 1 and w.target().read_text(encoding="utf-8") == GOOD and len(pubs) == 1
      and pubs[0]["status"] == "succeeded" and bg and bg[0]["status"] == "published"
      and w.store.published(w.owner, g.id, DELIV)["sha256"] == R._sha(GOOD.encode("utf-8")), (pubs, bg))
check("G17 ý định đăng mang liên kết và bản nộp; có mốc commit",
      pubs[0]["intent"].get("binding_id") and pubs[0]["intent"].get("submission_id") == bg[0]["id"]
      and pubs[0]["receipt"].get("commit_at"))
check("G12 prompt việc nền không chứa bản nháp chưa đăng", all("Bản thứ hai" not in pr for pr in w.eng.prompts))

# ═══════════ G37: đích có bản người dùng không có baseline ═══════════
w = World("g37")
w.target().parent.mkdir(parents=True, exist_ok=True)
w.target().write_text("bản của anh\n", encoding="utf-8")
mid, ref = w.next()
with w.turn(mid):
    g = w.create(mid, ref, hold=False)
w.approve(g)
w.adv()
check("G37 file người dùng không baseline: conflict, file nguyên vẹn, bản nộp giữ ở trạng thái conflict",
      w.target().read_text(encoding="utf-8") == "bản của anh\n"
      and [s["status"] for s in w.subs(g)] == ["conflict"])


def granted_world(name):
    """Mục tiêu đã có phạm vi; trả (world, goal) với lượt cập nhật kế tiếp mở được liên kết grant."""
    w = World(name)
    mid, ref = w.next()
    with w.turn(mid):
        g = w.create(mid, ref, hold=False)
    w.approve(g)
    return w, w.store.get(w.owner, g.id)


# ═══════════ G41, G38, G39: lượt chat nộp B, có hay không có Write A ═══════════
w, g = granted_world("g41")
mid, ref = w.next()
with w.turn(mid):
    g2 = w.revise(g, mid, ref)
    rb = w.submit()
st = R.handoff_after_turn(g2.id, ref, w.deps())
check("G41 lượt chat nộp B dưới quyền: cuối lượt host đăng và tiếp nhận, 0 lượt model",
      rb["status"] == "candidate" and st == "submission_published" and w.target().read_text(encoding="utf-8") == GOOD
      and w.eng.queries == 0 and len(w.events(g2, "artifact_adopted")) == 1, (rb, st))

A = "# Tóm tắt A\n\nBản Write A.\n\n## Kết luận\n\nA.\n"
B = "# Tóm tắt B\n\nBản nộp B.\n\n## Kết luận\n\nB.\n"
w, g = granted_world("g38")
mid, ref = w.next()
with w.turn(mid):
    g2 = w.revise(g, mid, ref)
    w.target().parent.mkdir(parents=True, exist_ok=True)
    w.target().write_text(A, encoding="utf-8")
    R.note_turn_event(ref, w.brain, {"type": "tool_call", "name": "Write", "id": "w1",
                                     "input": {"file_path": str(w.target()), "content": A}})
    R.note_turn_event(ref, w.brain, {"type": "tool_result", "tool_use_id": "w1", "is_error": False})
    w.submit(content=B)
st = R.handoff_after_turn(g2.id, ref, w.deps())
check("G38 Write A hợp lệ rồi nộp B: tiếp nhận A trước, đăng B qua CAS, mốc cuối là B",
      st == "submission_published" and w.target().read_text(encoding="utf-8") == B
      and w.store.published(w.owner, g2.id, DELIV)["sha256"] == R._sha(B.encode("utf-8"))
      and [s["source"] for s in w.subs(g2) if s["status"] in ("adopted_in_place", "published")]
      .count("observed_write") == 1, st)

w, g = granted_world("g39")
mid, ref = w.next()
with w.turn(mid):
    g2 = w.revise(g, mid, ref)
    w.target().parent.mkdir(parents=True, exist_ok=True)
    w.target().write_text(A, encoding="utf-8")
    w.submit(content=B)
st = R.handoff_after_turn(g2.id, ref, w.deps())
check("G39 Write A không biên nhận, nộp B: conflict, không ghi baseline B lên A",
      w.target().read_text(encoding="utf-8") == A and w.store.published(w.owner, g2.id, DELIV) is None
      and [s["status"] for s in w.subs(g2)] == ["conflict"], st)

# ═══════════ G10, G44, G46: khoá, dấu vân tay, phát lại ═══════════
w, g = granted_world("g10")
mid, ref = w.next()
with w.turn(mid):
    g2 = w.revise(g, mid, ref)
    r1 = w.submit(submission_key="k1")
    r2 = w.submit(submission_key="k1")
    r3 = w.submit(content=GOOD + "\nkhác\n", submission_key="k1")
check("G10 cùng khoá cùng dấu vân tay: trả biên nhận cũ (replay), không bản mới",
      r2.get("replay") and r2["submission_id"] == r1["submission_id"] and len(w.subs(g2)) == 1)
check("G10 cùng khoá khác nội dung: submission_conflict", r3.get("code") == "submission_conflict")
check("G20 lời gọi ngoài lượt có trợ lý: no_turn / not_agent_turn",
      R.submit_deliverable(None, {"path": DELIV, "content": GOOD}, w.deps())["code"] == "no_turn"
      and R.submit_deliverable(turn_context.make("dashboard", session_id="x", message_id=1),
                               {"path": DELIV, "content": GOOD}, w.deps())["code"] == "not_agent_turn")
R.apply_command(w.store, w.owner, g2.id, "revoke_grant", {"expected_revision": g2.revision}, w.brain)
with w.turn(mid):
    r4 = w.submit(submission_key="k1")
    r5 = w.submit(content="mới hẳn sau thu hồi\n", submission_key="k2")
check("G46 phát lại sau thu hồi trong cùng lượt: trả biên nhận cũ với trạng thái stale, không tác động mới",
      r4.get("replay") and r4["status"] == "stale" and len(w.subs(g2)) == 1, r4)
check("G5 lời nộp mới sau thu hồi: grant_revoked, không có bản nộp", r5.get("code") == "grant_revoked", r5)

# ═══════════ G43, G30: chọn liên kết theo đúng tin; hai mục tiêu cùng đích ═══════════
w = World("g43")
for _ in range(2):
    mid0, ref0 = w.next()
    with w.turn(mid0):
        gx = w.create(mid0, ref0, hold=False)
    w.approve(gx)
ga, gb = [w.store.get(w.owner, x.id) for x in w.store.list_open(w.owner)][:2]
mid, ref = w.next()
with w.turn(mid):
    ga2 = w.revise(ga, mid, ref)
    gb2 = w.revise(gb, mid, ref)
    amb = w.submit()
    ok_b = w.submit(handoff=w.store.turn_binding(w.owner, gb2.id, gb2.revision, ref)["id"])
check("G43 hai mục tiêu cùng đích cùng tin: ambiguous_handoff; có handoff thì chọn đúng",
      amb.get("code") == "ambiguous_handoff" and ok_b.get("ok") and ok_b["goal_id"] == gb2.id, (amb, ok_b))
midx, refx = w.next()
with w.turn(midx):
    other = w.submit()
check("G30 tin khác của cùng phiên không thấy liên kết của tin trước", other.get("code") == "no_open_handoff")
with w.turn(mid):
    g44 = w.submit(path="Inbox/khac.md", submission_key="k1")
check("G44 cùng khoá tuỳ chọn, cùng bytes, khác đích: không trả biên nhận cũ (đích ngoài phạm vi của lượt)",
      g44.get("code") == "path_not_in_scope", g44)

# ═══════════ G29, G70, G80 tới G84: thứ tự quyền do kho cấp ═══════════
w, g = granted_world("g29")
mid, ref = w.next()
seq_turn = w.store.authority_seq()
with w.turn(mid, seq=seq_turn):
    g2 = w.revise(g, mid, ref, seq=seq_turn)
    R.apply_command(w.store, w.owner, g2.id, "revoke_grant", {"expected_revision": g2.revision}, w.brain)
    R.apply_command(w.store, w.owner, g2.id, "resume", {}, w.brain)
    late = w.submit(content="sau cấp lại\n")
    g3 = w.revise(w.store.get(w.owner, g2.id), mid, ref, understanding="sửa thêm trong lượt cũ", seq=seq_turn)
    b3 = w.store.turn_binding(w.owner, g3.id, g3.revision, ref)
check("G29 thu hồi rồi cấp lại khi lượt còn sống: lượt cũ không nộp được", late.get("code") == "grant_revoked", late)
check("G70 lượt cũ sửa mục tiêu để lấy liên kết mới: không có liên kết (cổng ghim gốc, không do UNIQUE)",
      b3 is None and w.scope(g3)["state"] == "granted")

w, g = granted_world("g80")
mid, ref = w.next()
seq_turn = w.store.authority_seq()
R.apply_command(w.store, w.owner, g.id, "revoke_grant", {"expected_revision": g.revision}, w.brain)
R.apply_command(w.store, w.owner, g.id, "resume", {}, w.brain)
with w.turn(mid, seq=seq_turn):
    g2 = w.revise(w.store.get(w.owner, g.id), mid, ref, seq=seq_turn)
    first = w.store.turn_binding(w.owner, g2.id, g2.revision, ref)
    late = w.submit()
check("G80/G81 lượt chưa chạm mục tiêu, thu hồi và cấp lại sau ảnh chụp: lần chạm đầu không nhận gốc mới",
      first is None and late.get("code") in ("no_open_handoff", "path_not_in_scope") and w.scope(g2)["state"] == "granted",
      (first, late))
mid2, ref2 = w.next()
with w.turn(mid2):
    g3 = w.revise(g2, mid2, ref2, understanding="G82 lượt mới")
    b_ok = w.store.turn_binding(w.owner, g3.id, g3.revision, ref2)
check("G82 đối chứng: lượt mới chụp SAU lần cấp lại thì nhận liên kết grant", b_ok is not None
      and b_ok["authority"] == "grant")
mid3, ref3 = w.next()
with w.turn(mid3, seq=-1):
    g4 = w.revise(g3, mid3, ref3, understanding="G84 ảnh chụp lỗi", seq=-1)
    b_fail = w.store.turn_binding(w.owner, g4.id, g4.revision, ref3)
check("G84 ảnh chụp lỗi (-1): không mở liên kết grant dưới gốc có sẵn", b_fail is None)
# Giờ máy không tham gia: gốc mới mang seq lớn hơn dù created_at bị đặt lùi về quá khứ.
_c = sqlite3.connect(str(w.store.path))
_c.execute("UPDATE grants SET created_at=0 WHERE kind='root'")
_c.commit()
_c.close()
mid4, ref4 = w.next()
seq4 = w.store.authority_seq()
R.apply_command(w.store, w.owner, g4.id, "revoke_grant", {"expected_revision": g4.revision}, w.brain)
R.apply_command(w.store, w.owner, g4.id, "resume", {}, w.brain)
_c = sqlite3.connect(str(w.store.path))
_c.execute("UPDATE grants SET created_at=0")
_c.commit()
_c.close()
with w.turn(mid4, seq=seq4):
    g5 = w.revise(w.store.get(w.owner, g4.id), mid4, ref4, understanding="G81 đồng hồ lùi", seq=seq4)
check("G81 created_at lùi về 0 (giả đồng hồ lùi): vẫn không nhận gốc cấp lại sau ảnh chụp",
      w.store.turn_binding(w.owner, g5.id, g5.revision, ref4) is None)

# ═══════════ G60: lượt còn sống nộp tiếp sau khi chủ dự án đã cho phép ═══════════
w = World("g60")
mid, ref = w.next()
seq60 = w.store.authority_seq()
with w.turn(mid, seq=seq60):
    g = w.create(mid, ref, seq=seq60)
    w.submit()
    w.approve(g)
    late = w.submit(content="thêm sau khi cho phép\n", submission_key="sau")
    g2 = w.revise(w.store.get(w.owner, g.id), mid, ref, seq=seq60)
    b2 = w.store.turn_binding(w.owner, g2.id, g2.revision, ref)
check("G60 lượt chat còn sống sau khi chủ dự án cho phép: scope_decided; sửa thêm không có liên kết dưới gốc mới",
      late.get("code") == "scope_decided" and b2 is None, (late, b2))

# ═══════════ G31, G32, G33: thứ tự mốc commit với thu hồi ═══════════
w, g = granted_world("g31")
mid, ref = w.next()
with w.turn(mid):
    g2 = w.revise(g, mid, ref)
    rb = w.submit()
sub = w.store.submission(w.owner, rb["submission_id"])
it = w.store.publish_intent(w.p, sub["id"], DELIV, None, {})
R.apply_command(w.store, w.owner, g2.id, "revoke_grant", {"expected_revision": g2.revision}, w.brain)
cm = w.store.publish_commit(w.p, it["action_id"], lambda: None)
check("G31 thu hồi sau ý định, trước mốc commit: đăng bị huỷ, file không đổi, bản nộp stale",
      it["status"] == "intent" and cm["status"] == "aborted" and not w.target().exists()
      and w.store.submission(w.owner, sub["id"])["status"] == "stale", (it, cm))

w, g = granted_world("g32")
mid, ref = w.next()
with w.turn(mid):
    g2 = w.revise(g, mid, ref)
    rb = w.submit()
sub = w.store.submission(w.owner, rb["submission_id"])
it = w.store.publish_intent(w.p, sub["id"], DELIV, None, {})
cm = w.store.publish_commit(w.p, it["action_id"], lambda: None)
R.apply_command(w.store, w.owner, g2.id, "revoke_grant", {"expected_revision": g2.revision}, w.brain)
check("G32 mốc commit trước thu hồi: bản nộp không bị đổi thành stale bởi thu hồi",
      w.store.submission(w.owner, sub["id"])["status"] == "publishing")
w.target().parent.mkdir(parents=True, exist_ok=True)
w.target().write_text(GOOD, encoding="utf-8")
fin = w.store.publish_finish(w.p, it["action_id"], R._sha(GOOD.encode("utf-8")))
with w.turn(mid):
    again = w.submit(content="sau thu hồi\n", submission_key="x")
check("G32 hoàn tất tác động đã commit (luật tác động đã commit), lần nộp sau bị chặn",
      cm["status"] == "committed" and fin["status"] == "published" and again.get("code") == "grant_revoked", (cm, fin))

w, g = granted_world("g33")
mid, ref = w.next()
with w.turn(mid):
    g2 = w.revise(g, mid, ref)
    rb = w.submit()
w.target().parent.mkdir(parents=True, exist_ok=True)
w.target().write_text(GOOD, encoding="utf-8")
R.apply_command(w.store, w.owner, g2.id, "revoke_grant", {"expected_revision": g2.revision}, w.brain)
it = w.store.publish_intent(w.p, rb["submission_id"], DELIV, R._sha(GOOD.encode("utf-8")), {})
check("G33 nhánh same sau thu hồi: không tạo baseline", it["status"] in ("not_candidate", "stale")
      and w.store.published(w.owner, g2.id, DELIV) is None, it)

# ═══════════ G72: host_publish vẫn chạy đủ cổng (tạm dừng) ═══════════
w, g = granted_world("g72")
mid, ref = w.next()
with w.turn(mid):
    g2 = w.revise(g, mid, ref)
    rb = w.submit()
w.store.set_paused(w.owner, g2.id, True)
pub = R.host_publish(w.store.get(w.owner, g2.id), w.store.submission(w.owner, rb["submission_id"]), w.deps(), w.clock())
check("G72 tạm dừng: không đăng dù liên kết hợp lệ", pub["status"] == "held" and not w.target().exists(), pub)

# ═══════════ G62, G64, G65, G66: khởi động lại và đối soát ═══════════
w, g = granted_world("g62")
mid, ref = w.next()
with w.turn(mid):
    g2 = w.revise(g, mid, ref)
    rb = w.submit()
_boot = R.BOOT_ID
R.BOOT_ID = "tien-trinh-moi"
w.clock.t += R.HANDOFF_HOLD_S + 1
w.adv()
R.BOOT_ID = _boot
b = w.store.turn_binding(w.owner, g2.id, g2.revision, ref)
check("G62 khởi động lại sau khi chèn candidate: liên kết sealed rồi closed, đăng và tiếp nhận, 0 lượt model",
      w.target().read_text(encoding="utf-8") == GOOD and w.eng.queries == 0
      and w.store.submission(w.owner, rb["submission_id"])["adopted_at"] and b["status"] == "closed", b)

w, g = granted_world("g64")
mid, ref = w.next()
with w.turn(mid):
    g2 = w.revise(g, mid, ref)
    rb = w.submit()
sub = w.store.submission(w.owner, rb["submission_id"])
it = w.store.publish_intent(w.p, sub["id"], DELIV, None, {})
w.store.publish_commit(w.p, it["action_id"], lambda: None)
w.target().parent.mkdir(parents=True, exist_ok=True)
w.target().write_text(GOOD, encoding="utf-8")
w.store.publish_finish(w.p, it["action_id"], R._sha(GOOD.encode("utf-8")))
R._reconcile(w.store.get(w.owner, g2.id), w.deps(), w.clock())
R._reconcile(w.store.get(w.owner, g2.id), w.deps(), w.clock())
check("G64 đã đăng, chưa tiếp nhận: đối soát tiếp nhận đúng một lần (một sự kiện, một bằng chứng chat_output)",
      len(w.events(g2, "artifact_adopted")) == 1
      and len(w.store.evidence_for(w.owner, g2.id, g2.revision, kind="chat_output")) == 1
      and len([r for r in w.store.reasons(w.owner, g2.id, state=None) if r["code"] == "handoff_done"]) == 1)

w, g = granted_world("g65")
mid, ref = w.next()
with w.turn(mid):
    g2 = w.revise(g, mid, ref)
    rb = w.submit()
R.apply_command(w.store, w.owner, g2.id, "revoke_grant", {"expected_revision": g2.revision}, w.brain)
_boot = R.BOOT_ID
R.BOOT_ID = "tien-trinh-moi-2"
w.clock.t += R.HANDOFF_HOLD_S + 1
w.adv()
R.BOOT_ID = _boot
check("G65 thu hồi trước khi đối soát: không đăng, bản nộp stale, không ghim sang quyền mới",
      not w.target().exists() and w.store.submission(w.owner, rb["submission_id"])["status"] == "stale")

w, g = granted_world("g66")
mid, ref = w.next()
with w.turn(mid):
    g2 = w.revise(g, mid, ref)
R.handoff_after_turn(g2.id, ref, w.deps())
with w.turn(mid):
    sealed = w.submit()
check("G66 lời nộp muộn sau khi lượt đã bàn giao (liên kết sealed): turn_closed", sealed.get("code") == "turn_closed",
      sealed)

# ═══════════ G67, G68, G69: nhiều revision trong một tin ═══════════
w, g = granted_world("g67")
mid, ref = w.next()
with w.turn(mid):
    g2 = w.revise(g, mid, ref, understanding="r2")
    b2 = w.store.turn_binding(w.owner, g2.id, g2.revision, ref)
    s2 = w.submit(content=GOOD + "r2\n", handoff=b2["id"])
    g3 = w.revise(g2, mid, ref, understanding="r3")
    b3 = w.store.turn_binding(w.owner, g3.id, g3.revision, ref)
    amb = w.submit(content=GOOD + "r3\n")
    s3 = w.submit(content=GOOD + "r3\n", handoff=b3["id"])
check("G67 cùng tin sửa hai lần: hai liên kết theo revision, liên kết revision cũ closed",
      b2["id"] != b3["id"] and w.store.turn_binding(w.owner, g2.id, g2.revision, ref)["status"] == "closed")
check("G85 nộp không kèm handoff khi có hai liên kết cùng đích: ambiguous_handoff; kèm mã mới thì đúng",
      amb.get("code") == "ambiguous_handoff" and s3.get("ok") and s3["revision"] == g3.revision, (amb, s3))
check("G67 bản nộp r2 superseded khi sang r3",
      w.store.submission(w.owner, s2["submission_id"])["status"] == "superseded")
it = w.store.publish_intent(w.p, s2["submission_id"], DELIV, None, {})
check("G69 bản nộp r2 không đăng được cho r3", it["status"] == "not_candidate")
with w.turn(mid):
    same = R.revise_goal(w.store, w.p, g3.id, g3.revision,
                         {"understanding": "r3", "relevant_quote": "Em lo giúp anh bản tóm tắt cuộc họp",
                          "criteria": w.proposal()["criteria"]},
                         {"message_ref": ref, "session_id": w.sid, "message_id": mid, "user_text": USER,
                          "constraints": [], "hold_until": w.clock() + 900, "authority_seq": w.store.authority_seq(),
                          **RA.ctx(w.ag())})
check("G68 phát lại lời sửa không đổi gì: không revision mới, không liên kết mới",
      same[1] == "none" and len([x for x in w.store.turn_bindings(w.owner, ref, w.ag()["agent_key"],
                                                                     w.ag()["config_version"])]) == 2)

# ═══════════ G7, G34: thu hồi khi lượt nền đang chạy; phép thử ═══════════
w, g = granted_world("g7")


def _revoke_mid():
    R.apply_command(w.store, w.owner, g.id, "revoke_grant", {"expected_revision": g.revision}, w.brain)


class RevokeEngine(Engine):
    async def query(self, prompt):
        _revoke_mid()
        async for ev in Engine.query(self, prompt):
            yield ev


e7 = RevokeEngine()
w.adv(eng=e7)
bg = [s for s in w.subs(g) if s["source"] == "background_text"]
check("G7 thu hồi khi lượt nền đang gọi engine: lượt vẫn tính, bản nộp stale, không đăng",
      e7.queries == 1 and w.store.get(w.owner, g.id).calls_used == 1 and bg and bg[0]["status"] == "stale"
      and not w.target().exists(), bg)

# ═══════════ G47, G28, G49: nâng kho từ 0.92.1; đóng băng legacy ═══════════
legacy_db = _STATE / "legacy.sqlite3"
wl = World("legacy-src")
mid, ref = wl.next()
gl = wl.create(mid, ref, hold=False)
# Dựng kho "0.92.1": xoá bảng A4 khỏi bản sao của kho này, giữ mục tiêu đang mở có trợ lý và đường sản phẩm.
src = sqlite3.connect(str(wl.store.path))
dst = sqlite3.connect(str(legacy_db))
src.backup(dst)
src.close()
for t in RS.A4_TABLES:
    dst.execute(f"DROP TABLE IF EXISTS {t}")
dst.commit()
dst.close()
s_legacy = RS.GoalStore(legacy_db)
bak = legacy_db.with_name(legacy_db.name + RS.A4_BACKUP_SUFFIX)
bk = sqlite3.connect(str(bak))
bk_tables = {r[0] for r in bk.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
bk.close()
st_l = s_legacy.scope_state(RA.owner(wl.brain), gl.id)
check("G47 nâng lên: có resonance.sqlite3.pre-0.93.0 đúng một bản, không có bảng A4",
      bak.is_file() and "grants" not in bk_tables and "goals" in bk_tables)
check("G28 legacy_frozen đúng _deliverable_rel lúc nâng, có quyền revision",
      st_l["state"] == "granted" and st_l["root"]["source"] == "legacy_frozen"
      and st_l["root"]["write_paths"] == [G.path_key(wl.brain, DELIV)], st_l)
RS.GoalStore(legacy_db)
_cg = sqlite3.connect(str(legacy_db))
_n_grants = _cg.execute("SELECT COUNT(*) FROM grants WHERE goal_id=?", (gl.id,)).fetchone()[0]
_cg.close()
check("G47 mở lại kho đã nâng: không chép snapshot lần hai, không đóng băng lại",
      _n_grants == 2 and len(list(_STATE.glob("legacy.sqlite3.pre-0.93.0*"))) == 1, _n_grants)
# G49: revision do mã cũ tạo (không có quyền revision) sau khi nâng lại: không tự cấp.
cc = sqlite3.connect(str(legacy_db))
fr = cc.execute("SELECT frame_json FROM goal_revisions WHERE goal_id=? ORDER BY revision DESC LIMIT 1",
                (gl.id,)).fetchone()[0]
cc.execute("INSERT INTO goal_revisions VALUES(?,?,?,?,?,?,?)", (gl.id, 2, "", fr, "mã cũ", "agent:x", time.time()))
cc.execute("UPDATE goals SET revision=2 WHERE id=?", (gl.id,))
cc.commit()
cc.close()
st49 = s_legacy.scope_state(RA.owner(wl.brain), gl.id)
st49b = s_legacy.ensure_scope_request(RA.owner(wl.brain), gl.id)
check("G49 revision mã cũ tạo sau khi nâng lại: không tự cấp quyền, chỉ ghi yêu cầu chờ chủ dự án",
      st49["state"] == "missing" and st49b["state"] == "pending" and st49b["grant"] is None, (st49, st49b))

# ═══════════ G86: đối soát tác động đã commit dưới quyền đã thu hồi ═══════════
w, g = granted_world("g86")
mid, ref = w.next()
with w.turn(mid):
    g2 = w.revise(g, mid, ref)
    rb = w.submit()
    rc = w.submit(content=GOOD + "bản khác\n", submission_key="khac")
sub = w.store.submission(w.owner, rb["submission_id"])
it = w.store.publish_intent(w.p, sub["id"], DELIV, None, {}, now=w.clock())
w.store.publish_commit(w.p, it["action_id"], lambda: None)
R.apply_command(w.store, w.owner, g2.id, "revoke_grant", {"expected_revision": g2.revision}, w.brain)
w.clock.t += R.LEASE_EXTRA_S + 5
R._reconcile(w.store.get(w.owner, g2.id), w.deps(), w.clock())
acts = [x for x in w.store.actions(w.owner, g2.id) if x["kind"] == "publish"]
check("G86 đối soát tác động đã commit dưới quyền đã thu hồi: chỉ hoàn tất đúng hành động đó, không mở đăng mới",
      w.target().read_text(encoding="utf-8") == GOOD and len(acts) == 1 and acts[0]["status"] == "succeeded"
      and w.store.submission(w.owner, rc["submission_id"])["status"] == "stale", acts)

# ═══════════ G34: phép thử ghim quyền vào liên kết experiment; thu hồi giữa phép thử thì lượt thử kế tiếp dừng ═══════════
w, g = granted_world("g34")
pin = RA.pin(w.store, w.brain)
exp = w.store.begin_experiment(w.p, g.id, g.revision, "work.v1", "work.checklist.v1", 2, 10, {}, agent=pin)
check("G34 phép thử dưới quyền hiệu lực: giữ chỗ, có liên kết experiment",
      exp and w.store.binding_block(w.p, "experiment", exp) == "")
R.apply_command(w.store, w.owner, g.id, "revoke_grant", {"expected_revision": g.revision}, w.brain)
stop = R._trial_stop(w.store.get(w.owner, g.id), w.deps(), pin, None, exp)
check("G34 thu hồi giữa phép thử: cổng lượt thử kế tiếp dừng (tạm dừng hay grant_gate), không gọi model",
      bool(stop) and w.eng.queries == 0, stop)
try:
    w.store.begin_experiment(w.p, g.id, g.revision, "work.v1", "work.checklist.v1", 2, 10, {}, agent=pin)
    _exp2 = "opened"
except RS.GrantError as e:
    _exp2 = str(e)
check("G34 sau thu hồi không mở được phép thử mới", _exp2 == "grant_revoked", _exp2)

# ═══════════ G40 (một phần): tiến trình chết giữa ý định và mốc commit ═══════════
w, g = granted_world("g40")
mid, ref = w.next()
with w.turn(mid):
    g2 = w.revise(g, mid, ref)
    rb = w.submit()
it = w.store.publish_intent(w.p, rb["submission_id"], DELIV, None, {}, now=w.clock())
w.clock.t += R.LEASE_EXTRA_S + 5
R._reconcile(w.store.get(w.owner, g2.id), w.deps(), w.clock())
act = w.store.get_action(w.owner, it["action_id"])
check("G40 có ý định, chưa qua mốc commit, tiến trình chết: đối soát huỷ đăng, bản nộp về candidate, file không đổi",
      act["status"] == "cancelled" and (act["receipt"] or {}).get("error_code") == "aborted"
      and w.store.submission(w.owner, rb["submission_id"])["status"] == "candidate" and not w.target().exists(), act)
w.adv()
check("G40 lần thức sau đăng lại bản nộp đó, không gọi model", w.target().read_text(encoding="utf-8") == GOOD
      and w.eng.queries == 0)

# ═══════════ Hồi quy theo review mã nội bộ (sáu lỗi) ═══════════
# R1: đường sản phẩm có `.`/đoạn rỗng không được lọt thành "không cần phạm vi".
w = World("r1")
try:
    w.create(*w.next(), path="./Inbox/ban-tom-tat.md")
    _r1 = "created"
except R.GoalRejected:
    _r1 = "rejected"
check("R1 lập mục tiêu với đường ./Inbox/x.md: bị từ chối ngay", _r1 == "rejected", _r1)
mid, ref = w.next()
with w.turn(mid):
    g = w.create(mid, ref)
_c = sqlite3.connect(str(w.store.path))
fr = json.loads(_c.execute("SELECT frame_json FROM goal_revisions WHERE goal_id=?", (g.id,)).fetchone()[0])
fr["criteria"][0]["params"]["path"] = "./Inbox/ban-tom-tat.md"
_c.execute("UPDATE goal_revisions SET frame_json=? WHERE goal_id=?", (json.dumps(fr, ensure_ascii=False), g.id))
_c.commit()
_c.close()
w.target().parent.mkdir(parents=True, exist_ok=True)
w.target().write_text(GOOD, encoding="utf-8")
R.note_turn_event(ref, w.brain, {"type": "tool_call", "name": "Write", "id": "r1w",
                                 "input": {"file_path": str(w.target()), "content": GOOD}})
R.note_turn_event(ref, w.brain, {"type": "tool_result", "tool_use_id": "r1w", "is_error": False})
r1h = R.handoff_after_turn(g.id, ref, w.deps())
w.clock.t += R.HANDOFF_HOLD_S + 1
w.adv()
check("R1 đường cũ có `./` trong kho: phạm vi invalid (chặn), không tiếp nhận Write, không baseline, không gọi model",
      w.scope(g)["state"] == "invalid" and w.store.published(w.owner, g.id, "./Inbox/ban-tom-tat.md") is None
      and not w.events(g, "artifact_adopted") and w.eng.queries == 0
      and (w.store.run_state(w.owner, g.id) or {}).get("block_reason") == "path_rejected", (r1h, w.scope(g)["state"]))

# R2: yêu cầu chờ của revision cũ không làm ensure_scope_request vỡ khoá duy nhất.
w = World("r2")
mid, ref = w.next()
g = w.create(mid, ref, hold=False)
_c = sqlite3.connect(str(w.store.path))
_fr = _c.execute("SELECT frame_json FROM goal_revisions WHERE goal_id=?", (g.id,)).fetchone()[0]
_c.execute("INSERT INTO goal_revisions VALUES(?,?,?,?,?,?,?)", (g.id, 2, "", _fr, "mã cũ", "agent:x", time.time()))
_c.execute("UPDATE goals SET revision=2 WHERE id=?", (g.id,))
_c.commit()
_c.close()
try:
    st2 = w.store.ensure_scope_request(w.owner, g.id)
    _r2 = st2["state"]
except Exception as e:  # noqa: BLE001
    _r2 = f"{type(e).__name__}: {e}"
w.adv()
check("R2 revision mã cũ tạo khi còn yêu cầu chờ của revision trước: thay yêu cầu, chờ cho phép, không lỗi",
      _r2 == "pending" and w.scope(g)["request"]["revision"] == 2 and w.eng.queries == 0, _r2)

# R3: os.replace lỗi sau mốc commit: không chốt xung đột; đối soát hoàn tất.
w, g = granted_world("r3")
mid, ref = w.next()
with w.turn(mid):
    g2 = w.revise(g, mid, ref)
    rb = w.submit()
_real_replace = R.os.replace


def _busy(src, dst):
    raise PermissionError("file đang mở")


R.os.replace = _busy
try:
    pub3 = R.host_publish(w.store.get(w.owner, g2.id), w.store.submission(w.owner, rb["submission_id"]), w.deps(),
                          w.clock())
finally:
    R.os.replace = _real_replace
s3 = w.store.submission(w.owner, rb["submission_id"])
check("R3 thay file lỗi sau mốc commit: không chốt conflict, bản nộp vẫn publishing",
      pub3["status"] == "uncertain" and s3["status"] == "publishing", (pub3, s3["status"]))
w.clock.t += R.LEASE_EXTRA_S + 5
R._reconcile(w.store.get(w.owner, g2.id), w.deps(), w.clock())
check("R3 đối soát theo luật tác động đã commit: thay file từ bản nháp, published, tiếp nhận",
      w.target().read_text(encoding="utf-8") == GOOD
      and w.store.submission(w.owner, rb["submission_id"])["status"] == "published"
      and w.store.submission(w.owner, rb["submission_id"])["adopted_at"])

# R4: chốt guard không bị cổng của bàn giao hay Cho phép ghi đè.
w, g = granted_world("r4")
mid, ref = w.next()
with w.turn(mid):
    g2 = w.revise(g, mid, ref)
    w.submit()
_c = sqlite3.connect(str(w.store.path))
_c.execute("UPDATE goals SET run_state='blocked', block_reason='guard' WHERE id=?", (g2.id,))
_c.commit()
_c.close()
r4h = R.handoff_after_turn(g2.id, ref, w.deps())
check("R4 mục tiêu đã chốt guard: bàn giao không đăng, chốt guard giữ nguyên",
      r4h == "submission_held" and not w.target().exists()
      and (w.store.run_state(w.owner, g2.id) or {}).get("block_reason") == "guard", r4h)

# R5: đang thu hồi, lời sửa của model không dựng lại thẻ Cho phép; Tiếp tục mới cấp lại.
w, g = granted_world("r5")
R.apply_command(w.store, w.owner, g.id, "revoke_grant", {"expected_revision": g.revision}, w.brain)
mid, ref = w.next()
with w.turn(mid):
    g2 = w.revise(w.store.get(w.owner, g.id), mid, ref, understanding="model sửa khi đang thu hồi")
    b5 = w.store.turn_binding(w.owner, g2.id, g2.revision, ref)
check("R5 đang thu hồi, model sửa mục tiêu: vẫn revoked, không có yêu cầu mới, lượt không có liên kết",
      w.scope(g2)["state"] == "revoked" and w.scope(g2)["request"] is None and b5 is None, w.scope(g2)["state"])
R.apply_command(w.store, w.owner, g2.id, "resume", {}, w.brain)
check("R5 Tiếp tục: cấp lại gốc mới cho revision hiện tại", w.scope(g2)["state"] == "granted"
      and w.scope(g2)["root"]["source_ref"].get("regrant_of"))

# ═══════════ Hồi quy review mã A4 vòng 1 (đi qua handoff_after_turn, tick thật, mở lại kho) ═══════════
def _has(w, text):
    """File đích có đúng nội dung (thiếu file là False, không ném lỗi: ca đối chứng trên head cũ chạy hết)."""
    return w.target().is_file() and w.target().read_text(encoding="utf-8") == text


def _fit(w, g, kind):
    cur = w.store.get(w.owner, g.id)
    return R.apply_feedback(w.store, w.owner, g.id, kind, {"expected_revision": cur.revision}, w.brain)


def _with_before_commit(w, fn):
    """Chạy `fn` NGAY TRƯỚC giao dịch mốc commit (đúng chỗ can thiệp của người dùng có thể đến)."""
    orig = w.store.publish_commit

    def wrapped(*a, **kw):
        fn()
        return orig(*a, **kw)
    w.store.publish_commit = wrapped
    return lambda: setattr(w.store, "publish_commit", orig)


# P1-1: "Chưa đúng ý" ghi xong trước mốc commit thì không đăng; đổi lại "Đúng ý" thì đăng, không gọi model.
w, g = granted_world("c1p1")
mid, ref = w.next()
with w.turn(mid):
    g2 = w.revise(g, mid, ref)
    rb = w.submit()
undo = _with_before_commit(w, lambda: _fit(w, g2, "goal_fit_rejected"))
h1 = R.handoff_after_turn(g2.id, ref, w.deps())
undo()
check("V1-P1 'Chưa đúng ý' trước mốc commit: không đăng, bản nộp giữ candidate, không báo đã đăng",
      not w.target().exists() and w.store.submission(w.owner, rb["submission_id"])["status"] == "candidate"
      and h1 != "submission_published", h1)
_fit(w, g2, "goal_fit_confirmed")
w.clock.t += 60
w.adv()
check("V1-P1 đổi lại 'Đúng ý': lần thức sau đăng đúng bản đó, 0 lượt model",
      _has(w, GOOD) and w.eng.queries == 0
      and w.store.submission(w.owner, rb["submission_id"])["status"] == "published")

w, g = granted_world("c1p1same")
mid, ref = w.next()
with w.turn(mid):
    g2 = w.revise(g, mid, ref)
    rb = w.submit()
w.target().parent.mkdir(parents=True, exist_ok=True)
w.target().write_text(GOOD, encoding="utf-8")
_fit(w, g2, "goal_fit_rejected")
it = w.store.publish_intent(w.p, rb["submission_id"], DELIV, R._sha(GOOD.encode("utf-8")), {})
check("V1-P1 'Chưa đúng ý' trước nhánh same: không ghi mốc, bản nộp giữ candidate",
      it["status"] == "held" and it.get("reason") == "fit_rejected"
      and w.store.published(w.owner, g2.id, DELIV) is None
      and w.store.submission(w.owner, rb["submission_id"])["status"] == "candidate", it)

w, g = granted_world("c1p1ok")
mid, ref = w.next()
with w.turn(mid):
    g2 = w.revise(g, mid, ref)
    w.submit()
_fit(w, g2, "goal_fit_confirmed")
check("V1-P1 đối chứng 'Đúng ý': bàn giao đăng bình thường",
      R.handoff_after_turn(g2.id, ref, w.deps()) == "submission_published" and w.target().is_file())


def _committed_with_replace_failure(name):
    w, g = granted_world(name)
    mid, ref = w.next()
    with w.turn(mid):
        g2 = w.revise(g, mid, ref)
        rb = w.submit()
    real = R.os.replace
    R.os.replace = lambda s, d: (_ for _ in ()).throw(PermissionError("file đang mở"))
    try:
        pub = R.host_publish(w.store.get(w.owner, g2.id), w.store.submission(w.owner, rb["submission_id"]), w.deps(),
                             w.clock())
    finally:
        R.os.replace = real
    return w, g2, rb, pub


def settle(w, g):
    """Một lần thức của lịch `settle` (đúng đường scheduler gọi cho lịch này): chỉ đối soát lần đăng đã chốt."""
    return asyncio.run(R.advance(g.id, {"kind": "settle"}, w.deps()))


# P2-1: lỗi I/O tạm thời ở MỘT hay NHIỀU lần đối soát vẫn phục hồi được, đúng một lần; có khởi động lại xen giữa.
w, g2, rb, pub = _committed_with_replace_failure("c1p21")
real = R.os.replace
R.os.replace = lambda s, d: (_ for _ in ()).throw(PermissionError("vẫn đang mở"))
try:
    for _ in range(3):
        w.clock.t += 3700
        settle(w, g2)
finally:
    R.os.replace = real
mid_state = w.store.submission(w.owner, rb["submission_id"])["status"]
act = w.store.get_action(w.owner, pub["action_id"])
check("V1-P2-1 lỗi khoá file lặp ở đối soát: không chốt conflict, hành động vẫn chạy, có giãn cách",
      pub["status"] == "uncertain" and mid_state == "publishing" and act["status"] == "running"
      and int(act["receipt"].get("recovery_attempts") or 0) >= 2, (mid_state, act))
w.store = RS.GoalStore(w.store.path)          # khởi động lại xen giữa
w.clock.t += 3700
settle(w, g2)
w.clock.t += 3700
settle(w, g2)
s_fin = w.store.submission(w.owner, rb["submission_id"])
check("V1-P2-1 hết khoá (sau khởi động lại): hoàn tất đúng một lần, published, tiếp nhận, 0 lượt model",
      _has(w, GOOD) and s_fin["status"] == "published" and s_fin["adopted_at"]
      and len([e for e in w.events(g2, "artifact_adopted")]) == 1 and w.eng.queries == 0,
      (s_fin["status"], s_fin["adopted_at"], len(w.events(g2, "artifact_adopted")), w.eng.queries, w.target().exists()))

w, g2, rb, pub = _committed_with_replace_failure("c1p21x")
w.target().parent.mkdir(parents=True, exist_ok=True)
w.target().write_text("anh sửa tay\n", encoding="utf-8")
w.clock.t += 3700
settle(w, g2)
check("V1-P2-1 đối chứng: đích thật sự bị sửa thì giữ file người dùng và chốt conflict",
      w.target().read_text(encoding="utf-8") == "anh sửa tay\n"
      and w.store.submission(w.owner, rb["submission_id"])["status"] == "conflict")

# P2-2: thu hồi (tạm dừng) sau commit: scheduler thật vẫn hoàn tất qua lịch settle, kể cả sau khi mở lại kho.
for variant in ("not_replaced", "replaced_unrecorded"):
    w, g2, rb, pub = _committed_with_replace_failure("c1p22" + variant[:3])
    if variant == "replaced_unrecorded":
        w.target().parent.mkdir(parents=True, exist_ok=True)
        w.target().write_bytes(GOOD.encode("utf-8"))      # đúng bytes host sẽ ghi (không đổi xuống dòng)
    R.apply_command(w.store, w.owner, g2.id, "revoke_grant", {"expected_revision": g2.revision}, w.brain)
    w.store = RS.GoalStore(w.store.path)
    w.clock.t += 3700
    n1 = asyncio.run(R.tick(w.store, w.clock(), lambda bid: w.deps()))
    w.clock.t += 3700
    n2 = asyncio.run(R.tick(w.store, w.clock(), lambda bid: w.deps()))
    acts = [x for x in w.store.actions(w.owner, g2.id) if x["kind"] == "publish"]
    check(f"V1-P2-2 thu hồi sau commit ({variant}): tick thật hoàn tất đúng một lần, không lịch thừa, 0 lượt model",
          n1 == 1 and n2 == 0 and _has(w, GOOD) and len(acts) == 1
          and acts[0]["status"] == "succeeded" and not [x for x in w.store.wakes(w.owner, g2.id) if x["kind"] == "settle"]
          and w.eng.queries == 0 and w.store.get(w.owner, g2.id).paused, (n1, n2, acts))

w, g2, rb, pub = _committed_with_replace_failure("c1p22cancel")
w.store.cancel(w.owner, g2.id, g2.revision)
w.clock.t += 3700
nc = asyncio.run(R.tick(w.store, w.clock(), lambda bid: w.deps()))
check("V1-P2-2 mục tiêu đã huỷ sau commit: lịch settle vẫn hoàn tất lần đăng đã chốt",
      nc == 1 and _has(w, GOOD)
      and w.store.get(w.owner, g2.id).status == "cancelled")

w, g = granted_world("c1p22pre")
mid, ref = w.next()
with w.turn(mid):
    g2 = w.revise(g, mid, ref)
    rb = w.submit()
undo = _with_before_commit(w, lambda: R.apply_command(w.store, w.owner, g2.id, "revoke_grant",
                                                      {"expected_revision": g2.revision}, w.brain))
R.handoff_after_turn(g2.id, ref, w.deps())
undo()
w.clock.t += 3700
asyncio.run(R.tick(w.store, w.clock(), lambda bid: w.deps()))
check("V1-P2-2 đối chứng: thu hồi TRƯỚC mốc commit vẫn chặn, tick không đăng",
      not w.target().exists() and w.store.submission(w.owner, rb["submission_id"])["status"] == "stale")

# ═══════════ Hồi quy review mã A4 vòng 2 (phục hồi đăng; tick thật có cả lịch thường và settle) ═══════════
def _ticks(w, n=2, step=3700):
    out = []
    for _ in range(n):
        w.clock.t += step
        out.append(asyncio.run(R.tick(w.store, w.clock(), lambda bid: w.deps())))
    return out


def _deny_read(path_str):
    """Chặn đọc ĐÚNG một file (file nháp) bằng PermissionError; trả hàm gỡ."""
    real = Path.read_bytes

    def fake(self):
        if str(self) == path_str:
            raise PermissionError("file nháp đang bị khoá")
        return real(self)
    Path.read_bytes = fake
    return lambda: setattr(Path, "read_bytes", real)


def _deny_replace_target(w):
    real = R.os.replace

    def fake(src, dst):
        if Path(dst) == w.target():
            raise PermissionError("file đích đang mở")
        return real(src, dst)
    R.os.replace = fake
    return lambda: setattr(R.os, "replace", real)


def _handoff_with_failing_replace(name):
    """Bàn giao thật một bản nộp hợp lệ, thay file đích lỗi sau mốc commit: bản nộp ở `publishing`."""
    w, g = granted_world(name)
    mid, ref = w.next()
    with w.turn(mid):
        g2 = w.revise(g, mid, ref)
        rb = w.submit()
    undo = _deny_replace_target(w)
    try:
        h = R.handoff_after_turn(g2.id, ref, w.deps())
    finally:
        undo()
    return w, g2, rb, h


# V2-P2-1: file nháp không đọc được tạm thời không phải xung đột; mất hay sai hash có lý do riêng.
w, g2, rb, h = _handoff_with_failing_replace("v2n1")
draft = w.store.submission(w.owner, rb["submission_id"])["draft_ref"]
undo_r = _deny_read(draft)
undo_t = _deny_replace_target(w)
try:
    _ticks(w, 1)
    undo_t()
    _ticks(w, 2)
finally:
    undo_r()
    undo_t()
mid_s = w.store.submission(w.owner, rb["submission_id"])
w.store = RS.GoalStore(w.store.path)
_ticks(w, 2)
fin = w.store.submission(w.owner, rb["submission_id"])
check("V2-P2-1 file nháp bị khoá (một và nhiều lần): vẫn publishing, không ghi lý do target_changed",
      h == "submission_uncertain" and mid_s["status"] == "publishing" and mid_s["status_reason"] != "target_changed",
      (h, mid_s["status"], mid_s["status_reason"]))
check("V2-P2-1 hết khoá (sau mở lại kho): đăng đúng bản gốc, tiếp nhận một lần, 0 lượt engine",
      _has(w, GOOD) and fin["status"] == "published" and fin["adopted_at"]
      and len(w.events(g2, "artifact_adopted")) == 1 and w.eng.queries == 0, (fin["status"], w.eng.queries))

w, g2, rb, h = _handoff_with_failing_replace("v2n1h")
Path(w.store.submission(w.owner, rb["submission_id"])["draft_ref"]).write_bytes(b"# bi sua sau khi nop\n")
_ticks(w, 1)
s_h = w.store.submission(w.owner, rb["submission_id"])
# Bản nháp đã mất thì việc nền được làm lại một bản mới (mục tiêu gỡ gác); điều cần giữ là bytes SAI không bao giờ lên đích.
check("V2-P2-1 bản nháp sai hash: không đăng bytes sai, rejected với lý do riêng (không phải xung đột đích)",
      not (w.target().is_file() and b"bi sua sau khi nop" in w.target().read_bytes()) and s_h["status"] == "rejected"
      and s_h["status_reason"] == "draft_hash_mismatch" and not w.events(g2, "publish_conflict"),
      (s_h["status"], s_h["status_reason"]))

w, g2, rb, h = _handoff_with_failing_replace("v2n1c")
w.target().parent.mkdir(parents=True, exist_ok=True)
w.target().write_bytes("anh sửa tay\n".encode("utf-8"))
_ticks(w, 1)
check("V2-P2-1 đối chứng: file đích thật sự bị sửa vẫn conflict, file người dùng giữ nguyên",
      _has(w, "anh sửa tay\n") and w.store.submission(w.owner, rb["submission_id"])["status"] == "conflict")

# V2-P2-2: bước tiếp nhận lỗi sau khi đã đăng: nghĩa vụ còn, settle tiếp nhận đúng một lần ở mọi trạng thái.
for state in ("active", "revoked", "cancelled", "paused"):
    w, g = granted_world("v2n2" + state[:3])
    mid, ref = w.next()
    with w.turn(mid):
        g2 = w.revise(g, mid, ref)
        rb = w.submit()
    real_adopt = RS.GoalStore.adopt_submission
    _once = {"n": 0}

    def _fail_once(self, p, sid, _real=real_adopt):
        if _once["n"] == 0:
            _once["n"] += 1
            raise sqlite3.OperationalError("database is locked")
        return _real(self, p, sid)
    RS.GoalStore.adopt_submission = _fail_once
    try:
        h2 = R.handoff_after_turn(g2.id, ref, w.deps())
    finally:
        RS.GoalStore.adopt_submission = real_adopt
    if state == "revoked":
        R.apply_command(w.store, w.owner, g2.id, "revoke_grant", {"expected_revision": g2.revision}, w.brain)
    elif state == "cancelled":
        w.store.cancel(w.owner, g2.id, g2.revision)
    elif state == "paused":
        w.store.set_paused(w.owner, g2.id, True)
    w.store = RS.GoalStore(w.store.path)
    t2 = _ticks(w, 3)
    s2 = w.store.submission(w.owner, rb["submission_id"])
    check(f"V2-P2-2 tiếp nhận lỗi sau đăng ({state}): settle tiếp nhận đúng một lần, không đăng mới, 0 lượt engine",
          _has(w, GOOD) and s2["adopted_at"] and len(w.events(g2, "artifact_adopted")) == 1
          and len([x for x in w.store.actions(w.owner, g2.id) if x["kind"] == "publish"]) == 1
          and not [x for x in w.store.wakes(w.owner, g2.id) if x["kind"] == "settle"] and w.eng.queries == 0,
          (h2, t2, s2["adopted_at"], w.eng.queries))

# V2-P2-3: lần đăng đã chốt còn chờ thay file thì lịch làm việc KHÔNG gọi model; xong rồi mới xét tiếp.
w, g2, rb, h = _handoff_with_failing_replace("v2n3")
undo_t = _deny_replace_target(w)
try:
    _ticks(w, 3)
    calls_mid = w.eng.queries
    works_mid = len([x for x in w.store.actions(w.owner, g2.id) if x["kind"] == "work"])
    state_mid = (w.store.run_state(w.owner, g2.id) or {}).get("block_reason")
    w.store = RS.GoalStore(w.store.path)
    _ticks(w, 2)
finally:
    undo_t()
_ticks(w, 3)
pubs = [x for x in w.store.actions(w.owner, g2.id) if x["kind"] == "publish" and x["status"] == "succeeded"]
check("V2-P2-3 chờ thay file (lặp, có mở lại kho): không lượt engine, không action work, mục tiêu gác publish_settling",
      calls_mid == 0 and works_mid == 0 and state_mid == "publish_settling", (calls_mid, works_mid, state_mid))
check("V2-P2-3 mở khoá: bản gốc đăng đúng một lần, tiếp nhận, gỡ gác, vẫn 0 lượt engine",
      _has(w, GOOD) and len(pubs) == 1 and w.store.submission(w.owner, rb["submission_id"])["adopted_at"]
      and (w.store.run_state(w.owner, g2.id) or {}).get("block_reason") != "publish_settling" and w.eng.queries == 0,
      (len(pubs), w.eng.queries, (w.store.run_state(w.owner, g2.id) or {}).get("block_reason")))

# ═══════════ Hồi quy review mã A4 vòng 3: lỗi đăng phát sinh NGAY trong lần thức của scheduler ═══════════
# Bản nộp còn `candidate` (tiến trình bị ngắt trước bàn giao), scheduler thức và tự đăng; lỗi I/O xảy ra ngay lúc đó:
# thay file đích sau mốc commit, hay đọc file nháp trước mốc commit. Không được mở lượt model.
def _deny_draft_read(w, sid):
    return _deny_read(str(Path(w.store.submission(w.owner, sid)["draft_ref"])))


for fault in ("replace", "draft_read"):
    w, g = granted_world("v3" + fault[:3])
    mid, ref = w.next()
    with w.turn(mid):
        g2 = w.revise(g, mid, ref)
        rb = w.submit()
    sid = rb["submission_id"]
    pre = (w.store.submission(w.owner, sid)["status"], w.store.settle_pending(w.owner, g2.id))
    w.store = RS.GoalStore(w.store.path)
    undo = _deny_replace_target(w) if fault == "replace" else _deny_draft_read(w, sid)
    try:
        _ticks(w, 1)
        s1 = w.store.submission(w.owner, sid)
        st1 = (w.store.run_state(w.owner, g2.id) or {}).get("block_reason")
        pending1 = [r["code"] for r in w.store.reasons(w.owner, g2.id)]
        # Lỗi kéo dài: nhịp 30 giây trong 10 phút, có mở lại kho giữa chừng.
        busy = []
        for i in range(20):
            if i == 10:
                w.store = RS.GoalStore(w.store.path)
            busy += _ticks(w, 1, step=30)
        s2 = w.store.submission(w.owner, sid)
    finally:
        undo()
    works = len([x for x in w.store.actions(w.owner, g2.id) if x["kind"] == "work"])
    used = w.store.get(w.owner, g2.id).calls_used
    check(f"V3 lỗi {fault} ngay trong lần thức: 0 lượt engine, calls_used 0, không action work, gác publish_settling, "
          "lý do làm việc còn chờ",
          pre == ("candidate", 0) and w.eng.queries == 0 and used == 0 and works == 0 and st1 == "publish_settling"
          and pending1 and s1["status"] == ("publishing" if fault == "replace" else "candidate")
          and s2["status"] == s1["status"],
          (pre, w.eng.queries, used, works, st1, pending1, s1["status"], s2["status"]))
    check(f"V3 lỗi {fault} kéo dài: thức thưa dần (không mỗi nhịp 30 giây), không mở model",
          sum(1 for x in busy if x) <= 6 and w.eng.queries == 0, (busy, w.eng.queries))
    if fault == "draft_read":
        check("V3 file nháp bị khoá trước mốc commit: không chốt xung đột, không loại bản nộp, chưa có hành động đăng",
              not w.events(g2, "publish_conflict") and not w.events(g2, "submission_draft_lost")
              and not [x for x in w.store.actions(w.owner, g2.id) if x["kind"] == "publish"])
    for _ in range(40):
        _ticks(w, 1, step=60)
    pubs = [x for x in w.store.actions(w.owner, g2.id) if x["kind"] == "publish" and x["status"] == "succeeded"]
    fin = w.store.submission(w.owner, sid)
    check(f"V3 hết lỗi {fault}: đăng đúng bản đã giữ một lần, tiếp nhận một lần, gỡ gác, không còn lịch settle, "
          "0 lượt engine",
          _has(w, GOOD) and len(pubs) == 1 and fin["status"] == "published" and fin["adopted_at"]
          and len(w.events(g2, "artifact_adopted")) == 1
          and (w.store.run_state(w.owner, g2.id) or {}).get("block_reason") != "publish_settling"
          and not [x for x in w.store.wakes(w.owner, g2.id) if x["kind"] == "settle"] and w.eng.queries == 0,
          (len(pubs), fin["status"], w.eng.queries, (w.store.run_state(w.owner, g2.id) or {}).get("block_reason")))

# Bản nộp đang được giữ KHÔNG được tự đăng trái quyền khi mục tiêu đổi trạng thái trong lúc giữ: tạm dừng, thu hồi,
# huỷ, đổi revision (bản mới hơn ở revision mới). Hết khoá file nháp rồi vẫn không đăng bản cũ; nghĩa vụ giữ được bỏ,
# không còn lịch `settle` treo. Trong CÙNG revision, liên kết của lượt chỉ nhận một bản nộp: bản khác nội dung bị từ
# chối `submission_conflict`, nên bản đang giữ vẫn là bản hợp lệ duy nhất và được đăng đúng một lần khi hết khoá.
A_TEXT = GOOD + "\nDấu riêng của bản A.\n"
B_TEXT = GOOD + "\nDấu riêng của bản B.\n"


def _held_world(name):
    w, g = granted_world(name)
    mid, ref = w.next()
    with w.turn(mid):
        g2 = w.revise(g, mid, ref)
        rb = w.submit(content=A_TEXT)
    w.store = RS.GoalStore(w.store.path)
    undo = _deny_draft_read(w, rb["submission_id"])
    _ticks(w, 1)
    return w, g2, rb["submission_id"], undo, (mid, ref)


for change in ("paused", "revoked", "cancelled", "revision", "newer"):
    w, g2, sid, undo, (mid0, ref0) = _held_world("v3h" + change[:3])
    held0 = w.store.submission(w.owner, sid)
    try:
        if change == "paused":
            w.store.set_paused(w.owner, g2.id, True)
        elif change == "revoked":
            R.apply_command(w.store, w.owner, g2.id, "revoke_grant", {"expected_revision": g2.revision}, w.brain)
        elif change == "cancelled":
            w.store.cancel(w.owner, g2.id, g2.revision)
        elif change == "revision":
            mid, ref = w.next()
            with w.turn(mid):
                g3 = w.revise(g2, mid, ref, understanding="Bản tóm tắt cuộc họp, bản sửa lần hai")
                w.submit(content=B_TEXT)
            R.handoff_after_turn(g3.id, ref, w.deps())
        else:
            with w.turn(mid0):
                rn = w.submit(content=B_TEXT)
    finally:
        undo()
    for _ in range(40):
        _ticks(w, 1, step=60)
    sa = w.store.submission(w.owner, sid)
    text = w.target().read_text(encoding="utf-8") if w.target().is_file() else ""
    if change == "newer":
        pubs = [x for x in w.store.actions(w.owner, g2.id) if x["kind"] == "publish" and x["status"] == "succeeded"]
        check("V3 bản nộp đang giữ, lượt cùng revision nộp bản khác: bị từ chối submission_conflict, hết khoá đăng đúng "
              "bản đang giữ một lần, 0 lượt engine",
              rn.get("code") == "submission_conflict" and "bản A" in text and "bản B" not in text
              and sa["status"] == "published" and sa["adopted_at"] and len(pubs) == 1 and w.eng.queries == 0,
              (rn, sa["status"], len(pubs), w.eng.queries))
        continue
    b_expected = change == "revision"
    check(f"V3 bản nộp đang giữ rồi {change}: hết khoá không tự đăng bản cũ, bỏ giữ, không còn lịch settle"
          + (", đăng bản mới hơn" if b_expected else ", 0 lượt engine"),
          held0["status"] == "candidate" and held0["hold_until"] is not None
          and "bản A" not in text and sa["status"] != "published" and sa["hold_until"] is None
          and not [x for x in w.store.wakes(w.owner, g2.id) if x["kind"] == "settle"]
          and (("bản B" in text) if b_expected else w.eng.queries == 0),
          (held0["status"], held0["hold_until"], sa["status"], sa["hold_until"], "bản A" in text, "bản B" in text,
           w.eng.queries))

# Đối chứng: không lỗi thì cùng lần thức đăng ngay, không gác, 0 lượt engine.
w, g = granted_world("v3ctl")
mid, ref = w.next()
with w.turn(mid):
    g2 = w.revise(g, mid, ref)
    rb = w.submit()
w.store = RS.GoalStore(w.store.path)
_ticks(w, 1)
fin = w.store.submission(w.owner, rb["submission_id"])
check("V3 đối chứng không lỗi: lần thức đăng và tiếp nhận ngay, không gác, 0 lượt engine",
      fin["status"] == "published" and fin["adopted_at"] and w.eng.queries == 0
      and (w.store.run_state(w.owner, g2.id) or {}).get("block_reason") != "publish_settling")

# ═══════════ G18: không quét gì khi chưa tới hạn ═══════════
w = World("g18")
t0 = time.perf_counter()
for _ in range(5):
    w.adv()
check("G18 không có gì tới hạn: không dựng engine, nhịp rẻ", w.eng.queries == 0 and time.perf_counter() - t0 < 5)

if _fails:
    print(f"\n{len(_fails)} FAIL: {_fails}")
raise SystemExit(1 if _fails else 0)
