"""Codex chat turns that take the owner's messages mid-way (0.213.0).

`codex exec` reads one prompt from stdin and runs to the end, so until 0.212 a message sent while a Codex turn ran
waited for the next turn (steer_inbox "after"). Codex's own app (Enter while it works) uses `turn/steer` of
`codex app-server`: the message joins the running turn at the next model request, and a message that arrives while
the final answer is being written makes Codex run one more round in the same turn. Checked against the pinned 0.153.4
with a fake Responses endpoint (tests/python/test_codex_steer_0213.py): steer while a command runs, steer during the
final answer, resume of a thread `codex exec` created, the profile's MCP entry passed as `-c`.

Only the main chat engine of a web or chat-channel turn takes this path (`CodexCLI.steer`, set by main.py) and only
while that turn's steer inbox is open. Background work, workflows and loops keep `codex exec`. Anything that fails
before the turn has started (the profile cannot be read, app-server does not answer, the thread cannot open) falls
back to `codex exec`, i.e. exactly the old behaviour. JAVIS_CODEX_STEER=0 turns the whole path off.

Differences from exec handled here, each found by trying it:
- app-server ignores the root flags `-m`, `--sandbox`, `--ask-for-approval` and
  `--dangerously-bypass-approvals-and-sandbox`, so model, sandbox and approval go in `thread/start`;
- app-server refuses `-p <profile>`, so the profile file is flattened into `-c key=value` overrides;
- items arrive in camelCase (`commandExecution`, `aggregatedOutput`): `exec_item` turns them into the exec shape the
  rest of Javis reads (tool labels, file paths, `aggregated_output`).
"""
from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import AsyncIterator, Dict, List, Optional

import steer_inbox

ENV_SWITCH = "JAVIS_CODEX_STEER"
POLL_S = 0.25            # how often a running turn looks for messages to pass on
START_TIMEOUT_S = 120.0  # initialize + thread/start (a required MCP server may take its startup_timeout_sec)
STEER_SETTLE_S = 2.0     # after turn/completed, wait this long for answers to steer requests still in flight

TOOL_TYPES = ("commandExecution", "mcpToolCall", "webSearch", "dynamicToolCall")
_QUIET_TYPES = ("userMessage", "agentMessage", "reasoning", "plan", "hookPrompt", "contextCompaction")


class Fallback(Exception):
    """The turn could not start on app-server: run it with `codex exec` instead."""


def enabled() -> bool:
    return str(os.getenv(ENV_SWITCH, "1")).strip().lower() not in ("0", "false", "no", "off")


def wanted(cli) -> bool:
    """This query is the main engine of a chat turn whose inbox is open."""
    if not enabled() or not getattr(cli, "steer", False):
        return False
    sid = steer_inbox.current_sid()
    return bool(sid) and steer_inbox.INBOX.running(sid)


# ---- profile -> `-c` overrides ---------------------------------------------------------------
def _toml_value(v) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return str(v)
    if isinstance(v, str):
        return json.dumps(v, ensure_ascii=False)   # JSON string escapes are valid TOML basic-string escapes
    if isinstance(v, list):
        return "[" + ", ".join(_toml_value(x) for x in v) + "]"
    if isinstance(v, dict):
        return "{" + ", ".join(f"{json.dumps(str(k))} = {_toml_value(x)}" for k, x in v.items()) + "}"
    raise ValueError(f"unsupported TOML value {type(v).__name__}")


def _flatten(prefix: str, d: dict, out: List[str]) -> None:
    for k, v in d.items():
        k = str(k)
        if "." in k or not k:
            # Codex splits a `-c` key on every dot and keeps quotes literally (see mcp_hub, CODEX_VAULT_KEY): such a
            # key cannot be written as an override.
            raise ValueError(f"key {k!r} cannot be passed with -c")
        key = f"{prefix}.{k}" if prefix else k
        if isinstance(v, dict) and v:
            _flatten(key, v, out)
        else:
            out.append(f"{key}={_toml_value(v)}")


def profile_overrides(profile: Optional[str], codex_home: Path) -> List[str]:
    """`-c` overrides equal to `codex -p <profile>` (app-server refuses -p). Raises Fallback when unreadable."""
    if not profile:
        return []
    try:
        import tomllib
    except Exception as e:   # Python 3.10
        raise Fallback(f"tomllib missing: {e}")
    for base in (codex_home, Path.home() / ".codex"):
        p = base / f"{profile}.config.toml"
        if p.is_file():
            try:
                with open(p, "rb") as f:
                    data = tomllib.load(f) or {}
                out: List[str] = []
                _flatten("", data, out)
                return out
            except Exception as e:
                raise Fallback(f"profile {p.name}: {type(e).__name__}: {e}")
    raise Fallback(f"profile {profile!r} not found")


# ---- v2 items -> the `codex exec --json` shape ---------------------------------------------------
_STATUS = {"inProgress": "in_progress", "completed": "completed", "failed": "failed", "declined": "declined"}


def exec_item(it: dict) -> dict:
    """An app-server ThreadItem in the shape `codex exec --json` prints, which the rest of Javis reads."""
    t = str(it.get("type") or "")
    iid = str(it.get("id") or "")
    st = _STATUS.get(str(it.get("status") or ""), it.get("status"))
    if t == "commandExecution":
        return {"id": iid, "type": "command_execution", "command": it.get("command") or "",
                "aggregated_output": it.get("aggregatedOutput") or "", "exit_code": it.get("exitCode"), "status": st}
    if t == "mcpToolCall":
        return {"id": iid, "type": "mcp_tool_call", "server": it.get("server") or "", "tool": it.get("tool") or "",
                "arguments": it.get("arguments"), "result": it.get("result"), "error": it.get("error"), "status": st}
    if t == "webSearch":
        return {"id": iid, "type": "web_search_call", "query": it.get("query") or "", "action": it.get("action")}
    if t == "dynamicToolCall":
        return {"id": iid, "type": "tool_call", "name": it.get("tool") or "", "arguments": it.get("arguments"),
                "status": st}
    if t == "fileChange":
        return {"id": iid, "type": "file_change", "status": st,
                "changes": [{"path": c.get("path"), "kind": (c.get("kind") or {}).get("type")
                             if isinstance(c.get("kind"), dict) else c.get("kind")}
                            for c in (it.get("changes") or []) if isinstance(c, dict)]}
    snake = "".join("_" + c.lower() if c.isupper() else c for c in t)
    out = {k: v for k, v in it.items() if k not in ("type", "id")}
    out.update({"id": iid, "type": snake})
    return out


# ---- one turn ----------------------------------------------------------------------------------
class _Rpc:
    """JSON-RPC over the app-server's stdin/stdout. Reader threads feed one asyncio queue (codex_realtime's pattern)."""

    def __init__(self, proc, loop: asyncio.AbstractEventLoop):
        self.proc = proc
        self.loop = loop
        self.queue: asyncio.Queue = asyncio.Queue()
        self.stderr: List[str] = []
        self._ids = 0
        self._lock = threading.Lock()
        threading.Thread(target=self._read_out, daemon=True).start()
        threading.Thread(target=self._read_err, daemon=True).start()

    def _push(self, item) -> bool:
        try:
            self.loop.call_soon_threadsafe(self.queue.put_nowait, item)
            return True
        except RuntimeError:   # the turn is over and its loop closed: nobody is listening any more
            return False

    def _read_out(self):
        try:
            for line in self.proc.stdout:
                line = line.strip()
                if line and not self._push(line):
                    return
        except Exception:
            pass
        self._push(None)   # EOF

    def _read_err(self):
        try:
            for line in self.proc.stderr:
                line = line.rstrip()
                if line:
                    self.stderr.append(line)
                    del self.stderr[:-200]
        except Exception:
            pass

    def send(self, method: str, params: dict, notify: bool = False) -> int:
        msg = {"method": method, "params": params}
        mid = 0
        with self._lock:
            if not notify:
                self._ids += 1
                mid = msg["id"] = self._ids
            self.proc.stdin.write(json.dumps(msg, ensure_ascii=False) + "\n")
            self.proc.stdin.flush()
        return mid

    def reply(self, mid, error: str) -> None:
        with self._lock:
            self.proc.stdin.write(json.dumps({"id": mid, "error": {"code": -32601, "message": error}}) + "\n")
            self.proc.stdin.flush()


async def _call(rpc: _Rpc, method: str, params: dict, deadline: float, seen: list) -> dict:
    """Send a request and wait for its answer; notifications that arrive meanwhile are kept in `seen`."""
    mid = rpc.send(method, params)
    while True:
        left = deadline - time.monotonic()
        if left <= 0:
            raise Fallback(f"{method}: no answer")
        line = await asyncio.wait_for(rpc.queue.get(), timeout=left)
        if line is None:
            raise Fallback(f"{method}: app-server exited ({' | '.join(rpc.stderr[-3:])[:300]})")
        try:
            m = json.loads(line)
        except Exception:
            continue
        if m.get("id") == mid and "method" not in m:
            if "error" in m:
                raise Fallback(f"{method}: {(m.get('error') or {}).get('message')}")
            return m.get("result") or {}
        if "method" in m and "id" in m:
            rpc.reply(m["id"], "Javis does not grant requests from a chat turn")
            continue
        seen.append(line)


def _thread_params(cli) -> dict:
    p = {"cwd": cli.cwd, "approvalPolicy": "never",
         "sandbox": cli.sandbox or "danger-full-access"}
    if cli.model:
        p["model"] = cli.model
    return p


async def run(cli, prompt: str) -> AsyncIterator[dict]:
    """One chat turn on `codex app-server`, yielding CodexCLI's event dicts. Raises Fallback before anything is yielded
    when the turn cannot start there."""
    import claude_cli as cc
    import engine as engine_mod
    import localefmt
    from claude_sdk_engine import tran_watchdog

    sid = steer_inbox.current_sid()
    overrides = profile_overrides(cli.profile, cc._codex_home())
    args = [cli.cli_path]
    for c in overrides + list(cli.extra_config or []):
        args += ["-c", c]
    if cli.hub_turn:
        try:
            import turn_context
            luot = turn_context.codex_override()
        except Exception:
            luot = None
        if luot:
            args += ["-c", luot]
    if (cli.transport or cc.codex_transport()) == "http":
        for c in cc.codex_http_config():
            args += ["-c", c]
    args.append("app-server")

    resume_requested = bool(cli.session_id)
    t_start = time.time()
    full_prompt = (cli.instructions.strip() + "\n\n" + prompt) if cli.instructions else prompt
    loop = asyncio.get_running_loop()
    try:
        proc = subprocess.Popen(
            args, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=cli.cwd, text=True,
            encoding="utf-8", errors="replace", bufsize=1,
            creationflags=(subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0),
            start_new_session=(os.name != "nt"), env=cc.codex_env())
    except Exception as e:
        raise Fallback(f"spawn: {type(e).__name__}: {e}")
    with cc._PROC_LOCK:
        cc._ACTIVE_PROCS[proc] = cli.tag
    try:
        import tien_trinh_nen
        tien_trinh_nen.ghi_nhom(cli.tag, proc.pid)
    except Exception:
        pass
    rpc = _Rpc(proc, loop)
    seen: list = []
    started = False
    try:
        deadline = time.monotonic() + START_TIMEOUT_S
        try:
            await _call(rpc, "initialize", {"clientInfo": {"name": "javis", "version": "1"}}, deadline, seen)
            rpc.send("initialized", {}, notify=True)
            if cli.session_id:
                res = await _call(rpc, "thread/resume", {**_thread_params(cli), "threadId": cli.session_id,
                                                          "excludeTurns": True}, deadline, seen)
            else:
                res = await _call(rpc, "thread/start", _thread_params(cli), deadline, seen)
            thread_id = str(((res.get("thread") or {}).get("id")) or "")
            if not thread_id:
                raise Fallback("no thread id")
            res = await _call(rpc, "turn/start", {"threadId": thread_id,
                                                  "input": [{"type": "text", "text": full_prompt}]}, deadline, seen)
            turn_id = str(((res.get("turn") or {}).get("id")) or "")
            if not turn_id:
                raise Fallback("no turn id")
        except asyncio.TimeoutError:
            raise Fallback("start timed out")
        except (OSError, ValueError) as e:
            raise Fallback(f"{type(e).__name__}: {e}")
        started = True
        cli.session_id = thread_id
        yield {"type": "session", "session_id": thread_id}

        IDLE = tran_watchdog("JAVIS_CLAUDE_IDLE_TIMEOUT", "0")
        TOOL_IDLE = tran_watchdog("JAVIS_CLAUDE_TOOL_TIMEOUT", "3600")
        last = time.monotonic()
        busy = 0
        final_text = ""
        tok_in = tok_out = 0
        error_msg = ""
        sandbox_broken = False
        steering: Dict[int, list] = {}   # steer request id -> inbox items, put back if Codex refuses
        done = False
        settle_until = 0.0
        pending = list(seen)

        while True:
            if not done and sid:
                items = steer_inbox.INBOX.take(sid)
                if items:
                    note = steer_inbox.note_for([i["text"] for i in items])
                    try:
                        mid = rpc.send("turn/steer", {"threadId": thread_id, "expectedTurnId": turn_id,
                                                      "input": [{"type": "text", "text": note}]})
                        steering[mid] = items
                    except Exception:
                        steer_inbox.INBOX.requeue(sid, items)
            if done and (not steering or time.monotonic() > settle_until):
                break
            if pending:
                line = pending.pop(0)
            else:
                try:
                    line = await asyncio.wait_for(rpc.queue.get(), timeout=POLL_S)
                except asyncio.TimeoutError:
                    limit, why = (TOOL_IDLE, "tool") if busy else (IDLE, "im")
                    if limit and time.monotonic() - last > limit and not done:
                        cc._kill_tree(proc)
                        yield {"type": "error", "content": localefmt.chu(
                            f"Codex im {int(limit)}s ({'đang chờ công cụ' if why == 'tool' else 'giữa câu trả lời'})"
                            f" - đã dừng để tránh treo server.",
                            f"Codex was silent for {int(limit)}s ({'waiting on a tool' if why == 'tool' else 'mid-answer'})"
                            f" - stopped to avoid hanging the server.")}
                        return
                    continue
            if line is None:   # app-server gone
                if not done:
                    rc = proc.poll()
                    if rc is not None and rc >= 0 and rc != 0:
                        yield {"type": "error", "content": cc.codex_error_text(rc, rpc.stderr[-20:])}
                break
            last = time.monotonic()
            if not sandbox_broken and cc._SANDBOX_HONG.search(line):
                sandbox_broken = True
            try:
                m = json.loads(line)
            except Exception:
                continue
            method = m.get("method")
            if "id" in m and not method:   # an answer
                items = steering.pop(m["id"], None)
                if items is not None and "error" in m:
                    steer_inbox.INBOX.requeue(sid, items)   # the turn ended first: they run as the next turn
                continue
            if method and "id" in m:
                rpc.reply(m["id"], "Javis does not grant requests from a chat turn")
                continue
            p = m.get("params") or {}
            if p.get("threadId") not in (None, thread_id):
                continue   # a sub-agent's own thread
            if method == "item/started":
                it = p.get("item") or {}
                if it.get("type") in TOOL_TYPES:
                    busy += 1
                    ei = exec_item(it)
                    yield {"type": "progress", "name": cc._codex_tool_name(ei), "item": ei, "id": ei["id"]}
            elif method == "item/completed":
                it = p.get("item") or {}
                t = it.get("type")
                if t == "agentMessage":
                    txt = engine_mod.strip_provider_markers(it.get("text") or "")
                    if txt.strip():
                        final_text += (("\n" if final_text else "") + txt)
                        yield {"type": "text", "content": txt}
                elif t in TOOL_TYPES:
                    busy = max(0, busy - 1)
                    ei = exec_item(it)
                    yield {"type": "tool_call", "name": cc._codex_tool_name(ei), "item": ei, "id": ei["id"]}
                elif t and t not in _QUIET_TYPES:
                    yield {"type": "item", "item": exec_item(it)}
            elif method == "thread/tokenUsage/updated" and p.get("turnId") == turn_id:
                lu = ((p.get("tokenUsage") or {}).get("last") or {})
                tok_in += int(lu.get("inputTokens") or 0)
                tok_out += int(lu.get("outputTokens") or 0)
            elif method == "error":
                e = p.get("error") or {}
                msg = str(e.get("message") or "")
                if p.get("willRetry") or cc.la_thong_bao_ket_noi_lai(msg):
                    if "websocket" in msg.lower():
                        cc.ghi_codex_ws_hong(msg)
                    yield {"type": "retry", "content": msg}
                else:
                    error_msg = msg or error_msg
            elif method == "turn/completed" and (p.get("turn") or {}).get("id") == turn_id:
                turn = p.get("turn") or {}
                status = turn.get("status")
                done = True
                settle_until = time.monotonic() + STEER_SETTLE_S
                if status == "completed":
                    if sandbox_broken:
                        final_text = ((final_text + "\n\n" if final_text else "")
                                      + localefmt.chu(cc._NOTE_SANDBOX_HONG, cc._NOTE_SANDBOX_HONG_EN))
                    try:
                        import anh_codex
                        final_text, _ = anh_codex.dua_anh_ve_brain(final_text, thread_id, t_start,
                                                                   cli.vault_root or cli.cwd)
                    except Exception as e:
                        print(f"[anh codex] {type(e).__name__}: {e}", file=sys.stderr)
                    yield {"type": "final", "content": final_text, "session_id": thread_id,
                           "tokens_in": tok_in, "tokens_out": tok_out}
                elif status == "failed":
                    msg = str(((turn.get("error") or {}).get("message")) or error_msg or "turn failed")
                    yield {"type": "error", "content": "Codex: " + msg,
                           "resume_failed": resume_requested and cc._looks_like_codex_resume_error(msg)}
                # "interrupted": the owner pressed Stop; nothing to add.
    finally:
        if not started:
            print(f"[codex steer] fallback to exec ({' | '.join(rpc.stderr[-2:])[:200]})", file=sys.stderr)
        with cc._PROC_LOCK:
            cc._ACTIVE_PROCS.pop(proc, None)
        # Closing stdin ends app-server the way `codex exec` ends: background commands it started keep their process
        # group, which tien_trinh_nen adopts.
        try:
            proc.stdin.close()
        except Exception:
            pass

        def _reap(p=proc):
            try:
                p.wait(timeout=10)
            except Exception:
                try:
                    p.terminate()
                except Exception:
                    pass
        threading.Thread(target=_reap, daemon=True).start()
