"""Đường khởi động phải nhẹ: thư viện của tính năng tuỳ chọn KHÔNG được nạp lúc import main.

    python tests/run.py khoi_dong_nhe     (KHÔNG mạng)

Bối cảnh 0.9.238: `import edge_tts` nằm ở đầu main.py dù TTS là tính năng tuỳ chọn mà đa số
phiên không đụng tới. Đo bằng `python -X importtime`: 944ms trong tổng 2.263ms nạp main (41%),
cộng kéo cả chuỗi aiohttp 212ms vào đường khởi động. Trên VPS, khởi động chậm ăn thẳng vào
cửa sổ healthcheck lúc deploy.

Test này tồn tại vì lỗi kiểu đó rất dễ tái phát: ai đó thêm `import <thư viện nặng>` lên đầu
file cho tiện, không ai nhận ra, và app chậm dần từng chút một mà không có tín hiệu nào.

0.59.18 thêm `jsonschema` (~50ms) vào diện phải nạp lười, và sửa chính phép đo tỉ lệ ở cuối
file vì nó báo oan: xem khối chú thích ngay trên TRAN_TI_LE.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401  - nạp server/ vào sys.path (xem tests/python/_paths.py)
import os
import subprocess
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-khoidong-"))
HERE = str(SERVER)
sys.path.insert(0, HERE)

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

_fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)


# Thư viện chỉ phục vụ tính năng TUỲ CHỌN -> phải nạp lười.
# Thêm vào đây khi phát hiện thư viện nặng mới, đừng chờ ai đó tự nhận ra.
#
# ĐÂY LÀ HÀNG RÀO CHÍNH của file này, không phải phép đo tỉ lệ ở dưới: nó xác định, không
# nhiễu, và nêu đúng tên thư viện có lỗi. Phép đo tỉ lệ chỉ là còi báo cháy hạng hai.
NANG_PHAI_LUOI = {
    "edge_tts": "TTS (giọng đọc) - 944ms, kéo theo cả aiohttp",
    "aiohttp": "chỉ đi kèm edge_tts, không code nào của Javis dùng trực tiếp",
    # 0.59.18: jsonschema ~50ms, chỉ hai hàm của capability_executor và một hàm của
    # readonly_orchestrator dùng, và cả ba chỉ chạy khi thật sự cấp/kiểm một capability lease.
    "jsonschema": "kiểm schema capability lease - ~50ms, chỉ dùng khi có lease",
}

# File nào phải KHÔNG có lệnh import thư viện đó ở cột 0. Mặc định là main.py; thư viện nào
# từng nằm ở file khác thì ghi rõ file ấy, kẻo hàng rào canh sai chỗ.
NOI_CAM_IMPORT = {
    "jsonschema": ("capability_executor.py", "readonly_orchestrator.py"),
}

import main  # noqa: E402,F401

for mod, ly_do in NANG_PHAI_LUOI.items():
    check(f"'{mod}' KHÔNG nạp lúc import main ({ly_do})", mod not in sys.modules)

# ---- Nạp lười phải thật sự nạp được, không phải chỉ hoãn lỗi sang lúc user bấm nói ----
# CỐ TÌNH không gọi main.tts_voices(): hàm đó đi mạng tới dịch vụ giọng đọc của Microsoft,
# mà test này phải chạy được offline. Chỉ kiểm hai điều tách bạch: (a) thư viện nạp được
# khi cần, (b) hai chỗ dùng đều có lệnh import cục bộ nên sẽ nạp được lúc chạy.
try:
    import edge_tts  # noqa: E402,F401
    nap_duoc = True
except Exception as e:
    nap_duoc = False
    print(f"     (nạp edge_tts lỗi: {type(e).__name__}: {e})")
check("edge_tts vẫn nạp được khi cần (không phải chỉ hoãn lỗi sang lúc dùng)", nap_duoc)

import inspect  # noqa: E402

for ten in ("_tts_edge", "tts_voices"):
    fn = getattr(main, ten, None)
    src = inspect.getsource(fn) if fn else ""
    check(f"{ten}() có lệnh import edge_tts cục bộ", "import edge_tts" in src)

# ---- jsonschema cũng vậy, và nó khắt khe hơn edge_tts một bậc ----
try:
    import jsonschema  # noqa: E402,F401
    check("jsonschema vẫn nạp được khi cần", True)
except Exception as e:
    check(f"jsonschema vẫn nạp được khi cần (lỗi: {type(e).__name__}: {e})", False)

import capability_executor      # noqa: E402
import readonly_orchestrator    # noqa: E402

# Ba hàm dùng jsonschema phải có lệnh import CỤC BỘ, và lệnh đó phải nằm NGOÀI khối try.
# Vì sao khắt khe hơn edge_tts: cả ba chỗ đều bắt lỗi rồi trả "schema không hợp lệ"
# (readonly_orchestrator bắt cả `except Exception`). Để import trong try là một bản cài
# thiếu jsonschema biến thành "schema sai" - hàng rào coi như đã kiểm mà thực ra chưa kiểm
# gì, và không có dòng log nào. Ngoài try thì ImportError nổ thẳng, đúng như hồi import ở
# đầu file.
_BA_HAM = (
    (capability_executor.CapabilityExecutor, "issue_lease"),
    (capability_executor.CapabilityExecutor, "_validate"),
    (readonly_orchestrator.ReadonlyOrchestrator, "_planner_round"),
)
for lop, ten in _BA_HAM:
    src = inspect.getsource(getattr(lop, ten))
    co_import = "from jsonschema import" in src
    check(f"{lop.__name__}.{ten}() có lệnh import jsonschema cục bộ", co_import)
    if co_import:
        truoc_try = src.index("from jsonschema import") < (
            src.index("try:") if "try:" in src else len(src))
        check(f"{lop.__name__}.{ten}(): lệnh import nằm TRƯỚC khối try "
              "(trong try thì cài thiếu jsonschema hoá thành 'schema sai')", truoc_try)

# ---- Trần chi phí nạp, đo bằng TỈ LỆ chứ không phải mili giây ----
# Bản đầu dùng trần tuyệt đối 3000ms và nó ĐÃ báo oan: trên máy đang bị quét virus, chỉ
# riêng `import fastapi` đã 2,9-6,3 giây và interpreter trống mất 500ms, nên `import main`
# vọt lên 7,6 giây mà không có dòng code nào đổi. Trần theo mili giây đo tốc độ MÁY, không
# đo thứ ta quan tâm.
#
# Tỉ lệ so với `import fastapi` thì miễn nhiễm với tốc độ máy, vì cả tử lẫn mẫu cùng chậm đi.
#
# CHỈNH LẠI 0.59.18 sau khi phép đo này báo oan hai lần trong một buổi (đỏ trong bộ test đầy
# đủ, chạy riêng lại thì xanh; chạy riêng 12 lần thì đỏ 2). Hai nguyên nhân, cả hai đều là
# lỗi của phép đo chứ không phải của code:
#
# 1. ĐO KHÔNG XEN KẼ. Bản cũ đo xong cả ba lượt `pass`, rồi cả ba lượt fastapi, rồi cả ba
#    lượt main. Máy chậm đi đúng lúc đo mẫu số là tỉ lệ tụt, chậm đúng lúc đo tử số là tỉ lệ
#    vọt. Đo thật: mẫu số nhảy 347-502ms giữa các lần, tức tỉ lệ đu đưa +-0,2 mà không dòng
#    code nào đổi. Nay xen kẽ từng vòng (pass, fastapi, main, lặp lại), máy chậm thì cả ba
#    cùng chậm - biên độ co lại còn 0,08.
#
# 2. NGƯỠNG 3,0 ĐÃ HẾT BIÊN. Chú thích cũ ghi "hiện tại 1,93", nhưng đo lại 16/09, đã hoãn
#    jsonschema rồi, vẫn là 2,67-2,75 trên máy cài đúng requirements.txt và 2,75-2,88 trên
#    MÁY DEV có pip-audit (nó kéo `rich` vào, làm `httpx` nạp luôn module CLI của nó, cộng
#    ~110ms mà người dùng thật KHÔNG phải trả; trước khi hoãn jsonschema thì máy dev đo được
#    2,93-3,32, tức vượt trần cũ). Phần phình không nằm ở một thư viện nào: thân main.py tốn
#    ~320ms để khai hơn 300 endpoint, và nó lớn dần theo số tính năng một cách chính đáng.
#    Ngưỡng 4,0 vẫn tách sạch ca phải bắt: thêm lại edge_tts ở mức module là ~5,9 (đo bằng
#    chi phí nạp edge_tts 944ms + aiohttp 212ms trên nền hiện tại), và nó đúng ở cả hai môi
#    trường nên không có chuyện xanh ở CI mà đỏ ở máy người phát triển.
#
# Vẫn giữ phép đo này dù nó thô: nó là thứ duy nhất bắt được "main phình lên" khi thư viện
# nặng mới CHƯA kịp có tên trong NANG_PHAI_LUOI. Hàng rào chính xác là danh sách đó.
TRAN_TI_LE = 4.0


def do_nap_xen_ke(codes, n=5):
    """Chi phí nạp từng đoạn, đo XEN KẼ rồi lấy min mỗi loại.

    Xen kẽ để nhiễu của máy rơi đều lên cả ba loại; min vì nhiễu chỉ cộng thêm thời gian,
    không bao giờ trừ bớt."""
    import time
    ts = {c: [] for c in codes}
    for _ in range(n):
        for c in codes:
            t = time.perf_counter()
            subprocess.run([sys.executable, "-c", c], cwd=HERE, capture_output=True)
            ts[c].append((time.perf_counter() - t) * 1000)
    return {c: min(v) for c, v in ts.items()}


_do = do_nap_xen_ke(("pass", "import fastapi", "import main"))
base = _do["pass"]
chi_fastapi = _do["import fastapi"] - base
chi_main = _do["import main"] - base
ti_le = chi_main / chi_fastapi if chi_fastapi > 0 else 0
print(f"     (interpreter trần {base:.0f} ms | fastapi {chi_fastapi:.0f} ms | "
      f"main {chi_main:.0f} ms | tỉ lệ {ti_le:.2f})")
check(f"nạp main không quá {TRAN_TI_LE} lần chi phí nạp fastapi (đang {ti_le:.2f} lần)",
      0 < ti_le < TRAN_TI_LE)

# ---- Không ai lén thêm lại import ở mức module ----
for mod in NANG_PHAI_LUOI:
    for ten_file in NOI_CAM_IMPORT.get(mod, ("main.py",)):
        src = Path(HERE, ten_file).read_text(encoding="utf-8", errors="replace")
        o_cot_0 = [ln for ln in src.split("\n")
                   if ln.startswith(f"import {mod}") or ln.startswith(f"from {mod} ")]
        check(f"{ten_file} không có 'import {mod}' ở mức module", not o_cot_0)

print()
if _fails:
    print(f"FAIL {len(_fails)} test: " + ", ".join(_fails))
    sys.exit(1)
print("TẤT CẢ PASS")
