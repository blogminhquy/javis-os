"""Bundled plugin: tool `javis_github` (GitHub inside chat, docs/dev/2026-10-github-trong-chat-spec.md, section 11.2).

Why a tool: pushing, opening the PR, following CI and merging are done by the server (github_work) after each turn, with
no model involved (spec 4.1: the model never pushes or merges). What the server cannot guess is what the person wants
done NEXT, after this PR is merged. `op=next` records that, and the server starts it as a new turn of this chat once
every PR of the chat is merged and the checks after the merge passed. CI green alone never creates new work.

Ops:
- status: the chat's repos, branch, PR, CI, merge state, stuck reason, and the queued next jobs.
- next text=...: queue a job the person asked for, to run after the merge. Only what the person asked, never a plan of
  your own.
- cancel id=...: drop a queued job.
- review [repo] [provider]: a person asked for a cross review of the chat's PR now. Runs in the background, findings
  reach the chat; the merge waits for it. Default reviewer: the chat's own engine and model.
- review_skip [repo]: the person chose to skip the open findings; merges when CI is green.
"""
from __future__ import annotations

try:
    import luot_dang_chay
except Exception:
    luot_dang_chay = None


def _sid(args, ctx) -> str:
    cid = str((args or {}).get("chat_id") or "").strip()
    if not cid and luot_dang_chay is not None and ctx.vault_root:
        try:
            cid = luot_dang_chay.doan_chat_id(ctx.vault_root) or ""
        except Exception:
            cid = ""
    return cid[len("web:"):] if cid.startswith("web:") else ""


_CI = {"none": "chưa đẩy", "pending": "chờ CI", "running": "CI đang chạy", "green": "CI xanh", "red": "CI đỏ",
       "no_ci": "repo không có CI", "cancelled": "CI bị huỷ"}
_INTEG = {"no_pr": "chưa có PR", "pr_open": "PR đang mở", "ready": "sẵn sàng merge", "merged": "đã merge",
          "conflict": "xung đột", "merge_failed": "merge hỏng"}


def _status(sid: str) -> str:
    import github_work
    s = github_work.session_state(sid)
    if not s["repos"]:
        return "Khung chat này chưa có việc GitHub nào (chưa đẩy lên lần nào)."
    lines = []
    for r in s["repos"]:
        # A merged PR's leftover "pending" CI mark is not news (merged while Javis was cut off from GitHub).
        ci = "" if r["integ"] == "merged" and r["ci"] in ("pending", "running") else _CI.get(r["ci"], r["ci"])
        bits = [r["full_name"], r.get("branch") or "", ci, _INTEG.get(r["integ"], r["integ"])]
        if r.get("pr_url"):
            bits.append(r["pr_url"])
        if r.get("post_merge") == "red":
            bits.append("kiểm tra sau merge ĐỎ")
        if r.get("stuck_reason"):
            bits.append("kẹt: " + r["stuck_reason"])
        if r.get("reviewing"):
            bits.append("đang review chéo")
        lines.append(" · ".join(b for b in bits if b))
        for f in r.get("review_open") or []:
            lines.append(f"  phát hiện review chờ người dùng quyết: {f.get('file')}:{f.get('line')} {f.get('problem')}")
    for q in s.get("queue") or []:
        lines.append(f"việc kế tiếp #{q['id']}: {q['text']}")
    return "\n".join(lines)


def _chay(args, ctx) -> str:
    op = str((args or {}).get("op") or "").strip().lower()
    sid = _sid(args, ctx)
    if not sid:
        return ("ERROR: chỉ dùng được trong khung chat web có gắn repo GitHub. Truyền chat_id dạng web:<mã phiên> "
                "lấy từ khối KÊNH HỘI THOẠI HIỆN TẠI.")
    import github_work
    if op == "status":
        return _status(sid)
    if op == "next":
        text = str((args or {}).get("text") or "").strip()
        if not text:
            return "ERROR: thiếu text - việc kế tiếp người dùng đã giao."
        try:
            out = github_work.queue_next(sid, text)
        except ValueError as e:
            return f"ERROR: {e}"
        return (f"Đã xếp việc kế tiếp #{out['id']}. Khi mọi PR của khung chat này đã merge và kiểm tra sau merge "
                "qua, Javis tự mở một lượt mới để làm việc này. Nói với người dùng đúng như vậy, đừng hứa tự báo.")
    if op in ("review", "review_skip"):
        repo = _repo(sid, str((args or {}).get("repo") or "").strip())
        if repo.startswith("ERROR"):
            return repo
        if op == "review":
            return _review(sid, repo, str((args or {}).get("provider") or "").strip())
        return _skip(sid, repo)
    if op == "cancel":
        try:
            out = github_work.cancel_next(sid, int((args or {}).get("id") or 0))
        except (TypeError, ValueError):
            return "ERROR: id phải là số (xem op=status)."
        return "Đã bỏ việc kế tiếp." if out["cancelled"] else "Không có việc kế tiếp đang chờ mang mã đó."
    return "ERROR: op phải là status, next, cancel, review hoặc review_skip."


def _repo(sid: str, name: str) -> str:
    import github_work
    rows = [r for r in github_work.session_state(sid)["repos"] if r.get("pr_number") and r.get("integ") != "merged"]
    if name:
        hit = [r["full_name"] for r in rows if r["full_name"].lower() == name.lower()
               or r["full_name"].split("/")[-1].lower() == name.lower()]
        return hit[0] if hit else f"ERROR: khung chat này không có PR đang mở cho repo {name}."
    if len(rows) == 1:
        return rows[0]["full_name"]
    if not rows:
        return "ERROR: khung chat này chưa có PR nào đang mở để review."
    return "ERROR: có nhiều PR đang mở, hỏi lại người dùng repo nào: " + ", ".join(r["full_name"] for r in rows)


async def _review(sid: str, repo: str, provider: str) -> str:
    # Returned as a coroutine: the host awaits it on the event loop, where the review task can be started.
    import github_repos
    import github_work
    try:
        out = github_work.review_now(sid, repo, provider)
    except github_repos.RepoError as e:
        return f"ERROR: {e}"
    return (f"Đã bắt đầu review chéo {repo} bằng {out['reviewer']}. Chạy nền, kết quả tự hiện trong khung chat này, "
            "Javis chưa merge cho tới khi có kết quả. Nói với người dùng đúng như vậy, đừng hứa tự báo.")


async def _skip(sid: str, repo: str) -> str:
    import github_repos
    import github_work
    try:
        out = await github_work.review_skip(sid, repo)
    except github_repos.RepoError as e:
        return f"ERROR: {e}"
    integ = ((out or {}).get("row") or {}).get("integ")
    return ("Đã bỏ qua các phát hiện và merge." if integ == "merged" else
            "Đã bỏ qua các phát hiện. PR chưa merge (CI chưa xanh hoặc repo chưa cho merge), Javis merge khi đủ điều kiện.")


def register(ctx):
    ctx.register_tool(
        "javis_github",
        "GitHub của khung chat này. Sau mỗi lượt có sửa code, Javis TỰ kiểm tra, commit, đẩy lên, mở PR, theo dõi CI "
        "và merge theo cài đặt của repo, bạn không làm mấy việc đó và không hứa 'xong em báo'. "
        "op=status: trạng thái nhánh, PR, CI, merge, lý do kẹt. op=next text=...: xếp MỘT việc người dùng đã giao để "
        "Javis tự làm khi PR hiện tại đã merge xong (chỉ việc người dùng yêu cầu, không phải kế hoạch bạn tự nghĩ). "
        "op=cancel id=...: bỏ một việc đang chờ. "
        "op=review [repo] [provider]: CHỈ khi người dùng bảo review chéo PR, chạy nền, mặc định bằng chính engine đang "
        "chat. op=review_skip [repo]: người dùng chọn bỏ qua các phát hiện review và merge. Người dùng bảo sửa các "
        "phát hiện thì bạn tự sửa code ngay trong lượt này.",
        _chay,
        schema={
            "type": "object",
            "properties": {
                "op": {"type": "string", "enum": ["status", "next", "cancel", "review", "review_skip"]},
                "repo": {"type": "string", "description": "owner/repo khi khung chat có nhiều PR (op=review, review_skip)"},
                "provider": {"type": "string", "description": "Engine review khi người dùng chỉ định, vd deepseek, groq, gemini, anthropic-cli (op=review)"},
                "text": {"type": "string", "description": "Việc kế tiếp (op=next)"},
                "id": {"type": "integer", "description": "Mã việc kế tiếp (op=cancel)"},
                "chat_id": {"type": "string", "description": "Khung chat dạng web:<mã phiên>; bỏ trống để tự nhận"},
            },
            "required": ["op"],
        },
        min_mode="safe",
        emoji="🐙",
    )
