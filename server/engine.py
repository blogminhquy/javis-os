"""
Lớp engine cho CHAT qua API nhà cung cấp: OpenRouter, OpenAI, Anthropic API, Google Gemini.
(Hai engine CLI - Claude Code và Codex - nằm ở claude_cli.py.)

Mỗi provider có HAI đường vào:
- `*_chat`            : chat trần, không tool. Chỉ dùng khi hub không tìm được tool nào.
- `*_chat_with_mcp`   : vòng gọi tool đầy đủ với MCP Javis + tool file brain + skill. Đây là
                        đường MẶC ĐỊNH mà main.py::_api_stream_mcp chọn, nên "engine API =
                        chat thuần" KHÔNG còn đúng từ 0.9.
Stream token-by-token; trả các event {"type":"text"|"error","content":...} giống ClaudeCLI.query.
"""
import asyncio
import json
import os
import random
import re
import sys
import threading
import time
from datetime import datetime, timezone

import httpx

import limit_learner

# Lone surrogate (U+D800–U+DFFF) sanitizer - port từ hermes-agent/agent/message_sanitization.py.
# Model open-weight (qwen/deepseek/minimax/glm…) thi thoảng stream ra lone surrogate trong content.
# Ký tự này KHÔNG hợp lệ UTF-8: (1) ghi conversations/*.md (open encoding utf-8) ném UnicodeEncodeError
# → mất log học; (2) resend history → httpx ensure_ascii escape thành \udXXX gửi sang provider → có nơi
# 400. Thay bằng U+FFFD; no-op nhanh khi không có surrogate.
_SURROGATE_RE = re.compile(r"[\ud800-\udfff]")


def _sanitize_surrogates(text: str) -> str:
    if text and _SURROGATE_RE.search(text):
        return _SURROGATE_RE.sub("�", text)
    return text


# Dấu trích dẫn nội bộ của OpenAI, gói trong vùng ký tự Private Use: U+E200 mở, U+E202 ngăn,
# U+E201 đóng. Ví dụ thật lọt ra màn hình chủ repo: "citeturn4view0" - trình
# duyệt vẽ ba ký tự đó thành ba ô vuông trống, nên câu trả lời hiện ra là
# "Độ ẩm 70-99%. ␣cite␣turn4view0␣".
#
# Bóc chứ không dịch, vì bên trong KHÔNG có gì để giữ: nó chỉ là mã tham chiếu nội bộ
# ("turn4view0"), không kèm URL. Chính Javis cũng mắc bẫy này - được hỏi lấy tin ở đâu thì
# trả lời "mình chỉ còn mã tham chiếu turn4view0, không có URL nguồn gốc". Để nguyên là vừa
# bẩn màn hình vừa dạy model rằng đó là một nguồn có thật.
#
# Vùng Private Use không có nghĩa chuẩn nào, nội dung thật không bao giờ chứa nó, nên quét
# sạch cả vùng là an toàn - kể cả khi nhà cung cấp đổi khuôn dấu.
# Viết bằng mã escape chứ KHÔNG dán ký tự thật: chúng vô hình trong mọi trình soạn thảo,
# nên dán thẳng vào nguồn là dòng code trông như có lỗi đánh máy và lần sau ai đọc cũng
# xoá nhầm.
_MARKER_CA_KHOI = re.compile("\ue200[^\ue201]{0,200}\ue201")   # nguyên một dấu, có mở có đóng
_MARKER_SOT = re.compile("[\ue200-\ue20f]")                     # mảnh vụn khi dấu bị cắt giữa


def strip_provider_markers(text: str) -> str:
    """Bóc dấu trích dẫn nội bộ nhà cung cấp khỏi văn bản trước khi cho người dùng thấy.

    Bóc hai lượt vì stream cắt văn bản thành từng mẩu: một dấu hoàn chỉnh có thể bị chia
    đôi giữa hai mẩu, nên sau khi gỡ các khối trọn vẹn vẫn phải quét nốt mảnh vụn còn sót.
    """
    if not text:
        return text
    return _MARKER_SOT.sub("", _MARKER_CA_KHOI.sub("", text))


# Decorrelated jitter counter để nhiều stream chạy song song không retry cùng instant
_retry_counter = 0
_retry_lock = threading.Lock()


def _jittered_backoff(attempt: int, base: float = 1.0, max_delay: float = 8.0, jitter_ratio: float = 0.3) -> float:
    """Exponential backoff + jitter [0, jitter_ratio*delay]. attempt 1-based."""
    global _retry_counter
    with _retry_lock:
        _retry_counter += 1
        tick = _retry_counter
    delay = min(base * (2 ** max(0, attempt - 1)), max_delay)
    seed = (time.time_ns() ^ (tick * 0x9E3779B9)) & 0xFFFFFFFF
    return delay + random.Random(seed).uniform(0, jitter_ratio * delay)


_RETRY_STATUS = {408, 429, 502, 503, 504, 529}   # 529 = Anthropic/OpenRouter "Overloaded" (transient)
_RETRY_EXC = (httpx.ReadTimeout, httpx.ConnectTimeout, httpx.ConnectError, httpx.RemoteProtocolError)

# Cụm từ trong BODY báo lỗi tạm thời - bắt ca provider trả overload/rate-limit dưới status KHÔNG retriable
# (vd 400/402/200-with-error). Hẹp & nghiêng "overload/throttle" để 400 sai-format thật KHÔNG khớp.
_TRANSIENT_BODY_PATTERNS = (
    "overloaded", "at capacity", "over capacity", "temporarily unavailable",
    "too many requests", "try again in", "please retry after", "rate limit",
)


def _is_transient_body(text: str) -> bool:
    """True nếu body báo lỗi mang dấu hiệu tạm thời (đáng retry) dù status không nằm trong _RETRY_STATUS.
    Theo insight error_classifier của Hermes: phân loại theo MESSAGE, không chỉ status code."""
    if not text:
        return False
    low = text.lower()
    return any(p in low for p in _TRANSIENT_BODY_PATTERNS)


def _describe_exc(err: BaseException, max_depth: int = 3) -> str:
    """Walk __cause__/__context__ để phơi root cause. SDK thường wrap httpx error
    → 'APIConnectionError' đơn độc vô nghĩa, cần thấy 'RemoteProtocolError' bên trong."""
    seen, link, parts = [], err, []
    while link is not None and len(seen) < max_depth + 1:
        if any(link is s for s in seen):
            break
        seen.append(link)
        msg = str(link).strip().replace("\n", " ")
        if len(msg) > 140:
            msg = msg[:140] + "…"
        parts.append(f"{type(link).__name__}({msg})" if msg else type(link).__name__)
        nxt = getattr(link, "__cause__", None) or getattr(link, "__context__", None)
        if nxt is None or nxt is link:
            break
        link = nxt
    return " <- ".join(parts) if parts else type(err).__name__


# Anthropic gắn thời điểm cửa sổ hạn mức mở lại vào các header này, dạng mốc thời gian
# RFC3339 (vd "2026-08-09T09:52:31Z"). Chúng có mặt kể cả khi KHÔNG có `Retry-After`, và
# lúc đó đây là nguồn duy nhất nói được phải chờ bao lâu. Bỏ qua chúng nghĩa là tự đoán
# bằng backoff, mà đoán 1 giây cho một cửa sổ tính bằng phút thì thử lại chỉ tổ tốn lượt.
_ANTHROPIC_RESET_HEADERS = (
    "anthropic-ratelimit-requests-reset",
    "anthropic-ratelimit-tokens-reset",
    "anthropic-ratelimit-input-tokens-reset",
    "anthropic-ratelimit-output-tokens-reset",
)


def _giay_toi_moc(raw) -> float | None:
    """Mốc RFC3339 -> còn bao nhiêu giây nữa tới đó. None nếu không đọc được."""
    s = str(raw or "").strip()
    if not s:
        return None
    try:
        moc = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None
    if moc.tzinfo is None:
        moc = moc.replace(tzinfo=timezone.utc)
    return (moc - datetime.now(timezone.utc)).total_seconds()


def _parse_retry_after(headers, cap: float = 600.0):
    """Nhà cung cấp bảo chờ bao nhiêu giây trước khi hỏi lại? None nếu không nói.

    Ưu tiên `Retry-After` (OpenRouter/Anthropic gửi dạng số giây; bỏ qua dạng HTTP-date hiếm
    gặp). Thiếu nó thì đọc các header reset của Anthropic và lấy cửa sổ mở SỚM NHẤT: chờ hụt
    thì còn lượt thử lại để chờ tiếp, còn chờ dư là bắt người ta ngồi im vô ích.

    Cap 600s: đủ phủ mọi reset window thực tế, chặn giá trị bệnh lý.
    """
    if not headers or not hasattr(headers, "get"):
        return None
    raw = headers.get("retry-after") or headers.get("Retry-After")
    if raw:
        try:
            return max(0.0, min(float(raw), cap))
        except (TypeError, ValueError):
            pass
    som_nhat = None
    for ten in _ANTHROPIC_RESET_HEADERS:
        giay = _giay_toi_moc(headers.get(ten))
        # Mốc đã trôi qua (<=0) không nói được gì: đồng hồ hai máy lệch nhau là thường, và
        # "chờ 0 giây" thì hỏi lại ngay chỉ để nhận đúng cú 429 vừa rồi.
        if giay is not None and giay > 0 and (som_nhat is None or giay < som_nhat):
            som_nhat = giay
    if som_nhat is None:
        return None
    return max(0.0, min(som_nhat, cap))


# Trần thời gian CHỜ cửa sổ hạn mức trượt qua. Quá ngưỡng này thì báo cho người dùng thay
# vì ngồi im: chờ 10 giây là chấp nhận được, chờ một phút thì người ta tưởng treo.
_WINDOW_WAIT_MAX = 25.0

# Model tự bịa cú pháp gọi tool thay vì JSON chuẩn. Provider trả 400 kèm mã riêng; bắt theo
# MÃ và cụm từ đặc trưng chứ không theo status, vì 400 còn dùng cho cả chục lỗi khác mà thử
# lại chỉ tổ tốn thêm một lượt (payload sai định dạng, model không tồn tại, thiếu tham số).
_TOOL_SYNTAX_FAIL = ("tool_use_failed", "failed to call a function",
                     "failed_generation")


def _is_tool_syntax_failure(body_text: str) -> bool:
    low = str(body_text or "").casefold()
    return any(p in low for p in _TOOL_SYNTAX_FAIL)


class _RetryStream(Exception):
    """Sentinel để thoát các async with lồng nhau và quay lại vòng retry.
    retry_after: giây provider yêu cầu chờ (từ header Retry-After) - None thì dùng jittered backoff."""
    def __init__(self, retry_after=None):
        super().__init__()
        self.retry_after = retry_after


# ============================================================
# Lỗi TẠM THỜI: đánh dấu tại nguồn, chạy lại ở tầng trên
# ============================================================
def ev_loi_http(nhan, status, body_text, headers=None, fact=None, cat=300):
    """Sự kiện lỗi HTTP, kèm câu trả lời cho một câu hỏi: lượt này chạy lại được không?

    Đánh dấu tại NGUỒN vì chỉ ở đây mới còn đủ dữ kiện: status thật, body thật, và header
    `Retry-After` nhà cung cấp gửi kèm. Lên tới tầng trên thì tất cả đã bị ép thành một chuỗi
    chữ, và đoán lại bằng cách dò chữ trong chuỗi đó là thứ hỏng ngay lần đầu ai đó sửa nhãn.

    `fact` là hạn mức `limit_learner` vừa đọc được. Có nó thì KHÔNG đánh dấu: đó là lỗi vượt
    kích thước hoặc hết quota có thật, chạy lại y nguyên chỉ tốn thêm một lượt để nhận lại
    đúng lỗi đó. Phải co lại hoặc chờ cửa sổ trượt qua trước.
    """
    ev = {"type": "error", "content": f"{nhan} {status}: {str(body_text or '')[:cat]}"}
    if fact is None and (status in _RETRY_STATUS or _is_transient_body(str(body_text or ""))):
        ev["tam_thoi"] = True
        # Giữ status thật để tầng thử lại chọn được nhịp chờ đúng loại. 429 là hạn mức, cửa
        # sổ của nó tính bằng chục giây; 502/504 là một cú vấp, một giây sau thường đã ngon.
        # Hai thứ đó mà chờ chung một nhịp thì một trong hai luôn sai.
        ev["ma"] = status
        cho = _parse_retry_after(headers)
        if cho is not None:
            ev["cho"] = cho
    return ev


def ev_loi_exc(nhan, exc):
    """Sự kiện lỗi từ một ngoại lệ. Chỉ lỗi MẠNG mới đáng chạy lại.

    Lỗi lập trình (JSON hỏng, thiếu khoá, sai kiểu) chạy lại bao nhiêu lần cũng hỏng y hệt,
    và mỗi lần chạy lại là một lượt gọi model thật đã trả tiền.
    """
    ev = {"type": "error", "content": f"{nhan}: {_describe_exc(exc)}"}
    if isinstance(exc, _RETRY_EXC):
        ev["tam_thoi"] = True
    return ev


async def thu_lai_khi_tam_thoi(tao_stream, *, so_lan=3, nhan=""):
    """Chạy lại một lượt gọi model khi nó gãy vì lỗi TẠM THỜI (429, 5xx, mạng chớp tắt).

    Vì sao nằm ở TẦNG SỰ KIỆN chứ không nhét vào từng hàm stream: có tám đường gọi model và
    bốn vòng tool, mỗi cái một kiểu HTTP riêng. Nhét retry vào từng cái là tám bản sao của
    cùng một logic - và đó đúng là chỗ đã hỏng: `openrouter_stream` có retry từ lâu, bảy
    đường còn lại thì không. Một cú 429 chớp nhoáng của Anthropic đủ giết trọn một lượt trả
    lời của bot chuyên trách, để lại cho người nhắn một câu xin lỗi kỹ thuật và gọi người
    trực dậy - trong khi thử lại sau một giây là xong.

    Hai điều kiện để chạy lại, thiếu một là thôi:

    1. **Chưa nhả chữ nào ra ngoài.** Người ta đã đọc được nửa câu rồi thì chạy lại nghĩa là
       câu trả lời hiện ra hai lần.
    2. **Chưa chạy tool nào.** Vòng tool có thể đã gửi tin, đã ghi file, đã đặt lịch. Chạy
       lại cả vòng là làm lại từ đầu những việc đó. Thà báo lỗi còn hơn làm hai lần.

    Hết lượt mà vẫn hỏng thì trả đúng lỗi gốc, nhưng GỠ dấu `tam_thoi` đi: dấu đó là lời mời
    chạy lại, mà đã hết lượt rồi. Nhờ vậy bọc chồng hai lớp cũng không nở thành chín lần gọi,
    và `openrouter_stream` - vốn tự retry bên trong - không bị thử lại thêm một tầng nữa.
    """
    da_meta = False
    for lan in range(1, max(1, so_lan) + 1):
        chan = False        # đã nhả chữ / đã chạy tool → lượt này không chạy lại được nữa
        loi_hoan = None
        gen = tao_stream()
        try:
            async for ev in gen:
                t = ev.get("type")
                if t == "meta":
                    if da_meta:
                        continue        # lần chạy lại không phát lại meta cũ
                    da_meta = True
                elif t == "tool_call" or (t == "text" and ev.get("content")):
                    chan = True
                elif t == "error" and ev.get("tam_thoi") and not chan:
                    loi_hoan = ev
                    break
                yield ev
        finally:
            aclose = getattr(gen, "aclose", None)
            if aclose is not None:
                await aclose()
        if loi_hoan is None:
            return
        cho = loi_hoan.get("cho")
        if cho is None:
            # Nhà cung cấp không nói phải chờ bao lâu thì tự đoán, nhưng đoán theo LOẠI lỗi.
            # Nhịp mặc định 1s-2s-4s vá được cú vấp mạng, còn với 429 thì nó vô dụng: ba lần
            # thử gói gọn trong bảy giây, trong khi cửa sổ hạn mức của Anthropic tính theo
            # phút. Hỏi lại ba lần trong bảy giây chỉ là ăn đúng cú 429 đó ba lần.
            cho = (_jittered_backoff(lan, base=5.0, max_delay=20.0)
                   if loi_hoan.get("ma") == 429 else _jittered_backoff(lan))
        # Nhà cung cấp bảo chờ lâu hơn ngưỡng người ta chịu ngồi im thì đừng chờ - báo ngay để
        # họ biết mà làm việc khác, thay vì nhìn màn hình đứng yên nửa phút.
        if lan >= so_lan or cho > _WINDOW_WAIT_MAX:
            cuoi = dict(loi_hoan)
            cuoi.pop("tam_thoi", None)
            cuoi.pop("cho", None)
            cuoi["da_thu"] = lan
            if lan > 1:
                cuoi["content"] = f"{cuoi['content']} (đã thử lại {lan} lần)"
            # Câu này đi thẳng lên thẻ bot của CHỦ. Một cục JSON của nhà cung cấp không nói
            # được phải làm gì tiếp, mà đó đúng là thứ chủ cần biết khi nhìn thẻ đỏ.
            if loi_hoan.get("ma") == 429:
                cuoi["content"] += (
                    f" - hạn mức nhà cung cấp đang đầy"
                    + (f", cửa sổ mở lại sau khoảng {cho:.0f}s" if cho > _WINDOW_WAIT_MAX else "")
                    + ". Chờ cửa sổ trôi qua, hoặc đổi bộ não cho bot ở trang Models."
                )
            yield cuoi
            return
        print(f"[thử lại {nhan or '?'}] lần {lan} gãy tạm thời, chờ {cho:.1f}s: "
              f"{str(loi_hoan.get('content'))[:160]}", file=sys.stderr)
        await asyncio.sleep(cho)


def _apply_anthropic_cache(payload: dict, cache_ttl: str = "5m") -> None:
    """Áp prompt caching 'system_and_3' cho Anthropic Messages API: đánh cache_control
    trên system prompt + 3 message cuối → cache read 0.1x cost (giảm ~75% input token)
    cho multi-turn. Anthropic ignore an toàn nếu prompt < min token (1024 Sonnet/Opus,
    2048 Haiku) - không lỗi. Port từ Hermes agent/prompt_caching.py."""
    marker: dict = {"type": "ephemeral"}
    if cache_ttl == "1h":
        marker["ttl"] = "1h"
    sys_val = payload.get("system")
    if isinstance(sys_val, str) and sys_val:
        payload["system"] = [{"type": "text", "text": sys_val, "cache_control": marker}]
    elif isinstance(sys_val, list) and sys_val:
        last = sys_val[-1]
        if isinstance(last, dict):
            last["cache_control"] = marker
    msgs = payload.get("messages") or []
    for msg in msgs[-3:]:
        content = msg.get("content")
        if isinstance(content, str) and content:
            msg["content"] = [{"type": "text", "text": content, "cache_control": marker}]
        elif isinstance(content, list) and content:
            last = content[-1]
            if isinstance(last, dict):
                last["cache_control"] = marker


def _anthropic_mark_last(conv):
    """Copy conv + đánh cache_control lên block cuối của message cuối - cho vòng tool MCP.
    KHÔNG mutate conv gốc nên marker không tích luỹ qua các vòng tool (trần Anthropic
    4 breakpoint/request; ở đây tối đa 3: tools + system + message cuối). Message cuối
    lúc gửi luôn là user (câu hỏi hoặc tool_result) - hai loại block đều nhận cache_control."""
    if not conv:
        return conv
    marker = {"type": "ephemeral"}
    out = list(conv)
    last = dict(out[-1])
    c = last.get("content")
    if isinstance(c, str) and c:
        last["content"] = [{"type": "text", "text": c, "cache_control": marker}]
    elif isinstance(c, list) and c:
        blocks = list(c)
        if isinstance(blocks[-1], dict):
            lb = dict(blocks[-1])
            lb["cache_control"] = marker
            blocks[-1] = lb
        last["content"] = blocks
    out[-1] = last
    return out


def _is_claude_model(model):
    """Model OpenRouter thuộc họ Claude? (cache_control chỉ pass-through cho Anthropic)."""
    m = (model or "").lower()
    return "claude" in m or m.startswith("anthropic/")


def _or_mark_system(messages):
    """Copy messages, đánh cache_control lên system message ĐẦU (định dạng OpenAI-style của
    OpenRouter). System của Javis ~26k ký tự và bất biến trong phiên - cache được là lãi nhất.
    KHÔNG mutate list gốc: or_messages sống qua nhiều lượt, mutate là marker dính vĩnh viễn."""
    out = []
    marked = False
    for m in messages:
        if not marked and m.get("role") == "system" and isinstance(m.get("content"), str) and m["content"]:
            m = dict(m)
            m["content"] = [{"type": "text", "text": m["content"], "cache_control": {"type": "ephemeral"}}]
            marked = True
        out.append(m)
    return out


# Một số model OpenRouter (qwen, deepseek-r1, minimax...) nhét reasoning INLINE vào
# content dưới dạng <think>...</think> thay vì field "reasoning" riêng → nếu yield
# thẳng thì tag lậu lên chat, bẩn conversation log và phá parse JAVIS_METRICS.
# Scrubber stateful gỡ block khỏi text hiển thị, giữ đuôi tag chẻ đôi giữa 2 delta
# lại tới delta sau mới quyết định. Port rút gọn từ Hermes agent/think_scrubber.py.
_THINK_OPEN = ("<think>", "<thinking>")
_THINK_CLOSE = ("</think>", "</thinking>")
_THINK_MAXLEN = max(len(t) for t in _THINK_OPEN + _THINK_CLOSE)


def _think_find(low: str, tags) -> tuple:
    """Vị trí + tag xuất hiện sớm nhất trong chuỗi đã lowercase; (-1, '') nếu không có."""
    best, best_tag = -1, ""
    for t in tags:
        i = low.find(t)
        if i != -1 and (best == -1 or i < best):
            best, best_tag = i, t
    return best, best_tag


def _think_partial_tail(low: str, tags) -> int:
    """Độ dài đuôi có thể là phần đầu của một tag (giữ lại chờ delta sau)."""
    for n in range(min(len(low), _THINK_MAXLEN - 1), 0, -1):
        if any(t.startswith(low[-n:]) for t in tags):
            return n
    return 0


class _ThinkScrubber:
    """Gỡ <think>…</think> khỏi text stream theo từng delta. Reset/khởi tạo mỗi attempt."""

    def __init__(self):
        self._in = False   # đang ở trong block reasoning (đang nuốt chữ)
        self._buf = ""     # đuôi có thể là tag chẻ đôi, giữ lại

    def feed(self, text: str) -> str:
        if not text:
            return ""
        buf, self._buf, out = self._buf + text, "", []
        while buf:
            low = buf.lower()
            tags = _THINK_CLOSE if self._in else _THINK_OPEN
            idx, tag = _think_find(low, tags)
            if idx == -1:
                n = _think_partial_tail(low, tags)
                if not self._in:
                    out.append(buf[:len(buf) - n] if n else buf)
                self._buf = buf[len(buf) - n:] if n else ""
                break
            if not self._in:
                out.append(buf[:idx])
            buf = buf[idx + len(tag):]
            self._in = not self._in
        return "".join(out)

    def flush(self) -> str:
        """Cuối stream: còn đang trong block → bỏ (rò reasoning dở còn tệ hơn cụt);
        ngoài block → đuôi giữ lại là prose thật, trả về."""
        tail = "" if self._in else self._buf
        self._buf, self._in = "", False
        return tail


OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENAI_URL = "https://api.openai.com/v1/chat/completions"
ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
# Google Gemini qua endpoint TƯƠNG THÍCH OpenAI → dùng lại nguyên logic Chat Completions
# (stream, usage, tool-calling) như OpenAI, chỉ khác base URL + auth Bearer bằng Gemini API key.
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
# Groq đổi tên model khá nhanh (model cũ bị deprecate rồi gỡ). Để một chỗ duy nhất, và
# picker vẫn nạp danh sách LIVE từ /openai/v1/models nên mặc định này chỉ là lưới an toàn.
GROQ_DEFAULT_MODEL = "llama-3.3-70b-versatile"

# Ollama - model chạy NGAY TRÊN MÁY người dùng. Khác mọi provider trên ở hai điểm, và cả hai
# đều ăn vào cách viết mã chứ không chỉ là cấu hình:
#   1. KHÔNG có API key. Nó nghe trên máy nhà nên không có gì để xác thực. Header Authorization
#      vẫn gửi (Ollama bỏ qua) để dùng lại nguyên đường OpenAI-compat, khỏi rẽ thêm nhánh.
#   2. Địa chỉ KHÔNG cố định. Người dùng có thể chạy trên máy khác trong mạng, hoặc đổi cổng,
#      nên URL phải dựng từ host trong cấu hình chứ không hằng số hoá được như bốn cái trên.
# Ollama Cloud - model của Ollama chạy trên máy chủ của họ, xác thực bằng API key lấy ở
# ollama.com. Javis CỐ Ý chỉ đấu bản Cloud: bản chạy trên máy nhà đòi một ô địa chỉ riêng,
# tức một ca đặc biệt duy nhất xuyên suốt lớp nhà cung cấp, trong khi phần đông người dùng
# Javis chạy nó trên VPS - nơi "localhost" là chính cái container chứ không phải máy họ.
OLLAMA_BASE = "https://ollama.com"
OLLAMA_URL = OLLAMA_BASE + "/v1/chat/completions"

# Model Anthropic hỗ trợ adaptive thinking + output_config.effort (khỏi budget_tokens).
_ADAPTIVE_THINKING = ("opus-4-8", "opus-4-7", "opus-4-6", "opus-4-5", "sonnet-4-6", "fable-5", "mythos-5")


# Thang độ sâu suy nghĩ của Javis. Nhiều nấc hơn bộ low/medium/high mà API nhận, vì hai nấc
# trên cùng phục vụ đường Claude Code (từ khoá think) và đường Anthropic model cũ (budget token)
# - hai chỗ Javis tự điều khiển được độ sâu.
REASONING_LEVELS = ("off", "low", "medium", "high", "xhigh", "ultra")
# Giá trị effort GỬI LÊN API. Nhà cung cấp chỉ nhận low|medium|high; gửi "ultra" là ăn 400 và
# hỏng cả lượt chat. Nên hai nấc trên cùng quy về "high" khi nói chuyện với API.
_API_EFFORT = {"low": "low", "medium": "medium", "high": "high", "xhigh": "high", "ultra": "high"}


def api_effort(reasoning):
    """Mức Javis -> giá trị effort AN TOÀN để nhét vào payload của nhà cung cấp.

    Nơi gọi phải TỰ chặn mức "off" trước (không gửi trường effort gì cả); hàm này chỉ lo dịch
    mức đã bật. Giá trị lạ rơi về "medium" để một chỗ ghi sai config không làm hỏng cả lượt chat.
    """
    return _API_EFFORT.get(reasoning or "", "medium")


def _anthropic_reasoning(model, reasoning):
    """Phần payload thinking cho Messages API theo mức reasoning (xem REASONING_LEVELS).
    Model 4.6+ → adaptive thinking + effort (budget_tokens bị 400 trên 4.7/4.8).
    Model cũ (haiku-4-5, sonnet-4-5...) → extended thinking với budget_tokens < max_tokens."""
    if reasoning in (None, "", "off"):
        return {}
    m = (model or "").lower()
    if any(k in m for k in _ADAPTIVE_THINKING):
        return {
            "thinking": {"type": "adaptive", "display": "summarized"},
            "output_config": {"effort": api_effort(reasoning)},
            "max_tokens": 16000,   # chừa chỗ cho thinking + câu trả lời (đang stream nên không lo timeout)
        }
    # Model cũ: budget_tokens là chỗ hai nấc trên cùng khác nhau THẬT, không phải nhãn suông.
    budget = {"low": 2000, "medium": 6000, "high": 12000,
              "xhigh": 20000, "ultra": 32000}.get(reasoning, 6000)
    return {"thinking": {"type": "enabled", "budget_tokens": budget}, "max_tokens": budget + 8000}


def _openai_is_reasoning(model):
    """OpenAI: chỉ model o-series / gpt-5 nhận reasoning_effort (gpt-4o sẽ 400 nếu gửi)."""
    m = (model or "").lower()
    return m.startswith(("o1", "o3", "o4")) or "gpt-5" in m


def _groq_is_reasoning(model):
    """Groq: chỉ dòng suy luận (qwen3, deepseek-r1, gpt-oss, kimi-k2-thinking) nhận
    reasoning_effort. Model thường (llama, mixtral, gemma) gửi vào là 400."""
    m = (model or "").lower()
    return any(s in m for s in ("qwen3", "deepseek-r1", "gpt-oss", "thinking", "reasoning"))


def _gemini_is_reasoning(model):
    """Gemini: model 'thinking' (2.5 trở lên) nhận reasoning_effort qua endpoint OpenAI-compat.
    Model cũ (1.5 / 2.0-flash không thinking) → KHÔNG gửi để tránh 400."""
    m = (model or "").lower()
    return "2.5" in m or "gemini-3" in m or "thinking" in m


async def _openai_compat_stream(url, label, api_key, model, messages, reasoning, send_reasoning):
    """Chat Completions dạng OpenAI (dùng chung cho OpenAI + Gemini qua endpoint tương thích).
    Stream token-by-token + usage token ở chunk cuối. label chỉ dùng cho thông báo lỗi."""
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {"model": model, "messages": messages, "stream": True,
               "stream_options": {"include_usage": True}}   # → chunk cuối kèm usage token
    if reasoning not in (None, "", "off") and send_reasoning:
        payload["reasoning_effort"] = api_effort(reasoning)
    try:
        timeout = httpx.Timeout(120.0, connect=15.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream("POST", url, headers=headers, json=payload) as r:
                if r.status_code != 200:
                    body = await r.aread()
                    body_text = body.decode("utf-8", "replace")
                    # Nhà cung cấp vừa nói thẳng hạn mức thật của tài khoản này. Đó là con
                    # số đáng tin nhất đang có - đáng tin hơn mọi thứ tra từ tài liệu - nên
                    # phải học lấy thay vì vứt đi rồi bắt người dùng tự khai.
                    _fact = limit_learner.parse_limit_error(r.status_code, body_text)
                    if _fact:
                        limit_learner.remember(label, model, _fact)
                        yield {"type": "limit_exceeded", "provider": label, "model": model,
                               "kind": _fact.kind, "limit": _fact.limit,
                               "requested": _fact.requested,
                               "shrink_to": limit_learner.shrink_target(_fact),
                           "remedy": _fact.remedy, "raw": _fact.raw}
                    yield ev_loi_http(label, r.status_code, body_text, r.headers, _fact)
                    return
                got = False
                usage = None
                async for line in r.aiter_lines():
                    line = (line or "").strip()
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    try:
                        obj = json.loads(data)
                    except json.JSONDecodeError:
                        continue
                    if obj.get("usage"):
                        usage = obj["usage"]
                    c = ((obj.get("choices") or [{}])[0].get("delta") or {}).get("content")
                    if c:
                        got = True
                        yield {"type": "text", "content": c}
                if usage:
                    yield {"type": "usage", "input": usage.get("prompt_tokens", 0), "output": usage.get("completion_tokens", 0)}
                if not got:
                    yield {"type": "error", "content": f"{label} trả về rỗng. Thử model khác."}
    except Exception as e:
        yield ev_loi_exc(f"{label} lỗi", e)


async def openai_stream(api_key, model, messages, reasoning="off"):
    """OpenAI Chat Completions (provider 'openai') - chat thuần, định dạng giống OpenRouter."""
    async for ev in _openai_compat_stream(OPENAI_URL, "OpenAI", api_key, model or "gpt-4o-mini",
                                          messages, reasoning, _openai_is_reasoning(model)):
        yield ev


async def groq_stream(api_key, model, messages, reasoning="off"):
    """Groq (endpoint OpenAI-compatible, provider 'groq') - nhánh KHÔNG tool (dự phòng khi hub
    không có tool nào; đường thường là groq_chat_with_mcp)."""
    async for ev in _openai_compat_stream(GROQ_URL, "Groq", api_key, model or GROQ_DEFAULT_MODEL,
                                          messages, reasoning, _groq_is_reasoning(model)):
        yield ev


async def ollama_stream(api_key, model, messages, reasoning="off"):
    """Ollama Cloud (endpoint OpenAI-compatible, provider 'ollama') - nhánh KHÔNG tool.

    reasoning bỏ qua: `reasoning_effort` là tham số của OpenAI; model bên Ollama không hiểu,
    và gửi thừa thì có bản trả 400 chứ không im lặng bỏ qua.
    """
    async for ev in _openai_compat_stream(OLLAMA_URL, "Ollama", api_key, model,
                                          messages, reasoning, False):
        yield ev


async def gemini_stream(api_key, model, messages, reasoning="off"):
    """Google Gemini qua endpoint OpenAI-compatible (provider 'gemini') - chat thuần, cùng định dạng."""
    async for ev in _openai_compat_stream(GEMINI_URL, "Gemini", api_key, model or "gemini-2.5-flash",
                                          messages, reasoning, _gemini_is_reasoning(model)):
        yield ev


async def anthropic_stream(api_key, model, messages, reasoning="off"):
    """Anthropic Messages API (provider 'anthropic-api') - nhánh KHÔNG tool (dự phòng khi hub
    không có tool nào; đường thường là anthropic_chat_with_mcp).
    Tách system ra field riêng (Anthropic không nhận role=system trong messages).

    CHỈ nhận API key. Bản trước có thêm tham số `oauth_token` để gói Claude Code gọi thẳng
    endpoint này bằng access token mà CLI đã lưu; Anthropic cấm đúng việc đó nên đường ấy đã
    gỡ (xem claude_auth.py). Gói Claude Code nay đi qua binary `claude`, không qua đây.
    """
    sys_parts = [m.get("content", "") for m in messages if m.get("role") == "system"]
    conv = [{"role": m["role"], "content": m.get("content", "")}
            for m in messages if m.get("role") in ("user", "assistant")]
    headers = {"x-api-key": api_key, "anthropic-version": "2023-06-01",
               "content-type": "application/json"}
    payload = {"model": model or "claude-sonnet-4-6", "max_tokens": 4096, "messages": conv, "stream": True}
    payload.update(_anthropic_reasoning(model, reasoning))   # thinking + effort + max_tokens nếu bật reasoning
    sys_txt = "\n\n".join(s for s in sys_parts if s)
    if sys_txt:
        payload["system"] = sys_txt
    _apply_anthropic_cache(payload)   # system + 3 msg cuối được cache → giảm ~75% input cost
    try:
        timeout = httpx.Timeout(120.0, connect=15.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream("POST", ANTHROPIC_URL, headers=headers, json=payload) as r:
                if r.status_code != 200:
                    body = await r.aread()
                    body_text = body.decode("utf-8", "replace")
                    _fact = limit_learner.parse_limit_error(r.status_code, body_text)
                    if _fact:
                        limit_learner.remember("anthropic", model, _fact)
                        yield {"type": "limit_exceeded", "provider": "anthropic", "model": model,
                               "kind": _fact.kind, "limit": _fact.limit,
                               "requested": _fact.requested,
                               "shrink_to": limit_learner.shrink_target(_fact),
                           "remedy": _fact.remedy, "raw": _fact.raw}
                    yield ev_loi_http("Anthropic", r.status_code, body_text, r.headers, _fact)
                    return
                yield {"type": "meta", "model": model}
                got = False
                stop_reason = None
                usage_in = usage_out = 0
                async for line in r.aiter_lines():
                    line = (line or "").strip()
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if not data:
                        continue
                    try:
                        obj = json.loads(data)
                    except json.JSONDecodeError:
                        continue
                    t = obj.get("type")
                    if t == "message_start":
                        u = (obj.get("message") or {}).get("usage") or {}
                        usage_in = ((u.get("input_tokens") or 0) + (u.get("cache_read_input_tokens") or 0)
                                    + (u.get("cache_creation_input_tokens") or 0))
                    elif t == "content_block_delta":
                        txt = (obj.get("delta") or {}).get("text") or ""
                        if txt:
                            got = True
                            yield {"type": "text", "content": txt}
                    elif t == "message_delta":
                        sr = (obj.get("delta") or {}).get("stop_reason")
                        if sr:
                            stop_reason = sr
                        if (obj.get("usage") or {}).get("output_tokens"):
                            usage_out = obj["usage"]["output_tokens"]
                    elif t == "error":
                        yield {"type": "error", "content": f"Anthropic: {(obj.get('error') or {}).get('message', 'lỗi')}"}
                        return
                if usage_in or usage_out:
                    yield {"type": "usage", "input": usage_in, "output": usage_out}
                if not got:
                    yield {"type": "error", "content": f"Anthropic trả về rỗng (stop_reason={stop_reason}). Thử model khác trong Models."}
                    return
                # Stream xong nhưng KHÔNG phải end_turn/stop_sequence (max_tokens / refusal / ...) → báo user
                if stop_reason and stop_reason not in ("end_turn", "stop_sequence"):
                    notes = {
                        "max_tokens": "⚠️ Phản hồi bị cắt do hết max_tokens. Nhắn 'tiếp tục' để model viết tiếp.",
                        "refusal": "⚠️ Model từ chối phản hồi (refusal).",
                    }
                    yield {"type": "text", "content": "\n\n" + notes.get(stop_reason, f"⚠️ Stream kết thúc bất thường (stop_reason={stop_reason}).")}
    except Exception as e:
        yield ev_loi_exc("Anthropic lỗi", e)


async def single_tool_plan(provider, api_key, model, messages, reasoning, tool_spec):
    """Phase 6 planner: đúng một non-stream model call và đúng một tool call.

    Hàm chỉ trả arguments. Nó không dispatch tool, không retry, không chấp nhận câu trả lời text
    thay thế và không đưa nội dung lỗi provider vào runtime log.
    """
    fn = str(((tool_spec or {}).get("function") or {}).get("name") or "")
    params = ((tool_spec or {}).get("function") or {}).get("parameters")
    description = str(((tool_spec or {}).get("function") or {}).get("description") or fn)
    if not fn or not isinstance(params, dict):
        return {"status": "error", "error_code": "invalid_tool_spec", "input": 0, "output": 0}

    if provider == "anthropic-api":
        sys_parts = [str(m.get("content") or "") for m in messages if m.get("role") == "system"]
        conv = [{"role": m["role"], "content": m.get("content", "")}
                for m in messages if m.get("role") in ("user", "assistant")]
        payload = {
            "model": model or "claude-sonnet-4-6", "max_tokens": 2048,
            "messages": conv,
            "tools": [{"name": fn, "description": description[:1024], "input_schema": params}],
            "tool_choice": {
                "type": "tool", "name": fn, "disable_parallel_tool_use": True,
            },
            "stream": False,
        }
        if sys_parts:
            payload["system"] = "\n\n".join(x for x in sys_parts if x)
        headers = {
            "x-api-key": api_key, "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(120, connect=15)) as client:
                response = await client.post(ANTHROPIC_URL, headers=headers, json=payload)
            if response.status_code != 200:
                return {"status": "error", "error_code": f"provider_http_{response.status_code}",
                        "input": 0, "output": 0}
            data = response.json()
        except Exception as exc:
            return {"status": "error", "error_code": f"provider_exception:{type(exc).__name__}",
                    "input": 0, "output": 0}
        uses = [x for x in (data.get("content") or []) if x.get("type") == "tool_use"]
        usage = data.get("usage") or {}
        tokens_in = ((usage.get("input_tokens") or 0) +
                     (usage.get("cache_read_input_tokens") or 0) +
                     (usage.get("cache_creation_input_tokens") or 0))
        tokens_out = usage.get("output_tokens") or 0
        if len(uses) != 1 or uses[0].get("name") != fn or not isinstance(uses[0].get("input"), dict):
            return {"status": "error", "error_code": "tool_call_contract_violation",
                    "input": tokens_in, "output": tokens_out}
        return {"status": "ok", "arguments": uses[0]["input"], "name": fn,
                "model": data.get("model") or model, "input": tokens_in, "output": tokens_out}

    endpoints = {
        "openai": (OPENAI_URL, model or "gpt-4o-mini"),
        "groq": (GROQ_URL, model or GROQ_DEFAULT_MODEL),
        "gemini": (GEMINI_URL, model or "gemini-2.5-flash"),
        "openrouter": (OPENROUTER_URL, model or "openai/gpt-4o-mini"),
        "ollama": (OLLAMA_URL, model),
    }
    if provider not in endpoints:
        return {"status": "error", "error_code": "provider_not_supported", "input": 0, "output": 0}
    url, actual_model = endpoints[provider]
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    if provider == "openrouter":
        headers.update({"HTTP-Referer": "http://localhost:7777", "X-Title": "Javis OS"})
    payload = {
        "model": actual_model, "messages": list(messages), "tools": [tool_spec],
        "tool_choice": {"type": "function", "function": {"name": fn}},
        "parallel_tool_calls": False, "stream": False,
    }
    if reasoning not in (None, "", "off"):
        if provider == "openrouter":
            payload["reasoning"] = {"effort": api_effort(reasoning)}
        elif ((provider == "openai" and _openai_is_reasoning(model)) or
              (provider == "groq" and _groq_is_reasoning(model)) or
              (provider == "gemini" and _gemini_is_reasoning(model))):
            payload["reasoning_effort"] = api_effort(reasoning)
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(120, connect=15)) as client:
            response = await client.post(url, headers=headers, json=payload)
        if response.status_code != 200:
            return {"status": "error", "error_code": f"provider_http_{response.status_code}",
                    "input": 0, "output": 0}
        data = response.json()
    except Exception as exc:
        return {"status": "error", "error_code": f"provider_exception:{type(exc).__name__}",
                "input": 0, "output": 0}
    usage = data.get("usage") or {}
    tokens_in = usage.get("prompt_tokens") or 0
    tokens_out = usage.get("completion_tokens") or 0
    calls = (((data.get("choices") or [{}])[0].get("message") or {}).get("tool_calls") or [])
    if len(calls) != 1 or (calls[0].get("function") or {}).get("name") != fn:
        return {"status": "error", "error_code": "tool_call_contract_violation",
                "input": tokens_in, "output": tokens_out}
    raw_args = (calls[0].get("function") or {}).get("arguments")
    try:
        arguments = raw_args if isinstance(raw_args, dict) else json.loads(raw_args or "{}")
    except (json.JSONDecodeError, TypeError, ValueError):
        return {"status": "error", "error_code": "tool_arguments_not_json",
                "input": tokens_in, "output": tokens_out}
    if not isinstance(arguments, dict):
        return {"status": "error", "error_code": "tool_arguments_not_object",
                "input": tokens_in, "output": tokens_out}
    return {"status": "ok", "arguments": arguments, "name": fn,
            "model": data.get("model") or actual_model, "input": tokens_in, "output": tokens_out}


async def openrouter_stream(api_key, model, messages, reasoning="off"):
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "http://localhost:7777",
        "X-Title": "Javis OS",
    }
    if _is_claude_model(model):
        messages = _or_mark_system(messages)   # cache system ~26k cho model Claude qua OpenRouter
    payload = {"model": model or "openai/gpt-4o-mini", "messages": messages, "stream": True,
               "stream_options": {"include_usage": True}}   # → chunk cuối kèm usage token
    if reasoning not in (None, "", "off"):
        payload["reasoning"] = {"effort": api_effort(reasoning)}   # OpenRouter chuẩn hoá effort cho mọi model reasoning
    # Jittered retry - CHỈ cho transient (429/5xx hoặc network exception) và CHỈ khi chưa yield text.
    max_attempts = 3
    for attempt in range(1, max_attempts + 1):
        got_content = False
        scrubber = _ThinkScrubber()   # gỡ <think> inline; fresh mỗi attempt
        try:
            timeout = httpx.Timeout(120.0, connect=15.0)
            async with httpx.AsyncClient(timeout=timeout) as client:
                async with client.stream("POST", OPENROUTER_URL, headers=headers, json=payload) as r:
                    if r.status_code != 200:
                        body = await r.aread()
                        body_text = body.decode("utf-8", "replace")
                        _fact = limit_learner.parse_limit_error(r.status_code, body_text)
                        # Lỗi vượt KÍCH THƯỚC không phải lỗi tạm thời: thử lại y nguyên chỉ
                        # tốn thêm một lượt để nhận đúng lỗi đó. Phải co lại rồi mới thử.
                        retriable = (not _fact) and (
                            r.status_code in _RETRY_STATUS or _is_transient_body(body_text))
                        if retriable and attempt < max_attempts:
                            raise _RetryStream(_parse_retry_after(r.headers))
                        if _fact:
                            limit_learner.remember("openrouter", model, _fact)
                            yield {"type": "limit_exceeded", "provider": "openrouter",
                                   "model": model, "kind": _fact.kind, "limit": _fact.limit,
                                   "requested": _fact.requested,
                                   "shrink_to": limit_learner.shrink_target(_fact),
                           "remedy": _fact.remedy, "raw": _fact.raw}
                        yield {"type": "error", "content": f"OpenRouter {r.status_code}: {body_text[:300]}"}
                        return
                    sent_model = False
                    reasoning = ""
                    finish = None
                    usage = None
                    async for line in r.aiter_lines():
                        line = (line or "").strip()
                        if not line.startswith("data:"):
                            continue
                        data = line[5:].strip()
                        if data == "[DONE]":
                            break
                        try:
                            obj = json.loads(data)
                        except json.JSONDecodeError:
                            continue
                        if not sent_model and obj.get("model"):
                            sent_model = True
                            yield {"type": "meta", "model": obj["model"]}   # model THẬT OpenRouter tính tiền
                        if obj.get("usage"):
                            usage = obj["usage"]
                        ch = (obj.get("choices") or [{}])[0]
                        if ch.get("finish_reason"):
                            finish = ch["finish_reason"]
                        delta = ch.get("delta", {}) or {}
                        c = delta.get("content")
                        if c:
                            visible = _sanitize_surrogates(scrubber.feed(c))   # gỡ <think> inline + dọn lone surrogate
                            if visible:
                                got_content = True
                                yield {"type": "text", "content": visible}
                        else:
                            rc = delta.get("reasoning")   # model reasoning (deepseek-v4...) nhét chữ vào đây
                            if rc:
                                reasoning += rc
                    tail = _sanitize_surrogates(scrubber.flush())   # prose còn giữ lại cuối stream (không phải tag)
                    if tail:
                        got_content = True
                        yield {"type": "text", "content": tail}
                    # Không có content → fallback reasoning, hoặc báo lỗi rõ (KHÔNG để rỗng âm thầm)
                    if not got_content:
                        if reasoning.strip():
                            yield {"type": "text", "content": _sanitize_surrogates(reasoning.strip())}
                            got_content = True   # reasoning đã là nội dung - vẫn cần báo truncation phía dưới
                        else:
                            yield {"type": "error", "content": f"Model trả về rỗng (finish_reason={finish}). Thử lại hoặc đổi sang model khác trong Cài đặt."}
                            return
                    # Stream kết thúc nhưng KHÔNG phải 'stop' (length / content_filter / ...) → user cần biết phản hồi bị cắt
                    if finish and finish != "stop":
                        notes = {
                            "length": "⚠️ Phản hồi bị cắt do hết max_tokens. Nhắn 'tiếp tục' để model viết tiếp.",
                            "content_filter": "⚠️ Phản hồi bị lọc do bộ lọc nội dung.",
                        }
                        yield {"type": "text", "content": "\n\n" + notes.get(finish, f"⚠️ Stream kết thúc bất thường (finish_reason={finish}).")}
                    if usage:
                        yield {"type": "usage", "input": usage.get("prompt_tokens", 0), "output": usage.get("completion_tokens", 0)}
                    return  # success → thoát vòng retry
        except _RetryStream as rs:
            # Honor Retry-After provider gửi (429/503) - chính xác hơn đoán mò; thiếu thì jittered backoff
            await asyncio.sleep(rs.retry_after if rs.retry_after is not None else _jittered_backoff(attempt))
            continue
        except _RETRY_EXC as e:
            # Đã yield text → KHÔNG retry (tránh duplicate output); hết lượt → cũng fail-fast
            if got_content or attempt >= max_attempts:
                yield {"type": "error", "content": f"OpenRouter mạng lỗi: {_describe_exc(e)}"}
                return
            await asyncio.sleep(_jittered_backoff(attempt))
        except Exception as e:
            yield {"type": "error", "content": f"OpenRouter lỗi: {_describe_exc(e)}"}
            return


# ChatGPT OAuth (provider 'openai-oauth') - gọi backend Codex bằng token subscription.
CODEX_RESPONSES_URL = "https://chatgpt.com/backend-api/codex/responses"


def _codex_input(messages):
    """messages OpenAI-style → (instructions=system gộp, input=[message items] Responses API)."""
    instructions, inp = [], []
    for mm in messages:
        role = mm.get("role")
        content = mm.get("content", "") or ""
        if role == "system":
            instructions.append(content)
            continue
        ctype = "input_text" if role == "user" else "output_text"
        inp.append({"type": "message", "role": role, "content": [{"type": ctype, "text": content}]})
    return "\n\n".join(s for s in instructions if s), inp


async def openai_responses_stream(access_token, account_id, model, messages, reasoning="off"):
    """Chat qua gói ChatGPT (OAuth) - backend Codex Responses API. Model: gpt-5-codex / gpt-5."""
    if not access_token:
        yield {"type": "error", "content": "Chưa đăng nhập ChatGPT (OAuth). Vào Models để kết nối."}
        return
    import uuid
    instructions, inp = _codex_input(messages)
    payload = {"model": model or "gpt-5.5", "instructions": instructions, "input": inp,
               "stream": True, "store": False}
    if reasoning not in (None, "", "off"):
        payload["reasoning"] = {"effort": api_effort(reasoning)}
    headers = {
        "Authorization": f"Bearer {access_token}",
        "chatgpt-account-id": account_id or "",
        "OpenAI-Beta": "responses=experimental",
        "originator": "codex_cli_rs",
        "session_id": str(uuid.uuid4()),
        "Content-Type": "application/json",
        "Accept": "text/event-stream",
        "User-Agent": "javis-os/0.3 (codex)",
    }
    if not (account_id or ""):
        headers.pop("chatgpt-account-id", None)
    try:
        timeout = httpx.Timeout(180.0, connect=15.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream("POST", CODEX_RESPONSES_URL, headers=headers, json=payload) as r:
                if r.status_code != 200:
                    body = await r.aread()
                    body_text = body.decode("utf-8", "replace")
                    _fact = limit_learner.parse_limit_error(r.status_code, body_text)
                    if _fact:
                        limit_learner.remember("openai-oauth", model, _fact)
                        yield {"type": "limit_exceeded", "provider": "ChatGPT", "model": model,
                               "kind": _fact.kind, "limit": _fact.limit,
                               "requested": _fact.requested,
                               "shrink_to": limit_learner.shrink_target(_fact),
                           "remedy": _fact.remedy, "raw": _fact.raw}
                    yield ev_loi_http("ChatGPT", r.status_code, body_text, r.headers, _fact, cat=400)
                    return
                yield {"type": "meta", "model": model or "gpt-5-codex"}
                got = False
                usage = None
                async for line in r.aiter_lines():
                    line = (line or "").strip()
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if not data or data == "[DONE]":
                        if data == "[DONE]":
                            break
                        continue
                    try:
                        obj = json.loads(data)
                    except json.JSONDecodeError:
                        continue
                    et = obj.get("type")
                    if et == "response.output_text.delta":
                        # Đường tắt của gói ChatGPT đi qua đây, và nó cũng phát dấu trích dẫn
                        # nội bộ như Codex CLI. Bóc ngay tại nguồn: một mẩu delta có thể chỉ
                        # chứa mảnh vụn của dấu, nên hàm bóc quét cả vùng ký tự chứ không chỉ
                        # khối trọn vẹn.
                        d = strip_provider_markers(obj.get("delta") or "")
                        if d:
                            got = True
                            yield {"type": "text", "content": d}
                    elif et == "response.completed":
                        usage = ((obj.get("response") or {}).get("usage")) or usage
                    elif et in ("response.failed", "error", "response.error"):
                        err = (obj.get("response") or {}).get("error") or obj.get("error") or {}
                        msg = err.get("message") if isinstance(err, dict) else str(err)
                        yield {"type": "error", "content": "ChatGPT: " + (msg or "lỗi")}
                        return
                if usage:
                    yield {"type": "usage", "input": usage.get("input_tokens", 0), "output": usage.get("output_tokens", 0)}
                if not got:
                    yield {"type": "error", "content": "ChatGPT trả về rỗng. Kiểm tra gói Plus/Pro hoặc thử lại."}
    except Exception as e:
        yield ev_loi_exc("ChatGPT OAuth lỗi", e)


# ============================================================
# MCP đa-model - vòng tool-calling để model API/OAuth dùng MCP của Javis (qua mcp_client)
# ============================================================
def _clip_tool_result(result, max_chars: int = 8000, head_ratio: float = 0.6) -> str:
    """Cắt kết quả tool quá dài kiểu head+tail KÈM marker, thay cho hard-cut `[:max]`.
    Tail của kết quả MCP (POS/Ads) hay chứa total/summary/pagination → cắt cụt đầu là
    mất phần đó âm thầm. Giữ đầu + cuối + dòng báo bỏ bao nhiêu → model thấy cả hai mép
    và BIẾT data bị thiếu (không tưởng đủ rồi báo sai). Port head+tail của Hermes
    code_execution_tool."""
    text = str(result)
    if len(text) <= max_chars:
        return text
    head_n = int(max_chars * head_ratio)
    tail_n = max_chars - head_n
    omitted = len(text) - head_n - tail_n
    return (text[:head_n]
            + f"\n\n… [KẾT QUẢ TOOL BỊ CẮT - bỏ {omitted:,} ký tự giữa / tổng {len(text):,}] …\n\n"
            + text[-tail_n:])


def _mcp_to_openai_tools(mcp_tools):
    return [{"type": "function", "function": {
        "name": t["fn"], "description": (t.get("description") or t["fn"])[:1024],
        "parameters": t.get("schema") or {"type": "object", "properties": {}},
    }} for t in mcp_tools]


def _plain_vn(text):
    """Chuẩn hoá nhẹ để nhận intent tiếng Việt có/không dấu."""
    import unicodedata
    s = unicodedata.normalize("NFD", str(text or "").lower())
    return "".join(c for c in s if unicodedata.category(c) != "Mn").replace("đ", "d")


def _schedule_intent_text(messages, max_chars=600):
    """Lấy phần user thực sự ra lệnh, bỏ marker file và từ chối suy diễn từ bài quá dài.

    Gateway lịch chạy trước model và có quyền xoá dữ liệu. Vì vậy nó chỉ nên nhận câu lệnh
    ngắn, trực tiếp; bài viết/prompt dài có thể tình cờ chứa cả "dùng", "tất cả", "nhắc",
    "lịch"... nhưng không phải lệnh thao tác lịch.
    """
    last = next((m.get("content") or "" for m in reversed(messages or [])
                 if m.get("role") == "user"), "")
    text = str(last or "").strip()

    # Dashboard đặt marker file nhiều dòng trước caption; Telegram đặt marker tải file ở
    # dòng đầu. Control text không phải lời user và không được tham gia nhận diện mutation.
    if text.startswith("[File đính kèm"):
        marker_end = text.find("]\n\n")
        if marker_end >= 0:
            text = text[marker_end + 3:].strip()
    elif text.startswith("[Người dùng gửi"):
        marker_end = text.find("]\n")
        if marker_end >= 0:
            text = text[marker_end + 2:].strip()

    if not text or len(text) > max_chars:
        return None
    return text


_SCHEDULE_CANCEL_VERB_RE = re.compile(
    r"\b(?:hủy|huỷ|huy|xóa|xoá|xoa|gỡ|go|tắt|tat|dừng|dung|bỏ|bo)\b",
    re.IGNORECASE,
)


def _has_schedule_cancel_verb(text):
    """Giữ dấu để không đánh đồng dừng/dùng, tắt/tất, gỡ/gõ."""
    return bool(_SCHEDULE_CANCEL_VERB_RE.search(str(text or "")))


def _direct_schedule_cancel_request(messages):
    """Chỉ nhận câu huỷ lịch có động từ mệnh lệnh ở đầu phần user nhập."""
    text = _schedule_intent_text(messages)
    if text is None:
        return None, None

    # Các tiền tố hội thoại/phép lịch sự thường gặp trước động từ chính.
    lead = (
        r"^\s*(?:(?:javis|em|bạn|ban|ơi|oi|hãy|hay|please)\b[\s,;:!\-]*"
        r"|(?:vui\s+lòng|vui\s+long|làm\s+ơn|lam\s+on)\b[\s,;:!\-]*"
        r"|(?:giúp|giup|nhờ|nho)\s*(?:anh|em|tôi|toi|mình|minh)?\b[\s,;:!\-]*"
        r"|cho\s+(?:anh|em|tôi|toi|mình|minh)\b[\s,;:!\-]*"
        r"|(?:anh|tôi|toi|mình|minh)\s+(?:muốn|muon|cần|can)\b[\s,;:!\-]*)*"
    )
    match = re.match(lead + _SCHEDULE_CANCEL_VERB_RE.pattern, text, re.IGNORECASE)
    if not match:
        return text, None

    # "dung huy..." không dấu thường là "đừng huỷ", không phải "dừng lịch".
    command_plain = _plain_vn(text[match.start():])
    if re.match(r"^dung\s+(?:huy|xoa|go|tat|dung|bo)\b", command_plain):
        return text, None
    return text, match


def _tool_requirement(messages, mcp_tools):
    """Tool phải gọi ở vòng đầu cho câu hỏi cần dữ liệu sống; None nếu chat kiến thức thuần."""
    names = {t.get("fn") for t in (mcp_tools or [])}
    last = next((m.get("content") or "" for m in reversed(messages or [])
                 if m.get("role") == "user"), "")
    q = _plain_vn(last)
    action = any(x in q for x in (
        "kiem tra", "check", "xem", "doc", "liet ke", "tim", "lay", "dang chay",
        "hien co", "hom nay", "con ", "tao", "dat", "them", "huy", "xoa", "go ",
        "tat", "dung", "bat", "sua", "doi",
    ))
    schedule_text = _schedule_intent_text(messages)
    if schedule_text is not None:
        schedule_q = _plain_vn(schedule_text)
        schedule_action = any(x in schedule_q for x in (
            "kiem tra", "check", "xem", "doc", "liet ke", "tim", "lay", "dang chay",
            "hien co", "hom nay", "con ", "tao", "dat", "them", "huy", "xoa",
            "bat", "sua", "doi",
        )) or _has_schedule_cancel_verb(schedule_text)
        schedule = any(x in schedule_q for x in (
            "cron", "nhac", "nhac hen", "nhac thuoc", "lich thuoc", "lich nhac", "uong thuoc",
            "viec dinh ky", "morning briefing", "reminder",
        ))
        if schedule_action and schedule and "javis_schedule" in names:
            # Phân loại theo ý định đã siết chặt thay vì chỉ dựa vào việc câu có chữ "lịch/nhắc".
            # Nhờ vậy câu bàn về "đặt lịch tư vấn 1-1 có ổn không?" không bị ép function-call.
            if (
                _schedule_read_request(messages)
                or _schedule_create_request(messages)
                or _schedule_cancel_request(messages)
            ):
                return "javis_schedule"

    live_source = any(x in q for x in (
        "google", "gmail", "drive", "calendar", "keep", "task", "mcp", "pos",
        "don hang", "doanh thu", "ton kho", "lich dang chay", "du lieu hien tai",
    ))
    if action and live_source and names:
        return "required"
    return None


def _schedule_read_request(messages):
    """Câu hỏi chỉ-đọc lịch có thể dispatch thẳng, không phụ thuộc model biết function calling."""
    last = _schedule_intent_text(messages)
    if last is None:
        return False
    q = _plain_vn(last)
    conceptual = any(x in q for x in (
        "co nen", "nen ", "lieu ", "y kien", "the nao", "co ok khong", "co on khong",
        "hop ly khong", "thay bang", "tu van", "booking", "phuong an",
    ))
    if conceptual:
        return False
    read = any(x in q for x in (
        "kiem tra", "check", "xem", "doc", "liet ke", "dang chay", "hien co", "hom nay", "con ",
    ))
    mutate = any(x in q for x in (
        "tao", "dat", "them", "huy", "xoa", "bat", "sua", "doi",
    )) or _has_schedule_cancel_verb(last)
    schedule = any(x in q for x in (
        "cron", "nhac", "lich thuoc", "lich nhac", "viec dinh ky", "reminder",
        "morning briefing", "viec gi dang chay",
    ))
    return read and schedule and not mutate


def _schedule_create_request(messages):
    """Chỉ nhận lệnh TẠO reminder/cron trực tiếp, không nhận câu đang bàn về khái niệm "đặt lịch".

    ``javis_schedule`` là lịch tự động nội bộ của Javis, khác booking/cuộc hẹn/Calendar. Model có
    thể chủ động function-call ngay cả khi gateway không ép tool, nên điều kiện này còn được dùng
    làm cổng chặn trước mọi lần thực thi tool.
    """
    last = _schedule_intent_text(messages)
    if last is None:
        return False
    q = _plain_vn(last)

    # Các câu hỏi/đề xuất UX, bán hàng, booking hay tư vấn chỉ cần trả lời bằng hội thoại.
    conceptual = any(x in q for x in (
        "co ok khong", "co on khong", "lieu ", "nen ", "thay bang", "y kien",
        "tu van 1-1", "tu van 1:1", "booking", "dat lich tu van",
        "gia tri uu tien", "hoi dap", "phuong an",
    ))
    external_calendar = any(x in q for x in (
        "google calendar", "outlook calendar", "cuoc hop", "meeting", "su kien", "event",
    ))
    if conceptual or external_calendar or "?" in last:
        return False

    # Chỉ chấp nhận động từ mệnh lệnh ở đầu câu, sau vài tiền tố lịch sự thường gặp.
    lead = (
        r"^\s*(?:(?:javis|em|ban|oi|hay|please)\b[\s,;:!\-]*"
        r"|(?:vui\s+long|lam\s+on)\b[\s,;:!\-]*"
        r"|(?:giup|nho)\s*(?:anh|em|toi|minh)?\b[\s,;:!\-]*"
        r"|cho\s+(?:anh|em|toi|minh)\b[\s,;:!\-]*"
        r"|(?:anh|toi|minh)\s+(?:muon|can)\b[\s,;:!\-]*)*"
    )
    command = re.match(lead + r"(?:tao|dat|them|len\s+lich|nhac)\b", q, re.IGNORECASE)
    time_first_command = re.match(
        r"^\s*(?:\d{1,3}\s*(?:phut|gio)\s+nua|\d{1,2}\s*h(?:\d{1,2})?\b.*?)\s+nhac\b",
        q,
        re.IGNORECASE,
    )
    if not command and not time_first_command:
        return False

    # Một lệnh reminder thật phải có ngữ nghĩa tự động/định kỳ hoặc một mốc thời gian cụ thể.
    schedule_semantics = any(x in q for x in (
        "cron", "nhac", "reminder", "viec dinh ky", "moi ", "hang ngay", "hang tuan",
        "phut nua", "gio nua", "ngay mai", "sang mai", "chieu mai", "toi mai",
    ))
    time_semantics = bool(re.search(
        r"(?:\b\d{1,2}\s*(?:h|gio|phut|ngay)\b|\bluc\s+\d{1,2}\b|"
        r"\b(?:sang|trua|chieu|toi)\b)",
        q,
    ))
    return schedule_semantics or time_semantics


def _schedule_cancel_request(messages):
    """Nhận diện yêu cầu huỷ/xoá lịch, không nhầm với câu chỉ hỏi hoặc lịch ngoài Javis."""
    last, command = _direct_schedule_cancel_request(messages)
    if last is None or command is None:
        return False
    q = _plain_vn(last[command.end():])
    explicit_schedule = any(x in q for x in (
        "cron", "nhac", "lich thuoc", "lich nhac", "viec dinh ky",
        "morning briefing", "reminder", "vua bao",
    )) or bool(re.search(r"\bhen\b", q))
    # Người dùng thường nói gọn "huỷ lịch Làm việc tại cafe", không nhắc lại chữ cron/reminder.
    # Trước đây câu này lọt khỏi gateway, model tự đoán DELETE/JSON rồi có thể sửa thẳng
    # reminders.json. Chỉ nhận chữ "lịch" độc lập và tránh lịch ngoài Javis (Google Calendar,
    # cuộc họp/sự kiện) để không cướp yêu cầu của tool Calendar.
    plain_schedule = bool(re.search(r"\blich\b", q))
    external_calendar = any(x in q for x in (
        "google calendar", "outlook calendar", "cuoc hop", "meeting", "su kien", "event",
    ))
    return not external_calendar and (explicit_schedule or plain_schedule)


def _schedule_tool_allowed(messages, name, args):
    """Rào cuối: model không được tự ý đọc/sửa lịch khi user chỉ nhắc tới chữ "lịch"."""
    if name != "javis_schedule":
        return True
    op = str((args or {}).get("op") or "").strip().lower()
    if op == "list":
        return (
            _schedule_read_request(messages)
            or _schedule_create_request(messages)
            or _schedule_cancel_request(messages)
        )
    if op == "create":
        return _schedule_create_request(messages)
    if op == "cancel":
        return _schedule_cancel_request(messages)
    return False


def _schedule_tool_blocked_result():
    return (
        "BỊ CHẶN: user chỉ đang hỏi hoặc thảo luận về việc đặt lịch, không yêu cầu đọc hay thay đổi "
        "lịch tự động của Javis. Hãy trả lời trực tiếp câu hỏi; không liệt kê cron/reminder và không "
        "khẳng định đã tạo, sửa hoặc huỷ lịch."
    )


def _schedule_candidates(result):
    """Đọc các dòng ``- [id] tên - ...`` do javis_schedule(op=list) trả về."""
    out = []
    for line in str(result or "").splitlines():
        match = re.match(r"^\s*-\s*\[([^\]]+)\]\s*(.+?)\s*$", line)
        if not match:
            continue
        item_id = match.group(1).strip()
        label = match.group(2).split(" - ", 1)[0].strip()
        if item_id and label:
            out.append((item_id, label))
    return out


def _resolve_schedule_cancel_id(messages, list_result):
    """Chọn id chỉ khi khớp chắc chắn; mơ hồ thì trả None để hỏi lại."""
    last = next((m.get("content") or "" for m in reversed(messages or [])
                 if m.get("role") == "user"), "")
    q = _plain_vn(last)
    candidates = _schedule_candidates(list_result)
    if not candidates:
        return None

    # ID được nói thẳng là bằng chứng mạnh nhất.
    for item_id, _label in candidates:
        if re.search(rf"(?<![\w-]){re.escape(_plain_vn(item_id))}(?![\w-])", q):
            return item_id

    # Chỉ có đúng một lịch đang chạy thì "xoá cron/nhắc này" không thể nhầm.
    if len(candidates) == 1:
        return candidates[0][0]

    stop = {
        "anh", "em", "giup", "cho", "cai", "nay", "do", "vua", "bao", "di", "voi",
        "huy", "xoa", "go", "tat", "dung", "bo", "cron", "lich", "nhac", "hen",
        "viec", "dinh", "ky", "reminder", "morning", "briefing",
    }
    query_tokens = {t for t in re.findall(r"\w+", q) if len(t) > 1 and t not in stop}
    if not query_tokens:
        return None

    scored = []
    for item_id, label in candidates:
        label_norm = _plain_vn(label)
        label_tokens = set(re.findall(r"\w+", label_norm))
        overlap = len(query_tokens & label_tokens)
        exact_phrase = bool(label_norm and label_norm in q)
        scored.append((100 if exact_phrase else overlap, item_id))
    scored.sort(reverse=True)
    best_score, best_id = scored[0]
    second_score = scored[1][0] if len(scored) > 1 else -1
    if best_score >= 100 or (best_score >= 2 and best_score > second_score):
        return best_id
    return None


async def schedule_cancel_gateway(messages, mcp_tools, mcp_route):
    """Huỷ lịch ở tầng gateway để không phụ thuộc model có function-calling hay không.

    Chỉ tự huỷ khi ID khớp chắc chắn. Nếu có nhiều ứng viên mơ hồ, trả danh sách thật
    để kênh chat hỏi lại thay vì đoán hoặc bảo người dùng tự vào UI.
    """
    if not _schedule_cancel_request(messages):
        return None
    names = {t.get("fn") for t in (mcp_tools or [])}
    if "javis_schedule" not in names:
        return {
            "handled": False,
            "error": "javis_schedule không có trong MCP của phiên",
            "calls": [],
        }
    import mcp_client
    listed = await mcp_client.call_route(mcp_route, "javis_schedule", {"op": "list"})
    listed = _clip_tool_result(listed)
    if listed.startswith("ERROR:"):
        return {"handled": False, "error": listed, "calls": ["javis_schedule:list"]}
    if not _schedule_candidates(listed):
        return {
            "handled": False,
            "not_found": True,
            "list_result": listed,
            "calls": ["javis_schedule:list"],
        }
    item_id = _resolve_schedule_cancel_id(messages, listed)
    if not item_id:
        return {
            "handled": False,
            "needs_choice": True,
            "list_result": listed,
            "calls": ["javis_schedule:list"],
        }
    cancelled = await mcp_client.call_route(
        mcp_route, "javis_schedule", {"op": "cancel", "id": item_id}
    )
    cancelled = _clip_tool_result(cancelled)
    return {
        "handled": not cancelled.startswith("ERROR:"),
        "error": cancelled if cancelled.startswith("ERROR:") else "",
        "result": cancelled,
        "id": item_id,
        "calls": ["javis_schedule:list", "javis_schedule:cancel"],
    }


async def _cc_tool_loop(url, headers, model, messages, mcp_tools, mcp_route, reasoning_extra, label,
                        cache_system=False):
    """Vòng Chat Completions + tool (OpenAI/OpenRouter). Non-stream từng vòng; yield tool_call + text cuối.
    cache_system=True (OpenRouter + model Claude): đánh cache_control lên system - OpenAI/Gemini
    tự cache nên không cần."""
    import mcp_client
    tools = _mcp_to_openai_tools(mcp_tools)
    msgs = _or_mark_system(messages) if cache_system else list(messages)
    usage_in = usage_out = 0
    # Chỉ chờ cửa sổ hạn mức MỘT lần mỗi lượt: chờ hai lần là người dùng ngồi nhìn màn hình
    # đứng im nửa phút mà không hiểu chuyện gì.
    waited_for_window = False
    # Số lần model bịa sai cú pháp gọi tool. 0 -> thử lại; 1 -> bỏ tool; 2 -> chịu, báo lỗi.
    tool_fumbles = 0
    requirement = _tool_requirement(messages, mcp_tools)
    requirement_pending = bool(requirement)
    ignored_required = 0
    cancel_gate = await schedule_cancel_gateway(messages, mcp_tools, mcp_route)
    if cancel_gate:
        for call in cancel_gate.get("calls") or []:
            yield {"type": "tool_call", "name": call}
        if cancel_gate.get("error"):
            yield {"type": "error", "content": cancel_gate["error"]}
            return
        if cancel_gate.get("handled"):
            msgs.append({
                "role": "system",
                "content": (
                    "Javis gateway đã thao tác lịch bằng dữ liệu thật. Xác nhận ngắn gọn kết quả sau, "
                    "không nói rằng thiếu tool:\n\n" + cancel_gate.get("result", "")
                ),
            })
            requirement_pending = False
        elif cancel_gate.get("not_found"):
            msgs.append({
                "role": "system",
                "content": (
                    "Javis đã đọc kho lịch thật và không có lịch đang chạy để xoá. "
                    "Báo đúng kết quả này, không nói thiếu tool:\n\n"
                    + cancel_gate.get("list_result", "")
                ),
            })
            requirement_pending = False
        elif cancel_gate.get("needs_choice"):
            msgs.append({
                "role": "system",
                "content": (
                    "Javis đã đọc danh sách lịch thật nhưng có nhiều mục và chưa đủ chắc chắn để xoá. "
                    "Hãy hỏi user chọn đúng tên hoặc ID trong danh sách dưới đây; KHÔNG nói thiếu tool "
                    "và KHÔNG xác nhận đã xoá:\n\n" + cancel_gate.get("list_result", "")
                ),
            })
            requirement_pending = False
    # Đây là đường quan trọng nhất của cron/lịch thuốc: op=list là read-only và args xác định hoàn
    # toàn, nên server tự dispatch trước. OpenRouter/free dù route tới model không có function calling
    # vẫn nhận dữ liệu thật để tóm tắt, thay vì rơi về memory hoặc nói "không có tool".
    if requirement == "javis_schedule" and _schedule_read_request(messages):
        yield {"type": "tool_call", "name": "javis_schedule"}
        result = await mcp_client.call_route(mcp_route, "javis_schedule", {"op": "list"})
        clipped = _clip_tool_result(result)
        if clipped.startswith("ERROR:"):
            yield {"type": "error", "content": clipped}
            return
        msgs.append({
            "role": "system",
            "content": (
                "DỮ LIỆU THẬT vừa đọc bằng javis_schedule(op=list). Trả lời dựa trên dữ liệu này, "
                "không dùng memory để thay thế:\n\n" + clipped
            ),
        })
        requirement_pending = False
    for _ in range(_max_tool_rounds()):
        payload = {"model": model, "messages": msgs, "stream": False}
        # Bỏ hẳn khoá "tools" khi rỗng: vài endpoint OpenAI-compat từ chối mảng rỗng, và
        # nhánh cứu hộ ở dưới (model vấp cú pháp gọi tool) dựa vào đúng chỗ này.
        if tools:
            payload["tools"] = tools
        if requirement_pending and tools:
            payload["tool_choice"] = (
                {"type": "function", "function": {"name": requirement}}
                if requirement != "required" else "required"
            )
        payload.update(reasoning_extra or {})
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(180, connect=15)) as client:
                r = await client.post(url, headers=headers, json=payload)
                # Một số endpoint OpenAI-compatible chỉ nhận "required", không nhận named choice.
                if (r.status_code in (400, 422) and requirement_pending
                        and requirement not in (None, "required")):
                    payload["tool_choice"] = "required"
                    r = await client.post(url, headers=headers, json=payload)
            if r.status_code != 200:
                body_text = r.text or ""
                # Model YẾU tự bịa cú pháp gọi tool (Llama hay phát
                # "<function=ten{...}</function>" thay vì JSON tool_calls chuẩn), provider
                # trả 400 tool_use_failed. Đây KHÔNG phải lỗi của người dùng và cũng không
                # phải lỗi hạn mức - model chỉ vấp một lần. Hai nấc gỡ:
                #   1. Thử lại y nguyên: sinh chữ là ngẫu nhiên, lần sau thường trúng.
                #   2. Vẫn hỏng thì BỎ TOOL và hỏi lại, để model ít nhất trả lời bằng lời.
                # Trả lời thiếu tool vẫn hơn hẳn ném JSON lỗi ra rồi im lặng, mà "(không có
                # nội dung trả về)" chính là thứ người dùng đang thấy.
                if _is_tool_syntax_failure(body_text) and tool_fumbles < 2:
                    tool_fumbles += 1
                    if tool_fumbles == 2:
                        tools = []          # nấc 2: bỏ hẳn tool, cứu lấy câu trả lời
                        # Còn ép gọi một tool vừa bị gỡ thì request sau lại 400 ngay.
                        requirement_pending = False
                        yield {"type": "tool_call", "name": "javis_no_tools",
                               "content": "⚙ Model vấp cú pháp gọi công cụ, trả lời không dùng công cụ..."}
                    continue
                _fact = limit_learner.parse_limit_error(r.status_code, body_text)
                if _fact:
                    limit_learner.remember(label, model, _fact)
                    # CỬA SỔ ĐẦY thì co nhỏ gần như vô ích: lượt này đã vừa hạn mức rồi, chỉ
                    # là các lượt TRƯỚC chưa trôi qua. Việc đúng là chờ, và nhà cung cấp đã
                    # nói chờ bao lâu. Chờ vài giây rồi trả lời được vẫn hơn hẳn ném lỗi.
                    if (_fact.remedy == "wait" and _fact.retry_after
                            and _fact.retry_after <= _WINDOW_WAIT_MAX
                            and not waited_for_window):
                        waited_for_window = True
                        yield {"type": "tool_call", "name": "javis_wait_quota",
                               "content": (f"⚙ Hạn mức phút này đã đầy, chờ "
                                           f"{_fact.retry_after:.0f}s rồi thử lại...")}
                        await asyncio.sleep(_fact.retry_after + 0.5)
                        continue
                    yield {"type": "limit_exceeded", "provider": label, "model": model,
                           "kind": _fact.kind, "limit": _fact.limit,
                           "requested": _fact.requested, "used": _fact.used,
                           "window_full": _fact.window_full,
                           "retry_after": _fact.retry_after,
                           "shrink_to": limit_learner.shrink_target(_fact),
                           "remedy": _fact.remedy, "raw": _fact.raw}
                yield ev_loi_http(label, r.status_code, body_text, r.headers, _fact)
                return
            data = r.json()
        except Exception as e:
            yield ev_loi_exc(f"{label} lỗi", e)
            return
        u = data.get("usage") or {}   # cộng dồn token mọi vòng (kể cả vòng gọi tool)
        usage_in += u.get("prompt_tokens", 0) or 0
        usage_out += u.get("completion_tokens", 0) or 0
        msg = ((data.get("choices") or [{}])[0]).get("message") or {}
        tcs = msg.get("tool_calls") or []
        if tcs:
            requirement_pending = False
            msgs.append({"role": "assistant", "content": msg.get("content") or "", "tool_calls": tcs})
            for tc in tcs:
                fn = (tc.get("function") or {}).get("name")
                try:
                    args = json.loads((tc.get("function") or {}).get("arguments") or "{}")
                except json.JSONDecodeError:
                    args = {}
                if _schedule_tool_allowed(messages, fn, args):
                    yield {"type": "tool_call", "name": fn}
                    result = await mcp_client.call_route(mcp_route, fn, args)
                else:
                    result = _schedule_tool_blocked_result()
                msgs.append({"role": "tool", "tool_call_id": tc.get("id"), "content": _clip_tool_result(result)})
            continue
        content = msg.get("content") or ""
        if requirement_pending:
            ignored_required += 1
            if ignored_required < 2:
                msgs.append({
                    "role": "system",
                    "content": (
                        "Yêu cầu này cần dữ liệu đang chạy. BẮT BUỘC gọi tool được cung cấp ngay bây giờ; "
                        "không trả lời từ memory, không tự nhận là không có tool."
                    ),
                })
                continue
            yield {
                "type": "error",
                "content": (
                    f"{label} model '{model}' đã bỏ qua tool bắt buộc nên Javis không dùng câu trả lời "
                    "có nguy cơ bịa dữ liệu. Hãy chọn model có hỗ trợ tool/function calling."
                ),
            }
            return
        if usage_in or usage_out:
            yield {"type": "usage", "input": usage_in, "output": usage_out}
        if content:
            yield {"type": "text", "content": content}
        else:
            yield {"type": "error", "content": f"{label} trả về rỗng."}
        return
    yield {"type": "text", "content": _het_vong_msg()}


# ── Trần số vòng gọi tool của engine API (Claude Code/Codex tự quản vòng lặp của chúng) ──
# Mỗi vòng = một lượt gọi model + chạy tool nó xin. Có trần vì model kẹt vòng lặp sẽ đốt
# token vô hạn mà không ai thấy. 8 đủ cho gần hết câu hỏi thường ngày, nhưng một việc nền
# nhiều bước (đọc vài file, tra vài nguồn, ghi vài file) thì chạm trần rồi dừng giữa chừng.
# Nên nó là BIẾN MÔI TRƯỜNG, không phải số ghim trong ba chỗ khác nhau như trước.
def _max_tool_rounds() -> int:
    try:
        n = int(os.getenv("JAVIS_MAX_TOOL_ROUNDS", "8"))
    except (TypeError, ValueError):
        return 8
    return max(1, min(n, 40))   # kẹp: 0 thì không tool nào chạy, quá to thì mất ý nghĩa của trần


def _het_vong_msg() -> str:
    """Chạm trần phải nói ĐƯỢC VIỆC CẦN LÀM. Bản cũ chỉ báo con số rồi im, người dùng không
    biết mình vừa mất gì hay chỉnh ở đâu."""
    n = _max_tool_rounds()
    return (f"\n\n⚠ Đã chạy hết {n} vòng gọi tool cho lượt này nên phải dừng, câu trả lời ở "
            f"trên có thể còn dở. Cách xử lý: chia nhỏ yêu cầu thành từng bước, hoặc nâng trần "
            f"bằng biến môi trường JAVIS_MAX_TOOL_ROUNDS (tối đa 40) rồi khởi động lại Javis.")


async def openai_chat_with_mcp(api_key, model, messages, reasoning, mcp_tools, mcp_route):
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    extra = {}
    if reasoning not in (None, "", "off") and _openai_is_reasoning(model):
        extra["reasoning_effort"] = api_effort(reasoning)
    yield {"type": "meta", "model": model}
    async for ev in _cc_tool_loop(OPENAI_URL, headers, model or "gpt-4o-mini", messages, mcp_tools, mcp_route, extra, "OpenAI"):
        yield ev


async def groq_chat_with_mcp(api_key, model, messages, reasoning, mcp_tools, mcp_route):
    """Groq (endpoint OpenAI-compat) + vòng tool-calling MCP - Groq cũng là agent đủ đồ nghề
    của Javis y như OpenAI/Gemini. Non-stream từng vòng (dùng _cc_tool_loop chung)."""
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    extra = {}
    if reasoning not in (None, "", "off") and _groq_is_reasoning(model):
        extra["reasoning_effort"] = api_effort(reasoning)
    yield {"type": "meta", "model": model}
    async for ev in _cc_tool_loop(GROQ_URL, headers, model or GROQ_DEFAULT_MODEL, messages, mcp_tools, mcp_route, extra, "Groq"):
        yield ev


async def ollama_chat_with_mcp(api_key, model, messages, reasoning, mcp_tools, mcp_route):
    """Ollama Cloud + vòng tool-calling MCP - cũng là agent đủ đồ nghề của Javis y như các
    provider API khác, miễn model biết gọi tool (gpt-oss, qwen3-coder, deepseek... đều biết)."""
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    yield {"type": "meta", "model": model}
    async for ev in _cc_tool_loop(OLLAMA_URL, headers, model, messages,
                                  mcp_tools, mcp_route, {}, "Ollama"):
        yield ev


async def gemini_chat_with_mcp(api_key, model, messages, reasoning, mcp_tools, mcp_route):
    """Google Gemini (endpoint OpenAI-compat) + vòng tool-calling MCP - Gemini cũng thành
    agent dùng MCP của Javis, y như OpenAI. Non-stream từng vòng (dùng _cc_tool_loop chung)."""
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    extra = {}
    if reasoning not in (None, "", "off") and _gemini_is_reasoning(model):
        extra["reasoning_effort"] = api_effort(reasoning)
    yield {"type": "meta", "model": model}
    async for ev in _cc_tool_loop(GEMINI_URL, headers, model or "gemini-2.5-flash", messages, mcp_tools, mcp_route, extra, "Gemini"):
        yield ev


async def openrouter_chat_with_mcp(api_key, model, messages, reasoning, mcp_tools, mcp_route):
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json",
               "HTTP-Referer": "http://localhost:7777", "X-Title": "Javis OS"}
    extra = {}
    if reasoning not in (None, "", "off"):
        extra["reasoning"] = {"effort": api_effort(reasoning)}
    yield {"type": "meta", "model": model}
    async for ev in _cc_tool_loop(OPENROUTER_URL, headers, model or "openai/gpt-4o-mini", messages, mcp_tools, mcp_route, extra, "OpenRouter",
                                  cache_system=_is_claude_model(model)):
        yield ev


async def responses_with_mcp(access_token, account_id, model, messages, reasoning, mcp_tools, mcp_route):
    """ChatGPT OAuth (Codex Responses API) + tool MCP. EXPERIMENTAL (backend Codex).

    "EXPERIMENTAL" ở đây KHÔNG phải lời rào đón: tới 0.24.0 hàm này chưa từng được gọi từ đâu
    cả, và lần đầu có người gọi thật (bot chuyên trách mức Được ghi) thì nó trả rỗng ngay. Chỗ
    gọi phải coi "rỗng" là một kết cục CÓ THẬT và có đường lui, đừng coi là chuyện hiếm.
    """
    import uuid
    import mcp_client
    if not access_token:
        yield {"type": "error", "content": "Chưa đăng nhập ChatGPT (OAuth)."}
        return
    tools = [{"type": "function", "name": t["fn"], "description": (t.get("description") or t["fn"])[:1024],
              "parameters": t.get("schema") or {"type": "object", "properties": {}}} for t in mcp_tools]
    instructions, items = _codex_input(messages)
    headers = {
        "Authorization": f"Bearer {access_token}", "chatgpt-account-id": account_id or "",
        "OpenAI-Beta": "responses=experimental", "originator": "codex_cli_rs",
        "session_id": str(uuid.uuid4()), "Content-Type": "application/json", "Accept": "text/event-stream",
        "User-Agent": "javis-os/0.3 (codex)",
    }
    # Không có account_id thì BỎ HẲN header, đừng gửi chuỗi rỗng. `openai_responses_stream` -
    # đường không-tool đang chạy thật của gói này - làm đúng vậy, và hàm này thiếu đúng dòng đó.
    if not (account_id or ""):
        headers.pop("chatgpt-account-id", None)
    model = model or "gpt-5-codex"
    yield {"type": "meta", "model": model}
    timeout = httpx.Timeout(180, connect=15)
    async with httpx.AsyncClient(timeout=timeout) as client:
        usage_in = usage_out = 0
        for _ in range(_max_tool_rounds()):
            # Backend Codex BẮT BUỘC stream=True → đọc SSE, lấy response.completed.output để chạy vòng tool
            payload = {"model": model, "instructions": instructions, "input": items,
                       "tools": tools, "stream": True, "store": False}
            if reasoning not in (None, "", "off"):
                payload["reasoning"] = {"effort": api_effort(reasoning)}
            output, round_text = [], ""
            try:
                async with client.stream("POST", CODEX_RESPONSES_URL, headers=headers, json=payload) as r:
                    if r.status_code != 200:
                        body = await r.aread()
                        body_text = body.decode("utf-8", "replace")
                        _fact = limit_learner.parse_limit_error(r.status_code, body_text)
                        if _fact:
                            limit_learner.remember("openai-oauth", model, _fact)
                            yield {"type": "limit_exceeded", "provider": "ChatGPT",
                                   "model": model, "kind": _fact.kind, "limit": _fact.limit,
                                   "requested": _fact.requested,
                                   "shrink_to": limit_learner.shrink_target(_fact),
                           "remedy": _fact.remedy, "raw": _fact.raw}
                        yield ev_loi_http("ChatGPT", r.status_code, body_text, r.headers, _fact)
                        return
                    async for line in r.aiter_lines():
                        line = (line or "").strip()
                        if not line.startswith("data:"):
                            continue
                        data = line[5:].strip()
                        if not data:
                            continue
                        if data == "[DONE]":
                            break
                        try:
                            obj = json.loads(data)
                        except json.JSONDecodeError:
                            continue
                        et = obj.get("type")
                        if et == "response.output_text.delta":
                            # Bóc dấu trích dẫn nội bộ ngay tại nguồn, y như đường không-tool:
                            # backend Codex phát chúng ở CẢ hai đường.
                            round_text += strip_provider_markers(obj.get("delta") or "")
                        elif et == "response.completed":
                            _resp = obj.get("response") or {}
                            output = (_resp.get("output")) or []
                            _u = _resp.get("usage") or {}
                            usage_in += _u.get("input_tokens", 0) or 0
                            usage_out += _u.get("output_tokens", 0) or 0
                        elif et in ("response.failed", "error", "response.error"):
                            err = (obj.get("response") or {}).get("error") or obj.get("error") or {}
                            msg = err.get("message") if isinstance(err, dict) else str(err)
                            yield {"type": "error", "content": "ChatGPT: " + (msg or "lỗi")}
                            return
            except Exception as e:
                yield ev_loi_exc("ChatGPT lỗi", e)
                return
            fcalls = [o for o in output if o.get("type") == "function_call"]
            if fcalls:
                for o in output:
                    if o.get("type") in ("message", "function_call", "reasoning"):
                        items.append(o)
                for fc in fcalls:
                    try:
                        args = json.loads(fc.get("arguments") or "{}")
                    except json.JSONDecodeError:
                        args = {}
                    if _schedule_tool_allowed(messages, fc.get("name"), args):
                        yield {"type": "tool_call", "name": fc.get("name")}
                        result = await mcp_client.call_route(mcp_route, fc.get("name"), args)
                    else:
                        result = _schedule_tool_blocked_result()
                    items.append({"type": "function_call_output", "call_id": fc.get("call_id"), "output": _clip_tool_result(result)})
                continue
            text = ""
            for o in output:
                if o.get("type") == "message":
                    for c in (o.get("content") or []):
                        if c.get("type") in ("output_text", "text"):
                            text += c.get("text", "")
            text = text or round_text
            if usage_in or usage_out:
                yield {"type": "usage", "input": usage_in, "output": usage_out}
            if text:
                yield {"type": "text", "content": text}
            else:
                yield {"type": "error", "content": "ChatGPT trả về rỗng (backend Codex có thể chưa hỗ trợ tool)."}
            return
        yield {"type": "text", "content": _het_vong_msg()}


async def anthropic_chat_with_mcp(api_key, model, messages, reasoning, mcp_tools, mcp_route):
    """Anthropic Messages API + vòng tool-calling MCP - gỡ hạn chế 'anthropic-api = chat thuần'.
    Non-stream từng vòng (như _cc_tool_loop); yield meta/tool_call/text/error thống nhất.

    CHỈ nhận API key, cùng lý do với `anthropic_stream`: tham số `oauth_token` cũ cho phép gói
    Claude Code chạy vòng tool bằng token của chính CLI, và đó là thứ Anthropic cấm. Gói ấy nay
    chạy vòng tool bằng engine Claude Code thật (`main._claude_sub_stream_tools`).
    """
    import mcp_client
    sys_txt = "\n\n".join(m.get("content", "") for m in messages if m.get("role") == "system")
    conv = [{"role": m["role"], "content": m.get("content", "")}
            for m in messages if m.get("role") in ("user", "assistant")]
    headers = {"x-api-key": api_key, "anthropic-version": "2023-06-01",
               "content-type": "application/json"}
    tools = [{"name": t["fn"], "description": (t.get("description") or t["fn"])[:1024],
              "input_schema": t.get("schema") or {"type": "object", "properties": {}}} for t in mcp_tools]
    if tools:
        tools[-1]["cache_control"] = {"type": "ephemeral"}   # tools = prefix ổn định, cache 1 lần đủ
    yield {"type": "meta", "model": model}
    extras = _anthropic_reasoning(model, reasoning)
    timeout = httpx.Timeout(180, connect=15)
    async with httpx.AsyncClient(timeout=timeout) as client:
        usage_in = usage_out = 0
        for _ in range(_max_tool_rounds()):
            # Cache theo lối không-mutate (system dựng mới mỗi vòng, conv copy-khi-đánh-dấu)
            # → marker KHÔNG tích luỹ qua vòng tool, tối đa 3 breakpoint/request (trần API là 4).
            # Vòng tool là nơi cache lãi nhất: mỗi vòng 1 request chở lại nguyên system+tools+conv.
            payload = {"model": model or "claude-sonnet-4-6", "max_tokens": 4096,
                       "messages": _anthropic_mark_last(conv), "tools": tools, "stream": False}
            payload.update(extras or {})
            if sys_txt:
                payload["system"] = [{"type": "text", "text": sys_txt, "cache_control": {"type": "ephemeral"}}]
            try:
                r = await client.post(ANTHROPIC_URL, headers=headers, json=payload)
            except Exception as e:
                yield ev_loi_exc("Anthropic lỗi", e)
                return
            if r.status_code == 400 and extras and "thinking" in (r.text or "").lower():
                extras = {}   # thinking không tương thích payload/tool này → bỏ thinking, thử lại
                continue
            if r.status_code != 200:
                body_text = r.text or ""
                _fact = limit_learner.parse_limit_error(r.status_code, body_text)
                if _fact:
                    limit_learner.remember("anthropic", model, _fact)
                    yield {"type": "limit_exceeded", "provider": "anthropic", "model": model,
                           "kind": _fact.kind, "limit": _fact.limit,
                           "requested": _fact.requested,
                           "shrink_to": limit_learner.shrink_target(_fact),
                           "remedy": _fact.remedy, "raw": _fact.raw}
                yield ev_loi_http("Anthropic", r.status_code, body_text, r.headers, _fact)
                return
            try:
                data = r.json()
            except Exception:
                yield {"type": "error", "content": "Anthropic trả về không phải JSON."}
                return
            _u = data.get("usage") or {}   # cộng dồn token mọi vòng tool
            usage_in += ((_u.get("input_tokens") or 0) + (_u.get("cache_read_input_tokens") or 0)
                         + (_u.get("cache_creation_input_tokens") or 0))
            usage_out += _u.get("output_tokens") or 0
            blocks = data.get("content") or []
            tool_uses = [b for b in blocks if b.get("type") == "tool_use"]
            if tool_uses and data.get("stop_reason") == "tool_use":
                # Giữ NGUYÊN blocks (kể cả thinking) - API yêu cầu khi tiếp tục sau tool_use
                conv.append({"role": "assistant", "content": blocks})
                results = []
                for tu in tool_uses:
                    args = tu.get("input") or {}
                    if _schedule_tool_allowed(messages, tu.get("name"), args):
                        yield {"type": "tool_call", "name": tu.get("name")}
                        res = await mcp_client.call_route(mcp_route, tu.get("name"), args)
                    else:
                        res = _schedule_tool_blocked_result()
                    results.append({"type": "tool_result", "tool_use_id": tu.get("id"),
                                    "content": _clip_tool_result(res)})
                conv.append({"role": "user", "content": results})
                continue
            text = "".join(b.get("text", "") for b in blocks if b.get("type") == "text")
            if usage_in or usage_out:
                yield {"type": "usage", "input": usage_in, "output": usage_out}
            if text:
                yield {"type": "text", "content": text}
            else:
                yield {"type": "error", "content": "Anthropic trả về rỗng. Thử model khác trong Models."}
            return
        yield {"type": "text", "content": _het_vong_msg()}
