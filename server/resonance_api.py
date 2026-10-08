"""API của Hệ thống cộng hưởng cho dashboard (M4): thẻ "Javis đang hướng tới", phản hồi có nghĩa rõ, lệnh của người dùng.

Kế hoạch: docs/superpowers/plans/2026-10-06-resonance-00-mvp.md, Task M4. Dashboard có một tài khoản đăng nhập
duy nhất; middleware `_auth_guard` và `_csrf_guard` của main.py đã chặn trước khi tới đây, nên request tới được
route này là của người dùng (owner). Host tự dựng Principal từ đó và từ brain đã resolve; id hay đường dẫn trong
body không làm quyền.

Lỗi trả mã rõ: 404 không có mục tiêu trong brain này, 409 revision hoặc sản phẩm đã đổi (kèm trạng thái hiện tại
để thẻ vẽ lại), 400 payload sai luật, 403 trợ lý của mục tiêu chưa bật Cộng hưởng (chỉ cho phản hồi và lập mục tiêu
mới; xem thẻ và lệnh tạm dừng, huỷ, tiếp tục, bỏ chỉ dẫn luôn dùng được để người dùng can thiệp kể cả khi đã tắt).

A1 (Cộng hưởng theo từng agent): công tắc nằm ở sổ đăng ký agent trong kho, chỉ đổi qua các route `/resonance/agents*`
dưới đây. Công tắc brain cũ (`/resonance/settings`, `Javis/resonance.json`) còn đọc ghi được nhưng không cấp quyền gì.
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
    # A1. agents_meta(root) -> [{slug, name, provider}] của các file agent trong brain; agent_file(root, slug) -> Path
    # hay None (slug hợp lệ và file có thật).
    agents_meta: Callable[[str], list] = lambda root: []
    agent_file: Callable[[str, str], Any] = lambda root, slug: None


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


def _store_exists() -> bool:
    """Kho đã có chưa: các route đọc không được tạo kho chỉ để trả "chưa có gì"."""
    from config import STATE_DIR
    return (Path(STATE_DIR) / "resonance.sqlite3").is_file()


def register(app, deps: ResonanceApiDeps):
    def _ctx(brain: str):
        root = deps.brain_key(brain or "")
        if not root or not Path(root).is_dir():
            return None, None
        return root, RS.Principal("owner", "owner", root)

    def _off(why: str) -> JSONResponse:
        return _err(403, f"Trợ lý chưa bật Cộng hưởng ({why})", f"The assistant has Resonance turned off ({why})",
                    reason=why)

    @app.get("/resonance/settings")
    async def resonance_settings(brain: str = "brain"):
        """Công tắc brain CŨ: chỉ để hiện nhãn. `legacy: true` nói rõ nó không còn cấp quyền (A1)."""
        root, _ = _ctx(brain)
        if root is None:
            return _err(404, "Không tìm thấy brain", "Brain not found")
        return {"ok": True, "enabled": R.enabled_for(root), "legacy": True}

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
    async def resonance_goals(brain: str = "brain", session_id: Optional[str] = None,
                              agent_key: Optional[str] = None, unassigned: int = 0):
        """Mục tiêu đang mở. `agent_key`: của một trợ lý (khung "Mục tiêu của trợ lý"); `unassigned=1`: mục "Chờ gán"."""
        root, owner, err = _manage(brain)
        if err:
            return err
        store = deps.store()
        goals = store.list_open(owner, session_id=session_id, agent_key=agent_key or None, unassigned=bool(unassigned))
        return {"ok": True, "goals": [R.goal_view(store, owner, g.id, root) for g in goals[:20]]}

    def _manage(brain: str):
        """Xem và can thiệp (tạm dừng, huỷ, tiếp tục, bỏ chỉ dẫn) KHÔNG đòi công tắc bật (review M4, P2-1): tắt
        Resonance không được ngăn người dùng dừng hay huỷ mục tiêu đang có. Việc chạy tiếp vẫn bị công tắc chặn ở
        advance/_gate; phản hồi và lập mục tiêu mới vẫn đòi công tắc bật."""
        root, owner = _ctx(brain)
        if root is None:
            return None, None, _err(404, "Không tìm thấy brain", "Brain not found")
        return root, owner, None

    @app.get("/goals/{goal_id}")
    async def goal_get(goal_id: str, brain: str = "brain"):
        root, owner, err = _manage(brain)
        if err:
            return err
        view = R.goal_view(deps.store(), owner, goal_id, root)
        if view is None:
            return _err(404, "Không có mục tiêu này trong brain", "No such goal in this brain")
        return {"ok": True, "goal": view}

    @app.post("/goals/{goal_id}/feedback")
    async def goal_feedback(goal_id: str, request: Request, brain: str = "brain"):
        root, owner, err = _manage(brain)
        if err:
            return err
        if not _store_exists():
            return _off("unassigned")
        body = await _body(request)
        store = deps.store()
        g0 = store.get(owner, goal_id)
        if g0 is None:
            return _err(404, "Không có mục tiêu này trong brain", "No such goal in this brain")
        # Phản hồi đi vào việc chạy tiếp của mục tiêu: đòi trợ lý sở hữu đang bật, như công tắc brain trước A1.
        why = R.agent_gate(store, root, g0.agent_key)[1]
        if why:
            return _off(why)
        try:
            res = R.apply_feedback(store, owner, goal_id, str(body.get("kind") or ""), body, root)
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
        root, owner, err = _manage(brain)
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
        root, _owner, err = _manage(brain)
        if err:
            return err
        if not _store_exists():
            return _off("unassigned")
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
        # A1: tin phải thuộc phiên của một trợ lý, và mã GHIM của phiên (cùng hàm với run_turn) đang bật. Không phân
        # giải tin cũ theo slug hiện tại: phiên của trợ lý đã xoá không nhận mã của trợ lý mới cùng tên.
        ch = str(sess.get("channel") or "")
        if not ch.startswith("agent:") or len(ch) <= len("agent:"):
            return _off("unassigned")
        store = deps.store()
        ag = store.session_agent(root, sid, ch[len("agent:"):], sess.get("created_at") or 0)
        if ag is None:
            return _off("needs_new_session")
        why = R.agent_gate(store, root, ag["agent_key"])[1]
        if why:
            return _off(why)
        import nghe_sua
        text = nghe_sua.split_ui_context(str(msg.get("content") or ""))[1]
        p = RS.Principal("agent", ag["agent_key"], root)
        gdeps = R.GoalDeps(engine_factory=deps.engine_factory, budget=R.CallBudget(1), store=store)
        try:
            g = await R.form_goal(mref, {"principal": p, "brain_root": root, "session_id": sid, "message_id": mid,
                                        "user_text": text, "constraints": [], "agent_key": ag["agent_key"],
                                        "agent_version": ag["config_version"]}, gdeps)
        except R.GoalRejected as e:
            return _err(400, f"Chưa lập được mục tiêu: {e}", f"Could not set the goal: {e}")
        except RS.AgentStateError as e:
            return _off(str(e))
        if g.agent_key != ag["agent_key"]:
            return _err(409, "Tin này đã gắn với mục tiêu của trợ lý khác", "This message already belongs to another goal")
        return {"ok": True, "goal": R.goal_view(store, RS.Principal("owner", "owner", root), g.id, root)}


def register_agents(app, deps: ResonanceApiDeps):
    """Route A1 (trợ lý, công tắc theo trợ lý, gán mục tiêu). Đăng ký SAU route cuối của main.py để bảng route cũ
    giữ nguyên thứ tự (tests/python/route_table.json)."""
    def _ctx(brain: str):
        root = deps.brain_key(brain or "")
        if not root or not Path(root).is_dir():
            return None, None
        return root, RS.Principal("owner", "owner", root)

    def _manage(brain: str):
        root, owner = _ctx(brain)
        if root is None:
            return None, None, _err(404, "Không tìm thấy brain", "Brain not found")
        return root, owner, None

    # ───────────── A1: trợ lý và công tắc Cộng hưởng ─────────────

    def _agent_row(store, root: str, meta: dict) -> dict:
        reg = store.agent(root, meta["slug"])
        support = R.engine_support(meta.get("provider") or "")
        return {"slug": meta["slug"], "name": meta.get("name") or meta["slug"], "support": support,
                "registered": reg is not None, "agent_key": (reg or {}).get("agent_key"),
                "enabled": bool((reg or {}).get("enabled")), "status": (reg or {}).get("status") or "unregistered",
                "config_version": (reg or {}).get("config_version"),
                "goals_open": len(store.list_open(RS.Principal("owner", "owner", root), agent_key=reg["agent_key"]))
                if reg else 0}

    @app.get("/resonance/agents")
    async def resonance_agents(brain: str = "brain", slug: str = "", session_id: str = ""):
        """Trợ lý của brain kèm trạng thái Cộng hưởng. Đọc không tạo kho: chưa có kho thì mọi trợ lý đều chưa đăng ký.

        Có `slug` và `session_id` (phiên đang mở ở trang Cộng sự) thì trả thêm `session`: ready, needs_new_session
        hay not_this_agent, hỏi host theo đúng luật của run_turn mà KHÔNG ghi liên kết (review A1 tích hợp, P2). Giao
        diện đọc trạng thái này mỗi lần mở trang, mở phiên hay tải lại, không dựa vào phản hồi của lần bật."""
        root, owner = _ctx(brain)
        if root is None:
            return _err(404, "Không tìm thấy brain", "Brain not found")
        metas = deps.agents_meta(root) or []
        if not _store_exists():
            return {"ok": True, "agents": [{"slug": m["slug"], "name": m.get("name") or m["slug"],
                                            "support": R.engine_support(m.get("provider") or ""), "registered": False,
                                            "agent_key": None, "enabled": False, "status": "unregistered",
                                            "config_version": None, "goals_open": 0} for m in metas],
                    "orphans": [], "unassigned": 0, "legacy_brain_switch": R.enabled_for(root),
                    "session": "needs_new_session" if slug and session_id else None}
        store = deps.store()
        have = {m["slug"] for m in metas}
        # Mã còn `active` mà file đã mất: chốt `missing` ngay khi host thấy (review A1 tích hợp, P1-2), như cổng chung.
        for a in store.agents(root):
            if a["status"] == "active" and a["slug"] not in have:
                store.agent_mark_missing(root, a["agent_key"])
        rows = [_agent_row(store, root, m) for m in metas]
        # Mã còn sống mà file không còn (xoá tay, đổi tên tay): hiện riêng để chủ dự án thấy, kèm mục tiêu đang kẹt.
        orphans = [{"slug": a["slug"], "agent_key": a["agent_key"], "status": a["status"], "enabled": a["enabled"],
                    "goals_open": len(store.list_open(owner, agent_key=a["agent_key"]))}
                   for a in store.agents(root) if a["slug"] not in have]
        return {"ok": True, "agents": rows, "orphans": orphans,
                "unassigned": len(store.list_open(owner, unassigned=True)), "legacy_brain_switch": R.enabled_for(root),
                "session": _session_state(store, root, slug, session_id, pin=False) if slug and session_id else None}

    def _session_state(store, root: str, slug: str, session_id: str, pin: bool = True) -> Optional[str]:
        """Phiên đang mở dùng được mã hiện tại của trợ lý không (review A1 vòng 2, P2). Cùng hàm phân giải với
        run_turn (`session_agent`), nên câu trả lời đúng với lượt kế tiếp. Không tự chuyển phiên cũ sang mã mới."""
        if not session_id:
            return None
        ss = deps.session_store()
        row = ss.get_session(session_id) or {}
        if not row or deps.brain_key(row.get("brain") or "") != root or row.get("channel") != f"agent:{slug}":
            return "not_this_agent"
        live = store.agent(root, slug)
        got = store.session_agent(root, session_id, slug, row.get("created_at") or 0, pin=pin)
        return "ready" if got is not None and live is not None and got["agent_key"] == live["agent_key"] \
            else "needs_new_session"

    @app.post("/resonance/agents/toggle")
    async def resonance_agent_toggle(request: Request, brain: str = "brain"):
        """Chủ dự án bật hay tắt Cộng hưởng cho MỘT trợ lý. Không tool nào gọi được route này (chỉ qua lớp auth/CSRF
        của dashboard). Bật đòi file trợ lý có thật; lần bật đầu cấp mã. Có `session_id` của phiên đang mở thì trả
        `session`: ready, hay needs_new_session khi phiên đó không dùng được mã hiện tại (mở phiên mới qua host)."""
        root, owner = _ctx(brain)
        if root is None:
            return _err(404, "Không tìm thấy brain", "Brain not found")
        body = await _body(request)
        slug = str(body.get("slug") or "").strip()
        on = str(body.get("enabled", "")).strip().lower() in ("1", "true", "on", "yes")
        if not slug:
            return _err(400, "Thiếu trợ lý", "Missing assistant")
        if on and deps.agent_file(root, slug) is None:
            store = deps.store() if _store_exists() else None
            live = store.agent(root, slug) if store else None
            if live is not None and live["status"] == "active":
                store.agent_mark_missing(root, live["agent_key"])
            return _err(404, "Không có file trợ lý này trong brain", "No such assistant file in this brain")
        if not on and not _store_exists():
            return {"ok": True, "agent": None, "session": None}
        store = deps.store()
        try:
            a = store.agent_set_enabled(owner, slug, on)
        except RS.AgentStateError as e:
            return _err(409, f"Trợ lý cần chủ dự án xác nhận trước: {e}", f"The assistant needs confirmation first: {e}",
                        agent=store.agent(root, slug))
        if on and a is not None:
            store.wake_agent_goals(root, a["agent_key"])
        return {"ok": True, "agent": a,
                "session": _session_state(store, root, slug, str(body.get("session_id") or "")) if on else None}

    @app.post("/resonance/agents/confirm")
    async def resonance_agent_confirm(request: Request, brain: str = "brain"):
        """Trợ lý `missing` có file trở lại: `same=true` giữ mã (đúng trợ lý cũ), `same=false` cấp mã mới ở trạng thái
        tắt (mục tiêu và phiên cũ ở lại với mã cũ). Đòi file có thật."""
        root, owner = _ctx(brain)
        if root is None:
            return _err(404, "Không tìm thấy brain", "Brain not found")
        if not _store_exists():
            return _err(404, "Chưa có trợ lý nào đăng ký", "No registered assistant")
        body = await _body(request)
        store = deps.store()
        cur = store.agent_by_key(root, str(body.get("agent_key") or ""))
        if cur is None:
            return _err(404, "Không có trợ lý này trong brain", "No such assistant in this brain")
        if deps.agent_file(root, cur["slug"]) is None:
            return _err(409, "File trợ lý chưa có lại trong brain", "The assistant file is not back in this brain")
        same = str(body.get("same", "")).strip().lower() in ("1", "true", "on", "yes")
        try:
            a = store.agent_confirm(owner, cur["agent_key"], same)
        except RS.AgentStateError as e:
            return _err(409, str(e), str(e), agent=cur)
        if same and a["enabled"]:
            store.wake_agent_goals(root, a["agent_key"], "chủ dự án xác nhận trợ lý")
        return {"ok": True, "agent": a}

    @app.post("/goals/{goal_id}/assign")
    async def goal_assign(goal_id: str, request: Request, brain: str = "brain"):
        """Gán MỘT LẦN một mục tiêu chưa gán cho một trợ lý đang hoạt động cùng brain. CAS bằng expected_revision."""
        root, owner, err = _manage(brain)
        if err:
            return err
        body = await _body(request)
        try:
            exp = int(body.get("expected_revision"))
        except (TypeError, ValueError):
            return _err(400, "Cần expected_revision", "expected_revision is required")
        store = deps.store()
        try:
            store.assign_goal(owner, goal_id, str(body.get("agent_key") or ""), exp)
        except RS.ScopeError:
            return _err(404, "Không có mục tiêu này trong brain", "No such goal in this brain")
        except RS.ConflictError as e:
            return _err(409, f"Mục tiêu đã đổi: {e}", f"The goal changed: {e}",
                        goal=R.goal_view(store, owner, goal_id, root))
        except RS.AgentStateError as e:
            return _err(400, str(e), str(e))
        return {"ok": True, "goal": R.goal_view(store, owner, goal_id, root)}
