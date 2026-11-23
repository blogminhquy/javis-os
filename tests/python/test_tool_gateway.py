"""Tools hidden behind a gateway (Composio, a Composio or Gmail connector on the Claude account) are found.

    python tests/run.py tool_gateway      (no network)

Owner report 2026-11-23: Composio lists a handful of meta tools (COMPOSIO_SEARCH_TOOLS, COMPOSIO_MULTI_EXECUTE_TOOL)
while the hundreds of app tools behind them (GMAIL_SEND_EMAIL, NOTION_CREATE_PAGE...) never reach Javis's tool list.
javis_search_tools ranked only what it could see, so "gmail" came back as Resend, "gửi tin slack" as Zalo, and the
model said the app was not connected. A claude.ai account connector matched only when the request said its exact
name, so "đọc email mới nhất" never pointed at the Gmail connector, and a "Composio" connector on the Claude account
never matched "notion".
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import json
import os
import tempfile

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-toolgateway-"))
# The Codex hub profile is written under ~/.codex: keep it out of the real home.
os.environ["HOME"] = tempfile.mkdtemp(prefix="javis-toolgateway-home-")

import tool_finder  # noqa: E402
import mcp_hub  # noqa: E402

_fails = []


def check(name, cond, them=None):
    print(("ok   " if cond else "FAIL ") + name + ("" if cond or them is None else f"  [{them}]"))
    if not cond:
        _fails.append(name)


# The search tool's description as Composio really sends it (shortened), connected apps included.
_SEARCH_DESC = (
    "Tool Server Info: Composio connects 500+ apps\u2014Slack, GitHub, Notion, Google Workspace (Gmail, Sheets, "
    "Drive, Calendar), Microsoft (Outlook, Teams), X/Twitter, Figma, and more\u2014for seamless cross-app "
    "automation.\n  Use this tool to discover relevant tools plus the recommended plan.\n"
    "- User has manually connected the apps: ahrefs_mcp, facebook, gmail, google_analytics, googlecalendar, "
    "googledrive, googlesheets, pinterest. Prefer these apps when intent is unclear.\n"
    "Splitting guidelines (Important):\n  1. Atomic queries: 1 query = 1 tool call.")


def tool(ns, name, desc, cid="", label=""):
    return {"fn": f"{ns}__{name}", "name": name, "namespace": ns, "server": ns, "label": label or ns,
            "description": desc, "connector_id": cid, "schema": {"type": "object", "properties": {}}}


def _pool(with_composio=True):
    pool = [
        tool("pos-lcx", "pos_list_orders", "List orders of the shop, filter by status and created date.", "pos",
             "Làng Chài Xưa"),
        tool("pos-lcx", "pos_statistic_revenue", "Revenue statistics: total sales and order count per day.", "pos",
             "Làng Chài Xưa"),
        tool("zalo-quy", "zalo_send_message", "Send a text message to a Zalo user or group thread.", "zalo",
             "Minh Quý"),
        tool("zalo-quy", "zalo_get_history", "Get the message history of a Zalo thread.", "zalo", "Minh Quý"),
        tool("resend", "send-email", "Send an email with Resend.", "resend", "Resend"),
        tool("resend", "list-emails", "List sent emails.", "resend", "Resend"),
    ]
    if with_composio:
        pool += [
            tool("composio", "COMPOSIO_SEARCH_TOOLS", _SEARCH_DESC, "composio", "Composio"),
            tool("composio", "COMPOSIO_MULTI_EXECUTE_TOOL",
                 "Fast and parallel tool executor for tools discovered through COMPOSIO_SEARCH_TOOLS.", "composio",
                 "Composio"),
            tool("composio", "COMPOSIO_MANAGE_CONNECTIONS",
                 "Create or manage connections to user's apps. Supports multiple accounts per toolkit.", "composio",
                 "Composio"),
        ]
    return pool


# ---- 1. Reading a gateway ----------------------------------------------------------------------------------------
gw = tool_finder.gateway_info([t for t in _pool() if t["namespace"] == "composio"])
check("Composio is recognised as a gateway", bool(gw))
check("its search tool is COMPOSIO_SEARCH_TOOLS", gw and gw["tool"]["name"] == "COMPOSIO_SEARCH_TOOLS")
check("connected apps are read from its description, slugs normalised",
      gw and gw["connected"][:3] == ["ahrefs", "facebook", "gmail"], gw and gw["connected"])
check("'500+ apps' makes it reach any known app", gw and gw["universal"])
check("an ordinary source is not a gateway",
      tool_finder.gateway_info([t for t in _pool() if t["namespace"] == "pos-lcx"]) is None)
check("app ids: googlecalendar / Google Calendar / google_calendar are one app",
      {tool_finder.app_id(s) for s in ("googlecalendar", "Google Calendar", "google_calendar")} == {"googlecalendar"})
check("apps_in reads a Composio slug", tool_finder.apps_in("GMAIL_SEND_EMAIL") == ["gmail"])
check("apps_in ignores a request naming no app", tool_finder.apps_in("doanh thu pos hôm nay") == [])

# ---- 2. Ranking ----------------------------------------------------------------------------------------------------
idx = tool_finder.Index(_pool())


def top(q):
    r = idx.search(q)
    return [t["name"] for t, _s in r["hits"]], r


for q in ("gmail", "đọc email gmail mới nhất", "tạo trang notion", "gửi tin slack", "tạo issue github",
          "ghi vào google sheet", "xem lịch google calendar hôm nay", "GMAIL_SEND_EMAIL"):
    names, r = top(q)
    check(f"'{q}' -> the Composio search comes first", names[:1] == ["COMPOSIO_SEARCH_TOOLS"], names[:3])
    check(f"'{q}' -> named in via", any(v["named"] for v in r["via"]), r["via"])

names, r = top("đọc email mới nhất")
check("an app's job without its name -> gateway offered as related, not above the hits",
      [v["apps"] for v in r["via"]] == [["gmail"]] and not r["via"][0]["named"], r["via"])
names, r = top("doanh thu pos hôm nay")
check("a request for a direct source is untouched", names[:1] == ["pos_statistic_revenue"] and not r["via"], names)
names, r = top("gửi tin zalo cho Lan")
check("Zalo stays Zalo", names[:1] == ["zalo_send_message"] and not r["via"], names)
names, r = top("COMPOSIO_MANAGE_CONNECTIONS")
check("an exact tool name still wins", names == ["COMPOSIO_MANAGE_CONNECTIONS"], names)

# A pool with a direct Gmail source: that source first, the gateway only next to it.
direct = _pool() + [tool("gmail", "gmail_search_threads", "Search Gmail threads.", "gmail", "Gmail")]
names, r = [t["name"] for t, _s in tool_finder.Index(direct).search("gmail")["hits"]], \
    tool_finder.Index(direct).search("gmail")
check("a direct Gmail connection beats the gateway", names[:1] == ["gmail_search_threads"], names)
check("... and the gateway is still named", any(v["ns"] == "composio" for v in r["via"]), r["via"])

# No gateway at all: nothing changes.
r = tool_finder.Index(_pool(with_composio=False)).search("tạo trang notion")
check("no gateway -> no via", r["via"] == [])

# ---- 3. The hub's search answer ------------------------------------------------------------------------------------
pool = _pool()
route = {t["fn"]: {"call": None} for t in pool}
tools, r = mcp_hub._lazy_tools_and_route([], {}, pool, route, 8)
search_desc = next(t["description"] for t in tools if t["fn"] == "javis_search_tools")
check("the source menu names the apps behind the gateway", "cổng tới app đã nối: ahrefs, facebook, gmail" in search_desc)


def ask(q, ambient=None):
    _t, rr = mcp_hub._lazy_tools_and_route([], {}, pool, route, 8, ambient=ambient)
    out = asyncio.run(rr["javis_search_tools"]["call"]({"query": q}))
    return json.loads(out) if out.startswith("{") else out


ans = ask("tạo trang notion")
g = (ans.get("qua_cong") or [{}])[0] if isinstance(ans, dict) else {}
check("search answer has a qua_cong guide", g.get("tim_tool_an") == "composio__COMPOSIO_SEARCH_TOOLS", ans)
check("... with the catalog's search arguments", '"use_case"' in g.get("cach_goi", ""), g)
check("... and the executor with the source prefix",
      "composio__COMPOSIO_MULTI_EXECUTE_TOOL" in g.get("cach_goi", ""), g)
check("... the search tool itself is in the hits with its schema",
      ans["tools"][0]["name"] == "composio__COMPOSIO_SEARCH_TOOLS")
ans = ask("doanh thu pos hôm nay")
check("a POS request gets no gateway guide", isinstance(ans, dict) and "qua_cong" not in ans, ans)

# ---- 4. Claude account connectors ----------------------------------------------------------------------------------
AMB = [{"name": "Gmail"}, {"name": "Google Calendar"}, {"name": "Composio"}, {"name": "Notion"}]


def amb(q):
    return [s["name"] for s in mcp_hub._match_ambient(AMB, q)]


check("'đọc email mới nhất' -> the Gmail connector, though it never says Gmail", amb("đọc email mới nhất") == ["Gmail"],
      amb("đọc email mới nhất"))
check("'lịch hẹn tuần này' -> Google Calendar", amb("lịch hẹn tuần này") == ["Google Calendar"], amb("lịch hẹn tuần này"))
check("'tạo issue github' -> the Composio connector on the account", amb("tạo issue github") == ["Composio"],
      amb("tạo issue github"))
check("'tạo trang notion' -> Notion and Composio", amb("tạo trang notion") == ["Composio", "Notion"],
      amb("tạo trang notion"))
check("'doanh thu pos' -> nothing", amb("doanh thu pos") == [], amb("doanh thu pos"))
check("'gửi tin zalo' -> nothing", amb("gửi tin zalo cho Lan") == [], amb("gửi tin zalo cho Lan"))
ans = ask("tạo issue github", ambient=AMB)
check("the hub answer points at the account's Composio connector too",
      [a["connector"] for a in ans.get("tai_khoan_claude", [])] == ["Composio"], ans.get("tai_khoan_claude"))

# ---- 5. The user's own Codex MCP servers ----------------------------------------------------------------------
# Composio or Notion added straight to ~/.codex/config.toml: Codex calls them natively, outside the hub. The hub
# never named them, so a Codex turn searching for "notion" heard "no tool" (owner request 2026-11-23).
import claude_cli  # noqa: E402

_home = tempfile.mkdtemp(prefix="javis-codexhome-")
os.environ["CODEX_HOME"] = _home
with open(os.path.join(_home, "config.toml"), "w", encoding="utf-8") as f:
    f.write('model = "gpt-5"\n\n[mcp_servers.composio]\nurl = "https://connect.composio.dev/mcp"\n\n'
            '[mcp_servers.notion]\ncommand = "npx"\n\n[mcp_servers.old]\ncommand = "x"\nenabled = false\n\n'
            '[mcp_servers.javis]\nurl = "http://127.0.0.1/hub/mcp"\n')
check("CODEX_HOME is honoured", str(claude_cli._codex_home()) == _home)
check("_ambient_kind: Claude stays Claude", mcp_hub._ambient_kind(True) == "claude"
      and mcp_hub._ambient_kind("claude") == "claude")
check("_ambient_kind: codex", mcp_hub._ambient_kind("codex") == "codex")
check("_ambient_kind: anything else is off", mcp_hub._ambient_kind("") == "" and mcp_hub._ambient_kind("gemini") == ""
      and mcp_hub._ambient_kind(False) == "")
cx = mcp_hub._ambient_for("codex")
check("Codex servers are read, javis and disabled ones left out",
      [s["name"] for s in cx] == ["composio", "notion"], cx)
check("... marked as the Codex config", all(s["source"] == "codex_config" for s in cx))
check("Codex search: 'tạo trang notion' names both", [s["name"] for s in mcp_hub._match_ambient(cx, "tạo trang notion")]
      == ["composio", "notion"])

_t, rr = mcp_hub._lazy_tools_and_route([], {}, pool, route, 8, ambient=cx)
desc = next(t["description"] for t in _t if t["fn"] == "javis_search_tools")
check("the source menu names Codex's own servers", "mcp__notion__* (notion, cấu hình Codex riêng" in desc, desc[-300:])
ans = json.loads(asyncio.run(rr["javis_search_tools"]["call"]({"query": "tạo trang notion"})))
check("the search answer points at Codex's own servers",
      [a["connector"] for a in ans.get("codex_rieng", [])] == ["composio", "notion"], ans.get("codex_rieng"))
check("... not filed as Claude account connectors", "tai_khoan_claude" not in ans)
check("... with the Codex hint", "config.toml" in ans["codex_rieng"][0]["goi_the_nao"])
cj = json.loads(mcp_hub._connections_json(include_ambient="codex"))
check("javis_connections lists them on Codex",
      [c["connector"] for c in cj if c.get("source") == "codex_config"] == ["composio", "notion"])
check("the Codex hub profile tells the hub it is Codex",
      'X-Javis-Engine" = "codex"' in open(mcp_hub.codex_profile_path(), encoding="utf-8").read()
      if mcp_hub.codex_profile("full") else False)

# ---- 6. Grok Build and Antigravity: their own MCP servers too --------------------------------------------------
_h = os.environ["HOME"]
os.makedirs(os.path.join(_h, ".grok"), exist_ok=True)
with open(os.path.join(_h, ".grok", "config.toml"), "w", encoding="utf-8") as f:
    f.write('[mcp_servers.composio]\nurl = "https://connect.composio.dev/mcp"\n\n'
            '[mcp_servers.javis]\nurl = "http://127.0.0.1/hub/mcp"\n')
os.makedirs(os.path.join(_h, ".gemini", "config"), exist_ok=True)
with open(os.path.join(_h, ".gemini", "config", "mcp_config.json"), "w", encoding="utf-8") as f:
    json.dump({"mcpServers": {"notion": {"serverUrl": "https://mcp.notion.com/mcp"},
                              "cu": {"command": "x", "disabled": True},
                              "javis": {"serverUrl": "http://127.0.0.1/hub/mcp"}}}, f)
check("_ambient_kind knows grok and antigravity",
      mcp_hub._ambient_kind("grok") == "grok" and mcp_hub._ambient_kind("antigravity") == "antigravity")
gx = mcp_hub._ambient_for("grok")
check("Grok: ~/.grok/config.toml read, javis left out", [s["name"] for s in gx] == ["composio"], gx)
ax = mcp_hub._ambient_for("antigravity")
check("Antigravity: mcp_config.json read, javis and disabled left out", [s["name"] for s in ax] == ["notion"], ax)
check("Grok (not measured) is not given a made-up mcp__ pattern",
      mcp_hub._amb_tools(gx[0]) == "tool của MCP 'composio'")
# Measured on agy 1.5.14 (2026-11-23): MCP tools go through call_mcp_tool {"ServerName", "ToolName", "Arguments"}.
check("Antigravity gets its measured call_mcp_tool naming",
      mcp_hub._amb_tools(ax[0]) == "call_mcp_tool (ServerName 'notion')", mcp_hub._amb_tools(ax[0]))
check("Codex keeps its mcp__ pattern", mcp_hub._amb_tools(cx[0]) == "mcp__composio__*")
_t, rr = mcp_hub._lazy_tools_and_route([], {}, pool, route, 8, ambient=ax)
ans = json.loads(asyncio.run(rr["javis_search_tools"]["call"]({"query": "tạo trang notion"})))
check("an Antigravity search names its own Notion server",
      [a["connector"] for a in ans.get("antigravity_rieng", [])] == ["notion"], ans.get("antigravity_rieng"))
check("... with the Antigravity hint", "mcp_config.json" in ans["antigravity_rieng"][0]["goi_the_nao"])
cj = json.loads(mcp_hub._connections_json(include_ambient="grok"))
check("javis_connections lists Grok's own servers",
      [c["connector"] for c in cj if c.get("source") == "grok_config"] == ["composio"])
_agy = mcp_hub.antigravity_config_path("full", None)
check("the Antigravity hub file tells the hub it is Antigravity",
      json.load(open(_agy, encoding="utf-8"))["mcpServers"]["javis"]["headers"].get("X-Javis-Engine") == "antigravity")

print()
if _fails:
    print(f"{len(_fails)} FAIL")
    raise SystemExit(1)
print("all ok")
