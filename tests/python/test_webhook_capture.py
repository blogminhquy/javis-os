"""0.274.0: tools/webhook_capture.py, the bridge to spec §16.6: a stored delivery becomes a masked fixture (same shape and
types, no customer data, no credential) and a hook configuration is checked against such fixtures.

    python tests/run.py webhook_capture
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import json
import sys
import tempfile
from pathlib import Path

import test_webhook_spec_matrix as mx  # noqa: E402  (the harness; its main() runs only as a script)

sys.path.insert(0, str(ROOT / "tools"))
import webhook_capture as wc  # noqa: E402

fails = []


def check(name, cond, them=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(them) + "]") if them and not cond else ""))
    if not cond:
        fails.append(name)


async def main():
    sd = Path(tempfile.mkdtemp(prefix="wh-capture-"))
    f = mx.make(sd)
    h, t, _ = f.create("/b1", name="POSCake", target="task", text="x", rules=mx.SPEC_RULES)
    order = dict(mx.ORDER, shipping_address={"line1": "12 Lê Lợi", "phone": "0912345678"}, total=350000,
                 note="giao giờ hành chính, gọi chị Lan 0987654321 hoặc lan@example.com")
    c, r = await f.accept(h["id"], t, json.dumps(order, ensure_ascii=False).encode(), "application/json", "cap-1",
                          headers={"content-type": "application/json", "x-request-id": "req-9",
                                   "user-agent": "POSCake-Webhook/1.0"})
    await f.wait_idle()
    f.store().close()
    f._store = None
    out = sd / "captured" / "poscake-order.json"
    fx = wc.export(sd, r["event_id"], "run", out)
    text = out.read_text(encoding="utf-8")
    leaks = [s for s in ("Nguyễn Lan", "0912345678", "0987654321", "lan@example.com", "12 Lê Lợi") if s in text]
    check("export: no customer name, phone, e-mail or address in the fixture", not leaks, leaks)
    p = fx["payload"]
    check("export: the shape and the types the rules read are kept (ids, status, item names, number types)",
          p["id"] == 1001 and p["status"] == 1 and p["shop_id"] == 7 and isinstance(p["total"], int)
          and [i["name"] for i in p["items"]] == [i["name"] for i in mx.ORDER["items"]]
          and isinstance(p["shipping_address"]["phone"], str), p)
    check("export: the headers are the ones Javis keeps, no token", "x-javis-token" not in json.dumps(fx["headers"]).lower()
          and fx["headers"].get("user-agent") == "POSCake-Webhook/1.0", fx["headers"])
    cfg = sd / "hook.json"
    cfg.write_text(json.dumps({"rules": mx.SPEC_RULES}), encoding="utf-8")
    res = wc.check({"rules": mx.SPEC_RULES}, [out])
    check("check: the captured order gets the decision it expects under the hook's rules", res[0]["ok"]
          and res[0]["decision"] == "run", res)
    wrong = dict(json.loads(text), expect="filtered")
    out2 = sd / "captured" / "poscake-wrong.json"
    out2.write_text(json.dumps(wrong, ensure_ascii=False), encoding="utf-8")
    code = wc.main(["check", "--config", str(cfg), str(out), str(out2)])
    check("check: a fixture whose expected decision differs fails the run (exit 1)", code == 1)

    real_capture()


def real_capture():
    """The first REAL POSCake delivery (event_type create, captured 2026-10-22): what it teaches is pinned here."""
    import re
    fx = ROOT / "tests" / "fixtures" / "webhooks" / "captured" / "poscake-order-create.json"
    text = fx.read_text(encoding="utf-8")
    doc = json.loads(text)
    check("real capture: POSCake sends no signature and no custom header (content-type and user-agent only)",
          sorted(doc["headers"]) == ["content-type", "user-agent"], doc["headers"])
    leaks = re.findall(r"[\w.+-]+@[\w-]+\.[\w.]+|\b0\d{9}\b|pke\.gg/\w+|pancake-auth|order_id=\d+", text)
    check("real capture: no e-mail, phone number, payment or tracking link left in the fixture", not leaks, leaks)
    real = {"rules": {"filter": {"all": [
        {"path": "event_type", "op": "eq", "value": "create"},
        {"path": "items[*].variation_info.name", "op": "contains", "value": "AutopageAI", "quantifier": "any",
         "case_sensitive": False, "reason": "product_not_found"}]},
        "dedup": {"policy_version": 1, "business_paths": ["shop_id", "id", "status"], "ttl_s": 604800,
                  "missing": "quarantine"}, "correlation": "id"}}
    res = wc.check(real, [str(fx)])
    check("real capture: rules on the real field names (event_type, items[*].variation_info.name) run the order",
          res[0]["ok"] and res[0]["decision"] == "run", res)
    spec = {"rules": {"filter": {"all": [
        {"path": "status", "op": "eq", "value": 1},
        {"path": "items[*].name", "op": "contains", "value": "AutopageAI", "quantifier": "any",
         "case_sensitive": False, "reason": "product_not_found"}]}}}
    res = wc.check(spec, [str(fx)])
    check("real capture: the spec's illustrative names (status 1, items[*].name) would ignore every real new order",
          res[0]["decision"] == "filtered", res)


if __name__ == "__main__":
    asyncio.run(main())
    if fails:
        print(f"\nFAIL {len(fails)}: " + "; ".join(fails))
        sys.exit(1)
    print("\nOK - test_webhook_capture: all pass")
