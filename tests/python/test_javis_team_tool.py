"""Tool `javis_team` (0.173.0): Javis tạo, sửa, lưu trữ, xoá nhóm chat và tạo trợ lý có model riêng, ngay từ chat.

    python tests/run.py javis_team_tool

Chạy qua host thật (`main` + `team_api.current()`), không gọi model: không gửi tin nào vào nhóm nên không có lượt nhóm.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import importlib.util
import os
import tempfile
from pathlib import Path

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-team-tool-")
BR = Path(tempfile.mkdtemp(prefix="javis-team-tool-brain-"))
BR2 = Path(tempfile.mkdtemp(prefix="javis-team-tool-brain2-"))
(BR / "agents").mkdir()
for slug, name in (("lan", "Lan"), ("minh", "Minh"), ("hoa", "Hoa")):
    (BR / "agents" / f"{slug}.md").write_text(f"---\nname: {name}\nrole: Thành viên\n---\nBạn là {name}.\n",
                                              encoding="utf-8", newline="\n")
(BR2 / "agents").mkdir()

import main  # noqa: E402
import mcp_hub  # noqa: E402
import team_api  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (f"  {extra}" if extra and not cond else ""))
    if not cond:
        fails.append(name)


async def _publish(ev):
    return None


main._CHAT_RUNTIME.publish = _publish
main._TEAM_API.deps.spawn = lambda job: job.close() if asyncio.iscoroutine(job) else None


def _no_engine(team, key, role):
    raise AssertionError("javis_team không được mở lượt nhóm nào")


main._TEAM_API.deps.engine_for = _no_engine

spec = importlib.util.spec_from_file_location("javis_team_plugin", ROOT / "system" / "plugins" / "javis-team" / "plugin.py")
plugin = importlib.util.module_from_spec(spec)
spec.loader.exec_module(plugin)
regs = []


class Ctx:
    def __init__(self, vault_root):
        self.vault_root = vault_root
        self.slug = "javis-team"

    def register_tool(self, *a, **kw):
        regs.append((a, kw))

    def register_hook(self, *a, **k):
        pass


plugin.register(Ctx(str(BR)))
args0, kw0 = regs[0]
check("đăng ký đúng 1 tool javis_team, min_mode safe", len(regs) == 1 and args0[0] == "javis_team"
      and kw0.get("min_mode") == "safe", regs)
handler = args0[2]
check("javis_team là tool chỉ của chủ (bot chăm khách không thấy)", "javis_team" in mcp_hub.OWNER_ONLY_TOOLS)
check("team_api.current() có TeamOps sau khi host đăng ký", isinstance(team_api.current(), team_api.TeamOps))


def run(args, root=BR):
    return asyncio.run(handler(args, Ctx(str(root) if root else "")))


r = run({"op": "list_agents"})
check("list_agents: thấy ba trợ lý có sẵn, model chính", all(s in r for s in ("lan", "minh", "hoa")) and "model chính" in r, r)
check("không biết brain: lỗi rõ, không đoán", run({"op": "list"}, root=None).startswith("ERROR"))
check("op lạ: lỗi liệt kê op hợp lệ", "create_agent" in run({"op": "bay"}))

# Tạo trợ lý có model mà thiếu provider bị từ chối giống hệt POST /agents
r_no_prov = run({"op": "create_agent", "name": "Thiếu nhà", "role": "Thử", "model": "haiku"})
check("create_agent có model mà thiếu model_provider: từ chối", r_no_prov.startswith("ERROR"), r_no_prov)

# Tạo nhóm một lần: hai trợ lý mới (model riêng + mặc định) + một trợ lý có sẵn, trưởng nhóm theo slug
r = run({"op": "create", "name": "Phòng thử 3 AI", "members": ["lan"], "leader": "lan",
         "new_agents": [{"name": "Người phản biện", "role": "Tìm điểm yếu, đưa cách sửa", "model": "sonnet",
                         "model_provider": "anthropic-cli"},
                        {"name": "Người tóm tắt", "role": "Tóm tắt sau thảo luận", "model": "haiku",
                         "model_provider": "anthropic-cli"}]})
check("create: báo đã tạo, có trợ lý mới", r.startswith("Đã tạo nhóm") and "nguoi-phan-bien" in r, r)
pb = (BR / "agents" / "nguoi-phan-bien.md").read_text(encoding="utf-8")
tt = (BR / "agents" / "nguoi-tom-tat.md").read_text(encoding="utf-8")
check("trợ lý mới ghi đúng model và provider vào file", "model: sonnet" in pb and "model_provider: anthropic-cli" in pb
      and "model: haiku" in tt and "model_provider: anthropic-cli" in tt, (pb, tt))
ops = team_api.current()
teams = ops.api.teams().list_teams(main._brain_key(str(BR)))
check("nhóm có đúng 3 thành viên, Lan là trưởng nhóm", len(teams) == 1
      and len(ops.api.teams().members(teams[0]["team_id"])) == 3
      and teams[0]["leader_key"] == ops.member_key(teams[0], "lan"), teams)
tid = teams[0]["team_id"]
check("phiên chat của nhóm có thật (nhóm hiện trên trang Nhóm)",
      main.get_store().get_session(teams[0]["session_id"]) is not None)

r = run({"op": "create", "name": "Nhóm lỗi", "members": ["khong-co"]})
check("create với trợ lý không có: lỗi, không tạo nhóm", r.startswith("ERROR") and "khong-co" in r
      and len(ops.api.teams().list_teams(main._brain_key(str(BR)))) == 1, r)

check("get theo TÊN nhóm", "Phòng thử 3 AI" in run({"op": "get", "team": "phòng thử 3 ai"}))
check("list: thấy nhóm và model riêng", "[sonnet]" in run({"op": "list"}))
check("brain khác không thấy nhóm này", run({"op": "get", "team": tid}, root=BR2).startswith("ERROR"))

r = run({"op": "update", "team": tid, "name": "Phòng thử"})
check("update: đổi tên", "Phòng thử |" in r and ops.api.teams().get(tid)["name"] == "Phòng thử", r)
r = run({"op": "add_member", "team": tid, "slug": "hoa"})
check("add_member: thêm Hoa", "hoa" in r and len(ops.api.teams().members(tid)) == 4, r)
r = run({"op": "remove_member", "team": tid, "member": "hoa"})
check("remove_member theo slug: bỏ Hoa", len(ops.api.teams().members(tid)) == 3, r)
r = run({"op": "set_leader", "team": tid, "member": "nguoi-phan-bien"})
check("set_leader theo slug", ops.api.teams().get(tid)["leader_key"] == ops.member_key(ops.api.teams().get(tid),
                                                                                         "nguoi-phan-bien"), r)
r = run({"op": "create_agent", "name": "Người viết", "role": "Viết bản nháp", "model": "gpt-5.5",
         "model_provider": "openai-oauth", "team": tid, "leader": True})
check("create_agent + ghép nhóm + làm trưởng nhóm", "nguoi-viet" in r and "trưởng nhóm" in r
      and ops.api.teams().get(tid)["leader_key"] == ops.member_key(ops.api.teams().get(tid), "nguoi-viet"), r)

check("set_agent_model: provider lạ bị từ chối",
      run({"op": "set_agent_model", "slug": "minh", "model": "opus", "model_provider": "xyz"}).startswith("ERROR"))
r = run({"op": "set_agent_model", "slug": "minh", "model": "opus", "model_provider": "anthropic-cli"})
mt = (BR / "agents" / "minh.md").read_text(encoding="utf-8")
check("set_agent_model: ghi model, giữ tên và lời dặn", "model: opus" in mt and "name: Minh" in mt
      and "Bạn là Minh." in mt, mt)
r = run({"op": "set_agent_model", "slug": "minh", "model": ""})
check("set_agent_model rỗng: về model chính, bỏ provider", "model chính" in r
      and "model_provider" not in (BR / "agents" / "minh.md").read_text(encoding="utf-8"), r)

# Xoá: phải lưu trữ trước và phải có confirm=true
check("delete thiếu confirm: từ chối", run({"op": "delete", "team": tid}).startswith("ERROR"))
check("delete nhóm chưa lưu trữ: từ chối kể cả có confirm",
      "lưu trữ" in run({"op": "delete", "team": tid, "confirm": True}) and ops.api.teams().get(tid) is not None)
check("archive: nhóm thành archived", "lưu trữ" in run({"op": "archive", "team": tid})
      and ops.api.teams().get(tid)["status"] == "archived")
check("unarchive rồi archive lại", "mở lại" in run({"op": "unarchive", "team": tid})
      and ops.api.teams().get(tid)["status"] == "active" and "lưu trữ" in run({"op": "archive", "team": tid}))
sid = ops.api.teams().get(tid)["session_id"]
r = run({"op": "delete", "team": tid, "confirm": True})
check("delete nhóm đã lưu trữ: xoá nhóm, thành viên và phiên chat", r.startswith("Đã xoá") and ops.api.teams().get(tid) is None
      and ops.api.teams().members(tid, include_removed=True) == [] and main.get_store().get_session(sid) is None, r)
check("file trợ lý vẫn còn sau khi xoá nhóm", (BR / "agents" / "nguoi-phan-bien.md").is_file())

# Route của trang Nhóm dùng cùng TeamOps: DELETE /teams/{id}
c = TestClient(main.app, base_url="http://127.0.0.1:8080")
q = {"brain": str(BR)}
t2 = c.post("/teams", params=q, json={"name": "Nhóm route", "members": ["lan", "minh"], "leader_slug": "lan"}).json()
tid2 = t2["team"]["team_id"]
r1 = c.delete(f"/teams/{tid2}", params=q)
check("DELETE /teams nhóm chưa lưu trữ: 400", r1.status_code == 400 and ops.api.teams().get(tid2) is not None, r1.text)
c.patch(f"/teams/{tid2}", params=q, json={"status": "archived"})
r2 = c.delete(f"/teams/{tid2}", params=q)
check("DELETE /teams nhóm đã lưu trữ: 200, nhóm mất", r2.status_code == 200 and ops.api.teams().get(tid2) is None, r2.text)
check("GET nhóm đã xoá: 404", c.get(f"/teams/{tid2}", params=q).status_code == 404)
d1 = c.post("/teams", params=q, json={"name": "Nhóm gửi lại", "members": ["lan"], "client_req_id": "req-1"}).json()
d2 = c.post("/teams", params=q, json={"name": "Nhóm gửi lại", "members": ["lan"], "client_req_id": "req-1"}).json()
check("POST /teams gửi lại cùng mã yêu cầu: trả nhóm cũ kèm duplicate (hành vi cũ giữ nguyên)",
      d2.get("duplicate") is True and d1["team"]["team_id"] == d2["team"]["team_id"] and "duplicate" not in d1, (d1, d2))

# Đường hub thật: plugin bundled nạp được, chủ (API engine) thấy javis_team, bot chăm khách thì không
import plugins_host  # noqa: E402
_pl = {p.get("slug"): p for p in plugins_host.describe(None)}.get("javis-team") or {}
check("plugin javis-team nạp không lỗi, bật sẵn, bundled, đúng tool, min_mode khớp",
      not _pl.get("error") and _pl.get("enabled") is True and _pl.get("source") == "bundled"
      and _pl.get("tools") == ["javis_team"] and _pl.get("min_mode") == "safe", _pl)


async def _hub():
    tools, route = await mcp_hub.discover_all("full", vault_root=str(BR))
    names = [t.get("fn") or t.get("name") for t in tools]
    if "javis_search_tools" in names:
        owner = "javis_team" in await route["javis_search_tools"]["call"]({"query": "tạo nhóm chat trợ lý"})
        called = await route["javis_run_tool"]["call"]({"name": "javis_team", "args": {"op": "list_agents"}})
    else:
        owner = "javis_team" in names
        called = await route["javis_team"]["call"]({"op": "list_agents"})
    check("hub: gọi javis_team qua route của hub chạy thật (list_agents)", "lan" in str(called), called)
    btools, broute = await mcp_hub.discover_all("full", vault_root=str(BR), for_bot=True)
    bnames = [t.get("fn") or t.get("name") for t in btools]
    if "javis_search_tools" in bnames:
        bot = "javis_team" in await broute["javis_search_tools"]["call"]({"query": "tạo nhóm chat trợ lý"})
    else:
        bot = "javis_team" in bnames
    return owner, bot


_owner, _bot = asyncio.run(_hub())
check("hub: chủ tìm thấy javis_team", _owner)
check("hub: bot chăm khách KHÔNG thấy javis_team", not _bot)

raise SystemExit(1 if fails else 0)
