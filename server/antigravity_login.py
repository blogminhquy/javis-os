"""Đăng nhập Google cho Antigravity CLI NGAY TRÊN DASHBOARD, không phải mở terminal.

Vì sao phải có một module riêng thay vì bắc cầu token như Gemini CLI
--------------------------------------------------------------------
Với Gemini CLI, Javis tự chạy vòng OAuth rồi GHI thẳng `~/.gemini/oauth_creds.json` cho CLI
đọc (xem `gemini_oauth.py`). Ở đây KHÔNG làm được: `agy` cất phiên trong **keyring của hệ điều
hành**, không có file nào để ghi vào, và định dạng thì đóng.

Nên đổi cách: thay vì tự đăng nhập hộ, Javis **lái chính luồng đăng nhập của CLI** rồi làm
người đưa thư giữa nó và trình duyệt của người dùng. Luồng của `agy` khi không có màn hình
(tài liệu chính chủ + trải nghiệm thực tế của người dùng SSH):

1. Chạy `agy`, chưa có phiên -> nó nhận ra đang ở xa, IN RA một link authorize.
2. Người dùng mở link trên máy mình, đăng nhập Google, Google hiện ra MỘT MÃ.
3. Dán mã đó lại vào terminal -> CLI đổi mã lấy token, cất vào keyring.

Javis chen vào giữa bước 1 và 3: bắt cái link đưa lên dashboard, nhận mã người dùng dán vào ô
rồi bơm ngược xuống tiến trình. Kết quả là đúng trải nghiệm của Claude Code và Gemini CLI đang
có, mà không cần Javis cầm token của ai.

**PHẢI dùng PTY, không phải ống dẫn thường.** `agy` là giao diện bàn phím: không thấy terminal
thật thì nó đổi hành vi hoặc không chịu chạy. Kèm theo một cái lợi bất ngờ: vì Javis là bên
CẤP terminal, nó tự đặt luôn chiều rộng. Bản CLI hiện tại có lỗi đã biết là link authorize bị
xuống dòng theo bề rộng terminal, chèn dấu cách và ký tự xuống dòng vào GIỮA URL rồi người
dùng dán sang trình duyệt là hỏng (issue #315 của google-antigravity/antigravity-cli). Đặt bề
rộng thật lớn là lỗi đó không xảy ra ngay từ đầu, và còn một lớp nữa dọn khoảng trắng sót.

Chỉ chạy trên Linux/macOS: `pty` là module riêng của Unix. Windows lui về hướng dẫn gõ tay -
nói thẳng chứ không dựng một cái nút chết.
"""
from __future__ import annotations

import os
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
from typing import Optional

# Bề rộng terminal giả. To quá mức cần thiết là CỐ Ý: link authorize của Google dài vài trăm ký
# tự, mà CLI ngắt dòng theo bề rộng rồi chèn xuống dòng vào giữa URL.
_COLS = 1000
_ROWS = 50

# Đọc tối đa bấy nhiêu giây để chờ link hiện ra. Lần chạy đầu `agy` còn dựng cấu hình nên chậm.
_CHO_LINK = 60.0
# Sau khi dán mã, chờ CLI đổi mã lấy token.
_CHO_XONG = 90.0

_ANSI_RE = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")

# Một phiên đăng nhập đang dang dở. Mỗi máy một cái là đủ: đây là thao tác của chủ máy.
_phien: dict = {}
_khoa = threading.Lock()


def kha_dung() -> tuple[bool, str]:
    """Máy này đăng nhập trên dashboard được không, kèm lý do nếu không."""
    if os.name == "nt":
        return False, ("Đăng nhập trên dashboard chỉ chạy trên Linux/macOS (Windows không có "
                       "pseudo-terminal). Trên Windows mở PowerShell gõ `agy` một lần.")
    try:
        import pty  # noqa: F401
    except Exception:
        return False, "Máy chủ không có module `pty` nên phải đăng nhập bằng terminal."
    return True, ""


def _sach(s: str) -> str:
    """Bỏ mã màu ANSI và chuẩn hoá ký tự xuống dòng để còn dò được URL trong đống vẽ giao diện.

    `\\r\\n` phải gộp thành MỘT `\\n` trước khi xử `\\r` lẻ. Terminal bật ONLCR nên mỗi `\\n`
    tiến trình con ghi ra đều thành `\\r\\n`; đổi thẳng `\\r` sang `\\n` là mỗi dòng đẻ thêm một
    dòng TRỐNG ở giữa - mà dòng trống lại đúng là dấu hiệu `tim_url()` dùng để biết URL đã hết,
    nên link bị cắt cụt ngay mẩu đầu. Đã gặp thật lúc dựng, test canh đúng ca này.
    """
    return _ANSI_RE.sub("", s).replace("\r\n", "\n").replace("\r", "\n")


# Ký tự hợp lệ trong URL. Dùng để nhận ra một dòng có phải là PHẦN NỐI của URL bị ngắt hay không.
_URL_CHARS = re.compile(r"^[A-Za-z0-9\-._~:/?#\[\]@!$&'()*+,;=%]+$")
# Ký tự vẽ khung mà giao diện `agy` bọc quanh mỗi dòng.
_KHUNG = "│|┃┆┊║ \t"


def _don_url(u: str) -> str:
    """Cắt đuôi rác mà khung viền giao diện để lại.

    Dán một URL thừa ký tự sang Google là nó báo invalid_request rồi người dùng ngồi đoán mã
    mình chép sai, nên dọn ở đây.
    """
    u = re.sub(r"\s+", "", u)
    return u.rstrip("'\"`)]}>.,\\|-│")


def tim_url(log: str) -> str:
    """Moi link authorize ra khỏi đống chữ CLI vẽ, GỘP LẠI nếu nó bị ngắt dòng.

    Vì sao không chỉ dùng một regex: `\\S+` dừng ngay ở ký tự xuống dòng, nên URL bị ngắt dòng
    sẽ về một mẩu cụt trông vẫn "hợp lệ" - đúng kiểu lỗi tệ nhất, người dùng dán sang Google
    rồi nhận invalid_request mà không hiểu vì sao.

    Bề rộng 1000 cột đã chặn gần hết chuyện ngắt dòng, nhưng bản CLI nào tự ngắt theo bề rộng
    của riêng nó thì vẫn dính (issue #315), nên đây là lớp thứ hai.

    Luật nối: một dòng chỉ được coi là phần đuôi của URL khi nó KHÔNG rỗng, KHÔNG có khoảng
    trắng ở giữa, và mọi ký tự đều hợp lệ trong URL. Câu văn thường luôn có khoảng trắng giữa
    các từ nên tự nó chặn, không lo nuốt nhầm dòng chữ phía sau.
    """
    dong = [d.strip(_KHUNG) for d in _sach(log or "").split("\n")]
    for i, d in enumerate(dong):
        vt = d.find("https://")
        if vt < 0:
            continue
        dau = d[vt:]
        m = re.match(r"[A-Za-z0-9\-._~:/?#\[\]@!$&'()*+,;=%]+", dau)
        if not m:
            continue
        url = m.group(0)
        for sau in dong[i + 1:]:
            if not sau or not _URL_CHARS.match(sau):
                break
            url += sau
        url = _don_url(url)
        if "accounts.google.com" in url:
            return url
    return ""


# --------------------------------------------------------------------------
# Tự trả lời menu chọn cách đăng nhập
#
# Chủ repo gửi ảnh 2026-08-13: `agy` chưa đăng nhập thì việc ĐẦU TIÊN nó làm KHÔNG phải in link,
# mà là hỏi:
#
#     Welcome to the Antigravity CLI. You are currently not signed in.
#     Select login method:
#     > 1. Google OAuth
#       2. Use a Google Cloud project
#     [Use arrow keys to navigate, Enter to select]
#
# Bản trước ngồi chờ một cái link không bao giờ tới, rồi hết giờ. (Đường lui "hiện nguyên văn
# thứ CLI in ra" chính là thứ chỉ ra chuyện này - giữ nó là đúng.)
#
# Nên Javis phải bấm hộ. KHÔNG bấm Enter mù: dấu `>` có thể đang đứng ở dòng khác, và mục thứ
# hai là "Google Cloud project" - chọn nhầm là người dùng rơi vào luồng doanh nghiệp đòi
# project ID. Đọc xem con trỏ đang ở mục nào, đếm số bước tới mục OAuth, đi đúng bấy nhiêu
# phím mũi tên rồi mới Enter.
_MENU_RE = re.compile(r"select\s+login\s+method", re.I)
_MUC_RE = re.compile(r"^(?P<con_tro>[>❯›»*]?)\s*(?P<so>\d+)[.)]\s+(?P<ten>.+?)\s*$", re.M)
_XUONG = b"\x1b[B"
_LEN = b"\x1b[A"


def _phim_cho_menu(sach: str):
    """Cần bấm phím gì cho menu đang hiện. None = chưa thấy menu nào cần trả lời.

    `sach` là log ĐÃ bỏ mã màu. Chỉ đọc phần CUỐI vì giao diện vẽ lại cả màn mỗi lần con trỏ
    nhích - phần đầu log là những khung đã cũ, đọc nhầm vào đó là đếm sai vị trí con trỏ.
    """
    if not _MENU_RE.search(sach):
        return None
    khuc = sach[sach.lower().rindex("select login method"):]
    muc = list(_MUC_RE.finditer(khuc))
    if not muc:
        return None
    hien_tai = dich = None
    for i, m in enumerate(muc):
        if m.group("con_tro"):
            hien_tai = i
        ten = m.group("ten").lower()
        # "Google OAuth" là đường cá nhân. Loại thẳng mục nhắc tới cloud/project/enterprise:
        # đó là luồng doanh nghiệp, chọn vào là đòi project ID rồi tắc.
        if "oauth" in ten and not any(k in ten for k in ("cloud", "project", "enterprise")):
            dich = i
    if dich is None:
        return None
    if hien_tai is None:
        hien_tai = 0        # chưa thấy con trỏ: menu mặc định luôn đứng ở mục đầu
    if dich == hien_tai:
        return b"\r"
    buoc = abs(dich - hien_tai)
    return (_XUONG if dich > hien_tai else _LEN) * buoc + b"\r"


def _dong_phien(p: dict):
    try:
        if p.get("proc") and p["proc"].poll() is None:
            p["proc"].send_signal(signal.SIGTERM)
            time.sleep(0.2)
            if p["proc"].poll() is None:
                p["proc"].kill()
    except Exception:
        pass
    for k in ("master", "slave"):
        try:
            if p.get(k) is not None:
                os.close(p[k])
        except Exception:
            pass
    p.clear()


def huy():
    """Bỏ phiên đăng nhập đang dang dở (người dùng bấm huỷ, hoặc bắt đầu lại từ đầu)."""
    with _khoa:
        if _phien:
            _dong_phien(_phien)


def _lenh_dang_nhap(cli: str) -> list[str]:
    """Lệnh nào bật luồng đăng nhập.

    Hỏi `--help` trước rồi mới quyết, cùng kỷ luật với `antigravity_cli.py`: bản nào có
    subcommand `login` thì dùng nó cho gọn (không vào cả giao diện chat), bản không có thì chạy
    `agy` trần - chưa có phiên là nó tự vào đăng nhập.
    """
    try:
        import antigravity_cli
        if antigravity_cli.co_co(" login", "\nlogin", "agy login"):
            return [cli, "login"]
    except Exception:
        pass
    return [cli]


def bat_dau(timeout: float = _CHO_LINK) -> dict:
    """Mở tiến trình `agy` trong một terminal giả và chờ nó in ra link authorize.

    Trả {ok, url, log} hoặc {ok: False, error, log}. `log` là phần CLI đã in ra, giữ lại để khi
    luồng đổi (Google hay đổi) người dùng còn nhìn thấy thứ thật nó nói chứ không phải một câu
    "lỗi không rõ" của Javis.
    """
    duoc, vi_sao = kha_dung()
    if not duoc:
        return {"ok": False, "error": vi_sao}
    import antigravity_cli
    cli = antigravity_cli.find_antigravity_cli()
    if not cli:
        return {"ok": False,
                "error": f"Chưa cài Antigravity CLI. Cài một lần: {antigravity_cli.lenh_cai()}"}

    import fcntl
    import pty
    import struct
    import termios

    huy()   # bấm lại lần nữa thì bỏ phiên cũ, đừng để hai tiến trình cùng chờ
    master, slave = pty.openpty()
    try:
        fcntl.ioctl(master, termios.TIOCSWINSZ, struct.pack("HHHH", _ROWS, _COLS, 0, 0))
    except Exception:
        pass

    moi_truong = dict(os.environ)
    # Nói thẳng đây là phiên từ xa: `agy` dựa vào đó để chọn lối in-link thay vì mở trình duyệt
    # trên máy chủ (mở ra cũng không ai thấy). Đặt sẵn còn hơn để nó tự đoán.
    moi_truong.setdefault("SSH_CONNECTION", "127.0.0.1 0 127.0.0.1 22")
    moi_truong.setdefault("SSH_TTY", "/dev/pts/javis")
    moi_truong["COLUMNS"] = str(_COLS)
    moi_truong["LINES"] = str(_ROWS)
    moi_truong["TERM"] = "xterm-256color"
    moi_truong.pop("BROWSER", None)

    try:
        proc = subprocess.Popen(
            _lenh_dang_nhap(cli), stdin=slave, stdout=slave, stderr=slave,
            env=moi_truong, cwd=os.path.expanduser("~"), start_new_session=True)
    except Exception as e:
        os.close(master)
        os.close(slave)
        return {"ok": False, "error": f"Không chạy được `agy`: {type(e).__name__}: {e}"}

    p = {"proc": proc, "master": master, "slave": slave, "log": "", "ts": time.time()}
    with _khoa:
        _phien.clear()
        _phien.update(p)

    url = ""
    het = time.time() + timeout
    da_tra_loi = 0          # số menu đã bấm hộ
    menu_cu = ""            # chữ ký menu vừa trả lời, để không bấm đi bấm lại cùng một cái
    while time.time() < het:
        them = _doc(master, 0.4)
        if them:
            p["log"] = (p["log"] + them)[-20000:]
        sach = _sach(p["log"])
        url = tim_url(p["log"])
        if url:
            break
        # Chặn trên 3 lần là cố ý: gặp một màn hỏi lạ mà cứ bấm bừa thì tệ hơn hẳn dừng lại rồi
        # đưa nguyên văn cho người dùng đọc.
        if da_tra_loi < 3:
            phim = _phim_cho_menu(sach)
            if phim:
                chu_ky = sach[-400:]
                if chu_ky != menu_cu:
                    try:
                        os.write(master, phim)
                        da_tra_loi += 1
                        menu_cu = chu_ky
                        time.sleep(0.4)   # để CLI kịp vẽ lại trước khi mình đọc tiếp
                    except Exception:
                        pass
        if proc.poll() is not None:
            break

    log_sach = _sach(p["log"]).strip()
    if url:
        return {"ok": True, "url": url, "log": log_sach[-1500:]}
    with _khoa:
        _dong_phien(_phien)
    if "already" in log_sach.lower() or "signed in" in log_sach.lower():
        return {"ok": False, "error": "Có vẻ máy đã đăng nhập sẵn. Bấm Kiểm tra lại.",
                "log": log_sach[-1500:]}
    return {"ok": False,
            "error": "Không thấy link đăng nhập trong thứ CLI in ra. Bản `agy` này có thể đổi "
                     "luồng đăng nhập - xem phần dưới rồi làm tay bằng lệnh `agy`.",
            "log": log_sach[-1500:]}


def _doc(fd: int, cho: float) -> str:
    """Đọc thứ đang có trong terminal giả, tối đa `cho` giây. Không có gì thì trả rỗng."""
    import select
    ra = []
    het = time.time() + cho
    while time.time() < het:
        try:
            r, _, _ = select.select([fd], [], [], max(0.05, het - time.time()))
        except Exception:
            break
        if not r:
            break
        try:
            b = os.read(fd, 65536)
        except OSError:
            break
        if not b:
            break
        ra.append(b.decode("utf-8", "replace"))
    return "".join(ra)


def gui_ma(ma: str, timeout: float = _CHO_XONG) -> dict:
    """Bơm mã Google vừa cấp xuống tiến trình `agy`, rồi xác nhận đăng nhập đã ăn.

    Không tin lời CLI in ra để kết luận thành công: giao diện của nó vẽ đủ thứ và câu chữ đổi
    theo bản. Thay vào đó hỏi lại `antigravity_cli.auth_status()` - nó liệt kê model được thì
    nghĩa là tài khoản thật sự dùng được, đó mới là thứ người dùng cần.
    """
    ma = (ma or "").strip()
    if not ma:
        return {"ok": False, "error": "Chưa dán mã."}
    with _khoa:
        p = dict(_phien)
    if not p or not p.get("proc") or p["proc"].poll() is not None:
        return {"ok": False, "error": "Phiên đăng nhập đã hết hạn. Bấm Đăng nhập Google lại."}
    try:
        os.write(p["master"], (ma + "\n").encode("utf-8"))
    except Exception as e:
        return {"ok": False, "error": f"Không gửi được mã: {type(e).__name__}: {e}"}

    import antigravity_cli

    def _da_xong() -> bool:
        antigravity_cli._AUTH_CACHE.update(ts=0.0, val=None)
        try:
            return bool(antigravity_cli.auth_status(bo_qua_cache=True).get("connected"))
        except Exception:
            return False

    het = time.time() + timeout
    log = p.get("log", "")
    while time.time() < het:
        them = _doc(p["master"], 1.0)
        if them:
            log = (log + them)[-20000:]
            with _khoa:
                if _phien:
                    _phien["log"] = log
        if _da_xong():
            huy()
            return {"ok": True}
        if p["proc"].poll() is not None:
            # Tiến trình thoát là chuyện BÌNH THƯỜNG ở đây: đăng nhập xong thì `agy` kết thúc.
            # Bỏ cuộc ngay lúc này là bug đã gặp thật lúc dựng - lượt hỏi cuối rơi đúng vào
            # trước khi token kịp ghi vào keyring, nên báo thất bại trong khi đã thành công.
            # Cho thêm một nhịp ngắn rồi mới kết luận.
            for _ in range(6):
                if _da_xong():
                    huy()
                    return {"ok": True}
                time.sleep(0.8)
            break
    sach = _sach(log).strip()
    huy()
    if any(k in sach.lower() for k in ("invalid", "expired", "denied", "failed")):
        return {"ok": False,
                "error": "Google từ chối mã đó (sai, hết hạn, hoặc đã dùng rồi). Bấm Đăng nhập "
                         "Google để lấy link mới.", "log": sach[-1200:]}
    return {"ok": False,
            "error": "Đã gửi mã nhưng chưa thấy đăng nhập xong. Bấm Kiểm tra lại sau vài giây; "
                     "còn không thì chạy `agy` trong terminal một lần.", "log": sach[-1200:]}


def trang_thai() -> dict:
    """Có phiên đăng nhập nào đang chờ dán mã không (dashboard tải lại trang vẫn biết)."""
    with _khoa:
        p = dict(_phien)
    dang_cho = bool(p and p.get("proc") and p["proc"].poll() is None)
    return {"dang_cho": dang_cho, "tu_bao_gio": float(p.get("ts") or 0) if dang_cho else 0}
