"""Excel and scanned PDF reading for Team attachments and `javis_read_file` (0.271.0).

    python tests/python/test_doc_text_xlsx_0271.py      (no network, no model)

Customer report, codes 5 and 22: a Team "Giao việc" job with a 3-sheet Excel and a 3-page scanned PDF. Excel had no
reader, so members wrote shell commands to unzip workbook.xml (each stopped for an approval, the output cut at 1,500
characters or crashed with UnicodeEncodeError on a Windows console). A partner chatting through the CLI read the same
files correctly. The server now extracts .xlsx with the standard library: every sheet, formulas with their cached
values, error cells listed; a PDF page with no text layer is named as image-only.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import io
import os
import sys
import tempfile
import zipfile
from pathlib import Path

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-doc-xlsx-"))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import doc_text  # noqa: E402
import team_docs  # noqa: E402

fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(extra)[:400] + "]") if extra and not cond else ""))
    if not cond:
        fails.append(name)


TMP = Path(tempfile.mkdtemp(prefix="javis-doc-xlsx-files-"))
NS = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" ' \
     'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"'


def write_xlsx(path: Path, *, absolute_targets: bool = False, extra: dict = None) -> None:
    """A workbook laid out the way Excel saves one: shared strings, styles, three sheets (one hidden)."""
    t = (lambda n: f"/xl/worksheets/sheet{n}.xml") if absolute_targets else (lambda n: f"worksheets/sheet{n}.xml")
    parts = {
        "[Content_Types].xml": '<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/'
                               'package/2006/content-types"/>',
        "xl/workbook.xml": f'<?xml version="1.0" encoding="UTF-8"?><workbook {NS}><workbookPr/><sheets>'
                           '<sheet name="Tổng hợp" sheetId="1" r:id="rId1"/>'
                           '<sheet name="Chi tiết" sheetId="2" r:id="rId2"/>'
                           '<sheet name="Ẩn" sheetId="3" state="hidden" r:id="rId3"/></sheets></workbook>',
        "xl/_rels/workbook.xml.rels": '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.'
                                      'openxmlformats.org/package/2006/relationships">'
                                      f'<Relationship Id="rId1" Type="ws" Target="{t(1)}"/>'
                                      f'<Relationship Id="rId2" Type="ws" Target="{t(2)}"/>'
                                      f'<Relationship Id="rId3" Type="ws" Target="{t(3)}"/></Relationships>',
        "xl/sharedStrings.xml": f'<sst {NS}><si><t>Khoản mục</t></si><si><t>Giá trị</t></si>'
                                '<si><r><t>Doanh </t></r><r><rPr><b/></rPr><t>thu</t></r>'
                                '<rPh sb="0" eb="1"><t>XX</t></rPh></si><si><t>Tỷ lệ</t></si></sst>',
        "xl/styles.xml": f'<styleSheet {NS}><numFmts count="1"><numFmt numFmtId="164" formatCode="dd/mm/yyyy"/>'
                         '</numFmts><cellXfs count="3"><xf numFmtId="0"/><xf numFmtId="164"/><xf numFmtId="4"/></cellXfs>'
                         '</styleSheet>',
        "xl/worksheets/sheet1.xml": f'<worksheet {NS}><sheetData>'
                                    '<row r="1"><c r="A1" t="s"><v>0</v></c><c r="B1" t="s"><v>1</v></c></row>'
                                    '<row r="2"><c r="A2" t="s"><v>2</v></c><c r="B2" s="2"><v>1250000</v></c></row>'
                                    '<row r="3"><c r="A3" t="s"><v>3</v></c><c r="B3" t="e"><f>B2/0</f><v>#DIV/0!</v>'
                                    '</c></row>'
                                    '<row r="4"><c r="A4" t="inlineStr"><is><t>Tổng</t></is></c><c r="B4"><f>B2*2</f>'
                                    '<v>2500000</v></c></row></sheetData></worksheet>',
        "xl/worksheets/sheet2.xml": f'<worksheet {NS}><sheetData>'
                                    '<row r="1"><c r="A1" s="1"><v>45580</v></c><c r="B1" t="b"><v>1</v></c>'
                                    '<c r="C1" t="str"><f>"x"&amp;"y"</f><v>xy</v></c>'
                                    '<c r="D1" t="e"><v>#REF!</v></c><c r="E1"><f>A1+1</f></c></row>'
                                    '</sheetData></worksheet>',
        "xl/worksheets/sheet3.xml": f'<worksheet {NS}><sheetData><row r="1"><c r="A1"><v>7</v></c></row></sheetData>'
                                    '</worksheet>',
    }
    parts.update(extra or {})
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        for name, body in parts.items():
            z.writestr(name, body)


# ---- 1. Excel ----
write_xlsx(TMP / "tham-dinh.xlsx")
t = doc_text.extract(TMP / "tham-dinh.xlsx")
check("xlsx: every sheet is read, hidden one marked",
      "--- Sheet: Tổng hợp ---" in t and "--- Sheet: Chi tiết ---" in t and "--- Sheet: Ẩn (ẩn) ---" in t, t)
check("xlsx: shared strings, rich text joined, phonetic run skipped", "A2=Doanh thu" in t and "XX" not in t, t)
check("xlsx: plain number kept", "B2=1250000" in t, t)
check("xlsx: formula shows Excel's cached value and the formula", "B4=2500000 [=B2*2]" in t, t)
check("xlsx: error cell shown with its formula", "B3=#DIV/0! [=B2/0]" in t, t)
check("xlsx: error cells listed per sheet", "Ô lỗi (1): B3 #DIV/0!" in t and "Ô lỗi (1): D1 #REF!" in t, t)
check("xlsx: date style turns the serial into a date", "A1=2024-10-15" in t, t)
check("xlsx: boolean and string formula", "B1=TRUE" in t and 'C1=xy [="x"&"y"]' in t, t)
check("xlsx: formula without a cached value says so", "E1=(chưa có giá trị tính sẵn) [=A1+1]" in t, t)
check("xlsx: inline string", "A4=Tổng" in t, t)
check("xlsx: suffix is routed through doc_text (hub read and team attach use SUFFIXES)",
      ".xlsx" in doc_text.SUFFIXES and ".xlsm" in doc_text.SUFFIXES)

write_xlsx(TMP / "abs.xlsx", absolute_targets=True)
check("xlsx: absolute relationship targets resolve", "B4=2500000" in doc_text.extract(TMP / "abs.xlsx"))

write_xlsx(TMP / "bomb.xlsx", extra={"xl/sharedStrings.xml": '<!DOCTYPE x [<!ENTITY a "aaaa">]><sst><si><t>&a;</t></si>'
                                                             '</sst>'})
check("xlsx: a part with a DTD is refused, never expanded", doc_text.extract(TMP / "bomb.xlsx").startswith("ERROR:"))

old = doc_text.MAX_XLSX_XML_BYTES
doc_text.MAX_XLSX_XML_BYTES = 50
try:
    check("xlsx: a part too large once uncompressed is refused", "quá lớn" in doc_text.extract(TMP / "tham-dinh.xlsx"))
finally:
    doc_text.MAX_XLSX_XML_BYTES = old

with zipfile.ZipFile(TMP / "not-excel.xlsx", "w") as z:
    z.writestr("hello.txt", "hi")
check("xlsx: a zip without a workbook is a clear error", doc_text.extract(TMP / "not-excel.xlsx").startswith("ERROR:"))
(TMP / "old.xls").write_bytes(b"\xd0\xcf\x11\xe0" + b"\x00" * 100)
t = doc_text.extract(TMP / "old.xls")
check("xls (old binary format): says to save as .xlsx instead of returning binary noise",
      t.startswith("ERROR:") and ".xlsx" in t, t)

# ---- 2. PDF with a scanned page ----
try:
    import pypdf
    from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

    def text_page(writer, text):
        page = writer.add_blank_page(612, 792)
        font = DictionaryObject({NameObject("/Type"): NameObject("/Font"), NameObject("/Subtype"): NameObject("/Type1"),
                                 NameObject("/BaseFont"): NameObject("/Helvetica")})
        page[NameObject("/Resources")] = DictionaryObject({NameObject("/Font"): DictionaryObject(
            {NameObject("/F1"): writer._add_object(font)})})
        s = DecodedStreamObject()
        s.set_data(f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode())
        page[NameObject("/Contents")] = writer._add_object(s)

    w = pypdf.PdfWriter()
    text_page(w, "Bien ban tham dinh tai san so 12 ngay 15 thang 10 nam 2026 tai Ha Noi")
    w.add_blank_page(612, 792)
    text_page(w, "Ket luan: gia tri tai san uoc tinh mot ty hai tram trieu dong chan")
    buf = io.BytesIO()
    w.write(buf)
    (TMP / "mixed.pdf").write_bytes(buf.getvalue())
    t = doc_text.extract(TMP / "mixed.pdf")
    check("pdf: text pages are read", "Bien ban tham dinh" in t and "Ket luan" in t, t[:300])
    check("pdf: the page with no text layer is named as image-only",
          "[1/3 trang không có lớp chữ (ảnh scan), chưa đọc được: trang 2]" in t
          and "--- Trang 2 ---\n[Trang này không có lớp chữ" in t, t[:400])
    w = pypdf.PdfWriter()
    for _ in range(3):
        w.add_blank_page(612, 792)
    buf = io.BytesIO()
    w.write(buf)
    (TMP / "scan.pdf").write_bytes(buf.getvalue())
    check("pdf: a fully scanned file still says so plainly", "gần như không có chữ" in doc_text.extract(TMP / "scan.pdf"))
except ImportError:
    print("skip pdf checks: pypdf missing")

# ---- 3. Team attachments get a pinned text copy of the Excel ----
staging, brain = Path(tempfile.mkdtemp(prefix="javis-stg-")), Path(tempfile.mkdtemp(prefix="javis-br-"))
write_xlsx(staging / "bang-tinh.xlsx")
docs, pinned = {}, []


def add(rel, name):
    fid = f"f{len(docs) + 1}"
    docs[fid] = (rel, name)
    return fid


kept = team_docs.save([{"path": str(staging / "bang-tinh.xlsx"), "name": "bang-tinh.xlsx"}], staging=staging,
                      brain_root=brain, dest_dir=brain / "attachments" / "teams" / "t1",
                      to_rel=lambda p: str(Path(p).relative_to(brain)), add=add, pin=pinned.append,
                      readable={".md", ".txt"}, extract=doc_text.extract, extract_suffixes=doc_text.SUFFIXES)
txt = [rel for fid, (rel, name) in docs.items() if fid in pinned and rel.endswith(".txt")]
check("team attach: the Excel gets a pinned text copy members read", len(kept) == 1 and len(txt) == 1, docs)
if txt:
    body = (brain / txt[0]).read_text(encoding="utf-8")
    check("team attach: the copy holds every sheet and the error cell", "Sheet: Ẩn" in body and "#DIV/0!" in body)
blk = team_docs.block(["- [file] bang-tinh.xlsx - x"], [], "", tools=True)
check("tool turn: members are told to read PDF/Word/Excel with javis_read_file, not shell commands",
      "javis_read_file" in blk and "Excel" in blk, blk)

print()
if fails:
    print(f"FAIL - {len(fails)} check(s)")
    raise SystemExit(1)
print("OK - test_doc_text_xlsx_0271: all pass")
