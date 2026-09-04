"""Kho gói: tải từ mạng phải không bao giờ trỏ vào trong nhà, và kho hỏng thì hỏng tử tế.

    python tests/run.py kho_goi

Không cần pytest, KHÔNG chạm mạng thật (mọi lần tải đều thay bằng hàm giả).

Đây là đường đầu tiên trong Javis mà SERVER TỰ ĐI GỌI một địa chỉ nó không nghĩ ra, tức bề mặt
SSRF đầu tiên. Rất cụ thể: `mcp_hub` đặt hub ở `http://127.0.0.1:7777/hub/mcp` và hub cầm toàn
bộ khoá của người dùng; trên máy ảo đám mây thì `169.254.169.254` trả credential của chính máy
đó. Nên phần lớn test này canh đúng một câu hỏi: có địa chỉ nào lọt vào trong nhà không.

Ba nhóm:

1. **Chốt địa chỉ.** Chỉ https, chỉ cổng 443, và kiểm theo ĐỊA CHỈ ĐÃ PHÂN GIẢI chứ không theo
   tên máy - một tên công khai vẫn phân giải được về địa chỉ nội bộ.
2. **Chuyển hướng.** Kiểm lại ở MỖI chặng. Một tên miền lành trả 302 sang metadata là đường
   vòng kinh điển, và chốt ở chặng đầu không bảo vệ được gì.
3. **Kho là dữ liệu không tin được.** Cắt độ dài, ép kiểu, bỏ trường lạ; hỏng thì suy biến về
   cache hoặc trạng thái rỗng, không bao giờ ném một cục lỗi.
"""
from _paths import ROOT, SERVER, DASHBOARD  # noqa: E402,F401
import asyncio
import json
import sys
import tempfile
import time
from pathlib import Path

import packs_fetch
import packs_store

_fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)


# ─────────────── 1. Chốt địa chỉ ───────────────
CAM = [
    ("http thường", "http://vi-du.dev/x.zip", "https"),
    ("loopback bằng IP", "https://127.0.0.1/x.zip", "nội bộ"),
    ("loopback bằng tên", "https://localhost/x.zip", "nội bộ"),
    ("dải riêng 10.x", "https://10.0.0.1/x.zip", "nội bộ"),
    ("dải riêng 192.168.x", "https://192.168.1.1/x.zip", "nội bộ"),
    ("metadata máy ảo đám mây", "https://169.254.169.254/latest/meta-data", "nội bộ"),
    ("loopback IPv6", "https://[::1]/x.zip", "nội bộ"),
    ("cổng lạ", "https://vi-du.dev:8080/x.zip", "cổng 443"),
    ("thiếu tên máy", "https:///x.zip", "tên máy"),
    ("giao thức file", "file:///etc/passwd", "https"),
]
for ten, url, dau in CAM:
    try:
        packs_fetch.kiem_dia_chi(url)
        check(f"chặn: {ten}", False)
    except packs_fetch.LoiTai as e:
        check(f"chặn: {ten}", dau in str(e))

try:
    packs_fetch.kiem_dia_chi("https://raw.githubusercontent.com/x/y/main/a.json")
    check("cho qua địa chỉ công cộng bình thường", True)
except packs_fetch.LoiTai as e:
    check("cho qua địa chỉ công cộng bình thường: " + str(e), False)

# Địa chỉ IPv4 ánh xạ trong IPv6 phải bị bắt như chính nó, nếu không thì ::ffff:127.0.0.1 lọt.
check("::ffff:127.0.0.1 bị coi là nội bộ", packs_fetch._dia_chi_cam("::ffff:127.0.0.1"))
check("chuỗi không phải IP thì coi như cấm", packs_fetch._dia_chi_cam("khong-phai-ip"))
check("IP công cộng thì cho qua", not packs_fetch._dia_chi_cam("1.1.1.1"))

# ─────────────── 2. Rút gọn địa chỉ kho GitHub ───────────────
check("owner/repo@nhánh thành URL tải",
      packs_fetch.url_zip_github("acme/goi@v1").endswith("/zip/refs/heads/v1"))
check("thiếu nhánh thì mặc định main",
      packs_fetch.url_zip_github("acme/goi").endswith("/zip/refs/heads/main"))
check("https giữ nguyên",
      packs_fetch.url_zip_github("https://a.dev/x.zip") == "https://a.dev/x.zip")
for xau in ("", "linh tinh", "ftp://a.dev/x.zip"):
    try:
        packs_fetch.url_zip_github(xau)
        check(f"từ chối địa chỉ vô nghĩa: {xau!r}", False)
    except packs_fetch.LoiTai:
        check(f"từ chối địa chỉ vô nghĩa: {xau!r}", True)

# ─────────────── 3. Kho: làm sạch dữ liệu người khác viết ───────────────
ban = packs_store._lam_sach({
    "id": "acme.x", "name": "Tên trần", "description": {"vi": "a" * 900},
    "version": "1.0.0", "tier": "linh tinh", "verified": "có",
    "download": {"url": "goi.zip", "sha256": "ab", "size": "12"},
    "truong_la": "PHẢI BỊ BỎ", "author": {"name": "A" * 200, "email": "bo@di"},
})
check("bậc lạ bị ép về data (không tin lời khai)", ban["tier"] == "data")
check("verified ép thành bool", ban["verified"] is True)
check("mô tả bị cắt theo trần", len(ban["description"]["vi"]) == packs_store.MAX_MO_TA)
check("tên trần thành map đa ngôn ngữ", ban["name"] == {"en": "Tên trần"})
check("trường lạ bị bỏ", "truong_la" not in ban)
check("trường lạ trong author cũng bị bỏ", set(ban["author"]) == {"name"})
check("size không phải số thì về 0",
      packs_store._lam_sach({"download": {"size": "abc"}})["download"]["size"] == 0)

# ─────────────── 4. Kho: đọc, cache, và suy biến ───────────────
INDEX_TOT = json.dumps({
    "format": "javis-pack-index", "format_version": 1,
    "store": {"name": "Kho thử"},
    "packs": [
        {"id": "acme.a", "name": {"vi": "Gói A"}, "version": "1.0.0", "category": "sales",
         "download": {"url": "https://a.dev/a.zip", "sha256": "aa", "size": 10}},
        {"id": "acme.b", "name": {"vi": "Gói B"}, "version": "2.0.0",
         "download": {"url": "b.zip"}},
        {"id": "", "download": {"url": "https://a.dev/c.zip"}},          # thiếu id -> bỏ
        {"id": "acme.d"},                                                # thiếu chỗ tải -> bỏ
    ],
}).encode("utf-8")


def gia_tai(noi_dung=None, loi=None):
    async def _f(url, header=None, tran=None):
        if loi:
            raise loi
        return noi_dung
    return _f


with tempfile.TemporaryDirectory() as td:
    goc_cache, goc_tai = packs_store.CACHE, packs_fetch.tai
    packs_store.CACHE = Path(td) / "packs-store-cache.json"
    try:
        packs_fetch.tai = gia_tai(INDEX_TOT)
        d = asyncio.run(packs_store.lay(lam_moi=True))
        check("đọc được danh mục", d["ok"] and len(d["packs"]) == 2)
        check("bỏ mục thiếu id hoặc thiếu chỗ tải",
              {g["id"] for g in d["packs"]} == {"acme.a", "acme.b"})
        b = [g for g in d["packs"] if g["id"] == "acme.b"][0]
        check("địa chỉ tải tương đối được ghép với địa chỉ kho",
              b["download"]["url"].startswith("https://") and b["download"]["url"].endswith("b.zip"))
        check("có ghi cache xuống đĩa", packs_store.CACHE.is_file())

        # Lần sau còn hạn thì KHÔNG gọi mạng nữa.
        packs_fetch.tai = gia_tai(loi=RuntimeError("khong duoc goi"))
        d2 = asyncio.run(packs_store.lay())
        check("còn hạn thì dùng cache, không gọi mạng lại", d2["ok"] and not d2["stale"])

        # Hết hạn mà lấy mới thất bại -> vẫn vẽ được, nhưng PHẢI nói là số liệu cũ.
        c = json.loads(packs_store.CACHE.read_text(encoding="utf-8"))
        c["fetched_at"] = time.time() - packs_store.TTL - 10
        packs_store.CACHE.write_text(json.dumps(c), encoding="utf-8")
        d3 = asyncio.run(packs_store.lay())
        check("lấy mới hỏng mà còn cache thì vẫn vẽ được", d3["ok"] and d3["packs"])
        check("và NÓI RÕ là đang xem số liệu cũ", d3["stale"] is True and d3.get("error"))

        # Không cache, không mạng -> trạng thái rỗng, không ném lỗi.
        packs_store.CACHE.unlink()
        d4 = asyncio.run(packs_store.lay())
        check("không cache mà hỏng thì trả trạng thái rỗng, không nổ",
              d4["ok"] is False and d4["packs"] == [] and d4.get("error"))

        # Định dạng lạ.
        for raw, dau in (
            (b'{"format": "cai gi do", "packs": []}', "không phải danh mục"),
            (json.dumps({"format": "javis-pack-index", "format_version": 99,
                         "packs": []}).encode(), "mới hơn"),
            (b"khong phai json", ""),
        ):
            packs_fetch.tai = gia_tai(raw)
            r = asyncio.run(packs_store.lay(lam_moi=True))
            check(f"từ chối tệp không đúng định dạng ({dau or 'json hỏng'})",
                  r["ok"] is False and (not dau or dau in r.get("error", "")))
    finally:
        packs_store.CACHE, packs_fetch.tai = goc_cache, goc_tai

# ─────────────── 5. Canary trên mã nguồn ───────────────
src = (SERVER / "packs_fetch.py").read_text(encoding="utf-8")
check("KHÔNG để thư viện tự đi theo chuyển hướng (mất quyền kiểm giữa chừng)",
      "follow_redirects=False" in src)
check("kiểm lại địa chỉ ở MỖI chặng, không chỉ chặng đầu",
      src.count("kiem_dia_chi(hien)") >= 1 and "for _ in range(MAX_CHUYEN_HUONG" in src)
check("chặn theo địa chỉ ĐÃ PHÂN GIẢI, không theo tên máy",
      "getaddrinfo" in src and "is_global" in src)
check("kiểm MỌI địa chỉ tên máy phân giải ra, không chỉ cái đầu",
      "for x in thong_tin" in src)
check("trần dung lượng áp theo byte thật nhận được, không tin Content-Length",
      "Content-Length" in src and "aiter_bytes" in src)
check("nói thật về giới hạn còn lại (DNS rebinding)", "rebinding" in src.lower())

src_s = (SERVER / "packs_store.py").read_text(encoding="utf-8")
check("kho fetch ở phía server, không ở trình duyệt", "CORS" in src_s)
check("có trần số gói và trần độ dài", "MAX_GOI" in src_s and "MAX_MO_TA" in src_s)

src_r = (SERVER / "routes" / "packs.py").read_text(encoding="utf-8")
check("có endpoint đọc kho", '@router.get("/packs/store")' in src_r)
check("có endpoint tải từ địa chỉ", '@router.post("/packs/install-url")' in src_r)
i = src_r.index("packs_install_url")
than = src_r[i:i + 2200]
check("cài từ kho vẫn dừng ở bước SOI, không cài thẳng",
      "pack_install.soi(" in than and "pack_install.cai(" not in than)
check("đối chiếu dấu vân tay kho công bố ngay khi tải xong", "expect_sha256" in than)
check("cả hai endpoint đều đòi phiên đăng nhập thật",
      than.count("_DEPS.co_phien(request)") >= 1)

src_js = (DASHBOARD / "packs.js").read_text(encoding="utf-8")
check("lưới kho có ô tìm kiếm", 'id="pkQ"' in src_js)
check("và cột nhóm bấm lọc được", "data-kho-nhom" in src_js)
check("gói đã cài hiện 'Đã cài' thay vì mời cài lại", "Đã cài" in src_js)
check("có bản mới thì đổi nhãn nút", "Có bản mới" in src_js)
check("kho hỏng KHÔNG làm hỏng phần gói đã cài",
      "Bạn vẫn cài được gói từ tệp" in src_js)


# ============================================================
# Kho ở REPO RIÊNG, và bản cũ vẫn cài được
# ============================================================
# Tách repo là điểm mấu chốt: thêm một gói không còn dính tới việc ra bản mới của app, và người
# lạ gửi Pull Request vào kho được mà không cần quyền ghi vào mã nguồn Javis.
check("kho mặc định trỏ sang repo riêng, không phải repo Javis OS",
      "javis-store" in packs_store.STORE_MAC_DINH
      and "javis-os" not in packs_store.STORE_MAC_DINH)
check("và đọc qua raw.githubusercontent (không phải trang HTML của GitHub)",
      packs_store.STORE_MAC_DINH.startswith("https://raw.githubusercontent.com/"))

idx = json.loads((ROOT / "system" / "pack-index.json").read_text(encoding="utf-8"))
check("repo có sẵn tệp danh mục", idx.get("format") == "javis-pack-index")
check("và nó đọc được bằng chính bộ đọc",
      all(packs_store._lam_sach(x)["id"] for x in idx.get("packs", [])) if idx.get("packs") else True)
check("có tài liệu cách phát hành gói",
      (ROOT / "docs" / "dev" / "pack-store-index.md").is_file())

# Danh mục CŨ trong repo này đã đông lại, nhưng KHÔNG được xoá: bản 0.55.24-0.55.29 trỏ cứng vào
# đó. Xoá đi là mọi máy chưa cập nhật thấy kho rỗng. Nên nó phải còn, và mọi địa chỉ tải trong đó
# phải TUYỆT ĐỐI - đường tương đối sẽ ghép với repo Javis OS, nơi không còn tệp .zip nào.
check("danh mục cũ vẫn còn cho bản chưa cập nhật", bool(idx.get("packs")))
check("và mọi địa chỉ tải trong đó là tuyệt đối, trỏ sang kho mới",
      all((g.get("download") or {}).get("url", "").startswith("https://")
          and "javis-store" in g["download"]["url"] for g in idx.get("packs", [])))
check("danh mục cũ tự nói là đã đông lại, để không ai thêm nhầm vào đó",
      "ĐÔNG LẠI" in (idx.get("_doc") or ""))
# Gói thật đã dọn sang repo kho, nên repo này không còn ôm tệp .zip nào nữa.
check("repo Javis OS không còn giữ tệp gói", not (ROOT / "system" / "packs").exists())

# ============================================================
# 4. Kho là MỘT kho, vào được từ tab của bốn trang năng lực
# ============================================================
# Người dùng không đi tìm "gói", họ đi tìm một trợ lý hay một kỹ năng. Nên lưới phải chia
# được theo LOẠI, và bốn trang năng lực phải có đường sang đúng lát cắt của nó.

check("bộ đọc giữ lại loại năng lực hợp lệ",
      packs_store._lam_sach({"id": "a", "kind": "skill"})["kind"] == "skill")
check("loại lạ rơi về 'bundle' chứ không bị loại khỏi kho",
      packs_store._lam_sach({"id": "a", "kind": "khong-co-that"})["kind"] == "bundle")
check("thiếu loại cũng ra 'bundle', không ra rỗng",
      packs_store._lam_sach({"id": "a"})["kind"] == "bundle")
check("năm loại năng lực đều khai được",
      all(packs_store._lam_sach({"id": "a", "kind": k})["kind"] == k
          for k in ("agent", "skill", "workflow", "tool", "connector")))

check("lưới chia theo loại năng lực", "data-kho-loai" in src_js and "data-loai" in src_js)
check("có phân trang khi kho dài ra", "data-kho-trang" in src_js and "MOI_TRANG" in src_js)
# Connector đi kèm app hiện trong kho, và gỡ chúng phải đi qua `core_off` chứ KHÔNG qua trình
# gỡ gói: tệp trong system/ không được đụng vào, vì cây code read-only trên Docker.
check("gỡ connector của app đi đúng đường core-toggle",
      "/connect/core-toggle" in src_js and 'nguon === "app"' in src_js)
check("mỗi thẻ đeo nhãn loại của nó", "LOAI[g.kind]" in src_js)
check("kho mở được kèm loại lọc sẵn", "function moKho(" in src_js and "moKho: moKho" in src_js)
# Bộ lọc mở sẵn là Ý ĐỊNH CỦA MỘT LẦN BẤM. Không xoá đi thì lần sau vào kho từ thanh bên vẫn
# thấy lưới bị cắt còn một loại, mà không có gì trên màn hình giải thích vì sao.
check("loại lọc sẵn bị XOÁ ngay sau khi dùng, không dính lại lần sau",
      '_loaiCho = "";' in src_js.split("const loaiDau = _loaiCho;")[-1][:200])

src_con = (DASHBOARD / "console.js").read_text(encoding="utf-8")
check("năm trang năng lực đều có đường sang kho",
      all(x in src_con for x in ('agents: "agent"', 'skills: "skill"',
                                 'workflows: "workflow"', 'plugins: "tool"',
                                 'mcp: "connector"')))
# Năm bản sao của lưới kho là năm thứ sẽ lệch nhau sau vài tháng. Tab chỉ ĐIỀU HƯỚNG.
check("tab kho điều hướng sang kho chứ không nhúng bản sao lưới",
      "JavisPacks.moKho(kind)" in src_con and "veKho" not in src_con)

# Kho KHÔNG phải một chức năng ngang hàng với Trợ lý hay Kỹ năng - nó là chỗ ghé để lấy thêm
# một trong số chúng. Đường vào là tab trên chính trang đang đứng, không phải một mục nữa
# trên thanh bên vốn đã dài.
check("kho không hiện trên thanh bên", 'RAIL_AN = new Set(["packs"])' in src_con)
# Nhưng vẫn phải ở trong RAIL_ITEMS và trong `ids` của nhóm: bỏ hẳn thì `railGroups` coi là
# "chưa xếp nhóm" và dồn xuống nhóm đáy, tức hiện ở chỗ còn khó hiểu hơn.
check("vẫn giữ trong danh sách trang để không rơi xuống nhóm đáy",
      '"packs", "logs", "account", "usage",' in src_con
      and '"plugins", "packs"]' in src_con)
# VIEW_META thiếu "packs" từ đầu nên header trang kho ghi nhầm là tiêu đề Trang chủ.
check("trang kho có tiêu đề riêng, không mượn tiêu đề Trang chủ",
      '"plugins", "packs", "logs"' in src_con)

# Người vào trang này gần như luôn để TÌM thêm thứ gì đó. Xem lại thứ đã cài là việc thỉnh
# thoảng, nên nó xuống dưới.
check("kho nằm TRÊN phần đã cài",
      src_js.index("◆ Kho cài đặt") < src_js.index("◆ Đã cài"))

# Mục trong danh mục trỏ vào tệp NGAY TRONG REPO thì tệp đó phải có thật và đúng dấu vân tay.
# Đây là lỗi khó thấy nhất của một kho: index đã trỏ sang bản mới mà tệp thì quên chưa đẩy,
# và người dùng nhận một lỗi tải mà không ai ở đây biết.
import hashlib

for _g in idx.get("packs", []):
    _u = (_g.get("download") or {}).get("url", "")
    if _u.startswith("https://"):
        continue
    _p = ROOT / "system" / _u
    check(f"tệp của '{_g.get('id')}' có thật trong repo", _p.is_file())
    if _p.is_file():
        _b = _p.read_bytes()
        check(f"dấu vân tay của '{_g.get('id')}' khớp danh mục",
              hashlib.sha256(_b).hexdigest() == (_g.get("download") or {}).get("sha256"))
        check(f"kích thước của '{_g.get('id')}' khớp danh mục",
              len(_b) == (_g.get("download") or {}).get("size"))
    check(f"'{_g.get('id')}' khai loại năng lực để lọc được",
          packs_store._lam_sach(_g)["kind"] != "bundle")
    check(f"'{_g.get('id')}' khai lĩnh vực và tên lĩnh vực đọc được",
          bool(_g.get("category")) and bool(_g.get("category_label")))

if _fails:
    print(f"\nFAIL - test_kho_goi: {len(_fails)} lỗi: {_fails}")
    sys.exit(1)
print("\nOK - test_kho_goi: tất cả pass")
