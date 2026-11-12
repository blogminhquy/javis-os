"""GitHub inside chat: nothing a chat's shell can plant in the clone gets to see the token.

    python tests/run.py github_token_isolation      (no network: local fake GitHub over HTTP; needs git)

Javis's own authenticated git calls carry the token in git's environment. git passes that environment to every
program it starts, and a chat's worktree shares the clone's `.git`, where the model (or an `npm install` it runs) can
write hooks and config. Before this isolation a planted hook simply read the token (measured 12/11/2026 on
`reference-transaction` during fetch, `post-checkout` during worktree add, `pre-push` during push), and a repo-level
`insteadOf` sent the header to another server.

Every case below drives a real authenticated call of Javis against a remote that refuses requests without the token:
  1. Planted hooks (the three above, plus a husky-style `core.hooksPath`) never run in a call that holds the token,
     and Javis's fetch, worktree add, checkout and push still work.
  2. Programs named by repo-level config never run in it either: filter driver, fsmonitor, credential helper, askpass.
  3. Repo-level config that moves the connection is refused by name, and the other server receives nothing.
  4. The header goes to the registered origin only, and only inside a repo Javis cloned.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import base64
import os
import socket
import sys
import tempfile
import threading
from pathlib import Path

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-ghi-")
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from _fake_github import FakeGitHub, GOOD_TOKEN, git  # noqa: E402

fake = FakeGitHub()
os.environ["JAVIS_GITHUB_API"] = fake.url

import github_repos as r  # noqa: E402
import github_work as w  # noqa: E402

_fails = []
BASIC = base64.b64encode(f"x-access-token:{GOOD_TOKEN}".encode()).decode()
OUT = Path(tempfile.mkdtemp(prefix="planted-"))
ENV_DUMP = OUT / "env.txt"      # what a planted program saw in its environment
RAN = OUT / "ran.txt"           # which planted programs ran at all


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)


def attempt(fn, *a, **kw):
    """"" when the call went through, the refusal text otherwise."""
    try:
        fn(*a, **kw)
    except r.RepoError as e:
        return str(e) or "failed"
    return ""


def spy(name):
    """A shell script that records that it ran and dumps its whole environment. Paths in sh form for Windows too."""
    return f'#!/bin/sh\necho {name} >> "{RAN.as_posix()}"\nenv >> "{ENV_DUMP.as_posix()}"\nexit 0\n'


def plant(path, name):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(spy(name), encoding="utf-8", newline="\n")
    path.chmod(0o755)
    return path.as_posix()


def collect():
    """(names of planted programs that ran, whether any of them saw the token), then forget both."""
    ran = RAN.read_text(encoding="utf-8").split() if RAN.exists() else []
    seen = ENV_DUMP.read_text(encoding="utf-8", errors="replace") if ENV_DUMP.exists() else ""
    for p in (RAN, ENV_DUMP):
        if p.exists():
            p.unlink()
    return sorted(set(ran)), (GOOD_TOKEN in seen or BASIC in seen)


class Listener(threading.Thread):
    """Another server: answers 404 to everything and keeps what it was sent."""

    def __init__(self):
        super().__init__(daemon=True)
        self.sock = socket.socket()
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(8)
        self.port = self.sock.getsockname()[1]
        self.url = f"http://127.0.0.1:{self.port}"
        self.requests = []
        self.start()

    def run(self):
        while True:
            try:
                conn, _ = self.sock.accept()
                self.requests.append(conn.recv(65536).decode("latin-1"))
                conn.sendall(b"HTTP/1.1 404 Not Found\r\nContent-Length: 0\r\nConnection: close\r\n\r\n")
                conn.close()
            except OSError:
                return

    def take(self):
        got, self.requests = self.requests, []
        return got


# A default install keeps its state inside the Javis checkout (STATE_DIR is `server/`), so every clone is made in a
# folder that belongs to ANOTHER git repo, with an origin of its own. `git clone` reads none of that repo's config.
STATE = os.environ["JAVIS_STATE_DIR"]
git(["init", "-q", STATE], STATE)
git(["config", "remote.origin.url", "https://github.com/someone/javis-os.git"], STATE)

BRAIN = tempfile.mkdtemp(prefix="brain-")
r.connect(GOOD_TOKEN)
fake.add_repo("acme/secret", files={"README.md": "x\n", "src/a.py": "a = 1\n"})
fake.add_branch("acme/secret", "dev", "DEV.md", "only on dev\n")
url = fake.serve_private("acme/secret")

err = ""
try:
    r.attach("c1", BRAIN, BRAIN, ["acme/secret"])
except r.RepoError as e:
    err = str(e)
repos1 = r.session_repos("c1", BRAIN)
check(f"the first clone works with the state folder inside another git repo{': ' + err if err else ''}",
      not err and bool(repos1) and bool(repos1[0].get("worktree")))
if _fails:
    sys.exit(1)
repo1 = repos1[0]
clone, wt1 = repo1["clone"], repo1["worktree"]
dot_git = Path(clone) / ".git"


def cfg(*args, check_rc=True):
    return git(["config", *args], clone, check=check_rc)


# ============================================================
# 1. Planted hooks
# ============================================================
HOOKS = ("reference-transaction", "post-checkout", "pre-push")
for name in HOOKS:
    plant(dot_git / "hooks" / name, name)

# The plant is live: the same hooks run, and would read the environment, on plain git calls without the token.
git(["update-ref", "refs/probe/x", "HEAD"], clone)
git(["checkout", "-q", "--detach"], wt1)
git(["checkout", "-q", "-"], wt1)
git(["push", "-q", "--dry-run", fake.repos["acme/secret"]["bare"], "HEAD:refs/heads/probe"], wt1, check=False)
ran, saw = collect()
check("the planted hooks are live on plain git calls", set(HOOKS) <= set(ran))
check("and a call without the token has no token to show them", not saw)

# fetch
fake.push_to_default("acme/secret", "NEW.md", "landed after the clone\n")
before = git(["rev-parse", "origin/main"], clone).stdout.strip()
err = attempt(r.ensure_clone, BRAIN, BRAIN, "acme/secret")
ran, saw = collect()
check(f"fetch still works{': ' + err if err else ''}",
      not err and git(["rev-parse", "origin/main"], clone).stdout.strip() != before)
check("fetch: no planted hook ran", ran == [])
check("fetch: the token reached no planted hook", not saw)

# worktree add (a second chat), with the lazy fetch of the file that landed later
err = attempt(r.attach, "c2", BRAIN, BRAIN, ["acme/secret"])
ran, saw = collect()
repos2 = r.session_repos("c2", BRAIN)
wt2 = repos2[0]["worktree"] if repos2 and repos2[0].get("worktree") else ""
check(f"worktree add still works{': ' + err if err else ''}", not err and bool(wt2) and (Path(wt2) / "NEW.md").is_file())
check("worktree add: no planted hook ran (post-checkout)", ran == [])
check("worktree add: the token reached no planted hook", not saw)

# checkout onto another base ("Change branch")
err = attempt(r.set_base, "c1", BRAIN, "acme/secret", "dev")
ran, saw = collect()
check(f"checkout onto another base still works{': ' + err if err else ''}", not err and (Path(wt1) / "DEV.md").is_file())
check("checkout: no planted hook ran", ran == [])
check("checkout: the token reached no planted hook", not saw)

# push
(Path(wt2) / "work.md").write_text("the chat's work\n", encoding="utf-8")
head = w.commit_all(wt2, "work of the chat")
collect()       # the commit is a plain call: hooks may run there, they hold no token
branch = r.session_branch("c2")
err = attempt(w.push, repos2[0], branch)
ran, saw = collect()
check(f"push still works{': ' + err if err else ''}", not err and fake.branch_sha("acme/secret", branch) == head)
check("push: no planted hook ran (pre-push)", ran == [])
check("push: the token reached no planted hook", not saw)

# husky style: the repo redirects its hooks folder
husky = OUT / "husky"
for name in HOOKS:
    plant(husky / name, "husky-" + name)
cfg("core.hooksPath", husky.as_posix())
fake.push_to_default("acme/secret", "NEW2.md", "x\n")
err = attempt(r.ensure_clone, BRAIN, BRAIN, "acme/secret")
(Path(wt2) / "work2.md").write_text("more\n", encoding="utf-8")
w.commit_all(wt2, "more work")
collect()
err = err or attempt(w.push, repos2[0], branch)
ran, saw = collect()
check(f"a repo-level core.hooksPath changes nothing{': ' + err if err else ''}", not err and ran == [] and not saw)
cfg("--unset", "core.hooksPath")

# a file dropped into Javis's own empty hooks folder is cleared before the next call
plant(r.NO_HOOKS_DIR / "reference-transaction", "nohooks-dir")
fake.push_to_default("acme/secret", "NEW3.md", "x\n")
err = attempt(r.ensure_clone, BRAIN, BRAIN, "acme/secret")
ran, saw = collect()
check("Javis's hooks folder is emptied before every call", not err and ran == [] and not any(r.NO_HOOKS_DIR.iterdir()))

# ============================================================
# 2. Programs named by repo-level config
# ============================================================
# A filter driver, chosen for every file through .git/info/attributes: it would run on worktree add.
cfg("filter.spy.smudge", f"sh -c 'echo filter >> \"{RAN.as_posix()}\"; env >> \"{ENV_DUMP.as_posix()}\"; cat'")
cfg("filter.spy.required", "true")
(dot_git / "info").mkdir(exist_ok=True)
(dot_git / "info" / "attributes").write_text("* filter=spy\n", encoding="utf-8")
cfg("core.fsmonitor", plant(OUT / "fsmonitor.sh", "fsmonitor"))
fake.push_to_default("acme/secret", "LATER.md", "after the filter was planted\n")
err = attempt(r.attach, "c3", BRAIN, BRAIN, ["acme/secret"])
ran, saw = collect()
repos3 = r.session_repos("c3", BRAIN)
wt3 = repos3[0]["worktree"] if repos3 and repos3[0].get("worktree") else ""
check(f"worktree add works with a planted filter and fsmonitor{': ' + err if err else ''}",
      not err and bool(wt3) and (Path(wt3) / "LATER.md").read_text(encoding="utf-8") == "after the filter was planted\n")
check("the repo's filter driver and fsmonitor did not run with the token", ran == [] and not saw)
(dot_git / "info" / "attributes").unlink()
for key in ("filter.spy.smudge", "filter.spy.required", "core.fsmonitor"):
    cfg("--unset", key)

# A credential helper and an askpass program: git starts them when GitHub answers 401 (a token that expired).
cfg("credential.helper", f"!f() {{ echo helper >> \"{RAN.as_posix()}\"; env >> \"{ENV_DUMP.as_posix()}\"; }}; f")
cfg("core.askPass", plant(OUT / "askpass.sh", "askpass"))
real_token = r.token
r.token = lambda: "ghp_expired_token_0000"
try:
    err = attempt(r.git, ["fetch", "origin"], clone, auth=True)
finally:
    r.token = real_token
ran, saw = collect()
check("a rejected token fails as a sign-in problem", bool(err) and bool(w._AUTH_RE.search(err)))
check("the repo's credential helper and askpass did not run", ran == [])
cfg("--unset", "credential.helper")
cfg("--unset", "core.askPass")

# ============================================================
# 3. Repo-level config that moves the connection
# ============================================================
other = Listener()


def refused(label, key, *set_args, unset=None):
    """Plant one setting, expect Javis to refuse naming it and the other server to hear nothing, then remove it."""
    cfg(*set_args)
    err_fetch = attempt(r.git, ["fetch", "origin"], clone, auth=True)
    err_push = attempt(w.push, repos2[0], branch)
    ran, saw = collect()
    got = other.take()
    check(f"{label}: fetch and push refuse, naming {key}", key in err_fetch and key in err_push)
    check(f"{label}: nothing was sent to the other server", not got and not saw)
    cfg(*(unset or ["--unset-all", set_args[0]]))


refused("insteadOf", "insteadof", f"url.{other.url}/.insteadOf", url.rsplit("/", 1)[0] + "/")
refused("http.proxy", "http.proxy", "http.proxy", other.url)
refused("sslVerify for the origin", "sslverify", f"http.{url}.sslVerify", "false")
(dot_git / "extra.cfg").write_text(f'[url "{other.url}/"]\n\tinsteadOf = {url.rsplit("/", 1)[0]}/\n', encoding="utf-8")
refused("an included file", "include.path", "include.path", "extra.cfg")
refused("a second push URL", "remote.origin.pushurl", "remote.origin.pushurl", other.url + "/x.git")
refused("origin pointed elsewhere", "remote.origin.url", "remote.origin.url", other.url + "/x.git",
        unset=["remote.origin.url", url])
refused("a remote helper for origin", "remote.origin.vcs", "remote.origin.vcs", "spy")
refused("core.sshCommand", "core.sshcommand", "core.sshCommand", plant(OUT / "ssh.sh", "ssh"))

# The refusal reaches the person as the reason the push is stuck, and names what to remove.
cfg("http.proxy", other.url)
err = attempt(w.push, repos2[0], branch)
check("the refusal says what to remove", "http.proxy" in err and "--unset-all" in err)
cfg("--unset", "http.proxy")

# Attaching again puts a rewritten origin back to what GitHub says, so one stray `git remote set-url` heals itself.
cfg("remote.origin.url", other.url + "/x.git")
err = attempt(r.ensure_clone, BRAIN, BRAIN, "acme/secret")
check(f"ensure_clone restores origin to GitHub's URL{': ' + err if err else ''}",
      not err and git(["remote", "get-url", "origin"], clone).stdout.strip() == url and not other.take())

# Settings that move nothing stay allowed: a repo's own identity, a branch's upstream, a bigger post buffer.
cfg("user.name", "Someone")
cfg("http.postBuffer", "524288000")
cfg("pull.rebase", "true")
(Path(wt2) / "work3.md").write_text("still pushing\n", encoding="utf-8")
head = w.commit_all(wt2, "third commit")
collect()
err = attempt(w.push, repos2[0], branch)
check(f"harmless repo config does not block a push{': ' + err if err else ''}",
      not err and fake.branch_sha("acme/secret", branch) == head)

# ============================================================
# 4. Where the header may go
# ============================================================
# Another URL named on the command line, from inside the clone: reached, but without the token.
attempt(r.git, ["ls-remote", other.url + "/elsewhere.git"], clone, auth=True)
got = other.take()
check("a URL other than origin is reached without the token", bool(got) and not any(BASIC in q for q in got))

# A protocol that runs a command (`ext::`) is not allowed in a call that holds the token, whatever the repo says.
cfg("protocol.ext.allow", "always")
ext = f"ext::sh -c 'echo ext >> \"{RAN.as_posix()}\"; env >> \"{ENV_DUMP.as_posix()}\"'"
err = attempt(r.git, ["ls-remote", ext], clone, auth=True)
ran, saw = collect()
check("the ext:: transport is refused", bool(err) and ran == [] and not saw)
cfg("--unset", "protocol.ext.allow")

# A submodule the chat initialised has a git config of its own that Javis never looks at, and git walks into
# populated submodules while fetching. Javis's fetch stays out of it.
fake.add_repo("acme/sub", files={"lib.py": "x = 1\n"})
sub_url = fake.serve_private("acme/sub")
as_model = ["-c", f"http.extraheader=AUTHORIZATION: basic {BASIC}"]      # test only: lets the plain calls below sign in
added = git(as_model + ["submodule", "add", "-q", sub_url, "sub"], wt3, check=False)
cfg("fetch.recurseSubmodules", "true")
SUB_PATH = "/" + sub_url.rsplit("/", 1)[1]


def sub_requests(since):
    return [path for path, _ok in fake.git_requests[since:] if path.startswith(SUB_PATH)]


asked = len(fake.git_requests)
git(as_model + ["fetch", "-q", "origin"], wt3, check=False)
check("a plain fetch walks into the chat's submodule", added.returncode == 0 and bool(sub_requests(asked)))
asked = len(fake.git_requests)
err = attempt(r.git, ["fetch", "origin"], wt3, auth=True)
check(f"Javis's fetch does not{': ' + err if err else ''}", not err and not sub_requests(asked))
cfg("--unset", "fetch.recurseSubmodules")
collect()

# Outside a repo Javis cloned there is no registered origin, so there is no token.
stray = Path(tempfile.mkdtemp(prefix="stray-"))
git(["init", "-q", str(stray)], BRAIN)
asked = len(fake.git_requests)
err = attempt(r.git, ["ls-remote", url], str(stray), auth=True)
check("a folder Javis did not clone gets no token", bool(err) and len(fake.git_requests) == asked)
check("the origin comes from the registry, for the clone and for its worktrees",
      r.trusted_origin(clone) == url and r.trusted_origin(wt2) == url and r.trusted_origin(str(stray)) == "")

# The environment itself: one scoped header, hooks off, the origin's protocol only.
env = r.auth_env(clone, url)
pairs = {env[f"GIT_CONFIG_KEY_{i}"]: env[f"GIT_CONFIG_VALUE_{i}"] for i in range(int(env["GIT_CONFIG_COUNT"]))}
header_keys = [k for k, v in pairs.items() if BASIC in v]
check("the token sits under exactly one key, scoped to the origin URL", header_keys == [f"http.{url}.extraheader"])
check("hooks point at Javis's empty folder", pairs.get("core.hooksPath") == r.NO_HOOKS_DIR.as_posix()
      and r.NO_HOOKS_DIR.is_dir() and not any(r.NO_HOOKS_DIR.iterdir()))
check("only the origin's protocol is allowed", env.get("GIT_ALLOW_PROTOCOL") == "http")
check("a call without auth carries no token at all", BASIC not in "\n".join(r.git_env().values()))

# The clone on disk is as clean as before.
config_text = (dot_git / "config").read_text(encoding="utf-8")
check("the clone's git config holds no token", GOOD_TOKEN not in config_text and BASIC not in config_text)

fake.close()
print()
if _fails:
    print(f"FAIL {len(_fails)} test: " + ", ".join(_fails))
    sys.exit(1)
print("TẤT CẢ PASS")
