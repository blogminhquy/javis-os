"""A Codex job whose writes the sandbox refused is an environment problem, not a question for the owner (#1133).

    python tests/run.py kanban_codex_sandbox

The bug: on Windows, Codex quietly ran `--sandbox workspace-write` as `read-only`. A background job at `auto` could not
write its output, the worker stopped with [[NEEDS_INPUT]] about it, and the job sat in "waiting for your answer" where
no answer could help. The sandbox itself is fixed in claude_cli (windows.sandbox, see test_codex_windows_sandbox); this
is the net under it: such a run is blocked as `sandbox`, with what to change, and the owner is not asked anything.

Pinned here:
  1. Codex at auto, the question says the write was refused: blocked as `sandbox`, no question stored, not retried
  2. the same question on another engine, or from Codex at `suggest` (read-only by design): still a question
  3. an ordinary Codex question: still a question
  4. questions that only look alike ("sandbox" of a payment gateway, a view-only Google Sheet): still questions
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
from pathlib import Path

import aux_engine
from tasks import SANDBOX_BLOCK_KIND, TasksDeps, TasksFeature, sandbox_refused


def _atomic(path, text):
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")


async def _workflow(*_args, **_kwargs):
    if False:
        yield {}


def _feature(tmp_path):
    brain = tmp_path / "Brain"
    brain.mkdir(exist_ok=True)

    async def report(chat_id, text, **kw):
        return True

    deps = TasksDeps(
        brain_root=lambda value: str(brain), atomic_write_text=_atomic, execute_workflow=_workflow,
        workflows_dir=lambda b: brain / "workflows", build_system_prompt=lambda b: "system", aux_model=lambda: None,
        safe_tools=["Read", "Write"], state_dir=tmp_path / "state", scheduler_brains=lambda: [str(brain)], report=report,
    )
    return TasksFeature(deps), brain


def _run(feature, brain, result, provider, mode):
    # A distinct title each run: the store folds a second identical job into the first one.
    tid = feature.store.enqueue(feature._ensure(str(brain)), f"Viết báo cáo {provider} {mode}",
                                f"ghi báo cáo {provider} {mode} vào reports/", capability="files", status="ready")

    async def execute(task):
        return result, "", "[[NEEDS_INPUT]]" in result, {"provider": provider, "execution_mode": mode}

    feature._execute = execute
    claimed = feature.store.claim(tid, "w-test")
    assert claimed
    asyncio.run(feature._run_worker(claimed, "w-test"))
    return feature.store.get_task(tid)


REFUSED = ("Đã soạn nội dung báo cáo.\n[[NEEDS_INPUT]] Không ghi được reports/bao-cao.md: sandbox đang read-only "
           "(Access is denied). Anh muốn em lưu ở đâu?")


def test_codex_sandbox_refusal_is_blocked_not_asked(tmp_path):
    feature, brain = _feature(tmp_path)
    task = _run(feature, brain, REFUSED, aux_engine.CODEX, "auto")
    assert task["status"] == "blocked" and task["block_kind"] == SANDBOX_BLOCK_KIND, task
    assert "sandbox" in task["block_reason"] and "config.toml" in task["block_reason"]
    assert not (task.get("metadata") or {}).get("qa"), "no question for the owner is stored"
    feature.store.close()


def test_other_engines_and_suggest_still_ask(tmp_path):
    feature, brain = _feature(tmp_path)
    assert _run(feature, brain, REFUSED, "anthropic-api", "auto")["block_kind"] == "needs_input"
    assert _run(feature, brain, REFUSED, aux_engine.CODEX, "suggest")["block_kind"] == "needs_input"
    feature.store.close()


def test_ordinary_codex_question_still_asks(tmp_path):
    feature, brain = _feature(tmp_path)
    task = _run(feature, brain, "[[NEEDS_INPUT]] Gửi báo cáo cho anh Minh hay chị Lan?", aux_engine.CODEX, "full")
    assert task["block_kind"] == "needs_input", task
    md = {"provider": aux_engine.CODEX, "execution_mode": "full"}
    assert not sandbox_refused(md, "Gửi cho ai?")
    assert sandbox_refused(md, "touch reports/a.md: Read-only file system")
    assert sandbox_refused(md, "Không ghi được file vì sandbox chặn ghi (Access is denied).")
    feature.store.close()


def test_real_questions_that_only_look_alike_still_ask(tmp_path):
    """Review of the first draft: "sandbox" alone or "read-only" alone are real questions for the owner."""
    md = {"provider": aux_engine.CODEX, "execution_mode": "full"}
    assert not sandbox_refused(md, "[[NEEDS_INPUT]] Chạy thử trên sandbox của PayOS hay production luôn?")
    assert not sandbox_refused(md, "[[NEEDS_INPUT]] Google Sheet đang chỉ đọc, anh cấp quyền sửa cho em nhé?")
    assert not sandbox_refused(md, "[[NEEDS_INPUT]] API Google báo permission denied, anh cấp quyền tài khoản dịch vụ?")
    feature, brain = _feature(tmp_path)
    task = _run(feature, brain, "[[NEEDS_INPUT]] Google Sheet đang chỉ đọc, anh cấp quyền sửa cho em nhé?",
                aux_engine.CODEX, "auto")
    assert task["block_kind"] == "needs_input", task
    feature.store.close()


if __name__ == "__main__":
    import sys
    try:
        import pytest
    except ImportError:
        print("bỏ qua: chưa cài pytest")
        sys.exit(0)
    sys.exit(pytest.main([__file__, "-q"]))
