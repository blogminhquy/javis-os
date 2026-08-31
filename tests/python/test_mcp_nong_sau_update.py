"""Cập nhật xong không được mất kết nối MCP (Pancake POS và mọi nguồn nguội khác).

    python tests/run.py mcp_nong_sau_update      (KHÔNG mạng, không spawn tiến trình)

Chủ repo báo 31/08: *"Khi update rất hay bị mất kết nối với các mcp của javis, đặc biệt là
poscake"*. Kết nối không hỏng - nó chỉ VẮNG MẶT trong hộp công cụ của phiên chat vừa mở, và
lát sau tự khỏi. Chuỗi nhân quả, đọc từ dưới lên:

  1. Cập nhật = tiến trình mới: session pool RỖNG. Bản Docker còn mất cả cache npm/uv theo
     ảnh cũ, nên `npx -y ...` / `uvx ...` phải tải package lại từ đầu.
  2. `_warm_mcp_hub` (chỗ SINH RA để lo đúng việc này) gọi thẳng `discover_all`, tức đi qua
     vòng dò của LƯỢT CHAT với trần 20 giây mỗi nguồn. Con số đó đúng cho lượt chat - có
     người đang ngồi chờ - nhưng ở vòng làm nóng thì không có ai chờ cả, và nó cắt đúng thứ
     vòng này sinh ra để làm.
  3. Nguồn nguội quá 20 giây rơi khỏi vòng dò. Danh sách tool THIẾU đó được cache 60 giây.
  4. Người dùng vừa bấm cập nhật xong thì mở app gõ ngay - rơi trọn vào cửa sổ 60 giây ấy.
  5. CLI engine (Claude Code, Codex, Grok) đọc danh sách tool ĐÚNG MỘT LẦN lúc mở phiên. Nên
     nguồn kia vắng mặt suốt CẢ PHIÊN chat, dù bước 3 đã hết hạn từ lâu.

Ba chốt được khoá ở đây: trần làm nóng phải rộng hơn hẳn trần lượt chat, `warm_pool` phải mở
được phiên cho nguồn mà vòng chat bỏ, và một vòng dò THIẾU nguồn thì chỉ được cache ngắn.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import os
import time
from pathlib import Path

import mcp_client  # noqa: E402

_fails = []


def check(ten, dieu_kien, them=""):
    print(("ok   " if dieu_kien else "FAIL ") + ten
          + (("  [" + str(them) + "]") if them and not dieu_kien else ""))
    if not dieu_kien:
        _fails.append(ten)


def conn(i, **kw):
    c = {"id": f"c{i}", "connector_id": "x", "label": f"nguồn {i}", "slug": f"s{i}",
         "namespace": f"ns{i}", "transport": "http", "url": f"http://127.0.0.1:9/{i}",
         "command": "", "args": [], "headers": {}, "env": {}, "internal": "", "secrets": {},
         "config": {}, "perm": "full", "deny_tools": [], "is_default": False,
         "auth": None, "connector": {}}
    c.update(kw)
    return c


# ============================================================
# 1. Hai vòng, hai trần - và trần làm nóng phải RỘNG HƠN HẲN
# ============================================================
for k in ("JAVIS_MCP_DISCOVER_TIMEOUT", "JAVIS_MCP_WARM_TIMEOUT"):
    os.environ.pop(k, None)

check("trần lượt chat vẫn là 20s (không đụng vào đường găng)", mcp_client.tran_dial() == 20.0)
check(f"trần làm nóng rộng hơn hẳn ({mcp_client.tran_warm()}s > {mcp_client.tran_dial()}s)",
      mcp_client.tran_warm() >= 5 * mcp_client.tran_dial(), mcp_client.tran_warm())
os.environ["JAVIS_MCP_WARM_TIMEOUT"] = "45"
check("chỉnh được bằng JAVIS_MCP_WARM_TIMEOUT", mcp_client.tran_warm() == 45.0)
os.environ["JAVIS_MCP_WARM_TIMEOUT"] = "0"
check("đặt 0 = bỏ trần làm nóng", mcp_client.tran_warm() is None)
os.environ.pop("JAVIS_MCP_WARM_TIMEOUT")


# ============================================================
# 2. Nguồn NGUỘI: vòng chat bỏ, vòng làm nóng phải vớt được
# ============================================================
# "Nguội" = phải tải package / dựng lại phiên phía dịch vụ. Ở đây rút gọn thành 0,25 giây, và
# hai trần rút theo cùng tỉ lệ: chat 0,1s (bỏ) - làm nóng 5s (kịp). Đúng khe mà Pancake POS
# rơi vào trên VPS thật, chỉ khác đơn vị.
_CHAM = 0.25
_da_mo = set()          # phiên đã mở XONG (bị huỷ giữa chừng thì không tính - pool cũng vứt nó)


async def _list_tools_nguoi(spec):
    """`pool.list_tools` giả: lần mở ĐẦU TIÊN của c1 chậm, mở xong rồi thì tức thì."""
    k = spec.get("key")
    if k == "c1" and k not in _da_mo:
        await asyncio.sleep(_CHAM)
    _da_mo.add(k)       # chỉ chạy tới đây khi lượt gọi hoàn tất, không phải khi bị cắt
    return [{"name": "t", "description": "d", "inputSchema": {"type": "object"}}]


_that = mcp_client.pool.list_tools
mcp_client.pool.list_tools = _list_tools_nguoi
os.environ["JAVIS_MCP_DISCOVER_TIMEOUT"] = "0.1"
os.environ["JAVIS_MCP_WARM_TIMEOUT"] = "5"
try:
    conns = [conn(1), conn(2)]

    bo_qua = set()
    tools, _ = asyncio.run(mcp_client.discover_resolved(conns, bo_qua=bo_qua))
    check("vòng chat: nguồn nguội bị bỏ (đúng như hôm nay, không đổi)",
          {t["server"] for t in tools} == {"ns2"}, [t["server"] for t in tools])
    check("và caller BIẾT là bản thiếu (bo_qua có id nguồn bị bỏ)", bo_qua == {"c1"}, bo_qua)

    nong, lanh = asyncio.run(mcp_client.warm_pool(conns))
    check("vòng làm nóng: mở được phiên cho CẢ nguồn nguội", sorted(nong) == ["c1", "c2"], nong)
    check("và không còn nguồn nào lạnh", lanh == [], lanh)

    # Sau khi pool đã nóng, CHÍNH vòng chat với trần 0,1s đó phải thấy đủ hai nguồn - đây là
    # điều người dùng thật sự nhận được: gõ câu đầu tiên sau cập nhật là có đủ tool. Vẫn dùng
    # nguyên hàm giả cũ, không đổi sang hàm nhanh, để cái được chứng minh là VÒNG LÀM NÓNG chứ
    # không phải một điều kiện test dễ hơn.
    bo_qua2 = set()
    tools2, _ = asyncio.run(mcp_client.discover_resolved(conns, bo_qua=bo_qua2))
    check("pool đã nóng → lượt chat kế tiếp thấy ĐỦ nguồn",
          {t["server"] for t in tools2} == {"ns1", "ns2"}, [t["server"] for t in tools2])
    check("và không còn nguồn nào bị bỏ", bo_qua2 == set(), bo_qua2)

    # Connector ẢO (không url, không command) KHÔNG phải nguồn bị bỏ - nó vốn không có phiên
    # nào để mở. Đếm nhầm nó là cache ngắn hạn bật vĩnh viễn trên mọi máy có Meta Ads.
    ao = conn(9, url="", command="", auth="oauth", connector_id="meta-ads-graph")
    bo_qua3 = set()
    asyncio.run(mcp_client.discover_resolved([ao], bo_qua=bo_qua3))
    check("connector ảo KHÔNG bị tính là nguồn bị bỏ", bo_qua3 == set(), bo_qua3)
    nong3, lanh3 = asyncio.run(mcp_client.warm_pool([ao]))
    check("và cũng không bị tính là nguồn lạnh khi làm nóng",
          (nong3, lanh3) == ([], []), (nong3, lanh3))
finally:
    mcp_client.pool.list_tools = _that
    os.environ.pop("JAVIS_MCP_DISCOVER_TIMEOUT", None)
    os.environ.pop("JAVIS_MCP_WARM_TIMEOUT", None)


# ============================================================
# 3. Vòng dò THIẾU nguồn chỉ được cache NGẮN
# ============================================================
import mcp_hub  # noqa: E402

check(f"cache bản đủ vẫn 60s", mcp_hub._CACHE_TTL == 60)
check(f"cache bản thiếu ngắn hơn nhiều ({mcp_hub._CACHE_TTL_THIEU}s)",
      0 < mcp_hub._CACHE_TTL_THIEU <= mcp_hub._CACHE_TTL / 4, mcp_hub._CACHE_TTL_THIEU)

_thieu = {"on": True}


async def _dr(conns, bo_qua=None):
    if _thieu["on"] and bo_qua is not None:
        bo_qua.add("c1")
    return [], {}


_that_dr, _that_res = mcp_client.discover_resolved, mcp_hub.mcp_store.resolved
mcp_client.discover_resolved = _dr
mcp_hub.mcp_store.resolved = lambda enabled_only=True: []
try:
    mcp_hub._cache.clear()
    asyncio.run(mcp_hub.discover_all("full"))
    ttl_thieu = [v.get("ttl") for v in mcp_hub._cache.values()]
    check("vòng thiếu nguồn → cache ngắn hạn",
          ttl_thieu and all(t == mcp_hub._CACHE_TTL_THIEU for t in ttl_thieu), ttl_thieu)

    _thieu["on"] = False
    mcp_hub._cache.clear()
    asyncio.run(mcp_hub.discover_all("full"))
    ttl_du = [v.get("ttl") for v in mcp_hub._cache.values()]
    check("vòng đủ nguồn → cache 60s như cũ",
          ttl_du and all(t == mcp_hub._CACHE_TTL for t in ttl_du), ttl_du)

    # Cache ngắn phải THẬT SỰ hết hạn sớm: lùi mốc thời gian đúng quá ngưỡng ngắn rồi gọi lại,
    # phải thấy vòng dò chạy thêm lần nữa.
    _thieu["on"] = True
    mcp_hub._cache.clear()
    asyncio.run(mcp_hub.discover_all("full"))
    _lan = {"n": 0}

    async def _dem_dr(conns, bo_qua=None):
        _lan["n"] += 1
        return [], {}

    mcp_client.discover_resolved = _dem_dr
    for v in mcp_hub._cache.values():
        v["ts"] = time.time() - (mcp_hub._CACHE_TTL_THIEU + 1)
    asyncio.run(mcp_hub.discover_all("full"))
    check("bản thiếu hết hạn sau vài giây → dò lại (không phải chờ đủ 60s)", _lan["n"] == 1,
          _lan["n"])
finally:
    mcp_client.discover_resolved = _that_dr
    mcp_hub.mcp_store.resolved = _that_res
    mcp_hub._cache.clear()


# ============================================================
# 4. CANARY nguồn: vòng làm nóng lúc khởi động phải dùng warm_pool
# ============================================================
_main = Path(SERVER, "main.py").read_text(encoding="utf-8")
_warm = _main.split("async def _warm_mcp_hub", 1)[1].split("\n@app.on_event", 1)[0]
check("CANARY: _warm_mcp_hub làm nóng pool trước khi dò", "mcp_client.warm_pool(" in _warm)
check("CANARY: và làm mới cache sau khi nóng (force_refresh)",
      'discover_all("full", force_refresh=True)' in _warm)
check("CANARY: nguồn còn nguội được hẹn làm nóng lại", "for cho in (20, 60)" in _warm)

print()
if _fails:
    print(f"FAIL {len(_fails)}: " + "; ".join(_fails))
    raise SystemExit(1)
print("TẤT CẢ PASS")
