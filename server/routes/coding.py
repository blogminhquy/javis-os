"""Route của trang Coding (0.63.0): sổ repo, ràng buộc phiên, worktree, điểm hồi.

    GET  /coding/repos                      sổ repo của brain
    POST /coding/repos                      thêm repo (kiểm .git)
    POST /coding/repos/{id}/delete          xoá khỏi SỔ, không đụng đĩa
    GET  /coding/session/{sid}              ràng buộc hiện tại của phiên
    POST /coding/session/{sid}              đặt repo / nhánh / mức quyền / worktree
    POST /coding/session/{sid}/checkpoint   tạo điểm hồi, trả tên tag
    POST /coding/session/{sid}/rollback     git reset --hard về một điểm hồi của phiên

Không có `deps`: mọi thứ nằm trong `coding_store`, không cần gì từ main. Giữ chữ ký
`register(app, deps=None)` cho đồng khuôn với các module cùng thư mục.
"""
from __future__ import annotations

from fastapi import APIRouter, Form, Query
from fastapi.responses import JSONResponse

import coding_store

router = APIRouter()


def _400(msg: str):
    return JSONResponse({"ok": False, "error": msg}, status_code=400)


def _bat(v) -> bool:
    return str(v or "").strip().lower() not in ("", "0", "false", "off", "no")


def _ve_repo(r: dict) -> dict:
    """Bản ghi repo cho giao diện, kèm hai thứ đọc từ git ngay lúc hỏi.

    `nhanh` và `co_that` đọc LIVE chứ không lưu vào sổ: người dùng đổi nhánh bằng terminal là
    chuyện thường, mà một con số cũ nằm trong sổ thì không có gì nhắc nó sai.
    """
    p = r.get("duong_dan") or ""
    co_that = coding_store.la_repo_git(p)
    return {
        "id": r.get("id"), "ten": r.get("ten"), "duong_dan": p,
        "nhanh_goc": r.get("nhanh_goc") or "",
        "co_that": co_that,
        "nhanh": coding_store.nhanh_hien_tai(p) if co_that else "",
        "nhanh_ds": coding_store.danh_sach_nhanh(p) if co_that else [],
    }


def _make_router() -> APIRouter:
    r = APIRouter()

    @r.get("/coding/repos")
    async def coding_repos(brain: str = Query("")):
        return {"repos": [_ve_repo(x) for x in coding_store.list_repos(brain)],
                "muc_quyen": list(coding_store.MUC_QUYEN),
                "muc_quyen_mac_dinh": coding_store.MUC_QUYEN_MAC_DINH}

    @r.post("/coding/repos")
    async def coding_repo_them(duong_dan: str = Form(...), brain: str = Form(""),
                               ten: str = Form("")):
        try:
            rec = coding_store.add_repo(duong_dan, brain=brain, ten=ten)
        except coding_store.LoiCoding as e:
            return _400(str(e))
        return {"ok": True, "repo": _ve_repo(rec)}

    @r.post("/coding/repos/{rid}/delete")
    async def coding_repo_xoa(rid: str):
        # Chỉ gỡ khỏi sổ. Nói rõ trong câu trả lời để giao diện nhắc lại được cho người dùng:
        # "đã bỏ khỏi Javis, mã nguồn còn nguyên trên đĩa".
        if not coding_store.remove_repo(rid):
            return JSONResponse({"ok": False, "error": "Không có repo nào id đó"}, status_code=404)
        return {"ok": True, "con_tren_dia": True}

    @r.get("/coding/session/{sid}")
    async def coding_phien(sid: str):
        rb = coding_store.rang_buoc(sid)
        repo = coding_store.get_repo(rb.get("repo") or "")
        cwd = coding_store.cwd_cua_phien(sid)
        return {
            "rang_buoc": rb,
            "repo": _ve_repo(repo) if repo else None,
            "cwd": cwd,
            "diem_hoi": coding_store.danh_sach_diem_hoi(sid),
            # Chưa gắn repo thì KHÔNG chạy git ở đâu cả. Suy biến về "." là chạy `git status`
            # trong thư mục của tiến trình server - trả lời về một repo người dùng không hỏi.
            "cay_sach": coding_store.cay_sach(cwd) if cwd else None,
        }

    @r.post("/coding/session/{sid}")
    async def coding_phien_dat(sid: str, repo: str = Form(None), nhanh: str = Form(None),
                               muc_quyen: str = Form(None), worktree: str = Form(None)):
        """`worktree` nhận "1" để MỞ một worktree mới, "0" để gỡ. Bỏ trống là không đụng tới.

        Một cờ chứ không phải đường dẫn: đường dẫn do kho tự đặt, cho người dùng gõ tay chỉ mở
        đường cho một giá trị trỏ ra ngoài repo.
        """
        try:
            rb = coding_store.dat_rang_buoc(sid, repo=repo, nhanh=nhanh, muc_quyen=muc_quyen)
            them = {}
            if worktree is not None and str(worktree).strip() != "":
                if _bat(worktree):
                    them = coding_store.tao_worktree(sid)
                else:
                    them = coding_store.go_worktree(sid)
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


def register(app, deps=None):
    """Gắn router vào app. Gọi ĐÚNG vị trí dòng cũ trong main.py - xem routes/__init__.py."""
    router = _make_router()
    app.include_router(router)
    return router
