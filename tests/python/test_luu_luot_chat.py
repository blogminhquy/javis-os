"""Một lượt chat phải được LƯU ĐÚNG như nhau ở cả hai kênh (dashboard và Telegram).

    python tests/run.py luu_luot_chat        (KHÔNG mạng)

Bối cảnh - phụ lục spec 2026-07-28 ghi ba lỗ do hai bản dispatch trôi lệch:

  (1) Telegram KHÔNG ghi `usage_store` cho nhánh Claude-CLI và nhánh API. Bảng Mức dùng vì
      thế báo thiếu mọi cuộc trò chuyện Telegram không đi qua Codex.
  (2) Telegram KHÔNG `append_message` / `auto_title` / `log_conversation` / `learn.enqueue`.
      Hội thoại Telegram vắng mặt ở `/sessions`, ở `brain/Memory/conversations`, và ở vòng
      tự học - lỗ hổng chức năng lớn nhất trong danh sách.
  (7) Dashboard KHÔNG `strip_control_blocks` trước khi lưu, nên khối `<!-- JAVIS_ASK ... -->`
      thô lọt vào kho phiên và nhật ký hội thoại - tức lọt vào chính corpus dùng để tự học.

Test gọi THẲNG `_tg_answer` thật với engine giả, nên nó đo hành vi chứ không đo hình dạng
code. Phần AST ở cuối chốt rằng nhánh dashboard cũng đi qua cùng một đường lưu.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401  - nạp server/ vào sys.path (xem tests/python/_paths.py)
import ast
import asyncio
import os
import sys
import tempfile
import time

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-luuluot-"))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import main  # noqa: E402

_fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)


BRAIN = tempfile.mkdtemp(prefix="javis-luuluot-brain-")
ASK = ('<!-- JAVIS_ASK: {"question":"Xem kỳ nào?",'
       '"options":[{"label":"Tuần này","desc":"7 ngày"}]} -->')


# ---------------------------------------------------------------- kho giả
class KhoGia:
    """Đủ mặt các phương thức mà đường lưu một lượt chạm tới."""

    def __init__(self):
        self.sessions = {}
        self.messages = []      # (sid, role, content)
        self.titles = []        # (sid, user_msg)

    def get_or_create(self, session_id, *, brain, engine, model):
        sid = session_id or f"sid-{len(self.sessions) + 1}"
        row = self.sessions.setdefault(sid, {"id": sid, "msg_count": 0})
        row.update({"brain": brain, "engine": engine, "model": model,
                    "updated_at": time.time()})
        return sid

    def create_session(self, *, brain=None, engine=None, model=None, channel="web", **kw):
        # Từ 0.9.246 vỏ Telegram XOAY phiên (nghỉ lâu / đủ dài thì sang phiên mới), nên phiên
        # mới được mở qua đường này chứ không còn qua get_or_create(None, ...).
        sid = f"sid-{len(self.sessions) + 1}"
        self.sessions[sid] = {"id": sid, "brain": brain, "engine": engine, "model": model,
                              "channel": channel, "updated_at": time.time(), "msg_count": 0}
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
        return None

    def set_cli_session_id(self, sid, cli_sid):
        self.sessions.setdefault(sid, {})["cli_session_id"] = cli_sid

    def set_codex_thread_id(self, sid, tid):
        self.sessions.setdefault(sid, {})["codex_thread_id"] = tid

    def clear_codex_thread_id(self, sid):
        self.sessions.setdefault(sid, {}).pop("codex_thread_id", None)


class CLIGia:
    """Engine Claude giả: phát đúng bộ sự kiện mà nhánh anthropic-cli tiêu thụ."""

    def __init__(self, **kw):
        self.system_prompt = ""
        self.model = None
        self.session_id = None

    def reset_session(self):
        self.session_id = None

    async def query(self, prompt):
        yield {"type": "text", "content": "Doanh thu hôm nay 250k."}
        yield {"type": "final",
               "content": "Doanh thu hôm nay 250k.\n\n" + ASK,
               "session_id": "cli-abc",
               "tokens_in": 120, "tokens_out": 45, "cost_usd": 0.012}


def lap_gia(prov, kind, key, model):
    """Thay mọi phụ thuộc ngoài của _tg_answer bằng bản giả. Trả về (kho, usage, log, learn)."""
    kho, usage, nhat_ky, hoc = KhoGia(), [], [], []

    main.get_store = lambda: kho
    main._chat_provider = lambda mcfg: (prov, kind, key, model)
    main._reasoning_level = lambda mcfg: "off"
    main._tg_brain = lambda chat_id: BRAIN
    main._brain_root = lambda b: BRAIN
    main.build_system_prompt = lambda b: "SYS"
    main._apply_mcp = lambda cli, brain=None: None
    main._apply_codex_hub = lambda ccli, root: None
    main.claude_engine = lambda **kw: CLIGia(**kw)
    main.usage_store.record = lambda *a, **k: usage.append((a, k))
    main.log_conversation = lambda brain, u, j: nhat_ky.append((brain, u, j))
    main.channel_context.collect_turn_files = lambda *a, **k: []

    async def _khong_lich(message, brain):
        return None
    main._schedule_cancel_action = _khong_lich

    async def _enqueue(brain, conv_sid, user, assistant):
        hoc.append((brain, conv_sid, user, assistant))
    main.learn_feature.enqueue = _enqueue

    main._TG_SESS.clear()
    return kho, usage, nhat_ky, hoc


# ================================================================
# 1. Telegram - nhánh Claude CLI
# ================================================================
kho, usage, nhat_ky, hoc = lap_gia("anthropic-cli", "cli", "", "opus")
kq = asyncio.run(main._tg_answer("doanh thu hôm nay?", {"chat_id": "555"}))
tra_loi = kq.get("text") if isinstance(kq, dict) else str(kq)

check("cli: có trả lời", "250k" in (tra_loi or ""))

# ---- (1) Mức dùng ----
check("cli: usage_store.record ĐƯỢC gọi", len(usage) == 1)
if usage:
    a, k = usage[0]
    check("cli: usage ghi đúng nhà cung cấp 'cli'", a and a[0] == "cli")
    check("cli: usage ghi đúng token vào/ra (120/45)", 120 in a and 45 in a)

# ---- (2) Kho phiên + tiêu đề + nhật ký + tự học ----
vai = [r for _s, r, _c in kho.messages]
check("cli: lưu lượt user vào kho phiên", "user" in vai)
check("cli: lưu lượt assistant vào kho phiên", "assistant" in vai)
check("cli: user và assistant CÙNG một phiên",
      len({s for s, _r, _c in kho.messages}) == 1 and len(kho.messages) == 2)
check("cli: đặt tiêu đề tự động", len(kho.titles) == 1)
check("cli: ghi nhật ký hội thoại vào Memory", len(nhat_ky) == 1)
check("cli: đẩy vào hàng đợi tự học", len(hoc) == 1)

luu = next((c for _s, r, c in kho.messages if r == "assistant"), "")
check("cli: bản lưu KHÔNG còn khối điều khiển thô",
      "JAVIS_ASK" not in luu and "<!--" not in luu)
check("cli: bản lưu vẫn giữ nội dung trả lời", "250k" in luu)
if nhat_ky:
    check("cli: nhật ký cũng sạch khối điều khiển", "JAVIS_ASK" not in nhat_ky[0][2])
if hoc:
    check("cli: corpus tự học cũng sạch khối điều khiển", "JAVIS_ASK" not in hoc[0][3])

# ---- Phiên Telegram bền qua nhiều lượt (không đẻ phiên mới mỗi tin) ----
asyncio.run(main._tg_answer("còn hôm qua?", {"chat_id": "555"}))
check("cli: lượt thứ hai vào ĐÚNG phiên cũ",
      len({s for s, _r, _c in kho.messages}) == 1 and len(kho.messages) == 4)
check("cli: hai chat khác nhau -> hai phiên khác nhau",
      (asyncio.run(main._tg_answer("chào", {"chat_id": "999"})) is not None)
      and len({s for s, _r, _c in kho.messages}) == 2)


# ================================================================
# 2. Telegram - nhánh API (OpenRouter)
# ================================================================
kho2, usage2, nhat_ky2, hoc2 = lap_gia("openrouter", "api", "sk-test", "x/y")


async def _api_gia(prov, key, model, messages, reasoning="off", brain=None):
    async def _gen():
        yield {"type": "meta", "model": "x/y-thuc"}
        yield {"type": "text", "content": "Xong rồi anh."}
        yield {"type": "usage", "input": 300, "output": 70}
    return _gen()


async def _compact_gia(msgs, prov, key, model, streamer):
    return msgs


main._api_stream_mcp = _api_gia
main.compaction.compact_mem = _compact_gia

kq2 = asyncio.run(main._tg_answer("tổng kết đi", {"chat_id": "777"}))
check("api: có trả lời", "Xong rồi anh." in ((kq2.get("text") if isinstance(kq2, dict) else "") or ""))
check("api: usage_store.record ĐƯỢC gọi", len(usage2) == 1)
if usage2:
    a, k = usage2[0]
    check("api: usage ghi đúng nhà cung cấp 'openrouter'", a and a[0] == "openrouter")
    check("api: usage ghi đúng token vào/ra (300/70)", 300 in a and 70 in a)
    check("api: usage ghi model THẬT do sự kiện meta báo về", "x/y-thuc" in a)
check("api: lưu đủ user + assistant vào kho phiên", len(kho2.messages) == 2)
check("api: ghi nhật ký + tự học", len(nhat_ky2) == 1 and len(hoc2) == 1)


# ================================================================
# 3. Đường lưu dùng chung: _persist_turn bóc khối điều khiển
# ================================================================
check("main._persist_turn tồn tại", callable(getattr(main, "_persist_turn", None)))

if callable(getattr(main, "_persist_turn", None)):
    kho3, _u3, nhat_ky3, hoc3 = lap_gia("anthropic-cli", "cli", "", "opus")
    asyncio.run(main._persist_turn(kho3, "sid-x", BRAIN, "hỏi gì đó", "Trả lời.\n\n" + ASK))
    luu3 = next((c for _s, r, c in kho3.messages if r == "assistant"), "")
    check("_persist_turn: bóc khối điều khiển trước khi vào kho phiên",
          "JAVIS_ASK" not in luu3 and "<!--" not in luu3)
    check("_persist_turn: giữ nội dung trả lời", "Trả lời." in luu3)
    check("_persist_turn: hạ khối ASK xuống câu hỏi đọc được",
          "Xem kỳ nào?" in luu3 and "1. Tuần này" in luu3)
    check("_persist_turn: nhật ký cũng sạch",
          nhat_ky3 and "JAVIS_ASK" not in nhat_ky3[0][2])
    check("_persist_turn: corpus tự học cũng sạch",
          hoc3 and "JAVIS_ASK" not in hoc3[0][3])
    check("_persist_turn: text rỗng thì KHÔNG lưu gì",
          (asyncio.run(main._persist_turn(kho3, "sid-x", BRAIN, "u", "")) is None)
          and len(kho3.messages) == 1)


# ================================================================
# 4. AST - nhánh dashboard phải đi qua ĐÚNG đường lưu đó
# ================================================================
src = (SERVER / "main.py").read_text(encoding="utf-8", errors="replace")
tree = ast.parse(src)
do_turn = next((n for n in ast.walk(tree)
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == "_do_turn"), None)
check("tìm thấy _do_turn trong main.py", do_turn is not None)

if do_turn is not None:
    goi = {n.func.id for n in ast.walk(do_turn)
           if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
    goi |= {n.func.attr for n in ast.walk(do_turn)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)}
    check("_do_turn gọi _persist_turn (dùng chung đường lưu)", "_persist_turn" in goi)
    check("_do_turn KHÔNG còn tự gọi log_conversation thẳng", "log_conversation" not in goi)
    check("_do_turn KHÔNG còn tự gọi auto_title thẳng", "auto_title" not in goi)

print()
if _fails:
    print(f"FAIL {len(_fails)} test: " + ", ".join(_fails))
    sys.exit(1)
print("TẤT CẢ PASS")
