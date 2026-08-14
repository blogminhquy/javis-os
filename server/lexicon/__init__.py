"""Bộ từ vựng theo ngôn ngữ cho các CỔNG CHẶN - thay cho regex nhúng cứng tiếng Việt.

Vì sao có lớp này. Hành vi của Javis đang phụ thuộc vào việc người dùng gõ tiếng Việt ở hơn
mười chỗ: cổng đường tắt tiết kiệm token, cổng một bước chỉ đọc, bộ bắt khai man hành động,
bộ dò lời hứa suông, cò ghi ký ức, bộ dò bot bí. Mỗi chỗ là một `re.compile` chứa từ khoá
tiếng Việt bỏ dấu.

**Chỗ nguy hiểm KHÔNG phải "ngôn ngữ không có bộ từ vựng", mà là "ngôn ngữ có NỬA bộ từ
vựng".** Đo được trên mã thật trước khi sửa:

    "tóm tắt đơn hàng"    -> bị chặn đúng (mẫu `don hang` khớp)
    "summarize my orders" -> LỌT qua đường tắt, vì `summarize` khớp ALLOW còn DENY tiếng Anh
                             không có chữ "orders". Người dùng nhận một câu trả lời BỊA về
                             đơn hàng của chính họ.
    "สรุปยอดขายวันนี้"     -> không khớp gì cả -> `intent_uncertain` -> đi đường đầy đủ, AN TOÀN

Tiếng Thái an toàn vì nó không khớp gì hết. Tiếng Anh nguy hiểm vì nó khớp một nửa. Bài học:
**nửa bộ từ vựng tệ hơn không có bộ từ vựng nào**, nên hoặc làm cho đủ, hoặc tắt hẳn đường
tối ưu cho ngôn ngữ đó.

Luật suy biến (spec mục 4.3), theo LOẠI cổng chứ không theo một luật chung:

  MỞ RỘNG QUYỀN  (đường tắt, một bước chỉ đọc)  -> không có lexicon thì TỪ CHỐI, đi đường
                                                   đầy đủ. Trả giá bằng token, không trả giá
                                                   bằng tính đúng.
  BẮT LỖI        (khai man hành động, lời hứa)  -> không có lexicon thì KHÔNG được lặng lẽ
                                                   cho qua; đánh dấu `unverified` để trace
                                                   nhìn thấy được.
  TRÌNH BÀY      (cắt câu, cron ra chữ)         -> suy biến thô, không ai chết.

Một câu để nhớ: **thiếu bộ từ vựng làm Javis TỐN HƠN, không làm Javis LỎNG HƠN.**

Thêm ngôn ngữ: thêm `lexicon/<mã>.py` khai đủ các tên trong `BAT_BUOC`. Thiếu tên nào thì
`_kiem_parity` báo đỏ ngay lúc nạp chứ không để hỏng âm thầm giữa đường chạy.
"""
from __future__ import annotations

import importlib
from types import ModuleType
from typing import Dict, Optional

# Tên các tập BẮT BUỘC mọi lexicon phải khai. Đặt tên theo Ý NGHĨA chứ không theo chỗ gọi,
# để một tập dùng được ở nhiều cổng mà không phải đổi tên khi refactor chỗ gọi.
BAT_BUOC = (
    "DENY",              # fast path: dấu hiệu câu KHÔNG tự chứa (cần tool, cần dữ liệu live)
    "ALLOW",             # fast path: dấu hiệu câu tự chứa (giải thích, viết lách, tính toán)
    "WRITE_INTENT",      # có ý định GHI/thao tác ra ngoài
    "STATE_REF",         # nhắc tới trạng thái/ngữ cảnh trước đó
    "FALSE_ACTION",      # assistant KHAI đã làm xong một hành động
    "ACTION_VERBS",      # động từ hành động (dùng chung cho FALSE_ACTION)
    "QUANTITATIVE",      # câu trả lời có con số kèm đơn vị
    "CAPABILITY_DENIAL", # assistant khai "không có tool"
    "PROMISE",           # hứa sẽ báo lại sau
    "REMEMBER",          # user bảo "ghi nhớ điều này"
    "DENSE",             # lượt chat đáng chưng cất thành tri thức
    "STUCK",             # chatbot tự nhận là bí
)

_CACHE: Dict[str, Optional[ModuleType]] = {}


def _kiem_parity(mod: ModuleType, code: str) -> None:
    thieu = [t for t in BAT_BUOC if not hasattr(mod, t)]
    if thieu:
        raise ImportError(
            f"lexicon/{code}.py thiếu {', '.join(thieu)}. Mọi lexicon phải khai ĐỦ "
            f"{len(BAT_BUOC)} tập, nếu không thì cổng nào dùng tập thiếu sẽ hỏng trong im lặng."
        )


def get(code: str) -> Optional[ModuleType]:
    """Module lexicon của ngôn ngữ, hoặc None nếu chưa có.

    None là một câu trả lời HỢP LỆ và nơi gọi PHẢI xử lý nó theo luật suy biến ở đầu file,
    chứ không được coi như "dùng tạm tiếng Việt".
    """
    ma = str(code or "").strip().lower()
    if not ma:
        return None
    if ma in _CACHE:
        return _CACHE[ma]
    try:
        mod = importlib.import_module(f"lexicon.{ma}")
        _kiem_parity(mod, ma)
    except ImportError:
        mod = None
    _CACHE[ma] = mod
    return mod


def co(code: str) -> bool:
    return get(code) is not None


def ma_list() -> tuple:
    """Các ngôn ngữ đang CÓ bộ từ vựng. Quét thư mục thay vì khai tay, để thả một file vào
    là dùng được ngay - đúng lời hứa "thêm ngôn ngữ là thêm dữ liệu"."""
    import pathlib
    thu_muc = pathlib.Path(__file__).parent
    ra = []
    for p in sorted(thu_muc.glob("*.py")):
        if p.stem.startswith("_"):
            continue
        if co(p.stem):
            ra.append(p.stem)
    return tuple(ra)
