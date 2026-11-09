"""Find git on this machine, and install it when it is missing (owner, 09/11/2026).

The GitHub card on the Connections page used to say "git is not installed on this machine" and stop there, which left
a Windows owner with a card that could connect but never clone a repo. The owner asked: check for git before
connecting GitHub, and install it first when the machine has none. So "Connect" now goes through here.

    find()       the path of a git that works, or "". Besides PATH it looks in the folders the installers use, because a
                 server started before git was installed keeps its old PATH: a git found there is added to
                 os.environ["PATH"], so every later `git ...` of this process and its children finds it too.
    plan()       how this machine can install git without a person at a terminal, best first:
                   Windows  winget (per-user scope), then the official Git for Windows installer with /CURRENTUSER,
                            the same two steps packaging/windows/bootstrap.ps1 takes. Neither needs admin rights.
                   macOS    Homebrew when it is there, then Apple's developer tools (`xcode-select --install` opens
                            Apple's own dialog; the person presses Install and Javis waits for it).
                   Linux    the system package manager, only as root (Docker, most VPS) or with password-less sudo.
                 Empty = Javis cannot do it here; manual() is the command to run by hand.
    start()      runs the plan in a worker thread (an install takes minutes). state() reports it for the dashboard.

macOS ships /usr/bin/git as a stub that only asks to install the developer tools, and running it pops Apple's dialog.
So that one path counts as git only when `xcode-select -p` says the tools are there, and it is never run to check.
Never use the em dash here.
"""
from __future__ import annotations

import hashlib
import os
import platform
import re
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import localefmt
import winproc

# winget, brew and apt can each take several minutes on a slow line; past this the step counts as failed.
INSTALL_TIMEOUT = 20 * 60
# How long Javis waits for the person to press Install in Apple's dialog and for the download that follows.
XCODE_WAIT = 30 * 60
XCODE_POLL = 5
GFW_LATEST = "https://api.github.com/repos/git-for-windows/git/releases/latest"
# The official installer is about 65 MB; anything this small is an error page, not Git for Windows.
MIN_INSTALLER_BYTES = 20 * 1024 * 1024
MANUAL_URL = "https://git-scm.com/downloads"

LINUX_INSTALL: Dict[str, List[str]] = {
    "apt-get": ["apt-get", "install", "-y", "git"],
    "dnf": ["dnf", "install", "-y", "git"],
    "yum": ["yum", "install", "-y", "git"],
    "apk": ["apk", "add", "--no-cache", "git"],
    "pacman": ["pacman", "-S", "--noconfirm", "--needed", "git"],
    "zypper": ["zypper", "--non-interactive", "install", "git"],
}

_LOCK = threading.Lock()
_JOB: Dict[str, Any] = {"install": "idle", "method": "", "wait_user": False, "error": "", "version": "", "started": 0.0}
_XCODE_READY = {"ok": False}


class _Fail(Exception):
    """One install step failed; the message is the tool's own last line (already language-neutral)."""


# ============================================================
# Finding git
# ============================================================
def _exe_name() -> str:
    return "git.exe" if os.name == "nt" else "git"


def _registry_path_dirs() -> List[str]:
    """The PATH Windows gives a NEW process (user + machine), which an installer updated after this server started."""
    if os.name != "nt":
        return []
    out: List[str] = []
    try:
        import winreg
    except ImportError:
        return out
    keys = ((winreg.HKEY_CURRENT_USER, r"Environment"),
            (winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"))
    for hive, sub in keys:
        try:
            with winreg.OpenKey(hive, sub) as k:
                raw, _ = winreg.QueryValueEx(k, "Path")
        except OSError:
            continue
        out.extend(os.path.expandvars(p).strip() for p in str(raw or "").split(";") if p.strip())
    return out


def _candidate_dirs() -> List[str]:
    """Folders git lands in that this process's PATH may not list yet."""
    if os.name == "nt":
        env = os.environ
        bases = [env.get("ProgramW6432"), env.get("ProgramFiles"), env.get("ProgramFiles(x86)"),
                 os.path.join(env["LOCALAPPDATA"], "Programs") if env.get("LOCALAPPDATA") else None]
        dirs = [os.path.join(b, "Git", "cmd") for b in bases if b]
        return dirs + _registry_path_dirs()
    if sys.platform == "darwin":
        return ["/opt/homebrew/bin", "/usr/local/bin", "/Library/Developer/CommandLineTools/usr/bin", "/usr/bin"]
    return ["/usr/bin", "/usr/local/bin", "/bin"]


def _xcode_ready() -> bool:
    """Apple's developer tools are installed, so /usr/bin/git is a real git (asked without running git)."""
    if _XCODE_READY["ok"]:
        return True
    try:
        p = subprocess.run(["xcode-select", "-p"], capture_output=True, text=True, timeout=10,
                           stdin=subprocess.DEVNULL, creationflags=winproc.no_window())
    except (OSError, subprocess.SubprocessError):
        return False
    ok = p.returncode == 0 and bool((p.stdout or "").strip()) and os.path.isdir((p.stdout or "").strip())
    _XCODE_READY["ok"] = ok
    return ok


def _usable(path: str) -> bool:
    if sys.platform == "darwin" and os.path.realpath(path) == "/usr/bin/git":
        return _xcode_ready()
    return os.path.isfile(path)


def _add_to_path(folder: str) -> None:
    cur = os.environ.get("PATH", "")
    parts = [p for p in cur.split(os.pathsep) if p]
    if os.path.normcase(folder) not in (os.path.normcase(p) for p in parts):
        os.environ["PATH"] = os.pathsep.join([folder] + parts)


def find() -> str:
    """Path of a working git, or "". Cheap: a PATH lookup and a few file checks, no git process."""
    p = shutil.which("git")
    if p and _usable(p):
        return p
    for folder in _candidate_dirs():
        exe = os.path.join(folder, _exe_name())
        if os.path.isfile(exe) and _usable(exe):
            _add_to_path(folder)
            return exe
    return ""


def available() -> bool:
    return bool(find())


def version(path: str = "") -> str:
    """"2.47.0.windows.2" from `git --version`, or "" when it does not answer like git."""
    path = path or find()
    if not path:
        return ""
    try:
        p = subprocess.run([path, "--version"], capture_output=True, text=True, encoding="utf-8", errors="replace",
                           timeout=20, stdin=subprocess.DEVNULL, creationflags=winproc.no_window())
    except (OSError, subprocess.SubprocessError):
        return ""
    m = re.match(r"\s*git version\s+(\S+)", p.stdout or "")
    return m.group(1) if m else ""


# ============================================================
# How this machine installs git
# ============================================================
def _is_root() -> bool:
    try:
        return os.geteuid() == 0
    except AttributeError:
        return False


def _sudo_ok() -> bool:
    """Password-less sudo: Javis must never sit on a password prompt nobody can see."""
    if not shutil.which("sudo"):
        return False
    try:
        p = subprocess.run(["sudo", "-n", "true"], capture_output=True, timeout=10, stdin=subprocess.DEVNULL,
                           creationflags=winproc.no_window())
    except (OSError, subprocess.SubprocessError):
        return False
    return p.returncode == 0


def _linux_pm() -> str:
    for pm in LINUX_INSTALL:
        if shutil.which(pm):
            return pm
    return ""


def _brew() -> str:
    for p in (shutil.which("brew"), "/opt/homebrew/bin/brew", "/usr/local/bin/brew"):
        if p and os.path.isfile(p):
            return p
    return ""


def plan() -> List[str]:
    """The install methods to try here, best first. Empty when Javis cannot install git on this machine by itself."""
    if os.name == "nt":
        return (["winget"] if shutil.which("winget") else []) + ["installer"]
    if sys.platform == "darwin":
        # Homebrew refuses to run as root.
        return (["brew"] if (_brew() and not _is_root()) else []) + ["xcode"]
    pm = _linux_pm()
    if pm and (_is_root() or _sudo_ok()):
        return [pm]
    return []


def manual() -> str:
    """The command to run by hand when Javis cannot install git itself."""
    if os.name == "nt":
        return "winget install -e --id Git.Git"
    if sys.platform == "darwin":
        return "xcode-select --install"
    return "sudo " + " ".join(LINUX_INSTALL[_linux_pm() or "apt-get"])


# ============================================================
# Install steps
# ============================================================
def _tail(text: str) -> str:
    """Last readable line of an installer's output (progress bars redraw with \\r, so split on it too)."""
    lines = [ln.strip() for ln in re.split(r"[\r\n]+", str(text or ""))]
    lines = [ln for ln in lines if ln and re.search(r"[A-Za-z]{3}", ln)]
    return (lines[-1] if lines else "")[:300]


def _run(argv: List[str], timeout: int = INSTALL_TIMEOUT, env: Optional[Dict[str, str]] = None) -> Tuple[int, str]:
    try:
        p = subprocess.run(argv, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout,
                           stdin=subprocess.DEVNULL, env=env, creationflags=winproc.no_window())
    except FileNotFoundError:
        raise _Fail(f"{argv[0]}: not found")
    except subprocess.TimeoutExpired:
        raise _Fail(f"{os.path.basename(argv[0])} ran over {timeout} s and was stopped")
    return p.returncode, (p.stdout or "") + "\n" + (p.stderr or "")


def _install_winget() -> None:
    # --scope user: no admin rights and no UAC prompt the person may not see. "Already installed" exits non-zero, so
    # whether it worked is decided by find() afterwards, not by the exit code.
    rc, out = _run([shutil.which("winget") or "winget", "install", "-e", "--id", "Git.Git", "--scope", "user",
                    "--silent", "--accept-source-agreements", "--accept-package-agreements"])
    if rc != 0 and not find():
        raise _Fail(_tail(out) or f"winget exit {rc}")


def pick_asset(assets: List[Dict[str, Any]], machine: str = "") -> Optional[Dict[str, Any]]:
    """The Git for Windows installer for this CPU from a release's assets (not the portable or MinGit builds)."""
    m = (machine or platform.machine() or "").lower()
    suffix = "arm64" if m in ("arm64", "aarch64") else "64-bit"
    pat = re.compile(r"^Git-[0-9.]+-" + re.escape(suffix) + r"\.exe$")
    for a in assets or []:
        if pat.match(str(a.get("name") or "")):
            return a
    return None


def _install_official() -> None:
    """Git for Windows from its GitHub release, silent and per user (installs into %LOCALAPPDATA%\\Programs\\Git)."""
    import httpx
    import config as cfgmod
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "javis-os"}
    try:
        rel = httpx.get(GFW_LATEST, headers=headers, timeout=60, follow_redirects=True)
        rel.raise_for_status()
        asset = pick_asset(rel.json().get("assets") or [])
    except Exception as e:  # noqa: BLE001 - any network or JSON trouble is one readable failure
        raise _Fail(f"git-for-windows release: {e}")
    if not asset:
        raise _Fail("git-for-windows release: no installer for this CPU")
    folder = Path(cfgmod.STATE_DIR) / "cache" / "git-installer"
    folder.mkdir(parents=True, exist_ok=True)
    dest = folder / str(asset["name"])
    try:
        sha = hashlib.sha256()
        with httpx.stream("GET", str(asset["browser_download_url"]), headers={"User-Agent": "javis-os"},
                          timeout=120, follow_redirects=True) as r:
            r.raise_for_status()
            with open(dest, "wb") as f:
                for chunk in r.iter_bytes(1 << 16):
                    f.write(chunk)
                    sha.update(chunk)
        if dest.stat().st_size < MIN_INSTALLER_BYTES:
            raise _Fail("git installer download too small")
        digest = str(asset.get("digest") or "")
        if digest.startswith("sha256:") and digest[7:].lower() != sha.hexdigest():
            raise _Fail("git installer checksum does not match the release")
        rc, out = _run([str(dest), "/VERYSILENT", "/NORESTART", "/NOCANCEL", "/SP-", "/SUPPRESSMSGBOXES",
                        "/CURRENTUSER"])
        if rc != 0 and not find():
            raise _Fail(_tail(out) or f"git installer exit {rc}")
    except _Fail:
        raise
    except Exception as e:  # noqa: BLE001
        raise _Fail(f"git installer: {e}")
    finally:
        try:
            dest.unlink()
        except OSError:
            pass


def _install_brew() -> None:
    env = dict(os.environ, NONINTERACTIVE="1", HOMEBREW_NO_ENV_HINTS="1")
    rc, out = _run([_brew(), "install", "git"], env=env)
    if rc != 0 and not find():
        raise _Fail(_tail(out) or f"brew exit {rc}")


def _install_xcode() -> None:
    """Opens Apple's "install developer tools" dialog, then waits for the person to press Install and the download."""
    rc, out = _run(["xcode-select", "--install"], timeout=60)
    if rc != 0 and "already installed" not in out.lower():
        raise _Fail(_tail(out) or f"xcode-select exit {rc}")
    _set(wait_user=True)
    deadline = time.time() + XCODE_WAIT
    while time.time() < deadline:
        if find():
            return
        time.sleep(XCODE_POLL)
    raise _Fail("Apple developer tools were not installed in time")


def _install_linux(pm: str) -> None:
    pre = [] if _is_root() else ["sudo", "-n"]
    env = dict(os.environ, DEBIAN_FRONTEND="noninteractive")
    rc, out = _run(pre + LINUX_INSTALL[pm], env=env)
    if rc != 0 and pm == "apt-get":
        # A fresh container or VPS often has no package lists yet.
        _run(pre + ["apt-get", "update"], env=env)
        rc, out = _run(pre + LINUX_INSTALL[pm], env=env)
    if rc != 0 and not find():
        raise _Fail(_tail(out) or f"{pm} exit {rc}")


def _runner(method: str) -> Callable[[], None]:
    if method in LINUX_INSTALL:
        return lambda: _install_linux(method)
    return {"winget": _install_winget, "installer": _install_official, "brew": _install_brew,
            "xcode": _install_xcode}[method]


# ============================================================
# The install job
# ============================================================
def _set(**kw: Any) -> None:
    with _LOCK:
        _JOB.update(kw)


def _worker(methods: List[str]) -> None:
    last = ""
    try:
        for m in methods:
            _set(method=m, wait_user=False)
            try:
                _runner(m)()
            except _Fail as e:
                last = str(e)
                continue
            except Exception as e:  # noqa: BLE001 - one broken step must not leave the job "installing" forever
                last = f"{m}: {e}"
                continue
            path = find()
            if path:
                _set(install="ok", version=version(path), wait_user=False, error="")
                return
            last = f"{m}: git still not found after the install"
        _set(install="failed", wait_user=False, error=last or "unknown")
    except Exception as e:  # noqa: BLE001
        _set(install="failed", wait_user=False, error=str(e))


def start() -> Dict[str, Any]:
    """Start installing git unless it is already here or already being installed. Returns state()."""
    if available():
        return state()
    methods = plan()
    with _LOCK:
        if methods and _JOB["install"] != "installing":
            _JOB.update(install="installing", method=methods[0], wait_user=False, error="", version="",
                        started=time.time())
            threading.Thread(target=_worker, args=(methods,), name="git-install", daemon=True).start()
    return state()


def state() -> Dict[str, Any]:
    """What the dashboard shows. `install`: idle, installing, ok or failed (this process's last attempt)."""
    path = find()
    with _LOCK:
        job = dict(_JOB)
    out: Dict[str, Any] = {
        "has_git": bool(path),
        "install": job["install"],
        "method": job["method"],
        "wait_user": bool(job["wait_user"]) and job["install"] == "installing",
        "version": job["version"],
        "manual": manual(),
        "manual_url": MANUAL_URL,
        "error": "",
    }
    if not path:
        # Asked only while git is missing: on Linux it may run `sudo -n true`.
        out["can_install"] = job["install"] == "installing" or bool(plan())
    else:
        out["can_install"] = True
    if job["install"] == "failed" and not path:
        out["error"] = localefmt.chu("Chưa cài được git: {d}", "Could not install git: {d}", d=job["error"])
    return out
