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
import contextvars
import json
import os
import random
import re
import sys
import threading
import time
import uuid
from datetime import datetime, timezone
from contextlib import asynccontextmanager

import httpx

import fast_mode   # composer Fast mode bolt: per-provider parameters (0.164.0)
import limit_learner
import localefmt
import vision_input
import steer_inbox   # 0.206.0: messages the owner sends while a turn runs


TEAM_REQUEST_OBSERVER = contextvars.ContextVar("team_request_observer", default=None)


def _observe_team_request(event):
    """Optional host telemetry seam. Observer failures never change provider execution."""
    observer = TEAM_REQUEST_OBSERVER.get()
    if observer is not None:
        try:
            observer(event)
        except Exception:
            try:
                import usage_store
                usage_store.note_telemetry_error()
            except Exception:
                pass


def _request_usage(data, event_id):
    usage = data.get("usage") or {}
    anthropic = "input_tokens" in usage and ("cache_read_input_tokens" in usage or "content" in data)
    tin = usage.get("input_tokens") if "input_tokens" in usage else usage.get("prompt_tokens")
    if anthropic and tin is not None:
        tin += (usage.get("cache_read_input_tokens") or 0) + (usage.get("cache_creation_input_tokens") or 0)
    tout = usage.get("output_tokens") if "output_tokens" in usage else usage.get("completion_tokens")
    return {"event_id": event_id, "request_id": data.get("id"), "input": tin, "output": tout,
            "cost": usage.get("cost"), "cache_read": usage.get("cache_read_input_tokens"),
            "cache_create": usage.get("cache_creation_input_tokens")}


async def _observed_post(send):
    """Record every actual HTTP attempt, including retries and interrupted requests with unknown usage."""
    if TEAM_REQUEST_OBSERVER.get() is None:
        return await send()
    event_id = uuid.uuid4().hex
    _observe_team_request({"event_id": event_id, "input": None, "output": None})
    response = await send()
    try:
        data = response.json()
        if isinstance(data, dict):
            _observe_team_request(_request_usage(data, event_id))
    except Exception:
        pass
    return response


@asynccontextmanager
async def _observed_stream(client, *args, **kwargs):
    event_id = uuid.uuid4().hex
    _observe_team_request({"event_id": event_id, "input": None, "output": None})
    async with client.stream(*args, **kwargs) as response:
        yield response, event_id


def _c(vi: str, en: str) -> str:
    """Chữ hiện cho người dùng (lỗi, ghi chú cuối câu trả lời) theo ngôn ngữ giao diện."""
    return localefmt.chu(vi, en)

# Lone surrogate (U+D800-U+DFFF) sanitizer - port từ hermes-agent/agent/message_sanitization.py.
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
# Lỗi mạng đáng chạy lại. `httpx.NetworkError` gom ConnectError, ReadError, WriteError, CloseError.
# Trước 0.171.2 chỉ có ConnectError: kết nối mở được rồi bị cắt giữa chừng (ReadError, vd
# "[WinError 1236] The network connection was aborted by the local system" trên Windows, thường do
# mạng chập chờn, VPN hay phần mềm diệt virus) thì không được chạy lại, cả lượt chết ngay cú đầu.
_MANG_GAY = (httpx.NetworkError, httpx.RemoteProtocolError)
_RETRY_EXC = (httpx.ReadTimeout, httpx.ConnectTimeout) + _MANG_GAY
# Số lần gửi MỘT vòng gọi model trong vòng tool khi kết nối gãy (xem `_gui_vong`).
_LAN_GUI_VONG = 3

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
    ev = {"type": "error", "content": f"{nhan} {status}: {provider_message(body_text)[:cat]}"}
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


def provider_message(body_text) -> str:
    """The human sentence inside a provider's JSON error body, else the body as it came (0.335.0).

    Gemini answers a 503 with `[{"error": {"code": 503, "message": "This model is currently experiencing high demand...",
    "status": "UNAVAILABLE"}}]`, and that whole block reached the chat (owner report 26/10/2026). OpenAI, Anthropic and
    OpenRouter use the same `error.message` shape, sometimes with a bare `message`."""
    raw = str(body_text or "").strip()
    if not raw.startswith(("{", "[")):
        return raw
    try:
        d = json.loads(raw)
    except ValueError:
        return raw
    if isinstance(d, list) and d:
        d = d[0]
    if not isinstance(d, dict):
        return raw
    err = d.get("error")
    msg = err.get("message") if isinstance(err, dict) else (err if isinstance(err, str) else d.get("message"))
    if not (isinstance(msg, str) and msg.strip()):
        return raw
    # The provider's own error code stays in brackets, so the line can still be looked up (`rate_limit_error`,
    # `UNAVAILABLE`): Anthropic's 429 says only "Error" in its message.
    kind = (err.get("type") or err.get("status")) if isinstance(err, dict) else None
    return msg.strip() + (f" ({kind})" if isinstance(kind, str) and kind.strip() else "")


def _qua_tai(ev: dict) -> bool:
    """The provider is overloaded (503/529 or an "overloaded"/"high demand" body), not a broken request."""
    low = str(ev.get("content") or "").lower()
    return ev.get("ma") in (503, 529) or any(p in low for p in ("overloaded", "high demand", "at capacity"))


def ev_loi_exc(nhan, exc):
    """Sự kiện lỗi từ một ngoại lệ. Chỉ lỗi MẠNG mới đáng chạy lại.

    Lỗi lập trình (JSON hỏng, thiếu khoá, sai kiểu) chạy lại bao nhiêu lần cũng hỏng y hệt,
    và mỗi lần chạy lại là một lượt gọi model thật đã trả tiền.
    """
    ev = {"type": "error", "content": f"{nhan}: {_describe_exc(exc)}"}
    da_thu = getattr(exc, "_javis_da_thu", 0)
    if da_thu:
        # `_gui_vong` đã gửi lại vòng này đủ số lần. Không gắn `tam_thoi` nữa, kẻo tầng
        # `thu_lai_khi_tam_thoi` chạy lại cả lượt và số lần gọi nở thành cấp số nhân.
        ev["content"] += _c(f" (đã thử lại {da_thu} lần)", f" (retried {da_thu} times)") + _goi_y_mang()
        return ev
    if isinstance(exc, _RETRY_EXC):
        ev["tam_thoi"] = True
    if isinstance(exc, _MANG_GAY):
        ev["mang"] = True
    return ev


def _goi_y_mang() -> str:
    """Câu dặn khi kết nối tới nhà cung cấp gãy hẳn sau mọi lần thử: chuỗi lỗi kỹ thuật một mình
    không nói được người ta phải làm gì."""
    return _c(" - kết nối tới nhà cung cấp bị cắt giữa chừng. Thường do mạng chập chờn, VPN, hoặc phần mềm "
              "diệt virus/tường lửa trên máy chặn kết nối. Gửi lại tin là được; lặp lại nhiều lần thì kiểm "
              "tra mạng và tạm tắt quét HTTPS của phần mềm diệt virus.",
              " - the connection to the provider was cut mid-request. Usually a flaky network, a VPN, or an "
              "antivirus/firewall on this machine dropping the connection. Send the message again; if it keeps "
              "happening, check the network and turn off the antivirus HTTPS scanning.")


async def _gui_vong(gui, nhan=""):
    """Gửi MỘT vòng gọi model của vòng tool, gửi lại khi kết nối gãy giữa chừng (0.171.2).

    Vòng tool gọi model nhiều lần trong một lượt. `thu_lai_khi_tam_thoi` chỉ chạy lại cả lượt
    khi CHƯA chạy tool nào, nên một cú rớt mạng ở vòng thứ hai trở đi giết trọn lượt, dù tool đã
    chạy xong và chỉ còn đợi model viết câu trả lời. Gửi lại đúng request đó thì an toàn: request
    gãy chưa trả về gì, tool không chạy lại, cái mất duy nhất là tiền một lượt gọi model.

    Chỉ gửi lại khi MẠNG gãy, không gửi lại khi hết giờ chờ: một request 180 giây mà gửi lại ba
    lần là người ta ngồi nhìn màn hình chín phút. Hết lượt thì ném đúng lỗi gốc, gắn số lần đã thử
    để `ev_loi_exc` nói cho người dùng."""
    for lan in range(1, _LAN_GUI_VONG + 1):
        try:
            return await gui()
        except _MANG_GAY as e:
            if lan >= _LAN_GUI_VONG:
                e._javis_da_thu = lan
                raise
            cho = _jittered_backoff(lan)
            print(f"[thử lại vòng {nhan or '?'}] lần {lan} rớt mạng, chờ {cho:.1f}s: {_describe_exc(e)[:160]}",
                  file=sys.stderr)
            await asyncio.sleep(cho)


# ── Vòng tool nhận chữ TỪNG MẨU (0.438.5) ──
# Trước đây mỗi vòng của vòng tool gọi model kiểu non-stream: câu trả lời cuối chỉ hiện khi model viết
# xong, trong khi ChatGPT (Codex) và Claude Code hiện chữ lần lượt. Chủ repo 01/11/2026: "các apikey khác
# cũng phải như vậy". Nay mỗi vòng gọi `stream: true`, nhả chữ ra thành sự kiện `delta` (CHỈ để xem trước:
# nơi nào không biết `delta` thì bỏ qua, nên bot khách, việc nền, Telegram y như cũ), rồi gom lại thành
# đúng hình dạng của câu trả lời non-stream để phần còn lại của vòng tool chạy y nguyên.
# Tắt bằng JAVIS_API_STREAM_TOOLS=0. Endpoint nào từ chối stream thì tự lui về non-stream.
_KHONG_STREAM_VONG: set = set()   # nhãn provider đã từ chối vòng stream (trong tiến trình này)


def stream_vong_bat(label: str = "") -> bool:
    if label and label in _KHONG_STREAM_VONG:
        return False
    return (os.environ.get("JAVIS_API_STREAM_TOOLS") or "1").strip().lower() not in ("0", "false", "off", "no")


def _stream_bi_tu_choi(status, body_text) -> bool:
    """Endpoint nói nó không nhận stream (hay `stream_options`): lui về non-stream thay vì hỏng lượt."""
    return status in (400, 404, 415, 422, 501) and "stream" in (body_text or "").lower()


class _VongDaGom:
    """Một vòng stream gom lại: cùng bộ mặt với httpx.Response mà vòng tool đang đọc
    (status_code, text, headers, json())."""

    def __init__(self, status_code, data=None, text="", headers=None):
        self.status_code = status_code
        self._data = data
        self.text = text or (json.dumps(data, ensure_ascii=False) if data is not None else "")
        self.headers = headers if headers is not None else {}

    def json(self):
        if self._data is None:
            return json.loads(self.text)
        return self._data


class _GomCC:
    """Gom các chunk Chat Completions (stream) thành một `message` như bản non-stream."""

    def __init__(self):
        self.id = None
        self.content, self.reasoning_content, self.reasoning = [], [], []
        self.calls, self.order = {}, []
        self.usage = None
        self.finish = None

    def them(self, obj) -> str:
        """Nạp một chunk, trả phần chữ trả lời mới (rỗng nếu chunk không mang chữ)."""
        if obj.get("id") and not self.id:
            self.id = obj["id"]
        u = obj.get("usage") or (obj.get("x_groq") or {}).get("usage")
        if u:
            self.usage = u
        piece = ""
        for ch in obj.get("choices") or []:
            if (ch.get("index") or 0) != 0:
                continue
            d = ch.get("delta") or ch.get("message") or {}
            c = d.get("content")
            if isinstance(c, str) and c:
                self.content.append(c)
                piece += c
            for k, buf in (("reasoning_content", self.reasoning_content), ("reasoning", self.reasoning)):
                v = d.get(k)
                if isinstance(v, str) and v:
                    buf.append(v)
            for tc in d.get("tool_calls") or []:
                if isinstance(tc, dict):
                    self._call(tc)
            if ch.get("finish_reason"):
                self.finish = ch["finish_reason"]
        return piece

    def _call(self, tc):
        idx = tc.get("index")
        if idx is None:   # vài endpoint (Gemini) không ghi index: id mới là lệnh mới, không id là mẩu tiếp
            tid = tc.get("id")
            known = next((k for k, v in self.calls.items() if tid and v.get("id") == tid), None)
            if known is not None:
                idx = known
            elif tid or not self.order:
                idx = len(self.order)
            else:
                idx = self.order[-1]
        e = self.calls.get(idx)
        if e is None:
            e = self.calls[idx] = {"id": "", "type": "function", "function": {"name": "", "arguments": ""}}
            self.order.append(idx)
        for k, v in tc.items():
            if k == "index":
                continue
            if k == "function":
                fn = v or {}
                nm = fn.get("name")
                if nm:
                    cur = e["function"]["name"]
                    e["function"]["name"] = nm if (not cur or nm.startswith(cur)) else cur + nm
                args = fn.get("arguments")
                if isinstance(args, str):
                    e["function"]["arguments"] += args
                elif isinstance(args, dict):
                    e["function"]["arguments"] += json.dumps(args, ensure_ascii=False)
                for fk, fv in fn.items():
                    if fk not in ("name", "arguments"):
                        e["function"][fk] = fv
            elif k in ("id", "type"):
                if v:
                    e[k] = v
            else:
                e[k] = v   # vd extra_content của Gemini (thought signature) phải đi nguyên về lượt sau

    def ket(self) -> dict:
        msg = {"role": "assistant", "content": "".join(self.content) or None}
        if self.reasoning_content:
            msg["reasoning_content"] = "".join(self.reasoning_content)
        if self.reasoning:
            msg["reasoning"] = "".join(self.reasoning)
        calls = [self.calls[i] for i in self.order]
        for c in calls:
            if not c["id"]:
                c["id"] = "call_" + uuid.uuid4().hex[:12]
            if not c["function"]["arguments"].strip():
                c["function"]["arguments"] = "{}"
        if calls:
            msg["tool_calls"] = calls
        return {"id": self.id, "choices": [{"message": msg, "finish_reason": self.finish}],
                "usage": self.usage or {}}


def _ma_loi_stream(err: dict, mac_dinh: int = 502) -> int:
    """Lỗi nhà cung cấp gửi GIỮA luồng (status HTTP đã là 200): suy ra mã để vòng tool xử lý như lỗi HTTP."""
    code = err.get("code") if isinstance(err, dict) else None
    try:
        code = int(code)
        if 400 <= code <= 599:
            return code
    except (TypeError, ValueError):
        pass
    kind = str((err or {}).get("type") or "") if isinstance(err, dict) else ""
    return {"overloaded_error": 529, "rate_limit_error": 429, "invalid_request_error": 400,
            "authentication_error": 401, "permission_error": 403, "not_found_error": 404,
            "request_too_large": 413}.get(kind, mac_dinh)


async def _doc_body(r) -> str:
    return (await r.aread()).decode("utf-8", "replace")


async def _vong_stream(client_or_none, url, headers, payload, kieu):
    """MỘT vòng gọi model của vòng tool, dạng stream. Nhả {"type": "delta", "content"} khi chữ trả lời về,
    cuối cùng nhả {"type": "_vong", "r": _VongDaGom} mang đúng thứ bản non-stream trả về.

    kieu: "cc" (Chat Completions) hoặc "anthropic" (Messages API).
    Rớt mạng TRƯỚC khi nhả chữ nào thì gửi lại như `_gui_vong`; đã nhả chữ rồi thì ném lỗi (gửi lại là
    chữ hiện hai lần). Endpoint trả JSON thường dù đã xin stream thì đọc như non-stream."""
    body = dict(payload)
    body["stream"] = True
    if kieu == "cc":
        body.setdefault("stream_options", {"include_usage": True})
    lan = 0
    while True:
        lan += 1
        da_nha = False
        try:
            if client_or_none is None:
                client = httpx.AsyncClient(timeout=httpx.Timeout(180, connect=15))
            else:
                client = client_or_none
            try:
                async with _observed_stream(client, "POST", url, headers=headers, json=body) as (r, event_id):
                    if r.status_code != 200:
                        yield {"type": "_vong", "r": _VongDaGom(r.status_code, text=await _doc_body(r),
                                                                headers=r.headers)}
                        return
                    if "event-stream" not in (r.headers.get("content-type") or "").lower():
                        text = await _doc_body(r)
                        try:
                            data = json.loads(text)
                        except ValueError:
                            data = None
                        if isinstance(data, dict):
                            _observe_team_request(_request_usage(data, event_id))
                        yield {"type": "_vong", "r": _VongDaGom(200, data=data if isinstance(data, dict) else None,
                                                                text=text, headers=r.headers)}
                        return
                    gom = _GomCC() if kieu == "cc" else None
                    blocks, usage, stop, msg_id, err = {}, {}, None, None, None
                    async for line in r.aiter_lines():
                        line = (line or "").strip()
                        if not line.startswith("data:"):
                            continue
                        raw = line[5:].strip()
                        if raw == "[DONE]":
                            break
                        try:
                            obj = json.loads(raw)
                        except ValueError:
                            continue
                        if not isinstance(obj, dict):
                            continue
                        if kieu == "cc":
                            if obj.get("error") and not obj.get("choices"):
                                err = obj["error"] if isinstance(obj["error"], dict) else {"message": str(obj["error"])}
                                break
                            piece = gom.them(obj)
                            if piece:
                                da_nha = True
                                yield {"type": "delta", "content": piece}
                            continue
                        t = obj.get("type")
                        if t == "message_start":
                            m = obj.get("message") or {}
                            msg_id = m.get("id")
                            usage.update(m.get("usage") or {})
                        elif t == "content_block_start":
                            b = dict(obj.get("content_block") or {})
                            if b.get("type") == "tool_use":
                                b["_json"] = ""
                            blocks[obj.get("index", len(blocks))] = b
                            if b.get("type") == "text" and b.get("text"):
                                da_nha = True
                                yield {"type": "delta", "content": b["text"]}
                        elif t == "content_block_delta":
                            d = obj.get("delta") or {}
                            b = blocks.setdefault(obj.get("index", 0), {"type": "text", "text": ""})
                            dt = d.get("type")
                            if dt == "text_delta":
                                piece = d.get("text") or ""
                                b["text"] = (b.get("text") or "") + piece
                                if piece:
                                    da_nha = True
                                    yield {"type": "delta", "content": piece}
                            elif dt == "input_json_delta":
                                b["_json"] = b.get("_json", "") + (d.get("partial_json") or "")
                            elif dt == "thinking_delta":
                                b["thinking"] = (b.get("thinking") or "") + (d.get("thinking") or "")
                            elif dt == "signature_delta":
                                b["signature"] = (b.get("signature") or "") + (d.get("signature") or "")
                        elif t == "message_delta":
                            stop = (obj.get("delta") or {}).get("stop_reason") or stop
                            usage.update({k: v for k, v in (obj.get("usage") or {}).items() if v is not None})
                        elif t == "error":
                            err = obj.get("error") or {}
                            break
                        elif t == "message_stop":
                            break
                    if err is not None:
                        text = json.dumps({"error": err} if kieu == "cc" else {"type": "error", "error": err},
                                          ensure_ascii=False)
                        yield {"type": "_vong", "r": _VongDaGom(_ma_loi_stream(err), text=text, headers={})}
                        return
                    if kieu == "cc":
                        data = gom.ket()
                    else:
                        content = []
                        for i in sorted(blocks, key=lambda x: (not isinstance(x, int), x if isinstance(x, int) else 0)):
                            b = blocks[i]
                            if b.get("type") == "tool_use":
                                js = b.pop("_json", "")
                                try:
                                    b["input"] = json.loads(js) if js.strip() else (b.get("input") or {})
                                except ValueError:
                                    b["input"] = b.get("input") or {}
                            content.append(b)
                        data = {"id": msg_id, "type": "message", "role": "assistant", "content": content,
                                "stop_reason": stop, "usage": usage}
                    _observe_team_request(_request_usage(data, event_id))
                    yield {"type": "_vong", "r": _VongDaGom(200, data=data, headers=r.headers)}
                    return
            finally:
                if client_or_none is None:
                    await client.aclose()
        except _MANG_GAY as e:
            if da_nha or lan >= _LAN_GUI_VONG:
                e._javis_da_thu = lan
                raise
            cho = _jittered_backoff(lan)
            print(f"[thử lại vòng stream] lần {lan} rớt mạng, chờ {cho:.1f}s: {_describe_exc(e)[:160]}",
                  file=sys.stderr)
            await asyncio.sleep(cho)


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
            # An overloaded model (Gemini 503 "high demand", Anthropic 529) needs seconds, not one: the old 1s-2s pace
            # spent all three tries inside the same spike (owner report 26/10/2026).
            cho = (_jittered_backoff(lan, base=5.0, max_delay=20.0) if loi_hoan.get("ma") == 429
                   else _jittered_backoff(lan, base=4.0, max_delay=15.0) if _qua_tai(loi_hoan)
                   else _jittered_backoff(lan))
        # Nhà cung cấp bảo chờ lâu hơn ngưỡng người ta chịu ngồi im thì đừng chờ - báo ngay để
        # họ biết mà làm việc khác, thay vì nhìn màn hình đứng yên nửa phút.
        if lan >= so_lan or cho > _WINDOW_WAIT_MAX:
            cuoi = dict(loi_hoan)
            cuoi.pop("tam_thoi", None)
            cuoi.pop("cho", None)
            cuoi["da_thu"] = lan
            if lan > 1:
                cuoi["content"] = cuoi["content"] + _c(f" (đã thử lại {lan} lần)", f" (retried {lan} times)")
            if cuoi.pop("mang", None):
                cuoi["content"] += _goi_y_mang()
            # Câu này đi thẳng lên thẻ bot của CHỦ. Một cục JSON của nhà cung cấp không nói
            # được phải làm gì tiếp, mà đó đúng là thứ chủ cần biết khi nhìn thẻ đỏ.
            if loi_hoan.get("ma") == 429:
                cuoi["content"] += _c(
                    f" - hạn mức nhà cung cấp đang đầy"
                    + (f", cửa sổ mở lại sau khoảng {cho:.0f}s" if cho > _WINDOW_WAIT_MAX else "")
                    + ". Chờ cửa sổ trôi qua, hoặc đổi bộ não cho bot ở trang Models.",
                    f" - the provider's rate limit is full"
                    + (f", the window reopens in about {cho:.0f}s" if cho > _WINDOW_WAIT_MAX else "")
                    + ". Wait for the window to pass, or switch the bot's brain on the Models page."
                )
            elif _qua_tai(loi_hoan):
                cuoi["content"] += _c(
                    " - model này đang quá tải phía nhà cung cấp, không phải lỗi của Javis hay của bạn. Thường hết sau "
                    "vài phút: gửi lại sau ít phút, hoặc bấm chip model ở ô chat để đổi sang model khác.",
                    " - this model is overloaded on the provider's side; it is not a fault in Javis or on your end. It "
                    "usually passes within minutes: send again shortly, or press the model chip in the chat box to "
                    "switch to another model.")
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

# DeepSeek (endpoint OpenAI-compatible). The picker loads the LIVE list from /models; this
# default is only the safety net. `deepseek-chat` and `deepseek-reasoner` were retired on
# 2026-07-24, so never fall back to them.
DEEPSEEK_URL = "https://api.deepseek.com/chat/completions"
DEEPSEEK_MODELS_URL = "https://api.deepseek.com/models"
DEEPSEEK_DEFAULT_MODEL = "deepseek-flash"

# 0.355.0: the model each API engine runs when its card leaves the model on "default". The Models page shows this name
# next to "default"; the fallbacks in the engine functions below must stay equal to it (tests/python/test_model_mac_dinh.py).
DEFAULT_MODELS = {
    "openai": "gpt-4o-mini",
    "gemini": "gemini-2.5-flash",
    "anthropic-api": "claude-sonnet-4-6",
    "openrouter": "openai/gpt-4o-mini",
    "groq": GROQ_DEFAULT_MODEL,
    "deepseek": DEEPSEEK_DEFAULT_MODEL,
}

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


def ollama_local_url() -> str:
    """URL chat của Ollama chạy trên MÁY NHÀ (provider 'ollama-local'). "" = chưa cấu hình.

    Đây là chỗ hiện thực hoá điểm 2 ở khối chú thích trên: địa chỉ KHÔNG hằng số hoá được nên
    phải dựng lúc chạy từ cấu hình. Còn điểm 1 (không có API key) thì không cần làm gì -
    `_openai_compat_stream` vẫn gửi header Authorization và Ollama bỏ qua, nên dùng lại được
    nguyên đường OpenAI-compat, không đẻ thêm nhánh nào.
    """
    import config as cfgmod
    ep = (cfgmod.read_settings().get("model", {}).get("ollama_local_endpoint") or "").strip()
    ep = ep.rstrip("/")
    return (ep + "/v1/chat/completions") if ep else ""

def openai_compat_base() -> str:
    """Base URL của provider 'openai-compat' (tính tới /v1, không có gạch chéo cuối). "" = chưa đặt."""
    import config as cfgmod
    ep = (cfgmod.read_settings().get("model", {}).get("openai_compat_base") or "").strip().rstrip("/")
    # Người dùng hay dán nguyên URL chat thay vì base - cắt đuôi đó đi thay vì báo lỗi.
    if ep.endswith("/chat/completions"):
        ep = ep[: -len("/chat/completions")]
    return ep


def openai_compat_url() -> str:
    """URL chat của provider 'openai-compat'. "" = chưa đặt Base URL."""
    ep = openai_compat_base()
    return (ep + "/chat/completions") if ep else ""


def normalize_anthropic_compat_base(ep: str) -> str:
    """Base URL of an Anthropic-compatible gateway, in the shape of Claude Code's ANTHROPIC_BASE_URL:
    no trailing slash, no /v1 and no /messages. People paste any of the three, so all are accepted:
    "https://x.com/anthropic", "https://x.com/anthropic/v1" and "https://x.com/anthropic/v1/messages"
    all become "https://x.com/anthropic"."""
    ep = (ep or "").strip().rstrip("/")
    if ep.endswith("/messages"):
        ep = ep[: -len("/messages")].rstrip("/")
    if ep.endswith("/v1"):
        ep = ep[: -len("/v1")].rstrip("/")
    return ep


def anthropic_compat_base() -> str:
    """Base URL of provider 'anthropic-compat' (0.254.0). "" = not set."""
    import config as cfgmod
    return normalize_anthropic_compat_base(cfgmod.read_settings().get("model", {}).get("anthropic_compat_base") or "")


def anthropic_compat_url() -> str:
    """Messages URL of provider 'anthropic-compat'. "" = no base URL set."""
    ep = anthropic_compat_base()
    return (ep + "/v1/messages") if ep else ""


def anthropic_headers(api_key: str, compat: bool = False) -> dict:
    """Headers for the Messages API. A gateway gets the key BOTH ways: resellers differ on whether
    they read x-api-key (Claude Code's ANTHROPIC_API_KEY) or a Bearer token (ANTHROPIC_AUTH_TOKEN),
    and sending both is what lets one form work with either kind."""
    h = {"x-api-key": api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"}
    if compat:
        h["authorization"] = f"Bearer {api_key}"
    return h


# Model Anthropic hỗ trợ adaptive thinking + output_config.effort (khỏi budget_tokens).
#
# Thiếu tên nào ở đây là lượt chat của model ĐÓ rơi xuống nhánh `budget_tokens` bên dưới, mà
# dòng 5 trả 400 cho tham số đó - tức bật "độ sâu suy nghĩ" lên là hỏng cả lượt, im lặng với
# người dùng và chỉ hiện ra như một lỗi chung chung. `opus-5` và `sonnet-5` đã sót đúng như
# vậy: khớp theo chuỗi con nên "claude-opus-5" không dính mục "opus-4-8" nào cả.
_ADAPTIVE_THINKING = ("opus-5", "opus-4-8", "opus-4-7", "opus-4-6", "opus-4-5",
                      "sonnet-5", "sonnet-4-6", "fable-5", "mythos-5")


# Thang độ sâu suy nghĩ của Javis, sáu nấc.
REASONING_LEVELS = ("off", "low", "medium", "high", "xhigh", "ultra")
# Giá trị effort GỬI LÊN API kiểu OpenAI (OpenAI, Groq, Gemini, OpenRouter, Codex). Mấy nhà đó
# chỉ nhận low|medium|high; gửi "ultra" là ăn 400 và hỏng cả lượt chat, nên hai nấc trên cùng
# quy về "high".
#
# Anthropic thì KHÁC và có bảng riêng bên dưới (`_anthropic_effort`): Messages API nhận đủ
# low|medium|high|xhigh|max, nên dùng bảng này cho họ là bóp hai nấc trên cùng thành "Cao" -
# người dùng bấm "Tối đa" mà không có gì đổi, im lặng, không báo lỗi gì.
_API_EFFORT = {"low": "low", "medium": "medium", "high": "high", "xhigh": "high", "ultra": "high"}


def api_effort(reasoning):
    """Mức Javis -> giá trị effort AN TOÀN để nhét vào payload của nhà cung cấp.

    Nơi gọi phải TỰ chặn mức "off" trước (không gửi trường effort gì cả); hàm này chỉ lo dịch
    mức đã bật. Giá trị lạ rơi về "medium" để một chỗ ghi sai config không làm hỏng cả lượt chat.
    """
    return _API_EFFORT.get(reasoning or "", "medium")


# Model Anthropic nhận mức effort "xhigh" (mức này ra mắt cùng Opus 4.7; 4.6 trở về trước
# không có). Gửi "xhigh" cho model không hiểu là 400, nên chia làm hai nhóm.
_EFFORT_CO_XHIGH = ("opus-5", "opus-4-8", "opus-4-7", "sonnet-5", "fable-5", "mythos-5")
# Nhóm có "max" nhưng KHÔNG có "xhigh".
_EFFORT_CO_MAX = ("opus-4-6", "sonnet-4-6")


def _anthropic_effort(model, reasoning):
    """Mức Javis -> mức effort của Messages API, theo đúng thứ model đó nhận được.

    Vì sao không dùng chung `api_effort`: bảng kia bóp "xhigh" và "ultra" xuống "high" cho hợp
    với các nhà kiểu OpenAI, nên trên Anthropic thì ba nấc trên cùng của Javis ra cùng một kết
    quả. Người dùng chọn "Tối đa" và không có gì thay đổi - hỏng kiểu im lặng nhất.
    """
    m = (model or "").lower()
    if reasoning == "ultra":
        return "max" if any(k in m for k in _EFFORT_CO_XHIGH + _EFFORT_CO_MAX) else "high"
    if reasoning == "xhigh":
        return "xhigh" if any(k in m for k in _EFFORT_CO_XHIGH) else "high"
    return api_effort(reasoning)


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
            "output_config": {"effort": _anthropic_effort(model, reasoning)},
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


# Javis level -> DeepSeek `reasoning_effort`. DeepSeek only knows low|high|max (it maps
# medium/xhigh to high on its own), so send the values it names instead of relying on that.
_DEEPSEEK_EFFORT = {"low": "low", "medium": "high", "high": "high", "xhigh": "max", "ultra": "max"}
_DEEPSEEK_THINKING_OFF = {"thinking": {"type": "disabled"}}


def _deepseek_thinking(reasoning):
    """Payload fields that switch DeepSeek thinking on or off for this request.

    DeepSeek thinks BY DEFAULT, unlike every other OpenAI-compatible provider here. So "off"
    has to be said out loud: leaving the field out is not off, it is thinking at effort
    "high", which costs tokens and breaks the tool loop (see `deepseek_chat_with_mcp`).
    """
    if reasoning in (None, "", "off"):
        return dict(_DEEPSEEK_THINKING_OFF)
    return {"thinking": {"type": "enabled"},
            "reasoning_effort": _DEEPSEEK_EFFORT.get(reasoning, "high")}


def _thinking_rejected(status, body_text):
    """A 400 that is about thinking mode itself (missing `reasoning_content` in history, or a
    forced tool_choice), not about the user's request. Retrying with thinking off fixes it."""
    if status != 400:
        return False
    low = (body_text or "").lower()
    return "reasoning_content" in low or "thinking" in low


def _gemini_is_reasoning(model):
    """Gemini: model 'thinking' (2.5 trở lên) nhận reasoning_effort qua endpoint OpenAI-compat.
    Model cũ (1.5 / 2.0-flash không thinking) → KHÔNG gửi để tránh 400."""
    m = (model or "").lower()
    return "2.5" in m or "gemini-3" in m or "thinking" in m


# ── Ollama (Local): its OWN thinking level, not the shared Effort button (0.95.1) ─────────────────
# qwen3 and most local reasoning models think BY DEFAULT when the request says nothing. On a home machine one long think can
# eat the whole turn: a user counted CSV rows with qwen3 and got "Ollama (Local) returned nothing" after 69 s of thinking, and
# a rerun was still thinking after 5 minutes. Javis never sent a thinking switch to this provider, so nothing could stop it.
# And the Effort button is one setting for every model: "Medium" suits Claude but makes a local model ramble, "Off" tames the
# local model but takes thinking away from Claude. So Ollama (Local) reads its own level, `model.ollama_local_reasoning`,
# default "off", and the Effort button no longer reaches it.
OLLAMA_LOCAL_REASONING_DEFAULT = "off"
_OLLAMA_THINKING_OFF = {"reasoning_effort": "none"}    # Ollama's OpenAI layer maps "none" to think=false


def ollama_local_reasoning() -> str:
    """The thinking level for Ollama (Local): `model.ollama_local_reasoning`, "off" when unset or unreadable."""
    try:
        import config as cfgmod
        v = str((cfgmod.read_settings().get("model", {}) or {}).get("ollama_local_reasoning") or "").strip().lower()
    except Exception:      # noqa: BLE001 - an unreadable setting must not cost the turn; off is the safe level
        v = ""
    return v or OLLAMA_LOCAL_REASONING_DEFAULT


def _ollama_thinking(level) -> dict:
    """Payload fields for Ollama's thinking at this level. "off" is said OUT LOUD: leaving the field out is not off for qwen3,
    it is thinking at the model's own default."""
    if level in (None, "", "off"):
        return dict(_OLLAMA_THINKING_OFF)
    return {"reasoning_effort": api_effort(level)}


def _thought_without_answer(label: str) -> dict:
    """The error for a turn where the model only thought and never wrote an answer. Says what happened and what to change,
    instead of a bare "returned nothing" that sends the user hunting for a broken connection."""
    return {"type": "error", "content": _c(
        f"{label} suy nghĩ hết lượt mà chưa viết ra câu trả lời. Hạ mức suy nghĩ của model này hoặc chia việc nhỏ hơn rồi thử lại.",
        f"{label} spent the whole turn thinking and never wrote an answer. Lower this model's thinking level or split the "
        f"task into smaller steps, then try again.")}


async def _openai_compat_stream(url, label, api_key, model, messages, reasoning, send_reasoning,
                                extra_payload=None, fast_extra=None):
    """Chat Completions dạng OpenAI (dùng chung cho OpenAI + Gemini qua endpoint tương thích).
    Stream token-by-token + usage token ở chunk cuối. label chỉ dùng cho thông báo lỗi.
    extra_payload: provider-specific fields merged last (DeepSeek's thinking switch)."""
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {"model": model, "messages": messages, "stream": True,
               "stream_options": {"include_usage": True}}   # → chunk cuối kèm usage token
    if reasoning not in (None, "", "off") and send_reasoning:
        payload["reasoning_effort"] = api_effort(reasoning)
    payload.update(extra_payload or {})
    payload.update(fast_extra or {})   # Fast mode (0.164.0)
    try:
        timeout = httpx.Timeout(120.0, connect=15.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            async with _observed_stream(client, "POST", url, headers=headers, json=payload) as (r, usage_event_id):
                if r.status_code != 200:
                    body = await r.aread()
                    body_text = body.decode("utf-8", "replace")
                    if fast_extra and fast_mode.refused(r.status_code, body_text, "service_tier"):
                        yield {"type": "_fast_refused", "detail": body_text[:160]}
                        return
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
                got = thought = False
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
                        _observe_team_request(_request_usage(obj, usage_event_id))
                    delta = (obj.get("choices") or [{}])[0].get("delta") or {}
                    if delta.get("reasoning") or delta.get("reasoning_content"):
                        thought = True      # thinking text is never shown, only remembered for the error below
                    c = delta.get("content")
                    if c:
                        got = True
                        yield {"type": "text", "content": c}
                if usage:
                    yield {"type": "usage", "input": usage.get("prompt_tokens", 0), "output": usage.get("completion_tokens", 0)}
                if not got and thought:
                    yield _thought_without_answer(label)
                elif not got:
                    yield {"type": "error", "content": _c(f"{label} trả về rỗng. Thử model khác.",
                                                          f"{label} returned nothing. Try another model.")}
    except Exception as e:
        yield ev_loi_exc(_c(f"{label} lỗi", f"{label} error"), e)


async def openai_stream(api_key, model, messages, reasoning="off"):
    """OpenAI Chat Completions (provider 'openai') - chat thuần, định dạng giống OpenRouter."""
    async for ev in _fast_retry("openai", fast_mode.current(), lambda fast: _openai_compat_stream(
            OPENAI_URL, "OpenAI", api_key, model or "gpt-4o-mini", messages, reasoning,
            _openai_is_reasoning(model), fast_extra=fast_mode.compat_params("openai", fast))):
        yield ev


async def groq_stream(api_key, model, messages, reasoning="off"):
    """Groq (endpoint OpenAI-compatible, provider 'groq') - nhánh KHÔNG tool (dự phòng khi hub
    không có tool nào; đường thường là groq_chat_with_mcp)."""
    async for ev in _openai_compat_stream(GROQ_URL, "Groq", api_key, model or GROQ_DEFAULT_MODEL,
                                          messages, reasoning, _groq_is_reasoning(model)):
        yield ev


async def deepseek_stream(api_key, model, messages, reasoning="off"):
    """DeepSeek (endpoint OpenAI-compatible, provider 'deepseek') - nhánh KHÔNG tool.

    Without tools DeepSeek ignores `reasoning_content` in history, so thinking can follow the
    user's level freely here. `delta.reasoning_content` is not shown, only the answer."""
    async for ev in _openai_compat_stream(DEEPSEEK_URL, "DeepSeek", api_key,
                                          model or DEEPSEEK_DEFAULT_MODEL, messages, reasoning,
                                          False, _deepseek_thinking(reasoning)):
        yield ev


async def ollama_stream(api_key, model, messages, reasoning="off"):
    """Ollama Cloud (endpoint OpenAI-compatible, provider 'ollama') - nhánh KHÔNG tool.

    reasoning bỏ qua: `reasoning_effort` là tham số của OpenAI; model bên Ollama không hiểu,
    và gửi thừa thì có bản trả 400 chứ không im lặng bỏ qua.
    """
    async for ev in _openai_compat_stream(OLLAMA_URL, "Ollama", api_key, model,
                                          messages, reasoning, False):
        yield ev


async def ollama_local_stream(api_key, model, messages, reasoning="off"):
    """Ollama trên máy nhà - nhánh KHÔNG tool. Cùng khuôn `ollama_stream`, chỉ khác URL.

    `reasoning` (the shared Effort button) is ignored on purpose: the level is `ollama_local_reasoning()`, see the block
    above `_openai_compat_stream`. A model that cannot think at all answers a thinking request with a 400 about thinking;
    then the turn is asked again with thinking off, before any text went out."""
    url = ollama_local_url()
    if not url:
        yield {"type": "error", "content": _c("Chưa đặt địa chỉ Ollama trong trang Models.", "No Ollama address set on the Models page.")}
        return
    extra = _ollama_thinking(ollama_local_reasoning())
    while True:
        retry = False
        async for ev in _openai_compat_stream(url, "Ollama (Local)", api_key, model,
                                              messages, "off", False, extra):
            if (ev.get("type") == "error" and extra != _OLLAMA_THINKING_OFF
                    and _thinking_rejected(400, str(ev.get("content") or "")) and " 400:" in str(ev.get("content") or "")):
                retry = True
                break
            yield ev
        if not retry:
            return
        extra = dict(_OLLAMA_THINKING_OFF)


async def openai_compat_stream(api_key, model, messages, reasoning="off"):
    """Endpoint OpenAI-compatible tự khai (provider 'openai-compat') - nhánh KHÔNG tool.

    reasoning bỏ qua như Ollama: không biết model phía sau có nhận `reasoning_effort` không,
    mà gửi thừa thì có server trả 400 cho cả lượt."""
    url = openai_compat_url()
    if not url:
        yield {"type": "error", "content": _c("Chưa đặt Base URL cho OpenAI Compatible trong trang Models.", "No Base URL set for OpenAI Compatible on the Models page.")}
        return
    async for ev in _openai_compat_stream(url, "OpenAI Compatible", api_key or "none", model,
                                          messages, reasoning, False):
        yield ev


async def openai_compat_chat_with_mcp(api_key, model, messages, reasoning, mcp_tools, mcp_route):
    """Endpoint OpenAI-compatible tự khai + vòng tool-calling MCP (model phải biết gọi tool)."""
    url = openai_compat_url()
    if not url:
        yield {"type": "error", "content": _c("Chưa đặt Base URL cho OpenAI Compatible trong trang Models.", "No Base URL set for OpenAI Compatible on the Models page.")}
        return
    headers = {"Authorization": f"Bearer {api_key or 'none'}", "Content-Type": "application/json"}
    yield {"type": "meta", "model": model}
    async for ev in _cc_tool_loop(url, headers, model, messages,
                                  mcp_tools, mcp_route, {}, "OpenAI Compatible"):
        yield ev


async def ollama_local_chat_with_mcp(api_key, model, messages, reasoning, mcp_tools, mcp_route):
    """Ollama máy nhà + vòng tool-calling MCP. Model local biết gọi tool (qwen3, mistral...)
    thì có đủ đồ nghề của Javis y như mọi provider API khác."""
    url = ollama_local_url()
    if not url:
        yield {"type": "error", "content": _c("Chưa đặt địa chỉ Ollama trong trang Models.", "No Ollama address set on the Models page.")}
        return
    headers = {"Authorization": f"Bearer {api_key or 'local'}", "Content-Type": "application/json"}
    # Own thinking level, not `reasoning` (the shared Effort button): see `ollama_local_reasoning`. With thinking on, a 400
    # about thinking (a model that cannot think) drops to thinking off for the rest of the turn, the same rail as DeepSeek.
    extra = _ollama_thinking(ollama_local_reasoning())
    fallback = None if extra == _OLLAMA_THINKING_OFF else dict(_OLLAMA_THINKING_OFF)
    yield {"type": "meta", "model": model}
    async for ev in _cc_tool_loop(url, headers, model, messages,
                                  mcp_tools, mcp_route, extra, "Ollama (Local)",
                                  thinking_fallback=fallback):
        yield ev


async def gemini_stream(api_key, model, messages, reasoning="off"):
    """Google Gemini qua endpoint OpenAI-compatible (provider 'gemini') - chat thuần, cùng định dạng."""
    async for ev in _fast_retry("gemini", fast_mode.current(), lambda fast: _openai_compat_stream(
            GEMINI_URL, "Gemini", api_key, model or "gemini-2.5-flash", messages, reasoning,
            _gemini_is_reasoning(model), fast_extra=fast_mode.compat_params("gemini", fast))):
        yield ev


async def _fast_retry(provider, fast, make):
    """Run a stream with Fast mode; if the provider refuses the fast parameter before any output
    (the stream yields `_fast_refused`), run it once more without it. Fast mode never fails a turn."""
    async for ev in make(fast):
        if isinstance(ev, dict) and ev.get("type") == "_fast_refused":
            fast_mode.remember(provider, "fallback", ev.get("detail", ""))
            async for ev2 in make(False):
                yield ev2
            return
        yield ev
    if fast:
        fast_mode.remember(provider, "on")


async def anthropic_stream(api_key, model, messages, reasoning="off"):
    """Anthropic Messages API without tools; Fast mode with one retry without it (0.164.0)."""
    async for ev in _fast_retry("anthropic-api", fast_mode.current() and fast_mode.claude_supports(model or "claude-sonnet-4-6"),
                                lambda fast: _anthropic_stream_once(api_key, model, messages, reasoning, fast)):
        yield ev


async def anthropic_compat_stream(api_key, model, messages, reasoning="off"):
    """Anthropic-compatible gateway (provider 'anthropic-compat', 0.254.0) without tools: the same
    Messages API code as 'anthropic-api', sent to the owner's base URL. No Fast mode: that is an
    Anthropic beta header a reseller may not know."""
    async for ev in _anthropic_stream_once(api_key, model, messages, reasoning, False, compat=True):
        yield ev


async def _anthropic_stream_once(api_key, model, messages, reasoning="off", fast=False, compat=False):
    """Anthropic Messages API (provider 'anthropic-api') - nhánh KHÔNG tool (dự phòng khi hub
    không có tool nào; đường thường là anthropic_chat_with_mcp).
    Tách system ra field riêng (Anthropic không nhận role=system trong messages).

    CHỈ nhận API key. Bản trước có thêm tham số `oauth_token` để gói Claude Code gọi thẳng
    endpoint này bằng access token mà CLI đã lưu; Anthropic cấm đúng việc đó nên đường ấy đã
    gỡ (xem claude_auth.py). Gói Claude Code nay đi qua binary `claude`, không qua đây.
    """
    sys_parts = [m.get("content", "") for m in messages if m.get("role") == "system"]
    # Ảnh khách gửi (0.81.0) đi theo khuôn OpenAI trong Javis; Anthropic có khuôn riêng, đổi ở đây.
    conv = [{"role": m["role"], "content": vision_input.to_anthropic(m.get("content", ""))}
            for m in messages if m.get("role") in ("user", "assistant")]
    headers = anthropic_headers(api_key, compat)
    url = anthropic_compat_url() if compat else ANTHROPIC_URL
    label = "Anthropic Compatible" if compat else "Anthropic"
    lprov = "anthropic-compat" if compat else "anthropic"
    payload = {"model": model or "claude-sonnet-4-6", "max_tokens": 4096, "messages": conv, "stream": True}
    payload.update(_anthropic_reasoning(model, reasoning))   # thinking + effort + max_tokens nếu bật reasoning
    fast_h, fast_b = fast_mode.anthropic_params(payload["model"], fast)   # the model actually sent
    headers.update(fast_h)
    payload.update(fast_b)
    sys_txt = "\n\n".join(s for s in sys_parts if s)
    if sys_txt:
        payload["system"] = sys_txt
    _apply_anthropic_cache(payload)   # system + 3 msg cuối được cache → giảm ~75% input cost
    try:
        timeout = httpx.Timeout(120.0, connect=15.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            async with _observed_stream(client, "POST", url, headers=headers, json=payload) as (r, usage_event_id):
                if r.status_code != 200:
                    body = await r.aread()
                    body_text = body.decode("utf-8", "replace")
                    if fast_b and fast_mode.refused(r.status_code, body_text, "speed"):
                        yield {"type": "_fast_refused", "detail": body_text[:160]}
                        return
                    # A gateway serving a non-Claude model may not take this thinking shape: answer
                    # without it rather than fail the turn (the tool loop below does the same).
                    if compat and r.status_code == 400 and "thinking" in payload and "thinking" in body_text.lower():
                        async for ev in _anthropic_stream_once(api_key, model, messages, "off", False, compat=True):
                            yield ev
                        return
                    _fact = limit_learner.parse_limit_error(r.status_code, body_text)
                    if _fact:
                        limit_learner.remember(lprov, model, _fact)
                        yield {"type": "limit_exceeded", "provider": lprov, "model": model,
                               "kind": _fact.kind, "limit": _fact.limit,
                               "requested": _fact.requested,
                               "shrink_to": limit_learner.shrink_target(_fact),
                           "remedy": _fact.remedy, "raw": _fact.raw}
                    yield ev_loi_http(label, r.status_code, body_text, r.headers, _fact)
                    return
                yield {"type": "meta", "model": model}
                got = False
                stop_reason = None
                usage_in = usage_out = 0
                request_usage = {}
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
                        request_usage = dict(u)
                        request_usage["output_tokens"] = None
                        _observe_team_request(_request_usage({"usage": request_usage, "content": []}, usage_event_id))
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
                        if "output_tokens" in (obj.get("usage") or {}):
                            request_usage["output_tokens"] = obj["usage"]["output_tokens"]
                            _observe_team_request(_request_usage({"usage": request_usage, "content": []}, usage_event_id))
                    elif t == "error":
                        yield {"type": "error", "content": f"{label}: {(obj.get('error') or {}).get('message', _c('lỗi', 'error'))}"}
                        return
                if usage_in or usage_out:
                    yield {"type": "usage", "input": usage_in, "output": usage_out}
                if not got:
                    yield {"type": "error", "content": _c(f"{label} trả về rỗng (stop_reason={stop_reason}). Thử model khác trong Models.",
                                                          f"{label} returned nothing (stop_reason={stop_reason}). Try another model in Models.")}
                    return
                # Stream xong nhưng KHÔNG phải end_turn/stop_sequence (max_tokens / refusal / ...) → báo user
                if stop_reason and stop_reason not in ("end_turn", "stop_sequence"):
                    notes = {
                        "max_tokens": _c("⚠️ Phản hồi bị cắt do hết max_tokens. Nhắn 'tiếp tục' để model viết tiếp.",
                                         "⚠️ The reply was cut off at max_tokens. Say 'continue' to let the model keep writing."),
                        "refusal": _c("⚠️ Model từ chối phản hồi (refusal).", "⚠️ The model refused to answer (refusal)."),
                    }
                    yield {"type": "text", "content": "\n\n" + notes.get(stop_reason, _c(
                        f"⚠️ Stream kết thúc bất thường (stop_reason={stop_reason}).",
                        f"⚠️ The stream ended abnormally (stop_reason={stop_reason})."))}
    except Exception as e:
        yield ev_loi_exc(_c(f"{label} lỗi", f"{label} error"), e)


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

    if provider in ("anthropic-api", "anthropic-compat"):
        compat = provider == "anthropic-compat"
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
        headers = anthropic_headers(api_key, compat)
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(120, connect=15)) as client:
                response = await client.post(anthropic_compat_url() if compat else ANTHROPIC_URL,
                                             headers=headers, json=payload)
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
        "deepseek": (DEEPSEEK_URL, model or DEEPSEEK_DEFAULT_MODEL),
        "gemini": (GEMINI_URL, model or "gemini-2.5-flash"),
        "openrouter": (OPENROUTER_URL, model or "openai/gpt-4o-mini"),
        "ollama": (OLLAMA_URL, model),
        "openai-compat": (openai_compat_url(), model),
    }
    if provider not in endpoints or not endpoints[provider][0]:
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
    if provider == "deepseek":
        # A forced tool_choice is a 400 in DeepSeek thinking mode, and thinking is on by
        # default. This call forces exactly one tool, so thinking stays off whatever the level.
        payload.update(_DEEPSEEK_THINKING_OFF)
    elif reasoning not in (None, "", "off"):
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
    """OpenRouter without tools; Fast mode with one retry without it (0.164.0)."""
    async for ev in _fast_retry("openrouter", fast_mode.current(),
                                lambda fast: _openrouter_stream_once(api_key, model, messages, reasoning, fast)):
        yield ev


async def _openrouter_stream_once(api_key, model, messages, reasoning="off", fast=False):
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
    fast_extra = fast_mode.compat_params("openrouter", fast)
    payload.update(fast_extra)
    # Jittered retry - CHỈ cho transient (429/5xx hoặc network exception) và CHỈ khi chưa yield text.
    max_attempts = 3
    for attempt in range(1, max_attempts + 1):
        got_content = False
        scrubber = _ThinkScrubber()   # gỡ <think> inline; fresh mỗi attempt
        try:
            timeout = httpx.Timeout(120.0, connect=15.0)
            async with httpx.AsyncClient(timeout=timeout) as client:
                async with _observed_stream(client, "POST", OPENROUTER_URL, headers=headers, json=payload) as (r, usage_event_id):
                    if r.status_code != 200:
                        body = await r.aread()
                        body_text = body.decode("utf-8", "replace")
                        if fast_extra and fast_mode.refused(r.status_code, body_text, "service_tier"):
                            yield {"type": "_fast_refused", "detail": body_text[:160]}
                            return
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
                        yield {"type": "error", "content": f"OpenRouter {r.status_code}: {provider_message(body_text)[:300]}"}
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
                            _observe_team_request(_request_usage(obj, usage_event_id))
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
                            yield {"type": "error", "content": _c(
                                f"Model trả về rỗng (finish_reason={finish}). Thử lại hoặc đổi sang model khác trong Cài đặt.",
                                f"The model returned nothing (finish_reason={finish}). Retry or switch to another model in Settings.")}
                            return
                    # Stream kết thúc nhưng KHÔNG phải 'stop' (length / content_filter / ...) → user cần biết phản hồi bị cắt
                    if finish and finish != "stop":
                        notes = {
                            "length": _c("⚠️ Phản hồi bị cắt do hết max_tokens. Nhắn 'tiếp tục' để model viết tiếp.",
                                         "⚠️ The reply was cut off at max_tokens. Say 'continue' to let the model keep writing."),
                            "content_filter": _c("⚠️ Phản hồi bị lọc do bộ lọc nội dung.",
                                                 "⚠️ The reply was blocked by the content filter."),
                        }
                        yield {"type": "text", "content": "\n\n" + notes.get(finish, _c(
                            f"⚠️ Stream kết thúc bất thường (finish_reason={finish}).",
                            f"⚠️ The stream ended abnormally (finish_reason={finish})."))}
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
                yield {"type": "error", "content": _c(f"OpenRouter mạng lỗi: {_describe_exc(e)}",
                                                      f"OpenRouter network error: {_describe_exc(e)}")}
                return
            await asyncio.sleep(_jittered_backoff(attempt))
        except Exception as e:
            yield {"type": "error", "content": _c(f"OpenRouter lỗi: {_describe_exc(e)}",
                                                  f"OpenRouter error: {_describe_exc(e)}")}
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
            instructions.append(vision_input.content_text(content))
            continue
        # `content` có thể là danh sách có ẢNH khách gửi (0.81.0): đổi sang input_text/input_image.
        inp.append({"type": "message", "role": role, "content": vision_input.to_responses(content, role)})
    return "\n\n".join(s for s in instructions if s), inp


async def openai_responses_stream(access_token, account_id, model, messages, reasoning="off"):
    """ChatGPT plan (OAuth) through the Codex Responses backend; Fast mode with one retry (0.164.0)."""
    async for ev in _fast_retry("openai-oauth", fast_mode.current(), lambda fast: _openai_responses_stream_once(
            access_token, account_id, model, messages, reasoning, fast)):
        yield ev


async def _openai_responses_stream_once(access_token, account_id, model, messages, reasoning="off", fast=False):
    """Chat qua gói ChatGPT (OAuth) - backend Codex Responses API. Model: gpt-5-codex / gpt-5."""
    if not access_token:
        yield {"type": "error", "content": _c("Chưa đăng nhập ChatGPT (OAuth). Vào Models để kết nối.",
                                              "Not signed in to ChatGPT (OAuth). Go to Models to connect.")}
        return
    import uuid
    instructions, inp = _codex_input(messages)
    payload = {"model": model or "gpt-5.5", "instructions": instructions, "input": inp,
               "stream": True, "store": False}
    if reasoning not in (None, "", "off"):
        payload["reasoning"] = {"effort": api_effort(reasoning)}
    fast_extra = fast_mode.responses_params(fast)
    payload.update(fast_extra)
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
            async with _observed_stream(client, "POST", CODEX_RESPONSES_URL, headers=headers, json=payload) as (r, usage_event_id):
                if r.status_code != 200:
                    body = await r.aread()
                    body_text = body.decode("utf-8", "replace")
                    if fast_extra and fast_mode.refused(r.status_code, body_text, "service_tier"):
                        yield {"type": "_fast_refused", "detail": body_text[:160]}
                        return
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
                        _observe_team_request(_request_usage(obj.get("response") or {}, usage_event_id))
                    elif et in ("response.failed", "error", "response.error"):
                        err = (obj.get("response") or {}).get("error") or obj.get("error") or {}
                        msg = err.get("message") if isinstance(err, dict) else str(err)
                        yield {"type": "error", "content": "ChatGPT: " + (msg or _c("lỗi", "error"))}
                        return
                if usage:
                    yield {"type": "usage", "input": usage.get("input_tokens", 0), "output": usage.get("output_tokens", 0)}
                if not got:
                    yield {"type": "error", "content": _c("ChatGPT trả về rỗng. Kiểm tra gói Plus/Pro hoặc thử lại.",
                                                          "ChatGPT returned nothing. Check the Plus/Pro plan or try again.")}
    except Exception as e:
        yield ev_loi_exc(_c("ChatGPT OAuth lỗi", "ChatGPT OAuth error"), e)


# ============================================================
# MCP đa-model - vòng tool-calling để model API/OAuth dùng MCP của Javis (qua mcp_client)
# ============================================================
def _clip_tool_result(result, max_chars: int = 0, head_ratio: float = 0.6, ten: str = "") -> str:
    """Cắt kết quả tool quá dài kiểu head+tail KÈM marker, thay cho hard-cut `[:max]`.
    Tail của kết quả MCP (POS/Ads) hay chứa total/summary/pagination → cắt cụt đầu là
    mất phần đó âm thầm. Giữ đầu + cuối + dòng báo bỏ bao nhiêu → model thấy cả hai mép
    và BIẾT data bị thiếu (không tưởng đủ rồi báo sai). Port head+tail của Hermes
    code_execution_tool.

    Trần mặc định 8.000 ký tự. Các tool tự phân trang và tự cắt output của chúng (đọc file, terminal,
    tìm file, đọc web: `CAT_RONG`) được tới 60.000 (0.259.0, trước đó chỉ trong phiên Coding): cắt
    chúng ở 8.000 là cắt mất đúng chỗ cần sửa hay đúng đoạn bài cần đọc, trong khi kết quả MCP
    (báo cáo POS, danh sách đơn) vẫn giữ trần cũ để lượt chat thường không phình theo."""
    if not max_chars:
        max_chars = CAT_KET_QUA_CODING if ten in CAT_RONG else 8000
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
    text = vision_input.content_text(last).strip()

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
                        cache_system=False, thinking_fallback=None):
    """Vòng Chat Completions + tool (OpenAI/OpenRouter). Non-stream từng vòng; yield tool_call + text cuối.
    cache_system=True (OpenRouter + model Claude): đánh cache_control lên system - OpenAI/Gemini
    tự cache nên không cần.

    thinking_fallback (DeepSeek with thinking on): the payload fields that turn thinking OFF.
    Passing it means `reasoning_extra` turned thinking on, which changes three things:
      - each assistant tool-call message keeps its `reasoning_content`, because DeepSeek
        answers 400 when a thinking request with tools is missing it;
      - a turn that must force a tool runs with thinking off from the start, because a forced
        tool_choice is also a 400 in thinking mode;
      - a 400 about thinking itself (Javis history never stored `reasoning_content` for older
        turns) drops to thinking off for the rest of the turn instead of failing it."""
    import mcp_client
    tools = _mcp_to_openai_tools(mcp_tools)
    msgs = _or_mark_system(messages) if cache_system else list(messages)
    usage_in = usage_out = 0
    thinking_on = thinking_fallback is not None
    guard = _LapGuard()   # phanh chống kẹt vòng lặp (xem _LapGuard)
    # Chỉ chờ cửa sổ hạn mức MỘT lần mỗi lượt: chờ hai lần là người dùng ngồi nhìn màn hình
    # đứng im nửa phút mà không hiểu chuyện gì.
    waited_for_window = False
    # Số lần model bịa sai cú pháp gọi tool. 0 -> thử lại; 1 -> bỏ tool; 2 -> chịu, báo lỗi.
    tool_fumbles = 0
    requirement = _tool_requirement(messages, mcp_tools)
    requirement_pending = bool(requirement)
    if thinking_on and requirement_pending and tools:
        thinking_on = False
        reasoning_extra = thinking_fallback
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
    _n_vong = _max_tool_rounds()
    da_hien = False   # đã nhả chữ xem trước ở vòng nào chưa (để chèn dòng trống giữa hai vòng)
    for _vong in range(_n_vong):
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
        async def _gui(payload=payload):
            async with httpx.AsyncClient(timeout=httpx.Timeout(180, connect=15)) as client:
                r = await _observed_post(lambda: client.post(url, headers=headers, json=payload))
                # Một số endpoint OpenAI-compatible chỉ nhận "required", không nhận named choice.
                if (r.status_code in (400, 422) and requirement_pending
                        and requirement not in (None, "required")):
                    payload["tool_choice"] = "required"
                    r = await _observed_post(lambda: client.post(url, headers=headers, json=payload))
            return r
        # 0.438.5: vòng stream nhả chữ xem trước. Vòng đang ÉP gọi tool thì không: chữ ở vòng đó là
        # câu trả lời có thể bị loại (model lờ tool bắt buộc), không được hiện ra.
        stream_vong = stream_vong_bat(label) and not requirement_pending
        vong_hien = ""
        try:
            if stream_vong:
                r = None
                async for _it in _vong_stream(None, url, headers, payload, "cc"):
                    if _it["type"] != "delta":
                        r = _it["r"]
                        continue
                    if not vong_hien and da_hien:
                        yield {"type": "delta", "content": "\n\n"}
                    vong_hien += _it["content"]
                    da_hien = True
                    yield _it
                if r.status_code != 200 and _stream_bi_tu_choi(r.status_code, r.text):
                    _KHONG_STREAM_VONG.add(label)
                    print(f"[vòng stream] {label} không nhận stream, lui về non-stream: {(r.text or '')[:160]}",
                          file=sys.stderr)
                    continue
            else:
                r = await _gui_vong(_gui, label)
            if r.status_code == 200 and (reasoning_extra or {}).get("service_tier"):
                fast_mode.remember(str(label).lower(), "on")
            if r.status_code != 200:
                body_text = r.text or ""
                # Fast mode (0.164.0): the provider refused service_tier, so drop it and retry the round.
                if (reasoning_extra or {}).get("service_tier") and fast_mode.refused(r.status_code, body_text, "service_tier"):
                    reasoning_extra = {k: v for k, v in reasoning_extra.items() if k != "service_tier"}
                    fast_mode.remember(str(label).lower(), "fallback", body_text[:160])
                    continue
                if thinking_on and _thinking_rejected(r.status_code, body_text):
                    thinking_on = False
                    reasoning_extra = thinking_fallback
                    for _m in msgs:
                        if isinstance(_m, dict):
                            _m.pop("reasoning_content", None)
                    yield {"type": "tool_call", "name": "javis_thinking_off",
                           "content": _c(f"⚙ {label} không nhận chế độ suy nghĩ cho cuộc trò chuyện này, trả lời ở chế độ thường...",
                                         f"⚙ {label} refused thinking mode for this conversation, answering in normal mode...")}
                    continue
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
                               "content": _c("⚙ Model vấp cú pháp gọi công cụ, trả lời không dùng công cụ...",
                                             "⚙ The model fumbled the tool-call syntax, answering without tools...")}
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
                               "content": _c(f"⚙ Hạn mức phút này đã đầy, chờ "
                                             f"{_fact.retry_after:.0f}s rồi thử lại...",
                                             f"⚙ This minute's rate limit is full, waiting "
                                             f"{_fact.retry_after:.0f}s before retrying...")}
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
            yield ev_loi_exc(_c(f"{label} lỗi", f"{label} error"), e)
            return
        u = data.get("usage") or {}   # cộng dồn token mọi vòng (kể cả vòng gọi tool)
        usage_in += u.get("prompt_tokens", 0) or 0
        usage_out += u.get("completion_tokens", 0) or 0
        msg = ((data.get("choices") or [{}])[0]).get("message") or {}
        tcs = msg.get("tool_calls") or []
        if tcs:
            requirement_pending = False
            _asst = {"role": "assistant", "content": msg.get("content") or "", "tool_calls": tcs}
            if thinking_on and msg.get("reasoning_content"):
                _asst["reasoning_content"] = msg["reasoning_content"]
            msgs.append(_asst)
            for tc in tcs:
                fn = (tc.get("function") or {}).get("name")
                try:
                    args = json.loads((tc.get("function") or {}).get("arguments") or "{}")
                except json.JSONDecodeError:
                    args = {}
                if _schedule_tool_allowed(messages, fn, args):
                    yield {"type": "tool_call", "name": fn, "input": args}
                    result = await mcp_client.call_route(mcp_route, fn, args)
                else:
                    result = _schedule_tool_blocked_result()
                msgs.append({"role": "tool", "tool_call_id": tc.get("id"), "content": _clip_tool_result(result, ten=fn)})
            guard.ghi([((tc.get("function") or {}).get("name"),
                        (tc.get("function") or {}).get("arguments") or "") for tc in tcs])
            nhac = guard.loi_nhac() + _nhac_sap_het(_vong, _n_vong)
            if nhac:
                msgs[-1]["content"] += nhac   # nối vào kết quả tool cuối - chỗ chắc chắn model đọc
            _bs = steer_inbox.INBOX.take_note_current()   # 0.206.0: what the owner sent while this turn runs
            if _bs:
                msgs[-1]["content"] += _bs
            if guard.ket():
                if usage_in or usage_out:
                    yield {"type": "usage", "input": usage_in, "output": usage_out}
                yield {"type": "text", "content": _loi_ket_vong()}
                return
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
                "content": _c(
                    f"{label} model '{model}' đã bỏ qua tool bắt buộc nên Javis không dùng câu trả lời "
                    "có nguy cơ bịa dữ liệu. Hãy chọn model có hỗ trợ tool/function calling.",
                    f"{label} model '{model}' skipped a required tool, so Javis did not use an answer "
                    "that risks made-up data. Pick a model that supports tool/function calling."
                ),
            }
            return
        if usage_in or usage_out:
            yield {"type": "usage", "input": usage_in, "output": usage_out}
        if content:
            # streamed: chữ này đã hiện từng mẩu rồi, nơi nào đã hiện `delta` thì đừng in lại.
            yield {"type": "text", "content": content, "streamed": bool(vong_hien) and vong_hien == content}
        elif msg.get("reasoning") or msg.get("reasoning_content"):
            yield _thought_without_answer(label)
        else:
            yield {"type": "error", "content": _c(f"{label} trả về rỗng.", f"{label} returned nothing.")}
        return
    yield {"type": "text", "content": _het_vong_msg()}


# ── Trần số vòng gọi tool của engine API (Claude Code/Codex tự quản vòng lặp của chúng) ──
# Mỗi vòng = một lượt gọi model + chạy tool nó xin. Trần tồn tại vì model kẹt vòng lặp sẽ
# đốt token vô hạn mà không ai thấy. Nhưng trần ĐẾM SỐ 8 cũ bắt oan người làm việc thật
# (đọc vài file, tra vài nguồn, ghi vài file là hết 8 vòng - người dùng báo hoài, 27/08),
# trong khi ca kẹt thật thì đặc điểm không phải "nhiều vòng" mà là "lặp Y HỆT": gọi lại
# đúng tool với đúng tham số hết vòng này sang vòng khác. Nên từ 0.47.1 phanh chính là
# _LapGuard (soi đúng bệnh, cắt sớm hơn nhiều so với 8), còn trần đếm số chỉ là lưới đỡ
# xa: mặc định 30, kẹp 1-120, chỉnh bằng JAVIS_MAX_TOOL_ROUNDS.
#
# Phiên Coding (0.256.0) có trần RIÊNG, mặc định 150, kẹp 1-500, chỉnh bằng
# JAVIS_MAX_TOOL_ROUNDS_CODING: sửa một lỗi là đọc, sửa, chạy test, sửa lại, dễ quá 30 vòng mà
# không hề kẹt. main bật cờ `_PHIEN_CODING` cho đúng lượt của phiên Coding (`chay_trong_phien_coding`).
_PHIEN_CODING: contextvars.ContextVar = contextvars.ContextVar("javis_phien_coding", default=False)
CAT_KET_QUA_CODING = 60_000
CAT_RONG = frozenset({"javis_read_file", "javis_terminal", "javis_process", "javis_search_files",
                      "javis_edit_file", "javis_web_fetch", "javis_web_search", "javis_run_command"})
# Còn ngần này vòng thì nhắc model chốt việc, để lượt kết thúc bằng một bản tóm tắt chứ không bị
# cắt ngang giữa chừng.
NHAC_KHI_CON = 10


def _max_tool_rounds() -> int:
    if _PHIEN_CODING.get():
        try:
            n = int(os.getenv("JAVIS_MAX_TOOL_ROUNDS_CODING", "150"))
        except (TypeError, ValueError):
            return 150
        return max(1, min(n, 500))
    try:
        n = int(os.getenv("JAVIS_MAX_TOOL_ROUNDS", "30"))
    except (TypeError, ValueError):
        return 30
    return max(1, min(n, 120))   # kẹp: 0 thì không tool nào chạy, quá to thì mất ý nghĩa của trần


def _nhac_sap_het(vong: int, tong: int) -> str:
    """Câu nối vào kết quả tool khi lượt chỉ còn NHAC_KHI_CON vòng. "" ở mọi vòng khác."""
    if tong <= NHAC_KHI_CON * 2 or tong - vong - 1 != NHAC_KHI_CON:
        return ""
    return (f"\n\n⚠ [Javis] Lượt này chỉ còn {NHAC_KHI_CON} vòng gọi tool. Chốt việc: làm nốt bước "
            "quan trọng nhất, rồi trả lời người dùng bằng bản tóm tắt đã làm gì, còn gì dở, và bước "
            "tiếp theo nên là gì.")


async def chay_trong_phien_coding(tao_gen):
    """Bọc một generator của vòng tool để mọi vòng bên trong thấy đây là phiên Coding.

    Đặt cờ BÊN TRONG thân generator chứ không ở nơi gọi: cờ đi theo đúng task đang lặp qua
    generator, và hết lượt là trả về, không rò sang lượt sau của cùng kết nối WebSocket."""
    tok = _PHIEN_CODING.set(True)
    try:
        gen = tao_gen()
        if asyncio.iscoroutine(gen):
            gen = await gen
        async for ev in gen:
            yield ev
    finally:
        try:
            _PHIEN_CODING.reset(tok)
        except ValueError:          # generator bị dọn ở ngữ cảnh khác: cờ chết theo ngữ cảnh đó
            pass


def _het_vong_msg() -> str:
    """Chạm trần phải nói ĐƯỢC VIỆC CẦN LÀM. Bản cũ chỉ báo con số rồi im, người dùng không
    biết mình vừa mất gì hay chỉnh ở đâu."""
    n = _max_tool_rounds()
    bien, tran = (("JAVIS_MAX_TOOL_ROUNDS_CODING", 500) if _PHIEN_CODING.get()
                  else ("JAVIS_MAX_TOOL_ROUNDS", 120))
    return _c(f"\n\n⚠ Đã chạy hết {n} vòng gọi tool cho lượt này nên phải dừng, câu trả lời ở "
              f"trên có thể còn dở. Cách xử lý: chia nhỏ yêu cầu thành từng bước, hoặc nâng trần "
              f"bằng biến môi trường {bien} (tối đa {tran}) rồi khởi động lại Javis.",
              f"\n\n⚠ All {n} tool-call rounds for this turn were used, so it had to stop; the answer "
              f"above may be incomplete. To fix: split the request into steps, or raise the limit "
              f"with the environment variable {bien} (up to {tran}) and restart Javis.")


class _LapGuard:
    """Phanh chống model KẸT vòng lặp: gọi lại CÙNG bộ tool với CÙNG tham số vòng này sang
    vòng khác. Đây mới là thứ trần vòng cũ sinh ra để chống, và soi đúng bệnh thì cắt được
    ở vòng thứ 5 thay vì bắt oan mọi việc nhiều bước ở vòng thứ 8.

    Cách dùng (cả ba vòng tool dùng chung): mỗi vòng có tool_calls thì gọi `ghi(calls)` với
    calls = [(tên tool, chuỗi tham số)] của vòng đó. Lặp y hệt lần thứ NHAC thì `loi_nhac()`
    trả một câu để NỐI VÀO KẾT QUẢ TOOL cuối (chỗ duy nhất chắc chắn model đọc ở vòng sau,
    và hợp lệ với cả ba định dạng hội thoại). Vẫn lặp tới lần thứ DUNG thì `ket()` = True,
    vòng ngoài dừng hẳn bằng `_loi_ket_vong()`.

    Chủ ý chỉ so KHỚP TUYỆT ĐỐI liên tiếp: đọc-sửa-đọc lại cùng file là ba vòng khác nhau
    (vòng giữa khác chữ ký) nên không bao giờ bị bắt oan; chỉ có gọi lại y nguyên - thứ chắc
    chắn trả cùng kết quả - mới bị đếm."""
    NHAC = 3    # lặp y hệt vòng thứ 3 → nhắc thẳng vào kết quả tool
    DUNG = 5    # vẫn y hệt tới vòng thứ 5 → dừng lượt

    def __init__(self):
        self._sig = None
        self.lap = 0

    def ghi(self, calls) -> None:
        sig = json.dumps(sorted((str(n), str(a)) for n, a in calls), ensure_ascii=False)
        self.lap = self.lap + 1 if sig == self._sig else 1
        self._sig = sig

    def loi_nhac(self) -> str:
        if self.lap != self.NHAC:
            return ""
        return (f"\n\n⚠ [Javis] Bạn vừa gọi đúng tool này với đúng tham số này {self.NHAC} vòng "
                "liên tiếp - kết quả sẽ không đổi. ĐỪNG gọi lại nữa: trả lời ngay bằng dữ liệu "
                "đã có, hoặc đổi tham số nếu thật sự cần dữ liệu khác.")

    def ket(self) -> bool:
        return self.lap >= self.DUNG


def _loi_ket_vong() -> str:
    return _c(f"\n\n⚠ Model gọi lại cùng tool với cùng tham số {_LapGuard.DUNG} vòng liên tiếp "
              "(kẹt vòng lặp) nên Javis dừng lượt này để không đốt token vô ích. Câu trả lời ở "
              "trên có thể còn dở - thử hỏi lại, nói rõ hơn yêu cầu, hoặc đổi model ở trang Models.",
              f"\n\n⚠ The model called the same tool with the same arguments {_LapGuard.DUNG} rounds in a row "
              "(stuck in a loop), so Javis stopped this turn to avoid burning tokens. The answer "
              "above may be incomplete - ask again, state the request more clearly, or switch model on the Models page.")


async def openai_chat_with_mcp(api_key, model, messages, reasoning, mcp_tools, mcp_route):
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    extra = {}
    if reasoning not in (None, "", "off") and _openai_is_reasoning(model):
        extra["reasoning_effort"] = api_effort(reasoning)
    extra.update(fast_mode.compat_params("openai", fast_mode.current()))   # Fast mode (0.164.0)
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


async def deepseek_chat_with_mcp(api_key, model, messages, reasoning, mcp_tools, mcp_route):
    """DeepSeek + vòng tool-calling MCP - đủ đồ nghề của Javis như các provider API khác.

    Thinking is on by default at DeepSeek, so "off" sends an explicit switch. When the user
    asks for thinking, `_cc_tool_loop` gets `thinking_fallback` and handles DeepSeek's two
    thinking-mode rules for tool calls (see its docstring)."""
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    extra = _deepseek_thinking(reasoning)
    fallback = None if extra == _DEEPSEEK_THINKING_OFF else dict(_DEEPSEEK_THINKING_OFF)
    yield {"type": "meta", "model": model}
    async for ev in _cc_tool_loop(DEEPSEEK_URL, headers, model or DEEPSEEK_DEFAULT_MODEL, messages,
                                  mcp_tools, mcp_route, extra, "DeepSeek",
                                  thinking_fallback=fallback):
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
    extra.update(fast_mode.compat_params("gemini", fast_mode.current()))   # Fast mode (0.164.0)
    yield {"type": "meta", "model": model}
    async for ev in _cc_tool_loop(GEMINI_URL, headers, model or "gemini-2.5-flash", messages, mcp_tools, mcp_route, extra, "Gemini"):
        yield ev


async def openrouter_chat_with_mcp(api_key, model, messages, reasoning, mcp_tools, mcp_route):
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json",
               "HTTP-Referer": "http://localhost:7777", "X-Title": "Javis OS"}
    extra = {}
    if reasoning not in (None, "", "off"):
        extra["reasoning"] = {"effort": api_effort(reasoning)}
    extra.update(fast_mode.compat_params("openrouter", fast_mode.current()))   # Fast mode (0.164.0)
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
        yield {"type": "error", "content": _c("Chưa đăng nhập ChatGPT (OAuth).", "Not signed in to ChatGPT (OAuth).")}
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
    fast_extra = fast_mode.responses_params(fast_mode.current())   # Fast mode (0.164.0)
    yield {"type": "meta", "model": model}
    timeout = httpx.Timeout(180, connect=15)
    async with httpx.AsyncClient(timeout=timeout) as client:
        usage_in = usage_out = 0
        guard = _LapGuard()   # phanh chống kẹt vòng lặp (xem _LapGuard)
        _n_vong = _max_tool_rounds()
        for _vong in range(_n_vong):
            # Backend Codex BẮT BUỘC stream=True → đọc SSE, lấy response.completed.output để chạy vòng tool
            payload = {"model": model, "instructions": instructions, "input": items,
                       "tools": tools, "stream": True, "store": False}
            if reasoning not in (None, "", "off"):
                payload["reasoning"] = {"effort": api_effort(reasoning)}
            payload.update(fast_extra)
            output, round_text = [], ""
            streamed_items = {}
            completed = False
            try:
                async with _observed_stream(client, "POST", CODEX_RESPONSES_URL, headers=headers, json=payload) as (r, usage_event_id):
                    if r.status_code != 200:
                        body = await r.aread()
                        body_text = body.decode("utf-8", "replace")
                        if fast_extra and fast_mode.refused(r.status_code, body_text, "service_tier"):
                            fast_extra = {}   # Fast mode refused: drop it and retry the round
                            fast_mode.remember("openai-oauth", "fallback", body_text[:160])
                            continue
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
                    if fast_extra:
                        fast_mode.remember("openai-oauth", "on")
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
                        elif et == "response.output_item.done":
                            item = obj.get("item") or {}
                            if isinstance(item, dict) and item.get("type"):
                                key = (item.get("id") or item.get("call_id")
                                       or obj.get("output_index"))
                                if key is not None:
                                    streamed_items[key] = item
                        elif et == "response.completed":
                            completed = True
                            _resp = obj.get("response") or {}
                            output = (_resp.get("output")) or []
                            _u = _resp.get("usage") or {}
                            _observe_team_request(_request_usage(_resp, usage_event_id))
                            usage_in += _u.get("input_tokens", 0) or 0
                            usage_out += _u.get("output_tokens", 0) or 0
                        elif et in ("response.failed", "error", "response.error"):
                            err = (obj.get("response") or {}).get("error") or obj.get("error") or {}
                            msg = err.get("message") if isinstance(err, dict) else str(err)
                            yield {"type": "error", "content": "ChatGPT: " + (msg or _c("lỗi", "error"))}
                            return
            except Exception as e:
                yield ev_loi_exc(_c("ChatGPT lỗi", "ChatGPT error"), e)
                return
            if not completed:
                # A cut stream is the textbook temporary failure. `tam_thoi` lets
                # thu_lai_khi_tam_thoi run the turn again, which it only does while nothing
                # (no text, no tool call) has gone out yet, so no tool can run twice.
                yield {"type": "error", "tam_thoi": True,
                       "content": _c("ChatGPT: luồng phản hồi chưa hoàn tất.",
                                     "ChatGPT: response stream did not complete.")}
                return
            if not output:
                # Fallback to the items streamed one by one. A streamed `reasoning` item carries
                # no encrypted content (the payload does not ask for it and store is False), so
                # sending it back as input can be rejected by the API: keep only the ones that
                # can be replayed.
                output = [it for it in streamed_items.values()
                          if it.get("type") != "reasoning" or it.get("encrypted_content")]
            # A repeated SSE item must not execute a tool twice.
            unique_output, seen_calls = [], set()
            for item in output:
                if item.get("type") == "function_call":
                    call_id = item.get("call_id") or item.get("id")
                    if call_id and call_id in seen_calls:
                        continue
                    if call_id:
                        seen_calls.add(call_id)
                unique_output.append(item)
            output = unique_output
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
                        yield {"type": "tool_call", "name": fc.get("name"), "input": args}
                        result = await mcp_client.call_route(mcp_route, fc.get("name"), args)
                    else:
                        result = _schedule_tool_blocked_result()
                    items.append({"type": "function_call_output", "call_id": fc.get("call_id"), "output": _clip_tool_result(result, ten=fc.get("name") or "")})
                guard.ghi([(fc.get("name"), fc.get("arguments") or "") for fc in fcalls])
                nhac = guard.loi_nhac() + _nhac_sap_het(_vong, _n_vong)
                if nhac:
                    items[-1]["output"] += nhac   # nối vào kết quả tool cuối - chỗ chắc chắn model đọc
                _bs = steer_inbox.INBOX.take_note_current()   # 0.206.0: what the owner sent while this turn runs
                if _bs:
                    items[-1]["output"] += _bs
                if guard.ket():
                    if usage_in or usage_out:
                        yield {"type": "usage", "input": usage_in, "output": usage_out}
                    yield {"type": "text", "content": _loi_ket_vong()}
                    return
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
                yield {"type": "error", "content": _c("ChatGPT trả về rỗng (backend Codex có thể chưa hỗ trợ tool).",
                                                      "ChatGPT returned nothing (the Codex backend may not support tools yet).")}
            return
        yield {"type": "text", "content": _het_vong_msg()}


async def anthropic_compat_chat_with_mcp(api_key, model, messages, reasoning, mcp_tools, mcp_route):
    """Tool loop for provider 'anthropic-compat' (0.254.0): the Anthropic loop below, sent to the
    owner's gateway. A separate name so callers and tests can tell the two providers apart."""
    async for ev in anthropic_chat_with_mcp(api_key, model, messages, reasoning, mcp_tools, mcp_route, compat=True):
        yield ev


async def anthropic_chat_with_mcp(api_key, model, messages, reasoning, mcp_tools, mcp_route, compat=False):
    """Anthropic Messages API + vòng tool-calling MCP - gỡ hạn chế 'anthropic-api = chat thuần'.
    Non-stream từng vòng (như _cc_tool_loop); yield meta/tool_call/text/error thống nhất.

    CHỈ nhận API key, cùng lý do với `anthropic_stream`: tham số `oauth_token` cũ cho phép gói
    Claude Code chạy vòng tool bằng token của chính CLI, và đó là thứ Anthropic cấm. Gói ấy nay
    chạy vòng tool bằng engine Claude Code thật (`main._claude_sub_stream_tools`).
    """
    import mcp_client
    sys_txt = "\n\n".join(m.get("content", "") for m in messages if m.get("role") == "system")
    conv = [{"role": m["role"], "content": vision_input.to_anthropic(m.get("content", ""))}
            for m in messages if m.get("role") in ("user", "assistant")]
    headers = anthropic_headers(api_key, compat)
    url = anthropic_compat_url() if compat else ANTHROPIC_URL
    label = "Anthropic Compatible" if compat else "Anthropic"
    lprov = "anthropic-compat" if compat else "anthropic"
    tools = [{"name": t["fn"], "description": (t.get("description") or t["fn"])[:1024],
              "input_schema": t.get("schema") or {"type": "object", "properties": {}}} for t in mcp_tools]
    if tools:
        tools[-1]["cache_control"] = {"type": "ephemeral"}   # tools = prefix ổn định, cache 1 lần đủ
    yield {"type": "meta", "model": model}
    extras = _anthropic_reasoning(model, reasoning)
    fast_h, fast_b = fast_mode.anthropic_params(model or "claude-sonnet-4-6", fast_mode.current())   # Fast mode (0.164.0)
    if compat:
        fast_h, fast_b = {}, {}   # an Anthropic beta header; a reseller may reject it
    timeout = httpx.Timeout(180, connect=15)
    async with httpx.AsyncClient(timeout=timeout) as client:
        usage_in = usage_out = 0
        guard = _LapGuard()   # phanh chống kẹt vòng lặp (xem _LapGuard)
        _n_vong = _max_tool_rounds()
        da_hien = False   # 0.438.5: đã nhả chữ xem trước ở vòng nào chưa
        for _vong in range(_n_vong):
            # Cache theo lối không-mutate (system dựng mới mỗi vòng, conv copy-khi-đánh-dấu)
            # → marker KHÔNG tích luỹ qua vòng tool, tối đa 3 breakpoint/request (trần API là 4).
            # Vòng tool là nơi cache lãi nhất: mỗi vòng 1 request chở lại nguyên system+tools+conv.
            payload = {"model": model or "claude-sonnet-4-6", "max_tokens": 4096,
                       "messages": _anthropic_mark_last(conv), "tools": tools, "stream": False}
            payload.update(extras or {})
            payload.update(fast_b)
            if sys_txt:
                payload["system"] = [{"type": "text", "text": sys_txt, "cache_control": {"type": "ephemeral"}}]
            vong_hien = ""
            try:
                if stream_vong_bat(lprov):
                    r = None
                    async for _it in _vong_stream(client, url, {**headers, **fast_h}, payload, "anthropic"):
                        if _it["type"] != "delta":
                            r = _it["r"]
                            continue
                        if not vong_hien and da_hien:
                            yield {"type": "delta", "content": "\n\n"}
                        vong_hien += _it["content"]
                        da_hien = True
                        yield _it
                    if r.status_code != 200 and _stream_bi_tu_choi(r.status_code, r.text):
                        _KHONG_STREAM_VONG.add(lprov)
                        print(f"[vòng stream] {label} không nhận stream, lui về non-stream: {(r.text or '')[:160]}",
                              file=sys.stderr)
                        continue
                else:
                    r = await _gui_vong(lambda: _observed_post(
                        lambda: client.post(url, headers={**headers, **fast_h}, json=payload)),
                                        label)
            except Exception as e:
                yield ev_loi_exc(_c(f"{label} lỗi", f"{label} error"), e)
                return
            if fast_b and fast_mode.refused(r.status_code, r.text or "", "speed"):
                fast_h, fast_b = {}, {}   # Fast mode refused: drop it and retry the round
                fast_mode.remember("anthropic-api", "fallback", (r.text or "")[:160])
                continue
            if r.status_code == 200 and fast_b:
                fast_mode.remember("anthropic-api", "on")
            if r.status_code == 400 and extras and "thinking" in (r.text or "").lower():
                extras = {}   # thinking không tương thích payload/tool này → bỏ thinking, thử lại
                continue
            if r.status_code != 200:
                body_text = r.text or ""
                _fact = limit_learner.parse_limit_error(r.status_code, body_text)
                if _fact:
                    limit_learner.remember(lprov, model, _fact)
                    yield {"type": "limit_exceeded", "provider": lprov, "model": model,
                           "kind": _fact.kind, "limit": _fact.limit,
                           "requested": _fact.requested,
                           "shrink_to": limit_learner.shrink_target(_fact),
                           "remedy": _fact.remedy, "raw": _fact.raw}
                yield ev_loi_http(label, r.status_code, body_text, r.headers, _fact)
                return
            try:
                data = r.json()
            except Exception:
                yield {"type": "error", "content": _c(f"{label} trả về không phải JSON.", f"{label} did not return JSON.")}
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
                        yield {"type": "tool_call", "name": tu.get("name"), "input": args}
                        res = await mcp_client.call_route(mcp_route, tu.get("name"), args)
                    else:
                        res = _schedule_tool_blocked_result()
                    results.append({"type": "tool_result", "tool_use_id": tu.get("id"),
                                    "content": _clip_tool_result(res, ten=tu.get("name") or "")})
                guard.ghi([(tu.get("name"), json.dumps(tu.get("input") or {}, sort_keys=True,
                                                       ensure_ascii=False)) for tu in tool_uses])
                nhac = guard.loi_nhac() + _nhac_sap_het(_vong, _n_vong)
                if nhac:
                    results[-1]["content"] += nhac   # nối vào kết quả tool cuối - chỗ chắc chắn model đọc
                _bs = steer_inbox.INBOX.take_note_current()   # 0.206.0: what the owner sent while this turn runs
                if _bs:
                    results.append({"type": "text", "text": _bs})
                conv.append({"role": "user", "content": results})
                if guard.ket():
                    if usage_in or usage_out:
                        yield {"type": "usage", "input": usage_in, "output": usage_out}
                    yield {"type": "text", "content": _loi_ket_vong()}
                    return
                continue
            text = "".join(b.get("text", "") for b in blocks if b.get("type") == "text")
            if usage_in or usage_out:
                yield {"type": "usage", "input": usage_in, "output": usage_out}
            if text:
                yield {"type": "text", "content": text, "streamed": bool(vong_hien) and vong_hien == text}
            else:
                yield {"type": "error", "content": _c(f"{label} trả về rỗng. Thử model khác trong Models.",
                                                      f"{label} returned nothing. Try another model in Models.")}
            return
        yield {"type": "text", "content": _het_vong_msg()}
