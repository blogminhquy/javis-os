"""The Google Workspace card runs workspace-mcp's full tool set, and every tool in it is classed right.

    python tests/run.py google_workspace_full_tier

No network, no pytest.

Background (customer report, 2026-11-14): "the Google connection cannot do anything on Forms, Drive and
Sheets". The card ran `workspace-mcp --tool-tier core`, 43 tools that leave out the everyday ones:
editing a form's questions, reading its responses, listing a Drive folder, renaming, moving or copying a
file, finding a spreadsheet's tabs, adding a tab, appending rows. The card promised Forms, Drive and
Sheets, so the model got the job with no tool to do it.

Tier `complete` fixes that, and brings 76 more tools. Several of them carry no write word in their name,
so classify() would have put them in READ and a Read-only connection could run them (copying a Drive
file, appending rows, writing a PDF into Drive). The list below is the real `tools/list` of
workspace-mcp 2.4.2 at tier complete with each tool's MCP readOnlyHint, so a tool that writes can never
again slip into the read group unnoticed.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401  - puts server/ on sys.path
import json
import os
import tempfile

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-ws-tier-"))

import mcp_catalog  # noqa: E402
import mcp_store  # noqa: E402

_fails = []


def check(name, cond, extra=None):
    print(("ok   " if cond else "FAIL ") + name + ("" if cond or extra is None else f"  [{extra}]"))
    if not cond:
        _fails.append(name)


raw = json.loads((ROOT / "system" / "mcp-catalog.json").read_text(encoding="utf-8"))
ws_raw = next(c for c in raw["connectors"] if c["id"] == "google-workspace")
ws = mcp_catalog.get("google-workspace")

# ============================================================
# 1. The card runs the full tool set, and old connections follow
# ============================================================
args = ws_raw["args"]
tier = args[args.index("--tool-tier") + 1] if "--tool-tier" in args else None
check("Google Workspace runs tier complete (core has no form editing, no Drive listing, no tab tools)",
      tier == "complete", args)
check("still the official release, latest", args[0] == "workspace-mcp@latest", args)
check("no --tools filter: every service the card promises is loaded", "--tools" not in args, args)
old = [c.get("args") for c in ws_raw.get("lenh_cu") or []]
check("the previous default (latest + core) is an old command, so existing connections move",
      ["workspace-mcp@latest", "--tool-tier", "core"] in old, old)
check("the first default (bare name + core) is still an old command",
      ["workspace-mcp", "--tool-tier", "core"] in old, old)


def resolved_of(cid):
    return next(r for r in mcp_store.resolved(enabled_only=False) if r["id"] == cid)


fields = {"client_id": "x.apps.googleusercontent.com", "client_secret": "y", "user_email": "a@example.com"}
cid_core, _ = mcp_store.add_connection("google-workspace", {
    "label": "made-with-core", "command": "uvx", "args": ["workspace-mcp@latest", "--tool-tier", "core"],
    "fields": fields})
check("a connection made with the old core command now runs tier complete",
      resolved_of(cid_core)["args"] == args, resolved_of(cid_core)["args"])
hand = ["workspace-mcp@latest", "--tools", "drive", "sheets", "--tool-tier", "extended"]
cid_hand, _ = mcp_store.add_connection("google-workspace", {
    "label": "hand-made", "command": "uvx", "args": hand, "fields": fields})
check("a command the user set by hand is kept", resolved_of(cid_hand)["args"] == hand)

# ============================================================
# 2. Every tool of tier complete is classed right
# ============================================================
# name -> MCP readOnlyHint, from workspace-mcp 2.4.2 `tools/list` at tier complete.
TOOLS = {
    # Apps Script
    "get_script_project": True, "manage_script_content": False, "run_script_function": False,
    "manage_deployment": False, "list_script_deployments": True, "manage_script_project": False,
    "manage_script_version": False, "get_script_version": True, "get_script_activity": True,
    "generate_trigger_code": True, "manage_script_trigger": False,
    # Calendar
    "list_calendars": True, "get_events": True, "manage_event": False, "manage_out_of_office": False,
    "manage_focus_time": False, "query_freebusy": True, "manage_calendar": False,
    # Chat
    "list_spaces": True, "get_messages": True, "send_message": False, "search_messages": True,
    "create_reaction": False, "download_chat_attachment": False,
    # Contacts
    "list_contacts": True, "get_contact": True, "search_contacts": True, "manage_contact": False,
    "list_contact_groups": True, "get_contact_group": True, "manage_contacts_batch": False,
    "manage_contact_group": False,
    # Docs
    "search_docs": True, "get_doc_content": True, "list_docs_in_folder": True, "create_doc": False,
    "modify_doc_text": False, "find_and_replace_doc": False, "insert_doc_elements": False,
    "insert_doc_image": False, "update_doc_headers_footers": False, "batch_update_doc": False,
    "inspect_doc_structure": True, "create_table_with_data": False, "debug_table_structure": True,
    "export_doc_to_pdf": False, "update_paragraph_style": False, "get_doc_as_markdown": True,
    "manage_doc_tab": False, "list_document_comments": True, "manage_document_comment": False,
    # Drive
    "search_drive_files": True, "get_drive_file_content": True, "get_drive_file_download_url": True,
    "list_drive_items": True, "create_drive_folder": False, "create_drive_file": False,
    "import_to_google_doc": False, "import_to_google_slides": False, "import_to_google_sheets": False,
    "get_drive_file_permissions": True, "check_drive_file_public_access": True, "update_drive_file": False,
    "get_drive_shareable_link": True, "manage_drive_access": False, "copy_drive_file": False,
    "set_drive_file_permissions": False,
    # Forms
    "create_form": False, "get_form": True, "set_publish_settings": False, "get_form_response": True,
    "list_form_responses": True, "batch_update_form": False,
    # Gmail
    "search_gmail_messages": True, "get_gmail_message_content": True, "get_gmail_messages_content_batch": True,
    "get_gmail_attachment_content": False, "send_gmail_message": False, "draft_gmail_message": False,
    "get_gmail_thread_content": True, "get_gmail_threads_content_batch": True, "list_gmail_labels": True,
    "manage_gmail_label": False, "list_gmail_filters": True, "manage_gmail_filter": False,
    "modify_gmail_message_labels": False, "batch_modify_gmail_message_labels": False,
    # Custom Search
    "search_custom": True, "get_search_engine_info": True,
    # Sheets
    "list_spreadsheets": True, "get_spreadsheet_info": True, "read_sheet_values": True,
    "modify_sheet_values": False, "format_sheet_range": False, "manage_conditional_formatting": False,
    "create_spreadsheet": False, "create_sheet": False, "list_sheet_tables": True, "append_table_rows": False,
    "manage_sheet_tab": False, "resize_sheet_dimensions": False, "move_sheet_rows": False,
    "manage_named_range": False, "list_spreadsheet_comments": True, "manage_spreadsheet_comment": False,
    # Slides
    "create_presentation": False, "get_presentation": True, "batch_update_presentation": False,
    "get_page": True, "render_page_to_image": True, "list_presentation_comments": True,
    "manage_presentation_comment": False,
    # Tasks
    "list_task_lists": True, "get_task_list": True, "manage_task_list": False, "list_tasks": True,
    "get_task": True, "manage_task": False,
    # Auth
    "start_google_auth": False,
}
check("the fixture is the whole tier (119 tools)", len(TOOLS) == 119, len(TOOLS))

# Not read-only by MCP's own hint, yet nothing changes on Google's side: they open a sign-in, or save
# an attachment on the machine running Javis. Reviewed one by one; the catalog lists them too.
REVIEWED_READ = {"start_google_auth", "download_chat_attachment", "get_gmail_attachment_content"}
check("the catalog records the reviewed read tools",
      REVIEWED_READ <= set(ws_raw.get("ghi_da_can_nhac") or []), ws_raw.get("ghi_da_can_nhac"))

DANGER = {
    "send_gmail_message", "send_message", "run_script_function",          # send, run code (as before)
    "manage_drive_access", "set_drive_file_permissions",                   # share a file, hand over ownership
    "manage_gmail_filter",                                                 # acts on every future mail
    "manage_deployment",                                                   # publishes Apps Script
    "manage_task_list",                                                    # deletes a whole list (same as the Tasks card)
}
cls = {t: mcp_catalog.classify(ws, t) for t in TOOLS}
# A tool with a call rule is classed per action at call time (section 4); with no args classify() gives
# the lightest level any of its actions reaches, so manage_calendar lists at Read only for list_sharing.
ruled = {t for t in TOOLS if mcp_catalog.call_rule(ws, t) is not None}
check("call rules cover the combined tools that need them",
      ruled == {"manage_sheet_tab", "manage_doc_tab", "manage_contact_group", "manage_contacts_batch",
                "manage_calendar", "update_drive_file"}, sorted(ruled))
leaked = sorted(t for t, ro in TOOLS.items()
                if not ro and cls[t] == "read" and t not in REVIEWED_READ and t not in ruled)
check("no tool that writes is classed read: " + (", ".join(leaked) or "none"), not leaked)
hidden = sorted(t for t, ro in TOOLS.items() if ro and cls[t] != "read")
check("no read-only tool is hidden at Read only: " + (", ".join(hidden) or "none"), not hidden)
for t in sorted(DANGER):
    check(f"{t} needs Full access", cls[t] == "danger", cls[t])

# ============================================================
# 3. What the customer asked for runs at Draft (the default)
# ============================================================
DRAFT = ws_raw["default_perm"]
check("default level is still Draft", DRAFT == "safe")
everyday = {
    "batch_update_form": {"form_id": "f", "requests": []},                 # edit form questions
    "list_form_responses": {"form_id": "f"},                               # read answers
    "list_drive_items": {"folder_id": "root"},                             # list a folder
    "update_drive_file": {"file_id": "x", "name": "new name"},             # rename / move
    "copy_drive_file": {"file_id": "x"},                                   # copy
    "get_spreadsheet_info": {"spreadsheet_id": "s"},                       # find the tabs
    "create_sheet": {"spreadsheet_id": "s", "sheet_name": "T2"},           # add a tab
    "append_table_rows": {"spreadsheet_id": "s"},                          # append rows
    "manage_sheet_tab": {"spreadsheet_id": "s", "action": "rename"},       # rename a tab
}
for t, a in everyday.items():
    ok, why = mcp_catalog.allowed(ws, DRAFT, "full", t, a)
    check(f"Draft can run {t}", ok, why)

# ============================================================
# 4. Combined tools: only the action that loses a container or shares needs Full access
# ============================================================
for t in ("manage_sheet_tab", "manage_doc_tab", "manage_contact_group", "manage_contacts_batch"):
    check(f"{t} delete needs Full access", mcp_catalog.classify(ws, t, {"action": "delete"}) == "danger")
    check(f"{t} with no action stays at Draft", mcp_catalog.classify(ws, t, {}) == "write")
check("manage_sheet_tab rename stays at Draft",
      mcp_catalog.classify(ws, "manage_sheet_tab", {"action": "rename"}) == "write")
check("manage_calendar create stays at Draft",
      mcp_catalog.classify(ws, "manage_calendar", {"action": "create"}) == "write")
check("manage_calendar list_sharing is a read",
      mcp_catalog.classify(ws, "manage_calendar", {"action": "list_sharing"}) == "read")
for act in ("share", "update_sharing", "unshare", "something_new"):
    check(f"manage_calendar {act} needs Full access",
          mcp_catalog.classify(ws, "manage_calendar", {"action": act}) == "danger")
check("update_drive_file trashed=true is a delete: Full access",
      mcp_catalog.classify(ws, "update_drive_file", {"file_id": "x", "trashed": True}) == "danger")
check("update_drive_file trashed=false stays at Draft",
      mcp_catalog.classify(ws, "update_drive_file", {"file_id": "x", "trashed": False}) == "write")
ok, _ = mcp_catalog.allowed(ws, DRAFT, "full", "manage_drive_access", {"file_id": "x", "action": "grant"})
check("Draft cannot share a Drive file", ok is False)
ok, _ = mcp_catalog.allowed(ws, "readonly", "full", "copy_drive_file", {"file_id": "x"})
check("Read only cannot copy a Drive file", ok is False)
ok, _ = mcp_catalog.allowed(ws, "readonly", "full", "get_drive_shareable_link", {"file_id": "x"})
check("Read only can get a file's link (it changes nothing)", ok is True)

# ============================================================
# 5. Unchanged behaviour the owner chose earlier
# ============================================================
check("manage_event delete stays at Draft (single event, as the risk text says)",
      mcp_catalog.classify(ws, "manage_event", {"action": "delete"}) == "write")
check("manage_task delete stays at Draft (single to-do)",
      mcp_catalog.classify(ws, "manage_task", {"action": "delete"}) == "write")
check("generate_trigger_code only returns code: read", cls["generate_trigger_code"] == "read")

# The risk text names what the new tools can do, at the level they run.
risk = ws_raw.get("risk", "")
check("risk text tells Draft can edit forms and append rows", "Google Form" in risk and "Sheets" in risk)
check("risk text tells Full access can SHARE files", "CHIA SẺ" in risk)

if _fails:
    print(f"\nFAIL - test_google_workspace_full_tier: {len(_fails)} failed: {_fails}")
    raise SystemExit(1)
print("\nOK - test_google_workspace_full_tier")
