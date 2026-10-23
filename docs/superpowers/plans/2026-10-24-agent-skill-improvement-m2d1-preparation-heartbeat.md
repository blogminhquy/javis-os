# D1 preparation heartbeat scheduling

Full M0-M8 Goal section12 applies. Same worktree/branch/PR803/reserved0.299.0;
base01717332, approved bounded view observation/native20/registration. Preserve
all prior evidence; CI40002516501 is running.

## Evidence and impact before edits

Actual attempt5eede64f is terminal:2 marked calls, valid semantic review, first
v4 BASELINE cell prepared then not_run/authority_changed before an engine marker.
Its reservation was refunded; no second cell/selection/final.234.0495s scope-ready
to final,8673in/822out,USD0.0658008 subscription-equivalent partial; cash/requests
unknown. Canonical unchanged/plaintext cleaned. No unchanged retry or deadline rise.

Subsequent read-only host.live_guard plus actual result _guard succeeds9.141s,
0 native/model calls. The generic historical failure omits its original exception;
lease starvation is a hypothesis, requiring controlled reproduction.

TrialRunner._run_claimed.process holds its asyncio mutex across authority,
materialization, workspace.prepare, authority and prepared. Heartbeat needs the
same mutex before validation/renewal. Slow blocking filesystem/ACL work can expire
the lease while blocking renewal. workspace.prepare does not advance SQL
generation; prepared does and must remain serialized. Existing stale-writer,
source/permission checks and outer request deadline remain authoritative.

## Unit and checks

- [x] RED controlled real TrialStore/runner, synthetic adapter, short test lease
  and real workspace preparation delayed past that lease. Heartbeat must renew
  while filesystem work runs; owned execution completes with original deadline.
- [x] Revoke while preparation runs: no engine ACK, refund/cleanup. Repeated
  cancellation drains owned thread and holds actual execution lifetime until
  it settles, then removes plaintext and refunds without a model query.
- [x] Move only workspace.prepare outside runner mutex; preserve authority before/
  after, serialized prepared SQL transition, _settled_call drain and OS lifetime.
  No duration, lease/deadline, owner/source/grant, model, retry or checker change.
- [x] Targeted GREEN then existing24 runner and affected v4 reservation/
  materialization/lifetime regressions sequentially on frozen source maps.
  Reuse unchanged view/selection/reader/role proof by exact source.
- [x] Independent scoped scheduling review. Changed native footprint needs exact
  qualification/registration before another bounded fresh account attempt.
- [ ] Update evidence/docs/PR/CI; continue native observations/full D2/E/F/M3-M8.
  Do not call a synthetic reproduction the recovered historical exception.

## Self-review

Mutex release permits validating heartbeat, not another runner: OS execution
lifetime and durable lease remain held. SQL generation changes remain serialized.
Revoked authority and expired lease still refuse. _settled_call keeps ownership
of blocking filesystem work through cancellation; no native ACK/publication can
escape incomplete preparation. A single operation longer than the lease may
safely fail; this unit does not lengthen leases to hide slowness.

## Verified checkpoint

RED3 (1 failure/2 pass)8.029s; GREEN3/8.786s. Frozen affected regression
36PASS151.454s (24 runner,1 actual synthetic-adapter v4 pair,11 owner-service).
Independent scoped review approved;3PASS8.917s, log SHA
2ca533ae5f4d3180392b78c92baaa29361fd1f696ff5a31bcfdc084d478b6a8c.
No native/account calls. Exact new footprint qualification remains next.

Exact profile972175a2 now passes20 native enforcement checks94.829s. Public
qualificationa84d266d uses dummy providers/empty HOME;0 account calls. Metadata
6RED0.103s (one missing registration) ->6GREEN0.096s; old5 entries retained.
Independent exact registration audit and final-head CI remain required.

Independent exact registration approved:6PASS0.100s; all81sourcepins,5
qualification-test pins,3raw/4logs/fullrecord match. Audit SHAda67327e;
testlogSHAad2d0be5. Five prior entries/lookup AST/paired fixture AST unchanged.
No new account query; actual pair and observations remain open.
