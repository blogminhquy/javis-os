"""File VERSION phải khớp mục mới nhất trong CHANGELOG.md.

    python tests/run.py version_khop

Lỗi thật: ba bản 0.14.5, 0.14.6, 0.14.7 đều được ghi vào nhật ký mà quên bump `VERSION`.
Trang Cập nhật đọc HAI nguồn khác nhau - khung trên so `VERSION` trên nhánh main, huy hiệu
dưới đọc `CHANGELOG.md` - nên nó hiện đúng hai dòng ngược nhau trên cùng một màn hình:
"Đang dùng bản mới nhất (v0.14.4)" và "Có bản mới: v0.14.7".

Hậu quả nặng hơn vẻ ngoài. `update_available` tính bằng `VERSION`, nên nó là FALSE: người
dùng Docker không có nút bấm, cũng không có cả hướng dẫn Redeploy. Ba bản vá nằm đó mà
không ai lấy được, và không có một dòng lỗi nào. Bộ test cũ chạy xanh cả ba lần.

Đây là loại lỗi test phải bắt chứ không phải người phải nhớ: nó không làm hỏng chức năng
nào, chỉ làm đường phát hành đứt, nên chạy thử trên máy dev không đời nào lộ ra.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import re
import sys

_fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)


_VER_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")
_MUC_RE = re.compile(r"^## \[(.+?)\](?:\s*-\s*(\S+))?", re.M)

_ver_path = ROOT / "VERSION"
_cl_path = ROOT / "CHANGELOG.md"

check("có file VERSION", _ver_path.is_file())
check("có file CHANGELOG.md", _cl_path.is_file())

_ver = _ver_path.read_text(encoding="utf-8").strip()
_cl = _cl_path.read_text(encoding="utf-8")
_muc = _MUC_RE.findall(_cl)

check("VERSION đúng dạng x.y.z (không có 'v', không xuống dòng thừa)",
      bool(_VER_RE.match(_ver)))
check("CHANGELOG có ít nhất một mục phiên bản", len(_muc) >= 1)

_moi_nhat = _muc[0][0] if _muc else ""
# ĐÂY là bài kiểm chính. Lệch một nhịp là trang Cập nhật nói ngược nhau và người dùng
# Docker mất sạch đường lên bản mới.
check(f"CANARY: VERSION ({_ver}) khớp mục mới nhất trong CHANGELOG ({_moi_nhat})",
      _ver == _moi_nhat)

# Mọi số hiệu trong nhật ký phải đúng dạng, nếu không thì phần so sánh phiên bản của trang
# Cập nhật đọc phải rác và im lặng coi như 0.0.0.
_xau = [v for v, _d in _muc if not _VER_RE.match(v)]
check(f"mọi mục trong nhật ký đều đúng dạng x.y.z (sai: {_xau})", not _xau)

# Mới nhất phải nằm TRÊN CÙNG - trang Cập nhật lấy mục đầu tiên làm bản mới nhất, chứ không
# tự sắp xếp lại.
def _bo(v):
    m = _VER_RE.match(v)
    return tuple(int(x) for x in m.groups()) if m else (0, 0, 0)


_ds = [_bo(v) for v, _d in _muc if _VER_RE.match(v)]
check("nhật ký xếp mới nhất trên cùng", _ds == sorted(_ds, reverse=True))
check("không có phiên bản trùng trong nhật ký", len(_ds) == len(set(_ds)))

# Và endpoint phải đọc ĐÚNG file đó, chứ không phải một hằng số chép tay ở đâu đó.
import main  # noqa: E402

check("máy chủ báo đúng phiên bản trong file VERSION", main._read_version() == _ver)

print()
if _fails:
    print(f"THẤT BẠI {len(_fails)}: {_fails}")
    sys.exit(1)
print("OK - test_version_khop_changelog: tất cả pass")
