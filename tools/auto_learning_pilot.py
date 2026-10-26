"""Real-model pilot of automatic learning from chat (server/auto_learning.py) on a temp brain.

A door shop's quote skill misses three shop conventions (8% VAT, a 30% deposit on the total after VAT, delivery fee
200.000 below 5.000.000 before VAT). Chat turns are produced by the real model with the current skill; the owner's
next message corrects what was missed. Then the real pipeline runs: judge, case writer, Harness² loop with a model
grader, apply. A fixed hand-written check on fresh requests (deterministic numbers, never seen by Javis) measures the
skill before and after.

    python tools/auto_learning_pilot.py --out <dir> [--model claude-opus-5-5] [--effort medium]
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "server"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import auto_learning as A  # noqa: E402
from self_learning_pilot import CliEngine  # noqa: E402

SKILL = """---
name: bao-gia-cua
description: Viết báo giá cửa cho khách của cửa hàng
group: Sales
---
Khi khách hỏi giá, viết báo giá ngắn gọn bằng tiếng Việt:
- Liệt kê từng sản phẩm: tên, số lượng, đơn giá, thành tiền.
- Ghi tổng cộng.
- Lời chào lịch sự ở cuối.
"""

PRICES = {"cửa gỗ": 3_500_000, "cửa nhôm": 2_200_000, "cửa sắt": 1_800_000, "khoá cửa": 450_000}


def expected(items):
    sub = sum(PRICES[n] * q for n, q in items)
    vat = round(sub * 0.08)
    ship = 0 if sub >= 5_000_000 else 200_000
    total = sub + vat + ship
    return {"sub": sub, "vat": vat, "ship": ship, "total": total, "deposit": round(total * 0.3)}


def request_text(items):
    lines = ", ".join(f"{q} {n} (giá {PRICES[n]:,}đ/cái)".replace(",", ".") for n, q in items)
    return f"Báo giá giúp em: {lines}. Giao trong nội thành."


CHAT = [  # (items, owner's correction)
    ([("cửa gỗ", 2)], "Sai rồi em, báo giá cửa hàng mình luôn phải cộng VAT 8% và ghi tiền cọc 30% trên tổng sau VAT."),
    ([("cửa sắt", 1), ("khoá cửa", 2)], "Thiếu phí giao 200.000đ vì đơn dưới 5 triệu, và chưa có VAT 8% với cọc 30%."),
    ([("cửa nhôm", 3)], "Em lại quên VAT 8% rồi, cọc 30% nữa. Làm lại giúp anh."),
    ([("cửa sắt", 2)], "Đơn này dưới 5 triệu thì phải cộng phí giao 200.000đ, rồi VAT 8% và cọc 30% chứ em."),
]
FRESH = [[("cửa gỗ", 1)], [("cửa nhôm", 1), ("khoá cửa", 1)], [("cửa gỗ", 3), ("khoá cửa", 3)],
         [("cửa sắt", 1)], [("cửa nhôm", 2), ("cửa sắt", 1)], [("khoá cửa", 4)]]


def numbers(text: str) -> set:
    return {int(re.sub(r"[.,\s]", "", m)) for m in re.findall(r"\d{1,3}(?:[.,\s]\d{3})+|\d{4,}", text)}


def fixed_check(answer: str, items) -> dict:
    e, got = expected(items), numbers(answer)
    marks = {"vat": e["vat"] in got, "total": e["total"] in got, "deposit": e["deposit"] in got,
             "ship": (e["ship"] == 0) or (200_000 in got)}
    return {"pass": all(marks.values()), **marks}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--model", default="claude-opus-5-5")
    ap.add_argument("--effort", default="medium")
    ap.add_argument("--background-model", default="", help="model for judge/writer/grader/improver (default: --model)")
    args = ap.parse_args()
    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    engine = CliEngine(args.model, args.effort)
    background = CliEngine(args.background_model, args.effort) if args.background_model else engine
    tmp = Path(tempfile.mkdtemp(prefix="javis-auto-learning-"))
    brain = tmp / "brain"
    (brain / "skills" / "bao-gia-cua").mkdir(parents=True)
    (brain / "workflows").mkdir()
    skill_path = brain / "skills" / "bao-gia-cua" / "SKILL.md"
    skill_path.write_text(SKILL, encoding="utf-8")
    clock = [time.time()]
    host = A.Host(text_call=engine._call, background_call=background._call, engine_ready=lambda b: None, policy_on=lambda b: True,
                  skill_protected=lambda b, s: False, workflows_dir=lambda b: Path(b) / "workflows",
                  agent_text=lambda b, s: "", agent_procedure=lambda b, s: {}, agent_apply=lambda b, s, t: {},
                  agent_undo=lambda b, i: None, backups=tmp / "backups")
    learner = A.AutoLearner(A.Store(tmp / "al.sqlite3"), host, clock=lambda: clock[0], width=3)
    b = str(brain)

    def answer_with(skill_text, items):
        body = A.split_frontmatter(skill_text)[1]
        return engine._call("You are a Javis assistant. Follow the skill below.\n\n<skill>\n" + body + "\n</skill>",
                            request_text(items))

    log = {"model": args.model, "effort": args.effort, "started": time.strftime("%Y-%m-%d %H:%M")}
    before = [fixed_check(answer_with(SKILL, items), items) for items in FRESH]
    log["fixed_before"] = before
    for i, (items, correction) in enumerate(CHAT):
        session = f"chat-{i}"
        clock[0] += 60  # the owner reads the answer before writing back
        learner.note_skill_use(b, session, "bao-gia-cua")
        learner.observe_turn(b, session, "web", request_text(items), answer_with(SKILL, items), i + 1)
        clock[0] += 60
        learner.observe_turn(b, session, "web", correction, "Dạ em làm lại ạ.", i + 100)
    while learner.judge_ready():
        pass
    log["judged"] = learner.store.read("SELECT verdict, COUNT(*) AS n FROM episodes GROUP BY verdict")
    log["mistakes"] = learner.store.read("SELECT what, right_way, case_prompt, criteria FROM mistakes")
    started = time.time()
    run = learner.step()
    log["run"] = run
    log["run_seconds"] = round(time.time() - started)
    log["history"] = learner.history(b)
    after_text = skill_path.read_text(encoding="utf-8")
    log["skill_after"] = after_text
    log["fixed_after"] = [fixed_check(answer_with(after_text, items), items) for items in FRESH]
    log["usage"] = {**{k: v for k, v in engine.usage.items() if k != "models"}, "models": sorted(engine.usage["models"])}
    if background is not engine:
        log["usage_background"] = {**{k: v for k, v in background.usage.items() if k != "models"},
                                   "models": sorted(background.usage["models"])}
        log["usage_total_cost_usd"] = round(engine.usage["cost_usd"] + background.usage["cost_usd"], 4)
    (out / "result.json").write_text(json.dumps(log, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    shutil.copy(tmp / "al.sqlite3", out / "al.sqlite3")
    print(json.dumps({"run": run, "fixed_before": sum(x["pass"] for x in before),
                      "fixed_after": sum(x["pass"] for x in log["fixed_after"]), "usage": log["usage"],
                      "usage_background": log.get("usage_background"), "total_cost": log.get("usage_total_cost_usd"),
                      "judged": log["judged"]}, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
