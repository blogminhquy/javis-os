"""Tài khoản bot THUỘC MỘT BRAIN: đứng ở brain nào chỉ thấy tài khoản của brain đó.

    python tests/run.py tai_khoan_theo_brain      (KHÔNG mạng)

Chủ repo nói 21/09: "ở brain nào thì sẽ nhìn thấy tài khoản bot kênh đó kết nối", và đây là
bước đầu của hướng lớn hơn: chia quyền quản lý tài khoản cho brain / agent / skill / workflow /
chatbot, rồi mới lên được bản nhiều người dùng.

Tới 0.62.3 tài khoản kênh là TOÀN CỤC (không có trường brain nào), nên tab trộn tài khoản của
mọi brain. 0.62.4 thêm trường `brain` cho bản ghi tài khoản. Bốn luật phải giữ, tất cả đều là
loại hỏng lặng lẽ nếu sai:

  1. Thêm ở brain nào thì thuộc brain đó.
  2. Tài khoản CHƯA gán brain hiện ở MỌI brain. Nếu không thì một token có thật ngoài đời tồn
     tại mà không màn hình nào hiện ra, không ai xoá hay gắn lại được.
  3. Bot nhận tài khoản thì tài khoản nhận brain của bot. Từ 27/11/2026 form bot cho chọn kênh của MỌI brain (chủ repo:
     "phần sửa bot thêm kênh mới trong chatbot vẫn đang không nhìn thấy tất cả các kênh đã kết nối"), nên tick một kênh
     của brain khác vào bot là người dùng tự chuyển kênh đó sang brain của bot: hộp thư và tab Tài khoản bot đi theo
     bot đang trả lời. Sửa bot mà KHÔNG thêm kênh mới thì không đụng tới brain của kênh đã có.
  4. Không truyền brain (mã nội bộ, poller) thì vẫn trả HẾT như cũ.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import os
import sys
import tempfile

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-tkbrain-"))
os.environ.setdefault("BRAINS_DIR", tempfile.mkdtemp(prefix="javis-tkbrains-"))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import channel_accounts as ca  # noqa: E402
import chatbot_store  # noqa: E402

_fails = []


def check(name, cond, them=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(them) + "]") if them and not cond else ""))
    if not cond:
        _fails.append(name)


def ten(ds):
    return sorted(a["label"] for a in ds)


# ---- 1. Thêm ở brain nào thì thuộc brain đó -------------------------------------
a_shop, loi = ca.create_account({"channel": "telegram", "token": "1:shop",
                                 "label": "Shop", "brain": "/n/Shop"})
check("tạo tài khoản kèm brain", bool(a_shop) and not loi, loi)
a_kyluat, _ = ca.create_account({"channel": "telegram", "token": "2:kl",
                                 "label": "Kỷ luật", "brain": "/n/Kyluat"})
a_lolung, _ = ca.create_account({"channel": "telegram", "token": "3:ll", "label": "Lơ lửng"})

check("brain lưu đúng vào bản ghi", ca.get_account(a_shop).get("brain") == "/n/Shop",
      ca.get_account(a_shop))
check("không truyền brain thì để RỖNG, không đoán đại một brain nào",
      ca.get_account(a_lolung).get("brain") == "", ca.get_account(a_lolung))

# ---- 2. Lọc: của brain này + của chưa ai ----------------------------------------
check("ở brain Shop thấy tài khoản của Shop, KHÔNG thấy của Kỷ luật",
      ten(ca.list_accounts(brain="/n/Shop")) == ["Lơ lửng", "Shop"],
      ten(ca.list_accounts(brain="/n/Shop")))
check("ở brain Kỷ luật thấy của Kỷ luật, KHÔNG thấy của Shop",
      ten(ca.list_accounts(brain="/n/Kyluat")) == ["Kỷ luật", "Lơ lửng"],
      ten(ca.list_accounts(brain="/n/Kyluat")))
check("tài khoản chưa gán brain hiện ở MỌI brain (không có token nào tàng hình)",
      "Lơ lửng" in ten(ca.list_accounts(brain="/n/Shop"))
      and "Lơ lửng" in ten(ca.list_accounts(brain="/n/Brain-La")))
check("không truyền brain thì trả HẾT (mã nội bộ, poller dựa vào đó)",
      ten(ca.list_accounts()) == ["Kỷ luật", "Lơ lửng", "Shop"], ten(ca.list_accounts()))
check("lọc brain vẫn cộng dồn với lọc kênh",
      ca.list_accounts("zalo-bot", brain="/n/Shop") == [])

# ---- 3. Bot nhận tài khoản thì tài khoản nhận brain của bot ----------------------
bid, loi = chatbot_store.create_bot({"name": "Bot Lơ Lửng", "agent_slug": "ag",
                                     "brain": "/n/Kyluat", "account_ids": a_lolung})
check("tạo bot ôm tài khoản chưa có chủ", bool(bid) and not loi, loi)
check("tài khoản nhận brain của bot vừa ôm nó",
      ca.get_account(a_lolung).get("brain") == "/n/Kyluat", ca.get_account(a_lolung))
check("nhận chủ xong thì brain khác KHÔNG còn thấy nó nữa",
      "Lơ lửng" not in ten(ca.list_accounts(brain="/n/Shop")),
      ten(ca.list_accounts(brain="/n/Shop")))

# Người dùng tick kênh của brain khác vào bot (form giờ hiện mọi kênh): kênh chuyển sang brain của bot, nếu không thì
# hộp thư của brain bot giấu mất các cuộc chat bot đó đang trả lời (keys_of_other_brains lọc theo brain của kênh).
bid2, loi2 = chatbot_store.create_bot({"name": "Bot Shop", "agent_slug": "ag",
                                       "brain": "/n/Brain-Khac", "account_ids": a_shop})
check("tạo bot thứ hai", bool(bid2) and not loi2, loi2)
check("tick kênh của brain khác vào bot thì kênh sang brain của bot",
      ca.get_account(a_shop).get("brain") == "/n/Brain-Khac", ca.get_account(a_shop))
ca.update_account(a_shop, {"brain": "/n/Shop"})
ok2, loi2 = chatbot_store.update_bot(bid2, {"name": "Bot Shop 2"})
check("sửa bot mà không thêm kênh mới thì KHÔNG đụng tới brain của kênh đã có",
      ok2 and ca.get_account(a_shop).get("brain") == "/n/Shop", (loi2, ca.get_account(a_shop)))
ok2, loi2 = chatbot_store.update_bot(bid2, {"account_ids": [a_shop]})
check("lưu lại đúng danh sách kênh cũ cũng KHÔNG đụng tới brain của kênh",
      ok2 and ca.get_account(a_shop).get("brain") == "/n/Shop", (loi2, ca.get_account(a_shop)))
a_moi, _ = ca.create_account({"channel": "telegram", "token": "999:moi", "label": "Kênh mới", "brain": "/n/Shop"})
ok2, loi2 = chatbot_store.update_bot(bid2, {"account_ids": [a_shop, a_moi]})
check("sửa bot thêm một kênh của brain khác thì chỉ kênh MỚI sang brain của bot",
      ok2 and ca.get_account(a_moi).get("brain") == "/n/Brain-Khac" and ca.get_account(a_shop).get("brain") == "/n/Shop",
      (loi2, ca.get_account(a_moi), ca.get_account(a_shop)))
chatbot_store.update_bot(bid2, {"account_ids": [a_shop]})
ca.delete_account(a_moi)
chatbot_store.delete_bot(bid2)

# ---- 4. Chuyển brain bằng tay + gỡ chủ ------------------------------------------
ok, loi = ca.update_account(a_shop, {"brain": "/n/Kyluat"})
check("chuyển tài khoản sang brain khác", ok and ca.get_account(a_shop).get("brain") == "/n/Kyluat", loi)
ok, _ = ca.update_account(a_shop, {"brain": ""})
check("gỡ chủ thì quay lại hiện ở mọi brain",
      ok and "Shop" in ten(ca.list_accounts(brain="/n/Mot-Brain-Bat-Ky")))
ok, _ = ca.update_account(a_shop, {"label": "Shop 2"})
check("sửa nhãn mà KHÔNG gửi brain thì không đụng tới brain",
      ok and ca.get_account(a_shop).get("brain") == "")

# ---- 5. Di trú bản ghi cũ (không có trường brain) -------------------------------
import json  # noqa: E402
d = json.loads(ca.STORE_PATH.read_text(encoding="utf-8"))
for a in d["accounts"]:
    a.pop("brain", None)
ca.STORE_PATH.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
n = ca.dien_brain_con_thieu(lambda aid: "/n/Suy-Ra" if aid == a_kyluat else "")
check("di trú điền brain cho mọi bản ghi cũ", n == 3, n)
check("suy được từ bot thì lấy đúng brain đó",
      ca.get_account(a_kyluat).get("brain") == "/n/Suy-Ra")
check("không suy được thì để RỖNG chứ không đoán vào brain mặc định",
      ca.get_account(a_shop).get("brain") == "")
check("chạy lại di trú lần hai thì không còn gì để điền",
      ca.dien_brain_con_thieu(lambda aid: "/n/X") == 0)

# ---- 6. CANARY kiến trúc ---------------------------------------------------------
RT = (SERVER / "routes" / "channels.py").read_text(encoding="utf-8")
check("CANARY: route /channels/accounts nhận brain và cờ tat_ca",
      "async def channels_accounts(channel: str = \"\", brain: str = \"\", tat_ca: str = \"\")" in RT)
check("CANARY: Zalo cá nhân (kind=account) KHÔNG bị lọc mất theo brain",
      '"brain": "",   # kết nối ở trang Kết nối, không thuộc brain nào' in RT)
MAIN = (SERVER / "main.py").read_text(encoding="utf-8")
check("CANARY: form bot cho chọn kênh của MỌI brain, không lọc theo brain đang mở",
      "channel_accounts.list_accounts(brain=loc)" not in MAIN)
check("CANARY: di trú chạy lúc khởi động", "channel_accounts.dien_brain_con_thieu(" in MAIN)

print()
if _fails:
    print("THAT BAI " + str(len(_fails)) + ": " + ", ".join(_fails))
    sys.exit(1)
print("OK - test_tai_khoan_theo_brain: tat ca pass")
