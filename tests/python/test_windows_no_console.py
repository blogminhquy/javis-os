"""Không lời gọi lệnh con nào được để Windows bung một cửa sổ console đen.

    python tests/run.py windows_no_console      (KHÔNG mạng, KHÔNG cần Windows)

Chủ repo báo 2026-08-13, kèm mô tả rất đúng triệu chứng: "thi thoảng chuyển tab nó lại nháy đen
màn hình terminal xong tắt luôn".

Cơ chế: Javis trên Windows khởi động qua `start-javis.vbs`, tức tiến trình server chạy KHÔNG CÓ
console. Trong Windows, một tiến trình không console mà sinh ra chương trình dạng console (git,
curl, node, python, npx...) thì hệ điều hành TỰ CẤP cho đứa con một cửa sổ console mới. Nó chớp
lên rồi tắt cùng lúc với lệnh con. Không hỏng gì, nhưng cướp tiêu điểm bàn phím và trông hệt như
phần mềm lỗi - mà lại chỉ xảy ra trên máy người dùng, không bao giờ thấy ở CI Linux.

Chữa bằng đúng một cờ `CREATE_NO_WINDOW`, và cái khó không nằm ở chỗ chữa mà ở chỗ NHỚ chữa: cả
repo có hơn bốn chục lời gọi subprocess, thêm một lời gọi mới mà quên cờ thì triệu chứng quay
lại y nguyên, và không test nào trên Linux bắt được. Nên canary này quét mã nguồn.

Hai cách viết sai đã gặp thật, cả hai đều nằm trong danh sách canh:
- quên hẳn: curl của Substack, `git rev-parse` của luồng cập nhật, script của nhắc hẹn, và mọi
  lệnh git/pip trong `updater.py` (mà updater còn chạy DETACHED nên nháy suốt lượt cập nhật);
- viết đúng hình thức nhưng lấy nhầm chỗ: `getattr(asyncio.subprocess, "CREATE_NO_WINDOW", 0)`
  trong plugin `zalo-image`. Module `asyncio.subprocess` KHÔNG export cờ đó nên biểu thức luôn
  trả 0 - lời gọi trông như đã bảo vệ mà thật ra trần trụi.
"""
from _paths import ROOT  # noqa: E402,F401
import re
import sys

_fails = []


def check(name, cond, them=""):
    print(("ok   " if cond else "FAIL ") + name
          + (("  [" + str(them) + "]") if them and not cond else ""))
    if not cond:
        _fails.append(name)


# Những chỗ CỐ Ý mở cửa sổ, kèm lý do. Thêm vào đây phải kèm lý do, đừng dùng nó làm chỗ trốn.
_CO_Y = {
    # Mở terminal THẬT cho người dùng gõ tay: đăng nhập MCP của Claude Code và của Codex. Cả hai
    # là hành động do người dùng bấm, và cửa sổ chính là thứ họ cần nhìn.
    ("claude_cli.py", "mcp_open_auth_terminal"),
    ("claude_cli.py", "codex_mcp_open_login_terminal"),
    # Khởi động lại Javis sau khi cập nhật: tiến trình mới phải sống lâu hơn tiến trình sinh ra
    # nó, nên đi bằng DETACHED_PROCESS chứ không phải CREATE_NO_WINDOW.
    ("main.py", "_trigger"),
    ("updater.py", "start_server"),
    # Bench dev, chạy tay từ terminal có sẵn.
    ("bench_hotpath.py", None),
}

_SPAWN = re.compile(r"(?:subprocess\.(?:run|Popen|call|check_output|check_call)"
                    r"|asyncio\.create_subprocess_(?:exec|shell))\s*\(")


def _ham_chua(src: str, vt: int) -> str:
    """Tên hàm bao quanh vị trí này (dò ngược lên `def ...`). Rỗng nếu ở tầng module."""
    ten = ""
    for m in re.finditer(r"^\s*(?:async\s+)?def\s+(\w+)", src[:vt], re.M):
        ten = m.group(1)
    return ten


def _tron_ngoac(src: str, i: int) -> str:
    sau, j = 0, i
    while j < len(src):
        if src[j] == "(":
            sau += 1
        elif src[j] == ")":
            sau -= 1
            if sau == 0:
                return src[i:j + 1]
        j += 1
    return src[i:i + 400]


_thieu = []
_files = sorted(list((ROOT / "server").glob("*.py"))
                + list((ROOT / "system").rglob("*.py")))
for f in _files:
    src = f.read_text(encoding="utf-8")
    for m in _SPAWN.finditer(src):
        goi = _tron_ngoac(src, m.end() - 1)
        ham = _ham_chua(src, m.start())
        if (f.name, ham) in _CO_Y or (f.name, None) in _CO_Y:
            continue
        # Cờ có thể nằm ngay trong lời gọi, hoặc dựng sẵn thành kwargs vài dòng phía trên.
        truoc = src[max(0, m.start() - 400):m.start()]
        if "creationflags" in goi or "kwargs_no_window" in goi:
            continue
        if "creationflags" in truoc and "**kwargs" in goi:
            continue
        _thieu.append(f"{f.name}:{src[:m.start()].count(chr(10)) + 1} trong {ham or '<module>'}()")

check("CANARY: mọi lời gọi lệnh con đều chặn cửa sổ console của Windows",
      not _thieu, "; ".join(_thieu))

# Lấy cờ từ ĐÚNG module. `asyncio.subprocess` không có nó, nên `getattr(...)` ở đó luôn ra 0 và
# lỗi này im lặng tuyệt đối trên Linux lẫn CI.
_sai_module = []
for f in _files:
    if f.name == "winproc.py":
        continue      # chính nó dẫn lại cách viết sai đó trong chú thích để giải thích
    src = f.read_text(encoding="utf-8")
    if re.search(r"getattr\(\s*asyncio\.subprocess\s*,\s*[\"']CREATE_NO_WINDOW", src):
        _sai_module.append(f.name)
check("CANARY: không lấy CREATE_NO_WINDOW từ asyncio.subprocess (ở đó nó luôn là 0)",
      not _sai_module, _sai_module)

# Module dùng chung phải tồn tại và trả 0 ngoài Windows (truyền vô điều kiện được).
sys.path.insert(0, str(ROOT / "server"))
import winproc  # noqa: E402

check("winproc.no_window() trả 0 ngoài Windows", winproc.no_window() == 0)
check("winproc.kwargs_no_window() rỗng ngoài Windows", winproc.kwargs_no_window() == {})

print()
if _fails:
    print(f"{len(_fails)} test HỎNG: " + ", ".join(_fails))
    sys.exit(1)
print("Tất cả test windows_no_console đã qua.")
