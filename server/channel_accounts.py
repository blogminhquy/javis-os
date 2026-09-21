"""Kho TÀI KHOẢN KÊNH dạng token (Telegram Bot, Zalo Bot, và kênh `kind == "bot"` sau này).

Trước 0.61.0, token nằm TRONG bản ghi bot (`chatbot_store`): một bot = một token = một kênh.
Điều đó trộn hai thứ khác bản chất: TÀI KHOẢN (danh tính ở nền tảng, có token) và PHÂN CÔNG
(Agent nào đứng trực, mức quyền nào). Tách ra thì một nhân viên AI trực được nhiều tài khoản
(bot Telegram và bot Zalo cùng một vai), tài khoản đổi bot mà không mất lịch sử, và tab Tài khoản bot của
trang Hội thoại liệt kê mọi tài khoản như nhau bất kể kênh.

Hình dạng theo đúng khuôn `chatbot_store`: bản ghi ở JSON, token qua `secrets_store`, không bao
giờ trả token ra giao diện.

Tài khoản DI TRÚ từ bot cũ giữ NGUYÊN id của bot (`bot_xxx`) làm id tài khoản: kho hội thoại
đang khoá tài khoản theo `f"{kenh}:{bot_id}"`, giữ id là mọi hội thoại cũ vẫn thuộc đúng tài
khoản mà không phải sửa một dòng nào trong SQLite. Tài khoản tạo mới có id `acc_xxx`.

Tài khoản của kênh `kind == "account"` (Zalo cá nhân) KHÔNG ở đây: chúng sống ở trang Kết nối
(`mcp_store`) và module kênh tự liệt kê. Kho này chỉ giữ thứ có token.
"""
from __future__ import annotations

import json
import os
import threading
import time
import uuid
from typing import Any, Dict, List, Optional

import channels
import secrets_store
from config import STATE_DIR

STORE_PATH = STATE_DIR / "channel_accounts.json"
_lock = threading.RLock()

LABEL_MAX = 80
LOI_KHONG_CO = "Không có tài khoản kênh nào id đó"


def _now() -> float:
    return time.time()


def _load() -> dict:
    try:
        d = json.loads(STORE_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {"version": 1, "accounts": []}
    except Exception:
        try:
            STORE_PATH.rename(STORE_PATH.with_suffix(".json.hong"))
        except Exception:
            pass
        return {"version": 1, "accounts": []}
    if not isinstance(d, dict) or not isinstance(d.get("accounts"), list):
        return {"version": 1, "accounts": []}
    return d


def _save(d: dict) -> None:
    STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = STORE_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, STORE_PATH)


def _clean_kenh(v: Any) -> str:
    s = str(v or "").strip().lower()
    return s if s in channels.bot_ids() else ""


def _clean_label(v: Any) -> str:
    return " ".join(str(v or "").split())[:LABEL_MAX]


def _clean_external(v: Any) -> str:
    return str(v or "").strip().lstrip("@")[:120]


def _clean_brain(v: Any) -> str:
    return " ".join(str(v or "").split())[:200]


def _public(a: dict) -> dict:
    out = {k: v for k, v in a.items() if k not in ("token", "token_enc")}
    out["token_set"] = bool(a.get("token_enc"))
    out["kind"] = "bot"
    s = channels.spec(a.get("channel") or "")
    out["channel_label"] = s.nhan if s else str(a.get("channel") or "")
    out["logo"] = s.logo if s else ""
    out.setdefault("meta", {})
    return out


# ============================================================
# Đọc
# ============================================================
def list_accounts(channel: str = "", brain: str = "") -> List[dict]:
    """`brain` rỗng = mọi brain (hành vi cũ, và là thứ mã nội bộ cần: poller phải thấy hết).

    Có `brain` thì trả tài khoản của brain đó CỘNG tài khoản chưa gán brain nào. Tài khoản
    chưa gán là bản ghi cũ mà lúc di trú không suy ra được chủ (không bot nào trực) - cho nó
    hiện ở mọi brain, vì thà thấy thừa một thẻ còn hơn có một token tồn tại mà không màn hình
    nào hiện ra, không ai xoá hay gắn lại được.
    """
    k = str(channel or "").strip().lower()
    br = _clean_brain(brain)
    out = []
    with _lock:
        for a in _load()["accounts"]:
            if k and a.get("channel") != k:
                continue
            if br and _clean_brain(a.get("brain")) not in ("", br):
                continue
            out.append(_public(a))
    return out


def get_account(account_id: str) -> Optional[dict]:
    with _lock:
        for a in _load()["accounts"]:
            if a.get("id") == account_id:
                return _public(a)
    return None


def get_token(account_id: str) -> str:
    """Token THẬT - chỉ cho mã nội bộ. TUYỆT ĐỐI không trả ra giao diện."""
    with _lock:
        for a in _load()["accounts"]:
            if a.get("id") == account_id:
                return secrets_store.decrypt(a.get("token_enc", "")) or ""
    return ""


def owner_of(username: str, channel: str, exclude_id: str = "") -> Optional[dict]:
    """Tài khoản nào đang giữ đúng con bot này (so theo tên tài khoản từ getMe, THEO KÊNH).

    Một token chỉ được MỘT tiến trình long-polling; hai poller cùng token thì máy chủ trả 409
    và cả hai cùng chết. Tên tài khoản là không gian tên riêng của từng nền tảng.
    """
    u = _clean_external(username).lower()
    k = _clean_kenh(channel)
    if not u:
        return None
    with _lock:
        for a in _load()["accounts"]:
            if a.get("id") == exclude_id:
                continue
            if k and a.get("channel") != k:
                continue
            if _clean_external(a.get("external_id")).lower() == u:
                return _public(a)
    return None


# ============================================================
# Ghi
# ============================================================
def create_account(data: dict, account_id: str = "") -> tuple[Optional[str], str]:
    """Tạo tài khoản token. Trả (id, "") hoặc (None, lý do).

    `account_id` chỉ dùng khi DI TRÚ từ bot cũ (giữ id bot làm id tài khoản); bình thường để
    trống để sinh `acc_...`.
    """
    kenh = _clean_kenh(data.get("channel"))
    if not kenh:
        return None, (f"Kênh '{data.get('channel')}' không gắn được tài khoản token. Kênh có: "
                      + ", ".join(channels.bot_ids()))
    tok = str(data.get("token") or "").strip()
    if not tok:
        return None, f"Thiếu token {channels.nhan(kenh)}"
    ext = _clean_external(data.get("external_id"))
    trung = owner_of(ext, kenh) if ext else None
    if trung:
        return None, (f"Bot {channels.nhan(kenh)} \"{ext}\" đã có ở tài khoản "
                      f"\"{trung.get('label') or ext}\" rồi. Mỗi token một tài khoản.")
    with _lock:
        d = _load()
        aid = str(account_id or "").strip() or ("acc_" + uuid.uuid4().hex[:10])
        if any(a.get("id") == aid for a in d["accounts"]):
            return None, "Trùng id tài khoản"
        meta = data.get("meta") if isinstance(data.get("meta"), dict) else {}
        a = {
            "id": aid, "channel": kenh,
            # BRAIN CHỦ của tài khoản. Thêm ở 0.62.4: trước đó tài khoản là toàn cục nên tab
            # Tài khoản bot trộn của mọi brain, nhìn không biết cái nào của mình (chủ repo báo
            # 21/09). Rỗng = chưa gán, hiện ở mọi brain cho tới khi có bot nhận.
            "brain": _clean_brain(data.get("brain")),
            "label": _clean_label(data.get("label")) or ext or channels.nhan(kenh),
            "external_id": ext,
            "token_enc": secrets_store.encrypt(tok),
            "meta": meta,
            "created_at": _now(), "updated_at": _now(),
        }
        d["accounts"].append(a)
        _save(d)
        return aid, ""


_PATCHABLE = ("label", "token", "external_id", "meta", "brain")


def update_account(account_id: str, patch: dict) -> tuple[bool, str]:
    with _lock:
        d = _load()
        for a in d["accounts"]:
            if a.get("id") != account_id:
                continue
            if "external_id" in patch:
                ext = _clean_external(patch.get("external_id"))
                if ext and owner_of(ext, a.get("channel") or "", exclude_id=account_id):
                    return False, f"Bot \"{ext}\" đã có ở một tài khoản khác."
                a["external_id"] = ext
            if "label" in patch:
                lb = _clean_label(patch.get("label"))
                if lb:
                    a["label"] = lb
            if "brain" in patch:
                # Chuyển tài khoản sang brain khác. Cho phép đặt về RỖNG (= chưa gán, hiện ở
                # mọi brain): đó là lối thoát khi lỡ gán nhầm vào một brain rồi xoá brain đó.
                a["brain"] = _clean_brain(patch.get("brain"))
            if "token" in patch:
                tok = str(patch.get("token") or "").strip()
                if tok:
                    a["token_enc"] = secrets_store.encrypt(tok)
            if "meta" in patch and isinstance(patch.get("meta"), dict):
                m = dict(a.get("meta") or {})
                m.update(patch["meta"])
                a["meta"] = m
            a["updated_at"] = _now()
            _save(d)
            return True, ""
    return False, LOI_KHONG_CO


def delete_account(account_id: str) -> tuple[bool, str]:
    with _lock:
        d = _load()
        n = len(d["accounts"])
        d["accounts"] = [a for a in d["accounts"] if a.get("id") != account_id]
        if len(d["accounts"]) == n:
            return False, LOI_KHONG_CO
        _save(d)
        return True, ""


def ensure_from_bot(bot: dict) -> Optional[str]:
    """DI TRÚ: tài khoản cho một bản ghi bot cũ còn mang `token_enc`. Trả id tài khoản.

    Id tài khoản = id bot, để khoá `f"{kenh}:{bot_id}"` của kho hội thoại giữ nguyên. Chép
    thẳng `token_enc` (đã mã hoá) chứ không giải mã rồi mã hoá lại: máy không có key thì
    giải mã trả chuỗi rỗng và di trú xong bot mất token trong im lặng.
    """
    bid = str(bot.get("id") or "")
    if not bid or not bot.get("token_enc"):
        return None
    with _lock:
        d = _load()
        for a in d["accounts"]:
            if a.get("id") == bid:
                return bid
        kenh = _clean_kenh(bot.get("channel")) or (channels.bot_ids() or ("telegram",))[0]
        d["accounts"].append({
            "id": bid, "channel": kenh,
            "label": _clean_label(bot.get("name")) or channels.nhan(kenh),
            "external_id": _clean_external(bot.get("bot_username")),
            "token_enc": bot["token_enc"],
            "brain": _clean_brain(bot.get("brain")),
            "meta": {"di_tru_tu_bot": True},
            "created_at": float(bot.get("created_at") or _now()), "updated_at": _now(),
        })
        _save(d)
        return bid


def nhan_brain(account_id: str, brain: str) -> bool:
    """Tài khoản CHƯA gán brain thì nhận brain này. Đã có chủ rồi thì không đụng.

    Gọi khi một bot nhận tài khoản: brain của bot chính là brain của tài khoản. Cố ý KHÔNG
    ghi đè chủ cũ - đổi chủ là việc người dùng làm tay ở form sửa tài khoản, không phải thứ
    xảy ra sau lưng chỉ vì gắn bot của brain khác vào.
    """
    br = _clean_brain(brain)
    if not account_id or not br:
        return False
    with _lock:
        d = _load()
        for a in d["accounts"]:
            if a.get("id") != account_id or _clean_brain(a.get("brain")):
                continue
            a["brain"] = br
            a["updated_at"] = _now()
            _save(d)
            return True
    return False


def dien_brain_con_thieu(brain_cua) -> int:
    """DI TRÚ một lần: điền `brain` cho tài khoản có trước 0.62.4. Trả số bản ghi đã điền.

    `brain_cua(account_id)` do NGƯỜI GỌI cấp (main.py, chỗ nhìn thấy cả `chatbot_store`). Module
    này không tự tra bot được: `chatbot_store` đã import nó, tra ngược là vòng import.

    Không suy ra được (không bot nào trực) thì để RỖNG chứ không đoán đại vào brain mặc định:
    tài khoản rỗng brain hiện ở mọi brain, nên người dùng vẫn thấy và gắn lại được; đoán sai
    thì nó biến mất khỏi đúng cái brain mà người ta đang tìm.
    """
    n = 0
    with _lock:
        d = _load()
        for a in d["accounts"]:
            if "brain" in a:
                continue
            br = ""
            try:
                br = _clean_brain(brain_cua(a.get("id") or ""))
            except Exception:      # noqa: BLE001 - tra hỏng thì để rỗng, đừng chặn khởi động
                br = ""
            a["brain"] = br
            n += 1
        if n:
            _save(d)
    return n
