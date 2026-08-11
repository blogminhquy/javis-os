"""Danh sách model Claude LIVE cho provider `anthropic-cli` (gói Claude Code).

Trước 0.26.17 file này MƯỢN access token OAuth mà Claude Code lưu trong
`~/.claude/.credentials.json` (hoặc Keychain macOS) để hỏi `api.anthropic.com/v1/models`.
Anthropic cấm đúng việc đó - token của gói Free/Pro/Max chỉ được dùng trong Claude Code và
Claude.ai - nên đường ấy đã gỡ hẳn: không còn hàm nào đọc credential của người dùng.

Nay chỉ còn MỘT nguồn hợp lệ cho danh sách live: `anthropic_api_key` trong cấu hình. Không có
key thì trả None và caller giữ nguyên catalog trong config.py. Catalog đó là bốn alias
(opus/sonnet/haiku/fable) mà chính CLI hiểu, và alias luôn trỏ tới bản mới nhất của từng
dòng - nên máy không có API key vẫn chọn được model mới, chỉ là không thấy tên đầy đủ.
"""
MODELS_URL = "https://api.anthropic.com/v1/models"


def aliases(ids):
    """Alias 'luôn bản mới nhất' mà CLI nhận (opus, sonnet, haiku, fable...).

    Suy ra từ chính danh sách live - dòng model mới xuất hiện là tự có alias, khỏi sửa code.
    """
    out = []
    for i in ids:
        parts = (i or "").split("-")
        if len(parts) < 3 or parts[0] != "claude":
            continue
        fam = parts[1]
        if fam.isalpha() and fam not in out:
            out.append(fam)
    return out


async def fetch_models(api_key=""):
    """Danh sách model id (alias đứng trước, rồi tên đầy đủ). None = không lấy được.

    None là đường bình thường chứ không phải lỗi: phần đông người dùng chạy bằng gói
    subscription và không có API key. Caller giữ catalog cũ, picker vẫn đủ dùng.
    """
    import httpx
    key = (api_key or "").strip()
    if not key:
        return None
    headers = {"x-api-key": key, "anthropic-version": "2023-06-01"}
    async with httpx.AsyncClient(timeout=20) as c:
        r = await c.get(MODELS_URL, params={"limit": 100}, headers=headers)
        r.raise_for_status()
        data = r.json().get("data", [])
    ids = [x.get("id") for x in data if x.get("id")]
    return (aliases(ids) + ids) or None
