"""Bộ não thứ 10: Antigravity CLI (binary `agy`) - bản thay thế chính chủ của Gemini CLI.

**Vì sao có file này.** Ngày 18/06/2026 Google ngừng phục vụ Gemini CLI cho mọi tài khoản cá
nhân (miễn phí, AI Pro, Ultra) với mã `UNSUPPORTED_CLIENT`, và chỉ sang Antigravity. Đường đi
qua `gemini` vẫn giữ trong repo cho ai có giấy phép doanh nghiệp hoặc chạy bằng API key, còn
người dùng cá nhân muốn xài gói Google của mình thì phải qua đây.

Cái được, so với Gemini CLI: `agy` cho chọn ĐÚNG những model hiện trong trình chọn của
Antigravity IDE - gồm cả model không phải của Google (Claude). Nên "đổi model như Antigravity"
làm được thật, không phải hứa.

**KỶ LUẬT CỦA FILE NÀY: ĐO, KHÔNG ĐOÁN.**

`gemini_cli.py` viết được chắc tay vì tác giả có binary trong tay và đọc `--help` thật. Ở đây
KHÔNG có: máy dựng bản này bị chặn mạng nên không tải được `agy`, mà cờ dòng lệnh thì mỗi bản
một khác (xem CHANGELOG của chính nó: `--model` có từ 1.0.5, slug ổn định từ 1.1.5,
`--output-format` cho print mode từ 1.1.8, cho `models`/`agents` từ 1.1.12). Đoán cờ rồi ship
là đúng kiểu sai mà file kia đã cố tránh.

Nên file này KHÔNG cứng hoá gì cả. Nó:

- đọc `agy --help` MỘT LẦN rồi nhớ, và chỉ truyền những cờ mà chính binary trên máy khai;
- lấy danh sách model bằng `agy models`, không giữ bảng model chép tay (bảng chép tay là thứ
  hỏng ngay lần Google đổi tên model, mà họ đổi liên tục);
- ánh xạ sự kiện stream-json theo NHIỀU hình dạng, và cuối cùng luôn có lưới an toàn: dòng nào
  không hiểu thì giữ nguyên làm chữ, chứ tuyệt đối không im lặng trả bong bóng rỗng - đó đúng
  là triệu chứng khiến chủ repo mất buổi tối với Gemini CLI.

Chỗ nào chưa đo được thì ghi thẳng "CHƯA ĐO" trong chú thích thay vì làm ra vẻ chắc chắn.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import AsyncIterator, Optional

from claude_cli import _home_dir, _no_window, tim_binary

# Model mặc định khi người dùng chưa chọn gì. KHÔNG phải bảng model: chỉ là hạt giống để lượt
# đầu chạy được nếu `agy models` chưa kịp trả lời. Danh sách thật luôn lấy từ CLI.
MODEL_MAC_DINH = ""     # rỗng = không truyền --model, để CLI dùng model nó đang đặt

# Lệnh cài chính chủ, hiện nguyên văn cho người dùng chép.
LENH_CAI = {
    "linux": "curl -fsSL https://antigravity.google/cli/install.sh | bash",
    "mac": "curl -fsSL https://antigravity.google/cli/install.sh | bash",
    "windows": "irm https://antigravity.google/cli/install.ps1 | iex",
}


def lenh_cai() -> str:
    return LENH_CAI["windows"] if os.name == "nt" else LENH_CAI["linux"]


def find_antigravity_cli() -> Optional[str]:
    """Tìm binary `agy`. Cửa thoát JAVIS_AGY_BIN cho máy cài chỗ lạ.

    Trình cài chính chủ thả vào `~/.local/bin/agy`, mà thư mục đó KHÔNG chắc nằm trong PATH của
    tiến trình Javis - dịch vụ systemd và app trên macOS đều được cấp một PATH rất ngắn. Nên
    phải soi tay chỗ đó thay vì tin mỗi `which`.
    """
    envp = (os.environ.get("JAVIS_AGY_BIN") or "").strip()
    if envp:
        try:
            if Path(envp).exists():
                return envp
        except Exception:
            pass
    cli = tim_binary("agy")
    if cli:
        return cli
    home = _home_dir()
    ung_vien = [
        home / ".local" / "bin" / "agy",
        home / ".antigravity" / "bin" / "agy",
        Path("/usr/local/bin/agy"),
        Path("/opt/homebrew/bin/agy"),
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "antigravity" / "agy.exe",
        Path(os.environ.get("APPDATA", "")) / "npm" / "agy.cmd",
    ]
    for p in ung_vien:
        try:
            if p.exists():
                return str(p)
        except Exception:
            pass
    return None


# ---------------------------------------------------------------------------
# Dò năng lực của binary đang cài (thay cho việc đoán cờ)
# ---------------------------------------------------------------------------
_HELP_CACHE: dict = {"path": None, "text": "", "ts": 0.0}
_HELP_TTL = 300.0     # 5 phút: đủ để một phiên chat không đẻ tiến trình mỗi lượt, mà nâng cấp
                      # bản CLI xong cũng không phải khởi động lại Javis mới nhận cờ mới.


def _help_text() -> str:
    """Nội dung `agy --help`, nhớ trong RAM. Rỗng nếu không chạy được."""
    cli = find_antigravity_cli()
    if not cli:
        return ""
    now = time.time()
    if (_HELP_CACHE["path"] == cli and _HELP_CACHE["text"]
            and now - _HELP_CACHE["ts"] < _HELP_TTL):
        return _HELP_CACHE["text"]
    try:
        r = subprocess.run([cli, "--help"], capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=20, creationflags=_no_window())
        txt = (r.stdout or "") + "\n" + (r.stderr or "")
    except Exception:
        txt = ""
    _HELP_CACHE.update(path=cli, text=txt, ts=now)
    return txt


def co_co(*ten_co: str) -> bool:
    """Binary trên máy CÓ khai cờ này không (`--help` nhắc tới nó).

    Truyền một cờ mà bản CLI chưa có là nó thoát ngay với "unknown flag" - hỏng cả lượt chat
    chỉ vì một tuỳ chọn phụ. Hỏi trước rồi mới truyền thì bản cũ vẫn chạy, chỉ mất tính năng.
    """
    txt = _help_text()
    if not txt:
        return False
    return any(c in txt for c in ten_co)


def nhan_prompt_qua_stdin() -> bool:
    """CLI có đọc prompt từ stdin không.

    Quan trọng với Javis: system prompt kèm ngữ cảnh brain thường vài chục nghìn ký tự, mà
    Windows chặn dòng lệnh ở 32767 - nhét qua argv là gãy. Gemini CLI giải bằng `-p ""` rồi bơm
    stdin; `agy` CHƯA ĐO được nên hỏi `--help` xem có nhắc stdin không, có thì đi đường đó.
    """
    txt = (_help_text() or "").lower()
    return "stdin" in txt


def phien_moi() -> str:
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# Mức quyền
# ---------------------------------------------------------------------------
def co_quyen_cho_mode(mode: Optional[str]) -> list[str]:
    """Ba mức quyền của Javis -> cờ của `agy`. Giá trị lạ về nấc CHẶT NHẤT (fail-closed).

    Chỉ có `--dangerously-skip-permissions` (tự duyệt mọi tool) và `--sandbox` (siết terminal)
    là thấy trong tài liệu. KHÔNG có nấc "chỉ đọc" tương đương `--approval-mode plan` của Gemini
    CLI, nên `suggest` ở đây được siết bằng SANDBOX cộng với lời dặn trong system prompt, chứ
    không phải một cái chốt cứng của CLI. Khác biệt này phải nói thật ở tài liệu, đừng để người
    dùng tưởng mức Chỉ đọc do CLI chặn như bên Gemini.
    """
    m = str(mode or "").strip().lower()
    co: list[str] = []
    if m == "full":
        if co_co("--dangerously-skip-permissions"):
            co.append("--dangerously-skip-permissions")
        return co
    # suggest + auto + mọi giá trị lạ: bật sandbox nếu bản CLI có.
    if co_co("--sandbox"):
        co.append("--sandbox")
    if m == "auto" and co_co("--dangerously-skip-permissions"):
        # auto = được ghi file nháp trong brain. Headless mà dừng lại hỏi duyệt là treo tới hết
        # giờ, nên vẫn phải tự duyệt; rào tiền/đơn/đăng bài nằm ở MCP Hub chứ không ở đây.
        co.append("--dangerously-skip-permissions")
    return co


# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------
def _tach_model(doc) -> list[str]:
    """Bóc danh sách model từ thứ `agy models` trả về, chấp NHIỀU hình dạng.

    CHƯA ĐO được khoá thật của JSON, nên nhận cả list chuỗi lẫn list dict với các khoá hay gặp.
    Thà rộng còn hơn kén: kén sai một khoá là trình chọn model rỗng trơn.
    """
    if isinstance(doc, dict):
        for k in ("models", "data", "items", "result"):
            if isinstance(doc.get(k), list):
                doc = doc[k]
                break
    if not isinstance(doc, list):
        return []
    ra: list[str] = []
    for m in doc:
        if isinstance(m, str):
            ten = m.strip()
        elif isinstance(m, dict):
            ten = ""
            for k in ("slug", "id", "model", "name", "label", "display_name"):
                v = m.get(k)
                if isinstance(v, str) and v.strip():
                    ten = v.strip()
                    break
        else:
            ten = ""
        if ten and ten not in ra:
            ra.append(ten)
    return ra


def list_models() -> Optional[list]:
    """Danh sách model hỏi thẳng CLI. None = chưa cài CLI (phía trên còn biết mà nói lý do).

    Không giữ bảng model chép tay: Google đổi tên model liên tục, và chính người dùng mới là
    người biết tài khoản mình được cấp những gì. `agy models` trả đúng thứ hiện trong trình
    chọn của Antigravity IDE.
    """
    cli = find_antigravity_cli()
    if not cli:
        return None
    # Bản >= 1.1.12 có --output-format cho `models`; bản cũ thì chỉ in chữ. Thử JSON trước.
    if co_co("--output-format"):
        try:
            r = subprocess.run([cli, "models", "--output-format", "json"], capture_output=True,
                               text=True, encoding="utf-8", errors="replace", timeout=30,
                               creationflags=_no_window())
            if r.returncode == 0 and (r.stdout or "").strip():
                ds = _tach_model(json.loads(r.stdout))
                if ds:
                    return ds
        except Exception:
            pass
    try:
        r = subprocess.run([cli, "models"], capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=30, creationflags=_no_window())
    except Exception:
        return []
    if r.returncode != 0:
        return []
    # In chữ thuần. Đo trên `agy models` 1.1.12 (người dùng gửi kèm `cat -A`):
    #
    #     Fetching available models...
    #     gemini-3.6-flash-high^IGemini 3.6 Flash (High)$
    #     claude-sonnet-4-6^IClaude Sonnet 4.6 (Thinking)$
    #
    # Hai chỗ bản đầu làm sai, và cả hai đều hỏng LẶNG LẼ:
    #
    # 1. Cắt cột bằng `\s{2,}` - biểu thức đó KHÔNG khớp một tab đơn. Nên cả dòng
    #    "gemini-3.6-flash-high\tGemini 3.6 Flash (High)" bị lấy làm mã model, rồi truyền nguyên
    #    vào `--model`. `agy` không có model tên như vậy nên thoát mã 1 ở MỌI lượt chat - tức
    #    provider này không dùng được ở bất kỳ máy nào.
    # 2. Dòng thông báo "Fetching available models..." không bị lọc nên hiện như một model
    #    trong trình chọn.
    #
    # Lọc theo khoảng trắng là đủ và đúng bản chất: mã model là một slug, không bao giờ có
    # khoảng trắng; còn mọi câu thông báo thì luôn có.
    ra: list[str] = []
    for dong in (r.stdout or "").splitlines():
        d = dong.strip().lstrip("*->•").strip()
        if not d or d.endswith(":"):
            continue
        d = re.split(r"\t|\s{2,}", d)[0].strip()
        if not d or " " in d:
            continue
        if d not in ra:
            ra.append(d)
    return ra


# ---------------------------------------------------------------------------
# Đăng nhập
# ---------------------------------------------------------------------------
_AUTH_CACHE: dict = {"ts": 0.0, "val": None}
_AUTH_TTL = 60.0


def auth_status(bo_qua_cache: bool = False) -> dict:
    """Đã đăng nhập chưa: {connected, method, email, error}.

    Khác Gemini CLI ở một điểm quyết định cách viết hàm này: `agy` giữ phiên trong KEYRING của
    hệ điều hành, không có file credential nào để soi. Nên không có đường nào rẻ hơn là hỏi
    chính CLI - và vì trang Models gọi hàm này mỗi lần mở, phải nhớ kết quả một phút, đúng lý
    do mà `gemini_cli.auth_status()` cố tránh đẻ tiến trình.

    Dùng `models` làm phép thử vì nó cần tài khoản mới trả được danh sách, lại rẻ hơn nhiều so
    với chạy hẳn một lượt chat.
    """
    cli = find_antigravity_cli()
    if not cli:
        return {"connected": False, "method": "", "email": "",
                "error": f"Chưa cài Antigravity CLI. Cài một lần: {lenh_cai()}"}
    now = time.time()
    if not bo_qua_cache and _AUTH_CACHE["val"] and now - _AUTH_CACHE["ts"] < _AUTH_TTL:
        return dict(_AUTH_CACHE["val"])
    ds = list_models()
    if ds:
        d = {"connected": True, "method": "google (keyring của máy)", "email": "", "error": ""}
    else:
        d = {"connected": False, "method": "", "email": "",
             "error": "Đã cài Antigravity CLI nhưng chưa đăng nhập. Mở terminal trên máy chạy "
                      "Javis, gõ `agy` rồi làm theo hướng dẫn đăng nhập Google."}
    _AUTH_CACHE.update(ts=now, val=dict(d))
    return d


def login_huong_dan() -> dict:
    """Hướng dẫn đăng nhập. KHÔNG có nút bấm trên dashboard, và đó là quyết định có lý do.

    `agy` giữ token trong keyring hệ điều hành chứ không phải file, nên Javis không bắc cầu
    token hộ được như đã làm với Gemini CLI (`gemini_oauth.ghi_creds_cho_cli`). Dựng một nút
    "Đăng nhập" rồi bên dưới không làm gì được thì tệ hơn là nói thẳng phải gõ một lệnh.

    Điểm sáng cho người chạy VPS: `agy` tự nhận biết phiên SSH và IN RA một đường link để mở
    trên máy có trình duyệt, nên không cần màn hình ở phía máy chủ.
    """
    return {
        "cai": lenh_cai(),
        "dang_nhap": "agy",
        "ghi_chu": ("Chạy `agy` một lần trong terminal của máy chạy Javis. Máy có màn hình thì "
                    "nó tự mở trình duyệt; qua SSH thì nó in ra một đường link, mở link đó trên "
                    "máy của anh rồi đăng nhập Google là xong. Đăng nhập lưu trong keyring của "
                    "hệ điều hành nên chỉ phải làm một lần."),
    }


# ---------------------------------------------------------------------------
# MCP: đấu hub của Javis vào CLI
# ---------------------------------------------------------------------------
def ghi_mcp_settings(vault_root, hub: Optional[dict]) -> Optional[str]:
    """Ghi entry MCP `javis` vào cấu hình của `agy` trong chính brain đang mở.

    CHƯA ĐO được tên file cấu hình thật của `agy` (tài liệu chỉ nói nó dùng "một file riêng"
    thay vì nhét trong settings.json như Gemini CLI). Nên ghi ra CẢ HAI chỗ nhiều khả năng
    nhất, cùng một nội dung: `.antigravity/mcp.json` và `.antigravity/settings.json`. Ghi thừa
    một file JSON nhỏ trong brain là vô hại; đoán trượt rồi không đấu được MCP mới là hỏng.

    Khi đo được tên thật thì rút lại còn một file - để nguyên hai file là nợ kỹ thuật, không
    phải thiết kế.
    """
    ra = None
    for ten in ("mcp.json", "settings.json"):
        try:
            p = Path(vault_root).expanduser() / ".antigravity" / ten
            cu = {}
            if p.exists():
                try:
                    cu = json.loads(p.read_text(encoding="utf-8")) or {}
                except Exception:
                    cu = {}
            if not isinstance(cu, dict):
                cu = {}
            servers = cu.get("mcpServers")
            if not isinstance(servers, dict):
                servers = {}
            if hub:
                servers["javis"] = hub
            else:
                servers.pop("javis", None)
            if servers:
                cu["mcpServers"] = servers
            else:
                cu.pop("mcpServers", None)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps(cu, ensure_ascii=False, indent=2), encoding="utf-8")
            try:
                os.chmod(p, 0o600)   # chứa hub token
            except Exception:
                pass
            ra = str(p)
        except Exception as e:
            print(f"[antigravity mcp settings] {ten}: {e}", file=sys.stderr)
    return ra


# ---------------------------------------------------------------------------
# Một lượt chạy
# ---------------------------------------------------------------------------
class AntigravityCLI:
    """Một lượt chạy `agy` headless. Cùng hợp đồng sự kiện với ClaudeSDK/CodexCLI/GeminiCLI."""

    def __init__(self, cwd: Optional[str] = None, tag: str = "chat", model: Optional[str] = None,
                 instructions: Optional[str] = None):
        self.cli_path = find_antigravity_cli()
        self.cwd = cwd or os.getcwd()
        self.tag = tag
        self.model = model
        self.instructions = instructions
        self.session_id = None          # có giá trị -> nối lại mạch cũ
        self._session_moi = None
        self.mode = "suggest"
        self.extra_args: list[str] = []
        self.include_dirs: list[str] = []
        # Trần thời gian một lượt. Gemini CLI không cần vì `--approval-mode` chặn mọi câu hỏi;
        # ở đây mức suggest/auto CHƯA ĐO được là CLI có dừng hỏi không, mà headless dừng hỏi là
        # treo vĩnh viễn. Thà cắt và báo còn hơn để một việc nền ngậm tiến trình cả đêm.
        self.timeout = float(os.environ.get("JAVIS_AGY_TIMEOUT") or 900)

    def is_available(self) -> bool:
        return self.cli_path is not None

    def _build_args(self, prompt_argv: Optional[str]) -> list[str]:
        args = [self.cli_path]
        if self.model and co_co("--model"):
            args += ["--model", self.model]
        args += co_quyen_cho_mode(self.mode)
        if co_co("--output-format"):
            args += ["--output-format", "stream-json"]
        if self.session_id and co_co("--conversation"):
            args += ["--conversation", self.session_id]
        if co_co("--add-dir"):
            for d in self.include_dirs:
                args += ["--add-dir", str(d)]
        args += list(self.extra_args)
        # `-p` là cờ bật chế độ in-một-lượt-rồi-thoát. Truyền prompt qua argv hay stdin do
        # nhan_prompt_qua_stdin() quyết theo chính --help của bản đang cài.
        args += ["-p", prompt_argv if prompt_argv is not None else ""]
        return args

    async def query(self, prompt: str) -> AsyncIterator[dict]:
        if not self.cli_path:
            yield {"type": "error",
                   "content": f"Không tìm thấy Antigravity CLI (`agy`). Cài một lần trên máy "
                              f"chạy Javis:\n\n`{lenh_cai()}`\n\nRồi gõ `agy` một lần để đăng "
                              f"nhập Google."}
            return
        full = (self.instructions.strip() + "\n\n" + prompt) if self.instructions else prompt
        qua_stdin = nhan_prompt_qua_stdin()
        # Windows chặn TỔNG dòng lệnh ở 32767 ký tự (CreateProcess). Hội thoại dài thì
        # instructions (system prompt Javis + CLAUDE.md của brain + ngữ cảnh) vượt ngưỡng và
        # Python ném `WinError 206: The filename or extension is too long` - một câu không ai
        # đoán ra là do hội thoại dài (người dùng báo 2026-08-13, Javis 0.30.3, agy 1.1.12).
        #
        # Không tự cắt bớt ngữ cảnh: cắt là câu trả lời sai một cách âm thầm, tệ hơn hẳn. Cũng
        # chưa có đường vòng - người dùng đã ĐO trên máy thật rằng bản 1.1.12 không nhận prompt
        # qua stdin, không đọc AGENTS.md, không đọc GEMINI.md, và `--help` không có cờ nào nhận
        # prompt từ file. Nên nói thẳng, kèm hai việc làm được ngay.
        #
        # Ngày nào Google thêm cờ nhận prompt qua stdin thì `nhan_prompt_qua_stdin()` tự bắt
        # được và nhánh này thôi chạm tới.
        if (not qua_stdin and os.name == "nt"
                and len(full) + sum(len(a) + 3 for a in self._build_args("")) > 30000):
            yield {"type": "error",
                   "content": "Hội thoại này đã quá dài để gửi cho Antigravity CLI trên Windows "
                              "(Windows chặn độ dài dòng lệnh, mà bản `agy` hiện tại chưa nhận "
                              "prompt qua đường khác).\n\nHai cách đi tiếp: **mở hội thoại mới**, "
                              "hoặc **đổi sang bộ não khác** ở trang Models cho hội thoại này. "
                              "Bản chạy bằng Docker/Linux không dính giới hạn này."}
            return
        args = self._build_args(None if qua_stdin else full)
        loop = asyncio.get_running_loop()
        hang: asyncio.Queue = asyncio.Queue()
        HET = object()

        def doc_luong():
            proc = None
            try:
                proc = subprocess.Popen(
                    args, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                    cwd=self.cwd, text=True, encoding="utf-8", errors="replace", bufsize=1,
                    creationflags=_no_window(), start_new_session=(os.name != "nt"),
                )
                try:
                    if qua_stdin:
                        proc.stdin.write(full)
                    proc.stdin.close()
                except Exception:
                    pass
                for line in iter(proc.stdout.readline, ""):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        loop.call_soon_threadsafe(hang.put_nowait, json.loads(line))
                    except json.JSONDecodeError:
                        loop.call_soon_threadsafe(hang.put_nowait, {"_raw": line})
                err = ""
                try:
                    err = (proc.stderr.read() or "").strip()
                except Exception:
                    pass
                ma = proc.wait(timeout=self.timeout)
                if ma != 0 or err:
                    loop.call_soon_threadsafe(hang.put_nowait, {"_exit": ma, "_err": err})
            except subprocess.TimeoutExpired:
                loop.call_soon_threadsafe(
                    hang.put_nowait,
                    {"_exit": -1, "_err": f"Antigravity CLI chạy quá {int(self.timeout)}s nên bị "
                                          f"cắt. Nếu việc thật sự dài thì nâng biến môi trường "
                                          f"JAVIS_AGY_TIMEOUT."})
            except Exception as e:
                loop.call_soon_threadsafe(hang.put_nowait,
                                          {"_exit": -1, "_err": f"{type(e).__name__}: {e}"})
            finally:
                try:
                    if proc and proc.poll() is None:
                        proc.terminate()
                except Exception:
                    pass
                loop.call_soon_threadsafe(hang.put_nowait, HET)

        threading.Thread(target=doc_luong, name=f"javis-agy-{self.tag}", daemon=True).start()

        cac_manh: list[str] = []
        da_loi = False
        while True:
            ev = await hang.get()
            if ev is HET:
                break
            for ra in self._doi_su_kien(ev, cac_manh):
                if ra.get("type") == "error":
                    da_loi = True
                yield ra
        text = "".join(cac_manh).strip()
        if text:
            yield {"type": "final", "content": text}
        elif not da_loi:
            # Lưới an toàn cuối. Bản 1.0.0 của agy có lỗi nuốt stdout khi chạy qua ống dẫn
            # (issue #76 của google-antigravity/antigravity-cli); im lặng ở đây thì người dùng
            # lại thấy đúng cái bong bóng rỗng như hồi Gemini CLI.
            yield {"type": "error",
                   "content": "Antigravity CLI chạy xong nhưng không trả về nội dung nào. Bản "
                              "CLI quá cũ có lỗi mất stdout khi chạy nền - thử nâng cấp: "
                              f"`{lenh_cai()}`"}

    def _doi_su_kien(self, ev: dict, cac_manh: list) -> list:
        """Một dòng NDJSON của `agy` -> 0..n sự kiện theo hợp đồng của Javis.

        CHƯA ĐO được tên trường thật, nên nhận rộng: gom mọi hình dạng "có chữ để hiện" mà một
        stream sự kiện hay dùng. Dòng lạ hoàn toàn thì giữ nguyên làm chữ ở cuối hàm - mất công
        đẹp còn hơn mất câu trả lời.
        """
        if "_raw" in ev:
            cac_manh.append(str(ev["_raw"]))
            return []
        if "_exit" in ev:
            loi = str(ev.get("_err") or "").strip()
            if ev.get("_exit") == 0 and not loi:
                return []
            if _la_loi_chua_dang_nhap(loi):
                return [{"type": "error",
                         "content": "Antigravity CLI chưa đăng nhập. Mở terminal trên máy chạy "
                                    "Javis, gõ `agy` rồi làm theo hướng dẫn (qua SSH thì nó in "
                                    "ra một link để mở trên máy anh)."}]
            if not loi:
                loi = f"Antigravity CLI thoát với mã {ev.get('_exit')}."
            return [{"type": "error", "content": loi[:1500]}]

        t = str(ev.get("type") or ev.get("event") or "").lower()

        # `agy` gói payload LỒNG dưới đúng tên sự kiện, đo trên 1.1.12:
        #
        #   {"event":"init","conversation_id":"...","init":{"model":"...","cwd":"/app"}}
        #   {"event":"step_update","step_update":{"step_type":"agent_response",
        #                                        "text_delta":"Xin chào!","usage":{...}}}
        #   {"event":"result","result":{"status":"SUCCESS","response":"Xin chào!","usage":{...}}}
        #
        # Bản đầu chỉ đọc tầng NGOÀI CÙNG nên không thấy gì - `agy` chạy thành công mà bong bóng
        # trả lời rỗng. Trải phẳng một tầng để phần dưới đọc như mọi stream phẳng khác. Giữ khoá
        # tầng ngoài khi trùng tên là cố ý: `conversation_id` nằm ở ngoài chứ không ở trong.
        _sub = ev.get(t)
        if isinstance(_sub, dict):
            _gop = dict(_sub)
            _gop.update({k: v for k, v in ev.items() if k != t})
            ev = _gop

        # Mở mạch: nhặt id hội thoại để lượt sau nối lại được.
        if t in ("init", "session", "conversation", "start", "system"):
            for k in ("conversation_id", "session_id", "conversationId", "sessionId", "id"):
                v = ev.get(k)
                if isinstance(v, str) and v.strip():
                    self.session_id = v.strip()
                    break
            return []

        if t in ("tool_use", "tool_call", "tool"):
            return [{"type": "tool_call",
                     "name": str(ev.get("tool_name") or ev.get("name") or ""),
                     "id": str(ev.get("tool_id") or ev.get("id") or ""),
                     "input": ev.get("parameters") or ev.get("input") or {}}]
        if t in ("tool_result", "tool_output"):
            return [{"type": "tool_result", "id": str(ev.get("tool_id") or ev.get("id") or ""),
                     "status": str(ev.get("status") or ""),
                     "content": str(ev.get("output") or ev.get("content") or "")[:2000]}]
        if t == "error":
            tin = str(ev.get("message") or ev.get("error") or "Antigravity CLI lỗi.")
            if _la_loi_chua_dang_nhap(tin):
                return [{"type": "error",
                         "content": "Antigravity CLI chưa đăng nhập. Gõ `agy` một lần trên máy "
                                    "chạy Javis."}]
            if str(ev.get("severity") or "error") == "warning":
                return []
            return [{"type": "error", "content": tin[:1500]}]

        ra = []
        if t in ("result", "final", "done", "complete"):
            st = ev.get("stats") or ev.get("usage") or {}
            if isinstance(st, dict) and st:
                ra.append({"type": "usage",
                           "input_tokens": int(st.get("input_tokens")
                                               or st.get("prompt_tokens") or 0),
                           "output_tokens": int(st.get("output_tokens")
                                                or st.get("completion_tokens") or 0),
                           "total_tokens": int(st.get("total_tokens") or 0),
                           "cached": int(st.get("cached") or 0)})
            if str(ev.get("status") or "").lower() == "error":
                e = ev.get("error") or {}
                tin = str(e.get("message") if isinstance(e, dict) else e) or ""
                ra.append({"type": "error",
                           "content": tin[:1500] or "Antigravity CLI kết thúc với lỗi."})
                return ra
            # Sự kiện kết thúc mang LẠI TOÀN VĂN câu trả lời trong `response`, trong khi các
            # `text_delta` trước đó đã gom đủ rồi -> gom tiếp là câu trả lời hiện HAI LẦN.
            #
            # Nhưng cũng KHÔNG được bỏ hẳn: lượt trả lời ngắn có bản chỉ phát mỗi `result`,
            # không có delta nào. Nên chỉ lấy khi tay trắng - đúng một lần, và không bao giờ
            # rỗng vì lý do "đã bỏ qua chỗ duy nhất có chữ".
            if cac_manh:
                return ra

        # Còn lại: mọi thứ trông như chữ của trợ lý đều gom vào câu trả lời. Đây là chỗ hứng
        # những hình dạng chưa đo được, nên viết rộng có chủ đích.
        if str(ev.get("role") or "assistant").lower() in ("assistant", "model", "agent", ""):
            for k in ("text_delta", "content", "text", "delta", "message", "response", "output"):
                v = ev.get(k)
                if isinstance(v, str) and v:
                    cac_manh.append(v)
                    break
                if isinstance(v, dict):
                    vv = v.get("text") or v.get("content")
                    if isinstance(vv, str) and vv:
                        cac_manh.append(vv)
                        break
        return ra


def _la_loi_chua_dang_nhap(loi: str) -> bool:
    """Câu này có phải chuyện chưa đăng nhập không.

    "select login method" nằm trong danh sách vì bản `agy` chưa có phiên KHÔNG báo lỗi - nó mở
    thẳng menu chọn cách đăng nhập rồi ngồi chờ bàn phím (ảnh chủ repo 2026-08-13). Với một
    lượt chạy nền thì đó chính là "chưa đăng nhập", chỉ khác cách nói.
    """
    l = (loi or "").lower()
    return any(k in l for k in ("not signed in", "not logged in", "sign in", "login required",
                                "unauthenticated", "no active session", "authentication",
                                "select login method"))


def kiem_tra_nhanh(timeout: float = 60.0) -> dict:
    """Chạy thử một lượt cực ngắn cho nút "Kiểm tra lại" ở trang Models.

    Chỉ đọc trạng thái từ `models` thì mới biết tài khoản còn sống, chưa biết luồng chat có
    chạy không - mà đúng chỗ đó là chỗ Gemini CLI gãy. Nên ở đây chạy thật một lượt.
    """
    cli = find_antigravity_cli()
    if not cli:
        return {"ok": False, "error": f"Chưa cài Antigravity CLI. {lenh_cai()}"}
    args = [cli]
    if co_co("--output-format"):
        args += ["--output-format", "json"]
    args += ["-p", "Trả lời đúng một chữ: ok"]
    try:
        r = subprocess.run(args, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=timeout, creationflags=_no_window())
    except subprocess.TimeoutExpired as e:
        # Hết giờ ở đây gần như LUÔN là "chưa đăng nhập" chứ không phải máy chậm: chưa có phiên
        # thì `agy` mở menu "Select login method" rồi ngồi chờ bàn phím, mà ở đây không có ai
        # gõ. Câu "không trả lời kịp" đúng về mặt kỹ thuật nhưng chỉ sai đường - chủ repo bấm
        # Kiểm tra lại và ngồi nhìn "Đang thử..." mà không biết việc phải làm là đăng nhập
        # (ảnh 2026-08-13). Soi thứ nó kịp in ra để nói cho đúng.
        _ra = ""
        for _t in (getattr(e, "stdout", None), getattr(e, "stderr", None), getattr(e, "output", None)):
            if isinstance(_t, bytes):
                _t = _t.decode("utf-8", "replace")
            if _t:
                _ra += _t
        if _la_loi_chua_dang_nhap(_ra) or "select login method" in _ra.lower():
            return {"ok": False,
                    "error": "Chưa đăng nhập - CLI đang đứng ở màn chọn cách đăng nhập. Bấm "
                             "\"Đăng nhập Google\" ngay trên thẻ này."}
        return {"ok": False, "error": "Antigravity CLI không trả lời kịp."}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}
    out = (r.stdout or "").strip()
    if r.returncode != 0:
        loi = (r.stderr or out or "").strip()
        if _la_loi_chua_dang_nhap(loi):
            return {"ok": False, "error": "Chưa đăng nhập. Gõ `agy` một lần trên máy chạy Javis."}
        return {"ok": False, "error": loi[:400] or f"Thoát mã {r.returncode}"}
    if not out:
        return {"ok": False,
                "error": "CLI chạy xong nhưng không in ra gì. Bản cũ có lỗi mất stdout khi chạy "
                         f"nền - nâng cấp bằng: {lenh_cai()}"}
    try:
        d = json.loads(out)
    except json.JSONDecodeError:
        return {"ok": True, "reply": out[:200]}
    if isinstance(d, dict) and d.get("error"):
        e = d["error"]
        return {"ok": False,
                "error": str(e.get("message") if isinstance(e, dict) else e)[:400]}
    tra = ""
    if isinstance(d, dict):
        for k in ("response", "result", "content", "text", "output"):
            if isinstance(d.get(k), str):
                tra = d[k]
                break
    return {"ok": True, "reply": (tra or out)[:200]}
