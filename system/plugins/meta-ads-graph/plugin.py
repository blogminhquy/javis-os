"""Plugin bundled: đọc số liệu Meta Ads (Facebook/Instagram) qua Graph API - CHỈ ĐỌC.

Không đi qua MCP beta bị khoá của Meta (mcp.facebook.com/ads); gọi THẲNG graph.facebook.com
Marketing API bằng user access token của kết nối "meta-ads-graph" (connector BYO app - user tự
tạo Facebook App, OAuth do oauth_mcp lo, token tự gia hạn ~60 ngày). Đây là cách Composio/byadsco
làm. Mọi tool đều readonly (chỉ GET) - không tạo/sửa chiến dịch, không tiêu tiền.
"""
from __future__ import annotations

import json

GRAPH = "https://graph.facebook.com/v25.0"
CONNECTOR_ID = "meta-ads-graph"
_INSIGHT_FIELDS = "spend,impressions,clicks,ctr,cpc,cpm,reach,frequency,actions,action_values"
_CAMPAIGN_FIELDS = "name,status,effective_status,objective,daily_budget,lifetime_budget,start_time,stop_time"


def _connected_id():
    """id của kết nối meta-ads-graph ĐÃ đăng nhập (None nếu chưa). Import lười để load không phụ thuộc."""
    try:
        import mcp_store
        import oauth_mcp
    except Exception:
        return None
    for c in mcp_store.list_connections():
        if c.get("connector_id") == CONNECTOR_ID and oauth_mcp.status(c["id"]).get("connected"):
            return c["id"]
    return None


def _check():
    if not _connected_id():
        return ("Chưa kết nối Facebook. Vào trang Kết nối, chọn 'Meta Ads (Facebook & Instagram)', "
                "làm theo hướng dẫn tạo Facebook App rồi đăng nhập. Sau đó gọi lại tool này.")
    return None


async def _token():
    import oauth_mcp
    cid = _connected_id()
    if not cid:
        return None
    hdr = await oauth_mcp.auth_headers(cid)      # tự refresh token ~60 ngày khi sắp hết hạn
    return (hdr.get("Authorization", "") or "").replace("Bearer ", "").strip() or None


async def _get(path, params, token):
    import httpx
    try:
        async with httpx.AsyncClient(timeout=30) as c:
            r = await c.get(f"{GRAPH}/{str(path).lstrip('/')}",
                            params={**(params or {}), "access_token": token})
        try:
            return r.json()
        except Exception:
            return {"error": {"message": f"HTTP {r.status_code}: {r.text[:200]}"}}
    except Exception as e:
        return {"error": {"message": f"{type(e).__name__}: {e}"}}


def _fmt(d):
    if isinstance(d, dict) and d.get("error"):
        e = d["error"]
        return "ERROR: Facebook API: " + (e.get("message") if isinstance(e, dict) else str(e))
    return json.dumps(d, ensure_ascii=False, default=str)


async def _resolve_act(args, token):
    """Chuẩn hoá account_id thành 'act_<id>'; bỏ trống → lấy tài khoản quảng cáo đầu tiên."""
    aid = str((args or {}).get("account_id") or "").strip()
    if not aid:
        d = await _get("me/adaccounts", {"fields": "account_id", "limit": 1}, token)
        if isinstance(d, dict) and d.get("error"):
            return None, _fmt(d)
        data = (d or {}).get("data") or []
        if not data:
            return None, ("ERROR: Không thấy tài khoản quảng cáo nào. Kiểm tra bạn có quyền ads_read "
                          "và là admin của ad account.")
        aid = data[0].get("account_id") or ""
    return "act_" + aid.replace("act_", ""), None


async def _accounts(args, ctx):
    token = await _token()
    if not token:
        return "ERROR: " + (_check() or "chưa kết nối")
    d = await _get("me/adaccounts",
                   {"fields": "account_id,name,currency,account_status,amount_spent,balance", "limit": 100},
                   token)
    return _fmt(d)


async def _insights(args, ctx):
    token = await _token()
    if not token:
        return "ERROR: " + (_check() or "chưa kết nối")
    act, err = await _resolve_act(args, token)
    if err:
        return err
    args = args or {}
    params = {"fields": _INSIGHT_FIELDS, "level": (args.get("level") or "account")}
    since, until = str(args.get("since") or "").strip(), str(args.get("until") or "").strip()
    if since and until:
        params["time_range"] = json.dumps({"since": since, "until": until})
    else:
        params["date_preset"] = args.get("date_preset") or "last_7d"
    d = await _get(f"{act}/insights", params, token)
    return _fmt(d)


async def _campaigns(args, ctx):
    token = await _token()
    if not token:
        return "ERROR: " + (_check() or "chưa kết nối")
    act, err = await _resolve_act(args, token)
    if err:
        return err
    args = args or {}
    try:
        limit = max(1, min(200, int(args.get("limit") or 50)))
    except (TypeError, ValueError):
        limit = 50
    d = await _get(f"{act}/campaigns", {"fields": _CAMPAIGN_FIELDS, "limit": limit}, token)
    return _fmt(d)


async def _raw_get(args, ctx):
    token = await _token()
    if not token:
        return "ERROR: " + (_check() or "chưa kết nối")
    args = args or {}
    path = str(args.get("path") or "").strip().lstrip("/")
    if not path:
        return "ERROR: thiếu 'path' (vd 'me/adaccounts', 'act_123/insights')."
    params = args.get("params")
    if isinstance(params, str):
        try:
            params = json.loads(params)
        except Exception:
            params = {}
    if not isinstance(params, dict):
        params = {}
    d = await _get(path, params, token)
    return _fmt(d)


def register(ctx):
    ctx.register_tool(
        name="meta_ads_accounts", min_mode="readonly", check_fn=_check, handler=_accounts,
        description=("Liệt kê các tài khoản quảng cáo Facebook/Instagram của bạn (id, tên, tiền tệ, "
                     "trạng thái, tổng đã tiêu). Dùng đầu tiên để lấy account_id cho các tool khác."),
        schema={"type": "object", "properties": {}},
    )
    ctx.register_tool(
        name="meta_ads_insights", min_mode="readonly", check_fn=_check, handler=_insights,
        description=("Hiệu suất quảng cáo Facebook/Instagram: chi tiêu, hiển thị, click, CTR, CPC, CPM, "
                     "reach, hành động chuyển đổi. Bỏ trống account_id = tài khoản đầu tiên. Kỳ mặc định "
                     "7 ngày; đổi bằng date_preset (today/yesterday/last_7d/last_14d/last_30d/this_month/"
                     "last_month...) hoặc since+until (YYYY-MM-DD). level = account|campaign|ad."),
        schema={"type": "object", "properties": {
            "account_id": {"type": "string", "description": "act_<id> hoặc <id> (bỏ trống = tài khoản đầu tiên)"},
            "date_preset": {"type": "string", "description": "vd last_7d, last_30d, this_month"},
            "since": {"type": "string", "description": "Từ ngày YYYY-MM-DD (dùng kèm until)"},
            "until": {"type": "string", "description": "Đến ngày YYYY-MM-DD"},
            "level": {"type": "string", "description": "account | campaign | ad (mặc định account)"}}},
    )
    ctx.register_tool(
        name="meta_ads_campaigns", min_mode="readonly", check_fn=_check, handler=_campaigns,
        description=("Liệt kê chiến dịch quảng cáo của một tài khoản (tên, trạng thái, mục tiêu, ngân sách "
                     "ngày/trọn đời, thời gian chạy). Bỏ trống account_id = tài khoản đầu tiên."),
        schema={"type": "object", "properties": {
            "account_id": {"type": "string", "description": "act_<id> hoặc <id> (bỏ trống = tài khoản đầu tiên)"},
            "limit": {"type": "integer", "description": "Số chiến dịch tối đa (mặc định 50)"}}},
    )
    ctx.register_tool(
        name="meta_ads_get", min_mode="readonly", check_fn=_check, handler=_raw_get,
        description=("Gọi ĐỌC bất kỳ node/edge nào của Graph API Marketing (chỉ GET, không ghi). Dùng khi "
                     "3 tool trên chưa đủ. path = đường dẫn Graph (vd 'act_123/adsets', 'me/businesses'); "
                     "params = tham số truy vấn (object)."),
        schema={"type": "object", "properties": {
            "path": {"type": "string", "description": "Đường dẫn Graph API, vd 'act_123/adsets'"},
            "params": {"type": "object", "description": "Tham số query (vd {\"fields\":\"name,status\"})"}},
            "required": ["path"]},
    )
