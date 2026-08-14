"""Plugin bundled: tool javis_schedule - tạo/liệt kê/huỷ việc định kỳ + nhắc hẹn từ chat.

Trước tool này, chat muốn tạo việc định kỳ phải TỰ GÕ YAML frontmatter vào Javis/loops/<slug>.md,
hoặc shell ra curl POST /reminders (reminders.py:17 mô tả đúng đường đó). Tool này gói cả hai kho
lại sau MỘT tool duy nhất, tự route đúng chỗ theo bản chất lịch:

    - Lịch LẶP + BỀN ("120m", "mỗi 2 tiếng", "2h", "90 phút") -> ghi thẳng file
      <vault_root>/Javis/loops/<slug>.md. Loop VỐN LÀ 1 file .md (self_improve.py) - scheduler
      nền tự đọc thư mục, không cần gọi API nào. KHÔNG dùng POST /loops vì route đó cần đăng
      nhập, plugin (chạy in-process từ mọi engine, kể cả localhost không có session) gọi không
      tới (main.py không liệt /loops vào _AUTH_LOCAL_EXACT).
    - Lịch giờ CỐ ĐỊNH lặp lại (cron 5 trường "0 7 * * *", macro "@daily"...) hoặc MỘT LẦN
      ("30 phút nữa", "8h30", ngày giờ đầy đủ) -> gọi HTTP POST /reminders trên 127.0.0.1 (đường
      này CỐ Ý miễn đăng nhập cho localhost - main.py:70 _AUTH_LOCAL_EXACT).

An toàn (BẮT BUỘC, không nhận tham số để đổi):
    - Loop tạo qua chat LUÔN enabled: false + mode: suggest. Luật CLAUDE.md: "KHÔNG bao giờ tự
      đặt mode: full".
    - ctx.vault_root RỖNG -> báo lỗi rõ, TUYỆT ĐỐI không âm thầm rơi về Brain Default (đây chính
      là bug Task 1 vừa vá ở image_gen/_plugins_server - đừng tái tạo).
    - Trùng slug (đã có việc lặp cùng tên) -> báo lỗi, KHÔNG ghi đè: self_improve.py lấy định
      danh loop theo TÊN FILE, đẻ bản ascii song song thì bản gốc vẫn chạy -> thành 2 loop.
    - op=list PHẢI nhìn CẢ HAI kho (loops + reminders) - nhìn thiếu 1 kho thì model sẽ báo "không
      có việc nào" trong khi việc nằm ở kho kia.
"""
from __future__ import annotations

import os
import re
import unicodedata
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import httpx
import json
import yaml

# Múi giờ đọc từ cấu hình; rơi về UTC+7 khi plugin chạy ngoài tiến trình server.
def _tz():
    try:
        import localefmt
        return localefmt.tz()
    except Exception:
        return timezone(timedelta(hours=7))

# Frontmatter loop: ---\n<yaml>\n---\n<body> (khớp _FM_RE của self_improve.py)
_FM_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", re.DOTALL)

# Đơn vị chu kỳ/thời lượng chấp nhận, đã bỏ dấu tiếng Việt -> hệ số quy đổi ra PHÚT. Thứ tự
# trong _UNIT_ALT CÓ Ý NGHĨA: chuỗi dài/cụ thể hơn phải đứng TRƯỚC chuỗi ngắn là tiền tố của nó
# (vd "phut" trước "p", "hour" trước "h", "minute"/"min" trước "m") - regex alternation của
# Python khớp theo THỨ TỰ xuất hiện, không phải khớp dài nhất. "ngay"/"tuan"/"thang" không phải
# tiền tố của token nào khác nên chèn ở đâu cũng an toàn.
_UNIT_MINUTES = {
    "phut": 1, "minute": 1, "min": 1, "p": 1, "m": 1,
    "tieng": 60, "hour": 60, "gio": 60, "h": 60,
    "ngay": 1440, "tuan": 10080, "thang": 43200,
}
_UNIT_ALT = "phut|tieng|gio|hour|ngay|tuan|thang|minute|min|p|h|m"
# Đơn vị đứng MỘT MÌNH không kèm số ("mỗi ngày", "mỗi tuần", "mỗi tháng") -> ngầm định số lượng 1.
_BARE_UNIT_RE = re.compile(rf"\b({_UNIT_ALT})\b")

_CRON_TOKEN_RE = re.compile(r"^[\dA-Za-z*/,\-]+$")
# Chu kỳ THUẦN dạng "<số><đơn vị>" (không khoảng trắng, không chữ thừa) - vd "120m", "2h", "90phut".
_INTERVAL_FULL_RE = re.compile(rf"^\d+(?:[.,]\d+)?(?:{_UNIT_ALT})$")
# Tìm số + đơn vị BẤT KỲ ĐÂU trong chuỗi (cho phép có tiền tố "mỗi", khoảng trắng giữa số/đơn vị).
_INTERVAL_SEARCH_RE = re.compile(rf"(\d+(?:[.,]\d+)?)\s*({_UNIT_ALT})")
# Mốc TƯƠNG ĐỐI kiểu "<số><đơn vị>[nữa|tới|sau]" (hậu tố tuỳ chọn) - dùng khi tạo nhắc một lần.
_RELATIVE_DELAY_RE = re.compile(rf"^(\d+(?:[.,]\d+)?)({_UNIT_ALT})(?:nua|toi|sau)?$")

# Mốc GIỜ CỐ ĐỊNH kiểu "7h", "7h30", "07:00" - dùng để dò lịch "mỗi sáng 7h" cần LẶP HẰNG NGÀY
# ở đúng 1 giờ trong ngày (cron), khác hẳn "mỗi 7 tiếng" (duration thuần, lặp theo khoảng cách).
_CLOCK_RE = re.compile(r"\b(\d{1,2})[h:](\d{2})?\b")
_DAYPART_WORDS = ("sang", "trua", "chieu", "toi")


def _port() -> int:
    try:
        return int(os.getenv("JAVIS_PORT", "7777"))
    except (TypeError, ValueError):
        return 7777


def _today() -> str:
    return datetime.now(_tz()).strftime("%Y-%m-%d")


def _strip_diacritics(s: str) -> str:
    """Bỏ dấu tiếng Việt + hạ chữ thường (khớp cách _ascii_slug của self_improve.py làm)."""
    s = (s or "").lower().replace("đ", "d")
    s = unicodedata.normalize("NFD", s)
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


def _slugify_vn(name: str) -> str:
    """Tên tiếng Việt bất kỳ -> slug ascii an toàn cho tên file. Rỗng -> 'viec'."""
    t = _strip_diacritics(name)
    t = re.sub(r"[^a-z0-9]+", "-", t)
    t = t.strip("-")
    return t or "viec"


def _is_cron(schedule: str) -> bool:
    """Cron 5 trường (phút giờ ngày tháng thứ) hoặc macro '@daily'... (cron_util.py)."""
    s = (schedule or "").strip()
    if not s:
        return False
    if s.startswith("@"):
        return True
    parts = s.split()
    return len(parts) == 5 and all(_CRON_TOKEN_RE.match(p) for p in parts)


def _daily_cron(schedule: str) -> Optional[str]:
    """Dò lịch dạng MỐC GIỜ CỐ ĐỊNH lặp HẰNG NGÀY ('mỗi sáng 7h', 'mỗi ngày lúc 8h', '7h sáng
    hằng ngày') -> cron 5 trường 'M H * * *'. Trả None nếu KHÔNG phải dạng này (vd 'mỗi 7 tiếng'
    hay 'mỗi 2 tiếng' - duration thuần lặp theo KHOẢNG CÁCH, không có tín hiệu mốc-giờ-trong-ngày).

    Phân biệt bằng 2 tín hiệu PHẢI CÓ CẢ HAI: (a) chuỗi có ý LẶP HẰNG NGÀY - từ "mỗi" + một
    buổi trong ngày (sáng/trưa/chiều/tối) hoặc từ "ngày", hoặc cụm "hằng ngày"; VÀ (b) có một
    mốc giờ đồng hồ (7h, 7h30, 07:00) trong chuỗi. Thiếu 1 trong 2 -> None, để chỗ gọi tự rơi về
    nhánh cũ (duration/relative-delay) - KHÔNG đoán bừa."""
    norm = _strip_diacritics(schedule or "")
    has_moi = bool(re.search(r"\bmoi\b", norm))
    has_hang_ngay = "hang ngay" in norm
    if not (has_moi or has_hang_ngay):
        return None
    has_daypart = any(re.search(rf"\b{w}\b", norm) for w in _DAYPART_WORDS)
    has_ngay = bool(re.search(r"\bngay\b", norm))
    if not (has_daypart or has_ngay):
        return None   # "mỗi 7h"/"mỗi 2 tiếng" - không có tín hiệu HẰNG NGÀY, để nguyên là duration
    m = _CLOCK_RE.search(norm)
    if not m:
        return None   # có ý lặp hằng ngày nhưng KHÔNG có mốc giờ cụ thể ("mỗi sáng") -> chưa đủ để làm cron
    hour = int(m.group(1))
    minute = int(m.group(2)) if m.group(2) else 0
    if re.search(r"\b(chieu|toi)\b", norm) and hour < 12:
        hour += 12   # "7h tối"/"7h chiều" nói theo giờ 12h -> quy về giờ 24h
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return None
    return f"{minute} {hour} * * *"


def _route_kind(schedule: str, notify_only: bool = False) -> str:
    """Phân loại 1 chuỗi lịch: 'loop' (lặp + bền, ghi file) hay 'reminder' (kho nhắc hẹn có sẵn).

    notify_only=True luôn ép về reminder (chỉ muốn nhắc 1 lần, dù chuỗi trông giống chu kỳ)."""
    if notify_only:
        return "reminder"
    s = (schedule or "").strip()
    if _is_cron(s):
        return "reminder"          # cron đã có sẵn kho reminders lo, không cần ghi loop
    if _daily_cron(s):
        return "reminder"          # mốc giờ cố định lặp hằng ngày ("mỗi sáng 7h") -> cron ở kho reminders
    norm = _strip_diacritics(s)
    if re.search(r"\bmoi\b", norm):
        return "loop"               # "mỗi 2 tiếng" - từ "mỗi" tự thân đã là dấu hiệu LẶP ĐỊNH KỲ
    compact = norm.replace(" ", "")
    if _INTERVAL_FULL_RE.fullmatch(compact):
        return "loop"               # chu kỳ thuần "120m"/"2h"/"90phut" - không lẫn chữ thừa
    return "reminder"                # còn lại: mốc một lần ("30 phút nữa", "8h30", ISO...)


def _interval_min(schedule: str) -> Optional[int]:
    """Rút số phút từ 1 chuỗi chu kỳ ('120m'->120, '2 tiếng'/'2h'->120, 'mỗi ngày'->1440,
    'mỗi tuần'->10080, 'mỗi tháng'->43200 - đơn vị đứng một mình không kèm số thì ngầm định
    số lượng 1). Tối thiểu 5 phút (khớp trần cứng self_improve.py:257).

    Trả None khi KHÔNG rút được đơn vị/số nào rõ ràng (lịch mơ hồ, vd 'mỗi sáng' không kèm giờ
    hay đơn vị). Nơi gọi BẮT BUỘC coi None là lỗi cần hỏi lại model - TUYỆT ĐỐI không tự rơi về
    một số phút mặc định: chạy nhầm mỗi 5 phút là đốt tiền + spam Telegram thật (fail loudly)."""
    norm = _strip_diacritics(schedule)
    m = _INTERVAL_SEARCH_RE.search(norm)
    if m:
        try:
            num = float(m.group(1).replace(",", "."))
        except ValueError:
            return None
        factor = _UNIT_MINUTES.get(m.group(2), 1)
        return max(5, int(round(num * factor)))
    bare = _BARE_UNIT_RE.search(norm)
    if bare:
        return max(5, _UNIT_MINUTES.get(bare.group(1), 1))
    return None


def _yaml_scalar(s: str) -> str:
    """Trích dẫn 1 giá trị chuỗi thành scalar YAML AN TOÀN TUYỆT ĐỐI, dùng cho MỌI giá trị chuỗi
    do người/model nhập (tên việc, owner_chat...). KHÔNG liệt kê ký tự chỉ-thị cần escape (đó là
    trò đuổi bắt không bao giờ hết - bỏ sót 1 ký tự như '-' đầu chuỗi, '@', '*', '!', '%', '?',
    '|', '&', '>' là ghi ra frontmatter vỡ, yaml.safe_load ném ScannerError/ConstructorError, và
    self_improve.list_loops() nuốt lỗi bằng try/except nên loop CHẾT ÂM THẦM, biến mất khỏi tab
    Việc mà tool vẫn báo "đã tạo thành công").

    Thay vào đó LUÔN trả về chuỗi nháy kép kiểu JSON: YAML 1.2 là superset của JSON nên chuỗi
    nháy kép JSON LUÔN là scalar YAML hợp lệ trong mọi trường hợp, và json.dumps tự lo escape
    dấu ngoặc kép, dấu gạch chéo ngược, xuống dòng - không cần tự viết regex escape."""
    return json.dumps(str(s or ""), ensure_ascii=False)


def _loops_dir(vault_root: str) -> Path:
    return Path(vault_root) / "Javis" / "loops"


def _create_loop_file(vault_root: str, name: str, prompt: str, schedule: str,
                      owner_chat: str = "", brain_name: str = "") -> str:
    """Ghi 1 loop mới vào <vault_root>/Javis/loops/<slug>.md. AN TOÀN CỨNG (không nhận tham số
    để đổi): enabled luôn false, mode luôn suggest. Trùng slug (việc đã có) -> báo lỗi rõ, KHÔNG
    ghi đè - self_improve.py lấy định danh loop theo TÊN FILE nên đẻ bản ascii song song sẽ để
    bản gốc vẫn chạy, thành 2 loop làm cùng 1 việc."""
    if not vault_root:
        return "ERROR: không xác định được brain đang làm việc"
    name = (name or "").strip() or "Việc mới"
    prompt = (prompt or "").strip()
    if not prompt:
        return "ERROR: thiếu 'prompt' - mỗi vòng loop cần biết làm gì (viết tự-đủ, không phụ thuộc chat)"
    slug = _slugify_vn(name)
    d = _loops_dir(vault_root)
    fp = d / f"{slug}.md"
    if fp.exists():
        return (f"ERROR: đã có việc tên '{name}' (Javis/loops/{slug}.md) - "
                 f"sửa nó thay vì tạo bản sao (vd đổi lịch/nội dung của file đó)")
    interval = _interval_min(schedule)
    if interval is None:
        return (f"ERROR: không rõ chu kỳ '{schedule}' - nói rõ số + đơn vị (vd '120m', '2 tiếng', "
                 f"'mỗi ngày', 'mỗi tuần', 'mỗi tháng'), hoặc nếu là mốc giờ cố định thì dùng cron "
                 f"5 trường (vd '0 7 * * *' = 7h sáng mỗi ngày). TUYỆT ĐỐI không tự đoán 5 phút.")
    frontmatter = (
        "---\n"
        "type: loop\n"
        f"name: {_yaml_scalar(name)}\n"
        f"slug: {slug}\n"
        "enabled: false\n"
        "mode: suggest\n"
        # goal: custom - BẮT BUỘC, KHÔNG được để self_improve.py mặc định 'business' (đọc
        # self_improve.py:250,546). goal='business' bỏ qua HOÀN TOÀN loop["body"] (chỉ đọc số
        # liệu MCP), nên nếu thiếu dòng này, prompt user vừa gõ (thân file dưới đây) không bao
        # giờ được loop đọc tới - loop tạo ra "thành công" nhưng KHÔNG làm đúng việc user yêu cầu.
        "goal: custom\n"
        f"interval_min: {interval}\n"
        f"owner_chat: {_yaml_scalar((owner_chat or '').strip())}\n"
        f"updated: {_today()}\n"
        "---\n"
        "\n"
        f"{prompt}\n"
    )
    try:
        d.mkdir(parents=True, exist_ok=True)
        tmp = fp.with_suffix(".md.tmp")
        tmp.write_text(frontmatter, encoding="utf-8")
        tmp.replace(fp)
    except Exception as e:
        return f"ERROR: ghi file loop lỗi: {type(e).__name__}: {e}"
    where = f" trong brain {brain_name}" if brain_name else ""
    return (f"Đã tạo việc lặp '{name}'{where} (Javis/loops/{slug}.md), chạy mỗi {interval} phút. "
             f"Đang TẮT (enabled: false) và chỉ-gợi-ý (mode: suggest) theo luật an toàn - "
             f"vào tab Việc trong dashboard để bật thật.")


def _list_loops(vault_root: str) -> list:
    """Đọc rút gọn mọi loop trong <vault_root>/Javis/loops. Không import self_improve.py (tránh
    kéo theo main.py) - tự đọc frontmatter tối giản, đủ để liệt kê cho model đọc lại."""
    out = []
    if not vault_root:
        return out
    d = _loops_dir(vault_root)
    if not d.is_dir():
        return out
    for fp in sorted(d.glob("*.md")):
        try:
            text = fp.read_text(encoding="utf-8")
        except Exception:
            continue
        m = _FM_RE.match(text)
        if not m:
            continue
        try:
            fm = yaml.safe_load(m.group(1)) or {}
        except Exception:
            fm = {}
        if not isinstance(fm, dict):
            fm = {}
        out.append({
            "id": fp.stem,
            "name": str(fm.get("name") or fp.stem),
            "enabled": bool(fm.get("enabled", False)),
            "mode": str(fm.get("mode", "suggest") or "suggest"),
            "interval_min": fm.get("interval_min", 0),
        })
    return out


def _cancel_loop_file(vault_root: str, slug: str) -> str:
    d = _loops_dir(vault_root)
    fp = d / f"{slug}.md"
    try:
        if fp.resolve().parent != d.resolve():
            return "ERROR: id không hợp lệ"
    except Exception:
        return "ERROR: id không hợp lệ"
    if not fp.is_file():
        return f"ERROR: không thấy việc lặp '{slug}' trong Javis/loops"
    try:
        fp.unlink()
    except Exception as e:
        return f"ERROR: xoá file lỗi: {type(e).__name__}: {e}"
    return f"Đã xoá việc lặp '{slug}'."


def _reminder_time_payload(schedule: str) -> dict:
    """Suy tham số thời gian cho POST /reminders từ 1 chuỗi lịch. Cron -> {'cron'}. Mốc giờ cố
    định lặp hằng ngày ('mỗi sáng 7h') -> {'cron'} suy từ _daily_cron. Mốc tương đối kiểu
    '<n> <đơn vị> [nữa|tới|sau]' -> {'delay_min'}. Còn lại (HH:MM, '8h30', ngày giờ đầy đủ) ->
    {'at': schedule nguyên văn}, để reminders.resolve_due tự hiểu (cùng định dạng nó vốn chấp
    nhận khi engine gọi curl trực tiếp)."""
    s = (schedule or "").strip()
    if _is_cron(s):
        return {"cron": s}
    cron = _daily_cron(s)
    if cron:
        return {"cron": cron}
    norm = _strip_diacritics(s).replace(" ", "")
    m = _RELATIVE_DELAY_RE.match(norm)
    if m:
        try:
            num = float(m.group(1).replace(",", "."))
        except ValueError:
            num = None
        if num is not None:
            factor = _UNIT_MINUTES.get(m.group(2), 1)
            return {"delay_min": num * factor}
    return {"at": s}


# C1 (bảo mật/ổn định server): 3 hàm gọi HTTP dưới đây BẮT BUỘC là async + httpx.AsyncClient.
# Handler plugin chạy TRÊN event loop chính của uvicorn (plugins_host._make_call gọi
# `res = handler(args, ctx)` rồi mới await - KHÔNG bọc asyncio.to_thread). httpx.post ĐỒNG BỘ ở
# đây gọi vào CHÍNH server đang chạy nó (127.0.0.1:_port()) -> khoá luôn event loop đang cần
# rảnh để tự trả lời request đó -> deadlock/ReadTimeout, treo TOÀN BỘ server (mọi user, mọi tool)
# cho tới khi hết timeout. Xem mẫu async đúng: system/plugins/meta-ads-graph/plugin.py `_get()`,
# system/plugins/image-chatgpt/plugin.py `_gen()`. test_javis_schedule.py có lưới hồi quy
# (inspect.iscoroutinefunction) chặn ai đó quay lại lối sync.
async def _post_reminder(payload: dict, brain_name: str = "") -> str:
    """Tạo 1 nhắc hẹn/job qua HTTP POST /reminders trên localhost (miễn đăng nhập -
    main.py:70 _AUTH_LOCAL_EXACT, đúng đường agent vốn gọi bằng curl - reminders.py:17)."""
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.post(f"http://127.0.0.1:{_port()}/reminders", json=payload)
        data = r.json()
    except Exception as e:
        return f"ERROR: gọi kho nhắc hẹn lỗi: {type(e).__name__}: {e}"
    if not data.get("ok"):
        if data.get("can_force"):
            # THIẾU ĐIỀU KIỆN, không phải lỗi cú pháp. Model TUYỆT ĐỐI không được tự vượt rào:
            # phải nói thiếu gì rồi để user quyết. Đây đúng cái khách phàn nàn - Javis dựng cron
            # "báo qua Telegram" trong khi Telegram còn chưa đấu, rồi im lặng không nói gì.
            return (f"ERROR: {data.get('error')}\n"
                    "→ BÁO LẠI CHO USER đúng thứ còn thiếu ở trên và HỎI: đấu Telegram trước, "
                    "hay vẫn tạo dù chưa ai nhận được báo? User đồng ý tạo tiếp thì gọi lại tool "
                    "với allow_no_channel=true. KHÔNG tự quyết hộ.")
        return f"ERROR: {data.get('error') or 'tạo nhắc hẹn thất bại'}"
    where = f" (brain {brain_name})" if brain_name else ""
    if data.get("cron"):
        lich = data.get("cron_human") or data["cron"]
        ra = (f"Đã đặt lịch lặp {lich} (cron {data['cron']}){where} (id {data.get('id')}), "
              f"lần chạy kế tiếp {data.get('due_human') or '?'}.")
    else:
        ra = f"Đã đặt nhắc hẹn lúc {data.get('due_human') or '?'}{where} (id {data.get('id')})."
    # Việc tới giờ tự chạy MỘT MÌNH với đầy đủ quyền. Máy chủ gửi kèm câu cảnh báo; đọc lại
    # NGUYÊN VĂN cho user chứ đừng tóm tắt hay bỏ qua - đây là lúc duy nhất họ chắc chắn đang
    # nhìn, và sau đó thì không ai duyệt gì nữa.
    if data.get("canh_bao"):
        ra += ("\n\n" + data["canh_bao"]
               + "\n(NÓI LẠI nguyên văn đoạn cảnh báo trên cho user, đừng nuốt.)")
    return ra


async def _get_reminders(vault_root: str) -> dict:
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.get(f"http://127.0.0.1:{_port()}/reminders", params={"brain": vault_root})
        d = r.json()
        return d if isinstance(d, dict) else {"pending": [], "history": []}
    except Exception as e:
        return {"pending": [], "history": [], "error": f"{type(e).__name__}: {e}"}


async def _cancel_reminder(vault_root: str, rid: str) -> str:
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.post(f"http://127.0.0.1:{_port()}/reminders/cancel",
                             data={"id": rid, "brain": vault_root})
        data = r.json()
    except Exception as e:
        return f"ERROR: huỷ nhắc hẹn lỗi: {type(e).__name__}: {e}"
    if data.get("ok"):
        return f"Đã huỷ nhắc hẹn {rid}."
    return f"ERROR: không huỷ được ({data.get('error') or 'không rõ lý do (có thể id sai/đã xong)'})."


async def _do_create(vault_root: str, args: dict) -> str:
    name = str(args.get("name") or "").strip()
    prompt = str(args.get("prompt") or "").strip()
    schedule = str(args.get("schedule") or "").strip()
    if not name or not prompt or not schedule:
        return "ERROR: cần đủ 'name', 'prompt' và 'schedule' để tạo việc."
    notify_only = bool(args.get("notify_only") or False)
    chat_id = str(args.get("chat_id") or args.get("owner_chat") or "").strip()
    brain_name = Path(vault_root).name   # tên brain phiên → nói cho user biết việc rơi vào đâu
    kind = _route_kind(schedule, notify_only)
    if kind == "loop":
        return _create_loop_file(vault_root, name=name, prompt=prompt, schedule=schedule,
                                 owner_chat=chat_id, brain_name=brain_name)
    # I2: notify_only=True nghĩa là CHỈ nhắc bằng lời (mode "notify" - reminders.py:342 "⏰ Nhắc
    # anh: ..."), KHÔNG dựng nguyên engine Claude + MCP để "làm hộ" (mode "task" - reminders.py:
    # 418 _run_task, tốn tới max_wall_s=300). Trước đây hard-code "task" nên notify_only vô nghĩa -
    # mọi nhắc đều chạy LLM dù model chỉ được yêu cầu NHẮC.
    payload = {"text": prompt, "label": name, "mode": ("notify" if notify_only else "task"),
               "brain": vault_root, "chat_id": chat_id, "created_by": "javis_schedule",
               "allow_no_channel": bool(args.get("allow_no_channel") or False)}
    # Bỏ trống thì máy chủ tự đặt mặc định; chỉ gửi khi model có ý hạ/nâng mức rõ ràng.
    if str(args.get("muc_quyen") or "").strip():
        payload["muc_quyen"] = str(args["muc_quyen"]).strip().lower()
    payload.update(_reminder_time_payload(schedule))
    return await _post_reminder(payload, brain_name=brain_name)


async def _update_reminder(vault_root: str, rid: str, fields: dict) -> str:
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.post(f"http://127.0.0.1:{_port()}/reminders/update",
                             data=dict({"id": rid, "brain": vault_root}, **fields))
        data = r.json()
    except Exception as e:
        return f"ERROR: sửa lịch lỗi: {type(e).__name__}: {e}"
    if not data.get("ok"):
        return f"ERROR: {data.get('error') or 'không sửa được'}"
    rem = data.get("reminder") or {}
    when = rem.get("cron_human") or rem.get("cron") or ""
    return (f"Đã sửa lịch {rid}" + (f" thành '{when}'" if when else "")
            + f", lần chạy kế tiếp {rem.get('due_human') or '?'}.")


def _update_loop_file(vault_root: str, slug: str, fields: dict) -> str:
    """Sửa loop bằng cách ghi lại frontmatter. Chỉ nhận name/prompt/schedule - các trường an toàn
    (enabled/mode) vẫn phải bật tay trên dashboard, đúng luật loop tạo qua chat."""
    fp = _loops_dir(vault_root) / f"{slug}.md"
    try:
        if fp.resolve().parent != _loops_dir(vault_root).resolve() or not fp.is_file():
            return f"ERROR: không thấy việc lặp '{slug}'"
        text = fp.read_text(encoding="utf-8")
    except Exception as e:
        return f"ERROR: đọc file loop lỗi: {type(e).__name__}: {e}"
    m = _FM_RE.match(text)
    if not m:
        return f"ERROR: file loop '{slug}' không có frontmatter hợp lệ"
    try:
        fm = yaml.safe_load(m.group(1)) or {}
    except Exception as e:
        return f"ERROR: frontmatter lỗi: {e}"
    if not isinstance(fm, dict):
        return "ERROR: frontmatter lỗi"
    body = m.group(2)
    if fields.get("name"):
        fm["name"] = str(fields["name"])
    if fields.get("prompt"):
        body = str(fields["prompt"]).strip() + "\n"
    if fields.get("schedule"):
        interval = _interval_min(str(fields["schedule"]))
        if interval is None:
            return (f"ERROR: không rõ chu kỳ '{fields['schedule']}' - nói rõ số + đơn vị "
                    f"(vd '120m', '2 tiếng', 'mỗi ngày')")
        fm["interval_min"] = interval
    fm["updated"] = _today()
    lines = ["---"]
    for k, v in fm.items():
        lines.append(f"{k}: " + (_yaml_scalar(v) if isinstance(v, str) else json.dumps(v)))
    lines += ["---", "", body.strip(), ""]
    try:
        tmp = fp.with_suffix(".md.tmp")
        tmp.write_text("\n".join(lines), encoding="utf-8")
        tmp.replace(fp)
    except Exception as e:
        return f"ERROR: ghi file loop lỗi: {type(e).__name__}: {e}"
    return (f"Đã sửa việc lặp '{fm.get('name') or slug}' (mỗi {fm.get('interval_min')} phút). "
            f"Trạng thái bật/tắt giữ nguyên.")


async def _do_update(vault_root: str, args: dict) -> str:
    rid = str(args.get("id") or "").strip()
    if not rid:
        return "ERROR: cần 'id' để sửa (lấy từ op=list)."
    fields = {}
    if str(args.get("name") or "").strip():
        fields["name"] = str(args["name"]).strip()
    if str(args.get("prompt") or "").strip():
        fields["prompt"] = str(args["prompt"]).strip()
    if str(args.get("schedule") or "").strip():
        fields["schedule"] = str(args["schedule"]).strip()
    if not fields:
        return "ERROR: không có gì để sửa - truyền ít nhất một trong name / prompt / schedule."
    if (_loops_dir(vault_root) / f"{rid}.md").is_file():
        return _update_loop_file(vault_root, rid, fields)
    # Kho nhắc hẹn: đổi lịch thì dịch chuỗi lịch sang tham số thời gian như lúc tạo.
    payload = {}
    if "name" in fields:
        payload["label"] = fields["name"]
    if "prompt" in fields:
        payload["text"] = fields["prompt"]
    if "schedule" in fields:
        payload.update(_reminder_time_payload(fields["schedule"]))
    return await _update_reminder(vault_root, rid, payload)


async def _do_list(vault_root: str) -> str:
    lines = []
    loops = _list_loops(vault_root)
    if loops:
        lines.append("Việc LẶP (Javis/loops):")
        for lp in loops:
            trang = "bật" if lp["enabled"] else "tắt"
            lines.append(f"- [{lp['id']}] {lp['name']} - mỗi {lp['interval_min']} phút, "
                         f"đang {trang}, mode {lp['mode']}")
    rem = await _get_reminders(vault_root)
    pending = rem.get("pending") or []
    if pending:
        lines.append("Nhắc hẹn / lịch (kho reminders):")
        for r in pending:
            # Nói lịch bằng LỜI ("7:00 mỗi ngày") kèm biểu thức thô - model kể lại cho user thì
            # user hiểu ngay, không phải tự dịch "0 7 * * *".
            extra = (f" (lặp {r.get('cron_human') or r.get('cron')} - cron {r.get('cron')})"
                     if r.get("cron") else "")
            lines.append(f"- [{r.get('id')}] {r.get('label') or r.get('text')} - "
                         f"kế tiếp {r.get('due_human')}{extra}")
    if rem.get("error"):
        lines.append(f"(không đọc được kho nhắc hẹn: {rem['error']})")
    if not lines:
        return "Chưa có việc định kỳ hay nhắc hẹn nào (cả kho loop lẫn kho reminders đều trống)."
    return "\n".join(lines)


async def _do_cancel(vault_root: str, args: dict) -> str:
    rid = str(args.get("id") or "").strip()
    if not rid:
        return "ERROR: cần 'id' để huỷ (lấy từ kết quả op=list)."
    if (_loops_dir(vault_root) / f"{rid}.md").is_file():
        return _cancel_loop_file(vault_root, rid)
    return await _cancel_reminder(vault_root, rid)


async def javis_schedule(args: dict, cctx) -> str:
    args = args or {}
    vault_root = getattr(cctx, "vault_root", None)
    # An toàn CỨNG: đây chính là bug Task 1 vừa vá ở nơi khác (image_gen._resolve_vault rơi về
    # Brain Default khi vault_root rỗng, lưu nhầm brain suốt mà không ai biết). Không tái tạo.
    if not vault_root:
        return "ERROR: không xác định được brain đang làm việc"
    op = str(args.get("op") or "create").strip().lower()
    if op == "create":
        return await _do_create(vault_root, args)
    if op == "list":
        return await _do_list(vault_root)
    if op == "update":
        return await _do_update(vault_root, args)
    if op == "cancel":
        return await _do_cancel(vault_root, args)
    return f"ERROR: op không hợp lệ: {op!r} (dùng create|list|update|cancel)"


def register(ctx) -> None:
    ctx.register_tool(
        name="javis_schedule",
        description=(
            "Tạo/liệt kê/sửa/huỷ việc chạy ĐỊNH KỲ hoặc NHẮC HẸN ngay từ chat - thay vì tự gõ YAML "
            "vào Javis/loops hay tự curl POST /reminders. GỌI khi user nói kiểu: 'tạo cho tôi "
            "việc mỗi 2 tiếng quét đơn' (op=create, schedule='120m' hoặc 'mỗi 2 tiếng'), '7h "
            "sáng nào cũng nhắc tôi doanh thu' (schedule='0 7 * * *'), '30 phút nữa nhắc tôi "
            "gọi khách' (schedule='30 phút nữa'), 'còn việc gì đang chạy không' (op=list), hoặc "
            "'đổi giờ việc đó sang 8h' (op=update, id lấy từ op=list, schedule='0 8 * * *'), hoặc "
            "'huỷ việc quét đơn đi' (op=cancel, id lấy từ op=list trước). "
            "ĐỦ ĐIỀU KIỆN MỚI TẠO: trước khi op=create, tự hỏi việc này tới giờ chạy có ĐỦ thứ "
            "cần không (nguồn dữ liệu đã đấu chưa, kênh báo kết quả đã có chưa). Thiếu thì NÓI "
            "THẲNG thiếu gì và hỏi user, KHÔNG tạo trước rồi im lặng để nó chạy thất bại mỗi ngày. "
            "CHỈ GỌI khi user ra lệnh rõ ràng với lịch tự động của Javis; KHÔNG gọi chỉ vì câu có "
            "'đặt lịch', booking, tư vấn 1-1, cuộc hẹn, hoặc đang bàn về sản phẩm/UX/marketing. "
            "Trong các trường hợp đó phải trả lời hội thoại bình thường, không op=list/create/cancel. "
            "Tool TỰ CHỌN kho: lịch "
            "LẶP+BỀN ('120m'/'2h'/'mỗi X tiếng'/'90 phút') ghi file Javis/loops/<slug>.md (sửa "
            "được trong Obsidian, mặc định TẮT + chỉ-gợi-ý, phải vào tab Việc bật tay); lịch giờ "
            "cố định lặp lại (cron 5 trường '0 7 * * *', macro '@daily') hoặc một lần ('30 phút "
            "nữa', '8h30', '2026-07-20 09:00') vào kho nhắc hẹn có sẵn."
        ),
        handler=javis_schedule,
        min_mode="safe",
        schema={
            "type": "object",
            "properties": {
                "op": {"type": "string", "enum": ["create", "list", "update", "cancel"],
                       "description": ("create = tạo việc mới (cần name/prompt/schedule); "
                                       "list = liệt kê MỌI việc đang có, cả loop lẫn nhắc hẹn; "
                                       "update = sửa việc đã có theo id (truyền name/prompt/"
                                       "schedule - trường nào không truyền thì giữ nguyên); "
                                       "cancel = huỷ 1 việc theo id (lấy từ op=list).")},
                "name": {"type": "string",
                         "description": "Tên ngắn của việc, vd 'Quét đơn mỗi 2 tiếng' (op=create)."},
                "prompt": {"type": "string",
                           "description": ("Nội dung cần làm mỗi lần chạy/nhắc (op=create) - viết "
                                           "TỰ ĐỦ, không phụ thuộc ngữ cảnh chat hiện tại vì sẽ "
                                           "chạy lúc không ai hỏi.")},
                "schedule": {"type": "string",
                             "description": ("Lịch (op=create). Lặp+bền: '120m' (mỗi 120 phút), "
                                             "'2h', 'mỗi 2 tiếng', '90 phút'. Cố định lặp lại: "
                                             "cron 5 trường '0 7 * * *', macro '@daily'. Một lần: "
                                             "'30 phút nữa', '8h30' (qua giờ hôm nay -> tự sang "
                                             "mai), hoặc đủ ngày giờ '2026-07-20 09:00'.")},
                "notify_only": {"type": "boolean",
                                 "description": ("true = ép thành nhắc MỘT LẦN (kho reminders) dù "
                                                 "schedule trông giống chu kỳ lặp. Mặc định false.")},
                "muc_quyen": {"type": "string", "enum": ["suggest", "auto", "full"],
                              "description": ("Quyền của việc lúc tới giờ chạy. 'full' (mặc định) "
                                              "= dùng được mọi công cụ đã đấu, gồm cả hành động "
                                              "ra ngoài - cần cho việc kiểu 'tới giờ thì gửi/"
                                              "đăng/đặt'. 'auto' = đọc + ghi file, không hành "
                                              "động ra ngoài. 'suggest' = chỉ đọc rồi báo lại. "
                                              "Chỉ hạ mức khi user muốn vậy.")},
                "chat_id": {"type": "string",
                             "description": "chat_id Telegram người yêu cầu, để báo đúng người. Bỏ trống nếu không rõ."},
                "allow_no_channel": {"type": "boolean",
                                      "description": ("Chỉ đặt true khi tool đã báo THIẾU KÊNH GỬI, "
                                                      "bạn đã nói với user thiếu gì, và user vẫn "
                                                      "muốn tạo. TUYỆT ĐỐI không tự đặt true ngay "
                                                      "lần gọi đầu.")},
                "id": {"type": "string",
                       "description": "id việc cần sửa/huỷ (op=update|cancel) - lấy từ kết quả op=list."},
            },
            "required": ["op"],
        },
    )
