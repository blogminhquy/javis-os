"""Pre-push quality gate for GitHub inside chat (spec docs/dev/2026-10-github-trong-chat-spec.md, section 7, phase G2).

Everything here runs in a conversation's worktree BEFORE Javis pushes, driven by Javis and not by the model's memory:

  7.1 `repo_rules`      the repo's own rules (AGENTS.md, CLAUDE.md, CONTRIBUTING.md) for every engine, not only the ones
                        that read CLAUDE.md natively, plus the per-repo lessons Javis learned (phase G5).
  7.2 `suggest_checks`  the local check commands, read from the repo's CI workflows and its usual manifests.
      `run_checks`      runs them with a time ceiling. A command that cannot run on this machine (missing tool or
                        module) is reported as "skipped here, CI decides", never as green.
  7.3 `secret_scan`     added lines that look like a credential block the commit.
  7.4 `cheat_scan`      changes that turn CI green without fixing anything (skipped tests, deleted tests, edited workflows,
                        loosened coverage, file-wide lint disables). They do not block the push; they block auto-merge.
  7.6 `diff_size`       lines changed, lockfiles and generated files excluded, against the 400-line threshold.

`run_gate` puts them together and returns one report. Pure functions take text so tests need no repo; the rest only
needs git. No FastAPI, no main import.
"""
from __future__ import annotations

import os
import re
import signal
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import winproc

RULE_FILES = ("AGENTS.md", "CLAUDE.md", "CONTRIBUTING.md", ".github/CONTRIBUTING.md")
RULES_MAX_CHARS = 4000          # per repo, inline in the prompt; the paths are always listed so the model can read more
CHECK_TIMEOUT_S = 600           # spec 7.2: 10 minutes for the whole local check run, adjustable per repo
OUTPUT_TAIL = 6000              # characters of a failed command's output kept for the fix turn
DIFF_THRESHOLD = 400            # spec 7.6, owner 2026-10-27

LOCKFILES = {"package-lock.json", "yarn.lock", "pnpm-lock.yaml", "poetry.lock", "Pipfile.lock", "uv.lock",
             "Cargo.lock", "go.sum", "composer.lock", "Gemfile.lock", "bun.lockb", "flake.lock"}
GENERATED = re.compile(r"(\.min\.(js|css)$|(^|/)dist/|(^|/)build/|(^|/)vendor/|\.snap$|_pb2\.py$|\.generated\.)")

# ============================================================
# 7.1 Repo rules
# ============================================================


def repo_rules(worktree: str, max_chars: int = RULES_MAX_CHARS) -> Dict[str, Any]:
    """The rule files a repo carries, trimmed to `max_chars` in total. Returns {files: [paths], text}."""
    root = Path(worktree)
    found, chunks, used = [], [], 0
    for name in RULE_FILES:
        p = root / name
        if not p.is_file():
            continue
        found.append(str(p))
        if used >= max_chars:
            continue
        try:
            body = p.read_text(encoding="utf-8", errors="replace").strip()
        except OSError:
            continue
        room = max_chars - used
        cut = body if len(body) <= room else body[:room].rsplit("\n", 1)[0] + "\n[...]"
        chunks.append(f"--- {name} ---\n{cut}")
        used += len(cut)
    return {"files": found, "text": "\n\n".join(chunks)}


# ============================================================
# 7.2 Local check commands
# ============================================================
# Steps that must not run on the owner's machine: they install into the system, need secrets, or publish something.
_SKIP_STEP = re.compile(
    r"(\$\{\{|\bsudo\b|\bapt(-get)?\b|\bbrew\b|\bchoco\b|\bpip3? install\b|python3? -m pip install|"
    r"npm (i|install) -g|\bcurl\b[^\n]*\|\s*(ba)?sh|\bwget\b|\bdocker (push|login)\b|\bgh release\b|"
    r"\bnpm publish\b|\btwine upload\b|\bdeploy\b|\bpublish\b|\brelease\b|git push|"
    r"GITHUB_TOKEN|GITHUB_OUTPUT|GITHUB_ENV|GITHUB_STEP_SUMMARY)", re.IGNORECASE)
_BRANCH_ONLY = re.compile(r"refs/heads/(main|master)|github\.ref\s*==|github\.event_name\s*==\s*'(push|schedule|release)'")


def _workflow_triggers_on_change(on: Any) -> bool:
    """True when the workflow runs on push or pull_request (the events a Javis branch causes)."""
    if on is None:
        return False
    if isinstance(on, str):
        return on in ("push", "pull_request")
    if isinstance(on, list):
        return any(x in ("push", "pull_request") for x in on)
    if isinstance(on, dict):
        return any(k in on for k in ("push", "pull_request"))
    return False


def commands_from_workflow(text: str) -> List[Dict[str, str]]:
    """`run:` steps of a workflow that make sense on this machine, in order. Each item: {name, run}."""
    import fastyaml
    try:
        doc = fastyaml.safe_load(text) or {}
    except Exception:
        return []
    if not isinstance(doc, dict):
        return []
    # PyYAML reads the bare key `on` as the boolean True.
    on = doc.get("on", doc.get(True))
    if not _workflow_triggers_on_change(on):
        return []
    out: List[Dict[str, str]] = []
    jobs = doc.get("jobs") or {}
    if not isinstance(jobs, dict):
        return []
    for job in jobs.values():
        if not isinstance(job, dict):
            continue
        if _BRANCH_ONLY.search(str(job.get("if") or "")):
            continue
        for step in job.get("steps") or []:
            if not isinstance(step, dict) or not step.get("run"):
                continue
            run = str(step["run"]).strip()
            if _SKIP_STEP.search(run) or _BRANCH_ONLY.search(str(step.get("if") or "")):
                continue
            if step.get("env") and "${{" in str(step.get("env")):
                continue
            item = {"name": str(step.get("name") or run.splitlines()[0])[:80], "run": run}
            if item not in out:
                out.append(item)
    return out


def _manifest_checks(root: Path) -> List[Dict[str, str]]:
    out: List[Dict[str, str]] = []
    pkg = root / "package.json"
    if pkg.is_file():
        try:
            import json
            scripts = (json.loads(pkg.read_text(encoding="utf-8")) or {}).get("scripts") or {}
        except Exception:
            scripts = {}
        runner = "pnpm" if (root / "pnpm-lock.yaml").is_file() else ("yarn" if (root / "yarn.lock").is_file() else "npm")
        for s in ("lint", "typecheck", "test", "build"):
            if s in scripts:
                out.append({"name": f"{runner} {s}", "run": f"{runner} run {s}" if runner == "npm" else f"{runner} {s}"})
    if (root / "pyproject.toml").is_file() or (root / "pytest.ini").is_file() or (root / "setup.cfg").is_file():
        if (root / "tests").is_dir() or (root / "test").is_dir():
            out.append({"name": "pytest", "run": "python -m pytest -q"})
    mk = root / "Makefile"
    if mk.is_file():
        try:
            if re.search(r"^test:", mk.read_text(encoding="utf-8", errors="replace"), re.M):
                out.append({"name": "make test", "run": "make test"})
        except OSError:
            pass
    return out


def suggest_checks(worktree: str) -> List[Dict[str, str]]:
    """Proposed local check commands: the repo's CI steps first, then usual manifest commands CI does not cover."""
    root = Path(worktree)
    out: List[Dict[str, str]] = []
    wf = root / ".github" / "workflows"
    if wf.is_dir():
        for p in sorted(list(wf.glob("*.yml")) + list(wf.glob("*.yaml"))):
            try:
                for c in commands_from_workflow(p.read_text(encoding="utf-8", errors="replace")):
                    if c not in out:
                        out.append(c)
            except OSError:
                continue
    runs = "\n".join(c["run"] for c in out)
    for c in _manifest_checks(root):
        if c["run"].split()[-1] not in runs:
            out.append(c)
    return out


# A command that could not run here at all, as opposed to a check that ran and failed.
_ENV_FAIL = re.compile(r"(command not found|not recognized as an internal or external command|No module named|"
                       r"Cannot find module|ModuleNotFoundError|executable file not found|is not installed|"
                       r"ENOENT: no such file or directory, (spawn|open) )", re.IGNORECASE)


def classify(returncode: int, output: str) -> str:
    """"pass", "fail" or "skipped" (could not run on this machine; CI decides)."""
    if returncode == 0:
        return "pass"
    if returncode in (126, 127) or _ENV_FAIL.search(output or ""):
        return "skipped"
    return "fail"


def _kill_tree(p: subprocess.Popen) -> None:
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(p.pid)], capture_output=True,
                           creationflags=winproc.no_window())
        else:
            os.killpg(p.pid, signal.SIGKILL)
    except Exception:
        try:
            p.kill()
        except Exception:
            pass


def run_checks(worktree: str, checks: List[Dict[str, str]], timeout_s: int = CHECK_TIMEOUT_S) -> List[Dict[str, Any]]:
    """Run each check in the worktree, sharing one time budget. Stops at the first real failure."""
    results: List[Dict[str, Any]] = []
    deadline = time.monotonic() + max(10, int(timeout_s))
    env = dict(os.environ, CI="true", GIT_TERMINAL_PROMPT="0")
    for c in checks:
        left = deadline - time.monotonic()
        if left <= 0:
            results.append({"name": c["name"], "run": c["run"], "status": "skipped",
                            "output": "time budget used up", "seconds": 0})
            continue
        t0 = time.monotonic()
        shell = ["bash", "-e", "-c", c["run"]] if os.name != "nt" else ["cmd", "/c", c["run"]]
        try:
            p = subprocess.Popen(shell, cwd=worktree, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                                 encoding="utf-8", errors="replace", env=env, start_new_session=(os.name != "nt"),
                                 creationflags=winproc.no_window())
        except FileNotFoundError as e:
            results.append({"name": c["name"], "run": c["run"], "status": "skipped", "output": str(e), "seconds": 0})
            continue
        try:
            out, _ = p.communicate(timeout=left)
            status = classify(p.returncode, out)
        except subprocess.TimeoutExpired:
            _kill_tree(p)
            out = (p.communicate()[0] or "") if p.stdout else ""
            out += "\n[stopped: time budget used up]"
            status = "fail"
        results.append({"name": c["name"], "run": c["run"], "status": status, "output": (out or "")[-OUTPUT_TAIL:],
                        "seconds": round(time.monotonic() - t0, 1)})
        if status == "fail":
            break
    return results


# ============================================================
# Diff helpers
# ============================================================
def _git(args: List[str], cwd: str) -> str:
    p = subprocess.run(["git"] + args, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                       timeout=60, env=dict(os.environ, LC_ALL="C", GIT_TERMINAL_PROMPT="0"),
                       creationflags=winproc.no_window())
    return p.stdout or ""


def branch_diff(worktree: str, base: str) -> str:
    """Unified diff of everything this branch would push (commits since `base`, plus uncommitted edits)."""
    mb = _git(["merge-base", base, "HEAD"], worktree).strip() or base
    _git(["add", "-N", "."], worktree)   # untracked files show up in the diff, nothing is staged for real
    return _git(["diff", "--no-color", "-U0", mb], worktree)


def changed_files(diff: str) -> List[Dict[str, str]]:
    """[{path, status}] from a unified diff; status A, D or M."""
    out: List[Dict[str, str]] = []
    cur: Optional[Dict[str, str]] = None
    for line in diff.splitlines():
        if line.startswith("diff --git "):
            m = re.match(r"diff --git a/(.+?) b/(.+)$", line)
            cur = {"path": m.group(2) if m else "", "status": "M"}
            out.append(cur)
        elif cur is not None and line.startswith("new file mode"):
            cur["status"] = "A"
        elif cur is not None and line.startswith("deleted file mode"):
            cur["status"] = "D"
    return out


def _added_lines(diff: str):
    """(path, line_no, text) for each added line."""
    path, line_no = "", 0
    for line in diff.splitlines():
        if line.startswith("+++ "):
            path = line[6:] if line.startswith("+++ b/") else ""
        elif line.startswith("@@"):
            m = re.search(r"\+(\d+)", line)
            line_no = int(m.group(1)) if m else 0
        elif line.startswith("+") and not line.startswith("+++"):
            yield path, line_no, line[1:]
            line_no += 1


def _removed_lines(diff: str):
    path = ""
    for line in diff.splitlines():
        if line.startswith("--- "):
            path = line[6:] if line.startswith("--- a/") else ""
        elif line.startswith("-") and not line.startswith("---"):
            yield path, line[1:]


# ============================================================
# 7.3 Secret scan
# ============================================================
_SECRET_RES = [
    ("GitHub token", re.compile(r"(?<![A-Za-z0-9_])(ghp_|gho_|ghs_|ghu_)[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,}")),
    ("API key sk-", re.compile(r"(?<![A-Za-z0-9_-])sk-(ant-|or-|proj-)?[A-Za-z0-9_-]{20,}")),
    ("AWS key", re.compile(r"(?<![A-Z0-9])(AKIA|ASIA)[0-9A-Z]{16}(?![A-Z0-9])")),
    ("Google API key", re.compile(r"AIza[0-9A-Za-z_-]{35}")),
    ("Slack token", re.compile(r"xox[baprs]-[0-9A-Za-z-]{10,}")),
    ("private key", re.compile(r"-----BEGIN ([A-Z]+ )?PRIVATE KEY-----")),
    ("Telegram bot token", re.compile(r"(?<!\d)\d{8,10}:AA[0-9A-Za-z_-]{30,}")),
    ("xAI / Groq key", re.compile(r"(?<![A-Za-z0-9_-])(xai-[A-Za-z0-9]{30,}|gsk_[A-Za-z0-9]{30,})")),
]
_SECRET_FILES = re.compile(r"(^|/)(\.env(\.[^/]*)?|id_rsa|id_ed25519|.*\.pem|.*\.p12|.*\.pfx|credentials\.json)$")
_SECRET_FILE_OK = re.compile(r"\.env\.(example|sample|template|dist)$")


def secret_scan(diff: str) -> List[Dict[str, Any]]:
    """Credentials in ADDED lines or added credential files. Each finding: {path, line, kind} (never the value)."""
    found: List[Dict[str, Any]] = []
    for f in changed_files(diff):
        if f["status"] == "A" and _SECRET_FILES.search(f["path"]) and not _SECRET_FILE_OK.search(f["path"]):
            found.append({"path": f["path"], "line": 0, "kind": "credential file"})
    for path, no, text in _added_lines(diff):
        for kind, rx in _SECRET_RES:
            if rx.search(text):
                found.append({"path": path, "line": no, "kind": kind})
                break
    return found


# ============================================================
# 7.4 Cheat scan
# ============================================================
_SKIP_MARKERS = re.compile(
    r"(@pytest\.mark\.(skip|xfail)\b|pytest\.skip\(|unittest\.skip|@skip\b|\bit\.skip\(|\bdescribe\.skip\(|"
    r"\btest\.skip\(|\bxit\(|\bxdescribe\(|\bit\.only\(|\bdescribe\.only\(|\btest\.only\(|\bt\.Skip\(|"
    r"#\[ignore\]|@Disabled\b|@Ignore\b)")
_FILE_LINT_OFF = re.compile(r"(/\*\s*eslint-disable\s*\*/|^\s*//\s*eslint-disable\s*$|#\s*(ruff|flake8):\s*noqa\s*$|"
                            r"#\s*pylint:\s*skip-file|@ts-nocheck|#\s*type:\s*ignore\s*$)")
_COVERAGE = re.compile(r"(fail_under|fail-under|coverageThreshold|--cov-fail-under|min_coverage|minimum_coverage)", re.I)
_TEST_PATH = re.compile(r"(^|/)(tests?|__tests__|spec)(/|$)|(^|/)test_[^/]+\.py$|_test\.(py|go)$|\.(test|spec)\.[jt]sx?$")
_TEST_DEF = re.compile(r"^\s*(def test_\w+|async def test_\w+|(it|test)\(\s*['\"`]|func Test\w+\()")


def cheat_scan(diff: str) -> List[Dict[str, Any]]:
    """Signs that CI was made green without a fix. Each finding: {path, line, kind}."""
    found: List[Dict[str, Any]] = []
    for f in changed_files(diff):
        if f["path"].startswith(".github/workflows/"):
            found.append({"path": f["path"], "line": 0, "kind": "workflow edited"})
        if f["status"] == "D" and _TEST_PATH.search(f["path"]):
            found.append({"path": f["path"], "line": 0, "kind": "test file deleted"})
    for path, no, text in _added_lines(diff):
        if _SKIP_MARKERS.search(text):
            found.append({"path": path, "line": no, "kind": "test skipped"})
        elif _FILE_LINT_OFF.search(text):
            found.append({"path": path, "line": no, "kind": "lint disabled for a whole file"})
        elif _COVERAGE.search(text):
            found.append({"path": path, "line": no, "kind": "coverage threshold changed"})
    removed_tests: Dict[str, int] = {}
    for path, text in _removed_lines(diff):
        if _TEST_DEF.search(text):
            removed_tests[path] = removed_tests.get(path, 0) + 1
    added_tests: Dict[str, int] = {}
    for path, _no, text in _added_lines(diff):
        if _TEST_DEF.search(text):
            added_tests[path] = added_tests.get(path, 0) + 1
    for path, n in removed_tests.items():
        if n > added_tests.get(path, 0):
            found.append({"path": path, "line": 0, "kind": "test removed"})
    return found


# ============================================================
# 7.6 Diff size
# ============================================================
def diff_size(diff: str) -> int:
    """Changed lines, lockfiles and generated files excluded."""
    n, skip = 0, False
    for line in diff.splitlines():
        if line.startswith("diff --git "):
            m = re.match(r"diff --git a/(.+?) b/(.+)$", line)
            p = m.group(2) if m else ""
            skip = Path(p).name in LOCKFILES or bool(GENERATED.search(p))
        elif skip:
            continue
        elif (line.startswith("+") and not line.startswith("+++")) or (line.startswith("-") and not line.startswith("---")):
            n += 1
    return n


# ============================================================
# The gate
# ============================================================
def run_gate(worktree: str, base: str, checks: Optional[List[Dict[str, str]]] = None,
             timeout_s: int = CHECK_TIMEOUT_S, threshold: int = DIFF_THRESHOLD) -> Dict[str, Any]:
    """Everything section 7 asks, in one report.

    `ok` False means: do not push (a check failed, or a secret is in the diff). `merge_block` lists 7.4 findings, which
    let the push go but stop auto-merge. `skipped` checks could not run here and are left to CI.
    """
    diff = branch_diff(worktree, base)
    secrets = secret_scan(diff)
    cheats = cheat_scan(diff)
    size = diff_size(diff)
    if checks is None:
        checks = suggest_checks(worktree)
    results = run_checks(worktree, checks, timeout_s) if checks and not secrets else []
    failed = [r for r in results if r["status"] == "fail"]
    return {
        "ok": not secrets and not failed,
        "empty": not diff.strip(),
        "secrets": secrets,
        "merge_block": cheats,
        "diff_lines": size,
        "too_big": size > threshold,
        "checks": results,
        "failed": failed,
        "skipped": [r for r in results if r["status"] == "skipped"],
    }


def summary(report: Dict[str, Any]) -> str:
    """Short summary for the chat, in the machine's UI language (localefmt)."""
    import localefmt
    c = localefmt.chu
    lines = []
    res = report.get("checks") or []
    if report.get("secrets"):
        where = ", ".join(f"{s['path']}:{s['line']} ({s['kind']})" for s in report["secrets"][:5])
        lines.append(c(f"Chặn commit: diff có thứ giống thông tin bí mật ở {where}.",
                       f"Commit blocked: the diff has what looks like a secret at {where}."))
    if res:
        ok, sk = sum(1 for r in res if r["status"] == "pass"), len(report.get("skipped") or [])
        extra_vi = f", {sk} bỏ qua vì máy thiếu công cụ (chờ CI)" if sk else ""
        extra_en = f", {sk} skipped because this machine lacks a tool (CI decides)" if sk else ""
        lines.append(c(f"Kiểm tra ở máy: {ok}/{len(res)} đạt{extra_vi}.", f"Local checks: {ok}/{len(res)} passed{extra_en}."))
    for r in report.get("failed") or []:
        cmd = r["run"].splitlines()[0][:120]
        lines.append(c(f"Đỏ: `{cmd}`", f"Failed: `{cmd}`"))
    if report.get("merge_block"):
        what = ", ".join(f"{x['path']} ({x['kind']})" for x in report["merge_block"][:5])
        lines.append(c(f"Cần người xem trước khi merge: {what}.", f"Needs a person to look before merging: {what}."))
    if report.get("too_big"):
        n = report["diff_lines"]
        lines.append(c(f"Diff dài {n} dòng, quá ngưỡng {DIFF_THRESHOLD}: nên tách thành nhiều việc nhỏ.",
                       f"The diff is {n} lines, over the {DIFF_THRESHOLD} threshold: better split into smaller jobs."))
    return "\n".join(lines)
