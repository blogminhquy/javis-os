"""Keep tests away from the live Javis they may be started next to.

Owner incident 2026-11-22 (and 2026-11-12 before it): on a VPS, Javis itself runs this repo's tests inside the live
container, whose environment holds JAVIS_STATE_DIR=/data/state (the real settings.json), BRAINS_DIR=/brains and
JAVIS_ADMIN_PASSWORD. tests/run.py passed that environment to every test, and about two hundred test files only set
their temp state folder with `os.environ.setdefault("JAVIS_STATE_DIR", ...)`, which keeps the live one. A test that
writes the account then writes it into the owner's machine. Both times the owner's password was gone right after a
test run, which left the public account form open to a stranger.

`scrub(env)` removes that inheritance, the same way for the runner (the environment it hands each test) and for every
test process (`_paths` calls it on import, so `python tests/python/test_x.py` and pytest are covered too):
- a folder variable that does not point inside the temp folder is dropped, so each test falls back to its own;
- the deploy variables (admin account, bind address, deploy target) are always dropped: CI never sets them, so a
  test sees exactly what it sees on CI.
A process that already went through it carries JAVIS_TEST_ENV_SCRUBBED, so a test that sets one of these on purpose
for a child process keeps it.
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

MARK = "JAVIS_TEST_ENV_SCRUBBED"

# Folders that hold the owner's data. Kept only when a test pointed them into the temp folder.
DIR_VARS = ("JAVIS_STATE_DIR", "BRAINS_DIR", "BRAIN_PATH", "OBSIDIAN_VAULT_PATH", "JAVIS_SESSIONS_DB")

# Settings of the deployed machine. A test that needs one sets it itself.
DEPLOY_VARS = ("JAVIS_ADMIN_PASSWORD", "JAVIS_ADMIN_USER", "JAVIS_RESET_2FA", "JAVIS_REQUIRE_LOGIN", "JAVIS_SETUP_2FA",
               "JAVIS_HOST", "JAVIS_BIND", "JAVIS_PORT", "JAVIS_HOST_PORT", "JAVIS_DEPLOY_TARGET",
               "JAVIS_AUTO_UPDATE", "DOMAIN_NAME", "JAVIS_NAME", "WATCHTOWER_TOKEN")


def _temp_roots(env) -> list:
    roots = [tempfile.gettempdir()]
    for k in ("JAVIS_TEST_TMP", "TMP", "TEMP", "TMPDIR"):
        if env.get(k):
            roots.append(env[k])
    out = []
    for r in roots:
        try:
            out.append(Path(r).resolve())
        except (OSError, RuntimeError):
            continue
    return out


def _inside(path: str, roots) -> bool:
    try:
        p = Path(path).resolve()
    except (OSError, RuntimeError):
        return False
    return any(p == r or r in p.parents for r in roots)


def scrub(env=None, *, mark: bool = True):
    """Drop the live machine's folders and deploy settings from `env` (os.environ when None). Returns it."""
    env = os.environ if env is None else env
    if env.get(MARK):
        return env
    roots = _temp_roots(env)
    for k in DIR_VARS:
        v = env.get(k)
        if v is not None and not _inside(v, roots):
            env.pop(k, None)
    for k in DEPLOY_VARS:
        env.pop(k, None)
    if mark:
        env[MARK] = "1"
    return env
