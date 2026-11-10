"""Does the result layer hold when the data, the store and the traffic grow?

    python tests/run.py tool_result_scale -v     (prints the measurements)

Measured, not assumed. Each case prints what it took and checks a ceiling loose enough for a slow CI
machine and tight enough to catch a change that makes the cost grow with the wrong thing:

  1. one result of 150 KB, 1.3 MB and 6.4 MB: shaping time grows with the size, the view does not;
  2. a store holding far more than its ceiling: writes stay quick, the oldest copies leave;
  3. a dataset near the size limit (40,000 records): load, a grouped SQL query, and the follow-up question;
  4. 200 pages read by javis_query in one call;
  5. 24 large results at once: the event loop keeps answering while they are parsed and stored;
  6. a tool search over 600 tools.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import json
import os
import random
import tempfile
import time
import tracemalloc

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-scale-"))

import config  # noqa: E402
import engine  # noqa: E402
import mcp_catalog  # noqa: E402
import mcp_client  # noqa: E402
import mcp_hub  # noqa: E402
import mcp_store  # noqa: E402
import tool_result_query as query  # noqa: E402
import tool_result_shaper as shaper  # noqa: E402
import tool_result_store as store  # noqa: E402

_fails = []
random.seed(11)


def check(name, cond, extra=None):
    print(("ok   " if cond else "FAIL ") + name + ("" if cond or extra is None else f"  [{extra}]"))
    if not cond:
        _fails.append(name)


def order(i, pad=40):
    return {"id": i, "status": ("new", "done", "returned", "cancelled")[i % 4], "total": (i % 97) * 1000,
            "created_at": f"2026-{1 + i % 12:02d}-{1 + i % 28:02d}T10:00:00", "note": None, "tags": [],
            "customer": {"name": f"Khách {i}", "phone": f"09{10000000 + i}", "city": ("HN", "HCM", "DN")[i % 3]},
            "items": [{"sku": f"SP{j}", "qty": 1 + (i + j) % 3, "price": 50000 * (j + 1)} for j in range(1 + i % 3)],
            "pad": "x" * pad, **{f"e{k}": None for k in range(20)}}


def payload(n, pad=40):
    return json.dumps({"data": [order(i, pad) for i in range(n)], "total_entries": n, "page_number": 1}, indent=2)


config.read_settings = lambda: {"mcp": {"lazy_tools": "off"}}
shaper.settings(force=True)
store.configure(os.path.join(os.environ["JAVIS_STATE_DIR"], "scale.sqlite3"))

# ============================================================
# 1. One result, growing
# ============================================================
print("\n-- one result --")
views, times = [], []
with shaper.for_model():
    shaper.shape(payload(20), scope="/scale")           # warm-up: first use loads the encryption key
for label, n in (("150 KB", 170), ("1.3 MB", 1400), ("6.4 MB", 7000)):
    raw = payload(n)
    t0 = time.time()
    with shaper.for_model():
        s = shaper.shape(raw, scope="/scale")
    dt = time.time() - t0                               # timed without the memory tracer, which slows Python 3x
    tracemalloc.start()
    with shaper.for_model():
        shaper.shape(raw, scope="/scale")
    peak = tracemalloc.get_traced_memory()[1]
    tracemalloc.stop()
    views.append(s.sent_chars)
    times.append((len(raw), dt))
    print(f"   {label:>7}: raw {len(raw):>10,} chars -> view {s.sent_chars:,} chars ({s.kind}) in {dt * 1000:6.0f} ms, "
          f"peak memory {peak / len(raw):.1f}x the result")
    check(f"{label}: the view stays under the inline cap whatever the size", s.sent_chars <= shaper.INLINE_MAX_DEFAULT and s.ref)
    check(f"{label}: shaping uses a bounded multiple of the result's own size in memory", peak < len(raw) * 14, peak / len(raw))
check("the view does not grow with the result", max(views) - min(views) < 2500, views)
per_mb = [dt / (n / 1e6) for n, dt in times]
check("shaping time grows in step with the size, not faster", per_mb[2] < per_mb[0] * 4 + 0.2 and times[2][1] < 6, per_mb)

# ============================================================
# 2. A store far over its ceiling
# ============================================================
print("\n-- store --")
os.environ["JAVIS_TOOL_RESULT_STORE_MB"] = "16"
noise = "".join(random.choice("abcdefghijklmnopqrstuvwxyz0123456789 ") for _ in range(400_000))   # does not compress
t0 = time.time()
refs = [store.put(noise + str(i), scope="/scale") for i in range(150)]                                # about 60 MB raw
put_ms = (time.time() - t0) * 1000 / len(refs)
store.sweep()
st = store.stats()
t0 = time.time()
for r in refs[-20:]:
    assert store.get(r, "/scale") is not None
get_ms = (time.time() - t0) * 1000 / 20
print(f"   150 results of 400 KB: {put_ms:.1f} ms per write, {get_ms:.1f} ms per read, "
      f"{st['items']} kept in {st['stored_bytes'] / 1e6:.1f} MB (ceiling 16 MB)")
check("the store never passes its ceiling", st["stored_bytes"] <= 16 * 1024 * 1024, st)
check("the newest copies are the ones kept", store.get(refs[-1], "/scale") is not None and store.get(refs[0], "/scale") is None)
check("a write stays quick however full the store is", put_ms < 400, put_ms)
check("a read stays quick", get_ms < 200, get_ms)
os.environ.pop("JAVIS_TOOL_RESULT_STORE_MB")

# ============================================================
# 3. A dataset at the size limit
# ============================================================
print("\n-- query --")
N = 40_000
records = [shaper.lean_copy(order(i, 150), True) for i in range(N)]
body = query.make_dataset(records, {"source_tool": "t"})
t0 = time.time()
loaded = query.load(body)
t_load = time.time() - t0
t0 = time.time()
out = json.loads(query.run_sql(loaded, "tr_x", "SELECT status, COUNT(*), SUM(total) FROM records GROUP BY status ORDER BY status"))
t_sql = time.time() - t0
tracemalloc.start()
query.run_sql(loaded, "tr_x", "SELECT COUNT(*) FROM records")
peak = tracemalloc.get_traced_memory()[1]
tracemalloc.stop()
t0 = time.time()
out2 = json.loads(query.run_sql(loaded, "tr_x", "SELECT i.sku, SUM(i.qty * i.price) FROM records_items i JOIN records r "
                                               "ON r._row = i._record WHERE r.status = 'done' GROUP BY i.sku ORDER BY 2 DESC"))
t_join = time.time() - t0
want = {}
for i in range(N):
    want[("new", "done", "returned", "cancelled")[i % 4]] = want.get(("new", "done", "returned", "cancelled")[i % 4], 0) + (i % 97) * 1000
print(f"   {N:,} records, {len(body) / 1e6:.1f} MB: parse {t_load:.2f} s, grouped query {t_sql:.2f} s, "
      f"join over {sum(1 + i % 3 for i in range(N)):,} line items {t_join:.2f} s, peak memory {peak / 1e6:.0f} MB")
check("totals over 40,000 records are exact", {r[0]: r[2] for r in out["rows"]} == want)
# the next question on the same stored result reuses its database
query.clear_database_cache()
t0 = time.time()
query.run_sql(loaded, "tr_x", "SELECT COUNT(*) FROM records", cache_key="scale|tr_x")
t_first = time.time() - t0
t0 = time.time()
again = json.loads(query.run_sql(loaded, "tr_x", "SELECT status, SUM(total) FROM records GROUP BY 1 ORDER BY 1", cache_key="scale|tr_x"))
t_next = time.time() - t0
print(f"   first question {t_first:.2f} s (loads the records), the next one {t_next * 1000:.0f} ms (same database)")
check("a follow-up question does not load the records again", t_next < t_first / 4 and t_next < 1.0, (t_first, t_next))
check("...and is just as exact", {r[0]: r[1] for r in again["rows"]} == want)
for i in range(4):                       # other results come and go: the cache stays small
    query.run_sql({"kind": "records", "pointer": "/", "records": [{"a": j} for j in range(1500)]}, f"tr_{i}",
                  "SELECT COUNT(*) FROM records", cache_key=f"scale|tr_{i}")
check("the database cache is bounded", len(query._db_cache) <= query.DB_CACHE_ITEMS, len(query._db_cache))
query.clear_database_cache()
check("the join over line items answers", len(out2["rows"]) == 3 and out2["rows"][0][1] > 0, out2["rows"])
check("a dataset at the limit is queried in seconds, not minutes", t_load + t_sql < 30 and t_join < 30, (t_load, t_sql, t_join))
check("memory for the query stays within a few times the dataset", peak < len(body) * 8, peak / len(body))

# ============================================================
# 4 and 5. Through the hub: 200 pages in one call, 24 large results at once
# ============================================================
print("\n-- hub --")
PAGE = {n: json.dumps({"data": [order((n - 1) * 10 + i, 2500) for i in range(10)], "page_number": n,
                       "total_pages": 200, "total_entries": 2000}, indent=2) for n in range(1, 201)}
BIG = payload(150, 400)
_n_calls = [0]


class _Pool:
    async def call_tool(self, spec, tool, args):
        _n_calls[0] += 1
        await asyncio.sleep(0)
        if tool == "list_orders":
            return PAGE.get(int((args or {}).get("page_number") or 1), "{}")
        return BIG


CONN = {"id": "pos1", "connector_id": "scale-test-pos", "label": "POS", "slug": "pos", "namespace": "pos",
        "perm": "readonly", "deny_tools": []}
_real_get = mcp_catalog.get
mcp_catalog.get = lambda cid: ({"id": cid, "name": "POS", "tool_meta": {"read": ["list_*", "get_*"]}}
                               if cid == "scale-test-pos" else _real_get(cid))


async def _fake_discover(conns, bo_qua=None):
    spec = {"transport": "http", "url": "https://pos.test/mcp", "headers": {}}
    tools, route = [], {}
    for name in ("list_orders", "get_big"):
        fn = f"pos__{name}"
        route[fn] = {"spec": spec, "tool": name, "conn": dict(CONN)}
        tools.append({"fn": fn, "server": "pos", "name": name, "description": name,
                      "schema": {"type": "object", "properties": {"page_number": {"type": "integer"}}},
                      "conn_id": "pos1", "connector_id": CONN["connector_id"], "namespace": "pos", "label": "POS"})
    return tools, route

mcp_store.resolved = lambda enabled_only=True: [dict(CONN, transport="http", url="https://pos.test/mcp", headers={}, env={})]
mcp_client.discover_resolved = _fake_discover
mcp_client.pool = _Pool()
mcp_hub._builtin_tools = lambda *a, **k: ([], {})
BRAIN = tempfile.mkdtemp(prefix="scale-brain-")


async def hub_cases():
    tools, route = await mcp_hub.discover_all("full", vault_root=BRAIN, include_plugins=False, force_refresh=True)
    raw_pages = sum(len(p) for p in PAGE.values())
    t0 = time.time()
    ans = await engine._call_tool_for_model(route, "javis_query", {
        "tool": "pos__list_orders", "args": {}, "pages": 200,
        "sql": "SELECT COUNT(*), COUNT(DISTINCT id), SUM(total) FROM records"})
    t_pages = time.time() - t0
    doc = json.loads(ans)
    print(f"   200 pages ({raw_pages / 1e6:.1f} MB raw) in one javis_query call: {t_pages:.1f} s, "
          f"{_n_calls[0]} source calls, answer {len(ans)} chars")
    check("200 pages become one exact answer",
          doc["rows"] == [[2000, 2000, sum((i % 97) * 1000 for i in range(2000))]] and doc["javis_query"]["source"]["complete"] is True,
          doc.get("rows"))
    check("the answer is a few hundred characters for megabytes read", len(ans) < 800 and raw_pages > 4_000_000, len(ans))
    check("200 pages are gathered in well under the fetch time limit", t_pages < 120, t_pages)

    # the loop must keep ticking while 24 results of ~200 KB are parsed, stored and turned into views
    lags, stop = [], [False]

    async def ticker():
        last = time.perf_counter()
        while not stop[0]:
            await asyncio.sleep(0.005)
            now = time.perf_counter()
            lags.append(now - last - 0.005)
            last = now
    tick = asyncio.create_task(ticker())
    await asyncio.sleep(0.05)
    t0 = time.time()
    outs = await asyncio.gather(*[engine._call_tool_for_model(route, "pos__get_big", {}) for _ in range(24)])
    t_many = time.time() - t0
    stop[0] = True
    await tick
    worst = max(lags) * 1000
    print(f"   24 results of {len(BIG) / 1000:.0f} KB at once: {t_many:.2f} s in all, worst event-loop stall {worst:.0f} ms")
    check("every one of the 24 got its own view and reference",
          len({json.loads(o)["javis_stored_result"]["ref"] for o in outs}) == 24)
    check("the event loop is never held for long while results are shaped", worst < 250, worst)
    check("24 large results are served in a few seconds", t_many < 30, t_many)

asyncio.run(hub_cases())

# ============================================================
# 6. Tool search over many tools
# ============================================================
print("\n-- tool search --")
pool = [{"fn": f"src{i % 40}__tool_{i}", "name": f"tool_{i}", "namespace": f"src{i % 40}", "label": f"Source {i % 40}",
         "description": f"Does thing {i} for orders, customers and reports. " + "detail " * 60,
         "schema": {"type": "object", "properties": {f"p{k}": {"type": "string", "description": "d" * 40} for k in range(8)}}}
        for i in range(600)]
_t, r2 = mcp_hub._lazy_tools_and_route([], {}, pool, {}, 8)
t0 = time.time()
found = asyncio.run(r2[mcp_hub._LAZY_SEARCH]["call"]({"query": "orders report tool_17"}))
t_search = (time.time() - t0) * 1000
print(f"   600 tools: search in {t_search:.0f} ms, answer {len(found):,} chars")
check("a search over 600 tools is quick", t_search < 1500, t_search)
check("its answer does not grow with the number of tools", len(found) <= mcp_hub._SEARCH_BUDGET_CHARS + 2500, len(found))

if _fails:
    raise SystemExit(f"{len(_fails)} FAIL: " + "; ".join(_fails))
print("\nAll green")
