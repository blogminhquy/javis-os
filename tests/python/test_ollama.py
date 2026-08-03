"""Nhà cung cấp Ollama Cloud.

    python tests/run.py ollama

Bản 0.16.0 đấu CẢ hai đường của Ollama: chạy trên máy nhà và chạy trên Cloud. Chủ repo dùng
Javis trên VPS nên chỉ cần Cloud, và yêu cầu gỡ hẳn phần máy nhà.

Gỡ đi là được nhiều hơn mất về mặt mã: đường máy nhà đòi một ô ĐỊA CHỈ riêng, tức là
`host_field` - ca đặc biệt duy nhất xuyên suốt lớp nhà cung cấp, kéo theo một nhánh riêng ở
`_providers_view`, một nhánh riêng ở thẻ giao diện, và một hàm chọn-đường-theo-key. Bỏ hết,
Ollama thành đúng hình dạng của Groq hay Gemini: dán key là chạy.

File này canh hai thứ. Một, Ollama Cloud chạy thật: lượt chat đi đúng nhánh của nó chứ không
rơi về nhánh Anthropic mặc định cuối `_api_stream` - nhánh nuốt mọi provider quên đấu, và nuốt
trong im lặng. Hai, phần máy nhà đã đi sạch, không để lại mẩu nào còn sống nửa vời.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import os
import sys
import tempfile
import types

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-ollama-")

import config as cfg  # noqa: E402
import engine  # noqa: E402
import main  # noqa: E402

_fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)


# ---- 1. Là một provider API bình thường, không còn ca đặc biệt ----
_p = main._provider_def("ollama")
check("có nhà cung cấp ollama", bool(_p))
check("thuộc nhóm API (đi qua hub, không chạy lệnh máy)", _p.get("kind") == "api")
check("nhận diện bằng API key như mọi provider API", _p.get("key_field") == "ollama_key")
check("CANARY: không còn ô địa chỉ riêng", "host_field" not in _p)
check("nhãn nói rõ đây là bản Cloud", "Cloud" in (_p.get("label") or ""))
# Danh sách model của Ollama đổi luôn; /provider/models nạp bản LIVE nên đoán hộ là bày ra
# những cái tài khoản người dùng không có.
check("không đoán hộ danh sách model", _p.get("default_models") == [])
check("key có chỗ trong cấu hình mặc định", "ollama_key" in (cfg._DEFAULT["model"] or {}))
check("CANARY: key được mã hoá như mọi key khác", "model.ollama_key" in cfg._SECRET_PATHS)
check("CANARY: cấu hình không còn ô địa chỉ", "ollama_host" not in (cfg._DEFAULT["model"] or {}))


# ---- 2. Endpoint cố định, không dựng từ cấu hình nữa ----
check("gọi thẳng máy chủ Ollama Cloud", engine.OLLAMA_BASE == "https://ollama.com")
check("dùng đường chat chuẩn OpenAI", engine.OLLAMA_URL == "https://ollama.com/v1/chat/completions")
_esrc = (ROOT / "server" / "engine.py").read_text(encoding="utf-8")
check("CANARY: không còn hàm dựng URL theo địa chỉ", "def ollama_url(" not in _esrc)
check("CANARY: không còn địa chỉ máy nhà trong mã", "11434" not in _esrc)


# ---- 3. Chọn làm model chính thì mọi đường đều trỏ về Ollama ----
_c = {"model": dict(cfg._DEFAULT["model"])}
main._set_main_model(_c, "ollama", "gpt-oss:120b-cloud")
check("đặt được làm model chính",
      _c["model"]["main"] == {"provider": "ollama", "model": "gpt-oss:120b-cloud"})
check("engine legacy khớp theo", _c["model"]["engine"] == "ollama")
_c["model"]["ollama_key"] = "sk-cloud-test"
_prov, _kind, _key, _model = main._chat_provider(_c["model"])
check("lượt chat định tuyến về ollama", _prov == "ollama" and _kind == "api")
check("CANARY: mang đúng key vào lượt chat", _key == "sk-cloud-test")
check("giữ đúng model đã chọn", _model == "gpt-oss:120b-cloud")


# ---- 4. Lượt chat THẬT SỰ đi vào nhánh Ollama ----
# `_api_stream` kết thúc bằng `return engine.anthropic_stream(...)` - nhánh mặc định nuốt mọi
# provider quên đấu, và nuốt trong im lặng: không lỗi, chỉ là câu hỏi bay sang Anthropic với
# key của Ollama rồi báo lỗi xác thực chẳng liên quan gì.
_goi = {}
_goc = (engine.ollama_stream, engine.ollama_chat_with_mcp, engine.anthropic_stream)


async def _gia_stream(api_key, model, messages, reasoning="off"):
    _goi["stream"] = {"key": api_key, "model": model}
    yield {"type": "text", "content": "ok"}


async def _gia_anthropic(*a, **k):
    _goi["anthropic"] = True
    yield {"type": "text", "content": "sai nhánh"}


async def _gia_mcp(api_key, model, messages, reasoning, tools, route):
    _goi["mcp"] = {"key": api_key, "model": model, "tools": len(tools or [])}
    yield {"type": "text", "content": "ok"}


engine.ollama_stream, engine.ollama_chat_with_mcp = _gia_stream, _gia_mcp
engine.anthropic_stream = _gia_anthropic
try:
    async def _chay():
        gen = main._api_stream("ollama", "sk-cloud-test", "gpt-oss:120b-cloud",
                               [{"role": "user", "content": "chào"}])
        async for _ in gen:
            pass

    asyncio.run(_chay())
    check("CANARY: lượt chat vào đúng nhánh Ollama", "stream" in _goi)
    check("CANARY: KHÔNG lặng lẽ rơi về Anthropic", "anthropic" not in _goi)
    check("key thật sự được mang theo", (_goi.get("stream") or {}).get("key") == "sk-cloud-test")
finally:
    engine.ollama_stream, engine.ollama_chat_with_mcp, engine.anthropic_stream = _goc


# ---- 5. Có tool MCP thì Ollama cũng là agent, không chỉ chat suông ----
_src = (ROOT / "server" / "main.py").read_text(encoding="utf-8")
check("ollama nằm trong danh sách provider được phát tool",
      '"gemini", "groq", "ollama")' in _src)
check("có nhánh gọi vòng tool cho ollama",
      "engine.ollama_chat_with_mcp(key, model, messages, reasoning, tools, route)" in _src)
check("CANARY: mã đã sạch hàm chọn địa chỉ",
      "_ollama_cfg" not in _src and "_ollama_host" not in _src)


# ---- 6. Lấy danh sách model: hai đường, vì tài liệu không nói rõ đường nào là chính ----
class _FakeResp:
    def __init__(self, ma, body):
        self.status_code, self._body = ma, body

    def raise_for_status(self):
        if self.status_code != 200:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._body


def _fake_httpx(ket_qua):
    """ket_qua: dict đuôi-URL -> (status, body). Ghi lại URL và header đã gọi."""
    duong, auth = [], []

    class _C:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url, headers=None, **k):
            duong.append(url)
            auth.append((headers or {}).get("Authorization", ""))
            for duoi, (ma, body) in ket_qua.items():
                if url.endswith(duoi):
                    return _FakeResp(ma, body)
            return _FakeResp(404, {})

    mod = types.ModuleType("httpx")
    mod.AsyncClient = _C
    return mod, duong, auth


def _lay_model(ket_qua, m=None):
    mod, duong, auth = _fake_httpx(ket_qua)
    sys.modules["httpx"] = mod
    try:
        ids = asyncio.run(main._fetch_provider_models(
            "ollama", m if m is not None else {"ollama_key": "sk-cloud"}))
    except Exception:  # noqa: BLE001 - cả hai đường hụt là ca hợp lệ, coi như không có model
        ids = None
    finally:
        sys.modules.pop("httpx", None)
    return ids, duong, auth


_ids, _duong, _auth = _lay_model({"/v1/models": (200, {"data": [
    {"id": "gpt-oss:120b-cloud"}, {"id": "qwen3-coder:480b-cloud"}]})})
check("lấy được model qua đường chuẩn OpenAI",
      _ids == ["gpt-oss:120b-cloud", "qwen3-coder:480b-cloud"])
check("hỏi đúng máy chủ Cloud", bool(_duong) and _duong[0].startswith(engine.OLLAMA_BASE))
check("CANARY: mang key theo khi hỏi model, không chỉ khi chat",
      bool(_auth) and all(a == "Bearer sk-cloud" for a in _auth))

# Đường chuẩn hụt thì phải hỏi tiếp đường gốc của Ollama; thiếu bước này là key đúng mà trang
# vẫn báo "chưa thấy model".
_ids, _duong, _auth = _lay_model({
    "/v1/models": (404, {}),
    "/api/tags": (200, {"models": [{"name": "gpt-oss:120b-cloud"}]}),
})
check("CANARY: hụt đường chuẩn thì hỏi tiếp đường gốc Ollama", _ids == ["gpt-oss:120b-cloud"])
check("thử đúng thứ tự: chuẩn trước, gốc sau",
      len(_duong) == 2 and _duong[0].endswith("/v1/models") and _duong[1].endswith("/api/tags"))
# Giữ tên kèm tag: "gpt-oss" và "gpt-oss:120b-cloud" là hai model khác nhau.
check("giữ nguyên tên kèm tag", _ids == ["gpt-oss:120b-cloud"])

# Chưa dán key thì đừng gọi mạng làm gì - vừa vô ích vừa bắt người dùng chờ.
_ids, _duong, _auth = _lay_model({}, m={})
check("CANARY: chưa có key thì không gọi mạng", _ids is None and not _duong)


# ---- 7. Giao diện: thẻ key thường, không còn ô địa chỉ ----
_console = (ROOT / "dashboard" / "console.js").read_text(encoding="utf-8")
check("CANARY: giao diện không còn nhánh theo địa chỉ", "needs_host" not in _console)
check("CANARY: không còn nút Kiểm tra địa chỉ", "data-ph=" not in _console)
# Thiếu dòng này thì thẻ Ollama hiện "Đổi key (•••)" với bốn ký tự cuối của... không gì cả.
check("bảng key của giao diện biết ollama", '"ollama": "ollama_key"' in _console)
check("ollama vẫn nằm trong danh sách provider có MCP", '"groq", "ollama"]' in _console)

print()
if _fails:
    print(f"THẤT BẠI {len(_fails)}: {_fails}")
    sys.exit(1)
print("OK - test_ollama: tất cả pass")
