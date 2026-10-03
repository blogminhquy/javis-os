"""Report machine translations that have fallen behind their source.

Each translated file under docs/i18n/<code>/ (other than the hand-kept Vietnamese one) starts
with a marker naming its source and a hash of the source at the time it was translated:

    <!-- translated-from: README.md sha256:1a2b3c4d5e6f -->

When the source changes, the hash no longer matches and this script lists the translation as
stale. It never fails the build: an outdated translation is still useful, and blocking every
README edit on three re-translations would make the owner stop editing the README.

    python tools/check_translations.py           # human-readable list
    python tools/check_translations.py --github  # also emit ::warning annotations + job summary
    python tools/check_translations.py --stamp docs/i18n/es/README.md   # mark as up to date
"""
from __future__ import annotations

import hashlib
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
I18N = ROOT / "docs" / "i18n"
# Vietnamese is maintained by hand alongside the English original, not machine-translated.
HAND_KEPT = {"vi"}
MARKER = re.compile(r"<!--\s*translated-from:\s*(\S+)\s+sha256:([0-9a-f]{6,64})\s*-->")


def source_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:12]


def translations() -> list[Path]:
    if not I18N.is_dir():
        return []
    return sorted(p for p in I18N.glob("*/*.md") if p.parent.name not in HAND_KEPT)


def check(path: Path) -> tuple[str, str]:
    """Return (status, detail): status is ok, stale, unmarked or missing-source."""
    m = MARKER.search(path.read_text(encoding="utf-8").split("\n", 1)[0])
    if not m:
        return "unmarked", "first line has no translated-from marker"
    src = ROOT / m.group(1)
    if not src.is_file():
        return "missing-source", f"source {m.group(1)} does not exist"
    now = source_hash(src)
    if m.group(2)[:12] != now:
        return "stale", f"{m.group(1)} changed since translation ({m.group(2)[:12]} -> {now})"
    return "ok", m.group(1)


def stamp(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    first, _, rest = text.partition("\n")
    m = MARKER.search(first)
    if not m:
        sys.exit(f"{path}: no translated-from marker on the first line")
    new_first = MARKER.sub(f"<!-- translated-from: {m.group(1)} sha256:{source_hash(ROOT / m.group(1))} -->", first)
    path.write_text(new_first + "\n" + rest, encoding="utf-8")


def main(argv: list[str]) -> int:
    if argv[:1] == ["--stamp"]:
        for name in argv[1:]:
            stamp(Path(name).resolve())
        return 0
    github = "--github" in argv
    rows = []
    for p in translations():
        status, detail = check(p)
        rel = p.relative_to(ROOT).as_posix()
        rows.append((rel, status, detail))
        print(f"{status:15} {rel}  {detail if status != 'ok' else ''}".rstrip())
        if github and status != "ok":
            print(f"::warning file={rel},line=1::Translation {status}: {detail}")
    behind = [r for r in rows if r[1] != "ok"]
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if github and summary:
        with open(summary, "a", encoding="utf-8") as f:
            f.write("### Translations\n\n")
            if not behind:
                f.write(f"All {len(rows)} machine translations match their source.\n")
            else:
                f.write(f"{len(behind)} of {len(rows)} translations need updating:\n\n")
                for rel, status, detail in behind:
                    f.write(f"- `{rel}`: {detail}\n")
    print(f"\n{len(rows) - len(behind)}/{len(rows)} translations up to date")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
