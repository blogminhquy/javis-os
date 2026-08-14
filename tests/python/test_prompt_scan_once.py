"""build_system_prompt chỉ được quét cây skill MỘT lần, và chia sẻ không đổi kết quả.

    python tests/run.py prompt_scan_once     (KHÔNG mạng)

Bối cảnh: trước 0.9.237, _javis_capability_summary gọi skill_router.list_skills còn
_skill_router_block gọi list_enabled_meta (vốn là list_skills lọc lại), nên mỗi lượt chat
đi và parse YAML cả cây skill hai lần. Nay build_system_prompt quét một lần rồi truyền
xuống. Rủi ro của kiểu tối ưu này là im lặng đổi nội dung system prompt, nên test khoá
chặt hai điều: ĐẾM số lần quét, và ĐỐI CHIẾU nội dung sinh ra phải y hệt đường cũ.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401  - nạp server/ vào sys.path (xem tests/python/_paths.py)
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-scanonce-"))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import main            # noqa: E402
import skill_router    # noqa: E402

_fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)


# --- brain giả có skill thật để quét ---
brain_dir = Path(tempfile.mkdtemp(prefix="javis-scanonce-brain-"))
skills_dir = brain_dir / "skills"
for slug, group, enabled in [("viet-email", "Nội dung", True),
                             ("bao-cao-doanh-thu", "Bán hàng", True),
                             ("skill-tat", "Vận hành", False)]:
    d = (skills_dir / ".disabled" / slug) if not enabled else (skills_dir / slug)
    d.mkdir(parents=True, exist_ok=True)
    (d / "SKILL.md").write_text(
        f"---\nname: {slug}\ndescription: mô tả của {slug}\ngroup: {group}\n---\n\nThân skill.\n",
        encoding="utf-8")

brain = str(brain_dir)
root = main._brain_root(brain)
check("brain thử nghiệm được nhận đúng root", root == brain)

skills = skill_router.list_skills(root)
check(f"quét thấy 3 skill ({len(skills)})", len(skills) == 3)
check("2 skill bật, 1 skill tắt",
      sum(1 for s in skills if s["enabled"]) == 2 and sum(1 for s in skills if not s["enabled"]) == 1)

# --- 1. Chia sẻ kết quả KHÔNG được đổi nội dung sinh ra ---
check("_gather_capabilities: truyền sẵn == tự quét",
      main._gather_capabilities(brain, skills) == main._gather_capabilities(brain))
check("_javis_capability_summary: truyền sẵn == tự quét",
      main._javis_capability_summary(brain, skills) == main._javis_capability_summary(brain))
check("_skill_router_block: truyền sẵn == tự quét",
      main._skill_router_block(brain, root, skills) == main._skill_router_block(brain, root))

# --- 2. skills=None phải giữ nguyên đường cũ (không im lặng trả rỗng) ---
check("_skill_router_block(None) vẫn liệt kê skill bật",
      "viet-email" in main._skill_router_block(brain, root, None))
check("_skill_router_block chỉ liệt kê skill BẬT, không kèm skill tắt",
      "skill-tat" not in main._skill_router_block(brain, root, skills))

# --- 3. Đếm thật: build_system_prompt chỉ quét MỘT lần ---
_that = skill_router.list_skills
dem = {"n": 0}


def _dem_list_skills(r, lang=""):
    # `lang` phải có mặt: build_system_prompt quét cây skill theo ngôn ngữ của lượt (mô tả
    # skill có bản dịch). Stub thiếu tham số thì ném TypeError, mà build_system_prompt nuốt
    # lỗi quét để không làm hỏng cả prompt - hỏng sẽ lộ ra ở phép so nội dung bên dưới chứ
    # không phải ở đây.
    dem["n"] += 1
    return _that(r, lang)


try:
    skill_router.list_skills = _dem_list_skills
    main.skill_router.list_skills = _dem_list_skills
    dem["n"] = 0
    prompt_moi = main.build_system_prompt(brain)
    n_moi = dem["n"]
finally:
    skill_router.list_skills = _that
    main.skill_router.list_skills = _that

check(f"build_system_prompt quét cây skill đúng 1 lần (đếm được {n_moi})", n_moi == 1)

# --- 4. Nội dung system prompt phải giống hệt đường KHÔNG chia sẻ ---
# Dựng lại thủ công theo đường cũ rồi so hai khối liên quan.
khoi_cu = main._javis_capability_summary(brain) + main._skill_router_block(brain, root)
check("hai khối năng lực + router có mặt nguyên vẹn trong system prompt",
      khoi_cu and khoi_cu in prompt_moi)

# --- 5. Lỗi khi quét thì không được làm hỏng cả prompt ---
def _no_tung(_r):
    raise RuntimeError("giả lập ổ đĩa lỗi")


try:
    skill_router.list_skills = _no_tung
    main.skill_router.list_skills = _no_tung
    prompt_loi = main.build_system_prompt(brain)
finally:
    skill_router.list_skills = _that
    main.skill_router.list_skills = _that

check("quét skill nổ lỗi thì build_system_prompt vẫn trả prompt, không ném ra ngoài",
      isinstance(prompt_loi, str) and len(prompt_loi) > 100)
check("prompt lúc lỗi vẫn còn khối LỚP AGENTIC (chỉ mất phần skill)",
      "LỚP AGENTIC" in prompt_loi)

print()
if _fails:
    print(f"FAIL {len(_fails)} test: " + ", ".join(_fails))
    sys.exit(1)
print("TẤT CẢ PASS")
