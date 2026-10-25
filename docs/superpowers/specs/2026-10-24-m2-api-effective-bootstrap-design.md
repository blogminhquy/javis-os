# API bootstrap and technical consumer registration resolution

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

Design supplement, immutable source `687b05718ec2970b6a59ef68d20dcad8ef777547`.
No implementation, imports, execution, probes, network, source/Git mutations or
helpers. Only this report is written. It resolves the two architecture
prerequisites in `api-effective-binding-design.md`; names are proposed contracts.
E1 evaluator, native pin/profile, product acceptance and common activation core
retain their previous meanings. Actual integration remains an implementation
and validation gate, not a result of this report.

## 1. One process, one root, one real application

Choose a **one-shot disposable process bootstrap**, not a multi-instance rewrite
of main and not post-import monkeypatching. The test launches a fresh Python
process; the entire genuine Session, authoring work, main application, protocol
fixture and ASGI test client live in that process. No live Session object is
serialized into a child or reconstructed from its archive. The launcher is test
process management, not a second task/agent/API executor.

The source requires reserving the root before importing Session itself:

| Actual source | Consequence |
|---|---|
| `improvement_qualification_session.py:17–25` | Imports ImprovementStore and GoalStore before `Session.open`; GoalStore imports config. Setting the state path after Session.open is too late. |
| `config.py:17–27,581,1381–1437` | STATE_DIR, settings path and auth-session storage are module-owned; settings has a real RLock/cache. |
| `sessions.py:45–47,428,1934` | DB path is captured at import, singleton is constructed once by get_store. |
| `main.py:45,204–234` | Repository `.env` loads before the main body; actual ChatRuntime/runtime/registry/compiler services are initialized at import. |
| `main.py:1093–1111,6147–6169` | Brain/vault/source paths have environment overrides; `_brain_root` falls back on invalid paths, so qualification must pass/check the exact existing Session brain. |
| `resonance_store.py:458`; `main.py:2073,26648` | GoalStore defaults to state/resonance.sqlite3, but main otherwise creates a fresh ImprovementStore and state/improvement blob store. Same pathname is insufficient: qualification needs exact Session assets/store/blobs identity. |
| `context_runtime.py:222,2205` | get_runtime creates the real ObserveRuntime once, using config.STATE_DIR and the real config.read_settings function. No fake settings reader is necessary. |
| `mcp_store.py:28–30,61` | Missing disposable MCP registry falls back to repository `server/mcp_servers.json`. This must not borrow installed connections. |
| `secrets_store.py:15–36`; `usage_store.py:30–33` | App encryption and usage files are derived from config.STATE_DIR. App encryption is distinct from Session's `fixture-encryption.key`; both are fresh, owned and retained. |
| `plugins_host.py:48–54,331–341` | User plugins live in state/brain, but bundled plugins come from source and may be enabled by manifest. Disposable disabled overrides must be explicit before discovery. |
| `main.py:4334,4384,24295,24367` | Full startup includes native updates, credential watchdog and MCP warming. API route integration must not accidentally run that unrelated lifecycle. |

### Exact new bootstrap boundary

Add a small **stdlib-only** module, proposed
`server/improvement_qualification_bootstrap.py`. It must not import config,
Session, main, engine, crypto, or any state-bearing application module at module
scope. It owns one private constructor token and one process-local reservation.

`_reserve_api_process()` has no arguments. It refuses if a reservation already
exists or any application module (including config, sessions, resonance_store,
context_runtime or main) has already been loaded. It creates its own new
TemporaryDirectory and private child directories; it accepts no path, env map,
callback, provider, key or existing directory from a caller. The returned exact
private `ApiProcessReservation` owns the TemporaryDirectory, canonical root,
directory identities, pid, thread identity and single-use state. Merely setting
an environment variable never creates this object or grants qualification.

The launcher starts with a closed minimal process environment and known source
import path. Reservation sets these existing application paths before the first
application import, all derived from its own root:

```
JAVIS_STATE_DIR       = root/state
JAVIS_SESSIONS_DB     = root/state/conversations.db
CLAUDE_CWD           = root/brain
BRAIN_PATH           = root/legacy-brain
BRAINS_DIR           = root/brains
OBSIDIAN_VAULT_PATH   = root/vault
SOURCES_PATH         = root/sources
```

Home/config/cache/temp directories and any platform-required profile path in
the child environment are fresh descendants too; no host auth/proxy/provider
environment is copied. Preserve only documented OS/runtime necessities and
explicit reviewed native executable location needed for existing static pin
observation. Construct this environment before Session's native checks and do
not change it afterwards. An actual native identity/profile check can still
refuse this environment; it is not bypassed. This bootstrap is not itself
installed-native qualification.

`QualificationSession._open_reserved_api_process(reservation, **existing_open_args)`
is a private entry, with exactly the existing pin/endpoint/fingerprint/lifetime/
maximum_queries arguments plus the concrete reservation. Factor the **existing**
open implementation so it can consume this exact unconsumed reservation instead
of allocating another TemporaryDirectory. Public `open` still allocates its own
root as before; it gains no `root`, `allow_api` or adoption option. All existing
reviewed candidate, runtime identity, release, pin, anchor, encryption, store,
principal and source checks run unchanged. Existing `_temporary` and `_root`
become the reserved owned TemporaryDirectory and its canonical path, never a
copy or nested substitute. Session still creates exactly root/brain,
root/state/resonance.sqlite3, root/assets and its fixture key. Root reservation
must leave those not-yet-created Session artifacts absent.

On success, ownership of directory cleanup transfers once to Session; reservation
retains a non-owning identity link and changes to `session_bound`. On failure it
cleans only its own verified new directory after any opened owners settle.
Session's `_assert_native_current` continues checking its original native
authority tuple. A process cannot bind a second Session, reopen the reservation,
or consume a different Session's assets. The bootstrap registry points at the
exact Session object and is neither persisted nor reconstructible from events.

The native endpoint argument remains the existing Session lineage field. The
API fixture socket is a different owner, registered below; do not mutate or
reinterpret Session.scope()['endpoint'] as the API destination.

### Concrete initialization order

1. Reserve root in the fresh process, establish the closed child environment,
   then import/open the real Session through the private reservation entry.
   This solves config import ordering without resetting modules or globals.
2. Import real config/secrets_store, whose module paths already point into
   root/state. Create disposable settings through their real write/encryption
   functions under `_SETTINGS_LOCK`. Generate local auth credentials with
   `config.hash_password`, persist auth fields normally, and require real
   `gate_active()` to be true. App secrets_store creates its own state/.secret_key;
   it must successfully encrypt, never use plain fallback. No live settings,
   `.sessions.json`, keys, native account files or connector config are copied.
3. Open the owned API loopback socket/protocol service and generate its checked
   per-run bearer credential. Persist its actual `openai_compat_base/key` before
   any authoring context/consumer descriptor freezes. The socket object and
   secret remain private owners; only an opaque credential incarnation is stored
   as provenance. Initialize `state/mcp_servers.json` as the real empty v2
   registry. Seed `state/plugins.json` with disabled entries for the pinned
   bundled manifest inventory; user plugin directories are empty and existing
   user-plugin enable env is off. This is ordinary disposable configuration,
   not patched discovery. Manifest inventory/hash becomes consumer profile data.
4. **Keep the native default selection unchanged.** The disposable settings'
   `model.main`, `claude_model`, `claude_auth`, `reasoning`, `fast` are the genuine
   native authoring selection, fixed before context capture. Do not change
   main.provider to openai-compat. `improvement_trial_selection._selection`
   (`:320–354`) hashes exactly the five native semantic fields; `create_pin`
   (`:357`) still sees the native default. Later the concrete chat row is pinned
   to API through SessionStore.set_pinned_model. `_chat_provider_for_session`
   chooses that real row's API override. Native authoring and API consumer thus
   coexist without switching models/profiles or freezing a false native config.
5. Arm the reservation's **one-time main import attachment** with the exact
   live Session, then import the ordinary source `main` once. Proposed bootstrap
   functions have fixed slots, not arbitrary name-to-service callbacks:
   `_before_main_import()` checks the armed object and tells the dotenv boundary
   whether this owned process must skip repository `.env`; ordinary main retains
   existing load_dotenv behavior. The check must precede that load, ideally the
   first main import statement. It does not accept a request/env flag.
6. Main constructs its normal `ChatRuntime()` and uses actual
   `context_runtime.get_runtime()`. `sessions.get_store()` constructs the real
   SessionStore at the initial configured path. A private `_attach_main(main)`
   finishes only after module initialization and validates exact source module
   identities, module functions, store paths/locks/connections, runtime and app
   identities. The host owner retains those exact objects; it is registered as
   a child of Session before any asynchronous work. There is no later assignment
   of a substitute ChatRuntime/session/runtime singleton.
7. Two existing factory joins must honor the armed owner **from first use**:
   `main._resonance_store()` returns Session.assets.store and caches that exact
   object if its lazy slot is still empty; `_improvement_write_store()` returns
   Session.assets itself, preserving root/assets codec and qualification_anchor.
   `_improvement_read_store()` uses the corresponding cold read over those same
   assets rather than state/improvement. These functions have fixed production
   branches and a concrete private registered-host branch, no injectable factory.
   If any factory/singleton was already populated differently, abort bootstrap;
   do not swap it. Equality of file paths does not repair object inequality.
8. Create the real fixture agent file in Session.brain, register with
   `GoalStore.agent_register(Session.principal, slug)`, create the actual
   `SessionStore.create_session(brain=absolute_session_brain, channel='agent:'+slug)`
   row, set its pinned API route via `set_pinned_model`, and call the real
   `session_agent` pinning operation. No fabricated SQL rows or TC owner booleans.
   The API host later independently resolves the same rows via main's actual
   `_resonance_turn_agent`. Use the absolute brain everywhere: the unrelated
   default `root/brains/Brain Default` must never become this Session's brain.
9. Create a real auth-session token with config.new_session (or ordinary login),
   then drive **main.app's actual ASGI WebSocket route** with its cookie. The ASGI
   client sends no lifespan startup event. No local public server endpoint or
   copied/extracted run_turn is needed. Admission/receive loop, message append,
   `_CHAT_RUNTIME.register_job`, actual `_do_turn`, TaskSkillTurn, hub and engine
   remain the ordinary code. The external protocol fixture alone listens on a
   loopback socket. Its transport is real HTTP; app WebSocket admission is real
   ASGI routing with normal middleware/auth, not a substituted handler.

The test intentionally covers the initialized app's request/turn lifecycle,
not global startup/update/watchdog behavior. Not sending an ASGI lifespan event
is a test transport choice, not a production simulation flag or deletion of
app startup hooks. The host owner directly drains **the actual resources this
test constructed** rather than running unrelated full startup/shutdown hooks.
If a route needs a lazily created ordinary service, its existing factory runs
under these disposable paths and its actual owner is retained for close.

Two small required source fixes are part of this unit. First, the reserved
process's mcp_store._load must refuse missing/replaced owned STORE instead of
using `_LEGACY_STORE`; the real empty registry normally takes the usual path.
Second, `_do_turn` currently constructs a Claude engine even before choosing an
API branch (`main.py:15960`). Defer that unused constructor until an existing
native branch actually needs it. The API integration must not inspect native
account state incidentally. This preserves actual native branch behavior and
does not touch the native skill/profile design.

The host's actual configuration owner is the exact config module, SETTINGS_PATH,
STATE_DIR, `_SETTINGS_LOCK`, and initialized encryption owner, not a dict or
user callback. Its auth witness comes from real SESSIONS token membership and
issue timestamp. Add a private retained-session witness plus lock shared by
new_session/valid_session/drop_session/clear_sessions so concurrent revocation
can be checked consistently; no `is_owner=True` input. Its job witness is the
actual ChatJob returned after register_job, exact Task and tag/task/step ids.
Register-job readiness is published before TaskSkillTurn can capture; mismatch
or replacement refuses. Socket close is not job revoke; auth drop is.

Close order: revoke host admission/consumer registration; cancel and await exact
ChatRuntime jobs, their API clients/generators and retained skill operations;
remove/drain actual WebSocket clients; close owned protocol listener; close real
SessionStore and ObserveRuntime and any actually instantiated service; detach
main ownership; only then allow Session cleanup. Failure retains the Session
child owner and diagnostics. No reset/import reuse for another test: process
exits after close. Teardown does not delete source or another process's state.

### Authoring owner is not rebuilt from main

`improvement_trial_service.dashboard_host` (`:76–164`) is a production source
factory. It insists on `state/improvement` blobs, initialized workflow sources,
and its actual Dashboard collector; the collector's SQL profile accepts web,
not agent DM. Session owns `root/assets`. Do not widen that factory or force the
Session into its shape. The already specified E1 concrete same-Session
SkillCandidates/HostContext owner supplies authoring target/context/grant and
native source lineage. The API host **consumes that existing live authoring
owner**, never invents it from its chat admission. Context's authoring surface
and the new API consumer's DM session are distinct references. Equality is
required for Session/store/principal/target, not for native source provider and
API consumer route. This supplement does not claim product prompt parity or
change E1 authoring capture coverage.

## 2. Exact descriptor and technical version extension

Keep E1's in-process selector, plan/outcome and receipts version 1 unchanged.
Add one explicit technical API plan/outcome **version 2**, routed only by the
Session-owned API producer. There is no public union parser accepting a caller's
`kind`. The structural checker profile remains `skill-byte-transition` v1 and
coverage `authenticated_skill_bytes_only`; only the consumer binding is new.

### Descriptor issuance

Proposed fixed entry:

```
host.register_skill_consumer(authoring, *, context_id, target_id, session_id,
                             event_key) -> QualificationApiConsumer
```

`host` must be the exact Session-registered DashboardApiConsumerOwner attached
above, `authoring` the exact same-Session SkillCandidates owner, and identifiers
must resolve to their real current records. No selector/settings/provider/model/
key/profile/endpoint/outcome input is accepted. The session id identifies one
of this host's actual stored/pinned agent DMs. The owner must already hold a real
authenticated WebSocket admission for that session, but no user message or
runtime task exists yet. Registering the descriptor makes no model request and
grants no activation permission. A subsequent real message establishes the
per-turn/message/runtime/job witness; a descriptor cannot manufacture it.

Here the pre-message admission is the actual authenticated connection witness
minted at the existing handshake; `/ws` does not already supply a session-bound
handshake. Registration associates that witness with the independently read
owned session row inside the concrete host, since this Dashboard owner owns its
chats. It does not invent a receive/message event or require a new wire action.
Only the later actual received message can mint a per-turn admission.

Registration independently runs ordinary route selection against current
config and the real session row, derives reasoning/language/tool policy, checks
the actual endpoint listener/credential ownership, and reads the registered
agent pin/version and protected source/domain hashes. It compares the exact
objects and source modules after all slow I/O. It persists a canonical encrypted
`qualification_api_consumer_registered` event and blob; only after durable
append does it register the exact immutable live object to Session/host.

Closed `QualificationApiConsumerRecordV1` has exactly:

```
version=1, kind='qualification_api_consumer', domain='qualification',
run_hash, descriptor_id, host_incarnation, brain_id,
authoring_context_id, target_id, session_id, session_created_at,
agent_key, agent_config_version, context_id, domain_contract_hash,
language, channel='dashboard', provider='openai-compat',
endpoint_origin, endpoint_path='/v1/chat/completions', method='POST',
protocol_id, protocol_source_hash, credential_incarnation,
consumer_profile_id='dashboard-openai-compat-loopback',
consumer_profile_version=1, consumer_profile_hash,
consumer_config_hash, source_engine_config_hash, source_engine_profile_hash,
source_authority_hash, limits
```

`context_id` here is `dm:<agent_key>`; authoring_context_id names the native
authoring context separately. `protocol_id` is the one registered deterministic
response script identifier sent as the actual fixture request's model field,
not a new production model. Origin is literal registered 127.0.0.1 and bound
port, with no redirect/proxy path. Profile hashes the specified existing consumer
code closure, fixed protocol contract, bundled-plugin inventory and versioned
request/receipt rules. Config hashes the actual closed selected-route projection
including endpoint/model protocol id, reasoning/fast/language/mode/lazy/coding
workspace policy and opaque credential incarnation; it excludes credential bytes.
Source hashes come unchanged from the authentic authoring binding. Limits is
exact `{max_concurrent_turns:2,max_requests_per_turn:4,max_request_bytes:1048576,
max_response_bytes:1048576,turn_deadline_seconds:30,max_metadata_bytes:16384}`;
Session deadline/remaining limits can only tighten them. Retry tests fit these
bounds or use a separately reviewed profile version, never caller overrides.

descriptor_id is the canonical hash of all other fields. Raw descriptor hash is
the canonical record hash. Persisted data has no auth token, secret, live object,
path callback or permission boolean. The live object additionally retains exact
Session/host/source owners, socket owner, config and auth witness identities and
event hash. Replay requires equality of the entire request/current capture and
these live owners. Reopening a blob/JSON/dataclass never reconstructs authority.
Changing any descriptor constituent retires it for new work; do not edit it.

### Selector exact fields

The concrete API producer derives, never accepts, this exact
`QualificationApiSkillSelectorV1`:

```
version=1, kind='qualification_api_skill_consumer', domain='qualification',
run_hash, brain_id, target_id, authoring_context_id,
consumer_descriptor_id, consumer_descriptor_hash,
agent_key, context_id, domain_contract_hash, language, channel='dashboard',
consumer_profile_id, consumer_profile_version, consumer_profile_hash,
consumer_config_hash
```

This adds descriptor identity to the first report's proposed API selector and
is authoritative for the API branch. It deliberately makes the disposable
slot narrower than product: a registered host/session incarnation, not every
possible DM of that agent. All fields are equality-joined to the actual registered
record. Product SkillSelectorV1 and E1 TechnicalSkillSelectorV1 remain disjoint.
Use E1's existing domain/run/selector-hash unique pointer core; no new table,
wildcard, precedence or runtime selector mutation.

### Plan, outcome, decision and pin grammar

Add a host-only entry on the existing Session producer:

```
freeze_api_skill_transition(authoring, consumer, *,
    expected_target_generation, expected_policy_version, event_key)
    -> TechnicalSkillPlanV2
```

It accepts only the exact registered consumer object above, derives target and
context from it, and calls the **same** E1 freeze implementation after a private
owner-specific consumer validation. No checker registry/result/config selector
is supplied. Freeze occurs before any candidate staging for this native
authoring context; E1's unique run/target/context rule still applies. An existing
in-process plan is a conflict. To exercise both consumers, create separate
genuine authoring contexts/runs before their candidates, never a second plan
after learning the first outcome or cloning its candidate.

`TechnicalSkillPlanV2` has exactly the E1 plan's closed fields after the
technical-turn supplement's source-field renames, with these explicit changes:

- `version=2`;
- add `consumer_kind='qualification_api'`, `consumer_descriptor_id`,
  `consumer_descriptor_hash`;
- `selector` is exactly QualificationApiSkillSelectorV1 above; `selector_hash`
  is recomputed, and existing consumer_profile_hash equals the descriptor's;
- `source_engine_config_hash` and `source_engine_profile_hash` remain the E1
  native authoring values; no unprefixed engine hashes are reintroduced.

All E1 baseline/target/grant/edit-authority/frontmatter/dependency/checker/profile
fields, supported/account_ready/business_proof false values, fixed coverage,
plan-id derivation and generation/replay semantics remain required. The v2 cold
parser has a separately enumerated exact field set; it does not opportunistically
allow either old/new fields. Freeze atomically rechecks descriptor event/hash,
live host and native authoring authority with the ordinary no-candidate checks.

For avoidance of parser ambiguity, the complete v2 plan field-name set is:

```
version, domain, supported, account_ready, business_proof, coverage,
run_hash, plan_id, profile_id, profile_version, profile_hash, checker_source_hash,
brain_id, context_id, experiment_id, target_id,
base_revision_id, base_hash, target_generation,
selector, selector_hash, source_engine_config_hash, source_engine_profile_hash,
consumer_kind, consumer_descriptor_id, consumer_descriptor_hash,
consumer_profile_hash, policy_version, context_grant_hash, context_grant_generation,
edit_authority_id, edit_authority_generation, source_authority_hash,
frontmatter_hash, dependency_hash
```

Plan.context_id remains the **authoring context record id**; the nested selector's
context_id is the separately derived DM context. Their roles must not be confused.

`evaluate_skill_transition` remains one evaluator implementation. It dispatches
only from the exact Session-registered plan class to its matching private
consumer validator, then executes E1's same authenticated bytes, two variants,
two fixed cases, cleanup, summary and publication logic. API plan produces a
`TechnicalSkillOutcomeV2` whose field set is exactly OutcomeV1 plus
`consumer_descriptor_id`, `consumer_descriptor_hash`, `selector_hash`, with
version=2. Those added values must match its exact v2 plan. It still says
authenticated_skill_bytes_only, business/independence unverified. No HTTP or
model operation occurs during structural evaluation. The API coverage comes
only from the later actual consumer receipts.

The complete v2 outcome field-name set is:

```
version, domain, supported, account_ready, business_proof,
business_eligibility, independence, coverage,
run_hash, outcome_id, plan_id, plan_hash, candidate_id,
candidate_hash, candidate_provenance_hash, candidate_stage_event_hash,
authority_binding_hash, cells, complete, case_outcomes, outcome,
checker_source_hash, profile_hash, evaluation_evidence_hash, cleanup_evidence_hash,
consumer_descriptor_id, consumer_descriptor_hash, selector_hash
```

Unknown keys, omitted keys and bool-as-int reject. E1's exact cell/case schemas
and canonical hash/id derivation apply unchanged.

`issue_skill_decision` remains the only constructor and same shared entry. The
v2 decision's internal payload includes plan/outcome version and hashes,
descriptor id/hash and selector hash, plus E1's exact owner/run/candidate/
manifest/target/policy/activation CAS fields. The exact live registered v2
outcome/plan/consumer/host must agree; recompute fixed checks and all source
authority as E1 specifies. Native Session current validation and API host current
validation are both required. A valid API auth witness cannot replace a lost
native authoring grant, and vice versa.

The existing qualification apply admission passes this private decision into
the **same** prepare/ready/pointer CAS/recovery/revert core. Its technical pin
envelope gets a distinct API version/tag containing descriptor refs and the
API selector/config/profile; immutable source-authoring fields retain their
original meanings. Its parser is chosen from the concrete registered issuer,
never an incoming domain string. Historical cold parser dispatch by recorded
version may read evidence but cannot issue a decision or open a scope. E1 v1
pins/events remain valid in their original path with no migration/rewrite.

The real `/ws` message later enters TaskSkillTurn.start carrying a binding
minted by this exact host. Private API scope open requires that binding's actual
session/message/job/runtime and descriptor identity match the frozen v2 selector
and current pointer. It derives qualification domain from the owner. A baseline
turn before apply or after revert can use this same admitted API owner with the
same selector and a fresh task/step; source authority is still checked. Public
ordinary factory continues refusing anchored stores and technical records.

Lifecycle sequence is therefore unambiguous:

```
reserve process root -> real Session -> real app/loopback/auth/session owners
-> real native authoring context + editable region
-> authenticate actual /ws connection -> register API consumer descriptor
-> freeze v2 technical plan (zero candidates)
-> stage candidate ordinal 1 -> same four-cell E1 evaluation
-> private v2 decision -> same shared apply/CAS
-> actual /ws user message -> actual task/start/scope/API/tool delivery
-> revoke/close turn -> revert -> fresh admitted turn reads baseline
-> drain app owners -> Session cleanup
```

## Implementation files, focused proofs, and remaining limits

Required new bootstrap module and API binding/descriptor module are private
owners, not executor services. Existing modifications are bounded to
QualificationSession root adoption; main's dotenv/initial store attachment,
API-native constructor deferral and admission/turn joins; config auth witness
locking; mcp_store's owned-root no-legacy fence; and the E1 technical producer/
parser/pin extensions enumerated above. Existing sessions, ChatRuntime,
ObserveRuntime, GoalStore, engine, hub and E1 algorithms remain actual consumers.
The additional existing dependencies inspected for this resolution are
sessions.py, config.py, secrets_store.py, chat_runtime.py, mcp_store.py,
plugins_host.py, brain_ident.py, improvement_trial_service.py and
improvement_trial_selection.py. Their exact factory contracts are identified
above; no unspecified callback is needed.

Focused acceptance must prove: rejection when config/main was imported before
reservation; rejection of an arbitrary/adopted root or second Session; identical
Session.assets/store/blobs at actual scope; no repository .env/legacy registry
read; fresh auth/config keys; unchanged native five-field selection/pin through
API session selection; actual valid-cookie and invalid/drop-session WebSocket
controls; actual register_job/TaskSkillTurn path; pre-candidate v2 freeze and
four real cells; wrong descriptor/replay/native grant/host owner refusal; API
receiver payload; v1/v2/product parser separation; failed close retains cleanup
ownership. An I/O/socket observation test should fail on any unexpected external
write/connect/import side effect rather than patching those actions to succeed.
It is a confinement assertion, not a fake provider transport. Full app startup
is explicitly outside this route integration proof.

The architectural prerequisites are resolved by these contracts. No inherent
native/API identity conflict remains: private pre-import root adoption and a
real API session pin separate storage ownership from native authoring defaults.
Actual implementation/review may discover an additional import-time side effect
requiring a similarly narrow owned-path fix; it must be named and tested, never
hidden by global monkeypatching or reported as integration success. Existing
Q1/Q2 native source/Session admission can still refuse the installed environment;
that remains a real execution gate, not a reason to fabricate a Session.

Production business acceptance remains intentionally unavailable, not an
unresolved bootstrap design question. Agent-DM LazySkillSource prompt injection,
global startup, arbitrary file exclusion, real inference/account readiness and
native effective delivery remain unclaimed. No design here changes those gates.

## Required D2 direct-target and dependency-read gate

Contract clarification: the named-consumer API loopback coverage above does
**not** replace the original effective-skill design's requirement for generic
API reads of the selected skill and its dependencies. That requirement remains
a separate **REQUIRED, OPEN D2 gate**. No enforceable generic tool/path coverage
has been established by this report or the immutable source reads.

Before a product effective API profile can be enabled, its actual reachable
generic file/path/tool readers must either route reads of the selected skill
and its declared dependencies through the same live scope/effective pin, or
refuse those reads. The gate must enumerate the concrete profile's reachable
read tools, target/dependency paths and aliases, and prove their behavior with
actual consumer tests, including stale/revoked authority and alternate path
forms. A named skill-handler receipt, disabled external connections, or the
protocol fixture choosing only javis_use_skill cannot satisfy that gate.

Product effective-profile admission must require this verified direct-read
coverage **in addition to** host binding, source/grant/policy compatibility,
ordinary technical/runtime gates and genuine business acceptance. If the gate
is missing, partial, stale or failed, the product effective profile remains
unavailable even if business acceptance later becomes available. Never serve
candidate bytes through named skill consumers while quietly allowing an
unqualified generic reader to serve a conflicting canonical target/dependency
view under a product effective-profile claim.

The qualification API loopback may remain enabled only under its explicit
`qualification_api_protocol_delivery` label with
`direct_target_dependency_reads='unqualified'` and `d2_complete=False` in its
coverage projection. These are honest cold-report coverage fields, not new
caller-controlled authority flags or changes to the closed descriptor/plan/
outcome schemas. Product-profile gating derives from its own authenticated
coverage evidence and cannot consume these partial qualification receipts as
readiness. Ordinary baseline behavior remains its existing contract; no
canonical overwrite, permission revival or broad interception is authorized by
this clarification. This report therefore resolves the bootstrap/registration
architecture while leaving full D2 and product effective-profile readiness open.
