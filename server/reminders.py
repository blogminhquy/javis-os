"""
reminders.py - Nhắc hẹn từ chat cho Javis: "30 phút nữa nhắc anh...", "8h30 sáng mai...".

Vá đúng lỗ hổng người dùng nêu: Javis GỬI được Telegram ngay lúc chat, nhưng CHƯA tự
hẹn giờ để thức dậy gửi SAU. Module này thêm hàng đợi nhắc hẹn BỀN (JSON trong vault,
git-backed) + để scheduler nền (main._scheduler_loop, tick 30s) đánh thức đúng giờ:
  - mode "notify" (mặc định): tới giờ bắn thẳng tin nhắc qua Telegram cho ĐÚNG người đã đặt.
  - mode "task"            : tới giờ chạy engine làm việc đã hẹn rồi gửi kết quả về Telegram.
                             Quyền theo `muc_quyen` (suggest | auto | full, mặc định full).
                             Kết quả MỞ ĐẦU hoặc KẾT THÚC bằng [SILENT] → im lặng, vẫn lưu vào bản ghi.
  - mode "script"          : job KHÔNG cần LLM (rẻ, để giám sát) - chạy script có sẵn trong
                             <brain>/Javis/scripts, đẩy stdout về Telegram; exit≠0 → cảnh báo lỗi,
                             stdout rỗng hoặc có cờ [SILENT] → im lặng (port ý no_agent của Hermes).

Lịch: hẹn 1-lần (delay_min|at|due_at) HOẶC định kỳ bằng biểu thức CRON 5 trường (cron_util.py,
tự viết, không phụ thuộc lib). Có cron thì mỗi lần fire xong tự tính due_at kế tiếp.

Tạo nhắc: engine (Javis) tự gọi POST /reminders qua Bash curl từ localhost khi user nói
"nhắc anh ..." (endpoint được khai báo trong channel_context). Dashboard tạo/sửa/huỷ/xoá được
qua /reminders, /reminders/update, /reminders/cancel (giữ lịch sử), /reminders/delete (mất hẳn).

ĐỦ ĐIỀU KIỆN MỚI TẠO: notify/task tồn tại chỉ để BÁO cho người, mà kênh báo duy nhất là
Telegram. Chưa đấu Telegram thì _create ném NotifyNotReady kèm lý do, endpoint trả thêm cờ
can_force để chỗ gọi hỏi lại người dùng (allow_no_channel=true mới tạo tiếp). Trước đây job cứ
tạo, cứ chạy đúng giờ, rồi kết quả rơi vào hư không - người dùng tưởng Javis quên việc.
Thời gian do SERVER tính (giờ VN, UTC+7) từ delay_min | at | due_at → engine chỉ cần map câu
nói của user, KHỎI cần biết "bây giờ" trong prompt (giữ prompt-cache ổn định).

MỨC QUYỀN của mode "task": ba mức như loop (suggest chỉ đọc, auto thêm ghi file, full toàn
quyền), MẶC ĐỊNH `full`. Nhắc hẹn khác loop ở chỗ căn bản - nó làm ĐÚNG một việc người dùng đã
viết ra và hẹn giờ, tức là một câu lệnh trong chat được dời sang giờ khác - nên trói nó chặt
hơn lúc chat là tự mâu thuẫn. Bản 2026-08-07 còn trả kèm một câu cảnh báo `canh_bao` lúc tạo;
chủ repo bỏ hẳn luật "không giao tự động tiền/đơn/đăng bài/nhắn khách" ngày 2026-09-10 nên câu
đó đã gỡ. Xem `MUC_QUYEN_MAC_DINH`.

Module KHÔNG import main (tránh vòng lặp import): mọi helper tiêm qua RemindersDeps.
"""
from __future__ import annotations

import localefmt
import asyncio
import json
import os
import re
import shutil
import sys
import winproc         # lệnh con câm lặng trên Windows
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Callable, List, Optional

from fastapi import APIRouter, Body, Form, Query

import cron_util
import channel_context   # bóc khối JAVIS_* trước khi gửi Telegram - kênh chữ, không phải web
import once_ledger       # outside actions of one firing run once, across retries (0.238.0)
import turn_context


def _nhan_kw(fn, ten: str) -> bool:
    """Hàm `fn` có nhận tham số từ khoá `ten` không (hoặc **kwargs). Dùng để gửi thêm thông tin
    thẻ cho khung chat mà không làm vỡ những hàm gửi chỉ nhận (chat_id, text)."""
    import inspect
    try:
        ps = inspect.signature(fn).parameters.values()
    except (TypeError, ValueError):
        return False
    return any(p.name == ten or p.kind is p.VAR_KEYWORD for p in ps)
from claude_cli import claude_engine, _empty_mcp_file
import aux_engine   # engine viec nen theo model phu nguoi dung chon

# Múi giờ để tính giờ nhắc hẹn. Đọc từ cấu hình, KHÔNG còn ghim Việt Nam.
#
# Đây là chỗ đổi múi giờ có hệ quả THẤY NGAY: "7h sáng" phải là 7h sáng ở nơi người dùng ngồi,
# không phải 7h sáng ở Hà Nội. Ghim cứng thì người dùng ở múi giờ khác bị đánh thức lệch vài
# tiếng mỗi ngày, và không có gì trên màn hình nói cho họ biết vì sao.
#
# Giữ tên `VN_TZ` để không phải sửa 9 chỗ gọi, nhưng nó là HÀM chứ không phải hằng - đổi múi
# giờ ở trang Cài đặt là các lịch chờ tính lại theo múi mới ngay lượt quét sau.
def VN_TZ():
    return localefmt.tz()
VALID_MODE = {"notify", "task", "script"}

# Mức quyền của nhắc hẹn kiểu "task". Cùng bộ từ với loop để người dùng chỉ phải học một lần.
VALID_MUC_QUYEN = {"suggest", "auto", "full"}

# Mặc định TOÀN QUYỀN, và đây là một quyết định có chủ ý chứ không phải bỏ sót.
#
# Nhắc hẹn khác loop ở chỗ căn bản: loop tự nghĩ ra việc để làm mỗi vòng, còn nhắc hẹn làm ĐÚNG
# một việc người dùng đã viết ra và hẹn giờ từ trước. Nó là một câu lệnh trong chat được dời
# sang giờ khác, nên trói nó chặt hơn lúc chat là tự mâu thuẫn: người dùng gõ "10h mai gửi
# link vào nhóm" rồi tới giờ Javis báo về là nó không được phép gửi.
#
# Trước 2026-08-07 mức quyền bị ghim cứng ở chỉ-đọc, nên MỌI nhắc hẹn yêu cầu một hành động ra
# ngoài (gửi tin, đăng bài, đặt lịch, tạo đơn) đều thức dậy đúng giờ, chạy, rồi báo về là không
# làm được - trong khi việc thì vẫn chưa ai làm. Ai muốn mức nhẹ hơn thì đặt muc_quyen="suggest"
# hoặc "auto" cho nhắc hẹn đó.
MUC_QUYEN_MAC_DINH = "full"

NHAN_MUC_QUYEN = {"suggest": "chỉ đọc", "auto": "được ghi file", "full": "toàn quyền"}


def muc_quyen_cua(rem: dict) -> str:
    """Mức quyền một nhắc hẹn SẼ chạy. Bản ghi cũ chưa có trường này thì theo mặc định hiện tại.

    Đọc qua đây thay vì `rem.get("muc_quyen", ...)` rải khắp nơi: chỗ HIỂN THỊ và chỗ CHẠY phải
    nói cùng một con số, không thì thẻ ghi một đằng mà tới giờ nó làm một nẻo.
    """
    mq = str((rem or {}).get("muc_quyen") or "").strip().lower()
    return mq if mq in VALID_MUC_QUYEN else MUC_QUYEN_MAC_DINH
MIN_LEAD_S = 3                 # tối thiểu 3s trong tương lai (tránh bắn ngay/quá khứ)
MAX_DELAY_DAYS = 366           # trần: không hẹn quá ~1 năm (chỉ áp cho hẹn 1-lần, không áp cron)
MAX_FIRE_PER_TICK = 6          # trần số nhắc bắn mỗi nhịp (chống dồn spam khi server vừa bật lại)
MAX_KEEP = 500                 # trần số bản ghi giữ lại mỗi brain
SCRIPT_TIMEOUT_S = 120         # trần thời gian chạy 1 job script
SCRIPT_OUT_CAP = 3500          # trần ký tự stdout đẩy về Telegram
# "Remember the last run" (0.198.0, idea from OpenMausBot routines): a task-mode reminder can start from
# its previous result, so a watcher knows what it already reported. Capped so one long report
# cannot eat the next run's context.
PREVIOUS_RESULT_CAP = 2000
NEXT_RUNS_SHOWN = 3            # upcoming firings listed for a cron schedule
LATE_NOTE_AFTER_S = 15 * 60    # a firing this late (server off or busy) tells the model so

# Retry of a task-mode run that died on a NETWORK error (field report 0.270, code 26). The typical
# case: the machine was off at the scheduled time, the catch-up run starts seconds after it wakes,
# and DNS or Wi-Fi is not back yet ("getaddrinfo failed"). The run used to be recorded "done" with
# the error and never tried again. Now it waits and tries again, a bounded number of times; the
# delays are short enough to still be "this morning" and long enough for a network to come back.
RETRY_DELAYS_S = (5 * 60, 10 * 60, 20 * 60)
# Errors that say "the network was not there", not "the task is wrong". Deliberately narrow: a
# plain "timeout" is left out because the background wall-clock cap and long tool calls also
# time out, and re-running an hour-long task three times is worse than reporting it once.
_TRANSIENT_NET_RE = re.compile(
    r"getaddrinfo|name resolution|name or service not known|nodename nor servname|no address associated"
    r"|temporary failure in name|dns (?:error|lookup|resolution|failure)|ENOTFOUND|EAI_AGAIN"
    r"|ECONNREFUSED|ECONNRESET|ENETUNREACH|EHOSTUNREACH"
    r"|ETIMEDOUT|connect(?:ion)?\s*time(?:d)?\s*out|connecttimeout|connecterror|connectionerror"
    r"|connection (?:refused|reset|aborted|error|failed)|network (?:is )?unreachable|network error"
    r"|failed to establish a new connection|cannot connect to host|could not connect|unable to connect"
    r"|no route to host|socket hang up|server ?disconnected|no internet|mạng lỗi|rớt mạng|mất mạng|lỗi mạng",
    re.IGNORECASE)
# Errors a retry cannot fix even when a network word shows up in the same text.
_NOT_TRANSIENT_RE = re.compile(
    r"not logged in|unauthori[sz]ed|\b401\b|\b403\b|api[ _-]?key|invalid token|usage limit|limit reached"
    r"|hit your (?:\w+ )?limit|quota|hết lượt|insufficient|billing|not installed|chưa cài",
    re.IGNORECASE)


def is_transient_error(err: str) -> bool:
    """True when a failed run's error looks like the network was briefly away (DNS, refused or
    reset connection, unreachable host), so trying again a few minutes later can succeed."""
    text = str(err or "")
    return bool(_TRANSIENT_NET_RE.search(text)) and not _NOT_TRANSIENT_RE.search(text)


def ledger_job(rid: str, slot) -> str:
    """Once-only ledger key of ONE firing of a reminder (once_ledger.py). Every attempt of the same
    firing (first run, network retries, an incident retry) shares it, so an outside action that
    already went through is not sent again; the next cron slot is a new firing with a new key."""
    try:
        slot_txt = f"{float(slot):.0f}"
    except (TypeError, ValueError):
        slot_txt = str(slot or "")
    return f"reminder:{rid}:{slot_txt}"

# Đuôi file script → trình chạy. Chỉ chạy script CÓ SẴN trong <brain>/Javis/scripts (chủ tự viết),
# KHÔNG nhận lệnh tuỳ ý từ chat → chặn prompt-injection tạo job phá hoại.
_SCRIPT_RUNNERS = {
    ".py": [sys.executable],
    ".sh": ["bash"],
    ".ps1": ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File"],
    ".js": ["node"],
    ".bat": ["cmd", "/c"],
    ".cmd": ["cmd", "/c"],
}



def morning_brief_template() -> dict:
    """Ready-made "Morning brief" for the recurring-work page (0.222.0). Never created on its own:
    the page pre-fills the form with it and the person presses Save, so the usual checks still run
    (no report channel -> can_force). Read-and-report level: a brief only reads and summarises."""
    return {
        "id": "morning_brief",
        "label": localefmt.chu("Bản tin buổi sáng", "Morning brief"),
        "cron": "0 7 * * *",
        "mode": "task",
        "muc_quyen": "suggest",
        "text": localefmt.chu(
            "Soạn bản tin buổi sáng ngắn cho tôi, tối đa 10 dòng: "
            "1) chào và nói giờ hiện tại; "
            "2) lịch hôm nay nếu đã kết nối lịch (Google Calendar hay tương tự), chưa kết nối thì bỏ mục này; "
            "3) nhắc ngắn chuyện hôm qua đã bàn, đọc từ memory/conversations/ của ngày hôm qua nếu có; "
            "4) vài tin đáng chú ý trong lĩnh vực của tôi nếu có công cụ tìm kiếm web, không có thì bỏ. "
            "Không bịa số liệu: mục nào không có nguồn thì bỏ qua.",
            "Write me a short morning brief, 10 lines at most: "
            "1) greet me and say the current time; "
            "2) today's calendar if a calendar is connected (Google Calendar or similar), otherwise skip it; "
            "3) a short recap of what we discussed yesterday, from yesterday's file in memory/conversations/ if there is one; "
            "4) a few notable news items in my field if a web search tool is available, otherwise skip it. "
            "Do not invent numbers: skip any part that has no source."),
    }

class NotifyNotReady(ValueError):
    """Chưa có đường gửi kết quả (bot Telegram chưa bật / chưa có Chat ID).

    Tách riêng khỏi ValueError thường để endpoint trả thêm cờ can_force: đây KHÔNG phải lỗi cú
    pháp mà là THIẾU ĐIỀU KIỆN, và người dùng có quyền chọn tạo tiếp (kết quả chỉ lưu trong Javis).
    """

    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(localefmt.chu(
            f"Chưa gửi được kết quả về đâu: {reason}. Vào trang Kênh đấu bot Telegram "
            "(dán bot token + Chat ID) rồi tạo lại. Nếu vẫn muốn tạo, đặt allow_no_channel=true - "
            "việc sẽ chạy nhưng không ai được báo.",
            f"There is nowhere to send the result yet: {reason}. Connect a Telegram bot on the "
            "Channels page (paste the bot token + Chat ID), then create it again. To create it "
            "anyway, set allow_no_channel=true - it will run but nobody will be notified."
        ))


SILENT_MARK = "[SILENT]"


def _is_silent_task_result(body: str) -> bool:
    """True when a task reminder's answer opens or closes with the [SILENT] flag.

    Script jobs go quiet on [SILENT] anywhere in stdout. A model answer is prose that may
    mention the flag while explaining something, so a task only counts as silent when the
    flag OPENS or CLOSES the answer (0.408.0, `channel_context.is_silent_report`).
    """
    return channel_context.is_silent_report(body)


def _now() -> float:
    return time.time()


def _vnow() -> datetime:
    return datetime.now(VN_TZ())


def _fmt_vn(ts) -> str:
    try:
        return datetime.fromtimestamp(float(ts), VN_TZ()).strftime("%H:%M %d/%m/%Y")
    except Exception:
        return "?"


# ---- Chuẩn hoá thời điểm: delay_min | at | due_at → epoch (giây) ----
_AT_HHMM = re.compile(r"^(\d{1,2})[:h](\d{2})$")     # 8:30 / 8h30
_AT_HH = re.compile(r"^(\d{1,2})h$")                 # 8h
_AT_DATE = re.compile(r"^(\d{4})-(\d{1,2})-(\d{1,2})[ t](\d{1,2})[:h](\d{2})$")


def _parse_iso_vn(s: str) -> Optional[datetime]:
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M",
                "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(s, fmt).replace(tzinfo=VN_TZ())
        except ValueError:
            continue
    try:
        dt = datetime.fromisoformat(s)
        return dt.replace(tzinfo=VN_TZ()) if dt.tzinfo is None else dt
    except Exception:
        return None


def resolve_due(delay_min=None, delay_sec=None, at=None, due_at=None) -> float:
    """Trả epoch (giây) của thời điểm nhắc. Ưu tiên: delay_sec/delay_min > due_at > at.
    Ném ValueError nếu không hiểu / thiếu."""
    now = _now()
    # 1) delay tương đối (số phút/giây kể từ bây giờ)
    d = None
    if delay_sec not in (None, ""):
        d = float(delay_sec)
    elif delay_min not in (None, ""):
        d = float(delay_min) * 60.0
    if d is not None:
        if d < 0:
            raise ValueError(localefmt.chu("delay không được âm", "delay cannot be negative"))
        return now + max(d, MIN_LEAD_S)
    # 2) due_at tuyệt đối: epoch hoặc ISO
    if due_at not in (None, ""):
        s = str(due_at).strip()
        if re.fullmatch(r"\d{9,}(\.\d+)?", s):        # epoch giây (>= ~2001)
            return float(s)
        dt = _parse_iso_vn(s)
        if dt:
            return dt.timestamp()
        raise ValueError(localefmt.chu(f"due_at không hiểu: {due_at}", f"due_at not understood: {due_at}"))
    # 3) at: giờ trong ngày (HH:MM) hoặc ngày-giờ cụ thể
    if at not in (None, ""):
        s = str(at).strip().lower().replace("g", "h")   # "8g30" (kiểu VN) → "8h30"
        m = _AT_DATE.match(s)
        if m:
            y, mo, da, hh, mm = (int(x) for x in m.groups())
            try:
                return datetime(y, mo, da, hh, mm, tzinfo=VN_TZ()).timestamp()
            except ValueError as e:
                raise ValueError(localefmt.chu(f"ngày giờ sai: {at}", f"invalid date/time: {at}")) from e
        hh = mm = None
        m = _AT_HHMM.match(s)
        if m:
            hh, mm = int(m.group(1)), int(m.group(2))
        else:
            m = _AT_HH.match(s)
            if m:
                hh, mm = int(m.group(1)), 0
        if hh is None or not (0 <= hh <= 23 and 0 <= mm <= 59):
            raise ValueError(localefmt.chu(f"at không hiểu (dùng HH:MM hoặc YYYY-MM-DD HH:MM): {at}",
                                           f"at not understood (use HH:MM or YYYY-MM-DD HH:MM): {at}"))
        cand = _vnow().replace(hour=hh, minute=mm, second=0, microsecond=0)
        if cand.timestamp() <= now + MIN_LEAD_S:      # giờ đã qua trong hôm nay → sang mai
            cand = cand + timedelta(days=1)
        return cand.timestamp()
    raise ValueError(localefmt.chu("Thiếu thời điểm: cần delay_min HOẶC at HOẶC due_at",
                                   "Missing time: need delay_min OR at OR due_at"))


@dataclass
class RemindersDeps:
    brain_root: Callable[[str], str]
    atomic_write_text: Callable[[Any, str], None]
    send_telegram: Callable                    # async send_telegram(chat_id, text) -> (ok, err)
    build_system_prompt: Callable[[str], str]
    aux_model: Callable[[], Optional[str]]
    safe_tools: List[str]
    readonly_tools: List[str]
    scheduler_brains: Callable[[], List[str]]  # () -> danh sách brain scheduler quét
    apply_mcp: Optional[Callable] = None       # apply_mcp(cli, mode): gắn MCP Javis-quản-lý (đọc thật)
    mcp_allow_patterns: Optional[Callable] = None  # () -> ["mcp__<server>", ...] cho allowlist
    # Đổi engine việc nền theo model phụ người dùng chọn (Claude / Codex / API rẻ).
    # None = giữ nguyên Claude như trước (test dựng deps tối giản không cần tiêm).
    aux_swap: Optional[Callable] = None
    # () -> (sẵn_sàng, lý_do): có đường gửi kết quả cho người dùng chưa (bot Telegram bật +
    # token + Chat ID). None = bỏ qua kiểm tra (test dựng deps tối giản).
    notify_ready: Optional[Callable[[], tuple]] = None
    # 0.199.0: (source, ref, brain=, title=, error=, request=) -> report a broken run to Javis Core (incident_desk.py).
    incident_hook: Optional[Callable] = None
    # 0.202.0: async make_voice(brain, text) -> vault-relative mp3 path ("" on failure), and
    # async send_file(chat_id, abs_path, brain) -> (ok, err) for channels that need the file itself.
    make_voice: Optional[Callable] = None
    send_file: Optional[Callable] = None
    # register_brain(brain): remember a brain that now holds a reminder so `scheduler_brains`
    # keeps returning it (needed for folders outside BRAINS_DIR). None = nothing to register.
    register_brain: Optional[Callable[[str], None]] = None


class RemindersFeature:
    def __init__(self, deps: RemindersDeps):
        self.deps = deps
        self.lock = asyncio.Lock()   # serialize: 1 nhắc mode 'task' chạy engine/lần
        # Script jobs get their OWN lock. They call no model and finish within SCRIPT_TIMEOUT_S,
        # but sharing `self.lock` meant every script was skipped while one task-mode reminder
        # ran (up to an hour): a "follow up after 10 minutes" script with a 10-25 minute window
        # could miss customers right in business hours (field report 2026-10-13). Scripts still
        # run one at a time among themselves, since two of them may share state files.
        self.script_lock = asyncio.Lock()
        self._io = asyncio.Lock()    # serialize ghi file reminders.json
        # Nhắc mode task/script đang chạy NỀN (id) + các task asyncio đang sống, để tick sau
        # không bắn lại cùng một nhắc và để tắt máy chủ đợi được chúng.
        self._dang_chay: set = set()
        self._viec_nen: set = set()
        self.router = self._make_router()

    # ── store (JSON trong brain) ──
    def _path(self, brain: str) -> Path:
        return Path(self.deps.brain_root(brain)) / "Javis" / "reminders.json"

    def _load(self, brain: str) -> dict:
        data = {"reminders": [], "updated": 0.0}
        try:
            p = self._path(brain)
            if p.exists():
                d = json.loads(p.read_text(encoding="utf-8"))
                if isinstance(d, dict) and isinstance(d.get("reminders"), list):
                    data = d
        except Exception:
            pass
        return data

    def _save(self, brain: str, data: dict) -> None:
        data["updated"] = _now()
        self.deps.atomic_write_text(self._path(brain), json.dumps(data, ensure_ascii=False, indent=2))

    def _scripts_dir(self, brain: str) -> Path:
        return Path(self.deps.brain_root(brain)) / "Javis" / "scripts"

    def _resolve_script(self, brain: str, script: str) -> Path:
        """script CHỈ nhận TÊN FILE nằm trong <brain>/Javis/scripts (không path, không '..').
        Trả path thật đã kiểm tra tồn tại. Ném ValueError nếu không hợp lệ."""
        name = str(script or "").strip().replace("\\", "/")
        if not name:
            raise ValueError(localefmt.chu("mode 'script' cần tên file trong Javis/scripts",
                                           "mode 'script' needs a file name in Javis/scripts"))
        if "/" in name or name.startswith("."):
            raise ValueError(localefmt.chu("script chỉ nhận TÊN FILE trong Javis/scripts (không đường dẫn)",
                                           "script only takes a FILE NAME in Javis/scripts (no path)"))
        base = self._scripts_dir(brain)
        p = base / name
        try:
            rp, rbase = p.resolve(), base.resolve()
        except Exception:
            raise ValueError(localefmt.chu("đường dẫn script không hợp lệ", "invalid script path"))
        if rp.parent != rbase or not rp.is_file():
            raise ValueError(localefmt.chu(f"không thấy script '{name}' trong Javis/scripts",
                                           f"script '{name}' not found in Javis/scripts"))
        if rp.suffix.lower() not in _SCRIPT_RUNNERS and not os.access(rp, os.X_OK):
            raise ValueError(localefmt.chu(f"đuôi '{rp.suffix}' chưa hỗ trợ (dùng .py/.sh/.ps1/.js/.bat)",
                                           f"extension '{rp.suffix}' is not supported (use .py/.sh/.ps1/.js/.bat)"))
        return rp

    def notify_status(self) -> tuple:
        """(sẵn_sàng, lý_do) - có đường gửi kết quả cho người dùng hay không. Thiếu dep thì coi
        như sẵn sàng (test/embed tối giản), không tự dựng rào ở nơi không biết cấu hình."""
        if not self.deps.notify_ready:
            return True, ""
        try:
            ok, why = self.deps.notify_ready()
            return bool(ok), str(why or "")
        except Exception:
            return True, ""

    # ── tạo (sync; caller async giữ self._io) ──
    # (hàm module-level `muc_quyen_cua` ở cuối file - dùng chung cho _view và _run_task)
    def _create(self, brain: str, text: str, *, delay_min=None, at=None, due_at=None,
                chat_id="", mode="notify", repeat_min=0, label="", cron=None, script="",
                created_by="user", allow_no_channel=False, muc_quyen=None,
                remember_last=False, speak=False, call=False) -> dict:
        mode = mode if mode in VALID_MODE else "notify"
        mq = str(muc_quyen or "").strip().lower()
        mq = mq if mq in VALID_MUC_QUYEN else MUC_QUYEN_MAC_DINH
        # ĐỦ ĐIỀU KIỆN MỚI TẠO. notify/task tồn tại chỉ để BÁO cho người - chưa đấu Telegram thì
        # tới giờ nó chạy xong rồi ném kết quả vào hư không, người dùng tưởng Javis quên việc.
        # Thà chặn ngay lúc tạo và nói thiếu gì. (script = job giám sát, im lặng là bình thường.)
        if mode in ("notify", "task") and not allow_no_channel:
            ready, why = self.notify_status()
            if not ready:
                raise NotifyNotReady(why or localefmt.chu("chưa có kênh gửi", "no delivery channel yet"))
        text = (text or "").strip()
        script_name = ""
        if mode == "script":
            rp = self._resolve_script(brain, script)   # xác thực ngay lúc tạo (fail fast)
            script_name = rp.name
            if not text:
                text = f"chạy script {script_name}"
        elif not text:
            raise ValueError(localefmt.chu("Thiếu nội dung nhắc (text)", "Missing reminder content (text)"))
        cron_expr = (str(cron).strip() if cron not in (None, "") else "")
        if cron_expr:
            cron_expr = cron_util.validate_cron(cron_expr)     # chuẩn hoá + bắt lỗi
            due = cron_util.cron_next(cron_expr, _now(), VN_TZ())
            rep = 0                                            # cron thay cho repeat_min
        else:
            due = resolve_due(delay_min=delay_min, at=at, due_at=due_at)
            if due > _now() + MAX_DELAY_DAYS * 86400:
                raise ValueError(localefmt.chu("Hẹn quá xa (giới hạn ~1 năm)", "Too far ahead (limit ~1 year)"))
            try:
                rep = max(0, int(float(repeat_min or 0)))
            except (TypeError, ValueError):
                rep = 0
        rem = {
            "id": "r_" + uuid.uuid4().hex[:10],
            "text": text[:2000], "mode": mode, "due_at": float(due),
            "chat_id": str(chat_id or ""), "repeat_min": rep, "cron": cron_expr,
            "script": script_name, "label": (label or "")[:120], "status": "pending",
            "muc_quyen": mq,
            "remember_last": bool(remember_last),
            "speak": bool(speak) and mode != "script",
            # 0.203.0: ring the open dashboard as an incoming call at its time (dashboard/incoming-call.js).
            "call": bool(call) and mode != "script",
            "created_by": created_by, "created_at": _now(),
            "fired_at": 0.0, "result": "", "error": "",
        }
        data = self._load(brain)
        data.setdefault("reminders", []).append(rem)
        # Giữ gọn: quá trần thì bỏ bớt bản ghi đã đóng (pending luôn được giữ)
        rems = data["reminders"]
        if len(rems) > MAX_KEEP:
            rems.sort(key=lambda r: (r.get("status") != "pending", float(r.get("created_at", 0))))
            data["reminders"] = ([r for r in rems if r.get("status") == "pending"]
                                 + [r for r in rems if r.get("status") != "pending"])[:MAX_KEEP]
        self._save(brain, data)
        self._register(brain)
        return rem

    def _view(self, r: dict) -> dict:
        cron = r.get("cron", "") or ""
        return {"id": r.get("id"), "text": r.get("text"), "label": r.get("label"),
                "mode": r.get("mode"), "status": r.get("status"),
                "due_at": r.get("due_at"), "due_human": _fmt_vn(r.get("due_at", 0)),
                "chat_id": r.get("chat_id"), "repeat_min": r.get("repeat_min", 0),
                # cron_human: "0 7 * * *" đọc thành "7:00 mỗi ngày". Thẻ việc chỉ hiện biểu thức
                # thô thì người dùng không biết lịch chạy lúc nào - đúng lỗi khách báo.
                "cron": cron, "cron_human": cron_util.describe_cron(cron) if cron else "",
                "script": r.get("script", ""), "fired_at": r.get("fired_at", 0),
                # Bản ghi cũ (tạo trước khi có mức quyền) không có trường này → hiện đúng mức
                # nó SẼ chạy, chứ không phải để trống rồi người dùng tự đoán.
                "muc_quyen": muc_quyen_cua(r),
                "remember_last": bool(r.get("remember_last")),
                "speak": bool(r.get("speak")),
                "call": bool(r.get("call")),
                "next_runs": next_runs(cron) if cron and r.get("status") == "pending" else [],
                "result": (r.get("result") or "")[:500], "error": r.get("error", ""),
                # A pending network retry (code 26): which retry the next run is, out of how many.
                "retry_count": int(r.get("retry_count") or 0), "retry_max": len(RETRY_DELAYS_S)}

    def update(self, brain: str, rid: str, *, text=None, label=None, mode=None, chat_id=None,
               cron=None, at=None, delay_min=None, due_at=None, muc_quyen=None,
               remember_last=None, speak=None, call=None) -> dict:
        """Sửa 1 nhắc/lịch ĐANG CHỜ: nội dung, tên, kiểu, và thời điểm. Trả {"ok", "error",
        "reminder"}. Chỉ nhận tham số được truyền (None = giữ nguyên) nên gọi sửa một phần
        được. Đổi lịch thì tính lại due_at ngay để người dùng thấy lần chạy kế tiếp mới."""
        data = self._load(brain)
        cur = next((r for r in data.get("reminders", []) if r.get("id") == rid), None)
        if cur is None:
            return {"ok": False, "error": localefmt.chu("không thấy nhắc hẹn này", "reminder not found")}
        if cur.get("status") != "pending":
            return {"ok": False, "error": localefmt.chu("chỉ sửa được nhắc đang chờ (mục đã xong/đã huỷ thì tạo mới)",
                                                        "only pending reminders can be edited (create a new one for done/cancelled items)")}
        if text not in (None, ""):
            cur["text"] = str(text)[:2000]
        if label is not None:
            cur["label"] = str(label)[:120]
        if mode not in (None, ""):
            m = str(mode).strip().lower()
            if m not in VALID_MODE:
                return {"ok": False, "error": localefmt.chu(f"kiểu không hợp lệ: {mode}", f"invalid type: {mode}")}
            if cur.get("mode") == "script":
                pass   # job script GIỮ NGUYÊN kiểu (đổi là mất tên file script) - vẫn sửa được
                       # tên/nội dung/lịch, nên bỏ qua trường mode thay vì chặn cả lệnh sửa
            elif m == "script":
                return {"ok": False, "error": localefmt.chu("đổi sang job script thì tạo mới (cần chọn file script)",
                                                            "to switch to a script job, create a new one (a script file must be chosen)")}
            else:
                cur["mode"] = m
        if chat_id is not None:
            cur["chat_id"] = str(chat_id)
        if muc_quyen not in (None, ""):
            mq = str(muc_quyen).strip().lower()
            if mq not in VALID_MUC_QUYEN:
                return {"ok": False, "error": localefmt.chu(f"mức quyền không hợp lệ: {muc_quyen}", f"invalid permission level: {muc_quyen}")}
            cur["muc_quyen"] = mq
        if remember_last is not None:
            cur["remember_last"] = _truthy(remember_last)
        if speak is not None:
            cur["speak"] = _truthy(speak) and cur.get("mode") != "script"
        if call is not None:
            cur["call"] = _truthy(call) and cur.get("mode") != "script"
        has_when = any(v not in (None, "") for v in (cron, at, delay_min, due_at))
        if has_when:
            try:
                if cron not in (None, ""):
                    expr = cron_util.validate_cron(str(cron))
                    cur["cron"] = expr
                    cur["repeat_min"] = 0
                    cur["due_at"] = cron_util.cron_next(expr, _now(), VN_TZ())
                else:
                    due = resolve_due(delay_min=delay_min, at=at, due_at=due_at)
                    if due > _now() + MAX_DELAY_DAYS * 86400:
                        return {"ok": False, "error": localefmt.chu("Hẹn quá xa (giới hạn ~1 năm)", "Too far ahead (limit ~1 year)")}
                    cur["cron"] = ""          # chuyển lịch lặp → một lần: bỏ cron kẻo nó tự hồi sinh
                    cur["due_at"] = float(due)
            except ValueError as e:
                return {"ok": False, "error": str(e)}
        cur["error"] = ""                      # đã sửa thì lỗi lần chạy trước không còn đúng nữa
        if has_when:
            # A new time replaces a pending network retry: the next run is a fresh firing.
            cur.pop("retry_of", None)
            cur.pop("retry_count", None)
        self._save(brain, data)
        return {"ok": True, "error": "", "reminder": self._view(cur)}

    def delete(self, brain: str, rid: str) -> bool:
        """Xoá HẲN 1 bản ghi (khác cancel: cancel chỉ đổi trạng thái, mục vẫn nằm trong lịch sử).
        Trả True nếu có xoá."""
        data = self._load(brain)
        rems = data.get("reminders", [])
        left = [r for r in rems if r.get("id") != rid]
        if len(left) == len(rems):
            return False
        data["reminders"] = left
        self._save(brain, data)
        return True

    def cancel(self, brain: str, rid: str) -> bool:
        """Huỷ 1 nhắc (đồng bộ). Trả True nếu có đổi."""
        data = self._load(brain)
        hit = False
        for r in data.get("reminders", []):
            if r.get("id") == rid and r.get("status") == "pending":
                r["status"] = "cancelled"
                hit = True
        if hit:
            self._save(brain, data)
        return hit

    def pending_views(self, brain: str) -> list:
        """View các nhắc ĐANG CHỜ của 1 brain, sắp theo giờ tới. Dùng cho trang Việc gộp mọi
        brain (/viec/all) - tránh main.py thò vào _load/_view riêng tư."""
        rems = [r for r in self._load(brain).get("reminders", []) if r.get("status") == "pending"]
        rems.sort(key=lambda r: float(r.get("due_at") or 0))
        return [self._view(r) for r in rems]

    def move(self, from_brain: str, to_brain: str, rid: str) -> dict:
        """Dời 1 nhắc hẹn sang brain khác, giữ nguyên id + mọi field (cron/due_at/chat_id...).
        Trả {"ok":bool, "error":str}. Ghi ĐÍCH trước rồi mới xoá nguồn: sự cố giữa chừng để lại
        bản trùng (khôi phục được) chứ không mất record."""
        try:
            src_root = str(Path(self.deps.brain_root(from_brain)).resolve())
            dst_root = str(Path(self.deps.brain_root(to_brain)).resolve())
        except Exception:
            return {"ok": False, "error": localefmt.chu("brain không hợp lệ", "invalid brain")}
        if src_root == dst_root:
            return {"ok": False, "error": localefmt.chu("brain nguồn và đích trùng nhau", "source and target brain are the same")}
        src = self._load(from_brain)
        rec = next((r for r in src.get("reminders", []) if r.get("id") == rid), None)
        if rec is None:
            return {"ok": False, "error": localefmt.chu("không thấy nhắc hẹn ở brain nguồn", "reminder not found in the source brain")}
        dst = self._load(to_brain)
        dst.setdefault("reminders", []).append(rec)
        self._save(to_brain, dst)
        src["reminders"] = [r for r in src.get("reminders", []) if r.get("id") != rid]
        self._save(from_brain, src)
        self._register(to_brain)
        return {"ok": True}

    def _register(self, brain: str) -> None:
        if self.deps.register_brain:
            try:
                self.deps.register_brain(brain)
            except Exception as e:
                print(f"[reminders] register brain {brain}: {type(e).__name__}: {e}", file=sys.stderr)

    def _tick_brains(self) -> list:
        """The brains one tick visits, deduplicated by resolved root: "brain" and the default
        brain's path name the same folder, and visiting it twice would read its store twice."""
        try:
            cands = list(self.deps.scheduler_brains() or []) + ["brain"]
        except Exception:
            cands = ["brain"]
        out, seen = [], set()
        for b in cands:
            try:
                root = str(Path(self.deps.brain_root(b)).resolve())
            except Exception:
                continue
            if root in seen:
                continue
            seen.add(root)
            out.append(b)
        return out

    # ── scheduler gọi mỗi nhịp ──
    async def tick(self) -> None:
        for brain in self._tick_brains():
            try:
                await self._tick_brain(brain)
            except Exception as e:
                print(f"[reminders tick {brain}] {type(e).__name__}: {e}", file=sys.stderr)

    async def _tick_brain(self, brain: str) -> None:
        now = _now()
        async with self._io:
            due = [r for r in self._load(brain).get("reminders", [])
                   if r.get("status") == "pending" and float(r.get("due_at", 0)) <= now]
        if not due:
            return
        due.sort(key=lambda r: float(r.get("due_at", 0)))
        fired = 0
        for rem in due:
            if fired >= MAX_FIRE_PER_TICK:
                break
            if rem.get("mode") in ("task", "script"):
                if self._khoa(rem.get("mode")).locked() or rem.get("id") in self._dang_chay:
                    continue   # đang có 1 job chạy → để nhịp sau, không xếp hàng chờ trong tick
                # Chạy NỀN chứ không await ngay trong tick: một nhắc mode task có thể chạy tới
                # 1 giờ, await ở đây là mọi nhắc "notify" đến hạn sau nó (và cả loop, Kanban
                # trong cùng vòng scheduler) bị dời theo. Khoá `self.lock` bên trong _fire vẫn
                # giữ đúng một job engine một lúc.
                self._chay_nen(brain, rem)
            else:
                await self._fire(brain, rem)
            fired += 1

    def _khoa(self, mode) -> asyncio.Lock:
        """The lock a background reminder of this mode waits on (see `script_lock`)."""
        return self.script_lock if mode == "script" else self.lock

    def _chay_nen(self, brain: str, rem: dict) -> None:
        rid = rem.get("id")
        self._dang_chay.add(rid)

        async def _run():
            try:
                await self._fire(brain, rem)
            except Exception as e:
                print(f"[reminders] nhắc {rid} chạy nền lỗi: {type(e).__name__}: {e}", file=sys.stderr)
            finally:
                self._dang_chay.discard(rid)

        t = asyncio.get_running_loop().create_task(_run())
        self._viec_nen.add(t)
        t.add_done_callback(self._viec_nen.discard)

    async def cho_viec_nen(self) -> None:
        """Đợi các nhắc đang chạy nền xong (test và lúc tắt máy chủ)."""
        while self._viec_nen:
            await asyncio.gather(*list(self._viec_nen), return_exceptions=True)

    async def _fire(self, brain: str, rem: dict) -> None:
        mode = rem.get("mode", "notify")
        text = rem.get("text", "")
        head = rem.get("label") or text
        body, err = "", ""
        deliver, msg = True, ""
        # Which firing this is: a network retry keeps the slot of the run it repeats (`retry_of`).
        slot = rem.get("retry_of") or rem.get("due_at") or ""
        attempt = int(rem.get("retry_count") or 0)
        retry_at = 0.0           # > 0: this failed run is tried again at that time
        run_failed = False       # the run itself produced nothing usable (set per mode below)
        if mode == "task":
            previous = ""
            if rem.get("remember_last") and rem.get("result") and float(rem.get("fired_at") or 0) > 0:
                previous = (f"[{_fmt_vn(rem.get('fired_at'))}] "
                            + str(rem.get("result") or "")[:PREVIOUS_RESULT_CAP])
            late_s = _now() - float(rem.get("due_at") or _now())
            extra = {}
            if previous:
                extra["previous"] = previous
            if late_s >= LATE_NOTE_AFTER_S:
                extra["late_s"] = late_s
            job = ledger_job(str(rem.get("id") or ""), slot)
            async with self.lock:
                # Same once-only protection as a Kanban job (once_ledger.py): an outside action
                # (send, post, order) that went through in an earlier attempt of THIS firing is
                # not repeated by a retry, and one whose outcome is unknown is not repeated either.
                tok = turn_context.bind(turn_context.make(
                    "reminder", chat_id=str(rem.get("chat_id") or ""), job=job))
                try:
                    body, err = await self._run_task(brain, text, muc_quyen_cua(rem), **extra)
                finally:
                    turn_context.reset(tok)
            run_failed = not (body or "").strip()
            if err and run_failed:
                retry_at, why_not = self._retry_plan(rem, err, attempt, job)
                if why_not:
                    err = f"{why_not} | {err}"
            if body and _is_silent_task_result(body):
                # Same quiet rule as script jobs: a watcher that found nothing to do answers
                # "[SILENT] ..." and must not post to the channel. The result is still saved
                # on the reminder below so the run can be reviewed.
                deliver = False
            elif body:
                # `text`/`head` là prompt nội bộ để agent làm việc, có thể dài và chứa đường dẫn,
                # vai trò, quy trình. Telegram chỉ cần KẾT QUẢ cuối; ghép prompt vào đây vừa rối
                # vừa làm lộ chỉ dẫn máy như ca Coach Mục Tiêu & Kỷ Luật.
                msg = body.strip()
            elif err and retry_at:
                # The network will likely be back in a few minutes: say so once, on the first
                # failure, and stay quiet on the retries in between. The final outcome (an answer,
                # or the last error) is always posted.
                if attempt == 0:
                    luc = _fmt_vn(retry_at)[:5]
                    msg = (localefmt.chu("⚠ Nhắc hẹn chưa chạy được nhiệm vụ: ", "⚠ The reminder could not run its task: ")
                           + err[:300] + "\n\n"
                           + localefmt.chu(f"Có vẻ là lỗi mạng. Javis tự thử lại lúc {luc} "
                                           f"(lần 1/{len(RETRY_DELAYS_S)}), việc đã gửi đi rồi thì không gửi lại.",
                                           f"This looks like a network error. Javis will try again at {luc} "
                                           f"(attempt 1 of {len(RETRY_DELAYS_S)}); anything already sent is not sent again."))
                else:
                    deliver = False
            elif err:
                msg = localefmt.chu("⚠ Nhắc hẹn chưa chạy được nhiệm vụ: ", "⚠ The reminder could not run its task: ") + err[:300]
                if 0 < attempt <= len(RETRY_DELAYS_S):
                    msg += "\n\n" + localefmt.chu(f"Đã thử lại {attempt} lần vẫn lỗi.",
                                                  f"Still failing after {attempt} retries.")
                if self.deps.incident_hook:
                    try:
                        self.deps.incident_hook("reminder", str(rem.get("id") or ""), brain=brain,
                                                title=str(head or "")[:160], error=err, request=text[:1500])
                    except Exception:
                        pass
            else:
                msg = localefmt.chu("⚠ Nhắc hẹn đã chạy nhưng không trả về nội dung.", "⚠ The reminder ran but returned nothing.")
        elif mode == "script":
            async with self.script_lock:
                out, serr, code = await self._run_script(brain, rem.get("script", ""))
            body = out
            run_failed = code != 0
            if code != 0:
                err = (serr or out or "").strip()
                tail = err[-1500:]
                msg = localefmt.chu(f"⚠ Job script '{rem.get('script')}' lỗi (exit {code})",
                                    f"⚠ Script job '{rem.get('script')}' failed (exit {code})") + (":\n" + tail if tail else "")
            else:
                clean = (out or "").strip()
                if clean == "" or "[SILENT]" in out:
                    deliver = False       # stdout rỗng / cờ [SILENT] → im lặng (giống Hermes)
                else:
                    msg = clean[:SCRIPT_OUT_CAP]
        else:   # notify
            msg = localefmt.chu("⏰ Nhắc bạn: ", "⏰ Reminder: ") + text

        ok, send_err = True, ""
        voice_rel = ""
        if deliver and rem.get("speak") and msg and not msg.startswith("⚠") and self.deps.make_voice:
            # 0.202.0: "read it to me": the same text as a voice note, linked under the message (a player on the web)
            # and sent as an audio file where the channel needs the file itself (Telegram).
            try:
                voice_rel = await self.deps.make_voice(brain, text if mode == "notify" else msg) or ""
            except Exception as e:
                print(f"[reminders] voice note failed: {type(e).__name__}: {e}", file=sys.stderr)
            if voice_rel:
                msg = msg + f"\n\n[🔊 Tin thoại]({voice_rel})"
        if deliver:
            # Thẻ nhắc hẹn cho khung chat web (dashboard/chat-viec.js, 0.64.49): khung chat vẽ
            # dòng đầu có icon, nhãn và tên, nên bản web bỏ emoji và câu dẫn "Nhắc bạn:".
            loi = bool(err) or msg.startswith("⚠")
            viec = {"kind": "reminder", "status": "failed" if loi else "done",
                    "title": str(head or "")[:160], "id": str(rem.get("id") or "")}
            if rem.get("call") and not loi:
                # 0.203.0: the open dashboard rings with this message as an incoming call (dashboard/incoming-call.js).
                viec["call"] = "1"
            web = msg
            if mode == "notify":
                web = text + (f"\n\n[🔊 Tin thoại]({voice_rel})" if voice_rel else "")
            elif msg.startswith("⚠ "):
                web = msg[2:]
            try:
                # Telegram là kênh chữ thuần: mode "task" chạy chung system prompt/CLAUDE.md với
                # chat nên body có thể mang khối JAVIS_METRICS/JAVIS_ASK - lọc trước khi gửi, kẻo
                # lộ nguyên cụm "<!-- JAVIS_...: ... -->".
                kw = {}
                if _nhan_kw(self.deps.send_telegram, "viec"):
                    kw = {"viec": viec, "web": channel_context.strip_control_blocks(web)}
                if _nhan_kw(self.deps.send_telegram, "brain"):
                    # 0.186.0: the reminder's own brain (an empty chat_id lands in its Javis Core) and one key per
                    # firing, so a send repeated after a crash is filed once.
                    kw["brain"] = brain
                    # A network retry is a new message about the same firing: its own key, or the
                    # inbox would drop the answer as a duplicate of the error posted before it.
                    kw["dedup"] = f"rem:{rem.get('id', '')}:{slot}" + (f":r{attempt}" if attempt else "")
                ok, send_err = await self.deps.send_telegram(
                    rem.get("chat_id", ""), channel_context.strip_control_blocks(msg), **kw)
            except Exception as e:
                ok, send_err = False, f"{type(e).__name__}: {e}"
            if voice_rel and self.deps.send_file:
                try:
                    await self.deps.send_file(rem.get("chat_id", ""),
                                              str(Path(self.deps.brain_root(brain)) / voice_rel), brain)
                except Exception as e:
                    print(f"[reminders] voice note not sent: {type(e).__name__}: {e}", file=sys.stderr)

        # Cập nhật trạng thái: cron → lần kế · repeat_min → dời hạn · else done/failed.
        async with self._io:
            data = self._load(brain)
            cur = next((r for r in data.get("reminders", []) if r.get("id") == rem.get("id")), None)
            if cur is not None and cur.get("status") != "pending":
                # Người dùng đã HUỶ/tạm dừng nhắc này trong lúc nó đang chạy (mode task chạy
                # tới cả giờ): chỉ ghi kết quả, KHÔNG dựng lại lịch cron/repeat - bản trước ghi
                # đè status về "pending" nên nhắc đã huỷ sống lại.
                cur["fired_at"] = _now()
                cur["result"] = (body or "")[:2000]
                cur["error"] = (err or ("" if ok else send_err) or "")[:400]
                if cur.get("status") == "failed" and rem.get("retry_of") and ok and not run_failed:
                    cur["status"] = "done"   # a retry of the failed firing (Javis Core) worked
            elif cur is not None:
                cur["fired_at"] = _now()
                cur["result"] = (body or "")[:2000]
                cur["error"] = (err or ("" if ok else send_err) or "")[:400]
                cron = cur.get("cron")
                rep = int(cur.get("repeat_min") or 0)
                if retry_at:
                    # Network retry of THIS firing: stays pending, remembers which slot it repeats
                    # (same once-only ledger key) and how many retries it has used.
                    cur["retry_of"] = slot
                    cur["retry_count"] = attempt + 1
                    cur["due_at"] = float(retry_at)
                    cur["status"] = "pending"
                    self._save(brain, data)
                    return
                cur.pop("retry_of", None)
                cur.pop("retry_count", None)
                cur["last_slot"] = slot      # an incident retry reuses this firing's ledger key
                if cron:
                    try:
                        cur["due_at"] = cron_util.cron_next(cron, _now(), VN_TZ())
                        cur["status"] = "pending"
                    except Exception as ce:
                        cur["status"] = "failed"
                        cur["error"] = (cur.get("error", "") + f" | cron lỗi: {ce}")[:400]
                elif rep > 0:
                    step = rep * 60.0
                    # From the firing's own slot, not a retry's time, so retries do not shift the cycle.
                    nxt = float(slot or cur.get("due_at") or _now())
                    while nxt <= _now():
                        nxt += step
                    cur["due_at"] = nxt
                    cur["status"] = "pending"
                else:
                    # A run that produced no answer (engine error, nothing returned, script exit
                    # code) is "failed" even when the warning about it was delivered fine. Only the
                    # delivery used to count, so a dead run showed "done" (field report, code 26).
                    cur["status"] = "done" if ok and not run_failed else "failed"
            self._save(brain, data)

    def _next_regular(self, rem: dict, now: float) -> float:
        """Next regular firing of a repeating reminder after `now` (0 for a one-shot one)."""
        cron = rem.get("cron")
        if cron:
            try:
                return float(cron_util.cron_next(cron, now, VN_TZ()))
            except Exception:
                return 0.0
        rep = int(rem.get("repeat_min") or 0)
        if rep > 0:
            step = rep * 60.0
            nxt = float(rem.get("retry_of") or rem.get("due_at") or now)
            while nxt <= now:
                nxt += step
            return nxt
        return 0.0

    def _retry_plan(self, rem: dict, err: str, attempt: int, job: str) -> tuple:
        """(retry_at, note) for a task run that failed with `err` and no answer.

        retry_at > 0 schedules the next attempt of the same firing. No retry when the error is not
        a network one, the retries are used up, the next regular firing comes first anyway, or an
        outside action of this firing has an unknown outcome (the ledger could not tell whether it
        went through; nobody is there to ask, so the owner checks). `note` explains that last case.
        """
        if rem.get("mode") != "task" or attempt >= len(RETRY_DELAYS_S) or not is_transient_error(err):
            return 0.0, ""
        try:
            unsure = once_ledger.unknowns(job)
        except Exception as e:
            print(f"[reminders] once ledger unreadable: {type(e).__name__}: {e}", file=sys.stderr)
            unsure = []
        if unsure:
            what = "; ".join(str(u.get("target") or u.get("tool") or "") for u in unsure)[:300]
            return 0.0, localefmt.chu(
                f"Không tự thử lại vì một thao tác ra ngoài có thể đã chạy ({what}). Kiểm tra rồi chạy lại bằng tay",
                f"Not retried automatically: an outside action may already have gone through ({what}). "
                "Check it, then run it again by hand")
        now = _now()
        at = now + RETRY_DELAYS_S[attempt]
        nxt = self._next_regular(rem, now)
        if nxt and nxt <= at + 60:
            return 0.0, ""       # the next scheduled run is about as soon: let it do the work
        return at, ""

    async def _run_script(self, brain: str, script: str):
        """Job không-LLM: chạy script CÓ SẴN trong Javis/scripts, trả (stdout, stderr, exit_code).
        exit_code=-1 nếu không chạy được (thiếu trình chạy / timeout / lỗi khởi tạo)."""
        try:
            rp = self._resolve_script(brain, script)
        except ValueError as e:
            return "", str(e), -1
        runner = list(_SCRIPT_RUNNERS.get(rp.suffix.lower(), []))
        if runner:
            exe = shutil.which(runner[0]) or runner[0]
            if not (shutil.which(runner[0]) or Path(runner[0]).exists()):
                return "", localefmt.chu(f"thiếu trình chạy '{runner[0]}' cho {rp.suffix}",
                                         f"missing runner '{runner[0]}' for {rp.suffix}"), -1
            argv = [exe] + runner[1:] + [str(rp)]
        else:
            argv = [str(rp)]   # file thực thi có shebang (đã kiểm tra os.X_OK lúc tạo)
        env = dict(os.environ)
        env["JAVIS_BRAIN_ROOT"] = str(self.deps.brain_root(brain))
        try:
            proc = await asyncio.create_subprocess_exec(
                *argv, cwd=self.deps.brain_root(brain), env=env,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
                **winproc.kwargs_no_window())
        except Exception as e:
            return "", localefmt.chu(f"không chạy được script: {type(e).__name__}: {e}",
                                     f"could not run the script: {type(e).__name__}: {e}"), -1
        try:
            out_b, err_b = await asyncio.wait_for(proc.communicate(), timeout=SCRIPT_TIMEOUT_S)
        except asyncio.TimeoutError:
            try:
                proc.kill()
            except Exception:
                pass
            return "", localefmt.chu(f"script quá {SCRIPT_TIMEOUT_S}s → đã kill",
                                     f"script exceeded {SCRIPT_TIMEOUT_S}s → killed"), -1
        out = (out_b or b"").decode("utf-8", "replace")
        err = (err_b or b"").decode("utf-8", "replace")
        return out, err, (proc.returncode if proc.returncode is not None else -1)

    async def _run_task(self, brain: str, text: str, muc_quyen: str = "", previous: str = "",
                        late_s: float = 0.0, intro: str = ""):
        """mode 'task': tới giờ chạy engine làm việc user đã hẹn. Trả (kết_quả, lỗi).

        Mức quyền quyết định nó được chạm tới đâu, khớp với ba mức của loop:
          suggest - chỉ đọc (MCP đọc + đọc file), không ghi gì
          auto    - thêm quyền ghi file trong vault, hub vẫn chặn nhóm tool nguy hiểm
          full    - toàn quyền: mọi tool, mọi MCP đã đấu, gồm cả nhóm hành động ra ngoài
        """
        mq = str(muc_quyen or "").strip().lower()
        if mq not in VALID_MUC_QUYEN:
            mq = MUC_QUYEN_MAC_DINH
        try:
            sysprompt = self.deps.build_system_prompt(brain)
        except Exception:
            sysprompt = ""
        if mq == "full":
            # TOÀN QUYỀN: không allowlist → mọi tool + mọi MCP đã đấu (mirror nhánh full của
            # loop). Đây là mức DUY NHẤT làm được việc user hẹn kiểu "tới giờ thì gửi/đăng/đặt":
            # nhóm tool hành động ra ngoài bị hub xếp loại nguy hiểm nên hai mức dưới không
            # những gọi không được mà còn KHÔNG NHÌN THẤY nó.
            cli = claude_engine(system_prompt=sysprompt, cwd=self.deps.brain_root(brain),
                                tag="reminder", allowed_tools=None)
            if self.deps.apply_mcp:
                try:
                    # brain BẮT BUỘC ở nhánh ungated: plugin in-process nạp ở đây và cần biết
                    # vault nào, thiếu thì nó rơi về brain mặc định.
                    self.deps.apply_mcp(cli, mode="full", brain=brain)
                except TypeError:
                    self.deps.apply_mcp(cli)
        else:
            # allowlist = file tools + pattern MCP. Bash/Web/Task KHÔNG có trong list → tự bị
            # chặn (mirror nhánh suggest/auto của loop).
            base = self.deps.safe_tools if mq == "auto" else self.deps.readonly_tools
            tools = list(base)
            if self.deps.mcp_allow_patterns:
                try:
                    tools += list(self.deps.mcp_allow_patterns() or [])
                except Exception:
                    pass
            cli = claude_engine(system_prompt=sysprompt, cwd=self.deps.brain_root(brain),
                                tag="reminder", allowed_tools=tools)
            if self.deps.apply_mcp:
                try:
                    self.deps.apply_mcp(cli, mode=mq, brain=brain)   # hub ENFORCE theo mức
                except TypeError:
                    self.deps.apply_mcp(cli)
            else:
                mcpf = _empty_mcp_file()
                if mcpf:
                    cli.mcp_config = mcpf
                    cli.mcp_strict = True
        cli = aux_engine.apply(self.deps, cli, mode=mq, tag="reminder")
        # Trần chung cho fork nền (mặc định 1 giờ, env JAVIS_BG_MAX_WALL_S). Số cứng 300s cũ
        # từng giết việc lịch thật đang chạy dở - xem doc tại aux_engine.bg_max_wall_s.
        cli.max_wall_s = aux_engine.bg_max_wall_s()
        if not cli.is_available():
            return "", localefmt.chu("Claude CLI chưa cài", "Claude CLI is not installed")
        rang_buoc = {
            "suggest": ("Mức quyền của nhắc hẹn này là CHỈ ĐỌC: được đọc dữ liệu thật qua MCP "
                        "và đọc file, KHÔNG ghi file, KHÔNG hành động ra ngoài. Việc nào cần "
                        "hành động thì mô tả lại cho user tự làm."),
            "auto": ("Mức quyền của nhắc hẹn này là ĐƯỢC GHI FILE: đọc dữ liệu thật qua MCP và "
                     "ghi file nháp trong vault, nhưng KHÔNG tạo đơn / tiêu tiền / chạy quảng "
                     "cáo / đăng bài / gửi tin ra ngoài."),
            # Không kể lể "hãy cẩn thận": user đã được cảnh báo lúc tạo và đã chọn mức này. Nói
            # đúng một điều model cần biết mà nó không tự suy ra được: việc này chạy KHÔNG có
            # ai ngồi cạnh, nên hỏi lại là hỏi vào hư không.
            "full": ("Mức quyền của nhắc hẹn này là TOÀN QUYỀN: user đã chủ động cấp, nên cứ "
                     "làm đúng việc được giao bằng các công cụ đã đấu, gồm cả hành động ra "
                     "ngoài. Không có ai ngồi cạnh để duyệt hay trả lời câu hỏi ở bước này: "
                     "làm được thì làm rồi thuật lại đã làm gì, không làm được thì nói thẳng "
                     "là chưa làm và vì sao, tuyệt đối đừng hỏi lại rồi ngồi đợi."),
        }[mq]
        # `intro` (0.198.0): another caller of this runner, such as a webhook, says what woke it.
        prompt = (
            (intro or "NHIỆM VỤ NHẮC HẸN - tới giờ user đã đặt trước.")
            + " Làm việc dưới đây rồi VIẾT câu trả lời "
            "NGẮN GỌN như tin nhắn Telegram gửi cho user (tiếng Việt, không bảng, không gạch ngang dài). "
            + rang_buoc + "\n\n"
            "Việc cần làm:\n" + text
            + task_context_note(previous, late_s)
        )
        out, err = "", ""
        try:
            async for ev in cli.query(prompt):
                if ev["type"] == "final":
                    out = ev.get("content", "") or out
                elif ev["type"] == "error":
                    err = ev.get("content", "") or err
        except Exception as e:
            err = f"{type(e).__name__}: {e}"
        return out, err

    # ── router ──
    def _make_router(self) -> APIRouter:
        router = APIRouter()

        @router.get("/reminders")
        async def reminders_list(brain: str = Query("brain")):
            rems = sorted(self._load(brain).get("reminders", []),
                          key=lambda r: float(r.get("due_at", 0)))
            pending = [self._view(r) for r in rems if r.get("status") == "pending"]
            history = [self._view(r) for r in rems if r.get("status") != "pending"][-30:]
            ready, why = self.notify_status()
            return {"pending": pending, "history": history,
                    "counts": {"pending": len(pending)},
                    "notify": {"ok": ready, "error": why}}

        @router.post("/reminders")
        async def reminders_add(payload: dict = Body(None)):
            """Tạo nhắc hẹn / job. Agent gọi bằng curl JSON từ localhost (miễn đăng nhập qua
            _AUTH_LOCAL_EXACT). Body: {"text", (một trong) "delay_min"|"at"|"due_at"|"cron",
            ["chat_id","mode"(notify|task|script),"script","repeat_min","label","brain"]}."""
            p = payload or {}
            brain = str(p.get("brain") or "brain")
            # Body thiếu 'brain' → rơi Brain Default. Sau khi recipe curl (channel_context) và tool
            # javis_schedule đều gắn brain, thiếu brain là BẤT THƯỜNG (model quên) → log để soi chứ
            # KHÔNG chặn (giữ tương thích caller cũ/thủ công cố ý dùng default). Đây từng là bug câm
            # "chat brain khác nhưng nhắc hẹn vẫn vào default".
            if not str(p.get("brain") or "").strip():
                print(f"[reminders] POST thiếu 'brain' → Brain Default (created_by="
                      f"{p.get('created_by') or 'user'}, text={str(p.get('text'))[:40]!r})", file=sys.stderr)
            try:
                async with self._io:
                    rem = self._create(
                        brain, p.get("text"),
                        delay_min=p.get("delay_min"), at=p.get("at"), due_at=p.get("due_at"),
                        cron=p.get("cron"), script=p.get("script", ""),
                        chat_id=p.get("chat_id", ""), mode=p.get("mode", "notify"),
                        repeat_min=p.get("repeat_min", 0), label=p.get("label", ""),
                        created_by=str(p.get("created_by") or "user"),
                        allow_no_channel=bool(p.get("allow_no_channel") or False),
                        muc_quyen=p.get("muc_quyen"),
                        remember_last=_truthy(p.get("remember_last")),
                        speak=_truthy(p.get("speak")),
                        call=_truthy(p.get("call")),
                    )
            except NotifyNotReady as e:
                # can_force: chỗ gọi (dashboard/chat) hỏi lại người dùng rồi tạo tiếp với
                # allow_no_channel=true. KHÔNG tự bỏ qua hộ - thiếu kênh là điều người dùng cần biết.
                return {"ok": False, "error": str(e), "need": "telegram", "can_force": True}
            except ValueError as e:
                return {"ok": False, "error": str(e)}
            except Exception as e:
                return {"ok": False, "error": f"{type(e).__name__}: {e}"}
            return {"ok": True, "id": rem["id"], "mode": rem["mode"],
                    "due_at": rem["due_at"], "due_human": _fmt_vn(rem["due_at"]),
                    "cron": rem["cron"], "repeat_min": rem["repeat_min"],
                    "muc_quyen": rem.get("muc_quyen"),
                    "remember_last": rem.get("remember_last", False),
                    "speak": rem.get("speak", False),
                    "call": rem.get("call", False),
                    "next_runs": next_runs(rem["cron"]) if rem["cron"] else [],
                    # Kèm lời đọc để chỗ gọi (chat) nhắc lại lịch bằng tiếng Việt, khỏi bắt user
                    # tự dịch "0 7 * * *".
                    "cron_human": cron_util.describe_cron(rem["cron"]) if rem["cron"] else ""}

        @router.get("/reminders/templates")
        async def reminders_templates():
            """Ready-made reminders the recurring-work page can pre-fill (never created here)."""
            return {"templates": [morning_brief_template()]}

        @router.get("/reminders/scripts")
        async def reminders_scripts(brain: str = Query("brain")):
            """Liệt kê script chạy được (job không-LLM) đặt trong <brain>/Javis/scripts.
            Tự tạo thư mục nếu chưa có để user biết chỗ bỏ file vào."""
            d = self._scripts_dir(brain)
            try:
                d.mkdir(parents=True, exist_ok=True)
            except Exception:
                pass
            out = []
            try:
                for f in sorted(d.iterdir()):
                    if f.is_file() and (f.suffix.lower() in _SCRIPT_RUNNERS or os.access(f, os.X_OK)):
                        out.append({"name": f.name, "size": f.stat().st_size,
                                    "runner": f.suffix.lower().lstrip(".") or "exec"})
            except Exception:
                pass
            return {"dir": str(d), "scripts": out}

        @router.post("/reminders/cancel")
        async def reminders_cancel(id: str = Form(...), brain: str = Form("brain")):
            async with self._io:
                hit = self.cancel(brain, id)
            return {"ok": hit, "error": ("" if hit else "not found")}

        @router.post("/reminders/update")
        async def reminders_update(id: str = Form(...), brain: str = Form("brain"),
                                   text: str = Form(None), label: str = Form(None),
                                   mode: str = Form(None), chat_id: str = Form(None),
                                   cron: str = Form(None), at: str = Form(None),
                                   delay_min: str = Form(None), due_at: str = Form(None),
                                   muc_quyen: str = Form(None), remember_last: str = Form(None),
                                   speak: str = Form(None), call: str = Form(None)):
            """Sửa nhắc/lịch đang chờ (trang Việc định kỳ: nút Sửa). Bỏ trống trường nào thì giữ
            nguyên trường đó; truyền cron HOẶC at/delay_min/due_at để đổi thời điểm."""
            async with self._io:
                return self.update(brain, id, text=text, label=label, mode=mode, chat_id=chat_id,
                                   cron=cron, at=at, delay_min=delay_min, due_at=due_at,
                                   muc_quyen=muc_quyen, remember_last=remember_last, speak=speak, call=call)

        @router.post("/reminders/delete")
        async def reminders_delete(id: str = Form(...), brain: str = Form("brain")):
            """Xoá HẲN một mục (khác /reminders/cancel: cancel giữ lại trong lịch sử)."""
            async with self._io:
                hit = self.delete(brain, id)
            return {"ok": hit, "error": ("" if hit else "not found")}

        @router.post("/reminders/move")
        async def reminders_move(id: str = Form(...), from_brain: str = Form(...),
                                 to_brain: str = Form(...)):
            async with self._io:
                return self.move(from_brain, to_brain, id)

        @router.post("/reminders/clear")
        async def reminders_clear(brain: str = Form("brain")):
            """Dọn lịch sử (giữ lại các nhắc đang chờ)."""
            async with self._io:
                data = self._load(brain)
                data["reminders"] = [r for r in data.get("reminders", [])
                                     if r.get("status") == "pending"]
                self._save(brain, data)
            return {"ok": True}

        return router


def _truthy(v) -> bool:
    """Form fields arrive as strings ("true", "1", "on"); JSON as booleans."""
    if isinstance(v, bool):
        return v
    return str(v or "").strip().lower() in ("1", "true", "yes", "on")


def next_runs(cron: str, count: int = NEXT_RUNS_SHOWN, after: Optional[float] = None) -> list:
    """The next `count` firings of a cron schedule as [{"at", "human"}], so a person confirms a
    schedule by its dates instead of decoding "0 9 1 * *". Empty on a bad expression."""
    out = []
    t = _now() if after is None else float(after)
    try:
        for _ in range(max(0, int(count))):
            t = cron_util.cron_next(cron, t, VN_TZ())
            out.append({"at": t, "human": _fmt_vn(t)})
    except Exception:
        return []
    return out


def task_context_note(previous: str, late_s: float) -> str:
    """Extra context appended to a task-mode prompt: the previous run's report (when the reminder
    remembers it) and a line saying this run fired late. Prompt text, so Vietnamese (see
    docs/dev/them-mot-ngon-ngu.md)."""
    parts = []
    if late_s >= LATE_NOTE_AFTER_S:
        mins = int(late_s // 60)
        parts.append(f"Lưu ý: lần chạy này TRỄ khoảng {mins} phút so với giờ hẹn (máy chủ tắt hoặc "
                     "đang bận). Nếu việc phụ thuộc giờ giấc thì tính theo thời điểm hiện tại.")
    if previous:
        parts.append("Kết quả LẦN CHẠY TRƯỚC của chính việc này (để biết đã báo gì, chỉ báo cái "
                     "mới hoặc cái thay đổi, đừng lặp lại y nguyên):\n<<<\n"
                     + previous.replace(">>>", "> > >") + "\n>>>")
    return ("\n\n" + "\n\n".join(parts)) if parts else ""


def register(app, deps: RemindersDeps) -> RemindersFeature:
    feat = RemindersFeature(deps)
    app.include_router(feat.router)
    return feat
