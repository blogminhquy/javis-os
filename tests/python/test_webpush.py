"""Thông báo đẩy trình duyệt: phép mã hoá Web Push phải ĐÚNG CHUẨN, không chỉ "chạy được".

    python tests/python/test_webpush.py

Vì sao có file này
==================
Javis tự mã hoá Web Push thay vì cài `pywebpush` - gói đó kéo theo `http-ece`, thứ chỉ phát
hành dạng mã nguồn và phải biên dịch lúc cài, tức là có máy sẽ cài Javis không lên được.
Đổi lại, phần mã hoá thành TRÁCH NHIỆM CỦA MÌNH, và nó là loại code hỏng rất im: sai một
bước dẫn khoá thì hàm vẫn trả về đủ byte, server đẩy vẫn nhận 201, chỉ có trình duyệt là
lặng lẽ không hiện gì. Không ai truy ra được từ phía Javis.

Nên test này không kiểm "có ra bytes". Nó kiểm ba thứ THẬT:

  1. Vòng mã hoá - giải mã khép kín (ECDH + HKDF + AES128GCM đúng cả hai chiều).
  2. Khung dữ liệu đúng RFC 8188: salt(16) | rs(4) | idlen(1) | khoá(65) | ciphertext.
     Sai khung là trình duyệt vứt gói ngay trước khi giải mã.
  3. Chữ ký VAPID (RFC 8292) phải là r||s THÔ 64 byte, xác minh được bằng chính khoá công
     khai gửi kèm. `cryptography` ký ra DER; quên bước đổi thì mọi dịch vụ đẩy trả 401.

Bậc đối chiếu cao hơn nữa (so byte-for-byte với thư viện tham chiếu `http_ece`) đã chạy tay
lúc dựng: cùng salt + cùng khoá tạm thì hai bên ra ĐÚNG một chuỗi byte. Không đưa vào đây vì
không muốn thêm một dependency chỉ để chạy test.
"""
import os
import struct
import tempfile

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-push-"))

from _paths import ROOT, SERVER  # noqa: E402,F401

from cryptography.hazmat.primitives import hashes, serialization  # noqa: E402
from cryptography.hazmat.primitives.asymmetric import ec  # noqa: E402
from cryptography.hazmat.primitives.asymmetric import utils as au  # noqa: E402

import webpush  # noqa: E402

fails = []


def check(name, cond, extra=None):
    print(("PASS: " if cond else "FAIL: ") + name + ("" if cond or extra is None else f"  [{extra}]"))
    if not cond:
        fails.append(name)


# ─────────── 1. Khoá VAPID: sinh một lần, sống mãi ───────────
k1 = webpush.khoa_cong_khai()
k2 = webpush.khoa_cong_khai()
check("khoá công khai ổn định giữa các lần gọi", k1 == k2)
raw = webpush.b64u_giai(k1)
check("khoá là điểm P-256 dạng uncompressed 65 byte", len(raw) == 65 and raw[0] == 0x04, len(raw))
check("khoá lưu ra file để sống qua lần khởi động sau", webpush.VAPID_FILE.exists())
# Đổi khoá = mọi đăng ký cũ thành rác, nên nó phải nằm ở STATE_DIR chứ không trong cây mã nguồn.
check("khoá nằm trong STATE_DIR", str(webpush.VAPID_FILE).startswith(os.environ["JAVIS_STATE_DIR"]))

# ─────────── 2. Mã hoá đúng chuẩn, giải ngược lại được ───────────
ua = ec.generate_private_key(ec.SECP256R1())
ua_pub = ua.public_key().public_bytes(serialization.Encoding.X962,
                                      serialization.PublicFormat.UncompressedPoint)
p256dh = webpush.b64u(ua_pub)
auth = webpush.b64u(os.urandom(16))
tin = "Javis: doanh thu hôm nay 12 đơn 🎉".encode("utf-8")

body = webpush.ma_hoa(tin, p256dh, auth)
check("giải mã ngược ra ĐÚNG bản gốc (ECDH+HKDF+AESGCM khớp cả hai chiều)",
      webpush.giai_ma(body, ua, auth) == tin)
check("giữ nguyên tiếng Việt có dấu và emoji",
      webpush.giai_ma(body, ua, auth).decode("utf-8") == "Javis: doanh thu hôm nay 12 đơn 🎉")

check("khung RFC8188 - salt 16 byte", len(body[:16]) == 16)
check("khung RFC8188 - record size 4096", struct.unpack("!L", body[16:20])[0] == 4096)
check("khung RFC8188 - idlen = 65", body[20] == 65)
check("khung RFC8188 - keyid là điểm uncompressed", body[21] == 0x04)
check("thân dài hơn phần bọc (có ciphertext thật)", len(body) > 21 + 65 + 16)

# Dùng lại cặp (khoá tạm, salt) cho hai tin là lộ khoá dòng - đây là luật an toàn, không phải nit.
check("CANARY: hai lần mã hoá cùng nội dung PHẢI khác nhau",
      webpush.ma_hoa(tin, p256dh, auth) != webpush.ma_hoa(tin, p256dh, auth))

# Khoá rác phải chết NGAY chứ không nằm im tới lúc gửi thật.
for ten, p, a in (("p256dh sai độ dài", webpush.b64u(b"\x04" + b"\x00" * 10), auth),
                  ("auth secret sai độ dài", p256dh, webpush.b64u(b"\x00" * 8))):
    try:
        webpush.ma_hoa(b"x", p, a)
        check("chặn " + ten, False)
    except ValueError:
        check("chặn " + ten, True)

check("cắt bớt tin quá dài thay vì để dịch vụ đẩy từ chối cả gói",
      len(webpush.giai_ma(webpush.ma_hoa(b"a" * 9000, p256dh, auth), ua, auth)) == webpush.MAX_PLAINTEXT)

# ─────────── 3. Chữ ký VAPID xác minh được bằng chính khoá gửi kèm ───────────
tok = webpush._jwt_vapid("https://fcm.googleapis.com/fcm/send/xyz")
h, pl, sg = tok.split(".")
sig = webpush.b64u_giai(sg)
check("CANARY: chữ ký là r||s THÔ 64 byte, không phải DER", len(sig) == 64, len(sig))
pub = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), webpush.b64u_giai(k1))
try:
    pub.verify(au.encode_dss_signature(int.from_bytes(sig[:32], "big"),
                                       int.from_bytes(sig[32:], "big")),
               f"{h}.{pl}".encode("ascii"), ec.ECDSA(hashes.SHA256()))
    check("khoá công khai gửi kèm xác minh được chữ ký", True)
except Exception as e:
    check("khoá công khai gửi kèm xác minh được chữ ký", False, e)

import json  # noqa: E402
claims = json.loads(webpush.b64u_giai(pl))
check("aud là gốc của dịch vụ đẩy, không phải cả URL",
      claims["aud"] == "https://fcm.googleapis.com", claims.get("aud"))
check("có hạn dùng và chưa hết hạn", claims["exp"] > 0)
hdr = webpush.header_vapid("https://updates.push.services.mozilla.com/wpush/v2/abc")
check("header Authorization đúng dạng vapid t=..., k=...",
      hdr["Authorization"].startswith("vapid t=") and ", k=" + k1 in hdr["Authorization"])

# ─────────── 4. Kho đăng ký: gộp trùng, chặn rác, huỷ được ───────────
sub = {"endpoint": "https://fcm.googleapis.com/fcm/send/AAA",
       "keys": {"p256dh": p256dh, "auth": auth}}
ok, err = webpush.dang_ky(sub, "Chrome trên máy bàn")
check("đăng ký được", ok and not err, err)
webpush.dang_ky(sub, "Chrome trên máy bàn")
# Mỗi lần mở lại dashboard là trình duyệt trả về đúng endpoint cũ. Không gộp thì F5 vài lần
# là một cái thông báo hiện lên năm lần.
check("CANARY: trùng endpoint thì CẬP NHẬT, không đẻ thêm", webpush.so_sub() == 1, webpush.so_sub())

ok2, err2 = webpush.dang_ky({"endpoint": "http://khong-phai-https/abc",
                             "keys": {"p256dh": p256dh, "auth": auth}})
check("chặn endpoint không phải https", ok2 is False and "endpoint" in err2, err2)
ok3, err3 = webpush.dang_ky({"endpoint": "https://a.b/c", "keys": {"p256dh": "rac", "auth": "rac"}})
check("chặn khoá rác NGAY lúc đăng ký (không đợi tới lúc gửi)", ok3 is False, err3)

check("huỷ đăng ký", webpush.huy_dang_ky(sub["endpoint"]) and webpush.so_sub() == 0)
check("huỷ cái không có trả False", webpush.huy_dang_ky("https://khong-co/x") is False)


# ─────────── 5. Gửi thật: chặn request lại, GIẢI MÃ ra, và dọn đăng ký chết ───────────
# Đây là đoạn gần nhất với "chạy thật" mà không cần mạng: thay tầng HTTP bằng một bản giả,
# rồi đóng vai trình duyệt để mở gói. Chạy được tới đây nghĩa là dịch vụ đẩy thật cũng đọc
# được gói đó - phần còn lại chỉ là đường truyền.
import asyncio  # noqa: E402


class _GiaResponse:
    def __init__(self, code):
        self.status_code = code
        self.text = ""


class _GiaClient:
    """Đóng vai httpx.AsyncClient: ghi lại mọi request rồi trả mã do test đặt sẵn."""
    da_goi = []
    ma_tra = {}

    def __init__(self, *a, **k):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def post(self, url, content=None, headers=None, **k):
        _GiaClient.da_goi.append({"url": url, "body": content, "headers": headers or {}})
        return _GiaResponse(_GiaClient.ma_tra.get(url, 201))


import httpx  # noqa: E402

that_client = httpx.AsyncClient
webpush.dang_ky(sub, "máy test")
sub2 = {"endpoint": "https://updates.push.services.mozilla.com/wpush/v2/CHET",
        "keys": {"p256dh": p256dh, "auth": auth}}
webpush.dang_ky(sub2)
_GiaClient.ma_tra = {sub2["endpoint"]: 410}      # 410 = đăng ký đã chết
httpx.AsyncClient = _GiaClient
try:
    da_gui, da_don, chi_tiet = asyncio.new_event_loop().run_until_complete(
        webpush.gui_het("Javis", "Doanh thu hôm nay 12 đơn", "/?mo_thu=abc", tag="javis-abc"))
finally:
    httpx.AsyncClient = that_client

check("gửi tới mọi đăng ký còn sống", da_gui == 1, da_gui)
# Đây là lỗi chủ repo gặp 27/08: bấm Gửi thử trên điện thoại, máy tính hiện, điện thoại im -
# mà API vẫn trả "đã gửi" vì CÓ máy nhận được. Kết quả phải tách theo TỪNG thiết bị.
check("CANARY: trả kết quả theo TỪNG thiết bị, không chỉ một con số tổng",
      len(chi_tiet) == 2, len(chi_tiet))
check("mỗi mục nêu tên dịch vụ đẩy để nhận ra máy nào",
      all(m.get("dich_vu") for m in chi_tiet), chi_tiet)
check("máy hỏng bị đánh dấu ok=False kèm lý do",
      any((not m["ok"]) and m["loi"] for m in chi_tiet), chi_tiet)
check("CANARY: 410 thì DỌN đăng ký chết, không giữ lại để hỏng mãi",
      da_don == 1 and webpush.so_sub() == 1, (da_don, webpush.so_sub()))

goi = next(g for g in _GiaClient.da_goi if g["url"] == sub["endpoint"])
h = goi["headers"]
check("header Content-Encoding: aes128gcm", h.get("Content-Encoding") == "aes128gcm", h.get("Content-Encoding"))
check("có TTL để máy đang tắt bật lại vẫn nhận", int(h.get("TTL") or 0) > 0, h.get("TTL"))
check("có Authorization VAPID", str(h.get("Authorization", "")).startswith("vapid t="))
check("Content-Type là octet-stream", h.get("Content-Type") == "application/octet-stream")

# Đóng vai trình duyệt mở gói ra.
mo = json.loads(webpush.giai_ma(goi["body"], ua, auth).decode("utf-8"))
check("CANARY: trình duyệt giải mã ra ĐÚNG nội dung đã gửi",
      mo["title"] == "Javis" and mo["body"] == "Doanh thu hôm nay 12 đơn", mo)
# Không có url thì bấm vào thông báo chỉ mở trang chủ, người dùng lại phải tự đi tìm.
check("gói mang theo đường về đúng mẩu thư", mo["url"] == "/?mo_thu=abc", mo.get("url"))
check("gói mang tag để tin mới ĐÈ tin cũ, không xếp chồng", mo["tag"] == "javis-abc")


# ─────────── 6. Claim `sub` của VAPID phải LIÊN HỆ ĐƯỢC ───────────
# Google/Mozilla nhận gần như mọi chuỗi, nhưng Apple soi thật và trả 400 BadJwtToken cho
# địa chỉ không ra hồn. Hệ quả đúng như chủ repo gặp: Chrome trên máy tính nhận thông báo
# bình thường, iPhone thì im lặng tuyệt đối mà không có lỗi nào hiện ra.
lh = webpush.lien_he()
check("CANARY: sub KHÔNG được trỏ localhost", "localhost" not in lh, lh)
check("sub là mailto: hoặc https: theo RFC 8292",
      lh.startswith("mailto:") or lh.startswith("https://"), lh)
claims_lh = json.loads(webpush.b64u_giai(webpush._jwt_vapid("https://web.push.apple.com/x").split(".")[1]))
check("JWT gửi đi mang đúng địa chỉ đó", claims_lh["sub"] == lh, claims_lh.get("sub"))
os.environ["JAVIS_PUSH_CONTACT"] = "mailto:toi@congty.vn"
check("đổi được bằng JAVIS_PUSH_CONTACT", webpush.lien_he() == "mailto:toi@congty.vn")
os.environ["JAVIS_PUSH_CONTACT"] = "khong-phai-url"
check("giá trị rác thì rơi về mặc định hợp lệ, không gửi rác cho Apple",
      webpush.lien_he().startswith("mailto:"), webpush.lien_he())
os.environ.pop("JAVIS_PUSH_CONTACT", None)

check("nhận ra dịch vụ đẩy của Apple", "Apple" in webpush.ten_dich_vu("https://web.push.apple.com/x"))
check("nhận ra dịch vụ đẩy của Google", "Google" in webpush.ten_dich_vu("https://fcm.googleapis.com/x"))

if fails:
    print(f"\nFAIL - test_webpush: {len(fails)} lỗi: {', '.join(fails)}")
    raise SystemExit(1)
print("\nOK - test_webpush: tất cả pass")
