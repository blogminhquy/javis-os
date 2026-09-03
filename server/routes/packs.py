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
from dataclasses import dataclass
from typing import Callable

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse

import pack_install
import packs

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


_DEPS: PacksDeps = None


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
        r = pack_install.cai(str(d.get("staging_id") or ""),
                             str(d.get("consent_sha256") or ""),
                             enable=bool(d.get("enable")))
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
