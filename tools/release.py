"""Number releases on main from changelog fragments, so parallel PRs never fight over VERSION.

    python tools/release.py check                     # validate every fragment in changelog.d/
    python tools/release.py check changelog.d/x.md    # validate the given files
    python tools/release.py apply [--commit] [--reserved 0.460.0,0.461.0] [--date 2026-11-04]
    python tools/release.py pr-check --base origin/main [--optional]

Why: several Claude Code sessions work on this repo at once. Each used to pick the next
number itself and edit VERSION plus the top of both changelogs, so two PRs often claimed the same
number, and whichever merged second had to rebase and renumber (see docs/quy-uoc-dev.md). Now a PR
only adds one file `changelog.d/<slug>.md`, a name no other PR uses, and
`.github/workflows/release.yml` runs `apply --commit` on main after the merge: one version per
fragment, assigned one run at a time, so two merges seconds apart still get two distinct numbers.

Fragment format:

    ---
    bump: patch            # patch = fixes only, minor = anything new
    title: Short English title for the release commit
    ---
    ## vi
    ### Sửa lỗi
    - **Bold lead.** What the user sees differently.

    ## en
    ### Fixed
    - **Bold lead.** Same content in English.

Both languages must have the same number of `###` groups (tests/python/test_nhat_ky_song_ngu.py
enforces that on the assembled changelogs too).
"""
from __future__ import annotations

import argparse
import datetime as _dt
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FRAG_DIR_NAME = "changelog.d"

VI_SECTIONS = ("Thêm mới", "Sửa lỗi", "Cải thiện", "Bảo mật")
EN_SECTIONS = ("Added", "Fixed", "Improved", "Security")
SECTION_PAIR = dict(zip(VI_SECTIONS, EN_SECTIONS))
BUMPS = ("minor", "patch")

VER_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")
ENTRY_RE = re.compile(r"^## \[(\d+\.\d+\.\d+)\]", re.M)
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]*\.md$")
VI_MARKS = re.compile("[ăâđêôơưàáảãạằắẳẵặầấẩẫậèéẻẽẹềếểễệìíỉĩịòóỏõọồốổỗộờớởỡợùúủũụừứửữựỳýỷỹỵ]", re.I)
PR_REF_RE = re.compile(r"\(#(\d+)\)\s*$")
BANNED_DASHES = ("\u2014", "\u2013")

# Files a PR may change without shipping a release (pure documentation).
DOC_ONLY_RE = re.compile(r"^(docs/.*|[^/]+\.md|\.learn/.*|changelog\.d/README\.md)$")


class FragmentError(ValueError):
    pass


def parse_version(v: str) -> tuple[int, int, int]:
    m = VER_RE.match(v.strip())
    if not m:
        raise ValueError(f"not an x.y.z version: {v!r}")
    return tuple(int(x) for x in m.groups())  # type: ignore[return-value]


def fmt_version(t) -> str:
    return "%d.%d.%d" % tuple(t)


def _sections(body: str, allowed: tuple[str, ...], lang: str) -> list[tuple[str, list[str]]]:
    out: list[tuple[str, list[str]]] = []
    for raw in body.splitlines():
        line = raw.rstrip()
        if not line.strip():
            continue
        if line.startswith("### "):
            name = line[4:].strip()
            if name not in allowed:
                raise FragmentError(f"{lang}: unknown group '### {name}', use one of: {', '.join(allowed)}")
            out.append((name, []))
        elif line.startswith("- "):
            if not out:
                raise FragmentError(f"{lang}: bullet before any '### ' group")
            out[-1][1].append(line[2:].strip())
        elif line.startswith("  ") and out and out[-1][1]:
            continue  # continuation of the previous bullet
        else:
            raise FragmentError(f"{lang}: unexpected line {line[:60]!r} (only '### Group' and '- item')")
    if not out:
        raise FragmentError(f"{lang}: needs at least one '### ' group")
    for name, items in out:
        if not items:
            raise FragmentError(f"{lang}: group '### {name}' has no bullet")
    return out


def parse_fragment(text: str, name: str = "fragment") -> dict:
    """Parse and validate one fragment. Raises FragmentError with a message a person can act on."""
    for d in BANNED_DASHES:
        if d in text:
            raise FragmentError("contains an em dash or en dash, use '-' or rewrite the sentence")
    text = text.replace("\r\n", "\n").lstrip("﻿")
    m = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.S)
    if not m:
        raise FragmentError("must start with a '---' header block holding bump: and title:")
    meta: dict[str, str] = {}
    for line in m.group(1).splitlines():
        if not line.strip():
            continue
        if ":" not in line:
            raise FragmentError(f"header line without ':': {line!r}")
        k, v = line.split(":", 1)
        v = v.split(" #", 1)[0].strip()
        meta[k.strip()] = v
    bump = meta.get("bump", "")
    if bump not in BUMPS:
        raise FragmentError(f"bump must be one of {BUMPS}, got {bump!r}")
    title = meta.get("title", "")
    if not title:
        raise FragmentError("title: is required (English, used as the release commit subject)")
    if VI_MARKS.search(title):
        raise FragmentError("title must be English (commit messages are English)")
    if PR_REF_RE.search(title) or VER_RE.match(title.split(":", 1)[0]):
        raise FragmentError("title must not carry a version or (#PR), the release bot adds both")
    body = m.group(2)
    parts = re.split(r"^## (vi|en)\s*$", body, flags=re.M)
    if parts[0].strip():
        raise FragmentError("text before '## vi'")
    langs: dict[str, str] = {}
    for i in range(1, len(parts) - 1, 2):
        if parts[i] in langs:
            raise FragmentError(f"'## {parts[i]}' appears twice")
        langs[parts[i]] = parts[i + 1]
    if set(langs) != {"vi", "en"}:
        raise FragmentError("needs both a '## vi' block and a '## en' block")
    vi = _sections(langs["vi"], VI_SECTIONS, "vi")
    en = _sections(langs["en"], EN_SECTIONS, "en")
    if [SECTION_PAIR[n] for n, _ in vi] != [n for n, _ in en]:
        raise FragmentError("vi and en must have the same '###' groups in the same order "
                            f"(vi: {[n for n, _ in vi]}, en: {[n for n, _ in en]})")
    if VI_MARKS.search(langs["en"]):
        raise FragmentError("the '## en' block contains Vietnamese letters")
    return {"name": name, "bump": bump, "title": title, "vi": vi, "en": en}


def render(sections: list[tuple[str, list[str]]]) -> str:
    lines = []
    for name, items in sections:
        lines.append(f"### {name}")
        lines.extend(f"- {it}" for it in items)
    return "\n".join(lines)


def next_version(current: str, bump: str, reserved: set[str]) -> str:
    a, b, c = parse_version(current)
    while True:
        if bump == "minor":
            b, c = b + 1, 0
        else:
            c += 1
        v = fmt_version((a, b, c))
        if v not in reserved:
            return v


def insert_entry(changelog: str, version: str, date: str, body: str) -> str:
    block = f"## [{version}] - {date}\n{body}\n\n"
    m = ENTRY_RE.search(changelog)
    if not m:
        return changelog.rstrip("\n") + "\n\n" + block
    return changelog[:m.start()] + block + changelog[m.start():]


def top_version(changelog: str) -> str | None:
    m = ENTRY_RE.search(changelog)
    return m.group(1) if m else None


def _git(root: Path, *args: str) -> str:
    r = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, encoding="utf-8")
    if r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {r.stderr.strip()}")
    return r.stdout


def fragment_files(root: Path) -> list[Path]:
    d = root / FRAG_DIR_NAME
    if not d.is_dir():
        return []
    return sorted(p for p in d.iterdir() if p.is_file() and p.suffix == ".md" and p.name != "README.md")


def _added_order(root: Path) -> dict[str, tuple[int, str]]:
    """{fragment path: (age, subject of the commit that added it)}; higher age = merged earlier.

    Uses history order, not timestamps: merge commits on main are in merge order, while clock
    times can tie or go backwards. Empty outside git.
    """
    try:
        out = _git(root, "log", "--diff-filter=A", "--name-only", "--format=%x00%s", "--", FRAG_DIR_NAME)
    except (RuntimeError, OSError):
        return {}
    seen: dict[str, tuple[int, str]] = {}
    age, subject = 0, ""
    for line in out.splitlines():
        if line.startswith("\x00"):
            age += 1
            subject = line[1:]
        elif line.strip():
            seen[line.strip()] = (age, subject)  # later lines are older commits: keep the oldest
    return seen


def today_vn() -> str:
    try:
        from zoneinfo import ZoneInfo
        tz = ZoneInfo("Asia/Ho_Chi_Minh")
    except Exception:
        tz = _dt.timezone(_dt.timedelta(hours=7))
    return _dt.datetime.now(tz).strftime("%Y-%m-%d")


def apply(root: Path, reserved: set[str], date: str, commit: bool) -> list[str]:
    """Turn every fragment into its own release, oldest first. Returns the versions made."""
    files = fragment_files(root)
    if not files:
        return []
    order = _added_order(root)
    frags = []
    for p in files:
        rel = p.relative_to(root).as_posix()
        try:
            frag = parse_fragment(p.read_text(encoding="utf-8"), rel)
        except FragmentError as e:
            raise FragmentError(f"{rel}: {e}") from None
        age, subj = order.get(rel, (0, ""))
        pr = PR_REF_RE.search(subj)
        frag.update(path=p, rel=rel, age=age, pr=pr.group(1) if pr else "")
        frags.append(frag)
    frags.sort(key=lambda f: (-f["age"], f["rel"]))

    ver_path = root / "VERSION"
    vi_path, en_path = root / "CHANGELOG.md", root / "CHANGELOG.en.md"
    made = []
    for f in frags:
        vi_md = vi_path.read_text(encoding="utf-8")
        en_md = en_path.read_text(encoding="utf-8")
        current = ver_path.read_text(encoding="utf-8").strip()
        # Never go below what the changelog already shows (an old-style PR may have bumped only one).
        top = top_version(vi_md)
        if top and parse_version(top) > parse_version(current):
            current = top
        v = next_version(current, f["bump"], reserved)
        ver_path.write_text(v + "\n", encoding="utf-8")
        vi_path.write_text(insert_entry(vi_md, v, date, render(f["vi"])), encoding="utf-8")
        en_path.write_text(insert_entry(en_md, v, date, render(f["en"])), encoding="utf-8")
        f["path"].unlink()
        made.append(v)
        if commit:
            _git(root, "add", "--", "VERSION", "CHANGELOG.md", "CHANGELOG.en.md", f["rel"])
            subject = f"{v}: {f['title']}" + (f" (#{f['pr']})" if f["pr"] else "")
            _git(root, "commit", "-q", "-m", subject, "-m",
                 f"Released by tools/release.py from {f['rel']}.")
        print(f"{v}  {f['rel']}  ({f['bump']})")
    return made


def pr_check(root: Path, base: str, optional: bool) -> int:
    """CI gate for a PR branch: code changes need a fragment; old-style VERSION bumps still pass."""
    mb = _git(root, "merge-base", base, "HEAD").strip()
    changed = [ln for ln in _git(root, "diff", "--name-only", f"{mb}...HEAD").splitlines() if ln]
    added = [ln for ln in _git(root, "diff", "--name-only", "--diff-filter=A", f"{mb}...HEAD").splitlines() if ln]
    frags = [p for p in added if p.startswith(FRAG_DIR_NAME + "/") and p.endswith(".md")
             and not p.endswith("/README.md")]
    old_style = [p for p in changed if p in ("VERSION", "CHANGELOG.md", "CHANGELOG.en.md")]
    if old_style:
        print("::warning::This PR edits " + ", ".join(old_style) + " by hand. That still works, but it is the "
              "old way that makes parallel PRs collide on numbers. Next time add changelog.d/<slug>.md "
              "instead and leave VERSION alone (docs/quy-uoc-dev.md).")
        return 0
    if frags:
        bad = 0
        for p in frags:
            try:
                parse_fragment((root / p).read_text(encoding="utf-8"), p)
                print(f"ok   {p}")
            except FragmentError as e:
                print(f"::error file={p}::{e}")
                bad += 1
        return 1 if bad else 0
    code = [p for p in changed if not DOC_ONLY_RE.match(p)]
    if not code:
        print("Docs-only change, no release needed.")
        return 0
    msg = ("No changelog fragment. Add changelog.d/<slug>.md (format in tools/release.py and "
           "changelog.d/README.md); the release bot numbers it after merge. Do not edit VERSION.")
    if optional:
        print("::warning::" + msg + " (fork PR: the maintainer can add it.)")
        return 0
    print("::error::" + msg)
    return 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check")
    c.add_argument("files", nargs="*")
    a = sub.add_parser("apply")
    a.add_argument("--commit", action="store_true")
    a.add_argument("--reserved", default="")
    a.add_argument("--date", default="")
    a.add_argument("--root", default=str(ROOT))
    p = sub.add_parser("pr-check")
    p.add_argument("--base", default="origin/main")
    p.add_argument("--optional", action="store_true")
    args = ap.parse_args(argv)

    if args.cmd == "check":
        files = [Path(f) for f in args.files] or fragment_files(ROOT)
        bad = 0
        for f in files:
            try:
                parse_fragment(f.read_text(encoding="utf-8"), f.name)
                if not SLUG_RE.match(f.name):
                    raise FragmentError("file name must be lowercase a-z, 0-9 and '-', ending in .md")
                print(f"ok   {f}")
            except FragmentError as e:
                print(f"FAIL {f}: {e}")
                bad += 1
        return 1 if bad else 0
    if args.cmd == "apply":
        reserved = {v.strip() for v in args.reserved.replace("\n", ",").split(",") if VER_RE.match(v.strip())}
        try:
            made = apply(Path(args.root), reserved, args.date or today_vn(), args.commit)
        except FragmentError as e:
            print(f"::error::{e}")
            return 1
        if not made:
            print("No fragments, nothing to release.")
        return 0
    return pr_check(ROOT, args.base, args.optional)


if __name__ == "__main__":
    sys.exit(main())
