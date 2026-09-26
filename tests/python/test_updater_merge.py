"""Real Git checks for updating a customized branch from the release branch."""
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "server"))
os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-merge-state-")
import updater  # noqa: E402


def git(repo, *args):
    result = subprocess.run(["git", *map(str, args)], cwd=repo, capture_output=True,
                            text=True, encoding="utf-8", errors="replace")
    assert result.returncode == 0, (args, result.stdout, result.stderr)
    return result.stdout.strip()


with tempfile.TemporaryDirectory(prefix="javis-updater-merge-") as tmp:
    base = Path(tmp)
    remote = base / "release"
    remote.mkdir()
    git(remote, "init", "-b", "main")
    git(remote, "config", "user.name", "Javis Test")
    git(remote, "config", "user.email", "javis-test@example.invalid")
    (remote / "VERSION").write_text("1.0.0\n", encoding="utf-8")
    (remote / "shared.txt").write_text("base\n", encoding="utf-8")
    git(remote, "add", ".")
    git(remote, "commit", "-m", "release one")

    install = base / "install"
    git(base, "clone", remote, install)
    git(install, "config", "user.name", "Javis Test")
    git(install, "config", "user.email", "javis-test@example.invalid")
    git(install, "switch", "-c", "my-custom-branch")
    (install / "custom.txt").write_text("my own commit\n", encoding="utf-8")
    git(install, "add", "custom.txt")
    git(install, "commit", "-m", "local customization")
    custom_commit = git(install, "rev-parse", "HEAD")

    (remote / "VERSION").write_text("2.0.0\n", encoding="utf-8")
    git(remote, "add", "VERSION")
    git(remote, "commit", "-m", "release two")

    previous_root = updater.ROOT
    previous_source = updater.release_source
    updater.ROOT = install
    updater.release_source = lambda: ("origin", "main")
    try:
        merged, safe = updater.merge_release()
        assert merged.returncode == 0 and safe, (merged.stdout, merged.stderr)
        assert (install / "VERSION").read_text(encoding="utf-8") == "2.0.0\n"
        assert (install / "custom.txt").read_text(encoding="utf-8") == "my own commit\n"
        assert git(install, "merge-base", "--is-ancestor", custom_commit, "HEAD") == ""
        assert git(install, "branch", "--show-current") == "my-custom-branch"

        # A real content conflict must be aborted without losing the custom commit.
        (install / "shared.txt").write_text("local edit\n", encoding="utf-8")
        git(install, "add", "shared.txt")
        git(install, "commit", "-m", "local shared edit")
        before = git(install, "rev-parse", "HEAD")
        (remote / "shared.txt").write_text("release edit\n", encoding="utf-8")
        git(remote, "add", "shared.txt")
        git(remote, "commit", "-m", "release shared edit")
        conflict, safe = updater.merge_release()
        assert conflict.returncode != 0 and safe
        assert git(install, "rev-parse", "HEAD") == before
        assert (install / "shared.txt").read_text(encoding="utf-8") == "local edit\n"
        assert git(install, "status", "--porcelain") == ""
        detail = "\n".join((conflict.stdout or "", conflict.stderr or ""))
        message = updater.chan_doan_pull_hong(detail, merge_aborted=safe)
        assert "xung đột" in message.lower() and "shared.txt" in message
        assert "checkout main" not in message and "reset --hard" not in message

        # A fetch error also leaves the local branch untouched.
        original_source = updater.release_source
        updater.release_source = lambda: ("missing-remote", "main")
        try:
            failed, safe = updater.merge_release()
            assert failed.returncode != 0 and safe
            assert git(install, "rev-parse", "HEAD") == before
        finally:
            updater.release_source = original_source

        git(install, "switch", "--detach", before)
        detached, safe = updater.merge_release()
        assert detached.returncode != 0 and safe
        assert "detached HEAD" in (detached.stderr or "")
        assert git(install, "rev-parse", "HEAD") == before
    finally:
        updater.ROOT = previous_root
        updater.release_source = previous_source

print("TẤT CẢ PASS: cập nhật nhánh tùy chỉnh và hủy merge xung đột")
