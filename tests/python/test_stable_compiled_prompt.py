"""The token-saving (compiled) prompt of the Claude Code lane stays the same between new chats (#1329).

    python tests/run.py stable_compiled_prompt      (no network)

Field report 0.526.1 (issue #1329, a regression of #975): at a token-saving level the Claude Code lane does not send
`build_system_prompt` as is. It goes through `context_compiler._compile`, which put a clock with minute precision about
1,200 characters into the system prompt and appended the whole regular prompt AFTER it, followed by blocks that change
with every message (conversation state, retrieved memory, the selected skill). Claude Code caches the appended prompt
as ONE block, so every new chat rewrote about 25k tokens of cache instead of reading them.

With `stable_system=True` the compiled prompt:
1. carries the stable clock note instead of the time;
2. holds only the base contract and the legacy base, byte-identical across chats, times and questions;
3. hands the per-turn blocks back in `turn_context`, and nothing is lost: stable part + turn context is the full prompt;
4. is unchanged for every other caller (default `stable_system=False`).
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import os
import sys
import tempfile
from pathlib import Path

SCRATCH = Path(tempfile.mkdtemp(prefix="javis-stable-compiled-"))
os.environ["JAVIS_STATE_DIR"] = str(SCRATCH / "state")
os.environ["JAVIS_NO_REAL_JUDGE_ENGINE"] = "1"
os.environ["JAVIS_NO_REAL_REVIEW_ENGINE"] = "1"

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import context_compiler  # noqa: E402
from adaptive_context_runtime import AdaptiveContextCanary  # noqa: E402
from capability_registry import CapabilityRegistry  # noqa: E402
from context_compiler import CompileRequest, ContextCompiler, ContextItem  # noqa: E402
from context_runtime import ObserveRuntime  # noqa: E402

fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (f"  [{extra}]" if extra and not cond else ""))
    if not cond:
        fails.append(name)


def first_diff(a, b):
    return next((f"first diff at {i}: {a[i:i + 60]!r} vs {b[i:i + 60]!r}"
                 for i in range(min(len(a), len(b))) if a[i] != b[i]), "length")


CLOCK = {"now": "Bây giờ là 09:01 Thứ Hai 02/11/2026."}
context_compiler.dong_ho = lambda now=None, lang="": CLOCK["now"]

registry = CapabilityRegistry(SCRATCH / "state")
compiler = ContextCompiler(registry)
BASE = "Javis base contract. " + "luật hành xử " * 400


def item(item_id, kind, content, required=False):
    return ContextItem(id=item_id, kind=kind, content=content, source_ref="test:" + item_id,
                       token_cost=len(content) // 3, relevance=1.0, confidence=1.0, authority=1.0,
                       freshness=1.0, required=required, trust="system")


def compile_prompt(objective, memory, stable):
    result = compiler.compile_canary(CompileRequest(
        task_id="t-" + objective[:8], step_id="s", objective=objective, brain=str(SCRATCH / "brain"),
        channel="dashboard", provider="anthropic-cli", model="fable", model_kind="cli",
        hard_max_input_tokens=200000, rolling_tpm_remaining=200000, reserved_output_tokens=1000,
        execution_mode="canary",
        context_items=(item("source_fallback_contract", "source_fallback_contract", BASE, required=True),
                       item("conversation_state", "conversation_state", "Đang bàn: " + objective, required=True),
                       item("mem-1", "retrieved_memory", memory)),
        stable_system=stable, stable_context_ids=("source_fallback_contract",),
    ), {"selected": [], "selected_count": 0, "candidate_count": 0, "miss_class": ""})
    assert result.status == "compiled", result.trace_report
    system = next(x["content"] for x in result.capsule.rendered_request["messages"] if x["role"] == "system")
    return result.capsule, system


# ---- 1. the compiler: stable part identical, per-turn part handed back ----
cap_a, full_a = compile_prompt("Doanh thu tuần này thế nào?", "Khách Acme thích báo cáo ngắn.", True)
CLOCK["now"] = "Bây giờ là 23:59 Chủ Nhật 08/11/2026."
cap_b, full_b = compile_prompt("Viết giúp anh email chào hàng", "Email mẫu nằm ở thư mục sales.", True)
check("stable part is byte-identical across two chats, times and questions",
      cap_a.stable_system == cap_b.stable_system and bool(cap_a.stable_system),
      first_diff(cap_a.stable_system, cap_b.stable_system))
check("no clock time in the stable part", "09:01" not in cap_a.stable_system and "23:59" not in cap_b.stable_system)
check("the stable clock note is there", context_compiler.STABLE_CLOCK_NOTE in cap_a.stable_system)
check("the legacy base is in the stable part", BASE.strip() in cap_a.stable_system)
check("per-turn blocks are NOT in the stable part",
      "Đang bàn:" not in cap_a.stable_system and "Khách Acme" not in cap_a.stable_system)
check("per-turn blocks come back in turn_context",
      "Đang bàn: Doanh thu tuần này" in cap_a.turn_context and "Khách Acme thích báo cáo ngắn." in cap_a.turn_context
      and "Email mẫu nằm ở thư mục sales." in cap_b.turn_context)
check("turn_context keeps the block headings the model reads",
      "# Context: conversation_state" in cap_a.turn_context and "# Context: retrieved_memory" in cap_a.turn_context)
check("nothing is lost: every block of the full prompt is in one of the two parts",
      all(block in cap_a.stable_system or block in cap_a.turn_context
          for block in full_a.split("\n\n# Context: ")[1:]))
check("the budget still counts the per-turn blocks (they stay in the rendered request)",
      "Khách Acme" in full_a and "Đang bàn:" in full_a)

# ---- 2. every other caller is unchanged ----
CLOCK["now"] = "Bây giờ là 10:10 Thứ Ba 03/11/2026."
cap_c, full_c = compile_prompt("Doanh thu tuần này thế nào?", "Khách Acme thích báo cáo ngắn.", False)
check("default request still carries the clock", "10:10" in full_c and context_compiler.STABLE_CLOCK_NOTE not in full_c)
check("default request fills neither new field", cap_c.stable_system == "" and cap_c.turn_context == "")
check("default request keeps every block in the system prompt", "Khách Acme" in full_c and "Đang bàn:" in full_c)
check("CompileRequest defaults to the old behaviour",
      CompileRequest("t", "s", "o", "b", "dashboard", "p", "m").stable_system is False)

# ---- 3. the adaptive runtime hands out the stable prompt and the turn context ----
SETTINGS = {"context_runtime": {
    "mode": "canary",
    "context_sources": {"quota_profiles": [{
        "id": "test", "provider": "anthropic-cli", "model_pattern": "*",
        "rolling_tpm": 200000, "max_input_tokens": 150000, "reserved_output_tokens": 1000}]},
    "conversation_state_canary": {"policy_version": "s-test", "salt": "s", "channels": ["dashboard"],
                                  "provider_kinds": ["cli"], "allocation_basis_points": 10_000},
    "memory_canary": {"policy_version": "m-test", "salt": "m", "channels": ["dashboard"],
                      "provider_kinds": ["cli"], "allocation_basis_points": 0},
    "lazy_skill_canary": {"policy_version": "k-test", "salt": "k", "channels": ["dashboard"],
                          "provider_kinds": ["cli"], "allocation_basis_points": 0},
}}
runtime = ObserveRuntime(SCRATCH / "state", settings_reader=lambda: SETTINGS)
canary = AdaptiveContextCanary(SCRATCH / "state", registry, compiler, runtime, lambda: SETTINGS)
brain = SCRATCH / "brain"
brain.mkdir(parents=True, exist_ok=True)


def plan_for(session, question, stable):
    return canary.prepare(None, question, brain, session, [{"id": 1, "role": "user", "content": question}],
                          "dashboard", "anthropic-cli", "fable", "cli", lambda mem, skills: BASE,
                          stable_system=stable)


CLOCK["now"] = "Bây giờ là 08:00 Thứ Tư 04/11/2026."
p1 = plan_for("sess-aaa", "Doanh thu tuần này thế nào?", True)
CLOCK["now"] = "Bây giờ là 21:30 Thứ Năm 05/11/2026."
p2 = plan_for("sess-bbb", "Viết giúp anh email chào hàng", True)
check("the plan is used", p1.action == "use" and p2.action == "use", (p1.reason, p2.reason))
check("two new chats get the SAME system prompt from the token-saving path",
      p1.system_prompt == p2.system_prompt and bool(p1.system_prompt), first_diff(p1.system_prompt, p2.system_prompt))
check("that system prompt has no clock time", "08:00" not in p1.system_prompt and "21:30" not in p2.system_prompt)
check("the conversation state of each chat is in its turn_context, not in the system prompt",
      bool(p1.turn_context) and bool(p2.turn_context) and p1.turn_context != p2.turn_context
      and "# Context: conversation_state" in p1.turn_context
      and "# Context: conversation_state" not in p1.system_prompt)
p3 = plan_for("sess-ccc", "Doanh thu tuần này thế nào?", False)
check("without stable_system the plan is as before: clock and state in the system prompt, no turn_context",
      p3.action == "use" and "21:30" in p3.system_prompt and "# Context: conversation_state" in p3.system_prompt
      and p3.turn_context == "")

# ---- 4. the Claude Code lane uses both halves ----
SRC = (Path(SERVER) / "main.py").read_text(encoding="utf-8")
check("the subscription prompt asks the compiled path for a stable system prompt",
      "stable_system=stable," in SRC)
check("the Claude Code lane hands its prompt to _with_turn_context, before the turn facts header goes on top",
      "_cli_prompt, sysprompt = _with_turn_context(cli, _sub_plan, _cli_prompt, sysprompt)" in SRC
      and SRC.index("_with_turn_context(cli, _sub_plan") < SRC.index('_cli_prompt = _hdr + "\\n" + _cli_prompt'))


class FakeCli:
    def __init__(self, session_id=None):
        self.session_id = session_id
        self.system_prompt = "SYS"


class FakePlan:
    turn_context = "# Context: retrieved_memory\nKhách Acme thích báo cáo ngắn."


import main  # noqa: E402

prompt, system = main._with_turn_context(FakeCli(), FakePlan(), "Doanh thu tuần này?", "SYS")
check("first message of a thread: the turn context opens it, the system prompt is untouched",
      prompt == FakePlan.turn_context + "\n\nDoanh thu tuần này?" and system == "SYS")
prompt, system = main._with_turn_context(FakeCli("thread-1"), FakePlan(), "Còn tuần trước?", "SYS")
check("a resumed thread gets nothing added", prompt == "Còn tuần trước?" and system == "SYS")
prompt, system = main._with_turn_context(FakeCli(), None, "Xin chào", "SYS")
check("no plan (legacy prompt): nothing added", prompt == "Xin chào" and system == "SYS")
blocks = [{"type": "text", "text": "ảnh này là gì"}]
cli = FakeCli()
prompt, system = main._with_turn_context(cli, FakePlan(), blocks, "SYS")
check("a prompt that is not plain text keeps the context in the system prompt for that turn",
      prompt is blocks and system == "SYS\n\n" + FakePlan.turn_context and cli.system_prompt == system)
check("main and the compiler share one clock note",
      "_STABLE_CLOCK_NOTE = context_compiler.STABLE_CLOCK_NOTE" in SRC)

print()
if fails:
    print(f"FAIL: {len(fails)} check(s)")
    sys.exit(1)
print("All checks passed.")
