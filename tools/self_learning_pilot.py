"""Real-model pilot of the self-learning loop (server/improvement_loop.py) on one business skill.

Task: reconcile a shop's orders with bank transfers under the shop's own conventions. The cases are synthetic
fixtures with answers built by construction (no live account or customer data). The baseline skill knows the
output format and the obvious rule (match code and amount) but not the shop's conventions, which the loop must
learn from tuning feedback and which the sealed qualification cases test in new combinations:

  R1 order codes appear in memos in loose forms (dh-1023, "don 1023");
  R2 amounts may be written 1.250.000d, 1250k, 1,25tr;
  R3 carrier COD transfers (GHTK, GHN, Viettel Post) arrive minus a fee up to 30.000: still settled;
  R4 one transfer may pay several orders listed in its memo when the amount equals their sum;
  R5 several transfers for one order are summed;
  R6 refund lines (negative amount) are ignored;
  R7 any other difference is an amount mismatch.

Engine: the brain's selected Claude Code CLI in print mode with every customisation off (`--safe-mode`), no tools
(`--tools ""`), no session persistence, a pilot-only system prompt, in an empty working directory. Nothing is
installed; the user's existing sign-in is used.

Usage: python tools/self_learning_pilot.py --out <dir> [--model M --effort E --k 1 --width 4] [--dry]
"""
from __future__ import annotations

import argparse
import json
import random
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))
import improvement_loop as L  # noqa: E402

CARRIERS = ("GHTK COD", "GHN COD", "Viettel Post COD")
NAMES = ("Lan", "Minh", "Hoa", "Tuan", "Mai", "Khang", "Thu", "Long", "Nga", "Phuc", "Vy", "Son", "Ha", "Quang")

BASE_SKILL = """# Doi soat don hang voi giao dich ngan hang

Muc tieu: cho danh sach don hang va danh sach giao dich ngan hang, xac dinh don nao da duoc thanh toan.

Cach lam:
1. Voi moi giao dich, tim ma don hang trong noi dung chuyen khoan.
2. Neu tim thay ma don va so tien bang so tien don: don do da khop.
3. Neu tim thay ma don nhung so tien khac: ghi vao lech tien.
4. Don khong co giao dich nao: chua thanh toan.
5. Giao dich khong khop don nao: giao dich la.

Tra ve DUY NHAT mot JSON:
{"da_khop": [ma don], "chua_thanh_toan": [ma don], "lech_tien": [{"ma": ma don, "can_thu": so, "da_nhan": so}], "giao_dich_la": [ma giao dich]}
So tien la so nguyen VND, khong dau cham.
"""


def fmt_amount(rng, value: int, loose: bool) -> str:
    if not loose:
        return f"{value:,}".replace(",", ".")
    choice = rng.choice(("dot_d", "k", "tr"))
    if choice == "dot_d":
        return f"{value:,}".replace(",", ".") + "d"
    if choice == "k" and value % 1000 == 0:
        return f"{value // 1000}k"
    if value % 10000 == 0:
        return (f"{value / 1_000_000:.2f}".rstrip("0").rstrip(".") + "tr").replace(".", ",")
    return f"{value:,}".replace(",", ".") + "d"


class Builder:
    """Builds one case: orders, payments and the answer by construction."""

    def __init__(self, rng, fees=None):
        self.rng, self.orders, self.payments, self.fees = rng, [], [], fees
        self.ans = {"da_khop": set(), "chua_thanh_toan": set(), "lech_tien": set(), "giao_dich_la": set()}
        self.codes = rng.sample(range(1001, 9999), 12)

    def order(self):
        code = f"DH{self.codes.pop()}"
        amount = self.rng.randrange(150, 3000) * 1000
        self.orders.append((code, self.rng.choice(NAMES), amount))
        return code, amount

    def pay(self, sender, memo, amount, loose=False):
        pid = f"GD{len(self.payments) + 1:02d}"
        self.payments.append((pid, sender, memo, fmt_amount(self.rng, amount, loose) if amount >= 0
                              else "-" + fmt_amount(self.rng, -amount, False)))
        return pid

    def memo(self, code, loose=False):
        if not loose:
            return f"{code} {self.rng.choice(NAMES)} chuyen khoan"
        digits = code[2:]
        return self.rng.choice((f"dh-{digits} thanh toan", f"tt don {digits}", f"Dh {digits} ck"))

    # -- twists ---------------------------------------------------------------------------------------------
    def plain(self, loose_code=False, loose_amount=False):
        code, amount = self.order()
        self.pay(self.rng.choice(NAMES), self.memo(code, loose_code), amount, loose_amount)
        self.ans["da_khop"].add(code)

    def code_format(self):
        self.plain(loose_code=True)

    def amount_format(self):
        self.plain(loose_amount=True)

    def cod_fee(self):
        code, amount = self.order()
        # Design 2: tuning cycles through fees, so the evidence shows the convention is "up to 30.000".
        fee = next(self.fees) if self.fees is not None else self.rng.choice((15000, 20000, 22000, 25000, 30000))
        self.pay(self.rng.choice(CARRIERS), f"COD {code}", amount - fee)
        self.ans["da_khop"].add(code)

    def cod_fee_too_big(self):
        code, amount = self.order()
        fee = self.rng.choice((45000, 60000, 80000))
        self.pay(self.rng.choice(CARRIERS), f"COD {code}", amount - fee)
        self.ans["lech_tien"].add((code, amount, amount - fee))

    def combined(self):
        (c1, a1), (c2, a2) = self.order(), self.order()
        self.pay(self.rng.choice(NAMES), f"{c1} {c2} gop", a1 + a2)
        self.ans["da_khop"].update((c1, c2))

    def split(self):
        code, amount = self.order()
        first = (amount // 2000) * 1000
        self.pay(self.rng.choice(NAMES), f"{code} lan 1", first)
        self.pay(self.rng.choice(NAMES), f"{code} lan 2", amount - first)
        self.ans["da_khop"].add(code)

    def split_short(self):
        code, amount = self.order()
        first, second = (amount // 3000) * 1000, (amount // 3000) * 1000
        self.pay(self.rng.choice(NAMES), f"{code} coc", first)
        self.pay(self.rng.choice(NAMES), f"{code} tra them", second)
        self.ans["lech_tien"].add((code, amount, first + second))

    def refund(self):
        code, amount = self.order()
        self.pay(self.rng.choice(NAMES), f"{code} chuyen khoan", amount)
        self.pay("Shop", f"hoan tien {code} doi hang", -self.rng.randrange(50, 200) * 1000)
        self.ans["da_khop"].add(code)

    def overpay(self):
        code, amount = self.order()
        extra = self.rng.choice((10000, 50000, 100000))
        self.pay(self.rng.choice(NAMES), f"{code} chuyen khoan", amount + extra)
        self.ans["lech_tien"].add((code, amount, amount + extra))

    def unpaid(self):
        code, _amount = self.order()
        self.ans["chua_thanh_toan"].add(code)

    def unknown(self):
        pid = self.pay(self.rng.choice(NAMES), self.rng.choice(("ung ho quy", "chuyen tien", "tra no cu")),
                       self.rng.randrange(50, 900) * 1000)
        self.ans["giao_dich_la"].add(pid)

    def render(self):
        self.rng.shuffle(self.orders)
        self.rng.shuffle(self.payments)
        lines = ["Danh sach don hang:", "| Ma don | Khach | So tien |", "|---|---|---|"]
        lines += [f"| {c} | {n} | {f'{a:,}'.replace(',', '.')} |" for c, n, a in self.orders]
        lines += ["", "Giao dich ngan hang:", "| Ma GD | Nguoi chuyen | Noi dung | So tien |", "|---|---|---|---|"]
        lines += [f"| {p} | {s} | {m} | {a} |" for p, s, m, a in self.payments]
        lines += ["", "Hay doi soat va tra ve JSON dung dinh dang trong skill."]
        answer = {"da_khop": sorted(self.ans["da_khop"]), "chua_thanh_toan": sorted(self.ans["chua_thanh_toan"]),
                  "lech_tien": sorted([{"ma": c, "can_thu": a, "da_nhan": r} for c, a, r in self.ans["lech_tien"]],
                                      key=lambda x: x["ma"]),
                  "giao_dich_la": sorted(self.ans["giao_dich_la"])}
        return "\n".join(lines), answer


TUNING = [("cod_fee", "unpaid"), ("combined", "amount_format"), ("split", "unknown"), ("refund", "overpay"),
          ("code_format", "cod_fee_too_big"), ("split_short", "plain"), ("combined", "refund"), ("cod_fee", "split")]
QUALIFICATION = [("cod_fee", "combined"), ("cod_fee", "refund"), ("cod_fee", "overpay"), ("combined", "split"),
                 ("combined", "unknown"), ("refund", "split_short"), ("code_format", "refund"),
                 ("amount_format", "split"), ("cod_fee_too_big", "combined"), ("split_short", "unknown"),
                 ("code_format", "overpay"), ("amount_format", "cod_fee", "unpaid"), ("combined", "refund", "split"),
                 ("cod_fee", "split_short"), ("code_format", "combined", "overpay"),
                 ("amount_format", "refund", "unknown")]


# Design 2 (pre-registered after pilot 1, before any run of it): fresh data from a new seed, tuning fees varied,
# a larger sealed set (24). The decision rule (sign test, p < 0.05) and k are unchanged.
TUNING_V2 = [("cod_fee", "unpaid"), ("amount_format", "cod_fee"), ("amount_format", "combined"), ("split", "unknown"),
             ("overpay", "refund"), ("code_format", "cod_fee_too_big"), ("plain", "split_short"), ("combined", "refund"),
             ("cod_fee", "split"), ("overpay", "unknown")]
QUALIFICATION_V2 = QUALIFICATION + [("cod_fee", "code_format"), ("cod_fee_too_big", "refund"), ("overpay", "split"),
                                    ("combined", "split_short"), ("cod_fee", "unknown"), ("amount_format", "overpay"),
                                    ("code_format", "split"), ("cod_fee_too_big", "split")]


def build_cases(seed: int = 26102026, design: int = 1) -> list:
    rng = random.Random(seed)
    out = []
    tuning, qualification = (TUNING, QUALIFICATION) if design == 1 else (TUNING_V2, QUALIFICATION_V2)
    import itertools
    tuning_fees = itertools.cycle((15000, 22000, 30000, 18000, 25000)) if design == 2 else None
    for split, combos in (("tuning", tuning), ("qualification", qualification)):
        for index, combo in enumerate(combos):
            b = Builder(rng, tuning_fees if split == "tuning" else None)
            for twist in combo:
                getattr(b, twist)()
            for _ in range(rng.choice((1, 2))):
                b.plain()  # ordinary rows around the twists
            prompt, answer = b.render()
            out.append(L.Case(f"{split[0]}{index + 1:02d}", "+".join(sorted(combo)), split, prompt, answer))
    return out


def parse_output(text: str):
    text = text.strip()
    if "```" in text:
        text = text.split("```")[1]
        text = text[4:] if text.startswith("json") else text
    start, end = text.find("{"), text.rfind("}")
    return json.loads(text[start:end + 1])


def check(case, output) -> dict:
    try:
        got = parse_output(output)
        norm = {"da_khop": sorted(set(map(str, got.get("da_khop") or []))),
                "chua_thanh_toan": sorted(set(map(str, got.get("chua_thanh_toan") or []))),
                "lech_tien": sorted([{"ma": str(x.get("ma")), "can_thu": int(x.get("can_thu")), "da_nhan": int(x.get("da_nhan"))}
                                     for x in (got.get("lech_tien") or [])], key=lambda x: x["ma"]),
                "giao_dich_la": sorted(set(map(str, got.get("giao_dich_la") or [])))}
    except Exception as error:  # noqa: BLE001
        return {"pass": False, "score": 0.0, "feedback": f"output is not the required JSON ({type(error).__name__})"}
    right = [k for k in case.answer if norm[k] == case.answer[k]]
    wrong = [f"{k}: expected {case.answer[k]}, got {norm[k]}" for k in case.answer if k not in right]
    return {"pass": not wrong, "score": len(right) / 4, "feedback": "all fields correct" if not wrong else "; ".join(wrong)}


class CliEngine:
    """The selected Claude Code CLI, print mode, no tools, no customisations, empty working directory."""

    def __init__(self, model: str, effort: str, timeout: int = 240):
        self.model, self.effort, self.timeout = model, effort, timeout
        self.cwd = Path(tempfile.mkdtemp(prefix="javis-pilot-"))
        self.usage = {"calls": 0, "cost_usd": 0.0, "models": set(), "errors": 0}
        self.binary = shutil.which("claude") or "claude"  # claude.exe / claude.cmd on Windows
        self.lock = threading.Lock()

    def _call(self, system: str, prompt: str) -> str:
        command = [self.binary, "-p", "--safe-mode", "--tools", "", "--no-session-persistence", "--model", self.model,
                   "--effort", self.effort, "--output-format", "json", "--system-prompt", system]
        done = subprocess.run(command, input=prompt, capture_output=True, text=True, encoding="utf-8",
                              cwd=self.cwd, timeout=self.timeout)
        data = json.loads(done.stdout)
        with self.lock:  # four worker threads share these counters
            self.usage["calls"] += 1
            self.usage["cost_usd"] += float(data.get("total_cost_usd") or 0)
            self.usage["models"].update((data.get("modelUsage") or {}).keys())
            if data.get("is_error"):
                self.usage["errors"] += 1
        if data.get("is_error"):
            raise RuntimeError(str(data.get("result"))[:200])
        return str(data.get("result") or "")

    def solve(self, skill: str, prompt: str) -> str:
        system = ("Ban la tro ly Javis cua mot cua hang. Lam dung theo skill duoi day.\n\n<skill>\n" + skill +
                  "\n</skill>\n\nChi tra ve JSON, khong giai thich.")
        return self._call(system, prompt)

    def improve(self, instructions: str) -> str:
        return self._call("You improve skills for the Javis assistant. Write the skill in Vietnamese without "
                          "diacritics, like the current one.", instructions)


def oracle_solve(case_by_prompt):
    def solve(skill, prompt):
        return json.dumps(case_by_prompt[prompt].answer, ensure_ascii=False)
    return solve


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--model", default="claude-opus-5-5")
    ap.add_argument("--effort", default="medium")
    ap.add_argument("--k", type=int, default=1)
    ap.add_argument("--width", type=int, default=4)
    ap.add_argument("--dry", action="store_true", help="oracle solver, no model call (checks data and checker)")
    ap.add_argument("--seed", type=int, default=26102026)
    ap.add_argument("--design", type=int, choices=(1, 2), default=1)
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    cases = build_cases(args.seed, args.design)
    (out / "cases.json").write_text(json.dumps([{"id": c.id, "family": c.family, "split": c.split, "prompt": c.prompt,
                                                 "answer": c.answer} for c in cases], ensure_ascii=False, indent=1),
                                    encoding="utf-8")
    events = (out / "events.jsonl").open("a", encoding="utf-8")

    def on_event(kind, data):
        events.write(json.dumps({"at": time.time(), "kind": kind, **data}, ensure_ascii=False) + "\n")
        events.flush()
        print(kind, data, flush=True)
    if args.dry:
        by_prompt = {c.prompt: c for c in cases}
        bad = [c.id for c in cases if not check(c, json.dumps(c.answer))["pass"]]
        print("checker self-test failures:", bad)
        loop = L.Loop(cases, solve=oracle_solve(by_prompt), improve=lambda text: "no", check=check, on_event=on_event)
        result = loop.run(BASE_SKILL, k=args.k)
        usage = {"calls": 0}
    else:
        engine = CliEngine(args.model, args.effort)
        loop = L.Loop(cases, solve=engine.solve, improve=engine.improve, check=check, width=args.width,
                      on_event=on_event)
        started = time.time()
        result = loop.run(BASE_SKILL, k=args.k, qualification_repeats=2)
        usage = {**engine.usage, "models": sorted(engine.usage["models"]), "seconds": round(time.time() - started)}
    for label, text in result.versions.items():
        (out / f"skill-{label}.md").write_text(text, encoding="utf-8")
    (out / "qualification.jsonl").write_text("\n".join(json.dumps(r.__dict__, ensure_ascii=False)
                                                        for r in result.qualification), encoding="utf-8")
    summary = {**result.to_dict(), "usage": usage, "model": args.model, "effort": args.effort, "k": args.k,
               "seed": args.seed, "design": args.design,
               "cases": {"tuning": sum(c.split == "tuning" for c in cases),
                         "qualification": sum(c.split == "qualification" for c in cases)}}
    (out / "result.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: summary[k] for k in ("chosen", "tuning", "report", "usage")}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
