"""Shared rendering preserves legacy output while full protected mode retains raw owner bytes.

The legacy oracle is frozen before extraction, not computed through the new renderer.
All production API dependencies point at disposable fixtures; no application startup.
"""
from _paths import ROOT, SERVER  # noqa: F401
import copy
import importlib.util
import os
import re
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

SCRATCH = Path(tempfile.mkdtemp(prefix="main-rendering-"))
for key, relative in {"JAVIS_STATE_DIR": "state", "BRAINS_DIR": "brains", "OBSIDIAN_VAULT_PATH": "vault",
                      "BRAIN_PATH": "brain", "SOURCES_PATH": "sources", "JAVIS_SESSIONS_DB": "sessions.sqlite3"}.items():
    os.environ[key] = str(SCRATCH / relative)

import main
import memory_control

if importlib.util.find_spec("main_prompt_rendering"):
    import main_prompt_rendering as R
else:
    R = None

# Frozen from pre-extraction ordinary production functions on 2026-10-23.
LEGACY_SOURCE = r'''
def _fit_memory_index(mem: str, cap: int = None) -> str:
    """Ép chỉ mục bộ nhớ xuống dưới trần mà KHÔNG làm mất ký ức nào cho tới phút chót.

    Hạ dần theo bậc: giữ nguyên -> rút mô tả còn 100 ký tự -> còn 60 -> chỉ còn tiêu đề+link
    -> (cùng lắm) cắt bớt dòng kèm lời chỉ đường. Rút mô tả KHÔNG mất năng lực nhớ: tiêu đề và
    đường dẫn file vẫn còn nguyên, chi tiết đầy đủ vẫn nằm trong memory/facts/*.md và đọc được
    bất cứ lúc nào. Mất hẳn dòng mới là mất trí nhớ, nên đó là bậc CUỐI.
    """
    cap = cap or MEMORY_INDEX_MAX
    if len(mem) <= cap:
        return mem
    lines = mem.split("\n")

    def rebuild(desc_cap):
        out = []
        for l in lines:
            m = _MEM_ITEM_RE.match(l)
            if not m:
                out.append(l)
                continue
            head, desc = m.group(1), m.group(2).strip()
            if not desc:
                out.append(head)
            elif desc_cap is None:
                out.append(head)
            elif len(desc) <= desc_cap:
                out.append(f"{head} - {desc}")
            else:
                out.append(f"{head} - {desc[:desc_cap].rstrip()}…")
        return "\n".join(out)

    for desc_cap in (100, 60, None):
        got = rebuild(desc_cap)
        if len(got) <= cap:
            note = ("\n\n> (Mô tả trong chỉ mục đã rút gọn cho vừa ngữ cảnh. Chi tiết đầy đủ của "
                    "từng ký ức nằm trong file tương ứng ở memory/facts/ - cứ đọc khi cần.)")
            return got + note

    # Bậc cuối: buộc phải bỏ bớt dòng. Giữ các dòng ĐẦU (ký ức nền tảng ghi sớm nhất) và nói rõ
    # còn bao nhiêu, kèm đường đọc tiếp - đừng để mất im lặng.
    # 0.222.0: also NAME the hidden memories (file names only, within a small budget). A model
    # cannot look up a memory it does not know exists: with only a count, "who is Lan?" got "I do
    # not know" while facts/lan-em-gai.md sat on disk unread.
    hidden_budget = min(1200, cap // 5)
    kept, total = [], 0
    items = 0
    rebuilt = rebuild(None).split("\n")
    for l in rebuilt:
        if total + len(l) + 1 > cap - 300 - hidden_budget:
            break
        kept.append(l)
        total += len(l) + 1
        if _MEM_ITEM_RE.match(l):
            items += 1
    con_lai = sum(1 for l in lines if _MEM_ITEM_RE.match(l)) - items
    names = []
    used = 0
    for l in rebuilt[len(kept):]:
        m = _MEM_ITEM_RE.match(l)
        link = re.search(r"\]\(([^)]*)\)", m.group(1)) if m else None
        if not link:
            continue
        slug = Path(link.group(1).strip()).stem
        if not slug:
            continue
        if used + len(slug) + 2 > hidden_budget:
            names.append("…")
            break
        names.append(slug)
        used += len(slug) + 2
    ten = (f" Tên file của chúng: {', '.join(names)}. Cần ký ức nào thì đọc memory/facts/<tên>.md."
           if names else "")
    return "\n".join(kept) + (
        f"\n\n> (Chỉ mục quá dài nên còn {con_lai} ký ức chưa liệt kê ở đây.{ten} "
        "Đọc memory/MEMORY.md để xem đủ danh sách, và memory/facts/ để xem chi tiết.)")

def build_system_prompt(brain: str = "brain", include_memory: bool = True,
                        include_skills: bool = True,
                        lang: "lang_mod.LangDecision | str | None" = None,
                        project_id: str = "", session_id: str = "") -> str:
    """CLAUDE.md + nạp MEMORY.md của vault đang chọn → Javis luôn nhớ ngữ cảnh.

    `project_id`: hội thoại đang nằm trong project nào. Có thì ghép thêm hướng dẫn riêng +
    danh sách tài liệu của project đó (xem `_project_block`).
    `session_id`: cuộc trò chuyện đang chạy. Có thì ghép thêm tài liệu & link người dùng tự
    gắn vào ĐÚNG cuộc đó (xem `_session_block`)."""
    base = CLAUDE_MD_PATH.read_text(encoding="utf-8") if CLAUDE_MD_PATH.exists() else ""
    # Chốt ngôn ngữ NGAY đầu hàm: khối NGÔN NGỮ ở cuối cần nó, mà danh sách skill ở giữa cũng
    # cần (mô tả skill là bề mặt ĐỐI CHIẾU với câu người dùng vừa gõ, nên nó phải cùng thứ
    # tiếng với câu đó thì định tuyến mới sắc).
    _lq = lang if isinstance(lang, lang_mod.LangDecision) else None
    _lma = (_lq.lang if _lq else lang_registry.chuan_hoa(lang or "")) or lang_registry.MAC_DINH
    idx = _brain_memory_dir(brain) / "MEMORY.md"
    mem = ""
    try:
        if idx.exists():
            mem = idx.read_text(encoding="utf-8")
    except Exception:
        mem = ""
    # 0.188.0: the person's own profile (every brain) BEFORE the brain's memory, which wins where they differ.
    # #1349 (the one deliberate change to this oracle since extraction): the profile no longer hangs on
    # `include_memory`, so it reaches the model at the token-saving levels too.
    base += memory_control.profile_block()
    if include_memory and mem.strip():
        base += "\n\n# === BỘ NHỚ DÀI HẠN (nạp sẵn) ===\n" + _fit_memory_index(mem)
    if not memory_control.learning_enabled(_brain_memory_dir(brain)):
        base += memory_control.LEARNING_OFF_NOTE
    # Ngay sau bộ nhớ, TRƯỚC lớp agentic: hướng dẫn project là luật hành xử, phải đứng cùng
    # khu với CLAUDE.md và MEMORY.md chứ không lẫn vào khối đường dẫn kỹ thuật bên dưới.
    if project_id:
        try:
            base += _project_block(project_id)
        except Exception:
            pass
    # Ngay sau khối project, vì cùng loại: project là tài liệu của cả NHÓM, cái này là tài
    # liệu của riêng CUỘC đang chạy - hẹp hơn nên đứng sau, gần câu hỏi hơn.
    if session_id:
        try:
            base += _session_block(session_id)
        except Exception:
            pass
        base += _javis_core_block(session_id)
    # Đường dẫn lớp Agentic của vault đang làm việc (để Javis tạo agent/workflow/loop qua chat)
    root = _brain_root(brain)
    system_sync.ensure_synced(root)   # brain nào cũng có đủ năng lực hệ thống (1 lần/process, rẻ)
    try:
        # Mirror skills/ → .claude/skills để fork Claude cwd=brain (workflow/loop/learn/lint) nạp
        # native được skill viết giữa phiên (rẻ: cổng chữ ký stat-only bỏ qua nếu cây nguồn
        # không đổi, xem system_sync._mirror_signature - KHÔNG còn so hash nội dung nữa).
        #
        # KHÔNG gắn với include_skills. Cờ đó chỉ nói "có chèn khối ROUTER SKILL vào prompt hay
        # không" - một chuyện về CHỮ. Còn mirror là một tác dụng phụ lên ĐĨA mà Claude Code và
        # Codex dựa vào để tự tìm skill. Gộp hai chuyện làm một thì bật tiết kiệm token cho
        # Claude Code là vô hiệu hoá luôn skill native của nó, mà lỗi đó im lặng hoàn toàn.
        system_sync.mirror_skills(root)
    except Exception:
        pass
    ag, wf = _agents_dir(brain), _workflows_dir(brain)
    lp = Path(root) / "Javis" / "loops"
    sk = _skills_dir(brain)
    base += (
        "\n\n# === LỚP AGENTIC (vault đang làm việc) ===\n"
        f"Vault root: {root}\n"
        f"- AGENT: tạo/sửa tại `{ag}/<slug>.md`\n"
        f"- WORKFLOW: tạo/sửa tại `{wf}/<slug>.md`\n"
        f"- LOOP (nhiệm vụ lặp vô hạn): tạo/sửa tại `{lp}/<slug>.md`\n"
        f"- SKILL: tạo/sửa tại `{sk}/<slug>/SKILL.md` (tự mirror sang .claude/skills cho Claude native)\n"
        f"- FILE KHÁC (bài viết, báo cáo, nháp, dữ liệu): ghi VÀO TRONG vault root ở trên bằng đường "
        f"dẫn TUYỆT ĐỐI `{root}/<thư mục>/<tên file>`. TUYỆT ĐỐI không ghi tương đối theo thư mục "
        "làm việc và không ghi ra ngoài vault: file ngoài vault không hiện ở trang Tệp tin và mất "
        "khi cập nhật. Trong câu trả lời, dẫn link bằng đường dẫn TƯƠNG ĐỐI so với vault root "
        "(vd `bai-viet/bai-1.txt`), KHÔNG dùng giao thức `file://` và không mã hoá %20 dù harness "
        "có dặn khác (khung chat và Telegram mở không được), và CHỈ dẫn link tới file đã ghi xong "
        "thật. Khi đếm hay liệt kê "
        "file (vd \"còn bao nhiêu bài chưa xong\"), liệt kê lại thư mục bằng tool ngay lúc đó, "
        "đừng nhớ lại từ lượt trước.\n"
        "Khi user yêu cầu tạo/sửa agent, workflow hoặc loop qua chat, ghi file .md đúng định dạng "
        "(xem mục 'Tạo/sửa Agent & Workflow qua chat' và 'Điều phối' trong system prompt) bằng "
        "ĐƯỜNG DẪN TUYỆT ĐỐI ở trên. Trang Agents/Workflows/Việc định kỳ sẽ tự nhận file mới."
    )
    # Resonance (M2): chỉ brain đã bật mới có dòng này và mới thấy tool javis_goal. CLAUDE.md đã hết ngân sách
    # ký tự, và brain chưa bật thì không được dài thêm chữ nào.
    # Đường tìm tool khác nhau theo engine. Khi engine Claude dựng được server plugin in-process
    # "javis-plugins", hub bị báo bỏ nhóm plugin (X-Javis-No-Plugins), nên javis_search_tools của hub không
    # trả về javis_goal; tool đến model qua namespace mcp__javis-plugins__. Claude Code có hoãn nạp nó sau
    # ToolSearch hay không thì chưa xác minh (lần chạy 1 cho thấy javis_task từng bị hoãn như vậy), nên dòng
    # dưới chỉ nói "chưa nạp thì tìm". Dòng cũ chỉ nêu javis_search_tools (pilot lần 2, 07/10/2026).
    # Ranh giới bốn loại việc chỉ nằm ở dòng này và mô tả javis_goal: cả hai chỉ có trong lượt của agent đã bật.
    # Mô tả javis_task giữ nguyên để brain tắt tính năng không nhận chỉ dẫn mới (review PR #579, P2).
    # A1: theo agent của LƯỢT (ngữ cảnh lượt do host gắn), không theo công tắc brain cũ; chat thường không có dòng này.
    if _resonance_turn_enabled(root):
        base += "\n- " + _RESONANCE_GOAL_HINT
    # Quét cây skill MỘT lần cho cả hai khối dưới. Trước đây _javis_capability_summary
    # gọi list_skills còn _skill_router_block gọi list_enabled_meta (vốn chỉ là list_skills
    # lọc lại), nên cả cây skill bị đi và parse YAML HAI lần mỗi lượt chat - đo được 18ms
    # mỗi lần trên brain 30 skill. Lỗi thì để None và mỗi khối tự quét như cũ.
    # Quét LUÔN, kể cả khi bỏ khối router. Khối "NĂNG LỰC JAVIS HIỆN CÓ" chỉ ĐẾM skill và
    # liệt kê tên nhóm (vài chục ký tự), nên nó không phải chỗ tốn token; nhưng đưa cho nó một
    # danh sách rỗng thì Javis sẽ tự khai là mình không có skill nào - một câu SAI, và sai theo
    # hướng khiến nó đi tạo lại thứ đã có.
    try:
        _skills = skill_router.list_skills(root, _lma)
    except Exception:
        _skills = None
    try:
        base += _javis_capability_summary(brain, _skills)   # chỉ mục năng lực LIVE (mọi engine biết Javis có gì)
    except Exception:
        pass
    try:
        if include_skills:
            base += _skill_router_block(brain, root, _skills)   # ROUTER SKILL đa-engine: list skill + cách gọi
    except Exception:
        pass
    # Đồng hồ. Cùng một dòng với capsule của đường tiết kiệm (context_compiler.dong_ho), để
    # bật hay tắt tiết kiệm thì Javis vẫn biết bây giờ mấy giờ y như nhau. Model không có
    # đồng hồ, và tool `javis_now` thì không phải đường nào cũng phát tool.
    # Khối NGÔN NGỮ + đồng hồ đi CÙNG NHAU và đi CUỐI, sát chỗ model bắt đầu trả lời.
    # Ngôn ngữ đặt ở cuối vì luật càng gần chỗ sinh chữ thì model càng ít trôi; đồng hồ
    # đi kèm vì tên thứ trong tuần cũng phải theo ngôn ngữ đó.
    base += "\n\n# === BÂY GIỜ ===\n" + context_compiler.dong_ho(lang=_lma)
    base += lang_mod.khoi_ngon_ngu(_lq or lang_mod.LangDecision(_lma, "default", 1.0, True))
    try:
        # 1 dòng MỨC DÙNG để Javis TRẢ LỜI được khi user hỏi "token tiêu bao nhiêu" (chi tiết ở panel).
        _t = usage_store.summary().get("today", {}).get("total", {})
        if _t.get("in") or _t.get("out"):
            _c = f", ~${_t.get('cost', 0):.4f}" if _t.get("cost") else ""
            base += (f"\n\n# === MỨC DÙNG HÔM NAY (Javis tự đo) ===\n"
                     f"{_t.get('in', 0):,} token vào + {_t.get('out', 0):,} token ra qua "
                     f"{_t.get('turns', 0)} lượt{_c}. Đây là token Javis TỰ ĐO, KHÔNG phải hạn mức gói "
                     f"thuê bao (đa số nhà cung cấp không cho lấy hạn mức tài khoản qua API). Chi tiết "
                     f"từng nhà cung cấp ở panel 'Mức dùng' trên dashboard.")
    except Exception:
        pass
    return base

def _javis_capability_summary(brain: str, skills=None) -> str:
    """Bản LIVE gọn (capped) chèn vào system prompt: để engine nào cũng biết Javis có gì.
    Skill nhiều -> chỉ đếm + nhóm (chi tiết ở Javis/index.md), tránh phình context.
    skills: cây skill đã quét sẵn, xem _gather_capabilities."""
    try:
        c = _gather_capabilities(brain, skills)
    except Exception:
        return ""
    if not any(c.values()):
        return ""
    parts = ["\n\n# === NĂNG LỰC JAVIS HIỆN CÓ (đọc `Javis/index.md` để biết chi tiết + trigger) ==="]
    if c["agents"]:
        parts.append("Agents: " + ", ".join(a["name"] for a in c["agents"][:30]))
    if c["skills"]:
        groups = sorted({s["group"] for s in c["skills"] if s["enabled"]})
        parts.append(f"Skills: {sum(1 for s in c['skills'] if s['enabled'])} kỹ năng (nhóm: {', '.join(groups[:12])})")
    if c["workflows"]:
        parts.append("Workflows: " + ", ".join(w["name"] for w in c["workflows"][:20] if w["status"] == "active"))
    _lc = _dong_lan_chay_gan_nhat(brain)
    if _lc:
        parts.append(_lc)
    if c["loops"]:
        parts.append("Loops: " + ", ".join(f"{l['name']}({'bật' if l['enabled'] else 'tắt'})" for l in c["loops"][:20]))
    live_plugins = [p for p in c.get("plugins", []) if p.get("loaded")]
    if live_plugins:
        tool_names = [t for p in live_plugins for t in p.get("tools", [])]
        parts.append("Plugins đang chạy: " + ", ".join(p["name"] for p in live_plugins[:12])
                     + (f" (tool: {', '.join(tool_names[:12])})" if tool_names else ""))
    parts.append("Trước khi tạo năng lực mới, kiểm chỉ mục này để khỏi trùng.")
    return "\n".join(parts)

def _skill_router_block(brain: str, root: str, skills=None) -> str:
    """ROUTER SKILL đa-engine (chèn vào system prompt của MỌI engine). Liệt kê skill đang BẬT kèm
    mô tả (trigger) + chỉ rõ 2 cách nạp: tool javis_use_skill (engine API có tool) HOẶC mở thẳng
    file SKILL.md bằng công cụ đọc file (Claude/Codex - dùng ĐƯỜNG DẪN TUYỆT ĐỐI vì cwd có thể là
    /app). Đây là thứ giúp skill chạy trên cả ChatGPT/Codex, không phụ thuộc cơ chế native của Claude.
    Cắt theo CẢ số mục lẫn ngân sách ký tự (skill_router.cat_theo_ngan_sach), và xếp theo mức
    hay dùng trước khi cắt (skill_router.xep_theo_uu_tien) - nếu không thì việc cắt rơi vào
    thứ tự bảng chữ cái và một skill quan trọng biến mất khỏi router chỉ vì tên nó vần cuối.
    skills: cây skill đã quét sẵn (list_skills), lọc tại chỗ thay vì quét lại - xem
    _gather_capabilities. None = tự quét (đường cũ)."""
    metas = ([s for s in skills if s.get("enabled")] if skills is not None
             else skill_router.list_enabled_meta(root))
    if not metas:
        return ""
    sk_dir = skill_router.skills_base(root, canonical=True)
    lines = ["\n\n# === SKILL KHẢ DỤNG (router - dùng được trên MỌI engine) ==="]
    hien, con_lai = skill_router.cat_theo_ngan_sach(
        skill_router.xep_theo_uu_tien(metas, root))
    for s in hien:
        desc = (s.get("description") or "").replace("\n", " ")[:skill_router.SKILL_DESC_MAX]
        lines.append(f"- {s['slug']} ({s['name']}): {desc}")
    if con_lai > 0:
        # Nói rõ CÁCH LẤY chứ không chỉ nói còn bao nhiêu: `javis_use_skill` nạp được theo
        # slug kể cả skill không nằm trong danh sách trên, nên một skill bị cắt vẫn dùng được
        # nếu model biết tên. Câu cũ chỉ trỏ sang một file mà model không đọc.
        lines.append(f"…(+{con_lai} skill nữa chưa liệt kê ở đây - xem đủ danh sách trong "
                     f"`Javis/index.md`, và nạp thẳng bằng `javis_use_skill(name=<slug>)` "
                     f"nếu đã biết tên)")
    lines.append(
        "CÁCH DÙNG: khi yêu cầu của user KHỚP mô tả 1 skill ở trên, hãy NẠP skill đó rồi LÀM THEO - "
        "gọi tool `javis_use_skill(name=<slug>)` nếu engine có tool này; nếu không, mở file "
        f"`{sk_dir}/<slug>/SKILL.md` bằng công cụ đọc file rồi tuân theo hướng dẫn trong đó. "
        "Chỉ nạp khi thực sự khớp, không nạp tràn lan."
    )
    return "\n".join(lines)
'''
PROFILE_HEADER = ("\n\n# === HỒ SƠ NGƯỜI DÙNG (chung mọi brain, do người dùng tự viết) ===\n"
                  "Cách xưng hô, ngôn ngữ, cách trình bày và mức chi tiết người dùng muốn. Bộ nhớ riêng của brain bên dưới "
                  "thắng khi hai bên khác nhau.\n")
MEMORY_HEADER = "\n\n# === BỘ NHỚ DÀI HẠN (nạp sẵn) ===\n"


class MainRenderingTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(R, "The shared pure main renderer is not implemented")
        self.brain = Path(tempfile.mkdtemp(prefix="brain-", dir=SCRATCH))
        self.memory = self.brain / "memory"
        self.memory.mkdir()
        self.kernel = self.brain / "kernel.md"
        self.kernel.write_text("KERNEL: owner scope wins.\n", encoding="utf-8")
        self.memory_text = "- [Rule](facts/rule.md) - Owner rule.\n"
        (self.memory / "MEMORY.md").write_text(self.memory_text, encoding="utf-8")
        memory_control._profile_path().write_text("  Use anh/em.\n", encoding="utf-8")
        self.skills = [{"slug": "mail", "name": "Email", "description": "Write\nemail", "group": "Writing", "enabled": True},
                       {"slug": "disabled", "name": "Disabled", "description": "Hidden", "group": "Other", "enabled": False}]
        self.caps = {"agents": [{"name": "Editor"}], "skills": copy.deepcopy(self.skills),
                     "workflows": [{"name": "Review", "status": "active"}],
                     "loops": [{"name": "Daily", "enabled": False}],
                     "plugins": [{"name": "Clock", "loaded": True, "tools": ["javis_now"]}]}

    def fixture(self, *, caps=None, resonance=False, usage=None):
        stack = ExitStack()
        aliases = {"CLAUDE_MD_PATH": self.kernel, "_brain_memory_dir": lambda brain: self.memory,
                   "_brain_root": lambda brain: str(self.brain),
                   "_agents_dir": lambda brain: self.brain / "agents",
                   "_workflows_dir": lambda brain: self.brain / "workflows",
                   "_skills_dir": lambda brain: self.brain / "skills",
                   "_resonance_turn_enabled": lambda brain: resonance,
                   "_gather_capabilities": lambda brain, skills=None: copy.deepcopy(self.caps if caps is None else caps),
                   "_dong_lan_chay_gan_nhat": lambda brain: "Latest run: Review.",
                   "_project_block": lambda project_id: "\n<PROJECT RULES>",
                   "_session_block": lambda session_id: "\n<SESSION ASSET REFERENCES>",
                   "_javis_core_block": lambda session_id: "\n<CORE ROLE>"}
        for name, value in aliases.items():
            stack.enter_context(patch.object(main, name, value))
        stack.enter_context(patch.object(main.system_sync, "ensure_synced", lambda root: None))
        stack.enter_context(patch.object(main.system_sync, "mirror_skills", lambda root: None))
        stack.enter_context(patch.object(main.skill_router, "list_skills", lambda root, lang="": copy.deepcopy(self.skills)))
        stack.enter_context(patch.object(main.context_compiler, "dong_ho", lambda lang="": "10:15, fixed clock"))
        total = {"in": 1234, "out": 67, "turns": 3, "cost": 0.25} if usage is None else usage
        stack.enter_context(patch.object(main.usage_store, "summary", lambda: {"today": {"total": total}}))
        stack.enter_context(patch.object(memory_control, "learning_enabled", lambda path: False))
        self.addCleanup(stack.close)
        return stack

    @staticmethod
    def legacy_namespace():
        namespace = dict(vars(main))
        namespace["_MEM_ITEM_RE"] = re.compile(r'^(\s*-\s*\[[^\]]*\]\([^)]*\))\s*[-–—]?\s*(.*)$')
        exec(compile(LEGACY_SOURCE, "<frozen-pre-extraction-main>", "exec"), namespace)
        return namespace

    def test_actual_production_main_matches_frozen_legacy_for_all_include_flags(self):
        self.fixture()
        old = self.legacy_namespace()["build_system_prompt"]
        for memory in (False, True):
            for skills in (False, True):
                for language in ("vi", "en", main.lang_mod.LangDecision("en", "setting", 1.0, True)):
                    with self.subTest(memory=memory, skills=skills, language=language):
                        args = dict(include_memory=memory, include_skills=skills, lang=language,
                                    project_id="project-1", session_id="session-1")
                        self.assertEqual(main.build_system_prompt(str(self.brain), **args), old(str(self.brain), **args))

    def test_actual_production_preserves_block_precedence_and_learning_off_with_memory_disabled(self):
        self.fixture(resonance=True)
        prompt = main.build_system_prompt(str(self.brain), project_id="project-1", session_id="session-1")
        blocks = ["KERNEL:", "HỒ SƠ NGƯỜI DÙNG", "BỘ NHỚ DÀI HẠN", "GHI NHỚ MỚI ĐANG TẮT", "<PROJECT RULES>",
                  "<SESSION ASSET REFERENCES>", "<CORE ROLE>", "LỚP AGENTIC", main._RESONANCE_GOAL_HINT,
                  "NĂNG LỰC JAVIS HIỆN CÓ", "SKILL KHẢ DỤNG", "BÂY GIỜ", "NGÔN NGỮ", "MỨC DÙNG HÔM NAY"]
        self.assertEqual([prompt.index(block) for block in blocks], sorted(prompt.index(block) for block in blocks))
        without_memory = main.build_system_prompt(str(self.brain), include_memory=False)
        # #1349: the profile is a behaviour contract and stays; only the brain's memory index is left out.
        self.assertIn("Use anh/em", without_memory)
        self.assertLess(without_memory.index("HỒ SƠ NGƯỜI DÙNG"), without_memory.index("GHI NHỚ MỚI ĐANG TẮT"))
        self.assertNotIn("Owner rule.", without_memory)
        self.assertIn("GHI NHỚ MỚI ĐANG TẮT", without_memory)

    def test_profile_default_matches_real_profile_api_and_cap(self):
        raw = " \r\n" + "Owner preference. " * 500 + "TAIL\r\n "
        with patch.object(memory_control, "read_profile", return_value=raw.strip()[:memory_control.PROFILE_MAX]):
            self.assertEqual(R.render_profile_block(raw), memory_control.profile_block())
        self.assertEqual(R.render_profile_block("  Rule.\n", profile_max=4), PROFILE_HEADER + "Rule")
        self.assertEqual(R.render_profile_block("\r\n \t"), "")

    def test_full_protected_profile_keeps_leading_crlf_and_tail(self):
        raw = " \r\n" + "Owner preference. " * 500 + "TAIL\r\n "
        full = R.render_profile_block(raw, preserve_full_protected=True)
        self.assertEqual(full, PROFILE_HEADER + raw)
        self.assertNotIn("TAIL", R.render_profile_block(raw))
        self.assertEqual(R.render_profile_block("Rule"), R.render_profile_block("Rule", preserve_full_protected=True))

    def test_production_profile_does_not_strip_a_second_time_after_its_cap(self):
        raw = "X" * (memory_control.PROFILE_MAX - 1) + " " + "beyond cap"
        memory_control._profile_path().write_text(raw, encoding="utf-8")
        self.assertEqual(memory_control.profile_block(), PROFILE_HEADER + raw[:memory_control.PROFILE_MAX])

    def test_full_protected_mode_preserves_even_whitespace_only_source_bytes(self):
        raw = " \r\n\t"
        self.assertEqual(R.render_profile_block(raw, preserve_full_protected=True), PROFILE_HEADER + raw)
        self.assertEqual(R.render_memory_block(raw, memory_cap=1, preserve_full_protected=True), MEMORY_HEADER + raw)
        self.assertEqual(R.render_project_instructions("P", raw, instructions_max=1, preserve_full_protected=True),
                         "\n\n# === HƯỚNG DẪN RIÊNG CỦA PROJECT: P ===\n" + raw)

    def test_memory_default_retains_each_legacy_compaction_stage(self):
        self.fixture()
        old_fit = self.legacy_namespace()["_fit_memory_index"]
        text = "# Memory\n" + "\n".join(f"- [Owner {i}](facts/owner-{i}.md) - " + "long detail " * 30 for i in range(90))
        for cap in (100000, 18000, 10000, 5000, 1200):
            with self.subTest(cap=cap):
                self.assertEqual(R.fit_memory_index(text, cap), old_fit(text, cap))
                self.assertEqual(R.render_memory_block(text, memory_cap=cap), MEMORY_HEADER + old_fit(text, cap))
        self.assertEqual(R.render_memory_block(" \r\n", memory_cap=1), "")

    def test_full_protected_memory_never_drops_last_owner_rule(self):
        raw = "\r\n" + "\r\n".join(f"- [Rule {i}](facts/rule-{i}.md) - " + "long detail " * 30 for i in range(90)) + "\r\nTAIL OWNER RULE\r\n"
        self.assertEqual(R.render_memory_block(raw, memory_cap=100, preserve_full_protected=True), MEMORY_HEADER + raw)
        self.assertNotIn("TAIL OWNER RULE", R.render_memory_block(raw, memory_cap=100))
        self.assertEqual(R.render_memory_block("Rule", memory_cap=100),
                         R.render_memory_block("Rule", memory_cap=100, preserve_full_protected=True))

    def test_actual_production_over_cap_profile_and_memory_remain_legacy_capped(self):
        self.fixture()
        memory_control._profile_path().write_text("PROFILE-" * 900 + "PROFILE TAIL", encoding="utf-8")
        text = "\n".join(f"- [Owner {i}](facts/owner-{i}.md) - " + "details " * 100 for i in range(100))
        (self.memory / "MEMORY.md").write_text(text, encoding="utf-8")
        with patch.object(main, "MEMORY_INDEX_MAX", 1000):
            old = self.legacy_namespace()["build_system_prompt"]
            actual = main.build_system_prompt(str(self.brain))
            self.assertEqual(actual, old(str(self.brain)))
        self.assertNotIn("PROFILE TAIL", actual)
        self.assertIn("Chỉ mục quá dài", actual)

    def test_project_instructions_default_and_full_protected_preserve_contract(self):
        raw = " \r\n" + "Project rule. " * 500 + "TAIL\r\n "
        header = "\n\n# === HƯỚNG DẪN RIÊNG CỦA PROJECT: Owner Project ===\n"
        self.assertEqual(R.render_project_instructions("Owner Project", raw, instructions_max=100), header + raw.strip()[:100])
        self.assertEqual(R.render_project_instructions("Owner Project", raw, instructions_max=100, preserve_full_protected=True), header + raw)
        self.assertEqual(R.render_project_instructions("Owner Project", " \r\n", instructions_max=100), "")
        self.assertEqual(R.render_project_instructions("Owner Project", "Rule", instructions_max=100),
                         R.render_project_instructions("Owner Project", "Rule", instructions_max=100, preserve_full_protected=True))

    def test_real_project_collector_uses_shared_instructions_without_altering_caps(self):
        raw = " Project instruction. " * 500
        class Store:
            def get_project_full(self, identifier):
                return {"name": "Owner Project", "instructions": raw, "files": [], "links": []}
        with patch.object(main, "get_store", return_value=Store()):
            self.assertEqual(main._project_block("project-1"),
                             R.render_project_instructions("Owner Project", raw, instructions_max=main.sessions.PROJECT_INSTRUCTIONS_MAX))

    def test_capability_summary_keeps_existing_caps_and_loaded_plugin_filter(self):
        self.fixture()
        caps = {"agents": [{"name": f"Agent-{i}"} for i in range(35)],
                "skills": [{"group": f"Group-{i:02}", "enabled": i % 2 == 0} for i in range(30)],
                "workflows": [{"name": f"Workflow-{i}", "status": "active" if i % 2 else "draft"} for i in range(25)],
                "loops": [{"name": f"Loop-{i}", "enabled": bool(i % 2)} for i in range(24)],
                "plugins": [{"name": f"Plugin-{i}", "loaded": i % 2 == 0, "tools": [f"tool-{i}"]} for i in range(30)]}
        old = self.legacy_namespace()["_javis_capability_summary"]
        with patch.object(main, "_gather_capabilities", return_value=caps):
            old.__globals__["_gather_capabilities"] = main._gather_capabilities
            expected = old(str(self.brain))
        result = R.render_capability_summary(caps, "Latest run: Review.")
        self.assertEqual(result, expected)
        self.assertIn("Agent-29", result)
        self.assertNotIn("Agent-30", result)
        self.assertNotIn("Plugin-1,", result)
        self.assertEqual(R.render_capability_summary({key: [] for key in caps}, "Latest run"), "")

    def test_skill_router_preserves_budget_order_description_normalization_and_hidden_count(self):
        self.fixture()
        metas = [{"slug": "preferred", "name": "Preferred", "description": "First\nsecond"},
                 {"slug": "last", "name": "Last", "description": "X" * 200}]
        before = copy.deepcopy(metas)
        actual = R.render_skill_router(metas, skills_dir="/captured/skills", hidden_count=3, description_max=10)
        self.assertIn("- preferred (Preferred): First seco", actual)
        self.assertIn("- last (Last): XXXXXXXXXX", actual)
        self.assertIn("…(+3 skill nữa", actual)
        self.assertIn("`/captured/skills/<slug>/SKILL.md`", actual)
        self.assertLess(actual.index("- preferred"), actual.index("- last"))
        self.assertEqual(metas, before)
        self.assertEqual(R.render_skill_router([], skills_dir="/skills"), "")

    def test_actual_production_skill_budget_selection_remains_outside_renderer(self):
        self.fixture()
        self.skills = [{"slug": f"skill-{i:02}", "name": f"Skill {i}", "description": "Do work", "enabled": True} for i in range(8)]
        (self.brain / "Javis").mkdir()
        (self.brain / "Javis" / "skill-usage.json").write_text('{"skill-07":{"pinned":true}}', encoding="utf-8")
        with patch.object(main.skill_router, "SKILL_LIST_MAX", 2):
            old = self.legacy_namespace()["_skill_router_block"]
            actual = main._skill_router_block(str(self.brain), str(self.brain), self.skills)
            self.assertEqual(actual, old(str(self.brain), str(self.brain), self.skills))
        self.assertIn("- skill-07", actual)
        self.assertNotIn("- skill-02", actual)
        self.assertIn("…(+6 skill nữa", actual)

    def test_router_retains_discovery_instructions_when_all_known_skills_are_hidden(self):
        self.fixture()
        with patch.object(main.skill_router, "SKILL_LIST_MAX", 0):
            old = self.legacy_namespace()["_skill_router_block"]
            actual = main._skill_router_block(str(self.brain), str(self.brain), self.skills)
            self.assertEqual(actual, old(str(self.brain), str(self.brain), self.skills))
        self.assertIn("…(+1 skill nữa", actual)
        self.assertIn("CÁCH DÙNG", actual)

    def test_clock_language_usage_preserve_order_and_cost_conditions(self):
        self.assertEqual(R.render_clock_language("FIXED CLOCK", "\nLANGUAGE"), "\n\n# === BÂY GIỜ ===\nFIXED CLOCK\nLANGUAGE")
        self.assertEqual(R.render_usage_block({}), "")
        self.assertEqual(R.render_usage_block({"in": 0, "out": 0, "turns": 2, "cost": 3.0}), "")
        expected = ("\n\n# === MỨC DÙNG HÔM NAY (Javis tự đo) ===\n"
                    "1,234 token vào + 5 token ra qua 2 lượt, ~$0.1200. Đây là token Javis TỰ ĐO, KHÔNG phải hạn mức gói "
                    "thuê bao (đa số nhà cung cấp không cho lấy hạn mức tài khoản qua API). Chi tiết "
                    "từng nhà cung cấp ở panel 'Mức dùng' trên dashboard.")
        self.assertEqual(R.render_usage_block({"in": 1234, "out": 5, "turns": 2, "cost": 0.12}), expected)
        self.assertNotIn("~$", R.render_usage_block({"out": 1, "cost": 0}))
        self.assertNotIn("~$", R.render_usage_block({"in": 1, "cost": None}))

    def test_renderers_do_not_read_files_call_sources_or_mutate_inputs(self):
        before = copy.deepcopy(self.caps)
        with patch("builtins.open", side_effect=AssertionError("renderer attempted IO")), \
                patch.object(Path, "open", side_effect=AssertionError("renderer attempted IO")), \
                patch.object(os, "open", side_effect=AssertionError("renderer attempted IO")):
            R.render_profile_block("Rule")
            R.render_memory_block("Memory", memory_cap=100)
            R.render_project_instructions("Project", "Rule", instructions_max=100)
            paths = R.render_agentic_paths("/brain", "/brain/agents", "/brain/workflows", "/brain/Javis/loops", "/brain/skills")
            R.render_capability_summary(self.caps)
            R.render_skill_router([], skills_dir="/brain/skills")
            R.render_clock_language("clock", "language")
            R.render_usage_block({"in": 1})
        self.assertEqual(self.caps, before)
        self.assertIn("Vault root: /brain", paths)
        self.assertIn("`/brain/workflows/<slug>.md`", paths)
        self.assertIn("`/brain/skills/<slug>/SKILL.md`", paths)


if __name__ == "__main__":
    unittest.main()
