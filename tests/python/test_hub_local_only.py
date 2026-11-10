"""The MCP hub answers this machine only, and its file tools never hand out the hub bearer (security, 2026-11-10).

    python tests/run.py hub_local_only

What was wrong: `/hub/mcp` is a login-exempt route protected by one long-lived bearer. Engine configs keep that bearer
on disk, some of them inside a brain (`<brain>/.grok/config.toml`), and `javis_read_file` returned such a file as is.
With the bearer, a caller from the Internet picked its own permission level and its own "brain" through headers: the
state directory as the brain gave it `.sessions.json` to read and `plugins/` to write.

Pinned here:
  1. `/hub/mcp` refuses a caller that is not on this machine before it looks at the bearer.
  2. The X-Javis-Vault header cannot name the state directory, a code folder inside it, or a folder above it.
  3. `javis_read_file` hides the bearer in what it returns and refuses Javis's secret files.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import os
import sys
import tempfile
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="javis-hub-local-"))
_STATE = _TMP / "state"
_BRAINS = _TMP / "brains"
BRAIN = _BRAINS / "Brain Default"
(BRAIN / ".grok").mkdir(parents=True, exist_ok=True)
(_STATE / "plugins").mkdir(parents=True, exist_ok=True)
os.environ["JAVIS_STATE_DIR"] = str(_STATE)
os.environ["BRAINS_DIR"] = str(_BRAINS)
os.environ["JAVIS_SESSIONS_DB"] = str(_TMP / "conversations.db")
os.environ.pop("JAVIS_ADMIN_PASSWORD", None)

import mcp_hub  # noqa: E402
import secret_guard  # noqa: E402

_fails = []


def check(name, cond, extra=None):
    print(("ok   " if cond else "FAIL ") + name + ("" if cond or extra is None else f"  [{extra}]"))
    if not cond:
        _fails.append(name)


TOKEN = mcp_hub.hub_token()

# ---- 2. the vault header ----
check("a brain under BRAINS_DIR is accepted", not mcp_hub.vault_header_refused(BRAIN))
check("the state directory is not a brain", mcp_hub.vault_header_refused(_STATE))
check("a folder above the state directory is not a brain", mcp_hub.vault_header_refused(_TMP))
check("the filesystem root is not a brain", mcp_hub.vault_header_refused("/"))
check("the plugin folder of the state directory is not a brain", mcp_hub.vault_header_refused(_STATE / "plugins"))
_outside = Path(tempfile.mkdtemp(prefix="javis-hub-local-other-"))
check("a brain kept anywhere else (path:<folder>) is accepted", not mcp_hub.vault_header_refused(_outside))
root, source, broken = mcp_hub.resolve_vault(str(_STATE))
check("resolve_vault does not take the state directory from the header",
      source != "header" and root != str(_STATE.resolve()) and broken == str(_STATE), (root, source, broken))
root, source, broken = mcp_hub.resolve_vault(str(BRAIN))
check("resolve_vault still takes a real brain from the header",
      source == "header" and root == str(BRAIN.resolve()) and not broken, (root, source, broken))

# BRAINS_DIR inside the state directory is a legal layout: those brains stay valid, BRAINS_DIR itself does not.
_nested = _STATE / "brains"
(_nested / "Shop").mkdir(parents=True, exist_ok=True)
os.environ["BRAINS_DIR"] = str(_nested)
check("a brain under a BRAINS_DIR nested in the state directory is accepted",
      not mcp_hub.vault_header_refused(_nested / "Shop"))
check("that nested BRAINS_DIR itself is refused", mcp_hub.vault_header_refused(_nested))
os.environ["BRAINS_DIR"] = str(_BRAINS)

# ---- 3. the file tool ----
(BRAIN / ".grok" / "config.toml").write_text(
    '[mcp_servers.javis]\nurl = "http://127.0.0.1:7777/hub/mcp"\n\n[mcp_servers.javis.headers]\n'
    f'Authorization = "Bearer {TOKEN}"\n', encoding="utf-8")
(BRAIN / "note.md").write_text("plain note", encoding="utf-8")
(BRAIN / ".mcp_hub_full.json").write_text('{"x": 1}', encoding="utf-8")


async def read(path, for_bot=False, mode="full"):
    _tools, route = mcp_hub._builtin_tools(mode, str(BRAIN), for_bot=for_bot)
    return await route["javis_read_file"]["call"]({"path": path})

for label, kw in (("owner run", {}), ("customer bot", {"for_bot": True, "mode": "auto"})):
    out = asyncio.run(read(".grok/config.toml", **kw))
    check(f"{label}: the engine config is returned without the bearer",
          TOKEN not in out and "hub token hidden" in out and "mcp_servers.javis" in out, out[:200])
check("an ordinary note is unchanged", asyncio.run(read("note.md")) == "plain note")
out = asyncio.run(read(".mcp_hub_full.json"))
check("a per-run hub config is refused by the secret tripwire", '"x"' not in out and "CHẶN" in out, out[:120])
check("secret_guard names the per-run hub configs", secret_guard.check_text("cat /data/state/.mcp_hub_auto_ab12.json"))
check("hide_hub_token leaves other text alone", mcp_hub.hide_hub_token("abc") == "abc" and mcp_hub.hide_hub_token(None) is None)

# ---- 1. the route ----
import main  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

BODY = {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}
AUTH = {"Authorization": f"Bearer {TOKEN}", "X-Javis-Mode": "full"}

remote = TestClient(main.app, base_url="http://localhost", client=("203.0.113.9", 40000))
r = remote.post("/hub/mcp", json=BODY, headers=AUTH)
check("a remote caller holding the bearer gets 403", r.status_code == 403, r.status_code)
r = remote.post("/hub/mcp", json=BODY, headers={**AUTH, "X-Javis-Vault": str(_STATE)})
check("and cannot name the state directory as its brain either", r.status_code == 403, r.status_code)

local = TestClient(main.app, base_url="http://127.0.0.1:7777", client=("127.0.0.1", 40000))
r = local.post("/hub/mcp", json=BODY, headers={**AUTH, "X-Forwarded-For": "203.0.113.9"})
check("a call relayed by a tunnel or proxy on this machine gets 403", r.status_code == 403, r.status_code)
r = local.post("/hub/mcp", json=BODY, headers={"Authorization": "Bearer wrong"})
check("a local caller still needs the bearer", r.status_code == 401, r.status_code)
r = local.post("/hub/mcp", json=BODY, headers={**AUTH, "X-Javis-Vault": str(BRAIN)})
check("a local engine with the bearer is answered", r.status_code == 200 and "result" in r.json(), r.text[:200])

if _fails:
    print(f"\nFAIL - {len(_fails)}: " + ", ".join(_fails))
    sys.exit(1)
print("\nOK - test_hub_local_only")
