"""Test bảo mật lõi Javis (P0). Chạy tay / CI:

    python tests/run.py security

Không cần pytest, không chạm mạng. Tự cô lập STATE_DIR sang thư mục tạm.
Phủ: hash mật khẩu, require_login fail-closed, session TTL, setup token, mã hoá secret at rest,
secrets_store roundtrip, ma trận quyền MCP, chống path traversal, quyết định CSRF/DNS-rebinding,
rào _AUTH_LOCAL_EXACT (endpoint chỉ-localhost miễn đăng nhập).
"""
from _paths import ROOT, SERVER  # noqa: E402,F401  - nạp server/ vào sys.path (xem tests/python/_paths.py)
import os
import sys
import tempfile

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-sectest-")
os.environ.pop("JAVIS_ALLOWED_HOSTS", None)

import config as cfg           # noqa: E402
import secrets_store           # noqa: E402
import mcp_catalog             # noqa: E402
import mcp_hub                 # noqa: E402
import web_security            # noqa: E402
import main                    # noqa: E402

_fails = []


def check(name, cond):
    print(("ok  " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)


# ---- 1. Mật khẩu ----
h, salt = cfg.hash_password("hunter2")
check("password verify đúng", cfg.verify_password("hunter2", {"auth": {"password_hash": h, "salt": salt}}))
check("password verify sai", not cfg.verify_password("wrong", {"auth": {"password_hash": h, "salt": salt}}))
check("hash không phải plaintext", "hunter2" not in h and len(h) >= 40)

# ---- 2. require_login FAIL-CLOSED theo bind ----
_saved = {k: os.environ.get(k) for k in ("JAVIS_HOST", "JAVIS_REQUIRE_LOGIN")}
try:
    os.environ.pop("JAVIS_REQUIRE_LOGIN", None)
    os.environ["JAVIS_HOST"] = "0.0.0.0"
    check("public bind → bắt buộc login", cfg.require_login() is True)
    os.environ["JAVIS_HOST"] = "127.0.0.1"
    check("localhost bind → không ép login", cfg.require_login() is False)
    os.environ["JAVIS_HOST"] = "192.168.1.50"
    check("LAN IP bind → bắt buộc login", cfg.require_login() is True)
    os.environ["JAVIS_REQUIRE_LOGIN"] = "0"
    os.environ["JAVIS_HOST"] = "0.0.0.0"
    check("JAVIS_REQUIRE_LOGIN=0 ép tắt kể cả public", cfg.require_login() is False)
finally:
    for k, v in _saved.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v

# ---- 3. Session có HẠN ----
tok = cfg.new_session()
check("session mới hợp lệ", cfg.valid_session(tok))
cfg.SESSIONS[tok] = cfg._time.time() - (cfg._SESSION_TTL + 10)   # ép quá hạn
check("session quá hạn bị loại", not cfg.valid_session(tok))
check("session quá hạn bị xoá khỏi store", tok not in cfg.SESSIONS)

# ---- 4. Setup token (chống chiếm admin lần đầu public) ----
os.environ["JAVIS_HOST"] = "0.0.0.0"
os.environ.pop("JAVIS_REQUIRE_LOGIN", None)
t = cfg.get_or_create_setup_token()
check("public+chưa admin → có setup token", bool(t))
check("setup token đúng qua", cfg.check_setup_token(t))
check("setup token sai chặn", not cfg.check_setup_token("saibet"))
os.environ["JAVIS_HOST"] = "127.0.0.1"

# ---- 5. secrets_store roundtrip ----
enc = secrets_store.encrypt("sk-secret-123")
check("encrypt có prefix enc:", enc.startswith("enc:"))
check("encrypt che giá trị gốc", "sk-secret-123" not in enc)
check("decrypt khôi phục", secrets_store.decrypt(enc) == "sk-secret-123")
check("encrypt idempotent", secrets_store.encrypt(enc) == enc)
check("decrypt legacy plaintext", secrets_store.decrypt("sk-plain-legacy") == "sk-plain-legacy")

# ---- 6. Secret trong settings.json MÃ HOÁ at rest ----
c = cfg.read_settings()
c["model"]["openrouter_key"] = "sk-or-TESTKEY"
c["telegram"]["token"] = "123456:TELEGRAM-TESTTOKEN"
c["model"]["openai_oauth"]["access_token"] = "oauth-ACCESS-TEST"
cfg.write_settings(c)
raw = cfg.SETTINGS_PATH.read_text(encoding="utf-8")
check("settings.json KHÔNG chứa key plaintext", "sk-or-TESTKEY" not in raw and "TELEGRAM-TESTTOKEN" not in raw)
check("settings.json có enc:", "enc:" in raw)
check("caller giữ plaintext sau write", c["model"]["openrouter_key"] == "sk-or-TESTKEY")
c2 = cfg.read_settings()
check("read_settings giải mã lại đúng", c2["model"]["openrouter_key"] == "sk-or-TESTKEY"
      and c2["telegram"]["token"] == "123456:TELEGRAM-TESTTOKEN"
      and c2["model"]["openai_oauth"]["access_token"] == "oauth-ACCESS-TEST")

# ---- 7. Ma trận quyền MCP (lớp CỨNG) ----
conn = {"id": "x", "tool_meta": {"read": ["list_*", "*_get"], "write": ["create_*"],
                                 "danger": ["delete_*", "pay_*"]}}
check("classify read", mcp_catalog.classify(conn, "list_orders") == "read")
check("classify write", mcp_catalog.classify(conn, "create_order") == "write")
check("classify danger", mcp_catalog.classify(conn, "delete_order") == "danger")
check("readonly chặn write", mcp_catalog.allowed(conn, "readonly", "full", "create_order")[0] is False)
check("readonly cho read", mcp_catalog.allowed(conn, "readonly", "full", "list_orders")[0] is True)
check("safe cho write", mcp_catalog.allowed(conn, "safe", "full", "create_order")[0] is True)
check("safe chặn danger", mcp_catalog.allowed(conn, "safe", "full", "delete_order")[0] is False)
check("full cho danger", mcp_catalog.allowed(conn, "full", "full", "delete_order")[0] is True)
check("mode suggest ép readonly (chặn write dù perm full)",
      mcp_catalog.allowed(conn, "full", "suggest", "create_order")[0] is False)
check("mode auto trần safe (chặn danger dù perm full)",
      mcp_catalog.allowed(conn, "full", "auto", "delete_order")[0] is False)

# ---- 8. Chống path traversal trong vault ----
base = tempfile.mkdtemp(prefix="javis-vault-")
ok_path = mcp_hub._safe_path(base, "notes/report.md")
check("path hợp lệ trong vault", str(ok_path).startswith(os.path.realpath(base)))
for bad in ("../etc/passwd", "../../secret", "/etc/passwd"):
    try:
        mcp_hub._safe_path(base, bad)
        check(f"chặn traversal {bad}", False)
    except ValueError:
        check(f"chặn traversal {bad}", True)

# ---- 9. Quyết định CSRF / DNS-rebinding ----
web_security.invalidate()
check("cùng-origin ghi → cho qua",
      web_security.csrf_decision("POST", "localhost:7777", "http://localhost:7777", False) is None)
check("cross-origin ghi → chặn 403",
      (web_security.csrf_decision("POST", "localhost:7777", "http://evil.example", False) or (0,))[0] == 403)
check("không có Origin (curl/CLI) ghi → cho qua",
      web_security.csrf_decision("POST", "localhost:7777", None, False) is None)
check("cross-origin ĐỌC (GET) → cho qua (không mutating)",
      web_security.csrf_decision("GET", "localhost:7777", "http://evil.example", False) is None)
check("no-auth + host lạ (rebinding) → chặn",
      (web_security.csrf_decision("GET", "evil.example", None, False) or (0,))[0] == 403)
check("no-auth + host localhost → cho qua",
      web_security.csrf_decision("GET", "127.0.0.1:7777", None, False) is None)
check("no-auth + host IP → cho qua",
      web_security.csrf_decision("GET", "192.168.1.9:7777", None, False) is None)
check("đã bật auth + host lạ → cho qua (không khoá nhầm deploy)",
      web_security.csrf_decision("GET", "some-domain.com", None, True) is None)

# ---- 10. Rào _AUTH_LOCAL_EXACT: /reminders/cancel phải được miễn đăng nhập localhost ----
# Lỗi Important vừa vá: _AUTH_LOCAL_EXACT trước đây chỉ có ("/telegram/send-file", "/reminders"),
# thiếu "/reminders/cancel". main.py:94 khớp CHÍNH XÁC theo path (không phải prefix), nên khi đã
# bật mật khẩu (gate_active()=True) thì javis_schedule op=cancel (httpx.post từ localhost, không
# cookie) LUÔN 401 dù POST /reminders (TẠO nhắc) đã được miễn cùng nhóm. Huỷ là thao tác YẾU HƠN
# tạo nên miễn cùng mức là nhất quán, không phải nới rào.
check("rào: /reminders/cancel được miễn đăng nhập localhost",
      "/reminders/cancel" in main._AUTH_LOCAL_EXACT)
check("rào: /reminders (tạo nhắc) vẫn còn được miễn (không mất khi thêm /reminders/cancel)",
      "/reminders" in main._AUTH_LOCAL_EXACT)
# Nguyên tắc rào: một path KHÔNG có mặt trong tuple thì KHÔNG được miễn - vd /loops (route ghi
# self_improve; chính plugin javis_schedule đã lý luận "KHÔNG dùng POST /loops vì cần đăng nhập").
check("rào: /loops KHÔNG nằm trong _AUTH_LOCAL_EXACT (path lạ không tự nhiên được miễn)",
      "/loops" not in main._AUTH_LOCAL_EXACT)
check("rào: không còn webhook Zalo local sau khi chuyển sang MCP chuẩn",
      "/hook/zalo" not in main._AUTH_LOCAL_EXACT)
# Tin Zalo do NGƯỜI LẠ soạn và được chuyển thẳng vào Telegram của chủ. _notify_owner phải
# gửi PLAIN TEXT: nếu ai đó thêm parse_mode như telegram_bot._send (MarkdownV2) thì chữ
# trong tin khách sẽ dựng được markup, mở đường giả dạng lời của Javis.
import inspect  # noqa: E402
check("rào: _notify_owner gửi plain text, KHÔNG parse_mode (tin người lạ không dựng được markup)",
      "parse_mode" not in inspect.getsource(main._notify_owner))

# external_base: dựng redirect OAuth theo địa chỉ NGƯỜI DÙNG thấy (vụ VPS Hostinger:
# uvicorn sau proxy thấy http nội bộ, dựng redirect http:// làm Meta chặn "không bảo mật").
check("external_base: sau proxy https → lấy X-Forwarded-Proto",
      web_security.external_base("http", "javis.example.com", "https", "")
      == "https://javis.example.com")
check("external_base: X-Forwarded-Host thắng host nội bộ",
      web_security.external_base("http", "10.0.0.5:7777", "https", "javis.example.com")
      == "https://javis.example.com")
check("external_base: không proxy → giữ nguyên scheme/host của request",
      web_security.external_base("http", "localhost:7777", "", "")
      == "http://localhost:7777")
check("external_base: header nhiều giá trị (proxy chồng) → lấy giá trị ĐẦU",
      web_security.external_base("http", "x", "https, http", "a.com, b.com")
      == "https://a.com")
check("external_base: CHỈ dùng cho redirect_uri - không được lẫn vào quyết định localhost",
      "external_base" not in inspect.getsource(main._auth_guard))

# ---- 12. GET có tác dụng phụ: chặn khi TRANG KHÁC kích hoạt (Sec-Fetch-Site) ----
# Vì sao cần lớp này ngoài csrf_decision: điều hướng top-level GET không gửi Origin, mà cookie
# javis_session là SameSite=lax nên VẪN đi kèm → csrf_decision cho qua sạch.
check("cross-site điều hướng vào /workflows/run → chặn 403",
      (web_security.navigation_decision("/workflows/run", "cross-site") or (0,))[0] == 403)
check("cross-site điều hướng vào /workflows/resume (duyệt ghi) → chặn 403",
      (web_security.navigation_decision("/workflows/resume", "cross-site") or (0,))[0] == 403)
check("same-site (khác cổng, vẫn là trang khác) → chặn 403",
      (web_security.navigation_decision("/workflows/run", "same-site") or (0,))[0] == 403)
check("dashboard tự gọi (same-origin) → cho qua",
      web_security.navigation_decision("/workflows/run", "same-origin") is None)
check("user tự gõ URL / bookmark (none) → cho qua",
      web_security.navigation_decision("/workflows/run", "none") is None)
check("curl / Claude CLI / Codex (thiếu header) → cho qua, không khoá nhầm",
      web_security.navigation_decision("/workflows/run", None) is None)
check("endpoint ĐỌC không dính rào này",
      web_security.navigation_decision("/workflows", "cross-site") is None)
check("header hoa/thường lẫn lộn vẫn chặn",
      (web_security.navigation_decision("/workflows/run", " Cross-Site ") or (0,))[0] == 403)

# Rào chỉ có tác dụng nếu path trong SIDE_EFFECT_GET KHỚP route thật. Đổi tên route mà quên
# sửa danh sách = mở cửa lại trong im lặng, nên khoá hai chiều ở đây.
_get_routes = {r.path for r in main.app.routes
               if "GET" in (getattr(r, "methods", None) or set())}
for _p in web_security.SIDE_EFFECT_GET:
    check(f"SIDE_EFFECT_GET '{_p}' trỏ đúng một route GET có thật", _p in _get_routes)
check("middleware _csrf_guard có thật sự gọi navigation_decision",
      "navigation_decision" in inspect.getsource(main._csrf_guard))

print()
if _fails:
    print(f"THẤT BẠI {len(_fails)}: {_fails}")
    sys.exit(1)
print("OK - test_security: tất cả pass")
