"""Chữ TRẠNG THÁI của bước chạy nền không được lọt vào câu trả lời gửi ra ngoài.

Sự cố 13/09/2026 (chủ repo báo kèm log): bản tin giá vàng 07:01 gửi sang Telegram mở đầu bằng
"The task has been started in the background. Waiting for results." Không phải lỗi số liệu -
đó là câu chính model tự nói ở bước chờ tác vụ nền, còn vòng đọc sự kiện của `antigravity_cli`
thì cố ý gom RỘNG ("mọi thứ trông như chữ của trợ lý") để không bao giờ trả bong bóng rỗng.
Hai thứ đó cộng lại: câu trạng thái bị nối thẳng vào ĐẦU bản tin.

Trọng tài là `response` trong sự kiện `result` - `agy` mang toàn văn câu trả lời cuối ở đó.
Test này canh đúng một điều: gọt được phần thừa ĐẦU mà không bao giờ tự xén mất phần đuôi.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import os
import sys
import tempfile

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-agychot-"))

from antigravity_cli import _chot_van, AntigravityCLI  # noqa: E402

_fails = []


def check(ten, dieu_kien):
    print(("  OK   " if dieu_kien else "  HỎNG ") + ten)
    if not dieu_kien:
        _fails.append(ten)


BAN_TIN = "Giá vàng SJC sáng nay 82,1 triệu/lượng, tăng 300 nghìn so với hôm qua."
TRANG_THAI = "The task has been started in the background. Waiting for results."


# ---- gọt phần thừa đứng TRƯỚC ----
check("cắt câu trạng thái nối trước bản tin (đúng ca 13/09)",
      _chot_van(TRANG_THAI + BAN_TIN, BAN_TIN) == BAN_TIN)
check("cắt cả khi có xuống dòng ngăn giữa",
      _chot_van(TRANG_THAI + "\n\n" + BAN_TIN, BAN_TIN) == BAN_TIN)

# ---- KHÔNG được xén nhầm ----
check("gom trùng khít toàn văn thì giữ nguyên", _chot_van(BAN_TIN, BAN_TIN) == BAN_TIN)
check("không có toàn văn (bản agy cũ, chỉ có delta) thì giữ nguyên chỗ gom",
      _chot_van(TRANG_THAI + BAN_TIN, "") == TRANG_THAI + BAN_TIN)
check("chỗ gom rỗng thì trả rỗng, không dựng câu trả lời từ hư không",
      _chot_van("", BAN_TIN) == "")
check("CANARY: toàn văn bị CẮT NGẮN (chuỗi con giữa chừng) thì KHÔNG tin - giữ bản đầy đủ, "
      "thà thừa một dòng lạ còn hơn thiếu một đoạn không ai biết là đã mất",
      _chot_van(BAN_TIN + " Phần đuôi quan trọng.", BAN_TIN) == BAN_TIN + " Phần đuôi quan trọng.")
check("chữ thừa nằm GIỮA thì giữ nguyên (không đủ căn cứ để đoán chỗ cắt)",
      _chot_van("A" + BAN_TIN + "B", BAN_TIN) == "A" + BAN_TIN + "B")


# ---- nối vào vòng đọc sự kiện thật ----
def _gom(cac_su_kien):
    """Chạy đúng đường `_doi_su_kien` của engine rồi chốt văn như `query()` làm."""
    cli = AntigravityCLI(tag="test")
    manh, chan = [], {}
    for ev in cac_su_kien:
        cli._doi_su_kien(ev, manh, chan)
    return _chot_van("".join(manh).strip(), chan.get("toan_van", ""))


check("luồng thật: step_update trạng thái + step_update bản tin + result -> chỉ còn bản tin",
      _gom([
          {"event": "step_update", "step_update": {"step_type": "agent_response",
                                                   "text_delta": TRANG_THAI}},
          {"event": "step_update", "step_update": {"step_type": "agent_response",
                                                   "text_delta": BAN_TIN}},
          {"event": "result", "result": {"status": "SUCCESS", "response": BAN_TIN}},
      ]) == BAN_TIN)

check("luồng thật: lượt ngắn CHỈ có result (không delta nào) vẫn ra chữ",
      _gom([{"event": "result", "result": {"status": "SUCCESS", "response": BAN_TIN}}]) == BAN_TIN)

check("luồng thật: không có result thì giữ nguyên phần đã gom (không mất câu trả lời)",
      _gom([{"event": "step_update", "step_update": {"step_type": "agent_response",
                                                     "text_delta": BAN_TIN}}]) == BAN_TIN)

check("luồng thật: câu trả lời KHÔNG bị hiện hai lần khi result lặp lại toàn văn",
      _gom([
          {"event": "step_update", "step_update": {"step_type": "agent_response",
                                                   "text_delta": BAN_TIN}},
          {"event": "result", "result": {"status": "SUCCESS", "response": BAN_TIN}},
      ]) == BAN_TIN)

check("CANARY: _doi_su_kien gọi được KHÔNG kèm chan (chữ ký cũ vẫn chạy)",
      AntigravityCLI(tag="test")._doi_su_kien(
          {"event": "result", "result": {"status": "SUCCESS", "response": BAN_TIN}}, []) is not None)


print()
if _fails:
    print(f"{len(_fails)} test HỎNG: " + ", ".join(_fails))
    sys.exit(1)
print("Tất cả test antigravity _chot_van đã qua.")
