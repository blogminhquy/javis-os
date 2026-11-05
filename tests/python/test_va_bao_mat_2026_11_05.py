"""Security fixes from the 2026-11-05 audit (security-audit skill). Run by hand / CI:

    python tests/python/test_va_bao_mat_2026_11_05.py

No network. One check per finding, each pinned on the real code path, not on source text where avoidable:

  1. A run below Full access (a customer bot at "auto", an auto loop) cannot write files that run or configure code:
     plugins/<x>/plugin.yaml, Javis/loops, Javis/scripts, .git/config, .claude/settings.json. A customer bot cannot
     either, even at Full. The owner at Full still can.
  2. Work queued by a run below Full (javis_schedule, javis_task) is capped at that run's own level, and such a run
     cannot rewrite an existing scheduled job.
  3. /files/raw and /upload/raw serve html, xhtml, svg and xml under the share sandbox CSP; pdf and images unchanged.
  4. javis_add_mcp: op=add needs Full access, and customer bots never see the tool.
  5. The login-free local paths (/reminders...) refuse a browser request: non-loopback Host (DNS rebinding), Origin,
     Sec-Fetch-Site. A tool call on 127.0.0.1 still passes.
  6. <brain>/.grok/ (it holds the hub token) stays out of git and the GitHub backup, and an old commit of it is untracked.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-audit-1105-")

_fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + ("" if cond or not extra else "  " + str(extra)))
    if not cond:
        _fails.append(name)


# ============================================================
# 1. Protected write zones below Full access
# ============================================================
import mcp_hub  # noqa: E402

brain = Path(tempfile.mkdtemp(prefix="javis-audit-brain-"))
(brain / "notes").mkdir()


def _write(mode, rel, for_bot=False):
    tools, route = mcp_hub._builtin_tools(mode, str(brain), for_bot=for_bot)
    return asyncio.run(route["javis_write_file"]["call"]({"path": rel, "content": "enabled: true\n"}))


NGUY_HIEM = ["plugins/x/plugin.yaml", "plugins/x/plugin.py", "Javis/loops/x.md", "Javis/scripts/x.sh",
             ".git/config", ".claude/settings.json", ".grok/config.toml", "sub/.git/hooks/pre-commit"]
for rel in NGUY_HIEM:
    r = _write("auto", rel)
    check(f"1. auto cannot write {rel}", str(r).startswith("ERROR") and not (brain / rel).exists(), r)
r = _write("auto", "notes/nhap.md")
check("1. auto still writes an ordinary note", not str(r).startswith("ERROR") and (brain / "notes/nhap.md").is_file(), r)
r = _write("full", "plugins/y/plugin.yaml", for_bot=True)
check("1. a customer bot at Full cannot write plugins/", str(r).startswith("ERROR")
      and not (brain / "plugins/y/plugin.yaml").exists(), r)
r = _write("full", "plugins/z/plugin.yaml")
check("1. the owner at Full still writes plugins/ (unchanged)", not str(r).startswith("ERROR")
      and (brain / "plugins/z/plugin.yaml").is_file(), r)
check("1. a gated Team step keeps its own approval path (not refused by the new rule)",
      mcp_hub._ghi_vung_bao_ve(brain / "plugins/a.py", str(brain), None, "gated") == "")

# ============================================================
# 2. Queued work capped at the caller's level
# ============================================================
import plugins_host  # noqa: E402

cap = plugins_host._cap_job_level
a, why = cap("javis_schedule", {"op": "create", "name": "n"}, "auto")
check("2. auto + no level asked: the reminder is capped at auto", a.get("muc_quyen") == "auto" and not why, a)
a, why = cap("javis_schedule", {"op": "create", "muc_quyen": "full"}, "auto")
check("2. auto asking for full gets auto", a.get("muc_quyen") == "auto", a)
a, why = cap("javis_schedule", {"op": "create", "muc_quyen": "suggest"}, "auto")
check("2. a lighter level asked is kept", a.get("muc_quyen") == "suggest", a)
a, why = cap("javis_schedule", {"muc_quyen": "full"}, "suggest")
check("2. suggest caps at suggest (op defaults to create)", a.get("muc_quyen") == "suggest", a)
a, why = cap("javis_schedule", {"op": "update", "id": "r1", "prompt": "x"}, "auto")
check("2. auto cannot rewrite an existing scheduled job", why.startswith("ERROR"), why)
a, why = cap("javis_schedule", {"op": "create", "muc_quyen": "full"}, "full")
check("2. Full access unchanged", a.get("muc_quyen") == "full" and not why, a)
a, why = cap("javis_schedule", {"op": "update", "id": "r1"}, "full")
check("2. Full access may still update", not why)
a, why = cap("javis_schedule", {"op": "create"}, "gated")
check("2. gated Team step left to its approval gate", "muc_quyen" not in a and not why, a)
a, why = cap("javis_task", {"op": "add", "title": "t"}, "auto")
check("2. javis_task add at auto: mode capped (default was full)", a.get("mode") == "auto", a)
a, why = cap("javis_task", {"op": "list"}, "auto")
check("2. javis_task list untouched", "mode" not in a and not why, a)
a, why = cap("javis_web_search", {"q": "x"}, "auto")
check("2. other tools untouched", a == {"q": "x"} and not why, a)
check("2. the cap runs inside every plugin call (_make_call)",
      "_cap_job_level(name, args, mode)" in Path(SERVER, "plugins_host.py").read_text(encoding="utf-8"))

# ============================================================
# 4. javis_add_mcp
# ============================================================
check("4. javis_add_mcp is owner-only (hidden from customer bots)", "javis_add_mcp" in mcp_hub.OWNER_ONLY_TOOLS)
spec = importlib.util.spec_from_file_location("javis_connect_plugin",
                                              Path(ROOT, "system", "plugins", "javis-connect", "plugin.py"))
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
ghi = {}


class _Ctx:
    def register_tool(self, *a, **kw):
        ghi["tool"] = {"name": a[0], "min_mode": kw.get("min_mode"), "op_modes": kw.get("op_modes"),
                       "op_key": kw.get("op_key")}


mod.register(_Ctx())
t = ghi["tool"]
check("4. op=add needs Full access", plugins_host._required_mode(t, {"op": "add"}) == "full", t)
check("4. op=find still works at safe", plugins_host._required_mode(t, {"op": "find"}) == "safe", t)
check("4. an unknown op needs the strongest level", plugins_host._required_mode(t, {"op": "xoa"}) == "full", t)

# ============================================================
# 3 + 5. main.py: CSP on raw files, local tool exemption
# ============================================================
import main  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

raw = Path(tempfile.mkdtemp(prefix="javis-audit-raw-"))
for ten in ("x.html", "x.htm", "x.xhtml", "x.svg", "x.xml", "x.pdf", "x.png", "x.txt"):
    (raw / ten).write_bytes(b"<html><script>1</script></html>")
_goc = main._safe_serve_path
main._safe_serve_path = lambda b, rel: raw / rel
try:
    for ten in ("x.html", "x.htm", "x.xhtml", "x.svg", "x.xml"):
        r = main.raw_file_response("b", ten)
        check(f"3. {ten} served inline under the sandbox CSP",
              r.headers.get("content-security-policy") == main.share_render.CSP_HTML, dict(r.headers))
    for ten in ("x.pdf", "x.png", "x.txt"):
        r = main.raw_file_response("b", ten)
        check(f"3. {ten} unchanged (no CSP, pdf must still draw)", "content-security-policy" not in r.headers)
finally:
    main._safe_serve_path = _goc
_up = Path(SERVER, "main.py").read_text(encoding="utf-8").split("async def upload_raw", 1)[1].split("@app.", 1)[0]
check("3. /upload/raw goes through the same CSP helper", "_csp_neu_chay_script(resp, mt)" in _up)

main.cfgmod.gate_active = lambda: True
main.cfgmod.auth_enabled = lambda: True
local = TestClient(main.app, base_url="http://127.0.0.1:7777", client=("127.0.0.1", 50000))
BODY = {"text": "x", "delay_min": 5, "mode": "task", "muc_quyen": "full", "brain": "brain"}
r = local.post("/reminders", json=BODY)
check("5. a tool call on 127.0.0.1 still skips the login", r.status_code != 401, r.status_code)
r = local.get("/reminders")
check("5. GET from a tool still skips the login", r.status_code != 401, r.status_code)
rebind = TestClient(main.app, base_url="http://evil.example:7777", client=("127.0.0.1", 50000))
for path in main._AUTH_LOCAL_EXACT:
    r = rebind.post(path, json=BODY, headers={"origin": "http://evil.example:7777"})
    check(f"5. {path}: rebound page (Host evil.example) needs the login", r.status_code in (401, 403), r.status_code)
r = rebind.get("/reminders", headers={"sec-fetch-site": "same-origin"})
check("5. GET /reminders from a rebound page needs the login", r.status_code in (401, 403), r.status_code)
r = local.post("/reminders", json=BODY, headers={"origin": "http://127.0.0.1:7777"})
check("5. a loopback request carrying Origin (a browser page) needs the login", r.status_code == 401, r.status_code)
r = local.get("/reminders", headers={"sec-fetch-site": "cross-site"})
check("5. a loopback request carrying Sec-Fetch-Site needs the login", r.status_code == 401, r.status_code)

# ============================================================
# 6. .grok/ out of git and the backup
# ============================================================
import git_brain  # noqa: E402

check("6. .gitignore block ignores .grok/", ".grok/" in git_brain._GITIGNORE_BODY)
check("6. the backup skips .grok/", "/.grok/" in git_brain._BACKUP_SKIP_SUBSTR)
if shutil.which("git"):
    repo = Path(tempfile.mkdtemp(prefix="javis-audit-git-"))
    env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t", GIT_COMMITTER_NAME="t",
               GIT_COMMITTER_EMAIL="t@t")
    subprocess.run(["git", "init", "-q", str(repo)], check=True, env=env)
    (repo / ".grok").mkdir()
    (repo / ".grok" / "config.toml").write_text("Authorization = 'Bearer x'\n", encoding="utf-8")
    (repo / "a.md").write_text("a\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True, env=env)
    subprocess.run(["git", "-C", str(repo), "commit", "-qm", "old"], check=True, env=env)
    git_brain.untrack_media(str(repo))
    tracked = subprocess.run(["git", "-C", str(repo), "ls-files"], capture_output=True, text=True).stdout
    check("6. an old commit of .grok/ is untracked, the file stays on disk",
          ".grok/config.toml" not in tracked and "a.md" in tracked
          and (repo / ".grok" / "config.toml").is_file(), tracked)

print()
if _fails:
    print(f"FAIL {len(_fails)} test: " + ", ".join(_fails))
    sys.exit(1)
print("TẤT CẢ PASS")
