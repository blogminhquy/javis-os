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
        core_off.dat("connectors", "composio", True)
        check("gỡ rồi thì có trong sổ", core_off.la_da_go("connectors", "composio"))
        check("và file được tạo ra ở STATE_DIR", core_off.STORE.is_file())
        check("chữ ký đổi sau khi ghi", core_off.signature() is not None)
        core_off.dat("connectors", "gmail", True)
        check("gỡ cái thứ hai thì cả hai cùng nằm trong sổ",
              core_off.da_go("connectors") == {"composio", "gmail"})
        core_off.dat("connectors", "composio", False)
        check("cài lại thì rời khỏi sổ", core_off.da_go("connectors") == {"gmail"})
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
        # KHÔNG chốt con số: 0.55.36 dọn 16 khuôn sang kho và còn dọn nữa. Cái
        # đáng canh là catalog nạp được và không rỗng, không phải nó có mấy mục.
        check(f"kho có {tong} connector", tong >= 8)
        check("load() ban đầu thấy đủ", len(mcp_catalog.load()) == tong)

        core_off.dat("connectors", "composio", True)
        check("load() trừ cái đã gỡ", len(mcp_catalog.load()) == tong - 1)
        check("get() cái đã gỡ trả None", mcp_catalog.get("composio") is None)
        check("tat_ca() VẪN thấy nó (để vẽ khu Đã gỡ)", "composio" in mcp_catalog.tat_ca())
        pub = {c["id"] for c in mcp_catalog.public_catalog()}
        check("public_catalog cũng không còn nó (vì nó đọc qua load)", "composio" not in pub)
        check("match_url không còn khớp connector đã gỡ",
              (mcp_catalog.match_url("https://connect.composio.dev/mcp") or {}).get("id")
              != "composio")

        # Cache phải đổi theo sổ, không chỉ theo mtime file catalog. Thiếu vế này thì gỡ một
        # connector sẽ không có hiệu lực cho tới khi ai đó sửa file catalog, tức là không bao giờ.
        core_off.dat("connectors", "composio", False)
        check("cài lại có hiệu lực NGAY, không cần sửa file catalog",
              mcp_catalog.get("composio") is not None)

        # ─────────────── 3. Chốt mồ côi ───────────────
        goc_load = mcp_store._load

        def _gia():
            return {"version": 2, "connections": [
                {"id": "c-loi", "connector_id": "composio", "slug": "a", "label": "Composio A",
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
            check("và nói rõ nó KHÔNG có trong kho (phải cài từ Javis Store, không phải cài lại)",
                  mc["c-la"]["co_trong_kho"] is False)

            # Gỡ composio -> kết nối theo nó thành mồ côi và phải IM.
            core_off.dat("connectors", "composio", True)
            ids2 = {c["id"] for c in mcp_store.resolved(enabled_only=False)}
            check("gỡ connector thì kết nối theo nó DỪNG chạy", "c-loi" not in ids2)
            check("nhưng kết nối 'Tự thêm' không bị ảnh hưởng", "c-custom" in ids2)
            mc2 = {o["id"]: o for o in mcp_store.orphans()}
            check("orphans() nêu nó", "c-loi" in mc2)
            check("và nói rõ CÓ trong kho, tức cài lại là chạy tiếp",
                  mc2["c-loi"]["co_trong_kho"] is True)
            core_off.dat("connectors", "composio", False)
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
# Nhánh XEM TRƯỚC (`plan`) phải TRẢ VỀ trước khi có bất kỳ lần ghi nào.
#
# Vì sao đây là thứ đáng canh: trước 0.55.36 giao diện chỉ biết "cái gì sắp dừng" bằng cách
# gọi thẳng lệnh gỡ rồi đọc lỗi 409. Với connector CHƯA có kết nối nào - tức ca thường - lần
# gọi đó gỡ luôn, xong mới tới lượt hỏi. Một cú bấm nhầm vào dấu × ở góc thẻ là dịch vụ biến
# mất, không ai hỏi câu nào. Thứ tự trong hàm chính là bất biến giữ điều đó.
check("có nhánh xem trước không đụng gì", '"plan": True' in than_ep)
check("CANARY: nhánh xem trước nằm TRƯỚC lệnh ghi sổ",
      than_ep.index('"plan": True') < than_ep.index("core_off.dat("))
check("và làm mới cache hub sau khi đổi", "mcp_hub.invalidate_cache()" in than_ep)
check("/connect/catalog trả cả danh sách đã gỡ và mồ côi",
      '"removed"' in src_main and '"orphans": mcp_store.orphans()' in src_main)

src_js = (DASHBOARD / "console.js").read_text(encoding="utf-8")
check("giao diện có nút gỡ và nút cài lại",
      "data-coreoff" in src_js and "data-coreon" in src_js)
check("và có băng báo kết nối đang dừng vì thiếu dịch vụ", "banMoCoi" in src_js)
# Kết nối mồ côi vì khuôn đã dọn sang kho (0.55.36 dọn 16 cái) phải được chỉ ĐÚNG đường về.
# Câu cũ xui người dùng nâng cấp app hoặc bỏ kết nối đi. Từ nay câu đó vừa sai (nâng cấp
# không mọc lại khuôn nữa) vừa nguy hiểm (bỏ kết nối là vứt luôn credential đã đấu).
check("mồ côi vì khuôn ra kho thì chỉ sang Javis Store, không xui xoá kết nối",
      "Javis Store" in src_js and "data-mocoi" in src_js)
check("CANARY: không còn xui người dùng xoá kết nối để chữa mồ côi",
      "cập nhật app, hoặc xoá kết nối" not in src_js)
check("thẻ 'Tự thêm' không có nút gỡ", 'con.id === "custom" ? ""' in src_js)

# Trang Kết nối tách hai tab từ 0.55.32. Nó vốn gộp "thứ đang chạy" và "thứ đấu thêm được" vào
# một mạch cuộn, nên người đã đấu vài chục tài khoản phải cuộn hết đống đó mới tới chỗ đấu mới.
check("trang Kết nối có hai khối tách rời",
      'id="mcpTabDaNoi"' in src_js and 'id="mcpTabSanCo"' in src_js)
# Ẩn chứ KHÔNG bỏ khỏi DOM: phần dây nối bên dưới tìm theo id và chạy MỘT lần cho cả hai khối.
# Vẽ lẻ từng khối là mọi nút của khối kia mất handler mà không ai thấy cho tới lúc bấm.
check("khối ẩn vẫn nằm trong DOM để dây nối chạy một lần cho cả hai",
      '.hidden = v !== "danoi"' in src_js and '.hidden = v !== "sanco"' in src_js)
# Trang tự vẽ lại sau mỗi lần đấu/ngắt/gỡ. Biến tab nằm trong renderConnect thì mỗi thao tác
# lại quăng người dùng về tab đầu.
check("tab đang mở sống ngoài renderConnect nên vẽ lại không mất chỗ đứng",
      src_js.index("let _mcpTab") < src_js.index("async function renderConnect"))
check("ô trống chỉ đúng tab cần mở, không chỉ xuống 'Kho bên dưới' nữa",
      "mở tab <b>Kết nối sẵn có</b>" in src_js and "trong Kho bên dưới" not in src_js)

# Hàng tab phải có LỚP RIÊNG. Trang này gán lại onclick cho MỌI `.cat-chip` trong trang để lọc
# danh mục dịch vụ; dùng chung lớp là handler của tab bị đè mất sạch, và triệu chứng đánh lừa
# hoàn toàn - viên thuốc vẫn sáng lên nên trông như tab chạy, chỉ có khối hiển thị là đứng im.
check("hàng tab dùng lớp riêng, không đụng lớp của chip lọc danh mục",
      'class="tab-kho' in src_js)
_ham_tab = src_js[src_js.index("function hangTabKho"):src_js.index("function hangTabKho") + 1400]
# Soi chỗ GÁN LỚP thật, không soi cả đoạn: chú thích trong hàm có nhắc tên `.cat-chip` để
# giải thích vì sao tránh nó, và một canary đỏ vì đọc trúng lời giải thích thì vô dụng.
check("và không nút nào trong hàm dựng tab mang lớp cat-chip",
      'class="cat-chip' not in _ham_tab)
check("lớp tab-kho có kiểu dáng riêng trong css",
      ".tab-kho" in (DASHBOARD / "console.css").read_text(encoding="utf-8"))

# `zlAgo` là tên còn sót lại của một module Zalo đã gỡ, KHÔNG hề được định nghĩa. Nó ném
# ReferenceError giữa vòng tô chấm sức khoẻ, mà forEach không bắt lỗi, nên mọi kết nối sau cái
# đầu tiên có `checked_at` đều không được tô - và vòng làm mới 60 giây lại ném thêm một lần.
check("không còn gọi hàm zlAgo đã biến mất", "+ zlAgo(" not in src_js)
check("và có hàm thay thế được định nghĩa thật",
      "function _lucNao" in src_js and "_lucNao(rec.checked_at)" in src_js)

# ============================================================
# Connector của app hiện TRONG kho, và gỡ rồi thì phải thấy là đã gỡ
# ============================================================
# Từ 0.55.31 kho hiển thị gộp: connector đi kèm app nằm cùng lưới với gói tải từ kho, đánh dấu
# sẵn "Đã cài trên máy". Nếu không thế thì tab Kết nối của kho trống trơn cho tới khi ai đó
# phát hành gói connector, mà người dùng thì chỉ muốn một chỗ để nhìn Javis nối được với gì.
#
# Lỗi THẬT ở bản dựng đầu: khoá loại gõ "connector" số ít trong khi `core_off.LOAI` là
# "connectors" số nhiều. `da_go` trả rỗng hoàn toàn im lặng, nên MỌI connector mãi mãi hiện là
# "đã cài", kể cả cái vừa bấm gỡ xong. Chỉ thấy được bằng cách mở trình duyệt ra bấm thử.
import routes.packs as _rp   # noqa: E402

# Thư mục tạm RIÊNG: khối `with tempfile...` ở trên đã đóng từ lâu, đường dẫn của nó không còn.
_tmp_kho = tempfile.TemporaryDirectory()
_goc_store = core_off.STORE
try:
    core_off.STORE = Path(_tmp_kho.name) / "core-off-kho.json"
    core_off._cache.update(sig=None, data=None)
    ds = {x["id"]: x for x in _rp._connector_cua_app()}
    check("kho liệt kê connector đi kèm app", len(ds) > 10)
    check("và chúng mang đúng loại để lọc theo tab",
          all(x["kind"] == "connector" for x in ds.values()))
    check("kèm nguồn 'app' để giao diện biết gỡ bằng core_off chứ không phải trình gỡ gói",
          all(x["nguon"] == "app" for x in ds.values()))
    check("chưa gỡ gì thì tất cả hiện là đã cài", all(x["installed"] for x in ds.values()))

    _mot = sorted(ds)[0]
    core_off.dat("connectors", _mot, True)
    ds2 = {x["id"]: x for x in _rp._connector_cua_app()}
    check("gỡ một cái thì kho thấy ngay là CHƯA cài", ds2[_mot]["installed"] is False)
    check("và những cái khác không bị ảnh hưởng",
          all(v["installed"] for k, v in ds2.items() if k != _mot))

    core_off.dat("connectors", _mot, False)
    ds3 = {x["id"]: x for x in _rp._connector_cua_app()}
    check("cài lại thì về đúng trạng thái cũ", ds3[_mot]["installed"] is True)

    # ── Đường DI TRÚ: app bỏ dần connector, kho nhận lại ──
    # Từ 0.55.33 kho có sẵn gói cho 26 connector đi kèm app. Chừng nào app còn cấp một id thì
    # gói cấp đúng id đó KHÔNG cài được (luật chống bẻ hướng một kết nối đang đăng nhập thật),
    # nên thẻ của kho phải bị giấu - hiện hai thẻ mà một cái bấm không được là tệ hơn hẳn.
    check("app còn cấp thì id nằm trong danh sách đang chiếm", _mot in _rp._id_app_dang_cap())
    core_off.dat("connectors", _mot, True)
    # Gỡ rồi thì id thôi bị chiếm: thẻ của kho hiện ra VÀ cài được. Không trừ phần đã gỡ thì
    # người dùng gỡ dịch vụ của app đi là mất luôn đường lấy bản của kho.
    check("gỡ rồi thì id thôi bị chiếm, gói của kho vào được",
          _mot not in _rp._id_app_dang_cap())
    core_off.dat("connectors", _mot, False)

finally:
    core_off.STORE = _goc_store
    core_off._cache.update(sig=None, data=None)
    _tmp_kho.cleanup()

# `packs.py` phải dùng CÙNG một luật, nếu không giao diện hiện thẻ cài được mà trình nạp vẫn
# từ chối - hỏng theo kiểu khó hiểu nhất: bấm Cài xong không có gì xảy ra.
_src_packs = (SERVER / "packs.py").read_text(encoding="utf-8")
check("trình nạp gói cũng trừ phần đã gỡ khi tính id bị chiếm",
      'set(mcp_catalog.tat_ca()) - core_off.da_go("connectors")' in _src_packs)

# Mỗi mục connector trong kho khai id nó cấp, để chỗ giấu thẻ trùng có cái mà so.
_src_store = (SERVER / "packs_store.py").read_text(encoding="utf-8")
check("bộ đọc danh mục giữ lại `provides.connectors`", '"provides"' in _src_store)
_src_rt = (SERVER / "routes" / "packs.py").read_text(encoding="utf-8")
check("kho giấu thẻ trùng với dịch vụ app đang cấp",
      "app_dang_cap" in _src_rt and "_id_app_dang_cap" in _src_rt)

if _fails:
    print(f"\nFAIL - test_loi_go_duoc: {len(_fails)} lỗi: {_fails}")
    sys.exit(1)
print("\nOK - test_loi_go_duoc: tất cả pass")
