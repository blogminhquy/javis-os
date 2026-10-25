# Compose Owner Controls Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Root remains responsible for integration; local app/native tests run serially.

**Goal:** Connect the functioning owned composer and independently checked typed candidate to explicit owner controls, cold history and the existing improvement panel.

**Architecture:** Reuse the existing ExperimentService, OperationExecution/Tasks, ComposeInputs/Permissions and ComposerService. Cold metadata reads use only the existing scoped store; they never construct a host or native runner. The operator follows explicit preview/consent/run/revoke actions, while current source, ownership, product and independent-view gates remain authoritative.

**Tech Stack:** Python/FastAPI/SQLite/Fernet, existing asyncio lifecycle, vanilla dashboard JavaScript and existing bilingual UI helpers.

**Spec:** docs/superpowers/specs/2026-10-22-agent-skill-evidence-improvement-design.md, sections11 and22–24; AGENT-SKILL-IMPROVEMENT-GOAL.md sections3,12–17. The current checked-arm unit must finish its scoped review/evidence first.

## Global Constraints

- Only the managed checkout/branch; never modify the original D:\Project\Javis-OS.
- VERSION0.299.0 remains reserved; no task-branch integration before required review/CI.
- Keep old closed requests/history/default budget2 exact. Explicit new candidate_policy=two_proposals_and_one_compose reserves3 before observations; statistical budget is not compose consent.
- One compose, ordinary proposal cap2, no structural repair or semantic resampling of compose output. No model/provider/reasoning/account changes.
- Consent grants generation only. Newly composed bytes require their own exact-diff grant, semantic/dependency review, native view/Trial evidence, tuning/final/qualification/regression and activation gates.
- Preserve baseline/unknown/loss policy, protected meaning, brain/scope/grant/source pins, immutable encrypted evidence and actual Trial/Call ownership.
- Phase1 permits labelled fixture/DI/localhost controls only. No real account/model/query, native registration, activation, deploy/restart or rollout from this plan.
- Full M0–M8 Goal remains active. Actual upstream experience library follows the functioning compose slice; orchestration comparison follows library.

## Review Focus

1. Cold/off/old-schema GET and replay must not initialize a source, verifier, runner, schema or capability; exercise factories that raise if invoked.
2. A stale/foreign experiment or authorization path must refuse before native verification or new Operation/Call; exercise real same-store scopes.
3. Stop/close/recovery while preview, admission or publication is waiting must drain owned work without a late compose result escaping; exercise blocked-thread ordering.
4. A browser tab switched to another brain, a repeated click or a lost response must not send a second intent, restore revoked consent or display private stale evidence.
5. A staged candidate, reserved budget, simulated native packet or observational unknown must never be labelled qualified or ready to activate.

## Files and boundaries

- Modify server/improvement_experiment_service.py: one ComposerService over the existing execution/tasks; owned workflow dispatch, stopped history, cancellation and close.
- Modify server/improvement_experiment_requests.py: explicit closed compose control shapes, no caller-created input/config/definition pins or arbitrary operation names.
- Modify server/improvement_experiment_api.py: registered owner-session controls and bounded cold consent/composition/policy metadata; current experiment/path scope before work.
- Modify server/improvement_compose_permissions.py: narrow from_existing(assets) cold metadata/revocation facade if needed, with explicit denial of source/generation actions without concrete plans. Reuse the existing tables, events and nine-field consent metadata.
- Reuse server/improvement_compositions.py and improvement_compose_inputs.py; no alternate runner, publisher, consent or accounting ledger.
- Modify dashboard/improvement-candidates.js and .css; add a focused dashboard/improvement-experiments.js only if the existing candidate panel would otherwise become an unrelated controller. Register via existing panel entry and dashboard/index.html, using current request/lifetime/bilingual helpers.
- Add focused tests/python/test_improvement_compose_controls.py and test_improvement_compose_api.py plus dashboard interaction tests under tests/js following the existing candidate panel tests.
- Any added native source dependency must update the actual footprint inventory and its exact-source test; do not alter the actual309 registration proof test.

### Task 1: Actual owned controls and cold history

**Consumes:** ComposerService(execution,tasks).compose(principal,authorization_id,expected_generation,event_key); ComposeInputs(plans).build(principal,experiment_id,expected_generation); ComposePermissions.authorize/get/list/revoke and the existing ExperimentService ownership barrier.

**Produces:** Actual registered experiment controls with these meanings:

- compose-preview: expected_generation/event_key; current owner source-guarded projection of the saved input basis and its authorized tuning/candidate refs. No consent or native call. Do not expose hidden answers/checker internals/holdout/raw CoT.
- compose-authorize: expected_generation/event_key; explicit existing immutable authorization plus revocable grant. A preview or reserved budget never grants it implicitly.
- compose: authorization_id/expected_generation/event_key; expected_generation is the authorization's saved experiment generation. Authenticate path experiment scope before dispatch and call the existing composer once.
- compose-revoke: authorization_id/expected_generation/event_key; here expected_generation is the consent grant's own generation. Reuse existing metadata-only revoke after off/stopped state; never revive a grant.
- Cold per-experiment consent/composition metadata and a separate immutable-policy projection. Keep ExperimentRecords._public and historical event shapes unchanged rather than adding fields that would break old replay/creation proof equality.

- [x] Write real owner/service/ASGI failing tests for each closed shape, exact path/brain scope, source drift, off/old-schema cold reads, zero-probe false capability, and actual compose publication through the facade. Use only narrowly labelled fake native boundaries; keep current/product/readers real.
- [x] Observe meaningful RED before implementation, saving source/test hashes and distinguishing fixture errors from missing behavior.
- [x] Add the composer to ExperimentService construction and all relevant role workflow ownership/drain/close paths, with actual stopped completed/start history replay. Keep _snapshot's finite six-role bound; no second tasks object or executor.
- [x] Register only closed route names. Reuse existing owner-session dispatch, body limits, redaction, event conflict handling and current experiment authorization scope.
- [x] Implement cold metadata through the actual scoped store without a service factory or migration. A cold-only facade must refuse authorize/current/build/compose, rather than gaining authority from a missing attribute or caller-supplied flag.
- [x] Verify same-event joins, different-event one-compose limit, cancellation of slow work, late grant/source/domain changes, cold completed replay and interrupted-start no-redispatch. Keep default unqualified native paths closed.
- [x] Run scoped affected lifetime/recovery/API regression, independent review and evidence; commit the functioning controls. No API integration claim from grammar alone.

### Task 2: Existing operator panel uses the real controls

**Consumes:** Task1 actual routes, existing candidate exact-byte private review/authorization and semantic/view/report controls. Current native capability and independent checks remain separate facts.

**Produces:** A reachable owner flow in Cải tiến có kiểm chứng using actual server state, with explicit consent/run/revoke and durable recorded outcomes.

- [x] Before UI code, add a narrowly scoped cold `GET /improvement-experiments/{id}/compose-outcomes` projection if needed for exact disposition reload. Existing `/compositions` intentionally contains publications only; an invalid-output or native-incomplete result has no publication row. Reuse authenticated existing compose_generate/start, authorization and Operation history, bounded to the existing one-compose scope. Return recorded disposition/role status and references only, with authority not_checked/business_proof false. No new store, executor, schema, service factory, decryption, source probe or inferred readiness; old-schema known experiments return empty metadata, foreign scope refuses. Pin actual readonly ASGI cases with raising factories/decrypt callbacks before adding the reader, preserve existing routes, then review this narrow backend delta with the UI.
- [x] Pin interaction tests that exercise the real controller contract: no POST on open, no implied consent, no autorun, closed event keys on retry, no duplicate click intent, brain/tab switch cancellation and no stale private content.
- [x] Expose the new experiment budget choice only before experiment creation. Reopened old two-slot experiments retain their immutable policy; existing typed3 drafts remain labelled unevaluated in that experiment.
- [x] Show authorized current input refs and one-compose scope before consent. Show consent generation/status and a separate explicit run action. Disable or explain unavailable capability from actual current gate state; do not infer readiness from an installed CLI or the existence of a button.
- [x] Reuse the existing exact-byte candidate review and exact-diff grant action. Distinguish staged, semantic/dependency/native unknown or fail, tuning result, final result and activation eligibility. KEEP_BASE is a valid recorded outcome.
- [x] Support revocation/off, cold outcome reload and historical interrupted/invalid-output/native-incomplete states without replaying work. Read generated decision/provenance details only through an explicit currently authorized evidence path; metadata GET does not decrypt private blobs.
- [x] Keep controls bounded, keyboard accessible and bilingual with current tw()/info-tip conventions. Avoid product prose about internal module/schema/transport implementation.
- [x] Verify interaction behavior plus actual ASGI-to-service controls, scoped JS/i18n/regression checks and independent review. Record fixture versus native/business gates separately; do not deploy/restart.

## Reuse decision before code

Pinned Harness² remains1cfe254e8d25b15f37048c3730134686abe60335. prompts.compose_round is already actual unchanged vendor code; recursion.py _run_stage/run_sequential (blobdda6b98cd5af100b8941f33cbb079462299c5280) has benchmark filesystem ownership, retries and accounting, but no Javis owner-session API, revocable consent, browser lifetime or durable stop/replay contract. Adapt the existing Javis owner/API/panel around the actual composer rather than importing a second executor or benchmarking controller. Preserve upstream provenance/license, all new-content checks and the explicit source-profile qualification gap. This plan adds no new upstream copy and makes no quality/token savings claim.

## Open gates after this plan

The scoped runtime/ASGI/browser fixtures do not establish same-pipeline native qualification, actual model/account execution, fully qualified selected-final execution, business pilot, canary or activation. Those and the remaining M0–M8 work stay open. Save the exact final task-head full required CI and fresh whole-branch review for integration; early isolated Linux snapshots are supporting checks only.

## Implementation ruling before Task2

Task1 froze the actual publication-only composition reader and passed scoped review;
its immutable proof remains valid. Task2 may extend only the existing cold metadata
reader/API with the recorded-outcome projection described above, because reload
must distinguish invalid_output/native_incomplete from an interrupted or still
recorded operation without issuing POST on open. Do not alter Task1 history/event
shapes or rerun its unchanged broad suite. The new reader and affected transport
need their own meaningful RED/GREEN, focused actual ASGI regression and scoped
independent review. This is a bounded operator-history requirement, not another
compose attempt or new authority.


## Scoped completion checkpoint

Task1 backend67dfb662 and Task2 panel5490cde6/95790edb passed scoped technical
checks and independent review; Task2 three P2 recovery findings were reproduced
and closed in fix round1. Public compose-owner-controls and compose-owner-panel
proofs retain exact hashes and fixture/native limits. Early Linux snapshots do
not replace final task-head full CI. Minor candidate option labels and warning
noise remain tracked for final review. Actual-library plan is prepared before
code; canonical retrieval/native/business/M0-M8 gates remain open. Goal active.
