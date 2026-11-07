"""A voice call from a partner's chat speaks as that partner, not as plain Javis.

    python tests/run.py voice_persona

Owner report 2026-11-05: in a voice call with a partner (Partners page) the call model had neither the Javis context
nor the partner's prompt, and asked who it was it answered "em là ChatGPT". No engine runs here: the pure prompt
builders, the session -> partner lookup in main.py, and (by reading the code) that every call path uses them.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import os
import tempfile

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-vpersona-")
os.environ["BRAINS_DIR"] = tempfile.mkdtemp(prefix="javis-vpersona-brains-")

import main  # noqa: E402
import voice_brain  # noqa: E402
import voice_live  # noqa: E402
import voice_persona  # noqa: E402

fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        fails.append(name)


# --- the pure builders ---
for label, base in (("voice_live.SYSTEM_PROMPT", voice_live.SYSTEM_PROMPT),
                    ("voice_live.GPT_LIVE_PROMPT", voice_live.GPT_LIVE_PROMPT),
                    ("voice_live.CHATGPT_LIVE_PROMPT", voice_live.CHATGPT_LIVE_PROMPT),
                    ("voice_brain.SYSTEM_PROMPT", voice_brain.SYSTEM_PROMPT)):
    check(f"{label} opens with the clause voice_persona swaps", base.startswith(voice_persona.OPENING))
    out = voice_persona.apply(base, "Người viết", "BLOCK")
    check(f"{label} front-loads partner identity before the generic voice prompt",
          out.startswith("BLOCK\n\nBạn là Người viết, một cộng sự của chủ trong Javis,")
          and voice_persona.OPENING not in out)

block = voice_persona.identity_block("Người viết", "viết bài", "Viết súc tích.", "## Luật chủ dặn\n- không emoji")
check("identity block: name, role, Javis context",
      "**Người viết**" in block and "Vai trò: viết bài." in block and "Javis OS" in block)
check("identity block: never claims to be ChatGPT", "KHÔNG tự nhận là ChatGPT" in block)
check("identity block: explicit English identification",
      'When asked in English "Who are you?"' in block and "I\'m Người viết" in block)
check("identity block: carries the partner file and memory", "Viết súc tích." in block and "không emoji" in block)
check("identity block caps a long file", len(voice_persona.identity_block("A", "", "x" * 20000)) < 6000)
check("custom prompt without the opening gets the block in front",
      voice_persona.apply("Một prompt khác.", "A", "BLOCK") == "BLOCK\n\nMột prompt khác.")


# --- the Live provider and the fast lane take the persona ---
class _Fake(voice_live.LiveProvider):
    name = "gemini"


prov = _Fake("key")
prov.system = voice_persona.apply(prov.system, "Người viết", block)
check("Live provider prompt speaks as the partner, identity first",
      prov.system.startswith(block + "\n\n") and "Bạn là Người viết, một cộng sự của chủ trong Javis," in prov.system
      and voice_persona.OPENING not in prov.system)

conf = {"provider": "openai", "model": "m", "api_key": "k", "system": "PROMPT RIÊNG"}
b = voice_brain._make(conf)
check("fast lane brain takes the partner prompt", b.system == "PROMPT RIÊNG")
check("fast lane builds its messages from that prompt",
      voice_brain.build_messages([], "chào", b.system)[0]["content"] == "PROMPT RIÊNG")
check("fast lane without a partner keeps the Javis prompt",
      voice_brain._make({"provider": "openai", "model": "m", "api_key": "k"}).system == voice_brain.SYSTEM_PROMPT)
check("seed text carries the partner prompt for brains without a system flag",
      "PROMPT RIÊNG" in voice_brain.seed_text([], "chào", with_prompt=True, system="PROMPT RIÊNG"))


# --- main.py: session -> partner ---
ag_dir = main._agents_dir("brain")
ag_dir.mkdir(parents=True, exist_ok=True)
(ag_dir / "nguoi-viet.md").write_text("---\nname: Người viết\nrole: viết bài\n---\nViết súc tích.\n", encoding="utf-8")
store = main.get_store()
sid_agent = store.create_session(brain=main._brain_key("brain"), engine="cli", channel="agent:nguoi-viet")
sid_plain = store.get_or_create(None, brain=main._brain_key("brain"), engine="test", model="test")
sid_gone = store.create_session(brain=main._brain_key("brain"), engine="cli", channel="agent:khong-co")

agent = main._voice_agent(sid_agent, "brain")
check("a call in a partner's chat finds the partner",
      agent is not None and agent["slug"] == "nguoi-viet" and agent["brain"] == main._brain_root("brain"))
check("a plain chat call has no partner", main._voice_agent(sid_plain, "brain") is None)
check("a partner whose file is gone: plain Javis call", main._voice_agent(sid_gone, "brain") is None)
check("no session: plain Javis call", main._voice_agent("", "brain") is None)

persona = main._voice_persona(sid_agent, "brain")
check("persona carries the partner's name and file",
      persona is not None and persona[0] == "Người viết" and "Viết súc tích." in persona[1])
fast = main._voice_brain_conf({"provider": "openai"}, sid_agent, "brain")
check("fast lane conf of a partner chat speaks as the partner",
      fast.get("system", "").startswith(persona[1] + "\n\n")
      and "Bạn là Người viết, một cộng sự của chủ trong Javis," in fast.get("system", "")
      and fast["provider"] == "openai")
check("fast lane conf of a plain chat is unchanged",
      main._voice_brain_conf({"provider": "openai"}, sid_plain, "brain") == {"provider": "openai"})

# The work a call hands off runs as the partner too, with the voice channel line.
p = main._agent_chat_prompt("brain", "nguoi-viet", channel="voice", conv_sid=sid_agent)
check("handed-off work: partner prompt with the call channel", "cuộc gọi thoại" in p and f"web:{sid_agent}" in p)
check("partner chat prompt says who it is inside Javis",
      "cộng sự (trợ lý chuyên trách) trong Javis OS" in p and "KHÔNG tự nhận là" in p)

# --- every call path reads it (code reading: these paths run engines) ---
src = (SERVER / "main.py").read_text(encoding="utf-8")
ask = src[src.index("async def _voice_ask_javis("):src.index("def _live_call_lang(")]
check("_voice_ask_javis runs the turn as the partner", "agent = _voice_agent(conv_sid, brain)" in ask
      and "agent=agent" in ask and '"call_lang": call_lang' in ask)
check("the agent turn of a call gets the voice channel line", 'else "voice" if "call_lang" in (meta or {})' in src)
route = src[src.index("async def voice_live_ws("):]
route = route[:route.index("\n@app.")]
check("Live route builds its provider with the partner persona",
      "_voice_persona(session_id, brain)" in route and "**_persona_kw" in route)
check("fast lane builds its brain with the partner prompt",
      "conf = _voice_brain_conf(conf, conv_sid, brain)" in src[src.index("async def run_voice_turn("):])

if fails:
    raise SystemExit(f"{len(fails)} FAIL: " + ", ".join(fails))
print("all ok")
