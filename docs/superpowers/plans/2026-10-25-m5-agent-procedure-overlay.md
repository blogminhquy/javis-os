# M5 engineering: scoped agent procedure overlay

Date 25/10/2026. Base: 0.317.0 (M4). Spec sections 9.3, 15.2, 16.2, 18, 22 (A01, L01-L03, S04-S06), 23 (M5).
Goal section 13 applies: code and technical checks first; an agent pilot and canary with real work need the owner.

## Facts from the code (survey 25/10)

- Every agent prompt except chatbots and goals comes from `_workflow_agent_helpers._agent_sysprompt(slug)`
  (server/main.py): name/role/body, skills list, assets, the whole agent MEMORY.md, JAVIS_LESSON/JAVIS_RULE
  instructions, toolkit. It knows only the slug.
- Surfaces and how the turn identifies them: dashboard DM (`kenh=dashboard`, `agent` set), CLI `/chat agent` and
  Telegram `@agent` (`kenh=cli|telegram`, no `agent`), workflow steps (slug only), Team (`_team_agent_info`, kenh
  team), Kanban "Giao việc" (`_agent_persona`, `kenh=kanban`, `job`), pulse/review personas. Goals never load an
  agent prompt; chatbots read only meta and body.
- Owner content: `## Luật chủ dặn` in memory/agents/<slug>/MEMORY.md (never auto-removed), owner lines outside
  managed sections (`agent_rules.missing_owner_lines`), `learn_lock`. Javis-managed today: `## Bổ sung (tự học)`,
  `## Lịch sử (tự học)` in the agent file, `## Bài học (tự học)` in memory, `agent_lessons` rows.
- Direct writers that bypass any staging: learn.py agent `op=update` (Bổ sung), `agent_review.apply_change`
  (offsets, eagerness, lessons). Out-of-scope review ideas stay as `agent_review_proposals` with no apply path.
- The improvement subsystem captures agent targets but every later step is skill-only; no agent trial arm exists.

## Design

### Overlay, not an edit

A procedure overlay is an owner-approved text block (planning, source checks, output checks, handoff format,
use of granted skills) appended to the agent prompt as its own section. The agent file, its MEMORY.md, owner rules,
persona, model/provider/reasoning, skills list, grants, schedule and the Auto switch are never touched, so A01
holds by construction. Host checks on the text: size bound; no `JAVIS_RULE:`/`JAVIS_LESSON:` or other host
markers; no lines that try to set model, provider, reasoning, permissions or skills (closed keyword list, refusal
rather than rewrite). Meaning-level contradiction with owner rules needs an independent reviewer (model) and the
owner's judgement: the apply step requires the owner's explicit confirmation of the exact text; the automated
contradiction review is Phase 2.

### Scope and surfaces

Selector: `agent_key` plus a chosen set of surfaces from `dm` (dashboard, CLI, Telegram agent chats), `team`,
`kanban`, `workflow`. A surface not chosen, or not covered, never sees the overlay (spec 16.2). Resolution happens
in one place, `_agent_sysprompt`, from the host-known surface: the caller passes it explicitly (`dm`, `team`,
`kanban`, `workflow`); no guessing from model text. The agent key comes from the registry for that slug; no key, no
overlay.

### Pinning (I10, S05)

A dashboard DM session sees the overlay only when the session was created after the activation and the overlay is
still active; revert and suspension apply to every new prompt immediately (the safe direction). Team steps, Kanban
jobs and workflow steps are new work each time and read the current pointer.

### Storage

Schema 14 (add-only): `improvement_agent_procedures` (immutable candidate text, base agent identity and owner-rule
hash at creation) and `improvement_agent_overlays` (pointer per agent key and surface set, active -> reverted |
suspended, generation, decision key). Owner-rule drift (hash of `## Luật chủ dặn` plus owner lines) or agent
retirement suspends.

### Staging the direct writers (spec 8.3)

When an agent is enrolled in the improvement path (owner switch per agent), learn.py `op=update` additions and
review ideas become procedure candidates instead of direct writes; un-enrolled agents keep today's behaviour.

### Lesson linkage (spec 15.2)

`agent_lessons.source_refs` gains host-written `overlay:`/`experiment:` refs through the existing `link` event; the
UI labels such a lesson "đã thử có đối chứng" only while the referenced overlay is active and evidenced.

### UI

Agent page tab "Cải tiến": draft or staged procedure text, surface checkboxes, explicit owner confirmation, apply,
active overlays with revert and suspension reasons, coverage note per surface.

## Tests

A01 owner lines and meaning (marker and keyword refusals; file bytes unchanged), L01 scope isolation per agent and
surface, L03 trial text cannot write lessons/rules, S04 owner-rule drift suspends, S05 session pin, S06 revert with
no prior, UI vi/en.

## Phase 2

Agent pilot (document agent, spec 24.2) with owner-scored briefs, automated contradiction review, agent canary.
