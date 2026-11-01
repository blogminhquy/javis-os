"""Interactive Codex chat should not silently lose the Javis Hub on MCP startup.

Focus: argument construction only, no network / Codex binary / live task writes.
    python tests/run.py codex_chat_hub_required
"""
from _paths import SERVER  # noqa: F401
from claude_cli import CodexCLI
import codex_steer
import mcp_hub


def flags(argv):
    return [argv[i + 1] for i, v in enumerate(argv[:-1]) if v == "-c"]


def ready(argv):
    return [x for x in flags(argv) if x.startswith(mcp_hub.CODEX_REQUIRED_KEY + "=")]


def cli(profile="javis", hub_turn=True, extra=None):
    c = CodexCLI(cwd=".", tag="chat", model="gpt-test")
    c.cli_path = "codex"
    c.transport = "ws"
    c.profile = profile
    c.hub_turn = hub_turn
    c.extra_config = list(extra or [])
    return c


fails = []


def check(desc, yes):
    print(("ok   " if yes else "FAIL ") + desc)
    if not yes:
        fails.append(desc)


# Do not create a profile or touch real credentials. The app-server consumes
# exactly the fake profile lines below; exec just forwards its -p name.
old_profile = codex_steer.profile_overrides
codex_steer.profile_overrides = lambda *args: [
    'mcp_servers.javis.url="http://127.0.0.1:7777/hub/mcp"',
    "mcp_servers.javis.startup_timeout_sec=20",
]
try:
    c = cli(extra=[
        "model_reasoning_effort=medium",
        f"{mcp_hub.CODEX_REQUIRED_KEY}=false",
    ])
    for name, argv in (
        ("exec", c._build_args()),
        ("app-server", codex_steer._args(c, None)),
    ):
        check(name + ": exactly one true required flag",
              ready(argv) == [f"{mcp_hub.CODEX_REQUIRED_KEY}=true"])
        check(name + ": other configuration preserved",
              "model_reasoning_effort=medium" in flags(argv))
        check(name + ": expected command used",
              ("exec" in argv if name == "exec" else argv[-1] == "app-server"))
        if name == "app-server":
            check("app-server: timeout inherited from profile",
                  "mcp_servers.javis.startup_timeout_sec=20" in flags(argv))
    check("shared extra_config is not modified",
          c.extra_config[-1] == f"{mcp_hub.CODEX_REQUIRED_KEY}=false")

    for description, c in (
        ("no Hub assigned", cli(profile=None, hub_turn=True)),
        ("Hub not marked as turn-scoped", cli(profile="javis", hub_turn=False)),
    ):
        check(description + ": exec remains unmodified", not ready(c._build_args()))
        check(description + ": app-server remains unmodified",
              not ready(codex_steer._args(c, None)))
    bg = cli(hub_turn=False, extra=[f"{mcp_hub.CODEX_REQUIRED_KEY}=true"])
    check("background override preserved", ready(bg._build_args()) ==
          [f"{mcp_hub.CODEX_REQUIRED_KEY}=true"])
finally:
    codex_steer.profile_overrides = old_profile

if fails:
    raise SystemExit(f"{len(fails)} FAIL")
print("PASS: interactive Codex MCP startup policy on exec and app-server")
