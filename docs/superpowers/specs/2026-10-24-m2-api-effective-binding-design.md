# E2/D2 API effective-skill host binding

> Authoring prerequisite correction: the
> [same-Session source-owner supplement](2026-10-24-m2-skill-authoring-source-design.md)
> supplies a newly required concrete E1 source composition. Earlier references
> to an already specified owner-DM authoring collector are superseded by its
> fixed `qualification-skill-authoring/v1` file profile and real source/ACL/grant
> observations. API DM consumer authority remains independently authenticated.
> This prerequisite is not implemented. The fresh E2 same-builder follow-up
> returned "nothing important left" after reading the source-owner supplement.
> Earlier E1 verdicts did not establish that previously missing concrete owner.
> The new verdict is design readiness only; runtime/source/platform gates stay open.

> Root scope and acceptance preface — 2026-10-24
>
> Design only; implementation, independent builder check, runtime evidence and
> final qualification remain open. This E2 supplement depends on the E1
> activation, technical outcome and in-process turn designs. It does not certify
> those designs as implemented. The bootstrap supplement resolves the concrete
> fresh-process/root/auth/Session/route contracts and takes precedence over any
> unresolved bootstrap wording in the first API binding report.
>
> The permitted technical API profile proves authenticated loopback protocol
> delivery through the real existing route/engine/skill consumer. It is labeled
> `qualification_api_protocol_delivery`, with direct target/dependency reads
> unqualified and `d2_complete=False` in its coverage projection. These are
> evidence labels, never caller-controlled authority. It proves neither model
> comprehension nor real provider/account/business readiness.
>
> Full D2 additionally requires concrete generic target/dependency readers to
> consume the same live effective scope or refuse those reads. Product effective
> profiles remain unavailable until that separate authenticated coverage gate
> passes, even if business acceptance later exists. Native effective delivery
> and its Windows path/permission containment remain independent required gates;
> a partial API profile cannot close full D2 or the M2 Goal.
>
> Scope remains M2 engineering and integrated Claude Opus 5.5 handoff under
> Goal section 18. Business/live validation stays PENDING; no live pilot,
> deployment, restart, account/model inference or M3–M8 work is authorized here.
> Reconcile actual reviewed Q1/Q2 interfaces before producing an implementation
> plan. No parallel implementation is authorized by these design documents.

Related specifications:

- [Activation core](2026-10-24-m2-effective-skill-activation-design.md)
- [Technical outcome](2026-10-24-m2-technical-skill-outcome-design.md)
- [In-process technical turn](2026-10-24-m2-technical-skill-turn-design.md)
- [API host binding](2026-10-24-m2-api-effective-binding-design.md)
- [API fresh-process bootstrap](2026-10-24-m2-api-effective-bootstrap-design.md)

Design only, 2026-10-24. Immutable source basis:
`687b05718ec2970b6a59ef68d20dcad8ef777547`. Source reads used `git show`,
`git grep`, and `git ls-tree` at that commit. No working product source was read,
no app/module/test/native/CLI/API/network/account/config probe ran, and no Git
state changed. Only this report is written. Proposed names below are contracts,
not existing implementation. Reconcile Q1/Q2's eventual retained-owner interfaces
before building. E1 transaction/outcome/common-reader design remains unchanged.

## Decision

Add one private, retained **API consumer binding** to the existing Dashboard
turn. Its issuer joins actual Dashboard admission, concrete chat/session/message
storage, the session-pinned registered agent, selected route/configuration, and
the existing engine's actual HTTP attempts and MCP hub. Pass that binding into
`TaskSkillTurn.start`, the same `TaskSkillScope`, and the existing API engine.
Do not treat the present `provider_kind/tool_provider/hub_enabled/api_key`
arguments as authority for an effective candidate.

Use the existing `openai-compat` adapter and `_cc_tool_loop` against an owned,
authenticated loopback **protocol fixture** for positive disposable integration.
The endpoint returns deterministic tool-call protocol messages, not inference.
An ephemeral credential is actually checked at that endpoint; a real disposable
Dashboard session is actually checked by the normal handler. This is an honest
API consumer test, not an invented provider/key/owner predicate. Nothing changes
the user's configured provider/model, the QualificationSession native pin, or
the authoring HostContext. Product apply still requires genuine business and
independence acceptance, unavailable in Goal18.

Rejected alternatives: feeding E1's fixed in-process descriptor into
`TaskSkillTurn.start`; passing a dummy key and `la_chu=True`; interpreting the
native pin as API authority; weakening `HostContextStore`'s native check; mocking
the engine or `scope.read` and calling it API integration; creating a second
executor/ledger; exposing a simulation endpoint or public qualification flag.

## Verified joins and important limits

All line references refer to the immutable commit above.

| Source | Existing fact / consequence |
|---|---|
| `main.py:15802` `websocket_endpoint` | Checks `cfgmod.valid_session(cookie)` only when `gate_active()`, then admits the socket. A connected socket alone is not retained, revocable owner authority; gate-off is not authenticated owner evidence. |
| `config.py:1413–1437` | `new_session`, `valid_session`, `drop_session`, `clear_sessions` provide concrete opaque session membership/expiry. Retain the real admitted token privately; never persist its value/hash as public provenance. |
| `main.py:17828–17950` | Stored session brain overrides an inconsistent UI brain; provider is resolved from settings and stored session; `append_message` returns the actual user message id; `ObserveRuntime.start_turn` creates the actual runtime task/step. |
| `main.py:2089` `_resonance_turn_agent` | Resolves `agent:<slug>` from stored session, checks brain and agent file, then `GoalStore.session_agent` fixes exact agent key/config version against session creation identity. Slug recreation does not inherit old-session authority. The returned provider hint is not the later selected API route. |
| `main.py:2446,2478,2542,15915` | `_provider_key`, `_chat_provider`, `_chat_provider_for_session` and `_do_turn` determine the actual route, including pinned-model fallback, current key, and reasoning. Agent DM chat's actual route comes from this session selection; `_agent_sysprompt`'s model return is not the chat route. |
| `main.py:17106–17200` | `run_turn` owns TC token, CR trace, task-skill lifetime, and close/reset order. A stored session is not a runtime task: each turn has fresh task/step identities. |
| `main.py:16630–16780` | Actual normal API branch starts TaskSkillTurn before its prompt preparation; sends via `_api_stream_mcp`; collects usage/route events. Native and fast execute/reject branches do not enter it. |
| `main.py:16656`, `10289`, `10196` | Agent DMs force `AdaptiveContextPlan('legacy','persona_agent_chat')`, use `_agent_chat_prompt`, and list configured skill names. They do not presently select a `LazySkillSource` body through AdaptiveContext. Do not claim that prompt-injection coverage for this surface. |
| `main.py:2978–3080` | `_api_stream_mcp` obtains the real hub tools/route, coding context, scope-private inventory, and then a provider generator. Discovery exceptions currently may fall through to empty tools/plain API; this cannot swallow effective-binding invalidity. |
| `engine.py:629,974,1892–2128` | API engine is functions/generators, not a persistent provider object. `openai_compat_url()` reads settings again; `_cc_tool_loop` constructs an `httpx.AsyncClient`, POSTs actual JSON, calls `mcp_client.call_route`, clips tool results, and resends them. Bind concrete selected functions plus actual request/client identities, not a fictional Engine instance. |
| `engine.py:35–89` | `TEAM_REQUEST_OBSERVER`, `_request_usage`, `_observed_post`, `_observed_stream` already expose request ids and nullable telemetry. Observer errors are swallowed intentionally; that observer must not enforce permission. |
| `mcp_hub.py:833,1404,1515`; `mcp_client.py:1141` | Real `javis_use_skill` uses scope.read, slices text to 60,000 chars, then checks owner after awaited work. Real routing has guards and may return ERROR strings. Scope-private caches already exist and check source/epoch on hits. |
| `lazy_skill_runtime.py:100`; `skill_router.py` | Existing private scope selection and no-fallback behavior are reused. Lazy selection removes frontmatter, wraps the body, and enforces a body limit; a read hash alone is not the final outbound prompt hash. |
| `improvement_task_skill_turn.py:15–69`; `improvement_task_skill_scope.py:142,200,304` | Retained off-loop capture and event-loop binding; exact types, runtime object/DB identity, running rows/version, source checks, and copied-context revocation. Extend these concrete owners; do not replace them. |
| `improvement_trial_host.py:117–122`; `improvement_trial_sql_context.py:369` | Authoring HostContext deliberately requires anthropic-cli/claude-sdk; current SQL capture requires channel web. Neither is an existing owner-DM API issuer. Preserve both. |
| `improvement_qualification_session.py:79–145` | Session owns fresh disposable brain/store/blob encryption/native lineage and a retained-owner set. It does not own an admitted Dashboard session or an API route merely by existing. |
| `tests/python/test_improvement_task_skill_turn.py:135` | Existing main lifecycle test AST-extracts run_turn and replaces `_do_turn`, including an inert key. Good lifecycle coverage, not actual admission/prompt/tool/API integration. |
| `tests/python/test_openai_compat_connect.py` | Existing endpoint-key binding regression uses a mocked HTTP client. Keep it; the proposed loopback test additionally exercises real HTTP transport. |

## Exact issuer and object relationships

Use a private concrete host owner (working name `DashboardApiConsumerOwner`) with
an unexported constructor token, owned by the existing application/chat runtime.
There is no public constructor accepting a settings map, arbitrary `is_current`
callback, owner boolean, provider string, endpoint, principal, or root. Ordinary
host creation takes its existing concrete settings/session/GoalStore/runtime
owners. A private qualification bootstrap takes the **exact live Session** and
builds those same concrete owners in that Session's disposable application
state. It cannot accept replacement callbacks/objects or a production root.
Both use the same admission/selection/request-binding implementation. The domain
is fixed by the concrete owner, never selected by a wire field.

This is dependency/lifetime factoring at the existing host joins, not an agent
executor. There is no alternative run loop. Current main/config globals mean the
disposable bootstrap is real implementation work: it must run in an isolated
test process with all app state owned by the Session before constructing the
app's concrete services. Do not swap an active application's globals. If that
bootstrap cannot be made concrete, the end-to-end gate stays open; an extracted
function plus stub environment is not an acceptable substitute.

The issuer proceeds in two phases:

1. **Admitted message**: `/ws` records private evidence of the successful real
   owner-session validation and connection admission. On a message, revalidate
   that auth session and read the actual stored chat row and actual newly
   appended user row. Retain concrete store/path identity, session id and
   creation identity, message id/role/session ownership, canonical brain, and
   the job owner registered with `_CHAT_RUNTIME`. Bind after registration (the
   new asyncio task may wait on a private readiness event until registration
   finishes). Require registered `agent:<slug>` DM, active same key/version and
   unchanged file identity; read `authority_seq` from the real GoalStore.
   The existing TC fields are derived from this admission, not accepted as its
   proof. Gate-off or a synthetic/automatic continuation without a retained
   admitted owner message is not eligible for effective activation. Ordinary
   baseline behavior on those surfaces remains existing behavior.
2. **Selected API consumer**: inside `_do_turn`, after the real final session
   route/reasoning/language and permission mode are known, retain the selected
   provider definition/function identities, actual settings ownership, resolved
   endpoint, selected model/configuration, and credential reference. Mint one
   concrete turn binding only after these match admission/current rows. It is
   registered to the actual TaskSkillTurn and actual asyncio job, not reusable
   between calls. Mint before any scoped prompt/header/body read. Attach actual
   hub tools/route/coding context after discovery and before the first send.
   Retain actual AsyncClient/request identity when the engine constructs it.

The settings snapshot/hash covers only request-affecting configuration:
provider/adapter, normalized exact endpoint, selected model, reasoning and fast
settings, hub/tool mode/lazy mode, coding/workspace authority, and relevant
language/routing policy. Preserve request-level negotiated changes (e.g. named
tool choice fallback) as explicit allowed profile transitions with distinct
request hashes. An unknown transition refuses effective delivery. Do not bind
unrelated settings such as display theme, and do not add a new model choice.
Credential bytes stay private and are compared against the concrete config
owner under its lock; rotation/removal invalidates this binding. Persist an
opaque credential-generation identity if required, not the secret or a plain
secret hash. `openai_compat_url()` must use this retained resolved route on a
bound turn, rather than re-reading a possibly different destination while
retaining the earlier key. Unbound callers keep existing behavior.

Revalidation uses these same concrete owners and source readers. A later
configuration re-read which selects a different route invalidates the binding;
it must not silently rebind an already prepared effective prompt to that route.
The `_resonance_turn_agent` provider hint is checked only as source context,
never substituted for this actual selected route.

`TaskSkillTurn.start` retains its feature-off/native/missing-key/tools/hub short
circuits before core import/scan. Baseline snapshot operation can keep its
existing compatibility signature. **Effective resolution requires the exact
registered binding**, including when ordinary-looking TC values pass existing
checks. Anchored stores remain rejected by the public ordinary scope factory.
The qualification API owner reaches a private factory on the same exact
TaskSkillScope, with real Dashboard admission as an additional condition; it
does not reuse E1's non-Dashboard in-process factory. The shared pin/inventory/
read/CAS algorithm remains E1's algorithm.

## Selectors, source lineage, and acceptance

Production retains proposed `SkillSelectorV1`: brain/target; registered agent
key; exact `dm:<agent_key>`; language; dashboard channel; domain contract hash;
actual consumer engine configuration/profile hashes. Brain/target come from
the same asset store, agent/context from actual session pin, language from the
resolved host language decision used by consumers, engine hashes from the
binding above. An unresolved/auto language cannot pretend to be a concrete
language-specific slot. No wildcard or guessed agent-name selector.

The source snapshot does not expose an already implemented
`domain_contract_hash` issuer. Build this bounded projection with the host
binding: hash the closed DM contract version, registered key/config version,
protected agent definition/owner-rule source hashes, context policy, and actual
prompt/tool authority policy. Reuse source/grant validation; exclude mutable
ordinary transcript/usage counters from this stable contract. Changed protected
sources still invalidate live grants. This is a source-derived identity, not a
new business policy or acceptance issuer. A body/source hash cannot prove owner
acceptance. A product plan with missing or mismatched contract stays refused.

Qualification must have a **separate tagged API consumer selector**, e.g.
`QualificationApiSkillSelectorV1` with exact fields:

```
version=1, kind='qualification_api_skill_consumer', domain='qualification',
run_hash, brain_id, target_id, authoring_context_id,
agent_key, context_id, domain_contract_hash, language, channel='dashboard',
consumer_profile_id, consumer_profile_version, consumer_profile_hash,
consumer_config_hash
```

It is disjoint from both the product selector and E1's
`TechnicalSkillSelectorV1(kind=technical_skill_consumer)`. The registered
descriptor fixes consumer_profile_id to the loopback API protocol profile,
whose hash includes the reached adapter/tool-loop/request-fence/prompt/hub code
closure and protocol fixture contract. The consumer config describes the actual
disposable selected endpoint/model protocol identifier/tools/auth-generation,
not native authoring configuration. Endpoint's ephemeral port is allowed in
this run-scoped config; it does not become a production endpoint. The native
Session pin, release, source_engine_config_hash and source_engine_profile_hash
remain byte-for-byte authoring lineage, separately revalidated throughout.

Create the real disposable app configuration, admitted-capable agent/session
and owned endpoint descriptor **before freezing** the corresponding technical
outcome plan. Register the descriptor with the same Session owner so the plan
can bind this exact consumer configuration. E1's four structural byte checks
may authorize the owned disposable candidate for that exact API descriptor
through the existing technical producer/shared apply core. This does not
upgrade their coverage or change the producer's win/loss rules. An already
frozen in-process E1 plan/pointer cannot be edited or transplanted into this
slot: create a fresh bound technical plan/decision; use the same transaction
core. Do not fabricate `eligible` product comparisons. Any necessary closed
technical-parser extension must be explicit and reviewed, never a product
parser accepting technical records based on supplied labels.

Normal product factory requires its real accepted decision in addition to the
host binding and current grant. The qualification factory requires exact live
Session/registered descriptor/technical decision. Neither accepts the other's
records, even if content hashes match. Actual Dashboard authentication proves
ownership of the disposable chat; it does not supply business eligibility.

## Consumer and request fences

Pin the current activation generation/manifest before scoped prompt preparation.
Retain that immutable pin for this task/step and its API retries/tool rounds.
Revert/apply changes selection for a new task; it does not mutate a previously
retained pin. Source/owner/grant/policy/config revocation kills live use of the
old pin. There is no session-global mutable effective pointer cache.

The binding's private live check extends the current scope checks with admitted
auth/session/message/job/agent/config/descriptor authority. Recheck before and
after off-loop capture, after binding on the consuming task, on every metadata/
body/cache read, after discovery and tool awaits, and immediately before each
actual outbound request. Actual engine request sinks must call the concrete
binding directly, outside optional telemetry exception swallowing. Cover both
`_observed_post` and `_observed_stream` sinks used by supported API profiles;
pass actual payload/endpoint/headers/client rather than an opaque arbitrary
`send` callback to the enforcement join. Unbound behavior remains no-op.

Every retry, named-tool-choice fallback, autoshrink retry, and later tool round
gets a fresh request attempt identity and fence. Validate actual route and
payload after all provider transformations, not just initial `messages` in
`_api_stream_mcp`. Tool result clipping, frontmatter removal, lazy wrappers,
system caching annotations and autoshrink affect delivered bytes. Preserve
source-read receipt plus derived segment hash/length/transform/range and exact
final serialized request digest. A segment dropped by trimming has no delivery
receipt. Avoid substring inference: record an in-memory source segment identity
at the real router/lazy/hub producer and propagate that identity through the
existing composition/transformation sites. If lineage is lost, delivery is
unknown; never assert full-skill delivery from the unchanged source hash alone.

Agent-DM positive path: real prompt's skill declaration + actual hub inventory,
API response requesting `javis_use_skill` (or lazy hub search/run), actual guarded
call_route -> scope.read -> actual clipped tool message -> next HTTP request.
The receiver must assert the selected candidate bytes in that tool message and
their absence where baseline is expected. This establishes tool-result delivery,
not automatic lazy prompt injection. Exercise LazySkillSource through the common
E1 reader tests and, separately, the existing non-persona API adaptive branch
as a baseline compatibility control; do not change DM routing to manufacture
coverage. Metadata availability, body read, local tool result, request prepared,
request attempted, receiver-observed and model understanding are distinct facts.

The API currently has ordinary file-reading tools as well as `javis_use_skill`.
This vertical promises effective bytes through the named skill consumers only.
It does not intercept arbitrary file reads, hide canonical files, or prove a
model cannot independently inspect them. Product acceptance must not claim such
filesystem exclusion. No canonical overwrite, alias rewrite, registry refresh
with candidate content, or permission revival is permitted.

Do not let `except Exception` around hub discovery or call_route turn an invalid
effective owner into a plain mutable baseline read or a successful request with
stale bytes. Record the tool ERROR honestly, revoke the binding, and the request
fence prevents further sends. An intentionally unsupported surface/profile is
unavailable for effective selection before reading candidate content; baseline
controls keep existing behavior. Once candidate bytes enter a bound request,
failure is fail-closed for that turn, not a silent model/provider/tool fallback.

Compaction and background work need the same boundary: foreground history
compaction can make an additional API request; background `maybe_compact` may
inherit ContextVars. Preserve original request purpose/accounting, identify the
actual route used, and do not attribute a summary call to answer delivery. A
copied dead binding must refuse later effective reads/sends. Do not clear a
dead binding to recover fallback. Background work without effective bytes may
use its established independent owner; it cannot borrow this task's authority.

Revalidation has a defined linearization limit. At request start, current
authority is checked against locked/versioned local sources and the exact
request; no lock is held across network I/O. Revocation after a request is sent
cannot retract its bytes. Mark that attempt as in-flight/revoked, prohibit tool
use and further sends, and preserve any actual telemetry received. Do not claim
an impossible atomic remote-delivery/permission guarantee across awaits.

## Lifetime and immutable evidence

Binding registers with TaskSkillTurn/host (and Session retained-owner machinery
in qualification) before any await that can create a scope/client/request.
It owns request generators/clients and read/publication futures until they
settle. Stop or owner revocation immediately closes permission for new work,
then cancels/drains the existing generator/HTTP client and retains off-loop work
through repeated cancellation. Late scope creation is closed. Never reset a
ContextVar from another task; external close signals the owning job.

Within `run_turn` cleanup: revoke binding/scope first, settle capture/read/
publication/HTTP/generator cleanup, reset scope and request context tokens, then
reset TC/CR in their owning task. Runtime finish remains the original host's
responsibility; terminal status must reflect actual cancellation/error and
failed cleanup is not successful closure. Keep unresolved owners retained and
refuse Session cleanup until resources drain. Socket disconnect alone does not
kill the chat job (`_CHAT_RUNTIME` already owns it); auth expiry/drop/revocation
does kill further effective use. Shutdown cancels/drains retained host jobs.

Concurrent chats share no scope/cache/request binding. A binding also checks
the exact asyncio job, TC binding, CR trace, runtime DB object/path, current
task/step/status/version and store/root. A copied context with a live-looking
map or a different task cannot make a new consumer. Tool worker threads invoked
by the retained parent may read via their existing copied context, but cannot
mint/switch the owning turn. Resume/steer/follow-up starts a fresh task/step and
requires its own valid host admission contract; cold events never resurrect a
live binding. M2 does not infer support for autonomous continuations.

Append bounded immutable records to existing encrypted blobs/events; no new
request ledger/table. Join domain/run, consumer descriptor/config/profile,
selector/pin/generation, source read receipt, actual task/step/session/message,
request attempt/event id, transport adapter, payload digest, segment transforms,
and observed result/error/unknown telemetry. Use distinct version/operation for
qualification API receipts. Public views redact roots, credentials, private
prompts and tokens; raw receipts remain protected. Domain and coverage are
explicit: `qualification_api_protocol_delivery`, never production acceptance.

Retain `_request_usage` nullable per-attempt values and event ids alongside
existing `usage_store` and ContextRuntime aggregates. The existing engine's
optional observer is a telemetry join, not permission. Missing usage/cost stays
unknown even where legacy aggregate UI uses zeros. Do not sum duplicate update
events; reconcile by existing request event identity. Where an existing
CallLedger call/attempt/purpose owns the request, reference that actual row and
keep reservation/start/settlement semantics. Ordinary Dashboard reply currently
does not acquire an improvement CallLedger attempt at the cited caller: do not
invent `improve_probe` or debit a second call just to attach a skill receipt.
Loopback telemetry is explicitly fixture-reported and not provider billing;
zero external inference follows from owned endpoint confinement, not from
fabricated zero-token accounting. Popularity `skill_usage.bump` is not delivery.

## Disposable integration construction and bounds

The future integration test builds a real Session and private disposable app
host under it, with genuine temporary settings, Session's exact anchored
ImprovementStore/GoalStore, a real session DB, real agent registry/session pin,
and real ObserveRuntime. Use real app registration/session APIs or their
concrete storage owners; never inject SQL rows impersonating admission/runtime
or patch `valid_session`, `_resonance_turn_agent`, `start_turn`, `TaskSkillScope`,
hub handlers, `_api_stream_mcp`, engine generator, or httpx transport to GREEN.
Create a real disposable auth session with `config.new_session` (or ordinary
login), send its cookie through the actual `/ws` handler, and verify server-side
membership/expiry. Login password correctness is not the skill test's claim.

Create a temporary loopback server bound to an OS-assigned port. Its owned
socket/object identity, run nonce, exact route and source contract are registered
before plan freeze. Generate a random per-run bearer secret, put it only in the
disposable config, and make the fixture reject missing/wrong secrets. Configure
the existing openai-compat route in that disposable store and select it through
the ordinary session route. Its model field names the fixture's one registered
protocol script, explicitly not an installed/inferred product model. Never
alter native pin/model/profile or a live user setting. No caller-supplied
endpoint is accepted by the qualification bootstrap.

Fixture serves only its exact chat-completions route, returns a bounded script
of tool-call then final responses, captures actual raw request bodies, and
refuses redirects/unexpected destinations/extra calls. The real engine stays
unchanged in executor semantics. Production binding uses actual configured
credential/provider owners but asserts no account readiness from a nonempty
key. Test receiver authority proves only this disposable protocol service.

Constrain the qualification owner to literal loopback and its registered live
socket/port, disable proxy inheritance and redirects for this owned fixture
transport, reject URL userinfo/DNS/alternate destinations, and keep TLS/external
transport behavior unchanged outside qualification. No general-purpose local
simulation endpoint is added to the app. Other app startup/background services
must not run against real accounts: construct the app's existing services with
the owned disposable state and no external connector registrations. The test's
script only requests skill discovery/load; all actual hub guards remain active.

Proposed fixed resource bounds: at most two concurrent disposable turns, four
HTTP attempts per test turn (retry cases budgeted explicitly), 1 MiB request and
response capture, 30-second per-turn deadline, descriptor/receipt metadata at
most 16 KiB, and Session lifetime/remaining-resource limits always stricter.
Retain existing skill inventory/header/body and tool-result limits. Counts are
transport fixture limits, not extra native queries or a new billable budget.
Cancellation cleanup has a bounded diagnostic timeout but never drops a still
live owner merely to make the timeout pass. Missing teardown keeps gate failed.

## Cohesive implementation and RED/GREEN matrix

One bounded unit: private host/binding module plus joins in `main.py` admission/
run_turn/API branch, `improvement_task_skill_turn.py` and scope private factory,
actual engine request sinks/config selection, and minimal provenance at the
existing hub/lazy/prompt transformation sites. Reuse E1 resolver/pin/materialize/
decision/events without redesign. Tests live beside current task-skill tests,
with a new full host+loopback integration fixture and per-sink contract tests.
Only the necessary existing improvement service/UI reads expose selector,
actual delivery stage, coverage and unknown usage; they consume stored receipts
and never mint bindings. Apply/revert use actual host-resolved scope identifiers,
stale revision/CAS checks and the unchanged production gate. No UI rewrite here.

| Meaningful RED | Required GREEN evidence |
|---|---|
| Existing scalar start/forged TC values can appear sufficient | Exact registered host binding required for effective resolution; fabricated dict/token/trace/key/owner/descriptor and copied object denied before candidate scan/send. |
| Handshake-only auth, stale stored row, recycled slug | Real `/ws` positive admission; gate-off/invalid/expired/dropped cookie, archived/wrong brain chat, wrong user-message row, missing/replaced agent/session pin/config version denied. Auth revocation during await prevents next request. |
| Endpoint is read later than key | Pause after route selection; rotate key or endpoint/settings/session pin, then resume: no request goes to either unauthorized destination, no stale secret leaks. Valid unchanged route reaches owned receiver. |
| Technical native pin mistaken for API config | Preserve exact Session pin/release/source-context hashes across API turn. Foreign Session, mutated pin, E1 selector/plan transplant, product selector on anchored store all fail. Fresh API-bound technical outcome passes shared apply core. |
| Read receipt mislabeled as API delivery | Real handler -> TaskSkillTurn.start -> actual DM prompt -> real hub -> real engine -> real loopback POST sequence. Receiver observes candidate tool-result bytes; after revert a fresh admitted turn observes baseline. Distinct task/step/pin/request ids checked. Canonical files unchanged. |
| Plain/eager path only tested | Actual eager javis_use_skill and force-lazy hub search/run both exercise existing guarded route. Body slicing and engine clipping receipts match receiver. DM LazySkillSource injection remains explicitly uncovered; existing common-reader tests verify it separately. |
| Hub failure silently falls through | Remove/revoke scope during discovery/body/bump/tool return; copied contexts/caches yield unavailable and no later POST carries candidate/canonical fallback. Source permission/enable/frontmatter/grant/policy drift fails real fences. |
| First request checked but retry/second round unchecked | Pause fixture after first POST; revoke before tool read or second POST. Also named-choice retry, transport retry, autoshrink and compaction attempted routes each have separate fenced attempt receipts. Already sent attempt stays historical. |
| Usage inferred from final aggregate | Complete, partial, absent, malformed usage and network interruption preserve actual per-attempt unknowns; event-id update dedup; no invented improvement ledger rows/cost/model outcome. |
| Cancellation leaks capture/client or falsely cleans Session | Repeated Stop during capture/discovery/POST/tool read/event write; all actual futures/clients settle, late scope closes, copied contexts dead; forced close failure retains owner and cleanup refusal. |
| Cross-chat cache/selector bleed | Two real admitted concurrent sessions/agents with distinct config/selectors; receiver and receipts show only each turn's own version. New message/fresh turn resolves latest compatible generation. |
| Feature opt-in changes legacy routing | Default off/native/oauth/unknown provider, true key-requiring provider with empty key, tools/hub disabled short-circuit without core import/M0/migration/skill scan from this feature; ordinary valid nonqualification snapshot and existing compatible endpoint/no-key semantics retain behavior. |
| One adapter claim widened to all API engines | `_cc_tool_loop`/openai-compat full integration plus sink tests for every profile marked supported. Anthropic/streaming or any uncovered adapter remains unsupported for effective activation until its real serialization/delivery fence and test pass; ordinary baseline calls remain existing behavior. |
| Qualification evidence leaks to product UI/apply | Normal product factory refuses technical decision and unverified business result; cold UI only displays technical coverage with activation unavailable. No live config/policy/model changes. |

Default-off no-scan applies to incremental feature work; the existing ordinary
chat path itself already performs unrelated prompt/memory work. Do not claim
this feature removes those old operations.

## Gates and real blockers

1. None of this host binding or loopback integration exists at the source basis.
   Current tests prove narrower scope/lifecycle behavior. E2/D2 remains OPEN
   until the actual route/engine tests above run after the serial Q1/Q2 gates.
2. The concrete disposable app bootstrap and retained Dashboard auth/job/config
   owner are missing. Main uses globals and handshake-only auth; this cannot be
   solved by a test callback claiming ownership. Land the narrow concrete joins
   or report the exact bootstrap limitation and keep integration OPEN.
3. Product business/independence acceptance is genuinely unavailable. A real
   owner-DM API consumer binding proves admission/delivery, not accepted candidate
   quality. Normal production apply remains fail-closed. Do not broaden native
   HostContext/SQL capture just to forge an API-eligible authoring fixture.
4. E1's fixed in-process selector/outcome cannot directly address the API slot.
   A newly frozen, Session-registered API descriptor and explicit technical
   selector binding are prerequisites; parser changes require review alongside
   landed Q1/Q2 interfaces. The native Session pin remains unchanged.
5. Actual agent-DM LazySkillSource prompt injection does not occur today. This
   vertical can close real DM tool-delivery coverage, not that absent route, not
   arbitrary-file exclusion, model comprehension, provider-account readiness,
   native delivery, business outcome, or all-surface/resume coverage. E3 native
   gate remains independently open. Do not report full D2 from this test alone.

The engineering choice is implementable without real inference: authenticated
disposable host -> same TaskSkillTurn/scope/shared core -> same API tool loop ->
owned protocol receiver -> honest receipts/revoke/revert. Any missing concrete
join remains a named gate, never supplied by a permissive flag or eligibility
fixture.
