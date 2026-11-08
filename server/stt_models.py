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
  - a sentence never waits for the list: the first call uses the known default and refreshes in the background;
  - a discovered model the vendor refuses is retried once with the default; when the default then hears, the new model
    is set aside for a day (`mark_bad`) and the log says so;
  - the owner's own pin (`voice.stt_model` for Groq) always wins;
  - `JAVIS_NO_STT_MODEL_DISCOVERY=1` turns discovery off (the test runner sets it, so no test calls a vendor).
Ranking is by the vendor's own naming (version numbers, mini/turbo/preview words), which vendors have kept for years;
which model hears Vietnamese mixed with English BEST is measured by tools/stt_bench, not guessed here.
"""
from __future__ import annotations

import asyncio
import hashlib
import os
import re
import sys
import time

DEFAULTS = {"groq": "whisper-large-v3", "openai": "gpt-4o-transcribe", "gemini": "gemini-2.5-flash"}
VENDORS = tuple(DEFAULTS)
TTL = 24 * 3600              # a vendor's model list is asked again after a day
RETRY_AFTER_FAIL = 3600      # the list could not be read: try again in an hour, keep what we had
BAD_TTL = 24 * 3600          # a discovered model the vendor refused is left aside this long
LIST_TIMEOUT = 15.0
OFF_ENV = "JAVIS_NO_STT_MODEL_DISCOVERY"

_CACHE: dict = {}            # (vendor, key fingerprint) -> {"model": str, "next": epoch}
_BAD: dict = {}              # (vendor, model) -> epoch until which it is not used
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


async def refresh(vendor: str, key: str) -> str:
    """Ask `vendor` for its models now and remember the best ear model. Returns it, "" when none was found."""
    slot = (vendor, _fp(key))
    old = (_CACHE.get(slot) or {}).get("model") or ""
    try:
        picked = RANKERS[vendor](await _list_models(vendor, key))
    except Exception as e:  # noqa: BLE001 - no list means the model we had, never a lost sentence
        print(f"[stt models] {vendor}: {type(e).__name__}: {str(e)[:160]}", file=sys.stderr)
        _CACHE[slot] = {"model": old, "next": time.time() + RETRY_AFTER_FAIL}
        return old
    _CACHE[slot] = {"model": picked, "next": time.time() + TTL}
    if picked and picked != old:
        print(f"[stt models] {vendor}: {old or DEFAULTS[vendor]} -> {picked}", file=sys.stderr)
    return picked


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
    model = (c or {}).get("model") or default
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
        m = c.get("model") or DEFAULTS.get(vendor, "")
        out[vendor] = DEFAULTS.get(vendor, "") if is_bad(vendor, m) else m
    return out
