"""Pure SDK116 Windows query grammar, without connecting or starting a CLI."""
from _paths import ROOT, SERVER  # noqa: F401

import copy
import hashlib
import importlib.util
import json
import subprocess
import tempfile
import unittest
from contextlib import ExitStack
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from claude_agent_sdk._internal.transport.subprocess_cli import SubprocessCLITransport
from improvement_claude import TrialProfile
from improvement_sandbox import FixtureBroker, TrialWorkspace, trial_system_prompt
from improvement_store import _hash
from test_improvement_skill_asset_broker import manifest as make_manifest

if importlib.util.find_spec("improvement_query_dispatch"):
    from improvement_query_dispatch import validate_query_dispatch
else:
    validate_query_dispatch = None


CLI = r"C:\Trusted Tools\Claude\claude.exe"
CWD = r"D:\Trial Workspace\trial-a\attempt-2"
FLAGS = 0x08000006
TOOLS = ["mcp__fixture__fixture_read", "mcp__skill__skill_asset_read"]
PROMPT = 'Exact owner "quoted" rule\\tail\r\nCafé 日本語 😀\n'
MCP = {"mcpServers": {"fixture": {"type": "sdk", "name": "fixture"}, "skill": {"type": "sdk", "name": "skill"}}}


def sha(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def command(prompt=PROMPT, effort="medium"):
    return [CLI, "--output-format", "stream-json", "--verbose", "--system-prompt", prompt,
            "--tools", "", "--allowedTools", ",".join(TOOLS), "--model", "claude-opus-5-5",
            "--permission-prompt-tool", "stdio", "--permission-mode", "default",
            "--settings", '{"fastMode":false,"disableAllHooks":true}', "--mcp-config", canonical(MCP),
            "--strict-mcp-config", "--setting-sources=", "--no-session-persistence", "--disable-slash-commands",
            "--no-chrome", "--restricted", "--safe-mode", "--effort", effort, "--input-format", "stream-json"]


def expected(prompt=PROMPT, effort="medium"):
    return {"version": 1, "cli_path": CLI, "model": "claude-opus-5-5", "reasoning": effort,
            "prompt_hash": sha(prompt), "cwd": CWD, "tools": list(TOOLS)}


def replace_flag(argv, flag, value):
    changed = list(argv)
    changed[changed.index(flag) + 1] = value
    return changed


class QueryDispatchTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(validate_query_dispatch, "The closed query dispatch validator is not implemented")

    def validate(self, argv=None, **boundary):
        argv = command() if argv is None else argv
        return validate_query_dispatch(argv, **{"command_line": subprocess.list2cmdline(argv), "executable": None,
                                                "cwd": CWD, "creationflags": FLAGS, "expected": expected(), **boundary})

    def test_actual_fixture_only_shared_operation_options_match_version_two_policy(self):
        # OperationProfile delegates to this unbound TrialProfile with an empty
        # FixtureBroker. Test actual shared options/SDK serialization, without
        # claiming an operation workspace, native dispatch or role authorization.
        for effort in ('medium', 'high'):
            profile = TrialProfile({'provider': 'anthropic-cli', 'model': 'claude-opus-5-5',
                'reasoning': effort, 'cli_path': CLI, 'sdk_version': '0.2.116'},
                FixtureBroker([], 'a' * 64), PROMPT)
            options = profile.options(SimpleNamespace(session_id=None, cwd=CWD, _on_stderr=lambda _: None))
            options = replace(options, permission_prompt_tool_name='stdio')
            transport = SubprocessCLITransport(prompt='', options=options)
            args = transport._build_command()
            pin = expected(effort=effort) | {'version': 2, 'tool_policy': 'fixture_only', 'tools': TOOLS[:1]}
            with self.subTest(effort=effort):
                result = self.validate(args, expected=pin)
                self.assertEqual(result['tools'], TOOLS[:1])
                self.assertEqual(result['tool_policy'], 'fixture_only')
                self.assertEqual(result['reasoning'], effort)

    def test_exact_closed_command_returns_only_sanitized_consistency_evidence(self):
        argv = command()
        result = self.validate(argv)
        self.assertEqual(set(result), {"version", "verdict", "basis", "model", "reasoning", "prompt_hash", "tools",
                                       "argv_hash", "command_line_hash", "cli_path_hash", "cwd_hash", "settings_hash",
                                       "mcp_config_hash", "expected_hash", "creationflags", "coverage"})
        self.assertEqual((result["version"], result["verdict"], result["basis"]), (1, "pass", "query_argument_consistency"))
        self.assertEqual((result["model"], result["reasoning"], result["prompt_hash"], result["tools"]),
                         ("claude-opus-5-5", "medium", sha(PROMPT), TOOLS))
        self.assertEqual(result["argv_hash"], sha(canonical(argv)))
        self.assertEqual(result["command_line_hash"], sha(subprocess.list2cmdline(argv)))
        self.assertEqual(result["cli_path_hash"], sha(CLI))
        self.assertEqual(result["cwd_hash"], sha(CWD))
        self.assertEqual(result["settings_hash"], sha(canonical({"fastMode": False, "disableAllHooks": True})))
        self.assertEqual(result["mcp_config_hash"], sha(canonical(MCP)))
        self.assertEqual(result["expected_hash"], sha(canonical(expected())))
        self.assertEqual(result["creationflags"], FLAGS)
        self.assertEqual(result["coverage"], {"os_boundary": "unknown", "image": "unknown",
                                               "provider_acceptance": "unknown", "internal_reasoning": "unknown"})
        serialized = canonical(result)
        for forbidden in (PROMPT, CLI, CWD, "--system-prompt", "--settings", "mcpServers"):
            self.assertNotIn(forbidden, serialized)

    def test_two_efforts_and_unicode_quotes_newlines_keep_exact_prompt_hashes(self):
        for effort in ("medium", "high"):
            for prompt in (PROMPT, "", 'Line\n"quoted" \\末尾 😀\t'):
                with self.subTest(effort=effort, prompt=prompt):
                    result = self.validate(command(prompt, effort), expected=expected(prompt, effort))
                    self.assertEqual(result["reasoning"], effort)
                    self.assertEqual(result["prompt_hash"], sha(prompt))

    def test_actual_bound_v3_profile_and_sdk116_command_builder_match_the_pure_grammar(self):
        # The real workspace, binding and options are produced on the current OS.
        # Only after that, fixed Windows paths replace cli_path/cwd for this pure
        # serialization fixture. stdio mirrors SDKClient's automatic replacement.
        for effort in ("medium", "high"):
            with self.subTest(effort=effort), tempfile.TemporaryDirectory(prefix="query-dispatch-") as scratch:
                root = Path(scratch)
                value = make_manifest() | {"version": 3}
                value["baseline_context"] = {"content": PROMPT, "hash": sha(PROMPT), "coverage": "complete"}
                pin = {"provider": "anthropic-cli", "model": "claude-opus-5-5", "reasoning": effort,
                       "cli_path": str(root / "never-executed.exe"), "sdk_version": "0.2.116"}
                value["engine_config_hash"] = _hash(pin)
                workspaces = TrialWorkspace(root / "workspaces")
                receipt = workspaces.prepare("query-fixture", 1, value)
                try:
                    profile = TrialProfile(pin, FixtureBroker(value["case"]["fixtures"], value["grant_hash"]),
                                           trial_system_prompt(value))
                    profile.bind_installation(value, receipt, "c" * 64)
                    options = profile.options(SimpleNamespace(session_id=None, cwd=receipt["path"], _on_stderr=lambda _: None))
                    self.assertIsNotNone(options.can_use_tool)
                    self.assertEqual(options.allowed_tools, TOOLS)
                    options = replace(options, cli_path=CLI, cwd=CWD, permission_prompt_tool_name="stdio")
                    with patch.object(SubprocessCLITransport, "_find_cli", side_effect=AssertionError("CLI lookup forbidden")), \
                            patch.object(SubprocessCLITransport, "connect", side_effect=AssertionError("Connect forbidden")), \
                            patch("anyio.open_process", side_effect=AssertionError("Process forbidden")):
                        transport = SubprocessCLITransport(prompt="", options=options)
                        argv = transport._build_command()
                        result = self.validate(argv, expected=expected(options.system_prompt, effort))
                    self.assertEqual(result["prompt_hash"], sha(trial_system_prompt(value)))
                    self.assertEqual(result["reasoning"], effort)
                finally:
                    workspaces.cleanup("query-fixture", 1)

    def test_raw_command_line_executable_cwd_and_creationflags_must_match_exactly(self):
        for override in ({"command_line": subprocess.list2cmdline(command()) + " "},
                         {"command_line": subprocess.list2cmdline(command()).replace("--verbose", "--verbose ")},
                         {"command_line": None}, {"executable": CLI}, {"executable": ""},
                         {"cwd": CWD.lower()}, {"cwd": "D:\\other"}, {"cwd": Path(CWD)},
                         {"creationflags": FLAGS | 0x200}, {"creationflags": FLAGS ^ 4},
                         {"creationflags": True}, {"creationflags": float(FLAGS)}):
            with self.subTest(override=override), self.assertRaises(ValueError):
                self.validate(**override)

    def test_cli_path_must_equal_pin_without_windows_case_or_path_normalization(self):
        for path in (CLI.lower(), r"C:\Trusted Tools\Claude\..\Claude\claude.exe", r"C:\foreign\claude.exe"):
            with self.subTest(path=path), self.assertRaises(ValueError):
                self.validate([path, *command()[1:]])

    def test_relative_drive_relative_and_posix_paths_are_refused_even_when_pinned(self):
        for path in ("claude.exe", r"C:claude.exe", r"\claude.exe", "/usr/bin/claude"):
            pin = expected() | {"cli_path": path}
            with self.subTest(path=path), self.assertRaises(ValueError):
                self.validate([path, *command()[1:]], expected=pin)
            with self.subTest(cwd=path), self.assertRaises(ValueError):
                self.validate(expected=expected() | {"cwd": path}, cwd=path)

    def test_changed_model_effort_prompt_or_tool_inventory_cannot_match_selected_pin(self):
        for flag, value in (("--model", "claude-other"), ("--effort", "low"), ("--system-prompt", PROMPT + "extra"),
                            ("--tools", "Read"), ("--allowedTools", ",".join(reversed(TOOLS))),
                            ("--allowedTools", ",".join(TOOLS + ["Bash"])), ("--permission-mode", "bypassPermissions"),
                            ("--permission-prompt-tool", "foreign"), ("--output-format", "json"), ("--input-format", "text")):
            with self.subTest(flag=flag, value=value), self.assertRaises(ValueError):
                self.validate(replace_flag(command(), flag, value))

    def test_unknown_duplicate_missing_reordered_or_override_flags_are_refused(self):
        for suffix in (["--model", "claude-other"], ["--effort", "max"], ["--resume", "session"],
                       ["--fallback-model", "other"], ["--thinking", "adaptive"], ["--max-thinking-tokens", "8"],
                       ["--include-partial-messages"], ["--include-hook-events"], ["--plugin-dir", "private"],
                       ["--append-system-prompt", "override"], ["--system-prompt-file", "private"], ["--continue"]):
            with self.subTest(suffix=suffix), self.assertRaises(ValueError):
                self.validate(command() + suffix)
        for index in (3, 20, 21, 22, 23, 24, 25, 26):
            with self.subTest(missing=index), self.assertRaises(ValueError):
                self.validate(command()[:index] + command()[index + 1:])
        changed = command()
        changed[-4:-2], changed[-2:] = changed[-2:], changed[-4:-2]
        with self.assertRaises(ValueError):
            self.validate(changed)

    def test_settings_are_inline_duplicate_free_closed_and_strict_boolean(self):
        invalid = ["settings.json", "{}", "[]", "null", "{", '{"fastMode":false,"disableAllHooks":true,"fastMode":false}',
                   '{"fastMode":0,"disableAllHooks":true}', '{"fastMode":false,"disableAllHooks":1}',
                   '{"fastMode":true,"disableAllHooks":true}', '{"fastMode":false,"disableAllHooks":false}',
                   '{"fastMode":false,"disableAllHooks":true,"hooks":{}}',
                   '{"fastMode":NaN,"disableAllHooks":true}']
        for settings in invalid:
            with self.subTest(settings=settings), self.assertRaises(ValueError):
                self.validate(replace_flag(command(), "--settings", settings))

    def test_mcp_configuration_rejects_external_extra_malformed_and_duplicate_servers(self):
        invalid = ["mcp.json", "[]", "null", "{}", canonical({"mcpServers": {"fixture": MCP["mcpServers"]["fixture"]}}),
                   canonical(MCP | {"extra": True}),
                   '{"mcpServers":{"fixture":{"type":"sdk","name":"fixture","name":"fixture"},"skill":{"type":"sdk","name":"skill"}}}',
                   '{"mcpServers":{},"mcpServers":{}}']
        for descriptor in ({"type": "http", "url": "https://external.invalid"}, {"type": "sdk", "name": "foreign"},
                           {"type": "sdk", "name": "skill", "version": "1"}, {"type": True, "name": "skill"},
                           {"type": "sdk", "name": "skill", "instance": "secret"}):
            changed = copy.deepcopy(MCP)
            changed["mcpServers"]["skill"] = descriptor
            invalid.append(canonical(changed))
        changed = copy.deepcopy(MCP)
        changed["mcpServers"]["foreign"] = {"type": "sdk", "name": "foreign"}
        invalid.append(canonical(changed))
        for mcp in invalid:
            with self.subTest(mcp=mcp), self.assertRaises(ValueError):
                self.validate(replace_flag(command(), "--mcp-config", mcp))

    def test_nonempty_or_alternative_setting_sources_are_refused(self):
        for token in ("--setting-sources=user", "--setting-sources=user,project", "--setting-sources", "--setting-sources= "):
            changed = command()
            changed[changed.index("--setting-sources=")] = token
            with self.subTest(token=token), self.assertRaises(ValueError):
                self.validate(changed)

    def test_pin_schema_version_types_hashes_and_exact_two_tool_list_are_strict(self):
        variants = [None, [], expected() | {"extra": True}, expected() | {"version": True},
                    expected() | {"version": 1.0}, expected() | {"version": 2}, expected() | {"reasoning": "auto"},
                    expected() | {"reasoning": True}, expected() | {"model": ""}, expected() | {"model": "--override"},
                    expected() | {"prompt_hash": "A" * 64}, expected() | {"tools": tuple(TOOLS)},
                    expected() | {"tools": list(reversed(TOOLS))}, expected() | {"tools": TOOLS + ["Bash"]}]
        for key in expected():
            variants.append({name: value for name, value in expected().items() if name != key})
        for pin in variants:
            with self.subTest(pin=pin), self.assertRaises(ValueError):
                self.validate(expected=pin)

    def test_nul_surrogates_non_string_argv_and_flaglike_prompts_fail_without_repair(self):
        for prompt in ("--model=other", "-p", "nul\x00data"):
            with self.subTest(prompt=repr(prompt)), self.assertRaises(ValueError):
                self.validate(command(prompt), expected=expected(prompt))
        with self.assertRaises(ValueError):
            self.validate(command("bad\ud800value"))
        for argv in (None, (), tuple(command()), [*command()[:-1], 1], [*command()[:-1], b"stream-json"]):
            with self.subTest(argv=argv), self.assertRaises(ValueError):
                validate_query_dispatch(argv, command_line="", executable=None, cwd=CWD, creationflags=FLAGS, expected=expected())
        with self.assertRaises(ValueError):
            self.validate(command_line="raw\x00line")
        with self.assertRaises(ValueError):
            self.validate(command_line="raw\ud800line")

    def test_windows_command_limit_counts_utf16_units_including_astral_characters(self):
        overhead = len(subprocess.list2cmdline(command("x"))) - 1
        prompt = "😀" + "x" * (32766 - overhead - 2)
        argv = command(prompt)
        self.assertEqual(len(subprocess.list2cmdline(argv).encode("utf-16-le")) // 2, 32766)
        self.assertEqual(self.validate(argv, expected=expected(prompt))["prompt_hash"], sha(prompt))
        with self.assertRaises(ValueError):
            self.validate(command(prompt + "x"), expected=expected(prompt + "x"))

    def test_caller_mutation_does_not_change_inputs_or_previous_sanitized_results(self):
        argv, pin = command(), expected()
        before_argv, before_pin = list(argv), copy.deepcopy(pin)
        result = self.validate(argv, expected=pin)
        self.assertEqual(argv, before_argv)
        self.assertEqual(pin, before_pin)
        original = copy.deepcopy(result)
        argv.clear()
        pin["tools"].clear()
        self.assertEqual(result, original)
        result["tools"].clear()
        result["coverage"].clear()
        self.assertEqual(self.validate(), original)

    def test_pure_validator_never_reads_files_connects_or_starts_a_process(self):
        argv = command()
        with ExitStack() as stack:
            for target in ("builtins.open", "pathlib.Path.resolve", "pathlib.Path.read_text", "pathlib.Path.read_bytes",
                           "subprocess.Popen", "subprocess.run", "anyio.open_process", "socket.create_connection"):
                stack.enter_context(patch(target, side_effect=AssertionError("External access forbidden")))
            self.assertEqual(self.validate(argv)["basis"], "query_argument_consistency")
            with self.assertRaises(ValueError):
                self.validate(replace_flag(argv, "--model", "foreign"))


if __name__ == "__main__":
    unittest.main()
