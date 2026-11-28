"""Gói Claude Code xác thực bằng gì, và nói cho người dùng biết rủi ro của lựa chọn đó.

Vì sao có module này
--------------------
Trước 0.26.17, Javis TỰ ĐỌC access token OAuth mà Claude Code lưu trong
`~/.claude/.credentials.json` rồi gửi thẳng `Authorization: Bearer <token>` tới
`api.anthropic.com/v1/messages`. Anthropic cấm đúng việc đó: token của gói Free/Pro/Max chỉ
được dùng trong Claude Code và Claude.ai, và họ chặn hẳn các harness bên thứ ba từ 04/04/2026.
Cách phát hiện của họ dựa vào dấu vân tay request (thiếu telemetry/heartbeat mà CLI chính chủ
mới phát) - mà request Javis tự dựng thì không có gì trong số đó. Đường ấy đã được gỡ.

Nay Javis KHÔNG bao giờ đọc token của ai. Nó chạy binary `claude` (qua claude-agent-sdk) và
để chính sản phẩm của Anthropic lo phần đăng nhập. Còn lại đúng hai lựa chọn, người dùng tự
chọn ở trang Models, và CẢ HAI giữ nguyên vẹn năng lực (Bash, WebFetch, MCP, nối phiên cũ):

- `subscription`: dùng phiên đăng nhập sẵn có của Claude Code, tức gói Pro/Max đang trả.
  Không tốn thêm tiền. Hợp với "ordinary, individual usage" theo tài liệu của Anthropic:
  một người, máy cá nhân, ngồi gõ. Chạy nền 24/7 trên VPS hay nhiều người dùng chung một
  tài khoản thì KHÔNG thuộc phạm vi đó - xem CANH_BAO_SUBSCRIPTION.
- `api_key`: đưa `anthropic_api_key` xuống cho binary `claude` qua biến môi trường. Trả tiền
  theo lượt dùng qua Claude Console. Đây là đường Anthropic chỉ định cho sản phẩm bên thứ ba.
- `token` (2026-11-22): the same plan, signed in with a long-lived (1-year) token made by
  `claude setup-token`, handed to `claude` as CLAUDE_CODE_OAUTH_TOKEN. Owner's report that day: the
  plan's sign-in "reached its time limit and cannot be renewed" and every bot and job stopped. A
  setup-token is Anthropic's own answer for unattended runs (Claude Code names it in that very error).
  Javis still never reads the CLI's login: the owner gives this token to Javis on purpose.

Javis cố ý KHÔNG tắt cứng đường subscription: chủ máy được quyền tự cân rủi ro. Việc của
module này là bảo đảm họ cân nó khi đã BIẾT, chứ không phải vì không ai nói.
"""
from __future__ import annotations

import json
import math
import os
from pathlib import Path

import config as cfgmod

SUBSCRIPTION = "subscription"
API_KEY = "api_key"
TOKEN = "token"
MODES = (SUBSCRIPTION, TOKEN, API_KEY)

# A token from `claude setup-token` lives one year (the CLI says so when it makes one). Javis cannot read the date out of
# the token, so it counts from the day the token was saved.
TOKEN_DAYS = 365
TOKEN_ENV = "CLAUDE_CODE_OAUTH_TOKEN"
_TOKEN_PREFIX = "sk-ant-oat01-"

# Nguyên văn dán ở trang Models và trả kèm khi đặt việc nền chạy bằng gói subscription.
# Đừng rút gọn: người đọc cần đủ ba thứ - phạm vi gói, cái gì có thể làm mình giống bot, và lối ra.
# 0.352.0 (chủ repo): giọng nhẹ nhàng, nói đúng mức rủi ro. Có nguy cơ, nhưng Javis chưa ghi nhận
# trường hợp nào bị khoá; gặp thì báo nhà phát triển để mọi người cùng biết.
CANH_BAO_SUBSCRIPTION = (
    "Gói Claude Pro/Ultra được Anthropic tính cho việc dùng cá nhân thông thường của Claude Code. "
    "Chạy nền liên tục (loop, nhắc hẹn, việc Kanban, chatbot), chạy trên VPS, hoặc nhiều người "
    "dùng chung một tài khoản nằm ngoài phạm vi đó nên có nguy cơ bị khoá tài khoản, dù tới nay "
    "Javis chưa ghi nhận trường hợp nào. Nếu bạn gặp, hãy báo cho nhà phát triển qua mục Issues "
    "trên GitHub của Javis. Muốn chạy nền yên tâm hơn thì đổi sang API key ở trang Models, hoặc "
    "trỏ 'model việc nền' sang một provider khác."
)

CANH_BAO_SUBSCRIPTION_EN = (
    "Anthropic counts a Claude Pro/Ultra plan for ordinary personal use of Claude Code. "
    "Continuous background runs (loops, reminders, Kanban work, chatbots), running on a VPS, "
    "or several people sharing one account fall outside that, so there is a risk of the account "
    "being locked, although Javis has no reported case so far. If it happens to you, please tell "
    "the developer through Issues on Javis's GitHub. For more peace of mind, switch to an API key "
    "on the Models page, or point the 'background model' at another provider."
)

# Câu ngắn cho chỗ chật (badge, tooltip, dòng trạng thái).
CANH_BAO_NGAN = ("Chạy nền bằng gói subscription có nguy cơ bị khoá tài khoản, dù Javis chưa ghi nhận "
                 "trường hợp nào. Dùng API key cho việc nền là yên tâm nhất.")
CANH_BAO_NGAN_EN = ("Running background work on a subscription plan carries a risk of the account being "
                    "locked, though Javis has no reported case so far. An API key is the safest choice.")


def che_do(settings: dict = None) -> str:
    """`subscription` (mặc định), `token` hoặc `api_key`. Giá trị lạ trong file cấu hình về mặc định."""
    s = settings if settings is not None else cfgmod.read_settings()
    v = str(((s.get("model") or {}).get("claude_auth") or "")).strip().lower()
    return v if v in MODES else SUBSCRIPTION


def api_key(settings: dict = None) -> str:
    s = settings if settings is not None else cfgmod.read_settings()
    return str(((s.get("model") or {}).get("anthropic_api_key") or "")).strip()


def oauth_token(settings: dict = None) -> str:
    """The long-lived token saved on the Models page, "" when there is none."""
    s = settings if settings is not None else cfgmod.read_settings()
    return str(((s.get("model") or {}).get("claude_oauth_token") or "")).strip()


def clean_token(raw) -> str:
    """A pasted token without the spaces and line breaks a copy from a terminal brings along."""
    return "".join(str(raw or "").split())


def valid_token(tok) -> bool:
    """Whether `tok` looks like a token from `claude setup-token` (an API key or a login code does not)."""
    t = clean_token(tok)
    return t.startswith(_TOKEN_PREFIX) and len(t) >= len(_TOKEN_PREFIX) + 20 and t.replace("-", "").replace("_", "").isalnum()


def token_info(settings: dict = None, now: float = None) -> dict:
    """What the Models card shows about the saved token, never the token itself: set, last 4 characters, when it was
    saved, when it runs out, days left."""
    import time
    s = settings if settings is not None else cfgmod.read_settings()
    tok = oauth_token(s)
    if not tok:
        return {"set": False}
    try:
        at = float((s.get("model") or {}).get("claude_oauth_token_at") or 0)
    except (TypeError, ValueError):
        at = 0.0
    now = time.time() if now is None else now
    out = {"set": True, "tail": tok[-4:], "saved_at": int(at) if at else 0}
    if at:
        exp = at + TOKEN_DAYS * 86400
        out["expires_at"] = int(exp)
        out["days_left"] = token_days_left(exp, now)
        out["expired"] = exp <= now
    return out


def token_days_left(expires_at: float, now: float) -> int:
    """Days left, rounded up: a token saved a minute ago has 365 days left, not 364, and its last hours count as one."""
    return max(0, math.ceil((float(expires_at) - float(now)) / 86400))


# ---- claude.ai connectors next to the long-lived token (2026-11-26) ----
# Owner's report that day: after the switch to the token, Javis on Claude Code no longer saw the connectors added on
# claude.ai (Google Calendar, Gmail, Drive...). Claude Code itself decides that: a token handed in as
# CLAUDE_CODE_OAUTH_TOKEN counts as scope `user:inference` only, and the CLI loads claude.ai connectors only for a
# login that holds `user:mcp_servers` (a full `claude auth login`). No setting gives a setup-token that scope.
#
# So in token mode the machine's own login goes first WHEN it carries that scope, and the token stays as the backup:
# the turn that finds the login gone marks it (`note_login_failed`) and every turn after runs on the token, until the
# login file changes (a new sign-in), which lifts the mark by itself. Only the file's `scopes`, `expiresAt` and whether
# a refresh token is there are read, never a token, the same boundary as connect_health and claude_token_gate.
# macOS keeps the login in the Keychain (no file): there the token runs as before.
CONNECTOR_SCOPE = "user:mcp_servers"
_LOGIN_DEAD = {"sig": None, "at": 0.0, "claimed": False}
CLAIM_S = 60.0


def login_file() -> Path:
    """The CLI's login file for account 1 (its own config folder when CLAUDE_CONFIG_DIR is set for the server)."""
    base = os.environ.get("CLAUDE_CONFIG_DIR") or ""
    if base:
        return Path(base) / ".credentials.json"
    home = os.environ.get("HOME") or os.path.expanduser("~")
    return Path(home) / ".claude" / ".credentials.json"


def _login_sig():
    """(file stat, expiresAt) of the login file, None when there is none. Changes whenever the CLI writes a new login."""
    p = login_file()
    try:
        st = p.stat()
        oa = (json.loads(p.read_text(encoding="utf-8")) or {}).get("claudeAiOauth") or {}
        return (st.st_mtime_ns, st.st_size, oa.get("expiresAt"))
    except (OSError, ValueError, TypeError, AttributeError):
        return None


def login_connectors() -> bool:
    """Whether the machine's own Claude Code login can load claude.ai connectors: it has a refresh token and the
    `user:mcp_servers` scope. False on a Mac (Keychain, no file) and with no login at all."""
    try:
        oa = (json.loads(login_file().read_text(encoding="utf-8")) or {}).get("claudeAiOauth") or {}
    except (OSError, ValueError, TypeError, AttributeError):
        return False
    scopes = oa.get("scopes") or []
    return bool(oa.get("refreshToken")) and isinstance(scopes, list) and CONNECTOR_SCOPE in scopes


def login_dead() -> bool:
    """Whether a turn found this very login gone. A new login (the file changes) lifts the mark."""
    sig = _LOGIN_DEAD.get("sig")
    if sig is None:
        return False
    if _login_sig() != sig:
        _LOGIN_DEAD.update(sig=None, at=0.0, claimed=False)
        return False
    return True


def login_first(settings: dict = None) -> bool:
    """Token mode with a token saved, and the login next to it can carry claude.ai connectors and is not known dead:
    turns run on the login and the token waits as the backup."""
    s = settings if settings is not None else cfgmod.read_settings()
    return che_do(s) == TOKEN and bool(oauth_token(s)) and login_connectors() and not login_dead()


def note_login_failed(now: float = None, claim: bool = True) -> bool:
    """A turn on account 1 was refused for a lost sign-in. When that turn ran on the login with the token as backup,
    the login is marked and the token takes the next turns: True. False when the token itself was refused (or there
    is no token), so the caller marks the card as before.

    Two places hear the same refusal: the engine's own end-of-turn check (connect_health, every Claude turn, chat or
    background, `claim=False`) and the router (`claim=True`), which reruns the turn on the token. The router's call
    takes over a mark the engine set moments before, once; a second refusal (now on the token) is not taken over."""
    import time
    now = time.time() if now is None else now
    if login_first():
        _LOGIN_DEAD.update(sig=_login_sig(), at=now, claimed=claim)
        return True
    if claim and login_dead() and not _LOGIN_DEAD.get("claimed") \
            and 0 <= now - float(_LOGIN_DEAD.get("at") or 0) <= CLAIM_S:
        _LOGIN_DEAD["claimed"] = True
        return True
    return False


def token_took_over(now: float = None, within: float = 120.0) -> bool:
    """Whether the token took over from a dead login in the last `within` seconds: the failed turn may run again at
    once on the same card, now on the token."""
    import time
    at = float(_LOGIN_DEAD.get("at") or 0)
    now = time.time() if now is None else now
    return bool(at) and 0 <= now - at <= within and login_dead()


# ---- Connect Claude: the full sign-in first, the token second (owner, 2026-11-28) ----
# Owner that day: "keep both, but sign in fully first and get the token after". The full login is what the turns run
# on (connectors), so it comes first; the claude.ai page is then already signed in, and the token step is one click on
# Authorize. One sign-in cannot give both: Anthropic issues a setup-token with `user:inference` only (above).
BACKUP_REMIND_AFTER_S = 15 * 60


def login_then_token(platform: str = None) -> bool:
    """Whether Connect Claude runs the full sign-in first and the token second. False on a Mac (the login lives in
    the Keychain, Javis cannot see its scopes, so the token is the one way in, as before) and where `setup-token`
    cannot run from the card (no pseudo-terminal: Windows, where the token is pasted)."""
    import sys
    if (sys.platform if platform is None else platform) == "darwin":
        return False
    try:
        import claude_setup_token
        return claude_setup_token.supported()
    except Exception:  # noqa: BLE001
        return False


def backup_missing(settings: dict = None) -> bool:
    """Turns run on the machine's own connector-capable login and no long-lived token stands behind it: the day the
    login runs out, bots and background work stop (the 2026-11-22 report). Read from the file, never a token."""
    s = settings if settings is not None else cfgmod.read_settings()
    if "ANTHROPIC_API_KEY" in env_cho_cli(s) or oauth_token(s):
        return False
    return login_connectors()


def login_age_s(now: float = None) -> float:
    """Seconds since the CLI last wrote its login file; -1 with no file."""
    import time
    try:
        return (time.time() if now is None else now) - login_file().stat().st_mtime
    except OSError:
        return -1.0


def backup_remind_key(now: float = None) -> str:
    """The bell's dedup key for one "no backup token" notice per sign-in, or "" when it is not due yet: the owner may
    still be on step 2 right after signing in, so it waits BACKUP_REMIND_AFTER_S. Only where the card has the button
    the notice names (login_then_token)."""
    age = login_age_s(now)
    if age < BACKUP_REMIND_AFTER_S or not backup_missing() or not login_then_token():
        return ""
    sig = _login_sig()
    return f"claude-no-backup:{sig[0] if sig else 0}"


def runs_on(settings: dict = None) -> str:
    """What account 1's turns run on right now: "login", "token" or "api_key"."""
    s = settings if settings is not None else cfgmod.read_settings()
    env = env_cho_cli(s)
    if "ANTHROPIC_API_KEY" in env:
        return "api_key"
    return "token" if TOKEN_ENV in env else "login"


def env_cho_cli(settings: dict = None) -> dict:
    """Biến môi trường thêm cho tiến trình `claude`. {} = để CLI tự dùng phiên đăng nhập sẵn.

    Chỉ trả key khi người dùng ĐÃ chọn `api_key` VÀ đã dán key. Chọn `api_key` mà bỏ trống ô
    key thì trả {} - tức lui về phiên đăng nhập sẵn có, chứ không làm chết mọi lượt chat bằng
    một biến môi trường rỗng. Same for `token` (2026-11-22): the token goes down as
    CLAUDE_CODE_OAUTH_TOKEN, which the CLI reads before its own login; no token saved = the login.
    2026-11-26: a login that carries claude.ai connectors goes first, the token is its backup (`login_first`).
    """
    s = settings if settings is not None else cfgmod.read_settings()
    mode = che_do(s)
    if mode == TOKEN:
        tok = oauth_token(s)
        if tok and login_first(s):
            return {}
        return {TOKEN_ENV: tok} if tok else {}
    if mode != API_KEY:
        return {}
    k = api_key(s)
    return {"ANTHROPIC_API_KEY": k} if k else {}


def on_plan(settings: dict = None) -> bool:
    """Whether Claude Code runs on the owner's plan (its login or a long-lived token) rather than an API key that
    bills per token. An API key mode with no key saved falls back to the login, so it counts as the plan."""
    return "ANTHROPIC_API_KEY" not in env_cho_cli(settings)


def canh_bao_neu_can(settings: dict = None) -> str:
    """Câu cảnh báo nếu máy đang để gói subscription gánh việc nền. "" = không cần cảnh báo."""
    s = settings if settings is not None else cfgmod.read_settings()
    if che_do(s) == API_KEY:
        return ""
    import aux_engine
    if not aux_engine.is_claude(aux_engine.read_spec(s)):
        return ""
    import localefmt
    return localefmt.chu(CANH_BAO_SUBSCRIPTION, CANH_BAO_SUBSCRIPTION_EN)
