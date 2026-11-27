"""Plugin bundled: quản lý Trang/Fanpage Facebook qua Graph API.

Gọi THẲNG graph.facebook.com bằng user access token của kết nối "facebook-pages" (BYO app -
user tự tạo Facebook App, OAuth do oauth_mcp lo, token tự gia hạn ~60 ngày). Đọc danh sách Trang
qua /me/accounts, mỗi Trang có access_token RIÊNG - mọi thao tác trên một Trang (đăng bài, đọc/
trả lời bình luận) đều dùng token của chính Trang đó, KHÔNG dùng token cá nhân.

Tool đọc (fb_pages_list/fb_page_posts/fb_page_comments) = readonly. Tool ghi công khai
(fb_page_post/fb_page_photo/fb_page_album/fb_page_video/fb_page_edit/fb_page_reply) =
min_mode full → không bao giờ tự chạy ở chế độ suggest/auto, phải mức Toàn quyền + kết nối
đã ở mức đó.
Ảnh/video nhận URL http(s) hoặc file TRONG vault (sandbox như tool file); video upload đi
host graph-video riêng của Meta, Meta xử lý nền vài phút mới hiện bài.

One connection for everything (0.438.0, owner: "1 lần thôi cho gọn"): with no "facebook-pages"
connection, the tools use the Pages connected on the Facebook Messenger card. Those accounts already
hold a non-expiring Page token each, and Log in with Facebook asks for pages_manage_posts, so the
same login answers messages, comments and posts. A "facebook-pages" connection, when present, still
wins, so nothing changes for people who set that up.
"""
from __future__ import annotations

import json

GRAPH = "https://graph.facebook.com/v25.0"
# Upload video phải đi host riêng của Meta (graph thường từ chối file video)
GRAPH_VIDEO = "https://graph-video.facebook.com/v25.0"
CONNECTOR_ID = "facebook-pages"
# `_token()` returns this when the Pages come from the Messenger card instead of a user token.
MESSENGER = "messenger-card"


def _connected_ids():
    """Ids of every "facebook-pages" connection that is switched ON and signed in, in the order they were added.

    A connection turned off on the Connections page is never used (2026-11-21: it was, because only the sign-in was
    checked). Several connections are all used: `_pages` merges their Pages, see `_token`. Lazy imports so the plugin
    loads without the server modules."""
    try:
        import mcp_store
        import oauth_mcp
    except Exception:
        return []
    return [c["id"] for c in mcp_store.list_connections()
            if c.get("connector_id") == CONNECTOR_ID and c.get("enabled", True)
            and oauth_mcp.status(c["id"]).get("connected")]


def _connected_id():
    """The first usable "facebook-pages" connection, or None."""
    ids = _connected_ids()
    return ids[0] if ids else None


def _messenger_pages():
    """Pages connected on the Facebook Messenger card: [{id, name, category, access_token, tasks}].
    Their stored token is already a Page token, so no /me/accounts call is needed."""
    try:
        import channel_accounts
        import messenger_bot
    except Exception:
        return []
    out = []
    try:
        for a in channel_accounts.list_accounts(channel="messenger"):
            cr = messenger_bot.split_credentials(channel_accounts.get_token(a.get("id", "")))
            if cr.get("page_id") and cr.get("access_token"):
                out.append({"id": cr["page_id"], "access_token": cr["access_token"], "category": "", "tasks": None,
                            "name": (a.get("meta") or {}).get("bot_name") or a.get("label") or cr["page_id"]})
    except Exception:
        return []
    return out


def _check():
    if not _connected_id() and not _messenger_pages():
        return ("Chưa nối Fanpage nào. Vào trang Kết nối, thẻ 'Facebook Messenger', bấm Kết nối rồi Đăng nhập "
                "Facebook và tick Trang (một lần dùng cho cả tin nhắn, bình luận và đăng bài). "
                "Sau đó gọi lại tool này.")
    return None


async def _token():
    """What `_pages` reads the Pages with: one user token (a single connection, as before), a tuple of user tokens
    (several connections: each sign-in sees its own Pages, and the tools work on all of them), `MESSENGER`, or None."""
    ids = _connected_ids()
    if not ids:
        return MESSENGER if _messenger_pages() else None
    import oauth_mcp
    tokens = []
    for cid in ids:
        hdr = await oauth_mcp.auth_headers(cid)      # tự refresh token ~60 ngày khi sắp hết hạn
        tok = (hdr.get("Authorization", "") or "").replace("Bearer ", "").strip()
        if tok and tok not in tokens:
            tokens.append(tok)
    if not tokens:
        return None
    return tokens[0] if len(tokens) == 1 else tuple(tokens)


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


async def _post(path, data, token):
    import httpx
    try:
        async with httpx.AsyncClient(timeout=30) as c:
            r = await c.post(f"{GRAPH}/{str(path).lstrip('/')}",
                             data={**(data or {}), "access_token": token})
        try:
            return r.json()
        except Exception:
            return {"error": {"message": f"HTTP {r.status_code}: {r.text[:200]}"}}
    except Exception as e:
        return {"error": {"message": f"{type(e).__name__}: {e}"}}


async def _delete(path, token):
    import httpx
    try:
        async with httpx.AsyncClient(timeout=30) as c:
            r = await c.delete(f"{GRAPH}/{str(path).lstrip('/')}", params={"access_token": token})
        try:
            return r.json()
        except Exception:
            return {"error": {"message": f"HTTP {r.status_code}: {r.text[:200]}"}}
    except Exception as e:
        return {"error": {"message": f"{type(e).__name__}: {e}"}}


def _fmt(d):
    from graph_output import sanitize_graph_output
    d = sanitize_graph_output(d)
    if isinstance(d, dict) and d.get("error"):
        e = d["error"]
        msg = e.get("message") if isinstance(e, dict) else str(e)
        out = "ERROR: Facebook API: " + str(msg)
        if "pages_manage_posts" in str(msg) or (isinstance(e, dict) and str(e.get("code")) in ("10", "200")):
            # A Page connected on the Messenger card before 0.438.0 has no posting permission yet.
            out += (" (Gợi ý: Trang nối trước bản 0.438.0 chưa có quyền đăng bài. Vào trang Kết nối, thẻ "
                    "Facebook Messenger, bấm Kết nối, Đăng nhập Facebook lại và đồng ý quyền pages_manage_posts.)")
        return out
    return json.dumps(d, ensure_ascii=False, default=str)


# Scheduled posts (23/11/2026, owner: a post must sit in the Page's own Meta Business Suite calendar, not in another
# tool's queue). Meta takes `published=false` + `scheduled_publish_time` on /feed; photos of such a post are uploaded
# with `temporary=true` (graph-api/reference/page/photos). Meta wants the time at least 10 minutes ahead. Its upper
# bound reads differently across Meta's own pages (30 days, 75 days, 6 months), so it is left to Meta's own error.
MIN_LEAD_S = 10 * 60
_LEAD_MARGIN_S = 60   # the request itself takes a moment: 10 minutes sharp would be refused on arrival
DEFAULT_TZ = "Asia/Ho_Chi_Minh"


def _owner_tz():
    """The owner's timezone from Settings (localefmt.tz, which already falls back to the default). Outside the server
    process, the default zone by name."""
    try:
        import localefmt
        return localefmt.tz()
    except Exception:
        from zoneinfo import ZoneInfo
        return ZoneInfo(DEFAULT_TZ)


def _local_text(epoch):
    from datetime import datetime
    try:
        return datetime.fromtimestamp(float(epoch), _owner_tz()).strftime("%H:%M %d/%m/%Y")
    except (TypeError, ValueError, OverflowError, OSError):
        return ""


def _parse_schedule(args, now=None):
    """`schedule_at` of a publishing tool -> (epoch seconds, None), (None, None) when absent, or (None, "ERROR: ...").

    Takes a Unix time (seconds or milliseconds) or an ISO date and time ("2026-11-25T09:00", "2026-11-25 09:00",
    with or without an offset). A time with no offset is read in the owner's timezone, the clock they think in."""
    import time
    from datetime import datetime
    raw = (args or {}).get("schedule_at")
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        return None, None
    now = time.time() if now is None else now
    ts = None
    if isinstance(raw, (int, float)) and not isinstance(raw, bool):
        ts = float(raw)
    else:
        txt = str(raw).strip()
        if txt.replace(".", "", 1).isdigit():
            ts = float(txt)
        else:
            try:
                dt = datetime.fromisoformat(txt.replace("Z", "+00:00").replace("/", "-"))
            except ValueError:
                return None, ("ERROR: không hiểu giờ hẹn '" + txt[:40] + "'. Dùng dạng 2026-11-25T09:00 (giờ theo "
                              "múi giờ của bạn) hoặc Unix time.")
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=_owner_tz())
            ts = dt.timestamp()
    if ts > 1e12:   # milliseconds
        ts /= 1000.0
    ts = int(ts)
    if ts < now + MIN_LEAD_S + _LEAD_MARGIN_S:
        return None, ("ERROR: Facebook chỉ nhận giờ hẹn cách bây giờ ít nhất 10 phút. Giờ vừa đưa: "
                      + (_local_text(ts) or str(ts)) + ", bây giờ: " + _local_text(now) + ". Chọn giờ muộn hơn, "
                      "hoặc bỏ schedule_at để đăng ngay.")
    return ts, None


def _schedule_fields(ts):
    """The /feed fields that make a post wait for `ts` in the Page's own scheduled list."""
    return {"published": "false", "scheduled_publish_time": str(int(ts)), "unpublished_content_type": "SCHEDULED"}


def _scheduled_result(out, ts):
    """Add what the owner checks against to a publishing tool's answer."""
    if ts:
        out.update({"scheduled": True, "scheduled_publish_time": int(ts), "scheduled_for": _local_text(ts),
                    "note": ("Bài đang chờ trong lịch của Trang (Meta Business Suite > Lịch), chưa hiện công khai. "
                             "Xem lại bằng fb_page_scheduled; huỷ bằng fb_page_delete với post_id này.")})
    return out


async def _pages(user_token):
    """Danh sách Trang user quản lý, mỗi Trang kèm access_token RIÊNG. Trả (list, err).

    `user_token` may be a tuple (several "facebook-pages" connections, see `_token`): the Pages of every sign-in,
    each once. Before 2026-11-21 only the first connection was ever read, so a Page of the second one could not be
    reached. A sign-in that fails does not hide the Pages of the others; the error shows only when none answers."""
    if user_token == MESSENGER:
        return _messenger_pages(), None
    if isinstance(user_token, (tuple, list)):
        merged, seen, first_err = [], set(), None
        for tok in user_token:
            pages, err = await _pages(tok)
            if err:
                first_err = first_err or err
                continue
            for p in pages or []:
                if str(p.get("id")) not in seen:
                    seen.add(str(p.get("id")))
                    merged.append(p)
        return (None, first_err) if first_err and not merged else (merged, None)
    d = await _get("me/accounts", {"fields": "id,name,category,access_token,tasks", "limit": 200}, user_token)
    if isinstance(d, dict) and d.get("error"):
        return None, _fmt(d)
    return (d or {}).get("data") or [], None


async def _resolve_page(args, user_token):
    """Chọn Trang thao tác. Trả (page_id, page_token, page_name, err).
    - page_id / page (tên) trong args → khớp; nếu bỏ trống mà chỉ có 1 Trang → tự lấy;
    - nhiều Trang mà không chỉ rõ → lỗi kèm danh sách Trang để user chọn."""
    pages, err = await _pages(user_token)
    if err:
        return None, None, None, err
    if not pages:
        return None, None, None, ("ERROR: Không thấy Trang nào bạn quản lý. Kiểm tra: bạn là Admin của Trang, "
                                  "và khi đăng nhập Facebook đã TICK chọn Trang đó cho app.")
    ref = str((args or {}).get("page_id") or (args or {}).get("page") or "").strip()
    if ref:
        rl = ref.lower()
        for p in pages:
            if str(p.get("id")) == ref or rl in str(p.get("name", "")).lower():
                return p.get("id"), p.get("access_token"), p.get("name"), None
        avail = ", ".join(f"{p.get('name')} ({p.get('id')})" for p in pages)
        return None, None, None, f"ERROR: Không khớp Trang '{ref}'. Trang bạn có: {avail}"
    if len(pages) == 1:
        p = pages[0]
        return p.get("id"), p.get("access_token"), p.get("name"), None
    avail = ", ".join(f"{p.get('name')} ({p.get('id')})" for p in pages)
    return None, None, None, f"ERROR: Bạn có nhiều Trang, cần chỉ rõ page_id hoặc page (tên). Trang: {avail}"


async def _list(args, ctx):
    token = await _token()
    if not token:
        return "ERROR: " + (_check() or "chưa kết nối")
    pages, err = await _pages(token)
    if err:
        return err
    # KHÔNG lộ access_token của Trang ra output.
    safe = [{"id": p.get("id"), "name": p.get("name"), "category": p.get("category"),
             "tasks": p.get("tasks")} for p in pages]
    return json.dumps(safe, ensure_ascii=False, default=str)


async def _posts(args, ctx):
    token = await _token()
    if not token:
        return "ERROR: " + (_check() or "chưa kết nối")
    pid, ptok, pname, err = await _resolve_page(args, token)
    if err:
        return err
    args = args or {}
    try:
        limit = max(1, min(100, int(args.get("limit") or 10)))
    except (TypeError, ValueError):
        limit = 10
    d = await _get(f"{pid}/feed",
                   {"fields": "id,message,story,created_time,permalink_url,comments.summary(true).limit(0)",
                    "limit": limit}, ptok)
    return _fmt(d)


async def _comments(args, ctx):
    token = await _token()
    if not token:
        return "ERROR: " + (_check() or "chưa kết nối")
    args = args or {}
    obj = str(args.get("post_id") or args.get("object_id") or "").strip()
    if not obj:
        return "ERROR: thiếu 'post_id' (id bài cần đọc bình luận; lấy từ fb_page_posts)."
    # post_id dạng {pageid}_{postid}: tự suy Trang khi user không chỉ rõ.
    if not (args.get("page_id") or args.get("page")) and "_" in obj:
        args = {**args, "page_id": obj.split("_", 1)[0]}
    pid, ptok, pname, err = await _resolve_page(args, token)
    if err:
        return err
    try:
        limit = max(1, min(100, int(args.get("limit") or 25)))
    except (TypeError, ValueError):
        limit = 25
    d = await _get(f"{obj}/comments",
                   {"fields": "id,from,message,created_time,like_count",
                    "order": "reverse_chronological", "limit": limit}, ptok)
    return _fmt(d)


# ---- Page and post insights (issue #1879, 2026-11-27) ----------------------------------------------------------
# The Messenger card has asked for `read_insights` since 0.560.0 (an optional tick), but no tool read it, so a social
# report could not say how a Page or a post did. Read only, through the same Page token as every tool here; metric names
# Meta deprecates over time (the Nov 2025 "views" switch), so a refused metric is retried one by one and the rest still
# comes back with a note naming what Meta refused.
PAGE_METRICS = ("page_media_view", "page_total_media_view_unique", "page_post_engagements", "page_follows")
POST_METRICS = ("post_media_view", "post_total_media_view_unique", "post_clicks", "post_reactions_by_type_total")
INSIGHT_PERIODS = ("day", "week", "days_28", "lifetime")
MAX_METRICS = 10
MAX_RANGE_DAYS = 90
_METRIC_RE = __import__("re").compile(r"^[a-z][a-z0-9_]{1,63}$")
_DATE_RE = __import__("re").compile(r"^\d{4}-\d{2}-\d{2}$")
INSIGHTS_HINT = ("Hint: the Page needs the read_insights permission. Tell the owner: Connections page, Facebook Messenger "
                 "card, Connect, tick \"Read post insights\", then Log in with Facebook again.")


def _insight_metrics(args, default):
    raw = (args or {}).get("metrics")
    if isinstance(raw, str):
        raw = [x.strip() for x in raw.split(",")]
    picked = [str(m).strip().lower() for m in (raw or []) if str(m).strip()]
    bad = [m for m in picked if not _METRIC_RE.match(m)]
    if bad:
        return None, "ERROR: invalid metric name: " + ", ".join(bad[:5])
    picked = list(dict.fromkeys(picked))[:MAX_METRICS]
    return (picked or list(default)), None


def _insight_range(args):
    """(since, until) as YYYY-MM-DD, default the last 28 days. Error text when the dates cannot be read."""
    import datetime as _dt
    a = args or {}
    today = _dt.date.today()
    try:
        until = _dt.date.fromisoformat(str(a.get("until"))) if a.get("until") else today
        since = _dt.date.fromisoformat(str(a.get("since"))) if a.get("since") else until - _dt.timedelta(days=28)
    except ValueError:
        return None, None, "ERROR: since and until must be YYYY-MM-DD."
    if since > until:
        return None, None, "ERROR: since must be before until."
    if (until - since).days > MAX_RANGE_DAYS:
        return None, None, f"ERROR: Meta returns at most {MAX_RANGE_DAYS} days per call; split the range."
    return since.isoformat(), until.isoformat(), None


def _compact_insights(d):
    out = []
    for m in (d or {}).get("data") or []:
        if not isinstance(m, dict):
            continue
        out.append({"metric": m.get("name"), "period": m.get("period"), "title": m.get("title"),
                    "values": [{"end_time": v.get("end_time"), "value": v.get("value")}
                               for v in (m.get("values") or []) if isinstance(v, dict)]})
    return out


async def _read_insights(obj, metrics, params, token):
    """GET <obj>/insights for every metric; a refused batch is retried metric by metric. Returns (rows, refused, err)."""
    d = await _get(f"{obj}/insights", {**params, "metric": ",".join(metrics)}, token)
    if not (isinstance(d, dict) and d.get("error")):
        return _compact_insights(d), [], None
    if len(metrics) == 1:
        return [], [], d
    rows, refused, last_err = [], [], d
    for m in metrics:
        one = await _get(f"{obj}/insights", {**params, "metric": m}, token)
        if isinstance(one, dict) and one.get("error"):
            refused.append(m)
            last_err = one
        else:
            rows.extend(_compact_insights(one))
    return rows, refused, (None if rows else last_err)


def _insights_error(d):
    out = _fmt(d)
    e = (d or {}).get("error") if isinstance(d, dict) else None
    code = str(e.get("code")) if isinstance(e, dict) else ""
    if code in ("10", "200") or "read_insights" in out or "permission" in out.lower():
        out = out.split(" (Gợi ý:")[0] + " (" + INSIGHTS_HINT + ")"
    return out


async def _insights(args, ctx):
    token = await _token()
    if not token:
        return "ERROR: " + (_check() or "chưa kết nối")
    args = dict(args or {})
    post = str(args.get("post_id") or "").strip()
    if post and not (args.get("page_id") or args.get("page")) and "_" in post:
        args["page_id"] = post.split("_", 1)[0]
    metrics, err = _insight_metrics(args, POST_METRICS if post else PAGE_METRICS)
    if err:
        return err
    pid, ptok, pname, err = await _resolve_page(args, token)
    if err:
        return err
    if post:
        params = {"period": "lifetime"}
    else:
        period = str(args.get("period") or "day").strip().lower()
        if period not in INSIGHT_PERIODS:
            return "ERROR: period must be one of: " + ", ".join(INSIGHT_PERIODS)
        since, until, err = _insight_range(args)
        if err:
            return err
        params = {"period": period, "since": since, "until": until}
    rows, refused, err_d = await _read_insights(post or pid, metrics, params, ptok)
    if err_d is not None:
        return _insights_error(err_d)
    from graph_output import sanitize_graph_output
    out = {"page": {"id": pid, "name": pname}, "object": post or pid, **{k: v for k, v in params.items()},
           "metrics": rows}
    if refused:
        out["refused_metrics"] = refused
        out["note"] = ("Meta refused these metrics (deprecated, misspelled, or not available for this object); "
                       "the other metrics are valid.")
    return json.dumps(sanitize_graph_output(out), ensure_ascii=False, default=str)


async def _publish(args, ctx):
    token = await _token()
    if not token:
        return "ERROR: " + (_check() or "chưa kết nối")
    args = args or {}
    msg = str(args.get("message") or "").strip()
    link = str(args.get("link") or "").strip()
    if not msg and not link:
        return "ERROR: cần 'message' (nội dung bài) hoặc 'link'."
    ts, serr = _parse_schedule(args)
    if serr:
        return serr
    pid, ptok, pname, err = await _resolve_page(args, token)
    if err:
        return err
    data = {}
    if msg:
        data["message"] = msg
    if link:
        data["link"] = link
    if ts:
        data.update(_schedule_fields(ts))
    d = await _post(f"{pid}/feed", data, ptok)
    if isinstance(d, dict) and d.get("error"):
        return _fmt(d)
    return json.dumps(_scheduled_result({"ok": True, "page": pname,
                                         "post_id": d.get("id") if isinstance(d, dict) else None}, ts),
                      ensure_ascii=False, default=str)


def _media_roots(cctx):
    """Các gốc được phép đọc media: (1) vault đang làm việc, (2) vùng nhận file
    STATE_DIR/.staging - nơi ảnh/video user dán vào khung chat dashboard rơi xuống.
    File trong staging là file CHÍNH CHỦ vừa gửi nên đăng được, không phải mở sandbox bừa.
    (File gửi qua Telegram đã rơi sẵn vào <vault>/inbox/telegram nên thuộc gốc 1.)"""
    from pathlib import Path
    roots = []
    root = getattr(cctx, "vault_root", None)
    if root:
        try:
            roots.append(Path(root).resolve())
        except OSError:
            pass
    try:
        from config import STATE_DIR
        roots.append((Path(STATE_DIR) / ".staging").resolve())
    except Exception:
        pass
    return roots


def _resolve_media(ref, cctx):
    """'photo'/'video' nhận URL http(s) HOẶC đường dẫn file trong vault / vùng nhận file
    của chat (tương đối thử lần lượt từng gốc). Trả (url, path, err) - đúng một trong
    url/path có giá trị. File NGOÀI các gốc cho phép thì từ chối - plugin chạy full quyền
    nhưng không vì thế mà cho đăng file tuỳ ý trên máy lên mạng."""
    from pathlib import Path
    ref = str(ref or "").strip()
    if not ref:
        return None, None, "ERROR: thiếu đường dẫn file hoặc URL http(s) của media."
    if ref.startswith("http://") or ref.startswith("https://"):
        return ref, None, None
    roots = _media_roots(cctx)
    if not roots:
        return None, None, "ERROR: không xác định được vault/vùng nhận file để tìm media."
    try:
        if Path(ref).is_absolute():
            rp = Path(ref).resolve()
            if any(str(rp).startswith(str(r)) for r in roots) and rp.is_file():
                return None, rp, None
        else:
            for r in roots:
                cand = (r / ref).resolve()
                if str(cand).startswith(str(r)) and cand.is_file():
                    return None, cand, None
    except OSError as e:
        return None, None, f"ERROR: không đọc được đường dẫn ({type(e).__name__})."
    return None, None, (f"ERROR: không thấy '{ref}' trong vault hay vùng nhận file của chat. "
                        "File phải nằm trong vault, hoặc là file vừa gửi qua khung chat/Telegram.")


async def _post_multipart(path_in_graph, files, data, token, base=GRAPH, timeout=900):
    """POST multipart with several files: files = {field name: path}. Empty files sends data
    only (e.g. a video by file_url plus its cover image)."""
    import mimetypes
    import httpx
    from contextlib import ExitStack
    from pathlib import Path
    try:
        with ExitStack() as stack:
            parts = {}
            for field, fp in (files or {}).items():
                mime = mimetypes.guess_type(str(fp))[0] or "application/octet-stream"
                parts[field] = (Path(fp).name, stack.enter_context(open(fp, "rb")), mime)
            async with httpx.AsyncClient(timeout=timeout) as c:
                r = await c.post(f"{base}/{str(path_in_graph).lstrip('/')}",
                                 data={**(data or {}), "access_token": token}, files=parts or None)
        try:
            return r.json()
        except Exception:
            return {"error": {"message": f"HTTP {r.status_code}: {r.text[:200]}"}}
    except Exception as e:
        return {"error": {"message": f"{type(e).__name__}: {e}"}}


async def _post_file(path_in_graph, file_path, data, token, base=GRAPH, timeout=900):
    """POST multipart (upload file thật). Video đi base GRAPH_VIDEO, timeout dài."""
    return await _post_multipart(path_in_graph, {"source": file_path}, data, token,
                                 base=base, timeout=timeout)


async def _publish_photo(args, cctx):
    token = await _token()
    if not token:
        return "ERROR: " + (_check() or "chưa kết nối")
    args = args or {}
    url, path, err = _resolve_media(args.get("photo") or args.get("image") or "", cctx)
    if err:
        return err
    ts, serr = _parse_schedule(args)
    if serr:
        return serr
    pid, ptok, pname, perr = await _resolve_page(args, token)
    if perr:
        return perr
    caption = str(args.get("message") or args.get("caption") or "").strip()
    if ts:
        # A scheduled photo is a /feed post with the photo attached, like an album of one (Meta's documented path).
        mid, merr = await _upload_unpublished(pid, ptok, url, path, temporary=True)
        if merr:
            return merr
        return await _feed_with_media(pid, ptok, pname, [mid], caption, ts)
    data = {"caption": caption} if caption else {}
    if url:
        d = await _post(f"{pid}/photos", {**data, "url": url}, ptok)
    else:
        d = await _post_file(f"{pid}/photos", path, data, ptok)
    if isinstance(d, dict) and d.get("error"):
        return _fmt(d)
    return json.dumps({"ok": True, "page": pname,
                       "photo_id": d.get("id") if isinstance(d, dict) else None,
                       "post_id": d.get("post_id") if isinstance(d, dict) else None},
                      ensure_ascii=False, default=str)


# Cover image: Meta caps it at 10MB (graph-api/reference/video/thumbnails). Images only.
THUMB_MAX_BYTES = 10 * 1024 * 1024
THUMB_EXTS = (".jpg", ".jpeg", ".png")
RUPLOAD = "https://rupload.facebook.com/video-upload/" + GRAPH.rsplit("/", 1)[-1]   # same API version as GRAPH
RUPLOAD_CHUNK = 1024 * 1024


async def _file_chunks(path, size=RUPLOAD_CHUNK):
    """Read a video in 1MB pieces off the event loop, so a 1GB Reel never sits in memory whole."""
    import asyncio
    with open(path, "rb") as f:
        while True:
            piece = await asyncio.to_thread(f.read, size)
            if not piece:
                break
            yield piece


def _resolve_thumb(ref, cctx):
    """Video cover: an image file in the vault / chat drop zone (same sandbox as media).
    Returns (path, err); an empty ref gives (None, None)."""
    ref = str(ref or "").strip()
    if not ref:
        return None, None
    if ref.startswith("http://") or ref.startswith("https://"):
        return None, ("ERROR: thumbnail phải là file ảnh trong vault (Facebook nhận ảnh bìa dạng file "
                      "tải lên, không nhận link).")
    _u, path, err = _resolve_media(ref, cctx)
    if err:
        return None, err
    if path.suffix.lower() not in THUMB_EXTS:
        return None, "ERROR: thumbnail phải là ảnh .jpg hoặc .png."
    if path.stat().st_size > THUMB_MAX_BYTES:
        return None, "ERROR: thumbnail quá 10MB (giới hạn của Facebook). Hãy xuất .jpg nhẹ hơn."
    return path, None


async def _rupload(video_id, path, url, token):
    """Reels step 2: push the video to rupload.facebook.com (binary body or file_url header)."""
    import httpx
    headers = {"Authorization": f"OAuth {token}"}
    try:
        async with httpx.AsyncClient(timeout=900) as c:
            if url:
                r = await c.post(f"{RUPLOAD}/{video_id}", headers={**headers, "file_url": url})
            else:
                size = path.stat().st_size
                r = await c.post(f"{RUPLOAD}/{video_id}", content=_file_chunks(path),
                                 headers={**headers, "offset": "0", "file_size": str(size),
                                          "Content-Length": str(size)})
        try:
            return r.json()
        except Exception:
            return {"error": {"message": f"HTTP {r.status_code}: {r.text[:200]}"}}
    except Exception as e:
        return {"error": {"message": f"{type(e).__name__}: {e}"}}


async def _set_thumb(video_id, thumb, ptok):
    """Preferred cover for a video that already belongs to the Page:
    POST {video}/thumbnails with source + is_preferred. Returns None on success, else the error."""
    d = await _post_file(f"{video_id}/thumbnails", thumb, {"is_preferred": "true"}, ptok, base=GRAPH)
    if isinstance(d, dict) and d.get("error"):
        return _fmt(d)
    return None


async def _publish_reel(pid, ptok, pname, url, path, thumb, desc, title):
    """Publish a Reel: start, rupload, cover, finish PUBLISHED (video-api/guides/reels-publishing)."""
    d = await _post(f"{pid}/video_reels", {"upload_phase": "start"}, ptok)
    if isinstance(d, dict) and d.get("error"):
        return _fmt(d)
    vid = (d or {}).get("video_id")
    if not vid:
        return "ERROR: Facebook không trả video_id khi mở phiên tải Reel."
    up = await _rupload(vid, path, url, ptok)
    if not isinstance(up, dict) or up.get("error") or not up.get("success"):
        return _fmt(up if isinstance(up, dict) and up.get("error")
                    else {"error": {"message": f"tải video Reel lên lỗi: {up}"}})
    thumb_err = await _set_thumb(vid, thumb, ptok) if thumb else None
    fin = {"upload_phase": "finish", "video_id": vid, "video_state": "PUBLISHED"}
    if desc:
        fin["description"] = desc
    if title:
        fin["title"] = title
    d = await _post(f"{pid}/video_reels", fin, ptok)
    if isinstance(d, dict) and d.get("error"):
        return _fmt(d)
    if thumb and thumb_err:
        # The first try can miss while the video is still processing; retry once after publishing.
        thumb_err = await _set_thumb(vid, thumb, ptok)
    out = {"ok": True, "page": pname, "kind": "reel", "video_id": vid,
           "note": "Reel xử lý nền vài phút rồi mới hiện trên Trang."}
    if thumb:
        out["thumbnail"] = "đã gắn" if not thumb_err else f"chưa gắn được: {thumb_err}"
    return json.dumps(out, ensure_ascii=False, default=str)


async def _publish_video(args, cctx):
    token = await _token()
    if not token:
        return "ERROR: " + (_check() or "chưa kết nối")
    args = args or {}
    url, path, err = _resolve_media(args.get("video") or "", cctx)
    if err:
        return err
    thumb, terr = _resolve_thumb(args.get("thumbnail") or args.get("thumb") or "", cctx)
    if terr:
        return terr
    pid, ptok, pname, perr = await _resolve_page(args, token)
    if perr:
        return perr
    desc = str(args.get("message") or args.get("description") or "").strip()
    title = str(args.get("title") or "").strip()
    if args.get("reel") in (True, "true", "1", 1):
        return await _publish_reel(pid, ptok, pname, url, path, thumb, desc, title)
    data = {}
    if desc:
        data["description"] = desc
    if title:
        data["title"] = title
    if url and thumb:
        d = await _post_multipart(f"{pid}/videos", {"thumb": thumb}, {**data, "file_url": url},
                                  ptok, base=GRAPH_VIDEO)
    elif url:
        d = await _post(f"{pid}/videos", {**data, "file_url": url}, ptok)
    elif thumb:
        d = await _post_multipart(f"{pid}/videos", {"source": path, "thumb": thumb}, data,
                                  ptok, base=GRAPH_VIDEO)
    else:
        d = await _post_file(f"{pid}/videos", path, data, ptok, base=GRAPH_VIDEO)
    if isinstance(d, dict) and d.get("error"):
        return _fmt(d)
    out = {"ok": True, "page": pname,
           "video_id": d.get("id") if isinstance(d, dict) else None,
           "note": "Video Facebook xử lý nền vài phút rồi mới hiện trên Trang."}
    if thumb:
        out["thumbnail"] = "đã gửi kèm"
    return json.dumps(out, ensure_ascii=False, default=str)


async def _publish_album(args, cctx):
    """Đăng NHIỀU ảnh thành một bài (album): up từng ảnh published=false lấy id,
    rồi gom vào MỘT bài /feed qua attached_media. Meta cho tối đa 10 ảnh một bài."""
    token = await _token()
    if not token:
        return "ERROR: " + (_check() or "chưa kết nối")
    args = args or {}
    photos = args.get("photos") or []
    if isinstance(photos, str):   # model hay đưa chuỗi cách nhau dấu phẩy
        photos = [p.strip() for p in photos.split(",") if p.strip()]
    if len(photos) < 2:
        return "ERROR: album cần ít nhất 2 ảnh trong 'photos' (1 ảnh thì dùng fb_page_photo)."
    if len(photos) > 10:
        return f"ERROR: Meta cho tối đa 10 ảnh một bài, đang có {len(photos)}. Bớt lại hoặc chia 2 bài."
    ts, serr = _parse_schedule(args)
    if serr:
        return serr
    pid, ptok, pname, perr = await _resolve_page(args, token)
    if perr:
        return perr
    media_ids = []
    for i, ref in enumerate(photos):
        url, path, err = _resolve_media(ref, cctx)
        if err:
            return f"{err} (ảnh thứ {i + 1}: {str(ref)[:80]})"
        mid, merr = await _upload_unpublished(pid, ptok, url, path, temporary=bool(ts))
        if merr:
            return merr + f" (ảnh thứ {i + 1})"
        media_ids.append(mid)
    return await _feed_with_media(pid, ptok, pname, media_ids, str(args.get("message") or "").strip(), ts)


async def _upload_unpublished(pid, ptok, url, path, temporary=False):
    """Upload one photo without publishing it -> (photo id, None) or (None, "ERROR: ..."). `temporary=True` for a
    photo of a scheduled post: Meta requires it there, and drops an unused one after about 24 hours."""
    data = {"published": "false"}
    if temporary:
        data["temporary"] = "true"
    if url:
        d = await _post(f"{pid}/photos", {**data, "url": url}, ptok)
    else:
        d = await _post_file(f"{pid}/photos", path, data, ptok)
    if isinstance(d, dict) and d.get("error"):
        return None, _fmt(d)
    mid = (d or {}).get("id") if isinstance(d, dict) else None
    if not mid:
        return None, "ERROR: Facebook không trả id cho ảnh."
    return mid, None


async def _feed_with_media(pid, ptok, pname, media_ids, msg, ts=None):
    """ONE /feed post carrying the uploaded photos, published now or waiting for `ts`."""
    data = {}
    if msg:
        data["message"] = msg
    for i, mid in enumerate(media_ids):
        data[f"attached_media[{i}]"] = json.dumps({"media_fbid": mid})
    if ts:
        data.update(_schedule_fields(ts))
    d = await _post(f"{pid}/feed", data, ptok)
    if isinstance(d, dict) and d.get("error"):
        return _fmt(d)
    return json.dumps(_scheduled_result({"ok": True, "page": pname, "photos": len(media_ids),
                                         "post_id": d.get("id") if isinstance(d, dict) else None}, ts),
                      ensure_ascii=False, default=str)


async def _scheduled(args, ctx):
    """Posts waiting in the Page's own scheduled list (Meta Business Suite calendar), soonest first."""
    token = await _token()
    if not token:
        return "ERROR: " + (_check() or "chưa kết nối")
    pid, ptok, pname, err = await _resolve_page(args, token)
    if err:
        return err
    args = args or {}
    try:
        limit = max(1, min(100, int(args.get("limit") or 25)))
    except (TypeError, ValueError):
        limit = 25
    d = await _get(f"{pid}/scheduled_posts",
                   {"fields": "id,message,scheduled_publish_time,created_time,permalink_url", "limit": limit}, ptok)
    if isinstance(d, dict) and d.get("error"):
        return _fmt(d)
    rows = []
    for p in (d or {}).get("data") or []:
        if not isinstance(p, dict):
            continue
        row = dict(p)
        when = p.get("scheduled_publish_time")
        try:
            row["scheduled_publish_time"] = int(float(when))
            row["scheduled_for"] = _local_text(when)
        except (TypeError, ValueError):
            pass
        rows.append(row)
    rows.sort(key=lambda r: r.get("scheduled_publish_time") if isinstance(r.get("scheduled_publish_time"), int)
              else 0)
    return _fmt({"page": pname, "count": len(rows), "data": rows})


async def _edit_post(args, cctx):
    """Sửa NỘI DUNG CHỮ của bài đã đăng. Meta chỉ cho đổi message - không đổi được
    ảnh/video đã đính kèm (muốn đổi media thì xoá đăng lại, Javis không tự xoá)."""
    token = await _token()
    if not token:
        return "ERROR: " + (_check() or "chưa kết nối")
    args = args or {}
    post_id = str(args.get("post_id") or "").strip()
    msg = str(args.get("message") or "").strip()
    if not post_id:
        return "ERROR: thiếu 'post_id' (id bài cần sửa, lấy từ fb_page_posts)."
    if not msg:
        return "ERROR: thiếu 'message' (nội dung MỚI thay cho nội dung cũ)."
    # post_id dạng {pageid}_{postid}: tự suy Trang như fb_page_comments
    if not (args.get("page_id") or args.get("page")) and "_" in post_id:
        args = {**args, "page_id": post_id.split("_", 1)[0]}
    pid, ptok, pname, err = await _resolve_page(args, token)
    if err:
        return err
    d = await _post(post_id, {"message": msg}, ptok)
    if isinstance(d, dict) and d.get("error"):
        return _fmt(d)
    ok = bool(isinstance(d, dict) and (d.get("success") is True or d.get("id")))
    return json.dumps({"ok": ok, "page": pname, "post_id": post_id,
                       "note": "" if ok else "Facebook trả về khác thường: " + str(d)[:120]},
                      ensure_ascii=False, default=str)


async def _delete_post(args, cctx):
    """XOÁ HẲN một bài đã đăng trên Trang. Meta không có thùng rác cho bài Trang nên
    KHÔNG khôi phục được. Trước khi xoá có đọc lại bài, vừa để chắc đúng bài vừa giữ
    lại nội dung trả về cho người dùng đối chiếu (và có cái dán lại nếu lỡ tay)."""
    token = await _token()
    if not token:
        return "ERROR: " + (_check() or "chưa kết nối")
    args = args or {}
    post_id = str(args.get("post_id") or "").strip()
    if not post_id:
        return "ERROR: thiếu 'post_id' (id bài cần xoá, lấy từ fb_page_posts)."
    # post_id dạng {pageid}_{postid}: tự suy Trang như fb_page_edit
    if not (args.get("page_id") or args.get("page")) and "_" in post_id:
        args = {**args, "page_id": post_id.split("_", 1)[0]}
    pid, ptok, pname, err = await _resolve_page(args, token)
    if err:
        return err
    snap = await _get(post_id, {"fields": "id,message,created_time,permalink_url"}, ptok)
    if isinstance(snap, dict) and snap.get("error"):
        return _fmt(snap)                      # bài không tồn tại / không thuộc Trang này → dừng, chưa xoá gì
    d = await _delete(post_id, ptok)
    if isinstance(d, dict) and d.get("error"):
        return _fmt(d)
    ok = bool(isinstance(d, dict) and d.get("success") is True)
    cu = str((snap or {}).get("message") or "")
    return json.dumps({"ok": ok, "page": pname, "post_id": post_id,
                       "noi_dung_da_xoa": (cu[:300] + "…") if len(cu) > 300 else cu,
                       "created_time": (snap or {}).get("created_time"),
                       "note": "Đã xoá hẳn, KHÔNG khôi phục được." if ok
                               else "Facebook trả về khác thường: " + str(d)[:120]},
                      ensure_ascii=False, default=str)


async def _reply(args, ctx):
    token = await _token()
    if not token:
        return "ERROR: " + (_check() or "chưa kết nối")
    args = args or {}
    target = str(args.get("comment_id") or args.get("object_id") or args.get("post_id") or "").strip()
    msg = str(args.get("message") or "").strip()
    if not target:
        return "ERROR: thiếu 'comment_id' (bình luận cần trả lời) hoặc 'post_id' (để bình luận vào bài)."
    if not msg:
        return "ERROR: thiếu 'message' (nội dung trả lời)."
    pid, ptok, pname, err = await _resolve_page(args, token)
    if err:
        return err
    d = await _post(f"{target}/comments", {"message": msg}, ptok)
    if isinstance(d, dict) and d.get("error"):
        return _fmt(d)
    return json.dumps({"ok": True, "page": pname,
                       "reply_id": d.get("id") if isinstance(d, dict) else None},
                      ensure_ascii=False, default=str)


def register(ctx):
    ctx.register_tool(
        name="fb_pages_list", min_mode="readonly", check_fn=_check, handler=_list,
        description=("Liệt kê các Trang/Fanpage Facebook bạn quản lý (id, tên, hạng mục, quyền). Gọi đầu "
                     "tiên để lấy id/tên Trang cho các tool khác. KHÔNG lộ token của Trang."),
        schema={"type": "object", "properties": {}},
    )
    ctx.register_tool(
        name="fb_page_posts", min_mode="readonly", check_fn=_check, handler=_posts,
        description=("Đọc các bài GẦN ĐÂY trên một Trang của bạn (id bài, nội dung, thời gian, link, số bình "
                     "luận). Bỏ trống page nếu chỉ có 1 Trang; nhiều Trang thì truyền page_id hoặc page (tên)."),
        schema={"type": "object", "properties": {
            "page_id": {"type": "string", "description": "id Trang (bỏ trống nếu chỉ có 1 Trang)"},
            "page": {"type": "string", "description": "tên Trang (thay cho page_id)"},
            "limit": {"type": "integer", "description": "Số bài tối đa (mặc định 10)"}}},
    )
    ctx.register_tool(
        name="fb_page_comments", min_mode="readonly", check_fn=_check, handler=_comments,
        description=("Đọc bình luận của MỘT bài trên Trang (người bình luận, nội dung, thời gian). Cần post_id "
                     "lấy từ fb_page_posts. Trang tự suy từ post_id; nhiều Trang thì truyền thêm page_id/page nếu cần."),
        schema={"type": "object", "properties": {
            "post_id": {"type": "string", "description": "id bài cần đọc bình luận (từ fb_page_posts)"},
            "page_id": {"type": "string", "description": "id Trang (thường không cần, suy từ post_id)"},
            "page": {"type": "string", "description": "tên Trang (tuỳ chọn)"},
            "limit": {"type": "integer", "description": "Số bình luận tối đa (mặc định 25)"}},
            "required": ["post_id"]},
    )
    ctx.register_tool(
        name="fb_page_scheduled", min_mode="readonly", check_fn=_check, handler=_scheduled,
        description=("Đọc các bài ĐANG CHỜ ĐĂNG (đã hẹn giờ) trong lịch của một Trang: id bài, nội dung, giờ sẽ đăng. "
                     "Dùng để đối chiếu lịch đăng hay tìm post_id cần huỷ (fb_page_delete) hoặc sửa chữ "
                     "(fb_page_edit). Bỏ trống page nếu chỉ có 1 Trang."),
        schema={"type": "object", "properties": {
            "page_id": {"type": "string", "description": "id Trang (bỏ trống nếu chỉ có 1 Trang)"},
            "page": {"type": "string", "description": "tên Trang (thay cho page_id)"},
            "limit": {"type": "integer", "description": "Số bài tối đa (mặc định 25)"}}},
    )
    ctx.register_tool(
        name="fb_page_insights", min_mode="readonly", check_fn=_check, handler=_insights,
        description=("Read INSIGHTS of a Facebook Page or of one post: views, viewers, engagement, follows, clicks, "
                     "reactions. Without post_id: Page metrics per day/week/28 days between since and until (default the "
                     "last 28 days, at most 90). With post_id (from fb_page_posts): that post's lifetime metrics. "
                     "`metrics` picks other Graph API metric names. Needs the read_insights permission (the \"Read post "
                     "insights\" tick when connecting the Page on the Facebook Messenger card). Read only."),
        schema={"type": "object", "properties": {
            "page_id": {"type": "string", "description": "Page id (leave empty with a single Page)"},
            "page": {"type": "string", "description": "Page name (instead of page_id)"},
            "post_id": {"type": "string", "description": "Post id (from fb_page_posts) for that post's insights"},
            "metrics": {"type": "array", "items": {"type": "string"},
                        "description": "Graph API metric names (up to 10). Empty = the default set"},
            "period": {"type": "string", "enum": list(INSIGHT_PERIODS),
                       "description": "Page insights only: day (default), week, days_28, lifetime"},
            "since": {"type": "string", "description": "Start date YYYY-MM-DD (Page insights)"},
            "until": {"type": "string", "description": "End date YYYY-MM-DD (Page insights)"}}},
    )
    ctx.register_tool(
        name="fb_page_post", min_mode="full", check_fn=_check, handler=_publish,
        description=("ĐĂNG một bài lên Trang của bạn - hành động THẬT, công khai. Cần message (nội dung) và/hoặc "
                     "link. schedule_at = hẹn giờ: bài nằm trong lịch của Trang (Meta Business Suite) tới giờ đó. "
                     "Bỏ trống page nếu chỉ có 1 Trang; nhiều Trang thì truyền page_id/page."),
        schema={"type": "object", "properties": {
            "message": {"type": "string", "description": "Nội dung bài đăng"},
            "link": {"type": "string", "description": "Link đính kèm (tuỳ chọn)"},
            "schedule_at": {"type": "string", "description": "Hẹn giờ đăng (tuỳ chọn): 2026-11-25T09:00 theo múi giờ của bạn, hoặc Unix time. Ít nhất 10 phút nữa. Bỏ trống = đăng ngay"},
            "page_id": {"type": "string", "description": "id Trang (bỏ trống nếu chỉ có 1 Trang)"},
            "page": {"type": "string", "description": "tên Trang (thay cho page_id)"}}},
    )
    ctx.register_tool(
        name="fb_page_photo", min_mode="full", check_fn=_check, handler=_publish_photo,
        description=("ĐĂNG ẢNH lên Trang của bạn - hành động THẬT, công khai. photo = đường dẫn file ảnh "
                     "trong vault (vd attachments/anh.jpg) hoặc URL http(s). message = caption tuỳ chọn. "
                     "schedule_at = hẹn giờ đăng (vào lịch của Trang). Bỏ trống page nếu chỉ có 1 Trang."),
        schema={"type": "object", "properties": {
            "photo": {"type": "string", "description": "Đường dẫn ảnh trong vault hoặc URL http(s)"},
            "message": {"type": "string", "description": "Caption cho ảnh (tuỳ chọn)"},
            "schedule_at": {"type": "string", "description": "Hẹn giờ đăng (tuỳ chọn): 2026-11-25T09:00 theo múi giờ của bạn, hoặc Unix time. Ít nhất 10 phút nữa. Bỏ trống = đăng ngay"},
            "page_id": {"type": "string", "description": "id Trang (bỏ trống nếu chỉ có 1 Trang)"},
            "page": {"type": "string", "description": "tên Trang (thay cho page_id)"}},
            "required": ["photo"]},
    )
    ctx.register_tool(
        name="fb_page_album", min_mode="full", check_fn=_check, handler=_publish_album,
        description=("ĐĂNG ALBUM: nhiều ảnh (2-10) gom vào MỘT bài trên Trang - hành động THẬT, công khai. "
                     "photos = danh sách đường dẫn ảnh trong vault hoặc URL http(s). message = caption chung. "
                     "schedule_at = hẹn giờ đăng (vào lịch của Trang). Một ảnh thì dùng fb_page_photo."),
        schema={"type": "object", "properties": {
            "photos": {"type": "array", "items": {"type": "string"},
                       "description": "2-10 ảnh: đường dẫn trong vault hoặc URL http(s)"},
            "message": {"type": "string", "description": "Caption chung của album (tuỳ chọn)"},
            "schedule_at": {"type": "string", "description": "Hẹn giờ đăng (tuỳ chọn): 2026-11-25T09:00 theo múi giờ của bạn, hoặc Unix time. Ít nhất 10 phút nữa. Bỏ trống = đăng ngay"},
            "page_id": {"type": "string", "description": "id Trang (bỏ trống nếu chỉ có 1 Trang)"},
            "page": {"type": "string", "description": "tên Trang (thay cho page_id)"}},
            "required": ["photos"]},
    )
    ctx.register_tool(
        name="fb_page_edit", min_mode="full", check_fn=_check, handler=_edit_post,
        description=("SỬA nội dung chữ của một bài ĐÃ ĐĂNG trên Trang - hành động THẬT. Cần post_id (từ "
                     "fb_page_posts) và message MỚI thay toàn bộ nội dung cũ. Meta không cho đổi ảnh/video "
                     "đã đính kèm, chỉ đổi được chữ - muốn đổi ảnh thì đăng bài mới rồi fb_page_delete bài cũ."),
        schema={"type": "object", "properties": {
            "post_id": {"type": "string", "description": "id bài cần sửa (từ fb_page_posts)"},
            "message": {"type": "string", "description": "Nội dung MỚI thay cho nội dung cũ"},
            "page_id": {"type": "string", "description": "id Trang (thường tự suy từ post_id)"},
            "page": {"type": "string", "description": "tên Trang (tuỳ chọn)"}},
            "required": ["post_id", "message"]},
    )
    ctx.register_tool(
        name="fb_page_video", min_mode="full", check_fn=_check, handler=_publish_video,
        description=("ĐĂNG VIDEO lên Trang của bạn - hành động THẬT, công khai. video = đường dẫn file "
                     "video trong vault hoặc URL http(s) (tối đa cỡ 1GB). message = mô tả, title = tiêu đề, "
                     "thumbnail = ảnh bìa .jpg/.png trong vault (tối đa 10MB, cùng tỉ lệ với video), đều "
                     "tuỳ chọn. reel=true đăng dạng Reels (video dọc 9:16, 3-90 giây). Facebook xử lý nền "
                     "vài phút mới hiện bài. Bỏ trống page nếu chỉ có 1 Trang."),
        schema={"type": "object", "properties": {
            "video": {"type": "string", "description": "Đường dẫn video trong vault hoặc URL http(s)"},
            "thumbnail": {"type": "string",
                          "description": "Ảnh bìa .jpg/.png trong vault, hiện mặc định khi video lên (tuỳ chọn)"},
            "reel": {"type": "boolean", "description": "true = đăng dạng Reels (video dọc 3-90 giây)"},
            "message": {"type": "string", "description": "Mô tả video (tuỳ chọn)"},
            "title": {"type": "string", "description": "Tiêu đề video (tuỳ chọn)"},
            "page_id": {"type": "string", "description": "id Trang (bỏ trống nếu chỉ có 1 Trang)"},
            "page": {"type": "string", "description": "tên Trang (thay cho page_id)"}},
            "required": ["video"]},
    )
    ctx.register_tool(
        name="fb_page_delete", min_mode="full", check_fn=_check, handler=_delete_post,
        description=("XOÁ HẲN một bài đã đăng trên Trang - hành động THẬT, KHÔNG HOÀN TÁC ĐƯỢC (Trang không "
                     "có thùng rác). Cần post_id từ fb_page_posts. CHỈ gọi khi người dùng nói rõ muốn xoá "
                     "đúng bài đó; đừng tự xoá để 'dọn dẹp'. Xoá xong trả lại đoạn nội dung vừa xoá để đối chiếu."),
        schema={"type": "object", "properties": {
            "post_id": {"type": "string", "description": "id bài cần xoá (từ fb_page_posts)"},
            "page_id": {"type": "string", "description": "id Trang (thường tự suy từ post_id)"},
            "page": {"type": "string", "description": "tên Trang (tuỳ chọn)"}},
            "required": ["post_id"]},
    )
    ctx.register_tool(
        name="fb_page_reply", min_mode="full", check_fn=_check, handler=_reply,
        description=("TRẢ LỜI một bình luận, hoặc bình luận vào một bài - hành động THẬT, công khai. Cần message "
                     "và comment_id (trả lời bình luận) HOẶC post_id (bình luận vào bài). Nhiều Trang thì truyền "
                     "page_id/page."),
        schema={"type": "object", "properties": {
            "message": {"type": "string", "description": "Nội dung trả lời"},
            "comment_id": {"type": "string", "description": "id bình luận cần trả lời"},
            "post_id": {"type": "string", "description": "id bài (bình luận thẳng vào bài thay vì trả lời 1 comment)"},
            "page_id": {"type": "string", "description": "id Trang (khi có nhiều Trang)"},
            "page": {"type": "string", "description": "tên Trang (khi có nhiều Trang)"}},
            "required": ["message"]},
    )
