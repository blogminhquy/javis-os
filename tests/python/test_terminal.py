"""Terminal của tab Code: phiên pty thật, bộ đệm màn hình, trần số phiên, và các hàng rào.

    python tests/run.py terminal

Ba nhóm được canh ở đây, theo đúng thứ tự "hỏng thì đau tới đâu":

1. **Hàng rào** (quét mã nguồn main.py). Đây là endpoint chạy lệnh tuỳ ý trên máy chủ, tức là
   thứ nguy hiểm nhất dashboard có. Ai đó sửa nhầm một dòng làm mất nhát kiểm `valid_session`
   thì cả VPS thành shell công cộng, mà chạy thử bằng mắt sẽ KHÔNG thấy gì bất thường - trang
   vẫn mở, terminal vẫn chạy. Nên phải là test.
2. **Phiên sống lâu hơn WebSocket.** Đổi trang là socket đứt; shell chết theo thì đang `npm
   install` mà lỡ bấm sang tab khác là mất. Test nối lại rồi đòi xem màn hình cũ.
3. **Không bỏ lại tiến trình mồ côi.** Shell chạy trong process group riêng nên nó KHÔNG chết
   theo server; đóng phiên phải giết cả nhóm.

Chạy được trên Linux/macOS. Trên Windows phần pty tự bỏ qua (ở đó Javis chạy chế độ ống) -
nhưng nhánh ống vẫn được test ở mọi hệ bằng cách ép CO_PTY=False, vì đó là nhánh không ai ngồi
Linux chạy thử được.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401  - nạp server/ vào sys.path
import asyncio
import os
import queue
import re
import sys
import threading
import time

import terminal  # noqa: E402

_fails = []


def check(name, cond, them=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(them) + "]") if them and not cond else ""))
    if not cond:
        _fails.append(name)


# ============================================================
# 1. Hàng rào - quét mã nguồn (không import main: nó kéo cả app lên)
# ============================================================
SRC = (SERVER / "main.py").read_text(encoding="utf-8")
_ws = re.search(r"@app\.websocket\(\"/ws/terminal\"\).*?(?=\n@app\.|\n# =====)", SRC, re.S)
_than = _ws.group(0) if _ws else ""

check("có endpoint WebSocket /ws/terminal", bool(_than))
check("WS terminal đòi ĐÚNG session đăng nhập như /ws",
      "cfgmod.gate_active()" in _than and "cfgmod.valid_session" in _than
      and "javis_session" in _than)
check("CANARY: WS terminal KHÔNG nhận token API (_token_ok là đường của script, không phải shell)",
      "_token_ok" not in _than)
check("WS terminal tôn trọng công tắc tắt JAVIS_TERMINAL", "terminal.bat()" in _than)
check("/terminal/status + /terminal/close không nằm trong danh sách khỏi đăng nhập",
      "/terminal" not in re.search(r"_AUTH_PUBLIC_EXACT = \((.*?)\)", SRC, re.S).group(1)
      and "/terminal" not in re.search(r"_AUTH_LOCAL_EXACT = \((.*?)\)", SRC, re.S).group(1))
check("tắt server thì đóng hết shell (không bỏ lại tiến trình mồ côi)",
      "terminal.KHO.dong_het()" in SRC)
check("rời tab chỉ GỠ NGƯỜI XEM, không giết shell",
      "phien.go_ra(q)" in _than and "phien.dong()" not in _than)


# ============================================================
# 2. Công tắc + cấu hình
# ============================================================
_cu = os.environ.get("JAVIS_TERMINAL")
try:
    os.environ.pop("JAVIS_TERMINAL", None)
    check("mặc định terminal BẬT", terminal.bat() is True)
    for v in ("0", "off", "false", "no", "OFF"):
        os.environ["JAVIS_TERMINAL"] = v
        check(f"JAVIS_TERMINAL={v} -> tắt", terminal.bat() is False)
finally:
    os.environ.pop("JAVIS_TERMINAL", None)
    if _cu is not None:
        os.environ["JAVIS_TERMINAL"] = _cu

check("shell_argv() luôn trả ít nhất một lệnh", len(terminal.shell_argv()) >= 1)
check("che_do() ra 'pty' trên POSIX / 'ong' trên Windows",
      terminal.che_do() == ("ong" if os.name == "nt" else "pty"))

_st = terminal.trang_thai("/tmp")
check("trang_thai() đủ trường cho giao diện",
      all(k in _st for k in ("bat", "che_do", "shell", "cwd", "phien", "max_phien", "reap_phut")))


# ============================================================
# 3. Tiện ích: cắt bộ đệm + hàng đợi đầy
# ============================================================
_dai = ("x" * 50 + "\n") * 8000
_cat = terminal._cat_dem(_dai)
check("bộ đệm màn hình bị cắt về trong hạn mức", len(_cat) <= terminal.MAN_TOI_DA)
check("cắt ở ĐẦU DÒNG (không để lại nửa chuỗi thoát ANSI)", not _cat or _cat.startswith("x"))
check("bộ đệm ngắn thì giữ nguyên", terminal._cat_dem("abc") == "abc")


async def _thu_hang_doi():
    q = asyncio.Queue(maxsize=2)
    for i in range(5):
        terminal._day(q, {"type": "out", "data": str(i)})
    con = [q.get_nowait()["data"] for _ in range(q.qsize())]
    return con


check("hàng đợi đầy thì bỏ gói CŨ nhất, giữ gói mới (người xem chậm không làm nghẽn shell)",
      asyncio.run(_thu_hang_doi()) == ["3", "4"])


# ============================================================
# 4. Phiên thật
# ============================================================
async def _doc(q, dieu_kien, giay=6.0):
    """Gom output tới khi dieu_kien(buf) đúng, hoặc hết giờ."""
    buf = ""
    het = time.time() + giay
    while time.time() < het:
        try:
            g = await asyncio.wait_for(q.get(), timeout=0.4)
        except asyncio.TimeoutError:
            continue
        if g["type"] == "out":
            buf += g["data"]
        elif g["type"] == "exit":
            buf += f"\n<exit {g['code']}>"
        if dieu_kien(buf):
            break
    return buf


async def _phien_that():
    loop = asyncio.get_running_loop()
    p = terminal.KHO.mo("", "/tmp", 100, 30, loop)
    q = p.gan()
    p.go("echo KQ=$((6*7))\n")
    buf = await _doc(q, lambda b: "KQ=42" in b)
    check("chạy được lệnh và trả output", "KQ=42" in buf, repr(buf[-160:]))

    if terminal.CO_PTY:
        p.go("tty; stty size\n")
        buf = await _doc(q, lambda b: "30 100" in b)
        # Linux đặt tên pty là /dev/pts/N, macOS là /dev/ttysNNN - cả hai đều là pty thật.
        check("là pty THẬT (có /dev/pts hoặc /dev/ttys) chứ không phải ống",
              "/dev/pts" in buf or "/dev/ttys" in buf, repr(buf[-160:]))
        check("khổ giấy truyền đúng xuống shell (30 dòng x 100 cột)", "30 100" in buf, repr(buf[-160:]))
        p.doi_co(140, 45)
        p.go("stty size\n")
        buf = await _doc(q, lambda b: "45 140" in b)
        check("đổi cỡ khung -> shell biết ngay", "45 140" in buf, repr(buf[-160:]))

    # Nối lại: y như đổi trang rồi quay về tab Code.
    p.go_ra(q)
    check("gỡ người xem KHÔNG giết shell", p.song())
    p2 = terminal.KHO.mo(p.id, "/tmp", 100, 30, asyncio.get_running_loop())
    check("mo() với id cũ trả về ĐÚNG phiên cũ", p2 is p)
    q2 = p2.gan()
    dau = await asyncio.wait_for(q2.get(), timeout=2)
    check("nối lại thì vẽ lại màn hình cũ", dau["type"] == "out" and "KQ=42" in dau["data"])

    # Trần số phiên: mở thêm cho đủ rồi đòi một cái nữa.
    #
    # Vòng ĐẾM chứ không phải `while chưa đủ phiên sống`: nếu shell trên máy đang chạy test
    # chết ngay khi mở (thiếu bash, /tmp không ghi được), vòng theo điều kiện sẽ đẻ và dọn
    # phiên chết vô hạn - test không đỏ mà TREO, kiểu hỏng tệ nhất trên CI.
    them = []
    for _ in range(terminal.MAX_PHIEN + 2):
        if len([x for x in terminal.KHO._phien.values() if x.song()]) >= terminal.MAX_PHIEN:
            break
        try:
            them.append(terminal.KHO.mo("", "/tmp", 80, 24, asyncio.get_running_loop()))
        except RuntimeError:
            break
    tran = False
    try:
        terminal.KHO.mo("", "/tmp", 80, 24, asyncio.get_running_loop())
    except RuntimeError:
        tran = True
    check(f"quá {terminal.MAX_PHIEN} phiên thì từ chối kèm lời giải thích", tran)

    # Thoát shell -> có mã thoát, và phiên chết được dọn.
    p2.go("exit 7\n")
    await _doc(q2, lambda b: "<exit" in b)
    check("shell thoát -> báo đúng mã thoát", p2.ma_thoat == 7, p2.ma_thoat)
    p2.go_ra(q2)
    terminal.KHO.don()
    check("phiên đã chết bị dọn khỏi kho", terminal.KHO.lay(p2.id) is None)

    # Dọn theo thời gian: giả vờ người xem cuối rời đi từ lâu.
    con = [x for x in terminal.KHO._phien.values() if x.song()]
    if con:
        moc = con[0]
        moc.roi_luc = time.time() - terminal.REAP_GIAY - 10
        terminal.KHO.don()
        check("phiên không ai xem quá lâu bị dọn", terminal.KHO.lay(moc.id) is None)

    pids = [x.proc.pid for x in terminal.KHO._phien.values() if x.song()]
    terminal.KHO.dong_het()
    await asyncio.sleep(1.2)
    check("dong_het() đóng sạch kho", terminal.KHO.danh_sach() == [])
    con_song = [pid for pid in pids if _con_song(pid)]
    check("đóng phiên thì tiến trình shell chết thật, không mồ côi", not con_song, con_song)


def _con_song(pid):
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


asyncio.run(_phien_that())


# ============================================================
# 5. Chống deadlock close-vs-read (vụ treo 14/08/2026)
# ============================================================
async def _dong_khong_treo_loop():
    """Vụ treo 14/08/2026: dong() từng os.close(master) ngay trên event loop trong khi thread
    đọc còn kẹt os.read cùng fd. Trên macOS, close() một fd đang có read dở sẽ ngủ chờ read
    xong → loop đứng vĩnh viễn, server phớt SIGTERM, phải kill -9. Linux không treo kiểu đó
    nên không tái hiện được trên CI - thay vào đó chốt hai BẤT BIẾN mà bản lỗi vi phạm ở mọi
    hệ: (1) dong() trả về ngay, không làm việc chặn nào trên loop; (2) mọi cú os.close(master)
    chỉ xảy ra khi shell ĐÃ CHẾT hoặc thread đọc ĐÃ THOÁT."""
    loop = asyncio.get_running_loop()
    p = terminal.Phien("test-dong-an-toan", "/tmp", 80, 24, loop)
    q = p.gan()
    p.go("echo SAN_SANG=1\n")
    await _doc(q, lambda b: "SAN_SANG=1" in b)  # shell ở prompt -> thread đọc đang kẹt os.read

    ghi = []
    goc = p._dong_fd

    def _theo_doi():
        ghi.append({
            "proc_chet": p.proc.poll() is not None,
            "doc_thoat": not (p._doc_thread and p._doc_thread.is_alive()),
            "go_thoat": not (p._go_thread and p._go_thread.is_alive()),
        })
        goc()

    p._dong_fd = _theo_doi
    t0 = time.time()
    p.dong()
    tre = time.time() - t0
    check("dong() trả về ngay, không giữ event loop", tre < 0.5, f"{tre:.2f}s")

    het = time.time() + 8
    while time.time() < het and (p._fd >= 0 or p.song()):
        await asyncio.sleep(0.1)
    check("sau dong(): shell chết thật và fd master đã đóng", not p.song() and p._fd < 0,
          f"song={p.song()} fd={p._fd}")
    check("os.close(master) chỉ chạy khi shell đã chết hoặc cả hai thread đọc/ghi đã thoát "
          "(bất biến chống deadlock close-vs-read và close-vs-write)",
          bool(ghi) and all(g["proc_chet"] or (g["doc_thoat"] and g["go_thoat"]) for g in ghi),
          ghi)


if terminal.CO_PTY:
    asyncio.run(_dong_khong_treo_loop())


# ============================================================
# 6. Ghi xuống shell không được chặn loop (anh em của vụ 14/08/2026, phía GHI)
# ============================================================
async def _go_khong_chan_loop():
    """go() từng os.write(master) ngay trên event loop. Ghi vào pty master CHẶN khi bộ đệm
    input của slave đầy mà tiến trình foreground không đọc stdin - dán một khối chữ lớn vào
    lệnh đang bận là đủ - và loop bị giữ tới khi tiến trình chịu đọc. Ba bất biến chốt ở đây:
    (1) go() trả về ngay cả khi shell không đọc stdin; (2) hàng ghi đầy thì go() bỏ gói chứ
    không chặn; (3) đóng phiên đang kẹt ghi thì thread ghi tự thoát, không rò thread."""
    loop = asyncio.get_running_loop()
    p = terminal.Phien("test-go-an-toan", "/tmp", 80, 24, loop)
    q = p.gan()
    # Biến foreground thành tiến trình KHÔNG BAO GIỜ đọc stdin. Marker viết dạng tính toán
    # (N$((...)) -> N1337) để không khớp nhầm với dòng tty echo lại chính lệnh vừa gõ.
    p.go("echo N$((1000+337)); exec sleep 300\n")
    await _doc(q, lambda b: "N1337" in b)
    await asyncio.sleep(0.3)           # cho exec kịp thay shell bằng sleep

    # (1) Dán 300k NHIỀU DÒNG khi không ai đọc stdin: các dòng trọn vẹn dồn đầy bộ đệm
    # canonical của tty (4KB) là os.write lên master bị chặn - bản lỗi đứng ở đó vô hạn.
    # PHẢI nhiều dòng: một dòng đơn dài quá 4095 thì n_tty VỨT BỚT ký tự chứ không chặn
    # (đã thử, bản lỗi vẫn xanh với một dòng), tức là không tái hiện được bug. Gọi qua
    # thread phụ + join có hạn để nếu tái phát thì test ĐỎ chứ không TREO - kiểu hỏng tệ
    # nhất trên CI.
    dan = ("x" * 50 + "\n") * 6000
    t = threading.Thread(target=lambda: p.go(dan), daemon=True)
    t.start()
    t.join(2.0)
    check("go() với khối dán lớn khi shell không đọc stdin: trả về ngay, không chặn",
          not t.is_alive())

    # (2) Nhét hàng ghi cho đầy hẳn rồi go() thêm: phải về ngay (bỏ gói mới), không chặn.
    while True:
        try:
            p._go_doi.put_nowait(b"x")
        except queue.Full:
            break
    t0 = time.time()
    p.go("y")
    tre = time.time() - t0
    check("hàng ghi đầy -> go() bỏ gói mới ngay, không chặn", tre < 0.5, f"{tre:.2f}s")

    # (3) Đóng phiên khi thread ghi đang kẹt giữa cú os.write: giết shell trước (trật tự đã
    # chốt ở vụ 14/08/2026) làm cú ghi nhận EIO, thread ghi phải tự thoát - không để lại một
    # thread kẹt vĩnh viễn sau mỗi phiên kiểu này.
    p.dong()
    het = time.time() + 8
    while time.time() < het and (p.song() or p._fd >= 0
                                 or (p._go_thread and p._go_thread.is_alive())):
        await asyncio.sleep(0.1)
    check("đóng phiên đang kẹt ghi: shell chết thật và fd master đã đóng",
          not p.song() and p._fd < 0, f"song={p.song()} fd={p._fd}")
    check("thread ghi tự thoát sau khi đóng phiên (không rò thread kẹt)",
          not (p._go_thread and p._go_thread.is_alive()))
    p.go_ra(q)


if terminal.CO_PTY:
    asyncio.run(_go_khong_chan_loop())


# ============================================================
# 7. Mã thoát lấy trong thread đọc, không phải trên event loop
# ============================================================
async def _ma_thoat_khong_tren_loop():
    """_het() từng proc.wait(timeout=1) ngay trên event loop: shell đóng ống mà chưa chết hẳn
    là loop đứng trọn một giây. Giờ wait chạy trong thread đọc. Chốt bằng cách ghi lại THREAD
    nào gọi wait thay vì đo thời gian - đo giờ trên CI là mời flaky vào nhà."""
    loop = asyncio.get_running_loop()
    p = terminal.Phien("test-wait-thread", "/tmp", 80, 24, loop)
    q = p.gan()
    goc = p.proc.wait
    goi_tu = []

    def _wait_theo_doi(timeout=None):
        goi_tu.append(threading.get_ident())
        return goc(timeout=timeout)

    p.proc.wait = _wait_theo_doi
    p.go("exit 5\n")
    await _doc(q, lambda b: "<exit" in b)
    check("mã thoát vẫn về đúng qua đường mới", p.ma_thoat == 5, p.ma_thoat)
    check("proc.wait KHÔNG chạy trên thread của event loop",
          bool(goi_tu) and all(t != threading.get_ident() for t in goi_tu), goi_tu)
    p.go_ra(q)
    p.dong()


asyncio.run(_ma_thoat_khong_tren_loop())


# ============================================================
# 8. Nhánh ỐNG (Windows) - ép chạy trên mọi hệ, vì không ai ngồi Linux thử được nhánh này
# ============================================================
async def _nhanh_ong():
    that = terminal.CO_PTY
    terminal.CO_PTY = False
    try:
        check("ép CO_PTY=False -> che_do() báo 'ong'", terminal.che_do() == "ong")
        loop = asyncio.get_running_loop()
        p = terminal.Phien("test-ong", "/tmp", 80, 24, loop)
        check("phiên ống mở được", p.song() and p.che_do == "ong")
        q = p.gan()
        p.go("echo ONG=$((3*5))\n")
        buf = await _doc(q, lambda b: "ONG=15" in b)
        check("chế độ ống vẫn chạy được lệnh", "ONG=15" in buf, repr(buf[-160:]))
        p.doi_co(120, 40)
        check("đổi cỡ ở chế độ ống không làm nổ gì (không có khổ giấy để báo)", p.cols == 120)
        p.dong()
        await asyncio.sleep(0.8)
        check("đóng phiên ống -> tiến trình chết", not p.song())
    finally:
        terminal.CO_PTY = that


if os.name != "nt":
    asyncio.run(_nhanh_ong())

print()
if _fails:
    print(f"{len(_fails)} test HỎNG: " + ", ".join(_fails))
    sys.exit(1)
print("Tất cả test terminal đã qua.")
