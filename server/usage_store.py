"""
usage_store.py - Kho đếm token/chi phí do CHÍNH JAVIS đo (đa nhà cung cấp).

Vì Javis nhìn thấy token in/out trong mọi phản hồi (Claude Code CLI, Codex, OpenRouter, OpenAI,
Anthropic), đây là con số usage đồng nhất - KHÔNG phụ thuộc provider có lộ hạn mức hay không.
KHÁC với "hạn mức tài khoản" (gói thuê bao) mà đa số provider không cho lấy qua API.

Lưu STATE_DIR/usage.json: { "days": { "YYYY-MM-DD": { "<provider>|<model>": {in,out,turns,cost} } },
                            "total": { "<provider>|<model>": {in,out,turns,cost} } }
- Gộp theo NGÀY (giữ 30 ngày gần nhất) + TỔNG tích luỹ.
- cost chỉ ghi khi provider trả về chi phí thật (vd Claude Code CLI total_cost_usd); còn lại 0
  (chỉ đếm token) - KHÔNG tự đoán giá vì bảng giá mỗi model khác nhau, dễ sai.
"""
from __future__ import annotations

import json
import threading
from datetime import datetime, timezone, timedelta

import quota_scheduler          # sổ cái TPM dùng chung (không phụ thuộc ngược, xem module đó)
from config import STATE_DIR

_PATH = STATE_DIR / "usage.json"
_EVENTS_PATH = STATE_DIR / "usage-events.jsonl"   # append-only, forward-log cho dashboard token
_LOCK = threading.Lock()
_KEEP_DAYS = 30


def _today() -> str:
    return datetime.now(timezone(timedelta(hours=7))).strftime("%Y-%m-%d")


def _append_event(provider: str, model: str, tin: int, tout: int, cost: float) -> None:
    """Ghi them 1 dong vao usage-events.jsonl (append-only) cho indexer dashboard token doc.
    Best-effort: loi thi bo qua, KHONG duoc lam hong luong chat. Nhanh API (openrouter/openai/
    anthropic) khong co log tho nen day la nguon DUY NHAT cho chung; claude/codex indexer lay
    tu log tho nen dong claude/codex o day chi bi indexer bo qua (tranh dem trung)."""
    try:
        now = datetime.now(timezone.utc)
        line = json.dumps({"ts": int(now.timestamp()), "day": _today(),
                           "provider": provider or "?", "model": model or "?",
                           "in": int(tin or 0), "out": int(tout or 0), "cost": float(cost or 0.0)},
                          ensure_ascii=False)
        with open(_EVENTS_PATH, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except Exception:
        pass


def _load() -> dict:
    try:
        if _PATH.exists():
            d = json.loads(_PATH.read_text(encoding="utf-8"))
            if isinstance(d, dict):
                d.setdefault("days", {})
                d.setdefault("total", {})
                return d
    except Exception:
        pass
    return {"days": {}, "total": {}}


def _save(d: dict) -> None:
    try:
        tmp = _PATH.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
        tmp.replace(_PATH)
    except Exception:
        pass


def record(provider: str, model: str, tin=0, tout=0, cost=0.0) -> None:
    """Cộng dồn 1 lượt vào ngày hôm nay + tổng. Bỏ qua nếu không có token nào (lượt lỗi)."""
    tin, tout = int(tin or 0), int(tout or 0)
    cost = float(cost or 0.0)
    if tin <= 0 and tout <= 0 and cost <= 0:
        return
    key = f"{provider or '?'}|{model or '?'}"
    with _LOCK:
        d = _load()
        day = _today()
        for bucket in (d["days"].setdefault(day, {}), d["total"]):
            e = bucket.setdefault(key, {"in": 0, "out": 0, "turns": 0, "cost": 0.0})
            e["in"] += tin
            e["out"] += tout
            e["turns"] += 1
            e["cost"] += cost
        for old in sorted(d["days"])[:-_KEEP_DAYS]:   # dọn ngày cũ
            d["days"].pop(old, None)
        _save(d)
    _append_event(provider, model, tin, tout, cost)   # forward-log rieng (khong prune) cho dashboard token
    # Sổ cái TPM dùng chung. Đây là điểm móc PHỔ QUÁT: mọi đường gọi model (chat, loop,
    # task nền, nhắc hẹn, Telegram, CLI, Codex) đều đi qua record(), trong khi admit_quota
    # chỉ nhìn thấy bốn đường canary. Thiếu móc này thì hạn mức của TÀI KHOẢN bị đốt vô hình
    # và canary tưởng còn nhiều token hơn thực tế.
    quota_scheduler.observe(provider, model, tin + tout)


def _rollup(bucket: dict) -> dict:
    """Gộp các key <provider>|<model> thành list + tổng cộng."""
    items, tot = [], {"in": 0, "out": 0, "turns": 0, "cost": 0.0}
    for key, e in sorted(bucket.items(), key=lambda kv: -(kv[1]["in"] + kv[1]["out"])):
        prov, _, model = key.partition("|")
        items.append({"provider": prov, "model": model, **e})
        for k in tot:
            tot[k] += e.get(k, 0)
    return {"items": items, "total": tot}


def daily(n: int = 14) -> list:
    """Chuỗi n ngày gần nhất (cũ -> mới) để vẽ đồ thị, lấp cả ngày trống cho trục liền mạch:
    [{day, in, out, cost, turns}]."""
    d = _load()
    days = d.get("days", {})
    tz = timezone(timedelta(hours=7))
    today = datetime.now(tz).date()
    out = []
    for i in range(n - 1, -1, -1):
        day = (today - timedelta(days=i)).strftime("%Y-%m-%d")
        bucket = days.get(day, {})
        tot = {"in": 0, "out": 0, "cost": 0.0, "turns": 0}
        for e in bucket.values():
            tot["in"] += e.get("in", 0)
            tot["out"] += e.get("out", 0)
            tot["cost"] += e.get("cost", 0.0)
            tot["turns"] += e.get("turns", 0)
        out.append({"day": day, **tot})
    return out


def summary() -> dict:
    d = _load()
    day = _today()
    return {"day": day,
            "today": _rollup(d["days"].get(day, {})),
            "all_time": _rollup(d.get("total", {}))}
