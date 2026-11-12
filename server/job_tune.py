"""The owner's side of the background scorecard, from chat (tool `javis_tune`, 10/11/2026).

There is no settings page for how background jobs pick their model: the owner says what they want and Javis
adjusts (job_scorecard.py). This module turns those sentences into four operations and answers in JSON the chat
model words for the owner. Owner only (mcp_hub.OWNER_ONLY_TOOLS).
"""
from __future__ import annotations

import json

import core_loop
import job_scorecard
import tool_pins

OPS = ("status", "intent", "feedback", "teach", "set", "undo")
# Set by main.py: how to store and list the lessons about learning that Javis Core holds for a brain.
_TEACH = [None]
_LESSONS = [None]


def wire(*, teach=None, lessons=None) -> None:
    _TEACH[0], _LESSONS[0] = teach, lessons

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


def run(args: dict, vault_root: str = "") -> str:
    args = args or {}
    op = str(args.get("op") or "").strip().lower()
    if op not in OPS:
        return json.dumps({"ok": False, "error": "op phải là một trong: " + ", ".join(OPS)}, ensure_ascii=False)
    if op == "status":
        st = job_scorecard.status()
        st["intent_label"] = _INTENT_WORDS.get(st["intent"], st["intent"])
        st["ok"] = True
        st["note"] = ("Mỗi việc nền tự tìm model nhẹ nhất làm được việc: hỏng do model thì lần sau leo một bậc, chạy tốt "
                      "nhiều lần thì thử xuống một bậc. `fails` chỉ đếm lần hỏng do model. `knobs` là các núm Javis "
                      "Core tự chỉnh; mã thay đổi dạng k12 hay số đều hoàn lại được bằng op=undo.")
        st.update(core_loop.status())
        st["pinned_tools"] = tool_pins.status()
        st["pinned_tools_note"] = ("Công cụ mỗi brain hay gọi được hiện thẳng, khỏi một vòng tìm. calls_direct là số "
                                   "lần gọi thẳng (đã bớt vòng tìm), calls_after_search là số lần còn phải tìm trước. "
                                   "Tắt: op=set knob=tools.pin_limit value=0.")
        if _LESSONS[0] and vault_root:
            try:
                st["learning_lessons"] = _LESSONS[0](vault_root)
            except Exception:   # noqa: BLE001
                st["learning_lessons"] = []
        return json.dumps(st, ensure_ascii=False)
    if op == "teach":
        text = " ".join(str(args.get("text") or "").split())
        if not text:
            return json.dumps({"ok": False, "error": "teach cần text: một câu ngắn về cách tự học"}, ensure_ascii=False)
        if not _TEACH[0] or not vault_root:
            return json.dumps({"ok": False, "error": "kho bài học chưa sẵn sàng, thử lại sau vài giây"}, ensure_ascii=False)
        try:
            lid = _TEACH[0](vault_root, text[:300])
        except Exception as e:   # noqa: BLE001
            return json.dumps({"ok": False, "error": f"không lưu được bài học: {type(e).__name__}"}, ensure_ascii=False)
        return json.dumps({"ok": True, "lesson": f"L{lid}", "text": text[:300],
                           "effect": "mẻ tự học kế tiếp của brain này đọc bài học này trước khi quyết định ghi gì",
                           "revoke": "javis_memory op=lesson_revoke agent=javis-core id=L%s" % lid}, ensure_ascii=False)
    if op == "set":
        knob = str(args.get("knob") or "").strip()
        known = {k.id: k for k in core_loop.knobs()}
        if knob not in known:
            return json.dumps({"ok": False, "error": "không có núm này", "knobs": sorted(known)}, ensure_ascii=False)
        try:
            value = int(args.get("value"))
        except (TypeError, ValueError):
            return json.dumps({"ok": False, "error": "value phải là số nguyên"}, ensure_ascii=False)
        k = known[knob]
        if not (k.lo <= value <= k.hi):
            return json.dumps({"ok": False, "error": f"giá trị phải trong khoảng {k.lo} đến {k.hi}"}, ensure_ascii=False)
        ch = core_loop.change(knob, value, "owner", str(args.get("note") or "chủ dặn")[:200])
        return json.dumps({"ok": True, "knob": knob, "label": k.title_vi, "value": value,
                           "changed": bool(ch), "id": (ch or {}).get("id", "")}, ensure_ascii=False)
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
    cid = str(args.get("id") if args.get("id") is not None else "").strip()
    if not cid:
        return json.dumps({"ok": False, "error": "thiếu id của thay đổi (xem op=status, mục changes và knob_changes)"},
                          ensure_ascii=False)
    back = core_loop.undo(cid)
    if not back:
        return json.dumps({"ok": False, "error": "không có thay đổi mang id này, hoặc nó đã được hoàn lại"},
                          ensure_ascii=False)
    return json.dumps({"ok": True, **back}, ensure_ascii=False)
