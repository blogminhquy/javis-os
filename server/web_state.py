"""Sổ trạng thái engine Web: máy trạng thái, phân loại lỗi, cooldown.

Vì sao có file này
------------------
Bản rà soát kiến trúc 2026-09-22 chỉ ra một lỗ của Javis: `aux_engine._FallbackChain` thử
từng engine một cách MÙ, không nhớ mắt nào vừa chết, nên mỗi việc nền mới lại thử lại đúng
nhà cung cấp vừa hỏng. `limit_learner` có dữ liệu hạn mức nhưng không có trạng thái dùng chung.

Engine Web là nhà đầu tiên bắt buộc phải có sổ này, vì nó hỏng theo nhiều kiểu hơn API: hết
phiên đăng nhập, Cloudflare chặn, trang đổi giao diện, người dùng đóng trình duyệt. Nên viết
ở dạng TỔNG QUÁT ĐƯỢC ngay từ đầu, để sau bê nguyên sang các nhà khác thay vì viết bản thứ hai.

Ba ranh giới có chủ ý
---------------------
1. **THUẦN, không đụng trình duyệt.** Chỉ stdlib cộng `config.STATE_DIR`. Test được trong một
   giây, không cần Playwright, không cần mạng.
2. **KHÔNG BỊA MỐC RESET.** Nhà cung cấp không nói thì `cooldown_until` lấy theo trần mặc
   định của Javis và đánh dấu là ƯỚC. Bịa một con giờ rồi gọi lại đúng lúc đó là đốt thêm một
   lượt của lần sau (bài học của `limit_resume`).
3. **TRONG COOLDOWN THÌ TỪ CHỐI TRƯỚC KHI MỞ TRÌNH DUYỆT.** Mở Chromium mất vài giây và để
   lại tiến trình; mở ra chỉ để nhận lại đúng câu "hết lượt" là phí hai lần.
"""
from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Optional

from config import STATE_DIR

STORE_PATH = Path(STATE_DIR) / "web_chat.json"
_lock = threading.RLock()

# ---- Trạng thái. Tên giữ nguyên chữ hoa để đọc trong nhật ký là thấy ngay. ----
READY = "READY"
AUTH_REQUIRED = "AUTH_REQUIRED"          # chưa đăng nhập, hoặc phiên hết hạn
BUSY = "BUSY"                            # đang có một lượt chạy trên cùng profile
USAGE_LIMITED = "USAGE_LIMITED"          # nhà cung cấp báo chạm trần lượt
CHALLENGE_REQUIRED = "CHALLENGE_REQUIRED"  # Cloudflare / captcha, cần tay người
TEMPORARY_ERROR = "TEMPORARY_ERROR"      # hỏng tạm, thử lại được
TRANSPORT_BROKEN = "TRANSPORT_BROKEN"    # trang đổi khuôn, tee không bắt được luồng
NO_BROWSER = "NO_BROWSER"                # máy chưa có Chromium/Chrome
DISABLED = "DISABLED"                    # cổng môi trường chưa bật
UNKNOWN = "UNKNOWN"

# Trạng thái nào thì KHÔNG nên mở trình duyệt nữa cho tới khi hết cooldown.
_TRANG_THAI_NGHI = frozenset({USAGE_LIMITED, CHALLENGE_REQUIRED, TRANSPORT_BROKEN})

# Cooldown mặc định theo loại lỗi, giây. Chỉ dùng khi nhà cung cấp KHÔNG nói mốc reset.
COOLDOWN_MAC_DINH = {
    USAGE_LIMITED: 30 * 60,
    CHALLENGE_REQUIRED: 10 * 60,
    TRANSPORT_BROKEN: 15 * 60,
    TEMPORARY_ERROR: 60,
}

# Hỏng liên tiếp bao nhiêu lần thì vào cooldown dài, kể cả lỗi vốn nhẹ. Đây là cái phanh
# chống vòng lặp thử lại mà `_FallbackChain` đang thiếu.
NGUONG_NGAT = 3
COOLDOWN_NGAT = 15 * 60

# Trần cooldown. Nhà cung cấp nói "mở lại sau 4 ngày" thì vẫn chỉ nghỉ tới đây rồi thử lại:
# tiến trình gần như chắc chắn khởi động lại trong khoảng đó, và hứa chờ 4 ngày là hứa suông.
COOLDOWN_TOI_DA = 24 * 3600


@dataclass
class TrangThai:
    """Ảnh chụp sổ. Mọi trường đều tuỳ chọn để file cũ đọc lên không vỡ."""
    state: str = UNKNOWN
    last_success: float = 0.0
    last_error: str = ""
    last_error_kind: str = ""
    failure_count: int = 0
    cooldown_until: float = 0.0
    # Mốc nghỉ là do nhà cung cấp NÓI RA, hay Javis tự ước? Hiện lên giao diện khác nhau.
    cooldown_uoc: bool = True
    auth_state: str = ""
    active_thread_id: str = ""
    # Web không trả số token, nên đây là thứ duy nhất đo được mức tiêu thụ (spec mục 22).
    so_luot_trong_ngay: int = 0
    ngay: str = ""

    def dang_nghi(self, now: Optional[float] = None) -> bool:
        return self.cooldown_until > (now if now is not None else time.time())

    def con_nghi(self, now: Optional[float] = None) -> float:
        con = self.cooldown_until - (now if now is not None else time.time())
        return con if con > 0 else 0.0


def _now() -> float:
    return time.time()


def _hom_nay(now: float) -> str:
    return time.strftime("%Y-%m-%d", time.localtime(now))


def _doc() -> dict:
    try:
        return json.loads(STORE_PATH.read_text(encoding="utf-8")) or {}
    except (OSError, ValueError):
        return {}


def _ghi(d: dict) -> None:
    try:
        STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = STORE_PATH.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(STORE_PATH)
    except OSError:
        # Sổ hỏng không được làm gãy một lượt chat. Mất trạng thái thì lần sau dựng lại.
        pass


def doc() -> TrangThai:
    """Đọc sổ. Trường lạ trong file bị bỏ qua, nên file của bản sau đọc ở bản trước vẫn chạy."""
    with _lock:
        raw = _doc()
    hop_le = {f for f in TrangThai.__dataclass_fields__}
    return TrangThai(**{k: v for k, v in raw.items() if k in hop_le})


def _luu(t: TrangThai) -> TrangThai:
    with _lock:
        _ghi(asdict(t))
    return t


def dat_lai() -> None:
    """Xoá sổ. Dùng cho test và cho nút Ngắt trên giao diện."""
    with _lock:
        try:
            STORE_PATH.unlink()
        except OSError:
            pass


# ============================================================
# Phân loại lỗi
# ============================================================

# Nhận diện theo CHỮ nhà cung cấp/trang trả về. Cố ý để rộng và ưu tiên theo thứ tự: một câu
# vừa có "limit" vừa có "sign in" thì hết lượt nặng hơn, vì đăng nhập lại cũng không giải quyết.
_DAU_HIEU = (
    (USAGE_LIMITED, (
        "you've reached your limit", "you have reached your limit", "usage limit",
        "message limit", "rate limit", "too many requests", "hit your limit",
        "limit reached", "bạn đã đạt giới hạn",
    )),
    (CHALLENGE_REQUIRED, (
        "just a moment", "checking your browser", "cloudflare", "captcha",
        "verify you are human", "unusual activity", "security check",
    )),
    (AUTH_REQUIRED, (
        "log in", "login", "sign in", "session expired", "unauthorized",
        "please authenticate", "đăng nhập",
    )),
    (TRANSPORT_BROKEN, (
        "selector not found", "composer not found", "no response stream",
        "tee not installed", "khong tim thay o soan",
    )),
)


def phan_loai(text: str) -> str:
    """Đoán loại lỗi từ câu mà trang hoặc transport trả về. UNKNOWN nếu không nhận ra.

    UNKNOWN là câu trả lời HỢP LỆ, không phải thất bại: nhận bừa một loại rồi đặt cooldown 30
    phút cho một lỗi mạng thoáng qua là tệ hơn nhiều so với thừa nhận không biết.
    """
    s = (text or "").strip().lower()
    if not s:
        return UNKNOWN
    for loai, dau in _DAU_HIEU:
        for d in dau:
            if d in s:
                return loai
    return UNKNOWN


# ============================================================
# Ghi sự kiện
# ============================================================

def ghi_thanh_cong(thread_id: str = "", now: Optional[float] = None) -> TrangThai:
    """Một lượt chạy trót lọt: xoá cooldown, xoá đếm hỏng, cộng bộ đếm ngày."""
    now = _now() if now is None else now
    t = doc()
    ngay = _hom_nay(now)
    if t.ngay != ngay:
        t.ngay = ngay
        t.so_luot_trong_ngay = 0
    t.state = READY
    t.last_success = now
    t.last_error = ""
    t.last_error_kind = ""
    t.failure_count = 0
    t.cooldown_until = 0.0
    t.cooldown_uoc = True
    t.auth_state = "ok"
    t.so_luot_trong_ngay += 1
    if thread_id:
        t.active_thread_id = thread_id
    return _luu(t)


def ghi_hong(message: str, kind: str = "", retry_after: float = 0.0,
             now: Optional[float] = None) -> TrangThai:
    """Một lượt hỏng. `kind` rỗng thì tự phân loại từ `message`.

    `retry_after` > 0 nghĩa là NHÀ CUNG CẤP nói mốc mở lại; lúc đó `cooldown_uoc=False` và
    giao diện được phép hiện giờ cụ thể. Không có thì Javis ước theo bảng mặc định và nói rõ
    là ước.
    """
    now = _now() if now is None else now
    loai = (kind or "").strip() or phan_loai(message)
    t = doc()
    t.state = loai if loai != UNKNOWN else TEMPORARY_ERROR
    t.last_error = str(message or "")[:600]
    t.last_error_kind = loai
    t.failure_count += 1
    if loai == AUTH_REQUIRED:
        t.auth_state = "expired"

    if retry_after and retry_after > 0:
        t.cooldown_until = now + min(float(retry_after), COOLDOWN_TOI_DA)
        t.cooldown_uoc = False
    else:
        giay = COOLDOWN_MAC_DINH.get(t.state, 0)
        t.cooldown_until = (now + min(giay, COOLDOWN_TOI_DA)) if giay else 0.0
        t.cooldown_uoc = True

    # Phanh chống vòng lặp thử lại: hỏng liên tiếp đủ nhiều thì nghỉ dài, kể cả lỗi vốn nhẹ.
    if t.failure_count >= NGUONG_NGAT:
        t.cooldown_until = max(t.cooldown_until, now + COOLDOWN_NGAT)
        t.cooldown_uoc = True

    return _luu(t)


def ghi_dang_nhap(ok: bool, now: Optional[float] = None) -> TrangThai:
    """Sau khi chủ máy đăng nhập tay xong (hoặc bấm Ngắt)."""
    now = _now() if now is None else now
    t = doc()
    t.auth_state = "ok" if ok else ""
    t.state = READY if ok else AUTH_REQUIRED
    if ok:
        # Đăng nhập lại giải quyết đúng cảnh AUTH_REQUIRED, nên xoá cooldown của riêng nó.
        # Hết lượt hay bị Cloudflare thì đăng nhập lại KHÔNG giúp gì, giữ nguyên cooldown.
        if t.last_error_kind == AUTH_REQUIRED:
            t.cooldown_until = 0.0
            t.failure_count = 0
            t.last_error = ""
            t.last_error_kind = ""
    return _luu(t)


# ============================================================
# Hỏi trước khi chạy
# ============================================================

@dataclass(frozen=True)
class Chan:
    """Kết quả của `co_chay_duoc`: chạy được, hay bị chặn vì lý do nói được."""
    ok: bool
    kind: str = ""
    message: str = ""


def co_chay_duoc(now: Optional[float] = None) -> Chan:
    """Có nên mở trình duyệt cho lượt này không. Gọi TRƯỚC khi spawn Chromium.

    Trả `Chan(ok=False, ...)` kèm câu nói được để đưa thẳng cho người dùng.
    """
    now = _now() if now is None else now
    t = doc()

    if t.state == DISABLED:
        return Chan(False, DISABLED,
                    "Engine ChatGPT Web đang tắt. Bật biến môi trường "
                    "JAVIS_ENABLE_WEB_CHAT=true rồi khởi động lại Javis.")

    if t.dang_nghi(now):
        phut = int(t.con_nghi(now) // 60) + 1
        if t.last_error_kind == USAGE_LIMITED:
            ly_do = "gói ChatGPT Web đã chạm trần lượt"
        elif t.last_error_kind == CHALLENGE_REQUIRED:
            ly_do = "ChatGPT Web đang chặn bằng kiểm tra bảo mật, cần mở trình duyệt qua tay"
        elif t.last_error_kind == TRANSPORT_BROKEN:
            ly_do = "Javis không đọc được luồng trả lời của trang (trang có thể vừa đổi giao diện)"
        else:
            ly_do = f"hỏng {t.failure_count} lần liên tiếp"
        uoc = " (mốc do Javis ước, nhà cung cấp không nói rõ)" if t.cooldown_uoc else ""
        return Chan(False, t.last_error_kind or TEMPORARY_ERROR,
                    f"Đang nghỉ thêm khoảng {phut} phút{uoc}: {ly_do}. "
                    f"Chọn model khác ở ô chọn model nếu cần làm ngay.")

    if t.auth_state == "expired" or t.state == AUTH_REQUIRED:
        return Chan(False, AUTH_REQUIRED,
                    "Phiên ChatGPT Web đã hết hạn. Mở trang Models, thẻ ChatGPT, "
                    "bấm Mở cửa sổ đăng nhập rồi đăng nhập lại một lần.")

    return Chan(True)


def tom_tat() -> dict:
    """Ảnh chụp cho giao diện. KHÔNG bịa phần trăm quota (spec mục 8)."""
    t = doc()
    now = _now()
    return {
        "state": t.state,
        "dang_nghi": t.dang_nghi(now),
        "con_nghi_giay": int(t.con_nghi(now)),
        "cooldown_uoc": t.cooldown_uoc,
        "last_success": t.last_success,
        "last_error": t.last_error,
        "last_error_kind": t.last_error_kind,
        "failure_count": t.failure_count,
        "auth_state": t.auth_state,
        "so_luot_trong_ngay": t.so_luot_trong_ngay if t.ngay == _hom_nay(now) else 0,
        # Nói thẳng là không quan sát được, thay vì để giao diện tự đoán.
        "quota_source": "web_subscription",
        "quota_visibility": "unknown",
    }
