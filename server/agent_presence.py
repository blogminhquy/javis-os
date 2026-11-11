"""Keep the Auto registry in step with the assistant files that are really in the brain.

One function, `sync`, for every place where the host looks at a brain's assistants (the Auto list of the Partners
page, a pack install or uninstall). It does three things, all of them the host's own bookkeeping:

1. An `active` key whose file is gone becomes `missing` (as before: every gate of that key closes).
2. An `active` key whose file is there gets its origin recorded: the Store pack that placed the file, untouched, or
   nothing when the file is the user's own.
3. A `missing` key whose file is back is restored without asking when there is nothing to decide
   (`GoalStore.agent_restore`): the same pack put its own file back, or Auto is off and no goal is open.

Why (owner report 2026-11-11): uninstalling and installing a Store pack again left all 17 of its assistants on
"Auto: needs confirmation", one card at a time, on every reinstall. The question exists so that a different file under
an old name cannot inherit a running Auto. A pack putting its own assistant back is not that case, and neither is an
assistant with Auto off and nothing open.
"""
from __future__ import annotations

import sys

ORIGIN_PACK = "pack:"


def pack_map(root: str) -> dict:
    """{slug: pack id} of the untouched pack assistants in this brain. Empty when the pack ledger cannot be read."""
    try:
        import pack_vault
        return pack_vault.agent_packs(root)
    except Exception as e:  # noqa: BLE001 - the Auto list must never fail over the pack ledger
        print(f"[agent presence] pack ledger: {type(e).__name__}: {e}", file=sys.stderr)
        return {}


def pack_name(pack_id: str) -> str:
    """The pack's name as its Store card shows it, in the reader's language. The id when the pack cannot be read.

    Read from the manifest, not from `packs.installed()`: a pack that is switched off is listed there without its
    name, while its assistants are still in the brain and may still be waiting."""
    try:
        import localefmt
        import packs
        folder = packs.PACKS_DIR / str(pack_id)
        if packs.PACKS_DIR.resolve() not in folder.resolve().parents:
            return str(pack_id)
        manifest = next((folder / n for n in packs.MANIFEST_TEN if (folder / n).is_file()), None)
        data = packs._doc_file(manifest) if manifest else {}
        name = packs._ngon_ngu((data or {}).get("name") if isinstance(data, dict) else None, str(pack_id))
        vi = packs._chon(name, "vi") or str(pack_id)
        return localefmt.chu(vi, name.get("en") or vi)
    except Exception:  # noqa: BLE001
        return str(pack_id)


def sync(store, root: str, slugs, packs=None) -> dict:
    """Bring the registry of brain `root` in step with `slugs`, the assistants that have a file right now.

    `packs` is `pack_map(root)` when the caller already has it. Returns {"missing": [slug], "restored": [slug]} so
    the caller knows whether anything changed. Goals of a restored assistant with Auto on are woken, as after the
    owner's own "same assistant"."""
    have = {str(s) for s in (slugs or ())}
    packs = pack_map(root) if packs is None else packs
    origins = store.agent_origins(root)
    out = {"missing": [], "restored": []}
    for a in store.agents(root):
        key, slug = a["agent_key"], a["slug"]
        origin = (ORIGIN_PACK + packs[slug]) if slug in packs else ""
        if a["status"] == "active":
            if slug not in have:
                store.agent_mark_missing(root, key)
                out["missing"].append(slug)
            elif origins.get(key, "") != origin:
                store.agent_set_origin(root, key, origin)
        elif a["status"] == "missing" and slug in have:
            back = store.agent_restore(root, key, origin=origin)
            if back is None:
                continue
            out["restored"].append(slug)
            if back["enabled"]:
                store.wake_agent_goals(root, key, "trợ lý có file trở lại")
    return out
