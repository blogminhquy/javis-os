"""Test chế độ LAZY TOOLS của mcp_hub (chống phình context khi đấu nhiều connector).

Chạy tay / CI (không cần pytest, không chạm mạng):

    cd server && JAVIS_STATE_DIR=<temp> python test_mcp_lazy.py

Phủ: _lazy_config mặc định, _lazy_on (auto ngưỡng + ép bật/tắt), _rank_tools (khớp
cụm/từ khoá/namespace, query rỗng), _connector_menu, _apply_lazy (giấu pool, giữ builtin,
tắt thì nguyên vẹn) và DISPATCH qua route lazy (search trả JSON, run gọi đúng tool + giữ
lớp _guard, các nhánh lỗi name).
"""
import asyncio
import json
import os
import sys
import tempfile

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-lazytest-"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config  # noqa: E402
import mcp_hub  # noqa: E402

_fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)


def set_lazy(cfg):
    """Ép settings mcp.* cho các hàm đọc config (mode/threshold/top_k)."""
    config.read_settings = lambda: {"mcp": cfg}   # type: ignore[assignment]


# ---- fixtures: pool MCP (route entry CÓ 'conn') + builtin (chỉ 'call') ----
_calls = []   # ghi lại tool nào được dispatch tới (chứng minh run đi qua _guard)


def _guarded(fn, deny=False):
    async def _call(args):
        _calls.append((fn, args))
        return "ERROR: bị chặn quyền (giả lập)" if deny else f"OK[{fn}]:{json.dumps(args, ensure_ascii=False)}"
    return _call


def _mcp_tool(fn, ns, name, desc, connector_id="pos", deny=False):
    spec = {"fn": fn, "server": ns, "name": name, "description": desc,
            "schema": {"type": "object", "properties": {"x": {"type": "string"}}},
            "conn_id": "c1", "connector_id": connector_id, "namespace": ns, "label": ns}
    ent = {"call": _guarded(fn, deny), "conn": {"id": "c1", "namespace": ns}, "tool": name}
    return spec, ent


def _builtin(fn, desc):
    spec = {"fn": fn, "server": "javis", "name": fn, "description": desc,
            "schema": {"type": "object", "properties": {}}}
    ent = {"call": _guarded(fn)}   # KHÔNG 'conn' → luôn hiện
    return spec, ent


def _fixture():
    """(tools_spec, route) gồm 3 tool POS + 2 tool Ads + 2 builtin."""
    tools, route = [], {}
    data = [
        _mcp_tool("pos__pos_order", "pos", "pos_order", "Đơn hàng, doanh thu, chốt đơn POS"),
        _mcp_tool("pos__pos_customer", "pos", "pos_customer", "Khách hàng POS"),
        _mcp_tool("pos__pos_stock", "pos", "pos_stock", "Tồn kho sản phẩm"),
        _mcp_tool("ads__ads_insights", "ads", "ads_insights", "Hiệu suất quảng cáo Facebook", "meta-ads"),
        _mcp_tool("ads__ads_campaign", "ads", "ads_campaign", "Chiến dịch quảng cáo", "meta-ads"),
    ]
    for spec, ent in data:
        tools.append(spec)
        route[spec["fn"]] = ent
    for fn, desc in [("javis_connections", "Liệt kê nguồn"), ("javis_use_skill", "Nạp skill")]:
        spec, ent = _builtin(fn, desc)
        tools.append(spec)
        route[fn] = ent
    return tools, route


# ---- _lazy_config mặc định ----
set_lazy({})
mode, thr, top_k = mcp_hub._lazy_config()
check("_lazy_config mặc định = ('auto', 40, 8)", (mode, thr, top_k) == ("auto", 40, 8))
set_lazy({"lazy_threshold": "bad", "lazy_top_k": 999})
_, thr2, top_k2 = mcp_hub._lazy_config()
check("_lazy_config: threshold sai → 40, top_k kẹp ≤ 50", thr2 == 40 and top_k2 == 50)

# ---- _lazy_on ----
set_lazy({"lazy_tools": "auto", "lazy_threshold": 40})
check("_lazy_on auto: 50 tool (>40) → bật", mcp_hub._lazy_on(50) is True)
check("_lazy_on auto: 10 tool (≤40) → tắt", mcp_hub._lazy_on(10) is False)
set_lazy({"lazy_tools": True})
check("_lazy_on ép True → bật kể cả ít tool", mcp_hub._lazy_on(1) is True)
set_lazy({"lazy_tools": False})
check("_lazy_on ép False → tắt kể cả nhiều tool", mcp_hub._lazy_on(500) is False)
set_lazy({"lazy_tools": "off"})
check("_lazy_on 'off' → tắt", mcp_hub._lazy_on(500) is False)

# ---- _rank_tools ----
pool = [s for s, _ in [
    _mcp_tool("pos__pos_order", "pos", "pos_order", "Đơn hàng, doanh thu, chốt đơn POS"),
    _mcp_tool("pos__pos_stock", "pos", "pos_stock", "Tồn kho sản phẩm"),
    _mcp_tool("ads__ads_insights", "ads", "ads_insights", "Hiệu suất quảng cáo Facebook", "meta-ads"),
]]
r = mcp_hub._rank_tools(pool, "doanh thu pos hôm nay", 8)
check("_rank_tools: 'doanh thu pos' → pos_order đứng đầu", r and r[0]["fn"] == "pos__pos_order")
r2 = mcp_hub._rank_tools(pool, "quảng cáo", 8)
check("_rank_tools: 'quảng cáo' → ra ads_insights", any(t["fn"] == "ads__ads_insights" for t in r2))
check("_rank_tools: query rỗng → []", mcp_hub._rank_tools(pool, "", 8) == [])
check("_rank_tools: không khớp gì → []", mcp_hub._rank_tools(pool, "zzzxxxqqq", 8) == [])
check("_rank_tools: top_k cắt đúng", len(mcp_hub._rank_tools(pool, "pos ads tồn kho quảng cáo", 1)) == 1)

# ---- _connector_menu ----
menu = mcp_hub._connector_menu(pool)
check("_connector_menu: nêu namespace pos + ads", "pos" in menu and "ads" in menu)
check("_connector_menu: có đếm số tool", "tool" in menu)

# ---- _apply_lazy: BẬT → giấu pool, giữ builtin, thêm 2 meta-tool ----
set_lazy({"lazy_tools": True})
tools, route = _fixture()
lt, lr = mcp_hub._apply_lazy(tools, route)
lfns = {t["fn"] for t in lt}
check("_apply_lazy bật: có javis_search_tools", mcp_hub._LAZY_SEARCH in lfns)
check("_apply_lazy bật: có javis_run_tool", mcp_hub._LAZY_RUN in lfns)
check("_apply_lazy bật: builtin vẫn hiện", "javis_connections" in lfns and "javis_use_skill" in lfns)
check("_apply_lazy bật: tool pool MCP bị giấu", not any(f.startswith(("pos__", "ads__")) for f in lfns))
check("_apply_lazy bật: route lazy KHÔNG chứa tool pool", not any(f.startswith(("pos__", "ads__")) for f in lr))
check("_apply_lazy bật: cắt gọn còn 4 tool (2 builtin + 2 meta)", len(lt) == 4)
search_spec = next(t for t in lt if t["fn"] == mcp_hub._LAZY_SEARCH)
check("_apply_lazy: mô tả search nhúng thực đơn nguồn", "pos" in search_spec["description"] and "ads" in search_spec["description"])

# ---- _apply_lazy: TẮT → nguyên vẹn ----
set_lazy({"lazy_tools": False})
tools2, route2 = _fixture()
lt0, lr0 = mcp_hub._apply_lazy(tools2, route2)
check("_apply_lazy tắt: trả nguyên tools_spec", lt0 is tools2)
check("_apply_lazy tắt: trả nguyên route", lr0 is route2)

# ---- auto dưới ngưỡng → không đụng (5 tool pool < 40) ----
set_lazy({"lazy_tools": "auto", "lazy_threshold": 40})
tools3, route3 = _fixture()
lt_auto, _ = mcp_hub._apply_lazy(tools3, route3)
check("_apply_lazy auto: 5 tool < ngưỡng → không lazy", lt_auto is tools3)


async def _dispatch_tests():
    set_lazy({"lazy_tools": True})
    tools, route = _fixture()
    _lt, lr = mcp_hub._apply_lazy(tools, route)

    # search qua route lazy → JSON có tool khớp
    res = await mcp_client_call(lr, mcp_hub._LAZY_SEARCH, {"query": "doanh thu pos"})
    ok = False
    try:
        obj = json.loads(res)
        ok = any(t["name"] == "pos__pos_order" for t in obj.get("tools", []))
    except Exception:
        ok = False
    check("dispatch search: trả JSON chứa pos__pos_order", ok)

    # search không khớp → thông điệp kèm menu (không phải JSON tool)
    res_empty = await mcp_client_call(lr, mcp_hub._LAZY_SEARCH, {"query": ""})
    check("dispatch search rỗng → gợi ý menu", "Nguồn đang đấu" in res_empty)

    # run gọi đúng tool pool → dispatch tới _guard của tool đó
    _calls.clear()
    res_run = await mcp_client_call(lr, mcp_hub._LAZY_RUN,
                                    {"name": "pos__pos_order", "args": {"x": "hôm nay"}})
    check("dispatch run: gọi tới đúng tool pool", _calls and _calls[0][0] == "pos__pos_order")
    check("dispatch run: trả kết quả tool", res_run.startswith("OK[pos__pos_order]"))

    # run: args dạng chuỗi JSON vẫn parse
    _calls.clear()
    await mcp_client_call(lr, mcp_hub._LAZY_RUN, {"name": "pos__pos_stock", "args": "{\"x\":\"1\"}"})
    check("dispatch run: args chuỗi JSON được parse", _calls and _calls[0][1] == {"x": "1"})

    # run: tên sai / meta / thiếu → ERROR rõ, KHÔNG dispatch
    _calls.clear()
    r_bad = await mcp_client_call(lr, mcp_hub._LAZY_RUN, {"name": "khong_co", "args": {}})
    r_meta = await mcp_client_call(lr, mcp_hub._LAZY_RUN, {"name": mcp_hub._LAZY_RUN, "args": {}})
    r_none = await mcp_client_call(lr, mcp_hub._LAZY_RUN, {"args": {}})
    check("dispatch run: tên sai → ERROR", r_bad.startswith("ERROR"))
    check("dispatch run: gọi meta-tool → ERROR", r_meta.startswith("ERROR"))
    check("dispatch run: thiếu name → ERROR", r_none.startswith("ERROR"))
    check("dispatch run: các nhánh lỗi KHÔNG dispatch tool nào", _calls == [])

    # run GIỮ lớp _guard: tool bị chặn quyền → trả nguyên ERROR của guard
    tools_d, route_d = _fixture()
    spec, ent = _mcp_tool("pos__pos_refund", "pos", "pos_refund", "Hoàn tiền (danger)", deny=True)
    tools_d.append(spec)
    route_d[spec["fn"]] = ent
    _ltd, lrd = mcp_hub._apply_lazy(tools_d, route_d)
    r_deny = await mcp_client_call(lrd, mcp_hub._LAZY_RUN, {"name": "pos__pos_refund", "args": {}})
    check("dispatch run: giữ lớp _guard (tool bị chặn → ERROR quyền)", "bị chặn quyền" in r_deny)


async def mcp_client_call(route, fn, args):
    """Gọi qua đúng đường mcp_client.call_route (entry {'call'})."""
    import mcp_client
    return await mcp_client.call_route(route, fn, args)


asyncio.run(_dispatch_tests())

print()
if _fails:
    print("FAILED (%d): %s" % (len(_fails), ", ".join(_fails)))
    sys.exit(1)
print("ALL PASS")
