"""Each vendor's best speech-to-text model, found by asking the vendor instead of a name written in Javis (2026-11-08).

Owner: "pick the vendor's best Whisper by itself when they upgrade their models, not a hand update in Javis, so it
scales and we never chase the vendors". The model names used to be constants (`whisper-large-v3`, `gpt-4o-transcribe`,
`gemini-2.5-flash`), so a vendor's new model reached nobody until someone edited the code. The chat model pickers
already list live models (main._fetch_provider_models); this does the same for the ears.

How a model is chosen, per vendor, from its own model list (refreshed once a day, in the background):
  - groq   : Whisper/transcribe models still active, not English-only, full size before turbo/distil, newest version.
  - openai : `*-transcribe` before `whisper-*`, full before mini, newest generation, the undated alias (which the vendor
             moves to its newest snapshot) before a dated one. Diarize and realtime models answer in another shape.
  - gemini : stable `gemini-*-flash` (fast, takes audio), newest version; previews, lite, live, tts and image are out.
The ChatGPT plan's ear needs nothing: its endpoint picks the model server side and upgrades with the plan.

Rails, because "newest" is not always "works":
  - SCORED BEFORE THE SWITCH (stt_gate): a model Javis has not judged yet hears the same short set of sentences as the
    model in use (Vietnamese, English, and Vietnamese with English terms) and is taken only when it is not worse. The
    verdict is kept in <STATE_DIR>/stt_models.json, so a restart does not score again, and a model that lost is not
    scored again for a month. When nothing can be measured (no Edge voice reachable) the model in use stays, unless
    the vendor no longer lists it;
  - a sentence never waits for the list: the first call uses the known default and refreshes in the background;
  - a discovered model the vendor refuses is retried once with the default; when the default then hears, the new model
    is set aside for a day (`mark_bad`) and the log says so;
  - the owner's own pin (`voice.stt_model` for Groq) always wins;
  - `JAVIS_NO_STT_MODEL_DISCOVERY=1` turns discovery off (the test runner sets it, so no test calls a vendor).
Ranking is by the vendor's own naming (version numbers, mini/turbo/preview words), which vendors have kept for years;
whether the newest one hears Vietnamese mixed with English at least as well is measured by stt_gate, not guessed.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import sys
import time
from pathlib import Path

DEFAULTS = {"groq": "whisper-large-v3", "openai": "gpt-4o-transcribe", "gemini": "gemini-2.5-flash"}
VENDORS = tuple(DEFAULTS)
TTL = 24 * 3600              # a vendor's model list is asked again after a day
RETRY_AFTER_FAIL = 3600      # the list could not be read: try again in an hour, keep what we had
BAD_TTL = 24 * 3600          # a discovered model the vendor refused is left aside this long
REJECT_TTL = 30 * 24 * 3600  # a model that scored worse than the one in use is not scored again this long
GATE_RETRY = 3600            # nothing could be measured: try the score again in an hour
LIST_TIMEOUT = 15.0
OFF_ENV = "JAVIS_NO_STT_MODEL_DISCOVERY"

_CACHE: dict = {}            # (vendor, key fingerprint) -> {"model": str, "next": epoch}
_BAD: dict = {}              # (vendor, model) -> epoch until which it is not used
_VERDICTS: dict = {}         # vendor -> {"accepted": model, "rejected": {model: until}, "last": scores}, on disk
_LOADED = [False]
_TASKS: set = set()          # running refreshes (a reference, so the loop does not drop them)
_RUNNING: set = set()        # (vendor, key fingerprint) being refreshed


def _fp(key: str) -> str:
    return hashlib.sha256(str(key or "").encode("utf-8")).hexdigest()[:12]


# ---------------------------------------------------------------------------
# Ranking (pure: a vendor's model list in, one model id or "" out)
# ---------------------------------------------------------------------------
_DATE = re.compile(r"-(?:20\d{2}-\d{2}-\d{2}|20\d{6}|\d{4})(?=$|-)")   # -2025-03-20, -20250320, -0125
_REVISION = re.compile(r"-\d{3}$")                                       # gemini-2.0-flash-001
_NUM = re.compile(r"\d+")


def _version(mid: str) -> tuple:
    """(major, minor, ...) from an id, dates and revision suffixes left out: "gpt-4o-transcribe" -> (4,),
    "gemini-2.5-flash" -> (2, 5), "whisper-large-v3-turbo" -> (3,)."""
    core = _REVISION.sub("", _DATE.sub("", str(mid or "").lower()))
    return tuple(int(n) for n in _NUM.findall(core)[:3])


def _dated(mid: str) -> bool:
    low = str(mid or "").lower()
    return bool(_DATE.search(low) or _REVISION.search(low))


def _has(low: str, words) -> bool:
    return any(re.search(r"(^|[-_.])" + re.escape(w) + r"($|[-_.\d])", low) for w in words)


def rank_groq(models: list) -> str:
    cands = []
    for m in models or []:
        mid = str((m or {}).get("id") or "")
        low = mid.lower()
        if not ("whisper" in low or "transcribe" in low) or (m or {}).get("active") is False:
            continue
        if low.endswith("-en") or _has(low, ("en", "distil", "translate")):
            continue           # English only: a Vietnamese sentence would come back translated or lost
        light = _has(low, ("turbo", "mini", "lite", "small", "base", "tiny"))
        cands.append(((not light, _version(mid), int((m or {}).get("created") or 0)), mid))
    return max(cands)[1] if cands else ""


def rank_openai(models: list) -> str:
    cands = []
    for m in models or []:
        mid = str((m or {}).get("id") or "")
        low = mid.lower()
        transcribe = "transcribe" in low
        if not (transcribe or low.startswith("whisper")):
            continue
        if _has(low, ("diarize", "realtime", "tts", "translate", "preview")):
            continue           # another answer shape, or not a plain transcription model
        light = _has(low, ("mini", "nano", "lite", "turbo"))
        cands.append(((transcribe, not light, _version(mid), not _dated(mid), int((m or {}).get("created") or 0)),
                      mid))
    return max(cands)[1] if cands else ""


def rank_gemini(models: list) -> str:
    cands = []
    for m in models or []:
        mid = str((m or {}).get("name") or (m or {}).get("id") or "").split("/")[-1]
        low = mid.lower()
        methods = (m or {}).get("supportedGenerationMethods")
        if methods is not None and "generateContent" not in methods:
            continue
        if not low.startswith("gemini-") or not _has(low, ("flash",)):
            continue
        if _has(low, ("preview", "exp", "experimental", "lite", "live", "tts", "image", "audio", "thinking", "latest",
                      "8b", "native")):
            continue           # not stable, not the full flash, or not a plain text answer
        cands.append(((_version(mid), not _dated(mid), -len(mid)), mid))
    return max(cands)[1] if cands else ""


RANKERS = {"groq": rank_groq, "openai": rank_openai, "gemini": rank_gemini}


# ---------------------------------------------------------------------------
# Asking the vendor
# ---------------------------------------------------------------------------
async def _list_models(vendor: str, key: str) -> list:
    import httpx
    async with httpx.AsyncClient(timeout=httpx.Timeout(LIST_TIMEOUT)) as c:
        if vendor == "groq":
            r = await c.get("https://api.groq.com/openai/v1/models", headers={"Authorization": f"Bearer {key}"})
        elif vendor == "openai":
            r = await c.get("https://api.openai.com/v1/models", headers={"Authorization": f"Bearer {key}"})
        else:
            r = await c.get("https://generativelanguage.googleapis.com/v1beta/models",
                            headers={"x-goog-api-key": key}, params={"pageSize": 1000})
        if r.status_code != 200:
            raise RuntimeError(f"{vendor} models HTTP {r.status_code}")
        d = r.json()
    rows = d.get("models") if vendor == "gemini" else d.get("data")
    return [x for x in (rows or []) if isinstance(x, dict)]


def _state_file() -> Path:
    import config as cfgmod
    return Path(cfgmod.STATE_DIR) / "stt_models.json"


def _verdicts() -> dict:
    if not _LOADED[0]:
        _LOADED[0] = True
        try:
            d = json.loads(_state_file().read_text(encoding="utf-8"))
            if isinstance(d, dict):
                _VERDICTS.update({k: v for k, v in d.items() if k in DEFAULTS and isinstance(v, dict)})
        except (OSError, ValueError):
            pass
    return _VERDICTS


def _save() -> None:
    try:
        f = _state_file()
        tmp = f.with_suffix(".tmp")
        tmp.write_text(json.dumps(_VERDICTS, ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(tmp, f)
    except OSError as e:
        print(f"[stt models] save: {e}", file=sys.stderr)


def accepted(vendor: str) -> str:
    """The model that last won (or needed no) scoring for `vendor`, "" when none yet."""
    return str((_verdicts().get(vendor) or {}).get("accepted") or "")


def _rejected(vendor: str, model: str) -> bool:
    until = ((_verdicts().get(vendor) or {}).get("rejected") or {}).get(model)
    return bool(until and float(until) > time.time())


def _ids(vendor: str, models: list) -> set:
    return {str(m.get("name") or m.get("id") or "").split("/")[-1] for m in models}


async def refresh(vendor: str, key: str) -> str:
    """Ask `vendor` for its models now; a newer ear model is scored against the one in use (stt_gate) and taken only
    when it is not worse. Returns the model in use afterwards."""
    slot = (vendor, _fp(key))
    in_use = (_CACHE.get(slot) or {}).get("model") or accepted(vendor) or DEFAULTS[vendor]
    try:
        models = await _list_models(vendor, key)
    except Exception as e:  # noqa: BLE001 - no list means the model we had, never a lost sentence
        print(f"[stt models] {vendor}: {type(e).__name__}: {str(e)[:160]}", file=sys.stderr)
        _CACHE[slot] = {"model": in_use, "next": time.time() + RETRY_AFTER_FAIL}
        return in_use
    picked = RANKERS[vendor](models)
    nxt = time.time() + TTL
    v = _verdicts().setdefault(vendor, {})
    if not picked or picked == in_use or _rejected(vendor, picked):
        model = in_use
    else:
        import stt_gate
        try:
            g = await stt_gate.compare(vendor, key, in_use, picked)
        except Exception as e:  # noqa: BLE001 - a scoring that breaks decides nothing
            print(f"[stt gate] {vendor}: {type(e).__name__}: {str(e)[:160]}", file=sys.stderr)
            g = {"ok": None, "reason": "error"}
        last = {"at": int(time.time()), "in_use": in_use, "candidate": picked, "reason": g.get("reason"),
                "scores": {in_use: g.get("current") or {}, picked: g.get("candidate") or {}}}
        if g.get("ok") is True:
            model = picked
            v.update(accepted=picked, last=dict(last, result="switch"))
        elif g.get("ok") is False:
            model = in_use
            v.setdefault("rejected", {})[picked] = int(time.time() + REJECT_TTL)
            v["last"] = dict(last, result="keep")
        elif in_use not in _ids(vendor, models):
            model = picked             # nothing measured, but the vendor no longer lists the model in use
            v.update(accepted=picked, last=dict(last, result="switch_unmeasured"))
        else:
            model, nxt = in_use, time.time() + GATE_RETRY
            v["last"] = dict(last, result="unmeasured")
        _save()
    _CACHE[slot] = {"model": model, "next": nxt}
    if model != in_use:
        print(f"[stt models] {vendor}: {in_use} -> {model}", file=sys.stderr)
    return model


def _spawn(vendor: str, key: str) -> None:
    slot = (vendor, _fp(key))
    if slot in _RUNNING:
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return

    async def run():
        try:
            await refresh(vendor, key)
        finally:
            _RUNNING.discard(slot)

    _RUNNING.add(slot)
    task = loop.create_task(run())
    _TASKS.add(task)
    task.add_done_callback(_TASKS.discard)


def is_bad(vendor: str, model: str) -> bool:
    until = _BAD.get((vendor, model))
    return bool(until and until > time.time())


def best(vendor: str, key: str, pinned: str = "") -> str:
    """The model `vendor`'s ear should use now. Never waits on the network: a stale or missing answer is refreshed in
    the background and the known default (or the last pick) is used meanwhile."""
    if pinned:
        return pinned
    default = DEFAULTS.get(vendor, "")
    if not key or vendor not in RANKERS:
        return default
    slot = (vendor, _fp(key))
    c = _CACHE.get(slot)
    if (not c or time.time() >= c.get("next", 0)) and os.environ.get(OFF_ENV) != "1":
        _spawn(vendor, key)
    model = (c or {}).get("model") or accepted(vendor) or default
    return default if is_bad(vendor, model) else model


def mark_bad(vendor: str, model: str) -> None:
    """A discovered model the vendor refused while its default worked: leave it aside for a day."""
    if model and model != DEFAULTS.get(vendor):
        _BAD[(vendor, model)] = time.time() + BAD_TTL
        print(f"[stt models] {vendor}: {model} refused, back to {DEFAULTS.get(vendor)} for a day", file=sys.stderr)


async def hear_with(vendor: str, key: str, pinned: str, run):
    """Run one ear with the best model: `run(model)` -> dict like stt.groq_nghe. A discovered model that fails is tried
    once more with the default, and set aside when the default hears; a pinned or default model is never retried."""
    model = best(vendor, key, pinned)
    res = await run(model)
    default = DEFAULTS.get(vendor, "")
    if pinned or res.get("ok") or res.get("ly_do") != "loi" or not default or model == default:
        return res
    again = await run(default)
    if again.get("ok") or again.get("ly_do") == "khong_nghe_ro":
        mark_bad(vendor, model)
        return again
    return res


def current() -> dict:
    """{vendor: model in use} for the keys seen so far (the settings page and logs)."""
    out = {}
    for (vendor, _k), c in _CACHE.items():
        m = c.get("model") or accepted(vendor) or DEFAULTS.get(vendor, "")
        out[vendor] = DEFAULTS.get(vendor, "") if is_bad(vendor, m) else m
    return out
