"""Tests for the bundled TikTok competitor watch plugin (Apify + Gemini). Run by hand or in CI:

    python tests/run.py tiktok_monitor

No network: the token, the Apify actor, the subtitle and video downloads and Gemini are all faked. Covers: the plugin
registers two read-only tools, the token gate and where the token comes from, reading profile names, normalising an
actor item, scoring against the channel's own median, the scan memory per brain (new videos, views gained, analysed
marks), error items told in words, and the analysis with and without a Gemini key.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401  - puts server/ on sys.path (see tests/python/_paths.py)
import asyncio
import importlib.util
import json
import os
import sys
import tempfile
import time
import types
from pathlib import Path

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-ttmon-"))
os.environ.pop("APIFY_TOKEN", None)

_fails = []


def check(name, cond):
    print(("ok  " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)


spec = importlib.util.spec_from_file_location(
    "tiktok_monitor_test", str(ROOT / "system" / "plugins" / "tiktok-monitor-apify" / "plugin.py"))
plug = importlib.util.module_from_spec(spec)
spec.loader.exec_module(plug)


class _Ctx:
    def __init__(self, brain="brainA"):
        self.tools = []
        self.vault_root = str(Path(tempfile.gettempdir()) / brain)
        self.data_dir = Path(tempfile.mkdtemp(prefix="ttmon-data-"))

    def register_tool(self, name, description, handler, schema=None, min_mode="readonly", check_fn=None, **k):
        self.tools.append({"name": name, "min_mode": min_mode, "schema": schema, "description": description})


# ---- 1. Registration ----
ctx = _Ctx()
plug.register(ctx)
check("register: two read-only tools",
      sorted(t["name"] for t in ctx.tools) == ["tiktok_analyze_video", "tiktok_monitor"]
      and all(t["min_mode"] == "readonly" for t in ctx.tools))
check("register: descriptions have no em dash", all("—" not in t["description"] for t in ctx.tools))
manifest = (ROOT / "system" / "plugins" / "tiktok-monitor-apify" / "plugin.yaml").read_text(encoding="utf-8")
check("plugin.yaml lists both tools", "- tiktok_monitor" in manifest and "- tiktok_analyze_video" in manifest)


# ---- 2. Token ----
real_connections = plug._connections
plug._connections = lambda: []
check("token: none -> _check blocks and names the connector", "Theo dõi Facebook (Apify)" in (plug._check() or ""))

fake_store = types.ModuleType("mcp_store")
fake_store.list_connections = lambda: [{"id": "c1", "connector_id": "zalo"},
                                       {"id": "c2", "connector_id": "facebook-monitor"}]
fake_store.connection_secrets = lambda cid: {"apify_token": "apify_api_fb"} if cid == "c2" else {}
saved_store = sys.modules.get("mcp_store")
sys.modules["mcp_store"] = fake_store
plug._connections = real_connections
check("token: reused from the facebook-monitor Apify connection", plug._token() == "apify_api_fb")
if saved_store is None:
    sys.modules.pop("mcp_store", None)
else:
    sys.modules["mcp_store"] = saved_store
plug._connections = lambda: []
os.environ["APIFY_TOKEN"] = "apify_api_env"
check("token: APIFY_TOKEN environment variable as the last resort", plug._token() == "apify_api_env")
os.environ.pop("APIFY_TOKEN", None)


# ---- 3. Profiles ----
names, bad = plug.parse_profiles("@thienphustorevn, https://www.tiktok.com/@b.c_d?lang=vi\nplain_name @THIENPHUSTOREVN ???")
check("parse_profiles: @name, link and bare name, no duplicates", names == ["thienphustorevn", "b.c_d", "plain_name"])
check("parse_profiles: unreadable entry reported", bad == ["???"])
check("parse_profiles: list input", plug.parse_profiles(["@x1", "y2"])[0] == ["x1", "y2"])


# ---- 4. Normalising an item (shape from the actor's README) ----
NOW = time.time()


def item(vid, views, hours_ago, pinned=False, user="shop", **extra):
    base = {"id": vid, "text": f"caption {vid} #tools", "createTime": int(NOW - hours_ago * 3600),
            "authorMeta": {"name": user, "nickName": "Shop VN", "fans": 60700, "heart": 128900, "video": 773},
            "musicMeta": {"musicName": "original sound", "musicAuthor": "Shop VN", "musicOriginal": True},
            "webVideoUrl": f"https://www.tiktok.com/@{user}/video/{vid}",
            "videoMeta": {"duration": 30}, "diggCount": views // 20, "shareCount": views // 200,
            "playCount": views, "collectCount": views // 100, "commentCount": views // 500,
            "hashtags": [{"name": "tools"}, {"name": "hukan"}], "isPinned": pinned}
    base.update(extra)
    return base


n = plug.normalize_video(item("1", 10000, 5))
check("normalize: counts", (n["views"], n["likes"], n["shares"], n["saves"], n["comments"]) == (10000, 500, 50, 100, 20))
check("normalize: profile, url, hashtags, music", n["profile"] == "shop" and n["url"].endswith("/video/1")
      and n["hashtags"] == ["tools", "hukan"] and n["music"] == "original sound - Shop VN" and n["original_sound"])
check("normalize: ISO date built from createTime", n["posted"].endswith("Z") and n["posted"][:2] == "20")


# ---- 5. Scoring against the channel's own median ----
vids = [plug.normalize_video(x) for x in (
    item("p", 900000, 24 * 40, pinned=True),       # old pinned hit: left out of the median
    item("a", 1000, 24 * 5), item("b", 1000, 24 * 4), item("c", 800, 24 * 3),
    item("d", 5000, 24 * 2),                       # 5x median -> hot
    item("e", 1500, 30),                           # young and above median -> rising
    item("f", 300, 10))]
median = plug.score_profile(vids, 3.0, NOW, {}, first_scan=True)
by = {v["id"]: v for v in vids}
check("score: median skips the pinned video", median == 1000)
check("score: 5x median is hot", by["d"]["flags"] == ["hot"] and by["d"]["ratio"] == 5.0)
check("score: young video above median is rising", by["e"]["flags"] == ["rising"])
check("score: pinned old hit still shows as hot", "hot" in by["p"]["flags"])
check("score: ordinary video has no flag", by["a"]["flags"] == [] and by["f"]["flags"] == [])
check("score: first scan flags nothing new", not any("new" in v["flags"] for v in vids))
check("score: share and save rates per 1000 views", by["d"]["shares_per_1k"] == 5.0 and by["d"]["saves_per_1k"] == 10.0)


# ---- 6. tiktok_monitor end to end ----
async def monitor_tests():
    plug._token = lambda: "APIFYTOK"
    calls = []
    scan = {"items": []}

    async def fake_actor(token, input_obj):
        calls.append((token, input_obj))
        return scan["items"]
    plug._run_actor = fake_actor

    scan["items"] = [item("a", 1000, 24 * 5), item("b", 1100, 24 * 4), item("c", 900, 24 * 3),
                     item("d", 6000, 24 * 2),
                     {"url": "https://www.tiktok.com/@ghost", "input": "ghost", "error": "Profile is private",
                      "errorCode": "PROFILE_PRIVATE"}]
    mctx = _Ctx("brainMonitor")
    out = json.loads(await plug._monitor({"profiles": "@shop, @ghost", "limit": 15}, mctx))
    token, sent = calls[-1]
    check("monitor: actor gets usernames, limit and latest sorting",
          token == "APIFYTOK" and sent["profiles"] == ["shop", "ghost"] and sent["resultsPerPage"] == 15
          and sent["profileSorting"] == "latest" and sent["shouldDownloadVideos"] is False)
    check("monitor: hot video listed first", out["videos"] and out["videos"][0]["id"] == "d"
          and "hot" in out["videos"][0]["flags"])
    check("monitor: profile summary", out["profiles"][0]["profile"] == "@shop" and out["profiles"][0]["followers"] == 60700
          and out["profiles"][0]["median_views"] == 1050 and out["profiles"][0]["first_scan"] is True)
    check("monitor: error item told in words", any("riêng tư" in e and "ghost" in e for e in out["errors"]))
    check("monitor: only notable videos by default", {v["id"] for v in out["videos"]} == {"d"})

    # Second scan a bit later: one new video, old ones gained views.
    scan["items"] = [item("a", 1300, 24 * 5), item("b", 1100, 24 * 4), item("c", 900, 24 * 3),
                     item("d", 9000, 24 * 2), item("g", 1200, 6)]
    out2 = json.loads(await plug._monitor({"profiles": "shop"}, mctx))
    by2 = {v["id"]: v for v in out2["videos"]}
    check("monitor: second scan flags the unseen video as new", "new" in by2["g"]["flags"] and out2["counts"]["new"] == 1)
    check("monitor: views gained since the last scan", by2["d"]["views_gain"] == 3000)
    check("monitor: second scan is not a first scan", out2["profiles"][0]["first_scan"] is False)

    everything = json.loads(await plug._monitor({"profiles": "shop", "include_all": True}, mctx))
    check("monitor: include_all returns every video, newest first",
          [v["id"] for v in everything["videos"]] == ["g", "d", "c", "b", "a"])
    recent = json.loads(await plug._monitor({"profiles": "shop", "include_all": True, "days": 3}, mctx))
    check("monitor: days keeps only recent videos", {v["id"] for v in recent["videos"]} == {"g", "d", "c"})

    other = json.loads(await plug._monitor({"profiles": "shop"}, _Ctx("brainOther")))
    check("monitor: another brain has its own scan memory", other["profiles"][0]["first_scan"] is True)

    scan["items"] = [{"url": "https://www.tiktok.com/@ghost", "input": "ghost", "error": "x", "errorCode": "NOT_FOUND"}]
    check("monitor: nothing but errors -> ERROR", (await plug._monitor({"profiles": "ghost"}, mctx)).startswith("ERROR"))

    async def broken(token, input_obj):
        return {"__error": "token sai"}
    plug._run_actor = broken
    r = await plug._monitor({"profiles": "shop"}, mctx)
    check("monitor: Apify failure -> ERROR with the reason", r.startswith("ERROR") and "token sai" in r)
    check("monitor: no profiles -> ERROR", (await plug._monitor({}, mctx)).startswith("ERROR"))
    return mctx

monitor_ctx = asyncio.run(monitor_tests())


# ---- 7. Subtitles ----
vtt = "WEBVTT\n\n1\n00:00:00.000 --> 00:00:02.000\nBulong <b>2300Nm</b>\n\n2\n00:00:02.000 --> 00:00:04.000\nBulong 2300Nm\nbắn tôn luôn\n"
check("vtt_to_text: timings, tags and repeats dropped", plug.vtt_to_text(vtt) == "Bulong 2300Nm bắn tôn luôn")
pick = plug.pick_subtitle({"videoMeta": {"subtitleLinks": [
    {"language": "eng-US", "source": "MT", "downloadLink": "u-mt"},
    {"language": "vie-VN", "source": "ASR", "downloadLink": "u-vi"}]}})
check("pick_subtitle: spoken track before a machine translation", pick["downloadLink"] == "u-vi")
check("pick_subtitle: none -> None", plug.pick_subtitle({"videoMeta": {}}) is None)


# ---- 8. tiktok_analyze_video ----
async def analyze_tests():
    url = "https://www.tiktok.com/@shop/video/7706782226712775943"
    video_item = item("7706782226712775943", 4200, 20, mediaUrls=["https://api.apify.com/v2/key-value-stores/k/records/v"],
                      videoMeta={"duration": 25, "subtitleLinks": [{"language": "vie-VN", "downloadLink": "sub"}]})
    sent = {}

    async def fake_actor(token, input_obj):
        sent["input"] = input_obj
        return [video_item]
    plug._run_actor = fake_actor

    async def fake_text(link, limit=200_000):
        return "WEBVTT\n\n00:00.000 --> 00:02.000\nĐèn 136 LED mất điện vẫn sáng\n"
    plug._get_text = fake_text

    async def fake_download(item_, token, notes):
        return b"\x00\x00\x00\x18ftypmp42"
    plug._download_video = fake_download

    # No Gemini key: words only, said plainly.
    plug._gemini_key = lambda: ""
    out = await plug._analyze({"url": url}, monitor_ctx)
    check("analyze: actor asked for this video with the file", sent["input"]["postURLs"] == [url]
          and sent["input"]["shouldDownloadVideos"] is True)
    check("analyze without Gemini: subtitle text returned", "Đèn 136 LED mất điện vẫn sáng" in out)
    check("analyze without Gemini: says the pictures were not seen", "Chưa xem được hình" in out and "Gemini API key" in out)

    # With Gemini: the prompt carries the numbers, the channel median and the owner's channel.
    seen = {}

    async def fake_gemini(video, prompt, key, notes):
        seen["prompt"], seen["key"], seen["video"] = prompt, key, video
        return "## 1. Video nói gì\nĐèn pin mini cho ngày mất điện."
    plug._gemini_key = lambda: "GEMKEY"
    plug._gemini_analyze = fake_gemini
    out = await plug._analyze({"url": url, "apply_to": "shop đồ mẹ và bé", "lang": "vi"}, monitor_ctx)
    check("analyze with Gemini: analysis returned", "Đèn pin mini cho ngày mất điện" in out)
    check("analyze with Gemini: video and key handed over", seen["key"] == "GEMKEY" and seen["video"].startswith(b"\x00"))
    check("analyze: prompt has the owner's channel", "shop đồ mẹ và bé" in seen["prompt"])
    check("analyze: prompt has the numbers and the channel median from the last scan",
          "4,200 view" in seen["prompt"] and "gấp" in seen["prompt"])
    check("analyze: prompt has the subtitle", "Đèn 136 LED" in seen["prompt"])
    check("analyze: prompt has no em dash", "—" not in seen["prompt"])

    # The video is now marked as analysed for the next scan.
    async def scan_actor(token, input_obj):
        return [item("7706782226712775943", 4300, 21), item("a", 1000, 24 * 5), item("b", 900, 24 * 6)]
    plug._run_actor = scan_actor
    nxt = json.loads(await plug._monitor({"profiles": "shop", "include_all": True}, monitor_ctx))
    mark = {v["id"]: v for v in nxt["videos"]}["7706782226712775943"]
    check("analyze: next scan shows analyzed", mark.get("analyzed") is True)

    async def sensitive(token, input_obj):
        return [{"url": url, "input": url, "error": "sensitive", "errorCode": "POST_SENSITIVE"}]
    plug._run_actor = sensitive
    r = await plug._analyze({"url": url}, monitor_ctx)
    check("analyze: sensitive post -> ERROR in words", r.startswith("ERROR") and "nhạy cảm" in r)
    check("analyze: profile link refused", (await plug._analyze(
        {"url": "https://www.tiktok.com/@shop"}, monitor_ctx)).startswith("ERROR"))
    check("analyze: short link accepted by the URL check", bool(plug.VIDEO_URL_RE.match("https://vt.tiktok.com/ZSabc123/")))

asyncio.run(analyze_tests())


# ---- 9. Prompt language ----
check("reply language: en", plug._reply_language("en") == "English")
check("reply language: vi", plug._reply_language("vi") == "tiếng Việt")

if _fails:
    print(f"\nFAIL - {len(_fails)} test: {_fails}")
    sys.exit(1)
print("\nOK - test_tiktok_monitor: all pass")
