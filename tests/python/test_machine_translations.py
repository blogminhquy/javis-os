"""Machine-translated README and quick start (docs/i18n/<code>/, since 0.69.0).

    python tests/run.py machine_translations

The Chinese, Spanish and Japanese pages are generated from the English originals and nobody on
the team reads them closely, so whatever breaks in them breaks silently. This test checks what
a reader would hit first: dead relative links (the files sit three folders deep), in-page
anchors that no longer match the translated headings, a missing way back to the other
languages, and the translated-from marker that tools/check_translations.py uses to spot stale
copies. Staleness itself is NOT a failure here; that is a warning in the Translations workflow.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import importlib.util
import os
import re
import sys
import unicodedata
from pathlib import Path

R = Path(ROOT)
_fails = []


def check(name, ok, detail=""):
    print(f"{'ok  ' if ok else 'FAIL'} {name}" + ("" if ok else f"  [{detail}]"))
    if not ok:
        _fails.append(name)


_spec = importlib.util.spec_from_file_location("check_translations", R / "tools" / "check_translations.py")
ct = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ct)

LINK = re.compile(r"\]\(([^)\s]+)\)|<img[^>]*\bsrc=\"([^\"]+)\"")
CODE = re.compile(r"```.*?```|`[^`\n]*`", re.DOTALL)
HEADING = re.compile(r"^#{1,6}\s+(.+?)\s*#*\s*$", re.M)
PAIRS = {"README.md": "README.md", "QUICKSTART.md": "QUICKSTART.en.md"}


def slug(h: str) -> str:
    """GitHub's heading anchor: lowercase, drop punctuation and emoji, spaces to hyphens."""
    h = re.sub(r"<[^>]+>", "", h)
    h = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", h).replace("`", "").replace("*", "")
    # Keep letters, combining marks (Devanagari vowel signs are marks, which \w misses), digits.
    h = "".join(ch for ch in h.strip().lower()
                if ch in "-_ " or unicodedata.category(ch)[0] in "LMN")
    return h.replace(" ", "-")


def anchors(text: str) -> set:
    seen, out = {}, set()
    for h in HEADING.findall(CODE.sub("", text)):
        s = slug(h)
        n = seen.get(s, 0)
        out.add(s if n == 0 else f"{s}-{n}")
        seen[s] = n + 1
    return out


langs = sorted(p.name for p in (R / "docs" / "i18n").iterdir() if p.is_dir() and p.name not in ct.HAND_KEPT)
check("there are machine-translated languages", len(langs) >= 3, str(langs))

readme_en = (R / "README.md").read_text(encoding="utf-8")
quick_en = (R / "QUICKSTART.en.md").read_text(encoding="utf-8")

# Calibrate slug() on the English README, whose anchors GitHub already renders correctly.
_bad_en = [a for a in re.findall(r"\]\(#([^)]+)\)", CODE.sub(" ", readme_en)) if a not in anchors(readme_en)]
check("slug() reproduces the English README's own anchors", not _bad_en, ", ".join(_bad_en[:5]))

for code in langs:
    for name, source in PAIRS.items():
        p = R / "docs" / "i18n" / code / name
        rel = p.relative_to(R).as_posix()
        check(f"{rel} exists", p.is_file())
        if not p.is_file():
            continue
        text = p.read_text(encoding="utf-8")
        body = CODE.sub(" ", text)

        status, detail = ct.check(p)
        check(f"{rel}: translated-from marker names {source}",
              status in ("ok", "stale") and f"translated-from: {source} " in text.split("\n", 1)[0],
              detail)

        dead = []
        for m in LINK.finditer(body):
            target = (m.group(1) or m.group(2)).split("#")[0]
            if not target or target.startswith(("http://", "https://", "mailto:")):
                continue
            if not (p.parent / target).exists():
                dead.append(target)
        check(f"{rel}: every relative link resolves", not dead, ", ".join(dead[:5]))

        known = anchors(text)
        bad = [a for a in re.findall(r"\]\(#([^)]+)\)", body) if a not in known]
        check(f"{rel}: every in-page anchor matches a heading", not bad, ", ".join(bad[:5]))

        check(f"{rel}: links back to the English original",
              f"({os.path.relpath(R / source, p.parent)})" in text)
        dashes = text.count("—") + text.count("–") + text.count("―")
        check(f"{rel}: no em or en dash", dashes == 0, f"{dashes} found")

        src_sections = len(re.findall(r"^## ", CODE.sub("", (R / source).read_text(encoding="utf-8")), re.M))
        own_sections = len(re.findall(r"^## ", CODE.sub("", text), re.M))
        check(f"{rel}: same number of sections as {source}", src_sections == own_sections,
              f"{own_sections} vs {src_sections}")

    check(f"README.md language bar links docs/i18n/{code}/README.md",
          f"(docs/i18n/{code}/README.md)" in readme_en)
    check(f"QUICKSTART.en.md links docs/i18n/{code}/QUICKSTART.md",
          f"(docs/i18n/{code}/QUICKSTART.md)" in quick_en)

# Every language bar lists every language that exists, in the same order (run --bars to fix).
_stale_bars = ct.rewrite_bars(write=False)
check("language bars are complete and consistent (tools/check_translations.py --bars)",
      not _stale_bars, ", ".join(_stale_bars[:5]))

# The English README must not point at a translation that does not exist.
for code in re.findall(r"\(docs/i18n/([A-Za-z-]+)/README\.md\)", readme_en):
    check(f"README.md links an existing docs/i18n/{code}/README.md",
          (R / "docs" / "i18n" / code / "README.md").is_file())

if _fails:
    print(f"\nFAIL - {len(_fails)} check(s) failed")
    sys.exit(1)
print("\nOK - test_machine_translations: all pass")
