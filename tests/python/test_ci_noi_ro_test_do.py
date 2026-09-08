"""CI phải NÓI RÕ test nào đỏ, và phép đo thời gian không được đo tốc độ máy.

    python tests/run.py ci_noi_ro_test_do      (KHÔNG mạng)

Hai bài học từ vụ 03/09/2026, cùng một lần CI đỏ.

**Một: log không nói được test nào đỏ.**
CI không chạy `tests/run.py` (thứ có sẵn phần tổng kết ở cuối) mà chạy một vòng lặp bash
riêng, in tên file TRƯỚC khi chạy rồi đi tiếp qua chỗ đỏ. Nên tên test đỏ nằm lẫn giữa hàng
nghìn dòng ở GIỮA log, còn phần đuôi - thứ duy nhất đọc được khi log bị cắt - lại là test
cuối cùng, luôn xanh. Kết quả: biết CI đỏ mà không biết đỏ ở đâu, phải tải nguyên log về mới
lần ra. Nay vòng lặp gom tên lại in ở CUỐI và đẩy lên phần tóm tắt của GitHub.

**Hai: mấy phép đo thời gian đang đo TỐC ĐỘ MÁY.**
Cùng một commit chạy hai lần song song: run `push` xanh, run `pull_request` đỏ. Bước test
Python của run đỏ mất 4 phút, run xanh mất 3 phút - máy chạy hôm đó chậm hơn hẳn. Những
ngưỡng chép tay kiểu `< 0.05` hay `< 0.3` giây không tách được "mã sai" với "máy chậm", nên
chúng đỏ oan và làm mòn niềm tin vào CI, thứ đắt hơn nhiều so với cái chúng canh.

Cách sửa đã áp dụng, và cũng là luật cho người viết test sau: **suy ngưỡng ra từ chính hằng
số mà phép đo đang canh** (thời gian giả lập CLI chậm, ân hạn kill, thời gian một nguồn treo),
hoặc **so với một phép đo nền lấy ngay trên máy đó**. Đừng chép tay một con số mili giây.
File `test_khoi_dong_nhe.py` đã đi trước một bước bằng cách đo TỈ LỆ so với `import fastapi`,
lý do ghi ngay trong đó.

Test này ghim cả hai, vì cả hai đều là loại rất dễ bị lặng lẽ rút gọn lại lúc dọn code.
"""
from _paths import ROOT  # noqa: E402,F401
import re

CI = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
TESTS = ROOT / "tests" / "python"

_fails = []


def check(ten, dieu_kien, them=""):
    print(("ok   " if dieu_kien else "FAIL ") + ten
          + (("  [" + str(them) + "]") if them and not dieu_kien else ""))
    if not dieu_kien:
        _fails.append(ten)


def _doc(ten):
    return (TESTS / ten).read_text(encoding="utf-8")


# ============================================================
# 1. CI gom tên test đỏ rồi in ở CUỐI
# ============================================================
# Cả hai bước (JS và Python) đều phải có, không chỉ một: lần đỏ 03/09 rơi vào bước Python,
# nhưng bước JS có đúng cùng hình dạng vòng lặp nên cùng một khe hở.
for nhan, lenh in (("JS", "node"), ("Python", "python")):
    khoi = re.search(r"- name: Chạy test " + nhan + r"[\s\S]*?exit \$status", CI)
    khoi = khoi.group(0) if khoi else ""
    check(f"bước test {nhan}: có gom tên file đỏ lại",
          'dsdo="$dsdo $(basename "$f")"' in khoi, khoi[:120])
    check(f"bước test {nhan}: in danh sách đỏ ở CUỐI bước",
          f'echo "ĐỎ (test {nhan}):$dsdo"' in khoi)
    check(f"bước test {nhan}: đẩy luôn lên tóm tắt của GitHub (thấy ngay trên trang Actions)",
          "$GITHUB_STEP_SUMMARY" in khoi)
    # Gom tên mà nuốt mất mã thoát thì CI xanh trong khi test đỏ - hỏng nặng hơn lỗi gốc.
    check(f"bước test {nhan}: vẫn thoát với mã lỗi", "exit $status" in khoi)
    check(f"bước test {nhan}: vẫn chạy hết mọi file chứ không dừng ở file đỏ đầu tiên",
          "status=1" in khoi and "break" not in khoi)

# `do` là TỪ KHOÁ của bash. Đặt tên biến là `do` thì tuỳ chỗ mà shell hiểu khác nhau, và lỗi
# kiểu đó chỉ lộ ra lúc CI chạy thật chứ không lộ lúc đọc file.
check("CANARY: không dùng `do` làm tên biến (từ khoá của bash)",
      not re.search(r"^\s*do=", CI, re.M))

check("lý do vì sao phải in ở cuối được ghi ngay trong file",
      "phần đuôi" in CI or "cắt" in CI)


# ============================================================
# 2. Phép đo thời gian buộc vào hằng số, không chép tay mili giây
# ============================================================
# Mỗi mục dưới đây là một chỗ ĐÃ từng chép tay một con số và đã được sửa. Ghim lại đúng cái
# tên hằng số, vì bản sửa rất dễ bị "dọn" ngược về một con số cho gọn mắt.
_neo = [
    ("test_khoi_dong_cham.py", ["CHAM_S", "TUAN_TU_S", "TRAN_S", "TREO_S"],
     [r"mat *< *1\.0", r"mat2 *< *1\.5"],
     "trần suy từ số nguồn và thời gian mỗi nguồn"),
    ("test_settings_khong_treo_theo_cli.py", ["CLI_CHAM_S"], [r"mat *< *0\.3"],
     "trần suy từ chính thời gian CLI giả lập"),
    ("test_dua_token_claude.py", ["_nen"], [r"time\.time\(\) *- *t0 *< *0\.05"],
     "so với phép đo nền trên chính máy đó"),
    ("test_terminal.py", ["TRAN_NGAY_S"], [r"tre *< *0\.5"],
     "một trần chung cho mọi phép đo 'trả về ngay'"),
    ("test_claude_khong_tu_dang_xuat.py", ["AN_HAN_S"], [r"< *2\.5"],
     "trần buộc vào ân hạn thật của _kill_tree"),
]
for ten, phai_co, khong_duoc, y in _neo:
    src = _doc(ten)
    for hang in phai_co:
        check(f"{ten}: còn dùng {hang} ({y})", hang in src)
    for xau in khong_duoc:
        check(f"CANARY: {ten} không quay lại ngưỡng chép tay /{xau}/",
              re.search(xau, src) is None)

# Ngưỡng cực hẹp là dấu hiệu chắc chắn của phép đo tốc độ máy: không có lỗi thật nào chỉ lộ
# ra ở mốc dưới 200ms mà không lộ ra ở mốc rộng hơn, trong khi một nhịp GC hay một lần đổi
# tiến trình trên máy chạy CI đã đủ vượt qua nó.
_HEP = re.compile(r"(?:time\.time\(\)|perf_counter\(\))[^\n]*?-[^\n]*?<\s*0\.(?:0\d|1\d?)\b")
_pham = []
for f in sorted(TESTS.glob("test_*.py")):
    if f.name == "test_ci_noi_ro_test_do.py":
        continue                      # chính file này chứa mẫu regex ở trên
    for i, dong in enumerate(f.read_text(encoding="utf-8").split("\n"), 1):
        if _HEP.search(dong):
            _pham.append(f"{f.name}:{i}")
check("CANARY: không test nào chốt thời gian trôi dưới 0.2s (đó là đo tốc độ máy)",
      not _pham, _pham[:5])

print()
if _fails:
    print(f"ĐỎ {len(_fails)} mục: " + "; ".join(_fails[:4]))
    raise SystemExit(1)
print("Tất cả xanh.")
