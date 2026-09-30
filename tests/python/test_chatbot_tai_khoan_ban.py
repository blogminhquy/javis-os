"""Form Bot mới hiện cả kênh đang do bot khác trực (0.65.9), GET /chatbots -> `tai_khoan_ban`.

    python tests/run.py chatbot_tai_khoan_ban      (KHÔNG mạng)

Chủ dự án (2026-09-30): "để đỡ phải lựa chọn chatbot vào kênh nào đó nó bị khó hiểu". Trước đây form giấu hẳn kênh đang có bot trực,
nên người dùng thấy một kênh "biến mất" mà không biết vì sao. Từ 0.65.9 form hiện chúng mờ, kèm tên bot (và brain nếu khác brain đang
mở) đang giữ. Server cấp danh sách đó; hai chỗ dễ hỏng:
  1. `tai_khoan` (kênh RẢNH, tick được) và `tai_khoan_ban` (kênh có bot) phải là hai tập KHÔNG giao nhau, hợp lại là mọi kênh của brain,
     nếu không một kênh vừa hiện tick được vừa hiện khoá, hoặc biến mất.
  2. Lọc theo brain như cũ: kênh của brain khác không lọt vào danh sách của brain đang mở (kênh chưa gán brain thì hiện ở mọi brain),
     nhưng kênh Ở brain này mà bot giữ nó nằm brain khác thì vẫn hiện khoá kèm `bot_brain` khác.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import os
import sys
import tempfile

_STATE = tempfile.mkdtemp(prefix="javis-tkban-")
os.environ["JAVIS_STATE_DIR"] = _STATE
os.environ["JAVIS_ALLOWED_HOSTS"] = "testserver"
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import channel_accounts  # noqa: E402
import chatbot_store  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
import main  # noqa: E402

fails = []


def check(name, cond, them=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(them) + "]") if them and not cond else ""))
    if not cond:
        fails.append(name)


def acc(label, ext, brain="A", channel="telegram"):
    aid, loi = channel_accounts.create_account({"channel": channel, "token": "1:" + ext, "label": label,
                                                "external_id": ext, "brain": brain})
    assert aid, loi
    return aid


def bot(name, brain, account_ids):
    bid, loi = chatbot_store.create_bot({"name": name, "agent_slug": "tro-ly", "brain": brain, "agent_brain": brain,
                                         "account_ids": account_ids, "muc_quyen": "suggest"})
    assert bid, loi
    return bid


A_RANH = acc("Kênh rảnh", "ranh_bot")
A_NHI = acc("Kênh của Nhi", "nhi_bot")
A_KHAC = acc("Kênh brain B", "khac_bot", brain="B")
A_CHUNG = acc("Kênh chưa gán brain", "chung_bot", brain="")
A_LAN_BRAIN_KHAC = acc("Kênh brain A do bot B giữ", "lan_bot", brain="A")
B_NHI = bot("Nhi Mai", "A", A_NHI)
B_LAN = bot("Lan", "B", A_LAN_BRAIN_KHAC)      # bot ở brain B giữ kênh nằm ở brain A (dữ liệu lệch có thật, xem routes/channels.py)

cl = TestClient(main.app)
d = cl.get("/chatbots", params={"brain": "A"}).json()
ranh = {a["id"] for a in d["tai_khoan"]}
ban = {a["id"]: a for a in d["tai_khoan_ban"]}

check("kênh rảnh của brain A tick được", A_RANH in ranh, ranh)
check("kênh chưa gán brain hiện ở mọi brain và tick được", A_CHUNG in ranh)
check("kênh của brain B không lọt vào danh sách của brain A", A_KHAC not in ranh and A_KHAC not in ban)
check("kênh có bot KHÔNG còn nằm trong danh sách tick được", A_NHI not in ranh and A_LAN_BRAIN_KHAC not in ranh)
check("kênh có bot nằm trong danh sách khoá", A_NHI in ban and A_LAN_BRAIN_KHAC in ban, list(ban))
check("CANARY: hai danh sách không giao nhau (không kênh nào vừa tick được vừa khoá)", not (ranh & set(ban)), ranh & set(ban))
check("khoá ghi đúng bot đang giữ", ban[A_NHI]["bot_id"] == B_NHI and ban[A_NHI]["bot_name"] == "Nhi Mai" and ban[A_NHI]["bot_brain"] == "A", ban[A_NHI])
check("bot giữ kênh nằm ở brain KHÁC thì `bot_brain` nói ra (giao diện ghi tên brain đó)",
      ban[A_LAN_BRAIN_KHAC]["bot_name"] == "Lan" and ban[A_LAN_BRAIN_KHAC]["bot_brain"] == "B", ban[A_LAN_BRAIN_KHAC])
check("mỗi dòng khoá có đủ trường để vẽ (kênh, nhãn, tên phía nền tảng)",
      all(k in ban[A_NHI] for k in ("id", "channel", "label", "external_id", "bot_id", "bot_name", "bot_brain")))
check("TUYỆT ĐỐI không lộ token ra giao diện", all("token" not in str(a).lower().replace("token_set", "") for a in d["tai_khoan_ban"]))

d2 = cl.get("/chatbots", params={"brain": "B"}).json()
check("đứng ở brain B: thấy kênh brain B (rảnh) và kênh chưa gán, không thấy kênh của brain A",
      {a["id"] for a in d2["tai_khoan"]} == {A_KHAC, A_CHUNG}, {a["id"] for a in d2["tai_khoan"]})

check("không dùng em dash trong file này", chr(0x2014) not in open(__file__, encoding="utf-8").read())

if fails:
    print("\nFAIL - test_chatbot_tai_khoan_ban: " + str(len(fails)) + " lỗi: " + ", ".join(fails))
    sys.exit(1)
print("\nOK - test_chatbot_tai_khoan_ban: tất cả pass")
