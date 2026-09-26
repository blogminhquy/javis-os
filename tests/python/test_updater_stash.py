"""Real Git regression tests for updater's local-change backup."""
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "server"))
os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-stash-state-")
import updater  # noqa: E402


def git(repo, *args):
    result = subprocess.run(["git", *args], cwd=repo, capture_output=True,
                            text=True, encoding="utf-8", errors="replace")
    assert result.returncode == 0, (args, result.stderr, result.stdout)
    return result.stdout.strip()


with tempfile.TemporaryDirectory(prefix="javis-updater-stash-") as temp:
    repo = Path(temp)
    git(repo, "init")
    git(repo, "config", "user.name", "Javis Test")
    git(repo, "config", "user.email", "javis-test@example.invalid")
    target = repo / "config.txt"
    target.write_text("base\n", encoding="utf-8")
    git(repo, "add", "config.txt")
    git(repo, "commit", "-m", "base")

    previous_root = updater.ROOT
    updater.ROOT = repo
    try:
        target.write_text("local change\n", encoding="utf-8")
        stash_oid, error = updater.stash_local_changes()
        assert not error and len(stash_oid) == 40, (stash_oid, error)
        assert target.read_text(encoding="utf-8") == "base\n"
        assert git(repo, "rev-parse", "refs/stash") == stash_oid

        # Incoming release edits the same line. Applying the backup conflicts.
        target.write_text("release change\n", encoding="utf-8")
        git(repo, "add", "config.txt")
        git(repo, "commit", "-m", "release")
        restored, error = updater.restore_local_changes(stash_oid)
        assert not restored and error
        assert target.read_text(encoding="utf-8") == "release change\n"
        assert git(repo, "status", "--porcelain") == ""
        assert git(repo, "rev-parse", "refs/stash") == stash_oid
        assert updater.drop_update_stash(stash_oid, restored) is False
        assert git(repo, "rev-parse", "refs/stash") == stash_oid

        # Rollback returns to the original code, where the backup applies cleanly.
        git(repo, "reset", "--hard", "HEAD~1")
        restored, error = updater.restore_local_changes(stash_oid)
        assert restored and not error
        assert target.read_text(encoding="utf-8") == "local change\n"
        assert updater.drop_update_stash(stash_oid, restored) is True
        assert git(repo, "stash", "list") == ""
    finally:
        updater.ROOT = previous_root


def drive_update(health, restores):
    """Exercise the actual updater decisions without stopping a real server."""
    state = {}
    dropped = []
    restore_calls = iter(restores)

    def write_state(changes):
        state.update(changes)

    def fake_run(command):
        assert command[:2] == ["git", "reset"], command
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    with patch.object(sys, "argv", ["updater.py", "--old-sha", "a" * 40,
                                   "--old-version", "1.0.0", "--target", "2.0.0"]), \
         patch.multiple(updater,
                        service_mode=lambda: "nohup",
                        stop_server=lambda *a: None,
                        start_server=lambda *a: None,
                        stash_local_changes=lambda: ("b" * 40, ""),
                        restore_local_changes=lambda oid: next(restore_calls),
                        drop_update_stash=lambda oid, restored: dropped.append((oid, restored)) or True,
                        merge_release=lambda: (SimpleNamespace(returncode=0, stdout="", stderr=""), True),
                        run=fake_run,
                        pip_install=lambda: SimpleNamespace(returncode=0),
                        poll_health=lambda *a: next(health),
                        read_current_version=lambda: "2.0.0",
                        _head_hien_tai=lambda: "a" * 40), \
         patch.object(updater.time, "sleep", lambda _: None), \
         patch.object(updater.us, "write_state", write_state), \
         patch.object(updater.us, "record_boot_version", lambda version: None):
        result = updater.main()
    return result, state, dropped


result, state, dropped = drive_update(iter([True]), iter([(False, "conflict")]))
assert result == 1 and state["result"] == "error"
assert state["stashed"] is True and "git stash" in state["error"]
assert dropped == [], "Conflicting backup must never be dropped on success"

result, state, dropped = drive_update(iter([False, True]),
                                      iter([(False, "conflict"), (True, "")]))
assert result == 0 and state["result"] == "rolled_back"
assert state["stashed"] is False and dropped == [("b" * 40, True)]

print("TẤT CẢ PASS: updater stash an toàn khi khôi phục xung đột và rollback")
