"""Việc nền của giọng nói phải ở LẠI khung chat đang nói, và không đội lốt Telegram.

    python tests/run.py viec_nen_giong_dung_khung_chat        (KHÔNG mạng)

Chủ dự án báo 17/09, hai triệu chứng của CÙNG một gốc:

  1. "chạy nền xong đang trả lời tag là TG thì không đúng" - hội thoại sinh ra mang nhãn TG
     trong thanh Lịch sử, dù người dùng đang ngồi trên dashboard.
  2. "mỗi 1 lần gọi chạy nền khi nói chuyện giọng nói là nó sinh ra 1 hội thoại mới... từ đó
     sinh ra rất nhiều hội thoại chỉ có 1 tin hay 2 tin".

Gốc nằm ở `_voice_ask_javis`: nó chạy lượt bộ não chính qua vỏ chung `_tg_answer` với
`chat_id` DUY NHẤT cho mỗi việc (`voice:<sid>:<uuid>`). Vỏ đó tự khớp phiên theo chat_id, mà
chat_id chưa từng thấy nghĩa là chưa có phiên, nên `_tg_conv_sid` mở một bản ghi hội thoại
MỚI - mỗi việc nền một cái. Và `_tg_conv_sid` lại đóng cứng `channel="telegram"` cho mọi bản
ghi nó tạo, bất kể kênh thật là gì, nên đống hội thoại rơi vãi ấy còn đeo thêm nhãn TG.

Hai chỗ sửa, test canh cả hai:

  * `_tg_conv_sid` nhận kênh thật và đóng đúng dấu (chữa luôn cho Zalo, CLI và bot chuyên
    trách - cả ba đang bị dán nhãn telegram y hệt).
  * `_tg_answer` nhận `phien_kho` (dùng đúng phiên kho này, đừng tự mở) và `ghi_kho`
    (False = chỉ ĐỌC phiên đó làm ngữ cảnh, không ghi tin nào), để việc nền của giọng chạy
    NGAY TRONG hội thoại người dùng đang nói, còn `push_to_chat` vẫn là nơi duy nhất ghi kết
    quả xuống - không đẻ phiên, không ghi đôi.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import inspect
import os
import re
import sys
import tempfile
import time

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-vnkc-"))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import main  # noqa: E402

_fails = []


def check(name, cond, extra=None):
    print(("ok   " if cond else "FAIL ") + name + ("" if cond or extra is None else f"  [{extra}]"))
    if not cond:
        _fails.append(name)


SRC = (ROOT / "server" / "main.py").read_text(encoding="utf-8")
BRAIN = tempfile.mkdtemp(prefix="javis-vnkc-brain-")


# ---------------------------------------------------------------- kho giả
class KhoGia:
    """Bản rút gọn của kho phiên, đủ cho đường lưu một lượt (xem test_luu_luot_chat)."""

    def __init__(self):
        self.sessions = {}
        self.messages = []      # (sid, role, content)
        self.titles = []
        self.da_tao = []        # kênh của từng phiên MỚI mở, theo thứ tự

    def get_or_create(self, session_id, *, brain, engine, model):
        sid = session_id or f"sid-{len(self.sessions) + 1}"
        row = self.sessions.setdefault(sid, {"id": sid, "msg_count": 0})
        row.update({"brain": brain, "engine": engine, "model": model,
                    "updated_at": time.time()})
        return sid

    def create_session(self, *, brain=None, engine=None, model=None, channel="web", **kw):
        sid = f"sid-{len(self.sessions) + 1}"
        self.sessions[sid] = {"id": sid, "brain": brain, "engine": engine, "model": model,
                              "channel": channel, "updated_at": time.time(), "msg_count": 0}
        self.da_tao.append(channel)
        return sid

    def archive_stale(self, channel, before_ts):
        return 0

    def get_session(self, sid):
        return self.sessions.get(sid)

    def get_messages(self, sid):
        return [{"role": r, "content": c} for s, r, c in self.messages if s == sid]

    def append_message(self, sid, role, content, tool_calls=None):
        self.messages.append((sid, role, content))
        row = self.sessions.setdefault(sid, {"id": sid, "msg_count": 0})
        row["msg_count"] = row.get("msg_count", 0) + 1
        row["updated_at"] = time.time()
        return len(self.messages)

    def auto_title(self, sid, first_user_message):
        self.titles.append((sid, first_user_message))

    def set_cli_session_id(self, sid, cli_sid):
        self.sessions.setdefault(sid, {})["cli_session_id"] = cli_sid

    def set_codex_thread_id(self, sid, tid):
        self.sessions.setdefault(sid, {})["codex_thread_id"] = tid

    def clear_codex_thread_id(self, sid):
        self.sessions.setdefault(sid, {}).pop("codex_thread_id", None)


def lap_gia():
    """Thay phụ thuộc ngoài của `_tg_answer` bằng bản giả. Trả về (kho, đã-thấy-lịch-sử)."""
    kho = KhoGia()
    thay = {"lich_su": None, "hoi": None}

    async def _loi_engine(text, meta, progress, **kw):
        # Lõi giả: ghi lại ngữ cảnh mà vỏ truyền xuống rồi trả một câu như thật.
        thay["hoi"] = text
        thay["lich_su"] = main._tg_lich_su_kho(kw.get("store"), kw.get("conv_sid") or "", text)[0]
        return {"text": "Xong rồi anh: doanh thu hôm nay 250k."}

    main.get_store = lambda: kho
    main._tg_answer_engine = _loi_engine
    main._chat_provider = lambda mcfg: ("anthropic-cli", "cli", "", "opus")
    main._chat_provider_kenh = lambda mcfg, kenh: ("anthropic-cli", "cli", "", "opus")
    main._tg_brain = lambda chat_id: BRAIN
    main._brain_root = lambda b: BRAIN
    main.log_conversation = lambda brain, u, j: None

    async def _enqueue(brain, conv_sid, user, assistant):
        return None
    main.learn_feature.enqueue = _enqueue

    async def _khong_canh_bao(brain, chat, text, trace):
        return ""
    main._canh_bao_hua_suong = _khong_canh_bao
    main._link_file_khong_thay = lambda root, text: []

    main._TG_SESS.clear()
    main._TG_SID_MAP.clear()
    return kho, thay


# ================================================================
# 1. `_tg_conv_sid` đóng dấu ĐÚNG kênh thật
# ================================================================
# Trước bản này mọi bản ghi nó tạo đều mang channel="telegram", nên hội thoại của Zalo, của
# CLI, của bot chuyên trách và của việc nền giọng nói đều hiện nhãn TG ở thanh Lịch sử.
_sig = inspect.signature(main._tg_conv_sid)
check("_tg_conv_sid nhận được kênh thật", "channel" in _sig.parameters)
check("mặc định vẫn là telegram (chỗ gọi cũ không đổi nghĩa)",
      _sig.parameters.get("channel") is not None
      and _sig.parameters["channel"].default == "telegram")

kho, _ = lap_gia()
sess_tg = main._tg_session("555")
sid_tg = main._tg_conv_sid(kho, sess_tg, BRAIN, "cli", "opus")
check("lượt Telegram vẫn gắn channel='telegram'", kho.get_session(sid_tg)["channel"] == "telegram")

for kenh in ("cli", "zalo", "bot:ban-hang"):
    kho, _ = lap_gia()
    s = main._tg_session("kh-" + kenh)
    sid = main._tg_conv_sid(kho, s, BRAIN, "cli", "opus", channel=kenh)
    check(f"kênh {kenh!r} KHÔNG bị dán nhãn telegram",
          kho.get_session(sid)["channel"] == kenh, kho.get_session(sid)["channel"])


# ================================================================
# 2. `_tg_answer` nhận phiên kho có sẵn, và chế độ chỉ-đọc
# ================================================================
_sig_ans = inspect.signature(main._tg_answer)
check("_tg_answer nhận phien_kho", "phien_kho" in _sig_ans.parameters)
check("_tg_answer nhận ghi_kho", "ghi_kho" in _sig_ans.parameters)
check("CANARY: vỏ chung vẫn giữ nguyên bốn tham số đầu (kênh CLI canh chuỗi này)",
      'async def _tg_answer(text, meta=None, progress=None, channel="telegram"' in SRC)

# --- 2a. Mặc định không đổi: vẫn tự mở phiên, vẫn ghi đủ hai tin ---
kho, thay = lap_gia()
asyncio.run(main._tg_answer("doanh thu hôm nay?", {"chat_id": "555"}))
check("mặc định: vẫn tự mở một phiên", len(kho.sessions) == 1)
check("mặc định: vẫn ghi đủ tin user + assistant", len(kho.messages) == 2)

# --- 2b. Có phien_kho + ghi_kho=False: không đẻ phiên, không ghi tin nào ---
kho, thay = lap_gia()
KHUNG = kho.create_session(brain=BRAIN, engine="codex", model="opus", channel="web")
kho.append_message(KHUNG, "user", "kiểm tra giúp anh mã nguồn có nối GitHub không")
kho.append_message(KHUNG, "assistant", "Ừ, để xem ngay.")
so_phien_truoc = len(kho.sessions)
so_tin_truoc = len(kho.messages)

asyncio.run(main._tg_answer("kiểm tra mã nguồn có nối GitHub không",
                            {"chat_id": "voice:khung-1:abcd1234"},
                            channel="cli", phien_kho=KHUNG, ghi_kho=False))

check("việc nền KHÔNG đẻ hội thoại mới", len(kho.sessions) == so_phien_truoc,
      f"{len(kho.sessions)} phiên")
check("việc nền KHÔNG tự ghi tin nào (push_to_chat mới là nơi ghi)",
      len(kho.messages) == so_tin_truoc, f"{len(kho.messages)} tin")
check("việc nền không đặt lại tiêu đề khung chat", kho.titles == [])
check("nhưng vẫn ĐỌC được lịch sử của đúng khung chat đó",
      thay["lich_su"] is not None and len(thay["lich_su"]) == 2
      and "nối GitHub" in thay["lich_su"][0]["content"],
      thay["lich_su"])
check("không ghi liên kết bền chat->phiên cho khoá dùng một lần",
      not any(k.startswith("voice:") for k in main._TG_SID_MAP))


# ================================================================
# 3. `_voice_ask_javis` ghim lượt vào khung chat đang nói
# ================================================================
kho, thay = lap_gia()
KHUNG2 = kho.create_session(brain=BRAIN, engine="codex", model="opus", channel="web")
kho.append_message(KHUNG2, "user", "tra doanh thu tháng 6 giúp anh")

out = asyncio.run(main._voice_ask_javis("tra doanh thu tháng 6", KHUNG2, BRAIN,
                                        key=f"voice:{KHUNG2}:abcd1234"))
check("việc nền vẫn trả về nội dung như cũ", "250k" in out, out)
check("và vẫn không đẻ hội thoại nào", len(kho.sessions) == 1, len(kho.sessions))
check("và không ghi thêm tin nào vào khung chat", len(kho.messages) == 1, len(kho.messages))


# ================================================================
# 3b. Bản ghi hội thoại sau một lượt nói + một việc nền trông ĐÚNG như phải thế
# ================================================================
# Đây là thứ người dùng thật sự nhìn thấy: một khung chat, ba tin, không có khung nào khác mọc
# ra bên cạnh. Dựng lại đúng chuỗi mà `run_voice_turn` + `_voice_bg_task` đi qua.
kho, thay = lap_gia()
KHUNG3 = kho.create_session(brain=BRAIN, engine="codex", model="opus", channel="web")
kho.append_message(KHUNG3, "user", "kiểm tra giúp anh mã nguồn có nối GitHub không")   # người nói
kho.append_message(KHUNG3, "assistant", "Ừ, để xem ngay.")                            # câu chờ


async def _mot_luot_co_viec_nen():
    ket_qua = await main._voice_ask_javis(
        "kiểm tra mã nguồn có nối GitHub không", KHUNG3, BRAIN,
        key=f"voice:{KHUNG3}:abcd1234")
    # `push_to_chat` là nơi DUY NHẤT ghi kết quả việc nền xuống kho.
    main._CHAT_RUNTIME.publish = _khong_bat_ws
    await main.push_to_chat(KHUNG3, ket_qua)


async def _khong_bat_ws(frame):
    return None


asyncio.run(_mot_luot_co_viec_nen())

check("cả lượt nói lẫn việc nền nằm trong ĐÚNG MỘT khung chat",
      len(kho.sessions) == 1 and list(kho.sessions)[0] == KHUNG3, list(kho.sessions))
tin = [(r, c) for s, r, c in kho.messages if s == KHUNG3]
check("khung chat có đúng 3 tin: người nói -> câu chờ -> kết quả", len(tin) == 3, tin)
check("không có tin 'user' giả nào mang câu máy tự đặt ra",
      [r for r, _c in tin] == ["user", "assistant", "assistant"], [r for r, _c in tin])
check("kết quả việc nền ghi đúng MỘT lần, không ghi đôi",
      sum(1 for _r, c in tin if "250k" in c) == 1, tin)
check("khung chat vẫn mang kênh web, không bị đổi thành telegram",
      kho.get_session(KHUNG3)["channel"] == "web", kho.get_session(KHUNG3)["channel"])


# ================================================================
# 4. Khoá phiên dùng một lần phải được dọn, không rò bộ nhớ
# ================================================================
# Mỗi việc nền tạo một khoá `voice:<sid>:<uuid>` trong `_TG_SESS`, mà `_TG_SESS` chỉ bị xoá
# khi bot Telegram khởi động lại. Nói chuyện cả buổi là cả trăm khoá chết nằm lại, mỗi khoá
# còn ôm một đối tượng engine CLI.
body = (re.search(r"async def _voice_bg_task\([\s\S]*?\n        async def _start_resumed_turn", SRC)
        or [""])[0]
check("nhấc được thân _voice_bg_task", bool(body))
check("việc nền xong thì dọn khoá phiên dùng một lần khỏi _TG_SESS",
      "_TG_SESS.pop(" in body, body[-400:] if body else "")
check("kết quả vẫn đi về khung chat bằng push_to_chat", "push_to_chat(conv_sid" in body)
check("việc nền vẫn ghim vào khung chat đang nói (phien_kho=conv_sid)",
      re.search(r"_voice_ask_javis\(request, conv_sid, brain,", body) is not None)
check("_voice_ask_javis truyền phiên kho xuống vỏ chung",
      re.search(r"phien_kho=.{0,30}conv_sid", SRC) is not None)

print(("\n%d FAIL" % len(_fails)) if _fails else "\nTat ca OK")
raise SystemExit(1 if _fails else 0)
