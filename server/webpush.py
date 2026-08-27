"""Thông báo đẩy của trình duyệt (Web Push) - tự mã hoá, KHÔNG thêm thư viện ngoài.

Vì sao tự viết thay vì cài `pywebpush`
======================================
`pywebpush` kéo theo `http-ece`, mà gói đó chỉ phát hành dạng mã nguồn và phải BIÊN DỊCH
lúc cài. Javis là app tự cài trên máy người dùng và trên VPS bằng một dòng
`pip install -r requirements.txt`; thêm một gói có thể gãy lúc build nghĩa là có máy cài
Javis không lên được nữa - trả giá quá đắt cho một tính năng phụ. Toàn bộ phép mã hoá dưới
đây chỉ cần `cryptography`, thứ Javis vốn đã có sẵn trong requirements.

Chuẩn áp dụng
=============
- RFC 8291 (Message Encryption for Web Push), bản `aes128gcm`.
- RFC 8188 (khung dữ liệu aes128gcm: salt | rs | idlen | keyid | ciphertext).
- RFC 8292 (VAPID): tự giới thiệu với dịch vụ đẩy bằng JWT ES256 ký bằng khoá riêng của
  chính máy này. Khoá sinh MỘT LẦN rồi giữ ở STATE_DIR - đổi khoá là mọi đăng ký cũ chết,
  nên nó phải sống qua các lần cập nhật Javis.

Bước dẫn khoá (đã đối chiếu với thư viện tham chiếu `http_ece`):
    ecdh   = ECDH(khoá_riêng_tạm, p256dh_của_trình_duyệt)
    ikm    = HKDF(salt=auth, info=b"WebPush: info\\x00" + ua_pub + as_pub, len=32)(ecdh)
    cek    = HKDF(salt=salt, info=b"Content-Encoding: aes128gcm\\x00", len=16)(ikm)
    nonce  = HKDF(salt=salt, info=b"Content-Encoding: nonce\\x00",      len=12)(ikm)

Giới hạn thật, nói trước cho khỏi mất công dò:
- Web Push CHỈ chạy trong secure context: https, hoặc localhost. Javis chạy trần bằng IP
  qua http trong mạng LAN thì trình duyệt không cho đăng ký, không có cách nào lách.
- iOS chỉ đẩy được khi người dùng đã "Thêm vào MH chính" (PWA đã cài), từ iOS 16.4.
"""
from __future__ import annotations

import base64
import json
import os
import struct
import sys
import threading
import time
from pathlib import Path
from urllib.parse import urlsplit

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, utils as asym_utils
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from config import STATE_DIR

VAPID_FILE = STATE_DIR / "vapid.json"
SUBS_FILE = STATE_DIR / "push_subs.json"
_LOCK = threading.RLock()

# Dịch vụ đẩy chỉ bảo đảm nhận nổi 4096 byte SAU khi mã hoá. Phần bọc (salt 16 + rs 4 +
# idlen 1 + khoá 65 + thẻ GCM 16 + byte đệm 1) ăn mất 103 byte, nên chừa rộng tay.
MAX_PLAINTEXT = 3000
TTL_GIAY = 24 * 3600          # trình duyệt tắt máy vẫn nhận được khi bật lại trong ngày
_JWT_SONG_GIAY = 12 * 3600    # RFC 8292 khuyến nghị tối đa 24h; 12h cho thoải mái lệch giờ


def b64u(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def b64u_giai(s) -> bytes:
    t = str(s or "").strip().replace("-", "+").replace("_", "/")
    return base64.b64decode(t + "=" * (-len(t) % 4))


# ============================================================
# Khoá VAPID - sinh một lần, sống mãi ở STATE_DIR
# ============================================================
def _sinh_vapid() -> dict:
    pk = ec.generate_private_key(ec.SECP256R1())
    pem = pk.private_bytes(serialization.Encoding.PEM,
                           serialization.PrivateFormat.PKCS8,
                           serialization.NoEncryption()).decode("ascii")
    pub = pk.public_key().public_bytes(serialization.Encoding.X962,
                                       serialization.PublicFormat.UncompressedPoint)
    return {"private_pem": pem, "public": b64u(pub), "created": time.time()}


def khoa_vapid() -> dict:
    """Cặp khoá VAPID của máy này, sinh ở lần gọi đầu tiên rồi giữ nguyên mãi.

    Đổi khoá = mọi đăng ký đẩy cũ thành rác (dịch vụ đẩy từ chối vì khác `k=`), nên file
    này thuộc loại phải sống qua cập nhật - đó là lý do nó nằm ở STATE_DIR chứ không phải
    trong cây mã nguồn.
    """
    with _LOCK:
        try:
            d = json.loads(VAPID_FILE.read_text(encoding="utf-8"))
            if d.get("private_pem") and d.get("public"):
                return d
        except (OSError, ValueError):
            pass
        d = _sinh_vapid()
        try:
            VAPID_FILE.parent.mkdir(parents=True, exist_ok=True)
            tmp = VAPID_FILE.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
            try:
                os.chmod(tmp, 0o600)     # khoá riêng: đừng để cả máy đọc được
            except OSError:
                pass
            tmp.replace(VAPID_FILE)
        except OSError as e:
            print(f"[webpush] ghi {VAPID_FILE.name} lỗi: {type(e).__name__}: {e}", file=sys.stderr)
        return d


def khoa_cong_khai() -> str:
    return khoa_vapid()["public"]


def lien_he() -> str:
    """Địa chỉ liên hệ đặt vào claim `sub` của JWT VAPID (RFC 8292).

    KHÔNG được để "localhost". RFC nói `sub` phải là mailto: hoặc https: mà nhà cung cấp
    dịch vụ đẩy LIÊN HỆ ĐƯỢC với chủ máy chủ. Google và Mozilla dễ tính, nhận gần như mọi
    chuỗi; **Apple thì soi thật** và trả 400 BadJwtToken cho địa chỉ không ra hồn - nghĩa là
    máy tính (Chrome/FCM) nhận thông báo bình thường còn iPhone thì im lặng tuyệt đối. Đúng
    lỗi chủ repo báo 27/08: bấm Gửi thử trên điện thoại thì máy tính hiện, điện thoại không.

    Đổi được bằng biến môi trường JAVIS_PUSH_CONTACT (mailto:... hoặc https://...) cho ai
    muốn để địa chỉ thật của mình.
    """
    v = str(os.getenv("JAVIS_PUSH_CONTACT") or "").strip()
    if v.startswith("mailto:") or v.startswith("https://"):
        return v
    return "mailto:javis-os@users.noreply.github.com"


def _jwt_vapid(endpoint: str, sub_lien_he: str = None) -> str:
    """JWT ES256 tự giới thiệu với dịch vụ đẩy (RFC 8292).

    Chữ ký PHẢI là r||s thô 64 byte. `cryptography` ký ra DER, nên có bước đổi ở dưới -
    quên bước này thì mọi dịch vụ đẩy trả 401 mà không nói vì sao.
    """
    sub_lien_he = sub_lien_he or lien_he()
    d = khoa_vapid()
    pk = serialization.load_pem_private_key(d["private_pem"].encode("ascii"), password=None)
    p = urlsplit(endpoint)
    aud = f"{p.scheme}://{p.netloc}"
    head = b64u(json.dumps({"typ": "JWT", "alg": "ES256"}, separators=(",", ":")).encode())
    body = b64u(json.dumps({"aud": aud, "exp": int(time.time()) + _JWT_SONG_GIAY,
                            "sub": sub_lien_he}, separators=(",", ":")).encode())
    ky = f"{head}.{body}".encode("ascii")
    der = pk.sign(ky, ec.ECDSA(hashes.SHA256()))
    r, s = asym_utils.decode_dss_signature(der)
    return f"{head}.{body}." + b64u(r.to_bytes(32, "big") + s.to_bytes(32, "big"))


def header_vapid(endpoint: str) -> dict:
    return {"Authorization": f"vapid t={_jwt_vapid(endpoint)}, k={khoa_cong_khai()}"}


# ============================================================
# Mã hoá nội dung (RFC 8291 + RFC 8188)
# ============================================================
def ma_hoa(plaintext: bytes, p256dh: str, auth: str, *,
           salt: bytes = None, khoa_tam=None) -> bytes:
    """Trả về NGUYÊN thân request đã mã hoá cho một đăng ký đẩy.

    `salt` và `khoa_tam` chỉ để test bơm giá trị cố định vào - chạy thật thì luôn ngẫu nhiên,
    và PHẢI ngẫu nhiên: dùng lại cặp (khoá tạm, salt) cho hai tin là lộ khoá dòng.
    """
    ua_pub_raw = b64u_giai(p256dh)
    auth_raw = b64u_giai(auth)
    if len(ua_pub_raw) != 65 or ua_pub_raw[0] != 0x04:
        raise ValueError("p256dh không phải điểm P-256 dạng uncompressed 65 byte")
    if len(auth_raw) != 16:
        raise ValueError("auth secret phải đúng 16 byte")
    if len(plaintext) > MAX_PLAINTEXT:
        plaintext = plaintext[:MAX_PLAINTEXT]

    salt = salt or os.urandom(16)
    priv = khoa_tam or ec.generate_private_key(ec.SECP256R1())
    as_pub = priv.public_key().public_bytes(serialization.Encoding.X962,
                                            serialization.PublicFormat.UncompressedPoint)
    ua_pub = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), ua_pub_raw)
    ecdh = priv.exchange(ec.ECDH(), ua_pub)

    ikm = HKDF(algorithm=hashes.SHA256(), length=32, salt=auth_raw,
               info=b"WebPush: info\x00" + ua_pub_raw + as_pub).derive(ecdh)
    cek = HKDF(algorithm=hashes.SHA256(), length=16, salt=salt,
               info=b"Content-Encoding: aes128gcm\x00").derive(ikm)
    nonce = HKDF(algorithm=hashes.SHA256(), length=12, salt=salt,
                 info=b"Content-Encoding: nonce\x00").derive(ikm)

    # 0x02 = dấu kết thúc bản ghi CUỐI (RFC 8188). Cả tin gói trong MỘT bản ghi nên luôn là 02.
    ct = AESGCM(cek).encrypt(nonce, plaintext + b"\x02", None)
    return salt + struct.pack("!L", 4096) + bytes([len(as_pub)]) + as_pub + ct


def giai_ma(body: bytes, khoa_rieng_ua, auth: str) -> bytes:
    """Giải mã ngược - CHỈ dùng trong test để chứng minh vòng mã hoá đúng thật.

    Không có hàm này thì test chỉ kiểm được "có ra bytes", tức là một lỗi dẫn khoá vẫn
    lọt qua và chỉ lộ ra khi trình duyệt thật im lặng không hiện thông báo nào.
    """
    salt, ct = body[:16], body[21 + body[20]:]
    as_pub_raw = body[21:21 + body[20]]
    ua_pub_raw = khoa_rieng_ua.public_key().public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    ecdh = khoa_rieng_ua.exchange(
        ec.ECDH(), ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), as_pub_raw))
    ikm = HKDF(algorithm=hashes.SHA256(), length=32, salt=b64u_giai(auth),
               info=b"WebPush: info\x00" + ua_pub_raw + as_pub_raw).derive(ecdh)
    cek = HKDF(algorithm=hashes.SHA256(), length=16, salt=salt,
               info=b"Content-Encoding: aes128gcm\x00").derive(ikm)
    nonce = HKDF(algorithm=hashes.SHA256(), length=12, salt=salt,
                 info=b"Content-Encoding: nonce\x00").derive(ikm)
    return AESGCM(cek).decrypt(nonce, ct, None).rstrip(b"\x02")


# ============================================================
# Kho đăng ký của từng trình duyệt
# ============================================================
def _load_subs() -> dict:
    try:
        d = json.loads(SUBS_FILE.read_text(encoding="utf-8"))
        if isinstance(d, dict) and isinstance(d.get("subs"), list):
            return d
    except (OSError, ValueError):
        pass
    return {"version": 1, "subs": []}


def _save_subs(d: dict) -> None:
    try:
        SUBS_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = SUBS_FILE.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(SUBS_FILE)
    except OSError as e:
        print(f"[webpush] ghi {SUBS_FILE.name} lỗi: {type(e).__name__}: {e}", file=sys.stderr)


def dang_ky(sub: dict, nhan: str = "") -> tuple:
    """Ghi nhận MỘT trình duyệt. Trả (ok, lỗi). Trùng endpoint thì CẬP NHẬT, không đẻ thêm.

    Trùng là chuyện bình thường chứ không phải ngoại lệ: mỗi lần mở lại dashboard, trang
    đăng ký lại và trình duyệt trả về đúng endpoint cũ. Không gộp thì mỗi lần F5 đẻ thêm
    một bản ghi và một cái thông báo trùng.
    """
    ep = str((sub or {}).get("endpoint") or "").strip()
    keys = (sub or {}).get("keys") or {}
    p256dh, auth = str(keys.get("p256dh") or ""), str(keys.get("auth") or "")
    if not ep.startswith("https://"):
        return False, "endpoint không hợp lệ"
    if not p256dh or not auth:
        return False, "thiếu khoá p256dh/auth"
    try:
        ma_hoa(b"x", p256dh, auth)      # thử mã hoá NGAY để khoá rác không nằm im tới lúc gửi
    except Exception as e:
        return False, f"khoá không dùng được: {e}"
    with _LOCK:
        d = _load_subs()
        d["subs"] = [s for s in d["subs"] if s.get("endpoint") != ep]
        d["subs"].append({"endpoint": ep, "p256dh": p256dh, "auth": auth,
                          "nhan": str(nhan or "")[:120], "ts": time.time()})
        _save_subs(d)
    return True, ""


def huy_dang_ky(endpoint: str) -> bool:
    with _LOCK:
        d = _load_subs()
        truoc = len(d["subs"])
        d["subs"] = [s for s in d["subs"] if s.get("endpoint") != str(endpoint or "")]
        if len(d["subs"]) == truoc:
            return False
        _save_subs(d)
        return True


def danh_sach_sub() -> list:
    with _LOCK:
        return list(_load_subs().get("subs") or [])


def so_sub() -> int:
    return len(danh_sach_sub())


def _ghi_ket_qua(ep: str, ok: bool, loi: str) -> None:
    """Ghi kết quả lần gửi gần nhất lên chính đăng ký đó.

    Vì sao cần: trước bản này lỗi gửi chỉ in ra stderr, mà không ai đọc log server của máy
    mình. Chủ repo bấm Gửi thử trên điện thoại, máy tính hiện thông báo còn điện thoại im -
    và không có cách nào biết vì sao, vì API vẫn trả ok=true (máy tính gửi được là đủ tính).
    Giữ kết quả theo TỪNG thiết bị thì màn hình nói thẳng được "iPhone: 400 BadJwtToken".
    """
    with _LOCK:
        d = _load_subs()
        for s in d["subs"]:
            if s.get("endpoint") == ep:
                s["lan_cuoi"] = time.time()
                s["ok_lan_cuoi"] = bool(ok)
                s["loi_lan_cuoi"] = str(loi or "")[:200]
                _save_subs(d)
                return


def ten_dich_vu(endpoint: str) -> str:
    """Tên dễ đọc của dịch vụ đẩy, để người dùng nhận ra máy nào là máy nào."""
    host = urlsplit(str(endpoint or "")).netloc.lower()
    if "apple" in host:
        return "Apple (iPhone/iPad/Mac)"
    if "google" in host or "fcm" in host:
        return "Google (Chrome/Android)"
    if "mozilla" in host:
        return "Mozilla (Firefox)"
    if "microsoft" in host or "windows" in host:
        return "Microsoft (Edge)"
    return host or "?"


async def gui_het(tieu_de: str, than: str, url: str = "/", tag: str = "javis") -> tuple:
    """Đẩy MỘT thông báo tới MỌI trình duyệt đã đăng ký. Trả (số_gửi_được, số_bị_dọn, chi_tiết).

    Gửi cho tất cả là cố ý: bật/tắt là việc của từng thiết bị, nên đã bật ở đâu thì ở đó phải
    nhận - bấm Gửi thử trên điện thoại mà chỉ máy tính kêu là sai.

    Dịch vụ đẩy trả 404/410 nghĩa là đăng ký ĐÃ CHẾT (người dùng gỡ app, xoá dữ liệu site).
    Dọn ngay tại chỗ, không thì danh sách phình mãi và mỗi lần báo lại tốn thêm một request
    chắc chắn hỏng. Mọi mã lỗi KHÁC đều được giữ lại trên đăng ký để màn hình nói ra được.
    """
    subs = danh_sach_sub()
    if not subs:
        return 0, 0, []
    payload = json.dumps({"title": tieu_de, "body": than, "url": url, "tag": tag},
                         ensure_ascii=False).encode("utf-8")
    import httpx
    ok, don, chi_tiet = 0, [], []
    async with httpx.AsyncClient(timeout=15) as c:
        for s in subs:
            ep = s["endpoint"]
            muc = {"dich_vu": ten_dich_vu(ep), "nhan": s.get("nhan", ""), "ok": False,
                   "ma": 0, "loi": ""}
            try:
                body = ma_hoa(payload, s["p256dh"], s["auth"])
                h = header_vapid(ep)
                h.update({"Content-Encoding": "aes128gcm", "TTL": str(TTL_GIAY),
                          "Content-Type": "application/octet-stream", "Urgency": "normal"})
                r = await c.post(ep, content=body, headers=h)
                muc["ma"] = r.status_code
                if r.status_code in (404, 410):
                    don.append(ep)
                    muc["loi"] = "đăng ký đã hết hiệu lực - đã dọn"
                elif 200 <= r.status_code < 300:
                    ok += 1
                    muc["ok"] = True
                else:
                    muc["loi"] = (r.text or "").strip()[:200] or f"HTTP {r.status_code}"
                    print(f"[webpush] {r.status_code} từ {urlsplit(ep).netloc}: "
                          f"{muc['loi']}", file=sys.stderr)
            except Exception as e:
                muc["loi"] = f"{type(e).__name__}: {e}"[:200]
                print(f"[webpush] gửi lỗi: {muc['loi']}", file=sys.stderr)
            chi_tiet.append(muc)
            if ep not in don:
                _ghi_ket_qua(ep, muc["ok"], muc["loi"])
    for ep in don:
        huy_dang_ky(ep)
    return ok, len(don), chi_tiet
