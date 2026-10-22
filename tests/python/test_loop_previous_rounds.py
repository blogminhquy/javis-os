"""Regression (customer report 0.270, Code 16): a loop round must see earlier rounds.

A Suggest loop told "suggest exactly 1 new wiki page, do not repeat earlier rounds" suggested the
same page on two runs one minute apart and wrote that it found no record of earlier rounds: each
round runs in a fresh session and its prompt carried nothing from the loop's own log. Now the
next round's prompt ends with a bounded tail of Javis/loop-log/ entries for that loop.

No Claude CLI, SDK or network: the engine is a fake that records the prompt it receives.

    python tests/python/test_loop_previous_rounds.py
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import os
import tempfile
from pathlib import Path

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-prevrounds-"))

import self_improve  # noqa: E402

_fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)


_BRAIN = tempfile.mkdtemp(prefix="javis-prevrounds-brain-")


def _atomic_write(path, text):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


deps = self_improve.LoopDeps(
    build_system_prompt=lambda brain: "SYS",
    brain_root=lambda brain: _BRAIN,
    aux_model=lambda: None,
    atomic_write_text=_atomic_write,
    project_root=Path("."),
    state_dir=Path(os.environ["JAVIS_STATE_DIR"]),
    safe_tools=["Read", "Write", "Edit", "Glob", "Grep"],
    readonly_tools=["Read", "Glob", "Grep", "LS"],
)
feat = self_improve.LoopFeature(deps)

prompts = []
answers = []


class FakeCli:
    max_wall_s = 0

    def is_available(self):
        return True

    async def query(self, prompt):
        prompts.append(prompt)
        yield {"type": "final", "content": answers.pop(0) if answers else ""}


feat._make_cli = lambda *a, **k: FakeCli()

SLUG = "goi-y-wiki"
OTHER = "loop-khac"


def _write_loop(slug, body):
    d = Path(_BRAIN) / "Javis" / "loops"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{slug}.md").write_text(
        f"---\nname: {slug}\ngoal: custom\nmode: suggest\nenabled: false\n---\n{body}\n", encoding="utf-8")


_write_loop(SLUG, "Đề xuất đúng 1 trang wiki mới, không lặp lại đề xuất của các vòng trước.")
_write_loop(OTHER, "Việc khác.")

# 1. First round: no earlier rounds, and the prompt says so plainly.
answers.append("Đề xuất: trang 'Quy định Khối Thực thi'.")
r1 = asyncio.run(feat.run_cycle("brain", SLUG, "manual"))
check("round 1 ran", r1.get("ok"))
check("round 1 prompt says there is no earlier round",
      "NHẬT KÝ CÁC VÒNG TRƯỚC" in prompts[0] and "vòng đầu tiên" in prompts[0])

# A round of another loop must not leak into this loop's tail.
answers.append("Đề xuất của loop khác: trang 'Bí mật'.")
asyncio.run(feat.run_cycle("brain", OTHER, "manual"))

# 2. Second round: the first round's suggestion is in the prompt.
answers.append("Đề xuất: trang 'Quy trình duyệt chi'.")
r2 = asyncio.run(feat.run_cycle("brain", SLUG, "manual"))
p2 = prompts[2]
check("round 2 ran", r2.get("ok"))
check("round 2 prompt carries round 1's suggestion", "Quy định Khối Thực thi" in p2)
check("round 2 prompt tells the model not to repeat it", "KHÔNG đề xuất hay làm lại" in p2)
check("round 2 prompt has no other loop's result", "Bí mật" not in p2)
check("round 2 prompt does not carry its own answer", "Quy trình duyệt chi" not in p2)

# 3. Third round: newest first, both earlier suggestions present.
answers.append("Đề xuất: trang 'Mẫu biên bản'.")
asyncio.run(feat.run_cycle("brain", SLUG, "manual"))
p3 = prompts[3]
check("round 3 sees both earlier rounds",
      "Quy định Khối Thực thi" in p3 and "Quy trình duyệt chi" in p3)
check("round 3 lists the newest round first",
      p3.index("Quy trình duyệt chi") < p3.index("Quy định Khối Thực thi"))

# 4. Failed rounds are skipped; the tail stays bounded however long the log grows.
answers.append("")  # empty answer = failed round, logged as "Lỗi: ..."
asyncio.run(feat.run_cycle("brain", SLUG, "manual"))
for i in range(8):
    answers.append(f"Đề xuất số {i}: " + ("x" * 3000))
    asyncio.run(feat.run_cycle("brain", SLUG, "manual"))
block = feat._previous_rounds_block("brain", SLUG)
check("tail is bounded in size",
      len(block) <= self_improve.PREV_ROUNDS_TOTAL_CHARS + 400)
check("tail keeps at most PREV_ROUNDS_MAX rounds",
      block.count("### Vòng ") <= self_improve.PREV_ROUNDS_MAX)
check("each round is cut short", "[...]" in block and "x" * 700 not in block)
check("failed rounds are left out", "Lỗi:" not in block)
check("newest round is in the tail", "Đề xuất số 7" in block)

# 5. No log on disk: fall back to the state's last summary.
import shutil  # noqa: E402
shutil.rmtree(Path(_BRAIN) / "Javis" / "loop-log")
fb = feat._previous_rounds_block("brain", SLUG)
check("without a log, the state's last summary is used", "Đề xuất số 7" in fb)

check("no em or en dash in the added prompt text",
      "\u2014" not in p2 and "\u2013" not in p2 and "\u2014" not in fb)

if _fails:
    raise SystemExit(f"{len(_fails)} check(s) failed")
print("all ok")
