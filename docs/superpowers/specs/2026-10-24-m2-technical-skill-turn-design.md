# M2 technical skill turn and shared-reader binding design

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

Root status: precise narrowed E1 turn binding, same-builder check passed. No
execution, source implementation or activation ran. This supplements
[activation design](2026-10-24-m2-effective-skill-activation-design.md) and
[technical outcome](2026-10-24-m2-technical-skill-outcome-design.md).
Its technical selector/profile/lineage grammar and integration coverage supersede
their earlier ordinary API-turn wording. E2/D2 ordinary API host binding remains
separate required work. No change to native Session identity or production gate.

Read-only source-resolution rawSHA256d2a6e56744989dddef62632c33c141c05aed4c592a698055b3b4012a8bc5e3e9.

# E1 technical turn and consumer binding resolution

Bounded design supplement, 2026-10-24, immutable source `411e8c49`. Resolves the remaining question in `effective-skill-builder-check.md`. No Q1 working files, app imports, tests, native/CLI/model probes, source edits or Git mutations. Only this file is written. Proposed names are contracts, not claims of implementation.

## Choice and corrected E1 claim

Choose a **retained technical in-process turn**, minted by the existing live QualificationSession, into the same TaskSkillScope inventory/pin/read implementation and the actual router/lazy/skill-hub readers. E1 does not enter `TaskSkillTurn.start`, does not claim an ordinary API provider/credential binding, and does not relabel the Session's native pin.

This supersedes the outcome-resolution phrase "actual simulated owner-DM API TaskSkillScope" and the original public design's E1 full-API-turn claim. The precise E1 result is: authentic disposable outcome → shared activation materialization/CAS → retained technical task/step → common skill readers → revoke/close → revert → fresh technical task reads baseline. Coverage is `technical_in_process_skill_read`, alongside the outcome's `authenticated_skill_bytes_only`. It proves shared data-path integration and lifetime fences, not ordinary Dashboard admission, API prompt/tool delivery, a model call, or native skill delivery.

Ordinary owner-DM API binding and its real TaskSkillTurn lifecycle remain necessary E2/D2 work and must appear as an explicit unclosed plan/gate. Full D2 is not quietly reduced to this fixture. E3 native effective-profile availability remains separately open. No future M2F authority is required for the narrower E1 path.

## Immutable facts and consequence

- `QualificationSession.open` (`improvement_qualification_session.py:79`) authenticates a native CLI/SDK/profile/release pin and creates the exact disposable brain/store/principal. `_assert_native_current` (288) compares retained native pin/runtime identities, anchor, paths, registry/current lifetime. E1 preserves those checks and that pin byte-for-byte.
- `TaskSkillTurn.start` (`improvement_task_skill_turn.py:15`) short-circuits unless snapshot enabled, API provider, tools/hub enabled and API key present. It then captures a TaskSkillScope off-loop and binds it on the calling event loop, retaining capture under repeated cancellation. Supplying true values here is not independent evidence of a host-selected API consumer; E1 never does so.
- `TaskSkillScope.open` (`improvement_task_skill_scope.py:142`) requires exact Token, ObserveRuntime and TurnTrace, derives its identity from current turn/trace, and `_live` (200) checks the live binding, exact trace/runtime DB, running task/step, brain, session/channel/version and Dashboard owner fields. Its `current` (304) and `bind` (321) require exact TaskSkillScope type. A wrapper/subclass will not transparently satisfy those consumers.
- `turn_context.make/bind/reset` (96/208/215) create and revoke context bindings; they normalize caller fields, not authenticate a stored chat/registered agent. E1 must not use them to claim an actual Dashboard sender/agent. Copied contexts hold a dead binding after reset.
- `ObserveRuntime.start_turn` (`context_runtime.py:558`) creates real fresh RUNNING task/step rows and returns a TurnTrace; it is best-effort and can return None. `bind_trace/reset_trace` (78/82) bind the trace. `finish` (2007) uses versioned updates and returns success; `close` (2195) closes its owned DB. These provide actual technical task lifetime without an engine, when their results/rows are checked rather than assumed.

## Distinct source lineage and consumer configuration

There are two different identities; neither is converted into the other:

1. **Qualification/authoring lineage:** unchanged native Session pin/release plus actual engine/config/profile captured by the genuine authoring HostContext. They remain exactly authenticated reference facts. Any authoring-config hash already in the plan/outcome/materialization is compared to that frozen source context. It is not a claim that E1 launched that engine or selected an API provider.
2. **Technical consumer:** one host-owned fixed profile named `in-process-skill-read`, version 1. It means same-process, read-only skill metadata/body consumption through the existing readers, no provider/model/credential/engine instance, no HTTP turn key, no resume, no general tool dispatch. Its hash pins the closed descriptor and actual reached scope/router/lazy/skill-handler source closure when E1 lands. No requested provider, api_key, engine_options, callback, tool-enable boolean or external root can configure it.

The qualification-domain selector is a separate exact tagged type, not a product SkillSelectorV1 with invented engine hashes. Proposed `TechnicalSkillSelectorV1` fields are exactly:

```
version=1, kind='technical_skill_consumer', domain='qualification',
run_hash, brain_id, target_id, authoring_context_id,
language='en', consumer_profile_id='in-process-skill-read',
consumer_profile_version=1, consumer_profile_hash
```

Session derives brain/run, the authenticated plan derives target/authoring context, and fixed profile supplies language/config. These fields are not user-selectable. Its canonical hash identifies the technical activation slot. It contains no Dashboard channel, agent/DM identity, provider or account readiness assertion. It cannot match a product selector even if all coincidental hashes equal. Use the existing domain/run-key plus selector-hash unique pointer core; no new pointer table or alternate read algorithm.

Narrow amendment to the *technical* plan/decision/pin grammar from the prior report: `selector` means this exact technical type; its `selector_hash` and `consumer_profile_hash` must join every decision, activation, materialization, turn and receipt. Rename technical plan/pin `engine_config_hash`/`engine_profile_hash` to `source_engine_config_hash`/`source_engine_profile_hash` so these fields explicitly describe the genuine authoring-context reference. If already nested source-context metadata supplies them, retain them only there. Product contracts keep their exact original engine fields and actual owner-DM selector. No union parser silently accepts technical data as product data; parsing is selected by the concrete owner, never caller labels.

The Session creates/registers the fixed consumer descriptor before freezing the technical outcome plan. The producer uses that registered descriptor to derive this selector. Hence no circular reference to a not-yet-created turn or plan hash is necessary. Each later technical turn has a fresh incarnation/task/step but matches this same immutable selector/profile and actual activation generation.

## Exact live turn issuer and scope boundary

Proposed host-only entry on the existing `ActivationOwner.for_qualification(session)`:

```
async with owner.open_technical_skill_turn(plan) as turn:
    # Invoke the bounded real skill metadata/body consumers in this context.
```

It consumes the exact live Session-registered plan, not a JSON descriptor. It can open a baseline scope before apply and after revert, as well as the currently active technical pin; opening a read turn is not itself permission to apply. At open, it authenticates the plan, Session current/root/store/principal, concrete activation owner and fixed consumer descriptor. It verifies current source/context/grant/policy and pointer generation through the same resolver used by the shared activation core. An unavailable/stale technical slot refuses; an explicitly absent/reverted valid slot resolves guarded baseline. No fallback from failed effective authorization to an unguarded canonical read.

The entry creates a private concrete `TechnicalSkillTurn` owned and registered by that Session. The caller cannot construct one from a token, trace, dict or event. No public endpoint exposes this method. Retain it in final Q1/Q2's existing host-operation/child-owner machinery before any await or off-loop runtime/scope setup. Do not invent a separate executor or Session lifetime registry.

The turn owns a fresh `ObserveRuntime` under a unique descendant of `Session.root/state/technical-turns/`, with an internal fixed metadata-only observe policy. It never uses global `get_runtime`, live settings or a caller runtime/settings reader. Runtime creation is inside that retained owner. It calls actual `start_turn` with Session's brain, host-generated session/incarnation id and channel `qualification_skill_consumer`; requires a returned exact TurnTrace and verifies the actual RUNNING task/step rows. It retains the exact runtime object, `_db` identity/path and trace. No row/trace is inserted or synthesized to bypass start_turn.

It binds a genuine `turn_context` Token and CR trace in the consuming task's context with exactly:

- `kenh='qualification_skill_consumer'`, `chat_type='private'`;
- `chat_id=session_id=<host-generated technical incarnation>`;
- `la_chu=False`, `sender_id=''`, `message_id=0`, `agent=None`;
- `provider=''`, no authority_seq, team_gate, job or execution metadata.

These describe an internal technical context, not a real Dashboard user message. Ownership of disposable skill access comes from the registered Session/activation/turn object, not these fields. No API key is read or created. Do not call `turn_context.issue_key` or expose this context over HTTP. General tool dispatch is outside this turn's contract; the bounded harness invokes only the real skill metadata/body handlers through their existing in-process interfaces.

Add one private factory on the **same exact TaskSkillScope class**, e.g. `_open_technical(turn)`. It accepts only this concrete registered owner and extracts assets/principal/runtime/trace/token itself. It never accepts `allow_qualification`, `is_owner`, provider strings or an authorization callback. Factor only the existing inventory/capture/pin/read machinery into a shared private constructor; keep the public ordinary factory strict. Public `TaskSkillScope.open` retains Dashboard-owner predicates and rejects qualification-anchored stores before capture, including forged Dashboard-looking contexts. This adds a domain refusal, not a public exception.

`TaskSkillScope._live` has two owner-specific validations selected by the unforgeable constructor-owned binding: ordinary Dashboard validation unchanged; technical validation requires exact retained Session/turn/profile/selector and the exact technical TC fields above. Both paths then run the same token/context/trace/runtime-object and DB task/step/version/brain checks, file/source/permission checks and common effective-pin logic. A generic `domain='qualification'` dict or existing scope's field mutation cannot select the technical branch. No separate TaskSkillScope subclass, router fork or second asset cache implementation.

Technical scope/event/receipt identity must include domain/run, consumer-profile/selector hash, technical turn incarnation and actual task/step ids, with coverage `technical_in_process_skill_read`. Do not write these as ordinary version-1 Dashboard snapshots. Use the existing encrypted blob/event persistence with an exact technical record version/operation and distinct cold parser. The same `current`, `bind`, metadata/read/cache code works because the object remains exact TaskSkillScope. Private branch validation is repeated before/after slow publication and each consumer read. Copied context after close still sees a bound dead owner and suppresses fallback.

## Lifetime, accounting and failure order

The context manager enters and exits on the same owning asyncio task/context. A close request from Session.close signals that owner; it does not reset another task's ContextVar token. Close immediately revokes the scope/turn's ability to start or complete a fresh read, then drains retained capture/read/blob futures even under repeated cancellation. Binding occurs on the consuming loop only after off-loop capture has settled and current Session/turn authority is rechecked, matching TaskSkillTurn's ownership pattern. A late scope created after cancellation is closed before its future is released.

On exit: revoke/close scope; settle all this turn's in-flight skill reads/publications; reset scope token, CR trace token and TC token in the owning context; finish the actual runtime task via `ObserveRuntime.finish` with honest COMPLETED/FAILED/CANCELLED status and verify terminal task/step state; close this turn's exact runtime DB. Retain an unresolved cleanup owner if any actual future/DB close remains unsettled. A false/failed finish is diagnostic failure, not a successful turn receipt. Session.cleanup refuses until all such owners drain. Other turns/native owners remain retained and are never cleared to make this turn look complete.

Pin/read provenance means the actual skill bytes returned to this technical in-process consumer. It is not API/model input delivery, semantic use or token/cost evidence. Do not call `set_route`, `observe_payload`, `record_usage`, a CallLedger reservation/start/settlement, an API client or native query for this path. No artificial zero-token billing entry. Existing real read receipts/cache/popularity behavior may occur inside the disposable scope and must remain labeled accurately. Optional real Q2 query records stay separate; equality of Session does not join a technical read to native input delivery.

There is no resume/reconstruction from cold technical turn events. New technical turn creates a fresh runtime task/step and validates the current pointer, permissions and descriptor. Prior task pin remains historical. Revert does not mutate an old retained pin's content; the next fresh valid turn resolves baseline. Revocation/source authority change kills live use even if the runtime row is still RUNNING.

## Positive and refusal checks

The following are requirements for implementation tests, not tests run by this design worker.

1. Construct the genuine disposable Session, genuine authoring records and fixed byte-check outcome/decision from the prior resolution. Assert Session native pin/release unchanged. Apply through shared activation core; open the private technical turn; observe real fresh RUNNING runtime task/step and the exact non-Dashboard/no-provider TC context. Exercise actual router metadata, lazy resolution and the existing in-process skill-hub handler against the same scope. Check exact candidate bytes, pin/hash and technical delivery receipt. Close, revert, open a fresh turn, and verify baseline bytes and a fresh task/step. The test may not mock TaskSkillScope.read or substitute a fake hub/router response.
2. Prove the native-pinned Session alone is insufficient: raw Session, arbitrary TC Token/TurnTrace, foreign runtime/store/brain, copied typed plan/turn, forged technical descriptor and cold receipt cannot enter `_open_technical`. Exact registered owner and actual runtime rows are required. Same run with a different selector/profile/authoring-context reference fails.
3. Keep `TaskSkillTurn.start` ordinary negative controls: native provider, missing API key, disabled snapshot, tools disabled and hub disabled short-circuit without capture/scanning. Never turn these GREEN by passing fake API/key values in the E1 positive case. Public TaskSkillScope.open rejects qualification anchor even with Dashboard/owner-looking TC values. Ordinary valid nonqualification controls retain behavior.
4. Change source native pin, expire/close Session, revoke authoring grant, change target/policy/selector/profile hash, replace runtime DB object/path, finish task early or mutate trace/task version during capture/read/publication. Refuse at the actual live fence and suppress unguarded fallback. No caller callback claiming current can repair it.
5. Repeated cancellation before runtime start returns, during scope capture, blob append or hub read keeps futures/owner registered until settled. Late captured scope is closed; copied contexts refuse after close/reset. Session.cleanup refuses while exact technical owner is outstanding. Finish/close failure leaves diagnostic/incomplete provenance, not a successful cleanup receipt.
6. Assert no API/native construction, no credential/config substitution, no HTTP turn key, no model/tool-dispatch invocation, no CallLedger query or token debit. Reading source-context engine hashes is not recorded as a provider route. Product factories/cold readers cannot consume technical events as ordinary scope authority.

## Required remaining ordinary API vertical

E2/D2 must bind activation selection to the real authenticated Dashboard session/message/registered agent, actual selected API engine/config/profile and host-enabled tools/hub/credential state, then exercise `TaskSkillTurn.start` and its real API consumer lifecycle. It must derive those facts from their actual host owners, retain the actual turn token/runtime/trace, and revalidate compatible effective pins before delivery. A supplied mapping or E1 descriptor cannot provide that binding.

That larger host bridge is deliberately not designed or claimed solved here; it is a separately required consumed vertical in the parent's E2/D2 plan. This does not leave E1 ambiguous: E1 now has the exact private technical selector/turn factory and evidence scope above, while its positive claim explicitly excludes the ordinary API gate. Full API/native completion remains open until its concrete host integration and relevant qualification gates pass. Product business acceptance stays fail-closed throughout.
