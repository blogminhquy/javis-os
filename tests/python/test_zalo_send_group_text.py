"""POST /zalo/send-group-text: a local-only route that sends one text to one Zalo GROUP.

    python tests/python/test_zalo_send_group_text.py

A class website running on the same machine calls it to send recordings and lessons to students' groups. The
login exemption itself (direct local calls only, never through a tunnel or proxy) is covered for every
_AUTH_LOCAL_EXACT path by test_local_exempt_tunnel.py. This file covers what the route accepts and refuses, and
that it always sends with the "group" chat type. No network: zalo_personal.gui is replaced.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import os
import sys
import tempfile

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-zalogroup-")

import main  # noqa: E402
from channels import zalo_personal  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

_fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + ("" if cond or not extra else "  " + str(extra)))
    if not cond:
        _fails.append(name)


calls = []
answer = {"value": (True, "")}


async def fake_gui(tk, chat_id, text, chat_type="private", mention=None):
    calls.append((tk.get("id"), chat_id, text, chat_type))
    if isinstance(answer["value"], Exception):
        raise answer["value"]
    return answer["value"]


zalo_personal.gui = fake_gui
main.cfgmod.gate_active = lambda: True
main.cfgmod.auth_enabled = lambda: True
local = TestClient(main.app, base_url="http://127.0.0.1:7777", client=("127.0.0.1", 50000))


def post(body):
    return local.post("/zalo/send-group-text", json=body).json()


check("the route is in the local-only list", "/zalo/send-group-text" in main._AUTH_LOCAL_EXACT)

for missing in ("conn_id", "thread_id", "text"):
    body = {"conn_id": "c1", "thread_id": "123", "text": "hi"}
    body[missing] = "  "
    r = post(body)
    check(f"missing {missing} is refused", r == {"ok": False, "error": "conn_id, thread_id and text are all required"}, r)

r = post({"conn_id": "c1", "thread_id": "abc", "text": "hi"})
check("a thread id that is not a number is refused", r.get("ok") is False and "digits" in r.get("error", ""), r)

r = post({"conn_id": "c1", "thread_id": "123", "text": "x" * 4001})
check("a text over 4000 characters is refused", r.get("ok") is False and "4000" in r.get("error", ""), r)
check("nothing was sent for the refused bodies", calls == [], calls)

r = post({"conn_id": "c1", "thread_id": "123", "text": "  Recording link  "})
check("a valid body is sent", r == {"ok": True, "error": ""}, r)
check("it always sends as a group, with the trimmed text", calls[-1:] == [("c1", "123", "Recording link", "group")], calls)

answer["value"] = (False, "group not found")
r = post({"conn_id": "c1", "thread_id": "123", "text": "hi"})
check("Zalo's refusal comes back as ok false", r == {"ok": False, "error": "group not found"}, r)

answer["value"] = RuntimeError("socket closed")
resp = local.post("/zalo/send-group-text", json={"conn_id": "c1", "thread_id": "123", "text": "hi"})
check("an exception is reported, never a 500", resp.status_code == 200 and "socket closed" in resp.json().get("error", ""),
      (resp.status_code, resp.text[:120]))

print()
if _fails:
    print(f"FAIL {len(_fails)} test")
    sys.exit(1)
print("ALL PASS")
