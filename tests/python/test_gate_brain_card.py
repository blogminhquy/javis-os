"""The Javis Gate card's brain selector, server side (#1726, owner 2026-11-24).

    python tests/run.py gate_brain_card -v      (no network)

GET /gate/brains feeds the card on the Connections page; POST /gate/default-brain saves the owner's choice into
settings.json (`gate_default_brain`, a brain folder; "" = "Brain used last"). Locks the round trip, the refusal of a
brain that is not on the machine, and that the card only shows while the Javis Gate package is installed.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import os
import sys
import tempfile
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="gate-brain-card-"))
for name in ("Brain Default", "Cá Nhân"):
    (_TMP / "brains" / name).mkdir(parents=True, exist_ok=True)
os.environ["JAVIS_STATE_DIR"] = str(_TMP / "state")
os.environ["BRAINS_DIR"] = str(_TMP / "brains")
(_TMP / "state").mkdir(parents=True, exist_ok=True)

from fastapi.testclient import TestClient  # noqa: E402

import main  # noqa: E402
import gate_brain  # noqa: E402
import packs  # noqa: E402
import plugins_host  # noqa: E402

main.cfgmod.gate_active = lambda: False
fails = []


def check(name, cond, info=None):
    print(("ok   " if cond else "FAIL ") + name + ("" if cond or info is None else f"  ({info!r})"))
    if not cond:
        fails.append(name)


c = TestClient(main.app, base_url="http://127.0.0.1:8080")

d = c.get("/gate/brains").json()
check("the card state lists every brain with its folder and name",
      [b["folder"] for b in d.get("brains") or []] == ["Brain Default", "Cá Nhân"], d)
check("nothing picked yet: 'Brain used last' (empty default)", d.get("default") == "" and not d.get("default_missing"))
check("no Javis Gate package: the card stays hidden", d.get("installed") is False)

r = c.post("/gate/default-brain", json={"brain": "Cá Nhân"})
check("saving a brain answers ok", r.status_code == 200 and r.json().get("ok"), r.text)
check("it lands in settings.json", main.cfgmod.read_settings().get(gate_brain.SETTINGS_KEY) == "Cá Nhân")
check("and the card reads it back", c.get("/gate/brains").json().get("default") == "Cá Nhân")
check("the Gate now uses it", (gate_brain.default_brain() or {}).get("folder") == "Cá Nhân")

r = c.post("/gate/default-brain", json={"brain": "../state"})
check("a brain that is not on the machine is refused", r.status_code == 400 and not r.json().get("ok"), r.text)
check("and the saved choice is untouched", main.cfgmod.read_settings().get(gate_brain.SETTINGS_KEY) == "Cá Nhân")
r = c.post("/gate/default-brain", json={"brain": 5})
check("a value that is not text is refused", r.status_code == 400)

r = c.post("/gate/default-brain", json={"brain": ""})
check("an empty choice goes back to 'Brain used last'",
      r.json().get("ok") and main.cfgmod.read_settings().get(gate_brain.SETTINGS_KEY) == "" and
      gate_brain.default_brain() is None)

main.cfgmod.update_settings({gate_brain.SETTINGS_KEY: "Gone"})
d = c.get("/gate/brains").json()
check("a saved brain that was deleted is reported, so the card can say so",
      d.get("default") == "Gone" and d.get("default_missing") is True, d)
check("and the Gate falls back to the brain used last", gate_brain.default_brain() is None)

# The Javis Gate package installed: the card shows, with the package's page.
fake = _TMP / "packs" / "javis.gate" / "plugins" / "javis-gate"
fake.mkdir(parents=True)
packs.plugin_dirs = lambda: [("javis.gate", fake)]
plugins_host.describe = lambda *a, **k: [{"slug": "javis-gate", "page": "/ext/javis-gate/"}]
d = c.get("/gate/brains").json()
check("with the Javis Gate package the card shows", d.get("installed") is True, d)
check("with a link to the package's page", d.get("page") == "/ext/javis-gate/", d)

print(("FAILED: " + str(len(fails))) if fails else "all ok")
sys.exit(1 if fails else 0)
