"""Improve on the owner's request (2026-11-15): `server/self_upgrade.py` and the bundled tool `javis_improve`.

    python tests/run.py self_upgrade -v

Owner: "khi anh yêu cầu nó cải tiến thì nó cũng có thể thay đổi được chính nó và cải tiến toàn bộ hệ thống được",
scope: everything in the brain and Javis's own code. Checked here, no model, no network:
- only a turn the owner started may change anything (Auto's wake-ups, customer bots and turnless runs may not);
- only the brain's own definitions (agents, skills, workflows, loops, memory, its CLAUDE.md), never plugins, hidden
  folders, the learning switch or anything outside the brain;
- every save keeps a backup with an id; undo restores it (a created file is removed), an undo can be undone, a file
  edited again after the change keeps its current text in the undo;
- a definition file that would no longer load is refused (frontmatter, skill description over 150 characters);
- Javis's own code: attached next to the chat's other repos through GitHub in chat; GitHub not connected is said;
- update: refused while no newer release exists, otherwise starts the Update button's path after the turn ends;
- the tool is owner-only in the hub and needs Full access for source and update.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import importlib.util
import os
import tempfile
from pathlib import Path

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-self-upgrade-")

import mcp_hub  # noqa: E402
import plugins_host  # noqa: E402
import self_upgrade as SU  # noqa: E402
import turn_context  # noqa: E402

fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (f"  {str(extra)[:500]}" if extra and not cond else ""))
    if not cond:
        fails.append(name)


def raises(fn, *a, **kw):
    try:
        fn(*a, **kw)
    except SU.ImproveError as e:
        return str(e)
    return ""


BR = Path(tempfile.mkdtemp(prefix="javis-self-upgrade-brain-"))
(BR / "agents").mkdir()
AGENT = "---\nname: Lan\nrole: Trợ lý chạy bộ\n---\nBạn là Lan.\n"
(BR / "agents" / "lan.md").write_text(AGENT, encoding="utf-8")
(BR / "plugins" / "x").mkdir(parents=True)
(BR / "memory").mkdir()
OUT = Path(tempfile.mkdtemp(prefix="javis-self-upgrade-out-"))
root = str(BR)

# ═════ ai được sửa ═════
check("chủ trên dashboard: được", SU.owner_turn({"kenh": "dashboard", "la_chu": True}))
check("việc Kanban hay nhắc hẹn chủ đã giao: được", SU.owner_turn({"kenh": "kanban"})
      and SU.owner_turn({"kenh": "reminder"}))
check("lượt tự thức của Auto: không", not SU.owner_turn({"kenh": "pulse", "chat_id": "web:s"}))
check("bot nói với khách: không", not SU.owner_turn({"kenh": "zalo", "la_chu": False}))
check("không có lượt (loop, engine không mang khoá): không", not SU.owner_turn(None) and not SU.owner_turn({}))

# ═════ được sửa gì ═════
for p, kind in (("agents/lan.md", "agent"), ("skills/viet-email/SKILL.md", "skill"), ("workflows/bao-cao.md", "workflow"),
                ("Javis/loops/quet-don.md", "loop"), ("memory/agents/lan/MEMORY.md", "memory"),
                ("CLAUDE.md", "brain_rules"), (str(BR / "agents" / "lan.md"), "agent")):
    try:
        got = SU.resolve(root, p)[2]
    except SU.ImproveError as e:
        got = f"ERR {e}"
    check(f"vùng được sửa: {Path(p).name if os.path.isabs(p) else p} -> {kind}", got == kind, got)
for p in ("plugins/x/plugin.py", ".claude/settings.json", "agents/.hidden.md", "memory/learning.json",
          "memory/forgotten.json", "../ngoai.md", str(OUT / "a.md"), "settings.json", "agents"):
    check(f"không được sửa: {p}", bool(raises(SU.resolve, root, p)))

# ═════ lưu, sao lưu, hoàn tác ═════
new_agent = AGENT.replace("Bạn là Lan.", "Bạn là Lan. Luôn nhắc lấy BIB trước ngày chạy.")
c1 = SU.save(root, "agents/lan.md", content=new_agent, reason="Chủ bảo nhắc BIB", actor="dashboard", now=1000)
check("lưu: ghi file mới, có mã thay đổi và diff", (BR / "agents" / "lan.md").read_text(encoding="utf-8") == new_agent
      and c1["id"] == 1 and c1["added"] == 1 and c1["removed"] == 1 and "+Bạn là Lan. Luôn nhắc" in c1["diff"], c1)
check("lưu không đổi gì: không ghi thay đổi", SU.save(root, "agents/lan.md", content=new_agent).get("unchanged"))
c2 = SU.save(root, "agents/lan.md", edits=[{"old": "Luôn nhắc lấy BIB", "new": "Luôn nhắc lấy BIB và gửi xe"}])
check("sửa theo đoạn (edits)", "lấy BIB và gửi xe" in (BR / "agents" / "lan.md").read_text(encoding="utf-8")
      and c2["id"] == 2, c2)
check("edits: đoạn old không có hay có nhiều lần thì từ chối",
      bool(raises(SU.save, root, "agents/lan.md", edits=[{"old": "không có", "new": "x"}]))
      and bool(raises(SU.save, root, "agents/lan.md", edits=[{"old": "-", "new": "x"}])))
check("content và edits cùng lúc: từ chối", bool(raises(SU.save, root, "agents/lan.md", content="x",
                                                          edits=[{"old": "a", "new": "b"}])))
check("file định nghĩa mất frontmatter: từ chối, file giữ nguyên",
      bool(raises(SU.save, root, "agents/lan.md", content="Chỉ còn chữ")) and
      "lấy BIB và gửi xe" in (BR / "agents" / "lan.md").read_text(encoding="utf-8"))
long_desc = "---\nname: Viết email\ndescription: " + ("x" * 151) + "\n---\nThân\n"
check("skill: description quá 150 ký tự bị từ chối", "150" in raises(SU.save, root, "skills/viet-email/SKILL.md",
                                                                     content=long_desc))
c3 = SU.save(root, "skills/viet-email/SKILL.md", content="---\nname: Viết email\ndescription: Viết email ngắn\n---\nThân\n")
check("skill mới: tạo file, đánh dấu tạo mới", c3["created"] and (BR / "skills" / "viet-email" / "SKILL.md").is_file(), c3)
check("nội dung rỗng bị từ chối", bool(raises(SU.save, root, "memory/x.md", content="   ")))

u1 = SU.undo(root, c2["id"], actor="dashboard")
check("hoàn tác: về đúng bản trước", (BR / "agents" / "lan.md").read_text(encoding="utf-8") == new_agent
      and u1["undo_of"] == c2["id"], u1)
check("hoàn tác hai lần cùng một thay đổi: từ chối", "đã được hoàn tác" in raises(SU.undo, root, c2["id"])
      or "already undone" in raises(SU.undo, root, c2["id"]))
u2 = SU.undo(root, u1["id"])
check("hoàn tác chính lần hoàn tác: lấy lại bản đã sửa",
      "lấy BIB và gửi xe" in (BR / "agents" / "lan.md").read_text(encoding="utf-8"), u2)
u3 = SU.undo(root, c3["id"])
check("hoàn tác file đã tạo: xoá file", not (BR / "skills" / "viet-email" / "SKILL.md").exists() and u3["removed_file"])
c4 = SU.save(root, "memory/agents/lan/MEMORY.md", content="# Bộ nhớ\n- A\n")
(BR / "memory" / "agents" / "lan" / "MEMORY.md").write_text("# Bộ nhớ\n- A\n- B tự thêm sau\n", encoding="utf-8")
u4 = SU.undo(root, c4["id"])
check("file bị sửa thêm sau thay đổi: vẫn hoàn tác, có ghi chú và bản hiện tại hoàn tác lại được",
      u4.get("note") and not (BR / "memory" / "agents" / "lan" / "MEMORY.md").exists(), u4)
SU.undo(root, u4["id"])
check("hoàn tác lần đó: lấy lại cả dòng tự thêm sau",
      "B tự thêm sau" in (BR / "memory" / "agents" / "lan" / "MEMORY.md").read_text(encoding="utf-8"))
h = SU.history(root, 3)
check("lịch sử: mới nhất trước", [x["id"] for x in h] == sorted([x["id"] for x in h], reverse=True) and len(h) == 3, h)
check("mã thay đổi lạ: báo rõ", bool(raises(SU.undo, root, 999)) and bool(raises(SU.undo, root, "abc")))

# Skill hệ thống: sửa được khi chủ bảo, có câu nói rõ hệ quả.
import system_sync  # noqa: E402
_orig = system_sync.is_system_skill
system_sync.is_system_skill = lambda slug: slug == "javis-builder"
try:
    c5 = SU.save(root, "skills/javis-builder/SKILL.md", content="---\nname: B\ndescription: Dựng năng lực\n---\nx\n")
finally:
    system_sync.is_system_skill = _orig
check("skill hệ thống: sửa được, kèm ghi chú không còn tự cập nhật theo app", "note" in c5, c5)

# ═════ mã nguồn Javis ═════
import github_repos  # noqa: E402
state = {"connected": True, "repos": [{"full_name": "acme/shop"}], "attach": []}
gh = {k: getattr(github_repos, k) for k in ("status", "session_repos", "attach")}
github_repos.status = lambda: {"connected": state["connected"], "has_git": True}


def _session_repos(sid, brain=""):
    return [dict(r, worktree=f"/wt/{r['full_name']}", branch="javis/abc", can_push=True) for r in state["repos"]]


def _attach(sid, brain, brain_root, names):
    state["attach"].append((sid, brain, brain_root, list(names)))
    state["repos"] = [{"full_name": n} for n in names]
    return {}


github_repos.session_repos, github_repos.attach = _session_repos, _attach
try:
    got = SU.attach_source("s1", root)
    check("gắn mã nguồn Javis: giữ repo cũ của chat, thêm repo chính thức", state["attach"] == [
        ("s1", root, root, ["acme/shop", SU.SOURCE_REPO])] and got["attached"]["full_name"] == SU.SOURCE_REPO, state)
    SU.attach_source("s1", root)
    check("gắn lần hai: không gắn lại", len(state["attach"]) == 1)
    state["connected"] = False
    check("GitHub chưa kết nối: nói rõ cần làm gì", "GitHub" in raises(SU.attach_source, "s2", root))
    check("không rõ khung chat: từ chối", bool(raises(SU.attach_source, "", root)))
finally:
    for k, v in gh.items():
        setattr(github_repos, k, v)

# ═════ tự cập nhật ═════
calls = {"start": 0, "busy": [True, True, False]}


async def _start():
    calls["start"] += 1
    return {"ok": True, "mode": "native"}


def _busy(chat_id):
    return calls["busy"].pop(0) if calls["busy"] else False


async def _no_sleep(_s):
    await asyncio.sleep(0)


async def scenario():
    SU.wire(start=_start, versions=lambda: _v("0.562.0", "0.562.0"), turn_busy=_busy)
    same = await SU.schedule_update("web:s1", sleep=_no_sleep)
    SU.wire(versions=lambda: _v("0.562.0", "0.563.0"))
    ok = await SU.schedule_update("web:s1", sleep=_no_sleep, poll_s=0.01)
    again = await SU.schedule_update("web:s1", sleep=_no_sleep)
    await SU._UPDATE["task"]
    return same, ok, again


async def _v(a, b):
    return a, b


same, ok, again = asyncio.run(scenario())
check("chưa có bản mới hơn: không cập nhật, nói rõ chờ Release", not same["ok"] and "Release" in same["error"]
      and calls["start"] in (0, 1), same)
check("có bản mới: hẹn cập nhật, trả bản hiện tại và bản mới", ok["ok"] and ok["latest"] == "0.563.0", ok)
check("hẹn hai lần: không chạy đôi", again.get("already") or again.get("ok"), again)
check("cập nhật chạy SAU khi lượt chat kết thúc, đúng một lần", calls["start"] == 1 and calls["busy"] == [], calls)
check("so phiên bản theo số", SU._newer("0.563.0", "0.562.9") and not SU._newer("0.562.0", "0.562.0")
      and SU._newer("1.0.0", "0.999.9"))

# ═════ công cụ javis_improve ═════
spec = importlib.util.spec_from_file_location("javis_improve_plugin", ROOT / "system/plugins/javis-improve/plugin.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
ctx = plugins_host.PluginContext("javis-improve", "bundled", ROOT / "system/plugins/javis-improve", root)
mod.register(ctx)
tool = ctx._tools[0]
check("tool javis_improve đăng ký", tool["name"] == "javis_improve")
check("đọc trạng thái chạy ở mọi mức; sửa brain cần safe; mã nguồn và cập nhật chỉ Full",
      plugins_host._required_mode(tool, {"op": "status"}) == "readonly"
      and plugins_host._required_mode(tool, {"op": "save"}) == "safe"
      and plugins_host._required_mode(tool, {"op": "source"}) == "full"
      and plugins_host._required_mode(tool, {"op": "update"}) == "full"
      and not plugins_host._min_mode_ok(plugins_host._required_mode(tool, {"op": "save"}), "suggest"))
check("chỉ phiên của chủ thấy tool (bot khách không)", "javis_improve" in mcp_hub.OWNER_ONLY_TOOLS)


def call(args, turn):
    tok = turn_context.bind(turn) if turn is not None else None
    try:
        return asyncio.run(tool["handler"](args, ctx))
    finally:
        if tok is not None:
            turn_context.reset(tok)


before = (BR / "agents" / "lan.md").read_text(encoding="utf-8")
out = call({"op": "save", "path": "agents/lan.md", "content": before + "\nThêm.\n"},
           turn_context.make("pulse", chat_id="web:s1"))
check("tool: lượt tự thức của Auto bị từ chối, file giữ nguyên", out.startswith("ERROR") and "CHỦ" in out
      and (BR / "agents" / "lan.md").read_text(encoding="utf-8") == before, out)
out = call({"op": "save", "path": "agents/lan.md", "content": before + "\nThêm.\n"}, None)
check("tool: không có lượt thì cũng từ chối", out.startswith("ERROR"), out)
owner = turn_context.make("dashboard", chat_id="s9", la_chu=True, session_id="s9",
                          agent={"key": "ag_1", "slug": "lan", "config_version": 1})
out = call({"op": "save", "path": "agents/lan.md", "content": before + "\nThêm.\n", "reason": "Chủ bảo"}, owner)
check("tool: chủ yêu cầu thì lưu, trả mã hoàn tác và nhắc báo chủ", "op=undo id=" in out and "Thêm." in
      (BR / "agents" / "lan.md").read_text(encoding="utf-8"), out)
cid = SU.history(root, 1)[0]["id"]
out = call({"op": "undo", "id": cid}, owner)
check("tool: hoàn tác", f"Đã hoàn tác #{cid}" in out and (BR / "agents" / "lan.md").read_text(encoding="utf-8")
      == before, out)
out = call({"op": "save", "path": "plugins/x/plugin.py", "content": "x"}, owner)
check("tool: ngoài vùng thì báo lỗi rõ", out.startswith("ERROR") and "javis_plugin" in out, out)
SU.wire(versions=lambda: _v("0.562.0", "0.562.0"))
out = call({"op": "status"}, owner)
check("tool: trạng thái chỉ đúng file của chính trợ lý, thay đổi gần đây, phiên bản",
      "agents/lan.md" in out and "Thay đổi gần đây" in out and "v0.562.0" in out, out)
out = call({"op": "history"}, turn_context.make("pulse"))
check("tool: xem lịch sử không cần quyền chủ", out.startswith("#"), out)
out = call({"op": "update"}, turn_context.make("pulse"))
check("tool: cập nhật từ lượt tự thức bị từ chối", out.startswith("ERROR") and "CHỦ" in out, out)
out = call({"op": "update"}, owner)
check("tool: chủ bảo cập nhật mà chưa có bản mới thì nói rõ", out.startswith("ERROR") and "Release" in out, out)

src = (ROOT / "server" / "main.py").read_text(encoding="utf-8")
check("main: nối đường cập nhật của nút Cập nhật, phiên bản và lượt đang chạy",
      "self_upgrade.wire(start=_self_upgrade_start, versions=_self_upgrade_versions, turn_busy=luot_dang_chay.has_turn)"
      in src and "res = await _update_core()" in src and "return await _update_core()" in src)
check("prompt trợ lý: chủ bảo cải tiến thì dùng javis_improve, không ai bảo thì chỉ đề xuất",
      "CHỦ bảo cải tiến" in src and "`javis_improve`" in src)
claude_md = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")
core = (ROOT / "system" / "agents" / "javis-core.md").read_text(encoding="utf-8")
check("CLAUDE.md và vai Javis Core: cải tiến khi chủ yêu cầu qua javis_improve",
      "`javis_improve`" in claude_md and "`javis_improve`" in core)
for f in ("server/self_upgrade.py", "system/plugins/javis-improve/plugin.py", "system/plugins/javis-improve/plugin.yaml"):
    text = (ROOT / f).read_text(encoding="utf-8")
    check(f"không ký tự gạch ngang dài: {f}", "—" not in text and "–" not in text)

if fails:
    print(f"\n{len(fails)} FAIL")
    raise SystemExit(1)
print("\nTẤT CẢ OK")
