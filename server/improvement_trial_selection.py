"""Strict read-only selection capture; never load decrypted config or execute a runtime.

The ordinary Claude factory always uses the SDK. This reader deliberately rejects
its implicit model/provider fallbacks: trials need an explicit persisted selection.
Runtime versions below come from the verified hash allowlist, not a CLI invocation.
"""
from __future__ import annotations

import hashlib
import ast
import importlib.metadata
import json
import math
import os
import re
import shutil
import stat
import sys
import types
import threading
import inspect
from functools import wraps
from pathlib import Path

import improvement_claude as native

MAX_SETTINGS_BYTES = 1024 * 1024
MAX_BINARY_BYTES = 512 * 1024 * 1024
_FIELDS = {"provider", "model", "reasoning", "auth_mode", "fast"}
_binary_observation = threading.local()

# Audited ordinary discovery semantics. Unknown source changes require another
# parity review, rather than silently assigning the SDK a different executable.
_DISCOVERY_CODE = {
    "tim_binary": "3a106ae21c4cfa126d8c36e732dffe9045226239038bff13cdb70db2860b1c2b",
    "_duong_dan_tim_binary": "4b54e92c6b5b078adcf123159c37341bf99d304eb8195dae82431b71622d3ba2",
    "_thu_muc_bin_windows": "84ec5dc0a1c0ec7c977e6b80383f57497509b6cd5ef6547b7b5f1a0da618254c",
    "_home_dir": "5c70cc1085f020104f4b72bc08a323bda413aa69bdd83ed32d8dd8caa6b97781",
    "_state_dir": "e97b40c8983e0795acb59b2c8a1ef726ff4e44acb07c9c6699dbf442c2e2fbd8",
    "_doc_bin_nho": "df04b8ed0929d15f74cbce87f7a9c803c071a1f7447d53f542874e1dbbb24979",
    "_binary_da_nho": "0a70eeed3ebe4623019425b374f3ce20acec9d539f36c882dbd8d38e50b9dcbc",
    "ClaudeSDK._options": "278718fd845cc87cd8c1c7a10285349fbb5fad1fbefea770f3be910f678c380a",
}


def _codes(code):
    yield code
    for value in code.co_consts:
        if type(value) is types.CodeType:
            yield from _codes(value)


def _discovery_source(module, name, functions):
    """Validate loaded callable identities and audited source without executing it."""
    error = "trial_selection_discovery_changed"
    path = Path(__file__).resolve().parent / (name + ".py")
    if (type(module) is not types.ModuleType or sys.modules.get(name) is not module
            or Path(module.__file__).resolve() != path):
        raise ValueError(error)
    raw, _ = _read_stable(path, 8 * MAX_SETTINGS_BYTES)
    tree = ast.parse(raw)
    compiled = None
    for dotted in functions:
        nodes, function = tree.body, module
        for part in dotted.split("."):
            function = getattr(function, part, None)
            node = next((item for item in nodes if isinstance(item, (ast.ClassDef, ast.FunctionDef)) and item.name == part), None)
            if node is None:
                raise ValueError(error)
            nodes = node.body
        if (type(function) is not types.FunctionType or function.__globals__ is not module.__dict__
                or function.__closure__ or function.__module__ != name
                or Path(function.__code__.co_filename).resolve() != path
                or hashlib.sha256(ast.dump(node, include_attributes=False).encode()).hexdigest() != _DISCOVERY_CODE[dotted]):
            raise ValueError(error)
        if compiled is None:
            compiled = list(_codes(compile(raw, function.__code__.co_filename, "exec", dont_inherit=True)))
        if function.__code__ not in compiled:
            raise ValueError(error)
    return tree


def _discovery_guard(cli, sdk, state_root):
    error = "trial_selection_discovery_changed"
    tree = _discovery_source(cli, "claude_cli", [key for key in _DISCOVERY_CODE if "." not in key])
    _discovery_source(sdk, "claude_sdk_engine", ["ClaudeSDK._options"])
    for name, value in (("os", os), ("sys", sys), ("shutil", shutil), ("Path", Path), ("re", re), ("json", json)):
        if getattr(cli, name, None) is not value:
            raise ValueError(error)
    if sdk.os is not os or sdk._SDK_OK is not True or sdk._sdk is not sys.modules.get("claude_agent_sdk"):
        raise ValueError(error)
    options = getattr(sdk._sdk, "ClaudeAgentOptions", None)
    if "cli_path" not in getattr(options, "__dataclass_fields__", {}):
        raise ValueError("trial_selection_sdk_cli_unavailable")
    assignments = {target.id: node.value for node in tree.body if isinstance(node, ast.Assign)
                   for target in node.targets if isinstance(target, ast.Name)}
    for name in ("_THU_MUC_BIN_THEM", "_THU_MUC_BIN_WINDOWS", "_BIN_NHO_FILE"):
        if getattr(cli, name, None) != ast.literal_eval(assignments[name]):
            raise ValueError(error)
    expression = assignments["_RX_BIEN_WIN"]
    if (type(cli._RX_BIEN_WIN) is not type(re.compile(""))
            or cli._RX_BIEN_WIN.pattern != ast.literal_eval(expression.args[0])
            or cli._RX_BIEN_WIN.flags != re.compile(ast.literal_eval(expression.args[0])).flags):
        raise ValueError(error)
    configured = (os.getenv("JAVIS_STATE_DIR", "") or "").strip()
    expected = Path(configured) if configured else Path(cli.__file__).resolve().parent
    if not state_root.is_absolute() or expected != state_root:
        raise ValueError("trial_selection_discovery_state_unavailable")


def _remembered_cli(cli, state_root):
    # The ordinary helper prefers its already-loaded cache, even if disk differs.
    # Never call _doc_bin_nho: it warms mutable process state on a metadata read.
    cache = cli._BIN_NHO
    if type(cache) is not dict or set(cache) != {"data"}:
        raise ValueError("trial_selection_discovery_changed")
    data = cache["data"]
    if data is None:
        path = state_root / cli._BIN_NHO_FILE
        if not path.exists():
            return ""
        raw, _ = _read_stable(path, MAX_SETTINGS_BYTES)
        data = json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs, parse_constant=_constant, parse_float=_finite)
    if type(data) is not dict:
        return ""
    value = data.get("claude") or ""
    if type(value) is not str:
        raise ValueError("trial_selection_discovery_unavailable")
    return value if value and os.path.isfile(value) else ""


def _sdk_cli_path(cli, state_root):
    override = (os.environ.get("JAVIS_CLAUDE_CLI") or "").strip()
    selected = override or shutil.which("claude") or shutil.which("claude", path=cli._duong_dan_tim_binary())
    selected = selected or _remembered_cli(cli, state_root)
    if not selected or "_bundled" in selected.replace("\\", "/"):
        raise ValueError("trial_selection_sdk_cli_unavailable")
    path = Path(selected)
    if not path.is_absolute() or ".." in path.parts:
        raise ValueError("trial_selection_sdk_cli_unavailable")
    _path_info(path)
    return path


def resolve_sdk_cli(claude_cli, claude_sdk_engine, state_root):
    """Resolve the ordinary current SDK executable without cache writes or probes.

    This returns the actual selected path, independent of the runtime allowlist.
    Call create_pin separately; an unknown current binary must never select an old
    qualified binary instead. Cold modules and SDK bundled fallback are unsupported.
    """
    try:
        root = Path(state_root)
        _discovery_guard(claude_cli, claude_sdk_engine, root)
        first = _sdk_cli_path(claude_cli, root)
        identity = _identity(_path_info(first))
        _discovery_guard(claude_cli, claude_sdk_engine, root)
        if _sdk_cli_path(claude_cli, root) != first or _identity(_path_info(first)) != identity:
            raise ValueError("trial_selection_discovery_changed")
        return first
    except (OSError, TypeError, AttributeError, KeyError, IndexError, SyntaxError, StopIteration, UnicodeError, RecursionError):
        raise ValueError("trial_selection_discovery_unavailable") from None


def _identity(info):
    # Python 3.12 Windows lstat still exposes creation time as ctime, while fstat
    # exposes change time. birthtime is the comparable identity field on both.
    # Windows lstat also infers executable permission bits from a .exe suffix;
    # fstat does not. The file kind and Windows attributes remain comparable.
    return (info.st_dev, info.st_ino, stat.S_IFMT(info.st_mode), info.st_size, info.st_mtime_ns,
            getattr(info, "st_birthtime_ns", info.st_ctime_ns), getattr(info, "st_file_attributes", 0))


def _path_info(path):
    info = None
    for component in reversed((path, *path.parents)):
        info = component.lstat()
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise ValueError("trial_selection_linked_source")
    if info is None or not stat.S_ISREG(info.st_mode):
        raise ValueError("trial_selection_nonregular_source")
    return info


def _read_stable(path, limit, *, digest=False):
    """Bind opened bytes to the same regular path identity before and after reading."""
    try:
        path = Path(path).absolute()
        before = _path_info(path)
        if not 0 <= before.st_size <= limit:
            raise ValueError("trial_selection_source_size")
        flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
        descriptor = os.open(path, flags)
        with os.fdopen(descriptor, "rb") as handle:
            if _identity(os.fstat(handle.fileno())) != _identity(before):
                raise ValueError("trial_selection_source_changed")
            result = hashlib.sha256() if digest else bytearray()
            size = 0
            while True:
                block = handle.read(min(1024 * 1024, limit - size + 1))
                if not block:
                    break
                size += len(block)
                if size > limit:
                    raise ValueError("trial_selection_source_size")
                if digest:
                    result.update(block)
                else:
                    result.extend(block)
            after = os.fstat(handle.fileno())
            if (_identity(after) != _identity(before) or size != before.st_size
                    or _identity(_path_info(path)) != _identity(before)):
                raise ValueError("trial_selection_source_changed")
        return (result.hexdigest() if digest else bytes(result)), _identity(before)
    except (OSError, TypeError, OverflowError):
        raise ValueError("trial_selection_source_unavailable") from None


def _bounded_binary_reads(function):
    """Only for synchronous view validation, without native execution/publication.

    Intermediate CLI observations retain fresh open/identity/permission checks.
    A result cannot leave this boundary until all CLI bytes are freshly rehashed.
    Never apply this around a writer, async work or a native/model call.
    """
    if inspect.iscoroutinefunction(function) or inspect.isgeneratorfunction(function) or inspect.isasyncgenfunction(function):
        raise TypeError('trial_selection_observation_requires_sync')
    @wraps(function)
    def observed(*args, **kwargs):
        if getattr(_binary_observation, 'values', None) is not None:
            raise ValueError('trial_selection_observation_nested')
        values = {}
        _binary_observation.values = values
        try:
            result = function(*args, **kwargs)
            # Disable reuse before the final independent full-byte observations.
            _binary_observation.values = None
            for path, (limit, expected) in values.items():
                if _read_stable(path, limit, digest=True) != expected:
                    raise ValueError('trial_selection_source_changed')
            return result
        finally:
            _binary_observation.values = None
    return observed


def _read_binary(path, limit):
    """CLI-only opt-in; ordinary digest/source callers remain entirely fresh."""
    values = getattr(_binary_observation, 'values', None)
    if values is None:
        return _read_stable(path, limit, digest=True)
    try:
        path = Path(path).absolute()
        cached = values.get(path)
        if cached is None:
            result = _read_stable(path, limit, digest=True)
            values[path] = (limit, result)
            return result
        _, result = cached
        before = _path_info(path)
        if not 0 <= before.st_size <= limit:
            raise ValueError('trial_selection_source_size')
        if _identity(before) != result[1]:
            raise ValueError('trial_selection_source_changed')
        flags = os.O_RDONLY | getattr(os, 'O_BINARY', 0) | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_NONBLOCK', 0)
        descriptor = os.open(path, flags)
        try:
            if (_identity(os.fstat(descriptor)) != result[1]
                    or _identity(_path_info(path)) != result[1]
                    or _identity(os.fstat(descriptor)) != result[1]):
                raise ValueError('trial_selection_source_changed')
        finally:
            os.close(descriptor)
        return result
    except (OSError, TypeError, OverflowError):
        raise ValueError('trial_selection_source_unavailable') from None


def _pairs(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("trial_selection_duplicate_key")
        value[key] = item
    return value


def _finite(value):
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("trial_selection_nonfinite_json")
    return number


def _constant(value):
    raise ValueError("trial_selection_nonfinite_json")


def _text(value, limit=512):
    if (not isinstance(value, str) or not 1 <= len(value) <= limit or not value.strip()
            or any(ord(character) < 32 for character in value)):
        raise ValueError("trial_selection_invalid_field")
    try:
        value.encode("utf-8")
    except UnicodeError:
        raise ValueError("trial_selection_invalid_field") from None
    return value


def _closed(value):
    if not isinstance(value, dict) or set(value) != _FIELDS:
        raise ValueError("trial_selection_invalid_fields")
    for field in ("provider", "model", "reasoning", "auth_mode"):
        _text(value[field])
    if type(value["fast"]) is not bool or value["auth_mode"] not in {"subscription", "api_key"}:
        raise ValueError("trial_selection_invalid_field")
    return dict(value)


def _selection(settings_path):
    content, identity = _read_stable(settings_path, MAX_SETTINGS_BYTES)
    try:
        settings = json.loads(content.decode("utf-8"), object_pairs_hook=_pairs,
                              parse_constant=_constant, parse_float=_finite)
    except (ValueError, UnicodeError, RecursionError):
        raise ValueError("trial_selection_invalid_json") from None
    if not isinstance(settings, dict) or not isinstance(settings.get("model"), dict):
        raise ValueError("trial_selection_model_missing")
    model = settings["model"]
    main = model.get("main")
    if main is None:
        main = {}
    if not isinstance(main, dict):
        raise ValueError("trial_selection_invalid_main")
    provider, selected_model = main.get("provider", ""), main.get("model", "")
    if provider == "" and selected_model == "":
        if model.get("engine") != "cli":
            raise ValueError("trial_selection_legacy_engine_unsupported")
        provider, selected_model = "anthropic-cli", model.get("claude_model")
    value = _closed({"provider": provider, "model": selected_model,
                     "reasoning": model.get("reasoning", "off"), "fast": model.get("fast", False),
                     "auth_mode": model.get("claude_auth", "subscription")})
    return value, identity


def read_selection(settings_path):
    """Return only persisted nonsecret routing semantics; failures never become defaults."""
    return _selection(settings_path)[0]


def selection_hash(value):
    """Hash exactly the five semantic fields, independent of unrelated secret changes."""
    raw = json.dumps(_closed(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def create_pin(settings_path, cli_path):
    """Build the adapter's closed pin using a known binary hash; no auth or CLI probes."""
    selected, source_identity = _selection(settings_path)
    if (selected["provider"] != "anthropic-cli" or selected["auth_mode"] != "subscription"
            or selected["fast"] or selected["reasoning"] not in {"low", "medium", "high", "xhigh", "max"}):
        raise ValueError("unsupported_trial_configuration")
    try:
        binary = Path(cli_path)
        if not binary.is_absolute():
            raise ValueError("trial_selection_binary_not_absolute")
        digest, binary_identity = _read_binary(binary, MAX_BINARY_BYTES)
        sdk_version = importlib.metadata.version("claude-agent-sdk")
        matches = [runtime for runtime in native.VERIFIED_NATIVE_RUNTIMES
                   if runtime[0] == sys.platform and runtime[2:] == (digest, sdk_version)]
        if len(matches) != 1:
            raise ValueError("trial_selection_runtime_unverified")
        profile = native.profile_hash()
        pin = {"version": 1, "provider": selected["provider"], "engine_id": "claude-sdk",
               "model": selected["model"], "reasoning": selected["reasoning"], "cli_path": str(binary),
               "cli_hash": digest, "cli_version": matches[0][1], "sdk_version": sdk_version,
               "profile_version": native.PROFILE_VERSION, "profile_hash": profile}
        # Validate only the closed schema: verify() executes native version/auth probes.
        native.ClaudeTrialAdapter(pin)
        if importlib.metadata.version("claude-agent-sdk") != sdk_version or native.profile_hash() != profile:
            raise ValueError("trial_selection_capture_changed")
        current, current_identity = _selection(settings_path)
        if (current != selected or current_identity != source_identity
                or _identity(_path_info(binary)) != binary_identity):
            raise ValueError("trial_selection_capture_changed")
        return pin
    except (OSError, TypeError, importlib.metadata.PackageNotFoundError):
        raise ValueError("trial_selection_runtime_unavailable") from None
