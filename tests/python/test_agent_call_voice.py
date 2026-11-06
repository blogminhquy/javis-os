"""Per-agent ChatGPT Live voice selection: isolated state, no provider/network calls.

    python tests/run.py agent_call_voice

Public fixture: Milo from fictional ABC Company.
"""
from _paths import ROOT, SERVER  # noqa: F401
import asyncio
import os
import tempfile
from pathlib import Path

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-agent-voice-state-")
os.environ["BRAINS_DIR"] = tempfile.mkdtemp(prefix="javis-agent-voice-brains-")

import main  # noqa: E402
import voice_live  # noqa: E402

def check(label, value):
    assert value, label
    print("ok  " + label)

root = main._brain_root("brain")
ag_dir = main._agents_dir("brain")
ag_dir.mkdir(parents=True, exist_ok=True)
(ag_dir / "milo-adviser.md").write_text(
    "---\nname: Milo\nrole: AI adviser at ABC Company\nchatgpt_voice: maple\n---\n"
    "Respond within your specialist role.\n",
    encoding="utf-8",
)
(ag_dir / "nora-support.md").write_text(
    "---\nname: Nora\nrole: AI assistant at ABC Company\nchatgpt_voice: breeze\n---\n"
    "Respond within your specialist role.\n",
    encoding="utf-8",
)
store = main.get_store()
def partner(slug):
    return store.create_session(brain=main._brain_key("brain"), engine="cli", channel="agent:" + slug)

sid_milo = partner("milo-adviser")
sid_nora = partner("nora-support")
sid_default = store.get_or_create(None, brain=main._brain_key("brain"), engine="test", model="test")
cfg = {"voice": {"live_provider": "chatgpt", "chatgpt_voice": "juniper"}, "model": {}}
milo = main._voice_partner_settings(cfg, sid_milo, "brain")
nora = main._voice_partner_settings(cfg, sid_nora, "brain")
check("Milo receives Maple", milo["voice"]["chatgpt_voice"] == "maple")
check("Nora receives Breeze", nora["voice"]["chatgpt_voice"] == "breeze")
check("Global setting unchanged", cfg["voice"]["chatgpt_voice"] == "juniper")
check("Normal Javis chat uses global voice", main._voice_partner_settings(cfg, sid_default, "brain") is cfg)
check("Unknown session does not override voice", main._voice_partner_settings(cfg, "", "brain") is cfg)
api_cfg = {"voice": {"live_provider": "openai", "live_voice": "cedar", "chatgpt_voice": "juniper"}}
check("API Live provider does not change", main._voice_partner_settings(api_cfg, sid_milo, "brain") is api_cfg)
(ag_dir / "milo-adviser.md").write_text(
    (ag_dir / "milo-adviser.md").read_text(encoding="utf-8").replace("chatgpt_voice: maple", "chatgpt_voice: unsafe-voice"),
    encoding="utf-8"
)
check("Unknown stored voice falls back safely", main._voice_partner_settings(cfg, sid_milo, "brain") is cfg)

# Save through the real agent API handler, then read the actual YAML frontmatter.
async def save(choice, slug="milo-adviser"):
    return await main.save_agent(
        name="Milo", role="AI adviser at ABC Company", skills="", model="", slug=slug,
        prompt="Respond within your specialist role.", brain="brain", model_provider="",
        group=None, avatar_shape=None, avatar_palette=None, avatar_color=None,
        avatar_eye=None, avatar_eye_color=None, avatar_eye_size=None, avatar_image=None,
        tags=None, reasoning=None, chatgpt_voice=choice,
    )

saved = asyncio.run(save("maple"))
check("Save endpoint accepts an allowed voice", isinstance(saved, dict) and saved.get("ok") is True)
meta, _ = main._read_md(ag_dir / "milo-adviser.md")
check("Voice persisted in agent frontmatter", meta.get("chatgpt_voice") == "maple")
check("Saved voice used on next call", main._voice_partner_settings(cfg, sid_milo, "brain")["voice"]["chatgpt_voice"] == "maple")
bad = asyncio.run(save("not-a-real-voice"))
check("Unsupported voice rejected", getattr(bad, "status_code", None) == 400)
meta2, _ = main._read_md(ag_dir / "milo-adviser.md")
check("Rejected value did not overwrite saved voice", meta2.get("chatgpt_voice") == "maple")
saved = asyncio.run(save(""))
meta3, _ = main._read_md(ag_dir / "milo-adviser.md")
check("Explicit default clears override", saved.get("ok") is True and meta3.get("chatgpt_voice") == "")
check("Cleared voice returns to global default", main._voice_partner_settings(cfg, sid_milo, "brain") is cfg)
print("all ok")
