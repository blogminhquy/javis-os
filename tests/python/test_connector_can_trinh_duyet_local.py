"""Connector cần trình duyệt trên máy chạy Javis không được để user domain public đâm ngõ cụt.

    python tests/run.py can_trinh_duyet_local

Issue #112: connector google-workspace chạy workspace-mcp, thư viện đó tự làm OAuth với
callback CỨNG http://localhost:8000/oauth2callback. Truy cập Javis qua domain public thì
Google chuyển trình duyệt của NGƯỜI DÙNG về localhost của họ - không có gì nghe ở đó,
ERR_CONNECTION_REFUSED, và không một dòng nào nói cho họ biết vì sao. Nay /connect/add
chặn kèm lời giải thích (khuôn can_force như POST /reminders), còn LAN/localhost thì cho
qua vì máy chạy Javis thường là desktop có màn hình.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import json
import sys

_fails = []


def check(name, cond, them=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(them) + "]") if them and not cond else ""))
    if not cond:
        _fails.append(name)


# ---- 1. Catalog khai cờ đúng chỗ ----
cat = json.load(open(ROOT / "system" / "mcp-catalog.json", encoding="utf-8"))
items = cat if isinstance(cat, list) else cat.get("connectors") or []
by_id = {c.get("id"): c for c in items if isinstance(c, dict)}
for cid in ("google-workspace", "google-tasks"):
    check(f"{cid} khai needs_local_browser (cùng chạy workspace-mcp, cùng callback localhost)",
          by_id.get(cid, {}).get("needs_local_browser") is True)

# ---- 2. host_kieu_local phân biệt đúng public/local ----
import web_security  # noqa: E402

for h, mong in [("localhost", True), ("127.0.0.1:7777", True), ("[::1]:7777", True),
                ("192.168.1.5:7777", True), ("10.0.0.2", True), ("mymac.local", True),
                ("javis.example.com", False), ("https://javis.phamquangdai.com", False),
                ("8.8.8.8:7777", False)]:
    check(f"host_kieu_local({h!r}) == {mong}", web_security.host_kieu_local(h) is mong)

# ---- 3. /connect/add chặn đúng ca, khuôn can_force ----
import main  # noqa: E402
import inspect

src = inspect.getsource(main.connect_add)
check("connect_add đọc cờ needs_local_browser từ catalog", "needs_local_browser" in src)
check("chặn theo host NHƯ NGƯỜI DÙNG THẤY (external_base, sau reverse proxy)",
      "external_base" in src and "x-forwarded-host" in src)
check("trả can_force (cùng khuôn POST /reminders), không chặn chết",
      '"can_force": True' in src)
check("force=true thì cho qua (ca desktop có màn hình truy cập qua LAN/tên miền)",
      'data.get("force")' in src)
check("lời chặn chỉ đường thay thế (thẻ Lịch/Gmail riêng cho VPS)",
      "Gmail riêng" in src)

# ---- 4. Frontend gửi force + đổi nút thành xác nhận ----
console = (ROOT / "dashboard" / "console.js").read_text(encoding="utf-8")
check("console.js gửi force khi user xác nhận lần hai", "force: !!m._forceAdd" in console)
check("console.js đổi nút thành lời xác nhận khi can_force",
      "Tôi hiểu, vẫn kết nối" in console)

print()
if _fails:
    print(f"{len(_fails)} test HỎNG: " + ", ".join(_fails))
    sys.exit(1)
print("Tất cả test can_trinh_duyet_local đã qua.")
