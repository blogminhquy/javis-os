"""Regression test: OpenAI OAuth/Codex giữ đúng ngữ cảnh giữa các lượt.

Chạy:
    python tests/run.py codex_context

Không gọi mạng, không cần đăng nhập ChatGPT/Codex.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401  - nạp server/ vào sys.path (xem tests/python/_paths.py)
import asyncio
import json
import os
import sqlite3
import sys
import tempfile
from pathlib import Path


import compaction  # noqa: E402
from claude_cli import CodexCLI, _looks_like_codex_resume_error  # noqa: E402
from sessions import SessionStore  # noqa: E402


_fails = []


def check(name, cond):
    print(("ok  " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)


with tempfile.TemporaryDirectory(prefix="javis-codex-context-") as tmp:
    tmp_path = Path(tmp)

    # 1) DB cũ tự thêm cột riêng của Codex, không đụng cli_session_id của Claude.
    old_db = tmp_path / "old.db"
    conn = sqlite3.connect(str(old_db))
    conn.executescript("""
    CREATE TABLE sessions (
        id TEXT PRIMARY KEY, title TEXT, brain TEXT NOT NULL DEFAULT 'brain',
        engine TEXT, model TEXT, cli_session_id TEXT,
        created_at REAL NOT NULL, updated_at REAL NOT NULL,
        msg_count INTEGER NOT NULL DEFAULT 0, parent_session_id TEXT,
        archived INTEGER NOT NULL DEFAULT 0
    );
    CREATE TABLE messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
        role TEXT NOT NULL, content TEXT, ts REAL NOT NULL, tool_calls_json TEXT
    );
    """)
    conn.close()
    store = SessionStore(db_path=old_db)
    sid = store.create_session(brain="brain", engine="codex", model="gpt-test")
    store.set_cli_session_id(sid, "claude-session")
    store.set_codex_thread_id(sid, "codex-thread")
    row = store.get_session(sid)
    check("migration: thêm codex_thread_id cho DB cũ", row.get("codex_thread_id") == "codex-thread")
    check("schema: Codex/Claude giữ id riêng", row.get("cli_session_id") == "claude-session")
    store.clear_codex_thread_id(sid)
    check("đổi provider: vô hiệu hóa thread Codex stale",
          store.get_session(sid).get("codex_thread_id") is None)
    store._conn.close()

    # 2) Lượt mới và lượt resume dựng đúng argv theo CLI chính thức.
    cli = CodexCLI(cwd=tmp, model="gpt-test", instructions="Bạn là Javis.")
    cli.cli_path = "codex"
    cli.profile = "javis"
    fresh_args = cli._build_args()
    check("argv: lượt mới không có resume", "resume" not in fresh_args and fresh_args[-1] == "-")
    cli.session_id = "0199a213-81c0-7800-8aa1-bbab2a035a53"
    resume_args = cli._build_args()
    check("argv: resume đúng thread id",
          resume_args[-3:] == ["resume", "0199a213-81c0-7800-8aa1-bbab2a035a53", "-"])
    check("argv: resume vẫn bật JSONL", "--json" in resume_args)

    # 3) Parser bắt thread.started ngay và gắn lại vào final.
    fake_events = [
        {"type": "thread.started", "thread_id": "thread-from-jsonl"},
        {"type": "item.completed", "item": {"type": "agent_message", "text": "Đã nhớ."}},
        {"type": "turn.completed", "usage": {
            "input_tokens": 378930, "cached_input_tokens": 308480, "output_tokens": 3}},
    ]
    script = "import json\n" + "\n".join(
        f"print(json.dumps({json.dumps(ev, ensure_ascii=False)}), flush=True)"
        for ev in fake_events
    )
    parser_cli = CodexCLI(cwd=tmp)
    parser_cli.cli_path = sys.executable
    parser_cli._build_args = lambda: [sys.executable, "-c", script]

    async def collect():
        return [event async for event in parser_cli.query("Câu hiện tại")]

    parsed = asyncio.run(collect())
    check("JSONL: phát session ngay khi thread.started",
          any(e.get("type") == "session" and e.get("session_id") == "thread-from-jsonl"
              for e in parsed))
    final = next((e for e in parsed if e.get("type") == "final"), {})
    check("JSONL: final giữ thread id", final.get("session_id") == "thread-from-jsonl")
    check("JSONL: giữ nội dung assistant", final.get("content") == "Đã nhớ.")
    check("JSONL: input_tokens đã gồm cache, không cộng cached_input_tokens lần nữa",
          final.get("tokens_in") == 378930 and final.get("tokens_out") == 3)

    # 4) Phiên cũ được bootstrap từ SQLite nhưng ưu tiên đoạn gần nhất trong trần context.
    history = [
        {"role": "user", "content": "Tên dự án là Sao Mai."},
        {"role": "assistant", "content": "Tôi đã ghi nhớ tên Sao Mai."},
    ]
    prompt = compaction.codex_bootstrap_prompt(history, "Tên dự án là gì?", max_chars=4000)
    check("bootstrap: có lịch sử hai vai", "<User>" in prompt and "<Javis>" in prompt)
    check("bootstrap: giữ yêu cầu hiện tại", prompt.endswith("Tên dự án là gì?"))
    check("bootstrap: không vượt trần khi current ngắn", len(prompt) <= 4000)

    huge = [{"role": "user", "content": "cũ-" + ("x" * 5000)},
            {"role": "assistant", "content": "mới-" + ("y" * 1200)}]
    clipped = compaction.codex_bootstrap_prompt(huge, "tiếp tục", max_chars=2200)
    check("bootstrap: cắt phần cũ, giữ phần mới", "mới-" in clipped and "phần lịch sử cũ hơn" in clipped)

    # 5) Chỉ fallback khi đúng lỗi mất thread; lỗi auth/model không tự chạy lại.
    check("fallback: nhận diện thread không tồn tại",
          _looks_like_codex_resume_error("Failed to resume: thread not found"))
    check("fallback: không nuốt lỗi auth",
          not _looks_like_codex_resume_error("Authentication token expired"))


if _fails:
    print(f"\n{len(_fails)} test(s) FAILED")
    raise SystemExit(1)
print("\nAll Codex context tests passed.")
