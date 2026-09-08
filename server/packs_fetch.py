"""Tải gói từ mạng: chỉ HTTPS, chỉ zip, và không bao giờ trỏ được vào bên trong nhà.

Vì sao có một file riêng cho việc "tải một tệp"
-----------------------------------------------
Vì đây là chỗ SERVER TỰ ĐI GỌI một địa chỉ, và địa chỉ đó không phải do server nghĩ ra. Đó là
định nghĩa của SSRF. Javis chạy trên máy của người dùng hoặc trên VPS của họ, tức nó đang đứng
SẴN BÊN TRONG vành đai mạng: một request đi ra từ đây tới `127.0.0.1` hay `10.0.0.5` chạm được
những thứ mà người ngoài không chạm tới.

Rất cụ thể với Javis: `mcp_hub` đặt hub ở `http://127.0.0.1:7777/hub/mcp`, và hub cầm toàn bộ
khoá của người dùng. Trên máy ảo đám mây thì `169.254.169.254` trả về credential của chính máy
đó. Không rào thì "cài gói từ link" thành một cái loa đọc hộ.

Repo đã có một tiền lệ ở `ollama_local.chuan_hoa_endpoint`, nhưng nó chặn theo TÊN MÁY. Chưa
đủ cho đường này, vì tên máy công khai vẫn phân giải được về địa chỉ nội bộ, và một chuyển
hướng có thể đưa từ nơi lành sang nơi không lành. Nên ở đây kiểm theo ĐỊA CHỈ ĐÃ PHÂN GIẢI, và
kiểm lại sau MỖI chặng.

Giới hạn nói thật
-----------------
Vẫn còn một khe hẹp: giữa lúc kiểm địa chỉ và lúc thư viện HTTP tự phân giải lại để kết nối,
một DNS do kẻ tấn công điều khiển có thể đổi câu trả lời (DNS rebinding). Bịt kín khe đó phải
tự nối socket tới đúng IP đã kiểm rồi đặt SNI và Host bằng tay, tức viết lại tầng TLS. Không
làm ở đây, và ghi ra để không ai tưởng chỗ này kín hơn thực tế. Chốt thật cho gói có mã vẫn là
màn hình xác nhận cộng chữ ký nội dung, chứ không phải bộ tải này.
"""
from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

MAX_TAI = 25 * 1024 * 1024      # khớp trần của pack_install.MAX_ZIP
MAX_CHUYEN_HUONG = 3
TIMEOUT_KET_NOI = 10.0
TIMEOUT_TONG = 60.0


class LoiTai(ValueError):
    """Câu chữ đã sẵn sàng hiện thẳng lên giao diện, không cần dịch lại."""


def _dia_chi_cam(ip: str) -> bool:
    """Địa chỉ này có nằm trong nhà không.

    Gộp mọi dải KHÔNG phải Internet công cộng, chứ không liệt kê từng dải: liệt kê tay là kiểu
    danh sách luôn thiếu một mục. `is_global` của thư viện chuẩn đã biết loopback, riêng tư,
    link-local (gồm 169.254.169.254 của máy ảo đám mây), multicast và các dải để dành."""
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return True         # không phân giải ra IP hợp lệ thì coi như cấm
    if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped:
        addr = addr.ipv4_mapped     # ::ffff:127.0.0.1 phải bị bắt như 127.0.0.1
    return not addr.is_global


def kiem_dia_chi(url: str) -> str:
    """Kiểm một URL trước khi gọi. Trả về host đã phân giải được, hoặc ném LoiTai.

    Kiểm MỌI địa chỉ mà tên máy phân giải ra, không chỉ cái đầu tiên: một tên có thể trả về
    nhiều bản ghi, và chỉ cần một cái trỏ vào trong là đủ."""
    p = urlparse(str(url or "").strip())
    if p.scheme != "https":
        raise LoiTai("Chỉ tải được qua https://")
    if not p.hostname:
        raise LoiTai("Địa chỉ thiếu tên máy")
    if p.port not in (None, 443):
        # Cổng lạ gần như luôn là dịch vụ nội bộ. Chặn thẳng thay vì đoán.
        raise LoiTai("Chỉ tải được từ cổng 443")
    try:
        thong_tin = socket.getaddrinfo(p.hostname, 443, proto=socket.IPPROTO_TCP)
    except OSError as e:
        raise LoiTai(f"Không phân giải được tên máy: {p.hostname}") from e
    dia_chi = {x[4][0] for x in thong_tin}
    if not dia_chi:
        raise LoiTai(f"Không phân giải được tên máy: {p.hostname}")
    cam = sorted(a for a in dia_chi if _dia_chi_cam(a))
    if cam:
        raise LoiTai(f"Địa chỉ này trỏ vào mạng nội bộ ({cam[0]}), không tải được.")
    return p.hostname


async def tai(url: str, *, header: dict = None, tran: int = MAX_TAI) -> bytes:
    """Tải nội dung một URL. Đi từng chặng chuyển hướng một, kiểm lại địa chỉ ở mỗi chặng.

    KHÔNG dùng `follow_redirects` của thư viện: để nó tự đi là mất quyền kiểm tra giữa chừng,
    mà chuyển hướng chính là đường vòng kinh điển - một tên miền công cộng trả 302 sang
    `169.254.169.254` thì cái kiểm ở chặng đầu chẳng bảo vệ được gì.
    """
    import httpx

    hien = str(url or "").strip()
    hd = {"User-Agent": "Javis-OS pack fetcher", **header_xac_thuc(hien), **(header or {})}
    async with httpx.AsyncClient(follow_redirects=False,
                                 timeout=httpx.Timeout(TIMEOUT_TONG, connect=TIMEOUT_KET_NOI)) as cl:
        for _ in range(MAX_CHUYEN_HUONG + 1):
            kiem_dia_chi(hien)
            try:
                async with cl.stream("GET", hien, headers=hd) as r:
                    if r.status_code in (301, 302, 303, 307, 308):
                        ke = r.headers.get("location")
                        if not ke:
                            raise LoiTai("Máy chủ chuyển hướng nhưng không nói đi đâu")
                        truoc = httpx.URL(hien).host
                        hien = str(httpx.URL(hien).join(ke))
                        if httpx.URL(hien).host != truoc:
                            # Chuyển sang host KHÁC thì bỏ header xác thực. Gửi tiếp token của
                            # host cũ sang host mới là cách rò token kinh điển: chỉ cần một
                            # chuyển hướng do bên kia điều khiển là token đi theo.
                            hd = {k: v for k, v in hd.items()
                                  if k not in ("Authorization", "PRIVATE-TOKEN")}
                            hd.update(header_xac_thuc(hien))
                        continue
                    if r.status_code == 404:
                        raise LoiTai("Không tìm thấy tệp ở địa chỉ này (404)")
                    if r.status_code in (401, 403):
                        raise LoiTai("Không có quyền tải tệp này (%d)" % r.status_code)
                    if r.status_code >= 400:
                        raise LoiTai(f"Máy chủ trả lỗi {r.status_code}")
                    # Trần áp theo BYTE THẬT NHẬN ĐƯỢC, không tin Content-Length: header đó do
                    # bên kia khai, và khai một đằng gửi một nẻo là chuyện thường.
                    khoi, tong = [], 0
                    async for mieng in r.aiter_bytes(1 << 16):
                        tong += len(mieng)
                        if tong > tran:
                            raise LoiTai(f"Tệp quá lớn, trần {tran // 1024 // 1024}MB")
                        khoi.append(mieng)
                    return b"".join(khoi)
            except httpx.HTTPError as e:
                raise LoiTai(f"Không tải được: {type(e).__name__}") from e
    raise LoiTai("Chuyển hướng quá nhiều lần")


def token_cho(url: str) -> str:
    """Token đã lưu cho host của URL này, hoặc chuỗi rỗng.

    Lưu theo HOST chứ không theo từng URL: một token GitHub dùng được cho mọi repo mà nó có
    quyền, nên bắt người dùng dán lại cho từng gói là hành hạ vô ích.

    Token đi bằng HEADER, không bao giờ nhét vào URL. Nhét vào URL thì nó nằm trong argv của
    tiến trình con, trong log của proxy, và trong `Referer` khi có chuyển hướng - đó chính là
    lý do `git_brain._redact` phải tồn tại cho đường git."""
    try:
        import config as cfgmod
        from urllib.parse import urlparse
        host = (urlparse(str(url or "")).hostname or "").lower()
        if not host:
            return ""
        kho = (cfgmod.read_settings().get("packs") or {}).get("tokens") or {}
        return str(kho.get(host) or "")
    except Exception:
        return ""


def header_xac_thuc(url: str) -> dict:
    """Header xác thực cho host này. Rỗng nếu chưa lưu token nào.

    GitHub và GitLab nhận hai kiểu header khác nhau, nên nhận diện theo host. Host lạ thì dùng
    `Authorization: Bearer` vì đó là kiểu phổ biến nhất."""
    tk = token_cho(url)
    if not tk:
        return {}
    from urllib.parse import urlparse
    host = (urlparse(url).hostname or "").lower()
    if "gitlab" in host:
        return {"PRIVATE-TOKEN": tk}
    return {"Authorization": "Bearer " + tk}


def url_zip_github(raw: str) -> str:
    """Đổi vài cách viết quen thuộc thành URL tải thẳng. Không đoán bừa, chỉ nhận dạng rõ ràng.

    Nhận `owner/repo@ref` và link Release của GitHub, vì đó là hai cách người ta hay đưa link
    nhất. Mọi thứ khác giữ nguyên và để `kiem_dia_chi` phán."""
    s = str(raw or "").strip()
    if not s:
        raise LoiTai("Chưa nhập địa chỉ")
    if s.startswith("https://"):
        return s
    if "/" in s and "://" not in s and " " not in s:
        kho, _, ref = s.partition("@")
        if kho.count("/") == 1:
            return f"https://codeload.github.com/{kho}/zip/refs/heads/{ref or 'main'}"
    raise LoiTai("Địa chỉ phải là https://, hoặc dạng owner/repo@nhánh")
