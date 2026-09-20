"""Chat với một trợ lý ở trang Cộng sự: system prompt là prompt của trợ lý, không phải Javis.

    python tests/run.py agent_chat_prompt

Không chạy engine. Kiểm hai hàm thuần trong main.py và canh (bằng đọc mã) rằng bộ điều
phối lượt rẽ nhánh theo persona ở đủ các chỗ chọn prompt.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import os
import re
import sys
import tempfile
from pathlib import Path

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-agchat-")
os.environ["BRAINS_DIR"] = tempfile.mkdtemp(prefix="javis-agchat-brains-")  # KHONG dung brains/ that

import main  # noqa: E402

fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        fails.append(name)


# Brain tạm (xem ghi chú Task 3 về biến env chọn thư mục brains; đặt TRƯỚC import main nếu cần)
ag_dir = main._agents_dir("brain"); ag_dir.mkdir(parents=True, exist_ok=True)
(ag_dir / "nguoi-viet.md").write_text("---\nname: Người viết\nrole: viết bài\nskills: [viet-email]\n---\nViết súc tích.\n",
                                       encoding="utf-8")

p = main._agent_chat_prompt("brain", "nguoi-viet")
check("prompt la cua tro ly", "Bạn là agent **Người viết**" in p and "Viết súc tích." in p and "JAVIS_LESSON" in p)
check("prompt noi ro dang chat truc tiep", "trò chuyện trực tiếp" in p)
check("prompt KHONG keo CLAUDE.md cua Javis", "SWAPPABLE BRAIN" not in p and "# === LỚP AGENTIC" not in p)
# 2026-09-18: agent "Biên tập viên" từ chối đẩy file lên Drive vì "ngoài phạm vi", rồi BỊA đã
# "bàn giao cho agent dang_tai" và hẹn "có kết quả em báo lại". Prompt agent phải nói rõ: vai
# là chuyên môn chứ không phải hàng rào tool, không bịa giao việc, không hẹn báo lại.
check("prompt agent noi ro co TOAN BO tool qua hub (khong tu choi viec ngoai vai)",
      "javis_run_tool" in p and "javis_task" in p and "javis_connections" in p
      and "không phải hàng rào" in p)
check("prompt agent cam bia 'da giao cho agent khac'", "không bịa tên agent" in p)
check("prompt agent cam hen 'co ket qua em bao lai'", "báo lại" in p and "KẾT THÚC khi bạn nói xong" in p)
try:
    main._agent_chat_prompt("brain", "khong-co")
    check("tro ly khong co -> FileNotFoundError", False)
except FileNotFoundError:
    check("tro ly khong co -> FileNotFoundError", True)

sach = main._ket_luot_agent("brain", "nguoi-viet", "viết giúp", "Bài đây.\nJAVIS_LESSON: chủ thích câu ngắn")
check("ket luot boc JAVIS_LESSON", sach.strip() == "Bài đây.")
mem = (main._brain_memory_dir("brain") / "agents" / "nguoi-viet" / "MEMORY.md")
check("bai hoc vao bo nho agent", mem.exists() and "chủ thích câu ngắn" in mem.read_text(encoding="utf-8"))
runs = list((main._brain_memory_dir("brain") / "agents" / "nguoi-viet" / "runs").glob("*.md"))
check("nhat ky run cua agent co dong", runs and "viết giúp" in runs[0].read_text(encoding="utf-8"))

# Canh mã: _do_turn rẽ theo persona ở các chỗ chọn prompt
src = (SERVER / "main.py").read_text(encoding="utf-8")
than = src[src.index("async def _do_turn("):src.index("async def run_turn(")]
check("_do_turn doc persona tu phien", "_persona = workflow_chat.persona_cua_phien(_row0)" in than)
check("_legacy_system_prompt dung prompt tro ly", "_agent_chat_prompt(brain, _persona[1])" in than)
check("_subscription_system_prompt bo qua nen ngu canh khi co persona",
      re.search(r"def _subscription_system_prompt\(.*?\):\s*\"\"\".*?\"\"\"\s*if _persona:\s*return _legacy_system_prompt\(\), None", than, re.S) is not None)
check("nhanh phase8 API khong dung plan khi co persona", 'action == "use" and not _persona' in than)
check("cuoi luot goi _ket_luot_agent", "_ket_luot_agent(brain, _persona[1], user_message, final_text)" in than)

# Fix round 1 - issue 1: bong bóng chat KHÔNG được để lộ dòng JAVIS_LESSON. Mọi nhánh engine
# đã gửi khung "response" RAW trước khi tới _ket_luot_agent, nên sau khi bóc sạch phải gửi
# lại một khung "response" nữa để ép trình duyệt vẽ lại đúng chữ (xem app.js: data.type ===
# "response" thay hẳn nội dung bong bóng bằng data.content).
_m_resend = re.search(
    r"_ket_luot_agent\(brain, _persona\[1\], user_message, final_text\)(.{0,1600}?)\"type\": \"response\"(.{0,200}?)\}\)\)",
    than, re.S)
check("sau _ket_luot_agent co gui lai khung response de xoa JAVIS_LESSON tren bong bong",
      _m_resend is not None)
# Fix round 2: khung gửi lại PHẢI kèm "tts": False, nếu không app.js gọi voice.speak() lần
# hai (đọc lại từ đầu) vì t.spoke chỉ được set từ nhánh "stream", không phải từ speak() dự
# phòng ở cuối nhánh "response" cho engine đọc-một-lần.
check("khung gui lai co tts:false de khong doc lai lan hai",
      _m_resend is not None and '"tts": False' in _m_resend.group(2))

# Fix round 1 - issue 2: cụm canary của engine kiểu "api" (Phase 9 write-path, orchestrator,
# readonly, Fast Path) phải KHÔNG được chạy khi có persona - nếu không nó tự trả lời bằng
# prompt riêng, bỏ mất hẳn prompt trợ lý cho lượt đó. Cả cụm phải rơi thẳng xuống nhánh Phase 8
# API/OAuth cuối (đã persona-aware) khi có persona.
_m_cascade = re.search(
    r'elif \(kind == "api" and api_key\) or kind == "oauth":(.*?)# ===== API/OAuth: Phase 8',
    than, re.S)
check("cascade api-key ton tai va bi gate boi not _persona",
      _m_cascade is not None and 'and not _persona' in _m_cascade.group(1))

print("\nFAIL:" if fails else "\nOK - agent_chat_prompt", fails or "")
sys.exit(1 if fails else 0)
