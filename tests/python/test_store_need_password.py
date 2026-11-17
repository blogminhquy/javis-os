"""The Store says a sign-in password is missing, instead of only "Sign in" (owner report 2026-11-17).

    python tests/run.py store_need_password      (no network)

A local install with no password opens every page without a login, but the Store (installing a pack runs
someone else's code in the server) needs a real session. With no password no session can exist, so the
Store was shut for good with a bare "Sign in to Javis to manage packs." The refusal now carries
`need_password` and says where to set one, while an install that has a password keeps the old message.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import json
import os
import tempfile

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-store-pw-"))

import routes.packs as packs_routes  # noqa: E402

fails = []


def check(name, cond, extra=None):
    print(("ok   " if cond else "FAIL ") + name + ("" if cond or extra is None else f"  [{extra}]"))
    if not cond:
        fails.append(name)


def refusal(password_set):
    orig = packs_routes.cfgmod.auth_enabled
    packs_routes.cfgmod.auth_enabled = lambda: password_set
    try:
        r = packs_routes._tu_choi()
    finally:
        packs_routes.cfgmod.auth_enabled = orig
    return r.status_code, json.loads(r.body)


code, body = refusal(False)
check("no password: still refused with 401", code == 401 and body.get("ok") is False, (code, body))
check("no password: says need_password", body.get("need_password") is True, body)
check("no password: the message points at the Account page",
      "Account" in body.get("error", "") or "Tài khoản" in body.get("error", ""), body.get("error"))

code, body = refusal(True)
check("password set: still refused with 401", code == 401, code)
check("password set: no need_password, so the page does not send people to set one again",
      body.get("need_password") is False, body)


def test_store_need_password():
    assert not fails, fails


if __name__ == "__main__":
    raise SystemExit(1 if fails else 0)
