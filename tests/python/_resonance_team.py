"""Helper chung cho test Resonance A5 (đội một agent làm, một agent review). Kho SQLite thật, engine GIẢ có hai vai
(phân theo lời dặn hệ thống của lượt: lượt review dùng `R.REVIEW_SYSTEM`), đồng hồ giả. Mục tiêu tạo qua `form_goal` thật
(đúng đường của tool javis_goal và /goal-requests), chạy qua `R.tick` và `R.advance` thật. Không gọi model thật."""
from __future__ import annotations

import asyncio
import hashlib
import json
import tempfile
from pathlib import Path

import resonance as R
import resonance_store as RS
import _resonance_agent as RA

DELIV = "Inbox/ban-tom-tat.md"
GOOD = "# Tóm tắt\n\nMột bản tóm tắt đủ dài để qua tiêu chí, có mục Kết luận.\n\n## Kết luận\n\nXong.\n"
BAD = "# Tóm tắt\n\nChưa có phần chốt.\n"
USER = "Em lo giúp anh bản tóm tắt cuộc họp tới khi anh thấy dùng được. Ghi vào Inbox/ban-tom-tat.md."
MAKER, REVIEWER = "nguoi-lam", "nguoi-duyet"


def verdict(v="pass", oks=(True,), fixes=""):
    return json.dumps({"verdict": v, "criteria": [{"index": i, "ok": ok, "reason": "x"} for i, ok in enumerate(oks)],
                       "fixes": fixes}, ensure_ascii=False)


PASS = verdict("pass")
CHANGES = verdict("needs_changes", (False,), "Thêm mục Kết luận rõ hơn")


class Clock:
    def __init__(self, t=1_800_000_000.0):
        self.t = t

    def __call__(self):
        return self.t


class Engine:
    """Engine giả của MỘT vai. `script`: danh sách chữ trả lần lượt (hết thì lặp phần tử cuối); phần tử là dict
    {"error": "..."} thì phát sự kiện lỗi; "raise" thì ném lỗi khi dựng (không dựng được engine)."""

    def __init__(self, *script):
        self.script, self.queries, self.prompts, self.max_wall_s = list(script) or [GOOD], 0, [], None
        self.available = True
        self.hook = None          # gọi ở đầu mỗi lượt: mô phỏng việc khác xảy ra TRONG LÚC engine chạy

    def is_available(self):
        return self.available

    async def query(self, prompt):
        item = self.script[min(self.queries, len(self.script) - 1)]
        self.queries += 1
        self.prompts.append(prompt)
        if self.hook is not None:
            res = self.hook(self)
            if asyncio.iscoroutine(res):
                await res
        if isinstance(item, dict) and item.get("error"):
            yield {"type": "error", "content": item["error"]}
            return
        yield {"type": "final", "content": item, "tokens_in": 1, "tokens_out": 1}


class Evidence:
    def __init__(self):
        self.items = {}
        self.fail = False

    def put(self, goal, label, text, meta):
        if self.fail:
            raise OSError("kho bằng chứng hỏng")
        eid = f"ev_{len(self.items) + 1}"
        self.items[eid] = {"text": text, "content_hash": hashlib.sha256(text.encode("utf-8")).hexdigest()}
        return eid

    def valid(self, eid):
        return self.items.get(eid)


async def _notes(goal, kind, text, card=""):
    return True


class Team:
    """Một kho, một brain, hai trợ lý đang bật, cặp làm/review do chủ dự án chọn."""

    def __init__(self, state: Path, name: str, pair: bool = True):
        self.brain = str(Path(tempfile.mkdtemp(prefix=f"brain-a5-{name}-")).resolve())
        (Path(self.brain) / "Javis").mkdir(parents=True)
        self.state = state
        self.name = name
        self.store = RS.GoalStore(state / f"{name}.sqlite3")
        # 0.142.0 bỏ người review cố định cho mục tiêu MỚI. Các test A5 dựng lại mục tiêu kiểu cũ (có đội) để đường review
        # của mục tiêu cũ còn được kiểm; test riêng của bản 0.142.0 ở test_review_removed_0142.py.
        self.store.attach_reviewer_teams = True
        self.maker = RA.enable(self.store, self.brain, MAKER)
        self.reviewer = RA.enable(self.store, self.brain, REVIEWER)
        self.owner = RA.owner(self.brain)
        if pair:
            self.store.team_pair_set(self.owner, self.maker["agent_key"], self.reviewer["agent_key"])
        self.p = RS.Principal("agent", self.maker["agent_key"], self.brain)
        self.clock = Clock()
        self.work = Engine(GOOD)
        self.rev = Engine(PASS)
        self.ev = Evidence()
        self.mid = 0
        self.sid = f"s-{name}"
        self.factory_raise = False

    # ── engine hai vai ──
    def factory(self, system_prompt, tag):
        if system_prompt == R.REVIEW_SYSTEM:
            if self.factory_raise:
                raise RuntimeError("không dựng được engine review")
            return self.rev, {"provider": "fake", "model": "fake-1", "text_only": True}
        return self.work, {"provider": "fake", "model": "fake-1", "text_only": True}

    def deps(self):
        return R.GoalDeps(engine_factory=self.factory, budget=R.CallBudget(0), clock=self.clock, store=self.store,
                          principal=RS.Principal("agent", "javis", self.brain), brain_root=self.brain, evidence=self.ev,
                          notify=_notes)

    def reopen(self):
        """Mở lại kho (mô phỏng khởi động lại tiến trình)."""
        self.store = RS.GoalStore(self.state / f"{self.name}.sqlite3")
        self.store.attach_reviewer_teams = True
        return self.store

    def ag(self, slug=MAKER):
        return self.store.agent(self.brain, slug)

    def next(self):
        self.mid += 1
        return self.mid, R.message_ref(self.sid, self.mid)

    def proposal(self, human=False, path=DELIV):
        crit = [{"description": "Có mục Kết luận", "evaluator": "artifact_contract",
                 "params": {"path": path, "must_contain": ["Kết luận"]}}]
        if human:
            crit.append({"description": "Anh thấy dùng được", "evaluator": "human_confirmation"})
        return {"understanding": "Bản tóm tắt cuộc họp", "relevant_quote": "Em lo giúp anh bản tóm tắt cuộc họp",
                "criteria": crit, "horizon": {"kind": "review", "at_iso": "2027-01-20T09:00:00+07:00"},
                "stage": "delivery", "mode": "achieve"}

    def create(self, mid=None, ref=None, human=False, approve=True, slug=MAKER):
        if mid is None:
            mid, ref = self.next()
        d0 = R.GoalDeps(engine_factory=lambda s, t: (None, {}), budget=R.CallBudget(0), store=self.store)
        a = self.ag(slug)
        g = asyncio.run(R.form_goal(ref, {
            "principal": RS.Principal("agent", a["agent_key"], self.brain), "brain_root": self.brain,
            "session_id": self.sid, "message_id": mid, "user_text": USER, "constraints": [], "budget_calls": 4,
            "proposal": self.proposal(human), "hold_until": None, "authority_seq": self.store.authority_seq(),
            "agent_key": a["agent_key"], "agent_version": a["config_version"]}, d0))
        if approve:
            RA.approve(self.store, self.brain, g.id)
        return g

    def chat_update(self, g, content, understanding="Bản tóm tắt cuộc họp, bản sửa trong chat"):
        """Lượt chat của agent làm (đường A4 thật): sửa mục tiêu (revision mới, có bàn giao), nộp bản qua
        `submit_deliverable`, kết thúc lượt rồi bàn giao cuối lượt. Trả (revision mới, kết quả nộp, kết quả bàn giao)."""
        import turn_context
        mid, ref = self.next()
        a = self.ag()
        pa = RS.Principal("agent", a["agent_key"], self.brain)
        with RA.turn(a, self.sid, mid, USER, self.brain, slug=MAKER, store=self.store):
            cur = self.store.get(self.owner, g.id)
            g2 = R.revise_goal(self.store, pa, g.id, cur.revision,
                               {"understanding": understanding, "relevant_quote": "Em lo giúp anh bản tóm tắt cuộc họp",
                                "criteria": self.proposal()["criteria"]},
                               {"message_ref": ref, "session_id": self.sid, "message_id": mid, "user_text": USER,
                                "constraints": [], "user_unsure": False, "reason": "góp ý",
                                "hold_until": self.clock() + R.HANDOFF_HOLD_S,
                                "authority_seq": self.store.authority_seq(), "agent_key": a["agent_key"],
                                "agent_version": a["config_version"]})[0]
            sub = R.submit_deliverable(turn_context.current(), {"path": DELIV, "content": content}, self.deps())
        ho = R.handoff_after_turn(g.id, ref, self.deps())
        return g2, sub, ho

    # ── chạy ──
    def wake(self, g):
        return asyncio.run(R.advance(g.id, {"kind": "wake"}, self.deps()))

    def tick(self):
        return asyncio.run(R.tick(self.store, self.clock(), lambda bid: self.deps()))

    def run(self, g, n=12, step=0.0):
        """Thức tới khi không còn lịch tới hạn (tối đa n lần). `step`: dời đồng hồ mỗi vòng (backoff)."""
        for _ in range(n):
            w = [x for x in self.store.wakes(self.owner, g.id) if x["kind"] == "work"]
            if not w or float(w[0]["due_at"]) > self.clock():
                if step and w:
                    self.clock.t = max(self.clock.t, float(w[0]["due_at"]) + 1)
                else:
                    break
            self.wake(g)

    # ── đọc ──
    def g(self, g):
        return self.store.get(self.owner, g.id)

    def st(self, g):
        return self.store.run_state(self.owner, g.id) or {}

    def team(self, g):
        return self.store.goal_team(self.owner, g.id)

    def calls(self, g):
        t = self.team(g) or {"calls": {}}
        gg = self.g(g)
        return (t["calls"].get("maker", {}).get("used"), t["calls"].get("reviewer", {}).get("used"), gg.calls_used)

    def reviews(self, g):
        return list(reversed(self.store.reviews(self.owner, g.id, limit=50)))

    def reasons(self, g, state="pending"):
        return [(r["code"], r["source_ref"]) for r in self.store.reasons(self.owner, g.id, state=state)]

    def target(self):
        return Path(self.brain) / DELIV

    def actions(self, g, kind=None):
        return [a for a in self.store.actions(self.owner, g.id) if kind is None or a["kind"] == kind]

    def events(self, g, kind):
        return [e for e in self.store.events(self.owner, g.id) if e["kind"] == kind]
