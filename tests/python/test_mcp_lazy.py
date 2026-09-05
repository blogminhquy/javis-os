"""Test chế độ LAZY TOOLS của mcp_hub (chống phình context khi đấu nhiều connector).

Chạy tay / CI (không cần pytest, không chạm mạng):

    python tests/run.py mcp_lazy

Phủ: _lazy_config mặc định, _lazy_on (auto ngưỡng + ép bật/tắt), _rank_tools (khớp
cụm/từ khoá/namespace, query rỗng), _connector_menu, _apply_lazy (giấu pool, giữ builtin,
tắt thì nguyên vẹn) và DISPATCH qua route lazy (search trả JSON, run gọi đúng tool + giữ
lớp _guard, các nhánh lỗi name).
"""
from _paths import ROOT, SERVER  # noqa: E402,F401  - nạp server/ vào sys.path (xem tests/python/_paths.py)
import asyncio
import json
import os
import sys
import tempfile

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-lazytest-"))

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
# Builtin KHÔNG còn được miễn: javis_connections và javis_use_skill đều phình theo số
# nguồn/số skill người dùng cắm thêm, đúng số hạng O(N) mà tầng lazy sinh ra để chống.
# Trước đây chúng lọt lưới vì pool suy ra từ "có conn hay không", mà builtin thì không có.
check("_apply_lazy bật: builtin phình theo N cũng bị giấu",
      "javis_connections" not in lfns and "javis_use_skill" not in lfns)
check("_apply_lazy bật: tool pool MCP bị giấu", not any(f.startswith(("pos__", "ads__")) for f in lfns))
check("_apply_lazy bật: route lazy KHÔNG chứa tool pool", not any(f.startswith(("pos__", "ads__")) for f in lr))
check("_apply_lazy bật: fixture không có tool hạt nhân → còn đúng 2 meta", len(lt) == 2)
check("_apply_lazy bật: builtin bị giấu vẫn GỌI ĐƯỢC qua run",
      "javis_use_skill" in lr or mcp_hub._LAZY_RUN in lr)
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

# ---- Phase 8 ép lazy để số MCP tăng không làm prompt đầu tăng theo ----
set_lazy({"lazy_tools": False})
tools4, route4 = _fixture()
lt_forced, _ = mcp_hub._apply_lazy(tools4, route4, force=True)
forced_fns = {t["fn"] for t in lt_forced}
check("_apply_lazy Phase 8 force: giấu pool dù global setting tắt",
      mcp_hub._LAZY_SEARCH in forced_fns and not any(x.startswith("pos__") for x in forced_fns))


# ============================================================
# AMBIENT - connector đấu vào TÀI KHOẢN Claude (Drive/Gmail...): tool native mcp__*, hub chỉ
# KỂ cho model biết + chỉ cách gọi (không qua run). Trước đây lazy layer mù với nhóm này.
# ============================================================
_AMB = [{"name": "Google Drive", "url": "https://g"}, {"name": "Gmail", "url": ""}]

# ---- _ambient_prefix / _match_ambient (pure) ----
check("_ambient_prefix: 'Google Drive' → 'Google_Drive'", mcp_hub._ambient_prefix("Google Drive") == "Google_Drive")
check("_ambient_prefix: rỗng → 'mcp'", mcp_hub._ambient_prefix("") == "mcp")
check("_match_ambient: 'tìm file trên drive' → Google Drive",
      [s["name"] for s in mcp_hub._match_ambient(_AMB, "tìm file trên drive")] == ["Google Drive"])
check("_match_ambient: khớp theo prefix 'google_drive'",
      any(s["name"] == "Google Drive" for s in mcp_hub._match_ambient(_AMB, "đọc google_drive")))
check("_match_ambient: query rỗng → []", mcp_hub._match_ambient(_AMB, "") == [])
check("_match_ambient: không khớp → []", mcp_hub._match_ambient(_AMB, "doanh thu pos") == [])

# ---- _ambient_enabled / _ambient_servers theo settings (không đụng CLI khi tắt) ----
set_lazy({"ambient_hint": False})
check("_ambient_enabled: tắt qua settings", mcp_hub._ambient_enabled() is False)
check("_ambient_servers: tắt → [] (không đụng CLI)", mcp_hub._ambient_servers() == [])
set_lazy({})
check("_ambient_enabled: mặc định bật", mcp_hub._ambient_enabled() is True)

# ---- _ambient_refresh: nạp từ claude mcp list, chỉ lấy 'connected' ----
import claude_cli  # noqa: E402
_orig_native = claude_cli.mcp_native_list
claude_cli.mcp_native_list = lambda: [
    {"name": "Google Drive", "url": "https://g", "connected": True},
    {"name": "Gmail", "url": "", "connected": True},
    {"name": "Chưa auth", "url": "https://x", "connected": False},
]
try:
    mcp_hub._ambient_refresh()
    _got = [s["name"] for s in mcp_hub._ambient_cache["servers"]]
    check("_ambient_refresh: lấy đúng server 'connected'", _got == ["Google Drive", "Gmail"])
    check("_ambient_refresh: bỏ server chưa connected", "Chưa auth" not in _got)
finally:
    claude_cli.mcp_native_list = _orig_native
    mcp_hub._ambient_cache.update({"ts": 0.0, "servers": [], "refreshing": False})

# ---- _connector_menu kèm ambient ----
menu_amb = mcp_hub._connector_menu(pool, _AMB)
check("_connector_menu ambient: nêu Google Drive + tiền tố native",
      "Google Drive" in menu_amb and "mcp__Google_Drive__" in menu_amb)
check("_connector_menu không ambient: KHÔNG có tài khoản Claude",
      "Google Drive" not in mcp_hub._connector_menu(pool))

# ---- _connections_json(include_ambient) + _apply_lazy(include_ambient) - monkeypatch nguồn ----
_orig_amb = mcp_hub._ambient_servers
mcp_hub._ambient_servers = lambda: list(_AMB)
try:
    cj = mcp_hub._connections_json(include_ambient=True)
    check("_connections_json ambient: có source claude_account", "claude_account" in cj)
    check("_connections_json ambient: chỉ tool native mcp__Google_Drive__", "mcp__Google_Drive__" in cj)
    check("_connections_json KHÔNG ambient: bỏ tài khoản Claude",
          "claude_account" not in mcp_hub._connections_json(include_ambient=False))

    set_lazy({"lazy_tools": True})
    tools_a, route_a = _fixture()
    lta, _lra = mcp_hub._apply_lazy(tools_a, route_a, include_ambient=True)
    search_a = next(t for t in lta if t["fn"] == mcp_hub._LAZY_SEARCH)
    check("_apply_lazy ambient: mô tả search nhúng connector tài khoản",
          "mcp__Google_Drive__" in search_a["description"])
    ltn, _lrn = mcp_hub._apply_lazy(_fixture()[0], _fixture()[1])   # include_ambient mặc định False
    search_n = next(t for t in ltn if t["fn"] == mcp_hub._LAZY_SEARCH)
    check("_apply_lazy KHÔNG ambient: search không nhúng tài khoản Claude",
          "Google Drive" not in search_n["description"])
finally:
    mcp_hub._ambient_servers = _orig_amb


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

    # ---- AMBIENT trong search: query khớp connector tài khoản → chỉ tool native (không qua run) ----
    set_lazy({"lazy_tools": True})
    _orig_amb = mcp_hub._ambient_servers
    mcp_hub._ambient_servers = lambda: [{"name": "Google Drive", "url": "https://g"}]
    try:
        tools_am, route_am = _fixture()
        _lam, lram = mcp_hub._apply_lazy(tools_am, route_am, include_ambient=True)
        # "drive" KHÔNG có trong pool (pos/ads) → chỉ ra tool native mcp__Google_Drive__
        res_dr = await mcp_client_call(lram, mcp_hub._LAZY_SEARCH, {"query": "tìm file trên drive"})
        obj_dr = json.loads(res_dr)
        check("dispatch search ambient: trả tai_khoan_claude", bool(obj_dr.get("tai_khoan_claude")))
        check("dispatch search ambient: chỉ tool native mcp__Google_Drive__",
              "mcp__Google_Drive__" in str(obj_dr.get("tai_khoan_claude")))
        check("dispatch search ambient: KHÔNG bịa tool pool cho drive", "tools" not in obj_dr)
        # query POS vẫn ra tool pool bình thường, không dính ambient
        res_pos = await mcp_client_call(lram, mcp_hub._LAZY_SEARCH, {"query": "doanh thu pos"})
        obj_pos = json.loads(res_pos)
        check("dispatch search ambient: query pos vẫn trả tool pool",
              any(t["name"] == "pos__pos_order" for t in obj_pos.get("tools", [])))
        check("dispatch search ambient: query pos KHÔNG kèm tài khoản Claude", "tai_khoan_claude" not in obj_pos)
    finally:
        mcp_hub._ambient_servers = _orig_amb


async def mcp_client_call(route, fn, args):
    """Gọi qua đúng đường mcp_client.call_route (entry {'call'})."""
    import mcp_client
    return await mcp_client.call_route(route, fn, args)


asyncio.run(_dispatch_tests())


# ============================================================
# Nhóm tool HẠT NHÂN + ngưỡng theo KÍCH THƯỚC
# ============================================================
def _core_fixture():
    """Pool nhỏ nhưng có đủ tool hạt nhân, để kiểm chúng KHÔNG bị giấu."""
    tools, route = [], {}
    for fn in sorted(mcp_hub.CORE_TOOL_FNS):
        spec, ent = _builtin(fn, f"tool hạt nhân {fn}")
        tools.append(spec)
        route[fn] = ent
    for spec, ent in [_mcp_tool("pos__pos_order", "pos", "pos_order", "Đơn hàng POS")]:
        tools.append(spec)
        route[spec["fn"]] = ent
    return tools, route


set_lazy({"lazy_tools": True})
ct, cr = mcp_hub._apply_lazy(*_core_fixture())
cfns = {t["fn"] for t in ct}
check("tool hạt nhân KHÔNG bao giờ bị giấu", mcp_hub.CORE_TOOL_FNS <= cfns)
check("tool ngoài nhóm hạt nhân vẫn bị giấu", "pos__pos_order" not in cfns)

# Rào khoá hai chiều: tên trong CORE_TOOL_FNS phải là builtin CÓ THẬT. Gõ sai hoặc đổi tên
# builtin mà quên sửa danh sách thì tool đó âm thầm rơi vào pool - hỏng câm, không ai biết.
_vault = tempfile.mkdtemp(prefix="javis-corecheck-")
os.makedirs(os.path.join(_vault, "skills"), exist_ok=True)
_bt, _br = mcp_hub._builtin_tools("full", _vault)
_real = {t["fn"] for t in _bt}
for _fn in sorted(mcp_hub.CORE_TOOL_FNS):
    check(f"CORE_TOOL_FNS '{_fn}' là builtin có thật", _fn in _real)

# Ngưỡng theo KÍCH THƯỚC: ít tool nhưng schema nặng vẫn phải bật lazy. Đây chính là tình
# huống thật đã bỏ lọt - 26 tool nặng 17k ký tự nằm dưới ngưỡng đếm 40 nên lazy chưa từng
# chạy lần nào.
set_lazy({})   # về mặc định 'auto'
check("auto: ít tool + schema nhẹ → KHÔNG bật lazy", mcp_hub._lazy_on(5, 1000) is False)
check("auto: ít tool nhưng schema NẶNG → BẬT lazy",
      mcp_hub._lazy_on(5, mcp_hub._lazy_char_budget() + 1) is True)
check("auto: đông tool tuy schema nhẹ → vẫn bật (điều kiện cũ còn nguyên)",
      mcp_hub._lazy_on(500, 0) is True)
set_lazy({"lazy_tools": False})
check("ép tắt: schema nặng vẫn KHÔNG bật", mcp_hub._lazy_on(500, 10**9) is False)

# _pool_chars phải đo thật, vì nó là đại lượng quyết định
set_lazy({})
_p = [{"fn": "x", "description": "y" * 500, "schema": {}}]
check("_pool_chars đếm theo ký tự schema thật", mcp_hub._pool_chars(_p) > 500)
check("_pool_chars không nổ với dữ liệu lạ", mcp_hub._pool_chars([{"fn": object()}]) == 0)

# Skill bị giấu vẫn phải TÌM LẠI được, nếu không thì tiết kiệm token bằng cách làm hỏng Javis.
_vs = tempfile.mkdtemp(prefix="javis-skillfind-")
for _slug, _desc in [("viet-email", "Soạn email bán hàng theo giọng thương hiệu")]:
    _d = os.path.join(_vs, "skills", _slug)
    os.makedirs(_d, exist_ok=True)
    with open(os.path.join(_d, "SKILL.md"), "w", encoding="utf-8") as _fh:
        _fh.write(f"---\nname: {_slug}\ndescription: {_desc}\ngroup: Test\n---\nnội dung\n")
set_lazy({"lazy_tools": True})
_st, _sr = mcp_hub._apply_lazy(*mcp_hub._builtin_tools("full", _vs))


async def _skill_findable():
    raw = await _sr[mcp_hub._LAZY_SEARCH]["call"]({"query": "viết email cho khách"})
    try:
        names = [t["name"] for t in json.loads(raw).get("tools", [])]
    except (ValueError, TypeError):
        names = []
    check("giấu javis_use_skill rồi vẫn tìm lại được bằng từ khoá skill",
          "javis_use_skill" in names)


asyncio.run(_skill_findable())


# ============================================================
# THỰC ĐƠN PHẢI GỌI TÊN TỪNG PLUGIN
#
# Vụ thật 05/09/2026: người dùng cài gói TTS Dropship (20 tool), plugin nạp đủ, hub phục vụ
# đủ, `javis_run_tool` gọi tới nơi. Nhưng lazy đang bật, và tool plugin không mang
# `namespace` nên cả 20 tool rơi vào nhóm "javis" cùng builtin. Model đọc thực đơn chỉ thấy
# đúng một dòng "javis (javis, 45 tool): skill của brain, danh sách nguồn đang đấu, tiện ích
# nội bộ" - KHÔNG một chữ nào nhắc TTS, dropship, sàn hay đơn hàng.
#
# Nó kết luận gói chưa kết nối và báo là không lên đơn được. Không có lỗi nào ở đâu cả: hub
# đúng, plugin đúng, quyền đúng. Chỉ là thứ DUY NHẤT model đọc được về năng lực của mình lại
# không nói ra năng lực đó có tồn tại.
#
# Nên đây là canary về NỘI DUNG thực đơn, không phải về việc tool có nằm trong pool. Tool nằm
# trong pool mà không ai biết đường tìm thì đúng bằng không có.
# ============================================================
_pl_tools = [
    {"fn": "tts_create_order", "server": "javis", "namespace": "tts-dropship",
     "label": "TTS Dropship", "group_desc": "Bán dropship trên sàn thitruongsi.com - lên đơn, "
                                            "theo dõi vận đơn, xem tiền về",
     "description": "TẠO ĐƠN HÀNG THẬT trên sàn", "schema": {"type": "object", "properties": {}}},
    {"fn": "tts_orders", "server": "javis", "namespace": "tts-dropship",
     "label": "TTS Dropship", "group_desc": "Bán dropship trên sàn thitruongsi.com - lên đơn, "
                                            "theo dõi vận đơn, xem tiền về",
     "description": "Đọc đơn hàng", "schema": {"type": "object", "properties": {}}},
    {"fn": "javis_use_skill", "server": "javis",
     "description": "Chạy skill của brain", "schema": {"type": "object", "properties": {}}},
]
_menu = mcp_hub._connector_menu(_pl_tools)
check("thực đơn GỌI TÊN plugin, không gộp hết vào 'javis'", "tts-dropship" in _menu)
check("thực đơn nêu tên hiển thị của plugin", "TTS Dropship" in _menu)
check("thực đơn nói plugin đó LÀM GÌ (mô tả từ manifest)", "dropship" in _menu.lower())
check("đếm đúng số tool của riêng plugin đó", "2 tool" in _menu)
check("builtin vẫn ở nhóm javis với mô tả nội bộ",
      "javis (" in _menu and "skill của brain" in _menu)

# Không có `group_desc` (plugin đời cũ) thì vẫn phải gọi tên nhóm, chỉ là thiếu mô tả - suy
# biến nghiêng về "nói được tên" chứ không quay lại gộp chung.
_menu2 = mcp_hub._connector_menu([{"fn": "x_a", "server": "javis", "namespace": "goi-cu",
                                   "label": "Gói cũ", "description": "d",
                                   "schema": {}}])
check("plugin thiếu mô tả vẫn hiện thành nhóm riêng", "goi-cu" in _menu2 and "Gói cũ" in _menu2)


# `plugins_host.plugin_tools` phải THẬT SỰ gắn ba trường đó, nếu không thì canary trên chỉ
# canh một fixture do chính test dựng ra.
def _plugin_gan_nhan():
    import plugins_host
    src = os.path.join(SERVER, "plugins_host.py")
    with open(src, encoding="utf-8") as fh:
        s = fh.read()
    khoi = s.split('tools.append({"fn": fn, "server": "javis"')[-1][:400]
    for truong in ('"namespace": lp.slug', '"label": lp.name', '"group_desc": lp.description'):
        check(f"plugin_tools gắn {truong}", truong in khoi)
    check("LoadedPlugin mang description của manifest",
          '"description"' in s.split("__slots__")[1][:200])


_plugin_gan_nhan()

print()
if _fails:
    print("FAILED (%d): %s" % (len(_fails), ", ".join(_fails)))
    sys.exit(1)
print("ALL PASS")
