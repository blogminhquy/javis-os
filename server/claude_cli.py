"""
Hạ tầng engine CLI: factory claude_engine() (engine Claude - chạy qua claude_sdk_engine),
CodexCLI (ChatGPT subscription, spawn `codex exec` bằng Popen + thread cho tương thích mọi
event loop Windows), auth Claude Code, registry ngắt tiến trình theo tag.
Nhánh ClaudeCLI Popen cũ đã gỡ ở v0.9.37 (engine Claude giờ luôn đi qua Agent SDK -
kế hoạch + nhật ký: docs/dev/2026-07-ke-hoach-agent-sdk.md).
"""
import asyncio
import json
import os
import sys
import shutil
import subprocess
import threading
import time
import traceback
from pathlib import Path
from typing import AsyncIterator, Optional


# Registry các tiến trình Claude đang chạy - để ngắt giữa chừng.
# Map proc -> tag ("chat" | "metrics" | "workflow" | "loop" | ...) để ngắt CÓ CHỌN LỌC.
_ACTIVE_PROCS = {}
_PROC_LOCK = threading.Lock()


def _looks_like_codex_resume_error(message: str) -> bool:
    """Nhận diện lỗi rollout/thread không còn để caller bootstrap từ SQLite đúng một lần."""
    s = (message or "").lower()
    subject = any(x in s for x in ("resume", "session", "thread", "rollout"))
    failure = any(x in s for x in (
        "not found", "does not exist", "could not find", "failed to load",
        "failed to resume", "unable to resume", "invalid session", "no session",
    ))
    return subject and failure


def cancel_all(tag=None):
    """Ngắt tiến trình Claude. tag=None → tất cả; có tag → ngắt nhóm khớp.
    Khớp theo HỌ tag: 'chat' ngắt cả 'chat:abc' (tag đa phiên per-kết-nối/per-chat_id);
    'chat:abc' chỉ ngắt đúng phiên đó. Tương tự 'telegram' vs 'telegram:<chat_id>'.
    Ngắt CẢ hai engine: subprocess CLI (Popen) lẫn phiên Agent SDK đang chạy."""
    with _PROC_LOCK:
        procs = [p for p, t in _ACTIVE_PROCS.items()
                 if tag is None or t == tag or str(t).startswith(str(tag) + ":")]
    for p in procs:
        try:
            if os.name == "nt":
                # Kill cả cây tiến trình (claude spawn node con)
                subprocess.run(["taskkill", "/F", "/T", "/PID", str(p.pid)],
                               capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
            else:
                p.terminate()
        except Exception:
            pass
    n = len(procs)
    try:
        import claude_sdk_engine
        n += claude_sdk_engine.cancel_all(tag)
    except Exception:
        pass
    return n


def _kill_tree(p):
    """Giết 1 tiến trình claude/codex VÀ TOÀN BỘ cây con (node) - dùng cho watchdog idle-timeout.
    Tiến trình treo (kẹt auth / flail trên path không tồn tại) nếu không giết sẽ sống mãi, ngốn
    RAM/CPU và làm treo server một-tiến-trình. POSIX dùng killpg (cần start_new_session=True)."""
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(p.pid)],
                           capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
        else:
            import signal as _signal
            try:
                os.killpg(os.getpgid(p.pid), _signal.SIGKILL)
            except Exception:
                p.kill()
    except Exception:
        pass


def find_claude_cli() -> Optional[str]:
    """Tìm claude CLI trên máy."""
    cli = shutil.which("claude")
    if cli:
        return cli
    if os.name == "nt":
        candidates = [
            Path(os.environ.get("USERPROFILE", "")) / ".local" / "bin" / "claude.EXE",
            Path(os.environ.get("USERPROFILE", "")) / ".local" / "bin" / "claude.exe",
            Path(os.environ.get("APPDATA", "")) / "npm" / "claude.cmd",
            Path(os.environ.get("APPDATA", "")) / "npm" / "claude.exe",
        ]
        for p in candidates:
            if p.exists():
                return str(p)
    for p in ("/usr/local/bin/claude", "~/.local/bin/claude", "~/.npm-global/bin/claude"):
        path = Path(p).expanduser()
        if path.exists():
            return str(path)
    return None


# ---- Claude Code auth (đăng nhập Anthropic dùng cho engine CLI) ----
def _no_window():
    return subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0


# ---- MCP RỖNG cho fork học (cô lập tuyệt đối) ----
# `--strict-mcp-config` của Claude Code CHỈ có hiệu lực khi đi kèm 1 file --mcp-config.
# Fork học phải chạy với 0 MCP → ta ghi 1 file {"mcpServers":{}} rồi truyền strict.
# Gọi _empty_mcp_file() TRẢ path đã ĐẢM BẢO tồn tại + non-empty (fail-closed: caller phải
# assert path này trước khi spawn; None/rỗng ⇒ TỪ CHỐI spawn, không để fork nuốt MCP máy).
import tempfile as _tempfile

def _empty_mcp_file() -> Optional[str]:
    try:
        p = Path(_tempfile.gettempdir()) / "javis-empty-mcp.json"
        if not (p.exists() and p.stat().st_size > 0):
            p.write_text('{"mcpServers":{}}', encoding="utf-8")
        return str(p) if p.stat().st_size > 0 else None
    except Exception:
        return None


def auth_status():
    """Trạng thái đăng nhập Claude Code: {connected, email, plan, org}."""
    cli = find_claude_cli()
    if not cli:
        return {"connected": False, "error": "Claude CLI chưa cài"}
    try:
        r = subprocess.run([cli, "auth", "status", "--json"], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=25, creationflags=_no_window())
        d = json.loads((r.stdout or "").strip() or "{}")
        return {"connected": bool(d.get("loggedIn")), "email": d.get("email", ""),
                "plan": d.get("subscriptionType", "") or d.get("authMethod", ""), "org": d.get("orgName", "")}
    except Exception as e:
        return {"connected": False, "error": f"{type(e).__name__}: {e}"}


def auth_logout():
    cli = find_claude_cli()
    if not cli:
        return {"ok": False, "error": "Claude CLI chưa cài"}
    try:
        subprocess.run([cli, "auth", "logout"], capture_output=True, text=True, timeout=25, creationflags=_no_window())
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


def auth_login():
    """Mở luồng đăng nhập (browser) ở tiến trình nền - tự hoàn tất qua localhost callback rồi thoát.
    Chạy được trên máy có trình duyệt (local). Frontend poll auth_status tới khi connected."""
    cli = find_claude_cli()
    if not cli:
        return {"ok": False, "error": "Claude CLI chưa cài"}
    try:
        subprocess.Popen([cli, "auth", "login", "--claudeai"],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=_no_window())
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


# ---- Đăng nhập Claude NGAY TRÊN UI (chạy được cả VPS headless) ----
# Chạy `claude auth login --claudeai` với pipe: đọc LINK nó in cho user mở, nhận CODE user dán rồi
# ghi vào stdin. Trạng thái giữ ở _LOGIN (1 phiên 1 lúc là đủ). KHÔNG mở browser trên server.
import re as _re_login
_LOGIN = {"proc": None, "url": "", "done": False, "error": "", "lines": []}
_LOGIN_URL_RE = _re_login.compile(r"https?://\S+")


def auth_login_ui_start():
    cli = find_claude_cli()
    if not cli:
        return {"ok": False, "error": "Claude CLI chưa cài"}
    try:
        if _LOGIN["proc"] and _LOGIN["proc"].poll() is None:
            _kill_tree(_LOGIN["proc"])
    except Exception:
        pass
    _LOGIN.update({"proc": None, "url": "", "done": False, "error": "", "lines": []})
    try:
        proc = subprocess.Popen(
            [cli, "auth", "login", "--claudeai"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace", bufsize=1,
            creationflags=_no_window(), start_new_session=(os.name != "nt"),
        )
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}
    _LOGIN["proc"] = proc

    def _reader():
        try:
            for line in proc.stdout:
                line = line.rstrip()
                if not line:
                    continue
                _LOGIN["lines"].append(line)
                if not _LOGIN["url"]:
                    m = _LOGIN_URL_RE.search(line)
                    if m:
                        _LOGIN["url"] = m.group(0)
                low = line.lower()
                if "success" in low or "logged in" in low:
                    _LOGIN["done"] = True
                elif "error" in low or "failed" in low or "invalid" in low:
                    _LOGIN["error"] = line
        except Exception as e:
            _LOGIN["error"] = f"{type(e).__name__}: {e}"
        finally:
            try:
                if proc.poll() is not None and proc.returncode == 0:
                    _LOGIN["done"] = True
            except Exception:
                pass
    threading.Thread(target=_reader, daemon=True).start()
    for _ in range(60):   # đợi tối đa ~12s để có URL / xong sớm / lỗi
        if _LOGIN["url"] or _LOGIN["done"] or _LOGIN["error"]:
            break
        time.sleep(0.2)
    if not (_LOGIN["url"] or _LOGIN["done"] or _LOGIN["error"]):
        return {"ok": False, "error": "Không lấy được link đăng nhập (claude CLI không in URL)."}
    return {"ok": True, "url": _LOGIN["url"], "done": _LOGIN["done"], "error": _LOGIN["error"]}


def auth_login_ui_code(code):
    proc = _LOGIN.get("proc")
    if not proc:
        return {"ok": False, "error": "Chưa bắt đầu đăng nhập (bấm Đăng nhập trước)."}
    try:
        proc.stdin.write((code or "").strip() + "\n")
        proc.stdin.flush()
    except Exception as e:
        return {"ok": False, "error": f"Không gửi được code: {e}"}
    for _ in range(120):   # ~24s
        if _LOGIN["done"]:
            return {"ok": True}
        if _LOGIN["error"]:
            return {"ok": False, "error": _LOGIN["error"]}
        if proc.poll() is not None:
            return {"ok": proc.returncode == 0,
                    "error": "" if proc.returncode == 0 else "Đăng nhập thất bại - thử lại."}
        time.sleep(0.2)
    return {"ok": _LOGIN["done"], "error": _LOGIN.get("error", "")}


# ---- MCP native (cho server OAuth - Claude Code tự lo OAuth; scope user = dùng chung mọi cwd) ----
def mcp_native_add(name, url, transport="http", header=None, client_id=None):
    cli = find_claude_cli()
    if not cli:
        return {"ok": False, "error": "Claude CLI chưa cài"}
    args = [cli, "mcp", "add", "--scope", "user", "--transport", transport]
    if header:
        args += ["--header", header]
    if client_id:
        args += ["--client-id", client_id]
    args += [name, url]
    try:
        r = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace",
                           timeout=30, creationflags=_no_window())
        ok = r.returncode == 0
        return {"ok": ok, "out": (r.stdout or r.stderr or "").strip()[:300]}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


def mcp_native_remove(name):
    cli = find_claude_cli()
    if not cli:
        return {"ok": False, "error": "Claude CLI chưa cài"}
    try:
        subprocess.run([cli, "mcp", "remove", "--scope", "user", name], capture_output=True,
                       text=True, timeout=30, creationflags=_no_window())
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


def mcp_native_status(name):
    """Trạng thái server OAuth native: {authenticated, status} qua `claude mcp get` (parse 'Needs authentication')."""
    cli = find_claude_cli()
    if not cli:
        return {"authenticated": False, "status": "no_cli"}
    try:
        r = subprocess.run([cli, "mcp", "get", name], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=30, creationflags=_no_window())
        out = ((r.stdout or "") + (r.stderr or "")).lower()
        if "needs authentication" in out:
            return {"authenticated": False, "status": "needs_auth"}
        if r.returncode != 0 or "not found" in out or "no mcp server" in out:
            return {"authenticated": False, "status": "not_found"}
        return {"authenticated": True, "status": "ok"}
    except Exception as e:
        return {"authenticated": False, "status": "error", "error": f"{type(e).__name__}: {e}"}


def mcp_native_list():
    """Liệt kê MCP sẵn trong Claude Code (đồng bộ từ claude.ai) - chỉ để hiển thị.
    Parse output `<tên>: <url> - <trạng thái>` (health check nên hơi lâu)."""
    cli = find_claude_cli()
    if not cli:
        return []
    try:
        r = subprocess.run([cli, "mcp", "list"], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=60, creationflags=_no_window())
        out = r.stdout or ""
    except Exception:
        return []
    servers = []
    for line in out.splitlines():
        line = line.strip()
        if " - " not in line:
            continue
        pos = line.find("http://")
        if pos < 0:
            pos = line.find("https://")
        if pos < 0:
            continue
        name = line[:pos].rstrip().rstrip(":").strip()
        rest = line[pos:]
        dash = rest.rfind(" - ")
        if dash < 0:
            continue
        url = rest[:dash].strip()
        status = rest[dash + 3:].strip()
        connected = ("connected" in status.lower()) or ("✔" in status) or ("✓" in status)
        servers.append({"name": name, "url": url, "status": status, "connected": connected})
    return servers


def mcp_open_auth_terminal():
    """Mở 1 cửa sổ terminal chạy `claude` để user gõ /mcp xác thực OAuth MCP (chỉ máy local có màn hình)."""
    cli = find_claude_cli()
    if not cli:
        return {"ok": False, "error": "Claude CLI chưa cài"}
    try:
        if os.name == "nt":
            subprocess.Popen('start "Javis - Xac thuc MCP (go /mcp)" cmd /k claude', shell=True)
        else:
            for term in ("x-terminal-emulator", "gnome-terminal", "konsole", "xterm"):
                if shutil.which(term):
                    subprocess.Popen([term, "-e", "claude"])
                    break
            else:
                return {"ok": False, "error": "Không tìm thấy terminal"}
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


_engine_env_warned = False


def claude_engine(system_prompt=None, cwd=None, tag="chat", allowed_tools=None, model=None):
    """FACTORY engine Claude - mọi call site tạo engine qua đây. Từ v0.9.37 engine Claude
    CHỈ chạy qua claude-agent-sdk (claude_sdk_engine.ClaudeSDK); nhánh Popen ClaudeCLI cũ
    đã gỡ sau khi bake ổn (nhật ký ở docs/dev/2026-07-ke-hoach-agent-sdk.md mục 8).
    SDK chưa cài thì ClaudeSDK tự báo lỗi rõ trong .query() (hướng dẫn pip install).
    Env JAVIS_CLAUDE_ENGINE=cli|sdk-loops chỉ còn giá trị lịch sử - bị bỏ qua kèm log 1 lần."""
    global _engine_env_warned
    mode = os.getenv("JAVIS_CLAUDE_ENGINE", "sdk").strip().lower()
    if mode in ("cli", "sdk-loops") and not _engine_env_warned:
        _engine_env_warned = True
        print(f"[claude engine] JAVIS_CLAUDE_ENGINE={mode} đã gỡ từ v0.9.37 - engine Claude "
              "luôn chạy Agent SDK. Gặp lỗi hãy báo issue kèm log.", file=sys.stderr)
    from claude_sdk_engine import ClaudeSDK
    return ClaudeSDK(system_prompt=system_prompt, cwd=cwd, tag=tag,
                     allowed_tools=allowed_tools, model=model)


# ============================================================
# Codex CLI - chạy `codex exec --json` cho provider ChatGPT OAuth (gói subscription).
# Giống cách Hermes spawn codex (app-server); ta dùng `exec` gọn hơn. codex tự lo
# subscription auth (~/.codex/auth.json) + MCP (~/.codex/config.toml) + tool NATIVE
# → ChatGPT subscription DÙNG ĐƯỢC MCP (điều mà raw HTTP endpoint không làm được).
# ============================================================
def _home_dir() -> Path:
    """Thư mục home đáng tin trên MỌI cách khởi động server.

    Không dựa mỗi USERPROFILE: khi server được bật lại bởi tự-cập-nhật, dịch vụ Windows
    hay tác vụ nền, biến này có thể trống - lúc đó home thành Path("") nên mọi đường dẫn
    ~/.codex/... hoá ra tương đối và không tồn tại, khiến Javis báo nhầm "chưa cài Codex CLI"
    dù binary vẫn nằm đó. Thử lần lượt các nguồn rồi mới chịu thua.
    """
    cands = [os.environ.get("USERPROFILE"), os.environ.get("HOME")]
    drive, path = os.environ.get("HOMEDRIVE", ""), os.environ.get("HOMEPATH", "")
    if drive and path:
        cands.append(drive + path)
    for c in cands:
        try:
            if c and Path(c).exists():
                return Path(c)
        except Exception:
            pass
    try:
        h = Path.home()          # dự phòng cuối: pathlib tự suy ra (pwd trên POSIX)
        if h.exists():
            return h
    except Exception:
        pass
    return Path("")


def find_codex_cli() -> Optional[str]:
    envp = os.environ.get("JAVIS_CODEX_BIN")     # cửa thoát: chỉ thẳng chỗ cài lạ
    if envp:
        try:
            if Path(envp).exists():
                return envp
        except Exception:
            pass
    home = _home_dir()
    cands = [
        home / ".codex" / ".sandbox-bin" / "codex.exe",
        home / ".codex" / "plugins" / ".plugin-appserver" / "codex.exe",
        Path(os.environ.get("APPDATA", "")) / "npm" / "codex.cmd",
        Path(os.environ.get("APPDATA", "")) / "npm" / "codex.exe",
        home / ".codex" / ".sandbox-bin" / "codex",
    ]
    # Windows Store có thể đặt app-execution alias ``codex.exe`` lên PATH nhưng
    # service/tiến trình nền không được quyền chạy alias đó (WinError 5). Bản
    # executable Codex Desktop xuất trong ~/.codex chạy được thật, nên ưu tiên
    # nó trên Windows. POSIX vẫn tôn trọng PATH trước như thông lệ.
    cli = shutil.which("codex")
    if cli and (os.name != "nt" or "windowsapps" not in cli.lower()):
        return cli
    for p in cands:
        try:
            if p.exists():
                return str(p)
        except Exception:
            pass
    if cli:
        return cli
    for p in ("/usr/local/bin/codex", "~/.local/bin/codex"):
        pp = Path(p).expanduser()
        if pp.exists():
            return str(pp)
    return None


# ---- MCP NATIVE của Codex (kho gốc ~/.codex/config.toml, quản bằng `codex mcp ...`) ----
# Đối xứng với bộ mcp_native_* của Claude ở trên: Codex cũng có kho MCP gốc riêng (user tự
# `codex mcp add`, hoặc app khác ghi vào config.toml). Javis chạy `codex exec -p javis` mà
# profile chỉ PHỦ THÊM lên config gốc nên kho này vẫn được engine ChatGPT nạp - các hàm dưới
# cho Javis liệt kê/thêm/gỡ/kiểm tra nó, và mở `codex mcp login <tên>` cho server OAuth.
def _codex_run(sub_args, timeout=30):
    """Chạy `codex <sub_args...>` trả CompletedProcess; None nếu chưa cài Codex CLI."""
    cli = find_codex_cli()
    if not cli:
        return None
    return subprocess.run([cli] + list(sub_args), capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=timeout,
                          creationflags=_no_window())


def codex_mcp_parse_list(out):
    """Parse output `codex mcp list --json` → list chuẩn hoá [{name, url, command, transport,
    status, connected}]. PURE (test được không cần codex). Format --json từng đổi giữa các bản
    Codex nên chấp nhận nhiều hình dạng: list phẳng, bọc {"servers": [...]}, hay map tên→cấu
    hình; parse hụt trả [] chứ không nổ."""
    out = (out or "").strip()
    if not out:
        return []
    try:
        data = json.loads(out)
    except json.JSONDecodeError:
        return []
    if isinstance(data, dict):
        inner = data.get("servers") or data.get("mcp_servers") or data
        if isinstance(inner, list):
            data = inner
        elif isinstance(inner, dict):
            data = [dict(v, name=v.get("name") or k) if isinstance(v, dict) else {"name": str(k)}
                    for k, v in inner.items()]
        else:
            return []
    if not isinstance(data, list):
        return []
    servers = []
    for it in data:
        if not isinstance(it, dict):
            continue
        name = str(it.get("name") or "").strip()
        if not name:
            continue
        tr = it.get("transport") if isinstance(it.get("transport"), dict) else {}
        url = str(it.get("url") or tr.get("url") or "")
        cmd = it.get("command") or tr.get("command") or ""
        if not isinstance(cmd, str):
            cmd = " ".join(str(x) for x in cmd)
        args = it.get("args") or tr.get("args") or []
        if cmd and args:
            cmd = (cmd + " " + " ".join(str(a) for a in args)).strip()
        ttype = str((it.get("transport") if isinstance(it.get("transport"), str) else tr.get("type"))
                    or ("http" if url else ("stdio" if cmd else "")))
        enabled = it.get("enabled")
        auth = str(it.get("auth_status") or it.get("auth") or "").lower()
        needs_login = auth in ("unauthenticated", "needs_login", "not_logged_in", "logged_out")
        status = ("tắt" if enabled is False
                  else "cần đăng nhập (codex mcp login)" if needs_login else "đã khai báo")
        servers.append({"name": name, "url": url, "command": cmd, "transport": ttype,
                        "status": status, "connected": enabled is not False and not needs_login})
    return servers


def codex_mcp_parse_list_text(out):
    """Fallback cho bản codex cũ không có `mcp list --json`: parse bảng text, lấy cột tên.
    PURE. Bỏ dòng header/kẻ bảng/'No MCP servers configured'."""
    servers = []
    for line in (out or "").splitlines():
        line = line.strip().strip("│|").strip()
        if not line or "no mcp servers" in line.lower():
            continue
        if not set(line) - set("-─┼┤├┌┐└┘│| "):   # dòng kẻ bảng
            continue
        first = line.split()[0]
        if first.lower() in ("name", "server"):    # dòng header bảng
            continue
        servers.append({"name": first, "url": "", "command": "", "transport": "",
                        "status": "đã khai báo", "connected": True})
    return servers


def codex_mcp_native_list():
    """Liệt kê MCP gốc của Codex (~/.codex/config.toml) - chỉ hiển thị, như mcp_native_list
    bên Claude. Ưu tiên `codex mcp list --json`; bản cũ fallback parse bảng text."""
    try:
        r = _codex_run(["mcp", "list", "--json"], timeout=30)
    except Exception:
        return []
    if r is None:
        return []
    if r.returncode == 0:
        servers = codex_mcp_parse_list(r.stdout)
        if servers:
            return servers
    try:
        r2 = _codex_run(["mcp", "list"], timeout=30)
    except Exception:
        return []
    if r2 is None or r2.returncode != 0:
        return []
    return codex_mcp_parse_list_text(r2.stdout)


def _codex_mcp_add_args(name, url=None, command=None, bearer_env=None):
    """Dựng argv sau `codex` cho `mcp add` (PURE để test). url → server HTTP (bearer_env =
    TÊN biến env chứa token, không phải token); command (str hoặc list) → server stdio sau '--'."""
    args = ["mcp", "add", name]
    if url:
        args += ["--url", url]
        if bearer_env:
            args += ["--bearer-token-env-var", bearer_env]
    elif command:
        cmd = command if isinstance(command, list) else str(command).split()
        args += ["--"] + [str(c) for c in cmd]
    return args


def codex_mcp_native_add(name, url=None, command=None, bearer_env=None):
    """Đăng ký 1 server vào kho MCP gốc của Codex (`codex mcp add`). Server OAuth: thêm bằng
    url rồi user chạy `codex mcp login <tên>` MỘT lần (như claude → /mcp bên Claude)."""
    if not find_codex_cli():
        return {"ok": False, "error": "Codex CLI chưa cài"}
    if not (url or command):
        return {"ok": False, "error": "Thiếu url hoặc command"}
    try:
        r = _codex_run(_codex_mcp_add_args(name, url, command, bearer_env), timeout=30)
        ok = r is not None and r.returncode == 0
        return {"ok": ok, "out": ((r.stdout or "") + (r.stderr or "")).strip()[:300] if r else ""}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


def codex_mcp_native_remove(name):
    if not find_codex_cli():
        return {"ok": False, "error": "Codex CLI chưa cài"}
    try:
        _codex_run(["mcp", "remove", name], timeout=30)
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


def codex_mcp_native_status(name):
    """Trạng thái 1 server trong kho gốc Codex qua `codex mcp get` (parse chuỗi cần đăng nhập) -
    đối xứng mcp_native_status bên Claude."""
    if not find_codex_cli():
        return {"authenticated": False, "status": "no_cli"}
    try:
        r = _codex_run(["mcp", "get", name], timeout=30)
        out = (((r.stdout or "") + (r.stderr or "")) if r else "").lower()
        if r is None or r.returncode != 0 or "not found" in out or "no mcp server" in out:
            return {"authenticated": False, "status": "not_found"}
        if ("not logged in" in out or "needs login" in out or "unauthenticated" in out
                or "login required" in out):
            return {"authenticated": False, "status": "needs_auth"}
        return {"authenticated": True, "status": "ok"}
    except Exception as e:
        return {"authenticated": False, "status": "error", "error": f"{type(e).__name__}: {e}"}


def codex_mcp_open_login_terminal(name):
    """Mở 1 cửa sổ terminal chạy `codex mcp login <tên>` để user xác thực OAuth cho MCP gốc
    của Codex (chỉ máy local có màn hình - như mcp_open_auth_terminal bên Claude)."""
    cli = find_codex_cli()
    if not cli:
        return {"ok": False, "error": "Codex CLI chưa cài"}
    # Tên đi vào chuỗi shell trên Windows → chỉ nhận chữ/số/_/- để khỏi tiêm lệnh.
    safe = "".join(ch for ch in str(name or "") if ch.isalnum() or ch in "_-")
    if not safe or safe != str(name):
        return {"ok": False, "error": "Tên server không hợp lệ"}
    try:
        if os.name == "nt":
            subprocess.Popen(f'start "Javis - Dang nhap MCP Codex" cmd /k codex mcp login {safe}',
                             shell=True)
        else:
            for term in ("x-terminal-emulator", "gnome-terminal", "konsole", "xterm"):
                if shutil.which(term):
                    subprocess.Popen([term, "-e", cli, "mcp", "login", safe])
                    break
            else:
                return {"ok": False, "error": "Không tìm thấy terminal"}
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


class CodexCLI:
    def __init__(self, cwd: Optional[str] = None, tag: str = "chat", model: Optional[str] = None,
                 instructions: Optional[str] = None):
        self.cli_path = find_codex_cli()
        self.cwd = cwd or os.getcwd()
        self.tag = tag
        self.model = model              # gpt-5.5 / gpt-5.4 ...
        self.instructions = instructions
        self.extra_config = []          # list '-c key=value' (override config, vd thêm mcp_servers)
        self.profile = None             # tên profile codex (-p) - Javis ghi javis.config.toml để thêm MCP
        self.session_id = None          # Codex thread_id; có giá trị → `codex exec resume <id>`
        # Sandbox của Codex: None = toàn quyền (mặc định, giữ nguyên hành vi cũ của chat/workflow).
        # Việc nền đặt 'read-only' / 'workspace-write' để khớp mode suggest/auto của loop -
        # Codex KHÔNG có allowlist per-call như Claude nên đây là lớp chặn thật sự duy nhất.
        self.sandbox = None

    def is_available(self) -> bool:
        return self.cli_path is not None

    def _build_args(self) -> list[str]:
        """Dựng argv cho lượt mới/resume.

        Cờ sandbox/approval/model/profile/config là GLOBAL của Codex CLI. Một số bản CLI
        chấp nhận chúng sau ``exec``, nhưng bản trên VPS không nhận
        ``exec --ask-for-approval`` và thoát exit 2. Đặt tất cả global flag trước
        subcommand để tương thích cả bản cũ lẫn mới.
        """
        args = [self.cli_path]
        if self.sandbox:
            args += ["--sandbox", self.sandbox, "--ask-for-approval", "never"]
        else:
            args += ["--dangerously-bypass-approvals-and-sandbox"]
        if self.model:
            args += ["-m", self.model]
        if self.profile:
            args += ["-p", self.profile]
        for c in (self.extra_config or []):
            args += ["-c", c]
        args += ["exec", "--json", "--skip-git-repo-check"]
        if self.session_id:
            args += ["resume", self.session_id]
        args.append("-")
        return args

    async def query(self, prompt: str) -> AsyncIterator[dict]:
        if not self.cli_path:
            yield {"type": "error", "content": "Không tìm thấy Codex CLI (cần ChatGPT login qua codex)."}
            return
        resume_requested = bool(self.session_id)
        args = self._build_args()
        # Codex exec không nhận system-prompt riêng → gộp instructions (vai trò agent) vào đầu prompt.
        # Prompt bơm qua STDIN (positional "-") thay vì argv - né trần command line 32767 ký tự
        # của Windows (WinError 206 khi dán bài dài).
        full_prompt = (self.instructions.strip() + "\n\n" + prompt) if self.instructions else prompt
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue = asyncio.Queue()
        SENTINEL = object()

        def reader_thread():
            proc = None
            tinfo = {"timed_out": False}
            last = {"t": time.time()}
            IDLE = float(os.getenv("JAVIS_CLAUDE_IDLE_TIMEOUT", "180"))
            # Trần RIÊNG khi codex đang chạy TOOL/lệnh (im lặng lúc đó là bình thường -
            # render video, build... có thể rất lâu). Cùng logic với engine Claude SDK.
            TOOL_IDLE = float(os.getenv("JAVIS_CLAUDE_TOOL_TIMEOUT", "3600"))
            # Trần RIÊNG cho DÒNG ĐẦU TIÊN: hội thoại dài thì lượt đầu phải nạp lại ngữ cảnh
            # lớn nên lâu, im lặng lúc đó không phải treo. Giữ IDLE ngắn cho các khoảng lặng
            # SAU khi đã có chữ. Parity với engine Claude SDK.
            FIRST_IDLE = float(os.getenv("JAVIS_CLAUDE_FIRST_TIMEOUT", "600"))
            busy = {"n": 0}   # số item tool/lệnh đã started mà chưa completed
            seen = {"dong_dau": False}   # đã có dòng đầu tiên chưa (quyết định dùng trần nào)
            _TOOL_ITEMS = ("command_execution", "mcp_tool_call", "function_call",
                           "tool_call", "local_shell_call", "web_search_call")
            try:
                creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
                proc = subprocess.Popen(
                    args, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                    cwd=self.cwd, text=True, encoding="utf-8", errors="replace", bufsize=1,
                    creationflags=creationflags, start_new_session=(os.name != "nt"),
                )
                with _PROC_LOCK:
                    _ACTIVE_PROCS[proc] = self.tag

                def _feed_stdin():
                    try:
                        proc.stdin.write(full_prompt)
                        proc.stdin.close()
                    except Exception:
                        pass
                threading.Thread(target=_feed_stdin, daemon=True).start()

                def _watchdog(p):
                    while p.poll() is None:
                        if busy["n"] > 0:
                            limit = TOOL_IDLE
                        elif seen["dong_dau"]:
                            limit = IDLE
                        else:
                            limit = FIRST_IDLE
                        if time.time() - last["t"] > limit:
                            tinfo["timed_out"] = True
                            _kill_tree(p)
                            if busy["n"] > 0:
                                err = (f"Tool chạy quá {int(TOOL_IDLE)}s chưa xong - đã dừng để tránh treo "
                                       f"server. (tăng JAVIS_CLAUDE_TOOL_TIMEOUT nếu tác vụ thật sự dài hơn)")
                            elif not seen["dong_dau"]:
                                err = (f"Codex chưa trả lời gì sau {int(FIRST_IDLE)}s - đã dừng để tránh treo "
                                       f"server. Hay gặp khi hội thoại đã rất dài: lượt đầu phải nạp lại toàn "
                                       f"bộ ngữ cảnh nên lâu. Mở hội thoại mới thường hết ngay. "
                                       f"(tăng JAVIS_CLAUDE_FIRST_TIMEOUT nếu muốn chờ lâu hơn)")
                            else:
                                err = (f"Codex đang trả lời rồi im {int(IDLE)}s - đã dừng để tránh treo server. "
                                       f"(tăng JAVIS_CLAUDE_IDLE_TIMEOUT nếu tác vụ thật sự dài)")
                            asyncio.run_coroutine_threadsafe(queue.put({"__error__": err}), loop)
                            return
                        time.sleep(5)
                threading.Thread(target=_watchdog, args=(proc,), daemon=True).start()

                stderr_lines = []

                def read_stderr():
                    for line in proc.stderr:
                        line = line.rstrip()
                        if line:
                            stderr_lines.append(line)
                st = threading.Thread(target=read_stderr, daemon=True)
                st.start()
                for line in proc.stdout:
                    last["t"] = time.time()
                    seen["dong_dau"] = True   # có chữ rồi → từ đây dùng trần ngắn IDLE
                    line = line.strip()
                    if line:
                        # Theo dõi tool/lệnh đang chạy dở để watchdog nới trần đúng lúc
                        if '"item.started"' in line and any(t in line for t in _TOOL_ITEMS):
                            busy["n"] += 1
                        elif '"item.completed"' in line and any(t in line for t in _TOOL_ITEMS):
                            busy["n"] = max(0, busy["n"] - 1)
                        asyncio.run_coroutine_threadsafe(queue.put(line), loop)
                proc.wait()
                st.join(timeout=2)
                if proc.returncode not in (0, None) and stderr_lines and not tinfo["timed_out"]:
                    asyncio.run_coroutine_threadsafe(
                        queue.put({"__error__": "Codex lỗi (exit " + str(proc.returncode) + "):\n" + "\n".join(stderr_lines[-5:])}), loop)
            except Exception as e:
                traceback.print_exc()
                asyncio.run_coroutine_threadsafe(queue.put({"__error__": f"Codex subprocess: {type(e).__name__}: {e}"}), loop)
            finally:
                try:
                    if proc is not None:
                        with _PROC_LOCK:
                            _ACTIVE_PROCS.pop(proc, None)
                except Exception:
                    pass
                asyncio.run_coroutine_threadsafe(queue.put(SENTINEL), loop)

        threading.Thread(target=reader_thread, daemon=True).start()

        final_text = ""
        while True:
            item = await queue.get()
            if item is SENTINEL:
                break
            if isinstance(item, dict) and "__error__" in item:
                yield {"type": "error", "content": item["__error__"]}
                continue
            try:
                ev = json.loads(item)
            except json.JSONDecodeError:
                continue
            t = ev.get("type")
            if t == "thread.started":
                thread_id = ev.get("thread_id") or ""
                if thread_id:
                    self.session_id = thread_id
                    # Phát ngay để caller lưu trước cả khi lượt bị ngắt giữa chừng.
                    yield {"type": "session", "session_id": thread_id}
            elif t == "item.completed":
                it = ev.get("item") or {}
                itype = it.get("type")
                if itype == "agent_message":
                    txt = it.get("text") or ""
                    if txt.strip():
                        final_text += (("\n" if final_text else "") + txt)
                        yield {"type": "text", "content": txt}
                elif itype in ("mcp_tool_call", "command_execution", "function_call",
                               "tool_call", "local_shell_call", "web_search_call"):
                    name = it.get("name") or it.get("server") or it.get("command") or itype
                    # Kèm `item` THÔ. Codex không có trường file_path chuẩn hoá như Claude:
                    # đường dẫn nằm rải trong changes[]/arguments/command tuỳ loại item, và
                    # khuôn còn đổi theo bản CLI. Caller tự moi (channel_context
                    # .candidate_paths_from_tool) thay vì tầng này đoán một khuôn cố định.
                    yield {"type": "tool_call", "name": str(name)[:80], "item": it}
                elif itype:
                    # Item lạ (vd bản vá file) - KHÔNG dựng thành "đang gọi tool" để khỏi ồn,
                    # nhưng vẫn đẩy payload lên cho caller moi đường dẫn file vừa ghi.
                    yield {"type": "item", "item": it}
            elif t == "turn.completed":
                u = ev.get("usage") or {}
                yield {"type": "final", "content": final_text, "session_id": self.session_id,
                       "tokens_in": (u.get("input_tokens") or 0) + (u.get("cached_input_tokens") or 0),
                       "tokens_out": u.get("output_tokens") or 0}
            elif t in ("error", "turn.failed", "thread.error", "stream.error"):
                msg = ev.get("message") or (ev.get("error") or {}).get("message") or json.dumps(ev)[:200]
                yield {"type": "error", "content": "Codex: " + str(msg),
                       "resume_failed": resume_requested and _looks_like_codex_resume_error(str(msg))}
