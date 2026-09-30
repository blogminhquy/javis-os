"""Kho của bộ phán xử hội thoại nhóm (0.65.0): dữ liệu, giữ hạn, trần, và CÁCH LY GIỮA CÁC BOT.

    python tests/run.py reply_policy_store      (KHÔNG mạng)

Chủ dự án chạy nhiều bot lĩnh vực không liên quan (Javis Vũ, Nhi Mai, Ngọc Thu). Điều file này canh
nặng nhất: ca học ở bot này không bao giờ được tra ra ở bot kia, kể cả khi tin y hệt.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import os
import sys
import tempfile

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-rp-store-")
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


NOW = 1_800_000_000.0
DAY = 86400.0
F0 = {"address_level": "none", "follow_up": False, "question": True}

# ---- quyết định ----
d1 = st.log_decision({"bot_id": "A", "chat_id": "g1", "msg_id": "m1", "ts": NOW, "text": "x" * 900,
                      "sender": "Nam", "verdict": "silent", "candidate": True, "silence_code": "judge_silent",
                      "mode": "on", "signals": {"question_score": 0.6}}, NOW)
row = st.get_decision(d1)
check("ghi quyết định, nội dung cắt 400 ký tự", row and len(row["text"]) == 400)
check("recent_decisions theo bot", len(st.recent_decisions("A")) == 1 and st.recent_decisions("B") == [])
check("only_silent lọc đúng", len(st.recent_decisions("A", only_silent=True)) == 1)

# ---- nhãn: nhãn đầu thắng, chủ ghi đè được ----
check("set_label lần đầu ok", st.set_label(d1, "missed", 1.0, NOW) is not None)
check("set_label lần hai bị từ chối (nhãn đầu thắng)", st.set_label(d1, "correct", 1.0, NOW) is None)
check("nhãn vẫn là missed", st.get_decision(d1)["label"] == "missed")
check("force_label của chủ ghi đè", st.force_label(d1, "correct", 1.5, NOW)["label"] == "correct")

# ---- cửa theo dõi ----
d2 = st.log_decision({"bot_id": "A", "chat_id": "g1", "ts": NOW, "text": "câu khác", "verdict": "silent",
                      "candidate": True}, NOW)
st.add_watch(d2, "A", "g1", NOW + 600, 2)
check("open_watches thấy cửa còn hạn", [w["id"] for w in st.open_watches("A", "g1", NOW + 10)] == [d2])
check("cửa của cuộc chat khác không lẫn vào", st.open_watches("A", "g2", NOW + 10) == [])
check("cửa của bot khác không lẫn vào", st.open_watches("B", "g1", NOW + 10) == [])
st.tick_watch(d2)
st.tick_watch(d2)
check("hết số tin thì cửa đóng", st.open_watches("A", "g1", NOW + 10) == [])
st.add_watch(d2, "A", "g1", NOW + 600, 5)
check("hết hạn giờ thì cửa đóng", st.open_watches("A", "g1", NOW + 601) == [])

# ---- ca, cách ly giữa bot, xếp hạng ----
TEXT = "Javis báo lỗi cổng 7777 đang bị dùng thì làm sao"
ca = st.add_case("A", "g1", TEXT, F0, "reply", "label:missed", "auto", 1.0, now=NOW)
st.add_case("B", "g9", TEXT, F0, "silent", "label:intruded", "auto", 1.0, now=NOW)
fa = rp.find_cases(st, "A", "g1", TEXT, F0, now=NOW)
fb = rp.find_cases(st, "B", "g9", TEXT, F0, now=NOW)
fc = rp.find_cases(st, "C", "g5", TEXT, F0, now=NOW)
check("bot A tra ra ca của A", any(c["id"] == ca and c["verdict"] == "reply" for c in fa), fa)
check("bot A KHÔNG thấy ca của bot B (tin y hệt)", all(c["verdict"] == "reply" for c in fa if c["source"] != "mechanic"))
check("bot B chỉ thấy ca của B", [c["verdict"] for c in fb if c["source"] != "mechanic"] == ["silent"], fb)
check("bot C chưa học gì thì không có ca thật nào", [c for c in fc if c["source"] != "mechanic"] == [], fc)

# Cùng nội dung: ca cùng cuộc chat xếp trên ca cuộc chat khác; ca mới xếp trên ca cũ; ca nặng trên ca nhẹ.
st.add_case("D", "g1", TEXT, F0, "reply", "cùng chat", "auto", 1.0, now=NOW)
st.add_case("D", "g2", TEXT, F0, "silent", "chat khác", "auto", 1.0, now=NOW)
r = [c for c in rp.find_cases(st, "D", "g1", TEXT, F0, now=NOW) if c["source"] != "mechanic"]
check("cùng cuộc chat xếp trên", r and r[0]["reason"] == "cùng chat", r)
st.add_case("E", "g1", TEXT, F0, "reply", "cũ", "auto", 1.0, now=NOW - 120 * DAY)
st.add_case("E", "g1", TEXT, F0, "silent", "mới", "auto", 1.0, now=NOW)
r = [c for c in rp.find_cases(st, "E", "g1", TEXT, F0, now=NOW) if c["source"] != "mechanic"]
check("ca mới xếp trên ca cũ (nhạt theo tuổi)", r and r[0]["reason"] == "mới", r)
st.add_case("F", "g1", TEXT, F0, "silent", "nhẹ", "auto", 0.3, now=NOW)
st.add_case("F", "g1", TEXT, F0, "reply", "nặng", "owner", 2.0, now=NOW)
r = [c for c in rp.find_cases(st, "F", "g1", TEXT, F0, now=NOW) if c["source"] != "mechanic"]
check("ca do chủ dạy (nặng) xếp trên ca nhẹ", r and r[0]["reason"] == "nặng", r)
st.add_case("G", "g1", "hôm nay trời rất đẹp", F0, "silent", "lạc đề", "auto", 1.0, now=NOW)
check("ca không chung chữ nào thì không được tra ra",
      [c for c in rp.find_cases(st, "G", "g1", TEXT, F0, now=NOW) if c["source"] != "mechanic"] == [])

# Mẫu cơ chế chung: tối đa hai, chỉ khi đặc trưng khớp, và chỗ giữ được thay bằng tên bot.
feat_follow = {"address_level": "possible", "follow_up": True, "question": True}
m = [c for c in rp.find_cases(st, "Z", "gz", "vậy còn cái kia thì sao", feat_follow, bot_name="Nhi Mai",
                              topic="chăm sóc da", now=NOW) if c["source"] == "mechanic"]
check("mẫu cơ chế theo đặc trưng, tối đa 2", 1 <= len(m) <= 2, m)
check("mẫu cơ chế không còn chỗ giữ chưa thay", all("{" not in c["text"] + c["reason"] for c in m), m)
m2 = rp.find_cases(st, "Z", "gz", "x", {"address_level": "certain", "follow_up": False, "question": False},
                   bot_name="Nhi Mai", now=NOW)
check("tên bot được thay vào mẫu cơ chế", any("Nhi Mai" in c["text"] for c in m2), m2)

# ---- trần ca ----
old_cap = st.MAX_CASES_PER_BOT
st.MAX_CASES_PER_BOT = 4
for i in range(6):
    st.add_case("H", "g1", f"tình huống số {i} riêng biệt", F0, "silent", "r", "auto", 1.0, now=NOW + i)
owner = st.add_case("H", "g1", "lời dạy của chủ", F0, "reply", "r", "owner", 1.0, now=NOW - 400 * DAY)
check("vượt trần thì giữ đúng 4 ca", st.count_cases("H") == 4, st.count_cases("H"))
check("ca do chủ dạy không bị bỏ trước dù cũ", any(c["id"] == owner for c in st.list_cases("H")))
st.MAX_CASES_PER_BOT = old_cap

# ---- ca khởi tạo nhạt dần và biến mất ----
b1 = st.add_case("I", "", "hướng dẫn cài đặt cổng", F0, "reply", "khởi tạo", "bootstrap", 0.5, now=NOW)
st.set_case_weight(b1, 0.2)
check("hạ trọng số ca khởi tạo", next(c for c in st.list_cases("I") if c["id"] == b1)["weight"] == 0.2)
st.set_case_weight(b1, 0.05)
check("dưới 0.1 thì xoá hẳn", st.count_cases("I") == 0)

# ---- độ lệch ngưỡng ----
check("chưa học thì lệch 0", st.get_offset("A", "g1", NOW) == 0.0)
check("cộng độ lệch", abs(st.adjust_offset("A", "g1", -0.05, NOW) + 0.05) < 1e-9)
check("kẹp ở -0.25", st.adjust_offset("A", "g1", -5.0, NOW) == -0.25)
check("kẹp ở +0.25", st.adjust_offset("A", "g2", 5.0, NOW) == 0.25)
check("độ lệch tách theo cuộc chat", st.get_offset("A", "g1", NOW) == -0.25 and st.get_offset("A", "g2", NOW) == 0.25)
check("độ lệch tách theo bot", st.get_offset("B", "g1", NOW) == 0.0)
check("nhạt dần: sau 14 ngày còn một nửa", abs(st.get_offset("A", "g1", NOW + 14 * DAY) + 0.125) < 1e-6)
pa = rp.BotProfile(bot_id="A", eagerness="medium", learning_enabled=True)
check("ngưỡng = gốc + lệch", abs(rp.threshold_for(pa, st, "g1", NOW) - 0.35) < 1e-9)
pa.learning_enabled = False
check("tắt học thì lệch bị bỏ qua", rp.threshold_for(pa, st, "g1", NOW) == 0.60)
pa.learning_enabled, pa.eagerness = True, "high"
st.adjust_offset("A", "g3", -0.25, NOW)
check("ngưỡng không xuống dưới 0.30", rp.threshold_for(pa, st, "g3", NOW) == 0.30)
pa.eagerness = "low"
st.adjust_offset("A", "g4", 0.25, NOW)
check("ngưỡng không vượt 0.90", rp.threshold_for(pa, st, "g4", NOW) == 0.90)

# ---- bài học ----
check("thêm bài học", st.add_lesson("J", "Gọi tên trơn cũng là gọi bot", NOW) is True)
check("khử trùng (chữ hoa/dấu/cách khác)", st.add_lesson("J", "gọi TÊN trơn cũng là  gọi bot", NOW) is False)
for i in range(20):
    st.add_lesson("J", f"bài học riêng biệt {chr(97 + i) * 4} về cách nói", NOW + i)
check("tối đa 15 dòng, dòng cũ rơi ra", len(st.list_lessons("J")) == 15
      and all("Gọi tên trơn" not in x["text"] for x in st.list_lessons("J")))
check("bài học tách theo bot", st.list_lessons("K") == [])

# ---- hồ sơ vai ----
st.set_role_profile("J", "Đảm nhiệm: mỹ phẩm", "h1", NOW)
check("hồ sơ vai lưu và đọc", st.get_role_profile("J")["agent_hash"] == "h1")
check("hồ sơ vai tách theo bot", st.get_role_profile("K") is None)

# ---- quên ----
st.add_case("L", "g1", "ca một", F0, "reply", "r", "auto", 1.0, now=NOW)
st.add_case("L", "g2", "ca hai khác hẳn", F0, "reply", "r", "auto", 1.0, now=NOW)
st.add_case("L", "", "ca khởi tạo giữ lại", F0, "reply", "r", "bootstrap", 0.5, now=NOW)
st.add_lesson("L", "bài học L", NOW)
st.adjust_offset("L", "g1", 0.1, NOW)
st.adjust_offset("L", "g2", 0.1, NOW)
st.forget("L", "g1")
check("quên một cuộc chat: chỉ ca và ngưỡng của cuộc chat đó", st.get_offset("L", "g1", NOW) == 0.0
      and st.get_offset("L", "g2", NOW) > 0 and st.count_cases("L", "auto") == 1)
res = st.forget("L")
check("quên hết: ca học, ngưỡng, bài học sạch; ca khởi tạo còn", st.count_cases("L", "auto") == 0
      and st.count_cases("L", "bootstrap") == 1 and st.list_lessons("L") == [] and st.get_offset("L", "g2", NOW) == 0.0, res)
check("quên bot này không đụng bot khác", st.count_cases("A") >= 1)

# ---- giữ hạn ----
old = st.log_decision({"bot_id": "P", "chat_id": "g", "ts": NOW - 20 * DAY, "text": "cũ", "verdict": "silent"}, NOW)
lab = st.log_decision({"bot_id": "P", "chat_id": "g", "ts": NOW - 20 * DAY, "text": "cũ có nhãn", "verdict": "silent"}, NOW)
st.set_label(lab, "missed", 1.0, NOW)
new = st.log_decision({"bot_id": "P", "chat_id": "g", "ts": NOW - DAY, "text": "mới", "verdict": "silent"}, NOW)
st.add_case("P", "g", "ca rất cũ của auto", F0, "reply", "r", "auto", 1.0, now=NOW - 200 * DAY)
st.add_case("P", "g", "ca rất cũ của chủ", F0, "reply", "r", "owner", 1.0, now=NOW - 200 * DAY)
out = st.purge(NOW)
ids = {r["id"] for r in st.recent_decisions("P")}
check("purge bỏ quyết định chưa nhãn quá 14 ngày", old not in ids and out["decisions_unlabeled"] >= 1, out)
check("quyết định có nhãn còn giữ (dưới 180 ngày)", lab in ids and new in ids)
check("purge bỏ ca tự động quá 180 ngày, giữ ca của chủ", [c["source"] for c in st.list_cases("P")] == ["owner"], st.list_cases("P"))

# ---- xoá bot ----
st.delete_bot("A")
s = st.stats("A")
check("xoá bot: không còn dòng nào", s["decisions"] == 0 and s["cases"] == 0 and s["lessons"] == 0, s)
check("xoá bot A không đụng bot B", st.count_cases("B") == 1)

check("kho nằm trong thư mục state, không phải trong repo", str(st.db_path()).startswith(os.environ["JAVIS_STATE_DIR"]))

print()
if _fails:
    print(f"{len(_fails)} FAIL")
    sys.exit(1)
print("ALL PASS")
