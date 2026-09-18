"""Khung chat tải dần: mở hội thoại chỉ kéo phần đuôi, cuộn lên mới lấy khúc cũ hơn.

    python tests/run.py chat_tai_dan

Chủ repo báo 17/09: vào một cuộc chat siêu dài thì màn dựng cả nghìn bong bóng một lượt,
khựng vài giây rồi hay đứng lưng chừng thay vì rơi xuống câu trả lời gần nhất.

Hai chỗ dễ làm sai, và test này canh đúng hai chỗ đó:

1. `limit` PHẢI không bắt buộc. Rất nhiều đường khác trong server vẫn gọi get_messages để
   dựng ngữ cảnh cho engine; đổi mặc định thành "chỉ 30 tin cuối" là im lặng cắt trí nhớ
   của Javis giữa cuộc mà không ai thấy lỗi nào.

2. Con trỏ phải là CẶP (ts, id) chứ không chỉ mỗi id. Thứ tự hiển thị là `ORDER BY ts, id`,
   mà tin ghi bù (bot, việc nền) có id lớn trong khi mốc giờ nhỏ. Con trỏ chỉ có id sẽ nhảy
   cóc qua vài tin hoặc trả lại tin đã hiện - cả hai đều lặng thinh.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import os
import sys
import tempfile

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-taidan-"))

from fastapi.testclient import TestClient  # noqa: E402
import main  # noqa: E402
from sessions import get_store  # noqa: E402

fails = []


def check(name, cond, them=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(them) + "]") if not cond and them else ""))
    if not cond:
        fails.append(name)


BRAIN = tempfile.mkdtemp(prefix="javis-brain-taidan-")
st = get_store()
SID = "cuoc-sieu-dai"
st.get_or_create(SID, brain=BRAIN, engine="cli", model="x")
for i in range(100):
    st.append_message(SID, "user" if i % 2 == 0 else "assistant", f"tin so {i}")

c = TestClient(main.app, base_url="http://127.0.0.1")


def chu(ds):
    return [m["content"] for m in ds]


# ---- 1. Khuôn cũ không đổi ----------------------------------------------------
d = c.get(f"/sessions/{SID}").json()
check("không truyền limit thì vẫn trả CẢ hội thoại", len(d.get("messages", [])) == 100)
check("thiếu limit thì không kèm has_more (giữ nguyên khuôn cũ)", "has_more" not in d)
check("get_messages của kho phiên vẫn trả đủ", len(st.get_messages(SID)) == 100)

# ---- 2. Mở hội thoại: chỉ phần ĐUÔI ------------------------------------------
d = c.get(f"/sessions/{SID}?limit=30").json()
ds = d.get("messages", [])
check("limit=30 trả đúng 30 tin", len(ds) == 30)
check("và đó là 30 tin CUỐI", chu(ds)[0] == "tin so 70" and chu(ds)[-1] == "tin so 99")
check("xếp xuôi (cũ trước) để dựng bong bóng đúng thứ tự",
      [m["ts"] for m in ds] == sorted(m["ts"] for m in ds))
check("báo còn tin phía trên", d.get("has_more") is True)
check("kèm tổng số tin của cả cuộc", d.get("total") == 100)

# ---- 3. Cuộn lên: khúc cũ hơn -------------------------------------------------
dau = ds[0]
d2 = c.get(f"/sessions/{SID}/messages",
           params={"limit": 30, "before_ts": dau["ts"], "before_id": dau["id"]}).json()
ds2 = d2.get("messages", [])
check("khúc kế trả đúng 30 tin", len(ds2) == 30)
check("nối LIỀN ngay trước khúc trước, không sót không lặp",
      chu(ds2)[0] == "tin so 40" and chu(ds2)[-1] == "tin so 69")
check("vẫn còn tin phía trên", d2.get("has_more") is True)

# Kéo cho tới hết để chắc chắn con trỏ không đứng yên tại chỗ (vòng lặp vô hạn) và không bỏ sót.
gom, truoc, vong = [], ds2[0], 0
while vong < 20:
    vong += 1
    r = c.get(f"/sessions/{SID}/messages",
              params={"limit": 30, "before_ts": truoc["ts"], "before_id": truoc["id"]}).json()
    lo = r.get("messages", [])
    if not lo:
        break
    gom = lo + gom
    truoc = lo[0]
    if not r.get("has_more"):
        break
check("kéo tiếp tới đầu cuộc thì gom đủ 40 tin còn lại", len(gom) == 40, len(gom))
check("và đúng từ tin đầu tiên", chu(gom)[0] == "tin so 0" if gom else False)
check("vòng kéo dừng lại chứ không quay mãi", vong < 20, vong)

# ---- 4. Mốc giờ KHÔNG tăng đều -------------------------------------------------
# Tin ghi bù có id lớn mà ts nhỏ. Con trỏ chỉ dựa vào id sẽ trả lại chính tin đang hiện.
SID2 = "cuoc-lech-gio"
st.get_or_create(SID2, brain=BRAIN, engine="cli", model="x")
st.append_message(SID2, "user", "A")
st.append_message(SID2, "assistant", "B")
with st._lock:  # ghi thẳng một tin có id LỚN NHẤT nhưng mốc giờ SỚM NHẤT
    st._conn.execute("INSERT INTO messages (session_id, role, content, ts) VALUES (?,?,?,?)",
                     (SID2, "user", "Z-som-nhat", 1.0))
    st._conn.commit()
d3 = c.get(f"/sessions/{SID2}?limit=2").json()
ds3 = d3.get("messages", [])
check("tin mốc giờ sớm nhất không lọt vào khúc cuối dù id lớn nhất",
      chu(ds3) == ["A", "B"], chu(ds3))
d4 = c.get(f"/sessions/{SID2}/messages",
           params={"limit": 5, "before_ts": ds3[0]["ts"], "before_id": ds3[0]["id"]}).json()
check("cuộn lên lấy đúng tin ghi bù, không trả lại tin đang hiện",
      chu(d4.get("messages", [])) == ["Z-som-nhat"], chu(d4.get("messages", [])))
check("tới đầu cuộc thì has_more tắt", d4.get("has_more") is False)

# ---- 5. Ca biên ---------------------------------------------------------------
check("phiên không tồn tại trả 404", c.get("/sessions/khong-co-that/messages").status_code == 404)
st.get_or_create("cuoc-rong", brain=BRAIN, engine="cli", model="x")
d5 = c.get("/sessions/cuoc-rong?limit=30").json()
check("cuộc chưa có tin nào: rỗng và không còn gì phía trên",
      d5.get("messages") == [] and d5.get("has_more") is False and d5.get("total") == 0)
check("thiếu con trỏ thì rơi về khúc cuối, không nổ",
      chu(c.get(f"/sessions/{SID}/messages", params={"limit": 3}).json()["messages"])
      == ["tin so 97", "tin so 98", "tin so 99"])

print("")
if fails:
    print(f"ĐỎ {len(fails)} mục")
    sys.exit(1)
print("Tất cả xanh.")
