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

Javis cố ý KHÔNG tắt cứng đường subscription: chủ máy được quyền tự cân rủi ro. Việc của
module này là bảo đảm họ cân nó khi đã BIẾT, chứ không phải vì không ai nói.
"""
from __future__ import annotations

import config as cfgmod

SUBSCRIPTION = "subscription"
API_KEY = "api_key"

# Nguyên văn dán ở trang Models và trả kèm khi đặt việc nền chạy bằng gói subscription.
# Đừng rút gọn: người đọc cần đủ ba thứ - điều bị cấm, cái gì làm mình giống bot, và lối ra.
CANH_BAO_SUBSCRIPTION = (
    "Gói Claude Pro/Max chỉ được Anthropic tính cho việc dùng cá nhân thông thường của "
    "Claude Code. Chạy nền liên tục (loop, nhắc hẹn, việc Kanban, chatbot), chạy trên VPS, "
    "hoặc nhiều người dùng chung một tài khoản đều nằm NGOÀI phạm vi đó và đã có người bị "
    "khoá tài khoản vì lý do này. Muốn chạy nền yên tâm thì đổi sang API key ở trang Models, "
    "hoặc trỏ 'model việc nền' sang một provider khác."
)

# Câu ngắn cho chỗ chật (badge, tooltip, dòng trạng thái).
CANH_BAO_NGAN = ("Chạy nền bằng gói subscription có thể bị Anthropic khoá tài khoản. "
                 "Dùng API key cho việc nền là an toàn nhất.")


def che_do(settings: dict = None) -> str:
    """`subscription` (mặc định) hoặc `api_key`. Giá trị lạ trong file cấu hình về mặc định."""
    s = settings if settings is not None else cfgmod.read_settings()
    v = str(((s.get("model") or {}).get("claude_auth") or "")).strip().lower()
    return API_KEY if v == API_KEY else SUBSCRIPTION


def api_key(settings: dict = None) -> str:
    s = settings if settings is not None else cfgmod.read_settings()
    return str(((s.get("model") or {}).get("anthropic_api_key") or "")).strip()


def env_cho_cli(settings: dict = None) -> dict:
    """Biến môi trường thêm cho tiến trình `claude`. {} = để CLI tự dùng phiên đăng nhập sẵn.

    Chỉ trả key khi người dùng ĐÃ chọn `api_key` VÀ đã dán key. Chọn `api_key` mà bỏ trống ô
    key thì trả {} - tức lui về phiên đăng nhập sẵn có, chứ không làm chết mọi lượt chat bằng
    một biến môi trường rỗng.
    """
    s = settings if settings is not None else cfgmod.read_settings()
    if che_do(s) != API_KEY:
        return {}
    k = api_key(s)
    return {"ANTHROPIC_API_KEY": k} if k else {}


def canh_bao_neu_can(settings: dict = None) -> str:
    """Câu cảnh báo nếu máy đang để gói subscription gánh việc nền. "" = không cần cảnh báo."""
    s = settings if settings is not None else cfgmod.read_settings()
    if che_do(s) == API_KEY:
        return ""
    import aux_engine
    return CANH_BAO_SUBSCRIPTION if aux_engine.is_claude(aux_engine.read_spec(s)) else ""
