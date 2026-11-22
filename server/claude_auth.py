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
        out["days_left"] = int((exp - now) // 86400)
        out["expired"] = exp <= now
    return out


def env_cho_cli(settings: dict = None) -> dict:
    """Biến môi trường thêm cho tiến trình `claude`. {} = để CLI tự dùng phiên đăng nhập sẵn.

    Chỉ trả key khi người dùng ĐÃ chọn `api_key` VÀ đã dán key. Chọn `api_key` mà bỏ trống ô
    key thì trả {} - tức lui về phiên đăng nhập sẵn có, chứ không làm chết mọi lượt chat bằng
    một biến môi trường rỗng. Same for `token` (2026-11-22): the token goes down as
    CLAUDE_CODE_OAUTH_TOKEN, which the CLI reads before its own login; no token saved = the login.
    """
    s = settings if settings is not None else cfgmod.read_settings()
    mode = che_do(s)
    if mode == TOKEN:
        tok = oauth_token(s)
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
