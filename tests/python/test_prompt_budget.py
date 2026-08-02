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
# Nâng trần này KHÔNG bị cấm, nhưng phải là một quyết định CÓ Ý THỨC: mỗi 3.500 ký tự thêm
# vào là khoảng 1.000 token nhân với mọi lượt chat của mọi model. Nếu thấy chạm trần, cân
# nhắc chuyển phần đó thành skill (chỉ nạp khi cần) thay vì nhồi tiếp vào prompt lõi.
CLAUDE_MD_MAX_CHARS = 30_000

_claude_md = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")
check(
    f"CLAUDE.md dưới trần {CLAUDE_MD_MAX_CHARS:,} ký tự",
    len(_claude_md) <= CLAUDE_MD_MAX_CHARS,
    f"[hiện {len(_claude_md):,} ký tự ~{_tok(len(_claude_md)):,} token, "
    f"còn {CLAUDE_MD_MAX_CHARS - len(_claude_md):,} ký tự]",
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
