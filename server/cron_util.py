"""
cron_util.py - Bộ đọc & tính lịch cron 5 trường cho Javis (KHÔNG phụ thuộc thư viện ngoài).

Vì project giữ dependency tối giản (không có croniter), module này tự parse biểu thức cron
chuẩn 5 trường "phút giờ ngày-tháng tháng thứ" và tính LẦN CHẠY KẾ TIẾP sau một mốc thời gian.
Dùng cho nhắc hẹn/job định kỳ (reminders.py): mỗi lần fire xong tính due_at kế tiếp qua cron_next.

Hỗ trợ mỗi trường: '*'  '*/n'  'a'  'a-b'  'a-b/n'  'a,b,c' (kết hợp). Tên tháng (jan..dec) và
thứ (sun..sat) chấp nhận. dow: 0=Chủ nhật..6=Thứ bảy (7 cũng = Chủ nhật). Macro: @hourly @daily
@midnight @weekly @monthly @yearly/@annually. Ngữ nghĩa Vixie: nếu CẢ ngày-tháng lẫn thứ đều
bị giới hạn (khác '*') thì 1 ngày khớp khi khớp MỘT trong hai (OR).

Tính theo timezone truyền vào (Javis dùng giờ VN UTC+7 - offset cố định, không DST nên số học
datetime an toàn).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone, tzinfo
from typing import Optional, Set, Tuple

import lang_registry   # tên thứ trong tuần theo ngôn ngữ

_MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], start=1)}
_DOWS = {d: i for i, d in enumerate(
    ["sun", "mon", "tue", "wed", "thu", "fri", "sat"], start=0)}

_MACROS = {
    "@hourly": "0 * * * *",
    "@daily": "0 0 * * *",
    "@midnight": "0 0 * * *",
    "@weekly": "0 0 * * 0",
    "@monthly": "0 0 1 * *",
    "@yearly": "0 0 1 1 *",
    "@annually": "0 0 1 1 *",
}

# (lo, hi) hợp lệ cho từng trường: minute, hour, dom, month, dow
_BOUNDS = [(0, 59), (0, 23), (1, 31), (1, 12), (0, 7)]

_MAX_YEARS_AHEAD = 5   # cron không chạy trong 5 năm coi như bất khả thi → lỗi


def _parse_atom(atom: str, lo: int, hi: int, names: dict) -> Tuple[Set[int], bool]:
    """1 phần (giữa các dấu phẩy). Trả (tập giá trị, is_star). Trường cron không có số âm."""
    atom = atom.strip().lower()
    if atom == "":
        raise ValueError("trường cron rỗng")
    step = 1
    if "/" in atom:                       # tách bước /n
        base, _, s = atom.partition("/")
        if not s.isdigit() or int(s) < 1:
            raise ValueError(f"bước cron không hợp lệ: {atom}")
        step = int(s)
        atom = base.strip() or "*"

    def _num(tok: str) -> int:
        tok = tok.strip().lower()
        if tok in names:
            return names[tok]
        if not tok.isdigit():
            raise ValueError(f"giá trị cron không hiểu: {tok}")
        return int(tok)

    if atom == "*":
        start, end, is_star = lo, hi, (step == 1)
    elif "-" in atom:
        a, _, b = atom.partition("-")
        start, end, is_star = _num(a), _num(b), False
    else:
        v = _num(atom)
        start, end, is_star = v, (hi if step != 1 else v), False   # "n/step" = n..hi bước step
    if start > end:
        raise ValueError(f"khoảng cron ngược: {atom}")
    vals = {v for v in range(start, end + 1, step) if lo <= v <= hi}
    if not vals:
        raise ValueError(f"trường cron không có giá trị hợp lệ: {atom}")
    return vals, is_star


def _parse_field(spec: str, lo: int, hi: int, names: dict) -> Tuple[Set[int], bool]:
    """Cả trường (có thể nhiều phần ngăn bởi ','). is_star = True chỉ khi trường phủ '*'."""
    out: Set[int] = set()
    is_star = False
    for part in (spec.strip().lower() or "*").split(","):
        vals, st = _parse_atom(part, lo, hi, names)
        out |= vals
        is_star = is_star or st
    return out, is_star


class CronExpr:
    __slots__ = ("minutes", "hours", "doms", "months", "dows", "dom_star", "dow_star", "raw")

    def __init__(self, expr: str):
        self.raw = expr.strip()
        s = self.raw.lower()
        if s in _MACROS:
            s = _MACROS[s]
        fields = s.split()
        if len(fields) != 5:
            raise ValueError("cron phải có 5 trường (phút giờ ngày tháng thứ) hoặc macro @daily...")
        self.minutes, _ = _parse_field(fields[0], 0, 59, {})
        self.hours, _ = _parse_field(fields[1], 0, 23, {})
        self.doms, self.dom_star = _parse_field(fields[2], 1, 31, {})
        self.months, _ = _parse_field(fields[3], 1, 12, _MONTHS)
        dows, self.dow_star = _parse_field(fields[4], 0, 7, _DOWS)
        self.dows = {0 if d == 7 else d for d in dows}   # 7 → 0 (Chủ nhật)

    def _day_ok(self, dt: datetime) -> bool:
        cron_dow = (dt.weekday() + 1) % 7   # Python: Mon=0..Sun=6 → cron: Sun=0..Sat=6
        dom_hit = dt.day in self.doms
        dow_hit = cron_dow in self.dows
        if not self.dom_star and not self.dow_star:
            return dom_hit or dow_hit      # ngữ nghĩa Vixie: cả hai giới hạn → OR
        if not self.dom_star:
            return dom_hit
        if not self.dow_star:
            return dow_hit
        return True

    def next_after(self, after: datetime) -> datetime:
        """Lần khớp đầu tiên STRICTLY sau 'after' (đã có tzinfo)."""
        dt = (after + timedelta(minutes=1)).replace(second=0, microsecond=0)
        limit_year = after.year + _MAX_YEARS_AHEAD
        while dt.year <= limit_year:
            if dt.month not in self.months:
                dt = _first_of_next_month(dt)
                continue
            if not self._day_ok(dt):
                dt = (dt + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
                continue
            if dt.hour not in self.hours:
                dt = (dt + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
                continue
            if dt.minute not in self.minutes:
                dt = (dt + timedelta(minutes=1)).replace(second=0, microsecond=0)
                continue
            return dt
        raise ValueError(f"cron '{self.raw}' không có lần chạy nào trong {_MAX_YEARS_AHEAD} năm tới")


def _first_of_next_month(dt: datetime) -> datetime:
    y, m = (dt.year + 1, 1) if dt.month == 12 else (dt.year, dt.month + 1)
    return dt.replace(year=y, month=m, day=1, hour=0, minute=0, second=0, microsecond=0)


def validate_cron(expr: str) -> str:
    """Parse + thử tính 1 lần chạy để bắt biểu thức bất khả thi. Trả biểu thức đã chuẩn hoá
    (hạ chữ thường). Ném ValueError nếu sai."""
    ce = CronExpr(expr)
    ce.next_after(datetime(2000, 1, 1, tzinfo=timezone.utc))
    return ce.raw.lower()


def cron_next(expr: str, after_epoch: float, tz: tzinfo) -> float:
    """Epoch (giây) của lần chạy kế tiếp sau 'after_epoch', tính theo timezone tz."""
    after = datetime.fromtimestamp(float(after_epoch), tz)
    return CronExpr(expr).next_after(after).timestamp()


# ── Đọc cron thành lời ────────────────────────────────────────────────────────
# "0 7 * * *" là thứ chỉ dân kỹ thuật đọc được. Người dùng nhìn thẻ việc mà không biết nó chạy
# lúc nào thì coi như lịch đó vô hình - nên mọi chỗ hiện cron PHẢI kèm câu tiếng Việt này.
# Chữ để đọc cron thành lời, theo ngôn ngữ. Tên thứ lấy từ sổ đăng ký ngôn ngữ (nó đã có
# `weekdays` cho đồng hồ), chỉ các cụm nối là riêng của cron nên khai ở đây.
#
# Cron dùng 0 = CHỦ NHẬT, còn `weekdays` của sổ đăng ký theo `datetime.weekday()` tức 0 = THỨ
# HAI. Lệch một vòng, và quên đổi thì mọi lịch "thứ hai hằng tuần" hiện thành "chủ nhật" - sai
# im lặng, người dùng chỉ phát hiện khi việc chạy nhầm ngày.
_CHU_CRON = {
    "vi": {"moi_ngay": "mỗi ngày", "hang_tuan": "{d} hằng tuần",
           "hang_thang": "ngày {d} hằng tháng", "trong_thang": " trong tháng ",
           "moi_phut": "mỗi phút", "moi_phut_trong_gio": "mỗi phút trong giờ {h}",
           "moi_n_phut": "mỗi {n} phút", "phut_moi_gio": "phút {m:02d} mỗi giờ",
           "moi_n_gio": "mỗi {n} giờ (phút {m:02d})"},
    "en": {"moi_ngay": "every day", "hang_tuan": "every {d}",
           "hang_thang": "day {d} of each month", "trong_thang": " in month ",
           "moi_phut": "every minute", "moi_phut_trong_gio": "every minute during hour {h}",
           "moi_n_phut": "every {n} minutes", "phut_moi_gio": "at minute {m:02d} of every hour",
           "moi_n_gio": "every {n} hours (at minute {m:02d})"},
}


def _chu(lang: str) -> dict:
    return _CHU_CRON.get(lang_registry.chuan_hoa(lang) or lang_registry.MAC_DINH,
                         _CHU_CRON[lang_registry.MAC_DINH])


def _ten_thu(d: int, lang: str) -> str:
    """Tên thứ cho MÃ CRON (0 = chủ nhật). Xem ghi chú về lệch một vòng ở trên."""
    tuan = lang_registry.get(lang).weekdays
    if not tuan or len(tuan) != 7:
        return str(d)
    return tuan[6 if d == 0 else d - 1]


def _is_step(vals: Set[int], lo: int, hi: int) -> Optional[int]:
    """vals có đúng dạng lo, lo+n, lo+2n... phủ hết khoảng? Trả n (bước), None nếu không."""
    s = sorted(vals)
    if len(s) < 2 or s[0] != lo:
        return None
    n = s[1] - s[0]
    if n < 2 or any(b - a != n for a, b in zip(s, s[1:])):
        return None
    if s[-1] + n <= hi:            # còn chỗ cho một giá trị nữa mà thiếu → không phải bước đều
        return None
    return n


def _hhmm(h: int, m: int) -> str:
    return f"{h}:{m:02d}"


def describe_cron(expr: str, lang: str = "") -> str:
    """Biểu thức cron → câu tiếng Việt ngắn ("7:00 mỗi ngày", "mỗi 30 phút", "9:00 thứ hai
    hằng tuần"). Dạng lạ/phức tạp thì trả lại chính biểu thức - thà thô còn hơn nói sai giờ.
    Không bao giờ ném lỗi: đây là chuỗi hiển thị, cron sai đã bị validate_cron bắt từ lúc tạo.

    Ngôn ngữ chưa có bộ chữ cron thì rơi về tiếng Việt chứ KHÔNG rơi về biểu thức thô: một câu
    sai ngôn ngữ vẫn đọc được giờ, còn "0 7 * * *" thì không đọc được."""
    C = _chu(lang)
    try:
        ce = CronExpr(expr)
    except Exception:
        return str(expr or "").strip()

    # Phạm vi NGÀY: mỗi ngày / các thứ trong tuần / ngày trong tháng.
    if ce.dom_star and ce.dow_star:
        scope = C["moi_ngay"]
    elif ce.dom_star:
        days = ", ".join(_ten_thu(d, lang) for d in sorted(ce.dows))
        scope = C["hang_tuan"].format(d=days)
    elif ce.dow_star:
        days = ", ".join(str(d) for d in sorted(ce.doms))
        scope = C["hang_thang"].format(d=days)
    else:
        return ce.raw          # vừa giới hạn thứ vừa giới hạn ngày (ngữ nghĩa OR) - đừng diễn giải
    if len(ce.months) != 12:
        scope += C["trong_thang"] + ", ".join(str(m) for m in sorted(ce.months))

    # Phạm vi GIỜ/PHÚT.
    every_min = len(ce.minutes) == 60
    every_hour = len(ce.hours) == 24
    if every_min:
        return C["moi_phut"] if every_hour else C["moi_phut_trong_gio"].format(
            h=", ".join(str(h) for h in sorted(ce.hours)))
    min_step = _is_step(ce.minutes, 0, 59)
    if min_step and every_hour:
        return C["moi_n_phut"].format(n=min_step)
    if len(ce.minutes) == 1:
        mm = next(iter(ce.minutes))
        if every_hour:
            return C["phut_moi_gio"].format(m=mm)
        hour_step = _is_step(ce.hours, 0, 23)
        if hour_step:
            return C["moi_n_gio"].format(n=hour_step, m=mm)
        times = ", ".join(_hhmm(h, mm) for h in sorted(ce.hours))
        return f"{times} {scope}"
    if len(ce.hours) == 1:
        h = next(iter(ce.hours))
        times = ", ".join(_hhmm(h, m) for m in sorted(ce.minutes))
        return f"{times} {scope}"
    return ce.raw
