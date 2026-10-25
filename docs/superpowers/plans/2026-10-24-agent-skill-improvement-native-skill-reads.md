# Native skill reads and independent observed-use checks

Full M0–M8 Goal section12 applies. Baseeb588477/PR803/reserved0.299.0. Standalone
SkillAssetBroker is approved, but no native tool/read proof exists. This unit
implements native-observations UnitB; actual client configuration/image proof
remains independent and UNKNOWN until its separate guardian boundary is verified.

## Impact and version boundary

Changing the prompt/tool inventory of an old materialized input would change its
historical expected prompt. Introduce input manifest v3 for newly materialized
v4 view trials, with the same effective_view and strict one-skill fields. Keep
manifest v1/v2 prompt/hash/tool/receipt behavior byte-exact. A new reader accepts
v1/v2/v3; an old reader refuses unsupported v3 rather than interpreting new input
with old policy. Existing JSON/encrypted trace storage remains the transport;
this does not add a parallel ledger or silently migrate historical records.

Components:

- improvement_sandbox: accept v3, keep v1/v2 rendering exact; v3 system prompt
  includes selected asset descriptors and asks for the exact readonly tool read.
  Owner context and public acceptance stay pinned. No hidden answers appear.
- improvement_view_materialization: new linked v4 materializations use v3; asset
  content is still the validated immutable resolved bytes, never a canonical read.
- improvement_skill_asset_broker: accept validated v3 too, retain exact input
  hash binding. Existing v2 standalone behavior remains valid.
- New improvement_skill_asset_proof pure parser/validator: derive native reads
  from exact broker response ID/text/hash plus actual same-session ToolUse ID,
  name/input and matching ToolResult. No FIFO/timing/equal-arguments-only joins.
- improvement_claude.TrialProfile: only bound v3 installations add
  mcp__skill__skill_asset_read alongside the existing fixture tool. Baseline and
  candidate inventories match. Unbound OperationProfile and v1/v2 remain fixture
  only. Capture exact native call input/result content/session plus immutable
  broker observations in encrypted engine events. Missing init/session or native
  completion preserves UNKNOWN; model text and an inline prompt are not proof.
- New receipt v3 for v3 view input: retain existing pins/coverage, add only closed
  asset_read_proofs summaries recomputed from raw observations. Older receipts
  v1/v2 retain their exact accepted field sets and UNKNOWN observed-use behavior.
- improvement_trial_checks: preserve all18 IDs and quality/owner/selection gates.
  v3 tool inventory and side-effect checks recognize only these two tools. Derive
  asset_observed_use from independently validated raw joins and require receipt
  summaries to match. Available/selected/read/understood remain distinct; no
  comprehension claim. Actual reasoning stays UNKNOWN in this unit.
- Shared _inventory/_effects consumers in improvement_operation_checks keep
  their existing two/three-argument signatures and fixture-only defaults.
  Role results and typed role profile tests cover this actual shared boundary.

Every newly reachable module joins improvement_claude.PROFILE_SOURCES in the same
change. Existing972175a2 registration cannot authorize changed execution. No new
selected-account query until the full changed native boundary is qualified and
registered separately. Do not repeat native20 per small edit; freeze the whole
boundary after affected checks and scoped independent review.

## Native result semantics

Keep raw native optional is_error in new telemetry. Do not blindly default a
missing arbitrary trace field to false. Establish documented SDK/protocol
semantics and actual success/error/omission controls. A successful host response
can support derived success only when its unpredictable ID/exact emitted bytes
uniquely join the actual native call/result in this session. Explicit native
error, malformed/foreign/truncated response or absent proof cannot PASS. Older
trace bytes and UNKNOWN coverage stay unchanged. Fixture-only legacy behavior
is not silently normalized by the new asset read.

## Meaningful tests and verification

1. RED/GREEN pure broker/native-correlation tests: valid exact read; parallel
   equal-argument calls delivered in reversed order; duplicate/replayed ID,
   orphan result/call, absent init, foreign session/view/attempt/input, changed
   content/hash, error and truncation. No success without a unique matched read.
2. Actual SDK-option/handler tests on validated real workspace: bound v3 gets
   exactly two readonly tools and returns only pinned bytes, denial has no path
   fallback; v1/v2 and all three operation roles retain their existing inventory.
3. Receipt/checker tests derive the read from real tool handler output plus
   typed SDK native messages. Receipt-only forged pass/changed summary refuses;
   old v1/v2 unknowns and original prompt/hash bytes remain exact. Missing client
   reasoning proof still blocks full18/final selection.
4. Affected sandbox/profile/worker/checker/view-materialization/view-execution
   suites sequentially on frozen source. Reuse unchanged source-qualified reader,
   source/grant/CAS/ledger/recovery evidence unless interfaces actually affect it.
5. Broader scoped independent native-boundary review is justified by this actual
   versioned input/receipt/tool change. Native local-provider qualification must
   exercise actual baseline/candidate asset tools, response correlation and
   denied foreign reads, not just unit-injected SDK objects. Include ordinary
   solver/operation/lifetime isolation proof on the same final footprint.
6. Register after actual proof, final-head CI and preserve actual usage/failed
   attempts. Only then consider one bounded new configured-account pipeline.
   No model swap, deadline increase, automatic retry or forced candidate win.

Self-review: this is an appropriate native read, not a claim that the model
followed/understood the instructions. A broker return alone is insufficient.
Receipt v3 does not turn reasoning/image coverage into PASS. If the model skips
the tool, keep UNKNOWN and baseline; do not retry just to manufacture eligibility.
