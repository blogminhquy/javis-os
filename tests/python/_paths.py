"""Đường dẫn dùng chung cho mọi test Python, và nạp server/ vào sys.path.

Vì sao có file này: trước 0.9.242 các test nằm CHUNG thư mục với mã nguồn, nên chúng lấy
đường dẫn bằng `Path(__file__).parent` (ra server/) và `Path(__file__).parent.parent` (ra
gốc repo). Khi test dọn sang tests/python/ thì cả hai lệch một tầng, và 37 chỗ như vậy nằm
rải trong 30 file. Gom về một chỗ thì sửa một lần, và lần sau có dời nữa cũng chỉ sửa ở đây.

Import nó cũng đồng thời NẠP server/ vào sys.path, nên test gọi `import main` được từ bất kỳ
thư mục làm việc nào. Trước đây test phải chạy đúng từ server/ mới import được; nay không còn
ràng buộc đó, kể cả với các test mở file nguồn bằng đường dẫn.

    from _paths import ROOT, SERVER     # đặt TRƯỚC mọi `import <module server>` VÀ mọi tempfile.*

Import nó còn trỏ thư mục tạm của cả tiến trình vào một thư mục riêng, tự xoá khi thoát -
xem khối "Thư mục tạm" bên dưới. Vì vậy phải import TRƯỚC lần gọi tempfile đầu tiên.

Ngoài đường dẫn, file này giữ `moi_duong_dan(app)`: cách DUY NHẤT đúng để liệt kê đường dẫn
của app. Xem chú thích của hàm - đọc thẳng `app.routes` là sai từ fastapi 0.141.
"""
import atexit
import os
import shutil
import stat
import sys
import tempfile
import time
from pathlib import Path

# tests/python/_paths.py -> parents[0]=python, [1]=tests, [2]=gốc repo
ROOT = Path(__file__).resolve().parents[2]
SERVER = ROOT / "server"
DASHBOARD = ROOT / "dashboard"
SYSTEM = ROOT / "system"

if str(SERVER) not in sys.path:
    sys.path.insert(0, str(SERVER))

# Chốt chung cho MỌI test Python (T3 phần J, 0.156.0): máy chủ không bao giờ dựng engine phán xử thật trong lúc test.
# Từ 0.156.0 mỗi tin nhóm có thể mở một lô phán xử chạy model việc nền; harness đi qua main.py chỉ thay engine của lượt
# nhóm, nên thiếu chốt này thì lô phán xử sẽ dựng model thật. Test cần phán xử tự tiêm engine giả.
import os as _os  # noqa: E402
_os.environ["JAVIS_NO_REAL_JUDGE_ENGINE"] = "1"
_os.environ["JAVIS_NO_REAL_REVIEW_ENGINE"] = "1"
# Lượt nhóm, lượt quét, lượt học (`main._team_engine_for`): test quên thay `team_engine.build` thì dừng, không dựng CLI thật.
_os.environ["JAVIS_NO_REAL_TEAM_ENGINE"] = "1"
# A test that boots the real server must not download a real browser on startup (0.375.0).
_os.environ["JAVIS_SKIP_BROWSER"] = "1"


# ─────────── Thư mục tạm: một thư mục riêng cho mỗi tiến trình test, tự xoá khi thoát ───────────
#
# VÌ SAO (0.281.0): ~460 file test gọi `tempfile.mkdtemp(...)` (nhiều chỗ ngay ở mức module) mà
# không xoá. Mỗi lượt chạy để lại ~1200 thư mục trong %TEMP%, dồn lại tới 50.277 thư mục (~30 GB)
# làm đầy ổ C nhiều lần. Sửa từng chỗ là ~850 chỗ trong ~460 file và test mới lại quên,
# nên sửa MỘT chỗ ở đây: mọi file test đều import `_paths` trước khi đụng tới tempfile, nên chỉ
# cần trỏ thư mục tạm của cả tiến trình vào một thư mục cha riêng rồi xoá nguyên cây lúc thoát.
#
# - Đặt cả `tempfile.tempdir` lẫn env TMP/TEMP/TMPDIR: tiến trình con (server dựng thật, git,
#   node, CLI giả) thừa hưởng env nên file tạm của chúng cũng rơi vào đây.
# - Đã có JAVIS_TEST_TMP (tiến trình con của một test, hoặc tests/run.py tạo sẵn cho từng file)
#   thì DÙNG LẠI, không lồng thêm tầng và không xoá - bên nào tạo ra thì bên đó xoá.
# - atexit chạy cả khi test gọi `sys.exit()` ở mức module. File thoát bằng `os._exit` phải gọi
#   `don_thu_muc_tam()` ngay trước đó.
# - Sót lại (Windows không cho xoá sqlite còn mở lúc atexit, hoặc tiến trình bị giết ngang):
#   lần import sau xoá `jt-<pid>-*` của tiến trình đã chết. tests/run.py thì xoá thư mục của
#   từng file test ngay sau khi tiến trình đó thoát, lúc file đã được nhả.
# - conftest.py trỏ basetemp của pytest vào `<thư mục này>/p` để tmp_path vừa nằm trong đây vừa
#   NGẮN hơn mặc định (bỏ được `pytest-of-<user>/pytest-N/`).
# Tên NGẮN có chủ ý: Windows chưa bật long path thì cả đường dẫn giới hạn 260 ký tự, và
# evidence_store đặt file sâu ~180 ký tự dưới tmp_path của pytest. Thêm một tầng tên dài là
# test phase6/7/9 đỏ vì không ghi được file.
_TAM_TIEN_TO = "jt-"
_TAM_CU_GIAY = 12 * 3600


def xoa_cay(p) -> None:
    """rmtree chịu được file chỉ-đọc (object của git trên Windows). Không xoá được thì bỏ qua:
    file còn bị tiến trình khác giữ sẽ được lần quét sau dọn."""
    def go_chi_doc(ham, duong, _loi):
        try:
            os.chmod(duong, stat.S_IWRITE)
            ham(duong)
        except OSError:
            pass

    # Tiền tố \\?\ cho Windows: có test cố ý dựng đường dẫn quá 260 ký tự (a5 pilot), thiếu nó
    # thì rmtree không xoá được cây đó.
    p = os.path.abspath(p)
    if os.name == "nt" and not p.startswith("\\\\?\\"):
        p = "\\\\?\\" + p
    try:
        if sys.version_info >= (3, 12):
            shutil.rmtree(p, onexc=go_chi_doc)
        else:
            shutil.rmtree(p, onerror=go_chi_doc)
    except OSError:
        pass


def _con_song(pid: int) -> bool:
    """Tiến trình `pid` còn chạy không. Không chắc thì coi là CÒN (để yên, quy tắc 12 giờ lo)."""
    if pid == os.getpid():
        return True
    if os.name == "nt":
        import ctypes
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        h = k32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            return ctypes.get_last_error() == 5  # bị từ chối = tiến trình có thật
        try:
            ma = ctypes.c_ulong()
            if not k32.GetExitCodeProcess(h, ctypes.byref(ma)):
                return True
            return ma.value == 259  # STILL_ACTIVE
        finally:
            k32.CloseHandle(h)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except OSError:
        return True
    return True


def _quet_rac_cu(goc: str) -> None:
    """Dọn `javis-test-<pid>-*` mà atexit của tiến trình đó không xoá hết: trên Windows, sqlite
    còn mở ở biến module lúc atexit chạy nên không xoá được, nhưng tiến trình chết là file nhả.
    Tiến trình đã chết thì xoá ngay; không đọc được pid thì chỉ xoá khi cũ hơn 12 giờ."""
    han = time.time() - _TAM_CU_GIAY
    try:
        ds = list(os.scandir(goc))
    except OSError:
        return
    for e in ds:
        try:
            if not (e.name.startswith(_TAM_TIEN_TO) and e.is_dir(follow_symlinks=False)):
                continue
            pid = e.name[len(_TAM_TIEN_TO):].split("-", 1)[0]
            if pid.isdigit():
                rac = not _con_song(int(pid))
            else:
                rac = e.stat(follow_symlinks=False).st_mtime < han
            if rac:
                xoa_cay(e.path)
        except (OSError, ValueError):
            pass


def _dat_thu_muc_tam():
    p = os.environ.get("JAVIS_TEST_TMP", "")
    cua_minh = not (p and os.path.isdir(p))
    if cua_minh:
        goc = tempfile.gettempdir()
        _quet_rac_cu(goc)
        p = tempfile.mkdtemp(prefix=f"{_TAM_TIEN_TO}{os.getpid()}-", dir=goc)
    for k in ("TMP", "TEMP", "TMPDIR", "JAVIS_TEST_TMP"):
        os.environ[k] = p
    tempfile.tempdir = p
    return p, cua_minh


TEST_TMP, _TAM_CUA_MINH = _dat_thu_muc_tam()


def don_thu_muc_tam() -> None:
    """Xoá thư mục tạm của tiến trình này (nếu chính nó tạo ra). atexit tự gọi."""
    if _TAM_CUA_MINH:
        xoa_cay(TEST_TMP)


atexit.register(don_thu_muc_tam)


def moi_route(app):
    """Mọi route của app, ĐI ĐỆ QUY qua các router con. Trả danh sách đối tượng route.

    VÌ SAO KHÔNG ĐỌC THẲNG `app.routes` (0.59.19): fastapi 0.115 gộp route của
    `include_router` thẳng vào `app.routes`, nhưng fastapi 0.141 BỌC mỗi lần include thành
    một đối tượng `_IncludedRouter` và giữ route con trong `.original_router.routes`. Đối
    tượng bọc đó KHÔNG có `.path`, nên code cũ hoặc nổ AttributeError (test_cli_kenh) hoặc
    im lặng không thấy 67 endpoint (test_jobs, test_route_table) - kiểu thứ hai tệ hơn, vì
    một phép thử "endpoint này phải còn" sẽ đỏ oan, còn phép thử "endpoint này phải mất" thì
    xanh oan.
    """
    ra, da_di = [], set()

    def di(routes):
        for r in routes:
            ra.append(r)
            con = getattr(r, "routes", None)
            if not con:
                con = getattr(getattr(r, "original_router", None), "routes", None)
            if con and id(r) not in da_di:
                da_di.add(id(r))
                di(con)

    di(getattr(app, "routes", []) or [])
    return ra


def moi_duong_dan(app):
    """Tập hợp đường dẫn của mọi route, đi đệ quy. Xem moi_route()."""
    return {getattr(r, "path", "") for r in moi_route(app)}
