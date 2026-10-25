"""Pure, closed SDK116 Windows query argument consistency validation."""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import PureWindowsPath


_FLAGS = 0x08000006  # CREATE_NO_WINDOW | CREATE_SUSPENDED | DEBUG_ONLY_THIS_PROCESS
_TOOLS = ("mcp__fixture__fixture_read", "mcp__skill__skill_asset_read")
_POLICIES = {"fixture_only": (_TOOLS[:1], ("fixture",)), "pinned_skill": (_TOOLS, ("fixture", "skill")),
             "baseline_inline": (_TOOLS[:1], ("fixture",))}
_PIN_FIELDS = {"version", "cli_path", "model", "reasoning", "prompt_hash", "cwd", "tools"}
_EFFORTS = ("low", "medium", "high", "xhigh", "max")
# Literal tokens and named single-value positions in SDK116 _build_command.
# An exact shape rejects duplicates, reordering, alternate syntax and overrides.
_GRAMMAR = (
    ("cli_path",), "--output-format", "stream-json", "--verbose", "--system-prompt", ("prompt",),
    "--tools", "", "--allowedTools", ("allowed_tools",), "--model", ("model",),
    "--permission-prompt-tool", "stdio", "--permission-mode", "default",
    "--settings", ("settings",), "--mcp-config", ("mcp_config",), "--strict-mcp-config", "--setting-sources=",
    "--no-session-persistence", "--disable-slash-commands", "--no-chrome", "--restricted", "--safe-mode",
    "--effort", ("reasoning",), "--input-format", "stream-json",
)


def _invalid():
    # Never attach a raw prompt, command, settings value or path to the error.
    raise ValueError("invalid_query_dispatch")


def _text(value):
    if type(value) is not str or "\x00" in value:
        _invalid()
    try:
        value.encode("utf-16-le")
    except UnicodeEncodeError:
        _invalid()
    return value


def _windows_absolute(value):
    _text(value)
    if not PureWindowsPath(value).is_absolute():
        _invalid()


def _sha(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _hash(value):
    return _sha(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False))


def _strict_json(value):
    def pairs(items):
        result = {}
        for key, item in items:
            if key in result:
                _invalid()
            result[key] = item
        return result

    def constant(_):
        _invalid()

    try:
        return json.loads(value, object_pairs_hook=pairs, parse_constant=constant)
    except (ValueError, RecursionError):
        raise ValueError("invalid_query_dispatch") from None


def validate_query_dispatch(argv, *, command_line, executable, cwd, creationflags, expected):
    """Validate supplied Windows query inputs; return sanitized consistency only.

    ``expected`` is a closed pin with cli_path, selected model/reasoning,
    raw UTF-8 prompt_hash, workspace cwd and the exact tools list. Version1 keeps
    the fixture/skill inventory and result bytes. Version2 adds tool_policy:
    fixture_only for the existing operation inventory, or pinned_skill for the
    two readonly tools. baseline_inline has only the fixture tool for the native
    baseline bundle. This grammar choice does not authorize a role or launch.
    Only the installed SDK116 trial query grammar is supported, including its
    SDKClient stdio permission-prompt option. The raw Windows command must equal
    subprocess.list2cmdline(argv), executable must be None, and creationflags must
    be exactly the hidden/suspended/debug-only flags. No argument is repaired or
    path normalized; flag-like literal prompt values are unsupported.

    Invalid inputs raise ValueError with a generic message. Success contains only
    selected model/effort/tools, values/hashes and explicit unknown coverage for
    the OS boundary, image, provider acceptance and internal reasoning. Hashes
    bind the supplied raw argv/command and pins without returning their contents.
    This pure function never reads files, creates a client or starts a process.
    Calling it with an asserted capture does not prove an OS event happened.
    Runtime interception, image/lifetime proof and session binding are separate.
    """
    if (type(expected) is not dict or any(type(key) is not str for key in expected)
            or type(expected.get("version")) is not int or expected["version"] not in (1, 2)):
        _invalid()
    version = expected["version"]
    if set(expected) != _PIN_FIELDS | ({"tool_policy"} if version == 2 else set()):
        _invalid()
    pin = dict(expected)
    policy = pin["tool_policy"] if version == 2 else "pinned_skill"
    if type(policy) is not str or policy not in _POLICIES:
        _invalid()
    tools, servers = _POLICIES[policy]
    for name in ("cli_path", "model", "reasoning", "prompt_hash", "cwd"):
        _text(pin[name])
    if (not pin["model"] or pin["model"].startswith("-") or pin["reasoning"] not in _EFFORTS
            or re.fullmatch(r"[0-9a-f]{64}", pin["prompt_hash"]) is None
            or type(pin["tools"]) is not list or any(type(tool) is not str for tool in pin["tools"])
            or pin["tools"] != list(tools)):
        _invalid()
    pin["tools"] = list(pin["tools"])
    _windows_absolute(pin["cli_path"])
    _windows_absolute(pin["cwd"])
    if (type(argv) is not list or len(argv) != len(_GRAMMAR) or executable is not None
            or type(creationflags) is not int or creationflags != _FLAGS):
        _invalid()
    actual_argv = list(argv)
    for value in actual_argv:
        _text(value)
    _text(command_line)
    _text(cwd)
    if (cwd != pin["cwd"] or len(command_line.encode("utf-16-le")) // 2 > 32766
            or subprocess.list2cmdline(actual_argv) != command_line):
        _invalid()
    selected = {}
    for actual, token in zip(actual_argv, _GRAMMAR):
        if type(token) is tuple:
            selected[token[0]] = actual
        elif actual != token:
            _invalid()
    if (selected["cli_path"] != pin["cli_path"] or selected["model"] != pin["model"]
            or selected["reasoning"] != pin["reasoning"] or selected["allowed_tools"] != ",".join(tools)
            or selected["prompt"].startswith("-") or _sha(selected["prompt"]) != pin["prompt_hash"]):
        _invalid()
    settings = _strict_json(selected["settings"])
    if (type(settings) is not dict or set(settings) != {"fastMode", "disableAllHooks"}
            or settings["fastMode"] is not False or settings["disableAllHooks"] is not True):
        _invalid()
    mcp = _strict_json(selected["mcp_config"])
    if (type(mcp) is not dict or set(mcp) != {"mcpServers"} or type(mcp["mcpServers"]) is not dict
            or set(mcp["mcpServers"]) != set(servers)):
        _invalid()
    for name, descriptor in mcp["mcpServers"].items():
        if (type(descriptor) is not dict or set(descriptor) != {"type", "name"}
                or type(descriptor["type"]) is not str or descriptor["type"] != "sdk"
                or type(descriptor["name"]) is not str or descriptor["name"] != name):
            _invalid()
    result = {"version": version, "verdict": "pass", "basis": "query_argument_consistency", "model": selected["model"],
            "reasoning": selected["reasoning"], "prompt_hash": pin["prompt_hash"], "tools": list(tools),
            "argv_hash": _hash(actual_argv), "command_line_hash": _sha(command_line),
            "cli_path_hash": _sha(pin["cli_path"]), "cwd_hash": _sha(cwd), "settings_hash": _hash(settings),
            "mcp_config_hash": _hash(mcp), "expected_hash": _hash(pin), "creationflags": creationflags,
            "coverage": {"os_boundary": "unknown", "image": "unknown", "provider_acceptance": "unknown",
                         "internal_reasoning": "unknown"}}
    if version == 2:
        result["tool_policy"] = policy
    return result
