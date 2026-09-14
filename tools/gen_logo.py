#!/usr/bin/env python3
"""Sinh logo + favicon + icon PWA của Javis từ hình linh vật.

    python tools/gen_logo.py

Linh vật: một khối tròn CAM ĐẶC viền hổ phách nhạt rất mảnh, và hai mắt đen hình bầu dục
dọc LIẾC LÊN PHÍA TRÊN BÊN PHẢI. Mắt lệch là cố ý, không phải vẽ ẩu: đặt giữa mặt thì ra
một cái mặt cười vô hồn, liếc đi thì nó thành một thực thể đang để ý tới cái gì đó.

Đây là dáng CHÂN DUNG, chỉ dùng cho logo/favicon. Con pet ở mép màn hình (dashboard/pet.js)
có mắt nhìn theo con trỏ thật, nên lúc nghỉ nó nhìn thẳng chứ không đóng băng ở dáng này.

Vẽ BẰNG HÌNH HỌC chứ không nhúng file ảnh: mọi cỡ đều sắc nét, và đổi màu hay tỉ lệ chỉ
là sửa vài hằng số ở đây rồi chạy lại. Vẽ ở cỡ gấp 8 lần rồi thu nhỏ (khử răng cưa bằng
tay) vì Pillow không có antialias cho hình vẽ. Cung tròn được rải bằng nhiều chấm tròn
nhỏ chồng nhau thay vì dùng ImageDraw.arc, chỉ để hai đầu cung được BO TRÒN.

Ghi ra:
  dashboard/logo.png      - logo chính, cũng là nguồn của /brand-logo và /favicon.ico
  dashboard/favicon.png
  dashboard/icon-192.png  - icon PWA (manifest.json)
  dashboard/icon-512.png

Cùng hình học này được vẽ lại bằng SVG trong dashboard/pet.js (con pet góc màn hình),
nên sửa tỉ lệ ở đây thì ngó sang bên đó cho khớp.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "dashboard"

# Bảng màu "Hổ phách" - tông mặc định của linh vật (khớp PALETTES.amber.sun trong pet.js).
CAM = (242, 140, 40, 255)        # #F28C28 thân
VANH = (247, 201, 143, 255)      # #F7C98F viền ngoài
MAT = (30, 30, 30, 255)          # #1E1E1E mắt

SS = 8                           # hệ số vẽ phóng đại để khử răng cưa

# Tỉ lệ theo CẠNH ảnh (ảnh vuông). Giữ khớp với pet.js.
THAN_R = 0.425                   # bán kính thân
VANH_R = 0.433                   # bán kính viền (nằm sát ngoài thân)
VANH_DAY = 0.013                 # bề dày viền

MAT_X = 0.078                    # nửa khoảng cách giữa hai mắt
MAT_LECH_X = 0.150               # cả cặp mắt liếc sang phải bao nhiêu
MAT_LECH_Y = -0.125              # ... và liếc lên trên bao nhiêu
MAT_RX = 0.037                   # bán trục ngang của mắt
MAT_RY = 0.092                   # bán trục dọc của mắt


def ve(canh: int) -> Image.Image:
    """Vẽ linh vật trên nền trong suốt, cạnh `canh` pixel."""
    n = canh * SS
    img = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    cx = cy = n / 2

    def hop(r):
        return [cx - r, cy - r, cx + r, cy + r]

    # Viền vẽ bằng hai hình tròn lồng nhau chứ không dùng ImageDraw.ellipse(outline=...):
    # nét outline của Pillow dày theo pixel nguyên nên ở cỡ nhỏ nó dày mỏng không đều.
    d.ellipse(hop((VANH_R + VANH_DAY / 2) * n), fill=VANH)
    d.ellipse(hop((VANH_R - VANH_DAY / 2) * n), fill=(0, 0, 0, 0))
    d.ellipse(hop(THAN_R * n), fill=CAM)

    for dau in (-1, 1):
        mx = cx + (MAT_LECH_X + dau * MAT_X) * n
        my = cy + MAT_LECH_Y * n
        d.ellipse([mx - MAT_RX * n, my - MAT_RY * n, mx + MAT_RX * n, my + MAT_RY * n], fill=MAT)

    return img.resize((canh, canh), Image.LANCZOS)


def main() -> int:
    for ten, canh in [("logo.png", 512), ("favicon.png", 64),
                      ("icon-192.png", 192), ("icon-512.png", 512)]:
        p = OUT_DIR / ten
        ve(canh).save(p)
        print(f"  {p.relative_to(ROOT)}  {canh}x{canh}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
