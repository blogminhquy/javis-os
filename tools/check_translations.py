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
    python tools/check_translations.py --bars    # rewrite every language bar from LANGS

Adding a language: add it to LANGS, put its files in docs/i18n/<code>/, run --bars. Bars only
ever list languages whose file exists, so a half-added language never shows a dead link.
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
# Order of the language bars. (code, flag, native name). English and Vietnamese live outside
# docs/i18n for historical reasons, see target().
LANGS = [
    ("en", "🇬🇧", "English"), ("vi", "🇻🇳", "Tiếng Việt"), ("zh", "🇨🇳", "简体中文"),
    ("es", "🇪🇸", "Español"), ("ja", "🇯🇵", "日本語"), ("hi", "🇮🇳", "हिन्दी"),
    ("pt-BR", "🇧🇷", "Português"), ("ko", "🇰🇷", "한국어"), ("ru", "🇷🇺", "Русский"),
    ("de", "🇩🇪", "Deutsch"), ("fr", "🇫🇷", "Français"), ("id", "🇮🇩", "Bahasa Indonesia"),
]
MARKER = re.compile(r"<!--\s*translated-from:\s*(\S+)\s+sha256:([0-9a-f]{6,64})\s*-->")


def lists_languages(line: str) -> bool:
    """Language bars and the README's language table row: they change whenever a language is
    added, which says nothing about whether a translation's content is current."""
    return line.count(" · ") >= 2 and "English" in line and "Tiếng Việt" in line


def source_hash(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    kept = "\n".join(line for line in text.split("\n") if not lists_languages(line))
    return hashlib.sha256(kept.encode("utf-8")).hexdigest()[:12]


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


def target(code: str, doc: str) -> Path:
    """Where `doc` ("README" or "QUICKSTART") lives for language `code`."""
    if doc == "README":
        return ROOT / "README.md" if code == "en" else I18N / code / "README.md"
    if code == "en":
        return ROOT / "QUICKSTART.en.md"
    return ROOT / "QUICKSTART.md" if code == "vi" else I18N / code / "QUICKSTART.md"


def bar(current: str, doc: str, here: Path) -> str:
    items = []
    for code, flag, name in LANGS:
        dest = target(code, doc)
        if not dest.is_file():
            continue
        label = f"{flag} {name}" if doc == "README" else name
        if code == current:
            items.append(f"{flag} **{name}**" if doc == "README" else f"**{name}**")
        else:
            items.append(f"[{label}]({os.path.relpath(dest, here.parent).replace(os.sep, '/')})")
    return " · ".join(items)


def is_bar(line: str, doc: str) -> bool:
    if not lists_languages(line) or line.startswith("|"):
        return False
    return "🌍" in line if doc == "README" else line.startswith("*")


def rewrite_bars(write: bool = True) -> list[str]:
    """Bring every language bar in line with LANGS. write=False only reports what would change."""
    changed = []
    for code, _flag, _name in LANGS:
        for doc in ("README", "QUICKSTART"):
            path = target(code, doc)
            if not path.is_file():
                continue
            lines = path.read_text(encoding="utf-8").split("\n")
            for i, line in enumerate(lines):
                if not is_bar(line, doc):
                    continue
                if doc == "README":
                    help_part = line[line.rindex(" · [🌍"):] if " · [🌍" in line else ""
                    new = bar(code, doc, path) + help_part
                else:
                    new = "*" + bar(code, doc, path) + "*"
                if new != line:
                    lines[i] = new
                    changed.append(path.relative_to(ROOT).as_posix())
                break
            if write and changed and changed[-1] == path.relative_to(ROOT).as_posix():
                path.write_text("\n".join(lines), encoding="utf-8")
    return changed


def main(argv: list[str]) -> int:
    if argv[:1] == ["--bars"]:
        for rel in rewrite_bars():
            print("updated", rel)
        return 0
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
