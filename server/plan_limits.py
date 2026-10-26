"""Plan usage limits (0.329.0): how much of the subscription's 5-hour and weekly allowance is used.

The composer ring shows these two meters for the brains that run on a plan the user already pays
for: Claude Code signed in to Pro/Max, and ChatGPT through Codex. Javis never reads either login
token, so the numbers come from what the two CLIs report on their own:

- Claude Code sends a `rate_limit_event` in its stream after each request (hooked by `cai_vao_claude_sdk`). `rate_limit_info.raw`
  carries `unifiedWindows.five_hour` and `.seven_day` (utilization 0-1, resetsAt in epoch seconds).
  Older CLIs send only the window that bound (`rateLimitType` plus `utilization`), merged here.
- Codex app-server sends `account/rateLimits/updated` (camelCase), and every `token_count` line of a
  Codex rollout file carries `rate_limits` (snake_case). Both are `primary` and `secondary` windows,
  told apart by their length in minutes (300 is the 5-hour one, 10080 the weekly one).

The last snapshot of each brain is kept in STATE_DIR/plan_limits.json, so the ring survives a
restart. A window whose reset time has passed reads as 0%: the plan has started a fresh window.

Grok Build and Antigravity report no meter at all (only token counts). For them, and for the two
above, `ghi_het` records the moment the CLI refused a turn for running out of plan quota (the chat
turn's limit detector calls it), so the ring can at least turn red then. It stays red until the
reset time the CLI gave, or for an hour when it gave none.
"""
from __future__ import annotations

import glob
import json
import os
import re
import threading
import time
from pathlib import Path
from typing import Optional

import config as cfgmod

NAM_GIO = "five_hour"
TUAN = "seven_day"
CANH_BAO = 50     # % from which the ring turns amber
SAT = 80          # % from which it turns red: close to the 5-hour or the weekly limit

HET_MAC_DINH_S = 3600   # how long "ran out" stays red when the CLI gave no reset time
# Engine names of the chat turn's limit detector (limit_learner) -> brain keys here.
BRAIN_THEO_ENGINE = {"claude-code": "claude", "codex": "codex", "grok-cli": "grok", "antigravity-cli": "agy"}
BRAINS = ("claude", "codex", "grok", "agy")
# Plain words a Grok or Antigravity error uses when the plan pushed back. Only checked for those two
# engines, after the shared detector found nothing: they print no fixed sentence for it.
_HET_RE = re.compile(r"usage\s+limit|rate[\s_-]?limit|too\s+many\s+requests|\b429\b|quota|resource[\s_]+exhausted"
                     r"|out\s+of\s+credits|limit\s+(?:reached|exceeded)", re.I)

_lock = threading.Lock()
_codex_cache: dict = {}   # path -> (mtime, snapshot) of the rollout last read


def _file() -> Path:
    return Path(cfgmod.STATE_DIR) / "plan_limits.json"


def _doc_file() -> dict:
    try:
        d = json.loads(_file().read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except Exception:   # noqa: BLE001 - missing or damaged: start over
        return {}


def _ghi_file(d: dict):
    p = _file()
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, p)
    except OSError:
        pass


def _so(x) -> Optional[float]:
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _cua_so(pct, resets_at) -> Optional[dict]:
    p = _so(pct)
    if p is None:
        return None
    r = _so(resets_at)
    return {"pct": max(0.0, min(100.0, p)), "resets_at": int(r) if r else 0}


def tu_claude(info: dict) -> dict:
    """`rate_limit_info` of a Claude Code rate_limit_event (the raw dict) -> {five_hour, seven_day, status}."""
    info = info if isinstance(info, dict) else {}
    out = {"status": str(info.get("status") or "")}
    uw = info.get("unifiedWindows")
    if isinstance(uw, dict):
        for k in (NAM_GIO, TUAN):
            w = uw.get(k)
            if isinstance(w, dict) and _so(w.get("utilization")) is not None:
                out[k] = _cua_so(_so(w.get("utilization")) * 100, w.get("resetsAt"))
    else:
        k = info.get("rateLimitType")
        u = _so(info.get("utilization"))
        if k in (NAM_GIO, TUAN) and u is not None:
            out[k] = _cua_so(u * 100, info.get("resetsAt"))
    return out


def tu_codex(snap: dict) -> dict:
    """Codex RateLimitSnapshot, camelCase (app-server) or snake_case (rollout) -> {five_hour, seven_day}."""
    snap = snap if isinstance(snap, dict) else {}
    snap = snap.get("rateLimits") if isinstance(snap.get("rateLimits"), dict) else snap
    out = {"status": "", "goi": str(snap.get("planType") or snap.get("plan_type") or "")}
    for ten, mac_dinh in (("primary", NAM_GIO), ("secondary", TUAN)):
        w = snap.get(ten)
        if not isinstance(w, dict):
            continue
        pct = w.get("usedPercent", w.get("used_percent"))
        phut = _so(w.get("windowDurationMins", w.get("window_minutes")))
        reset = w.get("resetsAt", w.get("resets_at"))
        if reset is None and _so(w.get("resets_in_seconds")) is not None:
            reset = time.time() + _so(w.get("resets_in_seconds"))
        k = mac_dinh if not phut else (NAM_GIO if phut <= 12 * 60 else TUAN)
        cs = _cua_so(pct, reset)
        if cs:
            out[k] = cs
    return out


def ghi(brain: str, snap: dict, now: float = None):
    """Store one brain's snapshot. A window the report leaves out keeps its last value."""
    if not any(k in snap for k in (NAM_GIO, TUAN)):
        return
    now = time.time() if now is None else now
    with _lock:
        d = _doc_file()
        cu = d.get(brain) if isinstance(d.get(brain), dict) else {}
        moi = dict(cu)
        moi.update({k: v for k, v in snap.items() if v not in (None, "")})
        moi["at"] = int(now)
        d[brain] = moi
        _ghi_file(d)


def la_het_han_muc(loi: str) -> bool:
    return bool(_HET_RE.search(str(loi or "")))


def ghi_het(engine: str, reset_epoch: float = 0.0, now: float = None):
    """The CLI just refused a turn for plan quota: the ring turns red until the reset (or an hour)."""
    brain = BRAIN_THEO_ENGINE.get(str(engine or ""), "")
    if not brain:
        return
    now = time.time() if now is None else now
    reset = float(reset_epoch or 0)
    reset = reset if reset > now else 0.0
    with _lock:
        d = _doc_file()
        b = dict(d.get(brain) if isinstance(d.get(brain), dict) else {})
        b["het"] = {"at": int(now), "reset": int(reset), "until": int(reset or now + HET_MAC_DINH_S)}
        d[brain] = b
        _ghi_file(d)


def ghi_claude(info: dict, now: float = None):
    ghi("claude", tu_claude(info), now)


def cai_vao_claude_sdk() -> bool:
    """Record Claude Code's rate_limit_event without editing claude_sdk_engine.py.

    That file is pinned by the native qualification evidence (improvement_claude.PROFILE_SOURCES,
    docs/superpowers/evidence/*-cli310.json), so any edit breaks its source hash. Its run loop calls
    the module-level `map_message` by name, so wrapping that name is enough: the wrapper stores the
    meter and returns exactly what the original returns. Idempotent; False when the SDK is absent."""
    try:
        import claude_sdk_engine as eng
    except Exception:  # noqa: BLE001 - no SDK: Claude Code runs another way, nothing to hook
        return False
    goc = eng.map_message
    if getattr(goc, "_plan_limits", False):
        return True

    def map_message(msg):
        if type(msg).__name__ == "RateLimitEvent":
            try:
                ghi_claude(getattr(msg.rate_limit_info, "raw", None) or {})
            except Exception:  # noqa: BLE001 - a meter must never break a turn
                pass
        return goc(msg)
    map_message._plan_limits = True
    map_message.__wrapped__ = goc
    eng.map_message = map_message
    return True


def ghi_codex(snap: dict, now: float = None):
    ghi("codex", tu_codex(snap), now)


def _codex_dir() -> str:
    return os.getenv("JAVIS_CODEX_SESSIONS_DIR") or os.path.expanduser("~/.codex/sessions")


def _ngay_moi_nhat(goc: str, n: int) -> list:
    """The newest `n` day folders under sessions/YYYY/MM/DD, without listing every file of every day."""
    out = []

    def con(p):
        try:
            return sorted((x for x in os.listdir(p) if x.isdigit()), reverse=True)
        except OSError:
            return []
    for y in con(goc):
        for m in con(os.path.join(goc, y)):
            for d in con(os.path.join(goc, y, m)):
                out.append(os.path.join(goc, y, m, d))
                if len(out) >= n:
                    return out
    return out


def _doc_rollout(path: str) -> Optional[dict]:
    """The last `rate_limits` of one rollout file, read from its tail only."""
    try:
        with open(path, "rb") as fh:
            fh.seek(0, os.SEEK_END)
            n = fh.tell()
            fh.seek(max(0, n - 262144))
            lines = fh.read().decode("utf-8", "replace").splitlines()
    except OSError:
        return None
    for line in reversed(lines):
        if '"rate_limits"' not in line:
            continue
        try:
            obj = json.loads(line)
        except ValueError:
            continue
        p = obj.get("payload") if isinstance(obj, dict) else None
        if isinstance(p, dict) and p.get("type") == "token_count" and isinstance(p.get("rate_limits"), dict):
            s = tu_codex(p["rate_limits"])
            if NAM_GIO in s or TUAN in s:
                return s
    return None


def quet_codex(now: float = None) -> Optional[dict]:
    """Newest Codex rollout files (Codex used inside or outside Javis) -> the latest snapshot, if newer
    than what is stored. Only the 3 newest files are opened, and an unchanged file is not reread."""
    now = time.time() if now is None else now
    try:
        files = []
        for ngay in _ngay_moi_nhat(_codex_dir(), 2):   # YYYY/MM/DD folders: only the newest two days
            files += glob.glob(os.path.join(ngay, "rollout-*.jsonl"))
        files = sorted(files, key=os.path.getmtime, reverse=True)[:3]
    except OSError:
        return None
    for f in files:
        try:
            mt = os.path.getmtime(f)
        except OSError:
            continue
        hit = _codex_cache.get(f)
        snap = hit[1] if hit and hit[0] == mt else _doc_rollout(f)
        _codex_cache[f] = (mt, snap)
        if snap:
            cu = (_doc_file().get("codex") or {}).get("at") or 0
            if mt > cu:
                ghi("codex", snap, mt)
            return snap
    return None


def muc(pct: float) -> str:
    return "bad" if pct >= SAT else ("warn" if pct >= CANH_BAO else "ok")


def doc(now: float = None) -> dict:
    """What the ring draws, per brain: each window's % (0 once its reset has passed), the worst level,
    and `het` while a refusal for plan quota is still in force. None when nothing is known yet."""
    now = time.time() if now is None else now
    d = _doc_file()
    out = {}
    for brain in BRAINS:
        b = d.get(brain)
        if not isinstance(b, dict):
            out[brain] = None
            continue
        r = {"at": int(b.get("at") or 0), "status": str(b.get("status") or ""), "goi": str(b.get("goi") or "")}
        for k in (NAM_GIO, TUAN):
            w = b.get(k)
            if isinstance(w, dict):
                moi = bool(w.get("resets_at")) and w["resets_at"] <= now
                r[k] = {"pct": 0 if moi else round(float(w.get("pct") or 0)),
                        "resets_at": 0 if moi else int(w.get("resets_at") or 0), "moi": moi}
        h = b.get("het")
        if isinstance(h, dict) and int(h.get("until") or 0) > now:
            r["het"] = {"at": int(h.get("at") or 0), "reset": int(h.get("reset") or 0)}
        ds = [r[k]["pct"] for k in (NAM_GIO, TUAN) if k in r]
        if not ds and "het" not in r:
            out[brain] = None
            continue
        r["max"] = max(ds) if ds else 0
        r["muc"] = muc(r["max"])
        con_han = not ds or not all(r[k]["moi"] for k in (NAM_GIO, TUAN) if k in r)
        if "het" in r:
            r["muc"], r["max"] = "bad", 100   # the plan refused a turn: red and full, whatever the last meter said
        elif con_han and r["status"] == "rejected":
            r["muc"] = "bad"       # the plan already refused a request in this window
        elif con_han and r["status"] == "allowed_warning" and r["muc"] == "ok":
            r["muc"] = "warn"
        out[brain] = r
    return out


_TEN_GOI = {"pro": "Pro", "max": "Max", "plus": "Plus", "team": "Team", "business": "Business",
            "enterprise": "Enterprise", "edu": "Edu", "free": "Free", "go": "Go"}


def ten_goi(raw: str) -> str:
    """"max" -> "Max", "chatgpt_plus" -> "Plus", "SuperGrok" stays. Empty stays empty: never a guess."""
    v = str(raw or "").strip()
    if not v:
        return ""
    k = v.lower().replace("chatgpt_", "").replace("claude_", "")
    if k in _TEN_GOI:
        return _TEN_GOI[k]
    return v if any(c.isupper() for c in v) else v.replace("_", " ").title()
