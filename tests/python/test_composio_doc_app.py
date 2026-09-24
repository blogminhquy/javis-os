"""Composio ở mức Chỉ đọc phải ĐỌC được dữ liệu các app đã nối.

    python tests/run.py composio_doc_app

Vụ thật 24/09: người dùng nối Composio (mặc định mức Chỉ đọc) rồi nhờ Javis đọc/sửa lịch. Javis
chỉ còn mỗi COMPOSIO_SEARCH_TOOLS: cổng chạy hành động COMPOSIO_MULTI_EXECUTE_TOOL bị xếp
"nguy hiểm" và COMPOSIO_MANAGE_CONNECTIONS bị xếp "ghi" theo TÊN, nên cả hai bị giấu khỏi danh
sách. Kết quả: không đọc được lịch, không liệt kê được app đã nối. Thêm vào đó chế độ tìm tool
cắt mô tả còn 400 ký tự, nuốt mất dòng "User has manually connected the apps: ..." của Composio.

Test này canh: (1) phân loại từng lệnh con theo `call_rules`, fail-closed; (2) hub liệt kê hai
tool cổng ở mức Chỉ đọc nhưng vẫn chặn lệnh ghi lúc gọi, với câu báo nêu đúng lệnh con;
(3) kết quả tìm tool giữ mô tả đầy đủ cho các kết quả đầu.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import json
import os
import tempfile

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-composio-doc-"))

import config  # noqa: E402
import mcp_catalog  # noqa: E402
import mcp_client  # noqa: E402
import mcp_hub  # noqa: E402
import mcp_store  # noqa: E402

_fails = []


def check(name, cond, them=None):
    print(("ok   " if cond else "FAIL ") + name + ("" if cond or them is None else f"  [{them}]"))
    if not cond:
        _fails.append(name)


COM = mcp_catalog.get("composio")
check("catalog có connector composio", bool(COM))
EXEC, CONN = "COMPOSIO_MULTI_EXECUTE_TOOL", "COMPOSIO_MANAGE_CONNECTIONS"


def chay(*slugs):
    return {"tools": [{"tool_slug": s, "arguments": {}} for s in slugs], "sync_response_to_workbench": False}


def cls(tool, args):
    return mcp_catalog.classify(COM, tool, args)


# ============================================================
# 1. Phân loại từng lệnh con
# ============================================================
for slug in ("GOOGLECALENDAR_EVENTS_LIST", "GOOGLECALENDAR_FIND_EVENT", "GOOGLECALENDAR_LIST_CALENDARS",
             "GOOGLECALENDAR_EVENTS_GET", "GMAIL_FETCH_EMAILS", "GMAIL_FETCH_MESSAGE_BY_MESSAGE_ID",
             "GOOGLEDRIVE_FIND_FILE", "GOOGLESHEETS_BATCH_GET", "YOUTUBE_LIST_USER_PLAYLISTS"):
    check(f"lệnh đọc {slug} → read", cls(EXEC, chay(slug)) == "read", cls(EXEC, chay(slug)))
for slug in ("GOOGLECALENDAR_PATCH_EVENT", "GOOGLECALENDAR_UPDATE_EVENT", "GMAIL_SEND_EMAIL",
             "GOOGLECALENDAR_DELETE_EVENT", "GMAIL_LIST_AND_DELETE", "GOOGLECALENDAR_EVENTS_INSTANCES",
             "FACEBOOK_CREATE_POST", "LAMGI_KHONG_RO"):
    check(f"lệnh không chắc là đọc {slug} → không phải read", cls(EXEC, chay(slug)) != "read", cls(EXEC, chay(slug)))
check("trộn đọc + ghi → lấy mức nặng nhất",
      cls(EXEC, chay("GOOGLECALENDAR_EVENTS_LIST", "GMAIL_SEND_EMAIL")) == "danger")
check("danh sách lệnh rỗng → fail-closed", cls(EXEC, {"tools": []}) == "danger")
check("thiếu hẳn danh sách → fail-closed", cls(EXEC, {}) == "danger")
check("lệnh thiếu tool_slug → fail-closed", cls(EXEC, {"tools": [{"arguments": {}}]}) == "danger")
check("lúc liệt kê (args=None) cổng được coi là đọc để hiện ra", cls(EXEC, None) == "read")

check("MANAGE_CONNECTIONS list → read", cls(CONN, {"toolkits": [{"name": "gmail", "action": "list"}]}) == "read")
check("MANAGE_CONNECTIONS thiếu action (mặc định add) → write",
      cls(CONN, {"toolkits": [{"name": "gmail"}]}) == "write")
check("MANAGE_CONNECTIONS remove → write",
      cls(CONN, {"toolkits": [{"name": "gmail", "action": "remove", "account_id": "x"}]}) == "write")
check("REMOTE_BASH vẫn nguy hiểm", cls("COMPOSIO_REMOTE_BASH_TOOL", {"command": "ls"}) == "danger")
check("SEARCH_TOOLS vẫn là đọc", cls("COMPOSIO_SEARCH_TOOLS", {"queries": []}) == "read")

ok, _ = mcp_catalog.allowed(COM, "readonly", "full", EXEC, chay("GOOGLECALENDAR_EVENTS_LIST"))
check("mức Chỉ đọc cho qua lệnh đọc lịch", ok)
ok, why = mcp_catalog.allowed(COM, "readonly", "full", EXEC,
                              chay("GOOGLECALENDAR_EVENTS_GET", "GOOGLECALENDAR_PATCH_EVENT"))
check("mức Chỉ đọc chặn lệnh sửa lịch", not ok)
check("câu báo nêu đúng lệnh con bị chặn, không kể lệnh đọc",
      "GOOGLECALENDAR_PATCH_EVENT" in why and "GOOGLECALENDAR_EVENTS_GET" not in why, why)
ok, _ = mcp_catalog.allowed(COM, "safe", "full", CONN, {"toolkits": [{"name": "notion"}]})
check("mức Ghi nháp nối được app mới", ok)
ok, _ = mcp_catalog.allowed(COM, "full", "full", EXEC, chay("GMAIL_SEND_EMAIL"))
check("Toàn quyền chạy được mọi lệnh", ok)
ok, _ = mcp_catalog.allowed(COM, "full", "suggest", EXEC, chay("GMAIL_SEND_EMAIL"))
check("loop mức suggest vẫn bị chặn gửi dù kết nối Toàn quyền", not ok)
ok, _ = mcp_catalog.allowed(COM, "full", "suggest", EXEC, chay("GMAIL_FETCH_EMAILS"))
check("loop mức suggest đọc mail được", ok)

# ============================================================
# 2. Hub: ở mức Chỉ đọc hai tool cổng HIỆN ra, lệnh ghi vẫn bị chặn lúc gọi
# ============================================================
_goi = []


class _Pool:
    async def call_tool(self, spec, tool, args):
        _goi.append((tool, args))
        return "OK"


TEN = [("COMPOSIO_SEARCH_TOOLS", "Tìm tool. User has manually connected the apps: gmail, googlecalendar."),
       (EXEC, "Chạy tool"), (CONN, "Quản lý kết nối"), ("COMPOSIO_REMOTE_BASH_TOOL", "Chạy shell")]
CONN_REC = {"id": "cp1", "connector_id": "composio", "label": "Composio", "slug": "composio",
            "namespace": "composio", "perm": "readonly", "transport": "http",
            "url": "https://connect.composio.dev/mcp", "headers": {}, "env": {}, "deny_tools": []}


async def _discover_gia(conns, bo_qua=None):
    spec = {"transport": "http", "url": CONN_REC["url"], "headers": {}}
    tools, route = [], {}
    for name, desc in TEN:
        fn = f"composio__{name}"
        route[fn] = {"spec": spec, "tool": name,
                     "conn": {"id": "cp1", "namespace": "composio", "perm": "readonly",
                              "deny_tools": [], "label": "Composio", "connector_id": "composio"}}
        tools.append({"fn": fn, "server": "composio", "name": name, "description": desc,
                      "schema": {"type": "object", "properties": {}}, "conn_id": "cp1",
                      "connector_id": "composio", "namespace": "composio", "label": "Composio"})
    return tools, route


mcp_store.resolved = lambda enabled_only=True: [CONN_REC]
mcp_client.discover_resolved = _discover_gia
mcp_client.pool = _Pool()
mcp_hub._builtin_tools = lambda *a, **k: ([], {})
config.read_settings = lambda: {"mcp": {"lazy_tools": "off"}}
mcp_hub._cache.clear()

tools, route = asyncio.run(mcp_hub.discover_all("full", include_plugins=False, force_refresh=True))
ten = {t["name"] for t in tools}
check("mức Chỉ đọc vẫn liệt kê cổng chạy lệnh", EXEC in ten, sorted(ten))
check("mức Chỉ đọc vẫn liệt kê quản lý kết nối (để liệt kê tài khoản)", CONN in ten)
check("shell từ xa vẫn bị ẩn ở mức Chỉ đọc", "COMPOSIO_REMOTE_BASH_TOOL" not in ten)

kq = asyncio.run(mcp_client.call_route(route, f"composio__{EXEC}", chay("GOOGLECALENDAR_EVENTS_LIST")))
check("gọi lệnh đọc lịch đi tới Composio", kq == "OK" and _goi and _goi[-1][0] == EXEC, kq)
n = len(_goi)
kq = asyncio.run(mcp_client.call_route(route, f"composio__{EXEC}", chay("GOOGLECALENDAR_PATCH_EVENT")))
check("gọi lệnh sửa lịch bị chặn, không tới Composio", kq.startswith("ERROR:") and len(_goi) == n, kq)
kq = asyncio.run(mcp_client.call_route(route, f"composio__{CONN}", {"toolkits": [{"name": "gmail", "action": "list"}]}))
check("liệt kê tài khoản gmail đi tới Composio", kq == "OK", kq)

# ============================================================
# 3. Tìm tool (lazy) giữ mô tả đầy đủ cho kết quả đầu
# ============================================================
dai = "Tool Server Info: Composio connects 500+ apps. " + ("x" * 1100) + " User has manually connected the apps: gmail, googlecalendar."
pool = [{"fn": "composio__COMPOSIO_SEARCH_TOOLS", "name": "COMPOSIO_SEARCH_TOOLS", "description": dai,
         "namespace": "composio", "label": "Composio", "schema": {"type": "object", "properties": {}}}]
for i in range(6):
    pool.append({"fn": f"composio__KHAC_{i}", "name": f"KHAC_{i}", "namespace": "composio",
                 "description": "composio khác " + ("y" * 900), "label": "Composio",
                 "schema": {"type": "object", "properties": {}}})
config.read_settings = lambda: {"mcp": {"lazy_tools": "on", "lazy_top_k": 8}}
t2, r2 = mcp_hub._lazy_tools_and_route([], {}, pool, {}, 8)
kq = json.loads(asyncio.run(r2[mcp_hub._LAZY_SEARCH]["call"]({"query": "composio connected apps"})))
mota = {t["name"]: t["description"] for t in kq["tools"]}
check("kết quả đầu giữ dòng app đã nối", "manually connected the apps: gmail" in mota.get("composio__COMPOSIO_SEARCH_TOOLS", ""))
check("kết quả sau vẫn cắt gọn", all(len(v) <= mcp_hub._MO_TA_GON for k, v in list(mota.items())[mcp_hub._SO_KQ_DAY_DU:]))

if _fails:
    raise SystemExit(f"{len(_fails)} FAIL")
print("Tất cả xanh")
