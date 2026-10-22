"""0.274.0: webhook security (webhook platform M4): per-provider signatures, encrypted secrets with key rotation,
tools through the hub dispatcher with the owner's approval, idempotency from the provider's own delivery id.

    python tests/run.py webhook_security_m4      (no network, no model: the tool dispatcher is a fake)

What is proven here:
  1. secrets: AES-GCM, files mode 600, bound to their name, survive a rotation (also one cut in the middle), the
     environment key works, a missing key fails the branch cleanly; webhooks.json never holds a plain secret; a
     plain secret from before M4 is sealed at start; deleting a hook or a header deletes its secret;
  2. signatures (Stripe, GitHub, Shopify, generic HMAC with a replay window, Systeme.io synthetic fixture) are
     checked on the RAW body BEFORE anything is stored: a bad one answers 401 and keeps nothing; POSCake is refused
     (its contract is not known);
  3. the provider's delivery id dedups its retries; `_event` comes from the adapter and cannot be forged by the
     payload;
  4. a tool action waits for the owner's approval, runs once through the dispatcher at the hook's CURRENT level with
     templated arguments (the payload is substituted, never evaluated), a rejection cancels it, a tool error fails
     only that branch, a hung tool is unknown.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import base64
import hashlib
import hmac
import json
import os
import stat
import sys
import tempfile
import time
from pathlib import Path

STATE = Path(tempfile.mkdtemp(prefix="javis-wh-m4-"))
os.environ["JAVIS_STATE_DIR"] = str(STATE)
os.environ["JAVIS_NO_REAL_JUDGE_ENGINE"] = "1"
os.environ["JAVIS_WH_NO_NETWORK"] = "1"
os.environ.pop("JAVIS_WH_MASTER_KEY", None)
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import webhook_actions as wa  # noqa: E402
import webhook_secrets as wsec  # noqa: E402
import webhook_store as ws  # noqa: E402
import webhook_triggers as wt  # noqa: E402
import webhook_verify as wv  # noqa: E402

fails = []


def check(name, cond, them=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(them) + "]") if them and not cond else ""))
    if not cond:
        fails.append(name)


def mode(p: Path) -> int:
    return stat.S_IMODE(p.stat().st_mode)


# ---- 1. secrets ----
SD = Path(tempfile.mkdtemp(prefix="m4-vault-"))
v = wsec.Vault(SD)
v.put("wh_1/a/crm/X-Api-Key", "sk-live-SECRET")
check("vault: round trip", v.get("wh_1/a/crm/X-Api-Key") == "sk-live-SECRET")
raw = (SD / "webhook_secrets.json").read_text()
check("vault: the value is not in the file in clear", "sk-live-SECRET" not in raw)
check("vault: both files are mode 600", mode(SD / "webhook_secrets.json") == 0o600 and mode(SD / "webhook_keys.json") == 0o600,
      (oct(mode(SD / "webhook_secrets.json")), oct(mode(SD / "webhook_keys.json"))))
d = json.loads(raw)
d["items"]["wh_2/verify"] = d["items"]["wh_1/a/crm/X-Api-Key"]
(SD / "webhook_secrets.json").write_text(json.dumps(d))
try:
    v.get("wh_2/verify")
    swapped = True
except wsec.SecretError:
    swapped = False
check("vault: a ciphertext copied under another name does not decrypt (name is bound)", not swapped)
v.put("wh_2/verify", "whsec_abc12345")
keys_before = json.loads((SD / "webhook_keys.json").read_text())
res = v.rotate()
keys_after = json.loads((SD / "webhook_keys.json").read_text())
check("rotate: new active key, old one dropped, every secret re-encrypted and still readable",
      res["rewrapped"] == 2 and keys_after["active"] != keys_before["active"] and list(keys_after["keys"]) == [keys_after["active"]]
      and v.get("wh_1/a/crm/X-Api-Key") == "sk-live-SECRET" and v.get("wh_2/verify") == "whsec_abc12345")
# a rotation cut after step 1 (both keys in the file, secrets still under the old key): still readable
old_kid = keys_after["active"]
new = {"active": "knew", "keys": dict(keys_after["keys"], knew=base64.b64encode(os.urandom(32)).decode())}
(SD / "webhook_keys.json").write_text(json.dumps(new))
check("rotate cut in the middle: every secret still decrypts with the key that sealed it",
      v.get("wh_1/a/crm/X-Api-Key") == "sk-live-SECRET")
(SD / "webhook_keys.json").write_text(json.dumps({"active": "knew", "keys": {"knew": new["keys"]["knew"]}}))
try:
    v.get("wh_1/a/crm/X-Api-Key")
    lost_ok = False
except wsec.SecretError as e:
    lost_ok = "missing" in str(e)
check("a lost key gives a clear error, never a wrong value", lost_ok)
os.environ["JAVIS_WH_MASTER_KEY"] = base64.b64encode(b"k" * 32).decode()
ve = wsec.Vault(Path(tempfile.mkdtemp(prefix="m4-env-")))
ve.put("a/b", "v1")
check("JAVIS_WH_MASTER_KEY: used instead of a key file", ve.get("a/b") == "v1" and not (ve.dir / "webhook_keys.json").exists())
try:
    ve.rotate()
    env_rot = False
except wsec.SecretError as e:
    env_rot = "rotate it there" in str(e)
check("JAVIS_WH_MASTER_KEY: rotation refused (rotate the variable)", env_rot)
del os.environ["JAVIS_WH_MASTER_KEY"]
check("secret names are restricted (no spaces or newlines)", wsec.NAME_RE.match("a b") is None and wsec.NAME_RE.match("a\nb") is None)

# ---- 2. signatures ----
BODY = b'{"id":"evt_1","type":"invoice.paid","data":{"object":{"amount":5000}}}'
SEC = "whsec_test_secret_123"
now = time.time()


def stripe_sig(body, secret=SEC, t=None):
    t = int(now if t is None else t)
    return f"t={t},v1=" + hmac.new(secret.encode(), f"{t}.".encode() + body, hashlib.sha256).hexdigest()


S = {"provider": "stripe", "secret": SEC}
check("Stripe: valid", wv.verify(S, SEC, {"stripe-signature": stripe_sig(BODY)}, BODY, now)[0])
check("Stripe: one of several v1 values may match", wv.verify(S, SEC, {"stripe-signature": stripe_sig(BODY) + ",v1=deadbeef"}, BODY, now)[0])
check("Stripe: a changed body fails", not wv.verify(S, SEC, {"stripe-signature": stripe_sig(BODY)}, BODY + b" ", now)[0])
check("Stripe: an old timestamp fails (replay window)", "replay" in wv.verify(S, SEC, {"stripe-signature": stripe_sig(BODY, t=now - 600)}, BODY, now)[1])
check("Stripe: a missing header fails", not wv.verify(S, SEC, {}, BODY, now)[0])
gh = "sha256=" + hmac.new(SEC.encode(), BODY, hashlib.sha256).hexdigest()
check("GitHub: valid and invalid", wv.verify({"provider": "github"}, SEC, {"x-hub-signature-256": gh}, BODY)[0]
      and not wv.verify({"provider": "github"}, SEC, {"x-hub-signature-256": gh[:-1] + "0"}, BODY)[0])
sh = base64.b64encode(hmac.new(SEC.encode(), BODY, hashlib.sha256).digest()).decode()
check("Shopify: valid and invalid", wv.verify({"provider": "shopify"}, SEC, {"x-shopify-hmac-sha256": sh}, BODY)[0]
      and not wv.verify({"provider": "shopify"}, SEC, {"x-shopify-hmac-sha256": "x" + sh[1:]}, BODY)[0])
G = wv.validate({"provider": "hmac_sha256", "secret": SEC, "header": "X-Signature", "encoding": "base64", "prefix": "sha256=",
                 "timestamp_header": "X-Timestamp", "tolerance_s": 120})
ts = str(int(now))
gs = "sha256=" + base64.b64encode(hmac.new(SEC.encode(), ts.encode() + b"." + BODY, hashlib.sha256).digest()).decode()
check("generic HMAC: base64, prefix, timestamp inside the window", wv.verify(G, SEC, {"x-signature": gs, "x-timestamp": ts}, BODY, now)[0])
check("generic HMAC: outside the window fails", not wv.verify(G, SEC, {"x-signature": gs, "x-timestamp": ts}, BODY, now + 500)[0])
SYS_BODY = json.dumps({"type": "CONTACT_CREATED", "data": {"contact": {"email": "lan@example.com", "fields": [
    {"slug": "first_name", "value": "Lan"}, {"slug": "phone_number", "value": "0912345678"}]}}}).encode()
ss = hmac.new(SEC.encode(), SYS_BODY, hashlib.sha256).hexdigest()
check("Systeme.io (synthetic fixture, assumed scheme): valid and invalid",
      wv.verify({"provider": "systeme_io"}, SEC, {"x-webhook-signature": ss}, SYS_BODY)[0]
      and not wv.verify({"provider": "systeme_io"}, SEC, {"x-webhook-signature": "00" + ss[2:]}, SYS_BODY)[0])
n = wv.normalize("systeme_io", {"x-webhook-event": "CONTACT_CREATED", "x-webhook-message-id": "m-1",
                                 "x-webhook-attempt-id": "a-7", "x-webhook-id": "a-7"}, json.loads(SYS_BODY))
check("Systeme.io normalisation: type, the MESSAGE id (stable across retries, spec §10), never the attempt id, contact",
      n["type"] == "contact.created" and n["id"] == "m-1"
      and n["contact"] == {"email": "lan@example.com", "first_name": "Lan", "phone_number": "0912345678"}, n)
check("Systeme.io is marked unverified, nothing is marked production verified",
      wv.ADAPTER_STATUS["systeme_io"] == "unverified" and "production" not in json.dumps(wv.ADAPTER_STATUS))
try:
    wv.validate({"provider": "poscake", "secret": "x" * 10})
    pos = ""
except wv.VerifyError as e:
    pos = str(e)
check("POSCake: refused with the reason (contract not known, not guessed)", "not known" in pos)
try:
    wv.validate({"provider": "github", "secret": "short"})
    weak = False
except wv.VerifyError:
    weak = True
check("verify: a secret under 8 characters is refused", weak)

# ---- through the feature ----
FEAT = Path(tempfile.mkdtemp(prefix="m4-feat-"))
calls_ai, sent, tool_calls = [], [], []
tool_answer = {"v": "Đã tạo đơn POS #77"}


async def run_task(brain, text, level):
    calls_ai.append(level)
    return "ok", ""


async def no_wf(*a, **k):
    return "", "", False


async def send(chat_id, text, viec=None, web="", brain="", dedup=""):
    sent.append(text)
    return True, ""


async def call_tool(brain, level, name, args):
    tool_calls.append({"brain": brain, "level": level, "name": name, "args": args})
    if tool_answer["v"] == "HANG":
        await asyncio.sleep(5)
    return tool_answer["v"]


def make(**kw):
    deps = dict(state_dir=lambda: FEAT, run_task=run_task, run_workflow=no_wf, send=send, base_url=lambda _r: "",
                workflow_exists=lambda b, s: True, call_tool=call_tool, resolve=lambda h: ["93.184.216.34"])
    deps.update(kw)
    return wt.WebhookFeature(wt.WebhookDeps(**deps))


async def main():
    f = make()
    st = f.store()
    h, tok, err = f.create("/b1", name="Stripe", target="task", text="Ghi", level="full",
                           verify={"provider": "stripe", "secret": SEC},
                           actions=[{"id": "crm", "kind": "http", "url": "https://crm.example/h", "headers": {"X-Api-Key": "sk-PLAIN"}},
                                    {"id": "ai", "kind": "ai"}])
    js = json.dumps([dict(r) for r in st._db.execute("SELECT config FROM hooks")] +
                    [dict(r) for r in st._db.execute("SELECT config FROM hook_revisions")])
    check("create: the stored hook and its revisions hold references only, no secret in clear",
          not err and SEC not in js and "sk-PLAIN" not in js and '$secret' in js, err)
    view = f.view(f._find(f._load(), h["id"]))
    check("view: the signing secret is masked and the adapter status shown", view["verify"]["secret"] == "••••"
          and view["adapter_status"] == "spec" and SEC not in json.dumps(view))

    code, r = await f.accept(h["id"], tok, BODY, "application/json", "", headers={"stripe-signature": "t=1,v1=00"})
    check("bad signature: 401, nothing stored", code == 401 and st._db.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 0
          and st._db.execute("SELECT COUNT(*) FROM dedup").fetchone()[0] == 0)
    code, r = await f.accept(h["id"], "wrong-token", BODY, "application/json", "", headers={"stripe-signature": stripe_sig(BODY)})
    check("the Javis token is still required before the signature", code == 401)
    f._kick = lambda: None
    code, r1 = await f.accept(h["id"], tok, BODY, "application/json", "", headers={"stripe-signature": stripe_sig(BODY)})
    check("good signature: accepted", code == 202, r1)
    code, r2 = await f.accept(h["id"], tok, BODY, "application/json", "", headers={"stripe-signature": stripe_sig(BODY)})
    check("Stripe's retry of the same event id is a duplicate (provider delivery id as idempotency key)",
          code == 200 and r2.get("duplicate") and r2["run_id"] == r1["run_id"], r2)
    tr = st.get(r1["run_id"])["trace"]
    check("the normalised event is in the trace", tr.get("event", {}).get("type") == "invoice.paid", tr)
    del f._kick

    # update with the masked secret keeps it; a removed header deletes its vault entry
    names_before = f.vault.names()
    f.update(h["id"], {"verify": {"provider": "stripe", "secret": "••••"},
                       "actions": [{"id": "ai", "kind": "ai"}]})
    check("update with the masked secret keeps it", f._secret(f._find(f._load(), h["id"])["verify"]["secret"]) == SEC)
    check("a header removed from the hook is deleted from the vault",
          any("/a/crm/" in n for n in names_before) and not any("/a/crm/" in n for n in f.vault.names()))
    f.delete(h["id"])
    check("deleting the hook deletes its secrets", not any(n.startswith(h["id"]) for n in f.vault.names()))

    # _event cannot be forged by the payload of a hook without a provider
    h2, tok2, _ = f.create("/b1", name="Plain", target="task", text="x", level="full",
                           rules={"filter": {"path": "_event.type", "op": "eq", "value": "order.paid"}})
    code, r = await f.accept(h2["id"], tok2, b'{"_event": {"type": "order.paid"}}', "application/json", "forge")
    await f.wait_idle()
    check("a payload cannot set _event (no provider): ignored", code == 202 and st.get(r["event_id"])["status"] == "filtered", r)

    # GitHub delivery id dedup, through the feature
    h3, tok3, _ = f.create("/b1", name="GH", target="task", text="x", level="full", verify={"provider": "github", "secret": SEC},
                           rules={"filter": {"path": "_event.type", "op": "eq", "value": "push"}})
    hd = {"x-hub-signature-256": gh, "x-github-event": "push", "x-github-delivery": "gh-1"}
    f._kick = lambda: None
    c1, a1 = await f.accept(h3["id"], tok3, BODY, "application/json", "", headers=hd)
    c2, a2 = await f.accept(h3["id"], tok3, BODY, "application/json", "", headers=hd)
    del f._kick
    check("GitHub: _event.type filter works and a redelivery is a duplicate", c1 == 202 and c2 == 200 and a2.get("duplicate"), (c1, a1, c2, a2))

    # a plain secret saved before M4 is sealed at start
    st.import_hooks([{"id": "wh_old", "name": "Old", "brain": "/b1", "target": "task", "text": "x", "level": "full",
                      "enabled": True, "token_hash": "", "actions": [{"id": "c", "kind": "http", "url": "https://x.vn",
                                                                       "headers": {"X-Key": "old-PLAIN"}}]}])
    n_sealed = f._migrate_secrets()
    js = json.dumps([dict(r) for r in st._db.execute("SELECT config FROM hooks")] +
                    [dict(r) for r in st._db.execute("SELECT config FROM hook_revisions")])
    check("start: a plain header from before M4 is moved into the vault, older revisions scrubbed too",
          n_sealed == 1 and "old-PLAIN" not in js and f.vault.get("wh_old/a/c/X-Key") == "old-PLAIN")
    sj = Path(tempfile.mkdtemp(prefix="m4-json-"))
    (sj / "webhooks.json").write_text(json.dumps({"hooks": [{"id": "wh_j", "name": "J", "brain": "/b1", "target": "task",
                                                            "text": "x", "level": "full", "enabled": True,
                                                            "token_hash": "", "verify": {"provider": "github",
                                                                                         "secret": "j-PLAIN-secret"}}]}))
    fj = make(state_dir=lambda: sj)
    js = json.dumps([dict(r) for r in fj.store()._db.execute("SELECT config FROM hook_revisions")])
    check("migration from webhooks.json seals plain secrets BEFORE any revision is written",
          "j-PLAIN-secret" not in js and fj.vault.get("wh_j/verify") == "j-PLAIN-secret")

    # tool action with approval
    await f.wait_idle()
    tool_calls.clear(); sent.clear(); calls_ai.clear()
    h4, tok4, err = f.create("/b1", name="POS", target="", text="", level="full", rules={"mapping": {"phone": "phone", "name": "name"}},
                             actions=[{"id": "pos", "kind": "tool", "tool": "pos_create_order",
                                       "args": {"phone": "{phone}", "note": "Webhook {name}", "ref": "{_delivery_id}", "qty": 1}}])
    check("tool action: approval on by default", not err and f._find(f._load(), h4["id"])["actions"][0]["approve"] is True, err)
    evil = {"phone": "0912 {_delivery_id}", "name": "{phone}", "approve": False, "level": "full"}
    code, r = await f.accept(h4["id"], tok4, json.dumps(evil).encode(), "application/json", "t1")
    await f.wait_idle()
    ev = st.get(r["run_id"])
    check("the tool waits for approval: event waiting, tool not called, the owner is asked",
          ev["status"] == "waiting" and not tool_calls and ev["branches"][0]["status"] == "approval"
          and any("duyệt" in m.lower() or "approval" in m.lower() for m in sent), (ev["status"], sent))
    from fastapi import FastAPI
    import httpx
    app = FastAPI()
    app.include_router(f.router)
    cl = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")
    rr = await cl.post("/webhooks/events/approve", json={"id": r["run_id"], "action": "pos", "decision": "approve"})
    await f.wait_idle()
    ev = st.get(r["run_id"])
    did = wa.delivery_id(r["run_id"], "pos")
    check("approved: the tool runs once through the dispatcher at the hook's level", rr.status_code == 200 and len(tool_calls) == 1
          and tool_calls[0]["name"] == "pos_create_order" and tool_calls[0]["level"] == "full" and tool_calls[0]["brain"] == "/b1"
          and ev["status"] == "done" and ev["branches"][0]["status"] == "completed", (rr.text, tool_calls, ev["status"]))
    check("arguments are templated once: payload text is substituted, never expanded or evaluated",
          tool_calls[0]["args"] == {"phone": "0912 {_delivery_id}", "note": "Webhook {phone}", "ref": did, "qty": 1},
          tool_calls[0]["args"])
    rr = await cl.post("/webhooks/events/approve", json={"id": r["run_id"], "action": "pos", "decision": "approve"})
    check("approving again: refused (409), nothing runs twice", rr.status_code == 409 and len(tool_calls) == 1)

    # reject
    code, r = await f.accept(h4["id"], tok4, b'{"phone": "1", "name": "B"}', "application/json", "t2")
    await f.wait_idle()
    rr = await cl.post("/webhooks/events/approve", json={"id": r["run_id"], "action": "pos", "decision": "reject"})
    await f.wait_idle()
    ev = st.get(r["run_id"])
    check("rejected: the delivery and the event are cancelled, the tool never runs", ev["branches"][0]["status"] == "cancelled"
          and ev["status"] == "cancelled" and ev["state"] == "cancelled" and len(tool_calls) == 1, (ev["status"], ev["branches"]))
    code, r = await f.accept(h4["id"], tok4, b'{"phone": "9"}', "application/json", "t2b")
    await f.wait_idle()
    await cl.post("/webhooks/events/approve", json={"id": r["run_id"], "action": "pos", "decision": "approve"})
    await f.wait_idle()
    ev = st.get(r["run_id"])
    check("a field the arguments need is missing: the tool is not called with an empty value (spec §8.3)",
          ev["branches"][0]["status"] == "failed" and "{name} is missing" in ev["branches"][0]["detail"]
          and len(tool_calls) == 1, ev["branches"])

    # level lowered after approval request: the tool gets the lower level (the hub enforces it)
    code, r = await f.accept(h4["id"], tok4, b'{"phone": "2", "name": "C"}', "application/json", "t3")
    await f.wait_idle()
    f.update(h4["id"], {"level": "suggest"})
    await cl.post("/webhooks/events/approve", json={"id": r["run_id"], "action": "pos", "decision": "approve"})
    await f.wait_idle()
    check("approval never lifts a level: the tool is called at the hook's level of now", tool_calls[-1]["level"] == "suggest")
    f.update(h4["id"], {"level": "full"})

    # tool error -> failed; retry runs only that branch (no new approval needed: the owner already approved)
    tool_answer["v"] = "ERROR: kết nối POS đang đặt mức quyền hạn chế"
    code, r = await f.accept(h4["id"], tok4, b'{"phone": "3", "name": "D"}', "application/json", "t4")
    await f.wait_idle()
    await cl.post("/webhooks/events/approve", json={"id": r["run_id"], "action": "pos", "decision": "approve"})
    await f.wait_idle()
    ev = st.get(r["run_id"])
    check("a tool answering ERROR fails its branch with the reason", ev["status"] == "failed"
          and "hạn chế" in ev["branches"][0]["detail"], ev["branches"])
    tool_answer["v"] = "ok"
    n = len(tool_calls)
    st.retry(r["run_id"])
    f._kick()
    await f.wait_idle()
    check("owner retry of the failed tool runs it once more", st.get(r["run_id"])["status"] == "done" and len(tool_calls) == n + 1)

    # hung tool -> unknown
    old = wa.TOOL_TIMEOUT_S
    wa.TOOL_TIMEOUT_S = 0.2
    tool_answer["v"] = "HANG"
    h5, tok5, _ = f.create("/b1", name="Treo", target="", text="", level="full",
                           actions=[{"id": "pos", "kind": "tool", "tool": "pos_x", "approve": False}])
    code, r = await f.accept(h5["id"], tok5, b"{}", "application/json", "t5")
    await f.wait_idle()
    wa.TOOL_TIMEOUT_S = old
    tool_answer["v"] = "ok"
    check("a tool that hangs is unknown (it may have acted), not retried", st.get(r["run_id"])["status"] == "unknown")
    check("no model was called for tool-only hooks", calls_ai == [])

    # missing vault key: the branch fails cleanly, the server keeps working
    h6, tok6, _ = f.create("/b1", name="Mất khoá", target="", text="", level="full",
                           actions=[{"id": "crm", "kind": "http", "url": "https://crm.example/h", "headers": {"X-K": "v"}}])
    (FEAT / "webhook_keys.json").write_text(json.dumps({"active": "kz", "keys": {"kz": base64.b64encode(os.urandom(32)).decode()}}))
    code, r = await f.accept(h6["id"], tok6, b"{}", "application/json", "t6")
    await f.wait_idle()
    b6 = st.get(r["run_id"])["branches"][0]
    check("a header secret that no longer decrypts blocks its delivery with a clear reason (spec §7: missing credential)",
          b6["status"] == "blocked" and "enter it again" in b6["detail"], b6)
    r = await cl.post("/webhooks/secrets/rotate")
    check("rotation refuses when a secret cannot be read (nothing half-done)", r.status_code == 409, r.text)
    await cl.aclose()


asyncio.run(main())

for name in ("webhook_verify.py", "webhook_auth.py", "webhook_secrets.py"):
    src = (SERVER / name).read_text(encoding="utf-8")
    check(f"{name}: no model, no network", not any(x in src for x in ("aux_engine", "claude_cli", "anthropic", "httpx", "requests.")))

if fails:
    print(f"\nFAIL {len(fails)}: " + ", ".join(fails))
    sys.exit(1)
print("\nOK - test_webhook_security_m4: all pass")
