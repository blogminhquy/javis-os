# Contributing to Javis OS

*[Tiếng Việt](CONTRIBUTING.md) · **English***

Thank you for wanting to contribute. This repo accepts Pull Requests from **forks**, so you
need no direct write access, only a fork on your own account, your code, then a PR targeting
the `main` branch.

## The process

1. **Fork** this repo and clone your fork.
2. Create a branch named after the work in hand (`fix-zoom-mobile`, `them-mcp-notion`, say).
3. Write the code, then run the tests yourself before opening the PR (see Tests below); a PR
   with no local test run tends to trip over small things only CI catches.
4. Open the PR against `main` of the upstream repo (`blogminhquy/javis-os`), describing clearly
   **why** the change is needed, not only **what** changed (the what is visible in the diff).
5. CI (GitHub Actions) runs automatically. A PR merges only when green and approved; there is no
   auto-merge, the maintainer reviews each PR.

## Running the tests before opening a PR

```bash
pip install -r requirements.txt
python tests/run.py          # everything (Python + JS)
python tests/run.py --py     # Python only
python tests/run.py --js     # JS only
```

The script finds `.venv` if present and runs from any folder inside the repo.

## Code conventions

The project follows the conventions written in `CLAUDE.md` at the repo root (used by both people
and AI agents working on the repo), worth reading before a large change, especially these:

- Do not add features or refactors outside the scope of the PR in hand.
- Write comments only to explain **why** (a hidden constraint, a workaround), never repeating
  what the code already says (**what**).
- `CHANGELOG.md` is written for someone reading on a phone: a few bullets saying what the user
  **sees differently**, without naming functions or file paths (technical detail belongs in
  the PR).
- Do not use the em dash character; use the hyphen `-` instead.

## Reporting bugs and proposing features before coding

For a small change, open the PR directly. For a large feature or an architectural change, open an
**Issue** describing it first so the direction can be discussed, avoiding the case where the code
is finished but the direction does not fit the project.

## Translations

Javis already **replies** in whatever language you write in. What a translation adds is the
interface, the docs and the voice in that language. Three ways to help, from small to large:

1. **The README.** Translate [README.md](README.md) into `docs/i18n/<code>/README.md` (for
   example `docs/i18n/es/README.md`), fix the relative links (they go three folders up:
   `../../../`), and add your language to the language bar at the top of README.md.
2. **The dashboard.** Copy `dashboard/i18n/en.json` to `dashboard/i18n/<code>.json` and
   translate the values, never the keys. A half-finished file is fine: any key you have not
   translated yet falls back to English.
3. **The whole language.** Register it in `server/lang_registry.py` so the voice, date formats
   and currency follow it too. The step-by-step handbook is
   [docs/dev/them-mot-ngon-ngu.md](docs/dev/them-mot-ngon-ngu.md) (in Vietnamese for now;
   open an Issue and we will walk you through it).

English is the source language for the README. When you change it, update the translations or
mention in the PR which ones are now behind.

## Security issues

Do not report a security issue through a public Issue. Contact the maintainer directly.
