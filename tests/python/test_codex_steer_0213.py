"""0.213.0: Codex chat turns take the owner's messages mid-way (codex_steer.py, `codex app-server` + `turn/steer`).

Two layers:
1. Always: a fake `codex` (a Python script speaking the app-server JSON-RPC and the `exec --json` stream) drives
   CodexCLI.query. Covers the steer handed over while a command runs, the profile passed as `-c` instead of `-p`,
   model/sandbox/approval in thread/start, a refused steer put back for the next turn, the fallback to `codex exec`
   when the turn cannot start on app-server, and when the path is used at all.
2. When the real Codex CLI is installed: the same steer against a fake OpenAI Responses endpoint, end to end.

Run:
    python tests/run.py codex_steer
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import json
import os
import shutil
import socket
import stat
import subprocess
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

TMP = Path(tempfile.mkdtemp(prefix="javis-codex-steer-"))
os.environ["JAVIS_STATE_DIR"] = str(TMP / "state")
os.environ["CODEX_HOME"] = str(TMP / "codex-home")
(TMP / "codex-home").mkdir()

import steer_inbox as si  # noqa: E402
import codex_steer  # noqa: E402
from claude_cli import CodexCLI  # noqa: E402

fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        fails.append(name)


# ---- pure helpers ----
ov = []
codex_steer._flatten("", {"mcp_servers": {"javis": {"url": "http://h/mcp", "startup_timeout_sec": 20,
                                                    "http_headers": {"Authorization": "Bearer x\"y",
                                                                     "X-Javis-Mode": "full"}}}}, ov)
check("profile flattens into -c overrides, header names unquoted",
      'mcp_servers.javis.url="http://h/mcp"' in ov and "mcp_servers.javis.startup_timeout_sec=20" in ov
      and 'mcp_servers.javis.http_headers.Authorization="Bearer x\\"y"' in ov
      and 'mcp_servers.javis.http_headers.X-Javis-Mode="full"' in ov)
try:
    codex_steer._flatten("", {"a.b": 1}, [])
    check("a dotted key cannot be passed with -c", False)
except ValueError:
    check("a dotted key cannot be passed with -c", True)
ei = codex_steer.exec_item({"type": "commandExecution", "id": "c1", "command": "ls", "aggregatedOutput": "x",
                            "exitCode": 0, "status": "completed"})
check("commandExecution reads as exec's command_execution",
      ei == {"id": "c1", "type": "command_execution", "command": "ls", "aggregated_output": "x", "exit_code": 0,
             "status": "completed"})
ei = codex_steer.exec_item({"type": "mcpToolCall", "id": "m1", "server": "javis", "tool": "pos_stats",
                            "arguments": {"a": 1}, "status": "inProgress"})
check("mcpToolCall reads as mcp_tool_call", ei["type"] == "mcp_tool_call" and ei["tool"] == "pos_stats"
      and ei["status"] == "in_progress")
ei = codex_steer.exec_item({"type": "fileChange", "id": "f1", "changes": [{"path": "/b/x.md", "kind": {"type": "add"}}]})
check("fileChange keeps its paths", ei["type"] == "file_change" and ei["changes"][0] == {"path": "/b/x.md", "kind": "add"})

# ---- when the path is used ----
cli0 = CodexCLI.__new__(CodexCLI)
cli0.steer = True
check("not outside a chat turn", not codex_steer.wanted(cli0))
tok = si.INBOX.open("w0")
check("inside a chat turn with an open inbox", codex_steer.wanted(cli0))
cli0.steer = False
check("not for an engine that is not the chat engine", not codex_steer.wanted(cli0))
cli0.steer = True
os.environ[codex_steer.ENV_SWITCH] = "0"
check("JAVIS_CODEX_STEER=0 turns it off", not codex_steer.wanted(cli0))
del os.environ[codex_steer.ENV_SWITCH]
si.INBOX.close("w0", token=tok)

# ---- a fake codex ----
FAKE = r'''#!/usr/bin/env python3
import json, os, sys, threading, time
argv = sys.argv[1:]
open(os.environ["FAKE_ARGV"], "a").write(json.dumps(argv) + "\n")
if "exec" in argv:
    for ev in ({"type": "thread.started", "thread_id": "ex1"}, {"type": "turn.started"},
               {"type": "item.completed", "item": {"id": "i1", "type": "agent_message", "text": "EXEC PATH"}},
               {"type": "turn.completed", "usage": {"input_tokens": 3, "output_tokens": 2}}):
        print(json.dumps(ev), flush=True)
    sys.exit(0)
lock = threading.Lock()
steers = []
def out(m):
    with lock:
        sys.stdout.write(json.dumps(m) + "\n"); sys.stdout.flush()
def note(method, **p):
    out({"method": method, "params": p})
def turn(tid, ref, tu):
    note("turn/started", threadId=tid, turn={"id": tu, "status": "inProgress"})
    if not os.environ.get("FAKE_NO_CMD"):
        cmd = {"type": "commandExecution", "id": "c1", "command": "sleep 1", "aggregatedOutput": "", "status": "inProgress"}
        note("item/started", threadId=tid, turnId=tu, item=cmd)
        time.sleep(float(os.environ.get("FAKE_TOOL_S", "1")))
        note("item/completed", threadId=tid, turnId=tu, item={**cmd, "aggregatedOutput": "A\n", "exitCode": 0, "status": "completed"})
    note("item/completed", threadId="sub-thread", turnId="x", item={"type": "agentMessage", "id": "s", "text": "SUB AGENT"})
    note("thread/tokenUsage/updated", threadId=tid, turnId=tu, tokenUsage={"last": {"inputTokens": 10, "outputTokens": 4}})
    time.sleep(0.4)
    with lock:
        said = " ".join(steers)
    text = "DONE" + (" BANANA" if "BANANA" in said else "")
    if os.environ.get("FAKE_DELTA"):
        for part in (text[:2], text[2:]):
            note("item/agentMessage/delta", threadId=tid, turnId=tu, itemId="a" + tu, delta=part)
            time.sleep(0.05)
    note("item/completed", threadId=tid, turnId=tu, item={"type": "agentMessage", "id": "a" + tu, "text": text})
    note("thread/tokenUsage/updated", threadId=tid, turnId=tu, tokenUsage={"last": {"inputTokens": 5, "outputTokens": 1}})
    with lock:
        ended[0] = True
    note("turn/completed", threadId=tid, turn={"id": tu, "status": "completed"})
ended = [False]
nturn = [0]
for line in sys.stdin:
    m = json.loads(line)
    meth, mid, p = m.get("method"), m.get("id"), m.get("params") or {}
    if meth in ("initialize",):
        out({"id": mid, "result": {"userAgent": "fake"}})
    elif meth == "thread/start":
        open(os.environ["FAKE_ARGV"], "a").write(json.dumps({"thread/start": p}) + "\n")
        out({"id": mid, "result": {"thread": {"id": "th1"}}})
    elif meth == "thread/resume":
        if p.get("threadId") == "dead":
            out({"id": mid, "error": {"code": -32600, "message": "no rollout found for thread id dead"}})
        else:
            out({"id": mid, "result": {"thread": {"id": p["threadId"]}}})
    elif meth == "turn/start":
        nturn[0] += 1
        tu = "tu%d" % nturn[0]
        with lock:
            ended[0] = False
        open(os.environ["FAKE_ARGV"], "a").write(json.dumps({"turn/start": p}) + "\n")
        out({"id": mid, "result": {"turn": {"id": tu, "status": "inProgress"}}})
        threading.Thread(target=turn, args=(p["threadId"], p, tu), daemon=True).start()
    elif meth == "turn/steer":
        with lock:
            late = ended[0] or os.environ.get("FAKE_REFUSE_STEER")
            if not late:
                steers.append(json.dumps(p.get("input")))
        if late:
            out({"id": mid, "error": {"code": -32600, "message": "no active turn"}})
        else:
            out({"id": mid, "result": {"turnId": p.get("expectedTurnId")}})
'''
fake = TMP / "codex"
fake.write_text(FAKE.replace("#!/usr/bin/env python3", "#!" + sys.executable), encoding="utf-8")
fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
if os.name == "nt":
    # Windows cannot start a shebang script (WinError 193): run the same fake through a .cmd, as npm installs codex.
    (TMP / "codex.cmd").write_text(f'@"{sys.executable}" "{fake}" %*\r\n', encoding="utf-8")
    fake = TMP / "codex.cmd"
os.environ["FAKE_ARGV"] = str(TMP / "argv.jsonl")
(TMP / "codex-home" / "javis.config.toml").write_text(
    '[mcp_servers.javis]\nurl = "http://127.0.0.1:7777/hub/mcp"\nstartup_timeout_sec = 20\n'
    '[mcp_servers.javis.http_headers]\n"Authorization" = "Bearer tok"\n"X-Javis-Mode" = "full"\n', encoding="utf-8")


def new_cli(**kw):
    c = CodexCLI(cwd=str(TMP), tag="chat:t:1", model="gpt-5.5")
    c.cli_path = str(fake)
    c.steer = True
    c.profile = "javis"
    c.transport = "ws"
    for k, v in kw.items():
        setattr(c, k, v)
    return c


def argv_log():
    p = TMP / "argv.jsonl"
    rows = [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines()] if p.exists() else []
    p.unlink(missing_ok=True)
    return rows


async def drive(cli, sid, steer_text=None, steer_on="progress"):
    tok = si.INBOX.open(sid)
    evs = []
    try:
        async for ev in cli.query("làm báo cáo"):
            evs.append(ev)
            if steer_text and ev["type"] == steer_on:
                si.INBOX.put(sid, steer_text)
    finally:
        left = si.INBOX.close(sid, token=tok)
    return evs, left


reads = []
si.INBOX.on_read = lambda sid, ids: reads.append(sid)

evs, left = asyncio.run(drive(new_cli(), "web:a", "kết thúc bằng BANANA"))
rows = argv_log()
types = [e["type"] for e in evs]
final = next((e for e in evs if e["type"] == "final"), {})
check("app-server: session, progress, tool_call, text, final in order",
      types[0] == "session" and "progress" in types and types.index("progress") < types.index("tool_call")
      < types.index("text") < types.index("final"))
check("app-server: the message sent while the command ran reached the same turn",
      "BANANA" in final.get("content", "") and left == [] and "web:a" in reads)
argv = rows[0] if rows else []
check("app-server: started as app-server with the profile as -c, never -p",
      argv[-1:] == ["app-server"] and "-p" not in argv
      and 'mcp_servers.javis.url="http://127.0.0.1:7777/hub/mcp"' in argv
      and 'mcp_servers.javis.http_headers.X-Javis-Mode="full"' in argv)
tstart = next((r["thread/start"] for r in rows if isinstance(r, dict) and "thread/start" in r), {})
check("app-server: model, sandbox and approval go in thread/start",
      tstart.get("model") == "gpt-5.5" and tstart.get("sandbox") == "danger-full-access"
      and tstart.get("approvalPolicy") == "never")
tc = next((e for e in evs if e["type"] == "tool_call"), {})
check("app-server: a command reads like exec's (label, output)",
      tc.get("item", {}).get("type") == "command_execution" and tc["item"].get("aggregated_output") == "A\n")
check("app-server: a sub-agent's thread is not mixed into the answer", "SUB AGENT" not in final.get("content", ""))
check("app-server: tokens of this turn add up", final.get("tokens_in") == 15 and final.get("tokens_out") == 5)

# no steer: same answer without BANANA, no leftovers
evs, left = asyncio.run(drive(new_cli(), "web:b"))
argv_log()
check("app-server: a turn with nothing sent meanwhile", any(e.get("content") == "DONE" for e in evs if e["type"] == "final"))

# Codex refuses the steer (its turn just ended): the message is put back and runs as the next turn
os.environ["FAKE_REFUSE_STEER"] = "1"
evs, left = asyncio.run(drive(new_cli(), "web:c", "thêm bảng"))
del os.environ["FAKE_REFUSE_STEER"]
argv_log()
check("refused steer: the message comes back as a leftover for the next turn", [i["text"] for i in left] == ["thêm bảng"])

# fallback: a missing profile, and a dead thread, both end up on `codex exec`
evs, left = asyncio.run(drive(new_cli(profile="khong-co"), "web:d"))
rows = argv_log()
check("fallback: an unreadable profile runs the turn on exec",
      any(e.get("content") == "EXEC PATH" for e in evs if e["type"] == "final")
      and all("app-server" not in r for r in rows if isinstance(r, list)) and any("exec" in r for r in rows if isinstance(r, list)))
evs, left = asyncio.run(drive(new_cli(session_id="dead"), "web:e"))
rows = argv_log()
check("fallback: a thread app-server cannot resume runs on exec",
      any(e.get("content") == "EXEC PATH" for e in evs if e["type"] == "final")
      and any(isinstance(r, list) and r[-1:] == ["app-server"] for r in rows)
      and any(isinstance(r, list) and "exec" in r for r in rows))

# outside a chat turn (a workflow, a loop): exec, as before
async def no_turn():
    c = new_cli()
    return [e async for e in c.query("x")]
evs = asyncio.run(no_turn())
rows = argv_log()
check("background work stays on exec", any(e.get("content") == "EXEC PATH" for e in evs if e["type"] == "final")
      and not any(isinstance(r, list) and "app-server" in r for r in rows))

# ---- 0.382.0: streamed text, instructions once, a warm process for the next turn ----
import warm_pool  # noqa: E402

os.environ["JAVIS_WARM_BUDGET_MB"] = "500"
os.environ["FAKE_NO_CMD"] = "1"
os.environ["FAKE_DELTA"] = "1"


async def turns(*clis):
    out = []
    prev = None
    for i, kw in enumerate(clis):
        c = new_cli(**kw)
        if prev is not None and "session_id" not in kw:
            c.session_id = prev.session_id
        out.append((await drive(c, f"web:w{i}"))[0])
        prev = c
    st = warm_pool.POOL.status()
    await warm_pool.POOL.close_all()
    return out, st


(r1, r2), st = asyncio.run(turns({"instructions": "LUAT JAVIS", "warm_key": "conv-w"},
                                 {"instructions": "LUAT JAVIS", "warm_key": "conv-w"}))
rows = argv_log()
spawns = [r for r in rows if isinstance(r, list) and r[-1:] == ["app-server"]]
tstart = [r["thread/start"] for r in rows if isinstance(r, dict) and "thread/start" in r]
tturns = [r["turn/start"] for r in rows if isinstance(r, dict) and "turn/start" in r]
check("deltas: the answer arrives piece by piece and is not sent again as a block",
      [e["content"] for e in r1 if e["type"] == "text"] == ["DO", "NE"])
check("deltas: final still carries the whole answer", any(e.get("content") == "DONE" for e in r1 if e["type"] == "final"))
check("instructions go once, as developerInstructions of thread/start",
      len(tstart) == 1 and tstart[0].get("developerInstructions") == "LUAT JAVIS")
check("the message itself no longer carries the instructions",
      len(tturns) == 2 and all("LUAT JAVIS" not in json.dumps(t["input"]) for t in tturns))
check("warm: the second turn runs on the same process (one spawn, no resume, two turns)",
      len(spawns) == 1 and not any(isinstance(r, dict) and "thread/resume" in r for r in rows))
check("warm: the second turn says it was warm and has its own answer",
      any(e.get("warm") for e in r2 if e["type"] == "session")
      and any(e.get("content") == "DONE" for e in r2 if e["type"] == "final"))
check("warm: the pool held one codex slot and served one hit", st["hits"] == 1 and st["admitted"] == 1)

(r1,), st = asyncio.run(turns({"instructions": "LUAT JAVIS", "session_id": "old-thread"}))
tturns = [r["turn/start"] for r in argv_log() if isinstance(r, dict) and "turn/start" in r]
check("a thread from before 0.382.0 (rules only in its first message) still gets them in front of the message",
      len(tturns) == 1 and json.dumps(tturns[0]["input"], ensure_ascii=False).count("LUAT JAVIS") == 1)
check("a thread opened with developerInstructions is on record", codex_steer.carries_instructions("th1")
      and not codex_steer.carries_instructions("old-thread"))

(r1, r2), st = asyncio.run(turns({"warm_key": "conv-m"}, {"warm_key": "conv-m", "model": "gpt-5.4"}))
spawns = [r for r in argv_log() if isinstance(r, list) and r[-1:] == ["app-server"]]
check("warm: another model is another fingerprint, so the turn opens a new process", len(spawns) == 2)

del os.environ["FAKE_NO_CMD"]
(r1,), st = asyncio.run(turns({"warm_key": "conv-c"}))
argv_log()
check("a turn that ran a shell command hands its process back (adoption on POSIX, Stop on Windows)",
      st["slots"] == [] and any(e["type"] == "final" for e in r1))

os.environ["JAVIS_WARM_BUDGET_MB"] = "0"
os.environ["FAKE_NO_CMD"] = "1"
(r1,), st = asyncio.run(turns({"warm_key": "conv-z"}))
argv_log()
check("budget 0 turns the pool off", st["slots"] == [] and any(e["type"] == "final" for e in r1))
for k in ("JAVIS_WARM_BUDGET_MB", "FAKE_NO_CMD", "FAKE_DELTA"):
    os.environ.pop(k, None)

# ---- wiring ----
src = (SERVER / "main.py").read_text(encoding="utf-8")
check("main: the web chat engine and the channel engine opt in", src.count("ccli.steer = True") == 2)
check("main: Codex turns stay live unless the switch is off",
      "if not codex_steer.enabled():" in src and '(prov == "openai-oauth" and not codex_steer.enabled())' in src)
for f in ("codex_steer.py",):
    check(f"no long dashes in {f}", not any(c in (SERVER / f).read_text(encoding="utf-8") for c in "–—"))


# ---- the real Codex CLI against a fake Responses endpoint ----
def real_codex():
    exe = shutil.which("codex")
    if not exe:
        print("skip real Codex CLI: not installed")
        return
    try:
        ver = subprocess.run([exe, "--version"], capture_output=True, text=True, timeout=20).stdout
    except Exception as e:
        print(f"skip real Codex CLI: {e}")
        return
    requests = []

    class H(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *a):
            pass

        def do_GET(self):
            body = b'{"data": [], "models": []}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):
            req = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
            requests.append(req)
            inp = req.get("input") or []
            tools = [t.get("name") or t.get("type") for t in req.get("tools") or []]
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Connection", "close")
            self.end_headers()

            def sse(ev):
                self.wfile.write(f"event: {ev['type']}\ndata: {json.dumps(ev)}\n\n".encode())
            sse({"type": "response.created", "response": {"id": f"r{len(requests)}"}})
            if not any(i.get("type") == "function_call_output" for i in inp):
                name = next((t for t in ("exec_command", "shell_command", "shell") if t in tools), "shell")
                args = ({"cmd": "sleep 3; echo A"} if name == "exec_command" else {"command": "sleep 3; echo A"}
                        if name == "shell_command" else {"command": ["bash", "-lc", "sleep 3; echo A"]})
                item = {"type": "function_call", "name": name, "arguments": json.dumps(args), "call_id": "c1", "id": "fc1"}
            else:
                text = "DONE" + (" BANANA" if "BANANA" in json.dumps(inp) else "")
                item = {"type": "message", "role": "assistant", "id": "m1",
                        "content": [{"type": "output_text", "text": text, "annotations": []}]}
            sse({"type": "response.output_item.done", "output_index": 0, "item": item})
            sse({"type": "response.completed", "response": {"id": f"r{len(requests)}", "usage": {
                "input_tokens": 10, "input_tokens_details": {"cached_tokens": 0}, "output_tokens": 5,
                "output_tokens_details": {"reasoning_tokens": 0}, "total_tokens": 15}}})
            self.wfile.flush()

    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    srv = ThreadingHTTPServer(("127.0.0.1", port), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    os.environ["FAKE_KEY"] = "x"
    c = CodexCLI(cwd=str(TMP), tag="chat:real:1", model="gpt-5.5")
    c.cli_path = exe
    c.steer = True
    c.transport = "ws"
    c.extra_config = ['model_provider="fake"', f'model_providers.fake.base_url="http://127.0.0.1:{port}/v1"',
                      'model_providers.fake.name="fake"', 'model_providers.fake.wire_api="responses"',
                      'model_providers.fake.env_key="FAKE_KEY"']
    try:
        evs, left = asyncio.run(asyncio.wait_for(drive(c, "web:real", "kết thúc bằng BANANA"), 120))
    finally:
        srv.shutdown()
    final = next((e for e in evs if e["type"] == "final"), {})
    print(f"real Codex CLI {ver.strip()}: {[e['type'] for e in evs]}")
    check("real Codex CLI: a message sent while a command runs joins the same turn",
          "BANANA" in final.get("content", "") and left == [] and len(requests) == 2)
    check("real Codex CLI: the command reads like exec's", any(
        e["type"] == "tool_call" and e["item"].get("type") == "command_execution" for e in evs))


real_codex()

print()
print("FAIL" if fails else "PASS", f"({len(fails)} failed)")
raise SystemExit(1 if fails else 0)
