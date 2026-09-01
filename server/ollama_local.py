"""Ollama chạy trên MÁY NHÀ - dò, đọc cấu hình máy, tải và gỡ model.

VÌ SAO MODULE NÀY KHÔNG GIỐNG grok_cli/antigravity_cli
--------------------------------------------------------
Với Grok Build hay Antigravity, Javis biết "đã cài chưa" bằng `shutil.which(<binary>)`, và
điều đó ĐÚNG vì chính tiến trình Javis là thứ sẽ gọi cái binary đó để chat - hai bên chắc
chắn cùng một máy.

Ollama thì không. Nó nói chuyện qua HTTP, nên máy chạy Ollama có thể là:
  - chính máy chạy Javis (bản native trên máy để bàn),
  - hoặc một máy KHÁC hẳn (Javis trong Docker/VPS, Ollama ở máy nhà, nối qua LAN/Tailscale).

Cả module này xoay quanh việc KHÔNG giả định trường hợp thứ nhất:
  - "đã sẵn sàng" = gọi được `GET /api/tags`, KHÔNG phải "có binary ollama trên máy Javis";
  - quản lý model qua HTTP API, KHÔNG shell ra `ollama pull` (lệnh đó chỉ chạy trên máy Javis,
    tức sai máy trong phần lớn trường hợp);
  - đọc RAM/GPU chỉ khi CHẮC CHẮN cùng máy (xem `same_host`), còn lại hỏi người dùng.

Đây cũng là lý do bản demo đầu tiên phải bỏ nút "Cài Ollama tự động": Javis trong container
không có quyền, và cũng không có đường, chạy một lệnh cài trên máy vật lý của người dùng.
"""
from __future__ import annotations

import ipaddress
import json
import os
import shutil
import subprocess
from urllib.parse import urlparse

import httpx

import deploy_info
import winproc               # lệnh con chạy câm trên Windows, không nháy console đen

# Cổng mặc định của Ollama (docs.ollama.com). Chỉ dùng để GỢI Ý sẵn trong ô nhập.
CONG_MAC_DINH = 11434
GOI_Y_ENDPOINT = f"http://127.0.0.1:{CONG_MAC_DINH}"

# Dò endpoint phải NHANH: người dùng đang đứng nhìn màn hình chờ. Máy tắt thì TCP báo ngay,
# còn IP không tồn tại trong LAN thì treo tới hết timeout - nên để ngắn.
TIMEOUT_DO = 5.0
# Tải model là việc hàng GB, không đặt trần tổng; chỉ chặn lúc KẾT NỐI để khỏi treo vô hạn
# khi endpoint chết giữa chừng.
TIMEOUT_TAI = httpx.Timeout(None, connect=10.0)


class LoiEndpoint(ValueError):
    """Endpoint người dùng nhập không dùng được. Câu chữ đã sẵn sàng để hiện thẳng lên UI."""


def chuan_hoa_endpoint(raw: str) -> str:
    """Kiểm và chuẩn hoá địa chỉ người dùng nhập. Ném LoiEndpoint kèm câu giải thích.

    Đây là ô NGƯỜI DÙNG NHẬP mà SERVER sẽ tự đi gọi, nên nó là một bề mặt SSRF: không rào thì
    một địa chỉ như `file://` hay `http://169.254.169.254` (metadata của máy ảo đám mây) biến
    Javis thành cái loa đọc hộ. Rào ở đây, một chỗ, thay vì tin vào từng chỗ gọi.
    """
    u = (raw or "").strip().rstrip("/")
    if not u:
        raise LoiEndpoint("Chưa nhập địa chỉ Ollama")
    if "://" not in u:
        u = "http://" + u          # gõ "192.168.1.20:11434" là ý người dùng, đừng bắt gõ đủ
    p = urlparse(u)
    if p.scheme not in ("http", "https"):
        raise LoiEndpoint("Địa chỉ phải bắt đầu bằng http:// hoặc https://")
    if not p.hostname:
        raise LoiEndpoint("Địa chỉ thiếu tên máy hoặc IP")
    # Link-local (169.254.x.x) là dải metadata của AWS/GCP/Azure - hỏi vào đó là moi thông tin
    # máy chủ, không bao giờ là một Ollama thật.
    #
    # Phép thử "có phải IP không" phải đứng RIÊNG khỏi phép ném lỗi: LoiEndpoint là con của
    # ValueError, nên gói cả hai trong một try thì chính cái `except ValueError` dưới đây nuốt
    # mất phát ném, và địa chỉ metadata lọt lưới. Đã dính đúng vậy lúc viết.
    try:
        ip = ipaddress.ip_address(p.hostname)
    except ValueError:
        ip = None                   # tên miền, không phải IP - bình thường
    if ip is not None and (ip.is_link_local or ip.is_multicast or ip.is_reserved):
        raise LoiEndpoint("Địa chỉ này không phải một máy chạy Ollama")
    if p.path not in ("", "/"):
        raise LoiEndpoint("Chỉ nhập địa chỉ máy chủ, không kèm đường dẫn (vd http://127.0.0.1:11434)")
    return f"{p.scheme}://{p.netloc}"


def same_host(endpoint: str) -> bool:
    """Máy chạy Ollama có CHẮC CHẮN là máy chạy Javis không?

    Phải đúng CẢ HAI: địa chỉ trỏ về chính mình, VÀ Javis không nằm trong container. Thiếu vế
    sau thì `127.0.0.1` bên trong Docker lại bị hiểu là máy người dùng - đúng cái nhầm khiến
    tính năng này bị hoãn ngay từ đầu.
    """
    try:
        host = (urlparse(endpoint or "").hostname or "").lower()
    except ValueError:
        return False
    if host not in ("127.0.0.1", "localhost", "::1", "0.0.0.0"):
        return False
    return deploy_info.deploy_mode() in ("native", "windows")


def _headers(key: str | None) -> dict:
    # Ollama trên máy nhà không có xác thực, nhưng có người đặt nó sau reverse proxy. Gửi
    # Bearer khi có key, còn không thì thôi - Ollama trần bỏ qua header lạ nhưng một proxy
    # khó tính có thể không.
    h = {"Content-Type": "application/json"}
    if key:
        h["Authorization"] = f"Bearer {key}"
    return h


async def probe(endpoint: str, key: str | None = None) -> dict:
    """Ollama ở địa chỉ này còn sống không, và đang có model gì.

    Dùng `GET /api/tags` làm luôn phép thử: nó vừa là tín hiệu sống vừa là dữ liệu cần lấy,
    nên không tốn thêm một vòng gọi chỉ để ping.
    """
    try:
        ep = chuan_hoa_endpoint(endpoint)
    except LoiEndpoint as e:
        return {"reachable": False, "models": [], "error": str(e)}
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_DO) as cli:
            r = await cli.get(ep + "/api/tags", headers=_headers(key))
        if r.status_code != 200:
            return {"reachable": False, "models": [],
                    "error": f"Máy chủ trả lỗi {r.status_code}"}
        return {"reachable": True, "models": (r.json() or {}).get("models") or [], "error": None}
    except httpx.ConnectError:
        return {"reachable": False, "models": [],
                "error": "Không nối được. Ollama đã chạy chưa, và địa chỉ có đúng không?"}
    except httpx.TimeoutException:
        return {"reachable": False, "models": [], "error": "Hết giờ chờ - máy không trả lời"}
    except Exception as e:
        return {"reachable": False, "models": [], "error": str(e)[:200]}


async def running_models(endpoint: str, key: str | None = None) -> list:
    """Model đang NẠP trong RAM/VRAM (`GET /api/ps`). Rỗng khi hỏng - đây là thông tin phụ,
    không đáng làm hỏng cả màn hình."""
    try:
        ep = chuan_hoa_endpoint(endpoint)
        async with httpx.AsyncClient(timeout=TIMEOUT_DO) as cli:
            r = await cli.get(ep + "/api/ps", headers=_headers(key))
        return (r.json() or {}).get("models") or [] if r.status_code == 200 else []
    except Exception:
        return []


async def delete_model(endpoint: str, model: str, key: str | None = None) -> dict:
    ep = chuan_hoa_endpoint(endpoint)
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_DO * 4) as cli:
            r = await cli.request("DELETE", ep + "/api/delete", headers=_headers(key),
                                  json={"model": model, "name": model})
        if r.status_code in (200, 204):
            return {"ok": True}
        return {"ok": False, "error": f"Ollama trả lỗi {r.status_code}: {r.text[:200]}"}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}


async def pull_stream(endpoint: str, model: str, key: str | None = None):
    """Tải model, yield từng mốc tiến độ Ollama đẩy về.

    HUỶ TẢI = NGƯỜI GỌI NGỪNG LẶP. Ollama không có endpoint huỷ, và tài liệu ghi rõ lần pull
    sau sẽ tiếp tục từ chỗ dở theo digest. Nên chỉ cần đóng kết nối là xong, không có gì phải
    dọn và cũng không mất phần đã tải.
    """
    ep = chuan_hoa_endpoint(endpoint)
    async with httpx.AsyncClient(timeout=TIMEOUT_TAI) as cli:
        async with cli.stream("POST", ep + "/api/pull", headers=_headers(key),
                              json={"model": model, "name": model, "stream": True}) as r:
            if r.status_code != 200:
                await r.aread()
                yield {"status": "error", "error": f"Ollama trả lỗi {r.status_code}"}
                return
            async for dong in r.aiter_lines():
                dong = (dong or "").strip()
                if not dong:
                    continue
                try:
                    yield json.loads(dong)
                except json.JSONDecodeError:
                    continue        # Ollama chỉ đẩy JSON theo dòng; dòng lạ thì bỏ, không nổ


# ── Đọc cấu hình máy ────────────────────────────────────────────────────────────
# Chỉ có nghĩa khi same_host() True. Ollama KHÔNG có endpoint nào trả về RAM/GPU của máy nó
# đang chạy, nên với một địa chỉ ở xa thì Javis không có đường nào biết - phải hỏi người dùng.

def _chay(cmd: list) -> str:
    """Chạy một lệnh đọc thông tin, trả stdout hoặc "" nếu máy không có lệnh đó."""
    if not shutil.which(cmd[0]):
        return ""
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=6,
                           creationflags=winproc.no_window())
        return r.stdout if r.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def _ram_gb() -> float:
    try:
        import psutil
        return round(psutil.virtual_memory().total / (1024 ** 3), 1)
    except Exception:
        pass
    # Không có psutil: Linux đọc thẳng /proc, Mac hỏi sysctl. Thà lấy được con số thô còn hơn
    # bỏ trống rồi bắt người dùng tự khai trên chính máy Javis đang đứng.
    try:
        with open("/proc/meminfo", encoding="utf-8") as f:
            for d in f:
                if d.startswith("MemTotal:"):
                    return round(int(d.split()[1]) / (1024 ** 2), 1)
    except OSError:
        pass
    out = _chay(["sysctl", "-n", "hw.memsize"])
    try:
        return round(int(out.strip()) / (1024 ** 3), 1)
    except (TypeError, ValueError):
        return 0.0


def _gpu() -> tuple:
    """(tên GPU, VRAM GB). Thử NVIDIA rồi AMD; Apple Silicon dùng chung RAM nên xử riêng."""
    out = _chay(["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"])
    if out.strip():
        dong = out.strip().splitlines()[0]
        phan = [x.strip() for x in dong.split(",")]
        if len(phan) >= 2:
            try:
                return phan[0], round(float(phan[1]) / 1024, 1)
            except ValueError:
                return phan[0], 0.0
    out = _chay(["rocm-smi", "--showmeminfo", "vram", "--csv"])
    if out.strip():
        for d in out.splitlines():
            for o in d.split(","):
                try:
                    b = int(o.strip())
                except ValueError:
                    continue
                if b > 1024 ** 3:               # ô nào ra byte thì đó là dung lượng VRAM
                    return "GPU AMD", round(b / (1024 ** 3), 1)
        return "GPU AMD", 0.0
    # Apple Silicon: GPU dùng CHUNG bộ nhớ với CPU, nên không có "VRAM" tách riêng. Báo đúng
    # như vậy thay vì bịa một con số - phần gợi ý model đọc has_gpu để biết còn vram_gb=0
    # nghĩa là "cứ tính theo RAM".
    if deploy_info.host_platform() == "mac" and "arm" in (_chay(["uname", "-m"]) or "").lower():
        return "Apple Silicon (bộ nhớ dùng chung)", 0.0
    return "", 0.0


def detect_specs() -> dict:
    """Cấu hình máy ĐANG CHẠY JAVIS. Người gọi phải tự kiểm same_host() trước."""
    ten, vram = _gpu()
    return {"source": "auto", "ram_gb": _ram_gb(), "has_gpu": bool(ten),
            "vram_gb": vram, "gpu_name": ten}
