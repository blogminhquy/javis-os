"""Javis không được TỰ đẻ việc nền từ kế hoạch của chính mình.

    python tests/run.py khong_tu_de_viec

Chủ repo báo 01/09/2026, kèm ảnh chuông thông báo: đang bàn kế hoạch trong khung chat thì
Javis tự giao một loạt việc Kanban ("Áp dụng kế hoạch ramp ... vào Funnel Tripwire",
"Cập nhật timeline dự án ..."), rồi mỗi việc xong hoặc kẹt lại bắn một thông báo về chuông
và về đúng khung chat đang nói chuyện. Việc thì không ai yêu cầu, mà tiếng ồn thì thật.

Vì sao model làm vậy: prompt kênh dạy nó chỉ có HAI lối đúng khi không làm xong trong lượt
("làm luôn" hoặc "giao việc nền"), cộng bộ dò lời hứa dán đính chính khi hứa mà không tạo
việc. Hai thứ đó đúng cho một YÊU CẦU CỦA NGƯỜI DÙNG, nhưng chúng không hề nói rằng một kế
hoạch do chính Javis vừa nghĩ ra thì KHÔNG phải là yêu cầu. Thiếu vế đó, đường an toàn nhất
với model là cứ giao việc cho chắc.

Test canh cái vế vừa thêm, ở cả BA nơi model thật sự đọc:
  1. Khối prompt kênh (`channel_context`) - mọi lượt chat đều được chèn.
  2. Mô tả tool `javis_task` - thứ engine API đọc ngay lúc quyết định gọi hay không.
  3. `CLAUDE.md` - system prompt gốc.
Thiếu một trong ba thì luật hở đúng ở engine đi qua đường đó.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import pathlib
import sys

import channel_context  # noqa: E402

_loi = []


def check(ten, dieu_kien, chi_tiet=""):
    print(f"       {'ok  ' if dieu_kien else 'FAIL'} {ten}" + (f"  [{chi_tiet}]" if not dieu_kien and chi_tiet else ""))
    if not dieu_kien:
        _loi.append(ten)


# ============================================================
# 1. Khối prompt kênh: chèn vào MỌI lượt chat, mọi engine
# ============================================================
khoi = channel_context.build_channel_block("dashboard", {"session_id": "s-test"}, port=8765)
check("khối kênh dựng được", bool(khoi), repr(khoi)[:80])
check("có cổng 'chỉ giao việc khi người dùng bảo làm'",
      "CHỈ GIAO VIỆC NỀN KHI NGƯỜI DÙNG BẢO LÀM" in khoi)
check("nói rõ kế hoạch của chính Javis chưa được user gật thì vẫn là đề xuất",
      "vẫn là đề xuất" in khoi)
check("nêu đúng mấy cái tên việc tự đẻ hay gặp",
      "áp dụng kế hoạch" in khoi and "cập nhật lại timeline" in khoi)
check("nói thẳng một lượt bàn bạc bình thường tạo KHÔNG việc nào",
      "KHÔNG việc nào" in khoi)
check("giải thích HẬU QUẢ (mỗi việc bắn thông báo về chuông và khung chat)",
      "chuông" in khoi and "thông báo" in khoi)
check("không chắc thì HỎI trước khi tạo", "HỎI MỘT CÂU" in khoi)

# Vế cũ phải còn nguyên: bỏ nó đi là quay lại lỗi hứa suông (0.9.x), tệ hơn lỗi đang sửa.
check("VẪN cấm hứa suông (luật cũ không bị cuốn theo)",
      "KHÔNG HỨA THỨ MÌNH KHÔNG LÀM ĐƯỢC" in khoi)
check("VẪN còn lối giao việc nền cho yêu cầu thật của user",
      "javis_task" in khoi)

# ============================================================
# 2. Mô tả tool - đường mà engine API đọc lúc quyết định
# ============================================================
mo_ta = {}


class _Ctx:
    vault_root = ""

    @staticmethod
    def register_tool(ten, desc, fn, schema=None, **kw):
        mo_ta[ten] = desc


sys.path.insert(0, str(ROOT / "system" / "plugins" / "javis-task"))
import plugin as javis_task_plugin  # noqa: E402

try:
    javis_task_plugin.register(_Ctx())
except TypeError:
    # Chữ ký register_tool đổi: đọc thẳng file nguồn để test không mù theo.
    mo_ta["javis_task"] = (ROOT / "system" / "plugins" / "javis-task" / "plugin.py").read_text(encoding="utf-8")

desc = mo_ta.get("javis_task", "")
check("tool javis_task có mô tả", bool(desc))
check("mô tả tool nêu cổng 'chỉ khi NGƯỜI DÙNG bảo làm'",
      "CHỈ op=add khi NGƯỜI DÙNG bảo làm" in desc)
check("mô tả tool cấm giao việc cho 'bước tiếp theo' tự nghĩ ra",
      "bước tiếp theo" in desc and "chưa" in desc)
check("mô tả tool vẫn dạy kèm chat_id (đường kết quả về đúng người)",
      "chat_id" in desc)

# ============================================================
# 3. CLAUDE.md - system prompt gốc
# ============================================================
claude_md = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")
# Trần 33.600 ký tự của `test_prompt_budget` chỉ còn vài chục ký tự dư, nên luật ở đây phải
# NGẮN: CLAUDE.md giữ điều luật, còn ví dụ và lý do nằm ở khối kênh (mục 1) vốn không bị trần này.
check("CLAUDE.md: việc nền chỉ cho việc USER yêu cầu",
      "a ONE-OFF job THE USER ASKED FOR" in claude_md)
check("CLAUDE.md: kế hoạch do Javis đề xuất KHÔNG phải mệnh lệnh",
      "is not an order" in claude_md and "never queue it" in claude_md)
check("CLAUDE.md nói rõ hội thoại lập kế hoạch tạo ZERO việc",
      "ZERO tasks" in claude_md)
check("CLAUDE.md vẫn giữ bậc thang cũ (trả lời thẳng là đủ cho 80%)",
      "Answer directly" in claude_md)

print()
if _loi:
    print(f"ĐỎ {len(_loi)} mục: " + "; ".join(_loi[:4]))
    sys.exit(1)
print("Tất cả xanh.")
