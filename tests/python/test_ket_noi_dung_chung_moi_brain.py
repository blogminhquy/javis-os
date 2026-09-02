"""Kết nối MCP là của CẢ Javis, dùng chung cho mọi brain - và model phải được nói vậy.

    python tests/run.py ket_noi_dung_chung_moi_brain      (KHÔNG mạng)

Vụ 02/09: ở brain "Ngọc Thu Phạm", Javis không thấy tool POS Làng Chài Xưa rồi kết luận
"nguồn có trong kho chung nhưng chưa được gắn vào brain này", còn bảo người dùng vào trang Kết
nối tìm mục "gắn nguồn có sẵn cho brain" - một mục không tồn tại. Nó còn ghi kết luận sai đó
vào bộ nhớ dài hạn, nên lần sau càng tin.

Sự thật trong code: hub dựng tool từ mcp_store.resolved() cho MỌI vault như nhau, không có
bộ lọc theo brain. Không thấy tool chỉ có hai lý do: nguồn đang tắt, hoặc nguồn hỏng lúc dò.
File này canh (1) kiến trúc vẫn không lọc theo brain, (2) javis_connections nói ra hai lý do
đó thay vì để model tự bịa lý do thứ ba.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import json
import os
import sys
import tempfile

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-mcpchung-"))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import mcp_hub  # noqa: E402
import mcp_store  # noqa: E402

_fails = []


def check(name, cond, them=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(them) + "]") if them and not cond else ""))
    if not cond:
        _fails.append(name)


# ---- 1. Kiến trúc: không có bộ lọc theo brain --------------------------------
_hub = (SERVER / "mcp_hub.py").read_text(encoding="utf-8")
_disc = _hub.split("async def discover_all(", 1)[1].split("\ndef registry_inventory(", 1)[0]
check("CANARY: hub lấy MỌI kết nối đang bật cho mọi vault (không lọc theo brain)",
      "mcp_store.resolved(enabled_only=True)" in _disc and "brain" not in _disc.split("conns = ")[1].split("\n")[0])
check("CANARY: kho kết nối không có cột brain",
      "brain" not in (SERVER / "mcp_store.py").read_text(encoding="utf-8").split("def add_connection", 1)[1].split("def update_connection", 1)[0])
check("CANARY: trang Kết nối không có mục 'gắn nguồn cho brain' (mục đó không tồn tại)",
      "gắn nguồn" not in (ROOT / "dashboard" / "console.js").read_text(encoding="utf-8"))

# ---- 2. javis_connections nói đúng bệnh ----------------------------------------
cid, err = mcp_store.add_connection("custom", {"label": "POS Thử", "url": "http://127.0.0.1:1/mcp"})
check("dựng được một kết nối thử", bool(cid), err)
ra = json.loads(mcp_hub._connections_json())
check("phần tử đầu là ghi chú cho model", "ghi_chu" in ra[0])
check("ghi chú nói kết nối dùng chung cho MỌI brain", "MỌI brain" in ra[0]["ghi_chu"])
check("và cấm nói 'gắn nguồn vào brain'", "gắn nguồn vào brain" in ra[0]["ghi_chu"])
rec = next(r for r in ra if r.get("label") == "POS Thử")
check("kết nối đang bật, chưa có lỗi thì không bị dán trạng thái xấu",
      rec.get("trang_thai") in (None, "ổn"), rec.get("trang_thai"))
# Nguồn không dò được: phải nói THẲNG là nguồn hỏng, kèm việc cần làm.
ra2 = json.loads(mcp_hub._connections_json(bo_qua={cid}))
rec2 = next(r for r in ra2 if r.get("label") == "POS Thử")
check("CANARY: nguồn dò hụt thì trạng thái nói nguồn đang hỏng, không phải chưa gắn brain",
      "KHÔNG DÒ ĐƯỢC" in rec2.get("trang_thai", "") and "Kết nối" in rec2.get("trang_thai", ""),
      rec2.get("trang_thai"))
mcp_store.toggle_connection(cid)
ra3 = json.loads(mcp_hub._connections_json())
rec3 = next(r for r in ra3 if r.get("label") == "POS Thử")
check("nguồn đang tắt thì nói đang tắt và bật lại là mọi brain dùng được",
      "ĐANG TẮT" in rec3.get("trang_thai", "") and "mọi brain" in rec3.get("trang_thai", ""))
check("mô tả tool javis_connections cũng nói dùng chung cho mọi brain",
      "DÙNG CHUNG cho mọi brain" in _hub)
check("danh sách nguồn dò hụt được đưa vào javis_connections",
      "_connections_json(include_ambient, hidden, bo_qua)" in _hub)

print()
if _fails:
    print(f"ĐỎ {len(_fails)} mục: " + "; ".join(_fails))
    raise SystemExit(1)
print("Tất cả xanh.")
