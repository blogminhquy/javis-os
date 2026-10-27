"""GitHub inside chat, phase G2: the pre-push quality gate (spec section 7).

    python tests/run.py github_gate      (no network; needs git and bash)

Acceptance criteria covered here:
  5. A local check that fails means no push (`ok` False with the failing command).
  6. A diff carrying a token is blocked before commit, and the finding never repeats the secret.
  7. A diff that adds `@pytest.mark.skip` or edits a workflow is flagged so auto-merge stops.
Plus: repo rules reach every engine (trimmed, paths listed), CI commands are read from the workflows without the steps
that must not run on the owner's machine, a missing tool is "skipped" not "passed", and the 400-line diff threshold
ignores lockfiles.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-gate-")
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import github_gate as g  # noqa: E402

_fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)


def git(args, cwd):
    return subprocess.run(["git"] + args, cwd=cwd, capture_output=True, text=True, check=True)


def repo(files):
    d = tempfile.mkdtemp(prefix="gate-repo-")
    git(["init", "-q", "-b", "main"], d)
    git(["config", "user.email", "t@t"], d)
    git(["config", "user.name", "T"], d)
    for name, text in files.items():
        p = Path(d, name)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    git(["add", "-A"], d)
    git(["commit", "-qm", "init"], d)
    return d


# ---- 7.1 Repo rules ----
r = repo({"AGENTS.md": "Rule A\n" * 10, "CLAUDE.md": "x" * 9000, "src/a.py": "a = 1\n"})
rules = g.repo_rules(r)
check("rule files are found", [Path(p).name for p in rules["files"]] == ["AGENTS.md", "CLAUDE.md"])
check("rules are trimmed to the ceiling", len(rules["text"]) <= g.RULES_MAX_CHARS + 200 and "[...]" in rules["text"])
check("a repo without rule files gives nothing", g.repo_rules(tempfile.mkdtemp())["text"] == "")

# ---- 7.2 Commands from workflows ----
wf = """
name: CI
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Install system deps
        run: sudo apt-get install -y ffmpeg
      - name: Install
        run: npm ci
      - name: Lint
        run: npm run lint
      - name: Test
        run: |
          npm test
          echo done
      - name: Matrix thing
        run: echo ${{ matrix.os }}
      - name: Deploy
        if: github.ref == 'refs/heads/main'
        run: ./deploy.sh
      - name: Publish
        run: npm publish
"""
cmds = g.commands_from_workflow(wf)
runs = [c["run"] for c in cmds]
check("CI run steps are read in order", runs[:3] == ["npm ci", "npm run lint", "npm test\necho done"])
check("sudo, ${{ }}, main-only and publish steps are left out",
      not any(("sudo" in x) or ("${{" in x) or ("deploy" in x) or ("publish" in x) for x in runs))
check("a workflow that only runs on schedule gives nothing",
      g.commands_from_workflow("on:\n  schedule:\n    - cron: '0 0 * * *'\njobs:\n  a:\n    steps:\n      - run: make\n") == [])
check("broken YAML gives nothing instead of crashing", g.commands_from_workflow("on: [push\njobs: {") == [])
r2 = repo({".github/workflows/ci.yml": wf, "package.json": json.dumps({"scripts": {"test": "x", "typecheck": "tsc"}})})
sug = [c["run"] for c in g.suggest_checks(r2)]
check("manifest commands CI does not cover are added", "npm run typecheck" in sug and sug.count("npm test\necho done") == 1)
r3 = repo({"pyproject.toml": "[project]\nname='x'\n", "tests/test_a.py": "def test_a():\n    assert 1\n"})
check("a Python repo with tests gets pytest", any("pytest" in c["run"] for c in g.suggest_checks(r3)))

# ---- run_checks and classify ----
res = g.run_checks(r, [{"name": "ok", "run": "true"}, {"name": "missing", "run": "definitely-not-a-tool-xyz --x"},
                       {"name": "bad", "run": "echo boom; exit 3"}, {"name": "never", "run": "true"}])
check("a passing command passes", res[0]["status"] == "pass")
check("a missing tool is skipped, not passed", res[1]["status"] == "skipped")
check("a real failure fails and keeps its output", res[2]["status"] == "fail" and "boom" in res[2]["output"])
check("checks stop at the first real failure", len(res) == 3)
check("ModuleNotFoundError counts as could-not-run", g.classify(1, "ModuleNotFoundError: No module named 'x'") == "skipped")
slow = g.run_checks(r, [{"name": "slow", "run": "sleep 30"}], timeout_s=10)
check("a command over the time budget is stopped and fails", slow[0]["status"] == "fail" and slow[0]["seconds"] < 25)

# ---- 7.3 Secrets ----
tok = "ghp_" + "A1b2C3d4" * 5
d = f"""diff --git a/config.py b/config.py
--- a/config.py
+++ b/config.py
@@ -1,0 +2,1 @@
+TOKEN = "{tok}"
diff --git a/.env b/.env
new file mode 100644
--- /dev/null
+++ b/.env
@@ -0,0 +1 @@
+X=1
diff --git a/.env.example b/.env.example
new file mode 100644
--- /dev/null
+++ b/.env.example
@@ -0,0 +1 @@
+X=
"""
sec = g.secret_scan(d)
check("criterion 6: a GitHub token in an added line is found", any(s["kind"] == "GitHub token" and s["line"] == 2 for s in sec))
check("an added .env file is flagged, .env.example is not",
      any(s["path"] == ".env" for s in sec) and not any(s["path"] == ".env.example" for s in sec))
check("a finding never repeats the secret", tok not in json.dumps(sec))
check("a removed secret is not a finding",
      g.secret_scan(f"diff --git a/a b/a\n--- a/a\n+++ b/a\n@@ -1 +0,0 @@\n-T = '{tok}'\n") == [])
for s in ["sk-ant-" + "x" * 30, "AKIA" + "ABCDEFGHIJKLMNOP", "-----BEGIN OPENSSH PRIVATE KEY-----"]:
    check(f"detects {s[:12]}...", bool(g.secret_scan(f"diff --git a/f b/f\n--- a/f\n+++ b/f\n@@ -0,0 +1 @@\n+{s}\n")))

# ---- 7.4 Cheats ----
cheat = """diff --git a/tests/test_x.py b/tests/test_x.py
--- a/tests/test_x.py
+++ b/tests/test_x.py
@@ -1,2 +1,3 @@
+@pytest.mark.skip(reason="flaky")
 def test_a():
-def test_b():
diff --git a/.github/workflows/ci.yml b/.github/workflows/ci.yml
--- a/.github/workflows/ci.yml
+++ b/.github/workflows/ci.yml
@@ -3 +3 @@
-      run: pytest
+      run: pytest || true
diff --git a/tests/test_old.py b/tests/test_old.py
deleted file mode 100644
--- a/tests/test_old.py
+++ /dev/null
@@ -1 +0,0 @@
-def test_old(): pass
diff --git a/setup.cfg b/setup.cfg
--- a/setup.cfg
+++ b/setup.cfg
@@ -1 +1 @@
+fail_under = 10
diff --git a/web/app.ts b/web/app.ts
--- a/web/app.ts
+++ b/web/app.ts
@@ -0,0 +1 @@
+// @ts-nocheck
"""
kinds = {c["kind"] for c in g.cheat_scan(cheat)}
check("criterion 7: an added skip marker is flagged", "test skipped" in kinds)
check("criterion 7: an edited workflow is flagged", "workflow edited" in kinds)
check("a deleted test file is flagged", "test file deleted" in kinds)
check("a removed test function is flagged", "test removed" in kinds)
check("a loosened coverage threshold is flagged", "coverage threshold changed" in kinds)
check("a file-wide lint disable is flagged", "lint disabled for a whole file" in kinds)
check("an ordinary code change is not flagged",
      g.cheat_scan("diff --git a/src/a.py b/src/a.py\n--- a/src/a.py\n+++ b/src/a.py\n@@ -1 +1 @@\n-a = 1\n+a = 2\n") == [])
check("renaming a test (one removed, one added) is not 'test removed'",
      not [c for c in g.cheat_scan("diff --git a/t/test_a.py b/t/test_a.py\n--- a/t/test_a.py\n+++ b/t/test_a.py\n"
                                   "@@ -1 +1 @@\n-def test_old():\n+def test_new():\n") if c["kind"] == "test removed"])

# ---- 7.6 Diff size ----
big = "diff --git a/package-lock.json b/package-lock.json\n--- a/package-lock.json\n+++ b/package-lock.json\n" + \
      "".join(f"+l{i}\n" for i in range(900)) + \
      "diff --git a/src/a.py b/src/a.py\n--- a/src/a.py\n+++ b/src/a.py\n" + "".join(f"+x{i}\n" for i in range(12))
check("lockfile lines do not count toward the diff size", g.diff_size(big) == 12)

# ---- run_gate end to end on a real repo ----
w = repo({"src/a.py": "a = 1\n", "check.sh": "grep -q 'a = 2' src/a.py\n"})
checks = [{"name": "check", "run": "bash check.sh"}]
Path(w, "src/a.py").write_text("a = 3\n", encoding="utf-8")
rep = g.run_gate(w, "main", checks)
check("criterion 5: a failing local check means no push", rep["ok"] is False and rep["failed"][0]["name"] == "check")
check("the summary names the failing command", "bash check.sh" in g.summary(rep))
Path(w, "src/a.py").write_text("a = 2\n", encoding="utf-8")
rep = g.run_gate(w, "main", checks)
check("passing checks and a clean diff mean ok", rep["ok"] is True and not rep["merge_block"] and rep["diff_lines"] == 2)
Path(w, "src/secret.py").write_text(f'T = "{tok}"\n', encoding="utf-8")
rep = g.run_gate(w, "main", checks)
check("criterion 6: an untracked file with a token blocks the gate", rep["ok"] is False and rep["secrets"])
check("checks do not even run when a secret is found", rep["checks"] == [])
Path(w, "src/secret.py").unlink()
rep = g.run_gate(w, "main", [])
check("no change at all is reported as empty", rep["ok"] is True)
git(["checkout", "-q", "--", "."], w)
check("the gate leaves no stray changes behind", g.run_gate(w, "main", [])["empty"] is True)

print()
if _fails:
    print(f"FAIL {len(_fails)} test: " + ", ".join(_fails))
    sys.exit(1)
print("TẤT CẢ PASS")
