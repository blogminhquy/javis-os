# D1 genuine native observations — engineering plan, not acceptance evidence

Existing full M0-M8 Goal and section12 apply. This follows the bounded view
observation unit. No new account attempt is authorized by this plan alone:
exact native qualification, current selected configuration and all existing
owner/grant/source checks remain prerequisites.

## Problem, intent and evidence semantics

Current actual checker always returns UNKNOWN for asset_observed_use and
actual_reasoning. TrialProfile always emits observed_use=unknown and no actual
reasoning value. ComparisonResults requires all18 integrity checks to PASS, so
this implementation cannot produce genuine eligible-final evidence. Synthetic
SQL rows or changing the all18 gate would hide the missing implementation.

Spec section10.3 requires observed actual configuration and an appropriate
host-observed asset call/read. It does not require private chain-of-thought or
proof of comprehension. New reasoning proof basis is explicitly
qualified_client_configuration: actual OS-owned native dispatch with verified
model/effort/fast/prompt configuration, tied to init/session and exact runtime
qualification. Provider acceptance and model-internal reasoning remain UNKNOWN.
Asset proof means exact immutable revision bytes returned by a successful native
tool call/result in the same trial/session/view; inline availability or model
self-report is insufficient. These semantics were independently audited against
actual source and SDK116; no implementation or runtime proof exists yet.

## Impact and source map before implementation

- improvement_worker._sdk_hidden_processes wraps actual SDK anyio.open_process.
  Separate --version from stream-json query children. SDK116 query connects
  before profile.before_query, so a native-spawn handshake belongs in ready
  state, before the existing engine_start_requested/accounting acknowledgment.
  Spawn is not inference; keep the current inference marker unchanged.
- improvement_native_transport.execute_worker owns the actual WorkerGroup.
  NativeLifetime guardian owns the exact Windows job and retained process
  handles. Current inventory returns PIDs only; add incarnation/image attestation
  through this owner, never trust a worker's PID or IsProcessInJob(any job).
- improvement_claude.TrialProfile binds manifest, selected options, init, models,
  calls/results and terminal. Its role composition is shared with OperationProfile;
  unbound operation roles must retain their existing fixture-only inventory.
- improvement_sandbox owns immutable materialized asset bytes and fixture grants.
  A new asset broker consumes the validated preloaded manifest, never canonical
  paths or arbitrary model-supplied filesystem references.
- improvement_trial_evidence/protocol/checks/results persist and validate raw
  traces in the existing encrypted store. Historical v1/v2 receipts/traces and
  reports must remain byte-exact and preserve their UNKNOWNs. New v4 execution
  uses closed receipt v3 with versioned dispatch/read proofs; no historical rewrite.
- comparison full18 and selection/qualification policy remain unchanged. Every
  new module reachable from native execution joins PROFILE_SOURCES in the same
  change. New exact qualification precedes registration and account inference.

## Unit A — prove the launch boundary before adopting it

Candidate ownership refinement (not yet implemented): the existing guardian can
own the exact selected CLI read guard before releasing the Python worker, hash
that same handle, and retain it through the whole job drain. Only runtime path/
hash/policy enter the supervisor, never model input, auth or account config.
This avoids relying on the worker to retain a guard after host/worker death or
adding cross-process duplicated file handles. The host validates query-child
incarnation/image/exact job through this guardian, then resumes its suspended
initial thread. No guard is released early merely because spawn succeeded.
Probe filesystem/ancestor semantics and SDK suspended-spawn compatibility first.

Primary references distinguish documented guarantees from pending experiments:
[CreateFileW](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-createfilew)
documents rejection of existing writable mappings without FILE_SHARE_WRITE;
[NTFS rename algorithm](https://learn.microsoft.com/en-us/openspecs/windows_protocols/ms-fsa/87f86c9b-6c2a-4803-84b7-131a74a434fa)
and [product behavior186](https://learn.microsoft.com/en-us/openspecs/windows_protocols/ms-fsa/4e3695bd-7574-4f24-a223-b4679c065b63)
cover ordinary open-descendant rename checks. Extended/POSIX rename and reparse
mutation still require actual negative probes on the configured filesystem.

- [ ] Inspect exact Windows process/job APIs and actual SDK116 command. Write
  inert, hidden owned-process probes using workspace-only test executables and
  isolated config; no account/auth/model access or installed-runtime mutation.
- [ ] Demonstrate byte/image binding through spawn, including replacement,
  ancestor reparse/rename and existing writable-mapping races. A path plus a
  later hash is insufficient when an updater can replace the loaded image.
  Select a bounded handle/OS guard only after these negative probes. Do not claim
  immutability from FILE_SHARE_READ alone or omit the race if unavailable.
- [ ] Extend exact guardian job attestation with process handle, creation time,
  image identity and owned job reference. Refuse foreign/unseen/exited/PID-reused
  targets. Keep handles under the existing guardian cleanup ownership.
- [ ] TDD closed native_spawned -> host verification -> ack in ready state;
  duplicate/out-of-order/stale/foreign events reject, cancellation and failed
  attestation drain the actual owned worker/job before workspace/slot release.
- [ ] Capture only sanitized actual launch configuration/hashes, never auth env
  values, raw secrets or account files. Refuse duplicate/override model/effort,
  unexpected resume, changed runtime/SDK/profile or unsupported command shape.

Proof v1 binds trial/attempt/input/engine_config, query_spawn_id, worker/native
incarnations, exact owned_job_ref, executable identity/hash, SDK identity/hash,
sanitized argv/config/prompt hashes, model/effort/fast, init/session and exact
qualification hash. It records basis, provider_acceptance=unknown and
internal_reasoning=unknown explicitly. Missing proof UNKNOWN; contradiction FAIL.

## Unit B — immutable v4 asset broker and native result correlation

- [ ] Add a v4-only readonly skill_asset_read(view_id, view_hash, asset_id,
  content_hash). Validate every field against the bound manifest and return only
  those immutable bytes. Wrong/foreign/missing revisions refuse without any
  canonical read. Baseline and candidate receive the same tool inventory.
- [ ] Each successful broker response creates a unique unpredictable
  observation_id plus request/response/content hashes and trial/attempt/view/
  session binding. Raw content remains only in the encrypted trace/workspace.
- [ ] SDK116 handlers receive arguments, not native tool_use_id. Join the broker
  observation_id and exact response bytes to native ToolResultBlock.content, then
  tool_use_id to ToolUseBlock.id/name/exact input in the same session. Never join
  by FIFO, timing or equal arguments alone. Test duplicate/parallel calls, replay,
  orphan results, missing/error/truncated content, forged IDs and cross-session
  data. None may PASS without a unique completed matching read.
- [ ] Only validated matched proof may set a revision observed_use=pass.
  Available/selected remain separate. Preserve unknown when the model skips the
  tool; no retry merely to force use or win. Instruction may ask the solver to
  retrieve intended assets, while owner/protected context and contract stay pinned.
- [ ] Unbound semantic/proposer/repair roles retain their separate inventory;
  operation input-read coverage remains UNKNOWN until independently implemented.

## Unit C — versioned checks, native qualification and actual pipeline

New actual trace diagnostic5eede64f also found a successful native tool_result
with is_error=null. Current strict event checks leave event/side-effect coverage
UNKNOWN. Verify the documented native/SDK optional-error semantics before
projecting any default; do not fill arbitrary missing telemetry as false. Include
actual native success/error/omission cases in this unit's coverage tests.

- [ ] Add receipt v3 and independent pure validators for both proofs. Keep old
  receipt acceptance and UNKNOWN behavior; reject malformed/mismatched new
  proofs. Update event schema/protocol summaries without altering old bytes.
- [ ] Test actual TrialRunner/CallLedger/raw trace lifecycle and no-result escape
  on stale grants, source edits, cancellation, crash, late results and cleanup
  failures. Retain all18 checks and existing owner/holdout gates.
- [ ] Scoped independent review covers changed native lifecycle/interface,
  ownership/image races, read correlation and old-reader behavior. Broader review
  is justified by this actual protocol change, not merely a continuation.
- [ ] Exact CLI/SDK/source local-provider native qualification covers at least
  two effort values, actual outgoing payload model/effort/fast/prompt, ambient
  override negatives, both asset variants, denied foreign tools/reads, duplicate
  correlation and guardian cleanup/recovery. Native internal reasoning remains
  unobservable; fixture responses are not account/business evidence.
- [ ] Register exact new footprint after qualification. Run one bounded fresh
  selected-account pipeline only after current configuration/grants verify.
  Record genuine pair, raw checks, usage and cleanup regardless of outcome. A
  candidate need not win. Final/qualification claim only when real prerequisites
  support it; owner accuracy and business/live gates are separate.
- [ ] Final-head CI/review, docs/PR/status and integration per repo. Continue
  full D2 immutable production task/session views, E/F, M3-M8; this plan does not
  declare those features supported or complete.

## Component/probe checkpoint

Standalone image read-sharing17 checks/review and immutable skill broker12
checks/independent parent review now pass; neither is a native caller. Their
metadata exclusion/loaded-image and native observed-use coverages remain UNKNOWN.
Physical NT image-name correlation probe (held-handle hash + actual suspended
child, positive junction alias/negative foreign identical bytes) is observed
but not file-object identity. Candidate next primary bridge is actual process
creation debug-event hFile, with valid file IDs and exact retained process/thread
handles before resume. No debug proof exists yet; thread-affinity, detach/resume,
cleanup and SDK compatibility must be demonstrated before lifecycle integration.
The current81-source native profile972175a2 remains unchanged.
