"""Xoá kết nối phải xoá SẠCH, và không bao giờ xoá ra ngoài vùng của mình.

    python tests/run.py purge_ket_noi

Không cần pytest, không chạm mạng, không đụng STATE_DIR thật.

Bối cảnh (đo trên máy chủ repo 2026-09-03): `server/connector-home/` có 5 thư mục `zalo-*` mồ
côi trong khi `mcp_servers.json` không còn một kết nối Zalo nào, và một trong số đó vẫn giữ
credential phiên đăng nhập. Nghĩa là nút "Xoá kết nối" để lại đúng thứ người dùng bấm nút để
loại bỏ.

Ba lỗi gốc, và ba thứ test này canh:

1. THỨ TỰ. `/connect/delete` cũ gọi `mcp_store.delete_connection` TRƯỚC rồi mới
   `mcp_hub.invalidate_cache`, mà `invalidate_cache` lại đi vòng qua `list_connections()` để
   tìm phiên cần đóng. Hàng đã bị xoá nên phiên của chính nó không bao giờ được đóng và tiến
   trình con sống tới `_IDLE_TTL` = 900 giây. Nên phải canh: LÀM IM trước, XOÁ sau.

2. HAI DẠNG TÊN. `mcp_store.resolved` đặt home theo `<connector_id>-<slug>`, còn
   `zalo_login.start` đặt theo `zalo-<slug>-<sid6>` và ghi đường dẫn thật vào `config.home_dir`.
   Suy đường dẫn từ id với slug là bỏ sót đúng loại thư mục do quét QR tạo ra, tức đúng loại
   có credential.

3. CHỐT AN TOÀN. `config.home_dir` người dùng sửa được qua `POST /connect/update`. Không có
   chốt thì "xoá kết nối" là một lệnh rmtree trỏ đi đâu cũng được.
"""
from _paths import ROOT, SERVER, DASHBOARD  # noqa: E402,F401
import asyncio
import json
import sys
import tempfile
from pathlib import Path

import purge

_fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)


# ─────────────── 1. Chốt an toàn: không xoá ra ngoài vùng ───────────────
with tempfile.TemporaryDirectory() as td:
    tmp = Path(td)
    home = tmp / "connector-home"
    home.mkdir()
    (home / "that").mkdir()

    check("thư mục thật bên trong -> cho xoá", purge._an_toan_de_xoa(home / "that", home))
    check("chính base -> TỪ CHỐI", not purge._an_toan_de_xoa(home, home))
    check("gốc ổ đĩa -> TỪ CHỐI", not purge._an_toan_de_xoa(Path("C:/" if sys.platform == "win32" else "/"), home))
    check("leo ../.. ra ngoài -> TỪ CHỐI", not purge._an_toan_de_xoa(home / ".." / "..", home))
    check("anh em cùng cấp -> TỪ CHỐI", not purge._an_toan_de_xoa(tmp / "khac", home))
    check("None -> TỪ CHỐI", not purge._an_toan_de_xoa(None, home))

    # Symlink trỏ ra ngoài: phải resolve CẢ HAI vế mới bắt được. Bỏ qua khi HĐH không cho tạo
    # symlink (Windows đòi quyền), vì thiếu quyền không phải là lỗi của mã đang kiểm.
    ngoai = tmp / "ngoai"
    ngoai.mkdir()
    try:
        (home / "lien_ket").symlink_to(ngoai, target_is_directory=True)
        check("symlink trỏ ra ngoài -> TỪ CHỐI", not purge._an_toan_de_xoa(home / "lien_ket", home))
    except (OSError, NotImplementedError):
        print("bỏ qua symlink (hệ điều hành không cho tạo)")


# ─────────────── 2. Tìm home phải bắt được CẢ HAI dạng tên ───────────────
with tempfile.TemporaryDirectory() as td:
    tmp = Path(td)
    home = tmp / "connector-home"
    home.mkdir()
    goc_home, purge.HOME_DIR = purge.HOME_DIR, home
    try:
        # Dạng do zalo_login tạo: tên có hậu tố sid, và đường dẫn thật nằm ở config.home_dir.
        qr = home / "zalo-minh-quy-a9bef8"
        qr.mkdir()
        conn_qr = {"id": "c1", "connector_id": "zalo", "slug": "minh-quy",
                   "config": {"home_dir": str(qr)}}
        ra = purge._thu_muc_home(conn_qr)
        check("bắt được thư mục QR qua config.home_dir", qr in ra)

        # Dạng do mcp_store.resolved suy ra: <connector_id>-<slug>, không có config.home_dir.
        cong_thuc = home / "notebooklm-tk-chinh"
        cong_thuc.mkdir()
        conn_ct = {"id": "c2", "connector_id": "notebooklm", "slug": "tk-chinh", "config": {}}
        check("bắt được thư mục theo công thức id-slug", cong_thuc in purge._thu_muc_home(conn_ct))

        # config.home_dir trỏ ra NGOÀI vùng -> bỏ qua, không được đưa vào danh sách xoá.
        ngoai = tmp / "thu-muc-quy"
        ngoai.mkdir()
        conn_ngoai = {"id": "c3", "connector_id": "zalo", "slug": "x",
                      "config": {"home_dir": str(ngoai)}}
        check("home trỏ ra ngoài vùng -> KHÔNG đưa vào danh sách xoá",
              not purge._thu_muc_home(conn_ngoai))
        check("và thư mục đó vẫn còn nguyên", ngoai.is_dir())
    finally:
        purge.HOME_DIR = goc_home


# ─────────────── 3. THỨ TỰ: làm im trước, xoá sau ───────────────
# Đây là lỗi gốc, nên canh bằng cách ghi lại trình tự lời gọi thật chứ không đọc mã nguồn.
import capability_registry  # noqa: E402
import connect_health  # noqa: E402
import mcp_catalog  # noqa: E402
import mcp_client  # noqa: E402
import mcp_hub  # noqa: E402
import mcp_store  # noqa: E402
import oauth_mcp  # noqa: E402

with tempfile.TemporaryDirectory() as td:
    tmp = Path(td)
    for ten in ("connector-home", "connector-cred", "connector-files", "purge-trash"):
        (tmp / ten).mkdir()
    nhat_ky = []
    conn = {"id": "cid1", "connector_id": "zalo", "slug": "minh-quy", "label": "Zalo của Quý",
            "secrets": {"x": "enc:..."}, "config": {"home_dir": str(tmp / "connector-home" / "zalo-minh-quy-aa11bb")}}
    (tmp / "connector-home" / "zalo-minh-quy-aa11bb").mkdir()
    (tmp / "connector-home" / "zalo-minh-quy-aa11bb" / "cred.json").write_text("{}", encoding="utf-8")

    goc = {}
    for mod, ten in ((purge, "HOME_DIR"), (purge, "CRED_DIR"), (purge, "FILES_DIR"), (purge, "TRASH_DIR")):
        goc[ten] = getattr(mod, ten)
    purge.HOME_DIR = tmp / "connector-home"
    purge.CRED_DIR = tmp / "connector-cred"
    purge.FILES_DIR = tmp / "connector-files"
    purge.TRASH_DIR = tmp / "purge-trash"

    luu = {
        "get_connection": mcp_store.get_connection, "delete_connection": mcp_store.delete_connection,
        "forget_oauth": oauth_mcp.forget, "forget_health": connect_health.forget,
        "forget_rate": mcp_hub.forget_rate, "audit_scrub": mcp_hub.audit_scrub,
        "invalidate_cache": mcp_hub.invalidate_cache, "get_registry": capability_registry.get_registry,
        "close_now": mcp_client.pool.close_now, "dang_ban": mcp_client.pool.dang_ban_theo_key,
    }

    async def _close_now(key):
        nhat_ky.append("close_now")
        return True

    class _RegGia:
        def drop_connection(self, cid):
            nhat_ky.append("registry")
            return 1

    def _xoa(cid):
        nhat_ky.append("delete_connection")
        return True

    mcp_store.get_connection = lambda cid: (conn if cid == "cid1" else None)
    mcp_store.delete_connection = _xoa
    oauth_mcp.forget = lambda cid: nhat_ky.append("oauth")
    connect_health.forget = lambda cid: nhat_ky.append("health")
    mcp_hub.forget_rate = lambda cid: nhat_ky.append("rate")
    mcp_hub.audit_scrub = lambda cid, drop=False: (nhat_ky.append("audit"), 3)[1]
    mcp_hub.invalidate_cache = lambda: nhat_ky.append("invalidate")
    capability_registry.get_registry = lambda: _RegGia()
    mcp_client.pool.close_now = _close_now
    mcp_client.pool.dang_ban_theo_key = lambda key: False

    try:
        bc = asyncio.run(purge.purge_connection("cid1"))
        check("purge trả ok", bool(bc.get("ok")))
        check("LÀM IM đứng TRƯỚC xoá hàng (lỗi gốc: xoá trước nên không tìm ra phiên để đóng)",
              nhat_ky.index("close_now") < nhat_ky.index("delete_connection"))
        check("làm mới cache đứng SAU cùng",
              nhat_ky.index("invalidate") > nhat_ky.index("delete_connection"))
        for buoc in ("oauth", "health", "rate", "registry", "audit"):
            check("có gọi bước dọn: " + buoc, buoc in nhat_ky)

        # Thư mục có credential phải RỜI khỏi chỗ cũ (mặc định là chuyển vào thùng rác).
        check("thư mục home đã rời khỏi connector-home",
              not (tmp / "connector-home" / "zalo-minh-quy-aa11bb").exists())
        rac = list((tmp / "purge-trash").glob("conn-cid1__*"))
        check("và nằm trong thùng rác kèm phiếu ghi nguồn gốc",
              len(rac) == 1 and (rac[0] / "manifest.json").is_file())
        if rac:
            mf = json.loads((rac[0] / "manifest.json").read_text(encoding="utf-8"))
            check("phiếu ghi đúng conn_id", mf.get("conn_id") == "cid1")

        # Nhật ký: mặc định GIỮ, không xoá.
        check("nhật ký mặc định được GIỮ, không xoá",
              any(str(x).startswith("audit:") for x in bc.get("kept", [])))

        # Đang chạy dở một việc thì phải TỪ CHỐI, không giết ngang.
        nhat_ky.clear()
        mcp_client.pool.dang_ban_theo_key = lambda key: True
        bc2 = asyncio.run(purge.purge_connection("cid1"))
        check("đang chạy dở tool -> từ chối xoá", bc2.get("busy") is True and not bc2.get("ok"))
        check("và KHÔNG đụng gì cả", not nhat_ky)

        # gc_trash chỉ dọn thứ quá hạn.
        check("gc_trash chưa quá hạn thì không dọn", purge.gc_trash(days=30) == 0)
        check("gc_trash quá hạn thì dọn", purge.gc_trash(days=0) == 1)
    finally:
        for ten, v in goc.items():
            setattr(purge, ten, v)
        mcp_store.get_connection = luu["get_connection"]
        mcp_store.delete_connection = luu["delete_connection"]
        oauth_mcp.forget = luu["forget_oauth"]
        connect_health.forget = luu["forget_health"]
        mcp_hub.forget_rate = luu["forget_rate"]
        mcp_hub.audit_scrub = luu["audit_scrub"]
        mcp_hub.invalidate_cache = luu["invalidate_cache"]
        capability_registry.get_registry = luu["get_registry"]
        mcp_client.pool.close_now = luu["close_now"]
        mcp_client.pool.dang_ban_theo_key = luu["dang_ban"]


# ─────────────── 4. audit_scrub: giữ dòng, chỉ bỏ nhãn ───────────────
with tempfile.TemporaryDirectory() as td:
    p = Path(td) / "mcp_audit.jsonl"
    dong = [{"conn_id": "a", "label": "Cửa hàng của Quý", "tool": "pos_order"},
            {"conn_id": "b", "label": "Khác", "tool": "x"}]
    p.write_text("\n".join(json.dumps(d, ensure_ascii=False) for d in dong) + "\n", encoding="utf-8")
    goc_audit, mcp_hub._AUDIT_PATH = mcp_hub._AUDIT_PATH, p
    try:
        n = mcp_hub.audit_scrub("a")
        con = [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]
        check("audit_scrub chạm đúng 1 dòng", n == 1)
        check("GIỮ nguyên số dòng (nhật ký không tự xoá được)", len(con) == 2)
        check("đã bỏ tên hiển thị của kết nối bị xoá",
              [d for d in con if d["conn_id"] == "a"][0]["label"] == "")
        check("không đụng dòng của kết nối khác",
              [d for d in con if d["conn_id"] == "b"][0]["label"] == "Khác")
        mcp_hub.audit_scrub("a", drop=True)
        con2 = [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]
        check("drop=True thì mới thật sự xoá dòng", len(con2) == 1 and con2[0]["conn_id"] == "b")
    finally:
        mcp_hub._AUDIT_PATH = goc_audit


# ─────────────── 5. Endpoint và catalog ───────────────
src_main = (SERVER / "main.py").read_text(encoding="utf-8")
i_del = src_main.index('@app.post("/connect/delete")')
than_del = src_main[i_del:i_del + 1600]
check("/connect/delete đi qua purge.purge_connection", "purge.purge_connection" in than_del)
check("/connect/delete KHÔNG tự gọi delete_connection nữa (chỉ có MỘT chỗ biết cách dọn)",
      "mcp_store.delete_connection" not in than_del)
check("có endpoint /connect/purge-plan", '@app.get("/connect/purge-plan")' in src_main)
check("nhịp nền có dọn thùng rác", "purge.gc_trash" in src_main)

cat = json.loads((ROOT / "system" / "mcp-catalog.json").read_text(encoding="utf-8"))
by_id = {c["id"]: c for c in cat["connectors"]}
for cid in ("zalo", "notebooklm"):
    canh = (by_id.get(cid) or {}).get("purge_warning") or ""
    check(f"{cid} có cảnh báo mất phiên đăng nhập khi xoá", len(canh) > 30)
    check(f"{cid}: cảnh báo nói rõ phải đăng nhập lại", "lại" in canh)
# Cảnh báo phải nằm trong CATALOG chứ không viết cứng trong JS.
src_js = (DASHBOARD / "console.js").read_text(encoding="utf-8")
check("giao diện đọc cảnh báo từ dữ liệu, không viết cứng", "d.warning" in src_js)
check("hộp xác nhận vẽ từ /connect/purge-plan", "/connect/purge-plan" in src_js)


# ─────────────── 6. safeHref: nới cho đường dẫn nội bộ mà vẫn chặn XSS ───────────────
i_sh = src_js.index("const safeHref =")
than_sh = src_js[i_sh:i_sh + 400]
check("safeHref nhận đường dẫn cùng origin (link Hướng dẫn tự host hết chết)",
      "^\\\\/(?!\\\\/)" in than_sh or "/^\\/(?!\\/)/" in than_sh)
# Canary: mọi chỗ nhúng guide_url vào href PHẢI đi qua safeHref. esc() chỉ escape dấu ngoặc,
# không chặn được javascript:, nên bỏ sót một chỗ là mở lại đúng lỗ vừa vá.
bo_sot = [n for n, L in enumerate(src_js.splitlines(), 1)
          if "guide_url" in L and 'href="' in L and "safeHref" not in L]
check("mọi chỗ render guide_url đều qua safeHref: " + (str(bo_sot) if bo_sot else "đạt"), not bo_sot)

# ─────────────── 7. close_now phải CHỜ thật, khác invalidate bắn-rồi-quên ───────────────
src_cli = (SERVER / "mcp_client.py").read_text(encoding="utf-8")
i_cn = src_cli.index("async def close_now")
check("close_now await close() chứ không _close_later", "await ent[\"obj\"].close()" in src_cli[i_cn:i_cn + 900])
check("kill_tree đã gom về winproc, không nhân bản trong mcp_client",
      "winproc.kill_tree" in src_cli and "taskkill" not in src_cli)
check("zalo_login huỷ đăng nhập cũng giết cả cây tiến trình",
      "winproc.kill_tree" in (SERVER / "zalo_login.py").read_text(encoding="utf-8"))

if _fails:
    print(f"\nFAIL - test_purge_ket_noi: {len(_fails)} lỗi: {_fails}")
    sys.exit(1)
print("\nOK - test_purge_ket_noi: tất cả pass")
