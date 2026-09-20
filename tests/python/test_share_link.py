"""Link CHIA SẺ CÔNG KHAI một file trong brain (0.59.39).

    python tests/run.py share_link

Chủ dự án xin 18/09: trong khung mở file cần một nút Chia sẻ, cho ra đường link mà gửi cho ai
họ cũng xem được, và xem được BẢN HOÀN THIỆN - .html chạy thật, .md hiện đậm nghiêng với ảnh.
Mục đích là làm vài ứng dụng nhỏ rồi gửi cho người khác xem ngay.

Đây là mặt tiền CÔNG KHAI đầu tiên của Javis chạm vào file trong brain, nên phần lớn test này
là test an toàn chứ không phải test tính năng:

  1. "/s/" trong danh sách đường công khai PHẢI có gạch chéo cuối. Hàng rào so bằng
     `path.startswith`, nên khai "/s" là mở toang /settings, /skills, /sessions, /stt.
  2. Token phải không đoán được, và thu hồi phải chết hẳn.
  3. Tài nguyên kèm theo bó trong thư mục chứa file (cộng attachments), không cho đọc cả brain.
  4. Trang trả về phải mang header cách ly, không thì một file .html do AI viết ra, mở bởi
     chính chủ lúc đang đăng nhập, sẽ chạy cùng gốc với dashboard.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import os
import sys
import tempfile

_STATE = tempfile.mkdtemp(prefix="javis-share-")
_BRAINS = tempfile.mkdtemp(prefix="javis-share-brains-")
os.environ["JAVIS_STATE_DIR"] = _STATE
os.environ["BRAINS_DIR"] = _BRAINS

BRAIN = os.path.join(_BRAINS, "brain")
os.makedirs(os.path.join(BRAIN, "attachments"), exist_ok=True)
os.makedirs(os.path.join(BRAIN, "rieng"), exist_ok=True)
with open(os.path.join(BRAIN, "ghi-chu.md"), "w", encoding="utf-8") as f:
    f.write("# Tiêu đề\n\nChữ **đậm** và *nghiêng*.\n\n![hình](attachments/a.png)\n\n"
            "- mục một\n- mục hai\n")
with open(os.path.join(BRAIN, "app.html"), "w", encoding="utf-8") as f:
    f.write("<!doctype html><h1>App nhỏ</h1><script>window.CHAY=1</script>")
with open(os.path.join(BRAIN, "ghi.txt"), "w", encoding="utf-8") as f:
    f.write("dong mot <b>khong phai the</b>\ndong hai")
with open(os.path.join(BRAIN, "attachments", "a.png"), "wb") as f:
    f.write(b"\x89PNG\r\n\x1a\n" + b"0" * 40)
with open(os.path.join(BRAIN, "rieng", "kin.md"), "w", encoding="utf-8") as f:
    f.write("khong duoc lo")
with open(os.path.join(BRAIN, "hang-xom.md"), "w", encoding="utf-8") as f:
    f.write("ghi chu khac, cung thu muc")
# Ghi chú nằm trong THƯ MỤC CON, ảnh nằm ngay cạnh nó. Đây là cách người ta viết note thật
# (và là chỗ Javis hỏng trước 0.59.43: mọi đường dẫn tương đối bị tính theo GỐC BRAIN).
os.makedirs(os.path.join(BRAIN, "06 - Sources", "hinh"), exist_ok=True)
with open(os.path.join(BRAIN, "06 - Sources", "bai-viet.md"), "w", encoding="utf-8") as f:
    f.write("# Bài\n\n![cạnh note](anh-canh-note.png)\n\n![thư mục con](hinh/trong-hinh.png)\n")
for _t in ("anh-canh-note.png",):
    with open(os.path.join(BRAIN, "06 - Sources", _t), "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n" + b"0" * 20)
with open(os.path.join(BRAIN, "06 - Sources", "hinh", "trong-hinh.png"), "wb") as f:
    f.write(b"\x89PNG\r\n\x1a\n" + b"0" * 20)
with open(os.path.join(BRAIN, "06 - Sources", "ghi-chu-khac.md"), "w", encoding="utf-8") as f:
    f.write("khong duoc lo qua link chia se")

os.makedirs(os.path.join(BRAIN, "assets"), exist_ok=True)
with open(os.path.join(BRAIN, "assets", "style.css"), "w", encoding="utf-8") as f:
    f.write("body{color:red}")

from fastapi.testclient import TestClient   # noqa: E402
import share_render                         # noqa: E402
import share_store                          # noqa: E402
import main                                 # noqa: E402

_fails = []


def check(name, cond, extra=None):
    print(("ok   " if cond else "FAIL ") + name + ("" if cond or extra is None else f"  [{extra}]"))
    if not cond:
        _fails.append(name)


# base_url localhost: web_security chặn Host lạ khi chưa bật cổng đăng nhập.
cl = TestClient(main.app, base_url="http://localhost")


# ============ 1. AN TOÀN: đường công khai không được nuốt đường khác ============
check('"/s/" khai KÈM gạch chéo cuối', "/s/" in main._AUTH_PUBLIC_PREFIX)
check('KHÔNG khai "/s" trần (sẽ mở công khai /settings, /skills, /sessions...)',
      "/s" not in main._AUTH_PUBLIC_PREFIX)
# Phép thử có quyền lực thật: mô phỏng đúng phép so của hàng rào.
_nuot = [d for d in ("/settings", "/skills", "/sessions", "/stt", "/share/list", "/share/create")
         if any(d.startswith(p) for p in main._AUTH_PUBLIC_PREFIX)]
check("không đường nội bộ nào lọt vào diện công khai", not _nuot, ", ".join(_nuot))


# ============ 2. Tạo link ============
r = cl.post("/share/create", json={"brain": BRAIN, "path": "ghi-chu.md"})
d = r.json()
check("tạo được link", r.status_code == 200 and d.get("ok") is True, r.text[:120])
TOK = d.get("token", "")
check("token đủ dài để không đoán được", len(TOK) >= 20, f"{len(TOK)} ký tự")
check("trả ĐƯỜNG DẪN tương đối, không phải URL tuyệt đối dựng từ header Host",
      d.get("path") == "/s/" + TOK, d.get("path"))
check("bấm Chia sẻ lần hai trả ĐÚNG link cũ, không đẻ link mới",
      cl.post("/share/create", json={"brain": BRAIN, "path": "ghi-chu.md"}).json().get("token") == TOK)
check("/share/of biết file này đã có link",
      (cl.get("/share/of", params={"brain": BRAIN, "path": "ghi-chu.md"}).json().get("share") or {})
      .get("token") == TOK)


# ============ 3. Trang .md: BẢN HOÀN THIỆN, không phải mã nguồn ============
p = cl.get("/s/" + TOK)
check("mở được trang .md", p.status_code == 200, p.status_code)
body = p.text
check("in đậm ra thẻ strong", "<strong>đậm</strong>" in body)
check("in nghiêng ra thẻ em", "<em>nghiêng</em>" in body)
check("tiêu đề ra thẻ h1", "<h1>Tiêu đề</h1>" in body)
check("danh sách ra thẻ ul/li", "<li>mục một</li>" in body)
check("ảnh trỏ qua chính token đang xem, không phải /files/raw",
      f"/s/{TOK}/asset?p=attachments" in body and "/files/raw" not in body)
check("KHÔNG lộ mã nguồn markdown thô", "**đậm**" not in body)
check("trang .md cách ly ở mức chặt nhất (không cần script)",
      p.headers.get("content-security-policy") == share_render.CSP_TINH,
      p.headers.get("content-security-policy"))
check("và trang .md thật sự KHÔNG chứa script nào", "<script" not in body.lower())


# ============ 4. Trang .html: chạy thật, nhưng trong hộp cách ly ============
th = cl.post("/share/create", json={"brain": BRAIN, "path": "app.html"}).json()
h = cl.get("/s/" + th["token"])
check("mở được trang .html", h.status_code == 200)
check("giao diện chạy thật, trả nguyên văn HTML người dùng", "<h1>App nhỏ</h1>" in h.text)
_csp = h.headers.get("content-security-policy") or ""
check("có sandbox", "sandbox" in _csp, _csp)
check("cho chạy script (để app nhỏ hoạt động)", "allow-scripts" in _csp, _csp)
check("KHÔNG allow-same-origin - đây là chốt chặn chính, thiếu nó thì sandbox vô nghĩa "
      "và file .html đọc được cookie đăng nhập của người mở",
      "allow-same-origin" not in _csp, _csp)
check("có nosniff", h.headers.get("x-content-type-options") == "nosniff")


# ============ 5. Trang .txt: giữ nguyên văn, không diễn giải thành thẻ ============
tt = cl.post("/share/create", json={"brain": BRAIN, "path": "ghi.txt"}).json()
t = cl.get("/s/" + tt["token"])
check("mở được trang .txt", t.status_code == 200)
check(".txt giữ nguyên văn, thẻ trong file bị escape chứ không chạy",
      "&lt;b&gt;khong phai the&lt;/b&gt;" in t.text and "<b>khong phai the</b>" not in t.text)


# ============ 6. Tài nguyên kèm theo: đúng phạm vi, không hơn ============
a = cl.get(f"/s/{TOK}/asset", params={"p": "attachments/a.png"})
check("ảnh trong attachments xem được", a.status_code == 200 and "image" in (a.headers.get("content-type") or ""))
check("traversal ra ngoài brain bị chặn",
      cl.get(f"/s/{TOK}/asset", params={"p": "../../../etc/passwd"}).status_code == 404)
check("file ở thư mục KHÁC trong brain không đọc được qua token",
      cl.get(f"/s/{TOK}/asset", params={"p": "rieng/kin.md"}).status_code == 404)
# Luật LOẠI FILE, khoá riêng. Ghi chú .md nằm CÙNG thư mục với file được chia sẻ cũng không
# được đọc: đây chính là lỗ mà phép thử trên bắt được lúc mới viết xong.
check("tài liệu .md nằm cùng thư mục cũng KHÔNG đọc được (luật loại file)",
      cl.get(f"/s/{TOK}/asset", params={"p": "hang-xom.md"}).status_code == 404)
check("nhưng css trong thư mục con thì được (trang .html cần nó)",
      cl.get(f"/s/{TOK}/asset", params={"p": "assets/style.css"}).status_code == 200)


# ============ 7. Thu hồi ============
check("token bịa ra trả 404", cl.get("/s/khong-he-ton-tai").status_code == 404)
cl.post("/share/revoke", json={"token": TOK})
check("thu hồi xong link chết hẳn", cl.get("/s/" + TOK).status_code == 404)
check("và tài nguyên của nó cũng chết theo",
      cl.get(f"/s/{TOK}/asset", params={"p": "attachments/a.png"}).status_code == 404)


# ============ 8. Bộ dựng markdown: hàm thuần, soi kỹ phần an toàn ============
md = share_render.md_to_html
check("HTML thô trong .md bị escape, không cho chạy",
      "&lt;script&gt;" in md("<script>alert(1)</script>", "/s/T/asset"))
check("link javascript: bị bỏ, chỉ còn lại chữ",
      "javascript:" not in md("[bấm](javascript:alert(1))", "/s/T/asset"))
check("link ngoài vẫn đi được và mang rel an toàn",
      'rel="noopener noreferrer nofollow"' in md("[web](https://vi.dụ)", "/s/T/asset"))
check("ảnh wikilink ![[x.png]] cũng đi qua token",
      "/s/T/asset?p=a.png" in md("![[a.png]]", "/s/T/asset"))
check("dấu sao trong khối mã KHÔNG bị hiểu là in nghiêng",
      "<em>" not in md("```\na * b * c\n```", "/s/T/asset"))
check("bảng dựng ra thẻ table", "<table>" in md("| a | b |\n|---|---|\n| 1 | 2 |", "/s/T/asset"))
check("frontmatter bị giấu, không đổ ra trang",
      "type: source" not in md("---\ntype: source\n---\n\nNội dung", "/s/T/asset"))


# ============ ẢNH TRONG .md: tìm theo THƯ MỤC CỦA NOTE trước ============
# Chủ dự án 18/09: "ở file .md hiện tại đang không hiển thị ảnh, nếu có chèn link ảnh hoặc là
# tham chiếu đến ảnh trong folder cũng nên hiển thị ảnh trong file .md nhé."
#
# Trước bản này `p` được phân giải thẳng từ GỐC BRAIN, nên note ở "06 - Sources/bai-viet.md"
# viết ![](anh-canh-note.png) là server đi tìm <brain>/anh-canh-note.png, không có, trả 404, và
# người xem thấy một ô trống. Giờ thử theo thứ tự: thư mục của note, rồi gốc brain, rồi
# attachments - đúng thứ tự `ungVienAnh` bên dashboard/chat-render.js dùng.
check("thứ tự ứng viên: thư mục note trước, rồi gốc brain, rồi attachments",
      main._ung_vien_tai_nguyen("06 - Sources/bai-viet.md", "anh.png")
      == ["06 - Sources/anh.png", "anh.png", "attachments/anh.png"],
      main._ung_vien_tai_nguyen("06 - Sources/bai-viet.md", "anh.png"))
check('"./" được bỏ, không đẻ ứng viên thừa',
      main._ung_vien_tai_nguyen("a/note.md", "./x.png")[0] == "a/x.png",
      main._ung_vien_tai_nguyen("a/note.md", "./x.png"))
check('".." thu gọn tại chỗ chứ không gửi thẳng xuống đĩa',
      main._ung_vien_tai_nguyen("a/b/note.md", "../anh.png")[0] == "a/anh.png",
      main._ung_vien_tai_nguyen("a/b/note.md", "../anh.png"))
check('".." vượt lên trên gốc brain thì BỎ hẳn ứng viên đó',
      all(not u.startswith("..")
          for u in main._ung_vien_tai_nguyen("a/note.md", "../../../etc/passwd")),
      main._ung_vien_tai_nguyen("a/note.md", "../../../etc/passwd"))

_r = cl.post("/share/create", json={"brain": BRAIN, "path": "06 - Sources/bai-viet.md"})
_tok_sub = _r.json().get("token")
check("chia sẻ được note nằm trong thư mục con", bool(_tok_sub), _r.text)
if _tok_sub:
    _a = cl.get(f"/s/{_tok_sub}/asset", params={"p": "anh-canh-note.png"})
    check("ẢNH CẠNH NOTE hiện được (lỗi chủ dự án báo)", _a.status_code == 200, _a.status_code)
    _b = cl.get(f"/s/{_tok_sub}/asset", params={"p": "hinh/trong-hinh.png"})
    check("ảnh trong thư mục con cạnh note cũng hiện được", _b.status_code == 200, _b.status_code)
    # Thêm ứng viên KHÔNG được nới phạm vi: hai hàng rào cũ vẫn phải chặn đúng như trước.
    _c = cl.get(f"/s/{_tok_sub}/asset", params={"p": "ghi-chu-khac.md"})
    check("ghi chú khác CÙNG thư mục vẫn KHÔNG đọc được (chặn theo loại file)",
          _c.status_code == 404, _c.status_code)
    _d = cl.get(f"/s/{_tok_sub}/asset", params={"p": "rieng/kin.md"})
    check("ghi chú ở thư mục khác vẫn không đọc được", _d.status_code == 404, _d.status_code)
    _e = cl.get(f"/s/{_tok_sub}/asset", params={"p": "../../../etc/passwd"})
    check("không vượt được ra ngoài brain", _e.status_code == 404, _e.status_code)
    # Đường lui về attachments vẫn còn: note ở thư mục con trỏ tới ảnh Javis tự cất.
    _f = cl.get(f"/s/{_tok_sub}/asset", params={"p": "a.png"})
    check("vẫn lui được về attachments/ khi ảnh không nằm cạnh note",
          _f.status_code == 200, _f.status_code)

# ============ APP .html ĐỌC FILE DỮ LIỆU CẠNH NÓ (0.59.46) ============
# Chủ dự án 20/09: "một số ứng dụng html đọc file dữ liệu mà share xong không thấy hiện các dữ
# liệu". Hai lý do, phải sửa cả hai:
#   1. Trang mở ở /s/<token> (không gạch cuối) nên fetch("data.json") xin /s/data.json - không
#      có route nào ở đó. Nay .html chuyển hướng sang /s/<token>/ và có route /s/<token>/<p>.
#   2. Trang chạy trong sandbox không allow-same-origin -> origin "null", fetch là chéo nguồn,
#      thiếu Access-Control-Allow-Origin là trình duyệt chặn đọc dù file đã tải về.
os.makedirs(os.path.join(BRAIN, "apps", "bang", "con"), exist_ok=True)
with open(os.path.join(BRAIN, "apps", "bang", "index.html"), "w", encoding="utf-8") as f:
    f.write("<!doctype html><h1>Bảng</h1><script>fetch('data.json')</script>")
with open(os.path.join(BRAIN, "apps", "bang", "data.json"), "w", encoding="utf-8") as f:
    f.write('{"doanh_thu": 12}')
with open(os.path.join(BRAIN, "apps", "bang", "con", "so.csv"), "w", encoding="utf-8") as f:
    f.write("a,b\n1,2\n")
with open(os.path.join(BRAIN, "apps", "bang", "trang2.html"), "w", encoding="utf-8") as f:
    f.write("<p>trang phụ</p>")
with open(os.path.join(BRAIN, "apps", "bang", "ghi-chu.md"), "w", encoding="utf-8") as f:
    f.write("ghi chú trong thư mục app")
with open(os.path.join(BRAIN, "apps", "hang-xom.json"), "w", encoding="utf-8") as f:
    f.write("{}")
_ta = cl.post("/share/create", json={"brain": BRAIN, "path": "apps/bang/index.html"}).json()
_tk = _ta.get("token")
check("chia sẻ được app trong thư mục con", bool(_tk), _ta)
if _tk:
    _r0 = cl.get(f"/s/{_tk}", follow_redirects=False)
    check("/s/<token> của trang .html CHUYỂN HƯỚNG sang địa chỉ có gạch cuối (để đường dẫn "
          "tương đối trong app trỏ đúng)", _r0.status_code in (301, 302, 307, 308)
          and (_r0.headers.get("location") or "").endswith(f"/s/{_tk}/"), (_r0.status_code, _r0.headers.get("location")))
    _r1 = cl.get(f"/s/{_tk}/")
    check("trang .html mở được ở /s/<token>/", _r1.status_code == 200 and "<h1>Bảng</h1>" in _r1.text)
    check("vẫn trong hộp cách ly sandbox, không allow-same-origin",
          "sandbox" in (_r1.headers.get("content-security-policy") or "")
          and "allow-same-origin" not in (_r1.headers.get("content-security-policy") or ""))
    _d = cl.get(f"/s/{_tk}/data.json")
    check("data.json cạnh trang ĐỌC ĐƯỢC qua đường dẫn tương đối", _d.status_code == 200
          and "doanh_thu" in _d.text, _d.status_code)
    check("kiểu MIME là json", "application/json" in (_d.headers.get("content-type") or ""),
          _d.headers.get("content-type"))
    check("CANARY: có Access-Control-Allow-Origin: * (trang sandbox có origin null, thiếu là "
          "fetch bị chặn đọc dù file đã tải)", _d.headers.get("access-control-allow-origin") == "*")
    check("csv trong thư mục con của app cũng đọc được",
          cl.get(f"/s/{_tk}/con/so.csv").status_code == 200)
    check("trang phụ .html của app mở được", cl.get(f"/s/{_tk}/trang2.html").status_code == 200)
    check("ghi chú .md trong thư mục RIÊNG của app đọc được (app ghi chú cần nó)",
          cl.get(f"/s/{_tk}/ghi-chu.md").status_code == 200)
    check("KHÔNG leo lên thư mục cha (apps/hang-xom.json)",
          main._share_sibling({"brain": BRAIN, "path": "apps/bang/index.html", "token": _tk},
                              "../hang-xom.json") is None)
    check("KHÔNG leo ra gốc brain đọc ghi chú khác",
          main._share_sibling({"brain": BRAIN, "path": "apps/bang/index.html", "token": _tk},
                              "../../ghi-chu.md") is None
          and cl.get(f"/s/{_tk}/..%2F..%2Fghi-chu.md").status_code == 404)
    check("thư mục ẩn bị chặn",
          main._share_sibling({"brain": BRAIN, "path": "apps/bang/index.html", "token": _tk},
                              ".git/config") is None)
    check("token bịa thì 404", cl.get("/s/khong-co/data.json").status_code == 404)
# Trang .html nằm NGAY GỐC BRAIN: tài nguyên trình bày vẫn được, FILE DỮ LIỆU thì không - thư
# mục chứa nó là cả kho ghi chú, mở ra là một token lẻ đọc được mọi ghi chú.
_tg = cl.post("/share/create", json={"brain": BRAIN, "path": "app.html"}).json().get("token")
if _tg:
    check("app ở gốc brain: css trong thư mục con vẫn được",
          cl.get(f"/s/{_tg}/assets/style.css").status_code == 200)
    check("CANARY: app ở gốc brain KHÔNG đọc được ghi chú .md cạnh nó",
          cl.get(f"/s/{_tg}/hang-xom.md").status_code == 404)
    check("CANARY: app ở gốc brain KHÔNG đọc được .json/.txt ở gốc",
          cl.get(f"/s/{_tg}/ghi.txt").status_code == 404)
    check("và không đọc được thư mục riêng tư", cl.get(f"/s/{_tg}/rieng/kin.md").status_code == 404)
# Link chia sẻ của .md KHÔNG mở đường này: ghi chú lấy ảnh qua /asset với luật riêng.
_tm = cl.post("/share/create", json={"brain": BRAIN, "path": "06 - Sources/bai-viet.md"}).json().get("token")
if _tm:
    check("token của .md không phục vụ file cạnh nó qua /s/<token>/<p>",
          cl.get(f"/s/{_tm}/ghi-chu-khac.md").status_code == 404
          and cl.get(f"/s/{_tm}/anh-canh-note.png").status_code == 404)
    check("/s/<token>/ của .md quay về /s/<token>", cl.get(f"/s/{_tm}/").status_code == 200)

print()
if _fails:
    print(f"THẤT BẠI {len(_fails)}: {_fails}")
    sys.exit(1)
print("OK - test_share_link: tất cả pass")
