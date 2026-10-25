# M2D2 routing-state foundation implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make discovery and actual skill reads agree when an authoritative skill
is disabled, before adding production effective-view/task/session integration.

**Architecture:** Keep the existing canonical → Claude mirror → legacy precedence.
A disabled skill at an earlier or equal source suppresses enabled copies there
and at lower-priority sources. Reuse skill_router for ordinary hub reads and
existing lazy discovery; do not introduce an activation pointer or an overlay.

**Tech Stack:** Existing Python, pathlib, CapabilityRegistry, LazySkillSource,
actual mcp_hub built-in handler and skill_usage sidecar. No model calls.

## Authority and scope

Full Goal M0–M8 and Goal section12 remain authoritative. This independently
testable repair is one prerequisite of full D2, not completion of production
effective views. D1 stable head999c207a has approved whole/scoped reviews and
exact native qualification81/958527ac; full CI39990661065 is running. Its account
pair, eligible final and owner/business/live gates remain open. Keep that evidence
source-bound and preserve the actual failed selected-account attempt.

Reuse the attached M2 worktree and reserved0.299 draftPR803. Main remains
d3d7cb36/0.298.0; no new release reservation is needed for this continuation.
Do not change the original D:/Project checkout, native adapter, schema, grants,
candidate status, owner semantics or any live setting. This unit changes no
PROFILE_SOURCES file; verify that fact rather than re-running qualified native20.

## Actual gap and callers

- `server/skill_router.py:resolve_skill_file` searches only enabled paths. A
  canonical `.disabled/<slug>/SKILL.md` does not stop a stale mirror from loading.
- `list_skill_manifests` already gives disabled entries precedence, while
  `list_skills` visits enabled entries first within each source. A same-source
  enabled/disabled collision can therefore disagree across discovery APIs.
- `mcp_hub._builtin_tools` resolves and reads the file inside the real
  `javis_use_skill` handler, then bumps usage only on successful loading.
- LazySkillSource refreshes manifests by stat signature and the real capability
  registry. Disabling an active canonical skill must invalidate its warmed
  selection even when an enabled stale mirror remains.

## Files and responsibilities

Modify `server/skill_router.py` only for source-state precedence. Add
`tests/python/test_skill_resolution_state.py` with isolated brain/state roots,
real file states, actual registry/cache and actual hub handler. Existing
`test_skill_usage.py`, `test_skill_caps.py`, `test_skill_da_ngon_ngu.py`,
`test_adaptive_context_phase8.py` and `test_skill_subtree_ship.py` are affected
regressions. Update the operator/progress/changelog records after evidence exists.

## Task 1 — authoritative disabled state through discovery and loading

- [ ] Record the exact source/consumer/test impact and initial native81 hashes.
- [ ] Add behavioral tests: disabled canonical suppresses each enabled fallback;
  same-source enabled/disabled collision stays off; disabled Claude source
  suppresses `.agents`; legacy-only enabled fallback still works; canonical
  enabled wins normally; a warmed hub handler refuses after disable without
  incrementing usage; a warmed LazySkillSource drops the disabled skill.
- [ ] Run `python tests/python/test_skill_resolution_state.py -v` and retain RED
  showing actual body resolution/discovery disagreement, not fixture errors.
- [ ] Make resolver check an authoritative disabled file before the enabled
  file at each source. Keep slug validation and source precedence. Resolve
  unreadable state conservatively; never continue into a stale lower source.
- [ ] Make list_skills suppress enabled copies with an authoritative disabled
  entry at the same source, without reordering unrelated ordinary entries.
  Use the same declared source ordering for legacy disabled state as manifests.
  Do not read bodies during manifest-only discovery or change frontmatter.
- [ ] Run new GREEN and the five affected scripts sequentially. For the pytest
  Phase8 module, use the repository runner or the exact supported pytest command.
  Record every actual exit/log and full source map. No fake runtime/usage call.
- [ ] Review the narrow source delta and real handler/cache evidence; scope any
  independent review to this new routing change. Do not repeat whole D1 review.
- [ ] Commit/push the complete unit and run final-head CI when the delivery
  source is stable. Existing999 CI is historical for later source changes.
  No D2 completion or live activation claim from this repair.

## Full D2 still required after this unit

Production support still needs immutable ordinary task assets, same-store
durable host task/session pins, qualified activation selectors (E dependency),
per-view capability/cache projection, common router/lazy/hub/helper resolution,
task-specific native materialization, exact telemetry and incompatible-resume
handling. Scope conflict must keep the baseline and notify; missing/foreign host
identity never selects an overlay. Do not use D1 comparison context as ordinary
production authority or manufacture an M0 revision from an A candidate body.

Read-only inventory is retained in the task's `d2_integration_map.md`. The existing
CapabilityRegistry has a single mutable skill source per brain, so task overlays
cannot overwrite it. Dashboard run_turn binds actual host session/message/agent
identity; context_runtime owns existing task/step IDs. Native sessions retain a
Claude session_id across turns and cannot silently reload a changed view.

SDK0.2.116 locally exposes setting_sources, skills, plugins, cwd and resume.
Official [SDK skills](https://code.claude.com/docs/en/agent-sdk/skills) documents
filesystem discovery governed by setting sources; [SDK plugins](https://code.claude.com/docs/en/agent-sdk/plugins)
documents local plugin directories. A per-task plugin with filtered discovery is
only a design candidate. It needs actual qualification of duplicate/global skill
exclusion, protected settings/permission parity, helpers and resumed sessions.
Do not disable user policy or copy credentials to make it work. Keep unsupported
adapters/selectors unavailable until demonstrated. Resolve these interfaces in
the next full D2 implementation plan before writing dependent source code.

## Self-review

This unit is ready to execute: concrete mismatch, actual callers and bounded
behavioral tests are known; no activation or native architecture decision is
needed to repair it. Full D2 design remains open and cannot be called complete
with baseline-only routing. E/F and M3–M8 remain mandatory under the full Goal.

## Task 2 — one stable ordinary skill read for hub and lazy loader

Impact before edits: skill_router gains a frozen per-read asset (not a durable task
pin); actual mcp_hub.javis_use_skill and LazySkillSource consume the same bytes,
source-relative reference and raw SHA256. Existing discovery remains header-only.
No experiment/view/native/schema/activation source changes. D1 native81 proof can
be reused only after exact source comparison. Full D2 task pins remain open.

Concrete mismatch: lazy selection scores a manifest then independently reads a
mutable path. A change in description/source between selection and body read can
attach the old capability revision to new instructions. Hub has its own mutable
read and can return a skill disabled while the read is in progress. Both paths
must refuse a changed source rather than promote a stale mirror or retry.

Interfaces in server/skill_router.py: frozen SkillAsset with slug, relative_path,
content:bytes, content_hash, frontmatter_hash and normalized text property;
read_skill_asset(root, slug, max_bytes=SKILL_ASSET_MAX_BYTES) -> SkillAsset | None.
SKILL_ASSET_MAX_BYTES=1048576, matching immutable improvement asset capacity.
Use source precedence/disabled resolver before and after one bounded binary read.
Compare path/descriptor dev+inode+size+mtime; compare ctime within each stat API
(to avoid Windows path-stat/fstat creation/change-time mismatch). Resolve inside
brain before opening, verify resolved path and source precedence after reading.
Inside-brain symlinks remain readable; an external target is refused. Do not add
learning/edit eligibility restrictions to ordinary system/pack/learn-locked reads.
No retry or writes. Unavailable/oversized sources return None. Hub retains its
60000-character display cap and counts only successful reads. Lazy retains its
current body limit and fallback policy, but also requires exact manifest relative
path and frontmatter hash from the scored capability to match this read. Receipt
source hash is exact original bytes, including CRLF, with explicit policy v2.

- [ ] Add tests/python/test_skill_asset_reads.py with real files, actual hub and
  actual warmed LazySkillSource: canonical/mirror/legacy bytes and raw CRLF hash;
  ordinary learn_lock/system-like metadata remains readable; outside symlink
  refused and inside symlink preserved (platform-supported fixture); disabled
  during binary read; source rewrite during read; exact 1MiB limit and oversized
  refusal; lazy metadata changes after scoring refuse loading; actual hub failed
  read does not increment usage; actual hub and lazy use the shared reader.
- [ ] Observe RED for these behavioral gaps before adding implementation.
- [ ] Add the shared bounded stable reader; extract header parsing without
  changing manifest-only discovery; wire hub and lazy without independent reads.
- [ ] Run GREEN, routing-state7, affected skill_usage/caps/language/subtree and
  Phase8 scripts sequentially. Retain source/log hashes and native81 comparison.
- [ ] Scoped independent review of this new delta and original reproductions;
  preserve whole-D1 and routing review. Commit/push only concrete verified result.
  Require full CI on actual final head. No Task2/full D2 completion claim from
  per-read stability alone.

Self-review: This is a working consistency repair on ordinary paths, not an
unused pin/activation scaffold. It preserves discovery limits, ordinary ownership
and disabled semantics, and does not claim same bytes across an entire task.
Oversize refusal is explicit instead of silently loading an unpinnable asset;
header/body/source mismatch does not auto-refresh and choose a different skill.
Native plugin design probe is separate synthetic evidence only: attempt2 FAILED
(stale cwd Read bypassed permission callback); attempt3 A and B-only continuation
PASS controlled Read/Skill deny-hook mechanism. No policy parity, Bash/other path,
resumed native session or production adapter support follows from that proof.


### Task2 independent P1 repair — descriptor authority

Reviewer confirmed at85bf8e68: a transient actual external Windows junction can
satisfy all pathname stats and final lexical resolution yet return external bytes.
Original repro/log preserved in task ledger. Do not approve/merge current unit.
Impact before repair: new server/skill_asset_io.py owns OS-opened descriptor
containment; skill_router uses it before any body read. Hub/lazy callers keep the
same API. POSIX opens each resolved absolute path component from a directory fd
with O_DIRECTORY/O_NOFOLLOW and opens the leaf nonblocking/nofollow. Windows
checks GetFinalPathNameByHandleW on the actual descriptor against the expected
resolved in-brain path; no second textual resolve substitutes for handle identity.
Both validate regular-file and size on fstat before reading; close all fds on
failure. Initial resolution retains ordinary within-brain link support. Unsupported
platform facilities fail unavailable, never use unchecked path fallback.
Tests add the exact transient junction/symlink window, actual inside-directory-link
support, and POSIX swapped FIFO refusal without blocking. Reader mutation fixture
must observe actual binary handle reads rather than the replaced Path.open seam.
First run new behavior tests on old source to establish RED; then focused GREEN,
original independent reproduction and same7 affected scripts sequentially. Source
native81 unchanged must be verified; full final-head CI still required. Reviewer
rechecks only this fix/new OS boundary and original affected behaviors.
