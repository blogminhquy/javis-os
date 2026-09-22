"""Canh NGÂN SÁCH các khối cố định đi vào mỗi lượt chat.

    python tests/run.py prompt_budget

Vì sao cần file này: `CLAUDE.md` phình từ 21.479 lên 26.505 ký tự (+23%) trong đúng quãng
thời gian đang xây adaptive runtime để CHỐNG phình, và không ai biết vì không có gì canh.
Mỗi ký tự thêm vào các khối dưới đây là thuế đánh lên MỌI lượt chat của MỌI model.

Bối cảnh số học, để các trần dưới đây không phải con số cảm tính: gói Groq on_demand miễn
phí cho `llama-3.3-70b-versatile` là 12.000 token mỗi phút. Một lượt Javis từng gửi 21.446
token nên bị chặn trước khi kịp trả lời. Đó là bài toán gốc của cả nhánh này.

Ba trần, ba mục đích khác nhau:
  1. `CLAUDE.md` - chặn TRÔI trên đường legacy đang chạy hôm nay.
  2. `CORE_CONTRACT` - khoá thành quả của đường biên dịch, thứ làm Groq chạy được.
  3. Schema tool hạt nhân - khoá thành quả của tầng lazy (Việc 1).
"""
from _paths import ROOT, SERVER  # noqa: E402,F401  - nạp server/ vào sys.path
import json
import os
import sys
import tempfile

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-budget-"))

_fails = []


def check(name, cond, detail=""):
    print(("ok   " if cond else "FAIL ") + name + (("  " + detail) if detail else ""))
    if not cond:
        _fails.append(name)


def _tok(chars):
    """Ước lượng token thô cho tiếng Việt trộn Anh. Đủ chính xác cho việc canh trần."""
    return int(chars / 3.5)


# ============================================================
# 1. CLAUDE.md - system prompt đường legacy
# ============================================================
# TRẦN NÀY ĐÃ ĐÔNG CỨNG (0.64.7). Trước đó nó là một con số "nâng được nếu có ý thức", và
# đúng chỗ này từng có lời dặn "lần chạm trần TIẾP THEO thì cắt thật, đừng nâng số này nữa".
# Lời dặn đó bị bỏ qua ba lần liên tiếp: 21.479 → 26.505 → 30.016 → 33.600. Không ai làm sai
# cả, chỉ là sửa một dòng số cho test xanh lại thì dễ hơn đi cắt nội dung, nên ai cũng chọn
# cách dễ. Một lời dặn trong chú thích không phải là cái chặn.
#
# Cái chặn thật nằm ở chỗ con số này phải KHỚP với `main.PROMPT_KERNEL_MAX_CHARS`, và phép
# thử ngay dưới canh sự khớp đó. Muốn nâng trần thì phải sửa HAI file và viết ra lý do ở cả
# hai chỗ - đủ ma sát để người sửa dừng lại nghĩ, thay vì gõ số mới cho xong việc.
#
# CHẠM TRẦN THÌ LÀM GÌ: đẩy một mục RA KHỎI prompt, đừng nâng số.
#   - Mục chỉ dành cho phiên Claude Code sửa repo → `docs/` (mục "Dev conventions" đã đi
#     đường này ngày 2026-09-22, để lại một dòng trỏ sang, tiết kiệm hơn 1.000 ký tự).
#   - Know-how dùng khi cần chứ không phải mọi lượt → một skill trong `skills/` (router chỉ
#     nạp nội dung skill lúc thật sự gọi tới).
# Cả hai cách đều giữ nguyên năng lực, chỉ đổi chỗ đặt. Nâng trần thì không.
#
# Trần để ở 33.600 trong khi file đang 33.012: chừa chừng 590 ký tự để sửa lỗi chính tả hay
# làm rõ một câu luật, cố tình KHÔNG đủ để nhét thêm một mục.
#
# ĐÃ ĐO THẬT (chủ repo chạy trên máy có mạng, 28/08/2026): 33.369 ký tự = **6.555 token** theo
# `cl100k_base`, tức 5,09 ký tự/token. Ba điều rút ra:
#
#   1. Bản tiếng Anh nhiều ký tự hơn nhưng ÍT TOKEN HƠN bản tiếng Việt cũ - đúng như dự đoán,
#      và nay là số đo chứ không phải suy luận. Bản cũ ăn khoảng 8.576 token theo chính thước
#      đo của file này (30.016 / 3.5), nên đổi ngôn ngữ TIẾT KIỆM chứ không tốn thêm.
#   2. Tỉ lệ 3.5 ở `_tok()` được cân cho tiếng Việt nên nó ĐÁNH GIÁ CAO chi phí của văn bản
#      tiếng Anh chừng 45%. Trần 33.600 ký tự vì vậy tương đương chỉ ~6.600 token thật, thoải
#      mái hơn con số nhìn vào tưởng. KHÔNG sửa `_tok()` thành hai hệ số theo ngôn ngữ: nó còn
#      đo mấy nguồn khác trong file này, đổi một chỗ là lệch cả bảng.
#   3. `cl100k_base` là bộ tách token của OpenAI, KHÔNG phải của Claude, nên 6.555 là ước lượng
#      chứ không phải con số Anthropic tính tiền. Nó vẫn dùng được cho việc ở đây vì thứ cần
#      biết là SO SÁNH giữa hai bản, và cùng một thước thì so được.
#
# Đo lại khi cần (chú ý `python -m pip` để chắc chắn cài vào đúng Python đang chạy):
#     python -m pip install tiktoken
#     python -c "import tiktoken; print(len(tiktoken.get_encoding('cl100k_base').encode(open('CLAUDE.md', encoding='utf-8').read())))"
KERNEL_MAX_CHARS = 33_600

_claude_md = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")
check(
    f"CLAUDE.md dưới trần {KERNEL_MAX_CHARS:,} ký tự",
    len(_claude_md) <= KERNEL_MAX_CHARS,
    f"[hiện {len(_claude_md):,} ký tự ~{_tok(len(_claude_md)):,} token, "
    f"còn {KERNEL_MAX_CHARS - len(_claude_md):,} ký tự]",
)

# Mục "Dev conventions" đã ĐẨY RA NGOÀI ngày 2026-09-22 (đúng cách file này dặn: chạm trần thì
# cắt thật hoặc đẩy một mục ra, đừng nâng số). Nó chỉ dành cho phiên Claude Code sửa repo, còn
# người dùng Javis không bao giờ cần, nên để trong prompt là đánh thuế mọi lượt chat. Trong
# CLAUDE.md giờ chỉ còn một dòng trỏ sang. Hai canary dưới đây giữ cho dòng trỏ không rỗng:
# xoá file mà quên dòng trỏ, hay đổi tên file mà quên sửa CLAUDE.md, đều đỏ ở đây.
_QUY_UOC = ROOT / "docs" / "quy-uoc-dev.md"
check(
    "CLAUDE.md còn trỏ sang file quy ước dev",
    "docs/quy-uoc-dev.md" in _claude_md,
)
check(
    "file quy ước dev có thật và còn luật đặt xí chỗ số phiên bản",
    _QUY_UOC.exists() and "xí chỗ" in _QUY_UOC.read_text(encoding="utf-8"),
)

# ------------------------------------------------------------
# 1b. Trần phải ĐÔNG, và tổng thật phải đo được
# ------------------------------------------------------------
# Hai phép thử dưới đây là cái biến trần trên từ "lời dặn" thành "cái chặn".
import main  # noqa: E402

check(
    "trần trong code và trần trong test vẫn khớp nhau",
    main.PROMPT_KERNEL_MAX_CHARS == KERNEL_MAX_CHARS,
    f"[main.PROMPT_KERNEL_MAX_CHARS={main.PROMPT_KERNEL_MAX_CHARS:,}, "
    f"test KERNEL_MAX_CHARS={KERNEL_MAX_CHARS:,}]",
)

# Và phép thử QUAN TRỌNG hơn cả trần: TỔNG ký tự cố định đi kèm mỗi lượt chat.
# Vì sao nó quan trọng hơn: nhân prompt chỉ là MỘT khối trong khoảng bảy khối được ghép vào
# system prompt, mà trước 0.64.7 chỉ khối đó có người canh. Hệ quả là gọt CLAUDE.md xuống
# từng trăm ký tự trong khi khối kênh hội thoại lặng lẽ chiếm hơn 7.000 - ai cũng đang nhìn
# đúng một phần tư vấn đề. `do_phan_bo_prompt` đo BẢN THẬT (lắp prompt rồi đếm), nên số ở
# đây là số thật chứ không phải cộng ước lượng.
PROMPT_TONG_MAX_CHARS = 50_000

_pb = main.do_phan_bo_prompt("brain")
check("đo được bảng phân bổ prompt", "loi" not in _pb, str(_pb.get("loi", "")))

if "loi" not in _pb:
    _bang = "\n".join(f"      {k['ky_tu']:>7,}  {k['phan_tram']:>5}%  {k['ten'][:58]}"
                      for k in _pb["khoi"])
    print(f"      {_pb['nhan_ky_tu']:>7,}  "
          f"{_pb['nhan_ky_tu'] * 100.0 / max(1, _pb['tong_ky_tu']):>5.1f}%  "
          f"NHÂN PROMPT (CLAUDE.md)")
    print(_bang)

    check(
        f"tổng prompt cố định dưới trần {PROMPT_TONG_MAX_CHARS:,} ký tự",
        _pb["tong_ky_tu"] <= PROMPT_TONG_MAX_CHARS,
        f"[hiện {_pb['tong_ky_tu']:,} ký tự ~{_pb['tong_token_uoc']:,} token, "
        f"còn {PROMPT_TONG_MAX_CHARS - _pb['tong_ky_tu']:,} ký tự]",
    )
    # Bảng cộng lại phải ra đúng tổng. Đây là phép tự kiểm của chính phép đo: nếu ai đó thêm
    # một khối bằng kiểu tiêu đề khác, khối đó sẽ bị cộng nhầm vào khối đứng trước và không
    # ai biết - trừ khi con số bị lệch, mà phép này bắt đúng chỗ lệch đó.
    _cong = _pb["nhan_ky_tu"] + sum(k["ky_tu"] for k in _pb["khoi"])
    check(
        "bảng phân bổ cộng lại đúng bằng tổng (không khối nào rơi mất)",
        _cong == _pb["tong_ky_tu"],
        f"[cộng {_cong:,} vs tổng {_pb['tong_ky_tu']:,}]",
    )
    # Nhân prompt trong bảng phải đúng là CLAUDE.md (lệch đúng 2 ký tự xuống dòng nối khối
    # sau). Lệch nhiều hơn nghĩa là phép tách tiêu đề đã hiểu sai đâu là nhân.
    check(
        "phần 'nhân' trong bảng đúng là CLAUDE.md",
        abs(_pb["nhan_ky_tu"] - len(_claude_md)) <= 4,
        f"[bảng {_pb['nhan_ky_tu']:,} vs file {len(_claude_md):,}]",
    )

# ============================================================
# 2. CORE_CONTRACT - prompt lõi đường biên dịch (thay CLAUDE.md khi canary bật)
# ============================================================
# Đây là trần QUAN TRỌNG NHẤT file này. CORE_CONTRACT là thứ thay thế CLAUDE.md khi
# context_sources bật, và chính nó làm cho model bị siết TPM dùng được. Nó phình lên là
# mất luôn lý do tồn tại của cả nhánh.
CORE_CONTRACT_MAX_CHARS = 2_000

import context_compiler  # noqa: E402

_core = context_compiler.CORE_CONTRACT
check(
    f"CORE_CONTRACT dưới trần {CORE_CONTRACT_MAX_CHARS:,} ký tự",
    len(_core) <= CORE_CONTRACT_MAX_CHARS,
    f"[hiện {len(_core):,} ký tự ~{_tok(len(_core)):,} token]",
)

# Và khoá TỶ LỆ, không chỉ trị tuyệt đối: đường biên dịch phải nhỏ hơn hẳn đường legacy,
# nếu không thì bật canary lên cũng không cứu được gì. Kiểm bằng tỷ lệ để trần này còn
# đúng cả khi CLAUDE.md được dọn gọn lại sau này.
_ratio = len(_core) / max(1, len(_claude_md))
check(
    "đường biên dịch nhỏ hơn legacy ít nhất 10 lần",
    _ratio <= 0.10,
    f"[CORE_CONTRACT bằng {_ratio * 100:.1f}% CLAUDE.md, "
    f"tiết kiệm {(1 - _ratio) * 100:.0f}%]",
)

# ============================================================
# 3. Schema tool hiện thẳng - khoá thành quả tầng lazy
# ============================================================
# Trước Việc 1: 26 tool nặng khoảng 17.000 ký tự đi vào mọi request. Trần này bảo đảm
# nhóm hạt nhân không âm thầm phình trở lại (thêm tool vào CORE_TOOL_FNS, hoặc mô tả của
# một tool hạt nhân dài ra theo số thứ user cắm thêm).
CORE_TOOLS_MAX_CHARS = 3_000

import mcp_hub  # noqa: E402
import config  # noqa: E402

_vault = tempfile.mkdtemp(prefix="javis-budget-vault-")
os.makedirs(os.path.join(_vault, "skills"), exist_ok=True)
# 30 skill mô tả dài: mô phỏng brain thật, để bắt được đúng kiểu phình theo N.
for _i in range(30):
    _d = os.path.join(_vault, "skills", f"skill-{_i:02d}")
    os.makedirs(_d, exist_ok=True)
    with open(os.path.join(_d, "SKILL.md"), "w", encoding="utf-8") as _fh:
        _fh.write(f"---\nname: skill {_i:02d}\ndescription: "
                  + ("mô tả skill dài để giống thật " * 4)
                  + "\ngroup: Test\n---\nnội dung\n")

_tools, _route = mcp_hub._builtin_tools("full", _vault)
_before = sum(len(json.dumps(t, ensure_ascii=False)) for t in _tools)

config.read_settings = lambda: {"mcp": {"lazy_tools": True}}   # type: ignore[assignment]
_lazy_tools, _lazy_route = mcp_hub._apply_lazy(_tools, _route)
_after = sum(len(json.dumps(t, ensure_ascii=False)) for t in _lazy_tools)

check(
    f"schema tool hiện thẳng dưới trần {CORE_TOOLS_MAX_CHARS:,} ký tự",
    _after <= CORE_TOOLS_MAX_CHARS,
    f"[hiện {_after:,} ký tự ~{_tok(_after):,} token, {len(_lazy_tools)} tool]",
)
check(
    "tầng lazy thật sự cắt được phần phình theo số skill",
    _after < _before,
    f"[{_before:,} → {_after:,} ký tự, giảm {(1 - _after / max(1, _before)) * 100:.0f}%]",
)

# ============================================================
# 4. Tổng chi phí cố định đường biên dịch phải vừa model bị siết nhất
# ============================================================
# Đây là phép thử cuối cùng và là lý do tồn tại của cả nhánh: cộng các khối cố định của
# đường biên dịch lại, nó phải nằm gọn dưới hạn mức của gói Groq miễn phí, còn chừa chỗ
# cho câu hỏi, lịch sử và câu trả lời.
GROQ_FREE_TPM = 12_000
COMPILED_FIXED_MAX_TOKENS = 3_000     # chừa hơn 9.000 token cho hội thoại + câu trả lời

_compiled_fixed = _tok(len(_core) + _after)
check(
    f"chi phí cố định đường biên dịch dưới {COMPILED_FIXED_MAX_TOKENS:,} token",
    _compiled_fixed <= COMPILED_FIXED_MAX_TOKENS,
    f"[hiện ~{_compiled_fixed:,} token, còn ~{GROQ_FREE_TPM - _compiled_fixed:,} "
    f"token dưới hạn mức Groq miễn phí {GROQ_FREE_TPM:,} TPM]",
)

print()
if _fails:
    print(f"THẤT BẠI {len(_fails)}: {_fails}")
    sys.exit(1)
print("OK - test_prompt_budget: tất cả pass")
