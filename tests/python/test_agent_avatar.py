"""Avatar đi cùng file agent, lưu lại qua API và không mất khi client cũ sửa agent."""
from _paths import ROOT, SERVER  # noqa: F401
import os
import tempfile
from pathlib import Path

state = tempfile.mkdtemp(prefix="javis-avatar-test-")
os.environ["JAVIS_STATE_DIR"] = state
os.environ["BRAINS_DIR"] = str(Path(state) / "brains")
os.environ["JAVIS_SESSIONS_DB"] = str(Path(state) / "sessions.db")

import main
import agent_avatar
from fastapi import FastAPI
from fastapi.testclient import TestClient

# Dùng endpoint thật với kho tạm, không khởi động job nền hay engine của app.
app = FastAPI()
app.post("/agents")(main.save_agent)
app.get("/agents")(main.list_agents)
client = TestClient(app)

def save(**kw):
    return client.post("/agents", data={"name": "Người viết", "brain": "brain", **kw})

r = save(avatar_shape="pentagon", avatar_palette="pink")
assert r.status_code == 200 and r.json()["ok"]
slug = r.json()["slug"]
def read():
    return next(x for x in client.get("/agents", params={"brain":"brain"}).json()["agents"] if x["slug"] == slug)
assert read()["avatar"] == {"shape":"pentagon", "palette":"pink"}
assert main._read_md(main._agents_dir("brain") / (slug + ".md"))[0]["avatar"] == read()["avatar"]
assert save(slug=slug, role="Đã đổi vai").status_code == 200
assert read()["avatar"] == {"shape":"pentagon", "palette":"pink"}
assert save(slug=slug, avatar_shape="cloud", avatar_palette="sage").status_code == 200
assert read()["avatar"] == {"shape":"cloud", "palette":"sage"}
assert save(slug=slug, avatar_shape='<svg onload="alert(1)">').status_code == 400
assert read()["avatar"] == {"shape":"cloud", "palette":"sage"}
assert save(name="Ngẫu nhiên", slug="random-avatar").status_code == 200
meta = main._read_md(main._agents_dir("brain") / "random-avatar.md")[0]
assert meta["avatar"]["shape"] in agent_avatar.SHAPES
assert meta["avatar"]["palette"] in agent_avatar.PALETTES
assert agent_avatar.for_agent({}, "old-agent") == agent_avatar.for_agent({}, "old-agent")
assert agent_avatar.for_agent({"avatar":"old-invalid-data"}, "old-agent")
print("OK - avatar API: persistence, legacy updates, random creation and invalid-input rejection")
