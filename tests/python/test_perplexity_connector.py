"""Perplexity is a built-in connection: the official remote MCP with an API key (owner, 2026-11-17).

    python tests/run.py perplexity_connector

What this guards:
1. The card points at Perplexity's own hosted MCP (https://api.perplexity.ai/mcp) and sends the key the way
   Perplexity documents it: `Authorization: Bearer <key>`.
2. Its four tools only read the web, so they run at Read-only, the default. A tool Perplexity adds later is NOT
   waved through as a read: tool_meta lists exact names, never a `perplexity_*` glob.
3. Pressing Check on the Connections page must not spend the user's API credit: no `validate` tool call, the
   check only lists tools (which already needs a valid key).
4. The English overlay covers every Vietnamese string, and a pasted `pplx-` key is masked in chat logs.

No pytest, no network, never touches the real STATE_DIR.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import json
import os
import sys
import tempfile
from pathlib import Path

import localefmt
import mcp_catalog
import secret_redact

_fails = []


def check(name, cond, detail=""):
    print(("ok   " if cond else "FAIL ") + name + (f"  ({detail})" if detail and not cond else ""))
    if not cond:
        _fails.append(name)


URL = "https://api.perplexity.ai/mcp"
TOOLS = ("perplexity_search", "perplexity_ask", "perplexity_reason", "perplexity_research")

# ---------------- 1. Where it dials and how it signs in ----------------
con = mcp_catalog.tat_ca().get("perplexity") or {}
auth = con.get("auth") or {}
check("core catalog has the perplexity connector", bool(con))
check("remote MCP over HTTP, Perplexity's own endpoint", con.get("transport") == "http" and con.get("url") == URL,
      f"{con.get('transport')} {con.get('url')}")
check("signs in with an API key", auth.get("type") == "apikey")
fields = auth.get("fields") or []
check("exactly one field, the API key", [f.get("key") for f in fields] == ["api_key"], fields)
check("key goes in the Bearer header",
      mcp_catalog.build_headers(con, {"api_key": "pplx-TEST123"}) == {"Authorization": "Bearer pplx-TEST123"},
      mcp_catalog.build_headers(con, {"api_key": "pplx-TEST123"}))
check("the key field is required, so a connection never goes out with an empty Bearer",
      not fields[0].get("optional") if fields else False)
check("the URL carries no credential", "{" not in (con.get("url") or "") and "key" not in (con.get("url") or ""))
check("status is open (not 'soon')", con.get("status") in ("ready", "beta"), con.get("status"))
icon = con.get("icon") or ""
check("icon is a bundled Lucide name, nothing downloaded",
      icon and not icon.startswith(("http", "/")) and f'"{icon}"' in
      (ROOT / "dashboard" / "icons.manifest.json").read_text(encoding="utf-8"), icon)

# ---------------- 2. Permissions ----------------
check("default level is Read-only", con.get("default_perm") == "readonly", con.get("default_perm"))
meta = con.get("tool_meta") or {}
check("tool_meta lists the four tools by exact name", sorted(meta.get("read") or []) == sorted(TOOLS), meta)
check("no write or danger tools declared", not meta.get("write") and not meta.get("danger"), meta)
check("CANARY: no glob in tool_meta (a future tool must not be read-only by accident)",
      not any("*" in t or "?" in t for t in (meta.get("read") or [])), meta)
for tool in TOOLS:
    check(f"{tool} classifies as read", mcp_catalog.classify(con, tool) == "read", mcp_catalog.classify(con, tool))
    check(f"{tool} runs at Read-only", mcp_catalog.allowed(con, "readonly", "full", tool)[0])
    check(f"{tool} runs in a suggest-mode loop", mcp_catalog.allowed(con, "readonly", "suggest", tool)[0])
check("CANARY: an unknown write-like tool is NOT allowed at Read-only",
      not mcp_catalog.allowed(con, "readonly", "full", "perplexity_delete_thread")[0])

# ---------------- 3. Checking a connection costs nothing ----------------
check("no validate tool call (Check must not spend API credit)", "validate" not in con, con.get("validate"))

# ---------------- 4. Text: guide layout, English overlay, key masking ----------------
guide = auth.get("guide") or ""
check("guide explains per-use billing", "credit" in guide)
check("guide warns that perplexity_research is the costly one", "perplexity_research" in guide)
check("guide uses no em/en dash", "—" not in guide and "–" not in guide)
steps = auth.get("steps") or []
check("wizard steps link the API Portal", any(s.get("link") == "https://console.perplexity.ai" for s in steps))

en = json.loads((ROOT / "system" / "mcp-catalog.en.json").read_text(encoding="utf-8"))["connectors"]
ov = en.get("perplexity") or {}
check("English overlay exists", bool(ov))
check("English overlay has description, guide, field label", bool(ov.get("description") and ov.get("guide")
      and ((ov.get("fields") or {}).get("api_key") or {}).get("label")))
check("English overlay has as many steps as the source", len(ov.get("steps") or []) == len(steps),
      f"{len(ov.get('steps') or [])} != {len(steps)}")

tok = localefmt.dat_ngon_ngu_yeu_cau("en")
try:
    pub_en = {c["id"]: c for c in mcp_catalog.public_catalog()}
finally:
    localefmt.bo_ngon_ngu_yeu_cau(tok)
pub_vi = {c["id"]: c for c in mcp_catalog.public_catalog()}
check("Connections page lists the card", "perplexity" in pub_vi)
check("English device reads the English description",
      (pub_en.get("perplexity") or {}).get("description", "").startswith("Search and research the web"))
check("Vietnamese device still reads the source", (pub_vi.get("perplexity") or {}).get("description")
      == con.get("description"))
key = "pplx-" + "a1B2c3D4e5F6g7H8i9J0k1L2m3N4o5P6q7R8s9T0u1V2w3X4"
masked = secret_redact.redact_secrets("my key is " + key + " thanks")
check("a pasted Perplexity key is masked (first 6 and last 4 kept)",
      key not in masked and "pplx-a...w3X4" in masked, masked)
check("CANARY: the word Perplexity alone is left alone",
      secret_redact.redact_secrets("ask Perplexity about pplx pricing") == "ask Perplexity about pplx pricing")
check("CANARY: a short pplx- string is not mistaken for a key",
      secret_redact.redact_secrets("prefix pplx-abc") == "prefix pplx-abc")

# ---------------- 5. Added as a real connection, the hub dials it right ----------------
with tempfile.TemporaryDirectory() as tmp:
    old_env = os.environ.get("JAVIS_STATE_DIR")
    os.environ["JAVIS_STATE_DIR"] = tmp
    # An empty store file first: without it mcp_store falls back to server/mcp_servers.json, the real one.
    (Path(tmp) / "mcp_servers.json").write_text('{"version": 2, "connections": []}', encoding="utf-8")
    for mod in ("mcp_store", "secrets_store", "config"):
        sys.modules.pop(mod, None)
    try:
        import config as fresh_config  # noqa: E402
        check("STATE_DIR points at the temp dir", str(fresh_config.STATE_DIR) == tmp, fresh_config.STATE_DIR)
        import mcp_store  # noqa: E402
        check("temp store starts empty", not mcp_store.list_connections())
        cid, err = mcp_store.add_connection("perplexity", {"fields": {"api_key": "pplx-TEST456"}})
        check("connection is added", not err, err)
        if not err:
            r = [x for x in mcp_store.resolved(enabled_only=False) if x["connector_id"] == "perplexity"][0]
            check("resolved: dials the official endpoint", r["url"] == URL, r["url"])
            check("resolved: Bearer header with the key", r["headers"] == {"Authorization": "Bearer pplx-TEST456"},
                  r["headers"])
            check("resolved: Read-only by default", r["perm"] == "readonly", r["perm"])
            stored = (Path(tmp) / "mcp_servers.json").read_text(encoding="utf-8")
            check("CANARY: the key is encrypted at rest, not in plain text", "pplx-TEST456" not in stored)
    finally:
        if old_env is None:
            os.environ.pop("JAVIS_STATE_DIR", None)
        else:
            os.environ["JAVIS_STATE_DIR"] = old_env
        for mod in ("mcp_store", "secrets_store", "config"):
            sys.modules.pop(mod, None)

if _fails:
    print(f"\nFAIL - test_perplexity_connector: {len(_fails)} failed: {_fails}")
    sys.exit(1)
print("\nOK - test_perplexity_connector: all pass")
