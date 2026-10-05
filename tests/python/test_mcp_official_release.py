"""Third-party MCPs follow their official release (owner's rule, 2026-10-05), and the
permission fixes that rule exposed.

    python tests/run.py mcp_official_release

No network. Three things are guarded here:

1. Every built-in connector launched through npx/uvx takes its MCP from npm/PyPI and ends the
   package with `@latest`. A bare name is not enough: npx and uvx reuse whatever version a
   machine cached first, so two machines would run two versions forever. The one exception must
   say why in `ngoai_le_ban_chinh_thuc`: Zalo no longer follows upstream (owner, 2026-10-05);
   Javis moves to its own CLI and only zca-js keeps following official releases. Until then it
   runs the unmodified zalo-agent-cli 1.6.2, whose formats Javis reads directly, so its three
   pins (catalog, zalo_cli.py, zalo_login.py) must match. The store runs the same rule in javis-store/tools/ban_chinh_thuc.py.
2. workspace-mcp 2.x added `run_script_function` (runs Apps Script) and `import_to_google_*`.
   Their names carry no write hint, so classify() used to put both in the READ group.
3. `call_rules` without `items`: a single-action gateway such as Hostinger 2.x `execute`, which
   names its one sub-action at the top level of args. Before 0.82.0 every such call failed
   closed to danger, so a read-only connection could not even list its domains through it.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import json
import os
import tempfile

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-official-release-"))

import mcp_catalog  # noqa: E402
import zalo_cli  # noqa: E402
import zalo_login  # noqa: E402

_fails = []


def check(name, cond, extra=None):
    print(("ok   " if cond else "FAIL ") + name + ("" if cond or extra is None else f"  [{extra}]"))
    if not cond:
        _fails.append(name)


# ============================================================
# 1. Official release, latest version
# ============================================================
_WITH_VALUE = {"npx": {"-p", "--package"}, "uvx": {"--with", "--python", "-p", "--index-url"}}


def package_of(command, args):
    """The package spec npx/uvx will fetch (same parsing as the store's ban_chinh_thuc.py)."""
    args = [str(a) for a in args or []]
    i = 0
    while i < len(args):
        a = args[i]
        if (command == "uvx" and a == "--from") or (command == "npx" and a in ("-p", "--package")):
            return args[i + 1] if i + 1 < len(args) else ""
        if a in _WITH_VALUE[command]:
            i += 2
            continue
        if a.startswith("-"):
            i += 1
            continue
        return a
    return ""


raw = json.loads((ROOT / "system" / "mcp-catalog.json").read_text(encoding="utf-8"))
launched = [c for c in raw["connectors"] if str(c.get("command") or "") in ("npx", "uvx")]
check("catalog still has npx/uvx connectors to check", len(launched) >= 5, len(launched))
for c in launched:
    pkg = package_of(c["command"], c.get("args"))
    if str(c.get("ngoai_le_ban_chinh_thuc") or "").strip():
        check(f"{c['id']}: pinned on purpose and says why", len(c["ngoai_le_ban_chinh_thuc"]) > 40)
        continue
    check(f"{c['id']}: package found in the command", bool(pkg), c.get("args"))
    low = pkg.lower()
    check(f"{c['id']}: official release, not GitHub code ({pkg})",
          not low.startswith(("git+", "http:", "https:", "file:", ".", "/")) and "github.com" not in low)
    check(f"{c['id']}: follows the latest release ({pkg})", low.endswith("@latest"))

zalo = next(c for c in raw["connectors"] if c["id"] == "zalo")
zalo_pkg = package_of("npx", zalo["args"])
check("Zalo is the documented exception and says it no longer follows upstream",
      "KHÔNG đi theo bản gốc" in str(zalo.get("ngoai_le_ban_chinh_thuc") or ""))
check("Zalo MCP, zalo_cli and zalo_login pin the SAME CLI version",
      zalo_pkg == zalo_cli.CLI_PACKAGE == zalo_login._CLI_PACKAGE,
      (zalo_pkg, zalo_cli.CLI_PACKAGE, zalo_login._CLI_PACKAGE))

ads = mcp_catalog.get("google-ads")
check("Google Ads runs the PyPI release, not GitHub main", ads.get("args") == ["google-ads-mcp@latest"])
check("Google Ads guide no longer asks for Git", "Git " not in ads["auth"]["guide"])

# ============================================================
# 2. workspace-mcp 2.x tools
# ============================================================
ws = mcp_catalog.get("google-workspace")
check("run_script_function (runs Apps Script) is danger",
      mcp_catalog.classify(ws, "run_script_function") == "danger")
for t in ("import_to_google_doc", "import_to_google_sheets", "import_to_google_slides"):
    check(f"{t} is write", mcp_catalog.classify(ws, t) == "write", mcp_catalog.classify(ws, t))
check("generate_trigger_code only returns code: read",
      mcp_catalog.classify(ws, "generate_trigger_code") == "read")
check("existing classes unchanged: send_gmail_message danger, get_doc_content read",
      mcp_catalog.classify(ws, "send_gmail_message") == "danger"
      and mcp_catalog.classify(ws, "get_doc_content") == "read")
ok, _ = mcp_catalog.allowed(ws, "safe", "full", "run_script_function", {"function_name": "f"})
check("Draft level (the Workspace default) can no longer run Apps Script", ok is False)

# ============================================================
# 3. call_rules for a single-action gateway
# ============================================================
rule = {"key": "operation", "else": "danger", "read_values": ["domains_portfolio_list", "vps_virtual-machines_list"]}
gw = {"id": "gw", "tool_meta": {"read": ["search"]},
      "call_rules": {"execute": dict(rule), "multi-execute": {"items": "steps", **rule}}}
cls = mcp_catalog.classify
check("single action, listed read operation: read",
      cls(gw, "execute", {"operation": "domains_portfolio_list", "params": {}}) == "read")
check("single action, unlisted operation: danger",
      cls(gw, "execute", {"operation": "domains_portfolio_purchase"}) == "danger")
check("single action, no operation at all: danger (fail-closed)", cls(gw, "execute", {}) == "danger")
check("single action, read value is matched whole, not by prefix",
      cls(gw, "execute", {"operation": "domains_portfolio_list_and_delete"}) == "danger")
check("listing time (no args): gateway shown so it can be listed",
      cls(gw, "execute") == "read" and cls(gw, "multi-execute") == "read")
check("list gateway: all reads -> read",
      cls(gw, "multi-execute", {"steps": [{"operation": "domains_portfolio_list"},
                                          {"operation": "vps_virtual-machines_list"}]}) == "read")
check("list gateway: one write among reads -> danger",
      cls(gw, "multi-execute", {"steps": [{"operation": "domains_portfolio_list"},
                                          {"operation": "dns_zone_update"}]}) == "danger")
check("list gateway: steps missing or not a list -> danger",
      cls(gw, "multi-execute", {}) == "danger" and cls(gw, "multi-execute", {"steps": "x"}) == "danger")
ok, _ = mcp_catalog.allowed(gw, "readonly", "full", "execute", {"operation": "domains_portfolio_list"})
check("read-only connection can run a read operation through the gateway", ok is True)
ok, _ = mcp_catalog.allowed(gw, "safe", "full", "execute", {"operation": "domains_portfolio_purchase"})
check("Draft level cannot run an unlisted operation through the gateway", ok is False)

# ============================================================
# 4. Existing connections move to the new command
# ============================================================
# A connection stores its command when it is created, so without `lenh_cu` an existing Google
# Ads connection would keep running GitHub main forever and the rule would only reach new ones.
import mcp_store  # noqa: E402


def resolved_of(cid):
    return next(r for r in mcp_store.resolved(enabled_only=False) if r["id"] == cid)


old_ads = ["--from", "git+https://github.com/googleads/google-ads-mcp.git", "google-ads-mcp"]
cid_old, _ = mcp_store.add_connection("google-ads", {
    "label": "old", "command": "uvx", "args": old_ads,
    "fields": {"client_id": "x", "client_secret": "y", "developer_token": "D"}})
r = resolved_of(cid_old)
check("old Google Ads connection now runs the official release",
      r["command"] == "uvx" and r["args"] == ["google-ads-mcp@latest"], (r["command"], r["args"]))
custom = ["--from", "google-ads-mcp==0.0.3", "google-ads-mcp"]
cid_custom, _ = mcp_store.add_connection("google-ads", {
    "label": "custom", "command": "uvx", "args": custom,
    "fields": {"client_id": "x", "client_secret": "y", "developer_token": "D"}})
check("a command the user changed by hand is kept", resolved_of(cid_custom)["args"] == custom)
cid_new, _ = mcp_store.add_connection("google-ads", {
    "label": "new", "fields": {"client_id": "x", "client_secret": "y", "developer_token": "D"}})
check("a new connection takes the catalog command", resolved_of(cid_new)["args"] == ["google-ads-mcp@latest"])
cid_zalo, _ = mcp_store.add_connection("zalo", {
    "label": "zalo-old", "command": "npx", "args": ["-y", "zalo-agent-cli", "mcp", "start"]})
check("old unpinned Zalo connection moves to the pinned command",
      resolved_of(cid_zalo)["args"] == zalo["args"], resolved_of(cid_zalo)["args"])
for c in raw["connectors"]:
    for cu in c.get("lenh_cu") or []:
        check(f"{c['id']}: an old command is never the current one",
              (cu.get("command"), cu.get("args")) != (c.get("command"), c.get("args")))

if _fails:
    print(f"\nFAIL - test_mcp_official_release: {len(_fails)} failed: {_fails}")
    raise SystemExit(1)
print("\nOK - test_mcp_official_release")
