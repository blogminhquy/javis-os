"""Hướng dẫn và tài liệu của project phải THỰC SỰ đi vào system prompt.

    python tests/run.py project_vao_prompt      (KHÔNG mạng, không spawn engine)

Đợt 1 dựng kho. Đợt này là chỗ Project thôi làm cái nhãn lọc giao diện và bắt đầu đổi hành xử
của Javis. Hai quyết định đi KHÁC spec, cả hai đều vì cùng một lý do: một tính năng nửa vời
tệ hơn không có, vì người dùng tin là nó đang chạy.

1. GHIM FILE = NẠP NỘI DUNG, không phải đổi thứ tự danh sách.
   Spec chỉ liệt kê tên và thêm chữ "(ghim)". Nhưng người ghim bảng giá vào project thì họ
   nghĩ Javis đã BIẾT bảng giá, chứ không phải biết TÊN nó. Ghim mà chỉ đổi thứ tự là một cái
   nút trông như công tắc nhưng không nối vào đâu.

2. HƯỚNG DẪN ĐI CẢ VÀO ĐƯỜNG TIẾT KIỆM (Phase 8), danh sách tài liệu thì không.
   Spec bỏ cả khối khi Phase 8 rút gọn. Nhưng hướng dẫn là HỢP ĐỒNG HÀNH XỬ ("luôn trả lời
   bằng tiếng Anh"), vài trăm ký tự; bỏ nó nghĩa là cùng một project, cùng một câu hỏi, lượt
   này tuân luật lượt kia không - và người dùng không có cách nào biết vì sao, chỉ thấy Javis
   bướng. Danh sách tài liệu là dữ liệu tra cứu, bỏ thì cùng lắm model phải hỏi lại.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import os
import tempfile
from pathlib import Path

_STATE = tempfile.mkdtemp(prefix="javis-pvp-")
os.environ.setdefault("JAVIS_STATE_DIR", _STATE)
_BRAINS = tempfile.mkdtemp(prefix="javis-pvp-brains-")
os.environ["BRAINS_DIR"] = _BRAINS

import main  # noqa: E402
import sessions  # noqa: E402

_fails = []


def check(ten, dieu_kien, them=""):
    print(("ok   " if dieu_kien else "FAIL ") + ten
          + (("  [" + str(them)[:300] + "]") if them and not dieu_kien else ""))
    if not dieu_kien:
        _fails.append(ten)


st = main.get_store()
_root = Path(main._brain_root("brain"))
_root.mkdir(parents=True, exist_ok=True)

pid = st.create_project("Mộc Việt", brain="brain")
st.update_project(pid, instructions="Tông xanh lá. TRÁNH XANH DƯƠNG.")

# File thật trong brain để ghim (đường dẫn tương đối trần duyệt, như /files/list trả ra)
(_root / "bang-gia.md").write_text("Ghế gỗ: 1.200.000đ\nBàn trà: 2.500.000đ", encoding="utf-8")
(_root / "logo.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"x" * 50)
f_md = st.add_project_file(pid, "bang-gia.md")
f_png = st.add_project_file(pid, "logo.png")
st.add_project_link(pid, "https://elegant.vn", "Đối thủ")

# ============================================================
# 1. Hướng dẫn vào prompt
# ============================================================
kh = main._project_block(pid)
check("hướng dẫn có trong khối", "TRÁNH XANH DƯƠNG" in kh, kh)
check("kèm tên project để model biết luật này của ai", "Mộc Việt" in kh, kh)
check("không có project thì khối rỗng", main._project_block("khong-co-that") == "")

_p2 = st.create_project("Trống trơn", brain="brain")
check("project chưa có gì thì khối rỗng", main._project_block(_p2) == "",
      main._project_block(_p2))

# ============================================================
# 2. Chưa ghim = chỉ liệt kê tên. Ghim = NẠP NỘI DUNG
# ============================================================
check("file chưa ghim chỉ hiện tên + đường dẫn", "[file] bang-gia.md - bang-gia.md" in kh, kh)
check("và nội dung file chưa ghim KHÔNG bị nạp vào", "1.200.000đ" not in kh, kh)

st.set_project_file_pinned(pid, f_md, True)
kh = main._project_block(pid)
check("ghim rồi thì NỘI DUNG file được nạp thẳng vào prompt", "1.200.000đ" in kh, kh)
check("có tiêu đề nói rõ đây là nội dung nạp sẵn",
      "NỘI DUNG FILE ĐÃ GHIM" in kh, kh)

# ============================================================
# 3. Tệp nhị phân: nói THẲNG là không nạp được
# ============================================================
st.set_project_file_pinned(pid, f_png, True)
kh = main._project_block(pid)
check("ảnh ghim KHÔNG bị nhét byte nhị phân vào prompt", "\x89PNG" not in kh)
# Im lặng bỏ qua là tệ nhất: người dùng ghim xong tưởng Javis đã đọc rồi ngạc nhiên vì nó
# trả lời như chưa thấy gì.
check("mà nói thẳng là tệp nhị phân, tự mở khi cần",
      "tệp nhị phân" in kh and "logo.png" in kh, kh)

# ============================================================
# 4. Trần: một project không được nuốt hết ngân sách token
# ============================================================
(_root / "to.md").write_text("A" * 50000, encoding="utf-8")
f_to = st.add_project_file(pid, "to.md")
st.set_project_file_pinned(pid, f_to, True)
kh = main._project_block(pid)
check(f"file ghim to bị cắt về trần {main.PROJECT_GHIM_FILE_MAX} ký tự",
      kh.count("A") <= main.PROJECT_GHIM_FILE_MAX + 50, kh.count("A"))
check("và nói rõ là đã cắt bớt chứ không lặng lẽ", "đã cắt bớt" in kh, kh[-400:])
check("tổng nội dung ghim không vượt trần chung",
      len(kh) < main.PROJECT_GHIM_TONG_MAX + 3000, len(kh))

# ============================================================
# 5. Link: liệt kê, và DẶN model đừng đoán nội dung trang
# ============================================================
check("link có trong danh sách", "elegant.vn" in kh, kh)
# Chỉ 3 engine CLI có tool duyệt web. Sáu engine API nhìn thấy URL mà không mở được, nên
# prompt phải nói trước, không thì model bịa nội dung trang cho xong.
check("dặn thẳng: không có tool duyệt web thì nói, đừng đoán",
      "đừng đoán nội dung trang" in kh, kh)
check("và dặn đừng đoán nội dung file từ cái tên",
      "đừng đoán nội dung từ cái tên" in kh, kh)

# ============================================================
# 6. Đường tiết kiệm: giữ HƯỚNG DẪN, bỏ danh sách tài liệu
# ============================================================
gon = main._project_block(pid, chi_huong_dan=True)
check("bản gọn vẫn có hướng dẫn (hợp đồng hành xử, không được rơi)",
      "TRÁNH XANH DƯƠNG" in gon, gon)
check("bản gọn KHÔNG kèm danh sách tài liệu", "TÀI LIỆU & LINK" not in gon, gon)
check("và không nạp nội dung file", "1.200.000đ" not in gon, gon)
check("nên nó nhỏ hơn hẳn bản đầy đủ", len(gon) < len(kh) / 3, (len(gon), len(kh)))

# ============================================================
# 7. Nối vào build_system_prompt
# ============================================================
day_du = main.build_system_prompt("brain", project_id=pid)
check("build_system_prompt nhận project_id và ghép khối vào",
      "TRÁNH XANH DƯƠNG" in day_du)
khong = main.build_system_prompt("brain")
check("không truyền project_id thì KHÔNG có khối nào (hành vi cũ nguyên vẹn)",
      "TRÁNH XANH DƯƠNG" not in khong)
check("project_id sai cũng không làm hỏng prompt",
      "Javis" in main.build_system_prompt("brain", project_id="bay-gio-khong-co"))

# ============================================================
# 8. CANARY nguồn: ba chỗ gọi THẬT phải truyền project_id
# ============================================================
_src = (SERVER / "main.py").read_text(encoding="utf-8")
check("CANARY: đường chat dashboard truyền project_id",
      'lang=_lang_qd, project_id=_row0.get("project_id") or ""' in _src)
check("CANARY: engine gói thuê bao cũng truyền",
      'lang=_lang_qd, project_id=_row0.get("project_id") or "",' in _src)
check("CANARY: kênh Telegram cũng truyền",
      "build_system_prompt(brain, lang=_lang_qd, project_id=_pid)" in _src)
# Chỗ thứ tư trong spec là hàm ƯỚC TÍNH của trang chẩn đoán (session_id "uoc-tinh" - phiên
# giả). Nó đo prompt CHUNG chứ không đo một cuộc cụ thể, nên cố ý KHÔNG truyền project_id:
# gắn vào là con số ước tính nhảy theo project đang mở, mà nó vốn không nói về project nào.
check("CANARY: hàm ước tính KHÔNG gắn project (nó đo prompt chung)",
      'return build_system_prompt(brain) + channel_context.build_channel_block(' in _src)
check("CANARY: đường tiết kiệm chỉ lấy phần hướng dẫn",
      "_project_block(_pid, chi_huong_dan=True)" in _src)

print()
if _fails:
    print(f"FAIL {len(_fails)}: " + "; ".join(_fails))
    raise SystemExit(1)
print("TẤT CẢ PASS")
