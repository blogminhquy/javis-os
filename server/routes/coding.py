"""Route của trang Coding (0.63.1): sổ thư mục, phiên, ràng buộc, worktree, điểm hồi.

    GET  /coding/folders                    sổ thư mục của brain
    POST /coding/folders                    thêm thư mục (KHÔNG đòi git)
    POST /coding/folders/{id}/delete        bỏ khỏi SỔ, không đụng đĩa
    GET  /coding/sessions                   phiên của trang Coding, kèm thư mục đang gắn
    GET  /coding/session/{sid}              ràng buộc hiện tại của phiên
    POST /coding/session/{sid}              đặt thư mục / nhánh / mức quyền / worktree
    POST /coding/session/{sid}/checkpoint   tạo điểm hồi, trả tên tag
    POST /coding/session/{sid}/rollback     git reset --hard về một điểm hồi của phiên

Vì sao có `/coding/sessions` riêng thay vì dùng `/sessions?channel=...`: từ 0.63.1 mọi phiên
Coding dùng CHUNG một kênh (`coding_store.KENH`), còn thư mục là ràng buộc đổi được. Muốn vẽ
danh sách phiên kèm tên thư mục thì phải ghép hai nguồn, và ghép ở server rẻ hơn bắt giao diện
gọi một lần cho mỗi phiên.

`deps` chỉ nhận đúng một thứ từ main: `brain_keys` (mọi cách viết cùng trỏ về một brain). Kho
phiên lưu nguyên văn chuỗi brain mà chỗ tạo phiên truyền vào, nên lọc bằng một chuỗi duy nhất
là bỏ sót - main đã có sẵn bộ bí danh đó, chép lại ở đây là để hai bản trôi lệch nhau.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Callable

from fastapi import APIRouter, Form, Query
from fastapi.responses import JSONResponse

import coding_store
import sessions

router = APIRouter()


@dataclass
class CodingDeps:
    brain_keys: Callable[[str], list]


_DEPS: "CodingDeps" = None   # type: ignore

# Trần khi quét phiên để ghép thư mục. Kho phiên không lọc được theo TIỀN TỐ kênh, nên đọc một
# mẻ rồi lọc trong Python; 300 là quá đủ cho một trang danh sách và vẫn rẻ.
QUET_TOI_DA = 300


def _400(msg: str):
    return JSONResponse({"ok": False, "error": msg}, status_code=400)


def _bat(v) -> bool:
    return str(v or "").strip().lower() not in ("", "0", "false", "off", "no")


def _ve_thu_muc(r: dict) -> dict:
    """Bản ghi thư mục cho giao diện, kèm ba thứ đọc từ đĩa NGAY LÚC HỎI.

    `co_that`, `la_git`, `nhanh` đọc LIVE chứ không lưu vào sổ: người dùng `git init`, đổi
    nhánh hay xoá thư mục bằng terminal là chuyện thường, mà một con số cũ nằm trong sổ thì
    không có gì nhắc nó đã sai.
    """
    p = r.get("duong_dan") or ""
    co_that = bool(p) and os.path.isdir(p)
    git = co_that and coding_store.la_git(p)
    return {
        "id": r.get("id"), "ten": r.get("ten"), "duong_dan": p,
        "co_that": co_that,
        "la_git": git,
        "nhanh": coding_store.nhanh_hien_tai(p) if git else "",
        "nhanh_ds": coding_store.danh_sach_nhanh(p) if git else [],
    }


def _make_router() -> APIRouter:
    r = APIRouter()

    @r.get("/coding/folders")
    async def coding_thu_muc_ds(brain: str = Query("")):
        return {"thu_muc": [_ve_thu_muc(x) for x in coding_store.danh_sach_thu_muc(brain)],
                "muc_quyen": list(coding_store.MUC_QUYEN),
                "muc_quyen_mac_dinh": coding_store.MUC_QUYEN_MAC_DINH,
                "kenh": coding_store.KENH}

    @r.post("/coding/folders")
    async def coding_thu_muc_them(duong_dan: str = Form(...), brain: str = Form(""),
                                  ten: str = Form("")):
        try:
            rec = coding_store.them_thu_muc(duong_dan, brain=brain, ten=ten)
        except coding_store.LoiCoding as e:
            return _400(str(e))
        return {"ok": True, "thu_muc": _ve_thu_muc(rec)}

    @r.post("/coding/folders/{tid}/delete")
    async def coding_thu_muc_bo(tid: str):
        # Chỉ gỡ khỏi sổ. Nói rõ trong câu trả lời để giao diện nhắc lại được cho người dùng:
        # "đã bỏ khỏi Javis, thư mục còn nguyên trên đĩa".
        if not coding_store.bo_thu_muc(tid):
            return JSONResponse({"ok": False, "error": "Không có thư mục nào id đó"}, status_code=404)
        return {"ok": True, "con_tren_dia": True}

    @r.get("/coding/sessions")
    async def coding_phien_ds(brain: str = Query(""), limit: int = Query(60)):
        """Phiên của trang Coding, mới nhất trước, kèm id và tên thư mục đang gắn.

        Nhận MỌI kênh bắt đầu bằng `coding:` chứ không riêng hằng hiện tại: phiên tạo ở 0.63.0
        mang kênh `coding:<id thư mục>`, bỏ chúng đi là người dùng cập nhật xong thấy lịch sử
        của mình biến mất.
        """
        kho = sessions.get_store()
        khoa = _DEPS.brain_keys(brain) if (_DEPS and brain) else None
        ds = kho.list_sessions(limit=QUET_TOI_DA, brain=khoa, channel="*")
        ten_thu_muc = {x["id"]: x for x in coding_store.danh_sach_thu_muc()}
        ra = []
        for s in ds:
            if not str(s.get("channel") or "").startswith("coding:"):
                continue
            rb = coding_store.rang_buoc(s["id"])
            tid = rb.get("thu_muc") or ""
            if not tid:
                # Phiên cũ 0.63.0: thư mục nằm trong tên kênh chứ chưa có trong ràng buộc.
                duoi = str(s.get("channel") or "").split(":", 1)[-1]
                if duoi in ten_thu_muc:
                    tid = duoi
            tm = ten_thu_muc.get(tid)
            ra.append({
                "id": s["id"], "title": s.get("title") or "", "preview": s.get("preview") or "",
                "updated_at": s.get("updated_at"), "msg_count": s.get("msg_count") or 0,
                "thu_muc": tid, "thu_muc_ten": (tm or {}).get("ten") or "",
                "muc_quyen": rb.get("muc_quyen") or coding_store.MUC_QUYEN_MAC_DINH,
            })
            if len(ra) >= max(1, limit):
                break
        return {"phien": ra, "kenh": coding_store.KENH}

    @r.get("/coding/session/{sid}")
    async def coding_phien(sid: str):
        rb = coding_store.rang_buoc(sid)
        tm = coding_store.thu_muc(rb.get("thu_muc") or "")
        cwd = coding_store.cwd_cua_phien(sid)
        return {
            "rang_buoc": rb,
            "thu_muc": _ve_thu_muc(tm) if tm else None,
            "cwd": cwd,
            "diem_hoi": coding_store.danh_sach_diem_hoi(sid),
            # Chưa gắn thư mục thì KHÔNG chạy git ở đâu cả. Suy biến về "." là chạy `git status`
            # trong thư mục của tiến trình server - trả lời về một cây người dùng không hỏi.
            "cay_sach": coding_store.cay_sach(cwd) if cwd else None,
        }

    @r.post("/coding/session/{sid}")
    async def coding_phien_dat(sid: str, thu_muc: str = Form(None), nhanh: str = Form(None),
                               muc_quyen: str = Form(None), worktree: str = Form(None)):
        """`worktree` nhận "1" để MỞ một worktree mới, "0" để gỡ. Bỏ trống là không đụng tới.

        Một cờ chứ không phải đường dẫn: đường dẫn do kho tự đặt, cho người dùng gõ tay chỉ mở
        đường cho một giá trị trỏ ra ngoài cây làm việc.
        """
        try:
            rb = coding_store.dat_rang_buoc(sid, thu_muc_id=thu_muc, nhanh=nhanh,
                                            muc_quyen=muc_quyen)
            them = {}
            if worktree is not None and str(worktree).strip() != "":
                them = coding_store.tao_worktree(sid) if _bat(worktree) else coding_store.go_worktree(sid)
                rb = coding_store.rang_buoc(sid)
        except coding_store.LoiCoding as e:
            return _400(str(e))
        return {"ok": True, "rang_buoc": rb, "cwd": coding_store.cwd_cua_phien(sid), **them}

    @r.post("/coding/session/{sid}/checkpoint")
    async def coding_diem_hoi(sid: str):
        try:
            return {"ok": True, **coding_store.tao_diem_hoi(sid)}
        except coding_store.LoiCoding as e:
            return _400(str(e))

    @r.post("/coding/session/{sid}/rollback")
    async def coding_rollback(sid: str, tag: str = Form(...)):
        try:
            return coding_store.rollback(sid, tag)
        except coding_store.LoiCoding as e:
            return _400(str(e))

    return r


def register(app, deps: "CodingDeps" = None):
    """Gắn router vào app. Gọi ĐÚNG vị trí dòng cũ trong main.py - xem routes/__init__.py."""
    global _DEPS
    _DEPS = deps
    router = _make_router()
    app.include_router(router)
    return router
