"""
Cấu hình tập trung của Javis OS - đọc/ghi server/settings.json (gitignored, chứa secret).
Gồm: workspace, tài khoản admin (mật khẩu hash), model engine, telegram.
Auth CHỈ bật khi đã đặt mật khẩu → bản local chưa đặt vẫn chạy như cũ.
"""
import json
import os
import hashlib
import secrets
from pathlib import Path

# Mọi state Javis tự ghi (settings, auth sessions, loop config) nằm ở JAVIS_STATE_DIR.
# Mặc định = server/ (không đổi trên máy cũ). Docker/VPS đặt = /data/state (volume ghi được,
# vì code tree /app là read-only trong container).
STATE_DIR = Path(os.getenv("JAVIS_STATE_DIR", str(Path(__file__).parent)))
try:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
except Exception:
    pass

SETTINGS_PATH = STATE_DIR / "settings.json"
# Logo/avatar tùy chỉnh (đổi qua UI) lưu ở đây - ghi được + giữ qua update (Docker volume),
# vì code tree dashboard/ là read-only trong container.
BRANDING_DIR = STATE_DIR / "branding"

_DEFAULT = {
    "workspace_name": "Javis OS",
    "setup_done": False,                       # đã qua bộ cài đặt lần đầu chưa
    "auth": {"username": "", "password_hash": "", "salt": ""},
    # Logo/avatar hiển thị (góc trên, thanh bên, màn đăng nhập). logo_ext rỗng = dùng ảnh mặc định.
    "branding": {"logo_ext": "", "logo_v": 0},
    # Tên miền riêng cho HTTPS tự động (Caddy On-Demand TLS hỏi /tls-check trước khi xin cert).
    "domain": {"custom": ""},
    # Nhà cung cấp giọng đọc (TTS). edge = Edge TTS miễn phí (mặc định, dự phòng).
    # openai = OpenAI TTS (dùng model.openai_api_key). elevenlabs = ElevenLabs (key riêng).
    "voice": {
        "tts_provider": "edge",                       # edge | openai | elevenlabs
        "openai_tts_voice": "alloy",                  # alloy|echo|fable|onyx|nova|shimmer|ash|sage|coral
        "openai_tts_model": "gpt-4o-mini-tts",        # hoặc tts-1 / tts-1-hd
        "elevenlabs_key": "",
        "elevenlabs_voice": "21m00Tcm4TlvDq8ikWAM",   # Rachel (premade, đa ngôn ngữ) - đổi được
        "elevenlabs_model": "eleven_multilingual_v2",
    },
    "model": {
        # --- Mô hình MAIN MODEL theo provider (mới) ---
        # Rỗng = suy ra từ legacy engine (config cũ không vỡ); UI set vào đây khi user đổi model.
        "main": {"provider": "", "model": ""},
        # Model phụ cho việc NỀN (loop/metrics/ingest) - alias Claude qua CLI. "" = dùng mặc định
        # (không đổi). Đặt model rẻ (vd haiku) để tiết kiệm khi chạy nền nhiều.
        "auxiliary": {"model": ""},
        # Độ sâu suy nghĩ (reasoning/thinking) khi trả lời chat: off | low | medium | high.
        # Anthropic API/OpenRouter → adaptive thinking + effort; OpenAI → reasoning_effort (chỉ o-series);
        # Claude Code CLI → chèn từ khoá think/ultrathink vào prompt. off = trả lời nhanh như cũ.
        "reasoning": "off",
        # --- Credentials theo provider ---
        "openrouter_key": "",
        "anthropic_api_key": "",               # provider Anthropic API (P2)
        "openai_api_key": "",                  # provider OpenAI (ChatGPT API)
        "gemini_api_key": "",                  # provider Google Gemini (endpoint OpenAI-compat)
        "groq_api_key": "",                    # provider Groq (endpoint OpenAI-compat, suy luận rất nhanh)
        # Provider 'openai-oauth' - đăng nhập ChatGPT Plus/Pro qua device-code (xem openai_oauth.py).
        "openai_oauth": {"access_token": "", "refresh_token": "", "id_token": "", "account_id": "", "plan": "", "expires_at": 0},
        # --- Legacy: giữ đồng bộ với main để engine cũ không vỡ (engine/claude_model/openrouter_model) ---
        "engine": "cli",                       # cli (Claude Code, đủ MCP) | openrouter | anthropic-api
        "claude_model": "",                    # "" = mặc định CLI; hoặc opus/sonnet/haiku/fable
        "openrouter_model": "openai/gpt-4o-mini",
        # Catalog model theo provider (Telegram /model dùng key 'claude'+'openrouter'; picker dùng cả 3).
        "catalog": {
            # anthropic-cli: chỉ là mồi lúc cài mới. /provider/models hỏi API Anthropic bằng token
            # OAuth của Claude Code rồi ghi đè danh sách THẬT vào đây (xem claude_models.py).
            "claude": ["opus", "sonnet", "haiku", "fable"],
            "anthropic-api": ["claude-opus-4-8", "claude-sonnet-4-6", "claude-haiku-4-5-20251001"],
            "openai": ["gpt-4o", "gpt-4o-mini", "o3-mini"],                        # OpenAI API
            "gemini": ["gemini-2.5-flash", "gemini-2.5-pro", "gemini-2.0-flash"],  # Google Gemini API (picker load động)
            "groq": ["llama-3.3-70b-versatile", "qwen3-32b", "openai/gpt-oss-120b"],  # Groq (picker load động)
            # Không ghim model Codex: /provider/models lấy catalog LIVE bằng
            # codex app-server model/list và nhớ lại lần thành công gần nhất.
            "openai-oauth": [],
            "openrouter": ["openai/gpt-4o-mini", "anthropic/claude-3.5-sonnet", "google/gemini-2.0-flash-001", "deepseek/deepseek-chat"],
        },
    },
    # Ảnh sinh bằng javis_generate_image.
    # strip_c2pa: gỡ Content Credentials (C2PA) - dấu nguồn gốc do nhà cung cấp ảnh nhúng sẵn
    # để nói "ảnh này do AI tạo". MẶC ĐỊNH TẮT: giữ nguyên dấu là hành vi an toàn, và bản fork
    # nào cũng bắt đầu ở trạng thái này. Bật lên là quyết định CÓ Ý THỨC của chủ workspace,
    # kèm trách nhiệm tự công bố nội dung AI theo luật/điều khoản nền tảng nơi họ đăng.
    "image": {"strip_c2pa": False},
    # Vùng cache media của brain: attachments/ + inbox/. Ảnh là NGUYÊN LIỆU đi qua, không
    # phải tri thức - đọc xong rút thành .md là đủ dùng, nên chúng tự hết hạn thay vì nằm
    # mãi làm phình đĩa VPS. Muốn giữ ảnh lâu dài thì đấu kho ngoài (Drive), đừng để Javis ôm.
    # max_age_days / max_mb <= 0 = tắt luật tương ứng. enabled=False = không dọn gì cả.
    # staging_days: hạn RIÊNG cho STATE_DIR/.staging - nơi file dán vào khung chat rơi xuống.
    # Ngắn hơn hẳn vì đó là chỗ trung chuyển một lượt chat, không ai mở lại bao giờ.
    "media": {"enabled": True, "max_age_days": 30, "max_mb": 300, "staging_days": 3},
    "telegram": {"enabled": False, "token": "", "chat_id": ""},
    # Backup brain lên GitHub (repo RIÊNG TƯ). token = GitHub PAT (fine-grained, quyền Contents).
    # Lưu trong settings.json (đã gitignored) - KHÔNG bao giờ đẩy lên brain repo.
    "backup": {"enabled": False, "repo_url": "", "token": "", "branch": "main",
               "interval_hours": 6, "last_backup": 0.0, "last_status": ""},
    "dashboard": {
        # graph_enabled=False → vào thẳng Console, KHÔNG dựng đồ thị (nhẹ cho VPS/điện thoại).
        # Frontend cũng tự ép lite-mode khi màn hình hẹp dù cờ này bật.
        "graph_enabled": True,
    },
    # MCP do Javis quản lý (registry connection ở mcp_servers.json). strict=True → CHỈ dùng
    # kết nối của Javis (--strict-mcp-config), bỏ qua config MCP sẵn có của máy.
    # hub=True (mặc định): mọi engine đấu qua MCP HUB (1 entry "javis" - đa tài khoản, quyền,
    # audit tại hub). Đặt false để về chế độ cũ (per-server) nếu gặp sự cố.
    # lazy_tools: chống phình context khi đấu nhiều connector. "auto" = tự bật khi số tool
    # MCP vượt lazy_threshold (mặc định); True/False = ép bật/tắt. Khi bật, hub chỉ phơi
    # 2 meta-tool javis_search_tools/javis_run_tool thay cho hàng trăm schema -> model tự
    # tìm tool theo NGỮ CẢNH rồi mới nạp. lazy_top_k = số tool search trả về mỗi lần.
    # ambient_hint: kèm connector đấu vào TÀI KHOẢN Claude (Drive/Gmail...) vào javis_connections
    # + lazy search cho engine Claude, để model biết chúng tồn tại (gọi qua tool native mcp__*).
    "mcp": {"strict": False, "hub": True, "lazy_tools": "auto", "lazy_threshold": 40,
            "lazy_top_k": 8, "ambient_hint": True},
}


# Các trường SECRET trong settings.json → mã hoá at rest (Fernet, qua secrets_store) như MCP secret.
# Backward-compat: giá trị plaintext cũ đọc vẫn ra nguyên văn; lần ghi kế tiếp tự bọc "enc:".
# Mất file .secret_key → decrypt trả "" (nhập lại key) - đánh đổi giống MCP secret, an toàn hơn lộ key.
_SECRET_PATHS = (
    "model.openrouter_key", "model.anthropic_api_key", "model.openai_api_key", "model.gemini_api_key",
    "model.groq_api_key",
    "model.openai_oauth.access_token", "model.openai_oauth.refresh_token", "model.openai_oauth.id_token",
    "telegram.token", "backup.token", "voice.elevenlabs_key",
)


def _transform_secret_fields(cfg, fn):
    """Áp fn (encrypt|decrypt) lên các trường secret theo _SECRET_PATHS, tại chỗ. Bỏ qua nếu thiếu."""
    for path in _SECRET_PATHS:
        parts = path.split(".")
        parent = cfg
        for p in parts[:-1]:
            if isinstance(parent, dict) and isinstance(parent.get(p), dict):
                parent = parent[p]
            else:
                parent = None
                break
        key = parts[-1]
        if isinstance(parent, dict) and isinstance(parent.get(key), str) and parent.get(key):
            parent[key] = fn(parent[key])
    return cfg


# Cache read_settings theo (mtime_ns, size) của settings.json: middleware auth/CSRF gọi
# gate_active() -> read_settings() TRÊN MỌI REQUEST, mỗi lần đọc file + giải mã Fernet ~5-8ms
# (x2 middleware = 10-16ms/request chỉ để check đăng nhập). File đổi (kể cả write_settings
# ghi đè) thì mtime/size đổi -> tự đọc lại. Trả deep copy để caller sửa thoải mái không bẩn cache.
_SETTINGS_CACHE = {"sig": None, "cfg": None}


def read_settings():
    try:
        st = SETTINGS_PATH.stat()
        sig = (st.st_mtime_ns, st.st_size)
    except OSError:
        sig = None
    if sig is not None and sig == _SETTINGS_CACHE["sig"] and _SETTINGS_CACHE["cfg"] is not None:
        return json.loads(_SETTINGS_CACHE["cfg"])
    cfg = json.loads(json.dumps(_DEFAULT))   # deep copy
    try:
        if SETTINGS_PATH.exists():
            data = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
            for k, v in (data or {}).items():
                if isinstance(v, dict) and isinstance(cfg.get(k), dict):
                    cfg[k].update(v)
                else:
                    cfg[k] = v
    except Exception:
        pass
    try:
        import secrets_store   # lazy: secrets_store import config → tránh vòng lặp import
        _transform_secret_fields(cfg, secrets_store.decrypt)
    except Exception as e:
        print(f"[config] giải mã secret lỗi: {e}", file=__import__('sys').stderr)
    if sig is not None:
        _SETTINGS_CACHE["sig"] = sig
        _SETTINGS_CACHE["cfg"] = json.dumps(cfg, ensure_ascii=False)
    return cfg


def write_settings(cfg):
    # Deep-copy rồi mã hoá BẢN SAO: caller vẫn giữ cfg plaintext để dùng tiếp (không bị hỏng).
    out = json.loads(json.dumps(cfg))
    try:
        import secrets_store
        _transform_secret_fields(out, secrets_store.encrypt)   # encrypt idempotent (bỏ qua enc:/plain:)
    except Exception as e:
        print(f"[config] mã hoá secret lỗi: {e}", file=__import__('sys').stderr)
    SETTINGS_PATH.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")


_TOOL_ENV_OWNED = False   # ELEVENLABS_API_KEY trong env hiện do apply_tool_env đặt → được phép gỡ khi user xoá key


def apply_tool_env(cfg=None):
    """Bơm secret dùng chung từ Cài đặt vào os.environ để TOOL NGOÀI thừa kế khi engine CLI
    (Claude Code/Codex) spawn tiến trình con (Bash -> python/node). Hiện có: key ElevenLabs
    (Cài đặt > Giọng đọc) -> ELEVENLABS_API_KEY cho video-use phiên âm khi cắt sửa video.
    Lưu ý phạm vi: đặt vào env của CẢ server nên mọi tiến trình con (MCP stdio, script vault...)
    đều thừa kế - chấp nhận vì mục đích chính là đến được Bash con của engine, và cùng user
    thì con nào cũng đọc được settings.json + .secret_key; blast radius chỉ là key TTS.
    Chỉ ghi đè khi settings có giá trị; user xoá key trong settings thì gỡ khỏi env (nhưng
    không đụng biến user tự đặt ngoài shell). Gọi lúc startup + sau khi lưu Cài đặt giọng đọc."""
    global _TOOL_ENV_OWNED
    try:
        if cfg is None:
            cfg = read_settings()
        k = ((cfg.get("voice") or {}).get("elevenlabs_key") or "").strip()
        if k and not k.startswith("••••"):   # bỏ qua giá trị che mà client lỡ gửi lại
            os.environ["ELEVENLABS_API_KEY"] = k
            _TOOL_ENV_OWNED = True
        elif not k and _TOOL_ENV_OWNED:
            os.environ.pop("ELEVENLABS_API_KEY", None)
            _TOOL_ENV_OWNED = False
    except Exception as e:
        print(f"[config] apply_tool_env lỗi: {e}", file=__import__('sys').stderr)
    # Windows: helper Python con (vd video-use) in Unicode ra console cp1252 sẽ crash
    # (UnicodeEncodeError) -> ép UTF-8 cho mọi tiến trình con. Tôn trọng giá trị user tự đặt.
    if os.name == "nt" and not os.environ.get("PYTHONUTF8"):
        os.environ["PYTHONUTF8"] = "1"


# ---- Mật khẩu ----
def hash_password(password, salt=None):
    salt = salt or secrets.token_hex(16)
    h = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 120_000).hex()
    return h, salt


def auth_enabled(cfg=None):
    cfg = cfg or read_settings()
    return bool(cfg.get("auth", {}).get("password_hash"))


def require_login():
    """Có BẮT BUỘC đăng nhập để dùng Javis không (kể cả khi CHƯA đặt mật khẩu → ép setup).
    - JAVIS_REQUIRE_LOGIN=1/0 ép bật/tắt tường minh.
    - Mặc định: BẬT khi server nghe public (JAVIS_HOST=0.0.0.0, vd Docker/Hostinger/VPS) -
      vì Claude chạy full quyền, không được để hở ai cũng vào được."""
    v = os.getenv("JAVIS_REQUIRE_LOGIN", "").strip().lower()
    if v in ("1", "true", "yes", "on"):
        return True
    if v in ("0", "false", "no", "off"):
        return False
    # FAIL-CLOSED: bind KHÔNG phải loopback (0.0.0.0, ::, IP LAN…) → coi là public → bắt buộc login.
    # Chỉ tắt khi nghe thuần localhost. (Localhost + tunnel: đặt JAVIS_REQUIRE_LOGIN=1.)
    host = os.getenv("JAVIS_HOST", "127.0.0.1").strip().lower()
    return host not in ("127.0.0.1", "localhost", "::1")


def gate_active():
    """Có cần kiểm tra session trước khi cho truy cập không (đã đặt mật khẩu HOẶC bắt buộc login)."""
    return auth_enabled() or require_login()


def verify_password(password, cfg=None):
    cfg = cfg or read_settings()
    a = cfg.get("auth", {})
    if not a.get("password_hash"):
        return False
    h, _ = hash_password(password, a.get("salt"))
    return secrets.compare_digest(h, a["password_hash"])


# ---- Session (lưu ra file → restart KHÔNG bị đăng xuất) ----
# Lưu {token: created_ts} để session CÓ HẠN (chống token bất tử nếu lỡ rò).
import time as _time
_SESS_PATH = STATE_DIR / ".sessions.json"
_SESSION_TTL = 30 * 86400   # 30 ngày


def _load_sessions():
    try:
        if _SESS_PATH.exists():
            data = json.loads(_SESS_PATH.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return {k: float(v) for k, v in data.items()}
            if isinstance(data, list):   # tương thích định dạng cũ → coi như vừa tạo
                return {k: _time.time() for k in data}
    except Exception:
        pass
    return {}


SESSIONS = _load_sessions()


def _save_sessions():
    try:
        _SESS_PATH.write_text(json.dumps(SESSIONS), encoding="utf-8")
    except Exception:
        pass


def new_session():
    t = secrets.token_urlsafe(32)
    SESSIONS[t] = _time.time()
    _save_sessions()
    return t


def valid_session(token):
    if not token or token not in SESSIONS:
        return False
    if _time.time() - SESSIONS.get(token, 0) > _SESSION_TTL:
        SESSIONS.pop(token, None)
        _save_sessions()
        return False
    return True


def drop_session(token):
    SESSIONS.pop(token, None)
    _save_sessions()


def clear_sessions():
    SESSIONS.clear()
    _save_sessions()


# ---- Setup token: chống CHIẾM ADMIN lần đầu trên public ----
# Khi chạy public mà CHƯA có admin, /auth/setup PHẢI kèm token này - token chỉ in ra LOG server
# lúc khởi động, nên chỉ chính chủ (xem được log/terminal) tạo được tài khoản. Kẻ chỉ-có-URL bó tay.
_SETUP_TOKEN_PATH = STATE_DIR / ".setup_token"


def setup_token_required():
    return require_login() and not auth_enabled()


def get_or_create_setup_token():
    """Đọc/sinh token thiết lập 1 lần. None nếu không cần (local, hoặc đã có admin)."""
    if not setup_token_required():
        return None
    try:
        if _SETUP_TOKEN_PATH.exists():
            t = _SETUP_TOKEN_PATH.read_text(encoding="utf-8").strip()
            if t:
                return t
        t = secrets.token_urlsafe(24)
        _SETUP_TOKEN_PATH.write_text(t + "\n", encoding="utf-8")  # xuống dòng → cat ra sạch, dễ copy
        return t
    except Exception:
        return None


def check_setup_token(provided):
    try:
        if not _SETUP_TOKEN_PATH.exists():
            return False
        real = _SETUP_TOKEN_PATH.read_text(encoding="utf-8").strip()
        return bool(real) and secrets.compare_digest(real, (provided or "").strip())
    except Exception:
        return False


def clear_setup_token():
    try:
        _SETUP_TOKEN_PATH.unlink()
    except Exception:
        pass


def provision_admin_from_env():
    """Có JAVIS_ADMIN_PASSWORD (+ tùy chọn JAVIS_ADMIN_USER) và CHƯA có admin → tạo admin lúc boot
    → đóng /auth/setup cho mọi người (cách an toàn nhất cho deploy public). Trả True nếu vừa tạo."""
    if auth_enabled():
        return False
    pw = os.getenv("JAVIS_ADMIN_PASSWORD", "")
    if not pw:
        return False
    user = (os.getenv("JAVIS_ADMIN_USER", "admin").strip() or "admin")
    h, salt = hash_password(pw)
    cfg = read_settings()
    cfg["auth"] = {"username": user, "password_hash": h, "salt": salt}
    write_settings(cfg)
    return True
