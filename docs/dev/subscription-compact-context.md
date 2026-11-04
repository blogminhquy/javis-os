# Compact subscription context

The optional Codex dashboard path replaces the large Javis kernel with a small execution
contract. Native Codex instructions, tools, brain rules and skill discovery remain enabled.
Claude, personas, API engines and other channels retain their existing prompt paths.

Enable with an ordinary settings merge, preserving all other configuration:

```json
{"context_runtime": {
  "subscription_prompt_mode": "compact-v1",
  "memory_relevance_mode": "strict-v1"
}}
```

Both flags are opt-in. Remove them to restore the previous prompt/retrieval policy.
Rendering retains the existing profile, project, session attachments, core, coding, language,
clock and learning controls. Protected blocks are never trimmed to meet a token target.
The source compiler can independently fall back for memory and skills. A compiler error
retains the compact execution contract and restores source discovery; a broken source reader
falls back to the original prompt. The hub continues to enforce authority in code.

Strict retrieval removes conversational filler, requires relevant word/entity overlap and
honors the confidence threshold. It can return zero results. Always-on identity records
remain protected; explicit recall with insufficient confidence restores legacy memory.
Frequent names are retained even if most of a brain concerns one business. Active task terms
help short continuations and recall, without pulling an old topic into a clear new question.
Only selected brain skills are loaded by the existing lazy source compiler. Brain routers
and the native Codex/plugin catalogs are separate; this change does not suppress the latter.
The contract asks for bounded reads, JSON filtering and reuse of evidence already loaded.
It does not silently truncate tool errors or native tool results.

## Usage and thread rotation

`subscription.usage` trace events and the additive WebSocket `usage_telemetry` frame contain
turn input, cached input, uncached input, output, usage event count, verified request count,
request count (null when unknown), completeness and measured last-request input. Trace events
also retain request-level usage observations. Input already includes cached input.

Cumulative provider counters reject duplicate or limit-only notifications. A request count
is verified only when each cumulative delta equals the provider's last-request usage. Cold
resumes without a baseline and batched deltas explicitly leave the complete count unknown.
Warm handles retain their baseline. The exec fallback still reports turn totals, without
claiming request-level telemetry. Estimates from the context compiler remain estimates and
are not substituted for provider measurements.

The historical `sessions.last_input_tokens` column remains a turn total. The new
`last_context_input_tokens` starts at zero and is populated only by measured request input.
No historical turn totals are copied into it. All subscription rotation decisions read
the new column; providers without request measurements cannot trigger rotation from totals.
Session IDs, thread IDs, decisions and history are not reset by this migration. Rollback
does not require dropping the additive column. The read-only trial schema allowlist admits
the new bookkeeping column without projecting it as user instructions.

Historical usage-page `turns` are observation counts, not a verified number of requests.
The parser exposes that count basis and the UI labels it accordingly. Cached input is
still processed input; these metrics do not imply a subscription-quota saving percentage.

## Validation and deployment

Run the repository test runner for subscription, memory, Codex steering, usage parsing,
prompt rendering, project/session context and trial SQL context. Windows path-sensitive
failures must be checked on Linux before deployment. Validate the changelog fragment with
`python tools/release.py check`; do not change VERSION in the contribution.

For an older running release, apply the code diff to a snapshot of that exact release,
then test it. Do not replace its main.py with the latest upstream file. Build a local image
from the existing immutable image plus only the changed files. Keep the original image,
compose, encrypted settings and a consistent SQLite backup outside the brain. Verify file
hashes before changing the service, wait for active work to finish, recreate only Javis,
then verify health, data counts, model choice, hashes and a fresh chat. Keep a concrete
rollback that restores the old image/compose and only the changed settings flags. Do not
roll back the live database over newer conversation data.

Use paired fresh sessions with the same model/reasoning: short answer, sourced recall,
Wiki lookup, read-only TickTick, a clearly labeled scratch journal write with readback,
and an authority check. Never turn test content into a personal fact or send messages.
Report each task separately: tool round variance can outweigh a smaller system prompt.
Text-token reductions exclude native instructions/tools/history and are not total wire
usage reductions. A native context floor may prevent a 5,000-8,000 input target.
