"""Concrete protected context for a closed ordinary owner dashboard profile.

The supported profile is an explicit Claude subscription selection, an ordinary
web SQL session, unassigned adaptive paths, prewarmed provable plugins, and no
unapproved native ambient instructions/settings/auto-memory. Unsupported native,
pack, coding or adaptive sources fail before completeness is asserted. Candidate
and fixture bodies never belong in this shared snapshot. No live prompt builder,
settings decryption, migration, synchronization or native engine starts here.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import stat
import sys
import types
import threading
from collections import OrderedDict
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import improvement_trial_sql_context as SQL
from evidence_store import redact
from improvement_cases import output_path
from improvement_store import _hash
from improvement_trial_catalog import capture_catalog, _directory
from improvement_trial_context import ContextSource, _read, _root, _check_path
from improvement_trial_file_sources import _root as _owner_root, _authority, _acl_hash
from improvement_trial_plugins import PluginCapabilityProjection
from improvement_trial_selection import _read_stable, MAX_SETTINGS_BYTES
from improvement_trial_semantics import capture_semantics, validate_capture

MAX_DASHBOARD_FILES = 800
MAX_NATIVE_RULE_FILES = 100
_TARGET_KEYS = {"id", "generation", "kind", "canonical_ref", "identity", "source_hash", "protected_hash", "ownership"}
_SERVER = Path(__file__).resolve().parent
_COMPILED_CODE_CACHE = OrderedDict()
_COMPILED_CODE_LOCK = threading.RLock()


def _utc_now():
    return datetime.now(timezone.utc)


def _semantic_incarnation(info):
    # ctime is modification/metadata-change time on POSIX, not creation time.
    # Semantic-only projections must survive unrelated writes to the same inode.
    # Stable reads still compare full read stamps, and selected fields are hashed.
    return {"device": info.st_dev, "inode": info.st_ino, "kind": stat.S_IFMT(info.st_mode),
            "birth": getattr(info, "st_birthtime_ns", None), "mode": stat.S_IMODE(info.st_mode),
            "uid": getattr(info, "st_uid", None), "gid": getattr(info, "st_gid", None),
            "attributes": getattr(info, "st_file_attributes", 0)}


def _protected_authority(root, relative):
    authority = _authority(root, relative)
    path = root
    for index, entry in enumerate(authority[:-1]):
        if index:
            path /= relative.split("/")[index - 1]
        info = path.lstat()
        expected = {**entry["incarnation"],
            "birth": entry["incarnation"]["birth"] if hasattr(info, "st_birthtime_ns") else None,
            **{key: entry[key] for key in ("mode", "uid", "gid", "attributes")}}
        observed = _semantic_incarnation(info)
        if observed != expected:
            raise ValueError("dashboard_protected_authority_changed")
        # Keep native ACL, mode/uid/gid/attributes and real directory identity.
        # A sibling SQL journal is not a change to this protected file's authority.
        # The protected file itself retains the original exact incarnation guard.
        entry["incarnation"] = observed
    return authority


def _semantic(kind, ref, locator, projection, *, role="authority", identity=None):
    digest = _hash(projection)
    return {"kind": kind, "ref": ref, "locator": locator, "role": role, "required": True, "present": True,
            "identity": identity or _hash(locator), "hash": digest, "projection": projection, "projection_hash": digest}


class _Sources:
    def __init__(self):
        self.items, self.files = [], {}

    def semantic(self, kind, ref, locator, projection, **kwargs):
        item = _semantic(kind, ref, locator, projection, **kwargs)
        prior = next((source for source in self.items if source["ref"] == ref), None)
        if prior is not None:
            if prior != item:
                raise ValueError("dashboard_source_changed")
            return
        self.items.append(item)

    def file_record(self, record, projection, role="authority"):
        path = str(Path(record["root"]) / record["relative"]).casefold()
        if path in self.files:
            prior = self.files[path]
            if (prior["hash"], prior["identity"], prior["present"]) != (record["hash"], record["identity"], record["present"]):
                raise ValueError("dashboard_source_changed")
            if prior["role"] != role or prior["projection"] != projection:
                if role == "protected" and prior["role"] in ("discovery", "authority"):
                    # Catalog metadata remains independently pinned in the
                    # catalog inventory; the physical file has one stronger
                    # protected record when the owner also pinned its full text.
                    prior.update(role=role, projection=projection, projection_hash=_hash(projection),
                                 required=record["required"] or prior["required"])
                else:
                    raise ValueError("unsupported_dashboard_source_overlap")
            return
        if len(self.files) >= MAX_DASHBOARD_FILES:
            raise ValueError("insufficient_source: dashboard_sources_too_large")
        item = {"kind": "file", "ref": "dashboard-file:" + _hash(path),
            "locator": {"root": record["root"], "relative": record["relative"]}, "role": role,
            "required": record["required"], "present": record["present"], "identity": record["identity"], "hash": record["hash"],
            "projection": projection if record["present"] else None,
            "projection_hash": _hash(projection) if record["present"] else None}
        self.files[path] = item
        self.items.append(item)

    def read(self, root, relative, *, required=False, protected=False):
        path = root / relative
        _check_path(path)
        try:
            if path.stat().st_nlink != 1:
                raise ValueError("insufficient_source: linked_dashboard_source")
        except FileNotFoundError:
            pass
        authority = _protected_authority(root, relative) if protected and path.exists() else None
        record, text = _read(ContextSource("dashboard:" + relative, root, relative, required))
        if authority is not None:
            if _protected_authority(root, relative) != authority:
                raise ValueError("dashboard_protected_authority_changed")
            self.semantic("inventory", "dashboard:protected-authority:" + _hash(str(path)),
                          {"root": str(root), "relative": relative}, authority)
        projection = text if protected else {"source_hash": record["hash"]}
        self.file_record(record, projection, "protected" if protected else "authority")
        return text

    def directories(self, prefix, records):
        for index, record in enumerate(records):
            self.semantic("inventory", f"{prefix}:directory:{index}",
                {"component": prefix, "index": index, "relative": record["relative"], "root": record.get("root", "")}, record)

    def code(self, filename):
        path = _SERVER / filename
        if path.stat().st_nlink != 1:
            raise ValueError("insufficient_source: linked_dashboard_source")
        digest, _ = _read_stable(path, 8 * MAX_SETTINGS_BYTES, digest=True)
        info = path.stat()
        self.file_record({"root": str(_SERVER), "relative": filename, "required": True, "present": True,
            "identity": _hash({"dev": info.st_dev, "ino": info.st_ino, "ctime_ns": info.st_ctime_ns}), "hash": digest},
            {"source_hash": digest})


def _strict_json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate_dashboard_key")
            result[key] = value
        return result
    def constant(_):
        raise ValueError("nonfinite_dashboard_json")
    try:
        value = json.loads(raw, object_pairs_hook=pairs, parse_constant=constant)
        if type(value) is not dict:
            raise ValueError("dashboard_mapping_required")
        return value
    except (TypeError, ValueError, RecursionError):
        raise ValueError("insufficient_source: invalid_dashboard_json") from None


def _settings_projection(settings):
    if type(settings) is not dict:
        raise ValueError("insufficient_source: dashboard_settings_missing")
    model, locale, runtime = settings.get("model"), settings.get("locale"), settings.get("context_runtime")
    if any(type(value) is not dict for value in (model, locale, runtime)):
        raise ValueError("insufficient_source: dashboard_settings_missing")
    main = model.get("main")
    if (type(main) is not dict or set(main) != {"provider", "model"} or main.get("provider") != "anthropic-cli"
            or type(main.get("model")) is not str or not main["model"].strip()):
        raise ValueError("unsupported_dashboard_selection")
    if (model.get("claude_auth") != "subscription" or model.get("fast") is not False
            or model.get("reasoning") not in ("low", "medium", "high", "xhigh", "max")):
        raise ValueError("unsupported_dashboard_selection")
    if (any(type(locale.get(key)) is not str for key in ("ui_lang", "reply_lang", "tz"))
            or any(len(locale[key]) > 100 for key in ("ui_lang", "reply_lang", "tz"))):
        raise ValueError("insufficient_source: dashboard_locale_missing")
    choice = runtime.get("preset_choice")
    if (runtime.get("mode") not in ("off", "observe", "shadow") or type(choice) is not dict
            or choice.get("source") != "user"):
        raise ValueError("unsupported_dashboard_adaptive_context")
    # These modes never assign FeaturePolicy or Fast Path, regardless of allocations.
    return {"selection": {"provider": main["provider"], "model": main["model"], "auth_mode": model["claude_auth"],
                "reasoning": model["reasoning"], "fast": False},
            "locale": {key: locale[key] for key in ("ui_lang", "reply_lang", "tz")},
            "runtime": {"mode": runtime["mode"], "preset_choice": {"source": "user", "level": choice.get("level", "")}}}


def _clock(now, language, zone_name, registry):
    local = now.astimezone(ZoneInfo(zone_name))
    minutes = int(local.utcoffset().total_seconds() // 60)
    hours, remainder = divmod(abs(minutes), 60)
    offset = f"UTC{'+' if minutes >= 0 else '-'}{hours}" + (f":{remainder:02}" if remainder else "")
    lang = registry.get(language)
    return lang.clock_template.format(hm=f"{local:%H:%M}", weekday=lang.weekdays[local.weekday()] if lang.weekdays else "",
                                      date=f"{local:%d/%m/%Y}", tz=f"{zone_name} ({offset})")


def _nested_codes(code):
    yield code
    for item in code.co_consts:
        if isinstance(item, types.CodeType):
            yield from _nested_codes(item)


def _compiled_codes(raw, filename):
    """Cache pure compilation only; callers must freshly stable-read the source."""
    digest = hashlib.sha256(raw).hexdigest()
    with _COMPILED_CODE_LOCK:
        saved = _COMPILED_CODE_CACHE.get(filename)
        if saved is not None and saved[0] == digest:
            _COMPILED_CODE_CACHE.move_to_end(filename)
            return saved[1]
        codes = tuple(_nested_codes(compile(raw, filename, "exec", dont_inherit=True)))
        _COMPILED_CODE_CACHE[filename] = (digest, codes)
        _COMPILED_CODE_CACHE.move_to_end(filename)
        while len(_COMPILED_CODE_CACHE) > 32:
            _COMPILED_CODE_CACHE.popitem(last=False)
        return codes


def _verified_function(function, module, name, compiled, error):
    if (type(module) is not types.ModuleType or sys.modules.get(module.__name__) is not module or type(function) is not types.FunctionType
            or function.__globals__ is not module.__dict__ or function.__name__ != name
            or function.__closure__ or function.__module__ != module.__name__):
        raise ValueError(error)
    # _SERVER is canonical and _read_stable checks this exact path's complete
    # ancestry before compilation. Do not repeatedly resolve the same public
    # source path for each function in a module (especially large main.py).
    path = Path(module.__file__)
    if path != _SERVER / (module.__name__ + ".py") or Path(function.__code__.co_filename) != path:
        raise ValueError(error)
    if path not in compiled:
        raw, _ = _read_stable(path, 8 * MAX_SETTINGS_BYTES)
        try:
            compiled[path] = _compiled_codes(raw, function.__code__.co_filename)
        except (SyntaxError, ValueError, RecursionError):
            raise ValueError(error) from None
    if not any(code == function.__code__ for code in compiled[path]):
        raise ValueError(error)


class DashboardContextCapture:
    def __init__(self, *, host, sql, plugins, project_root: Path, state_root: Path, native_user_root: Path):
        if (type(host) is not types.ModuleType or sys.modules.get("main") is not host
                or Path(host.__file__).resolve() != _SERVER / "main.py"
                or type(sql) is not SQL.SQLiteContextProjection or type(plugins) is not PluginCapabilityProjection
                or plugins.host is not host.plugins_host or plugins.packs is not sys.modules.get("packs")):
            raise TypeError("concrete_dashboard_dependencies_required")
        self.host, self.sql, self.plugins = host, sql, plugins
        self.project_root, self.state_root, self.native_user_root = project_root, state_root, native_user_root

    def __call__(self, owner, surface, targets):
        return self._capture(owner, surface, targets)

    def revalidate(self, owner, surface, targets, *, frozen_capture):
        frozen = validate_capture(frozen_capture)
        if frozen["surface"] != surface or frozen["baseline_context"]["coverage"] != "complete":
            raise ValueError("dashboard_capture_changed")
        records = [record for record in frozen["sources"] if record["ref"] == "dashboard:volatile"]
        if len(records) != 1 or records[0]["kind"] != "runtime" or records[0]["role"] != "volatile":
            raise ValueError("invalid_dashboard_volatile_snapshot")
        result = self._capture(owner, surface, targets, volatile=records[0]["projection"])
        if result != frozen:
            raise ValueError("dashboard_context_changed")
        return result

    def recipe_capture(self, owner, surface, targets, *, frozen_capture):
        """Read current discovery with the original clock, usage and owner rules."""
        frozen = validate_capture(frozen_capture)
        if frozen["surface"] != surface or frozen["baseline_context"]["coverage"] != "complete":
            raise ValueError("dashboard_capture_changed")
        records = [record for record in frozen["sources"] if record["ref"] == "dashboard:volatile"]
        if len(records) != 1:
            raise ValueError("invalid_dashboard_volatile_snapshot")
        volatile = records[0]["projection"]
        if (type(volatile) is not dict or set(volatile) != {"clock_utc", "usage_total"}
                or volatile["usage_total"] is None
                or records[0] != _semantic("runtime", "dashboard:volatile",
                    {"policy": "frozen-clock-and-daily-usage-v1"}, volatile, role="volatile")):
            raise ValueError("invalid_dashboard_volatile_snapshot")
        result = self._capture(owner, surface, targets, volatile=volatile)

        def protected(capture):
            return [record for record in capture["sources"] if record["role"] == "protected"
                    or record["ref"].startswith("dashboard:protected-authority:")]

        if protected(result) != protected(frozen):
            raise ValueError("dashboard_protected_context_changed")
        return result

    def _capture(self, owner, surface, targets, volatile=None):
        try:
            root = _owner_root(owner)
            if (type(surface) is not dict or set(surface) != {"kind", "session_id", "language"}
                    or surface["kind"] != "dashboard" or type(surface["session_id"]) is not str
                    or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,199}", surface["session_id"])
                    or type(surface["language"]) is not str or surface["language"] not in self.host.lang_registry.LANGS):
                raise ValueError("unsupported_dashboard_surface")
            for path in (self.project_root, self.state_root):
                if _root(path) != path:
                    raise ValueError("dashboard_root_changed")
            if (self.host.CLAUDE_MD_PATH != self.project_root / "CLAUDE.md"
                    or self.host.cfgmod.SETTINGS_PATH != self.state_root / "settings.json"
                    or self.host.cfgmod.STATE_DIR != self.state_root
                    or self.host.coding_store.STORE_PATH != self.state_root / "coding.json"
                    or self.host.usage_store._PATH != self.state_root / "usage.json"
                    or self.sql.workflow_db is None):
                raise ValueError("unsupported_dashboard_host_layout")
            if volatile is None:
                now = _utc_now()
                if type(now) is not datetime or now.tzinfo is None or now.utcoffset() is None:
                    raise ValueError("invalid_dashboard_clock")
                volatile = {"clock_utc": now.astimezone(timezone.utc).isoformat(), "usage_total": None}
            else:
                if type(volatile) is not dict or set(volatile) != {"clock_utc", "usage_total"}:
                    raise ValueError("invalid_dashboard_volatile_snapshot")
                volatile = json.loads(json.dumps(volatile, allow_nan=False))
            first = self._scan(owner, root, surface, targets, volatile)
            frozen_volatile = next(record["projection"] for record in first["sources"] if record["ref"] == "dashboard:volatile")
            if self._scan(owner, root, surface, targets, frozen_volatile) != first:
                raise ValueError("dashboard_sources_changed_during_capture")
            if _owner_root(owner) != root:
                raise ValueError("dashboard_root_changed")
            return first
        except SQL._ScopeError:
            raise
        except (OSError, RuntimeError, UnicodeError, ZoneInfoNotFoundError) as error:
            raise ValueError("insufficient_source: dashboard_source_unavailable") from error

    def _sql_capture(self, owner, surface):
        # Resolve the *stored* membership via the same bounded SELECT-only native
        # source facade, then let full capture recheck owner/channel/project.
        source = self.sql.existing_sources.get(self.sql.session_db)
        if type(source) is not SQL.ExistingSQLiteSource:
            raise ValueError("sql_context_lifetime_required")
        with source.lock, SQL._existing_reader(source) as reader:
            row = SQL._one(reader, f"SELECT {','.join(SQL._SESSION_FIELDS)} FROM main.sessions WHERE id=? LIMIT 2", (surface["session_id"],))
            project = row["project_id"] or ""
        return self.sql.capture(owner, surface["session_id"], project)

    def _settings(self, sources):
        path = self.state_root / "settings.json"
        raw, _ = _read_stable(path, MAX_SETTINGS_BYTES)
        settings = _strict_json(raw.decode("utf-8"))
        projected = _settings_projection(settings)
        del settings, raw
        # The ordinary config cache is authoritative while its stat key matches.
        cache = self.host.cfgmod._SETTINGS_CACHE
        info = path.stat()
        if cache.get("sig") == (info.st_mtime_ns, info.st_size) and cache.get("cfg") is not None:
            if _settings_projection(_strict_json(cache["cfg"])) != projected:
                raise ValueError("dashboard_runtime_config_stale")
        sources.semantic("inventory", "dashboard:settings", {"source": str(path), "fields": "dashboard-nonsecret-v1"}, projected,
            identity=_hash({"file": _semantic_incarnation(info), "acl_hash": _acl_hash(path)}))
        return projected

    def _runtime(self, sources, language):
        host, compiled = self.host, {}
        # These ordinary entrypoints/source collectors are *verified*, never
        # invoked. Their loaded implementations must still match the concrete
        # app path for which this separate read-only collector preserves parity.
        # This is a closed dependency list, not arbitrary Python attestation.
        groups = ((host, ("build_system_prompt", "_project_block", "_session_block", "_liet_ke_tai_lieu",
            "_javis_core_block", "_gather_capabilities", "_javis_capability_summary", "_skill_router_block",
            "_dong_lan_chay_gan_nhat", "_brain_memory_dir", "_thu_muc_bo_nho", "_brain_root", "_brain_sub",
            "_agents_dir", "_workflows_dir", "_skills_dir", "_resonance_turn_enabled", "_khoi_coding",
            "_safe_serve_path", "_files_root", "_files_ceiling", "_javis_port")),
            (host.memory_control, ("profile_block", "read_profile", "_profile_path", "learning_enabled")),
            (host.coding_store, ("_load", "cwd_cua_phien", "pinned_folder_prompt")),
            (host.plugins_host, ("describe", "plugin_tools", "_load_all", "_iter_plugin_dirs", "_read_manifest", "_effective_enabled", "_theo_ngon_ngu")),
            (host.skill_router, ("list_skills", "list_enabled_meta", "cat_theo_ngan_sach", "xep_theo_uu_tien", "skills_base", "theo_ngon_ngu")),
            (host.cfgmod, ("read_settings",)),
            (host.localefmt, ("ten_tz", "now", "_cau_hinh")),
            (host.context_compiler, ("dong_ho", "_nhan_mui_gio", "_bay_gio")),
            (host.main_prompt_rendering, ("render_profile_block", "render_memory_block", "render_project_instructions",
            "render_agentic_paths", "render_capability_summary", "render_skill_router", "render_clock_language", "render_usage_block")),
            (host.main_attachment_rendering, ("render_attachment_lists", "render_project_assets", "render_session_assets")),
            (host.channel_context, ("build_channel_block",)), (host.lang_mod, ("khoi_ngon_ngu",)),
            (host.lang_registry, ("get",)), (host.system_sync, ("_mirror_signature", "ensure_synced", "mirror_skills")),
            (host.usage_store, ("_rollup", "summary", "_load", "_today")))
        for module, names in groups:
            for name in names:
                _verified_function(getattr(module, name, None), module, name, compiled, "unsupported_dashboard_runtime_renderer")
        _verified_function(host.get_store, host.sessions, "get_store", compiled, "unsupported_dashboard_runtime_renderer")
        if (host.lang_mod.lang_registry is not host.lang_registry or host.main_attachment_rendering.os is not os
                or host.channel_context.json is not json):
            raise ValueError("unsupported_dashboard_runtime_renderer")
        runtime = host._CONTEXT_RUNTIME
        if type(runtime) is not host.context_runtime.ObserveRuntime or type(host._FAST_PATH) is not host.fast_path_runtime.FastPathCanary:
            raise ValueError("unsupported_dashboard_runtime_reader")
        _verified_function(runtime._settings_reader, host.cfgmod, "read_settings", compiled, "unsupported_dashboard_runtime_reader")
        _verified_function(host._FAST_PATH.settings_reader, host.cfgmod, "read_settings", compiled, "unsupported_dashboard_runtime_reader")
        if host._FAST_PATH.runtime is not runtime:
            raise ValueError("unsupported_dashboard_runtime_reader")
        if host._ADAPTIVE_CONTEXT is not None:
            if (type(host._ADAPTIVE_CONTEXT) is not host.adaptive_context_runtime.AdaptiveContextCanary
                    or host._ADAPTIVE_CONTEXT.runtime is not runtime):
                raise ValueError("unsupported_dashboard_runtime_reader")
            _verified_function(host._ADAPTIVE_CONTEXT.settings_reader, host.cfgmod, "read_settings", compiled, "unsupported_dashboard_runtime_reader")
        import improvement_claude
        _verified_function(improvement_claude._managed_policy, improvement_claude, "_managed_policy", compiled, "unsupported_dashboard_runtime_renderer")
        lang = host.lang_registry.get(language)
        sources.semantic("inventory", "dashboard:rendering-runtime", {"profile": "verified-dashboard-renderers-v1"},
            {"language": {key: getattr(lang, key) for key in ("code", "clock_template", "weekdays", "lang_directive", "nudge")},
             "memory_cap": host.MEMORY_INDEX_MAX, "project_instructions_max": host.sessions.PROJECT_INSTRUCTIONS_MAX,
             "project_files_max": host.PROJECT_FILES_LIET_KE, "project_file_max": host.PROJECT_GHIM_FILE_MAX,
             "project_total_max": host.PROJECT_GHIM_TONG_MAX, "attachment_suffixes": sorted(host.PROJECT_GHIM_DUOI),
             "skill_description_max": host.skill_router.SKILL_DESC_MAX,
             "skill_list_max": host.skill_router.SKILL_LIST_MAX, "skill_char_budget": host.skill_router.SKILL_LIST_CHAR_BUDGET})

    def _native(self, root, sources):
        expected = Path.home() / ".claude"
        if os.environ.get("CLAUDE_CONFIG_DIR") or not expected.is_absolute() or expected != self.native_user_root:
            raise ValueError("unsupported_native_ambient_root")
        _check_path(expected)
        # No global instruction/settings contents, auth or foreign transcripts are
        # read. Presence itself is unsupported, never interpreted as permission.
        # Native discovery has its own sources in addition to Javis catalogs.
        # Presence is unsupported even if a cache currently calls it disabled:
        # capture cannot run its loader or inspect potentially private contents.
        discovery = ("skills", "agents", "plugins", "commands", "output-styles")
        probes = [(expected / name) for name in ("CLAUDE.md", "rules", "settings.json", "settings.local.json", "remote-settings.json", "projects", *discovery)]
        for ancestor in root.parents:
            probes.extend(ancestor / relative for relative in ("CLAUDE.md", "CLAUDE.local.md", ".claude/CLAUDE.md", ".claude/rules",
                                                               ".claude/settings.json", ".claude/settings.local.json", ".mcp.json"))
            probes.extend(ancestor / ".claude" / name for name in discovery)
        probes.extend(root / relative for relative in (".claude/settings.json", ".claude/settings.local.json", ".mcp.json"))
        # Brain .claude/skills is explicitly captured by the canonical/mirror
        # catalog. Other native discovery roots have no verified projector here.
        probes.extend(root / ".claude" / name for name in discovery if name != "skills")
        managed_roots = {"win32": Path(r"C:\Program Files\ClaudeCode"), "linux": Path("/etc/claude-code"),
                         "darwin": Path("/Library/Application Support/ClaudeCode")}
        if sys.platform not in managed_roots:
            raise ValueError("unsupported_native_ambient_policy")
        probes.append(managed_roots[sys.platform] / "CLAUDE.md")
        observations = []
        for path in probes:
            if path == self.project_root / "CLAUDE.md":
                continue
            _check_path(path)
            try:
                path.lstat()
            except FileNotFoundError:
                observations.append({"path": str(path), "present": False})
                continue
            raise ValueError("unsupported_native_ambient_context")
        import improvement_claude
        policy = improvement_claude._managed_policy()
        if policy != "absent":
            raise ValueError("unsupported_native_ambient_policy")
        sources.semantic("inventory", "dashboard:native-ambient", {"profile": "native-owner-absence-v1"},
            {"user_root": str(expected), "probes": observations, "managed_policy": policy})

    def _scan(self, owner, root, surface, targets, volatile):
        host, sources = self.host, _Sources()
        settings = self._settings(sources)
        locale, selection = settings["locale"], settings["selection"]
        language = surface["language"]
        self._runtime(sources, language)
        if locale["reply_lang"] != "auto" and locale["reply_lang"] != language:
            raise ValueError("unsupported_dashboard_language")
        ZoneInfo(locale["tz"])
        if not locale["tz"]:
            raise ValueError("insufficient_source: dashboard_timezone_missing")
        serving = os.environ.get("JAVIS_FILES_ROOT", "").strip().lower()
        if serving not in ("brain", "vault"):
            raise ValueError("unsupported_dashboard_serving_ceiling")
        sync = host.system_sync
        if (type(sync._SYNCED_ROOTS) is not set or str(root) not in sync._SYNCED_ROOTS
                or type(sync._MIRROR_SIG) is not dict or type(sync._MIRROR_RETRY) is not dict
                or sync._MIRROR_RETRY.get(str(root))
                or sync._MIRROR_SIG.get(str(root)) != sync._mirror_signature(root / "skills")):
            raise ValueError("unsupported_dashboard_unwarmed_sync")
        sources.semantic("inventory", "dashboard:system-sync", {"root": str(root), "component": "prewarmed-system-sync"},
            {"synced": True, "mirror_signature": sync._MIRROR_SIG.get(str(root)), "serving_ceiling": serving})
        sql = self._sql_capture(owner, surface)
        session = sql["session"]
        if (session["pinned_provider"] and (session["pinned_provider"] != selection["provider"]
                or (session["pinned_model"] or "") != selection["model"])):
            raise ValueError("unsupported_dashboard_pinned_model")
        pin_limits = host._PIN_LIMITED
        if type(pin_limits) is not dict or any(type(value) not in (int, float) or not math.isfinite(value) for value in pin_limits.values()):
            raise ValueError("unsupported_dashboard_selection_runtime")
        # Time-sensitive provider fallback is not one of the two frozen values.
        if session["pinned_provider"] and pin_limits.get(session["pinned_provider"], 0):
            raise ValueError("unsupported_dashboard_pinned_model")
        definitions = [provider for provider in host.PROVIDER_DEFS if provider.get("id") == selection["provider"]]
        if len(definitions) != 1 or definitions[0].get("kind") != "cli":
            raise ValueError("unsupported_dashboard_selection_runtime")
        sources.semantic("sql", "dashboard:sql", {"sessions": str(self.sql.session_db), "workflow": str(self.sql.workflow_db)}, sql)
        project = sql["project"]
        if project is not None:
            sources.semantic("sql", "dashboard:project-instructions", {"database": str(self.sql.session_db), "table": "projects",
                "id": project["id"], "field": "instructions"}, project["instructions"] or "", role="protected")
        self._native(root, sources)
        coding_path = self.state_root / "coding.json"
        _check_path(coding_path)
        try:
            coding_info = coding_path.lstat()
        except FileNotFoundError:
            coding_info = None
        coding_raw = _read_stable(coding_path, MAX_SETTINGS_BYTES)[0].decode("utf-8") if coding_info is not None else None
        if coding_raw is not None:
            coding = _strict_json(coding_raw)
            if (set(coding) != {"version", "thu_muc", "phien"} or coding.get("version") != 2
                    or type(coding.get("thu_muc")) is not list or type(coding.get("phien")) is not dict):
                raise ValueError("unsupported_dashboard_coding_registry")
            if surface["session_id"] in coding["phien"]:
                raise ValueError("unsupported_dashboard_coding_binding")
            # Only selected-session absence is semantic; do not retain other brains.
        sources.semantic("inventory", "dashboard:coding-binding", {"source": str(coding_path), "session_id": surface["session_id"]},
            {"registry_present": coding_raw is not None, "version": 2 if coding_raw is not None else None, "selected_session_binding": None},
            identity=_hash({"file": _semantic_incarnation(coding_info), "acl_hash": _acl_hash(coding_path)}) if coding_info is not None else None)
        catalog = capture_catalog(root, language=language)
        for item in catalog["files"]:
            sources.file_record(item, item["projection"] or {}, "discovery")
        sources.directories("dashboard-catalog", catalog["directories"])
        sources.semantic("inventory", "dashboard:catalog", {"root": str(root), "component": "agentic-catalog"},
                         {key: catalog[key] for key in ("layout", "capabilities", "router")})
        plugins = self.plugins.capture(root, observed_session=session, settings_ui={"ui_lang": locale["ui_lang"]})
        for record in plugins["sources"]:
            sources.file_record(record, {"source_hash": record["hash"]})
        sources.directories("dashboard-plugins", plugins["directories"])
        sources.semantic("inventory", "dashboard:plugins", {"root": str(root), "component": "plugins"},
            {key: plugins[key] for key in ("layout", "plugins", "visible_tools", "runtime", "locale")})
        if not isinstance(targets, list) or not 1 <= len(targets) <= 20:
            raise ValueError("unsupported_dashboard_targets")
        target_paths = set()
        target_ids = set()
        for target in targets:
            if (type(target) is not dict or set(target) != _TARGET_KEYS or target["kind"] != "skill"
                    or target["ownership"] not in ("user_protected", "user_managed")
                    or type(target["canonical_ref"]) is not str
                    or not re.fullmatch(r"skills/[a-z0-9][a-z0-9_-]{0,127}/SKILL\.md", target["canonical_ref"])
                    or type(target["id"]) is not str or not target["id"] or target["id"] in target_ids
                    or type(target["generation"]) is not int or target["generation"] < 1
                    or any(type(target[key]) is not str or not re.fullmatch(r"[0-9a-f]{64}", target[key])
                           for key in ("identity", "source_hash", "protected_hash"))
                    or target["source_hash"] != target["protected_hash"]):
                raise ValueError("unsupported_dashboard_targets")
            target_ids.add(target["id"])
            relative = output_path(target["canonical_ref"])
            if relative.casefold() in target_paths:
                raise ValueError("unsupported_dashboard_targets")
            target_paths.add(relative.casefold())
            path = root / relative
            record = next((item for item in catalog["files"] if item["relative"].casefold() == relative.casefold()), None)
            if record is None or not record["present"] or record["hash"] != target["source_hash"]:
                raise ValueError("dashboard_target_changed")
            info = path.stat()
            identity = hashlib.sha256(f":{info.st_dev}:{info.st_ino}".encode()).hexdigest()
            if identity != target["identity"] or not (record["projection"] or {}).get("description"):
                raise ValueError("dashboard_target_changed")
        sources.semantic("inventory", "dashboard:targets", {"root": str(root), "component": "mutable-target-metadata"}, targets)
        kernel = sources.read(self.project_root, "CLAUDE.md", required=True, protected=True)
        profile = sources.read(self.state_root, "user_profile.md", protected=True) or ""
        # Select the actual memory spelling by enumerating root membership; never
        # heal/migrate or enumerate facts and conversation history.
        members = []
        _directory(root, ".", members)
        members[0]["entries"] = [entry for entry in members[0]["entries"] if entry["name"].casefold() == "memory"]
        names = [entry["name"] for entry in members[0]["entries"] if entry["kind"] == "directory" and entry["name"].casefold() == "memory"]
        if len(names) > 1:
            raise ValueError("unsupported_dashboard_memory_layout")
        memory_dir = names[0] if names else "memory"
        if memory_dir not in ("memory", "Memory"):
            raise ValueError("unsupported_dashboard_memory_layout")
        sources.directories("dashboard-brain-root", members)
        memory = sources.read(root, memory_dir + "/MEMORY.md", required=True, protected=True)
        learning_raw = sources.read(root, memory_dir + "/learning.json")
        learning = _strict_json(learning_raw) if learning_raw is not None else {}
        if "enabled" in learning and type(learning["enabled"]) is not bool:
            raise ValueError("insufficient_source: invalid_dashboard_learning_state")
        content = kernel
        content += host.main_prompt_rendering.render_profile_block(profile, preserve_full_protected=True)
        content += host.main_prompt_rendering.render_memory_block(memory, memory_cap=host.MEMORY_INDEX_MAX, preserve_full_protected=True)
        if learning.get("enabled") is False:
            content += host.memory_control.LEARNING_OFF_NOTE
        if project:
            content += host.main_prompt_rendering.render_project_instructions(project["name"], project["instructions"] or "",
                instructions_max=host.sessions.PROJECT_INSTRUCTIONS_MAX, preserve_full_protected=True)
        for scope in ("project", "session"):
            files, links = sql[scope + "_files"], sql[scope + "_links"]
            loaded = []
            for item in files:
                relative = output_path(item["path"])
                if relative.casefold() in target_paths:
                    raise ValueError("dashboard_target_context_overlap")
                if item["pinned"] and Path(relative).suffix.lower() in host.PROJECT_GHIM_DUOI:
                    # Existing serving policy requires a real file rooted in this
                    # brain. Retain its actual ACL/lineage for fresh permission checks.
                    authority = _authority(root, relative)
                    text = sources.read(root, relative, required=True, protected=True)
                    if _authority(root, relative) != authority:
                        raise ValueError("dashboard_attachment_authority_changed")
                    sources.semantic("inventory", "dashboard:attachment-authority:" + _hash(relative),
                        {"root": str(root), "relative": relative}, authority)
                    loaded.append(text)
                else:
                    loaded.append(None)
            lines, sections = host.main_attachment_rendering.render_attachment_lists(files, links, loaded,
                list_max=host.PROJECT_FILES_LIET_KE, allowed_suffixes=host.PROJECT_GHIM_DUOI,
                file_max=host.PROJECT_GHIM_FILE_MAX, total_max=host.PROJECT_GHIM_TONG_MAX, preserve_full_protected=True)
            content += (host.main_attachment_rendering.render_project_assets(lines, sections) if scope == "project" else
                        host.main_attachment_rendering.render_session_assets(lines, sections))
        layout = catalog["layout"]
        if not all((root / layout[key]).is_dir() for key in ("agents", "workflows")):
            raise ValueError("unsupported_dashboard_unwarmed_sync")
        content += host.main_prompt_rendering.render_agentic_paths(str(root), root / layout["agents"], root / layout["workflows"],
                                                                  root / "Javis/loops", root / layout["skills"])
        caps = {**catalog["capabilities"], "plugins": plugins["plugins"]}
        latest = sql["latest_workflow"]
        latest_line = ""
        if latest:
            import workflow_runs
            labels = workflow_runs.NHAN_TRANG_THAI if plugins["locale"]["resolved"] == host.lang_registry.MAC_DINH else workflow_runs.NHAN_TRANG_THAI_EN
            stamp = datetime.fromtimestamp(latest["started_at"], ZoneInfo(locale["tz"])).strftime("%H:%M %d/%m")
            latest_line = (f"Lần chạy quy trình gần nhất: {latest['name']} lúc {stamp} ({labels[latest['status']]}). "
                           "Chi tiết hay các lần khác: tool javis_workflow (op=runs, op=show).")
        content += host.main_prompt_rendering.render_capability_summary(caps, latest_line)
        content += host.main_prompt_rendering.render_skill_router(catalog["router"]["visible"], skills_dir=root / "skills",
            hidden_count=catalog["router"]["hidden_count"], description_max=host.skill_router.SKILL_DESC_MAX)
        now = datetime.fromisoformat(volatile["clock_utc"])
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("invalid_dashboard_clock")
        total = volatile["usage_total"]
        if total is None:
            usage_path = self.state_root / "usage.json"
            _check_path(usage_path)
            try:
                usage_path.lstat()
            except FileNotFoundError:
                raw = None
            else:
                raw, _ = _read_stable(usage_path, MAX_SETTINGS_BYTES)
            usage = _strict_json(raw.decode("utf-8")) if raw is not None else {"days": {}, "total": {}}
            if type(usage.get("days")) is not dict:
                raise ValueError("insufficient_source: invalid_dashboard_usage")
            bucket = usage["days"].get(now.astimezone(ZoneInfo(locale["tz"])).strftime("%Y-%m-%d"), {})
            if type(bucket) is not dict or any(type(value) is not dict for value in bucket.values()):
                raise ValueError("insufficient_source: invalid_dashboard_usage")
            for key, value in bucket.items():
                if (type(key) is not str or set(value) != {"in", "out", "turns", "cost"}
                        or any(type(value[field]) is not int or value[field] < 0 for field in ("in", "out", "turns"))
                        or type(value["cost"]) not in (int, float) or not math.isfinite(value["cost"]) or value["cost"] < 0):
                    raise ValueError("insufficient_source: invalid_dashboard_usage")
            total = host.usage_store._rollup(bucket)["total"]
        if (type(total) is not dict or set(total) != {"in", "out", "turns", "cost"}
                or any(type(total[key]) is not int or total[key] < 0 for key in ("in", "out", "turns"))
                or type(total["cost"]) not in (int, float) or not math.isfinite(total["cost"]) or total["cost"] < 0):
            raise ValueError("insufficient_source: invalid_dashboard_usage")
        volatile = {"clock_utc": volatile["clock_utc"], "usage_total": total}
        sources.semantic("runtime", "dashboard:volatile", {"policy": "frozen-clock-and-daily-usage-v1"}, volatile, role="volatile")
        language_decision = host.lang_mod.LangDecision(language, "setting" if locale["reply_lang"] != "auto" else "ui", 1.0,
                                                      True, theo_nguoi_dung=locale["reply_lang"] == "auto")
        content += host.main_prompt_rendering.render_clock_language(_clock(now, language, locale["tz"], host.lang_registry),
                                                                    host.lang_mod.khoi_ngon_ngu(language_decision))
        content += host.main_prompt_rendering.render_usage_block(total)
        port_raw = os.environ.get("JAVIS_PORT", "7777")
        if not port_raw.isdecimal() or not 1 <= int(port_raw) <= 65535:
            raise ValueError("unsupported_dashboard_port")
        tg = host._TG_BOT is not None
        if tg and any("__bool__" in vars(cls) or "__len__" in vars(cls) for cls in type(host._TG_BOT).__mro__):
            raise ValueError("unsupported_dashboard_telegram_state")
        content += host.channel_context.build_channel_block("dashboard", {"session_id": surface["session_id"]},
            telegram_running=tg, port=int(port_raw), brain_root=str(root))
        sources.semantic("inventory", "dashboard:host", {"profile": "ordinary-dashboard-v1"},
            {"port": int(port_raw), "telegram_running": tg, "selection": selection, "language": language,
             "memory_layout": memory_dir, "target_refs": sorted(target_paths), "root_identity": _hash(_semantic_incarnation(root.stat()))})
        for filename in ("main.py", "main_prompt_rendering.py", "main_attachment_rendering.py", "channel_context.py", "context_compiler.py",
            "memory_control.py", "lang.py", "lang_registry.py", "localefmt.py", "usage_store.py", "config.py", "coding_store.py",
            "improvement_claude.py", "claude_sdk_engine.py", "adaptive_context_runtime.py", "fast_path_runtime.py", "workflow_runs.py",
            "system_sync.py", "skill_router.py", "improvement_trial_dashboard.py", "improvement_recipe_sources.py", "improvement_trial_semantics.py", "improvement_trial_catalog.py", "improvement_trial_sql_context.py"):
            path = str(_SERVER / filename).casefold()
            if path not in sources.files:
                sources.code(filename)
        # Brain-native owner rules are additive protected instructions, distinct
        # from Javis kernel and memory. Imports need an explicit future resolver.
        protected = []
        for relative in ("CLAUDE.md", "CLAUDE.local.md", ".claude/CLAUDE.md", ".claude/CLAUDE.local.md"):
            text = sources.read(root, relative, protected=True)
            if text is not None:
                protected.append((relative, text))
        directories = []
        def rules(relative):
            for entry in _directory(root, relative, directories) or []:
                name = relative + "/" + entry["name"]
                if entry["kind"] == "directory":
                    if len(directories) > MAX_NATIVE_RULE_FILES or len(Path(name).parts) > 20:
                        raise ValueError("insufficient_source: native_rules_too_large")
                    rules(name)
                elif entry["kind"] == "file" and entry["name"].endswith(".md"):
                    if len(protected) >= MAX_NATIVE_RULE_FILES:
                        raise ValueError("insufficient_source: native_rules_too_large")
                    protected.append((name, sources.read(root, name, required=True, protected=True)))
        rules(".claude/rules")
        sources.directories("dashboard-native-rules", directories)
        for relative, text in protected:
            if re.search(r"(?m)(?:^|\s)@(?:[A-Za-z0-9_./~]|[A-Za-z]:)", text):
                raise ValueError("unsupported_native_import")
            content += f"\n\n# === NATIVE OWNER INSTRUCTIONS: {relative} ===\n" + text
        for target in targets:
            raw, _ = _read_stable(root / target["canonical_ref"], MAX_SETTINGS_BYTES)
            if hashlib.sha256(raw).hexdigest() != target["source_hash"]:
                raise ValueError("dashboard_target_changed")
            text = raw.decode("utf-8", errors="strict")
            if text and text in content:
                raise ValueError("dashboard_target_context_overlap")
        if redact(content) != content:
            raise ValueError("insufficient_source: credential_bearing_dashboard_context")
        return capture_semantics(surface=surface, sources=sources.items, content=content, complete_plan=True)
