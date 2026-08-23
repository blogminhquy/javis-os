"""Hội thoại Telegram phải HIỆN ở thanh bên dashboard, không chỉ nằm im trong DB.

    python tests/run.py phien_telegram_hien        (KHÔNG mạng)

Người dùng báo 23/08: "bản mới hình như nó không lưu session chat mới từ Telegram". Lưu thì
vẫn lưu đủ - `_tg_answer` gọi `append_message` mỗi lượt - nhưng danh sách không thấy đâu.

Nguyên nhân: cột `sessions.brain` giữ NGUYÊN VĂN chuỗi mà chỗ tạo phiên truyền vào, và mỗi
kênh viết một kiểu cho CÙNG một brain:

  - dashboard gửi tên gọi tắt "brain" cho brain mặc định (app.js::currentBrainPath),
  - Telegram `/brain` lưu ĐƯỜNG DẪN TUYỆT ĐỐI (`_tg_set_brain` nhận `hit["path"]` từ
    /brains, mà endpoint đó trả path tuyệt đối cho MỌI brain, kể cả brain mặc định),
  - loop config lưu kiểu thứ ba tuỳ người dùng đặt.

`/sessions` lọc `WHERE s.brain = ?` bằng đúng một chuỗi, nên hai bên không bao giờ gặp nhau.

Bản vá có hai nửa và test này khoá cả hai:
  1. GHI khoá chuẩn (`main._brain_key`) → phiên MỚI của mọi kênh nằm chung một khoá.
  2. ĐỌC theo bí danh (`main._brain_keys` + `sessions.loc_brain`) → phiên CŨ đã lệch vẫn
     hiện lên, không cần migration nào.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401  - nạp server/ vào sys.path
import os
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix="javis-tgside-")
os.environ.setdefault("JAVIS_STATE_DIR", _TMP)
os.environ.setdefault("BRAINS_DIR", os.path.join(_TMP, "brains"))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from sessions import SessionStore, loc_brain  # noqa: E402
import main  # noqa: E402

_fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)


# ============================================================
# 1) loc_brain: một chuỗi hay danh sách bí danh, và "không lọc"
# ============================================================
check("không truyền brain thì KHÔNG lọc", loc_brain(None) == ("", []))
check("chuỗi rỗng cũng KHÔNG lọc", loc_brain("") == ("", []))
check("một chuỗi → so bằng", loc_brain("brain") == ("s.brain = ?", ["brain"]))

cond, params = loc_brain(["brain", "/brains/Brain Default"])
check("danh sách → IN (...)", cond == "s.brain IN (?,?)")
check("danh sách giữ đủ tham số", params == ["brain", "/brains/Brain Default"])
check("danh sách bỏ trùng và bỏ rỗng",
      loc_brain(["brain", "brain", "", None]) == ("s.brain = ?", ["brain"]))
check("đổi được tên cột", loc_brain("brain", cot="x.brain")[0] == "x.brain = ?")


# ============================================================
# 2) _brain_key / _brain_keys
# ============================================================
mac_dinh = main._brain_key("brain")
check("khoá chuẩn của brain mặc định là đường dẫn tuyệt đối", os.path.isabs(mac_dinh))
check("tên gọi tắt và đường dẫn cho ra CÙNG một khoá", main._brain_key(mac_dinh) == mac_dinh)

keys = main._brain_keys("brain")
check("bí danh của 'brain' có cả tên gọi tắt", "brain" in keys)
check("bí danh của 'brain' có cả đường dẫn tuyệt đối", mac_dinh in keys)

keys_path = main._brain_keys(mac_dinh)
check("đi từ ĐƯỜNG DẪN cũng ra đủ bí danh (chiều ngược lại)",
      "brain" in keys_path and mac_dinh in keys_path)
check("không truyền gì thì không lọc", main._brain_keys("") == [])

# Brain KHÁC brain mặc định không được kéo theo bí danh "brain" - lọc brain A mà ra hội
# thoại của brain B là trộn hai bộ não, tệ hơn hẳn lỗi đang chữa.
khac = os.path.join(_TMP, "brains", "Brain Khac")
os.makedirs(khac, exist_ok=True)
check("brain khác KHÔNG mang bí danh 'brain'", "brain" not in main._brain_keys(khac))


# ============================================================
# 3) Ca thật: Telegram lưu đường dẫn, dashboard hỏi "brain"
# ============================================================
st = SessionStore(os.path.join(_TMP, "side.db"))

# Phiên CŨ (trước bản vá): Telegram đã ghi đường dẫn tuyệt đối.
cu = st.create_session(brain=mac_dinh, engine="cli", model="opus", channel="telegram")
st.append_message(cu, "user", "doanh thu hom nay the nao")

# Phiên MỚI: đi qua đúng đường Telegram thật.
sess = {"cli": None, "codex": None, "or": None, "last": None, "sent": set(), "brain": None}
moi = main._tg_conv_sid(st, sess, mac_dinh, "cli", "opus")
st.append_message(moi, "user", "chot don gium anh")

# Và một phiên web bình thường.
web = st.get_or_create(None, brain=main._brain_key("brain"), engine="cli", model="opus")
st.append_message(web, "user", "chao Javis")

thay = {s["id"] for s in st.list_sessions(brain=main._brain_keys("brain"))}
check("thanh bên (brain='brain') thấy phiên Telegram CŨ", cu in thay)
check("thanh bên (brain='brain') thấy phiên Telegram MỚI", moi in thay)
check("thanh bên vẫn thấy phiên web", web in thay)

check("phiên Telegram mới ghi khoá chuẩn", st.get_session(moi)["brain"] == mac_dinh)
check("phiên web ghi CÙNG khoá với phiên Telegram",
      st.get_session(web)["brain"] == st.get_session(moi)["brain"])

# Bộ lọc một chuỗi (hành vi cũ) vẫn phải bỏ sót - đó chính là bằng chứng lỗi có thật.
sot = {s["id"] for s in st.list_sessions(brain="brain")}
check("bằng chứng lỗi cũ: lọc bằng ĐÚNG một chuỗi thì mất sạch phiên Telegram",
      cu not in sot and moi not in sot)

# Tìm kiếm đi cùng một luật, không thì "không thấy ở thanh bên nhưng tìm ra" lại là một
# kiểu lệch khác cũng khó hiểu như nhau.
hit = {r["session_id"] for r in st.search("doanh thu", brain=main._brain_keys("brain"))}
check("ô tìm kiếm cũng thấy phiên Telegram cũ", cu in hit)

# Brain khác vẫn phải sạch.
rieng = st.create_session(brain=main._brain_key(khac), engine="cli", model="opus",
                          channel="telegram")
st.append_message(rieng, "user", "viec cua brain khac")
check("lọc brain mặc định KHÔNG kéo theo hội thoại của brain khác",
      rieng not in {s["id"] for s in st.list_sessions(brain=main._brain_keys("brain"))})
check("lọc brain khác thì thấy đúng hội thoại của nó",
      {s["id"] for s in st.list_sessions(brain=main._brain_keys(khac))} == {rieng})

print()
if _fails:
    print("FAILED (%d): %s" % (len(_fails), ", ".join(_fails)))
    sys.exit(1)
print("ALL PASS")
