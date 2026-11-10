"""Before and after, on data shaped like the real measurements: is it smaller AND is it right?

    python tests/run.py tool_result_savings -v     (prints the table)

The fixture copies what was measured on a real install (2026-11-10): a shop order has about 107
fields, a third of them empty, with nested line items and a status history, and ten of them are
75,000 to 180,000 characters pretty-printed. Three jobs are compared between the old behaviour (an
API engine's cut at 8,000 characters, head and tail kept) and the new one.

A saving that returns the wrong number is worthless, so every case checks the answer too.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import json
import os
import random
import tempfile

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-savings-"))

import config  # noqa: E402
import engine  # noqa: E402
import mcp_catalog  # noqa: E402
import mcp_client  # noqa: E402
import mcp_hub  # noqa: E402
import mcp_store  # noqa: E402
import tool_result_shaper as shaper  # noqa: E402

_fails = []


def check(name, cond, extra=None):
    print(("ok   " if cond else "FAIL ") + name + ("" if cond or extra is None else f"  [{extra}]"))
    if not cond:
        _fails.append(name)


random.seed(20261110)
STATUSES = ["new", "confirmed", "shipped", "delivered", "returned", "cancelled"]


def order(i):
    items = [{"id": i * 10 + j, "product_id": 500 + j, "variation_id": 9000 + j, "name": f"Nước mắm cốt loại {j}",
              "quantity": random.randint(1, 4), "retail_price": random.choice([85000, 120000, 240000]),
              "discount_each_product": 0, "is_bonus_product": False, "note": None, "weight": 500,
              "images": [f"https://cdn.example/img/{j}-{k}.jpg" for k in range(3)], "fields": None,
              "variation_info": {"sku": f"NM-{j}", "barcode": None, "color": None, "size": None, "detail": None}}
             for j in range(random.randint(1, 4))]
    total = sum(it["quantity"] * it["retail_price"] for it in items)
    o = {"id": 700000 + i, "system_id": 4200 + i, "shop_id": 7, "status": random.choice(STATUSES),
         "status_name": "x", "inserted_at": f"2026-10-{1 + i % 31:02d}T{8 + i % 12:02d}:15:00",
         "updated_at": f"2026-10-{1 + i % 31:02d}T18:00:00", "total_price": total, "cod": total, "shipping_fee": 25000,
         "customer": {"id": f"c{i}", "name": f"Khách hàng {i}", "phone_number": f"09{10000000 + i}", "fb_id": None,
                      "email": None, "gender": None, "date_of_birth": None, "tags": [], "level": None,
                      "order_count": random.randint(1, 9), "succeed_order_count": 1, "returned_order_count": 0},
         "shipping_address": {"full_name": f"Khách hàng {i}", "phone_number": f"09{10000000 + i}",
                              "address": f"{i} Đường số 5, Phường Tân Phong", "province_id": "79",
                              "district_id": "778", "commune_id": "27478", "full_address": f"{i} Đường số 5, Phường "
                              "Tân Phong, Quận 7, Hồ Chí Minh", "post_code": None, "country_code": "84"},
         "items": items, "tags": [], "note": None, "note_print": None, "page_id": "1234567890", "ads_source": None,
         "histories": [{"updated_at": f"2026-10-{1 + i % 31:02d}T{9 + k}:00:00", "editor_id": "u1", "editor": None,
                        "status": {"old": STATUSES[k % 6], "new": STATUSES[(k + 1) % 6]},
                        "note": {"old": None, "new": None}, "extra": None} for k in range(5)],
         "partner": {"partner_id": 3, "extend_code": f"GHN{i}", "is_returned": None, "cod": total, "total_fee": 25000,
                     "delivery_name": None, "delivery_tel": None, "updated_at": None, "extend_update": [
                         {"status": "picked", "location": "Kho Q7", "updated_at": "2026-10-02T08:00:00", "note": None}] * 3},
         "warehouse_info": {"name": "Kho chính", "phone_number": "0900000000", "address": "Quận 7", "province_id": "79"}}
    for k in range(70):                       # the long tail of mostly empty fields a real order carries
        o[f"extra_field_{k}"] = None if k % 3 else (f"value-{k}" if k % 2 else 0)
    return o


ORDERS = [order(i) for i in range(300)]
TRUE_REVENUE = sum(o["total_price"] for o in ORDERS)
TRUE_BY_STATUS = {}
for o in ORDERS:
    TRUE_BY_STATUS[o["status"]] = TRUE_BY_STATUS.get(o["status"], 0) + 1
PAGE_SIZE = 10


def page_text(n):
    chunk = ORDERS[(n - 1) * PAGE_SIZE:n * PAGE_SIZE]
    return "HTTP 200 OK\n---\n" + json.dumps({"data": chunk, "success": True, "page_number": n, "page_size": PAGE_SIZE,
                                              "total_pages": len(ORDERS) // PAGE_SIZE, "total_entries": len(ORDERS)},
                                             indent=2, ensure_ascii=False)


_calls = []


class _Pool:
    async def call_tool(self, spec, tool, args):
        _calls.append(dict(args or {}))
        return page_text(int((args or {}).get("page_number") or 1))


CONN = {"id": "pos1", "connector_id": "savings-test-pos", "label": "POS", "slug": "pos", "namespace": "pos",
        "perm": "readonly", "deny_tools": []}
_real_get = mcp_catalog.get
mcp_catalog.get = lambda cid: ({"id": cid, "name": "POS", "tool_meta": {"read": ["list_*"]}}
                               if cid == "savings-test-pos" else _real_get(cid))


async def _fake_discover(conns, bo_qua=None):
    spec = {"transport": "http", "url": "https://pos.test/mcp", "headers": {}}
    fn = "pos__list_orders"
    return ([{"fn": fn, "server": "pos", "name": "list_orders", "description": "list orders",
              "schema": {"type": "object", "properties": {"page_number": {"type": "integer"}}}, "conn_id": "pos1",
              "connector_id": CONN["connector_id"], "namespace": "pos", "label": "POS"}],
            {fn: {"spec": spec, "tool": "list_orders", "conn": dict(CONN)}})

mcp_store.resolved = lambda enabled_only=True: [dict(CONN, transport="http", url="https://pos.test/mcp", headers={}, env={})]
mcp_client.discover_resolved = _fake_discover
mcp_client.pool = _Pool()
mcp_hub._builtin_tools = lambda *a, **k: ([], {})
config.read_settings = lambda: {"mcp": {"lazy_tools": "off"}}
shaper.settings(force=True)
BRAIN = tempfile.mkdtemp(prefix="savings-brain-")
tools, route = asyncio.run(mcp_hub.discover_all("full", vault_root=BRAIN, include_plugins=False, force_refresh=True))


def as_model(fn, args):
    return asyncio.run(engine._call_tool_for_model(route, fn, args))


def orders_visible_in(text, page=1):
    """How many orders of a page a reader can even identify (the order's own id is in the text)."""
    chunk = ORDERS[(page - 1) * PAGE_SIZE:page * PAGE_SIZE]
    return sum(1 for o in chunk if f'"id": {o["id"]}' in text or f'"id":{o["id"]}' in text)


rows = []
raw = page_text(1)
check("the fixture is as heavy as the real thing (ten orders, tens of thousands of characters)",
      60_000 <= len(raw) <= 220_000, len(raw))

# ---- job 1: "show me the ten latest orders" ----
old = engine._clip_tool_result(raw, ten="pos__list_orders")
new = as_model("pos__list_orders", {})
ref = json.loads(new)["javis_stored_result"]["ref"]
listing = as_model("javis_query", {"ref": ref, "fields": ["id", "status", "total_price", "customer.name"]})
check("before: the cut hid nine of the ten orders", orders_visible_in(old) <= 1, orders_visible_in(old))
got = json.loads(listing)["records"]
check("after: all ten orders, the asked fields, exact values",
      [(r["id"], r["total_price"]) for r in got] == [(o["id"], o["total_price"]) for o in ORDERS[:PAGE_SIZE]])
check("after: the first answer names every non-empty field so the model can ask for them",
      {"id", "status", "total_price", "customer", "items"} <= set(json.loads(new)["javis_stored_result"]["fields"]))
rows.append(("ten latest orders", len(raw), len(old), len(new) + len(listing),
             f"{orders_visible_in(old)} of 10 visible", "10 of 10, exact"))
check("job 1 costs less than the old cut and a tenth of the raw result",
      len(new) + len(listing) <= len(old) and len(new) + len(listing) < len(raw) * 0.1, (len(new), len(listing)))

# ---- job 2: "revenue of the month by status" (300 orders, 30 pages) ----
_calls.clear()
answer = as_model("javis_query", {"tool": "pos__list_orders", "args": {}, "pages": 100,
                                  "sql": "SELECT status, COUNT(*), SUM(total_price) FROM records GROUP BY status ORDER BY status"})
doc = json.loads(answer)
check("after: every page was read by code, none by the model", len(_calls) == 30 and doc["javis_query"]["source"]["complete"] is True)
check("after: counts per status are exact", {r[0]: r[1] for r in doc["rows"]} == TRUE_BY_STATUS, doc["rows"])
check("after: the revenue total is exact", sum(r[2] for r in doc["rows"]) == TRUE_REVENUE)
raw_month = sum(len(page_text(n)) for n in range(1, 31))
old_month = 30 * len(old)
seen_old = sum(orders_visible_in(engine._clip_tool_result(page_text(n)), n) for n in range(1, 31))
check("before: thirty cut pages showed at most one order in ten, so no total was possible", seen_old <= 30, seen_old)
rows.append(("month by status, 300 orders", raw_month, old_month, len(answer),
             f"{seen_old} of 300 visible", "300 of 300, exact"))
check("job 2 puts under 1% of the old cut into the conversation", len(answer) < old_month * 0.01, (len(answer), old_month))

follow = as_model("javis_query", {"ref": doc["javis_query"]["ref"], "sql":
                                  "SELECT i.name, SUM(i.quantity) q FROM records_items i GROUP BY 1 ORDER BY q DESC LIMIT 3"})
true_items = {}
for o in ORDERS:
    for it in o["items"]:
        true_items[it["name"]] = true_items.get(it["name"], 0) + it["quantity"]
top = sorted(true_items.items(), key=lambda kv: -kv[1])[:3]
calls_before = len(_calls)
check("a follow-up question (top products) reuses the dataset and is exact",
      [tuple(r) for r in json.loads(follow)["rows"]] == top and len(_calls) == calls_before, json.loads(follow)["rows"])

# ---- job 3: a mid-size result a CLI engine used to take whole (a 31-day report) ----
report = json.dumps({"data": [{"time": f"2026-10-{d:02d}", "result": {"revenue": d * 1000, "orders": d, "aov": 1000,
                                                                       **{f"m{k}": d * k for k in range(11)}},
                               "success": {"revenue": d * 1000, "orders": d, "aov": 1000,
                                           **{f"m{k}": d * k for k in range(11)}}} for d in range(1, 32)],
                     "summary": {"revenue": sum(d * 1000 for d in range(1, 32)), "orders": sum(range(1, 32))},
                     "pagination": None}, indent=2)
with shaper.for_model():
    shaped = shaper.shape(report, scope=BRAIN)
check("a 31-day report: ALL 31 days in one answer, as a table, with the period summary",
      shaped.kind == "table" and all(f"2026-10-{d:02d}" in shaped.text for d in range(1, 32))
      and str(sum(d * 1000 for d in range(1, 32))) in shaped.text, shaped.kind)
table = json.loads(shaped.text)["result"]["data"]
day17 = dict(zip(table["columns"], table["rows"][16]))
check("the table is exact: day 17 reads back the same numbers",
      day17["time"] == "2026-10-17" and day17["result.revenue"] == 17000 and day17["success.m10"] == 170, day17)
rows.append(("31-day report (CLI engines took it whole)", len(report), len(report), shaped.sent_chars,
             "31 of 31 days", "31 of 31 days, as a table"))
check("job 3 is at least 55% smaller than what a CLI engine received", shaped.sent_chars <= len(report) * 0.45,
      (shaped.sent_chars, len(report)))

print("\n%-44s %12s %12s %10s   %-20s %s" % ("job", "raw chars", "before", "after", "before: data", "after: data"))
for name, r, o, n, bq, aq in rows:
    print("%-44s %12s %12s %10s   %-20s %s" % (name, f"{r:,}", f"{o:,}", f"{n:,}", bq, aq))
stats = mcp_hub.result_size_stats(days=1)
print(f"\nsizes log: {stats['calls']} calls, {stats['raw_chars']:,} raw chars, {stats['sent_chars']:,} handed to a model, "
      f"saved {stats['saved_pct']}% (about {stats['saved_tokens_est']:,} tokens)")
check("the install's own meter agrees that almost nothing was handed over", stats["saved_pct"] > 95, stats["saved_pct"])

if _fails:
    raise SystemExit(f"{len(_fails)} FAIL: " + "; ".join(_fails))
print("All green")
