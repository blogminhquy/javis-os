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
import re
import sys
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
        check("là pty THẬT (có /dev/pts) chứ không phải ống", "/dev/pts" in buf, repr(buf[-160:]))
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
    them = []
    while len([x for x in terminal.KHO._phien.values() if x.song()]) < terminal.MAX_PHIEN:
        them.append(terminal.KHO.mo("", "/tmp", 80, 24, asyncio.get_running_loop()))
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
# 5. Nhánh ỐNG (Windows) - ép chạy trên mọi hệ, vì không ai ngồi Linux thử được nhánh này
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
