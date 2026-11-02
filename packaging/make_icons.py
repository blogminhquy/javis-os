#!/usr/bin/env python3
"""Build the desktop app icons from dashboard/icon-512.png.

    python packaging/make_icons.py

Writes packaging/assets/javis.ico (Windows installer and shortcuts) and
packaging/assets/javis.icns (macOS app bundle), plus a copy of the .icns inside the
in-repo "JAVIS OS.app". The outputs are committed, so CI and users never need Pillow
for this; rerun it only when the logo changes.
"""
from pathlib import Path
import shutil

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "dashboard" / "icon-512.png"
OUT = ROOT / "packaging" / "assets"


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    img = Image.open(SRC).convert("RGBA")
    img.save(OUT / "javis.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    img.save(OUT / "javis.icns")
    res = ROOT / "JAVIS OS.app" / "Contents" / "Resources"
    res.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(OUT / "javis.icns", res / "javis.icns")
    print("wrote", OUT / "javis.ico", OUT / "javis.icns")


if __name__ == "__main__":
    main()
