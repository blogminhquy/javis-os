"""Release must refresh Codex even when the Docker install layer was cached."""
from _paths import ROOT
import os
from pathlib import Path
import shutil
import subprocess

docker = (ROOT / "Dockerfile").read_text(encoding="utf-8")
workflow = (ROOT / ".github/workflows/docker-publish.yml").read_text(encoding="utf-8")
assert "ARG CODEX_CLI_VERSION=" in docker
assert "@openai/codex@${CODEX_CLI_VERSION}" in docker
assert "npm view @openai/codex@latest version" in workflow
assert "CODEX_CLI_VERSION=${{ env.CODEX_CLI_VERSION }}" in workflow

# Execute the actual installer function with an already installed codex.
# The old early return would skip npm entirely in this scenario.
bash = shutil.which("bash")
if not bash and os.name == "nt":
    candidate = Path("C:/Program Files/Git/bin/bash.exe")
    if candidate.exists():
        bash = str(candidate)
assert bash, "bash required for installer regression"
source = (ROOT / "install.sh").read_text(encoding="utf-8")
function = source[source.index("cai_them_cli() {"):]
function = function[:function.index("\n}") + 2]
script = '''
set -e
log() { :; }
ok() { :; }
warn() { :; }
codex() { echo old-cli; }
npm() { echo "NPM:$*" >&2; }
SUDO=""
''' + function + '\ncai_them_cli @openai/codex@latest codex "Codex CLI"\n'
# npm's output is redirected by the installer; record calls in a shell variable
# through a file descriptor that isn't redirected.
script = script.replace('echo "NPM:$*" >&2', 'echo "NPM:$*" >&3')
result = subprocess.run([bash, "-c", "exec 3>&1\n" + script],
                        capture_output=True, text=True, timeout=15)
assert result.returncode == 0, result.stderr
assert "NPM:install -g @openai/codex@latest" in result.stdout, result.stdout
for filename in ("install.sh", "update.sh"):
    result = subprocess.run([bash, "-n", str(ROOT / filename)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
print("ok: release cache key, installed CLI upgrade, shell syntax")
