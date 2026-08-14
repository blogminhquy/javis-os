"""
reminders.py - Nhắc hẹn từ chat cho Javis: "30 phút nữa nhắc anh...", "8h30 sáng mai...".

Vá đúng lỗ hổng người dùng nêu: Javis GỬI được Telegram ngay lúc chat, nhưng CHƯA tự
hẹn giờ để thức dậy gửi SAU. Module này thêm hàng đợi nhắc hẹn BỀN (JSON trong vault,
git-backed) + để scheduler nền (main._scheduler_loop, tick 30s) đánh thức đúng giờ:
  - mode "notify" (mặc định): tới giờ bắn thẳng tin nhắc qua Telegram cho ĐÚNG người đã đặt.
  - mode "task"            : tới giờ chạy engine làm việc đã hẹn rồi gửi kết quả về Telegram.
                             Quyền theo `muc_quyen` (suggest | auto | full, mặc định full).
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
hơn lúc chat là tự mâu thuẫn. Đổi lại, lúc tạo thì trả kèm `canh_bao` và chỗ gọi phải đọc lại
cho người dùng. Xem `CANH_BAO_TOAN_QUYEN` và `MUC_QUYEN_MAC_DINH`.

Module KHÔNG import main (tránh vòng lặp import): mọi helper tiêm qua RemindersDeps.
"""
from __future__ import annotations

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
from claude_cli import claude_engine, _empty_mcp_file
import aux_engine   # engine viec nen theo model phu nguoi dung chon

VN_TZ = timezone(timedelta(hours=7))
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
# Trước bản này mức quyền bị ghim cứng ở chỉ-đọc, nên MỌI nhắc hẹn yêu cầu một hành động ra
# ngoài (gửi tin, đăng bài, đặt lịch, tạo đơn) đều thức dậy đúng giờ, chạy, rồi báo về là không
# làm được - trong khi việc thì vẫn chưa ai làm. Nay mở quyền và ĐỔI LẠI BẰNG MỘT LỜI CẢNH BÁO
# rõ ràng lúc tạo; ai muốn mức cũ thì đặt muc_quyen="suggest" cho nhắc hẹn đó.
MUC_QUYEN_MAC_DINH = "full"

# Cảnh báo hiện lúc tạo một nhắc hẹn có thể tự hành động. Viết TRUNG TÍNH, không gắn với một ca
# dùng cụ thể nào: mỗi người đấu một bộ công cụ khác nhau, nên chỉ nói đúng ba điều mà ai cũng
# cần biết - nó chạy một mình, nó có quyền gì, và cái gì không rút lại được.
CANH_BAO_TOAN_QUYEN = (
    "⚠ Nhắc hẹn kiểu giao việc chạy MỘT MÌNH khi tới giờ, với đầy đủ quyền như lúc bạn đang "
    "ngồi chat: nó dùng được mọi công cụ đã đấu, nên tuỳ việc bạn giao mà nó có thể gửi tin, "
    "đăng bài, đặt lịch, tạo đơn hoặc tiêu tiền thật. Ở bước đó không có ai duyệt lại, và phần "
    "lớn những việc đó không rút lại được. Chỉ giao thứ bạn sẵn sàng để nó tự làm. Muốn nó chỉ "
    "đọc rồi báo lại thì đặt mức quyền \"chỉ đọc\" cho nhắc hẹn này."
)

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


class NotifyNotReady(ValueError):
    """Chưa có đường gửi kết quả (bot Telegram chưa bật / chưa có Chat ID).

    Tách riêng khỏi ValueError thường để endpoint trả thêm cờ can_force: đây KHÔNG phải lỗi cú
    pháp mà là THIẾU ĐIỀU KIỆN, và người dùng có quyền chọn tạo tiếp (kết quả chỉ lưu trong Javis).
    """

    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(
            f"Chưa gửi được kết quả về đâu: {reason}. Vào trang Kênh đấu bot Telegram "
            "(dán bot token + Chat ID) rồi tạo lại. Nếu vẫn muốn tạo, đặt allow_no_channel=true - "
            "việc sẽ chạy nhưng không ai được báo."
        )


def _now() -> float:
    return time.time()


def _vnow() -> datetime:
    return datetime.now(VN_TZ)


def _fmt_vn(ts) -> str:
    try:
        return datetime.fromtimestamp(float(ts), VN_TZ).strftime("%H:%M %d/%m/%Y")
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
            return datetime.strptime(s, fmt).replace(tzinfo=VN_TZ)
        except ValueError:
            continue
    try:
        dt = datetime.fromisoformat(s)
        return dt.replace(tzinfo=VN_TZ) if dt.tzinfo is None else dt
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
            raise ValueError("delay không được âm")
        return now + max(d, MIN_LEAD_S)
    # 2) due_at tuyệt đối: epoch hoặc ISO
    if due_at not in (None, ""):
        s = str(due_at).strip()
        if re.fullmatch(r"\d{9,}(\.\d+)?", s):        # epoch giây (>= ~2001)
            return float(s)
        dt = _parse_iso_vn(s)
        if dt:
            return dt.timestamp()
        raise ValueError(f"due_at không hiểu: {due_at}")
    # 3) at: giờ trong ngày (HH:MM) hoặc ngày-giờ cụ thể
    if at not in (None, ""):
        s = str(at).strip().lower().replace("g", "h")   # "8g30" (kiểu VN) → "8h30"
        m = _AT_DATE.match(s)
        if m:
            y, mo, da, hh, mm = (int(x) for x in m.groups())
            try:
                return datetime(y, mo, da, hh, mm, tzinfo=VN_TZ).timestamp()
            except ValueError as e:
                raise ValueError(f"ngày giờ sai: {at}") from e
        hh = mm = None
        m = _AT_HHMM.match(s)
        if m:
            hh, mm = int(m.group(1)), int(m.group(2))
        else:
            m = _AT_HH.match(s)
            if m:
                hh, mm = int(m.group(1)), 0
        if hh is None or not (0 <= hh <= 23 and 0 <= mm <= 59):
            raise ValueError(f"at không hiểu (dùng HH:MM hoặc YYYY-MM-DD HH:MM): {at}")
        cand = _vnow().replace(hour=hh, minute=mm, second=0, microsecond=0)
        if cand.timestamp() <= now + MIN_LEAD_S:      # giờ đã qua trong hôm nay → sang mai
            cand = cand + timedelta(days=1)
        return cand.timestamp()
    raise ValueError("Thiếu thời điểm: cần delay_min HOẶC at HOẶC due_at")


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


class RemindersFeature:
    def __init__(self, deps: RemindersDeps):
        self.deps = deps
        self.lock = asyncio.Lock()   # serialize: 1 nhắc mode 'task' chạy engine/lần
        self._io = asyncio.Lock()    # serialize ghi file reminders.json
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
            raise ValueError("mode 'script' cần tên file trong Javis/scripts")
        if "/" in name or name.startswith("."):
            raise ValueError("script chỉ nhận TÊN FILE trong Javis/scripts (không đường dẫn)")
        base = self._scripts_dir(brain)
        p = base / name
        try:
            rp, rbase = p.resolve(), base.resolve()
        except Exception:
            raise ValueError("đường dẫn script không hợp lệ")
        if rp.parent != rbase or not rp.is_file():
            raise ValueError(f"không thấy script '{name}' trong Javis/scripts")
        if rp.suffix.lower() not in _SCRIPT_RUNNERS and not os.access(rp, os.X_OK):
            raise ValueError(f"đuôi '{rp.suffix}' chưa hỗ trợ (dùng .py/.sh/.ps1/.js/.bat)")
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
                created_by="user", allow_no_channel=False, muc_quyen=None) -> dict:
        mode = mode if mode in VALID_MODE else "notify"
        mq = str(muc_quyen or "").strip().lower()
        mq = mq if mq in VALID_MUC_QUYEN else MUC_QUYEN_MAC_DINH
        # ĐỦ ĐIỀU KIỆN MỚI TẠO. notify/task tồn tại chỉ để BÁO cho người - chưa đấu Telegram thì
        # tới giờ nó chạy xong rồi ném kết quả vào hư không, người dùng tưởng Javis quên việc.
        # Thà chặn ngay lúc tạo và nói thiếu gì. (script = job giám sát, im lặng là bình thường.)
        if mode in ("notify", "task") and not allow_no_channel:
            ready, why = self.notify_status()
            if not ready:
                raise NotifyNotReady(why or "chưa có kênh gửi")
        text = (text or "").strip()
        script_name = ""
        if mode == "script":
            rp = self._resolve_script(brain, script)   # xác thực ngay lúc tạo (fail fast)
            script_name = rp.name
            if not text:
                text = f"chạy script {script_name}"
        elif not text:
            raise ValueError("Thiếu nội dung nhắc (text)")
        cron_expr = (str(cron).strip() if cron not in (None, "") else "")
        if cron_expr:
            cron_expr = cron_util.validate_cron(cron_expr)     # chuẩn hoá + bắt lỗi
            due = cron_util.cron_next(cron_expr, _now(), VN_TZ)
            rep = 0                                            # cron thay cho repeat_min
        else:
            due = resolve_due(delay_min=delay_min, at=at, due_at=due_at)
            if due > _now() + MAX_DELAY_DAYS * 86400:
                raise ValueError("Hẹn quá xa (giới hạn ~1 năm)")
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
                "result": (r.get("result") or "")[:500], "error": r.get("error", "")}

    def update(self, brain: str, rid: str, *, text=None, label=None, mode=None, chat_id=None,
               cron=None, at=None, delay_min=None, due_at=None, muc_quyen=None) -> dict:
        """Sửa 1 nhắc/lịch ĐANG CHỜ: nội dung, tên, kiểu, và thời điểm. Trả {"ok", "error",
        "reminder"}. Chỉ nhận tham số được truyền (None = giữ nguyên) nên gọi sửa một phần
        được. Đổi lịch thì tính lại due_at ngay để người dùng thấy lần chạy kế tiếp mới."""
        data = self._load(brain)
        cur = next((r for r in data.get("reminders", []) if r.get("id") == rid), None)
        if cur is None:
            return {"ok": False, "error": "không thấy nhắc hẹn này"}
        if cur.get("status") != "pending":
            return {"ok": False, "error": "chỉ sửa được nhắc đang chờ (mục đã xong/đã huỷ thì tạo mới)"}
        if text not in (None, ""):
            cur["text"] = str(text)[:2000]
        if label is not None:
            cur["label"] = str(label)[:120]
        if mode not in (None, ""):
            m = str(mode).strip().lower()
            if m not in VALID_MODE:
                return {"ok": False, "error": f"kiểu không hợp lệ: {mode}"}
            if cur.get("mode") == "script":
                pass   # job script GIỮ NGUYÊN kiểu (đổi là mất tên file script) - vẫn sửa được
                       # tên/nội dung/lịch, nên bỏ qua trường mode thay vì chặn cả lệnh sửa
            elif m == "script":
                return {"ok": False, "error": "đổi sang job script thì tạo mới (cần chọn file script)"}
            else:
                cur["mode"] = m
        if chat_id is not None:
            cur["chat_id"] = str(chat_id)
        if muc_quyen not in (None, ""):
            mq = str(muc_quyen).strip().lower()
            if mq not in VALID_MUC_QUYEN:
                return {"ok": False, "error": f"mức quyền không hợp lệ: {muc_quyen}"}
            cur["muc_quyen"] = mq
        has_when = any(v not in (None, "") for v in (cron, at, delay_min, due_at))
        if has_when:
            try:
                if cron not in (None, ""):
                    expr = cron_util.validate_cron(str(cron))
                    cur["cron"] = expr
                    cur["repeat_min"] = 0
                    cur["due_at"] = cron_util.cron_next(expr, _now(), VN_TZ)
                else:
                    due = resolve_due(delay_min=delay_min, at=at, due_at=due_at)
                    if due > _now() + MAX_DELAY_DAYS * 86400:
                        return {"ok": False, "error": "Hẹn quá xa (giới hạn ~1 năm)"}
                    cur["cron"] = ""          # chuyển lịch lặp → một lần: bỏ cron kẻo nó tự hồi sinh
                    cur["due_at"] = float(due)
            except ValueError as e:
                return {"ok": False, "error": str(e)}
        cur["error"] = ""                      # đã sửa thì lỗi lần chạy trước không còn đúng nữa
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
            return {"ok": False, "error": "brain không hợp lệ"}
        if src_root == dst_root:
            return {"ok": False, "error": "brain nguồn và đích trùng nhau"}
        src = self._load(from_brain)
        rec = next((r for r in src.get("reminders", []) if r.get("id") == rid), None)
        if rec is None:
            return {"ok": False, "error": "không thấy nhắc hẹn ở brain nguồn"}
        dst = self._load(to_brain)
        dst.setdefault("reminders", []).append(rec)
        self._save(to_brain, dst)
        src["reminders"] = [r for r in src.get("reminders", []) if r.get("id") != rid]
        self._save(from_brain, src)
        return {"ok": True}

    # ── scheduler gọi mỗi nhịp ──
    async def tick(self) -> None:
        try:
            brains = self.deps.scheduler_brains() or ["brain"]
        except Exception:
            brains = ["brain"]
        for brain in brains:
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
            if rem.get("mode") in ("task", "script") and self.lock.locked():
                continue   # đang có 1 job chạy → để nhịp sau, không xếp hàng chờ trong tick
            await self._fire(brain, rem)
            fired += 1

    async def _fire(self, brain: str, rem: dict) -> None:
        mode = rem.get("mode", "notify")
        text = rem.get("text", "")
        head = rem.get("label") or text
        body, err = "", ""
        deliver, msg = True, ""
        if mode == "task":
            async with self.lock:
                body, err = await self._run_task(brain, text, muc_quyen_cua(rem))
            if body:
                # `text`/`head` là prompt nội bộ để agent làm việc, có thể dài và chứa đường dẫn,
                # vai trò, quy trình. Telegram chỉ cần KẾT QUẢ cuối; ghép prompt vào đây vừa rối
                # vừa làm lộ chỉ dẫn máy như ca Coach Mục Tiêu & Kỷ Luật.
                msg = body.strip()
            elif err:
                msg = "⚠ Nhắc hẹn chưa chạy được nhiệm vụ: " + err[:300]
            else:
                msg = "⚠ Nhắc hẹn đã chạy nhưng không trả về nội dung."
        elif mode == "script":
            async with self.lock:
                out, serr, code = await self._run_script(brain, rem.get("script", ""))
            body = out
            if code != 0:
                err = (serr or out or "").strip()
                tail = err[-1500:]
                msg = f"⚠ Job script '{rem.get('script')}' lỗi (exit {code})" + (":\n" + tail if tail else "")
            else:
                clean = (out or "").strip()
                if clean == "" or "[SILENT]" in out:
                    deliver = False       # stdout rỗng / cờ [SILENT] → im lặng (giống Hermes)
                else:
                    msg = clean[:SCRIPT_OUT_CAP]
        else:   # notify
            msg = "⏰ Nhắc anh: " + text

        ok, send_err = True, ""
        if deliver:
            try:
                # Telegram là kênh chữ thuần: mode "task" chạy chung system prompt/CLAUDE.md với
                # chat nên body có thể mang khối JAVIS_METRICS/JAVIS_ASK - lọc trước khi gửi, kẻo
                # lộ nguyên cụm "<!-- JAVIS_...: ... -->".
                ok, send_err = await self.deps.send_telegram(
                    rem.get("chat_id", ""), channel_context.strip_control_blocks(msg))
            except Exception as e:
                ok, send_err = False, f"{type(e).__name__}: {e}"

        # Cập nhật trạng thái: cron → lần kế · repeat_min → dời hạn · else done/failed.
        async with self._io:
            data = self._load(brain)
            cur = next((r for r in data.get("reminders", []) if r.get("id") == rem.get("id")), None)
            if cur is not None:
                cur["fired_at"] = _now()
                cur["result"] = (body or "")[:2000]
                cur["error"] = (err or ("" if ok else send_err) or "")[:400]
                cron = cur.get("cron")
                rep = int(cur.get("repeat_min") or 0)
                if cron:
                    try:
                        cur["due_at"] = cron_util.cron_next(cron, _now(), VN_TZ)
                        cur["status"] = "pending"
                    except Exception as ce:
                        cur["status"] = "failed"
                        cur["error"] = (cur.get("error", "") + f" | cron lỗi: {ce}")[:400]
                elif rep > 0:
                    step = rep * 60.0
                    nxt = float(cur.get("due_at", _now()))
                    while nxt <= _now():
                        nxt += step
                    cur["due_at"] = nxt
                    cur["status"] = "pending"
                else:
                    cur["status"] = "done" if ok else "failed"
            self._save(brain, data)

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
                return "", f"thiếu trình chạy '{runner[0]}' cho {rp.suffix}", -1
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
            return "", f"không chạy được script: {type(e).__name__}: {e}", -1
        try:
            out_b, err_b = await asyncio.wait_for(proc.communicate(), timeout=SCRIPT_TIMEOUT_S)
        except asyncio.TimeoutError:
            try:
                proc.kill()
            except Exception:
                pass
            return "", f"script quá {SCRIPT_TIMEOUT_S}s → đã kill", -1
        out = (out_b or b"").decode("utf-8", "replace")
        err = (err_b or b"").decode("utf-8", "replace")
        return out, err, (proc.returncode if proc.returncode is not None else -1)

    async def _run_task(self, brain: str, text: str, muc_quyen: str = ""):
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
        cli.max_wall_s = 300
        if not cli.is_available():
            return "", "Claude CLI chưa cài"
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
        prompt = (
            "NHIỆM VỤ NHẮC HẸN - tới giờ user đã đặt trước. Làm việc dưới đây rồi VIẾT câu trả lời "
            "NGẮN GỌN như tin nhắn Telegram gửi cho user (tiếng Việt, không bảng, không gạch ngang dài). "
            + rang_buoc + "\n\n"
            "Việc cần làm:\n" + text
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
                    # Cảnh báo đi CÙNG kết quả tạo, không nằm đâu đó trong tài liệu: đây là lúc
                    # duy nhất người dùng chắc chắn đang nhìn. Chỗ gọi (chat/dashboard) có nhiệm
                    # vụ đọc lại nguyên văn cho họ.
                    "canh_bao": (CANH_BAO_TOAN_QUYEN
                                 if (rem["mode"] == "task" and rem.get("muc_quyen") == "full")
                                 else ""),
                    # Kèm lời đọc để chỗ gọi (chat) nhắc lại lịch bằng tiếng Việt, khỏi bắt user
                    # tự dịch "0 7 * * *".
                    "cron_human": cron_util.describe_cron(rem["cron"]) if rem["cron"] else ""}

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
                                   muc_quyen: str = Form(None)):
            """Sửa nhắc/lịch đang chờ (trang Việc định kỳ: nút Sửa). Bỏ trống trường nào thì giữ
            nguyên trường đó; truyền cron HOẶC at/delay_min/due_at để đổi thời điểm."""
            async with self._io:
                return self.update(brain, id, text=text, label=label, mode=mode, chat_id=chat_id,
                                   cron=cron, at=at, delay_min=delay_min, due_at=due_at,
                                   muc_quyen=muc_quyen)

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


def register(app, deps: RemindersDeps) -> RemindersFeature:
    feat = RemindersFeature(deps)
    app.include_router(feat.router)
    return feat
