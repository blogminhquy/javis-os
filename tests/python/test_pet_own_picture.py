"""Mascot own picture (2026-11-07): upload a picture for the pet and use it as the browser tab icon.

Owner: "thêm chức năng có thể upload hình riêng của pet, và hình đó sẽ có thể đổi được favicon luôn để người ta phân
biệt khi có nhiều javis". Runs the real save path and the real icon routes:
  - dashboard.pet.image keeps only a name the /avatars store holds; "" removes it; junk and paths never land.
  - /pet-icon, /favicon.ico and the served page carry the picture while `favicon` is on, the logo once it is off.
  - /pet-icon is public: the login screen shows the tab icon before any session.
"""
from _paths import ROOT, SERVER  # noqa: F401
import json
import os
import tempfile
from pathlib import Path

state = tempfile.mkdtemp(prefix="javis-pet-picture-")
os.environ["JAVIS_STATE_DIR"] = state
os.environ["BRAINS_DIR"] = str(Path(state) / "brains")
os.environ["JAVIS_SESSIONS_DB"] = str(Path(state) / "sessions.db")

import main  # noqa: E402
import avatar_upload  # noqa: E402
import config as cfgmod  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

app = FastAPI()
app.post("/settings")(main.settings_set)
app.get("/pet-icon")(main.pet_icon)
app.get("/favicon.ico")(main.favicon_ico)
app.get("/")(main.root)
client = TestClient(app)

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
name = avatar_upload.luu(PNG)


def save(pet):
    r = client.post("/settings", data={"section": "dashboard", "data": json.dumps({"pet": pet})})
    assert r.status_code == 200, r.text
    return cfgmod.read_settings()["dashboard"]["pet"]


# No picture yet: the tab keeps the logo.
assert main._pet_icon_file() is None
assert "/pet-icon" not in client.get("/").text

# A stored picture is kept, and the tab icon follows it (on by default).
pet = save({"image": name, "favicon": True})
assert pet["image"] == name and pet["favicon"] is True, pet
r = client.get("/pet-icon")
assert r.status_code == 200 and r.content == PNG, r.status_code
assert client.get("/favicon.ico").content == PNG
page = client.get("/").text
stem = name.split(".")[0]
assert '<link rel="icon" href="/pet-icon?v=' + stem + '">' in page, "page icon link"
assert '<link rel="apple-touch-icon" href="/pet-icon?v=' + stem + '">' in page, "apple icon link"

# Junk never lands: a path, a name the store does not hold, a non-string. The good name stays.
for junk in ("../settings.json", "0123456789abcdef0123.png", 'x"><script>', 42):
    pet = save({"image": junk})
    assert pet["image"] == name, (junk, pet)

# Switch off: the picture stays on the pet but the tab goes back to the logo.
pet = save({"favicon": False})
assert pet["image"] == name and pet["favicon"] is False, pet
assert main._pet_icon_file() is None
assert client.get("/pet-icon").content != PNG
assert "/pet-icon" not in client.get("/").text

# Remove the picture.
pet = save({"image": "", "favicon": True})
assert pet["image"] == "" and main._pet_icon_file() is None, pet

# Public like /brand-logo, so the login screen gets the icon too.
assert "/pet-icon" in main._AUTH_PUBLIC_EXACT
print("OK - pet own picture: stored by name only, junk rejected, tab icon follows the switch, public route")
