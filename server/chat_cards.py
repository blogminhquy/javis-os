"""Text form of a JAVIS_CARD block, for channels that cannot draw it (0.201.0).

The dashboard draws `<!-- JAVIS_CARD: {...} -->` as a chart, a row of number tiles or buttons
(dashboard/chat-card.js). Telegram, Zalo and the other text channels get this plain version instead:
a chart becomes one line per label, tiles become "label: value (delta)", buttons become a numbered
list the person answers with a number, the same way a JAVIS_ASK block degrades.
"""
from __future__ import annotations

import json

MAX_POINTS = 24
MAX_ITEMS = 6
MAX_BUTTONS = 4


def _fmt(v) -> str:
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    if isinstance(v, int):
        return f"{v:,}".replace(",", ".")
    return str(v)


def card_to_text(payload: str) -> str:
    """Plain text for one card; "" when the JSON is broken or the card is empty."""
    try:
        o = json.loads(payload)
    except Exception:
        return ""
    if not isinstance(o, dict):
        return ""
    title = str(o.get("title") or "").strip()
    lines = [f"**{title}**"] if title else []
    kind = o.get("type")
    if kind == "chart":
        labels = [str(x) for x in (o.get("labels") or [])][:MAX_POINTS]
        series = [s for s in (o.get("series") or []) if isinstance(s, dict)][:3]
        if not labels or not series:
            return ""
        names = [str(s.get("name") or "") for s in series]
        for i, lab in enumerate(labels):
            vals = []
            for s, name in zip(series, names):
                data = s.get("data") or []
                if i < len(data):
                    vals.append((f"{name} " if len(series) > 1 and name else "") + _fmt(data[i]))
            lines.append(f"- {lab}: " + " / ".join(vals))
    elif kind == "stats":
        items = [i for i in (o.get("items") or []) if isinstance(i, dict) and i.get("label")][:MAX_ITEMS]
        if not items:
            return ""
        for i in items:
            delta = f" ({i['delta']})" if i.get("delta") else ""
            lines.append(f"- {i['label']}: **{i.get('value', '')}**{delta}")
    elif kind == "buttons":
        btns = [b for b in (o.get("buttons") or []) if isinstance(b, dict) and str(b.get("label") or "").strip()][:MAX_BUTTONS]
        if not btns:
            return ""
        for n, b in enumerate(btns, 1):
            lines.append(f"{n}. {str(b['label']).strip()}")
    else:
        return ""
    return "\n".join(lines)
