"""Javis Resonance: lớp mỏng nối hội thoại và engine hiện có với mục tiêu có bằng chứng.

Kế hoạch: docs/superpowers/plans/2026-10-06-resonance-00-mvp.md. File này lớn dần theo mốc:
M1 (ở đây) chỉ có kiểu dữ liệu tối thiểu và một adapter chạy MỘT lượt engine rồi trả một
receipt do host quan sát được. Phân luồng, hình thành mục tiêu, evaluator, kho SQLite là việc
của M2 đến M5.

Đường engine M1 chốt (đã đối chiếu mã 0.83.2, xem docs/dev/resonance-mvp-verification.md):
engine việc nền người dùng chọn ở trang Models, dựng qua aux_engine, ép CHỈ CHỮ (không
công cụ, không MCP, thư mục trống), và KHÔNG có chuỗi dự phòng. Lý do bỏ chuỗi dự phòng:
`aux_engine.swap` ở mức dưới full thêm Claude, bộ não chính, OpenRouter free làm mắt sau,
tức là lượt này có thể lặng lẽ chạy bằng provider khác (kể cả API trả phí). Kế hoạch cấm
tự đổi provider; engine đã chọn không chạy được thì receipt phải nói thẳng như vậy.

Model chỉ sinh chữ. HOST mới là bên ghi đầu ra vào vùng đã cấp cho mục tiêu, rồi tự đọc lại
file vừa ghi để lấy hash. Receipt chỉ chứa thứ host thấy tận mắt, không chép lời tự báo
của model.
"""
from __future__ import annotations

import asyncio
import hashlib
import os
import re
import secrets
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

RECEIPT_STATUSES = ("succeeded", "failed", "uncertain", "cancelled")
ACTION_ID_RE = re.compile(r"^[A-Za-z0-9_-]{6,80}$")
CLAUDE_PROVIDER = "anthropic-cli"
# Engine CLI không mang thuộc tính provider; aux_engine._build_codex / _build_grok dựng đúng các loại này.
_PROVIDER_OF_KIND = {"CodexCLI": "openai-oauth", "GrokCLI": "grok-cli"}
OUTPUT_MAX_CHARS = 200_000
ERROR_DETAIL_MAX = 300

SYSTEM_PROMPT = ("Bạn là bộ thực thi một bước của Javis. Chỉ trả về nội dung được yêu cầu, viết bằng chữ. "
                 "Không gọi công cụ, không đọc hay ghi file, không chạy lệnh: host sẽ tự lưu câu trả lời.")


@dataclass(frozen=True)
class GoalRecord:
    """Mục tiêu tối thiểu M1 cần để chạy một lượt. Host tạo, model không sửa được.

    `output_root` là vùng host được phép ghi đầu ra của mục tiêu này. M2 thêm nguồn yêu cầu,
    cách hiểu, tiêu chí, ràng buộc, hạn mức, lịch và trạng thái bằng migration, không tạo kiểu thứ hai.
    """
    id: str
    brain_id: str
    owner: str
    revision: int
    output_root: str
    request_ref: str = ""


@dataclass(frozen=True)
class ActionReceipt:
    """Thứ host quan sát được sau một lượt. `usage=None` nghĩa là KHÔNG ĐO ĐƯỢC, không phải 0."""
    action_id: str
    goal_id: str
    revision: int
    status: str
    started_at: float
    finished_at: float
    engine: dict
    output_ref: Optional[str] = None
    output_sha256: Optional[str] = None
    output_chars: int = 0
    usage: Optional[dict] = None
    tool_calls_observed: int = 0
    error_code: str = ""
    error_detail: str = ""
    evidence_ids: tuple = ()

    def to_dict(self) -> dict:
        d = asdict(self)
        d["evidence_ids"] = list(self.evidence_ids)
        return d


class CallBudget:
    """Giới hạn số lượt gọi model. Giữ chỗ TRƯỚC khi gọi; hết lượt thì không gọi nữa.

    Gói thuê bao không cho đọc số token còn lại, nên đếm lượt là giới hạn có thật duy nhất ở M1.
    """

    def __init__(self, max_calls: int):
        self.max_calls = max(0, int(max_calls))
        self.used = 0

    @property
    def remaining(self) -> int:
        return max(0, self.max_calls - self.used)

    def try_reserve(self) -> bool:
        if self.used >= self.max_calls:
            return False
        self.used += 1
        return True


def _short(text: Any) -> str:
    return str(text or "").strip().replace("\n", " ")[:ERROR_DETAIL_MAX]


def _usage_from(ev: dict, usage: Optional[dict]) -> Optional[dict]:
    """Gom usage từ hai kiểu sự kiện engine đang phát: final của Claude SDK
    (tokens_in/tokens_out/cost_usd) và usage của engine API (input/output/cost)."""
    t = ev.get("type")
    if t == "final" and any(k in ev for k in ("tokens_in", "tokens_out", "cost_usd")):
        usage = dict(usage or {})
        usage["tokens_in"] = int(ev.get("tokens_in") or 0) + int(usage.get("tokens_in") or 0)
        usage["tokens_out"] = int(ev.get("tokens_out") or 0) + int(usage.get("tokens_out") or 0)
        if ev.get("cost_usd") is not None:
            usage["cost_usd"] = float(ev.get("cost_usd") or 0) + float(usage.get("cost_usd") or 0)
        if ev.get("duration_ms") is not None:
            usage["engine_ms"] = int(ev.get("duration_ms") or 0)
    elif t == "usage":
        usage = dict(usage or {})
        usage["tokens_in"] = int(ev.get("input") or 0) + int(usage.get("tokens_in") or 0)
        usage["tokens_out"] = int(ev.get("output") or 0) + int(usage.get("tokens_out") or 0)
        if ev.get("cost") is not None:
            usage["cost_usd"] = float(ev.get("cost") or 0) + float(usage.get("cost_usd") or 0)
    return usage


def pick_text_only_link(engine: Any, base: Any, requested: dict, chain_type: type = None) -> tuple:
    """Từ engine sau `aux_engine.swap` + `strip_tools`, giữ ĐÚNG mắt người dùng đã chọn.

    Trả (engine, info). engine=None khi không còn đường đáp ứng: mắt đầu không phải provider
    đã chọn nghĩa là swap/strip_tools đã lặng lẽ lùi về Claude (provider chưa sẵn sàng, hoặc
    không tắt được công cụ cho riêng lượt này, như Antigravity). Khi đó KHÔNG chạy thay bằng
    Claude, vì như thế là tự đổi provider.
    """
    if chain_type is not None and isinstance(engine, chain_type):
        links = list(engine._all())
    else:
        links = [engine]
    first = links[0] if links else None
    req_prov = str((requested or {}).get("provider") or CLAUDE_PROVIDER)
    if first is base:
        actual_prov = CLAUDE_PROVIDER
    else:
        # Engine API mang `provider`; CodexCLI/GrokCLI thì không, tra theo loại (aux_engine._build_*).
        actual_prov = str(getattr(first, "provider", "") or _PROVIDER_OF_KIND.get(type(first).__name__)
                          or type(first).__name__)
    info = {
        "requested_provider": req_prov,
        "requested_model": str((requested or {}).get("model") or ""),
        "provider": actual_prov,
        "model": str(getattr(first, "model", "") or ""),
        "kind": type(first).__name__ if first is not None else "",
        "fallback_links_dropped": max(0, len(links) - 1),
        "text_only": True,
    }
    if first is None:
        info["blocked"] = "không dựng được engine nào"
        return None, info
    if actual_prov != req_prov:
        info["blocked"] = (f"engine đã chọn ({req_prov}) không chạy được ở chế độ chỉ chữ; "
                           f"hệ thống định lùi về {actual_prov} nhưng Resonance không tự đổi provider")
        return None, info
    return first, info


@dataclass
class GoalDeps:
    """Những gì một lượt Resonance cần từ host. Model chỉ đề xuất; host xác nhận và ghi.

    `engine_factory(system_prompt, tag) -> (engine | None, info)`. Engine phải theo hợp đồng
    sự kiện của aux_engine: `is_available()` và `async query(prompt)` sinh dict có `type`.
    """
    engine_factory: Callable[[str, str], tuple]
    budget: CallBudget
    clock: Callable[[], float] = time.time
    max_wall_s: int = 600
    # Engine tự dừng ở max_wall_s; thêm khoảng này làm lưới cuối nếu engine không tôn trọng trần.
    wall_grace_s: float = 30.0
    tag: str = "resonance"

    async def run_once(self, goal: GoalRecord, prompt: str, action_id: str) -> ActionReceipt:
        t0 = self.clock()
        engine_info: dict = {}

        def done(status: str, *, code: str = "", detail: str = "", **kw) -> ActionReceipt:
            return ActionReceipt(action_id=action_id, goal_id=goal.id, revision=goal.revision, status=status,
                                 started_at=t0, finished_at=self.clock(), engine=dict(engine_info),
                                 error_code=code, error_detail=_short(detail), **kw)

        if not ACTION_ID_RE.match(str(action_id or "")):
            return done("cancelled", code="invalid_action_id", detail="action_id phải 6-80 ký tự chữ, số, _ hoặc -")
        try:
            root = Path(goal.output_root).resolve()
            out = (root / f"{action_id}.md").resolve()
            out.relative_to(root)
        except Exception as e:  # noqa: BLE001
            return done("cancelled", code="output_scope", detail=f"vùng ghi không hợp lệ: {e}")
        if not root.is_dir():
            return done("cancelled", code="output_scope", detail="vùng ghi chưa được cấp (thư mục không tồn tại)")
        if out.exists():
            # Một action_id chỉ được có MỘT tác động. Chạy lại cùng id không được gọi model lần hai.
            return done("cancelled", code="action_exists", detail="action_id này đã có đầu ra; không chạy lại",
                        output_ref=str(out))
        if not self.budget.try_reserve():
            return done("cancelled", code="budget_exhausted", detail=f"đã dùng hết {self.budget.max_calls} lượt gọi")

        try:
            engine, engine_info = self.engine_factory(SYSTEM_PROMPT, self.tag)
        except Exception as e:  # noqa: BLE001
            return done("failed", code="engine_build", detail=f"{type(e).__name__}: {e}")
        if engine is None:
            return done("failed", code="engine_blocked", detail=engine_info.get("blocked") or "không có engine")
        try:
            if not engine.is_available():
                return done("failed", code="engine_unavailable", detail="engine đã chọn chưa sẵn sàng")
        except Exception as e:  # noqa: BLE001
            return done("failed", code="engine_unavailable", detail=f"{type(e).__name__}: {e}")
        try:
            engine.max_wall_s = int(self.max_wall_s)
        except Exception:  # noqa: BLE001 - engine không có trần riêng thì vẫn còn wait_for bên dưới
            pass

        final_text: Optional[str] = None
        usage: Optional[dict] = None
        tool_calls = 0
        err: Optional[tuple] = None

        async def consume():
            nonlocal final_text, usage, tool_calls, err
            async for ev in engine.query(prompt):
                ev = ev or {}
                t = ev.get("type")
                if t == "tool_call":
                    tool_calls += 1
                elif t == "error":
                    err = ("engine_error", ev.get("content"))
                    return
                usage = _usage_from(ev, usage)
                if t == "final":
                    if ev.get("dua_token"):
                        err = ("engine_session_race", ev.get("content"))
                        return
                    final_text = ev.get("content") or ""

        try:
            await asyncio.wait_for(consume(), timeout=float(self.max_wall_s) + float(self.wall_grace_s))
        except asyncio.TimeoutError:
            return done("failed", code="timeout", detail=f"quá {self.max_wall_s}s", usage=usage,
                        tool_calls_observed=tool_calls)
        except Exception as e:  # noqa: BLE001
            return done("failed", code="engine_exception", detail=f"{type(e).__name__}: {e}", usage=usage,
                        tool_calls_observed=tool_calls)
        if err:
            return done("failed", code=err[0], detail=err[1], usage=usage, tool_calls_observed=tool_calls)
        try:
            import aux_engine
            if final_text is not None and aux_engine.final_loi_dang_nhap(final_text):
                return done("failed", code="engine_auth", detail=final_text, usage=usage,
                            tool_calls_observed=tool_calls)
        except ImportError:
            pass
        if tool_calls:
            # Lượt chỉ chữ mà model vẫn gọi công cụ: sandbox đã chặn, nhưng đầu ra không còn đáng tin
            # là "chỉ sinh chữ". Không ghi, báo thẳng để M3 quyết định chứ không lặng lẽ cho qua.
            return done("failed", code="tool_call_in_text_only", detail=f"{tool_calls} lần gọi công cụ",
                        usage=usage, tool_calls_observed=tool_calls)
        if not (final_text or "").strip():
            return done("failed", code="empty_output", detail="engine không trả chữ nào", usage=usage)
        text = final_text[:OUTPUT_MAX_CHARS]
        if not text.endswith("\n"):
            text += "\n"

        # Host ghi, rồi host tự đọc lại để lấy hash. Ghi tạm rồi đổi tên: không để lại file dở.
        tmp = out.with_name(f".{action_id}.{secrets.token_hex(4)}.tmp")
        try:
            with open(tmp, "x", encoding="utf-8", newline="\n") as f:
                f.write(text)
            if out.exists():
                tmp.unlink()
                return done("cancelled", code="action_exists", detail="có lượt khác vừa ghi cùng action_id",
                            usage=usage)
            os.replace(tmp, out)
            data = out.read_bytes()
        except Exception as e:  # noqa: BLE001
            try:
                tmp.unlink()
            except OSError:
                pass
            return done("failed", code="write_failed", detail=f"{type(e).__name__}: {e}", usage=usage)
        return done("succeeded", output_ref=str(out), output_sha256=hashlib.sha256(data).hexdigest(),
                    output_chars=len(data.decode("utf-8")), usage=usage, tool_calls_observed=0)
