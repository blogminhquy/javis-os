"""Google's own Workspace MCP servers behind one connection (google-workspace-official, 2026-11-27).

    python tests/run.py google_workspace_official

No network, no pytest. The servers are faked with httpx.MockTransport; the tool names come from
tests/python/fixtures/google_workspace_official_tools.json, read from the live servers (tools/list needs no sign-in).

What is checked:
1. The card: internal transport that the client knows, Google OAuth with offline access, every scope Google lists.
2. Every real tool is classified on purpose: Google's read-only tools are read, nothing else is, sending, trashing and
   deleting are danger, and a tool Google adds later is never read by accident.
3. The Gmail card no longer lets a Draft connection send mail or a Read-only one mark spam (Google added those tools).
4. The cards it replaces are no longer offered for new connections, and existing ones keep running.
5. The wire: stateless 2026-07-28 headers and _meta, one token for nine servers, a 401 refreshed once, a failing server
   left out of the list, and the approval relay (Google's form elicitation) bound to the exact call and connection.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import json
import sys

import httpx

import gcal_read
import google_workspace_mcp as gw
import mcp_catalog
import mcp_client

_fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)


catalog = json.loads((ROOT / "system" / "mcp-catalog.json").read_text(encoding="utf-8"))
by_id = {c["id"]: c for c in catalog["connectors"]}
fixture = json.loads((ROOT / "tests" / "python" / "fixtures" / "google_workspace_official_tools.json")
                     .read_text(encoding="utf-8"))["services"]
card = by_id.get("google-workspace-official") or {}

# ---- 1. The card ----
check("card exists", bool(card))
check("internal transport the client knows",
      card.get("transport") == "internal" and mcp_client._INTERNAL.get(card.get("internal")) == "google_workspace_mcp")
auth = card.get("auth") or {}
check("Google OAuth with a key the owner brings", auth.get("type") == "oauth" and auth.get("provider") == "google"
      and auth.get("authorize_url", "").startswith("https://accounts.google.com/")
      and {f["key"] for f in auth.get("fields") or []} == {"client_id", "client_secret"})
check("offline access, so no sign-in every hour",
      (auth.get("authorize_params") or {}).get("access_type") == "offline")
needed = {  # Google's list per server, "Configure the Google Workspace MCP servers"
    "gmail.readonly", "gmail.compose", "gmail.modify", "drive.readonly", "drive.file", "documents", "spreadsheets",
    "presentations", "calendar.calendarlist.readonly", "calendar.events.freebusy", "calendar.events.readonly",
    "calendar.events", "chat.messages.readonly", "chat.messages.create", "tasks", "directory.readonly"}
have = {s.replace("https://www.googleapis.com/auth/", "") for s in auth.get("scopes") or []}
check("every scope Google lists is asked for: " + (", ".join(sorted(needed - have)) or "all"), needed <= have)
check("guide points at Personal mode with the agent flag",
      any("auth/overview/personal" in (s.get("link") or "") and "isAgent=true" in s["link"]
          for s in auth.get("steps") or []))
check("the redirect step offers the copy box", any(s.get("copy") == "redirect" for s in auth.get("steps") or []))
check("Test button calls a real tool", (card.get("validate") or {}).get("tool") in
      {f"gmail_{n}" for n in fixture["gmail"]})
check("the module serves the same nine services as the fixture", {s[0] for s in gw.SERVICES} == set(fixture))

# ---- 2. Every real tool classified on purpose ----
wrong_read, wrong_write = [], []
for svc, tools in fixture.items():
    for name, read_only in tools.items():
        cls = mcp_catalog.classify(card, f"{svc}_{name}")
        if read_only and cls != "read":
            wrong_read.append(f"{svc}_{name}={cls}")
        if not read_only and cls == "read":
            wrong_write.append(f"{svc}_{name}")
check("Google's read-only tools are read: " + (", ".join(wrong_read) or "all"), not wrong_read)
check("no other tool is read: " + (", ".join(wrong_write) or "none"), not wrong_write)
danger = ["gmail_send_message", "gmail_reply", "gmail_forward", "chat_send_message", "gmail_trash_thread",
          "gmail_trash_message", "drive_trash_file", "gmail_mark_thread_spam", "gmail_apply_sensitive_message_label",
          "calendar_delete_event", "tasks_delete_task", "gmail_create_filter", "drive_request_access"]
not_danger = [t for t in danger if mcp_catalog.classify(card, t) != "danger"]
check("sending, trashing, deleting are danger: " + (", ".join(not_danger) or "all"), not not_danger)
plain = ["gmail_create_draft", "gmail_untrash_thread", "gmail_unmark_thread_spam", "tasks_undelete_task",
         "calendar_create_event", "docs_update_doc", "sheets_update_values", "drive_create_file"]
off = [f"{t}={mcp_catalog.classify(card, t)}" for t in plain if mcp_catalog.classify(card, t) != "write"]
check("drafts, restores and ordinary edits are write: " + (", ".join(off) or "all"), not off)
check("a tool Google adds later is never read", mcp_catalog.classify(card, "chat_mark_as_read") == "write"
      and mcp_catalog.classify(card, "drive_some_new_tool") == "write")
check("relaying an answer works at Read only (reads can need approval too)",
      mcp_catalog.classify(card, gw.CONFIRM_TOOL) == "read")
check("Read only blocks a draft", not mcp_catalog.allowed(card, "readonly", "full", "gmail_create_draft")[0])
check("Draft blocks sending", not mcp_catalog.allowed(card, "safe", "full", "gmail_send_message")[0])
check("Full sends", mcp_catalog.allowed(card, "full", "full", "gmail_send_message")[0])

# ---- 3. The Gmail card after Google added send and spam tools ----
gm = by_id["gmail"]
check("Gmail card: send, reply, forward are danger",
      all(mcp_catalog.classify(gm, t) == "danger" for t in ("send_message", "reply", "forward")))
check("Gmail card: marking spam is not read",
      mcp_catalog.classify(gm, "mark_thread_spam") != "read" and mcp_catalog.classify(gm, "mark_message_spam") != "read")
check("Gmail card: Draft cannot send", not mcp_catalog.allowed(gm, "safe", "full", "send_message")[0])
check("Gmail card no longer claims there is no send tool", "KHÔNG có tool gửi" not in gm.get("description", ""))
gm_unread = [f"gmail_{n}" for n, ro in fixture["gmail"].items() if not ro and mcp_catalog.classify(gm, n) == "read"]
check("Gmail card: no write tool of Google's list is read: " + (", ".join(gm_unread) or "none"), not gm_unread)

# ---- 4. Cards it replaces ----
for cid in ("google-workspace", "google-tasks", "gmail", "google-calendar"):
    check(f"{cid} points at the official card", by_id[cid].get("replaced_by") == "google-workspace-official")
check("the official card is not itself replaced", not card.get("replaced_by"))
pub = {c["id"]: c for c in mcp_catalog.public_catalog()}
check("the page is told which cards are replaced", pub.get("gmail", {}).get("replaced_by") == "google-workspace-official"
      and pub.get("google-workspace-official", {}).get("replaced_by") == "")
js = (ROOT / "dashboard" / "console.js").read_text(encoding="utf-8")
check("the page offers a replaced card only to someone who has one",
      "!c.replaced_by || conns.some(x => x.connector_id === c.id)" in js)
check("Tasks page reads the calendar of the official card",
      gcal_read.is_calendar({"connector_id": "google-workspace-official"})
      and (gcal_read.pick_tool([{"name": "gmail_list_labels"}, {"name": "calendar_get_event"},
                                {"name": "calendar_list_events"}]) or {}).get("name") == "calendar_list_events")


# ---- 5. The wire, against fake servers ----
class Fake:
    """Nine fake servers. `answers[(host, tool)]` is a list of results popped per call."""

    def __init__(self):
        self.seen = []
        self.answers = {}
        self.down = set()
        self.reject_token = set()

    def handler(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        host = request.url.host
        self.seen.append((host, dict(request.headers), body))
        if host in self.down:
            return httpx.Response(503, json={"error": {"code": 503, "message": "unavailable"}})
        method = body["method"]
        if request.headers.get("mcp-method") != method or request.headers.get("mcp-protocol-version") != gw.PROTOCOL:
            return httpx.Response(400, json={"jsonrpc": "2.0", "id": body["id"],
                                             "error": {"code": -32020, "message": "Header mismatch"}})
        if method == "tools/list":
            svc = next(s[0] for s in gw.SERVICES if httpx.URL(s[1]).host == host)
            tools = [{"name": n, "inputSchema": {"type": "object"}, "outputSchema": {"type": "object"},
                      "annotations": {"readOnlyHint": ro}} for n, ro in fixture[svc].items()]
            return httpx.Response(200, json={"jsonrpc": "2.0", "id": body["id"],
                                             "result": {"resultType": "complete", "tools": tools}})
        name = body["params"]["name"]
        if request.headers.get("mcp-name") != name:
            return httpx.Response(400, json={"jsonrpc": "2.0", "id": body["id"],
                                             "error": {"code": -32020, "message": "Header mismatch"}})
        if request.headers.get("authorization") in self.reject_token:
            return httpx.Response(401, json={"jsonrpc": "2.0", "id": body["id"], "result": {
                "isError": True, "resultType": "complete", "content": [{"type": "text", "text": "invalid_token"}]}})
        queue = self.answers.get((host, name)) or [{"resultType": "complete",
                                                    "content": [{"type": "text", "text": "done"}]}]
        result = queue.pop(0) if len(queue) > 1 else queue[0]
        return httpx.Response(200, headers={"content-type": "text/event-stream"},
                              text="event: message\ndata: " + json.dumps(
                                  {"jsonrpc": "2.0", "id": body["id"], "result": result}) + "\n\n")


fake = Fake()
gw._client = lambda: httpx.AsyncClient(transport=httpx.MockTransport(fake.handler))
tokens = {"conn-a": "Bearer one"}
refreshes = []


async def fake_auth(spec, force=False, rejected=""):
    cid = (spec or {}).get("oauth_conn_id") or ""
    if cid not in tokens:
        return {}
    if force:
        refreshes.append(rejected)
        tokens[cid] = "Bearer two"
    return {"Authorization": tokens[cid]}


gw._auth = fake_auth
spec_a = {"oauth_conn_id": "conn-a", "namespace": "google-workspace-official"}
run = asyncio.run

gw._tools_cache.clear()
tools = run(gw.list_tools(spec_a))
names = {t["name"] for t in tools}
check("nine servers listed once each", len([s for s in fake.seen if s[2]["method"] == "tools/list"]) == 9)
check("every tool prefixed with its service",
      names == {f"{s}_{n}" for s, ts in fixture.items() for n in ts} | {gw.CONFIRM_TOOL})
check("the product named in each description", all(t["description"].startswith("[") for t in tools
                                                    if t["name"] != gw.CONFIRM_TOOL))
check("outputSchema not passed to the model", not any("outputSchema" in t for t in tools))
h, hdr, body = fake.seen[0]
check("stateless headers and _meta on tools/list", hdr.get("mcp-method") == "tools/list"
      and body["params"]["_meta"]["io.modelcontextprotocol/clientCapabilities"] == {"elicitation": {"form": {}}}
      and body["params"]["_meta"]["io.modelcontextprotocol/protocolVersion"] == gw.PROTOCOL)

fake.seen.clear()
run(gw.list_tools(spec_a))
check("tools/list cached between sessions", not fake.seen)

gw._tools_cache.clear()
fake.down = {"chatmcp.googleapis.com"}
names2 = {t["name"] for t in run(gw.list_tools(spec_a))}
check("a server that is down is left out, the others stay",
      not any(n.startswith("chat_") for n in names2) and "gmail_search_threads" in names2)
gw._tools_cache.clear()
fake.down = {httpx.URL(s[1]).host for s in gw.SERVICES}
try:
    run(gw.list_tools(spec_a))
    check("all servers down is an error, not an empty list", False)
except RuntimeError:
    check("all servers down is an error, not an empty list", True)
fake.down = set()

check("not signed in says so", run(gw.call("gmail_list_labels", {}, {"oauth_conn_id": "nobody"})).startswith(
    "ERROR: Google Workspace is not signed in"))
check("unknown tool refused", run(gw.call("maps_find", {}, spec_a)).startswith("ERROR: unknown"))

fake.seen.clear()
out = run(gw.call("drive_search_files", {"query": "x"}, spec_a))
host, hdr, body = fake.seen[-1]
check("a call goes to its own server with the token",
      out == "done" and host == "drivemcp.googleapis.com" and hdr.get("authorization") == "Bearer one"
      and hdr.get("mcp-name") == "search_files" and body["params"]["name"] == "search_files"
      and body["params"]["arguments"] == {"query": "x"})

fake.reject_token = {"Bearer one"}
out = run(gw.call("tasks_list_task_lists", {}, spec_a))
check("a 401 refreshes once and repeats the call", out == "done" and refreshes == ["Bearer one"]
      and fake.seen[-1][1].get("authorization") == "Bearer two")
fake.reject_token = {"Bearer two"}
tokens["conn-a"] = "Bearer two"
out = run(gw.call("tasks_list_task_lists", {}, spec_a))
check("a 401 after the refresh tells the owner what to check",
      out.startswith("ERROR: Google refused the sign-in") and "AI-powered agent" in out)
fake.reject_token = set()

# Approval relay
ask = {"resultType": "input_required", "requestState": "{\"elicitationId\":\"e1\",\"requestBinding\":\"b1\"}",
       "inputRequests": {"approval_choice": {"method": "elicitation/create", "params": {
           "mode": "form", "message": "**To:** ariel@example.com\nSubject: Plan",
           "requestedSchema": {"type": "object", "required": ["approval_choice"], "properties": {"approval_choice": {
               "type": "string", "title": "Allow Javis to use send_message?",
               "enum": ["ALLOW_ONCE", "ALLOW_TOOL_ALWAYS", "DENY_ONCE"],
               "enumNames": ["Allow once", "Always allow this tool", "Don't allow"]}}}}}}}
sent = {"resultType": "complete", "content": [{"type": "text", "text": "sent id=42"}]}
fake.answers[("gmailmcp.googleapis.com", "send_message")] = [ask, sent]
args = {"to": ["ariel@example.com"], "subject": "Plan", "body": "Approved"}
out = run(gw.call("gmail_send_message", args, spec_a))
check("Google's approval request reaches the model as APPROVAL NEEDED with the preview",
      out.startswith("APPROVAL NEEDED") and "ariel@example.com" in out and "Allow Javis to use send_message?" in out
      and "call google-workspace-official__confirm_google_action with" in out)
pid = out.split('approval_id="', 1)[1].split('"', 1)[0] if 'approval_id="' in out else ""
check("nothing was sent yet", "sent id" not in out and len(gw._pending) == 1)
check("another connection cannot answer it",
      run(gw.call(gw.CONFIRM_TOOL, {"approval_id": pid, "choice": "ALLOW_ONCE"}, {"oauth_conn_id": "conn-b"}))
      .startswith("ERROR: no approval"))
check("a sticky choice is not relayed",
      run(gw.call(gw.CONFIRM_TOOL, {"approval_id": pid, "choice": "ALLOW_TOOL_ALWAYS"}, spec_a)).startswith("ERROR"))
fake.seen.clear()
out = run(gw.call(gw.CONFIRM_TOOL, {"approval_id": pid, "choice": "allow_once"}, spec_a))
host, hdr, body = fake.seen[-1]
p = body["params"]
check("the owner's answer repeats the exact call with Google's state", out == "sent id=42"
      and host == "gmailmcp.googleapis.com" and p["name"] == "send_message" and p["arguments"] == args
      and p["requestState"] == ask["requestState"]
      and p["inputResponses"] == {"approval_choice": {"action": "accept", "content": {"approval_choice": "ALLOW_ONCE"}}}
      and "requestState" not in p["_meta"] and hdr.get("mcp-name") == "send_message")
check("an answered approval cannot be used twice",
      run(gw.call(gw.CONFIRM_TOOL, {"approval_id": pid, "choice": "ALLOW_ONCE"}, spec_a)).startswith("ERROR: no approval"))

denied = {"resultType": "complete", "isError": True,
          "content": [{"type": "text", "text": "Action canceled. The user declined the confirmation request."}]}
fake.answers[("gmailmcp.googleapis.com", "trash_thread")] = [ask, denied]
out = run(gw.call("gmail_trash_thread", {"threadId": "t1"}, spec_a))
pid = out.split('approval_id="', 1)[1].split('"', 1)[0]
out = run(gw.call(gw.CONFIRM_TOOL, {"approval_id": pid, "choice": "DENY_ONCE"}, spec_a))
check("a refusal comes back as Google's error", out.startswith("ERROR: Action canceled")
      and fake.seen[-1][2]["params"]["inputResponses"]["approval_choice"]["content"]["approval_choice"] == "DENY_ONCE")

fake.answers[("calendarmcp.googleapis.com", "create_event")] = [ask]
out = run(gw.call("calendar_create_event", {"summary": "x"}, spec_a))
pid = out.split('approval_id="', 1)[1].split('"', 1)[0]
gw._pending[pid]["created"] -= gw.PENDING_TTL + 1
check("an approval expires",
      run(gw.call(gw.CONFIRM_TOOL, {"approval_id": pid, "choice": "ALLOW_ONCE"}, spec_a)).startswith("ERROR: no approval"))

fake.answers[("tasksmcp.googleapis.com", "delete_task")] = [ask]
out = run(gw.call("tasks_delete_task", {"task": "1"}, spec_a))
for _ in range(gw.MAX_ROUNDS):
    if not out.startswith("APPROVAL NEEDED"):
        break
    pid = out.split('approval_id="', 1)[1].split('"', 1)[0]
    out = run(gw.call(gw.CONFIRM_TOOL, {"approval_id": pid, "choice": "ALLOW_ONCE"}, spec_a))
check("Google asking again and again stops after a few rounds", out.startswith("ERROR: Google asked for input"))

gw._pending.clear()
for i in range(gw.PENDING_MAX + 5):
    fake.answers[("tasksmcp.googleapis.com", "update_task")] = [ask]
    run(gw.call("tasks_update_task", {"n": i}, spec_a))
check("waiting approvals are capped", len(gw._pending) <= gw.PENDING_MAX)

if _fails:
    print(f"FAIL - test_google_workspace_official: {len(_fails)} lỗi: {_fails}")
    sys.exit(1)
print("PASS - test_google_workspace_official")
