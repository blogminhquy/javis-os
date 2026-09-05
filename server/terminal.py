# -*- coding: utf-8 -*-
"""Terminal thật cho tab Code của dashboard.

Vì sao có file này
------------------
Javis chạy phần lớn trên VPS. Rất nhiều việc vặt của chủ máy (kéo code mới, xem log, chạy
`agy` để đăng nhập Antigravity, cài một CLI) vẫn phải mở SSH ở một cửa sổ khác. Tab Code đưa
đúng cái terminal đó vào trong dashboard.

Đây KHÔNG phải cái "terminal giả" đã bị gỡ ở 0.32.2. Bản đó dựng một ô chữ rồi cố đoán xem
chương trình muốn vẽ gì; lần này là pseudo-terminal THẬT của hệ điều hành, nên `htop`, `vim`,
Ctrl-C, màu, và mọi thứ hỏi phím đều chạy y như SSH.

Hai chế độ, nói thẳng chứ không giấu
------------------------------------
- **pty** (Linux, macOS, Docker): pseudo-terminal đầy đủ. Shell có controlling terminal riêng
  nên Ctrl-C giết đúng lệnh đang chạy chứ không giết shell.
- **ống** (Windows): Python trên Windows KHÔNG có module `pty`. ConPTY thì phải gọi tay qua
  ctypes kèm `STARTUPINFOEX` - một khối code khó mà `subprocess` không mở đường vào. Nên
  Windows chạy chế độ ống: gõ nguyên một dòng rồi Enter, lệnh chạy và output chảy về. Không có
  gợi ý Tab, không chạy được `vim`. Giao diện tự nói rõ điều này thay vì để người dùng gõ Tab
  rồi tự hỏi máy hỏng ở đâu.

Bảo mật
-------
Đây là chạy lệnh tuỳ ý trên máy chủ, tức là quyền cao nhất mà dashboard có thể cấp. Ba hàng
rào: WebSocket đòi đúng session đăng nhập như `/ws` (không nhận token API - terminal chỉ dành
cho trình duyệt đã đăng nhập), `JAVIS_TERMINAL=0` tắt hẳn tính năng, và số phiên mở cùng lúc
bị chặn ở `MAX_PHIEN`. Shell thừa kế env của server (trong đó có API key trong .env) - đúng
như mọi terminal khác của chủ máy, nhưng cần biết là nó ở đó.

Phiên sống lâu hơn tab
----------------------
Đổi trang trong dashboard là DOM bị xoá, WebSocket đứt. Nếu shell chết theo thì đang `npm
install` mà lỡ bấm sang tab khác là mất. Nên phiên nằm trong kho ở đây, WebSocket chỉ là người
xem: đứt kết nối thì shell chạy tiếp, quay lại thì nối vào phiên cũ và vẽ lại màn hình từ bộ
đệm. Không ai xem quá `REAP_GIAY` thì phiên mới bị dọn.
"""

from __future__ import annotations

import asyncio
import codecs
import os
import queue
import select
import shutil
import signal
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path

import winproc

IS_WINDOWS = os.name == "nt"

try:                                   # pty/termios chỉ có trên POSIX
    import fcntl
    import pty
    import struct
    import termios
    CO_PTY = not IS_WINDOWS
except ImportError:                    # pragma: no cover - chỉ xảy ra trên Windows
    CO_PTY = False

# Bộ đệm màn hình giữ lại để vẽ lại khi người dùng quay lại tab. 200k ký tự ~ vài nghìn dòng:
# đủ để không mất mạch việc, không đủ để thành chỗ rò bộ nhớ.
MAN_TOI_DA = 200_000
MAX_PHIEN = 4                          # mở cùng lúc; đủ cho một người, chặn vòng lặp tạo phiên
REAP_GIAY = 30 * 60                    # không ai xem quá lâu -> đóng shell
HANG_DOI_TOI_DA = 4000                 # gói chờ gửi cho một người xem; đầy thì bỏ gói cũ nhất
HANG_GO_TOI_DA = 2000                  # gói chờ ghi xuống shell; đầy nghĩa là shell không đọc stdin


def bat() -> bool:
    """Tính năng terminal có bật không. `JAVIS_TERMINAL=0` (hoặc off/false/no) là tắt hẳn."""
    v = str(os.getenv("JAVIS_TERMINAL", "")).strip().lower()
    return v not in ("0", "off", "false", "no")


def shell_argv() -> list[str]:
    """Shell sẽ chạy. `JAVIS_TERMINAL_SHELL` ghi đè; còn lại theo nếp của từng hệ."""
    rieng = str(os.getenv("JAVIS_TERMINAL_SHELL", "")).strip()
    if rieng:
        return [rieng]
    if IS_WINDOWS:
        for ten in ("powershell.exe", "cmd.exe"):
            p = shutil.which(ten)
            if p:
                return [p]
        return ["cmd.exe"]
    # KHÔNG thêm cờ -i: bash/zsh nối vào pty tự nhận ra mình là phiên tương tác. Thêm -i vào
    # mấy shell không hiểu cờ đó (dash) là hỏng ngay từ dòng đầu.
    sh = str(os.getenv("SHELL", "")).strip()
    if sh and Path(sh).exists():
        return [sh]
    for ten in ("bash", "sh"):
        p = shutil.which(ten)
        if p:
            return [p]
    return ["/bin/sh"]


def _khong_co_trinh_duyet() -> bool:
    """Máy chạy Javis có mở nổi một trình duyệt mà NGƯỜI DÙNG NHÌN THẤY không.

    Câu hỏi này quyết định luồng đăng nhập OAuth của mọi CLI chạy trong tab Code, xem `_env`.

    - `JAVIS_TERMINAL_REMOTE=1/0` ghi đè, cho ai có bố trí lạ (X11 forwarding, máy để bàn chạy
      Docker có chia màn hình...).
    - Windows/macOS chạy THẲNG trên máy: trình duyệt ở ngay trước mặt, giữ nguyên luồng cũ.
    - Linux: có `DISPLAY`/`WAYLAND_DISPLAY` là máy để bàn có màn hình; không có thì đây là VPS
      hoặc container - kể cả khi container đó nằm trên chính máy Mac của người dùng, vì trình
      duyệt nằm NGOÀI container còn CLI nằm trong.
    """
    v = str(os.getenv("JAVIS_TERMINAL_REMOTE", "")).strip().lower()
    if v in ("1", "on", "true", "yes"):
        return True
    if v in ("0", "off", "false", "no"):
        return False
    if IS_WINDOWS or sys.platform == "darwin":
        return False
    return not (os.getenv("DISPLAY") or os.getenv("WAYLAND_DISPLAY"))


def _env(extra: dict | None = None) -> dict:
    e = dict(os.environ)
    # xterm-256color: cho lệnh biết terminal này vẽ được màu và di được con trỏ.
    e["TERM"] = "xterm-256color"
    e.setdefault("COLORTERM", "truecolor")
    # Container thường không đặt LANG, và thiếu nó thì `ls` trong brain tiếng Việt ra một mớ
    # dấu hỏi. Chỉ setdefault - máy nào đã khai locale riêng thì giữ nguyên.
    if not IS_WINDOWS:
        e.setdefault("LANG", "C.UTF-8")
    # Dấu để script biết mình đang chạy trong terminal của Javis (vd muốn né tự cập nhật).
    e["JAVIS_IN_TERMINAL"] = "1"
    # PATH của server (systemd/Docker) thường CỤT - thiếu ~/.local/bin, đúng chỗ installer
    # chính chủ thả binary (agy, uv...). Hệ quả thật (16/08): người dùng cài agy xong, gõ
    # `agy` trong terminal của Javis nhận "command not found", tưởng cài hỏng, không đăng
    # nhập nổi Antigravity. Bù các ngăn quen thuộc, chỉ thêm ngăn ĐANG TỒN TẠI và chưa có
    # trong PATH - không phát minh PATH mới, chỉ vá chỗ server nghèo hơn shell thường.
    try:
        home = Path.home()
        ung_vien = [home / ".local" / "bin", home / ".antigravity" / "bin"]
        if IS_WINDOWS:
            ung_vien.append(Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "antigravity")
        parts = [p for p in (e.get("PATH", "") or "").split(os.pathsep) if p]
        for d in ung_vien:
            ds = str(d)
            if d.is_dir() and ds not in parts:
                parts.insert(0, ds)
        e["PATH"] = os.pathsep.join(parts)
    except Exception:
        pass
    # ĐĂNG NHẬP OAUTH TRONG TAB CODE: nói thẳng với CLI rằng người dùng đang ngồi ở MÁY KHÁC.
    #
    # Sự cố 05/09 (chủ repo, Javis chạy Docker, trình duyệt trên máy Mac): gõ `agy` trong tab
    # Code, màn hình in link Google rồi ĐỨNG IM - không có ô nào để dán mã về, đăng nhập tắc ở
    # đó. Nguyên nhân không nằm ở bàn phím của terminal (pty thật, gõ được) mà ở chỗ `agy` chọn
    # đường đăng nhập THEO MÔI TRƯỜNG:
    #   - Thấy `SSH_CONNECTION` -> biết người dùng ngồi máy khác: in link ra rồi CHỜ dán ngược
    #     lại URL callback (kèm mã) vào terminal.
    #   - Không thấy -> coi trình duyệt cùng máy: chỉ mở một cổng loopback
    #     `localhost:<cổng>/oauth-callback` rồi nằm chờ, và KHÔNG hỏi gì cả.
    # Terminal của Javis là pty thật ngay trên máy chủ nên chẳng có biến SSH nào -> luôn rơi
    # vào đường thứ hai. Trình duyệt lại ở máy Mac, nên Google trả về localhost CỦA MAC, chỗ đó
    # không có ai nghe: mã không bao giờ về tới `agy`, mà cũng không có chỗ nào để gõ nó vào.
    # Cùng một bệnh với mọi CLI đăng nhập kiểu loopback khi máy chủ không có màn hình.
    #
    # Chỉ đặt khi máy thật sự không có trình duyệt cho người dùng, và KHÔNG đè lên phiên SSH
    # thật. Cố ý không đặt `SSH_TTY`: giá trị của nó là đường dẫn tty, bịa ra một đường không
    # tồn tại còn hại hơn là thiếu.
    if _khong_co_trinh_duyet() and not e.get("SSH_CONNECTION"):
        # Định dạng thật: "<ip khách> <cổng khách> <ip máy chủ> <cổng máy chủ>". Javis không
        # biết IP của trình duyệt (WebSocket có thể qua proxy), và không CLI nào đọc mấy số
        # này - chúng chỉ hỏi "biến có hay không". Điền loopback cho đúng dạng.
        e["SSH_CONNECTION"] = "127.0.0.1 0 127.0.0.1 22"
        e.setdefault("SSH_CLIENT", "127.0.0.1 0 22")
    if extra:
        e.update({k: str(v) for k, v in extra.items() if v is not None})
    return e


def che_do() -> str:
    return "pty" if CO_PTY else "ong"


def _lenh_moi_dau() -> str:
    """Lệnh gõ hộ ngay khi shell vừa mở. Rỗng ở mọi nơi trừ Windows.

    Windows mặc định trả output theo codepage OEM của máy (tiếng Việt hay là cp1258/cp437),
    trong khi ở đây output được giải mã bằng UTF-8. Không bảo nó đổi thì mọi dòng có dấu về
    tới trình duyệt là một mớ ký tự lạ - hỏng lặng lẽ, và hỏng đúng với người dùng chính của
    Javis. Một dòng lệnh chữa được, nên chữa.

    Chưa chạy thử được trên Windows từ môi trường này. Nếu bản PowerShell nào không nuốt được
    câu lệnh, người dùng thấy MỘT dòng lỗi ở đầu màn hình rồi mọi thứ chạy tiếp - lộ ra chứ
    không âm thầm, đúng hướng đánh đổi cần chọn ở đây.
    """
    if not IS_WINDOWS:
        return ""
    ten = Path(shell_argv()[0]).name.lower()
    if "powershell" in ten or "pwsh" in ten:
        return ("[Console]::OutputEncoding=[Text.Encoding]::UTF8; "
                "$OutputEncoding=[Text.Encoding]::UTF8")
    if "cmd" in ten:
        return "chcp 65001 > nul"
    return ""


class Phien:
    """Một phiên terminal: tiến trình shell + ống đọc/ghi + bộ đệm màn hình.

    Luồng đọc là một THREAD chứ không phải `loop.add_reader`: chế độ ống trên Windows đọc từ
    pipe (add_reader không nhận pipe trên Windows), và một thread cho mỗi phiên với tối đa 4
    phiên là cái giá rẻ hơn nhiều so với hai đường đọc khác nhau cho hai hệ điều hành.
    """

    def __init__(self, sid: str, cwd: str, cols: int, rows: int, loop, extra_env: dict | None = None):
        self.id = sid
        self.cwd = str(cwd)
        self.extra_env = dict(extra_env or {})   # vd JAVIS_BRAIN - đường về gốc brain đang chọn
        self.cols = _gioi_han(cols, 20, 500, 80)
        self.rows = _gioi_han(rows, 5, 200, 24)
        self.che_do = che_do()
        self.tao_luc = time.time()
        self.roi_luc = 0.0             # lúc người xem cuối rời đi; 0 = đang có người xem
        self.ma_thoat: int | None = None
        self.man = ""                  # bộ đệm màn hình (đã giải mã)
        self.argv = shell_argv()
        self._loop = loop
        self._khach: list[asyncio.Queue] = []
        self._giai_ma = codecs.getincrementaldecoder("utf-8")(errors="replace")
        self._fd = -1
        self._fd_khoa = threading.Lock()   # ai lấy được fd thì người đó đóng, không đóng trùng
        self._doc_thread: threading.Thread | None = None
        self._go_doi: queue.Queue = queue.Queue(maxsize=HANG_GO_TOI_DA)
        self._go_thread: threading.Thread | None = None
        self.proc: subprocess.Popen | None = None
        self._mo()

    # ---- khởi động ----
    def _mo(self):
        env = _env(self.extra_env)
        if CO_PTY:
            master, slave = pty.openpty()

            def _con():
                # Chạy TRONG tiến trình con, ngay trước exec. setsid() tách khỏi phiên của
                # server, TIOCSCTTY nhận pty làm controlling terminal - thiếu nhát thứ hai thì
                # shell không có tty điều khiển, và Ctrl-C sẽ không giết được lệnh đang chạy.
                os.setsid()
                fcntl.ioctl(0, termios.TIOCSCTTY, 0)

            self.proc = subprocess.Popen(
                self.argv, cwd=self.cwd, env=env,
                stdin=slave, stdout=slave, stderr=slave,
                preexec_fn=_con, close_fds=True,
                **winproc.kwargs_no_window(),
            )
            os.close(slave)            # phía server chỉ giữ master
            # O_NONBLOCK cho master: KHÔNG một cú đọc/ghi nào được ngủ trong kernel. Cờ này
            # per-file-description nên ảnh hưởng CẢ HAI thread đọc và ghi cùng fd - cả hai đã
            # được dạy chờ bằng select thay vì chờ trong read/write (xem _vong_doc, _vong_go).
            # Lý do sống còn: một cú write đang ngủ vì bộ đệm input của slave đầy sẽ KHÔNG
            # được Linux đánh thức kể cả khi shell chết và fd bị đóng - thread đó kẹt vĩnh
            # viễn (đo được bằng test). Không ngủ thì không có gì để phải đánh thức.
            os.set_blocking(master, False)
            self._fd = master
            self._dat_co(self.cols, self.rows)
        else:
            # Windows: không có pty -> ống. stderr gộp vào stdout để thứ tự dòng đúng như khi
            # nhìn trên console thật. bufsize=0 để output hiện ngay, không đợi đầy đệm.
            #
            # Cờ dựng CÓ ĐIỀU KIỆN chứ không truyền thẳng: `creationflags` là tham số chỉ có
            # trên Windows, POSIX nhận vào là ném ValueError ngay - và nhánh này còn được test
            # chạy trên Linux (ép CO_PTY=False), vì không ai ngồi Linux thử được nó bằng tay.
            # CREATE_NEW_PROCESS_GROUP là điều kiện để gửi được Ctrl-Break xuống shell sau này.
            creationflags_windows = (
                {"creationflags": winproc.no_window() | winproc.CREATE_NEW_PROCESS_GROUP}
                if IS_WINDOWS else {}
            )
            self.proc = subprocess.Popen(
                self.argv, cwd=self.cwd, env=env,
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                bufsize=0, close_fds=True,
                start_new_session=True,      # POSIX: nhóm riêng để đóng phiên không đụng nhóm của server
                **creationflags_windows,
            )
        self._doc_thread = threading.Thread(target=self._vong_doc, name=f"term-{self.id[:6]}",
                                            daemon=True)
        self._doc_thread.start()
        self._go_thread = threading.Thread(target=self._vong_go, name=f"term-go-{self.id[:6]}",
                                           daemon=True)
        self._go_thread.start()
        moi = _lenh_moi_dau()
        if moi:
            self.go(moi + "\n")

    # ---- trạng thái ----
    def song(self) -> bool:
        return bool(self.proc) and self.proc.poll() is None

    def so_nguoi_xem(self) -> int:
        return len(self._khach)

    def tom_tat(self) -> dict:
        return {
            "id": self.id,
            "cwd": self.cwd,
            "che_do": self.che_do,
            "song": self.song(),
            "nguoi_xem": self.so_nguoi_xem(),
            "tao_luc": self.tao_luc,
            "ma_thoat": self.ma_thoat,
        }

    # ---- đọc từ shell ----
    def _vong_doc(self):
        fd = self._fd if CO_PTY else (self.proc.stdout.fileno() if self.proc and self.proc.stdout else -1)
        while fd >= 0:
            try:
                b = os.read(fd, 65536)
            except BlockingIOError:
                # Master để O_NONBLOCK (vì đường ghi, xem _mo). Chưa có chữ thì chờ bằng
                # select rồi đọc lại; shell chết thì fd báo đọc-được (hangup) nên vẫn tỉnh
                # dậy đúng lúc. Timeout chỉ là lưới đỡ cho ca fd bị đóng sau lưng select.
                try:
                    select.select([fd], [], [], 30)
                except (OSError, ValueError):
                    break
                continue
            except (OSError, ValueError):
                break                  # shell thoát -> master bị đóng/EIO
            if not b:
                break
            txt = self._giai_ma.decode(b)
            if txt:
                # Thread khác đang chạy: mọi thứ chạm vào hàng đợi asyncio phải quay về loop.
                try:
                    self._loop.call_soon_threadsafe(self._phat, txt)
                except RuntimeError:
                    break              # loop đã đóng (server đang tắt)
        # Lấy mã thoát Ở ĐÂY, trong thread đọc, chứ không phải trong _het() trên loop: shell
        # có thể đóng ống rồi mà chưa chết hẳn, và chờ ở đó là giữ cả server đứng một giây.
        # Cùng lớp với vụ os.close 14/08/2026, chỉ nhẹ hơn.
        #
        # Chờ bằng vòng poll() chứ KHÔNG bằng wait(timeout=1): đóng phiên thì thread _giet
        # cũng đang wait() trên cùng tiến trình, và wait() của Popen tranh nhau một khoá nội
        # bộ - kẻ thua ném TimeoutExpired dù tiến trình đã chết ngon lành, thành ra mã thoát
        # báo -1 sai (đo được: cứ vài lượt test lại lệch một lần). poll() không tranh khoá đó
        # và đọc được returncode ngay khi bên kia reap xong.
        ma = -1
        for _ in range(20):
            r = self.proc.poll() if self.proc else None
            if r is not None:
                ma = r
                break
            time.sleep(0.05)
        try:
            self._loop.call_soon_threadsafe(self._het, ma)
        except RuntimeError:
            pass

    def _phat(self, txt: str):
        self.man = _cat_dem(self.man + txt)
        for q in list(self._khach):
            _day(q, {"type": "out", "data": txt})

    def _het(self, ma: int = -1):
        if self.ma_thoat is None:
            self.ma_thoat = ma
        for q in list(self._khach):
            _day(q, {"type": "exit", "code": self.ma_thoat})
        self._dong_fd()

    # ---- ghi xuống shell ----
    def go(self, data: str):
        """Nhận phím/chữ dán từ trình duyệt. CHỈ xếp vào hàng, không chạm ống.

        Bản cũ os.write(master) ngay tại đây - tức trên event loop. Ghi vào pty master sẽ CHẶN
        khi bộ đệm input của slave đầy mà tiến trình foreground không đọc stdin (dán một khối
        chữ NHIỀU DÒNG vào lệnh đang bận là đủ), và loop bị giữ tới khi tiến trình chịu đọc.
        Anh em cùng lớp với vụ os.close 14/08/2026. Giờ mọi cú ghi thật nằm ở thread _vong_go,
        và master chạy O_NONBLOCK (xem _mo) nên kể cả thread đó cũng không bao giờ ngủ trong
        kernel - nó chờ bằng select có hạn, thứ luôn thoát ra được khi phiên đóng.
        """
        if not data or not self.song():
            return
        b = data.encode("utf-8", "ignore")
        try:
            self._go_doi.put_nowait(b)
        except queue.Full:
            # Shell không chịu đọc stdin mà người dùng vẫn đổ chữ vào. Bỏ gói MỚI chứ không bỏ
            # gói cũ (ngược với _day cho người xem): input mà rút mất khúc giữa thì lệnh gõ dở
            # thành lệnh khác; cắt ở đuôi ít nhất còn giữ nguyên những gì đã xếp hàng.
            pass

    def _vong_go(self):
        """Thread ghi riêng của phiên: hút hàng đợi, ghi xuống shell, phải chờ thì chỉ mình
        nó chờ - và chờ bằng select có hạn chứ không ngủ trong write.

        Master để O_NONBLOCK nên os.write hoặc nhận ngay phần vừa chỗ trống, hoặc ném
        BlockingIOError - không bao giờ ngủ trong kernel. Điều đó quan trọng vì Linux KHÔNG
        đánh thức một cú write đang ngủ trên master kể cả khi shell chết và fd bị đóng: bản
        ghi-chặn sẽ rò một thread kẹt vĩnh viễn mỗi lần dán to vào lệnh đang bận rồi đóng
        phiên. Thoát theo ba đường: sentinel None (từ _dung_go), cú ghi/select báo lỗi, hoặc
        thấy self._fd đã bị xoá giữa hai nhịp chờ.

        Nhánh ống (Windows) giữ ghi chặn: pipe được POSIX/Windows bảo đảm đánh thức người ghi
        bằng EPIPE/BrokenPipeError khi đầu đọc đóng, không có ca kẹt vĩnh viễn như pty.
        """
        fd = self._fd                  # chụp một lần; _dong_fd() xoá self._fd về -1 khi đóng
        while True:
            b = self._go_doi.get()
            if b is None:
                break
            try:
                if CO_PTY:
                    while b:           # ghi được phần nào cắt phần đó, ghi cho hết gói
                        if self._fd != fd:
                            return     # phiên đã đóng: _dong_fd xoá _fd TRƯỚC khi close, nên
                                       # còn thấy số cũ ở đây nghĩa là số đó chưa bị tái cấp
                        try:
                            b = b[os.write(fd, b):]
                        except BlockingIOError:
                            # Bộ đệm input của slave đầy (shell chưa đọc). Chờ có chỗ trống,
                            # timeout ngắn để vòng ngoài kịp thấy phiên đóng mà tự thoát.
                            select.select([], [fd], [], 0.2)
                elif self.proc and self.proc.stdin:
                    self.proc.stdin.write(b)
                    self.proc.stdin.flush()
                else:
                    break
            except (OSError, ValueError, BrokenPipeError):
                break

    def _dung_go(self):
        """Đánh thức thread ghi để nó thoát. Hàng đầy thì vứt bớt gói chờ - đằng nào phiên
        cũng đang đóng, chữ chưa ghi được không còn nơi đến."""
        while True:
            try:
                self._go_doi.put_nowait(None)
                return
            except queue.Full:
                try:
                    self._go_doi.get_nowait()
                except queue.Empty:
                    pass               # thread ghi vừa hút sạch giữa hai nhịp; vòng sau sẽ vào

    def ngat(self):
        """Ctrl-C. Chế độ pty thì ký tự \\x03 đã đi thẳng qua `go()`; đây là đường cho chế độ
        ống, nơi không có tty driver nào dịch phím thành tín hiệu."""
        if not self.song():
            return
        try:
            if CO_PTY:
                self.go("\x03")
            elif IS_WINDOWS:
                self.proc.send_signal(signal.CTRL_BREAK_EVENT)   # type: ignore[attr-defined]
            else:
                self.proc.send_signal(signal.SIGINT)             # nhánh ống trên POSIX: chỉ test đi qua
        except Exception:
            pass

    def doi_co(self, cols: int, rows: int):
        self.cols = _gioi_han(cols, 20, 500, self.cols)
        self.rows = _gioi_han(rows, 5, 200, self.rows)
        self._dat_co(self.cols, self.rows)

    def _dat_co(self, cols: int, rows: int):
        if not CO_PTY or self._fd < 0:
            return                     # chế độ ống không có khổ giấy để báo
        try:
            fcntl.ioctl(self._fd, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))
        except OSError:
            pass

    # ---- người xem ----
    def gan(self) -> asyncio.Queue:
        """Nối một người xem. Trả hàng đợi đã có sẵn màn hình cũ để vẽ lại ngay."""
        q: asyncio.Queue = asyncio.Queue(maxsize=HANG_DOI_TOI_DA)
        self._khach.append(q)
        self.roi_luc = 0.0
        if self.man:
            q.put_nowait({"type": "out", "data": self.man})
        if not self.song():
            q.put_nowait({"type": "exit", "code": self.ma_thoat})
        return q

    def go_ra(self, q: asyncio.Queue):
        try:
            self._khach.remove(q)
        except ValueError:
            pass
        if not self._khach:
            self.roi_luc = time.time()

    # ---- đóng ----
    def dong(self):
        """Đóng shell: giết tiến trình TRƯỚC, đóng fd SAU, tất cả trong thread nền.

        Thứ tự là điều sống còn chứ không phải thẩm mỹ (vụ treo 14/08/2026): bản cũ
        os.close(master) ngay tại đây - tức trên event loop - trong khi thread đọc còn kẹt
        trong os.read cùng fd. Trên macOS, close() một fd đang có read dở sẽ NGỦ CHỜ read
        xong; read thì chờ shell nhả chữ mà shell đang im. Event loop đứng vĩnh viễn, server
        phớt luôn SIGTERM (uvloop xử lý tín hiệu bằng callback trên loop). Giết shell trước
        thì read nhận EIO tự thoát và close hết đường kẹt; lỡ vẫn kẹt (tiến trình cháu tự
        setsid giữ slave) thì chỉ thread nền nằm lại, loop vô can."""
        threading.Thread(target=self._giet_va_dong, args=(self.proc,), daemon=True).start()

    def _giet_va_dong(self, p: subprocess.Popen | None):
        if p is not None and p.poll() is None:
            self._giet(p)
        self._dong_fd()

    def _la_nhom_truong(self, p: subprocess.Popen) -> bool:
        """Shell có phải TRƯỞNG của process group riêng không.

        Đây là câu hỏi phải hỏi trước mỗi `killpg`, và nó không thừa: lúc viết test cho nhánh
        ống trên Linux, `killpg` đã bắn SIGHUP vào nhóm của chính tiến trình gọi và giết luôn
        cả lượt chạy test. Trong Javis thật thì nhánh POSIX luôn setsid nên chuyện đó không
        tới được - nhưng "không tới được" mà sai thì mất cả server, nên chốt bằng điều kiện
        chứ không bằng niềm tin."""
        try:
            return os.getpgid(p.pid) == p.pid
        except (OSError, AttributeError):
            return False

    def _giet(self, p: subprocess.Popen):
        # Giết cả NHÓM khi giết được: setsid cho shell một process group riêng, nên lệnh con nó
        # đẻ ra (npm, python...) cũng nằm trong đó. Giết mỗi shell là bỏ lại một đàn mồ côi.
        nhom = not IS_WINDOWS and self._la_nhom_truong(p)
        try:
            if nhom:
                os.killpg(p.pid, signal.SIGHUP)
            else:
                p.terminate()
        except (OSError, ProcessLookupError):
            return
        try:
            p.wait(timeout=3)
        except Exception:
            try:
                if nhom:
                    os.killpg(p.pid, signal.SIGKILL)
                else:
                    p.kill()
            except (OSError, ProcessLookupError):
                pass

    def _dong_fd(self):
        # Hai đường cùng dẫn tới đây (thread giết của dong() và _het() trên loop khi shell tự
        # thoát). Lấy-rồi-xoá fd trong khoá để chỉ MỘT bên đóng: close hai lần cùng số fd mà
        # giữa chừng hệ thống đã tái cấp số đó cho việc khác là đóng nhầm fd của người ta.
        with self._fd_khoa:
            fd, self._fd = self._fd, -1
        if fd >= 0:
            try:
                os.close(fd)
            except OSError:
                pass
        self._dung_go()                # mọi đường đóng đều qua đây -> thread ghi cũng về theo


class Kho:
    """Kho phiên đang mở. Một bản dùng chung cho cả server (biến `KHO` bên dưới)."""

    def __init__(self):
        self._phien: dict[str, Phien] = {}
        self._don_task = None

    def danh_sach(self) -> list[dict]:
        return [p.tom_tat() for p in self._phien.values()]

    def lay(self, sid: str) -> Phien | None:
        return self._phien.get(sid or "")

    def mo(self, sid: str, cwd: str, cols: int, rows: int, loop,
           extra_env: dict | None = None) -> Phien:
        """Nối lại phiên `sid` nếu còn sống, không thì mở phiên mới.

        Ném RuntimeError khi đã chạm trần số phiên - người gọi báo lỗi đó ra màn hình chứ đừng
        lặng lẽ mở thêm.
        """
        self.don()
        cu = self._phien.get(sid or "")
        if cu is not None and cu.song():
            cu.doi_co(cols, rows)
            return cu
        if cu is not None:
            self._bo(cu)
        song = [p for p in self._phien.values() if p.song()]
        if len(song) >= MAX_PHIEN:
            raise RuntimeError(f"Đang mở {len(song)} phiên terminal rồi (tối đa {MAX_PHIEN}). "
                               "Đóng bớt một phiên rồi thử lại.")
        p = Phien(uuid.uuid4().hex[:12], cwd, cols, rows, loop, extra_env=extra_env)
        self._phien[p.id] = p
        self._bat_don(loop)
        return p

    def dong(self, sid: str) -> bool:
        p = self._phien.get(sid or "")
        if not p:
            return False
        self._bo(p)
        return True

    def dong_het(self):
        for p in list(self._phien.values()):
            self._bo(p)

    def don(self):
        """Dọn phiên đã chết và phiên không ai xem quá lâu."""
        for p in list(self._phien.values()):
            if not p.song() and not p._khach:
                self._bo(p)
            elif p.roi_luc and (time.time() - p.roi_luc) > REAP_GIAY:
                self._bo(p)

    def _bo(self, p: Phien):
        self._phien.pop(p.id, None)
        p.dong()

    def _bat_don(self, loop):
        if self._don_task is not None and not self._don_task.done():
            return
        try:
            self._don_task = loop.create_task(self._vong_don())
        except RuntimeError:
            self._don_task = None

    async def _vong_don(self):
        while self._phien:
            await asyncio.sleep(60)
            try:
                self.don()
            except Exception:
                pass
        self._don_task = None


KHO = Kho()


def trang_thai(cwd: str) -> dict:
    """Dữ liệu cho GET /terminal/status - đủ để giao diện nói thật về chế độ đang chạy."""
    argv = shell_argv()
    return {
        "bat": bat(),
        "che_do": che_do(),
        "shell": Path(argv[0]).name if argv else "",
        "cwd": str(cwd),
        "phien": KHO.danh_sach(),
        "max_phien": MAX_PHIEN,
        "reap_phut": REAP_GIAY // 60,
    }


# ---- tiện ích nhỏ ----
def _gioi_han(v, thap: int, cao: int, mac_dinh: int) -> int:
    try:
        n = int(v)
    except (TypeError, ValueError):
        return mac_dinh
    return max(thap, min(cao, n))


def _cat_dem(s: str) -> str:
    """Giữ đuôi bộ đệm trong hạn mức, cắt ở đầu dòng gần nhất.

    Cắt giữa một chuỗi thoát ANSI thì lần vẽ lại đầu tiên sẽ ra một mẩu rác kiểu `[38;5;`.
    Lùi tới newline gần nhất là đủ để chuyện đó gần như không xảy ra.
    """
    if len(s) <= MAN_TOI_DA:
        return s
    s = s[-MAN_TOI_DA:]
    i = s.find("\n")
    return s[i + 1:] if 0 <= i < 4096 else s


def _day(q: asyncio.Queue, goi: dict):
    """Đẩy gói cho người xem; hàng đợi đầy thì bỏ gói CŨ nhất.

    Người xem chậm (tab bị treo, mạng kém) không được phép làm nghẽn shell - thà mất mấy dòng
    cũ còn hơn để cả phiên đứng lại."""
    try:
        q.put_nowait(goi)
    except asyncio.QueueFull:
        try:
            q.get_nowait()
            q.put_nowait(goi)
        except Exception:
            pass
