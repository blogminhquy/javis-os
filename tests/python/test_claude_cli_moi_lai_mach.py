"""Claude Code phải MỒI LẠI từ SQLite ở MỌI ca mạch trống, không riêng ca xoay chủ động.

    python tests/run.py moi_lai_mach

Lỗi thật (người dùng báo 18/08/2026): giữa hội thoại, Javis đột nhiên hỏi lại "bạn muốn
so sánh cái gì?" như thể chưa từng nói chuyện. Nguyên nhân: nhánh anthropic-cli chỉ
bootstrap_prompt khi `_cli_xoay_mach` (xoay mạch chủ động vì vượt ngưỡng token), trong khi
mạch còn trống ở BA ca khác:

  1. Đường tắt (fast path) vừa trả lời xong thì dọn liên kết mạch
     (set_cli_session_id(conv_sid, "")) và TIN rằng lượt sau dựng lại từ SQLite -
     comment tại chỗ đó ghi rõ như vậy, nhưng nhánh Claude Code không hề làm.
  2. Lượt trước đứt trước sự kiện `final` nên chưa kịp lưu session id.
  3. Update/restart làm rollout cũ của CLI biến mất.

Codex (9063) và Gemini (8914) đều mồi "khi không có mạch"; Claude Code là nhánh duy nhất
gate theo "vừa xoay". Test này khoá bất biến CẤU TRÚC: điều kiện bootstrap của nhánh
anthropic-cli phải là "mạch trống", để cả ba ca trên cùng được cứu.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import re
import sys

_fails = []


def check(name, cond, them=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(them) + "]") if them and not cond else ""))
    if not cond:
        _fails.append(name)


src = (ROOT / "server" / "main.py").read_text(encoding="utf-8")

# Khoanh vùng nhánh anthropic-cli: từ marker nhánh tới chỗ gửi khung response của nó.
i0 = src.find("PROVIDER anthropic-cli")
check("tìm thấy nhánh anthropic-cli", i0 > 0)
vung = src[i0:i0 + 6000]

# 1. BẤT BIẾN CHÍNH: bootstrap gate theo "không có mạch", không phải "vừa xoay".
i_gate = vung.find("if not cli.session_id:")
i_boot = vung.find("compaction.bootstrap_prompt")
check("CANARY: bootstrap chạy khi MẠCH TRỐNG (if not cli.session_id), không riêng ca xoay",
      0 < i_gate < i_boot)
check("không còn gate bootstrap theo _cli_xoay_mach",
      not re.search(r"if _cli_xoay_mach:\s*\n(\s+#[^\n]*\n)*\s+_cli_raw", vung))

# 2. Xoay mạch vẫn được cứu QUA đường mới: xoay đặt session_id = None nên rơi đúng vào gate.
check("xoay mạch đặt cli.session_id = None (rơi vào gate mạch trống)",
      "cli.session_id = None" in vung)

# 3. Mồi lại phải bỏ message hiện tại ([:-1]) và mang theo tóm tắt nén nếu có.
check("transcript mồi bỏ message user hiện tại", "store.get_messages(conv_sid)[:-1]" in vung)
check("mang theo compact_summary khi mồi", 'summary=_row0.get("compact_summary")' in vung)

# 4. Đối chiếu ba nhánh: Codex và Grok vốn đã mồi khi không có mạch - giữ nguyên.
check("Codex vẫn mồi khi không có thread",
      re.search(r"_codex_current if stored_codex_thread else\s*\n\s*compaction\.bootstrap_prompt", src))
check("Grok vẫn mồi khi không có mạch",
      re.search(r"_k_cur if _k_mach else compaction\.bootstrap_prompt", src))

# 5. bootstrap_prompt với phiên MỚI (chưa có lịch sử) phải trả nguyên prompt - gate mới
#    chạy cho cả lượt đầu tiên nên ca này thành đường nóng, hỏng là mọi phiên mới hỏng.
sys.path.insert(0, str(ROOT / "server"))
import compaction  # noqa: E402

check("bootstrap_prompt([]) trả nguyên prompt (phiên mới không bị bọc header thừa)",
      compaction.bootstrap_prompt([], "câu hỏi đầu tiên") == "câu hỏi đầu tiên")
_prompt = compaction.bootstrap_prompt(
    [{"role": "user", "content": "giá systeme.io?"},
     {"role": "assistant", "content": "gói unlimited 97 đô một tháng"}],
    "ok tra và so sánh giúp anh nhé")
check("mồi lại mang đủ hai vai của lượt cũ",
      "giá systeme.io?" in _prompt and "97 đô" in _prompt)
check("yêu cầu hiện tại nằm cuối, nguyên văn", _prompt.endswith("ok tra và so sánh giúp anh nhé"))

print()
if _fails:
    print(f"{len(_fails)} test HỎNG: " + ", ".join(_fails))
    sys.exit(1)
print("Tất cả test moi_lai_mach đã qua.")
