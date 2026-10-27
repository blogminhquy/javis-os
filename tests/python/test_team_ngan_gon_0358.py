"""Nhóm (Team) 0.358.0: thành viên nói ngắn, giao diện điện thoại gọn (chủ repo 27/10/2026).

    python tests/run.py team_ngan_gon_0358

"trong nhóm thì bọn nó nói ngắn gọn thôi ko cần trình bày dài dòng xem loạn lắm" và "uxui nhìn điện thoại trong phần
team loạn lắm". Luật nói ngắn nằm trong đoạn nối vào MỌI lượt nhóm (INTERNAL_GROUP_NOTE), nên lượt trả lời, lập kế hoạch,
làm và tổng hợp đều nhận.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import os
import re
import sys
import tempfile

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-ngan-gon-"))

import team_runner as TR  # noqa: E402

_fails = []


def check(name, cond, them=""):
    print(("ok   " if cond else "FAIL ") + name + (f"  [{them}]" if not cond and them else ""))
    if not cond:
        _fails.append(name)


note = "\n".join(TR.INTERNAL_GROUP_NOTE)
check("mọi lượt nhóm nhận luật NÓI NGẮN như nhắn tin", "NÓI NGẮN" in note and "1 đến 3 câu" in note)
check("không chào hỏi, không nhắc lại câu hỏi, không tiêu đề, không bảng",
      all(w in note for w in ("không chào hỏi", "không nhắc lại câu hỏi", "không tiêu đề", "không bảng")))
check("sản phẩm dài ghi vào file, trong nhóm chỉ báo file và ý chính", "ghi vào file" in note and "1 đến 2 dòng chính" in note)
check("khối điều khiển JAVIS_TEAM không bị luật độ dài cắt", "JAVIS_TEAM" in note and "không tính vào độ dài" in note)
check("không em dash trong lời nhắc", "—" not in note and "–" not in note)
check("lượt làm việc có công cụ cũng trả lời NGẮN", "Trả lời trong nhóm NGẮN" in TR.WORK_TOOLS_NOTE)
SRC = (SERVER / "team_runner.py").read_text(encoding="utf-8")
check("lượt trả lời tin của chủ: 1 đến 3 câu", "Trả lời ngắn gọn (1 đến 3 câu), đúng vai của bạn trong nhóm." in SRC)
check("bước tổng hợp: kết quả cuối NGẮN, không kể lại từng bước",
      "thành một kết quả cuối NGẮN cho chủ nhóm" in SRC and "Không kể lại từng bước." in SRC)

css = (ROOT / "dashboard" / "console.css").read_text(encoding="utf-8")
i = css.find("/* 0.358.0 (owner, 27/10/2026")
block = css[i:]
check("CSS điện thoại 0.358.0 có mặt, trong khung 760px", i > 0 and "@media (max-width: 760px)" in block[:400])
check("đầu khung chat: nút biểu tượng không viền hộp", ".tm-chat-head .ws-btn.tm-icon, .tm-chat-head .tm-back { border-color: "
      "transparent;" in block)
check("tiêu đề trong tin cùng cỡ chữ, bảng cuộn ngang", ".tm-bubble h1" in block and "overflow-x: auto" in block)
check("ngăn bên: một cỡ chữ 16px, tiêu đề mục không viết hoa", ".tm-side .tm-qhead { font-size: 16px; text-transform: none;" in block)
sizes = [int(x) for x in re.findall(r"font-size:\s*(\d+)px", block)]
check("không chữ nào dưới 16px trong khối mới", sizes and min(sizes) >= 16, sizes)

print()
if _fails:
    print("FAILED: " + ", ".join(_fails))
    sys.exit(1)
print("All passed")
