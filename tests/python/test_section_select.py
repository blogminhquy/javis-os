"""Javis picks the parts of a long menu-style skill a task needs, before loading, and loads everything when unsure.

    python tests/run.py section_select      (no network)

Owner, 18/11/2026: save tokens on long skills only with "cơ chế nào đó tìm thông tin nạp thông minh trước khi nạp", never
at the cost of the answer. What this pins:
  1. The real javis-builder: each clear request gets its own template plus every rule section, verbatim (no loss of
     what the task needs); vague or unrelated requests load the whole skill.
  2. Only menu-style skills are split: a one-procedure skill (the seo-audit case) loads whole unless it opts in.
  3. The canary share, the owner-only rule, the env switch and the Off saving level.
  4. Learning from use: a part fetched in two turns is loaded up front; two heavy turns make the skill load whole.
  5. javis_use_skill (task, section, full) and the automatic skill path of the context runtime use it; the meter
     counts it; the API loops hand it the turn's request.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import json
import os
import shutil
import tempfile
from pathlib import Path
from unittest.mock import patch

_TMP = Path(tempfile.mkdtemp(prefix="javis-sections-"))
os.environ["JAVIS_STATE_DIR"] = str(_TMP / "state")
(_TMP / "state").mkdir()
os.environ.pop("JAVIS_SKILL_SECTIONS", None)

import section_select as ss  # noqa: E402

fails = []


def check(name, ok, extra=None):
    print(("ok   " if ok else "FAIL ") + name + ("" if ok or extra is None else f"  [{extra}]"))
    if not ok:
        fails.append(name)


BUILDER = (ROOT / ".claude" / "skills" / "javis-builder" / "SKILL.md").read_text(encoding="utf-8")

# ───────────────────────── 1. parsing ─────────────────────────
doc = """---
name: Demo
description: demo
---
# Demo

Intro text.

## Rules
Always do X.

## Templates
Pick one.

### Alpha
alpha body
```
## not a heading inside a fence
```

### Beta
beta body

## Extra
extra body
"""
lines, pre_end, units = ss.parse(doc)
check("parse: the preamble keeps frontmatter, title and intro", "Intro text." in "\\n".join(lines[:pre_end]) and
      lines[0] == "---")
check("parse: two levels, a fenced heading is text", [u.title for u in units] == ["Rules", "Templates", "Alpha", "Beta", "Extra"],
      [u.title for u in units])
check("parse: a rules heading is always loaded, its children too",
      units[0].always and not units[1].always and units[2].parent == 1)
check("find_section: a top-level section comes with its children",
      "alpha body" in ss.find_section(doc, "templates") and "beta body" in ss.find_section(doc, "Templates"))
check("find_section: accent and case free, prefix match", ss.find_section(doc, "ALP").startswith("### Alpha"))
check("find_section: unknown title", ss.find_section(doc, "gamma") is None)

# ───────────────────────── 2. the real javis-builder ─────────────────────────
TYPES = {"Agent": "Agent ->", "Loop": "Loop ->", "Plugin": "Plugin ->", "Workflow": "Workflow ->", "Skill": "Skill ->",
         "Team": "Nhóm chat ->"}
CASES = [
    ("Tạo giúp mình một agent chuyên viết email chăm sóc khách cũ", "Agent"),
    ("Tạo một loop cứ 30 phút kiểm tra đơn hàng mới trên POS", "Loop"),
    ("Viết plugin tính phí ship theo cân nặng", "Plugin"),
    ("Tạo workflow viết bài blog rồi đăng lên Facebook", "Workflow"),
    ("Tạo skill viết caption bán hàng", "Skill"),
    ("Lập nhóm chat gồm trợ lý marketing và trợ lý bán hàng", "Team"),
    ("Sửa agent viet-email cho ngắn gọn hơn", "Agent"),
    ("Thêm một bước vào workflow dang-bai", "Workflow"),
    ("Create an agent that writes cold emails", "Agent"),
    ("Làm cho mình cái tự động hoá chăm sóc khách", None),
    ("Nhắc mình uống thuốc lúc 8 giờ tối mỗi ngày", None),
    ("Mỗi sáng 7h tổng hợp doanh thu gửi Telegram", None),
    ("", None),
]
b_lines, b_pre, b_units = ss.parse(BUILDER)
rule_texts = ["\n".join(b_lines[u.start:u.end]) for u in b_units if u.always]
check("javis-builder: rule sections are found", len(rule_texts) >= 3, [u.title for u in b_units if u.always])
right = 0
for request, want in CASES:
    sel = ss.select(BUILDER, request, ss.SKILL_MIN_CHARS)
    if want is None:
        good = sel is None
    else:
        need = next(u for u in b_units if u.title.startswith(TYPES[want]))
        need_text = "\n".join(b_lines[need.start:need.end])
        good = (sel is not None and need_text in sel.text and all(r in sel.text for r in rule_texts)
                and sel.sent_chars < 0.75 * sel.full_chars)
    right += good
    if not good:
        print("     case:", request, "->", None if sel is None else sel.loaded)
check(f"javis-builder: {right}/{len(CASES)} requests get exactly what they need, unsure ones load whole",
      right == len(CASES))

# ───────────────────────── 3. only menu-style skills, the switches ─────────────────────────
procedure = "---\nname: SEO audit\ndescription: audit SEO\n---\n# SEO Audit\n\n" + "".join(
    f"## {t}\n" + (f"{t} check details. " * 80) + "\n\n" for t in
    ["On-Page SEO Audit", "Crawlability", "Indexation", "Site Speed", "Mobile Friendliness", "Content Quality"])
with patch.object(ss, "assigned", return_value=True):
    check("a one-procedure skill loads whole (not on the menu list)", ss.for_skill("seo-audit", procedure, "on-page seo audit", "", "s1") is None)
    opted = procedure.replace("description: audit SEO\n", "description: audit SEO\nsections: select\n")
    check("the same skill splits when its frontmatter opts in",
          (ss.for_skill("seo-audit", opted, "crawlability problems", "", "s1") or "").startswith("[Javis loaded"))
    picked = ss.for_skill("javis-builder", BUILDER, "", "Tạo agent viết email", "s1")
    check("javis-builder is on the menu list, and the result says what was left out",
          picked and picked.startswith("[Javis loaded") and 'section="<title>"' in picked and "full=true" in picked)

with patch.object(ss, "_flag", wraps=ss._flag):
    os.environ["JAVIS_SKILL_SECTIONS"] = "1"
    check("JAVIS_SKILL_SECTIONS=1: every owner session", ss.assigned("any-session"))
    check("but never without a session (bot, background job)", not ss.assigned(""))
    os.environ["JAVIS_SKILL_SECTIONS"] = "0"
    check("JAVIS_SKILL_SECTIONS=0: nobody", not ss.assigned("any-session"))
    os.environ.pop("JAVIS_SKILL_SECTIONS")
share = sum(ss.assigned(f"session-{i}") for i in range(2000)) / 2000
check("by default about 10% of sessions", 0.06 < share < 0.14, share)
import config  # noqa: E402
with patch.object(config, "read_settings", return_value={"context_runtime": {"skill_sections": {"allocation_basis_points": 10000}}}):
    check("settings raise the share to everyone", all(ss.assigned(f"s{i}") for i in range(50)))
with patch.object(config, "read_settings", return_value={"context_runtime": {"skill_sections": {"skills": ["seo-audit"]}}}):
    check("settings can list a skill as safe to split", ss.opted_in("seo-audit", procedure))
import tool_result_shaper  # noqa: E402
with patch.object(tool_result_shaper, "settings", return_value={"on": False}):
    os.environ["JAVIS_SKILL_SECTIONS"] = "1"
    check("the Off saving level turns it off", not ss.assigned("any-session"))
    os.environ.pop("JAVIS_SKILL_SECTIONS")
import turn_context as tc  # noqa: E402
tok = tc.bind(tc.make("zalo", sender_id="khach", chat_id="c1", la_chu=False))
check("a bot answering a customer has no session for it", ss.session_key() == "")
tc.reset(tok)
tok = tc.bind(tc.make("dashboard", la_chu=True, session_id="sess-9"))
check("the owner's chat session is the key", ss.session_key() == "sess-9")
tc.reset(tok)

# ───────────────────────── 4. learning from use ─────────────────────────
key = ss.text_key("skill", "javis-builder", BUILDER)
agent_title = next(u.title for u in b_units if u.title.startswith("Agent ->"))
check("section= names resolve to the real heading", ss.resolve_title(BUILDER, "agent") == agent_title)
for n in range(2):   # two turns that had to fetch the Agent template after a workflow request
    ss.note_load("skill", "javis-builder", key, f"turn-{n}")
    ss.note_fetch("skill", "javis-builder", f"turn-{n}", agent_title)
    ss.note_fetch("skill", "javis-builder", f"turn-{n}", agent_title)   # the same part twice counts once
full_now, extra = ss.learned(key)
check("a part fetched in two turns is learned", extra == {agent_title} and not full_now, (full_now, extra))
check("learned titles are matched like headings",
      ss.select(BUILDER, "Thêm một bước vào workflow dang-bai", ss.SKILL_MIN_CHARS,
                (False, {agent_title})).loaded.count(agent_title) == 1)
sel = ss.select(BUILDER, "Thêm một bước vào workflow dang-bai", ss.SKILL_MIN_CHARS, ss.learned(key))
check("the learned part now comes up front", sel is not None and "### Agent ->" in sel.text)
ss.note_fetch("skill", "javis-builder", "never-loaded", "Loop")
check("a fetch with no selective load before it is not counted", "Loop" not in (ss.learned(key)[1]))
for n in range(2):   # two heavy turns: the whole skill, or two extra parts
    ss.note_load("skill", "javis-builder", key, f"heavy-{n}")
    ss.note_fetch("skill", "javis-builder", f"heavy-{n}", "*")
check("two heavy turns: the skill loads whole from then on",
      ss.learned(key)[0] and ss.select(BUILDER, "Tạo agent viết email", ss.SKILL_MIN_CHARS, ss.learned(key)) is None)
check("a changed skill starts over", ss.learned(ss.text_key("skill", "javis-builder", BUILDER + " ")) == (False, set()))
(_TMP / "state" / "section_learning.json").unlink()

# ───────────────────────── 5. through javis_use_skill and the automatic skill path ─────────────────────────
import mcp_hub  # noqa: E402
vault = _TMP / "brain"
(vault / "skills" / "javis-builder").mkdir(parents=True)
(vault / "skills" / "javis-builder" / "SKILL.md").write_text(BUILDER, encoding="utf-8")
_tools, route = mcp_hub._builtin_tools("full", str(vault))
use = route["javis_use_skill"]["call"]
desc = next(t["description"] for t in _tools if t["fn"] == "javis_use_skill")
check("javis_use_skill offers task, section and full", "task=" in desc and "section=" in desc and "full=true" in desc)


async def _use(args):
    return await use(args)

os.environ["JAVIS_SKILL_SECTIONS"] = "1"
tok = tc.bind(tc.make("dashboard", la_chu=True, session_id="sess-use"))
try:
    got = asyncio.run(_use({"name": "javis-builder", "task": "tạo agent viết email"}))
    check("javis_use_skill with a task: the parts it needs", got.startswith("[Javis loaded") and "### Agent ->" in got
          and "### Loop ->" not in got, got[:120])
    part = asyncio.run(_use({"name": "javis-builder", "section": "Loop"}))
    check("section= brings one part", part.startswith("### Loop ->") or "\n### Loop ->" in part[:400], part[:80])
    whole = asyncio.run(_use({"name": "javis-builder", "full": True}))
    check("full=true brings the whole skill", "### Loop ->" in whole and "### Agent ->" in whole and len(whole) >= len(BUILDER))
    bad = asyncio.run(_use({"name": "javis-builder", "section": "nope"}))
    check("an unknown section lists the real ones", bad.startswith("ERROR") and "Agent ->" in bad)
    learned_titles = {t for t in json.loads((_TMP / "state" / "section_learning.json").read_text(encoding="utf-8"))
                      [ss.text_key("skill", "javis-builder", BUILDER)]["extra"]}
    check("a fetch through javis_use_skill is recorded under the real heading",
          learned_titles == {next(u.title for u in b_units if u.title.startswith("Loop ->"))}, learned_titles)
    plain = asyncio.run(_use({"name": "javis-builder"}))
    check("no task and no request known: the whole skill", "### Loop ->" in plain and not plain.startswith("[Javis"))
    ss.QUESTION.set("Tạo một loop kiểm tra đơn mới")
    from_turn = asyncio.run(_use({"name": "javis-builder"}))
    check("the turn's request alone is enough to choose", from_turn.startswith("[Javis loaded") and "### Loop ->" in from_turn)
    ss.QUESTION.set("")
finally:
    tc.reset(tok)
tok = tc.bind(tc.make("zalo", sender_id="khach", chat_id="c1", la_chu=False))
try:
    bot = asyncio.run(_use({"name": "javis-builder", "task": "tạo agent viết email"}))
    check("a bot turn always gets the whole skill", "### Loop ->" in bot and not bot.startswith("[Javis"))
finally:
    tc.reset(tok)

from capability_registry import CapabilityRegistry  # noqa: E402
from lazy_skill_runtime import LazySkillSource  # noqa: E402
lazy = LazySkillSource(CapabilityRegistry(_TMP / "state" / "registry"))
picked = lazy.resolve(vault, "Tạo agent javis-builder viết email chăm sóc khách", session_key="sess-lazy")
check("automatic skill path: a long menu skill now loads its needed parts instead of falling back",
      picked.action == "load" and "### Agent ->" in picked.context_item.content
      and "### Loop ->" not in picked.context_item.content, (picked.action, picked.reason))
old = lazy.resolve(vault, "Tạo agent javis-builder viết email chăm sóc khách")
check("without a session the old fallback stays", old.action == "fallback" and old.reason == "body_over_limit",
      (old.action, old.reason))
os.environ.pop("JAVIS_SKILL_SECTIONS")

import tool_result_reuse  # noqa: E402
tool_result_reuse._LOG_POOL.submit(lambda: None).result(timeout=5)
stats = mcp_hub.result_size_stats(7)
check("the meter counts what selective loading kept out", stats.get("saved_chars", 0) > 0 and
      any(r["tool"] in ("javis_use_skill", "lazy_skill") for r in stats.get("by_tool") or []), stats.get("by_tool"))

import engine  # noqa: E402
ss.QUESTION.set("")
engine._note_question([{"role": "system", "content": "x"}, {"role": "user", "content": "câu cũ"},
                       {"role": "assistant", "content": "y"},
                       {"role": "user", "content": [{"type": "text", "text": "tạo loop mới"}]}])
check("the API loops hand over the last request of the turn", ss.QUESTION.get() == "tạo loop mới", ss.QUESTION.get())

shutil.rmtree(_TMP, ignore_errors=True)
print()
if fails:
    print(f"{len(fails)} FAIL")
    raise SystemExit(1)
print("all ok")
