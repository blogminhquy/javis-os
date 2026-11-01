"""A fake GitHub for the GitHub-in-chat tests: a local HTTP server plus bare git repos as remotes.

Nothing here reaches github.com. Tests point Javis at it with `JAVIS_GITHUB_API=<server url>`; each fake repo's
`clone_url` is a bare repo on disk, so clone, fetch and push are real git operations.

The server keeps just enough of the REST API for what github_api.py calls: user, repos, pulls (create, find, read,
merge), check runs and statuses per commit, required checks, job logs and reruns, and the GraphQL mutation that marks a
draft PR ready. Tests drive CI by setting check runs per SHA (`set_checks`).
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

GOOD_TOKEN = "ghp_faketoken_0123456789abcdef"


def git(args, cwd, check=True):
    return subprocess.run(["git"] + list(args), cwd=cwd, capture_output=True, text=True, check=check,
                          env={**os.environ, "GIT_TERMINAL_PROMPT": "0", "LC_ALL": "C"})


class FakeGitHub:
    def __init__(self, scopes="repo, workflow", login="tester"):
        self.root = Path(tempfile.mkdtemp(prefix="fake-gh-"))
        self.repos = {}           # full_name -> dict
        self.pulls = {}           # full_name -> list of pr dicts
        self.checks = {}          # sha -> list of check runs
        self.statuses = {}        # sha -> list of statuses
        self.required = {}        # (full_name, branch) -> list | None (None = 403)
        self.logs = {}            # job id -> text
        self.reruns = []          # job ids
        self.calls = []           # (method, path)
        self.comments = []        # (full_name, number, body)
        self.scopes = scopes
        self.login = login
        self.token = GOOD_TOKEN
        # "Sign in with GitHub" (device flow, 0.430.0). `pending` polls answer authorization_pending first, one of
        # them `slow_down` when `slow` is set; `deny` ends with access_denied. `installs` is /user/installations.
        self.device = {"pending": 1, "slow": False, "deny": False, "expires_in": 0, "refresh_token": "",
                       "refreshed_token": "", "client_ids": [], "polls": 0}
        self.installs = 1
        self.lock = threading.Lock()
        handler = self._handler()
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"

    def close(self):
        self.server.shutdown()

    # ---- repos ----
    def add_repo(self, full_name, default_branch="main", files=None, private=False, push=True):
        bare = self.root / (full_name.replace("/", "__") + ".git")
        git(["init", "-q", "--bare", "-b", default_branch, str(bare)], self.root)
        work = Path(tempfile.mkdtemp(prefix="fake-seed-"))
        git(["init", "-q", "-b", default_branch], work)
        git(["config", "user.email", "seed@test"], work)
        git(["config", "user.name", "Seed"], work)
        for name, text in (files or {"README.md": "hello\n"}).items():
            p = work / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(text, encoding="utf-8")
        git(["add", "-A"], work)
        git(["commit", "-q", "-m", "init"], work)
        git(["remote", "add", "origin", str(bare)], work)
        git(["push", "-q", "origin", default_branch], work)
        self.repos[full_name] = {"full_name": full_name, "default_branch": default_branch, "private": private,
                                 "clone_url": bare.as_uri(), "bare": str(bare),
                                 "permissions": {"push": push, "pull": True, "admin": False}, "description": ""}
        self.pulls.setdefault(full_name, [])
        return bare

    def add_branch(self, full_name, branch, filename="BRANCH.md", text="branch\n"):
        """A second branch on GitHub, one commit ahead of the default branch."""
        rep = self.repos[full_name]
        work = Path(tempfile.mkdtemp(prefix="fake-branch-"))
        git(["clone", "-q", rep["bare"], str(work)], self.root)
        git(["config", "user.email", "other@test"], work)
        git(["config", "user.name", "Other"], work)
        git(["checkout", "-q", "-b", branch], work)
        (work / filename).write_text(text, encoding="utf-8")
        git(["add", "-A"], work)
        git(["commit", "-q", "-m", f"on {branch}"], work)
        git(["push", "-q", "origin", branch], work)

    def branch_sha(self, full_name, branch):
        r = git(["rev-parse", f"refs/heads/{branch}"], self.repos[full_name]["bare"], check=False)
        return r.stdout.strip() if r.returncode == 0 else ""

    def push_to_default(self, full_name, filename, text):
        """Someone else lands a commit on the default branch (base moved)."""
        rep = self.repos[full_name]
        work = Path(tempfile.mkdtemp(prefix="fake-other-"))
        git(["clone", "-q", rep["bare"], str(work)], self.root)
        git(["config", "user.email", "other@test"], work)
        git(["config", "user.name", "Other"], work)
        (work / filename).write_text(text, encoding="utf-8")
        git(["add", "-A"], work)
        git(["commit", "-q", "-m", f"other change {filename}"], work)
        git(["push", "-q", "origin", rep["default_branch"]], work)

    def set_checks(self, sha, runs):
        """runs: list of (name, status, conclusion[, job_id])."""
        out = []
        for i, r in enumerate(runs):
            name, status, conclusion = r[0], r[1], r[2]
            job = r[3] if len(r) > 3 else 1000 + len(self.checks) * 10 + i
            out.append({"id": job, "name": name, "status": status, "conclusion": conclusion,
                        "details_url": f"https://github.com/x/actions/runs/1/job/{job}",
                        "html_url": f"https://github.com/x/actions/runs/1/job/{job}", "app": {"slug": "github-actions"}})
        self.checks[sha] = out

    # ---- merge in the bare repo ----
    def _merge(self, full_name, pr, method):
        rep = self.repos[full_name]
        work = Path(tempfile.mkdtemp(prefix="fake-merge-"))
        git(["clone", "-q", rep["bare"], str(work)], self.root)
        git(["config", "user.email", "merge@test"], work)
        git(["config", "user.name", "Merge"], work)
        base = pr["base"]["ref"]
        git(["checkout", "-q", base], work)
        if method == "squash":
            r = git(["merge", "--squash", f"origin/{pr['head']['ref']}"], work, check=False)
            if r.returncode != 0:
                return None
            git(["commit", "-q", "-m", f"{pr['title']} (#{pr['number']})"], work)
        else:
            r = git(["merge", "--no-ff", "-m", f"Merge #{pr['number']}", f"origin/{pr['head']['ref']}"], work,
                    check=False)
            if r.returncode != 0:
                return None
        git(["push", "-q", "origin", base], work)
        return git(["rev-parse", "HEAD"], work).stdout.strip()

    def _update_branch(self, full_name, pr):
        rep = self.repos[full_name]
        work = Path(tempfile.mkdtemp(prefix="fake-upd-"))
        git(["clone", "-q", rep["bare"], str(work)], self.root)
        git(["config", "user.email", "upd@test"], work)
        git(["config", "user.name", "Upd"], work)
        git(["checkout", "-q", pr["head"]["ref"]], work)
        git(["merge", "-q", "--no-edit", f"origin/{pr['base']['ref']}"], work)
        git(["push", "-q", "origin", pr["head"]["ref"]], work)

    def _pr_view(self, full_name, pr):
        head_sha = self.branch_sha(full_name, pr["head"]["ref"]) if not pr["merged"] else pr["head"]["sha"]
        pr["head"]["sha"] = head_sha or pr["head"]["sha"]
        return pr

    # ---- HTTP ----
    def _handler(self):
        fake = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _send(self, code, body=None, headers=None, text=None):
                data = (text if text is not None else json.dumps(body if body is not None else {})).encode()
                self.send_response(code)
                self.send_header("Content-Type", "text/plain" if text is not None else "application/json")
                for k, v in (headers or {}).items():
                    self.send_header(k, v)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def _auth(self):
                if self.headers.get("Authorization") != f"Bearer {fake.token}":
                    self._send(401, {"message": "Bad credentials"})
                    return False
                return True

            def _body(self):
                n = int(self.headers.get("Content-Length") or 0)
                raw = self.rfile.read(n) if n else b""
                try:
                    return json.loads(raw or b"{}")
                except ValueError:
                    return {}

            def _route(self, method):
                u = urlparse(self.path)
                path, q = u.path, {k: v[0] for k, v in parse_qs(u.query).items()}
                with fake.lock:
                    fake.calls.append((method, path))
                if path.startswith("/_control/"):
                    # Test driver only (end-to-end runs in another process): set CI results, read PRs.
                    body = self._body() if method == "POST" else {}
                    with fake.lock:
                        if path == "/_control/checks":
                            fake.set_checks(body["sha"], [tuple(r) for r in body.get("runs") or []])
                            return self._send(200, {"ok": True})
                        if path == "/_control/state":
                            return self._send(200, {"pulls": fake.pulls, "comments": fake.comments,
                                                    "heads": {fn: {b: fake.branch_sha(fn, b) for b in q.get("branches", "main").split(",")}
                                                              for fn in fake.repos}})
                    return self._send(404, {"message": "no such control"})
                if path in ("/login/device/code", "/login/oauth/access_token"):
                    n = int(self.headers.get("Content-Length") or 0)
                    form = {k: v[0] for k, v in parse_qs((self.rfile.read(n) if n else b"").decode()).items()}
                    with fake.lock:
                        return self._device(path, form)
                if not self._auth():
                    return
                body = self._body() if method in ("POST", "PUT", "PATCH") else {}
                with fake.lock:
                    return self._dispatch(method, path, q, body)

            def _device(self, path, form):
                d = fake.device
                d["client_ids"].append(form.get("client_id"))
                if path == "/login/device/code":
                    return self._send(200, {"device_code": "dev-123", "user_code": "ABCD-1234", "interval": 1,
                                            "expires_in": 900, "verification_uri": "https://github.com/login/device"})
                if form.get("grant_type") == "refresh_token":
                    if form.get("refresh_token") == d["refresh_token"] and d["refreshed_token"]:
                        return self._send(200, {"access_token": d["refreshed_token"], "expires_in": 28800,
                                                "refresh_token": "ghr_next"})
                    return self._send(200, {"error": "bad_refresh_token"})
                if form.get("device_code") != "dev-123":
                    return self._send(200, {"error": "incorrect_device_code"})
                d["polls"] += 1
                if d["pending"] > 0:
                    d["pending"] -= 1
                    if d["slow"]:
                        d["slow"] = False
                        return self._send(200, {"error": "slow_down", "interval": 2})
                    return self._send(200, {"error": "authorization_pending"})
                if d["deny"]:
                    return self._send(200, {"error": "access_denied"})
                out = {"access_token": fake.token, "token_type": "bearer", "scope": ""}
                if d["expires_in"]:
                    out.update(expires_in=d["expires_in"], refresh_token=d["refresh_token"])
                return self._send(200, out)

            def _dispatch(self, method, path, q, body):
                if path == "/user/installations":
                    return self._send(200, {"total_count": fake.installs, "installations": []})
                if path == "/user":
                    h = {"X-OAuth-Scopes": fake.scopes} if fake.scopes is not None else {}
                    return self._send(200, {"login": fake.login, "id": 4242}, headers=h)
                if path == "/user/repos":
                    page = int(q.get("page") or 1)
                    items = list(fake.repos.values()) if page == 1 else []
                    return self._send(200, items)
                if path == "/graphql":
                    return self._send(200, {"data": {}})
                m = re.match(r"^/repos/([^/]+/[^/]+)(/.*)?$", path)
                if not m:
                    return self._send(404, {"message": "Not Found"})
                fn, rest = m.group(1), m.group(2) or ""
                if fn not in fake.repos:
                    return self._send(404, {"message": "Not Found"})
                rep = fake.repos[fn]
                if rest == "" and method == "GET":
                    return self._send(200, rep)
                if rest == "/pulls" and method == "GET":
                    head = q.get("head", "")
                    ref = head.split(":", 1)[-1]
                    items = [fake._pr_view(fn, p) for p in fake.pulls[fn] if not ref or p["head"]["ref"] == ref]
                    return self._send(200, items)
                if rest == "/pulls" and method == "POST":
                    if not fake.branch_sha(fn, body.get("head", "")):
                        return self._send(422, {"message": "Validation Failed", "errors": [{"message": "No commits"}]})
                    for p in fake.pulls[fn]:
                        if p["head"]["ref"] == body["head"] and p["state"] == "open":
                            return self._send(422, {"message": "Validation Failed",
                                                    "errors": [{"message": "A pull request already exists"}]})
                    n = sum(len(v) for v in fake.pulls.values()) + 1
                    pr = {"number": n, "node_id": f"PR_{n}", "state": "open", "merged": False, "draft": bool(body.get("draft")),
                          "title": body.get("title"), "body": body.get("body"),
                          "html_url": f"https://github.com/{fn}/pull/{n}", "mergeable": True,
                          "mergeable_state": "clean",
                          "head": {"ref": body["head"], "sha": fake.branch_sha(fn, body["head"])},
                          "base": {"ref": body.get("base") or rep["default_branch"]}, "merge_commit_sha": None}
                    fake.pulls[fn].append(pr)
                    return self._send(201, pr)
                mc = re.match(r"^/issues/(\d+)/comments$", rest)
                if mc and method == "POST":
                    fake.comments.append((fn, int(mc.group(1)), body.get("body")))
                    return self._send(201, {"id": len(fake.comments)})
                mu = re.match(r"^/pulls/(\d+)/update-branch$", rest)
                if mu and method == "PUT":
                    pr = next((p for p in fake.pulls[fn] if p["number"] == int(mu.group(1))), None)
                    if not pr:
                        return self._send(404, {"message": "Not Found"})
                    fake._update_branch(fn, pr)
                    pr["mergeable_state"] = "clean"
                    return self._send(202, {"message": "Updating pull request branch."})
                m2 = re.match(r"^/pulls/(\d+)(/merge)?$", rest)
                if m2:
                    pr = next((p for p in fake.pulls[fn] if p["number"] == int(m2.group(1))), None)
                    if not pr:
                        return self._send(404, {"message": "Not Found"})
                    if not m2.group(2) and method == "GET":
                        return self._send(200, fake._pr_view(fn, pr))
                    if m2.group(2) and method == "PUT":
                        if pr["merged"]:
                            return self._send(405, {"message": "Pull Request is not mergeable"})
                        cur = fake.branch_sha(fn, pr["head"]["ref"])
                        if body.get("sha") and body["sha"] != cur:
                            return self._send(409, {"message": "Head branch was modified"})
                        meth = body.get("merge_method") or "merge"
                        if meth in fake.repos[fn].get("disallowed_methods", []):
                            return self._send(405, {"message": f"{meth.capitalize()} merges are not allowed on this repository."})
                        sha = fake._merge(fn, pr, meth)
                        if not sha:
                            pr["mergeable"] = False
                            return self._send(405, {"message": "Merge conflict"})
                        pr["head"]["sha"] = cur
                        pr.update(merged=True, state="closed", merge_commit_sha=sha)
                        return self._send(200, {"merged": True, "sha": sha})
                m3 = re.match(r"^/commits/([0-9a-f]+)/(check-runs|status)$", rest)
                if m3:
                    sha = m3.group(1)
                    if m3.group(2) == "check-runs":
                        runs = fake.checks.get(sha, [])
                        return self._send(200, {"total_count": len(runs), "check_runs": runs if int(q.get("page") or 1) == 1 else []})
                    st = fake.statuses.get(sha, [])
                    return self._send(200, {"state": "pending", "statuses": st})
                if rest == "/branches" and method == "GET":
                    refs = git(["for-each-ref", "--format=%(refname:short)", "refs/heads"], fake.repos[fn]["bare"]).stdout.split()
                    page = int(q.get("page") or 1)
                    return self._send(200, [{"name": b, "commit": {"sha": fake.branch_sha(fn, b)}} for b in refs] if page == 1 else [])
                mb = re.match(r"^/branches/([^/]+)$", rest)
                if mb and method == "GET":
                    sha = fake.branch_sha(fn, mb.group(1))
                    if not sha:
                        return self._send(404, {"message": "Branch not found"})
                    return self._send(200, {"name": mb.group(1), "commit": {"sha": sha}})
                m4 = re.match(r"^/branches/([^/]+)/protection/required_status_checks$", rest)
                if m4:
                    req = fake.required.get((fn, m4.group(1)), "absent")
                    if req == "absent":
                        return self._send(404, {"message": "Branch not protected"})
                    if req is None:
                        return self._send(403, {"message": "Resource not accessible"})
                    return self._send(200, {"contexts": req})
                m5 = re.match(r"^/actions/jobs/(\d+)/(logs|rerun)$", rest)
                if m5:
                    job = int(m5.group(1))
                    if m5.group(2) == "logs":
                        return self._send(200, text=fake.logs.get(job, "log line\n"))
                    fake.reruns.append(job)
                    return self._send(201, {})
                return self._send(404, {"message": "Not Found"})

            def do_GET(self):
                self._route("GET")

            def do_POST(self):
                self._route("POST")

            def do_PUT(self):
                self._route("PUT")

            def do_PATCH(self):
                self._route("PATCH")

        return H
