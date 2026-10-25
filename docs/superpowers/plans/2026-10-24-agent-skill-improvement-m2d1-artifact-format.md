# D1 raw role artifact instructions implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the actual isolated role's final-answer artifact boundary explicit
before one new bounded selected-account feasibility of paired views.

**Architecture:** Keep artifact publication and strict schema validation unchanged.
The existing role system prompt describes final response bytes, independent of
untrusted task data. No output repair, Markdown stripping, SDK StructuredOutput,
new tool, retry loop or acceptance override. Host still validates every key,
meaning/source dependency and current authority before publishing any receipt.

**Tech Stack:** Existing OperationProfile/worker/TrialProfile, semantic and
proposer protocols, actual SDK116/CLI309, same CallLedger and encrypted stores.

**Spec:** ../specs/2026-10-22-agent-skill-evidence-improvement-design.md sections
4,7,10,11,13,18,20,23; full Goal M0-M8 and section12 apply.

## Current evidence and impact before edits

Base ed5e1e33 has approved whole/scoped D1 and reader descriptor fix. Exact-head
CI39996033610 runs; do not duplicate/cancel it. Current81/958527ac native proof
is valid for existing source only. New prompt source invalidates that profile,
so no actual native/account query under the changed footprint until qualified.
Same branch/worktree/reserved0.299 draftPR803, main d3d7cb36/0.298.0. Preserve all
previous reports and unrelated original D:/Project checkout.

Actual D1 account evidence90ecc20b: reviewer returned fenced JSON without
findings; parser refused. Baseline had correct arithmetic, fenced JSON plus
commentary, shapeFAIL and accuracyUNKNOWN. No pair/selection/claim existed. Its
actual protected owner objective overrode a contradictory first-row baseline;
do not construct an assumption that candidate must win. Invalid_output is now
an explicit durable refusal and stays so.

Single production change: server/improvement_operation_profile.py,
operation_system_prompt(manifest). Actual caller: OperationProfile -> existing
operation worker -> TrialProfile.options, prompt installation receipt and role
result source hashes. Add clear final-response requirement: artifact itself is
one raw JSON object using the role's supplied output_contract, all required keys
and exact types; no Markdown code fences, headings, preface or commentary.
Uncertainty must use permitted contract values with required evidence, never
invent a source or assert pass. Keep prior owner/protected/source restrictions.
Do not alter input rendering, semantic_output, product parser, policy, prompt
truncation, source authority, event/usage/receipt schema or tools/settings.

Official https://code.claude.com/docs/en/agent-sdk/structured-outputs and installed
SDK116 show output_format introduces StructuredOutput tool/results and retries.
That is not a drop-in change to the current one-fixture-tool profile; defer it.
This unit changes host instructions only and never adds implicit retries.

## Task1 — explicit final raw artifact contract

- [ ] Add focused tests to actual operation_worker test or new role-artifact
  test using actual OperationProfile/operation_system_prompt and closed semantic
  input: exact role/source/owner rules retained, final raw JSON requirement wired
  for improver and semantic reviewer; malformed/fenced/missing-findings products
  still refused by actual semantic_output. Observe RED before production edit.
- [ ] Change only operation_system_prompt. Keep raw result bytes and validators
  exact (AST/source comparison); version1 Trial prompt remains byte-identical.
- [ ] GREEN focused tests; affected operation_worker, operation_results,
  semantic_review and semantic workflow suites sequentially. Include actual
  invalid_output HTTP replay/source-fence cases from approved evidence if any
  code path is affected; reuse unchanged consumer proof only with source/AST.
  Record commands, wall times, source/test/log hashes on one frozen source map.
- [ ] Scoped independent review of new prompt/consumer boundary; retain prior
  reviews, no repeat whole D1. No quality claim from prompt unit tests.
- [ ] Qualify actual final81 footprint using the established20 local-provider
  native tests. Exact source maps before/after, CLI309/hash5441781f/SDK116,
  dummy auth/HOME, owned hidden workers/job drain. Registry update only after
  native evidence, targeted metadata RED/GREEN and scoped registration review.
- [ ] Commit/push verified unit and final-head full CI; no merge before required
  source review/CI, no activation/deployment/restart.

## Task2 — bounded new selected-account feasibility

Only after exact registration/current selected configuration verified, create a
NEW isolated scratch brain/state/key and new persistent event keys. Do not rerun
or overwrite old C/D1 scripts/history. Original failed reports remain immutable.
Synthetic reconciliation case source only, manual candidate explicitly labeled.
Use actual service/TrialRunner/role/calls, no patched adapter/readiness/owner
arbitration. At most one baseline, one semantic review and two fixed tuning arms;
no retries, repeated proposal or holdout exposure. If stage fails, record/refuse
and stop dependent stages. Existing report gate decides keep_base/inconclusive;
no requirement that candidate wins or eligible-final row is manufactured.
Capture current pin/config/runtime, actual call refs, terminal artifacts/checks,
partial usage, unchanged canonical and complete plaintext cleanup. Unknown
reasoning/asset-use/business accuracy remain unknown; human business acceptance
and genuine eligible-final remain open unless separately proven by real evidence.

- [ ] Inspect actual selection/auth status without dumping credentials; confirm
  same Opus5.5/medium/fastfalse/subscription, final registered source/runtime.
- [ ] Prepare run-once script with output-exists guard outside report-overwriting
  exception handler, fixed call count/history and a new scratch test key only.
- [ ] Run once and preserve success/failure and all usage. Never normalize model
  products or claim pilot/live benefit from this technical synthetic scope.
- [ ] Update plan/progress/operator/PR and continue actual D2/E/F/M3-M8.

## Self-review

This is a specific hypothesis from actual format counterevidence, not a pass
requirement or trial-until-win. Prompt alone cannot enforce model behavior; raw
consumer remains authoritative. Real feasibility is the effectiveness check.
No ownership, permissions, model/reasoning, holdout or success criteria change.
The limited unit advances a blocked actual paired pipeline; it does not replace
full production effective task/session views or the rest of the Goal.
