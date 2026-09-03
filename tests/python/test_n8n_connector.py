"""Connector n8n + khả năng URL ĐỘNG của catalog. Chạy tay / CI:

    python tests/python/test_n8n_connector.py

Không cần pytest, không chạm mạng.

Vì sao có file này: n8n là connector ĐẦU TIÊN mà địa chỉ server nằm trên tên miền của CHÍNH
người dùng (https://<n8n của bạn>/mcp-server/http), chứ không phải một địa chỉ dùng chung ghi
cứng trong catalog. Nên catalog có thêm `url_template` ghép từ ô đăng nhập. Hai thứ phải giữ:

  1. Ghép và chuẩn hoá địa chỉ cho đúng, và TỪ CHỐI đầu vào rác thay vì đẻ ra URL cụt.
  2. Phân loại quyền: execute_workflow CHẠY THẬT workflow (gửi mail, đăng bài, gọi API tính
     tiền) nên phải nằm nhóm NGUY HIỂM, không phải nhóm ghi thường. Xếp nhầm là mức Ghi nháp
     tự chạy được workflow của người dùng.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401  - nạp server/ vào sys.path
import json
import sys

import mcp_catalog as mc

loi = []


def check(ten, dieu_kien, them=""):
    print(("ok   " if dieu_kien else "FAIL ") + ten + (("  [" + str(them) + "]") if them and not dieu_kien else ""))
    if not dieu_kien:
        loi.append(ten)


con = mc.get("n8n")
check("catalog có connector n8n", bool(con))
if not con:
    print("\nFAIL - test_n8n_connector: thiếu hẳn connector")
    sys.exit(1)

# ---- 1. Khai báo cơ bản ----
check("transport http", con.get("transport") == "http")
check("có url_template thay vì url ghi cứng",
      con.get("url_template") == "{base_url}/mcp-server/http" and not con.get("url"))
check("mặc định CHỈ ĐỌC", con.get("default_perm") == "readonly")
check("có cảnh báo rủi ro", bool((con.get("risk") or "").strip()))
check("rủi ro nói rõ chuyện CHẠY workflow không hoàn tác được",
      "CHẠY" in con.get("risk", "") and "hoàn tác" in con.get("risk", ""))

fields = {f["key"]: f for f in ((con.get("auth") or {}).get("fields") or [])}
check("có ô địa chỉ instance", "base_url" in fields)
check("ô địa chỉ được đánh dấu url_base", bool(fields.get("base_url", {}).get("url_base")))
check("có ô token", "mcp_token" in fields)
# n8n dùng Bearer chuẩn; sai tên header là 401 mà không rõ vì sao.
check("token đi bằng header Authorization: Bearer",
      fields.get("mcp_token", {}).get("header") == "Authorization: Bearer {mcp_token}")
check("ô địa chỉ KHÔNG bị nhét thành header",
      "header" not in fields.get("base_url", {}))

# ---- 2. Ghép URL + chuẩn hoá ----
def url(raw):
    return mc.build_url(con, {"base_url": raw, "mcp_token": "tok"})


TOT = [
    ("https://cty.app.n8n.cloud", "https://cty.app.n8n.cloud/mcp-server/http"),
    # Người dùng hay quên scheme, thừa gạch chéo, hoặc dán nguyên URL đang mở trên trình duyệt.
    ("cty.app.n8n.cloud", "https://cty.app.n8n.cloud/mcp-server/http"),
    ("https://cty.app.n8n.cloud/", "https://cty.app.n8n.cloud/mcp-server/http"),
    ("https://cty.app.n8n.cloud/home/workflows?x=1", "https://cty.app.n8n.cloud/mcp-server/http"),
    ("  https://cty.app.n8n.cloud  ", "https://cty.app.n8n.cloud/mcp-server/http"),
    ("HTTPS://Cty.App.N8N.Cloud", "https://cty.app.n8n.cloud/mcp-server/http"),
    # n8n tự dựng trong mạng nội bộ: giữ nguyên http và cổng, đừng ép lên https.
    ("http://192.168.1.9:5678", "http://192.168.1.9:5678/mcp-server/http"),
    ("http://localhost:5678/", "http://localhost:5678/mcp-server/http"),
]
for raw, mong in TOT:
    check("địa chỉ " + repr(raw) + " -> đúng", url(raw) == mong, url(raw))

# Đầu vào không dùng được thì trả rỗng để caller rơi về url tĩnh / báo thiếu, TUYỆT ĐỐI không
# đẻ ra URL nửa vời rồi để người dùng ngồi đoán vì sao Test đỏ.
RAC = ["", "   ", "không phải url", "ftp://a.b", "javascript:alert(1)", "https://a.b/x y", "https:///"]
for raw in RAC:
    check("CANARY: đầu vào rác " + repr(raw) + " -> rỗng", url(raw) == "", url(raw))

check("CANARY: thiếu hẳn ô địa chỉ -> rỗng, không ra URL cụt",
      mc.build_url(con, {"mcp_token": "tok"}) == "",
      mc.build_url(con, {"mcp_token": "tok"}))
# Connector thường (không khai template) phải không bị ảnh hưởng gì.
check("connector url tĩnh không dính url_template",
      mc.build_url(mc.get("systeme-io"), {"mcp_key": "k"}) == "")

check("header dựng đúng từ token",
      mc.build_headers(con, {"base_url": "https://a.b", "mcp_token": "TOK"})
      == {"Authorization": "Bearer TOK"})

# ---- 3. Phân loại quyền ----
LOAI = {
    "search_workflows": "read", "get_workflow": "read", "list_tags": "read",
    "get_execution": "read", "search_executions": "read", "list_credentials": "read",
    "create_workflow": "write", "update_workflow": "write",
    "execute_workflow": "danger", "delete_workflow": "danger",
    "activate_workflow": "danger", "deactivate_workflow": "danger",
}
for tool, mong in LOAI.items():
    got = mc.classify(con, tool)
    check("phân loại " + tool + " -> " + mong, got == mong, got)

# Đây là luật an toàn quan trọng nhất của connector này.
check("CANARY: mức Ghi nháp KHÔNG được tự chạy workflow",
      not mc.allowed(con, "safe", "full", "execute_workflow")[0])
check("mức Ghi nháp vẫn tạo/sửa được workflow",
      mc.allowed(con, "safe", "full", "create_workflow")[0]
      and mc.allowed(con, "safe", "full", "update_workflow")[0])
check("mức Chỉ đọc chặn cả tạo workflow",
      not mc.allowed(con, "readonly", "full", "create_workflow")[0])
check("mức Chỉ đọc vẫn xem được workflow",
      mc.allowed(con, "readonly", "full", "search_workflows")[0])
check("mức Toàn quyền mới chạy được workflow",
      mc.allowed(con, "full", "full", "execute_workflow")[0])
# Loop nền ở chế độ gợi ý phải bị ép về chỉ đọc dù kết nối để Toàn quyền.
check("CANARY: loop chế độ suggest không chạy được workflow dù kết nối Toàn quyền",
      not mc.allowed(con, "full", "suggest", "execute_workflow")[0])

# ---- 4. Hướng dẫn đủ dùng ----
auth = con.get("auth") or {}
check("có hướng dẫn từng bước", len(auth.get("steps") or []) >= 3)
check("hướng dẫn nhắc chuyện token chỉ copy được MỘT LẦN",
      "copy" in (auth.get("guide") or "").lower()
      and any("che" in (s.get("text") or "") for s in (auth.get("steps") or [])))
check("có link tài liệu n8n", "docs.n8n.io" in (auth.get("guide_url") or ""))

# ---- 5. Logo tồn tại thật (icon trỏ /static/... = thư mục dashboard/) ----
icon = con.get("icon") or ""
if icon.startswith("/static/"):
    p = ROOT / "dashboard" / icon[len("/static/"):]
    check("file logo có thật: " + icon, p.exists(), str(p))

# ---- 6. Không phá catalog ----
data = json.loads((ROOT / "system" / "mcp-catalog.json").read_text(encoding="utf-8"))
ids = [c.get("id") for c in data.get("connectors", [])]
check("id không trùng nhau", len(ids) == len(set(ids)))
check("n8n nằm trong catalog", "n8n" in ids)

# ---- 7. Đường thật: thêm kết nối -> resolved() ra đúng URL + header ----
# Đây là chỗ dễ hỏng nhất khi refactor: URL phải dựng lại ở resolved() chứ không chỉ lúc thêm,
# nếu không thì user sửa địa chỉ n8n xong kết nối vẫn trỏ về địa chỉ cũ.
import os
import tempfile
from pathlib import Path

with tempfile.TemporaryDirectory() as tmp:
    os.environ["JAVIS_STATE_DIR"] = tmp
    # PHẢI nạp lại `config` nữa, không chỉ hai module dưới. `config.STATE_DIR` được tính MỘT
    # LẦN lúc import, và `mcp_store` lấy nó bằng `from config import STATE_DIR` - nên bỏ sót
    # `config` ở đây thì đổi biến môi trường không có tác dụng gì, và test ghi thẳng vào kho
    # kết nối THẬT của người đang chạy. Đã xảy ra: máy chủ repo tích được 7 kết nối rác tên
    # "n8n thử" và "Shop thử" sau nhiều lượt chạy, và lượt sau lấy nhầm hàng của lượt trước
    # nên test đỏ oan.
    # Hai bước, thiếu bước nào thì test ghi thẳng vào kho kết nối THẬT của người đang chạy.
    #
    # (1) Nạp lại `config` nữa, không chỉ hai module dưới: `config.STATE_DIR` tính MỘT LẦN lúc
    #     import, và `mcp_store` lấy nó bằng `from config import STATE_DIR`.
    # (2) Tạo sẵn một file store RỖNG trong thư mục tạm. `mcp_store._load` (dòng 60) có đường
    #     lui về `_LEGACY_STORE` = `server/mcp_servers.json` khi file ở STATE_DIR chưa tồn tại,
    #     nên một thư mục tạm trống vẫn rơi đúng vào kho thật.
    #
    # Đã xảy ra thật: máy chủ repo tích được 7 kết nối rác tên "n8n thử" và "Shop thử" sau
    # nhiều lượt chạy, rồi lượt sau lấy nhầm hàng của lượt trước nên test đỏ oan.
    (Path(tmp) / "mcp_servers.json").write_text('{"version": 2, "connections": []}',
                                                encoding="utf-8")
    for mod in ("mcp_store", "secrets_store", "config"):
        sys.modules.pop(mod, None)
    import config as _cfg_moi
    assert str(_cfg_moi.STATE_DIR) == tmp, "STATE_DIR chưa trỏ vào thư mục tạm"
    import mcp_store
    assert not mcp_store.list_connections(), "kho tạm phải rỗng - đang đọc nhầm kho thật"

    cid, err = mcp_store.add_connection("n8n", {
        "fields": {"base_url": "cty.app.n8n.cloud/home/workflows", "mcp_token": "TOK123"},
        "label": "n8n thử"})
    check("thêm được kết nối n8n", not err, err)
    if not err:
        r = [x for x in mcp_store.resolved(enabled_only=False) if x["connector_id"] == "n8n"][0]
        check("resolved: URL ghép đúng từ ô địa chỉ",
              r["url"] == "https://cty.app.n8n.cloud/mcp-server/http", r["url"])
        check("resolved: header Bearer đúng token",
              r["headers"] == {"Authorization": "Bearer TOK123"}, r["headers"])
        check("resolved: mặc định mức Chỉ đọc", r["perm"] == "readonly", r["perm"])

        mcp_store.update_connection(cid, {"fields": {"base_url": "https://moi.n8n.cloud",
                                                     "mcp_token": "TOK456"}})
        r2 = [x for x in mcp_store.resolved(enabled_only=False) if x["connector_id"] == "n8n"][0]
        check("CANARY: user sửa địa chỉ thì URL đi theo, không kẹt địa chỉ cũ",
              r2["url"] == "https://moi.n8n.cloud/mcp-server/http", r2["url"])
        check("user đổi token thì header đi theo",
              r2["headers"] == {"Authorization": "Bearer TOK456"}, r2["headers"])

if loi:
    print("\nFAIL - test_n8n_connector: %d lỗi: %s" % (len(loi), ", ".join(loi)))
    sys.exit(1)
print("\nOK - test_n8n_connector: tất cả pass")
