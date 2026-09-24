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

# ---- 0.64.39: cài đặt avatar dùng chung bộ chỉnh với linh vật ----
# Tám màu thêm ở 0.59.36 (cam, ruby...) trước đây bị máy chủ trả 400.
assert save(slug=slug, avatar_palette="cam").status_code == 200
assert read()["avatar"]["palette"] == "cam"
# Màu thân tự chọn theo mã, mắt trắng/đen/tự chọn, cỡ mắt thanh trượt.
r = save(slug=slug, avatar_palette="custom", avatar_color="#FA4F05", avatar_eye="custom",
         avatar_eye_color="#2A62B0", avatar_eye_size="1.3")
assert r.status_code == 200, r.text
assert read()["avatar"] == {"shape": "cloud", "palette": "custom", "color": "#fa4f05",
                            "eye": "custom", "eyeColor": "#2a62b0", "eyeSize": 1.3}, read()["avatar"]
# Client cũ sửa trợ lý (không gửi khoá avatar nào) thì giữ nguyên hết.
assert save(slug=slug, role="Lại đổi vai").status_code == 200
assert read()["avatar"]["color"] == "#fa4f05" and read()["avatar"]["eyeSize"] == 1.3
# Về màu có sẵn + mắt đen + cỡ thường thì bỏ các mã thừa, frontmatter gọn lại.
assert save(slug=slug, avatar_palette="jade", avatar_eye="den", avatar_eye_size="1").status_code == 200
assert read()["avatar"] == {"shape": "cloud", "palette": "jade", "eye": "den"}, read()["avatar"]
# Mã màu rác, màu mắt lạ, cỡ mắt ngoài khoảng: từ chối, không ghi gì.
for bad, code in ((dict(avatar_palette="custom", avatar_color='red"><script>'), "avatar_color"),
                  (dict(avatar_palette="custom"), "avatar_color"),
                  (dict(avatar_eye="nau"), "avatar_eye"),
                  (dict(avatar_eye="custom"), "avatar_eye_color"),
                  (dict(avatar_eye_size="9"), "avatar_eye_size"),
                  (dict(avatar_eye_size="nan"), "avatar_eye_size")):
    r = save(slug=slug, **bad)
    assert r.status_code == 400 and r.json()["error"] == code, (bad, r.text)
assert read()["avatar"] == {"shape": "cloud", "palette": "jade", "eye": "den"}
# Trợ lý cũ chưa lưu avatar vẫn lấy màu mặc định trong bộ 12 màu gốc (seed % 12), để thêm
# màu vào thư viện không làm cả danh sách trợ lý cũ đổi màu.
seed = sum(ord(c) for c in "old-agent")
assert agent_avatar.for_agent({}, "old-agent")["palette"] == agent_avatar.PALETTES_MAC_DINH[seed % 12]
# Dữ liệu hỏng trong frontmatter không lọt ra ngoài.
assert agent_avatar.for_agent({"avatar": {"palette": "custom", "color": "xyz", "eye": "custom"}}, "x") == \
    agent_avatar.for_agent({}, "x")
print("OK - avatar API: persistence, legacy updates, random creation and invalid-input rejection")
