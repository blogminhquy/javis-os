"""Nhịp tim thích nghi của Resonance (A2): chính sách thuần `heartbeat.v1`.

Không I/O, không đọc kho hay file: nhận dữ kiện, trả quyết định. Kho (`resonance_store`) giữ lý do thức và lịch;
`resonance.advance` gom dữ kiện, gọi các hàm ở đây, rồi ghi kết quả. Thiết kế:
`docs/superpowers/specs/2026-10-08-resonance-a2-heartbeat-design.md` (mục 3, 4).

Ba nguyên tắc:
- Chỉ LÝ DO mở được lượt model: bước đầu chưa làm, tin mới từ người dùng, hay thử lại tự động còn trong trần.
  Lần thức chỉ để kiểm (xem lại, hạn chót, mã lạ) không bao giờ gọi model.
- Mọi thử lại tự động dùng chung một luật: chừa lượt dự phòng cho lúc người dùng góp ý, và có trần riêng.
- Tham số là hằng có phiên bản, không phải ô cài đặt. Đổi mặc định thì tăng `POLICY_VERSION`.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional

# heartbeat.v2 (A3): thêm hai lớp sự kiện của làn học cách làm, `FOLLOWUP` (lượt làm sản phẩm bằng cách mới, dùng
# lượt đã giữ sẵn) và `TRIAL` (phép thử M5). Các tham số còn lại giữ nguyên như v1.
POLICY_VERSION = "heartbeat.v2"

POLICY = {
    "RETRY_BASE_S": 15 * 60,
    "STALL_AFTER": 2,
    "AUTO_RESERVE_CALLS": 1,
    "ERROR_MAX_FAILS": 3,
    "ERROR_BACKOFF_S": (3600, 4 * 3600, 24 * 3600),
    "REVIEW_MIN_S": 6 * 3600,
    "REVIEW_MAX_S": 7 * 86400,
    "CHECK_MIN_S": 15 * 60,
    "GUARD_OBSERVE_S": 3600,
    "DRIFT_RECHECK_MIN_S": 3600,
    "DRIFT_RECHECK_MAX_S": 86400,
    "HANDOFF_POLL_S": 30,
}

# Lớp của từng mã lý do (mục 3). Mã không có ở đây là "check": chỉ kiểm, không gọi model.
START, NEW, AUTO, CHECK, OBSERVE = "start", "new", "auto", "check", "observe"
FOLLOWUP, TRIAL = "followup", "trial"
CLASSES = {
    "created": START, "revised": START, "assigned": START,
    "feedback": NEW, "user_schedule": NEW,
    "retry_not_met": AUTO, "error_retry": AUTO, "recovery": AUTO,
    "guard_observe": OBSERVE,
    "method_followup": FOLLOWUP, "method_trial": TRIAL,
}
# Nghĩa vụ (slot) của hẹn giờ: hẹn mới chỉ thay hẹn cũ cùng nghĩa vụ.
RETRY_CODES = ("retry_not_met", "error_retry", "recovery")
UNPARK_CODES = ("agent_recheck", "guard_recheck", "drift_recheck", "handoff_wait")

# Lỗi cố định: thử lại tự động không giúp gì (mục 4). Mã chưa biết coi là tạm thời, vẫn bị trần.
FIXED_ERRORS = frozenset({"engine_build", "engine_blocked", "output_scope", "budget_exhausted", "invalid_action_id"})


def classify(code: str) -> str:
    return CLASSES.get(str(code or ""), CHECK)


def slot_of(code: str) -> str:
    code = str(code or "")
    if code in RETRY_CODES:
        return "retry"
    if code == "guard_observe":
        return "observe"
    if code == "trial_recovery":
        # A3: hẹn đối soát của phép thử có nghĩa vụ riêng, không thay hay bị thay bởi các hẹn kiểm khác.
        return "trial"
    return "check"


def is_fixed_error(code: str) -> bool:
    return str(code or "") in FIXED_ERRORS


@dataclass(frozen=True)
class Chain:
    """Chuỗi lượt việc của revision hiện tại, tính từ tin mới gần nhất (hay từ đầu revision).

    `best`: số tiêu chí đạt cao nhất đã thấy (-1 khi chưa có lượt nào thành công). `stall`: số lượt thành công liên
    tiếp không vượt `best`. `fails`: số lượt lỗi. `last_error`: mã lỗi của lượt cuối nếu lượt cuối lỗi."""
    best: int = -1
    stall: int = 0
    fails: int = 0
    last_error: str = ""


def chain_from(attempts: Iterable[dict]) -> Chain:
    """Dựng chuỗi từ các lượt việc theo thứ tự thời gian. Mỗi lượt: {"met_count": int | None, "error": str}.
    met_count None là lượt lỗi. Lượt tụt rồi hồi về mốc cũ không phải tiến bộ, nên dao động không đặt lại chuỗi."""
    best, stall, fails, last_error = -1, 0, 0, ""
    for a in attempts:
        mc = a.get("met_count")
        if mc is None and str(a.get("error") or "") == "held":
            # Đầu ra giữ lại vì bị chặn ngay trước khi đăng: chưa biết kết quả, không phải lỗi, không phải tiến bộ.
            continue
        if mc is None:
            fails += 1
            last_error = str(a.get("error") or "failed")
            continue
        last_error = ""
        if int(mc) > best:
            best, stall = int(mc), 0
        else:
            stall += 1
    return Chain(best, stall, fails, last_error)


def budget_left(budget_calls: int, calls_used: int) -> int:
    return max(0, int(budget_calls or 0) - int(calls_used or 0))


def auto_allowed(code: str, chain: Chain, left: int, policy: dict = POLICY) -> tuple:
    """Một luật chung cho mọi thử lại tự động. Trả (được, lý do)."""
    if left <= int(policy["AUTO_RESERVE_CALLS"]):
        return False, "reserve"
    if code == "retry_not_met":
        return (chain.stall < int(policy["STALL_AFTER"]), "stalled")
    if chain.last_error and is_fixed_error(chain.last_error):
        return False, "fixed_error"
    return (chain.fails < int(policy["ERROR_MAX_FAILS"]), "error_cap")


@dataclass(frozen=True)
class Decision:
    action: str          # work | trial | evaluate | budget
    why: str
    trigger: str = ""    # mã lý do đã mở lượt


def decide(snapshot: Iterable[dict], *, attempted: bool, outcome: str, left: int, chain: Chain,
           policy: dict = POLICY, hold_ok: bool = False, trial_ok: bool = False) -> Decision:
    """Thứ tự quyết định (mục 4, bước 4 tới 9), SAU khi cổng đã cho qua và không bị chờ do sửa ngoài luồng.

    `snapshot`: lý do đã tới hạn, mỗi lý do có "code". `attempted`: revision hiện tại đã có lượt việc hay bản tiếp
    nhận từ chat. `outcome`: met | human_only | not_met | unknown (đánh giá bằng code ngay lúc thức).

    A3: `hold_ok` là có một lượt đã giữ sẵn còn hợp lệ cho đúng revision (tin mới tiếp quản nó, lượt `FOLLOWUP` dùng
    nó, không cần phần dư trên lượt dự phòng); `trial_ok` là phép thử đủ ngân sách trọn vòng. Thứ tự: tin mới, bước đầu,
    lượt làm sản phẩm bằng cách mới, phép thử, thử lại tự động."""
    codes = [str(r.get("code") or "") for r in snapshot]
    classes = {c: classify(c) for c in codes}
    if outcome in ("met", "human_only"):
        return Decision("evaluate", "đã đạt hay chỉ còn chờ người dùng")
    new = next((c for c in codes if classes[c] == NEW), "")
    if new:
        return Decision("work" if (left > 0 or hold_ok) else "budget", "có tin mới từ người dùng", new)
    start = next((c for c in codes if classes[c] == START), "")
    if start and not attempted:
        return Decision("work" if left > 0 else "budget", "bước đầu của revision", start)
    follow = next((c for c in codes if classes[c] == FOLLOWUP), "")
    if follow and hold_ok:
        return Decision("work", "làm sản phẩm bằng cách làm vừa học, dùng lượt đã giữ", follow)
    trial = next((c for c in codes if classes[c] == TRIAL), "")
    if trial and trial_ok:
        return Decision("trial", "thử một cách làm khác khi bế tắc, đủ ngân sách trọn vòng", trial)
    for c in codes:
        if classes[c] == AUTO:
            ok, why = auto_allowed(c, chain, left, policy)
            if ok:
                return Decision("work", "thử lại tự động trong trần", c)
    return Decision("evaluate", "không có lý do mở lượt model")


def retry_due(chain: Chain, now: float, policy: dict = POLICY) -> float:
    return float(now) + float(policy["RETRY_BASE_S"]) * (2 ** max(0, int(chain.stall)))


def error_due(fails: int, now: float, reset_at: float = 0.0, policy: dict = POLICY) -> float:
    if reset_at and reset_at > now:
        return float(reset_at) + 60.0
    steps = policy["ERROR_BACKOFF_S"]
    return float(now) + float(steps[min(max(0, int(fails) - 1), len(steps) - 1)])


def next_interval(prev: Optional[float], changed: bool, lo: float, hi: float) -> float:
    """Khoảng giãn dần: lần đầu hay có thay đổi thì `lo`; không đổi thì nhân đôi, tối đa `hi`."""
    if changed or not prev or prev < lo:
        return float(lo)
    return float(min(float(hi), float(prev) * 2))


def check_due(now: float, review_interval: float, horizon: Optional[dict], policy: dict = POLICY) -> tuple:
    """Hẹn kiểm (nghĩa vụ `check`): (thời điểm, mã). Hạn chót gần thì ưu tiên theo mục 4.

    - Còn hơn 2 × CHECK_MIN_S: sớm nhất giữa lịch xem lại và nửa thời gian còn lại.
    - Còn từ 0 tới 2 × CHECK_MIN_S: một lần kiểm đúng hạn.
    - Qua hạn: lịch xem lại thường (người gọi tự báo qua hạn một lần)."""
    review = float(now) + float(review_interval)
    h = dict(horizon or {})
    try:
        at = float(h.get("at") or 0) if h.get("kind") == "deadline" else 0.0
    except (TypeError, ValueError):
        at = 0.0
    if at > now:
        left = at - now
        if left > 2 * float(policy["CHECK_MIN_S"]):
            half = float(now) + left / 2
            return (half, "deadline") if half < review else (review, "review")
        return at, "deadline"
    return review, "review"


def deadline_passed(now: float, horizon: Optional[dict]) -> bool:
    h = dict(horizon or {})
    if h.get("kind") != "deadline":
        return False
    try:
        at = float(h.get("at") or 0)
    except (TypeError, ValueError):
        return False
    return 0 < at <= now
