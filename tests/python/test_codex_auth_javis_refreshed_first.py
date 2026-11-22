"""Javis refreshing the ChatGPT token first never brings the spent token back (2026-11-22).

    python tests/run.py codex_auth_javis_refreshed_first     (no network, CODEX_HOME in a temp folder)

Owner's report, 22/11/2026: ChatGPT signed out "for no reason", at the same time as Claude Code. The trace:

    settings R1 = disk R1 (Javis bridged its pair to ~/.codex/auth.json)
    a bot, an image, a voice turn or the model list calls valid_creds -> Javis refreshes -> settings R2, disk still R1
    the next Codex turn calls write_codex_auth -> "disk differs, so Codex rotated it" -> copies R1 over R2
    R2 is lost for good; R1 was spent -> "refresh token was already used", for Javis and for Codex alike

`tests/python/test_codex_auth_khong_giam_len_nhau.py` covers the other direction (Codex rotated first); this file covers
Javis rotating first, plus two refreshes at once.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import base64
import json
import os
import sys
import tempfile
import threading
import time

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-codex-first-")
os.environ["CODEX_HOME"] = tempfile.mkdtemp(prefix="javis-codex-first-home-")
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import config as cfgmod   # noqa: E402
import openai_oauth       # noqa: E402

_fails = []


def check(name, cond, extra=None):
    print(("ok   " if cond else "FAIL ") + name + ("" if cond or extra is None else f"  [{extra}]"))
    if not cond:
        _fails.append(name)


def _jwt(claims):
    body = base64.urlsafe_b64encode(json.dumps(claims).encode()).rstrip(b"=").decode()
    return "x." + body + ".y"


def _at(name, exp):
    """An access token that names itself and carries its expiry, like a real ChatGPT JWT."""
    return _jwt({"name": name, "exp": int(exp)})


ID_TOKEN = _jwt({"https://api.openai.com/auth": {"chatgpt_account_id": "acc-1", "chatgpt_plan_type": "plus"}})


def _set_javis(rt, at, expires_at):
    cfg = cfgmod.read_settings()
    cfg["model"]["openai_oauth"] = {"access_token": at, "refresh_token": rt, "id_token": ID_TOKEN,
                                    "account_id": "acc-1", "plan": "plus", "expires_at": expires_at}
    cfgmod.write_settings(cfg)


def _set_disk(rt, at):
    p = openai_oauth._codex_auth_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"OPENAI_API_KEY": None, "tokens": {
        "id_token": ID_TOKEN, "access_token": at, "refresh_token": rt, "account_id": "acc-1"}}), encoding="utf-8")


def _javis():
    return cfgmod.read_settings()["model"].get("openai_oauth") or {}


def _disk():
    return openai_oauth.doc_codex_auth()


class _Resp:
    def __init__(self, data):
        self._d = data

    def raise_for_status(self):
        pass

    def json(self):
        return self._d


SPENT = set()      # refresh tokens OpenAI has already taken
POSTS = []


def _fake_post(url, data=None, **kw):
    """OpenAI's token endpoint: each refresh token works once, then it is "already used"."""
    rt = (data or {}).get("refresh_token")
    POSTS.append(rt)
    time.sleep(0.05)
    if rt in SPENT:
        raise RuntimeError("refresh token was already used")
    SPENT.add(rt)
    n = len(SPENT) + 1
    return _Resp({"access_token": _at(f"AT{n}", time.time() + 3600), "refresh_token": f"R{n}",
                  "id_token": ID_TOKEN, "expires_in": 3600})


openai_oauth.httpx.post = _fake_post
now = time.time()

# ---- 1. The incident: Javis refreshes first, then a Codex turn runs ----
SPENT.clear()
POSTS.clear()
old_at = _at("AT1", now - 100)                  # expired
_set_javis("R1", old_at, now - 160)
_set_disk("R1", old_at)                         # bridged earlier: the same pair on disk
creds = openai_oauth.valid_creds()              # a bot, an image or the model list
check("Javis refreshes once with R1", POSTS == ["R1"] and creds and not creds.get("stale"), POSTS)
check("settings hold the new pair R2", _javis().get("refresh_token") == "R2", _javis().get("refresh_token"))
check("CANARY: the new pair is written to Codex's file at once", _disk().get("refresh_token") == "R2",
      _disk().get("refresh_token"))
openai_oauth.write_codex_auth()                 # the next Codex turn
check("CANARY: a Codex turn never brings the spent R1 back", _javis().get("refresh_token") == "R2",
      _javis().get("refresh_token"))

# ---- 2. Same, when the copy to disk did not happen (an older Javis wrote settings only) ----
SPENT.clear()
POSTS.clear()
SPENT.add("R1")
live_at = _at("AT2", now + 3600)
_set_javis("R2", live_at, now + 3540)
_set_disk("R1", old_at)                         # the spent pair, issued earlier
ok = openai_oauth.write_codex_auth()
check("CANARY: an OLDER pair on disk is not taken", _javis().get("refresh_token") == "R2",
      _javis().get("refresh_token"))
check("it is overwritten with the live pair instead", ok is True and _disk().get("refresh_token") == "R2", _disk())

# ...and valid_creds, once R2's access token expired, refreshes with R2, not with the spent R1 from disk.
POSTS.clear()
_set_javis("R2", _at("AT2", now - 10), now - 70)
_set_disk("R1", old_at)
creds = openai_oauth.valid_creds()
check("valid_creds refreshes with its own R2, never with the older R1 on disk", POSTS == ["R2"], POSTS)
check("  and the session is alive", bool(creds) and not creds.get("stale"), creds)

# ---- 3. Codex really rotated (its pair was issued later): taken, as before ----
SPENT.clear()
POSTS.clear()
_set_javis("R5", _at("AT5", now - 10), now - 70)
_set_disk("R6", _at("AT6", now + 3600))
creds = openai_oauth.valid_creds()
check("a NEWER pair on disk is taken without refreshing", POSTS == [] and _javis().get("refresh_token") == "R6",
      (POSTS, _javis().get("refresh_token")))
_set_javis("R5", _at("AT5", now + 100), now + 40)
_set_disk("R7", _at("AT7", now + 3600))
openai_oauth.write_codex_auth()
check("write_codex_auth takes a newer pair from disk", _javis().get("refresh_token") == "R7",
      _javis().get("refresh_token"))

# ---- 4. Two refreshes at once: only one reaches OpenAI ----
SPENT.clear()
POSTS.clear()
_set_javis("R1", old_at, now - 160)
_set_disk("R1", old_at)
results = []
threads = [threading.Thread(target=lambda: results.append(openai_oauth.valid_creds())) for _ in range(4)]
for t in threads:
    t.start()
for t in threads:
    t.join()
check("CANARY: four threads, one refresh", POSTS == ["R1"], POSTS)
check("every thread gets a live token", len(results) == 4 and all(r and not r.get("stale") for r in results), results)

# ---- 5. The old rule really lost the session (proves the canaries above can fail) ----
SPENT.clear()
SPENT.add("R1")
_set_javis("R2", live_at, now + 3540)
_set_disk("R1", old_at)
openai_oauth._nhan_token_tu_codex(_disk())      # what "different means newer" did
check("CANARY of the canaries: the old rule put the spent R1 back", _javis().get("refresh_token") == "R1",
      _javis().get("refresh_token"))

print()
if _fails:
    print(f"FAILED {len(_fails)}: {_fails}")
    sys.exit(1)
print("All passed")
