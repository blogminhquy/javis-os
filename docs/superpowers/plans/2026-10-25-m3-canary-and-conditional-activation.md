# M3 engineering: canary, owner observation, monitoring and conditional activation

Date 25/10/2026. Base: release 0.314.0 (M2E manual activation, schema 11). Spec sections 13, 14, 15.2, 18, 19, 23 (M3).
Goal section 13 applies: this plan builds and technically verifies the code. A real pilot (12/20/12 cases on
real data, model-backed) and a live canary (7 days and 10 real tasks) need the owner's explicit go-ahead and
are tracked as Phase 2; nothing here claims business value.

## What exists and is reused

- Case sets with tuning/qualification/regression splits, `repeat_policy` feasibility (1) and pilot (2),
  `decision_policy` pinned in the experiment definition, `numeric_gate` (20 qualification families, 12 regression,
  exact sign test with `multiple_tests` correction) in `improvement_comparison_results.aggregate`.
- Owner decisions on trial attempts, semantic review, selection of one candidate, final freeze.
- M2E pointers (`improvement_activations`), read-time resolver, revert, suspend/reconcile.
- Recipes (schema 9/10) and `agent_lessons`.

## Units

### A. Canary allocation (schema 12, add-only)

Table `improvement_canaries(activation_id PK, brain_id, allocation_pct 1..100, salt, started_at, state
canary|promoted|ended, promoted_at, generation)`. An `active` activation with a `canary` row serves the overlay only
to sessions whose bucket `int(sha256(salt + ":" + session_id)) % 100 < allocation_pct`. The bucket depends only on
the session, so a whole conversation is pinned to one arm (spec 14.2). Default allocation 10; the owner may pick
one designated pilot context instead (allocation 100 on a single assistant chat is the M2E behaviour).

### B. Exposure and owner verdict

- `improvement_canary_exposures(activation_id, session_id, message_id, arm canary|control, content_hash, at)`,
  unique per message. Written when a covered skill read happens in the scope of a running canary, for both arms,
  so the control group has the same eligibility (spec 14.2: "nhóm đối chứng cùng eligibility").
- `improvement_canary_verdicts(activation_id, session_id, message_id, verdict pass|fail, reason, actor, at)`:
  explicit owner verdicts only. Emoji reactions stay soft signals (feedback_projector already treats them as
  feelings, not acceptance) and never count.
- Observation summary per canary: days since start, verdict counts per arm, `sufficient = days >= 7 and
  canary verdicts >= 10`; otherwise `insufficient_observation`. A clock-injected test proves the rule; a fake
  clock never counts as a live window.

### C. Monitoring and automatic suspension

- Two `fail` verdicts on independent canary sessions since the start suspend the activation
  (`canary_regression`); the prior compatible version is the canonical skill, so suspension is the revert.
- Existing reconcile reasons keep applying (canonical change, revoked authority, rejected evidence...).
- Soft signals (cost, length, reactions) only surface in the report; they never decide.

### D. Promotion

`promote` requires: sufficient observation, still active, no new fail since the last check, basis re-checked
inside the write transaction (policy, authority, report set, canonical bytes). Owner decision by default.
A canary never becomes active by the window simply ending (spec 13.3).

### E. Conditional activation policy

Base policy modes stay `off|suggest` (no table rebuild). A separate add-only table of owner grants
`improvement_auto_scopes(brain_id, target_id, scope_hash, selector_json, surface 'skill_body', allocation_pct,
granted_by, granted_at, revoked_at, generation)` records "auto_scoped" for one target and one scope. When a final
report for a candidate passes the numeric gate and a live grant exists, the host opens a canary activation with
the granted allocation (never 100% directly) and records `evidence_level=qualified`. Without a grant the owner
gets an `awaiting_apply` card. Revoking the grant stops new auto canaries and leaves owner-accepted ones alone
(spec 18.2).

### F. Lesson linkage

`improvement_lesson_links(lesson_id, brain_id, recipe_id, experiment_id, bundle_hash)` written by the host only.
`agent_lessons` keeps the active text; the link lets the UI label a lesson "đã thử có đối chứng" only while the
linked experiment is completed with a kept activation and the recipe is not revoked.

### G. Pilot report

A report view over the final comparison: every case and repeat, W/L/tie/unknown, the exact p-value with the
declared `multiple_tests`, a Wilson interval for the discordant win rate, coverage, contamination/restart/cancel
markers and the honest conclusion (improved within scope, equivalent, worse, insufficient evidence).

### H. UI

The improvement panel gets: canary allocation on apply, a canary card (arm counts, days, sufficient or not),
owner verdict buttons on listed exposures, promote/revert, the auto-scope grant toggle with an (i) explanation,
and the pilot report. All labels from server state, vi/en, phone width.

## Tests (spec matrix)

S01 CAS on promote/revert; S02 crash between exposure write and verdict; S04 basis change between observation and
promote; S05 a session keeps its arm; S06 suspension when prior is canonical; Q05 p/correction reuse; U01 exposure
writes never double count; T02 a canary never marks production work accepted; UI01 vi/en and stale cards.
Simulated pilot: a synthetic 12/20/12 set through select, final freeze, report, auto canary, verdicts, suspension
and promotion, labelled synthetic.

## Out of scope here (Phase 2, needs the owner)

Real model-backed pilot on business data, live canary window, enabling `auto_scoped` on a real brain.
