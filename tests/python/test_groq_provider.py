"""Regression: provider Groq đấu ĐỦ mọi tầng, không sót chỗ nào.

Thêm một provider phải chạm 7 chỗ rời nhau (PROVIDER_DEFS, config mặc định, danh sách khoá
bí mật, _api_stream, _api_stream_mcp, aux_engine, KEYFIELD trên giao diện). Sót một chỗ là
lỗi câm: provider hiện ra ở trang Models nhưng chat thì rơi về nhánh mặc định, hoặc key
không được mã hoá, hoặc chọn làm model việc nền thì nổ KeyError lúc chạy nền.

Groq dùng endpoint OpenAI-compatible nên đi chung `_openai_compat_stream` / `_cc_tool_loop`
với OpenAI và Gemini - test này chốt phần ĐẤU DÂY, còn phần vòng lặp chung đã có test riêng.

Chạy:
    .venv/Scripts/python.exe tests/python/test_groq_provider.py
"""
import asyncio
import json
import os
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-groq-test-"))

from _paths import ROOT, SERVER  # noqa: E402,F401  - nạp server/ vào sys.path

import aux_engine  # noqa: E402
import config as cfgmod  # noqa: E402
import engine  # noqa: E402
import main  # noqa: E402

CONSOLE_JS = (ROOT / "dashboard" / "console.js").read_text(encoding="utf-8")

fails = []


def check(name: str, condition: bool) -> None:
    print(("PASS: " if condition else "FAIL: ") + name)
    if not condition:
        fails.append(name)


# ─────────── 1. Đấu dây: có mặt ở mọi bảng ───────────
_defs = {p["id"]: p for p in main.PROVIDER_DEFS}
check("có trong PROVIDER_DEFS", "groq" in _defs)
_g = _defs.get("groq") or {}
check("kind=api (đi đường gọi API thẳng)", _g.get("kind") == "api")
check("khai đúng key_field", _g.get("key_field") == "groq_api_key")
check("có model mặc định để picker không rỗng khi chưa gọi được mạng",
      len(_g.get("default_models") or []) > 0)

check("config có ô groq_api_key", "groq_api_key" in cfgmod._DEFAULT["model"])
check("config có catalog groq", "groq" in cfgmod._DEFAULT["model"]["catalog"])
check("khoá Groq nằm trong danh sách MÃ HOÁ (không nằm thì key ghi thẳng plaintext ra đĩa)",
      "model.groq_api_key" in cfgmod._SECRET_PATHS)

check("aux_engine coi groq là provider API", "groq" in aux_engine.API_PROVIDERS)
check("aux_engine map được key field", aux_engine._KEY_FIELD.get("groq") == "groq_api_key")

check("giao diện biết ô nhập key nào là của groq", '"groq": "groq_api_key"' in CONSOLE_JS)

check("_api_label có tên người đọc được", main._api_label("groq") == "Groq")
_cfg = {"model": {}}
main._set_main_model(_cfg, "groq", "llama-3.3-70b-versatile")
check("_set_main_model ghi đúng engine + main", _cfg["model"]["engine"] == "groq"
      and _cfg["model"]["main"] == {"provider": "groq", "model": "llama-3.3-70b-versatile"})


# ─────────── 2. Chạy thật với máy chủ Groq giả lập ───────────
SEEN = []


class _Fake(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        SEEN.append({"auth": self.headers.get("Authorization"), "body": body})
        has_tools = bool(body.get("tools"))
        first = has_tools and not any(m.get("role") == "tool" for m in body["messages"])
        if body.get("stream"):
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            for ch in ("Xin ", "chào ", "từ Groq"):
                self.wfile.write(b"data: " + json.dumps({"choices": [{"delta": {"content": ch}}]}).encode() + b"\n\n")
            self.wfile.write(b"data: [DONE]\n\n")
            return
        msg = ({"role": "assistant", "content": None,
                "tool_calls": [{"id": "c1", "type": "function",
                                "function": {"name": "javis_connections", "arguments": "{}"}}]}
               if first else {"role": "assistant", "content": "Đã gọi tool xong"})
        out = {"choices": [{"message": msg, "finish_reason": "tool_calls" if first else "stop"}],
               "usage": {"prompt_tokens": 10, "completion_tokens": 5}}
        raw = json.dumps(out).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


_srv = HTTPServer(("127.0.0.1", 0), _Fake)
threading.Thread(target=_srv.serve_forever, daemon=True).start()
engine.GROQ_URL = f"http://127.0.0.1:{_srv.server_address[1]}/openai/v1/chat/completions"

TOOLS = [{"fn": "javis_connections", "server": "javis", "name": "javis_connections",
          "description": "liệt kê nguồn", "schema": {"type": "object", "properties": {}, "required": []}}]


async def _call(_args):
    return "Kết nối: POS, Lịch"


ROUTE = {"javis_connections": {"call": _call}}


async def _run():
    text = ""
    async for ev in engine.groq_stream("gsk_test", "llama-3.3-70b-versatile",
                                       [{"role": "user", "content": "chào"}], "off"):
        if ev["type"] == "text":
            text += ev["content"]
    check(f"chat thuần stream ra chữ (nhận: {text!r})", text == "Xin chào từ Groq")

    kinds, called = [], []
    async for ev in engine.groq_chat_with_mcp("gsk_test", "llama-3.3-70b-versatile",
                                              [{"role": "user", "content": "có nguồn nào"}],
                                              "off", TOOLS, ROUTE):
        kinds.append(ev["type"])
        if ev["type"] == "tool_call":
            called.append(ev.get("name"))
    check("vòng tool MCP gọi được tool", called == ["javis_connections"])
    check("và trả về chữ sau khi có kết quả tool", "text" in kinds)

    # reasoning_effort gửi nhầm cho model thường là Groq trả 400 -> phải lọc theo model.
    for mdl, want in (("llama-3.3-70b-versatile", None), ("qwen3-32b", "high")):
        SEEN.clear()
        async for _ in engine.groq_chat_with_mcp("gsk_test", mdl, [{"role": "user", "content": "x"}],
                                                 "high", TOOLS, ROUTE):
            pass
        got = SEEN[0]["body"].get("reasoning_effort")
        check(f"reasoning_effort với {mdl} = {want!r} (nhận {got!r})", got == want)
    check("gửi key bằng header Bearer", SEEN[0]["auth"] == "Bearer gsk_test")


asyncio.run(_run())

# _api_stream / _api_stream_mcp phải trỏ vào đúng hàm Groq, không rơi về nhánh mặc định
# (nhánh cuối của _api_stream_goc là anthropic_stream - sót là chat Groq đi gọi Anthropic).
_gen = main._api_stream_goc("groq", "k", "m", [{"role": "user", "content": "x"}], "off")
check("_api_stream chọn đúng generator của Groq", _gen.__qualname__.startswith("groq_stream"))
_gen.aclose() if hasattr(_gen, "aclose") else None

# Và lượt chat thật phải đi qua lớp thử-lại, không gọi thẳng generator gốc: nhà cung cấp trả
# 429 một nhịp mà bỏ cuộc ngay là chuyện đã xảy ra thật với bot chuyên trách.
_boc = main._api_stream("groq", "k", "m", [{"role": "user", "content": "x"}], "off")
check("_api_stream bọc lớp thử lại khi gãy tạm thời",
      _boc.__qualname__.startswith("thu_lai_khi_tam_thoi"))
_boc.aclose() if hasattr(_boc, "aclose") else None


if fails:
    raise SystemExit(f"\nFAIL - test_groq_provider: {len(fails)} lỗi")
print("\nOK - test_groq_provider: tất cả pass")
