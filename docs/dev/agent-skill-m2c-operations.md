# M2C owner operations

This document describes the released 0.296.0 implementation. Published M2B is
0.293.0. These controls do not enable candidate/final execution, activation,
compose, arbitrary helper execution, or a business/live acceptance claim.

All routes use the existing Dashboard owner session and CSRF policy. An API token
alone cannot authorize them. The server resolves `brain`; callers cannot submit
native readiness, capability receipts, config pins, arbitrary commands, source
grants, schedule positions, or successful assessment flags.

## Explicit preparation and roles

Read the current experiment generation from
`GET /improvement-experiments/{experiment_id}`. The `expected_generation` below
is this experiment generation, rather than an A candidate/base generation or an
operation's own generation. Every POST has a bounded `event_key`. Reuse exactly
the same key and body for retries; changing an already recorded owner's intent
with the same key conflicts. No action automatically dispatches the next phase.

POST paths below are relative to `/improvement-experiments/{experiment_id}/`:

| Action | Exact fields besides `event_key` | Result |
| --- | --- | --- |
| `preparation-freeze` | `expected_generation` | Freeze the host-derived tuning-only baseline schedule; phase becomes `preparing`. |
| `preparation-next` | `expected_generation` | Admit the next actual baseline Trial and hand it to the shared Trial supervisor. It returns stored metadata without waiting for the model result; a pending prior cell or still-owned cleanup returns409 without reserving another call. |
| `preparation-complete` | `expected_generation` | Seal exact published result references after all preparation workers/checkers and plaintext cleanup have settled; phase becomes `proposing`. Unknown results remain unknown. |
| `propose` | `expected_generation` | Run the isolated improver on actual completed tuning evidence. Stage at most the remaining two A slots, atomically. A malformed batch gets at most one structural repair automatically. |
| `semantic-review` | `candidate_id`, `expected_generation` | Run an isolated reviewer on this experiment's exact A before/after/provenance, protected context, and granted declared dependencies; store an immutable separate receipt. |
| `semantic-arbitrate` | `candidate_id`, `receipt_id`, `expected_generation`, `expected_binding_hash`, `verdict`, `reason` | Record owner interpretation of the exact receipt/binding. Verdict is `pass`, `fail`, or `unknown`; the concise reason is encrypted. |
| `semantic-evidence` | `candidate_id`, `expected_generation` | Explicitly recheck current source/grants/receipt/native linkage and return assessments. This is an owned source-reading operation, not an ordinary metadata GET. It does not create a successful qualification. |

Proposer and reviewer are genuine `improve_propose` and `improve_evaluate` calls in
the existing CallLedger. They are not solver Trials or Team executions. A model
assessment, dependency verdict, owner interpretation, and native coverage remain
separate. Owner confirmation cannot erase a model failure, waive dependency or
native unknowns, mint an edit grant, or change A's immutable `unreviewed` status.
An executable dependency remains unsupported until its actual later isolation
and runtime qualification exist. Declared-reference coverage is not a proof of
all executable imports or dynamic dependencies.

Each declared dependency must match one exact already-granted file identity.
Markdown links resolve relative to their declaring document; plain resource
names beginning with `skills/`, `agents/`, `.claude/` or `.agents/` resolve within
that document's bound root. Equal spellings retain both meanings. Missing files,
relative escapes, external URLs, ambiguous grants and executable dependencies
cannot receive a dependency pass; no fallback to an unrelated same-name file
or broader source grant occurs.

The current34-source profile9dcf7184 is registered only for Windows CLI2.1.308
with binary SHA c9796ba2 and SDK0.2.116, bound to the complete hashes in the
[native evidence](../superpowers/evidence/2026-10-23-m2c-native-qualification.json).
Other source/runtime combinations refuse before version/auth/model probes.
Qualification uses dummy authentication and local inference; actual selected
account readiness is checked separately before execution.
Exact-source dummy qualification passed both complete5-test suites; separate
readiness verification retained the persisted opus5-5/medium/subscription choice
and made zero model calls. Injected test engines and the installed SDK DTO
library are not native qualification evidence.

## Cold history and stopping

These owner GETs read stored metadata. They do not create an execution service,
decrypt model/source text, capture current context, probe native availability,
refresh usage, recover work, or dispatch:

- `/improvement-experiments/{experiment_id}/preparation`
- `/improvement-experiments/{experiment_id}/operations`
- `/improvement-operations/{operation_id}`
- `/improvement-candidates/{candidate_id}/semantic-history`

History can remain readable after off/revoke. It does not restore permission for
current semantic inspection or a new model call. The explicit stopping/recovery
routes still work after off/revoke so existing ownership and usage can settle.

`POST .../cancel` takes `expected_generation` and `event_key`. Its immutable
`acknowledgment` records the original stopping fence; `current` separately shows
the state after draining. `stopping` is a valid unfinished response when a real
brain execution lock or cleanup proof is still busy. Database terminal status
alone does not prove that a native worker, checker, or result/publication thread
has ended. Cancellation fences actual native roles before joining their complete
workflows, and retains synchronous decision threads through repeated HTTP
cancellation.

`POST .../recover` takes only `event_key`. It touches this experiment's actual
comparison/preparation links, role operations, and every recorded attempt. It
does not scan/settle unrelated reservations or clean unrelated journals. Recovery
and explicit resume never dispatch automatically or regrant a revoked source.
An interrupted stop preserves capacity until exact cleanup is proven under the
shared brain kernel lock and the final SQL state still matches. A replay retains
the original acknowledgment and can return a newer `current` state.

Shared finite limits are 12,000 comparison cells plus 2,000 preparation cells,
14,000 distinct Trials / 28,000 attempts, and four role operations / eight role
attempts. Separate comparison/preparation limits cannot be exchanged. Full-size
SQL tests establish bounded query/cardinality behavior; genuine small-scope
integration tests establish actual lineage, workers, calls, cleanup and replay.
Structural SQL fixtures are not evidence of model execution.

Application shutdown closes the concrete role supervisors/workflows and owned
controller operations before the shared Trial service and underlying sources.
A cleanup failure is not a successful shutdown/readiness proof.

On Windows, native cleanup has a separate supervisor. A worker starts suspended,
enters its job, and resumes only after durable fences protect the actual shared
brain and attempt locks. Host death closes the control pipe; the supervisor
terminates and waits for native process generations before removing fences.
Empty job accounting alone does not prove process exit. Missing birth inventory
or supervisor death leaves recovery blocked; never delete a `.lock.native`
fence merely because its database row or host PID is terminal. Such a fence is
an unresolved cleanup condition, requiring actual process-lifetime evidence.
These lifetime proofs do not grant account readiness or business acceptance.

## Errors, evidence and pilots

Errors use fixed bilingual text and fixed machine reasons. Invalid closed JSON
is HTTP400, oversized bodies413, stale state/identity conflicts409, unavailable
owner/source scope403, and unavailable native/service capability503. Raw native
exceptions, source bodies, credentials, and CLI paths do not enter error text.

VI: “Không thể thực hiện yêu cầu cải tiến trong phạm vi hiện tại.”

EN: “The improvement request is unavailable in the current scope.”

Usage retains actual call/attempt identities. Missing observations stay null or
partial/unknown. A marked call is never refunded as if it had not started.
Subscription-equivalent USD is not cash charged. Technical feasibility results
do not establish business ROI or permit live activation.

The retained real-model technical feasibility ran on ddec90ad/profile aa51b4b9:
baseline, proposer, one structural repair and semantic reviewer made four actual
marked calls and staged two proposals. The baseline's JSON shape criterion
failed; business accuracy still requires owner confirmation. The semantic/native
verdict stayed unknown and candidates stayed unreviewed. Observed usage was
32,248 input /6,091 output tokens and USD0.3644214 subscription-equivalent, with
partial coverage and no known cash charge. Later source corrections do not
create fresh real-model receipts. See the [source-bound feasibility evidence](../superpowers/evidence/2026-10-23-m2c-real-feasibility.json).

The owner delegated pilot selection: reconciliation first, document processing
second, with Python bug-fix/testing as an additional technical pilot. Independent
business data, business acceptance, qualified effective-view execution, and live
canary/activation gates still require their actual evidence in later milestones.
