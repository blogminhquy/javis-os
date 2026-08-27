"""Connector Hostinger (MCP chính chủ hostinger-api-mcp). Chạy tay / CI:

    python tests/python/test_hostinger_connector.py

Không cần pytest, không chạm mạng.

Vì sao có file này: Hostinger là chìa khoá vào HẠ TẦNG website của người dùng - tên miền, DNS,
VPS, hộp thư, hoá đơn. Server bày hơn 330 tool và tên tool của nó KHÔNG theo lối `verb_doi_tuong`
quen thuộc mà là `mang_verbDoiTuongV1` (vd `DNS_deleteDNSRecordsV1`), nên heuristic tên tool mặc
định của hub phân loại sai rất dễ. Xếp nhầm một tool xoá/tiêu tiền xuống nhóm ghi thường là mức
Ghi nháp tự xoá được website hoặc tự mua tên miền. Ba thứ phải giữ:

  1. Token đi bằng ENV `HOSTINGER_API_TOKEN` (server đang khai tử alias `API_TOKEN`), không phải
     header - đây là connector stdio.
  2. Phân loại quyền đúng cho cả ba nhóm, đặc biệt: xoá, dừng/khởi động lại VPS, khôi phục sao
     lưu, và MUA/GIA HẠN (tiêu tiền thật) đều phải là NGUY HIỂM.
  3. Mặc định Chỉ đọc + có cảnh báo rủi ro nói thẳng chuyện tiêu tiền và không hoàn tác được.
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


con = mc.get("hostinger")
check("catalog có connector hostinger", bool(con))
if not con:
    print("\nFAIL - test_hostinger_connector: thiếu hẳn connector")
    sys.exit(1)

# ---- 1. Khai báo cơ bản ----
check("chạy bằng stdio", con.get("transport") == "stdio")
check("gọi đúng package chính chủ trên npm",
      con.get("command") == "npx" and "hostinger-api-mcp" in (con.get("args") or []),
      str(con.get("command")) + " " + str(con.get("args")))
check("mặc định CHỈ ĐỌC", con.get("default_perm") == "readonly")
check("có cảnh báo rủi ro", bool((con.get("risk") or "").strip()))
risk = con.get("risk", "")
check("rủi ro nói thẳng chuyện TIÊU TIỀN và không hoàn tác được",
      "tiền" in risk.lower() and "hoàn tác" in risk)

# ---- 2. Đăng nhập bằng env, không phải header ----
fields = {f["key"]: f for f in ((con.get("auth") or {}).get("fields") or [])}
check("có đúng ô token", list(fields) == ["api_token"], list(fields))
check("token map vào env HOSTINGER_API_TOKEN",
      fields.get("api_token", {}).get("env") == "HOSTINGER_API_TOKEN",
      fields.get("api_token", {}).get("env"))
check("CANARY: token KHÔNG bị nhét thành header (stdio không có header)",
      "header" not in fields.get("api_token", {}))
check("build_env dựng đúng biến môi trường",
      mc.build_env(con, {"api_token": "TOK123"}) == {"HOSTINGER_API_TOKEN": "TOK123"},
      mc.build_env(con, {"api_token": "TOK123"}))
check("chưa dán token thì không đẻ ra env rỗng",
      mc.build_env(con, {}) == {}, mc.build_env(con, {}))
check("không dựng header nào", mc.build_headers(con, {"api_token": "TOK123"}) == {})

# ---- 3. Phân loại quyền theo tên tool THẬT của Hostinger ----
# Tên lấy từ hostinger-api-mcp 1.50.0 (src/core/tools/all.js).
LOAI = {
    # đọc
    "domains_getDomainListV1": "read",
    "domains_getDomainDetailsV1": "read",
    "DNS_getDNSRecordsV1": "read",
    "VPS_getVirtualMachineListV1": "read",
    "billing_getSubscriptionListV1": "read",
    "hosting_showMaintenanceStatusV1": "read",
    "domains_checkDomainAvailabilityV1": "read",
    "reach_countProfileSegmentContactsV1": "read",
    "hosting_searchWordPressPluginsV1": "read",
    # ghi thường
    "DNS_updateDNSRecordsV1": "write",
    "hosting_createWebsiteV1": "write",
    "mail_createMailboxV1": "write",
    "VPS_createSnapshotV1": "write",
    "hosting_deployWordpressPluginV1": "write",
    "VPS_setupPurchasedVirtualMachineV1": "write",
    "hosting_activateWordPressThemeV1": "write",
    "hosting_clearWebsiteCacheV1": "write",
    # Nhóm agency-hosting có DẤU GẠCH NGANG trong tiền tố tên tool. Mẫu nào chỉ khớp
    # [A-Za-z0-9_] là bỏ sót nguyên 38 tool này (đúng cái bẫy lúc dựng connector).
    "agency-hosting_listAgencyPlanWebsitesV1": "read",
    "agency-hosting_getWebsiteDetailsV1": "read",
    "agency-hosting_createANewWebsiteV1": "write",
    "agency-hosting_linkDomainToWebsiteV1": "write",
    "agency-hosting_buildWebsiteNodeJSAssetsV1": "write",
    # nguy hiểm: xoá, đụng vào máy đang chạy, và TIÊU TIỀN
    "DNS_deleteDNSRecordsV1": "danger",
    "hosting_deleteWebsiteV1": "danger",
    "DNS_resetDNSRecordsV1": "danger",
    "DNS_restoreDNSSnapshotV1": "danger",
    "VPS_stopVirtualMachineV1": "danger",
    "VPS_restartVirtualMachineV1": "danger",
    "VPS_purchaseNewVirtualMachineV1": "danger",
    "domains_purchaseNewDomainV1": "danger",
    "domains_claimFreeDomainV1": "danger",
    "billing_renewSubscriptionV1": "danger",
    "billing_createPurchaseOrderV1": "danger",
    "billing_disableAutoRenewalV1": "danger",
    "agency-hosting_deleteWebsiteV1": "danger",
    "agency-hosting_unlinkDomainFromWebsiteV1": "danger",
    "VPS_replaceAllFirewallRulesInGroupV1": "danger",
}
for tool, mong in LOAI.items():
    got = mc.classify(con, tool)
    check("phân loại " + tool + " -> " + mong, got == mong, got)

# Đây là luật an toàn quan trọng nhất của connector này.
check("CANARY: mức Ghi nháp KHÔNG xoá được bản ghi DNS",
      not mc.allowed(con, "safe", "full", "DNS_deleteDNSRecordsV1")[0])
check("CANARY: mức Ghi nháp KHÔNG mua được tên miền (tiêu tiền thật)",
      not mc.allowed(con, "safe", "full", "domains_purchaseNewDomainV1")[0])
check("CANARY: mức Ghi nháp KHÔNG dừng được VPS đang chạy",
      not mc.allowed(con, "safe", "full", "VPS_stopVirtualMachineV1")[0])
check("mức Ghi nháp vẫn sửa được DNS và tạo website",
      mc.allowed(con, "safe", "full", "DNS_updateDNSRecordsV1")[0]
      and mc.allowed(con, "safe", "full", "hosting_createWebsiteV1")[0])
check("mức Chỉ đọc chặn cả việc sửa DNS",
      not mc.allowed(con, "readonly", "full", "DNS_updateDNSRecordsV1")[0])
check("mức Chỉ đọc vẫn xem được tên miền và hoá đơn",
      mc.allowed(con, "readonly", "full", "domains_getDomainListV1")[0]
      and mc.allowed(con, "readonly", "full", "billing_getSubscriptionListV1")[0])
check("mức Toàn quyền mới xoá được website",
      mc.allowed(con, "full", "full", "hosting_deleteWebsiteV1")[0])
# Loop nền ở chế độ gợi ý phải bị ép về chỉ đọc dù kết nối để Toàn quyền.
check("CANARY: loop chế độ suggest không xoá được gì dù kết nối Toàn quyền",
      not mc.allowed(con, "full", "suggest", "hosting_deleteWebsiteV1")[0])
check("CANARY: mức Ghi nháp KHÔNG gỡ được tên miền khỏi website đang chạy",
      not mc.allowed(con, "safe", "full", "agency-hosting_unlinkDomainFromWebsiteV1")[0])
check("mức Ghi nháp vẫn xoá được cache website (việc lành)",
      mc.allowed(con, "safe", "full", "hosting_clearWebsiteCacheV1")[0])

# Không tool nào của Hostinger được rơi vào nhóm ĐỌC chỉ vì heuristic không nhận ra tên nó.
# Tên tool ở đây là `mang_verbDoiTuongV1`, mà bộ WRITE_HINTS mặc định dò theo từ rời nên
# `unlinkDomainFromWebsite` từng lọt thành "đọc" - tức mức Chỉ đọc gỡ được tên miền thật.
DONG_TU_DOC = ("get", "list", "show", "check", "count", "search",
               "preview", "suggest", "detect", "validate", "retrieve")
import re as _re


def _dong_tu(ten):
    than = ten.split("_", 1)[1] if "_" in ten else ten
    m = _re.match(r"[a-z]+", than)
    return m.group(0) if m else ""


lot_doc = [t for t in LOAI
           if mc.classify(con, t) == "read" and _dong_tu(t) not in DONG_TU_DOC]
check("CANARY: không tool hành động nào lọt xuống nhóm ĐỌC: " + (", ".join(lot_doc) or "đạt"),
      not lot_doc)

# ---- 4. Hướng dẫn đủ dùng ----
auth = con.get("auth") or {}
check("có hướng dẫn từng bước", len(auth.get("steps") or []) >= 3)
check("hướng dẫn nhắc token chỉ xem được MỘT LẦN",
      "copy" in (auth.get("guide") or "").lower()
      and any("không xem lại" in (s.get("text") or "") for s in (auth.get("steps") or [])))
check("có link tài liệu Hostinger", "hostinger.com/support" in (auth.get("guide_url") or ""))
check("bước tạo token trỏ thẳng vào trang API của hPanel",
      any("hpanel.hostinger.com/profile/api" in (s.get("link") or "")
          for s in (auth.get("steps") or [])))

# ---- 5. Nút Kiểm tra dùng tool ĐỌC, không tham số ----
val = con.get("validate") or {}
check("validate gọi tool đọc danh sách tên miền",
      val.get("tool") == "domains_getDomainListV1", val.get("tool"))
check("validate không cần tham số", val.get("args") == {})
check("CANARY: tool validate phải là tool ĐỌC (chạy được ở mức Chỉ đọc)",
      mc.classify(con, val.get("tool", "")) == "read")

# ---- 6. Logo tồn tại thật (icon trỏ /static/... = thư mục dashboard/) ----
icon = con.get("icon") or ""
check("icon trỏ tới file logo riêng, không phải icon chung chung",
      icon.startswith("/static/logos/hostinger"), icon)
p = ROOT / "dashboard" / icon[len("/static/"):] if icon.startswith("/static/") else None
check("file logo có thật: " + icon, bool(p and p.exists()), str(p))
if p and p.exists() and p.suffix == ".svg":
    svg = p.read_text(encoding="utf-8")
    check("logo là SVG hợp lệ", svg.lstrip().startswith("<svg") and "</svg>" in svg)
    check("logo dùng màu thương hiệu Hostinger (tím #673DE6)", "673DE6" in svg.upper())

# ---- 7. Không phá catalog ----
data = json.loads((ROOT / "system" / "mcp-catalog.json").read_text(encoding="utf-8"))
ids = [c.get("id") for c in data.get("connectors", [])]
check("id không trùng nhau", len(ids) == len(set(ids)))
check("hostinger nằm trong catalog", "hostinger" in ids)
pub = [c for c in mc.public_catalog() if c["id"] == "hostinger"]
check("bản public_catalog vẽ được card", bool(pub) and pub[0]["name"] == "Hostinger")
check("public_catalog KHÔNG lộ khối validate nội bộ",
      bool(pub) and "validate" not in pub[0])

if loi:
    print("\nFAIL - test_hostinger_connector: %d lỗi: %s" % (len(loi), ", ".join(loi)))
    sys.exit(1)
print("\nOK - test_hostinger_connector: tất cả pass")
