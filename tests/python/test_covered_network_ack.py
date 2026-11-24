"""A pack channel cannot quietly answer a network a core channel already answers (duplicate replies).

    python tests/run.py covered_network_ack

No network. Messenger answers Facebook and Instagram. A pack channel `bridge` (temp state dir, consented) bridges
many networks, like Zernio; its verify reports the account's `network`. Guarded here, through the real routes:
1. `covered_networks()` lists what core channels answer (Messenger: facebook + instagram, no pack channel, no `api`),
   and the dashboard channel list carries `networks` for core channels only.
2. Creating an account on a covered network without `dup_ack=<network>` is a 400 `network_covered_by_core`; with it,
   the account is created and `meta.network` recorded (and shown, whatever PUBLIC_META says).
3. An uncovered network (TikTok) needs no acknowledgement.
4. An account saved before the core recorded a network stays editable without the box (never locked out), and the
   edit records the network; after that an unchanged network is not asked again.
5. `options.network` of a declared select survives `_token_form`.
"""
from _paths import ROOT, SERVER, DASHBOARD  # noqa: E402,F401
import json
import os
import tempfile
from pathlib import Path

STATE = tempfile.mkdtemp(prefix="javis-covered-net-")
os.environ["JAVIS_STATE_DIR"] = STATE

import main  # noqa: E402
import packs  # noqa: E402
import channels  # noqa: E402
import channel_accounts  # noqa: E402
from plugins_host import _digest_thu_muc  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(extra)[:400] + "]") if extra and not cond else ""))
    if not cond:
        fails.append(name)


BRIDGE = '''
from channels import KenhSpec
SPEC = KenhSpec(id="bridge", nhan="Bridge", kind="bot")
PUBLIC_META = ("platform",)
NETWORKS = ("instagram",)      # ignored: only CORE channels cover a network

class Transport:
    pass

def prepare_token(new, old=None):
    return {"ok": True, "token": new if new.startswith("P:") else "P:" + new}

async def verify_token(token):
    user = token[2:]
    net = {"ig": "instagram", "fb": "facebook", "tt": "tiktok"}.get(user.split("-")[0], "")
    return {"ok": True, "username": user, "network": net, "meta": {"platform": net}}
'''

d = Path(STATE) / "packs" / "bridge-pack"
(d / "channels").mkdir(parents=True)
(d / "javis-pack.yaml").write_text(
    "format: javis-pack\nspec: 1\nid: bridge-pack\nversion: 1.0.0\nname: {vi: B, en: B}\ndescription: {vi: B}\n"
    "compat: {app: \">=0.1.0\"}\nprovides:\n  channels: [channels/bridge.py]\n", encoding="utf-8")
(d / "channels" / "bridge.py").write_text(BRIDGE, encoding="utf-8")
packs.LEDGER.write_text(json.dumps({"bridge-pack": {"enabled": True, "code_digest": _digest_thu_muc(d)}}))
packs.invalidate()
channels.reload_registry()
check("bridge pack channel loaded", channels.spec("bridge") is not None, channels.ids())

# 1. What core channels cover.
cov = channels.covered_networks()
check("1. Messenger covers facebook and instagram", cov.get("facebook") == "messenger" and cov.get("instagram") == "messenger", cov)
check("1. Telegram covers telegram (default: its logo)", cov.get("telegram") == "telegram", cov)
check("1. the internal API covers nothing", "api" not in cov, cov)
check("1. a pack channel never covers a network", "bridge" not in cov.values(), cov)
ui = {k["id"]: k for k in channels.cho_giao_dien()}
check("1. dashboard list: networks on core channels only", ui["messenger"]["networks"] == ["facebook", "instagram"]
      and ui["bridge"]["networks"] == [], (ui["messenger"].get("networks"), ui["bridge"].get("networks")))

c = TestClient(main.app, base_url="http://127.0.0.1:8080")

# 2. Covered network needs the acknowledgement.
r = c.post("/channels/accounts", data={"channel": "bridge", "token": "ig-shop", "label": "IG"})
check("2. Instagram without dup_ack is refused", r.status_code == 400 and r.json().get("code") == "network_covered_by_core", r.text)
check("2. the refusal names the core channel", "Messenger" in r.json().get("error", ""), r.text)
check("2. nothing was stored", not channel_accounts.list_accounts("bridge"))
r = c.post("/channels/accounts", data={"channel": "bridge", "token": "ig-shop", "label": "IG", "dup_ack": "facebook"})
check("2. an ack for another network does not count", r.status_code == 400, r.text)
r = c.post("/channels/accounts", data={"channel": "bridge", "token": "ig-shop", "label": "IG", "dup_ack": "Instagram"})
check("2. with dup_ack the account is created", r.status_code == 200 and r.json().get("ok"), r.text)
acc = r.json().get("account") or {}
check("2. network recorded and visible despite PUBLIC_META", (acc.get("meta") or {}).get("network") == "instagram", acc)

# 3. Uncovered network.
r = c.post("/channels/accounts", data={"channel": "bridge", "token": "tt-shop", "label": "TT"})
check("3. TikTok needs no acknowledgement", r.status_code == 200 and r.json().get("ok"), r.text)

# 4. Edits.
legacy, err = channel_accounts.create_account({"channel": "bridge", "token": "P:fb-old", "label": "old",
                                               "external_id": "fb-old", "meta": {"platform": "facebook"}})
check("4. legacy account stored without a network", not err and not (channel_accounts.get_account(legacy)["meta"] or {}).get("network"), err)
r = c.post(f"/channels/accounts/{legacy}/update", data={"token": "fb-old"})
check("4. a legacy account stays editable without the box", r.status_code == 200, r.text)
check("4. the edit records its network", (channel_accounts.get_account(legacy)["meta"] or {}).get("network") == "facebook",
      channel_accounts.get_account(legacy))
r = c.post(f"/channels/accounts/{legacy}/update", data={"token": "fb-old"})
check("4. an unchanged recorded network is not asked again", r.status_code == 200, r.text)
tt = next(a for a in channel_accounts.list_accounts("bridge") if a.get("external_id") == "tt-shop")
r = c.post(f"/channels/accounts/{tt['id']}/update", data={"token": "ig-moved"})
check("4. an edit that moves a TikTok account to Instagram needs the ack", r.status_code == 400
      and r.json().get("code") == "network_covered_by_core", r.text)
r = c.post(f"/channels/accounts/{tt['id']}/update", data={"token": "ig-moved", "dup_ack": "instagram"})
check("4. with the ack the move goes through", r.status_code == 200, r.text)

# 5. Declared select keeps `options.network`.
import types  # noqa: E402
m = types.ModuleType("stand_in")
m.TOKEN_FORM = {"fields": [{"key": "account_id", "type": "select", "label": "A",
                            "options": {"url": "/ext/bridge-pack/accounts", "list": "accounts", "network": "platform"}},
                           {"key": "b", "type": "select", "label": "B",
                            "options": {"url": "/ext/bridge-pack/x", "network": "Bad Key"}}]}
tf = {f["key"]: f for f in channels._token_form(m)["fields"]}
check("5. options.network kept", tf["account_id"]["options"]["network"] == "platform", tf)
check("5. a bad options.network is dropped", tf["b"]["options"]["network"] == "", tf)

print("\n" + ("ALL OK" if not fails else f"{len(fails)} FAIL: {fails}"))
raise SystemExit(1 if fails else 0)
