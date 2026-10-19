"""0.227.0: bot đọc đủ tin dài trong nhóm Zalo.

    python tests/run.py bot_doc_du_tin_dai      (KHÔNG mạng)

Nhóm của chủ (19/10): bot báo chị Diệu "tin của chị phần cuối bị cắt" rồi hỏi lại mức phụ thu, trong khi chị đã nhắn đủ, có
cả mức phụ thu 1-2 triệu. Ngữ cảnh nhóm đưa cho bot chỉ giữ 300 ký tự đầu của mỗi tin cũ; tin của chị dài chừng 470 ký tự.
Người phán xử (bot có nên lên tiếng không) cũng chỉ đọc 400 ký tự đầu của tin cần quyết.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import os
import sys
import tempfile
import time

_STATE = tempfile.mkdtemp(prefix="javis-tindai-")
os.environ["JAVIS_STATE_DIR"] = _STATE
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import chatbot_reply_policy as rp  # noqa: E402
import chatbot_runtime  # noqa: E402
import conversations  # noqa: E402

fails = []


def check(name, cond, them=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(them) + "]") if them and not cond else ""))
    if not cond:
        fails.append(name)


NOW = time.time()


def ghi(chat, i, text, ten="Diệu", loai="customer"):
    return conversations.ghi_su_kien({
        "channel": "zalo_personal", "account_id": "zp1", "account_name": "Nick", "bot_id": "",
        "external_chat_id": chat, "chat_type": "group", "chat_title": "Nhóm " + chat,
        "sender_type": loai, "sender_id": "u-" + ten, "sender_name": ten, "text": text,
        "external_message_id": f"{chat}-{i}", "created_at": NOW - 1000 + i})


# ---- 1. Đúng ca của chủ ----
DIEU = ("Chào em, chị muốn hỏi về gói tiệc cưới ngày 12/12 cho khoảng 30 bàn, thực đơn chị đã chọn bản số 2 có thêm món "
        "lẩu hải sản, nhà hàng có xe đưa đón khách từ đầu ngõ vào không, chị cần sân khấu nhỏ cho ban nhạc và một khu chụp "
        "ảnh có hoa tươi, bàn tiếp tân phía trước, phần trang trí bên chị gửi báo giá sau cũng được. Bên chị cũng cần phòng "
        "chờ cho cô dâu trang điểm từ sáng sớm và chỗ đỗ xe cho khoảng hai chục ô tô. Về phần phát sinh thì chị chấp nhận "
        "mức phụ thu 1-2 triệu nếu kéo dài thêm giờ.")
check("(chuẩn bị) tin của chị Diệu dài hơn 300 ký tự như thật", 400 < len(DIEU) < 600, len(DIEU))
ghi("g1", 1, DIEU)
ghi("g1", 2, "@Bot bên em báo giá giúp chị nhé", ten="Diệu")
khoi = chatbot_runtime.ngu_canh_nhom({"chat_type": "group", "chat_id": "g1", "message_id": "g1-2"}, "zalo_personal", "zp1")
check("ngữ cảnh nhóm có ĐỦ tin của chị Diệu, cả đoạn phụ thu ở cuối", "phụ thu 1-2 triệu nếu kéo dài thêm giờ" in khoi, khoi[-160:])
check("tin đủ thì không có dấu rút gọn", rp.clean_chat_text(DIEU, 10000) in khoi and "[…]" not in khoi)

# ---- 2. Tin RẤT dài: rút gọn có dấu, bot được dặn không nói với khách là tin bị cắt ----
DAI = "Danh sách khách mời: " + ", ".join(f"Khách số {i}" for i in range(600))
ghi("g2", 1, DAI, ten="Hà")
ghi("g2", 2, "câu hỏi đang hỏi", ten="Hà")
k2 = chatbot_runtime.ngu_canh_nhom({"chat_type": "group", "chat_id": "g2", "message_id": "g2-2"}, "zalo_personal", "zp1")
check("tin dài hơn trần: rút gọn còn đúng trần, kết thúc bằng dấu […]",
      k2.endswith(chatbot_runtime.LUOC) and len(k2.split(": ", 1)[1]) == chatbot_runtime.NGU_CANH_CHU, len(k2))
check("trần mỗi tin đủ rộng cho tin Zalo bình thường (>= 2000 ký tự)", chatbot_runtime.NGU_CANH_CHU >= 2000)
check("prompt dặn: tin có dấu […] là hệ thống rút gọn, đừng nói với khách là tin bị cắt",
      "[…]" in chatbot_runtime._NGU_CANH_NHOM and "đừng nói với họ là tin của họ bị cắt" in chatbot_runtime._NGU_CANH_NHOM)

# ---- 3. Nhiều tin dài: giữ tin MỚI nguyên vẹn, bỏ tin CŨ ----
for i in range(1, 31):
    ghi("g3", i, f"#{i} " + ("chữ " * 450), ten="An")
ghi("g3", 31, "câu đang hỏi", ten="An")
k3 = chatbot_runtime.ngu_canh_nhom({"chat_type": "group", "chat_id": "g3", "message_id": "g3-31"}, "zalo_personal", "zp1")
d3 = k3.split("\n")
check("tổng không quá trần của khối", len(k3) <= chatbot_runtime.NGU_CANH_TONG, len(k3))
check("tin mới nhất trước câu hỏi còn NGUYÊN", d3[-1].startswith("An: #30 ") and "[…]" not in d3[-1], d3[-1][:20])
check("quá trần thì bỏ tin cũ nhất", not any(x.startswith("An: #1 ") for x in d3) and len(d3) >= 6, len(d3))

# ---- 4. Người phán xử thấy cả đuôi tin dài ----
ev_text = "Chào cả nhà, " + "chuyện phiếm " * 60 + "vậy giá phụ thu là bao nhiêu hả bot?"
check("(chuẩn bị) câu hỏi nằm sau ký tự 400", ev_text.index("giá phụ thu") > 400)
ev = rp.Event(channel="zalo_personal", bot_id="b", chat_id="g4", chat_type="group", msg_id="m1", ts=NOW, text=ev_text,
              sender_id="u1", sender_name="Diệu", sender_role="known",
              window=[rp.Message(NOW - 5, "u2", "Hà", False, rp.clean_chat_text(DIEU, rp.WINDOW_TEXT_MAX))])
pr = rp.build_prompt(ev, rp.BotProfile(bot_id="b", name="Bot", role_text="Trợ lý nhà hàng"), "none",
                     rp.AddressResult("none", []), {}, [], [])
check("người phán xử thấy câu hỏi ở cuối tin dài", "giá phụ thu là bao nhiêu" in pr)
check("và thấy đủ tin dài trước đó trong cửa sổ", "phụ thu 1-2 triệu" in pr)
src = (SERVER / "chatbot_reply_policy.py").read_text(encoding="utf-8")
check("cửa sổ lưu mỗi tin tới WINDOW_TEXT_MAX ký tự", "clean_chat_text(msg.text, WINDOW_TEXT_MAX)" in src and rp.WINDOW_TEXT_MAX >= 800)

if fails:
    print(f"\nFAIL {len(fails)}: " + ", ".join(fails))
    sys.exit(1)
print("\nOK - test_bot_doc_du_tin_dai: all pass")
