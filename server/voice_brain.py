"""Bộ não GIỌNG NÓI riêng (Voice V2, docs/dev/2026-09-voice-v2-spec.md mục 2).

Khi người dùng NÓI với Javis, lượt đi qua một bộ não nhanh và nhẹ ở đây thay vì bộ não chính
(vốn dựng tiến trình, nạp MCP và prompt dài, mất 5-10 giây mới ra chữ đầu). Bộ não giọng trả
lời ngắn, và khi câu hỏi cần dữ liệu, tool, file, ký ức hay hành động thì nó trả đúng một dòng
`JAVIS_ASK_MAIN: <yêu cầu>`; main.py đọc dòng đó rồi chạy lượt bộ não chính như thường.

Hai loại bộ não:
  - AntigravityVoiceBrain: MỘT tiến trình `agy --input-format stream-json` sống suốt phiên
    nói. Đo 2026-09-14: lượt đầu 4,2 s (khởi động), lượt sau 1,3-2,0 s, stream từng mảnh
    chữ qua `step_update.text_delta`. Chạy trên gói Google đã có, không cần API key.
  - ApiVoiceBrain: Groq / Gemini / OpenAI / OpenRouter qua các hàm stream sẵn có trong
    engine.py, dùng key ở trang Models.

Sổ phiên: mỗi phiên chat web một bộ não, đóng sau IDLE_S giây không nói. Không import main.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import sys
import time
from typing import AsyncIterator, Callable, Dict, List, Optional

import winproc         # lệnh con câm lặng trên Windows (canary test_windows_no_console)

MARKER = "JAVIS_ASK_MAIN:"
IDLE_S = 300.0
TURN_TIMEOUT_S = 90.0
HISTORY_N = 10
PROVIDERS = ("antigravity", "groq", "gemini", "openai", "openrouter")

SYSTEM_PROMPT = (
    "Bạn là Javis, trợ lý cá nhân, đang NÓI CHUYỆN BẰNG GIỌNG với người dùng. Trả lời như người "
    "đang nói: ngắn (1 đến 3 câu), tự nhiên, không markdown, không gạch đầu dòng, không emoji, "
    "không dấu gạch dài. Trả lời bằng đúng ngôn ngữ người dùng vừa dùng.\n"
    "Bạn KHÔNG có tool và KHÔNG biết dữ liệu sống. Khi câu hỏi cần bất kỳ thứ nào sau đây: số liệu "
    "kinh doanh, lịch, email, file hay ghi chú trong brain, ký ức dài hạn, giao việc, nhắc hẹn, mở "
    "trang hay mở app, gửi tin, hay bất cứ hành động nào ra ngoài, thì KHÔNG đoán và KHÔNG bịa. Thay "
    "vào đó trả lời đúng khuôn này: tuỳ chọn một câu chờ ngắn ở dòng đầu (ví dụ 'Để mình xem.'), rồi "
    "một dòng riêng bắt đầu bằng " + MARKER + " theo sau là yêu cầu đầy đủ để bộ não chính của Javis "
    "thực hiện. Không viết gì sau dòng đó.\n"
    "Chuyện trò thường, hỏi ý kiến, giải thích khái niệm, tính nhẩm, chuyển ngữ: trả lời thẳng."
)

_MARK_RE = re.compile(r"^[ \t]*" + re.escape(MARKER) + r"[ \t]*(.+?)[ \t]*$", re.M)


def parse_marker(text: str):
    """(câu chờ, yêu cầu cho bộ não chính | None). Bỏ dòng marker khỏi câu chờ."""
    t = str(text or "")
    m = _MARK_RE.search(t)
    if not m:
        return t.strip(), None
    filler = t[:m.start()].strip()
    return filler, m.group(1).strip()


def build_messages(history: List[dict], text: str, system: str = SYSTEM_PROMPT) -> List[dict]:
    msgs = [{"role": "system", "content": system}]
    for h in (history or [])[-HISTORY_N:]:
        role = "assistant" if h.get("role") == "assistant" else "user"
        c = str(h.get("content") or "").strip()
        if c:
            msgs.append({"role": role, "content": c[:2000]})
    msgs.append({"role": "user", "content": str(text or "")})
    return msgs


class VoiceBrain:
    provider = ""
    model = ""

    def __init__(self):
        self.last_used = time.time()
        self._lock = asyncio.Lock()

    async def stream(self, text: str, history: List[dict]) -> AsyncIterator[str]:  # pragma: no cover
        raise NotImplementedError
        yield ""

    async def close(self) -> None:
        return None


class ApiVoiceBrain(VoiceBrain):
    """Groq / Gemini / OpenAI / OpenRouter qua engine.<prov>_stream."""

    def __init__(self, provider: str, api_key: str, model: str, stream_fn: Optional[Callable] = None):
        super().__init__()
        self.provider = provider
        self.api_key = api_key
        self.model = model
        self._stream_fn = stream_fn

    def _fn(self):
        if self._stream_fn:
            return self._stream_fn
        import engine
        return {
            "groq": engine.groq_stream, "gemini": engine.gemini_stream,
            "openai": engine.openai_stream, "openrouter": engine.openrouter_stream,
        }[self.provider]

    async def stream(self, text: str, history: List[dict]) -> AsyncIterator[str]:
        self.last_used = time.time()
        msgs = build_messages(history, text)
        async with self._lock:
            async for ev in self._fn()(self.api_key, self.model, msgs, "off"):
                t = ev.get("type")
                if t == "text" and ev.get("content"):
                    yield ev["content"]
                elif t == "error":
                    raise RuntimeError(str(ev.get("content") or "lỗi provider"))


class AntigravityVoiceBrain(VoiceBrain):
    """Một tiến trình `agy` sống lâu, nhận từng lượt qua stdin NDJSON.

    Khuôn stdin dò ra 2026-09-14 (không có trong help): `{"event":"user","message":{"role":
    "user","content":"..."}}`. Tên sự kiện khác bị bỏ qua, `message` là chuỗi thì tiến trình
    THOÁT. Sự kiện ra: `init`, `step_update` (text_delta khi step_type=agent_response),
    `result` (status SUCCESS|ERROR, response, error).

    `agy` không có cờ system prompt, nên hướng dẫn được ghép vào ĐẦU lượt đầu tiên của mỗi
    tiến trình, kèm mấy lượt gần nhất từ kho phiên để mạch không đứt khi tiến trình mở lại.
    """
    provider = "antigravity"

    def __init__(self, model: str = "", cli_path: str = "", spawn: Optional[Callable] = None):
        super().__init__()
        self.model = model
        self.cli_path = cli_path
        self._spawn = spawn          # test tiêm tiến trình giả
        self.proc = None
        self._seeded = False
        self.turns = 0

    def _args(self) -> List[str]:
        args = [self.cli_path]
        if self.model:
            args += ["--model", self.model]
        args += ["--input-format", "stream-json", "--output-format", "stream-json"]
        return args

    async def _ensure(self):
        if self.proc is not None and self.proc.returncode is None:
            return
        if not self.cli_path and not self._spawn:
            raise RuntimeError("Chưa cài Antigravity CLI (agy).")
        if self._spawn:
            self.proc = await self._spawn(self._args())
        else:
            self.proc = await asyncio.create_subprocess_exec(
                *self._args(), stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL, **winproc.kwargs_no_window())
        self._seeded = False
        self.turns = 0

    def _seed_text(self, history: List[dict], text: str) -> str:
        parts = ["[HƯỚNG DẪN CHO LƯỢT NÓI CHUYỆN NÀY]\n" + SYSTEM_PROMPT]
        h = [x for x in (history or [])[-HISTORY_N:] if str(x.get("content") or "").strip()]
        if h:
            parts.append("[MẤY LƯỢT GẦN NHẤT TRONG PHIÊN NÀY]")
            for x in h:
                ai = "Javis" if x.get("role") == "assistant" else "Người dùng"
                parts.append(f"{ai}: {str(x.get('content'))[:1500]}")
        parts.append("[NGƯỜI DÙNG VỪA NÓI]\n" + str(text or ""))
        return "\n\n".join(parts)

    async def stream(self, text: str, history: List[dict]) -> AsyncIterator[str]:
        self.last_used = time.time()
        async with self._lock:
            await self._ensure()
            content = text if self._seeded else self._seed_text(history, text)
            self._seeded = True
            self.turns += 1
            line = json.dumps({"event": "user", "message": {"role": "user", "content": content}},
                              ensure_ascii=False) + "\n"
            self.proc.stdin.write(line.encode("utf-8"))
            await self.proc.stdin.drain()
            got_delta = False
            deadline = time.time() + TURN_TIMEOUT_S
            while True:
                left = deadline - time.time()
                if left <= 0:
                    await self.close()
                    raise RuntimeError("Antigravity không trả lời trong 90 giây.")
                try:
                    raw = await asyncio.wait_for(self.proc.stdout.readline(), timeout=left)
                except asyncio.TimeoutError:
                    await self.close()
                    raise RuntimeError("Antigravity không trả lời trong 90 giây.")
                if not raw:
                    await self.close()
                    raise RuntimeError("Antigravity đóng tiến trình giữa chừng.")
                try:
                    ev = json.loads(raw.decode("utf-8", "ignore"))
                except Exception:
                    continue
                kind = ev.get("event")
                if kind == "step_update":
                    su = ev.get("step_update") or {}
                    if su.get("step_type") == "agent_response" and su.get("text_delta"):
                        got_delta = True
                        yield str(su["text_delta"])
                elif kind == "result":
                    r = ev.get("result") or {}
                    if r.get("status") != "SUCCESS":
                        raise RuntimeError(str(r.get("error") or "Antigravity báo lỗi."))
                    if not got_delta and r.get("response"):
                        yield str(r["response"])
                    return

    async def close(self) -> None:
        p, self.proc = self.proc, None
        self._seeded = False
        if p is None:
            return
        try:
            if p.stdin:
                p.stdin.close()
        except Exception:
            pass
        try:
            if p.returncode is None:
                p.kill()
        except Exception:
            pass
        # Đợi tiến trình khép hẳn để transport asyncio đóng pipe ngay bây giờ, không phải lúc
        # event loop đã đóng (khi đó Windows ném "I/O operation on closed pipe" ra stderr).
        try:
            await asyncio.wait_for(p.wait(), timeout=3.0)
        except Exception:
            pass


# ============================================================
# Sổ phiên
# ============================================================
_BRAINS: Dict[str, VoiceBrain] = {}
_REAPER: Optional[asyncio.Task] = None


def config_from_settings(cfg: dict) -> dict:
    v = (cfg or {}).get("voice") or {}
    m = (cfg or {}).get("model") or {}
    prov = str(v.get("brain_provider") or "").strip().lower()
    keys = {"groq": m.get("groq_api_key", ""), "gemini": m.get("gemini_api_key", ""),
            "openai": m.get("openai_api_key", ""), "openrouter": m.get("openrouter_key", "")}
    return {"mode": str(v.get("mode") or "standard"), "provider": prov,
            "model": str(v.get("brain_model") or "").strip(), "api_key": keys.get(prov, "")}


def _make(conf: dict) -> VoiceBrain:
    prov = conf.get("provider") or ""
    if prov == "antigravity":
        try:
            import antigravity_cli
            cli = antigravity_cli.find_antigravity_cli() or ""
        except Exception:
            cli = ""
        return AntigravityVoiceBrain(model=conf.get("model") or "", cli_path=cli)
    if prov in ("groq", "gemini", "openai", "openrouter"):
        if not conf.get("api_key"):
            raise RuntimeError(f"Bộ não giọng nói {prov} chưa có API key ở trang Models.")
        default = {"groq": "llama-3.3-70b-versatile", "gemini": "gemini-2.5-flash",
                   "openai": "gpt-4o-mini", "openrouter": "google/gemini-2.5-flash"}[prov]
        return ApiVoiceBrain(prov, conf["api_key"], conf.get("model") or default)
    raise RuntimeError("Chưa chọn bộ não giọng nói.")


async def get_brain(session_id: str, conf: dict) -> VoiceBrain:
    """Bộ não cho phiên này; đổi provider/model trong cài đặt thì dựng lại."""
    key = str(session_id or "default")
    b = _BRAINS.get(key)
    want = (conf.get("provider") or "", conf.get("model") or "")
    if b is not None and (b.provider, b.model) != want:
        await b.close()
        b = None
    if b is None:
        b = _make(conf)
        _BRAINS[key] = b
    _start_reaper()
    return b


def _start_reaper():
    global _REAPER
    if _REAPER is not None and not _REAPER.done():
        return
    try:
        _REAPER = asyncio.get_running_loop().create_task(_reap())
    except RuntimeError:
        pass


async def _reap():
    while True:
        await asyncio.sleep(30)
        now = time.time()
        for k, b in list(_BRAINS.items()):
            if now - b.last_used > IDLE_S:
                _BRAINS.pop(k, None)
                try:
                    await b.close()
                except Exception:
                    pass
        if not _BRAINS:
            return


async def close_all():
    for k, b in list(_BRAINS.items()):
        _BRAINS.pop(k, None)
        try:
            await b.close()
        except Exception:
            pass


def active_count() -> int:
    return len(_BRAINS)
