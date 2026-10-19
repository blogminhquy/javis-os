"""webhook_rules.py - what a hook does with an event BEFORE anything runs (0.229.0, webhook platform M2).

A hook may carry `rules`, all optional, all data (JSON), never code:

    {
      "schema":  {"fields": {"data.order.id": {"type": "string", "required": true},
                             "data.order.total": {"type": "number"}}},
      "filter":  {"all": [{"path": "event", "op": "eq", "value": "order.created"},
                          {"any": [{"path": "data.order.total", "op": "gte", "value": 100000},
                                   {"path": "data.vip", "op": "eq", "value": true}]}]},
      "mapping": {"order_id": "data.order.id",
                  "email": {"path": "data.customer.email", "transform": ["trim", "lower"]},
                  "total": {"path": "data.order.total", "type": "number", "default": 0},
                  "title": {"template": "Đơn {order_id} - {email}"}},
      "business_key": {"namespace": "shop", "entity": "order", "path": "data.order.id", "type": "string",
                       "ttl_s": 2592000, "on_missing": "accept"}
    }

Order of evaluation, the same at receipt and in simulation (`evaluate`):
  1. parse   the body (JSON, form, or plain text as {"_text": ...});
  2. schema  required fields and their types. A failing event is `invalid` (422 to the sender, nothing runs);
  3. filter  conditions over the payload. A non-matching event is `filtered` (200, nothing runs);
  4. mapping named fields picked from the payload, typed and transformed, handed to the run as DATA;
  5. business key  `<entity>:<value>` in `<namespace>`, deduplicated for `ttl_s` inside the hook's brain.

Safety: no eval, no regex, no format-string attribute access (templates substitute `{name}` by a plain
scan), bounded depth, bounded sizes, bounded work. The payload can never change the hook's level, target or
instruction: rules only read it. Nothing here touches the store, the network or a model.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from decimal import Decimal, InvalidOperation
from typing import Any, Optional
from urllib.parse import parse_qs

RULES_MAX_BYTES = 8 * 1024
PATH_MAX = 200
PATH_SEGMENTS_MAX = 12
CONDITIONS_MAX = 40
DEPTH_MAX = 4
FIELDS_MAX = 40
VALUE_MAX = 2000              # characters of a mapped value / a compared string
LIST_MAX = 50                 # items in an `in` list
TRACE_VALUE_MAX = 120         # characters of a value shown in a trace
TTL_MIN_S = 60
TTL_MAX_S = 366 * 86400
TTL_DEFAULT_S = 30 * 86400
NUM_EXP_MAX = 100             # |exponent| of a number we treat as a number (1e999999 would cost seconds as an int)
NUM_DIGITS_MAX = 60           # digits of an integer literal we parse as a number
DEPTH_PAYLOAD_MAX = 64        # nesting of the payload; deeper is refused as invalid
FIELD_JSON_MAX = 4000         # serialised size of ONE mapped field (an object or list mapped with type any)
FIELDS_JSON_MAX = 32000       # serialised size of all mapped fields together
KEY_VALUE_MAX = 200           # longer business key values are shortened with a hash, never cut

OPS = ("eq", "ne", "in", "not_in", "exists", "missing", "gt", "gte", "lt", "lte",
       "contains", "starts_with", "ends_with", "empty", "not_empty")
TYPES = ("string", "number", "integer", "boolean", "object", "array", "any")
KEY_TYPES = ("string", "integer", "email", "phone")
TRANSFORMS = ("trim", "lower", "upper", "digits", "string", "number", "integer", "boolean", "first", "join",
              "length")
NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,39}$")      # mapped field names, also the {name} in templates
NS_RE = re.compile(r"^[a-z0-9][a-z0-9_.-]{0,39}$")
_SEG_RE = re.compile(r"^([^\[\]]*)((?:\[\d{1,4}\])*)$")
_MISSING = object()


class RuleError(ValueError):
    """The rules themselves are wrong (shown to the owner when saving)."""


# ── paths ──
def parse_path(path: str) -> list:
    """`data.items[0].sku` -> ['data', 'items', 0, 'sku']. A leading `$.` is allowed. Keys with dots cannot be
    addressed (kept simple on purpose)."""
    p = str(path or "").strip()
    if p.startswith("$."):
        p = p[2:]
    elif p == "$":
        return []
    if not p or len(p) > PATH_MAX:
        raise RuleError(f"bad path: {path!r}")
    out: list = []
    for seg in p.split("."):
        m = _SEG_RE.match(seg)
        if not m or (not m.group(1) and not m.group(2)):
            raise RuleError(f"bad path: {path!r}")
        if m.group(1):
            out.append(m.group(1))
        for idx in re.findall(r"\[(\d{1,4})\]", m.group(2)):
            out.append(int(idx))
    if len(out) > PATH_SEGMENTS_MAX:
        raise RuleError(f"path too deep: {path!r}")
    return out


def get_path(doc: Any, path) -> Any:
    """The value at `path`, or the _MISSING sentinel. Never raises on the payload's shape."""
    segs = parse_path(path) if isinstance(path, str) else path
    cur = doc
    for s in segs:
        if isinstance(s, int):
            if isinstance(cur, list) and 0 <= s < len(cur):
                cur = cur[s]
            else:
                return _MISSING
        elif isinstance(cur, dict) and s in cur:
            cur = cur[s]
        else:
            return _MISSING
    return cur


# ── payload ──
def _bounded(d: Decimal) -> bool:
    return d.is_finite() and (d.is_zero() or abs(d.adjusted()) <= NUM_EXP_MAX)


def _parse_float(s: str):
    """JSON floats as exact Decimals, but only of sane size: `1e999999` stays the TEXT it was (a number that big is
    not a business value, and turning it into an int or float costs seconds or overflows)."""
    try:
        d = Decimal(s)
    except InvalidOperation:
        return s
    return d if _bounded(d) else s


def _parse_int(s: str):
    return int(s) if len(s.lstrip("-")) <= NUM_DIGITS_MAX else s


def _depth(text: str) -> int:
    """Deepest nesting of [ and { outside strings, in one pass (the parser would recurse on it)."""
    depth = best = 0
    in_str = esc = False
    for ch in text:
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
        elif ch == '"':
            in_str = True
        elif ch in "[{":
            depth += 1
            if depth > best:
                best = depth
                if best > DEPTH_PAYLOAD_MAX:
                    return best
        elif ch in "]}":
            depth -= 1
    return best


def parse_payload(body: bytes, content_type: str) -> tuple:
    """(document, kind). JSON object/array as is; a form as {key: value} (a repeated key as a list); anything
    else as {"_text": text}. kind `too_deep` = JSON nested deeper than DEPTH_PAYLOAD_MAX. Never raises."""
    text = bytes(body or b"").decode("utf-8", "replace")
    ct = (content_type or "").lower()
    if text.strip() and ("json" in ct or text.lstrip()[:1] in ("{", "[")):
        if _depth(text) > DEPTH_PAYLOAD_MAX:
            return {"_text": text[:VALUE_MAX]}, "too_deep"
        try:
            return json.loads(text, parse_float=_parse_float, parse_int=_parse_int,
                              parse_constant=lambda c: c), "json"
        except (ValueError, RecursionError):
            pass
    if "x-www-form-urlencoded" in ct:
        try:
            pairs = parse_qs(text, keep_blank_values=True)
            return {k: (v[0] if len(v) == 1 else v) for k, v in pairs.items()}, "form"
        except ValueError:
            pass
    return {"_text": text}, "text"


# ── typing ──
def type_of(v: Any) -> str:
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "boolean"
    if isinstance(v, int):
        return "integer"
    if isinstance(v, (float, Decimal)):
        return "number"
    if isinstance(v, str):
        return "string"
    if isinstance(v, list):
        return "array"
    if isinstance(v, dict):
        return "object"
    return "unknown"


def _num(v: Any) -> Optional[Decimal]:
    """A number from a JSON number or a numeric string ("150000", "1.5e3"); None otherwise. Booleans are not
    numbers. NaN/Infinity are refused."""
    if isinstance(v, bool) or v is None:
        return None
    if isinstance(v, int):
        if abs(v) >= 10 ** NUM_DIGITS_MAX:
            return None
        d = Decimal(v)
    elif isinstance(v, Decimal):
        d = v
    elif isinstance(v, float):
        if math.isnan(v) or math.isinf(v):
            return None
        d = Decimal(repr(v))
    elif isinstance(v, str):
        s = v.strip().replace("_", "")
        if not s or len(s) > 60:
            return None
        try:
            d = Decimal(s)
        except InvalidOperation:
            return None
    else:
        return None
    return d if _bounded(d) else None


def _matches_type(v: Any, t: str) -> bool:
    k = type_of(v)
    if t == "any":
        return True
    if t == "number":
        return k in ("number", "integer")
    if t == "integer":
        if k == "integer":
            return True
        if k != "number":
            return False
        d = _num(v)
        return d is not None and d == d.to_integral_value()
    return k == t


def _plain(v: Any, depth: int = 0) -> Any:
    """JSON-safe copy for traces, fields and prompts: a Decimal becomes an int, a float only when that is exact
    enough, otherwise its exact text (never inf/NaN, which JSON responses refuse, and never a float that would make
    two different big numbers equal)."""
    if depth > DEPTH_PAYLOAD_MAX:
        return "…"
    if isinstance(v, Decimal):
        if not _bounded(v):
            return str(v)
        if v == v.to_integral_value() and abs(v) < Decimal(10) ** 15:
            return int(v)
        if abs(v.adjusted()) <= 15 and len(v.as_tuple().digits) <= 15:
            return float(v)
        return str(v)
    if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
        return str(v)
    if isinstance(v, dict):
        return {str(k): _plain(x, depth + 1) for k, x in v.items()}
    if isinstance(v, list):
        return [_plain(x, depth + 1) for x in v]
    return v


def _short(v: Any) -> Any:
    if v is _MISSING:
        return None
    v = _plain(v)
    if isinstance(v, str):
        return v if len(v) <= TRACE_VALUE_MAX else v[:TRACE_VALUE_MAX] + "…"
    if isinstance(v, (dict, list)):
        s = json.dumps(v, ensure_ascii=False)
        return v if len(s) <= TRACE_VALUE_MAX else s[:TRACE_VALUE_MAX] + "…"
    return v


# ── validation (when the owner saves the rules) ──
def validate(rules: Any) -> dict:
    """Normalised rules, or RuleError with a message naming the bad part. {} or None means no rules."""
    if rules in (None, "", {}):
        return {}
    if isinstance(rules, str):
        try:
            rules = json.loads(rules)
        except ValueError as e:
            raise RuleError(f"rules are not valid JSON: {e}")
    if not isinstance(rules, dict):
        raise RuleError("rules must be an object")
    if len(json.dumps(rules, ensure_ascii=False).encode("utf-8")) > RULES_MAX_BYTES:
        raise RuleError(f"rules larger than {RULES_MAX_BYTES} bytes")
    unknown = set(rules) - {"schema", "filter", "mapping", "business_key"}
    if unknown:
        raise RuleError(f"unknown rule part: {sorted(unknown)[0]}")
    out: dict = {}
    if rules.get("schema"):
        out["schema"] = _v_schema(rules["schema"])
    if rules.get("filter"):
        count = [0]
        out["filter"] = _v_cond(rules["filter"], 1, count)
    if rules.get("mapping"):
        out["mapping"] = _v_mapping(rules["mapping"])
    if rules.get("business_key"):
        out["business_key"] = _v_bkey(rules["business_key"])
        f = out["business_key"].get("field")
        if f and f not in out.get("mapping", {}):
            raise RuleError(f"business_key field {f!r} is not a mapped field")
    return out


def _v_schema(s: Any) -> dict:
    if not isinstance(s, dict) or not isinstance(s.get("fields"), dict):
        raise RuleError("schema needs a `fields` object")
    if len(s["fields"]) > FIELDS_MAX:
        raise RuleError(f"schema has more than {FIELDS_MAX} fields")
    fields = {}
    for path, spec in s["fields"].items():
        parse_path(path)
        if isinstance(spec, str):
            spec = {"type": spec}
        if not isinstance(spec, dict):
            raise RuleError(f"schema field {path}: expected an object")
        t = str(spec.get("type") or "any")
        if t not in TYPES:
            raise RuleError(f"schema field {path}: unknown type {t}")
        fields[path] = {"type": t, "required": bool(spec.get("required", False))}
    return {"fields": fields}


def _v_cond(c: Any, depth: int, count: list) -> dict:
    if depth > DEPTH_MAX:
        raise RuleError(f"filter nested deeper than {DEPTH_MAX}")
    if not isinstance(c, dict):
        raise RuleError("a filter condition must be an object")
    for group in ("all", "any"):
        if group in c:
            items = c[group]
            if not isinstance(items, list) or not items:
                raise RuleError(f"`{group}` needs a non-empty list")
            return {group: [_v_cond(x, depth + 1, count) for x in items]}
    if "not" in c:
        return {"not": _v_cond(c["not"], depth + 1, count)}
    count[0] += 1
    if count[0] > CONDITIONS_MAX:
        raise RuleError(f"filter has more than {CONDITIONS_MAX} conditions")
    op = str(c.get("op") or "eq")
    if op not in OPS:
        raise RuleError(f"unknown filter op: {op}")
    path = str(c.get("path") or "")
    parse_path(path)
    out = {"path": path, "op": op}
    if op in ("exists", "missing", "empty", "not_empty"):
        return out
    if "value" not in c:
        raise RuleError(f"filter on {path}: `{op}` needs a value")
    v = c["value"]
    if op in ("in", "not_in"):
        if not isinstance(v, list) or not v or len(v) > LIST_MAX:
            raise RuleError(f"filter on {path}: `{op}` needs a list of 1 to {LIST_MAX} values")
        if any(isinstance(x, (dict, list)) for x in v):
            raise RuleError(f"filter on {path}: list values must be plain")
    elif isinstance(v, (dict, list)):
        raise RuleError(f"filter on {path}: the value must be plain")
    elif op in ("gt", "gte", "lt", "lte") and _num(v) is None:
        raise RuleError(f"filter on {path}: `{op}` needs a number")
    if isinstance(v, str) and len(v) > VALUE_MAX:
        raise RuleError(f"filter on {path}: value too long")
    out["value"] = v
    if c.get("case") == "insensitive":
        out["case"] = "insensitive"
    return out


def _v_mapping(m: Any) -> dict:
    if not isinstance(m, dict):
        raise RuleError("mapping must be an object of name -> path or spec")
    if len(m) > FIELDS_MAX:
        raise RuleError(f"mapping has more than {FIELDS_MAX} fields")
    out = {}
    for name, spec in m.items():
        if not NAME_RE.match(str(name)):
            raise RuleError(f"mapping name {name!r}: use letters, digits and _ (max 40)")
        if isinstance(spec, str):
            spec = {"path": spec}
        if not isinstance(spec, dict):
            raise RuleError(f"mapping {name}: expected a path or an object")
        o: dict = {}
        if "template" in spec:
            tpl = str(spec["template"])
            if len(tpl) > VALUE_MAX:
                raise RuleError(f"mapping {name}: template too long")
            for ref in _template_refs(tpl):
                if ref not in out:
                    raise RuleError(f"mapping {name}: template uses {{{ref}}}, which is not a field mapped above it")
            o["template"] = tpl
        elif "path" in spec:
            parse_path(spec["path"])
            o["path"] = str(spec["path"])
        elif "value" in spec:
            if isinstance(spec["value"], (dict, list)):
                raise RuleError(f"mapping {name}: a constant must be plain")
            o["value"] = spec["value"]
        else:
            raise RuleError(f"mapping {name}: needs `path`, `template` or `value`")
        t = str(spec.get("type") or "any")
        if t not in TYPES:
            raise RuleError(f"mapping {name}: unknown type {t}")
        o["type"] = t
        tr = spec.get("transform") or []
        if isinstance(tr, str):
            tr = [tr]
        if not isinstance(tr, list) or len(tr) > 6 or any(str(x) not in TRANSFORMS for x in tr):
            raise RuleError(f"mapping {name}: transforms are {', '.join(TRANSFORMS)} (at most 6)")
        o["transform"] = [str(x) for x in tr]
        if "default" in spec:
            if isinstance(spec["default"], (dict, list)):
                raise RuleError(f"mapping {name}: the default must be plain")
            o["default"] = spec["default"]
        o["required"] = bool(spec.get("required", False))
        out[str(name)] = o
    return out


def _v_bkey(b: Any) -> dict:
    if not isinstance(b, dict):
        raise RuleError("business_key must be an object")
    ns = str(b.get("namespace") or "default").strip().lower()
    if not NS_RE.match(ns):
        raise RuleError("business_key namespace: lowercase letters, digits, . _ - (max 40)")
    entity = str(b.get("entity") or "").strip().lower()
    if not NS_RE.match(entity):
        raise RuleError("business_key needs an `entity` (for example order, contact, payment)")
    src = {}
    if b.get("field"):
        src["field"] = str(b["field"])
    else:
        parse_path(b.get("path") or "")
        src["path"] = str(b.get("path"))
    t = str(b.get("type") or "string")
    if t not in KEY_TYPES:
        raise RuleError(f"business_key type: one of {', '.join(KEY_TYPES)}")
    try:
        ttl = int(b["ttl_s"]) if b.get("ttl_s") is not None else TTL_DEFAULT_S
    except (TypeError, ValueError):
        raise RuleError("business_key ttl_s must be a number of seconds")
    if not TTL_MIN_S <= ttl <= TTL_MAX_S:
        raise RuleError(f"business_key ttl_s between {TTL_MIN_S} and {TTL_MAX_S}")
    miss = str(b.get("on_missing") or "accept")
    if miss not in ("accept", "reject"):
        raise RuleError("business_key on_missing: accept or reject")
    return {"namespace": ns, "entity": entity, "type": t, "ttl_s": ttl, "on_missing": miss, **src}


# ── evaluation ──
def _cmp_str(v: Any, case: str) -> str:
    s = v if isinstance(v, str) else json.dumps(_plain(v), ensure_ascii=False) if isinstance(v, (dict, list)) \
        else ("true" if v is True else "false" if v is False else "" if v is None else str(_plain(v)))
    s = s[:VALUE_MAX]
    return s.lower() if case == "insensitive" else s


def _eq(a: Any, b: Any, case: str) -> bool:
    na, nb = _num(a), _num(b)
    if na is not None and nb is not None and not isinstance(a, bool) and not isinstance(b, bool):
        return na == nb
    if isinstance(a, bool) or isinstance(b, bool) or a is None or b is None:
        return a is b or (isinstance(a, bool) and isinstance(b, bool) and a == b)
    return _cmp_str(a, case) == _cmp_str(b, case)


def _test(cond: dict, doc: Any) -> tuple:
    """(passed, actual value) for one leaf condition."""
    v = get_path(doc, cond["path"])
    op, want, case = cond["op"], cond.get("value"), cond.get("case", "")
    if op == "exists":
        return v is not _MISSING, v
    if op == "missing":
        return v is _MISSING, v
    if op in ("empty", "not_empty"):
        empty = v is _MISSING or v is None or v == "" or v == [] or v == {}
        return empty == (op == "empty"), v
    if v is _MISSING:
        return op in ("ne", "not_in"), v
    if op == "eq":
        return _eq(v, want, case), v
    if op == "ne":
        return not _eq(v, want, case), v
    if op == "in":
        return any(_eq(v, w, case) for w in want), v
    if op == "not_in":
        return not any(_eq(v, w, case) for w in want), v
    if op in ("gt", "gte", "lt", "lte"):
        a, b = _num(v), _num(want)
        if a is None or b is None:
            return False, v
        return {"gt": a > b, "gte": a >= b, "lt": a < b, "lte": a <= b}[op], v
    if isinstance(v, list) and op == "contains":
        return any(_eq(x, want, case) for x in v[:500]), v
    s, w = _cmp_str(v, case), _cmp_str(want, case)
    if op == "contains":
        return w in s, v
    if op == "starts_with":
        return s.startswith(w), v
    if op == "ends_with":
        return s.endswith(w), v
    return False, v


def _eval_cond(cond: dict, doc: Any, steps: list) -> bool:
    if "all" in cond:
        return all(_eval_cond(c, doc, steps) for c in cond["all"])
    if "any" in cond:
        return any(_eval_cond(c, doc, steps) for c in cond["any"])
    if "not" in cond:
        return not _eval_cond(cond["not"], doc, steps)
    ok, actual = _test(cond, doc)
    step = {"path": cond["path"], "op": cond["op"], "actual": _short(actual), "pass": ok}
    if "value" in cond:
        step["value"] = _short(cond["value"])
    steps.append(step)
    return ok


def _transform(v: Any, name: str) -> Any:
    if v is None:
        return None
    if name == "trim":
        return v.strip() if isinstance(v, str) else v
    if name == "lower":
        return v.lower() if isinstance(v, str) else v
    if name == "upper":
        return v.upper() if isinstance(v, str) else v
    if name == "digits":
        return "".join(ch for ch in _cmp_str(v, "") if ch.isdigit())
    if name == "string":
        return _cmp_str(v, "")
    if name == "number":
        n = _num(v)
        return None if n is None else n
    if name == "integer":
        n = _num(v)
        return None if n is None else int(n.to_integral_value())
    if name == "boolean":
        if isinstance(v, bool):
            return v
        s = _cmp_str(v, "insensitive").strip()
        return True if s in ("1", "true", "yes", "on", "y") else False if s in ("0", "false", "no", "off", "n", "") \
            else None
    if name == "first":
        return v[0] if isinstance(v, list) and v else (None if isinstance(v, list) else v)
    if name == "join":
        return ", ".join(_cmp_str(x, "") for x in v[:LIST_MAX]) if isinstance(v, list) else v
    if name == "length":
        return len(v) if isinstance(v, (str, list, dict)) else None
    return v


def _template_refs(tpl: str) -> list:
    return re.findall(r"\{([A-Za-z_][A-Za-z0-9_]{0,39})\}", tpl)


def render_template(tpl: str, fields: dict) -> str:
    """`{name}` replaced by the mapped field's text; nothing else is interpreted (no attribute access, no format
    spec, no nesting). An unknown name stays as written."""
    def rep(m):
        k = m.group(1)
        if k not in fields or fields[k] is None:
            return "" if k in fields else m.group(0)
        return _cmp_str(fields[k], "")
    return re.sub(r"\{([A-Za-z_][A-Za-z0-9_]{0,39})\}", rep, tpl)[:VALUE_MAX]


def _map(mapping: dict, doc: Any, trace: list) -> tuple:
    """(fields, errors)."""
    fields: dict = {}
    errors: list = []
    for name, spec in mapping.items():
        if "template" in spec:
            v: Any = render_template(spec["template"], fields)
        elif "path" in spec:
            v = get_path(doc, spec["path"])
        else:
            v = spec.get("value")
        src = "missing" if v is _MISSING else "ok"
        if v is _MISSING:
            v = spec.get("default", None) if "default" in spec else _MISSING
            if v is not _MISSING:
                src = "default"
        if v is not _MISSING:
            for t in spec.get("transform") or []:
                v = _transform(v, t)
            if isinstance(v, str) and len(v) > VALUE_MAX:
                v = v[:VALUE_MAX]
            t = spec.get("type", "any")
            if t != "any" and v is not None:
                if t in ("number", "integer") and isinstance(v, str):
                    n = _num(v)
                    v = n if n is not None else v
                if t == "integer" and isinstance(v, Decimal) and v == v.to_integral_value():
                    v = int(v)
                if t == "string" and not isinstance(v, (dict, list)):
                    v = _cmp_str(v, "")
                if not _matches_type(v, t):
                    errors.append(f"{name}: expected {t}, got {type_of(v)}")
                    src = "type_error"
        if v is _MISSING or (v is None and spec.get("required")):
            if spec.get("required"):
                errors.append(f"{name}: required field missing")
            v = None
        pv = _plain(v)
        if isinstance(pv, (dict, list)) and len(json.dumps(pv, ensure_ascii=False)) > FIELD_JSON_MAX:
            errors.append(f"{name}: value larger than {FIELD_JSON_MAX} characters (map a smaller part)")
            src = "too_large"
            pv = None
        fields[name] = pv
        trace.append({"field": name, "value": _short(pv), "source": src})
    return fields, errors


def _key_value(v: Any, t: str) -> Optional[str]:
    """Typed normalisation of a business key value, so `"A-001 "` and `"a-001"` do not become two orders by
    accident only where the type says so. None = no usable value."""
    if v is _MISSING or v is None or isinstance(v, (dict, list)):
        return None
    if t == "integer":
        n = _num(v)
        if n is None or n != n.to_integral_value():
            return None
        return str(int(n))
    # Exact text of a number (never through float: 12345678901234567.5 and .7 must stay two keys).
    s = (format(v, "f") if isinstance(v, Decimal) else _cmp_str(v, "")).strip()
    if t == "email":
        s = s.lower()
        return s if "@" in s and len(s) <= 254 else None
    if t == "phone":
        d = "".join(ch for ch in s if ch.isdigit())
        if d.startswith("84") and len(d) >= 11:     # +84 912... and 0912... are the same Vietnamese number
            d = "0" + d[2:]
        return d if 6 <= len(d) <= 15 else None
    if len(s) > KEY_VALUE_MAX:
        # Cut values could make two different ids one key: keep a prefix to read, plus a hash of the whole value.
        s = s[:KEY_VALUE_MAX - 20] + "#" + hashlib.sha256(s.encode("utf-8")).hexdigest()[:19]
    return s or None


def evaluate(rules: dict, body: bytes, content_type: str) -> dict:
    """Run parse -> schema -> filter -> mapping -> business key. Pure and deterministic.

    Returns {
      "decision": "run" | "invalid" | "filtered",
      "reason": "",                # why invalid/filtered, in plain words (English; the UI shows codes)
      "fields": {...},             # mapped fields (JSON-safe), {} without a mapping
      "business_key": None | {"scope": "<namespace>", "key": "<entity>:<value>", "ttl_s": n},
      "trace": {"parse": kind, "schema": [...], "filter": [...], "mapping": [...], "business_key": {...}},
    }"""
    rules = rules or {}
    doc, kind = parse_payload(body, content_type)
    trace: dict = {"parse": kind}
    out = {"decision": "run", "reason": "", "fields": {}, "business_key": None, "trace": trace}
    if kind == "too_deep" and rules:
        out.update(decision="invalid", reason=f"payload nested deeper than {DEPTH_PAYLOAD_MAX}")
        return out
    if rules.get("schema"):
        steps, bad = [], []
        for path, spec in rules["schema"]["fields"].items():
            v = get_path(doc, path)
            if v is _MISSING:
                ok = not spec["required"]
                why = "missing" if not ok else "absent"
            else:
                ok = _matches_type(v, spec["type"])
                why = "ok" if ok else f"expected {spec['type']}, got {type_of(v)}"
            steps.append({"path": path, "pass": ok, "why": why})
            if not ok:
                bad.append(f"{path}: {why}")
        trace["schema"] = steps
        if bad:
            out.update(decision="invalid", reason="schema: " + "; ".join(bad[:5]))
            return out
    if rules.get("filter"):
        steps = []
        ok = _eval_cond(rules["filter"], doc, steps)
        trace["filter"] = steps
        if not ok:
            out.update(decision="filtered", reason="filter did not match")
            return out
    if rules.get("mapping"):
        steps = []
        fields, errors = _map(rules["mapping"], doc, steps)
        trace["mapping"] = steps
        out["fields"] = fields
        if not errors and len(json.dumps(fields, ensure_ascii=False)) > FIELDS_JSON_MAX:
            errors.append(f"mapped fields larger than {FIELDS_JSON_MAX} characters together")
            out["fields"] = {}
        if errors:
            out.update(decision="invalid", reason="mapping: " + "; ".join(errors[:5]))
            return out
    bk = rules.get("business_key")
    if bk:
        raw = out["fields"].get(bk["field"], _MISSING) if "field" in bk else get_path(doc, bk["path"])
        val = _key_value(raw, bk["type"])
        if val is None:
            trace["business_key"] = {"value": None, "on_missing": bk["on_missing"]}
            if bk["on_missing"] == "reject":
                out.update(decision="invalid", reason=f"business key {bk['entity']}: no usable {bk['type']} value")
                return out
        else:
            out["business_key"] = {"scope": bk["namespace"], "key": f"{bk['entity']}:{val}", "ttl_s": bk["ttl_s"]}
            trace["business_key"] = {"namespace": bk["namespace"], "key": f"{bk['entity']}:{_short(val)}",
                                     "ttl_s": bk["ttl_s"]}
    return out


def fields_text(fields: dict) -> str:
    """Mapped fields as `name: value` lines for the run's prompt (still inside the DATA block)."""
    lines = []
    for k, v in (fields or {}).items():
        s = json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else _cmp_str(v, "")
        lines.append(f"{k}: {s[:VALUE_MAX]}")
    return "\n".join(lines)
