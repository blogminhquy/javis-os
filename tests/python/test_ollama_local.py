"""Ollama chạy trên MÁY NHÀ: dò endpoint, đọc cấu hình máy, gợi ý, tải và gỡ model.

    python tests/run.py ollama_local

Test này dựng một Ollama GIẢ bằng http.server rồi cho Javis nói chuyện thật với nó. Không có
cách nào khác: máy chạy CI không có Ollama, mà đây lại là tính năng mà toàn bộ giá trị nằm ở
chỗ nói chuyện đúng giao thức với một tiến trình bên ngoài.

Thứ được canh kỹ nhất là GIẢ ĐỊNH NỀN mà bản thiết kế đầu tiên làm sai: nút "Cài Ollama" tự
chạy script và tự đọc RAM/GPU "máy này" chỉ đúng khi Javis và Ollama cùng một máy vật lý.
Phần đông người dùng chạy Javis trong Docker/VPS, nơi `localhost` là chính cái container.
Đó đúng là lý do provider ollama local bị chặn cố ý từ đầu (server/config.py), nên mọi thứ ở
đây phải chứng minh là nó không lặp lại giả định cũ.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import json
import os
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-ollama-"))

from fastapi.testclient import TestClient  # noqa: E402
import main  # noqa: E402
import ollama_local  # noqa: E402
import ollama_catalog  # noqa: E402

fails = []


def check(name, cond, them=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(them) + "]") if not cond and them else ""))
    if not cond:
        fails.append(name)


# ---- Ollama giả: đủ bốn endpoint Javis dùng ----------------------------------
DA_XOA = []


class OllamaGia(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _tra(self, code, obj):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/api/tags":
            return self._tra(200, {"models": [
                {"name": "qwen3:8b", "size": 5_200_000_000, "modified_at": "2026-08-28T10:00:00Z"},
                {"name": "gemma3:4b", "size": 3_300_000_000, "modified_at": "2026-08-20T10:00:00Z"},
            ]})
        if self.path == "/api/ps":
            return self._tra(200, {"models": [{"name": "qwen3:8b", "size_vram": 5_000_000_000}]})
        self._tra(404, {"error": "not found"})

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(n) or b"{}")
        if self.path == "/api/pull":
            self.send_response(200)
            self.send_header("Content-Type", "application/x-ndjson")
            self.end_headers()
            for mo in ({"status": "pulling manifest"},
                       {"status": "downloading", "completed": 500, "total": 1000},
                       {"status": "downloading", "completed": 1000, "total": 1000},
                       {"status": "success"}):
                self.wfile.write((json.dumps(mo) + "\n").encode("utf-8"))
                self.wfile.flush()
            return
        self._tra(404, {"error": "not found"})

    def do_DELETE(self):
        n = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(n) or b"{}")
        DA_XOA.append(body.get("model") or body.get("name"))
        self._tra(200, {})


srv = HTTPServer(("127.0.0.1", 0), OllamaGia)
threading.Thread(target=srv.serve_forever, daemon=True).start()
EP = f"http://127.0.0.1:{srv.server_address[1]}"

c = TestClient(main.app, base_url="http://127.0.0.1")

# ---- 1. Rào địa chỉ (đây là ô người dùng nhập mà SERVER tự đi gọi) -------------
for xau, vi_sao in [("file:///etc/passwd", "giao thức lạ"),
                    ("http://169.254.169.254", "dải metadata máy ảo đám mây"),
                    ("http://224.0.0.1", "địa chỉ multicast")]:
    try:
        ollama_local.chuan_hoa_endpoint(xau)
        check(f"chặn {vi_sao}", False, xau)
    except ollama_local.LoiEndpoint:
        check(f"chặn {vi_sao}", True)
# LoiEndpoint là con của ValueError. Gói phép thử "có phải IP không" chung một try với phát
# ném thì chính except ValueError nuốt mất phát ném đó, và địa chỉ metadata lọt lưới. Đã dính
# đúng vậy lúc viết, nên canh lại bằng một ca cụ thể.
check("CANARY: LoiEndpoint không bị chính except ValueError nuốt",
      issubclass(ollama_local.LoiEndpoint, ValueError))
check("gõ thiếu http:// vẫn hiểu được",
      ollama_local.chuan_hoa_endpoint("192.168.1.20:11434") == "http://192.168.1.20:11434")
check("cắt đường dẫn thừa", ollama_local.chuan_hoa_endpoint("http://a.vn:11434/") == "http://a.vn:11434")

# ---- 2. same_host: KHÔNG được suy ra từ mỗi chữ localhost ---------------------
check("địa chỉ LAN thì chắc chắn không cùng máy", not ollama_local.same_host("http://192.168.1.20:11434"))
_that = main.deploy_info.deploy_mode
try:
    main.deploy_info.deploy_mode = lambda: "docker"
    ollama_local.deploy_info.deploy_mode = lambda: "docker"
    # Đây là giả định đã làm hỏng bản thiết kế đầu: trong container, 127.0.0.1 là chính cái
    # container chứ không phải máy người dùng ngồi trước.
    check("CANARY: trong Docker thì localhost KHÔNG phải máy người dùng",
          not ollama_local.same_host("http://127.0.0.1:11434"))
finally:
    main.deploy_info.deploy_mode = _that
    ollama_local.deploy_info.deploy_mode = _that
check("chạy native + localhost thì mới là cùng máy", ollama_local.same_host("http://127.0.0.1:11434"))

# ---- 3. Vòng đời qua HTTP API ------------------------------------------------
r = c.get("/ollama-local/status").json()
check("chưa cấu hình thì không báo là nối được", r["reachable"] is False and r["endpoint"] == "")
check("có gợi ý sẵn địa chỉ mặc định", r["goi_y_endpoint"].endswith(":11434"))

r = c.post("/ollama-local/endpoint", data={"endpoint": EP}).json()
check("lưu địa chỉ xong dò được luôn", r.get("reachable") is True, r)
check("địa chỉ sai bị từ chối kèm lý do",
      c.post("/ollama-local/endpoint", data={"endpoint": "file:///x"}).status_code == 400)

r = c.get("/ollama-local/installed").json()
ten = [m["name"] for m in r["models"]]
check("liệt kê được model đã cài", ten == ["gemma3:4b", "qwen3:8b"], ten)
check("đổi byte sang GB cho người đọc",
      [m["size_gb"] for m in r["models"] if m["name"] == "qwen3:8b"] == [4.8])
# /api/ps là thứ DUY NHẤT cho biết model nào đang chiếm RAM/VRAM lúc này.
check("biết model nào đang nạp sẵn trong bộ nhớ",
      [m["loaded"] for m in r["models"] if m["name"] == "qwen3:8b"] == [True])

# ---- 4. Tải model: tiến độ phải chảy về qua SSE -------------------------------
with c.stream("POST", "/ollama-local/pull", data={"model": "qwen3:4b"}) as resp:
    moc = [json.loads(d[6:]) for d in resp.iter_lines() if d.startswith("data: ")]
check("có mốc tiến độ kèm số byte", any(m.get("total") for m in moc), moc[:3])
check("có mốc báo xong", any(m.get("status") == "success" for m in moc))
check("đóng luồng bằng một mốc riêng, client biết dừng đọc",
      moc and moc[-1].get("status") == "__done__")
# Ollama không có endpoint huỷ, và pull sau tự tiếp tục từ chỗ dở theo digest. Một endpoint
# /pull/cancel sẽ là API không làm gì cả - một lời hứa suông.
check("KHÔNG bịa ra endpoint huỷ tải",
      not any(getattr(r, "path", "") == "/ollama-local/pull/cancel" for r in main.app.routes))

r = c.post("/ollama-local/delete", data={"model": "gemma3:4b"}).json()
check("gỡ model gọi đúng sang Ollama", r.get("ok") is True and "gemma3:4b" in DA_XOA, DA_XOA)

# ---- 5. Gợi ý theo cấu hình máy ----------------------------------------------
c.post("/ollama-local/specs", data={"ram_gb": 32, "has_gpu": "1", "vram_gb": 8})
manh = c.get("/ollama-local/recommended").json()
c.post("/ollama-local/specs", data={"ram_gb": 8, "has_gpu": "0", "vram_gb": 0})
yeu = c.get("/ollama-local/recommended").json()
check("gợi ý tối đa 6 model", len(manh["models"]) <= 6 and len(yeu["models"]) <= 6)
check("máy yếu không bị mời model quá sức",
      all(m["size_gb"] <= 8 * 0.8 for m in yeu["models"]),
      [(m["name"], m["size_gb"]) for m in yeu["models"]])
# LỖI THẬT lúc dựng: xếp "lọt VRAM lên đầu" khiến máy 32GB nhận ĐÚNG cùng sáu model như máy
# 8GB, vì tám model dưới 8GB chiếm sạch chỗ. Người mua máy mạnh mở ra không thấy model lớn nào.
check("CANARY: máy mạnh phải thấy model lớn, không trùng khít máy yếu",
      {m["name"] for m in manh["models"]} != {m["name"] for m in yeu["models"]})
check("và thật sự có model lớn trong đó",
      max(m["size_gb"] for m in manh["models"]) > 9,
      [(m["name"], m["size_gb"]) for m in manh["models"]])
# Danh sách gợi ý không nói vì sao thì người dùng không có cơ sở nào để tin nó.
check("mỗi gợi ý kèm lý do vì sao nó ở đây", all(m.get("note") for m in manh["models"]))
check("model đã cài được đánh dấu, khỏi mời cài lại",
      any(m["name"] == "qwen3:8b" and m["installed"] for m in yeu["models"]))
# Một họ chiếm nhiều suất thì trông như nhiều lựa chọn mà thật ra chỉ có một.
_ho = [m["family"] for m in manh["models"]]
check("không để một họ model chiếm quá nửa danh sách",
      max(_ho.count(h) for h in set(_ho)) <= 3, _ho)

# ---- 5b. Đọc cấu hình máy: hụt thì phải NÓI là hụt ----------------------------
# psutil KHÔNG phải dependency của Javis. Bản đầu chỉ có đường Linux (/proc) và Mac (sysctl),
# nên máy Windows luôn trả 0 GB - mà "máy cá nhân cài Javis" thì Windows là ca thường gặp
# nhất. Tệ hơn: nó vẫn khai source="auto", tức máy 64GB bị mời toàn model dưới 8GB mà không
# có dấu hiệu nào cho thấy sai. Đó là hỏng lặng lẽ, loại khó phát hiện nhất.
import unittest.mock as _mock  # noqa: E402
with _mock.patch.object(ollama_local, "_ram_gb", lambda: 0.0):
    _hut = ollama_local.detect_specs()
check("CANARY: đọc hụt RAM thì KHÔNG được khai là 'auto'", _hut["source"] == "unknown", _hut)
check("đọc được RAM thì mới khai auto", ollama_local.detect_specs()["source"] == "auto")
check("có đường đọc RAM cho Windows, không trông vào psutil",
      "GlobalMemoryStatusEx" in (ROOT / "server" / "ollama_local.py").read_text(encoding="utf-8"))
# source='unknown' phải kéo theo gợi ý nói thẳng là đang đoán, chứ không im lặng.
_goi_y_khi_hut = ollama_catalog.goi_y({"source": "unknown", "ram_gb": 0})
check("và gợi ý lúc đó nói rõ là đang đoán ở mức an toàn",
      all("chưa đọc được" in (m.get("note") or "").lower() for m in _goi_y_khi_hut),
      [m.get("note") for m in _goi_y_khi_hut[:2]])

# ---- 6. Tìm kiếm + danh mục nền ----------------------------------------------
r = c.get("/ollama-local/search", params={"q": "coder"}).json()
check("tìm theo tên chạy", any("coder" in m["name"] for m in r["models"]))
check("lọc theo năng lực chạy",
      all("vision" in m["tags"] for m in c.get("/ollama-local/search",
                                               params={"capability": "vision"}).json()["models"]))
# Đây là điểm khác spec: chưa cào được ollama.com nên có danh mục nền đi kèm app. Nhờ vậy
# lần chạy ĐẦU TIÊN, khi chưa có cache nào, tab vẫn có dữ liệu - lỗ mà "giữ cache cũ" không bịt.
check("lần đầu chạy, chưa cache gì, danh mục vẫn không rỗng",
      len(ollama_catalog.thu_vien()["items"]) > 10)
check("và nói rõ dữ liệu đang lấy từ đâu", r.get("catalog_source") in ("builtin", "live"))
check("có sẵn chỗ cắm nguồn danh mục sống", callable(ollama_catalog.dat_nguon_song))

# ---- 7. Đấu vào lớp provider chung --------------------------------------------
check("ollama-local là một provider như mọi provider khác",
      any(p["id"] == "ollama-local" for p in main.PROVIDER_DEFS))
check("nó KHÔNG dùng ô API key (thứ xác thực nó là địa chỉ)",
      [p for p in main.PROVIDER_DEFS if p["id"] == "ollama-local"][0]["key_field"] is None)
import config as cfgmod  # noqa: E402
check("khoá của nó vẫn được mã hoá at rest như mọi khoá khác",
      "model.ollama_local_key" in cfgmod._SECRET_PATHS)
import engine  # noqa: E402
check("chat dùng lại nguyên đường OpenAI-compat, chỉ đổi URL",
      callable(engine.ollama_local_stream) and callable(engine.ollama_local_chat_with_mcp))
check("URL chat dựng từ cấu hình, không hằng số hoá",
      engine.ollama_local_url().startswith(EP.rsplit(":", 1)[0]) or engine.ollama_local_url() != "")

srv.shutdown()
print("")
if fails:
    print(f"ĐỎ {len(fails)} mục")
    sys.exit(1)
print("Tất cả xanh.")
