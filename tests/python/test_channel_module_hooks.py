"""Optional channel-module hooks that let a pack channel live without `if channel == ...` in the core.

    python tests/run.py channel_module_hooks

No network. A pack channel `demo` (written into a temp state dir, consented in the ledger) exercises, through the
real routes: `prepare_token` (rewrite + refuse, before verify), verify `meta` + `code` passthrough, `PUBLIC_META`,
`clean_settings` on a channel that is not generated-key, `webhook_info`, and in chatbot_runtime the
`webhook_active` / `javis_bot_id` / `_defer_delivery` contract.
"""
from _paths import ROOT, SERVER, DASHBOARD  # noqa: E402,F401
import json
import os
import tempfile
from pathlib import Path

STATE = tempfile.mkdtemp(prefix="javis-chan-hooks-")
os.environ["JAVIS_STATE_DIR"] = STATE

import main  # noqa: E402
import packs  # noqa: E402
import channels  # noqa: E402
import channel_accounts  # noqa: E402
import chatbot_runtime  # noqa: E402
from plugins_host import _digest_thu_muc  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(extra)[:400] + "]") if extra and not cond else ""))
    if not cond:
        fails.append(name)


DEMO = '''
from channels import KenhSpec
SPEC = KenhSpec(id="demo", nhan="Demo", kind="bot")
PUBLIC_META = ("platform", "who")

class Transport:
    pass

def prepare_token(new, old=None):
    if new == "bad":
        return {"ok": False, "error": "no good", "code": "missing_api_key"}
    if old is not None and old.split(":")[1] != new.split(":")[0]:
        return {"ok": False, "error": "other id", "code": "provider_identity_changed"}
    return {"ok": True, "token": new if new.startswith("P") else "P:" + new}

async def verify_token(token):
    if not token.startswith("P:"):
        return {"ok": False, "error": "not prepared", "code": "not_prepared"}
    if token == "P:reject":
        return {"ok": False, "error": "provider said no", "code": "provider_no"}
    return {"ok": True, "username": token[2:], "meta": {"platform": "x", "who": token[2:], "secret_note": "hide"}}

def account_settings_spec():
    return [{"key": "pause", "nhan": "Pause", "min": 1, "max": 60, "default": 1}]
def clean_settings(data):
    d = json.loads(data or "{}")
    if not isinstance(d.get("pause", 1), int):
        return None, "pause must be a number"
    return {"pause": d.get("pause", 1)}, ""

async def webhook_info(base, params):
    if params.get("fail"):
        return {"ok": False, "error": "upstream", "status": 502}
    return {"webhook_url": base + "/ext/demo/webhook", "ws": params.get("ws", "")}
'''.replace("from channels import", "import json\nfrom channels import")

d = Path(STATE) / "packs" / "demo-pack"
(d / "channels").mkdir(parents=True)
(d / "javis-pack.yaml").write_text(
    "format: javis-pack\nspec: 1\nid: demo-pack\nversion: 1.0.0\nname: {vi: D, en: D}\ndescription: {vi: D}\n"
    "compat: {app: \">=0.1.0\"}\nprovides:\n  channels: [channels/demo.py]\n", encoding="utf-8")
(d / "channels" / "demo.py").write_text(DEMO, encoding="utf-8")
packs.LEDGER.write_text(json.dumps({"demo-pack": {"enabled": True, "code_digest": _digest_thu_muc(d)}}))
packs.invalidate()
channels.reload_registry()
check("demo pack channel loaded", channels.spec("demo") is not None, channels.ids())

c = TestClient(main.app, base_url="http://127.0.0.1:8080")

# prepare_token + verify meta + PUBLIC_META
r = c.post("/channels/accounts", data={"channel": "demo", "token": "bad", "label": "x"})
check("prepare_token refusal is a 400 with its code", r.status_code == 400 and r.json().get("code") == "missing_api_key", r.text)
r = c.post("/channels/accounts", data={"channel": "demo", "token": "reject", "label": "x", "bot_username": "forged"})
check("verify refusal keeps the module's code, even with a username sent", r.status_code == 400
      and r.json().get("code") == "provider_no", r.text)
r = c.post("/channels/accounts", data={"channel": "DEMO", "token": "alice", "label": "A"})
j = r.json()
check("account created through prepare + verify", r.status_code == 200 and j.get("ok"), r.text)
aid = j.get("id", "")
check("stored token is the prepared one", channel_accounts.get_token(aid) == "P:alice", channel_accounts.get_token(aid))
acc = j.get("account") or {}
check("verify meta stored, but only PUBLIC_META leaves", acc.get("meta") == {"platform": "x", "who": "alice"}, acc.get("meta"))

# update: identity guard, settings for a non-generated channel
r = c.post(f"/channels/accounts/{aid}/update", data={"token": "bob"})
check("edit to another provider id is refused", r.status_code == 400 and r.json().get("code") == "provider_identity_changed", r.text)
check("refused edit keeps the old token", channel_accounts.get_token(aid) == "P:alice")
r = c.post(f"/channels/accounts/{aid}/update", data={"settings": json.dumps({"pause": 7})})
check("clean_settings applies to a non-generated channel", r.status_code == 200
      and (channel_accounts.get_account(aid).get("meta") or {}).get("pause") == 7, r.text)
r = c.post(f"/channels/accounts/{aid}/update", data={"settings": json.dumps({"pause": "x"})})
check("bad settings are a 400", r.status_code == 400, r.text)

# webhook_info
r = c.get("/channels/webhook-info", params={"channel": "demo", "ws": "w1"})
check("webhook_info hook answers", r.status_code == 200 and r.json().get("webhook_url", "").endswith("/ext/demo/webhook")
      and r.json().get("ws") == "w1" and r.json().get("ok") is True, r.text)
r = c.get("/channels/webhook-info", params={"channel": "demo", "fail": "1"})
check("webhook_info error keeps its status", r.status_code == 502 and "status" not in r.json(), r.text)
r = c.get("/channels/webhook-info", params={"channel": "telegram"})
check("a channel without the hook still says no webhook", r.status_code == 400, r.text)

# chatbot_runtime contract
class Hook:
    webhook_active = True
    status = "polling"
    last_error = ""
check("webhook transport with no task counts as running", chatbot_runtime._trang_thai_poller(Hook()).get("state") == "running",
      chatbot_runtime._trang_thai_poller(Hook()))
src = (SERVER / "chatbot_runtime.py").read_text(encoding="utf-8")
check("runtime hands the Javis bot id as javis_bot_id (never bot_id)", "tb.javis_bot_id = bot_id" in src and "tb.bot_id = bot_id" not in src)
check("runtime skips its own receipt when the transport defers it", '(meta or {}).get("_defer_delivery")' in src)
check("no channel-specific branch left for zernio in the core", "zernio" not in src.lower()
      and "zernio" not in (SERVER / "routes" / "channels.py").read_text(encoding="utf-8").lower())

print()
print("FAILED: " + ", ".join(fails) if fails else "all ok")
raise SystemExit(1 if fails else 0)
