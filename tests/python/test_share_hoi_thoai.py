"""Link chia sẻ một HỘI THOẠI (0.171.0).

    python tests/run.py share_hoi_thoai

Chủ repo 15/10/2026: chia sẻ cả đoạn hội thoại đang chat cho người khác đọc, giống link file và
quản lý chung ở trang Link chia sẻ. Đây là mặt tiền công khai thứ hai chạm vào dữ liệu riêng, nên
phần lớn test này là test an toàn:

  1. Chỉ câu hỏi và câu trả lời ra ngoài. Tool, khối ngữ cảnh máy chèn (file đính kèm có đường
     dẫn trên máy chủ, file đang ghim, ngữ cảnh giao diện) và khối điều khiển ẩn JAVIS_* bị gỡ.
  2. Link là ẢNH CHỤP tới lúc bấm: tin gõ SAU đó không tự lọt ra. Bấm lại thì dời mốc, giữ token.
  3. Ảnh chỉ đi qua được khi nằm trong attachments, và chỉ loại tài nguyên trình bày.
  4. Thu hồi là chết hẳn; trang không có script và mang header cách ly.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import os
import sys
import tempfile

_STATE = tempfile.mkdtemp(prefix="javis-share-ht-")
_BRAINS = tempfile.mkdtemp(prefix="javis-share-ht-brains-")
os.environ["JAVIS_STATE_DIR"] = _STATE
os.environ["BRAINS_DIR"] = _BRAINS

BRAIN = os.path.join(_BRAINS, "brain")
os.makedirs(os.path.join(BRAIN, "attachments"), exist_ok=True)
with open(os.path.join(BRAIN, "attachments", "anh.png"), "wb") as f:
    f.write(b"\x89PNG\r\n\x1a\n" + b"0" * 40)
with open(os.path.join(BRAIN, "attachments", "ghi.md"), "w", encoding="utf-8") as f:
    f.write("khong phai anh")
with open(os.path.join(BRAIN, "bi-mat.png"), "wb") as f:
    f.write(b"\x89PNG\r\n\x1a\n" + b"1" * 40)

from fastapi.testclient import TestClient   # noqa: E402
import share_store                          # noqa: E402
import main                                 # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

_fails = []


def check(name, cond, extra=None):
    print(("ok   " if cond else "FAIL ") + name + ("" if cond or extra is None else f"  [{extra}]"))
    if not cond:
        _fails.append(name)


cl = TestClient(main.app, base_url="http://localhost")
store = main.get_store()
SID = store.create_session(brain=BRAIN, title="Kế hoạch bán nước mắm")
store.append_message(SID, "user", "[File đính kèm để ĐỌC (đường dẫn):\n- /data/stage/bao-gia.pdf\n"
                                  "Mặc định: chỉ đọc file]\n\nGiá sỉ bao nhiêu?")
store.append_message(SID, "tool", "ket qua tool noi bo")
store.append_message(SID, "assistant", "Giá sỉ là **45k** một chai.\n\n![chai](attachments/anh.png)"
                                       "<!-- JAVIS_ASK: {\"question\":\"x\"} -->")
store.append_message(SID, "user", "> Giá sỉ là 45k một chai.\n\nVậy lấy 100 chai thì sao?")
store.append_message(SID, "assistant", "100 chai được giảm 5%.")

# ============ 1. Tạo link ============
check("chưa chia sẻ thì /share/chat/of trả rỗng",
      cl.get("/share/chat/of", params={"session_id": SID}).json().get("share") is None)
d = cl.post("/share/chat", json={"session_id": SID}).json()
TOK = d.get("token", "")
check("tạo được link hội thoại", d.get("ok") is True and len(TOK) >= 20, d)
check("trả đường dẫn tương đối /s/<token>", d.get("path") == "/s/" + TOK, d.get("path"))
check("/share/chat/of biết hội thoại đã có link",
      (cl.get("/share/chat/of", params={"session_id": SID}).json().get("share") or {}).get("token") == TOK)
check("hội thoại không tồn tại: báo lỗi, không tạo link",
      cl.post("/share/chat", json={"session_id": "khong-co"}).status_code == 400)

# ============ 2. Trang xem công khai ============
p = cl.get("/s/" + TOK)
body = p.text
check("mở được trang hội thoại", p.status_code == 200, p.status_code)
check("có tiêu đề hội thoại", "Kế hoạch bán nước mắm" in body)
check("có câu hỏi và câu trả lời", "Giá sỉ bao nhiêu?" in body and "<strong>45k</strong>" in body)
check("trích dẫn trong câu hỏi hiện thành khối trích dẫn", "<blockquote>" in body)
check("CANARY: khối file đính kèm (đường dẫn máy chủ) KHÔNG lộ ra", "/data/stage" not in body
      and "File đính kèm" not in body)
check("CANARY: kết quả tool KHÔNG lộ ra", "ket qua tool noi bo" not in body)
check("CANARY: khối điều khiển ẩn JAVIS_* KHÔNG lộ ra", "JAVIS_ASK" not in body)
check("trang không có script", "<script" not in body.lower())
check("header cách ly sandbox", p.headers.get("content-security-policy") == "sandbox")
check("ảnh trỏ qua chính token", f"/s/{TOK}/asset?p=attachments%2Fanh.png" in body)
check("/s/<token>/ (gạch cuối) chuyển về trang hội thoại",
      cl.get("/s/" + TOK + "/", follow_redirects=False).status_code == 307)

# ============ 3. Ảnh: chỉ attachments, chỉ tài nguyên ============
check("ảnh trong attachments xem được", cl.get(f"/s/{TOK}/asset", params={"p": "attachments/anh.png"}).status_code == 200)
check("CANARY: ảnh NGOÀI attachments không xem được",
      cl.get(f"/s/{TOK}/asset", params={"p": "bi-mat.png"}).status_code == 404)
check("CANARY: ghi chú trong attachments không xem được",
      cl.get(f"/s/{TOK}/asset", params={"p": "attachments/ghi.md"}).status_code == 404)
check("CANARY: leo thư mục không được",
      cl.get(f"/s/{TOK}/asset", params={"p": "../../etc/passwd"}).status_code == 404)
check("/raw của link hội thoại là 404", cl.get(f"/s/{TOK}/raw").status_code == 404)

# ============ 4. Ảnh chụp tới lúc bấm ============
store.append_message(SID, "user", "Câu riêng tư gõ sau khi gửi link")
store.append_message(SID, "assistant", "Trả lời riêng tư")
body = cl.get("/s/" + TOK).text
check("CANARY: tin gõ SAU khi chia sẻ không tự lọt ra", "riêng tư" not in body)
d2 = cl.post("/share/chat", json={"session_id": SID}).json()
check("bấm Chia sẻ lại: GIỮ đúng token cũ", d2.get("token") == TOK, d2)
check("bấm Chia sẻ lại: dời mốc, người cầm link thấy phần mới", "Câu riêng tư" in cl.get("/s/" + TOK).text)

# ============ 5. Quản lý ở trang Link chia sẻ ============
ds = cl.get("/share/list").json().get("items") or []
m = next((x for x in ds if x.get("token") == TOK), {})
check("link hội thoại có trong danh sách chia sẻ", bool(m))
check("đánh dấu loại hội thoại và tên theo tiêu đề", m.get("loai") == "hoi_thoai" and m.get("ten") == "Kế hoạch bán nước mắm", m)
r = cl.post("/share/rename", json={"token": TOK, "nhan": "Báo giá cho anh Linh"}).json()
check("đổi tên được", r.get("ok") and "Báo giá cho anh Linh" in cl.get("/s/" + TOK).text)
check("link file vẫn tạo riêng, không đụng link hội thoại",
      share_store.cua_file(BRAIN, "") is None)
check("thu hồi được", cl.post("/share/revoke", json={"token": TOK}).json().get("ok") is True)
check("thu hồi xong là 404", cl.get("/s/" + TOK).status_code == 404)
check("thu hồi xong /share/chat/of trả rỗng",
      cl.get("/share/chat/of", params={"session_id": SID}).json().get("share") is None)

print()
if _fails:
    print(f"ĐỎ {len(_fails)} mục: " + ", ".join(_fails))
    sys.exit(1)
print("Tất cả xanh.")
