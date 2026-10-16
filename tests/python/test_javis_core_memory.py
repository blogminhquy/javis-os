"""Memory under the person's control (0.188.0).

    python tests/python/test_javis_core_memory.py

Spec: owner, 16/10/2026 (Javis Core goal, sections 10, 12, 13 and 14; acceptance groups "Cá nhân hoá" and "Tự học").

- see what is remembered, with type, origin, source and dates; edit one; forget one;
- a forgotten memory is not learnt again from old chats (same slug or same text), and keeps no content;
- learning can be switched off per brain: no new memory from the learning loop, agent lessons or the model's file
  tool, the model is told so, and what is remembered is still used;
- the model cannot flip the switch or edit the forgotten list itself;
- a lesson the owner revoked is not re-learnt by the agent;
- the person's profile is shared by every brain and sits before the brain's own memory, which wins.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import json
import os
import tempfile
from pathlib import Path

STATE = tempfile.mkdtemp(prefix="javis-core-mem-")
os.environ["JAVIS_STATE_DIR"] = STATE

import agent_lessons as AL  # noqa: E402
import main  # noqa: E402
import memory_control as MC  # noqa: E402
import resonance_store as RS  # noqa: E402
from starlette.testclient import TestClient  # noqa: E402

fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(extra)[:300] + "]") if extra and not cond else ""))
    if not cond:
        fails.append(name)


main.cfgmod.gate_active = lambda: False
client = TestClient(main.app, base_url="http://127.0.0.1")
B = Path(tempfile.mkdtemp(prefix="javis-mem-b-"))
B2 = Path(tempfile.mkdtemp(prefix="javis-mem-b2-"))
mem = main._brain_memory_dir(str(B))
(mem / "facts").mkdir(parents=True, exist_ok=True)
(mem / "facts" / "xung-ho.md").write_text(
    "---\ntype: preference\ncreated: 2026-10-01\nupdated: 2026-10-02\nsource: chat 2026-10-02\nstatus: confirmed\n---\n"
    "Người dùng muốn được gọi là anh, trả lời ngắn.\n", encoding="utf-8")
(mem / "facts" / "kenh-ban.md").write_text(
    "---\ntype: business\norigin: javis-learned\nprovenance: user\ncreated: 2026-10-03\nupdated: 2026-10-03\n---\n"
    "Bán nước mắm qua Facebook và Zalo.\n", encoding="utf-8")
(mem / "MEMORY.md").write_text("# Bộ nhớ\n- [Xưng hô](facts/xung-ho.md) - gọi anh\n- [Kênh bán](facts/kenh-ban.md) - FB, Zalo\n",
                               encoding="utf-8")

# ---- 1. see ----
d = client.get("/memory/items", params={"brain": str(B)}).json()
by = {m["slug"]: m for m in d["items"]}
check("lists every memory with title, type, origin, source and dates",
      set(by) == {"xung-ho", "kenh-ban"} and by["xung-ho"]["title"] == "Xưng hô" and by["xung-ho"]["type"] == "preference"
      and by["xung-ho"]["source"] == "chat 2026-10-02" and by["kenh-ban"]["origin"] == "javis-learned", d)
check("learning is on by default", d["learning"] is True)

# ---- 2. edit ----
r = client.post("/memory/edit", json={"brain": str(B), "slug": "xung-ho", "body": "Gọi là anh Quý. Trả lời ngắn, có gạch đầu dòng."})
txt = (mem / "facts" / "xung-ho.md").read_text(encoding="utf-8")
check("edit rewrites the memory and marks it as the owner's, confirmed",
      r.json()["ok"] and "anh Quý" in txt and "origin: owner-edited" in txt and "status: confirmed" in txt
      and "source: chat 2026-10-02" in txt, txt)
check("edit of an unknown memory is a 404", client.post("/memory/edit", json={"brain": str(B), "slug": "x", "body": "y"}).status_code == 404)
check("a path in the slug is refused", client.post("/memory/forget", json={"brain": str(B), "slug": "../x"}).status_code == 400)

# ---- 3. forget ----
chat = main.get_store().create_session(brain=main._brain_key(str(B)), channel="web")
main.get_store().append_message(chat, "user", "Mình bán nước mắm qua Facebook và Zalo nhé")
r = client.post("/memory/forget", json={"brain": str(B), "slug": "kenh-ban"}).json()
idx = (mem / "MEMORY.md").read_text(encoding="utf-8")
fg = json.loads((mem / "forgotten.json").read_text(encoding="utf-8"))["items"]
check("forget removes the file and its index line", r["ok"] and not (mem / "facts" / "kenh-ban.md").exists()
      and "kenh-ban" not in idx and "xung-ho" in idx)
check("the forgotten list keeps a fingerprint and a title, not the content",
      fg and fg[0]["slug"] == "kenh-ban" and fg[0]["fp"] and "nước mắm" not in json.dumps(fg, ensure_ascii=False), fg)

feat = main.learn_feature
manifest = {"facts": [
    {"slug": "kenh-ban", "title": "Kênh bán", "body": "Bán hàng qua Facebook.", "confidence": 3},
    {"slug": "kenh-ban-2", "title": "Kênh bán", "body": "Bán nước mắm qua Facebook và Zalo.", "confidence": 3},
    {"slug": "gio-mo-cua", "title": "Giờ mở cửa", "body": "Cửa hàng mở 8h-21h.", "confidence": 3}]}
rep = feat._promote_sync(str(B), manifest, feat.read_config(), {"memory": True}, True)
check("the learning loop does not bring a forgotten memory back (same slug, or same text under a new slug)",
      not (mem / "facts" / "kenh-ban.md").exists() and not (mem / "facts" / "kenh-ban-2.md").exists()
      and (mem / "facts" / "gio-mo-cua.md").exists() and sum("đã yêu cầu quên" in b for b in rep["blocked"]) == 2, rep)
check("forgetting a memory does not delete the chat it came from",
      [m["content"] for m in main.get_store().get_messages(chat)] == ["Mình bán nước mắm qua Facebook và Zalo nhé"])

# ---- 4. learning switch ----
check("with learning on, the prompt carries no off-note",
      MC.LEARNING_OFF_NOTE.strip() not in main.build_system_prompt(str(B)))
client.post("/memory/learning", json={"brain": str(B), "enabled": False})
p = main.build_system_prompt(str(B))
check("off: the model is told, and what is remembered is still loaded",
      "GHI NHỚ MỚI ĐANG TẮT" in p and "Xưng hô" in p)
check("off: GET /memory/items says so", client.get("/memory/items", params={"brain": str(B)}).json()["learning"] is False)
check("another brain is not affected", "GHI NHỚ MỚI ĐANG TẮT" not in main.build_system_prompt(str(B2)))
before = sorted(x.name for x in (mem / "facts").glob("*.md"))
asyncio.new_event_loop().run_until_complete(feat.enqueue(str(B), "s1", "nhớ giúp tôi giờ đóng cửa là 22h", "Đã nhớ"))
check("off: a chat turn is not queued for learning",
      not any(str(B) in str(x) for x in getattr(feat, "_queue", []) or []) and sorted(x.name for x in (mem / "facts").glob("*.md")) == before)
calls = []
orig = AL.record_self_lessons
main.agent_lessons.record_self_lessons = lambda *a, **k: calls.append(k)
try:
    out = main._ket_luot_agent(str(B), "viet-bai", "viết lại", "Bài đây.\nJAVIS_LESSON: Chủ thích câu ngắn.")
finally:
    main.agent_lessons.record_self_lessons = orig
check("off: an agent's JAVIS_LESSON is stripped from the answer and not stored", calls == [] and "JAVIS_LESSON" not in out, (calls, out))
import mcp_hub  # noqa: E402
_tools, _route = mcp_hub._builtin_tools("full", str(B))
_write = _route["javis_write_file"]["call"]
_r1 = asyncio.new_event_loop().run_until_complete(_write({"path": "memory/facts/moi.md", "content": "x"}))
check("off: the model's file tool refuses to write under memory/ (called for real)",
      _r1.startswith("ERROR") and not (mem / "facts" / "moi.md").exists(), _r1)
_r2 = asyncio.new_event_loop().run_until_complete(_write({"path": "notes/ok.md", "content": "y"}))
check("off: writing elsewhere in the brain still works", not _r2.startswith("ERROR") and (B / "notes" / "ok.md").exists(), _r2)
_r3 = asyncio.new_event_loop().run_until_complete(_write({"path": "memory/learning.json", "content": '{"enabled": true}'}))
check("the model can never write the switch file", _r3.startswith("ERROR") and MC.learning_enabled(mem) is False, _r3)
client.post("/memory/learning", json={"brain": str(B), "enabled": True})
check("on again", MC.learning_enabled(mem) is True)

# ---- 5. a revoked lesson is not re-learnt ----
st = RS.GoalStore(Path(STATE) / "resonance-test.sqlite3")
lid = AL.add(st, agent_key="ag1", scope="dm:ag1", kind="method", text="Luôn gửi báo cáo lúc 7h.", source="self")
AL.revoke(st, lid, by="owner")
again = AL.add(st, agent_key="ag1", scope="dm:ag1", kind="method", text="Luôn gửi báo cáo lúc 7h.", source="self")
check("the agent cannot re-learn a lesson the owner revoked",
      again == lid and AL.get(st, lid)["status"] == "revoked"
      and not [r for r in AL.for_prompt(st, "ag1", AL.scopes_for("dm:ag1", "ag1")) if "7h" in r["text"]])
own = AL.add(st, agent_key="ag1", scope="dm:ag1", kind="method", text="Luôn gửi báo cáo lúc 7h.", source="owner")
check("the owner can still add it back on purpose", own != lid and AL.get(st, own)["status"] == "active")

# ---- 6. the person's profile ----
client.post("/profile", json={"text": "Gọi tôi là anh. Trả lời tiếng Việt, ngắn."})
p = main.build_system_prompt(str(B))
check("the profile is in every brain's prompt", "Gọi tôi là anh" in p and "Gọi tôi là anh" in main.build_system_prompt(str(B2)))
check("the profile sits before the brain's own memory (which wins where they differ)",
      p.index("HỒ SƠ NGƯỜI DÙNG") < p.index("BỘ NHỚ DÀI HẠN"))
check("GET /profile returns it", client.get("/profile").json()["text"].startswith("Gọi tôi là anh"))
client.post("/profile", json={"text": ""})
check("an empty profile adds nothing to the prompt", "HỒ SƠ NGƯỜI DÙNG" not in main.build_system_prompt(str(B)))
check("the profile survives a model change: it is a file, not a session",
      Path(STATE, "user_profile.md").exists())

print()
if fails:
    print(f"FAIL - {len(fails)} check(s)")
    raise SystemExit(1)
print("OK - test_javis_core_memory: all pass")
