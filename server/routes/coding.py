"""Route của trang Coding (0.63.1): sổ thư mục, phiên, ràng buộc, worktree, điểm hồi.

    GET  /coding/folders                    sổ thư mục của brain
    POST /coding/folders                    thêm thư mục (KHÔNG đòi git)
    POST /coding/folders/{id}/delete        bỏ khỏi SỔ, không đụng đĩa
    GET  /coding/sessions                   phiên của trang Coding, kèm thư mục đang gắn
    GET  /coding/session/{sid}              ràng buộc hiện tại của phiên
    POST /coding/session/{sid}              đặt thư mục / nhánh / mức quyền / worktree
    POST /coding/session/{sid}/checkpoint   tạo điểm hồi, trả tên tag
    POST /coding/session/{sid}/rollback     git reset --hard về một điểm hồi của phiên
    GET  /coding/session/{sid}/undo         mốc tự động trước mỗi lượt có thay đổi (0.256.0)
    GET  /coding/session/{sid}/undo/{mid}   file khác nhau giữa mốc và hiện tại, kèm diff một file
    POST /coding/session/{sid}/undo/{mid}   Hoàn tác về mốc (an toàn: giữ file người dùng tự sửa)

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
from pathlib import Path
from dataclasses import dataclass
from typing import Callable

from fastapi import APIRouter, Form, Query
from starlette.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse

import coding_store
import localefmt
import sessions

router = APIRouter()


@dataclass
class CodingDeps:
    brain_keys: Callable[[str], list]
    # 0.158.0, composer pinned folder: resolve a browse-relative path (raises ValueError when it
    # leaves the ceiling) and give the brain root, both owned by main.
    resolve_path: Callable[[str, str], str] = None
    brain_root: Callable[[str], str] = None


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


def _folder_view(r):
    """English view of a registered folder for the composer chip (0.158.0)."""
    if not r:
        return None
    v = _ve_thu_muc(r)
    return {"id": v["id"], "name": v["ten"], "path": v["duong_dan"], "exists": v["co_that"], "is_git": v["la_git"]}


def _brain_fields(sid: str, brain: str) -> dict:
    """`in_brain` / `brain_rel` of the session's main folder, relative to the brain root."""
    out = {"in_brain": False, "brain_rel": ""}
    tm = coding_store.thu_muc(coding_store.rang_buoc(sid).get("thu_muc") or "")
    if not tm or not brain or not (_DEPS and _DEPS.brain_root):
        return out
    try:
        rel = Path(tm["duong_dan"]).resolve().relative_to(Path(_DEPS.brain_root(brain)).resolve()).as_posix()
        out = {"in_brain": True, "brain_rel": "" if rel == "." else rel}
    except (ValueError, OSError):
        pass
    # 0.159.0: extra folders bound before the composer pin existed (they still reach the prompt),
    # so the chip can show "+N" instead of hiding them.
    out["extra_folders"] = [r.get("ten") or "" for r in coding_store.thu_muc_cua_phien(sid)
                            if r.get("id") != tm.get("id") and r.get("nguon") != "github"]
    return out


def _session_view(sid: str, brain: str) -> dict:
    """GET /coding/session/{sid}: blocking git and disk reads, run in a worker thread."""
    rb = coding_store.rang_buoc(sid)
    tm = coding_store.thu_muc(rb.get("thu_muc") or "")
    cwd = coding_store.cwd_cua_phien(sid)
    return {
        "rang_buoc": rb,
        # `thu_muc` là thư mục CHÍNH (engine đứng ở đó, git chạy ở đó); `thu_muc_ds` là
        # cả tập phiên đang gắn, theo thứ tự, chính đứng đầu.
        "thu_muc": _ve_thu_muc(tm) if tm else None,
        "thu_muc_ds": [_ve_thu_muc(x) for x in coding_store.thu_muc_cua_phien(sid)],
        "cwd": cwd,
        "diem_hoi": coding_store.danh_sach_diem_hoi(sid),
        # Chưa gắn thư mục thì KHÔNG chạy git ở đâu cả. Suy biến về "." là chạy `git status`
        # trong thư mục của tiến trình server - trả lời về một cây người dùng không hỏi.
        "cay_sach": coding_store.cay_sach(cwd) if cwd else None,
        # 0.158.0: English fields for the composer chip (old fields above stay as they are).
        "folder": _folder_view(tm) if tm and tm.get("nguon") != "github" else None,
        **_brain_fields(sid, brain),
    }


def _pin(sid: str, raw: str, brain: str):
    """POST /coding/session/{sid}/pin body, run in a worker thread (git and disk reads).
    Returns (status, payload)."""
    try:
        # GitHub repos attached to the chat (0.362.0) are not the pinned folder: pinning or unpinning keeps them.
        repos = [r["id"] for r in coding_store.thu_muc_cua_phien(sid) if r.get("nguon") == "github"]
        if not raw:
            old = [r["id"] for r in coding_store.thu_muc_cua_phien(sid) if r.get("nguon") != "github"]
            coding_store.dat_rang_buoc(sid, thu_muc_ids=repos)
            # Forget folders no other conversation uses, so the registry does not grow forever.
            # Only the registry entries go; nothing on disk is touched.
            for tid in old:
                if not coding_store.sessions_using(tid):
                    coding_store.bo_thu_muc(tid)
            return 200, {"ok": True, "folder": None, "in_brain": False, "brain_rel": "", "extra_folders": []}
        if os.path.isabs(raw):
            target = raw
        else:
            if not (_DEPS and _DEPS.resolve_path):
                return 400, {"ok": False, "error": localefmt.chu("Không đọc được đường dẫn.", "Cannot read path.")}
            try:
                target = _DEPS.resolve_path(brain, raw)
            except ValueError as e:
                return 400, {"ok": False, "error": str(e)}
        rec = coding_store.them_thu_muc(target, brain=brain)
        # Re-pinning the folder that is already the main one changes nothing: rebinding would
        # reset the worktree, the branch and the extra folders of that session.
        if rec["id"] != (coding_store.rang_buoc(sid).get("thu_muc") or ""):
            if repos:
                coding_store.dat_rang_buoc(sid, thu_muc_ids=[rec["id"]] + [x for x in repos if x != rec["id"]])
            else:
                coding_store.dat_rang_buoc(sid, thu_muc_id=rec["id"])
    except coding_store.LoiCoding as e:
        return 400, {"ok": False, "error": str(e)}
    return 200, {"ok": True, "folder": _folder_view(rec), **_brain_fields(sid, brain)}


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
            return JSONResponse({"ok": False, "error": localefmt.chu("Không có thư mục nào id đó", "No folder with that id")}, status_code=404)
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
    async def coding_phien(sid: str, brain: str = Query("")):
        return await run_in_threadpool(_session_view, sid, brain)

    @r.post("/coding/session/{sid}/pin")
    async def coding_session_pin(sid: str, path: str = Form(""), brain: str = Form("")):
        """Pin (or unpin with an empty path) the conversation's working folder in one call.

        `path` is absolute (from the folder browser, same trust as POST /coding/folders) or
        relative as /files/list and /files/search return it. Registering and binding in one
        request means the UI can never leave a folder registered but not bound.
        """
        status, payload = await run_in_threadpool(_pin, sid, str(path or "").strip(), brain)
        return payload if status == 200 else JSONResponse(payload, status_code=status)

    @r.post("/coding/session/{sid}")
    async def coding_phien_dat(sid: str, thu_muc: str = Form(None), nhanh: str = Form(None),
                               muc_quyen: str = Form(None), worktree: str = Form(None),
                               thu_mucs: str = Form(None)):
        """`worktree` nhận "1" để MỞ một worktree mới, "0" để gỡ. Bỏ trống là không đụng tới.

        Một cờ chứ không phải đường dẫn: đường dẫn do kho tự đặt, cho người dùng gõ tay chỉ mở
        đường cho một giá trị trỏ ra ngoài cây làm việc.

        `thu_mucs` là danh sách id ngăn bằng dấu phẩy, đặt CẢ tập thư mục của phiên cùng lúc
        (0.63.8). Id đầu tiên là thư mục CHÍNH. Chuỗi rỗng nghĩa là gỡ hết.
        """
        try:
            ds = None
            if thu_mucs is not None:
                ds = [x.strip() for x in str(thu_mucs).split(",") if x.strip()]
            rb = coding_store.dat_rang_buoc(sid, thu_muc_id=thu_muc, nhanh=nhanh,
                                            muc_quyen=muc_quyen, thu_muc_ids=ds)
            them = {}
            if worktree is not None and str(worktree).strip() != "":
                them = coding_store.tao_worktree(sid) if _bat(worktree) else coding_store.go_worktree(sid)
                rb = coding_store.rang_buoc(sid)
        except coding_store.LoiCoding as e:
            return _400(str(e))
        return {"ok": True, "rang_buoc": rb, "cwd": coding_store.cwd_cua_phien(sid),
                "thu_muc_ds": coding_store.thu_muc_cua_phien(sid), **them}

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

    # ---- Hoàn tác về mốc tự động (0.256.0, coding_checkpoint) ----
    # Khác điểm hồi ở trên: mốc do Javis TỰ tạo trước thao tác thay đổi đầu tiên của mỗi lượt,
    # nằm trong kho git bóng (không đụng repo), có ở cả thư mục không phải git, và khôi phục
    # chọn lọc chứ không `reset --hard`.
    @r.get("/coding/session/{sid}/undo")
    async def coding_undo_ds(sid: str):
        import coding_checkpoint
        ds = await run_in_threadpool(coding_checkpoint.danh_sach, sid)
        return {"moc": [{k: x.get(k) for k in ("id", "ws", "luc", "luot", "ly_do")} for x in ds]}

    @r.get("/coding/session/{sid}/undo/{mid}")
    async def coding_undo_xem(sid: str, mid: str, file: str = Query("")):
        import coding_checkpoint
        try:
            if file:
                return {"diff": await run_in_threadpool(coding_checkpoint.diff_file, sid, mid, file)}
            td = await run_in_threadpool(coding_checkpoint.thay_doi, sid, mid)
            return {"file": td["file"], "ws": td["moc"].get("ws")}
        except coding_checkpoint.LoiMoc as e:
            return _400(str(e))

    @r.post("/coding/session/{sid}/undo/{mid}")
    async def coding_undo(sid: str, mid: str, tat_ca: str = Form(""), file: str = Form("")):
        import coding_checkpoint
        try:
            return await run_in_threadpool(coding_checkpoint.khoi_phuc, sid, mid, not _bat(tat_ca),
                                           str(file or "").strip())
        except coding_checkpoint.LoiMoc as e:
            return _400(str(e))

    return r


def register(app, deps: "CodingDeps" = None):
    """Gắn router vào app. Gọi ĐÚNG vị trí dòng cũ trong main.py - xem routes/__init__.py."""
    global _DEPS
    _DEPS = deps
    router = _make_router()
    app.include_router(router)
    return router
