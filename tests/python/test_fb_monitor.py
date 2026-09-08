"""Test connector + plugin Theo dõi Facebook (Apify). Chạy tay / CI:

    python tests/run.py fb_monitor

KHÔNG mạng (giả _token + _run). Phủ: catalog connector hợp lệ (apikey, field apify_token,
readonly), plugin nạp 1 tool readonly, gate chưa-có-token, tách URL Trang vs Nhóm, bóc số share
(nhiều tên trường), chuẩn hoá bài, và fb_monitor routing đúng actor + lọc min_shares + sắp theo
share giảm dần + gộp lỗi.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401  - nạp server/ vào sys.path (xem tests/python/_paths.py)
import asyncio
import importlib.util
import json
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-fbmon-"))

_fails = []
def check(n, c):
    print(("ok  " if c else "FAIL ") + n)
    if not c: _fails.append(n)


# ---- 1. Connector: đã dọn sang kho ----
# Khuôn connector `facebook-monitor` rời `system/mcp-catalog.json` ở 0.55.36 và giờ sống trong gói
# `javis.facebook-monitor` của repo kho (blogminhquy/javis-store). Những assert về HÌNH DẠNG của nó
# (provider, scope, fields, default_perm, phân loại tool, chữ cảnh báo) đi theo dữ liệu sang đó:
# `tools/kiem-tra.py` của repo kho chạy đúng các phép kiểm ấy trên mọi Pull Request.
#
# Giữ lại ở đây là giả vờ: dữ liệu đổi được trong kho mà KHÔNG cần bản Javis mới, nên một test
# ở repo này chỉ canh được bản chụp lúc dọn nhà chứ không canh được thứ người dùng thật sự cài.
# Phần bên dưới - plugin đi kèm - vẫn là mã của app nên vẫn kiểm ở đây.


# ---- 2. Plugin nạp ----
spec = importlib.util.spec_from_file_location(
    "fb_monitor_test", str(ROOT / "system" / "plugins" / "fb-monitor-apify" / "plugin.py"))
plug = importlib.util.module_from_spec(spec)
spec.loader.exec_module(plug)


class _Ctx:
    def __init__(self): self.tools = []
    def register_tool(self, name, description, handler, schema=None, min_mode="readonly", check_fn=None, **k):
        self.tools.append({"name": name, "min_mode": min_mode})


ctx = _Ctx()
plug.register(ctx)
check("plugin: có tool fb_monitor readonly",
      len(ctx.tools) == 1 and ctx.tools[0]["name"] == "fb_monitor" and ctx.tools[0]["min_mode"] == "readonly")

plug._connected_id = lambda: None
check("plugin: _check chặn khi chưa có token", "Chưa kết nối" in (plug._check() or ""))


# ---- 3. Helper thuần: split URL, bóc share, chuẩn hoá ----
check("_split_urls: chuỗi nhiều dòng/phẩy → list",
      plug._split_urls("https://fb.com/a,\n https://fb.com/groups/b") == ["https://fb.com/a", "https://fb.com/groups/b"])
check("_shares: bóc nhiều tên trường", plug._shares({"shareCount": "1,234"}) == 1234 and plug._shares({"shares": 7}) == 7)
n = plug._norm({"text": "hello", "postUrl": "u1", "shares": 50, "likesCount": 10, "commentsCount": 3,
                "author": {"name": "Ann"}, "groupTitle": "Deal Hot"})
check("_norm: chuẩn hoá bài", n["shares"] == 50 and n["reactions"] == 10 and n["author"] == "Ann" and n["source"] == "Deal Hot")


# ---- 4. fb_monitor (giả _token + _run) ----
async def monitor_tests():
    plug._connected_id = lambda: "cfm"
    plug._token = lambda: "APIFYTOK"

    seen = {"actors": []}
    async def _fake_run(actor, token, input_obj):
        seen["actors"].append((actor, [s["url"] for s in input_obj["startUrls"]], input_obj["resultsLimit"], token))
        if actor == plug.PAGES_ACTOR:
            return [{"text": "page viral", "postUrl": "p1", "shares": 300, "likesCount": 20},
                    {"text": "page nhẹ", "postUrl": "p2", "shares": 5}]
        if actor == plug.GROUPS_ACTOR:
            return [{"text": "group hot", "url": "g1", "shares": 999, "groupTitle": "G"}]
        return []
    plug._run = _fake_run

    r = await plug._monitor({"urls": "https://fb.com/pageA, https://fb.com/groups/123", "min_shares": 10, "limit": 25}, None)
    d = json.loads(r)
    actors = {a[0] for a in seen["actors"]}
    check("fb_monitor: gọi CẢ actor Trang lẫn actor Nhóm", actors == {plug.PAGES_ACTOR, plug.GROUPS_ACTOR})
    # nhóm đi đúng actor nhóm
    grp_call = next(a for a in seen["actors"] if a[0] == plug.GROUPS_ACTOR)
    check("fb_monitor: URL /groups/ → actor nhóm", grp_call[1] == ["https://fb.com/groups/123"] and grp_call[2] == 25)
    check("fb_monitor: token truyền vào Apify", all(a[3] == "APIFYTOK" for a in seen["actors"]))
    # lọc min_shares (bỏ bài 5 share) + sắp giảm dần theo share
    shares = [p["shares"] for p in d["posts"]]
    check("fb_monitor: lọc min_shares + sắp theo share giảm dần", shares == [999, 300])
    check("fb_monitor: bài viral nhất lên đầu", d["posts"][0]["text"] == "group hot")

    # thiếu urls → ERROR
    r_no = await plug._monitor({}, None)
    check("fb_monitor: thiếu urls → ERROR", r_no.startswith("ERROR"))

    # Apify lỗi trên mọi actor → ERROR gộp
    async def _fake_err(actor, token, input_obj):
        return {"__error": "token sai"}
    plug._run = _fake_err
    r_err = await plug._monitor({"urls": "https://fb.com/pageA"}, None)
    check("fb_monitor: Apify lỗi → ERROR", r_err.startswith("ERROR") and "token sai" in r_err)

asyncio.run(monitor_tests())

if _fails:
    print(f"\nFAIL - {len(_fails)} test: {_fails}")
    sys.exit(1)
print("\nOK - test_fb_monitor: tất cả pass")
