"""Lớp gọi HTTP tới máy chủ Javis. Không biết gì về cách hiển thị."""
import json

import httpx


class LoiJavis(Exception):
    """Lỗi đã hiểu được, có câu chữ dành cho người đọc chứ không phải vết stack."""


class Client:
    def __init__(self, url: str, token: str = "", timeout: float = 900.0):
        if not url:
            raise LoiJavis(
                "Chưa biết Javis của bạn ở đâu.\n"
                "Chạy:  javis login <địa-chỉ>      ví dụ: javis login https://javis.example.com\n"
                "Hoặc đặt biến môi trường JAVIS_URL.")
        self.url = url.rstrip("/")
        self.token = token or ""
        # 900 giây, và đây là chủ ý: một lượt agentic có thể đọc file, gọi vài tool rồi mới
        # trả lời. Cắt ngang ở phút thứ nhất là vứt hết công đã bỏ ra, mà người dùng thì
        # không hiểu vì sao "Javis không trả lời".
        self.timeout = timeout

    def _headers(self) -> dict:
        h = {"User-Agent": "javis-cli"}
        if self.token:
            h["Authorization"] = "Bearer " + self.token
        return h

    def _kiem(self, r):
        if r.status_code == 401:
            raise LoiJavis(
                "Máy chủ từ chối: token thiếu hoặc đã bị thu hồi.\n"
                "Tạo token mới ở dashboard (Cài đặt > Token API) rồi chạy lại `javis login`.")
        if r.status_code == 403:
            raise LoiJavis("Máy chủ từ chối: token này không có quyền cho lệnh đó.")
        if r.status_code == 429:
            raise LoiJavis("Máy chủ tạm khoá vì có quá nhiều lần thử token sai từ máy này. "
                           "Chờ ít phút rồi thử lại.")
        if r.status_code >= 400:
            raise LoiJavis(f"Máy chủ trả lỗi {r.status_code}: {r.text[:300]}")
        return r

    def get(self, path: str, params: dict = None):
        try:
            with httpx.Client(timeout=30) as c:
                r = c.get(self.url + path, params=params or {}, headers=self._headers())
        except httpx.RequestError as e:
            raise LoiJavis(self._loi_mang(e))
        return self._kiem(r).json()

    def post(self, path: str, data: dict = None, timeout: float = None):
        try:
            with httpx.Client(timeout=timeout or self.timeout) as c:
                r = c.post(self.url + path, data=data or {}, headers=self._headers())
        except httpx.RequestError as e:
            raise LoiJavis(self._loi_mang(e))
        return self._kiem(r).json()

    def sse(self, path: str, data: dict = None):
        """Đọc luồng SSE, trả về từng gói đã giải mã.

        Gói hỏng thì BỎ QUA chứ không làm vỡ cả luồng: một dòng lỗi giữa chừng không đáng để
        mất câu trả lời đang tới.
        """
        try:
            with httpx.Client(timeout=self.timeout) as c:
                with c.stream("POST", self.url + path, data=data or {},
                              headers=self._headers()) as r:
                    if r.status_code >= 400:
                        r.read()
                        self._kiem(r)
                    for dong in r.iter_lines():
                        dong = (dong or "").strip()
                        if not dong.startswith("data:"):
                            continue
                        try:
                            yield json.loads(dong[5:].strip())
                        except json.JSONDecodeError:
                            continue
        except httpx.RequestError as e:
            raise LoiJavis(self._loi_mang(e))

    def _loi_mang(self, e) -> str:
        return (f"Không kết nối được tới {self.url}.\n"
                f"Chi tiết: {type(e).__name__}: {e}\n"
                "Kiểm tra: Javis có đang chạy không, địa chỉ có đúng không, "
                "và máy này có ra được tới đó không.")
