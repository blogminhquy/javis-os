"""plugin_authoring.py - create, read and edit USER plugins in place, for the `javis_plugin` tool.

Why this exists (owner, 2026-10-25): asked in chat to make a plugin, Javis used to hand the owner
a zip to download and upload again. API engines only write inside the vault through the vault
tools, and CLI engines are not guaranteed write access to `<JAVIS_STATE_DIR>`, so the model had no
way to put a plugin where the app loads it. This module is that way, behind one hub tool every
engine reaches (`system/plugins/javis-plugin`).

Safety rules (hard, no argument changes them):
    - A plugin written here is NEVER switched on by the model. Create writes `enabled: false`. An
      update that changes code (.py) or what the manifest declares (tools, hooks, min_mode, pages,
      anything that is not name/description/version/author) writes `enabled: false` again, so the
      owner re-reads the change before turning it back on. A docs-only update keeps the state.
    - Only user plugins: the global dir (`<JAVIS_STATE_DIR>/plugins`, every brain) or this brain's
      `<vault>/plugins`. A slug owned by a bundled plugin or by a store pack is refused, as is a tool
      name the core or a bundled plugin already uses.
    - Files: relative paths only (no `..`, no absolute, no hidden parts, no symlinks), an extension
      allowlist, per-file / total / count caps. plugin.yaml goes through the safe YAML loader with a
      size cap. Every .py is `compile()`d (never imported, never run): a syntax error refuses the
      whole write and nothing on disk changes.
    - Writes are atomic per plugin: the new folder is built in a hidden staging dir next to the
      plugin dirs (same filesystem), the previous version is moved to `.javis-authoring/bak/<slug>`
      (one-step undo by hand), then the new folder is renamed into place. Hidden dirs are never
      scanned as plugins (only direct children holding plugin.py are).
    - After a change the caller runs `refresh_hub()` (on the event loop) and `rebuild_index()`; the
      plugin loader's own cache is dropped here, right after the swap.
"""
from __future__ import annotations

import ast
import hashlib
import json
import os
import shutil
import sys
import time
import uuid
from pathlib import Path, PurePosixPath
from typing import Dict, List, Optional, Tuple

import yaml
import fastyaml

import localefmt
import plugins_host
from config import STATE_DIR

ALLOWED_EXT = frozenset({".py", ".yaml", ".yml", ".md", ".txt", ".json"})
MAX_FILE_BYTES = 200_000
MAX_TOTAL_BYTES = 600_000
MAX_FILES = 40
MAX_DEPTH = 3
MAX_MANIFEST_BYTES = 20_000
READ_FILE_CHARS = 60_000
READ_TOTAL_CHARS = 150_000

STAGING = ".javis-authoring"
_SKIP_DIRS = frozenset({"__pycache__"})

# Manifest keys that only describe the plugin to people. Changing anything else (tools, hooks,
# min_mode, page/http declarations, keys a future loader reads) counts as changing what runs.
_DOC_KEYS = frozenset({"name", "description", "version", "author", "enabled", "slug"})

# Ledger of plugins this tool created: `delete` only removes those, never one the owner installed.
_LEDGER = STATE_DIR / "plugin-authoring.json"


class AuthoringError(Exception):
    """A refused request. The message is what the model reads, so it says what to do instead."""


# ============================================================
# Small helpers
# ============================================================
def _err(vi: str, en: str, **kw) -> AuthoringError:
    return AuthoringError(localefmt.chu(vi, en, **kw))


def _is_doc_key(key: str) -> bool:
    k = str(key or "")
    return k in _DOC_KEYS or k.startswith(("name_", "description_"))


def _base_dir(scope: str, vault_root: Optional[str]) -> Path:
    if scope == "global":
        return plugins_host.global_plugins_dir()
    if scope == "brain":
        d = plugins_host.vault_plugins_dir(vault_root)
        if d is None:
            raise _err("Không xác định được brain đang làm việc, nên không ghi được plugin riêng của brain. "
                       "Dùng scope='global'.",
                       "No working brain is known, so a brain-private plugin cannot be written. "
                       "Use scope='global'.")
        return d
    raise _err("scope không hợp lệ: {s} (dùng global hoặc brain)",
               "Invalid scope: {s} (use global or brain)", s=repr(scope))


def _scope_of_source(source: str) -> str:
    return "global" if source == "user" else "brain"


def _bundled_tool_names() -> set:
    """Tool names bundled plugins declare in their manifests (read only, no code runs)."""
    out = set()
    try:
        for d in plugins_host.BUNDLED_DIR.iterdir():
            if d.is_dir():
                m, _e = plugins_host._read_manifest(d)
                out.update(str(t) for t in (m.get("tools") or []) if isinstance(t, str))
    except OSError:
        pass
    return out


def _pack_slugs() -> set:
    """Plugin slugs shipped inside installed store packs, enabled or not."""
    out = set()
    try:
        import packs
        base = Path(packs.PACKS_DIR)
        if base.is_dir():
            for pack in base.iterdir():
                pdir = pack / "plugins"
                if pack.is_dir() and pdir.is_dir():
                    out.update(d.name for d in pdir.iterdir() if d.is_dir())
    except Exception:
        pass
    return out


def _read_ledger() -> dict:
    try:
        d = json.loads(_LEDGER.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def _ledger_key(scope: str, base: Path, slug: str) -> str:
    return f"{scope}:{hashlib.sha1(str(base.resolve()).encode('utf-8')).hexdigest()[:12]}:{slug}"


def _ledger_set(key: str, value: Optional[dict]) -> None:
    d = _read_ledger()
    if value is None:
        d.pop(key, None)
    else:
        d[key] = value
    try:
        _LEDGER.parent.mkdir(parents=True, exist_ok=True)
        tmp = _LEDGER.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(_LEDGER)
    except OSError as e:
        print(f"[plugin_authoring] ledger write failed: {e}", file=sys.stderr)


# ============================================================
# Validation
# ============================================================
def clean_rel_path(raw) -> str:
    """Normalised relative path, or AuthoringError. Never touches the disk."""
    s = str(raw or "").strip()
    if not s or "\x00" in s or "\\" in s:
        raise _err("Đường dẫn file không hợp lệ: {p}", "Invalid file path: {p}", p=repr(raw))
    if s.startswith("/") or (len(s) > 1 and s[1] == ":"):
        raise _err("Chỉ nhận đường dẫn TƯƠNG ĐỐI trong thư mục plugin, không nhận {p}",
                   "Only paths RELATIVE to the plugin folder are accepted, not {p}", p=repr(s))
    parts = PurePosixPath(s).parts
    if not parts or any(x in ("", ".", "..") for x in parts):
        raise _err("Đường dẫn không được chứa '..' hay '.': {p}", "A path may not contain '..' or '.': {p}",
                   p=repr(s))
    if any(x.startswith(".") or x in _SKIP_DIRS for x in parts):
        raise _err("Không ghi file ẩn hay thư mục ẩn: {p}", "Hidden files or folders are not written: {p}",
                   p=repr(s))
    if len(parts) > MAX_DEPTH:
        raise _err("Thư mục lồng quá sâu (tối đa {n} cấp): {p}", "Folders nested too deep (max {n}): {p}",
                   n=MAX_DEPTH, p=repr(s))
    ext = PurePosixPath(s).suffix.lower()
    if ext not in ALLOWED_EXT:
        raise _err("Đuôi file {e} không được phép. Chỉ nhận: {ok}", "File type {e} is not allowed. Only: {ok}",
                   e=repr(ext or s), ok=", ".join(sorted(ALLOWED_EXT)))
    return "/".join(parts)


def _parse_manifest(text: str) -> dict:
    if len(text.encode("utf-8")) > MAX_MANIFEST_BYTES:
        raise _err("plugin.yaml quá lớn (tối đa {n} byte)", "plugin.yaml is too large (max {n} bytes)",
                   n=MAX_MANIFEST_BYTES)
    try:
        m = fastyaml.safe_load(text)
    except yaml.YAMLError as e:
        raise _err("plugin.yaml không đọc được: {e}", "plugin.yaml does not parse: {e}", e=str(e)[:300])
    if not isinstance(m, dict):
        raise _err("plugin.yaml phải là một bảng khoá: giá trị", "plugin.yaml must be a key: value mapping")
    return m


def _check_manifest(m: dict, slug: str, warnings: List[str]) -> dict:
    """Validated copy of the manifest. Refuses what would load wrong; warns about the rest."""
    m = dict(m)
    mm = m.get("min_mode")
    if mm not in plugins_host.VALID_MIN_MODE:
        raise _err("plugin.yaml phải khai min_mode là readonly (chỉ đọc/tính), safe (ghi file) hoặc full "
                   "(hành động ra ngoài: gửi, đăng, đặt đơn, trả tiền), đúng với việc tool thật sự làm.",
                   "plugin.yaml must declare min_mode as readonly (read or compute), safe (writes files) or "
                   "full (outside actions: send, post, order, pay), matching what the tool really does.")
    for key in ("tools", "hooks"):
        v = m.get(key)
        if v is None:
            m[key] = []
        elif not isinstance(v, list) or not all(isinstance(x, str) for x in v):
            raise _err("{k} trong plugin.yaml phải là danh sách tên", "{k} in plugin.yaml must be a list of names",
                       k=key)
    reserved = plugins_host._RESERVED_TOOLS | _bundled_tool_names()
    for t in m["tools"]:
        if not plugins_host._TOOL_RE.match(t):
            raise _err("Tên tool không hợp lệ: {t} (chữ thường a-z, số, gạch dưới)",
                       "Invalid tool name: {t} (lowercase a-z, digits, underscore)", t=repr(t))
        if t in reserved:
            raise _err("Tên tool {t} đã thuộc về Javis hoặc một plugin hệ thống. Đặt tên khác.",
                       "The tool name {t} already belongs to Javis or a system plugin. Pick another name.",
                       t=repr(t))
    if not str(m.get("name") or "").strip():
        m["name"] = slug
        warnings.append(localefmt.chu("plugin.yaml thiếu name, đã dùng slug.", "plugin.yaml had no name; used the slug."))
    if not str(m.get("description") or "").strip():
        warnings.append(localefmt.chu("plugin.yaml thiếu description: engine sẽ không biết khi nào gọi tool.",
                                      "plugin.yaml has no description: engines will not know when to call the tool."))
    m["slug"] = slug
    return m


def _registered_tool_names(src: str) -> Optional[set]:
    """Tool names a plugin.py passes to ctx.register_tool(...) as literals; None when undecidable."""
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return None
    names = set()
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr == "register_tool"):
            continue
        val = next((k.value for k in node.keywords if k.arg == "name"), None)
        if val is None and node.args:
            val = node.args[0]
        if not (isinstance(val, ast.Constant) and isinstance(val.value, str)):
            return None
        names.add(val.value)
    return names


def _compile_all(files: Dict[str, str]) -> None:
    for rel, text in sorted(files.items()):
        if rel.lower().endswith(".py"):
            try:
                compile(text, rel, "exec", dont_inherit=True)
            except SyntaxError as e:
                raise _err("Lỗi cú pháp ở {f} dòng {n}: {m}. Chưa ghi gì, sửa rồi gửi lại.",
                           "Syntax error in {f} line {n}: {m}. Nothing was written; fix it and send again.",
                           f=rel, n=e.lineno or "?", m=e.msg)
            except ValueError as e:
                raise _err("{f} không biên dịch được: {m}", "{f} does not compile: {m}", f=rel, m=str(e))


# ============================================================
# Reading what is on disk
# ============================================================
def _walk_files(pdir: Path) -> Tuple[List[Tuple[str, Path]], List[str]]:
    """([(rel, path)] of regular allowlisted files, [skipped rel]) under pdir. Never follows links."""
    keep, skipped = [], []
    for dirpath, dirnames, filenames in os.walk(pdir, followlinks=False):
        here = Path(dirpath)
        dirnames[:] = sorted(d for d in dirnames
                             if not d.startswith(".") and d not in _SKIP_DIRS and not (here / d).is_symlink())
        for fn in sorted(filenames):
            p = here / fn
            rel = p.relative_to(pdir).as_posix()
            if p.is_symlink() or fn.startswith(".") or p.suffix.lower() not in ALLOWED_EXT:
                skipped.append(rel)
                continue
            keep.append((rel, p))
    return keep, skipped


def _find(slug: str, vault_root: Optional[str], scope: str = "") -> Optional[dict]:
    """The plugin with this slug as describe() reports it (the effective copy), or the copy in the
    named scope when `scope` is given. None when absent."""
    if scope:
        base = _base_dir(scope, vault_root)
        pdir = base / slug
        if pdir.is_dir() and not pdir.is_symlink():
            return {"slug": slug, "source": "user" if scope == "global" else "vault", "dir": str(pdir)}
        return None
    for d in plugins_host.describe(vault_root):
        if d.get("slug") == slug:
            return d
    return None


# ============================================================
# Operations
# ============================================================
def list_plugins(vault_root: Optional[str]) -> dict:
    editable, readonly = [], []
    for d in plugins_host.describe(vault_root):
        if d["source"] in ("user", "vault"):
            editable.append({"slug": d["slug"], "name": d["name"], "scope": _scope_of_source(d["source"]),
                             "enabled": d["enabled"], "loaded": d["loaded"], "min_mode": d["min_mode"],
                             "tools": d["tools"], "error": d.get("error") or ""})
        else:
            readonly.append({"slug": d["slug"], "source": d["source"], "tools": d["tools"]})
    return {"user_plugins": editable,
            "system_and_pack_plugins_read_only": readonly,
            "note": "Edit only user_plugins with op=write; system and pack plugins cannot be changed or cloned."}


def read_plugin(slug: str, vault_root: Optional[str], scope: str = "") -> dict:
    slug = str(slug or "").strip()
    if not plugins_host.valid_slug(slug):
        raise _err("slug không hợp lệ: {s}", "Invalid slug: {s}", s=repr(slug))
    d = _find(slug, vault_root, scope)
    if d is None:
        raise _err("Không có plugin {s}. Xem op=list.", "No plugin {s}. See op=list.", s=repr(slug))
    if d["source"] not in ("user", "vault"):
        raise _err("{s} là plugin hệ thống hoặc của gói, chỉ đọc qua trang Plugins, không sửa được.",
                   "{s} is a system or pack plugin; it cannot be read or edited with this tool.", s=repr(slug))
    pdir = Path(d["dir"])
    files, truncated, skipped = {}, [], []
    keep, skipped = _walk_files(pdir)
    total = 0
    for rel, p in keep[:MAX_FILES]:
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            skipped.append(rel)
            continue
        room = min(READ_FILE_CHARS, READ_TOTAL_CHARS - total)
        if room <= 0:
            skipped.append(rel)
            continue
        if len(text) > room:
            text = text[:room]
            truncated.append(rel)
        files[rel] = text
        total += len(text)
    skipped += [rel for rel, _p in keep[MAX_FILES:]]
    manifest, _e = plugins_host._read_manifest(pdir)
    return {"slug": slug, "scope": _scope_of_source(d["source"]), "dir": str(pdir),
            "enabled": bool(manifest.get("enabled", False)), "files": files,
            "truncated": truncated, "skipped": skipped}


def _normalise_files(files) -> Dict[str, str]:
    if files is None:
        return {}
    if isinstance(files, str) and files.strip().startswith("{"):
        # Some engines send an object argument as JSON text; accept it rather than fail the turn.
        try:
            files = json.loads(files)
        except ValueError:
            pass
    if not isinstance(files, dict):
        raise _err("files phải là bảng {đường dẫn tương đối: nội dung chữ}",
                   "files must be a map {relative path: text content}")
    if len(files) > MAX_FILES:
        raise _err("Quá nhiều file (tối đa {n})", "Too many files (max {n})", n=MAX_FILES)
    out, total = {}, 0
    for raw, text in files.items():
        rel = clean_rel_path(raw)
        if not isinstance(text, str):
            raise _err("Nội dung {p} phải là chữ", "The content of {p} must be text", p=rel)
        if "\x00" in text:
            raise _err("{p} chứa ký tự NUL (file nhị phân không được nhận)",
                       "{p} contains a NUL character (binary files are not accepted)", p=rel)
        n = len(text.encode("utf-8"))
        if n > MAX_FILE_BYTES:
            raise _err("{p} quá lớn ({n} byte, tối đa {m})", "{p} is too large ({n} bytes, max {m})",
                       p=rel, n=n, m=MAX_FILE_BYTES)
        if rel in out:
            raise _err("Trùng đường dẫn: {p}", "Duplicate path: {p}", p=rel)
        total += n
        out[rel] = text
    if total > MAX_TOTAL_BYTES:
        raise _err("Tổng dung lượng quá lớn ({n} byte, tối đa {m})", "Total size too large ({n} bytes, max {m})",
                   n=total, m=MAX_TOTAL_BYTES)
    if "plugin.yaml" in out and "plugin.yml" in out:
        raise _err("Chỉ gửi một trong plugin.yaml hoặc plugin.yml", "Send only one of plugin.yaml or plugin.yml")
    return out


def _execution_view(m: dict) -> dict:
    """The manifest minus the keys that only describe it, for "did what runs change?"."""
    out = {k: v for k, v in (m or {}).items() if not _is_doc_key(k)}
    for k in ("tools", "hooks"):
        out[k] = list(out.get(k) or [])
    return out


def write_plugin(slug: str, files, vault_root: Optional[str], scope: str = "global",
                 remove=None) -> dict:
    """Create or update a user plugin. Returns a result dict; raises AuthoringError when refused."""
    slug = str(slug or "").strip()
    scope = str(scope or "global").strip().lower()
    if not plugins_host.valid_slug(slug):
        raise _err("slug không hợp lệ: {s}. Dùng chữ thường không dấu, số, '-', '_' hoặc '.', bắt đầu bằng chữ/số.",
                   "Invalid slug: {s}. Use lowercase ASCII, digits, '-', '_' or '.', starting with a letter or digit.",
                   s=repr(slug))
    if slug in plugins_host._slug_bundled():
        raise _err("{s} là plugin hệ thống đi kèm app, không sửa hay nhân bản được. Đặt slug khác.",
                   "{s} is a system plugin that ships with the app; it cannot be edited or cloned. Pick another slug.",
                   s=repr(slug))
    if slug in _pack_slugs():
        raise _err("{s} thuộc một gói trong Kho cài đặt. Đặt slug khác.",
                   "{s} belongs to a pack from the Store. Pick another slug.", s=repr(slug))
    base = _base_dir(scope, vault_root)
    new_files = _normalise_files(files)
    removing = sorted({clean_rel_path(x) for x in (remove or [])})
    warnings: List[str] = []

    pdir = base / slug
    if pdir.is_symlink() or (pdir.exists() and not pdir.is_dir()):
        raise _err("{p} không phải thư mục plugin thường, không ghi đè.",
                   "{p} is not a plain plugin folder; it is not overwritten.", p=str(pdir))
    exists = pdir.is_dir()

    old_files: Dict[str, str] = {}
    old_manifest: dict = {}
    if exists:
        keep, skipped = _walk_files(pdir)
        if skipped:
            warnings.append(localefmt.chu("Giữ nguyên các file không sửa được bằng tool này: {f}",
                                          "Kept files this tool cannot edit: {f}", f=", ".join(skipped[:10])))
        for rel, p in keep:
            try:
                old_files[rel] = p.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                raise _err("Không đọc được {p} của plugin cũ, không ghi đè.",
                           "Could not read {p} of the existing plugin; nothing was overwritten.", p=rel)
        old_manifest, merr = plugins_host._read_manifest(pdir)
        if merr and not any(k in new_files for k in ("plugin.yaml", "plugin.yml")):
            raise _err("plugin.yaml hiện tại hỏng ({e}). Gửi kèm plugin.yaml mới.",
                       "The current plugin.yaml is broken ({e}). Send a new plugin.yaml with it.", e=merr)
    else:
        if removing:
            raise _err("Plugin chưa có nên không có gì để xoá.", "The plugin does not exist yet, so nothing can be removed.")
        if not ("plugin.yaml" in new_files or "plugin.yml" in new_files) or "plugin.py" not in new_files:
            raise _err("Tạo plugin mới cần ít nhất plugin.yaml và plugin.py.",
                       "A new plugin needs at least plugin.yaml and plugin.py.")

    if exists and not new_files and not removing:
        raise _err("Không có file nào để ghi.", "No files to write.")
    for rel in removing:
        if rel in ("plugin.yaml", "plugin.yml", "plugin.py") or rel in new_files:
            raise _err("Không xoá được {p}.", "Cannot remove {p}.", p=rel)
        if rel not in old_files:
            raise _err("Không có file {p} để xoá.", "There is no file {p} to remove.", p=rel)

    # The folder as it will be after the write.
    final = {k: v for k, v in old_files.items() if k not in removing}
    yaml_new = next((k for k in ("plugin.yaml", "plugin.yml") if k in new_files), "")
    if yaml_new:
        for k in ("plugin.yaml", "plugin.yml"):
            final.pop(k, None)
    final.update(new_files)
    if len(final) > MAX_FILES:
        raise _err("Quá nhiều file (tối đa {n})", "Too many files (max {n})", n=MAX_FILES)
    if sum(len(v.encode("utf-8")) for v in final.values()) > MAX_TOTAL_BYTES:
        raise _err("Tổng dung lượng plugin quá lớn (tối đa {m} byte)", "The plugin is too large in total (max {m} bytes)",
                   m=MAX_TOTAL_BYTES)
    if "plugin.py" not in final:
        raise _err("Plugin cần plugin.py.", "A plugin needs plugin.py.")
    for rel, text in final.items():
        if rel.endswith(".json") and rel in new_files:
            try:
                json.loads(text)
            except ValueError as e:
                warnings.append(localefmt.chu("{p} không phải JSON hợp lệ: {e}", "{p} is not valid JSON: {e}",
                                              p=rel, e=str(e)[:120]))
    _compile_all(final)

    if yaml_new:
        manifest = _check_manifest(_parse_manifest(new_files[yaml_new]), slug, warnings)
    else:
        manifest = _check_manifest(old_manifest, slug, warnings)

    declared = set(manifest.get("tools") or [])
    found = _registered_tool_names(final["plugin.py"])
    if found is not None and found != declared:
        warnings.append(localefmt.chu(
            "tools trong plugin.yaml ({a}) khác tên tool plugin.py đăng ký ({b}).",
            "tools in plugin.yaml ({a}) differ from the names plugin.py registers ({b}).",
            a=", ".join(sorted(declared)) or "-", b=", ".join(sorted(found)) or "-"))
    for d in plugins_host.describe(vault_root):
        if d["slug"] != slug and declared & set(d.get("tools") or []):
            warnings.append(localefmt.chu("Tên tool trùng với plugin {s}; hub sẽ bỏ qua một trong hai.",
                                          "A tool name clashes with plugin {s}; the hub will skip one of them.",
                                          s=d["slug"]))

    code_changed = (not exists
                    or any(k.endswith(".py") and old_files.get(k) != v for k, v in new_files.items())
                    or any(k.endswith(".py") for k in removing))
    decl_changed = exists and _execution_view(manifest) != _execution_view(old_manifest)
    was_enabled = bool(old_manifest.get("enabled", False)) if exists else False
    enabled = was_enabled and not code_changed and not decl_changed
    manifest["enabled"] = enabled
    yaml_text = yaml.safe_dump(manifest, allow_unicode=True, sort_keys=False)
    final.pop("plugin.yml", None)       # always written back as plugin.yaml, the name the loader reads first
    final["plugin.yaml"] = yaml_text

    # Build the new folder next to the plugin dirs (same filesystem), then swap it in.
    stage_root = base / STAGING
    tmp = stage_root / f"tmp-{slug}-{uuid.uuid4().hex[:8]}"
    bak = stage_root / "bak" / slug
    try:
        tmp.mkdir(parents=True, exist_ok=False)
        for rel, text in final.items():
            out = tmp / rel
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(text, encoding="utf-8")
        if exists:
            for rel in skipped_to_copy(pdir):
                src = pdir / rel
                dst = tmp / rel
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst, follow_symlinks=False)
            if was_enabled:
                plugins_host.unload(slug)
            if bak.exists():
                shutil.rmtree(bak, ignore_errors=True)
            bak.parent.mkdir(parents=True, exist_ok=True)
            os.replace(pdir, bak)
            try:
                os.replace(tmp, pdir)
            except OSError:
                os.replace(bak, pdir)
                raise
        else:
            base.mkdir(parents=True, exist_ok=True)
            os.replace(tmp, pdir)
    except AuthoringError:
        raise
    except OSError as e:
        raise _err("Ghi plugin lỗi: {e}. Chưa có gì thay đổi.", "Writing the plugin failed: {e}. Nothing changed.",
                   e=f"{type(e).__name__}: {e}")
    finally:
        if tmp.exists():
            shutil.rmtree(tmp, ignore_errors=True)

    key = _ledger_key(scope, base, slug)
    if not exists:
        _ledger_set(key, {"created": time.strftime("%Y-%m-%dT%H:%M:%S"), "dir": str(pdir)})
    plugins_host.invalidate()

    shadow = ""
    if scope == "global" and vault_root:
        vb = plugins_host.vault_plugins_dir(vault_root)
        if vb is not None and (vb / slug).is_dir():
            shadow = localefmt.chu("Brain này có plugin riêng cùng slug, bản đó che bản toàn cục ở đây.",
                                   "This brain has a private plugin with the same slug; it hides the global one here.")
    if shadow:
        warnings.append(shadow)

    forced_off = exists and was_enabled and not enabled
    if enabled:
        owner = localefmt.chu("Chỉ sửa phần mô tả, plugin vẫn BẬT như trước.",
                              "Only the description changed; the plugin stays ON as before.")
    elif forced_off:
        owner = localefmt.chu("Mã hoặc khai báo đã đổi nên plugin đã được TẮT. Đọc lại thay đổi rồi bật ở trang Plugins.",
                              "The code or declarations changed, so the plugin was switched OFF. Review the change, then turn it on in the Plugins page.")
    else:
        owner = localefmt.chu("Plugin đã cài và đang TẮT. Bật nó ở trang Plugins khi đã xem mã.",
                              "The plugin is installed and OFF. Turn it on in the Plugins page once you have read the code.")
    return {"ok": True, "op": "write", "slug": slug, "scope": scope, "path": str(pdir),
            "created": not exists, "enabled": enabled, "switched_off": forced_off,
            "code_changed": bool(code_changed), "declarations_changed": bool(decl_changed),
            "files": sorted(final), "removed": removing,
            "backup": str(bak) if exists else "", "warnings": warnings, "tell_owner": owner}


def skipped_to_copy(pdir: Path) -> List[str]:
    """Files of an existing plugin this tool does not manage (other extensions), carried over as is.
    Symlinks and hidden entries are left behind on purpose: the new folder holds plain files only."""
    _keep, skipped = _walk_files(pdir)
    out = []
    for rel in skipped:
        p = pdir / rel
        if p.is_file() and not p.is_symlink() and not any(x.startswith(".") for x in PurePosixPath(rel).parts):
            out.append(rel)
    return out


def delete_plugin(slug: str, vault_root: Optional[str], scope: str = "") -> dict:
    """Remove a user plugin THIS TOOL created and that is currently off. The folder moves to the
    backup slot, so it can still be restored by hand. Anything else is left to the Plugins page."""
    slug = str(slug or "").strip()
    if not plugins_host.valid_slug(slug):
        raise _err("slug không hợp lệ: {s}", "Invalid slug: {s}", s=repr(slug))
    d = _find(slug, vault_root, scope)
    if d is None or d["source"] not in ("user", "vault"):
        raise _err("Không có plugin người dùng {s}.", "There is no user plugin {s}.", s=repr(slug))
    sc = _scope_of_source(d["source"])
    base = _base_dir(sc, vault_root)
    pdir = base / slug
    key = _ledger_key(sc, base, slug)
    if key not in _read_ledger():
        raise _err("Plugin {s} không do Javis tạo trong chat, nên chỉ gỡ được ở trang Plugins.",
                   "Plugin {s} was not created by Javis in chat, so only the Plugins page can remove it.", s=repr(slug))
    manifest, _e = plugins_host._read_manifest(pdir)
    if manifest.get("enabled"):
        raise _err("Plugin {s} đang BẬT. Chủ phải tắt nó ở trang Plugins trước.",
                   "Plugin {s} is ON. The owner has to turn it off in the Plugins page first.", s=repr(slug))
    bak = base / STAGING / "bak" / slug
    try:
        if bak.exists():
            shutil.rmtree(bak, ignore_errors=True)
        bak.parent.mkdir(parents=True, exist_ok=True)
        plugins_host.unload(slug)
        os.replace(pdir, bak)
    except OSError as e:
        raise _err("Xoá plugin lỗi: {e}", "Removing the plugin failed: {e}", e=f"{type(e).__name__}: {e}")
    _ledger_set(key, None)
    plugins_host.invalidate()
    return {"ok": True, "op": "delete", "slug": slug, "scope": sc, "backup": str(bak),
            "tell_owner": localefmt.chu("Đã gỡ plugin. Bản sao lưu nằm ở {p}.",
                                        "The plugin was removed. A backup is kept at {p}.", p=str(bak))}


def refresh_hub() -> None:
    """Drop the hub's tool cache so the change shows on the next turn of every engine. Call it on
    the event loop thread, like the /plugins routes do (it also recycles MCP client sessions)."""
    try:
        import mcp_hub
        mcp_hub.invalidate_cache()
    except Exception as e:
        print(f"[plugin_authoring] hub cache refresh failed: {e}", file=sys.stderr)


def rebuild_index(vault_root: Optional[str]) -> None:
    """Rebuild this brain's operations index (Javis/index.md) when the server module is loaded."""
    host = sys.modules.get("main")
    if vault_root and host is not None and callable(getattr(host, "rebuild_javis_index", None)):
        try:
            host.rebuild_javis_index(str(vault_root))
        except Exception as e:
            print(f"[plugin_authoring] index rebuild failed: {e}", file=sys.stderr)
