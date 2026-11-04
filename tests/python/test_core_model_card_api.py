"""The model row on the Javis Core card (0.461.0; owner 04/11/2026: Javis Core showed no model, so it looked like it had
none; agreed design: name the main model it follows, let the card pin it, one pin shared with the Core chat model bar).

    python tests/run.py core_model_card_api

No network, no model.
- GET /javis-core/model: no pin = follows the main model and says which; `run_*` is what the next Core turn runs on.
- POST /javis-core/model pins Javis Core as a whole (same `core_provider/core_model` as the Core chat model bar), and
  an empty provider removes the pin. Unknown provider = 400.
- The card and the Core chat model bar read and write the same pin, both ways.
- A pin that cannot run (no key) says so and shows the main model as what runs.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import os
import sys
import tempfile
from pathlib import Path

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-core-card-")
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (f"  [{str(extra)[:300]}]" if extra and not cond else ""))
    if not cond:
        fails.append(name)


import config as cfgmod  # noqa: E402
import javis_core  # noqa: E402
import main  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

if os.environ["JAVIS_STATE_DIR"] not in str(cfgmod.STATE_DIR):
    print(f"FAIL state dir is not the temp dir: {cfgmod.STATE_DIR}. STOP.")
    sys.exit(1)

cfgmod.update_settings({"model": {"main": {"provider": "anthropic-cli", "model": "opus"}, "groq_api_key": "gsk_test",
                                  "core_provider": "", "core_model": ""}})


def mcfg():
    return cfgmod.read_settings().get("model", {})


client = TestClient(main.app, base_url="http://127.0.0.1:8080")
store = main.get_store()
core = store.create_session(brain="brain", channel=javis_core.CHANNEL)

v = client.get("/javis-core/model").json()
check("no pin: the card follows the main model and names it",
      v.get("pinned") is False and v.get("main_provider") == "anthropic-cli" and v.get("main_model") == "opus", v)
check("no pin: what runs is the main model", (v.get("run_provider"), v.get("run_model")) == ("anthropic-cli", "opus"), v)

r = client.post("/javis-core/model", data={"provider": "groq", "model": "qwen3-32b"})
d = r.json()
check("pinning from the card answers with the new view", r.status_code == 200 and d.get("ok") and d.get("pinned") is True and
      d.get("pinned_provider") == "groq" and d.get("pinned_model") == "qwen3-32b" and d.get("pin_ok") is True, d)
check("...writes the one Core pin", mcfg().get("core_provider") == "groq" and mcfg().get("core_model") == "qwen3-32b", mcfg())
prov, _, _, model = main._chat_provider_for_session(mcfg(), store.get_session(core))
check("...and a Core chat runs on it", (prov, model) == ("groq", "qwen3-32b"), (prov, model))
meta = client.get(f"/sessions/{core}/meta").json()
check("...and the Core chat model bar shows it", meta.get("pinned_provider") == "groq" and meta.get("pin_ok") is True, meta)
check("the main model is left alone", (mcfg().get("main") or {}).get("provider") == "anthropic-cli", mcfg().get("main"))

client.post(f"/sessions/{core}/model", data={"provider": "anthropic-cli", "model": "sonnet"})
v = client.get("/javis-core/model").json()
check("a pin set from the Core chat shows on the card",
      v.get("pinned_provider") == "anthropic-cli" and v.get("pinned_model") == "sonnet" and v.get("run_model") == "sonnet", v)

r = client.post("/javis-core/model", data={"provider": "", "model": "whatever"})
d = r.json()
check("empty provider: follow the main model again", d.get("ok") and d.get("pinned") is False and
      not mcfg().get("core_provider") and not mcfg().get("core_model"), (d, mcfg()))
check("...and the Core chat model bar follows too", not client.get(f"/sessions/{core}/meta").json().get("pinned_provider"))

r = client.post("/javis-core/model", data={"provider": "no-such-brain", "model": "x"})
check("an unknown provider is refused and nothing changes", r.status_code == 400 and not mcfg().get("core_provider"), r.text)

cfgmod.update_settings({"model": {"core_provider": "openrouter", "core_model": "x/y"}})
v = client.get("/javis-core/model").json()
check("a pin with no key says it cannot run and shows the main model running",
      v.get("pinned") is True and v.get("pin_ok") is False and v.get("run_provider") == "anthropic-cli", v)
cfgmod.update_settings({"model": {"core_provider": "", "core_model": ""}})

src = (SERVER / "main.py").read_text(encoding="utf-8")
check("one writer of the Core pin", src.count('{"model": {"core_provider": prov, "core_model": mdl}}') == 1 and
      src.count("await _set_core_pin(") == 2)

dashes = [chr(0x2014), chr(0x2013)]
for f in (Path(__file__), ROOT / "dashboard" / "core-model.js"):
    check(f"no em or en dash in {f.name}", not any(d in f.read_text(encoding="utf-8") for d in dashes))

print()
if fails:
    raise SystemExit(f"FAIL {len(fails)}: " + "; ".join(fails[:6]))
print("ALL PASS")
