"""Antigravity chat turns over `agy acp` (Agent Client Protocol), kept warm between turns (2026-11-24).

Why ACP and not `--input-format stream-json` (agy_warm.py). Measured on agy 1.5.15, Windows, gemini-3.8-flash-high:
the stream-json output sends NOTHING while the model thinks (its output struct has no thinking field, and the
`showThinking` setting only reaches the terminal UI). A 250-word answer sat 12 to 18 s on an empty chat, then arrived
in 3.5 s, which read as "Antigravity waits for the whole answer before it writes". `agy acp` streams:

    agent_thought_chunk            a summary of the model's thinking, the first after about 5 s, then about every 3 s
    agent_message_chunk            the answer, token by token
    tool_call / tool_call_update   each tool step with its arguments and its output

It also reaches a ready session in 1.2 to 1.7 s, against 2.2 to 2.5 s to `init` on stream-json.

The protocol (JSON-RPC 2.0, one JSON object per line on stdin and stdout), as agy 1.5.15 answers it:
- initialize {protocolVersion: 1} -> agentCapabilities (sessionCapabilities.resume and load).
- session/new {cwd, mcpServers} -> {sessionId, models, configOptions}. agy loads the HOME mcp_config files on its own
  but NOT the workspace one (<cwd>/.agents/mcp_config.json), which stream-json does: checked with a probe server only
  that file named, stream-json called it and ACP did not see it. So `mcp_servers` passes the workspace entries, and
  always the hub entry Javis wrote for THIS turn (cli.hub_entry): the HOME file is shared by every brain, and two
  brains starting at once could otherwise read each other's X-Javis-Vault. Both http and stdio entries work, and a
  passed "javis" is the one used when HOME has one too. An MCP tool then runs as `mcp_<server>_<tool>` (not the
  `call_mcp_tool` of stream-json), and its step carries no output.
- session/resume {sessionId, cwd, mcpServers: []} -> {} continues a stored conversation without replaying it. The
  store is shared with stream-json BOTH ways, so the ids in sessions.AGY_THREAD_COLUMN keep working and the stream
  fallback resumes a thread this path opened. An unknown id is an ERROR here (-32603 "Failed to read session"),
  unlike `--conversation`, which quietly opens a new one.
- session/set_model {sessionId, modelId} -> {}; an unknown id is -32602. There is no --model or --effort flag:
  session/set_config_option {configId: "thought_level"} sets the effort of a model whose name does not carry one.
- session/prompt {sessionId, prompt: [{type: "text", text}]} -> session/update notifications, then the reply
  {stopReason, usage: {inputTokens, outputTokens, cachedReadTokens, thoughtTokens, totalTokens}} for THIS turn
  (inputTokens leaves the cached part out). The notification usage_update.used is the thread's size.
- `--dangerously-skip-permissions` approves every tool. Without it (`--sandbox` for suggest), agy 1.5.15 still wrote a
  file without asking; a session/request_permission that does come is answered here: allow on full/auto, reject
  otherwise.
- EOF on stdin ends the process.

Same contract as agy_warm.run, so main.py does not know which one served the turn, plus one event: `thinking`. Only
the owner's dashboard chat comes here (main sets `cli.stream_turns`). Anything that fails before the message is sent
raises agy_warm.Fallback and AntigravityCLI.query tries the stream-json path, then one-shot. JAVIS_AGY_ACP=0 turns
this path off.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from pathlib import Path
from typing import AsyncIterator, Optional

import agy_warm
import warm_pool
from agy_warm import Fallback

ENV_SWITCH = "JAVIS_AGY_ACP"
# One pool kind for both transports: a sign-in change drops either (main's drop_kind), and a slot of the other
# transport is closed by its fingerprint ("config_changed").
KIND = agy_warm.KIND
# How `agy --help` lists the command ("acp  Start the Agent Client Protocol (ACP) stdio server").
HELP_MARK = "Agent Client Protocol"
PROTOCOL_VERSION = 1
SETUP_TIMEOUT_S = agy_warm.START_TIMEOUT_S
EFFORT_OPTION = "thought_level"
# A turn that ended with an answer. max_tokens keeps what was written; "refusal" and "cancelled" are errors.
OK_STOPS = ("end_turn", "max_tokens", "max_turn_requests")
OUTPUT_CAP = 2000
THOUGHT_CAP = 4000


def enabled() -> bool:
    return str(os.getenv(ENV_SWITCH, "1")).strip().lower() not in ("0", "false", "no", "off")


def available() -> bool:
    """This agy has the `acp` command (1.5.x does; an older one only has stream-json)."""
    import antigravity_cli
    return antigravity_cli.co_co(HELP_MARK)


class AcpError(Exception):
    """agy answered a request with a JSON-RPC error."""

    def __init__(self, code, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


class AcpHandle(warm_pool.Handle):
    """A running `agy acp` with its session open, kept between turns of one chat."""
    kind = KIND

    def __init__(self, proc, lines, session_id: str, last_id: int):
        self.proc = proc
        self.lines = lines
        self.session_id = session_id
        self._last_id = last_id        # JSON-RPC ids are unique per connection, so the count lives with it

    def new_id(self) -> int:
        self._last_id += 1
        return self._last_id

    def alive(self) -> bool:
        return self.proc.poll() is None

    async def close(self) -> None:
        agy_warm.hand_back(self.proc)


def _line(obj: dict) -> str:
    """Every non-ASCII character escaped, as on the stream path: a read cut inside a character cannot happen."""
    return json.dumps(obj, ensure_ascii=True) + "\n"


def request_line(rid: int, method: str, params: dict) -> str:
    return _line({"jsonrpc": "2.0", "id": rid, "method": method, "params": params})


def answer_request(msg: dict, mode: Optional[str]) -> str:
    """agy's own request to the client. A permission request is allowed on full/auto and rejected otherwise (any
    unknown mode rejects); anything else is "method not found" so agy never waits on it."""
    if msg.get("method") == "session/request_permission":
        opts = [o for o in ((msg.get("params") or {}).get("options") or []) if isinstance(o, dict)]
        allow = str(mode or "").strip().lower() in ("full", "auto")
        pick = None
        for kind in (("allow_once", "allow_always") if allow else ("reject_once", "reject_always")):
            pick = next((o.get("optionId") for o in opts if o.get("kind") == kind and o.get("optionId")), None)
            if pick:
                break
        outcome = {"outcome": "selected", "optionId": pick} if pick else {"outcome": "cancelled"}
        return _line({"jsonrpc": "2.0", "id": msg.get("id"), "result": {"outcome": outcome}})
    return _line({"jsonrpc": "2.0", "id": msg.get("id"),
                  "error": {"code": -32601, "message": "Method not found"}})


def effort_for(model, effort, config=None) -> str:
    """The thought_level to set, "" for none. Same rule as the flags: a model whose name carries its effort
    (gemini-3.8-flash-high) takes none, and a value the session does not offer is not sent."""
    import antigravity_cli
    eff = str(effort or "").strip().lower()
    if not eff or antigravity_cli.model_khoa_effort(model):
        return ""
    for opt in config or []:
        if isinstance(opt, dict) and opt.get("id") == EFFORT_OPTION:
            values = {str(o.get("value")) for o in (opt.get("options") or []) if isinstance(o, dict)}
            return eff if eff in values else ""
    return eff


def _pairs(d) -> list:
    return [{"name": str(k), "value": str(v)} for k, v in d.items()] if isinstance(d, dict) else []


def acp_server(name: str, entry) -> Optional[dict]:
    """One mcp_config entry (agy's schema: serverUrl/url + headers, or command + args + env) -> an ACP McpServer.
    None for a disabled or unreadable entry."""
    if not isinstance(entry, dict) or entry.get("disabled") is True:
        return None
    url = entry.get("serverUrl") or entry.get("url") or entry.get("httpUrl")
    if isinstance(url, str) and url.strip():
        return {"type": "http", "name": name, "url": url.strip(), "headers": _pairs(entry.get("headers"))}
    cmd = entry.get("command")
    if isinstance(cmd, str) and cmd.strip():
        args = entry.get("args") if isinstance(entry.get("args"), list) else []
        return {"name": name, "command": cmd.strip(), "args": [str(a) for a in args], "env": _pairs(entry.get("env"))}
    return None


def mcp_servers(cli) -> list:
    """The MCP servers Javis passes to the session (see the module docstring): the workspace mcp_config entries of
    the turn's folder, then the hub entry of this turn, which replaces a workspace "javis"."""
    out: dict = {}
    try:
        p = Path(str(cli.cwd)).expanduser() / ".agents" / "mcp_config.json"
        doc = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
        for name, entry in ((doc or {}).get("mcpServers") or {}).items():
            s = acp_server(str(name), entry)
            if s:
                out[str(name)] = s
    except Exception as e:  # noqa: BLE001 - a broken file must not stop the turn; stream-json would skip it too
        print(f"[antigravity acp] workspace mcp_config: {type(e).__name__}: {e}", file=sys.stderr)
    hub = getattr(cli, "hub_entry", None)
    if isinstance(hub, dict):
        s = acp_server("javis", hub)
        if s:
            out["javis"] = s
    return list(out.values())


def server_names(cli, servers: list) -> list:
    """Every MCP server name a tool name may start with: the ones passed, plus the HOME config's own."""
    import antigravity_cli
    names = {str(s.get("name")) for s in servers if isinstance(s, dict) and s.get("name")}
    try:
        for p in antigravity_cli._duong_mcp_home():
            if p.exists():
                names.update(str(k) for k in ((json.loads(p.read_text(encoding="utf-8")) or {})
                                              .get("mcpServers") or {}))
    except Exception:  # noqa: BLE001 - only labels depend on it
        pass
    return sorted(names, key=len, reverse=True)


def unwrap_mcp_name(name: str, args: dict, servers: list) -> tuple:
    """`mcp_javis_javis_run_tool` {name: "javis_connections", args: {...}} -> ("javis_connections", {...}): the tool
    really called, as antigravity_cli.unwrap_mcp_call does for stream-json's call_mcp_tool. A name that starts with
    no known server stays as it is."""
    import antigravity_cli
    low = name.lower()
    for server in servers:
        prefix = f"mcp_{server}_".lower()
        if low.startswith(prefix) and len(name) > len(prefix):
            inner = {k: v for k, v in args.items() if k != "toolSummary"}
            wrapped = {"ServerName": server, "ToolName": name[len(prefix):], "Arguments": inner}
            if isinstance(args.get("toolSummary"), str):
                wrapped["toolSummary"] = args["toolSummary"]
            return antigravity_cli.unwrap_mcp_call("call_mcp_tool", wrapped)
    return name, args


def fingerprint(cli, argv: list, session_id: str, servers: Optional[list] = None) -> str:
    """What a warm process was opened with: its argv, the model, effort and MCP servers set on its session, and the
    transport, so a stream-json slot of the same chat is never taken for this one."""
    spec = list(argv) + ["transport=acp", f"model={cli.model or ''}",
                         f"effort={effort_for(cli.model, getattr(cli, 'effort', None))}",
                         "mcp=" + json.dumps(servers if servers is not None else mcp_servers(cli), sort_keys=True)]
    return agy_warm.fingerprint(cli, spec, session_id)


async def _write(proc, line: str) -> None:
    try:
        await asyncio.to_thread(agy_warm._write, proc, line)
    except (OSError, ValueError) as e:
        raise Fallback(f"stdin: {type(e).__name__}: {e}")


async def _call(proc, lines, rid: int, method: str, params: dict, mode, timeout: float) -> dict:
    """One request while no turn runs. Notifications are skipped and agy's own requests answered. Returns the result;
    raises AcpError on a JSON-RPC error, Fallback when agy does not answer or exits."""
    await _write(proc, request_line(rid, method, params))
    end = time.monotonic() + timeout
    while True:
        left = end - time.monotonic()
        if left <= 0:
            raise Fallback(f"{method}: no answer")
        try:
            line = await lines.get(left)
        except asyncio.TimeoutError:
            raise Fallback(f"{method}: no answer")
        if line is None:
            raise Fallback(f"{method}: agy exited ({lines.stderr_tail(2)[:200]})")
        try:
            msg = json.loads(line)
        except ValueError:
            continue
        if not isinstance(msg, dict):
            continue
        if msg.get("method"):
            if "id" in msg:
                await _write(proc, answer_request(msg, mode))
            continue
        if msg.get("id") != rid:
            continue
        if "error" in msg:
            err = msg.get("error")
            err = err if isinstance(err, dict) else {"message": str(err)}
            raise AcpError(err.get("code"), str(err.get("message") or err))
        res = msg.get("result")
        return res if isinstance(res, dict) else {}


async def open_session(argv: list, env, cwd: str, want: str, model, effort, mode, servers: Optional[list] = None,
                       timeout: float = SETUP_TIMEOUT_S):
    """Start `agy acp` and make its session ready: resume `want` (or open a new one when it does not come back) with
    `servers` as its MCP servers, then set the model and effort. Returns (proc, lines, session_id, lost, last_id).
    Raises Fallback."""
    servers = list(servers or [])
    try:
        proc = await asyncio.to_thread(agy_warm._spawn, argv, cwd, env)
    except Exception as e:  # noqa: BLE001
        raise Fallback(f"spawn: {type(e).__name__}: {e}")
    lines = agy_warm.Lines(proc)
    lines.attach(asyncio.get_running_loop())
    rid = 0
    try:
        rid += 1
        await _call(proc, lines, rid, "initialize", {
            "protocolVersion": PROTOCOL_VERSION,
            # agy keeps its own file and terminal tools: the client offers none of its own.
            "clientCapabilities": {"fs": {"readTextFile": False, "writeTextFile": False}, "terminal": False}},
            mode, timeout)
        sid, lost, config = "", False, None
        if want:
            rid += 1
            try:
                res = await _call(proc, lines, rid, "session/resume",
                                  {"sessionId": want, "cwd": str(cwd), "mcpServers": servers}, mode, timeout)
                sid, config = want, res.get("configOptions")
            except AcpError as e:
                lost = True
                print(f"[antigravity acp] conversation {want[:8]} did not come back ({e.message[:120]}),"
                      f" opening a new one", file=sys.stderr)
        if not sid:
            rid += 1
            res = await _call(proc, lines, rid, "session/new", {"cwd": str(cwd), "mcpServers": servers}, mode,
                              timeout)
            sid = str(res.get("sessionId") or "").strip()
            if not sid:
                raise Fallback("session/new: no session id")
            config = res.get("configOptions")
        if model:
            rid += 1      # an unknown model id raises AcpError: the stream path passes it as --model instead
            await _call(proc, lines, rid, "session/set_model", {"sessionId": sid, "modelId": str(model)}, mode,
                        timeout)
        level = effort_for(model, effort, config)
        if level:
            rid += 1
            try:
                await _call(proc, lines, rid, "session/set_config_option",
                            {"sessionId": sid, "configId": EFFORT_OPTION, "value": level}, mode, timeout)
            except AcpError as e:     # the turn still runs, at the model's own level
                print(f"[antigravity acp] effort {level} not taken ({e.message[:120]})", file=sys.stderr)
        return proc, lines, sid, lost, rid
    except AcpError as e:
        lines.detach()
        agy_warm._stop(proc)
        raise Fallback(f"acp: {e.message[:200]}")
    except BaseException:
        lines.detach()
        agy_warm._stop(proc)
        raise


def _recipe(argv: list, env, cwd: str, session_id: str, model, effort, mode, servers: list):
    """How to reopen this conversation's process ahead of its next turn (warm_pool.prewarm)."""

    async def _open() -> AcpHandle:
        proc, lines, got, lost, last = await open_session(argv, env, cwd, session_id, model, effort, mode, servers)
        lines.detach()
        if lost or got != session_id:
            agy_warm.hand_back(proc)
            raise RuntimeError("the conversation did not come back")
        return AcpHandle(proc, lines, got, last)
    return _open


def _text_of(content) -> str:
    if isinstance(content, dict) and str(content.get("type") or "text") == "text":
        t = content.get("text")
        return t if isinstance(t, str) else ""
    return ""


def tool_output(update: dict) -> str:
    """What a finished tool step printed: rawOutput.output for a command, else the text items of `content`."""
    raw = update.get("rawOutput")
    if isinstance(raw, str):
        return raw
    if isinstance(raw, dict):
        for k in ("output", "content", "result", "text"):
            if isinstance(raw.get(k), str) and raw[k]:
                return raw[k]
    parts = []
    for item in update.get("content") or []:
        if isinstance(item, dict):
            t = _text_of(item.get("content")) if item.get("type") == "content" else ""
            if t:
                parts.append(t)
    return "\n".join(parts)


def new_state(servers: Optional[list] = None) -> dict:
    """Per-turn state of `translate`. `servers`: MCP server names, longest first (server_names)."""
    return {"tools": {}, "done": set(), "context": 0, "servers": list(servers or [])}


def translate(update: dict, st: dict) -> list:
    """One session/update -> Javis events. Answer text comes out as {"type": "_text"} for the caller's pieces."""
    import antigravity_cli
    if not isinstance(update, dict):
        return []
    kind = str(update.get("sessionUpdate") or "")
    if kind == "agent_message_chunk":
        t = _text_of(update.get("content"))
        return [{"type": "_text", "content": t}] if t else []
    if kind == "agent_thought_chunk":
        t = _text_of(update.get("content")).strip()
        return [{"type": "thinking", "content": t[:THOUGHT_CAP]}] if t else []
    if kind in ("tool_call", "tool_call_update"):
        tid = str(update.get("toolCallId") or "")
        out = []
        if tid not in st["tools"]:
            args = update.get("rawInput") if isinstance(update.get("rawInput"), dict) else update.get("args")
            name = str(update.get("name") or update.get("title") or "")
            # call_mcp_tool or mcp_<server>_<tool> -> the tool really called, with the model's toolSummary
            name, params = antigravity_cli.unwrap_mcp_call(name, args if isinstance(args, dict) else {})
            name, params = unwrap_mcp_name(name, params, st.get("servers") or [])
            st["tools"][tid] = (name, params)
            out.append({"type": "tool_call", "name": name, "id": tid, "input": params})
        status = str(update.get("status") or "").lower()
        if status in ("completed", "failed") and tid not in st["done"]:
            st["done"].add(tid)
            out.append({"type": "tool_result", "id": tid, "status": "error" if status == "failed" else "",
                        "content": tool_output(update)[:OUTPUT_CAP]})
        return out
    if kind == "usage_update":
        try:
            st["context"] = int(update.get("used") or 0) or st["context"]
        except (TypeError, ValueError):
            pass
    return []


def usage_event(usage, context: int) -> Optional[dict]:
    """The reply's usage (this turn's own numbers) in the shape the other engines report."""
    if not isinstance(usage, dict) or not usage:
        return None
    inp = int(usage.get("inputTokens") or 0)
    cached = int(usage.get("cachedReadTokens") or 0)
    out = int(usage.get("outputTokens") or 0)
    return {"type": "usage", "context_tokens": int(context or 0) or inp + cached, "input_tokens": inp,
            "output_tokens": out, "total_tokens": int(usage.get("totalTokens") or 0) or inp + cached + out,
            "cached": cached}


async def run(cli, prompt: str) -> AsyncIterator[dict]:
    """One chat turn on a warm `agy acp`. Yields AntigravityCLI's events (plus `thinking`), a `session` event first.

    `prompt` carries the whole context for a NEW thread (the instructions go in front of it); `cli.resume_prompt` is
    sent instead when the thread really continues. Raises Fallback before anything is yielded when the turn cannot
    start here. Sets `cli.retry_one_shot` (and yields nothing more) when the turn failed before any text or tool for
    a reason a retry may fix, so the caller runs it the one-shot way with its own retries.
    """
    import antigravity_cli as agy
    import claude_cli as cc
    import localefmt
    import text_breaks

    loop = asyncio.get_running_loop()
    warm_key = str(getattr(cli, "warm_key", "") or "")
    want = str(cli.session_id or "").strip()
    argv = cli.acp_args()
    env = cli.engine_env()
    cwd = str(cli.cwd)
    servers = mcp_servers(cli)
    why: dict = {}
    slot = (warm_pool.POOL.take(warm_key, KIND, fingerprint(cli, argv, want, servers), why)
            if (warm_key and want) else None)
    if slot is None and not why.get("cold"):
        why["cold"] = "new_thread" if not want else "no_key"
    handle: Optional[AcpHandle] = None
    proc = lines = None
    sid = ""
    lost = False
    sent = False
    rid = 0
    for _attempt in (1, 2):
        if slot is not None:
            handle = slot.handle
            proc, lines, sid = handle.proc, handle.lines, handle.session_id
            lines.attach(loop, drop_stale=True)
        else:
            proc, lines, sid, lost, last = await open_session(argv, env, cwd, want, cli.model,
                                                              getattr(cli, "effort", None), cli.mode,
                                                              servers)  # raises Fallback
            handle = AcpHandle(proc, lines, sid, last)
            if lost:
                why["cold"] = "thread_lost"
        continuing = bool(want) and not lost
        if continuing and cli.resume_prompt is not None:
            text = cli.resume_prompt
        elif continuing:
            text = prompt
        else:
            text = agy.first_message(cli.instructions, prompt)
        rid = handle.new_id()
        try:
            await asyncio.to_thread(agy_warm._write, proc, request_line(
                rid, "session/prompt", {"sessionId": sid, "prompt": [{"type": "text", "text": text}]}))
            sent = True
            break
        except (OSError, ValueError) as e:
            lines.detach()
            if slot is not None:
                # The warm process died between turns: open a new one on the same thread.
                warm_pool.POOL.release(slot, keep=False)
                slot = None
                why["cold"] = "process_died"
                continue
            agy_warm._stop(proc)
            raise Fallback(f"stdin: {type(e).__name__}: {e}")
    if not sent:
        raise Fallback("stdin closed twice")

    with cc._PROC_LOCK:
        cc._ACTIVE_PROCS[proc] = cli.tag
    try:   # a warm agy keeps the mark of its conversation from its start: this turn still has to look for it
        import tien_trinh_nen
        tien_trinh_nen.note_mark(cli.tag, tien_trinh_nen.mark_for(cli.tag))
    except Exception:  # noqa: BLE001
        pass

    warm = slot is not None
    finished = False
    keep = False
    ok = False
    timed_out = False
    try:
        yield {"type": "session", "session_id": sid, "warm": warm,
               **({} if warm else {"cold": why.get("cold") or "new_thread"})}
        cap = cli.turn_cap()
        deadline = (time.monotonic() + cap) if cap > 0 else None
        pieces: list = []
        st = new_state(server_names(cli, servers))
        errors: list = []
        used_tool = after_tool = maybe_running = False
        status = ""
        while True:
            try:
                line = await lines.get(None if deadline is None else max(0.0, deadline - time.monotonic()))
            except asyncio.TimeoutError:
                timed_out = True
                break
            if line is None:
                break
            try:
                msg = json.loads(line)
            except ValueError:
                continue
            if not isinstance(msg, dict):
                continue
            method = msg.get("method")
            if method:
                if "id" in msg:
                    try:
                        await asyncio.to_thread(agy_warm._write, proc, answer_request(msg, cli.mode))
                    except (OSError, ValueError):
                        pass
                    continue
                params = msg.get("params") if isinstance(msg.get("params"), dict) else {}
                if method != "session/update" or str(params.get("sessionId") or sid) != sid:
                    continue
                n = len(pieces)
                for out in translate(params.get("update"), st):
                    t = out["type"]
                    if t == "_text":
                        pieces.append(out["content"])
                        continue
                    if t == "tool_call":
                        used_tool = after_tool = True
                    elif t == "tool_result":
                        name, args = st["tools"].get(out["id"], ("", {}))
                        if agy_warm.left_running(name, args, str(out.get("content") or "")):
                            maybe_running = True
                    yield out
                if after_tool and len(pieces) > n:
                    text_breaks.break_after_tool(pieces, n)
                    after_tool = False
                for piece in pieces[n:]:
                    if piece:
                        yield {"type": "delta", "content": piece}
                continue
            if msg.get("id") != rid:
                continue
            if "error" in msg:
                err = msg.get("error")
                err = err if isinstance(err, dict) else {"message": str(err)}
                errors.append(str(err.get("message") or "")[:1500] or localefmt.chu(
                    "Antigravity CLI lỗi.", "Antigravity CLI error."))
                status = "error"
            else:
                res = msg.get("result") if isinstance(msg.get("result"), dict) else {}
                stop = str(res.get("stopReason") or "")
                status = "success" if stop in OK_STOPS else "error"
                if stop == "refusal":
                    errors.append(localefmt.chu("Model từ chối trả lời câu này.",
                                                "The model declined to answer this."))
                elif status == "error":
                    errors.append(localefmt.chu(f"Antigravity CLI dừng lượt ({stop or 'không rõ lý do'}).",
                                                f"Antigravity CLI stopped the turn ({stop or 'no reason given'})."))
                u = usage_event(res.get("usage"), st["context"])
                if u:
                    yield u
            break
        text = "".join(pieces).strip()
        ok = status == "success"
        if not status and not timed_out:
            # agy ended without answering the prompt: say why if it said anything.
            tail = lines.stderr_tail()
            if agy._la_loi_chua_dang_nhap(tail):
                errors.append(tail)
            else:
                errors.append(tail[:1500] or localefmt.chu("Antigravity CLI dừng giữa lượt.",
                                                           "Antigravity CLI stopped mid-turn."))
        if timed_out:
            errors.append(agy._cau_bao_het_gio("print timeout", cap))
        errors = [localefmt.chu("Antigravity CLI chưa đăng nhập. Gõ `agy` một lần trên máy chạy Javis.",
                                "Antigravity CLI is not signed in. Type `agy` once on the machine running Javis.")
                  if agy._la_loi_chua_dang_nhap(e) else e for e in errors]
        if (not ok and not text and not used_tool and not timed_out
                and any(agy._la_loi_tam_thoi(e) for e in errors)):
            # Nothing done yet and the provider may only be busy: the one-shot path retries with a pause.
            cli.retry_one_shot = True
            finished = True
            return
        for e in errors:
            yield {"type": "error", "content": e}
        if text:
            yield {"type": "final", "content": text}
        elif ok:
            yield {"type": "error", "content": localefmt.chu(
                "Antigravity CLI chạy xong nhưng không trả về nội dung nào.",
                "Antigravity CLI finished but returned nothing.")}
        keep = bool(warm_key) and ok and not maybe_running and proc.poll() is None
        finished = True
    finally:
        with cc._PROC_LOCK:
            cc._ACTIVE_PROCS.pop(proc, None)
        lines.detach()
        cli.session_id = sid or None
        # A thread is worth resuming when it answered; one that only failed is opened anew next time.
        cli.resumable = bool(sid) and finished and ok
        effort = getattr(cli, "effort", None)
        if not finished or timed_out:
            # Stopped, out of time, or the chat went away mid-turn: as the one-shot path does, the process goes.
            agy_warm._stop(proc)
            if slot is not None:
                warm_pool.POOL.release(slot, keep=False)
        elif keep:
            fp_now = fingerprint(cli, argv, sid, servers)
            if slot is not None:
                warm_pool.POOL.release(slot, fingerprint=fp_now)
            else:
                new = warm_pool.POOL.admit(warm_key, KIND, fp_now, handle,
                                           recipe=_recipe(argv, env, cwd, sid, cli.model, effort, cli.mode, servers))
                if new is not None:
                    warm_pool.POOL.release(new)
                else:
                    agy_warm._hand_back_after_turn(cli, proc)
        else:
            if slot is not None:
                warm_pool.POOL.detach(slot)      # out of the pool, this turn closes it below
            if warm_key and ok and sid:
                # The thread is fine, only this process had to go: the owner typing the next message still
                # reopens one ahead of it (warm_pool.prewarm).
                warm_pool.POOL.remember(warm_key, KIND, fingerprint(cli, argv, sid, servers),
                                        _recipe(argv, env, cwd, sid, cli.model, effort, cli.mode, servers))
            agy_warm._hand_back_after_turn(cli, proc)
