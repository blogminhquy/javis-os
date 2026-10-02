"""Đổi credential ngay trên UI - bỏ bước bắt người dùng mở terminal chạy lệnh.

Ý tưởng: một số nhà cung cấp không cho lấy token bằng OAuth, mà bắt đổi từ một thứ người dùng
tự tạo (vd Google App Password -> Google master token). Việc đổi đó thường CHỈ LÀ MỘT LỜI GỌI
HTTP, nên server làm hộ được; không có lý do gì bắt người dùng mở terminal.

Catalog khai trong `auth`:

    "exchange": {
      "handler": "google_master_token",   # phải có trong HANDLERS dưới đây
      "inputs":  ["google_email", "app_password"],
      "output":  "master_token",
      "drop":    ["app_password"]         # XOÁ trước khi lưu - không bao giờ ghi xuống đĩa
    }

Đã dán sẵn `output` thì BỎ QUA đổi. Đây là đường lui quan trọng: Google hay chặn đăng nhập từ IP
trung tâm dữ liệu, nên người chạy Javis trên VPS vẫn phải tự lấy token ở máy nhà rồi dán vào.

BẢO MẬT:
- Field trong `drop` bị xoá dù đổi THÀNH CÔNG hay THẤT BẠI.
- Không bao giờ đưa giá trị người dùng nhập vào thông báo lỗi hay log.
- Catalog CHỈ chọn được handler đã khai sẵn trong module này. Không có đường để catalog (hay ai
  sửa được file JSON đó) chỉ định mã tuỳ ý cho server chạy.
"""

# ID thiết bị Android bất kỳ - Google chỉ dùng để phân biệt "thiết bị", không cần thật.
_ANDROID_ID = "0123456789abcdef"


def _c(vi: str, en: str) -> str:
    """Câu lỗi hiện ở form kết nối, theo ngôn ngữ giao diện (`localefmt.chu`)."""
    import localefmt
    return localefmt.chu(vi, en)


def _google_master_token(fields):
    """App Password HOẶC oauth_token (cookie trang EmbeddedSetup) -> master token. Trả (token, lỗi).

    Google siết dần đường App Password (perform_master_login trả BadAuthentication dù chuỗi đúng,
    tuỳ tài khoản). Đường lui chuẩn của cộng đồng gkeepapi: người dùng đăng nhập
    accounts.google.com/EmbeddedSetup trên trình duyệt, lấy cookie oauth_token (oauth2_4/...),
    đổi qua gpsoauth.exchange_token. Cookie đó dùng MỘT lần, không lưu."""
    try:
        import gpsoauth
    except ImportError:
        return None, _c("Máy chủ Javis thiếu thư viện gpsoauth. Chạy: pip install -r requirements.txt "
                        "rồi khởi động lại Javis.",
                        "The Javis server is missing the gpsoauth library. Run: pip install -r requirements.txt "
                        "and restart Javis.")

    email = str(fields.get("google_email") or "").strip()
    # Google hiển thị App Password thành 4 nhóm 4 ký tự có dấu cách; người dùng hay copy cả cách.
    pw = str(fields.get("app_password") or "").replace(" ", "").strip()
    otk = str(fields.get("oauth_token") or "").strip()
    if not email:
        return None, _c("Cần điền Email Google.", "Enter the Google email.")
    if not pw and not otk:
        return None, _c("Cần App Password, hoặc oauth_token lấy từ trình duyệt theo hướng dẫn "
                        "trong form (một trong hai).",
                        "An App Password is needed, or an oauth_token taken from the browser as the form "
                        "explains (one of the two).")

    if otk:
        try:
            res = gpsoauth.exchange_token(email, otk, _ANDROID_ID)
        except Exception as e:
            return None, _c(f"Không gọi được máy chủ Google ({type(e).__name__}). Kiểm tra mạng của "
                            "máy chạy Javis rồi thử lại.",
                            f"Could not reach Google's server ({type(e).__name__}). Check the network of "
                            "the machine running Javis and try again.")
        token = res.get("Token")
        if token:
            return token, ""
        ma = str(res.get("Error") or res.get("error") or "").strip()
        return None, _c(f"Google từ chối oauth_token (mã: {ma or 'không rõ'}). Cookie này dùng MỘT "
                        "lần và hết hạn nhanh: mở lại accounts.google.com/EmbeddedSetup trong tab "
                        "ẩn danh, lấy cookie oauth_token MỚI rồi dán và bấm Kết nối ngay.",
                        f"Google rejected the oauth_token (code: {ma or 'unknown'}). This cookie works ONCE "
                        "and expires fast: reopen accounts.google.com/EmbeddedSetup in a private "
                        "tab, take a NEW oauth_token cookie, paste it and click Connect right away.")

    if len(pw) != 16:
        return None, _c(f"App Password phải đúng 16 ký tự (đang nhận {len(pw)}). Đây KHÔNG phải mật "
                        "khẩu Gmail thường, mà là chuỗi Google sinh ra ở myaccount.google.com/apppasswords.",
                        f"The App Password must be exactly 16 characters (got {len(pw)}). It is NOT your "
                        "normal Gmail password but the string Google generates at myaccount.google.com/apppasswords.")

    try:
        res = gpsoauth.perform_master_login(email, pw, _ANDROID_ID)
    except Exception as e:
        return None, _c(f"Không gọi được máy chủ Google ({type(e).__name__}). Kiểm tra mạng của máy "
                        "chạy Javis rồi thử lại.",
                        f"Could not reach Google's server ({type(e).__name__}). Check the network of the "
                        "machine running Javis and try again.")

    token = res.get("Token")
    if token:
        return token, ""

    ma = str(res.get("Error") or res.get("error") or "").strip()
    if ma == "BadAuthentication":
        return None, _c("Google từ chối đăng nhập. Ba khả năng: (1) sai email hoặc App Password, "
                        "tạo lại chuỗi mới ở myaccount.google.com/apppasswords; (2) Google đã siết "
                        "đường App Password với tài khoản này, dùng đường lui oauth_token theo hướng "
                        "dẫn trong form (mở accounts.google.com/EmbeddedSetup); (3) Javis chạy trên "
                        "VPS bị Google chặn IP trung tâm dữ liệu, lấy token ở máy cá nhân rồi dán "
                        "vào ô Master token hoặc oauth_token.",
                        "Google rejected the sign-in. Three possibilities: (1) wrong email or App Password, "
                        "create a new one at myaccount.google.com/apppasswords; (2) Google has tightened "
                        "the App Password route for this account, use the oauth_token fallback as the form "
                        "explains (open accounts.google.com/EmbeddedSetup); (3) Javis runs on a "
                        "VPS whose data-center IP Google blocks, get the token on a personal machine and paste "
                        "it into the Master token or oauth_token box.")
    if ma in ("NeedsBrowser", "DeviceManagementRequiredOrSyncDisabled"):
        return None, _c("Google đòi xác minh thêm bằng trình duyệt. Đăng nhập tài khoản này trên "
                        "trình duyệt một lần, xác nhận cảnh báo bảo mật, rồi thử lại.",
                        "Google wants extra verification in a browser. Sign in to this account in a "
                        "browser once, confirm the security alert, then try again.")
    if ma == "NotAvailable":
        return None, _c("Tài khoản chưa bật xác minh 2 bước nên chưa tạo được App Password. Bật 2 bước "
                        "rồi tạo lại chuỗi.",
                        "2-Step Verification is off for this account, so no App Password can be created. Turn it on "
                        "and create the password again.")
    return None, _c(f"Google từ chối đăng nhập (mã: {ma or 'không rõ'}). Thử tạo lại App Password, "
                    "hoặc lấy master token ở máy cá nhân rồi dán thẳng vào ô Master token.",
                    f"Google rejected the sign-in (code: {ma or 'unknown'}). Try creating a new App Password, "
                    "or get the master token on a personal machine and paste it into the Master token box.")


def _apify_verify_token(fields):
    """Verify a Personal API token before saving a virtual connector."""
    import httpx

    token = str(fields.get("apify_token") or fields.get("apify_token_raw") or "").strip()
    if not token:
        return None, _c("Cần dán Apify Personal API token.", "Paste an Apify Personal API token.")
    try:
        response = httpx.get("https://api.apify.com/v2/users/me",
                             headers={"Authorization": f"Bearer {token}"}, timeout=15)
    except Exception as error:
        return None, _c(f"Không gọi được máy chủ Apify ({type(error).__name__}). "
                        "Kiểm tra mạng rồi thử lại.",
                        f"Could not reach Apify's server ({type(error).__name__}). "
                        "Check the network and try again.")
    if response.status_code == 200:
        return token, ""
    if response.status_code in (401, 403):
        return None, _c("Apify từ chối token này. Copy lại Personal API token tại "
                        "console.apify.com/settings/integrations rồi thử lại.",
                        "Apify rejected this token. Copy the Personal API token again at "
                        "console.apify.com/settings/integrations and try again.")
    return None, _c(f"Apify trả HTTP {response.status_code}. Thử lại sau ít phút.",
                    f"Apify returned HTTP {response.status_code}. Try again in a few minutes.")


HANDLERS = {
    "google_master_token": _google_master_token,
    "apify_verify_token": _apify_verify_token,
}

_FACEBOOK_MONITOR_EXCHANGE = {
    "handler": "apify_verify_token",
    "inputs": ["apify_token"],
    "output": "apify_token",
    "skip_if_output": False,
}


def run(connector, fields):
    """Chạy bước đổi credential nếu connector có khai. Trả (fields_mới, lỗi).

    Luôn trả về BẢN SAO đã xoá các field `drop`, kể cả khi lỗi - để người gọi không vô tình lưu
    thứ đáng ra phải vứt."""
    fields = dict(fields or {})
    ex = ((connector or {}).get("auth") or {}).get("exchange") or {}
    # Older javis.facebook-monitor packs have only the apify_token field. Their virtual
    # connector cannot be dialed by validate_connection, so verify it here as well.
    if not ex and (connector or {}).get("id") == "facebook-monitor":
        ex = _FACEBOOK_MONITOR_EXCHANGE
    if not ex:
        return fields, ""

    drop = list(ex.get("drop") or [])

    def _bo_rac(d):
        for k in drop:
            d.pop(k, None)
        return d

    out_key = str(ex.get("output") or "")
    # Some exchanges are conversions (Google), others validate the final value (Apify).
    if out_key and str(fields.get(out_key) or "").strip():
        if ex.get("skip_if_output") is not False:
            return _bo_rac(fields), ""
        inputs_cfg = list(ex.get("inputs") or [])
        if inputs_cfg and not str(fields.get(inputs_cfg[0]) or "").strip():
            fields[inputs_cfg[0]] = str(fields.get(out_key) or "").strip()

    inputs = list(ex.get("inputs") or [])
    nhan = {f.get("key"): f for f in ((connector or {}).get("auth") or {}).get("fields") or []}
    # Input khai optional trong auth.fields được phép bỏ trống - handler tự kiểm tổ hợp
    # (vd Google Keep: cần App Password HOẶC oauth_token, không bắt cả hai).
    thieu = [k for k in inputs
             if not str(fields.get(k) or "").strip() and not (nhan.get(k) or {}).get("optional")]
    if thieu:
        ten = ", ".join((nhan.get(k) or {}).get("label") or k for k in thieu)
        return _bo_rac(fields), _c(f"Thiếu: {ten}.", f"Missing: {ten}.")

    fn = HANDLERS.get(str(ex.get("handler") or ""))
    if not fn:
        return _bo_rac(fields), _c("Bản Javis này chưa biết cách đổi credential cho connector đó. "
                                   "Cập nhật Javis rồi thử lại.",
                                   "This Javis version does not know how to exchange credentials for that connector. "
                                   "Update Javis and try again.")

    try:
        gia_tri, loi = fn({k: fields.get(k) for k in inputs})
    except Exception as e:
        return _bo_rac(fields), _c(f"Lỗi khi đổi credential ({type(e).__name__}).",
                                   f"Error while exchanging credentials ({type(e).__name__}).")

    if loi or not gia_tri:
        return _bo_rac(fields), loi or _c("Không đổi được credential.", "Could not exchange the credentials.")

    fields[out_key] = gia_tri
    return _bo_rac(fields), ""
