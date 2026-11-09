# -*- coding: utf-8 -*-
"""Investment compass monthly drafts: store, validation, approval, plugin tools and routes.

    python tests/run.py compass_store

No network. Uses a temporary JAVIS_STATE_DIR, so the real outlook is never touched.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import copy
import importlib.util
import json
import os
import sys
import tempfile

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-compass-"))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import compass_store as cs  # noqa: E402

_fails = []


def check(name, cond, detail=""):
    print(("ok   " if cond else "FAIL ") + name + (f"  ({detail})" if detail and not cond else ""))
    if not cond:
        _fails.append(name)


# bundled data
data, source, at = cs.current()
check("starts from the bundled outlook", source == "bundled" and at == 0.0 and len(data["assets"]) == 7)
check("the bundled outlook passes its own validation", cs.validate(data, data) == [], "; ".join(cs.validate(data, data)))
check("asset ids are the seven the page colours", sorted(a["id"] for a in data["assets"]) == sorted(cs.ASSET_IDS))

# validation catches what would break the page
bad = copy.deepcopy(data)
bad["assets"][0]["stance"] = "buy"
check("an unknown stance is refused", any("stance" in e for e in cs.validate(bad, data)))
bad = copy.deepcopy(data)
bad["assets"][0]["score"] = 3
check("a score outside -2..2 is refused", any("score" in e for e in cs.validate(bad, data)))
bad = copy.deepcopy(data)
bad["assets"].pop()
check("a missing asset is refused", any("assets must be" in e for e in cs.validate(bad, data)))
bad = copy.deepcopy(data)
bad["factors"][0]["impact"]["bonds"] = 1
check("a factor naming an unknown asset is refused", any("impact" in e for e in cs.validate(bad, data)))
bad = copy.deepcopy(data)
bad["profiles"][0]["now"]["savings"] += 5
check("profile weights not adding to 100 are refused", any("add to 100" in e for e in cs.validate(bad, data)))
bad = copy.deepcopy(data)
bad["verdict"] = "plain text"
check("a top-level field changing type is refused", any("verdict" in e for e in cs.validate(bad, data)))
bad = copy.deepcopy(data)
bad["summary"] = {"vi": "a — b", "en": "a - b"}
check("long dashes are refused", any("dash" in e for e in cs.validate(bad, data)))
bad = copy.deepcopy(data)
bad["assets"][1]["enter_when"][0]["live"] = {"ref": "vn:idx:VNINDEX:trend", "op": "~", "value": "up"}
check("a live check with an unknown operator is refused", any("live check" in e for e in cs.validate(bad, data)))

# draft flow
r = cs.set_fields({"assets": [{"id": "gold", "stance": "accumulate", "score": 1}]}, note="Fed paused", updated="2026-12-08", as_of="12/2026")
check("a partial asset change makes a draft", r["ok"] and "asset:gold" in r["draft"]["changed"], str(r))
d = cs.draft()["data"]
gold = next(a for a in d["assets"] if a["id"] == "gold")
check("the change merges into the asset and keeps the rest", gold["stance"] == "accumulate" and gold["score"] == 1 and gold["thesis"])
check("updated and as_of are set", d["updated"] == "2026-12-08" and d["as_of"] == "12/2026")
check("the live page still shows the old outlook", cs.current()[0]["as_of"] == data["as_of"])
r = cs.set_fields({"verdict": {"vi": "Mới", "en": "New"}}, note="verdict")
check("a second change adds to the same draft", r["ok"] and {"asset:gold", "verdict"} <= set(r["draft"]["changed"]))
check("notes from both changes are kept", "Fed paused" in cs.draft()["note"] and "verdict" in cs.draft()["note"])
r = cs.set_fields({"assets": [{"id": "bonds", "stance": "hold"}]})
check("an unknown asset id is refused", not r["ok"] and "unknown asset" in r["errors"][0])
r = cs.set_fields({"assets": [{"id": "crypto", "score": 9}]})
check("a breaking change is refused and the draft kept", not r["ok"] and cs.draft() is not None
      and next(a for a in cs.draft()["data"]["assets"] if a["id"] == "crypto")["score"] == next(a for a in data["assets"] if a["id"] == "crypto")["score"])
check("empty fields are refused", not cs.set_fields({})["ok"] and not cs.set_fields("not json")["ok"])

ok = cs.approve()
cur, source, at = cs.current()
check("approve publishes the draft", ok["ok"] and source == "updated" and cur["as_of"] == "12/2026" and cur["verdict"]["vi"] == "Mới")
check("approve keeps the previous version", any(h.startswith("data-") for h in cs.history()))
check("no draft left after approval", cs.draft() is None and not cs.approve()["ok"])
cs.set_fields({"as_of": "01/2027"})
cs.discard()
check("discard drops the draft", cs.draft() is None and cs.current()[0]["as_of"] == "12/2026")
sm = cs.summary(cur)
check("summary text names the stances and sources", "gold" in sm and "accumulate" in sm and "Nguồn" in sm)

# plugin
spec = importlib.util.spec_from_file_location("javis_compass_plugin", os.path.join(ROOT, "system", "plugins", "javis-compass", "plugin.py"))
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
tools = {}


class Ctx:
    def register_tool(self, **kw):
        tools[kw["name"]] = kw


mod.register(Ctx())
check("read tool is readonly, draft tool is safe, no approve tool",
      tools["javis_compass"]["min_mode"] == "readonly" and tools["javis_compass_draft"]["min_mode"] == "safe" and len(tools) == 2)
check("tool descriptions carry no long dashes", not any(ch in t["description"] for t in tools.values() for ch in "–—"))


async def plug():
    t = await tools["javis_compass"]["handler"]({"op": "part", "part": "assets", "asset": "gold"}, {})
    check("one asset read in full", json.loads(t)["id"] == "gold", t[:100])
    t = await tools["javis_compass"]["handler"]({"op": "part", "part": "nope"}, {})
    check("an unknown part says which exist", t.startswith("ERROR") and "assets" in t)
    t = await tools["javis_compass_draft"]["handler"]({"op": "set", "fields": {"assets": [{"id": "usd", "score": -1}]}, "note": "n"}, {})
    check("draft tool writes a draft and says it is not published", "CHƯA" in t and cs.draft() is not None, t)
    t = await tools["javis_compass_draft"]["handler"]({"op": "set", "fields": {"profiles": 5}}, {})
    check("draft tool reports a breaking change", t.startswith("ERROR"))
    t = await tools["javis_compass_draft"]["handler"]({"op": "set", "fields": "{bad"}, {})
    check("draft tool reports bad JSON", t.startswith("ERROR"))
    t = await tools["javis_compass"]["handler"]({"op": "summary"}, {})
    check("summary mentions the waiting draft", "bản nháp" in t)
    t = await tools["javis_compass_draft"]["handler"]({"op": "discard"}, {})
    check("draft tool can discard", cs.draft() is None)

asyncio.run(plug())

# routes
import main  # noqa: E402
from _paths import moi_duong_dan  # noqa: E402
paths = set(moi_duong_dan(main.app))
for p in ("/compass/data", "/compass/approve", "/compass/discard"):
    check("route " + p, p in paths)

if _fails:
    print(f"\n{len(_fails)} FAIL")
    sys.exit(1)
print("\nall ok")
