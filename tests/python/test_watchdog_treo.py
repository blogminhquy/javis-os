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

Bổ sung 2026-08-07 (v0.25.6): trần 180s bị BỎ HẲN làm mặc định. Chủ repo gửi ảnh: bảo Javis
"thiết kế cho anh file .md", Javis nói "viết file luôn" rồi bị chém ở giây 180. Lý do là phép
đo sai chứ không phải con số nhỏ - SDK chỉ phát message khi model kết thúc một khối, nên suốt
lúc model suy nghĩ ở mức nỗ lực cao hoặc soạn nội dung file dài để đưa vào tool Write, kênh im
hoàn toàn dù mọi thứ đang chạy đúng. Nay hai trần đo-sự-im-lặng mặc định KHÔNG GIỚI HẠN; trần
chờ TOOL giữ nguyên vì nó đo một tiến trình con có thật đang sống.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import os
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
# claude_sdk_engine.py is pinned byte for byte, so its source still names "3600" for the tool cap; main.py sets the
# real default (0 = no cap, owner 2026-11-07) before any engine runs. See section 2b.
for ten, nguon, tool_mac_dinh in (("engine Claude SDK", sdk, "3600"), ("engine Codex CLI", cli, "0")):
    for bien, mac_dinh in (("JAVIS_CLAUDE_IDLE_TIMEOUT", "0"),
                           ("JAVIS_CLAUDE_TOOL_TIMEOUT", tool_mac_dinh),
                           ("JAVIS_CLAUDE_FIRST_TIMEOUT", "0")):
        check(f"{ten}: có trần {bien} (mặc định {mac_dinh})",
              re.search(rf'{bien}"\s*,\s*"{mac_dinh}"', nguon) is not None)

# ---- 2. "0 = không giới hạn" phải là hành vi THẬT, không chỉ là con số trong mã ----
from claude_sdk_engine import tran_watchdog  # noqa: E402

for raw in ("0", "-1", "0.0"):
    os.environ["JAVIS_TEST_TRAN"] = raw
    check(f"đặt '{raw}' → không giới hạn (None)",
          tran_watchdog("JAVIS_TEST_TRAN", "180") is None)
os.environ["JAVIS_TEST_TRAN"] = "45"
check("đặt số dương → giữ nguyên trần đó", tran_watchdog("JAVIS_TEST_TRAN", "180") == 45.0)
os.environ["JAVIS_TEST_TRAN"] = "linh tinh"
check("giá trị rác → về mặc định chứ không làm nổ lượt chat",
      tran_watchdog("JAVIS_TEST_TRAN", "180") == 180.0)
os.environ.pop("JAVIS_TEST_TRAN", None)
check("chưa đặt biến → dùng mặc định truyền vào",
      tran_watchdog("JAVIS_TEST_TRAN", "0") is None
      and tran_watchdog("JAVIS_TEST_TRAN", "3600") == 3600.0)

# ---- 2b. Hai trần đo SỰ IM LẶNG mặc định tắt, trần chờ TOOL thì không ----
def _mac_dinh(nguon, bien):
    m = re.search(rf'{bien}"\s*,\s*"([\d.]+)"', nguon)
    return float(m.group(1)) if m else -1


for ten, nguon in (("engine Claude SDK", sdk), ("engine Codex CLI", cli)):
    check(f"{ten}: trần im-giữa-chừng mặc định KHÔNG giới hạn",
          _mac_dinh(nguon, "JAVIS_CLAUDE_IDLE_TIMEOUT") == 0)
    check(f"{ten}: trần chờ-chữ-đầu mặc định KHÔNG giới hạn",
          _mac_dinh(nguon, "JAVIS_CLAUDE_FIRST_TIMEOUT") == 0)

# Owner 2026-11-07 ("bỏ hết các trần của các model"): the tool cap is off by default too, on every engine path.
main_src = (SERVER / "main.py").read_text(encoding="utf-8")
check("main.py: the tool cap defaults to no limit before any engine runs",
      'os.environ.setdefault("JAVIS_CLAUDE_TOOL_TIMEOUT", "0")' in main_src
      and main_src.index('os.environ.setdefault("JAVIS_CLAUDE_TOOL_TIMEOUT", "0")') < main_src.index("import claude_warm"))
for ten in ("claude_warm.py", "codex_steer.py"):
    check(f"{ten}: tool cap default is 0 (no limit)",
          _mac_dinh((SERVER / ten).read_text(encoding="utf-8"), "JAVIS_CLAUDE_TOOL_TIMEOUT") == 0)

# ---- 2c. Chốt trần và LÝ DO cùng lúc: suy ngược lý do lúc hết giờ là int(None) nổ ----
than_query = sdk.split("async def query")[1]
check("SDK: chốt trần kèm lý do trong cùng một nhánh", 'tran, ly_do' in than_query)
check("SDK: thông báo chọn theo lý do đã chốt, không suy ngược",
      'ly_do == "wall"' in than_query and 'ly_do == "tool"' in than_query)
than_watchdog_cli = cli.split("def _watchdog(p):")[1].split("threading.Thread")[0]
check("CLI: trần tắt (None) thì bỏ qua chứ không so sánh với None",
      "if limit and time.time()" in than_watchdog_cli)

# ---- 3. Cờ "đã có chữ chưa" phải thật sự được LẬT khi nhận dữ liệu ----
# Quên lật cờ thì mọi khoảng lặng đều xài trần dài, tức là mất luôn tác dụng chống treo.
than_query = sdk.split("async def query")[1]
check("SDK: có cờ đánh dấu đã nhận sự kiện đầu", "da_co_chu" in than_query)
check("SDK: cờ khởi tạo là False", "da_co_chu = False" in than_query)
check("SDK: cờ được lật True sau khi nhận được message", "da_co_chu = True" in than_query)
check("SDK: chọn trần theo cờ, không dùng cứng IDLE",
      "tran, ly_do = IDLE" in than_query and "tran, ly_do = FIRST_IDLE" in than_query)

check("CLI: có cờ đánh dấu đã nhận dòng đầu", '"dong_dau"' in cli)
check("CLI: cờ khởi tạo là False", 'seen = {"dong_dau": False}' in cli)
check("CLI: cờ được lật True trong vòng đọc stdout",
      'seen["dong_dau"] = True' in cli)
check("CLI: watchdog chọn trần theo cờ", 'seen["dong_dau"]' in than_watchdog_cli)
check("CLI: watchdog vẫn ưu tiên trần tool khi đang chạy tool",
      'busy["n"] > 0' in than_watchdog_cli and "TOOL_IDLE" in than_watchdog_cli)

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
