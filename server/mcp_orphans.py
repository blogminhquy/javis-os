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
import re
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


def _proc_start(pid: int) -> str:
    """When `pid` started, as the kernel counts it (clock ticks since boot, /proc/<pid>/stat field 22);
    "" where /proc is missing. Two processes that share a pid never share this value."""
    try:
        stat = Path(f"/proc/{int(pid)}/stat").read_text(encoding="utf-8", errors="replace")
        return stat.rsplit(")", 1)[1].split()[19]
    except (OSError, IndexError, ValueError):
        return ""


# Start time of this server process (0.283.0). A recorded owner pid that is alive is only the same server when its
# start time matches: after a restart the old server's pid is often handed to another process (a container hands out
# small pids again), and the old reaper then read "its server still runs" and left the survivor alive. Field report
# 22/10/2026 (Javis Vũ): after an update, an old `mcp start` kept evicting the new one every few minutes.
_SERVER_START = _proc_start(os.getpid())


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
                          "server_pid": os.getpid(), "server_start": _SERVER_START, "owner": _OWNER,
                          "ts": time.time()}
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


def _markers(args: List[str]) -> List[str]:
    """Every string whose presence in a command line marks the process as ours: `_marker`, plus the package name of a
    tarball URL (`.../javis-zalo/tar.gz/...` -> "/javis-zalo/"). npx runs the package as `node .../javis-zalo/...`, so
    once its `npm exec` launcher is gone the URL is in no command line of the group (0.283.0)."""
    out = []
    m = _marker(args)
    if m:
        out.append(m)
    for a in args or []:
        mm = re.match(r"https?://codeload\.github\.com/[^/]+/([^/]+)/tar\.gz/", str(a))
        if mm and len(mm.group(1)) >= 4:
            out.append("/" + mm.group(1) + "/")
    return out


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
    marks = _markers(ent.get("args") or [])
    if pid <= 0 or not marks:
        return False
    if os.name == "nt":
        line = _cmdline_windows(pid)
        return any(m in line for m in marks)
    if pid == os.getpgid(0):
        return False      # never our own server's group
    return any(m in _cmdline_posix(p) for p in _group_members_posix(pid) for m in marks)


def owner_alive(ent: dict) -> bool:
    """The server that recorded `ent` still runs: its pid is alive AND, where both start times are known, it is the same
    process (not a newer one that got the pid again)."""
    spid = int(ent.get("server_pid") or 0)
    if spid <= 0 or spid == os.getpid() or not pid_alive(spid):
        return False
    rec = str(ent.get("server_start") or "")
    if rec:
        now = _proc_start(spid)
        if now and now != rec:
            return False
    return True


def _environ_home(pid: int) -> str:
    try:
        raw = Path(f"/proc/{int(pid)}/environ").read_bytes()
    except OSError:
        return ""
    for kv in raw.split(b"\0"):
        if kv.startswith(b"HOME="):
            return kv[5:].decode("utf-8", "replace")
    return ""


def _same_dir(a: str, b: str) -> bool:
    try:
        return os.path.realpath(a) == os.path.realpath(b)
    except (OSError, ValueError):
        return a == b


def reap_same_home(home: str, keep_pgids=()) -> List[int]:
    """Kill every `... zalo ... mcp start` process (and its group) running with HOME = `home`, except the groups in
    `keep_pgids` and our own server's. Linux only (needs /proc); returns the process groups killed.

    Zalo keeps ONE live web socket per account. A connection with an isolated HOME (catalog `isolate_home`) is that
    account, so a second `mcp start` on the same HOME, whoever started it (an earlier server lifetime the ledger
    missed, a crashed update, a copy started by hand), evicts ours: the listener backs off up to five minutes and the
    bot only hears messages in the few seconds after each re-login (field report 22/10/2026). Plain CLI commands on
    the same HOME (`msg send-image`, `friend accept`, `login`) are never touched: they do not run `mcp start`."""
    if os.name == "nt" or not home or not Path("/proc").is_dir():
        return []
    try:
        own = os.getpgid(0)
    except OSError:
        return []
    keep = {int(x) for x in keep_pgids if x}
    groups = set()
    for d in Path("/proc").iterdir():
        if not d.name.isdigit():
            continue
        pid = int(d.name)
        if pid == os.getpid():
            continue
        line = _cmdline_posix(pid)
        words = line.split()
        if "zalo" not in line.lower() or not any(words[i] == "mcp" and words[i + 1] == "start"
                                                  for i in range(len(words) - 1)):
            continue
        h = _environ_home(pid)
        if not h or not _same_dir(h, home):
            continue
        try:
            pg = os.getpgid(pid)
        except OSError:
            continue
        if pg == own or pg in keep:
            continue
        groups.add(pg)
    killed = []
    for pg in sorted(groups):
        try:
            if winproc.kill_tree(pg):
                killed.append(pg)
                print(f"[mcp orphans] killed a second Zalo `mcp start` on {home} (process group {pg})",
                      file=sys.stderr)
        except Exception as e:      # noqa: BLE001
            print(f"[mcp orphans] {home}: {type(e).__name__}: {e}", file=sys.stderr)
    return killed


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
            if v.get("owner") and owner_alive(v):
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
