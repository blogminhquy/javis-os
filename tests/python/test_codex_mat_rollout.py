"""Chat Codex cũ mất rollout cục bộ thì dựng lại ngữ cảnh từ lịch sử, không báo lỗi mãi (0.88.2, issue #595).

    python tests/run.py codex_mat_rollout      (KHÔNG mạng, Codex giả)

@dev23072005 báo 09/10/2026: chuyển máy/VPS xong, chat Codex cũ lỗi mãi với

    thread/resume failed: no rollout found for thread id <id> (code -32600)

trong khi chat mới cùng model chạy tốt. Hai chỗ hở, cả hai đều đúng như issue chỉ ra:
  1. `_looks_like_codex_resume_error` trả False cho câu này (nó tìm "not found", "failed to
     resume", mà câu là "no rollout found", "resume failed").
  2. Lỗi chỉ có trên stderr (Codex thoát trước khi phát sự kiện JSON nào) đi thẳng thành `error`
     không có cờ `resume_failed`, nên caller không kích hoạt dựng lại từ lịch sử SQLite.

Điều được ghim (đúng các ca issue đề nghị):
  - câu lỗi của issue, cả qua stderr lẫn sự kiện JSON, được gắn `resume_failed`;
  - chỉ khi lượt này THẬT SỰ resume (có thread cũ), chat mới thì không;
  - lỗi đăng nhập, hạn mức, mạng, model không bị coi là mất rollout (tránh chạy lại vô ích).
  Việc dựng lại đúng một lần nằm ở caller (`_consume_codex`, `_nuot_codex`): lượt dựng lại không
  còn thread cũ nên không thể lặp.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import json
import sys
import tempfile

from claude_cli import CodexCLI, _looks_like_codex_resume_error

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

_fails = []


def check(name, cond, detail=""):
    print(("ok   " if cond else "FAIL ") + name + ("" if cond else f"  [{detail!r}]"))
    if not cond:
        _fails.append(name)


ISSUE = "thread/resume failed: no rollout found for thread id 0199-abc (code -32600)"

# ---- 1. Bộ nhận diện ----
check("câu lỗi của issue là mất rollout", _looks_like_codex_resume_error(ISSUE))
check("mẫu cũ vẫn nhận", _looks_like_codex_resume_error("Failed to resume: thread not found"))
for khac in ("Authentication token expired",
             "401 Unauthorized: please log in again before resuming the thread",
             "You've hit your usage limit. Try again later (session 3)",
             "stream error: network connection lost while loading thread",
             "model gpt-9 not found",
             "Codex lỗi (exit 1):\nerror: unexpected argument '--foo' found"):
    check(f"không coi là mất rollout: {khac[:50]!r}", not _looks_like_codex_resume_error(khac))


# ---- 2. Qua CodexCLI với tiến trình giả ----
def chay(stderr_text, session_id, stdout_events=()):
    lines = ["import json, sys"]
    lines += [f"print(json.dumps({json.dumps(ev)}), flush=True)" for ev in stdout_events]
    lines += [f"sys.stderr.write({json.dumps(stderr_text + chr(10))})", "sys.exit(1)"]
    cli = CodexCLI(cwd=tempfile.gettempdir())
    cli.session_id = session_id
    cli.cli_path = sys.executable
    cli._build_args = lambda: [sys.executable, "-c", "\n".join(lines)]

    async def gom():
        return [e async for e in cli.query("tiếp tục")]
    return [e for e in asyncio.run(gom()) if e.get("type") == "error"]


loi = chay(ISSUE, "0199-abc")
check("stderr-only: lỗi mất rollout gắn resume_failed", len(loi) == 1 and loi[0].get("resume_failed") is True, loi)
check("stderr-only: vẫn giữ câu lỗi gốc để chẩn đoán", bool(loi) and "no rollout found" in loi[0]["content"])

loi = chay(ISSUE, None)
check("chat mới (không resume) thì không gắn cờ", len(loi) == 1 and not loi[0].get("resume_failed"), loi)

loi = chay("Error: 401 Unauthorized. Please log in.", "0199-abc")
check("stderr-only: lỗi đăng nhập không gắn cờ", len(loi) >= 1 and not any(e.get("resume_failed") for e in loi), loi)

loi = chay("", "0199-abc", stdout_events=[{"type": "error", "message": ISSUE}])
check("sự kiện JSON: lỗi mất rollout gắn resume_failed", any(e.get("resume_failed") for e in loi), loi)

print()
if _fails:
    print(f"ĐỎ {len(_fails)} mục: " + ", ".join(_fails))
    sys.exit(1)
print("Tất cả xanh.")
