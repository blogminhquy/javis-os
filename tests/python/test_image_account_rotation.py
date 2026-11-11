"""Image generation rotates ChatGPT accounts only after a definite quota failure.

    python tests/run.py image_account_rotation     (no network)
"""
from _paths import ROOT, SERVER  # noqa: E402,F401

import asyncio
import os
import tempfile

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-image-rotation-")

import config  # noqa: E402
import image_gen  # noqa: E402
import model_routing  # noqa: E402
import openai_oauth  # noqa: E402
import plan_accounts  # noqa: E402

failures = []


def check(name, condition):
    print(("ok   " if condition else "FAIL ") + name)
    if not condition:
        failures.append(name)


main = {"access_token": "token-primary", "account_id": "primary"}
second = {"access_token": "token-secondary", "account_id": "secondary"}
settings = {"model": {"accounts": {"openai-oauth": [
    {"id": "main", "enabled": True},
    {"id": "assistant", "enabled": True}
]}}}
config.read_settings = lambda: settings
openai_oauth.valid_creds = lambda: main
openai_oauth.valid_creds_for = lambda key: second if key == "assistant" else main
plan_accounts.usable = lambda model, provider: [
    {"id": a["id"]} for a in model["accounts"][provider] if a["enabled"]
]
image_gen.host_model_candidates = lambda catalog=None: ["gpt-image-host"]
image_gen.save_png_b64 = lambda *a, **kw: {
    "ok": True, "rel_path": "attachments/image.png",
    "abs_path": "/fake/image.png", "file": "image.png"
}
rests = []
model_routing.mark_rest = lambda provider, account, seconds: rests.append((provider, account, seconds))
calls = []


async def quota_then_success(payload, headers, timeout):
    who = headers.get("chatgpt-account-id")
    calls.append(who)
    if who == "primary":
        return None, "ChatGPT 429: usage_limit_reached", 429
    return "fake-image-b64", None, 200


image_gen._mot_luot = quota_then_success
result = asyncio.run(image_gen.generate_chatgpt("pink-haired fashion stylist"))
check("quota on account 1 rotates to account 2", result.get("ok") and calls == ["primary", "secondary"])
check("only the exhausted account rests", rests == [("openai-oauth", "main", 300)])

# A non-quota error must NOT replay the image request on another account.
calls.clear()
rests.clear()


async def bad_prompt(payload, headers, timeout):
    calls.append(headers.get("chatgpt-account-id"))
    return None, "ChatGPT 400: invalid_request", 400


image_gen._mot_luot = bad_prompt
result = asyncio.run(image_gen.generate_chatgpt("invalid"))
check("non-quota errors never retry with another account",
      not result.get("ok") and calls == ["primary"] and not rests)

# Never contact an account the owner disabled on the Models page.
calls.clear()
settings["model"]["accounts"]["openai-oauth"][1]["enabled"] = False
image_gen._mot_luot = quota_then_success
result = asyncio.run(image_gen.generate_chatgpt("only account one"))
check("disabled secondary account is never used", not result.get("ok") and calls == ["primary"])
settings["model"]["accounts"]["openai-oauth"][1]["enabled"] = True

# A missing secondary credential must preserve the actual quota error.
calls.clear()
openai_oauth.valid_creds_for = lambda key: None
result = asyncio.run(image_gen.generate_chatgpt("secondary not logged in"))
check("secondary login absence preserves quota error",
      not result.get("ok") and "429" in result.get("error", ""))
openai_oauth.valid_creds_for = lambda key: second

# A single-account install continues to use the old main credential path.
settings["model"]["accounts"]["openai-oauth"] = [{"id": "main", "enabled": True}]
calls.clear()


async def success(payload, headers, timeout):
    calls.append(headers.get("chatgpt-account-id"))
    return "fake-image-b64", None, 200


image_gen._mot_luot = success
result = asyncio.run(image_gen.generate_chatgpt("single account"))
check("single account behaviour remains unchanged", result.get("ok") and calls == ["primary"])

# An explicitly disabled sole login must not generate any images.
settings["model"]["accounts"]["openai-oauth"][0]["enabled"] = False
calls.clear()
result = asyncio.run(image_gen.generate_chatgpt("owner disabled the only account"))
check("disabled sole account is never used", not result.get("ok") and calls == [])

print()
if failures:
    print(f"{len(failures)} FAIL")
    raise SystemExit(1)
print("ALL PASS")
