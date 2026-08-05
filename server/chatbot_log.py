"""Nhật ký hội thoại khách của từng bot, và thống kê CÂU BOT TRẢ LỜI KHÔNG NỔI.

Thứ hai mới là lý do module này tồn tại. Nhật ký thì hay, nhưng danh sách câu bot bí là thứ có
giá trị kinh doanh trực tiếp: nó chỉ ĐÚNG chỗ tài liệu của chủ đang thiếu, bằng lời của chính
khách hàng. Chủ đọc xong biết cần viết thêm cái gì vào brain, thay vì đoán.

Vì sao là JSONL riêng chứ không nhét vào kho phiên (`sessions`):

  - Kho phiên đã lưu ĐỦ nội dung hội thoại rồi (kênh `bot:<slug>`), nên chép lại là thừa. Thứ
    thiếu là mấy cờ mà chỉ lúc chạy mới biết: lượt này có tìm được tài liệu không, có chuyển
    người thật không. Bảng phiên không có chỗ cho chúng, và thêm cột vào bảng dùng chung chỉ
    để phục vụ một tính năng là cách làm bảng phình ra không kiểm soát được.
  - Nhật ký này CẮT BỚT theo trần dòng. Dữ liệu tự hết hạn không nên nằm chung với dữ liệu
    người dùng mong đợi là còn mãi.

Ghi bằng append nên một dòng hỏng không kéo theo dòng khác, và đọc thì bỏ qua dòng hỏng.
"""
from __future__ import annotations

import json
import os
import re
import sys
import threading
import time
import unicodedata
from pathlib import Path
from typing import Any, Dict, List

from config import STATE_DIR

THU_MUC = STATE_DIR / "chatbot-logs"

MAX_DONG = 2_000        # trần mỗi bot; quá thì cắt phần cũ nhất
CAT_XUONG = 1_500       # cắt thì cắt hẳn xuống mức này, đừng cắt một dòng mỗi lần
MAX_CHU = 2_000         # trần độ dài câu hỏi/câu trả lời lưu lại

_lock = threading.Lock()


def _path(bot_id: str) -> Path:
    an = re.sub(r"[^A-Za-z0-9_-]", "", str(bot_id or ""))[:64] or "khong-ten"
    return THU_MUC / f"{an}.jsonl"


def _cat(v: Any) -> str:
    return str(v or "")[:MAX_CHU]


def ghi(bot_id: str, rec: dict) -> None:
    """Thêm một lượt. Nuốt mọi lỗi: nhật ký hỏng thì cùng lắm mất thống kê, KHÔNG được làm
    gãy câu trả lời cho khách đang chờ."""
    try:
        d = {
            "ts": time.time(),
            "chat_id": str(rec.get("chat_id") or ""),
            "chat_type": str(rec.get("chat_type") or ""),
            "user_name": str(rec.get("user_name") or "")[:80],
            "hoi": _cat(rec.get("hoi")),
            "dap": _cat(rec.get("dap")),
            # Lý do KỸ THUẬT khi lượt gãy (engine lỗi, hết quota, chưa cấu hình...). Khách chỉ
            # nhận một câu xin lỗi chung, nên nếu không giữ ở đây thì không còn chỗ nào cho chủ
            # biết vì sao bot im - đúng ca đã xảy ra thật.
            "loi": str(rec.get("loi") or "")[:500],
            "co_tai_lieu": bool(rec.get("co_tai_lieu")),
            "nguon": [str(x)[:200] for x in (rec.get("nguon") or [])][:8],
            "chuyen_nguoi": bool(rec.get("chuyen_nguoi")),
            "bi": bool(rec.get("bi")),
        }
        p = _path(bot_id)
        with _lock:
            p.parent.mkdir(parents=True, exist_ok=True)
            with p.open("a", encoding="utf-8") as f:
                f.write(json.dumps(d, ensure_ascii=False) + "\n")
            _cat_bot(p)
    except Exception as e:
        print(f"[chatbot log] {e}", file=sys.stderr)


def _cat_bot(p: Path) -> None:
    """Cắt phần cũ khi file quá dài. Gọi trong _lock."""
    try:
        if p.stat().st_size < 200_000:
            return                      # ước lượng rẻ, khỏi đọc file mỗi lượt
        dong = p.read_text(encoding="utf-8", errors="replace").splitlines()
        if len(dong) <= MAX_DONG:
            return
        tmp = p.with_suffix(".jsonl.tmp")
        tmp.write_text("\n".join(dong[-CAT_XUONG:]) + "\n", encoding="utf-8")
        os.replace(tmp, p)
    except Exception as e:
        print(f"[chatbot log cắt] {e}", file=sys.stderr)


def _nap(bot_id: str) -> List[dict]:
    p = _path(bot_id)
    try:
        raw = p.read_text(encoding="utf-8", errors="replace")
    except FileNotFoundError:
        return []
    except Exception as e:
        print(f"[chatbot log đọc] {e}", file=sys.stderr)
        return []
    ra = []
    for dong in raw.splitlines():
        dong = dong.strip()
        if not dong:
            continue
        try:
            ra.append(json.loads(dong))
        except Exception:
            continue        # một dòng hỏng không được làm mất cả nhật ký
    return ra


def doc(bot_id: str, limit: int = 50) -> List[dict]:
    """Các lượt gần nhất, MỚI TRƯỚC."""
    n = max(1, min(int(limit or 50), 500))
    return list(reversed(_nap(bot_id)))[:n]


def _chuan(s: str) -> str:
    """Chuẩn hoá câu hỏi để gom trùng: bỏ dấu, bỏ chữ hoa, bỏ dấu câu. "Giá bao nhiêu?" và
    "gia bao nhieu" là MỘT câu khách hỏi, đếm thành hai thì không thấy được nó hỏi nhiều."""
    s = unicodedata.normalize("NFD", str(s or "").lower())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn").replace("đ", "d")
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def lo_hong(bot_id: str, limit: int = 30) -> List[dict]:
    """Câu bot trả lời không nổi, gom trùng và xếp theo SỐ LẦN HỎI giảm dần.

    Xếp theo số lần chứ không theo thời gian: thứ đáng viết tài liệu bổ sung trước là thứ
    nhiều khách hỏi nhất, không phải thứ vừa mới hỏi.
    """
    gom: Dict[str, dict] = {}
    for r in _nap(bot_id):
        if not r.get("bi"):
            continue
        k = _chuan(r.get("hoi"))
        if not k:
            continue
        g = gom.setdefault(k, {"hoi": r.get("hoi") or "", "lan": 0, "lan_cuoi": 0.0,
                               "chuyen_nguoi": 0})
        g["lan"] += 1
        if (r.get("ts") or 0) > g["lan_cuoi"]:
            g["lan_cuoi"] = r.get("ts") or 0
            g["hoi"] = r.get("hoi") or g["hoi"]      # giữ bản gần nhất, có dấu đầy đủ hơn
        if r.get("chuyen_nguoi"):
            g["chuyen_nguoi"] += 1
    ra = sorted(gom.values(), key=lambda g: (-g["lan"], -g["lan_cuoi"]))
    return ra[:max(1, min(int(limit or 30), 200))]


def tom_tat(bot_id: str) -> dict:
    """Vài con số cho thẻ bot. Đọc cả file nên đừng gọi trong vòng lặp danh sách."""
    rs = _nap(bot_id)
    if not rs:
        return {"luot": 0, "bi": 0, "chuyen_nguoi": 0, "ty_le_bi": 0.0, "lan_cuoi": 0.0}
    bi = sum(1 for r in rs if r.get("bi"))
    return {
        "luot": len(rs),
        "bi": bi,
        "chuyen_nguoi": sum(1 for r in rs if r.get("chuyen_nguoi")),
        "ty_le_bi": round(100.0 * bi / len(rs), 1),
        "lan_cuoi": max((r.get("ts") or 0) for r in rs),
    }


def xoa(bot_id: str) -> None:
    """Xoá nhật ký của một bot. Gọi khi xoá bot - giữ lại nhật ký của một bot không còn tồn
    tại thì không ai đọc được nữa mà vẫn nằm trên đĩa."""
    try:
        _path(bot_id).unlink()
    except FileNotFoundError:
        pass
    except Exception as e:
        print(f"[chatbot log xoá] {e}", file=sys.stderr)
