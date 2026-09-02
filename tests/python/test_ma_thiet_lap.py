"""Mã thiết lập: cửa chống CHIẾM ADMIN lần đầu trên server công khai.

    python tests/run.py ma_thiet_lap

Javis chạy public mà chưa có admin thì ai mở được URL cũng tạo được tài khoản admin. Cửa này
đóng lỗ đó: /auth/setup đòi một mã CHỈ in ra log server và nằm trong file bên trong container,
nên chỉ người có quyền vào máy mới tạo được admin.

Khách báo 02/09: vừa vào đã dính "Sai hoặc thiếu MÃ THIẾT LẬP". Cửa hoạt động ĐÚNG, nhưng ba
chỗ làm người ta vấp, và file này canh cả ba:
  1. Mã in ra log nằm CÙNG DÒNG với nhãn "SETUP TOKEN:", nên bôi đen một dòng là dính cả nhãn.
  2. Ô nhập nằm ở mục 2, còn nút bấm và dòng báo lỗi ở tít đáy - bỏ trống thì không thấy ô nào
     đang trống, có người còn không biết là CÓ một ô như vậy.
  3. Cửa chỉ được đóng khi THẬT SỰ cần: chạy local hoặc đã có admin thì không hỏi mã.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import os
import tempfile

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-token-")
os.environ["JAVIS_REQUIRE_LOGIN"] = "1"      # giả lập deploy public

import config as cfgmod  # noqa: E402

fails = []


def check(ten, dieu_kien, them=""):
    print(("ok   " if dieu_kien else "FAIL ") + ten + (("  [" + str(them) + "]") if not dieu_kien and them else ""))
    if not dieu_kien:
        fails.append(ten)


# ---- 1. Gọt thứ người ta THẬT SỰ dán vào ô ----------------------------------
# Đây là thao tác tự nhiên nhất: bôi đen dòng trong log rồi dán. Bản cũ so nguyên cục có nhãn
# với mã thật nên báo "sai mã", tức đúng thao tác tự nhiên nhất lại là thao tác hỏng.
check("CANARY: dán cả dòng log kèm nhãn vẫn ra đúng mã",
      cfgmod.lam_sach_setup_token("      SETUP TOKEN:  abc123") == "abc123")
check("nhãn viết thường cũng gọt được",
      cfgmod.lam_sach_setup_token("setup token: abc123") == "abc123")
check("nhãn tiếng Việt cũng gọt được",
      cfgmod.lam_sach_setup_token("MÃ THIẾT LẬP: abc123") == "abc123")
check("xuống dòng của cat bị cắt", cfgmod.lam_sach_setup_token("abc123\n") == "abc123")
check("nháy kép do copy dính cũng cắt", cfgmod.lam_sach_setup_token('"abc123"') == "abc123")
check("mã sạch thì giữ nguyên", cfgmod.lam_sach_setup_token("abc123") == "abc123")
# Gọt nhãn KHÔNG được biến thành nới lỏng: phần còn lại vẫn phải khớp tuyệt đối.
check("CANARY: gọt nhãn không làm mã sai thành đúng",
      cfgmod.lam_sach_setup_token("SETUP TOKEN: sai-mã") == "sai-mã")

# ---- 2. Cửa mở/đóng đúng lúc ------------------------------------------------
check("public + chưa có admin thì BẮT BUỘC có mã", cfgmod.setup_token_required())
tok = cfgmod.get_or_create_setup_token()
check("sinh được mã và ghi ra file", bool(tok) and len(tok) > 20, tok)
check("gọi lại trả ĐÚNG mã cũ, không sinh mã mới mỗi lần",
      cfgmod.get_or_create_setup_token() == tok)
check("mã đúng thì qua cửa", cfgmod.check_setup_token(tok))
check("và dán cả dòng log kèm nhãn cũng qua được cửa",
      cfgmod.check_setup_token("   SETUP TOKEN:  " + tok + "  "))
check("mã sai thì chặn", not cfgmod.check_setup_token(tok + "x"))
check("bỏ trống thì chặn", not cfgmod.check_setup_token(""))
check("None thì chặn, không nổ", not cfgmod.check_setup_token(None))

# Tạo xong admin là mã bị xoá: để lại một mã còn sống sau khi đã có admin là để lại chìa khoá
# thừa, mà /auth/setup lúc đó cũng đã tự chặn bằng "Đã có tài khoản".
cfgmod.clear_setup_token()
check("CANARY: xoá mã rồi thì mã cũ hết tác dụng", not cfgmod.check_setup_token(tok))
# Không có file mã mà vẫn đòi mã = ngõ cụt vĩnh viễn. Phải sinh lại được.
check("và mã mới sinh lại được, không kẹt vĩnh viễn",
      bool(cfgmod.get_or_create_setup_token()))

# ---- 3. Giao diện phải chỉ ĐÚNG ô đang trống -------------------------------
_app = (ROOT / "dashboard" / "app.js").read_text(encoding="utf-8")
check("có ô nhập mã trong wizard", 'id="wzToken"' in
      (ROOT / "dashboard" / "index.html").read_text(encoding="utf-8"))
# Nút bấm ở đáy, ô nhập ở mục 2. Báo lỗi mà không kéo màn hình thì người dùng nhìn dòng đỏ ở
# đáy và không biết ô nào đang trống - đúng cảnh khách gặp.
check("CANARY: lỗi mã thì KÉO MÀN HÌNH tới đúng ô đó",
      "scrollIntoView" in _app and "_soiOTrong" in _app)
check("chặn ô trống ngay ở client, không phải đợi server trả 403",
      '_tokO.value.trim()' in _app and "Thiếu MÃ THIẾT LẬP" in _app)
check("server trả lỗi mã thì cũng kéo về đúng ô",
      "/MÃ THIẾT LẬP/i.test" in _app)

print()
if fails:
    print(f"ĐỎ {len(fails)} mục: " + "; ".join(fails))
    raise SystemExit(1)
print("Tất cả xanh.")
