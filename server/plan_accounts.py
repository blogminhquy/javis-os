"""Several accounts on one subscription plan card: ChatGPT (Codex), Grok Build and Claude Code (0.353.0).

docs/dev/2026-10-model-routing-spec.md 2.2 and 6.3. Account 1 is the login the machine already has (`~/.codex`,
`~/.grok`, `~/.claude`): nothing about it moves, so a machine with one account behaves exactly as before. Every
EXTRA account gets its own config folder under `STATE_DIR/accounts/<id>/<kind>/`, and a run on that account points
the CLI at it (`CODEX_HOME`, `GROK_HOME`, `CLAUDE_CONFIG_DIR`). The CLI keeps and refreshes its own login there.

Rotation is sequential: the first account switched on, signed in and not resting runs; one out of quota rests
(model_routing.mark_rest) and the next takes over; a rested account comes back first once its reset time passes.
All accounts of a card are used before the next card in the usage order.

What an extra account does NOT carry (stated plainly in the guide): the plan usage meters, image generation and
the HTTP-only ChatGPT paths (chat without tools, bots, voice) still read account 1. A conversation that switches
account cannot resume the CLI thread of the other account, so that turn starts a fresh thread with the history
rebuilt (the existing resume fallback).
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import time
from pathlib import Path

import config as cfgmod
import model_routing

MAIN = "main"
KIND = {"openai-oauth": "codex", "grok-cli": "grok", "anthropic-cli": "claude"}
ENV = {"codex": "CODEX_HOME", "grok": "GROK_HOME", "claude": "CLAUDE_CONFIG_DIR"}
# Files copied from account 1's folder into an extra account's folder before each run, so the extra account sees
# the same settings and MCP servers (Codex `config.toml` and Javis's hub profile, Grok `config.toml`, Claude
# `settings.json`). Logins and history are never copied.
_SHARED = {"codex": ("*.toml",), "grok": ("config.toml",), "claude": ("settings.json",)}
# Claude keeps user-scope MCP servers (added through Claude Code's own MCP, `--scope user`) in `.claude.json` NEXT TO the
# config folder, together with that login's account data. Only its `mcpServers` list is carried over (0.355.0).
_MARK = ".javis-signed-in"


def supported(provider: str) -> bool:
    return provider in KIND


def _home_dir() -> Path:
    h = os.environ.get("USERPROFILE") if os.name == "nt" else os.environ.get("HOME")
    return Path(h) if h else Path.home()


def default_home(provider: str) -> Path:
    """Account 1's folder, where the CLI keeps the login the machine already has."""
    kind = KIND[provider]
    env = (os.environ.get(ENV[kind]) or "").strip()
    if env:
        return Path(env).expanduser()
    return _home_dir() / (".codex" if kind == "codex" else ".grok" if kind == "grok" else ".claude")


def root() -> Path:
    return Path(cfgmod.STATE_DIR) / "accounts"


def home(provider: str, account_id: str, create: bool = True):
    """Config folder of an extra account; None for account 1 (the CLI's own default)."""
    if not supported(provider) or not account_id or account_id == MAIN:
        return None
    safe = "".join(c for c in str(account_id) if c.isalnum() or c in "_-")[:40]
    if not safe:
        return None
    p = root() / safe / KIND[provider]
    if create:
        try:
            p.mkdir(parents=True, exist_ok=True)
        except OSError:
            return None
    return p


def env_for(provider: str, folder) -> dict:
    """Variables that point the CLI at an account's folder. {} for account 1."""
    if not folder or not supported(provider):
        return {}
    return {ENV[KIND[provider]]: str(folder)}


def prepare(provider: str, folder) -> None:
    """Copy account 1's shared settings into an extra account's folder when they are newer. Best effort."""
    if not folder or not supported(provider):
        return
    src = default_home(provider)
    for pat in _SHARED[KIND[provider]]:
        try:
            files = list(src.glob(pat))
        except OSError:
            continue
        for f in files:
            if not f.is_file() or f.name in ("auth.json", ".credentials.json"):
                continue
            dst = Path(folder) / f.name
            try:
                if not dst.exists() or f.stat().st_mtime > dst.stat().st_mtime:
                    shutil.copy2(f, dst)
            except OSError:
                pass
    if KIND[provider] == "claude":
        _share_claude_mcp(src, Path(folder))


def _share_claude_mcp(src_home: Path, folder: Path) -> None:
    """Copy account 1's user-scope MCP servers into an extra Claude account's `.claude.json`, keeping everything else
    that file holds for that account. Best effort."""
    src = (src_home / ".claude.json") if (src_home / ".claude.json").is_file() else (src_home.parent / ".claude.json")
    try:
        servers = (json.loads(src.read_text(encoding="utf-8")) or {}).get("mcpServers")
    except (OSError, ValueError, AttributeError):
        return
    if not isinstance(servers, dict):
        return
    dst = folder / ".claude.json"
    try:
        cur = json.loads(dst.read_text(encoding="utf-8")) if dst.is_file() else {}
        if not isinstance(cur, dict) or cur.get("mcpServers") == servers:
            return
        cur["mcpServers"] = servers
        dst.write_text(json.dumps(cur, ensure_ascii=False, indent=2), encoding="utf-8")
    except (OSError, ValueError):
        pass


def mark_signed_in(provider: str, folder) -> None:
    """Remember that Javis saw this account finish signing in (Claude on macOS keeps the token in the Keychain,
    so no file in the folder proves it)."""
    if not folder:
        return
    try:
        (Path(folder) / _MARK).write_text(json.dumps({"provider": provider, "at": time.time()}), encoding="utf-8")
    except OSError:
        pass


def signed_in(provider: str, account_id: str) -> bool:
    """Whether an account can run. Account 1 counts as signed in: its own card already says when it is not."""
    if account_id == MAIN:
        return True
    folder = home(provider, account_id, create=False)
    if not folder or not folder.exists():
        return False
    kind = KIND[provider]
    if kind == "codex":
        try:
            tok = (json.loads((folder / "auth.json").read_text(encoding="utf-8")) or {}).get("tokens") or {}
            return bool(tok.get("access_token") or tok.get("refresh_token"))
        except (OSError, ValueError, AttributeError):
            return False
    if kind == "grok":
        try:
            import grok_cli
            return bool(grok_cli.auth_status(home=folder).get("connected"))
        except Exception:  # noqa: BLE001
            return False
    if (folder / ".credentials.json").exists():
        return True
    # Only macOS keeps the Claude token in the Keychain, where no file proves it; elsewhere a missing credentials
    # file means signed out, whatever Javis remembered (0.355.0).
    return sys.platform == "darwin" and (folder / _MARK).exists()


def accounts(m: dict, provider: str) -> list:
    """[{'id','label','enabled'}] in the owner's order. Account 1 is always there, even before any list is saved."""
    lst = [dict(a) for a in (((m or {}).get("accounts") or {}).get(provider) or []) if isinstance(a, dict)]
    out, seen = [], set()
    for a in lst:
        aid = str(a.get("id") or "")
        if not aid or aid in seen:
            continue
        seen.add(aid)
        out.append({"id": aid, "label": str(a.get("label") or "")[:60], "enabled": a.get("enabled") is not False})
    if MAIN not in seen:
        out.insert(0, {"id": MAIN, "label": "", "enabled": True})
    return out


def usable(m: dict, provider: str, now: float = None) -> list:
    return [a for a in accounts(m, provider)
            if a["enabled"] and not model_routing.resting_until(provider, a["id"], now)
            and signed_in(provider, a["id"])]


def has_extra(m: dict, provider: str) -> bool:
    return any(a["id"] != MAIN for a in accounts(m, provider))


def pick(m: dict, provider: str):
    """The account a run uses now, or None when none can run (every one off, resting or signed out)."""
    u = usable(m, provider)
    return u[0] if u else None


def fallback(m: dict, provider: str):
    """The account to run when none is usable: the first switched-on, signed-in one even if resting (the provider then
    says it is out of quota), never an account the owner switched off. None when every account is off."""
    return next((a for a in accounts(m, provider) if a["enabled"] and signed_in(provider, a["id"])), None)


def save(m: dict, provider: str, items: list, removed=None) -> None:
    """Write the account list (order, label, on/off). Only accounts named in `removed` are deleted (with their login
    folder); one merely missing from `items`, as from a page drawn before it signed in, stays at the end of the list.
    Account 1 cannot be removed."""
    old = accounts(m, provider)
    before = {a["id"] for a in old}
    gone_ids = {str(x) for x in (removed or []) if str(x) != MAIN} & before
    clean, seen = [], set()
    for a in items or []:
        if not isinstance(a, dict):
            continue
        aid = str(a.get("id") or "")
        if aid not in before or aid in seen or aid in gone_ids:
            continue
        seen.add(aid)
        clean.append({"id": aid, "label": str(a.get("label") or "")[:60], "enabled": a.get("enabled") is not False})
    if MAIN not in seen:
        clean.insert(0, next((dict(a) for a in old if a["id"] == MAIN), {"id": MAIN, "label": "", "enabled": True}))
        seen.add(MAIN)
    for a in old:                      # missing from a stale page, not removed: keep it
        if a["id"] not in seen and a["id"] not in gone_ids:
            clean.append(dict(a))
    m.setdefault("accounts", {})[provider] = clean
    for gone in gone_ids:
        remove_folder(provider, gone)
        model_routing.clear_rest(provider, gone)


def add(m: dict, provider: str, account_id: str, label: str = "") -> None:
    """Append a freshly signed-in account at the END of the card's list (spec 2.2.6)."""
    lst = accounts(m, provider)
    if any(a["id"] == account_id for a in lst):
        return
    lst.append({"id": account_id, "label": str(label or "")[:60], "enabled": True})
    m.setdefault("accounts", {})[provider] = lst


def remove_folder(provider: str, account_id: str) -> None:
    folder = home(provider, account_id, create=False)
    if not folder:
        return
    try:
        shutil.rmtree(folder.parent if folder.parent.parent == root() else folder, ignore_errors=True)
    except OSError:
        pass


def view(m: dict, provider: str) -> list:
    """What the Models page draws for a plan card's account list."""
    out = []
    for a in accounts(m, provider):
        out.append({"id": a["id"], "label": a["label"], "enabled": a["enabled"], "main": a["id"] == MAIN,
                    "signed_in": signed_in(provider, a["id"]),
                    "resting_until": model_routing.resting_until(provider, a["id"])})
    return out


# ---------------------------------------------------------------- engines

def in_use(provider: str) -> bool:
    """Whether the plan account list drives this provider now. False for Claude Code running on an Anthropic API
    key: the key pays, there is no plan account to pick or to move on to."""
    if not supported(provider):
        return False
    if provider == "anthropic-cli":
        try:
            import claude_auth
            if claude_auth.che_do() == claude_auth.API_KEY:
                return False
        except Exception:  # noqa: BLE001
            pass
    return True


def apply(engine, provider: str, m: dict):
    """Point one engine at the account that should run now. Returns the account id (MAIN when account 1 runs or
    when no account can run, so the turn reports the provider's own error as before)."""
    if engine is None or not in_use(provider):
        return MAIN
    acc = (pick(m, provider) or fallback(m, provider)) if has_extra(m, provider) else None
    aid = acc["id"] if acc else MAIN
    use(engine, provider, aid)
    return aid


def use(engine, provider: str, account_id: str):
    """Point `engine` at one given account. Background work builds one link per account with this."""
    folder = home(provider, account_id)
    prepare(provider, folder)
    engine.account_provider = provider
    engine.account_id = account_id
    kind = KIND[provider]
    if kind == "codex":
        engine.codex_home = str(folder) if folder else None
    elif kind == "grok":
        engine.grok_home = str(folder) if folder else None
    else:
        _claude_use(engine, folder)
    return engine


def _claude_use(engine, folder) -> None:
    """Claude runs through claude-agent-sdk; its options are built per run, so the account's folder is added to
    the environment the SDK hands the `claude` process. The engine file itself is pinned (improvement profile),
    so this wraps the built options instead of editing it."""
    engine.claude_config_dir = str(folder) if folder else None
    # Wrapped once PER INSTANCE: background work copies the chat's engine (copy.copy) for a second account, and the
    # copy must build options from its own attributes, not through the original's closure.
    if getattr(engine, "_javis_wrap_owner", None) is engine:
        return
    cls_opts = getattr(type(engine), "_options", None)
    if cls_opts is None:
        return
    orig = cls_opts.__get__(engine, type(engine))

    def _options(*a, **k):
        o = orig(*a, **k)
        d = getattr(engine, "claude_config_dir", None)
        if d and hasattr(o, "env"):
            env = dict(getattr(o, "env", None) or {}) or dict(os.environ)
            env["CLAUDE_CONFIG_DIR"] = d
            o.env = env
        return o

    engine._options = _options
    engine._javis_wrap_owner = engine
