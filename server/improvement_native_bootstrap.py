"""Fixed Windows bootstrap; declared-file verification is not an import sandbox.

The host must authenticate these bootstrap bytes and the complete qualified
source/runtime/import manifest before launch. Self-hashes cannot provide that
authority. Loaded module pathnames/current files do not prove initial sections.
No SDK, account, model input, or business source is imported on module import.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path, PureWindowsPath
import re
import struct
import sys
import types


_NAME = "improvement_native_bootstrap.py"
_IMAGE = "improvement_native_image.py"
_TARGETS = {"trial": "improvement_worker.py", "operation": "improvement_operation_worker.py",
            "guardian": "improvement_native_lifetime.py"}
_MAX_FRAME = 1024 * 1024
_MAX_FILES = 4096
_RETAINED_OWNERS = []


def _invalid():
    raise ValueError("invalid_native_bootstrap")


def _text(value):
    if type(value) is not str or not value or "\x00" in value:
        _invalid()
    try:
        if len(value.encode("utf-16-le")) // 2 > 32766:
            _invalid()
    except UnicodeEncodeError:
        _invalid()


def _digest(value):
    if type(value) is not str or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        _invalid()


def _fields(value, fields):
    if type(value) is not dict or any(type(key) is not str for key in value) or set(value) != fields:
        _invalid()


def _absolute(value):
    _text(value)
    path = PureWindowsPath(value)
    if (not path.is_absolute() or re.fullmatch(r"[A-Za-z]:", path.drive) is None
            or any(part in (".", "..") or part.endswith((" ", ".")) for part in value.replace("\\", "/").split("/")[1:])):
        _invalid()


def _files(value):
    if type(value) is not dict or len(value) > _MAX_FILES:
        _invalid()
    folded = set()
    for name, digest in value.items():
        _text(name)
        if (len(name) > 1000 or "\\" in name or ":" in name or name.startswith("/")
                or any(part in ("", ".", "..") or part.endswith((" ", ".")) for part in name.split("/"))
                or name.casefold() in folded):
            _invalid()
        folded.add(name.casefold())
        _digest(digest)


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def validate_bootstrap_manifest(manifest):
    """Validate/copy declared pins; qualification/authentication stay external."""
    _fields(manifest, {"version", "entrypoint", "runtime", "source", "imports"})
    if (type(manifest["version"]) is not int or manifest["version"] != 1
            or type(manifest["entrypoint"]) is not str or manifest["entrypoint"] not in _TARGETS):
        _invalid()
    _fields(manifest["runtime"], {"executable", "dll"})
    for pin in manifest["runtime"].values():
        _fields(pin, {"path", "sha256", "volume_serial_64", "file_id_128"})
        _absolute(pin["path"])
        _digest(pin["sha256"])
        if (type(pin["volume_serial_64"]) is not int or not 0 < pin["volume_serial_64"] < 2 ** 64
                or type(pin["file_id_128"]) is not str or re.fullmatch(r"[0-9a-f]{32}", pin["file_id_128"]) is None):
            _invalid()
    _fields(manifest["source"], {"root", "files"})
    _fields(manifest["imports"], {"site_packages", "files"})
    _absolute(manifest["source"]["root"])
    _absolute(manifest["imports"]["site_packages"])
    _files(manifest["source"]["files"])
    _files(manifest["imports"]["files"])
    if (not {_NAME, _IMAGE, _TARGETS[manifest["entrypoint"]]} <= set(manifest["source"]["files"])
            or len(manifest["source"]["files"]) + len(manifest["imports"]["files"]) > _MAX_FILES):
        _invalid()
    raw = _canonical(manifest)
    if len(raw) > _MAX_FRAME:
        _invalid()
    return json.loads(raw)


def encode_bootstrap_frame(manifest) -> bytes:
    """Prefix one canonical manifest with its four-byte unsigned network length."""
    raw = _canonical(validate_bootstrap_manifest(manifest))
    return struct.pack(">I", len(raw)) + raw


def read_bootstrap_frame(fd=0):
    """Read only this frame; never buffer/prefetch the following worker packet."""
    if type(fd) is not int or fd < 0:
        _invalid()

    def exact(size):
        raw = bytearray()
        while len(raw) < size:
            part = os.read(fd, size - len(raw))
            if not part:
                raise ValueError("native_bootstrap_frame_incomplete")
            raw.extend(part)
        return bytes(raw)

    size, = struct.unpack(">I", exact(4))
    if not 0 < size <= _MAX_FRAME:
        _invalid()

    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                _invalid()
            result[key] = value
        return result

    def constant(_):
        _invalid()

    try:
        value = json.loads(exact(size), object_pairs_hook=pairs, parse_constant=constant)
        return validate_bootstrap_manifest(value)
    except (UnicodeError, ValueError, RecursionError):
        raise ValueError("invalid_native_bootstrap") from None


def _require_isolated():
    if (sys.flags.isolated != 1 or sys.flags.no_site != 1 or not sys.dont_write_bytecode
            or "site" in sys.modules):
        raise ValueError("native_bootstrap_isolation_required")


def _runtime_paths():
    """Observe actual process and Python-DLL module pathnames, without a child."""
    if os.name != "nt":
        raise OSError("native_bootstrap_windows_required")
    import ctypes
    from ctypes import wintypes
    dll = getattr(sys, "dllhandle", None)
    if type(dll) is not int or dll <= 0:
        raise ValueError("native_bootstrap_python_dll_unavailable")
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.GetModuleFileNameW.argtypes = [wintypes.HMODULE, wintypes.LPWSTR, wintypes.DWORD]
    kernel.GetModuleFileNameW.restype = wintypes.DWORD
    result = {}
    for name, handle in (("executable", None), ("dll", dll)):
        buffer = ctypes.create_unicode_buffer(32768)
        count = kernel.GetModuleFileNameW(handle, buffer, len(buffer))
        if not 0 < count < len(buffer):
            raise OSError("native_bootstrap_module_path_unavailable")
        result[name] = buffer.value
    return result


def _same_path(left, right):
    return os.path.normcase(os.path.normpath(str(left))) == os.path.normcase(os.path.normpath(str(right)))


def _read_source(path, digest):
    with open(path, "rb") as reader:
        raw = reader.read(8 * 1024 * 1024 + 1)
    if not raw or len(raw) > 8 * 1024 * 1024 or hashlib.sha256(raw).hexdigest() != digest:
        raise ValueError("native_bootstrap_source_changed")
    return raw


def _load_guard_type(root, files):
    path = root / _IMAGE
    raw = _read_source(path, files[_IMAGE])
    module = types.ModuleType("_javis_verified_bootstrap_image")
    module.__file__ = str(path)
    exec(compile(raw, str(path), "exec"), module.__dict__)
    return module.ImageReadGuard


def _retain(owner, error):
    if not any(value is owner for value in _RETAINED_OWNERS):
        _RETAINED_OWNERS.append(owner)
    error.owner = owner


class BootstrapOwner:
    """Own declared-file guards/DLL search lifetime and verified fixed target.

    prepare/run_target/close are synchronous inside one isolated Windows worker.
    The manifest is copied. Public ImageReadGuard methods verify declared files;
    no private guard handle is accessed. snapshot explicitly leaves unlisted
    import exclusion, initial loaded sections and host authentication unproved.
    Failed close retains the resource, owner and error.owner for a later retry.
    """

    def __init__(self, manifest):
        self._manifest = validate_bootstrap_manifest(manifest)
        self._resources, self._guards = [], []
        self._saved_path = None
        self._target_bytes = self._target_path = None
        self._prepared = self._closing = self._closed = self._ran = False

    def _guard(self, kind, path, digest):
        try:
            guard = kind(path, digest)
        except BaseException as error:
            partial = getattr(error, "guard", None)
            if partial is not None:
                self._resources.append(partial)
            raise
        self._resources.append(guard)
        self._guards.append(guard)
        return guard

    def prepare(self):
        if self._prepared or self._closing or self._closed:
            raise ValueError("native_bootstrap_owner_unavailable")
        if os.name != "nt":
            raise OSError("native_bootstrap_windows_required")
        try:
            _require_isolated()
            paths = _runtime_paths()
            runtime = self._manifest["runtime"]
            if (not _same_path(sys.executable, runtime["executable"]["path"])
                    or not _same_path(getattr(sys, "_base_executable", sys.executable), runtime["executable"]["path"])
                    or any(not _same_path(paths[name], pin["path"]) for name, pin in runtime.items())):
                raise ValueError("native_bootstrap_runtime_path_mismatch")
            root = Path(__file__).resolve().parent
            if Path(__file__).name != _NAME or not _same_path(root, self._manifest["source"]["root"]):
                raise ValueError("native_bootstrap_source_root_mismatch")
            files = self._manifest["source"]["files"]
            guard_type = _load_guard_type(root, files)
            import msvcrt
            for pin in runtime.values():
                guard = self._guard(guard_type, Path(pin["path"]), pin["sha256"])
                reader = open(pin["path"], "rb")
                self._resources.append(reader)
                compared = guard.compare_file_handle(msvcrt.get_osfhandle(reader.fileno()))
                if (compared["matches"] is not True or any(compared["actual"][key] != pin[key]
                        for key in ("sha256", "volume_serial_64", "file_id_128"))):
                    raise ValueError("native_bootstrap_runtime_identity_mismatch")
            for name, digest in files.items():
                self._guard(guard_type, root.joinpath(*name.split("/")), digest)
            packages = Path(self._manifest["imports"]["site_packages"])
            for name, digest in self._manifest["imports"]["files"].items():
                self._guard(guard_type, packages.joinpath(*name.split("/")), digest)
            self._target_path = root / _TARGETS[self._manifest["entrypoint"]]
            self._target_bytes = _read_source(self._target_path, files[self._target_path.name])
            explicit = [root, packages, packages / "win32", packages / "win32" / "lib"]
            dll_dir = packages / "pywin32_system32"
            if any(not path.is_dir() for path in [*explicit, dll_dir]):
                raise ValueError("native_bootstrap_import_directory_unavailable")
            self._resources.append(os.add_dll_directory(str(dll_dir)))
            self._saved_path = list(sys.path)
            prefix = [str(path) for path in explicit]
            sys.path[:] = prefix + [path for path in sys.path if not any(_same_path(path, item) for item in prefix)]
            self._prepared = True
            return self.snapshot()
        except BaseException as error:
            try:
                self.close()
            except BaseException as cleanup:
                raise cleanup from error
            raise

    def snapshot(self):
        if not self._prepared or self._closing or self._closed:
            raise ValueError("native_bootstrap_owner_unavailable")
        for guard in self._guards:
            guard.snapshot()
        return {"version": 1, "entrypoint": self._manifest["entrypoint"],
                "manifest_hash": hashlib.sha256(_canonical(self._manifest)).hexdigest(),
                "declared_files": len(self._guards), "site_processing": False,
                "coverage": {"declared_pins": "verified", "unlisted_import_exclusion": "unknown",
                             "initial_loaded_sections": "unknown", "host_manifest_authentication": "external_required"}}

    def run_target(self):
        self.snapshot()
        if self._ran:
            raise ValueError("native_bootstrap_target_already_run")
        self._ran = True
        old_argv = list(sys.argv)
        sys.argv[:] = [str(self._target_path)]
        namespace = {"__name__": "__main__", "__file__": str(self._target_path), "__package__": None,
                     "__spec__": None, "__cached__": None, "__loader__": None}
        try:
            exec(compile(self._target_bytes, str(self._target_path), "exec"), namespace)
            return 0
        except SystemExit as error:
            return 0 if error.code is None else error.code if type(error.code) is int else 1
        finally:
            sys.argv[:] = old_argv

    def close(self):
        self._closing = True
        try:
            while self._resources:
                self._resources[-1].close()
                self._resources.pop()
        except BaseException as error:
            _retain(self, error)
            raise
        if self._saved_path is not None:
            sys.path[:] = self._saved_path
            self._saved_path = None
        self._closed = True
        _RETAINED_OWNERS[:] = [owner for owner in _RETAINED_OWNERS if owner is not self]


def bootstrap_main():
    """Read one pin frame, run one fixed target, and retain failed cleanup owners."""
    if len(sys.argv) != 1:
        raise ValueError("native_bootstrap_arguments_forbidden")
    owner = BootstrapOwner(read_bootstrap_frame())
    try:
        owner.prepare()
        result = owner.run_target()
    except BaseException as error:
        try:
            owner.close()
        except BaseException as cleanup:
            _retain(owner, cleanup)
            raise cleanup from error
        raise
    try:
        owner.close()
    except BaseException as error:
        _retain(owner, error)
        raise
    return result


if __name__ == "__main__":
    raise SystemExit(bootstrap_main())
