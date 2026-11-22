"""`claude setup-token` run by Javis, so a long-lived Claude Code token takes one button and a pasted code (2026-11-22).

Owner's report that day: Claude Code's sign-in "reached its time limit and cannot be renewed", and every bot and
background job stopped with it. Anthropic's own answer for unattended runs is a one-year token made by
`claude setup-token`, handed to the CLI as CLAUDE_CODE_OAUTH_TOKEN (claude_auth.TOKEN). Most owners run Javis on a VPS
with no terminal at hand, so the Models card runs the command for them, the same way it already runs
`claude auth login` (claude_cli.auth_login_ui_start): it shows the sign-in link, takes the code the page shows, and
keeps the token the command prints.

Unlike `claude auth login`, `setup-token` draws a full-screen terminal UI and prints nothing without a terminal, so it
runs in a pseudo-terminal here (POSIX only). The terminal is very wide so the token is never wrapped across lines.
On Windows `supported()` is False and the card asks for the token to be pasted instead.

Kept free of imports from the app (only localefmt for sentences) so it can be tested alone with a fake `claude`.
"""
from __future__ import annotations

import os
import re
import signal
import subprocess
import sys
import threading
import time

import localefmt

# The link the command prints for the browser sign-in, and the token it prints at the end.
URL_RE = re.compile(r"https://[^\s\x07\x1b]*oauth/authorize[^\s\x07\x1b]*")
TOKEN_RE = re.compile(r"sk-ant-oat01-[A-Za-z0-9_-]{20,}")
# Terminal escapes: OSC (hyperlinks, titles) first, then CSI (colours, cursor moves) and the lone ESC ones left over.
_OSC = re.compile(r"\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)")
_CSI = re.compile(r"\x1b\[[0-9;?<>=]*[ -/]*[@-~]")
_ESC = re.compile(r"\x1b[@-_]")
# What the command prints for a code it does not take.
_BAD = ("invalid code", "invalid authorization", "oauth error", "failed to", "error:", "expired")

COLUMNS, ROWS = 500, 60
START_WAIT_S = 20
CODE_WAIT_S = 45
SESSION_MAX_S = 15 * 60

_lock = threading.Lock()
_S = {"proc": None, "fd": None, "raw": "", "url": "", "token": "", "error": "", "started": 0.0, "code_sent": False}


def supported() -> bool:
    """A pseudo-terminal exists here (Linux, macOS)."""
    if os.name != "posix":
        return False
    try:
        import pty  # noqa: F401
        return True
    except ImportError:
        return False


def plain(raw: str) -> str:
    """Terminal output with every escape removed. A hyperlink's target is dropped with its OSC, its visible text stays."""
    t = _OSC.sub("", raw or "")
    t = _CSI.sub("", t)
    return _ESC.sub("", t)


def find_url(raw: str) -> str:
    """The sign-in link: the target of a terminal hyperlink when there is one (never cut by the screen width), else
    the visible text."""
    for target in re.findall(r"\x1b\]8;[^;]*;([^\x07\x1b]*)(?:\x07|\x1b\\)", raw or ""):
        m = URL_RE.search(target)
        if m:
            return m.group(0)
    m = URL_RE.search(plain(raw))
    return m.group(0) if m else ""


_TOKEN_CHARS = re.compile(r"[A-Za-z0-9_-]+")


def find_token(raw: str, final: bool = False) -> str:
    """The token, once its line is complete.

    Output arrives in pieces, and a piece can end in the middle of the token: only lines followed by a line break count
    (`final`: the command has exited, so the last line is complete too). A screen narrower than the token wraps it, so
    a match that runs to the end of its line takes the next lines while they are nothing but token characters."""
    # A pseudo-terminal turns "\n" into "\r\n", so a program's "\r\n" arrives as "\r\r\n": one line break, not two.
    txt = re.sub(r"\r*\n", "\n", plain(raw)).replace("\r", "\n")
    lines = txt.split("\n")
    if not final:
        lines = lines[:-1]
    for i, line in enumerate(lines):
        m = TOKEN_RE.search(line)
        if not m:
            continue
        tok = m.group(0)
        if m.end() == len(line.rstrip()):
            # It may go on on the next line: take it only once a line that is not token characters (a blank line, a
            # sentence) shows where it ends, or once the command has exited.
            ended = final
            for nxt in lines[i + 1:]:
                part = nxt.strip()
                if not part or not _TOKEN_CHARS.fullmatch(part):
                    ended = True
                    break
                tok += part
            if not ended:
                return ""
        return tok
    return ""


def _tail(n: int = 2) -> str:
    """The last lines the command printed that say something, without the link or the token."""
    lines = []
    for line in plain(_S["raw"]).replace("\r", "\n").split("\n"):
        line = " ".join(line.split()).lstrip("✘✗✔✓×·•*>- ")
        if len(line) < 4 or URL_RE.search(line) or TOKEN_RE.search(line):
            continue
        if not any(ch.isalpha() for ch in line):
            continue          # spinner frames and box borders
        lines.append(line)
    out = " ".join(lines[-n:])
    # "Press Enter to retry" speaks to someone at the terminal; on the card a new link is the retry.
    cut = re.search(r"\bpress\s*enter", out, re.IGNORECASE)
    return (out[:cut.start()] if cut else out).strip(" .")[:300]


def _reader(fd: int, proc) -> None:
    while True:
        try:
            chunk = os.read(fd, 4096)
        except OSError:
            break
        if not chunk:
            break
        with _lock:
            if _S["proc"] is not proc:
                return
            _S["raw"] = (_S["raw"] + chunk.decode("utf-8", "replace"))[-200_000:]
            if not _S["url"]:
                _S["url"] = find_url(_S["raw"])
            if not _S["token"]:
                _S["token"] = find_token(_S["raw"])
            if _S["code_sent"] and not _S["token"]:
                low = plain(chunk.decode("utf-8", "replace")).lower()
                if any(b in low for b in _BAD):
                    _S["error"] = _tail() or " ".join(low.split())[:300]


def stop() -> None:
    """End the running command, if any, and forget its output (the token included)."""
    with _lock:
        proc, fd = _S["proc"], _S["fd"]
        _S.update(proc=None, fd=None, raw="", url="", token="", error="", started=0.0, code_sent=False)
    if proc is not None and proc.poll() is None:
        try:
            os.killpg(proc.pid, signal.SIGTERM)
        except Exception:  # noqa: BLE001
            try:
                proc.kill()
            except Exception:  # noqa: BLE001
                pass
    if fd is not None:
        try:
            os.close(fd)
        except OSError:
            pass


def start(cli: str, env: dict = None) -> dict:
    """Run `claude setup-token` and wait for its sign-in link. {ok, url} or {ok: False, error}."""
    if not supported():
        return {"ok": False, "unsupported": True, "error": localefmt.chu(
            "Máy này không chạy được bước lấy token tự động. Mở terminal, gõ claude setup-token, rồi dán token vào đây.",
            "This machine cannot get the token automatically. Open a terminal, run claude setup-token, then paste the "
            "token here.")}
    if not cli:
        return {"ok": False, "error": localefmt.chu("Chưa cài Claude Code trên máy chạy Javis.",
                                                    "Claude Code is not installed on the machine running Javis.")}
    stop()
    import fcntl
    import pty
    import struct
    import termios
    master, slave = pty.openpty()
    try:
        fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", ROWS, COLUMNS, 0, 0))
    except OSError:
        pass
    e = dict(os.environ)
    e.update(env or {})
    # The command makes a token for the plan it signs in to, never with one already in the environment.
    for k in ("CLAUDE_CODE_OAUTH_TOKEN", "ANTHROPIC_API_KEY"):
        e.pop(k, None)
    e.update(TERM="xterm-256color", COLUMNS=str(COLUMNS), LINES=str(ROWS))
    try:
        proc = subprocess.Popen([cli, "setup-token"], stdin=slave, stdout=slave, stderr=slave, env=e,
                                start_new_session=True, close_fds=True,
                                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
    except Exception as ex:  # noqa: BLE001
        os.close(master)
        os.close(slave)
        return {"ok": False, "error": f"{type(ex).__name__}: {ex}"}
    os.close(slave)
    with _lock:
        _S.update(proc=proc, fd=master, raw="", url="", token="", error="", started=time.time(), code_sent=False)
    threading.Thread(target=_reader, args=(master, proc), daemon=True, name="claude-setup-token").start()
    deadline = time.time() + START_WAIT_S
    while time.time() < deadline:
        with _lock:
            if _S["url"] or _S["token"]:
                return {"ok": True, "url": _S["url"], "done": bool(_S["token"])}
        if proc.poll() is not None:
            time.sleep(0.2)
            break
        time.sleep(0.2)
    with _lock:
        if _S["url"] or _S["token"]:
            return {"ok": True, "url": _S["url"], "done": bool(_S["token"])}
        tail = _tail()
    stop()
    return {"ok": False, "error": localefmt.chu("Claude Code không đưa ra link đăng nhập.",
                                                "Claude Code gave no sign-in link.") + (f" ({tail})" if tail else "")}


def send_code(code: str) -> dict:
    """Type the code the sign-in page showed and wait for the token. {ok, token} or {ok: False, error}."""
    code = "".join(str(code or "").split())
    with _lock:
        proc, fd = _S["proc"], _S["fd"]
    if proc is None or fd is None:
        return {"ok": False, "error": localefmt.chu("Chưa bắt đầu lấy token (bấm Lấy token trước).",
                                                    "Getting a token has not started (click Get token first).")}
    if not code:
        return {"ok": False, "error": localefmt.chu("Chưa có mã.", "No code yet.")}
    with _lock:
        if _S["token"]:
            return {"ok": True, "token": _S["token"]}
        _S["error"] = ""
        _S["code_sent"] = True
    try:
        os.write(fd, code.encode("utf-8"))
        time.sleep(0.15)
        os.write(fd, b"\r")
    except OSError as ex:
        return {"ok": False, "error": localefmt.chu(f"Không gửi được mã: {ex}", f"Could not send the code: {ex}")}
    deadline = time.time() + CODE_WAIT_S
    while time.time() < deadline:
        with _lock:
            if _S["token"]:
                return {"ok": True, "token": _S["token"]}
            if _S["error"]:
                return {"ok": False, "error": localefmt.chu("Claude không nhận mã này.", "Claude did not take this code.")
                        + f" ({_S['error']})"}
        if proc.poll() is not None:
            time.sleep(0.3)
            with _lock:
                if not _S["token"]:
                    _S["token"] = find_token(_S["raw"], final=True)
                if _S["token"]:
                    return {"ok": True, "token": _S["token"]}
                tail = _tail()
            return {"ok": False, "error": localefmt.chu("Lấy token không thành công, thử lại.",
                                                        "Getting the token did not work, try again.")
                    + (f" ({tail})" if tail else "")}
        time.sleep(0.2)
    return {"ok": False, "error": localefmt.chu("Claude chưa trả token sau 45 giây. Thử lại với một link mới.",
                                                "Claude gave no token after 45 seconds. Try again with a new link.")}


def poll() -> dict:
    """The token, when the command finished without a pasted code (a browser on the machine running Javis answers it
    over localhost), or whether it is still waiting."""
    with _lock:
        proc = _S["proc"]
        if proc is None:
            return {"waiting": False}
        if _S["token"]:
            return {"token": _S["token"]}
        if time.time() - _S["started"] > SESSION_MAX_S:
            ended = True
        else:
            ended = proc.poll() is not None
        if ended and not _S["token"]:
            _S["token"] = find_token(_S["raw"], final=True)
        if _S["token"]:
            return {"token": _S["token"]}
        tail = _tail() if ended else ""
    if ended:
        stop()
        return {"ended": True, "error": localefmt.chu("Phiên lấy token đã kết thúc. Bấm Lấy token để lấy link mới.",
                                                      "This token request has ended. Click Get token for a new link.")
                + (f" ({tail})" if tail else "")}
    return {"waiting": True}


def take_token() -> str:
    """The captured token, once, then the command is stopped and its output forgotten."""
    with _lock:
        tok = _S["token"]
    stop()
    return tok
