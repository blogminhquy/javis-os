"""
Lớp engine cho CHAT. Mặc định dùng Claude Code CLI (đầy đủ MCP/skill - ở claude_cli.py).
Đây là backend phụ: OpenRouter - chat THUẦN (không MCP/skill), khi user chọn engine=openrouter.
Stream token-by-token; trả các event {"type":"text"|"error","content":...} giống ClaudeCLI.query.
"""
import asyncio
import json
import random
import re
import threading
import time
import httpx

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


def _parse_retry_after(headers, cap: float = 600.0):
    """Đọc header Retry-After (giây) provider gửi kèm 429/503. Trả None nếu không có/không parse được.
    Provider (OpenRouter/Anthropic) gửi dạng số giây; bỏ qua dạng HTTP-date hiếm gặp.
    Cap 600s: đủ phủ mọi reset window thực tế, chặn giá trị bệnh lý."""
    if not headers or not hasattr(headers, "get"):
        return None
    raw = headers.get("retry-after") or headers.get("Retry-After")
    if not raw:
        return None
    try:
        return max(0.0, min(float(raw), cap))
    except (TypeError, ValueError):
        return None


class _RetryStream(Exception):
    """Sentinel để thoát các async with lồng nhau và quay lại vòng retry.
    retry_after: giây provider yêu cầu chờ (từ header Retry-After) - None thì dùng jittered backoff."""
    def __init__(self, retry_after=None):
        super().__init__()
        self.retry_after = retry_after


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

# Model Anthropic hỗ trợ adaptive thinking + output_config.effort (khỏi budget_tokens).
_ADAPTIVE_THINKING = ("opus-4-8", "opus-4-7", "opus-4-6", "opus-4-5", "sonnet-4-6", "fable-5", "mythos-5")


def _anthropic_reasoning(model, reasoning):
    """Phần payload thinking cho Messages API theo mức reasoning (off|low|medium|high).
    Model 4.6+ → adaptive thinking + effort (budget_tokens bị 400 trên 4.7/4.8).
    Model cũ (haiku-4-5, sonnet-4-5...) → extended thinking với budget_tokens < max_tokens."""
    if reasoning in (None, "", "off"):
        return {}
    m = (model or "").lower()
    if any(k in m for k in _ADAPTIVE_THINKING):
        return {
            "thinking": {"type": "adaptive", "display": "summarized"},
            "output_config": {"effort": reasoning},
            "max_tokens": 16000,   # chừa chỗ cho thinking + câu trả lời (đang stream nên không lo timeout)
        }
    budget = {"low": 2000, "medium": 6000, "high": 12000}.get(reasoning, 6000)
    return {"thinking": {"type": "enabled", "budget_tokens": budget}, "max_tokens": budget + 8000}


def _openai_is_reasoning(model):
    """OpenAI: chỉ model o-series / gpt-5 nhận reasoning_effort (gpt-4o sẽ 400 nếu gửi)."""
    m = (model or "").lower()
    return m.startswith(("o1", "o3", "o4")) or "gpt-5" in m


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
        payload["reasoning_effort"] = reasoning
    try:
        timeout = httpx.Timeout(120.0, connect=15.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream("POST", url, headers=headers, json=payload) as r:
                if r.status_code != 200:
                    body = await r.aread()
                    yield {"type": "error", "content": f"{label} {r.status_code}: {body.decode('utf-8', 'replace')[:300]}"}
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
        yield {"type": "error", "content": f"{label} lỗi: {_describe_exc(e)}"}


async def openai_stream(api_key, model, messages, reasoning="off"):
    """OpenAI Chat Completions (provider 'openai') - chat thuần, định dạng giống OpenRouter."""
    async for ev in _openai_compat_stream(OPENAI_URL, "OpenAI", api_key, model or "gpt-4o-mini",
                                          messages, reasoning, _openai_is_reasoning(model)):
        yield ev


async def gemini_stream(api_key, model, messages, reasoning="off"):
    """Google Gemini qua endpoint OpenAI-compatible (provider 'gemini') - chat thuần, cùng định dạng."""
    async for ev in _openai_compat_stream(GEMINI_URL, "Gemini", api_key, model or "gemini-2.5-flash",
                                          messages, reasoning, _gemini_is_reasoning(model)):
        yield ev


async def anthropic_stream(api_key, model, messages, reasoning="off"):
    """Anthropic Messages API (provider 'anthropic-api') - chat THUẦN, không MCP/skill.
    Tách system ra field riêng (Anthropic không nhận role=system trong messages)."""
    sys_parts = [m.get("content", "") for m in messages if m.get("role") == "system"]
    conv = [{"role": m["role"], "content": m.get("content", "")}
            for m in messages if m.get("role") in ("user", "assistant")]
    headers = {"x-api-key": api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"}
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
                    yield {"type": "error", "content": f"Anthropic {r.status_code}: {body.decode('utf-8', 'replace')[:300]}"}
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
        yield {"type": "error", "content": f"Anthropic lỗi: {_describe_exc(e)}"}


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
        payload["reasoning"] = {"effort": reasoning}   # OpenRouter chuẩn hoá effort cho mọi model reasoning
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
                        retriable = r.status_code in _RETRY_STATUS or _is_transient_body(body_text)
                        if retriable and attempt < max_attempts:
                            raise _RetryStream(_parse_retry_after(r.headers))
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
        payload["reasoning"] = {"effort": reasoning}
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
                    yield {"type": "error", "content": f"ChatGPT {r.status_code}: {body.decode('utf-8', 'replace')[:400]}"}
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
                        d = obj.get("delta") or ""
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
        yield {"type": "error", "content": f"ChatGPT OAuth lỗi: {_describe_exc(e)}"}


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
    schedule = any(x in q for x in (
        "cron", "nhac", "nhac hen", "nhac thuoc", "lich thuoc", "lich nhac", "uong thuoc",
        "viec dinh ky", "morning briefing", "reminder",
    ))
    if action and schedule and "javis_schedule" in names:
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
    last = next((m.get("content") or "" for m in reversed(messages or [])
                 if m.get("role") == "user"), "")
    q = _plain_vn(last)
    read = any(x in q for x in (
        "kiem tra", "check", "xem", "doc", "liet ke", "dang chay", "hien co", "hom nay", "con ",
    ))
    mutate = any(x in q for x in (
        "tao", "dat", "them", "huy", "xoa", "go ", "tat", "dung", "bat", "sua", "doi",
    ))
    return read and not mutate


def _schedule_cancel_request(messages):
    """Nhận diện yêu cầu huỷ/xoá lịch, không nhầm với câu chỉ hỏi hoặc tạo lịch."""
    last = next((m.get("content") or "" for m in reversed(messages or [])
                 if m.get("role") == "user"), "")
    q = _plain_vn(last)
    cancel = any(x in q for x in ("huy", "xoa", "go ", "tat", "dung", "bo lich", "bo nhac"))
    schedule = any(x in q for x in (
        "cron", "nhac", "lich thuoc", "lich nhac", "viec dinh ky",
        "morning briefing", "reminder", "vua bao",
    )) or bool(re.search(r"\bhen\b", q))
    return cancel and schedule


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
    for _ in range(8):
        payload = {"model": model, "messages": msgs, "tools": tools, "stream": False}
        if requirement_pending:
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
                yield {"type": "error", "content": f"{label} {r.status_code}: {(r.text or '')[:300]}"}
                return
            data = r.json()
        except Exception as e:
            yield {"type": "error", "content": f"{label} lỗi: {_describe_exc(e)}"}
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
                yield {"type": "tool_call", "name": fn}
                result = await mcp_client.call_route(mcp_route, fn, args)
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
    yield {"type": "text", "content": "\n\n⚠ Đã đạt giới hạn 8 vòng gọi tool MCP."}


async def openai_chat_with_mcp(api_key, model, messages, reasoning, mcp_tools, mcp_route):
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    extra = {}
    if reasoning not in (None, "", "off") and _openai_is_reasoning(model):
        extra["reasoning_effort"] = reasoning
    yield {"type": "meta", "model": model}
    async for ev in _cc_tool_loop(OPENAI_URL, headers, model or "gpt-4o-mini", messages, mcp_tools, mcp_route, extra, "OpenAI"):
        yield ev


async def gemini_chat_with_mcp(api_key, model, messages, reasoning, mcp_tools, mcp_route):
    """Google Gemini (endpoint OpenAI-compat) + vòng tool-calling MCP - Gemini cũng thành
    agent dùng MCP của Javis, y như OpenAI. Non-stream từng vòng (dùng _cc_tool_loop chung)."""
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    extra = {}
    if reasoning not in (None, "", "off") and _gemini_is_reasoning(model):
        extra["reasoning_effort"] = reasoning
    yield {"type": "meta", "model": model}
    async for ev in _cc_tool_loop(GEMINI_URL, headers, model or "gemini-2.5-flash", messages, mcp_tools, mcp_route, extra, "Gemini"):
        yield ev


async def openrouter_chat_with_mcp(api_key, model, messages, reasoning, mcp_tools, mcp_route):
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json",
               "HTTP-Referer": "http://localhost:7777", "X-Title": "Javis OS"}
    extra = {}
    if reasoning not in (None, "", "off"):
        extra["reasoning"] = {"effort": reasoning}
    yield {"type": "meta", "model": model}
    async for ev in _cc_tool_loop(OPENROUTER_URL, headers, model or "openai/gpt-4o-mini", messages, mcp_tools, mcp_route, extra, "OpenRouter",
                                  cache_system=_is_claude_model(model)):
        yield ev


async def responses_with_mcp(access_token, account_id, model, messages, reasoning, mcp_tools, mcp_route):
    """ChatGPT OAuth (Codex Responses API) + tool MCP. EXPERIMENTAL (backend Codex)."""
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
    model = model or "gpt-5-codex"
    yield {"type": "meta", "model": model}
    timeout = httpx.Timeout(180, connect=15)
    async with httpx.AsyncClient(timeout=timeout) as client:
        usage_in = usage_out = 0
        for _ in range(8):
            # Backend Codex BẮT BUỘC stream=True → đọc SSE, lấy response.completed.output để chạy vòng tool
            payload = {"model": model, "instructions": instructions, "input": items,
                       "tools": tools, "stream": True, "store": False}
            if reasoning not in (None, "", "off"):
                payload["reasoning"] = {"effort": reasoning}
            output, round_text = [], ""
            try:
                async with client.stream("POST", CODEX_RESPONSES_URL, headers=headers, json=payload) as r:
                    if r.status_code != 200:
                        body = await r.aread()
                        yield {"type": "error", "content": f"ChatGPT {r.status_code}: {body.decode('utf-8', 'replace')[:300]}"}
                        return
                    async for line in r.aiter_lines():
                        line = (line or "").strip()
                        if not line.startswith("data:"):
                            continue
                        data = line[5:].strip()
                        if not data or data == "[DONE]":
                            continue
                        try:
                            obj = json.loads(data)
                        except json.JSONDecodeError:
                            continue
                        et = obj.get("type")
                        if et == "response.output_text.delta":
                            round_text += obj.get("delta") or ""
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
                yield {"type": "error", "content": f"ChatGPT lỗi: {_describe_exc(e)}"}
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
                    yield {"type": "tool_call", "name": fc.get("name")}
                    result = await mcp_client.call_route(mcp_route, fc.get("name"), args)
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
        yield {"type": "text", "content": "\n\n⚠ Đã đạt giới hạn 8 vòng gọi tool MCP."}


async def anthropic_chat_with_mcp(api_key, model, messages, reasoning, mcp_tools, mcp_route):
    """Anthropic Messages API + vòng tool-calling MCP - gỡ hạn chế 'anthropic-api = chat thuần'.
    Non-stream từng vòng (như _cc_tool_loop); yield meta/tool_call/text/error thống nhất."""
    import mcp_client
    sys_txt = "\n\n".join(m.get("content", "") for m in messages if m.get("role") == "system")
    conv = [{"role": m["role"], "content": m.get("content", "")}
            for m in messages if m.get("role") in ("user", "assistant")]
    headers = {"x-api-key": api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"}
    tools = [{"name": t["fn"], "description": (t.get("description") or t["fn"])[:1024],
              "input_schema": t.get("schema") or {"type": "object", "properties": {}}} for t in mcp_tools]
    if tools:
        tools[-1]["cache_control"] = {"type": "ephemeral"}   # tools = prefix ổn định, cache 1 lần đủ
    yield {"type": "meta", "model": model}
    extras = _anthropic_reasoning(model, reasoning)
    timeout = httpx.Timeout(180, connect=15)
    async with httpx.AsyncClient(timeout=timeout) as client:
        usage_in = usage_out = 0
        for _ in range(8):
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
                yield {"type": "error", "content": f"Anthropic lỗi: {_describe_exc(e)}"}
                return
            if r.status_code == 400 and extras and "thinking" in (r.text or "").lower():
                extras = {}   # thinking không tương thích payload/tool này → bỏ thinking, thử lại
                continue
            if r.status_code != 200:
                yield {"type": "error", "content": f"Anthropic {r.status_code}: {(r.text or '')[:300]}"}
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
                    yield {"type": "tool_call", "name": tu.get("name")}
                    res = await mcp_client.call_route(mcp_route, tu.get("name"), tu.get("input") or {})
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
        yield {"type": "text", "content": "\n\n⚠ Đã đạt giới hạn 8 vòng gọi tool MCP."}
