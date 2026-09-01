"""File đã tạo và link đã nhắc trong MỘT cuộc trò chuyện.

    python tests/run.py tai_san_cuoc_chat

Chủ repo báo 01/09: chat dài đẻ ra hàng chục tài liệu (kế hoạch, landing page, bài quảng
cáo) rồi muốn tìm lại phải đọc ngược cả cuộc.

Quyết định thiết kế được canh ở đây là chuyện SUY RA TỪ TIN NHẮN ĐÃ LƯU thay vì dựng một
bảng ghi lúc tạo file. Bảng ghi chỉ đúng từ bản cập nhật trở đi, mà chỗ đang đau lại là các
cuộc chat CŨ - những cuộc đã dài, đã tạo xong tài liệu, và giờ mới cần tìm.

Hai luật giữ ứng viên KHÁC NHAU vì độ tin cậy khác nhau, và đó là phần dễ làm sai nhất:
link markdown là cử chỉ cố ý "đây là file của bạn" nên giữ cả khi file đã dời; còn đường
dẫn trần trong văn xuôi phải tự chứng minh bằng cách tồn tại, vì một đường dẫn giả định nêu
trong lời giải thích trông y hệt đường dẫn thật.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-taisan-"))

from fastapi.testclient import TestClient  # noqa: E402
import main  # noqa: E402
from sessions import get_store  # noqa: E402

fails = []


def check(name, cond, them=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(them) + "]") if not cond and them else ""))
    if not cond:
        fails.append(name)


# Brain RIÊNG trong thư mục tạm, không dùng brain mặc định. `_brain_root` trả về chính
# chuỗi truyền vào khi đó là một thư mục có thật, nên đây là lối cô lập mà API vốn đã mở.
# Ghi vào brain mặc định thì test này rải file thật vào `brains/` của người chạy lẫn của CI,
# và bất kỳ test nào sau đó soi brain mặc định cũng có thể đỏ tuỳ thứ tự chạy - đúng loại
# lỗi chập chờn khó truy nhất.
BRAIN = tempfile.mkdtemp(prefix="javis-brain-taisan-")
broot = Path(BRAIN)
(broot / "05 - Projects").mkdir(parents=True, exist_ok=True)
(broot / "attachments").mkdir(parents=True, exist_ok=True)
(broot / "05 - Projects" / "ke-hoach.md").write_text("# Kế hoạch", encoding="utf-8")
(broot / "attachments" / "banner.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 32)
(broot / "05 - Projects" / "co-that.md").write_text("co that", encoding="utf-8")

st = get_store()
SID = "cuoc-dai"
st.get_or_create(SID, brain=BRAIN, engine="cli", model="x")
st.append_message(SID, "user", "Tham khảo giúp mình https://moc-viet.vn/bang-gia nhé")
st.append_message(SID, "assistant",
                  "Xong rồi anh:\n"
                  "- [Kế hoạch quý 4](05 - Projects/ke-hoach.md)\n"
                  "- [Bài quảng cáo](05 - Projects/da-doi-ten.md)\n"
                  "- ![banner](attachments/banner.png)\n"
                  "Trong nháy: `" + str(broot / "05 - Projects" / "co-that.md") + "`\n"
                  "Ví dụ minh hoạ: `" + str(broot / "khong-ton-tai.md") + "`\n"
                  "Ngoài brain: /etc/passwd\n"
                  "Tham khảo https://elegant.vn/ và lại https://moc-viet.vn/bang-gia.")

c = TestClient(main.app, base_url="http://127.0.0.1")
d = c.get(f"/sessions/{SID}/assets").json()
files = {f["name"]: f for f in d.get("files", [])}
links = [l["url"] for l in d.get("links", [])]

# ---- 1. Ứng viên nào được giữ ------------------------------------------------
check("file nhắc bằng link markdown và CÓ THẬT thì có", "ke-hoach.md" in files)
check("ảnh nhúng cũng tính là tài liệu", "banner.png" in files)
check("ảnh được đánh dấu là ảnh", files.get("banner.png", {}).get("image") is True)
# Đây là điểm cốt lõi: file đã đổi tên/dời đi mà biến mất im lặng thì người dùng tưởng danh
# sách hỏng, trong khi sự thật là file còn đó dưới tên khác.
check("file nhắc bằng link markdown nhưng ĐÃ DỜI vẫn hiện", "da-doi-ten.md" in files)
check("và được đánh dấu là không còn", files.get("da-doi-ten.md", {}).get("exists") is False)
check("file còn thì đánh dấu là còn", files.get("ke-hoach.md", {}).get("exists") is True)
check("đường dẫn tuyệt đối trong backtick, CÓ THẬT, thì giữ", "co-that.md" in files)
# Một đường dẫn giả định trong lời giải thích trông y hệt đường dẫn thật, nên nó phải tồn tại
# mới được vào danh sách - nếu không mỗi lời giải thích lại đẻ ra một dòng rác.
check("đường dẫn tuyệt đối KHÔNG có thật thì bỏ", "khong-ton-tai.md" not in files)
check("đường dẫn ngoài brain bị bỏ", "passwd" not in files)
# GIỚI HẠN CÓ THẬT, ghi ra để người sau khỏi tưởng là bug: đường dẫn tuyệt đối KHÔNG bọc
# nháy/backtick mà có KHOẢNG TRẮNG thì bị cắt cụt ở chỗ khoảng trắng đầu tiên - regex đường
# dẫn trần của channel_context cấm khoảng trắng, vì không cấm thì nó nuốt cả câu văn phía sau.
# Chỗ này gần như luôn dính trong đời thật: brain mặc định tên là "Brain Default", tự nó đã
# có khoảng trắng. Nên nhánh đường dẫn trần chỉ ăn với brain đặt ở đường không dấu cách (VPS
# kiểu /opt/javis/brain), còn lối chính vẫn là link markdown - thứ CLAUDE.md đã dặn Javis
# nhúng mỗi khi đưa file cho người dùng, và bắt được kể cả tên có khoảng trắng.
check("CANARY: brain mặc định có khoảng trắng nên nhánh đường dẫn trần khó ăn",
      " " in str(main._default_brain_dir()), main._default_brain_dir())

# ---- 2. Nhãn và đường dẫn ----------------------------------------------------
check("giữ nhãn người dùng đọc được, không chỉ tên file",
      files.get("ke-hoach.md", {}).get("label") == "Kế hoạch quý 4")
check("có đường dẫn theo GỐC BRAIN để hiện cho người đọc",
      files.get("ke-hoach.md", {}).get("brain_path") == "05 - Projects/ke-hoach.md")
# `path` phải theo TRẦN duyệt vì giao diện đưa thẳng cho JavisOpenNoteAt - hàm đó nhận path
# trần. Trần có thể cao hơn gốc brain nên hai đường dẫn này KHÔNG phải lúc nào cũng giống nhau.
_ceil = main._files_root(BRAIN)
check("và đường dẫn theo TRẦN để giao diện mở thẳng được",
      files.get("ke-hoach.md", {}).get("path")
      == main._files_rel(_ceil, broot / "05 - Projects" / "ke-hoach.md"))

# ---- 3. Link -----------------------------------------------------------------
check("link của Javis có", "https://elegant.vn/" in links)
check("link người dùng gửi cũng có", "https://moc-viet.vn/bang-gia" in links)
check("link nhắc hai lần chỉ hiện một dòng", links.count("https://moc-viet.vn/bang-gia") == 1)
_vai = {l["url"]: l["vai"] for l in d.get("links", [])}
check("ghi rõ ai gửi link", _vai.get("https://moc-viet.vn/bang-gia") == "user"
      and _vai.get("https://elegant.vn/") == "assistant")
# Dấu chấm cuối câu không thuộc về địa chỉ.
check("cắt dấu câu dính đuôi URL", all(not u.endswith(".") for u in links), links)

# ---- 4. Ca biên ---------------------------------------------------------------
check("phiên không tồn tại trả 404", c.get("/sessions/khong-co-that/assets").status_code == 404)
st.get_or_create("cuoc-trong", brain=BRAIN, engine="cli", model="x")
d2 = c.get("/sessions/cuoc-trong/assets").json()
check("cuộc chưa có tin nhắn thì hai danh sách rỗng, không lỗi",
      d2.get("ok") and d2.get("files") == [] and d2.get("links") == [])

print("")
if fails:
    print(f"ĐỎ {len(fails)} mục")
    sys.exit(1)
print("Tất cả xanh.")
