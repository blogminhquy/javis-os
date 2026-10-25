# M4 engineering: skill routing surface and engine coverage

Date 25/10/2026. Base: 0.316.0 (M3 canary). Spec sections 9.2 (description is its own surface), 10 (executor and
isolation), 16.1 (body then routing), 22 (A03, E01-E06), 23 (M4). Goal section 13: code and technical checks
first; real engine smoke and pilots need the owner's go-ahead (Phase 2).

## Facts from the code

- Javis routes skills in two ways. API engines get the lazy router (`lazy_skill_runtime`, deterministic scoring over
  name/aliases/summary) and the skill index in the system prompt (`skill_router.list_skills`), then load bodies with
  `javis_use_skill`. CLI engines (Claude Code, Codex) also read `.claude/skills` natively and pick by description.
- Only Javis's own scoring is deterministic. Native CLI selection is model behaviour and can only be measured with
  real runs.
- M2E/M3 overlays are body-only: the resolver refuses any frontmatter change.

## Units

### U1. Routing case set and deterministic evaluator

Cases: `{query, expected: <slug>|none, kind: positive|negative|competing}`, locked per experiment, split like other
case sets. Evaluator runs the actual lazy router scoring over two metadata views (baseline, candidate description)
and labels each case `selected_correctly | missed | selected_unnecessarily | wrong_skill`. Report: per-case table,
W/L/tie with the existing sign-test helper, and the hard gate of spec M4: the candidate may not increase wrong or
unnecessary selections on negative and competing cases. This measures Javis's router only; native CLI routing is
reported as "not measured" until a real-engine pilot.

### U2. Description candidate and routing activation

- A routing candidate changes only the `description` value (<= 150 characters, the router truncation). Validator:
  body bytes, every other frontmatter key, name/slug, enabled state and group unchanged; translations
  (`description_<lang>`) untouched unless declared.
- Schema 13 adds `surface` to activations through an add-only table `improvement_activation_surfaces`
  (`activation_id`, `surface body|description`). The resolver keeps body-only rules for body overlays; a description
  overlay changes only the metadata the index and the lazy router read, in the same assistant DM scope and only for
  in-process engines. A disabled skill is never listed because of an overlay.
- Canary and promotion from M3 apply unchanged.

### U3. Telemetry: available, selected, observed use

A per-turn receipt for the covered paths: which revision metadata the index offered (`available`), what the lazy router
selected (`selected`), and which body `javis_use_skill` served (`observed_use`). No event does not prove the native
CLI did not read the skill; the report says so.

### U4. API engine trial adapter (spec 10.3 preferred V1 adapter)

A trial adapter for the API engines Javis already runs with a host-controlled tool inventory: only the pinned fixture
read tools and an output-write tool, no hub connectors, no shell, no web. Isolation matrix E01-E06 with a localhost
fake OpenAI-compatible provider in tests. Enabled per engine only after its matrix passes; the UI keeps "not
supported" for others. Real smoke per engine is Phase 2.

### U5. UI

Routing tab on the skill improvement panel: intent cases, baseline vs candidate selections, the regression gate,
and apply/canary for description candidates with the coverage note.

## Out of scope here

Native CLI routing measurement (model behaviour), real engine smoke, pilots.
