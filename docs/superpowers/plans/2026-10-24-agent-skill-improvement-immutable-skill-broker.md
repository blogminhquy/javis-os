# Immutable trial skill read broker

Full M0–M8 Goal section12 applies. Base3dcf1e26/PR803/reserved0.299.0. Native
observations plan UnitB is independent of the still-UNKNOWN loaded-image proof.
Implement the actual narrow reader before SDK/receipt integration; no current
production behavior or qualification claim changes in this component unit.

Impact: new server/improvement_skill_asset_broker.py and focused Python tests.
Reuse _manifest validation and canonical _hash/_json/_frozen. Consume version2
preloaded materialized manifest only. Bind strict trial_id/attempt/input_hash,
requiring input_hash equal canonical manifest hash; copy/freeze all inputs.

SkillAssetBroker(manifest, *, trial_id, attempt, input_hash) exposes read(args)
for exact view_id/view_hash/asset_id/content_hash. Only an exact match may
return the immutable selected bytes. No arbitrary path, canonical filesystem,
connector, grant expansion, fallback or mutable caller reference is consulted.
Wrong/missing/foreign/malformed arguments return a generic miss with no content.
Unbound operation roles/version1 manifests are refused.

Every success has a new unpredictable observation_id and trial/attempt/input/
effective-view/asset hash binding. Preserve an immutable host observation with
exact request, emitted response text/hash and content hash, enabling a later
unique broker-response/native-result join. Repeated/parallel reads have distinct
IDs; callers cannot mutate retained assets or historical observations through
returned objects. Successful read is not native observed_use until correlation
against actual native ToolUseBlock and ToolResultBlock proves the same session.

RED/GREEN focused tests cover exact bytes, foreign view/hash/asset, malformed
extra/path arguments, caller mutation, legacy refusal, input/hash binding and
distinct concurrent IDs. Patch path/connector entry points to prove no external
read. Synthetic broker tests do not attest SDK/native/account/model behavior.
Run tests sequentially, log hashes and independent source review. No changes to
existing fixture-only operation inventory, prompts, receipt versions, all18 gate
or native profile source list in this component-only unit. When made reachable,
add every new module to PROFILE_SOURCES and qualify that complete final boundary.

Self-review: a successful host return proves only the broker read at this layer;
it does not prove the model invoked/consumed it. No FIFO/argument/timing-only
correlation or receipt pass is permitted. Full correlation, v3 receipt and native
qualification remain required integration work under the existing plan.

## Component checkpoint

12RED (missing component),12GREEN0.030s. Independent parent source review
approved; separate12PASS0.703s subprocess on frozen full maps. Sourceb30198f8
and testd8bb8c3e; public397a6aad. Canonical response text/hash and perread random
IDs are host observations only. No native caller/session correlation/receipt
PASS or account qualification. Integration remains under native observations.
