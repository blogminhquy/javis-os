"""Nhà cung cấp Ollama: model chạy ngay trên máy người dùng.

    python tests/run.py ollama

Ollama khác BẢY provider còn lại ở hai điểm, và cả hai đều ăn vào cách viết mã chứ không chỉ
là thêm một dòng cấu hình:

  1. KHÔNG có API key. Mọi chỗ đang hỏi "đã có key chưa" để biết provider đã kết nối hay chưa
     sẽ trả lời SAI cho nó - hoặc luôn "chưa" (không key), hoặc luôn "rồi" (không cần key).
     Cả hai đều vô dụng. Ở đây "đã kết nối" = đã LẤY ĐƯỢC danh sách model từ máy đó, tức là
     bằng chứng nó chạy thật.

  2. Địa chỉ KHÔNG cố định. Bốn provider kia gõ cứng URL được; Ollama thì người dùng có thể
     chạy trên máy khác trong mạng hoặc đổi cổng, nên URL phải dựng từ cấu hình.

File này canh đúng hai chỗ đó, cộng với việc lượt chat thật sự đi tới nhánh Ollama chứ không
lặng lẽ rơi về Anthropic - nhánh mặc định cuối hàm `_api_stream`, thứ sẽ nuốt mọi provider
quên đấu và không báo lỗi gì.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import os
import sys
import tempfile

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-ollama-")

import config as cfg  # noqa: E402
import engine  # noqa: E402
import main  # noqa: E402

_fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)


# ---- 1. Có mặt trong danh sách nhà cung cấp, và khai đúng kiểu ----
_p = main._provider_def("ollama")
check("có nhà cung cấp ollama", bool(_p))
check("thuộc nhóm API (đi qua hub, không chạy lệnh máy)", _p.get("kind") == "api")
check("có ô địa chỉ (thứ mọi provider khác không có)", _p.get("host_field") == "ollama_host")
check("và có ô key riêng cho Ollama Cloud", _p.get("key_field") == "ollama_key")
# Model là thứ người dùng tự tải về máy. Đoán hộ một danh sách là bày ra những cái họ không có.
check("không đoán hộ danh sách model", _p.get("default_models") == [])
check("có chỗ trong cấu hình mặc định",
      {"ollama_host", "ollama_key"} <= set(cfg._DEFAULT["model"] or {}))
# Địa chỉ máy KHÔNG phải secret - mã hoá nó là mã hoá một thứ vô hại rồi về sau tự hỏi vì sao
# nó hiện ra dạng "enc:..." trên giao diện. Key Cloud thì ngược lại, bắt buộc phải mã hoá.
check("địa chỉ không bị coi là secret", "model.ollama_host" not in cfg._SECRET_PATHS)
check("CANARY: key Cloud được mã hoá như mọi key khác", "model.ollama_key" in cfg._SECRET_PATHS)


# ---- 2. Dựng URL từ địa chỉ người dùng khai ----
check("để trống = máy này, cổng mặc định",
      engine.ollama_url("") == "http://localhost:11434/v1/chat/completions")
check("gõ thiếu http:// vẫn hiểu",
      engine.ollama_url("localhost:11434") == "http://localhost:11434/v1/chat/completions")
check("gõ thừa gạch chéo cuối vẫn đúng",
      engine.ollama_url("http://192.168.1.9:11434/") == "http://192.168.1.9:11434/v1/chat/completions")
check("máy khác trong mạng", engine.ollama_url("http://192.168.1.9:11434")
      == "http://192.168.1.9:11434/v1/chat/completions")
check("https thì giữ nguyên https",
      engine.ollama_url("https://ollama.nhà.vn") == "https://ollama.nhà.vn/v1/chat/completions")

# Một nhà, hai đường chạy. Luật chọn đường khi không khai địa chỉ là chỗ dễ sai nhất.
check("trống trơn = máy này", main._ollama_cfg({}) == (engine.OLLAMA_DEFAULT_HOST, ""))
check("CANARY: có key mà không khai địa chỉ = đi Ollama Cloud",
      main._ollama_cfg({"ollama_key": "k1"}) == (engine.OLLAMA_CLOUD_HOST, "k1"))
check("khai địa chỉ rõ thì luôn theo địa chỉ đó, kể cả có key",
      main._ollama_cfg({"ollama_key": "k1", "ollama_host": "http://10.0.0.5:11434"})
      == ("http://10.0.0.5:11434", "k1"))
check("đọc đúng host đã khai khi không có key",
      main._ollama_host({"ollama_host": "http://10.0.0.5:11434"}) == "http://10.0.0.5:11434")
# Máy nhà không xác thực gì, nhưng header vẫn phải hợp lệ để dùng chung đường OpenAI-compat.
check("máy nhà: header có Bearer giữ chỗ", engine.ollama_headers("")["Authorization"] == "Bearer ollama")
check("CANARY: Cloud: header mang đúng key", engine.ollama_headers("k1")["Authorization"] == "Bearer k1")


# ---- 3. Chọn làm model chính thì mọi đường đều trỏ về Ollama ----
_c = {"model": dict(cfg._DEFAULT["model"])}
main._set_main_model(_c, "ollama", "llama3.1:8b")
check("đặt được làm model chính", _c["model"]["main"] == {"provider": "ollama", "model": "llama3.1:8b"})
check("engine legacy khớp theo", _c["model"]["engine"] == "ollama")
_prov, _kind, _key, _model = main._chat_provider(_c["model"])
check("lượt chat định tuyến về ollama", _prov == "ollama" and _kind == "api")
check("không đòi key khi chat", _key == "")
check("giữ đúng model đã chọn", _model == "llama3.1:8b")


# ---- 4. Lượt chat THẬT SỰ đi vào nhánh Ollama ----
# Đây là bài quan trọng nhất. `_api_stream` kết thúc bằng `return engine.anthropic_stream(...)`
# - một nhánh mặc định nuốt mọi provider quên đấu, và nuốt trong im lặng: không lỗi, chỉ là
# câu hỏi bay sang Anthropic với key rỗng rồi báo lỗi xác thực khó hiểu.
_goi = {}
_goc_stream, _goc_mcp = engine.ollama_stream, engine.ollama_chat_with_mcp
_goc_anthropic = engine.anthropic_stream


async def _gia_stream(host, model, messages, reasoning="off", api_key=""):
    _goi["stream"] = {"host": host, "model": model, "key": api_key}
    yield {"type": "text", "content": "ok"}


async def _gia_anthropic(*a, **k):
    _goi["anthropic"] = True
    yield {"type": "text", "content": "sai nhánh"}


async def _gia_mcp(host, model, messages, reasoning, tools, route, api_key=""):
    _goi["mcp"] = {"host": host, "model": model, "tools": len(tools or []), "key": api_key}
    yield {"type": "text", "content": "ok"}


engine.ollama_stream, engine.ollama_chat_with_mcp = _gia_stream, _gia_mcp
engine.anthropic_stream = _gia_anthropic
try:
    _c["model"]["ollama_host"] = "http://10.0.0.5:11434"
    cfg.write_settings(_c)
    cfg._SETTINGS_CACHE["sig"] = None

    async def _chay():
        gen = main._api_stream("ollama", "", "llama3.1:8b", [{"role": "user", "content": "chào"}])
        async for _ in gen:
            pass

    asyncio.run(_chay())
    check("CANARY: lượt chat vào đúng nhánh Ollama", "stream" in _goi)
    check("CANARY: KHÔNG lặng lẽ rơi về Anthropic", "anthropic" not in _goi)
    check("gửi tới đúng máy người dùng khai",
          (_goi.get("stream") or {}).get("host") == "http://10.0.0.5:11434")

    # Đường Cloud: không khai địa chỉ, chỉ có key.
    _goi.clear()
    _c["model"]["ollama_host"] = ""
    _c["model"]["ollama_key"] = "sk-cloud-test"
    cfg.write_settings(_c)
    cfg._SETTINGS_CACHE["sig"] = None
    asyncio.run(_chay())
    check("CANARY: chỉ dán key thì đi thẳng Ollama Cloud",
          (_goi.get("stream") or {}).get("host") == engine.OLLAMA_CLOUD_HOST)
    check("CANARY: key Cloud thật sự được mang theo",
          (_goi.get("stream") or {}).get("key") == "sk-cloud-test")
finally:
    engine.ollama_stream, engine.ollama_chat_with_mcp = _goc_stream, _goc_mcp
    engine.anthropic_stream = _goc_anthropic


# ---- 5. Có tool MCP thì Ollama cũng là agent, không chỉ chat suông ----
_src = (ROOT / "server" / "main.py").read_text(encoding="utf-8")
check("ollama nằm trong danh sách provider được phát tool",
      '"gemini", "groq", "ollama")' in _src)
check("có nhánh gọi vòng tool cho ollama",
      "engine.ollama_chat_with_mcp(_h, model, messages, reasoning, tools, route, api_key=_k)" in _src)


# ---- 6. Lấy danh sách model = phép thử kết nối ----
# /api/tags trả về model ĐÃ TẢI VỀ máy đó. Gọi được nghĩa là Ollama đang chạy và địa chỉ đúng,
# nên nó vừa là danh sách vừa là đèn báo - trang Models không cần thêm nút "thử kết nối" riêng.
check("hỏi model qua /api/tags của chính máy đó", "/api/tags" in _src)


# Cloud không trả /api/tags giống máy nhà, nên phải có đường thứ hai. Đo bằng HÀNH VI chứ
# không bằng chuỗi: "/v1/models" còn xuất hiện ở nhánh OpenAI trong cùng file, nên soát chuỗi
# thì gỡ hẳn đường này đi test vẫn xanh (đã kiểm ngược, đúng là lọt).
class _FakeResp:
    def __init__(self, ma, body):
        self.status_code, self._body = ma, body

    def raise_for_status(self):
        if self.status_code != 200:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._body


class _FakeClient:
    """Giả lập đúng ca Cloud: /api/tags không có, /v1/models có."""

    def __init__(self, *a, **k):
        self.da_goi = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def get(self, url, headers=None, **k):
        _duong.append(url)
        _auth.append((headers or {}).get("Authorization", ""))
        if url.endswith("/api/tags"):
            return _FakeResp(404, {})
        return _FakeResp(200, {"data": [{"id": "gpt-oss:120b-cloud"}, {"id": "qwen3:480b-cloud"}]})


_duong, _auth = [], []
import types  # noqa: E402
_fake_httpx = types.ModuleType("httpx")
_fake_httpx.AsyncClient = _FakeClient
sys.modules["httpx"] = _fake_httpx
try:
    _ids = asyncio.run(main._fetch_provider_models(
        "ollama", {"ollama_key": "sk-cloud", "ollama_host": ""}))
finally:
    sys.modules.pop("httpx", None)

check("CANARY: /api/tags hụt thì hỏi tiếp /v1/models (đường của Cloud)",
      _ids == ["gpt-oss:120b-cloud", "qwen3:480b-cloud"])
check("thử đường gốc trước rồi mới sang đường chuẩn",
      len(_duong) == 2 and _duong[0].endswith("/api/tags") and _duong[1].endswith("/v1/models"))
check("hỏi đúng máy chủ Cloud", _duong[0].startswith(engine.OLLAMA_CLOUD_HOST))
check("CANARY: mang key theo khi hỏi model, không chỉ khi chat",
      all(a == "Bearer sk-cloud" for a in _auth))
# Giữ nguyên tên kèm tag: "llama3.1" và "llama3.1:8b" là hai model khác nhau với Ollama,
# cắt mất tag là gọi sang một model không tồn tại.
check("lấy tên đầy đủ kèm tag (llama3.1:8b), không cắt mất tag",
      'ids = sorted(x.get("name") for x in data if x.get("name"))' in _src)

_view = main._providers_view({"model": {"catalog": {"ollama": ["llama3.1:8b", "qwen2.5:7b"]}}})
_ol = next(x for x in _view if x["id"] == "ollama")
check("lấy được model thì coi như đang chạy", _ol["configured"] is True)
check("giao diện biết đây là provider theo địa chỉ", _ol["needs_host"] is True)
# Có key (cho Cloud) NHƯNG thẻ vẫn phải đi nhánh địa chỉ, vì "đã kết nối" của Ollama đo bằng
# model thấy được chứ không bằng việc ô key có chữ.
check("thẻ đi nhánh địa chỉ chứ không phải nhánh key thường", _ol["needs_host"] is True)
_view2 = main._providers_view({"model": {}})
_ol2 = next(x for x in _view2 if x["id"] == "ollama")
# Đây là chỗ dễ sai nhất: nhánh "không key thì coi như đã kết nối" (dành cho Claude Code) sẽ
# bật đèn xanh cho Ollama dù máy chưa cài gì, và người dùng chọn nó rồi ngồi đợi một câu trả
# lời không bao giờ tới.
check("CANARY: chưa thấy model nào thì KHÔNG báo đang chạy", _ol2["configured"] is False)


# ---- 7. Giao diện có ô địa chỉ và nút thử ----
_console = (ROOT / "dashboard" / "console.js").read_text(encoding="utf-8")
check("thẻ nhà cung cấp có nhánh theo địa chỉ", "p.needs_host" in _console)
check("có ô nhập địa chỉ", 'id="ph-${p.id}"' in _console)
check("bấm là lưu rồi hỏi thẳng máy đó",
      "ollama_host: val" in _console and "refresh=1" in _console)
check("có ô dán key cho Ollama Cloud", "ollama_key" in _console)
# Ô key là ô mật khẩu nên luôn hiện trống. Gửi chuỗi rỗng lên là mỗi lần bấm Kiểm tra lại
# xoá mất key đã lưu - người dùng đổi địa chỉ xong tự nhiên mất kết nối Cloud.
check("CANARY: để trống ô key thì KHÔNG xoá key đã lưu",
      "if (kval) patch.ollama_key = kval;" in _console)
check("gõ sai thì nói rõ, không im lặng", "Không thấy model nào ở" in _console)
check("và báo lỗi phân biệt được máy nhà với Cloud",
      "Ollama Cloud đã bật model nào chưa" in _console)

print()
if _fails:
    print(f"THẤT BẠI {len(_fails)}: {_fails}")
    sys.exit(1)
print("OK - test_ollama: tất cả pass")
