"""Token OAuth thiếu PHẠM VI QUYỀN phải bị bắt tại chỗ, không để người dùng tự đoán.

    python tests/run.py scope_google

Không cần pytest, không chạm mạng.

Bối cảnh (báo từ người dùng thật, 2026-07-30): đấu Google Calendar xong, hỏi "tạo lịch sáng
mai 9h" trên bộ não ChatGPT thì Google trả ACCESS_TOKEN_SCOPE_INSUFFICIENT ở bước kiểm tra
rảnh bận. Xoá kết nối cài lại chục lần vẫn y nguyên - vì chỗ sai không nằm ở lần cài, mà ở
DANH SÁCH SCOPE Javis xin: server MCP Lịch của Google đòi các scope hạt nhỏ
(calendar.calendarlist.readonly, calendar.events.readonly, calendar.events.freebusy) chứ
không nhận mỗi scope gộp 'auth/calendar'. Thiếu freebusy thì suggest_time chết, trong khi
đăng nhập vẫn xanh và list_calendars (tool validate) vẫn chạy - nên nút Test cũng báo xanh.

Test này khoá 3 thứ: catalog xin đủ scope, Javis lưu và so được scope THẬT ĐƯỢC CẤP, và mọi
đường báo lỗi (Test, health, lỗi tool) đều nói thẳng thiếu quyền gì.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401  - nạp server/ vào sys.path
import json
import sys

import mcp_hub
import oauth_mcp

_fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)


CAL = "https://www.googleapis.com/auth/calendar"
FREEBUSY = "https://www.googleapis.com/auth/calendar.events.freebusy"
CALLIST = "https://www.googleapis.com/auth/calendar.calendarlist.readonly"
EVENTS_RO = "https://www.googleapis.com/auth/calendar.events.readonly"
EVENTS = "https://www.googleapis.com/auth/calendar.events"

# ---- 1. Catalog phải xin ĐỦ scope hạt nhỏ mà server MCP của Google đòi ----
catalog = json.loads((ROOT / "system" / "mcp-catalog.json").read_text(encoding="utf-8"))
by_id = {c["id"]: c for c in catalog["connectors"]}
cal_scopes = (by_id["google-calendar"].get("auth") or {}).get("scopes") or []
check("Lịch: giữ scope gộp 'calendar' (create_event nhận nó)", CAL in cal_scopes)
check("Lịch: xin calendar.events (đường thứ hai cho tool ghi)", EVENTS in cal_scopes)
check("Lịch: xin calendar.calendarlist.readonly", CALLIST in cal_scopes)
check("Lịch: xin calendar.events.readonly", EVENTS_RO in cal_scopes)
check("Lịch: xin calendar.events.freebusy - THIẾU nó là suggest_time chết", FREEBUSY in cal_scopes)

gmail_scopes = (by_id["gmail"].get("auth") or {}).get("scopes") or []
for s in ("gmail.modify", "gmail.readonly", "gmail.compose", "gmail.labels"):
    check(f"Gmail: xin {s}", f"https://www.googleapis.com/auth/{s}" in gmail_scopes)

# Cả hai vẫn phải giữ prompt=consent, nếu không Google đi đường tắt và KHÔNG cấp scope mới
# cho người đã từng đồng ý - đúng bẫy làm "đăng nhập lại" trở nên vô nghĩa.
for cid in ("google-calendar", "gmail"):
    ap = ((by_id[cid].get("auth") or {}).get("authorize_params") or {})
    check(f"{cid}: giữ prompt=consent để đăng nhập lại thật sự xin lại quyền",
          ap.get("prompt") == "consent")

# ---- 2. scope_report: so scope ĐƯỢC CẤP với scope catalog xin ----
_conn_gia = {"id": "c1", "connector": {"auth": {"scopes": ["openid", "email", CAL, FREEBUSY]}}}
oauth_mcp._conn = lambda cid: _conn_gia if cid == "c1" else None


def gia_lap_token(scopes_str, co_token=True):
    ent = {"scopes": scopes_str}
    if co_token:
        ent["access_token"] = "enc"
    oauth_mcp._load = lambda: {"c1": ent}


gia_lap_token("openid https://www.googleapis.com/auth/userinfo.email " + CAL)
rep = oauth_mcp.scope_report("c1")
check("token cũ chỉ có scope gộp -> báo THIẾU freebusy", rep["missing"] == [FREEBUSY])
check("token cũ chỉ có scope gộp -> known=True (đã biết, không phải mù)", rep["known"] is True)

gia_lap_token("openid https://www.googleapis.com/auth/userinfo.email " + CAL + " " + FREEBUSY)
check("token đủ quyền -> không thiếu gì", oauth_mcp.scope_report("c1")["missing"] == [])

# Google trả 'email' dưới dạng URL userinfo.email; xin bằng tên ngắn 'email' mà coi là thiếu
# thì mọi kết nối Google đều đỏ oan.
gia_lap_token(CAL + " " + FREEBUSY)   # không có openid/email
check("scope định danh (openid/email) không bao giờ tính là thiếu",
      oauth_mcp.scope_report("c1")["missing"] == [])

# Token lưu TRƯỚC bản này không có trường scopes -> KHÔNG được đoán bừa là thiếu.
gia_lap_token("")
rep = oauth_mcp.scope_report("c1")
check("token cũ chưa ghi scope -> known=False", rep["known"] is False)
check("CANARY: chưa biết thì missing RỖNG, không bắt user đăng nhập lại vô cớ", rep["missing"] == [])

# ---- 3. Thông báo lỗi phải gọi tên đúng quyền còn thiếu ----
gia_lap_token("openid " + CAL)
loi_scope = ('{"code": 403, "message": "Request had insufficient authentication scopes.", '
             '"status": "PERMISSION_DENIED"}')
msg = mcp_hub._friendly_tool_error(loi_scope, "c1")
check("lỗi thiếu scope + biết conn -> nêu ĐÍCH DANH quyền còn thiếu",
      "calendar.events.freebusy" in msg)
check("lỗi thiếu scope -> nói rõ phải Đăng nhập lại", "Đăng nhập lại" in msg)
check("lỗi thiếu scope -> nói rõ xoá đi cài lại KHÔNG chữa được",
      "xoá kết nối rồi tạo lại" in msg.lower() or "xoá kết nối rồi tạo lại" in msg)

msg_khong_conn = mcp_hub._friendly_tool_error(loi_scope)
check("không truyền conn_id vẫn chạy (chữ ký cũ còn dùng được)", "Đăng nhập lại" in msg_khong_conn)
check("không biết conn -> không bịa tên quyền", "freebusy" not in msg_khong_conn)

# ---- 4. Không có em dash trong mọi chuỗi UI (quy tắc cứng của dự án) ----
for m_ in (msg, msg_khong_conn,
           mcp_hub._hidden_hint({"c": {"perm": "readonly", "ns": "google-calendar",
                                       "tools": ["create_event"]}})):
    if "—" in m_ or "–" in m_:
        check("không có em/en dash trong thông báo", False)
        break
else:
    check("không có em/en dash trong thông báo", True)

# ---- 5. Tool bị mức quyền ẩn phải được KỂ RA, không biến mất im lặng ----
hidden = {"c1": {"perm": "readonly", "ns": "google-calendar",
                 "tools": ["create_event", "update_event", "delete_event"]}}
hint = mcp_hub._hidden_hint(hidden)
check("tool bị ẩn -> nêu tên tool", "create_event" in hint)
check("tool bị ẩn -> nêu mức quyền đang chặn", "readonly" in hint)
check("tool bị ẩn -> dặn model đừng kết luận là kết nối hỏng", "ĐỪNG kết luận" in hint)
check("lọc theo nguồn: nguồn khác thì không kể",
      mcp_hub._hidden_hint(hidden, {"pancake"}) == "")
check("lọc theo nguồn: trúng nguồn thì có kể",
      "create_event" in mcp_hub._hidden_hint(hidden, {"google-calendar"}))
check("CANARY: không có gì bị ẩn -> chuỗi rỗng, không nhiễu", mcp_hub._hidden_hint({}) == "")

# ---- 6. Các đường báo lỗi thật sự ĐI QUA những hàm trên (chống mồ côi) ----
src = (SERVER / "mcp_hub.py").read_text(encoding="utf-8")
check("validate_connection soát scope trước khi dial (nút Test hết báo xanh oan)",
      "scope_report" in src.split("async def validate_connection")[1])
health = (SERVER / "connect_health.py").read_text(encoding="utf-8")
check("vòng check sức khoẻ cũng soát scope", "scope_report" in health)
oa = (SERVER / "oauth_mcp.py").read_text(encoding="utf-8")
check("handle_callback LƯU scope thật được cấp", 'scopes=str(tk.get("scope")' in oa)
check("refresh giữ scope mới nhất", 'ent["scopes"] = str(tk["scope"])' in oa)

if _fails:
    print(f"\nFAIL - test_scope_google: {len(_fails)} lỗi: {_fails}")
    sys.exit(1)
print("\nOK - test_scope_google: tất cả pass")
