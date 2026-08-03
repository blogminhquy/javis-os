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
    # "tpm" token mỗi phút | "tpd" token mỗi ngày | "rpm" số lượt mỗi phút
    # "rpd" số lượt mỗi ngày | "context" cửa sổ ngữ cảnh | "rate" chặn nhịp không rõ chiều nào
    kind: str
    limit: int       # hạn mức nhà cung cấp nêu
    requested: int   # số nhà cung cấp nói là ta vừa xin
    source: str      # mẫu nào khớp, để còn lần lại khi nhận diện sai
    # Đã tiêu bao nhiêu trong cửa sổ. 0 = nhà cung cấp không nói.
    used: int = 0
    # Nhà cung cấp bảo chờ bao nhiêu giây. 0 = không nói.
    retry_after: float = 0.0
    # Nguyên văn (đã cắt) câu nhà cung cấp nói, để hiện lại khi ta không hiểu nó.
    raw: str = ""

    # Hạn mức ĐẾM TOKEN (để trang chẩn đoán nói đúng đơn vị).
    TOKEN_KINDS = ("tpm", "tpd", "context")
    # Hạn mức dùng được làm NGÂN SÁCH CHO MỘT REQUEST. Hẹp hơn TOKEN_KINDS một cách có chủ ý:
    #   - rpm/rpd đếm LƯỢT. Lấy "30 lượt mỗi phút" làm ngân sách là co prompt xuống 22 token.
    #   - tpd đếm token nhưng theo NGÀY. Lấy "100.000 token mỗi ngày" làm trần cho một
    #     request thì vừa quá rộng để bảo vệ được gì, vừa sai bản chất: hết hạn mức ngày thì
    #     request nhỏ cỡ nào cũng bị từ chối.
    BUDGET_KINDS = ("tpm", "context")

    @property
    def counts_tokens(self) -> bool:
        return self.kind in self.TOKEN_KINDS

    @property
    def usable_as_budget(self) -> bool:
        return self.kind in self.BUDGET_KINDS and self.limit > 0

    @property
    def window_full(self) -> bool:
        """Cửa sổ đã đầy vì các lượt TRƯỚC, không phải vì lượt này quá to.

        Phân biệt này quyết định hành động: lượt này quá to thì phải CO NHỎ, còn cửa sổ đầy
        thì co nhỏ gần như vô ích - phải CHỜ cho cửa sổ trượt qua. Nhầm hai cái này là cắt
        ngữ cảnh của người dùng để giải một bài toán mà cắt không giải được."""
        return self.used > 0 and self.requested > 0 and self.requested <= self.limit

    @property
    def remedy(self) -> str:
        """Việc ĐÚNG phải làm với lỗi này. Đây là thứ quyết định hành vi, không phải `kind`.

        Bốn giá trị:
          "shrink"    - lượt này quá to, co ngữ cảnh lại là qua.
          "wait"      - cửa sổ theo PHÚT đã đầy, chờ vài giây. Co nhỏ vô ích.
          "wait_long" - hết hạn mức theo NGÀY. Co nhỏ hoàn toàn vô ích, phải chờ sang ngày
                        hoặc đổi bộ não / nâng gói.
          "unknown"   - không đủ bằng chứng. Phải hiện nguyên văn lời nhà cung cấp.

        Vì sao tách khỏi kind: chủ repo gặp đúng ca này. Gói Groq siết BỐN thứ cùng lúc
        (token/phút, lượt/phút, token/ngày, lượt/ngày) và cả bốn đều mở đầu bằng "Rate limit
        reached", nên bản trước gộp hết vào một rọ "request quá lớn" rồi khuyên rút gọn yêu
        cầu - lời khuyên vô nghĩa với ba trong bốn loại.
        """
        if self.kind == "context":
            return "shrink"
        if self.kind == "tpm":
            return "wait" if self.window_full else "shrink"
        if self.kind in ("tpd", "rpd"):
            return "wait_long"
        if self.kind == "rpm":
            return "wait"
        if self.kind == "rate":
            return "wait" if self.retry_after > 0 else "unknown"
        return "unknown"


# Mỗi mẫu: (tên, kind, regex có 2 nhóm số theo thứ tự limit, requested).
# Viết riêng từng nhà cung cấp thay vì một regex tham lam: một regex "bắt mọi số gần chữ
# limit" sẽ đọc nhầm số tiền, số giây, số phiên bản - và đọc nhầm hạn mức thì tệ hơn không
# đọc, vì nó làm Javis tự bóp mình xuống một con số bịa.
# Groq (và vài endpoint OpenAI-compatible khác) dùng CHUNG một khuôn cho cả bốn chiều siết:
#
#   ... on tokens per minute (TPM): Limit 12000, Used 8812, Requested 4701. try again in 7.5s
#   ... on requests per minute (RPM): Limit 30, Used 30, Requested 1. ...
#   ... on tokens per day (TPD): Limit 100000, Used 100000, Requested 3200. ...
#   ... on requests per day (RPD): Limit 14400, Used 14400, Requested 1. ...
#
# Bản trước chỉ viết mẫu cho "tokens per minute", nên ba chiều kia rơi vào nhánh đoán mò
# "lỗi kích thước không rút được số" -> limit 0, requested 0 -> người dùng thấy câu
# "request quá lớn ... lượt này cần khoảng 0 token" rồi được khuyên rút gọn yêu cầu, trong
# khi rút gọn chẳng liên quan gì tới hết lượt-mỗi-ngày. Một mẫu đọc luôn CHIỀU siết thay vì
# bốn mẫu rời, vì bốn mẫu rời là bốn cơ hội quên một cái.
_GROQ_DIM_RE = re.compile(
    r"\bon\s+(tokens?|requests?)\s+per\s+(minute|hour|day)[^:]{0,40}:\s*"
    r"Limit\s+(\d+)\s*,\s*(?:Used\s+(\d+)\s*,\s*)?Requested\s+(\d+)", re.I)
_DIM_KIND = {("token", "minute"): "tpm", ("token", "day"): "tpd", ("token", "hour"): "tpm",
             ("request", "minute"): "rpm", ("request", "day"): "rpd",
             ("request", "hour"): "rpm"}

_PATTERNS: tuple[tuple[str, str, re.Pattern], ...] = (
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

# Dấu hiệu "vượt KÍCH THƯỚC" nói chung, để còn nhận ra lỗi mà không rút được số.
#
# "rate limit reached" ĐÃ BỊ GỠ khỏi danh sách này, và đó là bản vá quan trọng nhất ở đây.
# Nó là câu mở đầu chung của CẢ BỐN chiều siết (token/phút, lượt/phút, token/ngày,
# lượt/ngày), nên để nó ở đây nghĩa là mọi lần bị chặn nhịp đều bị gán nhãn "request quá
# lớn". Chặn nhịp giờ đi lối riêng ở _RATE_HINTS bên dưới, nơi lời khuyên là CHỜ chứ không
# phải co nhỏ.
_SIZE_ERROR_HINTS = (
    "request too large", "too many tokens", "maximum context length",
    "prompt is too long", "reduce your message size", "context_length_exceeded",
    "input token count", "exceeds the maximum",
)

# Bị chặn nhịp mà không đọc được chiều nào. Biết đây là chặn nhịp đã đủ để làm việc đúng
# (chờ), và quan trọng hơn là đủ để KHÔNG khuyên sai (rút gọn).
_RATE_HINTS = ("rate limit reached", "rate_limit_exceeded", "too many requests")


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
    snippet = text.strip()[:300]

    # Khuôn chung của Groq: đọc luôn CHIỀU siết, vì chiều mới quyết định phải làm gì.
    m = _GROQ_DIM_RE.search(text)
    if m:
        don_vi = m.group(1).rstrip("s").lower()
        chu_ky = m.group(2).lower()
        kind = _DIM_KIND.get((don_vi, chu_ky))
        if kind:
            try:
                limit = int(m.group(3))
                used = int(m.group(4) or 0)
                requested = int(m.group(5))
            except (TypeError, ValueError):
                limit = used = requested = 0
            if limit > 0:
                return LimitFact(kind=kind, limit=limit, requested=max(0, requested),
                                 source=f"groq_{kind}", used=max(0, used),
                                 retry_after=parse_retry_after(text), raw=snippet)

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
                         used=max(0, used), retry_after=parse_retry_after(text), raw=snippet)
    # Nhận ra là lỗi kích thước nhưng không rút được số: vẫn đáng báo, vì nó nói cho tầng
    # trên biết "co prompt lại rồi thử lại" thay vì "chờ rồi thử lại".
    low = text.casefold()
    if any(h in low for h in _SIZE_ERROR_HINTS):
        return LimitFact(kind="context", limit=0, requested=0, source="unparsed_size_error",
                         raw=snippet)
    # Bị chặn nhịp mà không đọc được chiều nào. KHÔNG gán nhãn kích thước: lời khuyên ở đây
    # là chờ, và nếu không biết chờ bao lâu thì phải hiện nguyên văn lời nhà cung cấp chứ
    # không được bịa một câu nghe như đã hiểu chuyện.
    if any(h in low for h in _RATE_HINTS):
        return LimitFact(kind="rate", limit=0, requested=0, source="unparsed_rate_limit",
                         retry_after=parse_retry_after(text), raw=snippet)
    return None


# ============================================================
# Hạn mức của gói THUÊ BAO (Claude Code, ChatGPT/Codex)
# ============================================================
# Vì sao tách hẳn khỏi LimitFact ở trên: hai loại hạn mức này đòi hai cách xử lý ngược nhau.
#
#   - Hạn mức API (LimitFact) đếm TOKEN. Vượt thì CO NHỎ prompt là qua được ngay.
#   - Hạn mức thuê bao đếm LƯỢT DÙNG theo cửa sổ giờ (Claude: 5 tiếng và tuần; ChatGPT:
#     tương tự). Vượt thì co prompt bao nhiêu cũng vô ích - phải CHỜ tới mốc reset, hoặc
#     đổi sang bộ não khác.
#
# Nhầm hai cái này là Javis sẽ cắt ngữ cảnh của người dùng để giải một bài toán mà cắt không
# giải được, rồi vẫn lỗi - tệ hơn hẳn việc nói thẳng "gói này hết lượt, tới HH:MM mới lại".
#
# Ranh giới trung thực: đây là NHẬN DẠNG CÂU CHỮ do CLI in ra, không phải một API hạn mức.
# Nhà cung cấp đổi cách viết thì mẫu sẽ trượt, và khi trượt thì Javis phải trả nguyên văn lỗi
# gốc chứ không được bịa ra một mốc reset. Vì vậy `reset_epoch` = 0 nghĩa là KHÔNG BIẾT, và
# mọi chỗ hiển thị đều phải xử đúng nghĩa "không biết" thay vì đoán bừa.


@dataclass(frozen=True)
class SubscriptionLimit:
    """Gói thuê bao đã hết lượt trong cửa sổ hiện tại."""
    engine: str            # "claude-code" | "codex"
    source: str            # mẫu nào khớp, để lần lại khi nhận diện sai
    reset_epoch: float = 0.0   # mốc reset (epoch giây). 0 = nhà cung cấp không nói.
    reset_text: str = ""       # nguyên văn phần nói về lúc reset, để hiện lại cho người dùng
    scope: str = ""            # "5 giờ" | "tuần" | "" (không rõ cửa sổ nào)


# Claude Code in ra dạng máy đọc được: "Claude AI usage limit reached|1730000000"
_CLAUDE_EPOCH_RE = re.compile(r"usage\s+limit\s+reached\s*\|\s*(\d{9,})", re.I)
# Và các dạng chữ. Mỗi mẫu kèm cửa sổ mà nó nói tới (nếu câu đó có nói).
_SUB_PATTERNS: tuple[tuple[str, str, str, re.Pattern], ...] = (
    ("claude_weekly", "claude-code", "tuần",
     re.compile(r"(weekly|per\s+week)\s+limit\s+reached|reached\s+your\s+weekly\s+limit", re.I)),
    ("claude_5h", "claude-code", "5 giờ",
     re.compile(r"\b5[\s-]?hour\s+limit\s+reached", re.I)),
    ("claude_usage", "claude-code", "",
     re.compile(r"claude\s+(ai\s+)?(usage|api)?\s*limit\s+reached", re.I)),
    ("claude_reached", "claude-code", "",
     re.compile(r"(you'?ve\s+)?reached\s+your\s+(current\s+)?usage\s+limit", re.I)),
    ("codex_hit", "codex", "",
     re.compile(r"(you'?ve\s+)?(hit|reached)\s+your\s+(usage|plan|weekly)\s+limit", re.I)),
    ("codex_quota", "codex", "",
     re.compile(r"usage\s+limit\s+reached|quota\s+exceeded\s+for\s+your\s+plan", re.I)),
)

# "resets at 3pm", "resets in 2 hours 15 minutes", "try again in 45 minutes"
_RESET_TEXT_RE = re.compile(
    r"(resets?\s+(?:at|in|on)\s+[^.\n|]{1,60}|try\s+again\s+in\s+[^.\n|]{1,40})", re.I)
_RESET_IN_RE = re.compile(
    r"\b(?:resets?|try\s+again)\s+in\s+"
    r"(?:(\d+)\s*(?:hours?|hrs?|h|giờ)\s*)?(?:(\d+)\s*(?:minutes?|mins?|m|phút))?", re.I)


def _reset_seconds(text: str) -> float:
    """Còn bao nhiêu giây nữa reset, theo câu "resets in ...". 0 = không đọc được."""
    m = _RESET_IN_RE.search(text or "")
    if not m or not (m.group(1) or m.group(2)):
        return 0.0
    hours = int(m.group(1) or 0)
    minutes = int(m.group(2) or 0)
    return float(hours * 3600 + minutes * 60)


def parse_subscription_limit(text: str, engine_hint: str = "",
                             now: float | None = None) -> SubscriptionLimit | None:
    """Nhận ra lỗi "gói thuê bao hết lượt". None nghĩa là không phải loại lỗi này.

    engine_hint dùng khi câu chữ không tự nói nó là engine nào (vd Codex chỉ in "usage limit
    reached"). Không có hint thì để mẫu tự quyết.
    """
    raw = str(text or "")
    if not raw.strip():
        return None
    ts = time.time() if now is None else float(now)

    epoch = 0.0
    m = _CLAUDE_EPOCH_RE.search(raw)
    if m:
        try:
            epoch = float(m.group(1))
        except (TypeError, ValueError):
            epoch = 0.0

    for name, engine, scope, pattern in _SUB_PATTERNS:
        if not pattern.search(raw):
            continue
        if epoch <= 0:
            delta = _reset_seconds(raw)
            if delta > 0:
                epoch = ts + delta
        note = _RESET_TEXT_RE.search(raw)
        return SubscriptionLimit(
            engine=(engine_hint or engine), source=name,
            reset_epoch=epoch if epoch > ts else 0.0,
            reset_text=(note.group(1).strip() if note else ""),
            scope=scope,
        )
    # Dạng máy đọc được của Claude Code có thể tới mà không kèm câu chữ nào khớp mẫu trên.
    if epoch > 0:
        return SubscriptionLimit(engine=(engine_hint or "claude-code"), source="claude_epoch",
                                 reset_epoch=epoch if epoch > ts else 0.0, scope="")
    return None


_lock = threading.Lock()
_learned: dict[tuple[str, str], tuple[LimitFact, float]] = {}


def _key(provider: str, model: str) -> tuple[str, str]:
    return (str(provider or "?").strip().casefold(), str(model or "?").strip())


def remember(provider: str, model: str, fact: LimitFact, now: float | None = None) -> None:
    """Nhớ hạn mức nhà cung cấp vừa nói. Bỏ qua fact không có con số.

    Nhớ CẢ hạn mức đếm lượt (rpm/rpd) vì trang chẩn đoán cần hiện, nhưng nơi dùng làm ngân
    sách token phải tự lọc bằng `counts_tokens` - xem `learned_token_limit`."""
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


def learned_token_limit(provider: str, model: str, now: float | None = None) -> LimitFact | None:
    """Hạn mức đã học mà DÙNG ĐƯỢC làm ngân sách cho một request.

    Tách hẳn khỏi `learned()` để chỗ gọi không phải nhớ tự lọc. Quên lọc một lần là lấy
    "30 lượt mỗi phút" làm ngân sách 30 token - xem LimitFact.BUDGET_KINDS."""
    fact = learned(provider, model, now)
    return fact if (fact and fact.usable_as_budget) else None


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
            # Đếm token hay đếm lượt. Trang chẩn đoán phải nói ra, vì "Limit 30" của hạn mức
            # lượt-mỗi-phút nhìn giống hệt một hạn mức token bé tí đáng sợ.
            "dem_token": fact.counts_tokens,
            "viec_can_lam": fact.remedy,
        }
    return out


def shrink_target(fact: LimitFact, safety: float = 0.75) -> int:
    """Số token nên nhắm tới cho lần thử lại. 0 nghĩa là không biết, đừng đoán.

    Nhắm THẤP hơn hạn mức khá nhiều vì hai lý do: hạn mức TPM là cửa sổ trượt nên phần vừa
    gửi hỏng vẫn còn nằm trong cửa sổ đó, và bộ đếm token của ta chỉ là ước lượng.

    CHỈ trả số cho hạn mức ĐẾM TOKEN. Hạn mức đếm LƯỢT ("30 lượt mỗi phút") mà đem nhân 0,75
    thì thành "co ngữ cảnh xuống 22 token" - vô nghĩa và huỷ hoại lượt chat. Đây là loại lỗi
    chỉ lộ ra khi gặp đúng gói bị siết theo lượt, tức là muộn."""
    if not fact or not fact.usable_as_budget:
        return 0
    return max(256, int(fact.limit * max(0.1, min(float(safety), 0.95))))


def reset() -> None:
    """Chỉ dùng trong test."""
    with _lock:
        _learned.clear()
