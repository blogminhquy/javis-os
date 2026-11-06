"""Guard the ChatGPT Live realtime request's partner identity without starting Codex.

This checks the actual `thread/realtime/start` parameter builder, not only the
pure text formatter. It does NOT prove that the remote model follows the prompt.

    python tests/python/test_voice_persona_payload.py
"""
from _paths import ROOT, SERVER  # noqa: F401

import voice_live
import voice_persona


def check(label, condition):
    if not condition:
        raise AssertionError(label)
    print("ok  " + label)


name = "Milo"
block = voice_persona.identity_block(
    name,
    "AI education adviser for Northstar Academy",
    "Be transparent that you are an AI assistant. Never claim to be human.",
    "Speak clearly and respectfully.",
)
prompt = voice_persona.apply(voice_live.CHATGPT_LIVE_PROMPT, name, block)

check("partner identity is at the very start of the voice prompt",
      prompt.startswith("# Bạn là ai trong cuộc gọi này\n"))
check("agent is identified before the generic Javis instructions",
      prompt.index("Bạn là **Milo**") < prompt.index("Bạn là Milo, một cộng sự"))
check("English self-identification survives prompt construction",
      'When asked in English "Who are you?"' in prompt
      and "I'm Milo, an AI assistant working within Javis OS." in prompt)
check("fictional academy role survives prompt construction",
      "Northstar Academy" in prompt)

# No Codex app-server or model is started: only serialize the outgoing request.
provider = voice_live.ChatGPTLive(
    system=prompt, app_server_getter=lambda *args, **kwargs: None
)
params = provider.start_params("fake-offer")
check("realtime/start sends the exact agent prompt to the provider",
      params["prompt"].startswith(prompt + "\n\n") and params["version"] == "v3")
check("a second handshake preserves identity rather than falling back to ChatGPT",
      provider.start_params("reconnect-offer")["prompt"] == params["prompt"])
check("ordinary Javis call keeps the normal prompt",
      voice_live.ChatGPTLive(
          app_server_getter=lambda *args, **kwargs: None
      ).start_params("plain-offer")["prompt"].startswith(voice_live.CHATGPT_LIVE_PROMPT + "\n\n"))

print("PASS: outbound ChatGPT Live prompt assembly (not a real Live call)")
