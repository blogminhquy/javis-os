"""System notices: server read state, asking Javis Core, push hygiene (0.187.0).

    python tests/python/test_javis_core_notices.py

Spec: owner, 16/10/2026 (Javis Core goal, sections 7, 8 and 15).

- the News tab's read set lives on the server: the same on every device, unchanged by switching brains;
- "Ask Javis Core" copies the notice, with its source and time, into the person's own Javis Core chat of the right
  brain, once; the shared notice is not changed;
- a push device is bound to the login it subscribed under: logout drops it, and an ended login receives nothing;
- "hide content" sends a push that only says something arrived.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import os
import tempfile
from pathlib import Path

STATE = tempfile.mkdtemp(prefix="javis-core-notice-")
os.environ["JAVIS_STATE_DIR"] = STATE

import inbox  # noqa: E402
import javis_core  # noqa: E402
import main  # noqa: E402
import webpush  # noqa: E402
from starlette.testclient import TestClient  # noqa: E402

fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(extra)[:300] + "]") if extra and not cond else ""))
    if not cond:
        fails.append(name)


def run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


main.cfgmod.gate_active = lambda: False
client = TestClient(main.app, base_url="http://127.0.0.1")
store = main.get_store()
A = Path(tempfile.mkdtemp(prefix="javis-notice-a-"))
B = Path(tempfile.mkdtemp(prefix="javis-notice-b-"))

NEWS = {"items": [{"id": "release:9.9.9", "kind": "update", "title": "Javis OS v9.9.9", "summary": "Bản mới",
                   "body": "• điểm 1", "published_at": "2026-10-16"},
                  {"id": "ann:bao-tri", "kind": "community", "title": "Bảo trì tối nay", "summary": "22h-23h",
                   "body": "", "published_at": "2026-10-16"}]}


async def fake_news():
    return NEWS

main._notifications_data = fake_news

# ---- 1. read state of the News tab on the server ----
check("starts empty", client.get("/notifications/read").json() == {"read": [], "initialized": False})
client.post("/notifications/read", json={"ids": ["ann:bao-tri"]})
check("marking on one device is visible to every device", client.get("/notifications/read").json()["read"] == ["ann:bao-tri"])
client.post("/notifications/read", json={"ids": ["ann:bao-tri"]})
check("marking twice keeps one entry", client.get("/notifications/read").json()["read"] == ["ann:bao-tri"])
client.post("/notifications/read", json={"all": True, "initialized": True})
st = client.get("/notifications/read").json()
check("read all marks every item shown, first-run pass recorded",
      set(st["read"]) == {"ann:bao-tri", "release:9.9.9"} and st["initialized"] is True, st)
js = (ROOT / "dashboard" / "notifications.js").read_text(encoding="utf-8")
check("the dashboard reads and writes it on the server (old local set pushed up once)",
      'fetch("/notifications/read"' in js and "guiDaDoc({ ids: chiMayNay, initialized: true })" in js
      and "guiDaDoc({ all: true })" in js)

# ---- 2. ask Javis Core about a notice ----
it = inbox.add("⚠ Bộ não AI ngừng trả lời", kind="system", source="system")
rep = inbox.add("✅ Việc 'Tổng hợp' đã hoàn thành.\nchi tiết", kind="report", source="kanban", label="Kanban",
                brain=main._brain_key(str(B)))
r = client.post("/javis-core/cite", json={"source": "inbox", "id": it["id"], "brain": str(A)})
sid = r.json().get("id")
msgs = store.get_messages(sid)
check("a system notice opens in Javis Core of the brain open now", r.status_code == 200
      and sid == javis_core.current_default(main._brain_key(str(A))) and msgs, r.text)
txt = str(msgs[-1]["content"]) if msgs else ""
check("the copy says what it is, where from, and that it is a snapshot",
      "Bộ não AI ngừng trả lời" in txt and "không phải trạng thái hiện tại" in txt
      and f"<!-- javis-cite:inbox:{it['id']} -->" in txt and msgs[-1]["role"] == "assistant", txt)
again = client.post("/javis-core/cite", json={"source": "inbox", "id": it["id"], "brain": str(A)}).json()
check("asking twice reuses the copy", again["reused"] is True and len(store.get_messages(sid)) == len(msgs))
r = client.post("/javis-core/cite", json={"source": "inbox", "id": rep["id"], "brain": str(A)}).json()
check("a report goes to Javis Core of ITS brain, not the brain open now",
      r["id"] == javis_core.current_default(main._brain_key(str(B))) and r["id"] != sid)
r = client.post("/javis-core/cite", json={"source": "news", "id": "ann:bao-tri", "brain": str(A)}).json()
check("a news item can be asked about too", r["id"] == sid
      and "Bảo trì tối nay" in str(store.get_messages(sid)[-1]["content"]))
check("the shared notice is unchanged", inbox.get(it["id"])["body"] == "⚠ Bộ não AI ngừng trả lời")
check("an unknown notice is a 404", client.post("/javis-core/cite", json={"source": "inbox", "id": "x"}).status_code == 404)
check("0.191.0: tapping a notice with no chat of its own opens it in Javis Core (no separate Ask button)",
      'if (!item.session_id) { closePanel(); hoiCore("inbox", item.id); return; }' in js
      and "openCommand(\"agent\", \"javis-core\", r.id)" in js)
check("0.191.0: no notice card carries an Ask Javis Core button any more", "nutHoi" not in js and "noti-ask" not in js)

# ---- 3. push devices bound to a login ----
webpush.SUBS_FILE.unlink(missing_ok=True)
sub = {"endpoint": "https://push.example/abc", "keys": {}}
orig_mh = webpush.ma_hoa
webpush.ma_hoa = lambda *a, **k: b""
try:
    ok, _ = webpush.dang_ky({"endpoint": "https://push.example/abc", "keys": {"p256dh": "p", "auth": "a"}}, "Phone",
                            phien=main._phien_bam("tok-1"))
    webpush.dang_ky({"endpoint": "https://push.example/def", "keys": {"p256dh": "p", "auth": "a"}}, "Laptop",
                    phien=main._phien_bam("tok-2"))
finally:
    webpush.ma_hoa = orig_mh
subs = webpush.danh_sach_sub()
check("a subscription keeps a hash of its login, never the token",
      ok and subs and all(s.get("phien") and "tok-" not in str(s) for s in subs), subs)
check("an ended login receives nothing (filtered before any network call)",
      run(webpush.gui_het("t", "b", phien_hop_le=set())) == (0, 0, []))
check("no login required (local use): nothing filtered", main._phien_con_hieu_luc() is None)
main.cfgmod.SESSIONS["tok-2"] = 9e12
client.cookies.set("javis_session", "tok-2")
client.post("/auth/logout")
client.cookies.clear()
left = [s["nhan"] for s in webpush.danh_sach_sub()]
check("logout drops that device, the other one stays", left == ["Phone"], left)

# ---- 4. hidden preview ----
seen = []


async def fake_push(title, body, url="/", tag="javis", phien_hop_le=None):
    seen.append((title, body))
    return 1, 0, []

orig = webpush.gui_het
webpush.gui_het = fake_push
try:
    client.post("/settings", data={"section": "push", "data": '{"preview": "hidden"}'})

    async def go():
        await main._bo_vao_hom_thu("", "Doanh thu hôm nay 12.500.000đ", kind="report")
        await asyncio.sleep(0.05)
    asyncio.get_event_loop().run_until_complete(go())
    check("hidden preview: the push does not carry the text",
          seen and seen[-1][0] == "Javis" and "12.500.000" not in seen[-1][1], seen)
    client.post("/settings", data={"section": "push", "data": '{"preview": "full"}'})
    asyncio.get_event_loop().run_until_complete(go())
    check("full preview again: the text is back", seen and "12.500.000" in seen[-1][1], seen)
finally:
    webpush.gui_het = orig
check("the inbox keeps the full report whatever the preview", "12.500.000" in inbox.danh_sach(1)[0]["body"])

print()
if fails:
    print(f"FAIL - {len(fails)} check(s)")
    raise SystemExit(1)
print("OK - test_javis_core_notices: all pass")
