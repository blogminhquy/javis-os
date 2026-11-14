"""Copy docker/guard.py into the `guard` service of the compose files that carry it.

    python tools/sync_guard.py          # rewrite the inline copies
    python tools/sync_guard.py --check  # exit 1 when a copy differs (tests/python/test_update_guard.py)

Why inline: on Hostinger the owner pastes ONE compose URL and nothing else reaches the server, so
the guard's code has to travel inside the compose file itself, the way the gateway's script does.
docker/guard.py stays the one place to edit, so the tests can import and exercise it.

Why a COMPACT copy (no docstrings, no comments, no blank lines, two-space indent): hPanel's compose
editor refuses to deploy more than 32,768 characters, and the full copy pushed
docker-compose.hostinger.yml past it (owner report 2026-11-14: Deploy blocked even for a one-line
edit). The explanations stay in docker/guard.py; tests/python/test_update_guard.py proves the
compact copy is the same program, and tests/python/test_hostinger_compose_size.py keeps the file
under the limit.
"""
import ast
import io
import sys
import tokenize
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "docker" / "guard.py"
COMPOSE_FILES = ("docker-compose.yml", "docker-compose.hostinger.yml")
# The script is the only item of the guard service's `command`, written as a YAML literal block.
OPENER = '    entrypoint: ["python", "-u", "-c"]\n    command:\n      - |\n'
INDENT = " " * 8


def docstring_lines(script: str) -> set:
    """Line numbers taken by the docstrings of the module, its classes and its functions."""
    lines = set()
    for node in ast.walk(ast.parse(script)):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and node.body:
            first = node.body[0]
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) \
                    and isinstance(first.value.value, str):
                lines.update(range(first.lineno, first.end_lineno + 1))
    return lines


def compact(script: str) -> str:
    """The same program with docstrings, comments and blank lines dropped and the indent halved."""
    comments = {tok.start[0]: tok.start[1]
                for tok in tokenize.generate_tokens(io.StringIO(script).readline)
                if tok.type == tokenize.COMMENT}
    docs = docstring_lines(script)
    out = []
    for number, line in enumerate(script.splitlines(), 1):
        if number in docs:
            continue
        line = line[:comments[number]].rstrip() if number in comments else line.rstrip()
        if line:
            body = line.lstrip(" ")
            out.append(" " * ((len(line) - len(body)) // 2) + body)
    return "\n".join(out) + "\n"


def inline_block() -> str:
    script = SOURCE.read_text(encoding="utf-8")
    if "$" in script:
        raise SystemExit("docker/guard.py must not contain '$': compose would read it as a variable")
    return "".join(INDENT + line for line in compact(script).splitlines(keepends=True))


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
