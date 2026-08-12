"""Bot chuyên trách: kho bản ghi + rào an toàn của bộ giám sát.

    python tests/run.py chatbot_store      (KHÔNG mạng)

Tính năng này khác mọi tính năng khác ở một điểm: người ở đầu bên kia là NGƯỜI LẠ. Mọi lỗi ở
đây không dừng ở "chủ thấy khó chịu" mà thành "khách nghe một câu sai từ cửa hàng". Nên test
canh đúng những chỗ mà một lần sửa ẩu là mở toang:

1. **Bot mới phải TẮT.** Gửi `enabled: true` lúc tạo mà kho nghe theo thì bot vừa tạo đã nói
   chuyện với khách thật, trước cả khi chủ kịp đọc lại prompt của Agent.

2. **Token không được rò ra giao diện.** `list_bots`/`get_bot` là thứ đổ thẳng vào JSON trả về
   trình duyệt. Một token Telegram lọt ra là ai cũng gửi được tin nhắn dưới danh nghĩa cửa hàng.

3. **Danh sách TRẮNG khi sửa.** Bản vá từ giao diện chỉ được chạm mấy trường đã khai. Nhận hết
   rồi trừ dần là kiểu bảo vệ hỏng ngay lần thêm trường mới.

4. **Bật mà chưa có token thì TỪ CHỐI.** Bật rồi để nó chết lặng trong bộ giám sát là đúng cái
   kiểu hỏng im lặng mà cả tính năng này sinh ra để tránh.

5. **Trong nhóm thì mặc định IM.** Bot bị thả vào một nhóm chưa khai mà tự nhận việc là nó chen
   vào giữa cuộc nói chuyện của khách với nhau.

6. **Lệnh là danh sách TRẮNG.** Bot chủ có /brain, /model, /status. Bot khách hàng mà kế thừa
   được một lệnh trong số đó thì khách đổi được brain của cửa hàng.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401  - nạp server/ vào sys.path
import asyncio
import os
import sys
import tempfile

_STATE = tempfile.mkdtemp(prefix="javis-chatbot-")
os.environ["JAVIS_STATE_DIR"] = _STATE

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import chatbot_store  # noqa: E402
import chatbot_runtime  # noqa: E402

_fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)


# CHỐT CHẶN - kho ghi ra STATE_DIR thật thì test này đè lên danh sách bot THẬT của người dùng.
if _STATE not in str(chatbot_store.STORE_PATH):
    print(f"FAIL kho không nằm trong thư mục tạm: {chatbot_store.STORE_PATH}. DỪNG.")
    sys.exit(1)


# ============================================================
# 1. Tạo
# ============================================================
bad, why = chatbot_store.create_bot({"agent_slug": "cskh", "brain": "shop"})
check("tạo thiếu tên -> từ chối", bad is None and "tên" in why.lower())

bad, why = chatbot_store.create_bot({"name": "Bot", "brain": "shop"})
check("tạo thiếu Agent -> từ chối", bad is None and "agent" in why.lower())

bad, why = chatbot_store.create_bot({"name": "Bot", "agent_slug": "cskh"})
check("tạo thiếu brain -> từ chối", bad is None and "brain" in why.lower())

# Slug Agent = TÊN FILE trong Javis/agents, và tên đó do người dùng đặt. Rào ở đây canh AN
# TOÀN ĐƯỜNG DẪN chứ không canh hình dạng: khuôn cũ chỉ nhận ASCII nên nó chặn đúng những
# Agent đặt tên tiếng Việt (`main._slugify` giữ nguyên dấu), và chặn bằng câu "Thiếu Agent"
# trong khi chủ đang nhìn thấy Agent mình vừa chọn trong ô.
for xau in ("../../etc/passwd", "a/b", "a\\b", ".hidden", "x" * 65, "  "):
    bad, why = chatbot_store.create_bot({"name": "Bot", "agent_slug": xau, "brain": "shop"})
    check(f"slug Agent nguy hiểm {xau!r} -> từ chối", bad is None and bool(why))

bid_vn, why = chatbot_store.create_bot({"name": "Bot tiếng Việt",
                                        "agent_slug": "tư-vấn-sản-phẩm", "brain": "shop"})
check("slug Agent tiếng Việt CÓ DẤU -> nhận", bool(bid_vn) and why == "")
check("slug tiếng Việt lưu nguyên vẹn",
      chatbot_store.get_bot(bid_vn)["agent"]["slug"] == "tư-vấn-sản-phẩm")
chatbot_store.delete_bot(bid_vn)

bid, why = chatbot_store.create_bot({
    "name": "Bot Chăm sóc khách",
    "agent_slug": "cskh",
    "agent_brain": "brain",
    "brain": "shop-cskh",
    "token": "123456:AAA-token-that",
    "bot_username": "@ShopCSKHBot",
    "groups": "-1001234567890, khong-phai-so, 987654321",
    "rate_limit": 9999,
    "handoff_to": "555000111",
    "enabled": True,          # <- cố tình bật; kho PHẢI bỏ qua
})
check("tạo đủ trường -> ok", bool(bid) and why == "")

b = chatbot_store.get_bot(bid)
check("bot mới LUÔN tắt dù người gọi gửi enabled=true", b.get("enabled") is False)
check("slug tự sinh không dấu", b.get("slug") == "bot-cham-soc-khach")
check("icon mặc định là tên icon Lucide", b.get("icon") == "headset")
check("agent lưu theo cặp (brain, slug)",
      b["agent"] == {"brain": "brain", "slug": "cskh"})
check("brain riêng của bot khác brain của Agent", b["brain"] == "shop-cskh")
check("@ trong username bị cắt", b.get("bot_username") == "ShopCSKHBot")
check("id nhóm ÂM được giữ (nhóm Telegram là số âm)", "-1001234567890" in b["groups"])
check("chuỗi không phải số bị loại khỏi danh sách nhóm", "khong-phai-so" not in b["groups"])
check("rate_limit bị kẹp về trần", b["rate_limit"] == chatbot_store.RATE_MAX)
check("reply_when mặc định là mention", b["reply_when"] == "mention")
# Mặc định phải là "agent": người dùng vừa CHỌN một Agent thì mong bot nói giống Agent đó. Ép
# cứng chế độ chỉ-tài-liệu như 0.20.0 làm một Agent coach viết rất kỹ vẫn trả lời "em chưa có
# thông tin" cho đúng câu thuộc chuyên môn của nó.
check("nguồn trả lời mặc định là chuyên môn Agent", b["nguon_tra_loi"] == "agent")


# ============================================================
# 2. Token không rò ra giao diện
# ============================================================
check("get_bot KHÔNG kèm token", "token" not in b and "token_enc" not in b)
check("get_bot có cờ token_set", b.get("token_set") is True)
check("list_bots cũng KHÔNG kèm token",
      all("token" not in x and "token_enc" not in x for x in chatbot_store.list_bots()))
check("mã nội bộ vẫn lấy được token thật",
      chatbot_store.get_token(bid) == "123456:AAA-token-that")
check("get_token với id lạ -> chuỗi rỗng", chatbot_store.get_token("bot_khong-co") == "")

_raw = chatbot_store.STORE_PATH.read_text(encoding="utf-8")
check("token trên đĩa đã mã hoá, không nằm dạng thô", "123456:AAA-token-that" not in _raw)


# ============================================================
# 3. Sửa: danh sách TRẮNG
# ============================================================
ok, _ = chatbot_store.update_bot(bid, {
    "name": "Bot CSKH",
    "rate_limit": 30,
    "reply_when": "always",
    "groups": ["-100999", "rác"],
    "id": "bot_gia-mao",          # <- không nằm trong danh sách trắng
    "created_at": 0,              # <- cũng không
    "token_enc": "gia-mao",       # <- càng không: ghi thẳng ô mã hoá
    "channel": "zalo",            # <- kênh không sửa từ giao diện
})
b = chatbot_store.get_bot(bid)
check("sửa được trường trong danh sách trắng", ok and b["name"] == "Bot CSKH")
check("rate_limit mới có hiệu lực", b["rate_limit"] == 30)
check("reply_when mới có hiệu lực", b["reply_when"] == "always")
check("danh sách nhóm được lọc lại khi sửa", b["groups"] == ["-100999"])
check("id KHÔNG sửa được qua bản vá", b["id"] == bid)
check("created_at KHÔNG sửa được qua bản vá", b["created_at"] != 0)
check("channel KHÔNG sửa được qua bản vá", b["channel"] == "telegram")
check("token_enc KHÔNG ghi đè thẳng được",
      chatbot_store.get_token(bid) == "123456:AAA-token-that")

chatbot_store.update_bot(bid, {"reply_when": "khi-nao-cung-duoc"})
check("reply_when giá trị lạ bị bỏ qua", chatbot_store.get_bot(bid)["reply_when"] == "always")

chatbot_store.update_bot(bid, {"nguon_tra_loi": "tai_lieu"})
check("đổi được sang chế độ chỉ tài liệu",
      chatbot_store.get_bot(bid)["nguon_tra_loi"] == "tai_lieu")
chatbot_store.update_bot(bid, {"nguon_tra_loi": "linh-tinh"})
check("nguồn trả lời giá trị lạ bị bỏ qua",
      chatbot_store.get_bot(bid)["nguon_tra_loi"] == "tai_lieu")
chatbot_store.update_bot(bid, {"nguon_tra_loi": "agent"})

chatbot_store.update_bot(bid, {"name": "   "})
check("tên rỗng không xoá mất tên cũ", chatbot_store.get_bot(bid)["name"] == "Bot CSKH")

ok, why = chatbot_store.update_bot("bot_khong-co", {"name": "x"})
check("sửa bot không tồn tại -> báo lỗi", ok is False and why == chatbot_store.LOI_KHONG_CO_BOT)

# Slug Agent hỏng phải TỪ CHỐI cả bản vá. Bản trước lặng lẽ bỏ qua riêng trường đó, nên form
# Sửa báo "đã lưu" trong khi bot vẫn trỏ về Agent cũ - chủ chỉ biết khi khách nhận được câu
# trả lời của một vai mà mình tưởng đã đổi.
ok, why = chatbot_store.update_bot(bid, {"name": "Tên mới", "agent_slug": "../trom"})
check("sửa với slug Agent nguy hiểm -> từ chối cả bản vá",
      ok is False and why == chatbot_store.LOI_SLUG_AGENT)
check("bản vá bị từ chối thì KHÔNG ghi trường nào",
      chatbot_store.get_bot(bid)["name"] == "Bot CSKH")

ok, _ = chatbot_store.update_bot(bid, {"agent_slug": "chăm-sóc-khách-hàng"})
check("sửa sang Agent tên tiếng Việt -> nhận",
      ok and chatbot_store.get_bot(bid)["agent"]["slug"] == "chăm-sóc-khách-hàng")
chatbot_store.update_bot(bid, {"agent_slug": "cskh"})


# ============================================================
# 4. Bật / tắt
# ============================================================
ok, _ = chatbot_store.set_enabled(bid, True)
check("bật bot có token -> ok", ok and chatbot_store.get_bot(bid)["enabled"] is True)
check("enabled_bots thấy bot đang bật",
      [x["id"] for x in chatbot_store.enabled_bots()] == [bid])

bid2, _ = chatbot_store.create_bot({"name": "Bot chưa token", "agent_slug": "cskh",
                                    "brain": "shop-2"})
ok, why = chatbot_store.set_enabled(bid2, True)
check("bật bot CHƯA có token -> từ chối kèm lý do", ok is False and "token" in why.lower())
check("bot đó vẫn tắt", chatbot_store.get_bot(bid2)["enabled"] is False)

chatbot_store.update_bot(bid2, {"enabled": True})
check("bản vá enabled=true cũng không bật nổi bot chưa có token",
      chatbot_store.get_bot(bid2)["enabled"] is False)


# ============================================================
# 5. Một token một bot
# ============================================================
check("token_owner tìm theo @username", (chatbot_store.token_owner("@shopcskhbot") or {}).get("id") == bid)
check("token_owner bỏ qua chính nó khi sửa",
      chatbot_store.token_owner("shopcskhbot", exclude_id=bid) is None)
check("token_owner với username rỗng -> None", chatbot_store.token_owner("") is None)


# ============================================================
# 6. Tra ngược Agent + xoá
# ============================================================
check("bots_using_agent tìm đúng bot", [x["id"] for x in chatbot_store.bots_using_agent("brain", "cskh")] == [bid, bid2])
check("bots_using_agent không nhận nhầm brain khác",
      chatbot_store.bots_using_agent("brain-khac", "cskh") == [])

ok, _ = chatbot_store.delete_bot(bid2)
check("xoá bot -> ok", ok)
check("xoá xong chỉ còn bot kia", [x["id"] for x in chatbot_store.list_bots()] == [bid])
ok, why = chatbot_store.delete_bot(bid2)
check("xoá lần hai -> báo không có", ok is False and why)


# ============================================================
# 7. Rào của bộ giám sát: có mở miệng không
# ============================================================
cfg = {"id": bid, "name": "Bot CSKH", "groups": ["-100999"], "reply_when": "mention",
       "rate_limit": 20, "handoff_to": "555000111"}

check("tin nhắn riêng -> luôn trả lời",
      chatbot_runtime._nen_tra_loi(cfg, {"chat_type": "private", "chat_id": "77"}) is True)
check("nhóm LẠ (chưa khai) -> im",
      chatbot_runtime._nen_tra_loi(cfg, {"chat_type": "group", "chat_id": "-100000"}) is False)
check("nhóm đã khai + mention nhưng không ai nhắc tên -> im",
      chatbot_runtime._nen_tra_loi(cfg, {"chat_type": "group", "chat_id": "-100999"}) is False)
check("nhóm đã khai + có nhắc tên -> trả lời",
      chatbot_runtime._nen_tra_loi(cfg, {"chat_type": "group", "chat_id": "-100999",
                                         "mentioned": True}) is True)
check("nhóm đã khai + reply vào bot -> trả lời",
      chatbot_runtime._nen_tra_loi(cfg, {"chat_type": "group", "chat_id": "-100999",
                                         "reply_to_bot": True}) is True)
check("reply_when=always trong nhóm đã khai -> trả lời",
      chatbot_runtime._nen_tra_loi({**cfg, "reply_when": "always"},
                                   {"chat_type": "group", "chat_id": "-100999"}) is True)
check("chưa khai nhóm nào -> im trong MỌI nhóm",
      chatbot_runtime._nen_tra_loi({**cfg, "groups": [], "reply_when": "always"},
                                   {"chat_type": "group", "chat_id": "-100999"}) is False)

# Lý do im phải PHÂN BIỆT ĐƯỢC. Hai kiểu im nhìn giống hệt nhau từ ngoài nhưng sửa khác hẳn:
# "nhóm chưa được bật" là việc của chủ và phải nổi lên trang Chatbot, còn "không ai gọi tên" là
# hành vi đúng và phải im tuyệt đối. Gộp làm một là hoặc spam chủ, hoặc giấu mất việc cần làm.
check("lý do im: nhóm chưa được bật",
      chatbot_runtime._ly_do_im(cfg, {"chat_type": "group", "chat_id": "-100000"}) == "nhom_chua_bat")
check("lý do im: nhóm đã bật nhưng không ai gọi tên",
      chatbot_runtime._ly_do_im(cfg, {"chat_type": "group", "chat_id": "-100999"}) == "khong_goi_ten")
check("có lý do trả lời thì lý do im là rỗng",
      chatbot_runtime._ly_do_im(cfg, {"chat_type": "private", "chat_id": "77"}) == "")

# CANARY - nhóm thường lên SIÊU NHÓM thì Telegram đổi id (thêm tiền tố -100), không báo ai cả.
# Chủ khai id lúc còn là nhóm thường, hôm sau bot im trong đúng nhóm nó vừa trả lời được hôm
# qua, và không có manh mối nào để lần. Hai dạng id phải khớp nhau.
check("id nhóm thường khớp với dạng siêu nhóm của chính nó",
      chatbot_runtime._khop_nhom(["-5313630519"], "-1005313630519") is True)
check("và ngược lại", chatbot_runtime._khop_nhom(["-1005313630519"], "-5313630519") is True)
check("hai nhóm KHÁC nhau vẫn không khớp",
      chatbot_runtime._khop_nhom(["-100999"], "-100000") is False)
check("chuẩn hoá không nuốt mất nhóm khác có đuôi trùng",
      chatbot_runtime._khop_nhom(["-999"], "-1999") is False)
check("nhóm đã khai dạng cũ, tin đến từ dạng mới -> vẫn trả lời",
      chatbot_runtime._nen_tra_loi({**cfg, "groups": ["-5313630519"]},
                                   {"chat_type": "group", "chat_id": "-1005313630519",
                                    "mentioned": True}) is True)

# ============================================================
# 7b. Nhóm chưa được bật phải NỔI LÊN, không được im lặng
# ============================================================
# Đây là lỗ hổng chủ repo báo (2026-08-06): thả bot vào nhóm, gọi tên nó, không có gì xảy ra.
# Không câu trả lời, không log, không dòng nào trên trang Chatbot - "hành vi đúng" và "bot
# hỏng" trông y hệt nhau. Rào giữ nguyên; cách từ chối thì phải nói được.
chatbot_runtime._NHOM_CHO.clear()
chatbot_runtime._DA_BAO_NHOM.clear()
chatbot_store.update_bot(bid, {"groups": [], "reply_when": "mention"})
_chan = chatbot_runtime._make_precheck_fn(bid)

_r1 = _chan("@bot ơi còn hàng không", {"chat_type": "group", "chat_id": "-4242",
                                       "chat_title": "Nhóm khách VIP", "mentioned": True})
check("nhóm chưa bật -> bot nói ĐÚNG MỘT câu chỉ đường", bool((_r1 or {}).get("reply")))
_r2 = _chan("alo", {"chat_type": "group", "chat_id": "-4242", "mentioned": True})
check("lần sau ở cùng nhóm thì im, không lải nhải", _r2 == {})

_cho = chatbot_runtime.nhom_cho(bid)
check("nhóm đó vào hàng đợi để chủ duyệt", len(_cho) == 1 and _cho[0]["chat_id"] == "-4242")
check("hàng đợi giữ tên nhóm cho chủ nhận ra", _cho[0]["ten"] == "Nhóm khách VIP")
check("và đếm số lần có người gọi", _cho[0]["lan"] == 2)

check("không ai gọi tên thì KHÔNG vào hàng đợi (im tuyệt đối)",
      _chan("hai người nói chuyện", {"chat_type": "group", "chat_id": "-777"}) == {}
      and len(chatbot_runtime.nhom_cho(bid)) == 1)

# Chế độ riêng tư của Telegram chặn tin nhắc tên Ở PHÍA TELEGRAM. Lúc đó đường DUY NHẤT còn
# chắc chắn là lệnh `/...`, nên chỉ nghe tin-gọi-bot là chưa đủ: gõ /id trong nhóm rồi quay lại
# dashboard mà vẫn không thấy nhóm nào để bấm cho phép thì đó là ngõ cụt hoàn toàn.
_sk = chatbot_runtime._make_event_fn(bid)
asyncio.run(_sk("thay_nhom", {"chat_id": "-8888", "chat_title": "Nhóm nội bộ"}))
_cho2 = [g for g in chatbot_runtime.nhom_cho(bid) if g["chat_id"] == "-8888"]
check("tin BẤT KỲ từ nhóm chưa bật cũng đưa nhóm đó lên hàng đợi", len(_cho2) == 1)
# Nhưng KHÔNG đếm là một lần gọi bot: đếm gộp thì mọi câu người ta nói với nhau đều cộng vào
# và con số "có người gọi bot N lần" mất sạch ý nghĩa.
check("chỉ THẤY nhóm thì không tính là một lần gọi bot", _cho2[0]["lan"] == 0)
asyncio.run(_sk("thay_nhom", {"chat_id": "-4242", "chat_title": "Nhóm khách VIP"}))
check("thấy lại nhóm đã có người gọi thì không thổi phồng bộ đếm",
      [g for g in chatbot_runtime.nhom_cho(bid) if g["chat_id"] == "-4242"][0]["lan"] == 2)
chatbot_runtime.bo_nhom_cho(bid, "-8888")

chatbot_store.update_bot(bid, {"groups": ["-4242"]})
chatbot_runtime.bo_nhom_cho(bid, "-4242")
check("cho phép rồi thì ra khỏi hàng đợi", chatbot_runtime.nhom_cho(bid) == [])
check("và lượt sau đi thẳng vào engine",
      _chan("còn hàng không", {"chat_type": "group", "chat_id": "-4242",
                               "mentioned": True}) is None)
chatbot_store.update_bot(bid, {"groups": []})


# ============================================================
# 8. Rào: giới hạn tần suất theo giờ, riêng từng người
# ============================================================
chatbot_runtime._HITS.clear()
qua = [chatbot_runtime._qua_han_muc("b1", "kh1", 3) for _ in range(5)]
check("trong hạn mức thì cho qua", qua[:3] == [False, False, False])
check("quá hạn mức thì chặn", qua[3:] == [True, True])
check("người KHÁC không bị vạ lây",
      chatbot_runtime._qua_han_muc("b1", "kh2", 3) is False)
check("bot KHÁC đếm riêng",
      chatbot_runtime._qua_han_muc("b2", "kh1", 3) is False)


# ============================================================
# 9. Rào: lệnh là danh sách TRẮNG
# ============================================================
cmd = chatbot_runtime._make_command_fn(cfg)


def chay(c, arg="", chat="77", meta=None):
    return (asyncio.run(cmd(c, arg, chat, meta)) or {}).get("reply", "")


check("/start chào khách", "Bot CSKH" in chay("/start"))
check("/help cũng chào", bool(chay("/help")))
check("/id trả về id cuộc trò chuyện", "77" in chay("/id"))
check("/id trong tin nhắn RIÊNG chỉ trả id, không giảng giải về nhóm",
      chay("/id", meta={"chat_type": "private", "chat_id": "77"}).count("\n") == 0)

# `/id` là chỗ DUY NHẤT chắc chắn nói được ra khi bot im trong nhóm: lệnh luôn về tới bot bất
# kể chế độ riêng tư của Telegram, còn tin nhắc tên thì chưa chắc. Ba nguyên nhân cho ra cùng
# một triệu chứng "riêng thì được, nhóm im re", nên nó phải nói được nhóm này đã bật chưa.
_id_nhom = chay("/id", chat="-4242", meta={"chat_type": "group", "chat_id": "-4242"})
check("/id trong nhóm chưa bật thì nói thẳng là chưa bật",
      "-4242" in _id_nhom and "chưa được bật" in _id_nhom)
check("/id chỉ đúng chỗ bấm cho phép", "trang Chatbot" in _id_nhom)
# Đọc nhóm từ KHO chứ không từ bản ghi chụp lúc dựng lệnh: chủ bấm "Cho phép" trên dashboard
# là ăn ngay từ câu tiếp theo, không phải tắt bật lại bot.
chatbot_store.update_bot(bid, {"groups": ["-100999"]})
_id_da_bat = chay("/id", chat="-100999", meta={"chat_type": "group", "chat_id": "-100999"})
check("/id trong nhóm ĐÃ bật thì nói đã bật", "đã được bật" in _id_da_bat)
chatbot_store.update_bot(bid, {"groups": []})
for xau in ("/brain", "/model", "/status", "/reset", "/mcp", "/task"):
    r = chay(xau)
    check(f"lệnh quản trị {xau} KHÔNG lọt sang bot khách",
          "brain" not in r.lower() and "model" not in r.lower() and "id cuộc" not in r.lower())
check("lệnh lạ trả lời chung chung, không khai còn tập lệnh khác",
      "không có lệnh" not in chay("/xyz").lower())


# ============================================================
# 10. Prompt của bot
# ============================================================
# Nội dung prompt do test_chatbot_cach_ly.py canh (Javis không được chèn luật của mình lên
# quy định người dùng viết trong Agent). Ở đây chỉ kiểm đúng phần thuộc về kho: bot TRỎ TỚI
# một Agent bằng cặp (brain, slug), và prompt dựng từ đúng cặp đó.
chatbot_runtime.wire(
    answer=None,
    brain_root=lambda b: "/tmp/khong-dung",
    read_agent=lambda brain, slug: ({"name": "Hoa CSKH", "role": "Trả lời khách về sản phẩm"},
                                    "Luôn hỏi khách đã mua chưa."),
)
p = chatbot_runtime.build_bot_prompt({"name": "Bot CSKH", "agent": {"brain": "brain", "slug": "cskh"},
                                      "handoff_to": "555000111"})
check("prompt lấy TÊN từ Agent", "Hoa CSKH" in p)
check("prompt lấy VAI TRÒ từ Agent", "Trả lời khách về sản phẩm" in p)
check("prompt lấy THÂN file Agent", "Luôn hỏi khách đã mua chưa." in p)
check("prompt KHÔNG mang system prompt điều phối của Javis",
      "javis_schedule" not in p and "Kanban" not in p)


def _no_agent(brain, slug):
    raise FileNotFoundError(slug)


chatbot_runtime.wire(answer=None, brain_root=lambda b: "/tmp/khong-dung", read_agent=_no_agent)
p3 = chatbot_runtime.build_bot_prompt({"name": "Bot mồ côi", "agent": {"brain": "brain", "slug": "mat-roi"}})
check("Agent biến mất thì prompt vẫn dựng được, không sập", bool(p3) and "Bot mồ côi" in p3)
check("Agent biến mất thì prompt nói rõ là chưa nạp được hướng dẫn",
      "chưa nạp được hướng dẫn" in p3)


# ============================================================
# 11. Trạng thái
# ============================================================
st = chatbot_runtime.status("bot_khong-chay")
check("bot chưa chạy -> state=off", st["state"] == "off" and st["running"] is False)

ok, why = chatbot_runtime.start_bot("bot_khong-co")
check("bật bot không tồn tại -> từ chối", ok is False and why)
ok, why = chatbot_runtime.start_bot(bid2)
check("bật bot đã xoá -> từ chối", ok is False and why)


# ============================================================
# 12. Lượt bot đi đường riêng, hạ bằng MÃ chứ không dặn trong prompt
# ============================================================
# Chi tiết của đường đó (không tool, chung cho tám bộ não) do test_chatbot_cach_ly.py canh.
_SRC = (SERVER / "main.py").read_text(encoding="utf-8")
check("lõi một lượt nhận tham số bot", "async def _tg_answer(text, meta=None, progress=None" in _SRC
      and "bot=None" in _SRC)
check("có bot thì rẽ sang đường riêng", "return await _bot_tra_loi(" in _SRC)

# Bot sống TRONG một brain: Agent nó dùng và tài liệu nó đọc là cùng một chỗ. Giao diện không
# hỏi brain nữa (trang thuộc về brain đang mở), nên server phải tự giữ hai trường bằng nhau -
# lệch được thì bot trỏ vào Agent nằm ngoài brain nó đọc, và không có gì báo.
check("trang Chatbot lọc bot theo brain", "async def chatbots_list(brain: str = \"\")" in _SRC)
check("bỏ trống brain thì trả tất cả (bộ giám sát cần thấy hết)",
      'if loc and str(b.get("brain") or "") != loc:' in _SRC)
check("tạo bot: hai trường brain tự bù cho nhau",
      'br = (brain or agent_brain or "").strip()' in _SRC)
check("sửa bot: hai trường brain luôn bằng nhau",
      'form["brain"] = form["agent_brain"] = br' in _SRC)
check("bot dùng prompt riêng chứ không phải build_system_prompt",
      "chatbot_runtime.build_bot_prompt(bot)" in _SRC)
check("có đường cho phép MỘT nhóm bằng một cú bấm",
      'async def chatbots_groups(' in _SRC and '"/chatbots/{bot_id}/groups"' in _SRC)
check("danh sách bot kèm hàng đợi nhóm chờ duyệt",
      'b["nhom_cho"] = chatbot_runtime.nhom_cho(b["id"])' in _SRC)
check("khai được nhóm ngay lúc TẠO bot, không chỉ lúc sửa",
      '"groups": groups, "reply_when": reply_when,' in _SRC)
check("xoá bot thì dọn luôn vết trong RAM", "chatbot_runtime.quen_bot(bot_id)" in _SRC)


# ============================================================
# 11. Tầng kênh: im lặng phải là im lặng THẬT
# ============================================================
# Trước bản này, bot từ chối một tin trong nhóm lạ vẫn đi hết đường: gửi tin "🤔 đang xử lý…",
# xoá nó, rồi gửi "(không có nội dung)" vào mặt người ngoài. Vừa lộ, vừa che mất lượt hỏng thật
# (câu trả lời rỗng vì engine gãy cũng ra đúng chuỗi đó).
_TG = (SERVER / "telegram_bot.py").read_text(encoding="utf-8")
# Điều phối lượt (chốt chặn, hàng đợi, /stop) nằm ở `bot_gateway` từ 0.26.5, dùng chung cho
# Telegram và Zalo. Phần riêng của Telegram vẫn soi ở _TG.
_GW = (SERVER / "bot_gateway.py").read_text(encoding="utf-8")
check("kênh có chốt chặn chạy TRƯỚC khi tốn một lượt", "self.precheck_fn = precheck_fn" in _TG)
check("chốt chặn đứng trước cả tin trạng thái", "if self.precheck_fn and not text.startswith" in _GW)
check("lệnh KHÔNG bị chốt chặn (còn /id để lấy id nhóm)",
      'not text.startswith("/")' in _GW)
check("im lặng có chủ ý khác câu trả lời rỗng",
      'im_lang = bool(reply.get("im_lang"))' in _TG and
      'if im_lang and not str(reply or "").strip() and not files:' in _TG)
check("bộ giám sát nối chốt chặn vào poller của bot",
      "precheck_fn=_make_precheck_fn(bot_id)" in
      (SERVER / "chatbot_runtime.py").read_text(encoding="utf-8"))
check("kênh nghe tin dịch vụ của nhóm (vào nhóm / bị đá / đổi id)",
      "async def _bao_su_kien" in _TG and '"migrate_to_chat_id"' in _TG)
check("đọc được chế độ riêng tư của Telegram từ getMe",
      'me.get("can_read_all_group_messages")' in _TG)

# CANARY - getMe hỏng thì bot KHÔNG biết @username của chính nó, `_co_nhac_ten` trả False cho
# MỌI tin, và bot điếc trong mọi nhóm trong khi tin nhắn riêng vẫn chạy hoàn hảo. Triệu chứng
# trùng khít với chế độ riêng tư của Telegram nên đứng ngoài không phân biệt được, và bản trước
# nuốt nó bằng đúng một dòng stderr rồi đặt trạng thái "polling" - thẻ xanh, không ai đoán ra.
check("getMe có thử lại chứ không bỏ cuộc sau một cú mạng hỏng",
      "async def _hoi_danh_tinh" in _TG and "lan=3" in _TG)
check("getMe hỏng thì GIỮ LẠI lý do cho trang Chatbot nói ra",
      "self.loi_danh_tinh" in _TG and "trong nhóm nó không nhận ra được ai đang gọi tên" in _TG)
check("lý do đó tách khỏi last_error (vòng lặp xoá last_error mỗi lượt poll)",
      'self.status = "polling"; self.last_error = ""' in _TG
      and "loi_danh_tinh" not in _TG.split('self.last_error = ""')[1].split("\n")[0])
check("mất danh tính thì hỏi lại định kỳ, không đợi người tắt bật tay",
      "if not self.bot_id and time.monotonic() - self._lan_hoi_danh_tinh > 60" in _TG)
_RT = (SERVER / "chatbot_runtime.py").read_text(encoding="utf-8")
check("trạng thái phơi lý do mất danh tính ra giao diện", '"loi_danh_tinh"' in _RT)
check("'đã hỏi được Telegram' đo bằng danh tính, không bằng trạng thái poll",
      '"da_hoi_telegram": bool(getattr(tb, "bot_id", 0))' in _RT)
check("lệnh nhận được meta để chẩn đoán đúng nhóm đang đứng",
      "res = await self.command_fn(cmd, arg, chat, meta)" in _GW
      and "async def _cmd(cmd, arg, chat, meta=None)" in _RT)

print()
if _fails:
    print(f"ĐỎ {len(_fails)} mục: " + ", ".join(_fails))
    sys.exit(1)
print("Tất cả xanh.")
