# Self-learning loop (Harness² sequential recursion with the Javis baseline rule)

Date 26/10/2026. Owner decision in chat 26/10: do part A (loop), part B (pilot preparation) and part C (real
model runs to measure effect); users must not install anything extra.

## Why a separate loop and not the M2 trial pipeline

The M2 owner pipeline cannot produce a real comparison today: `REVIEWED_RELEASES` is empty, so every native trial
is refused, and the `actual_reasoning` integrity check can never pass, so every report would be inconclusive.
Unblocking it needs a reviewed native release and a decision on unobservable integrity checks; both stay open.
This loop instead runs text-only on the brain's selected engine (no tools, no MCP, no files), which makes side
effects and evidence leakage impossible by construction. It runs on the engines that have a text-only path
(Claude Code, Codex and the API brains); Grok Build and Antigravity CLI are refused with a clear reason. Nothing
extra is installed: the loop uses the brain the owner already selected.

## Upstream shape (harness2/core/recursion.py, run_sequential, pin 1cfe254e; inspected, not copied)

For t in 1..k: from the current version's tuning rollouts, two proposals (INV = how the work is done, DOM = the
business procedure), each rolled out; then one composition over the round pool becomes the next current version.
Javis rules kept where upstream differs: the baseline always stays a candidate and wins ties; a candidate equal to
the baseline is never chosen; the chosen version is judged once on sealed qualification cases, run as interleaved
baseline/candidate pairs, two repeats each; engine errors drop the pair and too many fail the run; a sign test at
p < 0.05 decides "helped"; any case the baseline got fully right and the candidate broke is a "regression" that
refuses "helped" (spec Q04); the improver never sees a sealed case (tested).

## Product (server/improvement_loop_runs.py)

The owner starts a run from the Studio panel for a user skill with `skills/<slug>/examples.json` (13 to 40
examples; deterministic split, at least 10 sealed). Sealed families that already judged a candidate move to the
tuning side, so every verdict is made on fresh examples. The improver sees only the skill body (CRLF and BOM
normalised); the frontmatter is put back on Apply. Apply is offered only for "helped", writes over the exact bytes
the run started from (checked again right before the replace), and keeps a backup under the state folder. Runs
carry the boot id and a heartbeat; a run whose worker is alive in this process is never marked interrupted, while
a restart frees the slot. The owner can stop a run; calls already running finish within their 300 s limit and each
call has its own cancel tag. One engine error in a small roll is an unknown, not a wrong answer.

Not built: resuming a run, reuse of the M2 trial/compose/recipe owners, `rank_needs`/refinement-ledger
integration, a model-written examples file. Not yet shown: the product path end to end against a real model (only
a one-call smoke test), value on real owner skills, engines other than Claude Code.

## Pilot (tools/self_learning_pilot.py)

Reconciling a shop's orders with bank transfers under the shop's conventions (COD fee up to 30.000, combined and
split transfers, refunds ignored), synthetic fixtures with answers by construction, the selected Claude Code CLI in
safe mode with no tools. Results are recorded in docs/superpowers/evidence/2026-10-26-self-learning-pilots.json.
