"""Keep the Claude Agent SDK (the Python package Javis drives Claude Code through) current on its own (2026-11-10).

Claude Code updates itself daily (claude_update.py), but the `claude-agent-sdk` package that talks to it only moved when
a Javis release changed `requirements.txt`. The two drift apart, and fixes in the SDK (CVE-2026-96620, fixed in 0.2.121,
is the one that prompted this) waited for somebody to bump a number by hand.

Once a day, on the same switch as the Claude Code update (Models page, or JAVIS_CLAUDE_AUTO_UPDATE=0), this module asks
PyPI for a newer release and installs it. It is a package from the Internet going into the server's own environment, so
every step is fenced:

- Same series only. The installed `X.Y.*` moves to a newer `X.Y.*`, never to the next minor: that is where the SDK changes
  its interface. `requirements.txt` carries the same ceiling.
- Cooled down. A release is taken only COOLDOWN_S after it was uploaded, and never a yanked one or a pre-release, so a
  bad upload has time to be pulled before any Javis installs it.
- Nothing else moves. pip runs under a constraints file built from every exact pin of `requirements.txt`; a release that
  needs a different fastapi or starlette fails to install instead of dragging them along.
- Proven before it is kept. A fresh Python process imports the new package and builds real engine options through Javis's
  own `claude_sdk_engine`. If that fails the previous version is installed back and the bad version is remembered, so it
  is not tried again tomorrow.

The running server keeps the version it imported at start: the new one is used from the next restart, and `status()` says
so. The Docker image is not updated here (its packages belong to root and arrive with each image), exactly like Claude
Code itself.
"""
from __future__ import annotations

import importlib.metadata
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path
from typing import Optional

import claude_update
import config as cfgmod
import deploy_info
import localefmt
import winproc

PACKAGE = "claude-agent-sdk"
PYPI_URL = "https://pypi.org/pypi/claude-agent-sdk/json"
PERIOD_S = 24 * 3600
COOLDOWN_S = 3 * 24 * 3600
_STATE_FILE = "sdk-update.json"
_VERSION_RE = re.compile(r"^\d+(\.\d+){1,3}$")       # plain release numbers only: no rc, dev, post or local part
_REQ_PIN_RE = re.compile(r"^\s*([A-Za-z0-9_.\-]+)(\[[^\]]*\])?\s*==\s*([A-Za-z0-9_.\-]+)\s*(?:#.*)?$")
_MAX_BAD = 20

# What a fresh interpreter must manage with the new package before Javis keeps it: import every name the server uses, then
# build engine options through Javis's own engine module, the code that will really run on it.
_SMOKE = r"""
import sys
sys.path.insert(0, sys.argv[1])
import claude_agent_sdk
from claude_agent_sdk import (ClaudeAgentOptions, ClaudeSDKClient, HookMatcher, tool, create_sdk_mcp_server,
                              PermissionResultAllow, PermissionResultDeny, AssistantMessage, UserMessage,
                              SystemMessage, ResultMessage, StreamEvent, TextBlock, ToolUseBlock, ToolResultBlock)
fields = set(getattr(ClaudeAgentOptions, "__dataclass_fields__", {}))
missing = sorted({"system_prompt", "cwd", "allowed_tools", "disallowed_tools", "mcp_servers", "permission_mode",
                  "can_use_tool", "resume", "hooks"} - fields)
if missing:
    raise SystemExit("ClaudeAgentOptions lost fields: " + ", ".join(missing))
import claude_sdk_engine as eng
if not getattr(eng, "_SDK_OK", False):
    raise SystemExit("claude_sdk_engine does not accept this SDK")
opts = eng.ClaudeSDK(system_prompt="smoke", cwd=sys.argv[1], tag="sdk-smoke", allowed_tools=["Read"])._options()
if opts is None:
    raise SystemExit("engine built no options")
print("SMOKE-OK " + claude_agent_sdk.__version__)
"""


def _state_path() -> Path:
    return Path(cfgmod.STATE_DIR) / _STATE_FILE


def status() -> dict:
    """The last attempt as stored, plus what is installed and loaded now. Never raises."""
    try:
        d = json.loads(_state_path().read_text(encoding="utf-8")) or {}
    except Exception:  # noqa: BLE001
        d = {}
    if not isinstance(d, dict):
        d = {}
    d["installed"] = installed()
    d["loaded"] = loaded()
    d["restart_needed"] = bool(d["installed"] and d["loaded"] and d["installed"] != d["loaded"])
    return d


def _save(d: dict) -> None:
    try:
        p = _state_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        keep = {k: v for k, v in d.items() if k not in ("installed", "loaded", "restart_needed")}
        p.write_text(json.dumps(keep, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")
    except Exception:  # noqa: BLE001
        pass


def installed() -> str:
    """Version on disk (what the next start will import)."""
    try:
        importlib.invalidate_caches()
        return importlib.metadata.version(PACKAGE)
    except Exception:  # noqa: BLE001
        return ""


def loaded() -> str:
    """Version this process imported, "" when the SDK has not been imported yet."""
    mod = sys.modules.get("claude_agent_sdk")
    return str(getattr(mod, "__version__", "") or "") if mod else ""


def enabled(cfg: Optional[dict] = None) -> bool:
    """Same switch as the daily Claude Code update: one decision for the owner, one env var for the admin."""
    return claude_update.bat(cfg)


def due(now: Optional[float] = None) -> bool:
    now = time.time() if now is None else now
    try:
        last = float((json.loads(_state_path().read_text(encoding="utf-8")) or {}).get("ts") or 0)
    except Exception:  # noqa: BLE001
        last = 0.0
    return (now - last) >= PERIOD_S


def _key(v: str) -> tuple:
    return tuple(int(x) for x in v.split("."))


def pick(current: str, releases: dict, now: Optional[float] = None, bad=(), python=None) -> str:
    """The version to move to, or "" to stay. Pure: `releases` is the `releases` object of PyPI's JSON."""
    if not _VERSION_RE.match(current or ""):
        return ""
    now = time.time() if now is None else now
    cur = _key(current)
    best = ""
    for v, files in (releases or {}).items():
        if not _VERSION_RE.match(str(v)) or v in bad or not isinstance(files, list) or not files:
            continue
        k = _key(v)
        if k[:2] != cur[:2] or k <= cur:
            continue
        if any(f.get("yanked") for f in files if isinstance(f, dict)):
            continue
        newest_upload = max((_upload_ts(f) for f in files if isinstance(f, dict)), default=0.0)
        if not newest_upload or now - newest_upload < COOLDOWN_S:
            continue
        if not _python_ok(files, python):
            continue
        if not best or k > _key(best):
            best = v
    return best


def _upload_ts(f: dict) -> float:
    raw = str(f.get("upload_time_iso_8601") or f.get("upload_time") or "")
    if not raw:
        return 0.0
    try:
        from datetime import datetime, timezone
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except ValueError:
        return 0.0


def _python_ok(files: list, python=None) -> bool:
    py = python or "%d.%d.%d" % sys.version_info[:3]
    specs = {str(f.get("requires_python") or "") for f in files if isinstance(f, dict)}
    specs.discard("")
    if not specs:
        return True
    try:
        from packaging.specifiers import SpecifierSet
        return all(SpecifierSet(s).contains(py, prereleases=True) for s in specs)
    except Exception:  # noqa: BLE001
        return False


def _fetch_releases() -> dict:
    req = urllib.request.Request(PYPI_URL, headers={"Accept": "application/json", "User-Agent": "javis-os"})
    with urllib.request.urlopen(req, timeout=30) as r:   # noqa: S310 - fixed https URL, no caller input
        if r.status != 200:
            raise OSError(f"PyPI answered {r.status}")
        data = json.loads(r.read(20_000_000).decode("utf-8"))
    rel = data.get("releases") if isinstance(data, dict) else None
    if not isinstance(rel, dict):
        raise ValueError("PyPI answer has no releases")
    return rel


def requirements_path() -> Path:
    return Path(__file__).resolve().parent.parent / "requirements.txt"


def constraints_text(req_text: str) -> str:
    """Every exact pin of requirements.txt except the SDK itself, one `name==version` per line."""
    out = []
    for line in (req_text or "").splitlines():
        m = _REQ_PIN_RE.match(line)
        if m and m.group(1).lower().replace("_", "-") != PACKAGE:
            out.append(f"{m.group(1)}=={m.group(3)}")
    return "\n".join(out) + ("\n" if out else "")


def _run(cmd: list, timeout: int):
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PIP_DISABLE_PIP_VERSION_CHECK"] = "1"
    env["PIP_NO_INPUT"] = "1"
    return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                          timeout=timeout, env=env, stdin=subprocess.DEVNULL, creationflags=winproc.no_window())


def _pip_install(version: str, constraints: str) -> tuple:
    """(ok, last line of pip's output)."""
    fd, cpath = tempfile.mkstemp(prefix="javis-sdk-constraints-", suffix=".txt")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(constraints)
        cmd = [sys.executable, "-m", "pip", "install", "--quiet", f"{PACKAGE}=={version}"]
        if constraints.strip():
            cmd += ["-c", cpath]
        r = _run(cmd, 900)
        lines = [x for x in ((r.stdout or "") + (r.stderr or "")).splitlines() if x.strip()]
        return r.returncode == 0, (lines[-1] if lines else "")[:300]
    except subprocess.TimeoutExpired:
        return False, "pip did not finish in 15 minutes"
    except Exception as e:  # noqa: BLE001
        return False, f"{type(e).__name__}: {e}"
    finally:
        try:
            os.unlink(cpath)
        except OSError:
            pass


def _smoke(version: str) -> tuple:
    """(ok, why not). A fresh interpreter, so it imports what is on disk now, not what this server loaded at start."""
    server_dir = str(Path(__file__).resolve().parent)
    try:
        r = _run([sys.executable, "-c", _SMOKE, server_dir], 180)
    except subprocess.TimeoutExpired:
        return False, "the check did not finish in 3 minutes"
    except Exception as e:  # noqa: BLE001
        return False, f"{type(e).__name__}: {e}"
    out = (r.stdout or "").strip().splitlines()
    if r.returncode == 0 and out and out[-1] == f"SMOKE-OK {version}":
        return True, ""
    lines = [x for x in ((r.stderr or "") + "\n" + (r.stdout or "")).splitlines() if x.strip()]
    return False, (lines[-1] if lines else f"exit code {r.returncode}")[:300]


def update(reason: str = "manual", *, fetch=None, pip_install=None, smoke=None, now: Optional[float] = None) -> dict:
    """Look for a newer SDK and install it. Never raises: every failure comes back in `error`.

    `fetch`, `pip_install` and `smoke` are the three outside steps, replaceable in tests."""
    now = time.time() if now is None else now
    fetch, pip_install, smoke = fetch or _fetch_releases, pip_install or _pip_install, smoke or _smoke
    prev = {}
    try:
        prev = json.loads(_state_path().read_text(encoding="utf-8")) or {}
    except Exception:  # noqa: BLE001
        prev = {}
    bad = [str(x) for x in (prev.get("bad") or []) if isinstance(x, str)][-_MAX_BAD:]
    res = {"ok": False, "ts": now, "reason": reason, "bad": bad, "changed": False}
    if deploy_info.deploy_mode() == "docker":
        res.update(docker=True, error=localefmt.chu(
            "Bản Docker nhận Claude Agent SDK mới theo mỗi bản cập nhật Javis, không cập nhật riêng được.",
            "The Docker build gets a new Claude Agent SDK with each Javis update; it cannot be updated on its own."))
        return res                      # not stored: nothing was tried, and the image is read-only for this user
    cur = installed()
    res["from"] = res["to"] = cur
    if not cur:
        res["error"] = localefmt.chu("Chưa cài Claude Agent SDK.", "The Claude Agent SDK is not installed.")
        _save(res)
        return res
    try:
        target = pick(cur, fetch(), now, bad)
    except Exception as e:  # noqa: BLE001
        res["error"] = localefmt.chu("Không hỏi được PyPI: ", "Could not ask PyPI: ") + f"{type(e).__name__}: {e}"[:200]
        _save(res)
        return res
    if not target:
        res["ok"] = True
        _save(res)
        return res
    try:
        constraints = constraints_text(requirements_path().read_text(encoding="utf-8"))
    except OSError:
        constraints = ""
    ok, why = pip_install(target, constraints)
    if ok:
        ok, why = smoke(target)
        if not ok:
            why = localefmt.chu("Bản mới không qua bước chạy thử: ", "The new version failed its check: ") + why
    if not ok:
        # Put the previous version back whether pip stopped half way or the check failed, and do not try this one again.
        back_ok, back_why = pip_install(cur, constraints)
        res["bad"] = (bad + [target])[-_MAX_BAD:]
        res["error"] = (why or localefmt.chu("pip không cài được", "pip could not install it"))[:400]
        res["rolled_back"] = bool(back_ok)
        if not back_ok:
            res["error"] += localefmt.chu(" Cài lại bản cũ cũng lỗi: ", " Putting the old version back failed too: ") + back_why
        res["to"] = installed() or cur
        _save(res)
        return res
    res.update(ok=True, to=target, changed=True)
    _save(res)
    return res
