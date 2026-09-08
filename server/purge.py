"""Xoá một kết nối cho SẠCH: mọi thứ nó từng ghi ra đĩa, đúng thứ tự, có chốt an toàn.

Vì sao là một module riêng
--------------------------
Trước file này, câu hỏi "một kết nối có thể để lại những gì" không có ai trả lời. Mỗi chỗ ghi
tự ghi, còn `/connect/delete` thì gọi bốn hàm dọn rồi coi như xong. Kết quả đo được ngày
2026-09-03 trên máy chủ repo: 5 thư mục `connector-home/zalo-*` mồ côi trong khi không còn một
kết nối Zalo nào, một trong số đó vẫn giữ credential phiên đăng nhập. Tức là "xoá kết nối" để
lại đúng thứ mà người dùng bấm nút để loại bỏ.

Ba lỗi cụ thể đã sửa ở đây:

1. **Tiến trình con sống thêm 15 phút.** `/connect/delete` gọi `mcp_store.delete_connection`
   TRƯỚC rồi mới `mcp_hub.invalidate_cache`, mà `invalidate_cache` lại đi vòng qua
   `list_connections()` để tìm phiên cần đóng. Hàng đã bị xoá nên phiên của chính nó không bao
   giờ được đóng, và nó sống tới `mcp_client._IDLE_TTL` = 900 giây. `/connect/relogin` ngay
   dưới đó lại làm đúng - nó gọi `pool.invalidate(cid)`. Chỉ đường xoá là quên.

2. **`connector-home/` không có ai xoá.** Hai chỗ ghi (`mcp_store.resolved` và
   `zalo_login.start`), không chỗ nào xoá. Tệ hơn: hai chỗ đó đặt tên theo HAI DẠNG khác nhau
   (`<connector_id>-<slug>` và `zalo-<slug>-<sid6>`), nên suy đường dẫn từ id với slug là bỏ
   sót đúng những thư mục do quét QR tạo ra, tức đúng những thư mục chứa credential.

3. **Sổ năng lực chỉ xoá mềm.** `capability_registry` đặt `active=0`, và chỉ khi có ai refresh
   đúng brain đó. Tên tool của một kết nối đã xoá nằm lại trong chỉ mục FTS vô thời hạn.

Nguyên tắc thứ tự: LÀM IM trước, XOÁ sau
----------------------------------------
Phải chờ tiến trình stdio chết hẳn TRƯỚC khi rmtree thư mục home của nó. Còn sống là còn giữ
khoá trên file bên trong: trên Windows thì xoá trượt, trên POSIX thì xoá NỬA VỜI, và cả hai
đều im lặng. Đó là lý do `mcp_client.SessionPool.close_now` tồn tại bên cạnh `invalidate` vốn
bắn-rồi-quên.

Nguyên tắc an toàn: mọi đường dẫn đi qua `_ben_trong`
----------------------------------------------------
`config.home_dir` do NGƯỜI DÙNG đặt được qua `POST /connect/update`. Không có chốt thì "xoá kết
nối" là một lệnh rmtree trỏ đi đâu cũng được.
"""
from __future__ import annotations

import json
import shutil
import sys
import time
from pathlib import Path

from config import STATE_DIR

TRASH_DIR = STATE_DIR / "purge-trash"
HOME_DIR = STATE_DIR / "connector-home"
CRED_DIR = STATE_DIR / "connector-cred"
FILES_DIR = STATE_DIR / "connector-files"

# Bao lâu thì dọn hẳn thứ đã chuyển vào thùng rác.
TRASH_DAYS = 30


def _ben_trong(p: Path, base: Path) -> bool:
    """`p` có thật sự nằm trong `base` không, sau khi đã đi hết symlink.

    Gọi `resolve()` ở CẢ HAI vế là phần quan trọng: chỉ resolve một vế thì một symlink
    `connector-home/x` trỏ ra ngoài vẫn lọt."""
    try:
        r, b = p.resolve(), base.resolve()
    except OSError:
        return False
    return r == b or b in r.parents


def _an_toan_de_xoa(p: Path, base: Path) -> bool:
    """Chốt cuối trước mọi rmtree: nằm trong base, và KHÔNG phải chính base."""
    if not p or not _ben_trong(p, base):
        return False
    try:
        return p.resolve() != base.resolve()
    except OSError:
        return False


def _thu_muc_home(conn: dict) -> list[Path]:
    """Mọi thư mục home cô lập có thể thuộc về connection này.

    Đọc `config.home_dir` TRƯỚC vì đó là đường dẫn thật đã dùng lúc chạy (`mcp_store.resolved`
    coi nó là nguồn chân lý). Rồi mới quét thêm theo TIỀN TỐ, vì `zalo_login` đặt tên dạng
    `zalo-<slug>-<sid6>` chứ không phải `<connector_id>-<slug>`: chỉ suy theo công thức là bỏ
    sót đúng loại thư mục có credential.
    """
    ra: list[Path] = []
    khai = ((conn.get("config") or {}).get("home_dir") or "").strip()
    if khai:
        p = Path(khai)
        if _an_toan_de_xoa(p, HOME_DIR):
            ra.append(p)
        else:
            # Người dùng trỏ home ra ngoài vùng Javis quản. Không đụng, nhưng phải NÓI RA
            # thay vì im lặng bỏ qua, kẻo họ tưởng đã xoá.
            print(f"[purge] bo qua home ngoai vung: {khai}", file=sys.stderr)
    cid = conn.get("connector_id") or ""
    slug = conn.get("slug") or ""
    if cid and slug and HOME_DIR.is_dir():
        for p in HOME_DIR.glob(f"{cid}-{slug}*"):
            if p.is_dir() and _an_toan_de_xoa(p, HOME_DIR) and p not in ra:
                ra.append(p)
    return ra


def _thu_muc_cred(conn: dict) -> Path | None:
    cid, slug = conn.get("connector_id") or "", conn.get("slug") or conn.get("id") or ""
    if not cid:
        return None
    p = CRED_DIR / f"{cid}-{slug}"
    return p if (p.is_dir() and _an_toan_de_xoa(p, CRED_DIR)) else None


def _tep_secret(cid: str) -> list[Path]:
    if not cid or not FILES_DIR.is_dir():
        return []
    return [p for p in FILES_DIR.glob(f"{cid}-*") if _an_toan_de_xoa(p, FILES_DIR)]


def _co(p: Path) -> int:
    """Dung lượng một file hoặc cả cây thư mục, tính bằng byte. Lỗi thì trả 0."""
    try:
        if p.is_file():
            return p.stat().st_size
        return sum(f.stat().st_size for f in p.rglob("*") if f.is_file())
    except OSError:
        return 0


def plan_connection(cid: str) -> dict:
    """Liệt kê ĐÚNG những gì `purge_connection` sẽ xoá, và không xoá gì cả.

    Hộp xác nhận trên giao diện vẽ từ chính kết quả này, để lời cảnh báo không bao giờ trôi
    lệch khỏi việc thật sự làm - hai thứ đó viết rời nhau là kiểu chắc chắn lệch sau vài tháng.
    """
    import mcp_catalog
    import mcp_client
    import mcp_hub
    import mcp_store

    conn = mcp_store.get_connection(cid)
    if not conn:
        return {"ok": False, "error": "Không tìm thấy kết nối"}

    con = mcp_catalog.get(conn.get("connector_id")) or {}
    homes = _thu_muc_home(conn)
    cred = _thu_muc_cred(conn)
    files = _tep_secret(cid)
    muc: list[dict] = [{"kind": "connection", "label": "Kết nối và khoá đã lưu", "n": 1}]
    if conn.get("secrets"):
        muc.append({"kind": "secrets", "label": "Khoá hoặc mật khẩu đã mã hoá",
                    "n": len(conn.get("secrets") or {})})
    if homes:
        muc.append({"kind": "home", "label": "Phiên đăng nhập riêng của kết nối",
                    "n": len(homes), "bytes": sum(_co(p) for p in homes),
                    "paths": [str(p) for p in homes]})
    if cred:
        muc.append({"kind": "cred", "label": "Kho token connector tự giữ",
                    "n": 1, "bytes": _co(cred), "paths": [str(cred)]})
    if files:
        muc.append({"kind": "files", "label": "Tệp bí mật đã ghi ra đĩa",
                    "n": len(files), "bytes": sum(_co(p) for p in files)})
    try:
        n_audit = len(mcp_hub.audit_tail(limit=100000, conn_id=cid))
    except Exception:
        n_audit = 0
    if n_audit:
        muc.append({"kind": "audit", "label": "Dòng nhật ký gọi tool", "n": n_audit,
                    "note": "Mặc định GIỮ LẠI, chỉ xoá tên hiển thị."})

    return {
        "ok": True,
        "id": cid,
        "label": conn.get("label") or cid,
        "connector_id": conn.get("connector_id"),
        "connector_name": con.get("name") or conn.get("connector_id"),
        # Cảnh báo nằm trong CATALOG chứ không viết cứng trong JS: nó là tính chất của
        # connector (quét QR mất là mất thật), nên nó phải đi cùng connector.
        "warning": con.get("purge_warning") or "",
        "busy": mcp_client.pool.dang_ban_theo_key(cid),
        "items": muc,
    }


async def purge_connection(cid: str, *, mode: str = "trash", purge_audit: bool = False) -> dict:
    """Xoá kết nối và mọi dấu vết của nó. Thứ tự cố định, xem docstring đầu file.

    `mode="trash"` chuyển thư mục có credential vào `purge-trash/` (dọn hẳn sau 30 ngày) thay
    vì xoá ngay: quét lại QR Zalo là việc phải cầm điện thoại, nên một cú bấm nhầm không đáng
    phải trả giá đó. `mode="hard"` xoá thẳng.
    """
    import capability_registry
    import connect_health
    import mcp_client
    import mcp_hub
    import mcp_store
    import oauth_mcp

    conn = mcp_store.get_connection(cid)
    if not conn:
        return {"ok": False, "error": "Không tìm thấy kết nối"}

    # 1. LÀM IM. Chờ thật, không bắn-rồi-quên: bước 2 sắp dời đi thư mục mà tiến trình này
    #    đang giữ khoá. Đang chạy dở một tool call thì DỪNG LẠI - đóng phiên stdio là giết cả
    #    cây tiến trình, có thể đang đặt một cái đơn thật.
    if mcp_client.pool.dang_ban_theo_key(cid):
        return {"ok": False, "busy": True,
                "error": "Kết nối đang chạy dở một việc. Chờ nó xong rồi xoá."}
    da_dong = await mcp_client.pool.close_now(cid)

    bao_cao: dict = {"ok": True, "id": cid, "label": conn.get("label") or cid,
                     "closed_session": da_dong, "moved": [], "removed": [], "kept": []}

    # 2. CHỤP LẠI (chỉ khi mode="trash"): dời thư mục có credential sang thùng rác kèm phiếu
    #    ghi nó vốn ở đâu, để còn khôi phục được.
    homes = _thu_muc_home(conn)
    cred = _thu_muc_cred(conn)
    can_don = [p for p in homes + ([cred] if cred else []) if p.exists()]
    if mode == "trash" and can_don:
        kho = TRASH_DIR / f"conn-{cid}__{int(time.time())}"
        try:
            kho.mkdir(parents=True, exist_ok=True)
            ghi = []
            for p in can_don:
                dich = kho / p.name
                shutil.move(str(p), str(dich))
                ghi.append({"from": str(p), "to": str(dich)})
                bao_cao["moved"].append(str(p))
            (kho / "manifest.json").write_text(json.dumps(
                {"conn_id": cid, "label": conn.get("label"),
                 "connector_id": conn.get("connector_id"), "ts": time.time(), "paths": ghi},
                ensure_ascii=False, indent=1), encoding="utf-8")
        except OSError as e:
            print(f"[purge] chuyen vao thung rac that bai, xoa thang: {e}", file=sys.stderr)
            mode = "hard"
    if mode != "trash":
        for p in can_don:
            if not p.exists():
                continue
            try:
                shutil.rmtree(p, ignore_errors=True)
                bao_cao["removed"].append(str(p))
            except OSError as e:
                print(f"[purge] rmtree {p}: {e}", file=sys.stderr)

    # 3. GỠ mọi thứ còn lại. Mỗi cái một try riêng: một chỗ hỏng không được phép chặn phần còn
    #    lại, vì dừng giữa chừng để lại đúng cái tình trạng nửa vời đang muốn chấm dứt.
    for ten, viec in (
        ("oauth", lambda: oauth_mcp.forget(cid)),
        ("health", lambda: connect_health.forget(cid)),
        ("rate", lambda: mcp_hub.forget_rate(cid)),
        ("registry", lambda: capability_registry.get_registry().drop_connection(cid)),
        # delete_connection tự lo connector-files/<cid>-* và cred dir; gọi SAU khi đã chụp.
        ("store", lambda: mcp_store.delete_connection(cid)),
    ):
        try:
            viec()
            bao_cao["removed"].append(ten)
        except Exception as e:
            print(f"[purge] {ten}: {type(e).__name__}: {e}", file=sys.stderr)
            bao_cao.setdefault("errors", []).append(f"{ten}: {e}")

    # Nhật ký: mặc định GIỮ, chỉ bỏ nhãn. Xem docstring `mcp_hub.audit_scrub`.
    try:
        n = mcp_hub.audit_scrub(cid, drop=bool(purge_audit))
        (bao_cao["removed"] if purge_audit else bao_cao["kept"]).append(f"audit:{n}")
    except Exception as e:
        print(f"[purge] audit: {e}", file=sys.stderr)

    # 4. LÀM MỚI. Sau khi hàng đã biến mất, để lần dò tool kế tiếp dựng lại bảng route.
    try:
        mcp_hub.invalidate_cache()
    except Exception as e:
        print(f"[purge] invalidate: {e}", file=sys.stderr)

    return bao_cao


def gc_trash(days: int = TRASH_DAYS) -> int:
    """Dọn hẳn thứ đã nằm trong thùng rác quá `days` ngày. Trả về số thư mục đã xoá."""
    if not TRASH_DIR.is_dir():
        return 0
    han = time.time() - days * 86400
    n = 0
    for p in list(TRASH_DIR.iterdir()):
        try:
            if p.is_dir() and p.stat().st_mtime < han and _an_toan_de_xoa(p, TRASH_DIR):
                shutil.rmtree(p, ignore_errors=True)
                n += 1
        except OSError:
            continue
    return n
