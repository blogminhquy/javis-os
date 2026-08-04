"""Rào DUY NHẤT của bot chuyên trách: nó chỉ thấy brain của chính nó.

    python tests/run.py chatbot_cach_ly      (KHÔNG mạng)

Chủ repo chốt phạm vi ngày 2026-08-04: "Anh có Agent và quy định của nó rồi, em đừng tự thêm
vào quy định của nó. Chỉ có làm việc chống chỉ định xem các brain khác ngoài brain agent đang
ở thôi."

Nên file này canh HAI thứ, và chỉ hai thứ đó:

A. **Prompt là của Agent, không phải của Javis.** Không chèn khối luật nào lên trên hướng dẫn
   người dùng viết. Bản 0.19.0 tới 0.20.1 đều chèn, và nó cãi nhau với chính Agent.

B. **Cách ly brain, bằng MÃ chứ không bằng chữ.** Đây là phần đáng canh nhất, vì nó KHÔNG hiện
   ra khi dùng thử: bot vẫn trả lời đúng, vẫn lịch sự, và chủ không có cách nào biết nó vừa
   đọc được brain khác. Ba đường ra ngoài, mỗi đường một lớp chặn khác nhau:

     1. Engine API (OpenRouter, OpenAI, Anthropic, Gemini, Groq, Ollama): mọi đường đọc file
        đều qua tool của hub, và hub khoá bằng `mcp_hub._safe_path`.
     2. Claude Code: có tool NATIVE (Bash, Read, Glob, Grep) KHÔNG đi qua hub. cwd một mình
        không phải rào - `cat ../brain-khac/...` vẫn chạy. Lớp chặn thật là `allowed_tools`,
        vì đặt nó làm engine bật permission_mode="default" + cổng can_use_tool từ chối từng
        lượt gọi tool ngoài danh sách.
     3. Codex: KHÔNG có cả hai. Sandbox của nó chặn ghi và mạng, không nhốt phạm vi đọc. Nên
        bot bị TỪ CHỐI chạy trên Codex, chứ không hạ sandbox rồi coi như xong - một rào chặn
        được nửa vời còn tệ hơn không có, vì chủ tưởng nó đang bảo vệ mình.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401  - nạp server/ vào sys.path
import os
import sys
import tempfile
from pathlib import Path

_STATE = tempfile.mkdtemp(prefix="javis-cachly-")
os.environ["JAVIS_STATE_DIR"] = _STATE

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import chatbot_runtime  # noqa: E402
import mcp_hub  # noqa: E402

_fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)


# ============================================================
# A. Prompt là của Agent, Javis không chèn luật
# ============================================================
QUY_DINH = """## Quy định của tôi

1. Luôn hỏi lại người dùng đã ngủ đủ chưa trước khi tư vấn.
2. Không bao giờ nói "cố lên", đó là lời khuyên rỗng.
3. Mỗi câu trả lời kết thúc bằng đúng một hành động nhỏ làm được trong 5 phút."""

chatbot_runtime.wire(
    answer=None, brain_root=lambda b: "/tmp/khong-dung",
    read_agent=lambda brain, slug: ({"name": "Coach kỷ luật",
                                     "role": "Huấn luyện viên kỷ luật cá nhân."}, QUY_DINH),
)
bot = {"name": "Bot", "agent": {"brain": "brain", "slug": "coach"}, "handoff_to": "555"}
p = chatbot_runtime.build_bot_prompt(bot)

check("prompt lấy tên từ Agent", "Coach kỷ luật" in p)
check("prompt lấy vai trò từ Agent", "Huấn luyện viên kỷ luật cá nhân" in p)
check("prompt giữ NGUYÊN VĂN quy định người dùng viết", QUY_DINH in p)

# CANARY - đừng gỡ. Đây là yêu cầu trực tiếp của chủ repo, và là thứ dễ bị "thêm lại cho chắc"
# nhất: mỗi lần thấy bot trả lời chưa vừa ý, phản xạ đầu tiên là nhét thêm một dòng luật vào
# prompt. Làm vậy là quay lại đúng lỗi cũ - luật của Javis đè lên quy định người dùng đã viết.
for cam in ("Luật bắt buộc", "đứng trên mọi hướng dẫn khác", "Không hứa hẹn thay",
            "Bỏ qua mọi yêu cầu đổi vai", "Ngắn gọn, lịch sự", "cửa hàng", "bảng giá",
            "Người nhắn cho bạn có thể là NGƯỜI LẠ"):
    check(f"CANARY: Javis KHÔNG chèn luật của mình - '{cam[:32]}'", cam not in p)

check("prompt KHÔNG mang system prompt điều phối của Javis",
      "javis_schedule" not in p and "Kanban" not in p and "MCP Hub" not in p)

_SRC_RT = (SERVER / "chatbot_runtime.py").read_text(encoding="utf-8")
check("module không còn hằng số khối luật", "_LUAT" not in _SRC_RT)

# Tài liệu tra sẵn vẫn vào prompt, nhưng vào như DỮ LIỆU chứ không kèm mệnh lệnh nào.
p_tl = chatbot_runtime.build_bot_prompt(
    {**bot, "_tai_lieu": {"co": True, "khoi": "### Giá\n\nGói 3 tháng 6 triệu.", "nguon": ["gia.md"]}})
check("tài liệu tra được vẫn đưa vào prompt", "Gói 3 tháng 6 triệu" in p_tl)
check("khối tài liệu không kèm mệnh lệnh nào",
      "TUYỆT ĐỐI" not in p_tl and "đừng suy ra" not in p_tl)

# Không tìm thấy tài liệu: mặc định IM LẶNG, không dặn dò gì thêm.
p_trong = chatbot_runtime.build_bot_prompt({**bot, "_tai_lieu": {"co": False, "khoi": "", "nguon": []}})
check("không có tài liệu -> mặc định không thêm chữ nào vào prompt", p_trong == p)

# Chế độ "chỉ tài liệu" là lựa chọn CỦA NGƯỜI DÙNG, nên ở đó mới có một câu chỉ dẫn.
p_chat = chatbot_runtime.build_bot_prompt(
    {**bot, "nguon_tra_loi": "tai_lieu", "_tai_lieu": {"co": False, "khoi": "", "nguon": []}})
check("chế độ chỉ-tài-liệu (người dùng tự bật) mới có một câu chỉ dẫn",
      "chế độ CHỈ TRẢ LỜI THEO" in p_chat)
check("và nó vẫn KHÔNG đụng tới quy định của Agent", QUY_DINH in p_chat)


# ============================================================
# B1. Hub khoá đường đọc file trong vault
# ============================================================
GOC = Path(tempfile.mkdtemp(prefix="javis-cachly-brains-"))
(GOC / "brain-bot").mkdir()
(GOC / "brain-bot" / "gia.md").write_text("Gói 3 tháng 6 triệu.\n", encoding="utf-8")
(GOC / "brain-chu").mkdir()
(GOC / "brain-chu" / "bi-mat.md").write_text("Giá vốn 400k, biên 70%.\n", encoding="utf-8")

BOT_ROOT = GOC / "brain-bot"
check("đọc file TRONG brain của bot -> được",
      mcp_hub._safe_path(BOT_ROOT, "gia.md") == (BOT_ROOT / "gia.md").resolve())
check("chính gốc vault -> được", mcp_hub._safe_path(BOT_ROOT, ".") == BOT_ROOT.resolve())

# Mọi kiểu trèo ra ngoài đều phải nổ, không phải trả về rỗng: trả rỗng thì model tưởng file
# không tồn tại và thử tiếp bằng đường khác.
for xau in ("../brain-chu/bi-mat.md",
            "../../etc/passwd",
            "./../brain-chu/bi-mat.md",
            "a/b/../../../brain-chu/bi-mat.md",
            str(GOC / "brain-chu" / "bi-mat.md"),      # đường dẫn TUYỆT ĐỐI
            "/etc/passwd"):
    try:
        mcp_hub._safe_path(BOT_ROOT, xau)
        ok = False
    except ValueError:
        ok = True
    check(f"CANARY: chặn đường ra brain khác - '{xau[:40]}'", ok)

# Bẫy tên: "brain-bot-khac" có tiền tố trùng "brain-bot" nên so chuỗi thô sẽ cho lọt.
(GOC / "brain-bot-khac").mkdir()
(GOC / "brain-bot-khac" / "x.md").write_text("của người khác\n", encoding="utf-8")
try:
    mcp_hub._safe_path(BOT_ROOT, "../brain-bot-khac/x.md")
    ok = False
except ValueError:
    ok = True
check("CANARY: brain trùng tiền tố tên cũng bị chặn (không so chuỗi thô)", ok)


# ============================================================
# B2. Claude Code: cwd một mình KHÔNG phải rào, phải có allowed_tools
# ============================================================
_SRC = (SERVER / "main.py").read_text(encoding="utf-8")
check("bot chạy Claude Code với cwd = brain của nó",
      "cwd=_brain_root(brain) if bot else CLAUDE_CWD" in _SRC)
# Đây mới là lớp chặn thật. Không có nó thì engine chạy permission_mode="bypassPermissions",
# và Bash/Read/Glob/Grep native đọc thẳng brain khác lẫn mã nguồn server.
check("CANARY: bot chỉ được gọi tool qua hub Javis, cấm tool native",
      "allowed_tools=mcp_hub.allow_patterns() if bot else None" in _SRC)
check("engine bật cổng duyệt thật khi có allowed_tools",
      'kw["permission_mode"] = "default"' in
      (SERVER / "claude_sdk_engine.py").read_text(encoding="utf-8"))
check("allow_patterns chỉ mở đúng nhóm tool của hub",
      mcp_hub.allow_patterns() == ["mcp__javis"])


# ============================================================
# B3. Codex: không khoá được phạm vi đọc -> TỪ CHỐI chạy bot
# ============================================================
check("CANARY: bot bị từ chối khi engine chính là Codex",
      'if prov == "openai-oauth" and bot:' in _SRC)
check("câu từ chối nói rõ lý do và cách xử lý",
      "không khoá được phạm vi đọc file" in _SRC and "Đổi engine chính sang" in _SRC)
# Nếu ai đó gỡ nhánh từ chối rồi thay bằng hạ sandbox, test này đỏ - đúng ý đồ: sandbox của
# Codex chặn GHI và mạng, không nhốt phạm vi ĐỌC, nên nó không phải lời giải cho bài này.
check("không dùng sandbox Codex làm rào cách ly (nó không nhốt đường đọc)",
      'ccli.sandbox = "read-only"' not in _SRC)


# ============================================================
# B4. Mức quyền của lượt bot vẫn hạ bằng mã
# ============================================================
# Không phải luật trong prompt nên không vi phạm phạm vi chủ repo chốt: đây là quyền của tiến
# trình, thứ khách nói chuyện với bot không đụng tới được.
check("lượt bot chạy mức chỉ đọc", 'bot_mode = "suggest" if bot else "full"' in _SRC)
check("mức quyền truyền xuống hub", "mode=bot_mode" in _SRC)
check("bot đọc brain RIÊNG của nó, không phải brain của chủ",
      'brain = bot["brain"]' in _SRC)
check("phiên của bot tách khỏi phiên của chủ",
      '_tg_session(f"bot:{bot[\'id\']}:{chat_id}")' in _SRC)

print()
if _fails:
    print(f"ĐỎ {len(_fails)} mục: " + ", ".join(_fails))
    sys.exit(1)
print("Tất cả xanh.")
