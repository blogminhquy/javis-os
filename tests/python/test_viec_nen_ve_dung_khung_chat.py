"""Việc nền giao từ chat tự về đúng khung chat; loop và nhắc hẹn cũng thành thẻ (0.64.49).

    python tests/python/test_viec_nen_ve_dung_khung_chat.py

Audit 2026-09-24 (xem test_viec_nen_khong_moc_lung_tung.py) để lại hai việc, chủ repo bảo làm
luôn:
1. `javis_task` thiếu chat_id thì kết quả rơi về ID Telegram đầu tiên, máy chưa đấu Telegram
   thì mất hút. Trường đó trước đây hoàn toàn trông vào model tự chép. Nay máy chủ ghi sổ lượt
   đang chạy theo brain (luot_dang_chay.py) và tool tự điền khi chỉ có đúng một khung chat.
2. Kết quả loop và nhắc hẹn vẫn là bong bóng chữ trơn có emoji. Nay mang khối JAVIS_VIEC như
   việc Kanban để khung chat vẽ thẻ.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import importlib.util
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-khung-chat-state-"))

import luot_dang_chay as ldc  # noqa: E402

fails = []


def check(ten, dk, them=""):
    print(("ok   " if dk else "FAIL ") + ten + ("" if dk or not them else f"  [{them}]"))
    if not dk:
        fails.append(ten)


A = tempfile.mkdtemp(prefix="brainA-")
B = tempfile.mkdtemp(prefix="brainB-")

# ---- 1. Sổ lượt đang chạy ----
ldc._DANG.clear()
check("sổ rỗng thì không đoán", ldc.doan_chat_id(A) == "")
k1 = ldc.bat_dau("web:s1", A)
check("một khung chat trên brain A thì đoán ra nó", ldc.doan_chat_id(A) == "web:s1")
check("brain khác không bị gán nhầm", ldc.doan_chat_id(B) == "")
check("đường dẫn viết khác (dấu / cuối) vẫn khớp", ldc.doan_chat_id(A + "/") == "web:s1")
k2 = ldc.bat_dau("web:s1", A)
check("cùng một khung chạy hai lượt (lượt chat + việc nền giọng) vẫn đoán được",
      ldc.doan_chat_id(A) == "web:s1")
k3 = ldc.bat_dau("web:s2", A)
check("hai khung chat cùng chạy trên một brain thì KHÔNG đoán", ldc.doan_chat_id(A) == "")
ldc.ket_thuc(k3)
check("khung kia xong thì đoán lại được", ldc.doan_chat_id(A) == "web:s1")
ldc.ket_thuc(k1)
ldc.ket_thuc(k2)
check("gạch hết thì sổ rỗng", ldc.doan_chat_id(A) == "" and not ldc._DANG)
ldc.bat_dau("web:cu", A)
check("lượt kẹt quá lâu tự bị dọn",
      ldc.doan_chat_id(A, now=__import__("time").time() + ldc.TUOI_TOI_DA + 10) == "" and not ldc._DANG)
check("chat_id rỗng không vào sổ", ldc.bat_dau("", A) and not ldc._DANG)

MAIN = (SERVER / "main.py").read_text(encoding="utf-8")
rt = MAIN[MAIN.index("        async def run_turn("):MAIN.index("        async def run_workflow_turn(")]
check("run_turn ghi sổ lúc bắt đầu", "luot_dang_chay.bat_dau(f\"{WEB_CHAT_PREFIX}{conv_sid}\"" in rt)
check("run_turn gạch sổ trong finally (mọi đường ra)",
      rt.index("finally:") < rt.index("luot_dang_chay.ket_thuc(_khoa_luot)"))
bg = MAIN[MAIN.index("async def _voice_bg_task("):MAIN.index("async def _start_resumed_turn(")]
check("việc nền giọng cũng ghi và gạch sổ",
      "luot_dang_chay.bat_dau(" in bg and "luot_dang_chay.ket_thuc(_khoa_luot)" in bg)

# ---- 2. Tool javis_task tự điền chat_id ----
sys.path.insert(0, str(SERVER))
spec = importlib.util.spec_from_file_location(
    "javis_task_plugin", ROOT / "system" / "plugins" / "javis-task" / "plugin.py")
pl = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pl)

nhan = []


class _Store:
    def get_task(self, tid):
        return {"created_at": __import__("time").time(), "status": "triage"}


class _F:
    store = _Store()

    def enqueue(self, *a):
        nhan.append(a)
        return "t1"

    def board_view(self, v):
        return {"orchestration": "auto"}


pl.tasks_mod.current = lambda: _F()


class _Ctx:
    vault_root = A


ldc._DANG.clear()
k = ldc.bat_dau("web:s9", A)
out = pl._them({"title": "Tổng hợp doanh thu"}, _Ctx())
check("thiếu chat_id: tự gắn khung chat đang hỏi", nhan and nhan[-1][8] == "web:s9", repr(nhan[-1] if nhan else None))
check("kết quả tool nói rõ đã tự gắn", "tự gắn khung chat đang hỏi" in out, out)
check("đã gắn thì không còn cảnh báo mất hút", "CẢNH BÁO: chưa gắn người nhận" not in out)
out = pl._them({"title": "Việc khác", "chat_id": "123456"}, _Ctx())
check("model truyền chat_id thì giữ nguyên, không ghi đè", nhan[-1][8] == "123456")
ldc.bat_dau("web:s10", A)
out = pl._them({"title": "Việc ba"}, _Ctx())
check("hai khung cùng chạy: không đoán, giữ cảnh báo", nhan[-1][8] == "" and "CẢNH BÁO" in out)
ldc._DANG.clear()

# ---- 3. Nhắc hẹn và loop mang thẻ ----
import reminders  # noqa: E402

check("_nhan_kw: hàm (chat_id, text) không nhận viec", not reminders._nhan_kw(lambda c, t: None, "viec"))
check("_nhan_kw: hàm có viec thì nhận", reminders._nhan_kw(lambda c, t, viec=None: None, "viec"))
check("_nhan_kw: hàm **kw thì nhận", reminders._nhan_kw(lambda c, t, **kw: None, "viec"))

REM = (SERVER / "reminders.py").read_text(encoding="utf-8")
check("nhắc hẹn: chỉ truyền thẻ khi hàm gửi nhận được",
      'if _nhan_kw(self.deps.send_telegram, "viec"):' in REM)
check("nhắc hẹn: thẻ kind=reminder, lỗi thì failed",
      '"kind": "reminder", "status": "failed" if loi else "done"' in REM)
check("nhắc hẹn: bản web của nhắc thường là đúng lời nhắc, không kèm 'Nhắc bạn:'",
      'if mode == "notify":\n                web = text' in REM)
check("main: _bao_nhac_hen chuyển thẻ sang _notify_owner",
      "async def _bao_nhac_hen(chat_id, text, viec=None, web=\"\")" in MAIN
      and "viec=viec, web=web)" in MAIN)

# Chạy thật một nhắc hẹn thường qua hàm gửi CÓ nhận thẻ.
gui = []


async def _gui(chat_id, text, viec=None, web=""):
    gui.append((chat_id, text, viec, web))
    return True, ""


brain = Path(tempfile.mkdtemp(prefix="javis-rem-the-"))


def _ghi(p, t):
    Path(p).parent.mkdir(parents=True, exist_ok=True)
    Path(p).write_text(t, encoding="utf-8")

deps = reminders.RemindersDeps(
    brain_root=lambda _b: str(brain), atomic_write_text=_ghi,
    send_telegram=_gui, notify_ready=lambda *a, **k: None, build_system_prompt=lambda b: "",
    aux_model=lambda: None, aux_swap=lambda c, **k: c, safe_tools=[], readonly_tools=[],
    scheduler_brains=lambda: [str(brain)], apply_mcp=lambda *a, **k: None,
    mcp_allow_patterns=lambda *a, **k: [],
)
try:
    feat = reminders.RemindersFeature(deps) if hasattr(reminders, "RemindersFeature") else None
except Exception as e:
    feat = None
    print("   (bỏ qua chạy thật: không dựng được RemindersFeature:", type(e).__name__, e, ")")
if feat is not None and hasattr(feat, "_fire"):
    asyncio.run(feat._fire(str(brain), {"id": "r1", "mode": "notify", "text": "Uống nước", "chat_id": "web:s1"}))
    if gui:
        c, t, v, w = gui[-1]
        check("chạy thật: Telegram/hòm thư vẫn nhận câu đầy đủ", t.startswith("⏰ Nhắc bạn: Uống nước"), t)
        check("chạy thật: thẻ nhắc hẹn đúng trạng thái", v and v["kind"] == "reminder" and v["status"] == "done", repr(v))
        check("chạy thật: bản web gọn đúng lời nhắc", w == "Uống nước", repr(w))
    else:
        check("chạy thật: có gửi đi", False)

SI = (SERVER / "self_improve.py").read_text(encoding="utf-8")
check("loop: thẻ kind=loop, tự tạm dừng là blocked",
      '"status": "blocked" if paused_now else ("failed" if failed else "done")' in SI)
check("loop: gửi thẻ và bản web bỏ câu đầu emoji",
      "viec=viec," in SI and 'channel_context.strip_control_blocks("\\n\\n".join(parts[1:]) or parts[0])' in SI)

print(f"\n{len(fails)} FAIL" if fails else "\nTất cả xanh")
sys.exit(1 if fails else 0)
