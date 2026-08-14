"""Bộ từ vựng TIẾNG VIỆT - chép NGUYÊN VĂN từ các mẫu đang chạy.

**Không sửa một ký tự nào so với bản gốc.** Đây là điều kiện để tin rằng việc rút regex ra
khỏi các cổng không đổi hành vi của người dùng hiện tại: `tests/python/test_lang_gates.py`
chạy lại đúng bộ ca tiếng Việt và đòi kết quả trùng từng bit.

Nguồn gốc từng tập (số dòng theo bản trước khi rút):
  DENY, ALLOW                 <- fast_path_runtime.FastIntentClassifier
  WRITE_INTENT, STATE_REF     <- readonly_path_runtime + readonly_orchestrator (bản
                                 orchestrator rộng hơn: có thêm `write|post`; lấy bản RỘNG
                                 vì hụt một từ ở cổng chặn nguy hiểm hơn là thừa)
  FALSE_ACTION, ACTION_VERBS,
  QUANTITATIVE,
  CAPABILITY_DENIAL           <- context_compiler.DeterministicQualityGate
  PROMISE                     <- background_status
  REMEMBER, DENSE             <- learn.py
  STUCK                       <- chatbot_runtime._DAU_BI

Lưu ý một chỗ dễ hiểu nhầm: các mẫu gốc vốn đã TRỘN sẵn từ tiếng Anh (`gui|send`,
`xoa|delete`). Chúng được giữ nguyên ở đây thay vì tách sang `en.py`, vì bỏ chúng đi là làm
YẾU cổng cho người dùng tiếng Việt - một thay đổi hành vi mà không ai yêu cầu. `en.py` khai
bộ tiếng Anh ĐẦY ĐỦ của riêng nó.

Mọi mẫu chạy trên văn bản ĐÃ BỎ DẤU (xem `lang._bo_dau`), trừ FALSE_ACTION và QUANTITATIVE
vốn cố ý chạy trên văn bản thô để giữ được cả dạng có dấu.
"""
import re

DENY = (
    ("attachment", re.compile(
        r"\b(tep|file|attachment|attached|dinh kem|hinh anh|anh nay|tai lieu|"
        r"uploaded|the document i|i uploaded)\b"
    )),
    ("url_reference", re.compile(r"(https?://|www\.)")),
    ("live_data", re.compile(
        r"\b(hom nay|hom qua|bay gio|hien tai|moi nhat|thoi tiet|tin tuc|ty gia|gia vang|"
        r"gia co phieu|lich hom|thang nay|tuan nay|quy nay|thang truoc|tuan truoc|"
        r"doanh thu|don hang|email moi|email cua|hop thu|check email|"
        r"current|latest|today|yesterday|now|this week|this month|last week|last month|"
        r"weather|news|stock price|exchange rate|revenue|my email|my inbox)\b"
    )),
    ("external_source", re.compile(
        r"\b(web|internet|google|drive|gmail|calendar|github|repository|repo|database|"
        r"api|mcp|tool|vault|obsidian|slack|notion|airtable|facebook|tiktok|zalo|telegram)\b"
    )),
    ("side_effect", re.compile(
        r"\b(gui email|gui tin|xoa|delete|remove|tao lich|dat lich|nhac toi|upload|"
        r"publish|dang bai|dang len|cap nhat file|sua file|luu vao|write to|send email|"
        r"create event|post to|schedule)\b"
    )),
    ("conversation_state", re.compile(
        r"\b(truoc day|lan truoc|vua roi|luc nay|anh da|chung ta da|nho khong|memory|"
        r"cuoc tro chuyen|tin nhan truoc|doan chat|(nhung gi|cai) (anh|em|ban) (noi|viet)|"
        r"(em|anh|ban) vua (noi|viet)|viet tiep|previously|earlier|last time|we discussed|"
        r"do you remember|my last message|this conversation|cai nay|do nay|no)\b"
    )),
    ("agentic", re.compile(
        r"\b(hay lam giup|thuc hien|kiem tra giup|tim giup|doc giup|mo giup|"
        r"execute|run|check my|look up|search for|fetch|open my)\b"
    )),
)

ALLOW = (
    ("conversation", re.compile(r"^(xin chao|chao|hello|hi|cam on|thank you)\b")),
    ("explanation", re.compile(
        r"\b(la gi|giai thich|tai sao|vi sao|khai niem|phan biet|what is|explain|why|difference)\b"
    )),
    ("writing", re.compile(
        r"\b(viet|viet lai|dat ten|tieu de|y tuong|brainstorm|rewrite|draft|headline|ideas|outline)\b"
    )),
    ("transform", re.compile(r"\b(dich|tom tat|rut gon|translate|summarize|shorten)\b")),
    ("reasoning", re.compile(
        r"\b(tinh|giai bai|phan tich logic|compare|calculate|solve|pros and cons|uu nhuoc diem)\b"
    )),
)

STATE_REF = re.compile(
    r"\b(truoc day|lan truoc|vua roi|cai do|cai nay|nhu cu|tiep tuc|nho khong|"
    r"previously|earlier|last time|remember|that one|same as before)\b"
)

WRITE_INTENT = re.compile(
    r"\b(gui|send|xoa|delete|remove|huy|cancel|tao|create|cap nhat|update|sua|edit|"
    r"dang bai|publish|upload|dat lich|book|write|post)\b"
)

ACTION_VERBS = (
    r"(?:gửi|gui|xoá|xoa|xóa|tạo|tao|cập nhật|cap nhat|đặt lịch|dat lich|đăng|dang|"
    r"sent|send|deleted|delete|created|create|updated|update|published|publish|booked|book)"
)

FALSE_ACTION = re.compile(
    r"(?i)(?:"
    r"(?:^|[.!?\n]\s*)(?:đã|da|vừa|vua)\s+(?:được\s+|duoc\s+)?" + ACTION_VERBS + r"\b"
    r"|\b(?:em|tôi|toi|mình|minh|javis)\s+(?:đã|da|vừa|vua)\s+" + ACTION_VERBS + r"\b"
    r"|\b" + ACTION_VERBS + r"\s+thành công\b"
    r"|\b" + ACTION_VERBS + r"\s+thanh cong\b"
    r"|\bsuccessfully\s+" + ACTION_VERBS + r"\b"
    r"|\b(?:was|has been|have been)\s+(?:sent|deleted|created|updated|published|booked)\b"
    r"|\bi\s+(?:have\s+|just\s+)?(?:sent|deleted|created|updated|published|booked)\b"
    r")"
)

QUANTITATIVE = re.compile(
    r"(?i)(?:\d[\d.,]*\s*(?:%|phần trăm|đ|vnđ|vnd|usd|\$|triệu|tỷ|ty|nghìn|nghin|k\b|đơn|don|"
    r"khách|khach|lượt|luot|giờ|gio|phút|phut)"
    r"|(?:doanh thu|chi phí|chi phi|lợi nhuận|loi nhuan|tổng|tong)\s*(?:là|la|:)?\s*\d)"
)

CAPABILITY_DENIAL = (
    "không có tool", "không có công cụ", "không thể truy cập công cụ",
    "i do not have access to tools", "no tools available",
)

PROMISE = (
    ("co_ket_qua", re.compile(
        r"\b(co|khi co|khi nao co|neu co)\s+ket qua\b[^.!?]{0,40}?\b(em|minh|toi)\b[^.!?]{0,25}?"
        r"\b(bao|gui|cap nhat|tra loi|noi)\b"
    )),
    ("se_bao_lai", re.compile(
        r"\b(em|minh|toi)\s+(se\s+|xin\s+)?"
        r"(bao lai|bao ngay|bao anh|bao chi|bao ban|bao sau|bao lien|"
        r"cap nhat lai|cap nhat cho|thong bao lai|thong bao cho|"
        r"gui lai ket qua|quay lai bao|quay lai voi)\b"
    )),
    ("xong_em_bao", re.compile(
        r"\bxong\s+(roi\s+|thi\s+)?(em|minh|toi)\s+(se\s+)?(bao|gui|noi|cap nhat)\b"
    )),
    ("cho_em", re.compile(
        r"\b(cho|doi)\s+(em|minh)\s+(mot\s+)?(chut|ti|lat|xiu|it phut|vai phut)\b"
    )),
    ("doi_roi_tong_hop", re.compile(
        r"\b(em|minh|toi)\s+se\s+(doi|cho|theo doi)\b[^.!?]{0,60}?"
        r"\b(roi|xong|sau do)\b[^.!?]{0,30}?\b(tong hop|bao|gui|cap nhat)\b"
    )),
    ("dang_lam_se_bao", re.compile(
        r"\b(em|minh|toi)\s+(dang|se)\s+"
        r"(do|kiem tra|ra soat|ra lai|tra|tra cuu|tim|chay|lam|phan tich|xu ly|xem lai|doc lai)\b"
        r"[^.!?]{0,90}?\b(bao|gui|cap nhat|thong bao)\b"
    )),
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

REMEMBER = re.compile(
    r"(ghi nhớ|nhớ giúp|lưu lại|nhớ là|remember this|ghi lại vào bộ nhớ)", re.I
)

DENSE = re.compile(
    r"(là gì|gồm .{0,8}bước|công thức|mô hình|nguyên (lý|tắc)|framework|quy trình|"
    r"khái niệm|định nghĩa|cách (làm|dựng|triển khai))", re.I
)

STUCK = ("chưa có thông tin", "không có thông tin", "chưa nắm được", "chuyển cho nhân viên",
         "chuyển nhân viên", "chuyển cho người phụ trách", "chuyển cho người thật",
         "em chưa rõ", "chưa trả lời được")
