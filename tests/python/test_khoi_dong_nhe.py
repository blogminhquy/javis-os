"""Đường khởi động phải nhẹ: thư viện của tính năng tuỳ chọn KHÔNG được nạp lúc import main.

    python tests/run.py khoi_dong_nhe     (KHÔNG mạng)

Bối cảnh 0.9.238: `import edge_tts` nằm ở đầu main.py dù TTS là tính năng tuỳ chọn mà đa số
phiên không đụng tới. Đo bằng `python -X importtime`: 944ms trong tổng 2.263ms nạp main (41%),
cộng kéo cả chuỗi aiohttp 212ms vào đường khởi động. Trên VPS, khởi động chậm ăn thẳng vào
cửa sổ healthcheck lúc deploy.

Test này tồn tại vì lỗi kiểu đó rất dễ tái phát: ai đó thêm `import <thư viện nặng>` lên đầu
file cho tiện, không ai nhận ra, và app chậm dần từng chút một mà không có tín hiệu nào.

0.59.18 thêm `jsonschema` (~50ms) vào diện phải nạp lười.

2026-11-07: the timing ratio at the end of this file (main vs fastapi) is replaced by a list of the outside packages
`import main` may load. Same goal, but it cannot fail at random on a busy machine. See STARTUP_PACKAGES.
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
# ĐÂY LÀ HÀNG RÀO CHÍNH của file này: nó xác định, không nhiễu, và nêu đúng tên thư viện có lỗi.
# STARTUP_PACKAGES at the end catches a heavy library nobody has named here yet.
NANG_PHAI_LUOI = {
    "edge_tts": "TTS (giọng đọc) - 944ms, kéo theo cả aiohttp",
    "aiohttp": "chỉ đi kèm edge_tts, không code nào của Javis dùng trực tiếp",
    # 0.59.18: jsonschema ~50ms, chỉ hai hàm của capability_executor và một hàm của
    # readonly_orchestrator dùng, và cả ba chỉ chạy khi thật sự cấp/kiểm một capability lease.
    "jsonschema": "kiểm schema capability lease - ~50ms, chỉ dùng khi có lease",
    # 0.274.0: ws_compat chỉ vá uvicorn khi uvicorn thật sự được nạp (~40ms); webpush chỉ nạp
    # cryptography khi ký hoặc mã hoá (~20ms). Phép đo tỉ lệ đã chạm trần 4,0 ngay trên main.
    "uvicorn": "chỉ cần khi chạy server; mọi đường khởi động đã nạp nó trước hoặc tự nạp sau",
    "cryptography": "chỉ webpush ký VAPID và mã hoá tin đẩy, lúc thật sự gửi",
}

# File nào phải KHÔNG có lệnh import thư viện đó ở cột 0. Mặc định là main.py; thư viện nào
# từng nằm ở file khác thì ghi rõ file ấy, kẻo hàng rào canh sai chỗ.
NOI_CAM_IMPORT = {
    "jsonschema": ("capability_executor.py", "readonly_orchestrator.py"),
    "uvicorn": ("main.py", "ws_compat.py"),
    "cryptography": ("main.py", "webpush.py"),
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

# ---- Which outside libraries `import main` may load (replaces the timing ratio, 2026-11-07) ----
# History: this used to be a TIMING check, "import main costs at most N times import fastapi". It caught a heavy
# library slipping onto the startup path before anyone had named it in NANG_PHAI_LUOI. But the cost of main.py grows
# legitimately with every route (FastAPI spends ~3 ms building each one), so the ceiling was raised 4.0 -> 4.5 (0.244.0)
# -> 5.0 (0.318.0), and by 0.497.0 main itself measured 4.72-5.10 on one machine: any PR went red at random and had to
# be re-run by hand (owner, 2026-11-07: fix the check, do not raise the number a third time).
#
# Same goal, no clock: run `import main` in a fresh interpreter and list the TOP-LEVEL packages it loads from
# site-packages. That set does not depend on how fast or busy the machine is, so it never fails at random, and when a
# new library lands on the startup path the failure NAMES it. A heavy library always arrives as a new top-level name
# (edge_tts, aiohttp, pandas...), so this catches exactly what the ratio was for. Growth in Javis's own code (server/)
# and in the standard library is not counted: that is the legitimate growth the ratio kept tripping over.
#
# Adding a package here is a decision: say in the comment why the server needs it at startup. If it only serves an
# optional feature, import it inside the function that uses it and add it to NANG_PHAI_LUOI instead.
STARTUP_PACKAGES = {
    # The web framework and what it is built on.
    "fastapi", "starlette", "pydantic", "pydantic_core", "annotated_types", "annotated_doc", "typing_extensions",
    "typing_inspection", "anyio", "sniffio", "python_multipart",
    # Outgoing HTTP (provider APIs, update check, MCP), used across main.py.
    "httpx", "httpcore", "h11", "idna", "certifi",
    # Config and brain files: .env loading, YAML frontmatter.
    "dotenv", "yaml",
}
# Loaded only when the machine happens to have them installed: httpx's __init__ imports its command-line module, which
# pulls these in if present (pip-audit on a dev machine brings rich; uvicorn brings click). Allowed, never required.
STARTUP_PACKAGES_OPTIONAL = {"click", "pygments", "rich", "markdown_it", "mdurl"}

_PROBE = r"""
import json, os, sys, sysconfig
before = set(sys.modules)
import main
roots = {os.path.realpath(sysconfig.get_paths()[k]) for k in ("purelib", "platlib")}
tops = set()
for name, mod in list(sys.modules.items()):
    if name in before:
        continue
    f = os.path.realpath(getattr(mod, "__file__", None) or "") if getattr(mod, "__file__", None) else ""
    if f and (any(f.startswith(r + os.sep) for r in roots) or "site-packages" in f or "dist-packages" in f):
        tops.add(name.split(".")[0])
print("JAVIS-PROBE " + json.dumps(sorted(tops)))
"""


def startup_packages():
    """Top-level site-packages names a fresh `import main` loads, or None when the probe itself failed."""
    import json
    out = subprocess.run([sys.executable, "-c", _PROBE], cwd=HERE, capture_output=True, text=True)
    line = next((ln for ln in out.stdout.splitlines() if ln.startswith("JAVIS-PROBE ")), "")
    if not line:
        print("     (probe failed: " + (out.stderr.strip().splitlines() or ["no output"])[-1] + ")")
        return None
    return set(json.loads(line[len("JAVIS-PROBE "):]))


loaded = startup_packages()
check("probe ran `import main` in a fresh interpreter", loaded is not None)
if loaded is not None:
    print("     (loaded at startup: " + ", ".join(sorted(loaded)) + ")")
    unexpected = sorted(loaded - STARTUP_PACKAGES - STARTUP_PACKAGES_OPTIONAL)
    check("import main loads no outside library beyond STARTUP_PACKAGES"
          + (" (new: " + ", ".join(unexpected) + ")" if unexpected else ""), not unexpected)
    # The probe must see the framework, or it is not looking at site-packages at all and would pass anything.
    check("probe sees fastapi and pydantic (it really reads site-packages)", {"fastapi", "pydantic"} <= loaded)
    for mod in NANG_PHAI_LUOI:
        check(f"'{mod}' is not in the allowed startup list", mod not in STARTUP_PACKAGES | STARTUP_PACKAGES_OPTIONAL)

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
