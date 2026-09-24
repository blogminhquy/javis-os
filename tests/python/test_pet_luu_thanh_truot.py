"""Linh vật 0.64.39: máy chủ phải GIỮ được giá trị thanh trượt và mã màu tự chọn.

Nhánh lưu `dashboard.pet` lọc từng khoá (server/main.py). Một giá trị không qua được bộ lọc
bị bỏ TRONG IM LẶNG: request vẫn 200, màn hình vẫn đúng nhờ localStorage, F5 xong mới mất.
Đúng lỗi cỡ "Rất lớn" từng dính. Thanh trượt đổi cỡ từ CHUỖI ("vua") sang SỐ (96), nên phải
có test chạy thật cả đường lưu lẫn đường đọc lại.
"""
from _paths import ROOT, SERVER  # noqa: F401
import json
import os
import tempfile
from pathlib import Path

state = tempfile.mkdtemp(prefix="javis-pet-test-")
os.environ["JAVIS_STATE_DIR"] = state
os.environ["BRAINS_DIR"] = str(Path(state) / "brains")
os.environ["JAVIS_SESSIONS_DB"] = str(Path(state) / "sessions.db")

import main
import config as cfgmod
from fastapi import FastAPI
from fastapi.testclient import TestClient

app = FastAPI()
app.post("/settings")(main.settings_set)
client = TestClient(app)


def luu(pet):
    r = client.post("/settings", data={"section": "dashboard", "data": json.dumps({"pet": pet})})
    assert r.status_code == 200, r.text
    return cfgmod.read_settings()["dashboard"]["pet"]


pet = luu({"shape": "star", "palette": "custom", "color": "#FA4F05", "size": 96, "eye": "custom",
           "eyeColor": "#2A62B0", "eyeSize": 1.3, "side": "left", "pos": 0.4, "enabled": True})
assert pet["size"] == 96 and pet["eyeSize"] == 1.3, pet
assert pet["palette"] == "custom" and pet["color"] == "#fa4f05", pet
assert pet["eye"] == "custom" and pet["eyeColor"] == "#2a62b0", pet

# Kẹp đúng khoảng của pet.js (44-150px, hệ số 0.8-1.5).
pet = luu({"size": 999, "eyeSize": 9})
assert pet["size"] == 150 and pet["eyeSize"] == 1.5, pet
pet = luu({"size": 1, "eyeSize": 0.01})
assert pet["size"] == 44 and pet["eyeSize"] == 0.8, pet

# Client cũ vẫn gửi tên nấc: vẫn được nhận như trước.
pet = luu({"size": "rat_lon", "eyeSize": "to"})
assert pet["size"] == "rat_lon" and pet["eyeSize"] == "to", pet

# Rác không lọt: mã màu sai, bool giả làm số, chuỗi chứa ký tự lạ.
pet = luu({"color": 'red"><script>', "eyeColor": "#12345", "size": True, "palette": "<b>"})
assert pet["color"] == "#fa4f05" and pet["eyeColor"] == "#2a62b0", pet
assert pet["size"] == "rat_lon" and pet["palette"] == "custom", pet
print("OK - pet settings: slider numbers, custom colors, clamping, legacy keys, junk rejection")
