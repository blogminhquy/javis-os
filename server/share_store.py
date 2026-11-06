"""share_store.py - kho LINK CHIA SẺ CÔNG KHAI của từng file trong brain.

Một link là một token ngẫu nhiên trỏ tới (brain, đường dẫn file). Ai cầm link đều xem được,
KHÔNG cần đăng nhập - đó là toàn bộ mục đích: chủ dự án làm một trang .html hay một ghi chú
.md rồi gửi cho người khác xem ngay.

Ba điều quyết định hình dạng kho này:

1. TOKEN LÀ THỨ DUY NHẤT CHẶN NGƯỜI LẠ, nên nó phải không đoán được. `secrets.token_urlsafe(18)`
   cho 144 bit ngẫu nhiên. Không dùng uuid4 (chỉ 122 bit và có phần đoán được), không dùng
   tên file băm ra (đoán được tên file là đoán được link).

2. LINK TRỎ TỚI FILE THẬT, không chụp lại nội dung (chủ dự án chọn 18/09). Sửa file thì người
   xem tải lại là thấy bản mới. Nên kho chỉ giữ ĐƯỜNG DẪN, và mọi phép kiểm quyền đọc file
   vẫn đi qua rào chống traversal chung của server lúc phục vụ, không phải lúc tạo link.

3. MỘT FILE CHỈ CÓ MỘT LINK. Bấm Chia sẻ lần hai trên cùng file thì trả lại đúng token cũ chứ
   không đẻ token mới: người ta đã gửi link đi rồi, đẻ thêm là mỗi lần bấm lại một link khác
   mà link cũ vẫn sống, không ai thu lại được.
"""
import json
import os
import re
import secrets
import threading
import time
import unicodedata
from pathlib import Path

from config import STATE_DIR
import localefmt

_LOCK = threading.RLock()
STORE = STATE_DIR / "share_links.json"

# Trần số link. Kho là một file JSON đọc/ghi nguyên khối, và nó nằm trên đường phục vụ MỌI
# lượt mở link công khai, nên không được phép phình vô hạn.
MAX_LINKS = 2000


def _read_raw() -> dict:
    try:
        d = json.loads(STORE.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return d if isinstance(d, dict) else {}


def _write_raw(d: dict) -> None:
    STORE.parent.mkdir(parents=True, exist_ok=True)
    tmp = STORE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, STORE)          # thay nguyên khối: đọc song song không bao giờ thấy file dở


def _norm_path(p: str) -> str:
    """Chuẩn hoá đường dẫn để SO SÁNH (tìm link đã có của cùng một file).

    KHÔNG phải hàng rào bảo mật: rào chống traversal nằm ở `_safe_serve_path` phía server, chạy
    lúc phục vụ. Ở đây chỉ cần hai cách viết cùng một file quy về một chuỗi.
    """
    return str(p or "").strip().replace("\\", "/").lstrip("/")


def create(brain: str, path: str, nhan: str = "") -> dict:
    """Tạo (hoặc lấy lại) link của một file. Trả bản ghi kèm `token`."""
    brain = str(brain or "brain")
    path = _norm_path(path)
    if not path:
        raise ValueError(localefmt.chu("Thiếu đường dẫn file", "Missing file path"))
    with _LOCK:
        d = _read_raw()
        for tok, ban in d.items():
            if (isinstance(ban, dict) and not is_conversation(ban) and ban.get("brain") == brain
                    and _norm_path(ban.get("path")) == path):
                return dict(ban, token=tok)          # đã có link: trả lại đúng cái cũ
        if len(d) >= MAX_LINKS:
            raise ValueError(localefmt.chu(f"Đã đạt trần {MAX_LINKS} link chia sẻ, gỡ bớt link cũ trước",
                                           f"Reached the limit of {MAX_LINKS} share links, remove some old links first"))
        tok = secrets.token_urlsafe(18)
        d[tok] = {"brain": brain, "path": path, "nhan": str(nhan or ""), "tao_luc": time.time()}
        _write_raw(d)
        return dict(d[tok], token=tok)


def _find(d: dict, ident: str):
    """(token, record) for an address: the random token itself, or a custom slug (any case)."""
    if ident in d and isinstance(d[ident], dict):
        return ident, d[ident]
    low = ident.lower()
    if not SLUG_RE.match(low):
        return None, None
    for tok, ban in d.items():
        if isinstance(ban, dict) and ban.get("slug") == low:
            return tok, ban
    return None, None


def get(token: str):
    """Bản ghi của một token, hoặc None. Đây là cửa DUY NHẤT của đường công khai.

    `token` is the address in the URL: the random token, or the custom slug set on the Share links page. The record
    always carries the random `token` (the internal id the stats and the dashboard key on)."""
    tok = str(token or "").strip()
    if not tok:
        return None
    tok, ban = _find(_read_raw(), tok)
    if not isinstance(ban, dict):
        return None
    if is_conversation(ban):
        return dict(ban, token=tok) if ban.get("session_id") else None
    if not ban.get("path"):
        return None
    return dict(ban, token=tok)


def remove(token: str) -> bool:
    """Thu hồi một link. Sau lệnh này link cũ trả 404 cho tất cả mọi người."""
    tok = str(token or "").strip()
    with _LOCK:
        d = _read_raw()
        if tok not in d:
            return False
        d.pop(tok, None)
        _write_raw(d)
        return True


def rename(token: str, nhan: str):
    """Đổi tên hiển thị của một link (0.65.30). Rỗng = bỏ tên tự đặt, trang lại tự lấy tiêu đề
    file. Trả bản ghi mới, hoặc None nếu token không có. Token và đường dẫn KHÔNG đổi: link đã
    gửi đi vẫn sống."""
    tok = str(token or "").strip()
    ten = " ".join(str(nhan or "").split())[:120]
    with _LOCK:
        d = _read_raw()
        ban = d.get(tok)
        if not isinstance(ban, dict):
            return None
        ban["nhan"] = ten
        _write_raw(d)
        return dict(ban, token=tok)


# ---------------------------------------------------------------- custom address (slug)
#
# Owner, 2026-11-06: "ngoài đổi tên thì có thể đổi được đường dẫn phía sau". A link can carry a readable address,
# /s/vibecode-javis, next to its random token. Three rules:
#
# 1. The random token KEEPS working. Links already sent out must not break, and the token is the unguessable one, so
#    keeping it opens nothing new. Revoking kills both at once.
# 2. Only one slug per link. Changing it frees the old slug (it then answers 404), clearing it leaves the token only.
# 3. A slug is guessable by design. The dashboard says so next to the field; whoever wants a private link keeps the
#    random token.
SLUG_MIN, SLUG_MAX = 3, 64
SLUG_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?$")


def slugify(text: str) -> str:
    """'Vibecode Javis GitHub!' -> 'vibecode-javis-github'. Strips Vietnamese marks (đ -> d)."""
    t = unicodedata.normalize("NFD", str(text or "")).replace("đ", "d").replace("Đ", "D")
    t = "".join(c for c in t if unicodedata.category(c) != "Mn").lower()
    t = re.sub(r"[^a-z0-9]+", "-", t).strip("-")
    return re.sub(r"-{2,}", "-", t)[:SLUG_MAX].strip("-")


def set_slug(token: str, slug: str):
    """Give a link a custom address, or clear it with an empty `slug`. Returns the new record, None when the token is
    unknown; raises ValueError when the slug is too short or already taken."""
    tok = str(token or "").strip()
    raw = str(slug or "").strip()
    new = slugify(raw)
    if raw and len(new) < SLUG_MIN:
        raise ValueError(localefmt.chu(f"Đường dẫn cần ít nhất {SLUG_MIN} chữ hoặc số",
                                       f"The address needs at least {SLUG_MIN} letters or digits"))
    with _LOCK:
        d = _read_raw()
        ban = d.get(tok)
        if not isinstance(ban, dict):
            return None
        if new:
            for other, b in d.items():
                if other == tok:
                    continue
                if other.lower() == new or (isinstance(b, dict) and b.get("slug") == new):
                    raise ValueError(localefmt.chu("Đường dẫn này đã có link khác dùng",
                                                   "Another link already uses this address"))
            ban["slug"] = new
        else:
            ban.pop("slug", None)
        _write_raw(d)
        return dict(ban, token=tok)


def public_path(ban) -> str:
    """The address to hand out: /s/<slug> when the link has one, else /s/<token>."""
    return "/s/" + (str(ban.get("slug") or "") or str(ban.get("token") or ""))


def list_links(brain: str = "") -> list:
    """Mọi link đang sống, mới nhất trước. Lọc theo brain nếu truyền."""
    d = _read_raw()
    ra = [dict(v, token=k) for k, v in d.items()
          if isinstance(v, dict) and (not brain or v.get("brain") == brain)]
    ra.sort(key=lambda x: x.get("tao_luc") or 0, reverse=True)
    return ra


def for_file(brain: str, path: str):
    """Link đã có của đúng file này, hoặc None. Dùng để nút Chia sẻ biết mình đang bật hay tắt."""
    brain = str(brain or "brain")
    path = _norm_path(path)
    for tok, ban in _read_raw().items():
        if (isinstance(ban, dict) and not is_conversation(ban) and ban.get("brain") == brain
                and _norm_path(ban.get("path")) == path):
            return dict(ban, token=tok)
    return None


# ---------------------------------------------------------------- link HỘI THOẠI (0.171.0)
#
# Chủ repo 15/10/2026: chia sẻ cả một đoạn hội thoại cho người khác đọc, giống link file và
# quản lý chung ở trang Link chia sẻ. Cùng kho, cùng token, phân biệt bằng `loai: "hoi_thoai"`.
#
# Khác link file ở MỘT điều có chủ đích: link hội thoại là ẢNH CHỤP tới lúc bấm chia sẻ, không
# phải bản sống. File thì người chia sẻ sửa có chủ ý; hội thoại thì cứ thế dài thêm, và câu hỏi
# riêng tư gõ SAU khi gửi link không được tự lọt ra ngoài. Bấm Chia sẻ lại trên cùng hội thoại
# thì dời mốc tới hiện tại và GIỮ token: người đã có link thấy thêm phần mới, không link mới nào
# phải gửi lại. Mốc là cặp (ts, id) của tin cuối, đúng thứ tự `ORDER BY ts, id` của kho phiên.
KIND_CONVERSATION = "hoi_thoai"


def is_conversation(ban) -> bool:
    return isinstance(ban, dict) and ban.get("loai") == KIND_CONVERSATION


def create_conversation(session_id: str, brain: str = "", nhan: str = "", moc=None) -> dict:
    """Tạo link cho một hội thoại, hoặc DỜI MỐC của link đã có tới `moc` (giữ token)."""
    sid = str(session_id or "").strip()
    if not sid:
        raise ValueError(localefmt.chu("Thiếu mã hội thoại", "Missing conversation id"))
    moc = list(moc) if moc else None
    with _LOCK:
        d = _read_raw()
        for tok, ban in d.items():
            if is_conversation(ban) and ban.get("session_id") == sid:
                ban["moc"] = moc
                ban["cap_nhat_luc"] = time.time()
                _write_raw(d)
                return dict(ban, token=tok)
        if len(d) >= MAX_LINKS:
            raise ValueError(localefmt.chu(f"Đã đạt trần {MAX_LINKS} link chia sẻ, gỡ bớt link cũ trước",
                                           f"Reached the limit of {MAX_LINKS} share links, remove some old links first"))
        tok = secrets.token_urlsafe(18)
        d[tok] = {"loai": KIND_CONVERSATION, "session_id": sid, "brain": str(brain or ""), "path": "",
                  "nhan": " ".join(str(nhan or "").split())[:120], "moc": moc, "tao_luc": time.time()}
        _write_raw(d)
        return dict(d[tok], token=tok)


def for_conversation(session_id: str):
    """Link đã có của hội thoại này, hoặc None."""
    sid = str(session_id or "").strip()
    for tok, ban in _read_raw().items():
        if is_conversation(ban) and ban.get("session_id") == sid:
            return dict(ban, token=tok)
    return None
