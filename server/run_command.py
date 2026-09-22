"""`javis_run_command`: chạy MỘT lệnh trong thư mục làm việc của phiên, có rào.

Vì sao KHÔNG dùng PTY của `terminal.py`
--------------------------------------
Javis đã có một terminal thật cho NGƯỜI. Không giao nó cho model, vì chính docstring của file
đó ghi:

    Shell thừa kế env của server (trong đó có API key trong .env) - đúng như mọi terminal
    khác của chủ máy, nhưng cần biết là nó ở đó.  (terminal.py:29)

Cộng thêm: PTY là shell SỐNG LÂU, có trạng thái (biến môi trường vừa export, thư mục vừa cd,
tiến trình nền vừa chạy). Giao cho model nghĩa là cấp cả khoá lẫn một phiên không ai kiểm được.

Tool này ngược lại: MỘT lệnh, MỘT lần, không trạng thái, env lọc trắng, có trần thời gian, có
trần output, có audit.

Ba mức quyền
------------
Lấy thẳng từ chip của phiên Coding (`coding_store`), không phát minh thang mới:

  suggest  không chạy gì cả, trả về lệnh đề xuất dưới dạng chữ
  auto     chỉ lệnh trong allowlist, và chỉ trong thư mục làm việc
  full     chạy đầy đủ

Allowlist của mức `auto` phải VIẾT RA THÀNH DANH SÁCH, không để mỗi lần đoán. Đây là lần đầu
Javis cần một allowlist lệnh thật: Codex chỉ chặn ở tầng sandbox (`aux_engine.py:18-21`), còn
Claude Code có allowlist nhưng là của riêng CLI đó.

Không chạy qua shell
--------------------
Lệnh được TÁCH bằng `shlex.split` rồi chạy bằng `subprocess` với cờ shell TẮT. Nghĩa là
`&&`, `||`, `;`, `|`, `>`, backtick và `$(...)` không có nghĩa gì: chúng chỉ thành tham số
trần của chương trình. Đây là rào quan trọng nhất của cả file, vì nếu chạy qua shell thì
allowlist chỉ cần một dấu chấm phẩy là vô dụng.
"""
from __future__ import annotations

import os
import shlex
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import winproc         # cờ CREATE_NO_WINDOW: lệnh con không nháy cửa sổ đen trên Windows
from coding_ctx import AUTO, FULL, SUGGEST, CodingToolContext

# Trần thời gian một lệnh, giây. Mặc định vừa đủ cho một lượt test; trần trên chặn model tự
# đặt 2 tiếng rồi treo cả lượt chat.
TIMEOUT_MAC_DINH = 120
TIMEOUT_TOI_DA = 900

# Trần output trả về model. Cả một `pytest -v` của repo lớn có thể ra vài trăm nghìn ký tự;
# nhét hết vào một lượt web là vừa chậm vừa đầy ngữ cảnh. Giữ đầu và ĐUÔI: lỗi thật gần như
# luôn nằm ở đuôi.
OUTPUT_TOI_DA = 12_000
OUTPUT_DAU = 3_000

# Toán tử shell, xét SAU KHI TÁCH và chỉ khi nó là MỘT TOKEN RIÊNG.
#
# Xét trên chuỗi thô là bắt oan, và bắt oan đúng cái lệnh hay dùng nhất: `python -c "import
# sys; sys.exit(3)"` có dấu ';' nằm trong nháy, `grep "a|b"` có '|' nằm trong nháy. Sau
# `shlex.split` thì ';' trong nháy nằm GỌN trong một token, còn '&&' của shell thật thì đứng
# riêng thành một token.
#
# Và phải nói rõ rào này là rào CLARITY chứ không phải rào an toàn: an toàn đã do `shell=False`
# lo rồi, metachar lọt xuống cũng chỉ thành tham số trần. Chặn ở đây là để model đừng viết
# `cd x && pytest` rồi tưởng nó có tác dụng.
_TOAN_TU_SHELL = frozenset({"&&", "||", ";", "|", ">", ">>", "<", "&"})

# Allowlist mức `auto`: chương trình được phép chạy. So bằng TÊN CHƯƠNG TRÌNH (token đầu),
# không phải bằng chuỗi con, nên `gitfoo` không lọt qua vì có tiền tố `git`.
#
# Tiêu chí vào danh sách: đọc hoặc kiểm tra thì được; sửa thứ ngoài thư mục làm việc, đụng
# mạng, hoặc đổi lịch sử git thì không.
ALLOWLIST_AUTO = frozenset({
    # chạy thử, kiểm tra
    "pytest", "python", "python3", "node", "npm", "npx", "yarn", "pnpm",
    "go", "cargo", "make", "ruff", "flake8", "black", "mypy", "eslint", "tsc",
    # đọc cây mã nguồn
    "ls", "cat", "head", "tail", "wc", "find", "grep", "rg", "sed", "awk",
    "file", "stat", "du", "tree", "diff",
    # git chỉ đọc (xem `_GIT_AUTO`)
    "git",
})

# Lệnh con của `git` được phép ở mức `auto`. Chỉ đọc. `commit`, `push`, `reset`, `checkout`,
# `clean` đều đổi lịch sử hoặc mất việc đang làm, nên phải lên `full`.
_GIT_AUTO = frozenset({
    "status", "diff", "log", "show", "branch", "remote", "ls-files",
    "rev-parse", "describe", "blame", "shortlog", "config",
})

# Lệnh con của `npm`/`yarn`/`pnpm` được phép ở `auto`. `install` đụng mạng và ghi
# node_modules, nên để `full` (spec mục 26: "package install only if policy allows").
_NPM_AUTO = frozenset({"test", "run", "exec", "ls", "list", "why", "audit"})

# Chặn CỨNG ở MỌI mức, kể cả `full`. Không phải để chống người dùng, mà để một model trả sai
# khuôn không xoá được máy. Danh sách ngắn có chủ ý: dài quá thì sinh cảm giác an toàn giả.
CHAN_CUNG = frozenset({"rm", "rmdir", "mkfs", "dd", "shutdown", "reboot", "halt",
                       "poweroff", "chown", "chmod", "sudo", "su", "kill", "killall",
                       "pkill", "curl", "wget"})

# Biến môi trường được truyền xuống. LỌC TRẮNG, không thừa kế env server: env đó chứa API key
# trong .env, và một lệnh do model đặt ra không có lý do gì cần thấy chúng.
_ENV_TRANG = ("PATH", "HOME", "LANG", "LC_ALL", "TMPDIR", "TEMP", "TMP",
              "SYSTEMROOT", "COMSPEC", "PATHEXT", "USERPROFILE")


@dataclass(frozen=True)
class KetQua:
    ok: bool
    exit_code: int = 0
    output: str = ""
    error: str = ""
    elapsed: float = 0.0
    command: str = ""
    # Có thật sự chạy không. False khi bị chặn hoặc ở mức suggest.
    da_chay: bool = False


def _env_sach() -> dict:
    """Env lọc trắng. Không thừa kế env server (xem docstring đầu file)."""
    env = {k: v for k, v in os.environ.items() if k in _ENV_TRANG}
    env.setdefault("PATH", os.defpath)
    # Chặn pytest/python đọc nhầm cấu hình của chính Javis.
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env


def tach(command: str) -> tuple[list[str], str]:
    """Tách lệnh thành argv. Trả ([], lý do) nếu không tách được hoặc có ký tự shell."""
    cmd = str(command or "").strip()
    if not cmd:
        return [], "Lệnh rỗng."
    if "\n" in cmd:
        return [], ("Lệnh có nhiều dòng. Tool này chạy ĐÚNG MỘT chương trình; tách thành "
                    "nhiều lời gọi tool.")
    try:
        argv = shlex.split(cmd)
    except ValueError as e:
        return [], f"Không tách được lệnh ({e}). Kiểm tra dấu nháy."
    if not argv:
        return [], "Lệnh rỗng sau khi tách."
    for tok in argv:
        # Toán tử đứng riêng (`ls && pytest`), hoặc dính đuôi (`ls; whoami` -> token 'ls;').
        if tok in _TOAN_TU_SHELL or (len(tok) > 1 and tok.endswith(";")):
            return [], (f"Lệnh chứa toán tử shell '{tok}'. Tool này chạy ĐÚNG MỘT chương "
                        f"trình, KHÔNG qua shell, nên nối lệnh hay chuyển hướng đều không có "
                        f"tác dụng. Tách thành nhiều lời gọi tool.")
        # Thay thế lệnh. Không nguy hiểm (không có shell thì `$(whoami)` chỉ là chữ), nhưng
        # model viết ra là đang TƯỞNG nó chạy, nên nói thẳng thay vì để nó ngồi đoán vì sao
        # kết quả toàn dấu đô la. Hẹp có chủ ý: `python -c "print(1)"` có '(' mà không có '$('.
        if "$(" in tok or (tok.count("`") >= 2):
            return [], (f"Lệnh chứa thay thế lệnh ('{tok[:40]}'). Tool này không qua shell nên "
                        f"nó KHÔNG chạy, chỉ thành chữ. Cần giá trị đó thì gọi một lời gọi "
                        f"tool riêng để lấy trước.")
    return argv, ""


def kiem_quyen(argv: list[str], muc: str) -> str:
    """Mức quyền này có cho chạy `argv` không. Trả "" nếu được, hoặc lý do từ chối."""
    prog = Path(argv[0]).name.lower()
    # Bỏ đuôi .exe để `git.exe` trên Windows so khớp được với danh sách.
    if prog.endswith(".exe"):
        prog = prog[:-4]

    if prog in CHAN_CUNG:
        return (f"'{prog}' bị chặn ở MỌI mức quyền, kể cả toàn quyền. Đây là rào cứng của "
                f"Javis để một lời gọi sai khuôn không phá được máy. Cần thật thì chủ máy tự "
                f"chạy trong terminal.")

    if muc == FULL:
        return ""

    if muc != AUTO:
        return (f"Mức quyền hiện tại là '{muc}', không chạy lệnh. Nâng chip của phiên lên "
                f"'auto' hoặc 'full' trên trang Coding.")

    if prog not in ALLOWLIST_AUTO:
        return (f"'{prog}' không nằm trong danh sách lệnh được phép ở mức 'auto'. Mức này chỉ "
                f"cho chạy thử và đọc. Nâng chip của phiên lên 'full' nếu thật sự cần.")

    sub = (argv[1] if len(argv) > 1 else "").lower()
    if prog == "git" and sub not in _GIT_AUTO:
        return (f"'git {sub}' đổi lịch sử hoặc cây làm việc nên không chạy ở mức 'auto'. "
                f"Mức này chỉ cho git chỉ đọc: {', '.join(sorted(_GIT_AUTO))}.")
    if prog in ("npm", "yarn", "pnpm") and sub not in _NPM_AUTO:
        return (f"'{prog} {sub}' không chạy ở mức 'auto' (cài gói thì đụng mạng và ghi ngoài "
                f"thư mục làm việc). Mức này cho: {', '.join(sorted(_NPM_AUTO))}.")
    return ""


def _cat_output(s: str) -> str:
    """Giữ đầu và ĐUÔI. Lỗi thật gần như luôn nằm ở đuôi."""
    s = s or ""
    if len(s) <= OUTPUT_TOI_DA:
        return s
    duoi = OUTPUT_TOI_DA - OUTPUT_DAU
    return (s[:OUTPUT_DAU] + f"\n\n… [cắt {len(s) - OUTPUT_TOI_DA:,} ký tự ở giữa] …\n\n"
            + s[-duoi:])


def _cwd_hop_le(ctx: CodingToolContext, cwd: str) -> tuple[str, str]:
    """Thư mục chạy lệnh, đã ghim trong workspace. Trả (đường dẫn, lý do từ chối)."""
    root = Path(ctx.workspace_root).resolve()
    raw = str(cwd or "").strip() or "."
    try:
        t = (root / raw).resolve()
    except (OSError, ValueError):
        return "", f"Đường dẫn '{raw}' không hợp lệ."
    if t != root and root not in t.parents:
        return "", (f"'{raw}' nằm ngoài thư mục làm việc ({root}). Lệnh chỉ chạy được bên "
                    f"trong thư mục đó.")
    if not t.is_dir():
        return "", f"Không có thư mục '{raw}' trong thư mục làm việc."
    return str(t), ""


def chay(command: str, ctx: CodingToolContext, cwd: str = ".",
         timeout_s: Optional[float] = None) -> KetQua:
    """Chạy một lệnh. KHÔNG ném: mọi cảnh hỏng đều trả `KetQua` nói được.

    Không ném là có chủ ý: engine Web chạy vòng tool bằng chữ, một exception giữa lô tool là
    chết cả lượt, còn một câu lỗi thì model đọc rồi sửa ở vòng sau.
    """
    cmd = str(command or "").strip()
    if not ctx.active:
        return KetQua(False, command=cmd, error=(
            "Phiên này chưa gắn thư mục làm việc nào. Mở trang Coding, chọn repo rồi thử lại."))

    argv, loi = tach(cmd)
    if loi:
        return KetQua(False, command=cmd, error=loi)

    loi = kiem_quyen(argv, ctx.permission_mode)
    if loi:
        return KetQua(False, command=cmd, error=loi)

    if ctx.permission_mode == SUGGEST:
        # Tới đây thì kiem_quyen đã chặn rồi, nhưng giữ nhánh này để ý định hiện rõ trong mã.
        return KetQua(False, command=cmd, error="Mức 'suggest' chỉ đề xuất, không chạy.")

    thu_muc, loi = _cwd_hop_le(ctx, cwd)
    if loi:
        return KetQua(False, command=cmd, error=loi)

    try:
        tran = float(timeout_s) if timeout_s else TIMEOUT_MAC_DINH
    except (TypeError, ValueError):
        tran = TIMEOUT_MAC_DINH
    tran = max(1.0, min(tran, TIMEOUT_TOI_DA))

    t0 = time.time()
    try:
        r = subprocess.run(
            argv, cwd=thu_muc, env=_env_sach(), timeout=tran,
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            shell=False,          # KHÔNG BAO GIỜ bật cờ này: xem docstring đầu file.
            # Javis trên Windows chạy không có console (start-javis.vbs), nên mỗi lệnh con
            # dạng console được hệ điều hành CẤP một cửa sổ đen nháy lên rồi tắt. Tool này
            # chạy `pytest`, `git`, `npm`, tức đúng loại lệnh đó, và chạy nhiều lần một lượt.
            creationflags=winproc.no_window(),
        )
    except FileNotFoundError:
        return KetQua(False, command=cmd, elapsed=time.time() - t0,
                      error=f"Không tìm thấy chương trình '{argv[0]}' trên máy này.")
    except subprocess.TimeoutExpired:
        return KetQua(False, command=cmd, elapsed=time.time() - t0, da_chay=True,
                      error=f"Lệnh chạy quá {int(tran)} giây nên đã bị dừng.")
    except OSError as e:
        return KetQua(False, command=cmd, elapsed=time.time() - t0,
                      error=f"Không chạy được: {type(e).__name__}: {e}")

    ra = (r.stdout or "")
    if r.stderr:
        ra += ("\n[stderr]\n" + r.stderr) if ra else r.stderr
    return KetQua(ok=(r.returncode == 0), exit_code=r.returncode, output=_cat_output(ra),
                  elapsed=time.time() - t0, command=cmd, da_chay=True)


def ket_qua_cho_model(kq: KetQua) -> str:
    """Kết quả gói lại cho model đọc. Nén theo spec mục 18: mã thoát trước, chữ sau."""
    if not kq.da_chay:
        return f"ERROR: {kq.error}"
    dau = f"exit={kq.exit_code} ({kq.elapsed:.1f}s)"
    if kq.error:
        return f"{dau}\nERROR: {kq.error}\n{kq.output}".rstrip()
    return f"{dau}\n{kq.output}".rstrip() if kq.output else f"{dau}\n(không có output)"
