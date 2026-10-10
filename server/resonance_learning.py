"""Học có kiểm chứng của Resonance (A3): chính sách thuần `learning.v2` (v2 thêm thời gian chờ sau Thu hồi).

Không I/O: nhận dữ kiện, trả quyết định. Kho (`resonance_store`) giữ reaction, bài học và sổ giữ lượt; `resonance` dựng
tin báo và chạy phép thử. Thiết kế: `docs/superpowers/specs/2026-10-09-resonance-a3-feedback-learning-design.md`.

Hai làn tách riêng:
- Làn P (trình bày): reaction trên tin báo do host ghi chỉ ĐỀ XUẤT cách báo; owner xem trước rồi tự áp dụng. 0 lượt model.
- Làn M (cách làm): bế tắc khách quan mở một phép thử M5 khi đủ ngân sách trọn vòng và có tình huống giữ riêng.

Tham số là hằng có phiên bản, không phải ô cài đặt. Đổi mặc định thì tăng `POLICY_VERSION`.
"""
from __future__ import annotations

from typing import Iterable, Optional

POLICY_VERSION = "learning.v2"

DAY = 86400
POLICY = {
    "P_WINDOW_S": 30 * DAY,
    "P_MIN_MESSAGES": 2,
    "P_REVERT_MIN_MESSAGES": 1,
    "P_PROPOSAL_TTL_S": 14 * DAY,
    "P_DISMISS_COOLDOWN_S": 14 * DAY,
    # learning.v2 (sau pilot A3): Thu hồi cũng chờ như Bỏ qua, để phản hồi cũ không đề xuất lại ngay đúng thay đổi
    # chủ vừa thu hồi. Chỉ chặn cùng (trợ lý, khoá, giá trị); thay đổi khác, trợ lý khác và làn cách làm không đổi.
    "P_REVOKE_COOLDOWN_S": 14 * DAY,
    "M_HOLDOUT_MAX": 1,
    "M_HOLDOUT_SCAN": 5,
}

# Ứng viên duy nhất khi bế tắc: cách làm có hiệu lực -> cách làm thử. Không có mục thì không đề xuất.
METHOD_CANDIDATES = {"work.v1": "work.checklist.v1"}
FOLLOWUP_CALLS = 1

REACTION_VALUES = ("up", "down", "none")
REACTION_REASONS = ("too_long", "too_often", "unclear")

# Mục trình bày khai báo sẵn. `kinds`: loại tin khoá này được đổi. Mọi loại tin khác giữ mặc định.
PRESENTATION = {
    "notice_detail": {"default": "full", "values": ("full", "brief"), "kinds": ("goal.succeeded", "goal.maintained")},
    "notice_ping": {"default": "ping", "values": ("ping", "quiet"), "kinds": ("goal.maintained",)},
}
# Tin bắt buộc: luôn đầy đủ, luôn rung chuông; làn P không đụng tới (thiết kế mục 5.1). Test khoá danh sách này.
MANDATORY_KINDS = ("goal.guard", "goal.monitoring_lost", "goal.deadline_passed", "goal.publish_conflict",
                   "goal.failed", "goal.blocked", "goal.waiting_human", "goal.stalled", "goal.discovery_done",
                   "goal.method_changed")

# Trạng thái bài học. Đang chờ: tối đa một mỗi khoá và phạm vi; đang dùng: tối đa một (hai chỉ mục riêng).
PENDING_STATUSES = ("proposed", "trial_pending", "trialing")
LESSON_STATUSES = ("proposed", "trial_pending", "trialing", "active", "superseded", "revoked", "dismissed", "expired",
                   "stale", "skipped", "rejected", "unknown", "out_of_scope")


def default_presentation() -> dict:
    return {k: v["default"] for k, v in PRESENTATION.items()}


def presentation_for(kind: str, active: Optional[dict]) -> dict:
    """Cách dựng MỘT tin: {"detail": full|brief, "quiet": bool}. Tin bắt buộc luôn đầy đủ và rung chuông."""
    eff = {**default_presentation(), **{k: v for k, v in dict(active or {}).items() if k in PRESENTATION}}
    if kind in MANDATORY_KINDS:
        return {"detail": "full", "quiet": False}
    detail = eff["notice_detail"] if kind in PRESENTATION["notice_detail"]["kinds"] else "full"
    quiet = eff["notice_ping"] == "quiet" and kind in PRESENTATION["notice_ping"]["kinds"]
    return {"detail": detail if detail in PRESENTATION["notice_detail"]["values"] else "full", "quiet": bool(quiet)}


def _live(reactions: Iterable[dict], now: float, policy: dict) -> list:
    lo = float(now) - float(policy["P_WINDOW_S"])
    return [r for r in reactions if r.get("alive") and float(r.get("updated_at") or 0) >= lo]


def _msgs(rows: list, reason: str, kinds: tuple, detail: Optional[str] = None) -> list:
    """Số TIN khác nhau có giá trị hiện tại `down` + `reason`: bấm nhiều lần trên một tin vẫn là một tin."""
    seen = {}
    for r in rows:
        if r.get("value") != "down" or r.get("reason") != reason or r.get("notice_kind") not in kinds:
            continue
        if detail is not None and r.get("presentation") != detail:
            continue
        seen.setdefault(r["message"], r)
    return list(seen.values())


def propose(reactions: Iterable[dict], active: dict, pending_keys: Iterable[str], dismissed: Iterable[dict],
            now: float, policy: dict = POLICY) -> Optional[dict]:
    """Bộ học làn P. Đầu vào:
    - `reactions`: giá trị HIỆN TẠI của mỗi người trên mỗi tin của một trợ lý: {message, notice_kind, presentation,
      value, reason, alive, updated_at, ref}. `alive` False là mồ côi (tin bị xoá hay nội dung đổi): không đếm.
    - `active`: {khoá: giá trị} đang có hiệu lực (thiếu khoá là mặc định).
    - `pending_keys`: các khoá đang có đề xuất chờ.
    - `dismissed`: bài học chủ đã Bỏ qua hay Thu hồi {key, to_value, decided_at, status}. `status='revoked'` chờ
      `P_REVOKE_COOLDOWN_S`, còn lại chờ `P_DISMISS_COOLDOWN_S`; hết thời gian chờ chỉ đề xuất lại khi vẫn đủ phản hồi
      còn sống trong cửa sổ, và vẫn chỉ là đề xuất.
    Trả đề xuất {key, from_value, to_value, evidence} hay None. Không bao giờ tự áp dụng. Im lặng không phải tín hiệu."""
    rows = _live(reactions, now, policy)
    eff = {**default_presentation(), **dict(active or {})}
    pend = set(pending_keys or ())
    def _cool(d) -> float:
        k = "P_REVOKE_COOLDOWN_S" if d.get("status") == "revoked" else "P_DISMISS_COOLDOWN_S"
        return float(policy.get(k, policy["P_DISMISS_COOLDOWN_S"]))

    blocked = {(d.get("key"), d.get("to_value")) for d in (dismissed or ())
               if float(d.get("decided_at") or 0) >= float(now) - _cool(d)}

    def make(key, to, hits):
        if key in pend or (key, to) in blocked or eff[key] == to:
            return None
        return {"key": key, "from_value": eff[key], "to_value": to,
                "evidence": sorted(h.get("ref") or "" for h in hits)}

    det = PRESENTATION["notice_detail"]
    if eff["notice_detail"] == "brief":
        hits = _msgs(rows, "unclear", det["kinds"], detail="brief")
        if len(hits) >= int(policy["P_REVERT_MIN_MESSAGES"]):
            p = make("notice_detail", "full", hits)
            if p:
                return p
    else:
        hits = _msgs(rows, "too_long", det["kinds"])
        if len(hits) >= int(policy["P_MIN_MESSAGES"]):
            p = make("notice_detail", "brief", hits)
            if p:
                return p
    if eff["notice_ping"] == "ping":
        hits = _msgs(rows, "too_often", PRESENTATION["notice_ping"]["kinds"])
        if len(hits) >= int(policy["P_MIN_MESSAGES"]):
            return make("notice_ping", "quiet", hits)
    return None


def still_supported(lesson: dict, reactions: Iterable[dict], now: float, policy: dict = POLICY) -> bool:
    """Đề xuất làn P còn đủ số tin làm căn cứ (sau khi có tin bị xoá hay reaction bị thu hồi) không."""
    rows = _live(reactions, now, policy)
    key, to = lesson.get("key"), lesson.get("to_value")
    if key == "notice_detail" and to == "brief":
        return len(_msgs(rows, "too_long", PRESENTATION["notice_detail"]["kinds"])) >= int(policy["P_MIN_MESSAGES"])
    if key == "notice_detail" and to == "full":
        return len(_msgs(rows, "unclear", PRESENTATION["notice_detail"]["kinds"], detail="brief")) >= int(
            policy["P_REVERT_MIN_MESSAGES"])
    if key == "notice_ping" and to == "quiet":
        return len(_msgs(rows, "too_often", PRESENTATION["notice_ping"]["kinds"])) >= int(policy["P_MIN_MESSAGES"])
    return True


# ───────────── làn M ─────────────

def method_candidate(effective_ref: str) -> str:
    return METHOD_CANDIDATES.get(str(effective_ref or ""), "")


def trial_cost(n_cases: int) -> int:
    return 2 * max(0, int(n_cases))


def full_cycle(budget_calls: int, calls_used: int, explore_used: int, cost: int, explore_cap: int,
               reserve: int) -> tuple:
    """Ngân sách trọn vòng (thiết kế mục 6.3): phép thử trong phần khám phá, cộng một lượt làm sản phẩm giữ sẵn, cộng
    lượt dự phòng. Trả (được, lý do)."""
    if int(explore_used) + int(cost) > int(explore_cap):
        return False, "budget"
    if int(calls_used) + int(cost) + FOLLOWUP_CALLS + int(reserve) > int(budget_calls):
        return False, "budget"
    return True, ""
