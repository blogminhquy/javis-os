"""Hội thoại của bot chuyên trách nằm trong LỊCH SỬ CỦA AGENT (0.65.0), không còn ở Trò chuyện.

    python tests/run.py bot_sessions_in_agent_history      (KHÔNG mạng)

Chủ dự án (2026-09-30): "các đoạn hội thoại đang nằm ở Trò chuyện, anh muốn chuyển thành các đoạn phản
hồi lại nằm trong lịch sử của agent được nối với chatbot". Phiên của bot mang kênh `bot:<tên>`; trước
bản này chỉ các kênh cộng sự (`agent:`, `workflow:`, `coding:`) bị loại khỏi lịch sử Trò chuyện nên phiên
bot lọt vào đó.

Ba thứ được canh:
  1. TRÒ CHUYỆN không còn thấy phiên bot (và vẫn thấy chat thường).
  2. LỊCH SỬ CỦA AGENT thấy phiên của MỌI bot dùng Agent đó, cộng cuộc chủ tự chat với Agent; KHÔNG thấy
     phiên của bot dùng Agent khác.
  3. Ô tìm ở lịch sử Agent cũng vậy (không nhảy ra khỏi trợ lý đang mở).
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import os
import sys
import tempfile
from pathlib import Path

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-botsess-")
os.environ["JAVIS_ALLOWED_HOSTS"] = "testserver"       # xem test_workflow_runs_api.py
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import chatbot_store  # noqa: E402
import sessions  # noqa: E402

_fails = []


def check(name, cond, them=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(them) + "]") if them and not cond else ""))
    if not cond:
        _fails.append(name)


store = sessions.SessionStore(Path(tempfile.mkdtemp(prefix="sess-")) / "s.db")
mk = lambda ch, title: store.create_session(brain="brain", engine="cli", title=title, channel=ch)  # noqa: E731
web = mk("web", "chat thường của chủ")
tg = mk("telegram", "chat telegram")
own = mk("agent:lan", "chủ chat với Lan")
bot1 = mk("bot:javis-vu", "khách nhắn Javis Vũ")
bot2 = mk("bot:nhi-mai", "khách nhắn Nhi Mai")
wf = mk("workflow:viet-bai", "chạy quy trình")
cod = mk("coding:repo", "coding")
for sid, txt in ((web, "đổi bộ não ở đâu"), (own, "đổi bộ não giúp mình"), (bot1, "khách hỏi đổi bộ não thế nào"),
                 (bot2, "khách hỏi đổi bộ não của Nhi Mai")):
    store.append_message(sid, "user", txt)


def ids(rows):
    return {r["id"] for r in rows}


# 1. Trò chuyện
chat = ids(store.list_sessions(limit=50, brain=["brain"]))
check("Trò chuyện vẫn thấy chat thường và Telegram", {web, tg} <= chat, chat)
check("Trò chuyện KHÔNG thấy phiên bot", not ({bot1, bot2} & chat), chat)
check("Trò chuyện vẫn không thấy kênh cộng sự (như cũ)", not ({own, wf, cod} & chat))
check("vòng tự học (channel='*') vẫn thấy mọi phiên, kể cả bot",
      {web, own, bot1, bot2, wf, cod} <= ids(store.list_sessions(limit=50, brain=["brain"], channel="*")))

# 2. Lịch sử Agent
hist = ids(store.list_sessions(limit=50, brain=["brain"], channel="agent:lan", also_channels=["bot:javis-vu"]))
check("lịch sử Agent thấy cuộc chủ chat và phiên của bot dùng Agent đó", hist == {own, bot1}, hist)
check("không thấy phiên của bot dùng Agent KHÁC", bot2 not in hist)
check("không truyền kênh phụ thì như cũ (chỉ cuộc chủ chat)",
      ids(store.list_sessions(limit=50, brain=["brain"], channel="agent:lan")) == {own})
two = ids(store.list_sessions(limit=50, brain=["brain"], channel="agent:lan", also_channels=["bot:javis-vu", "bot:nhi-mai"]))
check("nhiều bot cùng dùng một Agent thì thấy hết", two == {own, bot1, bot2}, two)

# 3. Tìm kiếm
res = {r["session_id"] for r in store.search("đổi bộ não", brain=["brain"], channel="agent:lan", also_channels=["bot:javis-vu"])}
check("tìm trong lịch sử Agent: thấy phiên chủ và phiên bot của Agent đó", res == {own, bot1}, res)
res = {r["session_id"] for r in store.search("đổi bộ não", brain=["brain"], channel="agent:lan")}
check("tìm không kênh phụ thì như cũ", res == {own}, res)
res = {r["session_id"] for r in store.search("đổi bộ não", brain=["brain"])}
check("tìm ở Trò chuyện vẫn tìm mọi kênh (giữ hành vi cũ)", {web, own, bot1, bot2} <= res, res)

# 4. Ánh xạ Agent -> kênh bot ở tầng endpoint
import main  # noqa: E402

b1, err = chatbot_store.create_bot({"name": "Javis Vũ", "agent_slug": "lan", "brain": "brain"})
b2, err2 = chatbot_store.create_bot({"name": "Nhi Mai", "agent_slug": "hoa", "brain": "brain"})
check("(chuẩn bị) tạo hai bot dùng hai Agent khác nhau", b1 and b2 and not err and not err2, (err, err2))
k = main._kenh_bot_cua_agent("brain", "agent:lan")
slug1 = chatbot_store.get_bot(b1)["slug"]
check("kênh bot của Agent lan là đúng kênh phiên của bot đó (bot:<slug>)", k == ["bot:" + slug1], k)
check("Agent không có bot nào thì không thêm gì", main._kenh_bot_cua_agent("brain", "agent:khong-ai-dung") == [])
check("kênh không phải agent: thì không gộp gì", main._kenh_bot_cua_agent("brain", "workflow:viet-bai") == []
      and main._kenh_bot_cua_agent("brain", "") == [] and main._kenh_bot_cua_agent("brain", None) == [])
b3, err3 = chatbot_store.create_bot({"name": "Bot Brain Riêng", "agent_slug": "lan", "brain": "brain-rieng"})
check("(chuẩn bị) một bot cùng Agent nhưng ở brain RIÊNG", b3 and not err3, err3)
k2 = main._kenh_bot_cua_agent("brain", "agent:lan")
check("bot ở brain khác thì không lẫn vào lịch sử của brain đang mở", k2 == ["bot:" + slug1], k2)
k3 = main._kenh_bot_cua_agent("brain-rieng", "agent:lan")
check("và lịch sử của brain riêng có kênh bot của nó", "bot:" + chatbot_store.get_bot(b3)["slug"] in k3, k3)

# 5. Endpoint: gộp phiên bot là OPT-IN. Lúc trang Cộng sự chọn "phiên gần nhất để mở tiếp" (limit=1) mà lẫn phiên
#    của khách vào thì tin chủ gõ sẽ rơi vào cuộc chat của khách.
from fastapi.testclient import TestClient  # noqa: E402

cl = TestClient(main.app)
ms = main.get_store()
own2 = ms.create_session(brain="brain", engine="cli", title="chủ chat với Lan", channel="agent:lan")
ms.append_message(own2, "user", "đổi bộ não giúp mình")
bot_s = ms.create_session(brain="brain", engine="cli", title="khách nhắn Javis Vũ", channel="bot:" + slug1)
ms.append_message(bot_s, "user", "khách hỏi đổi bộ não")
r = cl.get("/sessions", params={"brain": "brain", "channel": "agent:lan", "limit": 1}).json()["sessions"]
check("mặc định (chọn phiên để mở tiếp): CHỈ phiên của chính Agent, dù phiên bot mới hơn", [x["id"] for x in r] == [own2], r)
r = cl.get("/sessions", params={"brain": "brain", "channel": "agent:lan", "limit": 20, "bots": 1}).json()["sessions"]
check("bots=1 (cột lịch sử): gộp cả phiên bot của Agent đó", {x["id"] for x in r} == {own2, bot_s}, [x["id"] for x in r])
r = cl.get("/sessions", params={"brain": "brain", "limit": 50}).json()["sessions"]
check("danh sách Trò chuyện qua endpoint: không có phiên bot", bot_s not in {x["id"] for x in r})
r = cl.get("/sessions/search", params={"q": "đổi bộ não", "brain": "brain", "channel": "agent:lan"}).json()["results"]
check("tìm mặc định: chỉ phiên của Agent", {x["session_id"] for x in r} == {own2}, r)
r = cl.get("/sessions/search", params={"q": "đổi bộ não", "brain": "brain", "channel": "agent:lan", "bots": 1}).json()["results"]
check("tìm bots=1: gộp phiên bot", {x["session_id"] for x in r} == {own2, bot_s}, r)

# 6. Giao diện: nhãn Bot trong lịch sử Agent
js = (ROOT / "dashboard" / "sessions-ui.js").read_text(encoding="utf-8")
check("giao diện: phiên bot trong lịch sử Agent mang nhãn sess.bot_badge",
      'window.t("sess.bot_badge")' in js and 'indexOf("bot:") === 0' in js)
check("giao diện: chỉ cột lịch sử và ô tìm của Agent xin gộp phiên bot (bots=1)",
      js.count('"&bots=1"') == 2 and 'indexOf("agent:") === 0' in js)
ws = (ROOT / "dashboard" / "workspace.js").read_text(encoding="utf-8")
check("trang Cộng sự chọn phiên để mở tiếp KHÔNG xin gộp phiên bot", "&limit=1" in ws and "bots=" not in ws)
import json  # noqa: E402
for lang in ("vi", "en"):
    d = json.loads((ROOT / "dashboard" / "i18n" / f"{lang}.json").read_text(encoding="utf-8"))
    check(f"i18n {lang} có sess.bot_badge", bool(d.get("sess.bot_badge")))

# 7. Phiên của bot trong NHÓM mang tên NHÓM (chủ dự án 2026-09-30: xem lịch sử toàn "[Minh Quý] @Javis Vũ ..." rất loạn)
gs = ms.create_session(brain="brain", engine="cli", title="", channel="bot:" + slug1)
ms.append_message(gs, "user", "[Minh Quý] @Javis Vũ hầy")
check("(chuẩn bị) phiên nhóm chưa có tên: tiêu đề hiện đang là tin đầu",
      next(x for x in ms.list_sessions(limit=50, brain=["brain"], channel="*") if x["id"] == gs)["preview"].startswith("[Minh Quý]"))
check("đặt tên phiên theo tên nhóm", ms.name_group_session(gs, "  Lớp Javis   OS ") is True
      and ms.get_session(gs)["title"] == "Lớp Javis OS", ms.get_session(gs))
check("đã có tên thì KHÔNG ghi đè (kể cả tên chủ tự đặt)", ms.name_group_session(gs, "Nhóm khác") is False
      and ms.get_session(gs)["title"] == "Lớp Javis OS")
gs2 = ms.create_session(brain="brain", engine="cli", title="", channel="bot:" + slug1)
check("nhóm chưa có tiêu đề: không đặt gì, để lượt sau đặt kịp",
      ms.name_group_session(gs2, "") is False and ms.name_group_session(gs2, None) is False
      and ms.name_group_session(gs2, "   ") is False and not (ms.get_session(gs2)["title"] or ""))
check("lượt sau biết tên nhóm thì đặt được", ms.name_group_session(gs2, "Nhóm mới") is True)
check("phiên không tồn tại thì không sập", ms.name_group_session("khong-co", "Nhóm") is False)
check("tên dài bị cắt 80 ký tự", ms.name_group_session(ms.create_session(brain="brain", engine="cli", title="", channel="bot:x"),
                                                        "N" * 300) is True)
src_main = (SERVER / "main.py").read_text(encoding="utf-8")
i_answer = src_main.index("async def _tg_answer(")
check("vỏ _tg_answer đặt tên phiên bot theo nhóm, chỉ với bot và tin nhóm",
      "if bot and chatbot_runtime._rp_is_group(meta):" in src_main[i_answer:i_answer + 12000]
      and "name_group_session(conv_sid" in src_main[i_answer:i_answer + 12000])
import chatbot_runtime  # noqa: E402
check("chỉ tin nhóm mới đổi tên phiên: chat riêng của khách vẫn theo tin đầu như cũ",
      chatbot_runtime._rp_is_group({"chat_type": "group"}) is True and chatbot_runtime._rp_is_group({"chat_type": "private"}) is False
      and chatbot_runtime._rp_is_group({}) is False)

print()
if _fails:
    print(f"{len(_fails)} FAIL")
    sys.exit(1)
print("ALL PASS")
