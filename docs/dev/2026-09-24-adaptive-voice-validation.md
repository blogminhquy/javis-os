# Adaptive voice: validation and rollout

Release: 0.64.35. Natural timing remains **opt-in**. No model classifier, paid API, extra audio capture, or speaker recognition has been added.

## Implemented boundaries

- Pure local policy/controller, one monotonic draft deadline. Recognition end/30-second rollover retains text under managed capture, including iOS.
- Incomplete phrases hold instead of calling the brain; explicit wait up to 90 seconds; saved drafts after inactivity, error, hidden tab or draft cap. Send/Continue/Discard and wake-name resumption.
- Per-session P75 pause adaptation after five valid samples, 20-sample limit, 150 ms maximum adjustment. No persisted voice profile.
- Before playback, new accepted text cancels the preceding response; response identities reject stale frames and existing TTS epochs reject old audio callbacks.
- SQLite receipts bind immutable raw text and message ID to each utterance. Model context is carried separately. Retry retrieves a receipt; it never reruns the action. Saved acknowledgement metadata survives history reload and a request to answer claims the existing message once.
- Compatible-server capability is required. Fixed timing remains fallback; Live uses its existing provider controller.

## Deliberately conservative acknowledgement policy

The free MVP has no general-purpose semantic intent classifier. A model answer beginning with an explanatory phrase is not sufficient evidence that no question is pending. `voice_answer_intents` is keyed to the exact assistant message; raw control blocks are inspected before stripping. Only complete definitions explicitly reviewed in `voice_turn_protocol.answer_complete` receive `answer_complete`. Other text, older messages without metadata, tool output, questions and confirmations remain `unknown` and produce normal replies.

This means automatic silence is uncommon in this release. The durable protocol, storage and Request an answer UI are functional, but no claim is made that arbitrary model prose is safely classified. Expanding this requires evaluated intent metadata, not a looser prefix rule.

## Evidence

- Local full JavaScript suite: 140/140 passed. Independent review findings resolved. GitHub CI remains the release gate.
- Production keepalive regression: initially closed capture reopens during pending audio, preserves queued audio, and respects hidden/suspended state.

- `test_voice_adaptive.js`: unfinished/complete/hold/negative/closing phrases, duplicate interim, identical subsequent utterances, READY revision, draft cap, bounded learning, metadata privacy.
- `test_voice_adaptive_ui.js`: production bridge with controlled DOM/time; saved draft can be manually sent after attention expiration, background never auto-sends, observation never sends.
- `test_voice_capture_lifecycle.js`: actual adapter in VM; iOS rollover retains draft, restart failure preserves draft, late final cannot change committed words, cancellation and old TTS callbacks.
- `test_voice_adaptive_frames.js`: actual app dispatch guard; a rejoined tab accepts a running response while stale/cancelled response IDs are rejected.
- `test_voice_turn_protocol.py`: SQLite atomic commit, restart retry, transcript conflict, request-answer idempotency, cross-session rejection, conservative question/confirmation fallback.
- `test_voice_protocol_ws.py`: production receive loop with real SQLite and simulated engine/socket; duplicate WS commit produces one stored user message, request-answer does not append another, model receives the requested content, tagged output retains identity.
- Browser fixture: production settings controls and adaptive renderer, simulated transcript input, real timer. “Ý là” remained as a saved draft and manual Send delivered exactly those words. This is UI evidence, not microphone/acoustic evidence.

## Device gate before making Natural default

Not performed in this development environment. User tablet Android feedback is required; do not present simulation as physical-device validation.

For each device (tablet Android, desktop Chrome/Edge, iOS when supported), run each row twice under Fixed and Natural. Mark actual end-of-intent manually, record early reply, split utterance, wrong silence, duplicate message, commit latency and first-audio latency. Use the same network, brain, voice and noise conditions for comparisons.

| # | Phrase/scenario | Expected |
|---|---|---|
| 1–5 | Open chat; switch page; read current note; ask time; ask a full question | One prompt per completed request |
| 6–10 | Negative answer; short answer; name-only wake; repeat identical request; full question with punctuation missing | No dropped reply, no duplicate |
| 11–15 | “Ý là”; “em”; “anh muốn em”; “có phải là”; “khi anh nói thì”, each followed by continuation | Hold the same draft |
| 16–20 | Long explanation; 30-second recognition rollover; browser spontaneous end; late corrected final; repeated interim | Preserve words, no automatic forced response |
| 21 | “Vâng” after action confirmation | Always process normally |
| 22 | Clear closing after trusted complete explanation | Store acknowledgement; Request an answer works |
| 23 | “Vâng nhưng kiểm tra lại giúp anh” | Normal response |
| 24 | Explicit wait for 20 seconds | No filler; no extra wake required |
| 25 | Wait expiry, then wake name or Continue | Same draft remains available |
| 26 | Continue before commit/first audio | Revoke pending response |
| 27 | Interrupt while a tool has started | Cancel best effort; no claim of undo |
| 28 | Disconnect between commit and receipt | One message/action after retry |
| 29 | Background tab / switch conversation | No stale auto-send or playback |
| 30 | TV, nearby person and fan while waiting for wake | Attention gate retained; no claim of source separation |

Acceptance before default: at least 50% fewer premature replies on unfinished scenarios (or no regression when baseline has zero), completed-request commit p95 no more than 300 ms slower, zero ignored action confirmations. Retain per-device results rather than pooling away Android regressions.

Rollback: select Fixed wait. Existing fixed endpoint settings remain stored. SQLite additions are additive tables, older readers ignore them.
