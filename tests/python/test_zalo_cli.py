"""Phần dùng chung để Javis chạy lại `zalo-agent-cli` (server/zalo_cli.py), cho plugin zalo-image và zalo-group.

    python tests/run.py zalo_cli      (KHÔNG mạng, không gọi npx thật)

Những chỗ ở đây đều ĐÃ HOẶC SUÝT gây hại khi gửi tin Zalo thật, nên mỗi cái có canary:
  1. THỨ TỰ THAM SỐ. Cờ nhiều giá trị (`--mention a b`) nuốt mọi tham số đứng sau nó, kể cả tham số vị trí; còn tham số bắt đầu
     bằng "-" ("- Họp lúc 9h") bị coi là cờ. Đã kiểm với chính Commander 14.0.3 mà CLI đóng gói: tham số vị trí đứng trước và cờ
     đứng sau; có tham số bắt đầu bằng "-" thì cờ đứng trước rồi `--`.
  2. MÃ THOÁT LÀ SỰ THẬT NỬA VỜI. CLI này không bao giờ thoát mã khác 0 khi Zalo từ chối (`error()` chỉ in "✗ ..." ra stderr, xem
     src/utils/output.js), nên chỉ nhìn `returncode == 0` là báo "đã gửi" cho cả những lần không gửi được. Thành công = mã 0 VÀ có
     JSON ở stdout.
  3. WINDOWS + cmd.exe. `npx.cmd` chạy qua `cmd /c` thì `& | ^ %` trong nội dung tin bị cmd diễn giải: vừa hỏng tin vừa là lỗ hổng
     chèn lệnh. Chạy `node npx-cli.js` thẳng; rơi về cmd thì từ chối tham số nguy hiểm.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import os
import sys
import tempfile
import time
import types
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import zalo_cli as Z  # noqa: E402

# Hermetic: thư mục cài trỏ vào chỗ trống và không bao giờ cài thật (không thì test đụng npm và mạng).
EMPTY = Path(tempfile.mkdtemp(prefix="zcli-empty-"))
Z.install_dir = lambda: EMPTY / "tools" / "zalo-agent-cli"
Z.AUTO_INSTALL = False

fails = []


def check(name, cond, them=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(them) + "]") if them and not cond else ""))
    if not cond:
        fails.append(name)


ESC = chr(27)


def with_env(nt: bool, which: dict, files: dict = None):
    """Giả lập môi trường: hệ điều hành, các lệnh tìm được, và file nào tồn tại."""
    Z.os = types.SimpleNamespace(name="nt" if nt else "posix", environ=os.environ, path=os.path)
    Z.shutil = types.SimpleNamespace(which=lambda n: which.get(n))
    real_is_file = Path.is_file
    Path.is_file = lambda self: str(self).replace("\\", "/") in (files or {}) or real_is_file(self)
    return real_is_file


real_os, real_shutil = Z.os, Z.shutil

# ============================================================
# 1. Thứ tự tham số
# ============================================================
rf = with_env(False, {"npx": "/usr/bin/npx"})
a = Z.build_argv(["msg", "send"], ["T1", "xin chào @Quý"], ["-t", "1", "--mention", "0:111:5", "9:222:4"])
check("tham số vị trí đứng TRƯỚC, cờ nhiều giá trị đứng CUỐI (nếu không --mention nuốt luôn threadId và nội dung)",
      a[a.index("send") + 1:] == ["T1", "xin chào @Quý", "-t", "1", "--mention", "0:111:5", "9:222:4"], a)
check("cờ --json đứng trước lệnh con, package ghim đúng", a[:4] == ["/usr/bin/npx", "-y", "zalo-agent-cli@1.6.2", "--json"]
      and a.index("--json") < a.index("msg"), a)

b = Z.build_argv(["msg", "send"], ["T1", "- họp lúc 9h"], ["-t", "1", "--mention", "0:111:5"])
check("nội dung bắt đầu bằng '-' thì cờ đứng trước, rồi `--`, rồi tham số vị trí (không bị coi là cờ)",
      b[b.index("send") + 1:] == ["-t", "1", "--mention", "0:111:5", "--", "T1", "- họp lúc 9h"], b)
c = Z.build_argv(["group", "note-create"], ["G1", "- ghi chú"], [])
check("không có cờ mà nội dung bắt đầu bằng '-' vẫn có `--`", c[c.index("note-create") + 1:] == ["--", "G1", "- ghi chú"], c)
d = Z.build_argv(["poll", "create"], ["G1", "Ăn gì?", "Phở", "Bún"], ["--multi", "--expire", "30"])
check("poll: câu hỏi và lựa chọn (biến thể) đứng trước cờ", d[d.index("create") + 1:] == ["G1", "Ăn gì?", "Phở", "Bún", "--multi", "--expire", "30"], d)
check("thiếu npx thì trả None chứ không đoán", (with_env(False, {}) and Z.build_argv(["msg", "send"], ["a", "b"])) is None)
Path.is_file = rf

# ============================================================
# 2. Windows: không đi qua cmd.exe
# ============================================================
NODE = "C:/Program Files/nodejs/node.exe"
CLI_JS = "C:/Program Files/nodejs/node_modules/npm/bin/npx-cli.js"
rf = with_env(True, {"npx": "C:/Program Files/nodejs/npx.cmd", "node": NODE}, {CLI_JS: True})
head = Z.npx_command()
check("CANARY: Windows có node + npx-cli.js thì chạy node THẲNG, không qua cmd.exe", head is not None and os.path.basename(head[0]).lower() == "node.exe"
      and head[1].replace("\\", "/") == CLI_JS, head)
argv = Z.build_argv(["msg", "send"], ["T1", "Họp & chốt, giảm 50%!"], [])
check("nên nội dung có & % ! đi nguyên vẹn và KHÔNG bị chặn", Z.unsafe_for_cmd(argv) is None and "Họp & chốt, giảm 50%!" in argv, argv)
Path.is_file = rf

rf = with_env(True, {"npx": "C:/Program Files/nodejs/npx.cmd", "node": None}, {})
head = Z.npx_command()
check("không tìm thấy npx-cli.js thì mới rơi về cmd.exe /c", head[:2] == ["cmd.exe", "/c"], head)
bad = Z.build_argv(["msg", "send"], ["T1", "a & calc"], [])
check("CANARY: rơi về cmd mà nội dung có ký tự cmd diễn giải thì TỪ CHỐI (chèn lệnh)", "&" in (Z.unsafe_for_cmd(bad) or ""), Z.unsafe_for_cmd(bad))
for ch in ("|", "<", ">", "^", "%", "!", '"', "\n"):
    check(f"cmd fallback từ chối ký tự {ch!r}", Z.unsafe_for_cmd(Z.build_argv(["msg", "send"], ["T1", f"x{ch}y"], [])) is not None)
ok_argv = Z.build_argv(["msg", "send"], ["T1", "Họp lúc 9h nhé"], ["-t", "1"])
check("cmd fallback vẫn cho tin bình thường", Z.unsafe_for_cmd(ok_argv) is None)
Path.is_file = rf
Z.os, Z.shutil = real_os, real_shutil

# ============================================================
# 3. Đọc kết quả: mã 0 chưa phải là thành công
# ============================================================
ok, data, err = Z.interpret(0, '{"message":{"msgId":"9"}}', "")
check("mã 0 + JSON = thành công, trả dữ liệu", ok and data["message"]["msgId"] == "9" and err == "")
ok, data, err = Z.interpret(0, "", ESC + "[31m  ✗ Create poll failed: Bạn không có quyền" + ESC + "[39m\n")
check("CANARY: mã 0 nhưng stdout trống + dòng ✗ ở stderr = THẤT BẠI (CLI không đặt mã thoát khác 0)", ok is False and "không có quyền" in err, err)
check("và câu lỗi sạch mã màu ANSI", ESC not in err and "✗" not in err, repr(err))
ok, data, err = Z.interpret(0, "", "")
check("mã 0 mà không có gì cả cũng là thất bại, có lý do", ok is False and err != "")
ok, data, err = Z.interpret(1, "", "Thread not found")
check("mã khác 0 thì thất bại kèm nguyên nhân", ok is False and "Thread not found" in err and "mã 1" in err)
ok, data, err = Z.interpret(None, None, "quá 120 giây chưa xong")
check("hết giờ thì nói hết giờ", ok is False and "120" in err)
check("JSON kèm dòng trạng thái xung quanh vẫn đọc được", Z.parse_json('đang tải…\n{"a": [1, 2]}\nxong') == {"a": [1, 2]})
check("không phải JSON thì None (không đoán)", Z.parse_json("hello") is None and Z.parse_json("") is None and Z.parse_json(None) is None)
check("mảng JSON cũng đọc được", Z.parse_json("[1,2]") == [1, 2])

# ============================================================
# 3b. `✗` in ra stdout cũng là lỗi
# ============================================================
ok, data, err = Z.interpret(0, "✗ Not logged in. Run: zalo-agent login", "")
check("mã 0 + '✗ ...' ở STDOUT (chưa đăng nhập) = thất bại, câu lỗi sạch dấu ✗", ok is False and err == "Not logged in. Run: zalo-agent login", err)

# ============================================================
# 3c. Bản đã cài sẵn: chạy thẳng bằng Node, không qua npx
# ============================================================
ROOT_INST = Path(tempfile.mkdtemp(prefix="zcli-inst-")) / "tools" / "zalo-agent-cli"
Z.install_dir = lambda: ROOT_INST
ENTRY = ROOT_INST / "node_modules" / "zalo-agent-cli" / "src" / "index.js"
rf = with_env(False, {"npx": "/usr/bin/npx", "node": "/usr/bin/node", "npm": "/usr/bin/npm"})
check("chưa cài thì không chạy thẳng, vẫn dùng npx", Z.direct_command() is None and Z.build_argv(["msg", "send"], ["a", "b"])[:4] == ["/usr/bin/npx", "-y", Z.CLI_PACKAGE, "--json"])

ENTRY.parent.mkdir(parents=True)
ENTRY.write_text("", encoding="utf-8")
check("CANARY: có index.js nhưng CHƯA có dấu cài xong (cài dở) thì KHÔNG dùng", Z.cli_entry() is None and Z.direct_command() is None)
(ROOT_INST / Z._INSTALL_MARK).write_text("zalo-agent-cli@1.0.0", encoding="utf-8")
check("CANARY: dấu cài của phiên bản KHÁC bản đang ghim thì không dùng (đổi phiên bản ghim là cài lại)", Z.cli_entry() is None)
(ROOT_INST / Z._INSTALL_MARK).write_text(Z.CLI_PACKAGE, encoding="utf-8")
check("cài xong đúng bản ghim thì dùng được", Z.cli_entry() == ENTRY and Z.direct_command() == ["/usr/bin/node", str(ENTRY)], Z.direct_command())
a = Z.build_argv(["msg", "send"], ["T1", "xin chào"], ["-t", "1", "--mention", "0:111:5"])
check("chạy thẳng: node index.js --json <lệnh>, KHÔNG có npx và -y", a == ["/usr/bin/node", str(ENTRY), "--json", "msg", "send", "T1", "xin chào", "-t", "1", "--mention", "0:111:5"], a)
b = Z.build_argv(["msg", "send"], ["T1", "- họp"], ["-t", "1"])
check("chạy thẳng vẫn giữ luật thứ tự: tham số bắt đầu bằng '-' thì cờ trước rồi `--`", b[b.index("send") + 1:] == ["-t", "1", "--", "T1", "- họp"], b)
ENTRY.unlink()
check("mất index.js thì quay về npx", Z.cli_entry() is None and Z.build_argv(["msg", "send"], ["a", "b"])[:2] == ["/usr/bin/npx", "-y"])
ENTRY.write_text("", encoding="utf-8")
Z.shutil = types.SimpleNamespace(which=lambda n: {"npx": "/usr/bin/npx"}.get(n))
check("có bản cài nhưng máy không có node thì quay về npx", Z.direct_command() is None)
Z.shutil = types.SimpleNamespace(which=lambda n: {"npx": "/usr/bin/npx", "node": "/usr/bin/node", "npm": "/usr/bin/npm"}.get(n))

rf2 = with_env(True, {"npx": "C:/Program Files/nodejs/npx.cmd", "node": "C:/Program Files/nodejs/node.exe"}, {})
c = Z.build_argv(["msg", "send"], ["T1", "Họp & chốt 50%"], [])
check("CANARY: Windows chạy thẳng bằng node.exe thì không qua cmd.exe, nội dung có & % đi nguyên vẹn",
      os.path.basename(c[0]).lower() == "node.exe" and Z.unsafe_for_cmd(c) is None and "Họp & chốt 50%" in c, c)
Path.is_file = rf2
Z.os, Z.shutil = real_os, real_shutil
Path.is_file = rf

# ============================================================
# 3d. Cài ngầm
# ============================================================
Z.os, Z.shutil = real_os, real_shutil


def fresh_install_dir():
    global ROOT_INST
    ROOT_INST = Path(tempfile.mkdtemp(prefix="zcli-inst-")) / "tools" / "zalo-agent-cli"
    Z.install_dir = lambda: ROOT_INST
    Z._install_state.update(task=None, failed_at=0.0)


GHI = ("import sys, pathlib\n"
       "root = pathlib.Path(sys.argv[sys.argv.index('--prefix') + 1])\n"
       "sys.stderr.write(' '.join(sys.argv[1:]))\n"
       "(root / 'node_modules' / 'zalo-agent-cli' / 'src').mkdir(parents=True)\n"
       "(root / 'node_modules' / 'zalo-agent-cli' / 'src' / 'index.js').write_text('')\n")
fresh_install_dir()
Z.npm_command = lambda: [sys.executable, "-c", GHI]
ok = asyncio.run(Z._install())
check("cài thật (npm giả): ghi index.js VÀ dấu cài xong", ok and Z.cli_entry() is not None and (ROOT_INST / "package.json").is_file(), ok)
check("CANARY: dấu cài chỉ có SAU khi index.js đã có (cài dở không được coi là xong)", (ROOT_INST / Z._INSTALL_MARK).read_text(encoding="utf-8") == Z.CLI_PACKAGE)

fresh_install_dir()
Z.npm_command = lambda: [sys.executable, "-c", "import sys; sys.exit(3)"]
ok = asyncio.run(Z._install())
check("npm thoát mã khác 0 thì cài hỏng, không có dấu cài", ok is False and Z.cli_entry() is None and not (ROOT_INST / Z._INSTALL_MARK).exists())

fresh_install_dir()
Z.npm_command = lambda: [sys.executable, "-c", "pass"]
ok = asyncio.run(Z._install())
check("npm báo xong mà không thấy index.js thì cài hỏng", ok is False and Z.cli_entry() is None)

fresh_install_dir()
Z.npm_command = lambda: [sys.executable, "-c", "import time; time.sleep(30)"]
Z.INSTALL_TIMEOUT = 1
ok = asyncio.run(Z._install())
Z.INSTALL_TIMEOUT = 300
check("npm quá giờ thì giết và báo hỏng, không treo", ok is False and Z.cli_entry() is None)

# start_install: chỉ một lần, hỏng thì chờ, đã cài thì thôi
CHAY = []


async def npm_gia_ok():
    CHAY.append(1)
    await asyncio.sleep(0.05)
    return True


async def npm_gia_hong():
    CHAY.append(1)
    return False


async def kich_hoat(n=3):
    for _ in range(n):
        Z.start_install()
    t = Z._install_state["task"]
    if t is not None:
        await t


Z.AUTO_INSTALL = True
Z.npm_command = lambda: ["npm"]
fresh_install_dir()
Z._install = npm_gia_hong
asyncio.run(kich_hoat())
check("gọi start_install nhiều lần một lúc thì chỉ chạy MỘT lần", len(CHAY) == 1, CHAY)
check("cài hỏng thì ghi giờ hỏng", Z._install_state["failed_at"] > 0)
CHAY.clear()
asyncio.run(kich_hoat())
check("CANARY: mới hỏng thì KHÔNG thử lại ở lượt sau (không cài lại ở mọi câu trả lời)", CHAY == [])
Z._install_state["failed_at"] = time.time() - Z.INSTALL_RETRY - 1
asyncio.run(kich_hoat())
check("qua thời gian chờ thì thử lại", len(CHAY) == 1, CHAY)

CHAY.clear()
fresh_install_dir()
Z.AUTO_INSTALL = False
asyncio.run(kich_hoat())
check("AUTO_INSTALL tắt thì không cài", CHAY == [])
Z.AUTO_INSTALL = True
Z.npm_command = lambda: None
asyncio.run(kich_hoat())
check("không có npm thì bỏ qua, không cài, không lỗi", CHAY == [])
Z.npm_command = lambda: ["npm"]
Z.start_install()
check("gọi ngoài vòng lặp sự kiện thì không làm gì, không lỗi", CHAY == [] and Z._install_state["task"] is None)
ENTRY2 = ROOT_INST / "node_modules" / "zalo-agent-cli" / "src" / "index.js"
ENTRY2.parent.mkdir(parents=True)
ENTRY2.write_text("", encoding="utf-8")
(ROOT_INST / Z._INSTALL_MARK).write_text(Z.CLI_PACKAGE, encoding="utf-8")
asyncio.run(kich_hoat())
check("đã cài xong thì không cài nữa", CHAY == [])

# run_cli: chưa cài thì kích hoạt cài ngầm, đã cài thì không
KICH = []
real_start = Z.start_install
Z.start_install = lambda: KICH.append(1)
real_run = Z.run


async def run_gia(argv, home, timeout=120):
    return 0, "{}", ""


Z.run = run_gia
asyncio.run(Z.run_cli({"home": "/h"}, ["msg", "send"], ["T", "x"]))
check("đã cài xong: run_cli không kích hoạt cài", KICH == [])
fresh_install_dir()
asyncio.run(Z.run_cli({"home": "/h"}, ["msg", "send"], ["T", "x"]))
check("chưa cài: run_cli kích hoạt cài ngầm (lượt này vẫn chạy bằng npx)", KICH == [1], KICH)
Z.start_install, Z.run = real_start, real_run
Z.AUTO_INSTALL = False

# ============================================================
# 4. Chạy tiến trình con thật: HOME đúng, đọc đủ đầu ra, hết giờ thì giết
# ============================================================
home = tempfile.mkdtemp(prefix="javis-zcli-")
code = "import os,sys;print(os.environ['HOME']);print(os.environ['USERPROFILE']);sys.stderr.write('loi')"
rc, out, err = asyncio.run(Z.run([sys.executable, "-c", code], home))
check("CANARY: tiến trình con nhận HOME và USERPROFILE là thư mục phiên (không thì CLI đòi quét QR lại)",
      rc == 0 and out.split() == [home, home] and err == "loi", (rc, out, err))
rc, out, err = asyncio.run(Z.run([sys.executable, "-c", "import time;time.sleep(30)"], home, timeout=1))
check("quá giờ thì giết tiến trình và báo hết giờ, không treo", rc is None and out is None and "1 giây" in err, (rc, err))

# ============================================================
# 5. Nhận ra "quá giờ" (tin có thể đã đi) và thư mục phiên
# ============================================================
check("CANARY: câu báo quá giờ đi qua interpret vẫn được is_timeout nhận ra (người gọi không gửi lại bằng đường khác)",
      Z.is_timeout(Z.interpret(None, None, "quá 40 " + Z.TIMEOUT_MARK)[2]))
check("lỗi thường không phải quá giờ", not Z.is_timeout("Thread not found") and not Z.is_timeout("") and not Z.is_timeout(None))
check("home_of lấy HOME rồi USERPROFILE, rỗng nếu không có",
      Z.home_of({"env": {"HOME": "/h/a"}}) == "/h/a" and Z.home_of({"env": {"USERPROFILE": "C:/u"}}) == "C:/u"
      and Z.home_of({"env": {}}) == "" and Z.home_of({}) == "" and Z.home_of(None) == "")
ok, data, err = asyncio.run(Z.run_cli({"home": ""}, ["msg", "send"], ["T1", "hi"]))
check("không có thư mục phiên thì từ chối chạy, có lý do", ok is False and "thư mục phiên" in err)

# ============================================================
# 4b. Chọn kết nối: nhiều tài khoản thì hỏi lại
# ============================================================
ONE = [{"id": "c1", "label": "Zalo chính", "home": "/h/a"}]
TWO = ONE + [{"id": "c2", "label": "Zalo phụ", "home": "/h/b"}]
check("một tài khoản thì chọn luôn", Z.pick_connection(ONE, "")[0]["id"] == "c1")
c, why = Z.pick_connection(TWO, "")
check("CANARY: hai tài khoản mà không nêu rõ thì TỪ CHỐI và liệt kê", c is None and "Zalo chính" in why and "Zalo phụ" in why)
check("nêu connection_id thì chọn đúng", Z.pick_connection(TWO, "c2")[0]["home"] == "/h/b")
check("connection_id lạ thì báo lỗi", Z.pick_connection(TWO, "zz")[0] is None)
check("không có kết nối nào thì báo lỗi", Z.pick_connection([], "")[0] is None)

# ============================================================
# 4c. Kiểm tra điều kiện
# ============================================================
Z.connections = lambda: []
Z.shutil = types.SimpleNamespace(which=lambda n: None)
check("chưa có Node thì nói rõ", "nodejs.org" in (Z.check() or ""))
Z.shutil = types.SimpleNamespace(which=lambda n: "/usr/bin/npx")
check("có Node mà chưa đấu Zalo thì chỉ chỗ cần bấm", "trang Kết nối" in (Z.check() or ""))
Z.connections = lambda: ONE
check("đủ điều kiện thì None", Z.check() is None)

check("không dùng em dash trong file này", chr(0x2014) not in open(__file__, encoding="utf-8").read()
      and chr(0x2014) not in (SERVER / "zalo_cli.py").read_text(encoding="utf-8"))

if fails:
    print("\nFAIL - test_zalo_cli: " + str(len(fails)) + " lỗi: " + ", ".join(fails))
    sys.exit(1)
print("\nOK - test_zalo_cli: tất cả pass")
