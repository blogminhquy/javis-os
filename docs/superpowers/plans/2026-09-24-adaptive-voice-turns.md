# Adaptive voice turns implementation plan

> **For agentic workers:** Use superpowers:executing-plans task by task. User approved implementation in this session.

**Goal:** Ship an opt-in free adaptive conversational endpoint with durable acknowledgement and unchanged committed transcripts.

**Architecture:** A pure policy and clock-driven controller own the draft deadline. Capture becomes an adapter when enabled. A durable SQLite ledger makes voice commits and requests to answer a recorded acknowledgement idempotent; the server validates the effective policy. Existing recognition, attention, brain, and TTS remain the adapters.

**Tech Stack:** Browser JavaScript, Python asyncio, SQLite, existing Node/Python test harness.

**Spec:** ../specs/2026-09-24-adaptive-voice-turns-design.md

## Global constraints

- Off by default; Standard/Fast only, no new paid APIs or model classifiers.
- Monotonic clock, at most 200 metadata events, no audio/text in diagnostic export.
- Draft cap 120 seconds / 4,000 characters; hold 90 seconds; unfinished expires after 10 seconds.
- Committed text immutable. Unknown context always responds. Pending confirmations never silently acknowledged.
- Tablet acoustics require user testing before enabling by default.

## Review focus

- Duplicate interim events must not extend deadlines (controller fake clock tests).
- Recognition rollover and late final must not lose or rewrite text (real adapter VM tests).
- Disconnect between persistence and ACK must not execute a second tool (SQLite retry tests).
- Confirmation, negative answer, or unknown prior intent must respond (server policy tests).
- Session changes, hidden tabs and cancelled response callbacks must not send/play stale work (integration event tests).

## Tasks

### 1. Local policy and controller

Files: dashboard/voice-turn-policy.js, dashboard/voice-adaptive.js, tests/js/test_voice_adaptive.js.

- [x] RED: drive `new Controller({now})`, `update(text)`, `tick()` with fake time. Assert “ý là” is never committed after 4 seconds, saved at 10; completed command commits once; repeats preserve deadline; hold resumes; sample adaptation bounded.
- [x] GREEN: implement `classify(text)`, `Controller.update/tick/submit/save/resume/reset/diagnostics`; actions are `commit`, `hold`, `ready`, `save_draft`, `cancel`.
- [x] Run `node tests/js/test_voice_adaptive.js`, then existing voice controller tests.

### 2. Capture and app lifecycle

Files: dashboard/voice.js, dashboard/voice-turn.js, dashboard/app.js, tests/js/test_voice_adaptive_capture.js.

- [x] RED: use existing fake SpeechRecognition harness; fire end with draft, verify no transcript delivery under managed endpoint; Stop/manual still delivers once; cancel late final discarded.
- [x] GREEN: add managed capture mode and rollover; wire controller updates and its sole deadline to app, draft controls and attention. Invalidate on background/settings/chat change. Block filler while draft/hold. Keep captured text through errors.
- [x] Run voice recognition/transcript/cancellation test group.

### 3. Durable voice protocol

Files: server/voice_turn_protocol.py, server/main.py, tests/python/test_voice_turn_protocol.py, dashboard/app.js.

- [x] RED: create temporary SessionStore, commit twice same utterance; assert one message. Attempt acknowledgement after confirmation/unknown: auto. Request answer twice: only one accepted. Reopen DB: retry still deduplicated.
- [x] GREEN: transactional ledger with stable message ID, effective policy, continuation ID, retry status. Advertise capability; tag async frames with response identity. Client keeps outstanding payload until receipt and requests answer by saved identity.
- [x] Run protocol tests and existing chat runtime/store tests.

### 4. Opt-in UI and release

Files: dashboard/index.html, dashboard/app.js, dashboard/i18n/{vi,en}.json, docs voice guides, CHANGELOG.md.

- [x] Add advanced mode Off/Observe/Natural, pace preset, reset learning and diagnostic download. Apply settings locally, preserve fixed endpoint fallback.
- [x] Run entire JS suite, relevant Python suite and full CI; record device test procedure rather than claiming hardware results.
- [x] Independent branch review and regression fixes; no remaining important findings in reviewed scope.
- [ ] Merge only green exact head, tag/release 0.64.35 after main CI and matching GHCR image.

## Execution ledger

- Version reserved in PR #447 before implementation. Reusing isolated managed worktree; original checkout untouched.

- Local policy/capture/SQLite tests exercised failures before implementation. Existing structural guards updated for the new optional path; production behavior tests added.
- User approved opt-in delivery before physical tablet benchmarking; device gate and conservative intent limitation documented in docs/dev/2026-09-24-adaptive-voice-validation.md.

- Independent review fixes: repeated identical utterance, closing acknowledgement classification, saved-draft manual send, contextual payload preservation, rejoined response identity, trusted intent metadata, pre-audio capture window, job reservation before receipt await, wake continuation. Each behavioral regression exercised in tests.
