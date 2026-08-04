"""Plugin zalo-image: gửi ảnh/file qua Zalo bằng phiên đã quét QR.

    python tests/run.py zalo_image

Không mạng, không gọi npx thật: thay hàm chạy tiến trình con bằng bản ghi lại argv, rồi soi
lệnh dựng ra có ĐÚNG không. Những gì file này canh:

1. RÀO ĐƯỜNG DẪN. Tool nhận đường dẫn từ chính câu chat, và đầu ra là GỬI RA NGOÀI, không thu
   hồi được. Không có rào "phải nằm trong brain" thì một câu khéo léo là tuồn được file khoá
   hay /etc/passwd ra một cuộc chat Zalo bất kỳ. Đây là thứ quan trọng nhất ở đây.
2. NHIỀU TÀI KHOẢN THÌ HỎI LẠI, KHÔNG ĐOÁN. Đoán sai nghĩa là tin nhắn đi dưới danh tính
   người khác.
3. DÙNG ĐÚNG HOME CỦA KẾT NỐI. Sai home là CLI không thấy phiên đăng nhập và tự bật QR mới -
   treo tiến trình con cho tới lúc hết giờ.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401  - nạp server/ vào sys.path
import asyncio
import importlib.util
import json
import sys
import tempfile
from pathlib import Path

fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        fails.append(name)


spec = importlib.util.spec_from_file_location(
    "zalo_image_plugin", ROOT / "system" / "plugins" / "zalo-image" / "plugin.py")
P = importlib.util.module_from_spec(spec)
spec.loader.exec_module(P)


class Ctx:
    def __init__(self, root):
        self.vault_root = str(root)


VAULT = Path(tempfile.mkdtemp(prefix="javis-zaloimg-")) / "brain"
(VAULT / "attachments").mkdir(parents=True)
(VAULT / "attachments" / "anh.jpg").write_bytes(b"fake")
(VAULT / "attachments" / "anh2.png").write_bytes(b"fake")
(VAULT / "bao-cao.pdf").write_bytes(b"fake")
NGOAI = VAULT.parent / "bi-mat.txt"
NGOAI.write_text("token", encoding="utf-8")

CTX = Ctx(VAULT)
_da_chay = []


def gia_lap(conns, rc=0, out='{"ok":true}', err=""):
    """Thay hai chỗ chạm thế giới thật: danh sách kết nối, và tiến trình con."""
    P._ket_noi_zalo = lambda: list(conns)
    P.shutil.which = lambda name: "/usr/bin/npx" if name == "npx" else None

    async def _chay(argv, home):
        _da_chay.append({"argv": argv, "home": home})
        return rc, out, err
    P._chay = _chay


MOT = [{"id": "c1", "label": "Zalo chính", "home": "/state/connector-home/zalo-a"}]
HAI = MOT + [{"id": "c2", "label": "Zalo phụ", "home": "/state/connector-home/zalo-b"}]


def goi(args):
    _da_chay.clear()
    return asyncio.run(P._send(args, CTX))


# ============================================================
# 1. Rào đường dẫn - phần quan trọng nhất
# ============================================================
gia_lap(MOT)
r = goi({"thread_id": "t1", "paths": ["../bi-mat.txt"]})
check("CANARY: đường dẫn trèo ra khỏi brain bị chặn", r.startswith("ERROR") and "NGOÀI brain" in r)
check("bị chặn thì KHÔNG chạy lệnh nào cả", not _da_chay)

r = goi({"thread_id": "t1", "paths": [str(NGOAI)]})
check("CANARY: đường dẫn TUYỆT ĐỐI ngoài brain cũng bị chặn", r.startswith("ERROR"))
check("đường dẫn tuyệt đối ngoài brain cũng không chạy lệnh", not _da_chay)

r = goi({"thread_id": "t1", "paths": ["attachments/khong-co.jpg"]})
check("file không tồn tại thì báo NGAY, không đẩy sang CLI",
      r.startswith("ERROR") and "không thấy file" in r and not _da_chay)

r = goi({"thread_id": "t1", "paths": ["attachments/anh.jpg"] * 11})
check("chặn gửi quá nhiều file một lượt", r.startswith("ERROR") and not _da_chay)

# ============================================================
# 2. Tham số thiếu
# ============================================================
check("thiếu thread_id thì nói rõ cách tìm",
      "zalo_search_threads" in goi({"paths": ["attachments/anh.jpg"]}))
check("thiếu paths thì báo lỗi", goi({"thread_id": "t1"}).startswith("ERROR"))

# ============================================================
# 3. Dựng lệnh đúng
# ============================================================
r = goi({"thread_id": "t1", "paths": ["attachments/anh.jpg", "attachments/anh2.png"],
         "caption": "ảnh sản phẩm", "thread_type": 1})
d = json.loads(r)
argv = _da_chay[0]["argv"]
check("gửi thành công trả JSON đọc được", d.get("ok") and d["sent"] == 2 and d["kind"] == "image")
check("chạy đúng package đã ghim", "zalo-agent-cli@1.6.2" in argv)
check("dùng lệnh con send-image cho ảnh", "send-image" in argv and "msg" in argv)
# --json phải đứng TRƯỚC lệnh con: nó là cờ toàn cục của program (commander), đặt sau
# "msg send-image" là commander coi như tham số lạ của lệnh con.
check("cờ --json đứng trước lệnh con", argv.index("--json") < argv.index("msg"))
check("truyền đúng threadId", "t1" in argv)
check("đường dẫn đưa sang CLI là TUYỆT ĐỐI (CLI resolve theo cwd của nó, không phải của Javis)",
      all(Path(a).is_absolute() for a in argv if a.endswith((".jpg", ".png"))))
check("truyền loại hội thoại (nhóm = 1)", argv[argv.index("-t") + 1] == "1")
check("truyền lời nhắn kèm", argv[argv.index("-m") + 1] == "ảnh sản phẩm")
check("CANARY: chạy trong HOME của đúng kết nối Zalo (nếu không CLI đòi quét QR lại)",
      _da_chay[0]["home"] == MOT[0]["home"])

r = goi({"thread_id": "t1", "paths": ["bao-cao.pdf"]})
check("file không phải ảnh thì đi đường send-file",
      json.loads(r)["kind"] == "file" and "send-file" in _da_chay[0]["argv"])

r = goi({"thread_id": "t1", "paths": ["attachments/anh.jpg", "bao-cao.pdf"]})
check("trộn ảnh với file thì từ chối chứ không tự đoán", r.startswith("ERROR") and not _da_chay)

r = goi({"thread_id": "t1", "paths": "attachments/anh.jpg"})
check("paths đưa vào một chuỗi cũng nhận (model hay truyền vậy)", json.loads(r)["sent"] == 1)

r = goi({"thread_id": "t1", "paths": ["attachments/anh.jpg"], "thread_type": 7})
check("thread_type lạ thì kẹp về 0 (cá nhân), không truyền số bậy sang CLI",
      _da_chay[0]["argv"][_da_chay[0]["argv"].index("-t") + 1] == "0")

# ============================================================
# 4. Nhiều tài khoản: hỏi lại, không đoán
# ============================================================
gia_lap(HAI)
r = goi({"thread_id": "t1", "paths": ["attachments/anh.jpg"]})
check("CANARY: hai tài khoản mà không nêu rõ thì TỪ CHỐI, không gửi bừa",
      r.startswith("ERROR") and not _da_chay)
check("và liệt kê ra để chọn", "Zalo chính" in r and "Zalo phụ" in r)
r = goi({"thread_id": "t1", "paths": ["attachments/anh.jpg"], "connection_id": "c2"})
check("nêu rõ connection_id thì gửi bằng đúng tài khoản đó",
      json.loads(r)["account"] == "Zalo phụ" and _da_chay[0]["home"] == HAI[1]["home"])
check("connection_id lạ thì báo lỗi",
      goi({"thread_id": "t1", "paths": ["attachments/anh.jpg"], "connection_id": "xxx"}).startswith("ERROR"))

# ============================================================
# 5. Chưa đủ điều kiện thì nói rõ phải làm gì
# ============================================================
gia_lap([])
r = goi({"thread_id": "t1", "paths": ["attachments/anh.jpg"]})
check("chưa đấu Zalo thì chỉ đúng chỗ cần bấm", "trang Kết nối" in r)

gia_lap(MOT)
P.shutil.which = lambda name: None
check("máy chưa có Node thì nói rõ", "nodejs.org" in goi({"thread_id": "t1", "paths": ["attachments/anh.jpg"]}))

# ============================================================
# 6. Lỗi từ CLI phải nổi lên, không nuốt
# ============================================================
gia_lap(MOT, rc=1, out="", err="Thread not found")
r = goi({"thread_id": "sai", "paths": ["attachments/anh.jpg"]})
check("CLI lỗi thì trả ERROR kèm nguyên nhân", r.startswith("ERROR") and "Thread not found" in r)

# ============================================================
# 7. Khai báo plugin: PHẢI ở mức full (gửi ra ngoài, không rút lại được)
# ============================================================
import fastyaml  # noqa: E402

y = fastyaml.safe_load((ROOT / "system" / "plugins" / "zalo-image" / "plugin.yaml").read_text(encoding="utf-8"))
check("plugin khai min_mode full", y.get("min_mode") == "full")
check("plugin khai đúng tool", y.get("tools") == ["zalo_send_image"])


class ThuCtx:
    def __init__(self):
        self.tools = []

    def register_tool(self, **kw):
        self.tools.append(kw)


tc = ThuCtx()
P.register(tc)
check("register 1 tool", len(tc.tools) == 1 and tc.tools[0]["name"] == "zalo_send_image")
check("CANARY: tool đăng ký ở mức full, chế độ suggest không tự gửi tin được",
      tc.tools[0]["min_mode"] == "full")
check("có check_fn để báo thiếu điều kiện trước khi gọi", callable(tc.tools[0]["check_fn"]))

if fails:
    print("\nFAIL - test_zalo_image: " + str(len(fails)) + " lỗi: " + ", ".join(fails))
    sys.exit(1)
print("\nOK - test_zalo_image: tất cả pass")
