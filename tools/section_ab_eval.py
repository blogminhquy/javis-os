"""A/B with a real model: is an answer as good when Javis loads only the parts of a skill a task needs? (2026-11-18)

    python tools/section_ab_eval.py                       # Anthropic (ANTHROPIC_API_KEY), 3 tries per case
    python tools/section_ab_eval.py --provider openai --model gpt-5-mini --base-url https://openrouter.ai/api/v1
    python tools/section_ab_eval.py --repeat 5 --out ab.json

Owner, 18/11/2026: merge selective skill loading only when the quality measure shows no task got worse. Each case asks
the same model the same request twice per try: once with the WHOLE skill as its instructions, once with what
section_select would load (the parts plus the list of what was left out). Both answers are scored on the key facts a
correct answer must contain (the template's own fields and paths, the safety rules) and on banned strings. The run fails
(exit 1) when the selective variant covers fewer key facts than the whole one on any case, averaged over the tries.

Cases are javis-builder requests, the one skill on section_select.MENU_SKILLS. A skill added to that list should bring
its own cases here first. Javis serves every language (owner, 18/11/2026), so cases come in several: a request in
another language than the skill carries the `task` the model would pass to javis_use_skill, written in the skill's
language as its description asks.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "server"))
sys.path.insert(0, str(ROOT / "tools"))

import section_select  # noqa: E402
from quality_eval import score  # noqa: E402

BANNED = ["\u2014", "\u2013"]   # the em and en dash the owner banned
# A path is wrong only when the answer writes a file under it; "not `Javis/agents/`" is the right warning, not a fault.
WRONG_AGENT_DIR = r"Javis/agents/[a-z0-9]"
ASK = ("Do not call any tool. Write out exactly what you would create (file path and full file content, or the tool "
       "call with its arguments), then one short line on what the user does next.")
CASES = [
    {"id": "agent", "ask": "Tạo giúp mình một agent chuyên viết email chăm sóc khách cũ.",
     "must": [["agents/"], ["type: agent"], ["role:"], ["tags:"], ["slug:"]],
     "must_not_re": [WRONG_AGENT_DIR]},
    {"id": "agent-en", "ask": "Create an agent that writes cold outreach emails.",
     "must": [["agents/"], ["type: agent"], ["role:"], ["tags:"]], "must_not_re": [WRONG_AGENT_DIR]},
    {"id": "loop", "ask": "Tạo một loop cứ 30 phút kiểm tra đơn hàng mới trên POS rồi báo mình.",
     # The skill prefers the javis_schedule tool over writing Javis/loops/<slug>.md by hand: either is right.
     "must": [["javis_schedule", "Javis/loops/"], ["enabled: false"], ["mode:"]], "must_not": []},
    {"id": "plugin", "ask": "Viết plugin tính phí ship theo cân nặng đơn hàng.",
     "must": [["javis_plugin"], ["min_mode"], ["readonly"], ["enabled: false", "tat", "off"]], "must_not": []},
    {"id": "workflow", "ask": "Tạo workflow: một trợ lý viết bài blog, rồi một trợ lý đăng lên Facebook.",
     # Two new assistants: a right answer creates them first, from the Agent template (role:, not description:).
     "must": [["workflows/"], ["type: workflow"], ["steps:"], ["status: 'off'", "status: \"off\"", "status: off"],
              ["role:"]],
     "must_not": [], "must_not_re": [r"Javis/workflows/[a-z0-9]", WRONG_AGENT_DIR]},
    {"id": "skill", "ask": "Tạo skill viết caption bán hàng cho Facebook.",
     "must": [["skills/"], ["SKILL.md"], ["description:"], ["group:"]], "must_not": []},
    {"id": "team", "ask": "Lập nhóm chat gồm trợ lý marketing và trợ lý bán hàng.",
     "must": [["javis_team"], ["op"], ["create"]], "must_not": []},
    {"id": "agent-ja", "ask": "古いお客様にフォローメールを書くエージェントを作って。",
     "task": "tạo agent viết email chăm sóc khách cũ",
     "must": [["agents/"], ["type: agent"], ["role:"], ["tags:"], ["slug:"]], "must_not_re": [WRONG_AGENT_DIR]},
    {"id": "loop-es", "ask": "Crea un loop que revise cada 30 minutos los pedidos nuevos del POS y me avise.",
     "must": [["javis_schedule", "Javis/loops/"], ["enabled: false"], ["mode:"]], "must_not": []},
    {"id": "workflow-ru", "ask": "Создай workflow: один помощник пишет статью для блога, другой публикует её в Facebook.",
     "task": "tạo workflow: trợ lý viết blog rồi trợ lý đăng Facebook",
     "must": [["workflows/"], ["type: workflow"], ["steps:"], ["status: 'off'", "status: \"off\"", "status: off"],
              ["role:"]],
     "must_not": [], "must_not_re": [r"Javis/workflows/[a-z0-9]", WRONG_AGENT_DIR]},
]


def grade(answer: str, case: dict) -> dict:
    """Key facts covered and rules broken. A tool call written as JSON ("mode": "full") or as keyword arguments
    (mode = "full") counts like YAML (mode: full): the same call, another notation."""
    plain = re.sub(r'"([A-Za-z_]+)"\s*:\s*', r"\1: ", answer)
    plain = re.sub(r"\b([A-Za-z_]+)\s*=\s*(?!=)", r"\1: ", plain)
    s = score(plain, case["must"], case.get("must_not", []) + BANNED)
    s["violations"] += [p for p in case.get("must_not_re", []) if re.search(p, answer)]
    return s


def variants(skill_text: str, request: str, task: str = "") -> dict:
    """The two instruction texts for one request: whole, and what section_select loads (None when it loads whole).
    Like for_skill, the choice reads the model's task and the user's request together."""
    query = " ".join(x for x in (task, request) if x)
    picked = section_select.select(skill_text, query, section_select.SKILL_MIN_CHARS)
    if picked is None:
        return {"whole": skill_text, "selected": None}
    tail = ("\n\n[Other parts of this skill, not loaded: " + "; ".join(f'"{t}"' for t, _a, _b in picked.left_out)
            + ". If the task needs one, call javis_use_skill(name=\"javis-builder\", section=\"<title>\"), or "
              "full=true for the whole skill.]")
    return {"whole": skill_text, "selected": picked.text + tail}


def ask_model(a, system: str, user: str) -> tuple[str, int]:
    import httpx
    if a.provider == "anthropic":
        key = os.getenv("ANTHROPIC_API_KEY") or "proxy-injected"
        r = httpx.post(a.base_url or "https://api.anthropic.com/v1/messages", timeout=180,
                       headers={"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
                       json={"model": a.model, "max_tokens": 2000, "system": system,
                             "messages": [{"role": "user", "content": user}]})
        r.raise_for_status()
        d = r.json()
        text = "".join(b.get("text", "") for b in d.get("content") or [] if b.get("type") == "text")
        return text, int((d.get("usage") or {}).get("input_tokens") or 0)
    key = os.getenv("OPENAI_API_KEY") or os.getenv("OPENROUTER_API_KEY") or "proxy-injected"
    r = httpx.post((a.base_url or "https://api.openai.com/v1").rstrip("/") + "/chat/completions", timeout=180,
                   headers={"Authorization": f"Bearer {key}"},
                   json={"model": a.model, "messages": [{"role": "system", "content": system},
                                                        {"role": "user", "content": user}]})
    r.raise_for_status()
    d = r.json()
    return d["choices"][0]["message"]["content"] or "", int((d.get("usage") or {}).get("prompt_tokens") or 0)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--provider", choices=("anthropic", "openai"), default="anthropic")
    ap.add_argument("--model", default="claude-sonnet-5-5")
    ap.add_argument("--base-url", default="")
    ap.add_argument("--repeat", type=int, default=3)
    ap.add_argument("--skill", default=str(ROOT / ".claude" / "skills" / "javis-builder" / "SKILL.md"))
    ap.add_argument("--only", default="")
    ap.add_argument("--out", default="")
    a = ap.parse_args(argv)
    skill = Path(a.skill).read_text(encoding="utf-8")
    system_head = ("You are Javis, the owner's assistant. Follow the skill below exactly; it is your instructions for "
                   "this request.\n\n")
    rows, worse = [], 0
    for case in CASES:
        if a.only and case["id"] not in a.only.split(","):
            continue
        v = variants(skill, case["ask"], case.get("task", ""))
        if v["selected"] is None:
            print(f"{case['id']:<10} section_select loads the whole skill: nothing to compare")
            rows.append({"id": case["id"], "selected": None})
            continue
        res = {"whole": [], "selected": []}
        for _ in range(a.repeat):
            for name in ("whole", "selected"):
                t0 = time.time()
                text, tin = ask_model(a, system_head + v[name], case["ask"] + "\n\n" + ASK)
                s = grade(text, case)
                res[name].append({"coverage": s["coverage"], "missing": s["missing"], "violations": s["violations"],
                                  "input_tokens": tin, "seconds": round(time.time() - t0, 1), "answer": text})
        cov = {k: statistics.mean(x["coverage"] for x in res[k]) for k in res}
        tok = {k: statistics.mean(x["input_tokens"] for x in res[k]) for k in res}
        viol = {k: sum(len(x["violations"]) for x in res[k]) for k in res}
        bad = cov["selected"] < cov["whole"] - 1e-9 or viol["selected"] > viol["whole"]
        worse += bad
        print(f"{case['id']:<10} coverage {cov['whole']:.2f} -> {cov['selected']:.2f}   input tokens "
              f"{tok['whole']:,.0f} -> {tok['selected']:,.0f} ({(tok['selected'] - tok['whole']) * 100 / max(1, tok['whole']):+.0f}%)"
              f"   {'WORSE' if bad else 'ok'}")
        rows.append({"id": case["id"], "coverage": cov, "input_tokens": tok, "violations": viol, "worse": bad,
                     "tries": res})
    print(f"\ncases worse: {worse}")
    if a.out:
        Path(a.out).write_text(json.dumps({"model": a.model, "provider": a.provider, "repeat": a.repeat, "cases": rows},
                                          ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"written: {a.out}")
    return 1 if worse else 0


if __name__ == "__main__":
    raise SystemExit(main())
