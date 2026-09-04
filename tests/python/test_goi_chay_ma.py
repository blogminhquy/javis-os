"""Gói mang được TOOL, và mã trong gói chỉ chạy khi đã có người xem rồi đồng ý.

    python tests/run.py goi_chay_ma

Không cần pytest, không chạm mạng, không đụng kho gói thật.

Đây là nửa còn lại của lời hứa "mọi thứ là gói": trước bản này gói chỉ thêm được connector,
tức thêm được NGUỒN DỮ LIỆU nhưng không thêm được KHẢ NĂNG.

Chủ dự án chốt 2026-09-03 là mở cho mã Python, vì chính chủ là người xem gói trước khi cài. Nên
cổng `JAVIS_ENABLE_USER_PLUGINS` KHÔNG áp cho gói. Việc đó nhất quán chứ không phải nới lỏng,
và test này canh đúng chỗ nhất quán nằm ở đâu:

- Cổng env bịt lỗ "thư mục ghi được nên mã chạy mà không ai bấm gì". Lỗ đó CÓ THẬT với
  `<brain>/plugins/` vì model ghi được vào vault qua `javis_write_file`.
- Trình cài phá bỏ đúng điều kiện đó: có người bấm, có màn hình liệt kê từng tệp `.py`, và có
  chữ ký nội dung mã ghi lại.
- Nên thay vì cổng env, gói chịu HAI chốt khác: phải có hàng trong sổ cài đặt (tức đã qua trình
  cài), và chữ ký mã tính lại từ đĩa phải khớp cái ghi lúc cài.

Chốt thứ hai kiểm lúc NẠP chứ không chỉ lúc cài, vì ai ghi được `plugin.py` thì cũng ghi được
`packs.json` - một chốt chỉ nằm ở trình cài thì chỉ gác được trình cài.
"""
from _paths import ROOT, SERVER, DASHBOARD  # noqa: E402,F401
import asyncio
import io
import json
import sys
import tempfile
import zipfile
from pathlib import Path

import pack_install
import packs
import plugins_host

_fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)


MF = ('format: javis-pack\nspec: 1\nid: {pid}\nversion: 1.0.0\n'
      'name: {{vi: "Gói thử"}}\ncompat: {{app: "{compat}"}}\n'
      'provides:\n  plugins: [plugins/{slug}]\n')
PLUGIN_PY = (
    'DA_DONG = []\n\n'
    'def _chao(args, ctx):\n'
    '    return "xin chao " + str(args.get("ten") or "ban")\n\n'
    'def register(ctx):\n'
    '    ctx.register_tool(name="{tool}", description="Chao mot cai", handler=_chao,\n'
    '                      min_mode="readonly",\n'
    '                      schema={{"type": "object", "properties": {{"ten": {{"type": "string"}}}}}})\n'
    '    ctx.on_unload(lambda: DA_DONG.append(1))\n')
PLUGIN_YML = 'name: Chao tu goi\nversion: 1.0.0\nenabled: true\nmin_mode: readonly\ntools:\n  - {tool}\n'


def zip_goi(pid="acme.tool", slug="chao", tool="goi_chao", compat=">=0.1.0", them=None):
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w") as z:
        z.writestr("javis-pack.yaml", MF.format(pid=pid, slug=slug, compat=compat))
        z.writestr(f"plugins/{slug}/plugin.py", PLUGIN_PY.format(tool=tool))
        z.writestr(f"plugins/{slug}/plugin.yaml", PLUGIN_YML.format(tool=tool))
        for ten, noi in (them or {}).items():
            z.writestr(ten, noi)
    return b.getvalue()


def route_co(ten):
    plugins_host.invalidate()
    _, route = plugins_host.plugin_tools("full", None)
    return ten in route


with tempfile.TemporaryDirectory() as td:
    tmp = Path(td)
    goc = (packs.PACKS_DIR, packs.LEDGER, pack_install.LEDGER, pack_install.STAGING,
           plugins_host._STATE_PATH)
    packs.PACKS_DIR = tmp / "packs"
    packs.LEDGER = pack_install.LEDGER = tmp / "packs.json"
    pack_install.STAGING = tmp / "packs-staging"
    plugins_host._STATE_PATH = tmp / "plugins.json"
    packs.PACKS_DIR.mkdir()
    try:
        packs.invalidate()
        plugins_host.invalidate()
        plugins_host._STATE_CACHE.update(sig=None, data=None)

        # ─────────────── 1. Gói mang tool, và tool ra tới hub ───────────────
        r = pack_install.soi(zip_goi(), "co-tool.zip")
        check("soi xếp gói có tệp .py vào bậc code", r["ok"] and r["tier"] == "code")
        check("và liệt kê plugin trong gói để hiện lên màn hình xác nhận",
              r.get("plugins") == ["chao"])
        check("KHÔNG có tool nào trước khi cài", not route_co("goi_chao"))

        pack_install.cai(r["staging_id"], r["sha256"], enable=True)
        the = {x["slug"]: x for x in plugins_host.describe()}
        check("thẻ plugin hiện với nguồn 'pack'", the.get("chao", {}).get("source") == "pack")
        check("và báo ĐANG NẠP, không phải 'bật (chưa nạp)'", the["chao"]["loaded"] is True)
        check("tool của gói ra tới hub", route_co("goi_chao"))

        _, route = plugins_host.plugin_tools("full", None)
        check("và gọi được thật",
              asyncio.run(route["goi_chao"]["call"]({"ten": "Quý"})) == "xin chao Quý")

        # ─────────────── 2. Đổi mã sau khi đồng ý thì KHÔNG chạy nữa ───────────────
        # Đọc/ghi bằng BYTE, không phải text: `write_text` trên Windows đổi \n thành
        # \r\n, nên ghi lại đúng nội dung cũ vẫn ra một tệp khác byte, và chữ ký mã sẽ
        # lệch - đúng như thiết kế. Đây cũng là điều đáng biết khi dùng thật: sửa plugin
        # của gói bằng trình soạn thảo Windows rồi lưu là gói tự báo "mã đã đổi", kể cả
        # khi không đổi chữ nào.
        pf = packs.PACKS_DIR / "acme.tool" / "plugins" / "chao" / "plugin.py"
        goc_ma = pf.read_bytes()
        pf.write_bytes(goc_ma + b"\n# them mot dong\n")
        check("sửa một byte trong mã thì tool biến mất", not route_co("goi_chao"))
        ly_do = plugins_host._load_all(None)["errors"].get("chao", "")
        check("và nói rõ lý do là mã đã đổi", "đã đổi" in ly_do)
        check("lý do chỉ đúng đường sửa (cài lại từ trang Gói)", "trang Gói" in ly_do)
        pf.write_bytes(goc_ma)
        check("trả mã về đúng từng byte thì chạy lại", route_co("goi_chao"))

        # ─────────────── 3. Gói THẢ TAY mang mã thì không tự chạy ───────────────
        so = pack_install.doc_so()
        luu = so.pop("acme.tool")
        pack_install._ghi_so(so)
        check("gói không có hàng trong sổ cài đặt thì mã KHÔNG tự chạy",
              not route_co("goi_chao"))
        ly_do2 = plugins_host._load_all(None)["errors"].get("chao", "")
        check("và nói rõ là chưa đi qua trình cài", "trình cài" in ly_do2)
        so["acme.tool"] = luu
        pack_install._ghi_so(so)
        check("có hàng trở lại thì chạy tiếp", route_co("goi_chao"))

        # ─────────────── 4. Tắt gói và gỡ gói đều DỪNG THẬT ───────────────
        pack_install.dat_bat_tat("acme.tool", False)
        check("tắt gói thì tool biến khỏi mọi engine", not route_co("goi_chao"))
        pack_install.dat_bat_tat("acme.tool", True)
        check("bật lại thì tool quay về", route_co("goi_chao"))

        asyncio.run(pack_install.go("acme.tool"))
        check("gỡ gói thì tool biến mất", not route_co("goi_chao"))
        check("và không để lại xác module trong bộ nhớ",
              not [m for m in sys.modules if m.startswith("javis_plugin_") and "chao" in m])
        check("thư mục gói cũng sạch", not (packs.PACKS_DIR / "acme.tool").exists())

        # ─────────────── 5. Không được cướp tên plugin có sẵn ───────────────
        bundled = sorted(plugins_host._slug_bundled())
        check("đọc được danh sách plugin đi kèm app", len(bundled) >= 5)
        r2 = pack_install.soi(zip_goi(pid="acme.cuop", slug=bundled[0], tool="x_tool"),
                              "cuop-ten.zip")
        check("từ chối gói mang plugin trùng tên plugin có sẵn",
              not r2["ok"] and bundled[0] in r2["error"])
        check("và không ghi gì vào kho", not any(packs.PACKS_DIR.iterdir()))

        # ─────────────── 6. Quét tương thích lúc khởi động ───────────────
        r3 = pack_install.soi(zip_goi(pid="acme.cu", slug="chao2", tool="tool_cu"), "cu.zip")
        pack_install.cai(r3["staging_id"], r3["sha256"], enable=True)
        check("gói khớp phiên bản thì bật bình thường", route_co("tool_cu"))
        mf = packs.PACKS_DIR / "acme.cu" / "javis-pack.yaml"
        mf.write_text(mf.read_text(encoding="utf-8")
                      .replace('compat: {app: ">=0.1.0"}', 'compat: {app: ">=99.0.0"}'),
                      encoding="utf-8")
        packs.invalidate()
        tat = pack_install.quet_tuong_thich()
        check("quét lúc khởi động TẮT gói không còn khớp phiên bản",
              any(x["id"] == "acme.cu" for x in tat))
        check("và nêu lý do đọc được", "cần Javis" in (tat[0]["reason"] if tat else ""))
        check("tool của nó biến mất", not route_co("tool_cu"))
        check("nhưng gói KHÔNG bị xoá (hạ cấp rồi nâng lại là chạy tiếp)",
              (packs.PACKS_DIR / "acme.cu").is_dir())
        asyncio.run(pack_install.go("acme.cu"))
    finally:
        (packs.PACKS_DIR, packs.LEDGER, pack_install.LEDGER, pack_install.STAGING,
         plugins_host._STATE_PATH) = goc
        packs.invalidate()
        plugins_host.invalidate()
        plugins_host._STATE_CACHE.update(sig=None, data=None)

# ─────────────── 7. Canary trên mã nguồn ───────────────
src = (SERVER / "plugins_host.py").read_text(encoding="utf-8")

# Cổng env phải giữ NGUYÊN cho user/vault. Nới nó ra là mở lại đúng lỗ nó sinh ra để bịt.
i = src.index("def _load_all")
than = src[i:i + 4000]
check("cổng env vẫn áp cho plugin trong vault và toàn cục",
      'if source in ("user", "vault"):' in than and "if not env_ok:" in than)
check("nhưng KHÔNG áp cho gói (gói chịu chốt đồng ý + chữ ký mã)",
      'if source == "pack":' in than and "_pack_duoc_nap" in than)

check("thứ tự nguồn: bundled trước, pack, rồi user/vault",
      src.index('for slug, d, _pid in _pack_plugin_dirs()')
      > src.index('for source, base in (("bundled", BUNDLED_DIR),)')
      and src.index('for slug, d, _pid in _pack_plugin_dirs()')
      < src.index('for source, base in (("user", GLOBAL_DIR)'))

# Chèn thư mục plugin vào sys.path làm nó CHE module thật của server cho mọi import plugin đó
# thực hiện - một gói chứa config.py là đủ.
i2 = src.index("def _import_entry")
check("nạp module KHÔNG chọc sys.path",
      "sys.path.insert" not in src[i2:i2 + 1200]
      and "submodule_search_locations" in src[i2:i2 + 1200])
check("nạp hỏng thì không để lại xác trong sys.modules",
      "sys.modules.pop(mod_name, None)" in src[i2:i2 + 1200])

check("có ctx.on_unload cho plugin tự dọn thread/socket nó mở",
      "def on_unload(self" in src)
check("unload chạy callback NGƯỢC thứ tự đăng ký", "for fn in reversed(" in src)
check("và pop module khỏi sys.modules", "sys.modules.pop(mod, None)" in src)
check("tắt một plugin là DỪNG thật, không chỉ ẩn đi",
      "if not enabled:" in src and src.index("if not enabled:") < src.index('if source == "pack":\n        # Plugin của gói'))

src_i = (SERVER / "pack_install.py").read_text(encoding="utf-8")
check("gỡ gói thì dừng plugin của nó TRƯỚC khi xoá thư mục",
      src_i.index("plugins_host.unload(slug)") < src_i.index("thu_muc = packs.PACKS_DIR / pid"))
check("trình cài từ chối gói cướp tên plugin có sẵn", "_slug_bundled()" in src_i)
check("có quét tương thích lúc khởi động", "def quet_tuong_thich" in src_i)
check("main.py gọi quét đó lúc khởi động",
      "pack_install.quet_tuong_thich()" in (SERVER / "main.py").read_text(encoding="utf-8"))

src_js = (DASHBOARD / "console.js").read_text(encoding="utf-8")
check("thẻ plugin hiện nhãn nguồn 'Từ gói'", 'pack: ["Từ gói"' in src_js)
check("plugin của gói chỉ quản lý ở trang Gói, không bật tắt lẻ",
      "data-goto-packs" in src_js)

if _fails:
    print(f"\nFAIL - test_goi_chay_ma: {len(_fails)} lỗi: {_fails}")
    sys.exit(1)
print("\nOK - test_goi_chay_ma: tất cả pass")
