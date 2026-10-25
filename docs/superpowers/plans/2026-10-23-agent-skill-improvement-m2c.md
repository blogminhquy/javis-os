# M2C generated proposals and semantic evidence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans
> to implement this plan task-by-task. The Goal explicitly selects inline
> execution with self-reviewed plans and an independent final review.

Status: canonicalized and self-reviewed for inline execution. Release reserved
before product code at50406532e3b349c4e04c4320e73bbfa6d86a9cdc / draft PR801.
Concrete contracts below resolve the pre-flight audit. Task completion requires
actual RED/GREEN evidence; a plan or reservation is not implementation.

**Goal:** Produce bounded real model-generated skill proposals and separately
pinned semantic/dependency assessments from authorized tuning evidence, with
honest per-role usage, durable cancellation/recovery and no premature activation.

**Architecture:** Extend the existing experiment ownership with genuine typed
preparation baseline Trials, then distinct proposer/reviewer operations backed by
the existing CallLedger and usage pipeline. Preserve A proposals and B comparison
lineage; semantic evidence is append-only, not an edit to A's immutable unreviewed
status. The same real brain execution barrier covers every enabled native role.

**Tech Stack:** Existing Python/FastAPI/SQLite/Fernet, asyncio supervisors,
Claude SDK/selected CLI fixture-only worker; standalone unittest scripts and
GitHub exact-head Linux CI. No new provider/account/money ledger/Goal.

**Spec:** docs/superpowers/specs/2026-10-22-agent-skill-evidence-improvement-design.md
sections9–12,18,23,26–29 and AGENT-SKILL-IMPROVEMENT-GOAL.md. Actual published B
baseline47f50f707268681dd4cbe8c7e443945155376237,0.293.0, PR800. Exact-head
CI39880551488 passed on2fe944ae; merged tree4e53048721ca658f620a73361b4281326852e3b6
is identical. Actual GHCR publication39882926274 and Build & push succeeded.
No deployment/restart/activation or complete M2/business/rollout acceptance.

## Global Constraints

- Apply Goal section12 (2026-10-23 owner process addendum) from this Task1 onward:
  RED/GREEN within fixes, impact regression at task end, independent whole review
  when stable and complete required exact-final CI before merge. Record reusable
  source-bound evidence and invalidation; no reruns merely for resume/compaction.
  Validate Linux early for SQLite/filesystem/process changes; parallel scripts
  only after verifying resource isolation. Keep every quality/authority gate.
- Keep the owner's selected engine/model/reasoning and existing quality gates.
  No monetary cap, alternate model or reduced source/validation to save usage.
- No qualification/regression/private answer material in improver input. Distinct
  family IDs do not prove business independence. Preserve technical labels.
- At most two actual proposals; at most one structural-repair request for a
  generated batch. No retry-until-win, invented candidate or placeholder arm.
- Trial/native operations never change canonical skills, protected owner rules,
  enabled state, source permission, mirrors or live memory. No host execution of
  arbitrary model-produced Python/commands/helpers. command_ok stays unsupported.
- Existing v1/v2 request/hash/history/replay semantics remain intact. New typed
  preparation execution must not become a legacy downgrade or readiness boolean.
- New native-role code belongs in the explicit profile source footprint and must
  pass exact selected-runtime fake-provider qualification before real execution.
- Actual effort/asset use/usage coverage remain unknown when not observable.
  Delivered request arguments and provider-effective behavior stay distinct.
- Owner product confirmation is not semantic/runtime/source acceptance or an
  activation grant. Candidate/final execution still requires D's actual view.
- Suggest mode never autonomously starts model work; owner intent must authorize
  every supported operation. Off/revoked blocks new work but permits settlement.
- Before product code, reserve next free VERSION/both changelogs and open/attach
  draft PR under repo rules. No production deploy/restart/live canary.

## Review Focus

1. Baseline-first workflow must work inside an existing durable experiment,
   without fake arms, hidden holdout use or orphan pre-B work.
2. A model cannot mint owner authority, role identity, arbitrary evidence refs,
   helpers, native flags or accepted semantic/runtime status.
3. Every preparation Trial and role call participates in stop/recovery ownership,
   even when its database row is terminal but a worker/checker is still alive.
4. Slow model/blob/source work cannot publish stale proposals or semantic receipts.
5. Limits/repair/idempotency cannot leak a third candidate or reset exposure after
   interruption; incomplete native evidence cannot silently become pass or zero.

## File/Interface Map

New focused modules (confirm names at canonicalization; no code stubs as output):
- improvement_preparation_protocol.py: pure closed request-v3/schedule identity.
- improvement_preparation.py: concrete host-derived preparation schedule/admission.
- improvement_operation_schema.py / improvement_operation_records.py: schema6
  immutable inputs/results/links, real call attempts/leases and bounded repair.
- improvement_operation_protocol.py: pure closed role requests/events/receipts.
- improvement_operation_workspace.py / improvement_operation_worker.py:
  real operation-ID workspace/native process boundary, not fake Trial receipts.
- improvement_operation_runner.py / improvement_operation_tasks.py:
  owned native role execution, actual usage settlement and cleanup.
- improvement_improver_inputs.py: fresh authorized tuning projection only.
- improvement_proposals.py: concrete bounded generation/repair/publication.
- improvement_semantic_review.py: pinned semantic/dependency assessment evidence.
- improvement_operation_api.py: closed owner controls/cold history projections.

Modify actual consumers: improvement_store.py; TrialStore request/current/reserve/
materialization; HostContextStore binding/context_loader/live_guard; trial result,
evidence/private/product/views; CallLedger purposes; turn_context/usage telemetry;
native profile source list; ExperimentService actual stop snapshots; main lazy
lifetime wiring. Keep files focused and avoid growing main with async ownership.

## Task 1 — schema6, preparation schedule and operation ownership

Interfaces: concrete PreparationRecords/OperationRecords(assets), cold metadata
reads, existing writer-owned transitions. Add immutable host-derived preparation
schedule/actual Trial links and role operation requests/attempts/results/evidence;
reuse agent_calls IDs. Exact schema/column names are finalized after reading the
current schema/CallLedger transaction contract, before writing migration code.
Use the frozen concrete contracts below. Impact: schema migration and cold B/A/M1
history consumers; no native profile/worker change. Fix loop: new operation test
case(s). Task regression: operations, experiments, store; old-reader source fetch.
Early Linux CI tests actual SQLite/backup/path behavior before later native work.

- [x] Read current schema5, B final publication and source rules; reserve release.
- [x] Write migration/old-reader/rollback/immutable-scope tests; run expected RED.
- [x] Implement schema6 in existing DB with one serialized pre-migration backup,
  safe fresh schema path and actual released B old-reader refusal before writes.
- [x] Preparation state uses B proposed→preparing CAS and retains brain capacity.
  Freeze complete tuning membership/repeats into a real schedule; no arm/candidate.
- [x] Schema enforces immutable typed preparation links and actual role call FKs;
  immutable schedules never UPDATE to attach trials. Positive atomic Trial/call/
  link/event admission is Task2; genuine operation reservation is Task3. Neither
  path is advertised ready by this metadata task.
- [x] Close role/status/ordinal/repair constraints; cold GET cannot migrate/probe.
- [x] GREEN scoped migration/permission/replay tests; commit with evidence.

Task1 local evidence: operations21/21 GREEN48.856s, experiments19/19 GREEN43.686s,
store22/22 GREEN5.232s. Migration RED4 missing-feature failures; metadata RED8;
SQL pending-completed and signed seed RED→GREEN2/2. Actual released B old-reader,
known1..5, concurrent backup/rollback and unchanged history checked. No native
profile code changed. Commit/early Linux verification follows; whole C remains open.

## Task 2 — genuine preparation baseline through existing solver

Interfaces: validate_preparation_request_v3, logical_key_v3, load_preparation_lineage;
PreparationService.admit_next(owner, experiment_id, expected_generation,event_key)
returns the existing AdmittedTrial shape backed by real rows. A preparation
request has version3, baseline only, exact common source/config/definition pins,
host schedule/cell identity and no candidate/arm/comparison fiction. Choose exact
closed pins after auditing all consumers, retaining v1/v2 expressions unchanged.
Impact regression: preparation/real execution/protocol; current operations schema,
TrialStore/Host/checks/results/decisions/private/views, comparison plans and old B
lineage/admission/execution/qualification/protocol. The new baseline uses actual
TrialTasks. Owner HTTP admission/handoff supervision and experiment-wide stop
integration remain Task8; these private functions do not expose a new route.

- [x] Behavioral RED: existing experiment/no candidate can prepare a real tuning
  baseline; arbitrary cell/qualification/alias/role/pin substitutions reject.
- [x] Update every version consumer: TrialStore; Host binding/context/guard;
  materialization; engine markers/observations; TrialResults exact immutable refs;
  public/private/product/evidence views. A parser-only extension is insufficient.
- [x] Host chooses next complete frozen tuning slot without gaps/cherry-picking;
  native preflight precedes atomic actual admission and late deadline minting.
- [x] Use the SAME existing TrialTasks dispatcher/Runner/CallLedger/usage.
  Preparation results are tuning evidence and cannot be paired v2 report cells.
- [x] Real synthetic-packet E2E proves workspace/output/result lineage and partial
  usage; replay stays exact after stopping/revoke, not a fresh execution grant.
- [x] Test concurrent next, current-source/config/grant drift after slow IO,
  actual stop before marker/after query/during checker, owned TrialTasks handoff
  and no holdout allocation/exposure. HTTP cancellation ownership remains Task8.
- [x] GREEN old v1/v2 parser/hash/authority/result regressions; commit.

Task2 evidence:12 impacted scripts initially10 GREEN/2 failed328s. Real Windows
encrypted publication conflict and incomplete old schema2 fixture were corrected
with deterministic RED/GREEN, preserving error/permission/rollback assertions.
Final affected4 scripts GREEN123s (operations21/preparation8/execution4/trials34),
storage25 GREEN6.330s. Old v2 protocol4/.004s and v3 protocol3/.002s passed.
Qualification14/58.135s and10 unchanged old paths are conditional scope evidence;
the changed blob/evaluator identity is rechecked by the current E2E, never claimed
to be proven by old snapshots. No full improvement sweep per patch, no independent
task reviewer, no native/model call. Early/final Linux CI remain separate.

## Task 3 — distinct real role/usage identities

Interfaces: closed operation metadata with operation_id/attempt/experiment_id,
actual host-issued role improver|semantic_reviewer and purpose improve_propose|
improve_evaluate; no fabricated trial_id/case_id. Native operation recorder verifies
the actual CallLedger purpose/mirror/brain/model/engine marker before persistence.

Impact: CallLedger, closed turn metadata, shared recorder/store/index/error counts
and per-operation view; actual operation attempt reservation stays in schema6.
Fix-loop new focused cases; task regression new roles plus old ledger/Team/usage/
turn metadata. Actual native no-learning behavior depends on Task4's worker;
Task3 must not claim metadata alone proves that runtime exclusion.

- [x] RED: existing ledger/metadata rejects genuine role operations; forged
  model role/brain/call refs and cross-role result packets must still reject.
- [x] Extend actual CallLedger purpose schema/allowlist and closed turn metadata,
  preserving Team and Trial formats and historical parsers byte-for-byte.
- [x] Reuse usage events/index for operation-specific request/token/coverage
  attribution. Expose null for unknown counts; equivalent price is not cash billing.
- [x] Preserve trusted learning_origin=compose on role metadata; telemetry never
  persists shared conversations/jobs. Actual worker/runner no-learning behavior is
  verified in Task4 before role enablement, not inferred from this metadata.
- [x] Test engine-marker interruption/refund, late telemetry, replay, foreign
  call identity, mixed role/session packets, usage-index reads and Team regressions.
- [x] GREEN meaningful role/usage/ledger checks; commit. Runtime learning exclusion
  remains an explicit Task4 dependency and whole-C release gate.

Task3 evidence: identity5 RED→GREEN, usage-index/view/error3 RED→GREEN, actual
operation call3 RED→GREEN, genuine marked operation telemetry RED→GREEN. Final
impacted8 scripts GREEN98s (real ledger, new calls/telemetry/usage, schema6, Team
quality usage, usage hotpath/index). Old Trial usage30 GREEN4.282s and original
turn context/Trial metadata checks passed. A later same-operation foreign-role
recovery finding RED1/2.921s is fixed; focused final telemetry9 GREEN25.058s.
Other unchanged successful paths are conditionally reused; full exact-head CI
remains required. No real worker/provider/model query or semantic acceptance.

## Task 4 — native role worker, workspace and owned lifecycle

Interfaces: concrete OperationRunner/OperationTasks over actual operation rows,
with typed operation-ID receipts/events. Share the real brain execution lock
with TrialWorkspace; keep distinct actual operation attempt lifetime locks.

- [x] RED: prepare/launch/drain/recover real synthetic role operations using the
  existing selected engine adapter; arbitrary host/code/tool capability rejects.
- [x] Implement bounded role input/output/event schema and native start handshake.
  Commit CallLedger engine marker before allowing actual query data through.
- [x] Own preflight→reserve→handoff through repeated HTTP cancellation and shutdown;
  refund only genuine unused reservations, settle observed starts interrupted.
- [x] No ambient hooks/plugins/skills/native Read/Bash/web/connectors; only actual
  preloaded fixture capability and immutable role input. No arbitrary evaluator
  code/script/registry from a model or HTTP body.
- [x] Actual isolated proposer/reviewer output containing JAVIS_LESSON, memory
  instructions and job suggestions produces zero production conversation/lesson/
  job effects, including cancellation/recovery. Trusted origin metadata alone
  from Task3 is not evidence of this runtime exclusion. Shared display persistence
  would additionally require durable digest/reaction replay provenance guards.
- [x] Include every new role worker/renderer/workspace source in explicit native
  profile footprint; version the profile. Historical results remain historical.
- [x] Test malformed packets, foreign live brain lock, lease expiry, cleanup
  failure, engine/checker/live-task after DB terminal and late result publication.
- [x] GREEN lifecycle/legacy native boundary tests; commit; no real account yet.

Task4 component complete: actual isolated operation worker/profile/IPC, original
writer-owned call/marker/trace/results, shared kernel barrier, owned cancellation/
shutdown/result threads and selected recovery. Real proposer and semantic reviewer
with synthetic SDK messages leave production sessions/lessons/jobs unchanged on
completion/cancel/recovery. Single infra retry uses actual attempt2, immutable
native error evidence, original deadline and durable owner-cancel fence; marked
first-attempt usage is retained. Same-number stale schema6 triggers reject before
native preflight; future schema rejection uses the existing store SchemaError.

Evidence: core13-script impact GREEN213s (conditional LF normalization proof),
retry11 GREEN282s, final changed lifecycle/schema6 scripts GREEN247s; future-schema
and positive actual lease2 GREEN5.241s. Retry races2 GREEN10.534s; aggregate usage
14in/6out across both marked attempts. Exact a1acaa99 LinuxCI39896580083 succeeded
for core only; new retry commit needs Linux CI. This is source-scoped component
evidence, not exact-final-C proof. Native qualification registration stays empty:
Task9 must qualify the complete stable profile/runtime before any real model call.
Public API/full stop and actual proposals/semantic evidence remain Tasks5–8.

## Task 5 — actual tuning projection and generation contract

Interfaces: ImproverInputs.build(owner,experiment_id,expected_generation) returns
bounded immutable data/hash/refs from actual preparation results and authorized
tuning snapshots; render_proposer_input is a pure data renderer.

- [x] RED: private answers/qualification/regression/unrelated artifact cannot be
  substituted, even after case relabel/clone/shared qualification fingerprint.
- [x] Load exact actual tuning result IDs/hashes, artifacts/source/public contract,
  baseline bytes and protected context. Never reuse PrivateReview as a model API.
- [x] Separate infrastructure/native/usage unknown from task deficiency. No CoT;
  preserve authorized traces with timing/tool/result/artifact/error evidence only.
- [x] Reject credential-bearing/insufficient source, stale grants/config/bytes and
  extra instructions outside the task. Pin recipe refs only when actually scoped
  and authorized; no whole recipe library or truncated required business input.
- [x] Closed generation output: ≤2 genuine body patches, hypothesis/affected
  component/evidence refs and not_a_target_defect for infrastructure causes.
- [x] Revalidate current authority after last slow read and before publication.
- [x] GREEN data-minimization/source/fingerprint/injection tests; commit.

Task5 component evidence: six absent-feature RED34.233s; first implementation
found a real unnecessary holdout-blob read in common ExperimentPlans._state.
The new internal tuning-only source projection fixes that without changing other
callers' full-source validation; private-answer/holdout read spies pass. Three
initial no-new-exposure assertions were corrected to preserve the genuine prior
baseline Trial exposures, not reset them to zero. Six GREEN36.335s.

Actual operation prompt now uses the pure proposer renderer. Four renderer/
reevaluation/credential/CoT checks GREEN13.166s (the first reevaluation test hook
was corrected to avoid recursively calling itself). A genuine late writer trace
at input publication reproduced RED6.642s; final trace/artifact/receipt snapshot
CAS fixed it, focused3 GREEN6.617s. Full task impact10/10 scripts GREEN256s on
canonical LF sources, including actual preparation execution, comparison plans,
A body patches, source/association authority and native worker/runner. Ten new
input cases passed50s inside that regression. No blanket improvement sweep.

Full required input is encrypted/hash-bound with exact sealed result refs and
current source/grant/config fences; oversize/credentials reject before publication.
Evaluator-private reasons/evidence and reasoning text are withheld; observed tool,
result/error/timing metadata and receipts remain bound. Missing tool payloads,
actual reasoning/input use and native coverage stay explicit unknowns. No separate
scoped recipe grant exists, so no recipe library is added; complete already-bound
protected context is retained. Native profile now pins25 source files and still
has no reviewed qualification registration. No native/model/API call or staging
is enabled by this component. Task6 will consume the closed generated batch.

## Task 6 — bounded generated proposal and repair publication

Interfaces: ProposalService.generate(owner,experiment_id,expected_generation,
event_key) and actual durable batch/repair records. Connect real improve_propose
operations to A's existing validator/staging with immutable generated provenance.

- [x] RED: native synthetic output becomes exact A proposals with actual role
  call/result refs; a malformed batch gets at most one durable structural repair.
- [x] Validate the entire batch before publishing any proposals; crash/replay/
  repair cannot consume a third A slot or partially authorize invalid output.
- [x] Factor a transaction-owned A stage primitive only where necessary; preserve
  existing manual API/replay/hash behavior. Publish original owner intent, real
  operation artifact hash and candidate link atomically under final source CAS.
- [x] Keep A semantic_status=unreviewed immutable. An editable region authorizes
  only actual granted bytes; generation never mints exact-diff/source grants.
  Proposals without edit authority remain readable/staged and unavailable to run.
- [x] Test protected/frontmatter/description/ownership/enabled/dependency escapes,
  stale source after native output, concurrent generate/repair and cancellation.
- [x] GREEN genuine generation/repair/private-review/old-A regressions; commit.

Task6 component complete locally: concrete ProposalService owns actual input/
intent/op admission, existing OperationTasks native completion and result publication.
A transaction-owned _stage_in preserves original public stage/replay behavior and
lets whole-batch A candidates/events plus generated publication/links commit in one
writer. Original owner region grants remain unchanged; no new exact-diff/source/
activation grant. Actual generated role call/result/artifact/input refs are retained.

Closed native JSON rejects duplicate keys and validates the whole batch, target,
actual evidence and remaining global slots before A inserts. One genuine repair
operation receives only original input/allowance, actual invalid artifact and fixed
validation code. Invalid repair terminates without looping. Missing observable
native evidence cannot be repaired into permission. Unobservable reasoning/input-use
remain unknown; all A drafts stay unreviewed and business_proof=false.

Evidence: actual2 workflows RED5.214s -> GREEN24.888s; first7 GREEN79.391s.
Actual ledger model mismatch before product consumption and a preflight after
shutdown during slow input reproduced2 RED17.886s; fixes plus repeated HTTP cancel,
DB-terminal publication-thread ownership, owner-cancel fence and strict JSON6
GREEN47.447s. Full body-patch schema now reaches both real role prompt renderers;
its missing-contract case reproduced RED. Owner-region/two drafts, unsupported
preflight, incomplete native inventory and renderer/duplicate-key5 GREEN27.741s.

Final affected9-script regression GREEN330s on canonical LF sources with all7
source/test hashes unchanged through the run. New workflow18 cases GREEN164s
inside it, including concurrent same-key callers with one existing manual slot,
mid-batch failure rollback, source drift, bounded repair and actual current calls.
Old A authoring/private review/body rules and operation input/result/worker/runner
passed. No full-improvement sweep or real native account/model query. Task4 retry
head a43638e7 LinuxCI39900250323 now SUCCESS; newer T5 Linux39901547032 is still
in progress and neither is exact-final-C acceptance. Native footprint27 files,
qualification registry empty; Tasks7–9/public C and business/live gates remain open.

## Task 7 — semantic/dependency evidence with exact provenance

Interfaces: SemanticReview.review(owner,candidate_id,expected_generation,event_key)
uses actual improve_evaluate operation(s); current_evidence validates concrete
immutable result refs, before/after bytes, protected context, dependency closure,
source authority and selected engine/evaluator/config. No generic readiness flag.

- [x] RED: merely retaining protected text while adding contradictory instructions
  does not establish eligibility; missing helpers/changed closure remain unresolved.
- [x] Deterministically verify body/frontmatter/paths/current dependency bytes and
  actual scope. A model's asserted helper or source path is never authority.
- [x] Obtain genuine model semantic assessment over authorized exact before/after
  data; strict output schema and actual native/usage coverage remain separate from
  its claimed score. No majority vote or invented reviewer independence.
- [x] Append receipts; do not UPDATE A's original provenance/status. Bind exact
  real operation input/output IDs/hashes and source/runtime/evaluator versions.
- [x] Preserve unknown/disagreement/owner-required. Typed owner arbitration is
  exact artifact/scope; product owner-confirm cannot waive semantic/runtime drift.
- [x] Revalidate after slow model/blob work and at consumption; stale/revoked
  receipts remain historical, never reactivate grants or accept changed bytes.
- [x] Candidate/final execution still closed until actual D view enforcement;
  semantic assessment alone never allocates holdout, composes, applies or activates.
- [x] GREEN protected-meaning/dependency/receipt/owner-scope tests; commit.

Task7 implementation component complete locally: actual isolated semantic role
uses improve_evaluate and real A before/after/provenance, protected context,
current source/grant/engine/evaluator pins and explicitly captured dependencies.
Shared RoleWorkflow factors the existing owned admission/native product/thread
lifetime from ProposalService, without exposing an arbitrary dispatch API.
Append-only semantic receipts retain genuine input/output/result/call refs; A
semantic_status/provenance remain unreviewed and unchanged.

Dependency evidence is explicitly a declared-reference graph, not a full runtime
qualification. Granted document bytes/native authority are pinned and transitively
checked; missing/ambiguous/cyclic refs remain unknown. Metadata/discovery projection
does not grant full file bodies. Executable helpers are read as data only, remain
unsupported/unknown for execution here, and require M6's real isolated runtime.
No new path, permission, helper command, model or source is accepted from output.

Strict reviewer schema and actual isolated renderer separate model verdict from
native coverage and deterministic findings. Model pass + native unknown stays
unknown; negative assessment is preserved even when the owner disagrees. Typed
owner arbitration pins exact receipt/binding and encrypts its private rationale;
owner evidence cannot waive source/native/dependency gates. Cold history/replay
survives revoke, but current evidence checks grants before decryption, then source
and native fences again after slow reads. Read-only consumption permits later
qualifying/awaiting_apply phases, without opening new reviews or final execution.

Evidence: semantic2 absent RED5.064s -> GREEN21.702s; dependency4 absent RED ->
GREEN.200s. Source-after-decrypt/private-reason2 RED21.753s -> core7 GREEN75.303s.
Revoke-before-decrypt, cancel-at-arbitration and malformed/conflicting verdicts
RED4/21.793s -> GREEN4/21.972s. Reviewer cancellation/DB-terminal receipt thread,
concurrent key and later-phase/schema7 GREEN41.075s. Actual granted/ungranted helper
integration2 GREEN23.369s and declared graph6 GREEN.303s; synthetic SDK throughout.

Affected9-script regression GREEN443s, including semantic18/161s and original
proposer18/165s, was followed by two narrow admission/input-binding corrections:
older draft schema must reject before preflight, and a real call over unrelated
input cannot mint tuning/semantic lineage. Four actual-workflow cases reproduced
RED33.879s; final negatives + normal propose/repair/review7 GREEN67.301s. Earlier
9-script sources are archived at exact recorded hashes with an explicit two-file
diff; reuse is conditional impact evidence, not exact-final-head proof. No full
sweep repeated solely for resume or these guarded boundaries. Final exact-C CI
and independent whole-C review remain Task9.

Configuration descriptor correction: main preparation/runner/workflow fixtures use
synthetic-model and synthetic CLI/SDK/profile pins; direct worker unit fixtures use
an Opus-shaped pin. Both inject synthetic engines/verifiers using installed SDK
DTOs0.2.116. Earlier T5/T6 evidence labels overgeneralized the fixture pin; their
source/log/results remain intact with a separate correction. They never proved
native account/model qualification. Actual Task5 Linux39901547032 and Task6
Linux39903506020 now SUCCESS on306e0871/07e84dc4 respectively; neither covers T7.
Current footprint32 files remains unqualified; Task8 public controls/full stop,
Task9 qualification/review/final CI and M0–M8 business/live acceptance stay open.

## Task 8 — owner controls and complete shared stop ownership

Interfaces: concrete owner preparation/proposal/semantic operations, cold lists/
history and current metadata; existing ExperimentService integrates all actual
preparation Trial links and native operation lifetimes in its final stop snapshot.

- [x] RED owner/token/CSRF/bounds/cross-brain/CAS/event tests for every new route.
- [x] Lazy main factories share existing TrialService and close operation services
  before underlying stores/sources. Ordinary GET does not capture/probe/recover.
- [x] Commit stopping first, join all admission/handoff operations, cancel linked
  real Trials and owned role operations outside writer, drain DB-terminal live
  tasks/checkers, take actual brain lock, prove exact scoped cleanup, final CAS.
- [x] No unrelated journal/reservation/role operation cleanup or settlement.
  Preserve B P2 regression, original acknowledgments and current metadata split.
- [x] Derive combined limits: B12000 comparison cells + up to2000 preparation
  cells; update all drain/recovery/attempt bounds consistently and test full-bound
  valid ownership versus oversized inputs. Include real role call attempts too.
- [x] Resume/recover never dispatches automatically or regrants. Frozen source
  drift/off/revoke closes new work while cancellation and usage settlement survive.
- [x] Add vi/en fixed errors and operating docs; broader wizard/navigation is F.
- [x] GREEN actual-main/lifetime/old owner/route/startup regressions; commit.

Task8 implementation verification:22/22 affected scripts GREEN768s sequentially,
with64 source/test hashes unchanged from run start through final verification.
Actual main verifies all23 experiment/operation/history routes' owner gates and
every POST's CSRF denial; eleven new routes are seven closed controls/four cold
history views. Genuine preparation/proposer/reviewer/owner-decision workflows,
repeated HTTP cancellation, slow preflight/result/publication/report threads,
all role attempts, held kernel locks, off/revoke and selected recovery pass.
Stopped retries replay durable metadata after service reconstruction, without
source decryption or redispatch. Trial drains match exact brain/request hashes,
so an empty scope does not join unrelated same-brain reservations.

The full14000/28000 SQL bounds test is structural, not a native/lineage claim;
smaller genuine integrations cover actual calls/workspaces/cleanup. Intermediate
RED logs include explicitly corrected test fixtures and are not exact-commit
reuse evidence. The final regression's source map/log hashes are retained with
the task ledger. Operator guide: `../../dev/agent-skill-m2c-operations.md`.
Task7 exact LinuxCI39907956153 succeeded on e1d71a33; current Task8 needs its own
Linux feedback. Profile33 remains unqualified with an empty registry; Task9 and
all later native/effective-view/business/live gates remain open.

## Task 9 — current-profile qualification, whole review and publication

Task9 native correction (actual failing blackbox evidence, not a scope change):
Windows kill-on-close, empty accounting and even disappearance of a named job
preceded native process-handle exit. Host death therefore needs a separate
cleanup supervisor, not a delay or a PID-list-only proof. Before any input gate
opens, it owns a suspended launcher job and durable fences at the actual shared
brain lock AND attempt lifetime lock. It drains on host-pipe EOF and removes
fences only after complete process-generation inventory and exit waits. Kernel
cumulative TotalProcesses must match birth notifications; a dropped notification
remains fail-closed. Supervisor death retains fences; no automatic deletion or
claim of crash cleanup follows merely from a terminal SQL state. New source is
included in the native profile hash (34 files); the registry stays empty until
the final complete current-source native qualification passes. Focused regression
adds actual host/supervisor death, suspended-launcher ownership, lost-inventory
faults and both recovery namespaces, then existing worker/lifetime consumers.

- [x] Run exact selected CLI/SDK dummy-HOME/config/auth + localhost fake-provider
  blackbox qualification for actual solver/proposer/reviewer profiles, including
  ambient source/plugin/hook/tool canaries, request identity and cancellation tree.
- [x] Save sanitized current source hashes and constraints; historical real-smoke
  remains06e75 and the later genuine C feasibility remains aa51b4b9; unknown
  reasoning/asset use stays unknown on all later profiles.
- [x] Only after current configuration/runtime verified, perform a necessary real
  technical role feasibility in a disposable authorized brain, with genuine usage.
  No rerun-until-win, alternate model, accepted business/semantic claim or live grant.
- [x] Run relevant migration/permissions/source/ledger/usage/learning/Team/prompt/
  UI/route/startup regressions and current old-v1/v2 baseline/report/lifetime checks.
- [x] Fresh whole-C independent review. Reproduce actual Important findings RED,
  fix and verify; no fake readiness/adapter or scope reduction to obtain green.
- [x] Rewrite both changelogs around the final verified implementation before the
  last CI run; reservation wording is not final release documentation.
- [x] Exact final-head Linux CI, fresh main/version/head checks, authorized straight
  merge, merged-tree equality and actual publication success. No deploy/restart.
- [x] Update engineering/business/rollout progress separately and continue D's
  real effective view. Positive final qualification, business pilot, activation,
  later agent/skill expansion and full M0–M8 remain open until actual evidence.

Task9 current checkpoint: exact34-source profile9dcf7184/CLI2.1.308/SDK0.2.116
passed solver5 and roles5 after the final dependency/preparation fixes and
fresh-main rebase. Dummy-provider qualification, actual selected-account
readiness, and historical real-model feasibility are separate proofs. The latter
made four actual calls on ddec90ad/profile aa51b4b9; baseline JSON shape failed,
business accuracy requires owner confirmation, semantic/native verdict is
unknown, and two A proposals remain unreviewed. No rerun sought a winning result.
The same whole-C reviewer closed both Important findings and approved only the
scoped fixture/main/changelog corrections afterward. Final21-script affected
regression passed663.451s in two source-qualified segments; only one standalone
test synchronization changed after the first15 successes, with an incorrect-join
negative control still failing. Exact-final LinuxCI39929264818 passed d05f4881;
PR801 merged2727edcc with identical tree5712b6ba, and actual publication39933347548
including Build & push succeeded. Task9's published verifier and completion
ledger ran successfully. D1 now starts from that released source in draftPR803;
full D/E/F/M2 and M3–M8 business/live gates remain open.

## Pre-flight interface audit for canonicalization

T1→T2: schedule identity/Trial link must be real, frozen and atomic; no fake arm.
T1→T3/T4: operation attempt/call/role identity must exist before native start.
T2→T5: preparation result lineage is not paired comparison evidence or holdout.
T3/T4→T6/T7: actual role events/usage/native result refs, never model authority.
T6→T7: immutable A proposal provenance stays unreviewed; receipts separate.
T1/T2/T4→T8: every actual owner participates in stop snapshot/locks/cleanup/CAS.
T4→T9: profile footprint includes new role-native code, not old proof inheritance.
T7→D: exact current semantic/source/dependency evidence cannot waive actual view,
runtime/config, qualification secrecy or owner activation prerequisites.

## Frozen concrete contracts (pre-flight self-review, 2026-10-23)

### Storage and preparation

Schema6 is additive in the existing resonance DB. Known versions1..5 migrate;
unknown versions reject before backup/write. Preserve earlier backup contracts;
known older schemas additionally receive one serialized, byte-preserved
`.pre-improvement-m2-generated.bak`, keyed by absence of improvement_preparations.
Fresh databases retain their original pre-M0 backup. Released B47f50f70 must
refuse schema6; CI fetches that actual source in addition to the old A reader.
DDL failure rolls back every new table/trigger/version. Cold readers do neither
migration nor decryption/probe.

`improvement_operation_schema.py` owns the following new tables. All scope FKs
include brain_id; append-only rows reject UPDATE/DELETE. SQL scope triggers must
check the actual parent relationships, not merely the existence of separate FKs.

| Table | Concrete columns and constraints |
| --- | --- |
| improvement_preparations | id,brain_id,experiment_id,context_id,definition_hash,schedule_hash,schedule_blob_hash,cell_count(1..2000),created_at; unique experiment/brain and id/brain; immutable |
| improvement_preparation_trial_links | preparation_id,brain_id,experiment_id,cell_position(0..1999),trial_id,request_hash,case_id,repeat(1/2),created_at; primary preparation/brain/position, unique trial/brain; exact v3 request and preparation identity; immutable |
| improvement_operations | id,brain_id,experiment_id,context_id,kind(propose/repair/semantic),role,purpose,candidate_id(nullable),parent_id(nullable),request_hash,request_json,input_hash,input_blob_hash,status,generation,attempt,created_at,updated_at; initial pending/gen1/attempt0; immutable request/identity, generation+1 transitions; no DELETE; unique one propose and one repair per experiment, one semantic per candidate |
| improvement_operation_attempts | operation_id,brain_id,attempt(1/2),status,call_id(unique FK agent_calls),lease_token,lease_until,writer_hash,engine_at,materialization_hash,workspace_json,result_json,failure_reason,created_at,updated_at; primary operation/brain/attempt; immutable identity/call, bounded lease/state transitions; actual ledger role/purpose/reason/mirror/brain/attempt checks |
| improvement_operation_observations | operation_id,brain_id,attempt,sequence,kind,payload_hash,blob_hashes_json,late(0/1),created_at; primary operation/brain/attempt/sequence; immutable |
| improvement_operation_results | id,operation_id,brain_id,attempt,result_hash,blob_hash,created_at; unique id/brain and operation/attempt/result_hash; immutable |
| improvement_proposal_publications | experiment_id,brain_id,operation_id,result_id,batch_hash,created_at; primary experiment/brain; exact successful propose/repair result; immutable |
| improvement_generated_candidates | experiment_id,brain_id,ordinal(1/2),candidate_id,operation_id,result_id,created_at; unique candidate/brain and experiment/brain/ordinal; exact publication/A candidate experiment/ordinal/result; immutable |
| improvement_semantic_receipts | id,brain_id,experiment_id,candidate_id,operation_id,result_id,binding_hash,binding_blob_hash,assessment_hash,blob_hash,created_at; unique operation/result/candidate; exact semantic operation and candidate/result scope; immutable |

Operation mutable statuses: pending -> reserved -> prepared -> running ->
completed|failed|interrupted|cancelled|not_run; intermediate states may settle
to interrupted/cancelled/not_run; terminal rows stay terminal. An infrastructure
retry may return interrupted/not_run to reserved only once (attempt2), only with
host-observed retryable reason and a new actual call; a completed/invalid product
never retries for a better answer. This retry transition is introduced/tested
with the runner, not exposed by Task1 metadata. Attempt statuses match their real
lifecycle; marked calls never refund. Terminal DB rows do not prove cleanup.

Pure `operation_request(value)` has exact keys version(1),experiment_id,context_id,
definition_hash,kind,role,purpose,candidate_id,parent_id,input_hash. The final two
IDs are explicit null except semantic candidate and repair parent respectively.
Input hash binds encrypted role input; request JSON contains no text, credential,
CLI path or caller-issued grant. Kind fixes role/purpose: propose/repair ->
improver/improve_propose; semantic -> semantic_reviewer/improve_evaluate.
Repair parent must be the same experiment's original propose operation.
`OperationRecords(assets)` supports cold `get/list` and transaction-owned
`_create_in(c,owner,request,input_blob_hash,expected_generation,event_key)` only;
it validates current experiment/context authority. It creates no call, lease,
native readiness or successful assessment. Positive attempt reservation waits
for Task3's genuine CallLedger purposes; using improve_probe is forbidden.

`preparation_schedule(definition,case_ids,case_seed)` yields exact keys version1,
experiment_id,definition_hash,context_id,case_set_id,case_set_hash,repeat_policy,
schedule_seed,cells. Cells are {case_id,repeat}, complete canonical tuning IDs
in deterministic hash order and every declared repeat; no arm/candidate fields.
`PreparationRecords(assets)` cold get/list and transaction-owned `_freeze_in`
persist an already host-derived exact schedule/blob/hash, current definition CAS,
and proposed -> preparing in the same writer/event. It does not authorize source
or native work. Task2's concrete `PreparationService(plans)` derives membership
from actual bound cases, compares the pure schedule, performs actual source
observations before/after slow native preflight, and atomically admits next slot
through SAME TrialStore/TrialTasks. No HTTP slot selector. Immutable links attach
actual v3 trials atomically; schedule rows never change to add links.

V3 has exact v2 common request fields, mandatory `preparation` instead of lineage,
baseline only, no qualification_id. Pins are the eight common pins (all v2 pins
except candidate_bundle_hash). Preparation is {version:1,context_id,
definition_hash,preparation_id,schedule_hash,cell_position}. Logical key includes
the full preparation identity plus actual case/repeat; no v1/v2 projection.
All Trial/Host/results/views/evidence consumers explicitly branch on version3.
Historical v1/v2 validators and hashes are retained, not generalized to accept
missing fields. No preparation result can satisfy a v2 comparison link.

Task2 completes preparing -> proposing only after every scheduled cell has an
exact published terminal result and no still-owned worker/checker. Unknown and
infrastructure outcomes remain visible; they do not become target deficiencies.
Arm binding/freezing is forbidden while preparation is incomplete; experiments
using the released manual path without preparation preserve existing behavior.
Manual staging still consumes A's global two proposal slots. Complete preparation
does not dispatch a proposer automatically.

### Real role boundary, usage and publication

Closed operation execution metadata branch precedes trial matching and detects
even malformed operation_id presence. Allowlist: experiment_id,operation_id,
attempt,execution_id,role,purpose,learning_origin,cli_session_id,cli_session_new.
Reject mixed Team/trial keys. execution_id is improvement_operation:<id>, origin
compose is learning exclusion provenance, not an implemented compose feature.
CallLedger context=improvement:<experiment>, mirror=that execution_id, reason=
improvement_operation:<id>:attempt:<n>. Reserve/attempt/event share one writer;
marker commits before worker ACK. Recorder rechecks actual brain/purpose/reason/
mirror/attempt/engine/model/marker, not caller metadata alone.

Extend existing usage recorder/store/index/reconciliation together. Add nullable
operation_id projection/index; keep old observation hashes and trial behavior.
`improvement_events(experiment_id,trial_id=None,*,operation_id=None)` rejects
mixed filters; recovery filters execution_id+attempt+source. Missing telemetry
for marked operations and operation-specific write errors remain partial/unknown.
No second money ledger. Actual effort/model observation and selected pins remain
distinct. Current isolated solver path never invokes conversation/self-lesson/
job hooks; preserve that isolation for operations and verify zero production
learning effects. No shared-conversation persistence is introduced in C. If later
added, durable trusted provenance must guard digest and delayed reaction replay,
not just a transient ContextVar or enqueue call.

`OperationWorkspace` uses operation IDs in receipts/journals/packets; its runner
receives the concrete SAME `TrialService.trials.workspace` brain barrier rooted
under trials/.executions. Sibling operations/.executions is prohibited. Profile
source footprint includes every new operation worker/renderer/workspace/native
adapter implementation. Operation profile keeps fixture-only native capability,
empty hooks/plugins/settings/skills and no arbitrary command/evaluator execution.
One actual operation supervisor owns preflight through final cleanup, including
repeated HTTP cancellation; no detached cleanup-ready callback.

Tuning inputs bind exact preparation result IDs/artifact/receipt/observation refs,
authorized snapshots/public contract/baseline/protected context and selected
config/source/recipe closure. Private answers and any qualification/regression
fingerprint aliases reject before model input. Full encrypted input is immutable;
bounded renderer rejects oversize required input rather than silently truncating.

Closed proposal output version1 is either {kind:patches,patches:[A manifests]} or
{kind:not_a_target_defect,reason:<bounded text>,evidence_refs:[actual input refs]}.
Max remaining A slots (two total including manual). Structural validation of the
whole batch occurs before any stage. One immutable repair operation for the whole
batch may see original authorized input + invalid output + fixed validation code;
it receives no new data or slot allowance. Publish A stage/event + publication +
generated links in ONE transaction, final source/grant/generation CAS. Concurrent
manual staging rejects the entire generated batch; no partial third candidate.

Semantic input pins exact A before/after bytes, deterministic dependency closure,
protected context, evaluator/config/source/grants, operation input/output refs.
Strict output version1: verdict pass|fail|unknown|owner_required, findings with
actual source/evidence refs and bounded rationale. No model-issued accepted
status/grant/native flag. Deterministic dependency result and model assessment
are separately represented within the append-only receipt blob; missing native
coverage cannot become semantic eligibility. A semantic_status/provenance stays
unreviewed forever. Future D consumption must revalidate exact current receipt,
actual view/runtime/source/config; a model pass cannot enable a candidate.

### Ownership, verification and self-review

Derived bounds: max comparison trials12000 + preparation2000 =14000, max solver
attempts28000. Max role operations4 (propose,repair,two semantic), max attempts8.
All drain/recovery/snapshot validators share these constants. Final stop holds
actual shared brain lock across scoped cleanup proofs and short writer CAS;
snapshot includes all immutable comparison/preparation links, actual attempts,
role identities/calls and live supervisors. Never broad-recover unrelated rows.
Source/off/revoked prevents new work, still permits settlement. Recovery/resume
does not dispatch or regrant. Existing stop acknowledgments stay historical.

Task1 verification: standalone test_improvement_operations.py and existing
test_improvement_experiments.py / test_improvement_store.py. Expected RED first:
schema6/preparation/role metadata absent. Expected GREEN: real migration/history/
old-reader/rollback/concurrent backup + scope/CAS/replay/cold denial tests pass.
Later task commands are their focused standalone scripts plus the relevant
existing consumers listed in each task; whole exact-head Linux CI remains final.

Self-review: verified published schema5, actual transaction-owned CallLedger,
HostContextStore/ExperimentPlans, strict v2 and all downstream version consumers.
Independent read-only usage audit confirmed operation identity would otherwise
be rejected/dropped in turn_context, recorder, index and reconciliation; all are
included. Resolved baseline dependency with typed preparation, shared lock-root
hazard with actual concrete barrier, immutable A evidence with separate receipts,
and aggregate stop bounds. No alternate model, readiness stub, fake trial, hidden
holdout input, activation or reduced Goal scope. Native capability and business
effect remain unproven until their actual subsequent checks.
