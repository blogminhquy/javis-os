"""Trang Công cụ: phần "công cụ tuỳ chọn" - thứ Javis dùng được nhưng không nhét sẵn vào bản cài.

Hiện chỉ có một mục: trình duyệt cho Javis tự kiểm thử giao diện. Lý do tách thành một tầng
riêng thay vì nhét thẳng vào ảnh nằm ở `server/optional_tools.py`.

Xác thực: theo đúng luật của trang Gói (`routes/packs.py`). Cài một công cụ là tải mã lạ về máy
và chạy nó, nên đường này đòi PHIÊN ĐĂNG NHẬP THẬT và KHÔNG nhận API token - "tự động tải một
trình duyệt về máy chủ" đúng là thứ không nên có đường tồn tại.
"""
from dataclasses import dataclass
from typing import Callable

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

import optional_tools

router = APIRouter()


@dataclass
class ToolsDeps:
    co_phien: Callable[[Request], bool]
    lam_moi_hub: Callable[[], None]


_DEPS: "ToolsDeps" = None   # type: ignore


def _tu_choi():
    return JSONResponse({"ok": False, "error": "cần đăng nhập"}, status_code=401)


def register(app, deps: ToolsDeps):
    global _DEPS
    _DEPS = deps

    @router.get("/tools/optional")
    async def tools_list(request: Request):
        if not _DEPS.co_phien(request):
            return _tu_choi()
        return {"ok": True, "tools": optional_tools.danh_sach()}

    @router.post("/tools/optional/install")
    async def tools_install(request: Request):
        """Bắt đầu tải ở NỀN rồi trả về ngay: tải cả trăm MB, giữ kết nối HTTP chờ nó xong là
        trình duyệt tự ngắt giữa chừng rồi người dùng tưởng hỏng. Màn hình hỏi tiến độ qua
        `GET /tools/optional`."""
        if not _DEPS.co_phien(request):
            return _tu_choi()
        d = await request.json()
        r = optional_tools.bat_dau_cai(str(d.get("id") or "browser"))
        return r if r.get("ok") else JSONResponse(r, status_code=400)

    @router.post("/tools/optional/remove")
    async def tools_remove(request: Request):
        if not _DEPS.co_phien(request):
            return _tu_choi()
        d = await request.json()
        r = optional_tools.go(str(d.get("id") or "browser"))
        if r.get("ok"):
            _DEPS.lam_moi_hub()
        return r if r.get("ok") else JSONResponse(r, status_code=400)

    app.include_router(router)
    return router
