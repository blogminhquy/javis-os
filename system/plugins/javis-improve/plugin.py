"""Bundled plugin: tool `javis_improve`, improvement on the owner's request (2026-11-15).

Owner: "khi anh yêu cầu nó cải tiến thì nó cũng có thể thay đổi được chính nó và cải tiến toàn bộ hệ thống được",
scope chosen: everything in the brain and Javis's own source code. The work is in `server/self_upgrade.py`.

Ops:
- status: what can be improved here (paths of the brain, this assistant's own file), recent changes, Javis's source
  repo (GitHub connected, attached to this chat), current and latest version.
- save path content|edits reason: write one file of the brain (agents, skills, workflows, Javis/loops, memory, the
  brain's CLAUDE.md) with a backup; returns the change id and a short diff.
- undo id: put a change back. history: recent changes.
- source: attach Javis's own repo to this chat (GitHub in chat does the checks, PR, CI and merge after the turn). Only
  on an install that can push to it; anywhere else nothing is attached and the answer asks for op=report.
- report title body: a link opening a prefilled issue on Javis's repo, for an install that cannot push. Nothing is
  sent: the person reads it and presses Submit (owner, 20/11/2026: keep users' fixes coming, without the failed push).
- update: read only. Says whether a newer release exists and sends the owner to the Update page to press Update
  there. It never starts an update (owner, 23/11/2026: no self-update, the person updates from the Update page).

Only a turn the owner started may save, undo or attach the source (`self_upgrade.owner_turn`): the owner's own
chat, or a Kanban job or reminder they set up. Auto's wake-ups and customer bots get a refusal and may only suggest.
Owner only: `mcp_hub.OWNER_ONLY_TOOLS` lists it, so a customer-facing bot never sees it.
"""
from __future__ import annotations

import asyncio
import time

import self_upgrade as SU

OPS = ("status", "save", "undo", "history", "source", "report", "update")
_REFUSE = ("ERROR: chỉ làm khi CHỦ yêu cầu trực tiếp (chat của chủ, hay việc Kanban hoặc nhắc hẹn chủ đã giao). Lượt tự "
           "thức của Auto và bot nói với khách không tự sửa chính nó hay hệ thống: hãy đề xuất cho chủ trong tin nhắn.")


def _turn() -> dict:
    try:
        import turn_context
        return turn_context.current() or {}
    except Exception:  # noqa: BLE001
        return {}


def _sid(args, ctx, turn) -> str:
    sid = str(turn.get("session_id") or "").strip()
    if sid:
        return sid
    cid = str((args or {}).get("chat_id") or "").strip() or str(turn.get("chat_id") or "").strip()
    if not cid:
        try:
            import luot_dang_chay
            cid = luot_dang_chay.doan_chat_id(getattr(ctx, "vault_root", "") or "") or ""
        except Exception:  # noqa: BLE001
            cid = ""
    return cid[len("web:"):] if cid.startswith("web:") else ""


def _actor(turn) -> str:
    agent = (turn.get("agent") or {}) if isinstance(turn.get("agent"), dict) else {}
    bits = [str(turn.get("kenh") or "?")]
    if agent.get("slug"):
        bits.append(f"agent:{agent['slug']}")
    return " ".join(bits)


def _when(ts) -> str:
    try:
        import localefmt
        return localefmt.format_ts(float(ts), "%d/%m %H:%M")
    except Exception:  # noqa: BLE001
        return time.strftime("%d/%m %H:%M", time.localtime(float(ts or 0)))


def _line(c: dict) -> str:
    tail = []
    if c.get("undo_of"):
        tail.append(f"hoàn tác #{c['undo_of']}")
    elif c.get("created"):
        tail.append("tạo mới")
    if c.get("undone_by"):
        tail.append(f"đã hoàn tác bởi #{c['undone_by']}")
    if c.get("reason") and not c.get("undo_of"):
        tail.append(c["reason"])
    return (f"#{c['id']} {_when(c.get('at'))} {c['path']} (+{c.get('added', 0)}/-{c.get('removed', 0)})"
            + (" · " + " · ".join(tail) if tail else ""))


async def _status(args, ctx, turn) -> str:
    root = getattr(ctx, "vault_root", "") or ""
    lines = [f"Brain: {root}",
             "Sửa được (op=save, có sao lưu và op=undo): agents/<slug>.md, skills/<slug>/..., workflows/<slug>.md, "
             "Javis/loops/<slug>.md, memory/... và CLAUDE.md của brain. Núm việc nền và tự học: javis_tune. "
             "Plugin: javis_plugin."]
    agent = turn.get("agent") if isinstance(turn.get("agent"), dict) else None
    if agent and agent.get("slug"):
        lines.append(f"File của chính bạn: agents/{agent['slug']}.md (bộ nhớ: memory/agents/{agent['slug']}/MEMORY.md)")
    hist = SU.history(root, 5) if root else []
    if hist:
        lines.append("Thay đổi gần đây:")
        lines += ["  " + _line(c) for c in hist]
    cur, latest = await SU.versions()
    if cur or latest:
        lines.append(f"Phiên bản: đang chạy v{cur or '?'}, mới nhất v{latest or '?'}")
    try:
        src = await asyncio.to_thread(SU.source_status, _sid(args, ctx, turn), root)
        if not src["connected"]:
            lines.append(f"Javis's code ({SU.SOURCE_REPO}): GitHub not connected. To fix Javis itself, send the "
                         "developer a bug report with op=report (needs no connection).")
        elif src["attached"]:
            a = src["attached"]
            lines.append(f"Mã nguồn Javis đã gắn vào chat này: {a.get('worktree') or a.get('clone')} "
                         f"(nhánh {a.get('branch') or '?'}).")
        elif src.get("can_write"):
            lines.append(f"Mã nguồn Javis ({SU.SOURCE_REPO}): GitHub đã kết nối, chưa gắn vào chat này (op=source).")
        else:
            lines.append(f"Javis's code ({SU.SOURCE_REPO}): this install cannot write to it. To fix Javis itself, "
                         "send the developer a bug report with op=report, do not edit code here.")
    except Exception as ex:  # noqa: BLE001 - status never fails because GitHub is unreachable
        lines.append(f"Mã nguồn Javis: chưa đọc được trạng thái GitHub ({type(ex).__name__}).")
    return "\n".join(lines)


def _update_text(out: dict) -> str:
    cur, latest = out.get("current") or "?", out.get("latest") or "?"
    page = "Cài đặt → Cập nhật (Settings → Updates)"
    if not out.get("latest"):
        head = f"Đang chạy v{cur}. Chưa đọc được bản mới nhất trên GitHub."
    elif out.get("newer"):
        head = f"Đang chạy v{cur}, đã có bản mới v{latest}."
    else:
        head = (f"Đang chạy bản mới nhất v{cur}. Thay đổi vừa merge thường thành bản phát hành vài phút sau, image "
                "Docker thêm 2 đến 5 phút.")
    return (head + f" KHÔNG có gì được cập nhật: Javis không tự cập nhật. Nói với chủ vào {page} và tự bấm nút "
            "Cập nhật ở đó khi muốn lên bản mới. Đừng nói là đã hẹn hay đang cập nhật.")


async def _run(args, ctx) -> str:
    args = args or {}
    op = str(args.get("op") or "").strip().lower()
    turn = _turn()
    root = getattr(ctx, "vault_root", "") or ""
    if op == "status":
        return await _status(args, ctx, turn)
    if op == "history":
        rows = SU.history(root, int(args.get("limit") or 10)) if root else []
        return "\n".join(_line(c) for c in rows) if rows else "Chưa có thay đổi nào qua javis_improve."
    if op not in OPS:
        return "ERROR: op phải là " + ", ".join(OPS) + "."
    if op == "update":   # reads the versions, starts nothing: no owner check needed
        out = await SU.update_hint()
        return _update_text(out)
    if op == "report":   # builds a link, sends nothing: no owner check needed
        try:
            cur, _latest = await SU.versions()
            url = SU.report_url(str(args.get("title") or ""), str(args.get("body") or ""), cur)
        except SU.ImproveError as e:
            return f"ERROR: {e}"
        return ("Link to a prefilled issue on Javis's repo (nothing has been sent):\n" + url + "\n"
                "Give the person this link as is and tell them plainly: open it, check the text, press Submit; "
                "a GitHub account is all they need. Do not say it was sent.")
    if not SU.owner_turn(turn):
        return _REFUSE
    try:
        if op == "save":
            out = await asyncio.to_thread(
                SU.save, root, str(args.get("path") or ""), content=args.get("content"), edits=args.get("edits"),
                reason=str(args.get("reason") or ""), actor=_actor(turn))
            if out.get("unchanged"):
                return f"{out['path']}: nội dung không đổi, không ghi gì."
            msg = (f"Đã lưu {out['path']} (thay đổi #{out['id']}, +{out['added']}/-{out['removed']} dòng"
                   f"{', tạo mới' if out.get('created') else ''}). Hoàn tác: javis_improve op=undo id={out['id']}.\n"
                   + (out.get("note", "") + "\n" if out.get("note") else "")
                   + (out.get("diff") or ""))
            return msg + ("\nBáo chủ ngắn gọn đã đổi gì, vì sao, và mã #" + str(out["id"]) + " để hoàn tác.")
        if op == "undo":
            out = await asyncio.to_thread(SU.undo, root, args.get("id"), actor=_actor(turn))
            what = "xoá file đã tạo" if out.get("removed_file") else "khôi phục bản trước"
            return (f"Đã hoàn tác #{out['undo_of']} ({what}) ở {out['path']}, ghi thành thay đổi #{out['id']}."
                    + ("\n" + out["note"] if out.get("note") else ""))
        if op == "source":
            sid = _sid(args, ctx, turn)
            got = await asyncio.to_thread(SU.attach_source, sid, root)
            if got.get("report"):
                return (f"Not attached: this install cannot write to {SU.SOURCE_REPO}, only its developer can, so "
                        "do NOT edit Javis's code here (it could never be sent). Turn the request into a report for "
                        "the developer instead: find the cause if you can (the code installed on this machine, or "
                        "the public repo), then call javis_improve op=report with title (one line) and body (what "
                        "happens, steps to reproduce, what was expected, likely cause with file paths, suggested fix; "
                        "a diff only if short). Hand the person the link it returns.")
            a = got["attached"]
            return "\n".join(x for x in [
                f"Đã gắn mã nguồn Javis ({SU.SOURCE_REPO}) vào chat này.",
                f"Thư mục làm việc: {a.get('worktree') or a.get('clone')} (nhánh {a.get('branch') or '?'}, gốc "
                f"{a.get('base_branch') or 'main'}).",
                got.get("note") or "",
                "Trước khi sửa: đọc CLAUDE.md và docs/quy-uoc-dev.md trong thư mục đó. Mỗi PR thêm đúng một file "
                "changelog.d/<slug>.md, không sửa VERSION hay CHANGELOG. Sửa nhỏ, có test.",
                "Hết lượt có sửa code, Javis TỰ kiểm tra ở máy, đẩy, mở PR, theo dõi CI và merge khi xanh (xem "
                "javis_github op=status). Workflow Release ra số phiên bản mới sau merge. Máy này KHÔNG tự lên bản "
                "mới: nói với chủ khi có bản mới thì vào Cài đặt → Cập nhật và bấm Cập nhật. Đừng hứa tự báo lại.",
            ] if x)
    except SU.ImproveError as e:
        return f"ERROR: {e}"
    return "ERROR: op không hợp lệ."


def register(ctx):
    ctx.register_tool(
        "javis_improve",
        "Improve on the OWNER'S REQUEST (the owner asks to improve you, an assistant, a skill, a workflow or Javis "
        "itself). op=status: what can be changed here, your own file, recent changes, Javis's code, versions. "
        "op=save {path, content | edits:[{old,new}], reason}: write ONE file of the brain (agents/, skills/, "
        "workflows/, Javis/loops/, memory/, the brain's CLAUDE.md) with a backup; returns a change id and a diff. "
        "Changing your own role, instructions, skills or model means editing your agents/<slug>.md. "
        "op=undo {id}: put a change back. op=history: recent changes. "
        "op=source: attach Javis's own code to this chat to fix it; after the turn Javis checks, opens a PR and "
        "merges on green CI. Only an install that can push to Javis's repo gets it; elsewhere use op=report. "
        "op=report {title, body}: a link to a prefilled issue for Javis's developer (bug or fix proposal); nothing "
        "is sent until the person presses Submit. "
        "op=update: read only, says whether a newer release exists; it never updates. Only the owner updates, by "
        "pressing Update on the Settings, Updates page, so point them there. "
        "Changes only on the owner's word; Auto's wake-ups and customer bots only suggest. After a change, tell the "
        "owner what changed and the undo id.",
        _run,
        schema={
            "type": "object",
            "properties": {
                "op": {"type": "string", "enum": list(OPS)},
                "path": {"type": "string", "description": "đường dẫn trong brain, vd agents/tro-ly-chay-bo.md"},
                "content": {"type": "string", "description": "toàn bộ nội dung mới của file (op=save)"},
                "edits": {"type": "array", "description": "thay từng đoạn (op=save), mỗi đoạn old xuất hiện đúng 1 lần",
                          "items": {"type": "object", "properties": {"old": {"type": "string"},
                                                                      "new": {"type": "string"}}}},
                "reason": {"type": "string", "description": "vì sao sửa, một câu"},
                "id": {"type": "integer", "description": "mã thay đổi (op=undo)"},
                "limit": {"type": "integer", "description": "số dòng (op=history)"},
                "chat_id": {"type": "string", "description": "khung chat dạng web:<mã phiên>; bỏ trống để tự nhận"},
                "title": {"type": "string", "description": "one line saying what the bug or proposal is (op=report)"},
                "body": {"type": "string", "description": "what happens, steps, expected, likely cause, suggested "
                                                          "fix (op=report)"},
            },
            "required": ["op"],
        },
        # Reading what can be improved runs anywhere; changing brain files needs `safe` (they are files of the brain);
        # attaching the source repo reaches outside the brain, so only at Full access. A report only builds a link the
        # person submits themselves, and update only reads the versions, so both run anywhere.
        min_mode="readonly",
        op_modes={"status": "readonly", "history": "readonly", "save": "safe", "undo": "safe", "source": "full",
                  "report": "readonly", "update": "readonly"},
        emoji="🛠️",
    )
