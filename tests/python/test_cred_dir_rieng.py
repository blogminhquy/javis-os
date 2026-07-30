"""Connector tự giữ token NGOÀI Javis phải có kho riêng, và xoá kết nối là xoá token theo.

    python tests/run.py cred_dir_rieng

Không cần pytest, không chạm mạng.

Bối cảnh (báo từ người dùng thật, 2026-07-30): "xoá đi cài lại rất nhiều lần" mà Lịch Google
vẫn báo thiếu quyền. Hoá ra người dùng đang đi qua connector `google-workspace`, chứ không phải
thẻ Lịch rời - mà connector đó chạy `workspace-mcp`, một server TỰ chạy luồng OAuth của nó và
cache token ra `~/.google_workspace_mcp/credentials`, nằm ngoài tầm với của Javis.

Hệ quả: xoá kết nối trong Javis không dọn gì cả. Thêm lại là tiến trình con đọc đúng file token
cũ, không mở lại màn đăng nhập, nên token cấp thiếu quyền thì thiếu vĩnh viễn - đúng vòng lặp
người dùng mắc kẹt. Kèm theo đó, mọi tài khoản dùng chung một kho nên hai connection giẫm nhau.

Cách chữa: mỗi connection một thư mục token riêng (env `WORKSPACE_MCP_CREDENTIALS_DIR`), xoá
kết nối thì xoá luôn thư mục đó, và có nút "Đăng nhập lại" vứt token mà giữ kết nối.
"""
from _paths import ROOT, SERVER, DASHBOARD  # noqa: E402,F401
import json
import sys

import mcp_catalog
import mcp_store

_fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)


catalog = json.loads((ROOT / "system" / "mcp-catalog.json").read_text(encoding="utf-8"))
by_id = {c["id"]: c for c in catalog["connectors"]}

# ---- 1. Mọi connector chạy workspace-mcp đều phải khai kho token riêng ----
chay_ws = [c for c in catalog["connectors"] if "workspace-mcp" in (c.get("args") or [])]
check("tìm được connector chạy workspace-mcp", len(chay_ws) >= 2)
thieu = [c["id"] for c in chay_ws
         if (c.get("cred_dir") or {}).get("env") != "WORKSPACE_MCP_CREDENTIALS_DIR"]
check("mọi connector workspace-mcp đều khai cred_dir: " + (", ".join(thieu) or "đạt"), not thieu)

# ---- 2. _cred_dir tách theo TỪNG connection, không dùng chung ----
c1 = {"id": "id1", "connector_id": "google-workspace", "slug": "acc-mot"}
c2 = {"id": "id2", "connector_id": "google-workspace", "slug": "acc-hai"}
d1, d2 = mcp_store._cred_dir(c1), mcp_store._cred_dir(c2)
check("connector có khai -> trả về đường dẫn", d1 is not None)
check("env đúng tên workspace-mcp đọc", (d1 or {}).get("env") == "WORKSPACE_MCP_CREDENTIALS_DIR")
check("hai tài khoản -> hai thư mục KHÁC nhau (không giẫm token của nhau)",
      d1 and d2 and d1["path"] != d2["path"])
check("thư mục nằm trong STATE_DIR của Javis, không phải home của user",
      d1 and "connector-cred" in str(d1["path"]))
check("CANARY: connector KHÔNG khai cred_dir thì trả None (không đẻ thư mục thừa)",
      mcp_store._cred_dir({"id": "x", "connector_id": "google-calendar", "slug": "s"}) is None)
check("CANARY: connector lạ cũng trả None",
      mcp_store._cred_dir({"id": "x", "connector_id": "khong-co-that", "slug": "s"}) is None)

# ---- 3. forget_cred_dir XOÁ THẬT thư mục đó ----
p = d1["path"]
p.mkdir(parents=True, exist_ok=True)
(p / "token.json").write_text("{}", encoding="utf-8")
check("dựng được thư mục token giả để thử", (p / "token.json").exists())
check("forget_cred_dir báo đã xoá", mcp_store.forget_cred_dir(c1) is True)
check("thư mục token BIẾN MẤT thật (lần sau server phải đăng nhập lại)", not p.exists())
check("gọi lại lần nữa không nổ, trả False", mcp_store.forget_cred_dir(c1) is False)
check("truyền None không nổ", mcp_store.forget_cred_dir(None) is False)
check("connection của connector không khai cred_dir -> False, không đụng gì",
      mcp_store.forget_cred_dir({"id": "x", "connector_id": "google-calendar", "slug": "s"}) is False)

# ---- 4. Xoá kết nối phải kéo theo token (đây chính là chỗ vòng lặp cũ gãy) ----
src = (SERVER / "mcp_store.py").read_text(encoding="utf-8")
than_delete = src.split("def delete_connection")[1].split("\ndef ")[0]
check("delete_connection có dọn kho token riêng", "forget_cred_dir" in than_delete)
check("resolved() có bơm env kho token xuống tiến trình con", "_cred_dir(c, con)" in src)

# ---- 5. Có đường "đăng nhập lại" mà KHÔNG phải xoá kết nối ----
main_src = (SERVER / "main.py").read_text(encoding="utf-8")
check("có endpoint /connect/relogin", '"/connect/relogin"' in main_src)
than_relogin = main_src.split('@app.post("/connect/relogin")')[1].split("@app.post")[0]
check("relogin gọi đúng hàm dọn token", "forget_cred_dir_by_id" in than_relogin)
check("relogin giết luôn session cũ đang giữ token trong RAM",
      "pool.invalidate" in than_relogin)
check("relogin KHÔNG xoá connection (chỉ vứt token)",
      "delete_connection" not in than_relogin)

# ---- 6. UI: nút chỉ hiện cho connector có kho token riêng ----
js = (DASHBOARD / "console.js").read_text(encoding="utf-8", errors="replace")
check("dashboard có nút Đăng nhập lại", 'data-m="relogin"' in js)
check("nút gắn cờ cred_dir nên nguồn khác không mọc nút thừa", "con.cred_dir ?" in js)
check("nút gọi đúng endpoint", '"/connect/relogin"' in js)
check("có hỏi xác nhận trước khi vứt token", 'act === "relogin"' in js and "confirm(" in js)

# ---- 7. Cờ cred_dir phải ra tới frontend, và chỉ là bool (không lộ tên biến môi trường) ----
pub = {c["id"]: c for c in mcp_catalog.public_catalog()}
check("public_catalog trả cờ cred_dir cho google-workspace",
      pub.get("google-workspace", {}).get("cred_dir") is True)
check("connector thường thì cờ tắt", pub.get("google-calendar", {}).get("cred_dir") is False)
check("cờ là bool, không phải dict (không lộ tên env ra frontend)",
      isinstance(pub.get("google-workspace", {}).get("cred_dir"), bool))

if _fails:
    print(f"\nFAIL - test_cred_dir_rieng: {len(_fails)} lỗi: {_fails}")
    sys.exit(1)
print("\nOK - test_cred_dir_rieng: tất cả pass")
