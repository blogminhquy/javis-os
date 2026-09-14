"""GET /tts với Edge phát STREAMING: byte đầu tới trình duyệt ngay khi Edge sinh ra.

    python tests/run.py tts_stream

Voice V1: trước đây `_tts_edge` gom cả câu thành một `bytes` rồi mới trả, câu dài 600 ký tự
mất 1-2 giây im lặng. Nay Edge trả `StreamingResponse`. Hai chỗ dễ vỡ:
  1. Edge lỗi NGAY (giọng không tồn tại, mất mạng) -> vẫn phải là 502 thật, không phải một
     stream 200 rỗng. Vì vậy khúc đầu được đợi TRƯỚC khi trả response.
  2. Header stream: Accept-Ranges none (trình duyệt đừng hỏi Range), Cache-Control no-cache.
Không chạm mạng: `edge_tts` bị thay bằng module giả trong sys.modules.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import os
import sys
import tempfile
import types

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-tts-"))

_fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)


class _FakeCommunicate:
    chunks = [b"ID3a", b"bbbb", b"cccc"]
    fail = False

    def __init__(self, text, voice, rate="+0%"):
        self.text, self.voice, self.rate = text, voice, rate

    async def stream(self):
        if _FakeCommunicate.fail:
            raise RuntimeError("Edge chết")
        for c in _FakeCommunicate.chunks:
            yield {"type": "audio", "data": c}
            yield {"type": "WordBoundary", "data": b""}


fake = types.ModuleType("edge_tts")
fake.Communicate = _FakeCommunicate
sys.modules["edge_tts"] = fake

import main  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

client = TestClient(main.app, base_url="http://127.0.0.1")   # host lạ bị web_security chặn 403

# Provider edge mặc định (settings test không có voice.tts_provider hoặc là edge).
_cfg_goc = main.cfgmod.read_settings
main.cfgmod.read_settings = lambda: {"voice": {"tts_provider": "edge"}, "model": {}}

r = client.get("/tts", params={"text": "xin chào", "voice": "vi-VN-HoaiMyNeural"})
check("edge stream: 200", r.status_code == 200)
check("edge stream: audio/mpeg", r.headers.get("content-type", "").startswith("audio/mpeg"))
check("edge stream: nối đủ mọi khúc audio theo thứ tự", r.content == b"ID3abbbbcccc")
check("edge stream: Accept-Ranges none", r.headers.get("accept-ranges") == "none")
check("edge stream: không Content-Length (chunked)", "content-length" not in {k.lower() for k in r.headers})

_FakeCommunicate.fail = True
r = client.get("/tts", params={"text": "xin chào"})
check("edge lỗi ngay: 502 thật chứ không phải stream rỗng", r.status_code == 502)
_FakeCommunicate.fail = False

# Provider trả phí lỗi -> rơi về Edge stream
main.cfgmod.read_settings = lambda: {"voice": {"tts_provider": "elevenlabs", "elevenlabs_key": ""}, "model": {}}
r = client.get("/tts", params={"text": "xin chào"})
check("elevenlabs thiếu key: rơi về Edge stream 200", r.status_code == 200 and r.content == b"ID3abbbbcccc")

# Khúc đầu rỗng -> Edge không trả audio -> 502
_FakeCommunicate.chunks = []
main.cfgmod.read_settings = lambda: {"voice": {"tts_provider": "edge"}, "model": {}}
r = client.get("/tts", params={"text": "xin chào"})
check("edge không có audio: 502", r.status_code == 502)
_FakeCommunicate.chunks = [b"ID3a", b"bbbb", b"cccc"]

main.cfgmod.read_settings = _cfg_goc

if _fails:
    print("\nFAIL:", len(_fails), _fails)
    raise SystemExit(1)
print("\nOK - tts stream")
