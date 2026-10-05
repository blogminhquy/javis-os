"""The reply judge tools reach the owner and never a customer-facing bot (0.77.0), and the plugin does what it says.

    python tests/run.py reply_policy_hub_owner_only      (no network)
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import importlib.util
import json
import os
import sys
import tempfile
from pathlib import Path

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-rp-hub-")
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import chatbot_reply_policy_store as st  # noqa: E402
import mcp_hub  # noqa: E402
import plugins_host  # noqa: E402

_fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(extra) + "]") if extra and not cond else ""))
    if not cond:
        _fails.append(name)


def run(c):
    return asyncio.run(c)


VAULT = tempfile.mkdtemp(prefix="javis-rp-vault-")
OWN = mcp_hub.OWNER_ONLY_TOOLS
check("both judge tools are owner-only", OWN == {"javis_reply_policy", "javis_reply_policy_tune"})


def names(tools):
    return {t["fn"] for t in tools}


# ---- discover_all ----
# With few tools the hub lists them all; with many it hides them behind javis_search_tools/javis_run_tool. Check
# the plain list first (lazy forced off), then the lazy tier separately below.
_lazy_on = mcp_hub._lazy_on
mcp_hub._lazy_on = lambda n, chars: False
tools, route = run(mcp_hub.discover_all("full", vault_root=VAULT, force_refresh=True))
check("the owner's session sees both tools", OWN <= names(tools) and OWN <= set(route), sorted(names(tools)))
tools_b, route_b = run(mcp_hub.discover_all("full", vault_root=VAULT, force_refresh=True, for_bot=True))
check("a bot session sees neither", not (OWN & names(tools_b)) and not (OWN & set(route_b)))
check("a bot still gets the rest of the plugin tools", "javis_task" in names(tools_b) or "javis_task" in route_b
      or mcp_hub._LAZY_RUN in route_b)
tools_o, _ = run(mcp_hub.discover_all("full", vault_root=VAULT))
check("the cache keeps owner and bot lists apart", OWN <= names(tools_o))

# lazy tier: the bot's javis_run_tool must not dispatch them either
_tl, route_lb = run(mcp_hub.discover_all("full", vault_root=VAULT, force_refresh=True, for_bot=True, force_lazy=True))
out = run(route_lb[mcp_hub._LAZY_RUN]["call"]({"name": "javis_reply_policy", "args": {"op": "bots"}}))
check("lazy run on a bot cannot reach the judge tool", str(out).startswith("ERROR"), out)
_tl, route_lo = run(mcp_hub.discover_all("full", vault_root=VAULT, force_refresh=True, force_lazy=True))
out = run(route_lo[mcp_hub._LAZY_RUN]["call"]({"name": "javis_reply_policy", "args": {"op": "bots"}}))
check("lazy run for the owner reaches it", not str(out).startswith("ERROR"), out)

# ---- Claude Code config for a bot ----
mcp_hub._has_connections = lambda: True
p_owner = mcp_hub.claude_config_path("full", vault_root=VAULT)
p_bot = mcp_hub.claude_config_path("full", vault_root=VAULT, bot=True)
h_owner = json.loads(Path(p_owner).read_text(encoding="utf-8"))["mcpServers"]["javis"]["headers"]
h_bot = json.loads(Path(p_bot).read_text(encoding="utf-8"))["mcpServers"]["javis"]["headers"]
check("bot config is a separate file", p_owner != p_bot)
check("bot config carries X-Javis-Bot, the owner's does not", h_bot.get("X-Javis-Bot") == "1" and "X-Javis-Bot" not in h_owner)


# ---- the HTTP hub honours the header ----
class Req:
    def __init__(self, headers, body):
        self.headers = {k.lower(): v for k, v in headers.items()}
        self._body = body

    async def json(self):
        return self._body


def http_tools(headers):
    req = Req(dict(headers, Authorization=f"Bearer {mcp_hub.hub_token()}"),
              {"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    resp = run(mcp_hub.handle_http(req))
    return {t["name"] for t in json.loads(resp.body)["result"]["tools"]}


def http_call(headers, name, arguments):
    req = Req(dict(headers, Authorization=f"Bearer {mcp_hub.hub_token()}"),
              {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": name, "arguments": arguments}})
    resp = run(mcp_hub.handle_http(req))
    return json.loads(resp.body)["result"]["content"][0]["text"]


base = {"X-Javis-Mode": "full", "X-Javis-Vault": VAULT}
check("hub over HTTP lists them for the owner", OWN <= http_tools(base))
check("hub over HTTP hides them for a bot", not (OWN & http_tools(dict(base, **{"X-Javis-Bot": "1"}))))
check("hub over HTTP refuses a bot's direct call",
      "ERROR" in http_call(dict(base, **{"X-Javis-Bot": "1"}), "javis_reply_policy", {"op": "bots"}))

# ---- the plugin itself ----
spec = importlib.util.spec_from_file_location("javis_reply_policy_plugin",
                                              ROOT / "system" / "plugins" / "javis-reply-policy" / "plugin.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
ctx = plugins_host.PluginContext("javis-reply-policy", "bundled", ROOT / "system/plugins/javis-reply-policy", VAULT)
m.register(ctx)
by = {t["name"]: t for t in ctx._tools}
check("read tool is readonly, tune tool is safe",
      by["javis_reply_policy"]["min_mode"] == "readonly" and by["javis_reply_policy_tune"]["min_mode"] == "safe")
m._bots = lambda: [{"id": "A", "name": "Javis Vũ", "channel": "zalo"}, {"id": "B", "name": "Nhi Mai", "channel": "zalo"}]
R, T = by["javis_reply_policy"]["handler"], by["javis_reply_policy_tune"]["handler"]

import time  # noqa: E402
now = time.time()
d1 = st.log_decision({"bot_id": "A", "chat_id": "g1", "ts": now - 600, "text": "@Quý lịch học tuần này sao anh",
                      "sender": "Lan", "verdict": "silent", "silence_code": "addressed_other", "candidate": False,
                      "address_level": "none"}, now - 600)
st.log_decision({"bot_id": "B", "chat_id": "g2", "ts": now - 500, "text": "bí mật của bot B", "verdict": "silent",
                 "silence_code": "judge_silent", "candidate": True}, now - 500)

check("bots lists both with numbers", "Javis Vũ" in run(R({"op": "bots"}, ctx)) and "Nhi Mai" in run(R({"op": "bots"}, ctx)))
rep = run(R({"op": "report", "bot": "javis vu"}, ctx))
check("report by name without diacritics, own data only", "lịch học" in rep and "bí mật" not in rep, rep[:200])
dec = run(R({"op": "decisions", "bot": "A", "code": "addressed_other"}, ctx))
check("decisions filter by code, fenced as data", f"#{d1}" in dec and "<chat_data>" in dec)
check("unknown bot is a clear error", run(R({"op": "report", "bot": "không có"}, ctx)).startswith("ERROR"))
check("unknown op is a clear error", run(R({"op": "xoá"}, ctx)).startswith("ERROR"))

out = run(T({"op": "apply", "bot": "A", "action": "consider_tagged_set", "value": "1",
             "reason": "chủ muốn bot trả lời thay khi khách tag chủ"}, ctx))
check("owner applies the tag knob", "#" in out and st.get_tuning("A").get("consider_tagged") == "1", out)
out2 = run(T({"op": "apply", "bot": "A", "action": "case_add", "decision_id": d1, "verdict": "reply"}, ctx))
check("owner turns a silenced tag into a reply example", "#" in out2 and st.count_cases("A", "owner") == 1, out2)
chg = run(R({"op": "changes", "bot": "A"}, ctx))
check("changes lists both, marked as the owner's", chg.count("chủ nhờ") == 2, chg)
cid = int(out.split("change_id=")[1].split(")")[0])
check("a change id of bot A cannot be undone through bot B",
      run(T({"op": "revert", "bot": "B", "change_id": cid}, ctx)).startswith("ERROR"))
check("revert undoes it", not run(T({"op": "revert", "bot": "A", "change_id": cid}, ctx)).startswith("ERROR")
      and st.get_tuning("A").get("consider_tagged") in (None, "0"))
check("a bad action is refused with the reason",
      run(T({"op": "apply", "bot": "A", "action": "set_rate_limit", "value": "9"}, ctx)).startswith("ERROR"))

if _fails:
    print(f"\n{len(_fails)} FAIL")
    sys.exit(1)
print("\nall ok")
