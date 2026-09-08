"""Đường LÙI của trình cập nhật: hỏng ở bước nào thì phải NÓI RA bước đó.

    python tests/run.py update_lui_hong

Không cần pytest, không chạm mạng, không chạy git hay pip thật (mọi lệnh đều thay bằng hàm giả).

Bối cảnh: người dùng báo ngày 04/09 - "nút cập nhật thường lỗi không cập nhật được, fallback bản
cũ lỗi luôn, khiến toàn die hẳn phải dùng con khác sửa". Đọc mã thì thấy đường lùi có hai bước
quyết định mà KHÔNG bước nào kiểm mã lỗi: `git reset --hard` và `pip install`.

Hậu quả không chỉ là im lặng. Nếu `git reset` trượt thì mã nguồn VẪN LÀ BẢN MỚI ĐANG HỎNG, nên
bật lại bao nhiêu lần cũng hỏng y hệt - trong khi thông báo cũ ("Bản mới lỗi và lùi bản cũng chưa
lên. Xem update.log.") lại khiến người ta tin rằng mã đã về bản cũ. Hai tình huống ấy cần hai
cách chữa khác hẳn nhau, nên nói sai còn tệ hơn không nói.

Test này CHẠY THẬT `updater.main()` với git/pip/server giả, rồi đọc trạng thái nó ghi ra.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import os
import sys
import tempfile

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-lui-test-")

import update_state as us   # noqa: E402
import updater              # noqa: E402

_fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)


class KetQuaGia:
    def __init__(self, rc=0, out="", err=""):
        self.returncode, self.stdout, self.stderr = rc, out, err


def chay_lui(*, reset_rc=0, head="old1234567890", pip_rc=0, lui_len=False, pip_moi_rc=0):
    """Diễn lại một lượt cập nhật hỏng, rồi trả về trạng thái cuối cùng.

    `health` mặc định False cho MỌI lần gọi: bản mới không lên (nên phải lùi), và bản cũ cũng
    không lên (nên phải báo lỗi) - đúng cảnh người dùng mô tả. Truyền `lui_len=True` để bản mới
    vẫn hỏng nhưng bản cũ lên lại được."""
    goc = (updater.run, updater.poll_health, updater.start_server, updater.stop_server,
           updater.service_mode, updater.read_current_version, updater.git_dirty,
           updater.pip_install, sys.argv)
    lan_pip = {"n": 0}

    def run_gia(cmd):
        if cmd[:2] == ["git", "reset"]:
            return KetQuaGia(reset_rc)
        if cmd[:2] == ["git", "rev-parse"] and cmd[-1] == "HEAD":
            return KetQuaGia(0, head)
        if cmd[:2] == ["git", "pull"]:
            return KetQuaGia(0, "Updating abc..def")
        return KetQuaGia(0, "")

    def pip_gia():
        lan_pip["n"] += 1
        return KetQuaGia(pip_moi_rc if lan_pip["n"] == 1 else pip_rc)

    try:
        updater.run = run_gia
        # Lần gọi ĐẦU là kiểm bản mới (luôn hỏng, nếu không thì đã chẳng có đường lùi để test);
        # lần sau là kiểm bản cũ sau khi lùi.
        lan_health = {"n": 0}

        def health_gia(*a, **k):
            lan_health["n"] += 1
            return lui_len and lan_health["n"] > 1

        updater.poll_health = health_gia
        updater.start_server = lambda *a, **k: None
        updater.stop_server = lambda *a, **k: None
        updater.service_mode = lambda *a, **k: "nohup"
        updater.read_current_version = lambda: "9.9.9"     # có đổi -> không rơi vào version_mismatch
        updater.git_dirty = lambda: False
        updater.pip_install = pip_gia
        sys.argv = ["updater.py", "--old-sha", "old1234567890abcdef",
                    "--old-version", "0.55.28", "--target", "9.9.9", "--port", "7777"]
        ma = updater.main()
    finally:
        (updater.run, updater.poll_health, updater.start_server, updater.stop_server,
         updater.service_mode, updater.read_current_version, updater.git_dirty,
         updater.pip_install, sys.argv) = goc
    return ma, us.read_state()


# ─────────── 1. git reset TRƯỢT: chuyện nặng nhất, phải nói thẳng ───────────
ma, st = chay_lui(reset_rc=1, head="moi9999999999")
check("lùi hỏng thì trả mã lỗi", ma == 1)
check("kết quả ghi đúng là rollback_failed", st.get("result") == "rollback_failed")
loi = st.get("error") or ""
check("nói rõ là LÙI MÃ NGUỒN không thành", "lùi mã nguồn KHÔNG thành" in loi)
# Câu quan trọng nhất của cả file này: người dùng phải biết máy họ đang chạy mã NÀO.
check("nói rõ mã nguồn vẫn là bản mới đang lỗi", "vẫn là bản mới đang lỗi" in loi)
check("đưa luôn lệnh chữa, không bắt đi đọc log", "git reset --hard old12345678" in loi)

# ─────────── 2. reset trả 0 nhưng HEAD KHÔNG nhúc nhích ───────────
# Có thật trên Windows: một tiến trình còn giữ file thì reset báo thành công một phần.
# Chỉ tin mã trả về là bỏ lọt đúng ca này.
ma, st = chay_lui(reset_rc=0, head="moi9999999999")
check("reset báo OK mà HEAD sai thì VẪN coi là hỏng", "lùi mã nguồn KHÔNG thành" in (st.get("error") or ""))

# ─────────── 3. pip của bản cũ hỏng ───────────
ma, st = chay_lui(reset_rc=0, head="old1234567890", pip_rc=1)
loi = st.get("error") or ""
check("pip của bản cũ hỏng thì nêu ra", "cài lại thư viện cho bản cũ thất bại" in loi)
check("kèm lệnh chạy lại", "pip install -r requirements.txt" in loi)
check("và KHÔNG đổ oan cho git khi git đã lùi đúng", "lùi mã nguồn KHÔNG thành" not in loi)

# ─────────── 4. Mọi bước đều đúng mà server vẫn không lên ───────────
# Không có gì để đổ lỗi thì phải nói ra điều đó, chứ đừng bịa một nguyên nhân.
ma, st = chay_lui(reset_rc=0, head="old1234567890", pip_rc=0)
loi = st.get("error") or ""
check("lùi đúng, pip xong mà vẫn không lên thì nêu nghi vấn cổng bị giữ",
      "cổng đang bị tiến trình khác giữ" in loi)
check("và không bịa ra lỗi git hay pip",
      "lùi mã nguồn KHÔNG thành" not in loi and "cài lại thư viện" not in loi)

# ─────────── 5. Bản mới cũng không cài nổi thư viện ───────────
ma, st = chay_lui(reset_rc=0, head="old1234567890", pip_rc=0, pip_moi_rc=1)
check("chỉ ra rằng lỗi nhiều khả năng ở môi trường, không ở mã nguồn",
      "lỗi nằm ở môi" in (st.get("error") or ""))

# ─────────── 6. Lùi THÀNH CÔNG thì không được kêu ca gì ───────────
ma, st = chay_lui(reset_rc=0, head="old1234567890", lui_len=True)
check("bản cũ lên lại được thì báo rolled_back", st.get("result") == "rolled_back")
check("và trả mã 0", ma == 0)

print()
if _fails:
    print(f"FAIL - test_update_lui_hong: {len(_fails)} lỗi: {_fails}")
    sys.exit(1)
print("OK - test_update_lui_hong: tất cả pass")
