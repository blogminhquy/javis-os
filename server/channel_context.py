"""
Ngữ cảnh kênh hội thoại - port ý tưởng gateway của hermes-agent (NousResearch).

Vấn đề: Javis nhận tin từ nhiều "cửa" (Telegram, dashboard web) nhưng model
không tự biết mình đang trả lời qua cửa nào, và file tạo ra không quay về
đúng kênh. Hermes giải bằng cách gateway CHÈN metadata kênh vào context mỗi
phiên (gateway/session.py: Source + User + Connected Platforms + Delivery
options). Module này làm đúng việc đó cho Javis:

1. build_channel_block()  - block metadata kênh chèn vào system prompt.
2. collect_turn_files()   - gom file sinh ra trong 1 lượt trả lời để gateway
                            tự gửi trả qua kênh chat (Telegram).
"""
import json
import os
import re
from pathlib import Path

# Trần an toàn khi auto-đính kèm file trả về kênh chat
MAX_FILES_PER_TURN = 10
MAX_FILE_MB = 50          # trần sendDocument của Telegram bot

# Không bao giờ auto-gửi file nằm trong các folder nội bộ/rác này
_EXCLUDE_PARTS = {".git", "__pycache__", "node_modules", ".obsidian", ".trash", ".tmp"}


def build_channel_block(source: str, meta: dict = None, telegram_running: bool = False,
                        port: int = 7777, brain_root: str = None) -> str:
    """Block 'KÊNH HỘI THOẠI HIỆN TẠI' để nối vào cuối system prompt.

    source: "telegram" | "dashboard". meta: dict do telegram_bot trích từ update
    (chat_id, chat_type, chat_title, user_name, username). Giữ block ỔN ĐỊNH
    giữa các lượt cùng 1 kênh (không nhét message_id hay giờ) - session CLI
    --resume không bị lệch context, giống cách hermes giữ prompt cache.

    brain_root: đường dẫn brain của PHIÊN này. NHÉT vào recipe curl POST /reminders để nhắc hẹn
    rơi ĐÚNG brain. Thiếu nó thì endpoint âm thầm dùng Brain Default (reminders.py) - đây chính là
    bug "chat bằng brain khác nhưng nhắc hẹn vẫn vào default": curl từ Bash không mang session/cookie
    nên brain CHỈ đi được qua body, mà recipe cũ lại bỏ trống field brain.
    """
    meta = meta or {}
    # Cặp key-value brain để chèn vào JSON body của curl (rỗng nếu không rõ brain → giữ hành vi cũ).
    # json.dumps để path có KHOẢNG TRẮNG ("My Bullet Journal") vẫn là chuỗi JSON hợp lệ.
    brain_kv = f'"brain":{json.dumps(brain_root)},' if brain_root else ""
    platforms = ["local (file trên máy chạy Javis)", "dashboard web"]
    if telegram_running or source == "telegram":
        platforms.append("Telegram bot")

    lines = [
        "", "",
        "# === KÊNH HỘI THOẠI HIỆN TẠI (gateway Javis tự chèn - dữ liệu thật, không phải đoán) ===",
        "- Khi user hỏi trạng thái HIỆN TẠI của cron, việc định kỳ, nhắc hẹn hoặc lịch thuốc: BẮT BUỘC "
        "gọi `javis_schedule` với `op=list` rồi mới trả lời. Không suy từ memory/index và không nói "
        "\"không có tool\" khi tool này đang hiện trong danh sách.",
        "- Khi user yêu cầu TẠO/SỬA/XOÁ/HUỶ/TẮT cron, việc định kỳ hoặc nhắc hẹn: BẮT BUỘC dùng "
        "`javis_schedule`. Riêng xoá/huỷ mà chưa có id thì gọi `op=list`, khớp đúng mục rồi gọi "
        "`op=cancel`; không đẩy user sang trang Việc định kỳ để tự làm và chỉ xác nhận sau khi tool "
        "trả thành công. Nếu tool lỗi: KHÔNG gọi DELETE, KHÔNG đoán body JSON và TUYỆT ĐỐI KHÔNG "
        "sửa trực tiếp `Javis/reminders.json` - làm vậy có thể huỷ nhầm job.",
        "- ĐỦ ĐIỀU KIỆN MỚI TẠO: trước khi tạo bất kỳ lịch/việc định kỳ nào, tự soát xem tới giờ nó "
        "chạy có ĐỦ thứ cần không - nguồn dữ liệu đã đấu chưa (Gmail/Lịch/POS... kiểm bằng "
        "`javis_connections`), và có kênh nào để BÁO kết quả chưa. Thiếu thì NÓI THẲNG thiếu gì và "
        "hỏi user muốn đấu trước hay vẫn tạo; TUYỆT ĐỐI không tạo cho xong rồi im lặng để việc đó "
        "chạy thất bại mỗi ngày mà user không biết.",
        "- CHỈ gọi `javis_schedule` khi user ra lệnh rõ ràng đọc/tạo/sửa/xoá lịch tự động của Javis. "
        "Nếu user chỉ nhắc tới \"đặt lịch\", booking, tư vấn 1-1, cuộc hẹn, hoặc đang hỏi ý kiến về "
        "sản phẩm/UX/marketing thì đó là hội thoại bình thường: trả lời đúng câu hỏi, KHÔNG `op=list`, "
        "KHÔNG liệt kê cron/reminder và KHÔNG tự tạo lịch.",
        "- Với mọi dữ liệu đang chạy hoặc dữ liệu tài khoản ngoài (MCP/Google/POS...): phải gọi tool "
        "phù hợp, hoặc `javis_connections` / `javis_search_tools` để tìm tool. Nếu tool thật sự lỗi, "
        "nêu đúng lỗi vừa nhận; không bịa trạng thái từ ngữ cảnh cũ.",
        "- KHÔNG HỨA THỨ MÌNH KHÔNG LÀM ĐƯỢC. Lượt trả lời của bạn KẾT THÚC ngay khi bạn nói "
        "xong: không có ai đánh thức bạn dậy để làm nốt, và bạn KHÔNG chạy tiếp ở nền. Nên "
        "TUYỆT ĐỐI không nói những câu kiểu \"em đang dò/đang kiểm tra, có kết quả em báo ngay\", "
        "\"xong em báo lại\", \"anh chờ em chút\", \"em sẽ đợi rồi tổng hợp\". Chỉ có hai lối "
        "đúng: (1) LÀM LUÔN trong lượt này rồi trả kết quả thật, hoặc (2) giao thành việc nền "
        "(`javis_task` op=add) / nhắc hẹn (`javis_schedule`) rồi nói rõ đã giao gì và kết quả sẽ "
        "về đâu. Không làm được cả hai thì nói thẳng là chưa làm, đừng hẹn.",
        "- Giao việc nền xong phải ĐỌC kết quả tool trả về rồi thuật lại đúng như vậy. Nếu tool "
        "báo điều phối đang TẮT thì việc chỉ nằm xếp hàng chứ chưa chạy - phải nói thẳng câu đó "
        "và bảo user bật \"AI tự vận hành\" ở trang Việc, KHÔNG được rút gọn thành \"việc đang "
        "chạy, kết quả sẽ tự về\".",
        "- THÊM MCP / đấu nguồn mới: BẮT BUỘC dùng tool `javis_add_mcp` (op=find để tra Kho kết nối "
        "trước, op=add để đấu). Chỉ đường này nguồn mới mới nằm trong kho của Javis và HIỆN ở khu "
        "'Đã kết nối' trang Kết nối cho người dùng thấy, đồng thời mọi bộ não dùng chung được. "
        "TUYỆT ĐỐI không thêm bằng `claude mcp add` / `codex mcp add` và không sửa tay file cấu hình "
        "MCP: kiểu đó chỉ một CLI thấy, người dùng nhìn trang Kết nối tưởng chưa thêm gì. Không thấy "
        "`javis_add_mcp` trong danh sách tool thì nó đang nằm sau `javis_search_tools` - tìm rồi gọi "
        "qua `javis_run_tool`, chứ đừng kết luận là không làm được. Thêm xong phải NÓI RÕ nó đang nằm "
        "ở trang Kết nối, đang bật hay tắt, và đang ở mức quyền nào.",
    ]
    if source == "telegram":
        who = (meta.get("user_name") or "").strip() or "user"
        if meta.get("username"):
            who += f" (@{meta.get('username')})"
        if meta.get("chat_type") in ("group", "supergroup"):
            conv = f"nhóm '{meta.get('chat_title') or '?'}', tin nhắn từ {who}"
        else:
            conv = f"DM với {who}"
        chat_id = meta.get("chat_id") or "?"
        lines += [
            f"- Nguồn tin nhắn này: Telegram ({conv}, chat_id {chat_id}).",
            f"- Nền tảng đang kết nối: {', '.join(platforms)}.",
            "- Đang chat qua Telegram: trả lời NGẮN gọn kiểu tin nhắn. Telegram hiển thị được "
            "đậm/nghiêng/`code`, KHÔNG hiển thị bảng markdown - đừng dùng bảng.",
            "",
            "## Gửi file cho user qua Telegram (2 cách)",
            "1. TỰ ĐỘNG (nên dùng - luôn về ĐÚNG người đang hỏi): file bạn tạo bằng tool Write trong "
            "lượt này, file có ĐƯỜNG DẪN TUYỆT ĐỐI trong câu trả lời cuối, HOẶC ảnh/tệp trong vault "
            "nhúng dạng markdown ![](attachments/...) (vd ẢNH Javis vừa tạo) - đều được Javis tự đính "
            f"kèm gửi qua Telegram ngay sau câu trả lời (tối đa {MAX_FILES_PER_TURN} file/lượt, mỗi file "
            f"dưới {MAX_FILE_MB}MB). Ảnh bạn vừa tạo: CHỈ cần nhúng ![](attachments/...) là đủ để user "
            "nhận, KHÔNG cần curl (curl dễ gửi nhầm cho chủ bot).",
            "2. GỬI NGAY / file có sẵn từ trước: dùng tool Bash gọi "
            f"`curl -s -X POST http://127.0.0.1:{port}/telegram/send-file "
            "-H \"Content-Type: application/json\" "
            "-d '{\"path\":\"<đường dẫn tuyệt đối>\",\"caption\":\"<mô tả ngắn>\","
            f"\"chat_id\":\"{chat_id}\"}}'`",
            f"- LUÔN giữ \"chat_id\":\"{chat_id}\" trong lệnh trên để file về ĐÚNG người đang hỏi "
            "(bỏ đi thì file sẽ gửi nhầm cho chủ bot).",
            "- KHÔNG nói \"em đã gửi file\" khi chưa làm một trong hai cách trên.",
            "- File user gửi lên Telegram đã được gateway tải về máy sẵn - đường dẫn nằm ngay trong tin nhắn.",
            "",
            "## Đặt nhắc hẹn (Javis TỰ thức dậy gửi sau - dùng khi user muốn được nhắc)",
            "Khi user muốn được NHẮC vào lúc nào đó (\"30 phút nữa nhắc anh...\", \"8h30 sáng mai nhắc...\", "
            "\"mỗi sáng 7h nhắc uống thuốc\", \"tối 9h báo doanh thu hôm nay\").",
            "- CÁCH NÊN DÙNG: gọi tool `javis_schedule` (op=create) - nó TỰ gắn đúng brain phiên này, "
            "khỏi lo nhắc rơi nhầm brain. Chỉ dùng curl bên dưới nếu vì lý do gì không gọi được tool.",
            "- Cách curl (nếu cần): dùng tool Bash gọi "
            f"`curl -s -X POST http://127.0.0.1:{port}/reminders "
            "-H \"Content-Type: application/json\" "
            f"-d '{{\"text\":\"<nội dung nhắc, ngắn gọn>\",{brain_kv}\"delay_min\":30,"
            f"\"chat_id\":\"{chat_id}\",\"mode\":\"notify\"}}'`",
            "- THỜI ĐIỂM (chọn 1): \"delay_min\": số phút nữa (vd 30, 120); HOẶC \"at\":\"HH:MM\" giờ trong "
            "ngày (đã qua thì tự sang mai); HOẶC \"at\":\"YYYY-MM-DD HH:MM\" cho ngày cụ thể. Server TỰ tính "
            "giờ Việt Nam - bạn KHỎI cần biết bây giờ là mấy giờ, cứ map thẳng câu user nói.",
            "- LỊCH ĐỊNH KỲ PHỨC TẠP (mỗi sáng, thứ 2 hằng tuần, mỗi 15 phút...): dùng \"cron\" thay cho "
            "delay_min/at, là biểu thức cron 5 trường \"phút giờ ngày tháng thứ\" (thứ: 0=CN..6=T7). Ví dụ "
            "mỗi ngày 7h = \"0 7 * * *\"; mỗi 15 phút = \"*/15 * * * *\"; 8h thứ 2 = \"0 8 * * 1\"; 9h ngày 1 "
            "hằng tháng = \"0 9 1 * *\". Bạn tự đổi câu user thành cron. Có cron thì tự lặp, KHỎI cần repeat_min.",
            "- LẶP đơn giản (không cần cron): thêm \"repeat_min\": số phút (vd 1440 = mỗi ngày, 60 = mỗi giờ).",
            "- \"mode\":\"notify\" (mặc định) = tới giờ nhắn lại đúng câu nhắc. \"mode\":\"task\" = tới giờ "
            "Javis TỰ LÀM việc mô tả trong text (đọc số liệu MCP, soạn nháp) rồi gửi kết quả về đây.",
            "- \"mode\":\"script\" = job giám sát KHÔNG cần AI (rẻ): chạy 1 file script CÓ SẴN trong "
            "Javis/scripts (\"script\":\"<tên file .py/.sh/.ps1>\"), đẩy stdout về đây; stdout rỗng thì im lặng, "
            "exit khác 0 thì báo lỗi. Chỉ chạy file user đã tự bỏ vào folder đó - KHÔNG bịa lệnh tuỳ ý.",
            f"- LUÔN giữ \"chat_id\":\"{chat_id}\" để nhắc về ĐÚNG người đang nói.",
            ("- LUÔN giữ NGUYÊN field \"brain\" có sẵn trong lệnh trên (nó trỏ brain đang chat) để nhắc "
             "hẹn thuộc ĐÚNG brain; bỏ đi thì nhắc rơi nhầm vào Brain Default." if brain_root else
             "- (Không xác định được brain phiên → nhắc sẽ vào Brain Default.)"),
            "- Gọi curl xong, đọc JSON trả về: ok=true kèm due_human là đã đặt - xác nhận lại NGẮN bằng lời "
            "(vd \"Ok, 8h30 sáng mai em nhắc anh nhé\"). KHÔNG nói đã đặt nếu curl chưa trả ok=true.",
            "",
            "## Fallback HUỶ nhắc hẹn khi javis_schedule thật sự lỗi",
            "- Chỉ dùng fallback này cho reminder có id dạng `r_...`; loop/file định kỳ phải dừng và báo đúng "
            "lỗi tool, không tự sửa/xoá file.",
            "- Chưa có id: đọc danh sách thật bằng "
            f"`curl -sG http://127.0.0.1:{port}/reminders "
            f"--data-urlencode \"brain={brain_root or 'brain'}\"`; chỉ chọn item `status=pending` khớp chắc chắn.",
            "- Có đúng id: huỷ bằng form-data chuẩn "
            f"`curl -s -X POST http://127.0.0.1:{port}/reminders/cancel "
            f"--data-urlencode \"id=<r_id>\" --data-urlencode \"brain={brain_root or 'brain'}\"`. "
            "Endpoint không có DELETE và không nhận JSON.",
            "- Chỉ xác nhận đã huỷ khi JSON trả `ok:true`; `ok:false`, 401 hoặc lỗi khác thì báo nguyên lỗi và dừng.",
            "",
            "## Tạo Loop / Việc (Kanban) cho user qua chat - báo kết quả về ĐÚNG người",
            "Loop chạy nền (mỗi vòng) và việc Kanban (khi chạy xong) TỰ báo kết quả về Telegram của "
            "NGƯỜI YÊU CẦU. Để về đúng người đang chat (không phải chủ bot), gắn danh tính họ khi tạo:",
            f"- Tạo LOOP: thêm dòng `owner_chat: \"{chat_id}\"` vào frontmatter file Javis/loops/<slug>.md.",
            f"- Tạo VIỆC: khi POST http://127.0.0.1:{port}/kanban/task, kèm field \"chat_id\":\"{chat_id}\".",
            "- Bỏ trống owner_chat/chat_id (vd tạo trên bản web) → báo về chủ bot (ID Telegram đầu tiên).",
            "- Muốn 1 loop ngừng báo mỗi vòng (loop quá ồn): đặt `notify: false` trong frontmatter loop đó.",
        ]
    elif source == "cli":
        # Terminal. Khác web ở chỗ KHÔNG render được gì: không ảnh, không bảng, không link bấm
        # được. Nói thẳng ra đây, nếu không Javis sẽ trả về markdown của web và người dùng nhận
        # một đống ký tự gạch dọc.
        who = (meta.get("host") or "").strip()
        lines += [
            "- Nguồn tin nhắn này: Javis CLI (user đang gõ trong terminal"
            + (f", máy {who}" if who else "") + ").",
            f"- Nền tảng đang kết nối: {', '.join(platforms)}.",
            "- Terminal KHÔNG render markdown: TUYỆT ĐỐI không dùng bảng, không nhúng ảnh "
            "`![](...)`, không dùng link markdown. Có file hay ảnh thì in ĐƯỜNG DẪN TUYỆT ĐỐI "
            "trên một dòng riêng để user copy hoặc mở bằng lệnh khác.",
            "- Trả lời gọn, xuống dòng thường xuyên. Khối mã vẫn dùng ba dấu backtick "
            "(CLI tô màu được).",
            "- Người hỏi đang ở terminal nên có sẵn shell: đường dẫn và lệnh gợi ý là thứ họ "
            "dùng được ngay, hữu ích hơn mô tả dài dòng.",
        ]
    else:
        web_sid = str(meta.get("session_id") or "").strip()
        lines += [
            "- Nguồn tin nhắn này: Dashboard web Javis (user mở bằng trình duyệt, file hiện dạng đường dẫn).",
            f"- Nền tảng đang kết nối: {', '.join(platforms)}.",
        ]
        if web_sid:
            lines += [
                "",
                "## Giao việc chạy nền rồi BÁO LẠI ĐÚNG KHUNG CHAT NÀY",
                f"- Mã phiên chat hiện tại: `{web_sid}`.",
                "- Khi POST http://127.0.0.1:%d/kanban/task, LUÔN kèm field "
                "`\"chat_id\":\"web:%s\"`. Đó là cách kết quả rơi thẳng về khung chat này lúc việc "
                "xong. Bỏ trống thì kết quả chỉ đi Telegram - user ngồi web sẽ không thấy gì cả." % (port, web_sid),
                "- Loop tạo từ đây: đặt `owner_chat: \"web:%s\"` trong frontmatter, cùng lý do." % web_sid,
                "- TUYỆT ĐỐI KHÔNG hứa kiểu \"em sẽ đợi các agent chạy xong rồi tổng hợp cho anh\": "
                "lượt trả lời của bạn KẾT THÚC ngay sau khi bạn nói, không có chỗ nào để bạn ngồi đợi "
                "và cũng không ai đánh thức bạn dậy để tổng hợp. Việc chạy nền tự báo kết quả THÔ về "
                "khung chat khi xong. Hãy nói đúng như vậy: đã giao mấy việc, mỗi việc làm gì, kết quả "
                "sẽ tự hiện ở đây, xem tiến độ ở trang Việc. Muốn có bản tổng hợp so sánh thì bảo user "
                "nhắn lại một câu sau khi kết quả về, HOẶC giao luôn một việc cuối chuyên đi tổng hợp "
                "(dùng `deps` trỏ vào các việc trước) thay vì tự hứa suông.",
                "- Javis TỰ KIỂM lời hứa: cuối mỗi lượt server dò câu trả lời xem có hẹn báo lại "
                "không, rồi đối chiếu với việc nền thật đang có. Hứa mà không có việc nào thì "
                "server tự dán một dòng đính chính ngay dưới câu của bạn cho user thấy. Nên câu "
                "hẹn suông không giúp bạn thoát, chỉ làm câu trả lời trông tệ hơn.",
            ]
        if telegram_running:
            lines += [
                "- Nếu user muốn nhận 1 file qua Telegram: dùng tool Bash gọi "
                f"`curl -s -X POST http://127.0.0.1:{port}/telegram/send-file "
                "-H \"Content-Type: application/json\" "
                "-d '{\"path\":\"<đường dẫn tuyệt đối>\",\"caption\":\"...\"}'`",
                "- Nếu user muốn được NHẮC sau (\"30 phút nữa nhắc...\", \"8h sáng mai...\"): nên gọi tool "
                "`javis_schedule` (op=create) để nhắc vào ĐÚNG brain đang chọn; hoặc dùng tool Bash gọi "
                f"`curl -s -X POST http://127.0.0.1:{port}/reminders -H \"Content-Type: application/json\" "
                f"-d '{{\"text\":\"<nội dung>\",{brain_kv}\"delay_min\":30}}'` (hoặc \"at\":\"HH:MM\" / "
                "\"at\":\"YYYY-MM-DD HH:MM\", thêm \"repeat_min\" để lặp). Giữ nguyên field \"brain\" để nhắc "
                "thuộc đúng brain. Server tính giờ VN; tới giờ Javis tự gửi nhắc qua Telegram cho chủ bot.",
            ]
    return "\n".join(lines) + "\n"


# ---- Trích đường dẫn file từ câu trả lời ----
# 3 mẫu: trong nháy/backtick (cho phép khoảng trắng - vault hay có "01 - Daily Log"),
# đường dẫn Windows trần, đường dẫn POSIX trần (không khoảng trắng).
_QUOTED_RE = re.compile(r"[`\"']((?:[A-Za-z]:[\\/]|/)[^`\"'\n]{2,300})[`\"']")
_WIN_RE = re.compile(r"(?:^|[\s(<])([A-Za-z]:[\\/][^\s`\"'()\[\]<>|*?]+)")
_POSIX_RE = re.compile(r"(?:^|[\s(<])(/[^\s`\"'()\[\]<>|*?:]+)")


def extract_paths(text: str) -> list:
    """Mọi chuỗi trông giống đường dẫn tuyệt đối trong text (chưa lọc tồn tại)."""
    out = []
    t = text or ""
    for rx in (_QUOTED_RE, _WIN_RE, _POSIX_RE):
        for m in rx.finditer(t):
            out.append(m.group(1).strip().rstrip(".,;:!?…"))
    return out


# Media/liên kết NHÚNG trong markdown: ![alt](path) hoặc [text](path).
# Chấp nhận cả đường dẫn có khoảng trắng KHÔNG bọc <> vì model thường trả
# ![](99 - Attachments/anh.png), dù CommonMark chuẩn yêu cầu <...>.
_MD_LINK_RE = re.compile(r"(!?)\[([^\]\n]*)\]\(\s*(?:<([^>\n]+)>|([^\n)]*?))\s*\)")
_MD_TITLE_RE = re.compile(r"""\s+(?:"[^"\n]*"|'[^'\n]*')\s*$""")


def _md_link_target(match) -> str:
    raw = (match.group(3) if match.group(3) is not None else match.group(4)) or ""
    raw = _MD_TITLE_RE.sub("", raw.strip())
    return raw.strip().strip("'\"")


def _vault_markdown_candidate(raw: str, vault_root: str):
    """Resolve một target Markdown về file bên trong vault; URL/anchor/path thoát vault → None."""
    if not raw or not vault_root:
        return None
    if "://" in raw or raw.startswith(("#", "mailto:", "data:", "tel:")):
        return None
    try:
        vroot = os.path.normpath(os.path.abspath(vault_root))
        if os.path.isabs(raw) or re.match(r"^[A-Za-z]:[\\/]", raw):
            cand = os.path.normpath(os.path.abspath(raw))
        else:
            cand = os.path.normpath(os.path.abspath(os.path.join(vroot, raw)))
        vroot_nc = os.path.normcase(vroot)
        cand_nc = os.path.normcase(cand)
        if cand_nc == vroot_nc or cand_nc.startswith(vroot_nc + os.sep):
            return cand
    except Exception:
        pass
    return None


def resolve_vault_relative(text: str, vault_root: str) -> list:
    """Đường dẫn nhúng Markdown → path tuyệt đối NẰM TRONG vault.

    Hỗ trợ path tương đối có khoảng trắng, dạng <path>, và path tuyệt đối trong chính vault.
    URL hoặc '../' thoát vault luôn bị bỏ.
    """
    out = []
    if not vault_root:
        return out
    for m in _MD_LINK_RE.finditer(text or ""):
        cand = _vault_markdown_candidate(_md_link_target(m), vault_root)
        if cand:
            out.append(cand)
    return out


def strip_attached_media(text: str, attached_paths: list, vault_root: str) -> str:
    """Bỏ ![alt](local-path) khỏi text nếu đúng file đó đã được xếp hàng gửi riêng.

    Không đụng link thường, URL web hoặc ảnh chưa attach được. Nhờ vậy Telegram không hiện
    nguyên `![...](99 - Attachments/...)` bên cạnh ảnh thật.
    """
    attached = set()
    for path in attached_paths or []:
        try:
            attached.add(os.path.normcase(os.path.normpath(os.path.abspath(str(path)))))
        except Exception:
            pass
    if not attached:
        return text or ""

    def repl(match):
        if match.group(1) != "!":
            return match.group(0)
        cand = _vault_markdown_candidate(_md_link_target(match), vault_root)
        if cand and os.path.normcase(os.path.normpath(cand)) in attached:
            return ""
        return match.group(0)

    cleaned = _MD_LINK_RE.sub(repl, text or "")
    cleaned = re.sub(r"[ \t]+\n", "\n", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


# Ứng viên đường dẫn moi từ payload một tool call. Token = cụm không chứa khoảng trắng và
# ký tự bao thường gặp trong JSON/shell; "trông giống đường dẫn" = có dấu phân cách thư mục
# VÀ kết thúc bằng phần mở rộng. Cố tình chặt ở đây chứ không chặt ở tầng trên, vì tầng trên
# (collect_turn_files) đã lọc bằng "tệp có thật" + "vừa đổi trong lượt này".
_TOOL_TOKEN_RE = re.compile(r"""[^\s"'`,;{}()\[\]<>|]+""")
_TOOL_PATH_RE = re.compile(r"[\\/].*\.[A-Za-z0-9]{1,8}$")


def candidate_paths_from_tool(item, _depth: int = 0) -> list:
    """Mọi chuỗi trông giống đường dẫn tệp trong payload của một tool call.

    Vì sao cần: Codex CLI KHÔNG phát ra trường `file_path` có cấu trúc như Claude - tuỳ loại
    item mà đường dẫn nằm trong `changes[].path`, trong `arguments` (chuỗi JSON), hay lẫn
    trong `command` của một lệnh shell. Thay vì đoán đúng một khuôn (schema của Codex còn
    đổi), hàm này đi hết payload và THU RỘNG mọi thứ trông giống đường dẫn.

    Thu rộng là an toàn: `collect_turn_files` phía sau chỉ giữ tệp CÓ THẬT và VỪA ĐỔI trong
    lượt này, nên ứng viên thừa lặng lẽ rơi, còn thiếu thì mất file của user.
    """
    out = []
    if _depth > 6:
        return out
    if isinstance(item, dict):
        for v in item.values():
            out += candidate_paths_from_tool(v, _depth + 1)
    elif isinstance(item, (list, tuple)):
        for v in item:
            out += candidate_paths_from_tool(v, _depth + 1)
    elif isinstance(item, str):
        s = item.strip()
        if s[:1] in ("{", "["):
            # `arguments` thường là chuỗi JSON: giải mã trước, kẻo dấu \ bị nhân đôi.
            try:
                return candidate_paths_from_tool(json.loads(s), _depth + 1)
            except Exception:
                pass
        for tok in _TOOL_TOKEN_RE.findall(s):
            tok = tok.rstrip(".,;:!?…")
            if _TOOL_PATH_RE.search(tok):
                out.append(tok)
    seen, uniq = set(), []
    for p in out:
        if p not in seen:
            seen.add(p)
            uniq.append(p)
    return uniq


def collect_turn_files(reply_text: str, written_paths: list, t0: float,
                       cwd: str = None, exclude: set = None, vault_root: str = None) -> list:
    """Danh sách file đáng gửi trả về kênh chat sau 1 lượt.

    Ứng viên = file agent ghi bằng tool Write (written_paths) + đường dẫn tuyệt đối
    nhắc trong câu trả lời cuối + đường dẫn TƯƠNG ĐỐI trong vault nhúng dạng markdown
    (![](attachments/x.png) - ảnh Javis tạo) khi có vault_root. Chỉ giữ file THẬT SỰ
    vừa thay đổi trong lượt (mtime >= t0) - nhắc tới file cũ sẽ không spam gửi lại; muốn
    gửi file cũ thì agent gọi endpoint /telegram/send-file. exclude = set path (normcase)
    đã gửi trong lượt qua endpoint, tránh gửi trùng.
    """
    cands = []
    for p in (written_paths or []):
        try:
            pp = Path(str(p))
            if not pp.is_absolute() and cwd:
                pp = Path(cwd) / pp
            cands.append(str(pp))
        except Exception:
            continue
    cands += extract_paths(reply_text)
    # Ảnh/tệp Javis tạo trong lượt thường được NHÚNG dạng path tương đối trong vault
    # (![](attachments/x.png)); resolve về gốc vault để tự đính kèm về ĐÚNG phiên chat.
    cands += resolve_vault_relative(reply_text, vault_root)

    seen = set(exclude or ())
    out = []
    for c in cands:
        try:
            rp = os.path.normpath(os.path.abspath(c))
            key = os.path.normcase(rp)
            if key in seen:
                continue
            p = Path(rp)
            if not p.is_file():
                continue
            if any(part in _EXCLUDE_PARTS for part in p.parts):
                continue
            st = p.stat()
            if not (0 < st.st_size <= MAX_FILE_MB * 1024 * 1024):
                continue
            if st.st_mtime < t0 - 2:   # chỉ file vừa tạo/sửa trong lượt này
                continue
            seen.add(key)
            out.append(rp)
            if len(out) >= MAX_FILES_PER_TURN:
                break
        except Exception:
            continue
    return out


# ============================================================
# Hạ khối điều khiển xuống chữ cho kênh không phải web
# ============================================================
# Javis nhúng khối điều khiển dạng HTML comment ở cuối câu trả lời cho dashboard
# đọc (hiện chỉ còn JAVIS_ASK - vẽ nút lựa chọn). Kênh chữ thuần như Telegram không
# hiểu mấy khối này, mà md_to_mdv2 chỉ escape chứ không bóc, nên không lọc là người
# dùng nhìn thấy nguyên cụm "<\!\-\- JAVIS\_ASK: ...".
# Regex để CHUNG cho mọi JAVIS_*, không liệt kê từng tên: khối lạ (vd JAVIS_METRICS
# thời còn bảng số liệu, hoặc ký ức cũ trong brain còn nhắc) thì lặng lẽ rơi mất
# thay vì lọt nguyên xi ra chat.
_CTRL_RE = re.compile(r"<!--\s*JAVIS_([A-Z_]+):\s*([\s\S]*?)\s*-->")
_MAX_ASK_OPTS = 4


def _ask_to_text(payload: str) -> str:
    """JSON của khối JAVIS_ASK -> câu hỏi + danh sách đánh số. JSON hỏng -> chuỗi rỗng.

    Người dùng Telegram nhắn lại "1" là xong: Javis đọc "1" trong ngữ cảnh câu hỏi
    vừa hỏi thì tự hiểu, không cần lưu state.
    """
    try:
        o = json.loads(payload)
    except Exception:
        return ""
    if not isinstance(o, dict):
        return ""
    q = str(o.get("question") or "").strip()
    opts = [x for x in (o.get("options") or [])
            if isinstance(x, dict) and str(x.get("label") or "").strip()]
    if not q or not opts:
        return ""
    lines = [q]
    for i, x in enumerate(opts[:_MAX_ASK_OPTS], 1):
        lines.append(f"{i}. {str(x['label']).strip()}")
    return "\n".join(lines)


def strip_control_blocks(text: str) -> str:
    """Bóc mọi khối <!-- JAVIS_*: ... --> khỏi text.

    JAVIS_ASK -> thay bằng câu hỏi + danh sách đánh số. Khối khác -> bỏ hẳn.
    Khối sai cú pháp cũng bị bỏ: một khối hỏng KHÔNG được phép nuốt mất câu trả lời.
    """
    def _sub(m):
        if m.group(1) == "ASK":
            t = _ask_to_text(m.group(2))
            return ("\n\n" + t) if t else ""
        return ""

    out = _CTRL_RE.sub(_sub, text or "")
    return re.sub(r"\n{3,}", "\n\n", out).strip()
