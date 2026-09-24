# Voice focus 0.64.28

Approved: free browser speech recognition, call Javis after idle. Explicit mic starts an
active conversation; 20 seconds without an accepted utterance or foreground reply enters
waiting. Short followups stay valid. This is an attention window, not speaker identification.

1. Test a deterministic gate before sending/persisting transcripts; latch utterances begun
   while active, require a final wake prefix while waiting, bound unfinished candidates.
2. Wire Standard/Fast, visible resume control, cancellation and settings. Default focus on,
   independently of the retired text filter toggle. Remove text-only noise deletion from Fast.
3. Live closes its provider connection while waiting. Browser wake recognition takes over;
   accepted wake+command is sent once after the new session is ready. Without browser speech
   support, show a click-to-resume control. No new API or VAD model dependency.
4. Test idle/cancel/handoff/duplicate ready with simulated browser boundaries; run regression
   suite, review, CI, merge and verify main CI and versioned GHCR image. Real acoustic quality
   remains unmeasured; TV saying the wake word and overlapping speech are known limitations.

## Verification and review

- Local: 136/136 JavaScript test files passed; after final lifecycle changes, all 18 voice,
  microphone, TTS and orb files passed again. Eleven relevant Python files passed, including
  real SQLite + production handler tests. Server/plugin compile and main import (271 routes)
  passed. No microphone recording or paid API call was used.
- Review fixes: click-resume discards buffered ambient speech; Live starts its idle window
  at ready; capture handoff waits for recognition end and respects cancellation; GPT-Live
  retains final reply, latest context, and delegated wake request. Running tools are tracked
  separately from playback and keep the session active until done, disconnect or user stop.
- Gemini incremental history follows https://ai.google.dev/gemini-api/docs/live-api/capabilities
  and OpenAI history/text generation follows
  https://developers.openai.com/api/docs/guides/realtime-conversations .
- CI and versioned GHCR publication are release gates after this commit. Actual noise and
  speaker-separation performance has not been measured; use the manual matrix in the audit.
