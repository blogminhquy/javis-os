"""Chat với cộng sự: phần THUẦN (không I/O) của trang Cộng sự.

Ba việc:
1. `persona_cua_phien`: đọc cột `channel` của một phiên ra ("agent"|"workflow", slug). main.py
   dùng nó ở bộ điều phối lượt để rẽ nhánh: phiên trợ lý đổi system prompt, phiên quy trình
   chạy `execute_workflow` thay vì hỏi bộ não chính.
2. Quy trình chạy như một lượt chat: `chay()` tiêu thụ luồng sự kiện của execute_workflow,
   đẩy khung WebSocket cho khung chat (status) và cột phải (wf_event), rồi trả về kết quả
   để main.py dựng tin trả lời bằng `tin_xong` / `tin_loi` / `tin_cho_duyet`. Tách khỏi
   main.py để test được bằng một generator giả, không cần engine.

3. `quyet_dinh_luot`: tin vừa gửi là MỘT LẦN CHẠY, hay là câu nói VỀ CHÍNH quy trình
   ("cập nhật lại workflow...", "đánh giá lại quy trình 7 bước", "gộp bớt bước")? Tin loại sau
   phải đi bộ não chính để đọc/sửa file quy trình, không được nhồi vào `{{input}}`.

Luật quan trọng: một lần chạy KHÔNG BAO GIỜ kết thúc mà không có tin trong chat. Luồng đứt
(engine chết không kịp phát `error`) vẫn thành `trang_thai="error"` với câu lỗi rõ.

Ghi chú: KHÔNG dùng ký tự em dash.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Any, Awaitable, Callable, Dict, Optional, Tuple

TRAN_KET_QUA_TRUOC = 8000
_LOAI = ("agent", "workflow")


def persona_cua_phien(row: Optional[dict]) -> Optional[Tuple[str, str]]:
    ch = str((row or {}).get("channel") or "")
    for loai in _LOAI:
        tien_to = loai + ":"
        if ch.startswith(tien_to) and len(ch) > len(tien_to):
            return loai, ch[len(tien_to):]
    return None


def ghep_dau_vao(user_message: str, ket_qua_truoc: str) -> str:
    """Tin sau trong cùng hội thoại vẫn hiểu được "sửa đoạn 2": nối kết quả lần trước vào."""
    u = str(user_message or "")
    k = str(ket_qua_truoc or "")
    if not k:
        return u
    return f"{u}\n\n# Kết quả lần trước\n{k[:TRAN_KET_QUA_TRUOC]}"


def tin_xong(so_lan: int, so_buoc: int, giay: int, ket_qua: str) -> str:
    than = str(ket_qua or "").strip() or "(quy trình xong nhưng không có nội dung)"
    return f"Lần chạy #{int(so_lan)} · {int(so_buoc)} bước · {int(giay)} giây\n\n{than}"


def tin_loi(i: Optional[int], agent: str, loi: str) -> str:
    loi = str(loi or "").strip() or "không rõ lý do"
    if i is None:
        return f"Quy trình dừng vì lỗi: {loi}"
    ten = f" ({agent})" if agent else ""
    return f"Quy trình dừng ở bước {int(i) + 1}{ten}: {loi}"


def tin_cho_duyet(node: str, prompt: str) -> str:
    p = str(prompt or "").strip()
    dau = f"Quy trình đang chờ duyệt bước \"{node}\""
    return (dau + (f": {p}" if p else "") + ". Bấm Duyệt ở cột phải để chạy tiếp.")


async def chay(events, emit: Callable[[dict], Awaitable[None]]) -> Dict[str, Any]:
    """Tiêu thụ luồng sự kiện của một lần chạy. `emit(frame)` gửi khung về trình duyệt.

    Khung phát ra:
    - `status` mỗi khi một bước bắt đầu (chip "đang làm" của khung chat);
    - `wf_event` cho MỌI sự kiện trừ `step_text` (cột phải vẽ tiến độ; step_text quá dày và
      cột phải không hiện chữ từng bước).
    Không phát `stream`: main.py gửi cả tin trả lời một lần sau khi có kết quả, để bong bóng
    sống và bản lưu giống hệt nhau.
    """
    kq: Dict[str, Any] = {"trang_thai": "error", "ket_qua": "", "so_buoc": 0, "loi": None,
                          "wait": None, "run_id": ""}
    agent_cua_buoc: Dict[int, str] = {}
    buoc_dang_chay: Optional[int] = None
    da_ket = False
    try:
        async for ev in events:
            t = ev.get("type")
            if t == "start":
                kq["so_buoc"] = int(ev.get("steps") or 0)
                kq["run_id"] = str(ev.get("run_id") or "")
            elif t == "step_start":
                i = int(ev.get("i") or 0)
                buoc_dang_chay = i
                agent_cua_buoc[i] = str(ev.get("agent") or "")
                tong = kq["so_buoc"] or (i + 1)
                await emit({"type": "status", "content": f"Bước {i + 1}/{tong}: {agent_cua_buoc[i]} đang làm..."})
            elif t == "done":
                kq["trang_thai"] = "done"
                kq["ket_qua"] = str(ev.get("result") or "")
                da_ket = True
            elif t == "error":
                # Lỗi của MỘT BƯỚC mang sẵn `i` và `agent` (main.py gắn khi bước hỏng): tin
                # theo nó trước. Chỉ rơi về "bước đang chạy" khi lỗi không thuộc bước nào
                # (không tìm thấy workflow, luồng đứt) - lúc đó `i` vắng mặt.
                i_loi = ev.get("i")
                i_loi = buoc_dang_chay if i_loi is None else int(i_loi)
                kq["trang_thai"] = "error"
                kq["loi"] = {"i": i_loi,
                             "agent": str(ev.get("agent") or agent_cua_buoc.get(
                                 i_loi if i_loi is not None else -1, "")),
                             "content": str(ev.get("content") or "")}
                da_ket = True
            elif t == "wait_user":
                kq["trang_thai"] = "waiting"
                kq["wait"] = dict(ev)
                da_ket = True
            if t != "step_text":
                await emit({"type": "wf_event", "event": dict(ev)})
    finally:
        aclose = getattr(events, "aclose", None)
        if aclose:
            try:
                await aclose()
            except Exception:
                pass
    if not da_ket:
        kq["trang_thai"] = "error"
        kq["loi"] = {"i": buoc_dang_chay, "agent": agent_cua_buoc.get(buoc_dang_chay if buoc_dang_chay is not None else -1, ""),
                     "content": "luồng chạy không kết thúc (engine dừng mà không báo)"}
    return kq


# ============================================================
# Tin NÓI VỀ chính quy trình, khác tin YÊU CẦU một lần chạy
# ============================================================
# Chuyện thật 16/09: ở phiên workflow:<slug>, mọi tin đều thành `{{input}}` của một lần chạy.
# Chủ dự án gõ "tôi muốn cập nhật lại workflow là có xuất bài viết ngay cả khi chưa đạt" và
# "tự đánh giá lại quy trình với 7 bước hiện tại, giảm số bước xuống" - hai câu nói VỀ quy
# trình - nên quy trình đem chúng đi viết bài: 7 bước, 640 giây, đốt hạn mức gói, trả ra một
# bản kiểm duyệt article.md chẳng liên quan gì tới câu hỏi.
#
# Chi phí của hai kiểu nhận nhầm KHÔNG bằng nhau, và đó là lý do chọn đoán thay vì hỏi lại:
#   - nhận nhầm tin nói-về-quy-trình thành lần chạy = 10 phút engine + hạn mức + kết quả rác;
#   - nhận nhầm một đề bài thành tin nói-về-quy-trình = một lượt chat rẻ, và câu trả lời có
#     kèm đúng một dòng chỉ cách ép chạy.
# Nên hàng rào này cố ý nghiêng về phía RẺ, và luôn nói ra là nó đã không chạy.

# Ép chạy: tiền tố ở đầu tin. Bấm nút "Chạy" ở cột phải gửi cờ `wf_run` nên không cần tiền tố.
TIEN_TO_CHAY = ("chay:", "run:")


def _khong_dau(s: str) -> str:
    """Bỏ dấu tiếng Việt + về chữ thường, để mẫu nhận dạng viết một lần là đủ.

    Người dùng gõ "quy trinh", "cap nhat" (không dấu) khá thường, nhất là trên điện thoại;
    khai hai bộ mẫu có dấu và không dấu thì thêm mẫu mới là chắc chắn lệch một bên."""
    x = unicodedata.normalize("NFD", str(s or ""))
    x = "".join(c for c in x if unicodedata.category(c) != "Mn")
    return x.replace("đ", "d").replace("Đ", "D").lower()


# ĐỘNG TỪ sửa/đánh giá. Cố ý KHÔNG có "chạy", "viết", "làm": đó là động từ của một đề bài.
_DONG_TU = (
    r"(?:danh gia|xem lai|ra soat|soat lai|kiem lai|cap nhat|sua|chinh|doi|viet lai|"
    r"thiet ke lai|toi uu|cai tien|hoan thien|rut gon|gian luoc|don gian hoa|gop|tach|"
    r"tom tat|giai thich|liet ke|bo|xoa|them|giam|bot|tang|"
    r"update|edit|change|evaluate|review|simplify|reduce|merge|summari[sz]e|explain|"
    r"optimi[sz]e)"
)
# DANH TỪ phải TỰ TRỎ vào quy trình đang mở. "quy trinh" trần KHÔNG tính: "viết bài tóm tắt
# quy trình làm nước mắm" là một đề bài, và nhận nhầm nó là câu hỏi về workflow thì người dùng
# mất một lần chạy họ thật sự muốn.
_DANH_TU = (
    r"(?:workflow|pipeline|steps|"
    r"quy trinh (?:nay|hien tai|tren|o day|dang mo|cua minh|cua toi)|"
    r"lai quy trinh|chinh quy trinh|so buoc|\d+ buoc|cac buoc (?:nay|hien tai)|buoc nao)"
)
# Hai chiều: động từ trước danh từ ("cập nhật lại workflow") và danh từ trước động từ
# ("quy trình này gộp bớt được không"). Khoảng cách tối đa 40 ký tự và KHÔNG vượt dấu kết câu:
# hai mệnh đề rời nhau trong cùng một tin thì không nói gì về nhau.
_KHONG_HET_CAU = r"[^.!?\n]{0,40}"
# Mẫu thứ ba: động từ DÍNH LIỀN "bước" ("bỏ bước kiểm chứng", "thêm bước QC ảnh", "gộp bước
# 2 và 3"). Đây là câu sửa cấu trúc quy trình rõ nhất mà hai mẫu trên không bắt được, vì danh
# từ ở đây là tên một bước cụ thể chứ không tự trỏ vào quy trình. Đòi DÍNH LIỀN nên "liệt kê
# các bước làm bánh" hay "viết bài theo từng bước" không lọt vào.
_MAU_SUA_BUOC = re.compile(r"\b(?:bo|xoa|them|gop|tach|doi|bot|giam|chen)\s+(?:mot\s+|1\s+)?buoc\b")
# Mẫu thứ tư: động từ SỬA dính liền "quy trình"/"workflow" mà sau đó KHÔNG phải một cụm định
# danh ("cập nhật quy trình:", "sửa quy trình đi", "rút gọn quy trình còn 4 bước").
# Vì sao phải xét cái đi sau: "viết bài tóm tắt quy trình làm nước mắm" cũng là động từ dính
# liền danh từ, nhưng "quy trình LÀM NƯỚC MẮM" là một quy trình KHÁC - đó là đề bài, nhận nhầm
# nó là người dùng mất đúng lần chạy họ muốn. Và động từ ở đây cố ý chỉ gồm nhóm SỬA/ĐÁNH GIÁ,
# không có "tóm tắt"/"giải thích"/"liệt kê": ba động từ đó là việc của một bài viết.
_DONG_TU_SUA = (
    r"(?:cap nhat|sua(?: lai)?|chinh(?: lai)?|doi|thiet ke lai|toi uu(?: lai)?|cai tien|"
    r"hoan thien|rut gon|gian luoc|don gian hoa|gop|tach|danh gia(?: lai)?|xem lai|"
    r"ra soat|soat lai|kiem lai|"
    r"update|edit|change|simplify|reduce|refactor|redesign|optimi[sz]e)"
)
_SAU_DANH_TU = (
    r"(?:$|[,.:;!?)\n]|\s+(?:nay|hien tai|tren|do|di|lai|voi|thanh|con|xuong|len|sao|"
    r"giup|cho|nhu|the|duoc|nhe)\b)"
)
_MAU_SUA_QUY_TRINH = re.compile(
    _DONG_TU_SUA + r"\s+(?:cai\s+|chinh\s+)?(?:quy trinh|workflow)" + _SAU_DANH_TU)
_MAU_VE_QUY_TRINH = (
    re.compile(_DONG_TU + r"\b" + _KHONG_HET_CAU + r"\b" + _DANH_TU),
    re.compile(_DANH_TU + r"\b" + _KHONG_HET_CAU + r"\b" + _DONG_TU),
    _MAU_SUA_BUOC,
    _MAU_SUA_QUY_TRINH,
)


def tach_lenh_chay(user_message: str) -> Tuple[bool, str]:
    """(ép chạy?, tin đã bỏ tiền tố). Tiền tố "chạy:" là đường thoát khi hàng rào đoán sai."""
    msg = str(user_message or "")
    dau = _khong_dau(msg.lstrip())
    for tt in TIEN_TO_CHAY:
        if dau.startswith(tt):
            return True, msg.lstrip()[len(tt):].lstrip()
    return False, msg


def la_tin_ve_quy_trinh(user_message: str) -> bool:
    """Tin này đang nói VỀ chính quy trình (sửa, đánh giá, tóm tắt nó) chứ không phải đề bài?"""
    dau = _khong_dau(user_message)
    if not dau.strip():
        return False
    return any(m.search(dau) for m in _MAU_VE_QUY_TRINH)


def quyet_dinh_luot(user_message: str, ep_chay: bool = False) -> Tuple[str, str]:
    """Rẽ nhánh một tin ở phiên workflow:<slug>. Trả ("chay"|"tra_loi", tin đã dọn tiền tố).

    Hàm THUẦN và module-level để test gọi thẳng: đây là chỗ quyết định một tin có đốt 10 phút
    engine hay không, mà quyết định không kiểm được thì không tin được.
    """
    tien_to, msg = tach_lenh_chay(user_message)
    if ep_chay or tien_to:
        return "chay", msg
    return ("tra_loi" if la_tin_ve_quy_trinh(msg) else "chay"), msg


def tin_khong_chay(ten: str = "") -> str:
    """Dòng nói THẲNG là lần chạy đã không khởi động, và cách ép chạy nếu đoán sai."""
    cua = f' "{ten}"' if str(ten or "").strip() else ""
    return ("Tin này đang nói về chính quy trình" + cua + " nên mình trả lời thay vì chạy nó. "
            "Muốn chạy thật với đúng câu này thì bấm nút Chạy ở cột phải, hoặc gửi lại với "
            "\"chạy:\" ở đầu tin.")


def khoi_quy_trinh_dang_mo(ten: str, slug: str, duong_dan: str, so_buoc: int,
                           buoc: Optional[list] = None) -> str:
    """Khối ngữ cảnh cho bộ não chính: người dùng đang đứng ở khung chat của quy trình nào.

    Cùng lối với khối "[FILE ĐANG MỞ...]" của trình sửa (xem CLAUDE.md): nói rõ file nào là
    đầu vào của lượt này, để câu "cập nhật lại workflow" không phải đoán xem workflow nào.
    Liệt kê luôn tên các bước - hỏi "gộp bớt bước được không" mà phải đi đọc file mới biết có
    những bước gì thì lượt trả lời nào cũng tốn thêm một vòng đọc file.
    """
    dong = [f"[QUY TRÌNH ĐANG MỞ trong trang Cộng sự: {ten} (slug: {slug}, {int(so_buoc)} bước)",
            f"File quy trình: {duong_dan}"]
    for i, b in enumerate(buoc or []):
        t = str((b or {}).get("task") or "").strip().replace("\n", " ")
        dong.append(f"  B{i + 1}. {(b or {}).get('agent') or '?'}: {t[:120]}")
    dong.append("Người dùng đang nói VỀ quy trình này, không phải đặt một đề bài cho nó. Đọc "
                "file trên trước khi trả lời; được yêu cầu sửa/gộp/thêm/bớt bước thì ghi thẳng "
                "vào chính file đó rồi nói đã đổi những gì. KHÔNG tự chạy quy trình.]")
    return "\n".join(dong)
