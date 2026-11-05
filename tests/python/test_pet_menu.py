"""The owner adds features to the mascot menu and reorders them (Settings > Mascot > Mascot menu).

    python tests/run.py pet_menu -v

Owner, 2026-11-05: "Chỉ cần thêm và sắp xếp vị trí thôi là ok rồi." A save may add and reorder, never drop an item
already saved; a save from an older revision is a conflict; a damaged saved value is never written over.
Runs the real host on a temporary state folder; no model call.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import json
import os
import re
import tempfile

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-petmenu-")

import main  # noqa: E402
import pet_menu  # noqa: E402
from starlette.testclient import TestClient  # noqa: E402

fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(extra)[:300] + "]") if extra and not cond else ""))
    if not cond:
        fails.append(name)


main.cfgmod.gate_active = lambda: False
client = TestClient(main.app, base_url="http://127.0.0.1")
D = list(pet_menu.DEFAULT_ITEMS)


def get():
    return client.get("/pet/menu").json()["menu"]


def post(items, rev):
    return client.post("/pet/menu", data={"items": json.dumps(items), "base_rev": str(rev)})


# ═════ never customised ═════
m = get()
check("a Javis that never saved a menu shows the default six", m["state"] == "default" and m["items"] == D and m["rev"] == 0, m)
check("the default is the menu the pet always had, in that order", D == ["chat", "agent", "workflow", "mic", "pet", "teams"])

# ═════ add + reorder ═════
want = ["teams", "chat", "agent", "workflow", "mic", "pet", "tasks"]
r = post(want, 0)
check("adding a feature and reordering saves", r.status_code == 200 and r.json()["ok"], r.text)
m = get()
check("the saved order comes back exactly", m["state"] == "custom" and m["items"] == want, m)
check("each save moves the revision on", m["rev"] == 1, m)
raw = main.cfgmod.read_settings()[pet_menu.SETTINGS_KEY]
check("stored as {schemaVersion, rev, items:[{actionId}]}",
      raw.get("schemaVersion") == 1 and raw["items"][0] == {"actionId": "teams"}, raw)
check("the menu lives apart from dashboard.pet (the pet's look)",
      "menu" not in ((main.cfgmod.read_settings().get("dashboard") or {}).get("pet") or {}))

# ═════ what a save may not do ═════
r = post(want + ["tasks"], 1)
check("the same feature cannot be added twice", r.status_code == 400 and r.json()["code"] == "bad", r.text)
r = post(want + ["javascript:alert(1)"], 1)
check("an id the app does not know cannot be added", r.status_code == 400 and r.json()["code"] == "bad", r.text)
r = post(want + ["made-up"], 1)
check("not even one shaped like a real id", r.status_code == 400, r.text)
r = client.post("/pet/menu", data={"items": "{nope", "base_rev": "1"})
check("a body that is not a JSON list is refused", r.status_code == 400 and not r.json()["ok"], r.text)
check("none of those refusals touched the saved menu", get()["items"] == want and get()["rev"] == 1)

# ═════ two windows ═════
r = post(want + ["files"], 0)
check("a save edited from an older revision is a conflict (409)", r.status_code == 409 and r.json()["code"] == "conflict", r.text)
check("the conflict answer carries the newer menu to reload", r.json()["menu"]["items"] == want, r.text)
check("the conflict did not overwrite anything", get()["items"] == want)

# ═════ remove anything, down to nothing ═════
# Owner, 2026-11-05: "tắt luôn cả các chức năng mặc định ... tất cả đều là nút X, có thể tắt hết sạch được luôn".
r = post([x for x in want if x != "mic"], 1)
check("a DEFAULT item can be removed", r.status_code == 200 and "mic" not in get()["items"], r.text)
r = post(["tasks", "chat"], 2)
check("so can an added one, several at once", r.status_code == 200 and get()["items"] == ["tasks", "chat"], r.text)
r = post([], 3)
check("the menu can be emptied completely", r.status_code == 200 and get()["items"] == [] and get()["state"] == "custom", r.text)
check("an empty menu stays custom, it does not fall back to the default six", get()["items"] == [])
r = post(["mic", "chat"], 4)
check("a removed default comes back like any feature", r.status_code == 200 and get()["items"] == ["mic", "chat"], r.text)

# ═════ menus saved with "hidden" flags (0.479.0 to 0.481.x) ═════
cfg = main.cfgmod.read_settings()
cfg[pet_menu.SETTINGS_KEY]["items"] = [{"actionId": "chat"}, {"actionId": "mic", "hidden": True}, {"actionId": "pet"}]
main.cfgmod.write_settings(cfg)
m = get()
check("an item an older save hid now reads as removed (the pet never showed it)", m["items"] == ["chat", "pet"] and m["hidden"] == [], m)
r = client.post("/pet/menu", data={"items": json.dumps(["chat", "pet", "files"]), "base_rev": str(m["rev"]), "hidden": json.dumps(["files"])})
check("an older dashboard sending `hidden` gets those left out", r.status_code == 200 and get()["items"] == ["chat", "pet"], r.text)
cfg = main.cfgmod.read_settings()
cfg[pet_menu.SETTINGS_KEY]["items"][0]["hidden"] = "yes"
main.cfgmod.write_settings(cfg)
check("a hidden flag that is not true/false still marks the stored menu damaged", get()["state"] == "invalid")
cfg[pet_menu.SETTINGS_KEY]["items"][0].pop("hidden")
main.cfgmod.write_settings(cfg)
check("and fixing it brings the menu back", get()["state"] == "custom")

# ═════ an id a later Javis removed ═════
cfg = main.cfgmod.read_settings()
cfg[pet_menu.SETTINGS_KEY]["items"].insert(1, {"actionId": "old-feature"})
main.cfgmod.write_settings(cfg)
m = get()
check("an id this Javis no longer knows is kept, not lost", "old-feature" in m["items"] and m["state"] == "custom", m)
r = post(m["items"] + ["models"], m["rev"])
check("and a later save may keep it in place", r.status_code == 200 and get()["items"][1] == "old-feature", r.text)
r = post([x for x in get()["items"] if x != "old-feature"], get()["rev"])
check("or remove it", r.status_code == 200 and "old-feature" not in get()["items"], r.text)

# ═════ damaged settings ═════
for bad, why in (({"schemaVersion": 99, "rev": 4, "items": []}, "newer schema"),
                 ({"schemaVersion": 1, "rev": 4, "items": "chat"}, "items not a list"),
                 ({"schemaVersion": 1, "rev": 4, "items": [{"actionId": "chat"}, {"actionId": "chat"}]}, "duplicate"),
                 ("garbage", "not an object")):
    cfg = main.cfgmod.read_settings()
    cfg[pet_menu.SETTINGS_KEY] = bad
    main.cfgmod.write_settings(cfg)
    m = get()
    check("damaged (" + why + "): the menu falls back to the default meanwhile", m["state"] == "invalid" and m["items"] == D, m)
    r = post(D + ["files"], m["rev"])
    check("damaged (" + why + "): no save goes over it", r.status_code == 409 and r.json()["code"] == "invalid_saved", r.text)
    check("damaged (" + why + "): the stored value is left as it was", main.cfgmod.read_settings()[pet_menu.SETTINGS_KEY] == bad)

# ═════ first save over the default ═════
cfg = main.cfgmod.read_settings()
cfg.pop(pet_menu.SETTINGS_KEY, None)
main.cfgmod.write_settings(cfg)
r = post(["chat", "agent", "workflow", "mic", "pet"], 0)
check("the first save may already drop a default item", r.status_code == 200 and "teams" not in get()["items"], r.text)

# ═════ the catalog in the dashboard is the same list ═════
src = (ROOT / "dashboard" / "pet-menu.js").read_text(encoding="utf-8")
ids = re.findall(r'\{ id: "([a-z]+)", label: ', src[src.index("var CATALOG = ["):src.index("];", src.index("var CATALOG = ["))])
check("pet-menu.js CATALOG lists exactly pet_menu.KNOWN_ACTIONS", ids == list(pet_menu.KNOWN_ACTIONS), (ids, pet_menu.KNOWN_ACTIONS))
check("and the same default six", re.search(r'var DEFAULT_ITEMS = \["chat", "agent", "workflow", "mic", "pet", "teams"\];', src) is not None)
for page in pet_menu.KNOWN_ACTIONS:
    if page in ("agent", "workflow", "mic", "pet", "chat", "teams"):
        continue
    check("page " + page + " is a real page id of the app", ('"' + page + '"') in (ROOT / "server" / "ui_targets.py").read_text(encoding="utf-8"))

print("\nĐỎ: %d" % len(fails) if fails else "\nXANH")
raise SystemExit(1 if fails else 0)
