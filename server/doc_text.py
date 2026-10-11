"""Bóc CHỮ từ file PDF và Word (.docx) cho tool `javis_read_file` của hub (0.92.2).

Vì sao có. Engine CLI (Claude Code, Codex) tự mở được PDF, còn sáu engine API và Ollama máy nhà chỉ có `javis_read_file`, mà tool
đó đọc mọi file bằng `read_text`: PDF/Word ra toàn mã nhị phân, model đọc xong báo "không đọc được" (người dùng Ollama local trên
Mac báo 11/10, kèm bản thử bằng pypdf tóm tắt đúng một PDF 17 trang).

Hai rào cho file người lạ có thể gửi tới: trần số trang PDF và trần kích thước XML của .docx (một file zip vài KB có thể giãn ra
hàng GB). Lỗi luôn trả CÂU người đọc hiểu, không ném ra ngoài: tool đọc file không được làm hỏng cả lượt chat.
"""
from __future__ import annotations

import re
import zipfile
from html import unescape
from pathlib import Path

SUFFIXES = (".pdf", ".docx")
MAX_PDF_PAGES = 300
MAX_DOCX_XML_BYTES = 20 * 1024 * 1024


def extract(path) -> str:
    """Chữ trong file, hoặc câu bắt đầu bằng "ERROR:" nói vì sao không bóc được."""
    p = Path(path)
    try:
        if p.suffix.lower() == ".pdf":
            return _pdf(p)
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
    parts = []
    for i, pg in enumerate(r.pages[:MAX_PDF_PAGES], 1):
        parts.append(f"--- Trang {i} ---\n{(pg.extract_text() or '').strip()}")
    text = "\n\n".join(parts)
    if len(re.sub(r"--- Trang \d+ ---|\s", "", text)) < 50:
        return (f"'{p.name}' có {tong} trang nhưng gần như không có chữ (có thể là PDF scan hoặc ảnh). Tool này không đọc được "
                f"chữ nằm trong ảnh.")
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
