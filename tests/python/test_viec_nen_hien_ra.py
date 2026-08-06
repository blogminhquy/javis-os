"""Regression: việc nền phải HIỆN RA, và lời hứa suông phải bị đính chính.

Lỗi thật chủ repo báo 2026-08-06 (kèm ảnh chụp khung chat):

    "anh đang bật chức năng siêu tiết kiệm, nhiều khi nó trả lời như này nhưng không hề báo
     lại chút nào cả. Và có agent chạy ngầm thì anh cũng không biết là nó đang chạy thật hay
     không? Không giống như claude nếu đang chạy ngầm thì vẫn có báo ở đầu hội thoại. Đây là
     không thấy gì luôn và không chạy luôn."

Câu Javis nói trong ảnh: "Em đang dò code để xem trong nhóm bot có lọc tin nhắn (theo mention,
reply, hay AI tự quyết định) trước khi trả lời hay không, có kết quả em báo ngay." Rồi hết.

Ba gốc rễ, test này canh cả ba:

  1. **Hứa suông không ai bắt.** Luật cũ chỉ cấm đúng một câu mẫu ("em sẽ đợi các agent chạy
     xong rồi tổng hợp"), nên kiểu "đang làm, xong báo" lọt thẳng. Nay server tự dò lời hứa
     rồi đối chiếu với việc nền THẬT, không có thì tự đính chính ngay dưới câu trả lời.

  2. **Không thấy gì đang chạy.** Khung chat không hiện một chữ nào về việc nền. Nay có
     endpoint `/background` + dải trạng thái trong khung chat.

  3. **Không chạy luôn.** Điều phối Kanban mặc định `off`, nên việc giao từ chat nằm im vô
     thời hạn. Plugin `javis-task` có sẵn một dòng cảnh báo cho chuyện này, nhưng cổng viết
     sai (`not view.get("orchestration")` - mà giá trị là chuỗi "off", luôn truthy) nên nó
     CHƯA TỪNG in ra lần nào, và `op=add` thì còn hứa thẳng "Việc chạy nền. Kết quả tự về".

Chạy:
    python tests/python/test_viec_nen_hien_ra.py
"""
import os
import re
import sys
import tempfile

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-bgstatus-test-"))

from _paths import ROOT, SERVER, DASHBOARD, SYSTEM  # noqa: E402,F401

import background_status as bg  # noqa: E402
import channel_context  # noqa: E402

fails = []


def check(name: str, condition: bool) -> None:
    print(("PASS: " if condition else "FAIL: ") + name)
    if not condition:
        fails.append(name)


# ─────────── 1. Bắt lời hứa "xong em báo" ───────────
# Câu NGUYÊN VĂN trong ảnh chủ repo gửi - đây là ca phải bắt được, không được trượt.
CAU_THAT = ("Em đang dò code để xem trong nhóm bot có lọc tin nhắn (theo mention, reply, hay "
            "AI tự quyết định) trước khi trả lời hay không, có kết quả em báo ngay.")
check("bắt được ĐÚNG câu chủ repo chụp lại", bool(bg.detect_promise(CAU_THAT)))

for cau in [
    "Ok anh, em sẽ báo lại ngay khi xong nhé.",
    "Anh chờ em một chút, em kiểm tra rồi nói anh.",
    "Em đang kiểm tra lại cấu hình, xong em báo anh.",
    "Em sẽ đợi các agent chạy nền hoàn tất rồi tổng hợp cho anh.",
    "Để em chạy thử rồi cập nhật cho anh sau.",
    "I'll get back to you once the check finishes.",
]:
    check(f"bắt lời hứa: {cau[:44]}…", bool(bg.detect_promise(cau)))

# Không được bắt nhầm. Cảnh báo thừa dán dưới một câu trả lời đúng làm người dùng mất tin vào
# chính dòng cảnh báo đó - hỏng nặng hơn là thiếu.
for cau in [
    "Doanh thu tuần này 42 triệu, tăng 12% so với tuần trước. Anh nên tăng ngân sách quảng cáo.",
    "Em đã báo kết quả ở trên rồi ạ.",
    "Em đã giao 3 việc nền, kết quả sẽ tự hiện ở đây khi xong.",
    "Anh báo em biết khi nào cần chạy lại nhé.",
    "Nhóm bot lọc tin nhắn theo mention, code nằm ở telegram_bot.py dòng 240.",
    "Em không kiểm tra được vì chưa đấu MCP Gmail.",
]:
    check(f"KHÔNG bắt nhầm: {cau[:44]}…", not bg.detect_promise(cau))

check("bỏ qua lời hứa nằm trong khối mã (model dán lại code, không phải nó hứa)",
      not bg.detect_promise("Đoạn cũ ghi vậy:\n```\nreply = 'xong em báo anh'\n```\nEm đã sửa rồi."))

check("dấu tiếng Việt không làm trượt mẫu (đ/Đ phải map tay, NFKD không phân rã)",
      bool(bg.detect_promise("em đang dò lại rồi báo anh")))


# ─────────── 2. Đối chiếu với việc nền THẬT ───────────
TASK_CHAY = {"id": "t_1", "title": "So sánh skill", "status": "running", "chat_id": "web:s1"}
TASK_CHO = {"id": "t_2", "title": "Rà log", "status": "triage", "chat_id": "web:s1"}
LOOP = {"slug": "canh-doanh-thu", "name": "Canh doanh thu", "enabled": True, "owner_chat": "web:s1"}
REM = {"id": "r_1", "label": "Uống thuốc", "chat_id": "web:s1", "due_at": 100.0}

v_rong = bg.active_view([], [], [], chat_id="web:s1", orchestration="off")
check("không có việc nào → count 0", v_rong["count"] == 0)
check("không có việc nào → đúng là hứa suông", not bg.has_pending_work(v_rong))

v_chay = bg.active_view([TASK_CHAY], [], [], chat_id="web:s1", orchestration="auto")
check("có việc đang chạy → count 1", v_chay["count"] == 1 and v_chay["running_count"] == 1)
check("việc đang chạy → KHÔNG cảnh báo hứa suông", bg.has_pending_work(v_chay))
check("việc khớp chat_id được đánh dấu mine", v_chay["items"][0]["mine"] is True)

v_khac = bg.active_view([{**TASK_CHAY, "chat_id": "web:s9"}], [], [],
                        chat_id="web:s1", orchestration="auto")
check("việc của hội thoại KHÁC vẫn hiện nhưng không mine",
      v_khac["count"] == 1 and v_khac["mine_count"] == 0)

# Ca đắt nhất của cả bản này: việc đã giao, nằm trong hàng đợi, mà điều phối tắt.
v_ket = bg.active_view([TASK_CHO], [], [], chat_id="web:s1", orchestration="off")
check("điều phối TẮT: việc xếp hàng bị đếm là ĐỨNG IM", v_ket["stalled_count"] == 1)
check("điều phối TẮT: việc xếp hàng KHÔNG cứu được lời hứa (nó sẽ không chạy)",
      not bg.has_pending_work(v_ket))
v_auto = bg.active_view([TASK_CHO], [], [], chat_id="web:s1", orchestration="auto")
check("điều phối AUTO: việc xếp hàng thì có chạy thật", bg.has_pending_work(v_auto))
check("điều phối AUTO: không còn đếm là đứng im", v_auto["stalled_count"] == 0)

# Loop và nhắc hẹn chạy bằng scheduler riêng, không phụ thuộc điều phối Kanban.
check("loop đang bật thì tính là có việc nền dù điều phối tắt",
      bg.has_pending_work(bg.active_view([], [LOOP], [], chat_id="web:s1", orchestration="off")))
check("nhắc hẹn chờ tới giờ cũng tính",
      bg.has_pending_work(bg.active_view([], [], [REM], chat_id="web:s1", orchestration="off")))
check("loop đã TẮT thì không tính",
      not bg.has_pending_work(bg.active_view(
          [], [{**LOOP, "enabled": False}], [], chat_id="web:s1", orchestration="off")))

v_tron = bg.active_view([TASK_CHO, TASK_CHAY], [LOOP], [REM],
                        chat_id="web:s1", orchestration="auto")
check("việc của hội thoại này xếp trước, đang chạy trước việc chờ",
      v_tron["items"][0]["status"] == "running")

note = bg.promise_note("off")
check("dòng đính chính nói rõ KHÔNG có việc nền nào", "KHÔNG tạo việc nền nào" in note)
check("dòng đính chính nêu luôn chuyện điều phối tắt", "trang Việc" in note)
check("dòng đính chính không dùng em dash (luật CLAUDE.md)", "\u2014" not in note)
check("promise_note khi điều phối auto thì không đổ lỗi cho điều phối",
      "trang Việc" not in bg.promise_note("auto"))


# ─────────── 3. Server: endpoint + móc nối ───────────
MAIN = (SERVER / "main.py").read_text(encoding="utf-8")
check("main.py có endpoint /background", '@app.get("/background")' in MAIN)
check("/background nhận chat_id để đánh dấu việc của đúng khung chat",
      re.search(r"async def background_active\(.*?chat_id: str = Query", MAIN, re.S) is not None)
check("dashboard: lượt xong thì kiểm lời hứa rồi đẩy đính chính vào đúng phiên",
      "_canh_bao_hua_suong(" in MAIN and "await push_to_chat(conv_sid, _canh_bao)" in MAIN)
check("telegram: đính chính nối vào cuối tin nhắn (tin chưa gửi đi)",
      'out["text"] = (out.get("text") or "") + "\\n\\n" + _canh_bao' in MAIN)
check("bot chuyên trách KHÔNG bị dán đính chính nội bộ",
      "if not bot and isinstance(out, dict):" in MAIN)
check("đọc kho việc lỗi thì im lặng chứ không cảnh báo bừa",
      re.search(r"except Exception:\s*\n\s*return \"\"\s*# không đọc được kho việc", MAIN))


# ─────────── 4. Prompt: cấm hẹn suông ở MỌI kênh ───────────
BLOCK_WEB = channel_context.build_channel_block("dashboard", {"session_id": "s1"})
BLOCK_TG = channel_context.build_channel_block("telegram", {"chat_id": "42"})
BLOCK_CLI = channel_context.build_channel_block("cli", {})
for ten, blk in (("web", BLOCK_WEB), ("telegram", BLOCK_TG), ("cli", BLOCK_CLI)):
    check(f"{ten}: prompt cấm hứa 'có kết quả em báo ngay'",
          "có kết quả em báo ngay" in blk and "KHÔNG HỨA THỨ MÌNH KHÔNG LÀM ĐƯỢC" in blk)
    check(f"{ten}: prompt bắt thuật đúng kết quả tool khi điều phối tắt",
          "điều phối đang TẮT" in blk)
check("web: prompt nói rõ server tự kiểm lời hứa",
      "server tự dán một dòng đính chính" in BLOCK_WEB)


# ─────────── 5. Plugin javis-task: cổng điều phối phải ĐÚNG ───────────
PLUGIN = (SYSTEM / "plugins" / "javis-task" / "plugin.py").read_text(encoding="utf-8")
check("bỏ cổng sai `not view.get(\"orchestration\")` (chuỗi 'off' luôn truthy)",
      'not view.get("orchestration")' not in PLUGIN)
check("cổng mới so đúng với 'auto'", '== "auto"' in PLUGIN)
check("op=add chỉ hứa 'kết quả tự về' khi điều phối THẬT SỰ chạy",
      re.search(r"if _dieu_phoi_chay\(muc\):\s*\n\s*ra\.append\(\"Việc chạy nền", PLUGIN)
      is not None)
check("op=add cảnh báo khi điều phối tắt", "_CANH_BAO_DIEU_PHOI.format(muc=muc)" in PLUGIN)
check("cảnh báo dặn model đừng hứa việc đang chạy",
      "đừng hứa là việc đang chạy" in PLUGIN)


# ─────────── 6. Dashboard: dải trạng thái ───────────
HTML = (DASHBOARD / "index.html").read_text(encoding="utf-8")
STRIP = (DASHBOARD / "background-strip.js").read_text(encoding="utf-8")
APPJS = (DASHBOARD / "app.js").read_text(encoding="utf-8")
CONSOLE = (DASHBOARD / "console.js").read_text(encoding="utf-8")
CSS = (DASHBOARD / "style.css").read_text(encoding="utf-8")

check("index.html có ô dải việc nền, mặc định ẩn",
      'id="bgStrip"' in HTML and re.search(r'id="bgStrip"[^>]*hidden', HTML) is not None)
check("index.html nạp background-strip.js SAU app.js",
      HTML.index("background-strip.js") > HTML.index("app.js?v="))
check("dải đi theo sang trang Trò chuyện (nằm trong CHAT_NODE_IDS)",
      '"chatArea", "bgStrip"' in CONSOLE)
check("dải hỏi /background kèm brain + chat_id", '"/background?brain="' in STRIP
      and 'chat_id=' in STRIP)
check("dải dùng tiền tố web: đúng như _notify_owner mong đợi", '"web:" + s' in STRIP)
check("dải ẩn hẳn khi không có việc nào", "hide();" in STRIP and "e.hidden = true" in STRIP)
check("dải nói thẳng khi việc KHÔNG tự chạy",
      "KHÔNG tự chạy" in STRIP and "AI tự vận hành" in STRIP)
check("dải không vẽ lại DOM khi trạng thái không đổi (đỡ nháy)",
      "lastKey" in STRIP and "if (key === lastKey) return;" in STRIP)
check("app.js làm tươi dải khi lượt xong và khi việc nền báo về",
      APPJS.count("window.JavisBackground.refresh()") >= 2)
check("app.js dọn dải khi đổi/mở hội thoại khác",
      APPJS.count("window.JavisBackground.reset()") >= 2)
check("CSS có ba tông run/stall/idle", ".bg-run" in CSS and ".bg-stall" in CSS)


if fails:
    raise SystemExit(f"\nFAIL - test_viec_nen_hien_ra: {len(fails)} lỗi")
print("\nOK - test_viec_nen_hien_ra: tất cả pass")
