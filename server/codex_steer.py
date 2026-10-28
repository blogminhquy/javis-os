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

0.382.0 (docs/dev/2026-10-toc-do-luot-chat-spec.md):
- the answer streams as Codex writes it (`item/agentMessage/delta`) instead of one block per finished message;
- the system prompt goes once, as `developerInstructions` of `thread/start`, instead of in front of every message.
  Checked with Codex 0.160: a new process that resumes the thread without them still follows them;
- a conversation that sets `cli.warm_key` keeps its app-server and thread for the next turn (warm_pool.py), which then
  starts with `turn/start` only. On POSIX a turn that ran a shell command hands its process back the old way (stdin
  closed, process group recorded) so tien_trinh_nen still adopts what it left running.
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
import turn_lane
import warm_pool

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
        self._held: list = []     # lines that came while no turn listened (a warm process between turns)
        self.keep_reading = False  # True for a warm process: outlive the loop of the turn that opened it
        threading.Thread(target=self._read_out, daemon=True).start()
        threading.Thread(target=self._read_err, daemon=True).start()

    def attach(self, loop: asyncio.AbstractEventLoop) -> None:
        """A new turn listens on a warm process. What came between turns belongs to the last one: dropped, except
        EOF (the process died meanwhile)."""
        with self._lock:
            died = None in self._held
            self._held = []
            self.loop = loop
            self.queue = asyncio.Queue()
        if died:
            self.queue.put_nowait(None)

    def detach(self) -> None:
        with self._lock:
            self.loop = None

    def _push(self, item) -> bool:
        with self._lock:
            loop, queue = self.loop, self.queue
            if loop is None:
                if len(self._held) < 500 or item is None:
                    self._held.append(item)
                return True
        try:
            loop.call_soon_threadsafe(queue.put_nowait, item)
            return True
        except RuntimeError:   # the turn is over and its loop closed
            if not self.keep_reading:
                return False   # nobody is listening any more
            with self._lock:
                if self.loop is loop:
                    self.loop = None
                self._held.append(item)
            return True

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


def _thread_params(cli, start: bool = False) -> dict:
    p = {"cwd": cli.cwd, "approvalPolicy": "never",
         "sandbox": cli.sandbox or "danger-full-access"}
    if cli.model:
        p["model"] = cli.model
    if start and (cli.instructions or "").strip():
        # Once per thread (0.382.0). A resumed thread already carries them: from its own thread/start, or, for a thread
        # an older Javis or `codex exec` opened, in front of its first message.
        p["developerInstructions"] = cli.instructions.strip()
    return p


class CodexHandle(warm_pool.Handle):
    """A `codex app-server` with its thread open, kept between turns of one conversation."""
    kind = "codex"

    def __init__(self, proc, rpc: "_Rpc", thread_id: str, lane=None):
        self.proc = proc
        self.rpc = rpc
        self.thread_id = thread_id
        self.lane = lane

    def alive(self) -> bool:
        return self.proc.poll() is None

    async def close(self) -> None:
        _close_proc(self.proc)
        if self.lane is not None:
            self.lane.close()


def _close_proc(proc) -> None:
    """Close the way `codex exec` ends: stdin closed, so background commands keep their process group."""
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


_INSTR_FILE = "codex_instr_threads.json"
_INSTR_MAX = 2000
_instr_lock = threading.Lock()


def _instr_path() -> Path:
    from config import STATE_DIR
    return Path(STATE_DIR) / _INSTR_FILE


def _instr_threads() -> List[str]:
    try:
        data = json.loads(_instr_path().read_text(encoding="utf-8"))
        return [str(x) for x in data] if isinstance(data, list) else []
    except Exception:
        return []


def mark_instructions(thread_id: str) -> None:
    """This thread got the system prompt as developerInstructions at thread/start (0.382.0)."""
    if not thread_id:
        return
    with _instr_lock:
        ids = [t for t in _instr_threads() if t != thread_id] + [thread_id]
        try:
            p = _instr_path()
            p.parent.mkdir(parents=True, exist_ok=True)
            tmp = p.with_suffix(".tmp")
            tmp.write_text(json.dumps(ids[-_INSTR_MAX:]), encoding="utf-8")
            os.replace(tmp, p)
        except Exception as e:  # noqa: BLE001 - worst case the next turn sends the prompt again, as before
            print(f"[codex steer] cannot record instructions of {thread_id}: {e}", file=sys.stderr)


def carries_instructions(thread_id: str) -> bool:
    """False for a thread an older Javis or `codex exec` opened: its rules are only in its first message, which
    Codex's own compaction may summarise away, so such a thread keeps getting them in front of every message."""
    return bool(thread_id) and thread_id in _instr_threads()


def _stat(p) -> str:
    try:
        st = os.stat(p)
        return f"{st.st_size}:{st.st_mtime_ns}"
    except OSError:
        return "-"


def _codex_account(home: str) -> str:
    """Who Codex is signed in as, without the file's stat: Javis rewrites auth.json on every turn when it holds the
    ChatGPT tokens (openai_oauth.write_codex_auth stamps last_refresh), and a refreshed token is the same account."""
    try:
        with open(os.path.join(home, "auth.json"), encoding="utf-8") as f:
            data = json.load(f) or {}
        tokens = data.get("tokens") or {}
        return str(tokens.get("account_id") or ("api-key" if data.get("OPENAI_API_KEY") else ""))
    except Exception:
        return "-"


def _fingerprint(cli, args: List[str]) -> str:
    """What the warm process was opened with. The thread id is part of it: a rotated or reset thread runs cold."""
    import hashlib
    try:
        st = os.stat(cli.cli_path)
        binary = f"{cli.cli_path}:{st.st_size}:{st.st_mtime_ns}"
    except OSError:
        binary = str(cli.cli_path)
    # The hub turn key changes with every lane, so it is left out: the slot keeps its own lane.
    args = [a for a in args if not a.startswith("mcp_servers.javis.http_headers.X-Javis-Turn")]
    import claude_cli as cc
    home = str(getattr(cli, "codex_home", None) or cc._codex_home())
    raw = json.dumps([binary, args, home, cli.cwd, cli.sandbox or "", cli.model or "", str(cli.session_id or ""),
                      # another account or a config edit needs a new process (Codex reads both at start-up)
                      _codex_account(home), _stat(os.path.join(home, "config.toml"))],
                     ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _args(cli, turn_key: Optional[str]) -> List[str]:
    """argv of app-server. `turn_key` is the `-c` carrying the hub turn key (a lane's fixed key on a warm process)."""
    import claude_cli as cc
    _acct_home = getattr(cli, "codex_home", None)   # extra ChatGPT account (plan_accounts, 0.353.0)
    overrides = profile_overrides(cli.profile, Path(_acct_home) if _acct_home else cc._codex_home())
    args = [cli.cli_path]
    for c in overrides + list(cli.extra_config or []):
        args += ["-c", c]
    if turn_key:
        args += ["-c", turn_key]
    if (cli.transport or cc.codex_transport()) == "http":
        for c in cc.codex_http_config():
            args += ["-c", c]
    args.append("app-server")
    return args


def _turn_key(cli, lane) -> Optional[str]:
    if not cli.hub_turn:
        return None
    try:
        import turn_context
        if lane is not None:
            return f'{turn_context.CODEX_HEADER_KEY}="{lane.key}"'
        return turn_context.codex_override()
    except Exception:
        return None


def _spawn(args: List[str], cwd: str, acct_home):
    import claude_cli as cc
    return subprocess.Popen(
        args, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=cwd, text=True,
        encoding="utf-8", errors="replace", bufsize=1,
        creationflags=(subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0),
        start_new_session=(os.name != "nt"), env=cc.codex_env(acct_home))


async def run(cli, prompt: str) -> AsyncIterator[dict]:
    """One chat turn on `codex app-server`, yielding CodexCLI's event dicts. Raises Fallback before anything is yielded
    when the turn cannot start there."""
    import claude_cli as cc
    import engine as engine_mod
    import localefmt
    from claude_sdk_engine import tran_watchdog

    sid = steer_inbox.current_sid()
    _acct_home = getattr(cli, "codex_home", None)
    warm_key = str(getattr(cli, "warm_key", "") or "")
    if cli.session_id and cli.instructions and not carries_instructions(cli.session_id):
        prompt = cli.instructions.strip() + "\n\n" + prompt   # a thread from before 0.382.0: as before
    lane = None
    if warm_key:
        import turn_context
        lane = turn_lane.Lane()
    try:
        args = _args(cli, _turn_key(cli, lane))      # an unreadable profile raises Fallback here, as before
    except BaseException:
        if lane is not None:
            lane.close()
        raise
    fp = _fingerprint(cli, args) if warm_key else ""
    resume_requested = bool(cli.session_id)
    t_start = time.time()
    loop = asyncio.get_running_loop()
    slot = warm_pool.POOL.take(warm_key, "codex", fp) if (warm_key and cli.session_id) else None
    proc = rpc = None
    seen: list = []
    started = False
    thread_id = ""
    turn_id = ""
    if slot is not None:
        # Warm: the process and the thread are open already, so the lane made above is not needed.
        if lane is not None:
            lane.close()
        h = slot.handle
        proc, rpc, lane, thread_id = h.proc, h.rpc, h.lane, h.thread_id
        rpc.attach(loop)
        if lane is not None:
            lane.attach()
        try:
            res = await _call(rpc, "turn/start", {"threadId": thread_id, "input": [{"type": "text", "text": prompt}]},
                              time.monotonic() + 30.0, seen)
            turn_id = str(((res.get("turn") or {}).get("id")) or "")
        except (Fallback, asyncio.TimeoutError, OSError, ValueError) as e:
            print(f"[codex warm] turn/start on the warm process failed ({e}), opening a new one", file=sys.stderr)
            turn_id = ""
        except BaseException:
            # Stop or a dropped socket right here: the process may have taken the turn with nobody listening.
            warm_pool.POOL.release(slot, keep=False)
            raise
        if not turn_id:
            warm_pool.POOL.release(slot, keep=False)
            slot = None
            proc = rpc = None
            seen = []
            import turn_context
            lane = turn_lane.Lane()
            try:
                args = _args(cli, _turn_key(cli, lane))
            except BaseException:
                lane.close()
                raise
    if proc is None:
        if lane is not None:
            lane.attach()
        try:
            proc = _spawn(args, cli.cwd, _acct_home)
        except Exception as e:
            if lane is not None:
                lane.close()
            raise Fallback(f"spawn: {type(e).__name__}: {e}")
        rpc = _Rpc(proc, loop)
        rpc.keep_reading = bool(warm_key)
        if not warm_key:
            # One process per turn, as before 0.382.0: its group is recorded now. A warm-capable turn records it only
            # when it hands the process back (end of this function), else the warm process itself would read as work
            # left running in the background.
            try:
                import tien_trinh_nen
                tien_trinh_nen.ghi_nhom(cli.tag, proc.pid)
            except Exception:
                pass
    with cc._PROC_LOCK:
        cc._ACTIVE_PROCS[proc] = cli.tag
    keep = False
    try:
        if not turn_id:
            deadline = time.monotonic() + START_TIMEOUT_S
            try:
                await _call(rpc, "initialize", {"clientInfo": {"name": "javis", "version": "1"}}, deadline, seen)
                rpc.send("initialized", {}, notify=True)
                if cli.session_id:
                    res = await _call(rpc, "thread/resume", {**_thread_params(cli), "threadId": cli.session_id,
                                                              "excludeTurns": True}, deadline, seen)
                else:
                    tparams = _thread_params(cli, start=True)
                    res = await _call(rpc, "thread/start", tparams, deadline, seen)
                thread_id = str(((res.get("thread") or {}).get("id")) or "")
                if not thread_id:
                    raise Fallback("no thread id")
                if not cli.session_id and "developerInstructions" in tparams:
                    await asyncio.to_thread(mark_instructions, thread_id)
                res = await _call(rpc, "turn/start", {"threadId": thread_id,
                                                      "input": [{"type": "text", "text": prompt}]}, deadline, seen)
                turn_id = str(((res.get("turn") or {}).get("id")) or "")
                if not turn_id:
                    raise Fallback("no turn id")
            except asyncio.TimeoutError:
                raise Fallback("start timed out")
            except (OSError, ValueError) as e:
                raise Fallback(f"{type(e).__name__}: {e}")
        started = True
        cli.session_id = thread_id
        yield {"type": "session", "session_id": thread_id, "warm": slot is not None}

        IDLE = tran_watchdog("JAVIS_CLAUDE_IDLE_TIMEOUT", "0")
        TOOL_IDLE = tran_watchdog("JAVIS_CLAUDE_TOOL_TIMEOUT", "3600")
        last = time.monotonic()
        busy = 0
        final_text = ""
        tok_in = tok_out = tok_cache = 0
        error_msg = ""
        sandbox_broken = False
        steering: Dict[int, list] = {}   # steer request id -> inbox items, put back if Codex refuses
        done = False
        status = ""
        ran_command = False
        settle_until = 0.0
        pending = list(seen)
        streamed = set()       # agentMessage ids already shown delta by delta (0.382.0)
        shown_any = False      # some answer text already went out this turn

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
            if p.get("turnId") not in (None, turn_id):
                continue   # late news of an earlier turn on a warm process
            if method == "item/agentMessage/delta":
                d = engine_mod.strip_provider_markers(str(p.get("delta") or ""))
                iid = str(p.get("itemId") or "")
                if d:
                    if iid not in streamed and shown_any:
                        yield {"type": "text", "content": "\n"}
                    streamed.add(iid)
                    shown_any = True
                    yield {"type": "text", "content": d}
            elif method == "item/started":
                it = p.get("item") or {}
                if it.get("type") in TOOL_TYPES:
                    busy += 1
                    ran_command = ran_command or it.get("type") == "commandExecution"
                    ei = exec_item(it)
                    yield {"type": "progress", "name": cc._codex_tool_name(ei), "item": ei, "id": ei["id"]}
            elif method == "item/completed":
                it = p.get("item") or {}
                t = it.get("type")
                if t == "agentMessage":
                    txt = engine_mod.strip_provider_markers(it.get("text") or "")
                    if txt.strip():
                        final_text += (("\n" if final_text else "") + txt)
                        if str(it.get("id") or "") not in streamed:
                            if shown_any:
                                yield {"type": "text", "content": "\n"}
                            shown_any = True
                            yield {"type": "text", "content": txt}
                elif t in TOOL_TYPES:
                    busy = max(0, busy - 1)
                    ran_command = ran_command or t == "commandExecution"
                    ei = exec_item(it)
                    yield {"type": "tool_call", "name": cc._codex_tool_name(ei), "item": ei, "id": ei["id"]}
                elif t and t not in _QUIET_TYPES:
                    yield {"type": "item", "item": exec_item(it)}
            elif method == "account/rateLimits/updated":
                try:   # 0.329.0: the plan's 5-hour and weekly meters, for the composer ring
                    import plan_limits
                    plan_limits.ghi_codex(p)
                except Exception:  # noqa: BLE001
                    pass
            elif method == "thread/tokenUsage/updated" and p.get("turnId") == turn_id:
                lu = ((p.get("tokenUsage") or {}).get("last") or {})
                tok_in += int(lu.get("inputTokens") or 0)
                tok_out += int(lu.get("outputTokens") or 0)
                tok_cache += int(lu.get("cachedInputTokens") or 0)   # 0.345.0: đã nằm trong inputTokens
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
                status = str(turn.get("status") or "")
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
                           "tokens_in": tok_in, "tokens_cache_read": tok_cache, "tokens_out": tok_out}
                elif status == "failed":
                    msg = str(((turn.get("error") or {}).get("message")) or error_msg or "turn failed")
                    yield {"type": "error", "content": "Codex: " + msg,
                           "resume_failed": resume_requested and cc._looks_like_codex_resume_error(msg)}
                # "interrupted": the owner pressed Stop; nothing to add.
        # Keep the process for the next turn only after a clean, finished turn that ran no shell command. A command may
        # have left something running: on POSIX only the old hand-back lets tien_trinh_nen adopt it, and on Windows a
        # later Stop (taskkill /T on the warm process) would take it down with the process.
        keep = (bool(warm_key) and done and status == "completed" and not steering
                and proc.poll() is None and not ran_command)
    finally:
        if not started:
            print(f"[codex steer] fallback to exec ({' | '.join(rpc.stderr[-2:])[:200]})", file=sys.stderr)
        with cc._PROC_LOCK:
            cc._ACTIVE_PROCS.pop(proc, None)
        if lane is not None:
            lane.detach()
        handled = False
        if keep:
            rpc.detach()
            fp_now = _fingerprint(cli, args)    # the session id is this thread now
            if slot is not None:
                warm_pool.POOL.release(slot, fingerprint=fp_now)
                handled = True
            else:
                new = warm_pool.POOL.admit(warm_key, "codex", fp_now, CodexHandle(proc, rpc, thread_id, lane),
                                           recipe=_recipe(cli, args, _acct_home, thread_id))
                if new is not None:
                    warm_pool.POOL.release(new)
                    handled = True
        elif slot is not None:
            # A warm turn that ends badly: hand the process back the old way so a left-over command is adopted.
            warm_pool.POOL.forget(warm_key)
            slot = None
        if not handled:
            if warm_key:
                try:
                    import tien_trinh_nen
                    tien_trinh_nen.ghi_nhom(cli.tag, proc.pid)
                except Exception:
                    pass
            _close_proc(proc)
            if lane is not None:
                lane.close()


def _recipe(cli, args: List[str], acct_home, thread_id: str):
    """How to reopen this process for a prewarm: same argv, same thread, resumed. The instructions live on the thread."""
    cwd, params = cli.cwd, {**_thread_params(cli), "threadId": thread_id, "excludeTurns": True}
    lane_arg = next((a for a in args if a.startswith("mcp_servers.javis.http_headers.")), None)

    async def _open() -> CodexHandle:
        import turn_context
        lane = turn_lane.Lane() if lane_arg else None
        argv = [(f'{turn_context.CODEX_HEADER_KEY}="{lane.key}"' if (lane and a == lane_arg) else a) for a in args]
        proc = _spawn(argv, cwd, acct_home)
        rpc = _Rpc(proc, asyncio.get_running_loop())
        rpc.keep_reading = True
        try:
            deadline = time.monotonic() + START_TIMEOUT_S
            await _call(rpc, "initialize", {"clientInfo": {"name": "javis", "version": "1"}}, deadline, [])
            rpc.send("initialized", {}, notify=True)
            await _call(rpc, "thread/resume", params, deadline, [])
        except BaseException:
            _close_proc(proc)
            if lane is not None:
                lane.close()
            raise
        rpc.detach()
        return CodexHandle(proc, rpc, thread_id, lane)
    return _open
