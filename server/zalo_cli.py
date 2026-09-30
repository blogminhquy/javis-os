"""Chạy lại CHÍNH `zalo-agent-cli` cho các plugin Zalo (`zalo-image`, `zalo-group`).

Vì sao có file này. MCP chuẩn của `zalo-agent-cli` bản 1.6.2 chỉ phơi bảy tool, và tool gửi tin chỉ nhận CHỮ, trong khi chính CLI đó đã
có lệnh gửi ảnh/file, tag người (`msg send --mention`), ghi chú nhóm (`group note-create`), nhắc hẹn (`reminder create`) và poll
(`poll create`). Javis gọi lại đúng CLI đó bằng lệnh con nó đã có,
với `HOME` trỏ vào thư mục phiên của kết nối Zalo đang đăng nhập (xem `zalo_login.py`): không fork package Node, không viết lại giao
thức, không bắt quét QR lần hai. Bản 1.6.2 là bản MỚI NHẤT trên npm, nên chờ upstream phơi thêm tool là chờ vô hạn.

Bẫy cần biết (đều đã dính hoặc suýt dính):
  - Windows: `npx` là `npx.cmd`, chạy qua `cmd.exe /c` thì cmd DIỄN GIẢI `& | < > ^ % !` trong tham số. Nội dung tin nhắn là chữ
    tự do ("Họp & chốt", "giảm 50%") nên đó vừa là lỗi vừa là lỗ hổng chèn lệnh. Nên chạy `node npx-cli.js` thẳng, không qua cmd.
    Chỉ khi không tìm thấy mới rơi về cmd, và lúc đó TỪ CHỐI tham số chứa ký tự nguy hiểm thay vì đoán cách thoát.
  - Tham số bắt đầu bằng "-" ("- Họp lúc 9h") bị Commander coi là cờ. Dùng `--` chặn trước các tham số vị trí.
  - CLI KHÔNG thoát mã khác 0 khi Zalo từ chối (xem `interpret`).
  - Tốc độ: mỗi lần `npx -y zalo-agent-cli@...` mất khoảng 3 giây chỉ để khởi động (đo trên Windows), cộng thêm việc HOME của
    phiên Zalo là thư mục riêng nên trên Linux npx còn có thể tải lại gói vào cache của HOME đó. Nên Javis cài ngầm MỘT bản ghim vào
    thư mục của mình (`install_dir`) và chạy thẳng `node index.js`; chưa cài xong thì vẫn chạy bằng npx như cũ.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import sys
import time
from pathlib import Path
from typing import Any, List, Optional, Tuple

import winproc

CONNECTOR_ID = "zalo"
CLI_PACKAGE = "zalo-agent-cli@1.6.2"     # ghim đúng bản mà connector Zalo đang chạy
DEFAULT_TIMEOUT = 120                     # tải file lên Zalo có thể lâu, nhưng không lâu vô hạn
TIMEOUT_MARK = "giây chưa xong"          # đuôi câu báo hết giờ; `is_timeout` nhận ra câu đó
AUTO_INSTALL = True                       # test tắt cờ này để không cài thật
INSTALL_TIMEOUT = 300                     # giây cho một lần `npm install`
INSTALL_RETRY = 1800                      # cài hỏng thì chờ chừng này giây mới thử lại (không cài lại ở mọi câu trả lời)
_INSTALL_MARK = ".javis-installed"        # ghi SAU KHI cài xong; cài dở (tắt máy giữa chừng) thì không có dấu này nên không dùng
_install_state: dict = {"task": None, "failed_at": 0.0}

# Ký tự mà cmd.exe diễn giải dù nằm trong ngoặc kép (hoặc khi tham số không có khoảng trắng nên không được bọc).
_CMD_UNSAFE = re.compile(r'[&|<>^%!"\r\n]')


def home_of(conn: Optional[dict]) -> str:
    """Thư mục phiên Zalo của một kết nối (bản đầy đủ có `env`, như `zalo_personal_channel.ket_noi_theo_id` trả). Rỗng nếu không rõ."""
    env = (conn or {}).get("env") or {}
    return str(env.get("HOME") or env.get("USERPROFILE") or "")


def connections() -> List[dict]:
    """Các kết nối Zalo đang BẬT: `[{id, label, home}]`, `home` là thư mục phiên của kết nối.

    Dùng `mcp_store.resolved()` chứ không `list_connections()`: bản public che mất `config`, mà đường dẫn HOME nằm trong đó.
    `resolved()` cũng đã áp đúng luật fallback khi kết nối chưa ghi home_dir - chép lại luật đó ở đây là hai bản trôi lệch.
    """
    try:
        import mcp_store
    except Exception:
        return []
    out = []
    for c in mcp_store.resolved(enabled_only=True):
        if c.get("connector_id") != CONNECTOR_ID:
            continue
        home = home_of(c)
        if home:
            out.append({"id": c["id"], "label": c.get("label") or "Zalo", "home": home})
    return out


def pick_connection(conns: List[dict], connection_id: str = "") -> Tuple[Optional[dict], str]:
    """Chọn MỘT kết nối để gửi. Nhiều tài khoản mà đoán bừa là gửi đi dưới danh tính người khác, hỏi lại rẻ hơn nhiều.
    Trả `(kết nối, "")` hoặc `(None, lý do)`."""
    cid = str(connection_id or "").strip()
    if cid:
        hit = [c for c in conns if c["id"] == cid]
        return (hit[0], "") if hit else (None, f"không có kết nối Zalo nào id '{cid}'.")
    if len(conns) == 1:
        return conns[0], ""
    ds = "; ".join(f"{c['label']} (id={c['id']})" for c in conns)
    return None, f"đang có {len(conns)} tài khoản Zalo, hãy nêu rõ connection_id. Danh sách: {ds}"


def check() -> Optional[str]:
    """Lý do CHƯA dùng được (người đọc hiểu và làm theo), hoặc None nếu ổn."""
    if not shutil.which("npx"):
        return ("Máy chạy Javis chưa có Node.js 20+ (lệnh npx) nên chưa dùng được tính năng này. "
                "Cài tại nodejs.org rồi thử lại.")
    if not connections():
        return ("Chưa đấu tài khoản Zalo nào. Vào trang Kết nối, chọn 'Zalo Agent MCP', "
                "quét QR bằng app Zalo rồi gọi lại tool này.")
    return None


def install_dir() -> Path:
    """Thư mục Javis tự cài bản ghim của CLI. Nằm trong state (volume trên Docker) nên sống qua khởi động lại và cập nhật ảnh."""
    import config
    return Path(config.STATE_DIR) / "tools" / "zalo-agent-cli"


def cli_entry() -> Optional[Path]:
    """`index.js` của bản đã cài, hoặc None nếu chưa cài xong / cài bản khác (đổi phiên bản ghim thì cài lại)."""
    root = install_dir()
    try:
        if (root / _INSTALL_MARK).read_text(encoding="utf-8").strip() != CLI_PACKAGE:
            return None
    except OSError:
        return None
    entry = root / "node_modules" / "zalo-agent-cli" / "src" / "index.js"
    return entry if entry.is_file() else None


def direct_command() -> Optional[List[str]]:
    """`[node, index.js]` khi đã cài sẵn: bỏ bước npx tìm gói mỗi lần. Windows cũng không qua cmd.exe."""
    entry = cli_entry()
    node = shutil.which("node")
    return [node, str(entry)] if entry and node else None


def npm_command() -> Optional[List[str]]:
    """Đầu lệnh chạy npm, cùng cách với `npx_command`. Windows không tìm thấy npm-cli.js thì trả None: bỏ qua việc cài ngầm
    (đường npx vẫn chạy được) chứ không đưa đường dẫn vào cmd.exe."""
    npm = shutil.which("npm")
    if not npm:
        return None
    if os.name != "nt":
        return [npm]
    node = shutil.which("node")
    if node:
        cli = Path(node).parent / "node_modules" / "npm" / "bin" / "npm-cli.js"
        if cli.is_file():
            return [node, str(cli)]
    return None


async def _install() -> bool:
    head = npm_command()
    if head is None:
        return False
    root = install_dir()
    try:
        root.mkdir(parents=True, exist_ok=True)
        pkg = root / "package.json"
        if not pkg.exists():
            pkg.write_text('{"name": "javis-zalo-cli", "private": true}\n', encoding="utf-8")
        (root / _INSTALL_MARK).unlink(missing_ok=True)
    except OSError as e:
        print(f"[zalo-cli] không tạo được thư mục cài: {e}", file=sys.stderr)
        return False
    argv = head + ["install", "--prefix", str(root), "--no-audit", "--no-fund", "--no-package-lock",
                   "--loglevel=error", CLI_PACKAGE]
    proc = await asyncio.create_subprocess_exec(
        *argv, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        stdin=asyncio.subprocess.DEVNULL, **winproc.kwargs_no_window())
    try:
        _out, err = await asyncio.wait_for(proc.communicate(), timeout=INSTALL_TIMEOUT)
    except asyncio.TimeoutError:
        try:
            proc.kill()
        except Exception:
            pass
        try:
            await asyncio.wait_for(proc.wait(), 5)
        except Exception:
            pass
        print(f"[zalo-cli] cài quá {INSTALL_TIMEOUT} giây, bỏ", file=sys.stderr)
        return False
    if proc.returncode != 0:
        print("[zalo-cli] cài lỗi: " + _ANSI.sub("", (err or b"").decode("utf-8", "replace")).strip()[-300:], file=sys.stderr)
        return False
    if not (root / "node_modules" / "zalo-agent-cli" / "src" / "index.js").is_file():
        print("[zalo-cli] cài xong nhưng không thấy index.js", file=sys.stderr)
        return False
    (root / _INSTALL_MARK).write_text(CLI_PACKAGE, encoding="utf-8")
    return True


async def _install_guarded() -> None:
    try:
        ok = await _install()
    except Exception as e:      # noqa: BLE001 - cài ngầm hỏng không được làm hỏng lượt đang chạy
        print(f"[zalo-cli] cài lỗi: {type(e).__name__}: {e}", file=sys.stderr)
        ok = False
    if ok:
        print("[zalo-cli] đã cài xong bản ghim, từ nay chạy thẳng bằng Node", file=sys.stderr)
    else:
        _install_state["failed_at"] = time.time()


def start_install() -> None:
    """Cài NGẦM bản ghim vào `install_dir` (một lần) để các lần sau chạy thẳng bằng Node. Gọi thoải mái: đã cài, đang cài, mới hỏng
    (chờ `INSTALL_RETRY`), hay không có vòng lặp sự kiện thì không làm gì. Lượt đang chạy KHÔNG chờ nó, vẫn đi bằng npx."""
    if not AUTO_INSTALL or cli_entry() is not None:
        return
    t = _install_state["task"]
    if t is not None and not t.done():
        return
    if time.time() - float(_install_state["failed_at"]) < INSTALL_RETRY:
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    if npm_command() is None:
        return
    _install_state["task"] = loop.create_task(_install_guarded())


def npx_command() -> Optional[List[str]]:
    """Đầu lệnh chạy npx. Windows thì chạy `node npx-cli.js` THẲNG để không qua cmd.exe (xem đầu file); rơi về
    `cmd.exe /c npx.cmd` chỉ khi không tìm thấy, và khi đó `run_cli` từ chối tham số nguy hiểm."""
    npx = shutil.which("npx")
    if not npx:
        return None
    if os.name != "nt":
        return [npx]
    node = shutil.which("node")
    if node:
        cli = Path(node).parent / "node_modules" / "npm" / "bin" / "npx-cli.js"
        if cli.is_file():
            return [node, str(cli)]
    return ["cmd.exe", "/c", npx]


def build_argv(command: List[str], positionals: Optional[List[str]] = None,
               options: Optional[List[str]] = None) -> Optional[List[str]]:
    """Dựng `node index.js --json <lệnh con> …` (bản đã cài sẵn) hoặc `npx -y zalo-agent-cli@… --json <lệnh con> …`.

    `command` là lệnh con (`["msg", "send"]`), `positionals` là chữ TỰ DO (nội dung tin), `options` là các cờ do mã Javis viết
    (`["-t", "1", "--mention", "0:123:5"]`).

    Thứ tự quan trọng vì Commander (thư viện đọc lệnh của CLI):
      - cờ có giá trị NHIỀU (`--mention <specs...>`) nuốt mọi tham số đứng sau nó, kể cả tham số vị trí. Nên mặc định đặt tham số vị
        trí TRƯỚC, cờ SAU;
      - nhưng tham số vị trí bắt đầu bằng "-" ("- Họp lúc 9h") bị coi là cờ. Khi đó đặt cờ trước rồi `--` rồi tham số vị trí.
    """
    direct = direct_command()
    if direct:
        argv = direct + ["--json"] + list(command)
    else:
        head = npx_command()
        if head is None:
            return None
        argv = head + ["-y", CLI_PACKAGE, "--json"] + list(command)
    pos = [str(p) for p in (positionals or [])]
    opts = [str(o) for o in (options or [])]
    if any(p.startswith("-") for p in pos):
        argv += opts + ["--"] + pos
    else:
        argv += pos + opts
    return argv


def uses_cmd(argv: List[str]) -> bool:
    return bool(argv) and os.path.basename(argv[0]).lower() == "cmd.exe"


def unsafe_for_cmd(argv: List[str]) -> Optional[str]:
    """Nếu lệnh sẽ đi qua cmd.exe mà có tham số chứa ký tự cmd diễn giải thì trả lý do, để chặn trước khi chạy."""
    if not uses_cmd(argv):
        return None
    for a in argv[3:]:
        if _CMD_UNSAFE.search(a):
            return ("máy Windows này không có sẵn npx-cli.js nên nội dung có ký tự & | < > ^ % ! \" hoặc xuống dòng "
                    "không gửi an toàn được. Bỏ các ký tự đó đi, hoặc cài lại Node.js 20+ bản chuẩn.")
    return None


async def run(argv: List[str], home: str, timeout: int = DEFAULT_TIMEOUT) -> Tuple[Optional[int], Optional[str], str]:
    """Chạy một lệnh con với HOME trỏ vào phiên Zalo. Trả `(mã thoát, stdout, stderr)`; hết giờ thì `(None, None, lý do)`."""
    env = dict(os.environ)
    env["HOME"] = home
    env["USERPROFILE"] = home
    proc = await asyncio.create_subprocess_exec(
        *argv, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        stdin=asyncio.subprocess.DEVNULL, env=env, **winproc.kwargs_no_window())
    try:
        out, err = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        try:
            proc.kill()
        except Exception:
            pass
        try:      # thu xác tiến trình vừa giết, kẻo để lại pipe mở (Windows in traceback lúc dọn rác)
            await asyncio.wait_for(proc.wait(), 5)
        except Exception:
            pass
        return None, None, f"quá {timeout} {TIMEOUT_MARK}"

    def dec(b):
        return (b or b"").decode("utf-8", "replace")

    return proc.returncode, dec(out), dec(err)


def parse_json(text: str) -> Any:
    """Lấy JSON từ đầu ra của CLI. Nó có thể in kèm dòng trạng thái quanh JSON nên tìm khối `{...}` hoặc `[...]` đầu tiên đọc
    được. Không có thì trả None (người gọi coi là "không đọc được", không đoán)."""
    s = str(text or "").strip()
    if not s:
        return None
    try:
        return json.loads(s)
    except ValueError:
        pass
    dec = json.JSONDecoder()
    for i, ch in enumerate(s):
        if ch in "{[":
            try:
                obj, _ = dec.raw_decode(s[i:])
                return obj
            except ValueError:
                continue
    return None


_ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


def interpret(rc: Optional[int], out: Optional[str], err: str) -> Tuple[bool, Any, str]:
    """Đọc kết quả một lệnh `--json` của CLI thành `(ok, dữ liệu, lỗi)`.

    QUAN TRỌNG: CLI này KHÔNG đặt mã thoát khác 0 khi lệnh hỏng. Mọi lệnh bọc trong `try { ... } catch (e) { error(e.message) }` mà
    `error()` chỉ in một dòng "✗ ..." ra stderr rồi thoát mã 0 (đọc `src/utils/output.js`). Nên chỉ nhìn `rc == 0` là báo "đã gửi" cho cả
    những lần Zalo từ chối. Ở chế độ `--json`, lệnh THÀNH CÔNG luôn in JSON ra stdout, còn lệnh hỏng thì stdout trống; vậy thành công =
    mã thoát 0 VÀ có JSON. Lỗi lấy từ các dòng "✗" ở stderr.
    """
    if rc is None:
        return False, None, f"Zalo {err}"
    if rc != 0:
        tail = _ANSI.sub("", (err or out or "")).strip()[-400:]
        return False, None, f"zalo-agent-cli thoát mã {rc}. {tail}"
    data = parse_json(out)
    if data is None:
        clean = _ANSI.sub("", err or "")
        # Dòng "✗ ..." thường ở stderr nhưng có lệnh in ra stdout ("✗ Not logged in. Run: zalo-agent login" khi chưa có phiên).
        both = clean + "\n" + _ANSI.sub("", out or "")
        marks = [ln.strip().lstrip("✗").strip() for ln in both.splitlines() if "✗" in ln]
        why = "; ".join(m for m in marks if m) or clean.strip()[-300:] or (out or "").strip()[-300:] or "không có phản hồi"
        return False, None, why
    return True, data, ""


def is_timeout(err: str) -> bool:
    """Lỗi này là do quá giờ? Khi đó tin có thể ĐÃ đi rồi (CLI gửi xong mới bị giết), nên người gọi KHÔNG được gửi lại bằng đường khác."""
    return TIMEOUT_MARK in str(err or "")


async def run_cli(conn: dict, command: List[str], positionals: Optional[List[str]] = None,
                  options: Optional[List[str]] = None, timeout: int = DEFAULT_TIMEOUT) -> Tuple[bool, Any, str]:
    """Chạy một lệnh Zalo trong phiên của `conn` (`{"home": ...}`) và trả `(ok, dữ liệu JSON, lỗi)`. Lỗi luôn là câu người đọc hiểu
    được (không phải traceback)."""
    home = str((conn or {}).get("home") or "")
    if not home:
        return False, None, "kết nối Zalo này chưa có thư mục phiên"
    if direct_command() is None:
        start_install()
    argv = build_argv(command, positionals, options)
    if argv is None:
        return False, None, "máy chưa có Node.js 20+ (lệnh npx)"
    why = unsafe_for_cmd(argv)
    if why:
        return False, None, why
    rc, out, err = await run(argv, home, timeout)
    return interpret(rc, out, err)
