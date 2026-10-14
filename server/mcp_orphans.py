"""Stdio MCP processes that outlived the Javis server which started them.

Why this exists (field report 2026-10-13, bot "Javis Vũ"): the bot stopped answering a Zalo group at
21:09. The account had TWO `javis-zalo mcp start` processes: one from 20:49, one the server started
when it came back at 21:10. Zalo pushes each message to one socket only, the bot read the new process,
and the new process received almost nothing (one sticker in two hours).

`McpStdioSession` starts every stdio server in its own process group (POSIX `start_new_session`) or
detached from any console (Windows), on purpose: killing the whole tree later needs that. The flip
side is that the children do not die with the server. `SessionPool.close_all` runs on a clean
shutdown, but a crash, a `kill -9`, the updater's taskkill or a launcher restart skips it, and the
next server opens a second session next to the survivor. For most connectors that only wastes RAM
(the 2026-08-15 VPS with 100 mcp-google-sheets processes); for an account that allows ONE live
socket it silently breaks the channel.

So every stdio process is written down here (STATE_DIR/mcp-stdio-pids.json) with the server that
owns it: its pid plus a token drawn once per server lifetime (a container restart often gives the new
server the very same pid). The first stdio start in a new lifetime reaps what an earlier lifetime
left behind, under two conditions, both required:
  - the owning server is DEAD. A live owner (a second server or a test run sharing this STATE_DIR)
    keeps its processes; reaping those would cut a working channel.
  - the pid still runs the very command that was recorded, so a pid the OS has handed to something
    else is left alone.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Dict, List

import winproc

_FILE = "mcp-stdio-pids.json"
_lock = threading.Lock()
_reaped = False
# This server lifetime. A pid alone cannot tell lifetimes apart: in Docker the server is often pid 7
# every time.
_OWNER = uuid.uuid4().hex


def _path() -> Path:
    try:
        from config import STATE_DIR
        return Path(STATE_DIR) / _FILE
    except Exception:      # noqa: BLE001 - no config (bare test): keep it next to this module
        return Path(__file__).parent / _FILE


def _load() -> Dict[str, dict]:
    try:
        data = json.loads(_path().read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:      # noqa: BLE001 - missing or broken file = nothing recorded
        return {}


def _save(data: Dict[str, dict]) -> None:
    p = _path()
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, p)
    except OSError as e:
        print(f"[mcp orphans] ghi sổ PID lỗi: {e}", file=sys.stderr)


def record(key: str, pid: int, args: List[str]) -> None:
    """Remember the stdio process now serving `key` (one per key: a newer one replaces the older)."""
    if not key or not pid:
        return
    with _lock:
        data = _load()
        data[str(key)] = {"pid": int(pid), "args": [str(a) for a in (args or [])],
                          "server_pid": os.getpid(), "owner": _OWNER, "ts": time.time()}
        _save(data)


def forget(key: str, pid: int) -> None:
    """The process for `key` was closed on purpose: drop it, unless a newer one already replaced it."""
    if not key:
        return
    with _lock:
        data = _load()
        ent = data.get(str(key))
        if ent and int(ent.get("pid") or 0) == int(pid or 0):
            data.pop(str(key), None)
            _save(data)


def _marker(args: List[str]) -> str:
    """The argument that must appear in a process's command line for it to count as ours. The last one
    is the most specific that survives every launcher layer (`npx ... mcp start` -> node ... `start`
    is too common, so take the last argument that is not a bare sub-command word)."""
    words = [a for a in (args or []) if a and not a.startswith("-")]
    for a in reversed(words):
        if len(a) >= 6:
            return a
    return " ".join(words[-2:]) if words else ""


def pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        try:
            import ctypes
            k32 = ctypes.windll.kernel32
            h = k32.OpenProcess(0x1000, False, int(pid))      # PROCESS_QUERY_LIMITED_INFORMATION
            if not h:
                return False
            code = ctypes.c_ulong()
            ok = k32.GetExitCodeProcess(h, ctypes.byref(code))
            k32.CloseHandle(h)
            return bool(ok) and code.value == 259             # STILL_ACTIVE
        except Exception:      # noqa: BLE001 - unknown: say alive, so nothing gets reaped
            return True
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    try:      # a zombie answers kill(0) but is dead: it only waits for its parent to collect it
        stat = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8", errors="replace")
        return stat.rsplit(")", 1)[1].split()[0] != "Z"
    except (OSError, IndexError):
        return True


def _cmdline_posix(pid: int) -> str:
    try:
        raw = Path(f"/proc/{pid}/cmdline").read_bytes()
        return raw.replace(b"\0", b" ").decode("utf-8", "replace")
    except OSError:
        pass
    try:      # macOS and other systems without /proc
        r = subprocess.run(["ps", "-o", "command=", "-p", str(pid)], capture_output=True,
                           text=True, timeout=5, creationflags=winproc.no_window())
        return r.stdout or ""
    except Exception:      # noqa: BLE001
        return ""


def _group_members_posix(pgid: int) -> List[int]:
    """Pids whose process group is `pgid` (the launcher may already be gone, its children not)."""
    out = []
    proc = Path("/proc")
    if proc.is_dir():
        for d in proc.iterdir():
            if not d.name.isdigit():
                continue
            try:
                stat = (d / "stat").read_text(encoding="utf-8", errors="replace")
                # pid (comm) state ppid pgrp ...; comm may contain spaces, so split after ')'
                fields = stat.rsplit(")", 1)[1].split()
                if int(fields[2]) == pgid:
                    out.append(int(d.name))
            except (OSError, IndexError, ValueError):
                continue
        return out
    try:
        r = subprocess.run(["ps", "-A", "-o", "pid=,pgid="], capture_output=True, text=True, timeout=5,
                           creationflags=winproc.no_window())
        for line in (r.stdout or "").splitlines():
            parts = line.split()
            if len(parts) == 2 and parts[1] == str(pgid):
                out.append(int(parts[0]))
    except Exception:      # noqa: BLE001
        pass
    return out


def _cmdline_windows(pid: int) -> str:
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command",
             f"(Get-CimInstance Win32_Process -Filter 'ProcessId={int(pid)}').CommandLine"],
            capture_output=True, text=True, timeout=20, creationflags=winproc.no_window())
        return (r.stdout or "").strip()
    except Exception:      # noqa: BLE001
        return ""


def still_ours(ent: dict) -> bool:
    """Is the recorded process (or, on POSIX, any member of its group) still running OUR command?"""
    pid = int(ent.get("pid") or 0)
    marker = _marker(ent.get("args") or [])
    if pid <= 0 or not marker:
        return False
    if os.name == "nt":
        return marker in _cmdline_windows(pid)
    if pid == os.getpgid(0):
        return False      # never our own server's group
    return any(marker in _cmdline_posix(m) for m in _group_members_posix(pid))


def reap_all() -> List[str]:
    """Kill stdio MCP processes left by an EARLIER server lifetime. Runs once per process; returns the
    keys whose survivor was killed. Entries this server recorded itself are never touched."""
    global _reaped
    with _lock:
        if _reaped:
            return []
        _reaped = True
        data = _load()
        old = {}
        for k, v in list(data.items()):
            v = v if isinstance(v, dict) else {}
            if v.get("owner") == _OWNER:
                continue                          # recorded by this very server
            spid = int(v.get("server_pid") or 0)
            if v.get("owner") and spid != os.getpid() and pid_alive(spid):
                continue                          # its server still runs: not an orphan
            old[k] = data.pop(k)
        _save(data)
    killed = []
    for key, ent in old.items():
        try:
            if still_ours(ent):
                winproc.kill_tree(int(ent["pid"]))
                killed.append(key)
                print(f"[mcp orphans] {key}: dọn tiến trình MCP còn sót từ lần chạy trước "
                      f"(pid {ent['pid']})", file=sys.stderr)
        except Exception as e:      # noqa: BLE001 - one bad entry must not stop the others
            print(f"[mcp orphans] {key}: {type(e).__name__}: {e}", file=sys.stderr)
    return killed


def _reset_for_tests() -> None:
    global _reaped
    _reaped = False
