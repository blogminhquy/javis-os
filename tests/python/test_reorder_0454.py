"""The owner orders projects, pinned chats and tags by hand (0.454.0).

    python tests/run.py reorder_0454 -v

Owner, 04/11/2026: "sắp xếp thứ tự Project kéo thả như Brain ... các tag và các project hoặc ghim và cả đoạn chat".
Runs the real host on a temporary state folder; no model call.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import json
import os
import tempfile
import time
from pathlib import Path

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-reorder-")
BR = Path(tempfile.mkdtemp(prefix="javis-reorder-brain-"))

import main  # noqa: E402
import ui_order  # noqa: E402
from starlette.testclient import TestClient  # noqa: E402

fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(extra)[:300] + "]") if extra and not cond else ""))
    if not cond:
        fails.append(name)


main.cfgmod.gate_active = lambda: False
client = TestClient(main.app, base_url="http://127.0.0.1")
store = main.get_store()
b = str(BR)

# ═════ projects ═════
pid = {name: store.create_project(name, brain=b) for name in ("Alpha", "Beta", "Gamma")}
want = [pid["Gamma"], pid["Alpha"], pid["Beta"]]
r = client.post("/projects/order", data={"brain": b, "order": json.dumps(want)})
check("POST /projects/order saves the order", r.status_code == 200 and r.json().get("ok") and r.json()["ordered"] == 3, r.text)
got = [p["id"] for p in client.get("/projects", params={"brain": b}).json()["projects"]]
check("projects come back in the owner's order", got == want, got)
store.set_project_pinned(pid["Beta"], True)
got = [p["id"] for p in store.list_projects(brain=b)]
check("the owner's order wins over pinning", got == want, got)
store.create_project("Delta", brain=b)
lst = [p["name"] for p in store.list_projects(brain=b)]
check("a project never ordered comes after the ordered ones", lst[-1] == "Delta", lst)
check("a bad order is refused", client.post("/projects/order", data={"brain": b, "order": "{not json"}).status_code == 400)
other = str(Path(tempfile.mkdtemp(prefix="javis-reorder-b2-")))
o1, o2 = store.create_project("Một", brain=other), store.create_project("Hai", brain=other)
client.post("/projects/order", data={"brain": other, "order": json.dumps([o2, o1])})
client.post("/projects/order", data={"brain": b, "order": json.dumps(want[::-1])})
check("ordering one brain never touches another brain's projects",
      [p["id"] for p in store.list_projects(brain=other)] == [o2, o1])
r = client.post("/projects/order", data={"brain": b, "order": json.dumps([o1])})
check("a project of another brain cannot be ordered from this one", r.json()["ordered"] == 0, r.text)

# ═════ pinned chats ═════
sids = []
for i in range(4):
    sid = store.create_session(brain=b, channel="web")
    store.append_message(sid, "user", f"chat {i}")
    sids.append(sid)
    time.sleep(0.01)
for sid in sids[:3]:
    store.set_pinned(sid, True)
want = [sids[1], sids[2], sids[0]]
r = client.post("/sessions/pin-order", data={"order": json.dumps(want)})
check("POST /sessions/pin-order saves the order", r.status_code == 200 and r.json().get("ok") and r.json().get("ordered") == 3, r.text)
rows = client.get("/sessions", params={"brain": b}).json()
rows = rows.get("sessions", rows) if isinstance(rows, dict) else rows
order = [s["id"] for s in rows if s["id"] in sids]
check("pinned chats come first, in the owner's order", order[:3] == want, order)
check("a chat that is not pinned stays after them", order[3] == sids[3], order)
store.set_pinned(sids[1], False)
store.set_pinned(sids[1], True)
rows = client.get("/sessions", params={"brain": b}).json()
rows = rows.get("sessions", rows) if isinstance(rows, dict) else rows
order = [s["id"] for s in rows if s["id"] in sids]
check("pinned again: it goes after the ordered pins", order[:3] == [sids[2], sids[0], sids[1]], order)
r = client.post("/sessions/pin-order", data={"order": json.dumps([sids[3]])})
check("a chat that is not pinned takes no place", r.json().get("ordered") == 0, r.text)

# ═════ tags ═════
r = client.get("/ui/order")
check("GET /ui/order lists both tag scopes", r.status_code == 200 and set(r.json()["orders"]) == set(ui_order.SCOPES), r.text)
r = client.post("/ui/order", data={"scope": "tags_teams", "order": json.dumps(["b", "a", "b", "", 5])})
check("POST /ui/order saves a clean, distinct list", r.status_code == 200 and r.json()["order"] == ["b", "a"], r.text)
check("and it is read back", client.get("/ui/order").json()["orders"]["tags_teams"] == ["b", "a"])
check("the other scope is left alone", client.get("/ui/order").json()["orders"]["tags_agents"] == [])
check("an unknown scope is refused", client.post("/ui/order", data={"scope": "x", "order": "[]"}).status_code == 400)
check("ui_order caps the list", len(ui_order.clean([str(i) for i in range(900)])) == ui_order.MAX_ITEMS)

# ═════ the qualified native trial context still reads the store ═════
import sqlite3  # noqa: E402
import improvement_trial_sql_context as SQLCTX  # noqa: E402
conn = sqlite3.connect(str(store.db_path))
conn.row_factory = sqlite3.Row
for table, req, allowed in (("sessions", SQLCTX._SESSION_FIELDS, SQLCTX._SESSION_COLUMNS),
                            ("projects", SQLCTX._PROJECT_FIELDS, SQLCTX._PROJECT_COLUMNS)):
    try:
        SQLCTX._schema(conn, table, req, allowed)
        check(f"the order lives in its own table: {table} keeps the column list the trial context accepts", True)
    except ValueError as e:
        check(f"the order lives in its own table: {table} keeps the column list the trial context accepts", False, e)

print("\n" + ("XANH" if not fails else f"ĐỎ: {len(fails)} lỗi"))
raise SystemExit(1 if fails else 0)
