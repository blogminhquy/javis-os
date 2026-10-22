"""webhook_capture.py - turn real deliveries into masked fixtures and check a hook configuration against them (0.274.0,
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
from decimal import Decimal
from typing import Optional

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
            return "x" * min(len(x), 12) if x else ""      # an empty text stays empty (`empty` rules)
        if wt._is_num(x):
            return 0
        return x
    def show(x):
        # A kept text still loses an e-mail or a phone inside it (digits become 0, the shape stays).
        if isinstance(x, Decimal):
            return int(x) if x == x.to_integral_value() else float(x)
        if not isinstance(x, str):
            return x
        m = wt._show_view(x)
        return m.replace("•", "0").replace("***", "xxx") if m != x else x
    return wt._payload_walk(v, key, 0, pii, False, product, hide, show)


def rule_paths(rules: dict, actions: Optional[list] = None) -> list:
    """The payload paths a hook's rules read: filter and `when` paths, schema fields, mapping sources, business key
    parts. A fixture must keep those (else it no longer gets the decision the real event got)."""
    out = []

    def walk(x):
        if isinstance(x, dict):
            for k, v in x.items():
                if k == "path" and isinstance(v, str):
                    out.append(v)
                elif k in ("business_paths", "paths") and isinstance(v, list):
                    out.extend(p for p in v if isinstance(p, str))
                else:
                    walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)
    r = rules if isinstance(rules, dict) else {}
    walk(r.get("filter"))
    walk(r.get("dedup") or r.get("business_key"))
    sch = r.get("schema") if isinstance(r.get("schema"), dict) else {}
    out.extend(sch.get("fields", {}).keys() if isinstance(sch.get("fields"), dict) else [])
    for v in (r.get("mapping") if isinstance(r.get("mapping"), dict) else {}).values():
        if isinstance(v, str):
            out.append(v)
        elif isinstance(v, dict) and isinstance(v.get("path"), str):
            out.append(v["path"])
    if isinstance(r.get("correlation"), str):
        out.append(r["correlation"])
    for a in actions or []:
        if isinstance(a, dict):
            walk(a.get("when"))           # an action's own condition reads the payload too
    return sorted(set(out))


def rule_operands(rules: dict, actions: Optional[list] = None) -> dict:
    """{path: [condition]} of the conditions in the filter and the actions' `when`: the constants the OWNER wrote."""
    out: dict = {}

    def walk(x):
        if isinstance(x, dict):
            if isinstance(x.get("path"), str) and "op" in x:
                out.setdefault(x["path"], []).append(x)
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)
    walk((rules or {}).get("filter") if isinstance(rules, dict) else None)
    for a in actions or []:
        if isinstance(a, dict):
            walk(a.get("when"))
    return out


def _operand_text(raw: str, conds: list):
    """A text the rules compare, written as the owner's own constants instead of the customer's text. A candidate is
    accepted only if EVERY condition on that path gives the same answer on it as on the real value (case, starts_with,
    ends_with, ne and several conditions included); the real value itself only when it is one of the owner's `eq`/`in`
    constants and the e-mail and phone masking leaves it whole. Anything else: None (the path is not kept)."""
    def results(v):
        out = []
        for c in conds:
            op = str(c.get("op") or "eq")
            cs = c.get("case_sensitive", c.get("case", True))
            cs = bool(cs) if not isinstance(cs, str) else cs != "insensitive"
            out.append(webhook_rules._test_one(op, v, c.get("value"), cs))
        return out
    want = results(raw)
    consts = []
    for c in conds:
        vals = c.get("value") if isinstance(c.get("value"), list) else [c.get("value")]
        consts += [(str(c.get("op") or "eq"), v) for v in vals if isinstance(v, str) and v]
    cands = []
    if any(op in ("eq", "in") and v == raw for op, v in consts) and _show_capture(raw) == raw:
        cands.append(raw)
    pre = [v for op, v in consts if op == "starts_with"]
    mid = [v for op, v in consts if op == "contains"]
    suf = [v for op, v in consts if op == "ends_with"]
    cands += [v for _, v in consts]
    cands.append(" ".join(pre[:1] + mid + suf[:1]))
    cands.append("x" * min(max(len(raw), 1), 12))      # the scrub's own placeholder, when the rules do not match it
    for cand in cands:
        # Never a value the e-mail and phone masking would change, even one the owner listed (a customer's e-mail).
        if cand and _show_capture(cand) == cand and results(cand) == want:
            return cand
    return None


def restore_paths(scrubbed, raw, paths: list, operands: Optional[dict] = None) -> tuple:
    """Put back, at each path the rules read, the value as received, so the fixture gets the real event's decision.
    Only a single value (never a whole object or list: those keep their scrubbed shape), never under an identity
    number, a customer block or a credential, never a link, and a kept text still loses any e-mail or phone inside it.
    Returns (payload, kept, refused)."""
    import webhook_triggers as wt
    kept, refused = [], []

    def unsafe(segs):
        product = False
        for sg in segs:
            if not isinstance(sg, str):
                continue
            k = sg.lower()
            words = wt._key_words(sg)
            if any(x in k for x in wt._SECRET_KEYS) or wt.is_ident_key(sg):
                return True
            hits = [x for x in wt._PII_KEYS if any(x in f for f in wt._key_forms(sg))]
            if wt.is_pii_key(sg) and not (product and hits == ["name"] and not (words & {"tel", "ten", "by"})):
                return True
            product = product or bool(words & wt._PRODUCT_PARENTS) or k in wt._PRODUCT_PARENTS
        return False

    def leaf_ok(key, v, product):
        if isinstance(v, (dict, list)) or wt._key_words(key) & wt._LINK_WORDS \
                or (isinstance(v, str) and v.startswith(("http://", "https://")) and "?" in v):
            return False
        # Texts by the same ALLOWLIST as the scrub (a denylist cannot know every key that holds a name: `ho_va_ten`,
        # free text in `message`); numbers and booleans the rules compare are restored.
        if isinstance(v, str) and not wt.keep_leaf(key, v, False, False, product):
            return False
        # A text the e-mail and phone masking would change is not written altered (the fixture would then get another
        # decision while saying it kept the path): the path is reported as not kept instead.
        return not (isinstance(v, str) and _show_capture(v) != v)

    def put(dst, src, segs, key, ok, product=False):
        if not segs:
            if not leaf_ok(key, src, product):
                const = _operand_text(src, cur_ops[0]) if isinstance(src, str) and cur_ops[0] \
                    and not (wt._key_words(key) & wt._LINK_WORDS) else None
                if const is None:
                    ok[0] = False
                    return dst
                return const
            return _show_capture(src)
        sg, rest = segs[0], segs[1:]
        if sg == webhook_rules.WILD or isinstance(sg, int):
            inner = product or bool(wt._key_words(key) & wt._PRODUCT_PARENTS) or str(key).lower() in wt._PRODUCT_PARENTS
            if sg == webhook_rules.WILD:
                if isinstance(src, list) and isinstance(dst, list):
                    return [put(d, s, rest, key, ok, inner) for d, s in zip(dst, src)]
                return dst
            if isinstance(src, list) and isinstance(dst, list) and sg < len(src) and sg < len(dst):
                dst = list(dst)
                dst[sg] = put(dst[sg], src[sg], rest, key, ok, inner)
            return dst
        if isinstance(src, dict) and isinstance(dst, dict) and sg in src and sg in dst:
            dst = dict(dst)
            sub = product and (not rest or bool(wt._key_words(sg) & wt._PRODUCT_SUB) or sg.lower() in wt._PRODUCT_SUB)
            dst[sg] = put(dst[sg], src[sg], rest, sg, ok, sub)
        return dst
    out = scrubbed
    cur_ops = [[]]
    for p in paths:
        try:
            segs = webhook_rules.parse_path(p)
        except webhook_rules.RuleError:
            refused.append(p)
            continue
        if unsafe(segs):
            refused.append(p)
            continue
        ok = [True]
        cur_ops[0] = (operands or {}).get(p) or []
        new = put(out, raw, segs, "", ok)
        if ok[0]:
            out = new
            kept.append(p)
        else:
            refused.append(p)
    return out, kept, refused


def _show_capture(x):
    import webhook_triggers as wt
    if isinstance(x, Decimal):
        return int(x) if x == x.to_integral_value() else float(x)
    if isinstance(x, str):
        m = wt._show_view(x)
        return m.replace("•", "0").replace("***", "xxx") if m != x else x
    return x


def export(state_dir: Path, eid: str, expect: str, out: Path, config: Optional[dict] = None) -> dict:
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
        payload, kept, refused = scrub(doc), [], []
        if config:
            payload, kept, refused = restore_paths(payload, doc, rule_paths(config.get("rules") or {},
                                                                            config.get("actions")),
                                                   rule_operands(config.get("rules") or {}, config.get("actions")))
        fx = {"name": out.stem, "origin": f"CAPTURED on staging from event {eid}, customer fields and credentials replaced",
              "content_type": ev.get("content_type") or "application/json", "headers": headers,
              "payload": payload, "expect": expect, "kept_for_rules": kept, "not_kept": refused}
    finally:
        st.close()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(fx, ensure_ascii=False, indent=1, default=str) + "\n", encoding="utf-8")
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
    e.add_argument("--config", help="the hook's {\"rules\": ...}: the paths they read keep their value (never an "
                   "identity, customer or credential path)")
    c = sub.add_parser("check")
    c.add_argument("--config", required=True, help="a JSON file with the hook's {\"rules\": ...}")
    c.add_argument("fixtures", nargs="+")
    a = ap.parse_args(argv)
    if a.cmd == "export":
        config = json.loads(Path(a.config).read_text(encoding="utf-8")) if a.config else None
        fx = export(Path(a.state_dir), a.event, a.expect, Path(a.out), config)
        print(f"written {a.out}: read it before committing (headers {sorted(fx['headers'])}; kept for the rules "
              f"{fx['kept_for_rules']}; not kept {fx['not_kept']})")
        return 0
    res = check(json.loads(Path(a.config).read_text(encoding="utf-8")), a.fixtures)
    for r in res:
        print(("ok   " if r["ok"] else "FAIL ") + f"{r['fixture']}: expected {r['expect']}, got {r['decision']}"
              + (f" ({r['reason']})" if r["reason"] else ""))
    return 0 if all(r["ok"] for r in res) else 1


if __name__ == "__main__":
    raise SystemExit(main())
