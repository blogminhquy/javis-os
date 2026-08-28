"""Xưng hô: Javis gọi người dùng là "bạn", tự xưng là "mình".

    python tests/run.py xung_ho

Vì sao có test này. Tiếng Việt bắt buộc chọn đại từ theo GIỚI TÍNH và TUỔI TÁC ngay từ câu
đầu tiên, trước khi biết gì về người đang nói. Javis phục vụ nhiều người, nên mặc định "anh/em"
là đoán, và đoán sai thì gọi nhầm giới một người thật. "bạn/mình" thì không bao giờ sai. Chủ
repo chốt luật này ngày 2026-08-14: chỉ chuyển sang anh/em hoặc chị/em khi ĐÃ BIẾT CHẮC giới
tính, và biết là do có căn cứ (ký ức trong brain, hoặc người đó tự nói), chứ không suy từ tên.

Test quét **chuỗi ký tự** trong mã nguồn, không quét chú thích: chú thích trong repo này có
nhiều chỗ TRÍCH NGUYÊN VĂN lời chủ repo hoặc trích đúng câu Javis đã nói lúc gặp lỗi. Sửa một
câu trích là làm sai bản ghi, nên chúng nằm ngoài phạm vi có chủ ý.

Cùng lối với `tests/js/test_i18n.mjs`: KHÔNG đòi dọn cả repo, chỉ đòi những file ĐÃ dọn thì
không được thụt lùi. Dọn tới đâu, thêm tên file vào `DA_DON` tới đó.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import ast
import pathlib
import re
import sys

_loi = []


def check(ten, dieu_kien, chi_tiet=""):
    print(f"       {'ok  ' if dieu_kien else 'FAIL'} {ten}")
    if not dieu_kien:
        _loi.append(ten)
        if chi_tiet:
            print("              " + chi_tiet)


R = pathlib.Path(ROOT)

# Quét TOÀN BỘ server/ và system/, trừ danh sách miễn trừ dưới. Quét cả cây chứ không liệt kê
# vài file đã dọn, vì đợt dọn đầu tìm ra 20 chỗ nằm rải ở 9 file khác nhau - liệt kê tay thì
# lần sau lại sót đúng kiểu đó.
GOC_QUET = ("server", "system")

# CỐ Ý KHÔNG dọn, và lý do:
MIEN_TRU = {
    # Bot chuyên trách nói với KHÁCH của chủ shop, không nói với chủ máy. Lối "anh chị / em"
    # là phép lịch sự bán hàng chuẩn, và "anh chị" gọi được CẢ HAI giới nên không đoán nhầm ai.
    "server/chatbot_runtime.py",
    "server/telegram_bot.py",
    # Đại từ ở đây là DỮ LIỆU để dò ngôn ngữ và khớp mẫu, không phải chữ hiện ra cho ai đọc.
    # Sửa là làm YẾU bộ dò - đúng thứ mà đợt đa ngôn ngữ vừa dựng lên.
    "server/lang.py",
    "server/lang_registry.py",
    "server/engine.py",
    "server/memory_index.py",
    "server/context_compiler.py",
    "server/chatbot_grounding.py",
    # `<em>` của HTML, không phải đại từ.
    "server/substack_mcp.py",
}

# "anh" đứng riêng làm đại từ. "tiếng Anh", "nước Anh", "giọng Anh", "Anh ngữ" là tên ngôn ngữ
# và quốc gia - bắt cả chúng thì test thành thứ phải đi vòng qua.
_ANH = re.compile(r"(?<![^\W\d_])[Aa]nh(?![^\W\d_])")
_ANH_HOP_LE = re.compile(r"(tiếng|nước|người|giọng|bản|sang|từ)\s+[Aa]nh|[Aa]nh\s+(ngữ|chị)", re.I)
# "em" đứng riêng. "em dash" là tên ký tự, không phải đại từ.
_EM = re.compile(r"(?<![^\W\d_])[Ee]m(?![^\W\d_])(?!\s+dash)")


def _chuoi_trong(path: pathlib.Path):
    """Chuỗi ký tự CHẠY THẬT trong file .py, kèm số dòng.

    Bỏ qua hai thứ, cùng một lý do: chú thích không lọt vào đây (dùng AST chứ không đọc dòng),
    và docstring bị loại ra bằng tay. Cả hai là TÀI LIỆU, mà tài liệu trong repo này có nhiều
    chỗ trích nguyên văn lời chủ repo hoặc trích đúng câu Javis đã nói lúc gặp lỗi - sửa một
    câu trích là làm sai bản ghi.
    """
    try:
        cay = ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError:
        return
    bo_qua = set()
    for node in ast.walk(cay):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            than = getattr(node, "body", None) or []
            if (than and isinstance(than[0], ast.Expr)
                    and isinstance(than[0].value, ast.Constant)
                    and isinstance(than[0].value.value, str)):
                bo_qua.add(id(than[0].value))
    for node in ast.walk(cay):
        if (isinstance(node, ast.Constant) and isinstance(node.value, str)
                and id(node) not in bo_qua):
            yield node.lineno, node.value


# ============================================================
# 1. File đã dọn không được có đại từ đoán giới
# ============================================================
_xau, _so_file = [], 0
for _goc in GOC_QUET:
    for p in sorted((R / _goc).rglob("*.py")):
        rel = p.relative_to(R).as_posix()
        if rel in MIEN_TRU or "__pycache__" in rel or "/lexicon/" in rel:
            continue
        _so_file += 1
        for dong, s in _chuoi_trong(p):
            # Tên file ví dụ ("attachments/anh.jpg") không phải đại từ.
            s_sach = re.sub(r"\S*/\S+", " ", s)
            if _ANH.search(_ANH_HOP_LE.sub(" ", s_sach)) or _EM.search(s_sach):
                _xau.append(f"{rel}:{dong}")
check(f"không chuỗi nào đoán giới người dùng ({_so_file} file)", not _xau,
      ", ".join(_xau[:6]))


# ============================================================
# 2. Luật phải nằm trong CLAUDE.md, không chỉ nằm trong đầu một phiên chat
# ============================================================
# Prompt là nơi DUY NHẤT luật này có hiệu lực với mọi bộ não. Ghi vào đây rồi thì Claude Code,
# Codex hay engine API đều theo như nhau; quên ghi thì nó chỉ đúng trong đúng phiên vừa nói.
_cm = (R / "CLAUDE.md").read_text(encoding="utf-8")
check("CLAUDE.md có luật xưng hô", "Address forms (Vietnamese)" in _cm)
check("và nêu mặc định bạn/mình", '"bạn"' in _cm and '"mình"' in _cm)
check("và nói rõ chỉ đổi khi ĐÃ BIẾT CHẮC giới tính",
      "KNOW the speaker's gender for certain" in _cm)
# Suy giới tính từ tên riêng là cái bẫy dễ sa nhất, vì nó có vẻ như một suy luận hợp lý.
check("CANARY: cấm suy giới tính từ tên riêng",
      "Inferring from a given name is NOT sufficient evidence" in _cm)
# Luật mới phải nói rõ nó thắng ký ức cũ, nếu không thì bộ nhớ dài hạn của máy đang chạy
# (còn ghi "thích xưng anh/em" từ thời một người dùng) sẽ lặng lẽ kéo giọng về như cũ.
check("CANARY: luật mới thắng ký ức cũ trong bộ nhớ dài hạn",
      "an old memory" in _cm and "beats that memory" in _cm)
check("và nói rõ chatbot với KHÁCH vẫn giữ lối anh chị",
      "anh chị" in _cm and "chatbot" in _cm)   # hai cụm này VẪN là tiếng Việt: đó là đại từ thật


# ============================================================
# 3. Bộ dò lời hứa phải bắt được giọng MỚI
# ============================================================
# Đây là chỗ đổi giọng có thể làm hỏng một cổng đang chạy: `background_status.detect_promise`
# dán một dòng đính chính khi Javis hứa suông. Mẫu chỉ bắt "em ... báo lại" mà giọng đổi sang
# "mình" thì cổng im lặng mất tác dụng, và không có gì kêu lên.
import background_status

for cau in ("Ok, mình sẽ báo lại sau nhé",
            "Mình đang dò lại code, có kết quả mình báo ngay",
            "Bạn chờ mình chút nhé",
            "Xong mình báo lại"):
    check(f"bắt được lời hứa giọng mới: {cau[:34]!r}",
          bool(background_status.detect_promise(cau, "vi")))

check("và vẫn bắt được giọng cũ (máy đang chạy chưa nạp prompt mới)",
      bool(background_status.detect_promise("Có kết quả em báo ngay", "vi")))
check("câu KHÔNG hứa thì không bị dán đính chính oan",
      not background_status.detect_promise("Doanh thu hôm nay 4,2 triệu, tăng 12% so hôm qua.", "vi"))

print()
if _loi:
    print(f"ĐỎ {len(_loi)} mục: " + "; ".join(_loi[:4]))
    sys.exit(1)
print("Tất cả xanh.")
