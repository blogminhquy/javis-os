"""Đóng một thư mục gói thành .zip và in dấu vân tay để dán vào danh mục kho.

    python examples/packs/dong-goi.py javis.tinh-gia

Có script này thay vì một dòng `zip -r` trong tài liệu vì ba lý do nhỏ mà mỗi cái đều đủ
làm hỏng một lần phát hành:

- `zip -r` gói cả `__pycache__` và `.DS_Store` vào. Chúng lọt vào chữ ký nội dung mã, nên
  gói đóng trên hai máy khác nhau ra hai `sha256` khác nhau.
- Đường dẫn trong zip phải dùng dấu `/`, kể cả khi đóng trên Windows.
- `sha256` phải lấy của ĐÚNG tệp vừa tạo. Tính rời ra bằng một lệnh khác là chỗ dễ dán nhầm
  của bản trước.

Mọi thứ script tự quyết đều được GHIM: tên và thứ tự mục, ngày tháng (mặc định `zipfile`
đóng dấu giờ hiện tại vào từng mục, nên đóng lại sau một phút là ra tệp khác), và quyền tệp.
Nhờ vậy đóng lại trên CÙNG MỘT MÁY luôn ra đúng một `sha256`, và `sha256` bạn dán vào danh mục
không tự nhiên lệch.

Cái KHÔNG ghim được là byte nén: DEFLATE cho ra chuỗi byte khác nhau giữa các bản zlib, nên tệp
đóng trên Windows và trên máy CI Linux có thể lệch `sha256` dù nội dung y hệt. Vì vậy phép đối
chiếu đúng là **so nội dung từng mục**, không so byte của tệp nén - `tests/python/test_goi_mau.py`
làm đúng thế. Chọn nén thay vì `ZIP_STORED` là có chủ ý: một gói mang theo ảnh mà không nén thì
đụng trần 25MB rất nhanh.
"""
import hashlib
import sys
import zipfile
from pathlib import Path

GOC = Path(__file__).resolve().parent
BO_QUA = ("__pycache__", ".git", ".DS_Store", ".pytest_cache")
# Mốc thời gian cổ nhất zip biểu diễn được. Giá trị cụ thể không quan trọng, việc nó là
# HẰNG SỐ mới quan trọng.
NGAY_GHIM = (1980, 1, 1, 0, 0, 0)


def dong(ten: str) -> Path:
    src = GOC / ten
    if not (src / "javis-pack.yaml").is_file():
        raise SystemExit(f"Không thấy {src / 'javis-pack.yaml'}")
    ra = GOC / "dist" / f"{ten.replace('.', '-')}.zip"
    ra.parent.mkdir(exist_ok=True)
    n = 0
    with zipfile.ZipFile(ra, "w", zipfile.ZIP_DEFLATED) as z:
        for p in sorted(src.rglob("*")):
            if not p.is_file() or any(x in p.parts for x in BO_QUA):
                continue
            it = zipfile.ZipInfo(str(p.relative_to(src)).replace("\\", "/"), NGAY_GHIM)
            it.compress_type = zipfile.ZIP_DEFLATED
            it.external_attr = 0o644 << 16      # tệp thường, không phải liên kết mềm
            z.writestr(it, p.read_bytes())
            n += 1
    print(f"{ra}  ({n} tệp, {ra.stat().st_size:,} byte)")
    print("sha256:", hashlib.sha256(ra.read_bytes()).hexdigest())
    return ra


if __name__ == "__main__":
    if len(sys.argv) < 2:
        co = sorted(d.name for d in GOC.iterdir()
                    if d.is_dir() and (d / "javis-pack.yaml").is_file())
        raise SystemExit("Cách dùng: python dong-goi.py <tên thư mục gói>\nCó sẵn: "
                         + (", ".join(co) or "chưa có gói nào"))
    dong(sys.argv[1])
