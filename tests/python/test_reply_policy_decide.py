"""Bộ phán xử hội thoại nhóm (0.65.0): luồng quyết định, học từ phản ứng, cách ly giữa bot.

    python tests/run.py reply_policy_decide      (KHÔNG mạng; người phán xử là bản giả)

Người phán xử là tham số `ask`, nên toàn bộ luồng chạy được dưới CI mà không cần model thật.

Ba nhóm ý được canh:
  1. QUYẾT ĐỊNH: gọi chắc chắn thì trả lời luôn, không tốn model; mọi lỗi (model hỏng, hết giờ, JSON
     rác) ra IM; luật căn cứ tài liệu và hạn mức không bị ca đã học qua mặt.
  2. HỌC TỨC THÌ: im nhầm rồi bị hỏi lại thì lần sau CÙNG loại tin bot nói; chen nhầm rồi bị nhắc thì
     ngưỡng nâng lên. Chỉ tín hiệu mạnh mới thành nhãn, chỉ CHỦ mới dạy được luật.
  3. CÁCH LY: ba bot khác lĩnh vực không đọc được ca, bài học hay hồ sơ vai của nhau, và ngưỡng của
     nhóm này không đổi nhóm kia.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import json
import os
import sys
import tempfile

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-rp-decide-")
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import chatbot_reply_policy as rp  # noqa: E402
import chatbot_reply_policy_store as st  # noqa: E402

_fails = []


def check(name, cond, them=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(them) + "]") if them and not cond else ""))
    if not cond:
        _fails.append(name)


def run(coro):
    return asyncio.run(coro)


NOW = 1_800_000_000.0
BOSS = "boss1"


def mk_profile(bot_id="bot_a", name="Javis Vũ", **kw):
    base = dict(bot_id=bot_id, name=name, auto_aliases=[name], mode="on", learning_enabled=True,
                trainer_ids=[BOSS], role_text="Đảm nhiệm: hỗ trợ cài đặt Javis.", grounding="docs")
    base.update(kw)
    return rp.BotProfile(**base)


def ev(text, *, bot_id="bot_a", chat="g1", sender="u1", name="Nam", ts=NOW, **kw):
    p = kw.pop("_profile", None)
    role = kw.pop("sender_role", None)
    e = rp.Event(channel="zalo_personal", bot_id=bot_id, chat_id=chat, chat_type="group", msg_id=f"m{ts}",
                 ts=ts, text=text, sender_id=sender, sender_name=name, **kw)
    e.sender_role = role or ("owner" if sender == BOSS else "new")
    return e


class Judge:
    """Người phán xử giả: kịch bản do test đặt, và ghi lại mọi prompt nhận được."""

    def __init__(self, verdict="reply", score=0.9, reason="ok", raw=None, boom=False, delay=0.0):
        self.verdict, self.score, self.reason, self.raw = verdict, score, reason, raw
        self.boom, self.delay = boom, delay
        self.prompts = []
        self.purposes = []
        self.queue = []

    async def __call__(self, prompt, purpose=""):
        self.prompts.append(prompt)
        self.purposes.append(purpose)
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.boom:
            raise RuntimeError("engine down")
        if self.queue:
            return self.queue.pop(0)
        if self.raw is not None:
            return self.raw
        return json.dumps({"verdict": self.verdict, "score": self.score, "reason": self.reason})


async def docs_yes(text):
    return {"co": True, "khoi": "Đoạn tài liệu khớp về cổng 7777."}


async def docs_no(text):
    return {"co": False, "khoi": ""}


Q = "Javis báo lỗi cổng 7777 đang bị dùng thì làm sao ạ?"

# ============================================================
# 1. Quyết định
# ============================================================
P = mk_profile()
j = Judge()
d = run(rp.decide(ev("javis vũ ơi"), P, store=st, ask=j, doc_search=docs_no, now=NOW))
check("gọi chắc chắn: trả lời luôn", d.verdict == "reply" and d.address_level == "certain" and d.candidate)
check("gọi chắc chắn: KHÔNG tốn lượt model", j.prompts == [])
check("gọi chắc chắn: có dòng nhật ký", st.get_decision(d.decision_id)["verdict"] == "reply")
check("gọi chắc chắn: không mở cửa theo dõi (không phải lời tự nói)", st.open_watches("bot_a", "g1", NOW + 1) == [])

j = Judge()
d = run(rp.decide(ev("hôm nay trời đẹp thật đấy mọi người"), P, store=st, ask=j, doc_search=docs_yes, now=NOW))
check("chuyện phiếm: im, mã no_signal", d.verdict == "silent" and d.silence_code == "no_signal" and not d.candidate)
check("chuyện phiếm: KHÔNG tốn model", j.prompts == [])
row = st.get_decision(d.decision_id)
check("chuyện phiếm: VẪN có dấu vết trong nhật ký (lỗi 'im không để lại gì' không lặp lại)",
      row and row["silence_code"] == "no_signal" and row["text"].startswith("hôm nay"))
d = run(rp.decide(ev("ok"), P, store=st, ask=Judge(), doc_search=docs_yes, now=NOW))
check("junk cũng có dấu vết", d.silence_code == "junk" and st.get_decision(d.decision_id) is not None)

j = Judge("reply", 0.9)
d = run(rp.decide(ev(Q, ts=NOW + 1), P, store=st, ask=j, doc_search=docs_yes, now=NOW + 1))
check("câu hỏi có căn cứ + model nói reply 0.9 >= 0.6: trả lời", d.verdict == "reply" and d.score == 0.9 and d.threshold == 0.60, d)
check("tốn đúng một lượt model", len(j.prompts) == 1 and j.purposes == ["judge"])
check("prompt có tin cần quyết và tài liệu khớp", "cổng 7777" in j.prompts[0] and "Đoạn tài liệu khớp" in j.prompts[0])
check("đã mở cửa theo dõi cho lời tự nói", len(st.open_watches("bot_a", "g1", NOW + 2)) == 1)

j = Judge("reply", 0.5)
d = run(rp.decide(ev(Q, ts=NOW + 2), P, store=st, ask=j, doc_search=docs_yes, now=NOW + 2))
check("điểm 0.5 < ngưỡng 0.6: im, mã below_threshold", d.verdict == "silent" and d.silence_code == "below_threshold", d)
d = run(rp.decide(ev(Q, ts=NOW + 3), P, store=st, ask=Judge("silent", 0.95), doc_search=docs_yes, now=NOW + 3))
check("model nói silent thì im dù điểm cao", d.verdict == "silent" and d.silence_code == "judge_silent")

for name, jj in (("JSON rác", Judge(raw="tôi nghĩ nên nói")), ("engine ném lỗi", Judge(boom=True)),
                 ("sai khuôn", Judge(raw='{"verdict":"maybe","score":1}')), ("thiếu điểm", Judge(raw='{"verdict":"reply"}'))):
    d = run(rp.decide(ev(Q, ts=NOW + 4), P, store=st, ask=jj, doc_search=docs_yes, now=NOW + 4))
    check(f"{name}: im, mã policy_error", d.verdict == "silent" and d.silence_code == "policy_error", d)
d = run(rp.decide(ev(Q, ts=NOW + 4), P, store=st, ask=None, doc_search=docs_yes, now=NOW + 4))
check("chưa nối model: im", d.verdict == "silent" and d.silence_code == "policy_error")
old_t = rp.JUDGE_TIMEOUT_S
rp.JUDGE_TIMEOUT_S = 0.05
import inspect  # noqa: E402
_orig = rp.run_judge


async def _fast(ask, prompt, timeout=0.05):
    return await _orig(ask, prompt, timeout=0.05)


rp.run_judge = _fast
d = run(rp.decide(ev(Q, ts=NOW + 4), P, store=st, ask=Judge(delay=1.0), doc_search=docs_yes, now=NOW + 4))
check("model chậm quá thời hạn: im", d.verdict == "silent" and d.silence_code == "policy_error", d)
rp.run_judge, rp.JUDGE_TIMEOUT_S = _orig, old_t

j = Judge()
d = run(rp.decide(ev(Q, ts=NOW + 5), P, store=st, ask=j, doc_search=docs_no, now=NOW + 5))
check("không có tài liệu khớp mà không ai gọi: im, KHÔNG tốn model", d.silence_code == "no_grounding" and j.prompts == [])
Prole = mk_profile(grounding="role")
j = Judge()
d = run(rp.decide(ev(Q, ts=NOW + 5), Prole, store=st, ask=j, doc_search=docs_no, now=NOW + 5))
check("bot nhận căn cứ là vai (grounding=role): không cần tài liệu, hỏi model", d.verdict == "reply" and len(j.prompts) == 1)

j = Judge()
d = run(rp.decide(ev(Q, ts=NOW + 6), P, store=st, ask=j, doc_search=docs_yes, rate_check=lambda: "rate_limited", now=NOW + 6))
check("hết hạn mức tự nói: im, KHÔNG tốn model", d.silence_code == "rate_limited" and j.prompts == [])
d = run(rp.decide(ev("javis vũ ơi", ts=NOW + 6), P, store=st, ask=j, doc_search=docs_yes, rate_check=lambda: "rate_limited", now=NOW + 6))
check("hạn mức tự nói KHÔNG chặn tin gọi chắc chắn", d.verdict == "reply")

j = Judge()
d = run(rp.decide(ev(Q, ts=NOW + 7, owner_typing=True), P, store=st, ask=j, doc_search=docs_yes, now=NOW + 7))
check("chủ đang gõ tay: nhường", d.silence_code == "owner_typing" and j.prompts == [])

# Tin nối tiếp: không cần tài liệu, người phán xử được hỏi.
j = Judge("reply", 0.8)
d = run(rp.decide(ev("vậy còn cái kia thì sao đây", ts=NOW + 8, bot_last_spoke_ts=NOW + 1, last_bot_addressee="u1"),
                  P, store=st, ask=j, doc_search=docs_no, now=NOW + 8))
check("tin nối tiếp sau lượt bot: level possible, hỏi model, không đòi tài liệu",
      d.address_level == "possible" and d.verdict == "reply" and len(j.prompts) == 1, d)

# Chạy thử (shadow): ghi quyết định nhưng KHÔNG mở cửa theo dõi.
P2 = mk_profile(bot_id="bot_s")
d = run(rp.decide(ev(Q, bot_id="bot_s", ts=NOW + 9), P2, store=st, ask=Judge(), doc_search=docs_yes, commit=False,
                  mode="shadow", now=NOW + 9))
check("shadow: có ghi, mode=shadow", st.get_decision(d.decision_id)["mode"] == "shadow")
check("shadow: không mở cửa theo dõi", st.open_watches("bot_s", "g1", NOW + 10) == [])
P3 = mk_profile(bot_id="bot_n", learning_enabled=False)
d = run(rp.decide(ev(Q, bot_id="bot_n", ts=NOW + 9), P3, store=st, ask=Judge(), doc_search=docs_yes, now=NOW + 9))
check("tắt học: không mở cửa theo dõi", st.open_watches("bot_n", "g1", NOW + 10) == [])

# ============================================================
# 2. Học tức thì: im nhầm
# ============================================================
A = mk_profile(bot_id="bot_learn")
j = Judge("silent", 0.3, "chưa chắc")
e1 = ev(Q, bot_id="bot_learn", sender="u1", name="Nam", ts=NOW + 100)
d1 = run(rp.decide(e1, A, store=st, ask=j, doc_search=docs_yes, now=NOW + 100))
check("ca 1: bot im vì model chưa chắc", d1.verdict == "silent" and d1.silence_code == "judge_silent")
check("ca 1: đang được theo dõi", [w["id"] for w in st.open_watches("bot_learn", "g1", NOW + 101)] == [d1.decision_id])

ph = ev("haha vui quá đi", bot_id="bot_learn", sender="u2", name="Hùng", ts=NOW + 110)
check("tin phớt lờ / không liên quan: KHÔNG thành nhãn", rp.observe(ph, A, st, now=NOW + 110) == [])
check("cửa theo dõi vẫn mở sau tin không liên quan", len(st.open_watches("bot_learn", "g1", NOW + 111)) == 1)

again = ev("sao không trả lời mình vậy", bot_id="bot_learn", sender="u1", name="Nam", ts=NOW + 130)
res = rp.observe(again, A, st, now=NOW + 130)
check("cùng người hỏi lại: nhãn missed (im nhầm) trọng số 1.0", res == [(d1.decision_id, "missed", 1.0)], res)
check("ngưỡng của cuộc chat hạ 0.05", abs(st.get_offset("bot_learn", "g1", NOW + 131) + 0.05) < 1e-6)
cases = st.list_cases("bot_learn")
check("thành một ca: quyết định đúng là reply", len(cases) == 1 and cases[0]["correct_verdict"] == "reply"
      and cases[0]["source"] == "auto", cases)
check("cửa theo dõi đã đóng", st.open_watches("bot_learn", "g1", NOW + 132) == [])
check("nhãn đã ghi vào nhật ký", st.get_decision(d1.decision_id)["label"] == "missed")

# Lần sau CÙNG loại tin: ca vừa học nằm trong prompt và ảnh hưởng quyết định ngay.
class Learner(Judge):
    async def __call__(self, prompt, purpose=""):
        self.prompts.append(prompt)
        seen = "-> reply" in prompt and "cổng 7777" in prompt.split("## Ca tương tự")[1].split("## Cuộc trò chuyện")[0]
        return json.dumps({"verdict": "reply" if seen else "silent", "score": 0.9 if seen else 0.3, "reason": "học"})


jl = Learner()
d2 = run(rp.decide(ev("Javis báo lỗi cổng 7777 đang bị dùng thì phải làm sao nhỉ?", bot_id="bot_learn", sender="u3",
                      name="Lan", ts=NOW + 300), A, store=st, ask=jl, doc_search=docs_yes, now=NOW + 300))
check("lần sau tin giống: prompt CÓ ca vừa học", "-> reply" in jl.prompts[0] and "label:missed" in jl.prompts[0])
check("lần sau tin giống: bot nói (đã học ngay, không chờ gom theo tuần)", d2.verdict == "reply", d2)
check("ngưỡng thấp hơn gốc sau khi học", abs(d2.threshold - 0.55) < 1e-3, d2.threshold)

# Tin không giống chữ nào thì ca không ảnh hưởng (không nhiễu sang chủ đề khác).
jl2 = Learner()
run(rp.decide(ev("cho mình hỏi cách đổi bộ não khác với", bot_id="bot_learn", sender="u4", name="Mai", ts=NOW + 310),
              A, store=st, ask=jl2, doc_search=docs_yes, now=NOW + 310))
check("tin khác chủ đề không kéo ca cũ vào prompt", "cổng 7777" not in jl2.prompts[0].split("## Ca tương tự")[1].split("## Cuộc trò chuyện")[0])

# Ca dương giống làm tin không giống câu hỏi vẫn thành ứng viên.
st.add_case("bot_pos", "g1", "cổng 7777 đang bị dùng bởi tiến trình khác", {"address_level": "none", "follow_up": False,
            "question": False}, "reply", "chủ dạy", "owner", 1.0, now=NOW)
B = mk_profile(bot_id="bot_pos")
jp = Judge("reply", 0.9)
dp = run(rp.decide(ev("cổng 7777 đang bị dùng bởi một tiến trình cũ", bot_id="bot_pos", ts=NOW + 320), B, store=st,
                   ask=jp, doc_search=docs_yes, now=NOW + 320))
check("ca dương giống làm tin thường thành ứng viên", dp.candidate and len(jp.prompts) == 1 and dp.verdict == "reply", dp)
dq = run(rp.decide(ev("cổng 7777 đang bị dùng bởi một tiến trình cũ", bot_id="bot_pos", ts=NOW + 321), B, store=st,
                   ask=Judge("reply", 0.9), doc_search=docs_no, now=NOW + 321))
check("nhưng ca đã học KHÔNG được miễn luật căn cứ tài liệu", dq.silence_code == "no_grounding", dq)

# ============================================================
# 3. Học tức thì: chen nhầm
# ============================================================
C = mk_profile(bot_id="bot_intr")
dj = run(rp.decide(ev(Q, bot_id="bot_intr", ts=NOW + 500), C, store=st, ask=Judge("reply", 0.9), doc_search=docs_yes,
                   now=NOW + 500))
check("bot chen vào (không ai gọi)", dj.verdict == "reply" and dj.address_level == "none")
boss = ev("đừng chen vào chuyện của nhóm", bot_id="bot_intr", sender=BOSS, name="Sếp", ts=NOW + 520)
res = rp.observe(boss, C, st, now=NOW + 520)
check("CHỦ nhắc 'đừng chen vào': nhãn intruded trọng số 1.0", res == [(dj.decision_id, "intruded", 1.0)], res)
check("ngưỡng nâng 0.08", abs(st.get_offset("bot_intr", "g1", NOW + 521) - 0.08) < 1e-6)
check("thành ca: quyết định đúng là silent", st.list_cases("bot_intr")[0]["correct_verdict"] == "silent")

dj2 = run(rp.decide(ev(Q + " ", bot_id="bot_intr", ts=NOW + 600, sender="u1"), C, store=st, ask=Judge("reply", 0.9),
                    doc_search=docs_yes, now=NOW + 600))
peer = ev("ai hỏi bot đâu mà trả lời", bot_id="bot_intr", sender="u5", name="Tùng", ts=NOW + 620)
res = rp.observe(peer, C, st, now=NOW + 620)
check("người thường nhắc cùng ý: chỉ trọng số 0.5", res == [(dj2.decision_id, "intruded", 0.5)], res)
check("ngưỡng chỉ nâng thêm 0.04", abs(st.get_offset("bot_intr", "g1", NOW + 621) - 0.12) < 1e-3, st.get_offset("bot_intr", "g1", NOW + 621))

# Được cảm ơn / hỏi tiếp đúng mạch: nhãn đúng, không đổi ngưỡng.
D = mk_profile(bot_id="bot_ok")
dk = run(rp.decide(ev(Q, bot_id="bot_ok", ts=NOW + 700), D, store=st, ask=Judge("reply", 0.9), doc_search=docs_yes, now=NOW + 700))
thanks = ev("cảm ơn bạn nhé", bot_id="bot_ok", sender="u1", name="Nam", ts=NOW + 710)
res = rp.observe(thanks, D, st, now=NOW + 710)
check("cảm ơn sau lời bot nói: nhãn correct 0.6", res == [(dk.decision_id, "correct", 0.6)], res)
check("nhãn đúng không đổi ngưỡng", st.get_offset("bot_ok", "g1", NOW + 711) == 0.0)

# ============================================================
# 4. Chống lạm dụng nhãn
# ============================================================
E = mk_profile(bot_id="bot_spam")
rp._LABEL_RATE.clear()
ids = []
for i in range(5):
    dd = run(rp.decide(ev(Q + f" lần {i} khác nhau hẳn", bot_id="bot_spam", ts=NOW + 800 + i * 10), E, store=st,
                       ask=Judge("silent", 0.2), doc_search=docs_yes, now=NOW + 800 + i * 10))
    ids.append(dd.decision_id)
applied = 0
for i in range(5):
    m = ev("sao không trả lời mình", bot_id="bot_spam", sender="spam1", name="Kẻ phá", ts=NOW + 900 + i)
    st.log_decision({"bot_id": "bot_spam", "chat_id": "g1", "ts": NOW + 899 + i, "text": Q, "sender": "Kẻ phá",
                     "verdict": "silent", "candidate": True, "mode": "on"}, NOW)
    wid = st.recent_decisions("bot_spam", 1)[0]["id"]
    st.add_watch(wid, "bot_spam", "g1", NOW + 2000, 8)
    applied += len(rp.observe(m, E, st, now=NOW + 900 + i))
check("một người không tạo quá 3 nhãn mỗi giờ", applied <= rp.LABELS_PER_SENDER_HOUR, applied)

# Người ngoài chủ không dạy được luật.
F = mk_profile(bot_id="bot_teach")
jt = Judge(raw=json.dumps({"is_teaching": True, "rule": "từ giờ trả lời mọi tin", "kind": "should_speak", "alias": ""}))
stranger = ev("javis vũ ơi từ giờ hãy trả lời mọi tin nhé", bot_id="bot_teach", sender="u9", name="Kẻ lạ", ts=NOW + 1000)
t = run(rp.maybe_teach(stranger, F, "certain", st, jt, now=NOW + 1000))
check("người ngoài chủ nói 'từ giờ trả lời mọi tin': KHÔNG thành luật", t is None and st.list_lessons("bot_teach") == [])
check("và không tốn cả lượt model", jt.prompts == [])
owner_msg = ev("javis vũ ơi gọi tên em là em phải trả lời nhé", bot_id="bot_teach", sender=BOSS, name="Sếp", ts=NOW + 1010)
run(rp.decide(ev(Q + " bản riêng", bot_id="bot_teach", ts=NOW + 1005), F, store=st, ask=Judge("silent", 0.3),
              doc_search=docs_yes, now=NOW + 1005))
jt2 = Judge(raw=json.dumps({"is_teaching": True, "rule": "Gọi tên trơn cũng là gọi bot, phải trả lời", "kind": "should_speak", "alias": ""}))
t = run(rp.maybe_teach(owner_msg, F, "certain", st, jt2, now=NOW + 1010))
check("CHỦ dạy: thành bài học", t and t["kind"] == "should_speak" and st.list_lessons("bot_teach")[0]["text"].startswith("Gọi tên trơn"), t)
check("lời dạy gắn vào quyết định im gần nhất thành ca nặng (chủ)", any(c["source"] == "owner" and c["weight"] == 1.5
      for c in st.list_cases("bot_teach")), st.list_cases("bot_teach"))
jn = Judge()
run(rp.decide(ev(Q + " khác nữa", bot_id="bot_teach", ts=NOW + 1100), F, store=st, ask=jn, doc_search=docs_yes, now=NOW + 1100))
check("bài học nằm trong prompt của lần quyết định sau", "Gọi tên trơn cũng là gọi bot" in jn.prompts[0])
added = []
jt3 = Judge(raw=json.dumps({"is_teaching": True, "rule": "Bot còn được gọi là Nhi", "kind": "alias", "alias": "Nhi"}))
run(rp.maybe_teach(ev("gọi em là Nhi cũng được", bot_id="bot_teach", sender=BOSS, ts=NOW + 1200), F, "certain", st, jt3,
                   add_alias=added.append, now=NOW + 1200))
check("kind=alias thì thêm tên gọi mới", added == ["Nhi"], added)
jt4 = Judge(raw=json.dumps({"is_teaching": False}))
check("không phải lời dạy thì không làm gì", run(rp.maybe_teach(ev("cảm ơn nhé", bot_id="bot_teach", sender=BOSS, ts=NOW + 1300),
                                                               F, "certain", st, jt4, now=NOW + 1300)) is None)
check("tin của chủ không gọi bot (level none) thì không tốn lượt model",
      run(rp.maybe_teach(ev("hôm nay đi ăn gì", bot_id="bot_teach", sender=BOSS, ts=NOW + 1400), F, "none", st, jt4)) is None
      and len(jt4.prompts) == 1)

# ============================================================
# 5. Nhãn của chủ (👍 👎) và Tiếp quản
# ============================================================
G = mk_profile(bot_id="bot_thumb")
dr = run(rp.decide(ev(Q, bot_id="bot_thumb", ts=NOW + 1500), G, store=st, ask=Judge("reply", 0.9), doc_search=docs_yes, now=NOW + 1500))
ds = run(rp.decide(ev(Q + " b", bot_id="bot_thumb", ts=NOW + 1510), G, store=st, ask=Judge("silent", 0.2), doc_search=docs_yes, now=NOW + 1510))
check("👎 trên lần bot nói: intruded", rp.owner_label(st, G, dr.decision_id, "down", NOW + 1520) == "intruded")
check("👎 trên lần bot im: missed", rp.owner_label(st, G, ds.decision_id, "down", NOW + 1520) == "missed")
check("👍: correct", rp.owner_label(st, G, dr.decision_id, "up", NOW + 1530) == "correct")
check("nhãn của chủ nặng 1.5", st.get_decision(dr.decision_id)["label_weight"] == 1.5)
check("nút lạ thì bỏ qua", rp.owner_label(st, G, dr.decision_id, "sideways") is None)
check("nhãn cho quyết định của BOT KHÁC bị từ chối", rp.owner_label(st, mk_profile(bot_id="bot_other"), dr.decision_id, "up") is None)
H = mk_profile(bot_id="bot_take")
dt = run(rp.decide(ev(Q, bot_id="bot_take", ts=NOW + 1600), H, store=st, ask=Judge("reply", 0.9), doc_search=docs_yes, now=NOW + 1600))
check("Tiếp quản ngay sau lần bot tự nói: chen nhầm", rp.note_takeover(st, H, "g1", NOW + 1650) == 1
      and st.get_decision(dt.decision_id)["label"] == "intruded")
Noff = mk_profile(bot_id="bot_noL", learning_enabled=False)
check("tắt học thì không gắn nhãn", rp.note_takeover(st, Noff, "g1", NOW + 1650) == 0
      and rp.owner_label(st, Noff, dr.decision_id, "up") is None)

# ============================================================
# 6. Cách ly giữa ba bot khác lĩnh vực
# ============================================================
AGENTS = {
    "bot_sw": ("Javis Vũ", "Đảm nhiệm: cài đặt và lỗi phần mềm Javis."),
    "bot_beauty": ("Nhi Mai", "Đảm nhiệm: tư vấn mỹ phẩm và chăm sóc da."),
    "bot_english": ("Ngọc Thu", "Đảm nhiệm: dạy tiếng Anh giao tiếp."),
}
profiles = {b: mk_profile(bot_id=b, name=n, role_text=r) for b, (n, r) in AGENTS.items()}
QSAME = "cho mình hỏi cách bắt đầu ở đâu vậy mọi người"
judges = {b: Judge("silent", 0.2) for b in AGENTS}
for b in AGENTS:
    run(rp.decide(ev(QSAME, bot_id=b, ts=NOW + 2000), profiles[b], store=st, ask=judges[b], doc_search=docs_yes, now=NOW + 2000))
    st.add_lesson(b, f"Bài học riêng của {AGENTS[b][0]}", NOW + 2000)
# Chỉ bot_sw học được một ca im nhầm.
rp.observe(ev("sao không trả lời mình", bot_id="bot_sw", sender="u1", ts=NOW + 2010), profiles["bot_sw"], st, now=NOW + 2010)
judges2 = {b: Judge("silent", 0.2) for b in AGENTS}
for b in AGENTS:
    run(rp.decide(ev(QSAME + " nhé", bot_id=b, sender="u7", name="Mới", ts=NOW + 2100), profiles[b], store=st,
                  ask=judges2[b], doc_search=docs_yes, now=NOW + 2100))
p_sw, p_be, p_en = (judges2[b].prompts[0] for b in ("bot_sw", "bot_beauty", "bot_english"))
check("prompt mỗi bot chỉ có hồ sơ vai của chính nó",
      "phần mềm Javis" in p_sw and "mỹ phẩm" not in p_sw and "tiếng Anh" not in p_sw
      and "mỹ phẩm" in p_be and "phần mềm" not in p_be and "tiếng Anh" in p_en and "mỹ phẩm" not in p_en)
check("bài học: bot_beauty chỉ thấy bài học của mình",
      "Bài học riêng của Nhi Mai" in p_be and "Bài học riêng của Javis Vũ" not in p_be and "Bài học riêng của Ngọc Thu" not in p_be)
check("bài học: bot_english chỉ thấy bài học của mình",
      "Bài học riêng của Ngọc Thu" in p_en and "Bài học riêng của Nhi Mai" not in p_en)
check("ca học ở bot_sw KHÔNG xuất hiện ở prompt hai bot kia (tin y hệt)", "label:missed" in p_sw
      and "label:missed" not in p_be and "label:missed" not in p_en)
check("chỉ bot_sw có ca thật", st.count_cases("bot_sw") == 1 and st.count_cases("bot_beauty") == 0 and st.count_cases("bot_english") == 0)
check("ngưỡng của bot_sw đã đổi, hai bot kia không",
      st.get_offset("bot_sw", "g1", NOW + 2100) < 0 and st.get_offset("bot_beauty", "g1", NOW + 2100) == 0.0
      and st.get_offset("bot_english", "g1", NOW + 2100) == 0.0)
# Cùng một bot, hai nhóm: ngưỡng tách theo nhóm.
check("ngưỡng tách theo nhóm: nhóm g2 của bot_sw chưa bị đổi", st.get_offset("bot_sw", "g2", NOW + 2100) == 0.0)
# Cùng một câu gọi tên, ba bot: chỉ đúng bot được gọi trả lời.
res = {b: run(rp.decide(ev("nhi mai ơi", bot_id=b, ts=NOW + 2200), profiles[b], store=st, ask=Judge("silent", 0.1),
                        doc_search=docs_no, now=NOW + 2200)).verdict for b in AGENTS}
check("'nhi mai ơi' chỉ Nhi Mai trả lời", res == {"bot_sw": "silent", "bot_beauty": "reply", "bot_english": "silent"}, res)

# ============================================================
# 7. Hồ sơ vai và ca khởi tạo do model sinh theo lĩnh vực của CHÍNH bot
# ============================================================
class Author(Judge):
    async def __call__(self, prompt, purpose=""):
        self.prompts.append(prompt)
        self.purposes.append(purpose)
        if purpose == "profile":
            return "Đảm nhiệm:\n- tư vấn chăm sóc da\nKhông đảm nhiệm:\n- chính trị\nGiọng và xưng hô:\n- nhẹ nhàng\nKhi nào nên lên tiếng trong nhóm:\n- khi có người hỏi về da"
        return json.dumps([{"text": "da mình bị mụn thì dùng gì", "verdict": "reply", "reason": "đúng ngành"},
                           {"text": "trưa nay ăn gì", "verdict": "silent", "reason": "chuyện phiếm"},
                           {"text": "sai khuôn", "verdict": "maybe"}])


cfgb = {"id": "bot_beauty", "name": "Nhi Mai"}
au = Author()
r1 = run(rp.ensure_role_profile(cfgb, "Bạn là Nhi Mai, chuyên gia da liễu.", ["kem chống nắng", "trị mụn"], st, au))
check("soạn hồ sơ vai từ Agent + mục lục tài liệu của CHÍNH bot", r1["changed"] and "chăm sóc da" in r1["generated_text"], r1)
check("prompt soạn hồ sơ chứa Agent và mục lục của bot đó", "da liễu" in au.prompts[0] and "kem chống nắng" in au.prompts[0])
check("ca khởi tạo sinh theo lĩnh vực, bỏ phần tử sai khuôn", st.count_cases("bot_beauty", "bootstrap") == 2, st.list_cases("bot_beauty"))
check("hồ sơ vai lưu với agent_hash", st.get_role_profile("bot_beauty")["agent_hash"] == rp.agent_hash("Bạn là Nhi Mai, chuyên gia da liễu.", ["kem chống nắng", "trị mụn"]))
au2 = Author()
r2 = run(rp.ensure_role_profile(cfgb, "Bạn là Nhi Mai, chuyên gia da liễu.", ["kem chống nắng", "trị mụn"], st, au2))
check("Agent không đổi: KHÔNG soạn lại, không tốn model", not r2["changed"] and au2.prompts == [])
r3 = run(rp.ensure_role_profile(cfgb, "Bạn là Nhi Mai, chuyên gia trang điểm.", ["kem chống nắng", "trị mụn"], st, au2))
check("Agent đổi: soạn lại và thay ca khởi tạo (không nhân đôi)", r3["changed"] and st.count_cases("bot_beauty", "bootstrap") == 2)
check("bot khác không bị đụng", st.get_role_profile("bot_sw") is None and st.count_cases("bot_sw", "bootstrap") == 0)
au3 = Judge(raw="ngắn")
r4 = run(rp.ensure_role_profile({"id": "bot_bad", "name": "X"}, "agent", [], st, au3))
check("model trả hồ sơ quá ngắn thì không lưu", not r4["changed"] and st.get_role_profile("bot_bad") is None)
r5 = run(rp.ensure_role_profile({"id": "bot_none", "name": "X"}, "agent", [], st, None))
check("chưa nối model thì không làm gì", not r5["changed"])
# Ca thật cùng loại làm nhạt ca khởi tạo giống nó.
before = [c["weight"] for c in st.list_cases("bot_beauty") if c["source"] == "bootstrap" and "mụn" in c["text"]]
Bp = mk_profile(bot_id="bot_beauty", name="Nhi Mai")
dm = run(rp.decide(ev("da mình bị mụn thì dùng gì vậy", bot_id="bot_beauty", ts=NOW + 3000), Bp, store=st, ask=Judge("silent", 0.2),
                   doc_search=docs_yes, now=NOW + 3000))
rp.observe(ev("sao không trả lời mình vậy", bot_id="bot_beauty", sender="u1", name="Nam", ts=NOW + 3020), Bp, st, now=NOW + 3020)
after = [c["weight"] for c in st.list_cases("bot_beauty") if c["source"] == "bootstrap" and "mụn" in c["text"]]
check("ca thật làm nhạt ca khởi tạo giống nó (0.5 -> 0.25)", before and after and after[0] < before[0], (before, after))

# ============================================================
# 8. Cửa sổ trong bộ nhớ và ngữ cảnh bot
# ============================================================
rp.reset_runtime_state()
rp.push_message("bw", "gx", rp.Message(NOW, "u1", "Nam", False, "xin chào cả nhà"))
rp.note_bot_reply("bw", "gx", "u1", "dạ chào anh", NOW + 5)
w = rp.window_of("bw", "gx", NOW + 6)
check("cửa sổ giữ cả tin người và tin bot", [m.is_bot for m in w] == [False, True])
check("bot_context nhớ người được trả lời", rp.bot_context("bw", "gx", NOW + 6) == (NOW + 5, "u1"))
check("cuộc chat khác không lẫn", rp.window_of("bw", "gy", NOW + 6) == [] and rp.bot_context("bw", "gy", NOW + 6) == (None, ""))
check("quá 30 phút thì quên", rp.window_of("bw", "gx", NOW + 3600) == [] and rp.bot_context("bw", "gx", NOW + 3600) == (None, ""))
pw = mk_profile(bot_id="bw", trainer_ids=[BOSS])
check("sender_role: người vừa được bot trả lời là 'known'", rp.sender_role(pw, "u1") == "known" and rp.sender_role(pw, "u2") == "new"
      and rp.sender_role(pw, BOSS) == "owner")
for i in range(20):
    rp.push_message("bw", "gz", rp.Message(NOW + i, "u", "n", False, f"tin {i}"))
check("cửa sổ tối đa 8 tin", len(rp.window_of("bw", "gz", NOW + 30)) == rp.WINDOW_MAX)

print()
if _fails:
    print(f"{len(_fails)} FAIL")
    sys.exit(1)
print("ALL PASS")
