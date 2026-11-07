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
    "Customer support assistant at ABC Company",
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
      "ABC Company" in prompt)

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

# Partner calls must not inherit the main Brain's unrelated memory index.
# The partner's own instructions and memory are already included in the persona.
class _FakeProvider:
    def __init__(self):
        self.system = voice_live.CHATGPT_LIVE_PROMPT


seen = []
original_factory = voice_live._make_provider
try:
    def _fake_factory(cfg, system, recognition_lang, memory_index):
        seen.append(memory_index)
        return _FakeProvider()

    voice_live._make_provider = _fake_factory
    voice_live.make_provider({}, memory_index="Unrelated main Brain context",
                             persona=(name, block))
    check("partner call excludes unrelated global Brain memory", seen[-1] == "")
    voice_live.make_provider({}, memory_index="Normal Javis memory")
    check("ordinary Javis call retains its global memory index",
          seen[-1] == "Normal Javis memory")
finally:
    voice_live._make_provider = original_factory

# A different agent's role must not be polluted by the first agent's identity.
nora = voice_persona.identity_block("Nora", "Travel support assistant at ABC Company")
switched = voice_persona.apply(voice_live.CHATGPT_LIVE_PROMPT, "Nora", nora)
check("new agent gets an independent prompt", "Nora" in switched and "Milo" not in switched)

print("PASS: outbound ChatGPT Live prompt assembly (not a real Live call)")
