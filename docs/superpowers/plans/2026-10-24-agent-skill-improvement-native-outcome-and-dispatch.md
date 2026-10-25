# Exact native read outcomes and qualified client dispatch

Scheduling addendum2026-10-24: Goal§13 and
[code-first M0–M8 plan](2026-10-24-agent-skill-improvement-code-first.md) apply.
Complete all milestone code/technical tests first; account feasibility, business
pilot and real canary/rollout move to Phase2 with unchanged evidence/criteria.
Actual owned runtime/localhost dummy technical qualification remains Phase1.

Full M0–M8 Goal/section12 applies. Base ea74d62e/PR803/reserved0.299.0.
This follows the terminal native skill qualification20/93.952s, exact profile
04c8c77b and independent review. It does not authorize a new account retry.

## Evidence and smallest remaining gap

Actual CLI309/SDK116 paired controls returned exact host skill bytes and denied
the foreign asset. Success ToolResultBlock.is_error was None; denial was True.
The strict manifest3/receipt3 reader therefore retained UNKNOWN. Keep that
historical behavior and all18 gates; do not globally replace missing flags with
False or reinterpret old receipt summaries under a newer proof policy.

The primary [tool-result protocol](https://platform.claude.com/docs/en/agents-and-tools/tool-use/handle-tool-calls)
describes an optional error flag and associates results through tool_use_id.
The installed SDK116 parser uses block.get('is_error'), so omission and JSON
null both become None. A typed SDK object alone cannot distinguish them.
Accordingly a new outcome can only be derived from exact successful host
response delivery, not from assuming either wire representation was observed.
Raw optional flags stay unchanged and separately visible.

The existing native-observations plan defines actual_reasoning proof as
qualified_client_configuration: observed native image/dispatch model, effort,
fast mode and prompt bound to the session and exact qualification. Provider
acceptance, private reasoning and instruction comprehension remain UNKNOWN.
This unit retains that existing distinction; it does not inspect private thoughts.

## Version and impact boundary

Use new input manifest4/receipt4 when the complete new dispatch/outcome boundary
is ready. Request protocol remains v4; input/receipt versions are separate
namespaces. Preserve manifest1/2/3 prompts, tool responses, receipt field sets,
hashes and historical UNKNOWN behavior. An old reader rejects unsupported input4.
The new manifest retains the strict single immutable skill, context, contract,
fixtures and exact effective_view descriptor. No source/grant/owner policy change.

New standalone components may first consume an existing validated immutable
manifest for synthetic component checks. They are not reachable from execution
or added to PROFILE_SOURCES until actual integration. Do not repeatedly
requalify native20 after each standalone edit. At integration, every reachable
new module joins the exact footprint, then one frozen boundary is qualified.

Affected consumers at integration:

- improvement_sandbox/materialization: new input version and prompt identity;
  reuse source checks before/after decryption and old version renderers.
- TrialProfile/options/handlers/observe/installation receipt: version4-only
  read envelopes and sanitized actual dispatch observations. Unbound roles and
  legacy trials keep their existing fixture-only behavior.
- FixtureBroker: retain existing source events, grant/fixture validation and
  history summaries. New envelopes wrap its actual return; do not invent a
  second source ledger or bypass misses. Skill bytes remain preloaded only.
- Trial evidence/protocol/checks/results: encrypted raw events plus a closed
  receipt4, independent outcome/dispatch validators, same18 check IDs. Shared
  operation-check helper signatures/default inventory remain compatible.
- Native transport/worker/lifetime guardian: actual ready-state spawn ACK,
  retained exact process/job/image ownership and full debug/job drain. Preserve
  the existing inference accounting ACK and cancellation/exposure semantics.

## Read-outcome foundation, then native integration

1. Design one closed host read envelope for the two authorized readonly tools.
   Bind trial/attempt/input/effective view, tool kind, exact arguments, pinned
   payload/content hash and a unique unpredictable response identity. Retain
   canonical emitted text/hash as immutable host observations. Failed requests
   remain content-free and never read canonical paths or live sources.
2. Use the existing FixtureBroker for actual fixture decisions/events and the
   selected immutable skill for skill reads. Keep host response observations
   detached from caller mutation, including equal parallel requests. A broker
   return alone is not native delivery or business proof.
3. Pure correlation joins every response identity/text to a unique native result
   and its actual call ID/name/input in the one initialized client stream.
   Reject duplicate/orphan/replay/wrong-tool/foreign-session/changed bytes.
   Do not join by timing, FIFO, equal arguments or a receipt-only assertion.
4. For input4 only, exact successful host response plus matching native delivery
   may establish outcome basis exact_host_success_and_native_delivery when the
   raw optional flag is False or None. Explicit native error, contradictory host
   status, malformed/truncated content or absent correlation cannot pass. Keep
   native_error_value raw; never write a fabricated raw false flag.
5. Independently verify denied reads too. A matched explicit native error plus
   actual host denial is safe boundary evidence, not a successful asset read.
   Missing or ambiguous denied outcome stays UNKNOWN. Source coverage, business
   quality and owner acceptance still have their own existing checks.
6. Receipt4 contains only closed summaries recomputed from raw records.
   event_coverage/side_effects may recognize the version4 derived basis only
   after independent validation. Generic missing telemetry, legacy fixture
   traces and unknown tools retain their existing UNKNOWN/fail behavior.

Meaningful RED/GREEN cases: success with False; exact host/native delivery with
None; None without host response; explicit error contradicting successful host
return; genuine denial; altered/foreign/missing/truncated/replayed envelopes;
parallel equal requests delivered in reverse order; mixed valid+orphan/wrong-tool
replay; caller mutation; old manifest/receipt UNKNOWN byte compatibility.
Native local-provider controls must retain actual omitted-success/explicit-error
evidence and exercise both asset and fixture tools. No model/account retry to
manufacture a successful proof or candidate win.

Standalone foundation API is PinnedReadOutcomeBroker(manifest, *, trial_id,
attempt, input_hash, fixture_broker=None). It reuses exact existing immutable
SkillAssetBroker and concrete FixtureBroker decisions, with a whole-read lock.
Its read(tool_name,args) returns a defensive envelope with exactly version1,
observation_id, trial_id, attempt, input_hash, effective_view, tool_name,
request_hash, outcome(hit/miss), result. Hit result is the unchanged underlying
broker result; miss result is only generic read_miss status/reason. Unknown
tool names or non-JSON inputs fail closed. No additional runtime source is read.

Observations have exactly version1, observation_id, trial_id, attempt,
input_hash, effective_view, tool_name, request, response_text, response_hash.
Both response and observations are retained as immutable canonical JSON and
returned defensively. Actual fixture events remain in the existing FixtureBroker
and are exposed defensively, rather than synthesized by the wrapper.

The standalone correlate_read_outcomes(manifest,workspace,events) validator
accepts only new trial_read_broker_observation records, never old asset records.
It returns verdict/reason/proofs. Successful proof basis is
exact_host_success_and_native_delivery; verified denial basis is
exact_host_denial_and_native_error. Summaries retain raw native_error_value,
tool/call/session/attempt/view/input identity, request/response hashes and outcome.
Both raw error fields must be present and agree; None is an observed SDK value,
not a substitute for an absent trace field. A successful hit requires exact
pinned underlying payload; fixture sequence is a positive unique integer.
No partial proof list escapes if another recorded read is uncorrelated.
This API remains unreachable until version4 integration; accepting a validated
old manifest in a standalone fixture is not permission to reinterpret old trials.

## Native dispatch/image foundation

The raw debug probe V1 failed before initial resume. V2 instead assigned the
actual job, used bootstrap Resume1, and held the documented pre-user-mode CREATE
event during actual image hFile identity/hash checks. Accepted code rearmed
Suspend0, continued CREATE, then final Resume1. Denied identical-byte foreign
image had no accepted continuation or post-attestation resume. This is a distinct
lifecycle, not a repaired report for V1.

First prove the SDK-imported anyio.open_process creator thread can own a
persistent debug pump through CREATE/EXIT without preventing pipe setup,
cancellation or process wait. A bounded inert compatibility probe now passes
three cases: selected image, identical-byte foreign image, cancel before local
ACK. Driver2.516s, actual same-thread CREATE/EXIT and anyio wait/aclose/job drain;
independent limited static review verifies29 artifact/runtime/source pins.
No guardian IPC/death/full SDK transport proof exists. The next small experiment
is an inert two-process receipt/ACK/drain boundary with exact worker incarnation;
no production integration precedes that evidence. Keep actual copied executable,
own job/marker, empty HOME and hidden process; no Claude/account/provider call.

Guardian must not receive model input, auth or the actual configured SDK argv/env.
Two recorded designs remain: a qualified worker-owned capture with duplicated
actual handles checked by the guardian, or a guardian-owned fixed Python worker
DEBUG_PROCESS descendant chain with opaque direct host-worker data pipes.
DuplicateHandle alone does not prove the supplied image handle originated in
the claimed CREATE event; explicitly retain the trusted capture-code assumption
or use direct guardian kernel events. Select after compatibility evidence.

At integration require actual retained worker/native incarnations, exact job,
actual debug image file ID/hash versus guardian-held read guard, closed launch
nonce and state transitions. Capture sanitized actual SDK launch arguments at
the OS dispatch boundary, not merely requested options. Reject duplicate model/
effort overrides, fast mode, resume, unsupported command shape and runtime drift.
Capture only the required values/hashes; no raw auth environment, secrets or
account files. Tie actual prompt/configuration to init/session and qualification.

Native image ACK in ready state precedes allowed execution/SDK query. The
existing engine_start_requested/ACK still marks inference/accounting separately.
On denial/cancel/death/timeout keep pumping owned debug EXIT before blocking job
drain; require independent process handles signaled and job quiescence before
workspace/slot/fence/guard release. A lost pump never authorizes cleanup success.

## Verification and exit from this unit

Self-review: version4 is necessary to preserve the newly committed version3
UNKNOWN semantics. Derived delivery is based on actual unique host/native bytes,
not a generic optional-flag default. Configuration proof is not private model
reasoning. Exact same two readonly tools for both paired arms; source/grant,
contract, owner/holdout, usage and all18 gates remain intact.

Run affected checks sequentially with frozen source pins; reuse unchanged
source-qualified component/reader/ledger proof. Review the actual changed
interfaces/lifetimes, then qualify the frozen native boundary with two effort
values, ambient override negatives, both read kinds/variants and cleanup/death
controls. Register exact evidence only after it passes. Final-head CI and scoped
independent review precede integration. Only then assess one bounded configured-
account pipeline under existing Goal authority/current selected configuration.
Continue independent full D2/E/F/M3–M8 work; business/live gates stay open.

## Dispatch consumer audit and next pure component

Read against committed df0e24b1 and installed SDK116. Adapter.verify runs native
`--version` and `auth status --json` in the host and again in the worker, before
worker_ready. SDK connect separately runs `-v`, then spawns the query process
before TrialProfile.before_query requests the existing inference ACK. A query
image gate alone cannot cover those other invocations. Keep separate explicit
purposes for bounded version/auth preflight and query, with no query capability
or reasoning proof inferred from a successful version check. Each actual native
invocation needs owned image/lifetime verification at integration.

SDKClient replaces permission_prompt_tool_name with stdio when can_use_tool is
present. The actual query grammar therefore includes --permission-prompt-tool
stdio, --permission-mode default, empty --tools, the exact allowedTools list,
literal --system-prompt, selected --model/--effort, inline --settings with exactly
fastMode:false/disableAllHooks:true, inline --mcp-config containing only the
fixture/skill SDK server descriptors, --strict-mcp-config, --setting-sources=,
and the existing five restrictive extra flags. SDK116 strips the in-process
server instance; each CLI descriptor is exactly type:sdk/name:<server>. It ends
with --input-format stream-json. Reject unknown/duplicate/override flags,
file/preset prompts, ambient setting sources, extra servers, resume/fallback,
partial/hook output, plugins and thinking overrides. Do not silently repair
an unsupported argument shape.

Next standalone component: a pure closed query-dispatch validator, unreachable
from execution and outside PROFILE_SOURCES until integration. Its input includes
the actual argument vector captured around SDK open_process and the actual raw
Windows CreateProcess command line, executable parameter, cwd and creationflags.
Require exact subprocess.list2cmdline agreement and an explicit expected pin
(CLI path, selected model/effort, prompt hash, workspace cwd and exact two-tool
inventory). Validate inline JSON with duplicate-key rejection and strict boolean
types. Preserve only sanitized selected values/hashes in its result; never emit
argv, prompt, raw settings/environment, auth or paths to guardian control IPC.
The result proves argument consistency only, not that this function ran at an
OS boundary, that an image was loaded, or that the provider accepted reasoning.

RED/GREEN cases cover actual SDK116 command construction without connect or a
native child, two efforts, raw-command mismatch, executable/cwd/flag drift,
duplicates/foreign flags, changed prompt/model/effort, JSON duplicate keys and
boolean-number confusion, external MCP servers and nonempty source lists.
No account/native qualification is justified by this unreachable parser alone.

The ready-state protocol also needs explicit evolution. Existing engine_event
requires a usage recorder and is illegal before inference ACK; do not encode
native launch controls as early engine events. Use a closed new packet/control
state for input4, persist its raw host evidence, and keep operation/legacy packet
semantics unchanged. A parent image allow decision must precede native execution;
the separate before_engine_start callback still marks exposure/accounting before
query submission. Cancellation or storage failure cannot discard ownership.

The first two-process V4 probe refused the venv redirector: retained launcher PID
15128 differed from actual trusted worker PID23332. No remote duplication or ACK
was attempted. Exact outer job drain preceded image-guard release; failed report
e9e73a48 and its separate frozen manifest54ed1d8a remain preserved. A distinct V5
probe will test direct hash-pinned base Python with -I -S and a fixed explicit
trusted site-package bootstrap. Never accept a receipt-supplied worker PID or
reopen a bare PID to bypass this refusal. This is not yet production transport.

V5 failed before any valid worker receipt. Its stderr was DEVNULL and the rejected
frame/exit code was not saved, so the historical startup cause is UNKNOWN.
The outer job drained before guard release. Subsequent static tracing establishes
an unsupported dependency in that bootstrap: SDK imports mcp, whose package
initializer imports client.stdio and then mcp.os.win32.utilities. That module
imports pywintypes, win32api, win32con and win32job. Installed pywin32.pth normally
adds win32 and win32/lib and runs its DLL bootstrap; the V5 fixed -S path list
omits them. The next diagnostic is import-only, with early startup/error capture,
fixed explicit paths/DLL directory and process creation disabled inside the
imported worker. It tests a concrete import hypothesis without another native
image run. Preserve V5 unchanged; no automatic follow-up image probe.

Future three-actor transport must transfer a retained worker capability into the
guardian while both source/target processes are retained, rather than pass a
receipt-supplied PID for reopen. The guardian retains only native runtime/image
identity and closed handle/nonce metadata. Host-to-worker input remains direct.
Treat the direct-base bootstrap and its DLL/import dependencies as a changed
runtime boundary requiring qualification, not an alias for old venv execution.
Never patch CreateProcess globally in the shared server; creator instrumentation
belongs in an isolated fixed worker or a purpose-specific owned preflight helper.

The separate import-only diagnostic V1 also stopped before SDK imports: early
direct-base worker PID/birth matched the retained process, but native job
accounting reported total2/active2 rather than its assumed total1. Parent refused
the import ACK, drained the exact job (active0), and saved exit91/stderr0 plus the
first raw frame. The second variant was not run. No SDK import outcome or second
member identity was observed. Preserve report c4b5d553 and the failed assumption.
Do not label the extra member conhost or an SDK child without actual evidence.

This now requires revising the experimental measurement boundary before another
run, rather than another bootstrap guess. The actual requirement is no SDK
process creation during imports; a fixed total1 was an added experimental
assumption. A bounded next diagnostic can capture the exact native-job startup
member set with retained process identities, birth times and observed image
paths before import ACK, then verify cumulative birth count/membership do not
change during imports and the rejecting CreateProcess counter remains0.
Inventory originates in the actual owned job, never a worker-supplied PID; any
query-opened member handle must be rechecked for exact job/incarnation and held
through terminal drain. Unknown identity or incomplete inventory stays unknown
and never authorizes a native image ACK. This is not a relaxation of the final
query process/image/guardian identity or lifetime requirements.

Runtime binding must include actual SDK implementation hashes, not only the
installed distribution version. The future qualified boundary should compare a
closed SDK/capture/bootstrap source manifest against its qualification record,
check those bytes before execution, and include the verified manifest hash in
capability/dispatch proof. Keep historical qualification entries/receipt bytes
unchanged. A new capability must fail closed when its actual source manifest is
missing or changed; do not authorize modified SDK code because its version
metadata still says0.2.116. Query/init model checks remain separate from argument
consistency, and private reasoning/provider acceptance remain UNKNOWN.

Synchronous preflight needs its own lifetime design: _runtime_observation uses
subprocess.run for version/auth, which blocks in communicate/wait. Holding its
debug CREATE/EXIT on that same blocked thread would deadlock. The SDK-anyio
same-thread async probe does not prove this synchronous consumer. Use a bounded
purpose-specific isolated preflight helper with an active creator/debug pump,
or independently qualify a dedicated creator/pump thread; never globally patch
the shared server or stop pumping before the owned native process is terminal.
This choice and its cancellation/drain evidence precede production integration.

Concrete consumer choice: keep synchronous admission/services compatible through
a blocking facade over a purpose-specific isolated async preflight helper. Existing
worker run_request already has an event loop and outer job; it must await the async
core instead of spawning another helper or calling asyncio.run. The closed purposes
are adapter_version, auth_status, sdk_version and query; the preflight facade cannot
request query or accept arbitrary argv. Host admission has no attempt workspace,
so its helper needs explicit scratch/lifetime/fence ownership rather than borrowed
attempt fences or putting the shared server in a disposable job.

Per-invocation evidence must remain separate from the stable capability runtime:
verify hashes the whole observed runtime, and repeated host/worker verification
requires equality. Bind a stable versioned policy/runtime-source fingerprint there;
never add unique launch nonce, PID, birth or receipt bytes to capability_hash input.
Plain await to_thread(adapter.verify) can abandon its preflight thread on caller
cancellation. Reuse existing settled-call ownership or an owned async verification
path, and finish helper/native drain before returning cancellation to its caller.

Next canonical code extracts NativeDebugInvocation from the V6 lifecycle. It owns
one actual saved SDK-anyio open_process call, a pre-create purpose-specific argument
validator and a cooperative async closed image-ACK callback. It returns the original
anyio Process only after the held CREATE allow/final resume; a persistent pump stays
on the creating event-loop OS thread through EXIT while SDK wait/aclose can run.
Actual CreateProcess instrumentation is isolated-worker-only. On cancellation or
failure retain spawn/raw handles/events/pump/ACK/process/streams until cleanup is
proven; an uncooperative ACK cannot be reported quiescent. The blocking stdin readline
used in probes is not yet a cancellable production ACK channel and is not promoted
by this component. No runtime caller or qualification entry is added before the
guardian/bootstrap/control integration and its frozen proof are complete.

SDK116 already accepts a custom transport. A new-version profile can construct a
SubprocessCLITransport subclass with explicitly replaced stdio permission-prompt
options (SDKClient's replacement is otherwise unused by a preconstructed transport).
Original options still drive SDK Query callbacks. This gives a concrete integration
consumer for the launch owner and exact user-frame write observation while retaining
the original transport write lock/readiness/exit checks. Legacy engines/profiles
keep their existing path; no shared-server global process monkeypatch is permitted.

## Operation input delivery and version boundaries

The operation consumer has an additional real blocker: execution_checks always
returns UNKNOWN for actual_input_use as well as actual_reasoning. OperationResults
aggregates every check, and SemanticReview combines that verdict with meaning and
dependency checks. Fixing Trial4 alone therefore cannot make semantic operations
eligible. Owner arbitration must not erase a native UNKNOWN.

Spec10.3 requires actual configuration and appropriate host call/read evidence;
it explicitly does not infer comprehension. A new qualified_native_user_input_delivery
basis must mean exact execution delivery, never comprehension, native read ACK,
provider acceptance or semantic correctness. A completed stdin send alone proves
only pipe delivery. Native parsed/read confirmation would require an independent
per-input ACK or echo, which SDK116 does not provide for this string-query path.

Before implementing this basis, bind the materialized data hash and the hash of
the entire operation_user_prompt wrapper to a fresh single-client/single-query
dispatch. Capture the actual user frame on the retained native child's real stdin
transport, recording completion only after await send returns. Bind an unpredictable
write nonce to operation/attempt/input/dispatch; reject partial, failed, cancelled,
truncated, changed or duplicate writes, replay/resume and foreign sessions. Require
native init plus assistant/terminal session evidence on that same fresh transport
without contradiction. The frozen local-provider qualification must verify that
the actual provider request contains the exact user content and exercise those
negative controls. Requested client.query arguments are insufficient.

SDK116 client.query serializes its string prompt as a user frame with the wire
session_id default. The native init uses a distinct native session identity; keep
both namespaces and qualify their fresh-transport mapping rather than compare them
as equal. connect may produce init before query's stdin write. Do not require a
false init-after-write ordering or invent a query UUID absent from the actual frame.
SubprocessCLITransport.write uses its write lock, checks ready/process/exit state,
then awaits TextSendStream.send; capture must retain those lifecycle protections.

Use operation materialization2/installation receipt2 and dispatch/input-delivery
proof1 with strict readers; report/check-policy identity must be versioned (report2
if proof/policy fields are added). Request1 can remain only if its contract is
unchanged. Evolve operation protocol/execution/workspace/profile/worker/checks/
results and semantic evidence/replay together. Old version1 bytes and UNKNOWN
verdicts remain unchanged; never recompute historical reports upward. All three
operation roles retain their fixture-only tool inventory. The standalone Trial
query parser's exact two-tool grammar is not the operation grammar. Keep combined
verdict, owner/source/grant/usage and all eligibility checks unchanged.

The pure parser now has an explicit expected pin2 tool_policy. fixture_only checks
exactly the existing single fixture SDK tool/server; pinned_skill checks exactly
fixture plus skill. No arbitrary inventory or role/purpose field is accepted. Pin1
and its full result bytes retain their two-tool behavior. This is grammar choice
only, not authorization. Actual shared unbound operation options/SDK116 command
construction pass at two efforts, without connecting or constructing an operation.
Pure8 RED/GREEN and affected17 regression pass; independent sequential17+8 approve
unchanged source/test hashes. A first overly deep invocation temp failed two old
fixture subcases at a269-character Windows lock path; the preserved failure and
short-private-temp passing rerun are recorded separately. No assertions/product
authority were changed. This component remains unreachable/outside PROFILE_SOURCES.

## Canonical components and concrete guardian integration

NativeDebugInvocation and its lazy x64 Win32 helper now pass11 actual isolated
component tests, independently11PASS4.300s. It returns the original SDK-imported
anyio Process after allow/final resume, with the creator-thread pump through EXIT.
Privacy/equality-spoofing failures were reproduced and corrected before freezing.
Failed event reads, handle close or uncooperative callbacks retain the owner for
retry. This proves one-process lifecycle with fixture ACKs, not image association,
whole-job/death recovery or a three-actor SDK query. Exact pins and REDs are public.

The fixed bootstrap independently passes12 tests plus1 Linux-only skip. It reads
exactly one bounded manifest frame, verifies declared current runtime/source/import
files with public guards, executes captured fixed target bytes and retains guard/DLL
cleanup ownership. Actual direct-base child startup, initial loaded sections,
unlisted imports and externally authenticated complete-manifest authority remain
unproved; the real file/module fixture simulates isolation flags. No runtime caller.

Canonical ImageMetadataChannel now supplies one owned connected socket and a closed
CREATE/ACK exchange: corrected13PASS1.588s and independent13PASS1.447s on unchanged
source12cce111/test2df8f4fa. Its first shutdown-only implementation failed on pending
Windows WSARecv; preserved evidence is not cleanup success. Poison, shutdown and
known successful socket close precede actual UNCANCELLED logical IO completion;
only then can closed=true be reported. Keep close-success separate from IO settlement;
partial frames poison the channel and lost close authority stays permanently
unproven. No blocking reader thread is promoted.
Only bounded strict metadata schemas and nonce/incarnation binding are allowed.
Later endpoint transfer uses actual held target incarnations, never receipt PIDs.
Python documents [socket sharing](https://docs.python.org/3.12/library/socket.html#socket.socket.share)
and [async socket IO](https://docs.python.org/3.12/library/asyncio-eventloop.html#working-with-socket-objects);
these are design references, not evidence of a cross-process run.

Initial ownership needs guardian-first creation: host-Popen-then-assignment has a
host-death gap. Precreate job/inventory/fences outside the worker; fixed guardian
creates the bootstrap root. Seal all transient guardian copies of worker stdio
before the host sends private packets. Only closed runtime/source/image policy
and native metadata reach guardian. Selected executable path/hash is allowed image
metadata; full config/model/SDK argv/env/auth-home stay on direct host-worker data.
Install the allowed worker environment before engine imports/verify. The guardian
is trusted qualified fixed-purpose code; debugger handles provide no memory
isolation against compromised guardian code, and none is claimed.

Use a guardian-only direct CreateProcessW/STARTUPINFOEX factory with JOB_LIST
and exact HANDLE_LIST. Microsoft's [attribute contract](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-updateprocthreadattribute)
supports creation-time job assignment on Windows10/Server2016+. Installed CPython
must not be assumed to support a job_list attribute dictionary. The native factory
avoids Popen std-handle mutation and the unassigned-root cleanup special case;
unsupported/attribute/create failure refuses without fallback. Explicit Unicode
environment and extended startup flags belong to the fixed-root grammar, separately
from the SDK query parser. Do not add a speculative post_create hook to the frozen
SDK capture. Actual root image/debug and nested worker-native ownership still need
qualification. Host adopts a duplicated retained worker wait/query capability from
the retained guardian, never PID reopen. All18 and authority/usage/fence/CI gates stay.

The fixed factory is now independently approved on672d55e8/test0624ea4d:16PASS
and1Linux-onlyskip2.098s. It owns preallocated native acquisition outputs; only
explicit native CloseHandle FALSE permits retry. Interrupted/ambiguous results
remain unproven. Public fixed-worker-launch evidence preserves failed fixture
assumptions and real product REDs separately. Do not rerun this standalone proof
merely to resume integration; the original pipe sealing/full job consumer remains.

Concrete GuardianV2 owner: constructor receives only factory policy, selected
image path/hash, two recovery fences, launch nonce and a fixed ordered subset of
purpose/nonce bindings. run(owned_control_socket) and aclose() own same-loop control,
same-creator root debug events, raw worker/job capabilities, original data-pipe
copies, purpose image channels, guards and retained cleanup. Initial launch_offer
includes actual held root CREATE/image comparison and process/thread incarnations,
borrowed source capabilities and target-bound socket-share blobs. Host adopted
means duplicated/verified host capabilities and retained blobs, not worker adoption.
After all original/transient guardian data-pipe capabilities are known closed,
stdio_sealed permits host startup input and root gate release. Worker adopts image
and private control endpoints from its later direct startup packet. Guardian never
receives that private control share, config/model/auth-home or user input.

Strict bounded canonical control2 frames carry launch binding and monotonic
per-direction sequences. image_observed carries purpose/incarnation and closed
comparison/hash; image_authorize must match the exact pending observation and
dispatch/durable evidence hashes. Host persists joined dispatch/image observations
under current lease/generation before authorization; inference/accounting ACK stays
separate. Stop/EOF/denial/expiry/malformed frames trigger owned drain. Native drained
means root/debug/job/guard proof only; control socket IO settlement remains separately
owned through aclose. No ambiguous share/close/IO result becomes cleanup success.
Missing GuardianV2 produced11RED0.154s; focused real Windows inert implementation
tests remain distinct from a full three-process host-death or genuine SDK proof.

Correction to the initial root-kill setup order: a fresh creator thread cannot
call DebugSetProcessKillOnExit before a debugging connection exists; the actual
attempt refused with WinError6 before child creation. Microsoft's
[primary contract](https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-debugsetprocesskillonexit)
requires an existing CreateProcess/DebugActiveProcess connection and documents TRUE
as the default. Dedicated fresh guardian startup therefore uses that default for
atomic debug creation, explicitly sets/checks TRUE immediately afterward and before
any Resume/private release, and retains raw process/job ownership on failure. No
attach/detach workaround or preexisting thread with disabled default is allowed.
One actual inert root case now passes1.231s (root CREATE/file gate, transferred
stdio/socket offers, sealing, root EXIT/signal/job0/fence/control drain); remaining
image/negative cases and independent review are still pending. This single case
does not qualify full three-actor/death behavior or genuine SDK startup.

In parallel, actual bare-to_thread verification cancellation was reproduced in both
adapters and both runners. Reuse existing settled operations rather than abandon
version/auth threads on cancellation; retain brain/execution ownership until they
settle and never proceed to query after cancellation. These existing-source edits
invalidate04c8 as current qualification; preserve its historical evidence and wait
for complete-boundary freeze/qualification before any account retry or registration.

Concrete startup2/private2 grammar and shared PrivateWorkerChannelV2 are now in
the new native_protocol/private_channel modules. Pure11 and socket9 have independent
scoped approval with exact public proof. The private endpoint prunes completed
consumed stream tasks/frame buffers, retains uncertain I/O, and keeps actual close
success distinct from cancellation and IO completion. Its isolated socketpairs
and pure in-memory tests have documented Goal12 isolation from native job fixtures.
No current profile registration or native child proof follows from these tests.

Guardian/host policy separates immutable overall lifetime_timeout<=300 from short
startup/actual CREATE/authorization deadlines;300 is the existing public trial and
experiment maximum. Do not impose a60s idle timeout on legitimate long inference
or start all four one-shot image clocks at adoption. Public socket readiness arms
the later channels only when bytes/EOF arrive, with channel-exclusive read/close.
No packet renews the overall budget. Actual delayed-channel proof passes1.966s
using short.05, delay.10 and overall5; its initial overall1 correctly timed out.

Host consumer uses the original retained guardian process handle to adopt actual
worker capabilities. It persists a version2 launch_offer projection with root
identity/image/purpose nonces and hash of exact full canonical received wire JSON,
omitting live handle numbers/share blobs. Raw offer stays privately owned through
adoption/drain; projection/hash never confer capability authority. Incoming host
envelopes have fresh sequence plus source/source_sequence (guardian or worker),
launch/PID/birth and closed body. Durable joined evidence callback returns only
decision and persisted evidence hash before image_authorize; cancelled/late append
must settle but cannot send allow. Existing accounting transaction remains the
separate inference gate, without inventing a third evidence source. Actual SDK
connect precedes before_query: first2 gates precede worker_ready, all4 precede
engine_start_requested/accounting ACK, then client.query delivers private input.

Guardian author24 passed14.572s before independent review reproduced one false
control-close proof: cancelled logical socket I/O was swallowed as completion.
Correct only that retained-control state, then verify affected final suite once;
independently proven native_drained/fence release stays separate from metadata-only
control.closed. Host source-missing9RED is preserved; concrete source implementation
and actual three-actor tests remain underway, with no account/SDK/profile enabling.

## Current consumer integration sequence

Guardian component is now approved at source4b9ee58c/test370474d2: author25 and
independent25 pass against exact imageb8 dependency. POSIX-only channel changes
do not alter default Windows Proactor execution; early Linux CI40029282316 checks
the seven-file portable snapshot a86c716e, not the unfinished runtime boundary.

Host author21 passes after five meaningful REDs for four independent ownership
findings: cancelled raw/thread task completion, partial public startup without
stdin EOF, acquired-but-unassigned Popen and socket registration after fallible
configuration. Source5b1c7cf8/test389a473a awaits narrowed independent correction
review. SDK source4414befa author19 is historical pending two reviewer corrections:
consumed stream task/result accumulation and immutable original Process/raw stdin/
SDK wrapper binding. A completed send is still delivery evidence only. Do not
start another native qualification on these intermediate candidates.

Next root changes have these concrete caller/dependency boundaries:

1. Add the actual startup2 worker consumer and route only new canonical initial
   packets from the fixed Trial/operation entrypoints. Verify actual self PID and
   creation time before fromshare; install the exact private environment before
   broader configuration/SDK imports. Own every socket immediately upon native
   acquisition, adopt endpoints first, and retain failed owners through actual
   drain. Legacy first-packet semantics/valid bytes remain unchanged. The new
   consumer must use NativeInvocationSet rather than the legacy hidden-process
   shim or duplicate preflight subprocesses.
2. Share the existing supported/capability checks with already observed closed
   preflight runtime without allowing observation data to bypass source/runtime
   registration. TrialProfile and OperationProfile supply an explicit fresh
   client factory to the actual SDK engine using the qualified custom transport.
   First two purposes gate worker_ready; all four gate engine_start_requested;
   the existing accounting ACK gates actual client.query. Client disconnect and
   invocation-owner close both remain owned. No new model/provider/default limit.
3. Extend durable Trial/operation readers and writers together for the strict
   version2 host envelope, global sequence, per-source sequence and exact launch/
   worker incarnation. Preserve old version1 bytes/readers and prohibit mixed
   histories. Existing encrypted observation tables retain late observed usage
   under actual writer/lease/generation checks, including UNKNOWN cleanup.
   Fresh admission preflight has no attempt workspace: reuse ImprovementStore's
   existing improvement_events transaction/idempotency and encrypted blob store
   for durable joined dispatch/image decisions. Store only hashes/blob references
   in public audit metadata; no parallel ledger, invented attempt or inferred ACK.
   Recheck current authority/config within the durable transition before allow;
   cancellation waits for the real transition but cannot release a late allow.
4. Version Trial manifest/receipt4 and operation materialization/receipt2 with the
   native dispatch and exact completed-input-write proof. Independently verify
   full expected user wrapper/content, fresh single transport, original Process/
   stdin, unpredictable write nonce and exact held dispatch incarnation. Native
   wire default session and native init UUID are distinct fields. Join subsequent
   actual init/assistant/terminal events to the same fresh transport. Missing or
   contradictory evidence remains UNKNOWN/FAIL, never provider acceptance or
   comprehension. Then freeze the complete source/SDK/policy footprint, qualify
   the actual local-provider pipeline once, register the new exact profile, and
   only afterward admit the bounded configured-account feasibility run.

Each unit gets meaningful original REDs, affected regression and scoped review;
app/native test ownership stays serial. Successful component proof is reused only
where exact code/semantics remain unaffected. Final-head full CI, all18 checks,
business/owner/source gates and D2/E/F/M3–M8 obligations remain open.

### Durable admission decision boundary

The next root storage unit is NativeImageDecisionStore(ImprovementStore), using
the existing improvement_events and encrypted RevisionBlobs. Its synchronous
persist(principal, joined, *, scope_hash, current) takes only a closed joined
host observation and an explicit trusted synchronous authority callback. The
callback receives the actual transaction connection and a defensive observation;
it must recheck the caller's current configuration/source/lease/generation and
return exactly allow or deny. Check before replay/write and again after fallible
blob IO. A callback error never releases allow. An image mismatch always denies.

The deterministic event key binds brain, scope, launch and invocation purpose;
the request hash binds scope and exact joined hash. Store only decision, hashes
and encrypted chunk references in event result_json. Replay validates encrypted
bytes and repeats current authority; a previous allow is never current authority.
Cancellation is settled by the existing host-owned transition wrapper and cannot
send a late allow. This store does not authenticate peer/native provenance or
replace the actual host join, selected-account guard, or accounting ACK.

### Worker integration audit constraints

Read-only audit of the actual callers confirms startup2 must be decoded from the
original initial bytes, then adopted before broader imports. Preflight must have
registration/current source/SDK/managed-policy admission BEFORE any guarded CLI
launch; verify_observed after preflight is necessary but insufficient alone.
The explicit native client factory uses a copied options.env for its transport,
with the original options retained for SDK callbacks. Its query policy comes from
the validated manifest, exact prompt/cwd/model/effort and fixture_only/pinned_skill
inventory. No resume or legacy hidden-process shim on this path.

Engine environment correction is committed19e1890b. SDK initialize uses its own
default availability bound; no new ambient timeout variable is installed for the
owned client. Token expiry gate does not mutate the environment. Common engine
disconnect suppresses exceptions, so native_runtime.aclose MUST succeed before
worker_complete; session close is still mandatory in outer finally.

The old dummy-provider harness patches its opener/shim and bypasses run_request;
it cannot qualify the new production boundary. Current closed startup/SDK env
also refuses dummy endpoint/API/config/proxy fields, and live auth verification
correctly requires registration and subscription auth. Before final freeze, add
one explicit closed qualification-only admission/policy: frozen candidate/source/
runtime, synthetic workspace, numeric loopback endpoint, literal dummy key,
empty auth home/config and strict existing proxy guards. Keep live/default auth
policy unchanged; qualification scope can never yield a live capability or
production eligibility. Exercise the SAME fixed entrypoints/run_request/profile/
factory/capture/guardian/durable consumers under that scope, with actual dummy
auth output retained. No opener/source/env patching after freeze. This branch is
not implemented or qualified yet; do not register intermediate component bytes.
