# M2 effective skill activation and runtime engineering design

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

Root status: proposed design; no activation implementation, migration, actual
native qualification or live apply. Goal18 authorizes M2 engineering only and
delegates routine design choices; no repeated approval. Q1 query worker currently
owns the sole local app/native slot. This design uses committed source, not WIP.
Fresh Astra/high builder check returned nothing important left for narrowed E1
after resolving outcome issuance and technical turn binding. E2's actual owner
API bridge and E3 native support remain required separate design/gates; this is
not approval of an unspecified ordinary API integration.

## Root scope and dependency rulings

Build **E1 transaction + shared skill readers** first, then **E2 actual owner API binding/UI/usage**,
and M2F integrated disposable feasibility workflow after D1 query gates. The
report's native E3 interface is a required separate support gate, not permission
to implement a second executor/sandbox or widen M2 into agent/workflow/bot work.
Do not dispatch any E implementer while Q1/Q2 implementation/gates hold the
serial slot. E design/builder checks are read-only and independent now.

The installed SDK0.2.116 mechanism supplement below supersedes the initial
unknown-discovery-primitive claim: explicit skills list + namespaced local
plugins exists, but it does not establish filesystem exclusion or original
Skill/path permission parity. Full native D2 remains OPEN until a legitimate
actual profile passes. Normal native baseline stays existing behavior; an
unavailable effective profile is not a silent claim of API-only completion.
Preserve actual setting_sources semantics, not its misleading old comment.

Two-table schema11 is proposed for required mutable readiness/CAS/unique scope.
The unrelated deferred recipe-consent plan did not reserve schema11. Recheck
actual schema before any migration; no reservation or product/schema write here.
Reuse existing blobs/events/outbox source/CallLedger/task-scope consumers.

Production acceptance remains fail-closed because genuine business/independence
evidence is unavailable in Goal18. Engineering must reach the same concrete
materialization/CAS/read/revert core through an exact live QualificationSession
in its disposable store, with technical decision provenance and no fake product
eligible result, caller allow flag or production policy write. Reconcile final
landed Q1/Q2 typed proof/retained-owner interfaces before implementation; do not
invent an outcome issuer which depends circularly on a future M2F workflow.
The [technical outcome contract](2026-10-24-m2-technical-skill-outcome-design.md)
resolves E1's prerequisite: Session-owned freeze/evaluate/issue over real current
M0/context/edit/candidate records. Its fixed pre-candidate four-cell structural
profile evaluates actual authenticated skill bytes, issues a private decision
only for a complete improvement win with preserved regression, and retains loss/
tie/unknown without apply. Coverage is authenticated_skill_bytes_only; no model/
business/native outcome is inferred. No M2F record or product comparison result
is required. This supersedes the report's undefined workflow-record prerequisite,
not its product gate. Narrow same-builder verification is complete for E1.

M2F tests win/loss/tie/unknown and keeps baseline on loss/unknown; simulation
never becomes business success/live canary. D2/E/F/final source-native/CI/review/
integration and committed handoff remain open. No M3–M8 expansion/new Goal.

## E1 turn-binding scope correction

The [technical turn contract](2026-10-24-m2-technical-skill-turn-design.md)
defines E1's exact retained in-process turn into common TaskSkillScope/router/
lazy/hub readers. It does not enter TaskSkillTurn.start or provide fake API/key/
owner fields. Native Session pin remains unchanged, authoring engine hashes are
source lineage, and a disjoint TechnicalSkillSelector/consumer profile identifies
this qualification-only slot. The supplement's technical field renames and owner
factory are authoritative. This corrects the report/outcome's "simulated owner-DM
API turn" claim. Real ordinary API host/provider admission remains necessary
E2/D2 work; full API/native coverage is not supplied by E1 or M2F byte checks.

## Source-derived architecture report and installed mechanism supplement

The report is reproduced verbatim from the read-only architecture artifact,
SHA2566f3e0ffd3585a86bc24ea6ff305532165e82cd259e064c575edd1ca4e52e4836.
It records source references, exact fields/ownership, alternatives, minimal
storage, materialization/recovery, runtime/pins, UI/usage and required tests.

# M2D2/E effective user-skill runtime and manual decisions

Design only. Source basis: `faa5a22107fbbf7299b635cf69d031aa634cf0d3`, 2026-10-24.
All product/spec reads used immutable git snapshots. No app/test/native imports,
execution, probes, source edits or Git mutations. This is not qualification evidence.
Proposed names below are new unless explicitly identified as existing.

## Decision and scope

Choose one activation owner in the existing resonance store, two minimal new
authoritative tables, existing encrypted blobs/events, and the actual
TaskSkillScope consumer. Keep comparison EffectiveViews comparison-only. Separate
a durable effective pin from its revocable per-turn handle. Manual apply/revert
share one materialization and pointer transaction core. Production admission
requires genuine acceptance and remains closed under Goal18; a concrete
QualificationSession-bound facade exercises the same core in its disposable store
without publishing eligible product evidence.

M2 changes exactly one existing user skill body, preserving raw frontmatter,
identity/description/ownership/enabled state and dependencies, in one explicit
scope. No routing changes, helper edits, agent/Team expansion, automatic
allocation/promotion, live canary, duplicate executor/ledger, or M3-M8 work.
VERSION remains0.299.0. Never edit
`tests/python/test_improvement_view_reservations.py`. Preserve existing
compose/Library/archive code, evidence and license. Goal18 supersedes broader
older plans. Owner has opted out of routine clarification; rulings here are
engineering choices, not owner acceptance of a candidate.

### Actual alternatives

1. Activate comparison EffectiveViews directly: few apparent edits, wrong
   authority/lifetime. Those rows belong to comparison/trial contexts and
   semantic lineage; load_current is not ordinary activation authority. Reject.
2. Event-only activation: no migration, but each load would replay history to
   derive unique current selectors, CAS generations and incomplete materialization.
   Relational uniqueness/recovery enforcement is weaker and more complex. Use
   events for decisions, pins and outbox, not mutable pointers.
3. Minimal relational pointer/readiness owner plus existing consumers: chosen.
   It supplies only mutable facts missing from schema10, retaining M0 blobs,
   events, concrete permissions and TaskSkillScope. No generic framework or
   type-only scaffolds; land with an exercised apply -> task read -> revert path.

## Verified source joins

| Existing source/function | Fact and integration consequence |
|---|---|
| `server/improvement_store.py`: SCHEMA_VERSION10, ensure, _replay/_event, capture, retire, _policy | Existing target identity/generation, immutable revisions/bundles, shared events; no activation owner. Policy only off/suggest. |
| `server/resonance_store.py`: GoalStore._Tx | BEGIN IMMEDIATE serializes writers; use for pointer CAS and event/outbox together. |
| `server/improvement_blobs.py`: RevisionBlobs.write/read, check_ancestry | Encrypted content-addressed bytes; file fsync+replace exists, directory/power-loss durability not thereby proven. |
| `server/improvement_views.py`: EffectiveViews.freeze_comparison/load_current/_load_current/resolve_request; improvement_view_sources.capture_sources; improvement_view_materialization.materialize_view | Comparison lineage/current checks, not activation. Reuse exact bytes and source facts without promoting comparison metadata into eligibility. |
| `server/improvement_comparison_results.py`: aggregate/ComparisonResults; improvement_view_schema.py | Arithmetic explicitly reports business_eligibility and independence unverified. Immutable views cannot represent mutable selectors/readiness. |
| `server/improvement_task_skill_scope.py`: open/_live/_source/read/read_receipt/current/bind/reset | Exact live turn token, ObserveRuntime, running task/step, same root/store. Header inventory at open, body on first read. Scope identity contains step/message: currently per-turn. Cold receipts cannot revive it. |
| `server/improvement_task_skill_turn.py`: start/close | Off/default/native exits before core import/M0 scan. Retains capture through repeated cancellation; binds on loop; close revokes copied contexts. |
| `server/main.py`: run_turn TaskSkillTurn use around committed line17135; start around16630 | Normal Dashboard API/OAuth branch only. Fast execute/reject/native do not enter scope. |
| `server/context_runtime.py`: ObserveRuntime.start_turn/TurnTrace | runtime.db is separate from resonance; every turn creates fresh task/step IDs. Session continuation is not a persistent runtime task. |
| `server/skill_router.py`: _task_metadata/list_skills/resolve_skill_file/read_skill_asset; skill_asset_io.open_skill_source | Shared precedence and descriptor-safe reads. Dead bound owner suppresses legacy fallback; preserve disabled canonical precedence. |
| `server/lazy_skill_runtime.py`: LazySkillSource.resolve | Private scope candidates/revisions/body receipt; no brain-wide registry overwrite. |
| `server/mcp_hub.py`: _builtin_tools nested _skill and tools_for_turn cache | Real scope read in retained thread context, owner rechecks after awaits, scope-private cache. skill_usage.bump is popularity, not proof of effective-version use. |
| `server/claude_sdk_engine.py`: ClaudeSDK._options/query/reset_session/warm_ping | Resume uses self.session_id. Ordinary settings user/project/local must retain owner policy. Allowed-tools mode already uses default gate without filesystem settings. |
| `server/improvement_experiment_api.py`: ExperimentApiDeps/register.dispatch; improvement_candidate_api.py owned lifetime | Reuse authenticated owner-session/closed request/settled calls and cold-reader pattern. |
| `dashboard/improvement-experiments.js`: mount/write/action/load; improvement-candidates.js | Existing detail controls, stale panels and retained uncertain payloads; extend these. |
| `server/improvement_usage.py`: trial_usage/operation_usage | Existing purpose/attempt/call reconciliation with partial/null telemetry; no second billing source. |
| `server/improvement_qualification_session.py`: open/_assert_native_current/close/cleanup; assets.qualification_anchor | Concrete disposable root/store/brain and encrypted anchor already exist; a domain string/hash alone grants no authority. |

Bounded source inspection found no genuine production business-acceptance issuer,
ordinary activation owner, or qualified ordinary-native selective skill loader.
Candidate authorize, comparison freeze, native startup and arithmetic do not
implicitly supply those missing authorities.

## Closed contracts and authority binding

Use exact-field parsers, reject unknown fields and bool-as-int, hash raw bytes,
persist private facts encrypted. Requests cannot choose actor, domain, filesystem
paths, capability maps, eligibility verdicts or arbitrary current-guard callbacks.

Proposed SkillSelectorV1 has exactly version1, brain_id, target_id, agent_key,
context_id, domain_contract_hash, language, channel, engine_config_hash and
engine_profile_hash. All fields required: host-resolved brain/live target identity,
actual registered agent, exact dm:<agent_key>, existing domain contract,
normalized language, dashboard channel and actual selected configuration/profile.
No wildcard/null/list/keyword selector. Host derives context, never guesses from
a display name. First supported M2 surface is the actual owner Dashboard agent DM;
other surfaces stay unavailable until their concrete owner joins are verified.
This keeps scope disjointness/equality decidable: one selector slot per
brain+target+selector hash. Corrupt/ambiguous matches produce activation_conflict
and guarded baseline, never last-write-wins. No future specificity engine now.

Private EffectivePinV1 contains exactly version/domain/run_hash, pin_id,
brain_id/target_id, selector_hash/selector, activation_id or null and generation,
materialization_id or null, manifest_hash, base_revision_id/base_hash,
candidate_id or null/content_hash, frontmatter_hash/dependency_hash,
source_authority_hash/owner_rule_hash, grant identity/version/hash, policy_version,
target_generation/identity, engine_config_hash/engine_profile_hash,
host_work_identity and inventory_hash. Product run_hash is null; qualification
requires an anchored run hash. The hash identifies content, not permission.

host_work_identity is a tagged union:
- task: actual runtime DB identity+task id+brain/agent/context. Retry/step can
  reopen only when the real host validates that same task.
- native_session: host-created incarnation+actual host chat/session+engine owner,
  later bound immutably to the observed CLI session id. No client-chosen resume.

A live handle separately owns exact turn token/runtime/trace and is never
serialized. Cold pin/receipt cannot construct it. New turn gets a new handle to
its compatible durable pin; foreign store/root/principal/context/engine or dead
owner refuses. Mode changes never reconstruct a closed owner.

ManualApplyRequestV1: version, expected_generation (experiment),
expected_activation_generation (0 if absent), comparison_report_id, candidate_id,
selector, expected_manifest_hash, expected_target_generation,
expected_policy_version, decision_key. Host recomputes hashes/bindings and checks
selector brain against authenticated brain. Revert: version,
expected_activation_generation, expected_prior_pin_hash, decision_key, bounded
reason. Suspend: version, expected_activation_generation, decision_key, reason.
No caller replacement bundle/path. Keep original exact payload on uncertain retry.

### Product admission

Derive acceptance through concrete same-store selection/report/semantic/owner/
source/grant/contract owners. Gates are conjunctive: fixed final candidate,
required paired quality/regression coverage, genuine required independent
business evidence, required owner/content acceptance, matching verified
execution/profile, current permission and one exact scope. Tuning/final numeric
eligible, JSON validity, synthetic uniqueness, native mechanical proof and
clicking Apply do not fill missing gates. This follows the stricter task brief;
the general spec's future manual unproven experiment option is not enabled here.

Current aggregate always leaves business/independence unverified. Product
preview/apply therefore returns explicit acceptance_pending and cannot even
prepare an activation. Do not add an issuer that turns an arbitrary owner
assertion into independent evidence. Genuine acceptance issuance is a later
business dependency; Goal18 neither obtains it nor opens live activation.
Implement and test the real refusal endpoint rather than an unconnected stub.

### Engineering without a bypass flag

Propose ActivationOwner.for_qualification(session) with host-only
apply_simulation/revert_simulation/open_simulated_turn. Require exact live
QualificationSession, identity-equal assets/store/blobs/principal, authenticated
run anchor and owned descendant paths. Recheck current Session at admission,
after each await and in commit. Consume final landed P1/Q concrete interface;
do not copy or weaken its private current/retention implementation.

Use existing owners to create real disposable target, body authorization,
candidate and simulation workflow records. Publish a technical outcome event
referencing that actual workflow, retaining business_eligibility=unverified and
independence=unverified. Never insert fabricated product TrialResults or change
ComparisonResults. A private TechnicalManualDecision constructor binds exact
live Session and outcome; no allow_unqualified, skip_eligibility, supplied callback
or supported=True mapping.

Distinct private product/technical admissions invoke the SAME prepare/ready/CAS
core and SAME scope.read/router/lazy/hub consumers. Core validates issuer,
domain, store and target at each transition. Technical rows are qualification+
run_hash and usable only through matching retained technical owner. Default
product API/runtime factories categorically reject qualification anchors and
lineage even if JSON labels are stripped. No public simulation endpoint/switch.
Session cleanup must await decision and turn owners as well as native owners.
This is engineering authority over owned disposable files, not fake eligibility.

## Storage and minimal migration

Two tables are justified: schema10 comparison tables are immutable; events alone
cannot directly enforce current-selector uniqueness/readiness/CAS. No new task,
ledger, result, scheduler, decision history or outbox table.

improvement_activation_materializations:
- id, brain_id, target_id, domain/run_key, immutable manifest_hash/blob_hash,
  immutable admission/request hash, relative_version_dir, state,
  generation, claim_nonce/lease_until and timestamps.
- state pending_materialization/ready/abandoned/unavailable; same-brain target FK;
  unique(brain,domain,run_key,manifest_hash); product run_key empty, qualification
  nonempty authenticated hash; strict path/digest grammar.
- immutable identity/content fields enforced by trigger; only state/generation/
  claim fields transition. ready requires verified matching immutable manifest.

improvement_activations (one current selector slot):
- id, brain_id, target_id, selector_hash/selector_blob_hash, domain/run_key,
  generation, state, materialization_id nullable, prior_pin_blob_hash nullable,
  current_pin_blob_hash, experiment_id, current decision event ref,
  policy_version, invalidation reason, timestamps.
- state canary/active/reverted/suspended/retired; unique exact scoped slot;
  same-brain/domain/target guards and ready-materialization constraint.
  Selector identity is immutable. Every pointer/state transition increments
  generation and appends previous/next pin hashes. prior is the exact previous
  committed pin, not a query selecting any historic winner.

No automatic canary->active implementation. Engineering apply is an explicit
one-context trial; its events never count as live canary. Product remains closed.
Future active promotion is outside Goal18.

Reuse improvement_events for decision reservation/results, transitions, durable
work/session pins and use receipts. Same decision_key+payload returns original
accepted response, changed payload409 before mutation. Initial accepted202/pending
can remain immutable; GET returns current operation status. Separate deterministic
ready/commit/failure events record progress, never rewrite original result_json.

Events are atomic outbox source. Delivery carries event id+object generation.
A distinct idempotent acknowledgement event per consumer (or an existing suitable
checkpoint) allows retry; duplicated delivery never repeats pointer commit.
Runtime reads pointer generation itself, so missed notification cannot make a
stale cache authoritative. No automatic external messaging is added.

Propose schema11 in server/improvement_activation_schema.py, wired into
improvement_store.ensure. Assert exact historical10 and absent new namespace
before backup; refuse future, partial and lookalike schema. Reuse existing
migration_transaction/backup conventions, atomic DDL+version, immutable guards,
downgrade refusal and all compose/recipe forward checks. Cold GET on10 returns
no activation without migration. Explicit writable factory alone initializes11.
No candidate content becomes a synthetic M0 revision/bundle.

## Materialization, CAS, durability and recovery

ActivationOwner retains one decision task BEFORE its first await. Reuse settled
call/cancellation-resistant owned-lifetime patterns: HTTP disconnect cannot
abandon an off-loop file/DB mutation. Close revokes new work then joins retained
workers. Cancellation is never proof that commit did not occur.

1. Authenticate owner/domain and validate exact request. Replay/conflict known
   key before mutation. Derive real candidate/base/dependency/owner/grant/contract/
   profile facts. Technical owner also checks Session/root/anchor. Build closed
   manifest from actual bytes; raw frontmatter must equal baseline.
2. BEGIN IMMEDIATE: recheck exact experiment/target/policy/selector generations,
   current authority and replay. Insert pending materialization+accepted decision
   event. Recheck source after encryption/slow capture before authority write.
3. Build only a host-named private subtree under
   STATE_DIR/improvement/<brain-key>/effective/<domain-run>/<id>.tmp. Descriptor
   checks prevent symlink/junction/path/case escape. No global mirror/canonical
   writes. Write exact bytes+manifest, hash from actual opened handles. Preserve
   owner policy separately from editable body. M2 dependencies remain unchanged.
4. Flush files, same-volume atomic rename into immutable version directory,
   flush parent metadata where supported, reopen and verify complete manifest
   and bytes. POSIX requires file and directory fsync. Windows requires a tested
   durable rename/flush strategy: os.replace alone is not power-loss evidence.
   Unsupported storage durability leaves profile unavailable. Recovery can refuse
   missing files; it cannot pretend a durable acknowledged commit existed.
5. Short transaction checks claim ownership, completed directory and current
   admission before setting ready. Source drift/expired owner marks stale or
   abandoned. Ready materialization alone never changes a selector.
6. Final BEGIN IMMEDIATE rechecks ready manifest, live target identity/generation,
   base/dependency/owner hashes, candidate authority, current grant/version,
   contract/profile/policy, evidence authority, experiment generation and expected
   selector generation. Recheck after slow reads immediately before CAS. Update
   pointer once and append transition/outbox+decision result in same transaction.
   No external await inside SQL; failure rolls back pointer and event together.
7. Publish committed event after transaction. Lost response uses original key or
   GET; no retry against a newer revision/generation/scope. Existing pins remain.

Filesystem and DB cannot transact together. Fresh descriptor/hash observation
immediately before CAS is necessary but cannot prevent an external editor from
changing the source afterwards. Commit therefore is not an enduring permission
promise: every new pin and subsequent tool/model/return gate rechecks source,
enabled state, owner/grant and manifest. Drift suspends before further use. An
already returned read is in flight, not undone. runtime.db and resonance are
also separate: check _live before/after resonance operations, before bind and
before delivery; do not claim atomicity across both DBs.

Recovery never renews authority:
- Pending/no directory: retain audit, remove only verified owned temporary tree
  after claim/retention checks, never activate.
- Pending/complete directory: verify exact bytes and current accepted intent;
  mark ready only if valid. Partial/mismatch is unavailable.
- Ready/no pointer: startup may finish ONLY an existing accepted persistent
  product decision with current authorization/CAS. A naked directory is not
  intent. Closed/expired qualification Session cannot auto-commit; mark simulation
  interrupted and abandon safely.
- Committed/missing-corrupt-notready directory: CAS suspend+event before serving;
  do not regenerate different bytes under its identity.
- Commit/outbox failure: redeliver existing event only. Competing reconcilers
  claim generation+nonce+lease; loser neither commits nor deletes winner files.
- Historical decision replay after revocation returns non-secret historical
  result plus current state, never body access/new authority/new generation.

Retain active/prior/live-pin versions. Initial M2 can safely omit automatic GC
and use only disposable-session cleanup after owners settle. If GC is introduced,
it requires reference checks, grace/journal and atomic reference exclusion; never
collect a pin while another process obtains it. No new retention subsystem needed.

## Effective task pins and existing consumers

Extend TaskSkillScope. Proposed open_effective(owner,...work_identity) derives
pin from exact ActivationOwner and actual turn objects; existing open retains
strict baseline snapshot behavior. At first supported work boundary, read exact
selector, verify ready/source/authority, pin candidate+canonical target bytes and
unchanged dependency manifest BEFORE model input. Persist one immutable work pin
event; subsequent openings read it and never choose a newer pointer. Frontmatter
stays canonical, so M2 does not change ranking/discovery metadata.

Other ordinary skills keep bounded header inventory and first-read bodies. Do
not claim all unrelated bodies were eagerly snapshotted. The activated target
and all dependencies used by its enabled profile are eagerly hash-pinned;
first-use timing cannot change that target body after work starts.

A real multi-step task reuses its host task identity and fresh step handles.
Dashboard start_turn currently creates new tasks per turn, so API turns are new
work. Do not invent one persistent API task for all chat history. Native uses
session incarnation below. Missing host identity refuses effective selection;
no silent attachment of a new pointer to old work.

scope.manifests returns original metadata plus private registry revision derived
from effective pin/inventory/profile. scope.read returns exact SkillAsset bytes
and records actual delivery; owner/source/grant rechecks precede and follow blob
reads and final return. For selected target, _source checks canonical base
identity/content/permissions, not candidate content. Pointer change alone does
not invalidate an old pin. Disable, canonical replacement, owner/grant/dependency
change does. current(root) rejects foreign/dead owner without fallback.

Consumer joins:
- Router _task_metadata remains scope-private. No global CapabilityRegistry
  overwrite. Cache keys include pin/inventory/profile/language and hub epoch;
  hits recheck authority/source.
- LazySkillSource.resolve consumes unchanged metadata and pinned body. Existing
  source_hash is candidate hash only when real effective pin proves that choice;
  receipt retains base and activation/pin lineage.
- Hub _skill retains off-loop reads and current-owner checks after every await.
  Effective delivery receipt is distinct from skill_usage.bump. A post-bump
  owner loss must not become proof that body was delivered/used.
- Actual generic file/helper tools cannot bypass an enabled effective scope to
  load the canonical or mirror target body. Route exact selected-target and
  declared-dependency reads through scope or refuse; unrelated reads unchanged.
  Audit/test these real paths before enabling a profile. Native shell bypass is
  not solved by API interception and requires the native gate.
- Feature absent/off/no matching supported effective runtime retains existing
  behavior; no new scan/import/M0 initialization until explicit feature path.
  Baseline task-snapshot option is not an activation switch. Cold metadata GET
  never constructs a runtime owner.

## Native pin/resume/loading and unresolved mechanism

ClaudeSDK ordinary chat is not the D1 trial worker. Never install TrialProfile or
dummy qualification environment into ordinary owner chat. D1 is the dependency
for selectedCLI localhost proof and retained native ownership, not permission to
change owner policies. Reconcile final landed P1/Q interfaces; do not duplicate
attempt accounting, native executor or session/query ledger.

Proposed EffectiveNativeBinding is constructed only from actual live scope and
exact ClaudeSDK owner. It owns immutable private directory/manifest, engine/profile
and session pin. _options, query input, observed session adoption, reset_session
and warm_ping must consult it. Preserve existing permission/settings semantics,
owner CLAUDE instructions, hooks and selected model/provider/reasoning.

Closed session rules:
- Create immutable host incarnation/pin before first query. On genuine CLI
  session id, append one-to-one session->pin binding before any later resume.
  A reused/conflicting observed id refuses; no arbitrary caller mapping.
- Resume always uses same directory/pin despite later pointer CAS. Never rewrite
  files under resumable session. New activation applies only to new incarnation.
- Missing/foreign/corrupt mapping or changed owner/profile/source yields
  effective_resume_unavailable before user input. Do not silently reset and resend
  potentially side-effecting prompt. Explicit new-session operation can start
  fresh with current authority.
- Ordinary suspend/revert leaves compatible in-flight pin; security invalidation
  stops at next relevant native/tool/return gate. Warm ping proves identical
  current pin/session/permissions or refuses.
- Close retains query/engine/materializer owners through actual SDK/process drain
  before cleanup. Cold records never reconstruct a live native binding.

**Mechanism ruling:** task-specific plugin loading is a candidate, not a proven
implementation primitive. Current ordinary _options loads user/project/local
settings and ambient skills. Disabling settings to hide duplicate canonical/
mirror skill removes owner policy. Blocking native Skill in a hook does not prove
discovery exclusion or direct Read/Bash/helper exclusion. Existing native probe
notes include failed stale-cwd Read and no policy-parity/resume proof.

After D1 lands, resolve this with one bounded installed selectedCLI localhost
gate. Prefer supported selective per-skill discovery/exclusion plus private
plugin ONLY if the installed SDK/CLI actually preserves owner policy with it.
If unavailable, do not invent an SDK field, clone owner settings ad hoc, rewrite
roots or add broad permission bypass. Keep that profile unavailable and record
an explicit **D2 native design/support blocker**. API transaction engineering is
independent; full D2 cannot quietly be called complete as API-only.

This source-only report cannot honestly supply a verified ordinary-native
exclusion primitive. That is the one unresolved architecture dependency, not a
request for routine user approval or live feasibility. D1 query success alone
cannot settle it.

Mandatory native proof binds selected CLI/SDK/source fingerprint, exact ordinary
options, all discovery roots, duplicate canonical+mirror exclusion, actual body
bytes, unchanged owner deny/allow policy, direct Read/Bash/helper routes,
model/reasoning, session/pin/resume, delivery and cleanup receipts. Actual installed
CLI with dummy localhost provider is required; mocked SDK fields do not qualify.
No native selector can activate until its profile passes the gate.

## Revert, off, suspension and permission loss

Revert uses only exact previous committed pin, verifying ready files, current
canonical/dependency/owner/grant/profile/contract and target identity. It cannot
revive expired grant or choose a convenient historical candidate. One CAS changes
pointer+generation+event/outbox; immutable versions/history remain.

Incompatible prior -> suspended_no_compatible_baseline. New work may use current
canonical only after ordinary guards pass. Never overwrite canonical, merge old
patch, restore old owner text or redeliver a past product. Missing prior is
explicit canonical fallback, not fabricated activation.

modeoff blocks new improvement work/uncommitted apply while preserving accepted
compatible activations and ordinary business tasks. Suspend affects new work on
that pointer only. Source/permission/target invalidation always wins, even while
modeoff. Changes remain separately observable; policy replay does not mutate
history. Ordinary off is not permission revocation. Recheck live authority rather
than blindly comparing one old policy number to shut down accepted work.

## API, UI, usage and provenance

Extend existing owner-session experiment routes and skill/agent detail controls.
No separate management dashboard or public simulation switch.

Proposed routes:
- GET target effective-revision for authorized explicit selector: current state,
  exact scope/pin/manifest, supported consumers, canonical and prior compatibility,
  business/native blocker reasons and admissible actions.
- POST experiment apply; POST activation revert/suspend; GET decision status.
  Invalid422, authority403, stale/conflict409, verified storage unavailable503.
  202 only after durable accepted pending decision. acceptance_pending is explicit
  refusal, never fake202 launch. Read historical metadata does not resume work.
- Existing report/usage GET remains redacted, no private bytes/absolute paths/
  secrets or bearer capability returned.

Reuse owner_session and CSRF middleware, bounded read_json and exact action parser;
never getattr from user operation. Retain service/request before awaits. HTTP abort
does not erase uncertain commit. Before-commit cancellation is recorded only after
retained work settles; after commit a separately authorized revert is required.
Historical reads still authenticate.

Existing JS mount owns full payload+key across uncertain retry. Disable double
click; reload409 without changing/replaying decision; version-guard late snapshots;
dedupe event/generation and reconcile after reconnect. Show exact body diff,
one-context scope, measured coverage/unknowns, model/reasoning, existing usage,
business/native pending and prior compatibility. vi/en/mobile. “Improved” never
comes from proposal, mechanical eligible, technical simulation or body receipt.
Engineering output labels simulation; production UI never exposes a bypass.

Usage stays existing usage event/CallLedger authority. Apply/read/revert without
model calls create no agent_call or fake zero-cost execution. improvement_usage
joins real operation/trial refs; ordinary use keeps its existing purpose/call and
adds provenance link, not improve_probe billing. Preserve null/partial tokens,
requests and money, late usage identity and existing deduplication.

Proposed immutable skill_effective_use receipt: domain/run; work/turn/session;
actual execution ref when available; target/slug; base and candidate content
hashes; activation id/generation; pin/manifest/inventory/profile hashes; consumer
(lazy_prompt/hub_skill/native_skill/direct_read); delivered bytes hash/length/
truncation and observation kind. Distinguish selected/materialized/delivered/
observed use. File existence or skill_usage.bump is not comprehension/business
success. Deduplicate identical tool invocation/native event id, retain genuine
second loads. Cold provenance checks access and returns history, never live scope.
Model text is not a host receipt.

## Cohesive implementation ownership and order

Root may sequence after P1/Q gates. This design does not inspect worker WIP or
assign another worker. Each unit must include actual consumers/tests, not unused
helpers/type scaffolds.

1. **Transaction and API-runtime vertical.** New
   `server/improvement_activation_schema.py` and
   `server/improvement_activations.py` own migration, closed contracts, concrete
   admissions, materialization/CAS/recovery. Extend improvement_store.ensure,
   improvement_task_skill_scope and improvement_task_skill_turn together. Add
   Session-bound engineering lifetime only after final P1/Q interface reconciliation.
   Prove real technical apply -> actual router/lazy/hub read -> revert and product
   categorical refusal. No global registry edit. Schema+authority consumer is one
   reviewable integrated unit; combine modules if file-size conventions warrant.
2. **Owner/API/UI/usage closeout.** Extend improvement_experiment_api and its exact
   request owner, main factory/lifetime registration, existing dashboard controls
   and vi/en strings. improvement_usage changes are projections/joins only.
   Real route+DOM tests prove exact-generation/scope decisions. Crash/migration/
   source-race cases use real store/files. Production acceptance remains pending.
3. **Native profile and installed gate.** Resolve mechanism above; own necessary
   claude_sdk_engine, host session/turn binding and materialization changes only.
   Reuse D1 Session/localhost worker interfaces, not a second executor/protocol/
   ledger. Gate precedes enablement. If no safe mechanism, document exact blocker
   and keep full native D2 engineering open, never redefine completion API-only.
4. **M2F integrated simulation/handoff.** Win/loss/tie/unknown/keep-baseline,
   apply/revert/recovery, stopped/revoked sources, usage and UI on disposable
   contexts. No live model/account/business work. Final-source evidence, full
   CI/review/native outcome go into committed Claude handoff; business/live stay
   PENDING. No M3-M8 expansion or new Goal.

## Meaningful RED/GREEN, integration and fault matrix

RED is a real consumer violating the invariant, not merely a missing method.
GREEN retains actual behavior. Only technical fixtures and mandatory installed
localhost gates later; none ran during this design.

| Boundary | Required behavior/evidence |
|---|---|
| Real body choice | Concrete disposable authoring/technical apply -> actual scope/router/LazySkillSource/hub loads candidate for exact selector and baseline for other agent/context/language/engine. No mocked scope.read or eligible flag. |
| Work pin | ApplyA/open actual task/applyB/rereadA; new task readsB. Target pinned before input. Retry retains task pin; new Dashboard turn intentionally has new task. |
| Native incarnation | Real selectedCLI first session mapping, pointer change, resume same bytes/directory/pin. Missing/forged/foreign/incompatible mapping refuses before input. |
| Domain separation | Product owner refuses technical store/anchor/lineage even stripped labels; forged admission, copied blobs, foreign principal/root/session fail. Closed/expired Session fails at admission and final CAS. Genuine simulation only succeeds inside owned store. |
| Product acceptance | Tuning/final arithmetic eligible with unknown business/independence refuses before materialization. Candidate authorize/click Apply insufficient. Regression failure/unknown/late drift cannot commit. |
| Selector/CAS | Two real processes apply same selector: exactly one generation winner. Same key/payload replay; changed payload409. Wildcard/unknown/Team scopes refused. Disjoint selector unaffected. |
| Source drift | Edit/disable/delete-recreate at read/encrypt/ready/precommit; revoke grant/owner after decrypt/before return. No stale mirror, permission revival or canonical edits. External change after commit caught at pin/read gate. |
| Owner lifetime | Cancel/close during off-loop capture/materialize/commit, repeated cancellation, copied context after close. Retained workers settle; no late bind/return; lost response preserves actual committed result. |
| Cache | Warm lazy/hub cache across pointer/policy/source changes; existing compatible pin stays exact, new scope sees correct version, dead bound scope never falls back to disk. |
| Direct reads | Actual generic API skill/helper read cannot load competing canonical body in effective scope; manifest/current-grant dependencies only. |
| Revert | Exact valid prior changes new work; changed/revoked/corrupt/missing prior suspends with guarded canonical fallback. Ordinary revert preserves compatible active pin; security invalidation stops it. |
| Crash/recovery | Fault after reservation, each write/flush/rename, ready, pointer commit and outbox. Two reconcilers. At most one pointer generation, no partial body/foreign temp deletion. |
| Filesystem | Real Windows/Linux descriptor containment and same-volume publication; junction/symlink swap, case collision, invalid path, permissions and oversize fail closed. Test actual handles, not mocked exists. |
| Outbox | Delivery failure/repetition yields one UI generation, no second apply. Cache correctness before notification. |
| Policy distinctions | off blocks new/uncommitted work but retains accepted compatible pointer; suspend affects new work; revoke invalidates even off; ordinary task not cancelled merely for off. |
| Migration | Fresh/historical10 copy to11; concurrent migration/backup interruption; partial/unknown/future namespace refusal; cold GET no migration; downgrade guard and forward compose/recipe constraints. |
| UI/API | Actual owner/CSRF denial; foreign brain/stale tab/double-click; timeout same key; acknowledged-write refresh failure; duplicate events/reconnect/panel dispose; vi/en/mobile. No client acceptance. |
| Usage/provenance | Actual delivery receipt exact pin; pre-return failure not counted observed use; duplicate invocation deduped; missing/late usage partial/null; ordinary purpose retained; no billing row from apply. |
| Defaults | Feature absent/off, legacy brain: no model call, policy write, migration, native option change, overlay scan or added eager body capture. Existing TaskSkillTurn lifetime/read behavior preserved. |

Mandatory integration beyond fixture seams: real current route factories,
two-process SQLite/file recovery, actual Windows descriptor/rename behavior,
installed selectedCLI+SDK localhost discovery/policy/resume for each native
support claim, affected repo regressions and final-head full CI/independent
review. Record exact source fingerprints; earlier native evidence is historical
if profile sources changed. Root owns scheduling; this designer ran none.

## Remaining blockers and limits

- Ordinary-native selective discovery preserving existing owner settings is not
  source-proven. Resolve the exact installed primitive or keep profile unavailable
  and full native D2 open. D1 query proof alone does not solve it.
- Genuine product business/independence acceptance is absent under Goal18. This is
  a fail-closed production condition, not a reason to stop transaction/runtime/UI
  engineering or seek live acceptance now.
- Windows power-loss durability needs implementation/actual filesystem gate.
  Existing blob file fsync+replace does not prove directory durability.
- Main auth middleware, all generic direct-file paths and final landed P1/Q
  interfaces were not exhaustively audited in this bounded design. Named consumer
  gates must pass before corresponding enablement. No success follows from a map.

Only this report was written. No tests, migrations, qualification, activation,
account access or runtime success are claimed.

---

## Native mechanism supplement: installed SDK0.2.116 and official docs

Appended 2026-10-24 after the initial design. Original38407bytes are preserved,
SHA2565f3eb11d921ae01f18af52701b656612c05e29c9695059397bb9f6c4a75f8702.
This supplement supersedes only the earlier claim that no concrete selective
model-discovery primitive was identified. It does not assert native qualification
or remove the remaining full-consumer blockers. No CLI, SDKClient, imports,
tests, model, account, localhost probe or product/settings edits occurred.

### Finding

There IS a concrete supported discovery candidate in the installed version:
`ClaudeAgentOptions.skills=[exact_names]` plus a uniquely namespaced local
`plugins=[{"type":"local","path":immutable_plugin_root}]`. Preserve the actual
ordinary `setting_sources`, cwd, HOME, permission_mode, owner hooks/settings,
model/reasoning and MCP configuration. The SDK sends an explicit skill filter
through its initialization control request, separately from tool permissions.
This closes the unknown-option issue; it is not a filesystem isolation boundary.

Full ordinary native effective-body enforcement remains structurally unproven
for the current unrestricted native Windows shell profile. Two distinct issues
must not be conflated with discovery: arbitrary subprocess file access, and
preserving permissions when the original skill/path becomes a namespaced skill/
private materialized path. The smallest sound ruling remains: implement/prove the
supported discovery candidate inside the existing engine, but do not enable an
ordinary native profile until all its read/policy/resume gates are satisfied.

### Installed source inspected without importing it

Package root: `D:/Project/Javis-OS/.venv/Lib/site-packages/claude_agent_sdk`.
Sibling `claude_agent_sdk-0.2.116.dist-info/METADATA` identifies Version0.2.116.
This is the actual installed project venv, not current remote SDK assumed to match.

| Static file/lines | Concrete behavior |
|---|---|
| types.py1729,1740,1776,1813 | tools controls availability; allowed_tools preapproves; permission_mode and disallowed_tools are separate. |
| types.py1953-1982 | Explicit setting_sources retained; skills None/all/list documented; exact names or plugin:skill; list hides unlisted model entries/Skill use but not Read/Bash files. |
| types.py825-832,1997 | SdkPluginConfig supports only local type+path; actual plugins option exists. |
| _internal/transport/subprocess_cli.py244-280 | _apply_skills_defaults copies original options, adds Skill(name) allow entries for list, and defaults user/project sources ONLY when sources is None. Explicit user/project/local or [] is not overwritten. |
| _internal/transport/subprocess_cli.py313-318,413-420 | Serializes effective allow rules, exact setting sources and local --plugin-dir. This is not the entire skills filter. |
| client.py229-241 | ClaudeSDKClient passes options.skills into actual Query, covering Javis's actual SDK client route. |
| _internal/query.py200-218 | initialize includes request.skills for an explicit list, including []; None/all omit it. Thus [] is not accidentally equivalent to no --allowedTools. |
| types.py1893-1910 | can_use_tool handles prompting, not every call; existing allows/permission mode can bypass it. PreToolUse is the per-call hook. |
| types.py413-420 | PreToolUse output supports deny/ask/allow/defer and updatedInput. These are available in0.2.116, not invented fields. |
| _internal/transport/subprocess_cli.py349-356 | resume and session_id are actual CLI flags; they do not pin files. |

File SHA256 values (external dependency fingerprint, not product qualification):
- types.py: 5f94726ec2754af2954f2cadf149ef866b1d634e7d07767954b763cbd265fbca
- _internal/transport/subprocess_cli.py: 1a95b09131da05c2986d7f9cb0536974e52eff6e946dbcc39df3a1453468ccf0
- _internal/query.py: a84c1fc3a1b09cdf2a2eb7a3bcb4d98e456d25b595764c02c5907dd859f1aa16
- client.py: 59f804ba4bcd407b1027841ad8d2b618b31f79eeef0ebd39611733d4a5094607

The installed SDK establishes Python-side fields/serialization. It does NOT prove
selectedCLI enforcement. The committed native-design-probe evidence identifies
historical CLI2.1.309/hash5441781f2b6bbd07354b4a74560ee88c68c9bf05d6db3c7e24c452c91673dc53;
this follow-up did not execute or re-fingerprint that binary. Bind later actual
installed results to the real selected CLI and unchanged package hashes.

### Primary-source observations, retrieved2026-10-24

The official SDK skills documentation supports exact-name filtering and plugin
qualified names. Unlisted skills are hidden from the model and refused by Skill,
but remain reachable through Read/Bash. Direct /name dispatch is independent of
the filter. Init.skills is not filtered proof and omits non-user-invocable skills.
[Anthropic SDK skills](https://code.claude.com/docs/en/agent-sdk/skills)

Local plugins load from a supplied directory and their skill commands carry a
plugin namespace. The init plugin entry reports its name/path. This lets the host
avoid reliance on same-name canonical/mirror precedence.
[Anthropic SDK plugins](https://code.claude.com/docs/en/agent-sdk/plugins)

Skill command names can differ from directory names; a plugin retains its prefix.
Current docs also expose skillOverrides=off, which blocks direct dispatch, but
that setting does not apply to plugin skills. It is a possible future selective
visibility policy, not proof of installed CLI support or file exclusion here.
[Anthropic skill naming and visibility](https://code.claude.com/docs/en/skills)

PreToolUse runs before permission evaluation. Deny/ask rules remain relevant even
with bypassPermissions; can_use_tool is the last unresolved permission step.
[Anthropic SDK permissions](https://code.claude.com/docs/en/agent-sdk/permissions)

A hook may return updatedInput without an allow decision, so normal permission
checks still apply. Hook coverage does not turn a shell command into a filesystem
access monitor, and settings-provided hooks still run.
[Anthropic SDK hooks](https://code.claude.com/docs/en/agent-sdk/hooks)

Read denies cover built-in file tools and recognized shell file operations, but
do not constrain arbitrary Python/Node subprocess opens or every recursive read.
[Anthropic file permission boundaries](https://code.claude.com/docs/en/permissions#what-read-and-edit-rules-cover)

The sandbox applies OS enforcement to shell processes on supported systems;
native Windows commands run unsandboxed. File tools, MCP and hooks are outside
that shell boundary. Switching Javis to WSL2 would change its engine profile and
is not authorized implicitly by this design.
[Anthropic sandbox platform and scope](https://code.claude.com/docs/en/sandboxing)

Session resume restores conversation, not filesystem snapshots; explicit resume
selects a recorded session. Therefore Javis must retain the same immutable plugin
and pin itself and must reject a foreign or missing mapping.
[Anthropic sessions](https://code.claude.com/docs/en/agent-sdk/sessions)

### Concrete discovery candidate and collision handling

Use a task/session-specific host-generated plugin name such as
`javis-effective-<pin-prefix>` (illustrative only), with manifest name and path
bound to full pin hash. Never use a reserved/vendor namespace. Keep the selected
SKILL.md bytes/frontmatter unchanged; plugin namespace is runtime identity, not
an improver edit. Derive actual last-segment name from validated frontmatter and
installed CLI naming rules, not slug assumption. Refuse ambiguous aliases/name
collisions. Canonical slug remains the product target; native qualified name is
mapped to that target+pin in receipts.

Set skills to the exact complete permitted native skill-name inventory, replacing
ALL aliases of the selected target with its qualified private name. Do not set
all, do not leave skills None, and do not rely on allowed_tools alone. Preserve
other existing authorized skill names. The existing TaskSkillScope brain scan
is not automatically a complete personal/project/parent/added-directory/plugin/
nested native inventory. Init.skills is also insufficient. If a complete source-
bound mapping cannot be established, fail profile admission rather than silently
hiding unrelated skills or allowing a duplicate. Reject a conflicting plugin
namespace/path and revalidate after init and before first model input.

Preserve existing explicit setting_sources and cwd so owner settings, CLAUDE.md,
managed policy and settings hooks remain in force. Append the private plugin only;
never replace configured plugins or disable user/project/local settings. The
body-only profile must prove target relative dependency semantics when loaded
from plugin root. Dynamic skill shell expansion, context:fork, unpinned helpers
or special frontmatter behavior is unsupported until separately covered; do not
rewrite frontmatter to suppress it secretly.

Model-visible discovery exclusion can therefore use a supported primitive while
retaining source loading. Claims should say exactly that: this does not stop the
CLI from scanning hidden skill metadata internally, nor does it hide files from
other tools. An init entry alone is not evidence of actual prompt exclusion.

### Policy and direct-read constraints that remain

1. **Namespaced permission identity.** Adding a new qualified Skill name must not
   evade an existing owner deny/ask on Skill(original-name). Likewise private
   file paths must not evade Read(original-source) deny/ask. The SDK injects
   Skill(qualified-name) allow entries when skills is set. Leaving settings files
   loaded is necessary but is not by itself proof that rules follow aliases and
   relocated files. No public SDK “evaluate original permission without executing”
   API was established in this bounded read. The installed gate must test original
   bare-name, alias, qualified-name, managed and path-specific deny/ask cases.
   If original restriction does not apply, refuse profile; do not add allow or
   silently reimplement the full CLI policy interpreter.
2. **Native Skill and file tools.** Compose an authoritative host PreToolUse guard
   with existing hooks; never overwrite them. Deny canonical/mirror competing
   target reads. Pinned allowed reads return no new allow, allowing original
   evaluation to continue. Redirecting Read with updatedInput is technically
   supported but is not selected as a policy-preserving solution until original
   path restrictions are proven to survive. Generic Grep/Glob/search/attachments/
   added directories and subagent routes need equivalent coverage or refusal.
   Hook string-path checks do not replace descriptor/root identity protection.
3. **Arbitrary shell.** Blocking cat or literal filenames cannot prevent
   python/node/encoded/indirect reads, copies, archive extraction or background
   subprocesses. On native Windows there is no documented built-in OS sandbox to
   enforce exact target exclusion while preserving an unrestricted ordinary Bash
   profile. Blanket removal of Bash/PowerShell/Monitor would change the existing
   surface and is not silently “policy parity.” A profile already lacking general
   execution may be supportable; converting this one is a product/profile change,
   not something an optimistic localhost test can prove away.
4. **Other executable channels.** MCP/hooks/skills with shell preprocessing and
   arbitrary native subagents can read files outside a file-tool guard. Inventory
   must establish trusted fixed behavior or disable admission for that profile;
   adding an effective-skill plugin does not grant a new general host sandbox.
5. **User /name and attached paths.** The skill filter does not block dispatch by
   typed command. Host input must reject/route selected-target native commands
   before the CLI parser sees them; model Skill hook alone is insufficient.
   A narrow initial candidate can refuse native slash-command dispatch while an
   effective pin is active, with explicit supported-profile semantics. Do not
   claim normal command parity or secretly rewrite /target into a different
   permitted namespace. Other command and @file forms require actual coverage.
6. **Resume/content already in history.** Never attach a new effective pin to an
   existing unpinned native session which may contain old body/tool outputs.
   Only a new incarnation can first receive the effective plugin. Resume/fork/
   keepwarm must retain same skills list/plugin bytes/identity/owner policy;
   changed or missing mapping refuses before input. Keeping the immutable file
   does not by itself stop later permission or owner-rule changes.

### Builder ruling and bounded required gate

Replace the earlier broad “unknown selective discovery primitive” blocker with:
**supported discovery candidate found; unrestricted native Windows filesystem and
resource-renaming permission parity are unresolved enforcement blockers.**
Do not build a new executor, Windows filesystem virtualization layer or cloned
policy engine to hide these blockers inside M2. Keep ordinary profile unavailable
unless its actual allowed surfaces admit a complete enforceable boundary.

The next permissible installed localhost experiment, when root releases the
serial native slot, should use the EXISTING ClaudeSDK path and exact source-bound
options with dummy transport/account only. No real-account/model inference.
Its minimum evidence: source-bound explicit initialize.skills; canonical+mirror
and qualified target with distinguishable bodies; unrelated authorized skill
preservation; actual model listing and native Skill exclusions; original owner
Skill/path deny+ask behavior; direct Read/Grep/Glob and indirect shell attempts;
user slash/attachment dispatch; context-fork/special frontmatter rejection;
first session and resume after pointer change; missing mapping before input;
actual delivered bytes/receipts and full close. A failed indirect shell/policy
case leaves profile blocked; narrow positive Read/Skill fixtures never override
it. A gate proving only discovery is useful but must be labeled discovery-only.

Original report's API-runtime/activation/recovery proposal remains unchanged.
Product acceptance still PENDING, no live activation, no M3-M8 expansion.
### Restricted existing profiles and source-default correction

A final focused read of committed ClaudeSDK._options and main callers narrows
what “restricted profile” can mean. **allowed_tools alone is not containment.**
At faa5a221, its truthy branch sets allowed_tools, permission_mode=default and
can_use_tool, but does NOT assign setting_sources=[]. Its comment says filesystem
settings are not loaded; the installed0.2.116 types/defaults do not substantiate
that comment. None preserves CLI defaults; setting a skills list while leaving
sources None actively defaults them to user/project in _apply_skills_defaults.
This can change local-settings behavior. Thus the earlier report/source-map claim
“allowed-tools branch has no filesystem settings” must be read as stated intent,
not verified actual isolation. Do not silently set [] as an effective-skill fix.
For each actual profile, preserve/test its real source policy explicitly.

Existing committed restricted callers are:
- main.py `_workflow_agent_helpers`, around10128-10180: gated workflow supplies
  allowed tools, strict empty MCP, and disallowed_tools Bash/WebFetch/WebSearch/Task
  except explicitly granted native tools. This is a candidate constrained engine
  pattern only when no executable native grants exist. Workflow/agent expansion
  is outside this M2 design; it is not evidence that owner Dashboard native is
  contained. Current0.2.116 actual tool names and additional execution tools still
  need inventory, not reliance on an old four-name deny list.
- main.py `lint`, around12589-12617: READONLY_TOOLS plus strict empty MCP and the
  same four native denies. A read-only lane may be easier to qualify mechanically,
  but /lint is not an existing effective owner task/pin consumer and does not
  satisfy M2 ordinary Dashboard support.
- main.py bot-specific `_claude_sub_*` route around2840-2875: explicit
  BOT_CAM_NATIVE, scoped hub and strict MCP are materially stronger than allow
  rules alone. It is a bot route, outside M2's selected owner DM surface; do not
  borrow bot authority or enable it to claim D2 complete.

No already-enabled ordinary owner Dashboard native profile was established in
this bounded source that both hard-excludes arbitrary execution and preserves all
original native Skill/path deny/ask identities under private-plugin relocation.
Therefore none is declared qualified here. A genuinely pre-existing restricted
profile could qualify WITHOUT weakening policy only if its actual inventory
already denies every general execution/delegation channel, every surviving file
read uses pinned/current-authorized bytes, original Skill/path deny and ask still
apply to candidate loading, and its actual host owner/session binding is in scope.
The existence of `allowed_tools` or a deny-list comment does not satisfy these
conditions. No additional profiles or routing expansion are proposed now.

Normal native baseline remains the existing Javis behavior. “Effective native
profile unavailable” means do not select an overlay for that consumer; it does
not disable or rewrite the owner's ordinary native configuration, tools, settings
or sessions. API D2/E/Q engineering proceeds independently, while full D2 native
acceptance remains explicitly open until a legitimate profile passes its gates.
This is an additive diagnosis/design ruling only; no fixes or probes were run.
