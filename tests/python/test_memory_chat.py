"""Memory and lessons from chat: tool `javis_memory` (0.190.0).

    python tests/python/test_memory_chat.py

Owner, 16/10/2026: "thà nhắn tin bảo xóa sửa thu hồi rồi AI làm giúp còn tốt hơn". The memory list and the lesson lists
left the settings column; this tool does the same work from chat, on any engine. Runs the bundled plugin through the
real host (`main` wires `memory_chat`), no model call.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import importlib.util
import json
import os
import tempfile
from pathlib import Path

STATE = tempfile.mkdtemp(prefix="javis-memchat-")
os.environ["JAVIS_STATE_DIR"] = STATE
BR = Path(tempfile.mkdtemp(prefix="javis-memchat-brain-"))
(BR / "agents").mkdir()
(BR / "agents" / "viet-bai.md").write_text("---\nname: Viết bài\nrole: Viết bài Facebook\n---\nViết ngắn.\n",
                                           encoding="utf-8")

import agent_lessons as AL  # noqa: E402
import main  # noqa: E402
import mcp_hub  # noqa: E402
import memory_control as MC  # noqa: E402

fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(extra)[:300] + "]") if extra and not cond else ""))
    if not cond:
        fails.append(name)


spec = importlib.util.spec_from_file_location("javis_memory_plugin", ROOT / "system" / "plugins" / "javis-memory" / "plugin.py")
plugin = importlib.util.module_from_spec(spec)
spec.loader.exec_module(plugin)
regs = []


class Ctx:
    def __init__(self, vault_root):
        self.vault_root = vault_root
        self.slug = "javis-memory"

    def register_tool(self, *a, **kw):
        regs.append((a, kw))

    def register_hook(self, *a, **k):
        pass


plugin.register(Ctx(str(BR)))
(name, desc, handler), kw = regs[0]


def call(args, root=BR):
    return asyncio.new_event_loop().run_until_complete(handler(args, Ctx(str(root))))


check("one tool, javis_memory, at level safe", name == "javis_memory" and kw.get("min_mode") == "safe")
check("owner only: a customer-facing bot never sees it", "javis_memory" in mcp_hub.OWNER_ONLY_TOOLS)
check("description is plain and says the person has no other screen for this",
      "không có màn hình nào" in desc and "\u2014" not in desc and "\u2013" not in desc)
man = (ROOT / "system" / "plugins" / "javis-memory" / "plugin.yaml").read_text(encoding="utf-8")
check("manifest: bundled, on, lists the tool", "enabled: true" in man and "- javis_memory" in man)

# ---- memory of the brain ----
mem = main._brain_memory_dir(str(BR))
(mem / "facts").mkdir(parents=True, exist_ok=True)
(mem / "facts" / "kenh-ban.md").write_text("---\ntype: business\nsource: chat 2026-10-03\n---\nBán nước mắm qua Zalo.\n",
                                          encoding="utf-8")
(mem / "MEMORY.md").write_text("# Bộ nhớ\n- [Kênh bán](facts/kenh-ban.md) - Zalo\n", encoding="utf-8")
out = call({"op": "list"})
check("list: each memory with slug, type, source, and the learning switch",
      "kenh-ban | business | chat 2026-10-03" in out and "Ghi nhớ mới: BẬT" in out, out)
out = call({"op": "edit", "slug": "kenh-ban", "text": "Bán nước mắm qua Zalo và Facebook."})
txt = (mem / "facts" / "kenh-ban.md").read_text(encoding="utf-8")
check("edit rewrites it and marks it as the owner's", "Facebook" in txt and "origin: owner-edited" in txt, out)
check("edit of an unknown slug says so", call({"op": "edit", "slug": "khong-co", "text": "x"}).startswith("ERROR"))
out = call({"op": "forget", "slug": "kenh-ban"})
check("forget removes it, keeps only a fingerprint, says the chat stays",
      not (mem / "facts" / "kenh-ban.md").exists() and MC.is_forgotten(mem, slug="kenh-ban")
      and "nước mắm" not in json.dumps(MC.forgotten(mem), ensure_ascii=False) and "lịch sử chat" in out, out)
check("a path in the slug is refused", call({"op": "forget", "slug": "../x"}).startswith("ERROR"))
out = call({"op": "learning", "enabled": False})
check("learning off from chat", MC.learning_enabled(mem) is False and "TẮT" in out)
check("learning: no value means show", "TẮT" in call({"op": "learning"}))
call({"op": "learning", "enabled": True})
check("learning back on", MC.learning_enabled(mem) is True)
call({"op": "profile", "text": "Gọi tôi là anh. Trả lời ngắn."})
check("profile set from chat is in every brain's prompt", "Gọi tôi là anh" in main.build_system_prompt(str(BR)))
check("profile: no text means show", "Gọi tôi là anh" in call({"op": "profile"}))
call({"op": "profile", "text": ""})
check("profile: empty text clears it", MC.read_profile() == "")
check("no brain: refuses instead of guessing", call({"op": "list"}, root="").startswith("ERROR"))
check("unknown op lists the valid ones", "lesson_revoke" in call({"op": "x"}))

# ---- lessons of an assistant ----
out = call({"op": "lessons", "agent": "Viết bài"})
check("an assistant with no lessons yet: says so (found by its name)", "Chưa có bài học" in out, out)
out = call({"op": "lesson_add", "agent": "viet-bai", "text": "Luôn kèm giá trong bài."})
check("lesson_add: the person's own lesson, used everywhere", "dùng ở mọi nơi" in out, out)
key = main._agent_jobs_key(main._brain_key(str(BR)), "viet-bai")
store = main._pulse_store()
rows = AL.lessons(store, key, status="active")
check("it is stored as an owner lesson in scope *", rows and rows[0]["scope"] == "*" and rows[0]["source"] == "owner", rows)
lid = rows[0]["id"] if rows else 0
agmem = mem / "agents" / "viet-bai"
agmem.mkdir(parents=True, exist_ok=True)
(agmem / "MEMORY.md").write_text("# Viết bài\nPhần chủ viết.\n\n## Bài học (tự học)\n- Mở bài bằng câu hỏi\n- Dùng emoji\n",
                                 encoding="utf-8")
out = call({"op": "lessons", "agent": "viet-bai"})
check("lessons lists stored ones (L) and old file ones (C)",
      f"L{lid} | mọi nơi | owner" in out and "C1 | bài học cũ" in out and "C2 | bài học cũ (MEMORY.md) | Dùng emoji" in out, out)
out = call({"op": "lesson_revoke", "agent": "viet-bai", "id": f"L{lid}"})
check("revoke a stored lesson", "Đã thu hồi" in out and AL.get(store, lid)["status"] == "revoked", out)
check("revoking it again says there is none", call({"op": "lesson_revoke", "agent": "viet-bai", "id": f"L{lid}"}).startswith("ERROR"))
out = call({"op": "lesson_revoke", "agent": "viet-bai", "id": "C2"})
md = (agmem / "MEMORY.md").read_text(encoding="utf-8")
check("remove one old file lesson, the owner's own part untouched",
      "Dùng emoji" not in md and "Mở bài bằng câu hỏi" in md and "Phần chủ viết." in md, md)
check("an unknown assistant says so", call({"op": "lessons", "agent": "Không ai"}).startswith("ERROR"))

src = (ROOT / "server" / "main.py").read_text(encoding="utf-8")
# ---- the receipt under an answer, and no empty "đã quên" (memory_receipt) ----
import memory_receipt as R  # noqa: E402
import time as _t  # noqa: E402
(mem / "facts" / "gio-mo-cua.md").write_text("---\ntype: business\n---\nMở cửa 8h-21h.\n", encoding="utf-8")
(mem / "facts" / "xung-ho.md").write_text("---\ntype: preference\n---\nGọi là anh.\n", encoding="utf-8")
(mem / "MEMORY.md").write_text("# Bộ nhớ\n- [Giờ mở cửa](facts/gio-mo-cua.md)\n- [Xưng hô](facts/xung-ho.md)\n", encoding="utf-8")
snap = R.snapshot(mem)
check("nothing done in the turn: no receipt, and nothing changed", R.facts_diff(snap, mem) == [] and not R.changed(snap, mem))
_t.sleep(0.02)
(mem / "facts" / "kenh-moi.md").write_text("---\ntype: business\n---\nBán thêm qua TikTok.\n", encoding="utf-8")
(mem / "facts" / "xung-ho.md").write_text("---\ntype: preference\n---\nGọi là anh Quý.\n", encoding="utf-8")
call({"op": "forget", "slug": "gio-mo-cua"})
d = {i["slug"]: i for i in R.facts_diff(snap, mem)}
check("the receipt knows what was saved, changed and forgotten in the turn, with titles",
      d.get("kenh-moi", {}).get("act") == "new" and d["kenh-moi"]["title"] == "Bán thêm qua TikTok."
      and d.get("xung-ho", {}).get("act") == "updated" and d.get("gio-mo-cua", {}).get("act") == "forgot"
      and d["gio-mo-cua"]["title"] == "Giờ mở cửa", d)
blk = R.receipt_block(list(d.values()), "/brain/x")
check("hidden block the dashboard draws, with the brain for Undo", blk.startswith("<!-- JAVIS_NHO: ")
      and json.loads(blk[len("<!-- JAVIS_NHO: "):-4])["brain"] == "/brain/x")
check("plain fallback line", "Bán thêm qua TikTok." in R.receipt_text(list(d.values())))
snap2 = R.snapshot(mem)
check("a lesson added through the tool counts as a change (no file moves)",
      call({"op": "lesson_add", "agent": "viet-bai", "text": "Ngắn gọn."}) and R.changed(snap2, mem))
snap3 = R.snapshot(mem)
call({"op": "forget", "slug": "khong-co"})
check("a failed tool call is not a change", not R.changed(snap3, mem))
for t in ("Dạ em đã ghi nhớ anh thích báo cáo buổi sáng.", "Em đã quên ghi nhớ về kênh bán rồi ạ.",
          "Mình đã nhớ rồi nhé!", "Em đã thu hồi bài học đó.", "I will remember that from now on.", "Saved to memory."):
    check(f"claim caught: {t}", R.detect_claim(t) != "")
for t in ("Em nhớ là anh nói bán qua Zalo.", "Doanh thu hôm nay 12 triệu.", "I remember you said Zalo.",
          "Anh muốn em ghi nhớ điều gì không?", "`em đã ghi nhớ` là câu mẫu trong code"):
    check(f"not a claim: {t}", R.detect_claim(t) == "")
check("the note is plain and says what to do", "không đổi gì" in R.claim_note() and "\u2014" not in R.claim_note())
sid_r = main.get_store().create_session(brain=main._brain_key(str(BR)), channel="web")
pub = []


async def _pub(ev):
    pub.append(ev)

_orig_pub = main._CHAT_RUNTIME.publish
main._CHAT_RUNTIME.publish = _pub
try:
    asyncio.new_event_loop().run_until_complete(main.push_to_chat(sid_r, "Đã nhớ: x", nho=blk))
    asyncio.new_event_loop().run_until_complete(main.push_to_chat(sid_r, "y", nho="<script>"))
finally:
    main._CHAT_RUNTIME.publish = _orig_pub
msgs = [m["content"] for m in main.get_store().get_messages(sid_r)]
check("push_to_chat stores the receipt block with the line (F5 draws it again) and pushes it live",
      msgs and msgs[0].endswith(blk) and pub and pub[0]["content"].endswith(blk), msgs)
check("push_to_chat takes only a real receipt block, nothing else", msgs[-1] == "y", msgs)
check("the turn takes a snapshot first, then pushes the receipt or the note after saving",
      "_mem_snap = memory_receipt.snapshot(_brain_memory_dir(brain))" in src
      and "memory_receipt.facts_diff(_mem_snap, _brain_memory_dir(brain))" in src
      and "memory_receipt.detect_claim(final_text)" in src and "turn_started=(_mem_snap or {}).get(\"t0\") or 0" in src)
check("an agent lesson recorded in the turn counts as a change", "memory_control.note_change(_brain_memory_dir(brain))" in src)

# ---- the screen no longer carries these lists ----
ws = (ROOT / "dashboard" / "workspace.js").read_text(encoding="utf-8")
html = (ROOT / "dashboard" / "index.html").read_text(encoding="utf-8")
ra = (ROOT / "dashboard" / "resonance-agent.js").read_text(encoding="utf-8")
lui = (ROOT / "dashboard" / "agent-lessons-ui.js").read_text(encoding="utf-8")
check("the Javis Core card has no memory list", "JavisCoreMemory" not in ws and "core-memory.js" not in html
      and not (ROOT / "dashboard" / "core-memory.js").exists())
check("the Auto panel has no lessons list", "/resonance/lessons?" not in ra and "lessonsHtml" not in ra)
check("the pulse part keeps only the daily limit", "/revoke" not in lui and "/promote" not in lui and "legacy" not in lui
      and "lessons-budget-sel" in lui)

print()
if fails:
    print(f"FAIL - {len(fails)} check(s)")
    raise SystemExit(1)
print("OK - test_memory_chat: all pass")
