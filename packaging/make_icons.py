#!/usr/bin/env python3
"""Build the desktop app icons from dashboard/icon-512.png.

    python packaging/make_icons.py

Writes packaging/assets/javis.ico (Windows installer and shortcuts) and
packaging/assets/javis.icns (macOS app bundle and the .dmg volume icon), plus a copy of
the .icns inside the in-repo "JAVIS OS.app", and the Windows setup wizard pictures:
wizard-<pct>.bmp (the tall panel on the first and last page) and wizard-small-<pct>.bmp
(the corner logo on the pages between), one per display scale Inno Setup picks from.
The outputs are committed, so CI and users never need Pillow for this; rerun it only when
the logo changes.
"""
from pathlib import Path
import shutil

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "dashboard" / "icon-512.png"
OUT = ROOT / "packaging" / "assets"


# Inno Setup 6 wizard picture sizes at 100%; it chooses the closest of the listed scales.
WIZ_BIG = (164, 314)
WIZ_SMALL = (55, 55)
SCALES = (100, 125, 150, 175, 200, 225, 250)
BG_DARK = (31, 31, 31)        # #1F1F1F, the logo's eye colour, as in logo.svg
ACCENT = (253, 97, 0)         # #FD6100, the logo's body colour
FONT_CANDIDATES = ("/usr/share/fonts/opentype/inter/Inter-Bold.otf",
                   "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")


def _font(size: int):
    for f in FONT_CANDIDATES:
        if Path(f).exists():
            return ImageFont.truetype(f, size)
    return ImageFont.load_default()


def _wizard_big(logo: Image.Image, pct: int) -> Image.Image:
    w, h = (round(v * pct / 100) for v in WIZ_BIG)
    img = Image.new("RGB", (w, h), BG_DARK)
    d = ImageDraw.Draw(img)
    d.rectangle([0, h - max(3, h // 80), w, h], fill=ACCENT)       # thin brand line at the foot
    side = round(w * 0.70)
    mark = logo.resize((side, side), Image.LANCZOS)
    top = round(h * 0.22)
    img.paste(mark, ((w - side) // 2, top), mark)
    font = _font(round(w * 0.15))
    text = "JAVIS OS"
    tw = d.textlength(text, font=font)
    d.text(((w - tw) / 2, top + side + round(h * 0.05)), text, font=font, fill=(255, 255, 255))
    return img


def _wizard_small(logo: Image.Image, pct: int) -> Image.Image:
    w, h = (round(v * pct / 100) for v in WIZ_SMALL)
    img = Image.new("RGB", (w, h), (255, 255, 255))     # the modern wizard header is white
    side = round(w * 0.88)
    mark = logo.resize((side, side), Image.LANCZOS)
    img.paste(mark, ((w - side) // 2, (h - side) // 2), mark)
    return img


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    img = Image.open(SRC).convert("RGBA")
    img.save(OUT / "javis.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    img.save(OUT / "javis.icns")
    res = ROOT / "JAVIS OS.app" / "Contents" / "Resources"
    res.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(OUT / "javis.icns", res / "javis.icns")
    for pct in SCALES:
        _wizard_big(img, pct).save(OUT / f"wizard-{pct}.bmp")
        _wizard_small(img, pct).save(OUT / f"wizard-small-{pct}.bmp")
    print("wrote", OUT / "javis.ico", OUT / "javis.icns", f"and {2 * len(SCALES)} wizard pictures")


if __name__ == "__main__":
    main()
