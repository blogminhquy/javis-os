"""Plugin bundled: tool `javis_task` - giao việc Kanban và xem tiến độ, từ MỌI engine.

Vì sao tool này tồn tại
=======================
`CLAUDE.md` và `docs/10-models-va-engine.md` đều hứa mọi bộ não được cấp cùng một bộ đồ nghề,
trong đó có "giao việc Kanban", và khác biệt duy nhất là chạy được lệnh máy hay không.

Lời hứa đó SAI cho tới bản này. Đường duy nhất để giao việc là `POST /kanban/task`, mà gọi được
nó thì phải có Bash và curl - tức là chỉ Claude Code với Codex. Năm engine API đứng ngoài. Tệ
hơn, chính `CLAUDE.md` còn dặn Javis "đừng bao giờ nói mình không làm task được, sai sự thật",
nên một engine API sẽ TỰ TIN nhận lời rồi im lặng không làm gì - kiểu hỏng tệ nhất, vì người
dùng đợi một việc không bao giờ chạy.

Hai cách sửa: hạ tài liệu xuống cho khớp mã, hoặc nâng mã lên cho khớp tài liệu. Chủ repo chọn
cách hai (2026-08-04), vì giao việc là thứ dùng thật và để nó chỉ chạy trên hai engine thì lời
hứa "đổi não thoải mái không mất chức năng" thủng đúng chỗ đáng tiếc nhất.

Gọi THẲNG, không đi vòng qua HTTP
=================================
`javis-schedule` POST tới `/reminders` được vì route đó CỐ Ý miễn đăng nhập cho localhost
(`main._AUTH_LOCAL_EXACT`). `/kanban/task` thì không, và cách duy nhất để nó gọi được qua HTTP
là thêm vào danh sách miễn auth đó - nghĩa là bất kỳ tiến trình nào trên cùng máy chủ cũng giao
được việc cho Javis mà không cần credential. Không đáng, khi plugin vốn đã chạy IN-PROCESS:
`tasks.current()` cho ngay hàng đợi thật, không hở thêm cửa nào.

An toàn (BẮT BUỘC, không có tham số nào mở được)
===============================================
- `mode="full"` bị TỪ CHỐI thẳng. Luật `CLAUDE.md`: "KHÔNG bao giờ tự đặt mode: full". Việc mức
  full tự thao tác THẬT ra ngoài - tạo đơn, tiêu tiền, chạy quảng cáo, gửi tin - và không hoàn
  tác được. Muốn vậy thì người dùng tự đặt ở trang Việc, nơi họ thấy rõ mình đang cho phép gì.
- Mặc định `suggest` (chỉ đọc + đề xuất), giống hệt luật đang áp cho loop tạo từ chat.
- `vault_root` rỗng -> báo lỗi rõ, TUYỆT ĐỐI không âm thầm rơi về Brain Default. Giao việc nhầm
  brain là việc chạy trên dữ liệu của người khác.
- `chat_id` rỗng thì CẢNH BÁO trong kết quả trả về chứ không nuốt: kết quả việc sẽ đi về ID
  Telegram đầu tiên trong whitelist, mà máy chưa đấu Telegram thì MẤT HÚT. Model phải lấy mã
  phiên từ khối "KÊNH HỘI THOẠI HIỆN TẠI" và truyền vào.

Phạm vi v1: `add` và `list`. Chuyển cột, huỷ, duyệt việc chờ phê duyệt vẫn làm ở trang Việc -
đó là những thao tác cần nhìn thấy bảng, và mô tả tool nói thẳng như vậy thay vì để model đoán.
"""
from __future__ import annotations

import tasks as tasks_mod

# Trần ký tự cho phần liệt kê việc. Kết quả tool đi thẳng vào ngữ cảnh của lượt chat, và engine
# API còn bị cắt ở 8000 ký tự (engine._clip_tool_result) - liệt kê 200 việc là đẩy văng phần
# quan trọng của câu hỏi ra ngoài.
_LIST_MAX = 40

# Cột đáng báo cáo, theo thứ tự người dùng quan tâm: đang chạy trước, xong rồi để cuối.
_COT = [
    ("running", "đang chạy"),
    ("review", "chờ duyệt"),
    ("blocked", "kẹt"),
    ("ready", "sẵn sàng"),
    ("todo", "chờ tới lượt"),
    ("triage", "mới nhận"),
    ("done", "xong"),
]

_MODE_CHO_PHEP = ("suggest", "auto")

# Chỉ mức điều phối "auto" mới có dispatcher lấy việc ra chạy (`tasks.TaskRunner._dispatch`).
# "off" (mặc định của MỌI brain mới) và "manual" đều để việc nằm im vô thời hạn.
_CANH_BAO_DIEU_PHOI = (
    "LƯU Ý QUAN TRỌNG: điều phối việc nền của brain này đang ở mức \"{muc}\" nên việc chỉ nằm "
    "xếp hàng, KHÔNG tự chạy và sẽ không có kết quả nào tự về. Phải nói thẳng điều này với "
    "người dùng và bảo họ bật \"AI tự vận hành\" ở trang Việc, đừng hứa là việc đang chạy."
)


def _dieu_phoi_chay(muc) -> bool:
    return str(muc or "").strip().lower() == "auto"


def _feature():
    f = tasks_mod.current()
    if f is None:
        return None, ("ERROR: hàng đợi việc chưa sẵn sàng (máy chủ đang khởi động?). "
                      "Thử lại sau vài giây, hoặc giao việc ở trang Việc trên dashboard.")
    return f, ""


def _them(args, ctx) -> str:
    if not ctx.vault_root:
        return ("ERROR: chưa biết đang làm việc trên brain nào nên không giao việc được. "
                "Giao ở trang Việc trên dashboard, ở đó brain đã xác định rõ.")
    tieu_de = str((args or {}).get("title") or "").strip()
    if not tieu_de:
        return "ERROR: thiếu title - việc phải có tên thì người dùng mới theo dõi được."

    mode = str((args or {}).get("mode") or "suggest").strip().lower()
    if mode == "full":
        return ("ERROR: tool này KHÔNG tạo được việc mức full. Mức full cho việc tự thao tác "
                "thật ra ngoài (tạo đơn, tiêu tiền, chạy quảng cáo, gửi tin) và không hoàn tác "
                "được, nên phải do chính người dùng đặt ở trang Việc. Hãy tạo mức suggest hoặc "
                "auto, rồi nói người dùng tự nâng nếu họ muốn.")
    if mode not in _MODE_CHO_PHEP:
        mode = "suggest"

    f, loi = _feature()
    if loi:
        return loi

    chat_id = str((args or {}).get("chat_id") or "").strip()
    deps = [d.strip() for d in str((args or {}).get("deps") or "").split(",") if d.strip()]
    try:
        tid = f.enqueue(
            ctx.vault_root,
            tieu_de,
            str((args or {}).get("intent") or "").strip() or tieu_de,
            "auto",
            2,
            deps,
            False,
            "chat",
            chat_id,
            "auto",
            mode,
            "",
        )
    except Exception as e:
        return f"ERROR: không giao được việc ({type(e).__name__}: {e})."

    ten_mode = {"suggest": "chỉ đọc và đề xuất", "auto": "được ghi file nháp trong brain"}[mode]
    ra = [f"Đã giao việc: {tieu_de}", f"Mã việc: {tid}", f"Mức quyền: {mode} ({ten_mode})"]
    if deps:
        ra.append("Chờ xong: " + ", ".join(deps))
    if not chat_id:
        # Không nuốt: đây là lý do số một khiến người dùng "giao việc rồi không thấy gì".
        ra.append("CẢNH BÁO: chưa gắn người nhận (chat_id), nên kết quả sẽ về ID Telegram đầu "
                  "tiên trong whitelist - máy chưa đấu Telegram thì mất hút. Lần sau hãy truyền "
                  "chat_id lấy từ khối KÊNH HỘI THOẠI HIỆN TẠI.")

    # Lý do số hai, và là lý do LẶNG LẼ nhất: điều phối mặc định TẮT ở mọi brain mới, nên
    # "đã giao việc" và "việc đang chạy" là hai chuyện hoàn toàn khác nhau. Trước bản này tool
    # kết thúc bằng câu "Việc chạy nền. Kết quả tự về" trong MỌI trường hợp - một lời hứa sai
    # mà model không có cách nào biết là sai, rồi nó chuyển tiếp nguyên văn cho người dùng.
    muc = "off"
    try:
        muc = f.board_view(ctx.vault_root).get("orchestration") or "off"
    except Exception:
        pass
    if _dieu_phoi_chay(muc):
        ra.append("Việc chạy nền. Kết quả tự về, tiến độ xem ở trang Việc.")
    else:
        ra.append(_CANH_BAO_DIEU_PHOI.format(muc=muc))
    return "\n".join(ra)


def _liet_ke(args, ctx) -> str:
    if not ctx.vault_root:
        return "ERROR: chưa biết đang làm việc trên brain nào nên không xem được danh sách việc."
    f, loi = _feature()
    if loi:
        return loi
    try:
        view = f.board_view(ctx.vault_root)
    except Exception as e:
        return f"ERROR: không đọc được bảng việc ({type(e).__name__}: {e})."

    cols = view.get("columns") or {}
    dong, con = [], 0
    for khoa, nhan in _COT:
        ds = cols.get(khoa) or []
        if not ds:
            continue
        for t in ds:
            if len(dong) >= _LIST_MAX:
                con += 1
                continue
            dong.append(f"[{nhan}] {t.get('id', '')} · {t.get('title', '')}")
    if not dong:
        return "Chưa có việc nào trong hàng đợi."
    if con:
        dong.append(f"…(+{con} việc nữa, xem đủ ở trang Việc)")

    # Điều phối TẮT thì việc nằm im mãi mãi mà không có một dòng lỗi nào. Nói ngay ở đây, vì đây
    # là chỗ model đang nhìn khi người dùng hỏi "việc chạy tới đâu rồi".
    #
    # `board_mode` trả CHUỖI "off"/"manual"/"auto", không phải bool - nên `not view.get(...)`
    # là sai: "off" là chuỗi rỗng-khác-rỗng nên luôn truthy, và cảnh báo này chưa từng in ra
    # một lần nào kể từ khi được viết. Đúng cổng phải là so với "auto": chỉ mức đó mới có
    # dispatcher lấy việc ra chạy (xem `tasks.TaskRunner._dispatch`).
    if not _dieu_phoi_chay(view.get("orchestration")):
        dong.append(_CANH_BAO_DIEU_PHOI.format(muc=str(view.get("orchestration") or "off")))
    return "\n".join(dong)


def register(ctx):
    ctx.register_tool(
        "javis_task",
        "Giao việc nền vào hàng đợi Kanban, hoặc xem việc đang chạy tới đâu. "
        "CHỈ op=add khi NGƯỜI DÙNG bảo làm một việc cụ thể mà lượt này không làm xong được. "
        "KHÔNG giao việc cho kế hoạch hay 'bước tiếp theo' do chính bạn vừa nghĩ ra và user chưa "
        "gật (vd 'áp dụng kế hoạch vừa trình bày', 'cập nhật timeline', 'theo dõi rồi nhắc lại'): "
        "mỗi việc đều bắn thông báo về chuông và về khung chat khi nó xong hoặc kẹt. "
        "op=add: cần title; nên kèm chat_id (lấy từ khối KÊNH HỘI THOẠI HIỆN TẠI) để kết quả về "
        "đúng người, và intent nếu cần mô tả kỹ hơn tiêu đề. mode=suggest (mặc định, chỉ đọc và "
        "đề xuất) hoặc auto (được ghi file nháp trong brain); mode full BỊ TỪ CHỐI, người dùng "
        "tự nâng ở trang Việc. deps='id1,id2' để việc này chờ việc khác xong. "
        "op=list: liệt kê việc theo cột. "
        "Chuyển cột, huỷ việc và duyệt việc chờ phê duyệt thì làm ở trang Việc, tool này không có.",
        _chay,
        schema={
            "type": "object",
            "properties": {
                "op": {"type": "string", "enum": ["add", "list"]},
                "title": {"type": "string", "description": "Tên việc, ngắn gọn (op=add)"},
                "intent": {"type": "string", "description": "Mô tả đầy đủ hơn nếu tiêu đề chưa đủ"},
                "mode": {"type": "string", "enum": ["suggest", "auto"]},
                "chat_id": {"type": "string", "description": "Người nhận kết quả, vd web:<mã phiên>"},
                "deps": {"type": "string", "description": "Mã các việc phải xong trước, cách nhau dấu phẩy"},
            },
            "required": ["op"],
        },
        min_mode="safe",
        emoji="🗂",
    )


async def _chay(args, ctx) -> str:
    op = str((args or {}).get("op") or "").strip().lower()
    if op == "add":
        return _them(args, ctx)
    if op == "list":
        return _liet_ke(args, ctx)
    return "ERROR: op phải là 'add' (giao việc) hoặc 'list' (xem việc đang có)."
