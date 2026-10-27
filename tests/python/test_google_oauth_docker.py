"""Đăng nhập Google Workspace khi Javis chạy Docker trên máy tính (issue #855).

    python tests/run.py google_oauth_docker

workspace-mcp hứng kết quả đăng nhập Google ở http://localhost:8000/oauth2callback. Javis trong
container: chỗ hứng đó nghe trên loopback của CONTAINER, còn trình duyệt ở máy người dùng, nên bấm
đồng ý xong là ERR_CONNECTION_REFUSED. Bản sửa có ba phần, test giữ cả ba:
  1. Trong Docker, kết nối workspace-mcp chạy với chỗ hứng nghe mọi địa chỉ của container nhưng vẫn
     trả về localhost:8000 (client OAuth loại "ứng dụng máy tính" nhận cổng loopback bất kỳ).
  2. docker-compose.google.yml mở cổng 8000 CHỈ cho chính máy đó; update.sh giữ file này khi cổng đang mở.
  3. Bấm Kết nối lần đầu trong Docker thì Javis nói rõ phải làm gì thay vì để đâm vào ngõ cụt.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import json
import os
import sys
import tempfile

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-gdocker-"))

import deploy_info  # noqa: E402
import main  # noqa: E402
import mcp_store  # noqa: E402

_fails = []


def check(name, cond, them=""):
    print(("ok   " if cond else "FAIL ") + name + (f"  [{them}]" if not cond and them else ""))
    if not cond:
        _fails.append(name)


# ---- 1. env của kết nối workspace-mcp ----
cid, err = mcp_store.add_connection("google-workspace", {"label": "test", "fields": {
    "client_id": "x.apps.googleusercontent.com", "client_secret": "GOCSPX-test"}})
check("thêm được kết nối Google Workspace để thử", bool(cid), str(err))


def _env():
    r = [x for x in mcp_store.resolved(enabled_only=False) if x["id"] == cid]
    return (r[0].get("env") or {}) if r else {}


_old = deploy_info.deploy_mode
try:
    deploy_info.deploy_mode = lambda: "native"
    env = _env()
    check("cài thường: không đổi gì (chỗ hứng vẫn là loopback mặc định)",
          "WORKSPACE_MCP_BASE_URI" not in env and "GOOGLE_OAUTH_REDIRECT_URI" not in env)
    deploy_info.deploy_mode = lambda: "docker"
    env = _env()
    check("Docker: chỗ hứng nghe mọi địa chỉ của container", env.get("WORKSPACE_MCP_BASE_URI") == "http://0.0.0.0")
    check("Docker: Google vẫn trả về localhost:8000 trên máy người dùng",
          env.get("GOOGLE_OAUTH_REDIRECT_URI") == "http://localhost:8000/oauth2callback")
    check("Docker: link workspace-mcp đưa ra trỏ về địa chỉ trình duyệt mở được",
          env.get("WORKSPACE_EXTERNAL_URL") == "http://localhost:8000")
    check("Docker: không mất biến bắt buộc của gói (callback http)", env.get("OAUTHLIB_INSECURE_TRANSPORT") == "1")
finally:
    deploy_info.deploy_mode = _old
    mcp_store.delete_connection(cid)

# ---- 2. compose ----
g = (ROOT / "docker-compose.google.yml").read_text(encoding="utf-8")
check("docker-compose.google.yml mở cổng 8000 chỉ cho chính máy đó", '"127.0.0.1:8000:8000"' in g)
check("file nhắc không dùng trên VPS", "VPS" in g)
u = (ROOT / "update.sh").read_text(encoding="utf-8")
check("update.sh giữ cổng 8000 khi container đang mở nó",
      'docker port "$NAME" 8000' in u and "-f docker-compose.google.yml" in u)
check("docker-compose.yml chính không tự mở cổng 8000 (máy đang dùng cổng đó vẫn chạy được Javis)",
      ":8000" not in (ROOT / "docker-compose.yml").read_text(encoding="utf-8"))


# ---- 3. lời nhắc khi bấm Kết nối ----
class _Req:
    def __init__(self, body, host="localhost:7777"):
        self._b = body
        self.url = type("U", (), {"scheme": "http", "netloc": host})()
        self.headers = {}

    async def json(self):
        return self._b


_old_mode = main._deploy_mode
try:
    main._deploy_mode = lambda: "docker"
    r = asyncio.run(main.connect_add(_Req({"connector_id": "google-workspace", "fields": {}})))
    check("Docker, mở Javis trên chính máy đó: nói rõ phải mở cổng 8000 và cho bấm lại",
          r.get("ok") is False and r.get("can_force") is True and "docker-compose.google.yml" in (r.get("error") or ""))
    r = asyncio.run(main.connect_add(_Req({"connector_id": "google-workspace", "fields": {}}, host="javis.example.com")))
    check("Docker qua tên miền công khai: vẫn là lời nhắc dùng thẻ Lịch/Gmail (issue #112)",
          "VPS" in (r.get("error") or "") and "docker-compose.google.yml" not in (r.get("error") or ""))
finally:
    main._deploy_mode = _old_mode

print()
if _fails:
    print("FAILED: " + ", ".join(_fails))
    sys.exit(1)
print("All passed")
