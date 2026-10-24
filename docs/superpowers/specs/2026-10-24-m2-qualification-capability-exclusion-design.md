# M2 technical capability exclusion — short design

Authority: Goal18, M2 engineering plus committed Claude Opus5.5 handoff. No
M3–M8 expansion, real account/model/business/pilot/canary, deploy or activation.
This is a prerequisite for an explicit account_ready=false technical localhost
qualification path, not a new path that permits execution.

Four ordinary product boundaries currently consume supported=true without
separately rejecting an explicit qualification domain or account_ready=false:
TrialAdmission.admit, OperationExecution.reserve, TrialRunner._run_claimed and
OperationRunner._run_claimed. Current anchored-store result fences stay intact,
but rejection must also occur before ordinary reservation/query consumption.

Approaches: a new shared capability schema would broaden legacy contracts and
require unrelated consumer migration. Four narrow extensions to existing
unsupported-result conditions preserve the established return/abort/settlement
paths. Choose those extensions; do not introduce another validator package,
runtime, ledger, permission or activation field.

In each existing condition, after its current dictionary/type guard, additionally
reject `value.get('account_ready') is False` OR
`value.get('domain') == 'qualification'`. Keep each function's current variable,
exact type/isinstance behavior, supported-is-True check, hash validation, errors,
host/source/grant/lease checks and refund/cleanup semantics. Ordinary capability
maps without these fields remain compatible. Do not coerce False/0/None or infer
account readiness from truthiness. Malformed legacy maps remain refused as before.

Use actual disposable TrialAdmission/OperationExecution/TrialRunner/OperationRunner
owners/stores/calls, seaming only adapter capability output. Start from the same
valid ordinary fixture capability and add false readiness, qualification domain,
or both while leaving supported=true and existing capability_hash untouched.
Before implementation those cases must demonstrate actual reservation or runner
progress beyond the intended boundary; afterwards admission reserves nothing,
and an already claimed runner never executes an adapter/query/start_engine,
retains engine_at=NULL and follows its normal unmarked abort/refund cleanup.
A valid ordinary control proves that no unrelated malformed-hash/source refusal
made the negative cases pass. New ordinary positive output remains engineering
fixture proof, not native/account or business readiness.

Scope: four existing production files plus one focused new test module. No SQL,
native startup/SDK/query environment, candidate registry, upstream vendor or
owner/model/reasoning/guardrail policy change. Existing affected regressions run
once, serially. Changed four native-footprint sources invalidate earlier source
qualification; current profile99 remains UNQUALIFIED/registries closed. No new
source module is added merely to increase the seed count; full installed import
closure and exact final M2 CI/review remain mandatory later gates.

Root call: this is a small, source-derived design with exact predicates and
unchanged interfaces, using the short-design path. Goal3/18 authorize continuous
self-reviewed design/implementation without another routine approval. The later
owned startup3 preflight vertical remains separately planned; no unused permit,
technical capability, native query or qualification registration is delivered here.
