"""Javis Gate: which brain an outside AI reads and writes (#1726, owner 2026-11-24).

Why this exists
---------------
claude.ai cannot send headers, so a call through the Gate names no brain and the hub fell back to the "open brain": the
brain of the most recently updated conversation (`sessions.brain_gan_nhat`). An owner who had last touched a chat in a
secondary brain got personal notes from claude.ai written there. The owner approved a brain selector for the Gate
(2026-11-24, "ô chọn brain cho Javis Gate anh đồng ý"):

- Every Gate tool that reads or writes a brain takes an optional `brain`: a brain's name (its label, or its folder) or
  its path. It is resolved ONLY against the registered brains (the folders of BRAINS_DIR), never as an arbitrary path,
  with names matched case- and accent-insensitively. An unknown name is refused with the list of valid names.
- `javis_brains` lists the brains, which one is the default, and which one was used last.
- Without `brain`, the Gate uses the default brain the owner picked on the Connections page (settings key
  `gate_default_brain`, the brain's FOLDER name, which never changes on a rename). Empty means "Brain used last",
  exactly the behaviour before this module, so nothing changes for an owner who never picks one.
- The result of every brain-bound tool names the brain it used.

Text returned here goes to the outside AI, so it is English (model-facing). The dashboard reads `card_state`.
"""
from __future__ import annotations

import unicodedata
from pathlib import Path
from typing import List, Optional, Tuple

SETTINGS_KEY = "gate_default_brain"
MAX_VALUE = 500

# The `brain` argument as the Gate's tools/list shows it on every brain-bound tool.
BRAIN_PARAM = {
    "type": "string",
    "description": ("Optional. The brain (the owner's knowledge base) to use: a name or path from javis_brains. "
                    "Leave out to use the default brain."),
}


def fold(value) -> str:
    """Lowercase, no accents ("Đ" -> "d"), spaces collapsed: "Cá Nhân" matches "ca  nhan"."""
    s = unicodedata.normalize("NFD", str(value or "").replace("đ", "d").replace("Đ", "D"))
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
    return " ".join(s.casefold().split())


def brains_dir() -> Path:
    import default_brain
    return default_brain.brains_dir_from_env()


def _resolved(p) -> str:
    try:
        return str(Path(p).expanduser().resolve())
    except (OSError, ValueError, RuntimeError):
        return str(p)


def registered() -> List[dict]:
    """Every brain on this Javis, in the owner's order (the brain picker's): [{"folder", "name", "path"}].

    `folder` is the brain's address and never changes; `name` is what the owner sees (brain_label, the folder until
    renamed); `path` is the resolved folder."""
    import brain_label
    import brain_order
    base = brains_dir()
    rows = []
    try:
        entries = sorted(base.iterdir(), key=lambda x: x.name.lower())
    except OSError:
        return []
    for p in entries:
        try:
            if not p.is_dir() or p.name.startswith("."):
                continue
        except OSError:
            continue
        rows.append({"name": p.name, "label": brain_label.display(p), "path": _resolved(p)})
    try:
        import config as cfgmod
        order = (cfgmod.read_settings() or {}).get(brain_order.SETTINGS_KEY) or []
    except Exception:  # noqa: BLE001 - an unreadable settings file only loses the owner's order
        order = []
    return [{"folder": r["name"], "name": r["label"], "path": r["path"]} for r in brain_order.sort(rows, order)]


def _refused(path: str) -> bool:
    """Defence in depth: a registered brain never points at Javis's own state (mcp_hub.vault_header_refused)."""
    try:
        import mcp_hub
        return bool(mcp_hub.vault_header_refused(path))
    except Exception:  # noqa: BLE001 - the check itself failing must not open anything
        return True


def _looks_like_path(v: str) -> bool:
    return "/" in v or "\\" in v or v.startswith("~")


def names_list(brains: List[dict]) -> str:
    return ", ".join(f'"{b["name"]}"' for b in brains) or "(none)"


def resolve(value, brains: Optional[List[dict]] = None) -> Tuple[Optional[dict], str]:
    """(brain, error) for a `brain` argument. (None, "") when the argument is empty.

    A path counts only when it IS one of the registered brains. A name matches a brain's label or folder: exactly
    first, then case- and accent-insensitively. Two brains matching one name is refused rather than guessed."""
    v = " ".join(str(value or "").split())
    if not v:
        return None, ""
    brains = registered() if brains is None else brains
    if len(v) > MAX_VALUE:
        return None, f"brain is too long. Valid brains: {names_list(brains)}."
    if _looks_like_path(v):
        want = _resolved(v)
        hit = next((b for b in brains if b["path"] == want), None)
        if hit and not _refused(hit["path"]):
            return hit, ""
        return None, (f'"{v}" is not the path of a Javis brain. Pass a name or path from javis_brains. '
                      f"Valid brains: {names_list(brains)}.")
    hits = [b for b in brains if v in (b["name"], b["folder"])]
    if not hits:
        f = fold(v)
        hits = [b for b in brains if f in (fold(b["name"]), fold(b["folder"]))]
    hits = list({b["path"]: b for b in hits}.values())
    if len(hits) == 1 and not _refused(hits[0]["path"]):
        return hits[0], ""
    if len(hits) > 1:
        return None, (f'"{v}" matches several brains ({names_list(hits)}). Pass the path from javis_brains instead.')
    return None, f'No brain is called "{v}". Valid brains: {names_list(brains)}.'


def configured_folder() -> str:
    """The folder the owner picked as the Gate's default brain, "" for "Brain used last". May name a brain that has
    since been deleted: `default_brain` checks."""
    try:
        import config as cfgmod
        v = (cfgmod.read_settings() or {}).get(SETTINGS_KEY)
    except Exception:  # noqa: BLE001
        return ""
    return v.strip() if isinstance(v, str) else ""


def default_brain(brains: Optional[List[dict]] = None) -> Optional[dict]:
    """The Gate's fixed default brain, or None (none picked, or the picked brain is gone: then the Gate falls back to
    the brain used last, as before)."""
    folder = configured_folder()
    if not folder:
        return None
    brains = registered() if brains is None else brains
    hit = next((b for b in brains if b["folder"] == folder), None)
    if hit is None or _refused(hit["path"]):
        return None
    return hit


def set_default(folder) -> Tuple[bool, str]:
    """Save the Gate's default brain: a registered folder, or "" for "Brain used last". (ok, error for the screen)."""
    import config as cfgmod
    import localefmt
    f = str(folder or "").strip()
    if f and not any(b["folder"] == f for b in registered()):
        return False, localefmt.chu("Không có brain này trên máy.", "This brain is not on this machine.")
    cfgmod.update_settings({SETTINGS_KEY: f})
    return True, ""


def raw_to_path(raw) -> str:
    """Resolved folder of a brain as stored in `sessions.brain` ("brain" = the default brain, or an absolute path),
    "" when it is neither."""
    s = str(raw or "").strip()
    if not s:
        return ""
    if s == "brain":
        import default_brain
        return _resolved(default_brain.path(brains_dir()))
    p = Path(s).expanduser()
    return _resolved(p) if p.is_absolute() else ""


def same_brain(raw, path: str) -> bool:
    got = raw_to_path(raw)
    return bool(got) and got == _resolved(path)


def label_of(raw) -> str:
    """The name of the brain a session row or a hub vault points at, for results."""
    p = raw_to_path(raw)
    if not p:
        return str(raw or "")
    try:
        import brain_label
        return brain_label.display(p)
    except Exception:  # noqa: BLE001
        return Path(p).name


# How the brain of one call was chosen, as the result line says it.
_HOW = {
    "argument": "named in this call",
    "gate-default": "the default brain for Javis Gate",
    "phien": "the brain the owner used last (no default brain is set for Javis Gate)",
    "duy-nhat": "the only brain on this Javis",
    "header": "set by the client's X-Javis-Vault header",
}


def result_line(vault_root, how: str) -> str:
    """One line under a brain-bound tool's result: the brain it used, and why that one."""
    if not vault_root:
        return no_brain_hint()
    why = _HOW.get(how, "")
    return f'[Javis brain: "{label_of(vault_root)}" ({vault_root})' + (f", {why}" if why else "") + "]"


def no_brain_hint() -> str:
    return ("(Javis Gate could not tell which brain to use: this Javis has more than one brain and none was named. "
            "Call javis_brains, ask the owner which brain they mean, then pass it as brain. The owner can also pick a "
            "default brain for Javis Gate on the Connections page.)")


def listing(last_used_path: str = "") -> dict:
    """What `javis_brains` returns."""
    brains = registered()
    fixed = default_brain(brains)
    last = _resolved(last_used_path) if last_used_path else ""
    rows = []
    for b in brains:
        row = {"name": b["name"], "path": b["path"]}
        if b["folder"] != b["name"]:
            row["folder"] = b["folder"]
        if fixed and b["path"] == fixed["path"]:
            row["default"] = True
        if last and b["path"] == last:
            row["last_used"] = True
        rows.append(row)
    out = {"ok": True, "brains": rows}
    if fixed:
        out["default"] = fixed["name"]
        out["default_rule"] = "Without brain, Gate tools use the default brain the owner picked."
    else:
        out["default"] = None
        out["default_rule"] = ("No default brain is set: without brain, Gate tools use the brain the owner used last "
                               "(the one marked last_used).")
    if len(rows) > 1:
        out["hint"] = ("More than one brain. Unless the owner already named one, ask which brain before you write, "
                       "then pass its name as brain.")
    return out


def card_state() -> dict:
    """The Javis Gate card on the Connections page: whether the Gate package is installed, its page, the brains and
    the default the owner picked ("" = Brain used last)."""
    installed, page = gate_installed()
    brains = registered()
    folder = configured_folder()
    return {"ok": True, "installed": installed, "page": page,
            "brains": [{"folder": b["folder"], "name": b["name"]} for b in brains],
            "default": folder, "default_missing": bool(folder) and not any(b["folder"] == folder for b in brains)}


GATE_PACK = "javis.gate"
GATE_PLUGIN = "javis-gate"


def gate_installed() -> Tuple[bool, str]:
    """(installed and on, its page) for the Javis Gate package. Never raises: a hint on the Connections page."""
    try:
        import packs
        dirs = packs.plugin_dirs()
    except Exception:  # noqa: BLE001
        return False, ""
    slugs = {d.name for pid, d in dirs if pid == GATE_PACK or d.name == GATE_PLUGIN}
    if not slugs:
        return False, ""
    page = ""
    try:
        import plugins_host
        for p in plugins_host.describe():
            if p.get("slug") in slugs and p.get("page"):
                page = str(p["page"])
                break
    except Exception:  # noqa: BLE001
        page = ""
    return True, page
