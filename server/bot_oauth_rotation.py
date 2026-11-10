"""Rotate ChatGPT OAuth plan accounts for *dedicated chatbot* Responses calls.

The owner's Codex CLI path already rotates CODEX_HOME on quota, but read/write
chatbots call the Codex Responses backend directly. Those calls previously read
openai_oauth.valid_creds() (account 1) regardless of the Models account order.
Only a chatbot turn enters this adapter. We never change an owner's model,
a pinned bot model, tools, or permission scope.

No retry across accounts after any text or tool call: both can have observable
side effects. In particular, a partial tool loop must not run twice.
"""
from __future__ import annotations

import asyncio
import sys

import config as cfgmod
import localefmt
import model_routing
import openai_oauth
import plan_accounts
import turn_context

PROVIDER = "openai-oauth"

# Include the provider's stable usage-limit code, not generic "limit" (which
# also appears in invalid-context and unsupported-model errors).
_QUOTA = ("usage_limit_reached", "usage limit", "you've hit your usage limit",
          "quota exceeded", "quota_exceeded", "out of quota", "resource_exhausted")
_AUTH = ("unauthorized", "invalid_token", "authentication failed", "token expired")


def _quota_failure(ev: dict, pending: list) -> bool:
    if ev.get("type") != "error":
        return False
    msg = str(ev.get("content") or "").lower()
    if any(x in msg for x in _QUOTA):
        return True
    # 429 on the *account-specific* request is also safe to try on account 2
    # provided NO answer or tool call has escaped this stream.
    if ev.get("ma") == 429:
        return True
    return any(p.get("type") == "limit_exceeded" and
               any(x in str(p.get("raw") or "").lower() for x in _QUOTA)
               for p in pending)


def _auth_failure(ev: dict) -> bool:
    if ev.get("type") != "error":
        return False
    msg = str(ev.get("content") or "").lower()
    return ev.get("ma") in (401, 403) or any(x in msg for x in _AUTH)


async def stream(factory, access_token: str, account_id: str):
    """Stream one chatbot turn on each usable account until one answers.

    factory(access_token, chatgpt_account_id) yields native engine events.
    Non-chatbot callers, including the authenticated owner's chat, remain
    exactly as before. The order follows Models' saved account list.
    """
    turn = turn_context.current() or {}
    if not turn.get("bot_id") or turn.get("la_chu"):
        async for ev in factory(access_token, account_id):
            yield ev
        return

    m = (cfgmod.read_settings().get("model") or {})
    if not plan_accounts.has_extra(m, PROVIDER):
        async for ev in factory(access_token, account_id):
            yield ev
        return

    candidates = plan_accounts.usable(m, PROVIDER)
    last_quota = None
    attempts = 0
    for acct in candidates:
        aid = acct["id"]
        try:
            creds = await asyncio.to_thread(openai_oauth.valid_creds_for, aid)
        except Exception as exc:  # noqa: BLE001 - one broken account cannot block another
            print(f"[bot oauth routing] credentials for {aid}: {type(exc).__name__}", file=sys.stderr)
            continue
        if not creds or not creds.get("access_token") or creds.get("stale"):
            continue
        attempts += 1
        pending = []
        committed = False
        try:
            async for ev in factory(creds["access_token"], creds.get("account_id") or ""):
                typ = (ev or {}).get("type")
                # An OAuth MCP stream emits meta before its HTTP request;
                # do not advertise a failed account's meta as the successful one.
                if not committed and typ in ("meta", "limit_exceeded"):
                    if len(pending) < 16:
                        pending.append(ev)
                    continue
                if not committed and _quota_failure(ev, pending):
                    last_quota = dict(ev)
                    # No output or tools: this account has not acted. Rest just
                    # this account so all subsequent turns start on the next.
                    from aux_engine import cooldown_for, COOLDOWN_QUOTA_S
                    sec = cooldown_for(ev.get("content")) or COOLDOWN_QUOTA_S
                    model_routing.mark_rest(PROVIDER, aid, seconds=sec)
                    print(f"[bot oauth routing] account {aid} quota exhausted; rotating", file=sys.stderr)
                    break
                if not committed and _auth_failure(ev):
                    # Different credential, same model; do not retry the bad
                    # token three times. Never expose the access token.
                    model_routing.mark_rest(PROVIDER, aid, seconds=180)
                    print(f"[bot oauth routing] account {aid} authentication failed; rotating", file=sys.stderr)
                    break
                if pending:
                    for cached in pending:
                        yield cached
                    pending = []
                if typ == "tool_call" or (typ == "text" and ev.get("content")):
                    committed = True
                yield ev
                if typ == "error":
                    # A mid-turn failure may have already executed tools.
                    return
            else:
                if pending:
                    for cached in pending:
                        yield cached
                return
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            # Do not restart after an unknown exception (side effects uncertain).
            print(f"[bot oauth routing] stream failed: {type(exc).__name__}", file=sys.stderr)
            yield {"type": "error", "content": f"ChatGPT: {type(exc).__name__}"}
            return

    if last_quota is not None:
        # Stop the enclosing generic retry wrapper from repeating the same
        # quota-exhausted account 3 times. 429 is not a brief network failure.
        last_quota.pop("tam_thoi", None)
        last_quota.pop("cho", None)
        last_quota["content"] = (str(last_quota.get("content") or "ChatGPT usage limit") + " " + localefmt.chu(
            f"(đã thử {attempts} tài khoản ChatGPT khả dụng)", f"(tried {attempts} usable ChatGPT account(s))"))
        yield last_quota
    else:
        yield {"type": "error", "content": "ChatGPT: " + localefmt.chu(
            "Không có tài khoản đã đăng nhập và còn lượt sử dụng.", "No signed-in account with usage left.")}
