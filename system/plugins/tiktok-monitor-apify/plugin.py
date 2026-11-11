"""Bundled plugin: watch competitors' PUBLIC TikTok channels and break down their winning videos.

Why Apify and not yt-dlp (tested 2026-11-11 on a Vietnamese shop channel): yt-dlp could not list a TikTok profile at
all ("Unable to extract secondary user ID", also when handed the profile's secUid), and every single video asked for a
login ("This post may not be comfortable for some audiences"). The owner's TikTok cookies would get past that, at the
price of putting their account at risk, and they stop working on a VPS. Apify's `clockworks/tiktok-scraper` runs its
own sessions and proxies, so Javis never holds a TikTok login. Same reasoning as `fb-monitor-apify`.

Two tools, both read-only (they spend Apify credit like `fb_monitor` does, and never touch an account):
  - `tiktok_monitor`: the latest videos of each profile with views, likes, comments, shares and saves, scored against
    the profile's OWN median, so "hot" means "far above what this channel usually gets", not "big channel". Every scan
    is kept per brain, so the next one says which videos are new and how many views each gained since. No AI call.
  - `tiktok_analyze_video`: downloads one video through the same actor and hands the file to Gemini, which watches the
    pictures and hears the voice (hook, beats, on-screen text, call to action), then writes how to reuse the pattern on
    the owner's channel. Without a Gemini key the tool still returns the caption, the numbers and TikTok's subtitles,
    so the calling engine can analyse the words itself.

Token: any connection carrying an `apify_token` (today the "facebook-monitor" connector of the store pack; one Apify
token works for every actor), else the APIFY_TOKEN environment variable.
Price on the actor page (free tier, 2026-11): about 0.0037 USD per video returned, plus 0.0013 USD per video download.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import statistics
import tempfile
import threading
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

APIFY_ACTS = "https://api.apify.com/v2/acts"
ACTOR = "clockworks~tiktok-scraper"
# Connections whose `apify_token` is reused, first match wins. "facebook-monitor" is the Apify connector the store
# ships today; the other two are the names a dedicated connector would take, so it works the day one exists.
TOKEN_CONNECTORS = ("tiktok-monitor", "apify", "facebook-monitor")
APIFY_TIMEOUT_S = 305          # Apify's run-sync endpoint gives up at 300 s
MAX_PROFILES = 10
DEFAULT_LIMIT = 20
DEFAULT_MIN_RATIO = 3.0
RISING_MAX_HOURS = 72          # a video this young that already beats the channel median is "rising"
MAX_LISTED = 25                # videos returned when only the notable ones are asked for
MAX_LISTED_ALL = 100

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
GEMINI_FALLBACK_MODEL = "gemini-flash-latest"   # only used when stt_models cannot be imported
GEMINI_TIMEOUT_S = 240
MAX_VIDEO_MB = 18              # the video rides inline in one generateContent request, same cap as stt.GEMINI_MAX_MB
MAX_SUBTITLE_CHARS = 6000

STATE_KEEP_DAYS = 60
HISTORY_POINTS = 14

USERNAME_RE = re.compile(r"^[A-Za-z0-9._]{2,40}$")
PROFILE_URL_RE = re.compile(r"tiktok\.com/@([A-Za-z0-9._]+)", re.I)
VIDEO_URL_RE = re.compile(r"^https?://(([a-z0-9-]+\.)*tiktok\.com/@[^/\s]+/(video|photo)/\d+"
                          r"|(vm|vt)\.tiktok\.com/\w+)", re.I)

# Error items of the actor (its README, "Error codes reference"), told in words the model can pass on.
ERROR_HINTS = {
    "NOT_FOUND": "không có kênh này, kiểm tra lại tên",
    "PROFILE_PRIVATE": "kênh để riêng tư",
    "PROFILE_EMPTY": "kênh chưa có video, hoặc TikTok bắt đăng nhập mới cho xem",
    "PROFILE_VIDEOS_UNAVAILABLE": "TikTok không trả video khi chưa đăng nhập, thử lại sau",
    "POST_SENSITIVE": "TikTok gắn nhãn nội dung nhạy cảm nên không xem được khi chưa đăng nhập",
    "POST_NOT_FOUND_OR_PRIVATE": "video đã bị xoá hoặc để riêng tư",
    "FILTER_NO_PASS": "không video nào qua bộ lọc",
}

_state_lock = threading.Lock()


# ---------------------------------------------------------------- token

def _connections():
    try:
        import mcp_store
        return list(mcp_store.list_connections() or [])
    except Exception:
        return []


def _connection_token(connection_id):
    try:
        import mcp_store
        return str((mcp_store.connection_secrets(connection_id) or {}).get("apify_token") or "").strip()
    except Exception:
        return ""


def _token():
    by_connector = {}
    for c in _connections():
        cid = c.get("connector_id")
        if cid in TOKEN_CONNECTORS and cid not in by_connector:
            by_connector[cid] = c.get("id")
    for cid in TOKEN_CONNECTORS:
        if by_connector.get(cid):
            tok = _connection_token(by_connector[cid])
            if tok:
                return tok
    return (os.environ.get("APIFY_TOKEN") or "").strip() or None


def _check():
    if _token():
        return None
    return ("Chưa có token Apify. Vào trang Kết nối, chọn 'Theo dõi Facebook (Apify)' (cài gói đó trong Kho nếu chưa "
            "thấy), dán Personal API token lấy ở console.apify.com > Settings > API & Integrations. Một token Apify "
            "dùng chung cho cả Facebook lẫn TikTok.")


# ---------------------------------------------------------------- Apify

async def _run_actor(token, input_obj):
    """Run the actor synchronously: the dataset items as a list, or {'__error': ...}."""
    import httpx
    url = f"{APIFY_ACTS}/{ACTOR}/run-sync-get-dataset-items"
    try:
        async with httpx.AsyncClient(timeout=APIFY_TIMEOUT_S) as c:
            r = await c.post(url, params={"token": token}, json=input_obj)
    except Exception as e:
        return {"__error": f"{type(e).__name__}: {e}"}
    try:
        data = r.json()
    except Exception:
        return {"__error": f"HTTP {r.status_code}: {r.text[:200]}"}
    if isinstance(data, dict) and data.get("error"):
        e = data["error"]
        msg = str(e.get("message") if isinstance(e, dict) else e)
        if r.status_code == 408 or "timed out" in msg.lower() or "timeout" in msg.lower():
            msg += " (lượt quét quá 300 giây: bớt số kênh hoặc giảm limit)"
        return {"__error": msg}
    if not isinstance(data, list):
        return {"__error": f"Apify trả dữ liệu lạ: {str(data)[:200]}"}
    return data


def _is_error_item(item):
    return bool(item.get("errorCode")) or (bool(item.get("error")) and not item.get("id"))


def _error_line(item):
    code = str(item.get("errorCode") or "")
    who = item.get("input") or item.get("url") or "?"
    hint = ERROR_HINTS.get(code) or str(item.get("error") or "lỗi không rõ")
    return f"{who}: {hint}" + (f" ({code})" if code else "")


# ---------------------------------------------------------------- parsing

def _num(obj, *keys):
    for k in keys:
        v = (obj or {}).get(k)
        if isinstance(v, bool):
            continue
        if isinstance(v, (int, float)):
            return int(v)
        if isinstance(v, str):
            s = v.replace(",", "").replace(".", "").strip()
            if s.isdigit():
                return int(s)
    return 0


def _int_arg(value, default, low, high):
    try:
        return max(low, min(high, int(value)))
    except (TypeError, ValueError):
        return default


def _float_arg(value, default, low, high):
    try:
        return max(low, min(high, float(value)))
    except (TypeError, ValueError):
        return default


def parse_profiles(raw):
    """Usernames from '@name', 'name' or profile links. Returns (usernames, entries it could not read)."""
    parts = [str(x) for x in raw] if isinstance(raw, list) else re.split(r"[\s,;]+", str(raw or ""))
    names, bad = [], []
    for part in parts:
        part = part.strip()
        if not part:
            continue
        m = PROFILE_URL_RE.search(part)
        name = (m.group(1) if m else part.lstrip("@")).strip().rstrip("/")
        if USERNAME_RE.match(name):
            if name.lower() not in {n.lower() for n in names}:
                names.append(name)
        else:
            bad.append(part)
    return names, bad


def _author(item):
    a = item.get("authorMeta")
    return a if isinstance(a, dict) else {}


def normalize_video(item):
    author = _author(item)
    meta = item.get("videoMeta") if isinstance(item.get("videoMeta"), dict) else {}
    music = item.get("musicMeta") if isinstance(item.get("musicMeta"), dict) else {}
    tags = [h.get("name") if isinstance(h, dict) else str(h) for h in (item.get("hashtags") or [])]
    created = _num(item, "createTime")
    posted = item.get("createTimeISO") or ""
    if not posted and created:
        posted = datetime.fromtimestamp(created, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {
        "id": str(item.get("id") or ""),
        "url": item.get("webVideoUrl") or item.get("submittedVideoUrl") or "",
        "profile": author.get("name") or item.get("authorMeta.name") or "",
        "created": created,
        "posted": posted,
        "duration_s": _num(meta, "duration"),
        "views": _num(item, "playCount"),
        "likes": _num(item, "diggCount"),
        "comments": _num(item, "commentCount"),
        "shares": _num(item, "shareCount"),
        "saves": _num(item, "collectCount"),
        "caption": str(item.get("text") or "")[:300],
        "hashtags": [t for t in tags if t][:10],
        "music": " - ".join(str(x) for x in (music.get("musicName"), music.get("musicAuthor")) if x),
        "original_sound": bool(music.get("musicOriginal")),
        "pinned": bool(item.get("isPinned")),
        "ad": bool(item.get("isAd") or item.get("isSponsored")),
        "slideshow": bool(item.get("isSlideshow")),
        "shop_product": bool(item.get("hasTikTokShopProduct")),
    }


def channel_median(videos):
    """Median views of the channel. Pinned videos are left out: they are old hits and lift the bar."""
    base = [v["views"] for v in videos if not v["pinned"]] or [v["views"] for v in videos]
    return statistics.median(base) if base else 0


def score_profile(videos, min_ratio, now, history, first_scan):
    """Adds ratio, rates and flags to each video of ONE profile, in place. Returns the channel median.

    `history`: {video_id: entry} from earlier scans of this brain. On a profile's first scan nothing is flagged
    "new", since every video would be."""
    median = channel_median(videos)
    for v in videos:
        views = v["views"] or 0
        v["ratio"] = round(views / median, 1) if median else None
        reactions = v["likes"] + v["comments"] + v["shares"] + v["saves"]
        v["engagement_pct"] = round(100 * reactions / views, 2) if views else None
        v["shares_per_1k"] = round(1000 * v["shares"] / views, 1) if views else None
        v["saves_per_1k"] = round(1000 * v["saves"] / views, 1) if views else None
        age_h = (now - v["created"]) / 3600 if v["created"] else None
        v["age_days"] = round(age_h / 24, 1) if age_h is not None else None
        flags = []
        prev = history.get(v["id"])
        if prev is None:
            if not first_scan:
                flags.append("new")
        else:
            points = prev.get("views") or []
            if points:
                ts, old = points[-1]
                v["views_gain"] = views - int(old or 0)
                v["hours_since_last_scan"] = round((now - ts) / 3600, 1)
            if prev.get("analyzed_at"):
                v["analyzed"] = True
        if v["ratio"] is not None and v["ratio"] >= min_ratio:
            flags.append("hot")
        elif median and age_h is not None and age_h <= RISING_MAX_HOURS and views >= median and not v["pinned"]:
            flags.append("rising")
        v["flags"] = flags
    return median


def profile_summary(videos, author, median, first_scan):
    regular = [v for v in videos if not v["pinned"]] or videos
    times = sorted(v["created"] for v in regular if v["created"])
    per_day = None
    if len(times) >= 2:
        span_days = (times[-1] - times[0]) / 86400
        per_day = round((len(times) - 1) / span_days, 1) if span_days >= 1 else float(len(times))
    durations = [v["duration_s"] for v in regular if v["duration_s"]]
    tags = Counter(t.lower() for v in regular for t in v["hashtags"]).most_common(6)
    return {
        "profile": "@" + (author.get("name") or videos[0]["profile"]),
        "nickname": author.get("nickName") or "",
        "followers": _num(author, "fans"),
        "total_likes": _num(author, "heart"),
        "total_videos": _num(author, "video"),
        "scanned": len(videos),
        "median_views": int(median),
        "posts_per_day": per_day,
        "median_duration_s": int(statistics.median(durations)) if durations else None,
        "top_hashtags": [t for t, _ in tags],
        "first_scan": first_scan,
    }


def _public(v):
    out = {k: val for k, val in v.items()
           if k != "created" and val is not None and val is not False and val != "" and val != []}
    out.setdefault("flags", [])
    return out


# ---------------------------------------------------------------- state (one file per brain)

def _state_path(ctx):
    base = getattr(ctx, "data_dir", None)
    base = Path(base) if base else Path(tempfile.gettempdir()) / "javis-tiktok-monitor"
    brain = str(getattr(ctx, "vault_root", "") or "")
    return base / f"scans-{hashlib.sha1(brain.encode('utf-8')).hexdigest()[:12]}.json"


def _load_state(path):
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_state(path, state):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


def _remember(state, videos, medians, now):
    known = state.setdefault("videos", {})
    for v in videos:
        entry = known.setdefault(v["id"], {"profile": v["profile"]})
        points = entry.setdefault("views", [])
        points.append([int(now), v["views"]])
        del points[:-HISTORY_POINTS]
        entry["last_seen"] = int(now)
    profiles = state.setdefault("profiles", {})
    for name, median in medians.items():
        profiles[name] = {"median_views": int(median), "at": int(now)}
    cutoff = now - STATE_KEEP_DAYS * 86400
    for vid in [k for k, e in known.items() if max(e.get("last_seen") or 0, e.get("analyzed_at") or 0) < cutoff]:
        known.pop(vid, None)


# ---------------------------------------------------------------- tiktok_monitor

async def _monitor(args, ctx):
    token = _token()
    if not token:
        return "ERROR: " + _check()
    args = args or {}
    names, bad = parse_profiles(args.get("profiles") or args.get("profile") or args.get("urls") or "")
    if not names:
        return ("ERROR: thiếu 'profiles' (tên kênh TikTok như @tenkenh hoặc link kênh)."
                + (f" Không đọc được: {', '.join(bad[:5])}" if bad else ""))
    errors = [f"{b}: không đọc được tên kênh" for b in bad]
    if len(names) > MAX_PROFILES:
        errors.append(f"chỉ quét {MAX_PROFILES} kênh đầu mỗi lượt, bỏ qua: {', '.join(names[MAX_PROFILES:])}")
        names = names[:MAX_PROFILES]
    limit = _int_arg(args.get("limit"), DEFAULT_LIMIT, 1, 100)
    min_ratio = _float_arg(args.get("min_ratio"), DEFAULT_MIN_RATIO, 1.5, 50.0)
    days = _int_arg(args.get("days"), 0, 0, 365)
    include_all = bool(args.get("include_all"))

    data = await _run_actor(token, {
        "profiles": names, "resultsPerPage": limit, "profileScrapeSections": ["videos"],
        "profileSorting": "latest", "excludePinnedPosts": False,
        "shouldDownloadVideos": False, "shouldDownloadCovers": False,
        "downloadSubtitlesOptions": "NEVER_DOWNLOAD_SUBTITLES"})
    if isinstance(data, dict):
        return "ERROR: Apify: " + str(data.get("__error") or data)[:400]

    by_profile, authors = {}, {}
    for item in data:
        if not isinstance(item, dict):
            continue
        if _is_error_item(item):
            errors.append(_error_line(item))
            continue
        v = normalize_video(item)
        if not v["id"]:
            continue
        key = (v["profile"] or "?").lower()
        by_profile.setdefault(key, []).append(v)
        authors.setdefault(key, _author(item))
    for name in names:
        if name.lower() not in by_profile and not any(name.lower() in e.lower() for e in errors):
            errors.append(f"{name}: Apify không trả video nào")

    now = time.time()
    path = _state_path(ctx)
    summaries, every, medians = [], [], {}
    with _state_lock:
        state = _load_state(path)
        history = state.get("videos") or {}
        for key, videos in by_profile.items():
            first_scan = not any(v["id"] in history for v in videos)
            median = score_profile(videos, min_ratio, now, history, first_scan)
            medians[key] = median
            summaries.append(profile_summary(videos, authors.get(key) or {}, median, first_scan))
            every.extend(videos)
        _remember(state, every, medians, now)
        try:
            _save_state(path, state)
        except Exception as e:
            errors.append(f"không lưu được lịch sử quét: {type(e).__name__}")

    if not every and errors:
        return "ERROR: " + "; ".join(errors)
    visible = [v for v in every if not days or (v["age_days"] is not None and v["age_days"] <= days)]
    hot = sorted((v for v in visible if "hot" in v["flags"]), key=lambda v: v["ratio"] or 0, reverse=True)
    rising = sorted((v for v in visible if "rising" in v["flags"]), key=lambda v: v["views"], reverse=True)
    fresh = sorted((v for v in visible if v["flags"] == ["new"]), key=lambda v: v["created"], reverse=True)
    if include_all:
        listed = sorted(visible, key=lambda v: v["created"], reverse=True)[:MAX_LISTED_ALL]
    else:
        listed = (hot + rising + fresh)[:MAX_LISTED]
    return json.dumps({
        "scanned_at": datetime.fromtimestamp(now, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "min_ratio": min_ratio,
        "profiles": summaries,
        "counts": {"videos": len(every), "hot": len(hot), "rising": len(rising),
                   "new": sum(1 for v in visible if "new" in v["flags"])},
        "videos": [_public(v) for v in listed],
        "errors": errors,
    }, ensure_ascii=False)


# ---------------------------------------------------------------- tiktok_analyze_video

def vtt_to_text(raw):
    """Plain words from a WebVTT subtitle: cue numbers, timings, tags and repeated lines dropped."""
    lines = []
    for line in str(raw or "").splitlines():
        s = line.strip()
        if (not s or "-->" in s or s.isdigit() or s.upper().startswith("WEBVTT")
                or s.startswith(("NOTE", "STYLE", "REGION"))):
            continue
        s = re.sub(r"<[^>]+>", "", s).strip()
        if s and (not lines or lines[-1] != s):
            lines.append(s)
    return " ".join(lines)


def pick_subtitle(item, prefer=("vie", "vi")):
    """TikTok's own subtitle track, spoken language first: a machine translation ('MT') only when nothing else."""
    meta = item.get("videoMeta") if isinstance(item.get("videoMeta"), dict) else {}
    links = [s for s in (meta.get("subtitleLinks") or [])
             if isinstance(s, dict) and (s.get("downloadLink") or s.get("tiktokLink"))]

    def rank(s):
        lang = str(s.get("language") or "").lower()
        return (str(s.get("source") or "").upper() == "MT", not any(lang.startswith(p) for p in prefer))
    links.sort(key=rank)
    return links[0] if links else None


async def _get_text(url, limit=200_000):
    import httpx
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as c:
        r = await c.get(url)
    if r.status_code != 200:
        raise RuntimeError(f"HTTP {r.status_code}")
    return r.text[:limit]


async def _subtitle_text(item, notes):
    track = pick_subtitle(item)
    if not track:
        return ""
    try:
        raw = await _get_text(track.get("downloadLink") or track.get("tiktokLink"))
    except Exception as e:
        notes.append(f"không tải được phụ đề TikTok: {type(e).__name__}: {str(e)[:120]}")
        return ""
    return vtt_to_text(raw)[:MAX_SUBTITLE_CHARS]


async def _download_video(item, token, notes):
    import httpx
    urls = [u for u in (item.get("mediaUrls") or []) if isinstance(u, str) and u.startswith("http")]
    if not urls:
        notes.append("Apify không trả file video")
        return b""
    url = urls[0]
    params = {"token": token} if "api.apify.com" in url and "token=" not in url else None
    cap = MAX_VIDEO_MB * 1024 * 1024
    try:
        async with httpx.AsyncClient(timeout=120, follow_redirects=True) as c:
            async with c.stream("GET", url, params=params) as r:
                if r.status_code != 200:
                    notes.append(f"tải video lỗi HTTP {r.status_code}")
                    return b""
                buf = bytearray()
                async for chunk in r.aiter_bytes():
                    buf.extend(chunk)
                    if len(buf) > cap:
                        notes.append(f"video lớn hơn {MAX_VIDEO_MB}MB nên không gửi cho Gemini")
                        return b""
                return bytes(buf)
    except Exception as e:
        notes.append(f"tải video lỗi: {type(e).__name__}: {str(e)[:120]}")
        return b""


def _gemini_key():
    try:
        import aux_engine
        key = aux_engine.api_key_for("gemini")
    except Exception:
        key = ""
    return str(key or os.environ.get("GEMINI_API_KEY") or "").strip()


def _gemini_model(key):
    try:
        import stt_models
        return stt_models.best("gemini", key) or GEMINI_FALLBACK_MODEL
    except Exception:
        return GEMINI_FALLBACK_MODEL


def _reply_language(arg):
    code = str(arg or "").strip().lower()
    if not code:
        try:
            import localefmt
            code = localefmt.ngon_ngu_tra_loi()
        except Exception:
            code = "vi"
    return {"vi": "tiếng Việt", "en": "English"}.get(code[:2], code)


def build_prompt(v, subtitle, apply_to, language, median=None):
    stats = (f"{v['views']:,} view, {v['likes']:,} tim, {v['comments']:,} bình luận, "
             f"{v['shares']:,} chia sẻ, {v['saves']:,} lưu")
    if median:
        stats += f" (kênh này thường được khoảng {int(median):,} view mỗi video, video này gấp {v['views'] / median:.1f} lần)"
    words = f"\n- Phụ đề TikTok (có thể sai chính tả): {subtitle}" if subtitle else ""
    mine = (f"Kênh/sản phẩm của tôi: {apply_to}" if apply_to
            else "Chưa có mô tả kênh của tôi: viết ý tưởng cho một kênh bán hàng cùng ngành.")
    return f"""Bạn là chuyên gia nội dung video ngắn TikTok. Hãy xem video đính kèm của một kênh đối thủ (cả hình lẫn tiếng) và phân tích để tôi học cách làm rồi áp dụng cho kênh của mình.

Thông tin video:
- Kênh: @{v['profile']} · đăng {v['posted'] or '?'} · dài {v['duration_s'] or '?'} giây
- Số liệu: {stats}
- Caption: {v['caption'] or '(trống)'}
- Nhạc: {v['music'] or '?'}{' (âm thanh gốc)' if v['original_sound'] else ''}{words}

Viết bằng {language}. Chỉ nói điều THẤY và NGHE được trong video, không đoán. Ghi mốc thời gian dạng mm:ss. Trình bày đúng các mục:

## 1. Video nói gì
Một câu: giới thiệu hoặc bán gì, cho ai.

## 2. Hook 3 giây đầu
Câu nói đầu tiên (gần nguyên văn), hình ảnh mở màn, chữ trên màn hình, và vì sao nó giữ người xem lại.

## 3. Diễn biến theo mốc thời gian
Từng nhịp: mm:ss, chuyện gì xảy ra (lời, hình, chữ trên màn).

## 4. Góc nội dung
Thuộc dạng nào (test sức mạnh, so sánh, xả kho hoặc giá sốc, nỗi lo theo mùa, review cùng người thật, hậu trường, bắt trend, kể chuyện...) và vì sao góc đó hợp với sản phẩm.

## 5. Cách quay dựng
Độ dài, số cảnh và nhịp cắt, góc máy, ai xuất hiện, chữ trên màn, nhạc và âm thanh, giọng nói.

## 6. Bán hàng và kêu gọi
Sản phẩm, giá, ưu đãi, bằng chứng đưa ra, câu kêu gọi hành động và lúc nó xuất hiện.

## 7. Vì sao video này ăn
3 đến 5 lý do cụ thể, dựa trên video và các tỉ lệ chia sẻ, lưu, bình luận ở trên.

## 8. Áp dụng cho kênh của tôi
{mine}
Đưa 3 ý tưởng video mới mượn CẤU TRÚC và góc nội dung, không chép lời, không dùng lại hình của đối thủ. Mỗi ý: hook 3 giây đầu, các nhịp chính, câu kêu gọi.
"""


async def _gemini_analyze(video, prompt, key, notes):
    import httpx
    model = _gemini_model(key)
    body = {"contents": [{"role": "user", "parts": [
                {"inline_data": {"mime_type": "video/mp4", "data": base64.b64encode(video).decode()}},
                {"text": prompt}]}],
            "generationConfig": {"temperature": 0.4}}
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(GEMINI_TIMEOUT_S)) as c:
            r = await c.post(GEMINI_URL.format(model=model), headers={"x-goog-api-key": key}, json=body)
    except Exception as e:
        notes.append(f"gọi Gemini ({model}) lỗi: {type(e).__name__}: {str(e)[:120]}")
        return ""
    try:
        d = r.json()
    except Exception:
        d = {}
    if r.status_code != 200:
        err = d.get("error") if isinstance(d.get("error"), dict) else {}
        notes.append(f"Gemini ({model}) từ chối: {str(err.get('message') or f'HTTP {r.status_code}')[:200]}")
        return ""
    parts = (((d.get("candidates") or [{}])[0].get("content") or {}).get("parts") or [])
    text = "\n".join(str(p.get("text") or "") for p in parts if isinstance(p, dict) and not p.get("thought")).strip()
    if not text:
        notes.append(f"Gemini ({model}) không trả lời, có thể do bộ lọc an toàn")
    return text


def render_analysis(v, analysis, subtitle, notes, median=None):
    head = [f"# Phân tích video TikTok @{v['profile']}", f"Link: {v['url']}",
            f"Đăng: {v['posted'] or '?'} · dài {v['duration_s'] or '?'} giây · {v['views']:,} view · {v['likes']:,} tim · "
            f"{v['comments']:,} bình luận · {v['shares']:,} chia sẻ · {v['saves']:,} lưu"
            + (f" · gấp {v['views'] / median:.1f} lần trung vị kênh" if median else ""),
            f"Caption: {v['caption'] or '(trống)'}"]
    if analysis:
        body = [analysis]
    else:
        body = ["## Chưa xem được hình và tiếng của video",
                ("Lời thoại (phụ đề TikTok): " + subtitle) if subtitle else "Không có phụ đề TikTok cho video này.",
                "Hãy tự phân tích phần có được theo các mục: hook 3 giây đầu, diễn biến, góc nội dung, cách quay dựng, "
                "bán hàng và kêu gọi, vì sao video ăn, 3 ý tưởng áp dụng cho kênh của người dùng. Nói rõ với người "
                "dùng là chưa xem được hình."]
    tail = ["Ghi chú: " + "; ".join(notes)] if notes else []
    return "\n\n".join(head + body + tail)


def _mark_analyzed(ctx, v):
    path = _state_path(ctx)
    with _state_lock:
        state = _load_state(path)
        entry = state.setdefault("videos", {}).setdefault(v["id"], {"profile": v["profile"]})
        entry["analyzed_at"] = int(time.time())
        try:
            _save_state(path, state)
        except Exception:
            pass


def _known_median(ctx, profile):
    entry = (_load_state(_state_path(ctx)).get("profiles") or {}).get(str(profile or "").lower()) or {}
    return entry.get("median_views") or None


async def _analyze(args, ctx):
    token = _token()
    if not token:
        return "ERROR: " + _check()
    args = args or {}
    url = str(args.get("url") or args.get("link") or "").strip()
    if not VIDEO_URL_RE.match(url):
        return "ERROR: cần 'url' là link một video TikTok (tiktok.com/@kenh/video/... hoặc vt.tiktok.com/...)."
    apply_to = str(args.get("apply_to") or args.get("goal") or "").strip()[:600]

    data = await _run_actor(token, {
        "postURLs": [url], "resultsPerPage": 1, "shouldDownloadVideos": True, "shouldDownloadCovers": False,
        "downloadSubtitlesOptions": "DOWNLOAD_SUBTITLES"})
    if isinstance(data, dict):
        return "ERROR: Apify: " + str(data.get("__error") or data)[:400]
    items = [i for i in data if isinstance(i, dict)]
    videos = [i for i in items if not _is_error_item(i) and i.get("id")]
    if not videos:
        why = "; ".join(_error_line(i) for i in items if _is_error_item(i)) or "Apify không trả về video này"
        return "ERROR: " + why

    item = videos[0]
    v = normalize_video(item)
    median = _known_median(ctx, v["profile"])
    notes = []
    subtitle = await _subtitle_text(item, notes)
    key = _gemini_key()
    analysis = ""
    if not key:
        notes.append("chưa có Gemini API key (trang Models) nên chưa xem được hình, mới đọc được chữ")
    else:
        video = await _download_video(item, token, notes)
        if video:
            prompt = build_prompt(v, subtitle, apply_to, _reply_language(args.get("lang")), median)
            analysis = await _gemini_analyze(video, prompt, key, notes)
    _mark_analyzed(ctx, v)
    return render_analysis(v, analysis, subtitle, notes, median)


# ---------------------------------------------------------------- register

def register(ctx):
    ctx.register_tool(
        name="tiktok_monitor", min_mode="readonly", check_fn=_check, handler=_monitor, emoji="📈",
        description=(
            "Theo dõi kênh TikTok CÔNG KHAI (thường là đối thủ) qua Apify: lấy các video mới nhất của từng kênh kèm "
            "view, tim, bình luận, chia sẻ, lưu, rồi so với trung vị view của CHÍNH kênh đó. Cờ 'hot' = gấp min_ratio "
            "lần trung vị trở lên, 'rising' = đăng dưới 3 ngày đã vượt trung vị, 'new' = chưa có ở lần quét trước. "
            "Javis nhớ từng lần quét theo brain nên lần sau có views_gain (view tăng thêm) và analyzed (đã phân tích). "
            "profiles = tên kênh hoặc link kênh, cách nhau bởi dấu phẩy hoặc xuống dòng (tối đa 10); limit = số video "
            "mới nhất mỗi kênh (mặc định 20); min_ratio (mặc định 3); days = chỉ trả video đăng trong N ngày; "
            "include_all = trả mọi video thay vì chỉ video đáng chú ý. Không gọi AI, không dùng tài khoản TikTok. Tốn "
            "phí Apify khoảng 0,004 USD mỗi video. Quy trình gợi ý: quét hằng ngày, gọi tiktok_analyze_video cho video "
            "hot hoặc rising chưa analyzed, rồi lưu bản phân tích vào brain khi người dùng muốn tích luỹ."),
        schema={"type": "object", "properties": {
            "profiles": {"type": "string",
                         "description": "Tên kênh (@tenkenh) hoặc link kênh TikTok, cách nhau bởi dấu phẩy hoặc xuống dòng"},
            "limit": {"type": "integer", "description": "Số video mới nhất lấy mỗi kênh (mặc định 20, tối đa 100)"},
            "min_ratio": {"type": "number", "description": "Gấp bao nhiêu lần trung vị view của kênh thì tính là hot (mặc định 3)"},
            "days": {"type": "integer", "description": "Chỉ trả video đăng trong N ngày gần nhất (0 = không lọc)"},
            "include_all": {"type": "boolean", "description": "Trả mọi video đã quét thay vì chỉ video hot, rising, new"}},
            "required": ["profiles"]},
    )
    ctx.register_tool(
        name="tiktok_analyze_video", min_mode="readonly", check_fn=_check, handler=_analyze, emoji="🎬",
        description=(
            "Phân tích SÂU một video TikTok (thường là video hot của đối thủ): tải video qua Apify rồi cho Gemini xem "
            "cả hình lẫn tiếng, trả về hook 3 giây đầu, diễn biến theo mốc thời gian, góc nội dung, cách quay dựng, "
            "cách bán hàng, vì sao video ăn, và 3 ý tưởng áp dụng cho kênh của người dùng. url = link video; "
            "apply_to = mô tả kênh hoặc sản phẩm của người dùng để ý tưởng sát hơn (nên truyền, lấy từ bộ nhớ nếu có); "
            "lang = ngôn ngữ trả lời (mặc định theo cài đặt). Chưa có Gemini API key thì tool trả caption, số liệu và "
            "phụ đề TikTok để bạn tự phân tích phần lời, và phải nói rõ là chưa xem được hình. Tốn khoảng 0,005 USD "
            "phí Apify và một lượt Gemini. Chỉ học cấu trúc, KHÔNG chép lời hay đăng lại video của người khác."),
        schema={"type": "object", "properties": {
            "url": {"type": "string", "description": "Link video TikTok (tiktok.com/@kenh/video/... hoặc link rút gọn)"},
            "apply_to": {"type": "string",
                         "description": "Kênh hoặc sản phẩm của người dùng, vd 'shop dụng cụ cầm tay, khách là thợ'"},
            "lang": {"type": "string", "description": "Mã ngôn ngữ trả lời, vd 'vi' hoặc 'en'"}},
            "required": ["url"]},
    )
