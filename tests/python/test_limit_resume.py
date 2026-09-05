"""Tự chạy lại lượt chat khi gói thuê bao mở lại hạn mức (limit_resume.py).

    python tests/run.py limit_resume

Điều test ép: mục chờ chỉ tự chạy khi BIẾT mốc reset, chạy đúng MỘT lần sau mốc, tắt ô
"tự tiếp tục" là không chạy nữa nhưng "Chạy lại ngay" vẫn dùng được, tin mới của cùng phiên
huỷ lịch, và có trần số lần tự chạy lại. Kèm `pop_last_message` của kho phiên: chỉ rút đúng
câu "hết lượt" ở cuối, không rút nhầm câu trả lời thật.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import os
import tempfile
import time

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-resume-"))

import limit_resume as lr  # noqa: E402

_fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)


def _runner(log):
    async def run(attempt):
        log.append(attempt)
    return run


# ---- 1. Biết mốc reset -> hẹn, ngủ tới mốc + trừ hao, chạy đúng một lần với attempt=1 ----
async def kich_ban_hen():
    reg = lr.LimitResumeRegistry(grace=0.05)
    log = []
    now = time.time()
    item = reg.schedule("s1", now + 0.1, _runner(log), engine="claude-code", notice="Hết lượt")
    check("hẹn: auto bật", item.auto and item.reason == "")
    check("hẹn: có trong snapshot", [x["session_id"] for x in reg.snapshot()] == ["s1"])
    p = item.payload(now)
    check("hẹn: payload đủ trường cho thẻ",
          p["resume_at"] > now and p["wait_seconds"] >= 0 and p["engine"] == "claude-code"
          and p["notice"] == "Hết lượt" and p["max_attempts"] == lr.MAX_ATTEMPTS)
    await asyncio.sleep(0.05)
    check("hẹn: chưa tới giờ thì chưa chạy", log == [])
    await asyncio.sleep(0.3)
    check("hẹn: tới giờ chạy đúng một lần, attempt=1", log == [1])
    check("hẹn: chạy xong thì rút khỏi sổ", reg.get("s1") is None and reg.snapshot() == [])


# ---- 2. Không biết mốc reset -> KHÔNG hẹn, còn nút chạy ngay ----
async def kich_ban_khong_moc():
    reg = lr.LimitResumeRegistry(grace=0.01)
    log = []
    item = reg.schedule("s2", 0, _runner(log), notice="x")
    check("không mốc: auto tắt, lý do no_reset", (not item.auto) and item.reason == "no_reset")
    check("không mốc: bật tay cũng không được", reg.set_auto("s2", True).auto is False)
    await asyncio.sleep(0.05)
    check("không mốc: không tự chạy", log == [])
    got = await reg.run_now("s2")
    check("không mốc: chạy ngay vẫn được, attempt=1", got is not None and log == [1])
    check("không mốc: chạy ngay xong thì rút khỏi sổ", reg.get("s2") is None)


# ---- 3. Tắt ô tự tiếp tục -> không chạy khi tới giờ; bật lại -> chạy ----
async def kich_ban_tat_bat():
    reg = lr.LimitResumeRegistry(grace=0.01)
    log = []
    now = time.time()
    reg.schedule("s3", now + 0.05, _runner(log), notice="x")
    item = reg.set_auto("s3", False)
    check("tắt: auto=false, reason=off, mục vẫn còn", item and not item.auto and item.reason == "off"
          and reg.get("s3") is item)
    await asyncio.sleep(0.15)
    check("tắt: tới giờ KHÔNG chạy", log == [])
    check("tắt: snapshot vẫn kê mục để thẻ còn nút chạy ngay", len(reg.snapshot()) == 1)
    reg.set_auto("s3", True)
    await asyncio.sleep(0.1)
    check("bật lại sau mốc: chạy luôn", log == [1])


# ---- 4. Tin mới cùng phiên huỷ lịch; hẹn lại thay mục cũ ----
async def kich_ban_huy():
    reg = lr.LimitResumeRegistry(grace=0.01)
    log = []
    now = time.time()
    reg.schedule("s4", now + 0.05, _runner(log), notice="x")
    got = reg.cancel("s4")
    check("huỷ: trả mục vừa huỷ", got is not None and reg.get("s4") is None)
    await asyncio.sleep(0.15)
    check("huỷ: không chạy", log == [])
    log2 = []
    reg.schedule("s5", now + 10, _runner(log), notice="cũ")
    item = reg.schedule("s5", now + 0.05, _runner(log2), notice="mới", attempt=1)
    check("hẹn lại: mục mới thay mục cũ", reg.get("s5") is item and item.notice == "mới")
    await asyncio.sleep(0.15)
    check("hẹn lại: chỉ runner mới chạy, attempt nối tiếp (2)", log == [] and log2 == [2])


# ---- 5. Trần số lần và mốc quá xa ----
async def kich_ban_tran():
    reg = lr.LimitResumeRegistry(grace=0.01, max_wait=60, max_attempts=3)
    log = []
    now = time.time()
    item = reg.schedule("s6", now + 0.05, _runner(log), attempt=3)
    check("trần lần: attempt=3 thì không hẹn nữa", not item.auto and item.reason == "max_attempts")
    item = reg.schedule("s7", now + 3600, _runner(log))
    check("quá xa: không hẹn, lý do too_far", not item.auto and item.reason == "too_far")
    await asyncio.sleep(0.1)
    check("trần/quá xa: không chạy gì", log == [])


# ---- 6. run_now khi không có mục -> None ----
async def kich_ban_rong():
    reg = lr.LimitResumeRegistry()
    check("run_now phiên lạ: None", await reg.run_now("khong-co") is None)
    check("set_auto phiên lạ: None", reg.set_auto("khong-co", True) is None)


for kb in (kich_ban_hen, kich_ban_khong_moc, kich_ban_tat_bat, kich_ban_huy,
           kich_ban_tran, kich_ban_rong):
    asyncio.run(kb())


# ---- 7. Kho phiên: rút đúng câu "hết lượt" ở cuối ----
import sessions  # noqa: E402

_db = os.path.join(tempfile.mkdtemp(prefix="javis-resume-db-"), "s.db")
from pathlib import Path  # noqa: E402
store = sessions.SessionStore(Path(_db))
sid = store.create_session(brain="brain")
store.append_message(sid, "user", "Doanh thu tháng này?")
store.append_message(sid, "assistant", "Hết lượt Claude Code.")
check("pop: sai nội dung thì không rút", store.pop_last_message(sid, "assistant", "khác") is False)
check("pop: sai vai thì không rút", store.pop_last_message(sid, "user") is False)
check("pop: đúng vai + nội dung thì rút", store.pop_last_message(sid, "assistant", "Hết lượt Claude Code.") is True)
msgs = store.get_messages(sid)
check("pop: còn đúng tin người dùng", [m["role"] for m in msgs] == ["user"])
check("pop: msg_count giảm theo", (store.get_session(sid) or {}).get("msg_count") == 1)
check("pop: phiên trống không nổ", store.pop_last_message("khong-co", "assistant") is False)

if _fails:
    print(f"\n{len(_fails)} FAIL: {_fails}")
    raise SystemExit(1)
print("\nOK tất cả")
