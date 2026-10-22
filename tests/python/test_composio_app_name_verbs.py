"""An app name that contains a verb must not decide the class of a Composio command.

    python tests/run.py composio_app_name_verbs      (no network)

Real case (2026-10-21): Composio SharePoint tools are named SHARE_POINT_<VERB>_... and SHARE is a
write verb in the rule for COMPOSIO_MULTI_EXECUTE_TOOL. Every SharePoint command, reads included,
fell to `danger`, so listing a folder or downloading a scan was blocked at Read-only and at Draft
and ran only at Full access. The rule now merges the words of known app names (`joined_words`)
before matching verbs, while real share, upload and delete commands stay blocked.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import os
import tempfile

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-composio-verbs-"))

import mcp_catalog  # noqa: E402

_fails = []


def check(name, cond, them=None):
    print(("ok   " if cond else "FAIL ") + name + ("" if cond or them is None else f"  [{them}]"))
    if not cond:
        _fails.append(name)


composio = mcp_catalog.get("composio")
check("the Composio connector is in the shipped catalog", bool(composio))
rule = (composio or {}).get("call_rules", {}).get("COMPOSIO_MULTI_EXECUTE_TOOL") or {}
check("its rule merges the SharePoint app name", "SHARE_POINT" in (rule.get("joined_words") or []))


def kind(*slugs):
    return mcp_catalog.classify(composio, "COMPOSIO_MULTI_EXECUTE_TOOL",
                                {"tools": [{"tool_slug": s, "arguments": {}} for s in slugs]})


# 1. The three commands from the report are reads now.
for slug in ("SHARE_POINT_GET_SITE_DRIVE_ITEM_BY_PATH",
             "SHARE_POINT_DOWNLOAD_FILE_BY_SERVER_RELATIVE_URL",
             "SHARE_POINT_LIST_FILES_IN_FOLDER"):
    check(f"{slug} -> read", kind(slug) == "read", kind(slug))
check("the Outlook control case stays read", kind("OUTLOOK_LIST_MESSAGES") == "read")

# 2. Writes and real shares stay blocked (fail-closed is unchanged).
for slug in ("SHARE_POINT_UPLOAD_FILE", "SHARE_POINT_DELETE_ITEM", "SHARE_POINT_SHARE_FILE",
             "SHARE_POINT_CREATE_FOLDER", "DROPBOX_SHARE_FILE", "GMAIL_SEND_EMAIL"):
    check(f"{slug} -> danger", kind(slug) == "danger", kind(slug))
check("an unknown SharePoint command with no verb -> danger", kind("SHARE_POINT_SITE_INFO") == "danger")
check("one write in a batch makes the whole call danger",
      kind("SHARE_POINT_LIST_FILES_IN_FOLDER", "SHARE_POINT_UPLOAD_FILE") == "danger")

# 3. Permission levels: the reads run at Read-only, the write still needs Full access.
read_call = {"tools": [{"tool_slug": "SHARE_POINT_DOWNLOAD_FILE_BY_SERVER_RELATIVE_URL", "arguments": {}}]}
ok, why = mcp_catalog.allowed(composio, "readonly", "full", "COMPOSIO_MULTI_EXECUTE_TOOL", read_call)
check("Read-only runs a SharePoint download", ok, why)
ok, why = mcp_catalog.allowed(composio, "safe", "full", "COMPOSIO_MULTI_EXECUTE_TOOL", read_call)
check("Draft runs a SharePoint download", ok, why)
write_call = {"tools": [{"tool_slug": "SHARE_POINT_UPLOAD_FILE", "arguments": {}}]}
ok, _ = mcp_catalog.allowed(composio, "readonly", "full", "COMPOSIO_MULTI_EXECUTE_TOOL", write_call)
check("Read-only still blocks a SharePoint upload", not ok)

# 4. The merge itself: exact consecutive words only, left to right.
j = mcp_catalog._join_words
check("merges the phrase", j(["SHARE", "POINT", "GET"], ["SHARE_POINT"]) == ["SHAREPOINT", "GET"])
check("keeps a later SHARE of its own",
      j(["SHARE", "POINT", "SHARE", "FILE"], ["SHARE_POINT"]) == ["SHAREPOINT", "SHARE", "FILE"])
check("does not merge words that are not consecutive",
      j(["SHARE", "FILE", "POINT"], ["SHARE_POINT"]) == ["SHARE", "FILE", "POINT"])
check("no joined_words leaves the words alone", j(["SHARE", "POINT"], None) == ["SHARE", "POINT"])

if _fails:
    raise SystemExit(f"{len(_fails)} FAIL")
print("All passed")
