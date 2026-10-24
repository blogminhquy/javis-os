# M2 Future Schema Controls Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Execute the single bounded task and scoped review; no broader feature work.

**Goal:** Restore two existing future-schema regression controls so the actual current M2 code is tested against an unsupported future version rather than the now-known historical9.

**Architecture:** Change only each fixture's SQLite version assignment to the actual `IM.SCHEMA_VERSION + 1`. Preserve all production validators and existing refusal/no-backup/no-native/history assertions. Reuse the actual isolated project runner and schema fixtures.

**Tech Stack:** Python3.12/SQLite/unittest and existing tests/run.py isolation. No app/runtime/profile/schema/UI behavior change.

**Spec:** AGENT-SKILL-IMPROVEMENT-GOAL.md18; agent-skill-evidence-improvement-design22/23/M2; existing operations migration/execution regression contracts. This is a concrete M2 consistency prerequisite formerly carried in the now-deferred recipe-destination plan; it does not dispatch that schema11/permission feature.

## Global Constraints

Status: source21a5c0b1 complete, actual2isolatedGREEN, independent source-spec
compliant/qualityApproved0Critical/0Important/1Minor. T1-R1: pins were recorded
post-GREEN/no intervening edits, not pre-run; retain timing limitation for final
wholebranch. Proof2026-10-24-m2-future-schema-controls.json
SHA74a92878248c7a22f3d49e13b06a7c57c88f88688406daf1760a5d02569cf6fa.

- Work only in C:/Users/admin/.codex/worktrees/agent-skill-improvement-m2a/Javis-OS; never modify/reset/clean D:/Project/Javis-OS. Its .venv Python may execute with -B. VERSION0.299.0 unchanged.
- Direct owner Goal18 ends current Goal at M2 engineering plus committed Claude Opus5.5 handoff. No M3–M8 expansion, new Goal, real account/model/business/pilot/canary run, deploy/restart or activation.
- Exactly two fixture SQL statements change; no production source, schema literals, historical fixtures, error assertions, mocks, native profile, protected reservation test or other tests change. No new test or warning suppression.
- Use actual tests/run.py chay_mot isolation and no-real judge/review/team flags. One serial local app/native slot; no background/helper/model process left owned.
- Root owns public docs/evidence/review/CI/integration. No push, subagents, reviewer, sidebar chat or unrelated worktree access by implementer.

## Review Focus

1. Unknown future schema refuses before backup/mutation, while historical9 remains a known version.
2. Cold read rejects the unknown version and preserves existing prior-history equality.
3. An unknown schema cannot reach native capability verification or reserve a call.
4. Actual future number tracks SCHEMA_VERSION rather than another hardcoded historical value.
5. A test-only repair leaves production/native bytes and all existing assertions unchanged.

### Task 1: Dynamic future fixture assignments

**Files:** Modify tests/python/test_improvement_operations.py only in OperationMigrationTests.test_unknown_future_version_rejects_without_backup_or_mutation; modify tests/python/test_improvement_operation_execution.py only in OperationExecutionTests.test_unknown_future_schema_never_becomes_native_authority_even_if_old_guards_exist.

**Interfaces:** Existing tests/production APIs unchanged. Each SQL assignment becomes a parameterized update with `(IM.SCHEMA_VERSION + 1,)`; preserve the second test's WHERE id=1 and each test's original SQL scope.

- [x] Run only the two current named tests, serially through actual isolated runner, retaining full raw command/cwd/start/end/PID/exit/stdout/stderr. Confirm the existing hardcoded9 reaches a known-version guard and fails the intended unsupported-future assertion. If it already passes for an unrelated reason, inspect before changing; do not claim RED.
- [x] Replace exactly the two assignments: `connection.execute("UPDATE improvement_schema SET version=?", (IM.SCHEMA_VERSION + 1,))` and `connection.execute("UPDATE improvement_schema SET version=? WHERE id=1", (IM.SCHEMA_VERSION + 1,))`. Preserve every other source/test line.
- [x] Freeze raw LF/hash/Git blobs for those two files, run exactly the same two tests serially and require exit0. Existing backup/native sentinels and history/error assertions must execute unchanged. No full operations/native/archive suite.
- [x] Self-review exact two-line diff, commit only those two paths with English message, audit committed/tested equality, write same-plan task-1-report.md and complete raw logs. Explicitly release slot/resources. No further source edits or test reruns after freeze unless a real failure requires a documented correction.
- [x] Root obtains fresh scoped spec+quality review, resolves evidence limitations and records component proof. Reuse unchanged production/native/source qualification evidence only within its actual scope; full final M2 CI/wholebranch/qualification/integration remains open.

## Self-review and continuation

Each assignment currently uses historical9 while actual schema is10. The exact
test identities, desired code and unchanged refusal mechanisms are supplied;
there is no permission/success-criteria/schema change. Goal18 authorizes this
routine correction without another approval. After the task's gate, continue
actual M2D1/D2/E/F engineering and handoff; deferred recipe/library tasks stay
backlog and business/live acceptance remains PENDING.
