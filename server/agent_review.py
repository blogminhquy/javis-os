"""Học trong đội (T3 phần L, 0.156.0): lượt xem xét reaction (4.4) và tự rà soát có tự áp, quay lại (8.3, 6.4).

Thiết kế: docs/superpowers/specs/2026-10-15-team-adaptive-design.md mục 3.2-3.4, 4.4, 6.4, 8, 9; hợp đồng
docs/dev/team-chat-t3-contract.md mục 3; tài liệu docs/dev/team-chat-t3-learn.md.

Lượt xem xét reaction (`serve_reaction_review(reason)`), phục vụ lý do `reaction_review` mà bộ chiếu T2 đã gom:
1. Thử khoá bận của agent KHÔNG chờ (bận thì lý do giữ `pending`, không tốn lần thử), hỏi hạn mức ngày
   (`agent_budget.try_spend`, hết thì "Chờ hạn mức"), rồi `WakeReasons.claim` (CAS + giữ chỗ sổ lượt `obligation = 0`).
2. Lời nhắc: tin bị phản hồi, reaction/lý do/góp ý của các nguồn, bài học đúng phạm vi ngữ cảnh. Engine của chính agent
   qua cùng nhà máy engine của lượt nhóm/quét (chỉ chữ, không công cụ).
3. Đầu ra có cấu trúc kiểm ĐÚNG khuôn (`parse_review`): sai khuôn hay `consumed` không nằm trong nguồn thì lượt `error`,
   lý do về `pending` (3.2).
4. Tác động theo kết quả host thật: `keep` không gửi gì ("Không cần đổi"); `lesson` ghi bài học phạm vi ngữ cảnh ("Đã điều
   chỉnh"); `ask_back`/`revise` là TIN MỚI (không sửa đè) và chỉ gửi khi bộ phán xử của agent nói `speak` ("Đã điều chỉnh"
   chỉ khi tin thật sự đã gửi, không thì "Không cần đổi" kèm "phán xử chọn im"). Ghi trạng thái lên mọi reaction trong
   `consumed`, đẩy gói WS, ghi quyết định vào `agent_pulse_events` kèm mã nguồn.

Tự rà soát (`maybe_self_review(agent_key)`), chỉ khi Cộng hưởng bật: ≥ 6 nhãn nói/im mới hay ≥ 5 tín hiệu hữu ích mới sau
`resumed_at` (và sau lần rà soát trước), cách lần trước ≥ 24 giờ. Tối đa 3 thay đổi từ danh sách đóng (`offset_set`,
`eagerness_set`, `lesson_add`, `lesson_remove`, `lesson_promote`), mỗi thay đổi dẫn mã bằng chứng đã cho xem; tự áp ngay, ghi
trước/sau, mở cửa sổ quan sát của P (`agent_pulse.apply_policy_change`), tự quay lại theo 6.4 qua hàm quay lại đã đăng ký;
không lặp thay đổi đã quay lại trong 14 ngày; không đè thiết lập chủ đang giữ. Ý ngoài phạm vi (quyền, luật chủ, mã, skill,
workflow, cấu trúc agent) chỉ thành đề xuất cho chủ. Học không bao giờ cấp quyền hay nâng trần.

Không hai vòng học cho một phản hồi: nguồn đã được lượt xem xét reaction tiêu thụ (`agent_wake_sources.consumed_at`) không
được tự rà soát đếm hay đọc lại; bằng chứng tự rà soát đã dùng ghi vào `agent_review_consumed`.
"""
from __future__ import annotations

import asyncio
import inspect
import json
import re
import secrets
import sys
import time
from contextlib import closing
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Optional

import agent_lessons as AL

try:
    from fastapi import Request  # chú thích kiểu của route phải ở mức module (annotations dạng chuỗi)
except ImportError:  # pragma: no cover - test thuần không cần fastapi
    Request = Any  # type: ignore

OUTCOMES = ("keep", "ask_back", "revise", "lesson")
LESSON_KINDS = ("presentation", "method")
REVIEW_KEYS = frozenset(("outcome", "message", "lesson", "consumed", "reason"))
CLOSED_CHANGES = ("offset_set", "eagerness_set", "lesson_add", "lesson_remove", "lesson_promote")
EAGERNESS = ("low", "medium", "high")
OFFSET_LIMIT = 0.25
MAX_CHANGES = 3
REVIEW_TIMEOUT_S = 600.0
SELF_MIN_LABELS = 6
SELF_MIN_SIGNALS = 5
SELF_GAP_S = 86400.0
SELF_BACKOFF_S = 3600.0
NO_REPEAT_S = 14 * 86400.0
MESSAGE_MAX = 4000
EXCERPT_MAX = 1200
EVIDENCE_LIMIT = 40
SOURCE_TAG = "self_review:"
# Mã im của bộ phán xử nghĩa là "chưa phán xử vì hết hạn mức hay chạm trần", không phải "chọn im" (review T3 L P2-1).
QUOTA_SILENCE = ("waiting_quota", "judge_cap", "server_ceiling")
APPLYING_STALE_S = 600.0    # thay đổi kẹt ở `applying` quá 10 phút: tiến trình chết giữa lúc áp
QUOTA_BACKOFF_S = 600.0     # hết hạn mức: phục vụ lại lý do sau 10 phút (không phải mỗi nhịp 30 giây)
ENGINE_BACKOFF_S = 300.0    # engine chưa dựng được: sau 5 phút
PROPOSAL_AREAS = ("permissions", "owner_rule", "code", "skill", "workflow", "structure", "other")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS agent_review_state(
  agent_key TEXT PRIMARY KEY, last_review_at REAL, last_attempt_at REAL, updated_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS agent_review_changes(
  id INTEGER PRIMARY KEY AUTOINCREMENT, review_ref TEXT NOT NULL, agent_key TEXT NOT NULL, context_ref TEXT NOT NULL,
  kind TEXT NOT NULL, signature TEXT NOT NULL, before_json TEXT NOT NULL DEFAULT '{}', after_json TEXT NOT NULL DEFAULT '{}',
  evidence_json TEXT NOT NULL DEFAULT '[]', why TEXT NOT NULL DEFAULT '', status TEXT NOT NULL,
  reject_reason TEXT NOT NULL DEFAULT '', policy_change_id INTEGER, created_at REAL NOT NULL, reverted_at REAL,
  revert_reason TEXT NOT NULL DEFAULT '');
CREATE INDEX IF NOT EXISTS agent_review_changes_key ON agent_review_changes(agent_key, id);
CREATE INDEX IF NOT EXISTS agent_review_changes_sig ON agent_review_changes(agent_key, signature, status);
CREATE TABLE IF NOT EXISTS agent_review_consumed(
  agent_key TEXT NOT NULL, source_ref TEXT NOT NULL, review_ref TEXT NOT NULL, at REAL NOT NULL,
  PRIMARY KEY(agent_key, source_ref));
CREATE TABLE IF NOT EXISTS agent_review_proposals(
  id INTEGER PRIMARY KEY AUTOINCREMENT, agent_key TEXT NOT NULL, review_ref TEXT NOT NULL, area TEXT NOT NULL,
  text TEXT NOT NULL, evidence_json TEXT NOT NULL DEFAULT '[]', status TEXT NOT NULL DEFAULT 'open', created_at REAL NOT NULL);
"""
_READY: set = set()

REVIEW_RULES = (
    "\n\n# LƯỢT XEM XÉT PHẢN HỒI CỦA CHỦ (reaction)\n"
    "Đây không phải chủ đang hỏi. Chủ đã thả cảm xúc, lý do hay góp ý lên tin của bạn; xem lại tin đó cùng các phản hồi "
    "bên dưới rồi chọn ĐÚNG MỘT cách xử lý:\n"
    "- keep: giữ cách làm, không gửi gì (khen, cảm xúc về sự việc được kể, hay chưa đủ rõ để đổi).\n"
    "- ask_back: gửi MỘT tin mới hỏi lại chủ cho rõ (message).\n"
    "- revise: gửi MỘT tin mới là bản sửa của tin bị phản hồi (message); không sửa đè tin cũ.\n"
    "- lesson: rút MỘT bài học cho đúng ngữ cảnh này (lesson.text một câu, lesson.kind presentation|method); không gửi tin.\n"
    "Emoji là cảm xúc, không phải chấm điểm hay mệnh lệnh: chỉ đổi khi lý do chất lượng, trục nói/im hay góp ý chữ cho thấy "
    "cần đổi. Không phải phản hồi nào cũng cần tin mới. Tin mới còn qua bộ phán xử nói/chờ/im trước khi gửi.\n"
    "consumed: các mã nguồn [rx:...] bạn đã xem xét xong trong lượt này, CHỈ lấy từ danh sách bên dưới, ít nhất một mã.\n"
    "Trả về DUY NHẤT một khối JSON đúng các khoá sau, không thêm khoá nào khác:\n"
    '{"outcome": "keep"|"ask_back"|"revise"|"lesson", "message": "...", "lesson": {"text": "...", '
    '"kind": "presentation"|"method"}, "consumed": ["rx:..."], "reason": "..."}\n'
)

SELF_RULES = (
    "\n\n# TỰ RÀ SOÁT (không phải chủ đang hỏi)\n"
    "Bên dưới là bằng chứng MỚI về cách bạn tham gia: quyết định nói/chờ/im đã được chủ gắn nhãn, và tín hiệu hữu ích. Đề "
    "xuất TỐI ĐA 3 thay đổi, CHỈ từ danh sách đóng sau, mỗi thay đổi dẫn mã bằng chứng đã cho xem (evidence):\n"
    "- offset_set: đổi độ lệch ngưỡng phán xử của MỘT ngữ cảnh (context_ref, value trong -0.25..0.25; âm là dễ lên tiếng "
    "hơn, dương là kín tiếng hơn).\n"
    "- eagerness_set: đổi độ hăng hái chung (value: low|medium|high).\n"
    "- lesson_add: thêm một bài học cho MỘT ngữ cảnh (context_ref team:<id> hay dm:<mã>, text, lesson_kind "
    "speak|method|presentation|collab).\n"
    "- lesson_remove: bỏ một bài học sai hay lỗi thời (lesson_id).\n"
    "- lesson_promote: đưa một bài học lên dùng mọi nơi (lesson_id), CHỈ khi bằng chứng đến từ ít nhất 2 ngữ cảnh khác nhau.\n"
    "Không đổi quyền, luật của chủ, mã, skill, workflow hay cấu trúc trợ lý: ý như vậy ghi vào proposals cho chủ quyết. "
    "Không đủ bằng chứng thì changes rỗng (đó là kết quả tốt). Nhiều trợ lý cùng ý không phải bằng chứng độc lập.\n"
    "Trả về DUY NHẤT một khối JSON:\n"
    '{"changes": [{"kind": "...", "context_ref": "...", "value": ..., "text": "...", "lesson_kind": "...", '
    '"lesson_id": 0, "evidence": ["decision:1", "rx:dm:2"], "why": "..."}], '
    '"proposals": [{"area": "permissions|owner_rule|code|skill|workflow|structure|other", "text": "...", '
    '"evidence": ["..."]}], "reason": "..."}\n'
)


def _next_day(now: float) -> float:
    """Mốc 0 giờ của ngày kế tiếp (giờ máy), như phép đếm hạn mức."""
    import agent_budget
    return agent_budget.day_start(agent_budget.day_start(float(now)) + 86400.0 + 3600.0)


def _chu(vi: str, en: str) -> str:
    try:
        import localefmt
        return localefmt.chu(vi, en)
    except Exception:  # noqa: BLE001
        return vi


def _j(v: Any) -> str:
    return json.dumps(v, ensure_ascii=False, sort_keys=True)


def _jl(s: Any, default: Any) -> Any:
    try:
        v = json.loads(s) if s else default
        return v if v is not None else default
    except (TypeError, ValueError):
        return default


async def _maybe(v: Any) -> Any:
    return await v if inspect.isawaitable(v) else v


def ensure(store, force: bool = False) -> None:
    key = str(getattr(store, "path", id(store)))
    if key in _READY and not force:
        return
    with closing(store._conn()) as c:
        c.executescript(_SCHEMA)
    _READY.add(key)


# ═══════════════════════════ kiểm đầu ra ═══════════════════════════

def _json_block(text: Any) -> Optional[dict]:
    s = str(text or "")
    m = re.search(r"\{.*\}", s, re.S)
    if not m:
        return None
    try:
        d = json.loads(m.group(0))
    except (TypeError, ValueError):
        return None
    return d if isinstance(d, dict) else None


def parse_review(text: Any, sources: Iterable[str]) -> tuple:
    """Kiểm ĐÚNG khuôn đầu ra của lượt xem xét reaction (4.4). Trả (kết quả đã chuẩn hoá, None) hay (None, mã lỗi).

    Khuôn: `outcome` thuộc keep|ask_back|revise|lesson; `message` là chuỗi (bắt buộc khác rỗng với ask_back/revise);
    `lesson` là {text, kind presentation|method} (bắt buộc với outcome lesson); `consumed` là danh sách mã nguồn khác rỗng
    và nằm TRONG nguồn của lý do; `reason` là chuỗi. Không nhận khoá lạ."""
    d = _json_block(text)
    if d is None:
        return None, "no_json"
    if set(d) - REVIEW_KEYS:
        return None, "unknown_keys"
    outcome = d.get("outcome")
    if outcome not in OUTCOMES:
        return None, "bad_outcome"
    msg = d.get("message", "")
    if msg is None:
        msg = ""
    if not isinstance(msg, str):
        return None, "bad_message"
    reason = d.get("reason", "")
    if reason is None:
        reason = ""
    if not isinstance(reason, str):
        return None, "bad_reason"
    consumed = d.get("consumed")
    if not isinstance(consumed, list) or not consumed or not all(isinstance(x, str) for x in consumed):
        return None, "bad_consumed"
    allowed = {str(x) for x in sources or []}
    if not set(consumed) <= allowed:
        return None, "consumed_not_subset"
    lesson = d.get("lesson")
    out_lesson = None
    if outcome == "lesson":
        if not isinstance(lesson, dict) or set(lesson) - {"text", "kind"}:
            return None, "bad_lesson"
        ltext, lkind = lesson.get("text"), lesson.get("kind")
        if not isinstance(ltext, str) or not AL.clean_text(ltext) or lkind not in LESSON_KINDS:
            return None, "bad_lesson"
        out_lesson = {"text": AL.clean_text(ltext), "kind": lkind}
    elif lesson not in (None, {}, "") and not isinstance(lesson, dict):
        return None, "bad_lesson"
    if outcome in ("ask_back", "revise") and not msg.strip():
        return None, "empty_message"
    return {"outcome": outcome, "message": msg.strip()[:MESSAGE_MAX] if outcome in ("ask_back", "revise") else "",
            "lesson": out_lesson, "consumed": list(dict.fromkeys(consumed)), "reason": reason.strip()[:300]}, None


def parse_self_review(text: Any) -> tuple:
    """Đầu ra tự rà soát: {changes: list, proposals: list, reason}. Sai khuôn: (None, mã lỗi)."""
    d = _json_block(text)
    if d is None:
        return None, "no_json"
    ch = d.get("changes", [])
    pr = d.get("proposals", [])
    if not isinstance(ch, list) or not isinstance(pr, list):
        return None, "bad_lists"
    if not all(isinstance(x, dict) for x in ch) or not all(isinstance(x, dict) for x in pr):
        return None, "bad_items"
    return {"changes": ch, "proposals": pr, "reason": str(d.get("reason") or "")[:300]}, None


# ═══════════════════════════ bộ chuyển tới phần J (phán xử) ═══════════════════════════

class JudgeAdapter:
    """Lời gọi tới `agent_judge` (phần J), nạp lười. Thiếu module hay chưa nối: phán xử trả `silent`
    (`judge_unavailable`, KHÔNG gửi), các hàm khác trả rỗng hay ném lỗi rõ ràng. Test tiêm đối tượng giả cùng giao diện."""

    def _mod(self):
        try:
            import agent_judge  # noqa: WPS433
        except ImportError:
            return None
        return agent_judge

    def _jd(self):
        mod = self._mod()
        if mod is None:
            return None
        try:
            return mod.default()
        except Exception:  # noqa: BLE001
            return None

    async def proactive(self, *, agent_key: str, context_ref: str, draft: str, source_event: str, origin: str,
                        payload: Optional[dict] = None) -> dict:
        mod = self._mod()
        fn = getattr(mod, "judge_proactive", None) if mod is not None else None
        if fn is None:
            return {"verdict": "silent", "reason": "judge_unavailable", "decision_id": None}
        try:
            d = await _maybe(fn(agent_key=agent_key, context_ref=context_ref, draft=draft, source_event=source_event,
                                origin=origin, payload=payload))
        except Exception as ex:  # noqa: BLE001
            return {"verdict": "silent", "reason": f"judge_error: {type(ex).__name__}", "decision_id": None}
        if not isinstance(d, dict) or d.get("verdict") not in ("speak", "wait", "silent"):
            return {"verdict": "silent", "reason": "judge_invalid", "decision_id": None}
        return d

    def profile(self, agent_key: str) -> dict:
        mod = self._mod()
        try:
            prof = dict(mod.get_profile(agent_key)) if mod is not None else {}
        except Exception:  # noqa: BLE001
            prof = {}
        prof.setdefault("offsets", {})
        return prof

    def set_offset(self, agent_key: str, context_ref: str, value: float, source: str) -> dict:
        mod = self._mod()
        if mod is None:
            raise RuntimeError("judge_unavailable")
        return mod.set_offset(agent_key, context_ref, float(value), source)

    def set_eagerness(self, agent_key: str, value: str, source: str) -> dict:
        mod = self._mod()
        if mod is None:
            raise RuntimeError("judge_unavailable")
        return mod.set_eagerness(agent_key, value, source)

    def labeled(self, agent_key: str, since: float) -> list:
        """Quyết định của agent có nhãn nói/im gắn SAU `since` (bỏ lời gọi trực tiếp: nhãn trên đó không dạy phán xử)."""
        jd = self._jd()
        st = jd.store(False) if jd is not None else None
        if st is None:
            return []
        out = []
        for d in st.decisions(agent_key, None, 500):
            if not d.get("label") or (d.get("address") or "") == "certain":
                continue
            at = d.get("label_at") if d.get("label_at") is not None else d.get("created_at")
            if at is None or float(at) <= float(since):
                continue
            out.append({"id": int(d["id"]), "context_ref": d["context_ref"], "verdict": d["verdict"],
                        "label": d["label"], "label_at": float(at), "excerpt": str(d.get("excerpt") or "")[:300],
                        "reason": str(d.get("reason") or "")[:200], "label_source": str(d.get("label_source") or "")})
        return out

    def owner_held(self, agent_key: str, kind: str, context_ref: str) -> bool:
        """Chủ đang giữ thiết lập này: độ hăng hái do chủ đặt, hay lần đặt độ lệch gần nhất của ngữ cảnh là của chủ."""
        if kind == "eagerness_set":
            return str(self.profile(agent_key).get("eagerness_source") or "") == "owner"
        jd = self._jd()
        st = jd.store(False) if jd is not None else None
        if st is None:
            return False
        for ch in st.changes(agent_key, 200):
            if ch.get("kind") == "offset_set" and ch.get("context_ref") == context_ref:
                return str(ch.get("source") or "") == "owner"
        return False


def judge_errors(rows: Iterable[dict]) -> tuple:
    """(số nhãn, số lỗi): lỗi là nhãn ngược kết luận (nói mà nhãn "nên im", im/chờ mà nhãn "nên nói")."""
    n = e = 0
    for d in rows or []:
        lab = d.get("label")
        if lab not in ("should_speak", "should_silent"):
            continue
        n += 1
        if (d.get("verdict") == "speak" and lab == "should_silent") or \
                (d.get("verdict") in ("silent", "wait") and lab == "should_speak"):
            e += 1
    return n, e


# ═══════════════════════════ phụ thuộc ═══════════════════════════

@dataclass
class ReviewDeps:
    store: Callable[[], Any]                                    # () -> GoalStore (resonance.sqlite3) | None
    reactions: Any                                              # FeedbackProjector: review_source / set_review_status
    engine_for: Optional[Callable[[str, str, str], tuple]] = None   # (key, ctx, purpose) -> (engine, model, run)
    persona: Callable[[str], str] = lambda key: ""
    try_busy: Callable[[str, str], bool] = lambda key, tok: True
    release_busy: Callable[[str, str], Any] = lambda key, tok: None
    send: Optional[Callable[[str, str, str, dict], Any]] = None     # -> {"session_id", "message_id"} | None
    judge: Any = field(default_factory=JudgeAdapter)
    budget: Optional[Callable[..., tuple]] = None               # (key, purpose, at, reason_ref=) -> (ok, why)
    publish: Callable[[dict], Any] = lambda ev: None
    judge_payload: Callable[[str], dict] = lambda ctx: {}
    contexts: Callable[[str], list] = lambda key: []
    legacy: Callable[[str], list] = lambda key: []
    clock: Callable[[], float] = time.time
    spawn: Callable[[Any], Any] = field(default=asyncio.ensure_future)


def _default_budget(store):
    def fn(key, purpose, at=None, reason_ref=None, units=1):
        import agent_budget
        return agent_budget.try_spend(key, purpose, at, store=store, reason_ref=reason_ref, units=units)
    return fn


class ReviewHost:
    def __init__(self, deps: ReviewDeps):
        self.deps = deps
        self.host_id = "learn-" + secrets.token_hex(4)
        self._self_checked: dict = {}
        self._self_running: set = set()
        self._running: set = set()
        self._tasks: set = set()
        # Lùi lại theo lý do (review T3 L P3): hết hạn mức hay engine chưa dựng được thì không phục vụ lại lý do đó mỗi
        # 30 giây (mỗi lần một dòng sự kiện, một gói WS, một dòng sổ giữ rồi hoàn). {reason_id: thời điểm được thử lại}.
        self._backoff: dict = {}
        self._quota_noted: dict = {}   # {reason_id: lần cuối ghi "Chờ hạn mức"} để không ghi lặp mỗi nhịp

    # ───────────── tiện ích ─────────────

    def _store(self):
        st = self.deps.store()
        if st is not None:
            ensure(st)
        return st

    def _budget(self, store, key, purpose, now, reason_ref=None, units=1) -> tuple:
        fn = self.deps.budget or _default_budget(store)
        try:
            if units != 1:
                got = fn(key, purpose, now, reason_ref=reason_ref, units=units)
            else:
                got = fn(key, purpose, now, reason_ref=reason_ref)
        except TypeError:
            got = fn(key, purpose, now)
        except Exception as ex:  # noqa: BLE001 - hạn mức hỏng không được thành "chạy vô hạn"
            return False, f"budget_error: {type(ex).__name__}"
        if isinstance(got, (tuple, list)):
            return bool(got[0]), str(got[1] if len(got) > 1 else "")
        return bool(got), ""

    def _publish(self, events: Iterable[dict]) -> None:
        for ev in events or []:
            try:
                got = self.deps.publish(ev)
                if asyncio.iscoroutine(got):
                    self._spawn(got)
            except Exception as ex:  # noqa: BLE001
                print(f"[learn publish] {type(ex).__name__}: {ex}", file=sys.stderr)

    def _spawn(self, coro) -> None:
        try:
            t = self.deps.spawn(coro)
        except Exception:  # noqa: BLE001
            coro.close()
            return
        if isinstance(t, asyncio.Future):
            self._tasks.add(t)
            t.add_done_callback(self._tasks.discard)

    async def wait_idle(self, timeout: float = 30.0) -> None:
        end = time.time() + timeout
        while self._tasks and time.time() < end:
            await asyncio.wait(list(self._tasks), timeout=max(0.01, end - time.time()))

    def _status(self, refs: Iterable[str], status: str, reason: str = "") -> list:
        """Ghi trạng thái lên reaction của các nguồn (luồng phụ). Trả gói WS; người gọi đẩy trên event loop."""
        events = []
        for ref in refs or []:
            try:
                events.extend(self.deps.reactions.set_review_status(ref, status, reason) or [])
            except Exception as ex:  # noqa: BLE001
                print(f"[learn status] {ref}: {type(ex).__name__}: {ex}", file=sys.stderr)
        return events

    async def _astatus(self, refs: Iterable[str], status: str, reason: str = "") -> None:
        self._publish(await asyncio.to_thread(self._status, list(refs or []), status, reason))

    def _event(self, store, key, ctx, kind, reason="", payload=None, at=None) -> None:
        try:
            import agent_pulse as AP
            AP.record_event(store, key, ctx, kind, source="learn", reason=reason, payload=payload or {}, at=at)
        except Exception as ex:  # noqa: BLE001
            print(f"[learn event] {kind}: {type(ex).__name__}: {ex}", file=sys.stderr)

    async def _run_engine(self, key, ctx, purpose, system, prompt, ledger, cid, turn_ref) -> tuple:
        """Gọi engine của chính agent. Trả (out, started, error). Mốc gọi engine ghi vào sổ lượt."""
        state = {"started": False}
        if self.deps.engine_for is None:
            return None, False, "engine_unavailable"
        try:
            engine, model, run = self.deps.engine_for(key, ctx, purpose)
        except Exception as ex:  # noqa: BLE001
            return None, False, f"engine_unavailable: {type(ex).__name__}"

        async def engine_started(*_a, **_k):
            if not state["started"]:
                state["started"] = True
                await asyncio.to_thread(ledger.mark_engine, cid, str(engine or ""), str(model or ""))

        req = {"system": system, "prompt": prompt, "engine_started": engine_started, "team_id": ctx,
               "turn_id": turn_ref, "agent_key": key, "context_ref": ctx, "purpose": purpose, "tools": []}
        if not getattr(run, "marks_engine", False):
            await engine_started()
        try:
            out = await asyncio.wait_for(run(req), timeout=REVIEW_TIMEOUT_S)
        except asyncio.CancelledError:
            raise
        except BaseException as ex:  # noqa: BLE001
            return None, state["started"], f"engine_error: {type(ex).__name__}"
        if not state["started"]:
            await engine_started()
        return (out if isinstance(out, dict) else {"text": str(out or "")}), True, None

    # ═════════════ lượt xem xét reaction (4.4) ═════════════

    def _sources(self, refs: Iterable[str]) -> list:
        out = []
        for ref in refs or []:
            try:
                s = self.deps.reactions.review_source(ref)
            except Exception:  # noqa: BLE001
                s = None
            if s is not None:
                out.append(s)
        return out

    def review_prompt(self, store, key: str, ctx: str, sources: list) -> str:
        import reaction_values as RV
        lines = [f"Ngữ cảnh: {'nhóm ' + ctx[5:] if ctx.startswith('team:') else 'chat riêng với chủ'}",
                 "Phản hồi cần xem xét (mỗi mục một mã nguồn):"]
        for s in sources:
            excerpt = re.sub(r"\s+", " ", str(s.get("message_text") or "")).strip()
            if len(excerpt) > EXCERPT_MAX:
                excerpt = excerpt[:EXCERPT_MAX] + "..."
            parts = [f"- [{s['source_ref']}] về tin #{s['message_id']}: \"{excerpt}\""]
            if s.get("value"):
                parts.append(f"cảm xúc: {RV.REACTION_EMOJI.get(s['value'], '')} ({s['value']})")
            if s.get("reasons"):
                parts.append("lý do: " + ", ".join(RV.REASON_LABEL.get(x, x) for x in s["reasons"]))
            if s.get("axis"):
                parts.append("nói/im: " + RV.AXIS_LABEL.get(s["axis"], s["axis"]))
            if s.get("comment"):
                parts.append('góp ý: "' + re.sub(r"\s+", " ", s["comment"]).strip() + '"')
            if not s.get("current"):
                parts.append("(chủ đã đổi phản hồi này sau đó)")
            lines.append(" · ".join(parts))
        block = AL.prompt_block(store, key, ctx)
        if block:
            lines.append("\n" + block)
        return "\n".join(lines)

    async def serve_reaction_review(self, reason: dict) -> dict:
        """Phục vụ MỘT lý do `reaction_review` (4.4). Trả {"outcome", ...} để test và nhật ký đọc."""
        from agent_ledger import CallLedger, WakeReasons
        # Vòng pulse gọi hàm này trên event loop: mọi đọc/ghi kho ở luồng phụ (GOAL mục 10).
        store = await asyncio.to_thread(self._store)
        if store is None:
            return {"outcome": "no_store"}
        rid = int(reason["id"])
        if self._backoff.get(rid, 0.0) > float(self.deps.clock()):
            return {"outcome": "backoff"}
        W = WakeReasons(store)
        cur = await asyncio.to_thread(W.get, rid)
        if cur is None or cur["status"] != "pending" or cur["code"] != "reaction_review":
            return {"outcome": "gone"}
        key, ctx = cur["agent_key"], cur["context_ref"]
        now = float(self.deps.clock())
        tok = f"{self.host_id}:{secrets.token_hex(4)}"
        if not await asyncio.to_thread(self.deps.try_busy, key, tok):
            return {"outcome": "busy"}
        released = {"done": False}

        def release():
            if not released["done"]:
                released["done"] = True
                try:
                    self.deps.release_busy(key, tok)
                except Exception:  # noqa: BLE001
                    pass
        try:
            # Chat riêng cần 2 lượt còn trống (lượt xem xét và lượt phán xử tin mới, cả hai ở mức ưu tiên reaction_review):
            # không để ask_back/revise mất vì lượt phán xử hết chỗ sau khi phản hồi đã tiêu thụ (review T3 L P2-1).
            units = 2 if str(ctx).startswith("dm:") else 1
            ok, why = await asyncio.to_thread(self._budget, store, key, "reaction_review", now, f"wr:{rid}", units)
            if not ok:
                # Hết hạn mức: vẫn kiểm mỗi nhịp (chủ nới trần thì chạy ngay), nhưng chỉ ghi trạng thái, sự kiện và gói WS
                # một lần mỗi 10 phút cho mỗi lý do (review T3 L P3: trước đây khoảng 2.880 dòng mỗi lý do mỗi ngày).
                if now - self._quota_noted.get(rid, -1e18) < QUOTA_BACKOFF_S:
                    return {"outcome": "quota", "reason": why, "deduped": True}
                self._quota_noted[rid] = now
                live = [s["source_ref"] for s in await asyncio.to_thread(W.sources, rid, True)]
                await self._astatus(live, "waiting_quota",
                                        _chu("Hết hạn mức lượt hôm nay của trợ lý", "The assistant's daily turns are used up"))
                await asyncio.to_thread(self._event, store, key, ctx, "quota", why or "agent_daily_calls",
                                        {"reason_id": rid, "purpose": "reaction_review"}, now)
                return {"outcome": "quota", "reason": why}
            if str(ctx).startswith("team:") and not await asyncio.to_thread(self._team_judge_room, store, ctx, now):
                # Trần phán xử trong ngày của NHÓM đã hết (đối ứng của units=2 ở chat riêng, review T3 vòng 2 P2-2): không
                # nhận lý do, không gọi model; phản hồi giữ nguyên, mở lại vào ngày mới.
                self._backoff[rid] = _next_day(now)
                if now - self._quota_noted.get(rid, -1e18) >= QUOTA_BACKOFF_S:
                    self._quota_noted[rid] = now
                    live = [s["source_ref"] for s in await asyncio.to_thread(W.sources, rid, True)]
                    await self._astatus(live, "waiting_quota", _chu("Đã chạm trần phán xử hôm nay của nhóm",
                                                                    "The team's judge limit for today is reached"))
                    await asyncio.to_thread(self._event, store, key, ctx, "quota", "judge_cap",
                                            {"reason_id": rid, "purpose": "reaction_review"}, now)
                return {"outcome": "quota", "reason": "judge_cap"}
            cl = await asyncio.to_thread(lambda: W.claim(rid, purpose="reaction_review", obligation=False, now=now))
            if cl["outcome"] != "claimed":
                if cl["outcome"] == "quota":
                    live = [s["source_ref"] for s in await asyncio.to_thread(W.sources, rid, True)]
                    await self._astatus(live, "waiting_quota",
                                            _chu("Đã chạm trần lượt chung của máy chủ",
                                                 "The server-wide turn ceiling is reached"))
                return {"outcome": cl["outcome"]}
            self._running.add(rid)
            try:
                return await self._review_claimed(store, W, CallLedger(store), cur, cl, now)
            finally:
                self._running.discard(rid)
        finally:
            # Nhả khoá bận ghi kho nhóm: luồng phụ (bị huỷ thêm vẫn chờ nhả xong).
            from io_offload import run_io_quiet
            await run_io_quiet(release)

    def _team_judge_room(self, store, ctx: str, now: float) -> bool:
        """Còn chỗ trong trần `judge_daily` của nhóm hôm nay cho lượt phán xử tin mới (đếm như `Judge._reserve`: dòng
        `judge_batch` của nhóm, `agent_key` rỗng, không hoàn). None là Không giới hạn; đọc lỗi thì coi như còn chỗ (bộ phán xử
        vẫn tự chặn ở trần)."""
        try:
            payload = dict(self.deps.judge_payload(ctx) or {})
        except Exception:  # noqa: BLE001
            return True
        cap = payload.get("judge_daily", 40) if "judge_daily" in payload else 40
        if cap is None:
            return True
        import agent_budget
        with closing(store._conn()) as c:
            used = int(c.execute("SELECT COUNT(*) FROM agent_calls WHERE purpose='judge_batch' AND context_ref=? "
                                 "AND agent_key='' AND status<>'refunded' AND created_at>=?",
                                 (ctx, agent_budget.day_start(now))).fetchone()[0])
        return used < int(cap)

    async def _review_claimed(self, store, W, ledger, reason, cl, now) -> dict:
        rid, key, ctx = int(reason["id"]), reason["agent_key"], reason["context_ref"]
        refs, cid = list(cl["sources"]), int(cl["call_id"])
        await self._astatus(refs, "reviewing", "")
        sources = await asyncio.to_thread(self._sources, refs)
        try:
            prompt = await asyncio.to_thread(self.review_prompt, store, key, ctx, sources)
            system = (self.deps.persona(key) or "") + REVIEW_RULES
        except Exception as ex:  # noqa: BLE001
            await asyncio.to_thread(W.settle, rid, "refunded", now=now)
            await self._astatus(refs, "pending_review", "")
            return {"outcome": "error", "error": f"prompt: {type(ex).__name__}"}
        out, started, err = await self._run_engine(key, ctx, "reaction_review", system, prompt, ledger, cid, f"wr:{rid}")
        if err:
            if not started:
                self._backoff[rid] = now + ENGINE_BACKOFF_S   # engine chưa dựng được: lượt hoàn, thử lại sau
            st = await asyncio.to_thread(W.settle, rid, "error" if started else "refunded", now=now)
            await self._astatus(refs, "pending_review",
                                    _chu("Lượt xem xét lỗi, sẽ thử lại", "The review failed and will be retried")
                                    if started else "")
            self._event(store, key, ctx, "reaction_review_error", reason=err, payload={"reason_id": rid, "call_id": cid,
                                                                                      "reason_status": st}, at=now)
            return {"outcome": "engine_error", "error": err, "reason_status": st}
        res, perr = parse_review(out.get("text"), refs)
        if res is None:
            st = await asyncio.to_thread(lambda: W.settle(rid, "error", tokens_in=out.get("tokens_in"),
                                                          tokens_out=out.get("tokens_out"), now=now))
            await self._astatus(refs, "pending_review",
                                    _chu("Lượt xem xét trả sai khuôn, sẽ thử lại",
                                         "The review returned an invalid format and will be retried"))
            self._event(store, key, ctx, "reaction_review_error", reason=perr,
                        payload={"reason_id": rid, "call_id": cid, "reason_status": st}, at=now)
            return {"outcome": "invalid", "error": perr, "reason_status": st}
        settled = await asyncio.to_thread(lambda: W.settle(rid, "ok", res["consumed"], tokens_in=out.get("tokens_in"),
                                                           tokens_out=out.get("tokens_out"), now=now))
        consumed = res["consumed"]
        rest = [r for r in refs if r not in consumed]
        if rest:
            await self._astatus(rest, "pending_review", "")
        try:
            eff = await self._apply_review(store, key, ctx, rid, cid, res, sources, now)
        except Exception as ex:  # noqa: BLE001
            eff = {"status": "no_change", "status_reason": _chu("Không áp dụng được kết quả xem xét",
                                                                "The review result could not be applied"),
                   "error": f"{type(ex).__name__}: {ex}"}
        requeued = None
        if eff.get("requeue"):
            # Tin mới chưa phán xử được vì hết hạn mức: nguồn về lý do chờ (không tiêu thụ), lượt sau xem lại.
            requeued = await asyncio.to_thread(lambda: W.requeue(rid, consumed, now=now))
            # Trần phán xử của nhóm hay trần chung: chỉ mở lại vào ngày mới (giờ máy), không chạy lại lượt xem xét (một lời
            # gọi model) mỗi 10 phút để rồi lại chạm trần (review T3 vòng 2 P2-2). Hết hạn mức ngày của agent: 10 phút.
            until = _next_day(now) if eff.get("silence") in ("judge_cap", "server_ceiling") else now + QUOTA_BACKOFF_S
            self._backoff[rid] = until
            if requeued:
                self._backoff[int(requeued)] = until
        await self._astatus(consumed, eff["status"], eff.get("status_reason", ""))
        payload = {"reason_id": rid, "call_id": cid, "outcome": res["outcome"], "consumed": consumed,
                   "moved_to": settled.get("moved_to"), "status": eff["status"], "reason": res["reason"]}
        if requeued:
            payload["requeued_to"] = int(requeued)
        for k in ("lesson_id", "decision_id", "verdict", "message_id", "error"):
            if eff.get(k) is not None:
                payload[k] = eff[k]
        self._event(store, key, ctx, "reaction_review", reason=res["outcome"], payload=payload, at=now)
        return dict(payload, outcome="served", review=res["outcome"])

    async def _apply_review(self, store, key, ctx, rid, cid, res, sources, now) -> dict:
        outcome = res["outcome"]
        if outcome == "keep":
            return {"status": "no_change", "status_reason": res["reason"][:160]}
        if outcome == "lesson":
            lid = await asyncio.to_thread(lambda: AL.add(
                store, agent_key=key, scope=ctx, kind=res["lesson"]["kind"], text=res["lesson"]["text"], source="review",
                source_refs=list(res["consumed"]) + [f"wr:{rid}", f"call:{cid}"], at=now))
            return {"status": "adjusted", "lesson_id": lid,
                    "status_reason": _chu("Đã rút bài học: ", "Lesson recorded: ") + res["lesson"]["text"][:140]}
        by_ref = {s["source_ref"]: s for s in sources}
        first = next((by_ref[r] for r in res["consumed"] if r in by_ref), None)
        reply_to = first["message_id"] if first else None
        # Chat riêng: tin mới vào ĐÚNG phiên có tin bị phản hồi (review T3 L P2-2), không phải phiên báo cáo.
        src_sid = str(first.get("session_id") or "") if (first and ctx.startswith("dm:")) else ""
        payload = dict(await asyncio.to_thread(self.deps.judge_payload, ctx) or {})
        payload.update({"origin": "reaction_review", "draft": res["message"],
                        "review": {"reason_id": rid, "consumed": list(res["consumed"]), "context_ref": ctx,
                                   "agent_key": key, "outcome": outcome, "reply_to": reply_to,
                                   "session_id": src_sid}})
        dec = await self.deps.judge.proactive(agent_key=key, context_ref=ctx, draft=res["message"],
                                              source_event=f"wr:{rid}", origin="reaction_review", payload=payload)
        verdict = dec.get("verdict")
        did = dec.get("decision_id")
        if verdict != "speak" and str(dec.get("silence_code") or "") in QUOTA_SILENCE:
            # Bộ phán xử dừng vì hết hạn mức hay chạm trần (chưa phán xử gì): KHÔNG phải "phán xử chọn im". Phản hồi không
            # được mất (GOAL 8.3, review T3 L P2-1): người gọi trả nguồn về lý do chờ, trạng thái "Chờ hạn mức".
            return {"status": "waiting_quota", "requeue": True, "verdict": verdict, "decision_id": did,
                    "silence": str(dec.get("silence_code") or ""),
                    "status_reason": _chu("Hết hạn mức lượt hôm nay của trợ lý, sẽ xem lại sau",
                                          "The assistant's daily turns are used up; it will review again later")}
        if verdict != "speak":
            why = (_chu("Phán xử chọn chờ", "The judge chose to wait") if verdict == "wait"
                   else _chu("Phán xử chọn im", "The judge chose silence"))
            return {"status": "no_change", "status_reason": why, "verdict": verdict, "decision_id": did}
        sent = await asyncio.to_thread(self._send, key, ctx, res["message"], outcome, reply_to, rid, did, src_sid)
        if sent and sent.get("message_id") is not None:
            return {"status": "adjusted", "verdict": "speak", "decision_id": did, "message_id": sent["message_id"],
                    "status_reason": (_chu("Đã gửi câu hỏi lại", "Sent a follow-up question") if outcome == "ask_back"
                                      else _chu("Đã gửi bản sửa", "Sent a revised answer"))}
        return {"status": "no_change", "verdict": "speak", "decision_id": did,
                "status_reason": _chu("Chưa gửi được tin mới", "The new message could not be sent")}

    def _send(self, key, ctx, text, outcome, reply_to, rid, did, session_id="") -> Optional[dict]:
        if self.deps.send is None:
            return None
        try:
            return self.deps.send(key, ctx, text, {"source_ref": f"wr:{rid}", "decision_id": did, "reply_to": reply_to,
                                                    "review": outcome, "session_id": session_id or ""})
        except Exception as ex:  # noqa: BLE001
            print(f"[learn send] {type(ex).__name__}: {ex}", file=sys.stderr)
            return None

    async def on_judge_send(self, decision: dict, payload: dict, mode: str) -> None:
        """Bộ gửi đăng ký với phần J (`agent_judge.register_sender`): một tin `ask_back`/`revise` từng bị phán xử cho CHỜ,
        nay được gỡ chờ và xét lại thành `speak`. Chỉ xử lý tin do lượt xem xét reaction tạo (`origin`)."""
        if str((payload or {}).get("origin") or "") != "reaction_review" or mode != "send":
            return
        rv = payload.get("review") or {}
        key, ctx = str(rv.get("agent_key") or ""), str(rv.get("context_ref") or "")
        if not key or not ctx:
            return
        sent = await asyncio.to_thread(self._send, key, ctx, str(payload.get("draft") or ""), rv.get("outcome"),
                                       rv.get("reply_to"), rv.get("reason_id"), (decision or {}).get("decision_id"),
                                       str(rv.get("session_id") or ""))
        if sent and sent.get("message_id") is not None:
            await self._astatus(list(rv.get("consumed") or []), "adjusted",
                                    _chu("Đã gửi tin mới sau khi chờ", "Sent the new message after waiting"))
            store = await asyncio.to_thread(self._store)
            if store is not None:
                await asyncio.to_thread(self._event, store, key, ctx, "reaction_review_sent",
                                        str(rv.get("outcome") or ""),
                                        {"reason_id": rv.get("reason_id"), "message_id": sent["message_id"],
                                         "decision_id": (decision or {}).get("decision_id")})

    def recover_stale_claims(self, now: Optional[float] = None) -> list:
        """Lý do `reaction_review` còn `claimed` quá một lượt (10 phút + 60 giây) mà tiến trình này không còn chạy lượt đó
        (tiến trình cũ chết giữa lượt): chốt `interrupted` để nguồn về `pending` (hay `failed` khi đã thử đủ), không kẹt mãi.
        Dòng sổ đã qua mốc engine vẫn tính (đối soát T2), chưa qua thì đối soát hoàn. Trả mã lý do đã gỡ; gói WS của trạng
        thái để ở `self.stale_events` cho người gọi đẩy trên event loop."""
        from agent_ledger import WakeReasons
        self.stale_events = []
        store = self._store()
        if store is None:
            return []
        t = float(self.deps.clock()) if now is None else float(now)
        with closing(store._conn()) as c:
            rows = [int(r[0]) for r in c.execute(
                "SELECT id FROM agent_wake_reasons WHERE code='reaction_review' AND status='claimed' AND updated_at<?",
                (t - REVIEW_TIMEOUT_S - 60.0,)).fetchall()]
        out = []
        W = WakeReasons(store)
        for rid in rows:
            if rid in self._running:
                continue
            got = W.settle(rid, "interrupted", now=t)
            if got.get("status") in ("pending", "failed", "superseded"):
                out.append(rid)
                live = [s["source_ref"] for s in W.sources(got.get("moved_to") or rid, live_only=True)]
                self.stale_events.extend(self._status(live, "pending_review", ""))
        return out

    def pending_reviews(self, limit: int = 20) -> list:
        """Lý do `reaction_review` đang chờ (cũ trước). Dùng khi host nhịp không có sổ đăng ký lý do."""
        store = self._store()
        if store is None:
            return []
        with closing(store._conn()) as c:
            return [dict(r) for r in c.execute("SELECT * FROM agent_wake_reasons WHERE code='reaction_review' AND "
                                               "status='pending' ORDER BY id LIMIT ?", (int(limit),)).fetchall()]

    # ═════════════ tự rà soát (8.3) ═════════════

    def _state(self, store, key) -> dict:
        ensure(store)
        with closing(store._conn()) as c:
            r = c.execute("SELECT * FROM agent_review_state WHERE agent_key=?", (key,)).fetchone()
        return dict(r) if r else {"agent_key": key, "last_review_at": None, "last_attempt_at": None}

    def _set_state(self, store, key, now, ok: bool) -> None:
        with store._Tx(store) as c:
            c.execute("INSERT INTO agent_review_state(agent_key,last_review_at,last_attempt_at,updated_at) "
                      "VALUES(?,?,?,?) ON CONFLICT(agent_key) DO UPDATE SET last_attempt_at=excluded.last_attempt_at, "
                      "last_review_at=COALESCE(excluded.last_review_at, agent_review_state.last_review_at), "
                      "updated_at=excluded.updated_at", (key, now if ok else None, now, now))

    def _consumed_refs(self, store, key) -> set:
        with closing(store._conn()) as c:
            mine = {r[0] for r in c.execute("SELECT source_ref FROM agent_review_consumed WHERE agent_key=?", (key,))}
            rr = {r[0] for r in c.execute(
                "SELECT s.source_ref FROM agent_wake_sources s JOIN agent_wake_reasons w ON w.id=s.reason_id "
                "WHERE w.agent_key=? AND w.code='reaction_review' AND s.consumed_at IS NOT NULL", (key,))}
        return mine | rr

    def _reviewing_refs(self, store, key) -> set:
        """Nguồn còn thuộc một lý do `reaction_review` CHƯA xong (đang chờ, đang chạy, kể cả chờ hạn mức): lượt xem xét
        reaction sẽ học từ chúng, nên tự rà soát không được đếm hay tiêu thụ (review T3 L P2-3: một phản hồi học hai lần)."""
        with closing(store._conn()) as c:
            return {r[0] for r in c.execute(
                "SELECT s.source_ref FROM agent_wake_sources s JOIN agent_wake_reasons w ON w.id=s.reason_id "
                "WHERE w.agent_key=? AND w.code='reaction_review' AND w.status IN ('pending','claimed') "
                "AND s.removed_at IS NULL AND s.consumed_at IS NULL", (key,))}

    def evidence(self, store, key: str, now: float) -> dict:
        """Bằng chứng MỚI cho tự rà soát: nhãn nói/im và tín hiệu hữu ích sau `resumed_at` và sau lần rà soát trước, trừ
        nguồn đã được lượt xem xét reaction hay lần rà soát trước tiêu thụ, nguồn còn nằm trong lý do `reaction_review` chưa
        xong, và nhãn sinh từ trục nói/im của reaction (thuộc về lượt xem xét reaction, không học hai lần)."""
        import agent_pulse as AP
        stt = self._state(store, key)
        resumed = store.resumed_at(key) or 0.0
        since = max(float(resumed), float(stt.get("last_review_at") or 0.0))
        used = self._consumed_refs(store, key) | self._reviewing_refs(store, key)
        labels = [d for d in self.deps.judge.labeled(key, since) if f"decision:{d['id']}" not in used
                  and str(d.get("label_source") or "") != "reaction"]
        sigs = [s for s in AP.signals(store, key, status="live")
                if s.get("kind") != "context_init" and float(s.get("at") or 0) > since and s["source_ref"] not in used]
        return {"since": since, "labels": labels[-EVIDENCE_LIMIT:], "signals": sigs[-EVIDENCE_LIMIT:], "state": stt,
                "n_labels": len(labels), "n_signals": len(sigs)}

    def due(self, store, key: str, now: float) -> tuple:
        """(đến hạn?, lý do). Cộng hưởng tắt: không. Chưa đủ 24 giờ từ lần trước hay đang lùi sau lỗi: không."""
        a = store.agent_any(key)
        if not a or a.get("status") != "active" or not a.get("enabled"):
            return False, "off", None
        stt = self._state(store, key)
        if stt.get("last_review_at") is not None and now - float(stt["last_review_at"]) < SELF_GAP_S:
            return False, "not_due", None
        if stt.get("last_attempt_at") is not None and now - float(stt["last_attempt_at"]) < SELF_BACKOFF_S:
            return False, "backoff", None
        ev = self.evidence(store, key, now)
        if ev["n_labels"] < SELF_MIN_LABELS and ev["n_signals"] < SELF_MIN_SIGNALS:
            return False, "not_enough", ev
        return True, "due", ev

    def self_prompt(self, store, key: str, ev: dict, contexts: list) -> tuple:
        """(lời nhắc, bằng chứng đã cho xem {mã: ngữ cảnh}, bài học đã cho xem {mã: dòng})."""
        shown: dict = {}
        lines = ["Ngữ cảnh của bạn: " + ", ".join(contexts or ["(chưa có)"])]
        prof = self.deps.judge.profile(key)
        lines.append(f"Độ hăng hái hiện tại: {prof.get('eagerness') or '?'}")
        offs = prof.get("offsets") or {}
        if offs:
            lines.append("Độ lệch ngưỡng theo ngữ cảnh: " + ", ".join(f"{c}={float(v):+.2f}" for c, v in offs.items()))
        if ev["labels"]:
            lines.append("\nQuyết định nói/chờ/im có nhãn của chủ:")
            for d in ev["labels"]:
                ref = f"decision:{d['id']}"
                shown[ref] = d["context_ref"]
                lines.append(f"- [{ref}] {d['context_ref']} · kết luận {d['verdict']} · nhãn {d['label']} · "
                             f"\"{d.get('excerpt') or ''}\"")
        if ev["signals"]:
            lines.append("\nTín hiệu hữu ích:")
            for s in ev["signals"]:
                shown[s["source_ref"]] = s["context_ref"]
                extra = f" {s['emoji']}" if s.get("emoji") else ""
                reasons = s.get("reasons") or _jl(s.get("reasons_json"), [])
                lines.append(f"- [{s['source_ref']}] {s['context_ref']} · {s['kind']}{extra} · giá trị "
                             f"{float(s['value']):+.2f}" + (f" · lý do {', '.join(reasons)}" if reasons else ""))
        cur = AL.lessons(store, key, status="active", limit=60)
        known = {}
        if cur:
            lines.append("\nBài học đang dùng:")
            for r in cur:
                known[int(r["id"])] = r
                lines.append(AL.lesson_line(r))
        return "\n".join(lines), shown, known

    def _sig(self, kind: str, ctx: str, target: str) -> str:
        return f"{kind}|{ctx}|{target}"

    def _reverted_recently(self, store, key, sig, now) -> bool:
        with closing(store._conn()) as c:
            return c.execute("SELECT 1 FROM agent_review_changes WHERE agent_key=? AND signature=? AND status='reverted' "
                             "AND reverted_at>=?", (key, sig, now - NO_REPEAT_S)).fetchone() is not None

    def _record_change(self, store, review_ref, key, ctx, kind, sig, evidence, why, status, reason="",
                       before=None, after=None, now=None) -> int:
        with store._Tx(store) as c:
            return int(c.execute(
                "INSERT INTO agent_review_changes(review_ref,agent_key,context_ref,kind,signature,before_json,after_json,"
                "evidence_json,why,status,reject_reason,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                (review_ref, key, ctx or "*", kind, sig, _j(before or {}), _j(after or {}), _j(list(evidence or [])),
                 str(why or "")[:300], status, str(reason or "")[:120], float(now))).lastrowid)

    def _update_change(self, store, cid, **cols) -> None:
        sets = ", ".join(f"{k}=?" for k in cols)
        vals = [(_j(v) if k.endswith("_json") else v) for k, v in cols.items()]
        with store._Tx(store) as c:
            c.execute(f"UPDATE agent_review_changes SET {sets} WHERE id=?", (*vals, int(cid)))

    def _base_error(self, key, ctx, now) -> float:
        rows = [d for d in self.deps.judge.labeled(key, now - 30 * 86400.0)
                if (ctx in ("*", "") or d["context_ref"] == ctx) and d["label_at"] <= now]
        n, e = judge_errors(rows)
        return (e / n) if n else 0.0

    def _link_policy(self, store, key, ctx, kind, cid, before, after, now) -> Optional[int]:
        """Cửa sổ quan sát 6.4 ở phần P: dùng dòng J đã ghi qua móc của nó (nguồn `self_review:<mã>`), chưa có thì tự ghi.
        Tỷ lệ lỗi phán xử nền ghi vào dòng đó để luật "+0,15 khi ≥ 6 nhãn" có mốc so."""
        import agent_pulse as AP
        src = f"{SOURCE_TAG}{cid}"
        pc = None
        for ch in AP.policy_changes(store, key, 50):
            if ch.get("source") == src:
                pc = int(ch["id"])
                break
        base = self._base_error(key, ctx, now)
        if pc is None:
            pc = AP.apply_policy_change(store, key, ctx, {"kind": kind, "before": before, "after": after, "source": src,
                                                          "base_error_rate": base}, at=now)
        else:
            with store._Tx(store) as c:
                c.execute("UPDATE pulse_policy_changes SET base_error=? WHERE id=? AND base_error IS NULL", (base, pc))
        return pc

    def apply_change(self, store, key: str, ch: dict, shown: dict, known: dict, contexts: list, review_ref: str,
                     now: float) -> dict:
        """Kiểm và tự áp MỘT thay đổi của danh sách đóng. Trả {status: applied|rejected|proposal, reason, change_id}."""
        kind = str(ch.get("kind") or "")
        why = str(ch.get("why") or "")
        ev = ch.get("evidence")
        if kind not in CLOSED_CHANGES:
            return {"status": "proposal", "reason": "out_of_scope", "kind": kind}
        ctx = str(ch.get("context_ref") or "")
        if not isinstance(ev, list) or not ev or not all(isinstance(x, str) and x in shown for x in ev):
            cid = self._record_change(store, review_ref, key, ctx, kind, self._sig(kind, ctx, "?"), ev if isinstance(
                ev, list) else [], why, "rejected", "evidence", now=now)
            return {"status": "rejected", "reason": "evidence", "change_id": cid}
        try:
            if kind == "offset_set":
                if ctx not in contexts or ctx == "*":
                    raise _Reject("context")
                after = max(-OFFSET_LIMIT, min(OFFSET_LIMIT, float(ch.get("value"))))
                before = float((self.deps.judge.profile(key).get("offsets") or {}).get(ctx, 0.0))
                if abs(after - before) < 0.005:
                    raise _Reject("no_change")
                if self.deps.judge.owner_held(key, kind, ctx):
                    raise _Reject("owner_held")
                sig = self._sig(kind, ctx, "up" if after > before else "down")
                b, a = {"offset": round(before, 4)}, {"offset": round(after, 4)}
            elif kind == "eagerness_set":
                ctx = "*"
                after = str(ch.get("value") or "")
                if after not in EAGERNESS:
                    raise _Reject("value")
                before = str(self.deps.judge.profile(key).get("eagerness") or "")
                if before == after:
                    raise _Reject("no_change")
                if self.deps.judge.owner_held(key, kind, ctx):
                    raise _Reject("owner_held")
                sig = self._sig(kind, ctx, after)
                b, a = {"eagerness": before}, {"eagerness": after}
            elif kind == "lesson_add":
                if not (ctx.startswith("team:") and ctx in contexts) and ctx != f"dm:{key}":
                    raise _Reject("context")
                if not any(str(shown.get(x) or "") == ctx for x in ev):
                    # Bài học của ngữ cảnh X phải có ít nhất một bằng chứng của CHÍNH X (review T3 L P2-5): không để chữ
                    # model rút từ nhóm A hay chat riêng lọt vào prompt của nhóm B.
                    raise _Reject("evidence_context")
                text = AL.clean_text(ch.get("text"))
                lk = str(ch.get("lesson_kind") or "method")
                if not text or lk not in AL.KINDS:
                    raise _Reject("value")
                sig = self._sig(kind, ctx, AL.normalize(text))
                b, a = {}, {"text": text, "kind": lk, "scope": ctx}
            else:
                try:
                    lid = int(ch.get("lesson_id"))
                except (TypeError, ValueError):
                    raise _Reject("lesson")
                row = known.get(lid)
                if row is None or row["status"] != "active" or row["scope"] == "*" or row["source"] == "owner":
                    raise _Reject("lesson")
                ctx = row["scope"]
                sig = self._sig(kind, "*", str(lid))
                b, a = {"lesson_id": lid, "scope": row["scope"], "text": row["text"]}, {}
                if kind == "lesson_promote":
                    evctx = {shown[x] for x in ev if str(shown.get(x) or "") not in ("", "*")}
                    if len(evctx) < AL.PROMOTE_MIN_CONTEXTS:
                        raise _Reject("contexts")
                    a = {"scope": "*", "contexts": sorted(evctx)}
            if self._reverted_recently(store, key, sig, now):
                raise _Reject("reverted_recently")
        except _Reject as rj:
            cid = self._record_change(store, review_ref, key, ctx, kind, self._sig(kind, ctx, "?"), ev, why,
                                      "rejected", rj.code, now=now)
            return {"status": "rejected", "reason": rj.code, "change_id": cid}
        except (TypeError, ValueError):
            cid = self._record_change(store, review_ref, key, ctx, kind, self._sig(kind, ctx, "?"), ev, why,
                                      "rejected", "value", now=now)
            return {"status": "rejected", "reason": "value", "change_id": cid}
        cid = self._record_change(store, review_ref, key, ctx, kind, sig, ev, why, "applying", before=b, after=a,
                                  now=now)
        src = f"{SOURCE_TAG}{cid}"
        try:
            if kind == "offset_set":
                got = self.deps.judge.set_offset(key, ctx, float(a["offset"]), src) or {}
                if got.get("after") is not None:
                    a = {"offset": round(float(got["after"]), 4)}
            elif kind == "eagerness_set":
                self.deps.judge.set_eagerness(key, a["eagerness"], src)
            elif kind == "lesson_add":
                lid = AL.add(store, agent_key=key, scope=ctx, kind=a["kind"], text=a["text"], source="review",
                             source_refs=list(ev) + [review_ref], at=now)
                a = dict(a, lesson_id=lid)
            elif kind == "lesson_remove":
                if AL.revoke(store, b["lesson_id"], by="review", reason=review_ref, at=now) is None:
                    raise _Reject("lesson")
            else:
                nid = AL.promote(store, b["lesson_id"], by="review", evidence_contexts=a["contexts"],
                                 source_refs=list(ev) + [review_ref], at=now)
                a = dict(a, lesson_id=nid)
        except Exception as ex:  # noqa: BLE001
            code = ex.code if isinstance(ex, _Reject) else f"apply_error: {type(ex).__name__}"
            self._update_change(store, cid, status="rejected", reject_reason=code[:120])
            return {"status": "rejected", "reason": code, "change_id": cid}
        pc = None
        try:
            pc = self._link_policy(store, key, ctx, kind, cid, b, a, now)
        except Exception as ex:  # noqa: BLE001
            print(f"[learn policy link] {type(ex).__name__}: {ex}", file=sys.stderr)
        self._update_change(store, cid, status="applied", after_json=a, policy_change_id=pc)
        return {"status": "applied", "change_id": cid, "policy_change_id": pc, "kind": kind, "before": b, "after": a}

    def _save_proposal(self, store, key, review_ref, area, text, evidence, now) -> Optional[int]:
        body = AL.clean_text(text, 600)
        if not body:
            return None
        with store._Tx(store) as c:
            return int(c.execute("INSERT INTO agent_review_proposals(agent_key,review_ref,area,text,evidence_json,"
                                 "created_at) VALUES(?,?,?,?,?,?)",
                                 (key, review_ref, area if area in PROPOSAL_AREAS else "other", body,
                                  _j([str(x) for x in (evidence or []) if isinstance(x, str)][:10]), now)).lastrowid)

    async def maybe_self_review(self, agent_key: str) -> dict:
        """Tự rà soát một agent khi đủ điều kiện (8.3). Trả {"outcome", ...}."""
        from agent_ledger import CallLedger, ReasonBusy
        store = await asyncio.to_thread(self._store)
        if store is None:
            return {"outcome": "no_store"}
        key = str(agent_key)
        if key in self._self_running:
            return {"outcome": "running"}
        now = float(self.deps.clock())
        ok_due, why, ev = await asyncio.to_thread(self.due, store, key, now)
        if not ok_due:
            return {"outcome": why}
        self._self_running.add(key)
        tok = f"{self.host_id}:{secrets.token_hex(4)}"
        try:
            if not await asyncio.to_thread(self.deps.try_busy, key, tok):
                return {"outcome": "busy"}
            try:
                ok, bwhy = await asyncio.to_thread(self._budget, store, key, "review", now)
                if not ok:
                    await asyncio.to_thread(self._event, store, key, "*", "quota", bwhy or "agent_daily_calls",
                                            {"purpose": "review"}, now)
                    return {"outcome": "quota", "reason": bwhy}
                ledger = CallLedger(store)
                review_ref = f"selfreview:{key}:{int(now * 1000)}"
                try:
                    cid = await asyncio.to_thread(lambda: ledger.reserve(
                        purpose="review", reason_ref=review_ref, agent_key=key, context_ref="*", obligation=False,
                        now=now))
                except ReasonBusy:
                    return {"outcome": "ledger_busy"}
                if cid is None:
                    await asyncio.to_thread(self._event, store, key, "*", "quota", "server_ceiling",
                                            {"purpose": "review"}, now)
                    return {"outcome": "quota", "reason": "server_ceiling"}
                return await self._self_review_run(store, key, ev, ledger, cid, review_ref, now)
            finally:
                try:
                    await asyncio.to_thread(self.deps.release_busy, key, tok)
                except Exception:  # noqa: BLE001
                    pass
        finally:
            self._self_running.discard(key)

    async def _self_review_run(self, store, key, ev, ledger, cid, review_ref, now) -> dict:
        contexts = [c for c in (await asyncio.to_thread(self.deps.contexts, key) or []) if c != "*"]
        if f"dm:{key}" not in contexts:
            contexts.append(f"dm:{key}")
        prompt, shown, known = await asyncio.to_thread(self.self_prompt, store, key, ev, contexts)
        system = (self.deps.persona(key) or "") + SELF_RULES
        out, started, err = await self._run_engine(key, "*", "review", system, prompt, ledger, cid, review_ref)
        if err:
            await asyncio.to_thread(ledger.settle if started else ledger.refund, *((cid, "error") if started
                                                                                 else (cid,)))
            await asyncio.to_thread(self._set_state, store, key, now, False)
            self._event(store, key, "*", "self_review_error", reason=err, payload={"call_id": cid}, at=now)
            return {"outcome": "engine_error", "error": err}
        res, perr = parse_self_review(out.get("text"))
        if res is None:
            await asyncio.to_thread(ledger.settle, cid, "error", out.get("tokens_in"), out.get("tokens_out"))
            await asyncio.to_thread(self._set_state, store, key, now, False)
            self._event(store, key, "*", "self_review_error", reason=perr, payload={"call_id": cid}, at=now)
            return {"outcome": "invalid", "error": perr}
        results, proposals = [], []
        applied = 0
        for i, ch in enumerate(res["changes"]):
            if i >= MAX_CHANGES:
                results.append({"status": "rejected", "reason": "over_limit", "kind": str(ch.get("kind") or "")})
                continue
            r = await asyncio.to_thread(self.apply_change, store, key, ch, shown, known, contexts, review_ref, now)
            if r["status"] == "proposal":
                pid = await asyncio.to_thread(self._save_proposal, store, key, review_ref, "other",
                                              f"{r.get('kind')}: {ch.get('why') or ch.get('text') or ''}",
                                              ch.get("evidence"), now)
                if pid:
                    proposals.append(pid)
            applied += r["status"] == "applied"
            results.append(r)
        for p in res["proposals"][:5]:
            pid = await asyncio.to_thread(self._save_proposal, store, key, review_ref, str(p.get("area") or "other"),
                                          p.get("text"), p.get("evidence"), now)
            if pid:
                proposals.append(pid)
        await asyncio.to_thread(ledger.settle, cid, "ok", out.get("tokens_in"), out.get("tokens_out"))

        def consume():
            with store._Tx(store) as c:
                for ref in shown:
                    c.execute("INSERT OR IGNORE INTO agent_review_consumed(agent_key,source_ref,review_ref,at) "
                              "VALUES(?,?,?,?)", (key, ref, review_ref, now))
        await asyncio.to_thread(consume)
        await asyncio.to_thread(self._set_state, store, key, now, True)
        payload = {"call_id": cid, "review_ref": review_ref, "applied": applied, "results": results,
                   "proposals": proposals, "evidence": sorted(shown)[:EVIDENCE_LIMIT], "reason": res["reason"]}
        self._event(store, key, "*", "self_review", reason=f"applied:{applied}", payload=payload, at=now)
        return dict(payload, outcome="reviewed")

    # ═════════════ quay lại (6.4) ═════════════

    def revert_policy(self, ch: dict) -> None:
        """Hàm quay lại đăng ký với P cho các loại thay đổi của tự rà soát. Chỉ xử lý thay đổi có nguồn `self_review:<mã>`;
        thay đổi của chủ hay của nhãn không bị đụng. Chủ đã đổi lại thiết lập đó sau đó thì giữ thiết lập của chủ."""
        src = str((ch or {}).get("source") or "")
        if not src.startswith(SOURCE_TAG):
            return
        store = self._store()
        if store is None:
            return
        try:
            cid = int(src[len(SOURCE_TAG):])
        except ValueError:
            return
        with closing(store._conn()) as c:
            r = c.execute("SELECT * FROM agent_review_changes WHERE id=?", (cid,)).fetchone()
        if r is None or r["status"] not in ("applied", "kept"):
            return
        key, ctx, kind = r["agent_key"], r["context_ref"], r["kind"]
        b, a = _jl(r["before_json"], {}), _jl(r["after_json"], {})
        now = float(self.deps.clock())
        note = ""
        try:
            if kind == "offset_set":
                if self.deps.judge.owner_held(key, kind, ctx):
                    note = "owner_held"
                else:
                    # Quay lại CHỈ phần dịch của chính thay đổi này (review T3 L P2-4): độ lệch hiện tại trừ (sau - trước),
                    # đã nhạt dần như độ lệch. Phần chủ dạy bằng nhãn trong cửa sổ quan sát được giữ nguyên.
                    import agent_judge_store as AJS
                    delta = AJS.decay(float(a.get("offset") or 0.0) - float(b.get("offset") or 0.0),
                                      float(r["created_at"]), now)
                    cur = float((self.deps.judge.profile(key).get("offsets") or {}).get(ctx, 0.0))
                    self.deps.judge.set_offset(key, ctx, AJS.clamp_offset(cur - delta), f"revert:{src}")
            elif kind == "eagerness_set":
                if self.deps.judge.owner_held(key, kind, ctx):
                    note = "owner_held"
                elif b.get("eagerness"):
                    self.deps.judge.set_eagerness(key, b["eagerness"], f"revert:{src}")
            elif kind == "lesson_add":
                if a.get("lesson_id"):
                    AL.revoke(store, int(a["lesson_id"]), by="auto", reason=f"revert:{src}", at=now)
            elif kind == "lesson_remove":
                AL.restore(store, int(b["lesson_id"]), by="auto", reason=f"revert:{src}", at=now)
            elif kind == "lesson_promote":
                if a.get("lesson_id"):
                    AL.revoke(store, int(a["lesson_id"]), by="auto", reason=f"revert:{src}", at=now)
                AL.restore(store, int(b["lesson_id"]), by="auto", reason=f"revert:{src}", at=now)
        except Exception as ex:  # noqa: BLE001
            note = f"revert_error: {type(ex).__name__}"
        by_owner = str((ch or {}).get("revert_by") or "") == "owner"
        self._update_change(store, cid, status="reverted", reverted_at=now,
                            revert_reason=note or ("owner" if by_owner else "policy_revert"))

    def refresh_policy_labels(self, now: Optional[float] = None) -> int:
        """Trước khi P đóng cửa sổ quan sát: số nhãn và số lỗi phán xử từ sau mỗi thay đổi đang quan sát của tự rà soát
        (`agent_pulse.record_policy_labels`); đồng bộ trạng thái kept/reverted từ P. Trả số thay đổi đã cập nhật."""
        import agent_pulse as AP
        store = self._store()
        if store is None:
            return 0
        t = float(self.deps.clock()) if now is None else float(now)
        with store._Tx(store) as c:
            # Tiến trình chết giữa `applying` và `applied` (review T3 L P3): tác động có thể đã áp mà không có cửa sổ 6.4.
            # Không để ẩn: đánh `interrupted` (hiện trong mục Bài học kèm trước/sau) để chủ kiểm và sửa tay nếu cần.
            c.execute("UPDATE agent_review_changes SET status='interrupted', reject_reason='crash' WHERE status='applying' "
                      "AND created_at<?", (t - APPLYING_STALE_S,))
        with closing(store._conn()) as c:
            rows = [dict(r) for r in c.execute("SELECT * FROM agent_review_changes WHERE status IN ('applied','kept') "
                                               "AND policy_change_id IS NOT NULL").fetchall()]
            pcs = {int(r["id"]): dict(r) for r in c.execute(
                "SELECT id, status, decided_reason FROM pulse_policy_changes WHERE id IN (%s)" %
                ",".join(str(int(r["policy_change_id"])) for r in rows)).fetchall()} if rows else {}
        n = 0
        for r in rows:
            pc = pcs.get(int(r["policy_change_id"]))
            if pc is None:
                continue
            if pc["status"] == "kept" and r["status"] != "kept":
                self._update_change(store, r["id"], status="kept")
                continue
            if pc["status"] == "reverted":
                self._update_change(store, r["id"], status="reverted", reverted_at=t,
                                    revert_reason=pc.get("decided_reason") or "policy_revert")
                continue
            if pc["status"] != "observing":
                continue
            ctx = r["context_ref"]
            rows_l = [d for d in self.deps.judge.labeled(r["agent_key"], float(r["created_at"]))
                      if ctx in ("*", "") or d["context_ref"] == ctx]
            labels, errors = judge_errors(rows_l)
            AP.record_policy_labels(store, int(r["policy_change_id"]), labels, errors)
            n += 1
        return n

    async def tick(self, agents: Optional[Iterable[str]] = None) -> dict:
        """Một nhịp (gọi trước `PulseHost.tick` mỗi 30 giây): cập nhật nhãn cho cửa sổ quan sát, rồi kiểm agent nào đến
        hạn tự rà soát (mỗi agent tối đa một lần kiểm mỗi 10 phút) và chạy ở tác vụ riêng."""
        store = await asyncio.to_thread(self._store)
        if store is None:
            return {"skipped": "no_store"}
        try:
            await asyncio.to_thread(self.refresh_policy_labels)
        except Exception as ex:  # noqa: BLE001
            print(f"[learn labels] {type(ex).__name__}: {ex}", file=sys.stderr)
        try:
            await asyncio.to_thread(self.recover_stale_claims)
            self._publish(getattr(self, "stale_events", []))
        except Exception as ex:  # noqa: BLE001
            print(f"[learn stale] {type(ex).__name__}: {ex}", file=sys.stderr)
        now = float(self.deps.clock())
        spawned = 0
        for key in list(agents or []):
            if key in self._self_running or now - self._self_checked.get(key, 0.0) < 600.0:
                continue
            self._self_checked[key] = now
            try:
                ok_due, _why, _ev = await asyncio.to_thread(self.due, store, key, now)
            except Exception as ex:  # noqa: BLE001
                print(f"[learn due] {key}: {type(ex).__name__}: {ex}", file=sys.stderr)
                continue
            if ok_due:
                self._spawn(self.maybe_self_review(key))
                spawned += 1
        return {"spawned": spawned}

    # ═════════════ hiển thị (mục "lessons" của khung nhịp) ═════════════

    def view_part(self, store, agent_key: str) -> dict:
        import agent_budget as AB
        import agent_pulse as AP
        ensure(store)
        key = str(agent_key)
        rows = AL.lessons(store, key, status="active")
        scopes: dict = {}
        for r in rows:
            scopes.setdefault(r["scope"], []).append({k: r[k] for k in ("id", "scope", "kind", "text", "source",
                                                                        "source_refs", "created_at", "promoted_from")})
        order = sorted(scopes, key=lambda s: (s == "*", not s.startswith("dm:"), s))
        try:
            legacy = list(self.deps.legacy(key) or [])
        except Exception:  # noqa: BLE001
            legacy = []
        with closing(store._conn()) as c:
            changes = [dict(r) for r in c.execute("SELECT * FROM agent_review_changes WHERE agent_key=? AND status<>"
                                                  "'applying' ORDER BY id DESC LIMIT 15", (key,)).fetchall()]
            props = [dict(r) for r in c.execute("SELECT * FROM agent_review_proposals WHERE agent_key=? ORDER BY id "
                                                "DESC LIMIT 5", (key,)).fetchall()]
        pcs = {int(p["id"]): p for p in AP.policy_changes(store, key, 100)}
        out_ch = []
        for ch in changes:
            pc = pcs.get(int(ch["policy_change_id"])) if ch.get("policy_change_id") else None
            out_ch.append({"id": ch["id"], "kind": ch["kind"], "context_ref": ch["context_ref"],
                           "before": _jl(ch["before_json"], {}), "after": _jl(ch["after_json"], {}),
                           "evidence": _jl(ch["evidence_json"], []), "why": ch["why"], "status": ch["status"],
                           "reject_reason": ch["reject_reason"], "created_at": ch["created_at"],
                           "reverted_at": ch["reverted_at"], "revert_reason": ch["revert_reason"],
                           "policy_change_id": ch["policy_change_id"],
                           "can_revert": bool(pc and pc.get("status") != "reverted" and ch["status"] in ("applied",
                                                                                                         "kept"))})
        reviews = AP.events(store, key, kinds=("reaction_review", "self_review"), limit=5)
        reg = store.agent_any(key) or {}
        return {"name": "lessons", "agent_key": key, "slug": reg.get("slug") or "",
                "scopes": [{"scope": s, "lessons": scopes[s]} for s in order], "legacy": legacy,
                "changes": out_ch,
                "proposals": [{"id": p["id"], "area": p["area"], "text": p["text"],
                               "evidence": _jl(p["evidence_json"], []), "created_at": p["created_at"]} for p in props],
                "budget": AB.usage(store, key, float(self.deps.clock())),
                "reviews": [{"id": e["id"], "kind": e["kind"], "context_ref": e["context_ref"], "reason": e["reason"],
                             "created_at": e["created_at"],
                             "status": (e.get("payload") or {}).get("status") or ""} for e in reviews]}


def open_proposals(store, agent_key: str, limit: int = 5) -> list:
    """Open out-of-scope ideas of one assistant, newest first (M5 shows them as procedure drafts)."""
    ensure(store)
    with closing(store._conn()) as c:
        return [{"id": r["id"], "area": r["area"], "text": r["text"], "created_at": r["created_at"]}
                for r in c.execute("SELECT id,area,text,created_at FROM agent_review_proposals WHERE agent_key=? AND "
                                   "status='open' ORDER BY id DESC LIMIT ?", (str(agent_key), int(limit)))]


class _Reject(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


# ═══════════════════════════ hàm cấp module (hợp đồng mục 3) ═══════════════════════════

_DEFAULT: list = [None]


def wire(host: Optional[ReviewHost]) -> Optional[ReviewHost]:
    """`main.py` nối host học mặc định (một lần lúc khởi động) rồi gọi `register_with_pulse()`."""
    _DEFAULT[0] = host
    return host


def default() -> Optional[ReviewHost]:
    return _DEFAULT[0]


def _need() -> ReviewHost:
    h = _DEFAULT[0]
    if h is None:
        raise RuntimeError("agent_review chưa được nối (main.py gọi agent_review.wire)")
    return h


async def serve_reaction_review(reason: dict) -> dict:
    return await _need().serve_reaction_review(reason)


async def maybe_self_review(agent_key: str) -> dict:
    return await _need().maybe_self_review(agent_key)


def pending_reviews(limit: int = 20) -> list:
    return _need().pending_reviews(limit)


def view(store, agent_key: str) -> dict:
    """Mục "lessons" của `GET /agents/{slug}/pulse` (sổ đăng ký của P)."""
    return _need().view_part(store, agent_key)


@dataclass
class LearnRouteDeps:
    brain_key: Callable[[str], str]                         # brain trên dashboard -> đường dẫn đã resolve
    agent_exists: Callable[[str, str], bool]                # (root, slug) -> file trợ lý có thật
    agent_key: Callable[[str, str], Optional[str]]          # (root, slug) -> agent_key đang hoạt động | None
    store: Callable[[], Any]                                # () -> GoalStore | None


def register_routes(app, deps: LearnRouteDeps) -> None:
    """Route của phần học (chỉ của chủ: middleware auth + CSRF của main chặn trước). Hành động chỉ báo thành công SAU khi
    kho đã ghi (200 kèm mục "lessons" mới):
    - `POST /agents/{slug}/lessons/{lesson_id}/revoke`: thu hồi một bài học (giữ lịch sử).
    - `POST /agents/{slug}/lessons/{lesson_id}/promote`: chủ đưa một bài học nhóm/chat riêng lên dùng mọi nơi.
    - `POST /agents/{slug}/budget` {daily_calls: số | "unlimited"}: hạn mức lượt tự phát mỗi ngày của trợ lý.
    Quay lại một thay đổi của tự rà soát dùng route của P (`POST /agents/{slug}/pulse/revert` kèm `change_id`)."""
    from fastapi.responses import JSONResponse
    import localefmt
    import agent_budget as AB

    def err(code, vi, en):
        return JSONResponse({"ok": False, "error": localefmt.chu(vi, en)}, status_code=code)

    async def body_of(request) -> dict:
        try:
            d = await request.json()
            return d if isinstance(d, dict) else {}
        except Exception:  # noqa: BLE001
            return {}

    def resolve(slug: str, brain: str):
        root = deps.brain_key(brain)
        if not deps.agent_exists(root, slug):
            return None, err(404, "Không tìm thấy trợ lý", "Assistant not found")
        key = deps.agent_key(root, slug)
        store = deps.store()
        if not key or store is None:
            return None, err(409, "Trợ lý chưa có bài học hay hạn mức nào", "This assistant has no lessons or limits yet")
        return (key, store), None

    def view_of(store, key):
        h = default()
        return h.view_part(store, key) if h is not None else {"name": "lessons"}

    async def act(slug, brain, fn):
        got, e = await asyncio.to_thread(resolve, slug, brain)
        if e:
            return e
        key, store = got
        try:
            res = await asyncio.to_thread(fn, store, key)
        except PermissionError:
            return err(403, "Chỉ chủ mới đổi được mục này", "Only the owner can change this")
        except ValueError as ex:
            return err(400, f"Yêu cầu không hợp lệ: {ex}", f"Invalid request: {ex}")
        if res is None:
            return err(409, "Không còn gì để đổi (đã đổi trước đó)", "Nothing to change (already done)")
        return {"ok": True, "result": res, "view": await asyncio.to_thread(view_of, store, key)}

    @app.post("/agents/{slug}/lessons/{lesson_id}/revoke")
    async def agent_lesson_revoke(slug: str, lesson_id: int, brain: str = "brain"):
        def fn(store, key):
            r = AL.revoke(store, int(lesson_id), by="owner", reason="owner", agent_key=key)
            return {"lesson_id": r["id"], "status": r["status"]} if r else None
        return await act(slug, brain, fn)

    @app.post("/agents/{slug}/lessons/{lesson_id}/promote")
    async def agent_lesson_promote(slug: str, lesson_id: int, brain: str = "brain"):
        def fn(store, key):
            return {"lesson_id": AL.promote(store, int(lesson_id), by="owner", agent_key=key)}
        return await act(slug, brain, fn)

    @app.post("/agents/{slug}/budget")
    async def agent_budget_set(slug: str, request: Request, brain: str = "brain"):
        b = await body_of(request)
        if "daily_calls" not in b:
            return err(400, "Thiếu hạn mức", "Missing limit")

        def fn(store, key):
            return {"daily_calls": AB.set_cap(store, key, b.get("daily_calls"), by="owner")}
        return await act(slug, brain, fn)


_REGISTERED: list = [False]


def register_with_pulse() -> bool:
    """Cắm vào sổ đăng ký của P (một lần): phục vụ lý do `reaction_review`, mục "lessons" của khung nhịp, hàm quay lại cho
    các loại thay đổi của tự rà soát. Chưa có module của P thì không làm gì (trả False)."""
    if _REGISTERED[0]:
        return True
    try:
        import agent_pulse as AP
        import agent_pulse_host as PH
    except ImportError:
        return False

    async def _handler(_host, reason):
        return await serve_reaction_review(reason)

    PH.register_reason_handler("reaction_review", _handler)
    PH.register_view_part("lessons", lambda store, key: view(store, key))
    for kind in CLOSED_CHANGES:
        AP.register_policy_reverter(kind, lambda ch: _need().revert_policy(ch))
    _REGISTERED[0] = True
    return True
