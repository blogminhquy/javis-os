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

## Security issues

Do not report a security issue through a public Issue. Contact the maintainer directly.
