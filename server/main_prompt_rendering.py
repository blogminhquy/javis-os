"""Pure shared rendering for ordinary main prompt blocks.

Callers own reads, authorization, completeness, ordering and volatile snapshots. The
legacy defaults retain production caps. Full-protected mode preserves raw profile,
memory and project instruction text; it does not claim a complete production surface.
No callable, runtime discovery, settings, filesystem read or context guard lives here.
"""
from __future__ import annotations

import re
from pathlib import Path

_MEM_ITEM_RE = re.compile(r'^(\s*-\s*\[[^\]]*\]\([^)]*\))\s*[-–—]?\s*(.*)$')


def render_profile_block(text: str, *, profile_max: int = 4000, preserve_full_protected: bool = False) -> str:
    """Owner profile comes before brain memory, which wins in a disagreement."""
    content = text if preserve_full_protected else text.strip()[:profile_max]
    return ("\n\n# === HỒ SƠ NGƯỜI DÙNG (user profile: every brain, written by the user) ===\n"
            "How the user wants to be addressed, and the language, layout and level of detail they want. The brain's own "
            "memory below wins where the two differ.\n" + content) if content else ""


def render_project_instructions(name: str, text: str, *, instructions_max: int,
                                preserve_full_protected: bool = False) -> str:
    """Render only protected instructions, never source documents or fixture contents."""
    if not (text if preserve_full_protected else text.strip()):
        return ""
    content = text if preserve_full_protected else text.strip()[:instructions_max]
    return f"\n\n# === HƯỚNG DẪN RIÊNG CỦA PROJECT: {name} ===\n" + content


def fit_memory_index(mem: str, cap: int) -> str:
    """Ép chỉ mục bộ nhớ xuống dưới trần mà KHÔNG làm mất ký ức nào cho tới phút chót.

    Hạ dần theo bậc: giữ nguyên -> rút mô tả còn 100 ký tự -> còn 60 -> chỉ còn tiêu đề+link
    -> (cùng lắm) cắt bớt dòng kèm lời chỉ đường. Rút mô tả KHÔNG mất năng lực nhớ: tiêu đề và
    đường dẫn file vẫn còn nguyên, chi tiết đầy đủ vẫn nằm trong memory/facts/*.md và đọc được
    bất cứ lúc nào. Mất hẳn dòng mới là mất trí nhớ, nên đó là bậc CUỐI.
    """
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
            note = ("\n\n> (Descriptions in this index were shortened to fit the context. The full detail of "
                    "each memory is in its own file under memory/facts/ - read it when needed.)")
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
    ten = (f" Their file names: {', '.join(names)}. For any of them, read memory/facts/<name>.md."
           if names else "")
    return "\n".join(kept) + (
        f"\n\n> (The index is too long, so {con_lai} memories are not listed here.{ten} "
        "Read memory/MEMORY.md for the full list, and memory/facts/ for the details.)")


def render_memory_block(text: str, *, memory_cap: int, preserve_full_protected: bool = False) -> str:
    """Keep the legacy memory formatter unless the host requests full protected text."""
    if not (text if preserve_full_protected else text.strip()):
        return ""
    return "\n\n# === BỘ NHỚ DÀI HẠN (long-term memory, preloaded) ===\n" + (text if preserve_full_protected else fit_memory_index(text, memory_cap))


def render_agentic_paths(root, agents, workflows, loops, skills) -> str:
    """Render captured paths without resolving or creating any directory."""
    ag, wf, lp, sk = agents, workflows, loops, skills
    return (
        "\n\n# === LỚP AGENTIC (agentic layer: the working vault) ===\n"
        f"Vault root: {root}\n"
        f"- AGENT: create/edit at `{ag}/<slug>.md`\n"
        f"- WORKFLOW: create/edit at `{wf}/<slug>.md`\n"
        f"- LOOP (an endlessly repeating task): create/edit at `{lp}/<slug>.md`\n"
        f"- SKILL: create/edit at `{sk}/<slug>/SKILL.md` (mirrored to .claude/skills by itself for native Claude)\n"
        f"- OTHER FILES (articles, reports, drafts, data): write them INSIDE the vault root above with an "
        f"ABSOLUTE path `{root}/<folder>/<file name>`. NEVER write relative to the working directory "
        "and never outside the vault: a file outside the vault does not show on the Files page and is "
        "lost on update. In your answer, link with a path RELATIVE to the vault root "
        "(e.g. `posts/post-1.txt`), do NOT use the `file://` scheme and do not encode %20 even if the "
        "harness says otherwise (the chat and Telegram cannot open those), and link ONLY to files "
        "actually written. When counting or listing "
        "files (e.g. \"how many posts are left\"), list the folder again with a tool right then; "
        "do not recall it from an earlier turn.\n"
        "When the user asks to create/edit an agent, workflow or loop from chat, write the .md file in "
        "the right format (see 'Creating/editing Agents and Workflows from chat' and 'Orchestration' in "
        "the system prompt) at the ABSOLUTE PATH above. The Agents, Workflows and Recurring pages pick up "
        "the new file by themselves."
    )


def render_capability_summary(c: dict, latest_workflow_line: str = "") -> str:
    """Render already observed capabilities; never discover or load plugins here."""
    if not any(c.values()):
        return ""
    parts = ["\n\n# === NĂNG LỰC JAVIS HIỆN CÓ (current capabilities: details and triggers in `Javis/index.md`) ==="]
    if c["agents"]:
        parts.append("Agents: " + ", ".join(a["name"] for a in c["agents"][:30]))
    if c["skills"]:
        groups = sorted({s["group"] for s in c["skills"] if s["enabled"]})
        parts.append(f"Skills: {sum(1 for s in c['skills'] if s['enabled'])} skills (groups: {', '.join(groups[:12])})")
    if c["workflows"]:
        parts.append("Workflows: " + ", ".join(w["name"] for w in c["workflows"][:20] if w["status"] == "active"))
    _lc = latest_workflow_line
    if _lc:
        parts.append(_lc)
    if c["loops"]:
        parts.append("Loops: " + ", ".join(f"{l['name']}({'on' if l['enabled'] else 'off'})" for l in c["loops"][:20]))
    live_plugins = [p for p in c.get("plugins", []) if p.get("loaded")]
    if live_plugins:
        tool_names = [t for p in live_plugins for t in p.get("tools", [])]
        parts.append("Plugins running: " + ", ".join(p["name"] for p in live_plugins[:12])
                     + (f" (tool: {', '.join(tool_names[:12])})" if tool_names else ""))
    parts.append("Before creating a new capability, check this index so you do not duplicate one.")
    return "\n".join(parts)


def render_skill_router(visible_metas: list, *, skills_dir, hidden_count: int = 0, description_max: int = 150) -> str:
    """Render a host-selected, already ordered/budgeted router list."""
    if not visible_metas and hidden_count <= 0:
        return ""
    sk_dir = skills_dir
    lines = ["\n\n# === SKILL KHẢ DỤNG (skill router: works on EVERY engine) ==="]
    for s in visible_metas:
        desc = (s.get("description") or "").replace("\n", " ")[:description_max]
        lines.append(f"- {s['slug']} ({s['name']}): {desc}")
    if hidden_count > 0:
        # Nói rõ CÁCH LẤY chứ không chỉ nói còn bao nhiêu: `javis_use_skill` nạp được theo
        # slug kể cả skill không nằm trong danh sách trên, nên một skill bị cắt vẫn dùng được
        # nếu model biết tên. Câu cũ chỉ trỏ sang một file mà model không đọc.
        lines.append(f"…(+{hidden_count} more skills not listed here - the full list is in "
                     f"`Javis/index.md`, and `javis_use_skill(name=<slug>)` loads one directly "
                     f"when you know its name)")
    lines.append(
        "HOW TO USE: when the user's request MATCHES the description of a skill above, LOAD that skill "
        "and FOLLOW it - call tool `javis_use_skill(name=<slug>)` if the engine has it; otherwise open "
        f"`{sk_dir}/<slug>/SKILL.md` with a file-reading tool and follow its instructions. "
        "Load one only on a real match, never indiscriminately."
    )
    return "\n".join(lines)


def render_clock_language(clock_text: str, language_block: str) -> str:
    """Render the frozen clock followed by its already resolved language contract."""
    return "\n\n# === BÂY GIỜ ===\n" + clock_text + language_block


def render_usage_block(today_total: dict) -> str:
    """Render an observed daily total; zero usage keeps the legacy empty block."""
    _t = today_total
    if _t.get("in") or _t.get("out"):
        _c = f", ~${_t.get('cost', 0):.4f}" if _t.get("cost") else ""
        return (f"\n\n# === MỨC DÙNG HÔM NAY (today's usage, measured by Javis) ===\n"
                f"{_t.get('in', 0):,} tokens in + {_t.get('out', 0):,} tokens out over "
                f"{_t.get('turns', 0)} turns{_c}. Javis MEASURES these tokens ITSELF; they are NOT the "
                f"subscription plan's quota (most providers do not expose account quotas through the "
                f"API). Per-provider detail is in the 'Usage' panel of the dashboard.")
    return ""
