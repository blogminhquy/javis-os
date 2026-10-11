"""Ollama máy nhà nhận được công cụ, tool đọc file bóc được PDF/Word, chip Apple được tính là GPU (0.92.2).

    python tests/run.py ollama_local_tool_pdf      (KHÔNG mạng, KHÔNG cần Ollama)

Người dùng Mac mini báo 11/10/2026 (kèm bản vá đã chạy thử trên máy):
  1. Chọn Ollama (Local) thì model "không có quyền tool": `_api_stream_mcp` chỉ nạp tool cho một danh sách provider mà danh sách
     đó thiếu `ollama-local`, nên nhánh `ollama_local_chat_with_mcp` không bao giờ chạy.
  2. `javis_read_file` đọc PDF/DOCX bằng `read_text`, ra toàn mã nhị phân.
  4. Trang Local Model trên chip Apple ghi "Chạy bằng CPU và RAM" trong khi Ollama chạy 100% GPU: gợi ý model chỉ coi là GPU khi có
     VRAM rời, và nhận diện chip bằng `uname -m` (Python bản Intel qua Rosetta thấy x86_64).
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import io
import os
import re
import sys
import tempfile
import zipfile
from pathlib import Path

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-ollama-local-"))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import localefmt  # noqa: E402

localefmt.dat_ngon_ngu_yeu_cau("vi")

import doc_text  # noqa: E402
import main  # noqa: E402
import ollama_catalog  # noqa: E402
import ollama_local  # noqa: E402

_fails = []


def check(name, cond, detail=""):
    print(("ok   " if cond else "FAIL ") + name + ("" if cond else f"  [{str(detail)[:300]}]"))
    if not cond:
        _fails.append(name)


# ============================================================
# 1. Ollama (Local) được nạp công cụ
# ============================================================
src = (SERVER / "main.py").read_text(encoding="utf-8")
i = src.index("async def _api_stream_mcp(")
than = src[i:src.index("\nasync def ", i + 10) if "\nasync def " in src[i + 10:] else len(src)]
nhanh = set(re.findall(r'prov == "([a-z-]+)":\s*\n\s*return engine\.\w+_chat_with_mcp', than))
check("tìm thấy các nhánh có tool của _api_stream_mcp", {"ollama-local", "openrouter", "deepseek"} <= nhanh, nhanh)
check("mọi provider có nhánh tool đều được nạp tool (CANARY chống sót như ollama-local)",
      nhanh <= set(main._API_TOOL_PROVIDERS), nhanh - set(main._API_TOOL_PROVIDERS))

goi = {}


async def _discover(mode, **kw):
    return [{"name": "javis_read_file"}], {"javis_read_file": "builtin"}


async def _ollama_local(key, model, messages, reasoning, tools, route):
    goi["tools"] = tools
    yield {"type": "text", "content": "ok"}

goc = (main.mcp_hub.discover_all, main.mcp_hub.registry_inventory, main.engine.ollama_local_chat_with_mcp, main._hub_enabled)
main.mcp_hub.discover_all = _discover
main.mcp_hub.registry_inventory = lambda *a, **k: ([], {})
main.engine.ollama_local_chat_with_mcp = _ollama_local
main._hub_enabled = lambda: True
try:
    async def _chay():
        out = main._api_stream_mcp("ollama-local", "", "qwen3.5:9b", [{"role": "user", "content": "đọc file a.md"}])
        if asyncio.iscoroutine(out):
            out = await out
        return [ev async for ev in out]
    evs = asyncio.run(_chay())
    check("Ollama (Local) đi nhánh có tool và nhận đủ tool của hub",
          [t["name"] for t in goi.get("tools") or []] == ["javis_read_file"], goi)
finally:
    (main.mcp_hub.discover_all, main.mcp_hub.registry_inventory, main.engine.ollama_local_chat_with_mcp,
     main._hub_enabled) = goc

# ============================================================
# 2. Bóc chữ PDF và Word
# ============================================================
TMP = Path(tempfile.mkdtemp(prefix="javis-doc-text-"))


def pdf_mot_trang(text: str) -> bytes:
    """Một PDF tối giản có đúng một dòng chữ, viết tay bằng thư viện chuẩn (không cần công cụ tạo PDF nào)."""
    stream = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode()
    objs = [b"<< /Type /Catalog /Pages 2 0 R >>",
            b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
            b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    out, offs = io.BytesIO(), []
    out.write(b"%PDF-1.4\n")
    for n, o in enumerate(objs, 1):
        offs.append(out.tell())
        out.write(f"{n} 0 obj\n".encode() + o + b"\nendobj\n")
    xref = out.tell()
    out.write(f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode())
    for o in offs:
        out.write(f"{o:010d} 00000 n \n".encode())
    out.write(f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode())
    return out.getvalue()


cau = "Doanh thu quy ba tang muoi hai phan tram so voi quy hai nho kenh ban le moi"
(TMP / "bao-cao.pdf").write_bytes(pdf_mot_trang(cau))
t = doc_text.extract(TMP / "bao-cao.pdf")
check("PDF có chữ: bóc ra đúng câu, có đánh số trang", cau in t and "--- Trang 1 ---" in t, t[:200])
(TMP / "scan.pdf").write_bytes(pdf_mot_trang(""))
t = doc_text.extract(TMP / "scan.pdf")
check("PDF scan (không có chữ): nói thẳng, không trả rỗng", "gần như không có chữ" in t, t)
(TMP / "hong.pdf").write_bytes(b"%PDF-1.4 rac")
check("PDF hỏng: câu lỗi, không ném ra ngoài", doc_text.extract(TMP / "hong.pdf").startswith("ERROR:"))

with zipfile.ZipFile(TMP / "hop-dong.docx", "w") as z:
    z.writestr("word/document.xml", '<w:document><w:body><w:p><w:r><w:t>Điều 1: Bên A &amp; Bên B</w:t></w:r></w:p>'
                                    '<w:p><w:r><w:t>Thời hạn</w:t><w:tab/><w:t>18 tháng</w:t></w:r></w:p></w:body></w:document>')
t = doc_text.extract(TMP / "hop-dong.docx")
check("DOCX: bóc chữ, giữ xuống dòng theo đoạn, giải mã &amp;", t == "Điều 1: Bên A & Bên B\nThời hạn\t18 tháng", t)
with zipfile.ZipFile(TMP / "khong-phai.docx", "w") as z:
    z.writestr("a.txt", "x")
check("DOCX thiếu document.xml: câu lỗi rõ", "không phải file Word" in doc_text.extract(TMP / "khong-phai.docx"))
goc_max = doc_text.MAX_DOCX_XML_BYTES
doc_text.MAX_DOCX_XML_BYTES = 10
try:
    check("DOCX giãn ra quá lớn (zip bomb): chặn, không đọc", "quá lớn" in doc_text.extract(TMP / "hop-dong.docx"))
finally:
    doc_text.MAX_DOCX_XML_BYTES = goc_max

HUB = (SERVER / "mcp_hub.py").read_text(encoding="utf-8")
check("javis_read_file dùng doc_text cho .pdf/.docx (chạy ngoài event loop)",
      "if p.suffix.lower() in doc_text.SUFFIXES:" in HUB and "await asyncio.to_thread(doc_text.extract, p)" in HUB)
check("requirements ghim pypdf", re.search(r"^pypdf==\d", (ROOT / "requirements.txt").read_text(encoding="utf-8"), re.M))

# ============================================================
# 4. Chip Apple là GPU
# ============================================================
ollama_catalog.thu_vien = lambda force=False: {"items": [
    {"name": "qwen3.5:9b", "size_gb": 6.6, "tags": ["tools"]},
    {"name": "deepseek-r1:14b", "size_gb": 9.0, "tags": ["thinking"]}]}
apple = {"source": "auto", "ram_gb": 32, "has_gpu": True, "vram_gb": 0, "gpu_name": ollama_local.APPLE_GPU}
ds = ollama_catalog.goi_y(apple)
ghi = [d.get("note", "") for d in ds]
check("chip Apple: gợi ý ghi chạy bằng GPU của chip, không phải CPU và RAM",
      ghi and all("GPU của chip Apple" in g for g in ghi) and not any("CPU và RAM" in g for g in ghi), ghi)
check("chip Apple: model suy nghĩ dài không bị dán nhãn chậm vì chạy CPU", not any(d.get("cham_vi_nghi") for d in ds), ds)
cpu = {"source": "auto", "ram_gb": 32, "has_gpu": False, "vram_gb": 0, "gpu_name": ""}
check("máy không GPU vẫn ghi CPU và RAM như cũ", any("CPU và RAM" in d.get("note", "") for d in ollama_catalog.goi_y(cpu)))

goc_chay = ollama_local._chay
try:
    ollama_local._chay = lambda cmd: {"hw.optional.arm64": "1\n"}.get(cmd[-1], "x86_64\n" if cmd[0] == "uname" else "")
    check("Python bản Intel qua Rosetta (uname báo x86_64): vẫn nhận ra chip Apple qua sysctl", ollama_local.la_apple_silicon())
    ollama_local._chay = lambda cmd: "x86_64\n" if cmd[0] == "uname" else ""
    check("Mac Intel thật: không phải chip Apple", not ollama_local.la_apple_silicon())
finally:
    ollama_local._chay = goc_chay

check("khai tay RAM trên Mac chip Apple không làm mất GPU dùng chung",
      'if tu_doc.get("gpu_name") == ollama_local.APPLE_GPU:' in src and 'd["has_gpu"], d["gpu_name"] = True' in src)

print()
if _fails:
    print(f"ĐỎ {len(_fails)} mục: " + ", ".join(_fails))
    sys.exit(1)
print("Tất cả xanh.")
