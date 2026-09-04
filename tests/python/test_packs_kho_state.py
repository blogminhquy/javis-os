"""Thả một thư mục vào STATE_DIR/packs là có thêm connector, và hỏng thì THIẾU chứ không THỪA.

    python tests/run.py packs_kho_state

Không cần pytest, không chạm mạng, không đụng `STATE_DIR/packs` thật.

Bối cảnh: 524 lần bump VERSION trong ba tháng, 60 lần trong đó chỉ để sửa
`system/mcp-catalog.json`. Nguyên nhân là `mcp_catalog.CATALOG_PATH` trỏ cứng vào một file
trong repo, mà trên Docker cây code read-only nên không có đường nào khác ngoài ra bản mới.
`server/packs.py` mở đường thứ hai: kho gốc vẫn ở chỗ cũ, gói chỉ PHỦ THÊM.

Ba luật mà test này canh, và cả ba đều là luật an toàn chứ không phải luật gọn gàng:

1. **Gói không bao giờ ghi đè kho gốc.** Một gói ship `id: pancake-pos` kèm `url_template` trỏ
   đi chỗ khác sẽ âm thầm bẻ hướng một kết nối ĐANG ĐĂNG NHẬP THẬT, vì `mcp_store.resolved`
   dựng lại url và header TỪ CONNECTOR ở mỗi lần resolve. Trùng id là từ chối, không có
   `override` trong spec 1.

2. **Connector từ gói luôn bắt đầu ở mức chỉ đọc**, bất kể manifest khai gì. Nâng quyền là
   việc của người dùng, theo TỪNG TÀI KHOẢN, ở trang Kết nối nơi cảnh báo rủi ro đã có sẵn.

3. **Hỏng thì thiếu, không bao giờ thừa.** Mọi lỗi dẫn tới "gói đó không nạp" kèm lý do đọc
   được, chứ không bao giờ dẫn tới nạp một phần hay làm kho gốc xấu đi.
"""
from _paths import ROOT, SERVER, DASHBOARD  # noqa: E402,F401
import io
import os
import shutil
import sys
import tempfile
from pathlib import Path

import mcp_catalog
import packs

_fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)


MANIFEST = """format: javis-pack
spec: 1
id: {pid}
version: 1.0.0
name: {{en: "Demo", vi: "Thử"}}
description: {{vi: "Gói thử"}}
compat: {{app: ">=0.1.0"}}
provides:
  connectors: [connectors/demo.yaml]
"""

CONNECTOR = """id: {cid}
name: Demo
icon: {icon}
category: Bán hàng
description: Connector thử.
transport: {transport}
url: https://vi-du.dev/mcp
auth:
  type: {auth}
  fields: [{{key: api_key, label: "API key"}}]
tool_meta:
  read: [demo_list]
default_perm: full
"""


def lam_goi(goc, pid, *, cid="demo-con", transport="http", auth="apikey", icon="assets/x.png",
            manifest=None, connector=None, khai_id=None, them_py=False):
    d = goc / pid
    (d / "connectors").mkdir(parents=True, exist_ok=True)
    (d / "javis-pack.yaml").write_text(
        manifest if manifest is not None else MANIFEST.format(pid=khai_id or pid),
        encoding="utf-8")
    (d / "connectors" / "demo.yaml").write_text(
        connector if connector is not None else CONNECTOR.format(
            cid=cid, transport=transport, auth=auth, icon=icon),
        encoding="utf-8")
    if them_py:
        (d / "plugin.py").write_text("def register(ctx):\n    pass\n", encoding="utf-8")
    return d


def lam_moi():
    """Buộc cả hai tầng đọc lại từ đĩa."""
    packs.invalidate()
    mcp_catalog._cache.update(sig=None, by_id={})


with tempfile.TemporaryDirectory() as td:
    kho = Path(td) / "packs"
    kho.mkdir()
    goc_dir, packs.PACKS_DIR = packs.PACKS_DIR, kho
    goc_env = os.environ.pop("JAVIS_DISABLE_PACKS", None)
    try:
        lam_moi()
        so_goc = len(mcp_catalog.tat_ca())
        check(f"kho gốc có {so_goc} connector", so_goc >= 29)
        check("chưa cài gói nào thì catalog bằng kho gốc", len(mcp_catalog.load()) == so_goc)
        check("và danh sách gói rỗng", packs.installed() == [])

        # ─────────────── 1. Gói hợp lệ ───────────────
        lam_goi(kho, "acme.demo")
        lam_moi()
        ds = packs.installed()
        check("gói hợp lệ nạp được", len(ds) == 1 and ds[0]["ok"] and not ds[0]["error"])
        check("và được xếp bậc data (không có mã, không có lệnh)", ds[0]["tier"] == "data")
        check("connector của gói vào catalog", len(mcp_catalog.load()) == so_goc + 1)
        con = mcp_catalog.get("demo-con")
        check("get() trả về nó", bool(con))
        check("có gắn nhãn nguồn _pack", (con or {}).get("_pack") == "acme.demo")
        check("manifest khai full nhưng BỊ ÉP về chỉ đọc",
              (con or {}).get("default_perm") == "readonly")
        pub = {c["id"]: c for c in mcp_catalog.public_catalog()}
        check("public_catalog có nó kèm nhãn nguồn", pub["demo-con"]["pack"] == "acme.demo")
        check("icon viết lại thành URL tuyệt đối, không lặp thư mục",
              pub["demo-con"]["icon"] == "/packs/acme.demo/asset/x.png")
        check("kho gốc KHÔNG bị đụng", len(mcp_catalog.tat_ca()) == so_goc)

        # ─────────────── 2. Không được ghi đè kho gốc ───────────────
        lam_goi(kho, "acme.gian", cid="pancake-pos")
        lam_moi()
        gian = [p for p in packs.installed() if p["id"] == "acme.gian"][0]
        check("gói ship id trùng connector gốc thì connector đó bị từ chối",
              gian["connectors"] == [])
        check("và nói rõ lý do", "đã có trong kho" in (gian["error"] or ""))
        pc = mcp_catalog.get("pancake-pos")
        check("Pancake POS gốc vẫn nguyên (không bị bẻ hướng)",
              bool(pc) and not pc.get("_pack"))
        shutil.rmtree(kho / "acme.gian")

        # Hai gói cùng khai một id: cái sau bị từ chối, cái trước giữ.
        lam_goi(kho, "acme.hai", cid="demo-con")
        lam_moi()
        hai = [p for p in packs.installed() if p["id"] == "acme.hai"][0]
        check("hai gói cùng khai một connector thì cái sau bị từ chối", hai["connectors"] == [])
        check("connector đó vẫn thuộc gói đầu",
              (mcp_catalog.get("demo-con") or {}).get("_pack") == "acme.demo")
        shutil.rmtree(kho / "acme.hai")

        # ─────────────── 3. Trường bị cấm ───────────────
        for ten, kw, dau_hieu in (
            ("transport internal", {"transport": "internal"}, "transport"),
            ("đăng nhập QR", {"auth": "qr"}, "đăng nhập"),
            ("icon trỏ ra URL ngoài", {"icon": "https://theo-doi.dev/px.png"}, "icon"),
            ("icon leo ra ngoài gói", {"icon": "../../.secret_key"}, "icon"),
        ):
            lam_goi(kho, "acme.xau", cid="con-xau", **kw)
            lam_moi()
            b = [p for p in packs.installed() if p["id"] == "acme.xau"][0]
            check(f"từ chối: {ten}", b["connectors"] == [] and dau_hieu in (b["error"] or ""))
            check(f"   và connector đó không vào catalog: {ten}",
                  mcp_catalog.get("con-xau") is None)
            shutil.rmtree(kho / "acme.xau")

        # Connector trỏ ra NGOÀI thư mục gói.
        d = lam_goi(kho, "acme.ra-ngoai")
        (d / "javis-pack.yaml").write_text(
            MANIFEST.format(pid="acme.ra-ngoai").replace(
                "connectors/demo.yaml", "../../mcp_servers.json"), encoding="utf-8")
        lam_moi()
        rn = [p for p in packs.installed() if p["id"] == "acme.ra-ngoai"][0]
        check("từ chối: connector trỏ ra ngoài thư mục gói",
              rn["connectors"] == [] and "ngoài" in (rn["error"] or ""))
        shutil.rmtree(d)

        # ─────────────── 4. Manifest sai thì cả gói không nạp ───────────────
        for ten, mf, dau_hieu in (
            ("thiếu format", "spec: 1\nid: acme.x\n", "format"),
            ("spec lạ", "format: javis-pack\nspec: 99\nid: acme.x\n", "spec"),
            ("YAML hỏng", "format: javis-pack\nspec: 1\n  id: [khong dong\n", "lỗi"),
            ("compat không khớp",
             "format: javis-pack\nspec: 1\nid: acme.x\ncompat: {app: '>=99.0.0'}\n", "cần Javis"),
            ("id khai lệch tên thư mục",
             "format: javis-pack\nspec: 1\nid: khac-han\n", "khác tên thư mục"),
        ):
            lam_goi(kho, "acme.x", manifest=mf)
            lam_moi()
            b = [p for p in packs.installed() if p["id"] == "acme.x"][0]
            check(f"từ chối cả gói: {ten}",
                  not b["ok"] and dau_hieu.lower() in (b["error"] or "").lower())
            shutil.rmtree(kho / "acme.x")

        # Thiếu hẳn manifest.
        (kho / "acme.trong").mkdir()
        lam_moi()
        b = [p for p in packs.installed() if p["id"] == "acme.trong"][0]
        check("thư mục không có manifest thì báo thiếu, không nổ",
              not b["ok"] and "thiếu" in b["error"])
        shutil.rmtree(kho / "acme.trong")

        # Id trùng tên module của server.
        lam_goi(kho, "config", khai_id="config")
        lam_moi()
        b = [p for p in packs.installed() if p["id"] == "config"][0]
        check("từ chối id gói trùng tên module của Javis",
              not b["ok"] and "module" in (b["error"] or ""))
        shutil.rmtree(kho / "config")

        # ─────────────── 5. Bậc code ───────────────
        lam_goi(kho, "acme.code", cid="con-code", them_py=True)
        lam_moi()
        b = [p for p in packs.installed() if p["id"] == "acme.code"][0]
        check("gói có file .py được xếp bậc code", b["tier"] == "code")
        shutil.rmtree(kho / "acme.code")
        lam_goi(kho, "acme.stdio", cid="con-stdio", transport="stdio")
        lam_moi()
        b = [p for p in packs.installed() if p["id"] == "acme.stdio"][0]
        check("gói chạy lệnh ngoài (stdio) cũng là bậc code", b["tier"] == "code")
        shutil.rmtree(kho / "acme.stdio")

        # ─────────────── 6. Công tắc tắt sạch ───────────────
        lam_moi()
        check("trước khi tắt vẫn còn gói", len(mcp_catalog.load()) == so_goc + 1)
        os.environ["JAVIS_DISABLE_PACKS"] = "true"
        lam_moi()
        check("JAVIS_DISABLE_PACKS tắt sạch mọi gói", len(mcp_catalog.load()) == so_goc)
        check("và kho gốc vẫn đủ", mcp_catalog.get("pancake-pos") is not None)
        os.environ.pop("JAVIS_DISABLE_PACKS", None)
        lam_moi()
        check("bỏ biến môi trường thì gói quay lại", len(mcp_catalog.load()) == so_goc + 1)

        # ─────────────── 7. Cache đổi theo đĩa ───────────────
        shutil.rmtree(kho / "acme.demo")
        check("xoá thư mục gói thì connector biến mất ở lần load kế (không cần khởi động lại)",
              len(mcp_catalog.load()) == so_goc)

        # ─────────────── 8. Chốt đường dẫn khi phục vụ file ───────────────
        d = lam_goi(kho, "acme.asset")
        (d / "assets").mkdir(exist_ok=True)
        (d / "assets" / "x.png").write_bytes(b"\x89PNG\r\n")
        lam_moi()
        check("asset trong gói lấy được", packs.asset_path("acme.asset", "x.png") is not None)
        for xau in ("../javis-pack.yaml", "../../mcp_servers.json", "/etc/passwd",
                    "..\\..\\.secret_key"):
            check(f"chặn đường dẫn leo ra ngoài: {xau}",
                  packs.asset_path("acme.asset", xau) is None)
        check("id gói không hợp lệ thì không phục vụ gì",
              packs.asset_path("../..", "x.png") is None)
        check("file không tồn tại trả None", packs.asset_path("acme.asset", "khong-co.png") is None)
    finally:
        os.environ.pop("JAVIS_DISABLE_PACKS", None)
        if goc_env is not None:
            os.environ["JAVIS_DISABLE_PACKS"] = goc_env
        packs.PACKS_DIR = goc_dir
        lam_moi()

# ─────────────── 9. Canary trên mã nguồn ───────────────
src = (SERVER / "packs.py").read_text(encoding="utf-8")
# Canary soi KHOÁ ĐƯỢC ĐỌC, không soi chữ trong ghi chú: spec 1 cố ý không có `override`,
# và lý do vì sao thì phải được viết ra trong file.
check("không đọc khoá 'override' ở đâu cả (gói không ghi đè được kho gốc)",
      'get("override"' not in src and "get('override'" not in src)
check("connector từ gói bị ép readonly một cách tường minh",
      'con["default_perm"] = "readonly"' in src)
check("transport internal nằm trong danh sách cấm", '_TRANSPORT_CAM = ("internal",)' in src)

src_cat = (SERVER / "mcp_catalog.py").read_text(encoding="utf-8")
check("phủ gói bằng setdefault, không phải gán đè", "by_id.setdefault(cid, con)" in src_cat)
check("khoá cache có gộp chữ ký của kho gói", "_sig_goi()" in src_cat)

src_hub = (SERVER / "mcp_hub.py").read_text(encoding="utf-8")
i = src_hub.index("def _store_mtime")
check("hub nhận ra kho gói và sổ đã gỡ cũng đổi được danh sách tool",
      '"packs"' in src_hub[i:i + 900] and "core-off.json" in src_hub[i:i + 900])

# Endpoint gói nằm ở routes/packs.py (bóc riêng ở 0.55.22), main.py chỉ gọi register.
src_r = (SERVER / "routes" / "packs.py").read_text(encoding="utf-8")
check("có endpoint liệt kê gói", '@router.get("/packs")' in src_r)
check("có endpoint phục vụ ảnh của gói", '/asset/{duong:path}' in src_r)
check("KHÔNG phục vụ SVG (mở thẳng một tab là chạy script)", ".svg" not in src_r)
check("gửi kèm nosniff", "X-Content-Type-Options" in src_r)
check("main.py gọi register đúng khuôn router", "packs_routes.register(app" in
      (SERVER / "main.py").read_text(encoding="utf-8"))

for f in (".gitignore", ".dockerignore"):
    t = (ROOT / f).read_text(encoding="utf-8")
    check(f"{f} bỏ qua kho gói (STATE_DIR mặc định nằm TRONG cây git)", "server/packs/" in t)

# ============================================================
# Đọc VERSION phải neo vào CÂY MÃ NGUỒN, không suy từ STATE_DIR
# ============================================================
# Lỗi thật ở 0.55.26: `PROJECT_ROOT` suy từ `STATE_DIR.parent`, đúng khi chạy từ gốc repo với
# state mặc định, và SAI ở mọi bản cài có đặt `JAVIS_STATE_DIR` - Docker `/data/state` ra
# `/data`, chỗ không có VERSION. `_app_version()` trả rỗng, `_hop_compat` so với (0,0,0), nên
# MỌI gói khai `compat.app` bị từ chối ở bước validate: "cần Javis >=0.55.25, bản này là "
# (bỏ trống). Cả kho không cài được gì, trên đúng những bản cài người dùng thật đang chạy.

# Chạy với STATE_DIR mặc định thì mã CŨ cũng qua (state mặc định nằm trong cây repo), nên
# phép kiểm ở tiến trình này không bắt được lỗi. Phải nạp `packs` trong một tiến trình con có
# `JAVIS_STATE_DIR` trỏ đi CHỖ KHÁC - đúng hình dạng của Docker và của bản cài thật.
import subprocess

with tempfile.TemporaryDirectory() as _td:
    _r = subprocess.run(
        [sys.executable, "-c",
         "import packs;print(packs._app_version());print(packs._hop_compat('>=0.0.1')[0])"],
        cwd=str(SERVER), capture_output=True, text=True,
        env={**os.environ, "JAVIS_STATE_DIR": _td, "PYTHONIOENCODING": "utf-8"})
    _dong = [x.strip() for x in (_r.stdout or "").splitlines() if x.strip()]

_that = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
check("đặt JAVIS_STATE_DIR đi chỗ khác thì VẪN đọc được VERSION",
      len(_dong) >= 1 and _dong[0] == _that)
check("nên gói khai compat vẫn cài được, không chết ở bước validate",
      len(_dong) >= 2 and _dong[1] == "True")

check("VERSION đọc từ cây mã nguồn, không phải từ thư mục state",
      (packs.PROJECT_ROOT / "VERSION").is_file())
check("neo giống hệt các module khác trong server",
      packs.PROJECT_ROOT.resolve() == (SERVER / "..").resolve())
# Canary: chặn đúng cái pattern đã gây ra lỗi, để không ai vô tình viết lại.
_src_packs = (SERVER / "packs.py").read_text(encoding="utf-8")
check("PROJECT_ROOT neo vào __file__ chứ KHÔNG suy từ STATE_DIR",
      "PROJECT_ROOT = Path(__file__).parent.parent" in _src_packs
      and "PROJECT_ROOT = STATE_DIR" not in _src_packs)

_ban = packs._app_version()
check("gói khai đúng phiên bản đang chạy thì QUA", packs._hop_compat(f">={_ban}")[0])
check("gói đòi bản tương lai thì bị chặn, kèm lý do có số", not packs._hop_compat(">=99.0.0")[0])
check("lý do nêu cả mốc cần lẫn bản đang chạy",
      _ban in packs._hop_compat(">=99.0.0")[1])

# Không đọc nổi VERSION là lỗi CỦA JAVIS. Từ chối mọi gói vì tệp của chính mình không đọc được
# thì hỏng nặng hơn nhiều so với cho cài một gói có thể hơi mới - người dùng đã đọc màn hình
# xác nhận và tự bấm đồng ý. Cùng tinh thần với luật sẵn có: dải cú pháp lạ coi như không giới hạn.
_goc_ver = packs._app_version
try:
    packs._app_version = lambda: ""
    check("không đọc được VERSION thì BỎ QUA chốt, không chặn sạch cả kho",
          packs._hop_compat(">=0.55.25")[0])
finally:
    packs._app_version = _goc_ver
check("dải cú pháp lạ vẫn coi như không giới hạn", packs._hop_compat("linh tinh")[0])

if _fails:
    print(f"\nFAIL - test_packs_kho_state: {len(_fails)} lỗi: {_fails}")
    sys.exit(1)
print("\nOK - test_packs_kho_state: tất cả pass")
