"""Release numbering from changelog.d/ fragments (tools/release.py, .github/workflows/release.yml).

    python tests/run.py changelog_fragments

Why: parallel sessions used to pick version numbers inside their PRs and kept taking the same one.
Now a PR adds changelog.d/<slug>.md and the Release workflow numbers it after the merge. This file
checks the fragments in the repo, the numbering on a real throwaway git repo, the PR gate, and
that the workflows stay wired the way release.yml's header explains.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import importlib.util
import os
import subprocess
import sys
import tempfile
from pathlib import Path

_spec = importlib.util.spec_from_file_location("release_tool", ROOT / "tools" / "release.py")
rel = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rel)

_fails = []


def check(name, cond, detail=""):
    print(("ok   " if cond else "FAIL ") + name + ("" if cond else f"  [{detail}]"))
    if not cond:
        _fails.append(name)


def raises(text):
    try:
        rel.parse_fragment(text)
    except rel.FragmentError as e:
        return str(e)
    return ""


GOOD = """---
bump: patch
title: Large Zalo images send again
---
## vi
### Sửa lỗi
- **Gửi ảnh Zalo lớn không còn lỗi.** Trước đây ảnh trên 5 MB bị từ chối.

## en
### Fixed
- **Large Zalo images send again.** Images over 5 MB used to be refused.
"""

# ---- 1. Fragments that live in the repo right now are valid ----
for p in rel.fragment_files(ROOT):
    err = ""
    try:
        rel.parse_fragment(p.read_text(encoding="utf-8"), p.name)
    except rel.FragmentError as e:
        err = str(e)
    check(f"repo fragment {p.name} is valid", not err, err)
    check(f"repo fragment {p.name} has a slug file name", bool(rel.SLUG_RE.match(p.name)), p.name)
check("changelog.d/README.md explains the format", (ROOT / "changelog.d" / "README.md").is_file())

# ---- 2. Parser accepts the documented template and rejects the usual slips ----
f = rel.parse_fragment(GOOD)
check("good fragment parses", f["bump"] == "patch" and f["title"] == "Large Zalo images send again")
check("good fragment keeps both languages", f["vi"][0][0] == "Sửa lỗi" and f["en"][0][0] == "Fixed")
check("README template parses", not raises(
    (ROOT / "changelog.d" / "README.md").read_text(encoding="utf-8").split("```\n", 2)[1]))
check("rejects missing en block", "en" in raises(GOOD.split("## en")[0]))
check("rejects an em dash", "dash" in raises(GOOD.replace("Trước đây", "Trước đây \u2014")))
check("rejects Vietnamese title", "English" in raises(GOOD.replace("title: Large", "title: Ảnh lớn")))
check("rejects version in title", "version" in raises(GOOD.replace("title: Large", "title: 0.1.0: Large")))
check("rejects (#PR) in title", "(#PR)" in raises(GOOD.replace("send again\n---", "send again (#12)\n---")))
check("rejects unknown bump", "bump" in raises(GOOD.replace("bump: patch", "bump: major")))
check("rejects unknown group", "unknown group" in raises(GOOD.replace("### Fixed", "### Bugfixes")))
check("rejects mismatched groups", "same" in raises(GOOD.replace("### Fixed", "### Added")))
check("rejects Vietnamese in en block", "Vietnamese" in raises(GOOD.replace("used to be refused", "bị từ chối")))
check("rejects a group with no bullet", "no bullet" in raises(GOOD.replace(
    "### Fixed\n", "### Fixed\n### Improved\n").replace("### Sửa lỗi\n", "### Sửa lỗi\n### Cải thiện\n")))

# ---- 3. Numbering ----
check("minor bump", rel.next_version("0.459.0", "minor", set()) == "0.460.0")
check("patch bump", rel.next_version("0.459.0", "patch", set()) == "0.459.1")
check("skips numbers claimed by open PRs", rel.next_version("0.459.0", "minor", {"0.460.0", "0.461.0"}) == "0.462.0")

# ---- 4. apply() on a real throwaway repo ----
def git(cwd, *args):
    r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0, r.stderr
    return r.stdout


VI_HEAD = "# Nhật ký cập nhật\n\n***Tiếng Việt** · [English](CHANGELOG.en.md)*\n\nGhi chú.\n\n"
EN_HEAD = "# Changelog\n\n*[Tiếng Việt](CHANGELOG.md) · **English***\n\nNote.\n\n"
OLD_VI = "## [0.459.0] - 2026-11-03\n### Thêm mới\n- Cũ.\n"
OLD_EN = "## [0.459.0] - 2026-11-03\n### Added\n- Old.\n"

tmp = Path(tempfile.mkdtemp(prefix="rel-"))
env_git = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@e", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@e"}
os.environ.update(env_git)
git(tmp, "init", "-q", "-b", "main")
(tmp / "VERSION").write_text("0.459.0\n", encoding="utf-8")
(tmp / "CHANGELOG.md").write_text(VI_HEAD + OLD_VI, encoding="utf-8")
(tmp / "CHANGELOG.en.md").write_text(EN_HEAD + OLD_EN, encoding="utf-8")
(tmp / "changelog.d").mkdir()
(tmp / "changelog.d" / "README.md").write_text("doc\n", encoding="utf-8")
git(tmp, "add", "-A")
git(tmp, "commit", "-q", "-m", "base")

# The fragment merged FIRST has a name that sorts LAST, so order must come from git history.
NEW = GOOD.replace("bump: patch", "bump: minor").replace("Large Zalo images send again", "Teams get tags") \
    .replace("### Sửa lỗi", "### Thêm mới").replace("### Fixed", "### Added")
(tmp / "changelog.d" / "zz-teams-tags.md").write_text(NEW, encoding="utf-8")
git(tmp, "add", "-A")
git(tmp, "commit", "-q", "-m", "Teams get tags (#996)")
# Same clock second (or a clock going backwards) must not change the order: history decides.
os.environ["GIT_COMMITTER_DATE"] = "2020-01-01T00:00:00"
(tmp / "changelog.d" / "aa-zalo-images.md").write_text(GOOD, encoding="utf-8")
git(tmp, "add", "-A")
git(tmp, "commit", "-q", "-m", "Fix large Zalo images (#997)")
os.environ.pop("GIT_COMMITTER_DATE")

made = rel.apply(tmp, {"0.460.0"}, "2026-11-04", commit=True)
check("one version per fragment, oldest merge first, reserved number skipped",
      made == ["0.461.0", "0.461.1"], made)
check("VERSION is the last one", (tmp / "VERSION").read_text(encoding="utf-8").strip() == "0.461.1")
log = git(tmp, "log", "--format=%s", "-2").splitlines()
check("one commit per release, with title and PR number",
      log == ["0.461.1: Large Zalo images send again (#997)", "0.461.0: Teams get tags (#996)"], log)
check("fragments are removed, README stays",
      [p.name for p in (tmp / "changelog.d").iterdir()] == ["README.md"])
check("working tree is clean after commit", git(tmp, "status", "--porcelain") == "")

import main  # noqa: E402

vi = main._parse_changelog((tmp / "CHANGELOG.md").read_text(encoding="utf-8"))
en = main._parse_changelog((tmp / "CHANGELOG.en.md").read_text(encoding="utf-8"))
check("app reads the new entries newest first",
      [r["version"] for r in vi] == ["0.461.1", "0.461.0", "0.459.0"], [r["version"] for r in vi])
check("both changelogs list the same versions", [r["version"] for r in vi] == [r["version"] for r in en])
check("same number of groups per version in both languages",
      all(len(a["sections"]) == len(b["sections"]) for a, b in zip(vi, en)))
check("date and content land in the entry",
      vi[0]["date"] == "2026-11-04" and vi[0]["sections"][0]["title"] == "Sửa lỗi"
      and en[1]["sections"][0]["title"] == "Added"
      and en[1]["sections"][0]["items"][0].startswith("**Teams get tags.**"))
check("header text stays above the entries",
      (tmp / "CHANGELOG.md").read_text(encoding="utf-8").startswith(VI_HEAD + "## [0.461.1] - 2026-11-04\n"))
check("no fragments: nothing happens", rel.apply(tmp, set(), "2026-11-04", commit=True) == [])

# A changelog ahead of VERSION (half an old-style bump) never makes the numbers go down.
(tmp / "VERSION").write_text("0.400.0\n", encoding="utf-8")
(tmp / "changelog.d" / "x.md").write_text(GOOD, encoding="utf-8")
check("starts from the higher of VERSION and the changelog",
      rel.apply(tmp, set(), "2026-11-04", commit=False) == ["0.461.2"])
git(tmp, "checkout", "-q", "--", ".")

# A broken fragment stops the run before anything is written.
(tmp / "changelog.d" / "bad.md").write_text(GOOD.replace("## en", "## fr"), encoding="utf-8")
try:
    rel.apply(tmp, set(), "2026-11-04", commit=True)
    broke = ""
except rel.FragmentError as e:
    broke = str(e)
check("broken fragment is named in the error", "changelog.d/bad.md" in broke, broke)
check("broken fragment leaves VERSION alone", (tmp / "VERSION").read_text(encoding="utf-8").strip() == "0.461.1")
(tmp / "changelog.d" / "bad.md").unlink()

# ---- 5. PR gate ----
def gate(files, optional=False):
    git(tmp, "checkout", "-q", "-B", "work", "main")
    for name, text in files.items():
        p = tmp / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    git(tmp, "add", "-A")
    git(tmp, "commit", "-q", "-m", "work")
    return rel.pr_check(tmp, "main", optional)


check("gate: code with fragment passes", gate({"server/a.py": "x=1\n", "changelog.d/a.md": GOOD}) == 0)
check("gate: code without fragment fails", gate({"server/a.py": "x=2\n"}) == 1)
check("gate: fork PR without fragment only warns", gate({"server/a.py": "x=3\n"}, optional=True) == 0)
check("gate: docs-only change needs no fragment", gate({"docs/x.md": "y\n", "README.md": "z\n"}) == 0)
check("gate: old-style VERSION bump still passes", gate({"server/a.py": "x=4\n", "VERSION": "0.462.0\n"}) == 0)
check("gate: broken fragment fails", gate({"server/a.py": "x=5\n", "changelog.d/b.md": GOOD.replace("## en", "")}) == 1)

# ---- 6. Workflow wiring ----
wf = (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")
dp = (ROOT / ".github/workflows/docker-publish.yml").read_text(encoding="utf-8")
ci = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
check("release runs on push to main, one numbering run at a time",
      "branches: [main]" in wf and "group: release-version" in wf and "cancel-in-progress: false" in wf)
check("release lands through a PR merged with the owner token (ruleset on main)",
      "secrets.RELEASE_TOKEN" in wf and "gh pr merge" in wf and "--admin" in wf and "--rebase" in wf)
check("release skips numbers claimed in open PR titles", "gh pr list" in wf and "--reserved" in wf)
check("release calls the image build on the newest main",
      "uses: ./.github/workflows/docker-publish.yml" in wf and "ref: main" in wf)
check("image build no longer runs on its own push (it would carry the old VERSION)",
      "workflow_call:" in dp and "\n  push:" not in dp and "ref: ${{ inputs.ref || github.sha }}" in dp)
check("CI gates PRs on the fragment and the `test` check waits for it",
      "release.py pr-check" in ci and "needs: [python, chung, changelog]" in ci)
for name, text in (("release.yml", wf), ("release.py", (ROOT / "tools/release.py").read_text(encoding="utf-8"))):
    check(f"{name}: no em dash / en dash", "\u2014" not in text and "\u2013" not in text)

print()
if _fails:
    print(f"FAILED {len(_fails)}: {_fails}")
    sys.exit(1)
print("OK - test_changelog_fragments: all pass")
