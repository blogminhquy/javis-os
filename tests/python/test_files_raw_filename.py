"""/files/raw keeps the file name, also for accented names, and knows Office types (#898, items 4 and 5).

    python tests/run.py files_raw_filename

Reported from a Windows Server install: /files/raw answered a bare `Content-Disposition: inline`, so a browser that
cannot show an .xlsx saved it as "raw" with no extension; and .xlsx/.docx/.pptx went out as application/octet-stream
where the system has no mime.types file. A name like "Báo cáo.xlsx" must still give a valid ASCII header.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-files-raw-")
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import main  # noqa: E402

_fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(extra) + "]") if extra and not cond else ""))
    if not cond:
        _fails.append(name)


tmp = Path(tempfile.mkdtemp(prefix="javis-files-raw-brain-"))


def serve(name, dl=False):
    f = tmp / name
    f.write_bytes(b"PK\x03\x04 test")
    with patch.object(main, "_safe_serve_path", lambda brain, path: f):
        return main.raw_file_response("brain", name, dl=dl)


r = serve("bang-tinh.xlsx")
cd = r.headers.get("content-disposition", "")
check("inline keeps the file name", cd.startswith("inline") and 'filename="bang-tinh.xlsx"' in cd, cd)
check(".xlsx has its Office type",
      r.headers.get("content-type") == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
      r.headers.get("content-type"))
check("nosniff stays", r.headers.get("x-content-type-options") == "nosniff")
for ext, mt in ((".docx", "wordprocessingml.document"), (".pptx", "presentationml.presentation")):
    check(ext + " has its Office type", mt in serve("tep" + ext).headers.get("content-type", ""))

for name in ("Báo cáo.xlsx", "á.pdf"):
    cd = serve(name).headers.get("content-disposition", "")
    check("accented name gives an ASCII header: " + name, cd.isascii(), cd)
    check("... with the UTF-8 name (RFC 5987): " + name, cd.startswith("inline") and "filename*=utf-8''" in cd, cd)

cd = serve("bang-tinh.xlsx", dl=True).headers.get("content-disposition", "")
check("CANARY: dl=1 still forces a download", cd.startswith("attachment"), cd)

if _fails:
    print(f"\n{len(_fails)} FAIL")
    sys.exit(1)
print("\nOK - test_files_raw_filename: all passed")
