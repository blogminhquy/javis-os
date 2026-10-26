# Agent and skill improvement Goal progress

## Checkpoint 26/10/2026: self-learning loop and first real-model measurements

Owner permission in chat 26/10 ("làm cả 3 phần để test hiệu quả"). Branch `claude/self-learning-loop`, PR #834
(0.333.0). The M2 native trial pipeline still cannot compare for real (empty `REVIEWED_RELEASES`, integrity check
`actual_reasoning` never passes), so the loop runs text-only on the selected engine instead.

- Built: `server/improvement_loop.py` (Harness² sequential recursion with the baseline rule, interleaved sealed
  pairs, regression gate), `server/improvement_loop_runs.py` (owner-started runs, body-only, Apply on "helped"
  over unchanged bytes, recovery, cancel), Studio section, `tools/self_learning_pilot.py`.
- Measured with real model calls (claude-opus-5-5, effort medium, Max plan, 410 calls, about 21 minutes, about
  6.4 USD equivalent) on synthetic shop-reconciliation fixtures
  ([evidence](../evidence/2026-10-26-self-learning-pilots.json)):
  pilot 1 inconclusive (p 0.0625, pass 37.5% -> 68.8%), pilot 2 helped by the sign test but 2 regressions so
  refused by the gate (pass 50% -> 87.5%), pilot 3 helped with no regression (p 0.0002, pass 45.8% -> 100%).
- Not shown: value on the owner's real skills and data, other engines, more than one task; round 2 did not beat
  round 1; learned skill quality varies between runs, which the regression gate and fresh sealed sets handle.

## Checkpoint Claude Opus 5.5, 26/10/2026: M0 to M8 engineering complete

Every milestone M0 to M8 has its engineering scope built, reviewed independently, natively re-qualified where the
store footprint changed (CLI 2.1.310, 20/20 each), merged on green CI and published (Docker green), except M8 which
ships with #831. Four kinds of evidence are kept apart:

- **Implemented and technically tested** (fixtures, localhost fakes, synthetic arms): all milestones, see the table.
- **Tested with real models:** none in this Goal phase. Native enforcement qualification uses dummy auth and
  localhost providers; it proves isolation, not quality.
- **Proven business value:** none claimed. Every applied improvement is labelled `manual_trial`.
- **Released:** 0.314.0 (M2), 0.316.0 (M3), 0.320.0 (M4), 0.323.0 (M5), 0.325.0 (M6), 0.327.0 (M7), 0.330.0 (M8,
  pending merge). VPS has not pulled any of them.

Blocked on the owner (Phase 2, Goal section 13), not on engineering: real feasibility and pilots on a chosen business
task (12/20/12 cases, owner scoring), a live canary (7 days and 10 real tasks), real engine smoke per adapter, the
API-engine trial adapter and native CLI routing measurement (need real runs), an agent pilot and agent canary, real
combined/ablation arms for bundles, a Team trial runner and Team business comparison, the self-running V4 loop
(needs `trial`/`auto_scoped` policy), executable helpers (needs the owner's grant for the executable kind), and any
activation on a real brain.

## Checkpoint Claude Opus 5.5, 25/10/2026

Owner re-issued the full M0–M8 Goal in a Claude Code session (Goal section 19); section 18
narrowing is history. Worktree `D:/Project/Javis-OS/.claude/worktrees/javis-agent-skill-improvement-3dc1ea`,
pushed to `codex/agent-skill-improvement-m2d1` (PR #803, retitled 0.314.0). The Codex worktree
`C:/Users/admin/.codex/worktrees/agent-skill-improvement-m2a` is untouched (two untracked WIP files left there).

Done in this session:
- Merged origin/main 0.312.0 into the M2D1 branch (`44ee0349`): 10 conflicts, branch logic kept for
  task-scope skill reads, i18n and script tags unioned, route table regenerated. Version 0.314.0 reserved (`b9a4fe23`).
- M2E manual activation (`a3359bff`): schema 11 `improvement_activations`, apply/revert/reconcile,
  read-time resolver in lazy router, in-process `javis_use_skill` and task scope; CLI hub requests and
  non-DM channels keep canonical. API `GET/POST /improvement-activations`, `POST .../{id}/revert`.
  Studio candidate panel: apply block and applied list with Revert. Ops doc `docs/dev/improvement-manual-apply.md`.
- M2F simulated feasibility (`a3359bff`): `test_improvement_feasibility_simulated.py`, four labelled
  synthetic scenarios (win, tie, required loss, unknown) through actual plans/reports/selection/apply.

| Milestone | Technical | Business evidence | Rollout |
|---|---|---|---|
| M0, M1, M2A–C | Released 0.287–0.296 (reused) | None claimed | Suggest-only |
| M2 (D1 integrated, E manual apply, F simulated feasibility) | **Released 0.314.0** (`f3348f04`, #803): full CI green, 2 independent reviews fixed, native profile re-qualified on CLI 2.1.310 (20/20), Docker publish green | None; real feasibility PENDING | Manual, API engines, assistant chat only |
| M3 (canary, owner verdicts, monitoring, promotion, grants, pilot conclusion) | **Released 0.316.0** (`b7c81dc7`, #822): CI green, review 2 important + 7 minor fixed, native re-qualified (20/20), Docker green | None; live canary and pilot PENDING | Off until the owner applies |
| M4 (routing evaluator, description overlay for the main chat, telemetry, UI) | **Released 0.320.0** (`e1d57392`, #823): CI green, review fixed, native re-qualified (20/20). Open: API-engine trial adapter (spec 10.3), native CLI routing measurement, hub `javis_use_skill` description still canonical | None; real engine smoke PENDING | Main chat, API engines, off until the owner applies |
| M5 (agent procedure overlay, surfaces dm/team/kanban/workflow, session pin, owner-rule drift, learn/review staging, lesson linkage, UI) | **Released 0.323.0** (`22ef0375`, #825): CI green, review 4 important + 6 minor fixed, native re-qualified (20/20) | None; agent pilot and agent canary PENDING (owner) | Off until the owner applies |
| M6 (agent-skill bundle: validator, atomic pointer, all-or-nothing read gate, recovery, attribution labels, UI) | **Released 0.325.0** (`485ad69f`, #828): CI green, review 1 critical + 7 important fixed, native re-qualified (20/20). Not built: executable helpers in the sandbox (owner grant for the executable kind), skill split/merge with alias, real ablation arms and a bundle qualification | None; real agent-only/skill-only arms PENDING | Off until the owner applies |
| M7 (Team trial pins and comparison T01, scoped reports T02, untested recipe transfer, API) | **Released 0.327.0** (`409219ad`, #830): CI green, review 1 critical + 5 important fixed, native re-qualified (20/20). Not built: a real Team trial runner, per-step artifact handoff, aggregate trial acceptance, plan/source pinning, lesson freezing during arms, UI | None; a Team business comparison PENDING (owner, real runs) | API only |
| M8 (source-gated need ranking, bounded refinement ledger, filtered export/import, pause every improvement, UI button) | Ready on #831 (0.330.0): review 1 critical + 4 important fixed, native re-qualified (20/20), CI pending at this commit. Not built: the self-running V4 loop (needs model runs and trial/auto_scoped policy), consolidation, automatic compose re-check, export/import UI, resume after pause | None | Pause button live; rest API/library |

Blocked on owner, not engineering: any model-backed feasibility/pilot (needs explicit permission to
run the selected Claude subscription engine), live canary (7 days and 10 real tasks), activation on a
real brain. Next: CI green and review fixes, merge 0.314.0, then M3 engineering.


## Current Q1 checkpoint — source component closed, installed gate open

Source622332e6 closes consumed baseline5 source after7316implementation,
8504fix1 and622332fix2. Scoped reviewI1/I2/I3 and newI4 allADDRESSED,0open
Critical/Important. InitialWindows62PASS; fix1fourteenexecutions/twelve selectors
withproductionidentical/test-only rechecks disclosed; fix2sevenPASSonexact
committedbytes.175/164/64rawslowdiagnostics retained forfinalreview,0warnings.
InitialLinux40090227041failure24pass37skip1error preserved; affectedfix1Linux
40091515738ninePASS andfinalsource40092465143fourPASS0skip. No fullCIclaim.

[Component proof](../evidence/2026-10-24-m2-owned-baseline-query.json)
SHA1bc070983ab57e4c3b39394bf058c7a7c6f6376d894619fc41b2637cd4f2727b.
Rootverified132indexedfiles/14currentpins/reportprefixes/97cleanupreceipts;
12:06:38UTC0samebirth/nativeprocesses,1unrelatedPIDreuse preserved,13workspace
witnessesgone/same2Oct23jh2dirs untouched. Workerterminal/serialslotreleased.
Privateignoredhistory/helpers/diagnosticsremainlocal; no force-add/keyblobcopy.

Q2view4/operation2 and ordinary markerfences next, afteractual622interface
reconciliation/plan. E1/E2source-owner/API/bootstrap designs buildercheckedonly;
no Eimplementation. MandatoryfinalstableinstalledCLI/SDKlocalhost qualification,
genericD2direct-read/nativeprofile,E/F,fullrequiredCI/wholebranch/integration/
finalhandoff OPEN. Business/livePENDING; no fullQ1native/M2/Goalcompletion.
Earlier fix1-active/design-next wording below is historical; do not restart.

## Owner scope override24/10 — finish M2 engineering and Claude handoff

Direct owner decision from “Xác định bước harness2 tốn thời gian” supersedes
all older full M0–M8/Phase2 completion and continuation instructions below.
Current Goal stays ACTIVE until M2A–F/D1/D2 engineering and committed/integrated
handoff pass their actual technical source/runtime/qualification/CI/review gates.
No new Goal, M3–M8 work or actual account/model/business/pilot/canary runs.
Business/live acceptance is PENDING and cannot be inferred from simulations.
See [Goal18](../AGENT-SKILL-IMPROVEMENT-GOAL.md#18-chủ-thu-hẹp-goal-tới-m2-engineering-và-yêu-cầu-bàn-giao--24102026)
and [initial handoff](../../handoffs/claude-opus-5-5/HANDOFF.md).

M0/M1 and M2A–C are reused; D1/D2/E/F remain open pending actual impact
assessment. Six-path recipe-source Task1 was safely closed and
preserved with scoped evidence, not treated as M2 completion. Undispatched
destination schema11/permission/retrieval and further Library/orchestration
expansion move to Claude backlog unless a concrete M2 consistency prerequisite
is established. Existing forward compose/Library/archive code/evidence remains.
Initial handoff snapshot is explicitly provisional; final M2 gate/cleanup/CI/
review/PR/version state must be updated before Goal completion.

## M2 owned preflight — component source gate closed, query vertical next

Sources bee28e3e/faa5a221/0549380e, immutable proof
[2026-10-24-m2-owned-technical-preflight.json](../evidence/2026-10-24-m2-owned-technical-preflight.json)
SHA52b482e0a894e75d4fdc29486abbae3d4a830344552bd9935dda0f4fad2f8827. Original frozen Windows62PASS+1symlinkskip; portability
selector1PASS; exact-sourceLinux26PASS/37platformskip. Initial scopedAstra review
I1 finalthread→returnrace fixed with deterministic3RED→8focusedWindowsPASS,
fix-sourceLinux3PASS/5Windows skip; scoped6.1rereview I1ADDRESSED0newbreakage.
Rootverified93+15+25receipts/reportprefixes/12committedpins/zeroownedprocesses.
No63suitererun, warning suppression or historyrewrite; retainP1M1noise/P1M2interim
serialdeviation for finalwholebranch. Final/fixruns serialized. Same2Oct23dirs
untouched; slotreleased. SelectedCLI/SDKClient notrun, bothmapsclosed/native
UNQUALIFIED. Q1baseline5designbuilderapproved; nextplan/officialbrief, thenQ2
view4/op2 and mandatoryfinalstableinstalledlocalhost qualification. D2/E/F,
fullfinalCI/review/integration/handoff remainOPEN; business/livePENDING.

## M2 capability exclusion — scoped gate closed, owned preflight next

Source d0d5b27c adds only exact false-account/domain qualification rejection at
4consumed product checks, preserves old type/isinstance/hash/authority/settlement.
Real-boundary new8methods/24fixtureexercises: cleanRED12intended failures;
finalWindows13PASS/0skip and earlyLinux40083817343/job120842572439 exact5pins
13PASS/0skip. Scoped fresh6.1/high specPASS/qualityApproved0Critical/0Important/
1MinorM1. Proof2026-10-24-m2-qualification-capability-exclusion.json
SHAac258798bd7cf5221bbf9c80fbd0d218cea3e3225120c0ef811122562d2d23b7.
Root independently checked87raw artifacts/committed LF pins/zeroownedprocesses.
Initial fixture failures and superseded freeze retained; new-test cleanup repair
refrozen before09, unchanged-source existing selectors retained with exactpins.
M1: async fixture slow-task noise17Windows09/14Linux;1existingWindowsoperation
selector diagnostic. Report-only counting correction complete, no raw/source/
test/rerun/suppression change; finalwholebranch musttriage residual timing noise.
Slotreleased, native99UNQUALIFIED/mapsclosed, taskremote4ba9624a unchanged;
only ownedCIreff611065a pushed. Not fullfinalCI/native/account/M2 acceptance.

Next actual Session-owned startup3 preflight designb32ce5db/plan519b366b has
fresh Astra/high builder nothingimportantleft; officialbrief/preflight prepared.
P1 notyetimplemented/qualified. Query/accounting/typedpublisher/coldcleanup then
D2/E/F/finalCI/review/integration/handoff remainOPEN. Owner delegated pilot
choice: reconciliation primary/document processing secondary/Pythonbugfix-tests
technicalcontrol, selectiononly; no livepilot underGoal18.

## Preserved recipe-source unit — scoped engineering closed under new scope

M2 regression follow-up21a5c0b1 changes only the2stale future9 fixture assignments
to actualSCHEMA_VERSION+1. Refusal/no-backup/no-native/history asserts unchanged;
actual2GREEN, source-spec compliant/qualityApproved0Critical/Important/1Minor.
T1-R1 freeze-order limitation retained (post-GREEN pins, no pre-run timestamp
claim). Proof2026-10-24-m2-future-schema-controls.json
SHA74a92878248c7a22f3d49e13b06a7c57c88f88688406daf1760a5d02569cf6fa.
Production/native unchanged99UNQUALIFIED, slotreleased; fullM2gates stillOPEN.

Source269d3892 adds actual retained source observation after legitimate skill
revision while old execution revalidate remains exact; current native target
ACL/lineage, fixture/rule/engine/source-grant/SQL and callback identity are fenced.
Historical archive output only shares the exact existing owner-rule hash.
Root audited6frozen/committed LF paths and69raw indexed artifacts. Windows43run:
42pass/1honest Windows directory-mode skip. Exact6pin earlyLinux40081705134,
job120836433669,43PASS/0skip; full83144byte log SHA
92228619315755f6843c083a761fa1bd37413d26ac52f32ac5f31714b8a29335.
Fresh scoped specPASS/qualityApproved,0Critical/Important/Minor. Root resolved
three evidence limitations against freeze/log/cleanup/static import-discovery
and Linux artifacts. Two punycode/one Node action-runtime notices retained
separately; no test ResourceWarning/task/timing diagnostics or suppression.
Public2026-10-24-recipe-source-observer.json SHA
a0ec009bb3eab3e53756cd37e560429f7f7dc8107de99760b4b6045a9fe43cf9.

PROFILE99 stays UNQUALIFIED/registriesclosed; static import closure is distinct
from current installed/runtime qualification. Task1 terminal audit/serial slot
released, no owned test process/temp/scratch remains;36preexisting Oct22 roots
untouched. Only owned earlyCI ref pushed, taskPRremote stays4ba9624a. Destination
Tasks2/3 remain unimplemented/backlog by owner decision. Continue M2D1/D2/E/F
engineering closeout and handoff, no further Library/orchestration expansion,
no model/account/business/pilot/canary. Final M2 CI/wholebranch review/integration
and resource audit remain mandatory; GoalACTIVE under Goal18.

## Current view-backed recipe archive — scoped engineering approved

Commitbc1a3a68 adds the trigger-only schema10 overlay over exact historical9,
preserving encrypted rows/tombstones/history, authenticated backup/rollback and
old9 cold reads. Actual ordinary and typed3 view Trial/Call/result/trace owners
now supply complete archive refs; all nine request pins and historical view
dependencies are fenced. The new source-ordering RED was fixed by checking the
actual grant/current-target metadata before binding decryption; the late-callback
RED was fixed with final comparison-scoped SQL fences. Earlier immutable Task1
proof is retained as historical evidence, not rewritten to cover these fixes.

Local64PASS on13frozen LF paths; Linux40078670232/job120827431984 exact13pins
76PASS across5modules, full108397byte log retained/SHA8cf4ae4da77d50b4ccb70404ebd0d4b6d07563164f7d604520437a7b45a5fdd0.
Fresh independent specPASS/qualityApproved,0Critical/0Important/1Minor. Minor
recipe-archive-authority/Task2/T2-R1 retains43local/42Linux asyncio timing
diagnostics as final test-hygiene follow-up; ResourceWarnings0/task-leaks0, no
suppression. One CI action-runtime deprecation notice is retained separately.
Checkpoint2026-10-24-recipe-archive-views.json
SHAd632b12330bce64cdb4537f6963d6c2644a6065d8a2cb928f8d1aeedd7fa4196.

PROFILE_SOURCES98 remains UNQUALIFIED/registriesclosed; protected309 proof and
VERSION0.299.0 unchanged. Both tasks in recipe-archive-authority are scoped
complete. Next actual destination grants/consent/max3 ranking, historical source
freshness, owned upstream Library lifecycle/recovery and downstream native/
candidate/view/Trial/apply/lesson consumers before orchestration comparison.
FullGoal ACTIVE; isolated grades/GC/operator reachability, final full-task-head
CI/wholebranch review and all Phase2 real trials remain open. The two preexisting
future9 fixtures and deferred minors remain on the final-review ledger. Only the
owned early-CI ref was pushed; task PR remote stays4ba9624a. No model/account,
activation, deploy/restart, real-brain migration or physical erasure performed.

## Encrypted source recipe authoring — scoped engineering approved

Commitcbbbdacd plus acceptance-onlyaa1e0732 implement actual closed source-side
archive capture/NO_ENTRY over existing candidate/preparation/Trial/Comparison
owners, encrypted manifests/exact refs/original evidence lifetime/final CAS, and
cold metadata/revoke/supersede. Typed3 resolves original composition reports;
parent observations confer no candidate3 outcome. Grades stay untested/confounded,
transfer unverified/businessfalse. Shared preparation extraction preserves actual
original-dbdec proposer bytes/events/hashes including recipes=[].

Local archive27v1 + affected cleanup6v2/records11/improver10/proposals2/preparation2
passed; six owned async-fixture cleanup warnings were diagnosed/fixed explicitly,
not suppressed. Initial independent review ImportantT1-R1 required the negative
conflicting-pin case; actual reevaluation/report/corrupt-catalog acceptance3PASS,
no production delta or invented RED. Narrow re-review ADDRESSED/no new findings,
spec/qualityPASS, executionnone. Early Linux40074394806 exactv2pins48PASS and
40075062683 exactv3pinsfocused3PASS, both ResourceWarnings0. All seven committed
raw pins, complete logs/reports/reviews and terminal process release reconciled.
Checkpoint2026-10-24-recipe-archive-authoring.json
SHAb19e63eb1f6a5401c7386ad265c89744ad64d7ae80bc4023d70b2f4dd0fa0745.

PROFILE_SOURCES97 UNQUALIFIED/registriesclosed; protected309 proof unchanged.
Actual v4 refs remain intact but schema9 refuses publication atomically. Mandatory
Task2 in2026-10-24-recipe-archive-authority.md now implements trigger-only10 and
actual ordinary/typed3 view-backed archive acceptance with old9 cold compatibility.
Then destination consent/max3/owned plaintext crash recovery and actual downstream
native/candidate/view/Trial/apply/lesson dependencies; physical GC/isolated grades,
full M0–M8/finaltaskCI/wholebranchreview/Phase2 remain open. No real model/account,
activation, deploy/restart or real-brain migration performed. Task PR remote stays
4ba9624a; only owned early-CI branches pushed. No orchestration comparison yet.

## Recipe archive schema9 — scoped engineering approved after R1 repair

Commitsefef01c2/6d677d71 add a backed-up additive archive migration in the existing
DB: immutable recipe/trial-reference metadata and monotone availability tombstones.
Official8 validates before backup; no compose rebuild/history/ciphertext/lease
rewrite. Existing1–7 chain and known8 cold reads remain;9 validates exact guards.
Historical target capture and protected owner-rule aggregate are distinct pins.
No raw recipe text, destination consent or plaintext/native consumer is enabled.

Real self-review REDs closed REPLACE history/tombstone resets and case-insensitive
namespace collisions. Independent review found ImportantR1: SQLite NUL bypassed
exact64 digest checks. Clean actual five-failure RED, shared explicit NUL guard,
targeted GREEN and17case final pass; narrowed re-review ADDRESSED/no new findings,
all7stablev3pins/no reviewer execution. Local28PASS includes explicitly reused
unchanged compose6; other17archive+5selected checks run on correctedv3. Early
Linux40071193085/job120804788438 SUCCESS exact7pins23PASS (17archive+6compose),
not final task-head fullCI. Root reconciled raw/Git/log/review/Linux/fixture pins.
Public2026-10-24-recipe-archive-schema.json SHA29db52f3f7f56a07915075a16ad780b18d08066ca8704a42a2255102b82a0712.

PROFILE96 rawdbd31ee091efa14b98f632460ee4f4376e70b5ed9f49f9d3716f025040ca566c
UNQUALIFIED; registries closed/actual309 proof untouched. Next actual encrypted
archive authoring/source/trace/shorterTTL controls, explicit destination grants,
owned plaintext recovery and improver/Operation/candidate/view/Trial/apply/lesson
propagation. Logical erased metadata is not physical erasure/GC. Full M0–M8 Goal,
same-pipeline dummy/native/final/fullCI/review and all Phase2 gates remain open;
no actual account/model query, real-brain migration, activation, deploy or restart.

## Actual Harness² Library snapshot — scoped engineering approved

Commit9e098a52 runs actual pinned Library/add/index/tree/retain/forget inside an
owned private procedure-only snapshot. Twenty extracted definitions have exact
source/AST provenance; three documented tree boundary-line adaptations preserve
strict UTF8, Windows paths and procedure newlines. Maximum3 entries, NO_ENTRY,
negative/confounded verdicts, serialized lifetime, mutation poison and honest
cleanup remain explicit. Returned authority is not_checked; no product consumer.

Windows32run/31pass/1explicitPOSIXskip includes actual junction sentinel; early
Linux40069793207/job120800563778 SUCCESS on the exact7rawpins,26run/25pass/
1explicitWindowsskip includes actual POSIX symlink. Fresh independent static
spec/quality review approved,0findings/no execution. Root reconciled source/
committed/log/review/Linux pins and targeted RED disclosures. Public checkpoint
2026-10-24-harness2-library-snapshot.json SHA0fc8b025b27af47068f4d9ddc86ee7c26f87c4046e136d7d08027595a9584603.

PROFILE95 remains7f7f77da63c0814fb08e55f58849899de0786023c0feb977b81e0778b2573044
UNQUALIFIED; actual309 test untouched. Next: canonical encrypted recipe authority,
source availability/retention/revoke, separately scoped retrieval consent and
owned crash recovery, then actual improver/Operation/candidate/view/Trial/apply
dependency propagation. Orchestration comparison follows functioning integration.
Full M0–M8 Goal, final exact-head full CI/review and all Phase2 gates remain open;
no real model/account query, activation, restart or measured value claim.

## Compose owner panel and recorded outcomes — scoped engineering approved

Commits5490cde6/95790edb add the actual mounted Studio owner flow and bounded
cold compose-outcomes. Open/reload GET only; preview/consent/run/revoke explicit;
generation types separate; old budget2 immutable; reserve3 only at create. A
recorded interrupted/invalid/native-incomplete compose consumes scope even without
publication. New bytes retain their own exact diff/semantic/dependency/native/
Trial/tuning/final gates. Unknown readiness/business eligibility is not upgraded.

Fresh independent static review found three P2 UI recovery defects: older reload
restored active consent, acknowledged actions stayed disabled after manual reload,
and definitely rejected create refs remained cached. All reproduced RED; scoped
fix/re-review ADDRESSED3/no new Important,12stablev2pins/no reviewer execution.
Latest snapshot/write epochs and bounded acknowledgment reconciliation preserve
revocation; only first definite pre-create400/403 permits corrected intent, while
uncertain/admitted/runtime requests retain exact event/payload and never resample.

Local14Python cases plus info-tip, both actual controller suites, i18n/two syntax
checks; JS-only fix adds10recovery/retention controls and reuses unchanged backend
proof. Early isolated Linux40068923965/job120797950847 SUCCESS, same12rawpins,
14Python plus those controller/i18n/info/syntax checks; snapshotd11365108d7a3fbc1fd8f644880584247ab2919e.
Root real-browser vi/en desktop walkthrough used labelled synthetic metadata;
actual panel mount, separate steps/KEEP_BASE/close verified, helper/tab cleaned.
This is no account/model/native proof. Raw warnings/diagnostics remain recorded.
Public checkpoint2026-10-24-compose-owner-panel.json SHA06224f4b71acf3a4382505c8500f77709ffc9489b18451fa809596e7cdc5c8c7.

PROFILE95 raw7f7f77da63c0814fb08e55f58849899de0786023c0feb977b81e0778b2573044 is UNQUALIFIED; actual309 proof untouched. MinorT2-R4
ambiguous candidate option labels andT2-R5 existing evidence warning noise remain
explicit deferred final-review items. Next bounded plan: actual Harness² Library
inside an owned private snapshot, then canonical encrypted recipe permission/
retention/retrieval and actual improver/candidate/view propagation before any
orchestration comparison. No library integration/readiness claimed from the plan.
Full M0–M8 Goal active; same-pipeline dummy/native, qualified final, remaining code,
final exact task-head full CI/fresh whole-branch review and all Phase2 actual model/
business pilot/canary/specifically authorized rollout remain open.

## Owned compose controls and cold history — scoped backend approved

Backend67dfb662 connects the existing concrete ComposerService/shared execution/
tasks to explicit owner preview/authorize/run/revoke. Preview exposes current
references only. Grant generation and saved experiment generation remain distinct;
budget3 is not consent. Scope/current/product/native guards and separate checks
for new bytes remain mandatory; old public/event history stays exact.

Stop resolves authorization-scoped compose ownership and drains it; close rolls
back late consent even after insertion during final source revalidation. Actual
readonly metadata and saved completed/start/current-consent HTTP replay precede
service construction. Active same-event HTTP retries join the existing owner to
the final result; orphaned starts never redispatch. Known revocation authenticates
readonly scope before using the existing same-store writer, works off/stopped and
never constructs host/native. That ordinary writer may initialize its existing
base GoalStore schema; no universal migration-free write claim is made.

Windows86PASS/13modules (24focused+62impact), early isolated Linux67PASS/9scripts
40066405520/job120790490552/exact9rawpins, snapshot51cdc17d0e6903de9b787d311417fb7ed6e832c6.
Fresh independent static scope review raised P2T1-R1 actual HTTP join, reproduced
RED29.934s; focused fix/API5GREEN96.240s plus main4GREEN9.204s. Narrow re-review
ADDRESSED/no new findings/9stablev2pins; reviewer executed no tests. Root validated
terminal logs/pins/CI. Existing Starlette/httpx deprecation warnings remain in main
test logs; corrected fixture ResourceWarnings are excluded from final evidence.
Public2026-10-24-compose-owner-controls.json SHA
de6eda2890334dcaeb7df9d17379cbd1bccaa41c84ad4a978e44251c3836809a (UTF8/LF).

All positive native predicates/SDK packets are synthetic storage controls, not
actual CLI/SDKClient/account/model/business evidence. PROFILE95 raw
4042a5083575db4354008675a333b4bdc5fa6022571c6f31334f80f1d7457831 remains
UNQUALIFIED; registries closed, actual309 proof test untouched. Next Task2 adds
bounded cold disposition metadata and reachable preview/consent/run/revoke panel;
publication-only /compositions does not imply every failed attempt published.
Then actual upstream library; same-pipeline dummy/native qualification, fully
qualified final execution, final task-head full CI/review, remaining M0–M8 code
and all Phase2 business/model/pilot/canary/authorized rollout stay open. Goal active.

## Reserved compose arm — scoped component approved

Explicit new candidate_policy reserves three hypotheses before observations;
old closed requests/history keep two. Typed candidate3 requires its own current
exact-diff grant, fresh semantic/dependency/native views and actual Trial/Call
preparation. Actual controlled integration reaches PREPARED then abort/refund/
cleanup; no inherited qualification. Legacy baseline comparison refuses arm3
before verification. Selection requires its own tuning evidence; KEEP_BASE and
cold off replay remain available. All three arms use multiplicity denominator60
instead of40. Bounded stop/drain reads include18000trials/sixroles, not new rights.
Historical ownership authenticates separate consent and execution actors against
actual immutable events/Operation/Result/Attempt/Call/publication links.

Meaningful policy/protocol/bounds/runtime/actor REDs preceded fixes; diagnostic
fixture errors are recorded separately. Local impact137PASS/16scripts, fresh
independent15PASS/192.949s/15stablepins/no open P0/P1/P2. Review report SHA
4aab1d8d7af57c4216e478e8c1dc9d6de4228ccdc561a5e1f58ffd81958a0eee.
Early isolated Linux40064018472/job120783344859 SUCCESS145PASS/17scripts,
snapshota3934037bc0e5442cf2aa4005a60eae1e2a49549/15exactpins. Public proof
2026-10-24-compose-checked-arms.json SHA
a4532ac0fef6678e222c64f3c492865aae675d36eca4c9037a6d059c7f026f82 (UTF8/LF).

Positive SDK/verifier/format/qualification and shared-source host DI are labelled
synthetic controls; no actual CLI/SDKClient/account/model/business proof. Actual
source/product/readers/current/view/ledger gates remain active; observational
unknowns stay unknown. PROFILE95/static raw hash
70f584395f5d91cf9d265c712178dfe420d9db8e9cc41f7808b9afc9075769cb is UNQUALIFIED;
registries closed and actual309 evidence test untouched. Full qualified selected
final, same-pipeline dummy, final task-head full CI and Phase2 remain open.
Next: 2026-10-24-compose-owner-controls.md actual facade/API/cold replay and
explicit preview/consent/run/revoke panel, then actual upstream experience library.
Full M0–M8 Goal remains active. User-delegated pilots remain reconciliation
primary, document processing secondary, Python bugfix/test technical control.

## Owned compose workflow/publication — scoped component approved

ComposerService now runs one explicit current-consent compose through the actual
shared RoleWorkflow/OperationTasks/Execution/CallLedger. Native2 format and current
source/grant/domain checks precede verification/Records creation. Same-event
callers share ownership; completed outcomes replay cold after off. Interrupted
start history does not resume implicitly; malformed output gets no repair or
second compose. Actual report2 and all required native/product gates remain
mandatory; default UNKNOWN qualification publishes no composition/candidate.

Actual report/artifact/decisions/input/basis link one immutable composition and
optional encrypted candidate3. Existing SkillCandidates.read_proposal consumes
version2/common provenance plus composition_id; no ordinary owner-request event,
region/edit/semantic approval or inherited pass. Ordinary staging stays capped2.
Event/typed metadata writes and slow reads precede final current/source and SQL
product/input/op/consent/domain CAS. Late grant/source/domain/call drift rolls back.

Author RED7/.207s before fixtures. Initial root7:2PASS/5failing cases(8assertions)
144.041s; actual diagnostic traced missing composer metadata to telemetry refusal
after the owned marker. Root metadata RED1/.001s preceded minimal closed
composer/improve_compose map addition; actual NativeUsageRecorder unchanged.
Targeted candidate+keepbase2PASS51.270s; remaining unknown/malformed/late4controls
3PASS147.390s. Independent static P2 native-history gap reproduced by deleting
actual encrypted decision/observation blobs: ROOT1/two subFAIL25.599s. Actual cold
OperationResults.read_stored extraction now authenticates that history for both
old and derived readers. Root actual callerTx mirror/model drift RED1/two subFAIL
25.915s led to final _attempt/bound_call/status/config/materialization/result check;
late token/cost fields remain mutable. ROOT4PASS56.883s and extended final lineage
1PASS26.620s. Root impact9scripts:61unittestPASS +manual turn_context PASS.

Independent ROOT4PASS44.395s/24stablepins/no findings, both P2 closed; own7 excluded
selfapproval. Review3270c767d2859cf541592c0eb0cddd5769cb9e83e6b1c227f8f1d7fb958aec05.
Early isolated Linux40061864692/job120776919060 SUCCESS69unittest +manual TC,
10scripts/10exactpins, snapshotb792833d45e53e648d536e52632f22f861ddab4c. Public
2026-10-24-compose-owned-publication.json SHA
1129532c0510ec9c7a839a0a4be07a8454308aa5c48e11fd77c117b2f660e3c3 (UTF8/LF).

Positive native packets/verifier/format/binding/qualification predicate are
explicit UNEXECUTED STORAGE CONTROLS, not native image ACK/account/model readiness.
PROFILE95/static Windowsraw3af5de7fdfbf4e05788b1bc18bcd42f7e181d16730c813468cce6da263dbc90c
is unqualified; registries closed and actual309 exact-evidence test untouched.
No real CLI/SDKClient/provider/model query, account retry, activation/deploy/restart
or measured quality/cost benefit. Next checked-arm policy plan reserves3 only in
an explicit alternate new request; old budget2 stays exact. Bind/freeze/select3
still need actual reserved policy/fresh semantic/owner/new bundle/view/tuning/
final/qualification/regression and API/UI. Actual upstream library follows that
functioning compose slice; full Goal/same-pipeline dummy/final-head CI/Phase2 open.

## Actual compose operation admission — scoped component approved

ComposePermissions.current now accepts an explicit actual stored operation and
authenticates its exact closed request/hash/input plus one immutable actual
operation_create event. Only the host creation mutation (original generation+1,
updated_at=operation.created_at) is normalized for the old immutable basis hash;
every other experiment field remains exact. Full current SQL/source/grant/policy/
holdout/domain fences retain the actual experiment row and recheck grant,
operation and creation history after slow reads. Shared SQL-only admission is
used by actual OperationRecords creation/reservation; existing Execution current
delegates the full guard at reserve/claim/materialize/start/heartbeat/retry.
Existing CallLedger/lease/workspace/cancel/refund remain authoritative.

Author RED6/.002s before fixtures; root independently GREEN6/52.625s. Additional
root controls initially reached the existing immutable experiment trigger before
the intended current guard (two fixture-error subcontrols); corrected to assert
actual SQL refusal, without bypassing/dropping the trigger. Corrected focused1
PASS6.955s. Root6-script impact regression PASS65; independent ROOT3PASS16.774s,
13stablepins/no findings, own-authored6 excluded selfapproval. Review report
ca2b7e6fb58ac1b9f15a4f6ed76dbb088b1aae1e5a0b87ef90fb9acb74b90ad3.
Early isolated Linux40060390227/job120772406637 SUCCESS74/74 on separate snapshot
017f887f6b8b897c219c39845e89f83ecec3faa7, eight raw source/test pins verified.
Public2026-10-24-compose-owned-admission.json SHA
5245196f130f744725f7025eb7742bebd37a3e1d522a26fcb4afdd8295d1d8f6.

Actual host-profile format selector is unchanged: legacy1 refuses compose;
declared selector2/verifier seams prove storage/PREPARED ownership only. Native
wire grammar now recognizes composer/improve_compose; no readiness/launch grant
is added. PROFILE_SOURCES91 includes newly consumed permission/input/protocol;
static raw profile912340a42d1aa8577e1eca75b41ac418affe64dcbf5198466553f9043a6f6e21
remains unqualified, registries closed, actual309 exact-evidence test untouched.
No real query/model/account/activation/deploy/restart. Next actual ComposerService
one-shot workflow, typed result/candidate provenance and independent composed
checks/API/UI. Ordinary staging/selection still restrict two candidates; reserve
an explicit three-hypothesis policy before admitting composed arm3 to selection.
Actual derived upstream library follows compose. Full Goal, same-pipeline dummy
qualification, exact final task-head full required CI and Phase2 remain open.

## Explicit compose consent/current input — scoped component approved

ComposePermissions uses actual owner/experiment/generation, authenticated existing
input/basis event and a small encrypted guard holding the exact original experiment
row/hash links. Complete stable SQL/definition/binding/policy authority remains
the existing input-basis hash, not a duplicate ledger. Actual schema8 authorization/
revocable grant/event publish atomically under current fences. Cold nine-field
get/list/revoke/replay do not decrypt/refresh/probe/build; replay returns the
current revoked state after off/source drift. Read-only current accepts actual
store SQLite/query_only, authenticates encrypted links and current brain/source/
policy/grants/holdout/domain/SQL, without public build/writer/event calls.

Author RED6missingmodule/.013s before fixtures; root independently GREEN6/57.051s.
Independent review found a final policy-read window after grant/source fence;
root actual tailpolicy/grant mutation RED1FAIL10.333s preceded fix. Tail capture
now precedes policy/source guards; final SQL input/grant/domain checks follow all
slow observations. Final root3races PASS25.472s, positive+query_only2PASS14.437s;
independent root3PASS15.882s/12stablepins/no remaining findings. Original reviewer-
authored6 excluded selfapproval. Initial root race control attempted revocation
twice through multiple arm guards; corrected test delegates complete actual fence
then revokes once, no criterion change; old fixture-error log retained.
Review cdceaadc41d0ec69e6588f07704828518192305a8b92298089ebe125016d8268.
Public2026-10-24-compose-permissions.json SHA
7ff6adeaef19e671cdb4f8ca0ed390650778e0343771fc0e846252614c47e517.

Unchanged producer/vendor/license/role/schema proofs reused; no extra broad suite
or portable rerun for this unwired component. PROFILE88 remains unqualified and
unchanged, actual309 exact-evidence test stays intact. Consent is not yet wired
to OperationRecords/Execution admission; current deliberately requires original
exact generation, no own-op mutation normalization. Native private identity grammar
still permits only improver/semantic pairs (native_protocol139); composer remains
a closed pending gate. Next plan2026-10-24-compose-owned-admission.md connects the
same actual owner/CallLedger/native2 paths and authenticates only their own exact
creation mutation. Composer publisher/new independent checks/API/UI/library/full
M0–M8/final-head CI/Phase2 remain open; no real query/model/account/activation.

## Compose role contract — scoped component approved

Closed compose requestv2 requires composer/improve_compose and authorization ID;
old propose/repair/semantic stay exactclosedv1. Actual workspace/worker identity
and profile now transport compose only in nativeformat2. Actual OperationProfile
renderer calls unchanged pinned compose_roundt=k1 through the existing closed
adapter. Existing CallLedger purpose and actual-call usage references recognize
compose. Actual legacy worker refuses before verifier/engine/ACK/readiness.

Root RED6:historical1PASS/new1FAIL4ERROR/.179s, then GREEN6/.627s plus actual
legacy-worker refusal1/.357s. Scoped5-script regression: shared ledger manual
scriptPASS0errors; workspace8/profile7/worker11/usage8. Initial worker inventory
test omitted5actual dependencies; add explicit names while preserving exact
set/length/rawhash assertions, focusedGREEN1/.055s. Actual309 native qualification
test remains untouched/open. Independent root7PASS1.174s/14stablepins/no findings,
report0f260a2f44ac06ac9607fcb699369a8484ce808b7ae64a179bdf0a743eb1b8ab.
Public2026-10-24-compose-role-contract.json SHA
c7d30ef146d5b39e1fa1c63b3f3800128d9a886149aadc39a000cef1bf1436c5.

PROFILE_SOURCES88/staticrawprofilee995019a433b3ddf65fdc63b30751a25038e9b24901ee01007ce8cbefdc7fca8
has no new qualification/registration. Reuse unchanged upstream AST/license and
schema46 Linux evidence; no repeated portable run for this bounded transport
delta. Final exact-head full required CI and native dummy qualification stay
mandatory. No compose consent/current-source service or OperationRecords/Execution
compose-phase admission connected yet; transport/ledger support is not enabled
dispatch, query permission, typed publication, new bundle, business gain or live
activation. Next explicit owner permission/revocation/current saved-input guard,
then actual owned admission/publisher/new checks/API/UI, library thereafter.

## Schema8 compose foundation — scoped approved, runtime still open

Four-table checked rebuild preserves actual schema7 prepared operation/lease/
workspace/CallLedger history and separate selected candidate/arm/result history,
all IDs/values/Fernet bytes and historical schema1–7 literals. Actual GoalStore
writer transaction owns backup/create/copy/drop/rename/guard restoration/FKcheck;
only its fresh migration connection uses FKOFF before BEGIN. Ordinary connections
retain FKON. Unknown schema7 guards refuse before backup; two writers serialize
one backup; mid-copy and invalid child FK errors roll back exact old history.

Distinct immutable compose permission/publication and revocable grant records,
composer/improve_compose and one operation total are schema constraints. Candidate3
needs typed composition provenance, no inherited edit/semantic authority; original
manual/generated proposal caps stay two. Sealed selection refuses new consent.
Final publication rechecks actual completed operation/result/attempt/call and
brain/purpose/attempt/context/mirror/reason. output_hash is the encrypted RESULT
REPORT blob; later publisher must authenticate raw artifact and decisions.

Author RED6missingmodule/.008s before private fixtures; root independently GREEN6
26.607s and again22.090s. Root extra sealed-selection RED and four settled-call
identity subtest failures preceded fixes; GREEN5/23.489s. Initial118-test Windows
cohort retained115PASS/2FAIL/1ERROR: stale extra-backup expectation, future-version
exception and view diagnostic. All three corrected with focused GREEN checks;
full new migration/role/view validation stayed enabled. Final independent root5
PASS21.636s/12stablepins/no findings, original reviewer-authored6 excluded from
self-approval. Report9416129700e71677164fad7ee9b3c77ccc02031c9a2ddc26ae5b9900bfd72ca9.

Early isolated [Linux40058375830](https://github.com/blogminhquy/javis-os/actions/runs/40058375830)
SUCCESS46/46: migration6/boundaries5/execution13/profile7/view15, exact12rawpins,
commit4a2877aedbdd45e7978f65aa7d6d1757a543c631. Earlier40058040941 retained
future-version exception failure after103PASS/104tested; unchanged candidate12/
cases28/experiments19/operations21 proof reused. Final delta restores original
SchemaError and view-specific diagnostics; no full unchanged cohort repetition.
Public evidence:2026-10-24-compose-schema-foundation.json SHA
87ef707685ca7ca20a507f09e71cbe0ec29ffeb9a2c248824c85ee86195105cc.

Actual new schema dependency is now in PROFILE_SOURCES86. Static raw profile hash
823a1434000fa3eabeafbd44ea92d704e60498491519f88bb702ff1aee5f514b matches no
historical qualification; both release/candidate registries remain empty. Preserve
the exact current native-evidence test: it is still an open requalification gate.
This unit enables no compose dispatch, owner query permission, typed positive
composed candidate/bundle, real model/account/business result or activation.
Next: explicit owner permission/current authenticated saved-input guard and typed
role/profile/ledger/workspace/usage connection, then actual publication/API/UI/
independent new-candidate checks. Library follows actual compose, orchestration
assessment after library; full M0–M8/final-head fullCI/Phase2 remain active/open.

## Authenticated host compose inputs — scoped component approved

Actual current two-arm candidate/report/lineage, authorized solver/artifact/
typed verdict/bound observable trace now feed the unchanged upstream renderer.
Original A refs remain immutable history, not new citation/source permission.
Input and stable hash/identity basis are encrypted in existing M0; exact tuning
exposure and metadata share final-fenced transaction rollback. Replay requires
current owner/brain/grant/policy/source/holdout/latest evidence. Actual settled
Trial/Attempt/CallLedger identity/status/engine_at joins are checked and captured.
Late call corruption, policy identity drift or final event domain marker refuse
publication. Basis excludes process-local checker callback IDs. No new schema,
executor/ledger, compose native call/allowance, candidate or executable bundle.

Author RED7missingmodule; root independently reviewed/executed all7. Initial
5green/2count failures exposed incorrect test expectation: successful input
publication must record tuning exposure like existing readers. Root/author agreed
exact tuning-key union, preserved old timestamps/replay and zero new exposure on
failure. GREEN7PASS49.139s before final policy fence; final-source positive/replay2
PASS14.658s, rootrace4PASS21.424s and protocol11PASS.169s. Actual call and policy
races each had meaningful RED before fixes; historical original-ref RED preceded
new-output/current-ref preserving fix. Independent rootrace4+historical1 PASS5/5
14.943s,15pins stable/no findings; own original7 excluded self-approval. Report
e6c9055afaf75487ebdddb7590cc4bea80332dc13b381e7f5766f1433f774422.

Early isolated [Linux40056590938](https://github.com/blogminhquy/javis-os/actions/runs/40056590938)
SUCCESS33/33 across protocol11,host7,races4,existing byte validator11. Exact8 raw
source/test/license pins verified on isolated commit50a73cc28262e4bf1a9b9159c0d38e3df3f47890,
fresh Ubuntu/Python3.12, serial no-real-engine fixtures. One initial dispatch500
produced no run; bounded retry succeeded. Task checkout/index/head unchanged by
CI snapshot; this is not task-final-head full required CI/native qualification.
[Public evidence](../evidence/2026-10-24-compose-host-inputs.json) distinguishes
synthetic_storage_fixture/technical_fixture/unexecuted controls from actual
selected model/config/native/account support. No cross-process restart execution,
provider delivery, business benefit, token saving or live activation proof.

Next: distinct composition owner permission/history plus explicit existing
Operation/CallLedger/schema/arm integration; preserve original two proposals,
one compose total, and independently probe/qualify/regress new bundle. Then actual
derived experience-library adapter and only afterward orchestration replacement
assessment. Native footprint integration/qualification, final exact-head full CI,
remaining M0–M8 technical work and Phase2 stay open; Goal remains active.

## Compose full pilot projection bound — scoped correction approved

Consumer inspection found the initial pure adapter mistakenly reused32 patch
citation slots for all tuning trial refs. A12-case/two-repeat/two-comparison
projection needs96 separate refs. New actual96ref fixture RED1ERROR (other9green)
→GREEN10. Trial projections now use existing schedule bounds (≤4000observations/
group,≤8000unique trials) while1MiB fail-closed/no-truncation and32citations per
patch/decision remain. Independent focused1PASS.036s,9stable pins; report
6f76a33a87bb919ffc52395065ace2b042b234b14c3b8056325e493ead308ff3.
Prior upstream9-definition/license proof is unchanged/reused. This is projection
capacity, not an actual pilot or support for unlimited context. Durable host and
runtime consumers remain next. [Additive evidence](../evidence/2026-10-24-compose-pilot-projection-bound.json).

## Actual upstream compose adapter — scoped pure component approved

Goal17's first functioning fixture slice now calls actual compose_round at t=k=1
from the pinned upstream source. Nine extracted definitions/constants match exact
source segments AND AST; raw original Git blob9ccacf23b64ac15b06a1939f26224960f56d757c
and Apache2 LICENSE blobd645695673349e3947e8e5ae42332d0ac3164cd7 independently
verified. Static narrow Javis body surface and context/notes→JSON mapping exclude
upstream guardrail/plugin surfaces and filesystem access. Existing byte validator
creates combined UTF8/CRLF bytes, KEEP_BASE or adoption; decisions remain model
claims, semantics unreviewed, no source authority or inherited pass/activation.

Meaningful RED8 preceded GREEN9; existing body patch regression11/11 PASS.
Independent9/9 PASS.256s,10 pins stable, no actionable finding; report
a06d21b5af3325fbf755a6c3ae5e288389caedbaa5ff71010e4c96b0b7a9a4bb.
[Public component evidence](../evidence/2026-10-24-harness2-compose-adapter.json)
and third_party/harness2/COMPOSE-PROVENANCE.json distinguish actual vendor code
from host glue and unverified caller projections. This is not durable/runtime/
executable-bundle integration. Next connect authenticated tuning lineage and a
distinct immutable composition record to existing Operation/CallLedger ownership
with explicit schema/arm migration; retain original two proposals and separately
probe/qualify/regress the new composed bundle. No ordinal3 or authority shortcut.
Native footprint must include new dependencies on connection and requalify; exact
final-head full CI, later library adapter and full M0–M8 remain open. No actual
model/account/business/cost-saving/live evidence.

## Upper engineering-domain product fences — scoped implementation approved

Comparison create/read/evidence/replay/final publication, experiment selection
and actual role admission/join/product/return now reuse the existing authenticated
require_product_store. Genuine engineering stores and unanchored markers refuse
ordinary publication even with missing cells, replay or a late domain change.
Comparator, baseline/unknown policy, schemas and encrypted history stay intact.
Meaningful RED6 (12 assertions, no fixture errors) and RED4 preceded GREEN6
23.820s/GREEN4 13.361s. Affected comparison/selection/proposal/semantic checks:
25 tests,4/4 scripts PASS203.919s. Independent root-source/race review approved,
4/4 PASS10.557s,8 stable pins, no actionable finding; reviewer-authored original
six cases were separately verified by root, excluded self-approval. Report hash
4fbd625e7b7c3ce0d506b871b8f81fdca847a8becfebf783df31776c3067f61f.
[Public evidence](../evidence/2026-10-24-qualification-product-boundaries.json)
distinguishes actual authenticated Session fixtures from unanchored refusal-only
race controls and explicit static/native seams. No actual native/account/model,
business benefit or live activation proof. Separate engineering reports/runtime,
current-source native qualification and final-head full CI remain open.

Next safe unit follows Goal17: actual pinned upstream compose through a bounded
adapter, then experience-library snapshots/index; do not revert to an earlier
native-first schedule or claim the whole M0–M8 Goal is complete.

## Owner direct compose/library priority — Goal§17

Owner directive from the same authorized chat is saved in Goal§17. Next safe
unit after current engineering-product boundaries: inspect exact pinned
prompts.aggregate/compose_round and recursion compose call/direct dependencies,
then actually import/vendor functioning independent implementation through a
narrow Javis adapter. Follow with actual library entry/index/serialization via
private authorized derived snapshots, retaining Javis immutable encrypted source,
brain/scope/revocation/retention/trace authority. Assess whole orchestration only
after those, counting executor/lease/cancel/restart/replay/ledger/migration/tests/
qualification costs; do not duplicate authoritative runtimes/ledgers. No scaffold
or prompt paraphrase counts as direct compose/library reuse. Keep baseline,
limits, every gate and Phase1/Phase2 ordering. Current upper-domain test/source
ownership is preserved; no full audit/restart or real inference.
Post§17 Goal SHA-256 b9466f98fff57c032a6c82132fe57d3beef2e187c7d963fbfc8bf60e5c1ee749;
pre§17 76e349119bd3f7148204b2e57800d9769aac4f7cb73c271e6f8541ff0a6c5b18.
All original/historical hashes and scoped evidence remain unchanged.

## Current proposer/evidence guidance — scoped implementation approved

Existing render_proposer_input now adapts Google Harness² propose/_INV/_DOM/
_KEEP_BASE/experience/evidence-boundary method at pinned1cfe254e, source Git
blob9ccacf23b64ac15b06a1939f26224960f56d757c. Actual OperationProfile consumer
receives the structured method separately from unchanged authorized evidence.
It asks for earliest supported failure, execution/domain_process distinction,
small explanatory edit, predicted effect/risk, linked observed attribution and
confounded cases, separate overall versus protected-meaning review, or existing
not_a_target_defect no-change. JSON/patch/refs/UTF8/candidate/repair contract and
all source/owner/permission/privacy gates remain enforced. No extra evidence I/O,
schema, store, executor or full-library input. Original Apache-2.0 LICENSE matches
exact upstream Git blobd645695673349e3947e8e5ae42332d0ac3164cd7; narrow provenance
and modifications retained in third_party/harness2/PROVENANCE.md.

Root meaningful RED6:1FAIL4ERROR.008s (missing method); GREEN6PASS.019s. Affected
actual improver-input/operation-profile2/proposal/skill-patch regression4/4PASS271s,
including generated drafts and one structural repair. Independent review clean:
guidance6+existing GenerationJsonTests2 PASS.016s,11pins stable; report
cbda0ee6c090a435493a44cbb839628b24f8682babc2f70ca91478b85c1a2279.
[Public evidence](../evidence/2026-10-24-proposer-evidence-guidance.json) records
source/consumer/test/license identities and actual test/model-quality limits.
No claim of model injection resistance, causal/business quality or token savings.

Native PROFILE_SOURCES still85; actual pure source hash changed
ac4b613eb692598d31bede47e5ee755c80872e18f3792c9c1cd5b1fba6f939cd →
6e32d3fb91d8ec4b5b596bd3d68f1165a3921fa7fcf3049b5b0c6872549d355e;
generation source24782400… →1f0eae72…. Historical qualification is not reused,
registrations remain gated. No native/account/model call or live action occurred.
Final exact-head full CI and full native qualification remain open. Preserve
this unit, then finish the already identified upper engineering-store product/
comparison/selection/replay boundaries using the existing actual domain helper
and the targeted upstream reuse decision. Remaining M0–M8/Phase2 scope unchanged.

## Owner selective replacement update — Goal§16

Direct owner update from the same authorized chat permits replacing existing
Javis code/structure with pinned upstream when concrete benefits justify total
adapter/consumer/migration/backward-compatibility/qualification/test/review cost.
This supersedes prior blanket no-rewrite restrictions only within that scope;
database/authority/native lifecycle can also be replaced when justified with a
compatibility/recovery plan. Keep all gates/history/baseline/unknown/ownership,
no parallel duplicate runtime/ledger, no full audit/restart or copy-percentage
refactor. Ordinary technical choices are already authorized. Phase1/Phase2 stay.
Goal§16 SHA-25676e349119bd3f7148204b2e57800d9769aac4f7cb73c271e6f8541ff0a6c5b18;
pre§16 e868339ebd3ad1a73fe9faea13b74e2af959c8b3f8148eb4c2ddbae63ac8fc20,
all earlier source/evidence lineage preserved. Active code-first plan/reuse map
carry this rule. Current proposer adaptation already uses real upstream method
via a small renderer while preserving Javis output/authority validators; no
additional infrastructure replacement is justified by this unit. Ongoing serial
fixture regression ownership is preserved; no account/model or activation starts.

## Current D2 ordinary named-skill snapshot unit — scoped technical approval

Actual final Dashboard API branch now privately carries the original host turn
token into an opt-in TaskSkillTurn lifecycle before Phase8 source/tool discovery.
Default/off/malformed/native/nonhub/no-key routes do no capture/store creation.
The core uses real running runtime rows and existing encrypted M0 blobs/events;
lazy selection, main's precomputed skill metadata and the actual named hub handler
share frozen per-task inventory and first selected bytes/hash. Global skill
registry remains unchanged; hub cache/epoch/inventory stay owned by task and
shadow scheduler refuses task descriptor publication. Closing invalidates copied
contexts; no mutable fallback from missing/dead/foreign/corrupt bound snapshots.

Root independent core13:12PASS1 Windows symlink privilege skip4.072s. Root impacted
regression10/10scripts40s includes actual Phase8, prompt scan and ordinary skill
asset/routing/language/caps/usage; later narrow cancellation fix independently
verified. Independent root-source review reproduced/closed two Important issues:
returning bytes after revocation during awaited usage, and capture failure
overwriting retained Stop. Meaningful RED/GREEN logs are preserved. Final independent
consumer11+root-owned cancellation1:12PASS5.141s,14pins stable; report
fb8a1670e1f0776c1f1bc61c80fe8f9816c65f8af2a5a75e9a882dd70294883f.
Own author tests/core are explicitly excluded from self-approval.

Early genuine Linux [40053479314](https://github.com/blogminhquy/javis-os/actions/runs/40053479314)
succeeded10/10scripts17s on isolatedcfdc8cd181a23b51a9585b22802c988ba5469cf5,
with nine exact selected raw files and fresh remote HOME/DB/filesystem. This is
not exact-final-task-head full CI. [Public evidence](../evidence/2026-10-24-m2d2-task-skill-snapshots.json)
and [engineering boundary notes](../../dev/agent-skill-task-snapshots.md) record
actual test seams, counter semantics and source identities.

This is a delivered narrow engineering unit, not complete D2 effective-view
isolation: arbitrary file/helper reads, native/HTTP/resume, OAuth/subscription and
earlier fast paths remain separate. Actual run_turn AST proof substitutes _do_turn;
final API route gates are source-reviewed, not full WebSocket/provider E2E. No
account/model/native call, live settings change/deploy/activation or quality/
business/canary conclusion. M0–M8 Goal remains active. Preserve this unit then
execute the Goal§15 proposer adaptation plan; remaining D1 qualifier/D2/E/F and
later code still require their own gates and final exact-head full CI.

## Owner prompt/evidence update — narrow existing renderer improvement next

Goal§15 persists the next direct owner directive from the same authorized chat:
after preserving the in-progress D2 snapshot unit, inspect pinned upstream
prompts/context/selection as relevant and adapt a narrow useful proposer/evidence
renderer delta. Keep execution/domain_process, JSON/patch/repair/byte-offset/owner
contracts, privacy/holdout and all gates. Use explicit edit→allowed source/trace→
observed behavior→helped/hurt/no effect/confounded reasoning, KEEP_BASE if evidence
is insufficient; no causal inference from winner/one rollout, no full-library
loading or infrastructure/schema rewrite. Actual prompt extraction must preserve
Apache-2.0/copyright/provenance. Record changed source footprint and invalidate
qualification as applicable, never reuse mismatched evidence. No quality/token
savings claim before actual Phase2 measurement. Next unit remains queued until
the current D2 integration is preserved and reviewed; no repeat broad audit.
Post§15 Goal SHA-256 e868339ebd3ad1a73fe9faea13b74e2af959c8b3f8148eb4c2ddbae63ac8fc20;
pre§15 77310e4c4635b012efb8f565bd842d314c82d6e2d168b90dd1ef006f484a2b2b.
All previous source/spec/evidence hashes stay historical.

## Current owner reuse update and D2 ordinary task integration

Goal§14 persists the direct2026-10-24 owner instruction from chat
`01a16662-a77c-72e2-9c40-265c5659d5cc`: assess targeted upstream reuse before
each unwritten component, pin Harness²1cfe254e8d25b15f37048c3730134686abe60335,
prefer narrow import/vendor+adapter where it reduces actual integration work.
No completed component rewrite for reuse percentage; preserve license, baseline,
quality/authority/ownership/usage/recovery gates and Goal§13 code-first ordering.
Post§14 raw Goal SHA-25677310e4c4635b012efb8f565bd842d314c82d6e2d168b90dd1ef006f484a2b2b;
pre§14 f683ff6abba61e110ef8034fe1451d80390d6688866c2def5f2f964ec4fcd356 and
all older original/spec/lineage hashes remain historical, never replaced.
[The incremental reuse map](../plans/2026-10-24-harness2-reuse-map.md) records
the first targeted decision: inspected actual upstream substrate protocols and
context builder are benchmark staging, lack Javis private live-turn ownership,
and delete/copy mutable destinations. Keep the narrow Javis task lifecycle using
its completed M0/runtime/core; no upstream code copied/imported for this unit.
Upcoming prompt/compose/selection/recipe/bundle units must inspect upstream first.

D2 core authored13 tests:12 passed/1 Windows symlink privilege skip3.318s;
independent integration review/execution is in progress. Actual lazy/hub/router
consumer RED7 had3 failures/1 error (mutable metadata, bound empty-body fallback,
missing encrypted pin); correctionGREEN7 passed2.274s. These are private fixture
tests without model/native/account calls. Actual host lifecycle integration,
independent review, impacted regression and final exact-head full CI remain open.
No ordinary task/activation/native/HTTP/resume production-readiness claim yet.

## Current technical continuation — actual operation binding branch verified

New independently authored fixture tests reuse genuine private Session, actual
selected owner/source files, HostContextStore/CaseStore/ExperimentPlans and
OperationExecution materialize/prepared/ledger. Root independently reviewed and
ran3 PASS9.359s: encrypted exact link/replay/unstarted call, cold authenticated
read after actual workspace cleanup_proven, durable default read/finish refusal
before+after link, and protected owner-file edit rejection before binding.
Public qualification-operation-binding records hashes/command/scope.

No production changes. Candidate/static observer and historical input_version1
fixture seams plus explicit real OperationRecords fixture reservation do not
claim ordinary native admission/full input2 qualification. No verifier/auth pass
was fabricated and no SDK/native/account ran. This closes the earlier static-only
operation binding records gap; all runtime/typed provenance/report/upper-promotion
integration work remains Phase1, actual account/business trials remain Phase2.

## Owner scheduling update — all M0–M8 code first, real trials second

Direct owner update relayed2026-10-24 from chat
`01a16662-a77c-72e2-9c40-265c5659d5cc` is persisted as Goal§13 and
[the active code-first plan](../plans/2026-10-24-agent-skill-improvement-code-first.md).
It changes order only: Phase1 completes functioning backend/runtime/UI/migration/
selected adapters/agent/bundle/Team/operations and mandatory technical tests for
all M0–M8. Phase2 then runs real account/model/business feasibility and pilots,
correction, real canary and authorized rollout. No scope cut or reset/MVP stop.

Previous source hashes remain historical:
original67061573b8c584d65d0ecf1daa4c56b536c78c07fcc5158cfa090d40ea299afd;
pre§13/after§12 558e91848624c2dbc5daf1d5decb64b43b960285ce0416e40099ca63863b2ec8.
Post§13 Goal SHA-256: f683ff6abba61e110ef8034fe1451d80390d6688866c2def5f2f964ec4fcd356.
New addendum identity never replaces old goal/spec/evidence lineage.

No real inference is currently owned/running. Preserve all historical failed/
unknown/refunded attempts and usage. Older checkpoint "next account feasibility"
instructions below are historical; those tasks move to Phase2, traced in the new
plan, with original selected config/quality/owner/canary criteria unchanged.
Current dummy/fixture/native localhost technical work remains Phase1; incomplete
business/canary evidence does not prevent independent later code. Keep actual
native/runtime/production/activation gates, independent review and final-head CI.
Code merge/publication does not authorize deploy/restart/live activation.

| Scope | Code complete | Technical checks / environment | Engine evidence required | Business pilot | Canary / rollout |
|---|---|---|---|---|---|
| M0–M1 | Previously integrated foundation; reuse | Historical exact-source Windows/Linux proofs; recheck actual impacts only | Existing limited evidence stays scoped; no blanket adapter readiness | No new result inferred | No activation inferred |
| M2 | A/B/C integrated; D1 ongoing, D2/E/F still open | Latest scoped Windows35 +Linux46; no complete owned native pipeline claim | Current exact-source dummy/native technical qualification pending; actual selected-account feasibility deferred | Phase2 pending | Phase2 pending |
| M3 | Pending full implementation | Dataset/policy/reviewer/canary/monitor/revert simulations to implement/test | Phase2 verification where applicable | Phase2 pending | Real7days/10tasks and owner gates pending |
| M4–M5 | Pending routing/adapters/scoped agent/UI | Real implementation +fixture/DI tests to complete | Each adapter/surface separately pending | Phase2 pending | Phase2 pending |
| M6–M8 | Pending bundle/helper/Team/adaptive governance | Full atomic/recovery/transfer/filter/stop technical tests to complete | Each applicable helper/engine/Team scope pending | Phase2 pending | Phase2 pending |

Phase1 is not complete. Full Goal remains active through Phase2. Immediate work
continues from d13ecb48: real operation binding execution proof, owned qualifier
and domain consumers, D2/E/F, then remaining milestone code in technical dependency
order. Do not repeat unchanged tests or real account attempts to delay later code.

## Current continuation — startup3 consistency and genuine Linux preparation approved

Explicit pure startup3 binds closed engineering scope/account_readyFalse, exact
pin/environment hashes, isolated HOME path shape and full attempt/receipt/config/
capability/call identity data. Production startup2 stays strict and rejects all
engineering extensions. Parser/channel binding alone grants no provenance,
native launch/account authority, actual M0/FS/emptyHOME/clock/budget observations.
No runtime consumer is installed yet; actual owned host/worker permit integration
and closure seeding remain mandatory before authority.

Private Session now supplies both AppData path fields under its fresh empty HOME
even when portable base lacks them; production worker_environment unchanged.
Independent35 PASS7.716s, all17 pins stable. Genuine clean Linux first failed on
undeclared direct packaging dependency; explicit packaging==26.2 matches local
tested runtime and received narrow review. Fresh isolated Linux40051859131
SUCCESS:46 PASS4.197s on fe7ecb0185, five selected rawsource/test/dependency pins
recorded. This is early scoped preparation CI, not final-task-head full CI.
Public qualification-startup3 records RED/GREEN/reviews/failed+successful CI.

Remaining operation binding execution proof, typed qualifier launch/runtime,
explicit engineering report publication/forensic joins and upper promotion
fences precede actual exact-source owned qualification/registration/account
feasibility/final CI. Goal remains open; no live/account activation occurred.

## Current continuation — durable engineering run/attempt domain approved

Concrete session now supplies a read-only expected run anchor to actual M0 store;
explicit forensic reopen requires it and uses SQLite read-only mode. Missing root
fails; unanchored reopen seeing engineering events refuses. Prepared trial links
bind actual request/workspace/materialization/config/capability/ledger call in one
immutable encrypted event, with atomic query budget and exact idempotent replay.
Historical link reads survive workspace cleanup/close without live lease checks.

Default TrialResults read/finish/reevaluate, TrialProducts._products and
OperationResults read/finish refuse durable engineering stores before data or
evaluators and final publication Tx. Canonical report bytes remain unchanged.
Two static findings (materialization mismatch, slow replay passing final fences)
were reproduced then repaired. Independent42 PASS50.472s, all16 pins unchanged;
public qualification-records contains scope and logs. No native/account/inventory.

Still no launch authority: operation bind runtime proof, explicit typed
engineering publication/forensic result and upper comparison/selection/replay
fences remain due before qualifier activation. Next explicit startup3 wire and
concrete host/worker permit integration, then actual exact-source owned pipeline
qualification, registration/account feasibility and final-head CI. Goal open.

## Current continuation — concrete qualification session foundation approved

Separate empty engineering-candidate authority validates exact static runtime and
observed closure before scratch allocation. Concrete host session owns fresh
private root, generated fixture-only encryption key, actual encrypted immutable
M0 run scope and same-DB CallLedger. Each environment gets a fresh empty HOME;
no ambient auth copied. Foreign/traversal/expired/closed/corrupted scope refuses.
Close retains forensic records; explicit cleanup refuses unsettled placeholders.

Independent source-closure P2 repaired: owner seeds PROFILE_SOURCES85, actual
offline observe_release proves owner mutation refuses profile/helper mutation
changes fingerprint. Root property is read-only. Independent16 PASS7.566s, all11
pins stable; public qualification-session records exact scope/logs/review. No
CLI/native/account/default inventory. This is preparation only: maximum_queries
metadata, actual owner attach/drain, typed verification/startup3/attempt-call links
and durable publication/cold-read domain fences remain pending. No qualification
or account readiness claim. Continue those integrations, final-source owned
pipeline proof/registration/account feasibility and exact-head CI. Goal open.

## Current continuation — four actual downstream native blockers repaired

Audit found RoleWorkflow old10 refused native14, semantic paired-view gate old10
likewise, improver projection raised KeyError on raw observation2, and comparison
old18 made native22 always UNKNOWN. Actual callers now select exact inventories
from authenticated report/evidence format, retaining all old requirements plus
four mandatory native gates. Semantic evidence binds actual report format/checks/
verdict on publication and current read; two permitted observational UNKNOWN stay.
Improver derives labelled sequence/source-aware projection, whitelists worker
metadata and withholds guardian/control/text/tool payload; stored raw unchanged.

Explicit execution_domain markers refuse at product/promotion inputs (even None,
false or labelled production). This is only a preliminary fence: future M0
qualification run/subject/attempt/call links must prevent omission/downgrade on
publish and cold read before qualifier can run. No such authority is enabled yet.

Author8 PASS6.272s; independent21 PASS29.700s total, all15 pins stable, no findings.
Includes actual encrypted op2 RoleWorkflow and targeted legacy proposal/improver/
semantic async paths. Public native-downstream records RED/GREEN/source/logs.
Complete native baseline→improver→semantic→paired chain remains separate proof;
dummy results cannot be promoted to fake it. Next concrete QualificationSession,
typed engineering verification and explicit startup3, then final-source actual
same-pipeline qualification/registration/account feasibility/final CI. Goal open.


## Current continuation — pure dummy qualification environment approved

Canonical pure helper accepts only literal dummy key and exact numeric
http://127.0.0.1:<canonical port> over a closed production base. It refuses URL
aliases, credentials, paths/query/fragments, proxies/auth config/mode knobs,
malformed fixed fields and final-envelope tampering. No ambient environment,
filesystem/network/launch or registry/account capability. Existing production
startup2 still rejects dummy extras. RED5 FAIL.006s -> author5 PASS.011s;
independent5 PASS.007s, all4 pins stable, no findings. Public
qualification-environment records exact source/test/log/report scope.

Authenticated qualification entrypoint, actual local traffic and empty-HOME/
source/runtime proof remain outstanding. Next integrate explicit qualification
protocol and host authority without changing default production validators or
treating dummy-only capability as real account readiness. Global runtime/source
registration still disabled; full same-pipeline proof and final CI still due.


## Current continuation — exact host-pinned native materializers approved

Planned claude-owned-images-v3 exact-source selector now emits genuine baseline5,
linked view4 and operation2; old profile inputs remain1/3/1. Global PROFILE_VERSION
stays old and registry empty. Selector added to source tuple84; full reachable
release closure/final qualification remain separate. No request/env mode switch.

Actual source-file race survived SQL-only _current: first GREEN6 retained1FAIL.
Native5 now requires concrete same-store HostContextStore from TrialAdmission,
with binding/source/binding checks before and after decrypted solver; finalSQL
and caller lease checks retained. Unbound5 refuses before solver; fake/foreign
hosts refuse. Actual request3 prepares before candidate/view; linked real pair
and role preserve exact stored authority/data. Independent14 PASS101.454s total,
all12 pins stable, no findings; public native-materializers retains full lineage.
Semantic authoring fixture setup uses explicit historical-format seam only;
view call itself uses actual new selector, stored host/profile/source and pair.

Next is canonical dummy-only same-pipeline qualification support, preserving
production startup2 default refusals and no auth-copy/account retry. Native full
source qualification, exact registration, account feasibility and final CI due.
M0–M8 business/owner/live-canary gates remain open and unchanged.


## Current continuation — baseline native result/runner consumers approved

Validated baseline5 now reaches exact receipt/delivery checks, whole V2 product
and result publication, four durable decisions with final transaction reread,
cold authentication after cleanup, and native runner closing/late/usage handling.
Policy derives from actual validated manifest, not receipt; request1/2/3 baseline
only, no paired-view downgrade. Missing delivery/decisions and asset reading/
reasoning/provider stay UNKNOWN. No invented view or read-outcome fields accepted.
Author10 PASS13.183s; independent58 PASS80.353s total (new10/trace12/checks29/
results7), all10 pins stable, no findings. Public native-baseline-consumers records
RED/GREEN/fixture correction lineage and review's narrow runner-guard scope.

Producers/global runtime selection/registration remain unchanged. Next actual
materializers choose explicit5/4/2 from exact host-pinned planned new profile,
preserve old formats and recheck source after native baseline read. No native
child/account activation; final-source qualification/full final CI still due.


## Current continuation — baseline guarded worker/parent routes approved

Explicit baseline5 now follows actual worker/adapter/parent guarded routes with
fixture-only baseline_inline policy, exact typed private ACK and runtime drain
before completion. Legacy entry refuses5 before unguarded verifier; bound old
inputs still refuse legacy launch. Parent keeps four exact durable M0 decisions
under actual attempt scope; operation/unknown policies refuse before admission.
Author focused7 PASS2.687s after precise RED checks and fixture corrections;
independent31 PASS10.057s total (new7/startup14/parent10), all12 pins unchanged,
no findings. Public native-baseline-routes records full lineage and narrow scope.

No product emitter or account/runtime activation. Next baseline5 consumers extend
whole V2 history, exact receipt/delivery, final-transaction durable decision reread,
cold result authentication and runner cancellation/usage. Asset reading/provider/
comprehension remain UNKNOWN; full final-source qualification and final CI due.


## Current continuation — native baseline profile independently approved

Explicit manifest5 now binds the same owned runtime/client/transport/original
stdin write as view4, with distinct baseline_inline policy and fixture-only tools.
Operation cannot select that policy. Receipt5 includes actual completed delivery
or None, no invented effective_view/read proof; asset use/provider/comprehension
remain UNKNOWN. Unbound native4/5 options/start refuse ambient client fallback.
Focused profile4 RED1FAIL/3ERROR1.488s and SDK2 RED1ERROR.847s became GREEN;
independent18 PASS6.792s total includes old view4/query/binding paths. All11 pins
stable and ClaudeTrialAdapter AST unchanged against c3f82ce8. Public
native-baseline-profile records exact logs/report and limited engineering scope.

No baseline5 parent/worker/runner/result/materializer activation or registration
yet. Next extends explicit guarded worker/parent routes, then result validation
and actual host-selected producers. Reuse unchanged prior component proofs;
full final-source native qualification and exact-final-head CI remain due.


## Current continuation — explicit native baseline manifest foundation approved

Readonly manifest5 now carries the real baseline bundle/context/assets/fixtures
without an invented paired view. Its inline prompt/effective hash equal legacy1;
full canonical input hash distinguishes5. Historical1/2/3/4 behavior stays exact,
multi skill/agent assets retain old protected validation, paired-view brokers
refuse5 and unchanged read correlators stay UNKNOWN. Focused6 RED2ERROR/1FAIL.011s,
author6 PASS.020s; independent21 PASS.057s includes final assertion correction,
legacy manifest4 eleven and four affected sandbox checks, all nine pins stable.
Public native-baseline-foundation records exact scope and logs.

No materializer or runtime emits/executes5 yet. Next is owned native baseline
factory/input-delivery receipt plus exact distinct baseline tool policy, then
worker/parent/runner/result/materializer integration. Keep actual baseline asset
read/provider/comprehension coverage UNKNOWN and preserve final eligibility gates.
Current local head after ancillary fix isfcf265db; parent/callers remain approved
in their recorded scope, full source/native qualification and final-head CI due.

## Current continuation — actual default inventory observed; ancillary fix approved

Readonly default inventory initially refused native_release_path in6.078s.
Actual installed segno/yt_dlp RECORDs include six standard manuals/docs/shell
completion paths outside site-packages. Narrow omission never follows those
paths; selected RECORD/METADATA bytes stay pinned. Real selected-dependency
fixture RED1 ERROR.138s -> GREEN.416s. Independent review found malformed Windows
tail aliases were omitted before validation: actual RED1 with4 subfailures.381s,
fixed by strict tail validation, GREEN.416s. Independent final builder11 PASS2.578s
with sourcecdec514e/test9a9a3fdd unchanged; minor finding closed.

One actual unoverridden default observation succeeded in44.187s on priorb711
builder:206 source,1629 import and2 runtime files, fingerprint73d43cd9. Coverage
authority/unlisted-import exclusion/initial sections/dynamic closure stays UNKNOWN.
That observed snapshot precedes the stricter-tail line and remains historical;
no repeated44s inventory just to relabel it current. Public native-default-inventory
pins exact logs/manifests/source and this reuse limit. Final source qualification
will rebuild after consumers settle. Registry is still empty, no launch/account
query or performance/caching claim.

Next is explicit native baseline support plus actual materializer4/2 integration,
then closed dummy-only qualification policy and final frozen full-pipeline native
evidence. Baseline preparation must retain genuine bundle authority without an
invented paired view or unguarded fallback. Goal M0–M8/business/canary stays open.

## Current continuation — all nine native admission callers independently approved

All nine audited synchronous caller bindings now pass one independent combined18
in82.937s, no skips, all13 source/test pins unchanged. Root's affected legacy39
(first2) and selected legacy12 (next7) pass106.280s/178.021s. Public
native-admission-callers records exact source/log hashes, intermediate RED/GREEN
lineage and honest engineering coverage. Original calls/attempts are never
created for preflight; existing worker-thread ownership and cold replay remain.

Review caught an absolute retry deadline crossing the final slow source read:
RED1 FAIL3.472s, corrected by final SQL/time eligibility check before image allow.
Self-review caught eager historical V1 first-record decrypt: RED1 FAIL4.523s,
corrected by detecting V2 only from already-selected engine events. Actual
encrypted observation2 transient503 proof now supports the existing single
bounded retry with original deadline. Final focused3 PASS13.722s and independent
combined18 include both fixes. Artifact text still cannot invent retry authority.

Next source audit found baseline preparation still emits manifest1, while the
new guarded Trial path supports native4 with a real paired view. Preparation
precedes candidate/view creation; it cannot use an invented view or legacy
fallback. Explicit native baseline support is outstanding before materializer
activation/whole-pipeline qualification. Read-only plan is in the native-admission
ledger/materializer-next.md. Actual default installed closure inventory is next;
then baseline/view/role materializers and closed dummy-only qualification policy.
No source activation, account retry, deploy, registration or M2 completion.

## Current continuation — parent final independent execution approved

Independent reviewer m2d1_whole_review completed parent10 PASS4.312s and actual
isolated SDK-env1 PASS1.259s with all five source/test pins and driver unchanged.
No skips, native child or account calls. Scoped parent/adapters review is clean;
it excludes that reviewer's own runner code and all new admission callers.
Public native-parent-adapters now records these exact independent log/report
hashes. Earlier pending-agent statements below are historical. Root retains the
serial test slot for the three frozen-plan admission callers' RED/GREEN work.

## Current continuation — first two actual admission callers bound

Trial owner admission and operation reserve now bind existing M0/owner authority
before native verification. Original SQL/plan/available-slot/source checks repeat
inside decision transactions; no synthetic attempt/call is created for preflight.
Operation stale generation, nonpending state or prior attempt refuses before
native observation. Historical replay remains cold. Meaningful RED5 FAIL10.378s,
final author5 PASS13.571s and directly affected legacy39 PASS106.280s. One earlier
expected-exception fixture mismatch is retained in evidence; existing Trial
ValueError(trial_native_unavailable) contract is unchanged. Public
native-admission-first2 pins the three files and all logs. Independent caller
review and seven remaining synchronous caller bindings are still due.

Earlier four implementation units are committed locally as35997184,03ce75f0,
52a68927,3d0a02da. PR803 is still on historical4ba9624a; neither early portable
CI nor the old native registration qualifies this branch. Parent final execution
review is handed to the available independent reviewer under the sole serial
app/native slot. No native/account retry, activation or deploy occurred.

## Current continuation — guarded parent, result consumers and closing evidence

Release inventory has scoped independent approval10 PASS2.507s after two real
parsed-METADATA/RECORD mutation reproductions were corrected. It binds declared
source/import/runtime bytes; the external reviewed registry remains empty.
This is neither an import sandbox nor full installed-closure qualification.
Public native-release-inventory records exact hashes and evidence limitations.

Actual parent/adapters pass final author10 (3.985s), isolated actual-SDK builder1
(1.040s, engineering Capture/IO), affected legacy adapter7+2. Independent static
review's query-environment finding is fixed: only query has the three SDK-added
keys. Its final independent execution remains pending because that agent hit
the account usage limit; author execution is not relabeled as independent.
Static admission precedes any guarded preflight; actual M0 authority and full
attempt receipt/config/capability bind all four image decisions. Bound older
inputs refuse before fallback. Public native-parent-adapters states this boundary.

Actual result/check consumers have independent root19 PASS68.323s on final pins
and affected legacy7 PASS12.305s. They require complete observation2 history and
all four exact encrypted M0 decisions, reread inside final publication, and retain
cold historical reads after cleanup. Pure historical query-environment relation,
provider acceptance, comprehension and internal reasoning remain UNKNOWN.
Public native-result-consumers preserves source-policy and lazy-reader fixes.

Actual runners have clean independent static review and independent root19
PASS74.671s on final pins; affected legacyTrial3/Operation2 pass. Original raw
envelopes, sequence and usage survive storage error, revocation and repeated
cancellation. Late retry uses original writer/attempt after abort, never a new
lease or image allow. Recorder mutation is isolated by a separate copy.
Public native-runner-evidence records exact fixture/native coverage limits.

No source activation, account retry, deployment, registration or milestone
completion occurred. Next: bind actual admission/reserve preflight callers to
fresh M0 authority, then materializer4/2 and closed dummy-only qualification.
Final exact source closure/native qualification and final-head full CI remain
mandatory. Goal M0–M8 stays active; business and rollout gates remain open.

## Current continuation — actual profiles, startup2 routes and exit status approved

Historical native decision reader is independently approved4 PASS.891s after
meaningful missing-API RED4 and author4 PASS.865s. It rereads actual M0 event and
exact encrypted join bytes, supports same result-publication transaction, and
does not rerun live authority or write. Shared attempt_scope binds full stored
receipt/config/brain/identity/capability. Existing persist method AST unchanged.
Actual independent result/check integration is in progress; no native proof from
an allow string. Public native-decision-reader records hashes and coverage.

CI readiness: NativeSDKTests now has the same isolated-Windows marker as its
actual production runtime requirement. Reviewer verified all method bodies AST
unchanged, sys imported; historical genuine isolated-driver proofs remain valid.
This is explicit unsupported-platform skipping, not Linux SDK transport coverage;
pure portable checks remain enabled. Final-head CI and qualification still due.

Owner delegated pilot selection: reconciliation primary, document processing
secondary, Python bugfix/test technical control. No source/activation expansion.

Native input binding aa9ad4ef independently passes8 (1.749s); TrialProfile4
e98e4dca independently passes8 (3.559s), affected legacy15+3 pass. Exact actual
SDK constructor/write binding is covered with engineering native IO; no provider
or comprehension claim. Public native-profile-binding/trial-profile4 evidence.

OperationProfile2 independently passes7 (2.574s), affected legacy3 pass. Actual
fixed worker startup2 routes independently pass14 (2.394s), affected legacy3+4
pass. New profiles bind before options, guarded preflight admits before CLI,
typed accounting ACK precedes query and runtime close precedes worker_complete.
Routes use engineering runtime/session seams; no new materializer emits versions
4/2 and no parent consumer activates this boundary yet. Public operation-profile2
and startup2-worker-routes evidence record exact hashes and limits.

Actual inert Windows exit7 reproduced a false success after worker_complete.
Only execute_worker_v2 changed: after cleanup/closing evidence/cancellation,
completion now requires exact builtin integer zero for worker and guardian.
Independent5 PASS3.435s; affected cancellation1 PASS.176s. Actual drain/closed
status and synthetic usage7/null survive. Public native-exit-status evidence.

Next is actual parent adapter/callback/runner and independent result/check
integration, then closed dummy-only qualification admission. Historical native
registration and early Linux CI remain historical, not current qualification.
No selected-account retry, deployment/live activation or milestone completion.

## Current continuation — manifest4 foundation and early Linux CI approved

Manifest4 readonly foundation independently passes11 .039s after author11 .042s;
68 immediately affected existing checks pass. Root verified all14 explicit final
manifest pins with zero mismatches. Public manifest4-foundation preserves exact
versions1/2/3 behavior and the necessary supported-version test delta2/3/4 vsfuture5.
Untouched old asset correlator remains UNKNOWN for4. No materializer/profile/
receipt/check/result/worker/registry now emits or executes the new version.

Early portable Linux CI40029282316 completed SUCCESS on isolated a86c716e snapshot,
not current branch head. Exact seven portable files still match current checkout;
image14 .156s, private9 .287s and actual POSIX selector1 .030s pass. Full existing
workflow succeeds; public portable-channel-ci records log hash/snapshot/limits.
This closes pending genuine POSIX evidence only, not Windows Selector support,
new boundary qualification or exact-final-head PR CI. Do not reuse this as final CI.

Next concrete work is actual versioned profile/worker/client factory and completed
input-write/session proof, followed by durable image callback/current authority
and result/runner adapters. Static admission must precede every guarded preflight;
runtime close must precede completion. Then add the explicit closed dummy-only
qualification admission before freezing all reachable sources, qualify the SAME
pipeline, register exact bytes, and only then admit configured-account feasibility.
No live activation/deploy/account retry, M2 completion or Goal completion claimed.

## Current continuation — actual observation storage and static admission approved

Commit8f2f5678 contains actual Trial/operation observation2 storage: independent18
PASS28.887s after author18PASS36.286s and affected legacy9PASS. Complete encrypted
history validates before V2 reads/appends/replay; no mixed version, no late lease
renewal, no freeze before actual drained. Public native-observation-storage names
exact pins, O(history) cost, missing-anchor/late gaps and unchanged V1 limitations.

Static preflight admission is independently approved3PASS.039s after author3PASS
.023s; affected observed7 .023s and legacyClaude22 1.817s pass. Current claude
source0696aaa6/test1fbdaa53/public static-preflight-admission prove registration
before metadata and no CLI/auth/capability. Actual isolated consumer must still
invoke it before guarded CLI and verify_observed afterward. No route enabled.

Manifest4 readonly foundation is the next independent source unit, preserving
all old prompts/payloads/hashes and legacy-correlator UNKNOWN. Root continues
actual profile/worker/input-delivery integration; no intermediate qualification,
account retry, final CI or M2 milestone completion is claimed.

## Current continuation — owned environment and durable decision store approved

Commit19e1890b fixes actual engine startup mutation before explicit owned client
construction: author2PASS.876s, independent2PASS.849s, affected factory2PASS.812s
and both legacy startup diagnostics pass. Absent/None factory keeps old startup
override; native factory preserves exact environment, SDK default initialization
availability bound and separate immutable lifetime. Public owned-client-environment
records constructor-sentinel scope, no actual native/account query proof.

New NativeImageDecisionStore uses existing M0 events and encrypted blobs with
two actual-transaction current-authority checks, exact replay bytes, scope/join
hashes and mismatch denial. Author8PASS1.547s, independent8PASS1.688s after missing
unit8FAIL1.151s. Public native-decision-store records synthetic input/current guard
and no enabled production callback. Current callback integration, cancellation
settlement and native provenance remain separate obligations.

Actual observation storage candidate passes new18 and affected legacy9; scoped
independent review is underway. Root verified all10 explicit storage manifest pins
with zero mismatches. No result readers/runners/receipts or native routes enabled.

Read-only worker audit is persisted in the existing integration plan. Critical
remaining points are registration/static admission BEFORE any native preflight,
mandatory runtime close before worker_complete despite common-engine disconnect
suppression, manifest4/receipt4/read-outcome integration, and an explicit closed
dummy qualification policy in final canonical source. The old patched-opener
harness cannot qualify the new path. No intermediate registration/account retry.

## Current continuation — worker/codec approved; actual durable consumers in progress

Selected pilots are reconciliation primary, document processing secondary and
Python bugfix/test technical control, as delegated by the owner. No new business
source access, live activation or owner acceptance is inferred from that choice.

Worker session source95970ef1/testb6c747fe is independently approved13PASS4.889s
after author13PASS4.943s. Internal dispatch now unwinds before outer cleanup,
closing the independently reproduced reentrant-close P2. Commit313aa1eb contains
the component and public native-worker-session evidence. Root verified all17
explicit final manifest files with zero mismatches; no main route enabled.

Pure observation codec source3cd30058/testc9b55432 is independently approved14PASS
.052s after author14PASS.050s, isolated stdlib/protocol only. Commit9b227da2 and
public native-observation-codec retain lexical authority limits. Actual encrypted
SQLite writer/read integration is underway; existing V1 history stays immutable.

Root reproduced a new lost-usage path: fully decoded private usage rejected by
host phase checks vanished before publication. Meaningful RED1FAIL.166s; scoped
fix retains it once in closing evidence without live delivery/authorization.
Author1PASS.188s, independent1PASS.162s, affected host21PASS12.887s. Current host
source5693e2b0/test6587cd56 and public rejected-usage-retention preserve exact
proof and distinguish the initial fixture error. Native/provider authority is
not conferred by this socket-only regression.

Next actual integration is durable observation2 history for both Trial and
operation: stored first-offer/receipt binding, strict active counters, unchanged
lease/writer checks, V2 drained freeze and explicit late gap/unknown handling.
One author owns app/native tests; root/reviewer do not overlap those tests.
Complete boundary qualification/registration and final-head CI remain pending;
historical native20 proof does not qualify changed source bytes.

## Current continuation — guardian component approved; host review and early Linux channel check

Engine bridge is independently approved at sourcef1dcc8ed/testa34a72bd: actual
query/options ignored a trusted profile client factory before2 meaningful REDs;
now optional create_client(options) runs before connect/accountACK, with no fallback
on factory failure. Author2 .842s, independent2 .833s, existing Claude22 1.447s.
Public native-client-factory records the bounded hook, not actual transport proof
or enabled production consumers. New v4 consumers must require/bind it explicitly.

Worker author12PASS4.587s source54e3cee1/testfb093ea1 was NOT approved. Independent
static review found reentrant dispatch cleanup: runtime image_ack->worker.send
failure->worker.aclose->runtime/capture close waits the same image_ack callback.
Reviewer did not run12; author owns sole native/app slot for focused active-runtime
dispatch failure RED, a non-reentrant internal emitter and final affected suite.
No root/reviewer tests run meanwhile. Original missing-json fixture failure and
unknown partial-acquisition cases stay explicit; no production main route enabled.

Latest scoped results supersede pending reviews below: host source5b1c7cf8/
test389a473a approved independently21PASS12.726s after author21PASS12.956s;
commit4d936c0b/public host-native-v2 evidence preserves four P2s/five REDs/history.
SDK source355c03a5/testa1474c45 approved independently22PASS3.821s after author22
PASS3.760s; commit3f998a34/public native-sdk-component evidence preserves both P2s
and all failed candidates. Root verified all10 declared host delta manifest files
and all26 SDK manifest files. Explicit pinsets are not exhaustive import proof.

Root added shared verify_observed(runtime) without enabling a consumer. Missing
method6/20subfail RED then6GREEN; self-review then reproduced3 additional REDs
where asserted pin metadata hid current source/SDK drift. Final source39c6e1ce/
test0023a135 passes author7 .020s, independent7 .018s, existing Claude22 1.488s.
Fresh local source hash/installed SDK metadata must match after closed validation,
with registration first; legacy verify keeps its observer/gates/capability parity.
No CLI/account/model calls. Public observed-runtime-verification records exact
proof. Whole-runtime registration still historical/invalid for changed sources.

Worker endpoint consumer is the next actual unit: author owns ONLY new
native_worker module/test and has sole native/app slot after root/reviewer release.
Missing-module3RED .090s; implementation/real isolated-child adoption fixtures in
progress. No main route is enabled. Actual fixed factory cwd is source.root, while
initial HOME/USERPROFILE/TEMP/TMP/AppData all equal private scratch. Worker checks
source cwd separately; preflight invocation cwd is verified initial scratch, not
repo context. Private startup retains selected login discovery HOME/AppData via
existing worker_environment (never copied); isolated TEMP/state/brain paths stay
under scratch. Runtime client factory, durable evidence2, input/manifest4 and
complete frozen qualification remain open. No root/reviewer app/native tests run
while worker author owns the slot.

Diagnostic Linux CI40029282316 on a86c remains in progress (Docker-size job passed,
Python test step running at last check). Do not call POSIX cleanup GREEN from
Windows/static proof; diagnostic ref contains only seven portable files, not
these newly approved runtime/verifier consumers. Main PR803 still holds local
runtime changes pending complete qualification and final-head CI.

Goal remains ACTIVE M0–M8. Owner-delegated pilot choice remains reconciliation
primary, document processing secondary, Python bugfix/test technical control;
no new source scope, business acceptance or activation inferred.

Local8597d549 commits frozen GuardianV2 source4b9ee58c/test370474d2 with public
guardian-v2 evidence: author25PASS14.978s and independent25PASS15.124s on imageb8.
All66 explicit frozen ledger files were hash-verified; this is scoped engineering
proof, not three-actor/runtime qualification. Earlier failed review remains UNKNOWN
in the evidence; the later deterministic positive does not explain it retroactively.

Host append-only V2 author source0d6263cf/testebfd0703 now has16PASS12.112s on exact
prior channel pins. Meaningful REDs found reused stream-id ownership, indefinite
terminal waiting, ignored short bootstrap writes, and STOP before natural drain.
Bounded natural-drain grace does not replace actual drain/terminal proof. Historical
ConnectionAbortedError/no-drain failure is preserved, not claimed fully diagnosed.
Independent host STATIC review is in progress; no reviewer native run yet. SDK
invocation author owns the sole native/app slot, new module/test only; integration
into actual workers/client/profile/evidence is still required.

Pushed4ba CI40024951291 FAILED only image-channel script:13 tests/errors3/failure1,
cleanup still unproven after shutdown+immediate descriptor close on Linux. Root
added a POSIX Selector pre-close wait for actual uncancelled tasks in both image
and private endpoints; default Windows Proactor path is unchanged. Static scoped
review approves imagefe5933c9/privateee05c29a and new POSIX fixture9638aa3e.
Windows Selector diagnostics failed and are preserved; Windows Selector behavior
is not claimed supported/proved by the Proactor qualification. The POSIX-only
fixture is explicitly skipped there. Failure-only fixture drain is bounded and
never part of its positive uncancelled-completion assertions.

To check Linux early without publishing unfinished native profile changes,
seven exact portable source/test files are on diagnostic ref
codex/agent-skill-improvement-channel-linux-check, snapshot
a86c716e7ae1ff222b5d66c20b9d4254e609d231 over pushed4ba. Existing full CI40029282316
is running there. No new PR/workflow/deploy was created. It is component evidence
only, never final Goal CI. Actual Linux result remains pending; do not call the
Selector fix GREEN yet. Existing83-source qualification/registration stays
historical; complete runtime freeze/new qualification still gates main PR803.

The following entries preserve earlier checkpoints; newer exact pins above take
precedence where subsequent work changed a dependency.

Shared protocol/endpoint proof is committede2380bd7 locally. Guardian independent
25 attempt stopped failfast after7tests1.328s: first6incl canceled-control fix pass,
delayed50ms native marker missing; exact cause UNKNOWN. One assigned later diagnostic
passed1.608s but leaves that failure unresolved; current trace showed only3ms gate
margin at hostauthorization. Approved TEST-ONLY split now asserts unused receive
task/owner/channel deadlines remainNone afterdeliberateidle, then uses actual
production8s gate for unchanged native/image/terminal positive checks.

Reviewer also traced same real raw-task cancellation flaw into existing image
channel dependency. Root reproduced1REDerror0.060s and corrected sticky unknown
after actualsocketclose. New14PASS1.505s, independent14PASS1.507s/no warnings on
sourceb8a5a50b/test8f12da2d; existing13assertionsunchanged. Historical13 remains
history, no blanket update. Public image-channel-cancelled-io records negative
owner retained across retry/processdrain. Guardian author now has sole native/app
slot for ONE consolidated25 on source4b9ee58c/test370474d2/imageb8a5a50b; final
native review remains pending. Root/host have no active app/native tests.

Latest: independent guardian static review reproduced false control.closed after
cancelled logical recv, before running native24. Reviewer found no other actionable
ownership issue; author has sole native/app slot for narrow correction and final
affected regression. Historical f33a24 is not approved final source. True native
quiescence remains independent of unknown metadata control IO; no blanket fence
reorder. Earlier5563 CI40022263716 now succeeded, pushed4ba CI40024951291 still runs.

This continuation is progress: closed startup2/private2 protocol11 and shared
owned private endpoint9 now have meaningful RED/GREEN and independent scoped
approval. Source9ddcd57c/testf2147bee pure11PASS0.016s; endpoint sourced5498531/
test1cd4a33e independent9PASS1.251s. Endpoint review reproduced settled stream
task/plaintext accumulation before fixing it; consumed completed operations are
pruned, uncertain IO retained. Captured pre-cleanup task refs verify EOF/cancel
completion after pruning. Public private-native-protocol/private-worker-channel
records exact pins/commands/failures and explicit no-authority/unknown limits.

The two new tests ran concurrently with guardian only after documented isolation:
pure stdlib values, or anonymous private socketpairs with OS-assigned ports in a
separate isolated process/loop; no app/SDK/HOME/env/DB/sharedfiles/native children.
No generic parallel test approval is inferred. Actual app/native tests stay serial.

GuardianV2 author24PASS14.572s on f33a7dc3/test958d35da/driverdef67a76; session18714
is terminal and released. Reviewer now owns its sole native/app slot; final review
pending. Earlier failed full11 had cleanup errors/stale creator-thread events;
actual repeated TerminateProcess after successful TerminateJobObject was corrected
without treating termination as exit. Full root/debug/native/job/guard/fence terminal
predicates stay. Short frame/authorization budgets are separated from immutable
overall lifetime<=300 (the existing public trial/experiment/operation maximum).
Fresh image channels arm only on public socket readiness, so later purposes do not
expire during earlier preflight steps. Actual delayed-unused-channel test passes
1.966s with short.05, delay.10 and lifetime5; initial lifetime1 correctly expired
because full Windows startup itself took longer. No234s sleep/timeout policy cut.

Host GuardianSessionV2 source-missing9RED (21 subtest failures) passes no fixture
execution; author now appends the concrete three-actor consumer, preserving V1,
while reviewer checks guardian. Host test814415aa; originaltransport29b34bdf;
red log9db6f3d3. Root owns shared protocol/endpoint; host author owns transport/v2
tests; guardian author owns lifetime/v2tests. Host native GREEN waits slot handoff.
Actual source confirms SDK connect occurs before before_query/accounting ACK;
worker_ready needs adapter_version/auth_status, engine_start_requested needs all4
image gates, then accounting ACK gates client.query/user input. The host's initial
contrary unrun draft was corrected before production edits/tests.

Pilot choice remains owner-delegated: reconciliation primary, document processing
secondary, Python bugfix/test technical control. This selects work types only;
business source scope, owner acceptance and live activation are not inferred.

Pushed4ba9624a76cd4bfb54d3d229263baa223944383b includes image metadata channel
57fea085 and the fixed worker factory; CI40024951291 runs on that exact head.
Reviewed owned-verification commita1920608 is local, not pushed yet. Keep the
exact current-native-registration test intact while the whole changed runtime
boundary is unfinished; qualify/register the complete frozen boundary before
publishing those runtime changes. Do not rerun old native20 on intermediate code.
The atomic fixed worker factory now has independent scoped approval:17 collected,
16PASS+1Linux-onlyskip2.098s on source672d55e8/test0624ea4d. Real acquisition and
close-result failures were reproduced and corrected before approval; only actual
native CloseHandle FALSE permits retry, while ambiguous post-success errors stay
unproven. Factory17 is inert fixed-base Python/pipe/job engineering evidence, not
actual SDK startup, original pipe sealing or full guardian/debug/job drain. Public
fixed-worker-launch evidence preserves all historical failed attempts separately.

Next canonical GuardianV2 API/schema is settled in the existing dispatch plan;
missing-component11RED is recorded and implementation is underway without runtime
enabling. A separate real cancellation gap was reproduced in both actual adapter
generators and both actual runners: verification threads outlived their cancelled
caller. Existing settled ownership now keeps the thread and execution lifetime;
focused4 pass; affected TrialRunner25/OperationRunner15/Claude22 pass sequentially
in30.704s/75.389s/1.534s. Independent focused4 pass on all7 unchanged pins in
0.344s/2.080s/3.463s with no findings; public owned-verification records commands,
hashes, REDs and limits. The first too-short
runner observations passed before cleanup finished; stronger waiting reproduced
both original failures, preserved separately. These four changed PROFILE_SOURCES
invalidate04c8 as a current qualification. Its20/nativeSkill evidence remains
historical; no registration/account retry until the whole changed boundary freezes
and qualifies. No new account/SDK/provider invocation or live use occurred.

CI40019712830 at326c succeeded. Earlier5563 CI40022263716 was still running at
last observation; neither earlier result qualifies4ba or local/working changes.
PR803 body now reflects the pushed channel/factory batch and local runtime work.

GuardianV2 first implementation collected11:2 contract pass and9 Windows setup
paths refused before launch_offer in1.639s. No passing native integration evidence
is claimed. V2 must avoid sandbox._private_directory because it launches ACL
helpers outside the job and imports broader host dependencies. Approved correction
creates exclusive/fsynced markers only beneath existing authenticated private lock
parents, with ancestry checks; authenticating those parents is a host-consumer
precondition. No missing broad parents, ACL subprocess or new security framework.
Author owns lifetime source/v2tests and has the sole test/native process slot;
parent/reviewer have no active tests. Corrected implementation/review remain open.
Fresh-thread DebugSetProcessKillOnExit(TRUE) also refused WinError6 before creation;
primary Microsoft documentation confirms an existing debugging connection is
required and TRUE is the default. Approved order uses a fresh dedicated creator's
default at creation, then explicitly enables TRUE before any Resume/private release.
First actual inert root case now passes1.231s with stdio sealing and root/debug/job/
fence/control drain; remaining image/negative cases and review are still underway.

## Prior continuation — canonical capture/bootstrap committed; metadata channel verified

Current pushed head5563ab908bc7bd56e94a001dff4d1ef070d50535 includes query-policy
7f710bbc and independently approved capture/bootstrap. All eight newly committed
source/test Git blobs exactly match their tested worktree bytes. New CI40022263716
runs; older ffcd CI40016579262 succeeded, while326c CI40019712830 still runs.
Earlier CI cannot qualify the new head. PR803 stays draft/reserved0.299.0;
no merge/deploy/restart/selected-CLI/account retry/live activation occurred.

Prior checkpoint326c9d9ea0b49f4a7c1cfb1dcfc03031732807d4 added the approved
borrowed-file API and public importV2/guardianV6/D2 audit evidence to PR803. Current
head/CI are recorded above. PR body preserves successful limited inert probes and
their historical failures. No merge, deployment, restart, selected-CLI/model/account
retry or live activation occurred.

Canonical NativeDebugInvocation now exposes the SDK's actual async process interface
with a persistent samecreator pump through EXIT and exact one dispatch. Initial9
RED/GREEN preceded a real privacy/strict-ACK finding, then2 RED tests with7 expected
failures and corrected11GREEN4.226s. Independent isolated11PASS4.300s approves
source902ba370/helper54dd2ed7/testf712dd9e with7 unchanged evidence/dependency pins;
all83 qualified source pins remain unchanged. Public canonical-native-capture
records retained/retryable cancellation/error/handle/ACK ownership and limits.
No runtime consumer/profile entry, image validation, full job/worker-death or SDK
query proof is implied. Existing plan records the custom SDK transport
integration consumer, stable capability versus per-invocation proof separation,
owned async verification and explicit host-preflight lifetime requirement. Full
guardian/bootstrap/control integration remains open.

Query grammar now explicitly separates pin2 fixture_only/pinned_skill policies,
without granting role or execution authority; old pin1 schema/full result bytes
remain unchanged. Pure8 RED-to-GREEN pass0.008s, affected17 pass0.433s, independent
sequential17 pass0.458s and8 pass0.011s on unchanged266b75f1/fe73ba59/aee418b0 pins.
Public query-dispatch-policies records the first deep-temp Windows269-char failure
and unchanged-source short-temp passing rerun. No runtime caller/profile change.
Bootstrap fixed-entrypoint/framing/declared-file verification now passes12 tests
plus1 Linux-only skip in0.196s; independent same13 collected12PASS1skip0.213s approves
source7d1a69f0/teste25ebc72 and unchanged public guard dependency4fc9654a. This is
controlled in-process Windows file/module verification with simulated isolation
flags, not actual isolated direct-base child startup. Public native-bootstrap
records fixed targets, exact framed stdin/no-overread, verified captured target
bytes and retained close-error ownership. Unlisted-import exclusion/initial loaded
sections stay UNKNOWN; external qualification must authenticate bootstrap/manifest
completeness. No production caller/profile entry or SDK/native-child call.

Query policy delta7f710bbc was batched with approved capture/bootstrap in one push;
its three Git blob IDs exactly equal tested worktree bytes. Capture author freeze uses37 explicit
files; an initial broad glob accidentally included an open reviewer log and failed,
preserved separately without source/test changes. A genuinely asynchronous closed
metadata channel is the next consumer prerequisite; the current capture callback
does not promote blocking stdin reads into cancellable IO.

Metadata image channel now passes13 tests in1.588s and independent13 in1.447s;
source12cce111/test2df8f4fa unchanged and no warnings. First13 failed1/3errors because
shutdown alone did not settle Windows WSARecv; its failed source/log remain preserved.
Corrected order is poison→shutdown→known socket close→UNCANCELLED IO completion
before closed=true. Lost close authority stays permanently unproven; the negative
test's real socket is closed/no IO pending, but retained proof-owner is not called
success. Public image-metadata-channel records framing/strict metadata/binding/
partial IO/replay/cancel scope and23-file author freeze. No children/SDK/account
calls, cross-process endpoint transfer or runtime/profile entry. Initial
worker creation/assignment also needs a concrete no-orphan lifetime: a host crash
between suspended Popen and guardian/job assignment must not be ignored. Guardian-
first fixed worker creation with transient private-pipe capability copies closed
before host writes private data is the settled integration direction. Use a
guardian-only direct CreateProcessW JOB_LIST/HANDLE_LIST factory for atomic creation
assignment, with exactly three inherited stdio pipe capabilities and no inherited
job/control/socket metadata handles. Future socket.share transfer follows retained
actual process identity. Factory implementation/tests are next; old SDK capture,
bootstrap and83 qualified profile remain unchanged until actual integration.

## Previous continuation — query validator committed; startup import measured

Commit ffcd1b44ee7d021be70ab5803ac0d9a3d8c7875a is pushed on PR803; staged
source/test bytes matched the approved9831cd30/f53eb9fd pins. New final-head CI
40016579262 is in progress. Main remains0.298.0; open PR805/807 have no reserved
version, so PR803 retains0.299.0. No merge/deploy/restart/account retry occurred.

Separate once-only startup import diagnostic V2 completed both predeclared
variants in4.219s. Minimal-root reproduced ModuleNotFoundError:pywintypes, exit10;
explicit trusted win32/win32-lib paths plus a retained DLL-directory handle
imported SDK/anyio successfully, exit0. Both original retained direct-base worker
PID/birth identities matched before import ACK. Actual native-job pre/post
snapshots retained the same two members/incarnations and cumulative total2;
rejecting CreateProcess counter stayed0. The additional actual job member's
observed image path was System32/conhost.exe; current reopened-file bytes are
recorded, not loaded-image/page proof or an inferred role. All four retained
process handles signaled before job close; both actual jobs drained to active0.
No SDKClient/connect/open_process, CLI/model/account/provider call occurred.
Report129805b2 and manifest46216676 preserve the result. Historical V5's lost
startup error remains UNKNOWN. Independent limited static approval verifies175
frozen files,25 source pins,4 prior manifests and83 qualified pins. Future
cleanup-failure handling must also retain observer-handle dictionaries; that
unexercised path is not proved by the two completed normal drains. Public
startup-import-support records the scope.

The separately authorized V6 guardian receipt probe subsequently passed all four
predeclared inert cases in one6.683s run: selected image allow, identical-byte
foreign-file refusal, EOF before ACK, and worker death while CREATE held. Actual
remote object duplication uses the original retained worker; process/thread
incarnations, exact job and file-ID/hash match are checked before the one bound
allow ACK. Death keeps guardian duplicates valid and observes native terminal
before outer-job termination, without foreign Continue. All actual jobs drain
before guard release. Report70d56f53/manifest203d504b are independently approved
as limited evidence:208 frozen files,165 report/runtime pins and83 unchanged
qualified pins verified. Public guardian-image-receipt preserves both positive
proof and limits. No SDKClient/Claude/account/provider call occurred. This is
trusted creator capture plus guardian object checks, not independent kernel
association, full three-actor confidentiality, SDK query/configuration or all18
eligibility. Generic failure/repeated cancellation/recovery remain unproved.

Public ImageReadGuard.compare_file_handle now compares actual full file identity
and privately reopened synchronous bytes without reading/seeking/closing the
borrowed handle. Three meaningful missing-method RED cases preceded implementation;
the full35 tests (original17 unchanged plus18) pass2.033s and independent35 pass
2.702s. Both scoped reviews approve source4fc9654a/test8c7abdc7; all83 qualified
pins unchanged. Private close failure invalidates attestation and retains retryable
reader ownership. Public borrowed-file-comparison evidence records the byte-bound,
non-deadline limitation and UNKNOWN debug origin/loaded image/metadata exclusion.
It remains unreachable/outside PROFILE_SOURCES. Historical V6 stays frozen at
ffcd/ab6; the changed API is not retroactively qualified by that experiment.

Source audit also identifies an operation-specific blocker: actual_input_use and
actual_reasoning are always UNKNOWN, and combined semantic verdict correctly keeps
them UNKNOWN. The existing plan now requires separately versioned exact user-frame
delivery capture plus qualified local-provider content verification; stdin success
alone is pipe delivery, not a native read ACK or comprehension. SDK string-query
wire session default differs from native init session, and init may precede query
write. Preserve both namespaces and all old operation1 reports/UNKNOWNs. This is
an integration requirement, not new runtime input-use proof. Sync host/worker
preflight lifetime integration and three-actor control remain open.

Read-only full-D2 consumer audit at ffcd found reusable explicit Team/task/firing
identities but additional gaps: workflow local traces are not bound/passed into
node executors or resume; loops lack a durable pre-execution cycle ID; Goal
operation identity is dropped by its text-only engine factory. DM native session
history lacks effective-view identity, and ordinary warm_ping rebuilds options
outside a turn. turn_context.execution_metadata is Team/improvement-specific and
must not become a generic pin authority. Keep separate immutable host bindings
and durable task/session pins, preserve ordinary owner policy and Goal text-only
permissions, and never install task overlays into the global capability registry.
Existing disabled-routing/per-read proofs are reused; full D2 remains open.
Concrete consumer/function anchors and limits are recorded in
`../evidence/2026-10-24-m2d2-consumer-context-audit.md`; this is source inspection,
not runtime task/session-pin evidence.

## Current continuation — read-outcome foundations and actual anyio gate, 24 October

Versioned native skill reads are committed/pushed ea74d62e and unreachable
read-outcome foundations df0e24b1 on PR803. The exact83-source profile04c8c77b
remains unchanged. Latest CI40013889560 at df0e24b1 is running; Docker size,
byte compilation, actual main import and dashboard JS passed, full Python check
pending. No deployment or account retry.

The next plan preserves input/receipt3 UNKNOWN semantics and introduces future
input/receipt4 only when complete dispatch/outcome integration is ready. New
standalone PinnedReadOutcomeBroker reuses actual skill/fixture decisions and
emits immutable ten-field envelopes/observations. New pure correlator validates
underlying pinned payloads and actual native call/result identity/session/bytes;
None supports derived success only with exact unique host/native delivery.
Absent raw flags stay UNKNOWN, explicit errors cannot be overwritten, and
verified denial is boundary evidence rather than a successful skill read.
No execution caller or new PROFILE_SOURCES entry exists yet.

Author15broker/24proof RED-to-GREEN checks pass; independent sequential15PASS
0.072s and24PASS0.112s approve the exact four files and nine readonly dependencies.
All83 qualified source pins remain unchanged; no native20 rerun is necessary for
these unreachable components. Public read-outcome-foundation8700030d records
hashes and limits. Actual input4/receipt4 integration/qualification remains open.

A separate once-only inert probe uses the SDK-imported anyio.open_process on
the actual creating/debugging OS thread. Three cases pass in2.516s: selected
image, identical-byte foreign image refusal and real cancellation before a local
image ACK. Actual CREATE hFile identity/hash, process/thread incarnation/exact
job, continued debug EXIT, anyio wait/reader/aclose and job drain all precede guard
release. Independent limited static review verifies29 artifact/runtime/source
pins and unchanged83 source pins. Public sdk-anyio-image-gate retains original
V1 failure and V2 bootstrap-resume distinction. No SDK client/query, selected
CLI/account/provider or guardian IPC ran. Guardian receipt/ACK/drain, worker death,
full SDK/configuration proof and all18 eligibility remain unqualified.

The separate two-process V4 probe failed its exact-source-worker check: retained
venv launcher15128 differed from executing worker23332. No remote duplication or
ACK occurred. Actual outer job drain completed before guard release; independent
static review verified29 frozen entries and83 unchanged qualified source pins.
The failed report e9e73a48 and manifest54ed1d8a remain immutable. A separately
planned V5 direct-base -I/-S bootstrap also failed before its first worker receipt;
report33c3c92d preserves that failure. Stderr was discarded, so its historical
startup cause and worker exit code are UNKNOWN. Job drain preceded guard release.
Independent static review verified41 V5 frozen entries and83 unchanged qualified
pins. Public guardian-image-probe-failures records both runs. Neither run proves
a successful guardian handshake/death case.

Static dependency tracing found that MCP imports pywintypes/win32api/win32con/
win32job, normally resolved through pywin32.pth paths and DLL bootstrap. V5's
explicit site-package root does not include those paths. A separate import-only
diagnostic with startup/error capture is being prepared to test this hypothesis;
no further native image run or automatic account retry is authorized by a guess.
The new pure query-dispatch parser passes16 author checks after16 missing-module
REDs (0.002s then0.424s; invocation1471/1777ms). Independent scoped review approves
the exact source9831cd30/testf53eb9fd with16PASS0.420s and11 unchanged dependency
pins. Actual bound3 options and SDK116 command construction pass at medium/high;
fixed Windows paths are synthetic serialization fixtures, not actual dispatch.
Closed raw-command/configuration/JSON/override and mutation checks pass. Public
query-dispatch-foundation records the evidence. It remains unreachable, outside
PROFILE_SOURCES, and all OS/image/provider/internal reasoning coverage is UNKNOWN.
No native20 or unchanged39 read-outcome rerun was needed. Final-head Linux CI
remains required. The import-only diagnostic V1 subsequently stopped before SDK
imports: direct-base PID/birth matched the retained worker, but actual job
accounting was total2/active2 rather than the experiment's assumed total1. No
import ACK was sent, second variant was not run, exact job drained to active0,
worker exit91/stderr0 were saved. Report c4b5d553 retains the failure; the extra
member identity and historical V5 startup cause stay UNKNOWN. Next step is actual
job startup-member identification and a pre/post import birth/membership
measurement, preserving exact worker/image/guardian checks. No blind rerun.

Full Goal M0–M8 stays active. Pilot work types remain reconciliation, document
processing and Python technical control; business-source/owner/live gates stay
open. Continue actual guardian ownership and version4 integration, then full
D2/E/F/M3–M8. Reserved0.299.0; final-head CI/review/integration still required.


## Current continuation — native skill reads, 24 October

Owner delegated pilot choice: reconciliation first, document processing second,
Python bugfix/test as the technical control. This is a work-type choice, not
new business-source access, owner acceptance or live activation permission.

Fresh linked v4 materializations now use input manifest3 and receipt3. The
prompt supplies an exact read descriptor; a second closed readonly MCP tool
serves only immutable pinned skill bytes. Old manifests1/2 retain exact prompt,
hash, tool and receipt behavior. Operation roles remain fixture-only. Both new
reachable broker/proof modules join the exact native footprint, now83 sources;
the historical972175a2 registration does not authorize this changed footprint.

The pure correlator joins actual native call/result IDs, initialized stream
session, exact arguments and unpredictable broker response IDs/text/hash.
Receipt summaries are independently recomputed by the checker. Available,
selected, observed read and comprehension remain distinct; no comprehension
claim. Missing native optional error flags stay UNKNOWN. Full18 and actual
reasoning gates remain unchanged.

Review found two mixed-valid orphan/replay cases: reproduced14 tests/2FAIL,
fixed14PASS0.061s. It also caught the shared operation-inventory signature
regression and two qualification-fixture issues; all are corrected. The exact
83-source footprint expectation is updated without weakening its set/hash checks.
Sequential affected verification:133PASS197.876s subprocess wall on unchanged
product sources, with qualification-fixture-only repairs between records.
Independent final proof14PASS0.040s + native-skill11PASS3.386s, source/test hashes
unchanged; scoped review approved. Raw records/logs live in the native-skill-reads
ledger. Actual native qualification20PASS93.952s on the frozen83-source
profile04c8c77b with dummy auth/local providers. Both paired arms return the
exact host response and candidate foreign read is denied. Actual success
is_error is absent/NULL; explicit denied-read error is TRUE. Coverage therefore
stays UNKNOWN. A single exact registration was added after proof;7metadata
checks show1RED0.129s then7GREEN0.126s. Independent registration audit APPROVED,
7PASS0.127s;83source/6test pins,3raw/4logs/full1183-file record verified. All6
prior entries and lookup/unrelated fixture ASTs remain unchanged. The profile
source was not changed by registration, so no native20 rerun is needed.
No selected-account call has been retried. Public native-skill-reads evidence
9b745a63 and native qualification bf793edf preserve the exact source/log pins.

Separate inert debug-image evidence preserves V1 failed before first Resume.
V2's distinct pre-user-mode CREATE gate binds actual hFile volume/file ID/hash
to the retained guard, accepts the selected image, and refuses an identical-byte
foreign file with zero output. Actual EXIT/job/process drain precedes guard
release. No SDK/Claude/account ran in these probes. Guardian confidentiality,
SDK creator-thread/debug-pump compatibility, death/cancel/drain and native
configuration coverage remain unqualified. Public debug-image-handle record
and hashed confidential-guardian design addendum preserve these limits.

Main fetched again:0.298.0; open PR805/807 have no reserved version, PR803 keeps
0.299.0. Bilingual changelog validation passes. Current delta is ready for
commit/push and final-head CI, with the full Goal still active.

Goal M0–M8 stays active; genuine configured-account pair/final, full D2/E/F,
M3–M8, business evidence and live gates remain open. PR803/reserved0.299.0,
final-head CI/review/integration still required. No deploy/restart/live activation.


## Current continuation — immutable skill broker and Linux fixture repair, 24 October

Standalone SkillAssetBroker now validates/fixes one materialized v2 manifest,
trial/attempt/input and view/asset hashes, serves exact immutable bytes and
retains unique read IDs plus exact emitted response/hash for future native
correlation.12 author testsPASS0.030s; independent parent source review approved,
separate12PASS0.703s subprocess on frozen full maps. No native observed_use is
claimed before actual ToolUse/ToolResult/session correlation. No native caller
exists yet; add this module to PROFILE_SOURCES at eventual integration.
Public broker397a6aad; pure synthetic component, no SDK/account execution.

Actual LinuxCI40002516501 at01717332 failed only the new view-observation fixture:
its inert binary was created inside a protected skill folder after provenance
froze, legitimately changing Linux directory ctime. Test-only staging now uses
an independent external temp directory. Portable actual entry-clock proxy gives
matching2RED27.959s then2GREEN29.127s; ordinary Windows2PASS29.016s and binary11
PASS0.765s. Independent portable2PASS29.468s approves the exact fixture diff.
All assertion ASTs and product source remain unchanged; full actual Linux CI
on the final head is still required. No authority normalization/checker relaxation.

The subsequent inert image-name probe7293fe21 binds actual held-leaf hash to
resolved kernel NT image name in a positive junction-alias case and refuses a
different identical-byte copied image before resume, then drains. Independent
review keeps loaded-image identity UNKNOWN: name comparison is not file-object
identity and guardian does not own the guard yet. Public db56a10b. Next small
candidate proof is actual CREATE_PROCESS_DEBUG_INFO.hFile with file identity,
then SDK thread-affinity/continue/detach/resume/death/guardian ownership checks.
No debug-path probe has run yet. Native current81pins still972175a2.

Full Goal M0–M8 remains active. Full18 observations, genuine account pair/final,
full D2/E/F/M3–M8, business and live gates stay open. No new account retry,
deployment/restart/live activation. PR803/reserved0.299.0; main lastd3d7cb36.


## Current continuation — native image read-sharing component, 24 October

Current pushedf131d958/PR803/reserved0.299.0 has exact native972175a2 and
independent registration approval; full LinuxCI40005387321 is pending. Main
d3d7cb36/0.298.0 unchanged at last read. Historical29fCI39997792693 succeeded.

Own-file native launch probes expose two false assumptions: metadata-only
directory handles do not exclude write/delete sharing, and retaining a leaf
does not prevent junction entry replacement. Proper flags3/existingtarget
POSIX controls close the earlier flags2 evidence gap. Suspended actual anyio
spawn of inert copiedwhere.exe proves job/thread plumbing, not full SDK or
guardian-held image binding. First help-output fixture failure is preserved;
newroot /R marker controls pass. Attribute-only mountpoint SET still succeeds
on an empty directory even with a read guard; loaded-image/metadata exclusion
coverage remains UNKNOWN. No actual Claude/account call occurred.

New standalone ImageReadGuard owns root-to-leaf real read/shareREAD/NoFollow
handles, refuses observed reparse/path/type mismatch, hashes the held leaf and
keeps explicit UNKNOWN coverage for metadata exclusion/loaded image. Parent17
checksPASS0.250s; independent17PASS0.199s. Two scoped review lifecycle
findings were reproduced then fixed: partial close invalidates snapshots;
failed entry/exit retains cleanup ownership or closes all handles. Fresh
metadata observations refuse detected drift without claiming future exclusion.

This module is not yet reachable from native execution; existing81 profile
pins remain exactly972175a2. No new native qualification/account readiness or
genuine pair/final is implied. Evidence: native-launch-probes and
native-image-guard JSON records; next guardian ownership/full drain and actual
loaded-image attestation before any new proof can PASS. Full D2/E/F/M3–M8 and
business/live gates remain open. No deploy/restart/live activation.


## Current continuation — preparation heartbeat, 24 October

The new actual account attempt on01717332 is terminal: two marked calls, baseline
shapeFAIL/ownerUNKNOWN, valid semantic meaning/dependenciesPASS/nativeUNKNOWN.
First scheduled v4 cell was BASELINE; it materialized/prepared, then stopped
not_run/authority_changed before an engine marker. Its reservation was refunded;
no second cell, genuine pair, selection or final exists.234.0495s scope-ready to
final;8673in/822out,USD0.0658008 subscription-equivalent partial; cash/requests
unknown. Canonical unchanged and all plaintext cleaned. Public evidence5eede64f.

One read-only current host.live_guard + result _guard subsequentlyPASS9.141s.
The exact historical exception is unavailable. Controlled reproduction confirms
a separate concrete scheduling bug: workspace preparation can monopolize the
runner mutex past its lease and block its validating heartbeat. New3 tests on
old source:1FAIL/2PASS8.029s; four-line scheduling fix:3PASS8.786s. Preparation
now releases only that mutex during owned filesystem work; authority checks,
serialized SQL generation changes, execution lifetimes, cancellation drain,
60s lease/20s heartbeat and180s request deadline remain unchanged.

Scoped independent review APPROVED exact runner6c708940/test31cf3f60:3PASS8.917s.
Sequential affected regression36PASS151.454s on frozen full source maps: runner24,
actual synthetic-adapter v4 pair1, owner-service11. Public scheduling evidence
`../evidence/2026-10-24-m2d1-preparation-heartbeat.json`. Changed native footprint
now has20PASS94.829s exact native enforcement at profile972175a2,
CLI309/hash5441781f/SDK116. Public qualificationa84d266d. Metadata6RED
(1 missing registration)0.103s ->6GREEN0.096s; all5 historical entries and
nonmetadata fixture AST remain unchanged. Independent registration audit APPROVED against7e63c26c:6PASS0.100s;
81pins/5qual-testpins/3raw/4logs/fullrecord and all5prior entries/lookup AST
verified. Audit logda67327e, testlogad2d0be5; only2 expected registration/test
files differ after qualification. Final-head CI remains required.
No new account attempt or unchanged retry.
Native observations remain a later engineering unit; actual success tool_result
is_error=null additionally leaves event/side-effect coverageUNKNOWN. No telemetry
default or all18 gate has been weakened.

## Current continuation — bounded CLI observation, 24 October

Working delta on29f5bdd5 addresses repeated CLI hashing in current view reads.
Only create_pin opts into bounded CLI reuse; ordinary source digests remain
fresh. Each hit still opens the file and checks read access, ancestry, size and
descriptor/path identity. Before the view returns, a fresh whole-file hash and
identity must match the original. Scope is synchronous and private per call and
thread, with no native execution or semantic publication. Every original source,
grant, settings, SDK and profile fence remains at its existing site.

New component9RED then11GREEN0.318s; two actual view/capture tests with an inert
observerPASS28.805s (12 observations/two full reads; end-of-capture runtime edit
refused). Seven affected scripts94PASS465.156s on identical source maps.
Independent scoped review APPROVED matching source hashes:11PASS0.350s and one
view boundaryPASS15.010s. Public unit evidence9525fa0c (committed LF bytes).
Actual selected-CLI read-only component:12 pins9.172s/12 full reads ->1.796s/2
full reads, identical pins, no auth/native/model queries. This is not full-pipeline
latency or business evidence.

Product delta committed a8155c63; exact new81-source profilebe4a5866 has native
20PASS94.516s on WindowsCLI309/hash5441781f/SDK116. Public qualificationfd52de7a.
Only one registry entry is added; all four prior entries remain. Metadata5RED
(missing new registration) then5GREEN0.085s. Scoped registration verification is
approved at01717332,5metadataPASS0.119s; subsequent actual attempt is above.
Historicale7 cannot authorize changed source.
No unchanged account retry or deadline increase. Plan:
`../plans/2026-10-24-agent-skill-improvement-m2d1-view-observation.md`.

## Current continuation — raw role artifact boundary, 24 October

Role system instructions now explicitly request final raw JSON artifact bytes.
Strict parser, raw artifact preservation, semantics, owner/grant, unknown, tool
inventory and retry behavior are unchanged. Actual-worker2RED then59GREEN/four
sequential suites226.922s. Prompt delta independently approved atb7a81542; new2
worker checks independentlyPASS1.023s. Evidence:
`../evidence/2026-10-24-m2d1-artifact-format.json` SHA c6a696b3.

The prompt changes the exact81-source footprint: current profilee7aaa5bd has
new native20PASS94.078s on identical full source maps, WindowsCLI309/hash5441781f/
SDK116. Artifact `../evidence/2026-10-24-m2d1-native-qualification-format.json`
SHA c5e0acc9. The prior958 qualification is historical for changed source. One
exact registry entry follows4 metadataRED/GREEN; prior3 registrations/lookup and
qualification fixture helpers remain unchanged. Registration independently
approved29f5bdd5, metadata4PASS0.076s. Final-source CI39997792693 is running.

The fresh bounded selected-account feasibility is terminal: two actual calls,
baseline shapeFAIL/ownerUNKNOWN and valid raw semantic JSON (meaning/dependencies
PASS, native observations UNKNOWN). Views froze. The first scheduled v4 cell
(candidate) timed out180s before materialization/native query; its reservation
was refunded. The second cell was not admitted. No genuine pair, comparison,
selection, selected-final or qualification claim exists. Usage8659in/839out,
USD0.0707556 subscription-equivalent partial; cash/request totals remain unknown.
Canonical bytes stayed unchanged and plaintext workspaces were removed. Evidence:
`../evidence/2026-10-24-m2d1-real-format-feasibility.json` SHA ddc5af2c.

One subsequent read-only profile of current baseline view resolved in10.266s,
without model/native queries or writes: twelve create_pin calls rehashed the
298624160-byte CLI; selection capture took9.246s. This is a measured preparation
bottleneck, not evidence of business gain. Preserve both runs; do not repeat the
account attempt unchanged or increase its deadline. The next unit addresses
redundant binary reads while preserving fresh byte validation and all authority
checks. Prompt compliance improved in this one observation only.
All old failed history/usage stays intact. Source-qualified final-head full CI
and full D1/D2/E/F/M3-M8/business/live gates remain open. Reader fixed5CI39996033610
is running and is historical for the later prompt change, not final-head proof.

## Current checkpoint — 24 October, D2 prerequisite continuation

- Worktree/branch remain M2D1/PR803, reserved0.299.0; main d3d7cb36/0.298.0.
  Latest pushed source3afed521 has approved whole-D1 plus scoped lifetime,
  runtime309, semantic-invalid-output, registry and disabled-routing reviews.
  Exact-head LinuxCI39992114257 is still running; later local changes require
  their own final-head CI. No merge/deploy/restart/live activation.
- D1 exact81-source profile958527ac/CLI309/SDK116 remains registered to native
  artifact1f3391cf,20 tests94.890s. Ordinary router/lazy/hub edits change none of
  those81 bytes. Reuse that proof without repeating native/model calls.
- Actual prior D1 account feasibility made2 calls; baseline shapeFAIL and strict
  reviewer format refusal prevented any view/pair/selection/qualification claim.
  Preserve public90ecc20b and partial usage. Genuine account pair/eligible-final,
  full D1 acceptance and D2/E/F/M3-M8 remain open.
- Pilot choice delegated by owner: reconciliation primary, document processing
  secondary, Python bugfix/tests technical. This selects work types only; it
  grants no new real dataset, owner acceptance or live activation.
- D2 disabled-source precedence was independently approved at3afed521. New
  ordinary read unit uses one stable bounded source for actual hub/lazy, checks
  selected manifest path/header and records exact raw byte hashes. Seven
  sequential local commands pass; new10-test suite9PASS plus1 Windows file-link
  privilege skip, actual Windows outside directory-junction refusalPASS. Scoped
  review, Linux symlink coverage and final-head CI pending. Proof:
  `../evidence/2026-10-24-m2d2-skill-reads.json`. A per-read asset is not a task pin.
- Separate controlled native design experiment: plugin-only permission callback
  FAILED because direct cwd Read loaded the old skill. PreToolUse deny alternative
  passed A and B-only continuation; initial B had0 query requests due fixture
  setup collision, which was fixed without repeating A. Six dummy local requests,
  zero account/model inference. Proof:
  `../evidence/2026-10-24-m2d2-native-design-probe.json`. Owner policy parity,
  Bash/other paths, task/session binding, cache partitions, activation selectors
  and resume remain open; no production adapter support from this experiment.

Latest scoped review of85bf8e68 found one Important/P1: a transient external
Windows junction could return outside bytes despite pre/post lexical checks.
The descriptor repair now authenticates Windows actual opened-handle path before
reading; POSIX uses anchored nofollow component opens and nonblocking leaf open.
Regular-file/size checks precede body reads. Exact original repro is now refused.
Seven affected commands passed sequentially; new14-test suite12PASS/2 Windows
platform/privilege skips. Inside Windows junction remains readable. Evidence:
`../evidence/2026-10-24-m2d2-descriptor-fix.json`. Prior skill-read containment
claim at85bf is superseded; scoped fix review and actual final-head LinuxCI remain
pending. All81 isolated native pins remain unchanged, with no native/model query.

## Identity and authority

- Goal: execute the complete M0–M8 contract in `../AGENT-SKILL-IMPROVEMENT-GOAL.md`.
- Goal source SHA-256: `67061573b8c584d65d0ecf1daa4c56b536c78c07fcc5158cfa090d40ea299afd`.
- Owner process addendum2026-10-23: Goal section12, relayed from chat
  `01a16662-a77c-72e2-9c40-265c5659d5cc`. Applies M2C–M8; original source/hash and
  historical evidence remain intact. Amended Goal SHA-256 (separate identity):
  `558e91848624c2dbc5daf1d5decb64b43b960285ce0416e40099ca63863b2ec8`.
- Agent/skill spec SHA-256: `fceea3d375388eeb0f0e3eada48cc2c74a611b2bfcad9978441a683052b108bc`.
- Team dependency spec SHA-256: `e01014f05bf3e090cc63a52e581049833b292dfe5e77a094bd75d8941504f2ff`.
- Authoritative baseline: `a9ee52ff0d3a1ce0eaa61d18c1b9c83081e21b26`, main 0.286.0.
- Worktree: `C:/Users/admin/.codex/worktrees/agent-skill-improvement-m0/Javis-OS`.
- M0 branch: `codex/agent-skill-improvement-m0`; release0.287.0, PR #794 merged
  `0990331574e617fa1a79cd69fcd7b87d465448c5`; publication39797072172 succeeded.
- Original checkout remains untouched by implementation; only the three relevant source documents were copied.
- M1 engineering integrated: release0.291.0, PR795 straight squash merged
  `9dd7a9f9de3e8fadb338298e0f9743d48e5c1d4b`. Final-head Linux CI39852883192
  passed on independently reviewed e0381902; the merged tree is identical.
  Publication39856024117 succeeded on the actual main merge. No production
  deployment, restart or activation occurred. Earlier reservations, failures and
  checkpoints below remain historical and do not supersede this state.
- M2A engineering published: PR799 straight squash merged
  `cbef2f464932e533825512e8e11c2299e6b3bf4f` as0.292.0. Final-head Linux
  CI39862650038 passed on d4703f34; actual merged tree is identical.
  Publication39865749261 succeeded. M1 main CI39856024098 also passed.
- M2B engineering published0.293.0: PR800 squash47f50f707268681dd4cbe8c7e443945155376237;
  exact-head LinuxCI39880551488 SUCCESS on reviewed2fe944ae. Merged tree is
  identical4e53048721ca658f620a73361b4281326852e3b6. Actual GHCR publication
  39882926274 and Build & push succeeded. Independent whole-B review/recovery
  recheck approved with no open Important/Critical. Fixed-source9-script
  regression passed251s; broad63-script sweep passed1048s across the narrow fix,
  explicitly not used as exact-head proof. Task6 accepted; Task4 positive C+D
  qualification integration, complete M2/business/rollout remain open.
- M2C engineering published0.296.0: PR801 squash2727edcc5cdfab6f2dcf2e2871164f22f2771f92.
  Exact final-head LinuxCI39929264818 passed on independently reviewed d05f4881;
  actual merged tree5712b6ba79720a5a44a43d3cecd85cff84f3cd21 is identical.
  Publication39933347548 and Build & push succeeded. Task9 completed through
  its actual published-source verifier; no open Important/Critical findings.
  Native profile9dcf7184 and21-script regression evidence remain source-bound.
  Historical real feasibility aa51b4b9 still has baseline shape FAIL, semantic
  UNKNOWN and partial usage; it does not establish a business win or live grant.
- Current engineering continuation is M2D1, branch
  `codex/agent-skill-improvement-m2d1` in the SAME isolated worktree
  `C:/Users/admin/.codex/worktrees/agent-skill-improvement-m2a/Javis-OS`.
  DraftPR803 now reserves0.299.0 after rebasing onto main0.298.0; original
  reservation0.297.0 at c4991ec8 remains historical. Plan is
  `../plans/2026-10-23-agent-skill-improvement-m2d1.md`.
  D1 builds shared immutable view identity/source resolution and actual isolated
  candidate probes; full D remains open until production router/lazy/hub/native
  task/resume integration is actually verified. E/F and M3–M8 remain open.
  Task1 started at d00312d5. Closed pure identity and additive schema7 now pass
  the six affected scripts sequentially:104 tests,221.921s. Actual released C
  reader refuses7, while its backup restores exact schema6 history, including
  settled role results/semantic receipts/calls and encrypted bytes. Composite
  scope/immutable guards reject splicing individually valid candidate/receipt/
  comparison rows. Cold metadata neither decrypts nor migrates; canonical skill
  bytes and target pointers stay unchanged. Evidence:
  `../evidence/2026-10-23-m2d1-task1-verification.json`, SHA256
  b9d7c51fd9725111678365f667b4af2168738b73329e89475ba2d700d52f76f8.
  Task1 local foundation is verified; task-done checks committed bytes/logs.
  Checkpoint Linux CI remains pending. WSL is unavailable; the PR workflow now
  fetches actual C2727edcc for its reader test. No real provider/account inference
  or new D native qualification occurred. C's exact34-source native profile is
  unchanged9dcf7184, verified against released C; this does not qualify future D.
  Task2 still owns authenticating encrypted manifests and current source/semantic
  authority plus atomic pair publication/CAS/replay; Task3 owns actual v4 lineage
  and legacy-format exclusion. No metadata row grants execution or live authority.
- D1 Task2 local source/publication boundary now passes five sequential affected
  scripts:76 tests,392.830s. Actual current C/edit/source authority constructs both
  immutable views, with one publication event, generation CAS and exact historical
  replay; second-insert and post-insert source changes roll back all view rows.
  Resolving SQL metadata requires its exact publication event/request/generation
  plus current source and semantic evidence. Holdout inputs and expected answers
  are not decrypted by view capture/load. Actual Windows DACL/junction/incarnation,
  owner arbitration, dependency and byte-format fixtures pass; Linux branches of
  the new source service still require CI. C semantic/native unknown and A's
  unreviewed status remain unchanged. Evidence:
  `../evidence/2026-10-23-m2d1-task2-verification.json`, SHA256
  588f7dba351d6d4253039819179207e467306163b14bfb7447d8c700d08fc41e.
  All C34-profile and selected Task1 source bytes remain exact; there is no new D
  native qualification, API wiring, actual comparison Trial or real model call.
  Task3/4 retain actual admission/native-preflight/reservation/query fences.
- Early Task1 LinuxCI39938959026 on8a25dee9 is FAILURE: new view schema15 and
  protocol11 passed, while test_improvement_candidate_records.py,
  test_improvement_cases.py and test_improvement_trials.py retain old backup/drop
  fixture assumptions. Fix these exact fixtures next; keep backup ordering,
  historical version/data assertions and rollback checks intact. Older
  protocol-only LinuxCI39936301937 on d91cc25b succeeded. Neither run proves the
  newly implemented Task2 source path. PR803 remains draft and not mergeable.
- The three legacy migration fixtures are now corrected locally: exact third
  views-backup entry and child-first removal of view tables when constructing a
  real schema2 fixture. All74 tests in those three scripts pass sequentially,
 34.537s of unittest time. No production bytes changed; AST comparison proves
  every import, fixture helper and other test method stayed identical to the
  Task2 verified commit68dc6c26507841f30e5ead93fe5281aad2afb4e5. This qualifies
  reuse of Task2's76-test proof; it does not replace fresh current-head Linux CI.
  Correction evidence `../evidence/2026-10-23-m2d1-legacy-fixture-correction.json`,
  SHA256641a71c203e8e42d2a09ee51c17195bcf2b1ce2af999fe2f8dc043a73bdaa5e0.
- Earlier pending/failure
  checkpoints remain historical; complete M2/business/rollout gates remain open.

## M2C engineering continuation

### D2 routing-state foundation, 24 October

An independent production-path repair now makes authoritative disabled state
agree across skill discovery and actual body loading. Previously a disabled
canonical skill disappeared from manifests but the actual hub handler could
still read its stale Claude mirror. Same-source enabled/disabled collisions
also disagreed between metadata APIs. Resolver and list_skills now respect
the disabled source before lower-priority enabled copies, including legacy state.
Unrelated enabled-source precedence remains unchanged.

Behavioral RED7 reproduced5 failures; GREEN7 passed0.123s. Actual warmed hub
reads deny after disable without increasing usage; a warmed lazy registry drops
the disabled skill. Five affected scripts passed sequentially in13.392s, including
11 Phase8 pytest cases. No model or native query occurred. All81 qualified native
source hashes remain identical, so exact958527ac/1f3391cf enforcement evidence is
reused. Artifact `../evidence/2026-10-24-m2d2-routing-state.json`, SHA256
56246006f3a4dce8cb58762f648c30380c67b0618dd3b5742dec366da04de610.

Scoped routing-delta review and final-head CI remain required. D1 CI39990661065
on999c207a was running before this new source delta; it cannot prove a later head.
This repair does not implement task/session pins, production overlays or native
materialization. Full D2/E/F and M3–M8, account pair/final-positive and all
owner/business/live gates remain open.

### D1 selected-account feasibility and invalid-output follow-up, 23 October

At54210807, exact qualified profile81/4d346a3a made two real selected-account
calls with unchanged Opus5.5/medium/subscription: baseline TrialRunner and
semantic reviewer,117.817s from prepared scope to final accounting. The baseline
completed but failed JSON shape; owner accuracy stayed unknown. Its full18
integrity checks retained reasoning/asset-use and event/side-effect unknowns.
The reviewer produced fenced JSON missing required `findings`. Strict parsing
refused it, with no receipt, view, selection or qualification claim. The inner
model word `pass` is not an accepted assessment. Canonical bytes stayed exact;
all plaintext workspaces were removed. No model retry or owner arbitration.

Evidence `../evidence/2026-10-23-m2d1-real-feasibility.json`, SHA256
90ecc20bfc31c581292e654f8a4ff68192e77e56ec6caba8f3a1600e536321a0.
Observed usage8569 input/877 output tokens, subscription-equivalent USD0.0707254;
cash and request counts are unavailable and coverage remains partial. These
are technical synthetic calls, with no business efficacy or live authority.
Actual native TrialRunner baseline is demonstrated; the account pair and
genuine eligible final remain unproven.

The failed review exposed a separate operator defect: malformed output surfaced
as generic HTTP503 instead of a stable typed outcome. Actual workflow RED3
reproduced two strict validation errors while the source-revocation test passed;
actual HTTP RED1 reproduced503. A narrow follow-up records `invalid_output` with
the original native result, no receipt and no automatic retry. Parser, prompt,
assessments, native checks and eligibility are unchanged. Five sequential focused
and affected scripts passed63 tests in349.720s on one complete source map.
Artifact `../evidence/2026-10-23-m2d1-semantic-invalid-output.json`, SHA256
4a8d10e966a7931410093822f8b1261f8ecef7c0d01042c8ba27dc36286d9464.
AST proof preserves all other product code and prior test methods; the scoped
independent review approved exact330501fa, with no finding. Its actual HTTP
invalid-output/stop/off/revoke/cold-replay recheck passed1 test in12.336s; log
`review-semantic-invalid-http-recheck.log` SHA256
8a21a9b0c8d756098faa0c00fca79c79cbea40a2860705b016d95d583901327e.
Changed profile
81/958527ac69c3b5728044b22cf6d3bdebb920da7cbe46a9da261e899568ced1ef
passed20 actual native enforcement tests in94.890s on one source map: paired1,
solver5, typed roles5 and quiescence9. The exact309/5441781f/SDK116 tuple is now
registered against `../evidence/2026-10-23-m2d1-native-qualification-outcome.json`,
SHA2561f3391cf9c1bf621d3ef2de44dd181acf17dd7d922fed4a80ae66bef36c8fab4.
Metadata RED→GREEN3 passed0.068s; prior C and D registrations remain exact.
These native suites used only dummy auth/local providers, with no new selected
account calls or quality/owner waiver. Prior source qualification stays historical.
Task3/4/5, D2/E/F and M3–M8 remain open; final CI/publication are not complete.

### D1 fresh-main and runtime309 checkpoint, 23 October

Current draftPR803 reserves0.299.0, rebased onto main d3d7cb36/0.298.0.
All main release history was preserved. Rebased source3e1abcf0 kept all81 native
files identical to the reviewed lifetime fix; one test's single CRLF→LF change
was hash-reconstructed, with other improvement test bytes unchanged. Seven
affected owner-main/voice/route/bilingual scripts passed18.375s. Independent
reviewer closed the sole P2 at23f62b0b after a targeted20.260s real lifetime test;
constructor/view/lifetime source pins still match after rebase.

The installed CLI auto-updated to2.1.309 during final verification. The previous
308 candidate guard refused before execution, as intended. No downgrade or
global CLI modification occurred. The exact309 binary SHA5441781f and SDK0.2.116
were qualified on new profile81/4d346a3ae4f1afa99784fc51307258ad99a8d470ac6a0c46f1d330e6b0e656fa.
Actual paired views1 +solver5+roles5+quiescence9 passed20 tests in96.767s on
identical source maps; adapter guards22 passed1.711s. Actual CLI --version is
checked within the owned hidden dummy job. Artifact
`../evidence/2026-10-23-m2d1-native-qualification-final.json`, SHA256
012d9e37690e8711da75a344dfee0677df8d6c690b90f689ddbb14574c82f295.

The exact registration now points to that evidence; historical C remains intact,
lookup code is unchanged, and altered pin/platform is refused. Metadata RED→GREEN2
passed0.045s. Current source qualification is enforcement-only: all queries used
dummy auth and local providers, observed reasoning/asset use remain unknown.
Reuse/source/recheck checkpoint
`../evidence/2026-10-23-m2d1-source-checkpoint.json`, SHA256
99c01d1afdc91f2516b57a12cecfb81bec13dd184295cfd934a37fd502661253.
The runtime tuple/test-version probe/registration delta was independently
approved at5421080714f78c653e2ab10c17a5e8ee4a613a55, with no actionable finding.
The reviewer verified all81 source pins, retained evidence/log hashes and the
narrow AST delta; two independent registration tests passed0.048s. Retained log
`review-runtime309-registration.log` SHA256
30f47d7034bdb0b1ae42ced51a1e81d221a64bb267df84e0f5819d0749e11b82.
Earlier LinuxCI39982218130 succeeded on740c0c67; final-head CI is still required.
Current selected-account readiness was verified read-only with unchanged
Opus5.5/medium/fastfalse/subscription. Native TrialRunner feasibility is running
in a new encrypted disposable synthetic reconciliation scope; no accepted
business dataset or human semantic arbitration is inferred from pilot choice.
No eligible selected-final, business win, activation, deployment or restart.
Task3/4/5, D2/E/F and M3–M8 remain OPEN; previous native proofs stay historical.

### D1 independent review and lifetime repair, 23 October

One whole-D1 independent review covered published C2727edcc through740c0c67.
It found one Important/P2 and no Critical/additional permission or holdout bypass.
An actual15.456s reproduction showed a rebuilt facade retaining a closed
semantic resolver while its original Trial owner remained live, then failing
current admission with role_workflow_closed. Constructor refusal RED failed
as expected in14.312s. The narrow fix now refuses that half-closed facade and
keeps the original resolver; only both exact successful close futures permit
replacement. Missing/pending/cancelled/failed closure remains blocked.

Actual lifetime4 plus five sequential affected commands passed29 tests,
239.901s recorded. Successful later rebuild/admission and still-live semantic
reuse are covered, along with owner/main/service controls and actual v4 handoff/
cancel. AST/source proof shows the only product change is constructor refusal;
the prior stop/current-source/materialization behavior is preserved. Evidence
`../evidence/2026-10-23-m2d1-review-lifetime-fix.json`, SHA256
fb8333f444f84ac85f03d3f0c71402eb30f599e1a025499802b860739e7d94b5.
Same-reviewer scoped recheck is pending, not another whole review.

Before the fix, profile81/2221a859 also passed full local/dummy solver5, roles5
and quiescence9 in60.609s on one source map. Its source-bound artifact
`../evidence/2026-10-23-m2d1-native-qualification.json`, SHA256
96adabecf47773debc2988098a68cc3a9c592a00ad2ed9b0d8a6e4cab096936b,
is historical after the constructor change and was never registered. Current
profile81/d070550687af101c07094e1234c5988fae15af9318eb5f5277c4cb2e413324ba
remains unregistered; requalify after fix stability. Exact740c LinuxCI39982218130
is in progress and cannot prove the subsequent fix. Earlier ec6CI39976688967
succeeded. No actual account query, genuine eligible final or business/live
acceptance occurred. Task3/4/5, D2/E/F and M3–M8 remain OPEN.

### D1 paired native-view checkpoint, 23 October

Owner controls are committed/pusheddaed0cf26872abe9d6e03f7d8bc59b04c39f8f83.
The new opt-in native-view test passed on the same unchanged product81-source
profile2221a859:39.172s wall, two native queries/separate sessions, four local
provider model messages, zero selected-account calls. Both manifests come from
actual temporary owner/view/Trial materialization with the exact pinned native
configuration captured before the comparison context. Preparation/reviewer
fixtures remain explicitly simulated. Native execution uses real SDK/CLI,
TrialProfile, owned hidden jobs and dummy auth/local transport without an
adapter/readiness stub. Exact prompts/view/assets/receipts, denied ambient/
outside tools, unchanged canonical bytes and cleanup after native drain pass.

The initial harness attempt failed when cleanup_proven's actual ACL metadata
spawn reached the worker-only Popen interception. The original failed log/source
record is retained; keeping that proof within the existing real-Popen scope
fixed the fixture without changing product code or relaxing an assertion.
Sanitized evidence `../evidence/2026-10-23-m2d1-native-view-enforcement.json`,
SHA2560691a727db9dd81b91e814ccfaa4278f04d9c90c5a325cc789b282de31f6a10c.
All server and owner47+route test bytes are unchanged, so that scoped evidence
is reused. Current profile remains UNREGISTERED. Composite solver/role/death/
quiescence qualification, actual native TrialRunner/account feasibility,
genuine selected-final positive, independent whole-D1 review and final CI remain
open. D2/E/F/M3–M8 and business/live acceptance stay open; no activation/deploy.

### D1 owner-view controls checkpoint, 23 October

Actual owner `view-freeze`/`view-evidence` POSTs now accept only comparison ID,
experiment generation and event key. Freeze uses actual immutable publication;
current evidence rechecks authority on every completed-key retry and exposes
source/semantic scope plus unknowns, never a native readiness ticket. Cold
view-binding GET uses the existing metadata store after off/revoke. The service
owns source threads through HTTP cancellation; stop joins them before final
settlement. No automatic next/query or canonical skill mutation is introduced.

On one frozen source map,47 unittest checks plus the actual route snapshot check
passed in9 sequential processes,295.126s wall. Main session/CSRF protection covers
all26 improvement routes. The snapshot changes618→621 with exactly3 additions;
all retained definitions and relative ordering remain exact. The actual lifetime
test rejects a controlled mutation removing the new stop joins, then passes on
unmodified code. Existing B/C owner/stop/lifetime workflows and actual v4 paired
reservation remain green. Operator guide:
`../../dev/agent-skill-m2d1-views.md`. Evidence
`../evidence/2026-10-23-m2d1-task5-view-controls.json`, SHA256
b3a617be7e9eda67398ff166b28ff7ff833908e2f779089bfa670f088b3305a9.
The route snapshot was intentionally regenerated with the direct Python script;
the wrapper does not forward its documented `--update` flag. No product failure
was hidden by accepting an unrelated route change.

Profile81/2221a8599529ac50cf3c9c98057cd003e9dfc45828ac808b5f11e802279511ba
is unregistered; historical C qualification does not apply. No real model call,
selected-final positive, business proof, deployment or activation occurred.
Task3/4/5 and D2/E/F/M3–M8 stay OPEN. Earlier LinuxCI39970471529 succeeded on
c5229ea3; ec6f1d6c CI39976688967 was still in progress at this checkpoint.
PR803 remains draft; independent whole-D1 review and final-head CI are pending.

### D1 Task3 checkpoint, 23 October

Task1/Task2/legacy-fixture Linux CI39944212136 succeeded on exact d81606b5.
Protocol-only676fe8a8 and additive-link ab5dc1ef were then pushed together;
early Linux CI39949800035 is running on ab5dc1ef7d7113befe893618ff79fa1376d1ef91.
The new SQL/format checkpoint passed92 tests in six sequential affected scripts,
378.281s, with retained source/runtime/log hashes. Existing released B/C schema
definitions and C34 native footprint remain byte-identical. Actual v3 Trial
splicing into v4 links, legacy admission after view publication and direct view
publication after legacy admission reject. No future Trial/Call was fabricated.

Task3 remains OPEN: actual v4 Trial/CallLedger dispatch, current-host fences,
bounded stop/recovery/report consumers and existing qualification-registry links
still require implementation. SQL/blob historical view proof is being added
separately; it cannot authorize current files, native execution or live scope.
C's native registration must be invalidated in the same change that makes v4
reachable and the exact final D footprint qualified before actual queries.
The draft PR is not ready to integrate. Business/live/M3–M8 gates stay open.

Subsequent Task3 history checkpoint b755699e passed56 scoped tests (portable
evidence170d0de3). Actual reservation now passes140 tests in nine sequential
affected checks,231.248s, recorded in
`../evidence/2026-10-23-m2d1-task3-reservations.json` (SHA256
bde6b073ae78acbf4e220cd5363fa40fd16e1f4bc5dd3d2ac225cd83a0b8a796).
Genuine v4 baseline/candidate Trials and existing Calls/links are created; source
changes roll back actual reservations, and cold replay stays readable after
off/revoke. No model query/engine marker. Current native footprint is now76
files/51b62052, deliberately UNREGISTERED, invalidating C9dc for this new code.
No default actual native execution can pass until final D qualification. Current
Task3 still lacks complete shared stop/recovery/report/next/admission scopes and
existing qualification-registry ownership. V4 materialization explicitly denies
until Task4 implements it. Task3 and D remain OPEN; no live scope is enabled.

Lifecycle1a09a0e3 then passed28 affected checks (182.812s): stop/refund/recovery
includes actual v4 links under the shared12000 comparison bound, and next refuses
pending/terminal-no-result slots. Owned next now passes71 scoped+affected checks
(401.851s recorded, basis per row), evidence
`../evidence/2026-10-23-m2d1-task3-owned-next.json` SHA256
4d9df2ba736bf8fc736dc2d8e0e19d10b8f24cf406d7ee0dc99684b1aa944221.
Actual brain barrier covers next/source/native-preflight/Trial+Call reservation;
concurrent owner keys reserve once and cancelled HTTP stays owned through stop.
Current native profile is78 sources/058166e7, deliberately unregistered. No real
query or actual v4 materialization. View report/final registry, retained lifetime
audit, actual workspace/native qualification and public controls remain OPEN.
Early Linux39949800035 succeeded on ab5dc1ef; later source needs its own CI.

Linux39952941333 failed52c79f1c only because worker's exact expected source list
still pinned C34. Correction9795f698 explicitly expands it to78, preserves set/
hash equality and adds duplicate/count refusal;9 worker+1 default-denial checks
pass, with no production source change. Evidence43f43c28 qualifies prior scope
reuse, not a fresh final CI. Later dad605c3 Linux39957029202 was already running
before the fixture correction and may retain that exact old failure.

Concrete retained-host reconstruction then reproduced role_workflow_closed.
Resolver replacement now requires both exact typed same-store workflow/owner
close futures to complete successfully. A live owner or missing/pending/cancelled/
failed close refuses replacement, without constructor source/native I/O. Current
32 scoped/affected checks pass276.518s; evidence
`../evidence/2026-10-23-m2d1-task3-view-lifetime.json` SHA256
c56e88ee52a9813711021db8d93984f53594d0ee42bdbb519eab8679dcf7c60e.
Current78-source profilebfda8912 is UNREGISTERED. No real query/native execution,
ordinary D2 task/session resume, business or rollout acceptance is claimed.

Report checkpoint:63 tests passed sequentially in166.953s on one frozen source
map. Real pending v4 Trial/Call links now appear in reports; missing evidence
remains inconclusive. Current owner meaning veto blocks new reporting, while
historical report bytes/hash and cold replay remain unchanged, including the
older metadata-only prototype with no result refs. Full18 integrity checks and
report v1 envelope remain intact. Evidence
`../evidence/2026-10-23-m2d1-task3-reports.json`, SHA256
aabb253c30404d6155ba2bba92981285462da56e9e6439c5218abc363567609d.
Current78-source profile4e3ecee0 is unregistered; final qualification ownership,
actual view workspace/native execution and public controls remain OPEN.
Linux39957029202 failed on olderdad605c3, before the fixture correction; current
Linux39959675109 remains in progress on254a90ca, preceding this report change.
No real model query or business/live acceptance is claimed.

Tuning workspace checkpoint:69 checks passed in171.812s across actual view
materialization4, sandbox, TrialStore, view reservation and worker footprint.
The real linked pair materializes/prepares exact baseline revision/A candidate
bytes with common inputs, without modifying canonical or manufacturing a bundle.
Source edits during solver read roll back the materialization and retain exact
prior exposure rows. V1 prompt/hash stays unchanged; v2 binds its view descriptor.
Evidence `../evidence/2026-10-23-m2d1-task4-materialization.json`, SHA256
87d9d7306dc3226ac3f2a68860bc4277eec699c08535e4ba4892c5aed38d76d3.
Current79-source profilebeddb902 is unregistered. Native v4 receipt/check/result
integration, final qualification ownership and public controls remain open.
No actual native query, successful result, eligibility or business/live proof.

Native identity/pipeline checkpoint:75 checks passed,176.126s recorded with
per-row timing basis. Actual owner schedule/Runner/ledger/products/Fernet results
and cleanup execute one pair using a clearly simulated adapter. Result4 pins
the full request/lineage/view; Profile receipt2 derives from real workspace2.
Full18 check IDs and unknown effort/asset use remain; both simulated results
are non-pass, and comparison selection stays unsupported. Actual histories read
exactly after off/revoke. Legacy checks/Claude/results/v2 execution pass.
Evidence `../evidence/2026-10-23-m2d1-task4-view-execution.json`, SHA256
4d7c1b9f7ea74b27e1b335ae93274561fb8290e2a82915ed61bc66bb54aea721.
Source79/2192bf86 remains unregistered; no real model call/native qualification.
Linux39959675109 SUCCESS254a90ca; Linux39965159570 in progressc811b9d6.
Current result code still requires its own CI/review. Final holdout ownership,
native scenarios on final exact source and public controls remain open.

Before final consumption, an audit found current effective-view capture did not
reuse the improver's global holdout-alias rule. Genuine owner-created case sets
reproduced private reads despite qualification/regression aliases. The shared
unchanged SQL guard now runs before any current view plaintext; existing frozen
metadata remains readable.31 checks passed262.843s recorded: new boundary3,
improver inputs10, view sources16, real paired reservations/native-footprint2.
Evidence `../evidence/2026-10-23-m2d1-task3-view-holdout.json`, SHA256
07ef50951c43236be3128be3e9740bed1521e94e1e31c1a0bf178c88517cf6fc.
Current79-source b46e2cc3 is unregistered. This is a current-authority repair,
not a final holdout claim/native/business acceptance. Task3 remains OPEN.

Additive final-link metadata checkpoint:79 checks passed204.563s recorded across
new guards4, view schema, TrialStore, migration/store and native footprint. A
real legacy CaseStore reservation cannot be adopted by a tuning comparison;
missing/changed guard blocks new authority before plaintext. Earlier prototype
metadata stays readable, existing view DDL is AST-identical, and schema2
downgrade drops the new child first. Evidence
`../evidence/2026-10-23-m2d1-task3-qualification-schema.json`, SHA256
c52e682319fafcd9613e125ce3741bc6b27cb9f7bf3ae4a4b94f4b7327e3179a.
Current79-source d6b20eb5 is unregistered. Genuine positive selected-final link,
owned reserve/consume and final native/public controls remain open; runtime
final requests are still explicitly denied. No final/eligible result is faked.
Linux39965159570 SUCCESSc811b9d6; b3a3f0cb CI39966693829 was still in progress.

Owned final code checkpoint:70 tests passed494.250s across8 sequential scripts
on one source map. Conditional selected-report/current-view authorization now
reserves/links the existing qualification registry in actual admission and
consumes only before returning qualification input. Cold historical ownership
has a separate SQL/blob reader. Actual tests deny nonfinal/foreign/missing scope,
missing/foreign transaction and consumed qualification relabelled as regression;
the real tuning pipeline with simulated engine still passes and stays non-pass.
Evidence `../evidence/2026-10-23-m2d1-task3-owned-qualification.json`, SHA256
5f54cee420f022709b4ea9278fcc5cda975f85c2b1faf55f9f9b9eea0283697a.
Source81/759f44ab is UNREGISTERED. Genuine positive selected-final execution is
unverified; no eligible selection/result was fabricated and full18/unknown was
preserved. Legacy v2 tuning-family bypass is under separate audit. Task3, native
qualification, public controls and whole-D1 integration remain OPEN.

Legacy baseline bypass repair: genuine RED3 showed the old v2 path reading
context despite a later owner-declared holdout alias, and its last SQL fence
accepting that alias. New v2 reservation/admission and common late fences now
use the same no-consumed-exception tuning rule.30 checks passed134.850s across
the new boundary, B lineage/admission/actual execution and actual v4 pair/native
footprint. Exact old replay/metadata stays cold; qualifier/history source and
v4/materialization methods retain their earlier qualified scope by AST/hash.
Evidence `../evidence/2026-10-23-m2d1-task3-legacy-alias.json`, SHA256
fa40a4baf1887cc1c873be511546b3d45311f3636c48c5e6c7ba18422180ee40.
Current81-source c2e7968e is unregistered. Actual positive final/native, public
controls and independent whole-D1 review/CI remain open; Task3 is not done.

- Final affected regression21/21 GREEN,663.451s, qualified across two frozen
  segments: first15 passed scripts retain identical product/helper/test bytes;
  only the failed standalone task-drain test changed from a30ms scheduler sample
  to actual completion while the unrelated reservation stays blocked. Its6-test
  suite passed, and an intentionally wrong unrelated-reservation join still
  failed with TimeoutError. The same reviewer approved this test-only correction.
  All6 remaining scripts passed on the new frozen scope. Native profile9dcf7184
  is unchanged. Current sanitized engineering evidence SHA2b3fd081 records
  commands/log hashes, segment reuse, review and runtime boundaries. Fresh main
  remains ed8163fb/0.295.0 and PR801 solely reserves0.296.0. Exact-final Linux CI,
  integration and actual publication remain pending; no Task9 completion yet.
- Current final-source checkpoint: rebased onto ed8163fb/main0.295.0, reserved
  0.296.0 in PR801. Product/test bytes survived rebase unchanged; the same
  independent reviewer approved scoped main integration, fixture corrections
  and corrected bilingual changelog blocks. Both original Important findings
  remain closed. The new34-source profile9dcf7184 passed exact native solver5/5
  (11.344s process wall time), roles5/5 (43.031s), and cleanup faults9/9 (1.241s
  unittest time). Sanitized artifact SHA98ee4e8c is registered outside the profile.
  Separate persisted-selection/native-readiness verification passed with zero
  model calls. Final affected21-script regression is running sequentially with
  source/test hashes; exact-final Linux CI/integration/publication remain pending.
  Historical aa51b4b9 feasibility remains old-source evidence only.
- Current continuation: both Important review findings are closed by the same
  independent reviewer. Dependency identity11/11, existing dependencies6/6 and
  actual preparation ownership4/4 passed. Full old preparation regression then
  exposed two stale fixture assumptions (ACL metadata prohibition and a barrier
  inside newly serialized preflight); only those fixtures were corrected and
  preparation8/8 passed20.738s. Native/model calls remain forbidden in fixtures.
  Checkpoint LinuxCI39922323540 SUCCESS on ddec90ad. Fresh main ed8163fb is0.295.0;
  preserve this checkpoint, rebase and reserve0.296.0 before final qualification.
- The real baseline result is explicitly FAIL: the pinned JSON `shape` criterion
  failed `structural_check`; business `accuracy` is UNKNOWN pending owner
  confirmation. All four actual calls settling ok proves pipeline execution,
  not baseline quality. The source-bound feasibility artifact includes sanitized
  recorded result checks; no criterion was changed and no model rerun sought a win.
- Whole-C independent review completed for47f50f70..ddec90ad: no Critical,
  two Important findings. Preparation could reserve a later immutable cell
  while the previous runner was pending/closing; nested dependency resolution
  could bind an unrelated same-name granted file. Parent reproduced both RED.
  Pending/cleanup/concurrent admission is now serialized through the actual
  brain barrier and final SQL check. Dependencies resolve one lexical absolute
  identity from each declaring file and its bound root, without root/candidate
  fallback; semantic input supplies the actual principal root. Focused tests
  and review recheck are in progress. These dependency source changes invalidate
  aa51b4b9 for current execution; fresh source-bound native qualification is
  required, and no native auth/model command uses the changed unqualified source.
- Genuine technical feasibility completed on ddec90ad/profile aa51b4b9 in
  258.944s: actual baseline, proposer, one structural repair and semantic reviewer
  with selected opus5-5/medium/subscription; four marked actual CallLedger calls,
  all settled ok, two generated A candidates, and all plaintext workspaces removed.
  A remains unreviewed; combined semantic/native verdict remains unknown. Usage
  is partial: observed32248 input/6091 output tokens, subscription-equivalent
  USD0.3644214, no known cash charge or request count. The sanitized source-bound
  report is `../evidence/2026-10-23-m2c-real-feasibility.json`. It does not create
  a current receipt after later source changes or establish business/rollout proof.
  Preserve this worktree's ignored `.superpowers/live-c-technical` encrypted
  history and generated private test key, alongside M1's preserved live-a files.
- Task9 native checkpoint: current profile aa51b4b9 (34 sources), exact
  CLI2.1.308/c9796ba2 and SDK0.2.116 passed both complete native suites:
  solver5/5 in10.588s and roles5/5 in45.642s, including real host/supervisor
  death, all three typed role renderers, ambient canaries and pending native
  cancellation. Published sanitized qualification evidence is bound by
  SHA310e6df5; the exact registry entry does not attest auth or business effects.
  Six sequential affected regressions passed34.672s with40 unchanged source/test
  hashes. Separate safe re-pin/native auth projection verifies the persisted
  opus5-5/medium/subscription selection and actual current runtime, zero model
  calls. Genuine role/CallLedger feasibility, whole-C review, final broader
  affected regression and exact-final Linux CI remain open. Earlier empty-registry
  and failing qualification checkpoints below remain historical.
- Task9 in progress from9d892ea9. Actual CLI dummy-auth/local-provider qualification
  exposed native lifetime gaps: job/accounting disappearance preceded process
  exit; actual host death released the byte lock while four native handles were
  unsignaled. The first named-job alternative also failed and was discarded.
  Normal/cancellation cleanup now retains handles and waits; a separate cleanup
  supervisor retains durable fences on the SAME brain and actual attempt locks
  across host death. A suspended Windows launcher is assigned before resume,
  preventing pre-existing Python launcher descendants from escaping the job.
  Birth notifications are checked against cumulative kernel TotalProcesses;
  dropped/unreadable inventory cannot issue a cleanup proof. Supervisor death
  leaves both fences in place and cannot grant automatic recovery.
  The supervised native four-method suite passed37.082s before the final ready
  protocol change; the actual final-protocol supervisor-death case passed4.494s
  and nine cleanup/cancellation fault tests passed1.346s. Final current-source
  qualification, affected regressions, independent review and final CI remain
  pending. Source footprint is now34; qualification registry remains EMPTY.
  No actual-account inference/auth or business acceptance has occurred.
- Task8 exact LinuxCI39913163250 completed FAILURE on9d892ea9, solely
  test_route_table.py: the eleven intentional new C owner/history routes were
  absent from its committed snapshot. The snapshot was regenerated to618 routes;
  only those additions and consequent existing route order shifts changed.
  This failure is retained; it cannot satisfy final integration.
- Owner delegated pilot choice in the pending M2–M3 question: prioritize data
  reconciliation as the business pilot, document processing second; Python
  bug-fix/test remains the additional technical pilot. This selects the work
  types, without supplying an accepted business dataset or live activation grant.
- Reuse attached managed M2 worktree on `codex/agent-skill-improvement-m2c` from
  actual published main47f50f70/0.293.0. Fresh open-PR inspection found no other
  reservation;0.294.0 is reserved before C product code with both changelogs.
- Plan: `../plans/2026-10-23-agent-skill-improvement-m2c.md`. Concrete contracts
  canonicalized/self-reviewed; actual Task1 started from50406532e3b349c4e04c4320e73bbfa6d86a9cdc.
  Tasks1–8 now implement schema6, preparation, real role workflows and owner
  transport/full stop locally. Native C qualification and accepted semantic/
  business evidence remain open. Draft PR801 reserves0.294.0 before product code.
- Current Task8 checkpoint:22/22 affected regression scripts GREEN768s, sequential
  with64 source/test hashes verified unchanged from start through completion.
  Seven closed owner POSTs/four cold history GETs reuse actual main session/CSRF
  gates and the same OwnerTrialService/brain barrier/CallLedger. Stop includes
  comparison+preparation links and every role attempt/call, cancels native work
  before joining complete workflows, and owns slow decision/publication/report
  threads. Durable stopped replay survives reconstruction without source reads
  or redispatch. Empty scopes do not wait on unrelated same-brain reservations;
  scoped recovery preserves unrelated corrupt journals and old acknowledgments.
  Full14000/28000 SQL tests prove structural bounds only; real smaller integrations
  prove calls/lineage/kernel/cleanup. Source33 native registry remains empty.
  Task7 exact LinuxCI39907956153 SUCCESS on e1d71a33; Task8 Linux feedback and
  Task9 qualification/whole-C independent review/exact-final CI remain required.
  Operator guide: `../../dev/agent-skill-m2c-operations.md`. No new actual model,
  native-auth, business acceptance, activation, deployment or restart is claimed.
- Initial Task1 checkpoint followed Goal section12: fix-loop new focused cases; Task1
  regression operations/experiments/store, then early Linux CI for SQLite/backup/
  paths. Full required final CI and independent stable-branch review remain.
  Migration5 and metadata8 first passed together13/13 in33.041s. Additional
  pending-to-completed SQL fence and signed case-seed compatibility reproduced
  RED, then2/2 GREEN5.204s. Expanded task regression passed: operations21/21 in
  48.856s, experiments19/19 in43.686s, store22/22 in5.232s. These are source-
  scoped interim results, not final-head CI. Reuse released B only for unchanged
  behavior; its schema5 evidence does not validate new schema6. No native profile
  source changed, so prior native qualification remains historical evidence for
  that unchanged profile; no redundant auth/model call. No speedup ratio claimed.
- Baseline-first investigation favors a genuine typed preparation solver Trial
  inside the durable experiment, without fake candidate/arm or a v1 downgrade.
  Every consumer/result/stop/recovery scope and combined capacity bound must
  account for it. Proposer/reviewer calls need distinct actual operation identity,
  CallLedger/usage and native worker/workspace ownership; no fake solver Trials.
- Task1 metadata/schema6 committed/pushed as c4d1c058 (62 focused local checks);
  early LinuxCI39885490382 remains a separate pending snapshot. Task2 now has
  actual host-derived complete tuning schedules, v3 baseline admission through
  the existing CallLedger/TrialStore/Runner/TrialTasks, exact historical/result
  lineage and completion under the real brain barrier/all-attempt cleanup/CAS.
  Private synthetic-worker E2E verifies partial usage and unknown verdicts; no
  native model or business acceptance. Public API/full stop integration is Task8.
- Task2 impacted regression initially10/12 scripts GREEN328s; actual failures
  were concurrent Windows encrypted-blob publication and a schema2 test fixture
  leaving new C tables behind. Both were reproduced and corrected separately,
  preserving permission/corruption rejection and rollback assertions. Targeted
  fixes passed3 blob cases/.467s and schema2/.705s; full storage25 passed6.330s.
  Final four affected scripts GREEN123s (operations21/preparation8/execution4/
  trials34); ten unchanged successful paths and
  qualification14/58.135s are conditional historical scope evidence, not final
  commit CI. The blob guard change also changes evaluator source identity;
  current E2E reruns the fresh pins. No blanket rerun of all improvement scripts.
- Task3 now reserves genuine improve_propose/evaluate calls/attempts/events in the
  existing writer and validates actual operation/call/marker ownership for native
  telemetry. Operation metadata, shared usage projection/reconciliation and error
  coverage remain separate from solver/Team identity; unknown data stays unknown.
  Eight impacted scripts passed98s; old Trial usage30/4.282s and turn checks passed.
  Same-operation foreign-role recovery was reproduced RED then fixed, with final
  telemetry9/25.058s. Full current-head CI/review remains pending. No actual role
  worker/model query; native learning exclusion is carried explicitly to Task4.
- Task4 is IN PROGRESS in the working tree: typed operation workspace/profile/
  worker/adapter, shared owned native IPC, real SQL leases/markers/refund and
  encrypted replay/late trace. Four new component scripts passed53s; earlier
  affected legacy worker/decoder checks passed separately. These are synthetic
  technical checks, not full Runner/native qualification or business evidence.
  Lifecycle supervisor/results/recovery/full learning-exclusion proof remain.
  Native profile changed to roles-v2 with thirteen actual source files, so the
  prior native qualification is historical. Actual current profile qualification
  must gate role execution; the old runtime tuple alone cannot qualify a new
  profile. No real model/auth query or public role enablement occurred.
- Earlier C Linux runs on bb869812/b2927d55 failed only two old backup-count
  assertions. Exact per-migration backup/original-content tests now pass14s,
  committed0ca0dba7; its LinuxCI39892216765 is pending. That commit excludes the
  uncommitted Task4 runtime and cannot validate it. Exact final-C CI is required.
- The exact0ca0dba7 LinuxCI39892216765 subsequently completed SUCCESS; it verifies
  committed Tasks1–3/backup corrections only. Task4 now also has actual encrypted
  results, pure typed record checks, owned Runner/Tasks, owner cancellation and
  scoped crash recovery. Completion/cancel/recovery checks use the actual worker/
  profile with a synthetic SDK engine; real session/lesson/job stores stay unchanged.
  Native profile qualification is enforced before native version/auth probes.
  Its reviewed registration authority is separate from the nineteen-file profile
  hash to avoid self-reference; roles-v2 has no qualified registration yet.
  The planned single infrastructure retry and exact-current native qualification
  remain open. An interim Task4 commit/early Linux run may capture tested core
  ownership while those are implemented; it does not complete Task4 or enable C.
- Task4 isolated lifecycle component is complete locally: core13 scripts GREEN213s,
  retry11 GREEN282s, final changed lifecycle/schema6 scripts GREEN247s and final
  future-schema/positive lease2 GREEN5.241s. Real proposer and reviewer worker paths
  with synthetic SDK messages preserve actual production sessions/lessons/jobs in
  completion/cancel/recovery. One infra retry retains original deadline and first
  marked usage, cannot revive owner-cancelled work, and has real writer/native
  evidence. Same-number stale schema6 guards cannot authorize new work. The current
  profile includes22 actual source files; its reviewed qualification registry is
  empty, so no native preflight/model call is enabled. Task9 qualifies stable C.
  Exact core a1acaa99 LinuxCI39896580083 succeeded (test and Docker-size jobs);
  new retry changes need fresh Linux feedback. Tasks5–9, independent stable whole-C
  review and exact-final-C CI remain open; no business/semantic/native readiness.
- Task5 authorized input component is complete locally: actual sealed preparation
  refs, baseline/protected context/public contract and tuning-only snapshot/trace/
  artifact/receipt projection are encrypted/hash-bound after final source and SQL
  CAS. No private answers, arbitrary checker reasons/evidence or holdout blobs are
  read into this model path. Unknown native coverage, reasoning/input use, tool
  payload coverage and partial usage stay explicit; no separate recipe grant or
  whole recipe library is inferred. Pure bounded output validation accepts only
  up to remaining two A body-patch slots or not_a_target_defect with genuine refs.
  The actual proposer prompt uses this renderer. An unnecessary common holdout
  blob read and a late-trace omission race were reproduced and fixed. Final scoped
  regression10/10 GREEN256s, new input cases10 GREEN50s within it. Source25 profile
  has no qualified registration; Tasks6–9/public C and all business/live gates stay
  open. T4 early LinuxCI39900250323 is still in progress on a43638e7; it cannot
  verify these newer T5 sources. No additional model/auth call occurred.
- Task6 generated proposal/one-repair/staging component is complete locally:
  concrete owned workflow uses real role calls/results/artifacts and actual A
  authoring. Whole batch and generated publication/links/events share one writer;
  mid-batch failure rolls back all A rows. Max remaining two slots includes manual
  drafts; same-key concurrent callers share one operation; one structural repair
  retains original data/allowance. No new region/exact-diff/source/activation grant.
  Source/grant/current-call/native evidence drift fences publication. Repeated HTTP
  cancellation/shutdown retains real worker/admission/publication threads after DB
  terminal status. Missing native evidence cannot become structural repair. Native
  unobservable reasoning/input-use remain unknown, drafts remain A-unreviewed and
  business_proof=false. Final scoped9/9 GREEN330s (new workflow18 GREEN164s inside
  it), on pinned unchanged LF sources. Actual Task4 retry head a43638e7 LinuxCI
  39900250323 is now SUCCESS; T5 head306e0871 Linux39901547032 remains in progress.
  Current footprint27 files has no qualified native registration; Task7 semantic/
  dependency receipts, Task8 API/full stop, Task9 qualification/whole-C review/final
  CI and all business/live gates stay open. No actual model/auth query or deploy.
- Task7 semantic/dependency implementation component is complete locally: actual
  improve_evaluate role, exact A before/after/provenance/protected context and bound
  source/engine/evaluator/declared dependency evidence. Immutable receipt/input/
  output/call linkage never updates A's unreviewed status or original provenance.
  Model pass + native unknown stays unknown. Exact owner arbitration encrypts its
  rationale and cannot erase negative findings or waive native/source/dependency
  gaps. Current consumption rechecks after slow reads and permits later-phase
  reads without new dispatch; cold history/replay survives revoke. Granted helper
  bytes are observed; ungranted file bodies are not read. Executable/runtime
  dependency qualification remains unsupported here and belongs to M6/D gates.
  Scope9/9 GREEN443s precedes a recorded two-file admission/input-binding fix;
  final4 reproductions + normal propose/repair/review7 GREEN67.301s. Reuse is
  conditional, never final-head proof. Source32 profile registry remains empty.
  Task8 full API/stop and Task9 qualification/independent whole-C review/exact-final
  CI remain; no actual model/business/live acceptance or deployment is claimed.
- Test environment correction: prior T5/T6 evidence descriptions overgeneralized
  an Opus-shaped worker-unit pin. Main end-to-end fixtures actually use synthetic
  model/CLI/SDK/profile labels; installed SDK DTO library is0.2.116 with injected
  engines/verifiers. Separate correction preserves all original source/log hashes;
  no rerun or real-runtime claim follows from it. Task5 LinuxCI39901547032 and
  Task6 LinuxCI39903506020 completed SUCCESS on306e0871 and07e84dc4; newer T7 code
  passed exact LinuxCI39907956153 on e1d71a33; complete exact-final-C CI remains.
- Generated proposals remain A-unreviewed with separately pinned semantic and
  dependency assessments. No assessment/owner product confirmation waives source,
  runtime/view, qualification, activation or real business-data gates. Candidate/
  final execution stays closed until genuine C+D support. Broader UI is F.
- M2B publication is verified; mainCI39882926358 also completed SUCCESS on actual
  merge47f50f70 (fresh read, no rerun). No deploy/restart/live activation occurred.

## M2B engineering continuation

- Reuse the clean managed M2 worktree, branch `codex/agent-skill-improvement-m2b`,
  from actual published A main cbef2f46/0.292.0. Fresh main/open-PR inspection
  found no open reservations;0.293.0 is the next free release.
- Plan: `../plans/2026-10-23-agent-skill-improvement-m2b.md`, self-reviewed
  against actual source. Six units cover schema5/experiment ownership, real A
  arms/full counterbalanced matrix, closed request-v2/baseline execution,
  both-variant qualification preflight, immutable complete-pair reports and
  owner cancellation/recovery. Task1 now implements schema5, proposed metadata
  and owner CAS/block/resume/stop fences; source/runtime execution remains gated.
- Read-only B–F audits identified exact case-set association, fresh proposal
  lineage after context changes, chosen active edit authority, native delivery
  limits and missing preparation/navigation. Those boundaries are in the plan;
  actual effort/internal semantic use stay unknown where unobservable.
- Reserved VERSION/both changelogs in a2f1b074 and attached draft PR800 before
  implementation: https://github.com/blogminhquy/javis-os/pull/800.
  Changed-candidate execution, compose, real activation and live canary remain
  unavailable until their actual prerequisites and owner scope grants exist.
- Task1 tests preserve actual A encrypted authoring and M1 context/case/contract/
  qualification/trial/ledger history. Migration and actual released-A-reader
  checks pass; metadata creation/CAS/revocation, SQL NULL constraints and active
  capacity retention are covered. Interim independent Task1 review found no
  Important issues and independently checked five migration/reader/CAS/SQL cases
  plus a distinct valid context competing in proposed/blocked/stopping phases.
  Root final unit regression7/7 GREEN84s (new experiment suite19 tests GREEN29s).
  Exact Task1 checkpoint5e5ed821 Linux CI39868224361 passed both jobs.
  This is not the final whole-B review; Tasks2–6 and final CI/publication remain.
- Task2 host planning now derives definitions from actual associated sources,
  verifies A proposal bytes/provenance and pins one chosen active edit authority.
  Whole compact matrices counterbalance both variants; each challenger has a
  distinct fresh baseline comparison. KEEP_BASE seals and enters stopping in one
  transaction; all new A edit writes honor the seal while history/revoke survive.
  Candidate selection remains closed until Task5 immutable report verification.
  Root comparison suite24 tests GREEN48s and related8/8 regression GREEN157s.
  Independent review's final protected-context read races were reproduced RED,
  fixed with final full observations and independently rechecked; no open
  Important scoped findings. Tasks3–6 and whole-B acceptance remain open.
  Exact Task2 checkpoint2e9d2db8 Linux CI39869374705 passed both jobs.
- Task3 now carries closed v2 comparison lineage through actual preflight,
  atomic trial/call/link, baseline Runner/workspace, usage and immutable results.
  V1 history/replay survives; experiment-owned new work cannot downgrade to v1.
  Current fences refresh after slow reads; stopping blocks late checker results.
  Candidate/final execution remains closed before decryption/probe/reservation.
  Final five new-unit scripts34 tests GREEN79s; related Host24 GREEN15s after
  expected frozen-revalidation count update; old M1 E2E/Runner/light-startup3/3
  GREEN332s. Scoped independent source review has no open Important findings
  after reproduced downgrade/post-I/O races were fixed and rechecked.
- Public-source compilation dominated capture CPU. The bounded exact-byte code
  cache keeps fresh stable reads and every live-function/path check. Independent
  cached/uncached full captures match; revalidation5.352->0.699s on this machine.
  Cache6 tests pass independently. Root cache/Dashboard/old E2E3/3 GREEN75s,
  E2E288->40s. This is measured technical overhead reduction, not model/business
  effectiveness. No real native/model/auth query or four-file profile change.
  Tasks4–6 and final whole-B review, exact-head CI/merge/publication remain open.
- Task4 denial-boundary checkpoint is PARTIAL: lower qualification ownership
  follows frozen experiment/set/hash and shared qualification fingerprints even
  after renaming/reclassification. Fresh bare-pin reserve/consume and legacy
  execution reject; historical replay and global claims survive. Original5 tests
  RED->GREEN; renamed owner early-preflight RED->GREEN. Expanded14 qualification
  tests GREEN46s, including verified actual frozen final lineage for both
  variants/splits with zero allocations, concurrent aliases and actual pre-B
  consumption replay. Independent scoped review found no Important issue and
  passed four focused checks15.65s. Related seven-script regression GREEN190s
  (Cases, Trials, M1 Admission/transactions and v2 Lineage/Admission/Qualification).
  No unused positive v2 qualification helper or readiness flag was added. Positive
  final allocation/linked consumption and drift/resume remain C+D dependencies;
  Task4 and complete M2 remain open. Task5 reports can proceed independently.
- Task5 report component committedc860d8c0: pure complete-case arithmetic,
  exact integer multiple-test correction, critical/regression preservation and
  explicit technical/unverified evidence; concrete encrypted immutable reports
  enumerate expected cells and pin exact result IDs/hashes. Pure19 tests GREEN.
  Actual synthetic Runner/Fernet/ledger tests preserve report refs across genuine
  product reevaluation and reject pointer races. Missing artifact/call marker,
  late source drift during policy hashing and corrupt Fernet results reproduced
  RED->GREEN. Scoped independent review found no remaining Important issue;
  final component regression5/5 scripts GREEN178s, including31 new component
  tests. Selection now pins exact complete CURRENT tuning evidence for every
  declared arm; the chosen arm must support improvement. Publication ordering
  uses immutable event IDs, handling clock rollback and deduplicated report
  republication. Scoped premature-second-arm sealing finding and root chronology
  findings reproduced RED->GREEN. Selection11 tests GREEN39.9s; final seven-script
  regression GREEN264s. Candidate selection opens only that metadata seal; final
  execution/allocation remains C+D gated. Task6 and whole-B acceptance remain open.

- Task6 engineering checkpoint adds twelve owner-only routes, cold report/history
  reads, strict closed bodies and lazy main wiring over the SAME OwnerTrialService
  dispatcher. Stop fences retain capacity through pending admission/handoff,
  terminal-row live workers, actual checker drainage and verified cleanup under
  the real brain execution lock. All recorded linked attempts participate in the
  final CAS. Cleaned journals are retained and validated as replay protection;
  invalid journals cannot be relabeled clean by legacy cancellation cleanup.
  Recovery never dispatches and works while off/revoked; owner resume events and
  metadata transitions commit atomically. Candidate/final execution stays closed.
  Root service13 GREEN46.655s; API5 GREEN17.123s; actual v2 Runner lifetime3
  GREEN20.815s (synthetic native packets, real storage/workspaces/usage); five-script
  service/API/cleanup/Tasks/Sandbox regression GREEN83s. Actual-main/old-main/light
  startup3/3 GREEN30s. A separate Python process proves the actual OS brain lock;
  simultaneous admissions preserve one cell/trial/call. Route snapshot now607
  entries, with the established595-entry prefix unchanged and12 appended routes.
  Current native profile ffe27adc5caba5249b95358245d874e99f1d59ffc9ee49684d9f0e085198e643
  passes exact CLI2.1.308/SDK0.2.116 dummy-HOME/localhost qualification5/5 in14.845s.
  The old real smoke remains on its original06e75 profile with aggregate unknown.
  Full required regressions, fresh whole-B review, final exact-head Linux CI and
  integration/publication remain pending; Task6 and full M2 are not complete.

- Fresh whole-B review of cbef2f46..69a91832 found one Important recovery-scope
  issue: brain-wide trial recovery could touch an unrelated old trial or let its
  damaged journal block an otherwise empty stopping experiment. Root reproduced
  it, added three behavioral RED cases, then scoped both expired settlement and
  filesystem cleanup to actual immutable experiment links. The separate existing
  brain-wide owner-trial recovery remains unchanged. New scope suite3 GREEN13.544s;
  the independent original diagnostic now closes the experiment and leaves the
  unrelated journal intact. Reviewer28 focused tests passed and no other Important
  issue was identified. Fixed-source regressions, independent recheck and new
  exact-head Linux CI remain required before integration. The initial broad63
  regression spans the narrow fix and cannot serve as exact-final-head evidence.

## M2A engineering continuation

- Worktree: `C:/Users/admin/.codex/worktrees/agent-skill-improvement-m2a/Javis-OS`;
  branch `codex/agent-skill-improvement-m2a`, release0.292.0 reservationf6d8d356,
  attached draft PR799: https://github.com/blogminhquy/javis-os/pull/799.
- Dependency M1 is published as0.291.0 on main9dd7a9f9. Replayed only A's six
  own commits onto that actual merged source; the resulting tree is byte-identical
  to the reviewed A checkpoint b01ddf1b. PR799 targets main for final CI/integration;
  0.292.0 remains the next free reservation. The original checkout remains untouched.
- Plan: `../plans/2026-10-23-agent-skill-improvement-m2a.md`, reviewed/self-reviewed.
  Tasks1–2 add schema4 owner-authority/immutable candidate metadata and byte-exact
  owner staging. Their new suites pass12/11/14 tests; relevant assets, Host,
  store/case/trial/admission regressions pass. Task3 exact private review passes13
  tests and its combined8 selectors pass54s. Task4 adds9 browser-owner routes,
  complete baseline/diff/artifact review and inert vi/en Studio authoring. API7,
  actual-main4 and final private-review15 tests pass; focused14 Python scripts,
  JS5 scripts and unchanged-prefix595-route snapshot pass. Headless Chromium
  at390px vi/en verifies exact downloads, inert content and UTF-8/CRLF selection.
  An extra unrelated webhook POSIX-mode600 test fails on Windows; no test/guard
  was weakened. Fresh whole-branch independent review through65740de1 found no
  Important/Critical issues; the subsequent stale-Studio-skill correction also
  passed independent RED/GREEN reproduction and narrow review. Final CI and
  integration remain pending. Trial/activation flags stay false; no actual engine
  calls in A.
- Old M2 CI39851845888 failed only the existing fastyaml architectural guard:
  the patch validator directly called the slow YAML loader. The failure was
  reproduced locally and corrected to use the shared fastyaml parser after the
  unchanged strict token/node/duplicate-key checks. Five focused scripts pass25s;
  independent review passes2 scripts,12 parser-parity inputs and8 unsafe-input
  rejections with no Important findings. A fresh fixed-head CI is required.
- Final UI operation review reproduced and fixed successful-capture event reuse,
  duplicate pagination after reload, and Stage retry after a known successful
  write whose metadata refresh failed. Unknown transport retries keep the event;
  acknowledged actions retire it. Complete source period/timezone/cutoff/schema
  metadata is now inert alongside artifact fixtures. Peer independently reproduced
  all four old failures and verified the correction without Important findings.
  The updated complete JavaScript suite passes266/266 in43s; vi/en mobile browser
  checks pass. Final-head Linux CI still gates integration.
- CI39858827459 on bf17f891 failed only the existing lightweight-startup test:
  two new modules imported cryptography's InvalidToken at module load. The timing
  ratio itself passed4.08. The same deterministic failure reproduced locally;
  deferring those exact imports to private review/proposal operations preserves
  exception handling and all source/grant checks. Startup, private review,
  staging, API and actual-main scripts now pass5/5 in44s. Peer independently
  confirmed old/corrected fresh-main behavior and corrupt-blob rejection (two
  suites pass18s), with no Important findings. New final-head Linux CI is still
  required before merge; earlier runs do not qualify the corrected source.
- Owner delegated pilot choice. An objective Python bug-fix/test pilot is selected
  for reproducibility alongside the spec's required business pilots. This choice
  does not supply an accepted business dataset or owner acceptance evidence.

## Milestones

| Milestone | Engineering | Business evidence | Rollout |
|---|---|---|---|
| M0 | Complete: PR #794 merged09903315, CI39793439501 and publication39797072172 passed;0.287.0 | Not applicable to foundation | Metadata only; no live activation or production restart |
| M1 | Complete engineering: PR795 merged9dd7a9f9, CI39852883192 and publication39856024117 succeeded;0.291.0 | One historical real-engine synthetic baseline; aggregate unknown; no business pilot | Trial/activation flags false; not enabled |
| M2 | A0.292.0, B0.293.0 and C0.296.0 published; D1/PR803 reserves0.299.0 on main0.298.0. View/ledger/qualification infrastructure and isolated skill reads implemented; canonical native dispatch and full D2/E/F remain open | Real synthetic role/format/observation attempts remain historical, with fail/unknown/not-run results; no eligible pair or independent business pilot | Not enabled |
| M3 | Pending | No qualification or live canary | Not enabled |
| M4 | Pending | No adapter/routing pilot | Not enabled |
| M5 | Pending | No agent pilot | Not enabled |
| M6 | Pending | No bundle/helper pilot | Not enabled |
| M7 | Pending | No Team improvement pilot | Not enabled |
| M8 | Pending | No adaptive-library evidence | Not enabled |

## Existing -> missing -> evidence -> milestone

| Existing | Missing | Evidence on baseline | Owner |
|---|---|---|---|
| Same resonance SQLite, WAL and BEGIN IMMEDIATE transactions | Immutable target/revision/bundle metadata | `resonance_store.py`, `_conn`, `_Tx`; read-only audit | M0 |
| Owner-only stable agent registry and owner-rule guard | Dedicated improvement identity, exact raw-byte protection, policy version | `agent_rules.py`, `resonance_store.agent_register` | M0 |
| Skill inventory with disabled-canonical shadowing | Safe capture of canonical assets and durable revision bytes | `skill_router.list_skill_manifests`; resolver alone is insufficient | M0 |
| Evidence encryption primitives | Revision-owned blob lifetime outside evidence TTL/cleanup | `evidence_store._serialize/put/cleanup` redacts and expires content | M0 |
| METHODS compare/holdout and ledger | Arbitrary immutable bundles and isolated solver adapter | `resonance.py`, `agent_ledger.py` | M1–M3 |
| Team default acceptance/quality-first/usage released in 0.285.0 | Verify and reuse these dependencies; do not implement them again | Baseline changelog and `test_team_quality_*` files | M1/M7 |
| Main's permissive brain fallback | Strict existing-brain identity for improvement routes | `_brain_root/_brain_key`, `brain_ident.canonical` | M0 |

## Baseline verification

- `D:/Project/Javis-OS/.venv/Scripts/python.exe tests/run.py learn_sua_skill -v`: PASS, 1 file.
- `... tests/run.py agent_rules -v`: PASS, 1 file.
- `... tests/run.py resonance_a3_learning -v`: PASS, 1 file in 132 seconds (session 92106 completed).
- Python env reused by explicit executable, not by copying `.venv` or production config. Main imports in new tests must set scratch state/brain roots first.
- No new model calls, business dataset reads or live activation so far.

## Decisions and review findings

- Ruling: use dedicated encrypted raw-byte revision blobs rather than normal EvidenceStore artifacts. EvidenceStore redacts content and applies a 14-day TTL, so it cannot prove an immutable original-byte revision. Cost if wrong: explicit blob migration/interface adaptation at M1.
- Ruling: M0 exposes authenticated capture/history/policy only, with no executable trial/apply controls. This delivers inspectable foundation while preserving later sandbox gates.
- Ruling: read-only missing policy/status must not create a DB, asset copy or model call. Store writes initialize schema atomically; registered reads use a lazy read path.
- Ruling: the user's Goal authorizes local planning/execution and PR integration without repeated approval; production rollout and business owner confirmation remain separate.
- Two independent read-only subagent audits completed, covering storage/identity and API/test infrastructure. These audits are not code reviews of implementation.

## Next action

Continue D1 from PR803/current continuation and the native-outcome-and-dispatch
plan: canonical isolated async capture, exact worker/guardian bootstrap/control,
owned preflight plus SDK version/query launches, then versioned read-outcome,
dispatch/reasoning and operation input-delivery integration. Freeze and qualify
the complete changed footprint before registering or retrying the selected account.
Use focused RED/GREEN and affected tests per Goal12; reuse unchanged pinned proof.
Continue full D2 production task/session bindings, then E apply/revert/canary and F
operator/feasibility without relabeling trial-only resolution as complete D.
Do not use live prompt builders or fallback engine selection as a heartbeat guard.
The owner run and activation capabilities remain false pending their actual release gates.
Full M0–M8 Goal remains active; no business or live rollout gate is closed by a code merge.

## M0 implementation evidence

- Implemented immutable revisions/bundles and append-only events in the existing shared SQLite
  store, encrypted exact-byte blobs, owner-only policy/CAS/idempotency, canonical ownership
  capture and six authenticated metadata endpoints. No engine, canonical write or activation.
- Final focused command: `D:/Project/Javis-OS/.venv/Scripts/python.exe tests/run.py improvement
  route_table prompt_budget team_quality_contracts team_quality_usage agent_rules learn_sua_skill -v`:
  **PASS 9/9 files, 51 seconds**. The three improvement scripts contain **39 behavioral tests**
  (20 store, 10 assets, 9 API), including actual-main authentication/CSRF and read-only access.
- Localization: three i18n scripts passed. Route snapshot intentionally adds six routes.
- Earlier broad security selection: 8/9 files passed. The unrelated unchanged webhook test
  requires POSIX mode 0600; Windows reports 0666 after chmod(0600). Ran the exact test from
  an archived clean baseline `a9ee52ff` and reproduced the identical assertion failure.
  Proof is in the local ignored ledger's `baseline-webhook-windows.txt`. No assertion or
  production permissions were weakened. Linux full CI remains mandatory.
- Fresh independent whole-branch review of `a9ee52ff..6f0541de`: no Critical findings;
  three P2 findings, all reproduced RED then fixed in one pass: cold GET migrated legacy
  DB; revision C after A/B/restore-A had wrong parent; corrupt empty ciphertext was accepted.
  Fixes use an actual read-only SQLite reader, current revision pointer for parentage, and
  a nonempty encrypted envelope. New tests verify all three plus existing-schema reads.
- Frozen M0 trial boundary: `docs/dev/agent-skill-trial-contract-v1.md`. This is a contract
  for M1, not a runtime or supported adapter. M1–M8 remain pending.
- M0 acceptance: same-byte capture deduplicates; protected bytes preserved and never edited;
  off blocks new captures; migration interruption rolls back; future schema rejected;
  encrypted loss/corruption unavailable; two-connection CAS has exactly one winner;
  deleted/replaced targets never inherit identity. Tests use scratch roots, no model calls.
- CI run `39784692950` on the pre-fix head: Docker size succeeded; full Python suite still
  running when final fixes were prepared. Its result cannot certify the final head.
- That pre-fix run subsequently passed fully. Final-head run `39785987176` passed all
  improvement tests but failed the unchanged Team runner's reply-concurrency timing probe:
  peak was 1 instead of 2, while both replies completed. No Team runtime file had changed.
  Reproduced deterministically by delaying the second fake engine start by 0.2s; the old
  fixed 0.1s sleep falsely rejected the parallel runner. Replaced this timing assumption
  with a bounded rendezvous, retaining the peak=2 and both-done assertions and the delayed
  startup. Focused regression then passed 4/4 files in 36s. A separate negative control
  forced sequential replies and verified the same peak=2 assertion still rejects them.
  New final-head CI is required before integration; no red run was merged.
- Fresh-process restart probe passed: two independent processes preserved the encrypted
  bytes, revision identity and one idempotent event. No model call or live action occurred.
- M1's migration work exposed a first-writer backup race shared with M0: both writers
  could enter the backup helper and contend on its temporary file. Reproduced on the M0
  branch with two first migrations (two backup calls instead of one). Backported the small
  fix so backup happens after the transactional schema recheck under BEGIN IMMEDIATE.
  M0 regression passed **3/3 files, 40 tests, 19 seconds** (21 store + 10 assets + 9 API).
  This fix is isolated in the temporary `agent-skill-improvement-m0-race` managed worktree;
  the original implementation worktree is now used by the engineering-only M1 branch.
- Final head e6637d33 passed CI39793439501, including Python suite and Docker size. Fresh
  main0.286.0/version/PR checks passed; PR794 squash-merged as09903315 with expected-head CAS.
  Build/publication39797072172 subsequently passed, publishing0.287.0. No production restart,
  deploy, live canary or activation was performed. M0 engineering is complete; M1–M8 remain.

## M1 engineering evidence

- 0.288.0 was reserved in dependent draft #795 before code. One dependent draft only;
  final review/merge waits for integrated/published M0. The source checkout stays untouched.
- Task 1: immutable acceptance contracts with mandatory/business distinction; exact raw and
  redacted fixture hashes; encrypted raw inputs and private answers; pinned source periods,
  timezone/version; case family/content split guards; transactional qualification claim,
  consumption, clone/exposure prevention and same-candidate resumption. No engine executed.
- Schema2 reads schema1 M0 metadata without migration; explicit writes upgrade atomically,
  preserving M0 policy/history and backup. A failed upgrade rolls back all M1 tables.
  The two-writer backup race was reproduced and fixed under BEGIN IMMEDIATE; the same fix
  was backported to M0 in e6637d33 through its own managed worktree.
- New case tests cover 25 behaviors, including malformed nested JSON, caller mutation after
  hashing, business criteria versus structural keywords, raw loss with surviving fixture,
  concurrent migration/qualification, old-schema rollback and answer/checker privacy.
  Latest cases/store scripts PASS 2/2 (15s) after input freezing; earlier full improvement
  run PASS 4/4 (29s). Additional final Task 1 regression is recorded in the local ledger.
- Native research used SDK0.2.116/CLI2.1.304 and localhost dummy auth/provider only. Bash,
  Read, WebFetch, ToolSearch and unregistered MCP were rejected; exact fixture hit/miss
  worked, with no ambient hooks/MCP/memory or outside canary effects. Disabling tool search
  yielded exactly one declared fixture tool. This is synthetic enforcement research, not
  OAuth execution, business evidence, billing coverage or an OS sandbox.
- Actual host selection was read through non-secret fields only: anthropic-cli,
  claude-opus-5-5, medium. CLI auth status reports logged in; no account tokens were copied
  or output. Production adapter capability remains false until released-path verification.
- Task 2 workspace substep committed as e0acfe16: eleven scratch tests verify exact fixture
  capabilities, separate attempts, pinned hashes, credential-text rejection, concurrent prepare,
  actual Windows junction boundaries and cleanup preserving another attempt. No live dispatch.
- Dedicated Claude profile now has a narrow existing-engine seam: no inherited settings,
  built-in tools, hooks, skills, plugins, subagents, sessions, model fallback or cost cap.
  Host acknowledgement precedes native query; raw observations preserve null usage, observed
  models and exact final-result bytes. Seven profile tests and existing SDK/completion scripts
  passed; production worker and runtime verification are still in progress, capability=false.
- Formal opt-in native test uses this profile through the existing engine factory, dummy auth
  and a localhost fake provider. PASS1/1 in5s with SDK0.2.116/native2.1.304: exact fixture tool
  inventory, requested model/effort, real tool hit/miss, unknown tools denied, outside canary
  unchanged, ambient hook/MCP/memory absent. This is synthetic, not real-model business evidence.
  Initial RED found ambient CLI discovery despite an explicit binary pin; trial availability
  now checks only that pin. A later timeout was a test-server query-string parsing defect;
  fixed without changing product behavior. Timeout cleanup terminates the owned process tree.
- Owner delegated pilot selection on22October. Selected first additional pilot: Python bug
  fixes in Javis-OS, using isolated repository snapshots and independent behavioral/regression
  tests as the business criterion. Preserve source-family splits, frozen qualification and
  all attempts. This choice does not close the spec's data-reconciliation Pilot A or document
  Pilot B gates; no historical case or user skill has yet been selected or run.
- Fresh worker and parent IPC now validate pinned workspace/config/capability, bind every
  packet to trial/attempt/input hash and require a host start acknowledgement before query.
  The parent callback must be bound; Task3/4 will supply the shared durable ledger callback.
  Fresh allowlisted env reaches the child, never inherited server tokens or turn authority.
- Windows worker ownership uses a kill-on-close Job Object attached before the initial input;
  POSIX uses an owned process group and existing winproc cleanup. A real descendant was
  terminated after its worker deliberately crashed. These are process-lifetime boundaries,
  not a sandbox for candidate Python code or permission to run host-side checker scripts.
- Latest explicit-native improvement plus console checks: PASS9/9 files in55s; py_compile
  passed for sandbox/profile/worker. A pre-existing console test assumed POSIX even when run
  on Windows; reproduced the same two failures on M0. Updated its expected platform flag,
  retaining the source canary; a negative control forcing the Windows flag to0 failed both
  assertions. New runtime/ACL subprocess calls use the existing hidden-console helper.
- Historical coding catalog:18 provisional families plus2 reserves, no parent-fail/fix-pass
  validation yet;44-family pilot not established. Details and independent-checker isolation
  gate are in `docs/dev/agent-skill-python-pilot-catalog.md`. No system skill is a writable target.
- Rebased M1 onto published09903315. Resolved the shared migration by preserving schema2
  and its backup under the transactional schema recheck; retained M0's new first-writer test
  and progress evidence. Post-rebase cases/store PASS2/2 in20s; diff whitespace check passed.
- PR795 now targets main ataf45da49 and remains draft. The temporary M0 backport worktree
  was archived through the app with a recoverable snapshot and PR794 reference; do not
  reuse its old filesystem path. Active M1 worktree remains unchanged.
- Contract review found missing public objective/criterion descriptions and an undeclared
  final artifact destination. Added strict required intent/output fields, a safe public
  projection without checker implementation refs, and portable output-path validation.
  Behavioral RED -> GREEN, case suite now28 checks, PASS1/1 in8s. M1 has not been released
  or enabled, so this tightens the draft contract before external records exist. Worker
  materialization of this public projection and complete installation receipts remain next.
- Task2 subsequently completed its public materialization and receipt components. Workspace
  requires a hash-pinned public contract and rejects private checker fields, missing intent
  and hash drift. Worker assembles all baseline instructions, assets and public requirements;
  no source truncation. Receipt binds journal/input/effective/prompt/contract/grant/fixture
  hashes, selected revision IDs and actual native inventory/model observations. Asset
  observed_use and actual reasoning remain unknown when unobserved, regardless of model claims.
- The fixture inventory view is a defensive copy, its grant is immutable, and binding rejects
  another broker/grant. Unexpected native tools or successful outside tool results are
  isolation failures. Native unavailable tools get explicit denial events; provider quota
  envelopes retain error/status metadata and nullable usage. No fallback was added.
- Fresh Python uses `-I -X utf8`, restoring only the trusted server source directory. A real
  child ignored malicious workspace sitecustomize/winproc modules even with hostile PYTHONPATH.
  Final explicit-native improvement/console run passed9/9 files in33s; SDK/completion
  regression passed2/2 in17s with an empty auth HOME, not a real credential/model call.
  Task2 is complete as a component; the parent start callback still needs Task3/4's durable
  shared ledger binding. No owner run endpoint or production capability is enabled yet.
- Task3 attribution substep: strict experiment/trial/case/variant/repeat/attempt/origin
  metadata survives async context/thread reads without a Team ID. Added improve_probe to
  the existing CallLedger, same mirrored trial reference; generic TTL does not settle live
  trial calls, and post-engine calls cannot be refunded. No fake goals or Team jobs.
- The existing usage index now projects improvement IDs with additive columns and a v2
  backfill cursor. Nullable/zero/late usage uses the same event file and aggregation.
  SDK and raw CLI records dedupe by actual provider request/session ID, not matching totals.
  Telemetry errors are scoped; ledger rows only expose missing observations, never bills.
- New usage suite8 checks and existing Team usage PASS2/2 files in6s; core ledger/index/turn
  regressions PASS4/4 in20s. Task3 remains open: host telemetry collector, global daily/TPM
  consistency, additional missing/late/conflicting coverage and durable runner binding.
- Global usage correction: unrelated raw chat previously erased trial usage for the whole
  provider/day. Improvement contributions now rebuild inside the existing daily/hourly
  index with exact fresh-session/request attribution and cache-component residuals. Late
  partial/full raw logs and repeated refresh preserve totals; cross-experiment session
  collisions remain partial rather than being allocated to either trial.
- Known request usage from an interrupted CLI run now reaches the existing legacy and TPM
  projections before a summary. Later summaries replace that attempt's snapshot, preserving
  timestamps and request identity. Unknown summaries retain observed request lower bounds;
  nullable usage and unpriced money remain incomplete in the trial view.
- Focused independent review identified partial-summary TPM loss, index timestamp drift and
  lifetime replay after daily retention. All three were reproduced RED and fixed GREEN.
  Improvement idempotency metadata is retained with lifetime totals; dropping it during a
  future compaction would be unsafe. Latest usage suite21 checks plus Team/index/quota
  passed4/4 files in8s. Expanded ledger/context regression passed7/7 in28s before the final
  retention-only fix. Host native recorder and durable runner binding remain next; no real
  model call, owner run endpoint or production activation has occurred.
- Task3 telemetry component now consumes raw SDK profile events in the host, bound to a
  matching genuine post-engine CallLedger row, brain, attempt and configured model. It
  records cache-inclusive token totals, nullable fields, request identity and subscription
  equivalents through the existing pipeline. Artifact/model text cannot set its execution
  identity. Session drift rejects; incomplete terminal coverage stays partial.
- Recovery reconstructs request/session/summary evidence from existing observations. Late
  summary can resolve missing coverage, while persisted telemetry errors remain. Even if
  event append fails, known usage reaches legacy/TPM and coverage reports the failure.
  Latest usage suite30 checks passed; expanded ledger/context/adapter/worker/usage regression
  passed9/9 files in32s before the last boundary-only test (then usage30 passed separately).
  All inputs were synthetic SDK messages; no real model call. Task4's durable runner must
  still persist its atomic start/lease and bind this recorder before releasing the ACK.
- Task4 storage component is in progress. Added schema3 trial/attempt/observation references
  in the same database; old metadata reads remain non-migrating and failed upgrade rolls
  back. Trial and CallLedger reservation/start are atomic. Concurrent logical reservation
  dedup, private host leases, pinned materialization, qualification consumption before input
  return, pre-engine refund and post-engine unknown recovery have14 passing store checks.
- Behavioral tests also found and fixed a forged effective hash despite a matching journal,
  boolean generation admission and preparation bypassing committed input exposure. Sandbox
  now recomputes its effective hash from actual manifest bytes. Native fake-provider and
  improvement/ledger regression passed12/12 files in52s before the last storage-only fix;
  store14 then passed. These are synthetic tests; no real query was started.
- Independent host evaluator component has23 tests:22 pass and1 file-symlink check skipped
  for unavailable Windows privilege; real junction protection passed. It preserves exact
  byte hashes, pinned checker/evaluator identity, separate structural/business verdicts and
  typed owner decisions. Candidate code/commands are never executed. Task4 still lacks the
  complete runner, heartbeat, event/result persistence and owner-decision service. M1 run
  capability remains disabled; no milestone/business/rollout completion is claimed.
- Storage review found one P2: sampling time before SQLite lock acquisition could authorize
  an expired lease. A deterministic transaction-entry clock test reproduced the defect;
  transitions now sample time inside the transaction and engine start rechecks immediately
  before its marker. Store suite15 passed after the fix. Final expanded improvement/native/
  ledger/Windows-console regression passed13/13 files in47s before this isolated clock fix;
  all native inference was a dummy localhost provider. No live/model/business evidence added.
- Task4 evidence/finalization component now has live lease renewal, immutable encrypted raw
  trace chunks, native artifact/receipt records and exact-byte output publication. Late
  evidence can be retained after cancellation without reopening or refunding an attempt.
  Host evaluation runs outside the write lock; result append, terminal state and existing
  call settlement commit atomically after fresh authority/output/lease checks.
- Terminal owner decisions bind the exact case/criterion/output/contract. Historical
  reevaluation appends a new encrypted report and preserves original execution, mandatory
  evidence, usage and ledger; old reports remain scoped and readable. Host abort records
  bounded reasons, refunds only before the marker and may close an expired owned lease.
- Independent review reproduced a trace mutation during unlocked evaluation. A behavioral
  RED-to-GREEN fix freezes normal packets at worker completion/evaluation and pins the trace
  head in reports. A second focused review of abort/reevaluation/history found no additional
  Important defects. Fresh results11 and trials29 checks passed independently; expanded
  storage/evaluator/owner/usage/ledger regression passed9/9 files in65s. These are synthetic
  component tests, with no real engine or business acceptance. Complete Runner integration,
  trusted context/source-grant service, owner API and selected-engine smoke remain required.
- Task4 Runner component is complete with21 synthetic lifecycle/integration checks, including
  a real NativeUsageRecorder boundary and32 storage checks. Parent caught an invalid execution
  ID that fake recorders admitted; the real-recorder test reproduced it and now passes.
  Raw packets persist before usage, the start marker/recorder precede worker ACK, process
  cleanup precedes evaluation, and reruns cannot create another query.
- Independent review reproduced repeated cancellation abandoning a start thread, plus
  preclaim policy revocation retaining a reservation. Cancellation now drains all owned
  state/telemetry operations and evaluator commit authority through repeated requests.
  An invalid unclaimed reservation refunds via strict generation/no-lease/no-engine CAS;
  a concurrent claimant is preserved. Both original reproductions and Runner21 passed
  independently after fixes. Trusted synchronous checkers must terminate; their threads
  cannot be forcibly killed, so the runner revokes commit authority and waits for them.
- Final Task4 regression passed13/13 files in90s (adapter/worker/sandbox/trial/evaluation/
  owner/usage/ledger), plus unchanged metadata API/assets/Windows-console3/3 in5s. Compilation
  and whitespace checks passed. No native/model query, business acceptance, API enablement
  or production rollout occurred. Continue Task5; the M0–M8 Goal remains active.
- Task5 components now bind encrypted complete host context, exact selected configuration,
  target generations, a narrow private fixture inventory and a revocable grant. Concurrent
  creation shares one binding; old events cannot reactivate it. Source/target/config drift,
  retired targets, missing encrypted chunks and policy/permission revocation fail closed.
  Inventory/grant creation precedes snapshot IDs, then every selected snapshot proves exact
  authorized membership and raw/fixture integrity. Qualification authorization reads no
  answers and changes no exposure/consumption state.
- Source capture22, nonsecret selection20, host binding19 and source membership17 checks
  cover real scratch filesystem/SQLite/encrypted-storage paths and synthetic host authority.
  Expanded component/lifecycle/usage regression passed10/10 files in74s; source17 passed
  separately after the final credential-metadata rejection. Independent primitive and
  fixture-integration reviews found no additional Important findings. No actual model,
  private production source read or trial endpoint was enabled.
- Complete production context needs more than a fixed file plan: ordinary dashboard uses
  SQL attachments/workflow state, directory membership/layout, plugin visibility and locale/
  channel inputs. Shared pure block extraction is in progress; a strict typed collector,
  concrete version/permission source provider and owner API remain. Do not mark Task5 or
  M1 done from these component tests. Full protected source retention and actual rendered
  baseline are distinct records; qualified inputs must remain selected-case fixtures.
- Shared pure production rendering is now extracted without changing production caps or
  block order. Trial-only full-protected mode retains exact profile, memory and project
  instruction bytes. A frozen pre-extraction oracle checks the actual production builder.
  Independent review found a removed compatibility matcher used by the existing prefix
  suite; its original failure was reproduced and the shared alias restored. Parent's fresh
  prompt/memory/language regression passed15/15 scripts in24s. This is a rendering component,
  not the complete read-only collector or an enabled trial endpoint.
- Concrete current-file provider19 and catalog15 checks now cover native ACL/identity,
  exact selected UTF-8 bytes, fresh source membership and production discovery precedence.
  Independent review reproduced and verified fixes for cross-member content/ACL/root drift,
  ordinary YAML dates and Windows filename casing. Mutable-file snapshot_version remains
  unsupported. No authorized source is silently refreshed and no raw catalog body is
  inserted into the baseline.
- Typed private capture v2 separates raw/semantic source pins from rendered model context,
  supports freshly revalidated dependencies with frozen clock/usage, and retains v1 history.
  Independent review reproduced SQL protected-text fixture aliasing and a raw target body
  mislabeled as discovery. Behavioral fixes check raw protected-text aliases, require file
  discovery metadata and reject full immutable target content in the common baseline.
  Parent's fresh provider/catalog/semantics/host regression passed4/4 scripts in14s. Complete
  dashboard composition, SQL lifecycle integration, owner API and real-engine smoke remain.
- Expanded source/context/storage/runner/usage regression passed13/13 scripts in78s after
  the independent fixes. The existing SQL component is under correction: a new readonly
  SQLite connection can create WAL/SHM files across lifecycle races. The selected production
  stores' existing native connection/lock must own the read instead. Existing SHM reader
  coordination is permitted; logical DB/WAL writes, migrations and new source artifacts are
  excluded. This is unfinished engineering, not evidence of a complete SQL collector.
- Fresh nonsecret selection remains anthropic-cli/claude-opus-5-5/medium/subscription,
  fast=false. Installed CLI changed from verified2.1.304 to PE2.1.308.0,
  SHA256c9796ba22a9221586b36371b36f5b66198d66eb4badf6a4cf4a5f7b07becea53,
  SDK0.2.116. Strict pin creation rejected the unverified runtime before native execution.
  Controlled dummy-provider qualification is separate pending engineering; no real auth,
  model call, implicit older-binary fallback or user configuration change occurred.
- SQL dependency component now has35 checks and independent final review. Reproductions
  caught readonly-native creation of missing sidecars and a DELETE-to-WAL mode transition.
  Every source now requires the production connection/close lock; this module never opens
  a source connection. Exact main-qualified SELECT/schema queries, owned read transactions,
  path/journal checks and lock ordering preserve logical source data and host connection
  settings. New source artifacts and hot-journal recovery are blocked; existing SHM read
  coordination is allowed. Parent's fresh SQL/context/Host/renderer/prefix regression
  passed5/5 scripts in19s. Full production composition and API remain unfinished.
- Project/session attachment templates now share pure rendering with protected trial mode.
  Ordinary limits/read order/errors and duplicate-row observations remain unchanged; trials
  retain complete pinned text and all rows. Parent review caught full raw files retained
  together after extraction (15 source bodies instead of the legacy at most2). A weakref
  regression reproduced it and bounded prefix/original-length observations restored ordinary
  retention. Incomplete prefixes cannot claim full protected text. Parent's fresh attachment/
  renderer/project/agent/prefix regression passed6/6 scripts in17s, including13 new checks.
- Exact Windows CLI2.1.308/SHA256c9796b…ea53 with SDK0.2.116 is now technically qualified
  and allowlisted. The developer opt-in uses scratch HOME, dummy authentication and bounded
  localhost fake responses only. Actual native tools remained fixture-only; ambient hooks,
  skills/plugins, unauthorized tools, fast override and session persistence were absent.
  Pending-query job close killed all4 owned processes after1 request and0 retries.
- Qualification caught SDK descendant launches missing CREATE_NO_WINDOW. A temporary,
  restored wrapper exists only in the single-query isolated worker; actual native SDK
  version/query launches both observed flags134217728. Parent independently reran native
  qualification/profile/worker/selection/console5/5 scripts in17s. Raw qualification evidence
  is in docs/dev/agent-skill-runtime-2.1.308-qualification.json. No real account auth/model
  query occurred; actual reasoning and asset-use coverage remain unknown.
- The prewarmed plugin capability projector now passes focused verification and independent
  review. It observes actual cache/source/locale inputs without loading plugins or calling
  visibility hooks. A real scratch SQLite/actual-main regression confirms the future
  owner/web/no-agent Goal branch even with another enabled agent. Its claim covers displayed
  capabilities; hook/HTTP/webhook execution authority and a complete Dashboard remain outside
  this component. Unsupported dynamic states fail closed. Parent's fresh smoke/plugin/
  Runner/task regression passed4/4 scripts in57s; full API and integration remain unfinished.
- A controlled selected-engine attempt verified the exact native runtime and configured
  account profile, then failed before reservation/query on an overlong Windows encrypted
  blob path. Ledger and engine marker stayed empty; this is not model feasibility evidence.
  The private output is retained. An early explicit output-path gate and a fresh shallow
  test root are being prepared; no provider/model/reasoning fallback is allowed.
- Process-owned trial task supervision now retains committing reservations across HTTP
  cancellation, dispatches once and commits explicit owner cancellation before worker
  cancellation. Shutdown drains pending starts, uses only acquired writer tokens and waits
  for cleanup. Independent review reproduced one foreign-lease shutdown defect and four
  cleanup failure variants; all original reproductions now pass independently. Parent's
  fresh15 task/24 Runner checks passed2/2 scripts in38s; independent rerun passed in36s.
  Unknown cleanup remains a visible shutdown failure. HTTP/lifespan integration is pending.
- The explicit shallow-root selected-engine feasibility query completed. Requested and
  observed model is claude-opus-5-5; configured effort is medium. Authorized fixture read
  and the JSON product checker passed; one baseline/repeat and one existing marked call
  settled ok. Aggregate verdict remains unknown for actual reasoning/internal skill use
  and incomplete native event/tool outcome coverage. Tokens4362/158 are observed with
  partial request attribution; request count is null. USD0.0226818 is a subscription
  equivalent reference, not a cash charge. No candidate, qualification execution or live
  activation occurred. Sanitized evidence is in
  docs/dev/agent-skill-selected-engine-feasibility-2026-10-23.json; private encrypted history
  and key remain under ignored .superpowers/live-a. The failed deep-path attempt had no query.
- Smoke13 checks cover real encrypted storage with synthetic adapters, cancellation report
  survival, durable marker recovery despite usage failure, Windows UTF-16 path budget and
  separate evaluator/execution summaries. Independent originals passed after two report
  fixes. Parent's fresh smoke/adapter/Host/results/Runner/tasks/storage/usage/worker/console
  regression passed10/10 scripts in91s. This does not establish business benefit or enable
  production trials. Task5 owner API contract is frozen in
  docs/dev/agent-skill-owner-trial-api-v1.md; concrete Dashboard review/fixes, current SDK
  CLI resolution, service/route/lifespan wiring and whole-branch review/CI remain.
- Current ordinary SDK CLI resolution is now concrete and read-only, including exact
  override/PATH/extra-directory/loaded-cache/cold-cache priority and source/runtime guards.
  Independent review found no Important defect; parent caught a missing source constant
  escaping as KeyError and added a behavioral safe-unavailable regression. Selection32
  checks pass, and parent selection/Host/smoke regression passed3/3 scripts in29s. A separate
  metadata-only actual-machine check resolved the same qualified CLI bytes (SHA256c9796b…ea53)
  with claude-opus-5-5/medium and no finder-cache warming/native query. Application module
  imports remained inside scratch state. Full owner service/routes remain pending.
- Fresh main is now046ea863/version0.290.0 (#796/#797). Open PR inventory contained only
  this draft; reservation was advanced to0.291.0 in ef617bf9 and PR795 retitled. Rebase/main
  reconciliation waits for current owned source changes to be frozen/committed; do not
  rebase over active agent edits. No integration or final CI claim yet.

- Concrete Dashboard capture now passes30 component checks and independent originals.
  Native user/ancestor contributors outside the closed profile reject capture by presence;
  actual loaded renderer/helper identity changes also reject without executing builders.
  Private fixture bodies embedded in longer protected text are rejected both before
  snapshot publication and by both Host guards, including manually inserted qualification
  snapshots. Independent reproductions confirmed no blob/event publication, answer read,
  qualification consumption or model call on rejection. These fixes do not attest native
  internal asset use or remove the selected-engine aggregate unknown verdict.
- Concrete owner-service composition retains initialized ordinary SessionStore/WorkflowRunStore
  native connections and locks. Independent review found stale singleton ownership could
  survive replacement; parent behavioral regressions reproduced it, then pre/post source
  lifetime checks fixed it. Parent and independent service11 checks passed; actual ordinary
  replacement foreign-owner session now rejects. Construction does not capture, warm stores,
  authenticate or query. Routes, reservation associations and lifespan wiring remain pending.
- Stored context metadata/revocation is being extracted into dependency-free HostContextRecords
  so cold status and explicit revocation do not need source/engine composition. The moved
  helpers are AST-identical; independent records5/Host24/snapshot25 checks pass. Existing
  SQLite SHM reader coordination is permitted, with no logical DB/WAL/blob changes. This
  is a component checkpoint, not API enablement or completed M1/business acceptance.

- Snapshot capture, immutable owner context/contract/case-set associations, cold context
  records, bounded request schemas and safe historical trial views now pass component
  verification and independent review. Associations reject legacy unassociated adoption,
  cross-context/contract rebinding and unauthorized snapshots across every split in one
  writer transaction. Public contract checker pins are host-resolved and never executed
  by the parser. Requests are bounded to2MiB/depth32 with exact unions; selected timeout
  is1..300 seconds per technical attempt, without a money budget or model override.
- Safe status distinguishes product and execution verdicts, excludes private checker
  reason/evidence and native paths, and reads stored usage snapshots without ingesting
  the ambient usage index. An independent pointer-integrity defect was reproduced then
  fixed: both result and blob hashes are checked in the original read snapshot. A real
  concurrent owner reevaluation preserves that initial status/result generation.
  Unknown usage remains null, known zero remains zero, and subscription equivalent
  stays separate from reported cash. Parent's fresh eight-script regression passed83s;
  independent association19, requests21 and views7 checks also passed. APIs remain off.

- Explicit owner admission and the13-route API are now wired into main on the draft
  branch. Browser owner sessions remain mandatory even for full API tokens; existing
  global authentication/CSRF still run first. The route snapshot adds exactly13 entries.
  Cold metadata never constructs a trial service/source collector or ingests usage.
  Production and developer capabilities remain false pending M1 final verification.
- Admission freezes actual associated IDs and all nine pins into an immutable experiment
  plan. Real native availability runs before reservations; one existing DB transaction
  commits qualification claims, trial, call and owner intent. Historical replay keeps
  its original deadline; changed requests/slots conflict. M1 changed candidate bodies
  are explicitly unavailable until M2. Admission26 and helper6 checks pass independently;
  an incompatible-plan race commits exactly one linked trial/call with no exposure.
- The process-owned service now retains full preflight/admission through HTTP and repeated
  internal cancellation. Review reproduced cleanup-read interruption and a shutdown
  handoff after the close flag; both are fixed and independently verified. Queued task
  reservations refund without dispatch, foreign leases survive shutdown, and genuine
  cleanup failures remain visible after operation removal. Parent owner-service11 checks
  pass. Main shutdown also moves its factory-lock wait off the event loop and retains
  close through repeated cancellation; main7 checks pass.
- Fresh parent integration regression passed12/12 scripts in137s. The newly public bundle
  endpoint exposed an inherited missing off-policy guard; component/API tests reproduced
  it, then the actual bundle writer was fixed after historical replay and before new
  work. Related store/API/helper3/3 passed23s; independent actual ASGI verification agrees.
  Route/auth security, prompt budget, Windows console and3 i18n scripts pass. One unrelated
  existing webhook test fails POSIX mode600 on Windows (observed666 after chmod600);
  its test and secret-store Git blobs are identical to origin/main. No assertion was
  relaxed. Linux CI remains required, including the corrected POSIX scratch-parent path.
- The actual-main end-to-end protocol test passed in119.6s with synthetic Claude
  verification/execution only and a scratch persisted sonnet/high selection. All13 handlers,
  real ledger/NativeUsageRecorder/results, original-deadline replay, owner reevaluation,
  cross-brain denial, recovery/revocation and orderly shutdown were exercised. One synthetic
  execution observed partial3/2 tokens and null requests; product/execution/aggregate verdicts
  remain separate. Fresh whole-branch review/CI/rebase/publication are still pending.
  No additional real model query, business pilot, activation or production restart occurred.

- The branch is rebased onto main046ea863 (0.290.0); its reserved release is0.291.0,
  draftPR795. CI runs39841676424/39841707666 on90610221 are in progress and cannot
  validate subsequent review fixes. Fresh whole-M1 review reproduced three gaps:
  cancellation during threaded worker creation, plaintext workspace retention, and the
  missing default single-model-trial limit per brain. Integration remains gated.
- The worker creation gap now has two actual-child RED-to-GREEN tests plus a repeated
  cleanup-cancellation check. Spawn and complete cleanup remain owned through repeated
  cancellation; interrupted spawn sends no worker input. Independent original reproduction
  confirms the child is closed. Adapter20/worker9/Runner24/selection32/console checks pass;
  isolated native qualification5 also passes with dummy credentials and a local fake
  provider. The lifetime cleanup fix changes the profile again, so qualification must run
  on the final frozen profile. Historical real smoke remains attributed to06e75, with its
  original aggregate unknown verdict. Plaintext cleanup and concurrency fixes are ongoing.

- Review fixes are committed as3affde20/4c75c379. Plaintext cleanup now waits for the
  actual worker and checker lifetime, including repeated cancellation and storage failures
  during closing reads/abort. Both failure variants were reproduced before correction.
  Kernel locks enforce per-brain capacity and protect live workspaces across processes;
  the durable marker transaction independently checks running/evaluating capacity.
  Cancellation/recovery cannot release capacity while the old worker is still closing.
- Seven final regression scripts passed in300s: smoke, actual-main end-to-end, results,
  Runner, task supervisor,17 new lifetime cases and34 trial-store cases. The new lifetime
  checks include actual host-process death, recovery/replay, interrupted cleanup, encrypted
  history preservation and cross-brain independence. Independent original reproductions
  now show no orphan, no retained plaintext, one same-brain model trial and no cleanup
  before a blocked checker settles, including when storage reads/abort fail.
- Final isolated native qualification passed5/5 in15.517s on profile
  c3b4f27ee81899fa1ae650513ae5c4b051cdcfd7b4106635a2e6acd2209f4df6. Historical real
  smoke06e75 is unchanged. A separate14-script required regression passed205s, covering
  current learning, owner/grant, ledger/usage, Team acceptance, skill usage and prompt budget.
  The M1 verification map and recovery runbook document the boundaries. Crash cleanup is
  explicit scoped recovery; trusted host checkers must settle before ownership is released.
  Final independent review reports no open Important findings; its fresh Runner/lifetime17
  checks passed2/2 in53s and all original reproductions pass. Final CI/integration remain
  pending; business and rollout gates stay open.

- Linux CI39841676424 on earlier90610221 failed six scripts. The actual causes are now
  corrected: both changelogs had a malformed0.291 heading after rebase; two legacy tests
  still searched main.py for instructions moved into the shared renderer; and POSIX ctime
  was incorrectly used as creation identity for semantic settings/coding and protected
  ancestor directories. This made unrelated secret writes and SQLite journal creation
  falsely invalidate context, also blocking service/end-to-end context creation.
- Changelog correction8fa86ccf preserves older releases/parser/version; three related
  suites pass. Renderer regression correction80fe04a6 checks actual rendered instructions,
  dynamic brain paths and main wiring; valid native file-URI fixtures preserve Windows
  drives. Three related suites pass, with independent review finding no weakened checks.
- Dashboard correction0ea1e134 has portable behavioral RED-to-GREEN reproductions and
  independent content/permission/inode/native-ACL checks. Full Dashboard34, Service11,
  actual-main end-to-end1 and the portable original service reproduction pass. Only semantic
  change-time identity is normalized; protected bytes, file identity, selected projections
  and actual authority remain guarded. The native profile remains exactlyc3b4, matching its
  qualification evidence; no redundant native/model query was run. Actual final-head Linux
  CI remains required, and prior failed heads cannot satisfy integration.

- Final Linux CI39847154134 on23e546b9 failed only the actual-main E2E, with
  not_run/authority_changed before the engine marker. A portable actual E2E using
  Windows FILE_BASIC_INFO.ChangeTime as POSIX ctime reproduced the same failure
  in77.636s. A deterministic journal create/unlink between authority capture and
  its follow-up stat isolated an intermediate comparison that still treated an
  ancestor directory's fallback ctime as creation identity.
- The final narrow Dashboard repair ignores fallback ctime only for those ancestor
  comparisons; device/inode/kind/true birthtime, mode/uid/gid/attributes, original
  native ACL projection and exact protected-file incarnation/read guards remain.
  Actual fixture authority is unchanged. Six focused author checks pass46.475s;
  parent two deterministic tests pass9.907s; independent five checks pass38.578s
  plus actual intermediate chmod and true-birth mismatch rejection. The same
  true-ChangeTime actual-main E2E now passes146.543s, with one synthetic execution
  and unchanged unknown verdicts. Parent Admission/AdmissionTx/Service regression
  passes3/3 in61s. No actual model/native-auth query or runtime
  profile change occurred. Fresh final-head Linux CI, merge and publication remain
  mandatory; this technical correction supplies no business or rollout evidence.
