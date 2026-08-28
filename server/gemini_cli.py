"""Bộ não thứ 9: Google Gemini CLI, chạy bằng ĐĂNG NHẬP GOOGLE (không cần mua API key).

Đối xứng với `CodexCLI` trong claude_cli.py: Javis không đọc token của ai cả, nó gọi đúng
binary `gemini` của máy và mượn phiên đăng nhập mà chính CLI đó giữ. Cùng một cách đã dùng cho
Claude Code và Codex.

**Vì sao là Gemini CLI chứ không phải nối thẳng vào Antigravity** (rà trên máy chủ repo
2026-08-12): Antigravity là app Electron thuần, trong `Resources/bin` chỉ có `language_server`
và `webm_encoder`, không có cổng dòng lệnh nào để gọi headless. Soi `language_server` thì nó
đi accounts.google.com → cloudcode-pa.googleapis.com + aiplatform.googleapis.com - tức là
CÙNG backend Code Assist mà Gemini CLI dùng cho gói "đăng nhập bằng tài khoản Google". Token
của Antigravity lại nằm trong Keychain qua safeStorage của Electron, không có đường lấy ra
bền vững, và cloudcode-pa là API nội bộ không cam kết hỗ trợ bên thứ ba. Nên đi qua CLI chính
chủ: cùng gói miễn phí đó, nhưng bằng interface Google công khai.

Bốn thứ lấy được từ chính CLI đã cài (đo trên gemini-cli 0.55.1) thay vì đoán:

- `-o stream-json` phát JSONL: `init` (có session_id + model), `message` (role user/assistant,
  `delta: true` khi chảy từng mảnh), `tool_use`, `tool_result`, `error` (severity), `result`
  (status + `stats` có token). Ánh xạ thẳng sang hợp đồng sự kiện của Javis.
- `--approval-mode` có đúng bốn nấc `default|auto_edit|yolo|plan`, khớp gọn ba mức quyền của
  Javis: suggest → `plan` (CHỈ ĐỌC thật, không phải lời hứa), auto → `auto_edit`, full → `yolo`.
- Phiên: `--session-id <uuid>` MỞ MỚI (đã tồn tại là CLI thoát lỗi), `--resume <uuid>` nối lại.
  Nên đúng khuôn "lượt đầu mở, lượt sau nối" của CodexCLI.
- MCP: đọc `mcpServers` trong `.gemini/settings.json` của THƯ MỤC LÀM VIỆC, entry HTTP dùng
  khoá `httpUrl` + `headers`. Ghi vào brain là mỗi brain một hub riêng, không đụng nhau.
"""
from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import AsyncIterator, Optional

from claude_cli import _home_dir, _no_window, tim_binary

# Model của CLI (hằng số trong chính bundle gemini-cli 0.55.1). Đây là DỰ PHÒNG khi chưa lấy
# được danh sách live - `auto-*` để CLI tự chọn theo hạn mức còn lại của tài khoản.
MODELS_MAC_DINH = [
    "gemini-3-pro-preview",
    "gemini-3-flash-preview",
    "gemini-2.5-pro",
    "gemini-2.5-flash",
    "gemini-3.1-flash-lite",
    "auto-gemini-3",
]
MODEL_MAC_DINH = "gemini-2.5-pro"

# mức quyền Javis -> --approval-mode của Gemini CLI
_APPROVAL = {"suggest": "plan", "auto": "auto_edit", "full": "yolo"}

# ---------------------------------------------------------------------------
# Google đã NGẮT Gemini CLI với tài khoản cá nhân (18/06/2026)
#
# Đây không phải lỗi cấu hình bên Javis và không patch được: Google chặn ở phía máy chủ. CLI
# trả về `IneligibleTierError` với `reasonCode: UNSUPPORTED_CLIENT` cho CẢ BA hạng cá nhân -
# free tier, Google AI Pro và Google AI Ultra. Chỉ còn hai đường sống: giấy phép Gemini Code
# Assist doanh nghiệp, hoặc chạy CLI bằng API key (GEMINI_API_KEY).
#
# Vì vậy lời hứa cũ của thẻ này - "dùng gói đăng nhập tài khoản Google, không cần mua API key"
# - nay SAI. Không dịch câu lỗi thì người dùng chỉ thấy "không có nội dung trả về" rồi ngồi
# thử lại mãi, nên bắt đúng nó và nói thẳng chuyện gì đã xảy ra.
LOI_HET_CUA = (
    "Google đã ngắt Gemini CLI với tài khoản cá nhân từ 18/06/2026 (cả gói miễn phí, "
    "Google AI Pro lẫn Ultra). Đây là chặn từ phía Google, đăng nhập lại hay đổi model đều "
    "không cứu được.\n\n"
    "Ba đường đi tiếp, chọn một:\n"
    "- **OpenRouter** - gần nhất với trình chọn model của Antigravity: nhiều model một chỗ, "
    "có cả Gemini lẫn Claude, chỉ cần một API key.\n"
    "- **Google Gemini (API)** - vẫn đúng model Gemini, lấy key ở aistudio.google.com, "
    "trả tiền theo lượt gọi.\n"
    "- **Antigravity CLI** - bản thay thế chính chủ của Google (binary `agy`), dùng đúng gói "
    "Google bạn đang có.\n"
    "- **Grok Build CLI** - nếu bạn có gói SuperGrok hoặc X Premium+, đây là đường dùng gói "
    "sẵn có và đăng nhập được ngay trên trang Models."
)


def _la_loi_het_cua(loi: str) -> bool:
    """Câu lỗi của CLI có phải chuyện Google ngắt hạng cá nhân không.

    Bắt bằng NHIỀU dấu hiệu vì Google đã đổi câu chữ một lần: `IneligibleTierError` là tên
    lớp lỗi, `UNSUPPORTED_CLIENT` là mã lý do trong `ineligibleTiers`, còn câu "no longer
    supported" là phần người đọc thấy.
    """
    l = (loi or "").lower()
    return ("ineligibletiererror" in l or "unsupported_client" in l
            or "no longer supported for gemini code assist" in l)


def approval_cho_mode(mode: Optional[str]) -> str:
    """Mức quyền của Javis -> nấc duyệt của Gemini CLI. Giá trị lạ về nấc CHẶT NHẤT.

    Fail-closed cố ý: một chuỗi mode gõ sai không được phép biến thành toàn quyền ghi file.
    """
    return _APPROVAL.get(str(mode or "").strip().lower(), "plan")


def find_gemini_cli() -> Optional[str]:
    """Tìm binary `gemini`. Cửa thoát JAVIS_GEMINI_BIN cho máy cài chỗ lạ."""
    envp = (os.environ.get("JAVIS_GEMINI_BIN") or "").strip()
    if envp:
        try:
            if Path(envp).exists():
                return envp
        except Exception:
            pass
    # tim_binary đã soi cả /opt/homebrew/bin, nvm... - chỗ macOS hay giấu binary npm global.
    cli = tim_binary("gemini")
    if cli:
        return cli
    home = _home_dir()
    for p in (home / ".local" / "bin" / "gemini", home / ".npm-global" / "bin" / "gemini",
              Path(os.environ.get("APPDATA", "")) / "npm" / "gemini.cmd"):
        try:
            if p.exists():
                return str(p)
        except Exception:
            pass
    return None


def _gemini_home() -> Path:
    return _home_dir() / ".gemini"


def _doc_json(p: Path):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def auth_status() -> dict:
    """Đã đăng nhập Google cho Gemini CLI chưa: {connected, method, email, error}.

    ĐỌC FILE, không gọi CLI. Gọi `gemini` để hỏi trạng thái là mỗi lần mở trang Models lại đẻ
    một tiến trình Node vài trăm ms; mà thứ cần biết đều nằm sẵn trên đĩa:

    - `~/.gemini/oauth_creds.json` - CLI ghi ra sau khi đăng nhập Google (đường MIỄN PHÍ, cùng
      backend Code Assist mà Antigravity dùng).
    - `~/.gemini/settings.json` - `security.auth.selectedType` (bản mới) hoặc `selectedAuthType`
      (bản cũ). Giá trị: oauth-personal | gemini-api-key | vertex-ai | cloud-shell.
    - biến môi trường GEMINI_API_KEY / GOOGLE_GENAI_USE_VERTEXAI / GOOGLE_GENAI_USE_GCA - CLI
      chấp nhận cả ba, nên Javis cũng phải coi là đã cấu hình.
    """
    cli = find_gemini_cli()
    if not cli:
        return {"connected": False, "method": "", "email": "",
                "error": "Chưa cài Gemini CLI (npm i -g @google/gemini-cli)."}
    # Đăng nhập NGAY TRÊN DASHBOARD đứng trước mọi thứ khác: Javis giữ refresh token nên nó
    # biết chắc, còn mấy dấu hiệu dưới đây đều là suy từ file của CLI. Quan trọng hơn: bản CLI
    # mới NUỐT `oauth_creds.json` vào keychain rồi xoá file đi, nên soi file mà kết luận là
    # ngay sau lượt chat đầu tiên trang Models sẽ báo "chưa đăng nhập" dù mọi thứ đang chạy.
    try:
        import gemini_oauth
        if gemini_oauth.connected():
            return {"connected": True, "method": "oauth-personal (Javis)",
                    "email": gemini_oauth.email(), "error": ""}
    except Exception:
        pass
    home = _gemini_home()
    creds = _doc_json(home / "oauth_creds.json") or {}
    co_oauth = bool(creds.get("refresh_token") or creds.get("access_token"))
    st = _doc_json(home / "settings.json") or {}
    chon = (((st.get("security") or {}).get("auth") or {}).get("selectedType")
            or st.get("selectedAuthType") or "")
    email = ""
    acc = _doc_json(home / "google_accounts.json") or {}
    if isinstance(acc, dict):
        email = str(acc.get("active") or acc.get("email") or "")
    if co_oauth:
        return {"connected": True, "method": chon or "oauth-personal", "email": email, "error": ""}
    if (os.environ.get("GEMINI_API_KEY") or "").strip():
        return {"connected": True, "method": "gemini-api-key", "email": "", "error": ""}
    for bien in ("GOOGLE_GENAI_USE_VERTEXAI", "GOOGLE_GENAI_USE_GCA"):
        if (os.environ.get(bien) or "").strip().lower() in ("1", "true", "yes", "on"):
            return {"connected": True, "method": bien, "email": "", "error": ""}
    if chon and chon != "oauth-personal":
        return {"connected": True, "method": chon, "email": "", "error": ""}
    return {"connected": False, "method": "", "email": "",
            "error": "Đã cài Gemini CLI nhưng chưa đăng nhập. Bấm \"Đăng nhập Google\" ngay "
                     "trên thẻ này."}


def login_huong_dan() -> dict:
    """Đường đăng nhập DỰ PHÒNG, cho ai thích làm trong terminal.

    Đường chính nay là nút "Đăng nhập Google" trên trang Models (xem gemini_oauth.py): Javis
    tự chạy vòng OAuth rồi bắc cầu token sang kho của CLI. Vẫn giữ hướng dẫn này vì ai đã
    `gemini` sẵn trên máy thì không cần đăng nhập lại lần nữa.
    """
    return {
        "cai": "npm install -g @google/gemini-cli",
        "dang_nhap": "gemini",
        "ghi_chu": ("Cách khác: chạy `gemini` trong terminal rồi chọn \"Login with Google\". "
                    "Javis nhận ra cả tài khoản đăng nhập kiểu đó."),
    }


def list_models() -> Optional[list]:
    """Danh sách model cho picker.

    Gemini CLI không có lệnh liệt kê model, nên nguồn là hằng số của chính bản CLI đang cài,
    cộng model người dùng đã chọn trong settings (`model.name`) nếu nó lạ - máy được cấp bản
    preview riêng vẫn thấy đúng tên mình đang dùng.
    """
    if not find_gemini_cli():
        return None
    ids = list(MODELS_MAC_DINH)
    st = _doc_json(_gemini_home() / "settings.json") or {}
    ten = str((st.get("model") or {}).get("name") or "").strip()
    if ten and ten not in ids:
        ids.insert(0, ten)
    return ids


def phien_moi() -> str:
    """UUID cho một mạch hội thoại mới. Gemini CLI đòi đúng dạng UUID."""
    return str(uuid.uuid4())


# ---- MCP: ghi hub của Javis vào .gemini/settings.json của THƯ MỤC LÀM VIỆC ----
def ghi_mcp_settings(vault_root, hub: Optional[dict]) -> Optional[str]:
    """Ghi `<vault>/.gemini/settings.json` với đúng một entry MCP trỏ về hub Javis.

    Vì sao ghi vào brain chứ không vào `~/.gemini`: file HOME là của người dùng và dùng chung
    cho mọi thứ họ chạy bằng `gemini`; đè lên đó là Javis giẫm vào cấu hình cá nhân, và nhiều
    brain thì brain nọ đọc header brain kia. Gemini CLI đọc settings theo thư mục làm việc, mà
    Javis luôn chạy nó với cwd = gốc brain, nên đây vừa đúng chỗ vừa cô lập sẵn.

    `hub=None` (chưa bật hub) → GỠ entry javis nếu có, giữ nguyên phần còn lại của file.
    Trả đường dẫn file đã ghi, hoặc None nếu không ghi được.
    """
    try:
        root = Path(vault_root).expanduser()
        p = root / ".gemini" / "settings.json"
        cu = _doc_json(p) or {}
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
        return str(p)
    except Exception as e:
        print(f"[gemini mcp settings] {e}", file=sys.stderr)
        return None


class GeminiCLI:
    """Một lượt chạy `gemini` headless. Cùng hợp đồng sự kiện với ClaudeSDK/CodexCLI.

    query() sinh dict {"type": "tool_call"|"text"|"final"|"error"|"usage", ...} để mọi nơi gọi
    (chat dashboard, Telegram, việc nền) không phải biết đây là engine nào.
    """

    def __init__(self, cwd: Optional[str] = None, tag: str = "chat", model: Optional[str] = None,
                 instructions: Optional[str] = None):
        self.cli_path = find_gemini_cli()
        self.cwd = cwd or os.getcwd()
        self.tag = tag
        self.model = model
        self.instructions = instructions
        self.session_id = None          # có giá trị → `--resume <id>`; không thì mở mạch mới
        self._session_moi = None        # uuid vừa cấp cho lượt mở mạch, đọc lại sau khi chạy
        # Nấc duyệt. None = để CLI tự hỏi, mà headless thì hỏi là treo → luôn đặt tường minh.
        self.approval_mode = "yolo"
        self.extra_args: list[str] = []
        self.include_dirs: list[str] = []

    def is_available(self) -> bool:
        return self.cli_path is not None

    def _build_args(self) -> list[str]:
        args = [self.cli_path]
        if self.model:
            args += ["-m", self.model]
        args += ["--approval-mode", self.approval_mode]
        # --skip-trust: headless mà gặp hỏi "có tin thư mục này không" là treo im tới hết giờ.
        # Thư mục ở đây là brain do chính Javis dựng, không phải repo lạ tải về.
        args += ["--skip-trust", "-o", "stream-json"]
        if self.session_id:
            args += ["--resume", self.session_id]
        else:
            self._session_moi = phien_moi()
            args += ["--session-id", self._session_moi]
        for d in self.include_dirs:
            args += ["--include-directories", str(d)]
        args += list(self.extra_args)
        # Prompt bơm qua STDIN, KHÔNG qua argv: Windows chặn dòng lệnh ở 32767 ký tự và một
        # system prompt của Javis kèm ngữ cảnh brain vượt ngưỡng đó dễ như chơi.
        # `-p ""` bật chế độ headless; nội dung stdin được nối vào (xem --help: "Appended to
        # input on stdin (if any)").
        args += ["-p", ""]
        return args

    def _bac_cau_token(self):
        """Dựng lại `~/.gemini/oauth_creds.json` trước mỗi lượt, và làm mới token nếu sắp hết.

        Phải làm MỖI LƯỢT chứ không phải một lần lúc đăng nhập: bản CLI mới nạp file đó vào
        keychain rồi xoá đi, nên ghi một lần là lượt thứ hai đã không còn gì để đọc.
        """
        try:
            import gemini_oauth
            if gemini_oauth.connected():
                gemini_oauth.ghi_creds_cho_cli()
        except Exception:
            pass   # đăng nhập bằng terminal vẫn chạy bình thường, không được chặn lượt

    async def query(self, prompt: str) -> AsyncIterator[dict]:
        if not self.cli_path:
            yield {"type": "error",
                   "content": "Không tìm thấy Gemini CLI. Cài bằng `npm i -g @google/gemini-cli` "
                              "rồi chạy `gemini` một lần để đăng nhập Google."}
            return
        self._bac_cau_token()
        args = self._build_args()
        # Gemini CLI không nhận system prompt riêng ở chế độ headless → gộp vào đầu prompt,
        # đúng cách CodexCLI đang làm.
        full = (self.instructions.strip() + "\n\n" + prompt) if self.instructions else prompt
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
                        # Không phải JSON: bản CLI cũ chưa có stream-json, hoặc một dòng cảnh
                        # báo lọt ra stdout. Giữ nguyên làm chữ thay vì vứt đi im lặng.
                        loop.call_soon_threadsafe(hang.put_nowait, {"_raw": line})
                err = ""
                try:
                    err = (proc.stderr.read() or "").strip()
                except Exception:
                    pass
                ma = proc.wait()
                if ma != 0 or err:
                    loop.call_soon_threadsafe(hang.put_nowait, {"_exit": ma, "_err": err})
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

        threading.Thread(target=doc_luong, name=f"javis-gemini-{self.tag}", daemon=True).start()

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
            yield {"type": "error",
                   "content": "Gemini CLI chạy xong nhưng không trả về nội dung nào."}

    def _doi_su_kien(self, ev: dict, cac_manh: list) -> list:
        """Một dòng JSONL của Gemini CLI -> 0..n sự kiện theo hợp đồng của Javis."""
        if "_raw" in ev:
            cac_manh.append(str(ev["_raw"]))
            return []
        if "_exit" in ev:
            loi = str(ev.get("_err") or "").strip()
            if ev.get("_exit") == 0 and not loi:
                return []
            if _la_loi_het_cua(loi):
                return [{"type": "error", "content": LOI_HET_CUA}]
            # Chưa đăng nhập là ca thường nhất, và CLI báo bằng một câu dài loằng ngoằng về
            # biến môi trường. Dịch sang việc phải làm.
            if "set an Auth method" in loi or "GEMINI_API_KEY" in loi:
                return [{"type": "error",
                         "content": "Gemini CLI chưa đăng nhập. Mở terminal chạy `gemini`, chọn "
                                    "\"Login with Google\" rồi thử lại."}]
            if not loi:
                loi = f"Gemini CLI thoát với mã {ev.get('_exit')}."
            return [{"type": "error", "content": loi[:1500]}]
        t = str(ev.get("type") or "")
        if t == "init":
            sid = str(ev.get("session_id") or "").strip()
            if sid:
                self.session_id = sid       # nối mạch cho lượt sau
            return []
        if t == "message":
            if str(ev.get("role")) == "assistant":
                cac_manh.append(str(ev.get("content") or ""))
            return []
        if t == "tool_use":
            return [{"type": "tool_call", "name": str(ev.get("tool_name") or ""),
                     "id": str(ev.get("tool_id") or ""),
                     "input": ev.get("parameters") or {}}]
        if t == "tool_result":
            return [{"type": "tool_result", "id": str(ev.get("tool_id") or ""),
                     "status": str(ev.get("status") or ""),
                     "content": str(ev.get("output") or "")[:2000]}]
        if t == "error":
            tin = str(ev.get("message") or "")
            # Chuyện Google ngắt hạng cá nhân đi qua ĐÂY chứ không chỉ qua stderr, và CLI gắn
            # severity=warning cho nó ở vài bản - lọc theo severity trước là nuốt mất, người
            # dùng lại thấy "không có nội dung trả về" trơ trọi. Nên xét nó TRƯỚC.
            if _la_loi_het_cua(tin):
                return [{"type": "error", "content": LOI_HET_CUA}]
            # severity=warning KHÔNG phải lỗi lượt: CLI dùng nó cho mấy chuyện lặt vặt (thiếu
            # extension, quota gần hết). Đẩy lên thành error là lượt nào cũng đỏ.
            if str(ev.get("severity") or "error") == "warning":
                return []
            return [{"type": "error", "content": tin or "Gemini CLI lỗi."}]
        if t == "result":
            ra = []
            st = ev.get("stats") or {}
            if st:
                ra.append({"type": "usage",
                           "input_tokens": int(st.get("input_tokens") or 0),
                           "output_tokens": int(st.get("output_tokens") or 0),
                           "total_tokens": int(st.get("total_tokens") or 0),
                           "cached": int(st.get("cached") or 0)})
            if str(ev.get("status")) == "error":
                e = ev.get("error") or {}
                tin = str(e.get("message") or "")
                ra.append({"type": "error",
                           "content": LOI_HET_CUA if _la_loi_het_cua(tin)
                           else (tin or "Gemini CLI kết thúc với lỗi.")})
            return ra
        return []


def kiem_tra_nhanh(timeout: float = 20.0) -> dict:
    """Chạy thử một lượt cực ngắn để biết CLI + đăng nhập có thật sự dùng được không.

    Trang Models cần một câu trả lời DỨT KHOÁT chứ không phải suy đoán từ file: token hết hạn
    mà refresh hỏng thì `oauth_creds.json` vẫn nằm đó nguyên vẹn.
    """
    cli = find_gemini_cli()
    if not cli:
        return {"ok": False, "error": "Chưa cài Gemini CLI."}
    try:
        import gemini_oauth
        if gemini_oauth.connected():
            gemini_oauth.ghi_creds_cho_cli()
    except Exception:
        pass
    try:
        r = subprocess.run([cli, "--approval-mode", "plan", "--skip-trust", "-o", "json",
                            "-p", "Trả lời đúng một chữ: ok"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace",
                           timeout=timeout, creationflags=_no_window())
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "Gemini CLI không trả lời kịp."}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}
    if r.returncode != 0:
        loi = (r.stderr or r.stdout or "").strip()
        # Nút "Kiểm tra lại" là chỗ ĐẦU TIÊN người dùng bấm khi thấy chat không ra gì, nên nó
        # phải nói được chuyện Google ngắt hạng cá nhân - đừng để họ đọc nguyên cái stack
        # trace tiếng Anh rồi tưởng máy mình hỏng.
        if _la_loi_het_cua(loi):
            return {"ok": False, "het_cua": True, "error": LOI_HET_CUA}
        if "set an Auth method" in loi:
            loi = "Chưa đăng nhập. Chạy `gemini` rồi chọn \"Login with Google\"."
        return {"ok": False, "error": loi[:400] or f"Thoát mã {r.returncode}"}
    try:
        d = json.loads((r.stdout or "").strip() or "{}")
    except json.JSONDecodeError:
        return {"ok": True, "reply": (r.stdout or "").strip()[:200]}
    if d.get("error"):
        tin = str((d["error"] or {}).get("message") or "")
        if _la_loi_het_cua(tin):
            return {"ok": False, "het_cua": True, "error": LOI_HET_CUA}
        return {"ok": False, "error": tin[:400]}
    return {"ok": True, "reply": str(d.get("response") or "")[:200]}
