"""Nhật ký tự học phải đọc SÂU đủ để phân trang có cái mà lật.

    python tests/run.py nhat_ky_hoc_sau

Vì sao có file này. Dashboard nay phân trang khung "Nhật ký học", nhưng phân trang chỉ có
nghĩa khi nguồn trả về nhiều hơn một trang. Endpoint cũ cắt cứng ở 3 FILE gần nhất, mà nhật
ký ghi mỗi ngày một file - tức là dù người dùng bấm "Sau" bao nhiêu lần cũng chỉ lật quanh
3 ngày. Sửa dashboard mà quên chỗ này thì tính năng trông như đã làm nhưng thực tế không.

Vẫn phải có TRẦN: một brain chạy vài năm có vài trăm file nhật ký, không thể vì ai đó gõ
limit to mà đọc hết cả năm lên rồi nhét vào một response.

KHÔNG mạng. Vault nằm trong thư mục tạm.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401  - nạp server/ vào sys.path
import os
import sys
import tempfile

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-hoclog-"))

fails = []


def check(name, cond, them=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(them) + "]") if them and not cond else ""))
    if not cond:
        fails.append(name)


import main  # noqa: E402
from starlette.testclient import TestClient  # noqa: E402

# 30 ngày nhật ký, mỗi ngày 2 mục -> 60 mục. Bản cũ (3 file) chỉ thấy được 6.
from pathlib import Path  # noqa: E402

VAULT = Path(tempfile.mkdtemp(prefix="javis-hocvault-")) / "brain"
log_dir = VAULT / "Javis" / "learn-log"
log_dir.mkdir(parents=True)
for ngay in range(1, 31):
    (log_dir / f"2026-07-{ngay:02d}.md").write_text(
        f"## [2026-07-{ngay:02d} 08:00] học buổi sáng\nnội dung\n\n"
        f"## [2026-07-{ngay:02d} 20:00] học buổi tối\nnội dung\n",
        encoding="utf-8")

main.cfgmod.gate_active = lambda: False          # test không đụng auth thật
# Endpoint đọc vault qua deps.brain_root chứ không gọi main._brain_root trực tiếp (deps được
# gắn một lần lúc register). Vá đúng chỗ nó thật sự hỏi, không vá chỗ trông giống.
main.learn_feature.deps.brain_root = lambda brain="brain": str(VAULT)
# base_url phải là IP: chưa bật cổng đăng nhập thì web_security siết Host để chống
# DNS-rebinding, mà "testserver" mặc định của TestClient không nằm trong allowlist.
client = TestClient(main.app, base_url="http://127.0.0.1")


def lay(limit):
    r = client.get(f"/learn/log?brain=brain&limit={limit}")
    return r.status_code, (r.json() or {}).get("entries", [])


ma, e10 = lay(10)
check("endpoint trả 200", ma == 200, ma)
check("limit nhỏ vẫn tôn trọng đúng limit", len(e10) == 10, len(e10))
check("mới nhất đứng trước", e10 and "2026-07-30" in e10[0], e10[0][:30] if e10 else "")

ma, e200 = lay(200)
# Đây là điểm chính: bản cũ cắt ở 3 file nên tối đa 6 mục, phân trang thành vô nghĩa.
check("CANARY: limit lớn đọc quá 3 file cũ (nếu không thì không có gì để lật trang)",
      len(e200) > 6, len(e200))
check("đọc được tới hết 30 ngày đã ghi", len(e200) == 60, len(e200))

ma, e_khung = lay(5000)
check("có TRẦN, không đọc vô hạn theo limit người gọi", len(e_khung) <= 500, len(e_khung))

ma, e0 = lay(0)
check("limit 0 hay âm thì kẹp về mức tối thiểu, không trả rỗng khó hiểu", len(e0) >= 1, len(e0))

# Brain chưa từng học thì không được nổ.
trong = Path(tempfile.mkdtemp(prefix="javis-hocrong-"))
main.learn_feature.deps.brain_root = lambda brain="brain": str(trong)
ma, e = lay(50)
check("brain chưa có nhật ký thì trả rỗng êm", ma == 200 and e == [], (ma, e))

if fails:
    print("\nFAIL - test_nhat_ky_hoc_sau: " + str(len(fails)) + " lỗi: " + ", ".join(fails))
    sys.exit(1)
print("\nOK - test_nhat_ky_hoc_sau: tất cả pass")
