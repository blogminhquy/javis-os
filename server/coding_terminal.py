"""Terminal THẬT cho engine API trong phiên Coding mức Toàn quyền (0.256.0).

Vì sao có file này
------------------
`run_command.py` cho engine API chạy MỘT chương trình, không qua shell, không nhớ gì giữa hai
lệnh, không chạy nền, và chặn cả `rm`, `curl`, `chmod`, `kill` ở mọi mức. Đủ cho mức Tự động
(chạy test, đọc repo), nhưng không đủ để LẬP TRÌNH: không `cd` được, không pipe được, không
bật được dev server để thử, không cài được gói. Claude Code, Codex và Hermes Agent đều có
terminal thật; engine API của Javis thì không, nên cùng một model mà làm kém hẳn.

File này cho mức Toàn quyền một terminal thật, học thiết kế từ Hermes Agent
(github.com/NousResearch/hermes-agent, MIT): `tools/terminal_tool.py`, `tools/environments/
base.py` (mỗi lệnh một bash mới nhưng nhớ cwd và biến môi trường qua file snapshot),
`tools/process_registry.py` (chạy nền, xem log, dừng), `tools/approval_detection.py` (rào cứng
cho lệnh phá cả máy), `tools/tool_output_truncate.py` (cắt 40% đầu, 60% đuôi). Viết lại theo
kiểu Javis.

Ranh giới an toàn, nói thẳng
----------------------------
- CHỈ mức Toàn quyền của phiên Coding. Mức Tự động vẫn là `run_command` (allowlist, không
  shell), mức Plan không chạy gì. Chat thường không bao giờ thấy tool này (mcp_hub lo).
- KHÔNG giữ danh sách chặn `rm`/`curl`/`chmod` như `run_command.CHAN_CUNG`. Trong một shell
  thật, danh sách đó không chặn được gì: `python -c "import shutil; shutil.rmtree('x')"` hay
  `bash -c "r""m -rf x"` đều lách qua. Giữ nó chỉ tạo cảm giác an toàn giả. Rào THẬT là:
    1. Rào cứng cho đúng những lệnh phá CẢ MÁY (`kiem_rao_cung`): rm -rf nhắm /, thư mục hệ
       thống hay home, mkfs, dd vào ổ đĩa thô, fork bomb, kill -1, tắt hay khởi động lại máy,
       sudo/su. Quét cả lớp `bash -c '...'` và `eval`.
    2. Mốc khôi phục trước lượt có lệnh thay đổi (`coding_checkpoint`), nên lỡ hỏng thì bấm
       Hoàn tác trên trang Coding là về.
    3. Môi trường lệnh KHÔNG thừa kế env của máy chủ (trong đó có API key của Javis): dựng từ
       danh sách trắng, rồi lọc thêm mọi tên trông như bí mật.
    4. Output che bí mật (`secret_redact`) trước khi đưa model đọc.
    5. Mọi lệnh ghi nhật ký (mcp_hub ghi vào mcp_audit.jsonl).
  Trên VPS Javis chạy trong Docker, nên "cả máy" ở đây là container.

Windows: không có bash thì chạy PowerShell, chỉ nhớ được thư mục (không nhớ biến môi trường),
và việc nền không có thông báo tự động khi xong (tien_trinh_nen chỉ chạy trên POSIX).
"""
from __future__ import annotations

import atexit
import os
import re
import shlex
import shutil
import signal
import subprocess
import threading
import time
import uuid
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import secret_redact
import winproc
from config import STATE_DIR

POSIX = os.name != "nt"

THU_MUC = STATE_DIR / "coding-terminal"

# Thời gian, giây. 180 đủ cho một lượt build hay test thường; quá 600 thì không ai nên ngồi
# chờ trong một lượt chat: lệnh tự chuyển sang chạy nền và model xem log sau.
TIMEOUT_MAC_DINH = 180
TIEN_CANH_TOI_DA = 600

# Output đưa model đọc: 50.000 ký tự, 40% đầu và 60% đuôi (lỗi thật gần như luôn ở đuôi).
OUTPUT_TOI_DA = 50_000
TY_LE_DAU = 0.4
# Bản đầy đủ ghi ra file, có trần để một `yes` chạy quên không lấp đầy ổ đĩa.
FILE_DAY_DU_TOI_DA = 5_000_000
GIU_FILE_GIAY = 7 * 86400

# Chạy nền.
NEN_MOI_PHIEN = 16
NEN_TOAN_HE = 64
DON_SAU_GIAY = 30 * 60
LOG_DONG_MAC_DINH = 200
CHO_TOI_DA = 600

# ---------------------------------------------------------------------------------------
# Môi trường lệnh
# ---------------------------------------------------------------------------------------
# Danh sách TRẮNG, không thừa kế env máy chủ: env đó chứa API key trong .env. Rộng hơn bản của
# run_command một chút vì đây là terminal để lập trình (công cụ cần biết người dùng, múi giờ,
# thư mục cài Go/Java/nvm).
_ENV_TRANG = ("PATH", "HOME", "LANG", "LC_ALL", "LC_CTYPE", "TZ", "USER", "LOGNAME", "SHELL",
              "TMPDIR", "TEMP", "TMP", "SYSTEMROOT", "COMSPEC", "PATHEXT", "USERPROFILE",
              "APPDATA", "LOCALAPPDATA", "PROGRAMFILES", "WINDIR", "JAVA_HOME", "GOPATH",
              "GOROOT", "NVM_DIR", "PYENV_ROOT", "CARGO_HOME", "RUSTUP_HOME")
# Lọc thêm theo tên, phòng khi ai đó đặt một biến trắng trùng tên lạ.
_TEN_BI_MAT = re.compile(r"(KEY|TOKEN|SECRET|PASSW|CREDENTIAL|COOKIE|PRIVATE)", re.I)


def env_sach() -> Dict[str, str]:
    env = {k: v for k, v in os.environ.items() if k in _ENV_TRANG and not _TEN_BI_MAT.search(k)}
    env.setdefault("PATH", os.defpath)
    if POSIX:
        env.setdefault("HOME", str(Path.home()))
    # Không màu, không trình phân trang, không hỏi mật khẩu: output là để model đọc, và một lệnh
    # đứng chờ nhập mật khẩu git là một lệnh treo tới hết giờ.
    env.update({"TERM": "dumb", "PAGER": "cat", "GIT_PAGER": "cat", "NO_COLOR": "1",
                "GIT_TERMINAL_PROMPT": "0", "PYTHONUNBUFFERED": "1", "JAVIS_TERMINAL": "1"})
    return env


# ---------------------------------------------------------------------------------------
# Rào cứng
# ---------------------------------------------------------------------------------------
_RAO_CUNG_PROG = {"sudo", "su", "doas", "shutdown", "reboot", "halt", "poweroff"}
_VO_BOC = {"env", "exec", "nohup", "time", "command", "builtin", "nice", "ionice", "timeout",
           "xargs", "setsid", "stdbuf", "watch", "strace"}
_SHELL = {"sh", "bash", "zsh", "dash", "ksh", "fish"}
_THU_MUC_HE_THONG = {"/", "/*", "~", "~/", "~/*", "$HOME", "${HOME}", "$HOME/*", "${HOME}/*",
                     "/bin", "/boot", "/dev", "/etc", "/home", "/lib", "/lib64", "/opt", "/proc",
                     "/root", "/sbin", "/srv", "/sys", "/usr", "/var", "/usr/local", "/usr/bin",
                     "/usr/lib", "/var/lib", "/mnt", "/media", "/System", "/Users", "/Library",
                     "/Applications", "C:\\", "C:/", "C:\\Windows", "C:/Windows"}
_FORK_BOMB = re.compile(r":\(\)\s*\{\s*:\s*\|\s*:\s*&\s*\}\s*;?\s*:")
_O_DIA_THO = r"/dev/(sd[a-z]|hd[a-z]|nvme\d|vd[a-z]|xvd[a-z]|mmcblk\d|disk\d|rdisk\d)"
_DD_O_DIA = re.compile(r"\bdd\b[^\n]*\bof=" + _O_DIA_THO)
_GHI_O_DIA = re.compile(r">\s*" + _O_DIA_THO)


def _doan_lenh(cmd: str) -> List[str]:
    """Tách thành từng đoạn lệnh tại ; & | xuống dòng ( ) ` $( NẰM NGOÀI dấu nháy.

    Tách thô bằng regex thì `echo "a; sudo b"` thành hai lệnh và bị chặn oan; tách theo nháy thì
    không. `$(...)` và backtick vẫn chạy được trong nháy kép nên cũng tính là ranh giới ở đó.
    """
    ra, cur, i, n = [], [], 0, len(cmd)
    nhay = ""                      # "", "'" hoặc '"'
    while i < n:
        c = cmd[i]
        if c == "\\" and nhay != "'" and i + 1 < n:
            cur.append(cmd[i:i + 2])
            i += 2
            continue
        if nhay:
            if c == nhay:
                nhay = ""
                cur.append(c)
            elif nhay == '"' and (c == "`" or cmd.startswith("$(", i)):
                ra.append("".join(cur))
                cur = []
                i += 2 if c == "$" else 1
                continue
            else:
                cur.append(c)
            i += 1
            continue
        if c in ("'", '"'):
            nhay = c
            cur.append(c)
        elif cmd.startswith("$(", i):
            ra.append("".join(cur))
            cur = []
            i += 2
            continue
        elif c in ";&|\n()`":
            ra.append("".join(cur))
            cur = []
        else:
            cur.append(c)
        i += 1
    ra.append("".join(cur))
    return [x.strip() for x in ra if x.strip()]


def _tach_tu(doan: str) -> List[str]:
    try:
        return shlex.split(doan, posix=True)
    except ValueError:
        return doan.split()


def _bo_vo(toks: List[str]) -> List[str]:
    """Bỏ phép gán biến đầu lệnh và các lệnh vỏ (env, nohup, timeout...) để thấy lệnh thật."""
    i = 0
    while i < len(toks):
        t = toks[i]
        if re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", t):
            i += 1
            continue
        ten = os.path.basename(t)
        if ten in _VO_BOC:
            i += 1
            while i < len(toks) and (toks[i].startswith("-") or re.match(r"^\d+[smhd]?$", toks[i])
                                     or re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", toks[i])):
                i += 1
            continue
        break
    return toks[i:]


def _chuan_dich(t: str) -> str:
    t = t.strip().strip("'\"")
    if len(t) > 1 and t.endswith("/") and t not in ("~/",):
        t = t.rstrip("/") or "/"
    return t


def kiem_rao_cung(cmd: str, sau: int = 0) -> str:
    """Lý do chặn nếu lệnh thuộc nhóm phá CẢ MÁY, hoặc "" nếu không. Chặn ở MỌI mức quyền."""
    if sau > 4:
        return ""
    s = str(cmd or "")
    if _FORK_BOMB.search(s.replace(" ", "")) or _FORK_BOMB.search(s):
        return "fork bomb"
    if _DD_O_DIA.search(s) or _GHI_O_DIA.search(s):
        return "ghi thẳng vào ổ đĩa thô"
    for doan in _doan_lenh(s):
        toks = _bo_vo(_tach_tu(doan))
        if not toks:
            continue
        prog = os.path.basename(toks[0])
        if prog in _RAO_CUNG_PROG:
            return f"lệnh '{prog}'"
        if prog.startswith("mkfs"):
            return "định dạng ổ đĩa (mkfs)"
        if prog in ("init", "telinit") and len(toks) > 1 and toks[1] in ("0", "6"):
            return f"'{prog} {toks[1]}' (tắt hoặc khởi động lại máy)"
        if prog == "systemctl" and any(t in ("poweroff", "reboot", "halt", "kexec") for t in toks[1:]):
            return "tắt hoặc khởi động lại máy qua systemctl"
        if prog in ("kill", "pkill") and toks[-1] == "-1":
            return "kill -1 (giết mọi tiến trình)"
        if prog == "rm":
            co = [t for t in toks[1:] if t.startswith("-") and t != "--"]
            de_quy = any(t == "--recursive" or (not t.startswith("--") and ("r" in t or "R" in t)) for t in co)
            dich = [_chuan_dich(t) for t in toks[1:] if not t.startswith("-")]
            if de_quy and any(d in _THU_MUC_HE_THONG for d in dich):
                return "xoá đệ quy thư mục gốc, thư mục hệ thống hoặc thư mục home"
        if prog in _SHELL and "-c" in toks[1:]:
            j = toks.index("-c", 1)
            if j + 1 < len(toks):
                ly_do = kiem_rao_cung(toks[j + 1], sau + 1)
                if ly_do:
                    return ly_do
        if prog == "eval" and len(toks) > 1:
            ly_do = kiem_rao_cung(" ".join(toks[1:]), sau + 1)
            if ly_do:
                return ly_do
    return ""


# Nguy hiểm nhưng HỢP LỆ khi lập trình. Ở mức Toàn quyền vẫn chạy, nhưng bắt buộc có mốc khôi
# phục trước và nhật ký ghi nhãn "nguy hiểm". Học từ DANGEROUS_PATTERNS của Hermes.
_NGUY_HIEM = [re.compile(p, re.I) for p in (
    r"\brm\s+(-\S+\s+)*-[a-z]*r", r"\brm\s+.*--recursive",
    r"\bgit\s+reset\s+--hard", r"\bgit\s+push\b.*(\s-f\b|--force)", r"\bgit\s+clean\s+-\S*f",
    r"\bgit\s+(checkout|restore)\s+(--\s+)?\.(\s|$)", r"\bgit\s+branch\s+-D\b",
    r"\bfind\b.*\s-delete\b", r"\bchmod\s+(-\S+\s+)*0?777\b", r"\bchown\s+-R\b",
    r"\b(curl|wget)\b[^|\n]*\|\s*(ba|z|da)?sh\b",
    r">\s*\S*\.env\b", r"\.ssh/", r"\b(drop|truncate)\s+(table|database|schema)\b",
    r"\bdelete\s+from\s+\w+\s*;?\s*(\"|'|$)", r"\bdocker\s+(system|volume)\s+prune\b",
)]


def la_nguy_hiem(cmd: str) -> bool:
    return any(p.search(str(cmd or "")) for p in _NGUY_HIEM)


# Lệnh chỉ đọc: không cần mốc khôi phục trước khi chạy. Ngắn có chủ ý; ngoài danh sách thì coi là
# có thể thay đổi file và tạo mốc (mỗi lượt tối đa một mốc, nên thừa cũng không tốn mấy).
_CHI_DOC = {"ls", "cat", "head", "tail", "wc", "grep", "rg", "pwd", "echo", "which", "type",
            "file", "stat", "du", "df", "tree", "diff", "env", "printenv", "date", "whoami",
            "uname", "ps", "less", "more", "true", "id", "hostname"}
_GIT_CHI_DOC = {"status", "log", "diff", "show", "branch", "remote", "ls-files", "rev-parse",
                "describe", "blame", "shortlog", "grep"}


def la_chi_doc(cmd: str) -> bool:
    if re.search(r"(^|[^>&0-9])>(?![&>]?\s*/dev/null)", cmd):
        return False
    for doan in _doan_lenh(cmd):
        toks = _bo_vo(_tach_tu(doan))
        if not toks:
            continue
        prog = os.path.basename(toks[0])
        if prog == "git":
            sub = next((t for t in toks[1:] if not t.startswith("-")), "")
            if sub not in _GIT_CHI_DOC or (sub == "branch" and any(t in ("-d", "-D", "-m", "-M") for t in toks)):
                return False
            continue
        if prog == "find" and any(t in ("-delete", "-exec", "-execdir") for t in toks):
            return False
        if prog not in _CHI_DOC and prog != "find":
            return False
    return True


# Lệnh không bao giờ tự thoát, hoặc tự đẩy mình xuống nền: chạy tiền cảnh là treo tới hết giờ,
# hoặc bị giết khi lệnh tiền cảnh kết thúc. Bảo model dùng background=true.
_CAN_CHAY_NEN = [re.compile(p, re.I) for p in (
    r"\b(npm|pnpm|yarn|bun)\s+(run\s+)?(dev|start|serve|watch)\b", r"\bnext\s+(dev|start)\b",
    r"\bvite(\s|$)(?!\s*build)", r"\buvicorn\b", r"\bgunicorn\b", r"\bflask\s+run\b",
    r"\bmanage\.py\s+runserver\b", r"\bpython3?\s+-m\s+http\.server\b", r"\brails\s+s(erver)?\b",
    r"\bphp\s+artisan\s+serve\b", r"\bstreamlit\s+run\b", r"\bdocker[ -]compose\s+up\b(?!.*\s-d\b)",
    r"\bnodemon\b", r"\bjupyter\s+(notebook|lab)\b", r"\btail\s+-f\b",
)]


def can_chay_nen(cmd: str) -> str:
    s = str(cmd or "").strip()
    if re.search(r"(^|\s)(nohup|setsid|disown)(\s|$)", s) or re.search(r"[^&]&\s*$", s):
        return ("Lệnh tự đẩy mình xuống nền (&, nohup, setsid). Ở đây tiến trình đó sẽ bị dọn khi "
                "lệnh kết thúc và không ai thấy log. Gọi lại với background=true (bỏ & và nohup), "
                "rồi xem log bằng javis_process.")
    for p in _CAN_CHAY_NEN:
        if p.search(s):
            return ("Lệnh này chạy mãi không tự thoát (dev server, watch, tail -f). Chạy tiền cảnh là "
                    "treo tới hết giờ. Gọi lại với background=true, rồi dùng javis_process "
                    "action=log để xem nó in gì.")
    return ""


# ---------------------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------------------
_ANSI = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]|\x1b\][^\x07\x1b]*(\x07|\x1b\\)|\x1b[()][A-Za-z0-9]|\x1b[=>]")


def lam_sach(text: str) -> str:
    """Bỏ mã màu, gộp dòng thanh tiến trình (\\r), che bí mật."""
    t = _ANSI.sub("", text or "")
    if "\r" in t:
        t = "\n".join((x.rstrip("\r").split("\r")[-1] if "\r" in x else x) for x in t.split("\n"))
    return secret_redact.redact_secrets(t)


def cat_output(text: str, duong_dan_day_du: str = "") -> str:
    if len(text) <= OUTPUT_TOI_DA:
        return text
    dau = int(OUTPUT_TOI_DA * TY_LE_DAU)
    duoi = OUTPUT_TOI_DA - dau
    goi_y = (f" Bản đầy đủ: {duong_dan_day_du} (đọc bằng javis_terminal, ví dụ "
             f"sed -n '1,200p' hoặc grep trên file đó)." if duong_dan_day_du else "")
    return (text[:dau] + f"\n\n… [đã cắt {len(text) - OUTPUT_TOI_DA:,} trên {len(text):,} ký tự ở "
            f"giữa.{goi_y}] …\n\n" + text[-duoi:])


_Y_NGHIA_MA = {126: "file không chạy được (thiếu quyền thực thi?)",
               127: "không tìm thấy lệnh (chưa cài, hoặc sai PATH)",
               130: "bị ngắt (Ctrl-C)", 137: "bị giết (SIGKILL, có thể hết RAM)",
               143: "bị dừng (SIGTERM)"}


# ---------------------------------------------------------------------------------------
# Trạng thái phiên
# ---------------------------------------------------------------------------------------
def _sid_an_toan(sid: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]", "_", str(sid or "khong-phien"))[:80] or "khong-phien"


def thu_muc_phien(sid: str) -> Path:
    d = THU_MUC / _sid_an_toan(sid)
    d.mkdir(parents=True, exist_ok=True)
    return d


def _trong_goc(p: str, goc: List[str]) -> bool:
    try:
        r = Path(p).resolve()
    except (OSError, ValueError):
        return False
    for g in goc:
        try:
            gg = Path(g).resolve()
        except (OSError, ValueError):
            continue
        if r == gg or gg in r.parents:
            return True
    return False


def _cwd_phien(sid: str, goc: List[str]) -> Tuple[str, str]:
    """(cwd hiện tại, câu báo nếu phải đặt lại). cwd thoát khỏi thư mục làm việc thì về gốc."""
    f = thu_muc_phien(sid) / "cwd"
    try:
        cu = f.read_text(encoding="utf-8").strip()
    except OSError:
        cu = ""
    if cu and Path(cu).is_dir() and _trong_goc(cu, goc):
        return cu, ""
    bao = (f"(Thư mục đang đứng '{cu}' nằm ngoài thư mục làm việc hoặc không còn, đã đặt lại về "
           f"{goc[0]}.)" if cu else "")
    if cu:
        try:
            f.write_text(goc[0], encoding="utf-8")      # nói một lần, không nhắc lại mỗi lệnh
        except OSError:
            pass
    return goc[0], bao


def _don_file_cu(d: Path) -> None:
    moc = time.time() - GIU_FILE_GIAY
    # Kịch bản của lệnh nền không xoá ngay được (bash đọc kịch bản dần dần trong lúc chạy), nên
    # dọn ở đây sau một ngày.
    moc_kb = time.time() - 86400
    for f in list(d.glob("*.log")) + list(d.glob("cmd-*.sh")):
        try:
            if f.stat().st_mtime < (moc if f.suffix == ".log" else moc_kb):
                f.unlink()
        except OSError:
            pass


def _doc_ong(ong, f_day_du, gioi_han: int, duoi: List[bytes]) -> int:
    """Đọc hết ống vào file (tới `gioi_han` byte), giữ thêm đuôi 64 KB trong `duoi`. Trả số byte."""
    tong = 0
    DUOI_MAX = 65_536
    while True:
        chunk = ong.read(65_536)
        if not chunk:
            break
        if tong < gioi_han:
            f_day_du.write(chunk[:gioi_han - tong])
        tong += len(chunk)
        duoi.append(chunk)
        while sum(len(x) for x in duoi) > DUOI_MAX * 2 and len(duoi) > 1:
            duoi.pop(0)
    return tong


def _git_bash() -> Optional[str]:
    if POSIX:
        return shutil.which("bash")
    return None


def _powershell() -> Optional[str]:
    return shutil.which("pwsh") or shutil.which("powershell")


def _co_tao_tien_trinh() -> int:
    """Cờ tạo tiến trình: trên Windows không nháy cửa sổ console và mở nhóm riêng (để dừng được
    cả cây). POSIX dùng start_new_session thay cho nhóm, cờ này là 0."""
    if POSIX:
        return 0
    return winproc.no_window() | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)


def _dung_nhom(p: subprocess.Popen) -> None:
    """Dừng cả nhóm tiến trình: TERM, đợi 3 giây, rồi KILL."""
    try:
        if POSIX:
            try:
                os.killpg(p.pid, signal.SIGTERM)
            except ProcessLookupError:
                return
            try:
                p.wait(timeout=3)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(p.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
        else:
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(p.pid)], capture_output=True,
                           creationflags=winproc.no_window())
    except Exception:
        try:
            p.kill()
        except Exception:
            pass


def _kich_ban_posix(command: str, sid: str, cwd: str, goc0: str, ghi_trang_thai: bool) -> Path:
    d = thu_muc_phien(sid)
    snap = d / "env.sh"
    q = shlex.quote
    dong = []
    if snap.is_file():
        dong.append(f"source {q(str(snap))} >/dev/null 2>&1")
    dong.append(f"cd -- {q(cwd)} 2>/dev/null || cd -- {q(goc0)}")
    dong.append(command)
    if ghi_trang_thai:
        dong += ["__javis_rc=$?",
                 f"pwd -P > {q(str(d / 'cwd'))} 2>/dev/null",
                 f"export -p > {q(str(d / 'env.sh.tmp'))} 2>/dev/null && "
                 f"mv -f {q(str(d / 'env.sh.tmp'))} {q(str(snap))}",
                 "exit $__javis_rc"]
    f = d / f"cmd-{uuid.uuid4().hex[:8]}.sh"
    f.write_text("\n".join(dong) + "\n", encoding="utf-8")
    return f


def _argv(command: str, sid: str, cwd: str, goc0: str, ghi_trang_thai: bool) -> Tuple[List[str], Optional[Path], str]:
    """(argv, file kịch bản cần xoá sau, lỗi). Bash trên POSIX, PowerShell trên Windows."""
    bash = _git_bash()
    if bash:
        f = _kich_ban_posix(command, sid, cwd, goc0, ghi_trang_thai)
        return [bash, "--noprofile", "--norc", str(f)], f, ""
    ps = _powershell()
    if ps:
        d = thu_muc_phien(sid)
        q = lambda s: "'" + str(s).replace("'", "''") + "'"
        kb = f"Set-Location -LiteralPath {q(cwd)}\n{command}\n"
        if ghi_trang_thai:
            kb += (f"$__c = $LASTEXITCODE\n(Get-Location).Path | Out-File -Encoding utf8 -LiteralPath "
                   f"{q(d / 'cwd')}\nexit $__c\n")
        return [ps, "-NoProfile", "-NonInteractive", "-Command", kb], None, ""
    return [], None, ("Máy này không có bash lẫn PowerShell nên không có terminal. Dùng "
                      "javis_run_command (chạy một chương trình, không qua shell).")


# ---------------------------------------------------------------------------------------
# Chạy tiền cảnh
# ---------------------------------------------------------------------------------------
def chay(command: str, sid: str, goc: List[str], timeout: Optional[float] = None,
         workdir: str = "", brain_root: str = "", chat_id: str = "") -> str:
    """Chạy một lệnh. Trả chữ cho model đọc, không ném. `goc`: các thư mục làm việc của phiên,
    đã resolve, thư mục chính đứng đầu."""
    cmd = str(command or "").strip()
    if not cmd:
        return "ERROR: lệnh rỗng."
    if not goc:
        return "ERROR: phiên này chưa gắn thư mục làm việc nào."
    ly_do = kiem_rao_cung(cmd)
    if ly_do:
        return (f"ERROR: chặn cứng: {ly_do}. Javis không cho model chạy lệnh có thể phá cả máy, ở "
                f"mọi mức quyền. Cần thật thì chủ máy tự chạy trong tab Terminal.")
    nen = can_chay_nen(cmd)
    if nen:
        return f"ERROR: {nen}"
    try:
        tran = float(timeout) if timeout else TIMEOUT_MAC_DINH
    except (TypeError, ValueError):
        tran = TIMEOUT_MAC_DINH
    tran = max(1.0, tran)
    if tran > TIEN_CANH_TOI_DA:
        kq = chay_nen(cmd, sid, goc, workdir=workdir, brain_root=brain_root, chat_id=chat_id)
        return (f"Xin chờ {int(tran)} giây là quá {TIEN_CANH_TOI_DA} giây cho một lệnh tiền cảnh, nên "
                f"đã chuyển sang chạy nền.\n{kq}")

    cwd, bao = _cwd_phien(sid, goc)
    rieng = False
    if str(workdir or "").strip():
        w = str(workdir).strip()
        wp = Path(w) if Path(w).is_absolute() else Path(cwd) / w
        if not _trong_goc(str(wp), goc) or not wp.is_dir():
            return (f"ERROR: workdir '{w}' không phải thư mục nằm trong thư mục làm việc của phiên "
                    f"({', '.join(goc)}).")
        cwd, rieng = str(wp.resolve()), True

    d = thu_muc_phien(sid)
    _don_file_cu(d)
    # workdir chỉ cho lệnh này: không ghi đè cwd đã nhớ của phiên.
    argv, kb, loi = _argv(cmd, sid, cwd, goc[0], ghi_trang_thai=not rieng)
    if loi:
        return f"ERROR: {loi}"
    duong_day_du = d / f"out-{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}.log"
    cwd_truoc = cwd
    t0 = time.time()
    het_gio = False
    duoi: List[bytes] = []
    try:
        with open(duong_day_du, "wb") as f_day_du:
            p = subprocess.Popen(argv, cwd=cwd, env=env_sach(), stdin=subprocess.DEVNULL,
                                 stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                 start_new_session=POSIX, creationflags=_co_tao_tien_trinh())
            dem = [0]
            th = threading.Thread(target=lambda: dem.__setitem__(0, _doc_ong(p.stdout, f_day_du,
                                                                              FILE_DAY_DU_TOI_DA, duoi)),
                                  daemon=True)
            th.start()
            try:
                p.wait(timeout=tran)
            except subprocess.TimeoutExpired:
                het_gio = True
                _dung_nhom(p)
            th.join(timeout=5)
            rc = p.returncode if p.returncode is not None else -1
            tong_byte = dem[0]
    except FileNotFoundError as e:
        return f"ERROR: không chạy được shell: {e}"
    except OSError as e:
        return f"ERROR: không chạy được: {type(e).__name__}: {e}"
    finally:
        if kb is not None:
            try:
                kb.unlink()
            except OSError:
                pass
    giay = time.time() - t0

    try:
        raw = duong_day_du.read_bytes()
    except OSError:
        raw = b""
    if tong_byte > FILE_DAY_DU_TOI_DA:
        raw += (f"\n… [output dài {tong_byte:,} byte, file chỉ giữ {FILE_DAY_DU_TOI_DA:,} byte đầu; "
                f"đuôi bên dưới]\n").encode() + b"".join(duoi)[-65_536:]
    text = lam_sach(raw.decode("utf-8", errors="replace"))
    if len(text) <= OUTPUT_TOI_DA:
        try:
            duong_day_du.unlink()
        except OSError:
            pass
        than = text
    else:
        try:
            duong_day_du.write_text(text, encoding="utf-8")
        except OSError:
            pass
        than = cat_output(text, str(duong_day_du))

    dau = [f"exit={rc} ({giay:.1f}s)"]
    if het_gio:
        dau.append(f"HẾT GIỜ: lệnh chạy quá {int(tran)} giây nên đã bị dừng. Lệnh dài thì chạy nền "
                   f"(background=true) rồi xem log bằng javis_process.")
    if bao:
        dau.append(bao)
    if not rieng:
        cwd_sau, bao_sau = _cwd_phien(sid, goc)
        if bao_sau:
            dau.append(bao_sau)
        elif cwd_sau != cwd_truoc:
            dau.append(f"cwd: {cwd_sau}")
    y = _Y_NGHIA_MA.get(rc)
    if y and not het_gio:
        dau.append(f"(mã {rc}: {y})")
    return "\n".join(dau) + "\n" + (than.rstrip() if than.strip() else "(không có output)")


# ---------------------------------------------------------------------------------------
# Chạy nền
# ---------------------------------------------------------------------------------------
class TienTrinh:
    def __init__(self, sid: str, command: str, cwd: str, p: subprocess.Popen, log: Path,
                 job_id: str = ""):
        self.id = "proc_" + uuid.uuid4().hex[:12]
        self.sid = sid
        self.command = command
        self.cwd = cwd
        self.p = p
        self.log = log
        self.bat_dau = time.time()
        self.ket_thuc: Optional[float] = None
        self.rc: Optional[int] = None
        self.job_id = job_id          # mã việc bên tien_trinh_nen (để báo khi xong)
        self.bi_dung = False

    def cap_nhat(self) -> None:
        if self.rc is None:
            rc = self.p.poll()
            if rc is not None:
                self.rc = rc
                self.ket_thuc = time.time()

    @property
    def dang_chay(self) -> bool:
        self.cap_nhat()
        return self.rc is None


_NEN: Dict[str, TienTrinh] = {}
_NEN_KHOA = threading.Lock()


def _don_nen() -> None:
    moc = time.time() - DON_SAU_GIAY
    with _NEN_KHOA:
        for k, v in list(_NEN.items()):
            v.cap_nhat()
            if v.rc is not None and (v.ket_thuc or 0) < moc:
                _NEN.pop(k, None)


def _tim(sid: str, pid: str) -> Optional[TienTrinh]:
    pid = str(pid or "").strip()
    if not pid:
        return None
    with _NEN_KHOA:
        ds = [v for v in _NEN.values() if v.sid == sid and (v.id == pid or v.id.startswith(pid)
                                                             or v.id[5:].startswith(pid))]
    return ds[0] if len(ds) == 1 else None


def chay_nen(command: str, sid: str, goc: List[str], workdir: str = "", brain_root: str = "",
             chat_id: str = "") -> str:
    cmd = str(command or "").strip()
    if not cmd:
        return "ERROR: lệnh rỗng."
    if not goc:
        return "ERROR: phiên này chưa gắn thư mục làm việc nào."
    ly_do = kiem_rao_cung(cmd)
    if ly_do:
        return (f"ERROR: chặn cứng: {ly_do}. Javis không cho model chạy lệnh có thể phá cả máy, ở "
                f"mọi mức quyền.")
    _don_nen()
    with _NEN_KHOA:
        cua_phien = [v for v in _NEN.values() if v.sid == sid and v.dang_chay]
        tong = [v for v in _NEN.values() if v.dang_chay]
    if len(cua_phien) >= NEN_MOI_PHIEN:
        return (f"ERROR: phiên này đã có {len(cua_phien)} tiến trình nền đang chạy (trần "
                f"{NEN_MOI_PHIEN}). Dừng bớt bằng javis_process action=kill.")
    if len(tong) >= NEN_TOAN_HE:
        return f"ERROR: cả máy đã có {len(tong)} tiến trình nền của Javis (trần {NEN_TOAN_HE})."
    cwd, _ = _cwd_phien(sid, goc)
    if str(workdir or "").strip():
        w = str(workdir).strip()
        wp = Path(w) if Path(w).is_absolute() else Path(cwd) / w
        if not _trong_goc(str(wp), goc) or not wp.is_dir():
            return f"ERROR: workdir '{w}' không nằm trong thư mục làm việc của phiên."
        cwd = str(wp.resolve())
    # Lệnh nền chạy dài: cmd kiểu `cmd &` bên trong vẫn được, nhưng bỏ & cuối để khỏi tách đôi.
    cmd_chay = re.sub(r"\s*&\s*$", "", re.sub(r"^\s*nohup\s+", "", cmd))
    argv, _kb, loi = _argv(cmd_chay, sid, cwd, goc[0], ghi_trang_thai=False)
    if loi:
        return f"ERROR: {loi}"
    d = thu_muc_phien(sid)
    log = d / f"proc-{uuid.uuid4().hex[:12]}.log"
    try:
        f = open(log, "wb")
        p = subprocess.Popen(argv, cwd=cwd, env=env_sach(), stdin=subprocess.DEVNULL, stdout=f,
                             stderr=subprocess.STDOUT, start_new_session=POSIX,
                             creationflags=_co_tao_tien_trinh())
        f.close()
    except OSError as e:
        return f"ERROR: không bật được tiến trình nền: {type(e).__name__}: {e}"
    job_id = ""
    if POSIX and chat_id:
        try:
            import tien_trinh_nen
            job_id = tien_trinh_nen.theo_doi_nhom(p.pid, cmd[:200], cwd, brain_root, chat_id) or ""
        except Exception:
            job_id = ""
    tt = TienTrinh(sid, cmd, cwd, p, log, job_id)
    # File log đặt tên theo id để model đọc được bằng đường dẫn nếu muốn.
    try:
        moi = d / f"{tt.id}.log"
        os.replace(log, moi)
        tt.log = moi
    except OSError:
        pass
    with _NEN_KHOA:
        _NEN[tt.id] = tt
    time.sleep(0.3)
    tt.cap_nhat()
    trang = "đã thoát ngay" if tt.rc is not None else "đang chạy"
    them = ("Xong là Javis tự báo vào khung chat này." if job_id else
            "Javis không tự báo khi nó xong; dùng javis_process action=wait hoặc poll để biết.")
    out = [f"Đã bật nền: {tt.id} ({trang}, pid {p.pid}). Log: {tt.log}",
           f"Xem: javis_process action=log process_id={tt.id}. Dừng: action=kill. {them}"]
    if tt.rc is not None:
        out.append(f"exit={tt.rc}\n" + _duoi_log(tt, 40))
    return "\n".join(out)


def _doc_log(tt: TienTrinh) -> List[str]:
    try:
        with open(tt.log, "rb") as f:
            f.seek(0, 2)
            n = f.tell()
            f.seek(max(0, n - 200_000))
            raw = f.read()
    except OSError:
        return []
    return lam_sach(raw.decode("utf-8", errors="replace")).split("\n")


def _duoi_log(tt: TienTrinh, so_dong: int) -> str:
    ds = _doc_log(tt)
    return "\n".join(ds[-so_dong:]).rstrip() or "(chưa có output)"


def _mo_ta(tt: TienTrinh) -> str:
    tt.cap_nhat()
    giay = (tt.ket_thuc or time.time()) - tt.bat_dau
    trang = "đang chạy" if tt.rc is None else (f"đã dừng (exit={tt.rc})" if tt.bi_dung else f"đã xong (exit={tt.rc})")
    return f"{tt.id}  {trang}  {int(giay)}s  {tt.command[:120]}"


def quan_ly(action: str, sid: str, process_id: str = "", offset: int = 0, limit: int = 0,
            timeout: float = 0) -> str:
    """javis_process: list | poll | log | wait | kill."""
    a = str(action or "list").strip().lower()
    _don_nen()
    if a == "list":
        with _NEN_KHOA:
            ds = [v for v in _NEN.values() if v.sid == sid]
        if not ds:
            return "(phiên này chưa có tiến trình nền nào)"
        return "\n".join(_mo_ta(v) for v in sorted(ds, key=lambda x: x.bat_dau))
    tt = _tim(sid, process_id)
    if tt is None:
        return (f"ERROR: không thấy tiến trình '{process_id}' của phiên này (hoặc tiền tố khớp nhiều "
                f"cái). Gọi action=list để xem mã.")
    if a == "poll":
        return _mo_ta(tt) + "\n" + _duoi_log(tt, 20)
    if a == "log":
        ds = _doc_log(tt)
        try:
            lim = int(limit or LOG_DONG_MAC_DINH)
        except (TypeError, ValueError):
            lim = LOG_DONG_MAC_DINH
        lim = max(1, min(lim, 2000))
        try:
            off = int(offset or 0)
        except (TypeError, ValueError):
            off = 0
        phan = ds[off:off + lim] if off > 0 else ds[-lim:]
        return _mo_ta(tt) + "\n" + cat_output("\n".join(phan).rstrip() or "(chưa có output)")
    if a == "wait":
        try:
            t = float(timeout or 60)
        except (TypeError, ValueError):
            t = 60.0
        t = max(1.0, min(t, CHO_TOI_DA))
        han = time.time() + t
        while time.time() < han and tt.dang_chay:
            time.sleep(0.25)
        dau = "" if not tt.dang_chay else f"(vẫn chạy sau {int(t)} giây chờ)\n"
        return dau + _mo_ta(tt) + "\n" + _duoi_log(tt, 40)
    if a == "kill":
        if not tt.dang_chay:
            return _mo_ta(tt) + "\n(đã kết thúc từ trước, không cần dừng)"
        tt.bi_dung = True
        if tt.job_id:
            try:
                import tien_trinh_nen
                tien_trinh_nen.ngung_theo_doi(tt.job_id)
            except Exception:
                pass
        _dung_nhom(tt.p)
        try:
            tt.p.wait(timeout=5)
        except Exception:
            pass
        tt.cap_nhat()
        return "Đã dừng.\n" + _mo_ta(tt) + "\n" + _duoi_log(tt, 20)
    return "ERROR: action phải là list, poll, log, wait hoặc kill."


def don_phien(sid: str) -> None:
    """Phiên Coding bị xoá: dừng mọi tiến trình nền của nó và xoá thư mục trạng thái."""
    with _NEN_KHOA:
        ds = [v for v in _NEN.values() if v.sid == sid]
    for v in ds:
        if v.dang_chay:
            v.bi_dung = True
            if v.job_id:
                try:
                    import tien_trinh_nen
                    tien_trinh_nen.ngung_theo_doi(v.job_id)
                except Exception:
                    pass
            _dung_nhom(v.p)
        with _NEN_KHOA:
            _NEN.pop(v.id, None)
    try:
        shutil.rmtree(THU_MUC / _sid_an_toan(sid), ignore_errors=True)
    except Exception:
        pass


@atexit.register
def _tat_het() -> None:
    """Javis tắt: tiến trình nền chạy nhóm riêng nên sẽ sống sót nếu không dọn. Dọn."""
    with _NEN_KHOA:
        ds = list(_NEN.values())
    for v in ds:
        try:
            if v.p.poll() is None:
                _dung_nhom(v.p)
        except Exception:
            pass
