"""Bộ câu đo tai nghe: tiếng Việt thuần, tiếng Anh thuần, và câu Việt pha Anh kiểu ra lệnh cho Javis.

Mỗi câu là các đoạn (ngôn ngữ, chữ): "v" tiếng Việt, "e" tiếng Anh. `terms` là thuật ngữ phải
nghe ĐÚNG thì lệnh mới chạy được (tên công cụ, tên người, số liệu quảng cáo).

Câu pha sinh hai bản (synth.py):
  a - cả câu đọc bằng giọng Việt: từ tiếng Anh mang âm Việt, gần cách người Việt nói nhất.
  b - đoạn nào đọc bằng giọng tiếng đó rồi ghép lại: tiếng Anh chuẩn bản xứ.
Câu thuần chỉ có bản a.

Đổi bộ câu là đổi mốc so sánh: thêm câu mới thì giữ câu cũ, để số đo các lần trước còn so được.
"""
CORPUS = [
    dict(id="v1", kind="pure_vi", seg=[("v", "Hôm nay thời tiết ở Hà Nội rất đẹp")], terms=[]),
    dict(id="v2", kind="pure_vi", seg=[("v", "Nhắc anh đi họp lúc ba giờ chiều")], terms=[]),
    dict(id="v3", kind="pure_vi", seg=[("v", "Doanh thu tuần này tăng so với tuần trước")], terms=[]),
    dict(id="v4", kind="pure_vi", seg=[("v", "Cho anh xem danh sách đơn hàng mới nhất")], terms=[]),
    dict(id="e1", kind="pure_en", seg=[("e", "Open the dashboard and show me the weekly sales report")], terms=[]),
    dict(id="e2", kind="pure_en", seg=[("e", "Send an email to the customer about the new order")], terms=[]),
    dict(id="m1", kind="mixed", seg=[("v", "Mở"), ("e", "dashboard Facebook ads"), ("v", "rồi báo cáo"), ("e", "ROAS"),
                                     ("v", "tuần này")], terms=["dashboard", "Facebook ads", "ROAS"]),
    dict(id="m2", kind="mixed", seg=[("v", "Gửi"), ("e", "email"), ("v", "cho khách hàng về đơn hàng mới")], terms=["email"]),
    dict(id="m3", kind="mixed", seg=[("e", "Javis"), ("v", "ơi"), ("e", "check inventory"), ("v", "của sản phẩm bulong")],
         terms=["Javis", "check", "inventory"]),
    dict(id="m4", kind="mixed", seg=[("v", "Tạo một"), ("e", "workflow"), ("v", "mới tên là"), ("e", "daily report")],
         terms=["workflow", "daily report"]),
    dict(id="m5", kind="mixed", seg=[("v", "Kết nối"), ("e", "MCP"), ("v", "của"), ("e", "Pancake POS")],
         terms=["MCP", "Pancake POS"]),
    dict(id="m6", kind="mixed", seg=[("v", "Đặt"), ("e", "reminder"), ("v", "họp"), ("e", "team"), ("v", "lúc ba giờ chiều")],
         terms=["reminder", "team"]),
    dict(id="m7", kind="mixed", seg=[("v", "Mở"), ("e", "Telegram")], terms=["Telegram"]),
    dict(id="m8", kind="mixed", seg=[("e", "Sync"), ("v", "dữ liệu sang"), ("e", "Google Sheets")], terms=["Sync", "Google Sheets"]),
    dict(id="m9", kind="mixed", seg=[("v", "Nhắn tin cho"), ("e", "John Smith"), ("v", "về"), ("e", "deadline"),
                                     ("v", "của dự án")], terms=["John Smith", "deadline"]),
    dict(id="m10", kind="mixed", seg=[("v", "Tăng"), ("e", "budget"), ("v", "của"), ("e", "campaign remarketing"),
                                      ("v", "lên hai triệu")], terms=["budget", "campaign", "remarketing"]),
]


def clips():
    """Danh sách clip: uid, kind, variant, text (câu đúng), terms, seg."""
    out = []
    for u in CORPUS:
        text = " ".join(t for _, t in u["seg"])
        for var in (("a", "b") if u["kind"] == "mixed" else ("a",)):
            out.append(dict(uid=f'{u["id"]}{var}', kind=u["kind"], variant=var, text=text,
                            terms=u["terms"], seg=u["seg"]))
    return out
