"""Hạ Resonance về 0.92.1 bằng snapshot lúc nâng lên 0.93.0 (A4, thiết kế mục 7.4, D11).

    python tools/resonance_restore_pre_a4.py --yes
    python tools/resonance_restore_pre_a4.py --state-dir /duong/dan/state --yes

CHẠY KHI JAVIS ĐÃ TẮT. Script làm đúng hai bước, đều bằng SQLite backup API (lấy cả phần còn trong WAL, không chép thô
file `.sqlite3`):
1. Chép kho HIỆN TẠI sang `resonance.sqlite3.post-0.93.0-<thời điểm>` để giữ hồ sơ sau nâng (lượt đã chạy, bản đã
   đăng, phản hồi, quyền đã cấp và thu hồi).
2. Ghi đè kho bằng snapshot `resonance.sqlite3.pre-0.93.0` mà mã 0.93.0 tạo một lần lúc nâng.

Hậu quả, cũng ghi trong ghi chú phát hành: mọi thay đổi của mục tiêu sau lúc nâng biến mất khỏi kho chạy (bản sao ở
bước 1 vẫn đọc được). File đã đăng trong brain vẫn còn, và 0.92.1 có thể thấy chúng là drift so với mốc cũ (A2).
Hạ về 0.92.1 mà KHÔNG khôi phục snapshot là không hỗ trợ: mã cũ không đọc bảng quyền, nên bấm Tiếp tục trên mục tiêu
đã thu hồi là chạy lại.
"""
from __future__ import annotations

import argparse
import os
import sqlite3
import sys
import time
from contextlib import closing
from pathlib import Path

SNAPSHOT_SUFFIX = ".pre-0.93.0"


def _backup(src: Path, dst: Path) -> None:
    with closing(sqlite3.connect(str(src), timeout=10)) as s, closing(sqlite3.connect(str(dst), timeout=10)) as d:
        s.backup(d)


def restore(state_dir: str) -> dict:
    """Khôi phục snapshot trước A4 vào kho của `state_dir`. Trả {ok, store, snapshot, kept, error}."""
    store = Path(state_dir) / "resonance.sqlite3"
    snap = store.with_name(store.name + SNAPSHOT_SUFFIX)
    if not snap.is_file():
        return {"ok": False, "error": f"không có snapshot {snap.name}: kho chưa từng được 0.93.0 nâng lên, không có gì "
                                      "để khôi phục"}
    kept = None
    if store.is_file():
        kept = store.with_name(f"{store.name}.post-0.93.0-{time.strftime('%Y%m%d-%H%M%S')}")
        _backup(store, kept)
    _backup(snap, store)
    with closing(sqlite3.connect(str(store), timeout=10)) as c:
        names = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        c.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    if "grants" in names:
        return {"ok": False, "store": str(store), "snapshot": str(snap), "kept": str(kept) if kept else "",
                "error": "snapshot vẫn có bảng A4; không phải bản trước 0.93.0"}
    return {"ok": True, "store": str(store), "snapshot": str(snap), "kept": str(kept) if kept else ""}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Khôi phục kho Resonance về snapshot trước 0.93.0 (chạy khi Javis đã tắt).")
    ap.add_argument("--state-dir", default=os.environ.get("JAVIS_STATE_DIR", ""),
                    help="thư mục state của Javis (mặc định JAVIS_STATE_DIR)")
    ap.add_argument("--yes", action="store_true", help="xác nhận Javis đã tắt và chấp nhận mất thay đổi sau lúc nâng")
    a = ap.parse_args(argv)
    if not a.state_dir:
        print("Thiếu --state-dir (hay biến JAVIS_STATE_DIR).", file=sys.stderr)
        return 2
    if not a.yes:
        print("Tắt Javis trước, rồi chạy lại với --yes. Mọi thay đổi của mục tiêu sau lúc nâng lên 0.93.0 sẽ không còn "
              "trong kho chạy; bản sao kho hiện tại được giữ cạnh file kho.", file=sys.stderr)
        return 2
    res = restore(a.state_dir)
    if not res["ok"]:
        print("Không khôi phục được: " + res["error"], file=sys.stderr)
        return 1
    print(f"Đã khôi phục {res['store']} từ {res['snapshot']}." +
          (f" Kho trước khi khôi phục giữ ở {res['kept']}." if res["kept"] else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
