"""Kho gói: đọc một file index công khai, cache lại, và hỏng thì hỏng cho tử tế.

Kho là gì trong Javis
---------------------
Đúng một file JSON đặt ở đâu đó công khai (mặc định là repo GitHub của người phát hành). Không
có máy chủ nào phải nuôi, không có cơ sở dữ liệu, không có tài khoản. Người phát hành sửa file
đó là kho đổi.

Vì sao đơn giản đến vậy lại đủ: kho chỉ làm MỘT việc là giúp người dùng TÌM RA gói. Việc khó
(mở gói, kiểm, hỏi, cài, gỡ sạch) đã nằm ở `pack_install`, và nó không quan tâm gói đến từ đâu.

Fetch ở PHÍA SERVER, không ở trình duyệt
----------------------------------------
Ba lý do, xếp theo mức quan trọng: chốt SSRF nằm ở server nên đường tải phải đi qua đó mới được
gác; trình duyệt sẽ vướng CORS với phần lớn nơi đặt file; và về sau nếu có kho riêng cần token
thì token không bao giờ nên rơi vào JavaScript.

Index là DỮ LIỆU KHÔNG TIN ĐƯỢC
-------------------------------
`name` và `description` trong index đi thẳng vào giao diện, và mô tả tool của gói thì đi thẳng
vào danh sách tool của những engine đang cầm Bash. Nên: cắt độ dài, ép kiểu, và không bao giờ
để một trường lạ trong index chui vào chỗ nào có ý nghĩa. `_lam_sach` là chỗ duy nhất quyết
định trường nào được đi tiếp.

Hỏng thì hỏng cho tử tế
-----------------------
Ba trạng thái, không cái nào là một cục lỗi ném vào mặt người dùng: còn cache thì vẫn vẽ được
lưới kèm một dòng nói số liệu đã cũ; không cache thì trạng thái rỗng kèm lời nhắc vẫn cài được
từ tệp; `format_version` lạ thì nói thẳng là kho cần bản Javis mới hơn, chứ không đọc nửa vời
rồi hiện sai.
"""
from __future__ import annotations

import json
import time
from urllib.parse import urljoin

from config import STATE_DIR

CACHE = STATE_DIR / "packs-store-cache.json"
TTL = 6 * 3600
FORMAT = "javis-pack-index"
FORMAT_VERSION = 1

# Kho mặc định. Người dùng đổi được trong Cài đặt, nên đây chỉ là điểm khởi đầu.
#
# Kho nằm ở REPO RIÊNG chứ không trong repo Javis OS, và đó là điểm mấu chốt của cả tầng này:
# thêm một gói vào kho không còn dính gì tới việc ra bản mới của app. Người phát hành đẩy một
# commit vào `javis-store`, và mọi máy đang chạy Javis thấy ngay ở lần làm mới danh mục kế tiếp.
#
# Tách repo còn mở được đường đóng góp: người lạ gửi Pull Request vào kho, chủ kho đọc mã rồi mới
# trộn - mà không ai phải có quyền ghi vào mã nguồn Javis.
STORE_MAC_DINH = ("https://raw.githubusercontent.com/blogminhquy/javis-store/"
                  "main/index.json")

# Loại năng lực một mục trong kho mang lại. Đây là thứ chia lưới thành các tab "Trợ lý /
# Kỹ năng / Quy trình / Công cụ", nên nó là trường quan trọng nhất về mặt trưng bày.
#
# Cùng luật với `tier`: LỜI KHAI của người phát hành, chỉ để lọc và hiện nhãn. Sự thật do
# `pack_install.soi` tính từ tệp đã tải về, và màn hình xác nhận nói theo sự thật đó chứ không
# theo dòng này.
#
# Giá trị lạ rơi về "bundle" chứ KHÔNG bị loại: một thẻ lọc không trúng vẫn tốt hơn một thẻ
# biến mất khỏi kho mà không ai hiểu vì sao. Kho là nơi tìm ra thứ mình cần; giấu đi là hỏng
# đúng việc nó sinh ra để làm.
LOAI = ("agent", "skill", "workflow", "tool", "connector", "bundle")

MAX_MO_TA = 300
MAX_TEN = 120
MAX_GOI = 500


def _chuoi(v, tran=MAX_TEN) -> str:
    return str(v if v is not None else "")[:tran]


def _map_nn(v, tran=MAX_TEN) -> dict:
    """`name`/`description` nhận chuỗi trần hoặc map đa ngôn ngữ. Chuẩn hoá và cắt độ dài."""
    if isinstance(v, dict):
        return {_chuoi(k, 8): _chuoi(x, tran) for k, x in list(v.items())[:12] if x}
    s = _chuoi(v, tran)
    return {"en": s} if s else {}


def _lam_sach(m: dict) -> dict:
    """Giữ đúng những trường Javis biết dùng. Trường lạ bị bỏ, không bao giờ đi tiếp.

    Đây là ranh giới giữa "dữ liệu người khác viết" và "thứ Javis hiển thị"."""
    tai = m.get("download") or {}
    return {
        "id": _chuoi(m.get("id"), 64),
        "name": _map_nn(m.get("name")),
        "description": _map_nn(m.get("description"), MAX_MO_TA),
        "version": _chuoi(m.get("version"), 32),
        "author": {"name": _chuoi((m.get("author") or {}).get("name"), 64)},
        "kind": _chuoi(m.get("kind"), 16) if _chuoi(m.get("kind"), 16) in LOAI else "bundle",
        # Id connector gói này cấp. Kho dùng nó để không hiện HAI thẻ cho cùng một dịch vụ khi
        # app vẫn còn bản của mình. Cắt cả số lượng lẫn độ dài như mọi trường khác: đây vẫn là
        # dữ liệu người lạ viết.
        "provides": {"connectors": [_chuoi(x, 64) for x in
                                    ((m.get("provides") or {}).get("connectors") or [])[:50]
                                    if _chuoi(x, 64)]},
        "category": _chuoi(m.get("category"), 32),
        "category_label": _map_nn(m.get("category_label"), 40),
        # `tier` là thứ người phát hành KHAI, chỉ để lọc và để hiện nhãn. Bậc THẬT do trình cài
        # tự tính từ tệp đã tải về - xem `pack_install.soi`. Khai một đằng đóng gói một nẻo thì
        # màn hình xác nhận vẫn nói đúng sự thật.
        "tier": "code" if str(m.get("tier")) == "code" else "data",
        "verified": bool(m.get("verified")),
        "updated": _chuoi(m.get("updated"), 32),
        "homepage": _chuoi(m.get("homepage"), 300),
        "download": {"url": _chuoi(tai.get("url"), 500),
                     "sha256": _chuoi(tai.get("sha256"), 64),
                     "size": int(tai.get("size") or 0) if str(tai.get("size") or "0").isdigit() else 0},
        # Để dành cho gói bán tiền sau này: có mặt từ v1 để lúc đó chỉ là một nút, không phải
        # một lần phá định dạng.
        "listing": {"price": (m.get("listing") or {}).get("price") or {},
                    "purchase_url": _chuoi((m.get("listing") or {}).get("purchase_url"), 300)},
    }


def _doc_cache() -> dict:
    try:
        d = json.loads(CACHE.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def _ghi_cache(d: dict) -> None:
    try:
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        tmp = CACHE.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
        tmp.replace(CACHE)
    except OSError:
        pass


def url_kho() -> str:
    try:
        import config as cfgmod
        u = ((cfgmod.read_settings().get("packs") or {}).get("store_url") or "").strip()
        return u or STORE_MAC_DINH
    except Exception:
        return STORE_MAC_DINH


async def lay(lam_moi: bool = False) -> dict:
    """Danh sách gói trong kho. Trả {ok, packs, store, stale, error, fetched_at}.

    `stale=True` nghĩa là đang vẽ bằng số liệu cũ vì lần lấy mới thất bại. Phải nói ra chứ
    không im lặng vẽ như thường: người dùng cần biết mình đang nhìn cái gì."""
    cache = _doc_cache()
    con_han = (time.time() - float(cache.get("fetched_at") or 0)) < TTL
    if cache.get("packs") and con_han and not lam_moi:
        return {"ok": True, "packs": cache["packs"], "store": cache.get("store") or {},
                "stale": False, "fetched_at": cache.get("fetched_at"), "url": url_kho()}

    import packs_fetch
    u = url_kho()
    try:
        raw = await packs_fetch.tai(u, tran=4 * 1024 * 1024)
        d = json.loads(raw.decode("utf-8"))
        if not isinstance(d, dict):
            raise ValueError("gốc phải là object")
        if str(d.get("format")) != FORMAT:
            raise ValueError("tệp này không phải danh mục gói của Javis")
        fv = int(d.get("format_version") or 0)
        if fv > FORMAT_VERSION:
            # Đọc nửa vời một định dạng mới hơn là cách chắc chắn để hiện sai. Nói thẳng.
            raise ValueError(f"kho này cần bản Javis mới hơn (định dạng v{fv})")
        goi = [_lam_sach(x) for x in (d.get("packs") or [])[:MAX_GOI] if isinstance(x, dict)]
        # Mục thiếu id hoặc thiếu chỗ tải thì bỏ: hiện một thẻ bấm vào không cài được thì tệ
        # hơn là không hiện.
        goi = [g for g in goi if g["id"] and g["download"]["url"]]
        for g in goi:
            if not g["download"]["url"].startswith("https://"):
                g["download"]["url"] = urljoin(u, g["download"]["url"])
        store = {"name": _chuoi((d.get("store") or {}).get("name"), 80),
                 "url": _chuoi((d.get("store") or {}).get("url"), 300)}
        _ghi_cache({"fetched_at": time.time(), "packs": goi, "store": store, "url": u})
        return {"ok": True, "packs": goi, "store": store, "stale": False,
                "fetched_at": time.time(), "url": u}
    except Exception as e:
        loi = str(e) or type(e).__name__
        if cache.get("packs"):
            return {"ok": True, "packs": cache["packs"], "store": cache.get("store") or {},
                    "stale": True, "error": loi, "fetched_at": cache.get("fetched_at"), "url": u}
        return {"ok": False, "packs": [], "store": {}, "stale": False, "error": loi, "url": u}
