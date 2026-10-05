"""Test đấu Google Ads bằng OAuth thay vì bắt chạy `gcloud auth application-default login`.

    python tests/run.py google_ads_oauth

Không cần pytest, KHÔNG chạm mạng (ghi thẳng token giả vào kho oauth).

Bối cảnh: file ADC mà gcloud sinh ra thực chất chỉ là
{type: authorized_user, client_id, client_secret, refresh_token}. Javis đã có sẵn luồng OAuth
Google (dùng cho Gmail/Lịch), nên chỉ cần chạy luồng đó với scope adwords rồi TỰ DỰNG file ADC.
Vướng duy nhất: oauth_mcp sinh HTTP header (cho transport http), còn google-ads là stdio và cần
credential dạng FILE + biến môi trường. Test này phủ đúng cầu nối đó.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401  - nạp server/ vào sys.path (xem tests/python/_paths.py)
import json
import os
import sys
import tempfile

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-adstest-"))

import mcp_catalog  # noqa: E402
import mcp_store  # noqa: E402
import oauth_mcp  # noqa: E402
import secrets_store  # noqa: E402

_fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)


# ---- catalog phải khai đúng ----
con = mcp_catalog.get("google-ads")
auth = (con or {}).get("auth") or {}
check("google-ads tồn tại trong catalog", con is not None)
check("đổi sang đăng nhập OAuth (không còn dán file gcloud)", auth.get("type") == "oauth")
check("provider google", auth.get("provider") == "google")
check("xin đúng scope adwords",
      any("adwords" in s for s in (auth.get("scopes") or [])))
check("xin refresh_token (access_type=offline)",
      (auth.get("authorize_params") or {}).get("access_type") == "offline")

of = (con or {}).get("oauth_file") or {}
check("khai oauth_file để dựng credential dạng FILE", of.get("format") == "google_adc")
check("oauth_file trỏ đúng biến môi trường",
      of.get("env") == "GOOGLE_APPLICATION_CREDENTIALS")

fields = {f["key"]: f for f in (auth.get("fields") or [])}
check("có ô Client ID + Client Secret", "client_id" in fields and "client_secret" in fields)
check("giữ ô developer_token", "developer_token" in fields)
check("giữ đường lui dán tay file ADC", bool(fields.get("adc_json", {}).get("optional")))
# google-ads-mcp không còn đọc GOOGLE_PROJECT_ID, và file ADC Javis dựng cũng không cần nó (0.82.0).
check("bỏ ô Project ID (server không đọc nữa)", "project_id" not in fields)
check("chạy bản PyPI chính thức mới nhất, không chạy code GitHub",
      (con or {}).get("args") == ["google-ads-mcp@latest"])

guide = auth.get("guide") or ""
# Nhắc gcloud như ĐƯỜNG LUI cho ai đã lỡ chạy thì được; bắt CÀI hoặc bắt CHẠY thì không.
_dong_can_truoc = next((l for l in guide.split("\n") if l.startswith("Cần trước")), "")
check("dòng 'Cần trước' KHÔNG bắt cài gcloud / Google Cloud CLI",
      "gcloud" not in _dong_can_truoc.lower() and "cloud cli" not in _dong_can_truoc.lower())
check("hướng dẫn KHÔNG còn dòng lệnh shell nào",
      not any(t in guide for t in ("application-default login", "--client-id-file",
                                   "winget install", "--scopes=")))
check("hướng dẫn nói rõ là KHÔNG cần chạy lệnh",
      "không phải chạy lệnh" in guide.lower() or "không cần chạy lệnh" in guide.lower())
check("hướng dẫn có nhắc dán Redirect URI", "callback" in guide)

# ---- dựng nội dung file ADC ----
check("format lạ -> trả rỗng, không nổ", oauth_mcp.credentials_file("khong-co", "linh tinh") == "")
check("chưa đăng nhập -> trả rỗng", oauth_mcp.credentials_file("khong-co", "google_adc") == "")

cid, err = mcp_store.add_connection("google-ads", {
    "label": "thử", "auth": "oauth",
    "fields": {"client_id": "CID.apps.googleusercontent.com", "client_secret": "GOCSPX-bimat",
               "developer_token": "DEVTOK", "login_customer_id": "123-456-7890"}})
check("tạo được connection oauth", bool(cid) and not err)

# Giả lập đã đăng nhập xong: nhét refresh_token vào kho oauth y như handle_callback làm.
_store = oauth_mcp._load()
_store[cid] = {"access_token": secrets_store.encrypt("AT"),
               "refresh_token": secrets_store.encrypt("RT-BI-MAT"),
               "provider": "google", "expires_at": 0}
oauth_mcp._save(_store)

blob = oauth_mcp.credentials_file(cid, "google_adc")
check("đã đăng nhập -> dựng được nội dung ADC", bool(blob))
adc = json.loads(blob or "{}")
check("ADC đúng kiểu authorized_user", adc.get("type") == "authorized_user")
check("ADC có client_id", adc.get("client_id") == "CID.apps.googleusercontent.com")
check("ADC có client_secret", adc.get("client_secret") == "GOCSPX-bimat")
check("ADC có refresh_token lấy từ kho oauth", adc.get("refresh_token") == "RT-BI-MAT")

# ---- ĐẦU-CUỐI: resolved() phải ghi file và trỏ env vào ----
res = next((c for c in mcp_store.resolved(enabled_only=False) if c["id"] == cid), None)
check("resolved() thấy connection", res is not None)
env = (res or {}).get("env") or {}
duong_dan = env.get("GOOGLE_APPLICATION_CREDENTIALS", "")
check("env GOOGLE_APPLICATION_CREDENTIALS được đặt", bool(duong_dan))
check("BẢO MẬT: env chứa ĐƯỜNG DẪN, không phải nội dung credential",
      "RT-BI-MAT" not in str(env))
check("file ADC thật sự tồn tại trên đĩa", bool(duong_dan) and os.path.exists(duong_dan))
if duong_dan and os.path.exists(duong_dan):
    tren_dia = json.loads(open(duong_dan, encoding="utf-8").read())
    check("file trên đĩa đúng nội dung ADC",
          tren_dia.get("refresh_token") == "RT-BI-MAT"
          and tren_dia.get("type") == "authorized_user")

check("các biến môi trường khác vẫn được truyền",
      env.get("GOOGLE_ADS_DEVELOPER_TOKEN") == "DEVTOK"
      and env.get("GOOGLE_ADS_LOGIN_CUSTOMER_ID") == "123-456-7890")

# ---- đường lui: dán tay file ADC thì KHÔNG bị OAuth ghi đè ----
cid2, _ = mcp_store.add_connection("google-ads", {
    "label": "dán tay", "fields": {
        "client_id": "x", "client_secret": "y", "developer_token": "D",
        "adc_json": json.dumps({"type": "authorized_user", "refresh_token": "TU-DAN-TAY"})}})
res2 = next((c for c in mcp_store.resolved(enabled_only=False) if c["id"] == cid2), None)
dd2 = ((res2 or {}).get("env") or {}).get("GOOGLE_APPLICATION_CREDENTIALS", "")
check("dán tay -> vẫn có env trỏ tới file", bool(dd2))
if dd2 and os.path.exists(dd2):
    check("dán tay -> giữ ĐÚNG nội dung người dùng dán, OAuth không ghi đè",
          "TU-DAN-TAY" in open(dd2, encoding="utf-8").read())

# ---- CANARY: chứng minh check 'file ADC có refresh_token' có quyền lực thật ----
_rong = oauth_mcp.credentials_file(cid2, "google_adc")
check("CANARY: connection CHƯA đăng nhập OAuth thì credentials_file PHẢI rỗng "
      "-> tức hàm thật sự đọc kho token chứ không bịa ra file", _rong == "")

if _fails:
    print(f"\nFAIL - test_google_ads_oauth: {len(_fails)} lỗi: {_fails}")
    sys.exit(1)
print("\nOK - test_google_ads_oauth: tất cả pass")
