# M2 View and Experiment Admission Marker Fences Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. One batched task, one implementer and one serial local app slot. Steps use checkbox syntax. Root owns review and affected Linux evidence.

**Goal:** Refuse qualification-marked availability at the two remaining ordinary experiment/view admission consumers before they allocate trials, calls or holdout claims.

**Architecture:** Add the existing exact marker predicates to the two existing availability guards. Exercise actual ordinary source/plan/view owners and transactions with a declared capability-response seam. This independently testable prerequisite does not add a positive technical query route.

**Tech Stack:** Existing Python3.12, unittest, SQLite, encrypted improvement assets and real ordinary fixture owners; no native process or account invocation.

**Spec:** `docs/superpowers/specs/2026-10-24-m2-owned-baseline-query-design.md`, Q2 ordinary marker requirement; Goal §3/18. Immutable source reconciliation at `aec7bf440329011cf4a1069d3e185232fdce2290` is recorded in `.superpowers/m2-engineering-handoff/query-q2-source-contract-map.md` and `query-q2-marker-preflight.md`. Those notes are discovery, not passing test evidence.

## Global Constraints

- Work only in C:/Users/admin/.codex/worktrees/agent-skill-improvement-m2a/Javis-OS. Preserve original D:/Project/Javis-OS; its .venv/Scripts/python.exe may run with -B and managed cwd. Keep VERSION0.299.0 and the existing reserved branch/PR.
- Goal §18: M2 engineering and committed/integrated handoff only. No M3–M8, new Goal, account/model/business pilot/canary, deploy/restart or activation. Business/live acceptance remains PENDING.
- This task changes only the two ordinary admission guards and one new focused test module. No positive qualification entry, scheduler, semantic owner, runner, ledger, schema, native profile, registry, source-footprint list or public readiness change.
- Preserve exact dictionary and supported-is-True guards, ValueError('trial_native_unavailable'), existing caught exceptions, historical replay ordering, real source/current/barrier/linked transaction behavior and final resolve. Refusal predicate is `available.get('account_ready') is False or available.get('domain') == 'qualification'`. Integer0 is not identity False.
- Preserve `tests/python/test_improvement_view_reservations.py` raw SHA256 `0577b5181fb090ba897ec8c3d0fce10fe88d2d09d03839497150cdacf6e793e0`. Do not change or run its whole suite. No vendor/license/settings/version/release registration changes.
- Fixtures are ordinary disposable stores with real source/plan/view preparation. Their preexisting synthetic semantic review/adapter outputs are explicitly engineering seams, not installed-native or business proof. Do not weaken product-domain fences or patch current-evidence/source/transaction/reservation methods to reach the guard.
- Compose fixture setup/cleanup without inheriting historical TestCase discovery; no unchanged whole suite, no duplicate P0/Q1 run. Own every fixture handle/task/store/workspace and restore process/usage globals actually affected. No ambient CLI, native/account/config/network probes, no servers or production process control.
- Before RED and final GREEN, freeze exact changed/test/dependency file bytes, LF/CR counts, SHA256, size and Git blob IDs. Run through actual tests/run.py.chay_mot with isolated `-I -B -Xutf8` child and no-real judge/review/team flags. Record raw commands, UTC, logger/driver/child PIDs, counts/exits/warnings and post-run equality. Preserve failed setup logs; do not suppress warnings or rewrite evidence.
- Worker does the task itself, no subagents/reviewers/sidebar chats/push. Root grants a short exact-path commit window after terminal test/resource report; do not stage ignored helpers or evidence.

## Review Focus

1. A supported=True response with a valid capability hash and only account_ready=False must refuse before any new owner rows; test both actual consumers.
2. A response with only domain='qualification', or both markers, must refuse even when other supported/hash fields look ordinary; test both consumers.
3. Missing optional markers and account_ready=0/domain='ordinary' retain genuine successful ordinary admission, including links and an unstarted reserved call; test both consumers.
4. Malformed/non-dict availability must keep the original controlled ValueError before marker/digest access; test both consumers, with wrong supported identity and invalid hash controls.
5. Refusal must preserve the whole existing reservation/claim/event footprint, including holdout tables and brain-barrier lifetime, rather than merely avoiding an adapter call; compare real before/after rows and make a valid subsequent admission using the same owner.

---

## File Ownership

| File | Responsibility |
|---|---|
| server/improvement_experiment_admission.py | Existing ExperimentAdmission.admit ordinary availability guard, before _digest and all reservation writes |
| server/improvement_view_admission.py | Existing ViewExperimentAdmission._admit_owned ordinary availability guard, before _digest/holdout claim/reservation |
| tests/python/test_improvement_qualification_view_admission_fences.py (new) | Focused real-owner refusal/valid/malformed controls; no inherited old tests |

Use existing `test_improvement_experiment_admission.ExperimentAdmissionTests` setup/admit by composition, which owns `LineageTests` and real plans. For the view consumer use `test_improvement_view_sources.SourceFixture` setup/asyncSetUp/freeze with actual `ExperimentService`/ViewExperimentAdmission/ComparisonSchedule wiring as in `test_improvement_view_next.py`; it is an ordinary store and may use its declared synthetic semantic preparation. Read those exact setup methods before composition. Neither fixture is an anchored Session positive-view proof. No edits to those old modules.

### Task 1: Batch the two ordinary marker exclusions

**Files:**
- Modify: `server/improvement_experiment_admission.py:135` (current immutable basis).
- Modify: `server/improvement_view_admission.py:144` (current immutable basis).
- Create/test: `tests/python/test_improvement_qualification_view_admission_fences.py`.

**Interfaces:**
- Consumes: `ExperimentAdmission.admit(self, principal, experiment_id, comparison_id, cell_position, *, expected_generation, event_key) -> AdmittedTrial` and `ViewExperimentAdmission.admit_next(self, principal, experiment_id, comparison_id, *, expected_generation, event_key) -> AdmittedTrial`.
- Consumes: `ClaudeTrialAdapter.verify(self) -> dict` only as the declared availability-response test seam, after real source preparation. Actual reservation/ledger/link/holdout behavior remains unpatched.
- Produces: unchanged public signatures; both consumers reject either exact qualification marker before `_digest(available.get('capability_hash'))` and all writes.

- [ ] **Step 1: Write the six focused tests using real ordinary owners.**

Create `LegacyExperimentMarkerFenceTests` (synchronous composed fixture) and `ViewMarkerFenceTests` (SourceFixture mixin plus isolated async TestCase, no inherited old test methods). Each class has exactly these three test methods:

`test_marked_capabilities_allocate_no_ownership`: for fresh setups/subtests use supported=True, capability_hash='c'*64 plus each of `{account_ready: False}`, `{domain: 'qualification'}`, and both. Assert ValueError matching '^trial_native_unavailable$', actual verifier called once, no new trial/attempt/call/experiment-link/view-link/qualification-claim/qualification/event rows (snapshot existing rows rather than assume empty setup). The view path enters through actual admit_next, so final claims remain unchanged. At least one marked refusal is followed by a valid response on the same fixture, demonstrating release of the real brain barrier and absence of poison ownership. Do not manufacture a final comparison through direct SQL.

`test_ordinary_controls_keep_real_admission`: `{supported: True, capability_hash: 'c'*64}` with missing optional markers, and with account_ready=0/domain='ordinary'. Assert actual reserved Trial row, one new reserved/unstarted CallLedger call, correct actual legacy-v2 or view-v4 request/link, and no technical-domain result. Preexisting fixture rows are not counted as this admission.

`test_malformed_availability_keeps_controlled_refusal`: None, list, supported=1, supported=False, and supported=True with malformed hash; assert the same controlled ValueError with unchanged ownership. This pins short-circuit behavior and existing digest validation.

For snapshots use actual read-only SQL on existing tables and preserve ordered row values; no fake writes/phase transitions. Existing fixture factories may allocate earlier synthetic preparation calls; label them and snapshot after valid real preparation. Test cleanup must run on both successful and failing assertions and restore any global subprocess/usage patches touched by nested setup.

- [ ] **Step 2: Freeze and run RED before production edits.**

Use a private driver under this plan's ignored SDD workspace which imports actual tests/run.py and calls its `chay_mot` for the new module with `D:/Project/Javis-OS/.venv/Scripts/python.exe -I -B -Xutf8 <absolute-new-test-path>`. Set the same no-real judge/review/team flags used by the existing task harness. Record the exact driver and child command in the report. Expected RED: the two marked-capability tests fail on actual accepted rows/admission, while ordinary/malformed controls pass. Missing imports, fixture setup failure or a synthetic thrown exception is not meaningful RED; resolve fixture failures first and preserve their logs.

- [ ] **Step 3: Extend both guards with the exact predicates.**

In the two named existing methods, after the exact dict/supported guard (or within its short-circuit expression), refuse `available.get('account_ready') is False or available.get('domain') == 'qualification'` with the existing error before digest/reservation. Keep all other code and ordering unchanged; no helper extraction is needed for two short guards.

- [ ] **Step 4: Freeze final bytes and run GREEN once for the changed module.**

Run the same isolated driver/new module: expected six tests PASS, zero skips/failures. Report actual subcase coverage, timing, warnings/noise and driver/child exits. Verify pre/post hashes equal and actual cleanup of every owned fixture. If final code changes afterward, rerun only affected selectors with a new freeze and preserve the earlier run. Root will arrange exact-source affected Linux and independent review; neither substitutes for final whole-branch CI/native gates.

- [ ] **Step 5: Self-review, report, then commit only with root's exact-path window.**

Read the diff and verify Global Constraints, six tests, cleanup and source equality. Write full report at the brief's matching task-1-report.md: RED/GREEN/raw-file digest index, changed/dependency pins, declared synthetic seams, test evidence, actual resources/globals disposition and limitations. Send root terminal status with no uncertainty hidden. After root authorizes the Git window, stage exactly the three paths above, commit `fix: reject qualification markers in view admissions`, verify committed bytes match tested bytes, append report without rewriting prior bytes and release the local slot. No push.

## Self-Review and Following Units

Root self-review: the plan covers exactly the two ordinary omissions, including identity-False, short-circuit guard order, actual writes and valid controls. Review Focus1/2/5 map to each marked test, Focus3 to each ordinary control, Focus4 to each malformed test. No cross-task interface conflicts (one batched task); source owners/signatures match the immutable source map. No positive view or operation closure is claimed here.

Next independent plan is the grounded operation2 consumed vertical using Q1 native/accounting/proof lifecycle. Positive view4 remains an explicit source-contract gap pending reconciliation of EffectiveViews -> SemanticReview.current_evidence -> product-domain fence. Preserve the scheduler and use separate genuinely prepared comparisons. The final stable-source installed localhost qualification, protected footprint gate, full required CI/review/integration and M2 handoff remain OPEN.
