"""`javis_code`: run a short read-only Python script that calls connection tools and returns only what it prints.

Why: Cloudflare's "Code Mode" showed that a model writing a little code against an API spends far fewer tokens than a
model calling tools one by one, because the intermediate results never pass through the conversation. Javis already
hides tool definitions behind the tool search and shapes large results into views with a ref (javis_query). What was
still missing is CHAINING: read orders, then look up each customer, then join with the ad spend, all in one step, with
only the final numbers coming back. This tool does that.

Hard rules, enforced here and not by the prompt:
  - Read only. A script can only reach connection tools through `call(tool, args)`, and every call must pass
    `tool_result_tools.is_plain_read` (the same strict test javis_query uses for reads Javis repeats by itself). The
    call then goes through the tool's normal guarded route: permission level, rate limit and audit still apply.
  - Isolated. The script runs in a separate Python process with an empty environment (no keys), a temporary
    working directory, CPU, memory, file-size and process limits, and an audit hook that refuses files, sockets,
    subprocesses and any module outside a small allowlist. The parent never runs the script's code.
  - Bounded. A cap on calls per run, on each call's result size, on wall-clock time, on runs at once, and on the
    answer's size (a long answer is stored whole and shown as a view with a reference).
  - Never worse than before. Switched off, busy or broken: one line telling the model to call the tools itself.
"""
from __future__ import annotations

import asyncio
import json
import os
import shutil
import sys
import tempfile
import time

import winproc

TOOL = "javis_code"
ANSWER_CHARS = 7000
OUTPUT_CHARS_MAX = 400_000          # what the child may print in total
CALL_RESULT_MAX = 3_000_000         # one tool result handed to the script
RPC_LINE_MAX = 8_000_000            # one protocol line from the child
CODE_CHARS_MAX = 20_000
MAX_CALLS_DEFAULT = 40
WALL_S_DEFAULT = 120
CPU_S_DEFAULT = 30
MEM_MB_DEFAULT = 1024
MAX_PARALLEL = 2

DESCRIPTION = (
    "Run a short Python script that READS from connected sources and returns only what it prints. Inside, "
    "`call(tool, args)` calls a read-only connection tool by its exact name (from the tool search) and returns the "
    "parsed JSON (or text); a failed call raises ToolError. Use it to CHAIN reads: page through a period, look up "
    "details for each item, join two sources, then compute and print just the answer, so the raw data never enters "
    "this conversation. For one call or SQL over one stored result, javis_query is simpler. Writes, sends and "
    "outside actions are refused. json, math, re, datetime, statistics and collections are ready; also "
    "importable: itertools, functools, decimal, fractions, heapq, bisect, operator, string, textwrap, unicodedata. "
    "No files, no network, no subprocess. Limits: 40 calls, 120 s. print() only what the owner's answer needs.")

SCHEMA = {
    "type": "object",
    "properties": {
        "code": {"type": "string",
                 "description": "Python 3 source. Use call(tool, args) for data and print() for the result."},
    },
    "required": ["code"],
}

ALLOWED_MODULES = (
    "json", "math", "cmath", "statistics", "datetime", "time", "calendar", "zoneinfo", "re", "collections",
    "itertools", "functools", "decimal", "fractions", "heapq", "bisect", "operator", "string", "textwrap",
    "unicodedata", "random", "copy", "pprint", "dataclasses", "typing", "enum", "numbers", "base64", "hashlib",
    "urllib.parse",
)

# The child. Runs with `python -I -S -c`, reads one JSON line (code + limits) from stdin, then speaks JSON lines:
# {"op": "call", "tool", "args"} out, {"ok", "text"} back, and finally {"op": "done", "output", "error"}.
CHILD = r'''
import sys, json, io, traceback, linecache, builtins
_boot = json.loads(sys.stdin.buffer.readline())
try:
    import resource         # absent on Windows: the audit hook below still applies there
    def _lim(kind, value):
        try:
            resource.setrlimit(kind, (value, value))
        except (ValueError, OSError):
            pass
    _lim(resource.RLIMIT_CPU, _boot["cpu_s"])
    _lim(resource.RLIMIT_AS, _boot["mem_mb"] * 1024 * 1024)
    _lim(resource.RLIMIT_FSIZE, 0)
    _lim(resource.RLIMIT_NPROC, 0)
    _lim(resource.RLIMIT_CORE, 0)
except ImportError:
    pass
_ALLOWED = tuple(_boot["modules"])
for _m in _ALLOWED:
    try:
        __import__(_m)
    except Exception:
        pass
try:
    import zoneinfo
    for _z in ("UTC", "Asia/Ho_Chi_Minh", "Asia/Bangkok", "Asia/Singapore"):
        zoneinfo.ZoneInfo(_z)       # cached now: reading tz files is refused once the audit hook is on
except Exception:
    pass
_rpc_in, _rpc_out = sys.stdin.buffer, sys.stdout.buffer
_out = io.StringIO()
_cap = _boot["output_max"]
_BLOCK = ("open", "os.", "socket.", "subprocess.", "shutil.", "ctypes.", "_posixsubprocess", "pty.", "fcntl.",
          "mmap.", "sqlite3.", "urllib.Request", "http.", "ftplib.", "smtplib.", "glob.", "webbrowser.",
          "tempfile.", "resource.", "signal.", "builtins.input", "cpython.run_", "sys.monitoring", "pdb")
def _audit(event, args):
    if event == "import":
        name = str(args[0] or "")
        if not any(name == m or name.startswith(m + ".") for m in _ALLOWED):
            raise ImportError("module '%s' is not available in javis_code" % name)
        return
    if event.startswith(_BLOCK):
        raise PermissionError("javis_code is read-only and isolated: '%s' is not allowed" % event)
sys.addaudithook(_audit)
_real_import = builtins.__import__
def _gated_import(name, globals=None, locals=None, fromlist=(), level=0):
    if level or not any(name == m or name.startswith(m + ".") for m in _ALLOWED):
        raise ImportError("module '%s' is not available in javis_code" % name)
    return _real_import(name, globals, locals, fromlist, level)
class ToolError(Exception):
    pass
_calls = [0]
def call(tool, args=None, **kwargs):
    """Call a read-only connection tool. Returns parsed JSON, or the text when it is not JSON."""
    if args is None:
        args = {}
    if not isinstance(args, dict):
        raise ToolError("args must be a dict")
    args = dict(args, **kwargs)
    _calls[0] += 1
    if _calls[0] > _boot["max_calls"]:
        raise ToolError("call limit reached (%d calls per run)" % _boot["max_calls"])
    _rpc_out.write((json.dumps({"op": "call", "tool": str(tool), "args": args}, default=str) + "\n").encode())
    _rpc_out.flush()
    line = _rpc_in.readline()
    if not line:
        raise ToolError("the host stopped answering")
    reply = json.loads(line)
    if not reply.get("ok"):
        raise ToolError(reply.get("text") or "call failed")
    text = reply.get("text") or ""
    try:
        return json.loads(text)
    except ValueError:
        return text
def _print(*a, **k):
    k.pop("file", None)
    k.pop("flush", None)
    if _out.tell() < _cap:
        builtins.print(*a, file=_out, **k)
_safe = {k: getattr(builtins, k) for k in dir(builtins)
         if k not in ("open", "input", "breakpoint", "exit", "quit", "help", "compile", "exec", "eval",
                      "__import__", "__loader__", "__spec__")}
_safe["__import__"] = _gated_import
_safe["print"] = _print
_src = _boot["code"]
linecache.cache["<javis_code>"] = (len(_src), None, _src.splitlines(True), "<javis_code>")
_env = {"__builtins__": _safe, "__name__": "__javis_code__", "call": call, "ToolError": ToolError}
for _m in ("json", "math", "re", "datetime", "statistics", "collections"):
    if _m in sys.modules:
        _env[_m] = sys.modules[_m]          # ready without an import: models often forget one
_err = ""
try:
    exec(builtins.compile(_src, "<javis_code>", "exec"), _env)
except BaseException as _e:
    _tb = traceback.format_exception(type(_e), _e, _e.__traceback__)
    _err = "".join(t for t in _tb if "<javis_code>" in t or not t.startswith("  File ")).strip()
    _err = _err.replace("Traceback (most recent call last):\n", "")
_text = _out.getvalue()
if len(_text) > _cap:
    _text = _text[:_cap] + "\n[output cut at the limit]"
_rpc_out.write((json.dumps({"op": "done", "output": _text, "error": _err[-4000:], "calls": _calls[0]}) + "\n").encode())
_rpc_out.flush()
'''

_active = 0


def enabled() -> bool:
    """`mcp.code_mode`: true (default) | false. JAVIS_CODE_MODE=0|1 wins."""
    v = (os.getenv("JAVIS_CODE_MODE") or "").strip().lower()
    if v in ("0", "false", "off", "no"):
        return False
    if v in ("1", "true", "on", "yes"):
        return True
    try:
        import config
        return (config.read_settings().get("mcp") or {}).get("code_mode", True) is not False
    except Exception:  # noqa: BLE001
        return True


def _env_int(name: str, default: int, low: int, high: int) -> int:
    try:
        return max(low, min(high, int(os.getenv(name, "") or default)))
    except (TypeError, ValueError):
        return default


def _child_env() -> dict:
    """No keys and no tokens: only what a Python process needs to start."""
    env = {"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8", "PYTHONIOENCODING": "utf-8"}
    if os.name == "nt" and os.environ.get("SYSTEMROOT"):
        env["SYSTEMROOT"] = os.environ["SYSTEMROOT"]
    return env


def _err(msg: str) -> str:
    return "ERROR: " + msg


def _fallback(why: str) -> str:
    return _err(f"{TOOL} did not run ({why}). Call the tools yourself; nothing was read or changed.")


def _bound_answer(text: str, scope: str) -> str:
    """A long answer is kept whole in the result store and shown as a view with a reference."""
    if len(text) <= ANSWER_CHARS:
        return text
    try:
        import tool_result_shaper
        import tool_result_store
        ref = tool_result_store.put(text, scope=scope, tool=TOOL, kind="text")
        if ref:
            return tool_result_shaper.build_text_preview(text, ref, ANSWER_CHARS)
    except Exception:  # noqa: BLE001
        pass
    return text[:ANSWER_CHARS] + "\n[answer cut here: it was longer than the limit]"


async def _dispatch(route: dict, name: str, args) -> tuple:
    """One `call()` from the script: (ok, text). Only declared reads, through the tool's guarded route."""
    import mcp_client
    import tool_result_shaper
    import tool_result_tools
    name = str(name or "").strip()
    args = args if isinstance(args, dict) else {}
    ent = route.get(name)
    if not ent or name == TOOL:
        return False, f"no tool named '{name}'. Use the exact name from the tool search."
    if not tool_result_tools.is_plain_read(ent, args):
        return False, (f"'{name}' is not a read {TOOL} may call: only connection tools that are clearly reads. "
                       "Call it directly outside the script if it is really needed.")
    with tool_result_shaper.raw_results():
        text = str(await mcp_client.call_route({name: ent}, name, args))
    if text.lstrip().startswith("ERROR:"):
        return False, text.strip()[:2000]
    if len(text) > CALL_RESULT_MAX:
        return False, (f"'{name}' returned {len(text)} characters, more than a script may take in one call "
                       f"({CALL_RESULT_MAX}). Ask for a shorter period, fewer fields or one page at a time.")
    return True, text


async def run(route: dict, code: str, scope: str = "") -> str:
    """One script run, start to finish. Always returns text for the calling model, never raises."""
    global _active
    code = str(code or "")
    if not code.strip():
        return _err("`code` is empty. Write Python that uses call(tool, args) and print().")
    if len(code) > CODE_CHARS_MAX:
        return _err(f"`code` is longer than {CODE_CHARS_MAX} characters; keep the script short.")
    if not enabled():
        return _fallback("it is switched off on this install")
    if _active >= MAX_PARALLEL:
        return _fallback(f"{_active} scripts are already running")
    max_calls = _env_int("JAVIS_CODE_MODE_MAX_CALLS", MAX_CALLS_DEFAULT, 1, 500)
    wall = _env_int("JAVIS_CODE_MODE_MAX_WALL_S", WALL_S_DEFAULT, 5, 1800)
    boot = {"code": code, "max_calls": max_calls, "modules": list(ALLOWED_MODULES), "output_max": OUTPUT_CHARS_MAX,
            "cpu_s": _env_int("JAVIS_CODE_MODE_CPU_S", CPU_S_DEFAULT, 1, 600),
            "mem_mb": _env_int("JAVIS_CODE_MODE_MEM_MB", MEM_MB_DEFAULT, 128, 8192)}
    workdir = await asyncio.to_thread(tempfile.mkdtemp, prefix="javis-code-")
    started = time.time()
    used: dict = {}
    done = None
    proc = None
    _active += 1
    try:
        proc = await asyncio.create_subprocess_exec(
            sys.executable, "-I", "-S", "-c", CHILD,
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            cwd=workdir, env=_child_env(),
            limit=RPC_LINE_MAX, **winproc.kwargs_no_window())

        async def _talk():
            nonlocal done
            proc.stdin.write((json.dumps(boot) + "\n").encode())
            await proc.stdin.drain()
            while True:
                line = await proc.stdout.readline()
                if not line:
                    return
                try:
                    msg = json.loads(line)
                except ValueError:
                    continue
                if msg.get("op") == "done":
                    done = msg
                    return
                if msg.get("op") == "call":
                    name = str(msg.get("tool") or "")
                    ok, text = await _dispatch(route, name, msg.get("args"))
                    used[name] = used.get(name, 0) + 1
                    proc.stdin.write((json.dumps({"ok": ok, "text": text}) + "\n").encode())
                    await proc.stdin.drain()

        try:
            await asyncio.wait_for(_talk(), timeout=wall)
        except asyncio.TimeoutError:
            return _fallback(f"the script was still running after {wall} seconds")
    except Exception as e:  # noqa: BLE001 - whatever broke, the model can still call the tools itself
        return _fallback(f"{type(e).__name__}: {str(e)[:200]}")
    finally:
        _active -= 1
        if proc is not None and proc.returncode is None:
            try:
                proc.kill()
            except ProcessLookupError:
                pass
            try:
                await asyncio.wait_for(proc.wait(), timeout=5)
            except Exception:  # noqa: BLE001
                pass
        await asyncio.to_thread(shutil.rmtree, workdir, ignore_errors=True)
    if done is None:
        tail = ""
        try:
            tail = (await asyncio.wait_for(proc.stderr.read(), timeout=2)).decode(errors="replace")[-600:]
        except Exception:  # noqa: BLE001
            pass
        why = "the script process ended without an answer"
        if tail.strip():
            why += ": " + tail.strip()
        elif proc.returncode is not None and proc.returncode < 0:
            why += " (stopped by a CPU or memory limit)"
        return _fallback(why)
    calls = ", ".join(f"{n} x{c}" if c > 1 else n for n, c in used.items()) or "none"
    head = f"{TOOL} ran in {time.time() - started:.1f}s, calls: {calls}."
    output = str(done.get("output") or "")
    error = str(done.get("error") or "").strip()
    if error:
        body = "ERROR in the script:\n" + error
        if output.strip():
            body += "\n\nPrinted before the error:\n" + output
        return head + "\n\n" + await asyncio.to_thread(_bound_answer, body, scope)
    if not output.strip():
        return head + "\n\nThe script printed nothing. print() the values the answer needs."
    return head + "\n\n" + await asyncio.to_thread(_bound_answer, output, scope)


def build(route_ref: dict, scope: str) -> tuple:
    """(tool spec, route entry) for one tool list. `route_ref` is filled by the hub once every route is final."""

    async def _call(args):
        args = args if isinstance(args, dict) else {}
        return await run(route_ref, args.get("code"), str(scope or ""))

    spec = {"fn": TOOL, "server": "javis", "name": TOOL, "namespace": "javis", "description": DESCRIPTION,
            "schema": SCHEMA}
    # Not a core tool: it lives behind the tool search, and the search tool's description names it in one line
    # (mcp_hub.CODE_MODE_HINT).
    entry = {"call": _call, "source_type": "builtin", "source_id": "javis",
             "effect": "read", "required_mode": "readonly", "health": "healthy"}
    return spec, entry
