"""skill_finder: finding the right skill by its whole text (2026-11-27). Run by hand or in CI:

    python tests/run.py skill_finder

No pytest, no network. Covers:
  - the quality gate on the synthetic 44-skill brain (tests/fixtures/skill_routing_cases.json): the right skill is
    among the suggestions for nearly every request that has one, nothing is preloaded for a request no skill fits,
    and the new ranking beats both the old router list and the old Phase 8 selector;
  - Vietnamese: words with their marks ("bán" is not "bạn", "về" is not "vẽ"), phrases, a request in Vietnamese
    reaching a skill written in English;
  - a short follow-up ranked by the previous messages, a skill named outright, words past character 150;
  - learning: a miss teaches the skill the request, a hit counts, the sidecar survives a restart;
  - the surfaces: javis_use_skill(find=...) and a wrong name, the tool search, find_skills() in javis_code, the turn
    head of main, the Phase 8 lazy skill source;
  - it never raises, and the new files have no long dash.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401  - puts server/ on sys.path (see tests/python/_paths.py)
import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-skillfinder-"))
sys.path.insert(0, str(ROOT / "tools"))

import skill_finder  # noqa: E402
import skill_routing_bench as bench  # noqa: E402

_fails = []


def check(name, cond, detail=""):
    print(("ok   " if cond else "FAIL ") + name + (f"  [{detail}]" if detail and not cond else ""))
    if not cond:
        _fails.append(name)


def brain_with(skills: dict) -> Path:
    return bench.write_brain(skills, Path(tempfile.mkdtemp(prefix="javis-skillfinder-brain-")))


def slugs(matches):
    return [m.slug for m in matches]


DATA = json.loads((ROOT / "tests" / "fixtures" / "skill_routing_cases.json").read_text(encoding="utf-8"))
BRAIN = brain_with(DATA["skills"])

# ---- 1. quality gate ----
skill_finder.reset_memory()
r = bench.evaluate(BRAIN, DATA["cases"])
print(bench.report(r))
check("the fixture has 44 skills and 54 requests with a right skill", len(DATA["skills"]) == 44 and r["positive"] == 54)
check("the right skill is among the suggestions for at least 50 of 54", r["new_shown"] >= 50, r["new_shown"])
check("the right skill comes first for at least 48 of 54", r["new_top"] >= 48, r["new_top"])
check("at most 2 of 8 requests no skill fits get a suggestion", r["false"] <= 2, r["false"])
check("nothing is preloaded for a request no skill fits", r["false_load"] == 0, r["false_load"])
check("a wrong body is preloaded at most once", r["wrong_load"] <= 1, r["wrong_load"])
check("better than the old router list", r["new_shown"] > r["old_list"] + 15, (r["new_shown"], r["old_list"]))
check("better than the old Phase 8 selector", r["new_shown"] > r["old_pick"] + 10, (r["new_shown"], r["old_pick"]))

# ---- 2. Vietnamese, phrases, other languages ----
skill_finder.reset_memory()
VI = brain_with({
    "sales-page": {"name": "Trang bán hàng", "group": "Marketing",
                   "description": "Viết trang bán hàng dài cho khoá học và ebook."},
    "habit": {"name": "Thói quen", "group": "Cá nhân", "description": "Xây thói quen mới, theo dõi chuỗi ngày."},
    "weather": {"name": "Thời tiết", "group": "Cá nhân", "description": "Báo thời tiết và gợi ý mặc gì hôm nay."},
    "paint": {"name": "Paint", "group": "Art", "description": "Paint an original image in a watercolor style."},
    "late-words": {"name": "Report helper", "group": "Ops",
                   "description": ("Helps with routine office paperwork of many kinds, keeps things tidy and "
                                   "consistent, and saves time on repetitive formatting work for the team. "
                                   "Also reconciles supplier invoices against purchase orders.")},
})
check("'bán hàng' keeps 'bán' (folded it is 'bạn', a stop word)",
      slugs(skill_finder.suggest(VI, "viết trang bán hàng cho khoá học"))[:1] == ["sales-page"])
check("'thời tiết' finds the weather skill, not the habit one ('thói' folds the same)",
      slugs(skill_finder.suggest(VI, "thời tiết hôm nay thế nào"))[:1] == ["weather"])
check("'về' (about) is not 'vẽ' (draw): no painting skill for a question about something",
      "paint" not in slugs(skill_finder.suggest(VI, "kể anh nghe về chuyện hôm qua")))
check("a Vietnamese request reaches an English description ('vẽ tranh màu nước' -> paint)",
      slugs(skill_finder.suggest(VI, "vẽ tranh màu nước con mèo"))[:1] == ["paint"])
check("typed without marks it still works ('viet trang ban hang')",
      "sales-page" in slugs(skill_finder.suggest(VI, "viet trang ban hang cho khoa hoc")))
check("words after character 150 of a description count (the old router cut them)",
      slugs(skill_finder.suggest(VI, "reconcile supplier invoices against purchase orders"))[:1] == ["late-words"])
check("a skill named outright comes first",
      slugs(skill_finder.suggest(BRAIN, "dùng skill thu-tay-email-sequence nhé"))[:1] == ["thu-tay-email-sequence"])
check("a request that is only a one-word slug is that skill",
      slugs(skill_finder.suggest(VI, "paint"))[:1] == ["paint"])
check("a greeting gets no suggestion", skill_finder.suggest(BRAIN, "chào em, khoẻ không") == [])

# ---- 3. follow-ups ----
check("'ok làm tiếp đi' is ranked by the previous message",
      slugs(skill_finder.suggest(BRAIN, "ok làm tiếp đi", ["viết kịch bản video tiktok 30 giây"]))[:1] == ["video-script"])
check("a request that says enough is not pulled away by the previous message",
      slugs(skill_finder.suggest(BRAIN, "soát lỗi chính tả bài viết này", ["lịch trình đi Đà Lạt"]))[:1]
      == ["proofread-vietnamese"])

# ---- 4. rendering ----
block = skill_finder.render_suggestions(skill_finder.suggest(BRAIN, "viết email chăm sóc khách sau khi mua"))
desc = DATA["skills"]["thu-tay-email-sequence"]["description"]
check("the block opens with the English head", block.startswith(skill_finder.SUGGESTIONS_HEAD))
check("the description is whole, not cut at 150", desc in block and len(desc) > 150)
check("nothing to suggest renders nothing", skill_finder.render_suggestions([]) == "")
check("readers of the request get it without the suggestions block",
      skill_finder.strip_suggestions(block + "\n\nviết email cho khách") == "viết email cho khách"
      and skill_finder.strip_suggestions("plain message") == "plain message")
check("the API engine loop notes the request without the block",
      "skill_finder.strip_suggestions(c)" in (SERVER / "engine.py").read_text(encoding="utf-8"))
many = [skill_finder.Match(f"s{i}", f"S{i}", "G", "x" * 3000, 9.0, 1.0) for i in range(3)]
check("the block keeps to its budget", len(skill_finder.render_suggestions(many)) < skill_finder.SUGGEST_CHARS + 3200)

# ---- 5. learning ----
skill_finder.reset_memory()
LB = brain_with({k: DATA["skills"][k] for k in ("video-script", "sales-funnel-8-plus-2", "digital-product-creator",
                                                  "content-calendar", "proofread-vietnamese")})
q = "dựng khoảnh khắc nổi bật phố cổ Hội An"
before = skill_finder.suggest(LB, q, session="s1")
check("before learning, no skill has these words", before == [], slugs(before))
skill_finder.note_suggested(LB, "s1", slugs(before), q)
check("a load the suggestions missed teaches the skill the request",
      skill_finder.note_load(LB, "video-script", "s1") == "learned")
side = json.loads((LB / "Javis" / "skill-routing.json").read_text(encoding="utf-8"))
check("the request is in the sidecar", side["skills"]["video-script"]["learned"][0]["text"] == q)
skill_finder.reset_memory()   # a restart
after = skill_finder.suggest(LB, "khoảnh khắc nổi bật phố cổ", session="s2")
check("after a restart a similar request finds the learned skill first", slugs(after)[:1] == ["video-script"],
      slugs(after))
skill_finder.note_suggested(LB, "s3", ["video-script"], "làm cái quảng bá ngắn cho kênh")
check("a load of a suggested skill is a hit", skill_finder.note_load(LB, "video-script", "s3") == "hit")
check("a load with no turn behind it teaches nothing", skill_finder.note_load(LB, "video-script", "") == "")
check("learned requests can be forgotten", skill_finder.forget(LB, "video-script")
      and skill_finder.learned(LB, "video-script") == [])

# ---- 6. the index follows the files ----
skill_finder.reset_memory()
CB = brain_with({"a": {"name": "A", "group": "G", "description": "Write wedding speeches."},
                 "b": {"name": "B", "group": "G", "description": "Plan garden layouts."}})
def found(root, q):
    return [h["slug"] for h in skill_finder.search(root, q)]


check("ranked by the current text", found(CB, "wedding speech toast")[:1] == ["a"])
p = CB / "skills" / "b" / "SKILL.md"
p.write_text(p.read_text(encoding="utf-8").replace("Plan garden layouts.", "Write wedding speeches and toasts, "
                                                    "best man and maid of honour."), encoding="utf-8")
os.utime(p, (p.stat().st_atime, p.stat().st_mtime + 5))
check("an edited skill is ranked by its new text", found(CB, "best man wedding toast")[:1] == ["b"])
dis = CB / "skills" / ".disabled"
dis.mkdir()
(CB / "skills" / "a").rename(dis / "a")
check("a disabled skill is never found", "a" not in found(CB, "wedding speech toast"))

# ---- 7. never raises ----
bad = brain_with({"ok": {"name": "Ok", "group": "G", "description": "Translate documents."}})
(bad / "skills" / "broken").mkdir()
(bad / "skills" / "broken" / "SKILL.md").write_bytes(b"---\ndescription: [unclosed\n---\n\xff\xfe")
check("a broken skill file does not break the others", "ok" in found(bad, "translate this document to English"))
check("a missing brain is no suggestion", skill_finder.suggest(Path("/nonexistent/brain/x"), "anything") == [])
check("turn_block never raises", skill_finder.turn_block(None, "x") == "")

# ---- 8. javis_use_skill, the tool search, javis_code ----
import mcp_hub  # noqa: E402
import code_mode  # noqa: E402

skill_finder.reset_memory()
specs, routes = mcp_hub._builtin_tools("full", BRAIN)
use = next(t for t in specs if t["fn"] == "javis_use_skill")
check("javis_use_skill names the skills", "thu-tay-email-sequence" in use["description"])
check("javis_use_skill no longer carries descriptions", desc[:60] not in use["description"])
check("javis_use_skill takes find=", "find" in use["schema"]["properties"])
found = asyncio.run(routes["javis_use_skill"]["call"]({"find": "chuỗi email chăm sóc khách hàng"}))
check("find= returns the best skills with their whole description",
      "thu-tay-email-sequence" in found and desc in found, found[:200])
wrong = asyncio.run(routes["javis_use_skill"]["call"]({"name": "email-sequence"}))
check("a wrong name answers with the closest skills",
      wrong.startswith("ERROR") and "thu-tay-email-sequence" in wrong, wrong[:200])
check("neither name nor find is a clear error",
      asyncio.run(routes["javis_use_skill"]["call"]({})).startswith("ERROR"))

pool = [t for t in specs if t["fn"] == "javis_use_skill"]
lazy_tools, lazy_route = mcp_hub._lazy_tools_and_route([], {}, pool, routes, 8, scope=str(BRAIN))
res = asyncio.run(lazy_route["javis_search_tools"]["call"]({"query": "soát lỗi chính tả tiếng Việt"}))
payload = json.loads(res) if res.strip().startswith("{") else {}
check("the tool search returns skills with their whole description",
      any(s["name"] == "proofread-vietnamese" for s in payload.get("skills") or []), res[:300])
check("and says how to load one", "javis_use_skill" in (payload.get("skills_note") or ""))

ok, text = asyncio.run(code_mode._dispatch({}, code_mode.SKILL_SEARCH, {"query": "dự báo dòng tiền"}, str(BRAIN)))
check("find_skills() in javis_code reads the skill index",
      ok and json.loads(text)[0]["slug"] == "cashflow-forecast", text[:200])
check("find_skills() needs a brain", code_mode._dispatch.__code__.co_argcount == 4)
check("javis_code tells the model about find_skills()", "find_skills(" in code_mode.DESCRIPTION)
check("the child script defines find_skills()", "def find_skills(" in code_mode.CHILD)

# ---- 9. the turn head of main, and every lane uses it ----
import main  # noqa: E402

skill_finder.reset_memory()
head = main._skill_turn_head(str(BRAIN), "sess-1", "tóm tắt video youtube này giúp anh")
check("main._skill_turn_head opens with the suggestions", head.startswith(skill_finder.SUGGESTIONS_HEAD)
      and "youtube-summary" in head, head[:200])
check("a non-text message gets nothing", main._skill_turn_head(str(BRAIN), "s", [{"type": "image"}]) == "")
check("a skill already loaded this turn is left out",
      "youtube-summary" not in main._skill_turn_head(str(BRAIN), "s", "tóm tắt video youtube này giúp anh",
                                                     exclude=("youtube-summary",)))
hist = [{"role": "user", "content": "viết kịch bản video tiktok 30 giây"}, {"role": "assistant", "content": "..."},
        {"role": "user", "content": "ok làm tiếp đi"}]
check("the stored history ranks a follow-up",
      "video-script" in main._skill_turn_head(str(BRAIN), "s", "ok làm tiếp đi", hist))
src = (SERVER / "main.py").read_text(encoding="utf-8")
for lane, marker in (("Grok", "_k_sk = await _turn_skills("), ("Antigravity", "_a_sk = await _turn_skills("),
                     ("Codex", "_codex_sk = await _turn_skills("), ("API engines", "_api_sk = await _turn_skills("),
                     ("Claude Code", "_cc_sk = await _turn_skills("), ("channels", "_text_engine = (_ch_sk")):
    check(f"the {lane} lane puts the suggestions at the head of the turn", marker in src)
check("the channel API lane keeps the plain message in its history", '_u_msg["content"] = text' in src)

# ---- 10. Phase 8 lazy skill source ----
from capability_registry import CapabilityRegistry  # noqa: E402
from lazy_skill_runtime import LazySkillSource  # noqa: E402

skill_finder.reset_memory()
source = LazySkillSource(CapabilityRegistry(Path(tempfile.mkdtemp(prefix="javis-skillfinder-reg-"))))
sel = source.resolve(BRAIN, "lên thực đơn bữa cơm gia đình cả tuần, kèm danh sách đi chợ")
check("a clear request preloads that skill's body", (sel.action, sel.slug) == ("load", "meal-planner"),
      (sel.action, sel.reason, sel.slug))
sel = source.resolve(BRAIN, "doanh thu hôm nay bao nhiêu")
check("a request no skill fits preloads nothing and does not fall back", sel.action == "none", (sel.action, sel.reason))

# ---- 11. no long dash in the new files ----
for rel in ("server/skill_finder.py", "tools/skill_routing_bench.py", "tests/fixtures/skill_routing_cases.json",
            "tests/python/test_skill_finder.py"):
    text = (ROOT / rel).read_text(encoding="utf-8")
    check(f"no long dash in {rel}", chr(0x2014) not in text and chr(0x2013) not in text)

print()
if _fails:
    print(f"FAILED {len(_fails)}: " + "; ".join(_fails))
    sys.exit(1)
print("all skill_finder checks passed")
