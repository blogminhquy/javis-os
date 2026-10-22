"""Windows: child processes print UTF-8 (0.271.0, customer report codes 5 and 22).

    python tests/python/test_windows_child_utf8_0271.py

A Team member on Windows ran a Python one-liner that printed Vietnamese sheet names and died with UnicodeEncodeError
(cp1252). Every engine CLI Javis starts inherits the server environment, so config sets PYTHONUTF8 and
PYTHONIOENCODING there on Windows, at import time, keeping any value the user set.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import os
import subprocess
import sys
import tempfile

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-utf8-"))

import config  # noqa: E402

fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (f"  [{extra}]" if extra and not cond else ""))
    if not cond:
        fails.append(name)


env = config.child_utf8_env({}, os_name="nt")
check("windows: UTF-8 mode and IO encoding are set for children",
      env.get("PYTHONUTF8") == "1" and env.get("PYTHONIOENCODING") == "utf-8", env)
env = config.child_utf8_env({"PYTHONUTF8": "0", "PYTHONIOENCODING": "cp1258"}, os_name="nt")
check("windows: a value the user set is kept", env == {"PYTHONUTF8": "0", "PYTHONIOENCODING": "cp1258"}, env)
check("other systems: nothing changes", config.child_utf8_env({}, os_name="posix") == {})
src = (SERVER / "config.py").read_text(encoding="utf-8")
check("applied at import time and from apply_tool_env",
      "\nchild_utf8_env()\n" in src and "    child_utf8_env()\n" in src)

# What the setting does: a child Python writing Vietnamese to a pipe under a cp1252 locale.
code = "print('Tổng hợp - Chi tiết - Đánh giá')"
base = {k: v for k, v in os.environ.items() if not k.startswith("PYTHON")}
bad = subprocess.run([sys.executable, "-c", code], capture_output=True, env=dict(base, PYTHONIOENCODING="cp1252"))
good = subprocess.run([sys.executable, "-c", code], capture_output=True,
                      env=config.child_utf8_env(dict(base, PYTHONIOENCODING=""), os_name="nt"))
check("cp1252 output really fails on Vietnamese (the reported error)", bad.returncode != 0
      and b"UnicodeEncodeError" in bad.stderr, bad.stderr[-200:])
check("with the child env the same print succeeds in UTF-8", good.returncode == 0
      and good.stdout.decode("utf-8").strip() == "Tổng hợp - Chi tiết - Đánh giá", good.stderr[-200:])

print()
if fails:
    print(f"FAIL - {len(fails)} check(s)")
    raise SystemExit(1)
print("OK - test_windows_child_utf8_0271: all pass")
