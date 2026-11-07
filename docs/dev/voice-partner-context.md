# Voice partner context budgets

Javis Voice calls launched from a partner chat build that partner's identity,
instructions, and memory into a realtime prompt. Chat text and realtime Voice
do **not** automatically have identical context windows.

## Defaults and bounded overrides

| Context | Previous default | New default | Environment override | Maximum |
| --- | ---: | ---: | --- | ---: |
| Partner Markdown body | 4,000 characters | 12,000 characters | `JAVIS_VOICE_AGENT_BODY_CHARS` | 24,000 |
| Partner memory | 2,000 characters | 6,000 characters | `JAVIS_VOICE_AGENT_MEMORY_CHARS` | 12,000 |

These budgets are Unicode character counts **inside Javis**, not provider
context-window sizes or audio token allowances. Overrides are loaded at server
startup and clamped between 1,000 and the documented maximum. Invalid values
fall back to defaults.

Bigger budgets increase the content sent to the provider. Actual latency,
provider limits, voice stability and cost still need real-call testing.

## Optional pinned instructions

An owner can put essential Voice rules anywhere in the partner Markdown file:

```md
<!-- JAVIS_VOICE_RULES_START -->
For ABC Company's sales assistant, check authoritative price and delivery
sources before quoting. Never claim an order was placed without a tool receipt.
<!-- JAVIS_VOICE_RULES_END -->
```

Javis moves this block ahead of ordinary partner instructions before applying
the character budget, and avoids duplicating it. An unmatched or empty marker
is left unchanged. This lets the owner preserve priority rules even when they
were written late in a large agent file.

Every partner Voice prompt also contains an always-on operational truth guard
outside both truncatable budgets: verify changing business facts through
authorized sources and do not claim completed actions without tool confirmation.
This is a defense in depth mechanism, **not** proof that the realtime model
actually called its tool or that any price source is approved.

## Scope and verification

- Applies to partner Voice prompt assembly on existing Live/fast call paths.
- Does not expand ordinary chat memory, approve data sources, create orders,
  add telephony/SIP or change the caller's selected voice.
- Test with `python tests/run.py voice_persona` and compare first-turn
  provider payloads plus actual tool receipts in a consented Live test.
- Before telephony rollout, add call-specific data access, approval gates,
  outbound calling policy and a human handoff path.
