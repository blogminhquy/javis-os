# Self-learning loop (Harness² sequential recursion with the Javis baseline rule)

Date 26/10/2026. Owner decision in chat 26/10: do part A (loop), part B (pilot preparation) and part C (real
model runs to measure effect); users must not install anything extra.

## Why a separate loop and not the M2 trial pipeline

The M2 owner pipeline cannot produce a real comparison today: `REVIEWED_RELEASES` is empty, so every native trial
is refused, and the `actual_reasoning` integrity check can never pass, so every report would be inconclusive.
Unblocking it needs a reviewed native release and a decision on unobservable integrity checks; both stay open.
This loop instead runs text-only on the brain's selected engine (no tools, no MCP, no files), which makes side
effects and evidence leakage impossible by construction and works for every provider the user already has.

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
examples; deterministic split, at least 10 sealed). The improver sees only the skill body; the frontmatter is put
back on Apply. Apply is offered only for "helped" on a sealed set not used before, writes over the exact bytes the
run started from, and keeps a backup under the state folder. Runs carry the boot id and a heartbeat, so a restart
or a hung engine never blocks the next run; the owner can stop a run. Not built: resuming a run, reuse of the M2
trial/compose/recipe owners, `rank_needs`/refinement-ledger integration, a model-written examples file.

## Pilot (tools/self_learning_pilot.py)

Reconciling a shop's orders with bank transfers under the shop's conventions (COD fee up to 30.000, combined and
split transfers, refunds ignored), synthetic fixtures with answers by construction, the selected Claude Code CLI in
safe mode with no tools. Results are recorded in docs/superpowers/evidence/2026-10-26-self-learning-pilots.json.
