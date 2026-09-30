"""Hòm thư: "Trả lời giúp tin này" và "Gợi ý câu trả lời" (0.65.5), POST /conversations/{id}/ai-reply.

    python tests/run.py hoi_thoai_tra_loi_giup      (KHÔNG mạng: engine và kênh gửi đều là đồ giả)

Chủ dự án (2026-09-30): muốn nhanh chóng chọn cho bot tự trả lời ngay trong hòm thư khi đang đúng chế độ. Bản này canh những chỗ
DỄ HỎNG của một hành động chủ bấm tay, chạy Agent thật của bot ngoài luồng poller:
  1. gửi: bot trả lời đúng tin khách cuối, gửi qua kênh đúng kiểu nhóm, ghi vào Hộp thư như lời của BOT, cuộc chat VẪN ở Tự động,
     và tin khách KHÔNG bị ghi trùng.
  2. nháp: không gửi, không ghi Hộp thư, chạy với ghi_kho=False, và luôn dọn dấu vết phiên (kể cả khi engine ném lỗi).
  3. chỉ đúng chế độ mới gửi: đang tiếp quản, bot tắt, tin cuối không phải của khách, đang có lượt khác chạy, thì từ chối kèm mã lý do.
  4. lỗi không nuốt: Agent chọn im, engine hỏng, gửi hỏng (trả chữ đã soạn để chủ gửi tay), và không bao giờ kẹt khoá "đang soạn".
  5. dạy bot: tin mà bộ phán xử đã chọn im thì gửi xong gắn nhãn "im nhầm" nặng nhất.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import os
import sys
import tempfile
import time

_STATE = tempfile.mkdtemp(prefix="javis-httlg-")
os.environ["JAVIS_STATE_DIR"] = _STATE
os.environ["JAVIS_ALLOWED_HOSTS"] = "testserver"
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import channels  # noqa: E402
import chatbot_reply_policy_store as rps  # noqa: E402
import chatbot_runtime  # noqa: E402
import chatbot_store  # noqa: E402
import conversations  # noqa: E402
import routes.conversations as cr  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
import main  # noqa: E402

_fails = []


def check(name, cond, them=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(them) + "]") if them and not cond else ""))
    if not cond:
        _fails.append(name)


# ---- đồ giả ----
ENGINE = []          # mỗi lần lõi được gọi: (text, meta, kwargs)
GUI = []             # mỗi lần gửi qua kênh
PROBE = []           # bản nháp hỏi phiên
UNDO = []            # bản nháp dọn dấu vết
MODE = {"engine": "ok", "gui": "ok"}


async def fake_answer(text, meta=None, progress=None, **kw):
    ENGINE.append((text, dict(meta or {}), dict(kw)))
    if MODE["engine"] == "boom":
        raise RuntimeError("engine ném lỗi")
    if MODE["engine"] == "str":
        return "Lượt hỏng: hết hạn mức"
    if MODE["engine"] == "silent":
        return {"text": "[IM_LANG]", "files": []}
    return {"text": "Dạ gói tháng bên em là 490.000đ ạ", "files": []}


async def fake_gui(kenh, tk, chat_id, text, chat_type="private"):
    GUI.append({"kenh": kenh, "tk": dict(tk), "chat": chat_id, "text": text, "type": chat_type})
    if MODE["gui"] == "fail":
        return False, "Zalo từ chối: phiên hết hạn"
    return True, ""


channels.gui = fake_gui
ECHO = []           # mỗi lần nhớ tiếng vọng của câu bot vừa gửi (Zalo cá nhân)
import zalo_personal_channel as _zc  # noqa: E402
_zc.ghi_da_gui = lambda conn, thread, text: ECHO.append((conn, thread, text))
chatbot_runtime.wire(answer=fake_answer, brain_root=lambda b: _STATE, read_agent=lambda b, s: ({}, ""),
                     session_probe=lambda key: (PROBE.append(key) or ("sid-nhap", 5)),
                     session_undo=lambda key, keep: UNDO.append((key, keep)))
RUN = {"on": True}
cr._DEPS.bot_status = lambda bid: {"running": RUN["on"]}

bot, _ = chatbot_store.create_bot({"name": "Nhi Mai", "agent_slug": "a", "brain": "brain", "reply_when": "auto"})
NOW = time.time()


def tin(chat, gui, text, typ="group", bot_id=None, ext="", dt=0):
    r = conversations.ghi_su_kien({
        "channel": "zalo_personal", "account_id": "zp1", "account_name": "Nick", "bot_id": bot if bot_id is None else bot_id,
        "external_chat_id": chat, "chat_type": typ, "chat_title": "Nhóm " + chat if typ == "group" else "",
        "sender_type": gui, "sender_id": "u" + chat if gui == "customer" else "", "sender_name": "Lan" if gui == "customer" else "Nhi Mai",
        "text": text, "external_message_id": ext, "created_at": NOW - dt})
    return r["conversation_id"]


def dem(cid, loai):
    return sum(1 for m in conversations.tin_nhan(cid) if m["sender_type"] == loai)


def reset():
    ENGINE.clear(); GUI.clear(); PROBE.clear(); UNDO.clear(); ECHO.clear()
    MODE["engine"] = MODE["gui"] = "ok"
    RUN["on"] = True
    chatbot_runtime._MANUAL_BUSY.clear()


cl = TestClient(main.app)


def post(cid, mode="send"):
    return cl.post(f"/conversations/{cid}/ai-reply", data={"mode": mode})


# ============================================================
# 1. Gửi
# ============================================================
reset()
c1 = tin("g1", "customer", "Chị ơi cho em hỏi giá gói tháng", ext="m1", dt=30)
r = post(c1)
j = r.json()
check("gửi: 200, bot trả lời đúng câu Agent soạn", r.status_code == 200 and j["ok"] and j["text"].startswith("Dạ gói tháng"), r.text)
check("Agent chạy MỘT lần trên đúng tin khách cuối, lượt thật (không phải nháp): ghi_kho không bị tắt",
      len(ENGINE) == 1 and "giá gói tháng" in ENGINE[0][0] and "ghi_kho" not in ENGINE[0][2], ENGINE)
m = ENGINE[0][1]
check("meta dựng đúng như poller cấp: nhóm, tên nhóm, người hỏi, id tin, tài khoản; đánh dấu được gọi",
      m["chat_type"] == "group" and m["chat_title"] == "Nhóm g1" and m["user_name"] == "Lan" and m["message_id"] == "m1"
      and m["account_id"] == "zp1" and m["mentioned"] is True and m["chat_id"] == "g1", m)
check("gửi qua kênh đúng kiểu nhóm, đúng cuộc chat", len(GUI) == 1 and GUI[0]["type"] == "group" and GUI[0]["chat"] == "g1"
      and GUI[0]["text"].startswith("Dạ gói tháng"), GUI)
check("nhóm Zalo cá nhân: Agent được báo ai đang nói (cả nhóm chung một mạch)", ENGINE[0][0].startswith("[Lan] "), ENGINE[0][0])
check("Zalo cá nhân: nhớ tiếng vọng của câu bot vừa gửi TRƯỚC khi gửi (không thì vòng đọc tưởng chủ nhắn tay hay khách nói, bot tự đáp chính mình)",
      ECHO == [("zp1", "g1", GUI[0]["text"])], ECHO)
check("câu bot vào Hộp thư như lời của BOT (không phải người thật)", dem(c1, "ai") == 1 and dem(c1, "human") == 0)
check("tin khách KHÔNG bị ghi trùng", dem(c1, "customer") == 1)
check("cuộc chat VẪN ở Tự động (khác gửi tay là tiếp quản)", conversations.chi_tiet(c1)["mode"] == "ai")
check("và bản nháp không hề bị gọi", PROBE == [] and UNDO == [])

# ============================================================
# 2. Nháp
# ============================================================
reset()
c2 = tin("g2", "customer", "ai biết đặt lịch không", dt=20)
r = post(c2, "draft")
j = r.json()
check("nháp: 200, trả chữ để đổ vào ô nhập", r.status_code == 200 and j["ok"] and j.get("draft") is True and j["text"].startswith("Dạ gói tháng"))
check("nháp KHÔNG gửi gì và KHÔNG ghi Hộp thư", GUI == [] and dem(c2, "ai") == 0 and dem(c2, "human") == 0 and ECHO == [])
check("nháp chạy với ghi_kho=False và đọc phiên đang nói làm ngữ cảnh (chỉ đọc)",
      ENGINE[0][2].get("ghi_kho") is False and ENGINE[0][2].get("phien_kho") == "sid-nhap", ENGINE[0][2])
check("nháp dọn dấu vết phiên về đúng độ dài lịch sử trước đó", UNDO == [(f"bot:{bot}:g2", 5)], UNDO)

reset()
MODE["engine"] = "boom"
r = post(c2, "draft")
check("nháp mà engine ném lỗi: 502 có mã engine", r.status_code == 502 and r.json()["code"] == "engine", r.text)
check("và VẪN dọn dấu vết phiên, VẪN nhả khoá đang soạn", UNDO == [(f"bot:{bot}:g2", 5)] and not chatbot_runtime._MANUAL_BUSY)

# ============================================================
# 3. Chỉ đúng chế độ mới gửi
# ============================================================
reset()
c3 = tin("g3", "customer", "ai đó giúp mình", dt=10)
conversations.dat_che_do(c3, "human")
r = post(c3)
check("đang tiếp quản: gửi bị từ chối, mã human, không chạy Agent", r.status_code == 409 and r.json()["code"] == "human" and ENGINE == [] and GUI == [])
r = post(c3, "draft")
check("nhưng gợi ý câu trả lời vẫn dùng được khi đang tiếp quản (đó là lúc cần nhất)", r.status_code == 200 and r.json()["ok"], r.text)

reset()
RUN["on"] = False
c4 = tin("g4", "customer", "bot tắt thì sao", dt=10)
r = post(c4)
check("bot đang tắt: từ chối, mã bot_off", r.status_code == 409 and r.json()["code"] == "bot_off" and ENGINE == [])

reset()
c5 = tin("g5", "customer", "hỏi", dt=20)
tin("g5", "ai", "dạ đây ạ", dt=10)
r = post(c5)
check("tin cuối là của bot: từ chối, mã already_answered (khỏi nói lần hai)", r.status_code == 409 and r.json()["code"] == "already_answered" and ENGINE == [])

reset()
c6 = tin("g6", "customer", "đang có lượt khác", dt=10)
chatbot_runtime._MANUAL_BUSY.add(c6)
r = post(c6)
check("đang có lượt nhờ-bot chạy dở cho cuộc chat này: từ chối, mã busy (không chạy chồng)", r.status_code == 409 and r.json()["code"] == "busy")
chatbot_runtime._MANUAL_BUSY.clear()

reset()
c7 = tin("g7", "customer", "không có bot", bot_id="", dt=10)
check("cuộc chat không có bot: 400 no_bot", post(c7).status_code == 400 and post(c7).json()["code"] == "no_bot")
check("cuộc chat không tồn tại: 404", cl.post("/conversations/999999/ai-reply", data={"mode": "send"}).status_code == 404)
check("mode lạ: 400", cl.post(f"/conversations/{c1}/ai-reply", data={"mode": "xoa"}).status_code == 400)

# ============================================================
# 4. Lỗi không nuốt
# ============================================================
reset()
MODE["engine"] = "silent"
c8 = tin("g8", "customer", "chuyện của thành viên", dt=10)
r = post(c8)
check("Agent chọn im: ok, silent, không gửi và không ghi gì", r.status_code == 200 and r.json()["silent"] is True and GUI == [] and dem(c8, "ai") == 0)

reset()
MODE["engine"] = "str"
c9 = tin("g9", "customer", "lượt hỏng", dt=10)
r = post(c9)
check("lõi trả chuỗi lỗi: 502, lý do nguyên văn cho chủ, KHÔNG gửi cho khách", r.status_code == 502 and "hết hạn mức" in r.json()["error"] and GUI == [] and dem(c9, "ai") == 0)

reset()
MODE["gui"] = "fail"
c10 = tin("g10", "customer", "gửi hỏng", dt=10)
r = post(c10)
j = r.json()
check("gửi hỏng: 400 mã send_failed, TRẢ CHỮ đã soạn để chủ gửi tay", r.status_code == 400 and j["code"] == "send_failed" and j["text"].startswith("Dạ gói tháng")
      and "phiên hết hạn" in j["error"], j)
check("và KHÔNG ghi thành lời bot đã nói (khách chưa hề nhận)", dem(c10, "ai") == 0 and not chatbot_runtime._MANUAL_BUSY)

# ============================================================
# 5. Dạy bot
# ============================================================
reset()
c11 = tin("g11", "customer", "Chị ơi cho em hỏi giá gói tháng", dt=40)
did = rps.log_decision({"bot_id": bot, "chat_id": "g11", "ts": NOW - 39, "text": "giá gói tháng", "verdict": "silent", "candidate": True,
                        "silence_code": "below_threshold", "mode": "on", "score": 0.5, "threshold": 0.6}, NOW - 39)
r = post(c11)
j = r.json()
check("tin mà bộ phán xử đã chọn im: gửi xong báo taught", r.status_code == 200 and j["taught"] is True, r.text)
check("quyết định im được gắn nhãn 'im nhầm' nặng nhất", rps.get_decision(did)["label"] == "missed" and rps.get_decision(did)["label_weight"] == 1.5,
      rps.get_decision(did))

reset()
c12 = tin("g12", "customer", "tin không có quyết định im nào", dt=40)
r = post(c12)
check("không có quyết định im thì không dạy (taught false) nhưng vẫn gửi bình thường", r.status_code == 200 and r.json()["taught"] is False and len(GUI) == 1)

# ============================================================
# 6. Giao diện cần biết bot có chạy không
# ============================================================
reset()
check("GET messages trả bot_running theo trạng thái thật của bot", cl.get(f"/conversations/{c1}/messages").json()["bot_running"] is True)
RUN["on"] = False
check("bot tắt thì bot_running là false", cl.get(f"/conversations/{c1}/messages").json()["bot_running"] is False)
check("cuộc chat không bot thì bot_running là false", cl.get(f"/conversations/{c7}/messages").json()["bot_running"] is False)

# ============================================================
# 7. Đường gửi tay của chủ không đổi
# ============================================================
reset()
c13 = tin("g13", "customer", "gõ tay", dt=10)
r = cl.post(f"/conversations/{c13}/reply", data={"text": "Dạ em xin lỗi ạ"})
check("chủ gõ tay KHÔNG đi qua nhớ-tiếng-vọng của bot (hành vi cũ giữ nguyên)", ECHO == [])
check("chủ gõ tay vẫn tiếp quản như cũ (refactor gom đường gửi không đổi hành vi)",
      r.status_code == 200 and r.json()["tiep_quan"] is True and GUI[0]["text"] == "Dạ em xin lỗi ạ" and GUI[0]["type"] == "group"
      and conversations.chi_tiet(c13)["mode"] == "human" and dem(c13, "human") == 1)

print()
if _fails:
    print(f"{len(_fails)} FAIL")
    sys.exit(1)
print("ALL PASS")
