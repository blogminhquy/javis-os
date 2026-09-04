"""Trang Gói: xem, cài từ tệp .zip, bật tắt, gỡ.

Bóc thành module riêng ngay từ đầu thay vì viết thẳng vào main.py (đã 14.6k dòng). Theo đúng
hai luật ở `routes/__init__.py`: không bao giờ `import main`, và lời gọi `register` trong
main.py phải nằm đúng vị trí vì `tests/python/route_table.json` khoá cả thứ tự.

Xác thực: mọi endpoint ở đây đòi PHIÊN ĐĂNG NHẬP THẬT
-----------------------------------------------------
Middleware xác thực của main.py chỉ chạy khi `cfgmod.gate_active()` là True, mà hàm đó trả
False trên một bản cài local chưa đặt mật khẩu. Với các trang khác thì đó là lựa chọn thoải mái
có chủ ý; với TRANG NÀY thì không, vì cài một gói là chạy mã lạ trong tiến trình server. Nên
`_doi_phien` kiểm độc lập, không phụ thuộc cổng chung.

Và cài KHÔNG nhận API token: token dành cho tự động hoá, mà "tự động cài một gói" đúng là thứ
không nên có đường tồn tại. Đường cài phải có người ngồi trước màn hình.

Cài hai bước
------------
`POST /packs/inspect` mở tệp, kiểm mọi luật, giải nén vào staging (NGOÀI thư mục kho, nên chưa
gì được nạp) rồi trả về đúng cái sắp xảy ra kèm `sha256`. `POST /packs/install` chỉ nhận nếu
người gọi đưa lại đúng sha256 đó - ràng buộc này làm cái đã hiện ra trên màn hình phải chính là
cái được cài.
"""
import sys
from dataclasses import dataclass
from typing import Callable

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse

import pack_install
import packs
import packs_fetch
import packs_store

# Chỉ ảnh, và KHÔNG SVG: một SVG phục vụ cùng origin thì trơ trong thẻ <img> nhưng chạy script
# khi người dùng mở thẳng nó ra một tab, tức là XSS trên chính origin của dashboard.
ANH = {".png": "image/png", ".webp": "image/webp", ".jpg": "image/jpeg",
       ".jpeg": "image/jpeg", ".gif": "image/gif"}

MAX_UPLOAD = pack_install.MAX_ZIP


@dataclass
class PacksDeps:
    """Thứ duy nhất cần từ main: cách hỏi "request này có phiên đăng nhập thật không"."""
    co_phien: Callable[[Request], bool]
    lam_moi_hub: Callable[[], None]
    brain_root: Callable[[str], str]


_DEPS: PacksDeps = None


def _nn(v, mac=""):
    """`name`/`description` là map đa ngôn ngữ. Lấy tiếng Việt, rơi về en, rồi về giá trị đầu."""
    if isinstance(v, dict):
        return v.get("vi") or v.get("en") or next(iter(v.values()), mac)
    return str(v or mac)


def _nhom(g: dict) -> str:
    """Tên NHÓM hiển thị của một mục trong kho.

    Gộp theo CHỮ NGƯỜI ĐỌC THẤY chứ không theo mã. Danh mục kho khai `category` là mã máy
    (`ban-hang`) kèm `category_label` để hiện; còn catalog connector đi kèm app từ xưa tới nay
    chỉ có một trường `category` viết thẳng tiếng Việt ("Bán hàng"). Gộp theo mã thì hai thứ
    cùng nghĩa nằm ở hai nhóm rời nhau, và cột nhóm bên trái hiện "Bán hàng" hai lần."""
    return _nn(g.get("category_label")) or str(g.get("category") or "") or "Khác"


def _id_app_dang_cap() -> set:
    """Id connector app đang THẬT SỰ cấp - đã trừ những cái người dùng gỡ đi.

    Trừ phần đã gỡ mới đúng: gỡ xong thì id không còn bị chiếm, nên gói trong kho cấp đúng id
    đó phải hiện ra và cài được. Không trừ thì người dùng gỡ một dịch vụ của app rồi không có
    đường nào lấy lại bản của kho."""
    try:
        import core_off
        import mcp_catalog
        return set(mcp_catalog.tat_ca() or {}) - core_off.da_go("connectors")
    except Exception:
        return set()


def _connector_cua_app() -> list:
    """Connector ship theo app, đóng gói lại thành mục của kho.

    `tat_ca()` trả về catalog ĐẦY ĐỦ kể cả cái đã gỡ - đúng thứ cần ở đây, vì cái đã gỡ phải
    hiện ra để bấm cài lại được. Cố ý KHÔNG lấy connector do gói cấp: gói đó đã là một mục
    riêng trong kho rồi, liệt kê thêm connector của nó là đếm hai lần."""
    try:
        import core_off
        import mcp_catalog
        # Khoá là "connectors" số NHIỀU (`core_off.LOAI`). Gõ số ít thì `da_go` trả rỗng một
        # cách hoàn toàn im lặng, và mọi connector mãi mãi hiện là "đã cài" - kể cả cái vừa gỡ.
        da_go = core_off.da_go("connectors")
        ra = []
        for cid, c in (mcp_catalog.tat_ca() or {}).items():
            # Chạy LỆNH thì là bậc code, dù không một dòng Python nào: `transport: stdio` khiến
            # Javis chạy `npx` với toàn bộ biến môi trường của máy chủ.
            code = str(c.get("transport") or "http").lower() == "stdio" or bool(c.get("command"))
            nhom = str(c.get("category") or "Khác")
            ra.append({
                "id": cid, "kind": "connector",
                "name": {"vi": c.get("name", cid)},
                "description": {"vi": c.get("description", "")},
                "version": "", "author": {"name": "Javis"},
                "category": nhom, "category_label": {"vi": nhom}, "nhom": nhom,
                "tier": "code" if code else "data",
                "verified": True, "icon": c.get("icon", ""),
                "installed": cid not in da_go, "installed_version": "",
                "nguon": "app",
                "download": {"url": "", "sha256": "", "size": 0},
            })
        return ra
    except Exception as e:
        # Kho vẫn phải vẽ được nếu chỗ này hỏng: mục tải từ kho không dính dáng gì tới catalog.
        print(f"[packs] không gộp được connector của app vào kho: {e}", file=sys.stderr)
        return []


def _tu_choi():
    return JSONResponse({"ok": False, "error": "Cần đăng nhập vào Javis để quản lý gói."},
                        status_code=401)


def _make_router() -> APIRouter:
    router = APIRouter()

    @router.get("/packs")
    async def packs_list(request: Request):
        if not _DEPS.co_phien(request):
            return _tu_choi()
        return {"packs": packs.installed(), "dir": str(packs.PACKS_DIR),
                "disabled": packs.tat_het(), "ledger": pack_install.doc_so(),
                "max_mb": MAX_UPLOAD // 1024 // 1024}

    @router.post("/packs/inspect")
    async def packs_inspect(request: Request, file: UploadFile = File(...)):
        """Soi tệp .zip rồi trả về đúng cái sắp xảy ra. Chưa đặt gì vào kho."""
        if not _DEPS.co_phien(request):
            return _tu_choi()
        # Đọc theo KHỐI và bỏ ngay khi vượt trần: `await file.read()` nạp cả tệp vào RAM rồi
        # mới kiểm, tức một tệp 2GB làm hết bộ nhớ máy chủ trước khi tới được dòng kiểm.
        khoi, tong = [], 0
        while True:
            b = await file.read(1 << 20)
            if not b:
                break
            tong += len(b)
            if tong > MAX_UPLOAD:
                return JSONResponse({"ok": False, "stage": "verify",
                                     "error": f"tệp quá lớn, trần {MAX_UPLOAD // 1024 // 1024}MB"},
                                    status_code=413)
            khoi.append(b)
        return pack_install.soi(b"".join(khoi), (file.filename or "").strip())

    @router.post("/packs/install")
    async def packs_install(request: Request):
        if not _DEPS.co_phien(request):
            return _tu_choi()
        d = await request.json()
        # `source` do client gửi lại nguyên văn từ kết quả soi, chỉ để GHI VÀO SỔ cho biết gói
        # này đến từ đâu. Không có gì trong hệ thống tin vào nó, nên nó chỉ là ghi chú.
        ng = d.get("source") if isinstance(d.get("source"), dict) else None
        if ng:
            ng = {"kind": str(ng.get("kind") or "")[:16], "url": str(ng.get("url") or "")[:500]}
        # Brain ĐANG MỞ lúc bấm Cài. Agent/workflow/skill thuộc về một brain cụ thể (khác
        # connector và plugin vốn dùng chung mọi brain), nên "cài vào tất cả" là áp đặt: người
        # dùng có brain việc và brain cá nhân, và họ không muốn mọi thứ ở cả hai nơi.
        r = pack_install.cai(str(d.get("staging_id") or ""),
                             str(d.get("consent_sha256") or ""),
                             enable=bool(d.get("enable")), nguon=ng,
                             brain_root=_DEPS.brain_root(str(d.get("brain") or "brain")))
        if r.get("ok"):
            _DEPS.lam_moi_hub()
        return r if r.get("ok") else JSONResponse(r, status_code=400)

    @router.post("/packs/toggle")
    async def packs_toggle(request: Request):
        if not _DEPS.co_phien(request):
            return _tu_choi()
        d = await request.json()
        r = pack_install.dat_bat_tat(str(d.get("id") or ""), bool(d.get("enabled")))
        if r.get("ok"):
            _DEPS.lam_moi_hub()
        return r if r.get("ok") else JSONResponse(r, status_code=400)

    @router.get("/packs/uninstall-plan")
    async def packs_uninstall_plan(request: Request, id: str = ""):
        if not _DEPS.co_phien(request):
            return _tu_choi()
        return pack_install.ke_hoach_go(id.strip())

    @router.post("/packs/uninstall")
    async def packs_uninstall(request: Request):
        if not _DEPS.co_phien(request):
            return _tu_choi()
        d = await request.json()
        r = await pack_install.go(str(d.get("id") or ""),
                                  purge_data=bool(d.get("purge_data")),
                                  purge_audit=bool(d.get("purge_audit")))
        if r.get("ok"):
            _DEPS.lam_moi_hub()
        return r if r.get("ok") else JSONResponse(r, status_code=409)

    @router.get("/packs/store")
    async def packs_store_list(request: Request, refresh: int = 0):
        """Danh mục gói trong kho. Fetch ở PHÍA SERVER, không ở trình duyệt.

        Ba lý do: chốt SSRF nằm ở server nên đường tải phải đi qua đó mới được gác; trình
        duyệt sẽ vướng CORS với phần lớn nơi đặt tệp; và nếu về sau có kho riêng cần token thì
        token không bao giờ nên rơi vào JavaScript."""
        if not _DEPS.co_phien(request):
            return _tu_choi()
        d = await packs_store.lay(lam_moi=bool(refresh))
        # Dịch vụ mà APP đang cấp. Gói trong kho cấp đúng id đó thì BỎ thẻ của kho đi: `packs.py`
        # từ chối cài một connector trùng id với kho gốc (một gói ship `id: pancake-pos` kèm
        # url khác sẽ âm thầm bẻ hướng một kết nối đang đăng nhập thật), nên thẻ đó bấm cũng
        # không cài được. Hiện hai thẻ cho cùng một dịch vụ, một cái vô dụng, là tệ hơn hẳn.
        #
        # Người dùng gỡ dịch vụ của app đi thì id thôi bị chiếm, thẻ của kho hiện ra và cài
        # được - đó chính là đường di trú dần từ app sang kho.
        app_dang_cap = _id_app_dang_cap()
        d["packs"] = [g for g in (d.get("packs") or [])
                      if not (set((g.get("provides") or {}).get("connectors") or [])
                              & app_dang_cap)]
        # Gói nào đã cài rồi thì đánh dấu, để lưới hiện "Đã cài" thay vì mời cài lại.
        da_cai = pack_install.doc_so()
        for g in d.get("packs") or []:
            hang = da_cai.get(g["id"])
            g["installed"] = bool(hang)
            g["installed_version"] = (hang or {}).get("version", "")
            g["nguon"] = "kho"
            g["nhom"] = _nhom(g)
        # Connector đi kèm app cũng hiện TRONG kho, đánh dấu sẵn là đã cài. Người dùng không
        # phân biệt "thứ ship theo app" với "thứ tải từ kho" - họ chỉ muốn một chỗ để nhìn xem
        # Javis nối được với cái gì. Trộn vào đây thì lưới Kết nối của kho có đủ mặt hàng ngay
        # từ ngày đầu, thay vì trống trơn cho tới khi ai đó phát hành gói connector.
        #
        # Chúng KHÔNG tải về từ đâu cả (`download.url` rỗng), và gỡ chúng đi qua `core_off`
        # chứ không qua trình gỡ gói - nên phải có `nguon` để giao diện biết bấm nút nào.
        (d.setdefault("packs", [])).extend(_connector_cua_app())
        return d

    @router.post("/packs/install-url")
    async def packs_install_url(request: Request):
        """Tải một gói từ địa chỉ rồi SOI như tệp tải lên. Chưa cài gì cả.

        Cố ý dừng ở bước soi: đường từ kho về máy không được phép ngắn hơn đường từ tệp. Cùng
        một màn hình xác nhận, cùng một chốt dấu vân tay - chỉ khác chỗ lấy byte."""
        if not _DEPS.co_phien(request):
            return _tu_choi()
        d = await request.json()
        try:
            url = packs_fetch.url_zip_github(str(d.get("url") or ""))
            du_lieu = await packs_fetch.tai(url)
        except packs_fetch.LoiTai as e:
            return JSONResponse({"ok": False, "stage": "download", "error": str(e)},
                                status_code=400)
        r = pack_install.soi(du_lieu, url.rsplit("/", 1)[-1] or "goi.zip")
        # Kho khai sẵn dấu vân tay thì đối chiếu NGAY: một tệp khác cái kho nói là dấu hiệu
        # đường tải bị chen ngang, và đó là lúc phải dừng chứ không phải lúc hỏi người dùng.
        mong = str(d.get("expect_sha256") or "").strip()
        if mong and r.get("ok") and r.get("sha256") != mong:
            return JSONResponse(
                {"ok": False, "stage": "verify",
                 "error": "Tệp tải về không khớp dấu vân tay mà kho công bố. Đã dừng."},
                status_code=400)
        r["source"] = {"kind": "url", "url": url}
        return r if r.get("ok") else JSONResponse(r, status_code=400)

    @router.get("/packs/token")
    async def packs_token_list(request: Request):
        """Danh sách host đã lưu token. KHÔNG bao giờ trả giá trị token."""
        if not _DEPS.co_phien(request):
            return _tu_choi()
        import config as cfgmod
        kho = (cfgmod.read_settings().get("packs") or {}).get("tokens") or {}
        return {"hosts": sorted(kho)}

    @router.post("/packs/token")
    async def packs_token_set(request: Request):
        """Lưu hoặc xoá token cho một host. Token được mã hoá khi ghi xuống đĩa."""
        if not _DEPS.co_phien(request):
            return _tu_choi()
        import config as cfgmod
        d = await request.json()
        host = str(d.get("host") or "").strip().lower()
        if not host or "/" in host or " " in host:
            return JSONResponse({"ok": False, "error": "Tên máy không hợp lệ"}, status_code=400)
        tk = str(d.get("token") or "").strip()
        cfg = cfgmod.read_settings()
        kho = dict((cfg.get("packs") or {}).get("tokens") or {})
        if tk:
            kho[host] = tk
        else:
            kho.pop(host, None)
        cfg.setdefault("packs", {})["tokens"] = kho
        cfgmod.write_settings(cfg)
        return {"ok": True, "hosts": sorted(kho)}

    @router.get("/packs/{pid}/asset/{duong:path}")
    async def packs_asset(pid: str, duong: str):
        """Ảnh của gói. KHÔNG đòi phiên: nó đi vào thẻ <img> của trang Kết nối như mọi logo
        khác, và nội dung là thứ chính người dùng vừa cài. Bù lại thì chặt về KIỂU tệp."""
        f = packs.asset_path(pid, duong)
        if f is None or f.suffix.lower() not in ANH:
            return JSONResponse({"error": "not found"}, status_code=404)
        return FileResponse(str(f), media_type=ANH[f.suffix.lower()], headers={
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "default-src 'none'; sandbox",
            "Cache-Control": "public, max-age=300",
        })

    return router


def register(app, deps: PacksDeps):
    """Gắn router vào app. Gọi ĐÚNG vị trí dòng cũ trong main.py - xem routes/__init__.py."""
    global _DEPS
    _DEPS = deps
    router = _make_router()
    app.include_router(router)
    return router
