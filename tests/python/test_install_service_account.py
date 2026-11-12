"""A fresh install started by root runs Javis as a regular account, not as root (owner, 2026-11-12).

    python tests/run.py install_service_account      (no network; needs bash)

At Full access Javis lets Claude Code run any command without asking, and Claude Code refuses that mode under root:
on a root install every Claude turn died with "SDK engine: ProcessError: Command failed with exit code 1". install.sh
now creates a regular account for the service, and update.sh pulls and installs as the account that owns the folder.

The block of install.sh that picks the account, and the block of update.sh that picks the owner, are cut out and run
for real in bash with the system commands (id, useradd, runuser, stat, getent, chown) replaced by shell functions, so
this runs without root. An install that already exists must never change account: that is the case most worth a test.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import subprocess
import tempfile
from pathlib import Path

_fails = []


def check(name, cond, extra=None):
    print(("ok   " if cond else "FAIL ") + name + ("" if cond or extra is None else f"  [{extra}]"))
    if not cond:
        _fails.append(name)


INSTALL = (ROOT / "install.sh").read_text(encoding="utf-8")
UPDATE = (ROOT / "update.sh").read_text(encoding="utf-8")

check("install.sh parses (bash -n)", subprocess.run(["bash", "-n", str(ROOT / "install.sh")]).returncode == 0)
check("update.sh parses (bash -n)", subprocess.run(["bash", "-n", str(ROOT / "update.sh")]).returncode == 0)

# ---- 1. install.sh: which account runs Javis ----
_start = INSTALL.index("# --- 0. Which account runs Javis ---")
_end = INSTALL.index('pick_run_user "$@"')
PICK = INSTALL[_start:_end]

STUBS = r'''
set -euo pipefail
log()  { echo "LOG $*"; }; ok() { echo "OK $*"; }; warn() { echo "WARN $*"; }; err() { echo "ERR $*" >&2; }
id() { if [ "$#" -ge 2 ]; then grep -qx "$2" "$T/users"; else echo "$FAKE_UID"; fi; }
uname() { echo "$FAKE_OS"; }
whoami() { echo "$FAKE_WHO"; }
stat() { echo "$ENV_OWNER"; }
getent() { echo "$2:x:1001:1001::/home/$2:/bin/bash"; }
useradd() { echo "CALL useradd $*"; echo "${@: -1}" >> "$T/users"; }
chown() { echo "CALL chown $*"; }
# runuser -u NAME -- env HOME=.. USER=.. LOGNAME=.. CMD...: the account cannot enter anything under $LOCKED.
runuser() {
  shift 3; shift 4
  if [ "$1" = test ]; then case "$3" in "$LOCKED"|"$LOCKED"/*) return 1;; esac; fi
  "$@"
}
exec() { echo "CALL exec $*"; exit 0; }
[ "${NO_RUNUSER:-0}" = 1 ] && unset -f runuser && PATH=/nonexistent
[ "${NO_USERADD:-0}" = 1 ] && unset -f useradd && PATH=/nonexistent
HOME="$T/roothome"; SVC=javis
cd "$APP_DIR"
'''


def pick(uid="0", os_name="Linux", app="opt/javis", unit=None, env_owner=None, users=("root",), env=None,
         locked="roothome", existing_dest=False, no_runuser=False, no_useradd=False):
    """Run the block. `app` and `locked` are relative to a temp folder. Returns (exit code, output, temp folder)."""
    t = Path(tempfile.mkdtemp(prefix="javis-acct-"))
    app_dir = t / app
    app_dir.mkdir(parents=True)
    (app_dir / "install.sh").write_text("#!/bin/sh\n")
    (t / "users").write_text("\n".join(users) + "\n")
    if unit is not None:
        (t / "javis.service").write_text(unit)
    if env_owner is not None:
        (app_dir / ".env").write_text("X=1\n")
    dest = t / "opt" / "moved"
    if existing_dest:
        dest.mkdir(parents=True)
    run_env = {"PATH": "/usr/bin:/bin", "T": str(t), "FAKE_UID": uid, "FAKE_OS": os_name,
               "FAKE_WHO": "root" if uid == "0" else "minh", "ENV_OWNER": env_owner or "root",
               "APP_DIR": str(app_dir), "UNIT_FILE": str(t / "javis.service"), "LOCKED": str(t / locked),
               "JAVIS_INSTALL_DIR": str(dest), "NO_RUNUSER": "1" if no_runuser else "0",
               "NO_USERADD": "1" if no_useradd else "0"}
    run_env.update(env or {})
    script = STUBS + PICK + '\npick_run_user\necho "RESULT RUN_AS=[$RUN_AS] RUN_USER=[$RUN_USER] RUN_HOME=[$RUN_HOME]"\n'
    bash = "/bin/bash" if Path("/bin/bash").exists() else "bash"
    r = subprocess.run([bash, "-c", script], env=run_env, capture_output=True, text=True, timeout=60)
    return r.returncode, r.stdout + r.stderr, t


rc, out, _ = pick(uid="1000")
check("a normal user: nothing changes, the service runs as that user",
      rc == 0 and "RESULT RUN_AS=[] RUN_USER=[minh]" in out and "CALL" not in out, out)

rc, out, _ = pick(os_name="Darwin")
check("root on macOS: left as it was (LaunchAgent install)", rc == 0 and "RUN_AS=[]" in out and "CALL" not in out, out)

rc, out, t = pick()
check("root, fresh install: the account 'javis' is created",
      rc == 0 and "CALL useradd --create-home --shell /bin/bash javis" in out, out)
check("root, fresh install: the service account is javis, with its own home",
      "RESULT RUN_AS=[javis] RUN_USER=[javis] RUN_HOME=[/home/javis]" in out, out)
check("root, fresh install: the folder is handed to the account, and nothing is moved",
      f"CALL chown -R javis: {t}/opt/javis" in out and "CALL exec" not in out and (t / "opt/javis").is_dir(), out)

rc, out, _ = pick(users=("root", "javis"))
check("the account already exists: used, not created again", rc == 0 and "useradd" not in out and "RUN_AS=[javis]" in out, out)

rc, out, _ = pick(env={"JAVIS_USER": "shop"})
check("JAVIS_USER picks the account name", rc == 0 and "useradd --create-home --shell /bin/bash shop" in out
      and "RUN_AS=[shop]" in out, out)
for bad in ("Shop Bot", "a;rm -rf x", "9lives", "root.x"):
    rc, out, _ = pick(env={"JAVIS_USER": bad})
    check(f"JAVIS_USER {bad!r} is refused before anything is created", rc == 1 and "CALL" not in out, out)

# A clone under /root: no other account can enter it.
rc, out, t = pick(app="roothome/javis")
check("fresh clone under /root: moved to the install folder, handed over, and the installer restarts from there",
      rc == 0 and (t / "opt/moved/install.sh").is_file() and not (t / "roothome/javis").exists()
      and f"CALL chown -R javis: {t}/opt/moved" in out and f"CALL exec bash {t}/opt/moved/install.sh" in out, out)
check("the move is announced", "WARN" in out and f"moves to {t}/opt/moved" in out, out)

rc, out, t = pick(app="roothome/javis", existing_dest=True)
check("the install folder is taken: stops, moves nothing, names both ways out",
      rc == 1 and (t / "roothome/javis/install.sh").is_file() and "JAVIS_INSTALL_DIR" in out
      and "JAVIS_RUN_AS_ROOT=1" in out and "CALL exec" not in out, out)

# ---- an install that already exists keeps its account ----
rc, out, t = pick(unit="[Service]\nUser=root\nExecStart=x\n", app="roothome/javis")
check("existing unit with User=root: stays root, no account created, nothing moved",
      rc == 0 and "RUN_AS=[] RUN_USER=[root]" in out and "CALL" not in out and (t / "roothome/javis").is_dir(), out)
check("staying root says why Claude chats fail and what the flag costs",
      "WARN" in out and "IS_SANDBOX=1" in out and "whole machine" in out, out)

rc, out, _ = pick(unit="[Service]\nExecStart=x\n")
check("existing unit with no User= line (a hand-written root unit): stays root", rc == 0 and "RUN_USER=[root]" in out, out)

rc, out, _ = pick(unit="[Service]\nUser=shop\n", users=("root", "shop"))
check("existing unit with User=shop: a re-run keeps shop", rc == 0 and "RUN_AS=[shop]" in out and "useradd" not in out, out)

rc, out, _ = pick(env_owner="root")
check("no unit, .env owned by root (an earlier root install under nohup): stays root",
      rc == 0 and "RUN_USER=[root]" in out and "CALL" not in out, out)

rc, out, _ = pick(env_owner="javis", users=("root", "javis"))
check("no unit, .env owned by javis (a re-run after a failed first run): keeps javis",
      rc == 0 and "RUN_AS=[javis]" in out and "useradd" not in out, out)

rc, out, t = pick(env_owner="javis", users=("root", "javis"), app="roothome/javis")
check("an existing install the account cannot reach: stops, and never moves a folder that holds data",
      rc == 1 and (t / "roothome/javis").is_dir() and "CALL exec" not in out, out)

rc, out, _ = pick(env={"JAVIS_RUN_AS_ROOT": "1"})
check("JAVIS_RUN_AS_ROOT=1: the old behaviour, with the warning", rc == 0 and "RUN_USER=[root]" in out
      and "CALL" not in out and "IS_SANDBOX=1" in out, out)

rc, out, _ = pick(no_runuser=True)
check("no runuser on this system: falls back to root and says so", rc == 0 and "RUN_USER=[root]" in out
      and "'runuser' is missing" in out, out)
rc, out, _ = pick(no_useradd=True)
check("no useradd on this system: falls back to root and says so", rc == 0 and "RUN_USER=[root]" in out
      and "'useradd' is missing" in out, out)

# ---- 2. install.sh: the rest of the script follows the chosen account ----
check("the systemd unit runs as the chosen account, not as whoever ran the installer",
      "User=$RUN_USER\n" in INSTALL and "User=$(whoami)" not in INSTALL)
check("vendor CLI installers run as the service account (they write into its HOME)",
      'curl -fsSL "$3" | as_user bash' in INSTALL and 'curl -fsSL "$3" | bash' not in INSTALL)
check("the Claude sign-in is checked for the service account", "as_user claude auth status" in INSTALL)
check("everything root wrote is handed over before the service starts",
      INSTALL.index('own "$APP_DIR"\n\n# --- 9.') < INSTALL.index("systemctl enable --now"))
check(".env is handed over the moment it is created (a re-run reads the account off it)",
      INSTALL.index("Created .env from template") < INSTALL.index("own .env") < INSTALL.index("# --- 7. minimal"))
check("a tarball Node goes where the service account can reach it, not under /root",
      "NODE_DIR=/opt/javis-node; LINK_DIR=/usr/local/bin" in INSTALL and '"$HOME/.javis/node/bin/node"' not in INSTALL)
check("the Update button of a non-root service is given a user manager (linger)",
      'loginctl enable-linger "$RUN_AS"' in INSTALL)
check("without systemd the server starts as the account, outside this terminal's session",
      "exec $DETACH runuser -u \"$RUN_AS\"" in INSTALL and "</dev/null >/dev/null 2>&1 &" in INSTALL)
check("as_user gives the command the account's own HOME",
      'runuser -u "$RUN_AS" -- env HOME="$RUN_HOME"' in INSTALL)
check("Javis never sets IS_SANDBOX by itself", "IS_SANDBOX=1" not in INSTALL.replace("IS_SANDBOX=1 is in .env", "")
      .replace("IS_SANDBOX=1 flag", "") and "IS_SANDBOX" not in UPDATE)

# ---- 3. update.sh: root updates the files as the account that owns them ----
_u0 = UPDATE.index('AS_OWNER=""')
_u1 = UPDATE.index('echo "==> Pulling the latest code from GitHub..."')
OWNER_BLOCK = UPDATE[_u0:_u1]
U_STUBS = r'''
set -euo pipefail
id() { echo "$FAKE_UID"; }
stat() { case "${@: -1}" in .) echo "$O_DIR";; .git) echo "$O_GIT";; .venv) echo "$O_VENV";; esac; }
getent() { [ "$2" = ghost ] || echo "$2:x:1001:1001::/home/$2:/bin/bash"; }
runuser() { :; }
cd "$APP_DIR"
'''


def owner(uid="0", d="javis", git="javis", venv="javis", has_venv=True):
    t = Path(tempfile.mkdtemp(prefix="javis-upd-"))
    (t / ".git").mkdir()
    if has_venv:
        (t / ".venv").mkdir()
    r = subprocess.run(["bash", "-c", U_STUBS + OWNER_BLOCK + '\necho "AS_OWNER=[$AS_OWNER]"\n'],
                       env={"PATH": "/usr/bin:/bin", "FAKE_UID": uid, "O_DIR": d, "O_GIT": git, "O_VENV": venv,
                            "APP_DIR": str(t)}, capture_output=True, text=True, timeout=60)
    return r.stdout + r.stderr


out = owner()
check("root, folder owned by javis: git and pip run as javis, with its HOME",
      "AS_OWNER=[runuser -u javis -- env HOME=/home/javis USER=javis LOGNAME=javis]" in out, out)
check("update.sh says whose files it updates", "belongs to the account 'javis'" in out, out)
check("root, everything owned by root (an older root install): unchanged", "AS_OWNER=[]" in owner("0", "root", "root", "root"))
check("sudo ./install.sh left a root-owned .venv in someone's clone: keeps updating as root",
      "AS_OWNER=[]" in owner("0", "minh", "minh", "root"))
check("no .venv yet: the folder and .git decide", "AS_OWNER=[runuser -u javis" in owner(has_venv=False))
check("a normal user running update.sh: unchanged", "AS_OWNER=[]" in owner("1000"))
check("an owner with no account entry: unchanged", "AS_OWNER=[]" in owner("0", "ghost", "ghost", "ghost"))
check("the pull and the pip install go through the owner",
      "$AS_OWNER git pull --ff-only" in UPDATE and "$AS_OWNER ./.venv/bin/pip install -r requirements.txt" in UPDATE)
check("the restart of the service itself stays with root", '$SUDO systemctl restart "$NAME"' in UPDATE)

# ---- 4. the docs say it ----
for name in ("DEPLOY.md", "DEPLOY.en.md"):
    doc = (ROOT / name).read_text(encoding="utf-8")
    check(f"{name} explains the root install and its three options",
          all(k in doc for k in ("JAVIS_USER", "JAVIS_INSTALL_DIR", "JAVIS_RUN_AS_ROOT=1", "su - javis -c")))

print("\n" + ("GREEN" if not _fails else f"RED: {len(_fails)} failed"))
raise SystemExit(1 if _fails else 0)
