"""Watchdog chống treo phải phân biệt "đang nạp ngữ cảnh" với "đã treo thật".

    python tests/run.py watchdog_treo

Không cần pytest, không chạm mạng, không spawn engine.

Bối cảnh (báo từ người dùng thật, 2026-07-30): "chat dài bị lỗi này" kèm ảnh
"Claude không phản hồi 180s - đã dừng để tránh treo server".

Watchdog vốn có hai trần: 180s cho lúc model im lặng, và 3600s cho lúc đang chờ tool chạy
(vì tool render/build im cả tiếng là bình thường). Nhưng nó bỏ sót trường hợp thứ ba: khoảng
im lặng TRƯỚC KHI có chữ đầu tiên. Hội thoại càng dài thì lượt đầu càng lâu (nạp lại toàn bộ
ngữ cảnh, model suy nghĩ trước khi phát chữ, có lúc SDK còn tự nén lịch sử), nên chat dài là
dính 180s và bị chém oan - đúng như người dùng gặp.

Test này khoá ba trần đó tách bạch ở CẢ HAI engine, và khoá luôn nội dung thông báo: người
dùng phải đọc ra được là nên mở hội thoại mới, chứ không phải chỉ được bảo đi sửa biến môi
trường mà đa số không biết đặt ở đâu.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import re
import sys

_fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)


sdk = (SERVER / "claude_sdk_engine.py").read_text(encoding="utf-8")
cli = (SERVER / "claude_cli.py").read_text(encoding="utf-8")

# ---- 1. Cả ba trần đều tồn tại, đều đọc được từ biến môi trường ----
for ten, nguon in (("engine Claude SDK", sdk), ("engine Codex CLI", cli)):
    for bien, mac_dinh in (("JAVIS_CLAUDE_IDLE_TIMEOUT", "180"),
                           ("JAVIS_CLAUDE_TOOL_TIMEOUT", "3600"),
                           ("JAVIS_CLAUDE_FIRST_TIMEOUT", "600")):
        check(f"{ten}: có trần {bien} (mặc định {mac_dinh})",
              re.search(rf'{bien}"\s*,\s*"{mac_dinh}"', nguon) is not None)

# ---- 2. Trần chờ-chữ-đầu phải DÀI HƠN trần im-giữa-chừng, nếu không thì vá vô nghĩa ----
def _mac_dinh(nguon, bien):
    m = re.search(rf'{bien}"\s*,\s*"(\d+)"', nguon)
    return float(m.group(1)) if m else -1


for ten, nguon in (("engine Claude SDK", sdk), ("engine Codex CLI", cli)):
    first = _mac_dinh(nguon, "JAVIS_CLAUDE_FIRST_TIMEOUT")
    idle = _mac_dinh(nguon, "JAVIS_CLAUDE_IDLE_TIMEOUT")
    tool = _mac_dinh(nguon, "JAVIS_CLAUDE_TOOL_TIMEOUT")
    check(f"{ten}: trần chờ chữ đầu > trần im giữa chừng", first > idle > 0)
    check(f"{ten}: trần chờ tool vẫn là dài nhất (render/build cả tiếng)", tool >= first)

# ---- 3. Cờ "đã có chữ chưa" phải thật sự được LẬT khi nhận dữ liệu ----
# Quên lật cờ thì mọi khoảng lặng đều xài trần dài, tức là mất luôn tác dụng chống treo.
than_query = sdk.split("async def query")[1]
check("SDK: có cờ đánh dấu đã nhận sự kiện đầu", "da_co_chu" in than_query)
check("SDK: cờ khởi tạo là False", "da_co_chu = False" in than_query)
check("SDK: cờ được lật True sau khi nhận được message", "da_co_chu = True" in than_query)
check("SDK: chọn trần theo cờ, không dùng cứng IDLE",
      "IDLE if da_co_chu else FIRST_IDLE" in than_query)

check("CLI: có cờ đánh dấu đã nhận dòng đầu", '"dong_dau"' in cli)
check("CLI: cờ khởi tạo là False", 'seen = {"dong_dau": False}' in cli)
check("CLI: cờ được lật True trong vòng đọc stdout",
      'seen["dong_dau"] = True' in cli)
than_watchdog = cli.split("def _watchdog(p):")[1].split("threading.Thread")[0]
check("CLI: watchdog chọn trần theo cờ", 'seen["dong_dau"]' in than_watchdog)
check("CLI: watchdog vẫn ưu tiên trần tool khi đang chạy tool",
      'busy["n"] > 0' in than_watchdog and "TOOL_IDLE" in than_watchdog)

# ---- 4. Thông báo phải chỉ được lối thoát mà người thường làm được ----
for ten, nguon in (("engine Claude SDK", sdk), ("engine Codex CLI", cli)):
    check(f"{ten}: thông báo chờ-chữ-đầu mách mở hội thoại mới",
          "Mở hội thoại mới" in nguon)
    check(f"{ten}: thông báo nói rõ vì sao (hội thoại dài, nạp lại ngữ cảnh)",
          "hội thoại đã rất dài" in nguon)
    check(f"{ten}: vẫn nêu biến môi trường cho người biết chỉnh",
          "JAVIS_CLAUDE_FIRST_TIMEOUT" in nguon)

# ---- 5. Ba thông báo phải KHÁC nhau, nếu không thì lại không phân biệt được bệnh ----
for ten, nguon in (("engine Claude SDK", sdk), ("engine Codex CLI", cli)):
    check(f"{ten}: thông báo im-giữa-chừng khác thông báo chờ-chữ-đầu",
          "rồi im" in nguon)

# ---- 6. Quy tắc cứng của dự án ----
for ten, nguon in (("engine Claude SDK", sdk), ("engine Codex CLI", cli)):
    doan = "".join(re.findall(r'"[^"]*đã dừng để tránh treo[^"]*"', nguon))
    check(f"{ten}: thông báo không có em/en dash", "—" not in doan and "–" not in doan)

if _fails:
    print(f"\nFAIL - test_watchdog_treo: {len(_fails)} lỗi: {_fails}")
    sys.exit(1)
print("\nOK - test_watchdog_treo: tất cả pass")
