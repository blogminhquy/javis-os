"""Việc nền của MỘT khung chat + bắt lời hứa suông.

Vì sao có file này
==================
Chủ repo báo (2026-08-06), kèm ảnh chụp: Javis đáp "Em đang dò code để xem trong nhóm bot có
lọc tin nhắn hay không, có kết quả em báo ngay" - rồi im lặng vĩnh viễn. Không có báo cáo nào
về, và người dùng cũng KHÔNG có cách nào biết là có agent nào đang chạy thật hay không.

Ba gốc rễ tách bạch, file này lo hai cái đầu:

1. **Hứa suông.** Lượt trả lời đóng lại ngay khi model nói xong; không ai đánh thức nó dậy để
   "báo ngay". Prompt đã cấm kiểu hứa "em sẽ đợi các agent chạy xong rồi tổng hợp", nhưng câu
   trên KHÔNG rơi vào mẫu đó - nó hứa theo kiểu "đang làm, xong báo". Chặn bằng prompt là trò
   đuổi bắt chữ, nên ở đây ta kiểm chứng bằng SỰ THẬT: lượt vừa rồi có tạo được việc nền nào
   không. Không có mà vẫn hứa thì Javis tự nói ra điều đó ngay dưới câu trả lời, thay vì để
   người dùng ngồi đợi một báo cáo không bao giờ tới.

2. **Không thấy gì đang chạy.** Việc nền có thật thì cũng không hiện ở đâu trong khung chat.
   `active_view()` gom đúng những thứ SẼ tự nói chuyện lại với khung chat này (việc Kanban,
   loop, nhắc hẹn) để dashboard vẽ thành một dải trạng thái sống.

3. (Ngoài file này) **Điều phối mặc định TẮT** nên việc giao từ chat nằm im mãi - xem
   `tasks.TaskRunner._dispatch` và plugin `javis-task`.

Nguyên tắc: file này KHÔNG chặn, KHÔNG sửa câu trả lời của model. Nó chỉ nói thêm sự thật.
"""
from __future__ import annotations

import re
import unicodedata

# Việc Kanban còn "sống" - tức là còn có ngày nó chạy rồi báo về. Khớp với
# task_store.ACTIVE_STATUS, chép lại ở đây để module này không phải nạp cả tầng task.
ACTIVE_TASK_STATUS = ("triage", "todo", "ready", "running", "review", "blocked")

# Trần số mục trả về cho dải trạng thái. Dải chat là chỗ liếc mắt, không phải trang Việc.
MAX_ITEMS = 12


def _norm(value: str) -> str:
    """Bỏ dấu + hạ chữ thường để mẫu regex viết bằng ASCII khớp được tiếng Việt thật.

    NFKD KHÔNG phân rã "đ" (U+0111) nên phải map tay - cùng cái bẫy đã ăn một lần ở
    `fast_path_runtime._norm`: thiếu dòng này thì mọi mẫu chứa "dang", "do", "doi" im lặng
    không bao giờ khớp.
    """
    raw = str(value or "").replace("đ", "d").replace("Đ", "D")
    raw = unicodedata.normalize("NFKD", raw.casefold())
    return " ".join("".join(c for c in raw if not unicodedata.combining(c)).split())


# Khối mã và trích dẫn nguyên văn KHÔNG tính: model dán lại code hay dán lại câu của người
# khác thì đó không phải lời hứa của nó.
_CODE_FENCE = re.compile(r"```.*?```", re.S)
_INLINE_CODE = re.compile(r"`[^`\n]*`")

# Mẫu lời hứa "sẽ báo lại sau". Cố ý viết hẹp: bắt nhầm một câu vô hại thì Javis tự dán một
# dòng cảnh báo thừa dưới câu trả lời đúng - phiền, và làm người dùng mất tin vào dòng đó.
_PROMISE = (
    # "có kết quả em báo ngay" / "khi nào xong em gửi anh"
    ("co_ket_qua", re.compile(
        r"\b(co|khi co|khi nao co|neu co)\s+ket qua\b[^.!?]{0,40}?\b(em|minh|toi)\b[^.!?]{0,25}?"
        r"\b(bao|gui|cap nhat|tra loi|noi)\b"
    )),
    # "em sẽ báo lại", "em báo anh ngay", "em sẽ cập nhật lại cho anh"
    ("se_bao_lai", re.compile(
        r"\b(em|minh|toi)\s+(se\s+|xin\s+)?"
        r"(bao lai|bao ngay|bao anh|bao chi|bao ban|bao sau|bao lien|"
        r"cap nhat lai|cap nhat cho|thong bao lai|thong bao cho|"
        r"gui lai ket qua|quay lai bao|quay lai voi)\b"
    )),
    # "xong em báo", "làm xong em gửi anh"
    ("xong_em_bao", re.compile(
        r"\bxong\s+(roi\s+|thi\s+)?(em|minh|toi)\s+(se\s+)?(bao|gui|noi|cap nhat)\b"
    )),
    # "anh chờ em chút", "đợi em một lát"
    ("cho_em", re.compile(
        r"\b(cho|doi)\s+(em|minh)\s+(mot\s+)?(chut|ti|lat|xiu|it phut|vai phut)\b"
    )),
    # Mẫu cũ đã có luật cấm trong prompt: "em sẽ đợi ... rồi tổng hợp"
    ("doi_roi_tong_hop", re.compile(
        r"\b(em|minh|toi)\s+se\s+(doi|cho|theo doi)\b[^.!?]{0,60}?"
        r"\b(roi|xong|sau do)\b[^.!?]{0,30}?\b(tong hop|bao|gui|cap nhat)\b"
    )),
    # Đúng câu chủ repo chụp được: "Em đang dò code ... có kết quả em báo ngay".
    # Bắt cả trường hợp vế sau không có chữ "kết quả": "em đang kiểm tra, xong em nói anh".
    ("dang_lam_se_bao", re.compile(
        r"\b(em|minh|toi)\s+(dang|se)\s+"
        r"(do|kiem tra|ra soat|ra lai|tra|tra cuu|tim|chay|lam|phan tich|xu ly|xem lai|doc lai)\b"
        r"[^.!?]{0,90}?\b(bao|gui|cap nhat|thong bao)\b"
    )),
    # "để em chạy thử rồi cập nhật cho anh sau" - cùng kiểu hẹn, chỉ khác chủ ngữ đứng sau "để".
    ("de_em_lam", re.compile(
        r"\b(de|cho)\s+(em|minh|toi)\s+"
        r"(do|kiem tra|ra soat|tra|tra cuu|tim|chay|lam|thu|xem|doc|phan tich|xu ly)\b"
        r"[^.!?]{0,80}?\b(roi|xong|sau do)\b[^.!?]{0,30}?"
        r"\b(bao|gui|cap nhat|thong bao|noi lai|tra loi)\b"
    )),
    ("english", re.compile(
        r"\b(i(?:'| wi)?ll|i will|we(?:'| wi)?ll|we will)\s+"
        r"(get back to you|report back|update you|let you know|keep you posted)\b"
    )),
)


def detect_promise(text: str) -> str:
    """Tên mẫu lời hứa "sẽ báo lại sau" trong câu trả lời, hoặc "" nếu không có.

    Trả về TÊN mẫu (không phải bool) để log/trace nói được là bắt bằng mẫu nào - lúc cần nới
    hay siết mẫu thì có số liệu thật thay vì đoán.
    """
    raw = str(text or "")
    if not raw.strip():
        return ""
    raw = _INLINE_CODE.sub(" ", _CODE_FENCE.sub(" ", raw))
    norm = _norm(raw)
    for name, pattern in _PROMISE:
        if pattern.search(norm):
            return name
    return ""


def promise_note(orchestration: str = "") -> str:
    """Dòng sự thật dán dưới câu trả lời có hứa mà KHÔNG có việc nền nào.

    Viết ở ngôi Javis, bằng lời nói, không bảng và không em dash (luật CLAUDE.md).
    """
    lines = [
        "⚠ Javis tự kiểm: lượt vừa rồi em có hứa sẽ báo lại, nhưng em KHÔNG tạo việc nền nào "
        "nên sẽ không có báo cáo nào tự về đây. Lượt trả lời của em đóng lại ngay khi em nói "
        "xong, không có ai đánh thức em dậy để làm nốt.",
        "Anh nhắn lại một câu là em làm ngay trong lượt sau, hoặc bảo em \"giao thành việc "
        "nền\" để em đẩy vào hàng đợi và kết quả tự rơi về khung chat này.",
    ]
    if orchestration and orchestration != "auto":
        lines.append(
            "Nói thêm cho rõ: điều phối việc nền của brain này đang ở mức "
            f"\"{orchestration}\", nghĩa là việc giao vào cũng chỉ nằm xếp hàng chứ chưa tự "
            "chạy. Bật \"AI tự vận hành\" ở trang Việc nếu anh muốn nó chạy một mình."
        )
    return "\n\n".join(lines)


def _task_item(task: dict, chat_id: str) -> dict:
    tid = str(task.get("id") or "")
    return {
        "kind": "task",
        "id": tid,
        "title": str(task.get("title") or tid)[:160],
        "status": str(task.get("status") or "triage"),
        "mine": bool(chat_id) and str(task.get("chat_id") or "") == chat_id,
        "at": float(task.get("updated_at") or task.get("created_at") or 0),
    }


def _loop_item(loop: dict, chat_id: str, running_slug: str) -> dict:
    slug = str(loop.get("slug") or "")
    return {
        "kind": "loop",
        "id": slug,
        "title": str(loop.get("name") or slug)[:160],
        "status": "running" if (running_slug and running_slug == slug) else "enabled",
        "mine": bool(chat_id) and str(loop.get("owner_chat") or "") == chat_id,
        "at": 0.0,
    }


def _reminder_item(rem: dict, chat_id: str) -> dict:
    rid = str(rem.get("id") or "")
    return {
        "kind": "reminder",
        "id": rid,
        "title": str(rem.get("label") or rem.get("text") or rid)[:160],
        "status": "pending",
        "mine": bool(chat_id) and str(rem.get("chat_id") or "") == chat_id,
        "at": float(rem.get("due_at") or 0),
        "due": str(rem.get("due_human") or ""),
    }


def active_view(tasks: list, loops: list, reminders: list, chat_id: str = "",
                orchestration: str = "off", running_loop: str = "") -> dict:
    """Gom việc nền còn sống thành một khung nhìn cho dải trạng thái của khung chat.

    Nhận dữ liệu THÔ đã đọc sẵn (không tự đi đọc kho) để test được mà không cần dựng cả server.

    `mine` = việc gắn đúng khung chat này (`chat_id` / `owner_chat` khớp). Việc của người khác
    vẫn hiện, nhưng đếm riêng: người dùng cần phân biệt "máy đang bận" với "việc CỦA TÔI đang
    chạy" - gộp một cục là quay lại đúng chỗ mù mà bản này đang đi sửa.
    """
    cid = str(chat_id or "").strip()
    items = []
    for t in tasks or []:
        if str(t.get("status") or "") in ACTIVE_TASK_STATUS:
            items.append(_task_item(t, cid))
    for lp in loops or []:
        if lp.get("enabled"):
            items.append(_loop_item(lp, cid, str(running_loop or "")))
    for r in reminders or []:
        items.append(_reminder_item(r, cid))

    # Việc CỦA KHUNG CHAT NÀY lên đầu, rồi tới việc đang chạy thật, rồi mới tới phần còn lại.
    order = {"running": 0, "review": 1, "blocked": 2, "ready": 3,
             "todo": 4, "triage": 5, "enabled": 6, "pending": 7}
    items.sort(key=lambda x: (0 if x["mine"] else 1, order.get(x["status"], 9), x["title"]))

    mine = [x for x in items if x["mine"]]
    running = [x for x in items if x["status"] == "running"]
    # Việc đã giao nhưng đứng im vì điều phối chưa bật. Đây là dòng người dùng cần thấy nhất:
    # "đã giao" và "đang chạy" là hai chuyện khác nhau.
    stalled = [x for x in items
               if x["kind"] == "task" and x["status"] in ("triage", "todo", "ready")]
    return {
        "count": len(items),
        "mine_count": len(mine),
        "running_count": len(running),
        "stalled_count": len(stalled) if str(orchestration or "off") != "auto" else 0,
        "orchestration": str(orchestration or "off"),
        "items": items[:MAX_ITEMS],
        "truncated": max(0, len(items) - MAX_ITEMS),
    }


def has_pending_work(view: dict) -> bool:
    """Có thứ gì đó sẽ tự nói chuyện lại với khung chat này không.

    Dùng để quyết định có dán dòng cảnh báo hứa suông hay không. Việc đang XẾP HÀNG mà điều
    phối tắt thì KHÔNG tính là có: nó sẽ nằm im, và im lặng đúng là thứ người dùng đang than.
    """
    if not isinstance(view, dict):
        return False
    if view.get("running_count"):
        return True
    if str(view.get("orchestration") or "off") == "auto" and view.get("count"):
        return True
    # Loop và nhắc hẹn tự chạy bằng scheduler riêng, không phụ thuộc điều phối Kanban.
    return any(x.get("kind") in ("loop", "reminder") for x in (view.get("items") or []))
