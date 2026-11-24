"""A stand-in for `agy acp` (the Agent Client Protocol server of agy 1.5.15, measured 2026-11-24).

Used by test_agy_acp.py. It answers the way the real binary does:
- JSON-RPC 2.0, one object per line; `initialize` first, then session/new or session/resume;
- session/resume of an id it does not know is an ERROR (-32603 "Failed to read session"); session/set_model of an
  unknown model is -32602; session/set_config_option takes configId "thought_level" (low|medium|high);
- session/prompt streams session/update notifications (agent_thought_chunk, tool_call, tool_call_update,
  agent_message_chunk, usage_update) and replies {stopReason, usage} with THIS turn's numbers;
- EOF on stdin ends it with exit 0.

State lives in the folder named by FAKE_AGY_DIR: one file per conversation (shared with _fake_agy_stream.py, as the
real store is), and `received.jsonl` with every prompt the process was sent (pid, conversation, text, model, effort).

Prompt keywords steer a turn: RUNCMD (a finished command), BGCMD (a command left running), MCPCALL (a hub tool
through call_mcp_tool), MCPACP (a hub tool named the acp way), ASKPERM (agy asks permission before a write), FAIL503 (a provider error before any work),
SLOW (a long turn), REFUSE (stopReason refusal). NOACP in argv exits at start.
"""
import json
import os
import sys
import time
import uuid

state = os.environ["FAKE_AGY_DIR"]
os.makedirs(state, exist_ok=True)
argv = sys.argv[1:]
if "NOACP" in argv:
    sys.stderr.write("unknown command acp\n")
    sys.exit(1)
MODELS = ("gemini-3.8-flash-high", "gemini-3.8-flash-low", "claude-sonnet-4-6")
CONFIG = [{"id": "thought_level", "type": "select", "currentValue": "high",
           "options": [{"value": v, "name": v} for v in ("low", "medium", "high")]}]


def out(obj):
    sys.stdout.write(json.dumps(obj) + "\n")
    sys.stdout.flush()


def reply(rid, result=None, error=None):
    out({"jsonrpc": "2.0", "id": rid, **({"error": error} if error else {"result": result or {}})})


def update(sid, upd):
    out({"jsonrpc": "2.0", "method": "session/update", "params": {"sessionId": sid, "update": upd}})


def read_msg():
    raw = sys.stdin.readline()
    if not raw:
        return None
    return json.loads(raw)


model, effort = "", ""
my_requests = 1000


def ask(method, params):
    """A request from agy to the client; returns the client's reply."""
    global my_requests
    my_requests += 1
    out({"jsonrpc": "2.0", "id": my_requests, "method": method, "params": params})
    while True:
        m = read_msg()
        if m is None:
            sys.exit(0)
        if m.get("id") == my_requests and "method" not in m:
            return m


def tool(sid, tid, name, args, output, status="completed"):
    update(sid, {"sessionUpdate": "tool_call", "toolCallId": tid, "name": name, "args": args, "rawInput": args,
                 "status": "in_progress", "kind": "execute", "title": name})
    update(sid, {"sessionUpdate": "tool_call_update", "toolCallId": tid, "name": name, "args": args,
                 "rawInput": args, "status": status, "kind": "execute", "title": name,
                 "rawOutput": {"output": output}})


while True:
    msg = read_msg()
    if msg is None:
        break
    rid, method, p = msg.get("id"), msg.get("method"), msg.get("params") or {}
    if method in ("session/new", "session/resume"):
        with open(os.path.join(state, "servers.jsonl"), "a", encoding="utf-8") as f:
            f.write(json.dumps({"method": method, "mcpServers": p.get("mcpServers")}) + "\n")
    if method == "initialize":
        reply(rid, {"protocolVersion": 1, "agentCapabilities": {"loadSession": True,
                                                                "sessionCapabilities": {"resume": {}}}})
    elif method == "session/new":
        sid = str(uuid.uuid4())
        open(os.path.join(state, sid), "w").close()
        reply(rid, {"sessionId": sid, "configOptions": CONFIG})
    elif method == "session/resume":
        if os.path.exists(os.path.join(state, p.get("sessionId") or "-")):
            reply(rid, {"configOptions": CONFIG})
        else:
            reply(rid, error={"code": -32603, "message": f"Failed to read session {p.get('sessionId')}; retry, "
                                                         f"or load it with session/load"})
    elif method == "session/set_model":
        if p.get("modelId") in MODELS:
            model = p["modelId"]
            reply(rid, {})
        else:
            reply(rid, error={"code": -32602, "message": f"Unknown model ID: {p.get('modelId')}"})
    elif method == "session/set_config_option":
        if p.get("configId") == "thought_level" and p.get("value") in ("low", "medium", "high"):
            effort = p["value"]
            reply(rid, {"configOptions": CONFIG})
        else:
            reply(rid, error={"code": -32602, "message": "bad option"})
    elif method == "session/prompt":
        sid = p["sessionId"]
        text = "".join(x.get("text") or "" for x in p.get("prompt") or [])
        with open(os.path.join(state, sid), "a", encoding="utf-8") as f:
            f.write(text + "\n---\n")
        with open(os.path.join(state, "received.jsonl"), "a", encoding="utf-8") as f:
            f.write(json.dumps({"pid": os.getpid(), "cid": sid, "text": text, "model": model,
                                "effort": effort}) + "\n")
        if "FAIL503" in text:
            reply(rid, error={"code": -32603, "message": "Eligibility check failed: UNAVAILABLE (code 503)"})
            continue
        update(sid, {"sessionUpdate": "agent_thought_chunk", "content": {
            "type": "text", "text": "**Weighing the question**\n\nThe owner wants a short answer. I will keep it brief."}})
        if "RUNCMD" in text or "BGCMD" in text:
            line = "nohup sleep 100 &" if "BGCMD" in text else "git status"
            tool(sid, "call_1", "run_command", {"CommandLine": line, "toolSummary": "Check the repo"},
                 "Command exited with code 0.\nOutput: ok")
        if "MCPACP" in text:      # how agy acp names an MCP tool: mcp_<server>_<tool>
            tool(sid, "call_4", "mcp_javis_javis_run_tool",
                 {"name": "javis_connections", "args": {"op": "list"}, "toolSummary": "List connections"}, "")
        if "MCPCALL" in text:
            tool(sid, "call_2", "call_mcp_tool",
                 {"ServerName": "javis", "ToolName": "javis_run_tool",
                  "Arguments": {"name": "javis_connections", "args": {"op": "list"}},
                  "toolSummary": "List connections"}, "3 connections")
        if "ASKPERM" in text:
            r = ask("session/request_permission", {"sessionId": sid, "toolCall": {"toolCallId": "call_3"},
                                                   "options": [{"optionId": "a1", "kind": "allow_once"},
                                                               {"optionId": "r1", "kind": "reject_once"}]})
            picked = ((r.get("result") or {}).get("outcome") or {}).get("optionId")
            with open(os.path.join(state, "permission.txt"), "w") as f:
                f.write(str(picked))
        if "UNKNOWNREQ" in text:
            r = ask("fs/read_text_file", {"sessionId": sid, "path": "x"})
            with open(os.path.join(state, "unknown_req.txt"), "w") as f:
                f.write(json.dumps(r))
        if "SLOW" in text:
            time.sleep(30)
        if "REFUSE" in text:
            reply(rid, {"stopReason": "refusal", "usage": {}})
            continue
        n = len(open(os.path.join(state, sid), encoding="utf-8").read().split("---")) - 1
        answer = f"answer {n}"
        update(sid, {"sessionUpdate": "agent_message_chunk", "content": {"type": "text", "text": answer[:3]}})
        update(sid, {"sessionUpdate": "agent_message_chunk", "content": {"type": "text", "text": answer[3:]}})
        update(sid, {"sessionUpdate": "usage_update", "used": 10200 + n, "size": 1048576})
        reply(rid, {"stopReason": "end_turn", "usage": {"inputTokens": 200, "outputTokens": 2,
                                                        "cachedReadTokens": 10000, "thoughtTokens": 1,
                                                        "totalTokens": 10202}})
    elif rid is not None and method:
        reply(rid, error={"code": -32601, "message": "Method not found"})
time.sleep(0.2)
sys.exit(0)
