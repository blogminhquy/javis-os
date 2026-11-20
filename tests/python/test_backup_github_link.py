"""Brain backup on the signed-in GitHub account (backup_github.py, owner 20/11/2026).

    python tests/run.py backup_github_link      (no network: a local fake GitHub, bare repos as remotes; needs git)

The owner: once GitHub is connected, linking the two-way brain sync must be easy too, no URL or token to paste.
Covered here:
  1. The sync token: a pasted backup token still wins; a backup linked through GitHub uses the connection's token;
     a backup with a URL but no token of its own borrows the connection.
  2. The picker lists only PRIVATE repos the account can push to.
  3. Linking refuses a public repo, and on success saves GitHub's clone URL, the default branch, and turns auto on.
  4. "Create" makes a private repo and links it; the name already taken links the existing repo; a token that may
     not create repos (a "Sign in with GitHub" token) gets github.com/new filled in plus the page to give Javis access.
  5. A sync really runs on the linked config (empty repo first, then a second machine pulls the brain back).
  6. Unlink forgets the repo and stops auto sync, and leaves a pasted token alone.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import os
import sys
import tempfile
from pathlib import Path

_STATE = tempfile.mkdtemp(prefix="javis-bkgh-")
os.environ["JAVIS_STATE_DIR"] = _STATE

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from _fake_github import FakeGitHub, GOOD_TOKEN, git  # noqa: E402

fake = FakeGitHub()
os.environ["JAVIS_GITHUB_API"] = fake.url

import backup_github  # noqa: E402
import config  # noqa: E402
import git_brain  # noqa: E402
import github_repos  # noqa: E402

_fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)


def raises(fn, *a, **kw):
    try:
        fn(*a, **kw)
    except backup_github.BackupLinkError as e:
        return str(e)
    return ""


def backup():
    return dict(config.read_settings().get("backup") or {})


def set_backup(**kw):
    config.update_settings({"backup": kw})


fake.add_repo("tester/notes-private", private=True)
fake.add_repo("tester/site-public", private=False)
fake.add_repo("tester/read-only", private=True, push=False)

# ---- 1. Which token the sync uses ----
check("nothing configured: no token, not ready", backup_github.effective_token(backup()) == ""
      and not backup_github.ready(backup()) and backup_github.token_source(backup()) == "")
set_backup(repo_url="https://github.com/tester/x", token="github_pat_pasted")
check("pasted token without GitHub: used as is", backup_github.effective_token(backup()) == "github_pat_pasted"
      and backup_github.token_source(backup()) == "token")
github_repos.connect(GOOD_TOKEN)
check("pasted token still wins over the connection", backup_github.effective_token(backup()) == "github_pat_pasted")
set_backup(use_github=True)
check("linked through GitHub: the connection's token", backup_github.effective_token(backup()) == GOOD_TOKEN
      and backup_github.token_source(backup()) == "github")
set_backup(token="", use_github=False)
check("URL and no token of its own: borrows the connection", backup_github.effective_token(backup()) == GOOD_TOKEN
      and backup_github.ready(backup()))
github_repos.disconnect()
check("connection gone and no own token: not ready", not backup_github.ready(backup()))
github_repos.connect(GOOD_TOKEN)

# ---- 2. Picker ----
names = [r["full_name"] for r in backup_github.repos()]
check("picker lists the private repo", "tester/notes-private" in names)
check("picker hides public repos", "tester/site-public" not in names)
check("picker hides repos the account cannot push to", "tester/read-only" not in names)

# ---- 3. Link ----
check("linking a public repo is refused", "public" in raises(backup_github.link, "tester/site-public").lower()
      or "công khai" in raises(backup_github.link, "tester/site-public"))
check("linking a bad name is refused", bool(raises(backup_github.link, "nope")))
check("linking an unknown repo is refused", bool(raises(backup_github.link, "tester/ghost")))
set_backup(enabled=False, token="github_pat_old")
out = backup_github.link("tester/notes-private")
b = backup()
check("link saves GitHub's clone URL", b["repo_url"] == fake.repos["tester/notes-private"]["clone_url"]
      and out["full_name"] == "tester/notes-private")
check("link rides on the connection and turns auto sync on", b["use_github"] is True and b["enabled"] is True)
check("link uses the repo's default branch", b["branch"] == "main")
check("after linking, the connection's token wins over the old pasted one",
      backup_github.effective_token(b) == GOOD_TOKEN)

# ---- 4. Create ----
out = backup_github.create("")
check("create makes a private repo with the default name", out.get("created") is True
      and fake.repos.get("tester/" + backup_github.DEFAULT_NAME, {}).get("private") is True)
check("create links the new repo", backup()["repo_url"] == fake.repos["tester/" + backup_github.DEFAULT_NAME]["clone_url"])
out = backup_github.create(backup_github.DEFAULT_NAME)
check("create on a taken name links the existing repo", out.get("existing") is True)
check("create refuses an odd name", bool(raises(backup_github.create, "bad name/../x")))
fake.can_create = False
out = backup_github.create("brain-two")
check("token that may not create repos: manual steps, nothing linked", out.get("manual") is True
      and "name=brain-two" in out["new_url"] and "visibility=private" in out["new_url"]
      and backup()["repo_url"] == fake.repos["tester/" + backup_github.DEFAULT_NAME]["clone_url"])
check("pasted token: no 'give Javis access' page", out["install_url"] == "")
fake.can_create = True

# ---- 5. A real sync on the linked config ----
if git_brain.has_git():
    brains = Path(tempfile.mkdtemp(prefix="brains-a-"))
    (brains / "brain" / "notes").mkdir(parents=True)
    (brains / "brain" / "notes" / "hello.md").write_text("# Hello from machine A\n", encoding="utf-8")
    b = backup()
    res = git_brain.sync_brains(str(brains), str(Path(_STATE) / "mirror-a"), b["repo_url"],
                                backup_github.effective_token(b), b["branch"])
    check("first sync pushes the brain to the linked empty repo", res.get("ok") is True and res.get("pushed"))
    brains_b = Path(tempfile.mkdtemp(prefix="brains-b-"))
    res = git_brain.sync_brains(str(brains_b), str(Path(_STATE) / "mirror-b"), b["repo_url"],
                                backup_github.effective_token(b), b["branch"])
    got = brains_b / "brain" / "notes" / "hello.md"
    check("a second machine linked to the same repo gets the brain back",
          res.get("ok") is True and got.is_file() and "machine A" in got.read_text(encoding="utf-8"))
else:
    print("skip  sync (git missing)")

# ---- 6. Unlink ----
backup_github.unlink()
b = backup()
check("unlink forgets the repo and stops auto sync", b["repo_url"] == "" and b["enabled"] is False
      and b["use_github"] is False)
check("unlink keeps a pasted token", b["token"] == "github_pat_old")
check("unlink never touches GitHub", "tester/" + backup_github.DEFAULT_NAME in fake.repos)

# ---- the "Sign in with GitHub" case for manual steps ----
config.update_settings({"github": {"source": "app", "token": GOOD_TOKEN, "login": "tester"}})
fake.can_create = False
out = backup_github.create("brain-three")
check("app sign-in: manual steps include the page to give Javis access", out.get("manual") is True
      and "/installations/new" in (out.get("install_url") or ""))

fake.close()
if _fails:
    print(f"\n{len(_fails)} FAILED")
    sys.exit(1)
print("\nall ok")
