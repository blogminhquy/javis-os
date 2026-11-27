"""A plain SELECT runs at Read only on Supabase's official MCP server locked to read_only=true (issue #1865).

    python tests/run.py supabase_read_only_sql      (no network)

Checks:
  1. only https://mcp.supabase.com with read_only=true AND a project_ref counts; a custom server, a URL without the
     lock, or read_only=false changes nothing;
  2. `is_read_only_sql` passes one plain read and refuses writes, several statements, data-modifying CTEs, SELECT INTO,
     row locks, EXPLAIN ANALYZE, acting functions and unterminated quoting; words inside strings, quoted identifiers
     and comments do not count;
  3. classify / allowed: on the locked server execute_sql is listed at Read only, a SELECT is allowed, a write is
     refused; on any other connection execute_sql stays a write;
  4. mcp_hub applies it both when listing and when calling.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import mcp_catalog as mc  # noqa: E402

_fails = []


def check(name, cond, detail=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(detail) + "]") if detail and not cond else ""))
    if not cond:
        _fails.append(name)


LOCKED = "https://mcp.supabase.com/mcp?project_ref=abcd&read_only=true&features=database"
# ---- 1. the lock ---------------------------------------------------------------------------------------
check("locked Supabase URL counts", mc.supabase_read_only(LOCKED))
for url in ("https://mcp.supabase.com/mcp?project_ref=abcd",
            "https://mcp.supabase.com/mcp?project_ref=abcd&read_only=false",
            "https://mcp.supabase.com/mcp?read_only=true",
            "https://mcp.supabase.com/mcp?project_ref=&read_only=true",
            "http://mcp.supabase.com/mcp?project_ref=abcd&read_only=true",
            "https://evil.example/mcp?project_ref=abcd&read_only=true&host=mcp.supabase.com",
            "https://mcp.supabase.com.evil.example/mcp?project_ref=abcd&read_only=true",
            "https://mcp.supabase.com/mcp?project_ref=abcd&read_only=true&read_only=false",
            "", None):
    check(f"not locked: {url}", not mc.supabase_read_only(url))

# ---- 2. the parse --------------------------------------------------------------------------------------
reads = ["select * from orders limit 10", "SELECT count(*) FROM orders;", "  select 1 ;; ",
         "with t as (select id from orders) select * from t",
         "explain select * from orders", "select 'delete from x' as note",
         'select "update" from t', "select id -- insert here\nfrom t", "select /* drop table */ 1",
         "select $$; drop table x$$", "select comment from posts", "select last_update, updated_at from t",
         "(select 1) union (select 2)", "values (1), (2)"]
for q in reads:
    check(f"read: {q!r}", mc.is_read_only_sql(q))
writes = ["insert into t values (1)", "update t set a = 1", "delete from t", "drop table t",
          "select 1; delete from t", "select 1; select 2",
          "with d as (delete from t returning *) select * from d", "select * into newt from t",
          "select * from t for update", "select * from t for no key update", "select * from t for share",
          "explain analyze select * from t", "select pg_terminate_backend(123)", "select set_config('a','b',false)",
          "select pg_sleep(10)", "select nextval('s')", "select dblink_exec('x','y')", "select lo_import('/etc/passwd')",
          "select pg_read_file('/etc/passwd')", "copy t to stdout", "truncate t", "create table x (a int)",
          "select 'unterminated", "select 1 /* open", "select $a$ open", "grant all on t to public",
          "vacuum", "call proc()", "do $$ begin end $$", "", None, "select " + "x," * 12000 + "1"]
for q in writes:
    check(f"not a read: {str(q)[:60]!r}", not mc.is_read_only_sql(q))

# ---- 3. classify / allowed -----------------------------------------------------------------------------
locked = mc.with_server_read_only(None, {"url": LOCKED})
plain = mc.with_server_read_only(None, {"url": "https://example.com/mcp"})
check("other connections are unchanged", plain is None)
check("listing: execute_sql is a read on the locked server", mc.classify(locked, "execute_sql", None) == "read")
check("listing: still a write elsewhere", mc.classify(plain, "execute_sql", None) == "write")
check("call: a SELECT is a read", mc.classify(locked, "execute_sql", {"query": "select 1"}) == "read")
check("call: a write stays a write", mc.classify(locked, "execute_sql", {"query": "delete from t"}) == "write")
check("call: a missing query is not a read", mc.classify(locked, "execute_sql", {}) == "write")
ok, why = mc.allowed(locked, "readonly", "full", "execute_sql", {"query": "select * from orders"})
check("Read only: the SELECT runs", ok, why)
ok, why = mc.allowed(locked, "readonly", "full", "execute_sql", {"query": "update orders set paid = true"})
check("Read only: the UPDATE is refused", not ok)
ok, why = mc.allowed(plain, "readonly", "full", "execute_sql", {"query": "select 1"})
check("Read only elsewhere: execute_sql still refused", not ok)
check("other Supabase tools keep their class", mc.classify(locked, "apply_migration", {"query": "select 1"}) == "write")
check("a catalog connector keeps its own metadata",
      mc.with_server_read_only({"tool_meta": {"read": ["list_*"]}}, {"url": LOCKED})["tool_meta"] == {"read": ["list_*"]})

# ---- 4. wiring -----------------------------------------------------------------------------------------
hub = (SERVER / "mcp_hub.py").read_text(encoding="utf-8")
check("mcp_hub uses it when calling and when listing", hub.count("mcp_catalog.with_server_read_only(") == 2
      and '(ent.get("spec") or {}).get("url")' in hub and '(raw.get("spec") or {}).get("url")' in hub)
for name in ("apply_migration", "reset_branch", "rebase_branch", "pause_project"):
    check(f"a custom connection's {name} is not a read", mc.classify(None, name, {}) != "read")

check("no em dash in this file", chr(0x2014) not in open(__file__, encoding="utf-8").read())

if _fails:
    print(f"\n{len(_fails)} FAIL")
    sys.exit(1)
print("\nPASS")
