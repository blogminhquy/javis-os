"""realestate_store.py - the Real estate page's data, updated each quarter with an owner review step.

The page ships with a curated file (dashboard/realestate/data.json). Housing numbers come out as quarterly reports
(CBRE, DKRA, VARS, Savills...), not as an API, so updates work like this:

  1. A quarterly reminder (created from the page) asks Javis to research the new reports and write a DRAFT through
     the `javis_realestate_draft` tool. Javis never publishes on its own.
  2. The page shows a "draft waiting" banner; the owner previews it and approves or discards it.
  3. Approving makes the draft the current data (STATE_DIR/realestate/data.json) and keeps the previous version in
     STATE_DIR/realestate/history/, so nothing is lost.

`validate_region()` keeps a draft from breaking the page: a region must keep every top-level field the current
region has, with the same JSON type.
"""
from __future__ import annotations

import copy
import json
import os
import shutil
import time
from pathlib import Path

BUNDLED = Path(__file__).resolve().parent.parent / "dashboard" / "realestate" / "data.json"
MAX_BYTES = 3 * 1024 * 1024


def _dir() -> Path:
    try:
        import config
        base = Path(config.STATE_DIR)
    except Exception:
        base = Path(os.getenv("JAVIS_STATE_DIR", str(Path(__file__).parent)))
    d = base / "realestate"
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


def current() -> tuple[dict, str, float]:
    """(data, source, updated_at). source is "updated" once an approved update exists, else "bundled"."""
    p = _dir() / "data.json"
    d = _read(p)
    if isinstance(d, dict) and d.get("regions"):
        return d, "updated", p.stat().st_mtime
    return (_read(BUNDLED) or {"regions": []}), "bundled", 0.0


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


def validate_region(new: dict, old: dict | None) -> list:
    """Problems that would break the page; empty list when the region is safe to store."""
    errs = []
    if not isinstance(new, dict):
        return ["region must be a JSON object"]
    if not str(new.get("id") or "").strip():
        errs.append("region needs an id")
    if old:
        for k, v in old.items():
            if k not in new:
                errs.append(f"missing field '{k}'")
            elif not _types_match(new[k], v):
                errs.append(f"field '{k}' must stay a {type(v).__name__}")
    return errs


def set_region(region_id: str, region, note: str = "", updated: str = "") -> dict:
    """Write one region into the draft (started from the current data). Returns {"ok", "errors"?, "draft"}."""
    if isinstance(region, str):
        try:
            region = json.loads(region)
        except Exception as e:
            return {"ok": False, "errors": [f"region is not valid JSON: {e}"]}
    region_id = str(region_id or (region or {}).get("id") or "").strip()
    if isinstance(region, dict):
        region = dict(region)
        region["id"] = region_id
    d = draft()
    base = copy.deepcopy(d["data"]) if d else copy.deepcopy(current()[0])
    regs = base.setdefault("regions", [])
    idx = next((i for i, r in enumerate(regs) if r.get("id") == region_id), None)
    old = regs[idx] if idx is not None else (regs[0] if regs else None)
    if idx is not None and isinstance(region, dict):
        # Only the fields that changed need to be sent; the rest of the region is kept as it is.
        region = {**regs[idx], **region}
    errs = validate_region(region, old)
    if errs:
        return {"ok": False, "errors": errs[:20]}
    if idx is None:
        regs.append(region)
    else:
        regs[idx] = region
    if updated:
        base["updated"] = str(updated)[:20]
    changed = list(dict.fromkeys(((d or {}).get("changed") or []) + [region_id]))
    notes = [x for x in [((d or {}).get("note") or "").strip(), str(note or "").strip()] if x]
    _write(_dir() / "draft.json", {"data": base, "note": "\n".join(dict.fromkeys(notes))[:4000], "at": time.time(),
                                   "changed": changed})
    return {"ok": True, "draft": draft_meta()}


def approve() -> dict:
    d = draft()
    if not d:
        return {"ok": False, "error": "no draft"}
    p = _dir() / "data.json"
    if p.exists():
        shutil.copy2(p, _dir() / "history" / f"data-{time.strftime('%Y%m%d-%H%M%S')}.json")
    else:
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
    """Compact text for the model: each region's period, headline numbers and sources."""
    def pick(v):
        return v.get(lang) or v.get("vi") or v.get("en") if isinstance(v, dict) else v
    lines = [f"Dữ liệu cập nhật: {data.get('updated') or '-'}"]
    for r in data.get("regions") or []:
        kp = r.get("kpis") or r.get("snapshot") or []
        nums = []
        if isinstance(kp, list):
            for k in kp[:6]:
                if isinstance(k, dict):
                    nums.append(f"{pick(k.get('label'))}: {pick(k.get('value'))} {pick(k.get('unit')) or ''}".strip()
                                + (f" ({pick(k.get('change'))})" if k.get("change") else ""))
        srcs = [s.get("name") or s.get("source") or "" for s in (r.get("sources") or []) if isinstance(s, dict)]
        lines.append(f"- {r.get('id')} ({pick(r.get('name'))}), kỳ {r.get('as_of')}: " + "; ".join(nums)
                     + (f" | nguồn: {', '.join(x for x in srcs[:6] if x)}" if srcs else ""))
    return "\n".join(lines)
