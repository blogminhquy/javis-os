"""Bóc CHỮ từ file PDF và Word (.docx) cho tool `javis_read_file` của hub (0.92.2).

Vì sao có. Engine CLI (Claude Code, Codex) tự mở được PDF, còn sáu engine API và Ollama máy nhà chỉ có `javis_read_file`, mà tool
đó đọc mọi file bằng `read_text`: PDF/Word ra toàn mã nhị phân, model đọc xong báo "không đọc được" (người dùng Ollama local trên
Mac báo 11/10, kèm bản thử bằng pypdf tóm tắt đúng một PDF 17 trang).

Hai rào cho file người lạ có thể gửi tới: trần số trang PDF và trần kích thước XML của .docx (một file zip vài KB có thể giãn ra
hàng GB). Lỗi luôn trả CÂU người đọc hiểu, không ném ra ngoài: tool đọc file không được làm hỏng cả lượt chat.

0.271.0 (customer report, Team "Giao việc" with a 3-sheet Excel and a scanned PDF): Excel had no reader, so Team members
wrote shell commands to unzip workbook.xml, each one stopped for an owner approval, and the output was cut or crashed on a
Windows console code page. `.xlsx`/`.xlsm` are now read here with the standard library only (no openpyxl dependency):
every sheet, the cached value of each formula next to the formula, error cells such as #DIV/0! listed per sheet. A PDF
page without a text layer is marked as an image-only page, so a member knows which pages it could not read instead of
getting silence for them.
"""
from __future__ import annotations

import datetime as _dt
import re
import zipfile
import xml.etree.ElementTree as ET
from html import unescape
from pathlib import Path

SUFFIXES = (".pdf", ".docx", ".xlsx", ".xlsm", ".xls")
XLSX_SUFFIXES = (".xlsx", ".xlsm")
MAX_PDF_PAGES = 300
MAX_DOCX_XML_BYTES = 20 * 1024 * 1024
# Excel caps: one sheet part (uncompressed), rows per sheet, and the whole text handed back.
MAX_XLSX_XML_BYTES = 40 * 1024 * 1024
MAX_XLSX_ROWS = 5000
MAX_XLSX_CHARS = 400_000
# A PDF page with fewer visible characters than this is treated as having no text layer (a scanned image).
PDF_PAGE_MIN_CHARS = 15


def extract(path) -> str:
    """Chữ trong file, hoặc câu bắt đầu bằng "ERROR:" nói vì sao không bóc được."""
    p = Path(path)
    try:
        suf = p.suffix.lower()
        if suf == ".pdf":
            return _pdf(p)
        if suf in XLSX_SUFFIXES:
            return _xlsx(p)
        if suf == ".xls":
            return (f"ERROR: '{p.name}' là file Excel đời cũ (.xls), Javis chỉ đọc được .xlsx. Mở file bằng Excel hoặc "
                    f"Google Sheets rồi lưu lại thành .xlsx.")
        return _docx(p)
    except Exception as e:      # noqa: BLE001 - file hỏng hay lạ: nói thẳng, đừng làm sập lượt chat
        return f"ERROR: không bóc được chữ từ '{p.name}': {type(e).__name__}: {e}"


def _pdf(p: Path) -> str:
    try:
        import pypdf
    except ImportError:
        return ("ERROR: máy chủ Javis thiếu thư viện pypdf nên chưa đọc được PDF. Cập nhật Javis (bản mới cài sẵn), hoặc chạy "
                "`pip install pypdf` trong môi trường của Javis.")
    r = pypdf.PdfReader(str(p))
    tong = len(r.pages)
    parts, image_only = [], []
    for i, pg in enumerate(r.pages[:MAX_PDF_PAGES], 1):
        body = (pg.extract_text() or "").strip()
        if len(re.sub(r"\s", "", body)) < PDF_PAGE_MIN_CHARS:
            image_only.append(i)
            body = (body + "\n" if body else "") + ("[Trang này không có lớp chữ, có thể là ảnh scan: tool này không đọc "
                                                    "được chữ trong ảnh]")
        parts.append(f"--- Trang {i} ---\n{body}")
    text = "\n\n".join(parts)
    if len(re.sub(r"--- Trang \d+ ---|\[Trang này không có lớp chữ[^\]]*\]|\s", "", text)) < 50:
        return (f"'{p.name}' có {tong} trang nhưng gần như không có chữ (có thể là PDF scan hoặc ảnh). Tool này không đọc được "
                f"chữ nằm trong ảnh.")
    if image_only:
        text = (f"[{len(image_only)}/{min(tong, MAX_PDF_PAGES)} trang không có lớp chữ (ảnh scan), chưa đọc được: trang "
                f"{', '.join(str(n) for n in image_only[:50])}{' ...' if len(image_only) > 50 else ''}]\n\n" + text)
    if tong > MAX_PDF_PAGES:
        text += f"\n\n… [chỉ đọc {MAX_PDF_PAGES} trang đầu, file có {tong} trang]"
    return text


def _docx(p: Path) -> str:
    with zipfile.ZipFile(p) as z:
        try:
            info = z.getinfo("word/document.xml")
        except KeyError:
            return f"ERROR: '{p.name}' không phải file Word .docx hợp lệ (thiếu word/document.xml)."
        if info.file_size > MAX_DOCX_XML_BYTES:
            return f"ERROR: nội dung '{p.name}' quá lớn để đọc ({info.file_size // (1024 * 1024)} MB khi giải nén)."
        xml = z.read(info).decode("utf-8", errors="replace")
    xml = re.sub(r"</w:p>", "\n", xml)
    xml = re.sub(r"<w:(tab|br)\b[^>]*/>", lambda m: "\t" if m.group(1) == "tab" else "\n", xml)
    text = unescape(re.sub(r"<[^>]+>", "", xml))
    return "\n".join(ln.rstrip() for ln in text.splitlines()).strip()


# ---- Excel (.xlsx / .xlsm), standard library only ----

_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
# Built-in number formats that show a date or a time (ECMA-376 18.8.30).
_BUILTIN_DATE_FMTS = frozenset(range(14, 23)) | frozenset(range(45, 48)) | frozenset({27, 30, 36, 50, 57})


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _xml_part(z: zipfile.ZipFile, name: str):
    """Parse one part of the package, or None when it is missing. Refuses a part that is too large once uncompressed and
    any DTD (entity expansion has no place in an Office file)."""
    try:
        info = z.getinfo(name)
    except KeyError:
        return None
    if info.file_size > MAX_XLSX_XML_BYTES:
        raise ValueError(f"phần '{name}' quá lớn ({info.file_size // (1024 * 1024)} MB khi giải nén)")
    data = z.read(info)
    if b"<!DOCTYPE" in data[:4096].upper() or b"<!ENTITY" in data.upper():
        raise ValueError(f"phần '{name}' có khai báo DTD, không đọc")
    return ET.fromstring(data)


def _text_of(el) -> str:
    """Visible text of a shared string or inline string: every <t>, skipping phonetic runs (<rPh>)."""
    out = []

    def walk(node):
        for ch in node:
            tag = _local(ch.tag)
            if tag == "rPh":
                continue
            if tag == "t":
                out.append(ch.text or "")
            else:
                walk(ch)
    walk(el)
    return "".join(out)


def _date_styles(z: zipfile.ZipFile) -> set:
    """Indexes of cell styles (`s` attribute) whose number format is a date or a time."""
    root = _xml_part(z, "xl/styles.xml")
    if root is None:
        return set()
    custom = {}
    for el in root.iter():
        if _local(el.tag) == "numFmt":
            try:
                custom[int(el.get("numFmtId"))] = el.get("formatCode") or ""
            except (TypeError, ValueError):
                continue
    out = set()
    for el in root:
        if _local(el.tag) != "cellXfs":
            continue
        for i, xf in enumerate(x for x in el if _local(x.tag) == "xf"):
            try:
                fid = int(xf.get("numFmtId") or 0)
            except ValueError:
                continue
            code = custom.get(fid)
            if code is None:
                if fid in _BUILTIN_DATE_FMTS:
                    out.add(i)
            else:
                bare = re.sub(r'"[^"]*"|\[[^\]]*\]|\\.', "", code).lower()
                if re.search(r"[dmyhs]", bare) and not re.fullmatch(r"[#0.,%\s;e+\-]*", bare):
                    out.add(i)
    return out


def _serial_to_date(v: str, date1904: bool) -> str:
    try:
        f = float(v)
    except ValueError:
        return v
    base = _dt.datetime(1904, 1, 1) if date1904 else _dt.datetime(1899, 12, 30)
    try:
        d = base + _dt.timedelta(days=f)
    except OverflowError:
        return v
    if f == int(f):
        return d.strftime("%Y-%m-%d")
    if f < 1:
        return d.strftime("%H:%M:%S")
    return d.strftime("%Y-%m-%d %H:%M:%S")


def _sheet_targets(z: zipfile.ZipFile) -> list:
    """[(name, part path, hidden)] in workbook order."""
    wb = _xml_part(z, "xl/workbook.xml")
    if wb is None:
        raise ValueError("thiếu xl/workbook.xml")
    rels = {}
    rr = _xml_part(z, "xl/_rels/workbook.xml.rels")
    if rr is not None:
        for el in rr:
            target = el.get("Target") or ""
            target = target.lstrip("/") if target.startswith("/") else "xl/" + target
            rels[el.get("Id")] = re.sub(r"[^/]+/\.\./", "", target)
    out = []
    for el in wb.iter():
        if _local(el.tag) != "sheet":
            continue
        rid = el.get(f"{{{_REL_NS}}}id") or next((v for k, v in el.attrib.items() if _local(k) == "id"), None)
        part = rels.get(rid) or f"xl/worksheets/sheet{el.get('sheetId')}.xml"
        out.append((el.get("name") or part, part, (el.get("state") or "visible") != "visible"))
    return out


def _cell_value(c, shared: list, date_styles: set, date1904: bool) -> tuple:
    """(shown value, formula or "") of one <c> element."""
    t = c.get("t") or "n"
    v_el = f_el = is_el = None
    for ch in c:
        tag = _local(ch.tag)
        if tag == "v":
            v_el = ch
        elif tag == "f":
            f_el = ch
        elif tag == "is":
            is_el = ch
    raw = (v_el.text or "") if v_el is not None else ""
    formula = ""
    if f_el is not None:
        formula = "=" + f_el.text if f_el.text else ("(công thức dùng chung)" if f_el.get("t") == "shared" else "")
    if t == "s":
        try:
            val = shared[int(raw)]
        except (ValueError, IndexError):
            val = raw
    elif t == "inlineStr":
        val = _text_of(is_el) if is_el is not None else ""
    elif t == "b":
        val = "TRUE" if raw == "1" else "FALSE" if raw == "0" else raw
    elif t in ("e", "str"):
        val = raw
    else:
        val = raw
        try:
            if raw and int(c.get("s") or 0) in date_styles:
                val = _serial_to_date(raw, date1904)
        except ValueError:
            pass
    if formula and (v_el is None or (not raw and t != "str")):
        # No cached value: the file was written by a tool that does not calculate (openpyxl, a script), or never opened.
        val = "(chưa có giá trị tính sẵn)"
    return val, formula


def _xlsx(p: Path) -> str:
    with zipfile.ZipFile(p) as z:
        try:
            sheets = _sheet_targets(z)
        except ValueError as e:
            return f"ERROR: '{p.name}' không phải file Excel .xlsx hợp lệ ({e})."
        shared = []
        ss = _xml_part(z, "xl/sharedStrings.xml")
        if ss is not None:
            shared = [_text_of(si) for si in ss if _local(si.tag) == "si"]
        date_styles = _date_styles(z)
        wb = _xml_part(z, "xl/workbook.xml")
        date1904 = any(_local(el.tag) == "workbookPr" and (el.get("date1904") or "").lower() in ("1", "true")
                       for el in wb.iter())
        blocks, total, cut = [], 0, False
        for name, part, hidden in sheets:
            root = _xml_part(z, part)
            head = f"--- Sheet: {name}{' (ẩn)' if hidden else ''} ---"
            if root is None:
                blocks.append(f"{head}\n(không tìm thấy dữ liệu của sheet này)")
                continue
            lines, errors, rows, more = [], [], 0, False
            for row in root.iter():
                if _local(row.tag) != "row":
                    continue
                cells = []
                for c in row:
                    if _local(c.tag) != "c":
                        continue
                    val, formula = _cell_value(c, shared, date_styles, date1904)
                    ref = c.get("r") or "?"
                    if c.get("t") == "e":
                        errors.append(f"{ref} {val}")
                    if val == "" and not formula:
                        continue
                    cells.append(f"{ref}={val}" + (f" [{formula}]" if formula else ""))
                if not cells:
                    continue
                rows += 1
                if rows > MAX_XLSX_ROWS:
                    more = True
                    break
                lines.append("\t".join(cells))
            summary = [head, f"{rows if not more else MAX_XLSX_ROWS} hàng có dữ liệu"
                       + (f", chỉ đọc {MAX_XLSX_ROWS} hàng đầu" if more else "")]
            if errors:
                summary.append(f"Ô lỗi ({len(errors)}): " + "; ".join(errors[:100]) + (" ..." if len(errors) > 100 else ""))
            block = "\n".join(summary + (lines or ["(sheet trống)"]))
            if total + len(block) > MAX_XLSX_CHARS:
                block = block[:max(0, MAX_XLSX_CHARS - total)]
                cut = True
            blocks.append(block)
            total += len(block)
            if cut:
                break
    if not sheets:
        return f"ERROR: '{p.name}' không có sheet nào."
    intro = (f"File Excel '{p.name}': {len(sheets)} sheet ({', '.join(n for n, _, _ in sheets)}). Mỗi dòng là một hàng, "
             f"ô ghi dạng THAM CHIẾU=giá trị; ô có công thức ghi giá trị Excel đã tính sẵn rồi tới [=công thức].")
    text = intro + "\n\n" + "\n\n".join(blocks)
    if cut:
        text += f"\n\n… [đã cắt ở {MAX_XLSX_CHARS:,} ký tự, file còn dữ liệu]"
    return text
