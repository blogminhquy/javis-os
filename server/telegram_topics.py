"""Telegram topic addresses for sessions and durable background destinations.

Only API payloads split a destination into chat_id and message_thread_id. Persisted
jobs retain the opaque address, so restarts cannot send a topic job to General.
"""
from __future__ import annotations
import re

_PATTERN = re.compile(r"(-?[0-9]+):topic:([1-9][0-9]*)\Z")


def thread_id(value):
    if value in (None, "", 0):
        return None
    if isinstance(value, bool) or not re.fullmatch(r"[1-9][0-9]*", str(value)):
        raise ValueError("Invalid Telegram topic id")
    return int(value)


def split(destination):
    raw = str(destination or "").strip()
    if ":topic:" not in raw:
        return raw, None
    match = _PATTERN.fullmatch(raw)
    if not match:
        raise ValueError("Invalid Telegram topic destination")
    return match[1], int(match[2])


def target(chat, topic=None):
    raw, existing = split(chat)
    tid = thread_id(topic) if topic is not None else existing
    if tid is None:
        return raw
    if not re.fullmatch(r"-?[0-9]+", raw):
        raise ValueError("Telegram topics require a numeric chat id")
    return f"{raw}:topic:{tid}"


def payload(destination):
    chat, topic = split(destination)
    out = {"chat_id": chat}
    if topic is not None:
        out["message_thread_id"] = topic
    return out


def conversation(meta):
    m = meta or {}
    if m.get("platform") != "telegram":
        return str(m.get("chat_id") or "")
    return target(m.get("chat_id"), m.get("message_thread_id"))


def turn_destination(turn, requested=""):
    """Keep an explicit different recipient; enrich the originating chat with its topic."""
    t = turn or {}
    value = str(requested or "").strip()
    if t.get("kenh") != "telegram":
        return value
    chat = str(t.get("chat_id") or "")
    if not value or value == chat:
        return target(chat, t.get("message_thread_id"))
    return value


def notification_destination(settings, group, current, *, explicit=False):
    """Group defaults apply only to untargeted notices, never to somebody else's job."""
    if explicit:
        return current
    routes = (settings or {}).get("topic_routes") or {}
    value = routes.get(group) if isinstance(routes, dict) else None
    if not value:
        return current
    # Do not silently fall back to General when a configured route becomes invalid.
    chat, tid = split(value)
    if tid is None:
        raise ValueError("Notification route requires a Telegram topic")
    return target(chat, tid)
