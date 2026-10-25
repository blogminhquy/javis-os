# Harness² Private Experience Snapshot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans. One implementation owner; serial local app/native tests. Complete the preceding compose owner-panel review before starting code.

**Goal:** Run the actual pinned Harness² Library entry/index/retain/forget implementation inside a checked disposable private snapshot, with a bounded procedure-only Javis adapter.

**Architecture:** Extract unchanged upstream Library definitions and only their tree/context dependencies into attributed modules. A Javis context manager allocates its own private temporary root, validates every path/content boundary before calling upstream filesystem methods, and returns bounded text projections. This component grants no source permission: canonical encrypted recipe records, scoped retrieval consent and actual improver/Operation/candidate dependency enforcement must be integrated in the next unit before any product input consumes it.

**Tech Stack:** Existing Python standard library, private-directory/link checks, upstream pure tree/context/Library implementation; no package or executor installation.

**Spec:** docs/superpowers/specs/2026-10-22-agent-skill-evidence-improvement-design.md sections15,18,22 (L01–L02), and AGENT-SKILL-IMPROVEMENT-GOAL.md sections3,12–17. This is the independently testable filesystem component of the library requirement; it does not complete M8 or library integration.

## Global Constraints

- Work only in the existing managed checkout/branch; never modify D:\Project\Javis-OS. VERSION0.299.0 remains reserved.
- Pin upstream1cfe254e8d25b15f37048c3730134686abe60335; preserve Apache-2.0/copyright and definition/source provenance. No benchmark, provider, dataset, scheduler or second executor/ledger.
- Upstream rmtree/copy/write and mutable index may touch only a fresh checked root owned by this object. Never accept a caller-selected root, source path, entry path or SurfaceSpec.
- Index and plaintext snapshot are disposable derived data; they are never canonical authority, grant, evidence grade, activation or business proof.
- V1 maximum3 recipe projections; empty/NO_ENTRY is valid. Do not load a whole domain or rewrite facts into transferable instructions. Selection win never upgrades a recipe verdict.
- Keep verdicts helped|hurt|no_observed_effect|confounded|untested exact. Preserve supplied evidence grade; this component neither derives nor authenticates causal evidence.
- No product API/UI/native input consumer in this unit. Actual canonical recipe permission/retention/revocation and source-rule/profile checks remain mandatory before later retrieval; do not add placeholder authority callbacks or return a ready flag.
- Phase1 fixture/DI/localhost only. No actual account/model/provider query, native registration, activation, deploy/restart or rollout. Full M0–M8 Goal remains active.

## Review Focus

1. Windows drive/UNC/device/ADS paths and junction/reparse/symlink children must refuse before any upstream write/delete; the adapter generates all tree paths and opaque task/domain identifiers itself.
2. A failed replacement cannot expose a mixture of old/new entries or leave another scope's plaintext retrievable; fail closed and require a fresh snapshot after mutation failure.
3. A failed permission setup or cleanup must not silently report success, delete outside the allocated root, or remove canonical encrypted evidence.
4. Concurrent replace/read/close must have explicit single-owner semantics and no late operation after close; serialize methods with one local lock, not another executor.
5. NO_ENTRY, negative/confounded evidence, marker rejection and Unicode text must survive real upstream serialization/index reconstruction without inventing a positive verdict or retaining a forgotten entry.

## Reuse decision before code

| Source at pinned commit | Git blob | Actual reuse / narrow glue | Reason and consumer |
|---|---|---|---|
| harness2/core/library.py | 39e50684b4044e483a3c16a447958044d4b5e6de | Unchanged Library, has_experience, slug, domain_dir, _inventory, _field; change import wiring only | Actual add/EXPERIENCE/index/tree_of/retain/forget replaces a new Javis serializer; bounded private snapshot is sole consumer. Exclude root_for (caller-controlled run layout is unnecessary). |
| harness2/core/tree.py | c9bf1341226aac448f6ec82038cb6d3896799412 | Unchanged SurfaceSpec, _res, _rx, normalize_rel, is_allowed, _stub_paths, always_on_text plus exact required type/regex constants; read_tree/write_tree have three documented boundary-line adaptations | Actual Library dependency; read_tree uses p.relative_to(d).as_posix() and p.read_bytes().decode('utf-8'), write_tree's content write uses newline='\n'. This preserves forward-slash keys, strict UTF-8 and original procedure LF/CRLF on Windows. Closed paths and stronger host checks precede it. Exclude compile/hooks/validation/diff unrelated to this component. |
| harness2/core/context.py | 72f2868b06c13e30c031cb91c0f04dcd80293ec9 | Unchanged GRADER_VERDICT_MARKERS, _MARKER_SCAN_SUFFIXES, assert_tree_has_no_grader_verdicts and required typing/Path imports | Actual Library.add tripwire. It is only a marker check; Javis authorization and private-evidence filtering remain separate required consumers. |
| tests/test_workflow.py | 2b7ebeb1816346f606922816a6f3609c64e8f8cc | Adapt the library-prefix/marker and NO_ENTRY cases at lines108–129,187–203 to the real extracted owner | Whole test imports DemoAdapter/schedule/provider execution unrelated to this component; preserve behavior through actual vendor calls, document adaptation rather than claim the full upstream suite ran. |

Exact upstream bytes are already locally verified against Git blob identities in the preceding plan workspace under upstream-library-sources. Copy only these inputs into this plan's workspace when implementation begins; do not repeat the full upstream audit. Existing LICENSE is reused. Add definition-level raw and AST hashes plus import modifications to LIBRARY-PROVENANCE.json; never rewrite historical compose/proposer proof.

Javis retains _private_directory, check_ancestry/is_link, canonical encrypted ImprovementStore/RevisionBlobs, source/grant/current checks and future operation ownership. Direct whole-package installation would pull unrelated benchmark/runtime/config behavior; a fresh serializer would duplicate the specific implementation the owner asked to reuse. The extraction adds three small dependency modules and one bounded adapter, with no migration or native footprint change until an actual native consumer is introduced. Do not classify these presently unconsumed modules as supported native capability.

### Task 1: Actual Library inside an owned private snapshot

**Files:**
- Create server/improvement_harness2_library.py, improvement_harness2_tree.py, improvement_harness2_context.py: attributed extracted definitions, minimal import glue and the three documented tree boundary-line adaptations only.
- Create server/improvement_recipe_snapshot.py: private root lifetime, closed projections, fixed surface/paths, checked vendor calls, bounded inert output.
- Create tests/python/test_improvement_recipe_snapshot.py: actual vendor behavior, filesystem/lifetime boundaries and provenance checks.
- Create third_party/harness2/LIBRARY-PROVENANCE.json; extend PROVENANCE.md additively. Root owns public evidence/progress/reuse-map updates after review.

**Interfaces:**
- Consume improvement_sandbox._private_directory(path), improvement_blobs.check_ancestry(path)/is_link(path), and the existing bounded credential redaction helper. Do not modify those helpers or reuse a TrialWorkspace root/journal for unrelated purposes.
- Produce RecipeSnapshot(*, brain_id: str, scope_hash: str, engine_config_hash: str, language: str) context manager in improvement_recipe_snapshot.py. brain_id is a nonempty bounded string<=1000UTF-8bytes, scope/engine hashes are lowercase64hex, language is vi|en. It allocates a unique tempfile root itself; has replace(entries: list[dict]) -> dict, read() -> dict, close() -> None. No public root/path or caller-provided surface argument. Lock all public methods; closed or poisoned instances refuse read/replace; close is idempotent after successful cleanup.
- Each entry is a closed projection with recipe_id (existing bounded opaque identifier), manifest_hash (64 lowercase hex), cue, procedure, evidence_summary, verdict, confidence_basis. All text is UTF-8, NUL-free; cue<=1000bytes, procedure<=16384bytes, evidence_summary<=8192bytes, confidence_basis<=4096bytes. Maximum3 unique entries, combined serialized projection<=98304bytes. Empty list means NO_ENTRY; literal prose is never coerced into an entry. These are engineering bounds, not new user/model limits.
- Identity is fixed at construction; hash brain/scope/engine/language into a safe opaque domain, and hash recipe_id/manifest_hash into entry names. Fixed surface has no always_on, hooks, plugins, agents, scripts or stubs; only generated procedures/recipe-<digest>/SKILL.md content. Never pass user strings as filesystem paths. Build upstream experience from cue/procedure/evidence_summary/confidence_basis and verdict without upgrading it.
- read/replace return only {snapshot_hash, entries, index_text, coverage:'derived_snapshot', authority_status:'not_checked', business_proof:false}; entries contain the closed projection plus the actual serialized EXPERIENCE text and actual tree read back from Library.tree_of. Hash the deterministic returned identity/entry/index content; no filesystem path, source permission or ready flag. Do not include brain_id in returned text.

- [x] Write actual failing tests before modules: real add->read_tree/index, replace three entries then retain one/forget all, empty NO_ENTRY, negative/confounded verdict preservation, exact Unicode and maximum3. Mutating the caller's original entry list or a returned projection must not change the stored/read-back snapshot or its hash. Observe missing implementation RED; save command/output/exits and avoid fixture-only failure claims.
- [x] Extract exact definitions from verified upstream bytes with copyright/import adaptation; generate provenance hashes from those exact definitions. Check definition AST and raw blocks, not literal presence of a method name. For read_tree/write_tree retain original/adapted definition hashes and the three exact boundary-line diffs; exercise reconstructed tree/index inventory and LF/CRLF Unicode procedures on Windows as well as Linux. Generated EXPERIENCE/index text is read as normalized text; it is never a canonical raw-byte revision. Actual tests must execute Library.add/rebuild_index/tree_of/retain/forget; no mocked serializer/index.
- [x] Implement the context manager and closed projection validation. Allocate unique private temp root, establish existing OS permissions before plaintext, check ancestry and every extant child immediately before vendor mutation/reading/deletion, reject unexpected paths/files/reparse nodes and bound file counts/bytes. Before recursive cleanup verify the resolved absolute target is exactly the owned allocation beneath its verified parent. Do not offer arbitrary rmtree or path overrides.
- [x] Test four entries, duplicate ids, malformed hashes/verdicts/extra fields, oversize/NUL/credential/marker text and attempted path/SurfaceSpec injection refuse before existing snapshot changes. Validator rejection leaves current valid snapshot intact; unexpected vendor I/O failure poisons it, clears any returnable projection, and requires close/new owner. Do not swallow cleanup failure.
- [x] Test actual POSIX link escape and Windows junction/reparse when available, with an outside sentinel that remains unchanged; do not skip platform coverage silently. Test close while a checked vendor operation is blocked using a thread barrier: ordering is serialized, no publication after close returns. No second executor or repeated race loops.
- [x] Run the focused actual test module through tests/run.py isolation, then the existing sandbox/blob scoped tests only where helper integration creates a concrete affected contract. Use one serial local slot. Save full logs and exact raw source/test/provenance pins; independent scoped review before commit. Early isolated Linux verifies this component; final task-head full required CI remains an integration gate.
- [x] Commit the working component with limitations explicit. Keep canonical recipe/consent/improver/candidate integration and all M0–M8/pilot gates open; continue to the next library unit rather than treating a snapshot fixture as complete retrieval.

## Follow-on library integration gate

Before any product/native consumer uses RecipeSnapshot, implement canonical encrypted recipe records with immutable trace/revision/experiment linkage, owner rule/source/profile/freshness and retention tombstones; separately revocable scope/target/engine/language grants; metadata filtering/ranking before decryption and max3 retrieval. Compare normalized schema migration with existing immutable event reuse on actual query/CAS/retention cost, then record that concrete choice before code. Do not turn arbitrary caller entry dictionaries or model source_refs into authority.

Then wire actual ImproverInputs sealing (old recipes=[] inputs remain exact), actual propose/repair/Operation PREPARED/publish fences, and authenticated candidate/view/Trial/apply dependency propagation so later revocation/expiry cannot escape through generated bytes. Link agent_lessons without copying raw trace or promoting self/review prose to proved evidence. Only functioning enforcement across those consumers allows the subsequent orchestration replacement comparison. No library quality or token-saving claim follows from this component's fixtures.

## Plan self-review

This unit maps Goal17's actual entry/index implementation and checked-root boundary to one independently testable deliverable. Its five Review Focus inputs have explicit tests. Inputs/outputs are closed and do not invent source authority. The full spec's canonical permission/retrieval/retention/lesson/native dependency requirements are explicitly the next open unit, not declared complete here. No new schema/version/API or activated surface is necessary for this filesystem component. Goal3 already authorizes continuous plan decisions and internal task/review execution; no repeat approval is required.
