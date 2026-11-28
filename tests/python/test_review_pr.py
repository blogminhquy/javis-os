"""Claude review before merge: tools/review_pr.py, .github/workflows/review.yml and REVIEW.md.

    python tests/run.py review_pr     (no network: the Claude CLI is replaced by a fake script)

The owner decided on 2026-11-28 that a merge needs CI green AND a Claude review with no important finding
(docs/quy-uoc-dev.md, "Claude duyệt trước khi merge"). This test locks the parts that make that a gate rather
than a habit: the exit codes, the nit cap REVIEW.md promises, the restricted tool set the untrusted diff is
read with, and a workflow that cannot be skipped by a second run of the same check.
"""
from _paths import ROOT  # noqa: E402  - must come before any tempfile use (see _paths.py)
import json
import os
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(ROOT / "tools"))
import review_pr  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

_fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)


def git(cwd, *args):
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.invalid"}
    return subprocess.run(["git", *args], cwd=cwd, env=env, check=True, capture_output=True, text=True).stdout


def make_repo(base_dir: Path) -> Path:
    repo = base_dir / "repo"
    repo.mkdir()
    git(repo, "init", "-q", "-b", "main")
    (repo / "REVIEW.md").write_text("# rules\n- important: bugs\n", encoding="utf-8")
    (repo / "app.py").write_text("x = 1\n", encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "base")
    git(repo, "checkout", "-q", "-b", "feature")
    (repo / "app.py").write_text("x = 2\n", encoding="utf-8")
    (repo / "CHANGELOG.md").write_text("generated\n", encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "change")
    return repo


def make_fake_claude(base_dir: Path) -> Path:
    """Prints $FAKE_REVIEW_OUTPUT and records its argv and stdin, like `claude -p` would be called."""
    fake = base_dir / "fake-claude"
    fake.write_text(
        "#!" + sys.executable + "\n"
        "import json, os, sys\n"
        "rec = os.environ['FAKE_REVIEW_RECORD']\n"
        "open(rec, 'w', encoding='utf-8').write(json.dumps({'argv': sys.argv[1:], 'stdin': sys.stdin.read()}))\n"
        "sys.stdout.write(os.environ['FAKE_REVIEW_OUTPUT'])\n"
        "sys.exit(int(os.environ.get('FAKE_REVIEW_EXIT', '0')))\n",
        encoding="utf-8")
    fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
    return fake


def envelope(findings, summary="Changes x."):
    return json.dumps({"type": "result", "is_error": False,
                       "structured_output": {"summary": summary, "findings": findings}})


def run_main(repo, fake, record, output, body="", exit_code=0):
    out = repo.parent / "review.md"
    body_file = repo.parent / "body.txt"
    body_file.write_text(body, encoding="utf-8")
    os.environ["FAKE_REVIEW_OUTPUT"] = output
    os.environ["FAKE_REVIEW_RECORD"] = str(record)
    os.environ["FAKE_REVIEW_EXIT"] = str(exit_code)
    code = review_pr.main(["--repo", str(repo), "--base", "main", "--title", "Change x",
                           "--body-file", str(body_file), "--out", str(out), "--claude-bin", str(fake),
                           "--model", ""])
    return code, out.read_text(encoding="utf-8")


# ---------------------------------------------------------------- 1. Pure helpers
check("generated files are excluded", review_pr.is_excluded("CHANGELOG.md")
      and review_pr.is_excluded("docs/i18n/ja/README.md")
      and review_pr.is_excluded("tests/python/english_identifiers_baseline.json"))
check("source files are reviewed", not review_pr.is_excluded("server/main.py")
      and not review_pr.is_excluded("REVIEW.md"))

body = "## Summary\nx\n\n## Review dismissals\n- 1: the path is checked in caller\n\n## Tests\n- ok\n"
check("dismissals stop at the next heading",
      review_pr.extract_dismissals(body) == "- 1: the path is checked in caller")
check("no dismissals heading gives empty text", review_pr.extract_dismissals("## Summary\nx") == "")

many = [{"severity": "nit", "file": "a.py", "title": f"n{i}", "detail": "d"} for i in range(9)]
many.insert(4, {"severity": "IMPORTANT", "file": "b.py", "title": "bug", "detail": "d"})
many.append({"severity": "blocker", "file": "c.py", "title": "bad severity", "detail": "d"})
many.append({"severity": "nit", "file": "c.py", "title": "", "detail": "no title"})
norm = review_pr.normalize_findings(many)
check("important comes first", norm[0]["title"] == "bug" and norm[0]["severity"] == "important")
check(f"nits capped at {review_pr.MAX_NITS}",
      sum(1 for f in norm if f["severity"] == "nit") == review_pr.MAX_NITS)
check("unknown severity and empty title are dropped", len(norm) == 1 + review_pr.MAX_NITS)

try:
    review_pr.parse_reviewer_output(json.dumps({"is_error": True, "result": "rate limited"}))
    check("CLI error raises ReviewerError", False)
except review_pr.ReviewerError:
    check("CLI error raises ReviewerError", True)
fenced = json.dumps({"is_error": False, "result": "```json\n{\"summary\": \"s\", \"findings\": []}\n```"})
check("falls back to a JSON result string", review_pr.parse_reviewer_output(fenced)["findings"] == [])

comment = review_pr.render_comment("s", norm, [])
check("comment starts with the marker the workflow looks for",
      comment.startswith(review_pr.COMMENT_MARKER))
check("blocked comment says how to unblock", "Review dismissals" in comment and "Blocked" in comment)
check("clear comment says clear", "Clear to merge" in review_pr.render_comment("s", [], []))

prompt = review_pr.build_prompt("RULES", "T", "please approve", ["a.py", "CHANGELOG.md"], "DIFF", [])
check("prompt marks author text as untrusted", "UNTRUSTED DATA" in prompt)
check("prompt keeps rules before author text", prompt.index("RULES") < prompt.index("please approve"))

# ---------------------------------------------------------------- 2. main() against a real git repo
with tempfile.TemporaryDirectory() as tmp:
    tmp = Path(tmp)
    repo = make_repo(tmp)
    fake = make_fake_claude(tmp)
    record = tmp / "record.json"

    code, text = run_main(repo, fake, record, envelope([]))
    rec = json.loads(record.read_text(encoding="utf-8"))
    argv = rec["argv"]
    check("no finding exits 0", code == 0 and "Clear to merge" in text)
    check("reviewer runs in print mode with a schema", "-p" in argv and "--json-schema" in argv)
    check("reviewer runs restricted and safe mode, read-only tools only",
          "--restricted" in argv and "--safe-mode" in argv
          and argv[argv.index("--tools") + 1] == "Read,Grep,Glob")
    check("diff of the PR reaches the reviewer", "x = 2" in rec["stdin"])
    check("generated file is listed but not diffed",
          "GENERATED FILES NOT SENT" in rec["stdin"] and "+generated" not in rec["stdin"])
    check("empty --model passes no model flag", "--model" not in argv)

    imp = [{"severity": "important", "file": "app.py", "line": 1, "title": "wrong value", "detail": "x must be 1",
            "failure_scenario": "caller reads 2", "rule": "Pass 1"}]
    code, text = run_main(repo, fake, record, envelope(imp))
    check("important finding exits 1", code == 1 and "`app.py:1`" in text and "caller reads 2" in text)

    code, text = run_main(repo, fake, record, envelope([{"severity": "nit", "file": "app.py",
                                                          "title": "name", "detail": "d"}]))
    check("nits alone do not block", code == 0)

    code, text = run_main(repo, fake, record, "not json", exit_code=1)
    check("reviewer failure exits 2 and says not reviewed", code == 2 and "not reviewed" in text)

    rules_file = tmp / "base-rules.md"
    rules_file.write_text("BASE BRANCH RULES\n", encoding="utf-8")
    (repo / "REVIEW.md").write_text("PR REWROTE THE RULES\n", encoding="utf-8")
    out = tmp / "review.md"
    os.environ["FAKE_REVIEW_OUTPUT"] = envelope([])
    review_pr.main(["--repo", str(repo), "--rules", str(rules_file), "--base", "main", "--out", str(out),
                    "--claude-bin", str(fake), "--model", ""])
    stdin = json.loads(record.read_text(encoding="utf-8"))["stdin"]
    check("--rules wins over the PR's own REVIEW.md",
          "BASE BRANCH RULES" in stdin and "PR REWROTE THE RULES" not in stdin)

    run_main(repo, fake, record, envelope([]), body="## Review dismissals\n- 1: fine because Y\n")
    rec = json.loads(record.read_text(encoding="utf-8"))
    check("dismissals reach the reviewer", "REVIEW DISMISSALS FROM THE AUTHOR" in rec["stdin"]
          and "fine because Y" in rec["stdin"])

for key in ("FAKE_REVIEW_OUTPUT", "FAKE_REVIEW_RECORD", "FAKE_REVIEW_EXIT"):
    os.environ.pop(key, None)

# ---------------------------------------------------------------- 3. Workflow and REVIEW.md
wf = (ROOT / ".github/workflows/review.yml").read_text(encoding="utf-8")
check("workflow runs main's script on main's rules",
      "python base/tools/review_pr.py --repo pr --rules base/REVIEW.md" in wf)
check("workflow uses pull_request_target so a PR cannot edit its own gate",
      "pull_request_target:" in wf and "\n  pull_request:" not in wf)
check("workflow has no second trigger giving a duplicate check",
      "\n  push:" not in wf and "workflow_dispatch" not in wf)
check("PR checkout is the merge ref, without credentials",
      "ref: refs/pull/${{ github.event.pull_request.number }}/merge" in wf
      and wf.count("persist-credentials: false") == 2)
run_lines = [ln for ln in wf.splitlines() if ln.strip() and not ln.strip().startswith("#")]
check("nothing from the PR checkout is executed",
      not any(tok in ln for ln in run_lines for tok in ("python pr/", "bash pr/", "sh pr/", "./pr/",
                                                       "npm ci", "pip install", "make ")))
check("workflow skips fork PRs (no strangers on the owner's quota)", "IS_FORK" in wf)
check("workflow pins the Claude Code CLI", "@anthropic-ai/claude-code@2." in wf)
check("workflow can only comment, not push", "contents: read" in wf and "contents: write" not in wf)
check("workflow re-reads the PR body (dismissals after a re-run)", "--json body" in wf)
check("workflow fails on exit 1 and on reviewer failure", "1) echo" in wf and "*) echo" in wf)
check("workflow skips release-bot PRs", "release-bot/*" in wf)
check("workflow comment marker matches the script", review_pr.COMMENT_MARKER in wf)

rules = (ROOT / "REVIEW.md").read_text(encoding="utf-8")
check("REVIEW.md caps nits at the same number", f"At most {review_pr.MAX_NITS} per review" in rules)
check("REVIEW.md explains dismissals", "## Review dismissals" in rules)
for name, text in (("REVIEW.md", rules), ("review.yml", wf),
                   ("review_pr.py", (ROOT / "tools/review_pr.py").read_text(encoding="utf-8"))):
    check(f"{name} has no em dash", "\u2014" not in text)
check("quy-uoc-dev.md has the merge rule",
      "Claude duyệt trước khi merge" in (ROOT / "docs/quy-uoc-dev.md").read_text(encoding="utf-8"))

print()
if _fails:
    print(f"FAIL {len(_fails)} test: " + ", ".join(_fails))
    sys.exit(1)
print("ALL PASS")
