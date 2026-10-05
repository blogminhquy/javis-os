"""A mismatched or missing .secret_key must never WIPE the secrets saved in settings.json (0.81.1).

    python tests/run.py khoa_lech_khong_xoa_secret      (no network)

Secrets (API keys, the ChatGPT login, the Telegram token...) are stored encrypted with STATE_DIR/.secret_key. When that key does
not match (volume recreated, key file lost or copied from another machine), read_settings() decrypts them to "". Any
write_settings() of that dict then wrote "" over the encrypted blobs, and putting the right key back no longer helped: every
connection had to be entered again.

Before 0.77.1 nothing wrote settings at startup, so restoring the key was enough. 0.77.1 (admin password from the environment)
rewrites settings once at boot on most Hostinger installs, which turned a transient key problem into permanent loss. A
report after 0.80.0 ("lost the model connections from the previous version") made the risk concrete.

Contract: when writing, a secret whose OLD value is an encrypted blob this machine cannot decrypt is kept as it is if the new
value is empty or missing. With the right key, clearing a secret still clears it.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import json
import os
import sys
import tempfile

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-khoalech-")
os.environ.pop("JAVIS_ADMIN_PASSWORD", None)
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import config as c  # noqa: E402
import secrets_store as ss  # noqa: E402

fails = []


def check(name, cond, them=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(them)[:300] + "]") if them and not cond else ""))
    if not cond:
        fails.append(name)


def raw():
    return json.loads(c.SETTINGS_PATH.read_text(encoding="utf-8"))


def use_key(key: bytes):
    """Swap the machine key, as a recreated volume or a copied state folder would."""
    ss._KEY_PATH.write_bytes(key)
    ss._fernet = None
    c._SETTINGS_CACHE["sig"] = None


from cryptography.fernet import Fernet  # noqa: E402

KEY_A, KEY_B = Fernet.generate_key(), Fernet.generate_key()
use_key(KEY_A)
cfg = c.read_settings()
cfg.setdefault("model", {})
cfg["model"]["openrouter_key"] = "sk-or-REAL"
cfg["model"]["openai_oauth"] = {"access_token": "AT-REAL", "refresh_token": "RT-REAL", "id_token": "ID-REAL"}
cfg.setdefault("telegram", {})["token"] = "123:TG-REAL"
cfg.setdefault("packs", {}).setdefault("tokens", {})["git.example.com"] = "PACK-REAL"
c.write_settings(cfg)
r = raw()
check("(setup) secrets are stored encrypted", r["model"]["openrouter_key"].startswith("enc:")
      and r["telegram"]["token"].startswith("enc:") and r["packs"]["tokens"]["git.example.com"].startswith("enc:"))
before = json.dumps(r, sort_keys=True)

# ---- 1. key mismatch: reading gives "", writing must NOT wipe ----
use_key(KEY_B)
cfg = c.read_settings()
check("with the wrong key the secrets read as empty (the trigger)", cfg["model"]["openrouter_key"] == ""
      and cfg["telegram"]["token"] == "")
cfg.setdefault("ui", {})["theme"] = "dark"       # an ordinary save of some unrelated setting
c.write_settings(cfg)
r = raw()
check("an unrelated save with the wrong key keeps every encrypted secret",
      r["model"]["openrouter_key"] == json.loads(before)["model"]["openrouter_key"]
      and r["model"]["openai_oauth"]["refresh_token"] == json.loads(before)["model"]["openai_oauth"]["refresh_token"]
      and r["telegram"]["token"] == json.loads(before)["telegram"]["token"], r["model"])
check("keys under a wildcard path (packs.tokens.*) are kept too",
      r["packs"]["tokens"]["git.example.com"] == json.loads(before)["packs"]["tokens"]["git.example.com"])
check("the unrelated change itself is saved", r["ui"]["theme"] == "dark")

cfg = c.read_settings()
cfg["model"].pop("openai_oauth", None)           # a code path that dropped the block entirely
c.write_settings(cfg)
check("a secret block dropped while the key is wrong is kept too",
      raw()["model"].get("openai_oauth", {}).get("access_token", "").startswith("enc:"))

# ---- 2. the startup write of 0.77.1 under a wrong key ----
os.environ["JAVIS_ADMIN_PASSWORD"] = "env-pass-123"
c.provision_admin_from_env()
os.environ.pop("JAVIS_ADMIN_PASSWORD", None)
r = raw()
check("the boot-time admin write (0.77.1) with a wrong key keeps the secrets",
      r["model"]["openrouter_key"].startswith("enc:") and r["telegram"]["token"].startswith("enc:"))

# ---- 3. the right key comes back: everything is there ----
use_key(KEY_A)
cfg = c.read_settings()
check("restoring the right key brings every connection back",
      cfg["model"]["openrouter_key"] == "sk-or-REAL" and cfg["model"]["openai_oauth"]["refresh_token"] == "RT-REAL"
      and cfg["telegram"]["token"] == "123:TG-REAL" and cfg["packs"]["tokens"]["git.example.com"] == "PACK-REAL", cfg["model"])

# ---- 4. with the right key, the owner can still clear or change a secret ----
cfg["model"]["openrouter_key"] = ""
cfg["telegram"]["token"] = "456:NEW"
c.write_settings(cfg)
cfg = c.read_settings()
check("with the right key, clearing a secret clears it", cfg["model"]["openrouter_key"] == "")
check("with the right key, changing a secret changes it", cfg["telegram"]["token"] == "456:NEW")

# ---- 5. with a wrong key, a NEW value typed by the owner still wins ----
use_key(KEY_B)
cfg = c.read_settings()
cfg["model"]["groq_api_key"] = "gsk-NEW"
cfg["telegram"]["token"] = "789:RETYPED"
c.write_settings(cfg)
use_key(KEY_B)
cfg = c.read_settings()
check("a key typed again under the new machine key is saved and readable",
      cfg["model"]["groq_api_key"] == "gsk-NEW" and cfg["telegram"]["token"] == "789:RETYPED")

src = (SERVER / "config.py").read_text(encoding="utf-8")
check("no em dash in config.py or this test", chr(0x2014) not in src and chr(0x2014) not in open(__file__, encoding="utf-8").read())

print()
if fails:
    print(f"{len(fails)} FAILED: " + ", ".join(fails))
    sys.exit(1)
print("All khoa_lech_khong_xoa_secret tests passed.")
