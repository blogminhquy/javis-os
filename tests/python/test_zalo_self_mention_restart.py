"""Zalo self @mention survives a Javis restart without widening group replies.

    python tests/run.py zalo_self_mention_restart     (no network)
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import json
import os
import stat
import tempfile
import time
from pathlib import Path

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-zalo-self-")
import zalo_personal_channel as zc  # noqa: E402

_fails = []


def check(name, ok):
    print(("ok   " if ok else "FAIL ") + name)
    if not ok:
        _fails.append(name)


root = Path(tempfile.mkdtemp(prefix="javis-self-id-test-"))
zc._SELF_ID_PATH = root / "self-ids.json"
conn = "conn-lynx"
own = "912345678901234567"
other = "823456789012345678"
group = "776655443322110099"

# A trusted group echo is the only source of a persisted identity.
zc._ID_MINH.clear()
zc._hoc_danh_tinh(conn, {"from": own, "threadId": group, "threadType": 1,
                           "senderName": "Mika", "isSelf": True})
check("trusted own group echo is cached", zc._cached_self_uid(conn) == own)
if os.name == "posix":
    check("identity cache has owner-only permissions",
          stat.S_IMODE(zc._SELF_ID_PATH.stat().st_mode) == 0o600)

zc._ID_MINH.clear()  # Same effect as a process restart.
event = {"text": "@Mika cười giè", "metadata": {"mentions": [own]}}
tag, reply = zc.nhan_dien_goi(conn, event, ten_khac=("Lynx",))
check("real direct mention still targets Mika after restart", tag and not reply)

zc._ID_MINH.clear()
check("tag of another human is not a bot mention",
      zc.nhan_dien_goi(conn, {"text": "@Đạt cười giè",
                               "metadata": {"mentions": [other]}}, ("Lynx",)) == (False, False))
check("plain text @Mika without structured mention is not trusted",
      zc.nhan_dien_goi(conn, {"text": "@Mika cười giè", "metadata": {}}, ("Lynx",)) == (False, False))
check("a rounded/nearby long ID is not considered equal",
      zc.nhan_dien_goi(conn, {"text": "@Mika", "metadata": {"mentions": [own[:-1] + "8"]}},
                       ("Lynx",)) == (False, False))
check("a mixed mention including Mika is recognized",
      zc.nhan_dien_goi(conn, {"text": "@Đạt @Mika giúp với",
                               "metadata": {"mentions": [other, own]}}, ("Lynx",))[0])

# Private chat self echoes are not a safe source of an account UID.
zc._ID_MINH.clear()
zc._SELF_ID_PATH.unlink()
zc._hoc_danh_tinh(conn, {"from": other, "threadId": "999999999999999999", "threadType": 0,
                           "senderName": "Someone", "isSelf": True})
check("private self echo is not cached", not zc._SELF_ID_PATH.exists())

# A new confirmed self UID invalidates an old, cached identity, failing closed.
zc._ID_MINH.clear()
zc._hoc_danh_tinh(conn, {"from": own, "threadId": group, "threadType": 1,
                           "senderName": "Mika", "isSelf": True})
zc._ID_MINH.clear()
zc.nhan_dien_goi(conn, event, ("Lynx",))  # Restore old cached identity.
zc._hoc_danh_tinh(conn, {"from": other, "threadId": group, "threadType": 1,
                           "senderName": "Other", "isSelf": True})
check("identity disagreement clears the durable UID",
      zc._cached_self_uid(conn) == "" and zc._ID_MINH[conn]["uid"] == "")
check("conflicted identity does not re-learn a stale ID",
      zc.nhan_dien_goi(conn, event, ("Lynx",)) == (False, False))

# Cache must not become trusted if expired or corrupted.
zc._ID_MINH.clear()
zc._SELF_ID_PATH.write_text(json.dumps({conn: {"uid": own, "ts": time.time() - 31 * 86400}}),
                            encoding="utf-8")
check("expired self ID is ignored", zc._cached_self_uid(conn) == "")
zc._SELF_ID_PATH.write_text("not-json", encoding="utf-8")
check("invalid cache is ignored", zc._cached_self_uid(conn) == "")

print()
if _fails:
    print(f"{len(_fails)} FAIL")
    raise SystemExit(1)
print("ALL PASS")
