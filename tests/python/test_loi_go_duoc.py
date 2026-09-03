"""Năng lực MẶC ĐỊNH của Javis phải gỡ được, và gỡ phải nghĩa là IM chứ không phải tự do.

    python tests/run.py loi_go_duoc

Không cần pytest, không chạm mạng, không đụng `core-off.json` thật.

Bối cảnh: chủ dự án chốt 2026-09-03 rằng đích đến là "bao giờ có kho thì xoá bớt, để lại đúng
cấu trúc mặc định của Javis, còn lại người dùng tự chọn cài thêm plugin, skill hay kết nối", và
bây giờ thì "tạm thời vẫn giữ những gì có trong kho nhưng code lại để đúng cấu trúc có thể gỡ
được". Nên bản này làm LỚP GỠ, không di trú dữ liệu: `system/mcp-catalog.json` không bị sửa một
byte nào, còn danh sách đã gỡ nằm ở `STATE_DIR/core-off.json`.

Ba chỗ dễ làm sai, và test canh cả ba:

1. LỌC ĐÚNG TẦNG. Lọc ở `public_catalog()` thì thẻ mất khỏi giao diện nhưng tool vẫn đi ra tới
   engine qua `mcp_store.resolved` -> `mcp_hub.discover_all`, tức "đã gỡ" là lời hứa sai.
   `mcp_catalog.load()` là nơi duy nhất mọi đường đi qua.

2. GỠ PHẢI NGHĨA LÀ IM. Thiếu connector, `resolved()` cũ vẫn dựng dial spec nhưng bỏ header và
   env, và `mcp_hub._guard` gọi `mcp_catalog.allowed(None, "full", ...)` - hàm đó trả True vô
   điều kiện khi mức hiệu lực là full. Tức gỡ một connector lại làm MẤT cổng chặn tool ghi của
   những kết nối theo nó.

3. `custom` KHÔNG phải mồ côi. Connector do người dùng tự khai không bao giờ có trong catalog,
   nên chốt mồ côi phải tha nó ra, nếu không thì mọi kết nối "Tự thêm (nâng cao)" chết sạch.
"""
from _paths import ROOT, SERVER, DASHBOARD  # noqa: E402,F401
import json
import sys
import tempfile
from pathlib import Path

import core_off
import mcp_catalog
import mcp_store

_fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)


CATALOG = ROOT / "system" / "mcp-catalog.json"
truoc_khi_chay = CATALOG.read_bytes()

with tempfile.TemporaryDirectory() as td:
    goc_store = core_off.STORE
    core_off.STORE = Path(td) / "core-off.json"
    core_off._cache.update(sig=None, data={})
    mcp_catalog._cache.update(sig=None, by_id={})
    try:
        # ─────────────── 1. Sổ đã gỡ: ghi, đọc, xoay vòng ───────────────
        check("chưa gỡ gì thì tập rỗng", core_off.da_go("connectors") == set())
        check("chưa có file thì chữ ký là None", core_off.signature() is None)
        core_off.dat("connectors", "tiktok-ads", True)
        check("gỡ rồi thì có trong sổ", core_off.la_da_go("connectors", "tiktok-ads"))
        check("và file được tạo ra ở STATE_DIR", core_off.STORE.is_file())
        check("chữ ký đổi sau khi ghi", core_off.signature() is not None)
        core_off.dat("connectors", "lark", True)
        check("gỡ cái thứ hai thì cả hai cùng nằm trong sổ",
              core_off.da_go("connectors") == {"tiktok-ads", "lark"})
        core_off.dat("connectors", "tiktok-ads", False)
        check("cài lại thì rời khỏi sổ", core_off.da_go("connectors") == {"lark"})
        check("cài lại thứ chưa từng gỡ cũng không nổ",
              core_off.dat("connectors", "khong-ton-tai", False) is False)
        try:
            core_off.dat("skills", "x", True)
            check("loại lạ phải bị từ chối", False)
        except ValueError:
            check("loại lạ phải bị từ chối", True)

        # File hỏng -> coi như CHƯA GỠ GÌ. Suy biến phải nghiêng về "thấy đủ năng lực" chứ
        # không phải "Javis đột nhiên trống rỗng".
        core_off.STORE.write_text("{ khong phai json", encoding="utf-8")
        core_off._cache.update(sig=None, data={})
        check("file hỏng thì coi như chưa gỡ gì, KHÔNG phải gỡ hết",
              core_off.da_go("connectors") == set())

        # ─────────────── 2. Catalog lọc đúng tầng ───────────────
        core_off.STORE.unlink()
        core_off._cache.update(sig=None, data={})
        mcp_catalog._cache.update(sig=None, by_id={})
        tong = len(mcp_catalog.tat_ca())
        check(f"kho có {tong} connector", tong >= 29)
        check("load() ban đầu thấy đủ", len(mcp_catalog.load()) == tong)

        core_off.dat("connectors", "tiktok-ads", True)
        check("load() trừ cái đã gỡ", len(mcp_catalog.load()) == tong - 1)
        check("get() cái đã gỡ trả None", mcp_catalog.get("tiktok-ads") is None)
        check("tat_ca() VẪN thấy nó (để vẽ khu Đã gỡ)", "tiktok-ads" in mcp_catalog.tat_ca())
        pub = {c["id"] for c in mcp_catalog.public_catalog()}
        check("public_catalog cũng không còn nó (vì nó đọc qua load)", "tiktok-ads" not in pub)
        check("match_url không còn khớp connector đã gỡ",
              (mcp_catalog.match_url("https://business-api.tiktok.com/x") or {}).get("id")
              != "tiktok-ads")

        # Cache phải đổi theo sổ, không chỉ theo mtime file catalog. Thiếu vế này thì gỡ một
        # connector sẽ không có hiệu lực cho tới khi ai đó sửa file catalog, tức là không bao giờ.
        core_off.dat("connectors", "tiktok-ads", False)
        check("cài lại có hiệu lực NGAY, không cần sửa file catalog",
              mcp_catalog.get("tiktok-ads") is not None)

        # ─────────────── 3. Chốt mồ côi ───────────────
        goc_load = mcp_store._load

        def _gia():
            return {"version": 2, "connections": [
                {"id": "c-loi", "connector_id": "tiktok-ads", "slug": "a", "label": "TikTok A",
                 "enabled": True, "perm": "full"},
                {"id": "c-custom", "connector_id": "custom", "slug": "tu-khai",
                 "label": "Tự khai", "enabled": True, "perm": "full",
                 "transport": "http", "url": "https://vi-du.dev/mcp"},
                {"id": "c-la", "connector_id": "khong-he-ton-tai", "slug": "b",
                 "label": "Nguồn lạ", "enabled": True, "perm": "full"},
            ]}

        mcp_store._load = _gia
        try:
            ids = {c["id"] for c in mcp_store.resolved(enabled_only=False)}
            check("kết nối theo connector CÒN trong kho thì vẫn chạy", "c-loi" in ids)
            check("kết nối 'Tự thêm' KHÔNG bị coi là mồ côi (nếu sai thì mọi custom chết sạch)",
                  "c-custom" in ids)
            check("kết nối trỏ vào connector không tồn tại thì KHÔNG được dựng dial spec",
                  "c-la" not in ids)

            mc = {o["id"]: o for o in mcp_store.orphans()}
            check("orphans() nêu đúng cái lạ", set(mc) == {"c-la"})
            check("và nói rõ nó KHÔNG có trong kho (phải cập nhật app, không phải cài lại)",
                  mc["c-la"]["co_trong_kho"] is False)

            # Gỡ tiktok-ads -> kết nối theo nó thành mồ côi và phải IM.
            core_off.dat("connectors", "tiktok-ads", True)
            ids2 = {c["id"] for c in mcp_store.resolved(enabled_only=False)}
            check("gỡ connector thì kết nối theo nó DỪNG chạy", "c-loi" not in ids2)
            check("nhưng kết nối 'Tự thêm' không bị ảnh hưởng", "c-custom" in ids2)
            mc2 = {o["id"]: o for o in mcp_store.orphans()}
            check("orphans() nêu nó", "c-loi" in mc2)
            check("và nói rõ CÓ trong kho, tức cài lại là chạy tiếp",
                  mc2["c-loi"]["co_trong_kho"] is True)
            core_off.dat("connectors", "tiktok-ads", False)
            check("cài lại thì kết nối chạy tiếp, không phải đấu lại",
                  "c-loi" in {c["id"] for c in mcp_store.resolved(enabled_only=False)})
        finally:
            mcp_store._load = goc_load
    finally:
        core_off.STORE = goc_store
        core_off._cache.update(sig=None, data={})
        mcp_catalog._cache.update(sig=None, by_id={})

# ─────────────── 4. Không di trú dữ liệu: catalog gốc không bị sửa ───────────────
check("system/mcp-catalog.json KHÔNG bị sửa một byte nào trong cả vòng gỡ và cài lại",
      CATALOG.read_bytes() == truoc_khi_chay)

# ─────────────── 5. Canary: lọc phải ở load(), và trạng thái ở STATE_DIR ───────────────
src_cat = (SERVER / "mcp_catalog.py").read_text(encoding="utf-8")
i_load = src_cat.index("def load()")
i_sau = src_cat.index("def tat_ca()")
check("việc lọc nằm trong load(), không phải ở chỗ hiển thị",
      "_da_go()" in src_cat[i_load:i_sau])
check("tat_ca() KHÔNG lọc (nó phục vụ khu Đã gỡ)",
      "_da_go()" not in src_cat[i_sau:i_sau + 700])

src_off = (SERVER / "core_off.py").read_text(encoding="utf-8")
check("sổ đã gỡ nằm ở STATE_DIR, không sửa vào cây code",
      'STORE = STATE_DIR / "core-off.json"' in src_off)
check("ghi bằng tmp + replace (một lần ghi bị cắt không được làm hỏng file)",
      ".json.tmp" in src_off and "tmp.replace(STORE)" in src_off)

src_store = (SERVER / "mcp_store.py").read_text(encoding="utf-8")
i_res = src_store.index("def resolved(")
than = src_store[i_res:i_res + 3000]
check("chốt mồ côi tha 'custom' ra một cách tường minh",
      'c["connector_id"] != "custom"' in than)

src_main = (SERVER / "main.py").read_text(encoding="utf-8")
check("có endpoint gỡ / cài lại", '@app.post("/connect/core-toggle")' in src_main)
i_ep = src_main.index('@app.post("/connect/core-toggle")')
than_ep = src_main[i_ep:i_ep + 2000]
check("gỡ mà đang có kết nối thì phải hỏi lại, không làm âm thầm",
      "need_confirm" in than_ep)
check("và làm mới cache hub sau khi đổi", "mcp_hub.invalidate_cache()" in than_ep)
check("/connect/catalog trả cả danh sách đã gỡ và mồ côi",
      '"removed"' in src_main and '"orphans": mcp_store.orphans()' in src_main)

src_js = (DASHBOARD / "console.js").read_text(encoding="utf-8")
check("giao diện có nút gỡ và nút cài lại",
      "data-coreoff" in src_js and "data-coreon" in src_js)
check("và có băng báo kết nối đang dừng vì thiếu dịch vụ", "banMoCoi" in src_js)
check("thẻ 'Tự thêm' không có nút gỡ", 'con.id === "custom" ? ""' in src_js)

if _fails:
    print(f"\nFAIL - test_loi_go_duoc: {len(_fails)} lỗi: {_fails}")
    sys.exit(1)
print("\nOK - test_loi_go_duoc: tất cả pass")
