"""The person's profile reaches the model at every token-saving level, on every route (#1349).

    python tests/run.py profile_every_saving_level      (no network)

Field report 0.541.0 (issue #1349): a rule written on the Profile page (`user_profile.md`, shared by every brain, at
most 4,000 characters) did not reach the model at the token-saving levels, the default one included. The profile is
a behaviour contract like CLAUDE.md, not a memory to retrieve, so no saving level may leave it out.

0.546.2 fixed the two prompt builders (`build_system_prompt` without the memory index, and
`build_adaptive_source_prompt`). Left open until this test: the capsules that REPLACE the prompt altogether. A
greeting takes the fast path at every level, a simple question takes it at "max", and on API engines the read-only
routes write their answer from a capsule too. None of them carried the profile.

Pinned here, for each level of `main.RUNTIME_PRESETS`:
1. a recognisable profile line is in the system prompt of every owner route: the regular prompt, the Claude Code
   lane, the API lane, and the fast path of both;
2. on the Claude Code lane it sits in the part that is cached (never in the per-turn context), once;
3. in a capsule it comes before the clock, so the head of the prompt is the same from one minute to the next;
4. the read-only routes carry it into the round that writes the answer, and not into the rounds that only plan or
   fill tool arguments;
5. it is required: a budget too small for it fails the compile instead of dropping it in silence;
6. an empty profile adds nothing anywhere: the block is the only difference between the two capsules.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import os
import sys
import tempfile
from pathlib import Path

STATE = tempfile.mkdtemp(prefix="javis-profile-levels-")
os.environ["JAVIS_STATE_DIR"] = STATE

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import context_compiler  # noqa: E402
import main  # noqa: E402
import memory_control  # noqa: E402
import test_readonly_orchestrator_phase7 as orchestrator_harness  # noqa: E402
import test_readonly_path_phase6 as readonly_harness  # noqa: E402
from context_compiler import CompileRequest  # noqa: E402
from starlette.testclient import TestClient  # noqa: E402

fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(extra)[:400] + "]") if extra and not cond else ""))
    if not cond:
        fails.append(name)


MARKER = "PROFILE-MARKER-1349: luôn gọi tôi là sếp Bảy."
HEADER = "HỒ SƠ NGƯỜI DÙNG (chung mọi brain"
CLOCK = {"now": "Bây giờ là 09:01 Thứ Hai 02/11/2026."}
context_compiler.dong_ho = lambda now=None, lang="": CLOCK["now"]

main.cfgmod.gate_active = lambda: False
client = TestClient(main.app, base_url="http://127.0.0.1")

BRAIN = Path(tempfile.mkdtemp(prefix="javis-profile-brain-"))
ROOT_OF_BRAIN = main._brain_root(str(BRAIN))
memory_dir = main._brain_memory_dir(str(BRAIN))
(memory_dir / "facts").mkdir(parents=True, exist_ok=True)
(memory_dir / "MEMORY.md").write_text(
    "# MEMORY\n- [Acme contact](facts/acme-contact.md) - email liên hệ của khách Acme\n", encoding="utf-8")
(memory_dir / "facts" / "acme-contact.md").write_text(
    "---\ntype: business\ncreated: 2026-11-01\nupdated: 2026-11-01\n---\n"
    "# Acme contact\nEmail liên hệ của khách hàng Acme: sales@acme.example.\n", encoding="utf-8")
main._CAPABILITY_REGISTRY.refresh_tools(ROOT_OF_BRAIN, [], {})

QUESTION = "Email liên hệ của Acme là gì?"
ENGINES = {
    # label: (provider, model, kind)
    "Claude Code": ("anthropic-cli", "claude-opus-5-5", "cli"),
    "API": ("groq", "llama-3.3-70b-versatile", "api"),
}


def system_of(messages) -> str:
    return "".join(str(m.get("content") or "") for m in messages or [] if m.get("role") == "system")


def regular_prompt() -> str:
    return main.build_system_prompt(str(BRAIN), stable=True)


def lane_prompt(engine: str, session: str):
    """The system prompt of one chat turn, built the way the owner lanes build it.

    Mirrors `_subscription_system_prompt` (Claude Code: the regular prompt as base, stable) and `_phase8_base` (API
    engines: the small adaptive base) in `main.py`. Returns (prompt, plan, flags the base builder was called with).
    """
    provider, model, kind = ENGINES[engine]
    flags = []

    def base(include_memory: bool, include_skills: bool) -> str:
        flags.append((include_memory, include_skills))
        if kind == "cli":
            return main.build_system_prompt(str(BRAIN), include_memory=include_memory,
                                            include_skills=include_skills, stable=True)
        return main.build_adaptive_source_prompt(str(BRAIN), include_memory=include_memory,
                                                 include_skills=include_skills, routing_overlays=True)

    plan = main._get_adaptive_context().prepare(
        None, QUESTION, ROOT_OF_BRAIN, session, [{"id": 1, "role": "user", "content": QUESTION}],
        "dashboard", provider, model, kind, base, stable_system=kind == "cli")
    if plan.action == "use" and plan.system_prompt:
        return plan.system_prompt, plan, flags
    return (regular_prompt() if kind == "cli" else main.build_system_prompt(str(BRAIN))), plan, flags


def fast_plan(engine: str, session: str, text: str):
    provider, model, kind = ENGINES[engine]
    trace = main._CONTEXT_RUNTIME.start_turn(session, ROOT_OF_BRAIN, "dashboard")
    trace.registry_revision = main._CAPABILITY_REGISTRY.revision(ROOT_OF_BRAIN)
    return main._FAST_PATH.prepare(trace, text, ROOT_OF_BRAIN, "dashboard", provider, model, kind, False, "", "")


def set_level(level: str) -> None:
    reply = client.post("/runtime/preset", data={"level": level})
    check(f"[{level}] the saving level is set", reply.status_code == 200 and reply.json().get("ok"), reply.text)
    check(f"[{level}] and it is the level in force",
          main.current_preset(main.cfgmod.read_settings().get("context_runtime") or {}) == level)


LEVELS = list(main.RUNTIME_PRESETS)
check("the three saving levels are the ones this test walks", set(LEVELS) == {"off", "saving", "max"}, LEVELS)

# ---- 1-3. every level, every owner route, with a profile ----
memory_control.write_profile(MARKER)
lean_builds = 0          # how many times a lane really built its base WITHOUT the memory index (the #1349 case)
compiled_levels = set()  # levels at which a lane really went through the compiler
fast_questions = 0
for level in LEVELS:
    set_level(level)
    prompt = regular_prompt()
    check(f"[{level}] regular prompt: the profile is there, once", MARKER in prompt and prompt.count(HEADER) == 1)

    for engine in ENGINES:
        prompt, plan, flags = lane_prompt(engine, f"profile-{level}-{engine}")
        check(f"[{level}] {engine} lane: the profile is in the system prompt",
              MARKER in prompt, (plan.action, plan.reason))
        check(f"[{level}] {engine} lane: the profile block appears once", prompt.count(HEADER) == 1,
              prompt.count(HEADER))
        if plan.action == "use":
            compiled_levels.add(level)
            lean_builds += sum(1 for include_memory, _ in flags if not include_memory)
            check(f"[{level}] {engine} lane: the profile is not in the per-turn context (it stays cached)",
                  MARKER not in plan.turn_context)
        if level == "off":
            check(f"[off] {engine} lane: nothing is compiled, the regular prompt is sent", plan.action == "legacy",
                  (plan.action, plan.reason))

        # A greeting takes the fast path whatever the level (0.345.0), and its capsule replaces the whole prompt.
        CLOCK["now"] = "Bây giờ là 09:01 Thứ Hai 02/11/2026."
        greeting = fast_plan(engine, f"hello-{level}-{engine}", "chào em")
        system = system_of(greeting.messages)
        check(f"[{level}] {engine} fast path: a greeting takes it", greeting.action == "execute",
              (greeting.action, greeting.reason))
        check(f"[{level}] {engine} fast path: the profile is in the capsule, once",
              MARKER in system and system.count(HEADER) == 1, system[:300])
        check(f"[{level}] {engine} fast path: the profile comes before the clock",
              0 < system.find(MARKER) < system.find(CLOCK["now"]), (system.find(MARKER), system.find(CLOCK["now"])))
        head = system[:system.find(CLOCK["now"])]
        CLOCK["now"] = "Bây giờ là 23:59 Chủ Nhật 08/11/2026."
        later = system_of(fast_plan(engine, f"hello-later-{level}-{engine}", "chào em").messages)
        check(f"[{level}] {engine} fast path: the head with the profile is the same a day later (cacheable)",
              MARKER in head and later.startswith(head) and "23:59" in later[len(head):])

        # A simple question that needs no lookup: the shortcut of the "max" level where the engine may use it.
        question = fast_plan(engine, f"simple-{level}-{engine}", "Giải thích ngắn gọn lãi kép là gì")
        if question.action == "execute":
            fast_questions += 1
            check(f"[{level}] {engine} fast path: a simple question carries the profile too",
                  MARKER in system_of(question.messages))
        if level != "max":
            check(f"[{level}] {engine}: a real question does not take the shortcut below 'max'",
                  question.action != "execute", (question.action, question.reason))

# The loop above must have exercised what the issue is about, or its checks prove nothing.
check("the saving levels really compiled a prompt", compiled_levels == {"saving", "max"}, compiled_levels)
check("a lane really built its base without the memory index (the case of the issue)", lean_builds > 0)
check("the shortcut of the 'max' level really ran for a simple question", fast_questions > 0)

# ---- 4. read-only routes (API engines): the answer round carries it, planning and argument rounds do not ----
EVIDENCE = {"evidence_ref": "evidence://task/t/step/s/ev_1", "source_type": "capability_read",
            "capability_id": "calendar_list", "capability_name": "calendar_list",
            "capability_revision": "r1", "content_hash": "0" * 64, "excerpt": "review at 09:00"}

scratch = Path(tempfile.mkdtemp(prefix="javis-profile-readonly-"))
stack = readonly_harness._stack(scratch)
readonly_plan = asyncio.run(stack[6].prepare(
    stack[3], "calendar list today events", str(stack[0]), "dashboard", "groq", "llama-3.3", "api", "actor-1"))
check("read-only route: the turn is admitted", readonly_plan.action == "execute", readonly_plan.reason)
check("read-only route: the arguments round has no profile (it writes no prose)",
      HEADER not in system_of(readonly_plan.messages))
final = stack[6].compiler.compile_evidence_final(readonly_plan.compile_request, EVIDENCE)
final_system = system_of(final.capsule.rendered_request["messages"]) if final.capsule else ""
check("read-only route: the answer round carries the profile",
      final.status == "compiled" and MARKER in final_system and final_system.count(HEADER) == 1, final.status)
check("read-only route: the profile comes before the round's own rules",
      0 < final_system.find(MARKER) < final_system.find("Đây là vòng tổng hợp cuối"))

scratch = Path(tempfile.mkdtemp(prefix="javis-profile-orchestrator-"))
ostack = orchestrator_harness._stack(scratch)
orchestrator_plan = asyncio.run(orchestrator_harness._prepare(ostack))
check("multi-step read-only route: the turn is admitted", orchestrator_plan.action == "execute",
      orchestrator_plan.reason)
check("multi-step read-only route: the request of the task carries the profile",
      MARKER in orchestrator_plan.compile_request.profile)
ocompiler = ostack["orchestrator"].compiler
manifests = [{k: x.get(k) for k in ("capability_id", "name", "summary", "capability_revision", "score")}
             for x in orchestrator_plan.candidates]
planner = ocompiler.compile_orchestrator_plan(orchestrator_plan.compile_request, manifests, [], 4)
check("multi-step read-only route: the planner round has no profile",
      planner.status == "compiled" and HEADER not in system_of(planner.capsule.rendered_request["messages"]),
      planner.status)
arguments = ocompiler.compile_canary(
    orchestrator_plan.compile_request,
    {"selected": [{"capability_id": manifests[0]["capability_id"]}], "miss_class": ""})
check("multi-step read-only route: an arguments round has no profile",
      arguments.status == "compiled" and arguments.trace_report.get("selected_count") == 1
      and HEADER not in system_of(arguments.capsule.rendered_request["messages"]), arguments.status)
bundle = ocompiler.compile_evidence_bundle_final(orchestrator_plan.compile_request, [EVIDENCE])
bundle_system = system_of(bundle.capsule.rendered_request["messages"]) if bundle.capsule else ""
check("multi-step read-only route: the answer round carries the profile",
      bundle.status == "compiled" and MARKER in bundle_system and bundle_system.count(HEADER) == 1, bundle.status)

# ---- 5. required, never dropped in silence ----
NO_TOOL = {"selected": [], "selected_count": 0, "candidate_count": 0, "miss_class": ""}


def capsule(profile: str, budget: int = 32_000):
    return main._CONTEXT_COMPILER.compile_canary(CompileRequest(
        task_id="profile-budget", step_id="s", objective="chào em", brain=ROOT_OF_BRAIN, channel="dashboard",
        provider="groq", model="llama-3.3-70b-versatile", model_kind="api", hard_max_input_tokens=budget,
        rolling_tpm_remaining=1_000_000, reserved_output_tokens=500, execution_mode="canary", profile=profile,
    ), NO_TOOL)


CLOCK["now"] = "Bây giờ là 09:01 Thứ Hai 02/11/2026."
bare = capsule("")
bare_tokens = int(bare.trace_report.get("estimated_input_tokens") or 0)
full_profile = memory_control.main_prompt_rendering.render_profile_block("x" * memory_control.PROFILE_MAX).strip()
fits = capsule(full_profile)
check("a profile at its 4,000 character cap fits a small-talk budget", fits.status == "compiled", fits.status)
check("the budget counts the profile",
      int(fits.trace_report.get("estimated_input_tokens") or 0) > bare_tokens + memory_control.PROFILE_MAX // 4)
check("the capsule records the profile as a required source",
      (fits.capsule.source_map.get("owner_profile") or {}).get("required") is True)
tight = capsule(full_profile, budget=bare_tokens + 50)
check("a budget too small for the profile fails the compile instead of dropping it",
      tight.status == "required_items_too_large" and tight.capsule is None, tight.status)
check("the same budget still serves a capsule with no profile", capsule("", budget=bare_tokens + 50).status == "compiled")

# ---- 6. an empty profile adds nothing, anywhere ----
with_profile = system_of(capsule(memory_control.profile_block().strip()).capsule.rendered_request["messages"])
memory_control.write_profile("")
check("an empty profile gives an empty block", context_compiler.owner_profile() == "")
check("CompileRequest carries no profile by default",
      CompileRequest("t", "s", "o", "b", "dashboard", "p", "m").profile == "")
for level in LEVELS:
    set_level(level)
    check(f"[{level}] empty profile: nothing in the regular prompt", HEADER not in regular_prompt())
    for engine in ENGINES:
        prompt, plan, _flags = lane_prompt(engine, f"empty-{level}-{engine}")
        check(f"[{level}] empty profile: nothing on the {engine} lane",
              HEADER not in prompt and HEADER not in plan.turn_context, (plan.action, plan.reason))
        greeting = fast_plan(engine, f"empty-hello-{level}-{engine}", "chào em")
        system = system_of(greeting.messages)
        check(f"[{level}] empty profile: nothing in the {engine} fast capsule",
              greeting.action == "execute" and HEADER not in system and context_compiler.PROFILE_END not in system)

empty_system = system_of(capsule(context_compiler.owner_profile()).capsule.rendered_request["messages"])
check("the profile block is the only difference between a capsule with a profile and one without",
      with_profile.replace("\n\n" + memory_control.main_prompt_rendering.render_profile_block(MARKER).strip()
                           + "\n" + context_compiler.PROFILE_END + "\n\n", "\n") == empty_system)

empty_final = stack[6].compiler.compile_evidence_final(
    CompileRequest(**{**readonly_plan.compile_request.__dict__, "profile": ""}), EVIDENCE)
check("empty profile: nothing in the read-only answer round",
      empty_final.status == "compiled"
      and HEADER not in system_of(empty_final.capsule.rendered_request["messages"]))

print()
if fails:
    print(f"FAIL: {len(fails)} check(s)")
    sys.exit(1)
print("All checks passed.")
