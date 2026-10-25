# Actual upstream compose: bounded body-candidate adapter

Goal12–17 and code-first Phase1 apply. Pinned Harness² commit
1cfe254e8d25b15f37048c3730134686abe60335. Preserve upper-domain80ad064c.

## Source and transition decision before implementation

| Source | Reuse | Javis adapter and reason |
|---|---|---|
| core/prompts.py blob9ccacf23b64ac15b06a1939f26224960f56d757c: compose_round,_tidy,_work,_lens,_st,_SurfaceText,ANSWER_FREE,EVIDENCE_BOUNDARY,_KEEP_BASE | Extract actual unchanged definitions, retaining exact AST/source hashes, copyright and Apache2.0. No executor/benchmark import. | Static narrow body surface replaces registry construction for Codex/OpenCode guardrail/plugin surfaces; minimal typed prompt inputs replace annotation-only spec/tree dependencies. Single checkpoint t=k=1 only. |
| aggregate in same blob | Inspected; not selected for this adapter | Hardcodes k baseline rollouts and2k single-rollout candidates. Javis has multiple tuning cases/repeats; compose_round first checkpoint truthfully accepts their grouped evidence without inventing sample counts. |
| core/recursion.py blobdda6b98cd5af100b8941f33cbb079462299c5280: run_parallel415,_run_stage; run_sequential530–559 | Match evidence shape, not copy executor | Upstream runs a NEW composed tree separately. Preserve Javis leases/cancel/ledger/native ownership and independently probe/qualify a new candidate. No second executor/ledger or imported finals-only selection. |
| tests/test_workflow.py blob2b7ebeb1816346f606922816a6f3609c64e8f8cc | Inspected for reusable coverage | No direct compose prompt/adapter assertions; add meaningful Javis fixture/closed-contract tests and verbatim-source provenance checks. |

First functioning slice: exact upstream compose implementation renders a single
checkpoint over a validated baseline and two existing distinct execution/domain
body patches plus explicit tuning projections. Host parser validates each kept/
revised/dropped decision and its exact evidence references, and creates NEW bytes
through the existing UTF8/protected-prefix/reference-inventory body validator.
It may return KEEP_BASE. It neither unions arbitrary prompts nor inherits pass,
semantic approval, source authority, edit grant, quality or qualification.

Use explicit trusted mapping: context/harness is the supplied baseline field,
not a real path/tool grant; INV/DOM are execution/domain_process inputs; upstream
notes map to closed JSON decisions. Public owner contract is distinct from private
checker/holdout answers. This first checkpoint has no prior history or rounds.
No whole library, secret, raw reasoning, external I/O or new permissions.

This slice is an actual upstream-function→renderer→closed JSON→existing patch
validator consumer, exercised with exact byte fixtures. It is NOT yet a native
compose operation, durable authorized candidate publication or executable bundle.
Do not describe it as complete compose integration. Next connect authenticated
host snapshots and existing operation/runtime+ledger with explicit schema migration
and one-compose ownership. Existing authoring/comparison ordinal1/2 caps must not
be bypassed by pretending a composition is a third ordinary proposal. Follow with
new candidate/bundle probe/qualification/regression and public UI; no inherited pass.

Tests first: meaningful missing-module RED, exact extracted-definition provenance,
actual upstream call and checkpoint limits, unchanged authorized input, new combined
UTF8/CRLF bytes with unknown gates, KEEP_BASE, closed decisions/refs/input hashes,
overlap/fabricated evidence/schema/size/secrets/protected-prefix rejection. Run serial
local tests, scoped impacted patch regression, independent review; native footprint
qualification and final-head full CI remain mandatory when consumer is connected.
No actual model/account/business/cost-saving/activation claim.
