# Agent and skill improvement M2D1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Run a real isolated baseline/candidate comparison using exact immutable
skill views and the existing Trial ownership/usage chain, preserving every
legacy protocol and all unknown/owner/live gates.

**Architecture:** One byte-exact host-derived view resolver constructs baseline
and candidate assets without writing canonical files, M0 target pointers or a
global native mirror. Append-only comparison bindings join these views to actual
source/semantic/edit authority. A deliberately new v4 request and v2 workspace
manifest traverse all existing Trial/native/evidence/result/stop consumers.

**Tech:** Current Python3.12, FastAPI, same resonance SQLite, RevisionBlobs,
existing native process supervision and actual CallLedger/usage. No second
runtime ledger, fake Trial/Operation, arbitrary shell or provider switch.

**Spec/authority:** Full agent-skill spec9–14/22–24 and Goal3/5/6/12. Published source is C2727edcc, tree5712b6ba, identical to tested d05f4881.
Preserve engineering/business/rollout evidence separately. D1 is an engineering
subproject; D remains OPEN until the same resolver is integrated and verified
through production router/lazy/hub/native task/resume paths. E still owns atomic
manual live-pointer apply/revert/canary; F owns the complete6/6/6 operator flow.
This delivery split does not reduce D or full M0-M8.

Source update: C is now published0.296.0, actual merge
2727edcc5cdfab6f2dcf2e2871164f22f2771f92. Its tree
5712b6ba79720a5a44a43d3cecd85cff84f3cd21 exactly matches the independently reviewed
and tested d05f4881; CI39929264818 and actual publication39933347548 passed.
D1's exclusive branch now reserves0.297.0 in draftPR803 before code; reservation
c4991ec8 passed the bilingual changelog test. No source/runtime change yet.

## Global constraints and release preflight

- [x] Verify C finalCI39929264818, actual squash tree, and publication, then fetch
  main/open reservations and reserve the next free version in its own draft PR.
  Use the suitable existing managed worktree; preserve both synthetic histories
  and generated test keys. Never alter the original D:/Project checkout.
- [x] Resolve the actual published C commit for schema6 old-reader verification
  before any schema7 code or CI-fetch pin is written.
- Preserve old v1/v2/v3 request hashes, logical slots, historical replay and
  rejection of changed candidates/final runtime through those legacy versions.
- Only one user skill body changes; retain protected bytes/meaning, frontmatter,
  identity, disabled state, dependencies, model/reasoning, grants and ownership.
- Native enforcement/source/config qualification precedes real account inference.
  New source invalidates the old9dcf7184 registration; no readiness stub or
  generic environment/HTTP exemption can enable an unknown profile.
- Missing reasoning, semantic input use, asset use or telemetry remain unknown.
  Never upgrade C's combined verdict, A's immutable unreviewed status, or a
  comparison integrity unknown. An inconclusive comparison keeps baseline.
- Task impact and source-qualified reuse first; focused RED/GREEN, affected
  sequential regression at task end, early Linux paths/SQLite feedback, one
  independent whole-D1 review at stability and scoped fix verification only.

## Probe authority and preserved unknowns

The existing C native report deliberately retains `actual_reasoning` and
`actual_input_use` unknown. Its combined semantic/native verdict therefore cannot
be treated as a positive eligibility proof. D must not simply change that result
to pass in order to execute a candidate.

Define a separate host-derived **authorization for an isolated technical probe**:
current owner experiment/source/edit grants, exact before/after/provenance and
dependencies, settled protected-meaning assessment, exact qualified isolation,
matched model/session/installation and complete ownership must all be validated.
Known native failures or missing security/isolation/source evidence block before
call reservation. Unknown protected meaning remains owner-required; an owner
cannot erase a negative model assessment or native security failure. Any allowed
observational unknown must remain in receipts, result integrity, reports and
eligibility. Never infer a quality win or live permission from probe execution.

The permitted observation-only unknown IDs below follow spec10.3/13.1 and the
actual C check inventory; record this ruling in the task ledger. Do not introduce a public
`allow_unknown`, `candidate_ready`, `semantic_ok` or test-only production flag.
Fixtures may simulate an owner only in explicitly synthetic disposable scopes;
they are not human business/semantic acceptance of a real brain.

Self-review ruling under Goal3/5/6/12: the only observation-only
native unknowns a technical probe may retain are `actual_reasoning` with reason
`native_reasoning_unobserved`, and `actual_input_use` with reason
`semantic_input_use_unobserved`. Require the exact current ten-ID operation
check inventory with no duplicate/missing IDs; every other check must pass.
Either of those two IDs failing still blocks. A missing/mismatched model,
session, installation, tool inventory, side-effect boundary, protocol or complete
result cannot be waived. Require semantic assessment pass, or an unknown/
owner-required semantic component resolved by an exact current owner pass;
negative assessment or finding remains rejected. Dependencies must pass with
unchanged exact source/authority and no executable/unresolved node. This yields
only an internal `ProbeAuthority`, never a changed C combined verdict, semantic
eligibility flag, comparison integrity pass or live grant.

The source/spec self-review retains the following mandatory tests: observation-only unknown permits a labeled isolated probe and still
produces unknown/inconclusive comparison; every other native unknown/failure,
missing observation row, semantic failure/unresolved owner gate, changed grant
and dependency unknown denies before reservation. No public bypass parameter.
This rule preserves B's full native-check quality gate; it does not remove
actual_reasoning/asset_observed_use from comparison projection. Final independent
D1 review must judge this behavior and the exact actual evidence, not infer
approval from the existence of this plan.

## Task decomposition

## Review Focus

1. Cross-brain aliases, same-name paths, disabled canonical shadowing, UTF-8/BOM/
   CRLF and changed native ACL/file incarnation must not load a different view
   or promote a historical receipt (Tasks1/2/4).
2. Terminal SQL before published result/actual cleanup, concurrent owner-next,
   and cancelled admission handoff must not burn an immutable later cell or
   release owned capacity (Task3).
3. A source/grant/config edit during slow encrypted I/O, native spawn or result
   publication must fence current work and preserve actual cleanup/usage rather
   than replace a frozen baseline with a newly captured source (Tasks2–4).
4. Observation-only unknowns, stale semantic proof, owner-required protected
   meaning and model failures must stay distinct; no probe permission may
   become a quality win, rewritten A status or live eligibility (Tasks2/4).
5. Qualification consumption/crash/late retry and new runtime-format links must
   preserve every expected pair, old history and sealed answers without extra
   final candidates, double-counted cells or unrelated cleanup (Tasks3–5).

### Task 1 — immutable effective-view identity and schema7

**Files:** new `server/improvement_view_protocol.py`,
`server/improvement_view_schema.py`; modify `server/improvement_store.py`;
new `tests/python/test_improvement_views.py` and
`tests/python/test_improvement_view_schema.py` (actual SQL/backup/old reader).

**Interfaces:** `view_manifest(value)->dict` validates closed version1 data and
`view_hash(value)->str` hashes that canonical projection. It contains exact brain,
target/base/candidate identity, source/context/grant/config/semantic proof hashes,
ordered asset refs/hashes and protected dependency identities. IDs/blob hashes
that would create a self-reference stay in the outer SQL record. No caller
declares coverage, successful review, native readiness or authority.

Store immutable views, immutable ordered view assets, and one immutable
comparison-view binding in the same resonance DB. Bindings reference the actual
brain/comparison plus baseline/candidate view IDs, v4 runtime, encrypted proof and
current semantic receipt. Composite FKs/triggers prevent cross-brain/experiment
joins; cold readers neither migrate, decrypt nor probe. Do not create M0
canonical revisions or move target.current_revision_id for a candidate.

Preserve the exact released B/C table and guard definitions. A fourth additive
`improvement_view_trial_links` table belongs to Task3's actual v4 runtime, rather
than widening or repurposing legacy v2 links. Its comparison must already have
the exact immutable view binding. Additional guards prevent any legacy link
after a view binding and prevent binding after any legacy link. Every stop/
report/recovery/bounds consumer must deliberately resolve the comparison's one
runtime format, never double its allowed cells or omit its new actual links.
Do not fake a v4 Trial row to make Task1's metadata tests positive; genuine
Trial/call/link publication is Task3's completion gate.

- [x] RED: schema6 lacks view tables; forged body/hash/source/variant identity,
  mutable/foreign links, duplicate view variants/bindings and unknown schema reject.
  Legacy/v4 runtime exclusion remains Task3 as explicitly separated above.
- [x] GREEN: real encrypted metadata save/cold read, concurrent
  one-time byte-preserved migration backup, crash rollback and old-reader refusal.
- [x] Verify actual published C reader refuses schema7 and its backup restores
  exact historical schema6. Preserve all earlier backup boundaries.
- [x] Commit verified task; record exact source/test/command/runtime evidence.

Task1 local implementation evidence: six sequential affected scripts passed104
tests in221.921s, source/runtime/log-bound in
`../evidence/2026-10-23-m2d1-task1-verification.json` (SHA256
b9d7c51fd9725111678365f667b4af2168738b73329e89475ba2d700d52f76f8).
The actual task-done verifier checks committed bytes against the full retained
dependency/log evidence, without repeating already-passed tests. This is local
foundation completion; checkpoint Linux CI and full D1 review/runtime/final CI
remain open. WSL is unavailable; use the existing PR's automatic Linux workflow.

Task boundary ruling: positive atomic pair publication/CAS/event replay belongs
to Task2's concrete host publisher, which owns current source/semantic authority.
Task1 proves the schema/immutable scoped metadata and pure identity without
inventing a publish API or pretending metadata is execution authority. Task2
must prove the same event key returns its exact stored pair, changed payload
conflicts, and a second insert/source-CAS failure rolls back both views/binding.

### Task 2 — current host view capture and source authority

**Files:** new `server/improvement_views.py`,
`server/improvement_view_sources.py`; use actual SkillCandidates, ExperimentPlans
and SemanticReview; new `tests/python/test_improvement_view_sources.py` and
`tests/python/test_improvement_view_authority.py` (actual permissions, links,
source incarnation, line endings and owner-meaning integration).

**Interfaces:** `EffectiveViews(plans, semantic)` accepts concrete same-store
dependencies. `freeze_comparison(principal, comparison_id, *,
expected_generation,event_key)->metadata` derives both views under actual current
authority, then commits view rows/binding/event atomically. `read_existing`
returns cold metadata; `load_current` explicitly rechecks current authority.
Host interfaces are private; HTTP receives only the explicit closed control
fields and never constructs a ResolvedView/ProbeAuthority. The shared resolver returns exact bytes and identity for a given frozen
view/asset; no fallback to canonical, root-relative same-name or global mirror.

Task2 implementation checkpoint: first12 source/atomic/policy tests passed95.073s.
Actual same-event concurrent publication RED exposed stale-generation failure
after the first writer committed; replay now rechecks the exact immutable event
on source/generation denial, without granting new work. Pure RED also exposed
missing-verdict KeyError and ignored native aggregate failure; both now deny.
The service derives meaning/dependency/native observations only from actual
current C evidence, keeps its combined unknown and A unreviewed unchanged, and
stores the exact actual owner-event reference when required. This metadata/source
boundary is not D native qualification or real Trial admission. Task2 remains
open through its further authority/mutation tests and affected regression.

- [x] RED: changing/replacing/deleting/disabling/revoking source during encrypted
  I/O cannot publish or resolve a view. Actual native-preflight changes must deny
  before CallLedger reservation/query in Tasks3/4's real consumers; that integration
  remains mandatory rather than being simulated by Task2 metadata tests.
- [x] RED: existing comparison cells prevent retrospective runtime binding; a
  third candidate, unrelated semantic receipt, changed protected meaning or an
  executable/ungranted dependency cannot expand the view.
- [x] GREEN: baseline/candidate differ at exactly the owner-authorized body;
  all other protected/context/dependency bytes and identities match. UTF-8/BOM/
  CRLF remain exact, with no canonical or global mirror write.
- [x] Actual host pair publication is one writer/event with current generation
  CAS, cold exact replay, conflicting-payload rejection and complete rollback
  when a second view/binding/source fence fails. No partial eligible view exists.
- [x] Add actual ACL, directory/file incarnation, symlink/junction and Linux
  case-distinct brain tests using shared stable readers. No lowercase hash as
  authorization. Verify deterministic replays after off/revoke remain historical.
- [x] Commit verified source capture and exact-byte resolver.

Task2 local verification: five sequential affected scripts passed76 tests in
392.830s. Portable report `../evidence/2026-10-23-m2d1-task2-verification.json`,
SHA256588f7dba351d6d4253039819179207e467306163b14bfb7447d8c700d08fc41e.
Task-done validates actual committed source/runtime/log hashes without repeating
passed tests. New D native integration and Linux source/authority branches remain
unverified until their actual consumers/CI run. Earlier Task1 LinuxCI39938959026
passed the new schema15/protocol11 but failed three older migration fixtures;
correct those exact fixture expectations/drop lists next, before pushing this
checkpoint. No branch integration, new native qualification or live claim.

The three Linux-feedback fixtures are now corrected locally and their74 tests
passed sequentially34.537s. Evidence SHA256
641a71c203e8e42d2a09ee51c17195bcf2b1ce2af999fe2f8dc043a73bdaa5e0.
Only three named test methods changed; AST comparison verifies all imports,
fixture helpers and other methods unchanged from verified Task2 commit68dc6c26.
Application and all Task2 selected source bytes remain exact. Reuse its scoped
76-test evidence; require fresh Linux CI after this checkpoint is pushed.

Task2 completion scope: run the two new source/authority scripts, pure view
protocol, existing dependency-identity and comparison-plan regression sequentially.
Reuse Task1's exact schema7/migration/store evidence and C's source-qualified
structural/candidate/semantic implementation evidence: those source/helper bytes
are unchanged and the new tests traverse their actual concrete services. Full
final-head CI still runs every mandatory script. No blanket improvement sweep.

Additional REDs: view capture initially used the plan's all-case source projection;
the actual holdout-blob spy caught that read. It now requests the existing tuning
projection, including for common source resolution of a final view; actual final
case admission owns its separate qualification grant. Another negative fixture
constructed valid scoped encrypted SQL metadata without a real publication event;
load_current now requires the exact immutable event/result/request-hash/generation
history as well as current source/semantic proof. Cold metadata remains historical.
The source fence after both inserts rolls back all view/binding/event rows.

Supported byte tests retain existing discovery semantics: YAML CRLF and plain BOM
are byte-exact; BOM plus YAML remains rejected as ambiguous by unchanged M2A.
Windows native DACL mutation/rejection/restoration is actual. The first fixture's
icacls /restore cleanup lacked privilege; DACL-only native restoration now restores
the exact original descriptor hash without changing owner/group or requesting
privilege. This changes only disposable test cleanup, not source authority policy.

### Task 3 — explicit v4 admission and full paired/final lineage

**Files:** new `server/improvement_view_admission.py` and pure
`server/improvement_view_trial_protocol.py`; extend the actual Trial
request/host/lineage/SQL-trigger consumers, ExperimentService and comparison
runtime integration; focused new `test_improvement_view_admission.py` and
`test_improvement_view_trial_protocol.py`.

**Interfaces:** host-derived v4 preserves explicit comparison cell/case/repeat
lineage and adds exact frozen view/binding identity. Owner HTTP still cannot
select a cell, issue a pin/grant or submit an authority verdict. Only the
concrete service chooses the next frozen slot and reserves through the SAME
TrialStore/CallLedger transaction and real TrialTasks handoff. No fake baseline
or regenerated deadline for an existing admission. Legacy versions remain closed.

Frozen v4 shape: the exact v2 common request fields plus required `view`, with
version4. `view` has exactly `view_id,view_hash,binding_hash`; view_hash is the
canonical immutable manifest hash, not the raw skill content hash. Existing
candidate_bundle_hash remains the typed A arm-envelope hash, not an installed M0
bundle. Preserve the complete v1 comparison lineage and optional qualification
ID shape; actual scope/source/claim authority is separately checked. A temporary
v2 copy may validate common pure shape only; never use a projected hash, request,
logical key, Trial or runtime authorization. Return/hash/reserve the full v4.
Logical keys use their own improvement-trial-v4 namespace and include the exact
view ID/hash/binding, comparison/pair/cell/case/repeat/variant. Deadlines remain
outside logical identity, inside full request hash, and exact replay never resets
the original deadline.

Before v4 consumers, align the view manifest/proof comparison_hash with B's
actual comparison_hash(row), which includes kind and cell_count as well as the
matrix. Task2's prototype field used matrix_hash while its other scoped pins
still bound the actual comparison; do not perpetuate two meanings for one name.
Observe focused RED, update the producer/proof and genuine metadata fixture,
then verify affected source paths. No D real-model/production view exists yet;
older prototype views remain cold history and cannot silently gain new authority.

As soon as any v4 admission/runtime entry becomes reachable, add its actual
source dependencies to PROFILE_SOURCES in that same change. That invalidates
the old C registration immediately; never leave v4 reachable under C's9dcf
qualification while waiting for Task4. Task4 completes enforcement scenarios and
registers only the final exact footprint. Unit SDK fixtures remain labeled
technical; default actual native readiness must stay false until qualification.

Actual literal-link consumers found before edits: experiment_lineage,
experiment_service snapshots/stop union/next scheduling, comparison_results,
experiment_admission, trials, trial_views and views. Version-specific consumers
also include private_review, trial_host, trial_decisions, trial_results and
trial_checks. Extend each deliberately; a second independent12000-cell allowance
for new links would violate the shared14000/28000 bounds.

Task3 historical-proof checkpoint: full v4 requests now traverse the shared
immutable comparison proof without projection to v2. Separate SQL/blob history
authenticates both manifests/assets, exact C semantic receipt/binding, actual
publication and an exact pinned owner event when present. The v2 wrapper keeps
its own validator/link/hash and rejects a view-bound comparison. Common cold
metadata/publication checks are shared with EffectiveViews; current file/native
authorization remains a separate mandatory boundary. Six new checks plus one
added independent owner-history case and49 existing affected checks passed
(56 total;492.648s of recorded unittest/subprocess time, with basis per row).
Portable evidence `../evidence/2026-10-23-m2d1-task3-history.json`, SHA256
170d0de3145bf6932c1d01b5040a55db71be3f3287d3d08b1fd3ba8bdea45d8a.
No real v4 Trial/Call has yet been created; root dispatch still rejects4. Task3
remains OPEN. No actual query, new native qualification or business/live proof.

Task3 actual-reservation checkpoint: the real TrialStore now creates v4 Trials,
existing improve_probe Calls and exact view links atomically after concrete
same-store source/semantic/lineage observation. Real Principal flows through all
current hooks; historical replay/cold metadata survive off/revoke without blob
reads. Descriptor mismatch denies before plaintext, and source edits after real
ledger reservation or the last history read roll back/deny. The first focused
RED/GREEN preceded nine sequential affected checks:140 tests,231.248s wall time.
Evidence `../evidence/2026-10-23-m2d1-task3-reservations.json`, SHA256
bde6b073ae78acbf4e220cd5363fa40fd16e1f4bc5dd3d2ac225cd83a0b8a796.
The reachable source footprint expanded in the SAME change to76 files, hash
51b62052babed7b4ceee02f8edf5a7101c92cefe0873280fc6148a6b7dcf7e3c.
No registration matches it; actual native readiness remains false. Engine markers
for new reservations are NULL. V4 materialization is explicitly closed until
Task4's real workspace path, and final cells until existing-registry ownership.
Shared bounded consumers/admission/kernel barriers are next. Task3 is not done;
this draft cannot be released or described as complete v4 execution.

Task3 lifecycle checkpoint: stop/recovery snapshots and scoped attempt SQL now
include both actual comparison formats under ONE12000-cell bound, plus existing
prep2000/attempt28000 bounds. Next metadata selects the frozen format and checks
terminal attempts, exact published result pointers and actual workspace cleanup.
The original three real-v4 reproductions RED47.063s became GREEN47.098s. A mixed
legacy/view budget fixture uses two genuine reservations; no future SQL rows or
successful results are fabricated. Final four affected scripts passed28 tests
sequentially182.812s. Evidence `../evidence/2026-10-23-m2d1-task3-lifecycle.json`,
SHA25615071ce22cdd11604343a869889c913881577b6470707514c6d1aca9552641c8.
Current76-source profilebc7f176a is still unregistered. Owned admission/kernel
barriers, v4 report consumers and actual final-registry ownership remain OPEN;
the metadata cleanup check alone does not prove the complete handoff boundary.

Task3 owned-next checkpoint: concrete ComparisonSchedule is shared by service and
ViewExperimentAdmission. Closed view event payload is exactly experiment_id,
comparison_id,expected_generation; its position comes from the frozen schedule.
Cold exact replay precedes current authority/kernel checks. New admissions hold
the actual brain barrier through fresh scoped idle/schedule checks, current
source/semantic/native preflight and atomic existing Trial/Call/view-link/event.
Legacy service next also holds that barrier without changing legacy event bytes.
New view source is bound to both same-store TrialStore instances and the host.
Both new modules joined the native footprint in the SAME reachable change.
Seven scoped next/handoff/cancellation checks plus64 affected API/lifetime/stop/
profile checks passed (71 total;401.851s recorded time, basis per evidence row).
Evidence `../evidence/2026-10-23-m2d1-task3-owned-next.json`, SHA256
4d9df2ba736bf8fc736dc2d8e0e19d10b8f24cf406d7ee0dc99684b1aa944221.
Current78-source profile058166e7 remains unregistered, with zero real model calls.
Retained-host/closed-workflow v4 resolver lifecycle still needs its scoped audit;
no task/resume support is claimed. Actual v4 report projection, existing final
qualification-registry ownership, real workspace/native and public controls
remain open. Task3 NOT done. Earlier Linux39949800035 succeeded only ab5dc1ef;
Linux39952941333 on52c79f1c is still running and cannot qualify this new code.

Linux39952941333 completed FAILURE on52c79f1c: only operation_worker's explicit
expected source set still pins C34. Production intentionally expanded to76 there
and78 by owned next; do not remove source coverage to satisfy the old fixture.
The one expected-set test now explicitly lists all78, preserves exact equality
and independent per-file hash, and adds duplicate/count refusal. Local RED1
0.004s; full worker9 GREEN3.493s and default unregistered-profile denial1
GREEN0.021s. AST proof confirms imports/fixtures/all other methods unchanged;
all production source bytes match the71-test owned-next checkpoint. Evidence
`../evidence/2026-10-23-m2d1-task3-footprint-fixture.json`, SHA256
43f43c2855698e1c8e1a8a161c28c4c873630cb86d2055ecb06a15e6890bd947.
This qualifies reuse of that scope; it does not replace fresh Linux/final CI.

Retained-host audit found a real reconstruction failure: after both old services
closed, new view admission still used the closed semantic resolver (RED1,14.657s).
Replacement now derives from the exact same-store semantic/Trial owner chain and
BOTH successful completed asyncio close futures, with no constructor I/O or
caller override. Live, missing, pending, cancelled and failed close states refuse
replacement. Frozen rows/requests/hashes stay unchanged. Original2 GREEN33.064s,
then one added failure-state check plus affected next/API/lifetime/worker/stop
checks passed32 total (276.518s recorded, basis per row). Evidence
`../evidence/2026-10-23-m2d1-task3-view-lifetime.json`, SHA256
c56e88ee52a9813711021db8d93984f53594d0ee42bdbb519eab8679dcf7c60e.
Current78-source profilebfda8912 remains unregistered. This resolves concrete
service reconstruction only; D2 ordinary task/session resume is still unverified.
Task3 v4 report projection/final registry and Tasks4/5 remain OPEN.

Next report interface ruling before code: keep the existing closed version1
comparison-report envelope and immutable historical bytes. It is runtime-neutral;
exact result_refs pin each actual TrialResult and its full request/view identity.
An explicit v4 TrialResult has version4 and effective_view exactly equal to the
closed request.view; no runtime v2 projection or hash substitution. Preserve all
18 B native checks and unknown/inconclusive outcomes. Snapshot selects one actual
comparison link format from its immutable binding, authenticates publication and
view descriptors in SQL without warming files; explicit current report creation
requires the concrete current view/semantic source and tuning-only common source
capture. Cold historical reads/replay do not require current grants/files/native.
New pure tests use labeled untrusted report dictionaries only; integration tests
use genuine pending v4 Trials and never fabricate successful future results or
qualification. Affected modules: comparison_results plus existing linked readers;
tests: new view_reports, existing comparison_results/reports/plans and view/source
authority boundaries as their actual changes require. No Task3 completion yet.

Task3 report checkpoint: 63 checks across view_reports6, comparison_results19,
comparison_reports13, comparison_plans24 and NativeFootprint1 passed sequentially
in166.953s on one unchanged source map. Actual pending v4 Trial/Call is captured;
no successful native result is fabricated. New reports recheck current meaning;
historical replay/read preserves exact report bytes, including all-absent result
refs on the older metadata-only schema7 prototype. Explicit v4 projection retains
all18 native checks and the comparison-report v1 envelope. Portable evidence
`../evidence/2026-10-23-m2d1-task3-reports.json`, SHA256
aabb253c30404d6155ba2bba92981285462da56e9e6439c5218abc363567609d.
Current78-source profile4e3ecee0 remains unregistered. Final registry, actual
workspace/native and public controls remain OPEN; Task3 is not complete.

Next additive table contract (before SQL): `improvement_view_trial_links` columns
are `comparison_id,brain_id,experiment_id,cell_position,trial_id,request_hash,
pair_id,case_id,repeat,variant,view_id,view_hash,binding_hash,created_at`.
Primary key is comparison/brain/cell; Trial/brain is unique. Composite FKs bind
the actual comparison-view binding, experiment, Trial and effective view. Its
insert guard requires full version4 request/lineage/view pins and the actual
variant asset. New additive guards reject a legacy link after a view binding
and reject a view binding after any legacy link. Existing B/C SQL definitions
stay byte-identical. Positive v4 rows wait for actual admission; negative tests
must use genuine C-preparation/B-baseline Trial rows, never fake future Calls.
Cold partial7 prototypes remain readable but cannot acquire new view authority.

- [ ] RED: a valid-looking v4 caller cannot bypass the actual view binding;
  candidate/final requests through v1/v2/v3 remain rejected without decryption.
- [ ] RED: pending, terminal-without-result or SQL-completed-but-still-closing
  prior cells cannot burn the next immutable comparison link/call. Hold the
  actual brain execution barrier across slow admission and final SQL CAS, as
  preparation already does; historical replay precedes slow work.
- [ ] GREEN: genuine two-arm Trial/call/link admission, concurrent next callers,
  stop/off/revoke during preflight, cancelled HTTP handoff, crash and late result.
- [ ] Extend actual sealed final qualification reservation/consumption links;
  one final candidate only, no tuning fingerprint alias or reused consumed
  holdout, no private answers in solver/improver/view. Refund/usage rules unchanged.
- [ ] Verify current v1/v2/v3 metadata/reports and older reader histories remain
  exact; commit the complete new admission boundary.

### Task 4 — actual workspace/native view and result evidence

Dependency ordering: implement tuning materialization now as the prerequisite
for genuine result/selection evidence. Task3 final-registry ownership remains
open; no fabricated eligible report or selected candidate may unlock it. This
unit changes sandbox manifest validation/effective hashing and TrialStore's
explicit v4 materialization through a new concrete view-materialization module.
Workspace v2 is precisely v1 plus `effective_view` with the request's closed
`view_id,view_hash,binding_hash`; asset ID is the real baseline revision or A
candidate, never a manufactured M0 bundle/revision. V1 prompt/hash bytes stay
unchanged. Native readiness remains denied on the changed profile. Test scope:
new real-reservation/materialization tests, sandbox, TrialStore, view reservation
and native-footprint fixtures; actual native/result integration is a later unit.

Tuning workspace checkpoint: actual linked pair now materializes/prepares v2
workspaces through the existing TrialStore and encrypted source/solver inputs.
Exact baseline revision/A candidate IDs and body bytes, common context/case,
canonical preservation and final source-race rollback are checked. V1 prompt and
effective hash are byte preserving; v2 effective hash includes its exact view
descriptor. All5 affected scripts passed69 tests sequentially in171.812s on one
frozen source map. Evidence `../evidence/2026-10-23-m2d1-task4-materialization.json`
SHA25687d9d7306dc3226ac3f2a68860bc4277eec699c08535e4ba4892c5aed38d76d3.
New79-source native profilebeddb90238b1b8d1fd21f0e547c0ecff12cb677e5a76f9ceaec6d48add23bfdd
is unregistered. Actual v4 receipts/checks/results, native qualification and final
registry remain open. No native query/result/eligibility was manufactured. Task3
and Task4 remain OPEN; no task-done marker.

Next unit: TrialProfile installation receipt v2 is exactly receipt v1 plus
`effective_view`, generated from the actual bound workspace v2. Pure invariants
explicitly validate full request4 and require workspace2/receipt2 and exact view
identity; other request versions retain workspace1/receipt1. Full18 check IDs and
unknown effort/asset use remain unchanged. TrialResults writes/reads version4
with full request hash, experiment_lineage and effective_view; owner recheck
retains these exact pins. Actual Runner/CallLedger/encrypted products/cleanup is
tested with a clearly simulated adapter, never claimed as native qualification.
Affected sources: claude, trial_checks, trial_results; callers: worker, Runner,
comparison projection/history/owner decisions. Tests: new view execution/checks,
existing Claude/checks/results/experiment execution and workspace/footprint.

Receipt/result checkpoint:75 checks passed across the direct owned pair1 and
seven sequential affected commands,176.126s recorded (unittest vs subprocess
basis per row). The direct pair reused unchanged source bytes rather than being
rerun solely for bookkeeping. Actual owner schedule, Runner, Trial/Call start,
encrypted products/results and cleanup produce/read explicit result4 with full
request/view pins. After off/revoke, both actual result4 histories and comparison
history stay cold/exact. The adapter is simulated, both results remain non-pass
and selection unsupported; two cells are not a full A/B or final qualification.
Pure record checks preserve all18 IDs and reject changed view/legacy receipt,
with reasoning/asset-use unknown. Native Profile derives receipt2 from its real
workspace2 and returns detached descriptors. Legacy Claude/checks/results and
actual v2 execution regressions pass. Evidence
`../evidence/2026-10-23-m2d1-task4-view-execution.json`, SHA256
4d7c1b9f7ea74b27e1b335ae93274561fb8290e2a82915ed61bc66bb54aea721.
Profile79/2192bf86b6a49e0fa2d524324db79c4a52493d91f37c56b9f183a4fa8b922e4d
is UNREGISTERED. Final registry, exact native qualification and public controls
remain OPEN; neither Task3 nor Task4 is complete.

Final-registry prerequisite audit: the existing improver builder rejects tuning
families aliased to qualification/regression or any claim, without a consumed
exception. Effective-view current capture did not call this common SQL guard.
Before opening final consumption, share that existing rule and apply it before
any current view plaintext read. Test with genuine owner-created case sets that
relabel an actual tuning snapshot, before freeze and after publication; current
work must reject while immutable cold history remains readable. Affected sources:
experiment_qualification, improver_inputs and view_sources (all already native
footprint members). Tests: new view holdout boundary, existing improver input,
view source/reservation and native footprint; no fabricated claims/eligible data.

Alias boundary checkpoint:3 genuine owner-API cases plus improver_inputs10,
view_sources16 and actual pair reservation/native-footprint2 passed31 checks,
262.843s recorded with timing basis per row. New/current capture rejects before
plaintext; cold metadata remains exact. AST extraction confirms both original
improver SQL statements remain identical after sharing. Evidence
`../evidence/2026-10-23-m2d1-task3-view-holdout.json`, SHA256
07ef50951c43236be3128be3e9740bed1521e94e1e31c1a0bf178c88517cf6fc.
Source79/b46e2cc3744067a9d367781b544df8b036de760c385319d7f5a4d4621459b771
remains unregistered. No final claim/eligible evidence fabricated; Task3 OPEN.

Final-registry contract before its SQL implementation:
`improvement_view_qualification_links` has columns `comparison_id,brain_id,
experiment_id,reservation_id,case_set_id,candidate_id,selection_event_key,
reservation_event_key,selection_hash,binding_hash,pins_hash,family_hash,created_at`.
PK is comparison/brain; reservation/brain and experiment/brain are independently
unique. Composite FKs bind actual comparison-view binding, experiment, existing
CaseStore qualification, case set, A candidate and both immutable events (reserve
event FK deferred to its same transaction). Scope trigger requires final kind,
the actual selected ordinal/candidate/definition and nine matching actual pins.
Code authenticates selected report publication/full18/current policy and exact
view/semantic/source; an unqualified or inconclusive selection cannot reserve.
One existing global claim covers qualification fingerprints, preserving spec7.3
and the actual CaseStore distinction from reusable regression checks. First
qualification materialization consumes it before input is returned; baseline,
candidate and repeats share it. Regression cells carry no qualification_id and
record their normal exposure, but still require the exact owned final binding;
a qualification family cannot be relabelled as regression, even after consumption.
No release, foreign/consumed-pool adoption, holdout alias reuse or new registry. A genuine
selected final comparison/view is required; no fabricated eligible/report/final
Trial may be used to claim an exercised positive path. Historical link proof is
immutable/cold; current admission separately revalidates policy/source/meaning.

First final-registry unit installs only the frozen additive link/SQL guards;
runtime final requests remain closed. Tests use a genuine tuning comparison and
genuine unrelated legacy CaseStore reservation to prove no adoption, missing/
changed-guard refusal before plaintext, prototype cold history, and continued raw
nine-pin denial. No positive final row is fabricated. Schema7 stays one current
unreleased shape; older7 prototypes remain metadata-readable but cannot gain new
authority. Update the existing schema2 downgrade fixture child-first. Affected
tests: new view qualification schema, view schema, legacy TrialStore/migration,
and exact native source footprint. Runtime owned reserve/consume is a later unit.

Qualification metadata checkpoint: direct4 plus view_schema, TrialStore, store
and NativeFootprint passed79 checks,204.563s recorded (per-row timing basis).
The real tuning/legacy reservation adoption is refused; changed/missing guard
blocks current plaintext, older prototype cold metadata survives. All previous
view DDL statements remain AST-identical; schema2 downgrade drops the new child
first. Evidence `../evidence/2026-10-23-m2d1-task3-qualification-schema.json`,
SHA256c52e682319fafcd9613e125ce3741bc6b27cb9f7bf3ae4a4b94f4b7327e3179a.
Profile79/d6b20eb5678033ceec44c20ffd6d6d26d3a49da2a7114b2629108c54bb68ffe4
is unregistered. No actual selected-final link is exercised or claimed. Final
runtime remains explicitly closed pending actual owned reserve/consume; Task3
is OPEN. Continue from this checkpoint, not by repeating these green scripts.

Next owned-registry unit: implement a SQL/blob-only historical qualification
reader and concrete same-plans/view qualifier. Current preview authenticates the
real selected event, every declared tuning report's current full18 policy and
evidence, current selected view/source/meaning, then claims the existing global
qualification family in the owner's actual admission transaction. No unlinked
legacy or consumed reservation is adopted. Final regression rejects qualification
aliases but keeps normal exposure; only qualification cells carry/consume the
shared claim. Integrate through ViewAdmission, current view/lineage and existing
TrialStore materialization, retaining replay-before-I/O and atomic Call/link/event.
Tests start with actual nonfinal/missing/foreign scope denials and constructor
ownership; positive final integration is not fabricated and remains unverified
until a genuinely eligible selected final exists. New native-reachable modules
must join the exact footprint in the same source change. Keep full18/unknown.

Owned registry code checkpoint:70 checks passed across8 sequential scripts in
494.250s, on one frozen source map. New actual denials cover nonfinal/missing/
foreign scope, missing/foreign transaction, and consumed qualification relabelled
as regression. Existing genuine tuning owner schedule/Runner/results/cleanup,
lineage/history, TrialStore, reports and worker regressions pass. Code now derives
selected-report/publication proof, shares the existing CaseStore claim registry
inside actual admission, consumes qualification only on materialization, and
authenticates cold qualification history without host/store backedges. Current
final report creation refreshes selected evidence; full18/unknown remains intact.
This replaces temporary unconditional final-unavailable gates with conditional
owned enforcement, not an exercised positive final path. No eligible/final row is
fabricated. Evidence `../evidence/2026-10-23-m2d1-task3-owned-qualification.json`,
SHA2565f54cee420f022709b4ea9278fcc5cda975f85c2b1faf55f9f9b9eea0283697a.
Source81/759f44aba5b931e24b1cbb8a59ffe49528a26e07a6d0797afa4339ac1478958e
is unregistered. Genuine positive final/native/public proof and Task3 remain OPEN.
Static follow-up found legacy v2 tuning may lack the same family fence; reproduce
that separately before claiming the alias audit complete. An ignored3-test draft
is ready; do not change completed source maps or repeat the8 green scripts.

Legacy alias follow-up: actual RED3 reproduces v2 lower-store/owned admission
reading context despite a genuine later owner-declared qualification alias, and
the final SQL fence not rejecting it. Preserve exact old event replay/metadata.
Add the shared tuning-family guard before private v2 reservation/admission reads
and in the common last SQL fence (also covering v4 after slow source observation).
Affected sources: trials(v2 branch), experiment_admission and experiment_lineage;
callers: old baseline Runner/live guard and existing v4 fences. Tests: new3,
existing B lineage/admission/actual execution plus native footprint; v4 methods,
qualification writer/history and the70-test checkpoint stay unchanged.

Legacy alias repair checkpoint: direct3 plus B lineage18, admission5, actual
baseline execution2 and genuine v4 pair/native-footprint2 passed30 checks,
134.850s recorded (basis per row). Both early v2 boundaries reject before
plaintext/native preflight; final SQL fences reject later aliases, while exact
old event replay/metadata remains cold. AST/source proof preserves the earlier
v4 current branch, trial materialization/reserve methods and owned qualifier/
history code; reuse that70-test scope, not a claim of final native readiness.
Evidence `../evidence/2026-10-23-m2d1-task3-legacy-alias.json`, SHA256
fa40a4baf1887cc1c873be511546b3d45311f3636c48c5e6c7ba18422180ee40.
Source81/c2e7968e01bcc0434cf9368602d694ca8d7c53de6c9df487d0bd99f1e1f75dc3
remains unregistered. Genuine positive selected-final and Task3/native/public
acceptance remain OPEN; no model query or quality eligibility was invented.

**Files:** new `server/improvement_view_materialization.py`; extend actual
TrialStore.materialize, sandbox/worker/TrialProfile, receipts/checks/results/
views/products/comparison projection. Add all new native-path sources to the
profile footprint. New `test_improvement_view_execution.py` and native opt-in
view qualification using exact pinned candidate and local dummy provider.

**Interfaces:** a closed v2 workspace manifest contains the resolved view assets
and exact common context/contract/fixture pins. Old v1 manifests render identical
old bytes. Installation/evidence records expose v4 view hash and exact revisions;
model-issued receipt text is never authority. New result projection validates
actual linked view/attempt/call/receipt before comparison; unknown observations
remain unknown rather than being omitted from mandatory integrity.

- [ ] RED: wrong view, stale source, missing installation, leaked host paths,
  mirror alias, ungranted tool, reused session or forged native event cannot
  produce successful installation/coverage or a report winner.
- [ ] GREEN: real Runner/workspace/Fernet/broker/kernel/CallLedger execution of
  baseline and candidate with identical common inputs; canonical/mirrors and
  all ordinary production learning/task/session stores remain untouched.
- [ ] Actual native local-provider qualification proves the selected engine saw
  the exact separate baseline/candidate installation and could not reach host
  brain/checkers/answers/shell/web/ambient source. Include actual worker/host/
  supervisor death, repeated cancellation and complete plaintext cleanup fences.
- [ ] Save full source/runtime/scenario hashes; register only the final exact
  qualified profile outside its hash. Perform necessary selected-model technical
  feasibility only afterward, with genuine usage and no rerun-until-win.
- [ ] Commit actual view execution/evidence, not an empty adapter or readiness
  flag. An inconclusive/rejected outcome is valid and keeps baseline.

Native-view qualification unit, frozen before test code: add opt-in
`tests/python/test_improvement_view_native_qualification.py`. Derive both v2
manifests through the actual temporary owner/source/CaseStore/semantic/view/
Trial materialization fixtures, using an exact pinned native engine configuration
before the comparison context is captured. Preparation/reviewer evidence in
these fixtures stays explicitly simulated and cannot qualify a business/final
selection. The native exercise itself uses real TrialWorkspace, FixtureBroker,
TrialProfile, SDK and pinned CLI with no adapter/readiness stub or registry entry.
Run each variant in a separate hidden owned Windows job/start gate, empty auth
HOME and local dummy provider; no selected account credentials or inference.
Check exact prompt/asset/view/receipt identities, distinct native sessions,
denied outside/ambient tools and expected answers, unchanged canonical bytes,
then drain the native job before actual plaintext cleanup. The local provider
must observe only the expected model/medium/no-fast/two-message fixture exchange.
Publish sanitized scenario/source/runtime hashes without fixture bodies/paths.
Affected product bytes: none; native footprint remains the same81 sources. The
new test composes existing materialization with actual native enforcement;
it does not claim a native TrialRunner/CallLedger feasibility or positive final.
Retain existing full solver/typed-role/host-supervisor-death/quiescence native
qualification checks on the same source profile before registration. Reuse
unchanged exact-source evidence after review; rerun only affected proof if fixes
change its source/runtime. Real selected-model feasibility follows registration.

Native-view checkpoint: the opt-in actual CLI test passed on unchanged81-source
profile2221a859 in39.172s process wall. Two genuine temporary v2 materializations
carry the exact native pin captured before the comparison context; each uses a
separate native query/session and two local provider messages. Full existing
blackbox isolation checks plus exact native prompt/view/asset/receipt identity
and real cleanup-after-job-drain pass. Actual reasoning/asset use stay unknown.
The first attempt failed in the test harness's cleanup ACL interception; its
log/source record is preserved. Moving the actual cleanup proof inside the
existing real-Popen scope fixed the harness without weakening an assertion or
changing product source. Sanitized evidence
`../evidence/2026-10-23-m2d1-native-view-enforcement.json`, SHA256
0691a727db9dd81b91e814ccfaa4278f04d9c90c5a325cc789b282de31f6a10c.
Native account calls remain0 and profile is still UNREGISTERED. Shared solver/
typed-role/death/quiescence composite qualification, genuine native TrialRunner
feasibility/positive final, whole-D1 review and final CI remain open. Prior owner
API47+route evidence is reused: all server and its executed test/route bytes are
unchanged; only this independent opt-in test and documentation were added.

### Task 5 — owned public controls, regressions and publication

Independent owner-control unit while genuine final/native proof stays open:
POST `view-freeze` and `view-evidence` under the existing experiment route accept
exactly `comparison_id,expected_generation,event_key`. No body/view/native grants
or automatic next/query. Both are owned before synchronous work and scope the
comparison to the URL experiment; stop joins these source threads. Freeze reuses
the actual immutable publication/replay. Current evidence recomputes (never a
durable readiness ticket), returns only metadata, C observational unknowns,
current generation/check time and `current_view_sources_and_semantics` scope.
Cold owner GET `/{experiment_id}/views/{comparison_id}` uses only existing store
metadata, never a service/source/native factory, including after off/revoke.
Affected files: requests/API/service, route snapshot, actual-main auth test and
new actual-view API/lifetime tests. Native footprint service already included;
profile remains unregistered. Actual positive final proof/Task3 is still open.

**Files:** extend actual experiment owner API/service/requests/route snapshot,
operator guide, bilingual changelogs and progress; focused owner route/stop tests.

- [x] Explicit owner view-freeze/current-evidence control is closed and CSRF/
  session protected; history stays cold after off/revoke. No API-token-only
  authoring, caller native proof or automatic next/model dispatch.
- [ ] Stop/recovery owns new view/admission/materialization/result threads,
  every actual Trial and native lifetime. No broad settlement of unrelated work
  or plaintext deletion based only on terminal SQL/PID state.
- [ ] Source-qualified affected regressions; early Linux checks before final
  stabilization; one independent whole-D1 review and scoped RED/GREEN fixes.
- [ ] Exact final-head full CI, fresh version/main, straight authorized merge,
  identical merged tree and actual publication. No deploy/restart/live activation.
- [ ] Record D1 engineering status and actual model/business/rollout separately;
  continue D2 production router/lazy/hub/native/task-pin integration. Do not
  call D, M2, M3-M8 or full Goal complete because this subproject ships.

Owner-control engineering checkpoint:47 unittest checks and one actual route
snapshot check passed across9 sequential processes,295.126s subprocess wall,
on one frozen server/test/route source map. Actual main tests cover session and
CSRF for all26 improvement routes; the621-entry snapshot adds exactly3 routes,
with retained route definitions/order otherwise preserved. Actual HTTP view
publication/current inspection, completed-key authority rechecks, foreign scope
denial, cold history/replay after off/revoke, and cancelled HTTP ownership pass.
A controlled in-process mutation removing only the view stop joins is rejected
by the actual source-thread settlement assertion; the unmodified source passes.
Existing B/C APIs, service/stop/lifetime workflows and actual v4 paired reservation
also pass. No native verify/query occurs through the new view controls. Guide:
`docs/dev/agent-skill-m2d1-views.md`. Evidence
`../evidence/2026-10-23-m2d1-task5-view-controls.json`, SHA256
b3a617be7e9eda67398ff166b28ff7ff833908e2f779089bfa670f088b3305a9.
Current81-source profile2221a859 is unregistered. Genuine selected-final positive,
exact D1 native qualification, independent whole-D1 review and exact-final CI
remain OPEN; this checkpoint does not complete Task3/4/5 or authorize rollout.

## Self-review and interface freeze

Independent whole-D1 review2727edcc..740c0c67 completed: one Important/P2,
no Critical or additional permission/holdout bypass. Confirmed real repro:
closed semantic workflow + still-live original OwnerTrialService is deliberately
not retired, but rebuilt ExperimentService constructor returns a facade retaining
that unusable resolver; current admission then raises role_workflow_closed.
Fix unit before code: explicitly refuse construction when retained resolver's
semantic workflow is closed and BOTH exact close futures are not successfully
complete. Preserve the original host/Trial resolver and every owner/cleanup fence;
after original owner closes successfully, rebuild/admission must work. No force
flag, earlier retirement, new store or automatic cleanup. Affected product:
ExperimentService constructor only; callers: main lazy service factory and all
same-host reconstruction. Focused RED/GREEN: real lifetime refusal, successful
later rebuild/admission, still-live semantic reuse, missing/pending/cancelled/
failed original-owner close. Then scoped service/owner API/view admission checks
and same reviewer's fix recheck. Existing control/stop/materialization logic is
unchanged; qualify reuse by AST/source hashes. Changing service invalidates the
whole exact81-source native profile; preserve pre-fix native proof as historical,
requalify final profile after fix stability, no native registration/model query
beforehand. Do not request another whole-D1 review.

Review repair checkpoint: original real reproduction15.456s failed with the
closed-workflow error; focused RED14.312s proves constructor refusal was absent.
The constructor now adds only explicit closed-resolver ConflictError refusal;
AST proof preserves all other service code and all other product sources. Actual
lifetime4 and five affected commands passed29 tests,239.901s recorded. They
cover refusal before private/native work, unchanged bound resolver, successful
later rebuild/admission, usable live semantic workflow with a new owner, all
invalid owner-close futures, owner API/main/service and v4 handoff/cancel.
Evidence `../evidence/2026-10-23-m2d1-review-lifetime-fix.json`, SHA256
fb8333f444f84ac85f03d3f0c71402eb30f599e1a025499802b860739e7d94b5.
Scoped independent recheck is pending. The earlier source-identical81/2221a859
composite native solver5/roles5/quiescence9 passed60.609s, artifact
`../evidence/2026-10-23-m2d1-native-qualification.json`, SHA256
96adabecf47773debc2988098a68cc3a9c592a00ad2ed9b0d8a6e4cab096936b.
That profile was never registered and is historical after this source change.
Current81/d0705506 is unregistered and needs exact-source native requalification
after the scoped fix review; no real account query or positive final is claimed.

Fix scoped recheck CLOSED the sole Important/P2 at23f62b0b: independent targeted
lifetime1 GREEN20.260s, log SHA256
bcc71f9c71f5cb7aef6a24240c359c55f87ec094e9a8e949bc90f93bb4612f9a.
Fresh main advanced tod3d7cb36/0.298.0. Rebased25 D1 commits to3e1abcf0,
reserved0.299.0 in draftPR803, preserved every main changelog byte and both real
0.297/0.298 releases. All81 native source bytes stayed identical; all improvement
tests stayed byte-identical except one CRLF normalized to LF in legacy alias
test, verified by reconstructing its exact previous hash at byte4115. Seven
affected main/voice/route/bilingual scripts passed18.375s on one source snapshot.
The existing29-test/fix-review scope is retained, not rerun solely for rebase.

Runtime-update unit BEFORE code: final native-view attempt3 failed safely in
1.562s at candidate_identity_unverified, before any native/model execution.
Installed CLI was auto-updated at23:00 to2.1.309, exact SHA256
5441781f2b6bbd07354b4a74560ee88c68c9bf05d6db3c7e24c452c91673dc53;
cached309 bytes match, SDK remains0.2.116. Do not restore/downgrade the user's
installed CLI or execute a hash-unknown runtime. Extend only that exact Windows
runtime tuple in improvement_claude, update the opt-in candidate guard to309,
and verify actual --version inside the already-owned hidden dummy qualification
job before the SDK query. Public verify must still refuse this unregistered
profile before any version/auth probe. Callers: native adapter/worker and shared
solver/role/view qualification tests; source count81 unchanged but hash changes.
Run focused adapter guards, then complete actual local/dummy solver5/roles5/
quiescence9 and paired-view1 on the final exact source. No registry/account query
until all proof passes. Historical308 artifacts/registrations stay intact; no
generic unknown-runtime exemption, source flag or altered model/reasoning.

Runtime309 checkpoint: exact new81-source profile
4d346a3ae4f1afa99784fc51307258ad99a8d470ac6a0c46f1d330e6b0e656fa
passed actual paired-view1, solver5, roles5 and quiescence9:20 tests in96.767s
on identical full source maps. Actual --version is checked inside the hidden
owned job before SDK query; public adapter guards22 passed1.711s. Source-bound
artifact `../evidence/2026-10-23-m2d1-native-qualification-final.json`, SHA256
012d9e37690e8711da75a344dfee0677df8d6c690b90f689ddbb14574c82f295.
Registration RED proves the exact entry absent; GREEN2/0.045s matches actual
artifact/source hashes and refuses changed tuple/platform. The new exact309
entry lives outside the native footprint; lookup function and historical C
entry remain unchanged. AST proof preserves all native adapter behavior except
one known-runtime tuple and all paired fixture helpers except the unexecuted
registration-test class. Do not rerun native20 solely for this post-proof entry.
Checkpoint `../evidence/2026-10-23-m2d1-source-checkpoint.json`, SHA256
99c01d1afdc91f2516b57a12cecfb81bec13dd184295cfd934a37fd502661253,
also qualifies the independent fix recheck/rebase/component evidence reuse.
Small runtime309 delta still requires scoped independent recheck; final CI,
actual native TrialRunner/account feasibility and genuine selected-final positive
remain open. No real account model call, business acceptance or rollout occurred.

Task1 metadata fields, SQL names, bounds and test commands are frozen below.
The probe-authority rule above retains all quality gates and old combined
verdicts. Finalize later task-specific internal field projections from these
closed contracts before each task's code; record any necessary interface ruling.
Check all new cross-version joins, immutable rows, old-reader gates and source
footprint; list affected callers before each task under Goal12. Production paths
must eventually serve this SAME resolver; a trial-only resolver is not the final
requested system and is not an acceptable replacement for D2/E/F.

## Concrete source-derived bounds and cross-version decisions

- Current C `MAX_ASSET_BYTES=1048576`; workspace assets have at most100 records,
  each at most that many bytes, and the rendered prompt is also bounded by this
  constant. v4 request metadata retains the current65536-byte limit. Keep these
  exact existing bounds; reject missing/oversized required input before a call,
  never drop protected data or truncate it to make a trial run.
- D1 still materializes one primary skill body. Existing textual protected
  dependencies remain part of the pinned common capture/semantic evidence, not
  newly executable files. No new helper path or script grant is introduced.
- Workspace v2 is the current v1 closed manifest plus one `effective_view`
  projection, with version2 explicit. Assets retain `{id,path,hash,content}`;
  baseline uses the real baseline revision ID and candidate the real A candidate
  identity, never a fabricated canonical revision. Its view asset descriptor
  must match every materialized asset exactly. Preserve old v1 rendering/hashes.
- Keep `bundle_hash` bound to existing experiment baseline/arm pins; store a
  separate `view_hash`, do not relabel an A envelope as an M0 bundle. The v2
  effective hash includes that view hash and all original context/contract/
  fixture/asset pins. Installation/result versions expose the same exact view.
- v4 keeps explicit comparison lineage and adds a closed `view` object with
  `{view_id,view_hash,binding_hash}` (the frozen Task3 protocol above). The actual comparison binding maps
  the correct baseline/candidate view. Pure shape validation is never authority;
  current SQL/blob/source checks, immutable links and kernel barriers remain
  mandatory. Preserve exact v2/v3 validators, hashes and actual historical gates.
- A comparison without an explicit new view binding keeps its old metadata/
  baseline-only behavior. Do not retrofit a binding after any comparison cell
  exists. Preparation v3 results remain separate evidence and cannot fill paired
  v4 comparison slots. Scope/default policy capabilities remain fail-closed.
- Current C native operation checks are materialization, worker_protocol,
  installation, tool_inventory, side_effects, completion, actual_model,
  actual_reasoning, native_session and actual_input_use. `actual_reasoning` and
  `actual_input_use` are explicitly unknown by current implementation even when
  other observations match. B `project_result` requires its full18-check native
  set, including asset_observed_use/actual_reasoning, before successful integrity.
  Keep that unknown result; do not remove checks from B or claim the actual C
  role report can currently be entirely pass. A new technical probe authorization
  must be separately justified and must not become native/quality eligibility.
- Production D2 cannot claim support merely because these isolated views work.
  Its concrete ordinary Dashboard surface currently has exact keys
  `{kind:'dashboard',session_id,language}` and host-bound current session/config/
  SQL/file sources. Agent/Team/Coding contexts require their own later coverage,
  not an opaque caller descriptor or ordinary brain fallback.

## Frozen Task1 metadata contract

Pure version1 view manifest has exact fields:
`version,evidence_class,brain_id,experiment_id,context_id,context_generation,
comparison_id,comparison_hash,definition_hash,arm_ordinal,arm_hash,candidate_id,
variant,target,engine_config_hash,baseline_context_hash,contract_hash,case_set_hash,
grant_hash,scope_hash,policy_version,source_authority_hash,semantic,assets`.
`evidence_class` is exactly `technical`; `variant` is `baseline|candidate`.
The opaque view ID, manifest hash and manifest blob hash are outside the hashed
manifest. No field declares execution readiness, success, live status or owner
acceptance. Hashes are64 lowercase hex; actual IDs use existing128-character
identifier validation, brain ID uses the existing1000-character bound. Integer
version/generation/policy/ordinal checks reject booleans.

`target` has exact fields
`target_id,base_revision_id,base_hash,base_generation,canonical_ref,identity,
protected_hash,ownership`; ownership is `user_protected|user_managed`, and the
canonical ref is one user `skills/<slug>/SKILL.md`, with the existing slug/device
and traversal guards. `semantic` has exact fields
`receipt_id,binding_hash,assessment_hash,dependency_hash,owner_event_key`;
owner_event_key is null or the actual bounded owner event key, not an approval
boolean. Actual row and current proof matching is Task2, not this pure validator.
Its non-null length is8..160, matching the actual ImprovementStore event contract.

`assets` is exactly one primary body asset in D1, with exact fields
`id,canonical_ref,before_hash,content_hash,identity,authority_hash,origin`.
The path/identity/before hash match the target. Baseline origin is `baseline`,
ID equals the actual base revision and content hash equals base hash; candidate
origin is `candidate`, ID equals the actual candidate ID. Empty or identical
candidate body is handled by actual authoring policy, never by inventing a new
canonical revision. Protected dependencies remain unchanged common context.
Manifest JSON is bounded by MAX_ASSET_BYTES and preserves canonical JSON hashes.

Task1 schema names: `improvement_effective_views`,
`improvement_effective_view_assets`, `improvement_comparison_views`, each immutable
and scoped by actual brain/experiment/comparison/target/HostContext/A candidate
FKs. Views are unique per `(comparison_id,brain_id,variant)`; assets per
`(view_id,brain_id,position)` with position0 only; the comparison binding is unique
per `(comparison_id,brain_id)`, references the exact baseline/candidate views and
actual semantic receipt, and stores one encrypted binding hash/blob. Composite
FKs plus actual join triggers prevent matching individually valid foreign rows.
The extra v4 link table/legacy-link exclusion guards are Task3.

Task1 SQL columns are frozen before implementation: views store `id,brain_id,
experiment_id,target_id,context_id,comparison_id,variant,candidate_id,
base_revision_id,base_hash,base_generation,source_authority_hash,
semantic_receipt_id,manifest_hash,manifest_blob_hash,created_at`. Both variants
identify the comparison's actual A candidate and semantic receipt. Assets store
`view_id,brain_id,position,asset_id,canonical_ref,before_hash,content_hash,identity,
authority_hash,origin`. Bindings store `comparison_id,brain_id,base_view_id,
candidate_view_id,semantic_receipt_id,binding_hash,binding_blob_hash,created_at`.
Content-addressed manifest/binding hashes equal their encrypted blob addresses.
SQL joins enforce actual comparison/arm/candidate/base/context/receipt lineage
and asset identity/hash/origin, plus complete matching assets before binding.
SQL cannot authenticate encrypted plaintext: Task2 must revalidate exact manifest,
blob bytes, current grants/source/semantic authority and pair proof before use.
No runtime version, Trial link, eligibility or live activation flag is stored here.

Migration7 adds `.pre-improvement-m2-views.bak`, keyed by absence of
`improvement_effective_views`. Run it through the SAME writer serialization;
retain all prior backups and accepted known versions1..6 explicitly. Fresh DBs
retain pre-M0 behavior. Unknown8/999 versions reject before backup/write. C's
actual2727edcc reader refuses7; restoring the byte-preserved backup restores its
actual6 history. Current metadata test expectations advance from6 to7 only for
current migration results; historical backup versions stay exact. Existing
concurrent-boundary tests add precisely the new one-time backup, not a relaxed
count. Preserve C's same-number-prototype refusal before any role/view authority.

Task1 commands, sequential:
`python tests/python/test_improvement_views.py -v`,
`python tests/python/test_improvement_view_schema.py -v`,
`python tests/python/test_improvement_store.py -v`,
`python tests/python/test_improvement_operations.py -v`, and
`python tests/python/test_improvement_experiments.py -v`, and
`python tests/python/test_improvement_operation_execution.py -v`.
The sixth script is affected because its future-schema test used literal7;
schema7 is now known, so the same refusal test must exercise actual future8.
RED must prove the view protocol/schema are absent; GREEN must exercise real
SQL/encrypted metadata, old-reader refusal, exact backup/rollback, cross-scope and
immutable guards. No native/auth/model calls in Task1. The CI workflow must fetch
published C2727edcc for its actual schema6 reader just as it fetches A/B today.

## Selected-account feasibility follow-up — 23 October

The exact registered81/4d346a3a source at54210807 ran one actual baseline
TrialRunner call and one actual semantic role, with the configured Opus5.5/medium
subscription. The real reviewer artifact was fenced JSON and lacked required
`findings`; the strict parser refused it. No receipt, view, pair, selection or
qualification claim was created. Preserve this failed attempt and its usage
in `../evidence/2026-10-23-m2d1-real-feasibility.json` (SHA90ecc20b), with
canonical unchanged and plaintext cleanup complete. Do not normalize it, infer
acceptance from its inner pass string, impersonate an owner or rerun until win.

Actual operator defect: this failure surfaced as generic503, and a retry exposed
only operation_recorded. A scoped follow-up adds a durable invalid_output outcome
under the same semantic_review event, referencing the original native product.
It grants no receipt or assessment, cannot enable a probe, and never retries the
model. Source/grant/generation/stop and exact product fences still apply before
recording; exact historical replay stays cold after stop/off/revoke.

Impact recorded before production edits in the retained task ledger: sole
production component SemanticReview._publish/new rejection helper; callers
owned ExperimentService.workflow, owner API and stopped cold replay. Strict
validator/prompt/native checks/eligibility/schema remain unchanged. Three
workflow RED tests reproduced two parser errors and one successful source-fence
refusal; one actual owner HTTP RED test reproduced503. An earlier wrong class
selector failed before tests and is excluded from this evidence.

- [x] Complete GREEN semantic workflow/protocol/dependency and actual owner
  workflow API suites, scoped view source/policy, view API and adapter guards
  sequentially on one fixed source map. Keep malformed raw products and unknowns.
  Passed63 tests in349.720s; source/AST/log proof is recorded in
  `../evidence/2026-10-23-m2d1-semantic-invalid-output.json` (SHA4a8d10e9).
- [x] Scoped independent new-delta review, retaining the completed whole-D1
  and earlier lifetime/runtime reviews. No repeat whole review.
  Approved exact330501fa, no finding; independent actual owner HTTP recheck
  passed1 test in12.336s, log SHA8a21a9b0.
- [x] Qualify the final changed81-source native footprint before any further
  actual native/account query; prior4d evidence is historical and cannot match
  the new profile. Preserve all original failures and exact registration rules.
  Profile958527ac passed20 native tests94.890s on identical full source maps;
  artifact `../evidence/2026-10-23-m2d1-native-qualification-outcome.json`, SHA1f3391cf.
  Exact registration followed metadata RED→GREEN3,0.068s; no account query.
- [ ] Final-head full CI, genuine account pair/final acceptance and remaining
  D1/D2/E/F/M3–M8 work stay open. No Task3/4/5 completion marker from this fix.
