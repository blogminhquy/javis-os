"""Cài gói từ tệp .zip: soi trước, hỏi rồi mới đặt vào kho, và gỡ thì sạch.

    python tests/run.py cai_go_goi

Không cần pytest, không chạm mạng, không đụng kho gói thật.

Một tệp zip từ người lạ là dữ liệu thù địch cho tới khi chứng minh ngược lại. Test này canh ba
nhóm việc:

1. **Luật zip.** Traversal, đường dẫn tuyệt đối, symlink, bit thực thi, zip bomb, tên nhạy cảm.
   Mỗi luật ở đây từng là lỗ thật ở đâu đó chứ không phải phòng xa. Đáng chú ý nhất là symlink:
   `zipfile` KHÔNG tự chặn, nên một member tên `plugin.py` trỏ tới `.secret_key` sẽ được mọi
   endpoint đọc tệp phục vụ lại nguyên vẹn.

2. **Luồng hai bước.** `soi()` mở tệp và kiểm nhưng KHÔNG đặt gì vào kho; `cai()` chỉ nhận khi
   người gọi đưa lại đúng `sha256` đã hiện ra. Ràng buộc đó làm cái người dùng đọc trên màn
   hình phải chính là cái được cài, không có khe nào để nội dung đổi ở giữa.

3. **Gỡ sạch.** Thư mục gói biến mất, sổ cài đặt bỏ hàng, và kết nối tạo từ connector của gói
   bị xoá THEO - để lại một hàng kết nối chết vẫn là để lại credential của nó trên đĩa.
"""
from _paths import ROOT, SERVER, DASHBOARD  # noqa: E402,F401
import asyncio
import io
import json
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path

import mcp_catalog
import pack_install
import packs

_fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)


MF = ('format: javis-pack\nspec: 1\nid: {pid}\nversion: 1.0.0\n'
      'name: {{vi: "Gói thử", en: "Test pack"}}\ncompat: {{app: ">=0.1.0"}}\n'
      'provides:\n  connectors: [connectors/demo.yaml]\n')
CON = ('id: {cid}\nname: Demo\nicon: assets/x.png\ncategory: Bán hàng\n'
       'description: Connector thử.\ntransport: http\nurl: https://vi-du.dev/mcp\n'
       'auth: {{type: apikey, fields: [{{key: api_key, label: "API key"}}]}}\n'
       'tool_meta: {{read: [demo_list]}}\ndefault_perm: full\n')


def zip_goi(pid="acme.thu", cid="acme-thu-con", boc="", them=None, mf=None):
    """Dựng một tệp zip trong bộ nhớ. `boc` mô phỏng lớp thư mục bọc của GitHub zipball."""
    b = io.BytesIO()
    tien = (boc + "/") if boc else ""
    with zipfile.ZipFile(b, "w") as z:
        z.writestr(tien + "javis-pack.yaml", mf if mf is not None else MF.format(pid=pid))
        z.writestr(tien + "connectors/demo.yaml", CON.format(cid=cid))
        z.writestr(tien + "assets/x.png", b"\x89PNG\r\n")
        for ten, noi in (them or {}).items():
            z.writestr(tien + ten if not ten.startswith(("/", "..")) else ten, noi)
    return b.getvalue()


def lam_moi():
    packs.invalidate()
    mcp_catalog._cache.update(sig=None, by_id={})


with tempfile.TemporaryDirectory() as td:
    tmp = Path(td)
    goc = (packs.PACKS_DIR, pack_install.LEDGER, pack_install.STAGING)
    packs.PACKS_DIR = tmp / "packs"
    packs.LEDGER = pack_install.LEDGER = tmp / "packs.json"
    pack_install.STAGING = tmp / "packs-staging"
    packs.PACKS_DIR.mkdir()
    try:
        lam_moi()
        so_goc = len(mcp_catalog.load())

        # ─────────────── 1. Vòng đời đầy đủ ───────────────
        du = zip_goi(boc="repo-abc123")   # có lớp bọc, đúng như GitHub zipball
        r = pack_install.soi(du, "acme-thu.zip")
        check("soi được tệp hợp lệ", r["ok"] and not r["error"])
        check("bóc được lớp thư mục bọc ngoài của zipball", r["id"] == "acme.thu")
        check("soi nêu đúng connector sắp thêm", r["connectors"] == ["acme-thu-con"])
        check("soi xếp bậc data cho gói không có mã", r["tier"] == "data")
        check("soi trả sha256 để đối chiếu lúc cài", len(r["sha256"]) == 64)
        check("SOI KHÔNG đặt gì vào kho", not any(packs.PACKS_DIR.iterdir()))
        check("và catalog chưa đổi", len(mcp_catalog.load()) == so_goc)

        xau = pack_install.cai(r["staging_id"], "0" * 64)
        check("cài với dấu vân tay SAI thì bị từ chối", not xau["ok"] and "đã đổi" in xau["error"])
        check("và vẫn chưa đặt gì vào kho", not any(packs.PACKS_DIR.iterdir()))

        ok = pack_install.cai(r["staging_id"], r["sha256"], enable=True)
        check("cài với đúng dấu vân tay thì được", ok["ok"])
        lam_moi()
        check("connector của gói vào catalog", len(mcp_catalog.load()) == so_goc + 1)
        check("sổ cài đặt ghi lại gói", "acme.thu" in pack_install.doc_so())
        hang = pack_install.doc_so()["acme.thu"]
        check("sổ ghi dấu vân tay đã cài", hang["sha256"] == r["sha256"])
        check("gói không có mã thì chữ ký mã rỗng", hang["code_digest"] == "")
        check("staging được dọn sau khi cài",
              not (pack_install.STAGING / r["sha256"]).exists())

        # Tắt rồi bật.
        pack_install.dat_bat_tat("acme.thu", False)
        lam_moi()
        check("tắt gói thì connector của nó rời khỏi catalog",
              len(mcp_catalog.load()) == so_goc)
        check("nhưng gói vẫn còn trong danh sách để bật lại",
              any(p["id"] == "acme.thu" and p.get("enabled") is False
                  for p in packs.installed()))
        pack_install.dat_bat_tat("acme.thu", True)
        lam_moi()
        check("bật lại thì connector quay về", len(mcp_catalog.load()) == so_goc + 1)

        # Gỡ.
        ke = pack_install.ke_hoach_go("acme.thu")
        check("kế hoạch gỡ nêu đúng connector", ke["connectors"] == ["acme-thu-con"])
        check("và nêu số kết nối bị ảnh hưởng", ke["connections"] == [])
        g = asyncio.run(pack_install.go("acme.thu"))
        lam_moi()
        check("gỡ xong thì catalog trở lại như cũ",
              g["ok"] and len(mcp_catalog.load()) == so_goc)
        check("thư mục gói biến mất", not (packs.PACKS_DIR / "acme.thu").exists())
        check("sổ cài đặt bỏ hàng", "acme.thu" not in pack_install.doc_so())
        check("không để lại thư mục rác trong kho",
              not [d for d in packs.PACKS_DIR.iterdir() if d.name.startswith(".trash")])

        # ─────────────── 2. Cài đè bản cũ, và rollback ───────────────
        r1 = pack_install.soi(zip_goi(), "v1.zip")
        pack_install.cai(r1["staging_id"], r1["sha256"], enable=True)
        mf2 = MF.format(pid="acme.thu").replace("version: 1.0.0", "version: 2.0.0")
        r2 = pack_install.soi(zip_goi(mf=mf2), "v2.zip")
        check("nâng cấp chính gói mình thì KHÔNG bị báo trùng connector",
              r2["ok"] and r2["connectors"] == ["acme-thu-con"])
        check("và soi biết máy đã có bản cũ", (r2.get("da_cai") or {}).get("version") == "1.0.0")
        pack_install.cai(r2["staging_id"], r2["sha256"], enable=True)
        check("cài đè xong thì sổ ghi bản mới",
              pack_install.doc_so()["acme.thu"]["version"] == "2.0.0")
        check("không để lại thư mục .trash",
              not [d for d in packs.PACKS_DIR.iterdir() if d.name.startswith(".trash")])
        asyncio.run(pack_install.go("acme.thu"))
        lam_moi()

        # ─────────────── 3. Luật zip ───────────────
        def zip_tho(cac_member, symlink=None, ti_le=False):
            b = io.BytesIO()
            with zipfile.ZipFile(b, "w", zipfile.ZIP_DEFLATED) as z:
                for ten, noi in cac_member.items():
                    z.writestr(ten, noi)
                if symlink:
                    zi = zipfile.ZipInfo(symlink[0])
                    zi.external_attr = (0o120777 << 16)   # S_IFLNK
                    z.writestr(zi, symlink[1])
                if ti_le:
                    z.writestr("phinh.txt", "A" * (2 * 1024 * 1024))
            return b.getvalue()

        cac_ca = [
            ("leo ra ngoài bằng ..",
             zip_tho({"javis-pack.yaml": MF.format(pid="x"), "../../trom.txt": "x"}), "leo ra ngoài"),
            ("đường dẫn tuyệt đối",
             zip_tho({"javis-pack.yaml": MF.format(pid="x"), "/etc/passwd": "x"}), "tuyệt đối"),
            ("liên kết tượng trưng",
             zip_tho({"javis-pack.yaml": MF.format(pid="x")},
                     symlink=("plugin.py", "../../.secret_key")), "liên kết tượng trưng"),
            ("mang theo tệp .env",
             zip_tho({"javis-pack.yaml": MF.format(pid="x"), ".env": "SECRET=1"}), "không cho phép"),
            ("mang theo khoá riêng",
             zip_tho({"javis-pack.yaml": MF.format(pid="x"), "khoa.pem": "x"}), "khoá riêng"),
            ("không phải zip", b"khong phai zip", "hợp lệ"),
        ]
        for ten, du_lieu, dau_hieu in cac_ca:
            b = pack_install.soi(du_lieu, "xau.zip")
            check(f"từ chối: {ten}", not b["ok"] and dau_hieu in b["error"])
            check(f"   và không ghi gì vào kho: {ten}", not any(packs.PACKS_DIR.iterdir()))

        # Tỉ lệ nén bất thường: 2MB toàn 'A' nén lại rất nhỏ.
        b = pack_install.soi(zip_tho({"javis-pack.yaml": MF.format(pid="x")}, ti_le=True), "bom.zip")
        check("từ chối: tỉ lệ nén bất thường", not b["ok"] and "tỉ lệ" in b["error"])

        # Quá nhiều tệp.
        b = pack_install.soi(zip_tho({f"f{i}.txt": "x" for i in range(600)}), "nhieu.zip")
        check("từ chối: quá nhiều tệp", not b["ok"] and "quá nhiều" in b["error"])

        # Zip hợp lệ nhưng không có manifest.
        b = pack_install.soi(zip_tho({"doc.txt": "chao"}), "khong-manifest.zip")
        check("từ chối: trong gói không có javis-pack.yaml",
              not b["ok"] and "javis-pack.yaml" in b["error"])

        # Id không hợp lệ. Lưu ý: qua đường ZIP thì id lấy TỪ MANIFEST rồi đặt tên thư
        # mục theo nó, nên ca "id lệch tên thư mục" chỉ xảy ra với gói thả tay - đã có
        # test riêng canh chuyện đó.
        b = pack_install.soi(zip_goi(mf='format: javis-pack\nspec: 1\nid: "Có Dấu"\n'), "id-xau.zip")
        check("từ chối id gói không hợp lệ", not b["ok"] and "id gói" in b["error"])
        b = pack_install.soi(zip_goi(mf="format: khong-phai\nspec: 1\nid: x\n"), "sai-format.zip")
        check("từ chối tệp không phải gói Javis", not b["ok"] and "format" in b["error"])

        # ─────────────── 4. Bậc code và chữ ký mã ───────────────
        du_ma = zip_goi(pid="acme.ma", cid="acme-ma-con",
                        them={"plugins/thu/plugin.py": "def register(ctx):\n    pass\n",
                              "plugins/thu/plugin.yaml": "name: Thu\nenabled: false\n"})
        rm = pack_install.soi(du_ma, "co-ma.zip")
        check("gói có tệp .py được xếp bậc code", rm["ok"] and rm["tier"] == "code")
        check("và soi liệt kê từng tệp mã để hiện lên màn hình xác nhận",
              "plugins/thu/plugin.py" in rm["py_files"])
        pack_install.cai(rm["staging_id"], rm["sha256"])
        check("gói có mã thì sổ ghi chữ ký nội dung mã",
              len(pack_install.doc_so()["acme.ma"]["code_digest"]) == 64)
        check("cài mà không tick bật thì mặc định TẮT",
              pack_install.doc_so()["acme.ma"]["enabled"] is False)
        asyncio.run(pack_install.go("acme.ma"))

        # ─────────────── 5. Dọn staging ───────────────
        r = pack_install.soi(zip_goi(), "bo-do.zip")
        check("soi mà không cài thì còn lại trong staging",
              (pack_install.STAGING / r["sha256"]).is_dir())
        check("dọn staging quá hạn", pack_install.don_staging(ttl=0) >= 1)
        check("và thư mục đó biến mất", not (pack_install.STAGING / r["sha256"]).exists())
    finally:
        packs.PACKS_DIR, packs.LEDGER, pack_install.STAGING = goc[0], goc[1], goc[2]
        pack_install.LEDGER = goc[1]
        lam_moi()

# ─────────────── 6. Plugin đi kèm app phải gỡ được ───────────────
import plugins_host  # noqa: E402

with tempfile.TemporaryDirectory() as td:
    goc_state = plugins_host._STATE_PATH
    plugins_host._STATE_PATH = Path(td) / "plugins.json"
    plugins_host._STATE_CACHE.update(sig=None, data=None)
    try:
        d = {x["slug"]: x for x in plugins_host.describe()}
        check("mọi thẻ plugin đều có trạng thái đã gỡ", all("removed" in x for x in d.values()))
        mau = "tool-audit"
        check("plugin mẫu có trong bộ đi kèm app", mau in d)
        plugins_host.set_removed(mau, True)
        d2 = {x["slug"]: x for x in plugins_host.describe()}
        check("gỡ rồi thì đánh dấu removed", d2[mau]["removed"] is True)
        check("và KHÔNG còn được nạp (tool biến khỏi mọi engine)", d2[mau]["loaded"] is False)
        check("trạng thái ghi ở STATE_DIR, không sửa cây code",
              plugins_host._STATE_PATH.is_file()
              and "removed" in json.loads(plugins_host._STATE_PATH.read_text(encoding="utf-8")))
        check("tệp của plugin vẫn nằm nguyên trong bản cài",
              (ROOT / "system" / "plugins" / mau / "plugin.py").is_file())
        plugins_host.set_removed(mau, False)
        check("cài lại được", {x["slug"]: x for x in plugins_host.describe()}[mau]["removed"] is False)
    finally:
        plugins_host._STATE_PATH = goc_state
        plugins_host._STATE_CACHE.update(sig=None, data=None)
        plugins_host.invalidate()

# ─────────────── 7. Canary trên mã nguồn ───────────────
src = (SERVER / "pack_install.py").read_text(encoding="utf-8")
check("chỉ nhận zip, KHÔNG tar (extractall của tar vẫn theo symlink)",
      "tarfile" not in src and "import zipfile" in src)
# Soi lời GỌI, không soi chữ trong ghi chú: docstring có nhắc `TarFile.extractall` để
# giải thích vì sao không dùng, và đó chính là thứ nên có trong file.
check("giải nén thủ công, không gọi extractall", ".extractall(" not in src)
check("mode do mình đặt, không nghe archive", "os.chmod(ra, 0o644)" in src)
check("có chốt dấu vân tay giữa lúc xem và lúc cài", "consent_sha256" in src)

src_r = (SERVER / "routes" / "packs.py").read_text(encoding="utf-8")
check("router không bao giờ import main",
      not any(L.strip().startswith(("import main", "from main")) for L in src_r.splitlines()))
check("mọi endpoint quản lý gói đòi phiên đăng nhập thật",
      src_r.count("_DEPS.co_phien(request)") >= 6)
check("đọc tệp tải lên theo khối, không nạp cả tệp vào RAM rồi mới kiểm",
      "await file.read(1 << 20)" in src_r)
check("KHÔNG phục vụ SVG", ".svg" not in src_r)

src_js = (DASHBOARD / "packs.js").read_text(encoding="utf-8")
check("màn hình xác nhận vẽ từ /packs/inspect", "/packs/inspect" in src_js)
check("gói có mã thì bắt gõ lại mã gói", "pkGo" in src_js and "Gõ lại mã gói" in src_js)
# Ô phải KHÔNG mang thuộc tính `checked` trong HTML. Đọc `.checked` lúc bấm thì khác.
_i = src_js.index('id="pkBat"')
check("ô 'bật sau khi cài' mặc định TẮT", "checked" not in src_js[_i - 60:_i + 20])
check("nói thẳng gói chạy mã thật, không làm mềm",
      "chạy Python thật bên trong máy chủ" in src_js)

src_c = (DASHBOARD / "console.js").read_text(encoding="utf-8")
check("trang Gói đăng ký trong rail", '"packs"' in src_c and "JavisPacks" in src_c)
for f in ("vi", "en"):
    d = json.loads((DASHBOARD / "i18n" / f"{f}.json").read_text(encoding="utf-8"))
    check(f"từ điển {f} có nhãn trang Gói", bool(d.get("page.packs.label")))

check("hai thư mục plugin rỗng đã dọn",
      not (ROOT / "system" / "plugins" / "zalo-rule").exists()
      and not (ROOT / "system" / "plugins" / "zalo-send").exists())

for f in (".gitignore", ".dockerignore"):
    t = (ROOT / f).read_text(encoding="utf-8")
    check(f"{f} bỏ qua sổ gói và staging",
          "server/packs.json" in t and "server/packs-staging/" in t)

if _fails:
    print(f"\nFAIL - test_cai_go_goi: {len(_fails)} lỗi: {_fails}")
    sys.exit(1)
print("\nOK - test_cai_go_goi: tất cả pass")
