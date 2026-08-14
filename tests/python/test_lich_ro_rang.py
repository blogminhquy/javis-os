"""Lịch phải RÕ RÀNG và SỬA ĐƯỢC - bốn lỗi khách báo cùng một chỗ (trang Việc định kỳ).

    python tests/run.py lich_ro_rang        (KHÔNG mạng)

1. Cron hiện ra mà không biết chạy lúc nào. Thẻ việc chỉ in "cron 0 7 * * *" - người dùng
   thường không đọc được cron, và ngay cả người đọc được cũng không biết LẦN KẾ TIẾP là khi nào.
2. Không sửa/xoá được lịch cron. Nhắc hẹn tạo xong là bất động: chỉ có Huỷ (giữ lại trong lịch
   sử) và Chuyển brain, muốn đổi giờ phải xoá rồi tạo lại.
3. Tạo cron quá dễ. Javis dựng job "sáng nào cũng báo qua Telegram" trong khi Telegram còn chưa
   đấu - job chạy đúng giờ rồi ném kết quả vào hư không, không ai được báo là thiếu gì.
4. "Vòng lặp tự cải thiện" mọc lại sau mỗi lần xoá / trên mỗi bản fork mới.
"""
import json
import re
import tempfile
from pathlib import Path

from _paths import ROOT, SERVER  # noqa: E402,F401  - nạp server/ vào sys.path

import cron_util  # noqa: E402
import reminders  # noqa: E402
import self_improve  # noqa: E402

CONSOLE = (ROOT / "dashboard" / "console.js").read_text(encoding="utf-8")
PLUGIN = (ROOT / "system" / "plugins" / "javis-schedule" / "plugin.py").read_text(encoding="utf-8")

fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        fails.append(name)


def atomic_write(path, text):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8", newline="\n")


# ── 1. Đọc cron thành lời ────────────────────────────────────────────────────
check("cron mỗi ngày đọc ra giờ cụ thể", cron_util.describe_cron("0 7 * * *") == "7:00 mỗi ngày")
check("cron bước phút đọc ra chu kỳ", cron_util.describe_cron("*/30 * * * *") == "mỗi 30 phút")
# Tên thứ nay lấy từ sổ đăng ký ngôn ngữ nên viết hoa ("Thứ Hai"), thống nhất với câu đồng
# hồ. So không phân biệt hoa thường: thứ test này canh là "có nói rõ thứ mấy", không phải
# cách viết hoa.
check("cron theo thứ nói rõ thứ", "thứ hai" in cron_util.describe_cron("0 9 * * 1").lower())
check("và cron đọc được sang tiếng Anh",
      "monday" in cron_util.describe_cron("0 9 * * 1", "en").lower())
check("cron theo ngày trong tháng nói rõ ngày", "ngày 1" in cron_util.describe_cron("0 0 1 * *"))
check("macro @daily cũng đọc được", cron_util.describe_cron("@daily") == "0:00 mỗi ngày")
check("nhiều mốc giờ trong ngày liệt kê đủ",
      cron_util.describe_cron("30 8,17 * * *").startswith("8:30, 17:30"))
# Dạng lạ thì trả lại biểu thức thô - thà thô còn hơn nói sai giờ chạy.
check("cron vừa giới hạn thứ vừa giới hạn ngày thì trả nguyên văn",
      cron_util.describe_cron("0 7 1 * 1") == "0 7 1 * 1")
check("cron rác không làm vỡ chỗ hiển thị", cron_util.describe_cron("khong phai cron") == "khong phai cron")


# ── Dựng feature nhắc hẹn tối giản (không mạng, không engine) ────────────────
def make_feature(notify_ready=None):
    brain = Path(tempfile.mkdtemp(prefix="javis-lich-brain-"))

    async def fake_send(_chat, _text):
        return True, ""

    deps = reminders.RemindersDeps(
        brain_root=lambda _b: str(brain),
        atomic_write_text=atomic_write,
        send_telegram=fake_send,
        build_system_prompt=lambda _b: "",
        aux_model=lambda: None,
        safe_tools=[], readonly_tools=[],
        scheduler_brains=lambda: [],
        notify_ready=notify_ready,
    )
    return reminders.RemindersFeature(deps), str(brain)


# ── 2. View mang đủ thông tin để hiện giờ ───────────────────────────────────
feat, brain = make_feature()
rem = feat._create(brain, "Báo doanh thu", cron="0 7 * * *", label="Bản tin sáng", mode="task")
view = feat.pending_views(brain)[0]
check("view có cron_human để thẻ việc nói được lịch bằng lời",
      view.get("cron_human") == "7:00 mỗi ngày")
check("view có due_at + due_human cho lần chạy kế tiếp",
      view.get("due_at", 0) > 0 and re.match(r"\d{2}:\d{2} \d{2}/\d{2}/\d{4}", view.get("due_human", "")))


# ── 3. Sửa được lịch, xoá được hẳn ──────────────────────────────────────────
old_due = view["due_at"]
r = feat.update(brain, rem["id"], cron="0 20 * * *", label="Bản tin tối")
check("sửa cron trả về ok", r.get("ok") is True)
check("sửa cron cập nhật luôn lời đọc", (r.get("reminder") or {}).get("cron_human") == "20:00 mỗi ngày")
check("sửa cron tính lại lần chạy kế tiếp", (r.get("reminder") or {}).get("due_at") != old_due)
check("sửa được cả tên", (r.get("reminder") or {}).get("label") == "Bản tin tối")
r2 = feat.update(brain, rem["id"], at="9h30")
check("đổi lịch lặp sang hẹn một lần thì bỏ cron",
      r2.get("ok") is True and (r2.get("reminder") or {}).get("cron") == "")
check("sửa cron sai cú pháp báo lỗi rõ, không ghi bừa",
      feat.update(brain, rem["id"], cron="99 * * * *").get("ok") is False)
check("sửa id không tồn tại báo lỗi", feat.update(brain, "r_khong_co", label="x").get("ok") is False)

check("xoá hẳn thì mất khỏi kho", feat.delete(brain, rem["id"]) is True
      and not feat.pending_views(brain))
check("xoá lần hai trả False (không giả vờ thành công)", feat.delete(brain, rem["id"]) is False)

# Huỷ khác xoá: huỷ giữ lại bản ghi để còn tra lịch sử.
feat2, brain2 = make_feature()
keep = feat2._create(brain2, "Uống thuốc", delay_min=30)
feat2.cancel(brain2, keep["id"])
check("huỷ chỉ đổi trạng thái, bản ghi vẫn còn trong kho",
      any(x.get("id") == keep["id"] for x in feat2._load(brain2).get("reminders", [])))
check("mục đã huỷ thì không sửa được nữa (tạo mới thay vì hồi sinh)",
      feat2.update(brain2, keep["id"], label="x").get("ok") is False)


# ── 4. Chưa có kênh báo thì KHÔNG âm thầm tạo ───────────────────────────────
feat3, brain3 = make_feature(notify_ready=lambda: (False, "bot Telegram chưa bật"))
blocked = False
try:
    feat3._create(brain3, "Bản tin sáng", cron="0 7 * * *", mode="task")
except reminders.NotifyNotReady as e:
    blocked = True
    msg = str(e)
check("chưa đấu Telegram thì chặn tạo job báo kết quả", blocked)
check("lời chặn nói rõ THIẾU GÌ", blocked and "bot Telegram chưa bật" in msg)
check("lời chặn chỉ luôn chỗ sửa", blocked and "Kênh" in msg)


def creates_ok(feat, brain, **kw):
    """Tạo được không? Trả True/False, KHÔNG nuốt các lỗi khác (chỉ bắt đúng rào thiếu kênh)."""
    try:
        return bool(feat._create(brain, kw.pop("text", "Việc test"), **kw).get("id"))
    except reminders.NotifyNotReady:
        return False


check("nhắc thường cũng bị chặn (nhắc mà không ai nhận thì vô nghĩa)",
      not creates_ok(feat3, brain3, delay_min=10, mode="notify"))
check("user đồng ý thì tạo tiếp được bằng allow_no_channel",
      creates_ok(feat3, brain3, cron="0 7 * * *", mode="task", allow_no_channel=True))
# Job script là loại giám sát: reminders.py cố ý IM LẶNG khi stdout rỗng, nên thiếu kênh báo
# không phải lý do chặn - chặn nó là làm hỏng một tính năng đang đúng.
(Path(brain3) / "Javis" / "scripts").mkdir(parents=True, exist_ok=True)
(Path(brain3) / "Javis" / "scripts" / "ping.py").write_text("print('[SILENT]')\n", encoding="utf-8")
check("job script KHÔNG bị chặn (giám sát im lặng là bình thường)",
      creates_ok(feat3, brain3, text="", mode="script", script="ping.py", delay_min=5))

# Sửa job script: đổi được tên/lịch nhưng KHÔNG được âm thầm đổi kiểu - đổi kiểu là mất tên
# file script, job hoá thành "nhắc" vô nghĩa.
sc = feat3._create(brain3, "", mode="script", script="ping.py", delay_min=5, label="Ping máy")
sc_up = feat3.update(brain3, sc["id"], mode="notify", label="Ping máy chủ", cron="*/10 * * * *")
check("sửa job script giữ nguyên kiểu script",
      sc_up.get("ok") is True and (sc_up.get("reminder") or {}).get("mode") == "script")
check("sửa job script vẫn đổi được tên và lịch",
      (sc_up.get("reminder") or {}).get("label") == "Ping máy chủ"
      and (sc_up.get("reminder") or {}).get("cron") == "*/10 * * * *")
check("dashboard khoá nút Kiểu khi sửa job script", "rem.script" in CONSOLE)
ready_feat, ready_brain = make_feature(notify_ready=lambda: (True, ""))
check("đã đấu Telegram thì tạo bình thường",
      ready_feat._create(ready_brain, "Bản tin sáng", cron="0 7 * * *", mode="task")
      .get("cron") == "0 7 * * *")
check("thiếu dep kiểm tra thì không dựng rào (test/embed tối giản)",
      make_feature()[0].notify_status()[0] is True)


# ── 5. "Vòng lặp tự cải thiện" không được hồi sinh ──────────────────────────
def make_loop_feature():
    state = Path(tempfile.mkdtemp(prefix="javis-lich-state-"))
    brain = Path(tempfile.mkdtemp(prefix="javis-lich-loopbrain-"))
    deps = self_improve.LoopDeps(
        build_system_prompt=lambda _b: "",
        brain_root=lambda _b: str(brain),
        aux_model=lambda: None,
        atomic_write_text=atomic_write,
        project_root=Path("."),
        state_dir=state,
        safe_tools=[], readonly_tools=[],
    )
    return self_improve.LoopFeature(deps), str(brain), state / "loop_config.json"


loopf, lbrain, cfg_path = make_loop_feature()
# Bản fork sạch: loop_config.json do register_brain() sinh ra chỉ để nhớ danh sách brain.
atomic_write(cfg_path, json.dumps({"brain": "brain", "brains": [lbrain]}, ensure_ascii=False))
loopf.ensure_migrated()
check("config rỗng thì KHÔNG dựng loop legacy (bản fork mới phải sạch)",
      not loopf.list_loops(lbrain))
check("đã soát một lần thì đóng dấu lại, khỏi soát lại mỗi lần khởi động",
      json.loads(cfg_path.read_text(encoding="utf-8")).get(self_improve.MIGRATED_KEY) is True)

# Bản cũ thật: có custom_goal → migrate 1 lần, và XOÁ RỒI thì không mọc lại.
loopf2, lbrain2, cfg2 = make_loop_feature()
atomic_write(cfg2, json.dumps({"brain": "brain", "mode": "auto", "interval_min": 30,
                               "custom_goal": "Đọc Hermes rồi cải tiến 1 thứ"}, ensure_ascii=False))
loopf2.ensure_migrated()
migrated = [lp for lp in loopf2.list_loops(lbrain2) if lp["slug"] == self_improve.LEGACY_SLUG]
check("bản cũ có nội dung thật thì vẫn migrate (không mất việc của người dùng)", len(migrated) == 1)
check("migrate giữ nguyên nội dung vào thân file",
      migrated and "Hermes" in (migrated[0].get("body") or ""))
loopf2.delete_loop(lbrain2, self_improve.LEGACY_SLUG)
loopf2._migrated = False          # giả lập KHỞI ĐỘNG LẠI server
loopf2.ensure_migrated()
check("xoá rồi khởi động lại thì loop legacy KHÔNG mọc lại",
      not [lp for lp in loopf2.list_loops(lbrain2) if lp["slug"] == self_improve.LEGACY_SLUG])
loopf2.write_config({"brain": "brain", "enabled": False, "custom_goal": ""})
check("lệnh ghi config legacy rỗng cũng không dựng lại loop đã xoá",
      not [lp for lp in loopf2.list_loops(lbrain2) if lp["slug"] == self_improve.LEGACY_SLUG])

# Vault cũ trong config không còn trên máy → brain_root() rơi về brain mặc định, và loop cũ sẽ
# mọc ra ở một brain chẳng liên quan. Đây đúng là đường mà "Vòng lặp tự cải thiện" lạ đi vào
# Brain Default trên máy khách.
loopf3, lbrain3, cfg3 = make_loop_feature()
atomic_write(cfg3, json.dumps({"brain": r"D:\Vault Da Bi Xoa", "enabled": True,
                               "custom_goal": "việc cũ"}, ensure_ascii=False))
loopf3.ensure_migrated()
check("vault cũ không còn thì KHÔNG dồn loop cũ sang brain khác",
      not [lp for lp in loopf3.list_loops(lbrain3) if lp["slug"] == self_improve.LEGACY_SLUG])
check("trường hợp đó cũng đóng dấu để khỏi soát lại mãi",
      json.loads(cfg3.read_text(encoding="utf-8")).get(self_improve.MIGRATED_KEY) is True)


# ── 6. Dashboard thật sự hiện giờ + có nút sửa/xoá ──────────────────────────
check("thẻ nhắc hẹn hiện lần chạy kế tiếp", "kế tiếp ${fmtWhen(r.due_at)}" in CONSOLE)
check("thẻ nhắc hẹn hiện cron bằng lời", "r.cron_human || r.cron" in CONSOLE)
check("có hàm nói rõ hôm nay/mai/ngày cụ thể", "function fmtWhen" in CONSOLE)
check("có hàm nói còn bao lâu nữa", "function fmtLeft" in CONSOLE)
check("thẻ nhắc hẹn có nút Sửa và Xoá",
      "rmEdit" in CONSOLE and "rmDel" in CONSOLE and "/reminders/delete" in CONSOLE)
check("form sửa được nhắc hẹn qua /reminders/update", "/reminders/update" in CONSOLE)
check("thiếu kênh báo thì hỏi lại chứ không im lặng",
      "can_force" in CONSOLE and "Vẫn tạo" in CONSOLE)
check("đầu trang Việc cảnh báo khi chưa có kênh báo", "lpNotifyWarn" in CONSOLE)
check("tool javis_schedule có op=update để sửa lịch bằng chat",
      '"update"' in PLUGIN and "_do_update" in PLUGIN)
check("tool KHÔNG tự vượt rào thiếu kênh",
      "KHÔNG tự quyết hộ" in PLUGIN and "allow_no_channel" in PLUGIN)

if fails:
    raise SystemExit(f"\nFAIL - test_lich_ro_rang: {len(fails)} lỗi: {fails}")
print("\nOK - test_lich_ro_rang: tất cả pass")
