"""Test: giảm PHẦN ĐẦU CỐ ĐỊNH mà mọi lượt chat đều phải trả tiền.

    python tests/run.py prefix_slim

Bối cảnh (đo trên brain thật "My Bullet Journal"): prefix mỗi lượt chat đi từ 38k token
(30/6) lên 85k (cuối tháng 7). Bóc ra: Claude Code tự nó ~49k, system prompt Javis 14,4k,
tool hub 8k, danh sách skill của brain ~5k, CLAUDE.md của brain 5,3k. MEMORY.md chỉ 5,7k
tức 7% - nên KHÔNG cắt bộ nhớ (thử rồi: rút mô tả xuống 60 ký tự chỉ tiết kiệm 1,4k token,
đổi khả năng nhớ lấy chừng đó là lỗ).

Thủ phạm thật là skill: brain đi từ 7 skill (7/7) lên 30 (22/7), prefix nhảy theo đúng nhịp.
14/30 skill vượt trần 150 ký tự của CHÍNH dự án, dài nhất 1.018.

Ba việc test này phủ:
1. Mirror `.claude/skills` (bản Claude Code đọc native) cắt description về <= 150, canonical
   giữ nguyên chữ của người dùng. Không mất năng lực: description chỉ để định tuyến, router
   xưa nay đã cắt ở 150 rồi; thân skill vẫn nạp đủ khi được gọi.
2. Chỉ mục bộ nhớ có TRẦN, và hạ dần theo bậc - rút mô tả trước, bỏ dòng là bậc CUỐI.
3. CLAUDE.md không còn ôm mẫu file dài (đã dời vào skill javis-builder) nhưng GIỮ NGUYÊN
   mọi luật an toàn và luật hành vi.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401  - nạp server/ vào sys.path (xem tests/python/_paths.py)
import os
import re
import sys
import tempfile
from pathlib import Path

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-prefix-")

import yaml  # noqa: E402

import system_sync as ss  # noqa: E402
import skill_router       # noqa: E402

fails = []


def check(name, cond):
    print(("  OK   " if cond else "  FAIL ") + name)
    if not cond:
        fails.append(name)


def desc_of(text):
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    fm = yaml.safe_load(m.group(1)) if m else {}
    return (fm or {}).get("description") or ""


def body_of(text):
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    return text[m.end():] if m else text


CAP = skill_router.SKILL_DESC_MAX
check("tran lay tu skill_router (mot nguon chan ly)", CAP == 150)

# ---- 1. cắt description khi mirror ----
LONG = "Kich hoat khi nguoi dung muon " + ("lam viec gi do rat cu the va dai dong. " * 30)
cases = {
    "tran": f"---\nname: A\ndescription: {'x' * 400}\ngroup: G\n---\nTHAN A",
    "nhay kep": f'---\nname: B\ndescription: "{LONG}"\ngroup: G\n---\nTHAN B',
    "gap >-": "---\nname: C\ndescription: >-\n  " + ("dai " * 120) + "\n  het.\ngroup: G\n---\nTHAN C",
    "khoi |": "---\nname: D\ndescription: |\n  " + ("y" * 500) + "\ngroup: G\n---\nTHAN D",
}
for k, src in cases.items():
    out = ss._cap_desc(src, CAP)
    check(f"cat duoc kieu '{k}'", out is not None)
    if not out:
        continue
    check(f"  '{k}': description <= {CAP}", len(desc_of(out)) <= CAP)
    check(f"  '{k}': than skill NGUYEN VEN", body_of(out).strip() == body_of(src).strip())
    check(f"  '{k}': group con nguyen", desc_of(out) and yaml.safe_load(
        re.match(r"^---\n(.*?)\n---\n", out, re.S).group(1)).get("group") == "G")

check("mo ta ngan thi KHONG dung toi",
      ss._cap_desc("---\nname: E\ndescription: Ngan gon.\ngroup: G\n---\nT", CAP) is None)
check("khong co frontmatter -> khong dung toi", ss._cap_desc("chi co than", CAP) is None)

# mirror thật: canonical giữ nguyên, mirror bị cắt, thân file giống hệt
root = Path(tempfile.mkdtemp(prefix="javis-mirror-"))
sk = root / "skills" / "dai-dong"
sk.mkdir(parents=True)
src_text = f"---\nname: Dai dong\ndescription: {'z' * 900}\ngroup: Marketing\n---\n\n# Than skill\nnoi dung day du"
(sk / "SKILL.md").write_text(src_text, encoding="utf-8")
(sk / "references").mkdir()
(sk / "references" / "them.md").write_text("phu luc", encoding="utf-8")
ss.mirror_skills(root)
mir = root / ".claude" / "skills" / "dai-dong" / "SKILL.md"
check("mirror duoc tao", mir.is_file())
check("canonical GIU NGUYEN chu cua nguoi dung",
      len(desc_of((sk / "SKILL.md").read_text(encoding="utf-8"))) == 900)
check("mirror bi cat ve <= tran", len(desc_of(mir.read_text(encoding="utf-8"))) <= CAP)
check("mirror giu nguyen than skill",
      body_of(mir.read_text(encoding="utf-8")).strip() == body_of(src_text).strip())
check("file khac trong package van duoc chep",
      (root / ".claude" / "skills" / "dai-dong" / "references" / "them.md").is_file())

# ---- 2. trần cho chỉ mục bộ nhớ ----
import main  # noqa: E402

ITEM = "- [Ky uc so {i}](facts/ky-uc-{i}.md) - " + "mo ta rat dai de test tran chi muc " * 4
mem = "# Bộ nhớ - Index\n\n" + "\n".join(ITEM.format(i=i) for i in range(60))
n_all = sum(1 for l in mem.split("\n") if main._MEM_ITEM_RE.match(l))
check("dung 60 ky uc trong ban thu", n_all == 60)

check("duoi tran -> giu NGUYEN VAN", main._fit_memory_index(mem, len(mem) + 10) == mem)

for cap in (12000, 8000, 5000):
    got = main._fit_memory_index(mem, cap)
    kept = sum(1 for l in got.split("\n") if main._MEM_ITEM_RE.match(l))
    check(f"tran {cap}: khong vuot qua nhieu", len(got) <= cap + 400)
    check(f"tran {cap}: van giu DU {n_all} ky uc (chi rut mo ta)", kept == n_all)

tiny = main._fit_memory_index(mem, 1200)
kept = sum(1 for l in tiny.split("\n") if main._MEM_ITEM_RE.match(l))
check("tran cuc chat: buoc phai bo bot dong", kept < n_all)
check("bo dong thi PHAI noi ro con bao nhieu + duong doc tiep",
      "chưa liệt kê" in tiny and "Memory/MEMORY.md" in tiny)
check("rut mo ta thi chi duong sang facts/", "Memory/facts/" in main._fit_memory_index(mem, 8000))
check("tran doc duoc tu bien moi truong", "JAVIS_MEMORY_INDEX_MAX" in
      SERVER.joinpath("main.py").read_text(encoding="utf-8"))

# ---- 3. CLAUDE.md: gỡ mẫu file, GIỮ luật ----
md = ROOT.joinpath("CLAUDE.md").read_text(encoding="utf-8")
check("da go mau frontmatter loop", "type: loop\nname: <Tên hiển thị tiếng Việt>" not in md)
check("da go mau plugin.py", "def register(ctx):" not in md)
check("da go mau frontmatter agent/workflow", "type: workflow\nname: <Tên>" not in md)
check("co tro toi javis-builder", "javis-builder" in md)

for luat in ("mode: suggest", "enabled: false", "JAVIS_ENABLE_USER_PLUGINS",
             "AT MOST 150 characters", "NEVER leave `group` empty", "owner_chat",
             "notify: false",
             "em dash"):
    check(f"GIU luat: {luat}", luat in md)

bld = ROOT.joinpath(
    ".claude/skills/javis-builder/SKILL.md").read_text(encoding="utf-8")
for truong in ("type: loop", "type: agent", "type: workflow", "plugin.yaml",
               "quiet_hours", "max_runs_per_day", "ambient_mcp", "tools_profile",
               "notify: false", "owner_chat"):
    check(f"javis-builder co phu: {truong}", truong in bld)

print()
if fails:
    print(f"FAILED {len(fails)}: " + "; ".join(fails))
    sys.exit(1)
print("PASS - tat ca")
