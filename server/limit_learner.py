"""limit_learner.py - Học hạn mức token TỪ CHÍNH LỖI nhà cung cấp trả về.

Vì sao module này tồn tại, và vì sao thiết kế cũ sai:

Bản trước bắt người vận hành KHAI TRƯỚC hạn mức của từng model rồi mới bảo vệ được. Nghĩa
là Javis chỉ đỡ được nhà cung cấp nào đã có người ngồi tra tài liệu và điền số. Cắm model
mới, hoặc nhà cung cấp đổi hạn mức, là lại thủng.

Nhưng chính câu báo lỗi đã chứa sự thật chính xác nhất:

    Request too large for model llama-3.3-70b-versatile ... on tokens per minute (TPM):
    Limit 12000, Requested 15447, please reduce your message size and try again.

Đó là hạn mức THẬT của tài khoản đó, tại thời điểm đó, do chính nhà cung cấp nói ra - đáng
tin hơn mọi con số tra từ tài liệu. Vứt nó đi rồi bắt người dùng tự khai là làm ngược.

Module này làm ba việc:
  1. Nhận diện lỗi "vượt hạn mức" của NHIỀU nhà cung cấp, không riêng ai.
  2. Rút ra con số hạn mức và con số đã yêu cầu.
  3. Nhớ lại, để lần sau chặn TRƯỚC khi gửi thay vì lại ăn một lỗi nữa.

Ranh giới: chỉ nhận diện lỗi NÓI RÕ là vượt kích thước/hạn mức. Lỗi quá tải tạm thời
(overloaded, 503) KHÔNG thuộc đây - chúng cần chờ rồi thử lại, không cần co nhỏ prompt.
Nhận nhầm hai loại này là co prompt vô ích trong khi vấn đề nằm ở phía nhà cung cấp.
"""
from __future__ import annotations

import re
import threading
import time
from dataclasses import dataclass

# Hạn mức học được sống bao lâu trước khi coi là cũ. Nhà cung cấp đổi gói, nâng tier, hoặc
# hạn mức khác nhau theo giờ - giữ vĩnh viễn là tự khoá mình vào một con số đã lỗi thời.
LEARNED_TTL_SECONDS = 24 * 3600


@dataclass(frozen=True)
class LimitFact:
    """Một lần nhà cung cấp nói thẳng ra hạn mức của mình."""
    kind: str        # "tpm" (token mỗi phút) | "context" (cửa sổ ngữ cảnh)
    limit: int       # hạn mức nhà cung cấp nêu
    requested: int   # số nhà cung cấp nói là ta vừa xin
    source: str      # mẫu nào khớp, để còn lần lại khi nhận diện sai
    # Đã tiêu bao nhiêu trong cửa sổ. 0 = nhà cung cấp không nói.
    used: int = 0
    # Nhà cung cấp bảo chờ bao nhiêu giây. 0 = không nói.
    retry_after: float = 0.0

    @property
    def window_full(self) -> bool:
        """Cửa sổ đã đầy vì các lượt TRƯỚC, không phải vì lượt này quá to.

        Phân biệt này quyết định hành động: lượt này quá to thì phải CO NHỎ, còn cửa sổ đầy
        thì co nhỏ gần như vô ích - phải CHỜ cho cửa sổ trượt qua. Nhầm hai cái này là cắt
        ngữ cảnh của người dùng để giải một bài toán mà cắt không giải được."""
        return self.used > 0 and self.requested > 0 and self.requested <= self.limit


# Mỗi mẫu: (tên, kind, regex có 2 nhóm số theo thứ tự limit, requested).
# Viết riêng từng nhà cung cấp thay vì một regex tham lam: một regex "bắt mọi số gần chữ
# limit" sẽ đọc nhầm số tiền, số giây, số phiên bản - và đọc nhầm hạn mức thì tệ hơn không
# đọc, vì nó làm Javis tự bóp mình xuống một con số bịa.
_PATTERNS: tuple[tuple[str, str, re.Pattern], ...] = (
    # Groq có HAI dạng, và chúng đòi hai cách xử lý khác hẳn nhau:
    #   413 "Request too large ... Limit 12000, Requested 15447"      -> lượt này quá to
    #   429 "Rate limit reached ... Limit 12000, Used 8812, Requested 4701" -> cửa sổ đã đầy
    # Mẫu cũ đòi "Requested" đứng NGAY sau "Limit" nên dạng có "Used" chen vào không khớp,
    # và lỗi 429 rơi thẳng ra màn hình. Đây đúng là lỗi chủ repo gặp sau khi đã vá dạng 413.
    ("groq_tpm_used", "tpm", re.compile(
        r"tokens?\s+per\s+minute[^:]*:\s*Limit\s+(\d+)\s*,\s*Used\s+(\d+)\s*,"
        r"\s*Requested\s+(\d+)", re.I)),
    ("groq_tpm", "tpm", re.compile(
        r"tokens?\s+per\s+minute[^:]*:\s*Limit\s+(\d+)\s*,\s*Requested\s+(\d+)", re.I)),
    # OpenAI: "maximum context length is 8192 tokens, however you requested 9000 tokens"
    ("openai_context", "context", re.compile(
        r"maximum\s+context\s+length\s+is\s+(\d+)\s+tokens?.{0,40}?requested\s+(\d+)", re.I | re.S)),
    # OpenAI rate limit: "Limit 30000, Requested 31000"
    ("openai_tpm", "tpm", re.compile(
        r"rate\s+limit[^.]{0,80}?Limit\s+(\d+)[^0-9]{1,20}Requested\s+(\d+)", re.I | re.S)),
    # Anthropic: "prompt is too long: 210000 tokens > 200000 maximum"  (thứ tự NGƯỢC)
    ("anthropic_context", "context", re.compile(
        r"prompt\s+is\s+too\s+long:\s*(\d+)\s+tokens?\s*>\s*(\d+)\s+maximum", re.I)),
    # Gemini / chung: "input token count (12345) exceeds the maximum ... (8192)"  (thứ tự NGƯỢC)
    ("gemini_context", "context", re.compile(
        r"input\s+token\s+count\s*\((\d+)\)\s*exceeds[^()]{0,60}\((\d+)\)", re.I)),
)

# Mẫu có thứ tự (requested, limit) thay vì (limit, requested). Tách ra thành dữ liệu thay vì
# nhớ trong đầu, vì đọc ngược hai số này là học đúng cái hạn mức sai.
_REVERSED = frozenset({"anthropic_context", "gemini_context"})

# Dấu hiệu "vượt kích thước" nói chung, để còn nhận ra lỗi mà không rút được số.
_SIZE_ERROR_HINTS = (
    "request too large", "too many tokens", "maximum context length",
    "prompt is too long", "reduce your message size", "context_length_exceeded",
    "input token count", "exceeds the maximum", "rate limit reached",
)


_RETRY_AFTER_RE = re.compile(r"try\s+again\s+in\s+([0-9]+(?:\.[0-9]+)?)\s*(ms|s|m)?\b", re.I)


def parse_retry_after(body: str) -> float:
    """Số giây nhà cung cấp bảo chờ. 0 nếu không nói.

    Con số này quý hơn mọi backoff tự đoán: nó là thời điểm cửa sổ trượt qua, do chính bên
    đếm nói ra."""
    m = _RETRY_AFTER_RE.search(str(body or ""))
    if not m:
        return 0.0
    try:
        value = float(m.group(1))
    except (TypeError, ValueError):
        return 0.0
    unit = (m.group(2) or "s").lower()
    if unit == "ms":
        value /= 1000.0
    elif unit == "m":
        value *= 60.0
    return max(0.0, min(value, 300.0))   # trần 5 phút: chờ lâu hơn thì báo còn hơn treo


def parse_limit_error(status_code: int, body: str) -> LimitFact | None:
    """Rút hạn mức từ body lỗi. None nghĩa là đây KHÔNG phải lỗi vượt kích thước.

    Không dựa vào status code để quyết định, vì mỗi nhà cung cấp trả một mã khác nhau cho
    cùng một chuyện: Groq trả 413, OpenAI trả 400, chỗ khác trả 429. Bằng chứng đáng tin là
    NỘI DUNG câu báo lỗi.
    """
    text = str(body or "")
    if not text:
        return None
    for name, kind, pattern in _PATTERNS:
        m = pattern.search(text)
        if not m:
            continue
        try:
            groups = [int(g) for g in m.groups()]
        except (TypeError, ValueError):
            continue
        used = 0
        if len(groups) >= 3:
            limit, used, requested = groups[0], groups[1], groups[2]
        else:
            a, b = groups[0], groups[1]
            limit, requested = (b, a) if name in _REVERSED else (a, b)
        if limit <= 0:
            continue
        return LimitFact(kind=kind, limit=limit, requested=max(0, requested), source=name,
                         used=max(0, used), retry_after=parse_retry_after(text))
    # Nhận ra là lỗi kích thước nhưng không rút được số: vẫn đáng báo, vì nó nói cho tầng
    # trên biết "co prompt lại rồi thử lại" thay vì "chờ rồi thử lại".
    low = text.casefold()
    if any(h in low for h in _SIZE_ERROR_HINTS):
        return LimitFact(kind="context", limit=0, requested=0, source="unparsed_size_error")
    return None


_lock = threading.Lock()
_learned: dict[tuple[str, str], tuple[LimitFact, float]] = {}


def _key(provider: str, model: str) -> tuple[str, str]:
    return (str(provider or "?").strip().casefold(), str(model or "?").strip())


def remember(provider: str, model: str, fact: LimitFact, now: float | None = None) -> None:
    """Nhớ hạn mức nhà cung cấp vừa nói. Bỏ qua fact không có con số."""
    if not fact or fact.limit <= 0:
        return
    ts = time.time() if now is None else float(now)
    with _lock:
        _learned[_key(provider, model)] = (fact, ts)


def learned(provider: str, model: str, now: float | None = None) -> LimitFact | None:
    """Hạn mức đã học, hoặc None nếu chưa học hoặc đã quá hạn."""
    ts = time.time() if now is None else float(now)
    with _lock:
        row = _learned.get(_key(provider, model))
    if not row:
        return None
    fact, at = row
    if ts - at > LEARNED_TTL_SECONDS:
        return None
    return fact


def snapshot(now: float | None = None) -> dict:
    """Cho trang Chẩn đoán: hạn mức nào đã tự học được, học lúc nào."""
    ts = time.time() if now is None else float(now)
    out = {}
    with _lock:
        rows = list(_learned.items())
    for (provider, model), (fact, at) in rows:
        if ts - at > LEARNED_TTL_SECONDS:
            continue
        out[f"{provider}|{model}"] = {
            "kind": fact.kind, "limit": fact.limit,
            "requested_khi_hoc": fact.requested,
            "hoc_cach_day_giay": int(ts - at),
        }
    return out


def shrink_target(fact: LimitFact, safety: float = 0.75) -> int:
    """Số token nên nhắm tới cho lần thử lại. 0 nghĩa là không biết, đừng đoán.

    Nhắm THẤP hơn hạn mức khá nhiều vì hai lý do: hạn mức TPM là cửa sổ trượt nên phần vừa
    gửi hỏng vẫn còn nằm trong cửa sổ đó, và bộ đếm token của ta chỉ là ước lượng."""
    if not fact or fact.limit <= 0:
        return 0
    return max(256, int(fact.limit * max(0.1, min(float(safety), 0.95))))


def reset() -> None:
    """Chỉ dùng trong test."""
    with _lock:
        _learned.clear()
