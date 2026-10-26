# Automatic learning from chat (skills, agents, workflows)

Date 26/10/2026. Owner decision in chat, 26/10: Javis improves itself while the owner talks to it. A judge reviews
the work, finds where Javis was wrong, writes the test cases itself and improves the skill, agent or workflow that
caused it. The owner does not need to know it is happening and approves nothing. The owner also asked for agents
and workflows, not only skills. Users install nothing extra.

## Goals

- Learn from real use: every owner chat turn that used a skill, every agent chat turn, every finished workflow run.
- Detect mistakes without the owner saying anything special: a judge reads the turn, the owner's next message
  (a correction, a redo, a complaint) and any reaction on the answer.
- Improve the target with the 0.333.0 loop (Harness² sequential recursion, baseline wins ties, sealed paired
  verdict, sign test, regression gate). The cases and their grading criteria are written by Javis.
- Apply a passing result on its own, keep the old version and a way back.

## Non-goals

- No bulk background rewrite of every skill (owner decision 2026-08-16 still holds): a target is touched only after
  real mistakes in real use, and at most once per cool-down.
- No tool calls during learning: everything runs text-only, so learning cannot send, buy or post anything.
- Kanban tasks, team chats and the native `nodes[]` workflow format are out of scope for this version.

## Anti-goals

- A judge that sees mistakes everywhere and burns the owner's plan: caps and cool-downs are hard limits.
- A change that makes things worse: the regression gate and the paired verdict stay; anything short of "helped"
  keeps the current version.
- Touching what the owner wrote by hand in an agent: agents learn through a learned procedure overlay (M5), never by
  editing `agents/<slug>.md`, and never the "Luật chủ dặn" section.

## Design (builder's calls, made by Claude)

1. **Episodes** (`server/auto_learning.py`, SQLite in the state folder, per brain).
   - Skill uses are noted per chat session from the hub's `javis_use_skill` handler (all engines) and from Claude
     Code's native `Skill` tool or a read of `skills/<slug>/SKILL.md`.
   - `_persist_turn` closes the turn. Each skill used becomes an episode (kind skill). An `agent:<slug>` session
     becomes an episode of kind agent. The same call stores the new user message as the follow-up of the
     session's previous episodes.
   - A finished workflow run (`_ghi_lich_su`, every source) becomes an episode of kind workflow.
   - System skills, `.agents` skills and protected skills are never recorded.
2. **Judge** (scheduler tick, worker thread, text-only call on the background model).
   - An episode is ready once it has a follow-up, a reaction, or is two hours old.
   - The judge returns `ok`, `mistake` or `unsure`. For a mistake it also returns what went wrong, the right
     behaviour and one self-contained test case (for a workflow, the faulty step).
   - Only `mistake` counts. A negative reaction makes a mistake verdict more likely but is not required.
   - Cap: 40 judgments per brain per day.
3. **Learning run**, which starts when a target has at least 3 open mistakes, its cool-down (3 days) has passed,
   and the brain has had no run today (cap 1 per day).
   - Javis writes 16 to 24 cases, each with a prompt and grading criteria. They come from the mistakes (each one a
     family, plus variants) and from turns judged ok (protection against regressions). Every case must be
     answerable without tools. If the writer says the work cannot be tested without tools, the target is skipped
     for 14 days.
   - The cases are split by family, about a quarter for tuning, so the improver never sees a sealed case.
   - A grader call scores each answer against the criteria. A grader failure is an engine error, never a fail.
   - The loop runs on the brain's selected engine (text-only path from 0.333.0).
4. **Apply.** Only on verdict `helped`, with a backup in the state folder and a history row that has an undo.
   - Skill: body of `SKILL.md`; the frontmatter is kept and the bytes must still match.
   - Agent: the text of a learned procedure overlay (stage plus apply on all surfaces); the agent file stays
     untouched.
   - Workflow: the `task` text of the faulty step in the frontmatter (steps format only).
5. **Switches and limits.** (Owner, 26/10: "turning on the learning features on the Learning page is all it
   takes".) Learning from chat follows the existing Learning page: "Bật tự học" plus the Skill, Role (Agent) and
   Step chain (Workflow) switches decide what learns. Auto-write mode applies on its own, Suggest prepares everything
   and waits for Apply, Dry run only judges. The page lists the changes with Apply and Undo. When the main engine
   has no text-only path (Grok Build, Antigravity), learning uses the background model set for learning on the
   Models page. The earlier points below still hold.
   - It is on by default, a call made by Claude. It follows the brain's improvement policy: mode `off` stops it.
   - The caps above are fixed constants; nothing is added to Settings.
   - A small "Javis đã tự học" list in the improvement panel shows what changed, with undo. There are no
     notifications.

## Not covered yet (known gaps)

- Telegram, Zalo and CLI owner turns carry no session id in the turn context, so skills loaded there are not recorded,
  and agent turns there are not `agent:` sessions.
- Codex reading SKILL.md through shell commands is not seen; Codex loads through `javis_use_skill` are.
- Workflows installed by store packs are not protected the way pack skills are.
- Kanban jobs, team chats and `nodes[]` workflows are out of scope.
- The host side of agent apply/undo (real `AgentProcedures`) is exercised only through fakes in tests.
