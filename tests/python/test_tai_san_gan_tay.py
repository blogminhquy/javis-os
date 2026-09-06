"""Tài liệu & link NGƯỜI DÙNG TỰ GẮN vào một cuộc trò chuyện.

    python tests/run.py tai_san_gan_tay

Chủ repo báo 05/09: khung "Trong cuộc trò chuyện này" đã tự dò ra file và link, nhưng không
có đường nào để tự thêm vào - trong khi khung Project ngay bên cạnh thì có.

Ba quyết định đáng canh, vì cả ba đều có cách làm sai trông hợp lý hơn:

1. TRỘN hai nguồn lúc đọc, không thay thế. Máy vẫn dò như cũ (bắt được cả cuộc chat từ tháng
   trước), người vẫn gắn được thứ máy không dò ra (file Javis ghi lặng lẽ giữa lượt). Trùng
   nhau thì bản GẮN TAY thắng: chỉ nó mới có id để gỡ và ghim.

2. Brain lấy từ PHIÊN, không nhận từ client - y hệt luật của route project. Cho client khai
   brain là mở đường cho một cuộc trỏ sang file của brain khác, phá rào `_safe_path` bằng
   DỮ LIỆU chứ không bằng lỗi code, nên không rào nào bắt được.

3. Gắn tay thì Javis phải THẤY. Không bơm vào system prompt thì nút thêm file chỉ là một danh
   sách để ngắm: người dùng gắn bảng giá vào rồi hỏi ngay, và Javis trả lời như chưa hề thấy.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-gantay-"))

from fastapi.testclient import TestClient  # noqa: E402
import main  # noqa: E402
import sessions as sessions_mod  # noqa: E402
from sessions import get_store  # noqa: E402

fails = []


def check(name, cond, them=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(them) + "]") if not cond and them else ""))
    if not cond:
        fails.append(name)


# Brain riêng trong thư mục tạm, cùng lối cô lập như test_tai_san_cuoc_chat: ghi vào brain
# mặc định là rải file thật vào `brains/` của người chạy lẫn của CI.
BRAIN = tempfile.mkdtemp(prefix="javis-brain-gantay-")
broot = Path(BRAIN)
# KHOÁ trần duyệt vào đúng brain này. Không đặt thì `_files_ceiling` cho localhost trần tới cả
# ổ đĩa (chủ máy tin cậy), đường dẫn tương đối tính từ "/" chứ không từ brain, và test sẽ đo
# nhầm một cấu hình khác hẳn cấu hình mà giao diện đang chạy.
os.environ["JAVIS_FILES_ROOT"] = BRAIN
(broot / "06 - Sources").mkdir(parents=True, exist_ok=True)
(broot / "06 - Sources" / "bang-gia.md").write_text("Nước mắm 500ml: 120k", encoding="utf-8")
(broot / "06 - Sources" / "brief.md").write_text("Brief landing", encoding="utf-8")
(broot / "06 - Sources" / "anh.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 16)
(broot / "05 - Projects").mkdir(parents=True, exist_ok=True)
(broot / "05 - Projects" / "ke-hoach.md").write_text("# Kế hoạch", encoding="utf-8")

st = get_store()
SID = "cuoc-gan-tay"
st.get_or_create(SID, brain=BRAIN, engine="cli", model="x")
st.append_message(SID, "assistant",
                  "Xong rồi:\n- [Kế hoạch quý 4](05 - Projects/ke-hoach.md)\n"
                  "Tham khảo https://moc-viet.vn/bang-gia nhé.")

c = TestClient(main.app, base_url="http://127.0.0.1")
API = f"/sessions/{SID}/assets"

# ============================================================
# 1. Thêm file: đi qua rào đường dẫn, và phải có thật
# ============================================================
r = c.post(API + "/files", data={"path": "06 - Sources/bang-gia.md"})
check("thêm được file có thật trong brain", r.status_code == 200 and r.json().get("ok"), r.text)
FID = r.json().get("id")

check("file không có trong brain thì từ chối",
      c.post(API + "/files", data={"path": "06 - Sources/khong-co.md"}).status_code == 404)
# Rào path là thứ duy nhất chặn một cuộc trỏ ra ngoài brain. Nó phải nói KHÔNG ngay ở cửa ghi,
# không phải để lỗi nổ lúc đọc.
check("đường dẫn trèo ra ngoài trần bị chặn",
      c.post(API + "/files", data={"path": "../../etc/passwd"}).status_code == 400)
# Đường dẫn rỗng giải ra chính thư mục trần, mà thư mục thì "có tồn tại" - không chặn thì gắn
# được một hàng trỏ vào một cái thư mục, ghim vào thì đọc lỗi.
check("đường dẫn rỗng bị từ chối", c.post(API + "/files", data={"path": ""}).status_code == 404)
check("thư mục cũng bị từ chối",
      c.post(API + "/files", data={"path": "06 - Sources"}).status_code == 404)
check("phiên không tồn tại trả 404",
      c.post("/sessions/khong-co-that/assets/files",
             data={"path": "06 - Sources/bang-gia.md"}).status_code == 404)
check("thêm CÙNG file lần hai trả lại id cũ, không đẻ bản ghi trùng",
      c.post(API + "/files", data={"path": "06 - Sources/bang-gia.md"}).json().get("id") == FID
      and len(st.list_session_files(SID)) == 1)

# ============================================================
# 2. Thêm link: chỉ http/https
# ============================================================
r = c.post(API + "/links", data={"url": "https://elegant.vn/", "label": "Mẫu tham khảo"})
check("thêm được link", r.status_code == 200 and r.json().get("ok"), r.text)
LID = r.json().get("id")
# Không rào thì `javascript:` lọt vào danh sách rồi hiện thành liên kết bấm được ngay trong
# giao diện - một cái bẫy XSS do chính người dùng tự dán vào.
check("javascript: bị từ chối",
      c.post(API + "/links", data={"url": "javascript:alert(1)"}).status_code == 400)
check("file: bị từ chối", c.post(API + "/links", data={"url": "file:///etc/passwd"}).status_code == 400)

# ============================================================
# 3. Danh sách TRỘN hai nguồn
# ============================================================
d = c.get(API + "?brain=" + BRAIN).json()
fs = {f["name"]: f for f in d["files"]}
check("file gắn tay có trong danh sách", "bang-gia.md" in fs)
check("và được đánh dấu là gắn tay (có id để gỡ/ghim)",
      fs.get("bang-gia.md", {}).get("manual") is True and fs.get("bang-gia.md", {}).get("id") == FID)
check("file Javis tự dò ra vẫn còn nguyên", "ke-hoach.md" in fs)
check("và KHÔNG bị đánh dấu gắn tay", fs.get("ke-hoach.md", {}).get("manual") is False)
# Thứ mình chủ động gắn vào phải nằm chỗ mắt nhìn trước.
check("phần gắn tay đứng TRƯỚC phần tự dò", d["files"][0]["manual"] is True)
check("có đường dẫn theo gốc brain để hiện cho người đọc",
      fs.get("bang-gia.md", {}).get("brain_path") == "06 - Sources/bang-gia.md")
ls = {l["url"]: l for l in d["links"]}
check("link gắn tay có, kèm nhãn",
      ls.get("https://elegant.vn/", {}).get("manual") is True
      and ls.get("https://elegant.vn/", {}).get("label") == "Mẫu tham khảo")
check("link Javis dò ra vẫn còn", ls.get("https://moc-viet.vn/bang-gia", {}).get("manual") is False)

# Gắn tay ĐÚNG file mà máy cũng dò ra: chỉ được hiện MỘT hàng, và phải là hàng gắn tay -
# hàng tự dò không có id nên bấm gỡ không được, người dùng tưởng nút hỏng.
c.post(API + "/files", data={"path": "05 - Projects/ke-hoach.md"})
d2 = c.get(API + "?brain=" + BRAIN).json()
trung = [f for f in d2["files"] if f["name"] == "ke-hoach.md"]
check("file vừa gắn tay vừa được dò ra chỉ hiện MỘT hàng", len(trung) == 1, len(trung))
check("và hàng đó là bản gắn tay (có nút gỡ)", trung and trung[0].get("manual") is True)
c.post(API + "/files/" + trung[0]["id"] + "/delete")

# ============================================================
# 4. Ảnh, và file đã dời đi
# ============================================================
c.post(API + "/files", data={"path": "06 - Sources/anh.png"})
d3 = c.get(API + "?brain=" + BRAIN).json()
check("ảnh gắn tay được đánh dấu là ảnh",
      [f for f in d3["files"] if f["name"] == "anh.png"][0]["image"] is True)

(broot / "06 - Sources" / "brief.md").write_text("x", encoding="utf-8")
c.post(API + "/files", data={"path": "06 - Sources/brief.md"})
os.remove(broot / "06 - Sources" / "brief.md")
d4 = c.get(API + "?brain=" + BRAIN).json()
mat = [f for f in d4["files"] if f["path"].endswith("brief.md")]
# Gắn tay là một cử chỉ CỐ Ý. Im lặng bỏ đi thì người dùng tưởng thao tác của mình bị nuốt,
# trong khi sự thật là file đã dời chỗ.
check("file gắn tay đã bị xoá vẫn Ở LẠI danh sách", len(mat) == 1)
check("và được đánh dấu là không còn", mat and mat[0]["exists"] is False)

# ============================================================
# 5. Ghim và gỡ
# ============================================================
check("ghim được", c.post(API + "/files/" + FID + "/pin", data={"pinned": "1"}).json().get("ok"))
check("và trạng thái ghim đọc lại đúng",
      [f for f in c.get(API + "?brain=" + BRAIN).json()["files"]
       if f.get("id") == FID][0]["pinned"] is True)
check("bỏ ghim được", c.post(API + "/files/" + FID + "/pin", data={"pinned": "0"}).json().get("ok"))

check("gỡ link được", c.post(API + "/links/" + LID + "/delete").json().get("ok"))
check("gỡ rồi thì không còn trong danh sách gắn tay",
      all(l["url"] != "https://elegant.vn/" for l in st.list_session_links(SID)))
# Gỡ khỏi cuộc KHÔNG được đụng file trên đĩa: file nằm trong brain và có đời sống riêng.
c.post(API + "/files/" + FID + "/delete")
check("gỡ file khỏi cuộc KHÔNG xoá file trên đĩa",
      (broot / "06 - Sources" / "bang-gia.md").is_file())

# id của cuộc khác không được xoá bản ghi của cuộc này.
st.get_or_create("cuoc-khac", brain=BRAIN, engine="cli", model="x")
gid = st.add_session_file("cuoc-khac", "06 - Sources/bang-gia.md")
check("id của cuộc khác không gỡ được qua route của cuộc này",
      c.post(API + "/files/" + gid + "/delete").json().get("ok") is False
      and len(st.list_session_files("cuoc-khac")) == 1)

# ============================================================
# 6. Xoá hội thoại thì tài liệu gắn vào nó đi theo (khoá ngoại)
# ============================================================
st.delete("cuoc-khac")
check("xoá hội thoại thì tài liệu gắn tay đi theo, không để lại hàng mồ côi",
      st.list_session_files("cuoc-khac") == [])

# ============================================================
# 7. Javis THẤY thứ được gắn - đây mới là điểm làm cho nút thêm có nghĩa
# ============================================================
st.get_or_create("cuoc-prompt", brain=BRAIN, engine="cli", model="x")
check("chưa gắn gì thì không có khối nào chen vào prompt",
      main._session_block("cuoc-prompt") == "")
pid2 = st.add_session_file("cuoc-prompt", "06 - Sources/bang-gia.md", "Bảng giá")
st.add_session_link("cuoc-prompt", "https://elegant.vn/", "Mẫu")
khoi = main._session_block("cuoc-prompt")
check("gắn rồi thì tên file có trong prompt", "Bảng giá" in khoi, khoi[:200])
check("link cũng có trong prompt", "https://elegant.vn/" in khoi)
# Chưa ghim = chỉ biết TÊN. Nạp sẵn cả nội dung mọi file là mỗi cuộc chat lặng lẽ nuốt token.
check("chưa ghim thì KHÔNG nạp nội dung", "120k" not in khoi)
st.set_session_file_pinned("cuoc-prompt", pid2, True)
khoi2 = main._session_block("cuoc-prompt")
# Ghim bảng giá vào rồi thì người dùng nghĩ Javis đã BIẾT bảng giá, chứ không phải biết TÊN nó.
check("ghim thì nạp luôn nội dung", "120k" in khoi2, khoi2[:300])
check("khối của cuộc được ghép vào system prompt",
      "120k" in main.build_system_prompt(BRAIN, include_memory=False, include_skills=False,
                                         session_id="cuoc-prompt"))
check("không truyền session_id thì không ghép gì",
      "120k" not in main.build_system_prompt(BRAIN, include_memory=False, include_skills=False))

# ============================================================
# 8. Trần số lượng: một cuộc chat kéo dài cả tháng không âm thầm phình ra
# ============================================================
st.get_or_create("cuoc-tran", brain=BRAIN, engine="cli", model="x")
for i in range(sessions_mod.SESSION_ASSETS_MAX):
    st.add_session_link("cuoc-tran", f"https://vd.vn/{i}")
check("chạm trần thì thêm nữa bị từ chối",
      st.add_session_link("cuoc-tran", "https://vd.vn/qua-tran") is None
      and len(st.list_session_links("cuoc-tran")) == sessions_mod.SESSION_ASSETS_MAX)
check("và route trả lỗi rõ ràng chứ không im lặng nuốt",
      c.post("/sessions/cuoc-tran/assets/links",
             data={"url": "https://vd.vn/qua-tran"}).status_code == 400)

# ============================================================
# 9. media_gc không được dọn mất tài liệu người dùng gắn tay
# ============================================================
check("đường dẫn gắn tay nằm trong danh sách GIỮ của media_gc",
      "06 - Sources/bang-gia.md" in get_store().all_session_file_paths())

print("")
if fails:
    print(f"ĐỎ {len(fails)} mục")
    sys.exit(1)
print("Tất cả xanh.")
