"""Công cụ TUỲ CHỌN: thứ Javis dùng được nhưng không nhét sẵn vào bản cài.

Vì sao có tầng này
------------------
Trình duyệt để Javis tự kiểm thử giao diện nặng cả trăm MB, mà phần lớn người dùng Javis không
lập trình và không bao giờ cần tới. Nhét sẵn vào ảnh Docker là bắt tất cả mọi người trả tiền
băng thông và ổ đĩa cho một tính năng của thiểu số, mỗi lần cập nhật một lần. Bỏ hẳn thì người
cần lại không có đường nào lấy.

Đường thứ ba, mượn đúng cách Hermes Agent làm (`--skip-browser`, `--ensure browser`): một DANH
SÁCH CÓ TÊN các công cụ tuỳ chọn, bỏ qua lúc đầu được, cài bổ sung sau bằng một nút bấm.

Ranh giới không lách được
-------------------------
Trong Docker, Javis chạy bằng user `javis` (uid 10001), mã nguồn để chỉ đọc. Nên phần nào cần
`apt-get` thì PHẢI nằm sẵn trong ảnh (Dockerfile lo, xem lớp WITH_BROWSER_DEPS); ở đây chỉ làm
được phần tải về thư mục ghi được. Chia đúng như vậy thì ảnh chỉ nặng thêm phần thư viện, còn
bản thân trình duyệt chỉ tải khi có người bấm.

Tải vào `STATE_DIR/browsers` chứ không vào cache mặc định của người dùng: STATE_DIR nằm trên ổ
gắn ngoài, nên bản tải về SỐNG QUA mỗi lần cập nhật. Để trong `~/.cache` thì cứ dựng lại
container là mất, và người dùng phải tải lại cả trăm MB mà không hiểu vì sao.
"""
from __future__ import annotations

import asyncio
import os
import platform
import shutil
import sys
import time
from pathlib import Path


import winproc
from config import STATE_DIR

# Nơi tải trình duyệt về. Playwright đọc biến môi trường này cho cả lúc tải lẫn lúc chạy, nên
# connector Playwright phải được truyền ĐÚNG biến này thì mới tìm thấy bản đã tải.
BROWSERS_DIR = STATE_DIR / "browsers"
ENV_BROWSERS_PATH = "PLAYWRIGHT_BROWSERS_PATH"

# Nơi cài thư viện Python tuỳ chọn. CÙNG lý do với BROWSERS_DIR, cộng một lý do nặng hơn: trong
# Docker, `site-packages` thuộc root và chỉ đọc, còn Javis chạy bằng user `javis`. Nên `pip
# install` kiểu thường KHÔNG ghi được, và không có nút nào cứu được điều đó. `pip install
# --target` vào thư mục state thì ghi được, sống qua mỗi lần cập nhật (state nằm trên ổ gắn
# ngoài), và gỡ chỉ là xoá một thư mục.
PYLIBS_DIR = STATE_DIR / "pylibs"

# Trần thời gian cài thư viện. Ngắn hơn tải trình duyệt vì đây chỉ là tải wheel từ PyPI.
CAI_LIB_TIMEOUT = 600.0

# Trần thời gian tải. Mạng VPS chậm vẫn phải xong trong chừng này, còn treo lâu hơn là hỏng
# thật chứ không phải chậm - và treo im vô hạn là kiểu lỗi tệ nhất (không kết quả, không lỗi).
TAI_TIMEOUT = 900.0

_LOG_TRAN = 4000          # giữ bao nhiêu ký tự log cuối để hiện trên màn hình
_viec: dict = {}          # id công cụ -> trạng thái lần cài đang chạy
_TASKS: set = set()       # giữ ref mạnh, không để bộ gom rác nuốt task đang tải


def _mo_ta_trinh_duyet() -> dict:
    return {
        "id": "browser",
        "ten": "Trình duyệt (Chromium)",
        "mo_ta": "Cho Javis tự mở trang, chụp màn hình và kiểm thử giao diện sau khi sửa code. "
                 "Cần cho kết nối Playwright.",
        "dung_luong_uoc": "khoảng 100 MB",
    }


def _mo_ta_pylib() -> dict:
    return {
        "id": "pylib-playwright",
        "ten": "Thư viện lái trình duyệt (playwright)",
        "mo_ta": "Cần cho model ChatGPT Web: Javis gõ vào một phiên ChatGPT thật trong trình "
                 "duyệt thay vì gọi API. Chưa cài thì model đó không hiện trong ô chọn model.",
        "dung_luong_uoc": "khoảng 140 MB",
    }


CONG_CU = {"browser": _mo_ta_trinh_duyet, "pylib-playwright": _mo_ta_pylib}


# ─────────────────────────── dò xem đã có gì chưa ───────────────────────────

def _chrome_he_thong() -> str:
    """Đường dẫn Google Chrome / Edge có sẵn trên máy, rỗng nếu không có.

    Máy cá nhân (Windows, macOS) gần như luôn có sẵn Chrome, và Playwright lái được nó qua
    `channel: chrome` mà KHÔNG phải tải gì. Máy chủ Linux thì gần như không bao giờ có. Dò
    trước khi mời tải là để người dùng máy cá nhân không phải tải thừa cả trăm MB.
    """
    he = platform.system().lower()
    ung_vien = []
    if he == "windows":
        for goc in (os.getenv("PROGRAMFILES"), os.getenv("PROGRAMFILES(X86)"),
                    os.getenv("LOCALAPPDATA")):
            if goc:
                ung_vien += [Path(goc) / "Google/Chrome/Application/chrome.exe",
                             Path(goc) / "Microsoft/Edge/Application/msedge.exe"]
    elif he == "darwin":
        ung_vien = [Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
                    Path("/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge")]
    else:
        for ten in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "microsoft-edge"):
            p = shutil.which(ten)
            if p:
                return p
        return ""
    for p in ung_vien:
        try:
            if p.is_file():
                return str(p)
        except OSError:
            pass
    return ""


def _da_tai() -> str:
    """Thư mục bản Chromium Javis đã tải, rỗng nếu chưa có."""
    try:
        for d in BROWSERS_DIR.iterdir():
            if d.is_dir() and d.name.startswith(("chromium", "chromium_headless_shell")):
                return str(d)
    except OSError:
        pass
    return ""


def _da_cai_pylib() -> str:
    """Thư mục thư viện playwright Javis đã cài, rỗng nếu chưa có."""
    try:
        if (PYLIBS_DIR / "playwright").is_dir():
            return str(PYLIBS_DIR)
    except OSError:
        pass
    return ""


def nap_pylibs() -> bool:
    """Đưa thư mục thư viện tự cài vào `sys.path`. Gọi TRƯỚC khi `import playwright`.

    Không có bước này thì cài xong vẫn không import được, và người dùng thấy nút bấm báo xong
    mà tính năng vẫn bảo thiếu thư viện - kiểu hỏng khó chịu nhất vì không ai đoán ra.

    Chèn vào CUỐI `sys.path` chứ không phải đầu: bản nào đã có sẵn trong Python của máy phải
    thắng bản Javis tự tải, kẻo một ngày hai bản lệch phiên bản và cái Javis tải đè lên cái
    người dùng chủ động cài.
    """
    d = _da_cai_pylib()
    if not d:
        return False
    if d not in sys.path:
        sys.path.append(d)
    return True


def co_playwright() -> bool:
    """Máy này import được `playwright` không, sau khi đã nạp thư mục tự cài."""
    nap_pylibs()
    try:
        import importlib.util
        return importlib.util.find_spec("playwright") is not None
    except Exception:
        return False


def _dung_luong(p: Path) -> int:
    tong = 0
    try:
        for goc, _thu_muc, tep in os.walk(p):
            for t in tep:
                try:
                    tong += os.path.getsize(os.path.join(goc, t))
                except OSError:
                    pass
    except OSError:
        pass
    return tong


def doc_mb(so_byte: int) -> str:
    return f"{so_byte / 1024 / 1024:.0f} MB" if so_byte else ""


def _trang_thai_browser(d: dict, viec: dict) -> dict:
    dang_chay = bool(viec.get("dang_chay"))
    tai_ve = _da_tai()
    he_thong = "" if tai_ve else _chrome_he_thong()
    if dang_chay:
        tt, ly_do = "dang_cai", "Đang tải trình duyệt về, việc này mất vài phút."
    elif tai_ve:
        tt, ly_do = "san_sang", "Javis đã tải sẵn một bản Chromium riêng."
    elif he_thong:
        tt, ly_do = "san_sang", f"Dùng trình duyệt có sẵn trên máy: {he_thong}"
    else:
        tt, ly_do = "chua_cai", "Máy này chưa có trình duyệt nào Javis lái được."
    d.update({
        "trang_thai": tt, "ly_do": ly_do,
        "go_duoc": bool(tai_ve),           # chỉ gỡ được thứ CHÍNH JAVIS tải về
        "duong_dan": tai_ve or he_thong,
        "dung_luong": doc_mb(_dung_luong(Path(tai_ve))) if tai_ve else "",
    })
    return d


def _trang_thai_pylib(d: dict, viec: dict) -> dict:
    dang_chay = bool(viec.get("dang_chay"))
    tu_cai = _da_cai_pylib()
    if dang_chay:
        tt, ly_do = "dang_cai", "Đang tải thư viện từ PyPI, việc này mất một hai phút."
    elif tu_cai:
        tt, ly_do = "san_sang", "Javis đã cài vào thư mục state, sống qua mỗi lần cập nhật."
    elif co_playwright():
        tt, ly_do = "san_sang", "Python của máy này đã có sẵn thư viện."
    else:
        tt, ly_do = "chua_cai", ("Chưa có thư viện. Cài xong phải KHỞI ĐỘNG LẠI Javis thì "
                                 "model ChatGPT Web mới hiện ra.")
    d.update({
        "trang_thai": tt, "ly_do": ly_do,
        "go_duoc": bool(tu_cai),           # chỉ gỡ thứ CHÍNH JAVIS cài, không đụng Python của máy
        "duong_dan": tu_cai,
        "dung_luong": doc_mb(_dung_luong(PYLIBS_DIR)) if tu_cai else "",
    })
    return d


def trang_thai(cong_cu: str = "browser") -> dict:
    """Trạng thái một công cụ tuỳ chọn, đủ để vẽ thẻ trên màn hình."""
    if cong_cu not in CONG_CU:
        return {"ok": False, "error": f"không có công cụ tên {cong_cu!r}"}
    d = dict(CONG_CU[cong_cu]())
    viec = _viec.get(cong_cu) or {}
    d["ok"] = True
    d = (_trang_thai_pylib if cong_cu == "pylib-playwright" else _trang_thai_browser)(d, viec)
    d.update({
        "tien_do": viec.get("tien_do", ""),
        "log": viec.get("log", ""),
        "loi": viec.get("loi", ""),
    })
    return d


def danh_sach() -> list:
    return [trang_thai(k) for k in CONG_CU]


# ─────────────────────────── cài và gỡ ───────────────────────────

def _ghi_log(cong_cu: str, dong: str) -> None:
    v = _viec.setdefault(cong_cu, {})
    v["log"] = ((v.get("log", "") + dong)[-_LOG_TRAN:])
    # Dòng tiến độ của Playwright có dạng "Downloading Chromium 141.0 (playwright build v1243)"
    # hoặc "|████ | 45% of 158.2 MiB". Lấy dòng cuối có chữ để hiện cho người dùng.
    for d in reversed(dong.splitlines()):
        if d.strip():
            v["tien_do"] = d.strip()[:160]
            break


def _lenh_cai(cong_cu: str) -> tuple:
    """(lệnh, thư mục chạy, env, trần giờ, câu lỗi khi không tìm thấy chương trình).

    Gom ở đây để `_chay_tai` chỉ còn phần CHẠY: đọc log, đếm giờ, ghi trạng thái. Thêm công cụ
    thứ ba sau này chỉ phải viết thêm một nhánh ở đây.
    """
    if cong_cu == "pylib-playwright":
        PYLIBS_DIR.mkdir(parents=True, exist_ok=True)
        # `--target`: cài vào thư mục ghi được thay vì site-packages. Trong Docker,
        # site-packages thuộc root và chỉ đọc còn Javis chạy user thường, nên đây KHÔNG phải
        # lựa chọn phong cách mà là đường duy nhất chạy được.
        # `--upgrade`: cài đè lên bản cũ trong cùng thư mục, nếu không pip bỏ qua và người
        # dùng bấm "Cài lại" mà chẳng có gì đổi.
        return (
            [sys.executable, "-m", "pip", "install", "--no-cache-dir", "--upgrade",
             "--target", str(PYLIBS_DIR), "playwright"],
            str(PYLIBS_DIR), dict(os.environ), CAI_LIB_TIMEOUT,
            "Python của máy này không gọi được pip, nên không cài được thư viện.",
        )
    BROWSERS_DIR.mkdir(parents=True, exist_ok=True)
    moi_truong = dict(os.environ)
    moi_truong[ENV_BROWSERS_PATH] = str(BROWSERS_DIR)
    # `--only-shell`: chỉ tải bản headless shell, nhỏ hơn hẳn bản đầy đủ. Javis chạy ẩn cửa sổ
    # nên không cần phần giao diện của trình duyệt.
    return (
        ["npx", "-y", "playwright@latest", "install", "--only-shell", "chromium"],
        str(BROWSERS_DIR), moi_truong, TAI_TIMEOUT,
        "Máy này không có Node (npx), không tải được trình duyệt.",
    )


async def _chay_tai(cong_cu: str) -> None:
    """Cài một công cụ tuỳ chọn. Chạy nền, mọi đường ra đều ghi lại trạng thái."""
    v = _viec.setdefault(cong_cu, {})
    v.update({"dang_chay": True, "loi": "", "log": "", "tien_do": "Đang chuẩn bị...", "bat_dau": time.time()})
    lenh, thu_muc, moi_truong, tran_gio, loi_thieu = _lenh_cai(cong_cu)
    try:
        tt = await asyncio.create_subprocess_exec(
            *lenh, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
            env=moi_truong, cwd=thu_muc, **winproc.kwargs_no_window())
    except FileNotFoundError:
        v.update({"dang_chay": False, "loi": loi_thieu})
        return
    except Exception as e:
        v.update({"dang_chay": False, "loi": f"{type(e).__name__}: {e}"})
        return

    async def _doc():
        while True:
            khuc = await tt.stdout.read(4096)
            if not khuc:
                break
            _ghi_log(cong_cu, khuc.decode("utf-8", "replace"))

    try:
        await asyncio.wait_for(asyncio.gather(_doc(), tt.wait()), timeout=tran_gio)
        ma = tt.returncode
    except asyncio.TimeoutError:
        try:
            tt.kill()
        except Exception:
            pass
        v.update({"dang_chay": False,
                  "loi": f"Chạy quá {int(tran_gio // 60)} phút chưa xong nên đã dừng. Thử lại khi mạng rảnh hơn."})
        return
    except asyncio.CancelledError:
        try:
            tt.kill()
        except Exception:
            pass
        v.update({"dang_chay": False, "loi": "Đã dừng giữa chừng."})
        raise
    except Exception as e:
        v.update({"dang_chay": False, "loi": f"{type(e).__name__}: {e}"})
        return

    v["dang_chay"] = False
    xong = _da_cai_pylib() if cong_cu == "pylib-playwright" else _da_tai()
    if ma != 0:
        v["loi"] = f"Lệnh cài trả mã lỗi {ma}. Xem log bên dưới."
    elif not xong:
        v["loi"] = "Lệnh chạy xong nhưng không thấy thứ vừa cài đâu."
    elif cong_cu == "pylib-playwright":
        nap_pylibs()
        v["tien_do"] = "Xong. Khởi động lại Javis để model ChatGPT Web hiện ra."
    else:
        v["tien_do"] = "Xong."
    print(f"[cong-cu] tải {cong_cu}: mã {ma}, lỗi={v.get('loi') or 'không'}", file=sys.stderr)


def bat_dau_cai(cong_cu: str = "browser") -> dict:
    """Khởi động việc tải ở NỀN rồi trả về ngay. Màn hình hỏi tiến độ qua `trang_thai`."""
    if cong_cu not in CONG_CU:
        return {"ok": False, "error": f"không có công cụ tên {cong_cu!r}"}
    if (_viec.get(cong_cu) or {}).get("dang_chay"):
        return {"ok": True, "dang_chay": True, "note": "đang tải rồi"}
    t = asyncio.get_event_loop().create_task(_chay_tai(cong_cu))
    _TASKS.add(t)
    t.add_done_callback(_TASKS.discard)
    return {"ok": True, "dang_chay": True}


def go(cong_cu: str = "browser") -> dict:
    """Xoá bản Javis tự tải. KHÔNG bao giờ đụng tới trình duyệt có sẵn của máy."""
    if cong_cu not in CONG_CU:
        return {"ok": False, "error": f"không có công cụ tên {cong_cu!r}"}
    goc = PYLIBS_DIR if cong_cu == "pylib-playwright" else BROWSERS_DIR
    d = _da_cai_pylib() if cong_cu == "pylib-playwright" else _da_tai()
    if not d:
        return {"ok": False, "error": "Không có bản nào do Javis cài để gỡ."}
    try:
        shutil.rmtree(goc, ignore_errors=True)
        _viec.pop(cong_cu, None)
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


def env_cho_connector() -> dict:
    """Biến môi trường phải truyền cho tiến trình Playwright MCP để nó thấy bản đã tải."""
    return {ENV_BROWSERS_PATH: str(BROWSERS_DIR)} if _da_tai() else {}


def env_playwright() -> dict:
    """Toàn bộ biến môi trường một tiến trình Playwright MCP cần trên MÁY NÀY.

    Gom ở đây để hiểu biết riêng về Playwright nằm đúng MỘT chỗ: `mcp_store` chỉ việc hỏi chứ
    không phải tự biết tên biến của một connector cụ thể. Người dùng đã tự chọn trình duyệt
    trong form thì giá trị đó đã nằm sẵn trong env và `setdefault` bên kia không đè lên.
    """
    e = dict(env_cho_connector())
    e["PLAYWRIGHT_MCP_BROWSER"] = trinh_duyet_mac_dinh()
    return e


def trinh_duyet_mac_dinh() -> str:
    """Giá trị `browser` hợp lý cho connector Playwright trên máy này.

    Máy cá nhân có Chrome thì dùng luôn Chrome (không phải tải gì). Máy chủ Linux thì phải là
    `chromium` - bản Javis tải về. Đặt sai chỗ này là connector đi tìm Google Chrome trên một
    container Debian và chết với câu lỗi không ai đoán ra.
    """
    if _da_tai():
        return "chromium"
    return "chrome" if _chrome_he_thong() else "chromium"
