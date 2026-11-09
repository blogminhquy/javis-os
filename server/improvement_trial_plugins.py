"""Read-only plugin capability inputs for an ordinary owner dashboard profile.

This component observes the real prewarmed host cache; it never loads a plugin,
calls visibility/registration hooks, reads settings, or writes canonical state.
Installed packs are explicitly unsupported until their complete catalog and trust
dependencies have a verified read-only projector. This is not a complete prompt.
"""
from __future__ import annotations

import contextvars
import hashlib
import inspect
import json
import os
import re
import stat
import sys
import threading
import types
from pathlib import Path

import yaml

from improvement_store import _hash
from improvement_trial_context import ContextSource, _check_path, _read, _root

MAX_PLUGIN_FILES = 512
MAX_PLUGIN_BYTES = 8 * 1024 * 1024
MAX_PLUGIN_ENTRIES = 2048
MAX_PLUGIN_RUNTIME_BYTES = 1024 * 1024
_SLUG = re.compile(r"[a-z0-9][a-z0-9._-]{0,63}\Z")
_TOOL = re.compile(r"[a-z][a-z0-9_]{0,63}\Z")
_LOCK_TYPES = (type(threading.Lock()), type(threading.RLock()))
_SESSION_FIELDS = {"id", "brain", "channel", "engine", "model", "project_id", "pinned_provider", "pinned_model", "archived"}
_RESERVED = {"javis_connections", "javis_read_file", "javis_list_dir", "javis_write_file", "javis_use_skill",
    "javis_edit_file", "javis_search_files", "javis_run_command", "javis_terminal", "javis_process",
    "javis_web_search", "javis_web_fetch"}
_GOAL_FILE = Path(__file__).resolve().parent.parent / "system" / "plugins" / "javis-goal" / "plugin.py"
# Pin the audited data-only branch; a coherent edited source+cache is still not
# authority to reinterpret an arbitrary predicate as the ordinary-owner result.
# Re-pinned 2026-11-09 after an audit of the diff: the plugin opens the store with `RS.shared()` instead of
# `RS.GoalStore()` (one opened store per file); `_visible`'s branches and what they return are unchanged.
_GOAL_SOURCE_HASH = "cf2eb26b4198cadcd067aa036a1aa129b6db4e1456098fdb34014542c858406e"


def _plain(value):
    """A bounded JSON snapshot, without invoking custom serialization methods."""
    def clean(item, depth=0):
        if depth > 40:
            raise ValueError("unsupported_plugin_runtime")
        if item is None or type(item) in (str, bool, int):
            return item
        if type(item) is float:
            import math
            if math.isfinite(item):
                return item
        if type(item) in (list, tuple):
            return [clean(child, depth + 1) for child in item]
        if type(item) is dict and all(type(key) is str for key in item):
            return {key: clean(child, depth + 1) for key, child in item.items()}
        raise ValueError("unsupported_plugin_runtime")
    result = clean(value)
    if len(json.dumps(result, ensure_ascii=False, allow_nan=False).encode("utf-8")) > MAX_PLUGIN_RUNTIME_BYTES:
        raise ValueError("insufficient_source: plugin_projection_too_large")
    return result


def _mapping(text, *, yaml_manifest=False):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate_plugin_member")
            result[key] = value
        return result
    try:
        if yaml_manifest:
            if any(isinstance(token, yaml.tokens.AliasToken) for token in yaml.scan(text, Loader=yaml.SafeLoader)):
                raise ValueError("plugin_yaml_alias_unsupported")
            class StrictLoader(yaml.SafeLoader):
                pass
            def mapping(loader, node):
                return pairs([(loader.construct_object(key, deep=True), loader.construct_object(value, deep=True))
                              for key, value in node.value])
            StrictLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, mapping)
            value = yaml.load(text, Loader=StrictLoader)
            value = {} if value is None else value
        else:
            value = json.loads(text, object_pairs_hook=pairs,
                               parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite")))
        if type(value) is not dict:
            raise ValueError("mapping_required")
        return _plain(value)
    except (TypeError, ValueError, yaml.YAMLError, RecursionError) as error:
        raise ValueError("insufficient_source: invalid_plugin_metadata") from error


def _identity(info):
    return _hash({"dev": info.st_dev, "ino": info.st_ino, "ctime_ns": info.st_ctime_ns})


class _Observation:
    def __init__(self):
        self.files = []
        self.directories = []
        self.raw = {}
        self.bytes = 0

    def directory(self, root, relative):
        if len(self.directories) >= MAX_PLUGIN_ENTRIES or len(Path(relative).parts) > 32:
            raise ValueError("insufficient_source: plugin_directory_too_large")
        path = root / relative
        _check_path(path)
        try:
            before = path.stat()
        except FileNotFoundError:
            self.directories.append({"root": str(root), "relative": relative, "present": False,
                                     "identity": None, "entries": []})
            return None
        if not stat.S_ISDIR(before.st_mode):
            raise ValueError("insufficient_source: plugin_not_directory")
        members = sorted(path.iterdir())
        if len(members) > MAX_PLUGIN_ENTRIES:
            raise ValueError("insufficient_source: plugin_directory_too_large")
        entries, names = [], set()
        for member in members:
            _check_path(member)
            info = member.lstat()
            if member.name.casefold() in names:
                raise ValueError("insufficient_source: ambiguous_plugin_member")
            names.add(member.name.casefold())
            kind = "directory" if stat.S_ISDIR(info.st_mode) else "file" if stat.S_ISREG(info.st_mode) else "other"
            if kind == "other":
                raise ValueError("insufficient_source: unsupported_plugin_member")
            entries.append({"name": member.name, "kind": kind})
        after = path.stat()
        _check_path(path)
        if (_identity(before), before.st_mtime_ns) != (_identity(after), after.st_mtime_ns):
            raise ValueError("insufficient_source: plugin_sources_changed")
        self.directories.append({"root": str(root), "relative": relative, "present": True,
                                 "identity": _identity(before), "entries": entries})
        return entries

    def read(self, root, relative, *, required=False):
        key = str(root / relative)
        if key in self.raw:
            return self.raw[key]
        if len(self.files) >= MAX_PLUGIN_FILES:
            raise ValueError("insufficient_source: plugin_sources_too_large")
        path = root / relative
        _check_path(path)
        try:
            if path.stat().st_nlink != 1:
                raise ValueError("insufficient_source: linked_plugin_source")
        except FileNotFoundError:
            pass
        record, text = _read(ContextSource("plugin:" + key, root, relative, required))
        self.bytes += len(text.encode("utf-8")) if text is not None else 0
        if self.bytes > MAX_PLUGIN_BYTES:
            raise ValueError("insufficient_source: plugin_sources_too_large")
        self.files.append(record)
        self.raw[key] = text
        return text

    def tree(self, root, relative):
        for item in self.directory(root, relative) or []:
            child = (Path(relative) / item["name"]).as_posix()
            if item["kind"] == "directory":
                # Python's own bytecode cache is not a source dependency. Never read it.
                if item["name"] != "__pycache__":
                    self.tree(root, child)
            elif item["name"].endswith((".py", ".yaml", ".yml", ".json")):
                self.read(root, child, required=True)


def _codes(code):
    yield code
    for constant in code.co_consts:
        if isinstance(constant, types.CodeType):
            yield from _codes(constant)


class PluginCapabilityProjection:
    """Host-owned dependencies only. No client JSON may construct this collector."""
    def __init__(self, *, host, packs_host, redactor):
        for module, name in ((host, "plugins_host"), (packs_host, "packs")):
            if (type(module) is not types.ModuleType or sys.modules.get(name) is not module
                    or Path(module.__file__).resolve() != Path(__file__).parent / (name + ".py")):
                raise TypeError("actual_plugin_host_required")
        if not isinstance(host._lock, _LOCK_TYPES) or not isinstance(packs_host._lock, _LOCK_TYPES):
            raise TypeError("actual_plugin_host_lock_required")
        if not callable(redactor) or inspect.iscoroutinefunction(redactor):
            raise TypeError("synchronous_plugin_redactor_required")
        self.host, self.packs, self.redactor = host, packs_host, redactor

    def capture(self, brain_root: Path, *, observed_session: dict, settings_ui: dict) -> dict:
        try:
            root = _root(brain_root)
            if root != brain_root:
                raise ValueError("insufficient_source: plugin_root_changed")
            if (type(observed_session) is not dict or set(observed_session) != _SESSION_FIELDS
                    or observed_session["brain"] != str(root) or observed_session["channel"] != "web"
                    or type(observed_session["archived"]) is not int or observed_session["archived"] != 0
                    or not isinstance(observed_session["id"], str) or not observed_session["id"]):
                raise ValueError("unsupported_plugin_surface")
            if (type(settings_ui) is not dict or set(settings_ui) != {"ui_lang"}
                    or type(settings_ui["ui_lang"]) is not str or len(settings_ui["ui_lang"]) > 50):
                raise ValueError("invalid_plugin_ui_projection")
            with self.host._lock, self.packs._lock:
                first = self._scan(root, observed_session, settings_ui)
                if self._scan(root, observed_session, settings_ui) != first:
                    raise ValueError("insufficient_source: plugin_sources_changed")
                safe = self.redactor(_plain(first))
                if safe != first:
                    raise ValueError("insufficient_source: credential_bearing_plugin_projection")
                return first
        except (OSError, RuntimeError) as error:
            raise ValueError("insufficient_source: plugin_sources_unavailable") from error

    __call__ = capture

    def _scan(self, root, session, settings_ui):
        host, packs = self.host, self.packs
        turn = sys.modules.get("turn_context")
        if type(turn) is not types.ModuleType or not isinstance(turn._CURRENT, contextvars.ContextVar):
            raise ValueError("unsupported_plugin_surface")
        binding = turn._CURRENT.get()
        if binding is not None:
            actual = binding.turn
            if (type(binding) is not turn._Binding or binding.alive is not True or type(actual) is not dict
                    or actual.get("kenh") != "dashboard" or actual.get("la_chu") is not True
                    or actual.get("agent") is not None or actual.get("session_id") != session["id"]
                    or actual.get("job") or actual.get("team_gate")):
                raise ValueError("unsupported_plugin_surface")
        observation = _Observation()
        server_root = Path(__file__).resolve().parent
        for filename in ("plugins_host.py", "packs.py", "localefmt.py", "lang_registry.py", "turn_context.py"):
            observation.read(server_root, filename, required=True)
        bundled, global_dir = Path(host.BUNDLED_DIR), Path(host.GLOBAL_DIR)
        state_path, pack_dir, ledger_path = Path(host._STATE_PATH), Path(packs.PACKS_DIR), Path(packs.LEDGER)
        for path in (bundled.parent, global_dir.parent, state_path.parent, pack_dir.parent, ledger_path.parent):
            if _root(path) != path:
                raise ValueError("insufficient_source: plugin_root_changed")
        state_raw = observation.read(state_path.parent, state_path.name)
        state = _mapping(state_raw) if state_raw is not None else {}
        if set(state) - {"enabled", "disabled", "removed"}:
            raise ValueError("unsupported_plugin_state")
        for key, value in state.items():
            if type(value) is not list or any(type(slug) is not str or not _SLUG.fullmatch(slug) for slug in value):
                raise ValueError("insufficient_source: invalid_plugin_state")
        ledger_raw = observation.read(ledger_path.parent, ledger_path.name)
        pack_members = observation.directory(pack_dir.parent, pack_dir.name)
        # Exact acceptance of packs also depends on the core connector catalog,
        # core-off state, compatibility and code-consent ledger. Never approximate it.
        if (any(item["kind"] == "directory" and not item["name"].startswith((".", "_")) for item in pack_members or [])
                or packs._cache.get("packs") or packs._cache.get("connectors") or (ledger_raw and _mapping(ledger_raw))):
            raise ValueError("unsupported_pack_context")
        pack_off = str(os.getenv("JAVIS_DISABLE_PACKS", "")).strip().lower() in ("1", "true", "yes", "on")
        if pack_off:
            pack_signature = "off"
        elif pack_members is None:
            pack_signature = None
        else:
            info = pack_dir.stat()
            pack_signature = [(info.st_mtime_ns, info.st_size)]
            if ledger_raw is not None:
                info = ledger_path.stat()
                pack_signature.append(("_so", info.st_mtime_ns, info.st_size))
            pack_signature = tuple(pack_signature)
        user_env = [str(os.getenv(key, "") or "").strip().lower() for key in
                    ("JAVIS_ENABLE_USER_PLUGINS", "JAVIS_ENABLE_VAULT_PLUGINS")]
        effective_env = next((value for value in user_env if value), "")
        user_enabled = effective_env not in ("0", "false", "no", "off")
        flat = observation.directory(root, "plugins")
        nested = observation.directory(root, "Javis/plugins")
        layout = "plugins" if flat is not None else "Javis/plugins" if nested is not None else "plugins"
        dirs = {}
        for source, base, members in (("bundled", bundled, observation.directory(bundled.parent, bundled.name)),
                                     ("user", global_dir, observation.directory(global_dir.parent, global_dir.name)),
                                     ("vault", root / layout, flat if layout == "plugins" else nested)):
            for item in members or []:
                if item["kind"] != "directory":
                    continue
                pdir = base / item["name"]
                observation.tree(base.parent, (Path(base.name) / item["name"]).as_posix())
                if any((pdir / entry).is_file() for entry in ("plugin.py", "__init__.py")):
                    dirs[pdir.name] = (source, pdir)
        signature = [user_enabled, state_path.stat().st_mtime if state_raw is not None else 0, pack_signature]
        manifests, descriptions = {}, []
        registry = sys.modules.get("lang_registry")
        if type(registry) is not types.ModuleType:
            raise ValueError("unsupported_plugin_locale")
        request_language = host.localefmt._UI_YEU_CAU.get()
        if type(request_language) is not str:
            raise ValueError("unsupported_plugin_locale")
        def normalize(value):
            code = value.strip().lower().replace("_", "-").split("-")[0]
            return code if code in registry.LANGS else ""
        language = request_language or normalize(settings_ui["ui_lang"]) or registry.MAC_DINH
        if language not in registry.LANGS:
            raise ValueError("unsupported_plugin_locale")
        cache = host._cache.get(f"{root}|True")
        if type(cache) is not dict:
            raise ValueError("insufficient_source: plugin_runtime_unavailable")
        errors = _plain(cache.get("errors") or {})
        if type(errors) is not dict or errors:
            # Loader errors can contain arbitrary exception/private runtime text.
            raise ValueError("unsupported_plugin_runtime_errors")
        def localized(manifest, key, original):
            if language == registry.MAC_DINH:
                return original
            for code in (language, registry.DU_PHONG_GIAO_DIEN):
                value = manifest.get(key + "_" + code)
                if isinstance(value, str) and value.strip():
                    return value.strip()
            return original
        for slug, (source, pdir) in dirs.items():
            if not _SLUG.fullmatch(slug):
                raise ValueError("unsupported_plugin_slug")
            for name in ("plugin.yaml", "plugin.yml", "plugin.py", "__init__.py"):
                file = pdir / name
                observation.read(pdir, name)
                if file.is_file():
                    info = file.stat()
                    signature.append((source, slug, name, info.st_mtime, info.st_size))
            file = pdir / "plugin.yaml"
            if not file.is_file():
                file = pdir / "plugin.yml"
            text = observation.raw.get(str(file))
            manifest = _mapping(text, yaml_manifest=True) if text is not None else {}
            # Production manifest/state caches can be stale even at equal mtime/size.
            hit = host._MANIFEST_CACHE.get(str(file))
            if hit is not None and (hit.get("manifest") != manifest or hit.get("err")):
                raise ValueError("insufficient_source: plugin_runtime_stale")
            for key in ("name", "description", "author", "min_mode"):
                if key in manifest and type(manifest[key]) is not str:
                    raise ValueError("unsupported_plugin_manifest")
            for key in ("tools", "hooks"):
                value = manifest.get(key) or []
                if type(value) is not list or any(type(name) is not str for name in value):
                    raise ValueError("unsupported_plugin_manifest")
            removed = slug in state.get("removed", [])
            want = bool(manifest.get("enabled", False)) and not removed
            if source == "bundled" and not removed:
                if slug in state.get("disabled", []):
                    want = False
                elif slug in state.get("enabled", []):
                    want = True
            loaded = want and (user_enabled or source == "bundled")
            manifests[slug] = (manifest, source, pdir, loaded)
            descriptions.append({"slug": slug, "name": localized(manifest, "name", manifest.get("name") or slug),
                "source": source, "description": localized(manifest, "description", manifest.get("description", "")),
                "enabled": want, "loaded": loaded, "gated": bool(source in ("user", "vault") and want and not user_enabled),
                "min_mode": manifest.get("min_mode", "readonly") if manifest.get("min_mode", "readonly") in
                    ("readonly", "safe", "full") else "readonly", "tools": manifest.get("tools") or [],
                "hooks": manifest.get("hooks") or [], "error": ""})
        if cache.get("sig") != tuple(signature):
            raise ValueError("insufficient_source: plugin_runtime_stale")
        state_hit = host._STATE_CACHE
        if state_hit.get("data") is not None and state_hit["data"] != state:
            raise ValueError("insufficient_source: plugin_runtime_stale")
        if set(host._RESERVED_TOOLS) != _RESERVED:
            raise ValueError("unsupported_plugin_reserved_tools")
        loaded_plugins = cache.get("plugins")
        expected = [slug for slug, (_, _, _, enabled) in manifests.items() if enabled]
        if (type(loaded_plugins) is not list or any(type(lp) is not host.LoadedPlugin for lp in loaded_plugins)
                or [lp.slug for lp in loaded_plugins] != expected):
            raise ValueError("insufficient_source: plugin_runtime_stale")
        runtime, visible = [], set()
        compiled = {}
        def function(fn, pdir):
            if not isinstance(fn, types.FunctionType):
                raise ValueError("unsupported_plugin_callable")
            path = Path(fn.__code__.co_filename)
            if not path.is_absolute() or not path.is_relative_to(pdir):
                raise ValueError("unsupported_plugin_external_callable")
            text = observation.read(pdir, path.relative_to(pdir).as_posix(), required=True)
            if path not in compiled:
                compiled[path] = list(_codes(compile(text, str(path), "exec", dont_inherit=True)))
            if not any(code == fn.__code__ for code in compiled[path]):
                raise ValueError("insufficient_source: plugin_runtime_code_mismatch")
            closure = [cell.cell_contents for cell in fn.__closure__ or ()]
            # Closures with mutable host/runtime state need a dedicated projector.
            if closure:
                raise ValueError("unsupported_plugin_closure")
            return {"path": str(path), "qualname": fn.__qualname__, "code_hash": _hash({
                        "source_hash": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                        "qualname": fn.__code__.co_qualname, "firstlineno": fn.__code__.co_firstlineno}),
                    "defaults": _plain(fn.__defaults__), "kwdefaults": _plain(fn.__kwdefaults__)}
        for lp in loaded_plugins:
            manifest, source, pdir, _ = manifests[lp.slug]
            if (lp.source != source or type(lp.ctx) is not host.PluginContext or lp.ctx.dir != pdir
                    or lp.ctx.vault_root != str(root) or lp.name != (manifest.get("name") or lp.slug)
                    or lp.description != str(manifest.get("description") or "").strip()
                    or lp.tools is not lp.ctx._tools or type(lp.tools) is not list):
                raise ValueError("insufficient_source: plugin_runtime_source_mismatch")
            modules = []
            for name, module in list(sys.modules.items()):
                if type(module) is not types.ModuleType or not isinstance(module.__dict__.get("__file__"), str):
                    continue
                file = Path(module.__dict__["__file__"])
                if not file.is_absolute() or not file.is_relative_to(pdir):
                    continue
                functions = []
                for key, item in list(module.__dict__.items()):
                    if isinstance(item, types.FunctionType) and item.__module__ == name:
                        functions.append(function(item, pdir))
                    elif isinstance(item, type) and item.__module__ == name:
                        for member in vars(item).values():
                            if isinstance(member, (staticmethod, classmethod)):
                                member = member.__func__
                            if isinstance(member, types.FunctionType):
                                functions.append(function(member, pdir))
                modules.append({"name": name, "path": str(file), "functions": functions})
            tools = []
            for tool in lp.tools:
                if type(tool) is not dict or type(tool.get("name")) is not str or not _TOOL.fullmatch(tool["name"]):
                    raise ValueError("unsupported_plugin_tool")
                scalar = _plain({key: value for key, value in tool.items() if key not in ("handler", "check_fn", "visible_fn")})
                handler = function(tool.get("handler"), pdir)
                checker = function(tool["check_fn"], pdir) if tool.get("check_fn") is not None else None
                vis = tool.get("visible_fn")
                visibility = None
                # Duplicate/reserved tools are skipped BEFORE visibility in production.
                skipped = tool["name"] in _RESERVED or tool["name"] in visible
                if vis is not None and not skipped:
                    visibility = function(vis, pdir)
                    module = sys.modules.get(vis.__module__)
                    if (source != "bundled" or lp.slug != "javis-goal" or pdir / "plugin.py" != _GOAL_FILE
                            or hashlib.sha256(observation.read(pdir, "plugin.py", required=True).encode("utf-8")).hexdigest() != _GOAL_SOURCE_HASH
                            or vis.__name__ != "_visible" or type(module) is not types.ModuleType or vis.__globals__ is not module.__dict__):
                        raise ValueError("unsupported_plugin_visibility")
                    # The verified source's ordinary owner/no-agent branch is false.
                    # No call to GoalStore, agent_gate or this callback is permitted.
                    skipped = True
                if not skipped:
                    visible.add(tool["name"])
                tools.append({"metadata": scalar, "handler": handler, "check": checker,
                              "visibility": visibility, "visible": not skipped})
            runtime.append({"slug": lp.slug, "source": source, "directory": str(pdir), "tools": tools, "modules": modules})
        result = []
        for row in descriptions:
            if row["loaded"] and row["tools"]:
                row["tools"] = [name for name in row["tools"] if name in visible]
                if not row["tools"]:
                    continue
            result.append(row)
        return _plain({"version": 1, "root": str(root), "layout": layout, "plugins": result,
            "visible_tools": sorted(visible), "runtime": {"cache_signature": signature, "plugins": runtime,
                "user_environment": user_env, "pack_disabled": pack_off, "profile": "ordinary-owner-dashboard-no-agent"},
            "locale": {"request_lang": request_language, "settings_ui_lang": settings_ui["ui_lang"], "resolved": language},
            "sources": observation.files, "directories": observation.directories})
