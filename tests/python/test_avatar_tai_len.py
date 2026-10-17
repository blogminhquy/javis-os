"""Ảnh đại diện tự tải lên cho trợ lý và nhóm (0.176.0).

    python tests/run.py avatar_tai_len      (KHÔNG mạng)

Chủ repo 16/10/2026: "ngoài avatar mặc định của Javis thêm 1 lựa chọn để tải avatar của họ lên ở trong cả agent và nhóm".
File này canh:
  1. Kho ảnh chỉ nhận ảnh thật (PNG, JPEG, WEBP, GIF theo byte đầu), không nhận SVG hay HTML đội lốt, có trần dung lượng.
  2. Tên ảnh do kho đặt, tên lạ không mở được file nào khác (kể cả ../).
  3. Trợ lý: lưu, giữ qua lần sửa không gửi ảnh, gỡ về hình Javis; hình Javis cũ vẫn còn.
  4. Nhóm: PATCH gắn và gỡ ảnh, ảnh không có trong kho bị từ chối.
  5. Route tải lên và đọc ảnh.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import io
import json
import os
import sys
import tempfile

_state = tempfile.mkdtemp(prefix="javis-avatar-up-")
os.environ["JAVIS_STATE_DIR"] = _state
os.environ["BRAINS_DIR"] = os.path.join(_state, "brains")
os.environ["JAVIS_SESSIONS_DB"] = os.path.join(_state, "sessions.db")
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import avatar_upload  # noqa: E402
import agent_avatar  # noqa: E402

_fails = []


def check(name, cond, them=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(them) + "]") if them and not cond else ""))
    if not cond:
        _fails.append(name)


PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
JPG = b"\xff\xd8\xff\xe0" + b"\x00" * 64
WEBP = b"RIFF\x24\x00\x00\x00WEBPVP8 " + b"\x00" * 64
GIF = b"GIF89a" + b"\x00" * 64

# ---- 1. Nhận diện loại ảnh theo nội dung
check("nhận PNG/JPEG/WEBP/GIF theo byte đầu",
      [avatar_upload.loai_anh(x) for x in (PNG, JPG, WEBP, GIF)] == ["png", "jpg", "webp", "gif"])
check("CANARY: không nhận SVG (có thể chạy script) hay HTML",
      avatar_upload.loai_anh(b"<svg xmlns='http://www.w3.org/2000/svg'><script>alert(1)</script></svg>") == ""
      and avatar_upload.loai_anh(b"<html><script>") == "")
for bad, code in ((b"", "avatar_empty"), (b"<svg/>", "avatar_type"),
                  (b"\x89PNG\r\n\x1a\n" + b"\x00" * (avatar_upload.MAX_BYTES + 1), "avatar_too_big")):
    try:
        avatar_upload.luu(bad)
        check("từ chối " + code, False)
    except ValueError as e:
        check("từ chối " + code, str(e) == code, e)

# ---- 2. Tên do kho đặt
ten = avatar_upload.luu(PNG)
check("lưu trả tên băm 20 ký tự + đuôi theo nội dung", len(ten) == 24 and ten.endswith(".png"), ten)
check("cùng ảnh tải lại là cùng một file", avatar_upload.luu(PNG) == ten)
check("ảnh vừa lưu hợp lệ, file có trên đĩa", avatar_upload.hop_le(ten) and avatar_upload.duong_dan(ten).is_file())
check("tên lạ hay đi lùi thư mục không hợp lệ",
      not any(avatar_upload.hop_le(x) for x in ("../settings.json", "a" * 20 + ".png", ten.upper(), ten + "/..", None, 5)))

# ---- 3. Trợ lý
meta = {"avatar": {"shape": "star", "palette": "jade"}}
a = agent_avatar.for_save(meta, "minh", image=ten)
check("trợ lý: lưu ảnh mà vẫn giữ hình Javis bên dưới", a.get("image") == ten and a["shape"] == "star" and a["palette"] == "jade", a)
check("trợ lý: đọc lại ra ảnh", agent_avatar.for_agent({"avatar": a}, "minh").get("image") == ten)
check("trợ lý: lần sửa không gửi ảnh (None) thì giữ ảnh", agent_avatar.for_save({"avatar": a}, "minh").get("image") == ten)
b = agent_avatar.for_save({"avatar": a}, "minh", image="")
check("trợ lý: gửi rỗng là gỡ ảnh, về đúng hình Javis cũ", "image" not in b and b["shape"] == "star", b)
try:
    agent_avatar.for_save(meta, "minh", image="../../etc/passwd")
    check("trợ lý: tên ảnh lạ bị từ chối", False)
except ValueError as e:
    check("trợ lý: tên ảnh lạ bị từ chối", str(e) == "avatar_image")
check("trợ lý: frontmatter trỏ ảnh đã mất thì về hình Javis, không vẽ ảnh vỡ",
      "image" not in agent_avatar.for_agent({"avatar": {"shape": "star", "image": "0" * 20 + ".png"}}, "minh"))

# ---- 4 + 5. Route thật trên một app tạm (không khởi động job nền hay engine của app)
import main  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

app = FastAPI()
app.post("/avatars/upload")(main.avatar_upload_post)
app.get("/avatars/{name}")(main.avatar_get)
app.post("/agents")(main.save_agent)
app.get("/agents")(main.list_agents)
c = TestClient(app)

r = c.post("/avatars/upload", files={"file": ("x.webp", io.BytesIO(WEBP), "image/webp")})
j = r.json()
check("route tải lên: trả tên ảnh WEBP", r.status_code == 200 and j.get("ok") and j.get("image", "").endswith(".webp"), j)
r2 = c.post("/avatars/upload", files={"file": ("x.png", io.BytesIO(b"<svg onload=alert(1)>"), "image/png")})
check("route tải lên: SVG đội tên .png bị từ chối 400", r2.status_code == 400 and r2.json().get("code") == "avatar_type", r2.text)
g = c.get("/avatars/" + j.get("image", "x"))
check("route đọc ảnh: trả đúng byte, cache lâu, nosniff",
      g.status_code == 200 and g.content == WEBP and "immutable" in g.headers.get("cache-control", "")
      and g.headers.get("x-content-type-options") == "nosniff", g.headers)
check("route đọc ảnh: tên lạ 404", c.get("/avatars/" + "f" * 20 + ".png").status_code == 404
      and c.get("/avatars/settings.json").status_code == 404)

s1 = c.post("/agents", data={"name": "Người viết", "brain": "brain", "avatar_shape": "star", "avatar_palette": "jade",
                             "avatar_image": j["image"]})
slug = s1.json().get("slug")


def doc():
    return next(x for x in c.get("/agents", params={"brain": "brain"}).json()["agents"] if x["slug"] == slug)


check("POST /agents: lưu ảnh, danh sách trả ảnh kèm hình Javis", doc()["avatar"].get("image") == j["image"]
      and doc()["avatar"]["shape"] == "star", doc())
c.post("/agents", data={"name": "Người viết", "brain": "brain", "slug": slug, "role": "Đổi vai"})
check("POST /agents: client cũ không gửi avatar_image thì ảnh còn nguyên", doc()["avatar"].get("image") == j["image"])
c.post("/agents", data={"name": "Người viết", "brain": "brain", "slug": slug, "avatar_image": "none"})
check("POST /agents: gửi none thì về hình Javis", "image" not in doc()["avatar"] and doc()["avatar"]["shape"] == "star", doc())
check("POST /agents: tên ảnh lạ 400",
      c.post("/agents", data={"name": "Người viết", "brain": "brain", "slug": slug, "avatar_image": "x.png"}).status_code == 400)

import team_store  # noqa: E402
ts = team_store.TeamStore()
t = ts.create_team("brain", "Ra mắt", "", "sess-1")
tid = t["team_id"] if isinstance(t, dict) else t
check("nhóm mới: chưa có ảnh riêng", (ts.get(tid) or {}).get("avatar_image") == "")
check("nhóm: gắn ảnh", ts.update(tid, avatar_image=ten).get("avatar_image") == ten)
check("nhóm: gỡ ảnh", ts.update(tid, avatar_image="").get("avatar_image") == "")

src = open(os.path.join(ROOT, "server", "team_api.py"), encoding="utf-8").read()
check("PATCH /teams: chỉ nhận ảnh có trong kho (hop_le), rỗng là gỡ",
      "avatar_upload.hop_le(img)" in src
      and '("name", "description", "status", "avatar_image", "tags") if k in body' in src)   # 0.195.0 adds tags
check("no em dash", chr(0x2014) not in open(__file__, encoding="utf-8").read())

print()
if _fails:
    print(f"{len(_fails)} FAIL: " + ", ".join(_fails))
    sys.exit(1)
print("ALL PASS")
