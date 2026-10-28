"""0.374.0: ghim một câu trả lời vào mục lục của cuộc chat (nút ghim dưới câu trả lời).

    python tests/run.py message_pins

Qua đường host thật (main.app, TestClient), không gọi model nào. Các ca: ghim / bỏ ghim, lịch sử (`/sessions/{id}` và
`/sessions/{id}/messages`) mang cờ `pinned`, chỉ câu trả lời mới ghim được, tin hay cuộc không có thì 404, thân sai 400,
tua lại (xoá tin) và xoá cuộc thì ghim đi theo, ghim của cuộc này không lẫn sang cuộc khác.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import os
import tempfile

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-msg-pins-")

import main  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (f"  {str(extra)[:300]}" if extra and not cond else ""))
    if not cond:
        fails.append(name)


c = TestClient(main.app, base_url="http://127.0.0.1:8080")
store = main.get_store()
S1 = store.create_session(brain="brain")
S2 = store.create_session(brain="brain")
u1 = store.append_message(S1, "user", "Lên kế hoạch tháng 11")
a1 = store.append_message(S1, "assistant", "# Kế hoạch tháng 11\n\nTuần 1: ...")
u2 = store.append_message(S1, "user", "Thêm ngân sách")
a2 = store.append_message(S1, "assistant", "Ngân sách 20 triệu")
b1 = store.append_message(S2, "assistant", "Cuộc khác")


def pin(sid, mid, body):
    return c.post(f"/sessions/{sid}/messages/{mid}/pin", json=body)


def pinned_in(sid):
    msgs = c.get(f"/sessions/{sid}?limit=50").json().get("messages") or []
    return {m["id"]: m.get("pinned") for m in msgs if m.get("role") == "assistant"}


r = pin(S1, a1, {"pinned": True})
check("ghim câu trả lời: 200, pinned true", r.status_code == 200 and r.json() == {"ok": True, "pinned": True}, r.text)
check("lịch sử mang cờ pinned đúng từng câu", pinned_in(S1) == {a1: True, a2: False}, pinned_in(S1))
page = c.get(f"/sessions/{S1}/messages?limit=50").json().get("messages") or []
check("khúc tin cũ (cuộn lên) cũng mang cờ pinned", any(m["id"] == a1 and m.get("pinned") is True for m in page), page)
check("ghim lần nữa không nhân đôi", pin(S1, a1, {"pinned": True}).status_code == 200
      and store.pinned_message_ids(S1, [a1, a2]) == {a1})
check("tin người dùng không có cờ pinned", all("pinned" not in m for m in page if m.get("role") == "user"), page)

r = pin(S1, a1, {"pinned": False})
check("bỏ ghim: 200, pinned false", r.status_code == 200 and r.json()["pinned"] is False and pinned_in(S1)[a1] is False,
      r.text)

r = pin(S1, u1, {"pinned": True})
check("câu hỏi không ghim được (409)", r.status_code == 409 and r.json()["ok"] is False, r.text)
check("tin không có trong cuộc: 404", pin(S1, b1, {"pinned": True}).status_code == 404)
check("cuộc không có: 404", pin("khong-co", a1, {"pinned": True}).status_code == 404)
for bad in ({}, {"pinned": "yes"}, {"pinned": 1}):
    check(f"thân sai {bad}: 400", pin(S1, a1, bad).status_code == 400)
check("thân không phải JSON: 400",
      c.post(f"/sessions/{S1}/messages/{a1}/pin", content=b"x", headers={"content-type": "application/json"}).status_code == 400)

pin(S1, a2, {"pinned": True})
pin(S2, b1, {"pinned": True})
check("ghim của cuộc này không lẫn sang cuộc khác", pinned_in(S1) == {a1: False, a2: True} and pinned_in(S2) == {b1: True})

store.rewind_from(S1, u2)
check("tua lại xoá câu trả lời thì ghim của nó đi theo", store.pinned_message_ids(S1, [a2]) == set()
      and not store._read("SELECT 1 FROM message_pins WHERE message_id = ?", (a2,)))
store.delete(S2)
check("xoá cuộc thì ghim đi theo", not store._read("SELECT 1 FROM message_pins WHERE session_id = ?", (S2,)))

print()
if fails:
    raise SystemExit(f"FAIL {len(fails)}: " + "; ".join(fails[:5]))
print("TẤT CẢ PASS")
