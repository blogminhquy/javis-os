"""Docker container installs Antigravity CLI and Grok Build by itself at boot (0.85.1).

    python tests/run.py docker_tu_cai_cli     (no network: `curl` is a fake on PATH)

Why: the image ships claude and codex, but agy and grok come only from Google's and xAI's own install
scripts, so they are not baked into the public image. Docker users used to get a "CLI not installed"
card with a command to type, and people deploying through Hostinger have nowhere to type it. The
entrypoint now installs both in the background on boot.

What is guarded:
  1. The server command still runs right away (the install is in the background, never blocking).
  2. Both CLIs end up installed and the state files say "ok"; a CLI already present is not
     reinstalled; a failed download says "failed" (and the next boot retries).
  3. JAVIS_AUTO_INSTALL_CLIS=0 turns it off completely.
  4. The Models page reads those states: "installing", "failed", "ok", a stuck "installing" turns
     into "failed", and outside Docker (no state folder) the answer is "".
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

_fails = []


def check(name, cond, detail=""):
    print(("ok   " if cond else "FAIL ") + name + ("" if cond else f"  [{detail!r}]"))
    if not cond:
        _fails.append(name)


EP = ROOT / "docker" / "entrypoint.sh"

# The fake `curl`: prints an "installer" for each vendor URL, or fails for the URL marked broken.
FAKE_CURL = r"""#!/bin/sh
for a in "$@"; do url="$a"; done
case "$url" in
  *antigravity.google*)
    [ -n "$FAIL_AGY" ] && exit 22
    echo 'mkdir -p "$HOME/.local/bin" && printf "#!/bin/sh\necho agy\n" > "$HOME/.local/bin/agy" && chmod +x "$HOME/.local/bin/agy"' ;;
  *x.ai*)
    echo 'mkdir -p "$HOME/.grok/bin" && printf "#!/bin/sh\necho grok\n" > "$HOME/.grok/bin/grok" && chmod +x "$HOME/.grok/bin/grok"' ;;
  *) exit 6 ;;
esac
echo "$url" >> "$CURL_LOG"
"""


def boot(td, **extra):
    home = Path(td) / "home"
    persist = Path(td) / "data" / "home"
    fake = Path(td) / "fakebin"
    home.mkdir(parents=True, exist_ok=True)
    fake.mkdir(exist_ok=True)
    (fake / "curl").write_text(FAKE_CURL, newline="\n")
    (fake / "curl").chmod(0o755)
    # PATH holds ONLY the fake curl and the system tools: a developer machine with the real agy or
    # grok on PATH would otherwise count as "already installed" and skip the install under test.
    sysdirs = [str(Path(shutil.which(b)).parent) for b in ("sh", "bash", "mkdir", "date") if shutil.which(b)]
    env = dict(os.environ, HOME=str(home), JAVIS_HOME_PERSIST=str(persist),
               PATH=os.pathsep.join(dict.fromkeys([str(fake), *sysdirs, "/usr/bin", "/bin"])),
               CURL_LOG=str(Path(td) / "curl.log"), **extra)
    t0 = time.monotonic()
    r = subprocess.run(["sh", str(EP), "sh", "-c", "echo SERVER_UP"], env=env,
                       capture_output=True, text=True, timeout=30)
    return r, time.monotonic() - t0, home, persist / ".cli-auto-install"


def wait_done(state_dir, names, timeout=20):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        st = {n: ((state_dir / n).read_text().split() or [""])[0] if (state_dir / n).exists() else ""
              for n in names}
        if all(v in ("ok", "failed") for v in st.values()):
            return st
        time.sleep(0.2)
    return st


if os.name == "nt" or not (shutil.which("sh") and shutil.which("bash")):
    print("ok   (entrypoint part skipped: POSIX script, the image is Linux)")
else:
    with tempfile.TemporaryDirectory() as td:
        r, took, home, sd = boot(td)
        check("the server command runs right away", r.returncode == 0 and "SERVER_UP" in r.stdout, r.stderr)
        check("booting does not wait for the downloads", took < 5, took)
        st = wait_done(sd, ("agy", "grok"))
        check("both CLIs installed, state ok", st == {"agy": "ok", "grok": "ok"}, st)
        check("agy lands in ~/.local/bin, grok in ~/.grok/bin (both linked into the volume)",
              (home / ".local" / "bin" / "agy").is_file() and (home / ".grok" / "bin" / "grok").is_file())
        n = len((Path(td) / "curl.log").read_text().splitlines())
        boot(td)
        wait_done(sd, ("agy", "grok"))
        time.sleep(0.5)
        check("next boot: already installed, nothing downloaded again",
              len((Path(td) / "curl.log").read_text().splitlines()) == n)

    with tempfile.TemporaryDirectory() as td:
        r, _, home, sd = boot(td, FAIL_AGY="1")
        st = wait_done(sd, ("agy", "grok"))
        check("a failed download says failed, the other CLI still installs",
              st == {"agy": "failed", "grok": "ok"}, st)
        check("the installer output is kept for support", (sd / "install.log").is_file())

    with tempfile.TemporaryDirectory() as td:
        r, _, home, sd = boot(td, JAVIS_AUTO_INSTALL_CLIS="0")
        time.sleep(1)
        check("JAVIS_AUTO_INSTALL_CLIS=0: nothing installed, no state written",
              r.returncode == 0 and not sd.exists() and not (Path(td) / "curl.log").exists())


# ============================================================
# What the Models page reads
# ============================================================
with tempfile.TemporaryDirectory() as td:
    os.environ["JAVIS_HOME_PERSIST"] = td
    import cli_autoinstall as ca
    check("no state folder (not Docker): nothing to say", ca.state("agy") == "")
    d = Path(td) / ".cli-auto-install"
    d.mkdir()
    (d / "agy").write_text(f"installing {int(time.time())}\n")
    (d / "grok").write_text(f"installing {int(time.time()) - ca.STUCK_AFTER_S - 5}\n")
    check("fresh install in progress reads installing", ca.state("agy") == "installing")
    check("an install that never finished turns into failed", ca.state("grok") == "failed")
    (d / "agy").write_text("ok 1\n")
    (d / "grok").write_text("failed 1\n")
    check("ok and failed read as written", ca.state("agy") == "ok" and ca.state("grok") == "failed")
    (d / "agy").write_text("")
    check("an empty or garbled file says nothing", ca.state("agy") == "")
    check("the log path points into the state folder", ca.log_path().startswith(td))

print()
if _fails:
    print(f"ĐỎ {len(_fails)} mục: " + ", ".join(_fails))
    sys.exit(1)
print("Tất cả xanh.")
