"""PostHog connector. Run by hand / CI:

    python tests/run.py posthog_connector

No pytest, no network.

Why this file exists. The PostHog card is pure data in system/mcp-catalog.json, and data is easy to get
wrong without anyone noticing. Three things are guarded here:

  1. THE ADDRESS. PostHog's MCP serves its ~1,000 tools behind ONE `exec` tool by default ("cli is the
     default for all clients", services/mcp README). Javis classifies read/write by TOOL NAME, so a single
     `exec` would leave it blind. `?mode=tools` makes the server list every tool under its own name.
  2. FAIL-CLOSED CLASSIFICATION. PostHog keeps adding tools, and many verbs (pause, end, reset, launch...)
     are in no generic write-hint list. Anything the read patterns do not recognise must count as a write,
     never fall through to "read".
  3. DANGER FOR WHAT REACHES REAL USERS. Workflows that broadcast messages, feature flags, experiments,
     surveys, data leaving PostHog and deletes need Full access, not Draft. Tool names below are verbatim
     from PostHog's tool reference (posthog.com/docs/model-context-protocol/tools.md) and
     services/mcp/schema/tool-definitions.json.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401  - put server/ on sys.path
import json
import os
import re
import sys
import tempfile

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-posthog-"))
import localefmt  # noqa: E402
import mcp_catalog as mc  # noqa: E402

failures = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(extra) + "]") if extra and not cond else ""))
    if not cond:
        failures.append(name)


con = mc.get("posthog")
check("catalog has the posthog connector", bool(con))
if not con:
    print("\nFAIL - test_posthog_connector: connector missing")
    sys.exit(1)

# ---- 1. Address and sign-in ----
check("remote http transport", con.get("transport") == "http")
check("official endpoint", (con.get("url") or "").startswith("https://mcp.posthog.com/mcp"), con.get("url"))
check("CANARY: tools mode pinned (default cli mode hides every tool behind one exec)",
      "mode=tools" in (con.get("url") or ""), con.get("url"))
check("api key sign-in", (con.get("auth") or {}).get("type") == "apikey")
headers = mc.build_headers(con, {"api_key": "phx_test123"})
check("key sent as a Bearer token", headers.get("Authorization") == "Bearer phx_test123", headers)
check("only the one header (no empty optional headers)", list(headers) == ["Authorization"], headers)
check("starts at read-only", con.get("default_perm") == "readonly")
check("risk text is there", bool((con.get("risk") or "").strip()))
step_links = [s.get("link", "") for s in (con.get("auth") or {}).get("steps") or []]
check("first step opens the key page with the MCP Server preset",
      bool(step_links) and "settings/user-api-keys" in step_links[0] and "preset=mcp_server" in step_links[0],
      step_links)
check("matched back from its own URL", mc.match_url(con["url"]) == "posthog")

# ---- 2 + 3. Classification ----
READS = [
    "execute-sql", "read-data-schema", "insight-query", "insight-trust-check", "explain-chart",
    "dashboard-get", "dashboards-get-all", "dashboard-insights-run", "feature-flag-get-all",
    "feature-flag-get-definition-by-key", "feature-flags-status-retrieve", "experiment-get", "experiment-list",
    "experiment-results-get", "experiment-timeseries-results", "annotations-list", "cohorts-list",
    "cohorts-retrieve", "query-error-tracking-issues-list", "query-llm-traces-list", "docs-search",
    "alerts-list", "alert-get", "billing-usage-get", "get-llm-total-costs-for-project", "project-get",
    "workflows-blast-radius", "external-data-sync-logs",
]
WRITES = [
    "dashboard-create", "dashboard-update", "dashboard-create-tile", "annotation-create",
    "annotations-partial-update", "action-create", "action-update", "error-tracking-issues-partial-update",
    "error-tracking-issues-merge-create", "switch-project", "switch-organization", "path-cleaning-rules-update",
    "explain-chart-save", "announcements-create-prepare",
    # Names PostHog may add later: unknown verbs must never become reads.
    "dashboard-pin", "insight-freeze", "some-future-tool",
]
DANGERS = [
    # Messages to real users, now or on a schedule.
    "workflows-run-batch", "workflows-schedule-create", "workflows-enable", "workflows-disable",
    "conversations-tickets-reply-create", "conversations-tickets-compose-create", "event-streams-send-test-message",
    # What end users see.
    "create-feature-flag", "update-feature-flag", "feature-flag-enable", "feature-flag-disable",
    "feature-flag-roll-out-to-everyone", "feature-flag-rules-update", "scheduled-changes-create",
    "early-access-feature-create", "experiment-create", "experiment-launch", "experiment-pause",
    "experiment-end", "experiment-ship-variant", "experiment-reset", "cohorts-partial-update",
    "cohorts-add-persons-to-static-cohort-partial-update", "canvas-publish-create", "canvas-promote-create",
    # Notifications and data leaving PostHog.
    "alert-create", "alert-destinations-create", "error-tracking-alerts-create", "batch-export-create",
    # Deletes, bulk changes, paid compute, two-step executes, other accounts.
    "delete-feature-flag", "dashboard-delete", "dashboards-bulk-delete", "early-access-feature-destroy",
    "feature-flags-bulk-update-tags-create", "notebooks-run", "notebooks-run-cell", "llma-evaluation-run",
    "access-control-default-rule-set-execute", "announcements-create-execute", "posthog-connection-call",
    "agent-feedback",
]
wrong = [(t, mc.classify(con, t)) for t in READS if mc.classify(con, t) != "read"]
check(f"{len(READS)} read tools classed read", not wrong, wrong)
wrong = [(t, mc.classify(con, t)) for t in WRITES if mc.classify(con, t) != "write"]
check(f"{len(WRITES)} write tools classed write (unknown names fail closed)", not wrong, wrong)
wrong = [(t, mc.classify(con, t)) for t in DANGERS if mc.classify(con, t) != "danger"]
check(f"{len(DANGERS)} tools that reach real users or delete classed danger", not wrong, wrong)

# What the permission levels let through.
check("read-only runs execute-sql", mc.allowed(con, "readonly", "full", "execute-sql")[0])
check("read-only blocks dashboard-create", not mc.allowed(con, "readonly", "full", "dashboard-create")[0])
check("draft allows dashboard-create", mc.allowed(con, "safe", "full", "dashboard-create")[0])
check("draft blocks workflows-run-batch", not mc.allowed(con, "safe", "full", "workflows-run-batch")[0])
check("full allows workflows-run-batch", mc.allowed(con, "full", "full", "workflows-run-batch")[0])

# ---- What the Connections page shows ----
VIET = re.compile("[ăđơưảãạằắẳẵặầấẩẫậẻẽẹềếểễệỉĩịỏõọồốổỗộờớởỡợủũụừứửữựỳỷỹỵ]", re.I)
token = localefmt.dat_ngon_ngu_yeu_cau("en")
try:
    pub_en = {c["id"]: c for c in mc.public_catalog()}.get("posthog") or {}
finally:
    localefmt.bo_ngon_ngu_yeu_cau(token)
shown = {k: pub_en.get(k) for k in ("name", "description", "guide", "risk", "fields", "steps")}
check("English card has no Vietnamese left", bool(pub_en) and not VIET.search(json.dumps(shown, ensure_ascii=False)))
check("English steps keep the links of the source",
      [s.get("link") for s in pub_en.get("steps") or []] == step_links)

print()
if failures:
    print(f"FAIL {len(failures)}: {failures}")
    sys.exit(1)
print("OK - test_posthog_connector: all pass")
