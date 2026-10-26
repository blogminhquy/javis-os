# M6 engineering: agent–skill bundle

Date 25/10/2026. Base: 0.321.0 (M5). Spec sections 9.2 (V3 rows), 14.3, 16.3, 22 (A04, Q06, Q07, S02, S06), 23 (M6).
Goal section 13 applies: code and technical checks first; helper execution on real data, real trials and any
bundle pilot need the owner.

## Facts from the code (survey 25/10)

- Three owner-applied overlay kinds exist, each with its own pointer table and read-time resolver:
  skill body for one assistant's chat (M2E `improvement_activations`, `effective_skill_asset`), skill description
  for the main chat (M4 `improvement_routing_overlays`, `main_chat_descriptions`), assistant procedure on chosen
  surfaces (M5 `improvement_agent_overlays`, `effective_overlay`).
- Each resolver already refuses its own overlay when the canonical bytes, identity or owner rules drift, and
  each table allows one live pointer per selector.
- `improvement_bundles` (M0) are immutable sets of captured revisions for trials; they are not pointers.
- Helper scripts: the M1 sandbox (`improvement_sandbox.py`) runs isolated native trials; no executable helper
  surface exists, and the spec requires an owner grant for the executable kind.

## Design

### Bundle = one pointer over existing overlays

A bundle activation groups members that already passed their own checks: at most one skill-body candidate
for one assistant, at most one procedure for the same assistant, and optional routing descriptions. The
members are staged objects (candidate ids, procedure ids), never live pointers. Apply creates the member
pointers and the bundle row in one transaction; revert moves every member pointer in the same transaction.
A member pointer created by a bundle carries the bundle id; the per-kind revert of such a member is refused
(revert the bundle), so the state is never half new.

### Availability is all or nothing (14.3, 16.3)

Read time: each resolver serves a bundle member only when the bundle is active and every member is still
servable (same canonical hashes, identity, owner rules). One member drifting suspends the whole bundle at
reconcile and hides every member at read time before reconcile runs.

### Dependency graph (A04)

The manifest lists members and `depends_on` edges by member key. The validator refuses cycles, missing
members, members of another brain or assistant, a member whose base hash no longer matches, and two members of
the same kind and selector, before anything is written.

### Attribution (Q06, Q07)

Pure report: arms present among baseline, agent-only, skill-only, combined. Only baseline vs combined means the
bundle as a whole is compared and component attribution is `confounded`; a combined arm never inherits the
separate arms' pass. Labels flow to the UI; no trial runs are added here (real arms need engine runs).

### Out of scope here (recorded as open)

Executable helpers in the sandbox with owner grant, skill split/merge with aliases, real ablation trials.

## Tests

A04 validator, S02 apply/revert atomicity incl. failure in the middle, S06 one member drifts so the bundle
suspends and no member serves, member revert refused, Q06/Q07 attribution labels, migration 14 -> 15, HTTP, UI.
