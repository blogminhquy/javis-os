"""webhook_capture.py - turn real deliveries into masked fixtures and check a hook configuration against them (0.241.0,
spec §16.6, §17).

    .venv/bin/python tools/webhook_capture.py export --state-dir <STATE_DIR> --event ev_... --expect run \
        --out tests/fixtures/webhooks/captured/poscake-order.json
    .venv/bin/python tools/webhook_capture.py check --config hook.json tests/fixtures/webhooks/captured/*.json

`export` reads one stored event (its body exactly as received and the headers Javis keeps) and writes a fixture with
every customer field and credential replaced, keeping the shape and the types: the rules see the same paths, the same
number / text / boolean types and the same array lengths. Run it on STAGING, read the file before committing it.

`check` evaluates each fixture with the rules of a hook configuration (`{"rules": {...}}`, the Advanced box of the
dashboard) and compares the decision with the fixture's `expect` (run, filtered, invalid, duplicate). It writes
nothing, sends nothing and calls no model. Exit code 0 when every fixture gets the decision it expects.

What stays the owner's to do: capture the deliveries (staging-pilot-pack.md, part 0), set `expect` for each, and read
every exported file before it goes into the repository.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "server"))

import webhook_rules  # noqa: E402

_SECRET_HEADERS = ("authorization", "cookie", "x-javis-token", "x-hub-signature", "x-hub-signature-256",
                   "x-shopify-hmac-sha256", "stripe-signature", "x-webhook-signature")


# Under these parents `name`, `title` and `sku` name a PRODUCT, not a person: kept, since filters read them.
PRODUCT_PARENTS = ("items", "line_items", "products", "order_items", "variations", "products_info", "lines")
PRODUCT_KEYS = ("name", "title", "sku", "product_name", "variation_name")


def scrub(v, key: str = "", pii: bool = False, product: bool = False):
    """Same shape and types, no customer data: the dashboard's allowlist (`webhook_triggers.keep_leaf`) decides what
    stays (ids, statuses, product names, amounts, times); every other text becomes a placeholder of its length class,
    every other number 0, every credential REDACTED."""
    import webhook_triggers as wt

    def hide(x, secret):
        if secret:
            return "REDACTED"
        if isinstance(x, str):
            return "x" * min(max(len(x), 1), 12)
        if isinstance(x, (int, float)):
            return 0
        return x
    return wt._payload_walk(v, key, 0, pii, False, product, hide)


def export(state_dir: Path, eid: str, expect: str, out: Path) -> dict:
    import webhook_store
    st = webhook_store.Store(state_dir / "webhook_events.sqlite3")
    try:
        ev = st.get(eid, True)
        if ev is None:
            raise SystemExit(f"no event {eid} in {state_dir}")
        body = bytes(ev.get("body") or b"")
        doc, kind = webhook_rules.parse_payload(body, ev.get("content_type") or "")
        if kind not in ("json", "form"):
            raise SystemExit(f"event {eid} is {kind}: only JSON and form bodies are exported")
        headers = {k: ("REDACTED" if k.lower() in _SECRET_HEADERS else v) for k, v in (ev.get("headers") or {}).items()}
        fx = {"name": out.stem, "origin": f"CAPTURED on staging from event {eid}, customer fields and credentials replaced",
              "content_type": ev.get("content_type") or "application/json", "headers": headers,
              "payload": scrub(doc), "expect": expect}
    finally:
        st.close()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(fx, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return fx


def check(config: dict, fixtures: list) -> list:
    rules = webhook_rules.validate(config.get("rules") or {})
    out = []
    for p in fixtures:
        fx = json.loads(Path(p).read_text(encoding="utf-8"))
        body = json.dumps(fx["payload"], ensure_ascii=False).encode("utf-8")
        res = webhook_rules.evaluate(rules, body, fx.get("content_type") or "application/json")
        out.append({"fixture": str(p), "expect": fx.get("expect"), "decision": res["decision"],
                    "reason": res.get("reason", ""), "ok": fx.get("expect") in (None, "", res["decision"])})
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Masked fixtures from real webhook deliveries, and rule checks on them.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("export")
    e.add_argument("--state-dir", required=True)
    e.add_argument("--event", required=True)
    e.add_argument("--expect", required=True, choices=("run", "filtered", "invalid", "duplicate"))
    e.add_argument("--out", required=True)
    c = sub.add_parser("check")
    c.add_argument("--config", required=True, help="a JSON file with the hook's {\"rules\": ...}")
    c.add_argument("fixtures", nargs="+")
    a = ap.parse_args(argv)
    if a.cmd == "export":
        fx = export(Path(a.state_dir), a.event, a.expect, Path(a.out))
        print(f"written {a.out}: read it before committing (headers {sorted(fx['headers'])})")
        return 0
    res = check(json.loads(Path(a.config).read_text(encoding="utf-8")), a.fixtures)
    for r in res:
        print(("ok   " if r["ok"] else "FAIL ") + f"{r['fixture']}: expected {r['expect']}, got {r['decision']}"
              + (f" ({r['reason']})" if r["reason"] else ""))
    return 0 if all(r["ok"] for r in res) else 1


if __name__ == "__main__":
    raise SystemExit(main())
