"""Bộ não thứ 11: xAI Grok Build CLI (binary `grok`), chạy bằng GÓI SuperGrok / X Premium+.

Đối xứng với `GeminiCLI` và `CodexCLI`: Javis không giữ token của ai cả, nó gọi đúng binary
`grok` của máy và mượn phiên đăng nhập mà chính CLI đó giữ trong `~/.grok/auth.json`.

**Vì sao module này KHÔNG chép khuôn `antigravity_cli.py`** - hai chỗ đau nhất của `agy` đều
không có ở đây:

- Trạng thái đăng nhập nằm trong FILE ĐỌC ĐƯỢC (`~/.grok/auth.json`, quyền 0600), không phải
  keyring của hệ điều hành. Nên `auth_status()` đọc đĩa, không phải đẻ một tiến trình mỗi lần
  mở trang Models, và trang Models nói được sự thật thay vì "hãy tự gõ lệnh rồi bấm kiểm tra".
- Cấu hình MCP đọc theo THƯ MỤC LÀM VIỆC (`<cwd>/.grok/config.toml`), nên ghi vào trong brain
  là mỗi brain một hub riêng, không giẫm lên cấu hình cá nhân ở `~/.grok/config.toml` và không
  brain nọ đọc header brain kia. Giống hệt `<brain>/.gemini/settings.json` bên Gemini CLI.

Và nó có thêm một thứ Antigravity không có: `grok login --device-auth` in ra URL + mã, tức
ĐĂNG NHẬP ĐƯỢC TỪ VPS qua nút bấm trên dashboard, không bắt người dùng mở terminal.

**GIỮ của `antigravity_cli.py`: `co_co()` - dò cờ trước khi truyền.** Bản CLI này còn rất mới
và đổi cờ liên tục; truyền một cờ nó chưa có là nó thoát ngay với "unknown flag", hỏng cả lượt
chat chỉ vì một tuỳ chọn phụ. Hỏi `--help` trước rồi mới truyền thì bản cũ vẫn chạy, chỉ mất
tính năng. MỌI cờ dưới đây đều đi qua `co_co()`, không có ngoại lệ.

Những gì đọc từ tài liệu chính chủ (`xai-org/grok-build`, user-guide) và VẪN PHẢI ĐO trên máy
thật trước khi tin - xem `docs/dev/2026-08-grok-cli.md`:

- `-p/--single <PROMPT>` chạy headless, `--prompt-file <PATH>` đọc prompt từ file.
- `--output-format streaming-json` phát NDJSON: `thought`, `tool_call`, `tool_call_update`,
  `text`, `usage`, `end`. `--output-format json` trả một cục có `text`/`sessionId`/`usage`.
- Phiên: `-s/--session-id <ID>` mở mới với id tự cấp, `-r/--resume <ID>` nối lại,
  `-c/--continue` nối phiên gần nhất của thư mục.
- Quyền: `--permission-mode bypassPermissions|defaultMode`, `--allow`/`--deny` theo luật
  `Bash(...)`, `Write(...)`, `Edit(...)`, `MCPTool(...)`; `--max-turns N`.
- MCP: `[mcp_servers.<ten>]` trong `config.toml`, entry HTTP dùng khoá `url` + `headers`.
"""
from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from pathlib import Path
from typing import AsyncIterator, Optional

from claude_cli import _home_dir, _no_window, tim_binary

try:                       # Python 3.11+ có sẵn; đọc TOML, KHÔNG ghi được.
    import tomllib
except ModuleNotFoundError:   # pragma: no cover - Javis yêu cầu 3.11, đây chỉ là lưới đỡ
    tomllib = None            # type: ignore[assignment]

# Model DỰ PHÒNG, chỉ dùng khi chưa hỏi được danh sách live từ CLI. Cố ý để ngắn và cố ý KHÔNG
# đưa vào `PROVIDER_DEFS`: bài học của `agy` là bảng model chép tay thì sai lặng lẽ, mà tên
# model của xAI đổi liên tục.
MODELS_DU_PHONG = ["grok-4.6", "grok-4.5"]

LENH_CAI = "curl -fsSL https://x.ai/cli/install.sh | bash"
LENH_CAI_WIN = "irm https://x.ai/cli/install.ps1 | iex"

# Mức quyền Javis -> luật chặn của Grok. Xem `permission_cho_mode`.
_LUAT_CHAN = {
    # suggest: CHỈ ĐỌC. Chặn cả ghi file lẫn lệnh máy.
    "suggest": ("Write(*)", "Edit(*)", "Bash(*)", "NotebookEdit(*)"),
    # auto: ghi file nháp được, KHÔNG chạy lệnh máy.
    "auto": ("Bash(*)",),
    # full: không chặn gì ở tầng CLI.
    "full": (),
}


def _grok_home() -> Path:
    """Thư mục cấu hình của `grok`. GROK_HOME thắng, đúng như CLI xử lý."""
    env = (os.environ.get("GROK_HOME") or "").strip()
    if env:
        return Path(env).expanduser()
    return _home_dir() / ".grok"


def _doc_json(p: Path):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def find_grok_cli() -> Optional[str]:
    """Tìm binary `grok`. Cửa thoát JAVIS_GROK_BIN cho máy cài chỗ lạ."""
    envp = (os.environ.get("JAVIS_GROK_BIN") or "").strip()
    if envp:
        try:
            if Path(envp).exists():
                return envp
        except Exception:
            pass
    cli = tim_binary("grok")
    if cli:
        return cli
    home = _home_dir()
    # Installer chính chủ thả binary vào ~/.local/bin (Unix) hoặc %LOCALAPPDATA% (Windows).
    for p in (home / ".local" / "bin" / "grok",
              home / ".grok" / "bin" / "grok",
              Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "grok" / "grok.exe"):
        try:
            if p.exists():
                return str(p)
        except Exception:
            pass
    return None


def lenh_cai() -> str:
    return LENH_CAI_WIN if os.name == "nt" else LENH_CAI


def _moi_truong() -> dict:
    """Môi trường cho một lượt chạy `grok`: kế thừa của server, tắt bộ tự cập nhật.

    Vì sao phải tắt: Javis chạy `grok` headless trên VPS và trong container. Bộ tự cập nhật của
    CLI có thể xen vào giữa lượt - tải bản mới, ghi vào chỗ chỉ đọc, hoặc in thêm chữ vào
    stdout làm hỏng dòng NDJSON đang đọc. Tài liệu chính chủ khuyên đúng điều này cho container.

    Đặt CẢ biến môi trường lẫn cờ `--no-auto-update` (xem `_build_args`) là có chủ ý, không
    phải thừa: cờ đi qua `co_co()` nên bản CLI chưa khai nó thì không được truyền, còn biến môi
    trường thì bản nào cũng nhận hoặc lặng lẽ bỏ qua - không bao giờ làm CLI thoát lỗi. Hai lớp
    phủ cho nhau.
    """
    env = dict(os.environ)
    env.setdefault("GROK_DISABLE_AUTOUPDATER", "1")
    return env


# ---------------------------------------------------------------------------
# Dò cờ: hỏi `--help` trước, đừng đoán
# ---------------------------------------------------------------------------
_HELP_CACHE: dict = {"path": None, "text": "", "ts": 0.0}
_HELP_TTL = 300.0     # 5 phút: một phiên chat không đẻ tiến trình mỗi lượt, mà nâng cấp bản
                      # CLI xong cũng không phải khởi động lại Javis mới nhận cờ mới.


def _help_text() -> str:
    """Nội dung `grok --help`, nhớ trong RAM. Rỗng nếu không chạy được."""
    cli = find_grok_cli()
    if not cli:
        return ""
    now = time.time()
    if (_HELP_CACHE["path"] == cli and _HELP_CACHE["text"]
            and now - _HELP_CACHE["ts"] < _HELP_TTL):
        return _HELP_CACHE["text"]
    try:
        r = subprocess.run([cli, "--help"], capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=20, creationflags=_no_window(),
                           env=_moi_truong())
        txt = (r.stdout or "") + "\n" + (r.stderr or "")
    except Exception:
        txt = ""
    _HELP_CACHE.update(path=cli, text=txt, ts=now)
    return txt


def co_co(*ten_co: str) -> bool:
    """Binary trên máy CÓ khai cờ này không (`--help` nhắc tới nó).

    Fail-closed: không đọc được `--help` thì coi như KHÔNG có cờ. Chạy thiếu một tuỳ chọn phụ
    còn hơn thoát ngay vì "unknown flag".
    """
    txt = _help_text()
    if not txt:
        return False
    return any(c in txt for c in ten_co)


def phien_moi() -> str:
    return str(uuid.uuid4())


def permission_cho_mode(mode: Optional[str]) -> list:
    """Mức quyền của Javis -> cờ quyền của Grok. Giá trị lạ về nấc CHẶT NHẤT.

    Fail-closed cố ý: một chuỗi mode gõ sai không được
    phép biến thành toàn quyền ghi file và chạy lệnh máy.

    HÀNG RÀO THẬT nằm ở header `X-Javis-Mode` mà MCP hub áp cho mọi tool đi qua nó - cái đó
    chặn được cả tool của MCP đã đấu. Cờ ở đây chỉ là lớp thứ hai, chặn tool NATIVE của chính
    Grok (Bash/Write/Edit), thứ hub không nhìn thấy.
    """
    m = str(mode or "").strip().lower()
    luat = _LUAT_CHAN.get(m)
    if luat is None:            # mode lạ -> nấc chặt nhất
        luat = _LUAT_CHAN["suggest"]
        m = "suggest"
    args: list = []
    if co_co("--permission-mode"):
        # headless mà để CLI dừng lại hỏi duyệt là treo tới hết giờ, nên luôn đặt tường minh.
        args += ["--permission-mode", "bypassPermissions"]
    if co_co("--deny"):
        for r in luat:
            args += ["--deny", r]
    return args


# ---------------------------------------------------------------------------
# TOML tối thiểu: đủ để round-trip `config.toml` của Grok
# ---------------------------------------------------------------------------
def _toml_gia_tri(v) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return json.dumps(v)
    if isinstance(v, (list, tuple)):
        return "[" + ", ".join(_toml_gia_tri(x) for x in v) + "]"
    return json.dumps(str(v), ensure_ascii=False)   # JSON string escape == TOML basic string


def _toml_khoa(k: str) -> str:
    """Khoá TOML: để trần nếu hợp lệ, quote nếu không.

    Bare key của TOML nhận A-Za-z0-9_- nên `mcp_servers`, `javis` lẫn `X-Javis-Mode` đều để
    trần được. Quote hết thì vẫn ĐÚNG nhưng ra một file đầy dấu nháy mà người mở lên đọc phải
    dụi mắt - file này nằm trong brain, người dùng có mở ra xem.
    """
    k = str(k)
    if k and all(c.isascii() and (c.isalnum() or c in "_-") for c in k):
        return k
    return json.dumps(k, ensure_ascii=False)


def _toml_dump(d: dict, duong: tuple = ()) -> str:
    """Serializer TOML tối thiểu: str/bool/số/list/dict lồng nhau.

    Vì sao tự viết thay vì thêm `tomli-w` vào requirements: repo cố ý giữ danh sách phụ thuộc
    gọn (xem lý do chọn `segno` trong requirements.txt), mà thứ cần ghi ở đây là đúng một bảng
    hai tầng. `tomllib` của stdlib chỉ ĐỌC được, nên phần ghi phải tự lo.

    HẠN CHẾ ĐÃ BIẾT: round-trip qua đây làm MẤT CHÚ THÍCH trong file. Chấp nhận được vì file
    này nằm trong `<brain>/.grok/` - thư mục do chính Javis dựng trong brain, không phải
    `~/.grok/config.toml` cá nhân của người dùng.
    """
    dong: list = []
    bang_con: list = []
    for k, v in d.items():
        if isinstance(v, dict):
            bang_con.append((k, v))
        else:
            dong.append(f"{_toml_khoa(k)} = {_toml_gia_tri(v)}")
    ra = ""
    if duong and dong:
        ra += "[" + ".".join(_toml_khoa(x) for x in duong) + "]\n"
    ra += "\n".join(dong)
    if dong:
        ra += "\n"
    for k, v in bang_con:
        con = _toml_dump(v, duong + (k,))
        if con.strip():
            ra += ("\n" if ra.strip() else "") + con
        else:
            ra += ("\n" if ra.strip() else "") + "[" + ".".join(
                _toml_khoa(x) for x in duong + (k,)) + "]\n"
    return ra


def _doc_toml(p: Path) -> dict:
    """Đọc TOML, KHÔNG phân biệt được 'không có file' với 'file hỏng'. Chỉ dùng khi đọc hỏng
    cũng không sao (liệt kê model, soi trạng thái). Chỗ nào sắp GHI ĐÈ thì dùng `_doc_toml_ky`."""
    ok, d = _doc_toml_ky(p)
    return d if ok else {}


def _doc_toml_ky(p: Path) -> tuple:
    """(đọc_được, dict). Phân biệt ba ca, và sự phân biệt này KHÔNG phải chuyện làm màu.

    File chưa có → (True, {}): ghi mới là đúng.
    File có và parse được → (True, nội dung): ghi đè phần của mình, giữ phần còn lại.
    File có mà parse KHÔNG được → (False, {}): tuyệt đối KHÔNG được ghi đè.

    Ca thứ ba là chỗ suýt mất dữ liệu: gộp nó vào ca đầu (trả `{}` rồi ghi tiếp) là mỗi lần
    Javis chạm vào một `config.toml` gõ sai một dấu ngoặc - hoặc dùng cú pháp mà `tomllib` của
    Python chưa biết - thì toàn bộ cấu hình Grok của người dùng trong brain đó bị xoá sạch,
    không một câu lỗi. Đây đúng là hạng lỗi im lặng mà module này viết ra để tránh.
    """
    try:
        if not p.exists():
            return True, {}
    except Exception:
        return False, {}
    if tomllib is None:      # pragma: no cover - Javis yêu cầu Python 3.11
        return False, {}
    try:
        with open(p, "rb") as f:
            d = tomllib.load(f)
        return True, (d if isinstance(d, dict) else {})
    except Exception as e:
        print(f"[grok mcp settings] `{p}` không đọc được, KHÔNG ghi đè: {e}", file=sys.stderr)
        return False, {}


# ---------------------------------------------------------------------------
# MCP: ghi hub của Javis vào `<brain>/.grok/config.toml`
# ---------------------------------------------------------------------------
def hub_entry(url: str, headers: Optional[dict] = None) -> dict:
    """Hình dạng entry MCP HTTP của Grok.

    Để hình dạng entry TRONG module engine chứ không viết tay ở `main.py` là bài học đắt của
    `agy`: nó đọc khoá `serverUrl`, còn `httpUrl` (khoá của Gemini CLI) bị bỏ qua không một
    tiếng động, và đó là thứ làm bộ não đó chạy mấy bản mà không có lấy một tool nào của Javis.
    Grok dùng khoá `url`, khác cả hai. Giữ ở đây để nó không trôi theo file nào khác.
    """
    e: dict = {"url": url}
    if headers:
        e["headers"] = dict(headers)
    return e


def mcp_config_path(vault_root) -> Path:
    return Path(vault_root).expanduser() / ".grok" / "config.toml"


def ghi_mcp_settings(vault_root, hub: Optional[dict]) -> Optional[str]:
    """Ghi `<vault>/.grok/config.toml` với đúng một entry MCP trỏ về hub Javis.

    Vì sao ghi vào brain chứ không vào `~/.grok`: file HOME là của người dùng và dùng chung cho
    mọi thứ họ chạy bằng `grok`; đè lên đó là Javis giẫm vào cấu hình cá nhân, và nhiều brain
    thì brain nọ đọc header brain kia. Grok đọc cấu hình theo thư mục làm việc, mà Javis luôn
    chạy nó với cwd = gốc brain, nên đây vừa đúng chỗ vừa cô lập sẵn từng brain.

    `hub=None` (chưa bật hub) → GỠ entry javis nếu có, giữ nguyên phần còn lại của file.
    Trả đường dẫn file đã ghi, hoặc None nếu không ghi được.
    """
    try:
        p = mcp_config_path(vault_root)
        doc_duoc, cu = _doc_toml_ky(p)
        if not doc_duoc:
            # Thà chạy KHÔNG có tool của Javis còn hơn xoá cấu hình của người dùng. Lỗi đã in
            # ra stderr ở `_doc_toml_ky`; `trang_thai_mcp` sẽ báo `co_javis=False` nên nút
            # "Kiểm tra lại" trên trang Models nói được là hub chưa vào.
            return None
        servers = cu.get("mcp_servers")
        if not isinstance(servers, dict):
            servers = {}
        if hub:
            servers["javis"] = hub
        else:
            servers.pop("javis", None)
        if servers:
            cu["mcp_servers"] = servers
        else:
            cu.pop("mcp_servers", None)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(_toml_dump(cu), encoding="utf-8")
        try:
            os.chmod(p, 0o600)   # chứa hub token
        except Exception:
            pass
        return str(p)
    except Exception as e:
        print(f"[grok mcp settings] {e}", file=sys.stderr)
        return None


def trang_thai_mcp(vault_root) -> dict:
    """ĐỌC LẠI chính file vừa ghi để trang Models nói được sự thật.

    Bài học của `agy` (0.43.0): cấu hình ghi thành công nhưng SAI CHỖ hoặc SAI KHOÁ thì CLI
    chạy trơn tru mà không có lấy một tool nào của Javis, và không ở đâu có một câu lỗi để lần
    ra. "Đã ghi xong" không phải bằng chứng; đọc lại mới là.
    """
    p = mcp_config_path(vault_root)
    ra = {"file": str(p), "ton_tai": False, "co_javis": False, "url": "", "so_header": 0}
    try:
        ra["ton_tai"] = p.exists()
    except Exception:
        return ra
    if not ra["ton_tai"]:
        return ra
    d = _doc_toml(p)
    e = ((d.get("mcp_servers") or {}) or {}).get("javis")
    if isinstance(e, dict):
        ra["co_javis"] = True
        ra["url"] = str(e.get("url") or "")
        h = e.get("headers")
        ra["so_header"] = len(h) if isinstance(h, dict) else 0
    return ra


# ---------------------------------------------------------------------------
# Đăng nhập
# ---------------------------------------------------------------------------
def auth_status() -> dict:
    """Đã đăng nhập chưa: {connected, method, account, plan, error}.

    ĐỌC FILE, không gọi CLI - mỗi lần mở trang Models mà đẻ một tiến trình là vài trăm ms cho
    một câu trả lời nằm sẵn trên đĩa.

    Thứ tự xét bám đúng "Auth Precedence" trong tài liệu chính chủ: phiên đăng nhập trong
    `~/.grok/auth.json` thắng, `XAI_API_KEY` là đường lùi khi không có phiên nào.
    """
    cli = find_grok_cli()
    if not cli:
        return {"connected": False, "method": "", "account": "", "plan": "",
                "error": f"Chưa cài Grok CLI ({lenh_cai()})."}
    auth = _doc_json(_grok_home() / "auth.json") or {}
    if isinstance(auth, dict) and (auth.get("access_token") or auth.get("refresh_token")):
        # Tên trường trong auth.json chưa được tài liệu hoá, nên dò vài tên hợp lý rồi thôi -
        # thiếu tên tài khoản chỉ làm thẻ bớt đẹp, không làm sai trạng thái kết nối.
        acc = ""
        for k in ("email", "account", "username", "handle", "user"):
            v = auth.get(k)
            if isinstance(v, str) and v.strip():
                acc = v.strip()
                break
            if isinstance(v, dict):
                acc = str(v.get("email") or v.get("name") or "").strip()
                if acc:
                    break
        plan = ""
        for k in ("plan", "subscription", "tier"):
            v = auth.get(k)
            if isinstance(v, str) and v.strip():
                plan = v.strip()
                break
        return {"connected": True, "method": str(auth.get("issuer") or "oauth"),
                "account": acc, "plan": plan, "error": ""}
    if (os.environ.get("XAI_API_KEY") or "").strip():
        return {"connected": True, "method": "xai-api-key", "account": "", "plan": "",
                "error": ""}
    return {"connected": False, "method": "", "account": "", "plan": "",
            "error": "Đã cài Grok CLI nhưng chưa đăng nhập. Bấm \"Đăng nhập\" ngay trên thẻ này."}


def login_huong_dan() -> dict:
    return {
        "cai": lenh_cai(),
        "dang_nhap": "grok login --device-auth",
        "ghi_chu": ("Cách khác: chạy `grok login` trong terminal. Qua SSH thì thêm "
                    "`--device-auth`, nó in ra một link và một mã để mở trên máy bạn. "
                    "Javis nhận ra cả tài khoản đăng nhập kiểu đó."),
    }


# ---------------------------------------------------------------------------
# Đăng nhập bằng device code, điều khiển từ dashboard
# ---------------------------------------------------------------------------
# `grok login --device-auth` KHÔNG phải một vòng trao đổi hai bước như OAuth của Gemini: nó in
# ra một link và một mã, rồi TỰ ĐỨNG ĐÓ HỎI máy chủ cho tới khi người dùng bấm xong trên web.
# Nên Javis không có "mã" nào để nhận lại và gửi đi - việc của nó là: mở tiến trình, bóc lấy
# link + mã, trả cho giao diện, rồi để tiến trình chạy tiếp và theo dõi `auth.json` xuất hiện.
#
# Đây là chỗ Grok làm được thứ Antigravity không làm được: đăng nhập ngay trên dashboard, kể cả
# khi Javis đang chạy trên VPS không có trình duyệt.
_LOGIN: dict = {"proc": None, "url": "", "code": "", "loi": "", "bat_dau": 0.0}
_URL_RE = None


def _bat_url_code(dong: str) -> None:
    """Bóc link và mã từ một dòng CLI in ra. Cả hai đều 'thấy thì lấy', không đoán vị trí."""
    global _URL_RE
    if _URL_RE is None:
        import re
        _URL_RE = re.compile(r"https?://[^\s\"'<>]+")
    if not _LOGIN["url"]:
        m = _URL_RE.search(dong)
        if m:
            _LOGIN["url"] = m.group(0).rstrip(".,);")
    if not _LOGIN["code"]:
        # Mã device code thường là chữ-số viết hoa có gạch nối (ABCD-EFGH). Tìm token dạng đó,
        # và chỉ nhận khi nó KHÔNG nằm trong link vừa bắt được.
        import re
        for tok in re.findall(r"\b[A-Z0-9]{4,}(?:-[A-Z0-9]{4,})+\b", dong):
            if tok not in (_LOGIN["url"] or ""):
                _LOGIN["code"] = tok
                break


def login_start(cho_giay: float = 30.0) -> dict:
    """Mở `grok login --device-auth`, trả {ok, url, code} để giao diện hiện ra cho người dùng.

    Tiến trình được GIỮ LẠI chạy tiếp sau khi hàm này trả về: nó còn phải hỏi máy chủ tới khi
    người dùng bấm xác nhận trên web. Giao diện theo dõi tiếp bằng `login_trang_thai()`.
    """
    cli = find_grok_cli()
    if not cli:
        return {"ok": False, "error": f"Chưa cài Grok CLI ({lenh_cai()})."}
    logout_huy_tien_trinh()
    args = [cli, "login"]
    if co_co("--device-auth", "--device-code"):
        args.append("--device-auth")
    try:
        proc = subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, text=True, encoding="utf-8",
                                errors="replace", bufsize=1, creationflags=_no_window(),
                                env=_moi_truong(), start_new_session=(os.name != "nt"))
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}
    _LOGIN.update(proc=proc, url="", code="", loi="", bat_dau=time.time())

    def doc():
        try:
            for dong in iter(proc.stdout.readline, ""):
                _bat_url_code(dong.strip())
        except Exception:
            pass

    threading.Thread(target=doc, name="javis-grok-login", daemon=True).start()
    han = time.time() + cho_giay
    while time.time() < han:
        if _LOGIN["url"]:
            break
        if proc.poll() is not None:
            break
        time.sleep(0.2)
    if not _LOGIN["url"]:
        if proc.poll() is not None and auth_status().get("connected"):
            return {"ok": True, "xong": True, "url": "", "code": ""}
        return {"ok": False,
                "error": ("Grok CLI không in ra link đăng nhập trong " f"{int(cho_giay)}s. "
                          "Thử chạy `grok login --device-auth` trong terminal của máy chủ.")}
    return {"ok": True, "xong": False, "url": _LOGIN["url"], "code": _LOGIN["code"]}


def login_trang_thai() -> dict:
    """Vòng đăng nhập đang tới đâu. Giao diện gọi lặp lại cái này sau `login_start`."""
    proc = _LOGIN.get("proc")
    d = auth_status()
    dang_chay = bool(proc and proc.poll() is None)
    return {"connected": bool(d.get("connected")), "dang_cho": dang_chay,
            "url": _LOGIN.get("url", ""), "code": _LOGIN.get("code", ""),
            "account": d.get("account", ""), "plan": d.get("plan", ""),
            "error": "" if (d.get("connected") or dang_chay) else d.get("error", "")}


def logout_huy_tien_trinh() -> None:
    proc = _LOGIN.get("proc")
    if proc and proc.poll() is None:
        try:
            proc.kill()
        except Exception:
            pass
    _LOGIN.update(proc=None, url="", code="", loi="", bat_dau=0.0)


def logout() -> dict:
    """`grok logout` - xoá phiên CLI đang giữ.

    Khác `agy` (không có nút Ngắt vì token nằm trong keyring không đụng được): ở đây CLI có
    lệnh đăng xuất chính chủ, nên nút Ngắt làm đúng việc nó hứa.
    """
    logout_huy_tien_trinh()
    cli = find_grok_cli()
    if not cli:
        return {"ok": False, "error": "Chưa cài Grok CLI."}
    try:
        r = subprocess.run([cli, "logout"], capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=30, creationflags=_no_window(),
                           env=_moi_truong())
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}
    if r.returncode != 0:
        return {"ok": False, "error": ((r.stderr or r.stdout or "").strip()[:300]
                                       or f"Thoát mã {r.returncode}")}
    return {"ok": True}


def list_models() -> Optional[list]:
    """Danh sách model cho picker.

    Hỏi CLI trước (nếu bản này có lệnh liệt kê), rồi mới tới bảng dự phòng cộng model đang đặt
    mặc định trong `~/.grok/config.toml` - máy được cấp bản preview riêng vẫn thấy đúng tên
    mình đang dùng.
    """
    cli = find_grok_cli()
    if not cli:
        return None
    ids: list = []
    if co_co("models"):
        try:
            r = subprocess.run([cli, "models", "--json"], capture_output=True, text=True,
                               encoding="utf-8", errors="replace", timeout=20,
                               creationflags=_no_window(), env=_moi_truong())
            if r.returncode == 0:
                d = json.loads((r.stdout or "").strip() or "[]")
                if isinstance(d, dict):
                    d = d.get("models") or d.get("data") or []
                for m in d if isinstance(d, list) else []:
                    mid = m.get("id") or m.get("name") if isinstance(m, dict) else m
                    if isinstance(mid, str) and mid.strip() and mid not in ids:
                        ids.append(mid.strip())
        except Exception:
            pass                          # không hỏi được thì rơi xuống bảng dự phòng
    if not ids:
        ids = list(MODELS_DU_PHONG)
    cfg = _doc_toml(_grok_home() / "config.toml")
    ten = str(((cfg.get("models") or {}) or {}).get("default") or "").strip()
    if ten and ten not in ids:
        ids.insert(0, ten)
    return ids


# ---------------------------------------------------------------------------
class GrokCLI:
    """Một lượt chạy `grok` headless. Cùng hợp đồng sự kiện với ClaudeSDK/CodexCLI/GeminiCLI.

    query() sinh dict {"type": "tool_call"|"tool_result"|"final"|"error"|"usage", ...} để mọi
    nơi gọi (chat dashboard, Telegram, việc nền) không phải biết đây là engine nào.
    """

    def __init__(self, cwd: Optional[str] = None, tag: str = "chat", model: Optional[str] = None,
                 instructions: Optional[str] = None):
        self.cli_path = find_grok_cli()
        self.cwd = cwd or os.getcwd()
        self.tag = tag
        self.model = model
        self.instructions = instructions
        self.session_id = None          # có giá trị → `--resume <id>`; không thì mở mạch mới
        self.mode = "full"
        self.max_turns = 0              # 0 = để CLI tự quản, như mọi engine CLI khác
        self.extra_args: list = []
        # Trần wall-clock cho MỘT lượt. Đây không phải phòng xa: `permission_cho_mode()` fail-
        # closed, nên trên một bản CLI không khai `--permission-mode` nó không truyền cờ nào -
        # và headless mà CLI dừng lại hỏi duyệt là treo tới vô tận, im lặng, không một dòng ra
        # stdout để vòng readline thoát. Watchdog dưới đây là thứ duy nhất gỡ được ca đó.
        self.timeout = float(os.environ.get("JAVIS_GROK_TIMEOUT") or 900)

    def is_available(self) -> bool:
        return self.cli_path is not None

    def _build_args(self, prompt_file: Optional[str] = None,
                    prompt_argv: Optional[str] = None) -> list:
        args = [self.cli_path]
        if self.model and co_co("--model"):
            args += ["--model", self.model]
        args += permission_cho_mode(self.mode)
        if self.max_turns and co_co("--max-turns"):
            args += ["--max-turns", str(int(self.max_turns))]
        if co_co("--output-format"):
            args += ["--output-format", "streaming-json"]
        if co_co("--no-auto-update"):
            args.append("--no-auto-update")
        # Mạch cũ thì nối lại; mạch mới thì KHÔNG tự cấp id.
        #
        # `-s/--session-id` có tồn tại, nhưng tài liệu nói id Grok tự sinh là UUIDv7 còn Javis
        # chỉ có uuid4 - cấp một id sai dạng là lượt đầu thoát lỗi và hỏng câm. Để CLI tự sinh
        # rồi ĐỌC LẠI id từ dòng sự kiện thì đúng trong mọi trường hợp. Khác Gemini CLI ở chỗ
        # này, và khác có chủ ý.
        if self.session_id and co_co("--resume"):
            args += ["--resume", self.session_id]
        args += list(self.extra_args)
        # Prompt: ưu tiên FILE. System prompt của Javis kèm ngữ cảnh brain vượt trần dòng lệnh
        # 32767 ký tự của Windows dễ như chơi (đã đo 36.045 ký tự trên một brain TRỐNG - xem
        # khối chú thích trong antigravity_cli.py), nên argv chỉ là đường lùi.
        if prompt_file and co_co("--prompt-file"):
            args += ["--prompt-file", prompt_file]
        else:
            args += ["-p", prompt_argv if prompt_argv is not None else ""]
        return args

    async def query(self, prompt: str) -> AsyncIterator[dict]:
        if not self.cli_path:
            yield {"type": "error",
                   "content": f"Không tìm thấy Grok CLI. Cài bằng `{lenh_cai()}` rồi chạy "
                              "`grok login` một lần để đăng nhập."}
            return
        # Grok không nhận system prompt riêng ở chế độ headless → gộp vào đầu prompt, đúng cách
        # CodexCLI và GeminiCLI đang làm.
        full = (self.instructions.strip() + "\n\n" + prompt) if self.instructions else prompt
        tep = None
        try:
            fd, tep = tempfile.mkstemp(prefix="javis-grok-", suffix=".txt")
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(full)
        except Exception:
            tep = None
        args = self._build_args(prompt_file=tep, prompt_argv=full)
        loop = asyncio.get_running_loop()
        hang: asyncio.Queue = asyncio.Queue()
        HET = object()

        qua_gio = threading.Event()

        def doc_luong():
            proc = None
            canh = None
            try:
                proc = subprocess.Popen(
                    args, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE, cwd=self.cwd, text=True, encoding="utf-8",
                    errors="replace", bufsize=1, creationflags=_no_window(),
                    env=_moi_truong(), start_new_session=(os.name != "nt"),
                )

                def cat():
                    """Giết tiến trình khi quá giờ, để vòng readline dưới kia thoát ra được.

                    `proc.wait(timeout=...)` KHÔNG cứu được ca này: nó chỉ chặn ở bước chờ
                    thoát, còn lúc CLI treo im không in gì thì luồng đang đứng trong
                    `readline()` chứ chưa tới đó.
                    """
                    if proc.poll() is None:
                        qua_gio.set()
                        try:
                            proc.kill()
                        except Exception:
                            pass

                canh = threading.Timer(self.timeout, cat)
                canh.daemon = True
                canh.start()
                for line in iter(proc.stdout.readline, ""):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        loop.call_soon_threadsafe(hang.put_nowait, json.loads(line))
                    except json.JSONDecodeError:
                        # Không phải JSON: bản CLI cũ chưa có streaming-json, hoặc một dòng
                        # cảnh báo lọt ra stdout. Giữ nguyên làm chữ thay vì vứt đi im lặng.
                        loop.call_soon_threadsafe(hang.put_nowait, {"_raw": line})
                err = ""
                try:
                    err = (proc.stderr.read() or "").strip()
                except Exception:
                    pass
                ma = proc.wait()
                if qua_gio.is_set():
                    loop.call_soon_threadsafe(
                        hang.put_nowait,
                        {"_exit": -1, "_err": f"Grok CLI chạy quá {int(self.timeout)}s nên bị "
                                              f"cắt. Nếu việc thật sự dài thì nâng biến môi "
                                              f"trường JAVIS_GROK_TIMEOUT."})
                elif ma != 0:
                    loop.call_soon_threadsafe(hang.put_nowait, {"_exit": ma, "_err": err})
                elif err:
                    # Thoát 0 mà stderr có chữ KHÔNG phải lỗi. Tài liệu chính chủ nói rõ: ở
                    # chế độ headless log đi ra stderr, và ai đặt `RUST_LOG` trong môi trường
                    # là mỗi lượt lại có vài dòng. Coi đó là lỗi thì lượt nào cũng đỏ trong khi
                    # câu trả lời vẫn về đủ. Giữ lại ở nhật ký máy chủ để còn lần ra khi cần.
                    print(f"[grok stderr] {err[:2000]}", file=sys.stderr)
            except Exception as e:
                loop.call_soon_threadsafe(hang.put_nowait,
                                          {"_exit": -1, "_err": f"{type(e).__name__}: {e}"})
            finally:
                if canh:
                    canh.cancel()
                try:
                    if proc and proc.poll() is None:
                        proc.terminate()
                except Exception:
                    pass
                # Dọn file prompt ở ĐÂY chứ không ở vòng đọc sự kiện: luồng này luôn chạy hết,
                # kể cả khi người dùng đóng tab giữa chừng và không ai đọc nốt hàng đợi nữa.
                # Để sót là rác tích dần trong thư mục tạm. (Bài học của antigravity_cli.)
                if tep:
                    try:
                        os.unlink(tep)
                    except Exception:
                        pass
                loop.call_soon_threadsafe(hang.put_nowait, HET)

        threading.Thread(target=doc_luong, name=f"javis-grok-{self.tag}", daemon=True).start()

        cac_manh: list = []
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
            yield {"type": "error",
                   "content": "Grok CLI chạy xong nhưng không trả về nội dung nào."}

    # -- dịch sự kiện -------------------------------------------------------
    @staticmethod
    def _lay(ev: dict, *ten, mac_dinh=""):
        """Lấy giá trị đầu tiên tìm thấy trong vài tên khoá hợp lý.

        Tên trường của `streaming-json` chưa được tài liệu hoá tới mức từng khoá, và đây là bản
        CLI mới đổi liên tục. Dò vài tên là chấp nhận được ở đây vì cái giá của việc đoán sai
        rất khác nhau: sai tên khoá tool thì mất một nhãn hiển thị, còn nuốt mất chữ trả lời
        thì người dùng thấy "không có nội dung trả về" trơ trọi.
        """
        for k in ten:
            v = ev.get(k)
            if v not in (None, ""):
                return v
        return mac_dinh

    def _doi_su_kien(self, ev: dict, cac_manh: list) -> list:
        """Một dòng NDJSON của Grok -> 0..n sự kiện theo hợp đồng của Javis."""
        if "_raw" in ev:
            cac_manh.append(str(ev["_raw"]))
            return []
        if "_exit" in ev:
            loi = str(ev.get("_err") or "").strip()
            if ev.get("_exit") == 0 and not loi:
                return []
            l = loi.lower()
            if "xai_api_key" in l or "not authenticated" in l or "unauthorized" in l:
                return [{"type": "error",
                         "content": "Grok CLI chưa đăng nhập. Mở trang Models bấm \"Đăng nhập\", "
                                    "hoặc chạy `grok login --device-auth` trong terminal."}]
            if not loi:
                loi = f"Grok CLI thoát với mã {ev.get('_exit')}."
            return [{"type": "error", "content": loi[:1500]}]

        t = str(ev.get("type") or "")
        # Id phiên có thể đi kèm nhiều loại sự kiện; nhặt ở đâu thấy cũng được, vì lượt sau chỉ
        # cần đúng một id để `--resume`.
        sid = str(self._lay(ev, "sessionId", "session_id") or "").strip()
        if not sid:
            meta = ev.get("metadata")
            if isinstance(meta, dict):
                sid = str(meta.get("sessionId") or meta.get("session_id") or "").strip()
        if sid:
            self.session_id = sid

        if t == "text":
            cac_manh.append(str(self._lay(ev, "text", "content", "delta")))
            return []
        if t == "thought":
            return []          # lập luận nội bộ, KHÔNG phải câu trả lời - không gộp vào final
        if t == "tool_call":
            return [{"type": "tool_call",
                     "name": str(self._lay(ev, "name", "tool_name", "tool")),
                     "id": str(self._lay(ev, "id", "tool_call_id", "toolCallId")),
                     "input": self._lay(ev, "input", "parameters", "arguments", mac_dinh={})}]
        if t == "tool_call_update":
            tt = str(self._lay(ev, "status", "state"))
            if tt not in ("completed", "success", "failed", "error"):
                return []      # tiến độ chạy dở, không phải kết quả
            return [{"type": "tool_result",
                     "id": str(self._lay(ev, "id", "tool_call_id", "toolCallId")),
                     "status": tt,
                     "content": str(self._lay(ev, "output", "result", "content"))[:2000]}]
        if t == "usage":
            return [self._usage(ev)]
        if t == "end":
            ra: list = []
            u = ev.get("usage")
            if isinstance(u, dict):
                ra.append(self._usage(u))
            ly_do = str(self._lay(ev, "stopReason", "stop_reason"))
            if ly_do in ("error", "max_turns"):
                tin = str(self._lay(ev, "error", "message"))
                ra.append({"type": "error",
                           "content": tin or f"Grok CLI kết thúc sớm ({ly_do})."})
            return ra
        if t == "error":
            tin = str(self._lay(ev, "message", "error", "content"))
            return [{"type": "error", "content": tin or "Grok CLI lỗi."}]
        return []

    @staticmethod
    def _usage(u: dict) -> dict:
        vao = int(u.get("input") or u.get("input_tokens") or u.get("inputTokens") or 0)
        ra = int(u.get("output") or u.get("output_tokens") or u.get("outputTokens") or 0)
        cache = int(u.get("cache_read") or u.get("cacheRead") or u.get("cached") or 0)
        return {"type": "usage", "input_tokens": vao, "output_tokens": ra,
                "total_tokens": int(u.get("total") or u.get("total_tokens") or (vao + ra)),
                "cached": cache}


# ---------------------------------------------------------------------------
def kiem_tra_nhanh(timeout: float = 30.0) -> dict:
    """Chạy thử một lượt cực ngắn để biết CLI + đăng nhập có THẬT SỰ dùng được không.

    Trang Models cần một câu trả lời DỨT KHOÁT chứ không phải suy đoán từ file: token hết hạn
    mà refresh hỏng thì `auth.json` vẫn nằm đó nguyên vẹn. Đây đúng là chỗ Gemini CLI đã gãy
    khi Google ngắt hạng cá nhân, và Grok Build cũng gắn quyền dùng vào GÓI chứ không vào
    binary - nên câu hỏi "chat được chưa" chỉ trả lời được bằng cách chat thật một lượt.
    """
    cli = find_grok_cli()
    if not cli:
        return {"ok": False, "error": f"Chưa cài Grok CLI ({lenh_cai()})."}
    args = [cli]
    args += permission_cho_mode("suggest")
    if co_co("--output-format"):
        args += ["--output-format", "json"]
    if co_co("--no-auto-update"):
        args.append("--no-auto-update")
    args += ["-p", "Trả lời đúng một chữ: ok"]
    try:
        r = subprocess.run(args, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=timeout, creationflags=_no_window(),
                           env=_moi_truong(), cwd=str(Path.home()))
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "Grok CLI không trả lời kịp."}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}
    if r.returncode != 0:
        loi = (r.stderr or r.stdout or "").strip()
        l = loi.lower()
        if "xai_api_key" in l or "not authenticated" in l or "unauthorized" in l:
            loi = ("Chưa đăng nhập. Bấm \"Đăng nhập\" trên thẻ này, hoặc chạy "
                   "`grok login --device-auth`.")
        elif "subscription" in l or "not eligible" in l or "forbidden" in l:
            loi = ("Tài khoản đăng nhập không có quyền dùng Grok Build. Nó đi kèm gói SuperGrok "
                   "hoặc X Premium+, không phải cứ có API key là chạy được.")
        return {"ok": False, "error": loi[:400] or f"Thoát mã {r.returncode}"}
    try:
        d = json.loads((r.stdout or "").strip() or "{}")
    except json.JSONDecodeError:
        return {"ok": True, "reply": (r.stdout or "").strip()[:200]}
    return {"ok": True, "reply": str(d.get("text") or d.get("response") or "")[:200]}
