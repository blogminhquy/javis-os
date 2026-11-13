"""Copy docker/guard.py into the `guard` service of the compose files that carry it.

    python tools/sync_guard.py          # rewrite the inline copies
    python tools/sync_guard.py --check  # exit 1 when a copy differs (tests/python/test_update_guard.py)

Why inline: on Hostinger the owner pastes ONE compose URL and nothing else reaches the server, so
the guard's code has to travel inside the compose file itself, the way the gateway's script does.
docker/guard.py stays the one place to edit, so the tests can import and exercise it.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "docker" / "guard.py"
COMPOSE_FILES = ("docker-compose.yml", "docker-compose.hostinger.yml")
# The script is the only item of the guard service's `command`, written as a YAML literal block.
OPENER = '    entrypoint: ["python", "-u", "-c"]\n    command:\n      - |\n'
INDENT = " " * 8


def inline_block() -> str:
    script = SOURCE.read_text(encoding="utf-8")
    if "$" in script:
        raise SystemExit("docker/guard.py must not contain '$': compose would read it as a variable")
    return "".join(INDENT + line if line.strip() else "\n" for line in script.splitlines(keepends=True))


def synced(text: str, name: str) -> str:
    start = text.find(OPENER)
    if start < 0 or text.find(OPENER, start + 1) >= 0:
        raise SystemExit(f"{name}: expected exactly one guard service command block")
    body = start + len(OPENER)
    taken = 0   # the block runs on while lines are blank or indented under the `- |`
    for line in text[body:].splitlines(keepends=True):
        if line.strip() and not line.startswith(INDENT):
            break
        taken += len(line)
    block = text[body:body + taken]
    # Blank lines at its end separate it from the next section: they stay where they are.
    trailing = block[len(block.rstrip("\n")) + 1:] if block.strip() else block
    return text[:body] + inline_block() + trailing + text[body + taken:]


def main() -> int:
    check = "--check" in sys.argv[1:]
    stale = []
    for name in COMPOSE_FILES:
        path = ROOT / name
        text = path.read_text(encoding="utf-8")
        new = synced(text, name)
        if new != text:
            stale.append(name)
            if not check:
                path.write_text(new, encoding="utf-8")
    if check and stale:
        print("guard script differs in: " + ", ".join(stale) + ". Run: python tools/sync_guard.py")
        return 1
    print(("updated: " + ", ".join(stale)) if stale and not check else "guard script in sync")
    return 0


if __name__ == "__main__":
    sys.exit(main())
