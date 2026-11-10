"""The owner's side of the background scorecard, from chat (tool `javis_tune`, 10/11/2026).

There is no settings page for how background jobs pick their model: the owner says what they want and Javis
adjusts (job_scorecard.py). This module turns those sentences into four operations and answers in JSON the chat
model words for the owner. Owner only (mcp_hub.OWNER_ONLY_TOOLS).
"""
from __future__ import annotations

import json

import job_scorecard

OPS = ("status", "intent", "feedback", "undo")
_INTENT_WORDS = {"save": "tiết kiệm", "balanced": "cân bằng", "sure": "chắc chắn"}


def _one_job(text: str):
    """(job key, error dict). The owner names a job in their own words; several matches are handed back to ask."""
    found = job_scorecard.find(text)
    if not found:
        return "", {"ok": False, "error": "không tìm thấy việc nào khớp", "hint": "gọi op=status để xem danh sách việc"}
    exact = [f for f in found if f["job"] == text]
    if exact:
        return exact[0]["job"], None
    if len(found) > 1:
        return "", {"ok": False, "error": "nhiều việc khớp, hỏi lại người dùng là việc nào", "matches": found}
    return found[0]["job"], None


def run(args: dict) -> str:
    args = args or {}
    op = str(args.get("op") or "").strip().lower()
    if op not in OPS:
        return json.dumps({"ok": False, "error": "op phải là một trong: " + ", ".join(OPS)}, ensure_ascii=False)
    if op == "status":
        st = job_scorecard.status()
        st["intent_label"] = _INTENT_WORDS.get(st["intent"], st["intent"])
        st["ok"] = True
        st["note"] = ("Mỗi việc nền tự tìm model nhẹ nhất làm được việc: hỏng do model thì lần sau leo một bậc, chạy tốt "
                      "nhiều lần thì thử xuống một bậc. `fails` chỉ đếm lần hỏng do model.")
        return json.dumps(st, ensure_ascii=False)
    if op == "intent":
        level = str(args.get("level") or "").strip().lower()
        if level not in job_scorecard.INTENTS:
            return json.dumps({"ok": False, "error": "level phải là save, balanced hoặc sure"}, ensure_ascii=False)
        job = ""
        if str(args.get("job") or "").strip():
            job, err = _one_job(str(args["job"]).strip())
            if err:
                return json.dumps(err, ensure_ascii=False)
        job_scorecard.set_intent(level, job)
        return json.dumps({"ok": True, "intent": level, "intent_label": _INTENT_WORDS[level],
                           "applies_to": job or "mọi việc nền",
                           "effect": {"save": "việc nền bắt đầu ở model nhẹ hơn và thử hạ bậc sớm hơn",
                                      "balanced": "việc nền tự cân giữa được việc và đỡ tốn",
                                      "sure": "việc nền bắt đầu ở model mạnh hơn và không tự hạ bậc"}[level]},
                          ensure_ascii=False)
    if op == "feedback":
        job, err = _one_job(str(args.get("job") or "").strip())
        if err:
            return json.dumps(err, ensure_ascii=False)
        good = args.get("good") is True
        if not job_scorecard.feedback(job, good, str(args.get("note") or "")[:200]):
            return json.dumps({"ok": False, "error": "việc này chưa chạy lần nào ở chế độ Tự động"}, ensure_ascii=False)
        now = next((j for j in job_scorecard.status(200)["jobs"] if j["job"] == job), {})
        return json.dumps({"ok": True, "job": job, "good": good, "model_next_run": now.get("model") or "",
                           "effect": "đã ghi nhận" if good else "lần chạy tới dùng model mạnh hơn một bậc (nếu còn bậc)"},
                          ensure_ascii=False)
    try:
        cid = int(args.get("id"))
    except (TypeError, ValueError):
        return json.dumps({"ok": False, "error": "thiếu id của thay đổi (xem op=status, mục changes)"}, ensure_ascii=False)
    back = job_scorecard.undo(cid)
    if not back:
        return json.dumps({"ok": False, "error": "không có thay đổi mang id này, hoặc nó đã được hoàn lại"},
                          ensure_ascii=False)
    return json.dumps({"ok": True, **back}, ensure_ascii=False)
