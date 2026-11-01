"""The order brains are listed in (0.431.0).

Owner, 2026-11-01 (user report with a phone screenshot): the brain list came out as "1-..., 3-..., 4-..., 2-..." and
there was no way to change it. GET /brains sorted by FOLDER name while the list shows the display LABEL (0.219.0,
brain_label), so a brain renamed "2-PSC Advisor" kept its folder's place.

Now:
- The owner can set the order by hand (the brain picker's Reorder mode). It is stored in settings.json as a list of
  folder names under "brain_order", so every device that opens this Javis shows the same order.
- A brain not in that list (new, or never ordered) comes after the ordered ones, sorted by its label the way a person
  reads it: numbers by value ("2-..." before "10-..."), case and accents ignored.

The folder name is the key on purpose: it is the brain's address and never changes on a rename, so an order survives
renaming a brain.
"""
from __future__ import annotations

import re
import unicodedata

SETTINGS_KEY = "brain_order"
MAX_ITEMS = 500
MAX_NAME = 255


def _fold(s: str) -> str:
    """Lowercase, no accents ("Đ" -> "d"), so "Ảnh" sorts with "anh"."""
    s = unicodedata.normalize("NFD", str(s or "")).replace("đ", "d").replace("Đ", "d")
    return "".join(ch for ch in s if unicodedata.category(ch) != "Mn").lower()


def natural_key(label: str):
    """Sort key that reads numbers by value: "2-x" < "10-x"."""
    parts = re.split(r"(\d+)", _fold(label))
    return [(0, int(p), "") if p.isdigit() else (1, 0, p) for p in parts if p != ""]


def clean(order) -> list:
    """A list of distinct folder names, at most MAX_ITEMS, each a plain name (no path separators)."""
    out, seen = [], set()
    if not isinstance(order, (list, tuple)):
        return out
    for x in order:
        name = str(x or "").strip()
        if not name or len(name) > MAX_NAME or "/" in name or "\\" in name or name in (".", ".."):
            continue
        if name in seen:
            continue
        seen.add(name)
        out.append(name)
        if len(out) >= MAX_ITEMS:
            break
    return out


def sort(brains: list, order) -> list:
    """Brains (dicts with "name" = folder and "label") in the saved order, the rest by label."""
    pos = {n: i for i, n in enumerate(clean(order))}
    ranked = [b for b in brains if b.get("name") in pos]
    rest = [b for b in brains if b.get("name") not in pos]
    ranked.sort(key=lambda b: pos[b.get("name")])
    rest.sort(key=lambda b: (natural_key(b.get("label") or b.get("name") or ""), str(b.get("name") or "")))
    return ranked + rest
