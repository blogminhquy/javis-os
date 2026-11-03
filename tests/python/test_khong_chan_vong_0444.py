"""0.444.4: slow server work runs off the event loop (VPS users, 2026-11-03: the app froze, Traefik answered 404).

Any handler that does sync file, SQLite, CPU or network work as `async def` stalls every other request, /health
included; three missed health checks and Traefik drops the route. These pin the fixes found by the audit."""
from _paths import ROOT, SERVER  # noqa: E402,F401
import ast
import inspect
import os
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path


def _handler(path: Path, name: str):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    raise AssertionError(f"{name} not found in {path}")


def test_tasks_bots_and_tasks_stats_run_on_a_worker_thread():
    # Plain `def` = FastAPI runs it in its threadpool. `async def` would run job_map / compute on the loop.
    assert isinstance(_handler(SERVER / "bot_jobs.py", "tasks_bots"), ast.FunctionDef)
    assert isinstance(_handler(SERVER / "task_stats.py", "tasks_stats"), ast.FunctionDef)


def _src(path: Path, name: str) -> str:
    return ast.get_source_segment(path.read_text(encoding="utf-8"), _handler(path, name))


def test_github_status_and_optional_tools_leave_the_loop():
    assert "run_in_threadpool(github_repos.status)" in _src(SERVER / "routes" / "github.py", "gh_status")
    assert "to_thread(optional_tools.danh_sach)" in _src(SERVER / "routes" / "tools.py", "tools_list")


def test_minify_and_fingerprints_leave_the_loop():
    main = SERVER / "main.py"
    assert "to_thread(tinh_gon.ban_phuc_vu" in _src(main, "get_response")
    assert "to_thread(_asset_fps, html)" in _src(main, "app_version")
    assert "to_thread(_asset_fps, html)" in _src(main, "root")


def test_github_install_count_failure_is_remembered(monkeypatch):
    import github_repos
    calls = []

    class Boom:
        def __init__(self, tok):
            pass

        def get(self, *a, **k):
            calls.append(1)
            raise github_repos.GitHubError(0, "down")

    monkeypatch.setattr(github_repos, "GitHub", Boom)
    github_repos._INSTALL_CACHE.update(at=0.0, n=-1)
    assert github_repos._installs("t") == -1
    assert github_repos._installs("t") == -1
    assert len(calls) == 1, "a failed lookup must not be repeated on every status call"
    github_repos._INSTALL_CACHE.update(at=0.0, n=-1)


def test_loop_events_reads_only_existing_log_files():
    import task_stats
    with tempfile.TemporaryDirectory() as d:
        folder = Path(d) / "Javis" / "loop-log"
        folder.mkdir(parents=True)
        (folder / "2026-11-01.md").write_text("## [2026-11-01 08:30] tong-hop · loop\nok\n", encoding="utf-8")
        (folder / "2026-11-03.md").write_text("## [2026-11-03 09:15] tong-hop · loop\nLỗi: x\n", encoding="utf-8")
        (folder / "notes.md").write_text("ignored", encoding="utf-8")
        t0 = time.perf_counter()
        end = datetime(2027, 1, 1, tzinfo=timezone.utc).timestamp()
        ev = task_stats.loop_events(d, 0, end, timezone.utc)
        assert time.perf_counter() - t0 < 0.5
        assert [e["status"] for e in sorted(ev, key=lambda e: e["ts"])] == ["ok", "fail"]
        # a window still filters by day
        lo = datetime(2026, 11, 2, tzinfo=timezone.utc).timestamp()
        assert [e["status"] for e in task_stats.loop_events(d, lo, end, timezone.utc)] == ["fail"]


def test_offline_ear_leaves_a_core_and_runs_niced(monkeypatch):
    import local_stt
    monkeypatch.delenv("JAVIS_LOCAL_STT_THREADS", raising=False)
    monkeypatch.setattr(os, "cpu_count", lambda: 2)
    assert local_stt._threads() == 1
    monkeypatch.setattr(os, "cpu_count", lambda: 1)
    assert local_stt._threads() == 1
    monkeypatch.setenv("JAVIS_LOCAL_STT_THREADS", "3")
    assert local_stt._threads() == 3
    assert '"--threads", str(_threads())' in inspect.getsource(local_stt.transcribe)
    worker = (SERVER / "offline_ear" / "worker.py").read_text(encoding="utf-8")
    assert "os.nice(10)" in worker


if __name__ == "__main__":
    import sys
    try:
        import pytest
    except ImportError:
        print("bỏ qua: chưa cài pytest")
        sys.exit(0)
    sys.exit(pytest.main([__file__, "-q"]))
