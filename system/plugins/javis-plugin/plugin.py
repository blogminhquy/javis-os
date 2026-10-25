"""Bundled plugin: `javis_plugin`, create, read and edit user plugins from chat (owner, 2026-10-25).

Asked to make a plugin, Javis used to give the owner a zip to download and upload again: API engines
write only inside the vault, and CLI engines may not reach `<JAVIS_STATE_DIR>`. This tool installs
the plugin where the app loads it, for every engine. The work and every safety rule live in
`server/plugin_authoring.py`; this file only maps the ops.

Levels per op (`op_modes`): list and read run at every level, write and delete need `safe`, so a
read-only (`suggest`) turn cannot change a plugin. Owner only: `mcp_hub.OWNER_ONLY_TOOLS` lists it,
so a customer-facing bot never sees it.
"""
from __future__ import annotations

import asyncio
import json

import plugin_authoring

_DESC = (
    "Create, read and edit the owner's own plugins (native Python tools/hooks every engine can call) "
    "in place, so they install straight onto the Plugins page. Never hand the owner a zip or write "
    "plugin files by hand. "
    "op=list: user plugins (slug, scope, enabled, load error) plus read-only system/pack plugins. "
    "op=read {slug}: the plugin's files. "
    "op=write {slug, files: {relative path: text}, scope?, remove?}: create (needs plugin.yaml + "
    "plugin.py) or update (send only changed files; remove = paths to delete). scope='global' "
    "(default, every brain) or 'brain' (this brain only). plugin.yaml must declare min_mode matching "
    "what the tool does (readonly | safe = writes files | full = outside actions). Syntax errors are "
    "refused and nothing is written. "
    "The plugin installs OFF: a new plugin, or an update that changes code or declared tools/hooks/"
    "min_mode, is switched off and only the owner turns it on in the Plugins page; you can never "
    "enable it. Say so in your reply. "
    "op=delete {slug}: remove a plugin this tool created that is off; otherwise the owner uses the "
    "Plugins page. Load the javis-builder skill for the plugin template."
)


def register(ctx):
    ctx.register_tool(
        "javis_plugin",
        _DESC,
        _run,
        schema={
            "type": "object",
            "properties": {
                "op": {"type": "string", "enum": ["list", "read", "write", "delete"]},
                "slug": {"type": "string", "description": "lowercase ASCII folder name, e.g. 'vat-calc'"},
                "scope": {"type": "string", "enum": ["global", "brain"],
                          "description": "write: where to install (default global). read/delete: pick a copy"},
                "files": {"type": "object", "additionalProperties": {"type": "string"},
                          "description": "write: {relative path: full text}, e.g. {'plugin.yaml': '...', "
                                         "'plugin.py': '...'}. Allowed: .py .yaml .yml .md .txt .json"},
                "remove": {"type": "array", "items": {"type": "string"},
                           "description": "write: relative paths to delete from an existing plugin"},
            },
            "required": ["op"],
        },
        min_mode="readonly",
        op_modes={"list": "readonly", "read": "readonly", "write": "safe", "delete": "safe"},
        emoji="🧩",
    )


def _dispatch(args: dict, vault_root: str) -> str:
    op = str(args.get("op") or "").strip().lower()
    try:
        if op == "list":
            res = plugin_authoring.list_plugins(vault_root or None)
        elif op == "read":
            res = plugin_authoring.read_plugin(args.get("slug"), vault_root or None, str(args.get("scope") or ""))
        elif op == "write":
            res = plugin_authoring.write_plugin(args.get("slug"), args.get("files"), vault_root or None,
                                                str(args.get("scope") or "global"), args.get("remove"))
        elif op == "delete":
            res = plugin_authoring.delete_plugin(args.get("slug"), vault_root or None, str(args.get("scope") or ""))
        else:
            return f"ERROR: unknown op {op!r} (use list | read | write | delete)"
    except plugin_authoring.AuthoringError as e:
        return f"ERROR: {e}"
    return json.dumps(res, ensure_ascii=False)


async def _run(args, ctx) -> str:
    args = dict(args or {})
    vault_root = getattr(ctx, "vault_root", "") or ""
    out = await asyncio.to_thread(_dispatch, args, vault_root)
    if not out.startswith("ERROR") and str(args.get("op") or "").strip().lower() in ("write", "delete"):
        # Same refresh as the /plugins/toggle route: hub cache on the loop, index off it.
        plugin_authoring.refresh_hub()
        await asyncio.to_thread(plugin_authoring.rebuild_index, vault_root)
    return out
