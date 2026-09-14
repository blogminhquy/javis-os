"""Dọn những câu Whisper BỊA ra đã lỡ nằm trong kho hội thoại.

    .venv/Scripts/python tools/don_ao_giac_stt.py            # chỉ xem, KHÔNG sửa gì
    .venv/Scripts/python tools/don_ao_giac_stt.py --xoa      # sửa thật (tự sao lưu DB trước)

Vì sao có file này: bộ lọc `stt.loc_ao_giac` (0.57.4) chặn từ lúc nghe trở đi, nhưng những tin
nhắn đã lỡ vào kho trước đó thì vẫn nằm nguyên trong hội thoại và vẫn được nạp làm ngữ cảnh cho
mọi lượt sau. File này quét lại kho bằng ĐÚNG bộ lọc ấy.

Hai mức xử lý, cố ý khác nhau:
  - Tin chỉ toàn câu bịa      -> XOÁ hẳn dòng đó.
  - Tin có câu bịa DÍNH vào lời thật -> chỉ cắt phần bịa, GIỮ nguyên lời người dùng nói.
Chỉ đụng tin của `role = 'user'`: lời trợ lý không đi qua Whisper.

Mặc định là xem trước. Có `--xoa` mới sửa, và trước khi sửa luôn chép DB ra file
`conversations.db.bak-aogiac-<thời điểm>` cạnh DB gốc.
"""
from __future__ import annotations

import shutil
import sqlite3
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "server"))

import sessions  # noqa: E402
import stt  # noqa: E402

CAT = 110   # cắt bớt khi in ra màn hình cho dễ đọc


def gon(s: str) -> str:
    s = " ".join(str(s or "").split())
    return s if len(s) <= CAT else s[:CAT - 1] + "…"


def main() -> int:
    sua = "--xoa" in sys.argv[1:]
    db = sessions.DB_PATH
    if not db.exists():
        print(f"Không thấy kho hội thoại: {db}")
        return 1

    con = sqlite3.connect(str(db))
    con.row_factory = sqlite3.Row
    rows = con.execute("SELECT id, session_id, content FROM messages WHERE role = 'user'").fetchall()

    xoa, cat = [], []
    for r in rows:
        goc = str(r["content"] or "")
        if not goc.strip():
            continue
        sach = stt.loc_ao_giac(goc)
        if sach == goc.strip():
            continue                      # không đụng gì
        (xoa if not sach else cat).append((r["id"], r["session_id"], goc, sach))

    print(f"Kho: {db}")
    print(f"Đã quét {len(rows)} tin của người dùng.")
    print(f"  Chỉ toàn câu bịa (sẽ XOÁ):      {len(xoa)}")
    print(f"  Câu bịa dính lời thật (sẽ CẮT): {len(cat)}")
    for mid, sid, goc, _ in xoa:
        print(f"  [xoá  #{mid} {sid[:8]}] {gon(goc)}")
    for mid, sid, goc, sach in cat:
        print(f"  [cắt  #{mid} {sid[:8]}] {gon(goc)}")
        print(f"        còn lại:            {gon(sach)}")

    if not xoa and not cat:
        print("\nKho sạch, không có gì để dọn.")
        return 0
    if not sua:
        print("\nMới chỉ XEM. Chạy lại kèm --xoa để sửa thật (DB sẽ được sao lưu trước).")
        return 0

    bak = db.with_name(db.name + f".bak-aogiac-{time.strftime('%Y%m%d-%H%M%S')}")
    shutil.copy2(db, bak)
    print(f"\nĐã sao lưu: {bak}")
    with con:
        for mid, _, _, _ in xoa:
            con.execute("DELETE FROM messages WHERE id = ?", (mid,))
        for mid, _, _, sach in cat:
            con.execute("UPDATE messages SET content = ? WHERE id = ?", (sach, mid))
    con.close()
    print(f"Xong: xoá {len(xoa)} tin, cắt {len(cat)} tin.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
