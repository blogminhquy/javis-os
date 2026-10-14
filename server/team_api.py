"""Route của nhóm chat team (T1) cho dashboard. Spec: docs/superpowers/specs/2026-10-13-team-chat-design.md mục 15.1.

Dashboard có một tài khoản đăng nhập duy nhất; middleware auth và CSRF của main.py chặn trước khi tới đây, nên request
tới được route này là của chủ nhóm (owner). Mọi route kiểm nhóm thuộc đúng brain đang mở: id nhóm của brain khác coi
như không có (404).

Gửi tin đi bằng `POST /teams/{id}/messages` (phán quyết R2 của kế hoạch T1); câu trả lời, trạng thái hàng đợi đẩy về
qua WebSocket chung bằng gói `team_message` / `team_state`. Lượt trả lời và bộ điều phối chạy NỀN (`deps.spawn`), route
trả ngay.

Kho `team.sqlite3` mở lười: chưa ai dùng nhóm thì không có file, vòng điều phối và phục hồi sau restart thoát ngay.
"""
from __future__ import annotations

import asyncio
import contextlib
import sys
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

from fastapi import Request
from fastapi.responses import JSONResponse

import localefmt
import resonance_store as RS
import task_store
import team_store
from team_runner import TeamRunner, run_io
from team_store import TeamError

LOOP_EVERY_S = 5.0          # nhịp điều phối (spec 8.3: cùng nhịp 5 giây của Kanban)
REMIND_EVERY_S = 3600.0     # nhịp nhắc việc bị chặn quá 24 giờ


@dataclass
class TeamApiDeps:
    brain_key: Callable[[str], str]                    # tên brain trên dashboard -> đường dẫn đã resolve
    session_store: Callable[[], Any]                   # () -> SessionStore
    task_store: Callable[[], Any]                      # () -> TaskStore của Kanban (kanban.sqlite3)
    resonance_store: Callable[[], Any]                 # () -> GoalStore (sổ danh tính agent)
    agents_meta: Callable[[str], list]                 # root -> [{slug, name, ...}]
    agent_info: Callable[[str, str], Optional[dict]]   # (root, agent_key) -> {slug, name, system} | None
    engine_for: Callable[[dict, str, str], tuple]      # (team, agent_key, role) -> (engine, model, async fn)
    broadcast: Optional[Callable[[dict], Any]] = None  # gói WS tới mọi tab (async)
    notify: Optional[Callable[[str, str], Any]] = None  # (session_id nhóm, chữ) -> hộp thư (async)
    spawn: Callable[[Any], Any] = field(default=asyncio.ensure_future)
    store_path: Optional[Path] = None                  # mặc định STATE_DIR/team.sqlite3
    admin: Any = None                                  # thao tác host cho lệnh quản trị Toàn quyền (T3)
    owner_name: Optional[Callable[[], str]] = None     # tên đăng nhập của chủ máy (người tạo nhóm, 0.142.0)


async def _body(request: Request) -> dict:
    try:
        data = await request.json()
        return data if isinstance(data, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


def _err(code: int, vi: str, en: str, **extra) -> JSONResponse:
    return JSONResponse({"ok": False, "error": localefmt.chu(vi, en), **extra}, status_code=code)


def _team_err(ex: Exception, code: int = 400) -> JSONResponse:
    return JSONResponse({"ok": False, "error": str(ex)}, status_code=code)


class TeamApi:
    def __init__(self, deps: TeamApiDeps):
        self.deps = deps
        self._teams = None
        self._runner = None
        self._loop_task = None
        self._loop = None
        self._loop_thread = None
        self._init_lock = threading.RLock()
        self._bg: set = set()

    def path(self) -> Path:
        if self.deps.store_path:
            return Path(self.deps.store_path)
        import config as cfgmod
        return Path(cfgmod.STATE_DIR) / "team.sqlite3"

    def exists(self) -> bool:
        return self._teams is not None or self.path().is_file()

    def teams(self) -> team_store.TeamStore:
        # Tạo lười từ nhiều luồng phụ (route chạy qua run_io): khoá để không ra hai kho, hai bộ chạy, hai accept_lock.
        with self._init_lock:
            if self._teams is None:
                self._teams = team_store.TeamStore(self.path())
        return self._teams

    def _spawn(self, value: Any) -> None:
        if asyncio.iscoroutine(value):
            try:
                task = self.deps.spawn(value)
            except Exception as ex:  # noqa: BLE001
                value.close()
                print(f"[team] không tạo được việc nền: {type(ex).__name__}: {ex}", file=sys.stderr)
                return
            # Giữ tham chiếu tới khi xong: event loop chỉ giữ tham chiếu yếu, việc nền không ai giữ có thể bị dọn rác
            # giữa chừng (lượt trả lời, gói WS, tin hộp thư).
            if isinstance(task, asyncio.Future):
                self._bg.add(task)
                task.add_done_callback(self._bg.discard)

    def runner(self) -> TeamRunner:
        with self._init_lock:
            return self._make_runner()

    def _make_runner(self) -> TeamRunner:
        if self._runner is None:
            def publish(ev: dict) -> None:
                if self.deps.broadcast is not None:
                    self._spawn(self.deps.broadcast(ev))

            def notify(team_id: str, text: str) -> None:
                if self.deps.notify is None:
                    return

                async def go():
                    team = await asyncio.to_thread(self.teams().get, team_id)
                    if team:
                        res = self.deps.notify(team["session_id"], text)
                        if asyncio.iscoroutine(res):
                            await res
                self._spawn(go())

            self._runner = TeamRunner(
                teams=self.teams(), tasks=self.deps.task_store(), sessions=self.deps.session_store(),
                engine_for=lambda team, key, role: self.deps.engine_for(team, key, role),
                agent_info=lambda root, key: self.deps.agent_info(root, key),
                publish=publish, notify=notify, worker_id="team-runner", admin=self.deps.admin)
            if self._loop is not None:
                self._runner._loop, self._runner._loop_thread = self._loop, self._loop_thread
        return self._runner

    def kick(self) -> None:
        """Đánh thức bộ điều phối ngay (không đợi nhịp 5 giây). Gọi được từ luồng phụ."""
        r = self.runner()
        r._on_loop(lambda: self._spawn(r.dispatch_once(wait=False)))

    def guard(self):
        """Khoá chấp nhận đầu ra của bộ chạy (R3) cho thao tác làm đầu ra nhóm hết hợp lệ từ ngoài (xoá agent). Chưa có
        kho nhóm thì không có lượt nhóm nào: không khoá gì."""
        return self.runner().accept_lock if self.exists() else contextlib.nullcontext()

    async def io(self, fn: Callable, *args, **kwargs) -> Any:
        """Phần thân của route ghi chạy ở luồng phụ (R5), cùng cách chờ khi bị huỷ như bộ chạy."""
        self._loop, self._loop_thread = asyncio.get_running_loop(), threading.get_ident()
        if self._runner is not None:
            self._runner._bind_loop()
        return await run_io(fn, *args, **kwargs)

    # ───────────── khung nhìn ─────────────

    def _identity(self, team: dict, m: dict, reg: dict, by_slug: dict) -> dict:
        """Nhân dạng {slug, name, avatar} của một thành viên, GIỮ THEO agent_key (review 4f6268bd #1).

        File trợ lý hiện tại chỉ được dùng khi xác nhận nó thuộc đúng mã này: dòng danh tính của mã còn `active` (mã đã
        nghỉ vì trợ lý bị xoá, hay `missing` chờ chủ xác nhận, thì file cùng slug có thể là trợ lý KHÁC). Khi xác nhận
        được thì chụp lại nhân dạng vào kho nhóm. Không xác nhận được thì dùng ảnh chụp gần nhất của chính mã đó; chưa
        từng chụp (bản ghi cũ) thì dự phòng theo chính mã: tên theo slug lúc vào nhóm, ảnh suy từ mã (`avatar_seed`),
        không bao giờ lấy tên hay ảnh của trợ lý mới cùng slug."""
        slug = reg.get("slug") or m["slug_at_join"]
        info = by_slug.get(slug) if reg.get("status") == "active" else None
        if info:
            ident = {"slug": slug, "name": info.get("name") or slug, "avatar": info.get("avatar")}
            if m.get("identity") != ident:
                self.teams().set_identity(team["team_id"], m["agent_key"], ident)
            return ident
        if m.get("identity"):
            return dict(m["identity"])
        return {"slug": slug, "name": m["slug_at_join"] or slug, "avatar": None, "avatar_seed": m["agent_key"]}

    def member_views(self, team: dict, meta: Optional[list] = None) -> list:
        """Thành viên đang hoạt động của nhóm kèm tên và ảnh đại diện ĐÚNG ảnh trợ lý đang dùng (`avatar` của file trợ lý;
        trợ lý chưa chọn ảnh thì dashboard tự suy từ slug như trang Cộng sự). Nhân dạng giữ theo agent_key (`_identity`)."""
        root = team["brain_id"]
        meta = self.deps.agents_meta(root) if meta is None else meta
        by_slug = {m["slug"]: m for m in (meta or [])}
        rs = self.deps.resonance_store()
        out = []
        for m in self.teams().members(team["team_id"]):
            reg = rs.agent_by_key(root, m["agent_key"]) or {}
            ident = self._identity(team, m, reg, by_slug)
            out.append(dict(ident, agent_key=m["agent_key"], title=str((by_slug.get(ident.get("slug")) or {}).get("title") or "")
                            if reg.get("status") == "active" else "",
                            role=m["role"], status=m["status"], agent_status=reg.get("status") or "",
                            resonance_enabled=bool(reg.get("enabled")), joined_at=m["joined_at"],
                            managed=bool(m.get("managed_by_team"))))
        return out

    def authors(self, team: dict, meta: Optional[list] = None) -> dict:
        """Sổ tác giả {agent_key: {slug, name, avatar}} của MỌI trợ lý từng ở nhóm, kể cả đã rời: tin cũ giữ đúng tên và
        ảnh của người viết (review b93c46bd #2), theo agent_key chứ không theo slug (review 4f6268bd #1). Ảnh nhóm và gợi ý
        @ không dùng sổ này, chỉ dùng thành viên đang hoạt động."""
        root = team["brain_id"]
        meta = self.deps.agents_meta(root) if meta is None else meta
        by_slug = {m["slug"]: m for m in (meta or [])}
        rs = self.deps.resonance_store()
        return {m["agent_key"]: self._identity(team, m, rs.agent_by_key(root, m["agent_key"]) or {}, by_slug)
                for m in self.teams().members(team["team_id"], include_removed=True)}

    def faces(self, team: dict, meta: list) -> dict:
        """Ảnh nhóm ở danh sách: tối đa 4 gương mặt thành viên đang hoạt động (trưởng nhóm trước) và tổng số người."""
        active = [m for m in self.member_views(team, meta) if m["status"] == "active"]
        active.sort(key=lambda m: (m["agent_key"] != team.get("leader_key"), m["joined_at"]))
        return {"faces": [{"slug": m["slug"], "name": m["name"], "avatar": m["avatar"]} for m in active[:4]],
                "member_count": len(active)}

    def counts(self, team_id: str) -> dict:
        q = self.deps.task_store().team_queue(team_id)
        return {"running": len(q["running"]), "waiting": len(q["waiting"]), "blocked": len(q["blocked"])}

    def last_message(self, team: dict) -> Optional[dict]:
        """Tin cuối của nhóm cho dòng xem trước ở danh sách (T5): loại người gửi, tên, 120 ký tự đầu, giờ."""
        page = self.deps.session_store().get_team_messages_page(team["session_id"], limit=1)
        msgs = page.get("messages") or []
        if not msgs:
            return None
        m = msgs[-1]
        author = self.runner()._name(team, m["author_ref"]) if m.get("author_kind") == "agent" and m.get("author_ref") else ""
        return {"author_kind": m.get("author_kind") or "", "author": author,
                "text": " ".join(str(m.get("content") or "").split())[:120], "ts": m.get("ts") or 0}

    def view(self, team: dict) -> dict:
        q = self.deps.task_store().team_queue(team["team_id"])
        meta = self.deps.agents_meta(team["brain_id"]) or []
        return dict(team, members=self.member_views(team, meta), authors=self.authors(team, meta),
                    creator=self.creator(team),
                    counts={"running": len(q["running"]), "waiting": len(q["waiting"]), "blocked": len(q["blocked"])},
                    running=[{"id": t["id"], "title": t["title"]} for t in q["running"]],
                    busy=self.runner().busy_view(team["team_id"]),
                    authority=self.runner().authority_view(team["team_id"]),
                    usage=self.runner().usage(team["team_id"]))

    def creator(self, team: dict) -> dict:
        """Người tạo, quản lý nhóm (0.142.0): người thật, không phải trợ lý. Javis có một tài khoản chủ máy nên mọi nhóm,
        kể cả nhóm tạo trước 0.142.0, thuộc chủ đó; tên lấy từ cấu hình đăng nhập của server, không từ client."""
        name = ""
        if self.deps.owner_name is not None:
            try:
                name = str(self.deps.owner_name() or "")[:80]
            except Exception:  # noqa: BLE001
                name = ""
        return {"kind": str(team.get("created_by") or "owner"), "you": True, "name": name}

    def register_agent(self, root: str, slug: str) -> dict:
        return self.deps.resonance_store().agent_register(RS.Principal("owner", "owner", root), slug)

    # ───────────── nền ─────────────

    def prime(self) -> None:
        """Lúc khởi động: chỉ khi kho nhóm ĐÃ có từ trước mới cần phục hồi. Cài mới (chưa có kho) thì không có gì để phục
        hồi; nếu để phục hồi chạy lúc kho vừa được tạo, nó sẽ chặn nhầm việc đang chạy và hoàn nhầm lượt đang giữ chỗ."""
        self._recovered = not self.exists()
        self._last_remind = 0.0

    async def tick(self) -> None:
        """Một vòng: phục hồi (một lần, nếu cần), nhận việc đầu hàng, mỗi giờ nhắc việc chặn quá 24 giờ."""
        if not hasattr(self, "_recovered"):
            self.prime()
        if not self.exists():
            return
        r = self.runner()
        if not self._recovered:
            self._recovered = True
            await r._io(r.archive_orphans)
            rep = await r._io(r.recover)
            if rep["resumed"]:
                self._spawn(r.resume_jobs(rep["resumed"]))
        await r.dispatch_once(wait=False)
        now = asyncio.get_running_loop().time()
        if now - self._last_remind >= REMIND_EVERY_S:
            self._last_remind = now
            await r._io(r.remind_blocked)

    async def loop(self) -> None:
        """Vòng điều phối mỗi 5 giây (spec 8.3)."""
        while True:
            try:
                await self.tick()
            except asyncio.CancelledError:
                raise
            except Exception as ex:  # noqa: BLE001
                print(f"[team loop] {type(ex).__name__}: {ex}", file=sys.stderr)
            await asyncio.sleep(LOOP_EVERY_S)


def register(app, deps: TeamApiDeps) -> TeamApi:
    """Đăng ký route `/teams/*`. Gọi SAU route cuối của main.py để bảng route cũ giữ nguyên thứ tự."""
    api = TeamApi(deps)

    @app.on_event("startup")
    async def _team_loop_start():
        api.prime()
        api._loop_task = asyncio.create_task(api.loop())

    def _root(brain: str) -> Optional[str]:
        root = deps.brain_key(brain or "")
        return root if root and Path(root).is_dir() else None

    def _team(team_id: str, brain: str):
        root = _root(brain)
        if root is None:
            return None, _err(404, "Không tìm thấy brain", "Brain not found")
        if not api.exists():
            return None, _err(404, "Không có nhóm này", "Team not found")
        team = api.teams().get(team_id)
        if not team or team["brain_id"] != root:
            return None, _err(404, "Không có nhóm này", "Team not found")
        return team, None

    def _slugs(root: str) -> set:
        return {m["slug"] for m in (deps.agents_meta(root) or [])}

    def _own_task(team_id: str, task_id: str) -> Optional[dict]:
        t = deps.task_store().get_task(task_id)
        return t if t and t.get("lane") == "team" and t.get("team_id") == team_id else None

    # Review T1, R5: thân của MỌI route (kể cả bước tìm nhóm, đọc kho phiên, kho việc, kho nhóm, file agent) chạy ở luồng
    # phụ qua `api.io`, event loop chỉ đọc body của request. Gói WS và việc nền do thân route tạo được bộ chạy xếp về
    # loop (call_soon_threadsafe). Thao tác làm đầu ra nhóm hết hợp lệ (bỏ thành viên, đổi trưởng nhóm, sửa yêu cầu,
    # lưu trữ) giữ `accept_lock` của bộ chạy (R3).

    @app.get("/teams")
    async def teams_list(brain: str = "brain", before: Optional[float] = None, limit: int = 50):
        def _do():
            root = _root(brain)
            if root is None:
                return _err(404, "Không tìm thấy brain", "Brain not found")
            if not api.exists():
                return {"ok": True, "teams": [], "next": None}
            meta = deps.agents_meta(root) or []
            rows = [dict(t, counts=api.counts(t["team_id"]), last=api.last_message(t), **api.faces(t, meta))
                    for t in api.teams().list_teams(root, limit=limit, before=before)]
            # Con trỏ trang sau chỉ tính nhóm không ghim (nhóm ghim luôn nằm ở trang đầu).
            plain = [t for t in rows if not t.get("pinned_at")]
            nxt = plain[-1]["updated_at"] if len(plain) >= max(1, min(int(limit), 200)) else None
            return {"ok": True, "teams": rows, "next": nxt}
        return await api.io(_do)

    @app.post("/teams")
    async def teams_create(request: Request, brain: str = "brain"):
        body = await _body(request)

        def _do():
            root = _root(brain)
            if root is None:
                return _err(404, "Không tìm thấy brain", "Brain not found")
            name = str(body.get("name") or "").strip()
            members = [str(s) for s in (body.get("members") or []) if str(s or "").strip()]
            leader = str(body.get("leader_slug") or "").strip()
            if not name:
                return _err(400, "Thiếu tên nhóm", "Team name is required")
            if leader and leader not in members:
                members.append(leader)
            # Nhóm cần ít nhất một trợ lý (0.142.0): người tạo là người thật, không tính là thành viên AI.
            if not members:
                return _err(400, "Chọn ít nhất một trợ lý", "Pick at least one assistant")
            have = _slugs(root)
            missing = [s for s in members if s not in have]
            if missing:
                return _err(400, f"Không có trợ lý: {', '.join(missing)}", f"No such assistant: {', '.join(missing)}")
            teams = api.teams()
            # Bấm Tạo hai lần hay mạng chậm gửi lại cùng mã: trả nhóm đã tạo, không tạo phiên hay nhóm thứ hai.
            req = str(body.get("client_req_id") or "").strip()[:80]
            old = teams.find_by_request(root, req) if req else None
            if old is not None:
                return {"ok": True, "team": api.view(old), "duplicate": True}
            keys = {slug: api.register_agent(root, slug)["agent_key"] for slug in dict.fromkeys(members)}
            tid = team_store.new_team_id()
            sid = deps.session_store().create_session(brain=brain, channel=f"team:{tid}", title=name[:120])
            # Người tạo: luôn là chủ máy đã qua cổng đăng nhập của server (Javis có một tài khoản), không đọc từ client.
            try:
                team = teams.create_team(root, name, str(body.get("description") or ""), sid, team_id=tid,
                                         members=[(keys[s], s) for s in keys], leader_key=keys[leader] if leader else None,
                                         client_req_id=req or None, by="owner")
            except Exception:
                # Không tạo được nhóm (kho bận quá lâu...): phiên vừa mở không gắn nhóm nào thì bỏ, không để mồ côi.
                try:
                    deps.session_store().delete(sid)
                except Exception:  # noqa: BLE001
                    pass
                raise
            if team["team_id"] != tid:
                # Hai yêu cầu cùng mã chạy song song: yêu cầu kia thắng, phiên vừa mở không gắn nhóm nào thì bỏ.
                try:
                    deps.session_store().delete(sid)
                except Exception:  # noqa: BLE001
                    pass
                return {"ok": True, "team": api.view(team), "duplicate": True}
            return {"ok": True, "team": api.view(team)}
        return await api.io(_do)

    @app.get("/teams/{team_id}")
    async def teams_get(team_id: str, brain: str = "brain"):
        def _do():
            team, err = _team(team_id, brain)
            return err or {"ok": True, "team": api.view(team)}
        return await api.io(_do)

    @app.patch("/teams/{team_id}")
    async def teams_patch(team_id: str, request: Request, brain: str = "brain"):
        body = await _body(request)

        def _do():
            team, err = _team(team_id, brain)
            if err:
                return err
            fields = {k: body[k] for k in ("name", "description", "status") if k in body}
            if not fields:
                return {"ok": True, "team": api.view(team)}
            runner = api.runner()
            try:
                with runner.accept_lock:
                    updated = api.teams().update(team_id, **fields)
            except TeamError as ex:
                return _team_err(ex)
            if fields.get("status") == "archived":
                q = deps.task_store().team_queue(team_id)
                for t in q["waiting"] + q["blocked"]:
                    runner.cancel_job(t["id"], "nhóm đã lưu trữ")
                runner.cancel_idle_running(team_id, "nhóm đã lưu trữ")
            elif fields.get("status") == "active" and team["status"] != "active":
                runner._on_loop(lambda: api._spawn(runner.resume_team(team_id)))
                api.kick()
            runner._state(team_id)
            return {"ok": True, "team": api.view(updated)}
        return await api.io(_do)

    @app.post("/teams/{team_id}/members")
    async def teams_member_add(team_id: str, request: Request, brain: str = "brain"):
        slug = str((await _body(request)).get("slug") or "").strip()

        def _do():
            team, err = _team(team_id, brain)
            if err:
                return err
            if slug not in _slugs(team["brain_id"]):
                return _err(400, f"Không có trợ lý: {slug}", f"No such assistant: {slug}")
            reg = api.register_agent(team["brain_id"], slug)
            api.teams().add_member(team_id, reg["agent_key"], slug)
            api.runner()._state(team_id)
            return {"ok": True, "team": api.view(api.teams().get(team_id))}
        return await api.io(_do)

    @app.delete("/teams/{team_id}/members/{agent_key}")
    async def teams_member_remove(team_id: str, agent_key: str, brain: str = "brain"):
        def _do():
            team, err = _team(team_id, brain)
            if err:
                return err
            with api.runner().accept_lock:
                removed = api.teams().remove_member(team_id, agent_key)
            if not removed:
                return _err(404, "Không phải thành viên đang hoạt động", "Not an active member")
            api.runner()._state(team_id)
            return {"ok": True, "team": api.view(api.teams().get(team_id))}
        return await api.io(_do)

    @app.post("/teams/{team_id}/leader")
    async def teams_leader(team_id: str, request: Request, brain: str = "brain"):
        key = (await _body(request)).get("agent_key")

        def _do():
            team, err = _team(team_id, brain)
            if err:
                return err
            try:
                with api.runner().accept_lock:
                    updated = api.teams().set_leader(team_id, str(key) if key else None)
            except TeamError as ex:
                return _team_err(ex)
            if updated["leader_key"]:
                api.runner().resume_no_leader(team_id)
                api.kick()
            api.runner()._state(team_id)
            return {"ok": True, "team": api.view(updated)}
        return await api.io(_do)

    @app.post("/teams/{team_id}/caps")
    async def teams_caps(team_id: str, request: Request, brain: str = "brain"):
        caps = (await _body(request)).get("caps") or {}

        def _do():
            team, err = _team(team_id, brain)
            if err:
                return err
            try:
                updated = api.teams().set_caps(team_id, caps)
            except TeamError as ex:
                return _team_err(ex)
            return {"ok": True, "team": api.view(updated)}
        return await api.io(_do)

    @app.get("/teams/{team_id}/queue")
    async def teams_queue(team_id: str, brain: str = "brain"):
        def _do():
            team, err = _team(team_id, brain)
            if err:
                return err
            return dict(deps.task_store().team_queue(team_id), ok=True, busy=api.runner().busy_view(team_id))
        return await api.io(_do)

    @app.post("/teams/{team_id}/queue/{task_id}/priority")
    async def teams_priority(team_id: str, task_id: str, request: Request, brain: str = "brain"):
        body = await _body(request)

        def _do():
            team, err = _team(team_id, brain)
            if err:
                return err
            if not _own_task(team_id, task_id):
                return _err(404, "Không có việc này trong nhóm", "No such job in this team")
            try:
                q = deps.task_store().team_priority(task_id, bool(body.get("on", True)),
                                                    int(body.get("expected_queue_version") or 0))
            except task_store.QueueConflict as ex:
                return JSONResponse({"ok": False, "code": "queue_changed", "queue": ex.queue,
                                     "error": localefmt.chu("Hàng đợi vừa thay đổi", "The queue just changed")},
                                    status_code=409)
            except task_store.QueueError:
                return _err(409, "Việc này không còn ở hàng chờ", "This job is no longer waiting")
            api.runner()._state(team_id)
            return {"ok": True, "queue": q}
        return await api.io(_do)

    @app.get("/teams/{team_id}/tasks/{task_id}")
    async def teams_task(team_id: str, task_id: str, brain: str = "brain"):
        def _do():
            team, err = _team(team_id, brain)
            if err:
                return err
            task = _own_task(team_id, task_id)
            if not task:
                return _err(404, "Không có việc này trong nhóm", "No such job in this team")
            msgs = deps.session_store().team_messages_of_task(team["session_id"], task_id)
            # Khung lọc theo việc dùng danh sách này: thiếu phản hồi thì bấm emoji ở đây sẽ xoá lý do, góp ý (review T2).
            got = api.teams().reactions_for(team["session_id"], [m["id"] for m in msgs])
            for m in msgs:
                m["reaction"] = got.get(int(m["id"]))
            return {"ok": True, "task": task, "steps": api.teams().steps(task_id), "messages": msgs}
        return await api.io(_do)

    @app.post("/teams/{team_id}/tasks/{task_id}/cancel")
    async def teams_task_cancel(team_id: str, task_id: str, brain: str = "brain"):
        def _do():
            team, err = _team(team_id, brain)
            if err:
                return err
            if not _own_task(team_id, task_id):
                return _err(404, "Không có việc này trong nhóm", "No such job in this team")
            prev = api.runner().cancel_job(task_id)
            if prev is None:
                return _err(409, "Việc đã kết thúc", "The job has already ended")
            api.kick()
            return {"ok": True, "previous": prev}
        return await api.io(_do)

    @app.post("/teams/{team_id}/tasks/{task_id}/amend")
    async def teams_task_amend(team_id: str, task_id: str, request: Request, brain: str = "brain"):
        text = str((await _body(request)).get("text") or "").strip()

        def _do():
            team, err = _team(team_id, brain)
            if err:
                return err
            if not _own_task(team_id, task_id):
                return _err(404, "Không có việc này trong nhóm", "No such job in this team")
            if not text:
                return _err(400, "Thiếu nội dung sửa", "The change is empty")
            with api.runner().accept_lock:
                rev = deps.task_store().team_amend(task_id, text)
            if rev is None:
                return _err(409, "Việc đã kết thúc", "The job has already ended")
            api.runner()._state(team_id)
            return {"ok": True, "revision": rev}
        return await api.io(_do)

    @app.post("/teams/{team_id}/tasks/{task_id}/unblock")
    async def teams_task_unblock(team_id: str, task_id: str, request: Request, brain: str = "brain"):
        action = str((await _body(request)).get("action") or "resume")

        def _do():
            team, err = _team(team_id, brain)
            if err:
                return err
            if not _own_task(team_id, task_id):
                return _err(404, "Không có việc này trong nhóm", "No such job in this team")
            if action not in ("retry", "resume"):
                return _err(400, "Thao tác không hợp lệ", "Invalid action")
            if not api.runner().unblock(task_id, action):
                return _err(409, "Việc không ở trạng thái bị chặn", "The job is not blocked")
            api.kick()
            api.runner()._state(team_id)
            return {"ok": True}
        return await api.io(_do)

    @app.post("/teams/{team_id}/pin")
    async def teams_pin(team_id: str, request: Request, brain: str = "brain"):
        """Ghim (`on: true`) hay bỏ ghim nhóm lên đầu danh sách."""
        on = bool((await _body(request)).get("on"))

        def _do():
            team, err = _team(team_id, brain)
            if err:
                return err
            api.teams().set_pinned(team_id, on)
            return {"ok": True, "pinned": on}
        return await api.io(_do)

    @app.post("/teams/{team_id}/tasks/{task_id}/extend")
    async def teams_task_extend(team_id: str, task_id: str, brain: str = "brain"):
        """Nút "Cho thêm lượt" (T5): nâng đúng giới hạn việc vừa chạm thêm một nấc rồi cho chạy tiếp."""
        def _do():
            team, err = _team(team_id, brain)
            if err:
                return err
            if not _own_task(team_id, task_id):
                return _err(404, "Không có việc này trong nhóm", "No such job in this team")
            out = api.runner().extend_job(task_id)
            if out is None:
                return _err(409, "Việc không bị chặn vì hết lượt", "The job is not blocked by a limit")
            api.kick()
            return dict(out, ok=True)
        return await api.io(_do)

    @app.get("/teams/{team_id}/messages")
    async def teams_messages(team_id: str, brain: str = "brain", before_ts: Optional[float] = None,
                             before_id: Optional[int] = None, limit: int = 30):
        def _do():
            team, err = _team(team_id, brain)
            if err:
                return err
            before = (before_ts, before_id) if before_ts is not None and before_id is not None else None
            page = deps.session_store().get_team_messages_page(team["session_id"], limit, before)
            # Phản hồi của chủ (T2) đi kèm từng tin, đọc một lần cho cả trang.
            ids = [m["id"] for m in page["messages"]]
            got = api.teams().reactions_for(team["session_id"], ids)
            # Kết cục lượt trả lời (0.142.0) đi kèm tin của chủ nhóm: tải lại trang vẫn thấy chờ, đang trả lời, lỗi.
            replies = api.teams().replies_for(team_id, ids)
            # Tên việc của các tin gắn việc (0.142.0): việc đã xong không còn trong hàng đợi, tải lại trang thì nhãn chỉ
            # còn mã việc. Đọc thẳng bản ghi gốc, chỉ việc thuộc đúng nhóm này.
            titles = {}
            for tid in {m.get("task_id") for m in page["messages"] if m.get("task_id")}:
                tk = deps.task_store().get_task(tid)
                if tk and tk.get("team_id") == team_id:
                    titles[tid] = tk.get("title") or ""
            for m in page["messages"]:
                if m.get("task_id") in titles:
                    m["task_title"] = titles[m["task_id"]]
                m["reaction"] = got.get(int(m["id"]))
                if replies.get(int(m["id"])):
                    m["replies"] = replies[int(m["id"])]
            return dict(page, ok=True)
        return await api.io(_do)

    @app.post("/teams/{team_id}/messages/{message_id}/reaction")
    async def teams_reaction(team_id: str, message_id: int, request: Request, brain: str = "brain"):
        """Thả cảm xúc, lý do, góp ý (spec 14). Không mở lượt, không gọi model."""
        body = await _body(request)

        def _do():
            team, err = _team(team_id, brain)
            if err:
                return err
            reasons = body.get("reasons")
            if reasons is not None and not isinstance(reasons, list):
                return _err(400, "Lý do phải là danh sách", "Reasons must be a list")
            try:
                state = api.runner().react(team_id, message_id, body.get("value"), reasons=reasons,
                                           comment=str(body.get("comment") or ""), nonce=str(body.get("nonce") or ""))
            except TeamError as ex:
                return _team_err(ex)
            return {"ok": True, "reaction": state}
        return await api.io(_do)

    @app.post("/teams/{team_id}/messages")
    async def teams_send(team_id: str, request: Request, brain: str = "brain"):
        body = await _body(request)

        def _do():
            team, err = _team(team_id, brain)
            if err:
                return err
            if team["status"] == "archived":
                return _err(409, "Nhóm đã lưu trữ, không gửi tin được", "The team is archived")
            runner = api.runner()
            try:
                sub = runner.submit(team_id, str(body.get("text") or ""), mentions=list(body.get("mentions") or []),
                                    as_job=bool(body.get("as_job")),
                                    client_msg_id=str(body.get("client_msg_id") or ""))
            except TeamError as ex:
                return _team_err(ex)
            if sub["replies"]:
                runner._on_loop(lambda: api._spawn(runner.run_replies(sub)))
            if sub.get("task_id") and sub["created"]:
                api.kick()
            return dict(sub, ok=True)
        return await api.io(_do)

    @app.post("/teams/{team_id}/messages/{message_id}/replies/{agent_key}/retry")
    async def teams_reply_retry(team_id: str, message_id: int, agent_key: str, brain: str = "brain"):
        """Thử lại một lượt trả lời bị lỗi (0.142.0). Bấm lặp hay bấm khi lượt đã xong thì trả trạng thái hiện tại, không
        chạy thêm lượt nào."""
        def _do():
            team, err = _team(team_id, brain)
            if err:
                return err
            runner = api.runner()
            try:
                sub = runner.retry_reply(team_id, message_id, agent_key)
            except TeamError as ex:
                return _team_err(ex, 409)
            if sub is not None:
                runner._on_loop(lambda: api._spawn(runner.run_replies(sub)))
            return {"ok": True, "retried": sub is not None, "replies": api.teams().replies_of(team_id, message_id)}
        return await api.io(_do)

    @app.post("/teams/{team_id}/messages/{message_id}/accept")
    async def teams_accept(team_id: str, message_id: int, brain: str = "brain"):
        def _do():
            team, err = _team(team_id, brain)
            if err:
                return err
            if team["status"] == "archived":
                return _err(409, "Nhóm đã lưu trữ, không tạo việc mới được", "The team is archived")
            try:
                tid = api.runner().accept_proposal(team_id, message_id)
            except TeamError as ex:
                return _team_err(ex)
            api.kick()
            return {"ok": True, "task_id": tid}
        return await api.io(_do)

    @app.post("/teams/{team_id}/messages/{message_id}/decision")
    async def teams_decision(team_id: str, message_id: int, request: Request, brain: str = "brain"):
        on = bool((await _body(request)).get("on", True))

        def _do():
            team, err = _team(team_id, brain)
            if err:
                return err
            ss = deps.session_store()
            if not ss.update_team_message_meta(team["session_id"], message_id, {"decision": on}):
                return _err(404, "Không có tin này trong nhóm", "No such message in this team")
            api.runner()._publish({"type": "team_message", "team_id": team_id,
                                   "message": ss.team_message(team["session_id"], message_id)})
            return {"ok": True}
        return await api.io(_do)

    @app.get("/teams/{team_id}/turns")
    async def teams_turns(team_id: str, brain: str = "brain", since: float = 0, limit: int = 500):
        def _do():
            team, err = _team(team_id, brain)
            if err:
                return err
            return {"ok": True, "turns": api.teams().turns(team_id, since, max(1, min(int(limit), 2000)))}
        return await api.io(_do)

    # ───────────── Toàn quyền (T3, spec 13, 15.1) ─────────────

    @app.post("/teams/{team_id}/authority")
    async def teams_authority(team_id: str, request: Request, brain: str = "brain"):
        """Chủ bật, sửa hay thu hồi Toàn quyền cho trưởng nhóm `{mode: "full"|"limited", grant}`. Route của dashboard
        (auth, CSRF); không lệnh JAVIS_TEAM nào gọi tới đây, nên trưởng nhóm không tự nâng mình lên Toàn quyền."""
        body = await _body(request)

        def _do():
            team, err = _team(team_id, brain)
            if err:
                return err
            mode = str(body.get("mode") or "")
            runner = api.runner()
            try:
                if mode == "full":
                    grant = body.get("grant")
                    if not isinstance(grant, dict):
                        return _err(400, "Thiếu hộp cấp quyền", "Missing grant")
                    runner.grant_authority(team_id, grant, by="owner")
                elif mode == "limited":
                    runner.revoke_authority(team_id, by="owner", reason=str(body.get("reason") or "chủ thu hồi")[:200])
                else:
                    return _err(400, "Chế độ không hợp lệ", "Invalid mode")
            except TeamError as ex:
                return _team_err(ex)
            return {"ok": True, "team": api.view(api.teams().get(team_id))}
        return await api.io(_do)

    @app.post("/teams/{team_id}/members/{agent_key}/managed")
    async def teams_member_managed(team_id: str, agent_key: str, request: Request, brain: str = "brain"):
        """Chủ đánh dấu (hay bỏ) "giao cho nhóm này quản lý" (spec 13.3). Mỗi agent tối đa một nhóm quản lý: 409."""
        on = bool((await _body(request)).get("on", True))

        def _do():
            team, err = _team(team_id, brain)
            if err:
                return err
            try:
                api.runner().set_managed(team_id, agent_key, on, by="owner")
            except TeamError as ex:
                return _team_err(ex, 409)
            return {"ok": True, "team": api.view(api.teams().get(team_id))}
        return await api.io(_do)

    # ───────────── Lịch sử dài (T4, spec 19) ─────────────

    @app.get("/teams/{team_id}/search")
    async def teams_search(team_id: str, q: str = "", limit: int = 50, brain: str = "brain"):
        """Tìm tin trong CHÍNH nhóm này: không phân biệt hoa thường và dấu, mới nhất trước, có đoạn trích."""
        def _do():
            team, err = _team(team_id, brain)
            if err:
                return err
            try:
                results = api.runner().search(team_id, q, max(1, min(int(limit), 200)))
            except TeamError as ex:
                return _team_err(ex)
            return {"ok": True, "results": results}
        return await api.io(_do)

    return api
