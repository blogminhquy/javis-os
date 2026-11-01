"""The structured end-of-step report of a team Work/Help step (0.436.0).

A step ends with one directive, the same shape as every JAVIS_TEAM block:
    <!-- JAVIS_TEAM: {"op": "done", "outcome": "succeeded", "summary": "...", "files": ["..."]} -->

Taken from stablyai/orca's `worker_done` (an explicit outcome and a three-sentence body: what was done, what was found,
what is left). Two things it buys:
- A step that reports `failed` stops the job for the owner instead of flowing into the synthesis as if it were a result
  (Orca: "never hide failure in prose"). That also saves the synthesis turn, which would only summarise a failure.
- The synthesis reads the short summary plus the file list when the full answer is longer than an input's character cap,
  instead of a text cut in the middle (the conclusion is usually at the end, exactly the part a cut loses).

A step without the block works as before: it counts as succeeded and its full text is the input.
"""
from __future__ import annotations

from typing import Any, Optional

OP = "done"
OUTCOMES = ("succeeded", "failed")
SUMMARY_MAX = 800
FILES_MAX = 20
FILE_CHARS = 300
# Appended to the Work/Help system note (stable text, so prompt caching keeps it). Prompt text stays Vietnamese like
# the rest of the team prompts (docs/dev/them-mot-ngon-ngu.md).
HINT = ('Kết thúc bước bằng MỘT khối báo cáo: <!-- JAVIS_TEAM: {"op": "done", "outcome": "succeeded", '
        '"summary": "<tối đa 3 câu: đã làm gì, thấy gì, còn gì>", "files": ["<đường dẫn file đã ghi>"]} -->. '
        'Chỉ ghi "outcome": "failed" khi bước KHÔNG làm ra được kết quả dùng được (thiếu quyền, thiếu dữ liệu, lỗi '
        'không vượt qua được); làm được một phần thì vẫn "succeeded" và ghi phần còn lại vào summary. Đừng giấu thất bại '
        'trong lời văn.')


def parse(op: Any) -> Optional[dict]:
    """The report of one `done` directive, or None when it carries nothing usable."""
    if not isinstance(op, dict):
        return None
    outcome = str(op.get("outcome") or "").strip().lower()
    if outcome not in OUTCOMES:
        outcome = "succeeded"
    summary = " ".join(str(op.get("summary") or "").split())[:SUMMARY_MAX]
    raw = op.get("files")
    files = []
    if isinstance(raw, (list, tuple)):
        for f in raw:
            f = str(f or "").strip()[:FILE_CHARS]
            if f and f not in files:
                files.append(f)
            if len(files) >= FILES_MAX:
                break
    if not summary and not files and outcome == "succeeded":
        return None
    return {"outcome": outcome, "summary": summary, "files": files}


def take(ops: list, notes: list) -> tuple:
    """(other ops, the first valid report or None). Later reports are dropped with a note."""
    rest, report = [], None
    for op in ops:
        if op.get("op") != OP:
            rest.append(op)
            continue
        got = parse(op)
        if got is None:
            notes.append("Khối báo cáo 'done' không có nội dung, đã bỏ")
        elif report is None:
            report = got
        else:
            notes.append("Mỗi bước chỉ báo cáo một lần, đã dùng khối đầu")
    return rest, report


def input_text(content: str, report: Optional[dict], limit: int, msg_id: Any) -> str:
    """What a later step reads of an earlier result: the full text when it fits, else the report (summary and files)
    when the step gave one, else the text cut at `limit` as before."""
    content = str(content or "")
    if len(content) <= limit or not report or not (report.get("summary") or report.get("files")):
        return content[:limit]
    parts = [report.get("summary") or ""]
    if report.get("files"):
        parts.append("File: " + ", ".join(report["files"]))
    parts.append(f"(Bản tóm tắt của bước; câu trả lời đầy đủ dài {len(content)} ký tự ở tin #{msg_id}.)")
    return " ".join(p for p in parts if p)[:limit]
