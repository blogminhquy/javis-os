"""Tài liệu song ngữ - Đợt 5 của tầng đa ngôn ngữ.

    python tests/run.py tai_lieu_song_ngu

Tài liệu dịch TAY, không qua từ điển, nên nó không có cơ chế rơi-về nào cả. Bản dịch lệch khỏi
bản gốc là lệch im lặng: người đọc tiếng Anh tin vào một trang không ai đọc lại, còn người viết
tiếng Việt không biết là mình vừa làm bản kia sai.

Test này canh những chỗ hỏng mà đọc bằng mắt không bắt được:
  - Link nội bộ trỏ vào hư không (đường dẫn tương đối đổi độ sâu khi file nằm trong docs/en/).
  - Mất dòng chuyển ngôn ngữ, tức là hai bản tồn tại mà không ai tìm ra bản kia.
  - Con số nhà cung cấp / nhóm rail nói khác nhau giữa hai thứ tiếng.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import pathlib
import re
import sys

_loi = []


def check(ten, dieu_kien):
    print(f"       {'ok  ' if dieu_kien else 'FAIL'} {ten}")
    if not dieu_kien:
        _loi.append(ten)


R = pathlib.Path(ROOT)

# Cặp bản gốc <-> bản dịch. Thêm một trang dịch = thêm một dòng ở đây.
CAP = [
    ("README.md", "README.en.md"),
    ("QUICKSTART.md", "QUICKSTART.en.md"),
    ("CONTRIBUTING.md", "CONTRIBUTING.en.md"),
    ("DEPLOY.md", "DEPLOY.en.md"),
    ("docs/README.md", "docs/en/README.md"),
    ("docs/01-bat-dau-thiet-lap.md", "docs/en/01-getting-started.md"),
    ("docs/02-tro-chuyen-va-giong-noi.md", "docs/en/02-chat-and-voice.md"),
    ("docs/03-do-thi-tri-thuc.md", "docs/en/03-knowledge-graph.md"),
    ("docs/04-phien-hoi-thoai.md", "docs/en/04-sessions.md"),
    ("docs/05-quan-ly-tep-tin.md", "docs/en/05-file-manager.md"),
    ("docs/06-skills.md", "docs/en/06-skills.md"),
    ("docs/07-agents-va-workflows.md", "docs/en/07-agents-and-workflows.md"),
    ("docs/08-viec-dinh-ky.md", "docs/en/08-recurring-jobs.md"),
    ("docs/09-mcp-va-so-lieu.md", "docs/en/09-connections-and-business-data.md"),
    ("docs/10-models-va-engine.md", "docs/en/10-models-and-engines.md"),
    ("docs/11-telegram.md", "docs/en/11-telegram.md"),
    ("docs/12-zalo.md", "docs/en/12-zalo-agent-mcp.md"),
    ("docs/13-second-brain-bo-nho-wiki.md", "docs/en/13-second-brain.md"),
    ("docs/14-bao-mat-tai-khoan.md", "docs/en/14-security-and-accounts.md"),
    ("docs/15-thuong-hieu-ten-mien.md", "docs/en/15-branding-and-domains.md"),
    ("docs/16-cau-hinh-env.md", "docs/en/16-env-configuration.md"),
    ("docs/17-khac-phuc-su-co.md", "docs/en/17-troubleshooting.md"),
    ("docs/18-sao-luu-github.md", "docs/en/18-github-backup.md"),
    ("docs/19-task-va-dataview.md", "docs/en/19-tasks-and-dataview.md"),
    ("docs/20-plugins.md", "docs/en/20-plugins.md"),
    ("docs/21-viec-kanban.md", "docs/en/21-kanban-work.md"),
    ("docs/22-tu-hoc.md", "docs/en/22-self-learning.md"),
    ("docs/23-muc-dung-token.md", "docs/en/23-usage-and-cost.md"),
    ("docs/24-cli-terminal.md", "docs/en/24-cli.md"),
    ("docs/25-chatbot.md", "docs/en/25-chatbots.md"),
    ("docs/26-kenh-zalo-bot.md", "docs/en/26-zalo-bot-channel.md"),
    ("docs/27-tab-code-terminal.md", "docs/en/27-code-terminal.md"),
]

# ============================================================
# 1. Cả hai bản đều tồn tại và TÌM ĐƯỢC NHAU
# ============================================================
for vi, en in CAP:
    p_vi, p_en = R / vi, R / en
    check(f"{en} tồn tại", p_en.is_file())
    if not (p_vi.is_file() and p_en.is_file()):
        continue
    t_vi, t_en = p_vi.read_text(encoding="utf-8"), p_en.read_text(encoding="utf-8")
    # Đường dẫn tương đối giữa hai file, tính từ thư mục chứa file nguồn.
    import os
    rel_en = os.path.relpath(p_en, p_vi.parent).replace(os.sep, "/")
    rel_vi = os.path.relpath(p_vi, p_en.parent).replace(os.sep, "/")
    check(f"{vi} có link sang bản tiếng Anh", f"({rel_en})" in t_vi)
    check(f"{en} có link về bản tiếng Việt", f"({rel_vi})" in t_en)


# ============================================================
# 2. Link nội bộ không được trỏ vào hư không
# ============================================================
# Đây là lỗi HAY GẶP NHẤT khi dịch: bản dịch nằm sâu thêm một tầng (docs/en/) nên mọi link
# tương đối phải lùi thêm một cấp, mà markdown thì không kêu gì khi link chết.
_LINK = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
# Khối code và chữ trong nháy ngược bị bóc ra TRƯỚC khi dò link: tài liệu hay minh hoạ cú pháp
# markdown bằng `![mô tả](attachments/ten-anh.png)`, đó là ví dụ về CÁCH VIẾT chứ không phải một
# link cần tồn tại. Không bóc thì mỗi ví dụ như vậy thành một báo động giả, và báo động giả
# nhiều lần thì người ta bỏ qua cả những link chết thật.
_CODE = re.compile(r"```.*?```|`[^`\n]*`", re.DOTALL)
_hong = []
_quet = [R / f for pair in CAP for f in pair] + [R / "docs/dev/them-mot-ngon-ngu.md"]
for p in _quet:
    if not p.is_file():
        continue
    for m in _LINK.finditer(_CODE.sub(" ", p.read_text(encoding="utf-8"))):
        dich = m.group(1).split("#")[0].strip()
        if not dich or dich.startswith(("http://", "https://", "mailto:", "#")):
            continue
        if not (p.parent / dich).exists():
            _hong.append(f"{p.relative_to(R).as_posix()} -> {dich}")
check("mọi link nội bộ trong tài liệu song ngữ đều tồn tại", not _hong)
if _hong:
    print("              " + "; ".join(_hong[:5]))


# ============================================================
# 3. Hai bản không được nói khác nhau về những con số ĐẾM ĐƯỢC
# ============================================================
# Số nhà cung cấp và số nhóm rail đọc thẳng từ mã nguồn, chứ không chép vào test - chép là
# tạo ra chỗ thứ ba để lệch.
_main = (R / "server" / "main.py").read_text(encoding="utf-8")
_defs = _main[_main.find("PROVIDER_DEFS = ["):]
_defs = _defs[:_defs.find("\n]")]
_so_provider = len(re.findall(r'^\s*\{"id":', _defs, re.MULTILINE))
check(f"đọc được số nhà cung cấp từ mã nguồn ({_so_provider})", _so_provider >= 8)

_console = (R / "dashboard" / "console.js").read_text(encoding="utf-8")
_groups = _console[_console.find("const RAIL_GROUPS = ["):]
_groups = _groups[:_groups.find("\n  ];")]
_so_nhom = len(re.findall(r"\bids:\s*\[", _groups))
check(f"đọc được số nhóm rail từ mã nguồn ({_so_nhom})", _so_nhom >= 5)

_readme_vi = (R / "README.md").read_text(encoding="utf-8")
_readme_en = (R / "README.en.md").read_text(encoding="utf-8")
check(f"README (vi) nói đúng {_so_provider} nhà cung cấp",
      f"{_so_provider} nhà cung cấp" in _readme_vi)
check(f"README (en) nói đúng {_so_provider} nhà cung cấp",
      f"{_so_provider} providers" in _readme_en)
check(f"README (vi) nói đúng {_so_nhom} nhóm rail", f"**{_so_nhom} nhóm**" in _readme_vi)
check(f"README (en) nói đúng {_so_nhom} nhóm rail", f"**{_so_nhom} groups**" in _readme_en)


# ============================================================
# 4. Sổ tay thêm ngôn ngữ phải khớp với ngôn ngữ THẬT đang có
# ============================================================
# Sổ tay là bài nghiệm thu của cả tầng đa ngôn ngữ. Nó liệt kê ngôn ngữ đang có ở cuối; bảng
# đó lệch với sổ đăng ký thì người làm theo sổ tay sẽ đi sai ngay từ bước 1.
_sotay = (R / "docs" / "dev" / "them-mot-ngon-ngu.md").read_text(encoding="utf-8")
import lang_registry
for _ma in lang_registry.cho_giao_dien():
    check(f"sổ tay có nhắc ngôn ngữ `{_ma['ma']}`", f"`{_ma['ma']}`" in _sotay)
check("sổ tay nói rõ bước bộ từ vựng là TUỲ CHỌN nhưng nửa vời thì nguy hiểm",
      "tuỳ chọn" in _sotay.lower() and "MỘT NỬA" in _sotay)


# ============================================================
# 5. Không em dash, ở cả bản dịch
# ============================================================
# Luật của repo (CLAUDE.md): em dash làm giọng đọc TTS khựng. Bản dịch tiếng Anh là chỗ dễ
# quên nhất vì em dash là dấu câu bình thường trong tiếng Anh.
_co_em_dash = [p.relative_to(R).as_posix() for p in _quet
               if p.is_file() and "—" in p.read_text(encoding="utf-8")]
check("không file tài liệu nào dùng em dash", not _co_em_dash)
if _co_em_dash:
    print("              " + ", ".join(_co_em_dash))

print()
if _loi:
    print(f"ĐỎ {len(_loi)} mục: " + "; ".join(_loi[:4]))
    sys.exit(1)
print("Tất cả xanh.")
