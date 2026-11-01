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

import avatar_upload
import localefmt
import resonance_store as RS
import task_store
import team_store
from team_runner import TeamRunner, run_io
from team_store import TeamError

LOOP_EVERY_S = 5.0          # nhịp điều phối (spec 8.3: cùng nhịp 5 giây của Kanban)
REMIND_EVERY_S = 3600.0     # nhịp nhắc việc bị chặn quá 24 giờ
RECONCILE_EVERY_S = 60.0    # nhịp đối soát sổ lượt chung với team_turns (T2, thiết kế 9.1)
FINISHED_SHOWN = 30          # việc đã xong hiện ở tab Việc của nhóm (0.193.0)
PINNED_SHOWN = 20            # tin đã ghim hiện ở dải trên khung chat (0.192.0), như Sổ quyết định của lượt
DESCRIBE_TIMEOUT_S = 120.0   # tả ảnh đính kèm trước lượt thành viên (0.192.0): quá thì lượt vẫn chạy, không có mô tả


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
    ceiling: Optional[Callable[[], Any]] = None        # () -> agent_ledger.TeamCeiling (T2, trần lượt chung) | None
    projector: Optional[Callable[[], Any]] = None      # () -> feedback_projector.FeedbackProjector (T2) | None
    judge: Optional[Callable[[], Any]] = None          # () -> agent_judge.Judge (T3 phần J) | None
    learning: Optional[Callable[[], Any]] = None       # () -> agent_lessons.TeamLearning (T3 phần L) | None
    contrib_reader: Optional[Callable[[str], list]] = None  # result_ref -> pulse_contrib còn hiệu lực (T4, lịch sử dài)
    attach: Optional[Callable[[dict, list], list]] = None  # (team, attachments) -> [{name, path, image}] (0.191.0)
    docs_block: Optional[Callable[[dict], str]] = None    # team -> documents/folder block of member turns (0.191.0)
    # (team, files, caption) -> awaitable: pictures among `files` get a pinned text description, read by member turns
    # (team turns are text only). Awaited BEFORE the member turns of the message that carried them (0.192.0).
    describe: Optional[Callable[[dict, list, str], Any]] = None
    # 0.208.0: what the department mandate needs from the host (team_mandate.MandateEngine deps): brain_root,
    # kanban_failures, mcp_status, run_test, open_job. None: mandates can be written but are never observed.
    mandate_deps: Optional[Callable[[], Any]] = None
    # 0.209.0: runs a `command_ok` acceptance criterion: (command, cwd) -> {ran, exit, output, error}. None: unknown.
    check_command: Optional[Callable[[str, Any], dict]] = None
    brain_root: Optional[Callable[[dict], Any]] = None   # team -> Path of its brain (acceptance product paths)
    work_dir: Optional[Callable[[dict], str]] = None     # team -> pinned working folder, "" when none (0.260.0)
    # 0.357.0: report a job Javis Core gave the team back where it was asked (main._notify_owner):
    # (owner_chat, text, *, kind, label, source, ngan, brain, dedup) -> (ok, error), sync or async. None: no reports.
    report: Optional[Callable[..., Any]] = None


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
            # Issue #798: route bodies run in a worker thread (`io` -> run_io), where `ensure_future` has no event loop,
            # so a recheck scheduled there never ran and the job stayed in acceptance_checking. Hand it to the main loop.
            loop = self._loop
            if loop is not None and threading.get_ident() != self._loop_thread and not loop.is_closed():
                try:
                    loop.call_soon_threadsafe(self._spawn, value)
                    return
                except RuntimeError:   # the loop closed in between: fall through and report below
                    pass
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
                    # 0.197.0: a muted team never reaches the owner's inbox or devices ("team nào bị tắt thông báo thì dù
                    # có tag tên cũng không báo về máy").
                    if team and not team.get("muted"):
                        res = self.deps.notify(team["session_id"], text)
                        if asyncio.iscoroutine(res):
                            await res
                self._spawn(go())

            self._runner = TeamRunner(
                teams=self.teams(), tasks=self.deps.task_store(), sessions=self.deps.session_store(),
                engine_for=lambda team, key, role: self.deps.engine_for(team, key, role),
                agent_info=lambda root, key: self.deps.agent_info(root, key),
                publish=publish, notify=notify, worker_id="team-runner", admin=self.deps.admin,
                ceiling=self.deps.ceiling() if self.deps.ceiling is not None else None,
                projector=self.deps.projector() if self.deps.projector is not None else None,
                judge=self.deps.judge() if self.deps.judge is not None else None,
                learning=self.deps.learning() if self.deps.learning is not None else None,
                contrib_reader=self.deps.contrib_reader, docs_block=self.deps.docs_block,
                check_command=self.deps.check_command, brain_root=self.deps.brain_root,
                work_dir=self.deps.work_dir)
            if self._loop is not None:
                self._runner._loop, self._runner._loop_thread = self._loop, self._loop_thread
        return self._runner

    def mandates(self):
        """0.208.0: the department mandate store, in the team store's file."""
        if getattr(self, "_mandates", None) is None:
            import team_mandate
            self._mandates = team_mandate.MandateStore(self.teams().path)
        return self._mandates

    def mandate_engine(self):
        if self.deps.mandate_deps is None:
            return None
        if getattr(self, "_mandate_engine", None) is None:
            import team_mandate
            self._mandate_engine = team_mandate.MandateEngine(self.mandates(), self.runner(), self.deps.mandate_deps())
        return self._mandate_engine

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

    def unread(self, team: dict) -> dict:
        """0.197.0: messages from assistants and the system since the owner last read the team (`n`, at most 99), and how
        many of them call the owner (`at`), for the badge and the @ mark on the team list."""
        return self.deps.session_store().team_unread(team["session_id"], team.get("read_at") or 0)

    def view(self, team: dict) -> dict:
        q = self.deps.task_store().team_queue(team["team_id"])
        meta = self.deps.agents_meta(team["brain_id"]) or []
        return dict(team, members=self.member_views(team, meta), authors=self.authors(team, meta),
                    creator=self.creator(team),
                    counts={"running": len(q["running"]), "waiting": len(q["waiting"]), "blocked": len(q["blocked"])},
                    running=[{"id": t["id"], "title": t["title"]} for t in q["running"]],
                    busy=self.runner().busy_view(team["team_id"]),
                    authority=self.runner().authority_view(team["team_id"]),
                    usage=self.runner().usage(team["team_id"]),
                    quality_policy=self.runner().quality.policy(team["team_id"]),
                    acceptance_template=self.runner().quality.template(team["team_id"]),
                    mandate=self.mandate_summary(team["team_id"]))

    def mandate_summary(self, team_id: str) -> Optional[dict]:
        """0.208.0: the team's mandate for the Team tab (None = no mandate), with each source's last state."""
        import team_mandate
        st = self.mandates()
        m = st.get(team_id)
        if not m:
            return None
        return dict(m, sources_state=team_mandate.sources_view(st, m), observing=self.deps.mandate_deps is not None)

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
        self._last_reconcile = 0.0

    async def tick(self) -> None:
        """Một vòng: phục hồi (một lần, nếu cần), nhận việc đầu hàng, mỗi giờ nhắc việc chặn quá 24 giờ."""
        if not hasattr(self, "_recovered"):
            self.prime()
        if not self.exists():
            await self._judge_tick_without_teams()
            return
        r = self.runner()
        if not self._recovered:
            self._recovered = True
            await r._io(r.archive_orphans)
            rep = await r._io(r.recover)
            if rep["resumed"]:
                self._spawn(r.resume_jobs(rep["resumed"]))
            for tid in rep.get("rechecks") or []:
                self._spawn(r.recheck(tid))
        # 0.207.0: approval requests past their deadline close before dispatch, so their jobs stay stopped with the reason.
        await r._io(r.expire_approvals)
        # 0.208.0: department mandates observe their granted sources when due (code only, no model).
        # In the background with no overlap (review 0.208.0): a slow check command must not hold up team dispatch.
        me = self.mandate_engine()
        t_now = asyncio.get_running_loop().time()
        busy_at = getattr(self, "_mandate_busy_at", 0.0)
        if me is not None and (not getattr(self, "_mandate_busy", False) or t_now - busy_at > 900):
            self._mandate_busy, self._mandate_busy_at = True, t_now

            async def _observe():
                try:
                    if await r._io(me.tick):
                        self.kick()
                except Exception as ex:  # noqa: BLE001 - one broken source must not stop the team loop
                    print(f"[team mandate] {type(ex).__name__}: {ex}", file=sys.stderr)
                finally:
                    self._mandate_busy = False
            self._spawn(_observe())
        # 0.436.0: jobs blocked by a temporary error whose retry time has come go back to the queue before dispatch.
        try:
            await r._io(r.retry_due)
        except Exception as ex:  # noqa: BLE001 - one broken retry must not stop the team loop
            print(f"[team retry] {type(ex).__name__}: {ex}", file=sys.stderr)
        await r.dispatch_once(wait=False)
        # T3 phần J: lần chờ của bộ phán xử quá 30 phút thì hết hạn (nhóm và chat riêng), xử lý nền.
        await r._io(r.judge_tick)
        now = asyncio.get_running_loop().time()
        if r.ceiling is not None and now - getattr(self, "_last_reconcile", 0.0) >= RECONCILE_EVERY_S:
            self._last_reconcile = now
            await r._io(r.reconcile_ceiling)
        if now - self._last_remind >= REMIND_EVERY_S:
            self._last_remind = now
            await r._io(r.remind_blocked)
        await self.core_reports()

    async def core_reports(self) -> int:
        """0.357.0 (issue #826): jobs Javis Core gave a team report back to the chat that asked, once per state worth
        reporting (done, cancelled, stopped for the owner). A failed send is retried next tick; the inbox copy dedupes."""
        if self.deps.report is None:
            return 0
        import team_dispatch
        sent = 0
        for it in await self.io(team_dispatch.due_reports, self):
            try:
                res = self.deps.report(it["report_to"], it["text"], kind="report", label=localefmt.chu("Team", "Team"),
                                       source="team", ngan=it["short"], brain=it["brain"], dedup=it["dedup"])
                if asyncio.iscoroutine(res):
                    res = await res
            except Exception as ex:  # noqa: BLE001 - one bad channel never stops the team loop
                print(f"[team core report] {type(ex).__name__}: {ex}", file=sys.stderr)
                continue
            if isinstance(res, tuple) and res and not res[0]:
                continue
            await self.io(self.deps.task_store().team_core_said, it["task_id"], it["key"], it["closed"])
            sent += 1
        return sent

    async def _judge_tick_without_teams(self) -> None:
        """Chưa có kho nhóm (chỉ dùng chat riêng): vẫn cho lần chờ của tin chủ động ở chat riêng hết hạn đúng giờ."""
        if self.deps.judge is None:
            return
        judge = self.deps.judge()
        if judge is None:
            return
        items = await asyncio.to_thread(judge.tick)
        if items:
            self._spawn(judge.process_released(items))

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


class OpError(Exception):
    """Lỗi của một thao tác nhóm, có mã HTTP và câu hai thứ tiếng (route trả JSON, công cụ `javis_team` trả chữ)."""

    def __init__(self, code: int, vi: str, en: str, **extra):
        super().__init__(vi)
        self.code, self.vi, self.en, self.extra = code, vi, en, extra


class TeamOps:
    """Thao tác quản lý nhóm dùng chung cho route `/teams/*` và công cụ `javis_team` (0.173.0): một chỗ duy nhất giữ luật
    (kiểm trợ lý có thật, khoá `accept_lock`, huỷ việc khi lưu trữ, chạy lại khi mở lại), nên trang web và Javis trong chat
    làm y như nhau. Mọi hàm chạy ở luồng phụ (route qua `api.io`, công cụ qua `asyncio.to_thread`). Lỗi: `OpError` hay
    `TeamError` của kho."""

    def __init__(self, api: "TeamApi"):
        self.api = api
        self.deps = api.deps

    # ───────────── tra cứu ─────────────

    def root(self, brain: str) -> str:
        root = self.deps.brain_key(brain or "")
        if not root or not Path(root).is_dir():
            raise OpError(404, "Không tìm thấy brain", "Brain not found")
        return root

    def team(self, root: str, team_id: str) -> dict:
        team = self.api.teams().get(team_id) if self.api.exists() else None
        if not team or team["brain_id"] != root:
            raise OpError(404, "Không có nhóm này", "Team not found")
        return team

    def slugs(self, root: str) -> set:
        return {m["slug"] for m in (self.deps.agents_meta(root) or [])}

    def member_key(self, team: dict, who: str) -> str:
        """`who` là agent_key hay slug của một thành viên (đang hoạt động hay đã rời) của nhóm."""
        who = str(who or "").strip()
        for m in self.api.teams().members(team["team_id"], include_removed=True):
            if who in (m["agent_key"], m.get("slug_at_join")):
                return m["agent_key"]
        reg = self.deps.resonance_store().agent(team["brain_id"], who) if who else None
        if reg:
            return reg["agent_key"]
        raise OpError(404, f"Không có thành viên: {who}", f"No such member: {who}")

    # ───────────── thao tác ─────────────

    def create(self, brain: str, root: str, name: str, members: list, leader: str = "", description: str = "",
               client_req_id: str = "") -> dict:
        """Tạo nhóm. Trả {"team": dòng nhóm, "duplicate": bool}."""
        name = str(name or "").strip()
        members = [str(s) for s in (members or []) if str(s or "").strip()]
        leader = str(leader or "").strip()
        if not name:
            raise OpError(400, "Thiếu tên nhóm", "Team name is required")
        if leader and leader not in members:
            members.append(leader)
        # Nhóm cần ít nhất một trợ lý (0.142.0): người tạo là người thật, không tính là thành viên AI.
        if not members:
            raise OpError(400, "Chọn ít nhất một trợ lý", "Pick at least one assistant")
        have = self.slugs(root)
        missing = [s for s in members if s not in have]
        if missing:
            raise OpError(400, f"Không có trợ lý: {', '.join(missing)}", f"No such assistant: {', '.join(missing)}")
        teams = self.api.teams()
        # Bấm Tạo hai lần hay mạng chậm gửi lại cùng mã: trả nhóm đã tạo, không tạo phiên hay nhóm thứ hai.
        req = str(client_req_id or "").strip()[:80]
        old = teams.find_by_request(root, req) if req else None
        if old is not None:
            return {"team": old, "duplicate": True}
        keys = {slug: self.api.register_agent(root, slug)["agent_key"] for slug in dict.fromkeys(members)}
        tid = team_store.new_team_id()
        sid = self.deps.session_store().create_session(brain=brain, channel=f"team:{tid}", title=name[:120])
        # Người tạo: luôn là chủ máy đã qua cổng đăng nhập của server (Javis có một tài khoản), không đọc từ client.
        try:
            team = teams.create_team(root, name, str(description or ""), sid, team_id=tid,
                                     members=[(keys[s], s) for s in keys], leader_key=keys[leader] if leader else None,
                                     client_req_id=req or None, by="owner")
        except Exception:
            # Không tạo được nhóm (kho bận quá lâu...): phiên vừa mở không gắn nhóm nào thì bỏ, không để mồ côi.
            self._drop_session(sid)
            raise
        if team["team_id"] != tid:
            # Hai yêu cầu cùng mã chạy song song: yêu cầu kia thắng, phiên vừa mở không gắn nhóm nào thì bỏ.
            self._drop_session(sid)
            return {"team": team, "duplicate": True}
        return {"team": team, "duplicate": False}

    def update(self, root: str, team_id: str, **fields) -> dict:
        """Đổi tên, mô tả, ảnh nhóm, trạng thái (`active`/`paused`/`archived`). Lưu trữ huỷ việc đang chờ hay bị chặn;
        mở lại thì chạy tiếp. Trả dòng nhóm sau khi đổi."""
        team = self.team(root, team_id)
        fields = {k: v for k, v in fields.items() if k in ("name", "description", "status", "avatar_image", "tags")
                  and v is not None}
        if not fields:
            return team
        runner = self.api.runner()
        with runner.accept_lock:
            updated = self.api.teams().update(team_id, **fields)
        if fields.get("status") == "archived":
            q = self.deps.task_store().team_queue(team_id)
            for t in q["waiting"] + q["blocked"]:
                runner.cancel_job(t["id"], "nhóm đã lưu trữ")
            runner.cancel_idle_running(team_id, "nhóm đã lưu trữ")
        elif fields.get("status") == "active" and team["status"] != "active":
            runner._on_loop(lambda: self.api._spawn(runner.resume_team(team_id)))
            self.api.kick()
        runner._state(team_id)
        return updated

    def add_member(self, root: str, team_id: str, slug: str) -> dict:
        self.team(root, team_id)
        slug = str(slug or "").strip()
        if slug not in self.slugs(root):
            raise OpError(400, f"Không có trợ lý: {slug}", f"No such assistant: {slug}")
        reg = self.api.register_agent(root, slug)
        self.api.teams().add_member(team_id, reg["agent_key"], slug)
        self.api.runner()._state(team_id)
        return self.api.teams().get(team_id)

    def remove_member(self, root: str, team_id: str, agent_key: str) -> dict:
        self.team(root, team_id)
        with self.api.runner().accept_lock:
            removed = self.api.teams().remove_member(team_id, agent_key)
        if not removed:
            raise OpError(404, "Không phải thành viên đang hoạt động", "Not an active member")
        self.api.runner()._state(team_id)
        return self.api.teams().get(team_id)

    def set_leader(self, root: str, team_id: str, agent_key: Optional[str]) -> dict:
        self.team(root, team_id)
        with self.api.runner().accept_lock:
            updated = self.api.teams().set_leader(team_id, str(agent_key) if agent_key else None)
        if updated["leader_key"]:
            self.api.runner().resume_no_leader(team_id)
            self.api.kick()
        self.api.runner()._state(team_id)
        return updated

    def delete(self, root: str, team_id: str) -> dict:
        """Xoá hẳn một nhóm ĐÃ LƯU TRỮ (0.173.0): dòng của nhóm trong kho nhóm và phiên chat của nhóm. Trả dòng đã xoá."""
        self.team(root, team_id)
        with self.api.runner().accept_lock:
            gone = self.api.teams().delete_team(team_id)
        self._drop_session(gone["session_id"])
        self.api.runner()._publish({"type": "team_state", "team_id": team_id, "deleted": True})
        return gone

    def _drop_session(self, sid: str) -> None:
        try:
            self.deps.session_store().delete(sid)
        except Exception:  # noqa: BLE001
            pass


_CURRENT: list = [None]


def current() -> Optional[TeamOps]:
    """`TeamOps` của tiến trình (đặt trong `register`), cho plugin `javis_team` gọi mà không import main. None khi chưa
    đăng ký (test không dựng host)."""
    return _CURRENT[0]



async def _described_then(api: "TeamApi", team: dict, pics: list, caption: str, then: Any) -> None:
    """Describe the pictures of a team message, then run what comes after it (`then()`, its member turns). A failed or slow
    description never stops the turns: they run anyway and the documents block says the picture could not be read."""
    try:
        await asyncio.wait_for(api.deps.describe(team, pics, caption), DESCRIBE_TIMEOUT_S)
    except Exception as ex:  # noqa: BLE001 - timeouts and engine errors alike
        print(f"[team] không tả được ảnh: {type(ex).__name__}: {str(ex)[:200]}", file=sys.stderr)
    if then is not None:
        await then()

def register(app, deps: TeamApiDeps) -> TeamApi:
    """Đăng ký route `/teams/*`. Gọi SAU route cuối của main.py để bảng route cũ giữ nguyên thứ tự."""
    api = TeamApi(deps)
    ops = TeamOps(api)
    api.ops = ops
    _CURRENT[0] = ops

    def _op_err(ex: Exception) -> JSONResponse:
        if isinstance(ex, OpError):
            return _err(ex.code, ex.vi, ex.en, **ex.extra)
        return _team_err(ex)

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
            rows = [dict(t, counts=api.counts(t["team_id"]), last=api.last_message(t), unread=api.unread(t),
                         **api.faces(t, meta))
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
            try:
                root = ops.root(brain)
                got = ops.create(brain, root, body.get("name"), list(body.get("members") or []),
                                 body.get("leader_slug") or "", body.get("description") or "",
                                 body.get("client_req_id") or "")
            except (OpError, TeamError) as ex:
                return _op_err(ex)
            out = {"ok": True, "team": api.view(got["team"])}
            if got["duplicate"]:
                out["duplicate"] = True
            return out
        return await api.io(_do)

    @app.get("/teams/{team_id}")
    async def teams_get(team_id: str, brain: str = "brain"):
        def _do():
            team, err = _team(team_id, brain)
            # 0.192.0: who is writing right now, for the "is typing" strip when the chat opens or reconnects.
            if err:
                return err
            # 0.192.0: pinned messages for the pinned strip on top of the chat (the same list member turns follow).
            pinned = [{"id": m["id"], "ts": m["ts"], "author_kind": m["author_kind"], "author_ref": m["author_ref"],
                       "content": str(m.get("content") or "")[:400]}
                      for m in deps.session_store().team_decisions(team["session_id"], PINNED_SHOWN)]
            import team_usage
            view = api.view(team)
            view["quality_usage"] = team_usage.team_usage(team_id)
            return {"ok": True, "team": view, "typing": api.teams().active_turns(team_id), "pinned": pinned}
        return await api.io(_do)

    @app.patch("/teams/{team_id}")
    async def teams_patch(team_id: str, request: Request, brain: str = "brain"):
        body = await _body(request)

        def _do():
            team, err = _team(team_id, brain)
            if err:
                return err
            fields = {k: body[k] for k in ("name", "description", "status", "avatar_image", "tags") if k in body}
            # Ảnh nhóm (0.176.0): "" gỡ ảnh (về ảnh ghép từ thành viên); tên ảnh phải có trong kho ảnh đã tải lên.
            if "avatar_image" in fields:
                img = fields["avatar_image"]
                if img is None:
                    fields["avatar_image"] = ""
                elif img != "" and not avatar_upload.hop_le(img):
                    return JSONResponse({"ok": False, "error": localefmt.chu("Ảnh team không hợp lệ, tải lại ảnh.",
                                                                             "Invalid team picture, upload it again.")},
                                        status_code=400)
            try:
                updated = ops.update(team["brain_id"], team_id, **fields)
            except (OpError, TeamError) as ex:
                return _op_err(ex)
            return {"ok": True, "team": api.view(updated)}
        return await api.io(_do)

    @app.delete("/teams/{team_id}")
    async def teams_delete(team_id: str, brain: str = "brain"):
        """Xoá hẳn một nhóm đã lưu trữ (0.173.0). Nhóm chưa lưu trữ: 400 kèm lời nhắc lưu trữ trước."""
        def _do():
            team, err = _team(team_id, brain)
            if err:
                return err
            try:
                gone = ops.delete(team["brain_id"], team_id)
            except (OpError, TeamError) as ex:
                return _op_err(ex)
            return {"ok": True, "deleted": gone["team_id"]}
        return await api.io(_do)

    @app.post("/teams/{team_id}/members")
    async def teams_member_add(team_id: str, request: Request, brain: str = "brain"):
        slug = str((await _body(request)).get("slug") or "").strip()

        def _do():
            team, err = _team(team_id, brain)
            if err:
                return err
            try:
                return {"ok": True, "team": api.view(ops.add_member(team["brain_id"], team_id, slug))}
            except (OpError, TeamError) as ex:
                return _op_err(ex)
        return await api.io(_do)

    @app.delete("/teams/{team_id}/members/{agent_key}")
    async def teams_member_remove(team_id: str, agent_key: str, brain: str = "brain"):
        def _do():
            team, err = _team(team_id, brain)
            if err:
                return err
            try:
                return {"ok": True, "team": api.view(ops.remove_member(team["brain_id"], team_id, agent_key))}
            except (OpError, TeamError) as ex:
                return _op_err(ex)
        return await api.io(_do)

    @app.post("/teams/{team_id}/leader")
    async def teams_leader(team_id: str, request: Request, brain: str = "brain"):
        key = (await _body(request)).get("agent_key")

        def _do():
            team, err = _team(team_id, brain)
            if err:
                return err
            try:
                return {"ok": True, "team": api.view(ops.set_leader(team["brain_id"], team_id, key))}
            except (OpError, TeamError) as ex:
                return _op_err(ex)
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
            out = dict(deps.task_store().team_queue(team_id), ok=True, busy=api.runner().busy_view(team_id))
            out.update(_finished(team))
            return out
        return await api.io(_do)

    def _finished(team: dict) -> dict:
        """0.193.0: finished jobs of the team for the Jobs tab: `finished` (not yet marked Done by the owner, each with a
        short report: result, who did which step) and `archived` (marked Done). Deleted ones are left out."""
        import job_marks
        rows = deps.task_store().team_history(team["team_id"], FINISHED_SHOWN)
        jobs = []
        for t in rows:
            steps = []
            try:
                steps = [{"agent_key": x.get("agent_key") or "", "kind": x.get("kind") or "", "status": x.get("status") or ""}
                         for x in api.teams().steps(t["id"])][:20]
            except Exception:  # noqa: BLE001 - a broken step list never hides the job
                steps = []
            jobs.append({"id": f"team:{t['id']}", "task_id": t["id"], "title": t.get("title") or "", "bucket": "done",
                         "status": t.get("status") or "", "cancelled": t.get("status") == "cancelled",
                         "result": str(t.get("result") or "")[:4000], "created_at": t.get("created_at"),
                         "updated_at": t.get("updated_at"), "steps": steps})
        try:
            kept, archived = job_marks.split(jobs, job_marks.marks(team["brain_id"]))
        except Exception:  # noqa: BLE001
            kept, archived = jobs, []
        return {"finished": kept, "archived": archived}

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
            agents = api.teams().agent_reactions_for(team["session_id"], [m["id"] for m in msgs])
            for m in msgs:
                m["reaction"] = got.get(int(m["id"]))
                m["agent_reactions"] = api.runner().agent_reactions_view(team, agents.get(int(m["id"])))
            import team_usage
            acceptance = api.runner().acceptance_view(team, task_id)
            return {"ok": True, "task": task, "steps": api.teams().steps(task_id), "messages": msgs,
                    "acceptance": acceptance,
                    "completion_valid": acceptance.get("completion_valid", False) if acceptance else False,
                    "usage": team_usage.task_usage(team_id, task_id)}
        return await api.io(_do)

    @app.post("/teams/{team_id}/tasks/{task_id}/cancel")
    async def teams_task_cancel(team_id: str, task_id: str, brain: str = "brain"):
        def _do():
            team, err = _team(team_id, brain)
            if err:
                return err
            if not _own_task(team_id, task_id):
                return _err(404, "Không có việc này trong nhóm", "No such job in this team")
            prev = api.runner().cancel_job(task_id, owner_cancel=True)
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
            runner = api.runner()
            with runner.accept_lock:
                shares = runner.result_shares(deps.task_store().get_task(task_id))
                rev = deps.task_store().team_amend(task_id, text)
                if rev is not None:
                    runner.on_job_amended(task_id)
            if rev is None:
                return _err(409, "Việc đã kết thúc", "The job has already ended")
            runner._state(team_id)
            # T3 (6.1): sửa yêu cầu SAU khi đã có kết quả: -0.4 cho người nộp kết quả của bản trước, phân bổ theo 6.5 khi
            # có bản tổng hợp (review T3 P P3).
            runner.pulse_task_event("revise", team_id, list(shares), f"revise:{task_id}:{rev}", shares=shares)
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
            cur = deps.task_store().get_task(task_id) or {}
            if cur.get("block_kind") in api.runner().APPROVAL_BLOCKS:
                return _err(409, "Việc này đang chờ quyết định trên thẻ duyệt; hãy duyệt, sửa yêu cầu hay huỷ việc",
                            "This job waits for a decision on its approval card; decide, edit or cancel the job")
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
            agents = api.teams().agent_reactions_for(team["session_id"], ids)
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
                m["agent_reactions"] = api.runner().agent_reactions_view(team, agents.get(int(m["id"])))
                if replies.get(int(m["id"])):
                    m["replies"] = replies[int(m["id"])]
            return dict(page, ok=True)
        return await api.io(_do)

    @app.post("/teams/{team_id}/messages/{message_id}/reaction")
    async def teams_reaction(team_id: str, message_id: int, request: Request, brain: str = "brain"):
        """Thả cảm xúc, lý do, trục nói/im, góp ý (spec 14; hợp đồng T2 mục 5). Không mở lượt, không gọi model. Gửi lại cùng
        `nonce` trả trạng thái hiện tại (200); `nonce` đã dùng cho tin khác: 409."""
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
                                           comment=str(body.get("comment") or ""), nonce=str(body.get("nonce") or ""),
                                           axis=str(body.get("axis") or ""), seen_sha=body.get("seen_sha") or None)
            except team_store.NonceConflict as ex:
                return _team_err(ex, 409)
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
            # 0.195.0: the owner works here now; the Teams page opens this team next time, on any device.
            api.teams().mark_owner(team_id)
            text = str(body.get("text") or "").strip()
            files = []
            if body.get("attachments") and api.deps.attach is not None:
                # 0.191.0: the files become the team's documents (text ones are read by every member turn); the
                # message keeps their names so everyone in the chat sees what was sent.
                files = api.deps.attach(team, list(body.get("attachments") or []))
                if files:
                    text = (text + "\n\n" if text else "") + "📎 " + ", ".join(f["name"] for f in files)
            try:
                sub = runner.submit(team_id, text, mentions=list(body.get("mentions") or []),
                                    as_job=bool(body.get("as_job")),
                                    client_msg_id=str(body.get("client_msg_id") or ""), files=files,
                                    mention_all=bool(body.get("mention_all")))
            except TeamError as ex:
                return _team_err(ex)
            pics = [f for f in files if f.get("image")] if api.deps.describe is not None else []
            if sub["replies"] or sub.get("judge"):
                # Lượt trả lời theo @ (như cũ), rồi bộ phán xử cho người không được gọi (T3 phần J), đều chạy nền.
                # 0.192.0: ảnh đính kèm được tả thành chữ TRƯỚC, để lượt của thành viên đọc được ảnh (lượt chỉ chữ).
                if pics:
                    turns = lambda: runner.run_message(sub)  # noqa: E731 - created only once the pictures are described
                    runner._on_loop(lambda: api._spawn(_described_then(api, team, pics, text, turns)))
                else:
                    runner._on_loop(lambda: api._spawn(runner.run_message(sub)))
            elif pics:
                runner._on_loop(lambda: api._spawn(_described_then(api, team, pics, text, None)))
            if sub.get("task_id") and sub["created"]:
                api.kick()
            return dict(sub, ok=True)
        return await api.io(_do)

    @app.post("/teams/{team_id}/files")
    async def teams_add_files(team_id: str, request: Request, brain: str = "brain"):
        """Add documents to a team from its info panel, without a message (0.191.0). Same rules as attaching in chat."""
        body = await _body(request)

        def _do():
            team, err = _team(team_id, brain)
            if err:
                return err
            if api.deps.attach is None:
                return _err(501, "Máy chủ chưa hỗ trợ tài liệu nhóm", "Team documents are not supported here")
            files = api.deps.attach(team, list(body.get("attachments") or []))
            if not files:
                return _err(400, "Không thêm được file nào", "No file could be added")
            pics = [f for f in files if f.get("image")] if api.deps.describe is not None else []
            if pics:
                api.runner()._on_loop(lambda: api._spawn(_described_then(api, team, pics, "", None)))
            return {"ok": True, "files": files, "session_id": team["session_id"]}
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

    @app.post("/teams/{team_id}/messages/{message_id}/reject")
    async def teams_reject(team_id: str, message_id: int, brain: str = "brain"):
        """Bác thẻ đề xuất việc (T3, nút Bỏ qua): -0.4 cho agent đề xuất, thẻ đổi trạng thái ở mọi tab."""
        def _do():
            team, err = _team(team_id, brain)
            if err:
                return err
            try:
                changed = api.runner().reject_proposal(team_id, message_id)
            except TeamError as ex:
                return _team_err(ex, 409)
            return {"ok": True, "rejected": True, "changed": changed}
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
            msg = ss.team_message(team["session_id"], message_id)
            api.runner()._publish({"type": "team_message", "team_id": team_id, "message": msg})
            # T3 (6.1): chốt quyết định trên tin của agent là bằng chứng hữu ích (+0.6); bỏ chốt thì tín hiệu `void`.
            src = f"decision:{team_id}:{int(message_id)}"
            if on and (msg or {}).get("author_kind") == "agent":
                api.runner().pulse_task_event("decision", team_id, [msg.get("author_ref") or ""], src,
                                              f"team:{team['session_id']}:{int(message_id)}")
            elif not on:
                api.runner()._pulse("void_task_event", src)
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

    @app.post("/teams/{team_id}/opened")
    async def teams_opened(team_id: str, brain: str = "brain"):
        """The owner opened this team (0.195.0). GET /teams returns `owner_at`, so the Teams page opens the team worked in
        last, on any device. Not an edit: the list order and the team's history stay as they are."""
        def _do():
            team, err = _team(team_id, brain)
            if err:
                return err
            api.teams().mark_owner(team_id)
            # 0.197.0: the team is read now; other open pages and devices clear its unread badge.
            api.runner()._publish({"type": "team_read", "team_id": team_id})
            return {"ok": True}
        return await api.io(_do)

    @app.get("/teams/{team_id}/approvals")
    async def teams_approvals(team_id: str, brain: str = "brain", task_id: str = ""):
        """Owner approval requests of the team (0.207.0), newest first, or of one job with `task_id`."""
        def _do():
            team, err = _team(team_id, brain)
            if err:
                return err
            return {"ok": True, "approvals": api.runner().approvals_view(team_id, task_id or None)}
        return await api.io(_do)

    @app.post("/teams/{team_id}/approvals/{approval_id}/decide")
    async def teams_approval_decide(team_id: str, approval_id: str, request: Request, brain: str = "brain"):
        """The owner's decision on one approval card (0.207.0): `decision` approve | reject | changes | revoke, `note`,
        `decision_key` (one per click: a retry replays the first answer, a second tab gets already_decided) and
        `expected_rev` (the job revision the card showed). Owner-only by construction: the dashboard's login and CSRF
        stand in front of this route, and no JAVIS_TEAM directive or chat text reaches it."""
        body = await _body(request)
        decision = str(body.get("decision") or "").strip().lower()
        note = str(body.get("note") or "")[:2000]
        key = str(body.get("decision_key") or "").strip()[:80]
        try:
            rev = int(body["expected_rev"]) if body.get("expected_rev") not in (None, "") else None
        except (TypeError, ValueError):
            rev = None

        def _do():
            team, err = _team(team_id, brain)
            if err:
                return err
            if decision not in ("approve", "reject", "changes", "revoke"):
                return _err(400, "Quyết định không hợp lệ", "Invalid decision")
            if decision != "revoke" and not key:
                return _err(400, "Thiếu mã lần bấm", "Missing decision key")
            if decision in ("reject", "changes") and not note.strip():
                return _err(400, "Ghi lý do để trợ lý biết hướng sửa", "Add a reason so the assistant knows what to change")
            out = api.runner().decide_approval(team_id, approval_id, decision, note=note, decision_key=key,
                                               expected_rev=rev, by="owner")
            if not out.get("ok"):
                code = 404 if out.get("error") == "not_found" else 409
                msgs = {"not_found": ("Không có yêu cầu này", "No such request"),
                        "already_decided": ("Yêu cầu đã được quyết ở nơi khác", "This request was already decided"),
                        "stale": ("Việc đã sửa, yêu cầu này không còn hợp lệ", "The job changed; this request is void"),
                        "expired": ("Yêu cầu đã hết hạn", "This request has expired"),
                        "job_ended": ("Việc đã kết thúc", "The job has already ended"),
                        "member_left": ("Người xin đã rời nhóm", "The member who asked left the team"),
                        "not_revocable": ("Chỉ thu hồi được yêu cầu đã duyệt mà chưa dùng",
                                          "Only an approved, unused request can be revoked"),
                        "key_reused": ("Mã lần bấm đã dùng cho yêu cầu khác", "This decision key was used elsewhere")}
                vi, en = msgs.get(out.get("error") or "", ("Không quyết được", "Could not decide"))
                return _err(code, vi, en, error=out.get("error"), approval=out.get("approval"))
            api.kick()
            return {"ok": True, "status": out.get("status"), "replay": bool(out.get("replay")),
                    "approval": out.get("approval")}
        return await api.io(_do)

    @app.post("/teams/{team_id}/work_mode")
    async def teams_work_mode(team_id: str, request: Request, brain: str = "brain"):
        """Owner's switch (0.207.0): `mode` gated (outside actions wait for approval, default) or full (the team acts on
        its own). Takes effect from the next step; a step already running keeps the level it started with."""
        mode = str((await _body(request)).get("mode") or "").strip().lower()

        def _do():
            team, err = _team(team_id, brain)
            if err:
                return err
            if mode not in ("gated", "full"):
                return _err(400, "Quyền làm việc không hợp lệ", "Invalid work mode")
            before = team.get("work_mode") or "gated"
            api.teams().set_work_mode(team_id, mode)
            if before != mode:
                r = api.runner()
                r._post(api.teams().get(team_id), "Chủ nhóm cho nhóm tự làm hành động ra ngoài, không cần hỏi từng bước."
                        if mode == "full" else "Chủ nhóm đặt lại: hành động ra ngoài của nhóm phải chờ duyệt.",
                        author_kind="system", meta={"kind": "work_mode", "work_mode": mode})
                r._publish({"type": "team_state", "team_id": team_id})
            return {"ok": True, "work_mode": mode}
        return await api.io(_do)

    # Quality policy and default acceptance templates are owner settings, never agent directives.
    def _quality_error(ex: ValueError) -> JSONResponse:
        code = getattr(ex, "code", "invalid_quality_setting")
        conflict = code in ("version_conflict", "stale_version")
        return _err(409 if conflict else 400, "Thiết lập chất lượng chưa hợp lệ",
                    "The quality setting is invalid", quality_code=code, detail=str(ex))

    @app.get("/teams/{team_id}/quality-policy")
    async def teams_quality_policy_get(team_id: str, brain: str = "brain"):
        def _do():
            team, err = _team(team_id, brain)
            if err:
                return err
            return {"ok": True, "policy": api.runner().quality.policy(team_id)}
        return await api.io(_do)

    @app.put("/teams/{team_id}/quality-policy")
    async def teams_quality_policy_put(team_id: str, request: Request, brain: str = "brain"):
        body = await _body(request)
        def _do():
            team, err = _team(team_id, brain)
            if err:
                return err
            try:
                policy = api.runner().quality.set_policy(team_id, body)
            except ValueError as ex:
                return _quality_error(ex)
            api.runner()._state(team_id)
            return {"ok": True, "policy": policy}
        return await api.io(_do)

    @app.get("/teams/{team_id}/acceptance-template")
    async def teams_acceptance_template_get(team_id: str, brain: str = "brain"):
        def _do():
            team, err = _team(team_id, brain)
            if err:
                return err
            return {"ok": True, "template": api.runner().quality.template(team_id)}
        return await api.io(_do)

    @app.put("/teams/{team_id}/acceptance-template")
    async def teams_acceptance_template_put(team_id: str, request: Request, brain: str = "brain"):
        body = await _body(request)
        def _do():
            team, err = _team(team_id, brain)
            if err:
                return err
            try:
                template = api.runner().quality.set_template(team_id, body)
            except ValueError as ex:
                return _quality_error(ex)
            api.runner()._state(team_id)
            return {"ok": True, "template": template}
        return await api.io(_do)

    @app.get("/teams/{team_id}/usage")
    async def teams_usage_get(team_id: str, brain: str = "brain"):
        def _do():
            team, err = _team(team_id, brain)
            if err:
                return err
            import team_usage
            return {"ok": True, "usage": team_usage.team_usage(team_id)}
        return await api.io(_do)

    @app.get("/teams/{team_id}/tasks/{task_id}/usage")
    async def teams_task_usage_get(team_id: str, task_id: str, brain: str = "brain"):
        def _do():
            team, err = _team(team_id, brain)
            if err:
                return err
            if not _own_task(team_id, task_id):
                return _err(404, "Không có việc này trong nhóm", "No such job in this team")
            import team_usage
            return {"ok": True, "usage": team_usage.task_usage(team_id, task_id)}
        return await api.io(_do)

    # ───────────── 0.209.0: product acceptance ─────────────

    @app.get("/teams/{team_id}/tasks/{task_id}/acceptance")
    async def teams_acceptance_get(team_id: str, task_id: str, brain: str = "brain"):
        def _do():
            team, err = _team(team_id, brain)
            if err:
                return err
            if not _own_task(team_id, task_id):
                return _err(404, "Không có việc này trong nhóm", "No such job in this team")
            r = api.runner()
            return {"ok": True, "acceptance": r.acceptance_view(team, task_id),
                    "history": r.acceptance.history(task_id) if r.acceptance is not None else []}
        return await api.io(_do)

    @app.put("/teams/{team_id}/tasks/{task_id}/acceptance")
    async def teams_acceptance_put(team_id: str, task_id: str, request: Request, brain: str = "brain"):
        """Owner sets the job's acceptance criteria (owner only: no JAVIS_TEAM directive reaches this)."""
        body = await _body(request)

        def _do():
            import team_acceptance
            team, err = _team(team_id, brain)
            if err:
                return err
            if not _own_task(team_id, task_id):
                return _err(404, "Không có việc này trong nhóm", "No such job in this team")
            try:
                got = api.runner().set_acceptance(team_id, task_id, body.get("criteria"), body.get("fix_rounds"))
                if got.get("recheck"):
                    api._spawn(api.runner().recheck(task_id))
            except team_acceptance.AcceptanceError as ex:
                return _err(400, f"Tiêu chí chưa hợp lệ: {ex}", f"Criteria are not valid: {ex}")
            api.runner()._system(api.teams().get(team_id), "Chủ nhóm đã đặt tiêu chí nghiệm thu cho việc này.",
                                 "acceptance_set")
            return {"ok": True, "acceptance": api.runner().acceptance_view(team, task_id)}
        return await api.io(_do)

    @app.post("/teams/{team_id}/tasks/{task_id}/acceptance/decide")
    async def teams_acceptance_decide(team_id: str, task_id: str, request: Request, brain: str = "brain"):
        body = await _body(request)

        def _do():
            team, err = _team(team_id, brain)
            if err:
                return err
            def _int(v):
                try:
                    return int(v) if v not in (None, "") else None
                except (TypeError, ValueError):
                    return None
            out = api.runner().decide_acceptance(team_id, task_id, str(body.get("decision") or "").lower(),
                                                 note=str(body.get("note") or "")[:2000],
                                                 revision=_int(body.get("revision")), round_=_int(body.get("round")),
                                                 contract_version=_int(body.get("contract_version")),
                                                 output_manifest_hash=(str(body["output_manifest_hash"])
                                                     if body.get("output_manifest_hash") is not None else None),
                                                 decision_key=str(body.get("decision_key") or "")[:200])
            if not out.get("ok"):
                msgs = {"not_found": ("Việc này chưa có tiêu chí nghiệm thu", "This job has no acceptance criteria"),
                        "not_waiting": ("Việc không ở bước chờ nghiệm thu", "The job is not waiting for acceptance"),
                        "product_changed": ("Sản phẩm đã đổi sau lần kiểm, cần kiểm lại", "The product changed after the check"),
                        "note_required": ("Ghi điều cần sửa", "Say what should change"),
                        "stale_card": ("Thẻ này đã cũ, xem thẻ nghiệm thu mới nhất", "This card is out of date; see the latest one"),
                        "bad_decision": ("Quyết định không hợp lệ", "Invalid decision")}
                vi, en = msgs.get(out.get("error") or "", ("Không quyết được", "Could not decide"))
                return _err(404 if out.get("error") == "not_found" else 409, vi, en, error=out.get("error"))
            api.kick()
            return out
        return await api.io(_do)

    # ───────────── 0.208.0: department mandate ─────────────

    def _mandate_view(team_id: str) -> dict:
        import team_mandate
        st = api.mandates()
        m = st.get(team_id)
        return {"ok": True, "mandate": m, "sources": team_mandate.sources_view(st, m),
                "opportunities": [team_mandate.view(o) for o in st.opportunities(team_id, limit=30)],
                "versions": [{"version": v["version"], "by": v["by"], "at": v["at"]} for v in st.versions(team_id)],
                "observing": api.deps.mandate_deps is not None}

    @app.get("/teams/{team_id}/mandate")
    async def teams_mandate_get(team_id: str, brain: str = "brain"):
        def _do():
            team, err = _team(team_id, brain)
            if err:
                return err
            return _mandate_view(team_id)
        return await api.io(_do)

    @app.put("/teams/{team_id}/mandate")
    async def teams_mandate_put(team_id: str, request: Request, brain: str = "brain"):
        """Owner writes or edits the team's mandate (a new version). Never reachable from a JAVIS_TEAM directive."""
        body = await _body(request)

        def _do():
            import team_mandate
            team, err = _team(team_id, brain)
            if err:
                return err
            try:
                api.mandates().put(team_id, body, by="owner", status=body.get("status") or None)
            except team_mandate.MandateError as ex:
                return _err(400, f"Mục tiêu chưa hợp lệ: {ex}", f"The mandate is not valid: {ex}")
            m = api.mandates().get(team_id)
            api.runner()._system(api.teams().get(team_id), f"Chủ nhóm đã cập nhật mục tiêu phòng ban (bản {m['version']}).",
                                 "mandate_edited")
            api.runner()._state(team_id)
            return _mandate_view(team_id)
        return await api.io(_do)

    @app.post("/teams/{team_id}/mandate/status")
    async def teams_mandate_status(team_id: str, request: Request, brain: str = "brain"):
        """`status` active | paused | off | revoked. Revoke cancels the mandate's jobs that have not started."""
        status = str((await _body(request)).get("status") or "").strip().lower()

        def _do():
            import team_mandate
            team, err = _team(team_id, brain)
            if err:
                return err
            if status not in team_mandate.STATUSES:
                return _err(400, "Trạng thái không hợp lệ", "Invalid status")
            try:
                if status == "revoked":
                    me = api.mandate_engine() or team_mandate.MandateEngine(api.mandates(), api.runner(), None)
                    out = me.revoke(team_id, by="owner")
                else:
                    api.mandates().set_status(team_id, status, by="owner")
                    out = {}
            except team_mandate.MandateError as ex:
                return _err(409, str(ex), str(ex))
            label = {"active": "bật", "paused": "tạm dừng", "off": "tắt", "revoked": "thu hồi"}[status]
            api.runner()._system(api.teams().get(team_id), f"Chủ nhóm đã {label} mục tiêu phòng ban.", "mandate_status")
            api.runner()._state(team_id)
            return dict(_mandate_view(team_id), cancelled=out.get("cancelled", []))
        return await api.io(_do)

    @app.post("/teams/{team_id}/mandate/opportunities/{opp_id}/decide")
    async def teams_mandate_decide(team_id: str, opp_id: str, request: Request, brain: str = "brain"):
        decision = str((await _body(request)).get("decision") or "").strip().lower()

        def _do():
            import team_mandate
            team, err = _team(team_id, brain)
            if err:
                return err
            me = api.mandate_engine() or team_mandate.MandateEngine(api.mandates(), api.runner(), None)
            if decision == "accept" and me.deps is None:
                return _err(409, "Máy chủ chưa bật quan sát mục tiêu", "Mandate observation is not enabled")
            out = me.decide(team_id, opp_id, decision, by="owner")
            if not out.get("ok"):
                return _err(404 if out.get("error") == "not_found" else 409, "Không quyết được cơ hội này",
                            "Could not decide this opportunity", error=out.get("error"))
            api.kick()
            return out
        return await api.io(_do)

    @app.get("/teams/{team_id}/mandate/trace/{opp_id}")
    async def teams_mandate_trace(team_id: str, opp_id: str, brain: str = "brain"):
        """mandate version -> observation -> opportunity -> decision -> approvals -> job -> steps (-> acceptance)."""
        def _do():
            import team_mandate
            team, err = _team(team_id, brain)
            if err:
                return err
            me = api.mandate_engine() or team_mandate.MandateEngine(api.mandates(), api.runner(), None)
            tr = me.trace(team_id, opp_id)
            if tr is None:
                return _err(404, "Không có cơ hội này", "No such opportunity")
            return {"ok": True, "trace": tr}
        return await api.io(_do)

    @app.post("/teams/{team_id}/mute")
    async def teams_mute(team_id: str, request: Request, brain: str = "brain"):
        """Turn this team's notifications off (`on: true`) or back on (0.197.0). Muted: nothing from the team reaches the
        owner's inbox or devices, not even a message calling the owner; the unread count still shows on the list."""
        on = bool((await _body(request)).get("on"))

        def _do():
            team, err = _team(team_id, brain)
            if err:
                return err
            api.teams().set_muted(team_id, on)
            api.runner()._publish({"type": "team_state", "team_id": team_id})
            return {"ok": True, "muted": on}
        return await api.io(_do)

    return api
