"""Measure how well Javis finds the right skill for a request: the old router against skill_finder.

    python tools/skill_routing_bench.py                       # the synthetic 44-skill brain of the tests
    python tools/skill_routing_bench.py --brain <brain dir> --cases <cases.json>
    python tools/skill_routing_bench.py -v                    # one line per request

cases.json: {"cases": [{"q": "request", "expect": "slug" or null, "recent": ["previous message", ...]}]}. With no
--brain, the skills come from the same file ({"skills": {slug: {"name", "group", "description", "body"}}}).

What is measured, per request that has a right skill:
  old list    the right skill was in the old router list at all (40 entries, 4,000 characters, descriptions cut at
              150, in alphabetical order as on a brain where nothing has been used yet)
  old pick    the old Phase 8 selector (word overlap over descriptions cut at 150) loaded the right skill
  new top     skill_finder ranks the right skill first among its suggestions
  new shown   the right skill is among the suggestions of the turn
and, per request no skill fits, how often something was suggested anyway (false).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))
os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-skillbench-"))

FIXTURE = ROOT / "tests" / "fixtures" / "skill_routing_cases.json"


def write_brain(skills: dict, root: Path) -> Path:
    for slug, s in skills.items():
        d = root / "skills" / slug
        d.mkdir(parents=True, exist_ok=True)
        front = {"name": s.get("name") or slug, "description": s.get("description") or "",
                 "group": s.get("group") or "Chung"}
        head = "---\n" + "".join(f"{k}: {json.dumps(v, ensure_ascii=False)}\n" for k, v in front.items()) + "---\n"
        (d / "SKILL.md").write_text(head + (s.get("body") or "") + "\n", encoding="utf-8")
    return root


def _old_visible(root: Path) -> set:
    import skill_router
    metas = sorted(skill_router.list_enabled_meta(root), key=lambda m: m["slug"])
    cut = [dict(m, description=(m.get("description") or "")[:150]) for m in metas]
    shown, _hidden = skill_router.cat_theo_ngan_sach(cut, 40, 4000)
    return {m["slug"] for m in shown}


def _norm(value: str) -> str:
    import re
    import unicodedata
    raw = unicodedata.normalize("NFKD", str(value or "").casefold())
    return " ".join(re.findall(r"[a-z0-9]{2,}", "".join(c for c in raw if not unicodedata.combining(c))))


def _old_score(query: str, item: dict) -> float:
    """The Phase 8 lazy skill score before 2026-11-27, frozen here: word overlap with the name and the summary."""
    query_norm = _norm(query)
    query_terms = set(query_norm.split())
    name = _norm(item.get("name") or "")
    aliases = {_norm(x) for x in item.get("aliases") or []}
    summary = _norm(item.get("summary") or "")
    name_terms = set((name + " " + " ".join(aliases)).split())
    all_terms = name_terms | set(summary.split())
    coverage = len(query_terms & all_terms) / max(1, len(query_terms))
    discriminative = len(query_terms & name_terms) / max(1, len(name_terms))
    phrase = bool(query_norm and (query_norm in summary or query_norm in name))
    explicit = query_norm == name or query_norm in aliases
    return min(1.0, coverage * 0.52 + discriminative * 0.25 + (0.13 if phrase else 0) + (0.25 if explicit else 0))


def _old_pick(root: Path, state: Path):
    """The Phase 8 selector as it was: the registry's candidates over manifests cut at 150, its own score, a
    minimum of 0.24 and a margin of 0.08 over the runner-up."""
    import skill_router
    from capability_registry import CapabilityRegistry
    registry = CapabilityRegistry(state)
    manifests = [dict(m, description=(m.get("description") or "")[:150])
                 for m in skill_router.list_skill_manifests(root)]
    registry.refresh_skills(root, manifests)

    def pick(q):
        cands = [x for x in registry.search(q, root, 40) if str(x.get("kind") or "") == "skill"]
        ranked = sorted(((_old_score(q, x), x) for x in cands), key=lambda p: (-p[0], p[1]["capability_id"]))
        if not ranked or ranked[0][0] < 0.24:
            return None
        if len(ranked) > 1 and ranked[0][0] - ranked[1][0] < 0.08:
            return None
        return str((ranked[0][1].get("metadata") or {}).get("slug") or ranked[0][1].get("name") or "")
    return pick


def evaluate(root: Path, cases: list, verbose: bool = False, old: bool = True) -> dict:
    import skill_finder
    skill_finder.reset_memory()
    visible = _old_visible(root) if old else set()
    old_pick = _old_pick(root, Path(tempfile.mkdtemp(prefix="javis-skillbench-reg-"))) if old else None
    n_pos = n_neg = 0
    got = {"old_list": 0, "old_pick": 0, "new_top": 0, "new_shown": 0, "new_load": 0, "false": 0,
           "false_load": 0, "old_false_pick": 0, "wrong_load": 0}
    rows = []
    for c in cases:
        q, want, recent = c["q"], c.get("expect"), c.get("recent") or []
        # expect: one slug, or a list of slugs that are all right answers (several skills doing the same job)
        wants = set(want) if isinstance(want, list) else ({want} if want else set())
        sug = skill_finder.suggest(root, q, recent)
        slugs = [m.slug for m in sug]
        picked = old_pick(q) if old_pick else None
        if wants:
            n_pos += 1
            got["old_list"] += bool(wants & visible)
            got["old_pick"] += picked in wants
            got["new_top"] += bool(slugs) and slugs[0] in wants
            got["new_shown"] += bool(wants & set(slugs))
            got["new_load"] += bool(slugs) and slugs[0] in wants and skill_finder.confident(sug)
            got["wrong_load"] += bool(slugs) and slugs[0] not in wants and skill_finder.confident(sug)
            ok = bool(wants & set(slugs))
        else:
            n_neg += 1
            got["false"] += bool(slugs)
            got["false_load"] += skill_finder.confident(sug)
            got["old_false_pick"] += bool(picked)
            ok = not slugs
        rows.append((ok, q, want, [(m.slug, round(m.score, 2), round(m.coverage, 2)) for m in sug], picked))
    if verbose:
        for ok, q, want, sug, picked in rows:
            print(("ok   " if ok else "MISS ") + f"{q!r} -> want {want}: {sug} | old pick {picked}")
    return {"positive": n_pos, "negative": n_neg, **got}


def report(r: dict) -> str:
    p, n = max(1, r["positive"]), max(1, r["negative"])
    return "\n".join([
        f"{r['positive']} requests with a right skill, {r['negative']} with none",
        f"old list  : right skill visible at all     {r['old_list']}/{r['positive']} ({100 * r['old_list'] // p}%)",
        f"old pick  : old selector loaded it         {r['old_pick']}/{r['positive']} ({100 * r['old_pick'] // p}%)",
        f"new top   : ranked first                   {r['new_top']}/{r['positive']} ({100 * r['new_top'] // p}%)",
        f"new shown : among the turn's suggestions   {r['new_shown']}/{r['positive']} ({100 * r['new_shown'] // p}%)",
        f"new load  : confident enough to preload    {r['new_load']}/{r['positive']} ({100 * r['new_load'] // p}%)",
        f"wrong load: preloaded the wrong skill      {r['wrong_load']}/{r['positive']}",
        f"false     : suggested when none fits       {r['false']}/{r['negative']} ({100 * r['false'] // n}%)",
        f"false load: preloaded when none fits       {r['false_load']}/{r['negative']} "
        f"(old selector: {r['old_false_pick']}/{r['negative']})",
    ])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--brain", help="brain folder with skills/ (default: the synthetic brain of the fixture)")
    ap.add_argument("--cases", default=str(FIXTURE))
    ap.add_argument("-v", "--verbose", action="store_true")
    a = ap.parse_args()
    data = json.loads(Path(a.cases).read_text(encoding="utf-8"))
    root = Path(a.brain) if a.brain else write_brain(data["skills"], Path(tempfile.mkdtemp(prefix="javis-skillbench-")))
    print(report(evaluate(root, data["cases"], a.verbose)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
