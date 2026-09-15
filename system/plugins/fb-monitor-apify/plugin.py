"""Plugin bundled: theo dõi Trang/Nhóm CÔNG KHAI Facebook tìm bài viral (nhiều share) qua Apify.

Thay vì tự cào bằng cookie tài khoản cá nhân (rủi ro khoá + IP VPS bị chặn), gọi dịch vụ quét
Apify: nó lo proxy, né chặn bot, trả về bài kèm số share/react/bình luận. KHÔNG đụng tài khoản
Facebook của user nên không lo khoá; chạy tốt trên VPS 24/7. Chỉ đọc.

Actor mặc định (công khai, không cần cookie):
  - Trang/Fanpage: apify/facebook-posts-scraper
  - Nhóm CÔNG KHAI: apify/facebook-groups-scraper
Tự chọn actor theo URL ('/groups/' → actor nhóm, còn lại → actor trang). Nhóm KÍN cần actor
khác nhận cookie - để bước sau.

Cần token Apify của kết nối "facebook-monitor" (đăng ký free tại apify.com, lấy Personal API
token). Chi phí theo lượt quét (~2.6 USD/1000 bài với actor mặc định).
"""
from __future__ import annotations

import json
import re

APIFY = "https://api.apify.com/v2/acts"
CONNECTOR_ID = "facebook-monitor"
PAGES_ACTOR = "apify~facebook-posts-scraper"      # Trang/Fanpage công khai
GROUPS_ACTOR = "apify~facebook-groups-scraper"    # Nhóm CÔNG KHAI


def _secrets():
    try:
        import mcp_store
    except Exception:
        return {}
    cid = _connected_id()
    if not cid:
        return {}
    return mcp_store.connection_secrets(cid) or {}


def _connected_id():
    try:
        import mcp_store
    except Exception:
        return None
    for c in mcp_store.list_connections():
        if c.get("connector_id") == CONNECTOR_ID:
            return c["id"]
    return None


def _token():
    return (_secrets().get("apify_token") or "").strip() or None


def _check():
    if not _token():
        return ("Chưa kết nối Apify. Vào trang Kết nối, chọn 'Theo dõi Facebook (Apify)', đăng ký "
                "apify.com rồi dán Personal API token. Sau đó gọi lại tool này.")
    return None


async def _run(actor, token, input_obj):
    """Chạy actor Apify đồng bộ, trả list bài (dataset items) hoặc {'__error': ...}."""
    import httpx
    url = f"{APIFY}/{actor}/run-sync-get-dataset-items"
    try:
        async with httpx.AsyncClient(timeout=305) as c:      # server Apify giới hạn 300s
            r = await c.post(url, params={"token": token}, json=input_obj)
    except Exception as e:
        return {"__error": f"{type(e).__name__}: {e}"}
    try:
        data = r.json()
    except Exception:
        return {"__error": f"HTTP {r.status_code}: {r.text[:200]}"}
    if isinstance(data, dict) and data.get("error"):
        e = data["error"]
        return {"__error": str(e.get("message") if isinstance(e, dict) else e)}
    if not isinstance(data, list):
        return {"__error": f"Apify trả dữ liệu lạ: {str(data)[:200]}"}
    return data


def _num(post, *keys):
    for k in keys:
        v = post.get(k)
        if isinstance(v, bool):
            continue
        if isinstance(v, (int, float)):
            return int(v)
        if isinstance(v, str):
            s = v.replace(",", "").replace(".", "").strip()
            if s.isdigit():
                return int(s)
    return 0


def _shares(p):
    return _num(p, "shares", "shareCount", "sharesCount", "share_count", "reshareCount")


def _norm(p):
    author = p.get("author") or p.get("user")
    if isinstance(author, dict):
        author = author.get("name") or author.get("id")
    text = p.get("text") or p.get("message") or p.get("postText") or p.get("caption") or ""
    return {
        "text": (text or "")[:500],
        "url": p.get("url") or p.get("postUrl") or p.get("facebookUrl") or p.get("topLevelUrl") or "",
        "shares": _shares(p),
        "reactions": _num(p, "likes", "likesCount", "reactionsCount", "reactions", "totalReactionsCount"),
        "comments": _num(p, "comments", "commentsCount", "commentCount"),
        "time": str(p.get("time") or p.get("timestamp") or p.get("date") or p.get("publishedTime") or ""),
        "author": author or "",
        "source": p.get("groupTitle") or p.get("pageName") or p.get("groupUrl") or p.get("facebookId") or "",
    }


def _split_urls(val):
    if isinstance(val, list):
        return [str(u).strip() for u in val if str(u).strip()]
    if isinstance(val, str):
        return [u.strip() for u in re.split(r"[\s,]+", val) if u.strip()]
    return []


async def _monitor(args, ctx):
    token = _token()
    if not token:
        return "ERROR: " + (_check() or "chưa kết nối")
    args = args or {}
    urls = _split_urls(args.get("urls") or args.get("url"))
    if not urls:
        return "ERROR: thiếu 'urls' (danh sách link Trang/Nhóm CÔNG KHAI cần theo dõi)."
    try:
        limit = max(1, min(100, int(args.get("limit") or 20)))
    except (TypeError, ValueError):
        limit = 20
    try:
        min_shares = max(0, int(args.get("min_shares") or 0))
    except (TypeError, ValueError):
        min_shares = 0

    groups = [u for u in urls if "/groups/" in u]
    pages = [u for u in urls if "/groups/" not in u]
    posts, errors = [], []
    for actor, batch in ((PAGES_ACTOR, pages), (GROUPS_ACTOR, groups)):
        if not batch:
            continue
        data = await _run(actor, token, {"startUrls": [{"url": u} for u in batch], "resultsLimit": limit})
        if isinstance(data, dict) and data.get("__error"):
            errors.append(f"{actor}: {data['__error']}")
            continue
        for p in data:
            if not isinstance(p, dict):
                continue
            # Actor trả BẢN GHI LỖI trộn lẫn dataset (vd not_available khi Trang chặn xem
            # lúc chưa đăng nhập) - trước đây bị đếm thành "bài viết" rỗng 0 share khiến
            # kết quả trông như quét được mà thật ra không quét được gì.
            if p.get("error"):
                mo_ta = str(p.get("errorDescription") or "")[:120]
                errors.append(f"{p.get('url') or '?'}: {p.get('error')}"
                              + (f" - {mo_ta}" if mo_ta else ""))
                continue
            posts.append(_norm(p))

    posts = [p for p in posts if p["shares"] >= min_shares]
    posts.sort(key=lambda p: p["shares"], reverse=True)
    posts = posts[:50]
    if not posts and errors:
        return "ERROR: " + "; ".join(errors)
    return json.dumps({"count": len(posts), "posts": posts, "errors": errors}, ensure_ascii=False)


def register(ctx):
    ctx.register_tool(
        name="fb_monitor", min_mode="readonly", check_fn=_check, handler=_monitor,
        description=("Theo dõi Trang và Nhóm CÔNG KHAI Facebook, tìm bài nhiều share (viral) qua Apify. "
                     "urls = danh sách link Trang/Nhóm (chuỗi cách nhau hoặc mảng); URL chứa '/groups/' được "
                     "quét bằng actor nhóm, còn lại quét như Trang. limit = số bài/nguồn (mặc định 20); "
                     "min_shares = chỉ lấy bài từ ngần này share trở lên. Trả bài kèm share/react/bình luận, "
                     "sắp theo share giảm dần. KHÔNG dùng tài khoản cá nhân, chỉ đọc. Tốn phí Apify theo lượt. "
                     "LƯU Ý: Trang nào chặn xem feed khi chưa đăng nhập Facebook sẽ trả lỗi not_available - "
                     "đó là chặn từ phía Facebook, đổi Trang khác hoặc chờ bản hỗ trợ cookie."),
        schema={"type": "object", "properties": {
            "urls": {"type": "string", "description": "Link Trang/Nhóm công khai, cách nhau bởi dấu phẩy hoặc xuống dòng"},
            "limit": {"type": "integer", "description": "Số bài quét mỗi nguồn (mặc định 20)"},
            "min_shares": {"type": "integer", "description": "Chỉ lấy bài có số share >= giá trị này (mặc định 0)"}},
            "required": ["urls"]},
    )
