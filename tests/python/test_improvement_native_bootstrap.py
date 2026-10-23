"""Fixed bootstrap contracts only; no SDK client, native child, or account probe."""
from _paths import ROOT, SERVER  # noqa: F401

import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import struct
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

if importlib.util.find_spec("improvement_native_bootstrap"):
    import improvement_native_bootstrap as BOOT
else:
    BOOT = None


TARGETS = {"trial": "improvement_worker.py", "operation": "improvement_operation_worker.py",
           "guardian": "improvement_native_lifetime.py"}
MAX_FRAME = 1024 * 1024


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def manifest(entrypoint="trial"):
    pin = {"path": r"C:\Python312\python.exe", "sha256": "a" * 64,
           "volume_serial_64": 17, "file_id_128": "b" * 32}
    return {"version": 1, "entrypoint": entrypoint,
            "runtime": {"executable": pin, "dll": {**pin, "path": r"C:\Python312\python312.dll"}},
            "source": {"root": r"D:\Trusted Source\server", "files": {
                "improvement_native_bootstrap.py": "c" * 64, "improvement_native_image.py": "d" * 64,
                TARGETS[entrypoint]: "e" * 64}},
            "imports": {"site_packages": r"D:\Trusted Venv\Lib\site-packages", "files": {"owned/package.py": "f" * 64}}}


class BootstrapContractTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(BOOT, "The fixed isolated bootstrap is not implemented")

    def pipe(self, raw):
        reader, writer = os.pipe()
        try:
            os.write(writer, raw)
        finally:
            os.close(writer)
        self.addCleanup(os.close, reader)
        return reader

    def test_three_fixed_entrypoints_and_canonical_defensive_manifest(self):
        for entrypoint in TARGETS:
            original = manifest(entrypoint)
            pinned = BOOT.validate_bootstrap_manifest(original)
            self.assertEqual(pinned, original)
            pinned["source"]["files"].clear()
            self.assertIn(TARGETS[entrypoint], original["source"]["files"])
            frame = BOOT.encode_bootstrap_frame(original)
            self.assertEqual(frame[:4], struct.pack(">I", len(canonical(original))))
            self.assertEqual(frame[4:], canonical(original))

    def test_one_frame_preserves_exact_following_worker_packet_even_with_fragmented_reads(self):
        value = manifest()
        packet = b'{"version":1,"private_worker_packet":"caf\xc3\xa9\\u0000"}\n'
        reader = self.pipe(BOOT.encode_bootstrap_frame(value) + packet)
        real_read = os.read
        with patch.object(BOOT.os, "read", side_effect=lambda fd, size: real_read(fd, min(size, 3))):
            self.assertEqual(BOOT.read_bootstrap_frame(reader), value)
        self.assertEqual(os.read(reader, len(packet) + 1), packet)

    def test_truncated_empty_or_oversize_frames_fail_before_consuming_following_data(self):
        for raw in (b"", b"\x00\x00", struct.pack(">I", 7) + b"{}"):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                BOOT.read_bootstrap_frame(self.pipe(raw))
        for size in (0, MAX_FRAME + 1):
            reader = self.pipe(struct.pack(">I", size) + b"NEXT")
            with self.subTest(size=size), self.assertRaises(ValueError):
                BOOT.read_bootstrap_frame(reader)
            self.assertEqual(os.read(reader, 5), b"NEXT")

    def test_duplicate_json_keys_nonobjects_invalid_utf8_and_constants_are_rejected(self):
        raws = [b'{"version":1,"version":1}', b"[]", b"null", b"{", b"\xff", b'{"version":NaN}']
        valid = canonical(manifest()).decode("utf-8")
        raws.append(valid.replace('"volume_serial_64":17', '"volume_serial_64":17,"volume_serial_64":17', 1).encode())
        for raw in raws:
            with self.subTest(raw=raw[:80]), self.assertRaises(ValueError):
                BOOT.read_bootstrap_frame(self.pipe(struct.pack(">I", len(raw)) + raw))

    def test_schema_refuses_extra_auth_prompt_environment_and_boolean_integer_confusion(self):
        variants = [None, [], manifest() | {"version": True}, manifest() | {"version": 1.0},
                    manifest() | {"version": 2}, manifest() | {"auth": {}}, manifest() | {"prompt": "private"},
                    manifest() | {"environment": {"KEY": "private"}}]
        for location in ("runtime", "source", "imports"):
            changed = manifest()
            changed[location]["extra"] = "foreign"
            variants.append(changed)
        for value in (True, 0, -1, 2 ** 64, "17"):
            changed = manifest()
            changed["runtime"]["dll"]["volume_serial_64"] = value
            variants.append(changed)
        for value in variants:
            with self.subTest(value=value), self.assertRaises(ValueError):
                BOOT.validate_bootstrap_manifest(value)

    def test_arbitrary_scripts_paths_missing_required_sources_and_bad_digests_are_refused(self):
        variants = [manifest() | {"entrypoint": "other.py"}, manifest() | {"entrypoint": "../improvement_worker.py"}]
        for key in manifest()["source"]["files"]:
            changed = manifest()
            changed["source"]["files"].pop(key)
            variants.append(changed)
        for path in ("../outside.py", "/absolute.py", "C:relative.py", "a\\b.py", "a//b.py", "a/./b.py", "a.py:stream"):
            changed = manifest()
            changed["imports"]["files"] = {path: "a" * 64}
            variants.append(changed)
        for digest in ("", "A" * 64, "z" * 64, True):
            changed = manifest()
            changed["source"]["files"]["improvement_worker.py"] = digest
            variants.append(changed)
        for pin in variants:
            with self.subTest(pin=pin), self.assertRaises(ValueError):
                BOOT.validate_bootstrap_manifest(pin)

    def test_paths_are_windows_absolute_and_nul_surrogates_redirector_shapes_are_not_repaired(self):
        for path in ("relative", r"C:relative", r"\rooted", "/usr/bin/python", "C:\\bad\x00path", "C:\\bad\ud800path"):
            for location in ("runtime", "source", "imports"):
                changed = manifest()
                if location == "runtime":
                    changed[location]["executable"]["path"] = path
                else:
                    changed[location]["root" if location == "source" else "site_packages"] = path
                with self.subTest(path=repr(path), location=location), self.assertRaises(ValueError):
                    BOOT.validate_bootstrap_manifest(changed)

    def test_frame_encoder_refuses_python_only_values_and_excessive_pin_inventory(self):
        for files in ({"bad.py": b"bytes"}, {"bad.py": object()}, {str(i) + ".py": "a" * 64 for i in range(4097)}):
            changed = manifest()
            changed["imports"]["files"] = files
            with self.subTest(count=len(files)), self.assertRaises(ValueError):
                BOOT.encode_bootstrap_frame(changed)

    def test_close_failure_retains_complete_owner_and_retries_only_unclosed_resources(self):
        owner = BOOT.BootstrapOwner(manifest())
        calls = []

        class Resource:
            def __init__(self, name, fail=False):
                self.name, self.fail = name, fail

            def close(self):
                calls.append(self.name)
                if self.fail:
                    self.fail = False
                    raise OSError("controlled_close_failure")

        first, second, third = Resource("guard"), Resource("dll_dir", True), Resource("reader")
        owner._resources.extend([first, second, third])
        with self.assertRaisesRegex(OSError, "controlled_close_failure") as failure:
            owner.close()
        self.assertIs(failure.exception.owner, owner)
        self.assertEqual(calls, ["reader", "dll_dir"])
        self.assertEqual(owner._resources, [first, second])
        owner.close()
        owner.close()
        self.assertEqual(calls, ["reader", "dll_dir", "dll_dir", "guard"])
        self.assertEqual(owner._resources, [])

    def test_bootstrap_cleanup_error_retains_owner_and_preserves_the_target_failure(self):
        body_error = RuntimeError("controlled_target_failure")
        cleanup_error = OSError("controlled_cleanup_failure")
        fake = SimpleNamespace(prepare=lambda: None, run_target=lambda: (_ for _ in ()).throw(body_error),
                               close=lambda: (_ for _ in ()).throw(cleanup_error))
        with patch.object(BOOT, "read_bootstrap_frame", return_value=manifest()), \
                patch.object(BOOT, "BootstrapOwner", return_value=fake), \
                patch.object(BOOT.sys, "argv", ["improvement_native_bootstrap.py"]):
            with self.assertRaisesRegex(OSError, "controlled_cleanup_failure") as failure:
                BOOT.bootstrap_main()
        self.assertIs(failure.exception.owner, fake)
        self.assertIs(failure.exception.__cause__, body_error)

    @unittest.skipIf(os.name == "nt", "Linux-safe import and explicit Windows-only runtime")
    def test_module_import_is_pure_but_actual_bootstrap_runtime_requires_windows(self):
        owner = BOOT.BootstrapOwner(manifest())
        with self.assertRaisesRegex(OSError, "windows"):
            owner.prepare()
        owner.close()


@unittest.skipUnless(os.name == "nt", "Real in-process Windows declared-file guards")
class WindowsBootstrapTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(BOOT, "The fixed isolated bootstrap is not implemented")

    def test_actual_module_paths_are_observed_and_venv_executable_is_not_silently_rebound(self):
        paths = BOOT._runtime_paths()
        self.assertEqual(set(paths), {"executable", "dll"})
        self.assertTrue(all(Path(path).is_absolute() and Path(path).is_file() for path in paths.values()))
        # This is current loaded-module pathname observation, not section provenance.
        if Path(paths["executable"]) != Path(sys.executable):
            value = manifest()
            value["runtime"]["executable"]["path"] = str(Path(sys.executable))
            owner = BOOT.BootstrapOwner(value)
            with patch.object(BOOT, "_require_isolated", return_value=None), self.assertRaises(ValueError):
                owner.prepare()
            owner.close()

    def test_exact_declared_files_fixed_target_and_retained_dll_directory_without_sdk_import(self):
        # In-process unit fixture: isolation flags and direct-base sys.executable
        # are simulated. Runtime module paths and NTFS file guards are actual.
        paths = BOOT._runtime_paths()
        import msvcrt
        import improvement_native_image as image
        before_sdk = {name for name in sys.modules if name.startswith("claude_agent_sdk")}
        # _paths may inherit a deep runner JAVIS_TEST_TMP. Keep this owned Windows
        # handle fixture short enough for the unchanged guard's MAX_PATH surface.
        short_temp = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local"))) / "Temp"
        with tempfile.TemporaryDirectory(prefix="jb-", dir=short_temp) as scratch:
            root = Path(scratch)
            source, packages = root / "server", root / "site-packages"
            source.mkdir()
            for directory in (packages, packages / "win32", packages / "win32" / "lib", packages / "pywin32_system32"):
                directory.mkdir(exist_ok=True)
            (source / "improvement_native_bootstrap.py").write_bytes(Path(BOOT.__file__).read_bytes())
            (source / "improvement_native_image.py").write_bytes((SERVER / "improvement_native_image.py").read_bytes())
            target = source / "improvement_native_lifetime.py"
            target.write_bytes(b'import sys\nassert sys.argv == [__file__]\nraise SystemExit(7)\n')

            def file_pin(path):
                digest = sha(Path(path).read_bytes())
                with image.ImageReadGuard(path, digest) as guard, open(path, "rb") as reader:
                    actual = guard.compare_file_handle(msvcrt.get_osfhandle(reader.fileno()))["actual"]
                return {"path": str(path), "sha256": digest, "volume_serial_64": actual["volume_serial_64"],
                        "file_id_128": actual["file_id_128"]}

            value = {"version": 1, "entrypoint": "guardian", "runtime": {name: file_pin(path) for name, path in paths.items()},
                     "source": {"root": str(source), "files": {path.name: sha(path.read_bytes()) for path in source.iterdir()}},
                     "imports": {"site_packages": str(packages), "files": {}}}
            saved_path, saved_argv = list(sys.path), list(sys.argv)
            with patch.object(BOOT, "__file__", str(source / "improvement_native_bootstrap.py")), \
                    patch.object(BOOT, "_require_isolated", return_value=None), \
                    patch.object(BOOT.sys, "executable", paths["executable"]), \
                    patch.object(BOOT.sys, "_base_executable", paths["executable"]):
                owner = BOOT.BootstrapOwner(value)
                snapshot = owner.prepare()
                try:
                    self.assertEqual(snapshot["coverage"], {"declared_pins": "verified", "unlisted_import_exclusion": "unknown",
                                                            "initial_loaded_sections": "unknown", "host_manifest_authentication": "external_required"})
                    self.assertEqual(sys.path[:4], [str(source), str(packages), str(packages / "win32"), str(packages / "win32" / "lib")])
                    with self.assertRaises(PermissionError):
                        target.write_bytes(b"changed")
                    self.assertEqual(owner.run_target(), 7)
                    self.assertEqual(sys.argv, saved_argv)
                    self.assertEqual({name for name in sys.modules if name.startswith("claude_agent_sdk")}, before_sdk)
                finally:
                    owner.close()
            self.assertEqual(sys.path, saved_path)
            target.write_bytes(b"released")


if __name__ == "__main__":
    unittest.main()
