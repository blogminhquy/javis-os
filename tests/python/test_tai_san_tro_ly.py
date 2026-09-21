"""Tài liệu & link gắn vào MỘT TRỢ LÝ.

    python tests/run.py tai_san_tro_ly

Chủ repo 21/09: "agent cũng sẽ thêm được file và link kiểu như bên gom project của trò
chuyện ấy". Project và cuộc trò chuyện đã có; trợ lý thì chưa, nên muốn một trợ lý luôn biết
bảng giá thì phải dán lại vào từng cuộc.

Bốn quyết định đáng canh, vì cả bốn đều có cách làm sai trông hợp lý hơn:

1. CHỖ LƯU là frontmatter của chính file trợ lý, không phải SQLite như project. Trợ lý là một
   file trong brain: xuất ra gửi người khác, copy brain sang máy mới, hay mở lên sửa tay đều
   phải còn nguyên danh sách. Để trong DB thì trợ lý qua tay người khác thành cái vỏ rỗng.

2. GIỮ MỌI KHOÁ KHÁC. Sáu route ở đây ghi đè file trợ lý; quên giữ phần thân hay các khoá
   frontmatter khác là mỗi lần gắn một file lại xoá mất prompt hoặc danh sách skill.

3. `brain` phải đi theo mọi lời gọi. Project và hội thoại nằm trong DB nên server tự tra ra
   brain của chúng; trợ lý thì không, và thiếu nó là mọi thao tác rơi vào brain mặc định -
   im lặng và sai.

4. Gắn vào thì trợ lý phải THẤY. Không bơm vào system prompt của nó thì danh sách chỉ để
   ngắm: người dùng gắn bảng giá xong hỏi ngay, và trợ lý trả lời như chưa hề thấy gì.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import os
import tempfile
from pathlib import Path

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-tsag-state-"))

from fastapi.testclient import TestClient  # noqa: E402
import agent_assets  # noqa: E402
import main  # noqa: E402

fails = []


def check(name, cond, them=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(them) + "]") if not cond and them else ""))
    if not cond:
        fails.append(name)


# ============================================================
# 0. Hàm thuần: kho nằm trong meta, không cần dựng brain
# ============================================================
m = {"type": "agent", "name": "Người viết", "skills": ["viet-email"]}
m, fid = agent_assets.them_file(m, "sources/bang-gia.md")
m, lid = agent_assets.them_link(m, "https://moc-viet.vn/gia", "Bảng giá")
check("thêm file rồi thì đọc ra đúng một hàng", len(agent_assets.doc(m)["files"]) == 1)
check("tên file tự suy từ đường dẫn", agent_assets.doc(m)["files"][0]["name"] == "bang-gia.md")
check("KHÔNG đụng vào các khoá khác của frontmatter",
      m.get("skills") == ["viet-email"] and m.get("name") == "Người viết", m)
m2, fid2 = agent_assets.them_file(m, "sources/bang-gia.md")
check("thêm CÙNG file lần hai trả id cũ, không đẻ hàng trùng",
      fid2 == fid and len(agent_assets.doc(m2)["files"]) == 1)
m, ok = agent_assets.ghim_file(m, fid, True)
check("ghim được", ok and agent_assets.doc(m)["files"][0]["pinned"] is True)
m, ok = agent_assets.ghim_file(m, "khong-co-id", True)
check("ghim một id không có thì trả False, không ném", ok is False)
m, ok = agent_assets.go_link(m, lid)
check("gỡ link được", ok and agent_assets.doc(m)["links"] == [])
m, ok = agent_assets.go_file(m, fid)
check("gỡ hết thì XOÁ hẳn khoá assets (đừng để lại khoá rỗng trong frontmatter)",
      "assets" not in m, m)
# Trần: danh sách này đi vào prompt ở MỌI lượt, và nằm trong một file người ta còn đọc bằng mắt.
mt = {}
for i in range(agent_assets.TRAN_MOI_LOAI):
    mt, _ = agent_assets.them_file(mt, f"sources/f{i}.md")
try:
    agent_assets.them_file(mt, "sources/qua-tran.md")
    check("chạm trần thì từ chối", False, "không ném ValueError")
except ValueError:
    check("chạm trần thì từ chối", True)
# File sửa tay hỏng (thiếu id, sai kiểu) không được làm sập cả trang.
xau = {"assets": {"files": ["chuỗi lạc", {"name": "thiếu path"}, {"path": "sources/ok.md"}],
                  "links": None}}
doc_xau = agent_assets.doc(xau)
check("frontmatter sửa tay hỏng thì bỏ hàng rác, giữ hàng đọc được",
      len(doc_xau["files"]) == 1 and doc_xau["files"][0]["path"] == "sources/ok.md", doc_xau)
check("và hàng thiếu id vẫn được cấp id để gỡ được", bool(doc_xau["files"][0]["id"]))

# ============================================================
# 1. Route: brain riêng trong thư mục tạm
# ============================================================
BRAIN = tempfile.mkdtemp(prefix="javis-brain-tsag-")
broot = Path(BRAIN)
os.environ["JAVIS_FILES_ROOT"] = BRAIN     # khoá trần duyệt vào đúng brain này
(broot / "sources").mkdir(parents=True, exist_ok=True)
(broot / "sources" / "bang-gia.md").write_text("Nước mắm 500ml: 120k", encoding="utf-8")
(broot / "sources" / "anh.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 16)

main.cfgmod.gate_active = lambda: False
c = TestClient(main.app, base_url="http://127.0.0.1")

r = c.post("/agents", data={"name": "Nguoi viet", "role": "Viết bài", "group": "Marketing",
                            "prompt": "Bạn viết bài bán hàng.", "skills": "viet-email",
                            "brain": BRAIN})
SLUG = r.json()["slug"]
API = f"/agents/{SLUG}/assets"

r = c.post(API + "/files", data={"path": "sources/bang-gia.md", "brain": BRAIN})
check("thêm được file có thật trong brain", r.status_code == 200 and r.json().get("ok"), r.text)
FID = r.json().get("id")
check("file không có trong brain thì từ chối",
      c.post(API + "/files", data={"path": "sources/khong-co.md", "brain": BRAIN}).status_code == 404)
# Rào path là thứ duy nhất chặn một trợ lý trỏ ra ngoài brain, và nó phải nói KHÔNG ngay ở
# cửa ghi chứ không để lỗi nổ lúc dựng prompt.
check("đường dẫn trèo ra ngoài trần bị chặn",
      c.post(API + "/files", data={"path": "../../etc/passwd", "brain": BRAIN}).status_code == 400)
check("thư mục cũng bị từ chối",
      c.post(API + "/files", data={"path": "sources", "brain": BRAIN}).status_code == 404)
check("trợ lý không tồn tại trả 404",
      c.post("/agents/khong-co-that/assets/files",
             data={"path": "sources/bang-gia.md", "brain": BRAIN}).status_code == 404)
# slug đi thẳng từ URL vào tên file, nên nó phải qua valid_slug trước mọi thứ khác.
check("slug trèo thư mục bị chặn",
      c.get("/agents/..%2F..%2Fetc/assets", params={"brain": BRAIN}).status_code in (400, 404))

r = c.post(API + "/links", data={"url": "https://moc-viet.vn/gia", "label": "Bảng giá",
                                 "brain": BRAIN})
check("thêm được link", r.status_code == 200 and r.json().get("ok"), r.text)
LID = r.json().get("id")
check("javascript: bị từ chối",
      c.post(API + "/links", data={"url": "javascript:alert(1)", "brain": BRAIN}).status_code == 400)

d = c.get(API, params={"brain": BRAIN}).json()
check("GET trả về đủ file và link", len(d["files"]) == 1 and len(d["links"]) == 1, d)
check("GET kèm tên trợ lý để vẽ đầu khung", d.get("name") == "Nguoi viet", d)

# ============================================================
# 2. Sáu route ghi đè file trợ lý: KHÔNG được làm mất gì khác
# ============================================================
meta, body = main._read_md(Path(BRAIN) / "agents" / f"{SLUG}.md")
check("prompt (thân file) còn nguyên sau khi gắn tài liệu",
      body.strip() == "Bạn viết bài bán hàng.", body)
check("skill và nhóm còn nguyên",
      meta.get("skills") == ["viet-email"] and meta.get("group") == "Marketing", meta)

# Sửa trợ lý ở trình sửa xong bấm Lưu: POST /agents dựng lại meta từ `previous`, nên tài liệu
# phải sống sót. Quên chuyện này là gắn xong, sửa một chữ trong prompt là mất sạch danh sách.
c.post("/agents", data={"name": "Nguoi viet", "role": "Viết bài hay hơn",
                        "prompt": "Bạn viết bài bán hàng.", "skills": "viet-email",
                        "slug": SLUG, "brain": BRAIN})
d = c.get(API, params={"brain": BRAIN}).json()
check("lưu lại trợ lý từ trình sửa KHÔNG làm mất tài liệu đã gắn", len(d["files"]) == 1, d)

# ============================================================
# 3. Ghim = NẠP NỘI DUNG vào prompt của trợ lý
# ============================================================
sp = main._agent_chat_prompt(BRAIN, SLUG)
check("chưa ghim thì prompt chỉ có TÊN file", "sources/bang-gia.md" in sp)
check("và CHƯA có nội dung file", "Nước mắm 500ml" not in sp, sp[-600:])
check("link cũng được liệt kê", "https://moc-viet.vn/gia" in sp)

c.post(API + f"/files/{FID}/pin", data={"pinned": "1", "brain": BRAIN})
sp = main._agent_chat_prompt(BRAIN, SLUG)
check("ghim rồi thì NỘI DUNG file nằm sẵn trong prompt", "Nước mắm 500ml: 120k" in sp)
# Bốn trần token của project dùng chung cho cả ba chỗ (main._liet_ke_tai_lieu), nên không có
# đường nào để một trợ lý nạp nhiều hơn một project.
check("dùng chung trần token với project",
      "_liet_ke_tai_lieu" in (ROOT / "server" / "main.py").read_text(encoding="utf-8").split(
          "def _agent_assets_block")[1][:900])

# File nhị phân ghim vào thì nói THẲNG là không nạp được. Im lặng bỏ qua thì người dùng ghim
# xong tưởng trợ lý đã đọc.
r = c.post(API + "/files", data={"path": "sources/anh.png", "brain": BRAIN})
c.post(API + f"/files/{r.json()['id']}/pin", data={"pinned": "1", "brain": BRAIN})
sp = main._agent_chat_prompt(BRAIN, SLUG)
check("file nhị phân ghim vào thì nói rõ không nạp được", "nhị phân" in sp, sp[-800:])

# Trợ lý chưa gắn gì thì KHÔNG được có khối rỗng trong prompt - mỗi dòng thừa lặp lại ở mọi lượt.
r2 = c.post("/agents", data={"name": "Trong tron", "role": "x", "prompt": "y", "brain": BRAIN})
check("trợ lý chưa gắn gì thì prompt không có khối tài liệu",
      "TÀI LIỆU & LINK CỦA BẠN" not in main._agent_chat_prompt(BRAIN, r2.json()["slug"]))

# ============================================================
# 4. Gỡ: khỏi trợ lý, KHÔNG xoá file trên đĩa
# ============================================================
c.post(API + f"/files/{FID}/delete", data={"brain": BRAIN})
d = c.get(API, params={"brain": BRAIN}).json()
check("gỡ khỏi trợ lý thì hàng biến mất",
      all(f["id"] != FID for f in d["files"]), d["files"])
check("nhưng file vẫn còn trong brain", (broot / "sources" / "bang-gia.md").exists())
c.post(API + f"/links/{LID}/delete", data={"brain": BRAIN})
check("gỡ link được", c.get(API, params={"brain": BRAIN}).json()["links"] == [])

if fails:
    print(f"\nFAIL {len(fails)} muc: " + ", ".join(fails))
    raise SystemExit(1)
print("\nOK - test_tai_san_tro_ly: tat ca pass")
