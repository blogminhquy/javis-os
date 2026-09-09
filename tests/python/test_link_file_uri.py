"""Link `file://` trong câu trả lời phải bấm mở được, và tên file có ngoặc tròn không bị cắt.

    python tests/run.py link_file_uri      (KHÔNG mạng, KHÔNG cần đăng nhập)

Chủ repo báo (2026-09-09): bấm link wiki vừa ingest bằng Antigravity thì dashboard bật khung
"Không tìm thấy file - Link trỏ tới file:///brains/Brain Default/wiki/30 Ngày Làm Chủ
Antigravity (CES Global).md nhưng chỗ đó không có gì". Hai gốc:

  1. Harness của Antigravity dặn model "dùng link markdown với giao thức file://" và model mã
     hoá khoảng trắng thành %20. Bộ chuẩn hoá link phía server (0.55.58) bỏ qua mọi target có
     "://" nên để nguyên; dashboard thì không nhận `file:` ở nhánh nào, coi nó là đường tương
     đối trong vault và đi hỏi server một file tên "file:///..." → 404.
  2. Regex link markdown phía server cắt target ở dấu ")" ĐẦU TIÊN, nên tên file có ngoặc tròn
     ("(CES Global).md") bị cụt đuôi: link đúng bị báo "không thấy file", còn chuẩn hoá thì ra
     đường dẫn thiếu đuôi. Dashboard đã nhận ngoặc cân bằng từ trước; hai đầu phải cùng luật.

File này canh: gỡ giao thức file:// ở server (link, ảnh, backtick, chữ trần), báo "không thấy"
đúng chỗ, regex nhận ngoặc cân bằng, và prompt dặn thẳng model đừng dùng file://.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401  - nạp server/ vào sys.path
import os
import sys
import tempfile
from pathlib import Path
from urllib.parse import quote

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-fileuri-")

import main  # noqa: E402
import channel_context  # noqa: E402

_fails = []


def check(name, cond, them=""):
    print(("ok   " if cond else "FAIL ") + name
          + (("  [" + str(them)[:200] + "]") if them and not cond else ""))
    if not cond:
        _fails.append(name)


MAIN = (ROOT / "server" / "main.py").read_text(encoding="utf-8")
TEN = "30 Ngày Làm Chủ Antigravity (CES Global).md"
brain = Path(tempfile.mkdtemp(prefix="javis-brain-")).resolve()
(brain / "wiki").mkdir()
(brain / "wiki" / TEN).write_text("x", encoding="utf-8")
(brain / "attachments").mkdir()
(brain / "attachments" / "so do.png").write_bytes(b"\x89PNG")
ngoai = Path(tempfile.mkdtemp(prefix="javis-ngoai-")).resolve()
(ngoai / "lac.md").write_text("z", encoding="utf-8")
ENC = quote(f"{brain}/wiki/{TEN}")          # dạng model ghi: %20, %C3%A0, %28...


def H(t, w=None):
    return main._chuan_hoa_link_file(str(brain), t, w)


def K(t):
    return main._link_file_khong_thay(str(brain), t)


# ============================================================
# 1. Gỡ giao thức file://
# ============================================================
check("_go_file_uri: file:///a/b → /a/b (giải mã %xx)",
      main._go_file_uri("file:///brains/Brain%20Default/wiki/x.md") == "/brains/Brain Default/wiki/x.md")
check("_go_file_uri: file://localhost/a → /a", main._go_file_uri("file://localhost/a/b.md") == "/a/b.md")
check("_go_file_uri: file:/C:/x (Windows) → C:/x", main._go_file_uri("file:///C:/x/y.md") == "C:/x/y.md")
check("_go_file_uri: không phải file URI → None",
      main._go_file_uri("https://a.vn/b.md") is None and main._go_file_uri("wiki/a.md") is None
      and main._go_file_uri("file:a.md") is None)

# ============================================================
# 2. Chuẩn hoá: CHÍNH cái link chủ repo báo
# ============================================================
check("CANARY: link file:// mã hoá %xx trỏ vào brain → tương đối theo gốc brain",
      H(f"[x](file://{ENC})") == f"[x](wiki/{TEN})", H(f"[x](file://{ENC})"))
check("file:// với khoảng trắng và ngoặc trần cũng ra đúng",
      H(f"[x](file://{brain}/wiki/{TEN})") == f"[x](wiki/{TEN})", H(f"[x](file://{brain}/wiki/{TEN})"))
check("file://localhost/... cũng gỡ được",
      H(f"[x](file://localhost{ENC})") == f"[x](wiki/{TEN})")
check("file:///wiki/x.md (tương đối theo brain nhưng khoác giao thức) → mở được nếu file có thật",
      H("[x](file:///wiki/" + quote(TEN) + ")") == f"[x](wiki/{TEN})", H("[x](file:///wiki/" + quote(TEN) + ")"))
check("file:///wiki/khong-co.md → giữ nguyên (không bịa)",
      H("[x](file:///wiki/khong-co.md)") == "[x](file:///wiki/khong-co.md)")
check("CANARY: file:// NGOÀI brain giữ nguyên (không bịa một đường vào brain)",
      H(f"[x](file://{ngoai}/lac.md)") == f"[x](file://{ngoai}/lac.md)")
check("ảnh markdown file:// cũng chuẩn hoá",
      H(f"![sơ đồ](file://{brain}/attachments/so%20do.png)") == "![sơ đồ](attachments/so do.png)")
check("file:// trong backtick → backtick tương đối",
      H(f"Đã lưu `file://{ENC}`") == f"Đã lưu `wiki/{TEN}`", H(f"Đã lưu `file://{ENC}`"))
check("file:// TRẦN trong câu → bọc backtick tương đối",
      H(f"Đã lưu file://{ENC} nhé") == f"Đã lưu `wiki/{TEN}` nhé", H(f"Đã lưu file://{ENC} nhé"))
check("file:// trần ngoài brain giữ nguyên", H(f"xem file://{ngoai}/lac.md đi") == f"xem file://{ngoai}/lac.md đi")
check("autolink <file:///...> không bị đụng", H("xem <file:///x/y.md> nhé") == "xem <file:///x/y.md> nhé")
check("URL http có (ngoặc) trong query giữ nguyên",
      H("[u](https://a.vn/x?y=(1))") == "[u](https://a.vn/x?y=(1))")

# ============================================================
# 3. "Không thấy file": file:// ngoài brain thì báo, trong brain thì không
# ============================================================
check("file:// trỏ đúng file trong brain → không báo", K(f"[x](file://{ENC})") == [])
check("file:// ngoài brain → báo bằng đường dẫn đã gỡ giao thức",
      K(f"[x](file://{ngoai}/lac.md)") == [f"{ngoai}/lac.md"], K(f"[x](file://{ngoai}/lac.md)"))
check("file:///wiki/khong-co.md → báo", K("[x](file:///wiki/khong-co.md)") == ["/wiki/khong-co.md"])

# ============================================================
# 4. Regex link markdown: ngoặc tròn cân bằng trong tên file
# ============================================================
_tg = [m["raw"] for m in channel_context.markdown_targets(
    f"[x](wiki/{TEN}) ![a](b.png) [c](<d e.md>) [t](a.md \"tiêu đề\") [k](a(b)c.md)")]
check("CANARY: tên file có (ngoặc) không bị cắt ở dấu ) đầu tiên",
      _tg[0] == f"wiki/{TEN}", _tg)
check("các dạng khác vẫn đúng: ảnh, <...>, có title, ngoặc giữa tên",
      _tg[1:] == ["b.png", "d e.md", "a.md", "a(b)c.md"], _tg)
check("link đúng có (ngoặc) KHÔNG còn bị báo 'không thấy file'", K(f"[x](wiki/{TEN})") == [])
check("chuẩn hoá tuyệt đối có (ngoặc) ra đủ đuôi .md",
      H(f"[x]({brain}/wiki/{TEN})") == f"[x](wiki/{TEN})", H(f"[x]({brain}/wiki/{TEN})"))

# ============================================================
# 5. Prompt: dặn thẳng model không dùng file://
# ============================================================
check("LỚP AGENTIC dặn KHÔNG dùng giao thức file:// và không mã hoá %20",
      "KHÔNG dùng giao thức `file://` và không mã hoá %20" in MAIN)
check("không em dash trong đoạn dặn", "\u2014" not in MAIN[MAIN.find("LỚP AGENTIC"):MAIN.find("LỚP AGENTIC") + 2500])

print("")
if _fails:
    print(f"{len(_fails)} test HỎNG: " + ", ".join(_fails))
    sys.exit(1)
print("Tất cả test link_file_uri đã qua.")
