"""Sổ đăng ký kênh + tài khoản kênh + trả lời khách từ Javis (Chatbot V2, 0.61.0).

    python tests/run.py kenh_tai_khoan      (KHÔNG mạng)

Bốn thứ file này canh, đều là loại hỏng lặng lẽ:

1. **Sổ đăng ký kênh** (`server/channels`): kho bot, kho hội thoại và bộ giám sát đều đọc từ
   MỘT sổ; năng lực suy từ chính module (có hàm `gui` mới có "trả lời từ Javis").
2. **Di trú**: bot cũ giữ token TRONG bản ghi -> tài khoản kênh id = id bot, token còn nguyên,
   hội thoại cũ vẫn khớp khoá `kenh:bot_id`, và token KHÔNG còn nằm trong chatbots.json.
3. **Một bot nhiều tài khoản**: mỗi tài khoản một poller, lượt qua tài khoản nào thì ghi vào
   kho theo tài khoản đó; tài khoản đang bot khác trực thì không gắn được (409 là cả hai chết).
4. **API chung cho mọi kênh**: /channels, /channels/accounts một khuôn, watch chỉ cho kênh
   tài khoản, xoá từ chối khi còn bot trực; /conversations/{id}/reply gửi qua sổ, ghi tin
   `human`, và TIẾP QUẢN cuộc chat có bot.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import json
import os
import sys
import tempfile

_STATE = tempfile.mkdtemp(prefix="javis-kenh-")
os.environ["JAVIS_STATE_DIR"] = _STATE

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from config import STATE_DIR  # noqa: E402
import secrets_store  # noqa: E402

# Bản ghi bot CŨ (trước 0.61.0) đặt sẵn TRƯỚC khi nạp kho, để test đúng đường di trú.
STATE_DIR.mkdir(parents=True, exist_ok=True)
(STATE_DIR / "chatbots.json").write_text(json.dumps({"version": 1, "bots": [
    {"id": "bot_cu1", "name": "Bot cũ", "agent": {"brain": "b", "slug": "cskh"}, "brain": "b",
     "channel": "zalo", "bot_username": "BotCu", "token_enc": secrets_store.encrypt("9:cu"),
     "enabled": False, "groups": [], "created_at": 1, "updated_at": 1}]}), encoding="utf-8")

import channels  # noqa: E402
import channel_accounts  # noqa: E402
import chatbot_runtime  # noqa: E402
import chatbot_store  # noqa: E402
import conversations  # noqa: E402

_fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)


# ============================================================
# 1. Sổ đăng ký kênh
# ============================================================
check("sổ có ba kênh đầu: Zalo Bot, Zalo cá nhân, Telegram",
      set(channels.ids()) == {"zalo", "zalo_personal", "telegram"})
check("kênh gắn được bot = kênh có Transport", set(channels.bot_ids()) == {"zalo", "telegram"})
check("kho bot, kho hội thoại đọc CÙNG sổ",
      set(chatbot_store.KENH) == set(channels.bot_ids()) and set(conversations.KENH) == set(channels.ids()))
check("mặc định kênh bot vẫn là Telegram (bản ghi cũ không có channel là bot Telegram)",
      chatbot_store.KENH_DEFAULT == "telegram")
zp = channels.spec("zalo_personal")
check("Zalo cá nhân là kênh kind=account, có công tắc ghi, có trả lời từ Javis",
      zp and zp.kind == "account" and zp.nl("ghi_theo_cong_tac") and zp.nl("tra_loi_tu_javis"))
tg = channels.spec("telegram")
check("Telegram: kind=bot, có nhóm, gửi file, trả lời từ Javis",
      tg and tg.kind == "bot" and tg.nl("nhom") and tg.nl("gui_file") and tg.nl("tra_loi_tu_javis"))
ui = channels.cho_giao_dien()
check("bản cho giao diện có logo, nhãn, năng lực, cách lấy token (giao diện không đoán theo id)",
      all(k in ui[0] for k in ("id", "nhan", "logo", "kind", "nang_luc", "lay_token", "tom_tat")))
check("kênh lạ: gui() trả lỗi chứ không ném",
      asyncio.run(channels.gui("viber", {}, "1", "x"))[0] is False)

# ============================================================
# 2. Di trú bot cũ
# ============================================================
b = chatbot_store.get_bot("bot_cu1")
check("CANARY: bot cũ có đúng một tài khoản, id = id bot",
      [a["id"] for a in b["accounts"]] == ["bot_cu1"] and b["token_set"] is True)
check("token còn nguyên sau di trú", chatbot_store.get_token("bot_cu1") == "9:cu")
raw = json.loads((STATE_DIR / "chatbots.json").read_text(encoding="utf-8"))
check("token KHÔNG còn trong chatbots.json, bot chỉ trỏ qua accounts",
      "token_enc" not in raw["bots"][0] and raw["bots"][0]["accounts"] == ["bot_cu1"])
raw_tk = (STATE_DIR / "channel_accounts.json").read_text(encoding="utf-8")
check("token ở kho tài khoản vẫn mã hoá, không dạng thô", "9:cu" not in raw_tk)
check("channel/bot_username của bot là ảnh của tài khoản",
      b["channel"] == "zalo" and b["bot_username"] == "BotCu")
conversations.ghi_su_kien({"channel": "zalo", "account_id": "bot_cu1", "bot_id": "bot_cu1",
                           "external_chat_id": "c9", "sender_type": "customer", "sender_id": "c9",
                           "sender_name": "K", "text": "hi"})
check("hội thoại cũ khớp khoá kênh:bot_id nên tiếp quản vẫn đọc đúng",
      conversations.che_do("zalo", "bot_cu1", "c9") == "ai")

# ============================================================
# 3. Tài khoản kênh: tạo, trùng, gắn bot, một tài khoản một bot
# ============================================================
aid, err = channel_accounts.create_account({"channel": "telegram", "token": "3:t", "label": "TG", "external_id": "tgb"})
check("tạo tài khoản token Telegram", bool(aid) and aid.startswith("acc_") and not err)
_, err = channel_accounts.create_account({"channel": "telegram", "token": "3:t2", "external_id": "@TGB"})
check("cùng tên bot trên cùng kênh thì từ chối (409 là cả hai poller chết)", "đã có" in err)
_, err = channel_accounts.create_account({"channel": "zalo_personal", "token": "x"})
check("kênh không nhận token thì từ chối kèm danh sách kênh có", "không gắn được" in err)
check("tài khoản công khai KHÔNG kèm token", "token_enc" not in channel_accounts.get_account(aid))

ok, err = chatbot_store.update_bot("bot_cu1", {"account_ids": ["bot_cu1", aid]})
check("bot trực HAI tài khoản (Zalo Bot + Telegram)",
      ok and [a["channel"] for a in chatbot_store.get_bot("bot_cu1")["accounts"]] == ["zalo", "telegram"])
bid2, err = chatbot_store.create_bot({"name": "Bot 2", "agent_slug": "cskh", "brain": "b", "account_ids": aid})
check("tài khoản đang bot khác trực thì bot mới KHÔNG gắn được", bid2 is None and "đang do bot" in err)
bid2, err = chatbot_store.create_bot({"name": "Bot 2", "agent_slug": "cskh", "brain": "b",
                                      "token": "4:z", "channel": "zalo", "bot_username": "BotHai"})
check("dán token mới lúc tạo bot -> tài khoản mới sinh ra và gắn vào bot",
      bool(bid2) and chatbot_store.get_bot(bid2)["accounts"][0]["external_id"] == "BotHai")
check("token_owner tìm ra bot đang giữ tên bot đó theo kênh",
      (chatbot_store.token_owner("bothai", channel="zalo") or {}).get("id") == bid2)
check("bots_using_account", [x["id"] for x in chatbot_store.bots_using_account(aid)] == ["bot_cu1"])

# ============================================================
# 4. Bộ giám sát: mỗi tài khoản một poller, lượt ghi đúng tài khoản
# ============================================================
class FakeT:
    def __init__(self, token, chat_id, answer_fn, command_fn=None, **kw):
        self.token = token; self.answer_fn = answer_fn; self.command_fn = command_fn; self.kw = kw
        self._task = None; self.status = "off"; self.last_error = ""

    def start(self):
        self.status = "polling"
        self._task = type("T", (), {"done": lambda s: False})()

    def stop(self):
        self.status = "stopped"


for k in ("zalo", "telegram"):
    channels.module(k).Transport = FakeT


async def _ans(text, meta=None, progress=None, channel="", bot=None):
    return {"text": f"[{channel}] ok", "files": []}


chatbot_runtime.wire(answer=_ans, brain_root=lambda b: _STATE, read_agent=lambda b, s: ({}, ""))
ok, err = chatbot_runtime.start_bot("bot_cu1")
run = chatbot_runtime._RUNNING.get("bot_cu1") or {}
check("bật bot -> hai poller, mỗi tài khoản một", ok and set(run.get("pollers", {})) == {"bot_cu1", aid})
st = chatbot_runtime.status("bot_cu1")
check("trạng thái gộp: running, kèm từng tài khoản",
      st["state"] == "running" and sorted(x["account_id"] for x in st["accounts"]) == sorted(["bot_cu1", aid]))
tb = run["pollers"][aid]
out = asyncio.run(tb.answer_fn("hỏi", {"chat_id": "77", "chat_type": "private", "user_name": "Lan", "message_id": 1}))
check("lượt qua poller Telegram gọi engine với kênh telegram", out.get("text") == "[telegram] ok")
ds = conversations.danh_sach(bot_id="bot_cu1")
check("CANARY: hội thoại ghi theo ĐÚNG tài khoản nhận tin (telegram:acc_...), không theo id bot",
      any(d["channel"] == "telegram" and d["channel_account_id"] == f"telegram:{aid}" for d in ds))
res = asyncio.run(tb.command_fn("help", "", "77", {"chat_id": "77", "message_id": 2}))
tin = conversations.tin_nhan([d for d in ds if d["channel"] == "telegram"][0]["id"])
check("lệnh qua poller cũng vào đúng tài khoản", res.get("reply") and tin[-2]["text"] == "/help")
check("precheck của poller nhận meta có tài khoản và cho qua chat riêng",
      tb.kw["precheck_fn"]("x", {"chat_id": "77", "chat_type": "private"}) is None)
# poller Telegram lỗi -> thẻ bot đỏ dù poller Zalo vẫn chạy
tb.status = "error"; tb.last_error = "401 Unauthorized"
st = chatbot_runtime.status("bot_cu1")
check("một tài khoản lỗi thì trạng thái chung là lỗi, kèm lý do", st["state"] == "error" and "401" in st["last_error"])
check("tắt bot dừng mọi poller", chatbot_runtime.stop_bot("bot_cu1") and chatbot_runtime.status("bot_cu1")["state"] == "off")

# ============================================================
# 5. API: /channels, /channels/accounts, watch, delete, reply
# ============================================================
import main  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

c = TestClient(main.app, base_url="http://127.0.0.1")
r = c.get("/channels")
check("GET /channels trả sổ đăng ký", r.status_code == 200 and {x["id"] for x in r.json()["channels"]} == set(channels.ids()))
r = c.get("/channels/accounts")
acc = r.json()["accounts"]
check("GET /channels/accounts: MỘT khuôn cho mọi kênh (cùng bộ khoá)",
      r.status_code == 200 and len(acc) >= 3 and all(
          set(("id", "account_key", "kind", "channel", "logo", "label", "state", "watch", "bot_id",
               "so_hoi_thoai", "chua_doc", "nang_luc", "xoa_duoc")) <= set(a) for a in acc))
tk_tg = [a for a in acc if a["id"] == aid][0]
check("tài khoản bot: kind=bot, bot trực đúng tên, có số hội thoại",
      tk_tg["kind"] == "bot" and tk_tg["bot_id"] == "bot_cu1" and tk_tg["so_hoi_thoai"] >= 1 and tk_tg["watch"] is None)
r = c.post(f"/channels/accounts/{aid}/watch", data={"on": "1"})
check("tài khoản bot KHÔNG có công tắc ghi (400 nói rõ)", r.status_code == 400 and "đang bật" in r.json()["error"])
r = c.post(f"/channels/accounts/{aid}/delete")
check("xoá tài khoản còn bot trực -> từ chối", r.status_code == 400 and "đang do bot" in r.json()["error"])


async def _fake_verify(tok):
    return {"ok": True, "username": "moibot", "bot_name": "Mới"}


channels.module("telegram").verify_token = _fake_verify
r = c.post("/channels/verify-token", data={"channel": "telegram", "token": "5:m"})
check("verify-token qua module kênh", r.json().get("ok") and r.json()["username"] == "moibot")
r = c.post("/channels/accounts", data={"channel": "telegram", "token": "5:m", "label": "Mới"})
aid3 = r.json().get("id")
check("POST /channels/accounts chưa có tên thì tự kiểm rồi tạo", bool(aid3) and r.json()["account"]["external_id"] == "moibot")
r = c.post("/channels/verify-token", data={"channel": "telegram", "token": "5:m"})
check("token đã là tài khoản rảnh -> chỉ về tài khoản đó thay vì báo trùng bot",
      r.json().get("ok") is False and r.json().get("account_id") == aid3)
r = c.post(f"/channels/accounts/{aid3}/delete")
check("xoá tài khoản rảnh -> ok", r.status_code == 200 and channel_accounts.get_account(aid3) is None)
r = c.post("/chatbots/verify-token", data={"channel": "telegram", "token": "5:m"})
check("đường cũ /chatbots/verify-token vẫn chạy (bí danh)", r.json().get("ok") is True)

# reply
sent = []


async def _fake_gui(tk, chat_id, text, chat_type="private"):
    sent.append((tk.get("token"), chat_id, text, chat_type))
    return True, ""


channels.module("telegram").gui = _fake_gui
conv = [d for d in conversations.danh_sach(bot_id="bot_cu1") if d["channel"] == "telegram"][0]
r = c.post(f"/conversations/{conv['id']}/reply", data={"text": "Dạ có ạ"})
check("reply: gửi bằng token của tài khoản, đúng chat, ok", r.json().get("ok") and sent == [("3:t", "77", "Dạ có ạ", "private")])
check("reply: tin vào kho là tin human, và TIẾP QUẢN cuộc có bot",
      r.json().get("tiep_quan") is True and conversations.chi_tiet(conv["id"])["mode"] == "human"
      and conversations.tin_nhan(conv["id"])[-1]["sender_type"] == "human")
r = c.post(f"/conversations/{conv['id']}/reply", data={"text": "   "})
check("reply tin rỗng -> 400", r.status_code == 400)


async def _bad_gui(tk, chat_id, text, chat_type="private"):
    return False, "chat not found"


channels.module("telegram").gui = _bad_gui
truoc = len(conversations.tin_nhan(conv["id"]))
r = c.post(f"/conversations/{conv['id']}/reply", data={"text": "x"})
check("gửi hỏng -> 400 kèm lý do, KHÔNG ghi tin vào kho",
      r.status_code == 400 and "chat not found" in r.json()["error"] and len(conversations.tin_nhan(conv["id"])) == truoc)
r = c.get("/conversations/channels")
check("bí danh cũ /conversations/channels trả cùng khuôn tài khoản", r.status_code == 200 and "accounts" in r.json())

# Nguồn: không em dash
for f in ("channels/__init__.py", "channels/telegram.py", "channels/zalo_bot.py", "channels/zalo_personal.py",
          "channel_accounts.py", "routes/channels.py"):
    check(f"{f} không dùng em dash", "\u2014" not in (SERVER / f).read_text(encoding="utf-8"))

if _fails:
    print(f"\nĐỎ {len(_fails)} mục: " + ", ".join(_fails))
    sys.exit(1)
print("\nOK - test_kenh_tai_khoan: tất cả pass")
