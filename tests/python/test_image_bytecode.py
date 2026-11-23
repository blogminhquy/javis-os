"""The Docker image ships bytecode for server/ (speed review 2026-11-23).

The image sets PYTHONDONTWRITEBYTECODE=1 and keeps /app read-only, so the running server can never write a .pyc. Without
a compile step at build time every start recompiled all of server/: `import main` measured 20.4 s from source against
7.2 s with bytecode on a 2 vCPU machine, about 13 seconds of unreachable dashboard on every restart and update.

Expected:
  - the Dockerfile compiles server/ after the source is copied in and before it drops to the unprivileged user;
  - `python -m compileall` writes .pyc files even with PYTHONDONTWRITEBYTECODE=1 (the claim the step relies on);
  - an import under PYTHONDONTWRITEBYTECODE=1 then loads that file instead of compiling the source again.

Run:
    python tests/run.py image_bytecode
"""
from _paths import ROOT  # noqa: E402,F401  - also points the temp dir at a private folder
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        fails.append(name)


# Comment lines are dropped first: a step that is only described in a comment must not count as present.
lines = [ln for ln in (ROOT / "Dockerfile").read_text(encoding="utf-8").splitlines() if not ln.lstrip().startswith("#")]
body = "\n".join(lines)
step = re.search(r"^RUN\s+python\s+-m\s+compileall\b[^\n]*\bserver\b", body, re.M)
copy = re.search(r"^COPY \. \.$", body, re.M)
user = re.search(r"^USER\s+javis\b", body, re.M)
check("the Dockerfile has a `RUN python -m compileall ... server` step", bool(step))
check("the step runs after the source is copied in", bool(step and copy and copy.start() < step.start()))
check("the step runs before the image drops to the unprivileged user (root owns /app)",
      bool(step and user and step.start() < user.start()))
check("the image still stops the running server writing bytecode (so the build step is the only source)",
      "PYTHONDONTWRITEBYTECODE=1" in body)

# The claim the step relies on, checked for real on a throwaway package.
tmp = Path(tempfile.mkdtemp(prefix="javis-image-bytecode-"))
pkg = tmp / "server"
pkg.mkdir()
(pkg / "sample_module.py").write_text("VALUE = 41 + 1\n", encoding="utf-8")
env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
env.pop("PYTHONPYCACHEPREFIX", None)
done = subprocess.run([sys.executable, "-m", "compileall", "-q", "server"], cwd=str(tmp), env=env,
                      capture_output=True, text=True)
compiled = list((pkg / "__pycache__").glob("sample_module.*.pyc")) if (pkg / "__pycache__").is_dir() else []
check("compileall exits 0", done.returncode == 0)
check("compileall writes the .pyc although PYTHONDONTWRITEBYTECODE=1", len(compiled) == 1)

# With the source unreadable as Python, only the compiled file can answer: mtime and size are kept so it stays valid.
src = pkg / "sample_module.py"
st = src.stat()
src.write_text("VALUE = (broken\n".ljust(st.st_size, "#")[:st.st_size], encoding="utf-8")
os.utime(src, ns=(st.st_atime_ns, st.st_mtime_ns))
probe = subprocess.run([sys.executable, "-c", "import sample_module; print(sample_module.VALUE)"],
                       cwd=str(pkg), env=env, capture_output=True, text=True)
check(f"an import under PYTHONDONTWRITEBYTECODE=1 loads the compiled file ({probe.stdout.strip()!r})",
      probe.returncode == 0 and probe.stdout.strip() == "42")

print()
if fails:
    print(f"FAIL {len(fails)}: " + ", ".join(fails))
    sys.exit(1)
print("ALL PASS")
