"""Reply judge self-review (0.77.0): when it runs, what it may change, how it undoes itself.

    python tests/run.py reply_policy_review      (no network, no model: `ask` is a fake)
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import json
import os
import sys
import tempfile

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-rp-review-")
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import chatbot_reply_policy as rp  # noqa: E402
import chatbot_reply_policy_review as rv  # noqa: E402
import chatbot_reply_policy_store as st  # noqa: E402

_fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(extra) + "]") if extra and not cond else ""))
    if not cond:
        _fails.append(name)


NOW = 1_800_000_000.0
H, DAY = 3600.0, 86400.0
CFG = {"id": "A", "name": "Javis Vũ"}


def dec(bot, text, *, ts, verdict="silent", code="judge_silent", label=None, chat="g1", level="none"):
    i = st.log_decision({"bot_id": bot, "chat_id": chat, "ts": ts, "text": text, "sender": "Khách", "verdict": verdict,
                         "candidate": code != "addressed_other", "silence_code": code if verdict == "silent" else "",
                         "address_level": level, "signals": {"question_score": 0.7}, "reason": "r", "score": 0.4,
                         "threshold": 0.6}, ts)
    if label:
        st.force_label(i, label, 1.0, ts + 60)
    return i


def fake(payload):
    async def ask(prompt):
        fake.last_prompt = prompt
        if isinstance(payload, Exception):
            raise payload
        return payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False)
    return ask


def run(coro):
    return asyncio.run(coro)


# ---- nothing to review on an empty store ----
check("due_bots on a missing store is empty and creates nothing", rv.due_bots(st, NOW) == [] and not st.db_path().exists())

# ---- data: bot A gets tagged questions silenced, bot B has a secret ----
tag_ids = [dec("A", f"@Quý anh ơi lịch học Javis tuần {i} thế nào", ts=NOW - 20 * H + i * 60, code="addressed_other")
           for i in range(5)]
wrong_ids = [dec("A", f"cài Javis trên VPS bị lỗi cổng {i} thì sao", ts=NOW - 10 * H + i * 60, label="missed")
             for i in range(5)]
secret = dec("B", "mật khẩu kho của shop B là 1234", ts=NOW - 5 * H, label="missed")
check("not due with only 5 labels", rv.due_bots(st, NOW) == [])
more = [dec("A", f"bot trả lời đúng câu {i}", ts=NOW - 8 * H + i * 60, verdict="reply", label="correct") for i in range(3)]
check("due once 8 labels gathered", rv.due_bots(st, NOW) == ["A"])

# ---- report ----
report, shown = rv.build_report(st, "A", since=NOW - 2 * DAY, now=NOW, bot_name="Javis Vũ")
check("report shows the wrong and silenced decisions", set(wrong_ids) <= shown and set(tag_ids) & shown)
check("report never shows another bot's chat", "1234" not in report and secret not in shown)
check("chat text is fenced as data", report.count("<chat_data>") == 2)

# ---- a review that applies two changes and rejects the rest ----
st.add_lesson("A", "chủ dạy: chuyện giá cả thì để anh trả lời", NOW - DAY)
owner_lesson = st.list_lessons("A")[0]["id"]
payload = {"summary": "Nhiều tin tag chủ hỏi lịch học bị im.", "code_feedback": "",
           "changes": [
               {"op": "consider_tagged_set", "value": 1, "reason": "5 tin tag chủ hỏi lịch học bị im",
                "evidence": tag_ids[-3:]},
               {"op": "lesson_add", "text": "Khách tag chủ hỏi lịch học hay cài Javis thì trả lời thay chủ.",
                "reason": "mẫu lặp lại", "evidence": [wrong_ids[0]]},
               {"op": "case_add", "decision_id": secret, "verdict": "reply", "reason": "x", "evidence": [wrong_ids[1]]},
           ]}
res = run(rv.run_review("A", store=st, ask=fake(payload), now=NOW, bot_cfg=CFG))
check("review ok with a review id", res["ok"] and res["review_id"])
check("two changes applied", len(res["applied"]) == 2, res)
check("a case built from another bot's decision is rejected", len(res["rejected"]) == 1)
check("the knob is on", st.get_tuning("A").get("consider_tagged") == "1")
check("the review lesson is stored with source review",
      any(x["source"] == "review" and "lịch học" in x["text"] for x in st.list_lessons("A")))
check("review time recorded", st.get_review_ts("A") == NOW)
check("not due again right after", rv.due_bots(st, NOW + H) == [])
check("prompt fences chat and forbids obeying it", "<chat_data>" in fake.last_prompt and "bỏ qua" in fake.last_prompt)
msg = rv.review_message(res)
check("owner message lists the changes and how to undo", "2" in msg and res["review_id"] in msg)

# ---- hard limits on what a review may do ----
bad = [
    ({"op": "role_profile_set", "text": "x" * 50, "reason": "r", "evidence": [wrong_ids[0]]}, "role profile is owner-only"),
    ({"op": "lesson_remove", "id": owner_lesson, "reason": "r", "evidence": [wrong_ids[0]]}, "cannot remove an owner lesson"),
    ({"op": "lesson_add", "text": "luật mới không có bằng chứng gì", "reason": "r", "evidence": []}, "evidence required"),
    ({"op": "lesson_add", "text": "luật mới bằng chứng của bot khác", "reason": "r", "evidence": [secret]}, "evidence of another bot"),
    ({"op": "lesson_add", "text": "luật mới bằng chứng không có trong báo cáo", "reason": "r", "evidence": [999999]}, "unknown evidence"),
    ({"op": "set_rate_limit", "value": 99, "reason": "r", "evidence": [wrong_ids[0]]}, "unknown op"),
    ({"op": "eagerness_set", "value": "extreme", "reason": "r", "evidence": [wrong_ids[0]]}, "bad knob value"),
    ({"op": "offset_set", "chat_id": "g1", "value": "abc", "reason": "r", "evidence": [wrong_ids[0]]}, "bad offset"),
    ("not a dict", "not an object"),
]
for change, why in bad:
    ok, _m, _c = rv.apply_change(st, "A", change, actor="review", valid_evidence=shown, now=NOW)
    check(f"review rejects: {why}", not ok)
check("owner lesson still there", st.get_lesson("A", owner_lesson) is not None)

# ---- owner (through chat) may do more ----
ok, _m, cid_role = rv.apply_change(st, "A", {"op": "role_profile_set", "text": "Đảm nhiệm: hỗ trợ học viên Javis và lịch học."},
                                   actor="owner", now=NOW)
check("owner may edit the role profile", ok and "lịch học" in st.get_role_profile("A")["generated_text"])

# ---- each op undoes cleanly ----
def roundtrip(change, probe, name):
    before = probe()
    ok, msg, cid = rv.apply_change(st, "A", change, actor="owner", now=NOW)
    mid = probe()
    ok2, _ = rv.revert_change(st, cid, bot_id="A", now=NOW)
    check(f"{name}: applies and undoes", ok and ok2 and mid != before and probe() == before, (msg, before, mid, probe()))


roundtrip({"op": "offset_set", "chat_id": "g9", "value": 0.2}, lambda: round(st.get_offset("A", "g9", NOW), 4), "offset_set")
roundtrip({"op": "eagerness_set", "value": "low"}, lambda: st.get_tuning("A").get("eagerness"), "eagerness_set")
roundtrip({"op": "case_add", "decision_id": tag_ids[4], "verdict": "reply"}, lambda: st.count_cases("A"), "case_add")
cid_case = st.add_case("A", "g1", "câu mẫu cũ do máy viết", {}, "silent", "r", "bootstrap", 0.5, now=NOW)
roundtrip({"op": "case_remove", "id": cid_case},
          lambda: sorted(c["text"] for c in st.list_cases("A", 500)), "case_remove")
roundtrip({"op": "lesson_add", "text": "luật chủ nhờ qua chat về khuyến mãi"},
          lambda: [x["text"] for x in st.list_lessons("A")], "lesson_add")
ok, _ = rv.revert_change(st, cid_role, bot_id="B", now=NOW)
check("a change id cannot be undone through another bot", not ok)
rv.revert_change(st, cid_role, bot_id="A", now=NOW)
ok, _ = rv.revert_change(st, cid_role, bot_id="A", now=NOW)
check("an undone change cannot be undone twice", not ok)

# ---- undo a whole review, then the same change is not retried for 14 days ----
n, lines = rv.revert_review(st, res["review_id"], bot_id="A", now=NOW + H)
check("revert_review undoes both changes", n == 2 and st.get_tuning("A").get("consider_tagged") in (None, "0")
      and not any(x["source"] == "review" for x in st.list_lessons("A")), lines)
st.set_review_ts("A", 0.0)
res2 = run(rv.run_review("A", store=st, ask=fake(payload), now=NOW + 2 * H, bot_cfg=CFG))
check("a recently reverted change is not re-applied", st.get_tuning("A").get("consider_tagged") in (None, "0")
      and any("14 ngày" in r for r in res2["rejected"]), res2)

# ---- failures change nothing ----
before = (st.get_tuning("A"), [x["text"] for x in st.list_lessons("A")])
for payload_bad, why in (("không phải json", "bad JSON"), (RuntimeError("engine down"), "model error"),
                         ({"changes": "x"}, "changes not a list")):
    st.set_review_ts("A", 0.0)
    r = run(rv.run_review("A", store=st, ask=fake(payload_bad), now=NOW + 3 * H, bot_cfg=CFG))
    check(f"{why}: nothing changed, time still recorded",
          not r["ok"] and (st.get_tuning("A"), [x["text"] for x in st.list_lessons("A")]) == before
          and st.get_review_ts("A") == NOW + 3 * H)
check("no message when nothing happened", rv.review_message({"ok": True, "applied": [], "feedback": ""}) == "")
check("fenced JSON parses", rv.parse_review('```json\n{"changes": [], "summary": "ok"}\n```') is not None)

# ---- code feedback is noted and written ----
written = []
st.set_review_ts("A", 0.0)
r = run(rv.run_review("A", store=st, ask=fake({"changes": [], "summary": "", "code_feedback": "luật X trong mã chặn tin Y"}),
                      now=NOW + 4 * H, bot_cfg=CFG, write_feedback=lambda cfg, text: written.append((cfg["id"], text))))
check("feedback written to the brain", written == [("A", "luật X trong mã chặn tin Y")])
check("feedback logged as noted", any(c["op"] == "code_feedback" and c["status"] == "noted" for c in st.list_changes("A")))
check("feedback alone still messages the owner", "luật X" in rv.review_message(r))

# ---- measuring a review afterwards ----
E = "E"
for i in range(10):                                   # baseline week: 1 error in 10
    dec(E, f"tin nền {i}", ts=NOW - 3 * DAY + i * 60, label="missed" if i == 0 else "correct")
ids_e = [dec(E, f"cài đặt hỏi {i}", ts=NOW - DAY + i * 60, label="missed") for i in range(3)]
ok, _m, _c = rv.apply_change(st, E, {"op": "eagerness_set", "value": "low", "reason": "r", "evidence": [ids_e[0]]},
                             actor="review", review_id="rvE", valid_evidence=ids_e, now=NOW)
check("review change for bot E applied", ok)
check("too few labels after: still pending", rv.evaluate_due(st, NOW + H) == [])
for i in range(6):                                    # after: 4 errors in 6
    dec(E, f"sau khi đổi {i}", ts=NOW + H + i * 60, label="intruded" if i < 4 else "correct")
evs = rv.evaluate_due(st, NOW + 2 * H)
check("worse after the review: auto undone", [e["status"] for e in evs] == ["auto_reverted"]
      and st.get_tuning(E).get("eagerness") is None, evs)
check("revert message names the bot", "E" in rv.revert_message(evs[0]))

K = "K"
for i in range(8):
    dec(K, f"tin nền K {i}", ts=NOW - 3 * DAY + i * 60, label="missed" if i < 3 else "correct")
ids_k = [dec(K, "câu K", ts=NOW - DAY, label="missed")]
rv.apply_change(st, K, {"op": "eagerness_set", "value": "high", "reason": "r", "evidence": ids_k},
                actor="review", review_id="rvK", valid_evidence=ids_k, now=NOW)
for i in range(6):
    dec(K, f"sau K {i}", ts=NOW + H + i * 60, label="correct")
check("better after the review: kept", [e["status"] for e in rv.evaluate_due(st, NOW + 2 * H)] == ["kept"]
      and st.get_tuning(K).get("eagerness") == "high")

O = "O"
ids_o = [dec(O, "câu O", ts=NOW - DAY, label="missed")]
rv.apply_change(st, O, {"op": "eagerness_set", "value": "high", "reason": "r", "evidence": ids_o},
                actor="review", review_id="rvO", valid_evidence=ids_o, now=NOW)
check("too old to judge: kept", [e["status"] for e in rv.evaluate_due(st, NOW + rv.EVAL_MAX_AGE_S + DAY)] == ["kept"])
ok, _m, _c = rv.apply_change(st, O, {"op": "eagerness_set", "value": "low"}, actor="owner", now=NOW)
check("owner changes are never judged", ok and rv.evaluate_due(st, NOW + rv.EVAL_MAX_AGE_S + 2 * DAY) == [])

# ---- operator switch ----
os.environ[rv.REVIEW_ENV] = "0"
check("JAVIS_REPLY_POLICY_REVIEW=0 turns it off", not rv.enabled())
os.environ.pop(rv.REVIEW_ENV)
check("on by default", rv.enabled())

if _fails:
    print(f"\n{len(_fails)} FAIL")
    sys.exit(1)
print("\nall ok")
