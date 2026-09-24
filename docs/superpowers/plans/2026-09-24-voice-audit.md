# Voice audit implementation plan

> Execute with systematic-debugging and test-driven-development, using focused parallel investigations for independent browser, Live, and server transcript paths. User has authorized implementation and release in this task.

**Goal:** Preserve complete voice turns and Vietnamese conversation intent across capture, transcription, playback, persistence and reconnects.

**Architecture:** Keep the existing standard/fast/Live modes. Repair ownership of asynchronous resources and transcript events at their source; use browser capture evidence rather than transcript length to select STT results. Preserve original user text when a model proposes destructive reinterpretation.

**Tech stack:** Browser Web Speech/MediaRecorder/Web Audio, JavaScript VM behavioral tests, Python async server/provider tests, GitHub CI and GHCR.

**Spec:** User-provided audit brief in this task, sections 1–7 (capture, transcript integrity, language, lifecycle, tests, fixes, release).

## Constraints

- Do not log personal transcripts/audio by default.
- Do not treat longer text as proof of better recognition.
- Preserve explicit language choices and Vietnamese default.
- No paid API or physical-microphone verification is claimed from simulation.
- Release includes VERSION, CHANGELOG, main push and verification of exact-commit CI/GHCR.

## Review focus

- Final MediaRecorder chunk after stop and overlapping recorder instances.
- STT completions out of order or after session/mode cancellation.
- TTS abort during recognition start, committed text surviving an abort.
- Model correction reducing a full command to a wake word or changing negation/numbers.
- Live connect/permission events after stop and fragmented provider transcripts.

## Tasks

- [x] Browser capture (`dashboard/voice.js`, `tests/js/test_voice_capture_lifecycle.js`): reproduce `head + tail` loss at recorder stop; keep per-recorder arrays; snapshot capture coverage/language; deliver STT in order; cancel stale work. Run `node tests/js/test_voice_capture_lifecycle.js` before/after.
- [x] Browser integration (`dashboard/app.js`): invalidate voice capture on session/mode changes and exit; preserve draft during transcription; verify selected-language settings reach Live. Exercise relevant handlers using VM tests with deterministic events.
- [x] Server transcript integrity (`server/voice_brain.py`, `server/main.py`): reproduce destructive JAVIS_NGHE replacement; accept only grounded edits; preserve original text/context and scope user_text events; remove transcript-bearing diagnostic prints. Run new regression tests and existing `voice_brain`, `voice_tap_am`, `nghe_sua` groups.
- [x] Live (`dashboard/voice-live.js`, `server/voice_live.py`): reproduce stop during permission/connect and old socket close after restart; reject obsolete sessions and clean resources; assemble provider user fragments into full final transcripts. Run provider and browser Live behavioral tests.
- [x] Audit report (`docs/dev/2026-09-24-voice-audit.md`): document mode ownership, concrete findings with file references, test matrix and remaining physical-device/audio checks.
- [ ] Verification and release: run relevant JS/Python suites plus repository gates, inspect complete diff, bump latest patch version, add truthful changelog, commit scoped changes, push main, verify exact commit CI and GHCR conclusions.

Local verification: 134/134 JS files; voice/STT/TTS and review checks passed. Final exact-commit CI/GHCR status is recorded in the task completion report after push.
