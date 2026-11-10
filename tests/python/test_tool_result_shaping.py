"""Large tool results: stored whole, shown as a view, read back or computed by javis_query.

    python tests/run.py tool_result_shaping

Measured on a real install (2026-11-10): ten shop orders are 99,000 to 183,000 characters and the
API engines cut every result at 8,000, head and tail kept, so a model saw the grand total and not
one whole order. This file pins the replacement:

  1. the store: encrypted, scoped to one brain, bounded, fail closed;
  2. the shaper: errors and small results word for word, JSON compacted, a large result replaced
     by a view of WHOLE records with a reference, nothing cut in the middle;
  3. javis_query: read chosen fields page by page, or compute over all records with read-only SQL;
  4. the hub: only a model's tool loop gets shaped results, internal callers and plugin hooks get
     the tool's own text, sizes land in their own log, and a tool that writes can never be paged.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import json
import os
import tempfile
import time

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-tool-results-"))

import config  # noqa: E402
import engine  # noqa: E402
import mcp_catalog  # noqa: E402
import mcp_client  # noqa: E402
import mcp_hub  # noqa: E402
import mcp_store  # noqa: E402
import tool_result_query as query  # noqa: E402
import tool_result_shaper as shaper  # noqa: E402
import tool_result_store as store  # noqa: E402
import tool_result_tools  # noqa: E402

_fails = []


def check(name, cond, extra=None):
    print(("ok   " if cond else "FAIL ") + name + ("" if cond or extra is None else f"  [{extra}]"))
    if not cond:
        _fails.append(name)


def order(i, big=False):
    return {"id": 1000 + i, "status": ("done", "new", "returned")[i % 3], "note": None, "tags": [],
            "customer": {"name": f"Khách {i}", "phone": f"09{10000000 + i}", "address": None},
            "items": [{"sku": f"SP{j}", "qty": 1 + (i + j) % 3, "price": 100000 * (j + 1), "discount": None}
                      for j in range(1 + i % 3)],
            "total": (1 + i % 9) * 100000, "created_at": f"2026-10-{1 + i % 28:02d}T10:00:00",
            **{f"empty_{k}": None for k in range(40)},
            "history": [{"at": "2026-10-01", "by": "staff", "what": "x" * (4000 if big else 200)}] * 4}


def page(n_orders, page_number=1, total_pages=1, total=None, start=0, big=False):
    return "HTTP 200 OK\n---\n" + json.dumps(
        {"data": [order(start + i, big) for i in range(n_orders)], "success": True, "page_number": page_number,
         "page_size": n_orders, "total_pages": total_pages, "total_entries": total or n_orders},
        indent=2, ensure_ascii=False)


# ============================================================
# 1. The store
# ============================================================
store.configure(os.path.join(os.environ["JAVIS_STATE_DIR"], "results-test.sqlite3"))
check("encryption is available in the test environment", store.available())
raw = page(40, total_pages=9, total=341)
ref = store.put(raw, scope="/brain-a", tool="pos_order", conn_id="c1")
check("put returns a reference", ref.startswith(store.REF_PREFIX), ref)
got = store.get(ref, "/brain-a")
check("the stored text comes back byte for byte", bool(got) and got["text"] == raw)
check("another brain cannot read it", store.get(ref, "/brain-b") is None)
_real_dir = tempfile.mkdtemp(prefix="scope-real-")
_link = _real_dir + "-link"
os.symlink(_real_dir, _link)
_r = store.put("x" * 3000, scope=_link + "/")
check("the same brain reached by another spelling of its path reads its own result",
      _r and store.get(_r, _real_dir) is not None and store.get(_r, _real_dir + "/") is not None)
check("an unknown reference reads as nothing", store.get("tr_" + "0" * 24, "/brain-a") is None)
check("a malformed reference reads as nothing", store.get("../../etc/passwd", "/brain-a") is None)
with open(os.path.join(os.environ["JAVIS_STATE_DIR"], "results-test.sqlite3"), "rb") as f:
    on_disk = f.read()
check("no plain customer text on disk", "Khách".encode("utf-8") not in on_disk and b"0910000000" not in on_disk)
short = store.put("x" * 5000, scope="/brain-a", ttl=60)
store.sweep(now=time.time() + 120)
check("an expired result is swept", store.get(short, "/brain-a") is None and store.get(ref, "/brain-a") is not None)
os.environ["JAVIS_TOOL_RESULT_STORE_MB"] = "8"
import random  # noqa: E402
random.seed(7)
noise = "".join(random.choice("abcdefghijklmnopqrstuvwxyz0123456789 ") for _ in range(1_500_000))
olds = [store.put(noise + str(i), scope="/brain-a") for i in range(14)]
store.sweep()
check("the store stays under its size ceiling by dropping the oldest",
      store.stats()["stored_bytes"] <= 8 * 1024 * 1024 and store.get(olds[0], "/brain-a") is None
      and store.get(olds[-1], "/brain-a") is not None, store.stats())
os.environ.pop("JAVIS_TOOL_RESULT_STORE_MB")
store.configure(os.path.join(os.environ["JAVIS_STATE_DIR"], "no-key.sqlite3"),
                crypto=(lambda s: s, lambda s: s, lambda: False))
check("without an encryption key nothing is stored", store.put(raw, scope="/brain-a") == "")
store.configure(os.path.join(os.environ["JAVIS_STATE_DIR"], "results-test2.sqlite3"))

# ============================================================
# 2. The shaper
# ============================================================
shaper.settings(force=True)
check("an internal caller gets the tool's own text", shaper.shape(raw).text == raw and shaper.shape(raw).kind == "internal")
with shaper.for_model():
    err = "ERROR: upstream said no " + "x" * 20000
    check("an error is returned word for word", shaper.shape(err).text == err)
    tiny = json.dumps({"ok": True, "n": None}, indent=2)
    check("a small result is returned word for word", shaper.shape(tiny).text == tiny)

    mid = json.dumps({"data": [{"a": 1, "b": None, "c": "", "d": [], "e": 0, "f": False}] * 40, "next": None,
                      "items": []}, indent=2)
    s = shaper.shape(mid)
    doc = json.loads(s.text)
    check("a medium result is compacted, not stored", s.kind == "compact" and not s.ref and s.sent_chars < s.raw_chars / 2)
    check("a result that fits loses NOTHING but its indentation: a read-edit-write round trip stays whole",
          doc == json.loads(mid) and "\n" not in s.text)

    s = shaper.shape(raw, tool="pos_order", conn_id="c1", scope="/brain-a")
    doc = json.loads(s.text)
    head = doc["javis_stored_result"]
    check("a large result becomes a view with a reference", s.kind == "preview" and s.ref == head["ref"])
    check("the view fits the API engines' own cap", s.sent_chars <= shaper.INLINE_MAX_DEFAULT, s.sent_chars)
    check("the view says how many records the result holds", head["records_in_result"] == 40 and head["records_at"] == "/data")
    check("totals and paging markers survive in the envelope",
          doc["envelope"] == {"success": True, "page_number": 1, "page_size": 40, "total_pages": 9, "total_entries": 341},
          doc.get("envelope"))
    check("every shown record is whole",
          head["shown_as"] == "full" and len(doc["records"]) == head["shown_records"] >= 1
          and all(r["items"] and r["history"][0]["what"] == "x" * 200 for r in doc["records"]))
    check("field names are listed so the model can pick them", {"id", "total", "customer", "items"} <= set(head["fields"]))
    check("the reference reads back the exact original", store.get(s.ref, "/brain-a")["text"] == raw)
    check("the notice names the tool that reads the rest", "javis_query" in head["note"])

    flat = json.dumps({"data": [{"day": f"2026-10-{1 + i % 28:02d}", "channel": ("fb", "zalo", "web")[i % 3],
                                 "stats": {"revenue": i * 1000, "orders": i, "refund": None}, "tags": ["a", "b"],
                                 "note": None} for i in range(140)], "total": 140, "next": None}, indent=2)
    s = shaper.shape(flat, scope="/brain-a")
    doc = json.loads(s.text)
    check("regular records that fit once key names are written a single time are ALL shown, as a table",
          s.kind == "table" and doc["javis_stored_result"]["view"] == "complete"
          and len(doc["result"]["data"]["rows"]) == 140 and s.sent_chars <= shaper.INLINE_MAX_DEFAULT, (s.kind, s.sent_chars))
    cols = doc["result"]["data"]["columns"]
    row = dict(zip(cols, doc["result"]["data"]["rows"][7]))
    check("the table loses nothing: nested fields are dotted columns, lists stay lists, the envelope is kept",
          row == {"day": "2026-10-08", "channel": "zalo", "stats.revenue": 7000, "stats.orders": 7, "tags": ["a", "b"]}
          and doc["result"]["total"] == 140 and doc["result"]["next"] is None, row)
    check("a complete table still carries the reference for computing", store.get(s.ref, "/brain-a")["text"] == flat)
    many = json.dumps({"data": [{"day": f"2026-10-{1 + i % 28:02d}", "channel": "fb", "revenue": i * 1000, "orders": i}
                                for i in range(3000)]}, indent=2)
    s = shaper.shape(many, scope="/brain-a")
    doc = json.loads(s.text)
    check("too many rows for one answer: a partial table of whole rows, far more than as objects",
          s.kind == "preview" and doc["javis_stored_result"]["shown_as"] == "table"
          and doc["javis_stored_result"]["records_in_result"] == 3000 and len(doc["rows"]) > 100
          and len(doc["rows"]) == doc["javis_stored_result"]["shown_records"] and s.sent_chars <= shaper.INLINE_MAX_DEFAULT,
          (s.kind, doc["javis_stored_result"].get("shown_as"), len(doc.get("rows") or [])))

    check("no table when two fields would share one column name", shaper.to_table([{"a.b": 1, "a": {"b": 2}}]) is None)
    check("a field that is a value in one record and an object in another keeps both columns",
          shaper.to_table([{"a": 1}, {"a": {"b": 2}}]) == (["a", "a.b"], [[1, None], [None, 2]]))

    huge = page(10, big=True)
    s = shaper.shape(huge, scope="/brain-a")
    doc = json.loads(s.text)
    check("records too large to show whole are outlined, never cut blind",
          s.kind == "preview" and doc["javis_stored_result"]["shown_as"] == "outline" and len(doc["records"]) >= 1
          and "more items" in json.dumps(doc["records"][0]) and s.sent_chars <= shaper.INLINE_MAX_DEFAULT)

    pre = shaper.shape("page 1 of 37, next_cursor=abc123\n" + json.dumps({"data": [order(i) for i in range(30)]}, indent=2),
                       scope="/brain-a")
    check("text a server prints before its JSON is kept in the view",
          json.loads(pre.text)["javis_stored_result"]["text_before_result"] == "page 1 of 37, next_cursor=abc123", pre.text[:160])
    lines = "\n".join(f"line {i}: GET /pkg/{i} 200 (cache {'miss' if i % 7 == 0 else 'hit'})" for i in range(4000))
    s = shaper.shape(lines, scope="/brain-a")
    check("large text gets whole first and last lines plus a reference",
          s.kind == "text_preview" and s.ref and "line 0:" in s.text and "line 3999:" in s.text
          and s.sent_chars <= shaper.INLINE_MAX_DEFAULT)
    check("no line of the text view is cut",
          all(ln in lines for ln in s.text.splitlines() if ln.startswith("line ")))

    several = "\n".join(json.dumps({"id": i, "name": f"Sheet {i}", "url": "https://x/" + "u" * 80, "empty": None},
                                   indent=2) for i in range(60))
    s = shaper.shape(several, scope="/brain-a")
    check("several JSON objects in a row are read as records", s.kind in ("compact", "preview") and s.sent_chars < s.raw_chars)

    one = json.dumps({"report": {"k" + str(i): "v" * 300 for i in range(80)}, "generated": "2026-11-10"}, indent=1)
    s = shaper.shape(one, scope="/brain-a")
    doc = json.loads(s.text)
    check("a large object without a record list is outlined", s.kind == "preview" and "document" in doc)

    check("a caller without javis_query never gets a dead reference",
          shaper.shape(raw, scope="/brain-a", can_read_back=False).kind in ("compact", "same")
          and not shaper.shape(raw, scope="/brain-a", can_read_back=False).ref)

    store.configure(os.path.join(os.environ["JAVIS_STATE_DIR"], "no-key2.sqlite3"),
                    crypto=(lambda s: s, lambda s: s, lambda: False))
    s = shaper.shape(raw, scope="/brain-a")
    check("no encryption key: compacted, nothing stored, no reference", s.kind == "compact" and not s.ref)
    store.configure(os.path.join(os.environ["JAVIS_STATE_DIR"], "results-test2.sqlite3"))

    os.environ["JAVIS_TOOL_RESULT_SHAPING"] = "0"
    shaper.settings(force=True)
    check("switched off: the tool's own text", shaper.shape(raw).text == raw and shaper.shape(raw).kind == "off")
    os.environ.pop("JAVIS_TOOL_RESULT_SHAPING")
    _real_read = config.read_settings
    config.read_settings = lambda: {"context_runtime": {"preset_choice": {"level": "off", "source": "user"}}}
    check("the owner's own Off saving level switches it off", shaper.settings(force=True)["on"] is False)
    config.read_settings = lambda: {"context_runtime": {"preset_choice": {"level": "off", "source": ""}}}
    check("an Off level nobody chose does not", shaper.settings(force=True)["on"] is True)
    config.read_settings = lambda: {"mcp": {"result_shaping": False}}
    check("mcp.result_shaping=false switches it off", shaper.settings(force=True)["on"] is False)
    config.read_settings = _real_read
    shaper.settings(force=True)

    with shaper.raw_results():
        check("javis_query's own page reads are untouched", shaper.shape(raw).text == raw and shaper.shape(raw).kind == "raw")

# ============================================================
# 3. javis_query: slice, SQL, text
# ============================================================
loaded = query.load(raw)
check("the record list is found on its own", loaded["kind"] == "records" and loaded["pointer"] == "/data" and len(loaded["records"]) == 40)
out = json.loads(query.slice_records(loaded, "tr_x", fields=["id", "total", "customer.name"], offset=5, limit=3))
check("chosen fields, dotted paths included", out["records"] == [
    {"id": 1005, "total": 600000, "customer.name": "Khách 5"}, {"id": 1006, "total": 700000, "customer.name": "Khách 6"},
    {"id": 1007, "total": 800000, "customer.name": "Khách 7"}], out["records"])
check("the page says where to resume", out["javis_query"]["next_offset"] == 8 and out["javis_query"]["total_records"] == 40)
out = json.loads(query.slice_records(loaded, "tr_x", max_chars=3000))
n = out["javis_query"]["returned"]
check("a page ends on a whole record and resumes after it",
      0 < n < 40 and out["javis_query"]["next_offset"] == n and len(json.dumps(out)) <= 3400, n)
out = json.loads(query.slice_records(loaded, "tr_x", fields=["nope"]))
check("an unknown field is reported with the real names", out["javis_query"]["unknown_fields"] == ["nope"] and "id" in out["javis_query"]["fields"])

want = {}
for i in range(40):
    want[("done", "new", "returned")[i % 3]] = want.get(("done", "new", "returned")[i % 3], 0) + (1 + i % 9) * 100000
out = json.loads(query.run_sql(loaded, "tr_x", "SELECT status, COUNT(*) n, SUM(total) revenue FROM records GROUP BY status ORDER BY status"))
check("SQL totals are computed over ALL records", {r[0]: r[2] for r in out["rows"]} == want, out["rows"])
out = json.loads(query.run_sql(loaded, "tr_x", "SELECT i.sku, SUM(i.qty) FROM records_items i JOIN records r ON r._row = i._record "
                                              "WHERE r.status = 'done' GROUP BY i.sku ORDER BY i.sku"))
sku = {}
for i in range(0, 40, 3):
    for j in range(1 + i % 3):
        sku[f"SP{j}"] = sku.get(f"SP{j}", 0) + 1 + (i + j) % 3
check("a list of objects is its own table, joined to its record", {r[0]: r[1] for r in out["rows"]} == sku, out["rows"])
out = json.loads(query.run_sql(loaded, "tr_x", "SELECT customer_name, items_count FROM records WHERE id = 1002"))
check("nested objects are flattened, lists counted", out["rows"] == [["Khách 2", 3]], out["rows"])
for bad in ("DELETE FROM records", "SELECT 1; SELECT 2", "PRAGMA table_info(records)", "ATTACH 'x' AS y",
            "SELECT load_extension('x')", "CREATE TABLE t(a)", "UPDATE records SET total = 0",
            "WITH x AS (SELECT 1) INSERT INTO records(_row) SELECT * FROM x"):
    try:
        query.run_sql(loaded, "tr_x", bad)
        check(f"refused: {bad}", False)
    except query.QueryError:
        check(f"refused: {bad}", True)
try:
    query.run_sql(loaded, "tr_x", "SELECT nope FROM records")
    check("a wrong column answers with the real tables", False)
except query.QueryError as e:
    check("a wrong column answers with the real tables", "records_items" in str(e) and "customer_name" in str(e))
for big in ("SELECT zeroblob(900000000)", "SELECT randomblob(100000000)",
            "SELECT replace(printf('%.*c', 3000000, 'x'), 'x', 'yyyyyyyyyy')",
            "SELECT length(replace(printf('%.*c', 900000, 'x'), 'x', 'yyyyyyyyyy'))"):
    try:
        got = query.run_sql(loaded, "tr_x", big)
        check(f"a query cannot build one enormous value: {big[:32]}", len(got) < 2000 and "9000000" not in got, got[:120])
    except query.QueryError:
        check(f"a query cannot build one enormous value: {big[:32]}", True)

# The time limit must hold when single steps are expensive, not only when there are many cheap ones (review
# 2026-11-10: with a check every 20,000 steps this query ran 133 s against an 8 s limit).
heavy = {"kind": "records", "pointer": "/", "records": [{"a": i} for i in range(2000)]}
terms = "+".join(["length(replace(s,'0','1'))"] * 150)
slow_sql = f"WITH p(s) AS (SELECT printf('%0900000d', 1)) SELECT sum({terms}) FROM p, records"
query.SQL_TIMEOUT_S, _keep = 1.0, query.SQL_TIMEOUT_S
t0 = time.time()
try:
    query.run_sql(heavy, "tr_x", slow_sql)
    check("a query of few but costly steps is stopped on time", time.time() - t0 < 6, time.time() - t0)
except query.QueryError as e:
    check("a query of few but costly steps is stopped on time", time.time() - t0 < 6, (time.time() - t0, str(e)[:80]))
query.SQL_TIMEOUT_S = _keep

# Column names: a real field keeps its own name when a generated or flattened one would collide with it.
clash = {"kind": "records", "pointer": "/", "records": [
    {"comments": [{"t": 1}, {"t": 2}], "comments_count": 120, "customer": {"name": "nested"}, "customer_name": "flat",
     "big": 2 ** 70}] * 3}
out = json.loads(query.run_sql(clash, "tr_x", "SELECT SUM(comments_count), MAX(customer_name) FROM records"))
check("a real comments_count is not replaced by the generated list length", out["rows"] == [[360, "flat"]], out["rows"])
cols = json.loads(query.schema_view(clash, "tr_x"))["tables"]["records"]["columns"]
check("the generated and flattened twins are kept under a suffixed name",
      "comments_count_2" in cols and "customer_name_2" in cols, cols)
out = json.loads(query.run_sql(clash, "tr_x", "SELECT comments_count_2, customer_name_2, big FROM records LIMIT 1"))
check("...with their own values, and an integer too large for SQLite kept as text",
      out["rows"] == [[2, "nested", str(2 ** 70)]], out["rows"])
# A real model once dropped the quotes around a date: SQL then subtracts, matches nothing, and "no orders" is reported.
try:
    query.run_sql(loaded, "tr_x", "SELECT COUNT(*) FROM records WHERE substr(created_at, 1, 10) = 2026-10-05")
    check("an unquoted date is refused with the fix, not answered with zero rows", False)
except query.QueryError as e:
    check("an unquoted date is refused with the fix, not answered with zero rows", "'2026-10-05'" in str(e), str(e))
out = json.loads(query.run_sql(loaded, "tr_x", "SELECT COUNT(*), 'day 2026-10-05' FROM records "
                                             "WHERE substr(created_at, 1, 10) = '2026-10-05' /* 2026-10-05 */ -- 2026-10-05"))
check("a quoted date, a date inside a string and a date in a comment are left alone",
      out["rows"][0][0] >= 1 and "warning" not in out["javis_query"], out)
out = json.loads(query.run_sql(loaded, "tr_x", "SELECT id FROM records WHERE status = 'no-such-status'"))
check("a filter that matches nothing says so and asks to check the values before reporting zero",
      out["rows"] == [] and "not yet proof" in out["javis_query"]["warning"], out["javis_query"])
out = json.loads(query.run_sql(loaded, "tr_x", "SELECT id FROM records LIMIT 0"))
check("an empty answer without a filter carries no such warning", "warning" not in out["javis_query"])
old_timeout = query.SQL_TIMEOUT_S
query.SQL_TIMEOUT_S = 0.2
try:
    query.run_sql(loaded, "tr_x", "WITH RECURSIVE c(x) AS (SELECT 1 UNION ALL SELECT x + 1 FROM c) SELECT COUNT(*) FROM c")
    check("a runaway query is stopped", False)
except query.QueryError as e:
    check("a runaway query is stopped", "longer than" in str(e), str(e))
query.SQL_TIMEOUT_S = old_timeout
out = json.loads(query.run_sql(loaded, "tr_x", "SELECT id, customer_name, created_at FROM records", max_chars=1500))
check("too many rows: whole rows, marked truncated", out["javis_query"].get("truncated") is True and 0 < len(out["rows"]) < 40)

sheet = json.dumps({"range": "Sheet1!A1:C401", "values": [["Ngày", "Kênh", "Doanh thu"]] + [
    [f"2026-10-{1 + i % 28:02d}", "fb" if i % 2 else "zalo", i * 1000] for i in range(400)]}, indent=2)
ld = query.load(sheet)
out = json.loads(query.run_sql(ld, "tr_x", 'SELECT "Kênh" AS k, SUM("Doanh_thu") FROM records GROUP BY 1 ORDER BY 1')
                 if False else query.run_sql(ld, "tr_x", 'SELECT K_nh, SUM(Doanh_thu) FROM records GROUP BY 1 ORDER BY 1'))
check("spreadsheet rows: the header row names the columns",
      out["rows"] == [["fb", sum(i * 1000 for i in range(400) if i % 2)], ["zalo", sum(i * 1000 for i in range(400) if not i % 2)]],
      out["rows"])
desc = json.loads(query.schema_view(ld, "tr_x"))
check("describe lists tables and columns", desc["tables"]["records"]["rows"] == 400 and "Doanh_thu" in desc["tables"]["records"]["columns"])
check("the answer says which row was taken as the header", desc["javis_query"]["header_row_used"] == ["Ngày", "Kênh", "Doanh thu"])
texty = query.load(json.dumps({"values": [["An", "Hà Nội", "khách mới"], ["Bình", "Huế", "khách cũ"], ["Chi", "Vinh", "vip"]]}))
out = json.loads(query.run_sql(texty, "tr_x", "SELECT COUNT(*), MIN(c1) FROM records"))
check("rows of text only: NO row is eaten as a header, every row counts", out["rows"] == [[3, "An"]], out)
check("...and the answer says the columns are positional", "no row was taken" in out["javis_query"]["columns"])

txt = query.text_view(lines, "tr_x", search="line 3997")
check("text search returns the matching line with its number", "3998: line 3997:" in txt, txt[:200])
one_line = " ".join(f"<p>block {i} with some words</p>" for i in range(6000))       # one line, about 190,000 chars
soft = shaper.soft_lines(one_line)
check("one enormous line is split into numbered pieces, nothing lost",
      len(soft) > 100 and "".join(soft) == one_line and max(len(x) for x in soft) <= shaper.SOFT_LINE_CHARS)
seen_txt, off, pages = [], 0, 0
while off is not None and pages < 400:
    part = query.text_view(one_line, "tr_x", offset=off, limit=200)
    head_line, _, body = part.partition("\n")
    seen_txt.append(body.replace("\n", ""))
    nxt = head_line.split("next_offset=")[1].rstrip("]")
    off = None if nxt == "None" else int(nxt)
    pages += 1
check("...so the whole text can be read back page by page", "".join(seen_txt) == one_line, (pages, len("".join(seen_txt))))
found_txt = query.text_view(one_line, "tr_x", search="block 5999")
check("...and a search shows the whole matching piece", "block 5999 with some words</p>" in found_txt, found_txt[-120:])
with shaper.for_model():
    s1 = shaper.shape(one_line, scope="/brain-a")
check("the view of a one-line result counts the same pieces", s1.kind == "text_preview" and f"lines={len(soft)}" in s1.text, s1.text[:120])
txt = query.text_view(lines, "tr_x", offset=100, limit=5)
check("text can be read by line range", "lines 101-105 of 4000 next_offset=105" in txt and "line 104:" in txt, txt[:120])
check("paging markers are found in an envelope",
      query.page_info({"success": True, "page_number": 2, "total_pages": 9, "total_entries": 341, "data": []})
      == {"page": 2, "total_pages": 9, "total": 341})

# ============================================================
# 4. The hub: who gets what
# ============================================================
_calls = []
PAGES = {n: page(30, page_number=n, total_pages=4, total=120, start=(n - 1) * 30) for n in (1, 2, 3, 4)}


class _Pool:
    async def call_tool(self, spec, tool, args):
        _calls.append((tool, dict(args or {})))
        if tool == "list_orders":
            return PAGES.get(int((args or {}).get("page_number") or 1), page(0))
        if tool == "list_zero_based":
            n = int((args or {}).get("page") or 0)
            rows = [{"id": n * 10 + i} for i in range(10)] if n < 5 else []
            return json.dumps({"data": rows, "page": n, "total_pages": 5, "total": 50})
        if tool == "list_short":
            n = int((args or {}).get("page") or 1)
            return json.dumps({"data": [{"id": n * 10 + i} for i in range(10)] if n <= 2 else [], "page": n, "total": 90})
        if tool == "get_report":
            return json.dumps({"summary": {"revenue": 123, "orders": 4}}, indent=2)
        if tool == "get_page_text":
            return lines
        if tool == "same_page_always":
            return PAGES[1]
        if tool == "create_order":
            return json.dumps({"created": True, "id": 77})
        if tool == "broken":
            return "ERROR: upstream 500"
        return "OK"


CONN = {"id": "shop1", "connector_id": "custom-test-shop", "label": "Shop", "slug": "shop", "namespace": "shop",
        "perm": "full", "deny_tools": []}
TOOLS = [("list_orders", {"page_number": {"type": "integer"}, "status": {"type": "string"}}),
         ("list_zero_based", {"page": {"type": "integer"}}), ("list_short", {"page": {"type": "integer"}}),
         ("trigger_sync", {}),
         ("get_report", {}), ("get_page_text", {}), ("same_page_always", {"page": {"type": "integer"}}),
         ("create_order", {"name": {"type": "string"}}), ("broken", {})]


async def _fake_discover(conns, bo_qua=None):
    spec = {"transport": "http", "url": "https://shop.test/mcp", "headers": {}}
    tools, route = [], {}
    for name, props in TOOLS:
        fn = f"shop__{name}"
        route[fn] = {"spec": spec, "tool": name, "conn": dict(CONN)}
        tools.append({"fn": fn, "server": "shop", "name": name, "description": name.replace("_", " "),
                      "schema": {"type": "object", "properties": props}, "conn_id": "shop1",
                      "connector_id": CONN["connector_id"], "namespace": "shop", "label": "Shop"})
    return tools, route


# A connector the catalog knows: which tools read is the catalog's call, never the tool name's. An unknown
# connector's tools all count as writes (fail closed), so they could not be paged at all.
_real_get = mcp_catalog.get
SHOP = {"id": "custom-test-shop", "name": "Shop", "tool_meta": {
    "read": ["list_*", "get_*", "same_*", "broken"], "write": ["create_*"]}}
mcp_catalog.get = lambda cid: SHOP if cid == "custom-test-shop" else _real_get(cid)
mcp_store.resolved = lambda enabled_only=True: [dict(CONN, transport="http", url="https://shop.test/mcp", headers={}, env={})]
mcp_client.discover_resolved = _fake_discover
mcp_client.pool = _Pool()
mcp_hub._builtin_tools = lambda *a, **k: ([], {})
_settings = {"mcp": {"lazy_tools": "off"}}
config.read_settings = lambda: json.loads(json.dumps(_settings))
shaper.settings(force=True)
mcp_hub._cache.clear()
BRAIN_A, BRAIN_B = tempfile.mkdtemp(prefix="brain-a-"), tempfile.mkdtemp(prefix="brain-b-")


def run(coro):
    return asyncio.run(coro)


tools, route = run(mcp_hub.discover_all("full", vault_root=BRAIN_A, include_plugins=False, force_refresh=True))
names = {t["fn"] for t in tools}
check("a brain with a connected source gets javis_query", "javis_query" in names, sorted(names))
qspec = next(t for t in tools if t["fn"] == "javis_query")
check("javis_query is paid for on every turn, so it stays small", len(json.dumps(qspec, ensure_ascii=False)) < 1400,
      len(json.dumps(qspec, ensure_ascii=False)))

plain = run(mcp_client.call_route(route, "shop__list_orders", {}))
check("an internal caller of the route still gets the tool's own text", plain == PAGES[1])


async def as_model(fn, args, r=None):
    return await engine._call_tool_for_model(r or route, fn, args)


seen = run(as_model("shop__list_orders", {}))
doc = json.loads(seen)
ref = doc["javis_stored_result"]["ref"]
check("a model's tool loop gets the view", doc["javis_stored_result"]["records_in_result"] == 30 and len(seen) <= 8000, len(seen))
check("the API engines' cut has nothing left to cut", engine._clip_tool_result(seen, ten="shop__list_orders") == seen)
check("a write tool's small answer is untouched", run(as_model("shop__create_order", {"name": "x"})) == '{"created": true, "id": 77}')
check("an upstream error is untouched", run(as_model("shop__broken", {})).startswith("ERROR: upstream 500"))

out = json.loads(run(as_model("javis_query", {"ref": ref, "sql": "SELECT COUNT(*), SUM(total) FROM records"})))
check("javis_query computes over the stored result", out["rows"] == [[30, sum((1 + i % 9) * 100000 for i in range(30))]], out)
out = json.loads(run(as_model("javis_query", {"ref": ref, "fields": ["id"], "limit": 3})))
check("javis_query reads records by field", out["records"] == [{"id": 1000}, {"id": 1001}, {"id": 1002}], out)

tools_b, route_b = run(mcp_hub.discover_all("full", vault_root=BRAIN_B, include_plugins=False, force_refresh=True))
other = run(as_model("javis_query", {"ref": ref, "limit": 1}, route_b))
check("another brain's turn cannot read the reference", other.startswith("ERROR:") and "unknown or has expired" in other, other[:120])
check("a made-up reference is refused the same way",
      run(as_model("javis_query", {"ref": "tr_" + "ab" * 12})).startswith("ERROR:"))

_calls.clear()
out = json.loads(run(as_model("javis_query", {"tool": "shop__list_orders", "args": {"status": "all"}, "pages": 10,
                                              "sql": "SELECT COUNT(*), COUNT(DISTINCT id), SUM(total) FROM records"})))
check("paging a read tool builds one dataset of every page",
      out["rows"] == [[120, 120, sum((1 + i % 9) * 100000 for i in range(120))]], out.get("rows"))
check("it stops at the last page the source reports",
      [c[1].get("page_number") for c in _calls] == [None, 2, 3, 4] and out["javis_query"]["source"]["complete"] is True,
      [c[1] for c in _calls])
check("the other arguments ride along on every page", all(c[1].get("status") == "all" for c in _calls))
dref = out["javis_query"]["ref"]
_calls.clear()
again = json.loads(run(as_model("javis_query", {"ref": dref, "sql": "SELECT status, COUNT(*) FROM records GROUP BY 1 ORDER BY 1"})))
check("the dataset is reused by reference without calling the source again",
      not _calls and again["rows"] == [["done", 40], ["new", 40], ["returned", 40]], again.get("rows"))

_calls.clear()
out = json.loads(run(as_model("javis_query", {"tool": "shop__list_orders", "args": {}, "pages": 2, "fields": ["id"], "limit": 2})))
check("fewer pages than exist: marked incomplete, with the reported total",
      len(_calls) == 2 and out["javis_query"]["source"]["complete"] is False
      and out["javis_query"]["source"]["reported_total"] == 120 and out["javis_query"]["total_records"] == 60, out["javis_query"])
_calls.clear()
out = json.loads(run(as_model("javis_query", {"tool": "shop__same_page_always", "args": {}, "pages": 5, "describe": True})))
check("a source that ignores the page argument is read once, not five times",
      len(_calls) == 2 and "same page again" in out["javis_query"]["source"]["note"], (len(_calls), out["javis_query"]))
_calls.clear()
out = json.loads(run(as_model("javis_query", {"tool": "shop__list_zero_based", "args": {}, "pages": 10,
                                              "sql": "SELECT COUNT(*), COUNT(DISTINCT id) FROM records"})))
check("a zero-based source is read from page 0 with no page skipped",
      out["rows"] == [[50, 50]] and [c[1].get("page") for c in _calls][:3] == [None, 1, 2]
      and out["javis_query"]["source"]["complete"] is True, (out.get("rows"), [c[1] for c in _calls]))
_calls.clear()
out = json.loads(run(as_model("javis_query", {"tool": "shop__list_short", "args": {}, "pages": 10, "describe": True})))
check("fewer records than the source reports is never called complete",
      out["javis_query"]["source"]["complete"] is False and "of the 90" in out["javis_query"]["source"]["note"],
      out["javis_query"]["source"])
_calls.clear()
refused = run(as_model("javis_query", {"tool": "shop__trigger_sync", "args": {}, "pages": 3}))
check("a tool nobody described as a read is never called by javis_query on its own",
      refused.startswith("ERROR:") and not _calls, refused[:120])
check("...although the hub's permission class alone would have let it through",
      mcp_catalog.classify(SHOP, "trigger_sync", {}) == "read" and not tool_result_tools.is_plain_read(
          {"conn": CONN, "tool": "trigger_sync"}, {}))
_calls.clear()
refused = run(as_model("javis_query", {"tool": "shop__create_order", "args": {"name": "x"}, "pages": 3}))
check("a tool that writes can never be a source", refused.startswith("ERROR:") and not _calls, refused[:100])
check("its own name is not a source", run(as_model("javis_query", {"tool": "javis_query", "args": {}})).startswith("ERROR:"))
check("an upstream error on the first page is passed on", run(as_model("javis_query", {"tool": "shop__broken", "args": {}})).startswith("ERROR: upstream 500"))
out = run(as_model("javis_query", {"tool": "shop__get_report", "args": {}}))
check("a source without a record list is shown as a document", '"revenue":123' in out, out[:200])
out = run(as_model("javis_query", {"tool": "shop__get_page_text", "args": {}, "search": "line 2500"}))
check("a text source is searchable", "2501: line 2500:" in out, out[:200])
check("no source at all is an error", run(as_model("javis_query", {"sql": "SELECT 1"})).startswith("ERROR:"))

tools_s, route_s = run(mcp_hub.discover_all("suggest", vault_root=BRAIN_A, include_plugins=False, force_refresh=True))
out = json.loads(run(as_model("javis_query", {"tool": "shop__list_orders", "args": {}, "sql": "SELECT COUNT(*) FROM records"}, route_s)))
check("a read-only run can still query a read tool", out["rows"] == [[30]])

sized = [json.loads(ln) for ln in mcp_hub._SIZES_PATH.read_text(encoding="utf-8").splitlines()]
sized = [a for a in sized if a.get("tool") == "list_orders"]
check("the sizes log records both sizes", any(a["shape"] == "preview" and a["raw_chars"] > 50000 > a["sent_chars"] > 0 for a in sized))
check("pages javis_query read for itself count as nothing sent", any(a["shape"] == "raw" and a["sent_chars"] == 0 for a in sized))
check("an internal read is not measured as a model read", all(a["shape"] != "internal" for a in sized))
audit = [a for a in mcp_hub.audit_tail(limit=300) if a.get("tool") == "list_orders"]
check("the audit log keeps its own shape, one line per call", audit and all("raw_chars" not in a and "cls" in a for a in audit))
stats = mcp_hub.result_size_stats(days=1)
check("the stats add up what was kept out of the conversation",
      stats["calls"] > 5 and stats["saved_chars"] > 100000 and stats["saved_pct"] > 80 and stats["stored"] >= 1
      and stats["by_tool"][0]["tool"] == "list_orders", {k: v for k, v in stats.items() if k != "by_tool"})

# ---- lazy tier: javis_query stays visible, an explicit result_view is cut from the whole result
_settings["mcp"] = {"lazy_tools": "on", "lazy_top_k": 8}
mcp_hub._cache.clear()
tools_l, route_l = run(mcp_hub.discover_all("full", vault_root=BRAIN_A, include_plugins=False, force_refresh=True))
names_l = {t["fn"] for t in tools_l}
check("behind the tool search, javis_query is still listed directly",
      {"javis_query", mcp_hub._LAZY_SEARCH, mcp_hub._LAZY_RUN} <= names_l and "shop__list_orders" not in names_l, sorted(names_l))
seen = json.loads(run(as_model(mcp_hub._LAZY_RUN, {"name": "shop__list_orders", "args": {}}, route_l)))
check("a tool run through the search tier is shaped too", seen["javis_stored_result"]["records_in_result"] == 30)
view = json.loads(run(as_model(mcp_hub._LAZY_RUN, {"name": "shop__list_orders", "args": {},
                                                   "result_view": {"pointer": "/data", "fields": ["id", "total"], "limit": 30}}, route_l)))
check("an explicit result_view is taken from the whole result", len(view["data"]) == 30 and view["data"][29]["id"] == 1029, str(view)[:200])
out = json.loads(run(as_model("javis_query", {"tool": "shop__list_orders", "args": {}, "pages": 4,
                                              "sql": "SELECT COUNT(*) FROM records"}, route_l)))
check("javis_query reaches a tool hidden behind the search tier", out["rows"] == [[120]])

# ---- a plugin hook around the tool call keeps seeing what the tool really returned
import plugins_host  # noqa: E402
_hook_saw = []


def _fake_wrap(fn, base_call, mode, vault_root):
    async def _wrapped(args):
        result = await base_call(args)
        _hook_saw.append((fn, result))
        return result
    return _wrapped

_real_has, _real_wrap = plugins_host.has_tool_hooks, plugins_host.wrap_with_hooks
plugins_host.has_tool_hooks = lambda vault_root=None: True
plugins_host.wrap_with_hooks = _fake_wrap
_settings["mcp"] = {"lazy_tools": "off"}
mcp_hub._cache.clear()
tools_h, route_h = run(mcp_hub.discover_all("full", vault_root=BRAIN_A, include_plugins=False, force_refresh=True))
seen = run(as_model("shop__list_orders", {}, route_h))
plugins_host.has_tool_hooks, plugins_host.wrap_with_hooks = _real_has, _real_wrap
mcp_hub._cache.clear()
check("a post_tool_call hook sees the tool's own text while the model gets the view",
      ("shop__list_orders", PAGES[1]) in _hook_saw and "javis_stored_result" in seen)

# ============================================================
# 5. Tool search answers stay small
# ============================================================
long_desc = "word " * 700
pool = [{"fn": "javis_use_skill", "name": "javis_use_skill", "namespace": "javis", "label": "javis",
         "description": "Load a skill. Skills: orders report, pos summary, list everything, " + long_desc,
         "schema": {"type": "object", "properties": {"name": {"type": "string"}}}}]
for i in range(12):
    pool.append({"fn": f"pos__orders_{i}", "name": f"orders_{i}", "namespace": "pos", "label": "POS",
                 "description": "List shop orders. " + ("detail " * 250),
                 "schema": {"type": "object", "properties": {f"p{k}": {"type": "string", "description": "d" * 60}
                                                             for k in range(12)}}})
_t, r2 = mcp_hub._lazy_tools_and_route([], {}, pool, {}, 8)
found = run(r2[mcp_hub._LAZY_SEARCH]["call"]({"query": "pos orders list"}))
res = json.loads(found)
check("a search ranks tools named for the job above a long unrelated description",
      res["tools"][0]["name"].startswith("pos__orders_") and all(t["name"] != "javis_use_skill" for t in res["tools"]),
      [t["name"] for t in res["tools"]])
check("a search answer stays near its budget", len(found) <= mcp_hub._SEARCH_BUDGET_CHARS + 1500, len(found))
check("hits that did not fit are still named", res.get("more_tools") and all("schema" not in t for t in res["more_tools"]))
exact = json.loads(run(r2[mcp_hub._LAZY_SEARCH]["call"]({"query": res["more_tools"][-1]["name"]})))
check("a search by exact name returns that tool's schema", exact["tools"][0]["name"] == res["more_tools"][-1]["name"]
      and "schema" in exact["tools"][0])

# ============================================================
# 6. A long tool loop trims an old view but keeps its reference
# ============================================================
conv = [{"role": "tool", "tool_call_id": str(i), "content": json.dumps(
    {"javis_stored_result": {"ref": f"tr_{i:024d}", "original_chars": 99225, "note": "n"}, "records": ["r" * 6000]})}
    for i in range(12)]
n = engine._gon_ket_qua_cu(conv, 30_000)
check("old results are trimmed in a long loop", n > 0)
check("a trimmed view still carries its reference and points to javis_query",
      "tr_000000000000000000000000" in conv[0]["content"] and "javis_query(ref=" in conv[0]["content"], conv[0]["content"][:160])

if _fails:
    raise SystemExit(f"{len(_fails)} FAIL: " + "; ".join(_fails))
print("All green")
