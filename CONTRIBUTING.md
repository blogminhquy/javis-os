# Contributing to Javis OS

***English** · [Tiếng Việt](docs/i18n/vi/CONTRIBUTING.md)*

Thank you for wanting to help. Javis is built by a small team in Vietnam and is opening up to contributors everywhere, so English is welcome in every issue, pull request and review.

By taking part you agree to follow the [Code of Conduct](CODE_OF_CONDUCT.md). Security problems go through [SECURITY.md](SECURITY.md), never a public issue.

## Ways to help

- **Report a bug** or **suggest a feature**: open an [issue](https://github.com/blogminhquy/javis-os/issues/new/choose) using the templates.
- **Translate** the interface, the docs or the connection store into your language (see [Translations](#translations)). This is the easiest way to start.
- **Add a connector** to the connection store, a **plugin** (a native Python tool every brain can call) or a **skill** (know-how in a markdown file).
- **Fix code.** Read [ARCHITECTURE.md](ARCHITECTURE.md) first. The code base was written in Vietnamese; [docs/dev/GLOSSARY.md](docs/dev/GLOSSARY.md) decodes the Vietnamese words in identifiers such as `chuan_hoa` (normalise) or `nhac_hen` (reminder).

For anything bigger than a small fix, open an issue first so the direction can be agreed before you write the code.

## Getting set up

```bash
git clone https://github.com/<you>/javis-os.git && cd javis-os
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt pytest
.venv/bin/python -m uvicorn main:app --app-dir server --port 7777   # http://localhost:7777
```

`install.sh` (Linux/macOS) and `install.ps1` (Windows) do the full install, including the CLI brains, if you want the complete app. To keep your experiments away from your real data, point `JAVIS_STATE_DIR` and `BRAINS_DIR` at a scratch folder.

## Running the tests

```bash
python tests/run.py          # everything (Python + JS), about 7 minutes
python tests/run.py --py     # Python only
python tests/run.py --js     # JS only (needs node)
python tests/run.py i18n     # only test files whose name contains "i18n"
```

The script finds `.venv` by itself and runs from any folder inside the repo. Tests are plain scripts that print `ok`/`FAIL` lines; run one directly with `python tests/python/test_<name>.py` to see its detail. CI runs the same suite on every pull request.

## The process

1. **Fork** the repo and create a branch named after the work (`fix-mobile-zoom`, `add-spanish-ui`).
2. Make the change and run the tests locally. A PR that never ran the tests tends to trip over small things only CI catches.
3. Open the PR against `main` of `blogminhquy/javis-os`. The template asks for **why** the change is needed, not only what changed: the diff already shows the what.
4. CI must be green. The maintainer reviews every PR; there is no auto-merge for outside contributions.

**Versions and changelogs:** each merge to `main` ships a new version (`VERSION` plus an entry in both [CHANGELOG.md](CHANGELOG.md), Vietnamese, and [CHANGELOG.en.md](CHANGELOG.en.md), English). As an outside contributor you can leave all three alone: the maintainer bumps the version and writes the entries when merging.

## Code conventions

- **Stay in scope.** No refactors or extra features beyond what the PR is about.
- **Comments explain why** (a hidden constraint, a workaround, a past bug), never what the next line already says.
- **No em dash character (U+2014) or en dash (U+2013)** anywhere, in code, docs or strings. Use a hyphen, comma or colon. The tests check this, because the dashes trip up text-to-speech.
- **Language of the code:** new modules, identifiers and comments are written in English. When you edit an existing file, follow that file's language so it stays consistent; you do not need to translate code you are not changing.
- **Text shown on screen is never hard-coded in one language:**
  - Dashboard: add a key to both `dashboard/i18n/vi.json` and `dashboard/i18n/en.json`, then call `t("your.key")`. `tests/js/test_i18n.mjs` fails on Vietnamese text in running JS code.
  - Server: write `localefmt.chu("Vietnamese text", "English text")`. If you do not write Vietnamese, put your English in both slots and say so in the PR; the maintainer will translate.
  - Prompts and tool descriptions sent to the AI model are a different case: they stay as they are (in Vietnamese). The model reads them fine and answers in the user's language.
- **Commit messages and PR descriptions** in English are preferred.

The maintainer's own working rules (version reservation, merge policy, how changelog entries are phrased) live in [docs/quy-uoc-dev.md](docs/quy-uoc-dev.md), in Vietnamese.

## Translations

Javis already **replies** in whatever language you write in. A translation adds the interface, the docs and the voice in that language. Three ways to help, from small to large:

1. **The README.** Translate [README.md](README.md) into `docs/i18n/<code>/README.md` (for example `docs/i18n/es/README.md`), fix the relative links (they go three folders up: `../../../`), and add your language to the language bar at the top of README.md.
2. **The dashboard.** Copy `dashboard/i18n/en.json` to `dashboard/i18n/<code>.json` and translate the values, never the keys. A half-finished file is fine: any key you have not translated yet shows in English.
3. **The whole language.** Register it in `server/lang_registry.py` so the voice, date formats and currency follow it too, and optionally add `system/mcp-catalog.<code>.json` for the connection store. The step-by-step handbook is [docs/dev/adding-a-language.md](docs/dev/adding-a-language.md).

English is the source language for the README. When you change it, update the translations or say in the PR which ones are now behind.

## Getting help

Ask in an issue, or comment on the PR you are working on. Questions in English or Vietnamese are both fine.
