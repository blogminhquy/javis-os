"""compass_store.py - the Investment compass page's outlook, refreshed each month with an owner review step.

The page ships with a curated file (dashboard/compass/data.json): stances per asset class, the cycle clock, factors,
sentiment, allocations, calendar and sources. Macro numbers (Fed, State Bank, inflation, GDP, foreign flows, property
reports) come out monthly, so updates work like the Real estate page:

  1. A monthly reminder (created from the page) asks Javis to research the latest numbers and write a DRAFT through
     the `javis_compass_draft` tool. Javis never publishes on its own.
  2. The page shows a "draft waiting" banner; the owner previews it and approves or discards it.
  3. Approving makes the draft the current outlook (STATE_DIR/compass/data.json) and keeps the previous version in
     STATE_DIR/compass/history/, so nothing is lost.

`validate()` keeps a draft from breaking the page: every top-level field keeps its JSON type, asset ids stay the seven
the page colours, stances and scores stay in range, factor impacts name real assets, profile weights add to 100.
"""
from __future__ import annotations

import copy
import json
import os
import shutil
import time
from pathlib import Path

BUNDLED = Path(__file__).resolve().parent.parent / "dashboard" / "compass" / "data.json"
MAX_BYTES = 2 * 1024 * 1024
ASSET_IDS = ("re_vn", "stocks_vn", "stocks_world", "gold", "crypto", "savings", "usd")
STANCES = ("accumulate", "hold", "reduce")
OPS = ("<", "<=", ">", ">=", "==", "!=", "in")


def _dir() -> Path:
    try:
        import config
        base = Path(config.STATE_DIR)
    except Exception:
        base = Path(os.getenv("JAVIS_STATE_DIR", str(Path(__file__).parent)))
    d = base / "compass"
    (d / "history").mkdir(parents=True, exist_ok=True)
    return d


def _read(p: Path):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def _write(p: Path, data) -> None:
    raw = json.dumps(data, ensure_ascii=False, indent=1)
    if len(raw.encode("utf-8")) > MAX_BYTES:
        raise ValueError("data too large")
    tmp = p.with_suffix(".tmp")
    tmp.write_text(raw, encoding="utf-8")
    os.replace(tmp, p)


def bundled() -> dict:
    return _read(BUNDLED) or {"assets": []}


def current() -> tuple[dict, str, float]:
    """(data, source, updated_at). source is "updated" once an approved update exists, else "bundled"."""
    p = _dir() / "data.json"
    d = _read(p)
    if isinstance(d, dict) and d.get("assets"):
        return d, "updated", p.stat().st_mtime
    return bundled(), "bundled", 0.0


def draft() -> dict | None:
    d = _read(_dir() / "draft.json")
    return d if isinstance(d, dict) and isinstance(d.get("data"), dict) else None


def draft_meta() -> dict | None:
    d = draft()
    if not d:
        return None
    return {"note": d.get("note") or "", "at": d.get("at") or 0, "changed": d.get("changed") or [],
            "updated": (d.get("data") or {}).get("updated") or ""}


def _types_match(a, b) -> bool:
    if a is None or b is None:
        return True
    if isinstance(a, bool) or isinstance(b, bool):
        return isinstance(a, bool) and isinstance(b, bool)
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return True
    return type(a) is type(b)


def _list(v) -> list:
    return v if isinstance(v, list) else []


def _is_int(v) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def validate(new: dict, old: dict | None = None) -> list:
    """Problems that would break the page; empty list when the outlook is safe to store."""
    if not isinstance(new, dict):
        return ["data must be a JSON object"]
    errs = []
    ref = old if isinstance(old, dict) else bundled()
    for k, v in ref.items():
        if k not in new:
            errs.append(f"missing field '{k}'")
        elif not _types_match(new[k], v):
            errs.append(f"field '{k}' must stay a {type(v).__name__}")
    assets = new.get("assets") if isinstance(new.get("assets"), list) else []
    ids = [a.get("id") for a in assets if isinstance(a, dict)]
    if sorted(ids) != sorted(ASSET_IDS):
        errs.append("assets must be exactly: " + ", ".join(ASSET_IDS))
    old_assets = {a.get("id"): a for a in (ref.get("assets") or []) if isinstance(a, dict)}
    for a in assets:
        if not isinstance(a, dict):
            continue
        aid = a.get("id")
        if a.get("stance") not in STANCES:
            errs.append(f"{aid}: stance must be accumulate, hold or reduce")
        if not _is_int(a.get("score")) or not -2 <= a["score"] <= 2:
            errs.append(f"{aid}: score must be a whole number from -2 to 2")
        for k, v in (old_assets.get(aid) or {}).items():
            if k in a and not _types_match(a[k], v):
                errs.append(f"{aid}: field '{k}' must stay a {type(v).__name__}")
        for lst in ("enter_when", "exit_when"):
            for s in _list(a.get(lst)):
                live = isinstance(s, dict) and s.get("live")
                if live and (not isinstance(live, dict) or live.get("op") not in OPS or not str(live.get("ref") or "")):
                    errs.append(f"{aid}: {lst} has a live check without a valid ref/op")
    for f in _list(new.get("factors")):
        imp = f.get("impact") if isinstance(f, dict) else None
        if not isinstance(imp, dict) or any(k not in ASSET_IDS or not _is_int(v) or abs(v) > 2 for k, v in imp.items()):
            errs.append(f"factor {f.get('id') if isinstance(f, dict) else '?'}: impact must map asset ids to -2..2")
    for p in _list(new.get("profiles")):
        for k in ("now", "neutral"):
            w = (p or {}).get(k) if isinstance(p, dict) else None
            if not isinstance(w, dict) or sum(v for v in w.values() if isinstance(v, (int, float))) != 100 \
                    or any(x not in ASSET_IDS for x in w):
                errs.append(f"profile {p.get('id') if isinstance(p, dict) else '?'}: '{k}' weights must use asset ids and add to 100")
    for e in _list(new.get("calendar")):
        if not isinstance(e, dict) or len(str(e.get("date") or "")) != 10:
            errs.append("calendar dates must be YYYY-MM-DD")
            break
    for s in _list(new.get("sources")):
        if not isinstance(s, dict) or not str(s.get("url") or "").startswith(("http://", "https://")):
            errs.append("every source needs an http(s) url")
            break
    raw = json.dumps(new, ensure_ascii=False)
    if "—" in raw or "–" in raw:
        errs.append("no long dashes (U+2013/U+2014), use '-'")
    return errs[:20]


def set_fields(fields, note: str = "", updated: str = "", as_of: str = "") -> dict:
    """Merge changed top-level fields into the draft (started from the current outlook).

    `assets` may list only the assets that changed, each with only its changed fields; they merge by id.
    Every other top-level key replaces the old value whole. Returns {"ok", "errors"?, "draft"}."""
    if isinstance(fields, str):
        try:
            fields = json.loads(fields)
        except Exception as e:
            return {"ok": False, "errors": [f"fields is not valid JSON: {e}"]}
    if not isinstance(fields, dict) or not fields:
        return {"ok": False, "errors": ["fields must be a non-empty object"]}
    d = draft()
    base = copy.deepcopy(d["data"]) if d else copy.deepcopy(current()[0])
    old = copy.deepcopy(base)
    changed = list((d or {}).get("changed") or [])
    for k, v in fields.items():
        if k == "assets" and isinstance(v, list):
            by_id = {a.get("id"): i for i, a in enumerate(base.get("assets") or []) if isinstance(a, dict)}
            for a in v:
                if not isinstance(a, dict) or a.get("id") not in by_id:
                    return {"ok": False, "errors": [f"unknown asset '{(a or {}).get('id') if isinstance(a, dict) else a}'; ids: "
                                                    + ", ".join(ASSET_IDS)]}
                i = by_id[a["id"]]
                base["assets"][i] = {**base["assets"][i], **a}
                changed.append("asset:" + a["id"])
        else:
            base[k] = v
            changed.append(k)
    if updated:
        base["updated"] = str(updated)[:10]
    if as_of:
        base["as_of"] = str(as_of)[:20]
    errs = validate(base, old)
    if errs:
        return {"ok": False, "errors": errs}
    notes = [x for x in [((d or {}).get("note") or "").strip(), str(note or "").strip()] if x]
    _write(_dir() / "draft.json", {"data": base, "note": "\n".join(dict.fromkeys(notes))[:4000], "at": time.time(),
                                   "changed": list(dict.fromkeys(changed))})
    return {"ok": True, "draft": draft_meta()}


def approve() -> dict:
    d = draft()
    if not d:
        return {"ok": False, "error": "no draft"}
    p = _dir() / "data.json"
    if p.exists():
        shutil.copy2(p, _dir() / "history" / f"data-{time.strftime('%Y%m%d-%H%M%S')}.json")
    elif BUNDLED.exists():
        shutil.copy2(BUNDLED, _dir() / "history" / "data-bundled.json")
    _write(p, d["data"])
    (_dir() / "draft.json").unlink(missing_ok=True)
    return {"ok": True}


def discard() -> dict:
    (_dir() / "draft.json").unlink(missing_ok=True)
    return {"ok": True}


def history() -> list:
    return sorted((f.name for f in (_dir() / "history").glob("data-*.json")), reverse=True)[:20]


def summary(data: dict, lang: str = "vi") -> str:
    """Compact text for the model: the headline, each asset's stance and score, factors and sources."""
    def pick(v):
        return (v.get(lang) or v.get("vi") or v.get("en") or "") if isinstance(v, dict) else (v or "")
    lines = [f"Nhận định {data.get('as_of') or '-'} (cập nhật {data.get('updated') or '-'}): {pick(data.get('verdict'))}"]
    for m in (data.get("clock") or {}).get("markers") or []:
        lines.append(f"- Chu kỳ {pick(m.get('name'))}: {m.get('phase')}")
    for a in data.get("assets") or []:
        lines.append(f"- {a.get('id')} ({pick(a.get('name'))}): {a.get('stance')} {a.get('score'):+d} | {pick(a.get('one_liner'))}"
                     if _is_int(a.get("score")) else f"- {a.get('id')}: {a.get('stance')}")
    fs = data.get("factors") or []
    if fs:
        lines.append("Yếu tố: " + "; ".join(f"{pick(f.get('name'))} = {pick(f.get('reading'))} ({f.get('as_of') or '-'})" for f in fs[:20]))
    srcs = [s.get("name") for s in (data.get("sources") or []) if isinstance(s, dict) and s.get("name")]
    if srcs:
        lines.append(f"Nguồn ({len(srcs)}): " + ", ".join(srcs[:8]) + ("..." if len(srcs) > 8 else ""))
    return "\n".join(lines)
