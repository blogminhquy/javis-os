"""0.274.0: golden signature fixtures for webhook_verify (webhook platform M4).

    python tests/run.py webhook_golden_signatures

The fixtures in tests/fixtures/webhooks/signatures.json are FROZEN: a change to webhook_verify that alters what a
provider's real signature looks like fails here. `github_docs_vector` is the example GitHub publishes in its own
documentation (an independent check of the scheme); the others were computed once from the providers' published
schemes; `systeme_io_synthetic` is an assumed scheme until a real Systeme.io delivery replaces it.
Each fixture also goes through the real receive path (WebhookFeature.accept) with Starlette-style headers.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path

STATE = Path(tempfile.mkdtemp(prefix="javis-wh-golden-"))
os.environ["JAVIS_STATE_DIR"] = str(STATE)
os.environ["JAVIS_NO_REAL_JUDGE_ENGINE"] = "1"
os.environ["JAVIS_WH_NO_NETWORK"] = "1"
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import webhook_rules as wr  # noqa: E402
import webhook_triggers as wt  # noqa: E402
import webhook_verify as wv  # noqa: E402
from starlette.datastructures import Headers  # noqa: E402

fails = []


def check(name, cond, them=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(them) + "]") if them and not cond else ""))
    if not cond:
        fails.append(name)


data = json.loads((ROOT / "tests" / "fixtures" / "webhooks" / "signatures.json").read_text(encoding="utf-8"))
FX = data["fixtures"]
check("fixtures present for every provider with a signature", {f["provider"] for f in FX} >= {"github", "stripe", "shopify",
                                                                                              "hmac_sha256", "systeme_io"})
check("the only provider-documented vector is labelled as such; the Systeme.io one says SYNTHETIC",
      [f["name"] for f in FX if "documentation" in f["origin"]] == ["github_docs_vector"]
      and all("SYNTHETIC" in f["origin"] for f in FX if f["provider"] == "systeme_io"))

for f in FX:
    cfg = wv.validate(dict({"provider": f["provider"], "secret": f["secret"]}, **(f.get("config") or {})))
    hdr = Headers(f["headers"])               # real header object: case-insensitive like a request's
    ok, why, kver, form = wv.verify_ex(cfg, f["secret"], hdr, f["body"].encode(), f["now"] or None)
    check(f"{f['name']}: {'accepted' if f['valid'] else 'refused'}", ok == f["valid"], why)
    if f.get("signed_form"):
        check(f"{f['name']}: the matched normalisation form is recorded ({f['signed_form']})", form == f["signed_form"], form)
    if f.get("event"):
        n = wv.normalize(f["provider"], hdr, wr.parse_payload(f["body"].encode(), "application/json")[0])
        check(f"{f['name']}: normalised type and id", n["type"] == f["event"]["type"] and n["id"] == f["event"]["id"], n)


async def through_accept():
    sent = []

    async def run_task(b, t, l):
        return "ok", ""

    async def nop(*a, **k):
        return "", "", False

    async def send(*a, **k):
        sent.append(a)
        return True, ""
    feat = wt.WebhookFeature(wt.WebhookDeps(state_dir=lambda: STATE, run_task=run_task, run_workflow=nop, send=send,
                                            base_url=lambda r: ""))
    import time as _t
    for f in FX:
        if f["provider"] == "stripe" and f["valid"]:
            continue                                # its timestamp is fixed in the past: covered by verify() above
        h, tok, err = feat.create("/b", name=f["name"], target="task", text="x",
                                  verify=dict({"provider": f["provider"], "secret": f["secret"]}, **(f.get("config") or {})))
        if f["provider"] == "hmac_sha256":
            continue                                # same: timestamped
        code, _ = await feat.accept(h["id"], tok, f["body"].encode(), "application/json", "", headers=Headers(f["headers"]))
        check(f"{f['name']}: through the real receive path -> {'202' if f['valid'] else '401'}",
              code == (202 if f["valid"] else 401), code)
    await feat.wait_idle()

asyncio.run(through_accept())

if fails:
    print(f"\nFAIL {len(fails)}: " + ", ".join(fails))
    sys.exit(1)
print("\nOK - test_webhook_golden_signatures: all pass")
