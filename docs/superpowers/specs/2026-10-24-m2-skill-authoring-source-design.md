# Same-Session E1 authoring source resolution

Root status: proposed prerequisite correction, no source implementation or
technical qualification. The fresh E2 builder found that the earlier E1/E2
designs did not actually specify a concrete retained authoring-source owner.
This supplement supplies that contract and supersedes references to an already
existing owner-DM authoring collector. The fresh E2 same-builder follow-up
returned "nothing important left" for this prerequisite and API design after
the supplement. The original question and dated follow-up remain preserved in
the private builder report (SHA256
`c3e786275c95c14062934520cdd7f4042111629e8f348964eeef7339f10887c2`).
This assesses design readiness, not implementation or qualification.

E1 must implement this same-Session fixed file-profile owner before its outcome
producer or E2 consumes it. It uses real file/ACL/source observations and existing
HostContext/SkillCandidates; supplied successful callbacks are insufficient.
The authoring surface is explicitly technical, separate from authenticated API
DM consumer authority. Native pin/ordinary product gates remain unchanged.
Actual reviewed Q1 host-operation retention is a dependency, not WIP to infer.

No D2 generic direct-target/dependency read, native effective-profile containment,
account, inference or business gate is passed by this design. Both API reports
retain their partial qualification protocol-delivery coverage and required
product-profile blockers. M2 engineering/handoff scope remains Goal section18.

Related: [E1 activation](2026-10-24-m2-effective-skill-activation-design.md),
[technical outcome](2026-10-24-m2-technical-skill-outcome-design.md),
[technical turn](2026-10-24-m2-technical-skill-turn-design.md),
[API binding](2026-10-24-m2-api-effective-binding-design.md), and
[API bootstrap](2026-10-24-m2-api-effective-bootstrap-design.md).

Design only, 2026-10-24. Immutable source basis: `fb2672b485c621e99a0822ab69dacd259c81aae5`. The full `api-effective-builder-check.md` was read. Only committed source/specs were inspected; no Q1 working source/report, imports, tests, native/CLI/API/account/network probes, source changes, Git mutations or helpers. Proposed interfaces are implementation contracts, not existing or tested facilities.

## Decision and correction

The builder identified a real missing implementation prerequisite. Neither SkillCandidates nor QualificationSession currently constructs the required authenticated authoring HostContext. The prior bootstrap's reference to an already specified concrete E1 source owner was too strong.

Add one private retained **QualificationSkillAuthoringSources** composition owned by the exact QualificationSession. It constructs actual HostContextStore and SkillCandidates using existing file capture, canonical-skill, persisted-selection and fixture-source primitives. API bootstrap consumes it after disposable-state initialization and before registering the API consumer or freezing a technical plan. It never accepts a caller HostContextStore plus successful callback dictionaries.

Its actual authoring surface is host-only **qualification-skill-authoring/v1**, a fixed file profile. E1's old minimum-prerequisite phrase “context/grant for the owner DM” is superseded specifically for qualification authoring: this grant belongs to that explicit technical surface in the same Session brain. The API consumer is separately authenticated from its real owner DM through the specified main/ws/job/config path. Its `authoring_context_id` links this actual grant; it does not claim the grant captured the DM's entire production prompt. E1's in-process selector remains separate.

This correction does not broaden DashboardContextCapture/SQLiteContextProjection or relocate `root/assets` to `state/improvement`. Reusing dashboard_host would require different storage and Dashboard/workflow sources and retain its web-surface restriction. A callback asserting completeness or Session-native pin alone would invent source authority. A fixed file profile can instead prove completeness for its own named input set, without claiming Dashboard/native/general-tool prompt completeness.

## Actual source basis

- `server/improvement_trial_context.py`: ContextSource/capture_context perform stable double reads, path/reparse checks, source identities, redaction, exclusions and plan hashing. Its explicit contract delegates surface validation and completeness to the composing host. Use existing capture version 1, already accepted by HostContextStore; do not widen Dashboard version 2.
- `server/improvement_trial_host.py:72`: HostContextStore repeatedly observes targets, selected engine, capture and fixture inventory before grant publication; it preserves context/fixture and target/context exclusion. `_snapshot_binding` and `_snapshot_observe` provide current grant/target/policy/source joins without inventing a trial request.
- `server/improvement_skill_candidates.py:31/86`: SkillCandidates observes canonical bytes, native permissions, exact encrypted baseline, protected state and pack ownership, but does not construct a collector. Keep its actual region/stage/provenance implementation.
- `server/improvement_trial_file_sources.py`: BrainFileFixtures reads actual UTF-8 files, ACL/ancestry/identity/content and rechecks the inventory. Initial metadata selects sources, not outcomes. Preserve exact BrainFileFixtures type: HostContextStore.capture_snapshot requires it.
- `server/improvement_trial_selection.py:320/346/357`: read_selection reads five persisted nonsecret fields. create_pin constructs an ordinary-profile pin; it must not be patched into Session's owned-image pin.
- `server/improvement_qualification_session.py:79/288`: Session supplies actual anchored assets/Principal/run and authenticates retained native pin/runtime/review/lifetime. Keep those objects and the pin unchanged. P1 `_owners` is Guardian-specific; consume the committed Q1 baseline-query design's host-task/pending-proof retention instead of introducing another executor or registry.

## Factory and retained objects

Add the small implementation module `server/improvement_qualification_authoring.py`. It is newly required E1 work, not an existing dependency. Its factory is exposed only through Session:

```
async QualificationSession.open_skill_authoring_sources() -> QualificationSkillAuthoringSources
```

No arguments: no external root, principal, assets, collector, callback, engine map, fixture map, source snapshot, completeness/success boolean or service. The exact live Session calls a private constructor. Retain initialization as a Q1 host operation before filesystem/config/DB work. Register the exact composition only after all source checks and its durable source-contract append succeed. One owner/profile per run; incompatible second initialization refuses. A copied/deserialized owner or partial initialization is unusable.

The owner retains identity-equal Session/principal/assets/store/blobs, concrete SkillCandidates, concrete HostContextStore, a concrete private capture member, exact BrainFileFixtures, selected-engine/target bound-method owners, fixed paths, source-contract record/hash, and observed native permission/incarnation snapshots. Recheck member/class/module identities and Session registration before/after slow I/O; do not rediscover dependencies from globals. This is trusted-process capability discipline, not protection against arbitrary Python memory replacement.

The real constructor receives these dependencies:

```
host = HostContextStore(session.assets,
    context_capture=owner.capture,
    selected_engine=owner.selected_engine,
    target_observer=owner.targets,
    fixture_observer=owner.fixtures)  # exact BrainFileFixtures

authoring = SkillCandidates(session.assets,
    pack_state_dir=session.root / 'state' / 'packs-state')
```

E1 keeps its existing freeze/evaluate signatures taking `authoring`; Session resolves that exact instance to this registered source owner and exact host/context. Another SkillCandidates using the same store is insufficient. API bootstrap consumes this owner rather than rebuilding a host from main.

Private owner entry points:

```
async create_context(*, event_key) -> real HostContextStore public context
assert_context_current(context_id, *, connection=None) -> no authority object
async declare_region(*, context_id, start, end, expected_target_generation,
                     event_key) -> real SkillCandidates result
async stage(*, context_id, patch, event_key) -> real SkillCandidates result
async aclose()  # revoke, drain retained work; no fresh grants
```

The owner generates/retains experiment ID, target/revision, surface and source refs. create_context calls actual `host.create(session.principal, experiment_id, surface, [target_id], source_refs=[fixed_ref], event_key=...)`, without accepting caller surface/selection/fixture parameters. Region/stage use actual SkillCandidates and preserve parser, body bounds, provenance, edit grant and sealed-experiment fences. No product experiment phase, trial success or comparison report is fabricated.

## Owned files and limited coverage

Reserved root becomes Session.root exactly as specified in the API bootstrap. Blobs remain `root/assets`; GoalStore remains `root/state/resonance.sqlite3`. E2 has installed config paths before imports; an E1-only initializer uses the same fixed Session-root selection file without importing main. Paths are fixed by the profile, not supplied in JSON:

| Path | Actual role |
|---|---|
| `root/brain/skills/e1-transition/SKILL.md` | Enabled user-owned canonical fixture skill; variant/target, excluded from common context. |
| `root/brain/qualification/authoring/contract.md` | Required protected common authoring instructions. |
| `root/brain/qualification/authoring/constraints.json` | Required protected fixed profile/body-only/no-dependency/qualification constraints. |
| `root/brain/qualification/fixtures/source.txt` | Nonempty actual engineering fixture inventory member, outside context and target. |
| `root/state/packs-state/` | Actual pack ownership directory; v1 requires empty bounded inventory and checked identity/permissions. |
| `root/state/settings.json` | Actual persisted disposable selection; never copied wholesale into context. |

Preparation creates required files exclusively under the owned root before source registration, with checked nonlinked ancestry. Never overwrite files, heal an absent source during revalidation, relocate assets, or copy live brain/settings/keys. Profile code supplies fixed contract, constraints and fixture-source bytes; hash/check their actual written bytes. Protected documents describe the bounded technical operation and exclusions; they contain neither E1 marker expectations nor target/candidate content. Protected context and fixture content must be distinct, nonempty, UTF-8, redaction-safe and within existing bounds.

The controlled engineering fixture setup writes the canonical baseline to the fixed skill path before opening this owner. That is actual input data, not an observer seam. The owner accepts no SourceSnapshot/hash/raw-byte argument for it: it reads it itself. Require fixed slug, enabled valid frontmatter, user ownership, empty dependency/reference inventory and body-only eligibility. Separate real Sessions may supply win/loss/tie baseline data without choosing checker rules/results. Do not replace target body after source freeze. Invalid content/permissions refuse rather than being repaired.

The capture member creates exactly two required ContextSource entries: refs `qualification-authoring:contract` and `qualification-authoring:constraints`, root Session brain, fixed relative paths above. Before/after real capture_context, observe actual `_root(principal)` and `_authority(root, relative)` for each; require saved native permission projections, identities/hashes and profile bytes. Recheck the whole set after the final read. This adds native permission fencing to the existing byte collector; no invented capture dict. Root/directory/leaf replacement, ACL change, hardlink/reparse or lost access refuses.

Only that concrete collector calls `capture_context(... complete_plan=True, excluded_refs=[target canonical ref, fixture relative ref])` after its exact inventory passes. Completeness means only all protected inputs to qualification-skill-authoring/v1. No request boolean/callback controls it. It neither reads nor claims coverage of chat history/persona/plugins/tools/workflows/coding folders/ambient HOME/global instructions. It cannot admit extra arbitrary protected sources under v1. General file readers remain the required D2 gate.

`revalidate(principal, surface, targets, *, frozen_capture)` reruns the same actual checks/capture and requires equality to frozen_capture. Principal must be identity-equal to Session principal; surface/targets exactly owner-derived. No refresh on drift. Capture remains existing v1 shape; no Dashboard parser change.

## Closed source contract and surface

Before context creation append canonical encrypted `qualification_skill_authoring_sources` using Session assets/events. Exact record fields:

```
version=1, domain='qualification', run_hash, owner_id,
profile_id='qualification-skill-authoring', profile_version=1,
profile_hash, source_closure_hash, brain_id,
selection_hash, source_engine_config_hash, source_engine_profile_hash,
protected_sources, fixture_inventory, pack_state,
target_id, base_revision_id, target_generation, target_source_hash,
target_source_authority_hash
```

owner_id is generated once before construction. protected_sources is exactly the ordered two actual observations `{ref, relative, identity, content_hash, authority_hash}`. authority_hash derives from real `_authority` projection; diagnostics may retain encrypted projection evidence, which never replaces live observation. fixture_inventory is exact real BrainFileFixtures output. pack_state is `{relative:'state/packs-state', identity_hash, authority_hash, entries:[]}` derived from the real empty directory. Target facts come from capture plus SkillCandidates.observe. `source_contract_hash` is the canonical record hash; event contains hash/blob reference. Enforce closed fields/strict scalar types. No key/login data, allow flag or asserted result belongs in the record.

Exact surface passed to host.create:

```
version=1, kind='qualification_skill_authoring', domain='qualification',
run_hash, brain_id, owner_id, profile_id, profile_version,
profile_hash, source_contract_hash
```

All values derive from the registered owner/record. No Dashboard session/channel/owner-boolean/API-provider field. Record finalizes before surface/capture/context, avoiding a hash cycle. HostContext's real grant binds surface/sources/engine/fixtures. Existing E1 context_grant_hash transitively binds this source contract; do not add ad-hoc fields to its closed plan/outcome grammar. Live producers additionally require the registered owner and authenticate the actual source event/blob. Copied/self-rehashed records or an arbitrary surface accepted by general HostContextStore cannot satisfy that registry. Historical replay cannot register a new owner or reactivate a grant.

## Actual native selection; no pin substitution

The owner reads fixed `root/state/settings.json` using existing read_selection/stable selection primitive. E2 uses the exact config path installed by reserved bootstrap; its actual module/path binding is checked there. Initial config must be persisted before source initialization. Native model.main represents retained Session model/reasoning; the API session later uses actual session pinning to select its API provider, leaving those native-main semantics unchanged. E1-only setup creates a real minimal disposable selection file before owner initialization, using actual Session pin values; it does not read/copy live settings or claim a live user's route choice.

Require the actual five-field projection to equal:

```
provider = session._pin['provider'] = 'anthropic-cli'
model = session._pin['model']
reasoning = session._pin['reasoning']
fast = False
auth_mode = 'subscription'
```

Auth mode is persisted selection metadata, not an observed login/account result. No native command/auth status/SDK client/account verifier/inference runs. Session already authenticates its reviewed static runtime/native pin: call unchanged `_assert_native_current` before/after selection/source reads. Require existing ClaudeTrialAdapter closed-shape validation and return a canonical immutable copy of that exact pin from selected_engine. Do not assemble a new pin from five strings, mutate Session._pin, change its profile version or attach API fields.

This corrects earlier bootstrap shorthand suggesting create_pin supplies the E1 authoring pin. At this source, create_pin uses the ordinary global profile. The new owner validates persisted selection against the independently authenticated Session owned-image pin and returns that pin byte-for-byte. Config cannot mint a reviewed Session; Session cannot excuse conflicting persisted selection. `selection_hash` hashes the real five-field projection; source_engine_config_hash is `IM._hash(Session._pin)` and source_engine_profile_hash its actual profile hash.

Stable file observation is required per read. Do not freeze the entire settings-file content/inode: legitimate atomic rewrites and unrelated API config changes are not native-selection drift. Reject semantic selection change, foreign path/parent/root, invalid ancestry, unreadable/ambiguous selection or change during a stable read. E2 independently pins/rechecks relevant API config/credential incarnation. No secret-bearing config enters baseline context.

## Real target and fixture ownership

Initialization reads the canonical target using actual capture_source with the fixed pack directory, brackets it with `_authority`/root checks, and passes the real returned SourceSnapshot/bytes to actual assets.capture. Only setup policy write is real `assets.set_policy` to suggest for this disposable brain with version/CAS. Capture returns genuine target/revision IDs; immediately authenticate through retained SkillCandidates.observe and recheck after publication. No fabricated row/SourceSnapshot/database insertion counts as positive evidence.

`owner.targets(principal, identifiers)` requires exact principal and exactly the registered target ID; loads the actual same-assets row; verifies live kind/ownership/generation/current revision; calls retained SkillCandidates.observe; returns exactly TARGET_FIELDS from the actual row/source. Also require the actual pack directory's empty inventory/identity/permissions. Changed inventory/ownership invalidates v1. Owner checks bracket protected sources/selection/Session. Never refresh target/revision during validation.

Construct exact BrainFileFixtures with this host selection:

```
'brain-file:qualification/fixtures/source.txt': {
  timezone: 'UTC', data_period: 'qualification-fixture-v1',
  cutoff: <UTC ISO timestamp derived once from Session.scope.created_at>,
  schema: 'qualification-authoring-source-v1',
  freshness_policy: 'require_current_version'
}
```

Selection metadata names a real synthetic engineering file, not an independent/business dataset. Inventory hashes/identity/permission ID/version/redaction/sufficiency come only from actual observer reads/ACLs. Freeze that nonempty output. HostContext uses its existing frozen-inventory reread; owner also checks exact fixture object and unchanged initial selection. Keep fixture observer unwrapped/exact-type so capture_snapshot remains genuinely usable if needed. E1 need not manufacture product cases/trials/snapshots merely to obtain an inventory.

Preserve HostContext's existing hash/body overlap checks. Add explicit profile path/inode alias exclusion across protected, target and fixture files; `_authority` rejects hardlinked leaves, but different strings alone are insufficient. No-dependency v1 eligibility must use actual existing skill patch/reference inventory checks. It does not prove generic dependency reads for other skills.

## Current authority, revocation, retained lifetime

assert_context_current is a concrete method, not a callback parameter. Require exact Session registration/member identities; authenticate read_run and source-contract event/blob; verify Session open/deadline/native review/runtime through unchanged Session method; compare actual native selection/profile/source closure; reobserve protected/target/fixture/pack facts.

For its context use actual `_snapshot_binding(connection, principal, experiment_id, fixed_fixture_ref)` to authenticate active grant/policy/target binding, then `_snapshot_observe(principal, binding)` for real source comparisons. Re-read grant generation/status, policy version, target row/revision and source-contract event in the caller's final transaction. Require exact frozen hashes/generations; do not synthesize a trial request/case for live_guard. Recheck after slow decrypt/capture/blob publication and immediately before final commit/return as applicable. E1 freeze/evaluate/issue/shared core and E2 descriptor/turn fences invoke this method alongside their existing CAS/identity checks.

Actual HostContextRecords.revoke or edit-authority revoke, policy off/version change, target/protected/fixture/pack authority drift, changed selection/review/runtime, Session close/expiry or owner close blocks new region/stage/freeze/issue/apply/read. Owner close synchronously revokes its live state; Session close revokes registered children. Live refusal must not depend on a fresh DB revoke write succeeding. An explicit context-revoke operation while open uses real host.revoke with expected generation/event; never edit grant rows directly or claim a durable revocation that was not written.

SkillCandidates checks only part of this contract. Thus facade and every E1 decision/use boundary recheck the retained source owner: stage success alone cannot publish a usable plan/outcome. Keep SkillCandidates concrete and existing checks intact. Revalidate under the real final writer after slow publication. Existing filesystem checks detect drift at observed boundaries; do not claim a filesystem-wide atomic transaction across unrelated processes.

Use final Q1's host-task/pending-proof mechanism (committed baseline-query spec, Proposed host interfaces and lifecycle clarification), never P1 Guardian-only `_owners`. Register operations before first await/to_thread; retain all genuine futures through repeated cancellation; drain actual reads/blob/DB work. Retain the persistent source owner as a child in that same host-owner mechanism. A live reference is not itself an unfinished operation, but cleanup requires the source owner closed and its operations/evidence settled, alongside other API/native owners. Closing cannot claim another thread has drained. Failed append/ambiguous cleanup keeps the exact operation for settlement without recapture or success. Only owning Session removes registration after drain; unrelated Q1/native/API owners remain retained.

The source composition owns no engine, scheduler, model call, native boundary, ledger entry or extra SQL pool. Session owns assets/store and closes them only after all consumers. Existing collectors own short-lived file handles; retained tasks own their completion. Root deletion stays Session.cleanup. Cold history never creates a new live owner.

## Exact initialization/freeze order and hash inputs

1. Consume final committed Q1 retention interface; do not infer it from WIP. Implement this E1 source composition and its actual same-Session vertical before claiming E2 integration.
2. In the previously specified fresh API process, reserve root/install paths before imports, open genuine reviewed Session adopting it, initialize actual main/store/auth/session/runtime owners, and persist native-main selection plus actual loopback API config. No consumer descriptor/plan is frozen yet.
3. Create the physical canonical skill and fixed protected/fixture files; initialize retained owner, real suggest policy/capture/revision and source contract; call actual HostContext.create. Authoring needs no Dashboard collector/workflow SQL; consumer still uses specified real API host owners.
4. Declare actual editable region through SkillCandidates. Join context/edit grants, immutable base, real no-dependency inventory/source contract. Zero candidates must still be staged.
5. Register actual authenticated API descriptor from real host/auth/session/agent/config owners and this registered authoring context. Source-engine fields remain unchanged native authoring pin hashes. Context grant hash transitively binds source-owner/profile/contract hash. No arbitrary callback-host context. Define any previously shorthand descriptor source-authority hash as canonical hash of validated source-contract hash, context grant hash/generation, target source-authority hash and actual API-host authority projection; no caller hash override or optional schema field.
6. Freeze existing E1 v2 plan for that exact API descriptor/selector and current source/context/edit-grant/policy/target/checker profile. Stage afterward. Retain the same four-cell evaluator, decision issuer and shared apply/materialize/CAS. E1 v1 in-process proof instead registers its already specified in-process descriptor and preserves its versioned plan grammar. Both require this live source owner at evaluation/issue/use.

profile_hash pins the fixed file-profile descriptor/paths/content constraints. source_closure_hash pins actual factory/capture/selection/current implementation and reached context/file/asset/candidate/store/record/selection/config semantics. Keep an explicit sorted source-path/raw-hash inventory in encrypted source evidence, not an asserted label. Profile/closure metadata is built from reviewed source, not auto-approved merely because its hash was computed. Add this newly reached authority file and dependencies to the relevant existing source/release inventory mechanisms. A Session must not open under an older reviewed closure that omits this path. Never rewrite an open Session native pin; changed closure requires normal fresh independent review/registration and a new Session.

To make the source-evidence envelope exact without changing the source-contract grammar, persist a closed evidence blob `{version:1, record:<closed record above>, source_inventory:[{path,sha256}], protected_authorities:[{ref,projection}]}`. Its event envelope is `{version:1, run_hash, owner_id, source_contract_hash, evidence_hash, blob_hash}`. Require evidence_hash to hash canonical evidence bytes, blob_hash to be the actual encrypted-blob content reference, source_closure_hash to hash the ordered inventory, and each authority_hash to match the stored projection. The live owner still rereads sources; encrypted historical evidence cannot replace that. Profile rules define ordering/maximums and reject unknown/duplicate paths/refs.

This adds source authentication to existing context/grant lineage, not a new E1 outcome schema, checker, native identity, or product acceptance authority. Stale pre-owner descriptors/plans cannot be upgraded/rehashed in place: create a new genuine Session/context/descriptor/zero-candidate plan and freeze normally. The API descriptor remains a later independent consumer registration; no source record needs its descriptor ID and no circular bootstrap is introduced.

## Focused evidence required from implementation

These are future checks, not tests executed here.

1. Real source positive: physical protected/fixture/skill files and real selection; genuine Session anchor/encrypted assets; actual ACL/source observations/BrainFileFixtures inventory/HostContext grant/SkillCandidates region and staging; freeze then real four-cell evaluation. Recompute record/capture hashes from actual files, retain exact Session pin and all object joins, keep canonical unchanged. No prepared callback output is a positive observer fixture.
2. Profile authority negatives: foreign principal/root/assets/store, copied owner/SkillCandidates/HostContext, arbitrary surface/profile/path/fields, missing/extra protected member, supplied completeness or source-contract mapping refuse. File-profile completeness cannot become Dashboard/API/native prompt coverage.
3. Real drift: change protected content/ACL/incarnation, create hardlink/reparse alias, remove/change fixture or permissions, add pack ownership, change target frontmatter/enable/ownership/references. Refuse without refresh, including during blob publication. Unsupported native ACL observation remains a real gate, not a permissive stub.
4. Selection negatives: persisted main model/reasoning/provider/fast/auth-mode drift, Session pin/review/runtime drift, ordinary-profile replacement or API pin substitution refuse. Unrelated settings rewrite may remain valid when five native fields match; API descriptor separately catches relevant API changes. Assert source setup invokes no CLI/auth/query.
5. Actual revoke/close/expiry during capture/stage/freeze/outcome/API read prevents usable publication. Pending real off-loop file/blob work plus repeated cancellation keeps ownership and blocks cleanup until settled. Preserve other owners. No successful return after late revoke.
6. Forged/replayed evidence: callback-success dict, manual event, self-rehash, foreign Session with equal bytes, forensic/cold context and revoked grant cannot register owner/mint plan. Replay grants historical metadata only. Source drift before freeze cannot trigger self-registration of reviewed code.
7. E2 consumption: actual bootstrap/auth/DM/job/engine loopback named-consumer path uses plan from this source owner and correct context/contract joins. Source-owner success alone is not API delivery. Do not weaken route/credential/native checks to get a positive.

## Remaining gates

Architecture prerequisite is resolved by this distinct concrete E1 source-owner contract. It was absent and must be implemented/checked before API work consumes it. No impossible join requires Dashboard widening, blob relocation, native inference, fabricated callback success or second executor. Reconcile final Q1 retention names only against committed interface when available; required ownership/drain behavior is fixed here.

Actual independently reviewed source registration, installed static runtime availability, platform ACL support, genuine Session opening and positive/refusal tests remain unperformed gates. This report grants no registry entry or proof they pass. If unavailable, retain exact blocker; portable static-observer seams remain fixture-only and cannot stand in for installed positive evidence.

REQUIRED D2 generic direct-target/dependency-read coverage remains OPEN and blocks product effective-profile enablement even if business acceptance later exists. Named-consumer API loopback remains partial `qualification_api_protocol_delivery`, not full D2/readiness. Agent-DM lazy delivery remains unclaimed. Native E3/effective profile, account/native qualification and business acceptance remain unchanged separate gates. This owner issues no product eligibility, inference/semantic improvement or business proof.

Implementation precision: `_authority(root, relative)` requires a regular leaf file, so do not call it with the pack directory as its leaf. The small private pack observer uses the same existing `_incarnation`/`_acl_hash` primitives on each real directory ancestor, requiring directory type and rejecting links/reparse points; records exact root/path/permission identity; enumerates the fixed pack directory with a strict bound and requires zero entries; then repeats lineage/permission/inventory observation after the other reads. It returns only its own actual observations. A supplied `entries=[]` or checking `exists()` alone is insufficient. The source owner also retains/rechecks that exact pack path on SkillCandidates; moving it to a different empty directory cannot repair drift. The ordinary capture_source pack check remains in force independently.

Avoid a validation recursion: the capture/selected-engine/target callbacks call private `owner._assert_sources_current()` (Session registration/lifetime, retained members, record, selection and direct file/pack/fixture observations only). That method never calls HostContext._observe, _snapshot_observe or assert_context_current. `assert_context_current` composes that direct source guard with the actual HostContext row/grant and _snapshot_observe checks. Initialization uses the same private observation primitives before registration, under the retained factory operation; this initializing state cannot issue a context, plan, API descriptor or consumer handle. Only its final successful source-record append and registration enable callbacks used by create_context. No public initializing/bypass flag is introduced.
