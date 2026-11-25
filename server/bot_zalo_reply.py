"""A quote is metadata of the current bot reply, never permission to send elsewhere."""
from __future__ import annotations

import re

_MARK = re.compile(r"\[ZALO_REPLY(?:\s*:[^\]\r\n]*)?\]", re.I)
_VALID = re.compile(r"\[ZALO_REPLY:([0-9]{1,40})\]", re.I)
PROMPT_HINT = """On personal Zalo you can quote an earlier TEXT message in THIS conversation without calling a send tool,
even at auto permission level. Read history to find the actual message id and confirm the account, conversation,
sender and content. Put [ZALO_REPLY:<message-id>] on its own line before your normal reply. The channel removes
this marker, verifies the target in this account and conversation, then sends ONE reply quoting it. Never invent
an id, use an id from another conversation, or also send the same reply through a tool. If the customer asks you
to point to information they supplied earlier, use this route after finding the exact message. Use history date
filters and pagination when the first page does not contain it. The marker requests a send; it does not prove
delivery. Do not claim you already sent the quote. Do not add the marker when you cannot verify the target.
"""


def pick(text):
    """Strip every directive, accepting exactly one well-formed numeric target."""
    value = str(text or "")
    marks = list(_MARK.finditer(value))
    target = ""
    if len(marks) == 1:
        valid = _VALID.fullmatch(marks[0].group())
        if valid:
            target = valid.group(1)
    return _MARK.sub("", value).strip(), target, bool(marks)


async def verify_target(conn, thread, thread_type, target):
    """Fail closed on missing, cross-thread or non-text targets. Never alter the destination."""
    import conversations
    import zalo_personal_channel as zc

    if not re.fullmatch(r"[0-9]{1,40}", str(target or "")):
        return False
    row = conversations.tin_theo_id("zalo_personal", str(conn.get("id") or ""), str(thread), target)
    if row and row.get("message_type") == "text":
        return True
    # Groups may trim the inbox. Confirm against the same account's MCP history, with bounded pagination.
    cursor = None
    seen = set()
    for _ in range(10):
        args = {"threadId": str(thread), "threadType": thread_type, "limit": 200}
        if cursor:
            args["lastMsgId"] = cursor
        result = await zc._goi(conn, "zalo_get_history", args)
        if not isinstance(result, dict):
            return False
        for message in result.get("messages") or []:
            if not isinstance(message, dict):
                continue
            mid = str(message.get("msgId") or message.get("id") or "")
            if mid == target:
                return (str(message.get("threadId") or "") == str(thread)
                        and message.get("type") == "text")
        cursor = result.get("cursor")
        if not result.get("hasMore") or not cursor or str(cursor) in seen:
            break
        seen.add(str(cursor))
    return False
