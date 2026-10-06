"""API của Hệ thống cộng hưởng cho dashboard (M4): thẻ "Em đang hướng tới", phản hồi có nghĩa rõ, lệnh của người dùng.

Kế hoạch: docs/superpowers/plans/2026-10-06-resonance-00-mvp.md, Task M4. Dashboard có một tài khoản đăng nhập
duy nhất; middleware `_auth_guard` và `_csrf_guard` của main.py đã chặn trước khi tới đây, nên request tới được
route này là của người dùng (owner). Host tự dựng Principal từ đó và từ brain đã resolve; id hay đường dẫn trong
body không làm quyền.

Lỗi trả mã rõ: 404 không có mục tiêu trong brain này, 409 revision hoặc sản phẩm đã đổi (kèm trạng thái hiện tại
để thẻ vẽ lại), 400 payload sai luật, 403 Resonance chưa bật ở brain.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional

from fastapi import Request
from fastapi.responses import JSONResponse

import localefmt
import resonance as R
import resonance_store as RS


@dataclass
class ResonanceApiDeps:
    store: Callable[[], Any]              # () -> GoalStore (mở lười)
    brain_key: Callable[[str], str]       # tên brain từ dashboard -> đường dẫn đã resolve
    engine_factory: Callable[..., tuple]  # engine chỉ chữ của Resonance (M1)
    session_store: Callable[[], Any]      # () -> SessionStore (đọc tin gốc cho /goal-requests)


async def _body(request: Request) -> dict:
    ctype = request.headers.get("content-type", "")
    try:
        if "application/json" in ctype:
            data = await request.json()
            return data if isinstance(data, dict) else {}
        form = await request.form()
        return {k: form.get(k) for k in form.keys()}
    except Exception:  # noqa: BLE001
        return {}


def _err(code: int, vi: str, en: str, **extra) -> JSONResponse:
    return JSONResponse({"ok": False, "error": localefmt.chu(vi, en), **extra}, status_code=code)


def set_enabled(brain_root: str, on: bool) -> None:
    """Bật/tắt Resonance cho MỘT brain (`<brain>/Javis/resonance.json`). Ghi tạm rồi đổi tên, giữ khoá lạ khác."""
    f = Path(brain_root) / "Javis" / "resonance.json"
    f.parent.mkdir(parents=True, exist_ok=True)
    data = {}
    try:
        data = json.loads(f.read_text(encoding="utf-8")) if f.is_file() else {}
        if not isinstance(data, dict):
            data = {}
    except Exception:  # noqa: BLE001
        data = {}
    data["enabled"] = bool(on)
    tmp = f.with_name(f".{f.name}.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    tmp.replace(f)


def register(app, deps: ResonanceApiDeps):
    def _ctx(brain: str):
        root = deps.brain_key(brain or "")
        if not root or not Path(root).is_dir():
            return None, None
        return root, RS.Principal("owner", "owner", root)

    def _need(brain: str):
        root, owner = _ctx(brain)
        if root is None:
            return None, None, _err(404, "Không tìm thấy brain", "Brain not found")
        if not R.enabled_for(root):
            return None, None, _err(403, "Hệ thống cộng hưởng chưa bật ở brain này",
                                    "Resonance is not enabled for this brain")
        return root, owner, None

    @app.get("/resonance/settings")
    async def resonance_settings(brain: str = "brain"):
        root, _ = _ctx(brain)
        if root is None:
            return _err(404, "Không tìm thấy brain", "Brain not found")
        return {"ok": True, "enabled": R.enabled_for(root)}

    @app.post("/resonance/settings")
    async def resonance_settings_set(request: Request, brain: str = "brain"):
        root, _ = _ctx(brain)
        if root is None:
            return _err(404, "Không tìm thấy brain", "Brain not found")
        body = await _body(request)
        on = str(body.get("enabled", "")).strip().lower() in ("1", "true", "on", "yes")
        set_enabled(root, on)
        return {"ok": True, "enabled": R.enabled_for(root)}

    @app.get("/resonance/goals")
    async def resonance_goals(brain: str = "brain", session_id: Optional[str] = None):
        root, owner, err = _need(brain)
        if err:
            return err
        store = deps.store()
        goals = store.list_open(owner, session_id=session_id)
        return {"ok": True, "goals": [R.goal_view(store, owner, g.id, root) for g in goals[:20]]}

    @app.get("/goals/{goal_id}")
    async def goal_get(goal_id: str, brain: str = "brain"):
        root, owner, err = _need(brain)
        if err:
            return err
        view = R.goal_view(deps.store(), owner, goal_id, root)
        if view is None:
            return _err(404, "Không có mục tiêu này trong brain", "No such goal in this brain")
        return {"ok": True, "goal": view}

    @app.post("/goals/{goal_id}/feedback")
    async def goal_feedback(goal_id: str, request: Request, brain: str = "brain"):
        root, owner, err = _need(brain)
        if err:
            return err
        body = await _body(request)
        store = deps.store()
        try:
            res = R.apply_feedback(store, owner, goal_id, str(body.get("kind") or ""), body)
        except RS.ScopeError:
            return _err(404, "Không có mục tiêu này trong brain", "No such goal in this brain")
        except RS.ConflictError as e:
            return _err(409, f"Mục tiêu đã đổi, xem lại thẻ: {e}", f"The goal changed, please review the card: {e}",
                        goal=R.goal_view(store, owner, goal_id, root))
        except R.GoalRejected as e:
            return _err(400, f"Chưa ghi được: {e}", f"Not recorded: {e}")
        except PermissionError as e:
            return _err(403, str(e), str(e))
        return {"ok": True, **res, "goal": R.goal_view(store, owner, goal_id, root)}

    @app.post("/goals/{goal_id}/commands")
    async def goal_command(goal_id: str, request: Request, brain: str = "brain"):
        root, owner, err = _need(brain)
        if err:
            return err
        body = await _body(request)
        store = deps.store()
        try:
            res = R.apply_command(store, owner, goal_id, str(body.get("command") or ""), body, root)
        except RS.ScopeError:
            return _err(404, "Không có mục tiêu này trong brain", "No such goal in this brain")
        except RS.ConflictError as e:
            return _err(409, f"Mục tiêu đã đổi, xem lại thẻ: {e}", f"The goal changed, please review the card: {e}",
                        goal=R.goal_view(store, owner, goal_id, root))
        except R.GoalRejected as e:
            return _err(400, f"Chưa làm được: {e}", f"Not done: {e}")
        except PermissionError as e:
            return _err(403, str(e), str(e))
        return {**res, "goal": R.goal_view(store, owner, goal_id, root)}

    @app.post("/goal-requests")
    async def goal_request(request: Request, brain: str = "brain"):
        """Người dùng chủ động bảo theo đuổi một tin nhắn đã gửi (message_ref "msg:<phiên>:<id>"). Tin phải là tin
        của NGƯỜI DÙNG trong phiên thuộc brain này. Một tin chỉ một mục tiêu; không có đề xuất của bộ não thì bộ lập
        mục tiêu gọi MỘT lượt chỉ chữ."""
        root, _owner, err = _need(brain)
        if err:
            return err
        body = await _body(request)
        mref = str(body.get("message_ref") or "")
        parts = mref.split(":")
        if len(parts) != 3 or parts[0] != "msg" or not parts[2].isdigit():
            return _err(400, "message_ref phải có dạng msg:<phiên>:<id>", "message_ref must be msg:<session>:<id>")
        sid, mid = parts[1], int(parts[2])
        ss = deps.session_store()
        sess = ss.get_session(sid) or {}
        if not sess or deps.brain_key(sess.get("brain") or "") != root:
            return _err(404, "Không có phiên này trong brain", "No such session in this brain")
        msg = next((m for m in ss.get_messages(sid) if int(m.get("id") or 0) == mid), None)
        if msg is None or msg.get("role") != "user":
            return _err(400, "Chỉ lập mục tiêu từ tin của người dùng", "A goal can only come from a user message")
        import nghe_sua
        text = nghe_sua.split_ui_context(str(msg.get("content") or ""))[1]
        p = RS.Principal("agent", "javis", root)
        store = deps.store()
        gdeps = R.GoalDeps(engine_factory=deps.engine_factory, budget=R.CallBudget(1), store=store)
        try:
            g = await R.form_goal(mref, {"principal": p, "brain_root": root, "session_id": sid, "message_id": mid,
                                        "user_text": text, "constraints": []}, gdeps)
        except R.GoalRejected as e:
            return _err(400, f"Chưa lập được mục tiêu: {e}", f"Could not set the goal: {e}")
        return {"ok": True, "goal": R.goal_view(store, RS.Principal("owner", "owner", root), g.id, root)}
