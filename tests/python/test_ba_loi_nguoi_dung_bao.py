"""Ba lỗi người dùng thật báo ngày 2026-08-04, và cái chốt giữ cho chúng không quay lại.

    python tests/run.py ba_loi

Cả ba đều là loại "chạy trên máy dev không đời nào lộ ra":

1. CÀI ĐẶT CHẾT NGAY BƯỚC 2 TRÊN WINDOWS TIẾNG VIỆT. `pip install -r requirements.txt` nổ
   UnicodeDecodeError giữa `setup.bat [2/3]`. Nguyên nhân: pip đọc file bằng `auto_decode()`,
   không thấy BOM và không thấy khai báo encoding kiểu PEP-263 ở HAI DÒNG ĐẦU thì nó decode
   bằng `locale.getpreferredencoding()` - trên Windows tiếng Việt là cp1252/cp1258, mà file
   có chú thích tiếng Việt. Máy Linux/macOS locale UTF-8 nên không bao giờ thấy, và
   `chcp 65001` trong setup.bat cũng không cứu (đổi codepage console, không đổi ANSI codepage).

2. MODEL BÁO SAI NGUYÊN NHÂN KHI BỊ CHẶN GHI FILE. Việc Kanban chạy mức `suggest` thì
   `javis_write_file` từ chối - đúng thiết kế. Nhưng câu từ chối cũ mơ hồ, model đọc xong tự
   dựng ra một nguyên nhân nghe hợp lý mà sai hoàn toàn: người dùng nhận được "môi trường
   filesystem đang lỗi quyền sandbox" rồi đi tìm lỗi ổ đĩa, trong khi thứ cần làm chỉ là nâng
   mức việc lên Ghi nháp. Thông báo cho MÁY ĐỌC cũng là giao diện, sai là hại thật.

3. CHẠM TRẦN VÒNG GỌI TOOL RỒI DỪNG, KHÔNG CÓ LỐI THOÁT. Con số 8 ghim cứng ở ba chỗ khác
   nhau trong engine.py, và câu báo chỉ nêu con số chứ không nói chỉnh ở đâu.

KHÔNG mạng.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401  - nạp server/ vào sys.path
import os
import re
import sys

fails = []


def check(name, cond, them=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(them) + "]") if them and not cond else ""))
    if not cond:
        fails.append(name)


# ============================================================
# 1. requirements.txt phải đọc được bằng ĐÚNG bộ giải mã của pip, kể cả locale cp1252
# ============================================================
REQ = ROOT / "requirements.txt"
raw = REQ.read_bytes()

check("requirements.txt có chú thích tiếng Việt (nếu không thì test này vô nghĩa)",
      any(b > 127 for b in raw))

hai_dong_dau = raw.split(b"\n")[:2]
check("CANARY: khai báo encoding nằm trong HAI DÒNG ĐẦU (pip chỉ soi đúng 2 dòng)",
      any(d[0:1] == b"#" and re.search(rb"coding[:=]\s*([-\w.]+)", d) for d in hai_dong_dau),
      [d[:40] for d in hai_dong_dau])

# Chạy CHÍNH hàm của pip, không mô phỏng lại: mô phỏng lại là tự chấm bài mình.
try:
    from pip._internal.utils.encoding import auto_decode
except Exception as e:                                   # pip quá mới đã bỏ auto_decode
    print(f"ok   (bỏ qua) pip ở máy này không còn auto_decode: {e}")
    auto_decode = None

if auto_decode is not None:
    import locale
    that = locale.getpreferredencoding
    try:
        # Giả lập đúng máy người dùng: Windows tiếng Việt, ANSI codepage cp1252.
        locale.getpreferredencoding = lambda do_setlocale=True: "cp1252"
        try:
            auto_decode(raw)
            ok_cp1252 = True
        except UnicodeDecodeError:
            ok_cp1252 = False
        check("CANARY: pip đọc được requirements.txt khi locale là cp1252 (máy Windows VN)",
              ok_cp1252)
        locale.getpreferredencoding = lambda do_setlocale=True: "cp1258"
        try:
            auto_decode(raw)
            ok_cp1258 = True
        except UnicodeDecodeError:
            ok_cp1258 = False
        check("pip đọc được cả khi locale là cp1258", ok_cp1258)
    finally:
        locale.getpreferredencoding = that

# Dòng khai báo là comment nên pip bỏ qua khi phân giải - đừng để nó thành một "gói" tên lạ.
dong1 = raw.split(b"\n")[0]
check("dòng khai báo là comment, không thành một requirement", dong1.startswith(b"#"))

# ============================================================
# 2. Câu từ chối ghi file phải NÓI ĐÚNG nguyên nhân và VIỆC CẦN LÀM
# ============================================================
import mcp_hub  # noqa: E402

src = (SERVER / "mcp_hub.py").read_text(encoding="utf-8")
i = src.find("async def _write(args):")
khoi = src[i:i + 1400]

check("tìm được nhánh từ chối ghi", i > 0 and "readonly" in khoi)
check("CANARY: nói rõ KHÔNG phải lỗi sandbox (đây chính là câu model bịa ra)",
      "sandbox" in khoi.lower() and "KHÔNG phải" in khoi)
check("nói rõ không phải lỗi ổ đĩa", "ổ đĩa" in khoi)
check("chỉ đúng chỗ chỉnh: trang Việc + mức Ghi nháp",
      "trang Việc" in khoi and "Ghi nháp" in khoi)
check("dặn model đừng thử ghi lại mà trả nội dung ra câu trả lời",
      "ĐỪNG thử ghi lại" in khoi)

# Chạy THẬT nhánh từ chối, không chỉ đọc chữ trong nguồn.
import asyncio  # noqa: E402
import tempfile  # noqa: E402
from pathlib import Path  # noqa: E402

vault = Path(tempfile.mkdtemp(prefix="javis-write-test-"))
tools, route = mcp_hub._builtin_tools("suggest", str(vault))
ghi = route.get("javis_write_file")
check("mức suggest vẫn THẤY tool ghi file (để model biết nó tồn tại mà xin nâng quyền)",
      ghi is not None)
if ghi:
    kq = asyncio.run(ghi["call"]({"path": "thu.md", "content": "xin chao"}))
    check("mức suggest thì từ chối thật", kq.startswith("ERROR"))
    check("và KHÔNG tạo file nào trên đĩa", not (vault / "thu.md").exists())
    check("câu trả về mang đủ thông tin để người dùng tự sửa",
          "Ghi nháp" in kq and "sandbox" in kq.lower(), kq[:80])

tools2, route2 = mcp_hub._builtin_tools("auto", str(vault))
kq2 = asyncio.run(route2["javis_write_file"]["call"]({"path": "thu.md", "content": "xin chao"}))
check("mức auto thì ghi được thật", not kq2.startswith("ERROR") and (vault / "thu.md").is_file(),
      kq2[:80])

# ============================================================
# 3. Trần vòng gọi tool: một chỗ khai, chỉnh được, và báo có việc-cần-làm
# ============================================================
import engine  # noqa: E402

esrc = (SERVER / "engine.py").read_text(encoding="utf-8")
check("CANARY: không còn chỗ nào ghim cứng range(8)", "for _ in range(8):" not in esrc)
check("không còn câu báo ghim cứng con số 8", "giới hạn 8 vòng gọi tool" not in esrc)
check("ba vòng lặp tool đều đọc từ một chỗ",
      esrc.count("for _ in range(_max_tool_rounds()):") == 3,
      esrc.count("for _ in range(_max_tool_rounds()):"))

that_env = os.environ.get("JAVIS_MAX_TOOL_ROUNDS")
try:
    # 0.47.1: mặc định 8 -> 30, kẹp trên 40 -> 120. Người dùng chạm trần 8 liên tục với việc
    # nhiều bước bình thường (27/08); phanh chống kẹt vòng lặp chuyển sang _LapGuard bên dưới.
    for dat, mong in ((None, 30), ("3", 3), ("40", 40), ("999", 120), ("0", 1), ("-5", 1),
                      ("abc", 30), ("", 30)):
        os.environ.pop("JAVIS_MAX_TOOL_ROUNDS", None)
        if dat is not None:
            os.environ["JAVIS_MAX_TOOL_ROUNDS"] = dat
        got = engine._max_tool_rounds()
        check(f"trần với biến môi trường {dat!r} -> {mong}", got == mong, got)
    os.environ.pop("JAVIS_MAX_TOOL_ROUNDS", None)
    msg = engine._het_vong_msg()
    check("câu báo nêu đúng con số đang áp dụng", "30 vòng" in msg, msg[:70])
    check("câu báo chỉ ra biến môi trường để nâng trần", "JAVIS_MAX_TOOL_ROUNDS" in msg)
    check("câu báo gợi ý chia nhỏ yêu cầu", "chia nhỏ" in msg)
    check("câu báo nói rõ câu trả lời có thể còn dở", "còn dở" in msg)
    os.environ["JAVIS_MAX_TOOL_ROUNDS"] = "20"
    check("đổi biến thì câu báo đổi theo", "20 vòng" in engine._het_vong_msg())
finally:
    os.environ.pop("JAVIS_MAX_TOOL_ROUNDS", None)
    if that_env is not None:
        os.environ["JAVIS_MAX_TOOL_ROUNDS"] = that_env

# ---- Phanh kẹt vòng lặp (_LapGuard): soi đúng bệnh thay vì đếm số ----
g = engine._LapGuard()
g.ghi([("doc_file", '{"path":"a.md"}')])
check("vòng đầu không nhắc", g.loi_nhac() == "" and not g.ket())
g.ghi([("doc_file", '{"path":"a.md"}')])
check("lặp lần 2 chưa nhắc", g.loi_nhac() == "")
g.ghi([("doc_file", '{"path":"a.md"}')])
check("lặp y hệt lần 3 thì nhắc", "ĐỪNG gọi lại" in g.loi_nhac())
g.ghi([("doc_file", '{"path":"a.md"}')])
check("lần 4 chưa dừng (đã nhắc, cho một cơ hội)", not g.ket())
g.ghi([("doc_file", '{"path":"a.md"}')])
check("lặp y hệt lần 5 thì dừng", g.ket())
check("câu dừng nói rõ kẹt vòng lặp + việc cần làm",
      "kẹt vòng lặp" in engine._loi_ket_vong() and "đổi model" in engine._loi_ket_vong())

g2 = engine._LapGuard()
g2.ghi([("doc_file", '{"path":"a.md"}')])
g2.ghi([("doc_file", '{"path":"a.md"}')])
g2.ghi([("ghi_file", '{"path":"a.md"}')])   # đổi tool -> chuỗi lặp đứt
g2.ghi([("doc_file", '{"path":"a.md"}')])   # đọc lại sau khi ghi: hợp lệ, không bị bắt oan
check("đổi tool/tham số thì chuỗi lặp đứt (đọc-sửa-đọc lại không bị bắt oan)",
      g2.lap == 1 and g2.loi_nhac() == "" and not g2.ket())

g3 = engine._LapGuard()
for _ in range(3):
    g3.ghi([("b", "{}"), ("a", "{}")])   # thứ tự trong 1 vòng không quan trọng - vẫn là lặp
check("cùng bộ tool khác thứ tự vẫn tính là lặp", g3.lap == 3)

check("cả ba vòng tool đều gắn phanh kẹt vòng lặp",
      esrc.count("guard = _LapGuard()") == 3, esrc.count("guard = _LapGuard()"))

check("biến mới có trong tài liệu env",
      "JAVIS_MAX_TOOL_ROUNDS" in (ROOT / "docs" / "16-cau-hinh-env.md").read_text(encoding="utf-8"))

if fails:
    print("\nFAIL - test_ba_loi_nguoi_dung_bao: " + str(len(fails)) + " lỗi: " + ", ".join(fails))
    sys.exit(1)
print("\nOK - test_ba_loi_nguoi_dung_bao: tất cả pass")
