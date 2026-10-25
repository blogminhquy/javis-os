# Narrow proposer guidance adaptation (Goal§15)

Apply after preserving the current D2 unit. Source/reuse decision is recorded in
the incremental Harness² reuse map at commit1cfe254e8d25b15f37048c3730134686abe60335,
prompts Git blob9ccacf23b64ac15b06a1939f26224960f56d757c. Preserve Apache-2.0,
Google copyright and exact source/function/modification provenance when adapting.

Change only existing generation input rendering plus attribution/license files
and focused tests. The real consumer is operation_user_prompt(propose) used by
OperationProfile; repair reuses the unchanged output contract. Do not alter the
store, workspace, runner, usage, case splitting, schemas or execution authority.

Render a compact structured method: locate the earliest failure supported by an
authorized run/trace/source; distinguish execution from domain_process; make a
small patch whose failure_signature/hypothesis/expected_behavior/regression risks
trace to permitted evidence_refs; accept no-change through the existing closed
not_a_target_defect JSON. Reflection distinguishes observed differences from
predicted effects and helped/hurt/no observed effect/confounded, with one rollout
or multiple simultaneous changes confounded. Overall outcome is not semantic/
owner-rule evidence. No new model output fields or hidden evidence are requested.

Tests first: real operation prompt includes trusted method while preserving its
authorized input exactly, existing output kinds/patch validator/UTF-8 offsets and
repair contract; adversarial data stays data, no added source reads or holdout/
private-answer leakage; correct no-change and existing patch still parse, new
upstream output shapes stay rejected. Avoid a literal-sentence-only test. Run
focused protocol tests then impacted improver-input/proposal/profile regression
once; independent delta review and final exact-head full CI remain required.

generation_protocol is already in the native PROFILE_SOURCES closure. Record
before/after source identity; do not reuse historical exact-source qualification.
Live registries remain closed. Fixture tests establish rendering/compatibility,
not model reasoning, causal quality, token saving, account readiness or rollout.
