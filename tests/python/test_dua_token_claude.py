"""Hai người dùng chung một tài khoản Claude không còn đá nhau văng đăng nhập.

    python tests/run.py dua_token_claude

Bệnh thật (chủ repo báo 02/09, hai vợ chồng dùng chung một javis.minhquy.vn): Javis chạy
nhiều tiến trình `claude` song song trên ĐÚNG MỘT file ~/.claude/.credentials.json. Refresh
token OAuth là loại dùng một lần, nên khi token hết hạn đúng lúc hai người cùng chat thì lượt
chạy sau ăn "refresh token was already used" - còn file thì vẫn lành, nên người kia không
thấy gì. Đúng cái hình "vợ bị văng, chồng dùng bình thường".

Hai thứ phải đúng, và chúng NGƯỢC CHIỀU nhau nên phải canh cả hai:
  1. Cuộc đua bị nhận ra là cuộc đua -> KHÔNG thắp đèn đỏ "mất đăng nhập", không đuổi người
     dùng đi kết nối lại (bấm Ngắt còn xoá bản sao lưu của vệ sĩ credentials, tức đẩy họ từ
     một lượt hỏng sang mất đăng nhập THẬT).
  2. Mất đăng nhập THẬT vẫn phải bị bắt như cũ. Nới tay ở (1) mà nuốt luôn ca này là giấu
     mất một lỗi người dùng buộc phải xử lý.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import json
import os
import tempfile
import time

import claude_token_gate as gate  # noqa: E402

fails = []


def check(name, cond, them=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(them) + "]") if not cond and them else ""))
    if not cond:
        fails.append(name)


def _dat_cred(han_giay, co_token=True):
    """Dựng ~/.claude/.credentials.json giả trong HOME tạm. han_giay = còn bao lâu nữa hết hạn."""
    d = tempfile.mkdtemp(prefix="javis-cred-")
    os.environ["HOME"] = d
    p = gate.duong_cred()
    p.parent.mkdir(parents=True, exist_ok=True)
    oa = {"expiresAt": int((time.time() + han_giay) * 1000)}
    if co_token:
        oa["accessToken"] = "sk-fake"
        oa["refreshToken"] = "rt-fake"
    p.write_text(json.dumps({"claudeAiOauth": oa}), encoding="utf-8")
    return p


# ---- 1. Phân biệt CUỘC ĐUA với MẤT ĐĂNG NHẬP THẬT ----------------------------
DUA = ("Your access token could not be refreshed because your refresh token was "
       "already used. Please log out and sign in again.")
THAT = "Failed to authenticate: OAuth session expired and could not be refreshed"

check("nhận ra câu của cuộc đua", gate.la_loi_tranh_lam_moi(DUA))
# Mốc nhận dạng phải là "already used". Bắt theo "could not be refreshed" trơn là nuốt luôn
# ca hết phiên THẬT (vụ Claude 27/07) - lúc đó người dùng bắt buộc phải đăng nhập lại mà màn
# hình lại bảo "gửi lại tin là được", tức treo họ ở đó mãi.
check("CANARY: KHÔNG bắt nhầm mất đăng nhập thật thành cuộc đua",
      not gate.la_loi_tranh_lam_moi(THAT))
check("chuỗi rỗng không phải cuộc đua", not gate.la_loi_tranh_lam_moi(""))

# ---- 2. Đọc hạn token, và chịu được mọi kiểu file hỏng ------------------------
_dat_cred(3600)
check("đọc được hạn token từ file", abs(gate.han_token() - (time.time() + 3600)) < 5)
check("còn token thì biết là còn đăng nhập", gate.con_dang_nhap())

_dat_cred(3600, co_token=False)
check("file lành nhưng hết token thì biết là đã đăng xuất", not gate.con_dang_nhap())

gate.duong_cred().write_text("{ hỏng", encoding="utf-8")
check("file hỏng không làm nổ, trả 0", gate.han_token() == 0.0)
check("file hỏng thì coi như chưa đăng nhập", not gate.con_dang_nhap())

os.environ["HOME"] = tempfile.mkdtemp(prefix="javis-nohome-")
# macOS cất token trong Keychain nên KHÔNG có file. Không đọc được hạn thì tuyệt đối không
# được xếp hàng - làm vậy là bắt mọi lượt chat trên Mac chờ vô cớ.
check("CANARY: không có file (macOS) thì trả 0, không xếp hàng", gate.han_token() == 0.0)
check("và xếp hàng trả rỗng ngay", asyncio.run(gate.xep_hang()) == "")


# ---- 3. Cổng xếp hàng: chỉ chặn trong cửa sổ hẹp -----------------------------
_dat_cred(3600)
# Token còn tốt là ĐƯỜNG NHANH: đây là 99.9% số lượt chat, thêm một mili giây ở đây cũng là
# thuế đánh lên mọi người để chữa một ca hiếm.
# Đo theo NỀN chứ không theo mili giây tuyệt đối. Bản cũ chốt 50ms, mà chỉ riêng
# `asyncio.run` dựng rồi dẹp một event loop đã tốn vài chục ms trên máy chạy CI đang tải
# nặng - tức là ngưỡng đó đo tốc độ máy chứ không đo "có xếp hàng hay không". Đường chậm
# thật thì chờ tới lượt làm mới token, tính bằng GIÂY, nên chỉ cần cách nền vài lần là đủ
# tách bạch. Sàn 0.5s để máy nhanh (nền ~0) không biến phép so thành vô nghĩa.
async def _rong():
    return ""


_t = time.time()
asyncio.run(_rong())
_nen = time.time() - _t          # chi phí dựng/dẹp event loop trên chính máy này

t0 = time.time()
nhan = asyncio.run(gate.xep_hang())
_mat = time.time() - t0
check("token còn hạn thì không xếp hàng", nhan == "", nhan)
check(f"và đường nhanh phải THẬT nhanh ({_mat*1000:.0f}ms, nền {_nen*1000:.0f}ms)",
      _mat < max(_nen * 5, 0.5), f"{_mat:.3f}s")

_dat_cred(10)   # trong cửa sổ CHUAN_BI_S
gate._MOC_DI_TRUOC = 0.0
check("token sắp hết hạn: người đầu tiên được đi luôn",
      asyncio.run(gate.xep_hang()) == "di-truoc")


async def _nguoi_toi_sau():
    """Người thứ hai tới lúc người đầu đang làm mới. Giả lập lượt kia ghi cặp token mới."""
    async def _lam_moi_xong():
        await asyncio.sleep(0.6)
        _dat_cred(3600)          # người đi trước ghi hạn mới -> người sau phải nhận ra
    asyncio.ensure_future(_lam_moi_xong())
    return await gate.xep_hang()


t0 = time.time()
nhan = asyncio.run(_nguoi_toi_sau())
cho = time.time() - t0
check("người tới sau CHỜ tới khi có token mới rồi mới chạy", nhan == "cho", nhan)
check("và chờ đúng lúc cần, không chờ hết trần", 0.4 < cho < gate.CHO_TOI_DA_S)

# Lượt đi trước chết giữa chừng (bị Dừng, bị watchdog giết) thì mốc giữ phải TỰ HẾT HẠN.
# Thiếu điều này là một lượt chết khoá mọi lượt sau vĩnh viễn - đổi một lỗi hiếm lấy một lỗi
# chết người.
_dat_cred(10)
gate._MOC_DI_TRUOC = time.time() - gate.GIU_TOI_DA_S - 1
check("CANARY: lượt đi trước chết thì lượt sau vẫn được đi",
      asyncio.run(gate.xep_hang()) == "di-truoc")


# ---- 4. Engine phải nói đúng bệnh, và việc nền phải nhảy mắt -----------------
_ma = (ROOT / "server" / "claude_sdk_engine.py").read_text(encoding="utf-8")
check("engine gọi cổng xếp hàng trước khi chạy claude",
      "claude_token_gate" in _ma and "xep_hang()" in _ma)
# Điều kiện phải là ĐUA **VÀ** CÒN ĐĂNG NHẬP. Thiếu vế sau thì một máy đã đăng xuất thật mà
# lỡ có chữ "already used" trong output cũng được tha, và đèn báo não im luôn.
check("CANARY: chỉ tha khi file credentials VẪN còn token",
      "la_loi_tranh_lam_moi" in _ma and "con_dang_nhap()" in _ma)
check("cuộc đua KHÔNG thắp đèn đỏ mất đăng nhập",
      "if dua_token:\n                connect_health.engine_run_ok" in _ma)
check("và câu trả về nói rõ phiên không mất", "Phiên KHÔNG mất" in _ma)

_aux = (ROOT / "server" / "aux_engine.py").read_text(encoding="utf-8")
# Việc nền KHÔNG gửi lại được, nên nó vẫn phải coi lượt này là hỏng và nhảy sang bộ não kế
# tiếp. Đọc CỜ chứ không khớp chữ: câu người đọc đã viết lại thành tiếng Việt dễ hiểu, khớp
# chữ là gãy ngay lần sửa câu tiếp theo.
check("việc nền nhảy mắt kế tiếp khi gặp cuộc đua", 'ev.get("dua_token")' in _aux)
check("CANARY: đọc cờ, không khớp chữ tiếng Việt",
      "Phiên KHÔNG mất" not in _aux)

print()
if fails:
    print(f"ĐỎ {len(fails)} mục")
    raise SystemExit(1)
print("Tất cả xanh.")
