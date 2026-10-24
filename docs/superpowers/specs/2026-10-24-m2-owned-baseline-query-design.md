# M2 owned baseline query and technical result design

Root status: Q1 architecture builder-approved, no query implementation or installed
qualification yet. P1 component source gate is reviewed through
0549380e17e66836ab475dae596d21e649e4e7a6, including the final-return authority race
fix; its installed gate remains OPEN for final stable query closure. Goal3/18
delegates routine design/execution choices without repeated human approval.
Fresh Astra/high builder check and the per-attempt lifecycle follow-up returned
nothing important left. The Q1 plan reconciles the committed interfaces below.

## Root scope and lifecycle rulings

Choose two consumed query verticals: **Q1 baseline5** end to end, then **Q2 view4
and operation2** using the same executor/ledger. The report below records both
interfaces for dependency clarity; Q2 methods/files/tests are explicit follow-on,
not part of Q1 implementation. Q1 modifies only its consumed trial/native/result
path, never operation/view functionality merely to install unused helpers. P1's
actual committed interfaces are reconciled in the Q1 plan after its scoped gate.

Committed-interface ruling: P1's `for_qualification(session)` is single-use
preflight and stores `session._native_parent`. Query attempts use the consumed
`NativeParentBoundary.for_qualification_query(session, binding)` factory, which
requires the Session-minted retained binding and derives its exact owner/lease
context. Do not reset/reuse the preflight singleton. The architecture report's
"on for_qualification boundary" shorthand below denotes this separate technical
query boundary, not permission to replay preflight. P1's synchronous full-current
check at result issuance remains required across subsequent facade handoffs.

The final stable-source installed localhost matrix is mandatory, after both
query formats and current source are reviewed. P1/Q1 component fixture gates do
not become installed qualification in the meantime; maps remain closed and no
product/account readiness is inferred. An earlier CLI diagnostic stage is used
only for a concrete unresolved runtime risk, not routine unchanged reruns. Any
later source change invalidates its affected proof and requires requalification.

Q2 also closes both known ordinary marker omissions before its technical entries:
ViewExperimentAdmission._admit_owned and ExperimentAdmission.admit receive the
same exact account_ready is False/domain qualification predicates and actual
refusal/ordinary controls. P0's exact four-consumer scoped gate remains closed;
this is the newly identified route coverage, not a retrospective global claim.

Lifecycle clarification: the final publisher runs inside the retained facade
task, so it cannot require that very task to be absent before its own append.
Require all native/workspace/lifetime owners and every *other* pending host/proof
operation **for this exact attempt** settled. Owners of other attempts stay retained
and visible; they do not block this attempt's report, but still block global
Session.cleanup. This avoids a cycle between concurrent retained facades or an
unrelated pending proof. Retain this exact publishing task through the immutable append;
remove its registration in a non-awaiting finally before the facade returns to
its caller. No other owner may be ignored via a boolean/caller cleanup claim.
Successful external return therefore has no remaining owner for its own attempt.
Tests hold a second genuine host operation pending while one attempt completes,
assert its owner is preserved and Session.cleanup still refuses. On append failure
retain the exact pending proof/diagnostic retry owner; do not return success or
relaunch. Tests pin this self-owner distinction and publication-failure retention.

Closed/expired Session can drain/save diagnostics but cannot publish a new
successful technical result. Existing immutable final results remain cold-readable
without a current candidate registry or surviving workspace. Partial stage is
truthful incomplete evidence, not a final result. No schema/second executor/
accounting ledger or arbitrary allow_qualification switch is authorized.

The architecture report below is verbatim apart from its heading being nested.
All source claims are from committed6a179c51, not an active P1 implementation.

## Architecture report — current-input qualification query

Design only, 2026-10-24. Authority: Goal18, `docs/handoffs/claude-opus-5-5/HANDOFF.md`, public `2026-10-24-m2-owned-technical-preflight-design.md`, and the bounded root source map. Actual source references below are static `git show` reads of `6a179c5162ab8e7a0e60d9c8a855e288010a421a`, not an audit of active P1 edits. No application imports, tests, native/CLI/SDKClient calls, account/model/network probes, Git mutations or product edits were performed. Only this report was written.

Goal ends at M2 engineering and integrated Claude Opus5.5 handoff. Business/live acceptance stays PENDING. No M3–M8, D2/E/F/UI or Library expansion here. Current PROFILE_SOURCES99 is UNQUALIFIED; candidate/release maps are empty. This document grants no launch authority or qualification.

## Approaches and chosen scope

1. **One complete three-format vertical:** exact Session entry into existing admissions/runners, startup3 query, accounting, typed publisher and cold reader for baseline5/view4/operation2 in one unit. Lowest number of intermediate source states, but broad review across trial, view and operation owners.
2. **Two consumed verticals, one final installed-source stage — chosen:** Q1 closes baseline5 admission → actual TrialRunner → Guardian/startup3/worker/SDK → real call/ACK → typed technical proof → cold read and cleanup. Q2 adds view4 and operation2 using Q1 machinery. Each unit is reviewable and consumed end to end, not an unused permit/parser. Run the required installed selected-CLI localhost matrix on the final stable full closure once, unless an earlier diagnostic gate is needed. Q1 is not all-format qualification.
3. **Unchanged ordinary runners with a technical adapter substitute:** rejected. Ordinary owners require supported/hash and P0 rejects qualification/account-false. Inventing supported=True bypasses that distinction; product stores also refuse the anchored domain. Copying a runner would introduce a second executor and drift in cancellation/accounting.

These are delegated routine engineering choices. P0's exact four-consumer task stays closed. The new ordinary view-admission fence belongs to Q2 before its technical entry. Q1 uses actual TrialAdmission with its existing request version1 and current **materialization version5**; these version numbers describe different contracts.

## Existing code and precise mismatches

Already present and reusable:

- `QualificationSession.open(*, pin, endpoint, expected_fingerprint, lifetime_seconds, maximum_queries)` creates its own root, Principal, encrypted RevisionBlobs, anchored ImprovementStore, GoalStore and CallLedger after candidate/static checks. `environment(cwd)` supplies fresh HOME and exact dummy/numeric localhost configuration. `open_forensic(root, *, expected_run_hash)` reopens existing state read-only without migrations/runtime.
- `bind_attempt(owner, principal, identifier, *, expected_generation, lease_token, capability_hash)` accepts exact TrialStore/OperationExecution and same assets/principal, requires real prepared workspace/reserved call/pre-engine active lease, revalidates materialization/source, writes encrypted immutable attempt link, and atomically counts existing native_qualification_attempt events against maximum_queries. Exact replay is historical identity, not relaunch or a refreshed lease. No second query budget ledger is needed.
- `qualification_records.read_run`, `actual_binding`, `read_attempt` authenticate run/pin, request/workspace/materialization, actual call purpose/context/mirror/reason/attempt, and equal call/attempt engine_at. Cold reads deliberately need no surviving workspace/live Session/current source. Keep that distinction.
- `TrialAdmission._prepare/_available/_replay` and final transaction own source/plan/reservation joins. `TrialRunner.run/_run_claimed` owns claim, lifetime, heartbeat, materialize/prepare/prepared, start_engine, NativeUsageRecorder, `_NativeRunnerEvidence`, late observations, abort and cleanup. `OperationExecution`/`OperationRunner` provide the corresponding real operation owner and OperationEvidence. Reuse these executors.
- `ViewExperimentAdmission` owns schedule.next_slot/require_idle, actual brain barrier, frozen comparison/arm/matrix/view linkage, final holdout claims, `_reserve_in`, and final `views.resolve_request(... require_link=True, trial_id=...)`. `TrialStore._materialization` dispatches request4 to materialize_view; other native trial materialization selects5. Operation materialize selects2.
- `execute_worker_v2` waits for actual before_engine_start completion before sending private engine_start_ack. `NativeImageDecisionStore`/attempt_scope provide four durable image allows. `_NativeRunnerEvidence` retains real received/closing packets and usage through failure.
- `validate_startup3/_link/worker_binding3` already parse exact trial/operation attempt links. Existing wire/link field `capability_hash` is a consistency join, not an authority issuer. Full startup3 must remain attached to the private2 incarnation/nonces.

Concrete missing consumers/conflicts:

1. P1 enables only preflight, two channels, scratch locks and trial entrypoint. Queries need genuine link, four ordered channels (`adapter_version`, `auth_status`, `sdk_version`, `query`), real attempt lifetime fences and correct trial/operation bootstrap policy.
2. Ordinary parent execute uses adapter.admit_preflight and qualified_launch, requiring production registration. Technical query must derive candidate launch from its exact live Session, without weakening those functions or adding REVIEWED_RELEASES entries.
3. Both worker run_request functions still insist on verified.supported and matching capability_hash after prepare_native_runtime. Technical observations intentionally fail that condition. Add an exact startup3-owner branch; never return a forged supported=True mapping.
4. `NativeProfileBinding.__init__` independently calls strict `native_sdk._environment`. Extending P1's SDK factory alone cannot permit dummy query. A narrowly worker-owned profile factory is necessary; default construction stays strict.
5. `NativeInvocationSet.transport` requires completed runtime preflight and all four channels, then checks exact SDK-added environment, query arguments, selected image and original streams. Reuse this transport/capture; do not bypass `_fixed('sdk_version')` or SDK construction in the installed gate.
6. TrialProducts.stage/TrialResults.finish/read and OperationResults.finish/read_stored categorically require_product_store. Keep refusal even if report labels are stripped. Technical results require separate existing-event/blob publication, not ordinary result tables or result_json pointers.
7. `validate_native_trace` demands all four observations, worker_ready/start/completion/drained. Its native_qualification check remains **unknown** because production registry is closed. Input delivery keeps native read/provider acceptance/comprehension unknown. Technical proof cannot rewrite these to pass.
8. At the stable source `ViewExperimentAdmission._admit_owned` checks only supported/hash. Q2 must add exact account_ready is False OR domain qualification refusal to its ordinary branch, with marker/control tests before technical view entry. This does not reopen P0. A bounded caller read found the same marker omission in ExperimentAdmission.admit; that route is not consumed here. Record it for a scoped ordinary-route follow-on rather than using it to enter this domain.
9. Existing QualificationRecordsTests and QualificationOperationBindingTests patch input_version to1; the operation fixture enters proposing/reservation via genuine internal transactions. They prove records, not current-format admission. New integrated tests must remove those seams for any claimed admission/current-input coverage; historical tests stay unchanged.
10. OperationRunner currently treats heartbeat completion while process() is still pending as cancellation. Technical staging makes the row terminal before final cleanup/proof. Its technical branch must distinguish its own committed evidence settlement from external termination: record an owned settlement latch under the runner lock, stop/join the heartbeat, and continue draining the same worker/finalizer. Do not let a terminal heartbeat cancel successful final publication, or treat another owner's terminal row as this latch. Ordinary run behavior stays unchanged; test this exact race.

## P1 dependency: consume the public interface after it lands

These are **P1 design contracts**, not claims about its active working files:

- Session `verify_native()`, `_assert_native_current(*, connection=None)`, `_preflight_launch(scratch)`, `_attach_native(guardian, boundary)`, `_detach_native(guardian, boundary)`, `aclose_native()` and owner→boundary retention.
- `NativeParentBoundary.for_qualification(session)`/`verify_qualification()`; ordinary verify/execute refuse qualification-bound boundaries.
- `GuardianSessionV2.start_qualification(boundary)` derives seed from its exact attached boundary, with current Session checks before image authorization.
- `NativeWorkerSessionV2.from_startup3(packet, *, namespace)`, `run_startup3(raw, *, entrypoint)`, technical prepare_native_runtime and `NativeInvocationSet.from_qualification_worker(owner)`; P1 only preflight/two channels.
- Pure `validate_technical_observation(value, *, pin)` and immutable QualificationPreflight: supported=False, account_ready=False, domain qualification, **no capability_hash**, cleanup proven. No fabricated subscription auth tuple.

Q1/Q2 extend these only after P1 is terminal. Do not ask the active P1 worker to add query. If committed P1 differs from its public design, reconcile against its final public interface before implementing.

## Proposed host interfaces and authority

Names below are **new proposals**, unless explicitly identified as existing. No boolean allow_qualification switch, public current callback, adapter mapping or computed hash grants authority.

In `improvement_qualification_session.py`:

```
async def run_trial(self, admission, public_start_request) -> QualificationQueryResult
async def run_view(self, admission, experiment_id, comparison_id, *, expected_generation, event_key) -> QualificationQueryResult
async def run_operation(self, execution, identifier, *, expected_generation, event_key) -> QualificationQueryResult
async def aclose_queries(self)
```

Require exact TrialAdmission/ViewExperimentAdmission/OperationExecution respectively, identical assets/store/principal and workspace/source roots below Session.root. Use self.principal internally. The exact selected engine must equal Session pin; copied source hashes do not make a foreign source root owned. These methods are host-only and do not become API/Dashboard endpoints.

Retain the complete façade task before any await that can reserve/decrypt/acquire. Add a private Session host-task/pending-proof set distinct from P1's exact Guardian `_owners`. `cleanup()` refuses either set or an unsettled attempt/lifetime, including before Guardian exists. `close()` revokes immediately and requests cancellation on the owning loop; `aclose_queries()` settles retained tasks using existing cancellation-resistant drain, without relaunch. `aclose_native()` keeps P1 native behavior. Repeated cancellation must not lose an off-loop admission/claim/preparation or cleanup future.

As a follow-on extension, Session records `_completed_preflight` only after its own verify_native has returned the exact completed P1 result. No supplied object may populate it. The façade runs P1 once when absent; source/candidate/current/lease checks remain fresh at every admission, binding, allow and ACK. P1 single-use remains. A closed/expired Session cannot reuse the cache as authority.

After actual prepared workspace/attempt, derive a private immutable `QualificationQueryBinding`:

```
version=1, domain='qualification', supported=False, account_ready=False,
run_hash, preflight_hash, kind, subject_id, attempt, request_hash,
workspace_hash, materialization_hash, engine_config_hash, authority_hash
```

`authority_hash = IM._hash(all preceding fields)`; preflight_hash hashes Session's exact completed result. Session retains its exact owner/lease/descriptor identity. The existing bind_attempt/startup/receipt field named capability_hash receives **only this authority_hash** to preserve existing joins, never a product capability object. Derive values from actual row/receipt, not caller JSON. Call existing bind_attempt under runner lock; it remains the sole query budget debit. Its encrypted link, not a new ledger, anchors the descriptor to the call.

For an exact wire choice, extend startup3's nested qualification object to **version2** with two additional required fields, `preflight_hash` and `query_binding`, for trial/operation only. Existing version1/preflight stays exact and accepted. Version1 query parser fixtures remain consistency-only historical input; actual query owner accepts only version2. query_binding is the closed descriptor above; validate every field against existing scope/link/receipt, recompute authority_hash, match it to link/request capability_hash. Pure parser acceptance never proves cached preflight provenance; the host's retained Session does. This avoids a vague optional-field escape hatch and does not change ordinary startup2/private2 grammar.

### Admissions: explicit wrappers, shared real transactions

- `TrialAdmission.admit_qualification(self, session, principal, public_start_request) -> AdmittedTrial`: exact Session first; reuse `_prepare/_available/_replay`, real live_guard and final plan/reservation transaction. Factor only the existing final transaction body if necessary. Ordinary admit retains its P0 marker refusal and adapter verification. Technical wrapper consumes cached genuine P1 proof plus live Session, never production verify or supported=True. Repeat Session checks in final transaction after slow reads and before/after event/reservation append. Live technical replay requires open/current Session.
- `ViewExperimentAdmission.admit_next_qualification(self, session, principal, experiment_id, comparison_id, *, expected_generation, event_key) -> AdmittedTrial`: same exact checks and existing schedule/brain lock/view/matrix/claim/final resolve transaction. Keep ordinary marker refusal separate. A technical result must not be used to advance ordinary comparison scheduling. Q2 proves valid admitted view cells; use separately prepared disposable comparisons when a later cell requires ordinary product evidence. Never fabricate that evidence or weaken scheduler semantics to traverse a pair.
- `OperationExecution.reserve_qualification(self, session, principal, identifier, *, expected_generation, event_key) -> dict`: reuse actual `_current`, `_snapshot_observe`, records._reserve_attempt_in and reservation events/CAS, with live Session checks in transaction. Existing plan/record owners must create the operation in a valid state; direct SQL phase manipulation is not integrated admission proof.

Same-store/domain checks apply before replay, not just insertion. Public JSON can neither select domain nor inject an authority callback. No global adapter/profile switch.

### Same runners, no second executor

- `TrialRunner.for_qualification(session, admission)` accepts exact TrialAdmission or ViewExperimentAdmission, derives trials and host.context_loader/live_guard internally; no injectable adapter/recorder factory on this entry. `run_qualification(self, principal, trial_id)` reaches the same claim/heartbeat/process/finally core after exact Session checks. Ordinary run refuses a qualification-configured runner and keeps its P0 path. Technical branch changes only verification, native boundary selection and result publication; all preparation/current/usage/abort/lifetime semantics stay shared. Technical `_response` uses the separate cold reader.
- `OperationRunner.for_qualification(session, execution)` and `run_qualification(self, principal, identifier)` do the equivalent with real OperationEvidence, recorder and OperationExecution.
- Both bind only after prepared succeeds. Both keep publisher futures owned through cancellation and workspace cleanup. They never import SDKClient in the host. No automatic retry: historical replay and cleanup retry cannot relaunch; a separately requested valid owner retry has new attempt/call/nonce/HOME and another bind_attempt budget debit, while retaining existing attempt/retry bounds.

## Proposed native consumed changes

| File | Change |
|---|---|
| qualification_session | `_query_launch(kind, scratch)` derives matching candidate trial/operation policy from held manifests/current release; `_query_binding(owner, principal, identifier, *, expected_generation, lease_token)` derives descriptor and consumes bind_attempt. |
| native_parent | `async execute_qualification(self, binding, *, owner, principal, identifier, expected_generation, lease_token, before_engine_start, on_closing_observations)` on for_qualification boundary. Derive receipt/manifest/prompt/policy/deadline from actual owner state; reuse `_dispatch`, `_persist`, decisions and attempt_scope. No caller current callback and no ordinary execute relaxation. |
| native_transport | Factor existing execute_worker_v2 packet/accounting/close loop into one shared internal loop. New `execute_worker_qualification(boundary, *, before_engine_start, on_closing_observations)` derives arguments, constructs/attaches Guardian before start, calls start_qualification. Add immediate live Session/bound-call check before qualification engine ACK send, after callback settlement. |
| native_worker | Extend P1 from_startup3/run_startup3 to matching trial/operation entrypoints, nested qualification version2, non-null link and four channels. prepare_native_runtime checks actual guarded technical observations/descriptor without production admit_preflight/verify_observed. Keep whole startup3. |
| native_sdk | Extend P1 from_qualification_worker for exact adopted trial/operation owner with four channels; privately retain that owner identity. Reuse actual preflight/transport/capture, fresh-client limits and original stream rules. |
| native_profile | `NativeProfileBinding.from_qualification_worker(owner, *, kind, identity, data_hash, user_prompt, query_policy)` derives runtime/environment from exact adopted owner and verifies namespace/receipt/link/runtime identity. Share initialization; only this factory admits dummy environment. Default constructor strict. |
| improvement_claude; operation_profile | Add narrowly named `bind_qualification_runtime(self, owner, *, user_prompt)` for TrialProfile and `bind_qualification_runtime(self, owner)` for OperationProfile, mirroring existing bind_native_runtime validation while choosing the new concrete-worker factory. Existing options/client/before_query/delivery remain shared. Default bind_native_runtime unchanged. |
| improvement_worker; operation_worker | run_request distinguishes exact authenticated startup3 owner, accepts closed technical consistency on that branch, and keeps ordinary supported/hash gate. Emit existing worker_ready with authority_hash in wire capability_hash. Reuse actual profile/broker/engine/query. main routes matching startup3; malformed mixed routes never fall back to V1. |
| qualification_protocol | Closed nested version2 and descriptor consistency described above, preserving version1/preflight and ordinary startup2. |
| improvement_qualification_results.py (new) | Typed encrypted technical stage/final publisher/cold reader below, reusing existing events/blobs/owners. No schema. |

Filenames without `improvement_` in this table abbreviate the corresponding existing `server/improvement_*.py` names. These additions are proposed, not claimed present at stable source.

## Accounting, cancellation and cleanup ordering

1. Retain façade → proven P1 preflight/cache → exact technical admission with Session/host checks in reservation transaction. Real runner claims, holds brain/execution/lifetime locks, renews lease and performs current baseline5/view4/operation2 materialization, workspace.prepare and prepared.
2. Under runner lock derive descriptor and bind_attempt. maximum_queries counts **attempts**, not HTTP rounds or fixed CLI commands. Once link commits, budget is not refunded for subsequent no-start failure. Actual call refund/settlement still follows existing engine_at semantics. Concurrent budget loser does not launch.
3. Construct Guardian (P1 pure constructor), attach before acquisition, and start exact versioned startup3. Query scratch/HOME live under Session.root. Use the real workspace brain/.lifetimes fences from execute_worker_v2, not preflight scratch locks. Native lifetime ≤ remaining Session lifetime, real request deadline and existing native maximum300s. Do not extend leases/deadlines to fit the gate.
4. Worker installs environment before SDK/config imports; actual adapter_version/auth_status precede worker_ready. Actual SDK connect guards sdk_version then query process. All four image decisions are durable before first user write. **CLI query process creation/initialization can precede accounting ACK** under existing design; model/user input cannot.
5. On engine_start_requested, actual before_start rechecks Session/source/materialization/lease/link under lock, calls real start_engine to commit equal call/attempt engine_at, initializes actual NativeUsageRecorder, then returns. Callback completion precedes ACK. Cancellation during write is settled; engine_at without ACK remains charged/unknown, never refunded as not_run.
6. Check live Session and exact bound call again immediately before starting private ACK send, after awaited callback work. If close happens after send begins, it is in flight and must drain; never call it unsent or resend an ambiguous ACK. Worker checks exact ACK; original-stream delivery records only a completed actual user write.
7. Preserve raw observation2 global/per-source order and all four durable decisions. Real TrialEvidence/OperationEvidence and `_NativeRunnerEvidence` retain normal/closing packets, including usage when append fails. Missing/late/ambiguous evidence is diagnostic only. Require runtime/worker/Guardian close, native drained, actual zero exits and settled evidence before native detach/success.
8. Validate technical evidence while workspace is still held. Stage immutable evidence and settle actual call/attempt transaction, then clean workspace under lifetime lock. Final proof is published only after cleanup_proven, successful release_execution and no retained native/host/evidence owner. An unknown handle/task/stream/write/process cannot be cleared by timeout or result completion.

Session.close cancels new work and requests stop; it does not assert drain. Retry only retained close/evidence tasks after failure/expiry; never reopen a PID, restore launch authority, reconnect SDK or repeat a user frame. P1 actual owner retention remains the native basis; the new host-task retention closes the pre-native and post-native lifecycle gaps.

For forensic accounting evidence, the private completed-boundary witness contains closed `call_id`, `engine_at`, `engine_start_request_sequence`, `ack_identity_hash`, `ack_send_complete=True` and `input_delivery_hash`. The shared transport fills ACK fields only from the actual settled callback/private send and Guardian accounting state, never from worker JSON or a supplied callback return. Stage persists these facts with the execution evidence and rechecks their DB/trace/delivery joins. ACK send completion alone is not asserted to prove receipt; the exact worker continuation plus original-stream delivery gives the bounded evidence. Interrupted or ambiguous send produces no completed witness. This is another fact in the existing evidence event, not another ledger/debit.

## Immutable technical result and cold authentication

Proposed frozen `QualificationQueryResult` has closed fields (nested tuples/frozen records, defensive serialization):

```
version=1, domain='qualification', supported=False, account_ready=False,
business_proof=False, run_hash, kind, subject_id, attempt,
request_hash, materialization_hash, workspace_hash, engine_config_hash,
query_authority_hash, attempt_link_hash, preflight_hash,
release_fingerprint, review_hash, launch_nonce, environment_hash,
call_id, engine_at, trace_hashes, native_decisions,
installation_hash, input_delivery_hash, checks,
execution_status, cleanup='proven', cleanup_evidence_hash
```

No capability_hash property, product result/evaluation ID, readiness/activation verdict. execution_status completed/failed describes controlled protocol outcome. Checks retain pass/fail/unknown and production native_qualification unknown; dummy output does not prove model reasoning/correctness. Optional additional hashed output references require an explicitly versioned closed extension, never open report fields.

`QualificationQueryResults(session)` is a publisher, not executor. Proposed signatures:

```
stage(owner, principal, identifier, *, expected_generation, lease_token, binding, native_completion)
publish(owner, principal, identifier, *, attempt, evidence_hash, cleanup_receipt) -> QualificationQueryResult
@staticmethod
read_stored(assets, principal, *, kind, subject_id, attempt, expected_run_hash) -> QualificationQueryResult
```

**Stage:** after actual native drain while workspace/lifetime is held, require exact private completion retained by Session boundary (not caller cleanup=True JSON). Authenticate live Session, actual owner/source/lease/materialization, read_run/read_attempt, complete encrypted trace, four reread native decisions, call/usage, exact installation and original-stream delivery. Invoke existing execution_invariants/execution_checks with actual contract/prompt data. Preserve their native_qualification/semantic unknowns; do not call business evaluator/ordinary publication. Insert encrypted immutable `native_qualification_query_evidence` event with existing `_event`/blobs, keyed by run/kind/subject/attempt. Store descriptor/preflight/trace/checks and needed materialization proof here for cold validation.

The existing input-delivery wire basis string is `qualified_original_stdin_write`; keep strict existing grammar but explain in the technical report that this names the original-stream construction/check, not a positive production profile registration. Its explicit coverage and native_qualification unknown remain authoritative. Do not rename it without a separately versioned protocol change.

Repeat scope/source/lease/link/trace/decision/call checks **inside the final transaction after slow blob writes**. Add narrow `TrialStore.finish_qualification(self, session, principal, identifier, *, expected_generation, lease_token, evidence)` and the identical signature on OperationExecution, called by this publisher; `evidence` is an exact private staged-evidence type, not an accepted mapping. Factor existing settlement primitives if needed. These methods require exact Session and revalidate the staged evidence in their transaction. Reuse CallLedger._settle_in, row generation/CAS, terminal status and lease clearing. Leave product result_json NULL and ordinary artifact/receipt/result tables empty. Do not call ordinary finish/stage with a bypass flag. NativeUsageRecorder.finish remains real and precedes settlement; usage unknown is preserved. SQL call state does not come from handler request counts.

**Cleanup/final publish:** runner finally cleans actual workspace and releases exact lifetime, then supplies a private owner-produced cleanup receipt. Authenticate stage event and original SQL/link/trace/decisions again; require current/open Session for successful publication. Insert encrypted `native_qualification_query_result` event and cleanup evidence; envelope contains only IDs/hashes/blob refs. Missing cleanup or failed append leaves staged evidence and no successful result. Retain that pending proof operation in Session until settled. Evidence/cleanup retry never repeats settlement/query. After expiry, diagnostic cleanup can be recorded but cannot manufacture a current successful result.

There is a necessary two-phase distinction: stage proves execution while workspace is live and atomically settles its call; final immutable report proves subsequent cleanup. That is two evidence events, **not** two executors/ledgers or two budget charges. A crash between stages has truthful terminal call + incomplete proof, recovered using existing workspace cleanup and retained immutable evidence, never a silently successful report.

**Cold reader:** require explicit expected_run_hash equal to anchored store. Authenticate read_run, unique stage/result events, canonical hashes/decryption, closed false flags and descriptor/link. Call existing read_attempt using query_authority_hash as its capability_hash argument. Use validated_history/decode_trace, exact ordered trace_hashes, reread_native_decisions and original attempt_scope; rejoin actual SQL request/materialization/workspace/call engine_at and terminal status, plus stage/cleanup dependencies. Original semantic checks remain bound to immutable stage/input/trace, not refreshed source/runtime. Wrong/missing/duplicate anchor, altered SQL join, removed trace/allow/cleanup blob or unsupported version fails closed; stripping domain labels never yields product history.

Reader works after workspace deletion and Session.close through existing open_forensic, with no migrations/source scans/native calls and without requiring current candidate registry. Live registration removal prevents new launch/publication but does not erase authenticated historical evidence. Gate order: final native/workspace proof → Session.close → open_forensic/read → dispose reader → explicit Session.cleanup. Intentional deletion of the entire archive/key ends forensic availability; do not promise otherwise or copy private key/blobs to handoff.

## Real-owner RED/GREEN fixtures

New focused tests, leaving protected/historical tests and assertions unchanged. Reuse setup composition rather than inheriting/rerunning suites:

- QualificationSessionTests/QualificationRecordsTests: real encrypted anchored DB, calls, replay and budget contention. Their candidate/runtime/static observer seams are fixture-only; keep registry seam active during every new live check, not only Session.open.
- QualificationOperationBindingTests: reuse its Session-owned source construction with AssociationTests/HostContextStore/ExperimentPlans/OwnerTrialService/OperationExecution. Do **not** reuse direct phase SQL, input_version=1 patch or upstream reservation bypass for admission coverage.
- AdmissionTests, TrialRunnerTests, OperationExecutionTests, OperationRunnerTests and P0's scratch helper: real owner/call/lifetime setup. Root sources and pin genuinely belong to Session; technical adapter is not spoofed.
- `test_improvement_view_sources.SourceFixture`/ViewMaterializationTests with real ViewExperimentAdmission/EffectiveViews/ComparisonSchedule: linked view4 input. Declared synthetic preparation/reviewer data is allowed; ordinary successful engine product/capability cannot be fabricated to advance schedule.
- HostGuardianWindowsTests real three-actor adoption/drain, pending append and accounting ACK tests: actual sockets/handles/native owner. Inert child/capture seams remain fixture evidence. Use P1's committed startup3 fixture after it exists. BaselineWorkerTests' fake EngineeringSession/EngineeringBinding are useful local controls, not full native query proof.

Q1 proposed `tests/python/test_improvement_qualification_query.py`:

1. Real admission creates one trial/call; actual materialize chooses5; real prepare/prepared/bind produces one encrypted link. Real runner/Guardian carries exact startup3 to actual worker and SDK/profile construction; any inert capture/HTTP seam is explicitly labeled. Ordinary constructor/startup2/profile reject the identical environment. RED exercises missing consuming branch or actual refusal, not just missing symbol.
2. Block actual start_engine transaction: no ACK/user write. Release: equal committed call/attempt engine_at and real recorder before private ACK, then original-stream write. Recorder failure, cancellation after commit, source change, wrong/ambiguous ACK forbid input/retry/refund. Inspect DB and actual private-send/write ordering, not callback count alone.
3. Two prepared attempts compete for maximum_queries=1: one link/launch; loser settles/refunds via existing call rules. Replay does not charge twice or relaunch started/expired/closed attempt. Foreign owner/root/pin/link is refused.
4. Change source/protected owner/grant/context/materialization/call/lease during decrypt/blob write/pending durable allow: final transactions refuse at correct boundary before allow/ACK/proof. No always-true current-source seam.
5. Cancellation before admission return, during claim/prepare, pending authorization, SDK creation, user write, receive, close, proof append and workspace cleanup; repeated cancellation retains owners and blocks Session.cleanup. Nonzero exit/missing drain/late evidence yields no successful proof. Real usage survives append failure/lease loss.
6. Completed proof only after actual cleanup; product tables/result_json empty; ordinary TrialProducts/TrialResults/OperationResults reject before/after Session.close. open_forensic reads after workspace removal with zero runtime construction. Corrupt/deletion/SQL drift/cleanup missing fails closed.
7. Race after proof blob write reauthenticates trace/decisions/source/call under transaction. Staged-only result does not become success; cleanup/persistence retry never launches. Existing ordinary valid controls and P0 marker controls retain behavior.

Q2 proposed `tests/python/test_improvement_qualification_view_operation_query.py`:

- Ordinary view markers account_ready=False, domain qualification, both, and supported=True/hash spoof reject before reservation/call/holdout claim; valid ordinary control passes. Technical entry never calls ordinary verifier.
- Actual view4 cell admission, current view_hash/binding_hash, allowed asset/fixture read and exact installation/input delivery. Foreign/stale comparison/link/protected content refuses. Forbidden tools remain denied. Preserve scheduler semantics; no fake product to advance paired cells.
- Actual operation plan/state/request reserve→claim→operation2→query→technical proof, role/purpose/call refs and shared brain barrier. No synthetic Trial identity, proposal acceptance or semantic-review publication.

Portable tests prove grammar/DB/domain only; Windows inert fixtures prove their kernel/lifecycle orchestration. Neither proves the installed selected CLI.

## Exact installed selected-CLI localhost protocol gate

After Q1/Q2 freeze/review, observe full installed closure and independently record its exact candidate in existing REVIEWED_QUALIFICATION_CANDIDATES. Never self-register computed hashes, reuse old99/83/309 proof or fill REVIEWED_RELEASES. Candidate review must cover query consumers, not just P1 preflight. Authority module's existing fingerprint exclusion avoids a cycle but is not permission to auto-approve.

One final bounded matrix uses **actual Session façade and owners** for baseline5, valid baseline/candidate view4 cells and representative operation2, plus required in-flight cancellation/refusal cases. Pre-count attempts; maximum_queries remains1–32 and per-attempt deadlines remain unchanged. If needed use explicitly separate Sessions/anchors; no silent retries or increased limits.

Use installed selected CLI/SDK/pins, real Guardian/bootstrap/startup3/worker, NativeInvocationSet/NativeDebugInvocation, NativeProfileBinding/ClaudeSDKClient/original streams, actual localhost HTTP handler and actual DB/CallLedger/NativeUsageRecorder. No adapter/auth/capture/SDK/owner constructor patches, no no-op before_query, no prerecorded native trace. Fresh HOME, literal `javis-native-qualification-dummy`, exact numeric localhost endpoint and closed Session.environment. No ambient login/config, alternate model or provider connection. Preserve selected requested model/reasoning; synthetic replies prove protocol behavior, not inference by that model.

Reuse protocol **data shapes** from `test_improvement_native.py` Handler and `test_improvement_runtime_qualification.py.append_tool_calls`: /v1/messages/count_tokens, /v1/messages SSE, contiguous tool-use blocks, tool-result round, usage and final frame. Do not reuse legacy qualification_worker/_spawn/ack no-op or synthetic-local-provider-only environment: they bypass actual current ownership and use different environment contracts. Extract a narrow passive handler fixture if necessary. Bound/record method/path, dummy-auth boolean, body/response hashes, HTTP/tool counts; keep plaintext private. Own server/socket/thread shutdown; reject redirects/CONNECT/unexpected paths. Establish containment sufficient for this gate's no-provider scope; endpoint environment alone does not prove absence of unrelated CLI egress.

Retain each query worker's required adapter_version/auth_status/sdk_version/query observations. Avoid extra ordinary admission/parent verify_async preflights: one P1 verification per Session plus fresh static/current authority is sufficient for technical admission. Removing per-query observations would lower the unchanged trace contract and is outside scope. This is the permitted reuse: one stable-source installed stage, not redundant stages on unchanged intermediate bytes.

Assert handler receives no user message before actual engine_at+ACK; allowed paths/dummy auth only; one logical query per charged attempt (HTTP tool rounds differ); required tool/data/installation/input-delivery evidence; no resume; ordinary capability refusal; four durable allows; typed proof/cold read; and actual native/server/task/workspace cleanup. Reobserve exact installed source/runtime afterward. Prove native exit through retained original ownership/handles, not recycled historical PID opens.

External/runtime gates: independent final candidate review/registration, actual installed CLI dummy-auth/local protocol behavior, required platform/runtime availability and effective localhost containment. If it requires actual account, produces unexpected traffic/protocol, or cleanup stays unknown, retain exact blocker/evidence. Do not fabricate subscription auth, relax parser/assertions, switch model or register production readiness. Skipped/unavailable gate stays OPEN; fixture GREEN cannot promote it.

## Closure and remaining implementation detail

Every changed native/host consumer invalidates footprint. PROFILE_SOURCES is a seed list; observe_release must include new results module and newly reached imports/factories in actual content/manifests, not merely a renamed count. Preserve global IC.PROFILE_VERSION v2, explicit native v3 selection and historical formats. Test closure mutations invalidate candidate identity. Further changes after installed gate require affected requalification against new independently reviewed candidate.

No new schema is demonstrated necessary: existing events/blobs hold typed binding/evidence/result/cleanup; existing attempts own lifecycle and CallLedger owns accounting. A schema proposal would need a concrete invariant those records cannot represent. Budget remains existing attempt-event count.

Implementation still must settle exact private completion/cleanup witness types and safe shared runner-finally factoring; stage evidence/settlement and final publication must survive crash/cancellation without early detach. Exact operation creation fixture must use its actual valid plans/records path before claiming admission coverage. These are ordinary implementation decisions, not missing human intent. Installed transcript/containment behavior cannot be certified from this static design and remains a real runtime gate.

Each vertical needs meaningful owner RED/GREEN, independent scoped review, fixture limitations and cleanup evidence. Root retains final exact-head required CI/whole-branch review and integrated M2 handoff obligations. This report completes a bounded design, not M2D1/native qualification/M2 acceptance.
