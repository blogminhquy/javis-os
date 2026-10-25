# D1 bounded read-only view observation

Scheduling addendum2026-10-24: [code-first M0–M8 plan](2026-10-24-agent-skill-improvement-code-first.md)
and Goal§13 now govern. Actual selected-account pair/final/feasibility/pilot and
canary tasks below belong to Phase2 after all milestone code/technical checks.
Technical native dummy/fixture/source tests continue in Phase1; old evidence and
acceptance criteria remain unchanged. No further real inference now.

Goal section12 applies; implementation continues inline under the existing M0-M8
authority. Base29f5bdd5, same worktree/branch/reserved0.299.0 and draftPR803.

## Evidence and scope before edits

Actual selected-account feasibility ddc5af2c made two calls, then the first v4
candidate cell timed out180s before materialization/query. Its reservation was
refunded. Preserve history, raw output, usage, deadline and no-retry behavior.
One subsequent read-only load_current resolved10.266s: twelve create_pin calls
spent9.246s hashing the same298624160-byte CLI. Profile evidencec184a053
(committed LF bytes; the original Windows working-copy hash was2c3d38b6).

Components/callers: improvement_views.EffectiveViews._load_current is synchronous
and read-only; called by load_current and resolve_request. Nested capture_sources
calls semantic.current_evidence and HostContextStore._snapshot_observe/_observe;
the selected_engine callback uses improvement_trial_selection.create_pin.
The latter reads settings twice, validates SDK/profile twice and hashes the CLI.
No native execution, model call, await or semantic publication occurs in
_load_current. Connection WAL PRAGMA and lazy decrypt missing-key behavior still
exist; this plan does not claim absolutely zero filesystem writes in helpers.
freeze_comparison and other publication paths remain outside scope.

Reject a process-wide metadata-only hash cache. A Windows sharing lock is also
unnecessary for this read-only unit and would interfere with updates; writable
memory mapping complicates its immutability claim. Instead retain fresh whole
binary reads at the bounds of one read-only view resolution. Intermediate
observations can reuse its digest after full ancestry/path identity/size checks,
fresh os.open/read-permission and before/after fstat checks, closing immediately.
Every original settings, SDK, profile, owner/grant, semantic, source, lineage and
publication check still runs at its current site. The result cannot return until
a second fresh complete binary read confirms exact original digest AND identity.

## Implementation and checks

- [x] First record focused RED for a private synchronous decorator on _load_current:
  twelve repeated pins cause exactly two complete CLI reads, independent outer
  calls hash again, threads cannot share observations. No inference/subprocess.
- [x] RED negative cases: same-length binary edit with restored mtime/identity
  metadata detected by final byte read; replacement/missing/reparse denied;
  settings/model/SDK/profile remain fresh within scope; exception/cancellation
  drops memo and preserves original error; final verification failure refuses
  the return value. Never keep open handles or bytes after scope.
- [x] Keep _read_stable entirely unchanged and always fresh, including dashboard
  code-source digest callers. Only create_pin opts into a new private _read_binary
  helper with bounded thread-local memo. Scope exit calls original _read_stable
  fresh; explicitly test nonCLI digest calls never memoize. Only _load_current
  uses the decorator. No
  helper outside existing81 source footprint, no API/receipt/checker change.
- [x] Actual EffectiveViews integration with an inert CLI observer in the real
  source-capture path verifies two full reads across twelve nested observations.
  Real create_pin runs separately in component tests. No native readiness is
  inferred from the inert observer; runtime mutation after last capture refuses
  output. Existing actual source mutations remain affected regression checks.
- [x] Focused GREEN then existing selection, view sources/lineage/reservations,
  materialization/qualification and trial runner affected suites sequentially.
  Reuse unchanged native worker/role/sandbox proofs only by exact source; changed
  footprint requires a new exact20 native qualification before account calls.
- [x] The old preserved view pins e7 and must refuse changed source; do not patch
  its authority to obtain a positive after-profile. Measure the actual12-pin
  read-only component or a newly prepared legitimate synthetic view with a new
  output file only after correctness checks; report timings and never promise a
  speedup before measurement. No account retry yet.
- [ ] Independent scoped review, exact native qualification/registration and
  final-head full CI. Preserve all old native registrations as history. Update
  docs/PR and continue observation-proof and full D2/E/F/M3-M8 work.

## Self-review and limits

Scope exit is the consistency boundary; no native process consumes a cached
binary inside it. Digest reuse does not claim OS-enforced immutability. A changed
binary left at return, including metadata-restored edits, fails a fresh full
read. A transient edit restored before the outer return has no native execution
inside this scope and the returned view corresponds to the verified final bytes.
This private decorator must not be moved around writes, async work, model/native
execution or outward callbacks that publish a result. Independent callgraph audit
is requested before coding. No owner/model/quality/holdout/live gate changes.

## Linux fixture correction

Actual CI40002516501 failed only the observation fixture because its runtime
sibling creation changed protected skill directory ctime after provenance.
Move only this inert binary into its own external temporary directory. Portable
entry-clock2RED27.959s ->2GREEN29.127s; native Windows2PASS29.016s/binary11PASS
0.765s; independent portable2PASS29.468s. Assertions/product/native81profile
unchanged. Actual final-head Linux CI remains mandatory. Evidence:
`../evidence/2026-10-24-m2d1-view-observation-linux-fixture.json`.
