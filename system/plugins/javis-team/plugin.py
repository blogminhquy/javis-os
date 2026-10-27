"""Plugin bundled: tool `javis_team` - quản lý nhóm chat từ MỌI engine (0.173.0).

Vì sao có tool này
==================
Chủ dự án (2026-10-16) muốn nói trong chat "tạo nhóm thử gồm vài trợ lý, mỗi người một model" là Javis làm luôn: tạo trợ lý
còn thiếu, lập nhóm, chọn trưởng nhóm. Trước bản này Javis chỉ có route `/teams/*` sau cổng đăng nhập, nên một phiên chat phải
điều khiển trình duyệt (Playwright) và vấp lỗi 401. Tool chạy IN-PROCESS qua `team_api.current()`: cùng một lớp `TeamOps` mà
route của trang Nhóm dùng, nên luật (trợ lý phải có thật, khoá, huỷ việc khi lưu trữ, chạy lại khi mở lại) y như bấm tay.

Luật an toàn
============
- `vault_root` rỗng -> lỗi rõ, không bao giờ đoán brain (giống `javis_task`).
- Xoá chỉ nhận nhóm ĐÃ lưu trữ và phải có `confirm: true`; model chỉ đặt cờ đó khi chủ nói rõ là xoá.
- Mức `safe`: chỉ ghi file trợ lý và dữ liệu nhóm trong máy, không thao tác ra ngoài. Chỉ chủ dùng (`OWNER_ONLY_TOOLS`).
- op=dispatch / job (0.357.0, issue #826): Javis Core giao một việc cho nhóm có sẵn và đọc lại trạng thái, nghiệm thu.
  Luật nằm ở `team_dispatch.py`: chỉ lượt của chủ hay việc nền chủ đã lên lịch, không bao giờ từ một bước việc nhóm;
  nơi báo kết quả lấy từ lượt, không từ model.
"""
from __future__ import annotations

import asyncio

try:
    import team_api
    import team_dispatch
    import turn_context
except Exception:          # chạy lẻ ngoài máy chủ
    team_api = team_dispatch = turn_context = None

_LIST_MAX = 30
_OPS = ("list", "get", "list_agents", "create", "update", "archive", "unarchive", "delete", "add_member",
        "remove_member", "set_leader", "create_agent", "set_agent_model", "dispatch", "job")
_NO_OPS = ("ERROR: bộ quản lý nhóm chưa sẵn sàng (máy chủ đang khởi động?). Thử lại sau vài giây, "
           "hoặc làm ở trang Nhóm trên dashboard.")


class _Fail(Exception):
    pass


def _s(v) -> str:
    return str(v or "").strip()


def _ops():
    ops = team_api.current() if team_api is not None else None
    if ops is None:
        raise _Fail(_NO_OPS)
    return ops


def _err_text(ex: Exception) -> str:
    if team_api is not None and isinstance(ex, team_api.OpError):
        return f"ERROR: {ex.vi}"
    return f"ERROR: {ex}"


def _dispatch(ops, root, team, args, turn) -> str:
    """op=dispatch (0.357.0, issue #826): Javis Core giao MỘT việc cho nhóm có sẵn, kết quả tự báo về khung chat đã giao."""
    got = team_dispatch.dispatch(ops, root, team, args.get("objective") or args.get("description"), turn,
                                 assignee=_s(args.get("assignee") or args.get("slug")),
                                 request_id=_s(args.get("request_id")))
    task = got["task"]
    out = [("Việc này đã giao trước đó (cùng mã đối chiếu), KHÔNG tạo việc thứ hai."
            if not got["created"] else f"Đã giao việc cho nhóm {team['name']}."),
           f"Mã việc: {got['task_id']}", f"Mã đối chiếu: {got['correlation_id']}",
           "Trạng thái: " + team_dispatch.phase(task, None, team)[1]]
    if got["report_to"]:
        out.append("Nhóm làm xong, bị chặn hay cần chủ quyết thì Javis tự báo về đúng khung chat này (và hòm thư); "
                   "không cần chờ hay hứa báo lại. Xem tiến độ: op=job với task là mã việc.")
    else:
        out.append("Không rõ khung chat để báo, nên kết quả về Javis Core của brain và hòm thư. Xem tiến độ: op=job.")
    if got["quality"]:
        out.append("Nhóm bật nghiệm thu: việc chỉ tính ĐẠT khi qua kiểm hay chủ xác nhận trên thẻ; Javis không tự duyệt.")
    if got["paused"]:
        out.append("CẢNH BÁO: nhóm đang tạm dừng nên việc NẰM CHỜ, chưa chạy. Nói rõ với chủ: bật lại nhóm ở trang Nhóm.")
    return "\n".join(out)


def _job(ops, team, args) -> str:
    v = team_dispatch.view(ops, team, team_dispatch.find(ops, team, args.get("task") or args.get("request_id")))
    nghiem = {"pass": "ĐẠT (đã kiểm hay chủ xác nhận)", "pending": "chưa xác nhận đạt",
              "none": "nhóm không bật nghiệm thu"}[v["verdict"]]
    out = [f"Việc {v['task_id']} của nhóm {v['team']}: {v['title']}", f"Trạng thái: {v['line']}",
           f"Nghiệm thu: {nghiem}" + (f" ({v['acceptance_status']})" if v["acceptance_status"] else "")]
    if v["correlation_id"]:
        out.append(f"Mã đối chiếu: {v['correlation_id']}")
    if v["steps"]:
        out.append("Các bước: " + "; ".join(f"{x['agent_key'] or '-'} {x['kind']} {x['status']}" for x in v["steps"]))
    if v["result"]:
        out.append("Kết quả:\n" + v["result"][:4000])
    return "\n".join(out)


def _agents(ops, root) -> list:
    return list(ops.deps.agents_meta(root) or [])


def _agent_models(root) -> dict:
    """{slug: (model, provider)} đọc thẳng từ frontmatter (agents_meta chỉ có provider đã suy)."""
    out = {}
    try:
        from skill_router import read_frontmatter_only
        from pathlib import Path
        d = Path(root) / "agents"
        for fp in sorted(d.glob("*.md")) if d.is_dir() else []:
            meta = read_frontmatter_only(fp)[0] or {}
            out[fp.stem] = (_s(meta.get("model")), _s(meta.get("model_provider")))
    except Exception:
        pass
    return out


def _find_team(ops, root, ref) -> dict:
    """`ref` là team_id hay TÊN nhóm (không phân biệt hoa thường) trong brain này."""
    ref = _s(ref)
    if not ref:
        raise _Fail("ERROR: thiếu team (mã nhóm hay tên nhóm). Dùng op=list để xem các nhóm.")
    if not ops.api.exists():
        raise _Fail("ERROR: brain này chưa có nhóm nào. Dùng op=create để tạo.")
    team = ops.api.teams().get(ref)
    if team and team["brain_id"] == root:
        return team
    hits = [t for t in ops.api.teams().list_teams(root, limit=200, include_archived=True)
            if _s(t.get("name")).lower() == ref.lower()]
    if len(hits) == 1:
        return hits[0]
    if len(hits) > 1:
        raise _Fail(f"ERROR: có {len(hits)} nhóm cùng tên '{ref}'. Dùng mã nhóm: "
                    + ", ".join(f"{t['team_id']} ({t['status']})" for t in hits))
    raise _Fail(f"ERROR: không có nhóm '{ref}' trong brain này. Dùng op=list để xem các nhóm.")


def _team_line(ops, team, models=None) -> str:
    members = [m for m in ops.api.teams().members(team["team_id"])]
    names = []
    for m in members:
        slug = m.get("slug_at_join") or m["agent_key"]
        mark = " (trưởng nhóm)" if m["agent_key"] == team.get("leader_key") else ""
        mdl = (models or {}).get(slug, ("", ""))[0]
        names.append(f"{slug}{mark}" + (f" [{mdl}]" if mdl else ""))
    return (f"- {team['name']} | mã {team['team_id']} | {team['status']} | "
            + (", ".join(names) or "chưa có trợ lý"))


def _new_agent(ops, root, spec: dict) -> str:
    name = _s(spec.get("name"))
    if not name:
        raise _Fail("ERROR: trợ lý mới cần name.")
    role = _s(spec.get("role")) or name
    return ops.deps.admin.create_agent(root, name, role, _s(spec.get("prompt")), model=_s(spec.get("model")),
                                       model_provider=_s(spec.get("model_provider")), tags=spec.get("tags") or None)


def _do(op: str, args: dict, root: str, turn=None) -> str:
    ops = _ops()
    if op == "list":
        if not ops.api.exists():
            return "Brain này chưa có nhóm nào."
        teams = ops.api.teams().list_teams(root, limit=_LIST_MAX, include_archived=bool(args.get("include_archived")))
        models = _agent_models(root)
        return ("Nhóm của brain này:\n" + "\n".join(_team_line(ops, t, models) for t in teams)) if teams \
            else "Brain này chưa có nhóm nào (hoặc chỉ có nhóm đã lưu trữ: thêm include_archived=true)."
    if op == "list_agents":
        models = _agent_models(root)
        rows = _agents(ops, root)
        if not rows:
            return "Brain này chưa có trợ lý nào. Dùng op=create_agent để tạo."
        return "Trợ lý của brain này (slug | tên | vai | model riêng):\n" + "\n".join(
            f"- {a['slug']} | {a.get('name') or a['slug']} | {a.get('title') or ''} | "
            + (models.get(a["slug"], ("", ""))[0] or "model chính") for a in rows[:80])
    if op == "get":
        team = _find_team(ops, root, args.get("team"))
        return _team_line(ops, team, _agent_models(root)) + (f"\nMô tả: {team['description']}" if team.get("description")
                                                             else "")
    if op == "create":
        created = [_new_agent(ops, root, a) for a in (args.get("new_agents") or []) if isinstance(a, dict)]
        members = [_s(m) for m in (args.get("members") or []) if _s(m)] + created
        leader = _s(args.get("leader"))
        if leader and leader not in members:
            # Trưởng nhóm có thể là TÊN trợ lý (kể cả trợ lý vừa tạo): đổi về slug thật nếu khớp đúng một trợ lý.
            hits = [a["slug"] for a in _agents(ops, root) if _s(a.get("name")).lower() == leader.lower()]
            leader = hits[0] if len(hits) == 1 else leader
        got = ops.create(root, root, args.get("name"), members, leader, _s(args.get("description")),
                         _s(args.get("client_req_id")))
        team = got["team"]
        head = "Nhóm này đã có từ trước (cùng mã yêu cầu), không tạo thêm." if got["duplicate"] else "Đã tạo nhóm."
        extra = f" Trợ lý mới tạo: {', '.join(created)}." if created else ""
        return (f"{head}{extra}\n{_team_line(ops, team, _agent_models(root))}\n"
                "Chủ mở trang Nhóm để nhắn vào nhóm.")
    if op == "create_agent":
        slug = _new_agent(ops, root, args)
        msg = f"Đã tạo trợ lý '{slug}'" + (f" với model {_s(args.get('model'))}" if _s(args.get("model")) else "") + "."
        if _s(args.get("team")):
            team = _find_team(ops, root, args.get("team"))
            ops.add_member(root, team["team_id"], slug)
            msg += f" Đã thêm vào nhóm {team['name']}."
            if args.get("leader"):
                ops.set_leader(root, team["team_id"], ops.member_key(team, slug))
                msg += " Trợ lý này là trưởng nhóm."
        return msg
    if op == "set_agent_model":
        slug = _s(args.get("slug"))
        if not slug:
            return "ERROR: thiếu slug của trợ lý."
        prov = _s(args.get("model_provider"))
        if prov and prov not in ops.deps.admin.providers():
            return "ERROR: model_provider không hợp lệ. Chọn một trong: " + ", ".join(ops.deps.admin.providers())
        try:
            r = ops.deps.admin.set_model(root, slug, _s(args.get("model")), prov)
        except FileNotFoundError:
            return f"ERROR: không có trợ lý '{slug}'. Dùng op=list_agents để xem."
        return f"Đã đặt model của '{slug}': " + (r["model"] or "dùng model chính") + (
            f" ({r['model_provider']})" if r["model_provider"] else "") + "."

    if op == "dispatch":
        # Danh tính kiểm TRƯỚC khi tra nhóm: lượt không phải của chủ thì không biết gì thêm về nhóm.
        turn = team_dispatch.check_caller(turn)
    team = _find_team(ops, root, args.get("team"))
    tid = team["team_id"]
    if op == "dispatch":
        return _dispatch(ops, root, team, args, turn)
    if op == "job":
        return _job(ops, team, args)
    if op == "update":
        fields = {k: args.get(k) for k in ("name", "description") if args.get(k) is not None}
        if not fields:
            return "ERROR: op=update cần name hay description mới."
        t = ops.update(root, tid, **fields)
        return "Đã sửa nhóm.\n" + _team_line(ops, t)
    if op == "archive":
        ops.update(root, tid, status="archived")
        return f"Đã lưu trữ nhóm {team['name']}: việc đang chờ của nhóm đã huỷ. Muốn mở lại dùng op=unarchive."
    if op == "unarchive":
        ops.update(root, tid, status="active")
        return f"Đã mở lại nhóm {team['name']}."
    if op == "delete":
        if args.get("confirm") is not True:
            return ("ERROR: xoá nhóm không hoàn tác được. Chỉ gọi lại với confirm=true khi chủ đã nói rõ là xoá nhóm "
                    f"'{team['name']}'.")
        if team["status"] != "archived":
            return (f"ERROR: nhóm '{team['name']}' chưa lưu trữ. Lưu trữ trước (op=archive), rồi mới xoá được.")
        ops.delete(root, tid)
        return f"Đã xoá hẳn nhóm {team['name']} cùng cuộc trò chuyện của nhóm."
    if op == "add_member":
        slug = _s(args.get("slug"))
        if not slug:
            return "ERROR: thiếu slug của trợ lý cần thêm."
        return "Đã thêm thành viên.\n" + _team_line(ops, ops.add_member(root, tid, slug))
    if op == "remove_member":
        key = ops.member_key(team, args.get("member") or args.get("slug"))
        return "Đã bỏ thành viên.\n" + _team_line(ops, ops.remove_member(root, tid, key))
    if op == "set_leader":
        who = args.get("member") or args.get("slug")
        key = ops.member_key(team, who) if _s(who) else None
        return ("Đã đổi trưởng nhóm.\n" if key else "Đã bỏ trưởng nhóm.\n") + _team_line(ops, ops.set_leader(root, tid, key))
    return "ERROR: op không hợp lệ."


async def _run(args, ctx) -> str:
    args = args or {}
    op = _s(args.get("op")).lower()
    if op not in _OPS:
        return "ERROR: op phải là một trong: " + ", ".join(_OPS) + "."
    if not ctx.vault_root:
        return ("ERROR: chưa biết đang làm việc trên brain nào nên không thao tác nhóm được. "
                "Làm ở trang Nhóm trên dashboard, ở đó brain đã xác định rõ.")
    try:
        root = _ops().root(str(ctx.vault_root))
        # Lượt đang chạy đọc Ở ĐÂY (luồng của lượt), không trong luồng phụ: danh tính người giao việc (op=dispatch).
        turn = turn_context.current() if turn_context is not None else None
        return await asyncio.to_thread(_do, op, args, root, turn)
    except _Fail as ex:
        return str(ex)
    except Exception as ex:  # noqa: BLE001 - lỗi kho/luật trả về chữ cho model, không làm hỏng lượt
        return _err_text(ex)


def register(ctx):
    ctx.register_tool(
        "javis_team",
        "Quản lý nhóm chat của brain: tạo, sửa, lưu trữ, xoá nhóm; thêm, bỏ trợ lý; chọn trưởng nhóm; tạo trợ lý mới "
        "(có thể đặt model riêng) rồi ghép vào nhóm. Dùng khi NGƯỜI DÙNG muốn có hay đổi một nhóm; đừng tự lập nhóm khi họ "
        "chưa nhờ. "
        "op=list (nhóm của brain), list_agents (trợ lý và model riêng), get (team). "
        "op=create: name, members (slug trợ lý có sẵn), new_agents (trợ lý cần tạo mới: [{name, role, prompt, model, "
        "model_provider}]), leader (slug hay tên), description. Một lần gọi tạo đủ trợ lý rồi lập nhóm. "
        "op=create_agent: name, role, prompt, model, model_provider; thêm team để ghép luôn vào nhóm, leader=true để làm "
        "trưởng nhóm. op=set_agent_model: slug, model (rỗng = model chính), model_provider. "
        "op=update: team + name/description. op=archive / unarchive: team. "
        "op=delete: chỉ nhóm ĐÃ lưu trữ, và chỉ kèm confirm=true khi chủ nói rõ là xoá (không hoàn tác). "
        "op=add_member: team + slug. op=remove_member / set_leader: team + member (slug). "
        "op=dispatch: GIAO MỘT VIỆC cho nhóm có sẵn khi chủ nhờ nhóm làm: team + objective (việc cần làm, đủ ý), "
        "assignee (slug thành viên, bỏ trống thì trưởng nhóm điều phối), request_id (mã đối chiếu nếu có; gọi lại cùng "
        "mã không tạo việc thứ hai). Kết quả TỰ báo về khung chat đang hỏi khi xong, bị chặn hay cần chủ quyết. "
        "op=job: team + task (mã việc hay mã đối chiếu) -> trạng thái, kết quả, nghiệm thu (XONG khác ĐẠT). "
        "team nhận mã nhóm hay tên nhóm. Model riêng: model là tên model (vd sonnet, haiku, opus, gpt-5.5), "
        "model_provider là nhà chạy (anthropic-cli, openai-oauth, openrouter, ...); bỏ trống provider thì Javis tự suy.",
        _run,
        schema={
            "type": "object",
            "properties": {
                "op": {"type": "string", "enum": list(_OPS)},
                "team": {"type": "string", "description": "Mã nhóm (tm_...) hay tên nhóm"},
                "name": {"type": "string", "description": "Tên nhóm (create/update) hay tên trợ lý (create_agent)"},
                "description": {"type": "string"},
                "members": {"type": "array", "items": {"type": "string"}, "description": "Slug trợ lý có sẵn"},
                "new_agents": {"type": "array", "items": {"type": "object", "properties": {
                    "name": {"type": "string"}, "role": {"type": "string"}, "prompt": {"type": "string"},
                    "model": {"type": "string"}, "model_provider": {"type": "string"}}}},
                "leader": {"description": "create: slug hay tên trưởng nhóm; create_agent: true để làm trưởng nhóm"},
                "slug": {"type": "string", "description": "Slug trợ lý (add_member, set_agent_model)"},
                "member": {"type": "string", "description": "Slug hay mã của thành viên (remove_member, set_leader)"},
                "role": {"type": "string"},
                "prompt": {"type": "string"},
                "model": {"type": "string"},
                "model_provider": {"type": "string"},
                "include_archived": {"type": "boolean"},
                "confirm": {"type": "boolean", "description": "Chỉ true khi chủ nói rõ là xoá nhóm"},
                "client_req_id": {"type": "string"},
                "objective": {"type": "string", "description": "dispatch: việc giao cho nhóm"},
                "assignee": {"type": "string", "description": "dispatch: slug thành viên nhận việc (tuỳ chọn)"},
                "request_id": {"type": "string", "description": "dispatch/job: mã đối chiếu chống giao trùng"},
                "task": {"type": "string", "description": "job: mã việc (t_...) hay mã đối chiếu"},
            },
            "required": ["op"],
        },
        min_mode="safe",
        emoji="👥",
    )
