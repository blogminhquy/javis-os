"""Remote access through a Cloudflare Tunnel that Javis runs itself (0.242.0).

Owner request 2026-10-20: someone who runs Javis on a Windows or macOS computer should reach it from anywhere by
filling in a form in Settings. No VPS, no open port, no router setup and no terminal. The Caddy wizard in
routes/domain.py cannot do that: it needs a public IP with ports 80/443 open, which a home computer behind a router
almost never has. A tunnel works the other way round: `cloudflared` dials out to Cloudflare, and Cloudflare forwards
visitors back down that connection.

Three modes, picked in Settings:
- quick: `cloudflared tunnel --url` hands out a random https://<words>.trycloudflare.com address. No account and no
  domain needed, but the address changes every time the tunnel restarts.
- token: a named tunnel the owner creates in Cloudflare Zero Trust. They paste its token (or the whole install command
  Cloudflare shows, we pick the token out of it), and the public hostname they set there stays fixed.
- tailscale (0.244.0): the owner installs Tailscale and signs in themselves; Javis asks the local tailscaled to proxy
  https://<machine>.<tailnet>.ts.net to this server (`tailscale serve`). Only devices in the owner's tailnet can open
  it, so nothing is exposed to the Internet at all.

Javis downloads the right `cloudflared` build for the machine on first use (Windows x64/ARM, macOS Intel/Apple
Silicon, Linux), keeps it in <state>/bin, starts it with the server and restarts it when it drops.

Safety rails, because a tunnel puts a dashboard that can run shell commands on the Internet:
- The tunnel only starts while an admin password is set, and the supervisor kills it within seconds if the password
  goes away (reset-auth). Without that, the first stranger to open the link would get the "create account" page.
- While it is enabled, config.require_login() is True, so login cannot be switched off from the dashboard.
- The token is stored encrypted (config._SECRET_PATHS) and handed to cloudflared through the TUNNEL_TOKEN environment
  variable rather than argv, so it does not show up in the process list.
"""
from __future__ import annotations

import base64
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import threading
import time
from collections import deque
from pathlib import Path

import config as cfgmod
import localefmt
import winproc

SETTINGS_KEY = "remote_tunnel"
MODES = ("quick", "token", "tailscale")
RELEASE_BASE = "https://github.com/cloudflare/cloudflared/releases/latest/download/"

QUICK_URL_RE = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com", re.I)
# A tunnel token is base64 of a JSON object {"a": account, "t": tunnel id, "s": secret}, so it always starts "eyJ".
TOKEN_RE = re.compile(r"eyJ[A-Za-z0-9+/_=-]{40,}")
CONNECTED_MARKERS = ("Registered tunnel connection", "Connection registered")

# Seconds to wait before restarting after cloudflared exits. A run that lasted longer than STABLE_AFTER counts as
# healthy, so the next drop starts from the short end again.
BACKOFF = (3, 10, 30, 60)
STABLE_AFTER = 120
PASSWORD_CHECK_EVERY = 5


def section(cfg=None) -> dict:
    """The remote_tunnel block of settings, always a dict."""
    try:
        cfg = cfg if cfg is not None else cfgmod.read_settings()
    except Exception:
        return {}
    v = cfg.get(SETTINGS_KEY)
    return v if isinstance(v, dict) else {}


def enabled(cfg=None) -> bool:
    return bool(section(cfg).get("enabled"))


# ---------------------------------------------------------------- token

def token_info(token: str):
    """{"account", "tunnel_id"} when `token` decodes as a Cloudflare tunnel token, else None."""
    t = (token or "").strip()
    if not t:
        return None
    for dec in (base64.b64decode, base64.urlsafe_b64decode):
        try:
            d = json.loads(dec(t + "=" * (-len(t) % 4)).decode("utf-8"))
        except Exception:
            continue
        if isinstance(d, dict) and d.get("a") and d.get("t") and d.get("s"):
            return {"account": str(d["a"]), "tunnel_id": str(d["t"])}
    return None


def extract_token(text: str) -> str:
    """The tunnel token inside whatever the owner pasted.

    Cloudflare's "Install and run a connector" page shows a command, not a bare token, and people copy the whole line:
    `cloudflared.exe service install eyJ...`, `sudo cloudflared service install eyJ...`, `brew install cloudflared &&
    sudo cloudflared service install eyJ...`, `cloudflared tunnel run --token eyJ...` or a `docker run` line. Any of
    these, or the bare token, works. Returns "" when nothing in the text decodes as a token.
    """
    for m in TOKEN_RE.finditer(text or ""):
        cand = m.group(0)
        if token_info(cand):
            return cand
    return ""


# ---------------------------------------------------------------- binary

def asset_name(system: str = "", machine: str = "") -> str:
    """The cloudflared release file for this OS and CPU, or "" when Cloudflare publishes none."""
    system = (system or platform.system()).lower()
    m = (machine or platform.machine()).lower()
    if m in ("arm64", "aarch64", "armv8", "armv8l"):
        arch = "arm64"
    elif m in ("x86_64", "amd64", "x64"):
        arch = "amd64"
    elif m in ("i386", "i686", "x86"):
        arch = "386"
    elif m.startswith("arm"):
        arch = "arm"
    else:
        arch = ""
    table = {
        "windows": {"amd64": "cloudflared-windows-amd64.exe", "arm64": "cloudflared-windows-arm64.exe",
                    "386": "cloudflared-windows-386.exe"},
        "darwin": {"amd64": "cloudflared-darwin-amd64.tgz", "arm64": "cloudflared-darwin-arm64.tgz"},
        "linux": {"amd64": "cloudflared-linux-amd64", "arm64": "cloudflared-linux-arm64", "arm": "cloudflared-linux-arm"},
    }
    return table.get(system, {}).get(arch, "")


def bin_dir() -> Path:
    return Path(cfgmod.STATE_DIR) / "bin"


def local_binary() -> Path:
    return bin_dir() / ("cloudflared.exe" if os.name == "nt" else "cloudflared")


def find_binary() -> str:
    """The copy Javis downloaded first (known to work), then one the owner installed (brew, winget, apt)."""
    p = local_binary()
    if p.is_file():
        return str(p)
    return shutil.which("cloudflared") or ""


def _version_of(path: str) -> str:
    try:
        r = subprocess.run([path, "--version"], capture_output=True, text=True, timeout=20,
                           creationflags=winproc.no_window())
        out = (r.stdout or "") + (r.stderr or "")
    except Exception:
        return ""
    return out.strip().splitlines()[0] if "cloudflared" in out.lower() else ""


def install_binary() -> str:
    """Download cloudflared into <state>/bin and return its path. Raises RuntimeError with a readable reason.

    httpx rather than urllib: the python.org build for macOS ships without system certificates until the owner runs
    "Install Certificates.command", so urllib fails TLS there, while httpx carries certifi.
    """
    name = asset_name()
    if not name:
        raise RuntimeError(localefmt.chu(
            f"Cloudflare chưa có bản cloudflared cho máy này ({platform.system()} {platform.machine()}).",
            f"Cloudflare publishes no cloudflared build for this machine ({platform.system()} {platform.machine()})."))
    import httpx
    dest = local_binary()
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_name(dest.name + ".part")
    ready = dest.with_name(dest.name + ".new")
    try:
        with httpx.stream("GET", RELEASE_BASE + name, follow_redirects=True, timeout=60) as r:
            r.raise_for_status()
            with open(part, "wb") as f:
                for chunk in r.iter_bytes(1 << 16):
                    f.write(chunk)
        if name.endswith(".tgz"):
            with tarfile.open(part) as tf:
                member = next((m for m in tf.getmembers() if m.isfile() and Path(m.name).name == "cloudflared"), None)
                if member is None:
                    raise RuntimeError("cloudflared missing from " + name)
                ready.write_bytes(tf.extractfile(member).read())
        else:
            os.replace(part, ready)
        # Anything under 5 MB is an error page, not a 30+ MB Go binary.
        if ready.stat().st_size < 5 * 1024 * 1024:
            raise RuntimeError("download too small")
        os.chmod(ready, 0o755)
        if not _version_of(str(ready)):
            raise RuntimeError("downloaded file does not run")
        os.replace(ready, dest)
    except Exception as e:
        raise RuntimeError(localefmt.chu(f"Không tải được cloudflared: {e}", f"Could not download cloudflared: {e}"))
    finally:
        for p in (part, ready):
            try:
                p.unlink()
            except OSError:
                pass
    return str(dest)


# ---------------------------------------------------------------- local target and log parsing

def local_port() -> int:
    try:
        return int(os.getenv("JAVIS_PORT", "7777"))
    except ValueError:
        return 7777


def local_target() -> str:
    """Where cloudflared should send visitors: this server, by an address it actually listens on."""
    host = (os.getenv("JAVIS_HOST", "127.0.0.1") or "").strip()
    if host in ("", "0.0.0.0", "::", "[::]", "localhost"):
        host = "127.0.0.1"
    if ":" in host and not host.startswith("["):
        host = "[" + host + "]"
    return f"http://{host}:{local_port()}"


def parse_quick_url(line: str) -> str:
    m = QUICK_URL_RE.search(line or "")
    # api.trycloudflare.com is the service cloudflared asks for an address, not the address itself.
    if m and not m.group(0).lower().startswith("https://api."):
        return m.group(0)
    return ""


def parse_ingress(line: str):
    """[(hostname, service)] from the "Updated to new configuration" line of a token tunnel, or None.

    cloudflared logs the ingress rules the owner set in the Cloudflare dashboard as an escaped JSON string:
    config="{\\"ingress\\":[{\\"hostname\\":\\"javis.example.com\\", \\"service\\":\\"http://localhost:7777\\"}, ...]}"
    Reading them back lets Settings show the real address without asking the owner to type it a second time.
    """
    if "Updated to new configuration" not in (line or ""):
        return None
    raw = line.replace('\\"', '"')
    rules = []
    for obj in re.finditer(r"\{[^{}]*\}", raw):
        h = re.search(r'"hostname"\s*:\s*"([^"]+)"', obj.group(0))
        s = re.search(r'"service"\s*:\s*"([^"]+)"', obj.group(0))
        if h:
            rules.append((h.group(1).strip().lower(), s.group(1).strip() if s else ""))
    return rules


def service_points_here(service: str) -> bool:
    """Whether an ingress service such as http://localhost:7777 reaches this Javis."""
    m = re.match(r"^https?://(\[[^\]]+\]|[^/:]+)(?::(\d+))?", (service or "").strip().lower())
    if not m:
        return False
    host, port = m.group(1).strip("[]"), m.group(2)
    if host not in ("localhost", "127.0.0.1", "::1", "0.0.0.0"):
        own = (os.getenv("JAVIS_HOST", "") or "").strip().strip("[]").lower()
        if host != own:
            return False
    return (int(port) if port else 80) == local_port()


# ---------------------------------------------------------------- stray process from an earlier run

def _pid_file() -> Path:
    return Path(cfgmod.STATE_DIR) / "remote-tunnel.pid"


def _looks_like_cloudflared(pid: int) -> bool:
    try:
        if os.name == "nt":
            r = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"], capture_output=True,
                               text=True, timeout=10, creationflags=winproc.no_window())
            return "cloudflared" in (r.stdout or "").lower()
        proc = Path(f"/proc/{pid}/cmdline")
        if proc.exists():
            return "cloudflared" in proc.read_bytes().decode("utf-8", "replace").lower()
        r = subprocess.run(["ps", "-p", str(pid), "-o", "command="], capture_output=True, text=True, timeout=10,
                           creationflags=winproc.no_window())
        return "cloudflared" in (r.stdout or "").lower()
    except Exception:
        return False


def kill_stray() -> bool:
    """Kill the cloudflared an earlier Javis left behind (crash, killed from Task Manager).

    A child survives its parent on every OS, so without this a restart would leave two connectors running: the old
    quick tunnel keeps a dead address alive, and the old named-tunnel connector keeps using a token the owner may
    have just replaced.
    """
    f = _pid_file()
    try:
        pid = int(f.read_text().strip())
    except (OSError, ValueError):
        return False
    killed = False
    if pid > 0 and pid != os.getpid() and _looks_like_cloudflared(pid):
        if os.name == "nt":
            killed = winproc.kill_tree(pid)
        else:
            try:
                import signal
                os.kill(pid, signal.SIGTERM)
                killed = True
            except OSError:
                pass
    try:
        f.unlink()
    except OSError:
        pass
    return killed


# ---------------------------------------------------------------- Tailscale (0.244.0)
# Tailscale needs a system service and an account sign-in, so Javis never installs it; it only drives the CLI of an
# install the owner made. `tailscale serve --bg` stores the proxy in tailscaled itself, so it keeps working while
# Javis restarts and Javis has no process to supervise, only a config to switch on and off.

TS_SERVE_TIMEOUT = 25
TS_ENABLE_RE = re.compile(r"https://login\.tailscale\.com/\S+")
TS_URL_RE = re.compile(r"https://[a-z0-9-]+(?:\.[a-z0-9-]+)*\.ts\.net", re.I)
TS_STATUS_TTL = 10.0
# Seconds between attempts while Tailscale is missing, signed out or waiting for HTTPS to be enabled.
TS_RETRY_EVERY = 15


def _tailscale_candidates():
    """Where the installers put the CLI when it is not on PATH."""
    if os.name == "nt":
        pf = os.environ.get("ProgramFiles", r"C:\Program Files")
        return [os.path.join(pf, "Tailscale", "tailscale.exe")]
    if sys.platform == "darwin":
        # The Mac App Store and standalone apps ship the CLI as the app binary itself.
        return ["/Applications/Tailscale.app/Contents/MacOS/Tailscale", "/opt/homebrew/bin/tailscale",
                "/usr/local/bin/tailscale"]
    return []


def find_tailscale() -> str:
    found = shutil.which("tailscale")
    if found:
        return found
    for p in _tailscale_candidates():
        if os.path.isfile(p):
            return p
    return ""


def _ts_run(binary: str, args, timeout: float = 15):
    """(returncode, output). returncode is None when the command was still running at `timeout`."""
    try:
        r = subprocess.run([binary, *args], capture_output=True, text=True, encoding="utf-8", errors="replace",
                           timeout=timeout, stdin=subprocess.DEVNULL, creationflags=winproc.no_window())
        return r.returncode, (r.stdout or "") + (r.stderr or "")
    except subprocess.TimeoutExpired as e:
        # Partial output is always bytes here, whatever text= says.
        parts = [x.decode("utf-8", "replace") if isinstance(x, bytes) else (x or "") for x in (e.stdout, e.stderr)]
        return None, "".join(parts)
    except Exception as e:
        return -1, str(e)


def tailscale_info(binary: str = None) -> dict:
    """{"installed", "backend" (Running, NeedsLogin, Stopped...), "dns_name", "ip"} from `tailscale status --json`."""
    binary = find_tailscale() if binary is None else binary
    if not binary:
        return {"installed": False, "backend": "", "dns_name": "", "ip": ""}
    info = {"installed": True, "backend": "", "dns_name": "", "ip": ""}
    rc, out = _ts_run(binary, ["status", "--json"], timeout=10)
    try:
        d = json.loads(out[out.index("{"):])
    except ValueError:
        # Not running at all: "failed to connect to local tailscaled" and no JSON.
        info["backend"] = "Stopped"
        return info
    me = d.get("Self") or {}
    ips = me.get("TailscaleIPs") or []
    info.update(backend=str(d.get("BackendState") or ""), dns_name=str(me.get("DNSName") or "").rstrip(".").lower(),
                ip=str(ips[0]) if ips else "")
    return info


def tailscale_serve_on(binary: str, target: str) -> dict:
    """Ask tailscaled to proxy https://<machine>.ts.net to `target`.

    The first time on a tailnet, Tailscale has to switch HTTPS certificates on: the command then prints a
    login.tailscale.com link and waits for the owner to click Enable. We return that link for Settings to show and
    try again later, instead of hanging a request on it.
    """
    rc, out = _ts_run(binary, ["serve", "--bg", "--https=443", target], timeout=TS_SERVE_TIMEOUT)
    enable = TS_ENABLE_RE.search(out)
    url = TS_URL_RE.search(out)
    return {"ok": rc == 0, "url": url.group(0).lower() if url else "",
            "enable_url": enable.group(0).rstrip(".,)") if enable else "", "output": out.strip()}


def tailscale_serve_off(binary: str) -> bool:
    """Remove only the :443 handler Javis added, never the owner's other serve or funnel entries (`serve reset` would)."""
    rc, _ = _ts_run(binary, ["serve", "--https=443", "off"], timeout=15)
    return rc == 0


# ---------------------------------------------------------------- supervisor

class TunnelManager:
    """Runs one cloudflared at a time in a background thread and keeps it alive while the setting is on.

    In tailscale mode the same thread switches `tailscale serve` on, watches the password and the Tailscale login,
    and switches it off again."""

    def __init__(self, binary_finder=None, installer=None, tailscale_finder=None):
        self._find = binary_finder or find_binary
        self._install = installer or install_binary
        self._ts_find = tailscale_finder or find_tailscale
        self._serving_bin = ""      # tailscale binary that currently has our serve entry on
        self._ts_cache = (0.0, None)
        self._lock = threading.RLock()
        self._thread = None
        self._stop = threading.Event()
        self._proc = None
        self.log = deque(maxlen=200)
        self._reset_state("off")

    def _reset_state(self, state: str):
        self.state = state          # off | installing | starting | running | waiting | error
        self.error = ""
        self.url = ""
        self.ingress = []
        self.mode = ""
        self.since = 0.0
        self.enable_url = ""

    # -- public

    def start(self):
        """(Re)start from the current settings. Safe to call while running: it restarts with the new settings."""
        with self._lock:
            self.stop()
            self._stop = threading.Event()
            self._reset_state("starting")
            self._thread = threading.Thread(target=self._run, args=(self._stop,), name="remote-tunnel", daemon=True)
            self._thread.start()

    def stop(self, wait: float = 8.0, keep_serve: bool = False):
        """Stop. keep_serve=True (server shutdown) leaves `tailscale serve` on: it lives in tailscaled, and the next
        start re-applies it anyway, so a restart does not flap the owner's link."""
        with self._lock:
            self._stop.set()
            self._kill_proc()
            t = self._thread
            self._thread = None
        if t and t.is_alive() and t is not threading.current_thread():
            t.join(wait)
        if self._serving_bin and not keep_serve:
            tailscale_serve_off(self._serving_bin)
        self._serving_bin = ""
        self._reset_state("off")

    def autostart(self):
        kill_stray()
        if enabled():
            self.start()

    def tailscale_binary(self) -> str:
        return self._ts_find()

    def tailscale_status(self, fresh: bool = False) -> dict:
        """tailscale_info, cached a few seconds: Settings polls status while something is starting."""
        ts_at, cached = self._ts_cache
        if fresh or cached is None or time.time() - ts_at > TS_STATUS_TTL:
            cached = tailscale_info(self._ts_find())
            self._ts_cache = (time.time(), cached)
        return cached

    def status(self) -> dict:
        sec = section()
        tok = str(sec.get("token") or "")
        info = token_info(tok) if tok else None
        hosts = [h for h, _ in self.ingress]
        mismatch = [s for _, s in self.ingress if s and not service_points_here(s)]
        url = self.url or (("https://" + hosts[0]) if hosts else "")
        return {
            "enabled": bool(sec.get("enabled")),
            "mode": sec.get("mode") if sec.get("mode") in MODES else "quick",
            "state": self.state,
            "error": self.error,
            "url": url,
            "hostnames": hosts,
            "service_mismatch": mismatch,
            "target": local_target(),
            "has_token": bool(info),
            "tunnel_id": (info or {}).get("tunnel_id", "")[:8],
            "binary": bool(self._find()),
            "can_download": bool(asset_name()),
            "password_set": cfgmod.auth_enabled(),
            "since": self.since,
            "tailscale": self.tailscale_status(),
            "enable_url": self.enable_url,
        }

    # -- internals

    def _kill_proc(self):
        p = self._proc
        if not p or p.poll() is not None:
            return
        try:
            p.terminate()
            p.wait(5)
        except Exception:
            try:
                p.kill()
            except Exception:
                pass

    def _note(self, line: str):
        line = line.rstrip()
        if not line:
            return
        self.log.append(line)
        url = parse_quick_url(line)
        if url and self.mode == "quick":
            self.url = url
        rules = parse_ingress(line)
        if rules is not None:
            self.ingress = rules
        if any(k in line for k in CONNECTED_MARKERS):
            self.state = "running"
            self.error = ""
            if not self.since:
                self.since = time.time()
        # Matched on the message, not on an ERR level: "failed to request quick Tunnel" is printed bare, without one.
        low = line.lower()
        if "unauthorized" in low or "invalid tunnel secret" in low or "provided tunnel token is not valid" in low:
            self.error = localefmt.chu("Cloudflare không nhận token này. Tạo tunnel mới hoặc dán lại token.",
                                       "Cloudflare rejected this token. Paste it again or create a new tunnel.")
        elif "failed to request quick tunnel" in low or "failed to unmarshal quick tunnel" in low:
            self.error = localefmt.chu("Cloudflare chưa cấp được link nhanh (mạng chặn hoặc Cloudflare bận), "
                                       "Javis sẽ thử lại.",
                                       "Cloudflare could not hand out a quick link (network blocked or Cloudflare "
                                       "busy); Javis will retry.")

    def _command(self, binary: str, sec: dict):
        env = dict(os.environ)
        env.pop("TUNNEL_TOKEN", None)
        if self.mode == "token":
            env["TUNNEL_TOKEN"] = str(sec.get("token") or "")
            return [binary, "tunnel", "--no-autoupdate", "run"], env
        return [binary, "tunnel", "--no-autoupdate", "--url", local_target()], env

    def _wait(self, stop: threading.Event, seconds: float) -> bool:
        """Sleep, waking early on stop. True when asked to stop."""
        return stop.wait(seconds)

    def _run(self, stop: threading.Event):
        fails = 0
        while not stop.is_set():
            sec = section()
            if not sec.get("enabled"):
                break
            self.mode = sec.get("mode") if sec.get("mode") in MODES else "quick"
            if not cfgmod.auth_enabled():
                self.state = "error"
                self.error = localefmt.chu("Cần đặt mật khẩu đăng nhập trước khi mở Javis ra Internet.",
                                           "Set a login password before opening Javis to the Internet.")
                return
            if self.mode == "tailscale":
                self._run_tailscale(stop)
                if stop.is_set() or not enabled():
                    break
                continue  # password gone: the top of the loop reports it
            if self.mode == "token" and not token_info(str(sec.get("token") or "")):
                self.state = "error"
                self.error = localefmt.chu("Chưa có token Cloudflare hợp lệ.", "No valid Cloudflare token saved.")
                return
            binary = self._find()
            if not binary:
                self.state = "installing"
                try:
                    binary = self._install()
                except Exception as e:
                    if stop.is_set():
                        break
                    self.state, self.error = "error", str(e)
                    fails += 1
                    if self._wait(stop, BACKOFF[min(fails, len(BACKOFF) - 1)] * 2):
                        break
                    continue
            if stop.is_set():
                break
            cmd, env = self._command(binary, sec)
            self.state, self.url, self.ingress, self.since = "starting", "", [], 0.0
            started = time.time()
            try:
                proc = subprocess.Popen(cmd, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                        stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace",
                                        bufsize=1, creationflags=winproc.no_window())
            except Exception as e:
                self.state = "error"
                self.error = localefmt.chu(f"Không chạy được cloudflared: {e}", f"Could not start cloudflared: {e}")
                fails += 1
                if self._wait(stop, BACKOFF[min(fails, len(BACKOFF) - 1)]):
                    break
                continue
            self._proc = proc
            try:
                _pid_file().write_text(str(proc.pid))
            except OSError:
                pass
            reader = threading.Thread(target=self._read, args=(proc,), name="remote-tunnel-log", daemon=True)
            reader.start()
            last_check = time.time()
            while proc.poll() is None and not stop.is_set():
                if self._wait(stop, 1):
                    break
                if time.time() - last_check >= PASSWORD_CHECK_EVERY:
                    last_check = time.time()
                    if not cfgmod.auth_enabled() or not enabled():
                        break
            self._kill_proc()
            reader.join(3)
            try:
                _pid_file().unlink()
            except OSError:
                pass
            if stop.is_set():
                break
            if not cfgmod.auth_enabled():
                continue  # the top of the loop reports the missing password and stops
            if not enabled():
                break
            fails = 0 if time.time() - started > STABLE_AFTER else fails + 1
            self.state = "waiting"
            if not self.error:
                tail = self.log[-1] if self.log else ""
                self.error = localefmt.chu(f"cloudflared dừng ({proc.returncode}). {tail}".strip(),
                                           f"cloudflared stopped ({proc.returncode}). {tail}".strip())
            if self._wait(stop, BACKOFF[min(fails, len(BACKOFF) - 1)]):
                break
        # A thread that was replaced (Reconnect during a slow download) must not paint "off" over its successor.
        if stop is self._stop and self.state != "error":
            self.state = "off"

    def _still_allowed(self) -> bool:
        sec = section()
        return bool(sec.get("enabled")) and sec.get("mode") == "tailscale" and cfgmod.auth_enabled()

    def _run_tailscale(self, stop: threading.Event):
        """Switch `tailscale serve` on and watch it. Returns on stop, or when it may no longer run (then it is off)."""
        while not stop.is_set():
            ts = self._ts_find()
            if not ts:
                self.state = "error"
                self.error = localefmt.chu("Máy này chưa cài Tailscale.", "Tailscale is not installed on this computer.")
                if self._wait(stop, TS_RETRY_EVERY) or not self._still_allowed():
                    return
                continue
            info = self.tailscale_status(fresh=True)
            if info.get("backend") != "Running":
                self.state = "waiting"
                self.error = localefmt.chu("Tailscale trên máy này chưa đăng nhập hoặc đang tắt. Mở app Tailscale "
                                           "để đăng nhập, Javis tự thử lại.",
                                           "Tailscale on this computer is signed out or off. Open the Tailscale app "
                                           "to sign in; Javis retries on its own.")
                if self._wait(stop, TS_RETRY_EVERY) or not self._still_allowed():
                    return
                continue
            self.state, self.enable_url = "starting", ""
            res = tailscale_serve_on(ts, local_target())
            if stop.is_set():
                # stop() may have run its serve-off while this call was still on its way: undo it here.
                if res["ok"]:
                    tailscale_serve_off(ts)
                return
            if not res["ok"]:
                self.enable_url = res["enable_url"]
                if self.enable_url:
                    self.state = "waiting"
                    self.error = localefmt.chu("Tailscale cần bật HTTPS cho mạng của bạn (làm một lần). Mở link "
                                               "bên dưới, bấm Enable, Javis tự thử lại.",
                                               "Tailscale needs HTTPS switched on for your network (once). Open the "
                                               "link below, click Enable, and Javis retries on its own.")
                else:
                    tail = res["output"].splitlines()[-1] if res["output"] else ""
                    self.state = "error"
                    self.error = localefmt.chu(f"Tailscale báo lỗi: {tail}", f"Tailscale reported an error: {tail}")
                if self._wait(stop, TS_RETRY_EVERY) or not self._still_allowed():
                    return
                continue
            self._serving_bin = ts
            self.url = res["url"] or (("https://" + info["dns_name"]) if info.get("dns_name") else "")
            self.state, self.error, self.since = "running", "", time.time()
            last_check = last_status = time.time()
            while not stop.is_set():
                if self._wait(stop, 1):
                    return
                now = time.time()
                if now - last_check >= PASSWORD_CHECK_EVERY:
                    last_check = now
                    if not self._still_allowed():
                        tailscale_serve_off(ts)
                        self._serving_bin = ""
                        self.url = ""
                        return
                if now - last_status >= 30:
                    last_status = now
                    up = self.tailscale_status(fresh=True).get("backend") == "Running"
                    if not up and self.state == "running":
                        self.state = "waiting"
                        self.error = localefmt.chu("Tailscale trên máy này vừa tắt hoặc đăng xuất.",
                                                   "Tailscale on this computer was turned off or signed out.")
                    elif up and self.state == "waiting":
                        self.state, self.error = "running", ""

    def _read(self, proc):
        try:
            for line in proc.stdout:
                self._note(line)
        except Exception:
            pass


MANAGER = TunnelManager()
