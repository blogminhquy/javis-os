"""webhook_rules.py - what a hook does with an event BEFORE anything runs (0.274.0, webhook platform M2).

A hook may carry `rules`, all optional, all data (JSON), never code:

    {
      "schema":  {"fields": {"data.order.id": {"type": "string", "required": true},
                             "data.order.total": {"type": "number"}}},
      "filter":  {"all": [{"path": "status", "op": "eq", "value": 1},
                          {"path": "items[*].name", "op": "contains", "value": "TRỢ LÝ AI JAVIS",
                           "quantifier": "any", "case_sensitive": false, "reason": "product_not_found"}]},
      "mapping": {"order_id": "data.order.id",
                  "email": {"path": "data.customer.email", "transform": ["trim", "lower"]},
                  "total": {"path": "data.order.total", "type": "number", "default": 0},
                  "title": {"template": "Đơn {order_id} - {email}"}},
      "dedup":   {"policy_version": 1, "business_paths": ["shop_id", "id", "status"], "ttl_s": 604800,
                  "missing": "quarantine"},
      "correlation": "id"
    }

Order of evaluation, the same in the worker and in simulation (`evaluate`):
  1. parse   the body (JSON, form, or plain text as {"_text": ...}); with rules, broken JSON, JSON that is not UTF-8
             or a content type the rules cannot read is `invalid` (the API calls it quarantined);
  2. schema  required fields and their types. A failing event is `invalid`;
  3. filter  conditions over the payload. A non-matching event is `filtered` (ignored, with reason codes);
  4. mapping named fields picked from the payload, typed and transformed, handed to the run as DATA;
  5. dedup   a business key: the typed tuple of `business_paths`, serialised and hashed (only the hash is kept), in
             the hook's own key space (or a namespace shared on purpose), for `ttl_s`.

Types are strict (spec §5): `1` is not `"1"`; a missing field is missing, never null, 0 or ""; `contains` on an array
needs `quantifier` any or all; an object is never turned into text to be compared. A different shape must be named:
`"as": "number"` on a condition converts a numeric string first. The stored trace keeps which condition passed, the
type it saw and the reason code, never the value (the body already holds it once); `evaluate(..., reveal=True)` (only
simulation) adds the values.

The legacy M2 `business_key` (namespace, entity, path or field, typed normaliser) is still read and ends in the same
hashed key.

Safety: no eval, no regex on payload values, no format-string attribute access (templates substitute `{name}` by a
plain scan), bounded depth, bounded sizes, bounded work. The payload can never change the hook's level, target or
instruction: rules only read it. Nothing here touches the store, the network or a model.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import unicodedata
from decimal import Decimal, InvalidOperation
from typing import Any, Optional
from urllib.parse import parse_qs

RULES_MAX_BYTES = 16 * 1024
PATH_MAX = 200
PATH_SEGMENTS_MAX = 12
NODES_MAX = 100               # filter nodes in all (groups and conditions), spec §5
CONDITIONS_MAX = NODES_MAX    # kept for older readers
DEPTH_MAX = 8
FIELDS_MAX = 40
VALUE_MAX = 2000              # characters of a mapped value / a compared string
LIST_MAX = 50                 # items in an `in` list
ARRAY_SCAN_MAX = 500          # elements of one array a condition looks at
TRACE_VALUE_MAX = 120         # characters of a value shown in a simulation trace
TTL_MIN_S = 60
TTL_MAX_S = 366 * 86400
TTL_DEFAULT_S = 7 * 86400     # spec §6.2 (the legacy business_key format kept its 30 days)
LEGACY_TTL_DEFAULT_S = 30 * 86400
NUM_EXP_MAX = 100             # |exponent| of a number we treat as a number (1e999999 would cost seconds as an int)
NUM_DIGITS_MAX = 60           # digits of an integer literal we parse as a number
DEPTH_PAYLOAD_MAX = 64        # nesting of the payload; deeper is refused as invalid
FIELD_JSON_MAX = 4000         # serialised size of ONE mapped field (an object or list mapped with type any)
FIELDS_JSON_MAX = 32000       # serialised size of all mapped fields together
KEY_PATHS_MAX = 6
CORRELATION_MAX = 120

OPS = ("eq", "ne", "in", "not_in", "exists", "missing", "gt", "gte", "lt", "lte",
       "contains", "starts_with", "ends_with", "empty", "not_empty")
PRESENCE_OPS = ("exists", "missing", "empty", "not_empty")
TYPES = ("string", "number", "integer", "boolean", "object", "array", "any")
KEY_TYPES = ("string", "integer", "email", "phone")
AS_TYPES = ("number", "integer", "string", "boolean")
TRANSFORMS = ("trim", "lower", "upper", "digits", "string", "number", "integer", "boolean", "first", "join",
              "length")
COND_KEYS = {"path", "op", "value", "quantifier", "case_sensitive", "case", "as", "reason"}
NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,39}$")      # mapped field names, also the {name} in templates
NS_RE = re.compile(r"^[a-z0-9][a-z0-9_.-]{0,39}$")
CODE_RE = re.compile(r"^[a-z][a-z0-9_]{0,39}$")
_SEG_RE = re.compile(r"^([^\[\]]*)((?:\[(?:\d{1,4}|\*)\])*)$")
WILD = "*"
_MISSING = object()


class RuleError(ValueError):
    """The rules themselves are wrong (shown to the owner when saving)."""


class TemplateError(ValueError):
    """A `{{...}}` value cannot be filled (missing field, an object inside text): the action does not run."""


# ── paths ──
def parse_path(path: str, wild: bool = True) -> list:
    """`data.items[0].sku` -> ['data', 'items', 0, 'sku']; `items[*].name` -> ['items', '*', 'name']. A leading `$.`
    is allowed. Keys with dots cannot be addressed (kept simple on purpose). `wild=False` refuses `[*]`."""
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
        for idx in re.findall(r"\[(\d{1,4}|\*)\]", m.group(2)):
            out.append(WILD if idx == "*" else int(idx))
    if len(out) > PATH_SEGMENTS_MAX:
        raise RuleError(f"path too deep: {path!r}")
    if WILD in out and not wild:
        raise RuleError(f"`[*]` is not allowed here: {path!r}")
    if out.count(WILD) > 1:
        raise RuleError(f"at most one `[*]` in a path: {path!r}")
    return out


def _step(cur: Any, s: Any) -> Any:
    if isinstance(s, int):
        return cur[s] if isinstance(cur, list) and 0 <= s < len(cur) else _MISSING
    if isinstance(cur, dict) and s in cur:
        return cur[s]
    return _MISSING


def get_path(doc: Any, path) -> Any:
    """The value at `path`, or the _MISSING sentinel. Never raises on the payload's shape. A `[*]` path gives the
    list of what each element holds (an element without it is _MISSING), or _MISSING if there is no array there."""
    segs = parse_path(path) if isinstance(path, str) else path
    cur = doc
    for i, s in enumerate(segs):
        if s == WILD:
            if not isinstance(cur, list):
                return _MISSING
            rest = segs[i + 1:]
            return [get_path(x, rest) for x in cur[:ARRAY_SCAN_MAX]]
        cur = _step(cur, s)
        if cur is _MISSING:
            return _MISSING
    return cur


# ── payload ──
def _bounded(d: Decimal) -> bool:
    return d.is_finite() and (d.is_zero() or abs(d.adjusted()) <= NUM_EXP_MAX)


class _NumberOutOfRange(ValueError):
    """A JSON number no business value has (`1e999999`, a 400-digit integer, NaN, Infinity). It is never turned into
    text: that would let `eq "1e999"` match a number and break "1 is not '1'" (spec §5). The payload is `bad_number`."""


def _parse_float(s: str):
    """JSON floats as exact Decimals, but only of sane size (a huge exponent costs seconds or overflows)."""
    try:
        d = Decimal(s)
    except InvalidOperation:
        raise _NumberOutOfRange(s[:40])
    if not _bounded(d):
        raise _NumberOutOfRange(s[:40])
    return d


def _parse_int(s: str):
    if len(s.lstrip("-")) > NUM_DIGITS_MAX:
        raise _NumberOutOfRange(s[:40])
    return int(s)


def _parse_constant(c: str):
    raise _NumberOutOfRange(c)


def _load_json(text: str) -> tuple:
    """(document, kind) of text known to be UTF-8 and not too deep. A lone surrogate (a `\\ud800` escape, legal to the
    parser) cannot be stored or forwarded as UTF-8, so such a payload is `bad_utf8`, like undecodable bytes."""
    doc = json.loads(text, parse_float=_parse_float, parse_int=_parse_int, parse_constant=_parse_constant)
    if "\\u" in text or "\\U" in text:
        try:
            json.dumps(doc, ensure_ascii=False, default=str).encode("utf-8")
        except UnicodeEncodeError:
            return {"_text": text[:VALUE_MAX]}, "bad_utf8"
    return doc, "json"


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


def _is_json_ct(ct: str) -> bool:
    return "json" in ct


SUPPORTED_CT = ("json", "x-www-form-urlencoded", "text/plain")


def parse_payload(body: bytes, content_type: str) -> tuple:
    """(document, kind). JSON object/array as is; a form as {key: value} (a repeated key as a list); anything
    else as {"_text": text}. kind: json | form | text | too_deep (nested deeper than DEPTH_PAYLOAD_MAX) | bad_json
    (said JSON, did not parse) | bad_utf8 (JSON that is not UTF-8, RFC 8259) | unsupported (a content type rules
    cannot read). Never raises."""
    raw = bytes(body or b"")
    text = raw.decode("utf-8", "replace")
    ct = (content_type or "").lower()
    looks_json = text.lstrip()[:1] in ("{", "[")
    if text.strip() and (_is_json_ct(ct) or (looks_json and not ct)):
        try:
            raw.decode("utf-8")
        except UnicodeDecodeError:
            return {"_text": text[:VALUE_MAX]}, "bad_utf8"
        if _depth(text) > DEPTH_PAYLOAD_MAX:
            return {"_text": text[:VALUE_MAX]}, "too_deep"
        try:
            return _load_json(text)
        except _NumberOutOfRange:
            return {"_text": text[:VALUE_MAX]}, "bad_number"
        except (ValueError, RecursionError):
            return {"_text": text[:VALUE_MAX]}, ("bad_json" if _is_json_ct(ct) else "text")
    if text.strip() and looks_json and not any(x in ct for x in ("x-www-form-urlencoded", "multipart")):
        # A JSON-looking body under text/plain or another label (some senders mislabel): read as JSON if it parses.
        if _depth(text) <= DEPTH_PAYLOAD_MAX:
            try:
                raw.decode("utf-8")
                return _load_json(text)
            except _NumberOutOfRange:
                return {"_text": text[:VALUE_MAX]}, "bad_number"
            except (ValueError, RecursionError, UnicodeDecodeError):
                pass
    if "x-www-form-urlencoded" in ct:
        try:
            pairs = parse_qs(text, keep_blank_values=True)
            return {k: (v[0] if len(v) == 1 else v) for k, v in pairs.items()}, "form"
        except ValueError:
            pass
    if ct and not any(x in ct for x in SUPPORTED_CT) and not ct.startswith("text/"):
        return {"_text": text}, "unsupported"
    return {"_text": text}, "text"


# ── typing ──
def type_of(v: Any) -> str:
    if v is _MISSING:
        return "missing"
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
    numbers. NaN/Infinity are refused. Used by the mapping's typed conversions and by `as: number`, never by a plain
    comparison (spec §5: `1` is not `"1"`)."""
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


def _is_number(v: Any) -> bool:
    return isinstance(v, (int, float, Decimal)) and not isinstance(v, bool)


def _strict_num(v: Any) -> Optional[Decimal]:
    """Only a real number (JSON number), never a string."""
    return _num(v) if _is_number(v) else None


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
    unknown = set(rules) - {"schema", "filter", "mapping", "business_key", "dedup", "correlation"}
    if unknown:
        raise RuleError(f"unknown rule part: {sorted(unknown)[0]}")
    if rules.get("business_key") and rules.get("dedup"):
        raise RuleError("use `dedup` or the older `business_key`, not both")
    out: dict = {}
    if rules.get("schema"):
        out["schema"] = _v_schema(rules["schema"])
    if rules.get("filter"):
        out["filter"] = validate_condition(rules["filter"])
    if rules.get("mapping"):
        out["mapping"] = _v_mapping(rules["mapping"])
    if rules.get("dedup"):
        out["dedup"] = _v_dedup(rules["dedup"], out.get("mapping", {}))
    elif rules.get("business_key"):
        out["dedup"] = _v_bkey(rules["business_key"], out.get("mapping", {}))
    if rules.get("correlation"):
        c = rules["correlation"]
        parse_path(c, wild=False) if isinstance(c, str) else None
        if not isinstance(c, str):
            raise RuleError("correlation is the path of one value (for example an order id)")
        out["correlation"] = c
    return out


def validate_condition(c: Any) -> dict:
    """A filter (or an action's `when`), normalised. Raises RuleError."""
    count = [0]
    return _v_cond(c, 1, count)


def _v_schema(s: Any) -> dict:
    if not isinstance(s, dict) or not isinstance(s.get("fields"), dict):
        raise RuleError("schema needs a `fields` object")
    if len(s["fields"]) > FIELDS_MAX:
        raise RuleError(f"schema has more than {FIELDS_MAX} fields")
    fields = {}
    for path, spec in s["fields"].items():
        parse_path(path, wild=False)
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
    count[0] += 1
    if count[0] > NODES_MAX:
        raise RuleError(f"filter has more than {NODES_MAX} nodes")
    for group in ("all", "any"):
        if group in c:
            items = c[group]
            if set(c) != {group}:
                raise RuleError(f"`{group}` stands alone in its object")
            if not isinstance(items, list) or not items:
                raise RuleError(f"`{group}` needs a non-empty list")
            return {group: [_v_cond(x, depth + 1, count) for x in items]}
    if "not" in c:
        if set(c) != {"not"}:
            raise RuleError("`not` stands alone in its object")
        return {"not": _v_cond(c["not"], depth + 1, count)}
    bad = set(c) - COND_KEYS
    if bad:
        raise RuleError(f"unknown key in a filter condition: {sorted(bad)[0]}")
    op = str(c.get("op") or "eq")
    if op not in OPS:
        raise RuleError(f"unknown filter op: {op}")
    path = str(c.get("path") or "")
    segs = parse_path(path)
    out: dict = {"path": path, "op": op}
    q = c.get("quantifier")
    if q is not None:
        if q not in ("any", "all"):
            raise RuleError(f"filter on {path}: quantifier is any or all")
        out["quantifier"] = q
    elif WILD in segs and op not in ("exists", "missing"):
        raise RuleError(f"filter on {path}: a `[*]` path needs quantifier any or all")
    if "as" in c:
        if c["as"] not in AS_TYPES:
            raise RuleError(f"filter on {path}: `as` is one of {', '.join(AS_TYPES)}")
        out["as"] = c["as"]
    if c.get("reason") is not None:
        if not isinstance(c["reason"], str) or not CODE_RE.match(c["reason"]):
            raise RuleError(f"filter on {path}: reason is a short code (a-z, 0-9, _)")
        out["reason"] = c["reason"]
    cs = c.get("case_sensitive")
    if cs is not None and not isinstance(cs, bool):
        raise RuleError(f"filter on {path}: case_sensitive is true or false")
    if cs is False or c.get("case") == "insensitive":
        out["case_sensitive"] = False
    if op in PRESENCE_OPS:
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
    elif op in ("gt", "gte", "lt", "lte") and (_strict_num(v) is None):
        raise RuleError(f"filter on {path}: `{op}` needs a number")
    elif op in ("contains", "starts_with", "ends_with") and not isinstance(v, str):
        raise RuleError(f"filter on {path}: `{op}` compares text: the value must be a string")
    if isinstance(v, str) and len(v) > VALUE_MAX:
        raise RuleError(f"filter on {path}: value too long")
    out["value"] = v
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


def _ttl(v, default: int) -> int:
    try:
        ttl = int(v) if v is not None else default
    except (TypeError, ValueError):
        raise RuleError("dedup ttl_s must be a number of seconds")
    if not TTL_MIN_S <= ttl <= TTL_MAX_S:
        raise RuleError(f"dedup ttl_s between {TTL_MIN_S} and {TTL_MAX_S}")
    return ttl


def _v_dedup(d: Any, mapping: dict) -> dict:
    """Spec §6.2: {"policy_version": 1, "business_paths": [...], "ttl_s": 604800, "missing": "quarantine",
    "namespace": "<optional: share the key space with other hooks of the brain>"}."""
    if not isinstance(d, dict):
        raise RuleError("dedup must be an object")
    bad = set(d) - {"policy_version", "business_paths", "ttl_s", "missing", "namespace", "fields"}
    if bad:
        raise RuleError(f"unknown key in dedup: {sorted(bad)[0]}")
    paths = d.get("business_paths") or []
    fields = d.get("fields") or []
    if not isinstance(paths, list) or not isinstance(fields, list) or not (paths or fields):
        raise RuleError("dedup needs business_paths (a list of paths) or fields (mapped field names)")
    if len(paths) + len(fields) > KEY_PATHS_MAX:
        raise RuleError(f"dedup: at most {KEY_PATHS_MAX} parts in a key")
    for p in paths:
        parse_path(p, wild=False)
    for f in fields:
        if f not in mapping:
            raise RuleError(f"dedup field {f!r} is not a mapped field")
    pv = d.get("policy_version", 1)
    if isinstance(pv, bool) or not isinstance(pv, int) or not 1 <= pv <= 9999:
        raise RuleError("dedup policy_version is a whole number from 1")
    miss = str(d.get("missing") or "quarantine")
    if miss not in ("quarantine", "accept"):
        raise RuleError("dedup missing: quarantine or accept")
    ns = str(d.get("namespace") or "").strip().lower()
    if ns and not NS_RE.match(ns):
        raise RuleError("dedup namespace: lowercase letters, digits, . _ - (max 40)")
    return {"parts": [{"path": str(p)} for p in paths] + [{"field": str(f)} for f in fields], "policy_version": pv,
            "ttl_s": _ttl(d.get("ttl_s"), TTL_DEFAULT_S), "missing": miss, "namespace": ns}


def _v_bkey(b: Any, mapping: dict) -> dict:
    """The M2 `business_key` format, read into the same shape as `dedup` (one part, a typed normaliser, an entity)."""
    if not isinstance(b, dict):
        raise RuleError("business_key must be an object")
    ns = str(b.get("namespace") or "").strip().lower()
    if ns and not NS_RE.match(ns):
        raise RuleError("business_key namespace: lowercase letters, digits, . _ - (max 40)")
    entity = str(b.get("entity") or "").strip().lower()
    if not NS_RE.match(entity):
        raise RuleError("business_key needs an `entity` (for example order, contact, payment)")
    if b.get("field"):
        if str(b["field"]) not in mapping:
            raise RuleError(f"business_key field {b['field']!r} is not a mapped field")
        part = {"field": str(b["field"])}
    else:
        parse_path(b.get("path") or "", wild=False)
        part = {"path": str(b.get("path"))}
    t = str(b.get("type") or "string")
    if t not in KEY_TYPES:
        raise RuleError(f"business_key type: one of {', '.join(KEY_TYPES)}")
    part["normalize"] = t
    miss = str(b.get("on_missing") or "accept")
    if miss not in ("accept", "reject"):
        raise RuleError("business_key on_missing: accept or reject")
    return {"parts": [part], "policy_version": 1, "entity": entity, "ttl_s": _ttl(b.get("ttl_s"), LEGACY_TTL_DEFAULT_S),
            "missing": "accept" if miss == "accept" else "quarantine", "namespace": ns}


# ── evaluation ──
def _text(v: Any, case_sensitive: bool) -> str:
    """Compared text: NFC first, so "ợ" typed as one code point or as o + two marks is the same letter (spec §15
    Unicode cases), then case folding when asked."""
    s = unicodedata.normalize("NFC", v[:VALUE_MAX])
    return s if case_sensitive else s.casefold()


def _same(a: Any, b: Any, cs: bool) -> bool:
    """Strict equality: numbers with numbers (1 == 1.0), text with text, booleans with booleans, null with null."""
    if _is_number(a) and _is_number(b):
        na, nb = _num(a), _num(b)
        return na is not None and nb is not None and na == nb
    if isinstance(a, str) and isinstance(b, str):
        return _text(a, cs) == _text(b, cs)
    if isinstance(a, bool) and isinstance(b, bool):
        return a == b
    return a is None and b is None


def _convert(v: Any, as_type: str) -> Any:
    """The explicit normalisation a condition asked for (`as`). _MISSING when the value cannot be read so."""
    if as_type == "number":
        n = _num(v)
        return _MISSING if n is None else n
    if as_type == "integer":
        n = _num(v)
        return _MISSING if n is None or n != n.to_integral_value() else int(n)
    if as_type == "string":
        if isinstance(v, str):
            return v
        if isinstance(v, bool):
            return "true" if v else "false"
        if _is_number(v):
            return str(_plain(v))
        return _MISSING
    if as_type == "boolean":
        if isinstance(v, bool):
            return v
        s = v.strip().casefold() if isinstance(v, str) else ""
        return True if s in ("1", "true", "yes", "on") else False if s in ("0", "false", "no", "off") else _MISSING
    return v


def _test_one(op: str, v: Any, want: Any, cs: bool) -> Optional[bool]:
    """One value against one condition. None = the types cannot be compared (type_mismatch)."""
    if op == "eq":
        return _same(v, want, cs)
    if op == "ne":
        return not _same(v, want, cs)
    if op == "in":
        return any(_same(v, w, cs) for w in want)
    if op == "not_in":
        return not any(_same(v, w, cs) for w in want)
    if op in ("gt", "gte", "lt", "lte"):
        a, b = _strict_num(v), _strict_num(want)
        if a is None or b is None:
            return None
        return {"gt": a > b, "gte": a >= b, "lt": a < b, "lte": a <= b}[op]
    if op in ("contains", "starts_with", "ends_with"):
        if not isinstance(v, str) or not isinstance(want, str):
            return None                     # never an object or a number turned into text (spec §5)
        s, w = _text(v, cs), _text(want, cs)
        return w in s if op == "contains" else s.startswith(w) if op == "starts_with" else s.endswith(w)
    return None


def _empty(v: Any) -> bool:
    return v is _MISSING or v is None or v == "" or v == [] or v == {}


def _code(cond: dict, why: str) -> str:
    """The reason code of a failing condition: the owner's label, else `missing_field`, `type_mismatch`,
    `empty_array`, `quantifier_required` or `<field>_mismatch` (spec §5: status_mismatch, missing_field...)."""
    if cond.get("reason"):
        return cond["reason"]
    if why:
        return why
    segs = [s for s in parse_path(cond["path"]) if isinstance(s, str) and s != WILD]
    last = re.sub(r"[^a-z0-9_]", "_", (segs[-1] if segs else "value").lower())[:30].strip("_") or "value"
    return f"{last}_mismatch"


def eval_leaf(cond: dict, doc: Any) -> tuple:
    """(passed, actual, why, error). `why` is '' or a reason code for a failure; `error` is a runtime fault of the
    rule against this payload (`quantifier_required`), which quarantines the event instead of matching or not."""
    op = cond["op"]
    segs = parse_path(cond["path"])
    v = get_path(doc, segs)
    wild = WILD in segs
    if op in ("exists", "missing"):
        present = (v is not _MISSING) if not wild else (v is not _MISSING and any(x is not _MISSING for x in v))
        if wild and v is not _MISSING and cond.get("quantifier") == "all":
            present = bool(v) and all(x is not _MISSING for x in v)
        ok = present if op == "exists" else not present
        return ok, v, "" if ok else ("missing_field" if op == "exists" else "field_present"), ""
    if op in ("empty", "not_empty"):
        if wild:
            if v is _MISSING:
                return op == "empty", v, "", ""
            if not cond.get("quantifier"):
                return False, v, "", "quantifier_required"
            res = [_empty(x) == (op == "empty") for x in v]
            ok = bool(res) and (all(res) if cond["quantifier"] == "all" else any(res))
            return ok, v, "" if ok else ("empty_array" if not v else ""), ""
        ok = _empty(v) == (op == "empty")
        return ok, v, "", ""
    if v is _MISSING:
        return False, v, "missing_field", ""
    q = cond.get("quantifier")
    if wild or isinstance(v, list):
        if not q:
            return False, v, "", "quantifier_required"
        vals = v if wild else v[:ARRAY_SCAN_MAX]
        if not vals:
            return False, v, "empty_array", ""
    else:
        vals = [v]
    cs = cond.get("case_sensitive", True)
    res = []
    for x in vals:
        if x is _MISSING:
            res.append(None)
            continue
        if cond.get("as"):
            x = _convert(x, cond["as"])
            if x is _MISSING:
                res.append(None)
                continue
        res.append(_test_one(op, x, cond.get("value"), cs))
    if q == "all":
        ok = all(r is True for r in res)
    else:
        ok = any(r is True for r in res)
    why = ""
    # Undecided while an unknown item could still change the answer: `any` with no True and some unknown, `all` with
    # no False and some unknown. Then the leaf is unknown (a `not` around it stays unknown), never a definite False.
    decided = any(r is False for r in res) if q == "all" else ok
    if not ok and not decided and any(r is None for r in res):
        unknown = [x for x, r in zip(vals, res) if r is None]
        why = "missing_field" if all(x is _MISSING for x in unknown) else "type_mismatch"
    return ok, v, why, ""


# A leaf that failed because its field is missing or of another type is UNKNOWN, not false: `not` keeps it unknown,
# so `not (status eq 4)` on a payload without `status` is filtered (missing_field), never a match (spec §5, strict
# types). Three values: True, False, None (unknown); the filter passes only on True.
_UNKNOWN_WHY = ("missing_field", "type_mismatch")


def _eval_cond(cond: dict, doc: Any, steps: list, errors: list, reveal: bool) -> Optional[bool]:
    if "all" in cond:
        seen_unknown = False
        for c in cond["all"]:
            r = _eval_cond(c, doc, steps, errors, reveal)
            if r is False:
                return False
            seen_unknown = seen_unknown or r is None
        return None if seen_unknown else True
    if "any" in cond:
        seen_unknown = False
        for c in cond["any"]:
            r = _eval_cond(c, doc, steps, errors, reveal)
            if r is True:
                return True
            seen_unknown = seen_unknown or r is None
        return None if seen_unknown else False
    if "not" in cond:
        r = _eval_cond(cond["not"], doc, steps, errors, reveal)
        if r is None:
            return None
        if r is True:
            # The inner condition held, so `not` fails: say which one (else the reason would be empty).
            steps.append({"path": "(not)", "op": "not", "pass": False, "type": "", "code": cond.get("reason") or
                          "excluded_by_not"})
        return not r
    ok, actual, why, err = eval_leaf(cond, doc)
    step = {"path": cond["path"], "op": cond["op"], "pass": ok, "type": type_of(actual)}
    if not ok:
        step["code"] = err or _code(cond, why)
    if err:
        errors.append(f"{cond['path']}: {err}")
    if reveal:
        step["actual"] = _short(actual)
        if "value" in cond:
            step["value"] = _short(cond["value"])
    steps.append(step)
    if not ok and not err and why in _UNKNOWN_WHY and cond["op"] not in ("exists", "missing", "empty", "not_empty"):
        return None
    return ok


def eval_condition(cond: dict, doc: Any) -> tuple:
    """(passed, reason_code, error) of a validated condition (an action's `when`). Never raises."""
    steps: list = []
    errors: list = []
    try:
        ok = _eval_cond(cond, doc, steps, errors, False) is True
    except Exception as e:                       # fail closed
        return False, "evaluation_error", f"{type(e).__name__}"
    if errors:
        return False, "quantifier_required", errors[0]
    code = next((s.get("code") for s in steps if not s["pass"] and s.get("code")), "")
    return ok, ("" if ok else code or "condition_failed"), ""


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
        return "".join(ch for ch in _scalar_text(v) if ch.isdigit())
    if name == "string":
        return _scalar_text(v) if not isinstance(v, (dict, list)) else json.dumps(_plain(v), ensure_ascii=False)
    if name == "number":
        n = _num(v)
        return None if n is None else n
    if name == "integer":
        n = _num(v)
        return None if n is None else int(n.to_integral_value())
    if name == "boolean":
        if isinstance(v, bool):
            return v
        s = _scalar_text(v).strip().lower()
        return True if s in ("1", "true", "yes", "on", "y") else False if s in ("0", "false", "no", "off", "n", "") \
            else None
    if name == "first":
        return v[0] if isinstance(v, list) and v else (None if isinstance(v, list) else v)
    if name == "join":
        return ", ".join(_scalar_text(x) for x in v[:LIST_MAX] if not isinstance(x, (dict, list))) \
            if isinstance(v, list) else v
    if name == "length":
        return len(v) if isinstance(v, (str, list, dict)) else None
    return v


def _scalar_text(v: Any) -> str:
    """Text of a scalar for templates and transforms (objects are refused by the callers)."""
    if v is None:
        return ""
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, Decimal):
        return format(v, "f") if _bounded(v) else str(v)
    if isinstance(v, str):
        return v[:VALUE_MAX]
    return str(_plain(v))


def _template_refs(tpl: str) -> list:
    return re.findall(r"(?<!\{)\{([A-Za-z_][A-Za-z0-9_]{0,39})\}(?!\})", tpl)


def render_template(tpl: str, fields: dict) -> str:
    """`{name}` replaced by the mapped field's text; nothing else is interpreted (no attribute access, no format
    spec, no nesting). An unknown name stays as written."""
    def rep(m):
        k = m.group(1)
        if k not in fields or fields[k] is None:
            return "" if k in fields else m.group(0)
        v = fields[k]
        return _scalar_text(v) if not isinstance(v, (dict, list)) else json.dumps(_plain(v), ensure_ascii=False)
    return re.sub(r"\{([A-Za-z_][A-Za-z0-9_]{0,39})\}", rep, tpl)[:VALUE_MAX]


_EXPR_RE = re.compile(r"\{\{\s*([A-Za-z_][A-Za-z0-9_]{0,39})((?:\.[A-Za-z0-9_\-]+|\[(?:\d{1,4}|\*)\])*)\s*\}\}")
TEMPLATE_ROOTS = ("payload", "fields", "event", "delivery")


def template_refs(value: Any) -> list:
    """The `{{root.path}}` expressions in a value (for validation when the owner saves an action)."""
    if not isinstance(value, str):
        return []
    return [(m.group(1), m.group(2)) for m in _EXPR_RE.finditer(value)]


def validate_template(value: Any, where: str) -> None:
    for root, rest in template_refs(value):
        if root not in TEMPLATE_ROOTS:
            raise RuleError(f"{where}: {{{{{root}...}}}} is not one of {', '.join(TEMPLATE_ROOTS)}")
        if rest:
            parse_path(rest.lstrip("."))


def render_value(value: Any, ctx: dict) -> Any:
    """Fill a tool argument (spec §8.3). `{{payload.bill_full_name}}` is a data path, nothing else: no function, no
    import, no secret. A value that is ONE expression keeps its type (a list stays a list); expressions inside text
    must be text, numbers or booleans. A missing field raises TemplateError: never an empty recipient, amount or id.
    The older `{name}` form reads a mapped field; `{_delivery_id}`, `{_event_id}`, `{_hook_id}` the run's ids."""
    if not isinstance(value, str):
        return value

    def lookup(root: str, rest: str) -> Any:
        base = ctx.get(root, _MISSING)
        if base is _MISSING:
            raise TemplateError(f"{{{{{root}}}}} is not available")
        v = get_path(base, parse_path(rest.lstrip("."))) if rest else base
        if v is _MISSING or v is None or (isinstance(v, list) and any(x is _MISSING for x in v)):
            raise TemplateError(f"{{{{{root}{rest}}}}} is missing in this event")
        return v

    whole = _EXPR_RE.fullmatch(value.strip())
    if whole and value.strip() == value:
        return _plain(lookup(whole.group(1), whole.group(2)))

    def rep(m):
        v = lookup(m.group(1), m.group(2))
        if isinstance(v, (dict, list)):
            raise TemplateError(f"{{{{{m.group(1)}{m.group(2)}}}}} is an object or a list: use it as the whole value")
        return _scalar_text(v)
    out = _EXPR_RE.sub(rep, value)
    fields = ctx.get("fields") or {}
    legacy = {"_delivery_id": (ctx.get("delivery") or {}).get("id"), "_event_id": (ctx.get("event") or {}).get("id"),
              "_hook_id": (ctx.get("event") or {}).get("hook_id")}

    def rep_old(m):
        k = m.group(1)
        if k in legacy and legacy[k]:
            return str(legacy[k])
        if k in fields:
            v = fields[k]
            if v is None:
                raise TemplateError(f"{{{k}}} is missing in this event")
            if isinstance(v, (dict, list)):
                raise TemplateError(f"{{{k}}} is an object or a list")
            return _scalar_text(v)
        return m.group(0)                        # not a field: literal text
    return re.sub(r"(?<!\{)\{([A-Za-z_][A-Za-z0-9_]{0,39})\}(?!\})", rep_old, out)[:VALUE_MAX]


def _map(mapping: dict, doc: Any, trace: list, reveal: bool) -> tuple:
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
                    v = _scalar_text(v)
                if not _matches_type(v, t):
                    errors.append(f"{name}: expected {t}, got {type_of(v)}")
                    src = "type_error"
        if v is _MISSING or (v is None and spec.get("required")):
            if spec.get("required"):
                errors.append(f"{name}: required field missing")
            v = None
        if isinstance(v, list) and any(x is _MISSING for x in v):
            v = [x for x in v if x is not _MISSING]
        pv = _plain(v)
        if isinstance(pv, (dict, list)) and len(json.dumps(pv, ensure_ascii=False)) > FIELD_JSON_MAX:
            errors.append(f"{name}: value larger than {FIELD_JSON_MAX} characters (map a smaller part)")
            src = "too_large"
            pv = None
        fields[name] = pv
        step = {"field": name, "source": src, "type": type_of(pv)}
        if reveal:
            step["value"] = _short(pv)
        trace.append(step)
    return fields, errors


def _normalise_key(v: Any, t: str) -> Any:
    """The legacy typed normalisers, so `"A-001 "` and `"a-001"` do not become two orders by accident only where the
    type says so. _MISSING = no usable value."""
    if t == "integer":
        n = _num(v)
        if n is None or n != n.to_integral_value():
            return _MISSING
        return int(n)
    s = (_scalar_text(v)).strip()
    if t == "email":
        s = s.lower()
        return s if "@" in s and len(s) <= 254 else _MISSING
    if t == "phone":
        d = "".join(ch for ch in s if ch.isdigit())
        if d.startswith("84") and len(d) >= 11:     # +84 912... and 0912... are the same Vietnamese number
            d = "0" + d[2:]
        return d if 6 <= len(d) <= 15 else _MISSING
    return s or _MISSING


def _canon(v: Any) -> list:
    """[type, text] of one key part: the TYPED serialisation that is hashed (spec §6.2: `1+23` and `12+3`, `1` and
    `"1"` are different keys)."""
    if isinstance(v, bool):
        return ["boolean", "true" if v else "false"]
    if isinstance(v, int):
        return ["number", str(v)]          # 1 and 1.0 are one key, as `eq` says they are equal
    if isinstance(v, (Decimal, float)):
        d = _num(v)
        if d is not None and d == d.to_integral_value():
            return ["number", str(int(d))]
        return ["number", format(d.normalize(), "f") if d is not None else str(v)]
    return ["string", unicodedata.normalize("NFC", str(v))]   # one key whenever eq says the texts are equal


def business_key(spec: dict, doc: Any, fields: dict) -> tuple:
    """(key, why). key = {"shared": namespace or "", "policy": n, "hash": sha256 hex, "ttl_s": n, "parts": [...]}
    or None; why = '' or a reason code (missing_key_field, key_not_scalar). The values themselves are not returned
    apart from `parts` (types and paths), so nothing but the hash is stored."""
    parts, shape = [], []
    for p in spec["parts"]:
        raw = fields.get(p["field"], _MISSING) if "field" in p else get_path(doc, p["path"])
        if raw is _MISSING or raw is None:
            return None, "missing_key_field"
        if isinstance(raw, (dict, list)):
            return None, "key_not_scalar"
        if p.get("normalize"):
            raw = _normalise_key(raw, p["normalize"])
            if raw is _MISSING:
                return None, "missing_key_field"
        parts.append(_canon(raw))
        shape.append({"part": p.get("path") or p.get("field"), "type": parts[-1][0]})
    head = [spec.get("entity") or "", int(spec.get("policy_version") or 1)]
    blob = json.dumps([head, parts], ensure_ascii=False, separators=(",", ":"))
    h = hashlib.sha256(blob.encode("utf-8")).hexdigest()
    return {"shared": spec.get("namespace") or "", "policy": int(spec.get("policy_version") or 1), "hash": h,
            "ttl_s": int(spec["ttl_s"]), "parts": shape}, ""


def evaluate(rules: dict, body: bytes, content_type: str, extra: Optional[dict] = None,
             reveal: bool = False) -> dict:
    """Run parse -> schema -> filter -> mapping -> dedup key. Pure and deterministic.

    Returns {
      "decision": "run" | "invalid" | "filtered",
      "reason": "",                # a reason code (missing_field, status_mismatch...) or the schema/mapping problem
      "reasons": [...],            # every failing condition's code
      "fields": {...},             # mapped fields (JSON-safe), {} without a mapping
      "business_key": None | {"shared", "policy", "hash", "ttl_s", "parts"},
      "correlation": "",           # the value at rules.correlation (an order id to search the log by)
      "trace": {"parse": kind, "schema": [...], "filter": [...], "mapping": [...], "business_key": {...}},
    }
    `reveal` (simulation only) adds the values seen to the trace; the stored trace never holds them."""
    rules = rules or {}
    doc, kind = parse_payload(body, content_type)
    if extra and isinstance(doc, dict):
        doc = dict(doc, **extra)        # e.g. `_event` from the provider adapter (M4); the payload cannot set it
    trace: dict = {"parse": kind}
    out = {"decision": "run", "reason": "", "reasons": [], "fields": {}, "business_key": None, "correlation": "",
           "trace": trace}
    if rules:
        bad = {"too_deep": f"payload_too_deep (nested deeper than {DEPTH_PAYLOAD_MAX})",
               "bad_json": "invalid_json", "bad_utf8": "invalid_utf8", "bad_number": "number_out_of_range",
               "unsupported": "unsupported_content_type"}.get(kind)
        if bad:
            out.update(decision="invalid", reason=bad, reasons=[bad.split(" ")[0]])
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
            out.update(decision="invalid", reason="schema: " + "; ".join(bad[:5]), reasons=["schema_mismatch"])
            return out
    if rules.get("filter"):
        steps, errors = [], []
        ok = _eval_cond(rules["filter"], doc, steps, errors, reveal) is True
        trace["filter"] = steps
        codes = [s["code"] for s in steps if not s["pass"] and s.get("code")]
        if errors:
            # A rule that cannot be applied to this payload (an array where a value was expected) is never read as
            # "match" or "no match": the event is quarantined with the reason (spec §5).
            out.update(decision="invalid", reason="filter: " + "; ".join(errors[:3]), reasons=["quantifier_required"])
            return out
        if not ok:
            out.update(decision="filtered", reason=(codes[0] if codes else "filter_mismatch"),
                       reasons=list(dict.fromkeys(codes))[:10] or ["filter_mismatch"])
            return out
    if rules.get("mapping"):
        steps = []
        fields, errors = _map(rules["mapping"], doc, steps, reveal)
        trace["mapping"] = steps
        out["fields"] = fields
        if not errors and len(json.dumps(fields, ensure_ascii=False)) > FIELDS_JSON_MAX:
            errors.append(f"mapped fields larger than {FIELDS_JSON_MAX} characters together")
            out["fields"] = {}
        if errors:
            out.update(decision="invalid", reason="mapping: " + "; ".join(errors[:5]), reasons=["mapping_error"])
            return out
    if rules.get("correlation"):
        c = get_path(doc, rules["correlation"])
        if c is not _MISSING and c is not None and not isinstance(c, (dict, list)):
            out["correlation"] = _scalar_text(c)[:CORRELATION_MAX]
    spec = rules.get("dedup")
    if spec:
        key, why = business_key(spec, doc, out["fields"])
        if key is None:
            trace["business_key"] = {"value": None, "missing": spec["missing"], "code": why}
            if spec["missing"] == "quarantine":
                out.update(decision="invalid", reason=why, reasons=[why])
                return out
        else:
            out["business_key"] = key
            tk = {"policy": key["policy"], "hash": key["hash"][:16], "ttl_s": key["ttl_s"], "parts": key["parts"],
                  "shared": key["shared"]}
            if reveal:
                tk["values"] = [_short(fields_get(doc, out["fields"], p)) for p in spec["parts"]]
            trace["business_key"] = tk
    return out


def fields_get(doc: Any, fields: dict, part: dict) -> Any:
    return fields.get(part["field"]) if "field" in part else get_path(doc, part["path"])


def fields_text(fields: dict) -> str:
    """Mapped fields as `name: value` lines for the run's prompt (still inside the DATA block)."""
    lines = []
    for k, v in (fields or {}).items():
        s = json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else _scalar_text(v)
        lines.append(f"{k}: {s[:VALUE_MAX]}")
    return "\n".join(lines)
