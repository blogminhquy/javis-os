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

import lang as lang_mod
import lang_registry
import lexicon   # mẫu lời hứa theo ngôn ngữ
import re
import time
import unicodedata

# Việc Kanban còn "sống" - tức là còn có ngày nó chạy rồi báo về. Khớp với
# task_store.ACTIVE_STATUS, chép lại ở đây để module này không phải nạp cả tầng task.
ACTIVE_TASK_STATUS = ("triage", "todo", "ready", "running", "review", "blocked")

# Việc đã nhận nhưng chưa ai nhấc lên chạy.
QUEUED_TASK_STATUS = ("triage", "todo", "ready")

# Trần số mục trả về cho dải trạng thái. Dải chat là chỗ liếc mắt, không phải trang Việc.
MAX_ITEMS = 12

# Việc xếp hàng mà điều phối tắt chỉ đáng báo khi nó VỪA được giao. Một backlog nằm từ tuần
# trước không phải tin tức: sơn vàng khung chat mãi mãi thì người dùng học cách nhìn xuyên qua
# nó, và lúc có việc hỏng thật thì dải cũng không còn ai đọc.
STALLED_FRESH_SEC = 24 * 3600


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
# Mẫu lời hứa ĐÃ DỜI sang server/lexicon/<mã>.py (tập PROMISE), một bộ mỗi ngôn ngữ.
# Cùng lý do với các cổng khác: một luật an toàn có hai bản thì bản bị quên là bản
# im lặng cho lọt.


def _mau_loi_hua(lang: str = "", _text_goc: str = ""):
    """Mẫu lời hứa cho ngôn ngữ của CÂU TRẢ LỜI.

    Không có bộ từ vựng thì trả HỢP của mọi bộ đang có, chứ không trả rỗng. Đây là cổng BẮT
    LỖI: bắt nhầm thì Javis tự dán thừa một dòng đính chính (phiền), còn bỏ sót thì luật
    "KHÔNG hứa em sẽ báo lại" trong CLAUDE.md mất hiệu lực mà không ai biết.
    """
    lex = lexicon.get(lang_registry.chuan_hoa(lang) or lang_mod.detect(_text_goc or "")[0])
    if lex is not None:
        return lex.PROMISE
    ra = []
    for ma in lexicon.ma_list():
        mod = lexicon.get(ma)
        if mod is not None:
            ra.extend(mod.PROMISE)
    return tuple(ra)


def detect_promise(text: str, lang: str = "") -> str:
    """Tên mẫu lời hứa "sẽ báo lại sau" trong câu trả lời, hoặc "" nếu không có.

    Trả về TÊN mẫu (không phải bool) để log/trace nói được là bắt bằng mẫu nào - lúc cần nới
    hay siết mẫu thì có số liệu thật thay vì đoán.
    """
    raw = str(text or "")
    if not raw.strip():
        return ""
    raw = _INLINE_CODE.sub(" ", _CODE_FENCE.sub(" ", raw))
    norm = _norm(raw)
    for name, pattern in _mau_loi_hua(lang, text):
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
                orchestration: str = "off", running_loop: str = "",
                now: float = 0.0) -> dict:
    """Gom việc nền còn sống thành một khung nhìn cho dải trạng thái của khung chat.

    Nhận dữ liệu THÔ đã đọc sẵn (không tự đi đọc kho) để test được mà không cần dựng cả server.

    `mine` = việc gắn đúng khung chat này (`chat_id` / `owner_chat` khớp). Việc của người khác
    vẫn hiện, nhưng đếm riêng: người dùng cần phân biệt "máy đang bận" với "việc CỦA TÔI đang
    chạy" - gộp một cục là quay lại đúng chỗ mù mà bản này đang đi sửa.

    `level` quyết định dải có ĐƯỢC HIỆN hay không, và đây là chỗ bản đầu làm sai. Chủ repo báo
    ngay hôm sau (2026-08-07, kèm ảnh): mở chat ra là một khối "9 việc nền đang chờ tới giờ"
    liệt kê đủ 9 cái nhắc hẹn. Chín cái đó không chạy, không hỏng, không cần ai làm gì - chúng
    chỉ đang đợi tới giờ, và trang Việc định kỳ đã liệt kê sẵn. Dải sinh ra để trả lời "ngay
    lúc này có cái gì đang chạy cho tôi không"; nhắc hẹn chờ tới giờ trả lời "không", mà câu
    trả lời "không" thì đúng nghĩa là ẩn đi. Chỉ hai mức đáng cắt ngang khung chat:

      - "run"   có việc đang chạy THẬT
      - "stall" vừa giao mà điều phối tắt nên nó KHÔNG chạy (người dùng phải bật mới xong)
      - "idle"  còn lại - dải ẩn hẳn
    """
    cid = str(chat_id or "").strip()
    moc = float(now) or time.time()
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

    # Việc đã giao nhưng đứng im vì điều phối chưa bật. Đây là dòng người dùng cần thấy nhất:
    # "đã giao" và "đang chạy" là hai chuyện khác nhau. Đánh dấu ngay trên từng mục để dải chỉ
    # vẽ đúng mấy cái này, khỏi phải tự đoán lại luật cũ ở phía trình duyệt.
    tat_dieu_phoi = str(orchestration or "off") != "auto"
    for x in items:
        moi = (not x["at"]) or (moc - x["at"]) <= STALLED_FRESH_SEC
        x["stalled"] = bool(tat_dieu_phoi and x["kind"] == "task"
                            and x["status"] in QUEUED_TASK_STATUS and moi)

    mine = [x for x in items if x["mine"]]
    running = [x for x in items if x["status"] == "running"]
    stalled = [x for x in items if x["stalled"]]
    level = "run" if running else ("stall" if stalled else "idle")
    return {
        "count": len(items),
        "mine_count": len(mine),
        "running_count": len(running),
        "stalled_count": len(stalled),
        "level": level,
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
