# Self-learning loop (Harness² sequential recursion over Javis owners)

Date 26/10/2026. Owner decision in chat 26/10: do part A (loop), part B (pilot preparation) and part C (real
model runs to measure effect); users must not install anything extra.

## Upstream shape (harness2/core/recursion.py, run_sequential, pin 1cfe254e)

For t in 1..k: from the shared base rollouts, two proposals (INV = how the work is done, DOM = the business
procedure), each rolled out; then one COMPOSE over the round pool (history + this round) gives c_t; the next round
starts from c_t. Finals are c_1..c_k. Selection (harness2/core/selection.py) then picks one final by anonymous id.
Javis keeps its contract where it differs: the baseline always stays in the comparison and wins ties or unknowns
(Goal section 14 item 7), and the finals are judged on a sealed qualification split, never on tuning evidence.

## Javis mapping

| Upstream | Javis owner |
|---|---|
| base rollouts | owner trial of the baseline on tuning cases (existing trial service) |
| propose INV/DOM | existing improver proposal (two angles, spec 9.4) |
| roll candidate | existing trial of each candidate on the same tuning cases |
| compose_round | existing Harness² compose adapter (`improvement_harness2_compose.py`) |
| finals + selection | existing comparison plan, qualification and selection, baseline kept |
| library | existing recipe/library records |

New code is only the orchestrator: a resumable, idempotent state machine that calls those owners in order, keeps
every step's ids, stops on any refused gate with its reason, and is bounded by `refinement_decision` (M8) and the
spec 8.1 sources (`rank_needs`). It never applies anything: the owner applies the selected candidate.

## Zero setup

Runs with the brain's selected engine and the user's existing sign-in; no new key, package or setting. The
loop starts only from an owner request in the Studio panel ("Để Javis tự cải tiến skill này").

## Pilot (parts B, C)

One user-owned skill with deterministic checkers, fixture data only (no live accounts), tuning and sealed
qualification splits, the selected engine fixed, every attempt and unknown kept. The report states measured
win/tie/loss, coverage and cost, and says plainly when the result is inconclusive.
