"""Câu trả lời trên khung chat web phải ĐỌC ĐƯỢC, không phải một khối văn xuôi.

    python tests/run.py chat_de_doc

Chủ repo gửi hai ảnh chụp khung chat (2026-08-09): những câu trả lời dài đổ ra thành hết đoạn
văn xuôi này tới đoạn văn xuôi khác, không gạch đầu dòng, không tiêu đề, không chỗ nào cho mắt
bám. Kèm lý do vì sao nó thành ra như vậy: "ngày xưa anh để Javis thể hiện cho dễ cho việc
voice, nhưng giờ khi anh dùng hầu như là chat nhiều. Và nó render ra văn xuôi rất khó đọc."

Gốc rễ là một luật trong CLAUDE.md có thật: "KHÔNG dùng bảng markdown, dấu gạch ngang dày, hay
header khi báo cáo trong chat. Prose ngắn gọn". Luật đó viết cho thời dùng bằng giọng nói và nó
đúng cho thời đó. Nhưng nó cấm nguyên cả bộ công cụ trình bày trên một kênh vẽ được đủ markdown,
và nút loa của dashboard thì đã tự bóc markdown trước khi đọc (`dashboard/voice.js::_cleanForTTS`)
nên nỗi lo hỏng giọng đọc không còn cơ sở.

Ba lớp phải cùng đổi, thiếu một lớp là hành vi quay về cũ ở đúng đường đó:
  1. CLAUDE.md - luật gốc nạp vào mọi lượt của mọi engine.
  2. `channel_context.build_channel_block("dashboard")` - khối kênh, đứng CUỐI system prompt
     nên nó là tiếng nói to nhất khi model chọn cách trình bày.
  3. `context_compiler` - đường tiết kiệm token không đi qua CLAUDE.md, chỉ có capsule.

Và một luật ngược chiều, quan trọng ngang phần trên: nới cho web KHÔNG được nới sang kênh chữ
thuần. Telegram và Zalo không vẽ được bảng, terminal thì không render gì cả. Bốn check cuối
canh đúng chỗ đó, vì đây là kiểu hồi quy dễ lọt nhất khi ai đó đi nới luật trình bày.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import os
import re
import tempfile

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-dedoc-"))

import channel_context  # noqa: E402
import context_compiler  # noqa: E402

_fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)


_CLAUDE_MD = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")
_VOICE_JS = (ROOT / "dashboard" / "voice.js").read_text(encoding="utf-8")

_WEB = channel_context.build_channel_block("dashboard", {"session_id": "s1"})
_TG = channel_context.build_channel_block("telegram", {"chat_id": "42"})
_ZL = channel_context.build_channel_block("zalo", {"chat_id": "z1"})
_CLI = channel_context.build_channel_block("cli", {"host": "may-chu"})


# ============================================================
# 1. CLAUDE.md: luật gốc không còn cấm bộ công cụ trình bày
# ============================================================
# CANARY: đúng câu cũ. Nó là thứ đã sinh ra mấy bức tường chữ trong ảnh chụp, nên nó quay lại
# là bệnh quay lại - dù phần còn lại của file có dặn gì đi nữa.
check("CANARY: câu cấm cũ đã biến khỏi CLAUDE.md",
      "KHÔNG dùng bảng markdown, dấu gạch ngang dày, hay header khi báo cáo trong chat"
      not in _CLAUDE_MD)

# CLAUDE.md nay là TIẾNG ANH (0.50.0) - soi câu tiếng Anh tương đương. Luật thì không đổi.
for tu in ("bullets", "Bold what people scan for", "###", "Short paragraphs"):
    check(f"CLAUDE.md dạy dùng '{tu}'", tu in _CLAUDE_MD)
check("CLAUDE.md nói rõ TTS tự bóc markdown (hết cớ viết xấu vì sợ voice)",
      "TTS" in _CLAUDE_MD and "strips markdown" in _CLAUDE_MD)
# Nới không phải là xổ toẹt: một câu hỏi nhỏ vẫn phải được trả lời bằng một câu.
check("CLAUDE.md vẫn chặn thói bẻ ý nhỏ thành báo cáo",
      "Structure serves length" in _CLAUDE_MD)
# Ký ức cũ "không thích bảng markdown" được nạp vào MỌI lượt và sẽ lặng lẽ kéo hành vi về cũ
# nếu luật mới không nói thẳng ai thắng ai.
check("CLAUDE.md xử lý ký ức cũ về định dạng (luật mới thắng)",
      "memory" in _CLAUDE_MD and "beats that memory" in _CLAUDE_MD)
# Luật em dash là luật riêng, không được cuốn theo lúc dọn luật trình bày.
check("luật cấm em dash còn nguyên",
      "NEVER use the em dash character" in _CLAUDE_MD)
check("chính CLAUDE.md không chứa em dash", "—" not in _CLAUDE_MD)


# ============================================================
# 2. Cơ sở của luật: TTS thật sự bóc markdown trước khi đọc
# ============================================================
# Nếu chỗ này hỏng thì luật ở trên thành lời hứa suông, và người dùng bật loa lên sẽ nghe
# "thăng thăng thăng doanh thu" thay vì "doanh thu".
# Lấy phần SAU lần nhắc cuối cùng: tên này xuất hiện ở chỗ gọi trước, chỗ định nghĩa sau.
_clean = _VOICE_JS.split("_cleanForTTS")[-1] if "_cleanForTTS" in _VOICE_JS else ""
check("voice.js có bộ lọc _cleanForTTS", bool(_clean))
check("TTS bóc tiêu đề markdown", "#{1,6}" in _clean)
check("TTS bóc dấu gạch đầu dòng", "[-*•]" in _clean)
check("TTS bóc chữ in đậm", "\\*\\*(.+?)\\*\\*" in _clean)
check("TTS bóc ô bảng markdown", "\\|" in _clean)


# ============================================================
# 3. Khối kênh dashboard: dạy trình bày, vì nó đứng cuối prompt
# ============================================================
check("khối web có hẳn mục cách trình bày", "Cách trình bày trong khung chat này" in _WEB)
check("web: nói rõ khung chat render đủ markdown", "render ĐỦ markdown" in _WEB)
for tu in ("gạch đầu dòng", "in đậm", "###", "bảng"):
    check(f"web: có dạy '{tu}'", tu in _WEB.lower() or tu in _WEB)
check("web: gọi tên đúng cái bệnh (văn xuôi liền mạch)", "văn xuôi liền mạch" in _WEB)
check("web: trấn an chuyện giọng đọc để khỏi tự siết lại",
      "bóc markdown" in _WEB)
check("web: vẫn dặn ngắn gọn, không lấy định dạng làm cớ viết dài",
      "giọng người đang nói" in _WEB and "viết dài" in _WEB)
check("khối web không dính em dash", "—" not in _WEB)


# ============================================================
# 4. Đường tiết kiệm token (capsule) nói cùng một thứ
# ============================================================
# Đường này KHÔNG đọc CLAUDE.md. Bỏ quên nó thì bật "Siêu tiết kiệm" là văn xuôi quay lại,
# mà người dùng không có cách nào đoán ra vì sao cùng một câu hỏi lại ra hai kiểu trình bày.
_hd_web = context_compiler.ContextCompiler._channel_contract("dashboard")
check("capsule web: dạy chia đoạn", "chia đoạn" in _hd_web)
check("capsule web: dạy gạch đầu dòng", "gạch đầu dòng" in _hd_web)
check("capsule web: cho dùng bảng khi so sánh", "bảng" in _hd_web)
_loi = context_compiler.ContextCompiler._output_contract_text("dashboard")
check("phần 'Cách trả lời' vẫn còn (Core Contract trỏ vào đây)", "Cách trả lời" in _loi)
check("phần 'Cách trả lời' nay có luật trình bày", "gạch đầu dòng" in _loi)
check("capsule không dính em dash", "—" not in _hd_web and "—" not in _loi)


# ============================================================
# 5. Nới cho web KHÔNG được tràn sang kênh chữ thuần
# ============================================================
check("Telegram: vẫn cấm bảng", "đừng dùng bảng" in _TG)
check("Zalo: vẫn cấm bảng", "đừng dùng bảng" in _ZL)
check("CLI: vẫn cấm bảng", "TUYỆT ĐỐI không dùng bảng" in _CLI)
check("CLI: vẫn cấm ảnh nhúng và link markdown",
      "không nhúng ảnh" in _CLI and "không dùng link markdown" in _CLI)
# Hợp đồng capsule của hai kênh này cũng vậy - cùng một luật, hai đường đi.
check("capsule Telegram: vẫn cấm bảng",
      "không dùng bảng Markdown" in context_compiler.ContextCompiler._channel_contract("telegram"))
check("capsule CLI: vẫn cấm bảng",
      "KHÔNG bảng Markdown" in context_compiler.ContextCompiler._channel_contract("cli"))
# Nhưng gạch đầu dòng thì kênh nào cũng hiện được, nên kênh nào cũng được dạy dùng.
for ten, khoi in (("Telegram", _TG), ("Zalo", _ZL), ("CLI", _CLI)):
    check(f"{ten}: vẫn được dùng gạch đầu dòng khi liệt kê", "gạch đầu dòng" in khoi)
# CLI không tô đậm được: dạy nó dùng ** là dạy nó in ra nguyên dấu sao.
check("CLI: không dạy dùng ** để in đậm",
      not re.search(r"in đậm[^.\n]*\*\*", _CLI))


if _fails:
    raise SystemExit(f"\nFAIL - test_chat_de_doc: {len(_fails)} lỗi")
print("\nOK - test_chat_de_doc: tất cả pass")
