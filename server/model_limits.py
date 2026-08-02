"""model_limits.py - Bộ hạn mức GỢI Ý theo provider/model, để khai quota profile cho canary.

Vì sao module này tồn tại: cả adaptive runtime dựng ra để cứu model bị siết TPM, nhưng nó
fail-closed khi không biết hạn mức - `quota_profiles` mặc định rỗng nên mọi task rơi về
legacy. Nghĩa là cỗ máy cứu Groq, khi gặp đúng Groq, không làm gì cả vì không ai bảo nó
Groq bị giới hạn bao nhiêu. Trước module này, cách duy nhất để khai là gõ tay JSON lồng ba
tầng vào settings.json.

RANH GIỚI RÕ RÀNG, đọc trước khi thêm mục:

- Đây là GỢI Ý, không phải sự thật. Hạn mức thật phụ thuộc gói cước của TỪNG tài khoản và
  nhà cung cấp đổi lúc nào cũng được. Mọi mục đều mang `verify: True` và giao diện phải nói
  rõ là con số cần đối chiếu, không được trình bày như thể đã biết chắc.
- KHÔNG hardcode vào `_DEFAULT` của config. Thiết kế cố ý bắt người vận hành khai một cách
  có ý thức; module này chỉ rút ngắn thao tác khai, không khai hộ.
- Thà THIẾU còn hơn SAI. Không có mục cho provider nào thì trả rỗng, người vận hành tự
  điền. Một con số bịa cao hơn thực tế còn tệ hơn không có số, vì nó làm admission cho qua
  đúng cái request lẽ ra phải chặn.

Hình dạng mỗi mục phải khớp thứ `CanaryPolicy.from_settings` đọc được (xem
`fast_path_runtime.QuotaRule`). Sai một tên trường là rule bị bỏ qua trong IM LẶNG và
`quota_profiles` tuy có phần tử vẫn sinh ra 0 rule. Có test khoá chuyện đó.
"""
from __future__ import annotations

import fnmatch

# Nguồn: tài liệu hạn mức công khai của từng nhà cung cấp, ghi lại kèm ngày tra để lần sau
# còn biết con số cũ tới mức nào.
#
# reserved_output_tokens: chỗ chừa cho câu trả lời. Đặt rộng tay vì tính thiếu thì request
# vượt hạn mức đúng lúc model trả lời dài, mà đó lại là lúc khó tái hiện nhất.
KNOWN_LIMITS: tuple[dict, ...] = (
    {
        "id": "groq-free-llama-3.3-70b",
        "provider": "groq",
        "model_pattern": "llama-3.3-70b*",
        "rolling_tpm": 12000,
        "context_window": 131072,
        "reserved_output_tokens": 2000,
        "window_seconds": 60,
        "note": "Groq gói on_demand miễn phí. Chính hạn mức đã chặn Javis ở 21.446 token.",
        "source": "Tài liệu rate limit công khai của Groq, tra ngày 2026-08-02",
        "verify": True,
    },
    {
        "id": "groq-free-qwen3-32b",
        "provider": "groq",
        "model_pattern": "qwen3-32b*",
        "rolling_tpm": 6000,
        "context_window": 131072,
        "reserved_output_tokens": 2000,
        "window_seconds": 60,
        "note": "Model nhỏ hơn KHÔNG có nghĩa hạn mức rộng hơn - TPM và cửa sổ ngữ cảnh là "
                "hai giới hạn khác nhau.",
        "source": "Tài liệu rate limit công khai của Groq, tra ngày 2026-08-02",
        "verify": True,
    },
    {
        "id": "groq-free-gpt-oss-120b",
        "provider": "groq",
        "model_pattern": "*gpt-oss-120b*",
        "rolling_tpm": 8000,
        "context_window": 131072,
        "reserved_output_tokens": 2000,
        "window_seconds": 60,
        "source": "Tài liệu rate limit công khai của Groq, tra ngày 2026-08-02",
        "verify": True,
    },
)


def suggest_profiles(provider: str, model: str = "") -> list[dict]:
    """Các mục gợi ý khớp provider (và model nếu có nêu). Rỗng nghĩa là chưa biết.

    Rỗng KHÔNG phải lỗi: nó có nghĩa là người vận hành phải tự khai, và đó là trạng thái
    đúng cho mọi provider chưa được tra hạn mức."""
    prov = (provider or "").strip().lower()
    if not prov:
        return []
    out = []
    for item in KNOWN_LIMITS:
        if item["provider"] != prov:
            continue
        if model and not fnmatch.fnmatch(str(model).strip().lower(),
                                         item["model_pattern"].lower()):
            continue
        out.append(dict(item))
    return out


def as_quota_profile(item: dict) -> dict:
    """Rút mục gợi ý về đúng các trường `CanaryPolicy.from_settings` đọc.

    Bỏ `note`/`source`/`verify` vì chúng là ghi chú cho người, không phải cấu hình. Giữ lại
    thì chúng đi thẳng vào settings.json và lần sau ai đọc sẽ tưởng là trường có ý nghĩa."""
    return {
        "id": item["id"],
        "provider": item["provider"],
        "model_pattern": item["model_pattern"],
        "rolling_tpm": int(item["rolling_tpm"]),
        "context_window": int(item["context_window"]),
        "reserved_output_tokens": int(item["reserved_output_tokens"]),
        "window_seconds": int(item.get("window_seconds") or 60),
    }


def known_providers() -> list[str]:
    return sorted({item["provider"] for item in KNOWN_LIMITS})
