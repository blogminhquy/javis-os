"""Việc nền không tự mọc lung tung, nhất là ở giọng nói (0.64.48).

    python tests/python/test_viec_nen_khong_moc_lung_tung.py

Chủ repo báo 2026-09-24: ở giao diện giọng nói "cứ nói đến chữ việc là nó đi tạo việc ngầm",
cơ chế tạo việc khó hiểu và hay làm sai. Audit ra bốn chỗ, test này khoá cả bốn:

1. Bộ nhận lệnh "dừng việc nền" bắt nhầm câu hỏi thường ("Thôi được rồi, quảng cáo đang chạy
   thế nào?", "tắt nhạc nền đi"): câu bị nuốt, Javis đáp "không có việc nền nào".
2. Luật của bộ não giọng liệt kê "giao việc" như một thứ phải đẩy đi, không nói rõ nhắc tới
   chữ "việc" KHÔNG phải lời nhờ, và không bảo hỏi lại khi không chắc.
3. "Đừng giao lại việc trùng" chỉ là lời dặn model; máy chủ không chặn trùng, không chặn dồn.
4. Kết quả việc nền về khung chat không mang trạng thái để vẽ thẻ, và dòng trống bị xoá sạch
   thành bức tường chữ.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import re
import sys

import voice_brain as vb  # noqa: E402
import channel_context  # noqa: E402

fails = []


def check(ten, dk, them=""):
    print(("ok   " if dk else "FAIL ") + ten + ("" if dk or not them else f"  [{them}]"))
    if not dk:
        fails.append(ten)


# ---- 1. Lệnh dừng: không nuốt câu thường ----
NUOT_NHAM = [
    "Thôi được rồi, quảng cáo đang chạy thế nào?",
    "Bỏ qua chuyện đó, nền tảng nào bán tốt nhất?",
    "tắt nhạc nền đi",
    "bỏ cái job tuyển dụng đó đi, viết bài khác",
    "thôi, việc ngầm đang chạy tới đâu rồi?",
    "Stop, nền tảng Shopee thế nào",
    "dừng lại, chiến dịch đang chạy có ổn không",
]
for c in NUOT_NHAM:
    check("KHÔNG nuốt câu thường: " + c, vb.la_lenh_dung_viec(c) is False)
VAN_LA_LENH = [
    "tạm dừng cái việc tìm kiếm ngầm đi nhé", "tắt việc tìm kiếm đang chạy", "dừng việc nền",
    "huỷ tác vụ đang chạy", "thôi bỏ việc ngầm đi", "ngừng chạy nền", "stop the background task",
    "Thôi, dừng việc ngầm đi.",
]
for c in VAN_LA_LENH:
    check("vẫn nhận lệnh dừng thật: " + c, vb.la_lenh_dung_viec(c) is True)

# ---- 2. Luật của bộ não giọng ----
P = vb.SYSTEM_PROMPT
check("luật: chỉ giao khi thật sự là lời nhờ", "CHỈ GIAO khi câu đó thật sự là lời nhờ" in P)
check("luật: nhắc chữ 'việc' không phải lời nhờ", "Nhắc tới chữ 'việc'" in P and "KHÔNG" in P)
check("luật: không chắc thì hỏi lại", "HỎI LẠI một" in P)
check("luật: mỗi lời nhờ chỉ giao MỘT lần", "MỘT lần: câu nói tiếp" in P)
check("luật cũ 'giao việc' không còn đứng như một loại dữ liệu cần đẩy đi",
      "ký ức dài hạn, giao việc, nhắc hẹn" not in P)
check("khuôn cũ các test khác dựa vào vẫn còn",
      "MỘT câu xác nhận" in P and "chạy NỀN" in P and "tự đứng được" in P and "KHÔNG giao việc mới" in P)

# ---- 3. Chốt ở máy chủ: không trùng, không dồn ----
vb._PENDING.clear()
vb.note_task_start("s1", "Tổng hợp doanh thu hôm nay từ POS")
check("việc gần giống việc đang chạy thì là TRÙNG",
      vb.viec_trung("s1", "tổng hợp doanh thu hôm nay từ POS.") == "Tổng hợp doanh thu hôm nay từ POS")
check("việc khác hẳn thì không trùng", vb.viec_trung("s1", "Đọc email mới nhất") is None)
check("phiên khác không bị tính trùng", vb.viec_trung("s2", "Tổng hợp doanh thu hôm nay từ POS") is None)
check("chưa đủ số việc thì chưa dồn", vb.day_viec_nen("s1") is False)
for i in range(vb.VIEC_NEN_TOI_DA - 1):
    vb.note_task_start("s1", f"việc {i}")
check("đủ số việc tối đa thì chặn nhận thêm", vb.day_viec_nen("s1") is True)
vb._PENDING.clear()

MAIN = (SERVER / "main.py").read_text(encoding="utf-8")
voice = MAIN[MAIN.index("async def run_voice_turn("):MAIN.index("async def _voice_bg_task(")]
i_chot = voice.find("voice_brain.viec_trung(conv_sid, ask)")
i_giao = voice.find("_nho_viec_nen_giong(conv_sid, asyncio.create_task(_voice_bg_task(")
check("main: kiểm trùng/dồn TRƯỚC khi giao việc nền", 0 < i_chot < i_giao, f"{i_chot} {i_giao}")
check("main: dồn việc cũng chặn", "voice_brain.day_viec_nen(conv_sid)" in voice)
check("main: lịch sử gửi model giọng đã bóc khối ẩn",
      "strip_control_blocks(m.get(\"content\") or \"\")" in voice)

# ---- 4. Kết quả mang trạng thái để vẽ thẻ ----
m = re.search(r"def khoi_viec\(viec\) -> str:[\s\S]*?\n\n\n", MAIN)
check("nhấc được khoi_viec", m is not None)
ns = {"json": __import__("json")}
exec(m.group(0) if m else "", ns)
k = ns["khoi_viec"]({"kind": "task", "status": "done", "title": "Lấy giá -->x", "id": "t1"})
check("khối đúng khuôn JAVIS_VIEC", k.startswith("<!-- JAVIS_VIEC: {") and k.endswith(" -->"), k)
check("tên việc chứa '-->' không làm vỡ khối", k.count("-->") == 1, k)
check("strip_control_blocks bóc khối cho Telegram/Zalo/hòm thư",
      channel_context.strip_control_blocks(k + "\nKết quả") == "Kết quả")
check("viec rỗng thì không có khối", ns["khoi_viec"](None) == "" and ns["khoi_viec"]({}) == "")
check("push_to_chat gắn khối SAU khi bóc (không tự bóc mất)",
      re.search(r"clean = channel_context\.strip_control_blocks\(text or \"\"\)\.strip\(\)[\s\S]{0,400}"
                r"_k = khoi_viec\(viec\)", MAIN) is not None)
check("kênh web nhận bản riêng cho thẻ", "push_to_chat(sid, (web or text) if viec else text, viec=viec)" in MAIN)
bg = MAIN[MAIN.index("async def _voice_bg_task("):MAIN.index("async def _start_resumed_turn(")]
check("việc nền giọng: kết quả mang thẻ", "push_to_chat(conv_sid, out or \"(việc nền xong nhưng không có nội dung)\", viec=viec)" in bg)
check("việc nền giọng: lỗi không còn in tên lớp ngoại lệ Python ra khung chat",
      "Việc nền lỗi: {type(e).__name__}" not in bg)
check("việc nền giọng: bị dừng cũng là thẻ", 'viec=dict(viec, status="cancelled")' in bg)
check("giao việc bằng giọng: lưu dòng giao để mở lại còn thấy",
      '"status": "giao"' in voice)

# Kanban: giữ dòng trống, kèm thẻ + bản web
sys.path.insert(0, str(SERVER))
import tasks as tasks_mod  # noqa: E402

gui = []


async def _bat(chat_id, text, **kw):
    gui.append((text, kw))


class _D:
    report = staticmethod(_bat)


class _F:
    deps = _D()


ket = "Đoạn một.\n\n- ý a\n- ý b\n\n\n\n## Tiêu đề\nĐoạn hai."
asyncio.run(tasks_mod.TasksFeature._report(_F(), {"title": "Tổng hợp", "status": "done", "result": ket,
                                                "chat_id": "web:abc", "id": "t9"}))
text, kw = gui[0]
check("kết quả giữ dòng trống giữa các đoạn", "Đoạn một.\n\n- ý a" in text, repr(text))
check("chuỗi dòng trống dài gộp về một", "\n\n\n" not in text)
check("kèm thông tin thẻ việc", kw.get("viec", {}).get("status") == "done" and kw["viec"].get("id") == "t9")
check("bản web bỏ câu đầu emoji và câu 'xem ở trang Việc'",
      "Việc 'Tổng hợp'" not in kw.get("web", "") and "trang Việc" not in kw.get("web", "")
      and kw.get("web", "").startswith("Đoạn một."), kw.get("web"))
check("bản đầy đủ (hòm thư) vẫn giữ tiêu đề", "Tổng hợp" in text)

# Luồng Cộng sự: có cổng "chỉ khi chủ bảo"
check("Cộng sự: việc nền chỉ khi chủ bảo rõ", "Việc nền (`javis_task`) CHỈ khi chủ bảo" in MAIN)

print(f"\n{len(fails)} FAIL" if fails else "\nTất cả xanh")
sys.exit(1 if fails else 0)
