"""Install ONE plugin from a .zip file (Plugins page, "Install from .zip").

Owner request 2026-10-25: "Ở phần plugin thêm luôn cho anh cài từ tệp zip nữa nhé."

What this module is NOT: a second zip extractor. Every zip rule (traversal, absolute paths,
symlinks via `external_attr`, archive modes ignored, size and compression-ratio caps, sensitive
names, zip only) lives in `pack_install.extract_checked`, and this module calls exactly that.
A fix to the zip rules then lands in both installers at once.

Two steps, like packs
---------------------
`inspect()` extracts into `STATE_DIR/plugins-staging/<sha>/<slug>/` (OUTSIDE the plugins folder,
so nothing half-inspected is ever loaded) and returns exactly what the confirmation screen
shows, with the zip's `sha256`. `install()` only proceeds when the caller hands back that same
sha256, so what the person read is what gets installed.

Rules on top of the zip rules
-----------------------------
- The zip holds ONE plugin: `plugin.yaml` + `plugin.py` (or `__init__.py`) at the root or inside
  one wrapper folder. A full store pack (it has `javis-pack.yaml`) is reported as `kind: pack`
  so the route hands it to the pack installer instead of a weaker copy of it.
- No compiled or native code (`.pyc`, `.so`, ...): the screen lists the source files the person
  can read, and an unchecked-hash `.pyc` would run something else than that source.
- The slug must pass `plugins_host.valid_slug` and may not shadow a bundled plugin or a plugin
  that came with a store pack. Replacing an existing GLOBAL user plugin needs `replace=True`,
  which the dashboard only sends after the person flips "Replace the installed version".
- The installed manifest is rewritten with `enabled: false` whatever the zip says (CLAUDE.md:
  user plugins start off, the owner switches them on in the app).
"""
from __future__ import annotations

import ast
import hashlib
import shutil
import sys
import time
from pathlib import Path

import yaml

import fastyaml
import localefmt
import pack_install
import packs
import plugins_host
from config import STATE_DIR

STAGING = STATE_DIR / "plugins-staging"
MANIFEST_NAMES = ("plugin.yaml", "plugin.yml")
# Compiled or native code. Refused because the confirmation shows readable sources only.
BINARY_CODE = (".pyc", ".pyo", ".so", ".pyd", ".dll", ".dylib")
FILES_SHOWN = 200


def _err(stage: str, vi: str, en: str, **extra) -> dict:
    out = {"ok": False, "stage": stage, "error": localefmt.chu(vi, en)}
    out.update(extra)
    return out


def _manifest_file(d: Path):
    return next((d / n for n in MANIFEST_NAMES if (d / n).is_file()), None)


def _read_manifest(f: Path):
    """(manifest dict, error dict or None). Same size cap and safe loader as pack manifests."""
    if f.stat().st_size > pack_install.MAX_MANIFEST:
        return None, _err("validate", "plugin.yaml quá lớn", "plugin.yaml is too large")
    try:
        m = fastyaml.safe_load(f.read_text(encoding="utf-8"))
    except Exception as e:      # noqa: BLE001
        return None, _err("validate", f"plugin.yaml lỗi: {e}", f"plugin.yaml error: {e}")
    if not isinstance(m, dict):
        return None, _err("validate", "plugin.yaml phải là một bảng khoá: giá trị",
                          "plugin.yaml must be a key: value mapping")
    return m, None


def _pack_slugs() -> set:
    """Plugin slugs that belong to a store pack, enabled or not."""
    out = set()
    try:
        out |= {d.name for _pid, d in packs.plugin_dirs()}
    except Exception as e:      # noqa: BLE001
        print(f"[plugin-zip] pack plugins: {e}", file=sys.stderr)
    for row in (pack_install.doc_so() or {}).values():
        out |= set((row or {}).get("plugins") or [])
    return out


def _collision(slug: str) -> dict:
    """Error dict when `slug` may never be installed from a zip, else {}."""
    if slug in plugins_host._slug_bundled():
        return _err("validate",
                    f"'{slug}' trùng tên một plugin có sẵn của Javis. Đổi slug trong plugin.yaml rồi thử lại.",
                    f"'{slug}' is the name of a built-in Javis plugin. Change the slug in plugin.yaml and try again.",
                    code="bundled")
    if slug in _pack_slugs():
        return _err("validate",
                    f"'{slug}' trùng tên một plugin đến từ gói trong Javis Store. Đổi slug trong plugin.yaml rồi thử lại.",
                    f"'{slug}' is the name of a plugin from a Javis Store pack. Change the slug in plugin.yaml and try again.",
                    code="pack")
    return {}


def _const(node):
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


def declared_tools(manifest: dict, sources: dict) -> list:
    """[{name, min_mode}] from the manifest `tools` list plus `register_tool(...)` calls found by
    READING the source (ast, never executed). Informational: the code is what really decides."""
    base = str(manifest.get("min_mode") or "readonly")
    base = base if base in plugins_host.VALID_MIN_MODE else "readonly"
    found: dict = {}
    order: list = []

    def add(name, mm):
        if not isinstance(name, str) or not name.strip():
            return
        name = name.strip()
        if name not in found:
            order.append(name)
            found[name] = None
        if mm in plugins_host.VALID_MIN_MODE:
            found[name] = mm

    for t in manifest.get("tools") or []:
        if isinstance(t, dict):
            add(t.get("name"), t.get("min_mode"))
        else:
            add(t if isinstance(t, str) else None, None)
    for text in sources.values():
        try:
            tree = ast.parse(text)
        except (SyntaxError, ValueError):
            continue
        for n in ast.walk(tree):
            if not (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                    and n.func.attr == "register_tool"):
                continue
            kw = {k.arg: k.value for k in n.keywords if k.arg}
            name = _const(kw.get("name")) or (_const(n.args[0]) if n.args else None)
            mm = _const(kw.get("min_mode")) or (_const(n.args[5]) if len(n.args) > 5 else None)
            add(name, mm)
    return [{"name": x, "min_mode": found[x] or base} for x in order]


def _check_tree(d: Path) -> dict:
    """Plugin-shape rules on an extracted tree. {} when fine."""
    for f in d.rglob("*"):
        if f.is_file() and (f.suffix.lower() in BINARY_CODE or "__pycache__" in f.parts):
            rel = str(f.relative_to(d)).replace("\\", "/")
            return _err("validate", f"không nhận mã đã biên dịch: {rel}",
                        f"compiled code is not accepted: {rel}")
    return {}


def _entry(d: Path):
    return next((d / e for e in plugins_host._ENTRY_FILES if (d / e).is_file()), None)


def inspect(data: bytes, filename: str = "", vault_root: str = "") -> dict:
    """Open, check and stage. Puts NOTHING in the plugins folder."""
    pack_install.don_staging(root=STAGING)
    big = pack_install.zip_too_large(data)
    if big:
        return big
    sha = hashlib.sha256(data).hexdigest()
    wrap = STAGING / sha
    raw = wrap / "_extract"
    if wrap.is_dir():
        shutil.rmtree(wrap, ignore_errors=True)
    res = pack_install.extract_checked(data, raw, STAGING / f"{sha}.zip")
    if not res.get("ok"):
        return res

    def fail(r):
        shutil.rmtree(wrap, ignore_errors=True)
        return r

    # A full store pack: the route passes it to the pack installer (same screen, same rules).
    if any((raw / n).is_file() for n in packs.MANIFEST_TEN):
        shutil.rmtree(wrap, ignore_errors=True)
        return {"ok": True, "kind": "pack"}
    bad = _check_tree(raw)
    if bad:
        return fail(bad)
    mf = _manifest_file(raw)
    if mf is None:
        return fail(_err("validate",
                         "không thấy plugin.yaml ở gốc tệp nén (hoặc trong một thư mục duy nhất)",
                         "no plugin.yaml at the top of the archive (or inside its one folder)"))
    manifest, e = _read_manifest(mf)
    if e:
        return fail(e)
    if _entry(raw) is None:
        return fail(_err("validate", "thiếu plugin.py cạnh plugin.yaml",
                         "plugin.py is missing next to plugin.yaml"))
    slug = str(manifest.get("slug") or res.get("root") or "").strip()
    if not plugins_host.valid_slug(slug):
        return fail(_err("validate",
                         f"slug không hợp lệ: {slug!r} (chữ thường không dấu, số, . _ -)",
                         f"invalid slug: {slug!r} (lowercase ASCII, digits, . _ -)"))
    clash = _collision(slug)
    if clash:
        return fail(clash)

    stage_dir = wrap / slug
    raw.replace(stage_dir)

    files, total, sources = [], 0, {}
    for f in sorted(stage_dir.rglob("*")):
        if not f.is_file():
            continue
        rel = str(f.relative_to(stage_dir)).replace("\\", "/")
        size = f.stat().st_size
        total += size
        files.append({"path": rel, "size": size})
        if f.suffix == ".py":
            try:
                sources[rel] = f.read_text(encoding="utf-8", errors="replace")
            except OSError:
                pass

    existing = None
    cur = plugins_host.GLOBAL_DIR / slug
    if cur.is_dir():
        m_old, _ = plugins_host._read_manifest(cur)
        existing = {"version": str((m_old or {}).get("version") or ""),
                    "enabled": bool((m_old or {}).get("enabled"))}
    vdir = plugins_host.vault_plugins_dir(vault_root) if vault_root else None
    vault_shadow = bool(vdir and (vdir / slug).is_dir())

    name = str(manifest.get("name") or slug)
    return {
        "ok": True, "kind": "plugin", "staging_id": sha, "sha256": sha,
        "filename": filename, "size": len(data), "unpacked": total,
        "slug": slug,
        "name": plugins_host._theo_ngon_ngu(manifest, "name", name),
        "description": plugins_host._theo_ngon_ngu(manifest, "description",
                                                   str(manifest.get("description") or "")),
        "version": str(manifest.get("version") or ""),
        "author": str(manifest.get("author") or ""),
        "tools": declared_tools(manifest, sources),
        "hooks": [str(h) for h in (manifest.get("hooks") or []) if isinstance(h, str)],
        "files": files[:FILES_SHOWN], "file_count": len(files),
        "py_files": sorted(sources),
        "enabled_in_zip": bool(manifest.get("enabled")),
        "existing": existing, "vault_shadow": vault_shadow,
        "user_gate": plugins_host._env_user_enabled(),
        "target": str(plugins_host.GLOBAL_DIR / slug),
    }


def install(staging_id: str, consent_sha256: str, *, replace: bool = False) -> dict:
    """Move the inspected plugin into the GLOBAL user plugin folder, switched OFF."""
    sha = str(staging_id or "").strip()
    wrap = STAGING / sha
    if not sha or not wrap.is_dir() or STAGING.resolve() not in wrap.resolve().parents:
        return _err("commit", "bản soi đã hết hạn, hãy chọn lại tệp",
                    "the preview has expired, please choose the file again")
    if not consent_sha256 or consent_sha256 != sha:
        return _err("commit", "nội dung tệp đã đổi so với lúc xem, hãy xem lại",
                    "the file changed since you previewed it, please review it again")
    kids = [d for d in wrap.iterdir() if d.is_dir()]
    if len(kids) != 1:
        return _err("commit", "bản soi hỏng, hãy chọn lại tệp",
                    "the preview is broken, please choose the file again")
    src, slug = kids[0], kids[0].name
    # Re-check everything inspect() checked: the bundled/pack sets can change in between.
    if not plugins_host.valid_slug(slug):
        return _err("commit", "slug không hợp lệ", "invalid slug")
    clash = _collision(slug) or _check_tree(src)
    if clash:
        return clash
    mf = _manifest_file(src)
    if mf is None or _entry(src) is None:
        return _err("validate", "thiếu plugin.yaml hoặc plugin.py", "plugin.yaml or plugin.py is missing")
    manifest, e = _read_manifest(mf)
    if e:
        return e

    dest = plugins_host.GLOBAL_DIR / slug
    existed = dest.exists()
    if existed and not replace:
        return _err("commit",
                    f"Đã có plugin '{slug}'. Bật 'Thay bản đang có' để thay nó.",
                    f"A plugin named '{slug}' is already installed. Turn on 'Replace the installed version' to replace it.",
                    code="exists")

    # Forced OFF, whatever the zip said. Same writer as the on/off switch (set_enabled).
    manifest["enabled"] = False
    manifest["slug"] = slug
    try:
        mf.write_text(yaml.safe_dump(manifest, allow_unicode=True, sort_keys=False), encoding="utf-8")
    except Exception as ex:      # noqa: BLE001
        return _err("commit", f"ghi plugin.yaml lỗi: {ex}", f"could not write plugin.yaml: {ex}")

    plugins_host.GLOBAL_DIR.mkdir(parents=True, exist_ok=True)
    trash = plugins_host.GLOBAL_DIR.parent / f".plugin-trash-{slug}-{int(time.time())}"
    moved = False
    try:
        if existed:
            # Stop the running copy first (on_unload, sys.modules), then swap folders.
            plugins_host.unload(slug)
            dest.replace(trash)
            moved = True
        shutil.move(str(src), str(dest))
    except Exception as ex:      # noqa: BLE001
        if moved and not dest.exists():
            try:
                trash.replace(dest)
            except OSError:
                pass
        return {"ok": False, "stage": "commit", "error": f"{type(ex).__name__}: {ex}"}
    finally:
        if moved and trash.exists() and dest.exists():
            shutil.rmtree(trash, ignore_errors=True)
    shutil.rmtree(wrap, ignore_errors=True)
    plugins_host.invalidate()
    gated = not plugins_host._env_user_enabled()
    return {"ok": True, "slug": slug, "enabled": False, "replaced": existed,
            "user_gate": not gated, "dir": str(dest)}
