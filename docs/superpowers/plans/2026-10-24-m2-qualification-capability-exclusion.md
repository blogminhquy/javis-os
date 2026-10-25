# M2 Qualification Capability Exclusion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. One bounded task, one serial local app/native slot, independent scoped spec+quality review.

**Goal:** Prevent an explicit technical/non-account capability from reaching ordinary product reservation or query paths, even when supported=true is spoofed.

**Architecture:** Extend four existing unsupported-result conditions with two exact reject predicates. Reuse actual ordinary owner/ledger/abort/refund/cleanup paths and existing fixture capabilities. No new validator/runtime/ledger or positive readiness authority.

**Tech Stack:** Existing Python/SQLite/Fernet/asyncio/unittest/project runner. No installation, CLI/SDKClient/model/account/network probe.

**Spec:** docs/superpowers/specs/2026-10-24-m2-qualification-capability-exclusion-design.md and Goal18. Current code21a5c0b1, docs945ee7e7; schema10/profile99 UNQUALIFIED.

## Global Constraints

- Managed checkout C:/Users/admin/.codex/worktrees/agent-skill-improvement-m2a/Javis-OS only. Never modify/reset/clean D:/Project/Javis-OS; its .venv Python may execute with -B. VERSION0.299.0 unchanged; English code/comments/commits, existing bilingual UI untouched.
- Goal18 ends current Goal at M2 engineering plus committed/integrated Claude Opus5.5 handoff. No M3–M8/recipe/Library expansion, new Goal, actual account/model/business/pilot/canary run, deploy/restart or activation.
- Preserve existing dictionary/type/isinstance, supported-is-True/hash/error and authority/lease/current-source checks. Reject exactly explicit account_ready is False or domain == qualification through each existing unsupported branch; maps lacking both fields keep existing semantics. No caller readiness/permission escape.
- Four production files plus one new test module only; no schema/profile seed list/registration/vendor/history/protected reservation-test change, no second executor/ledger. Native source footprint changes remain UNQUALIFIED; no inherited readiness.
- Use actual tests/run.py isolation/no-real judge/review/team flags and one serial local slot. Real disposable stores/calls/owners; only adapter capability is the deliberate seam, labelled engineering. No global warning suppression, broad unchanged suites, helpers/reviewer/subagents/sidebar chats or worker push.

## Review Focus

1. supported=true with explicit qualification domain/false account readiness must refuse before a new admission reservation or native query/start marker.
2. Already claimed unmarked attempts follow existing abort/refund/cleanup; refusal must not strand a lease or charge a started call.
3. A valid ordinary map without the new markers still follows its existing fixture path; negatives cannot pass due to a malformed hash/unrelated source failure.
4. Trial async native verification and ordinary synchronous verification converge on the same result check; no query can bypass it after a lease is claimed.
5. Native/semantic/result history, cold cancellation and profile/candidate registries remain unchanged; fixture assertions never become qualification/account readiness.

### Task 1: Four consumed capability fences with real-owner controls

**Files:** Modify server/improvement_trial_admission.py, server/improvement_operation_execution.py, server/improvement_trial_runner.py, server/improvement_operation_runner.py only their existing supported capability conditions. Create tests/python/test_improvement_qualification_admission_fences.py. Root owns docs/evidence; no other source/test writes.

**Interfaces:** Existing TrialAdmission.admit(principal,public_start_request), OperationExecution.reserve(principal,identifier,*,expected_generation,event_key), and both existing _run_claimed signatures remain unchanged. The two extra OR predicates are `value.get('account_ready') is False` and `value.get('domain') == 'qualification'`, after each function's original dictionary/type guard. Admission/operation errors stay trial_native_unavailable/operation_native_unavailable; runner failures stay unsupported_configuration and use existing unmarked settlement. Do not replace existing checks with a new helper.

- [ ] Add meaningful RED cases for all four real boundaries using existing AdmissionTests, OperationExecutionTests, TrialRunnerTests and OperationRunnerTests scratch fixtures. Avoid inheriting/discovering all unrelated old suite methods. Own synchronous/asynchronous cleanup explicitly; no global teardown suppression. Reuse valid ordinary capabilities with unchanged syntactically valid existing hash, then add each marker/both and supported=true. Assert actual DB calls/reservations/engine_at and adapter/context/materialize/query/start sentinels as appropriate, plus a valid ordinary control at each boundary. A correct new false-only technical map also refuses. No fake SQL authority rows/current=true callback.
- [ ] Run only the new focused module through actual isolated runner; record intended RED behavior before source edits, distinguishing unrelated fixture errors. Implement the four conditions only; preserve existing type/isinstance distinction and rejection/error branches.
- [ ] Before final runs freeze exact five-path LF SHA256/size/Git-blob map. Run the new module plus these existing affected selectors serially: AdmissionTests.test_unsupported_or_malformed_native_capability_reserves_nothing; OperationExecutionTests.test_no_native_capability_means_no_reserved_call_and_replay_after_off_is_cold; TrialRunnerTests.test_unsupported_adapter_refunds_before_any_query_or_recorder and test_success_orders_marker_and_recorder_before_ack_and_cleanup_before_evaluation; OperationRunnerTests.test_actual_worker_profile_runner_retains_unknown_result_and_cleans_plaintext. Use actual tests/run.py, no real engine. No full native/admission/runner/archive suites.
- [ ] Self-review source delta/owner accounting/cleanup, commit only five owned paths with English message, verify tested freeze equals committed objects. Write task-1-report.md with complete raw RED/intermediate/final commands/cwd/UTC/PID/exit/count/duration/log paths, warnings/skips/pins, exact API behavior and terminal resource/slot audit. Root owns independent review/early exact-byte Linux/public handoff. Never spawn helper/reviewer or push.
- [ ] Root resolves scoped spec+quality findings and early Linux evidence, records exact-source component proof and handoff. Continue actual M2 technical preflight/query/qualification, D2/E/F and final CI/review/integration; no M2/account/business/native completion from these negative controls.

## Self-review and next dependency

The four predicates are consumed by actual current callers, preserve legacy
interfaces, and cannot turn false readiness into product authority. Real owner
controls test both before-reservation and after-claim refusal. A shared schema
or unused permit is unnecessary. The following separate native preflight design
must keep current startup2/account gates strict and attach before acquisition;
this task does not implement or qualify that path.
