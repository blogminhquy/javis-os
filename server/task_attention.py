"""Worker escalation is a decision request, not a failed acceptance check.

This describes a question only. It never grants permission to perform an action.
"""
from __future__ import annotations

import json
import re

MARKER = "[[NEEDS_INPUT]]"
_LINE = re.compile(r"^[\s>#*_`\-•|]*" + re.escape(MARKER), re.MULTILINE)
_INTERNAL = re.compile(
    r"(?:replay|recovery|restart|traceback|regression|engineering blocker|"
    r"editorial[_ -]?qa|quality[_ -]?fail|acceptance[_ -]?fail|"
    r"chưa đạt điều kiện hoàn thành|kiểm thử.*(?:chưa|thiếu|thất bại)|"
    r"needs_source|thiếu nguồn|missing (?:source|evidence)|failed (?:test|check))", re.I,
)


def owner_request(result: str) -> dict | None:
    """Fail closed on an unstructured/malformed escalation; keep it inside engineering.

    A worker must name an owner-only decision, one question, and concrete alternatives.
    Technical/QA failures remain internal even if wrapped in this marker.
    """
    match = _LINE.search(result or "")
    if not match:
        return None
    text = (result or "")[match.end():].lstrip()
    try:
        value, _end = json.JSONDecoder().raw_decode(text)
    except (ValueError, TypeError):
        return None
    if not isinstance(value, dict) or value.get("kind") not in ("approval", "choice", "private_input"):
        return None
    question, reason, options = value.get("question"), value.get("owner_only_reason"), value.get("options")
    if not isinstance(question, str) or not 8 <= len(question.strip()) <= 600:
        return None
    if not question.rstrip().endswith(("?", "？")):
        return None
    if not isinstance(reason, str) or not 8 <= len(reason.strip()) <= 600:
        return None
    if not isinstance(options, list) or not 2 <= len(options) <= 5:
        return None
    if any(not isinstance(x, str) or not 1 <= len(x.strip()) <= 150 for x in options):
        return None
    options = [x.strip() for x in options]
    if len({x.casefold() for x in options}) != len(options):
        return None
    if _INTERNAL.search(question + "\n" + reason):
        return None
    return {"kind": value["kind"], "question": question.strip(),
            "owner_only_reason": reason.strip(), "options": options}


def question_text(request: dict) -> str:
    return request["question"] + "\n" + "\n".join(
        f"{i}. {option}" for i, option in enumerate(request["options"], 1))
