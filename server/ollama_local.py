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
    # Gõ thiếu CỔNG thì thêm cổng mặc định của Ollama, đừng để rơi về 80. Vụ thật 02/09: chủ
    # repo gõ mỗi IP máy chủ, Javis hiểu thành cổng 80, đi trúng web server của chính VPS đó và
    # nhận 301 - một mã lỗi không nói lên điều gì về Ollama cả. Cổng 80 gần như không bao giờ
    # là Ollama, còn 11434 thì luôn luôn, nên đoán ở đây là đoán đúng.
    #
    # CHỈ làm với http. Gõ `https://ollama.mien-cua-toi.com` không cổng là ý muốn đi qua một
    # reverse proxy ở 443 - nhét 11434 vào đó là bẻ gãy đúng cấu hình người ta cố tình dựng.
    if p.port is None and p.scheme == "http":
        return f"{p.scheme}://{p.hostname}:{CONG_MAC_DINH}"
    return f"{p.scheme}://{p.netloc}"


def la_ip_cong_khai(endpoint: str) -> bool:
    """Địa chỉ này có phải một IP CÔNG KHAI (Internet với tới được) không.

    Không phải để CHẶN - trỏ sang một máy khác qua Internet là chuyện hợp lệ. Nhưng Ollama
    KHÔNG có mật khẩu, nên mở nó ra một IP công khai là dựng một máy chủ model ai cũng gọi
    được. Người dùng phải được nói thẳng điều đó ngay lúc kết nối, chứ không phải đọc được
    trong một đoạn hướng dẫn ở trên rồi quên.
    """
    try:
        ip = ipaddress.ip_address(urlparse(chuan_hoa_endpoint(endpoint)).hostname or "")
    except (ValueError, LoiEndpoint):
        return False               # tên miền, hoặc địa chỉ hỏng - không kết luận
    return ip.is_global


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
        # 3xx = có thứ gì đó TRẢ LỜI, nhưng nó chuyển hướng - dấu hiệu kinh điển của việc trỏ
        # nhầm vào một web server (cổng 80/443 đá sang HTTPS). Nói bằng mã số trần thì người
        # dùng không có đường nào lần ra; nói đúng bệnh thì họ sửa được ngay.
        if 300 <= r.status_code < 400:
            return {"reachable": False, "models": [],
                    "error": (f"Địa chỉ này trả về chuyển hướng (mã {r.status_code}), tức là một "
                              "web server chứ không phải Ollama. Ollama nghe ở cổng 11434 - kiểm "
                              "tra lại xem đã ghi đúng cổng chưa.")}
        if r.status_code != 200:
            return {"reachable": False, "models": [],
                    "error": f"Máy chủ trả lỗi {r.status_code}"}
        try:
            data = r.json() or {}
        except ValueError:
            # Trả 200 nhưng không phải JSON = có máy chủ ở đó, chỉ là không phải Ollama.
            return {"reachable": False, "models": [],
                    "error": ("Địa chỉ này có máy chủ trả lời nhưng không phải Ollama. Kiểm tra "
                              "lại cổng (Ollama dùng 11434).")}
        if "models" not in data:
            return {"reachable": False, "models": [],
                    "error": ("Địa chỉ này trả lời nhưng không giống Ollama. Kiểm tra lại cổng "
                              "(Ollama dùng 11434).")}
        return {"reachable": True, "models": data.get("models") or [], "error": None}
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
    """Tổng RAM máy, tính GB. 0.0 = KHÔNG đọc được (người gọi phải hỏi người dùng).

    psutil KHÔNG phải dependency của Javis, nên đừng trông vào nó: cả ba đường dưới đây đều
    là thư viện chuẩn. Thiếu đường Windows là máy Windows luôn trả 0 - mà "máy cá nhân cài
    Javis" thì Windows là trường hợp thường gặp nhất.
    """
    try:
        import psutil
        return round(psutil.virtual_memory().total / (1024 ** 3), 1)
    except Exception:
        pass
    try:            # Linux
        with open("/proc/meminfo", encoding="utf-8") as f:
            for d in f:
                if d.startswith("MemTotal:"):
                    return round(int(d.split()[1]) / (1024 ** 2), 1)
    except OSError:
        pass
    if os.name == "nt":     # Windows - ctypes, không cần cài gì thêm
        try:
            import ctypes

            class _Mem(ctypes.Structure):
                _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                            ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                            ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                            ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                            ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]

            m = _Mem()
            m.dwLength = ctypes.sizeof(_Mem)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m)):
                return round(m.ullTotalPhys / (1024 ** 3), 1)
        except Exception:
            pass
    out = _chay(["sysctl", "-n", "hw.memsize"])        # macOS
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
    """Cấu hình máy ĐANG CHẠY JAVIS. Người gọi phải tự kiểm same_host() trước.

    ĐỌC HỤT RAM THÌ source = "unknown", KHÔNG phải "auto". Khác biệt này quyết định: "auto"
    nghĩa là con số đáng tin, nên phần gợi ý im lặng dùng nó. Máy 64GB mà đọc hụt thành 0 rồi
    vẫn khai "auto" thì người dùng bị mời toàn model dưới 8GB, và không có dấu hiệu nào cho
    thấy có gì sai - đúng kiểu hỏng lặng lẽ. Khai "unknown" thì giao diện hiện ô nhập tay và
    phần gợi ý nói thẳng là đang đoán ở mức an toàn.
    """
    ten, vram = _gpu()
    ram = _ram_gb()
    return {"source": "auto" if ram > 0 else "unknown", "ram_gb": ram,
            "has_gpu": bool(ten), "vram_gb": vram, "gpu_name": ten}
