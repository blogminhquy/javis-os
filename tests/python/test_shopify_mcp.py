"""Connector Shopify (MCP chuẩn UCP) + cơ chế `inject_args` của catalog. Chạy tay / CI:

    python tests/python/test_shopify_mcp.py

Không cần pytest, không chạm mạng.

Vì sao có file này: Shopify là connector ĐẦU TIÊN mà giao thức bắt MỖI lời gọi tool phải kèm
một khối kỹ thuật cố định - `meta["ucp-agent"].profile`, URL hồ sơ agent để cửa hàng tải về
mà thoả thuận năng lực. Thiếu khối đó là 400 ở MỌI tool, mà model thì không có cách nào tự
biết điền gì. Nên catalog có thêm `inject_args` và tầng client tự ghép vào. Bốn thứ phải giữ:

  1. Khối meta được chèn vào MỌI lời gọi, ở `pool.call_tool` - chốt DUY NHẤT mọi đường đi qua
     (hub, nút Test, meta-tool `run` của lớp lazy). Đặt nhầm ở `_guard` thôi là nút Test đi
     đường vòng rồi báo đỏ trong khi kết nối vẫn tốt.
  2. Model đưa gì thì giữ nguyên cái đó - chèn XUỐNG DƯỚI, không đè. `cancel_cart` cần
     `meta["idempotency-key"]` của riêng nó, đè mất là huỷ giỏ hàng sai.
  3. Connector KHÔNG khai `inject_args` phải không bị đụng tới một chữ nào.
  4. Phân quyền: dựng giỏ hàng là GHI (chạm shop thật), huỷ giỏ là NGUY HIỂM. Mức Chỉ đọc
     mặc định chỉ tra cứu.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401  - nạp server/ vào sys.path
import asyncio
import json
import os
import sys
import tempfile

import mcp_catalog as mc

loi = []


def check(ten, dieu_kien, them=""):
    print(("ok   " if dieu_kien else "FAIL ") + ten + (("  [" + str(them) + "]") if them and not dieu_kien else ""))
    if not dieu_kien:
        loi.append(ten)


con = mc.get("shopify")
check("catalog có connector shopify", bool(con))
if not con:
    print("\nFAIL - test_shopify_mcp: thiếu hẳn connector")
    sys.exit(1)

# ---- 1. Khai báo cơ bản ----
check("transport http", con.get("transport") == "http")
check("dùng url_template (mỗi shop một tên miền), không url ghi cứng",
      con.get("url_template") == "{shop_domain}/api/ucp/mcp" and not con.get("url"))
# Endpoint UCP là cái DUY NHẤT sống qua 31/08/2026; /api/mcp cũ là bản đã bị khai tử.
check("CANARY: trỏ endpoint UCP /api/ucp/mcp, KHÔNG phải /api/mcp cũ",
      "/api/ucp/mcp" in (con.get("url_template") or ""))
check("mặc định CHỈ ĐỌC", con.get("default_perm") == "readonly")
check("không đòi thông tin đăng nhập (endpoint công khai)",
      (con.get("auth") or {}).get("type") == "none")
check("có cảnh báo rủi ro", bool((con.get("risk") or "").strip()))
check("rủi ro nói rõ giỏ hàng CHƯA phải đơn và Javis không tự thanh toán được",
      "CHƯA phải đơn hàng" in con.get("risk", "") and "thanh toán" in con.get("risk", ""))

fields = {f["key"]: f for f in ((con.get("auth") or {}).get("fields") or [])}
check("có ô địa chỉ cửa hàng", "shop_domain" in fields)
check("ô địa chỉ được đánh dấu url_base", bool(fields.get("shop_domain", {}).get("url_base")))
check("có ô hồ sơ agent UCP", "agent_profile" in fields)
check("ô hồ sơ agent là TUỲ CHỌN (người thường không biết điền gì)",
      bool(fields.get("agent_profile", {}).get("optional")))
check("ô hồ sơ agent có sẵn giá trị mặc định",
      bool(fields.get("agent_profile", {}).get("default")))
check("KHÔNG ô nào bị nhét thành header (endpoint không cần xác thực)",
      not any(f.get("header") for f in fields.values()))
check("mọi ô đều lộ ra UI kèm default",
      all("default" in f for f in
          next(c for c in mc.public_catalog() if c["id"] == "shopify")["fields"]))

# ---- 2. Ghép URL + chuẩn hoá ----
def url(raw):
    return mc.build_url(con, {"shop_domain": raw})


TOT = [
    ("cua-hang.myshopify.com", "https://cua-hang.myshopify.com/api/ucp/mcp"),
    ("https://cua-hang.myshopify.com", "https://cua-hang.myshopify.com/api/ucp/mcp"),
    ("https://cua-hang.myshopify.com/", "https://cua-hang.myshopify.com/api/ucp/mcp"),
    # Người ta hay dán nguyên URL trang sản phẩm đang mở trên trình duyệt.
    ("https://shop-cua-ban.com/products/ao-thun?variant=42", "https://shop-cua-ban.com/api/ucp/mcp"),
    ("  cua-hang.myshopify.com  ", "https://cua-hang.myshopify.com/api/ucp/mcp"),
    ("HTTPS://Cua-Hang.MyShopify.Com", "https://cua-hang.myshopify.com/api/ucp/mcp"),
]
for raw, mong in TOT:
    check("địa chỉ " + repr(raw) + " -> đúng", url(raw) == mong, url(raw))

RAC = ["", "   ", "không phải url", "ftp://a.b", "javascript:alert(1)", "https://a.b/x y"]
for raw in RAC:
    check("CANARY: đầu vào rác " + repr(raw) + " -> rỗng", url(raw) == "", url(raw))

# ---- 3. inject_args: dựng khối meta bắt buộc ----
MAC_DINH = fields["agent_profile"]["default"]
check("ô trống -> rơi về hồ sơ mặc định của Javis",
      mc.build_inject_args(con, {}) == {"meta": {"ucp-agent": {"profile": MAC_DINH}}},
      mc.build_inject_args(con, {}))
check("user tự trỏ hồ sơ riêng -> đi theo user",
      mc.build_inject_args(con, {"agent_profile": "https://toi.com/p.json"})
      == {"meta": {"ucp-agent": {"profile": "https://toi.com/p.json"}}})
# Khai được nhưng KHÔNG có nguồn thì bỏ hẳn nhánh, đừng gửi "{agent_profile}" thô cho Shopify.
gia = {"id": "x", "auth": {"fields": [{"key": "k"}]},
       "inject_args": {"meta": {"a": "{k}"}, "giu": "hang so"}}
check("CANARY: placeholder không có nguồn -> bỏ nhánh, không gửi chuỗi thô",
      mc.build_inject_args(gia, {}) == {"giu": "hang so"}, mc.build_inject_args(gia, {}))
check("CANARY: connector không khai inject_args -> rỗng, không đụng gì",
      mc.build_inject_args(mc.get("pancake-pos"), {"api_key": "k"}) == {})

# ---- 4. merge: model LUÔN thắng ----
inj = mc.build_inject_args(con, {})
check("tham số model giữ nguyên, meta được thêm vào",
      mc.merge_inject_args({"catalog": {"query": "giày"}}, inj)
      == {"catalog": {"query": "giày"}, "meta": {"ucp-agent": {"profile": MAC_DINH}}})
# cancel_cart tự đặt meta["idempotency-key"]; ghép NÔNG là nuốt mất ucp-agent hoặc nuốt key.
check("CANARY: deep-merge - idempotency-key của model sống chung với ucp-agent",
      mc.merge_inject_args({"meta": {"idempotency-key": "abc"}}, inj)
      == {"meta": {"idempotency-key": "abc", "ucp-agent": {"profile": MAC_DINH}}},
      mc.merge_inject_args({"meta": {"idempotency-key": "abc"}}, inj))
check("CANARY: model tự đặt profile thì KHÔNG bị đè",
      mc.merge_inject_args({"meta": {"ucp-agent": {"profile": "CUA-MODEL"}}}, inj)
      == {"meta": {"ucp-agent": {"profile": "CUA-MODEL"}}})
check("inject rỗng -> trả nguyên tham số model",
      mc.merge_inject_args({"a": 1}, {}) == {"a": 1})

# ---- 5. Phân loại quyền ----
LOAI = {
    "search_catalog": "read", "lookup_catalog": "read", "get_product": "read", "get_cart": "read",
    "create_cart": "write", "update_cart": "write",
    "cancel_cart": "danger",
}
for tool, mong in LOAI.items():
    got = mc.classify(con, tool)
    check("phân loại " + tool + " -> " + mong, got == mong, got)

check("mức Chỉ đọc vẫn tra cứu được sản phẩm", mc.allowed(con, "readonly", "full", "search_catalog")[0])
check("CANARY: mức Chỉ đọc KHÔNG dựng được giỏ hàng trên shop thật",
      not mc.allowed(con, "readonly", "full", "create_cart")[0])
check("mức Ghi nháp dựng được giỏ hàng", mc.allowed(con, "safe", "full", "create_cart")[0])
check("CANARY: mức Ghi nháp KHÔNG huỷ được giỏ hàng",
      not mc.allowed(con, "safe", "full", "cancel_cart")[0])
check("mức Toàn quyền mới huỷ được giỏ", mc.allowed(con, "full", "full", "cancel_cart")[0])
check("CANARY: loop chế độ suggest không dựng giỏ dù kết nối Toàn quyền",
      not mc.allowed(con, "full", "suggest", "create_cart")[0])
# Javis KHÔNG khai năng lực thanh toán, nhưng nếu Shopify có ngày trả về tool checkout thì
# nó phải rơi thẳng vào nhóm nguy hiểm chứ không được coi là ghi thường.
for t in ("complete_checkout", "submit_payment", "create_order"):
    check("CANARY: tool tiêu tiền '" + t + "' bị xếp NGUY HIỂM", mc.classify(con, t) == "danger",
          mc.classify(con, t))

# ---- 6. Hồ sơ agent UCP có thật + khớp URL mặc định ----
prof = ROOT / "system" / "ucp-agent-profile.json"
check("file hồ sơ agent có thật trong repo", prof.exists(), str(prof))
if prof.exists():
    pj = json.loads(prof.read_text(encoding="utf-8"))
    check("hồ sơ khai phiên bản UCP", bool((pj.get("ucp") or {}).get("version")))
    ten_nl = [c.get("name") for c in (pj.get("capabilities") or [])]
    check("hồ sơ khai năng lực catalog + cart", "dev.ucp.shopping.catalog" in ten_nl
          and "dev.ucp.shopping.cart" in ten_nl, ten_nl)
    # Javis dừng ở giỏ hàng rồi đưa link cho người thật bấm - khai checkout là tự nhận
    # quyền thanh toán mà app không hề có đường đi tới.
    check("CANARY: hồ sơ KHÔNG khai năng lực thanh toán",
          not any("checkout" in str(n) for n in ten_nl), ten_nl)
# URL mặc định phải trỏ đúng file này; đổi tên file mà quên sửa URL là connector chết câm.
check("CANARY: URL hồ sơ mặc định trỏ đúng system/ucp-agent-profile.json",
      MAC_DINH.startswith("https://") and MAC_DINH.endswith("/system/ucp-agent-profile.json"),
      MAC_DINH)

# ---- 7. Logo + không phá catalog ----
icon = con.get("icon") or ""
if icon.startswith("/static/"):
    p = ROOT / "dashboard" / icon[len("/static/"):]
    check("file logo có thật: " + icon, p.exists(), str(p))
data = json.loads((ROOT / "system" / "mcp-catalog.json").read_text(encoding="utf-8"))
ids = [c.get("id") for c in data.get("connectors", [])]
check("id không trùng nhau", len(ids) == len(set(ids)))
check("shopify nằm trong catalog", "shopify" in ids)

# ---- 8. Đường thật: thêm kết nối -> resolved() ra đúng URL + inject_args ----
with tempfile.TemporaryDirectory() as tmp:
    os.environ["JAVIS_STATE_DIR"] = tmp
    for mod in ("mcp_store", "secrets_store"):
        sys.modules.pop(mod, None)
    import mcp_store

    cid, err = mcp_store.add_connection("shopify", {
        "fields": {"shop_domain": "cua-hang.myshopify.com/products/x"}, "label": "Shop thử"})
    check("thêm được kết nối shopify", not err, err)
    if not err:
        r = [x for x in mcp_store.resolved(enabled_only=False) if x["connector_id"] == "shopify"][0]
        check("resolved: URL ghép đúng từ ô địa chỉ",
              r["url"] == "https://cua-hang.myshopify.com/api/ucp/mcp", r["url"])
        check("resolved: không sinh header nào", r["headers"] == {}, r["headers"])
        check("resolved: mặc định mức Chỉ đọc", r["perm"] == "readonly", r["perm"])
        check("resolved: mang sẵn khối meta bắt buộc",
              r["inject_args"] == {"meta": {"ucp-agent": {"profile": MAC_DINH}}}, r["inject_args"])

        mcp_store.update_connection(cid, {"fields": {"shop_domain": "shop-khac.com",
                                                     "agent_profile": "https://toi.com/p.json"}})
        r2 = [x for x in mcp_store.resolved(enabled_only=False) if x["connector_id"] == "shopify"][0]
        check("CANARY: user đổi địa chỉ shop thì URL đi theo, không kẹt shop cũ",
              r2["url"] == "https://shop-khac.com/api/ucp/mcp", r2["url"])
        check("CANARY: user đổi hồ sơ agent thì meta đi theo, không kẹt hồ sơ cũ",
              r2["inject_args"] == {"meta": {"ucp-agent": {"profile": "https://toi.com/p.json"}}},
              r2["inject_args"])

    # ---- 9. Chốt thật: pool.call_tool có ghép meta vào không ----
    import mcp_client

    class PhienGia:
        def __init__(self):
            self.nhan = None

        async def call_tool(self, tool, arguments):
            self.nhan = (tool, arguments)
            return "ok"

    phien = PhienGia()

    # `**kw` chứ không liệt kê tay: `_retry` thật còn nhận `ban=` (cờ "phiên đang chạy tool",
    # thêm ở 0.52.8). Stub thiếu tham số là `call_tool` nuốt TypeError thành chuỗi ERROR, rồi
    # test đỏ ở một chỗ chẳng liên quan gì tới Shopify.
    async def _retry_gia(spec, fn, idempotent=False, **kw):
        return await fn(phien)

    that = mcp_client.pool._retry
    mcp_client.pool._retry = _retry_gia
    try:
        spec = mcp_client._conn_spec(r)
        check("_conn_spec mang theo inject_args",
              spec.get("inject_args") == {"meta": {"ucp-agent": {"profile": MAC_DINH}}},
              spec.get("inject_args"))

        asyncio.run(mcp_client.pool.call_tool(spec, "search_catalog", {"catalog": {"query": "giày"}}))
        tool, got = phien.nhan
        check("CANARY: pool.call_tool CHÈN meta vào lời gọi thật",
              got == {"catalog": {"query": "giày"},
                      "meta": {"ucp-agent": {"profile": MAC_DINH}}}, got)

        # Nút Test và lớp lazy cũng đi qua đây - gọi không tham số vẫn phải có meta.
        asyncio.run(mcp_client.pool.call_tool(spec, "search_catalog", {}))
        check("CANARY: gọi không tham số vẫn kèm meta (nút Test đi đúng đường này)",
              phien.nhan[1] == {"meta": {"ucp-agent": {"profile": MAC_DINH}}}, phien.nhan[1])

        asyncio.run(mcp_client.pool.call_tool(
            spec, "cancel_cart", {"id": "c1", "meta": {"idempotency-key": "u-1"}}))
        check("CANARY: idempotency-key của model sống sót qua lớp chèn",
              phien.nhan[1] == {"id": "c1", "meta": {"idempotency-key": "u-1",
                                                     "ucp-agent": {"profile": MAC_DINH}}},
              phien.nhan[1])

        # Connector cũ (Pancake) không được đụng tới một chữ nào.
        spec_cu = {"key": "k", "transport": "http", "url": "https://a.b"}
        asyncio.run(mcp_client.pool.call_tool(spec_cu, "pos_shop", {"action": "list"}))
        check("CANARY: connector không khai inject_args -> tham số nguyên xi",
              phien.nhan[1] == {"action": "list"}, phien.nhan[1])
    finally:
        mcp_client.pool._retry = that

if loi:
    print("\nFAIL - test_shopify_mcp: %d lỗi: %s" % (len(loi), ", ".join(loi)))
    sys.exit(1)
print("\nOK - test_shopify_mcp: tất cả pass")
