# -*- coding: utf-8 -*-
"""Test đọc video YouTube (youtube_read + plugin bundled youtube-read). Chạy tay:

    python tests/run.py youtube

KHÔNG chạm mạng thật: mọi request đi qua httpx.MockTransport, nên test chạy được cả trên CI
ngoại tuyến. Cái đang kiểm là phần Javis tự viết (tách mã video, chọn phụ đề, ghép lời thoại,
cắt theo trần ký tự, báo lỗi cho ra lỗi), không phải kiểm YouTube còn sống hay không.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401  - nạp server/ vào sys.path
import asyncio
import json
import os
import sys
import tempfile
import time

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-yt-test-"))

import httpx  # noqa: E402
import youtube_read as yt  # noqa: E402


# ------------------------------------------------------------------ dữ liệu giả
def _bot():
    """playerResponse kiểu "YouTube nghi IP máy chủ là robot" - ca hay gặp nhất trên VPS."""
    return _player(captions=False, status="LOGIN_REQUIRED",
                   reason="Sign in to confirm you're not a bot")


def _player(captions=True, status="OK", reason="", asr_only=False):
    tracks = []
    if captions:
        if not asr_only:
            tracks.append({"baseUrl": "https://timedtext/vi", "languageCode": "vi",
                           "name": {"simpleText": "Tiếng Việt"}})
        tracks.append({"baseUrl": "https://timedtext/en-asr", "languageCode": "en",
                       "kind": "asr", "vssId": "a.en", "name": {"simpleText": "English (auto)"}})
    p = {
        "playabilityStatus": {"status": status, "reason": reason},
        "videoDetails": {"title": "Cách bán hàng trên TikTok", "author": "Kênh Thử",
                         "lengthSeconds": "600", "shortDescription": "Mô tả video mẫu."},
    }
    if captions:
        p["captions"] = {"playerCaptionsTracklistRenderer": {
            "captionTracks": tracks,
            "translationLanguages": [{"languageCode": "vi"}, {"languageCode": "ja"}]}}
    return p


def _json3(n=6, buoc=30):
    return {"events": [{"tStartMs": i * buoc * 1000, "segs": [{"utf8": f"cau so {i}"}]}
                       for i in range(n)]}


_TEN_CLIENT = {"VISIONOS": "visionos", "TVHTML5_SIMPLY": "tv_simply", "TVHTML5": "tv",
               "IOS": "ios", "ANDROID": "android", "MWEB": "mweb",
               "WEB_EMBEDDED_PLAYER": "web_embedded", "WEB": "web"}
_THU_TU = ["visionos", "tv_simply", "tv", "ios", "android", "web_embedded", "mweb", "web"]


def _ten_client(req: httpx.Request) -> str:
    """Client nào đang gọi, đọc từ chính body request."""
    try:
        body = json.loads(req.content.decode("utf-8"))
        return _TEN_CLIENT.get(body["context"]["client"]["clientName"], "?")
    except Exception:
        return "?"


def _transport(player=None, caption_body=None, player_status=200, caption_status=200,
               ghi=None, theo_client=None):
    """MockTransport đóng vai YouTube. `ghi` là list để test soi lại request đã gửi.

    `theo_client` = {tên client: player dict hoặc mã HTTP} để giả cảnh YouTube đối xử khác
    nhau với từng client - đúng thứ xảy ra ngoài đời khi nó siết từng đường một.
    """
    def handler(req: httpx.Request) -> httpx.Response:
        if ghi is not None:
            ghi.append(req)
        u = str(req.url)
        if "youtubei/v1/player" in u:
            if theo_client is not None:
                rieng = theo_client.get(_ten_client(req), theo_client.get("*"))
                if isinstance(rieng, int):
                    return httpx.Response(rieng, text="nope")
                if rieng is not None:
                    return httpx.Response(200, json=rieng)
            if player_status != 200:
                return httpx.Response(player_status, text="nope")
            return httpx.Response(200, json=player if player is not None else _player())
        if "timedtext" in u:
            if caption_status != 200:
                return httpx.Response(caption_status, text="nope")
            if isinstance(caption_body, str):
                return httpx.Response(200, text=caption_body)
            return httpx.Response(200, json=caption_body if caption_body is not None else _json3())
        if "/watch" in u:
            return httpx.Response(200, text="<html>khong co gi</html>")
        if u.rstrip("/") in ("https://www.youtube.com", "https://youtube.com"):
            return httpx.Response(200, text='var x={"visitorData":"CgtWSVNJVE9SX0dJRA%3D%3D"};')
        return httpx.Response(404, text="?")
    return httpx.MockTransport(handler)


def _client(**kw):
    return httpx.AsyncClient(transport=_transport(**kw))


async def main():
    # 1) tách mã video khỏi mọi kiểu link người dùng hay dán
    ok = {
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ": "dQw4w9WgXcQ",
        "http://youtube.com/watch?v=dQw4w9WgXcQ&list=PL123&t=42": "dQw4w9WgXcQ",
        "https://youtu.be/dQw4w9WgXcQ?si=abcd": "dQw4w9WgXcQ",
        "https://youtu.be/dQw4w9WgXcQ": "dQw4w9WgXcQ",
        "https://www.youtube.com/shorts/dQw4w9WgXcQ": "dQw4w9WgXcQ",
        "https://m.youtube.com/watch?v=dQw4w9WgXcQ": "dQw4w9WgXcQ",
        "https://music.youtube.com/watch?v=dQw4w9WgXcQ": "dQw4w9WgXcQ",
        "https://www.youtube.com/live/dQw4w9WgXcQ": "dQw4w9WgXcQ",
        "https://www.youtube.com/embed/dQw4w9WgXcQ": "dQw4w9WgXcQ",
        "https://www.youtube-nocookie.com/embed/dQw4w9WgXcQ": "dQw4w9WgXcQ",
        "dQw4w9WgXcQ": "dQw4w9WgXcQ",
        # link nằm lẫn trong câu, có dấu chấm cuối câu
        "em tóm tắt hộ https://youtu.be/dQw4w9WgXcQ. cảm ơn": "dQw4w9WgXcQ",
        "xem cái này nhé www.youtube.com/watch?v=dQw4w9WgXcQ nha": "dQw4w9WgXcQ",
    }
    for raw, mong in ok.items():
        assert yt.parse_video_id(raw) == mong, (raw, yt.parse_video_id(raw))
    for xau in ("", None, "https://vimeo.com/12345", "https://www.youtube.com/@kenh",
                "https://youtu.be/short", "chỉ là chữ thôi"):
        assert yt.parse_video_id(xau) is None, xau

    # 2) chọn phụ đề: người làm trước máy nghe, ngôn ngữ xin trước ngôn ngữ mặc định
    tracks = _player()["captions"]["playerCaptionsTracklistRenderer"]["captionTracks"]
    assert yt.pick_track(tracks)["languageCode"] == "vi"
    assert yt.pick_track(tracks, "en")["languageCode"] == "en"
    assert yt.pick_track([]) is None
    hai_vi = [{"baseUrl": "u1", "languageCode": "vi", "kind": "asr", "vssId": "a.vi"},
              {"baseUrl": "u2", "languageCode": "vi", "vssId": ".vi"}]
    assert yt.pick_track(hai_vi)["baseUrl"] == "u2", "phải ưu tiên bản người làm"
    chi_asr = [{"baseUrl": "u3", "languageCode": "ja", "kind": "asr"}]
    assert yt.pick_track(chi_asr, "vi")["baseUrl"] == "u3", "không có vi/en thì lấy đại"

    # 3) đọc XML cũ: phải unescape HAI lần, phải bỏ thẻ con
    xml = ('<transcript><text start="0.5" dur="2">xin ch&amp;#224;o</text>'
           '<text start="3.25" dur="2">c&#225;i <b>n&#224;y</b> hay</text></transcript>')
    dong = yt.parse_xml(xml)
    assert dong == [(0.5, "xin chào"), (3.25, "cái này hay")], dong

    # 4) ghép lời thoại: gom khối, gắn mốc, bỏ dòng lặp của phụ đề máy nghe
    kq = yt.format_transcript([(0, "a"), (5, "a"), (10, "b"), (100, "c")])
    assert "[0:00] a b" in kq["text"] and "[1:40] c" in kq["text"], kq["text"]
    assert kq["truncated"] is False
    kq2 = yt.format_transcript([(0, "a"), (100, "b")], timestamps=False)
    assert "[" not in kq2["text"] and kq2["text"].splitlines()[0] == "a"
    # start_min: bỏ phần đã đọc lần trước
    kq3 = yt.format_transcript([(0, "dau"), (600, "cuoi")], start_s=300)
    assert "dau" not in kq3["text"] and "cuoi" in kq3["text"]
    # cắt theo trần ký tự + chỉ đúng chỗ đọc tiếp
    # mỗi dòng phải KHÁC nhau: dòng lặp y hệt bị luật chống lặp của phụ đề máy nghe gộp lại
    dai = [(i * 60, f"cau {i:03d} " + "x" * 190) for i in range(20)]
    kq4 = yt.format_transcript(dai, max_chars=1000)
    assert kq4["truncated"] and 0 < kq4["next_start_s"] <= 20 * 60, kq4["next_start_s"]
    assert len(kq4["text"]) <= 1400, len(kq4["text"])

    # 5) đường đọc đầy đủ, có thật sự gọi InnerTube rồi mới tới timedtext
    ghi = []
    async with httpx.AsyncClient(transport=_transport(ghi=ghi)) as c:
        r = await yt.read("https://youtu.be/dQw4w9WgXcQ", client=c)
    assert r["ok"] and r["code"] == "ok", r
    assert r["title"] == "Cách bán hàng trên TikTok" and r["author"] == "Kênh Thử"
    assert r["duration_s"] == 600 and r["video_id"] == "dQw4w9WgXcQ"
    assert r["lang"] == "vi" and "cau so 0" in r["transcript"], r["transcript"][:200]
    pl = [q for q in ghi if "youtubei/v1/player" in str(q.url)]
    tt = [q for q in ghi if "timedtext" in str(q.url)]
    assert pl and tt, [str(q.url) for q in ghi]
    assert "fmt=json3" in str(tt[0].url), str(tt[0].url)
    assert "key=" not in str(pl[0].url) and "prettyPrint=false" in str(pl[0].url), str(pl[0].url)
    txt = yt.render(r)
    assert "LỜI THOẠI" in txt and "cau so 5" in txt and "Kênh Thử" in txt

    # 5b) xin đọc tiếp quá cuối video: phải nói "đã đọc hết", không trả khối rỗng
    async with httpx.AsyncClient(transport=_transport()) as c:
        r = await yt.read("dQw4w9WgXcQ", start_min=99, client=c)
    assert r["ok"] and r["code"] == "exhausted" and r["transcript"] == "", r
    assert "đã đọc HẾT" in yt.render(r)

    # 6) json3 hỏng -> tự lui về XML, không bỏ cuộc
    ghi2 = []
    async with httpx.AsyncClient(transport=_transport(
            caption_body='<text start="1" dur="2">du phong xml</text>', ghi=ghi2)) as c:
        r = await yt.read("dQw4w9WgXcQ", client=c)
    assert r["ok"] and "du phong xml" in r["transcript"], r
    assert len(ghi2) >= 3, "phải thử json3 trước rồi mới tới xml"

    # 7) video không có phụ đề: KHÔNG ok, nhưng vẫn giữ metadata và dặn model đừng bịa
    async with httpx.AsyncClient(transport=_transport(player=_player(captions=False))) as c:
        r = await yt.read("dQw4w9WgXcQ", client=c, cho_phep_ytdlp=False)
    assert r["ok"] is False and r["code"] == "no_captions", r
    assert r["title"], "vẫn phải có tiêu đề để Javis nói được đang bàn video nào"
    txt = yt.render(r)
    assert "KHÔNG đọc được" in txt and "ĐỪNG bịa" in txt.replace("đừng bịa", "ĐỪNG bịa")
    assert "Mô tả video" in txt

    # 8) video riêng tư / đã gỡ: nói đúng lý do, không nói chung chung
    async with httpx.AsyncClient(transport=_transport(
            player=_player(status="LOGIN_REQUIRED", reason="Sign in to confirm your age"))) as c:
        r = await yt.read("dQw4w9WgXcQ", client=c, cho_phep_ytdlp=False)
    assert r["code"] == "unavailable" and "giới hạn tuổi" in r["error"], r
    async with httpx.AsyncClient(transport=_transport(player=_player(status="ERROR"))) as c:
        r = await yt.read("dQw4w9WgXcQ", client=c, cho_phep_ytdlp=False)
    assert r["code"] == "unavailable" and "không tồn tại" in r["error"], r

    # 9) YouTube chặn sạch (InnerTube 403 + trang watch rỗng): báo bị chặn, không im lặng
    async with httpx.AsyncClient(transport=_transport(player_status=403)) as c:
        r = await yt.read("dQw4w9WgXcQ", client=c, cho_phep_ytdlp=False)
    assert r["ok"] is False and r["code"] == "blocked", r
    assert any("403" in str(n) for n in r["notes"]), r["notes"]
    assert "chặn" in yt.render(r)

    # 10) link rác: trả lỗi tử tế chứ không nổ
    r = await yt.read("https://example.com/abc", cho_phep_ytdlp=False)
    assert r["ok"] is False and r["code"] == "bad_url", r

    # 11) cào trang watch làm dự phòng khi InnerTube chết hẳn
    pl = json.dumps(_player())
    def h_watch(req: httpx.Request) -> httpx.Response:
        u = str(req.url)
        if "youtubei/v1/player" in u:
            return httpx.Response(500, text="down")
        if "/watch" in u:
            return httpx.Response(200, text="<script>var ytInitialPlayerResponse = "
                                  + pl + ";var x=1;</script>")
        return httpx.Response(200, json=_json3())
    async with httpx.AsyncClient(transport=httpx.MockTransport(h_watch)) as c:
        r = await yt.read("dQw4w9WgXcQ", client=c)
    assert r["ok"] and r["title"] == "Cách bán hàng trên TikTok", r

    # 12) plugin bundled: có mặt, bật sẵn, chạy được ở mức chỉ-đọc (loop suggest vẫn tóm tắt được)
    import plugins_host
    plugins_host.invalidate()
    desc = {d["slug"]: d for d in plugins_host.describe(None)}
    assert "youtube-read" in desc, sorted(desc)
    assert desc["youtube-read"]["enabled"] and desc["youtube-read"]["loaded"], desc["youtube-read"]
    assert desc["youtube-read"]["min_mode"] == "readonly"
    tools, route = plugins_host.plugin_tools("suggest", None)
    assert "javis_youtube_read" in {t["fn"] for t in tools}, "tool phải chạy được cả ở chế độ suggest"
    out = await route["javis_youtube_read"]["call"]({})
    assert out.startswith("ERROR:"), out
    mo_ta = [t for t in tools if t["fn"] == "javis_youtube_read"][0]["description"]
    assert "WebFetch" in mo_ta, "mô tả phải chặn engine CLI đi nhầm đường WebFetch"

    # 13) đường dây plugin -> module -> render còn nguyên (tham số truyền đúng, kết quả render ra chữ)
    da_goi = {}

    async def _gia(url, lang=None, timestamps=True, start_min=0.0, max_chars=0):
        da_goi.update(url=url, lang=lang, timestamps=timestamps, start_min=start_min)
        return {"ok": True, "code": "ok", "title": "Video thử", "url": url,
                "transcript": "[0:00] noi dung that", "track": "Tiếng Việt (vi, người làm)"}

    goc_read = yt.read
    yt.read = _gia
    try:
        out = await route["javis_youtube_read"]["call"](
            {"url": "https://youtu.be/dQw4w9WgXcQ", "lang": "en", "start_min": 12, "timestamps": False})
    finally:
        yt.read = goc_read
    assert da_goi["lang"] == "en" and da_goi["start_min"] == 12.0 and da_goi["timestamps"] is False, da_goi
    assert "noi dung that" in out and "Video thử" in out, out

    # ============================================================
    # Nhóm chống-chặn (0.41.0). Đây là ca THẬT làm hỏng video của chủ repo trên VPS.
    # ============================================================
    # 14) client đầu bị nghi robot, client sau vẫn chạy -> PHẢI đọc được.
    #     Bản 0.40.0 dừng ngay ở client đầu nên chết đúng ca này.
    ghi3 = []
    async with httpx.AsyncClient(transport=_transport(
            theo_client={"visionos": _bot(), "tv_simply": _bot(), "tv": _player()},
            ghi=ghi3)) as c:
        r = await yt.read("dQw4w9WgXcQ", client=c, cho_phep_ytdlp=False)
    assert r["ok"] and r["code"] == "ok", r
    assert r["source"] == "innertube/tv", r.get("source")
    assert "cau so 0" in r["transcript"]
    da_thu = [_ten_client(q) for q in ghi3 if "youtubei" in str(q.url)]
    assert da_thu[:3] == ["visionos", "tv_simply", "tv"], da_thu

    # 15) MỌI client đều nghi robot -> báo ĐÚNG là bị chặn IP, và TUYỆT ĐỐI không được
    #     bảo người dùng rằng video riêng tư (họ sẽ đi mở quyền một video vốn đã công khai).
    async with httpx.AsyncClient(transport=_transport(theo_client={"*": _bot()})) as c:
        r = await yt.read("dQw4w9WgXcQ", client=c, cho_phep_ytdlp=False)
    assert r["ok"] is False and r["code"] == "blocked", r
    assert "robot" in r["error"] and "không hề riêng tư" in r["error"], r["error"]
    assert "riêng tư." not in r["error"], r["error"]

    # 16) ưu tiên lý do: video ĐÃ GỠ là sự thật về chính video nên thắng "nghi robot",
    #     vốn chỉ là chuyện của IP máy chủ.
    async with httpx.AsyncClient(transport=_transport(
            theo_client={"*": _bot(), "web": _player(captions=False, status="ERROR")})) as c:  # noqa: E501
        r = await yt.read("dQw4w9WgXcQ", client=c, cho_phep_ytdlp=False)
    assert r["code"] == "unavailable" and "không tồn tại" in r["error"], r

    # 17) đổi info yt-dlp sang khuôn captionTracks (hàm thuần, không cần cài yt-dlp)
    conv = yt._tu_ytdlp_info({
        "title": "Video từ yt-dlp", "uploader": "Kênh X", "duration": 754.2,
        "description": "mô tả", "is_live": False,
        "subtitles": {"vi": [{"ext": "vtt", "url": "https://timedtext/vi?fmt=vtt&v=1"},
                             {"ext": "json3", "url": "https://timedtext/vi?fmt=json3&v=1"}],
                      "live_chat": [{"ext": "json", "url": "https://x/live"}]},
        "automatic_captions": {"en": [{"ext": "srv3", "url": "https://timedtext/en?fmt=srv3"}],
                               "ja": [{"ext": "vtt"}]},
    })
    assert conv["meta"]["title"] == "Video từ yt-dlp" and conv["meta"]["duration_s"] == 754
    ma_track = {t["languageCode"]: t for t in conv["tracks"]}
    assert set(ma_track) == {"vi", "en"}, sorted(ma_track)  # live_chat bỏ, ja thiếu url nên bỏ
    assert "fmt=" not in ma_track["vi"]["baseUrl"], ma_track["vi"]["baseUrl"]
    assert ma_track["vi"]["kind"] == "" and ma_track["en"]["kind"] == "asr"

    # 18) yt-dlp gánh khi mọi đường tự viết đều bị chặn
    goc_ytdlp = yt._ytdlp

    async def _ytdlp_gia(url, notes, timeout_s=75.0):
        notes.append("yt-dlp: (giả lập)")
        return yt._tu_ytdlp_info({
            "title": "Cứu bởi yt-dlp", "uploader": "Kênh Y", "duration": 300,
            "subtitles": {"vi": [{"ext": "json3", "url": "https://timedtext/vi?fmt=json3"}]},
        })

    yt._ytdlp = _ytdlp_gia
    try:
        async with httpx.AsyncClient(transport=_transport(theo_client={"*": _bot()})) as c:
            r = await yt.read("dQw4w9WgXcQ", client=c)
    finally:
        yt._ytdlp = goc_ytdlp
    assert r["ok"] and r["source"] == "yt-dlp", r
    assert r["title"] == "Cứu bởi yt-dlp" and "cau so 0" in r["transcript"], r
    assert "Đọc được qua: yt-dlp" in yt.render(r)

    # 19) yt-dlp cũng thua -> vẫn phải báo tử tế, không nổ, không im lặng
    async def _ytdlp_thua(url, notes, timeout_s=75.0):
        notes.append("yt-dlp: RuntimeError: chặn nốt")
        return None

    yt._ytdlp = _ytdlp_thua
    try:
        async with httpx.AsyncClient(transport=_transport(theo_client={"*": _bot()})) as c:
            r = await yt.read("dQw4w9WgXcQ", client=c)
    finally:
        yt._ytdlp = goc_ytdlp
    assert r["ok"] is False and r["code"] == "blocked", r
    assert "yt-dlp" in yt.render(r), "phải nói đã thử cả yt-dlp"

    # 20) bỏ tham số fmt khỏi URL phụ đề mà không phá các tham số khác
    assert yt._bo_fmt("https://a/b?v=1&fmt=vtt&k=2") == "https://a/b?v=1&k=2"
    assert yt._bo_fmt("https://a/b?v=1") == "https://a/b?v=1"
    assert yt._them_tham_so("https://a/b?v=1", fmt="json3") == "https://a/b?v=1&fmt=json3"
    assert yt._them_tham_so("https://a/b", fmt="json3", tlang="") == "https://a/b?fmt=json3"

    # 21) dàn client: đủ sáu, xếp đúng thứ tự chịu đòn, và client nhúng có khai embedUrl
    ds = yt._clients()
    assert [x[0] for x in ds] == _THU_TU, [x[0] for x in ds]
    nhung = [x for x in ds if x[0] == "web_embedded"][0]
    # embedUrl PHẢI là trang ngoài YouTube: khai youtube.com là YouTube từ chối (yt-dlp dùng
    # reddit.com kèm chú thích "Can be any valid non-YouTube URL"). Bản trước khai nhầm.
    eu = nhung[1]["context"]["thirdParty"]["embedUrl"]
    assert eu and "youtube.com" not in eu, eu
    assert nhung[2].get("Referer") == eu
    for _, pl, _h in ds:
        c = pl["context"]["client"]
        assert c["hl"] == "en" and c["timeZone"] == "UTC" and c["utcOffsetMinutes"] == 0
        assert "gl" not in c, "yt-dlp không gửi gl, mình cũng đừng gửi"
    # phiên bản client phải khớp bảng của yt-dlp đang cài, không được tụt lại cả năm
    try:
        from yt_dlp.extractor.youtube._base import INNERTUBE_CLIENTS as _IC
    except Exception:
        _IC = None
    if _IC:
        # CHỈ CẢNH BÁO, không assert. yt-dlp bump phiên bản client theo nhịp riêng của nó;
        # bắt CI đỏ vì chuyện đó là đổ lỗi nhầm người và sẽ khiến người ta tắt test đi.
        lech = []
        for ten, ctx, _num, _n in yt._CLIENT_SPECS:
            if ten not in _IC:
                lech.append(f"{ten}: yt-dlp đã bỏ client này")
                continue
            that = _IC[ten]["INNERTUBE_CONTEXT"]["client"]
            if ctx["clientVersion"] != that["clientVersion"]:
                lech.append(f"{ten}: {ctx['clientVersion']} vs yt-dlp {that['clientVersion']}")
        if lech:
            print("       LƯU Ý dàn client đã lệch so với yt-dlp đang cài, nên cập nhật:")
            for x in lech:
                print(f"         - {x}")

    # 21b) danh sách client ghim cho yt-dlp phải RỖNG (để yt-dlp tự chọn theo bản nó bảo trì).
    #      Bản trước ghim tên tv_embedded đã bị xoá khỏi yt-dlp, tự tay vô hiệu quân dự bị.
    assert yt._YTDLP_CLIENTS == [], yt._YTDLP_CLIENTS

    # 22) trần thời gian tổng: hết giờ thì DỪNG THỬ, không cắm đầu gọi nốt sáu client.
    #     Không có chốt này thì một lần mạng bị nuốt gói làm treo lượt chat vài phút.
    ghi4 = []
    async with httpx.AsyncClient(transport=_transport(ghi=ghi4)) as c:
        pl, nguon = await yt._player_response(c, "dQw4w9WgXcQ", [], [],
                                              han=time.monotonic() - 1)
    assert pl is None and nguon == "" and ghi4 == [], "hết giờ mà vẫn gọi mạng"
    assert yt.TONG_TIMEOUT_S <= 120, "trần tổng đừng để dài quá một lượt chat chịu được"

    # ============================================================
    # Nhóm chống-dịch-máy (0.41.1). Đây là ca ĐÃ HỎNG THẬT trên VPS chủ repo ngày 22/08.
    # ============================================================
    # 23) LÝ DO BẰNG TIẾNG VIỆT vẫn phải nhận ra là "bị nghi robot".
    #     Bản 0.41.0 hỏi YouTube bằng hl=vi nên nhận lý do tiếng Việt, mà bộ dò chỉ có chuỗi
    #     tiếng Anh -> trượt sạch -> báo nhầm thành "video riêng tư", đúng ảnh chụp màn hình.
    ma, ly_do = yt._khong_xem_duoc({"playabilityStatus": {
        "status": "LOGIN_REQUIRED", "reason": "Đăng nhập để xác nhận bạn không phải robot"}})
    assert ma == "robot", f"lý do tiếng Việt bị phân loại nhầm thành {ma!r}"
    assert "không hề riêng tư" in ly_do, ly_do

    # 24) và câu hỏi gửi đi PHẢI bằng tiếng Anh, để lý do về luôn ổn định.
    #     Đây mới là lớp phòng thủ chính; danh sách tiếng Việt ở trên chỉ là lưới thứ hai.
    assert yt.HL_HOI == "en"
    ghi5 = []
    async with httpx.AsyncClient(transport=_transport(ghi=ghi5)) as c:
        await yt.read("dQw4w9WgXcQ", lang="vi", client=c, cho_phep_ytdlp=False)
    hoi = [json.loads(q.content.decode("utf-8")) for q in ghi5 if "youtubei" in str(q.url)]
    assert hoi, "không có request InnerTube nào"
    assert hoi and all(h["context"]["client"]["hl"] == "en" for h in hoi), \
        "vẫn còn hỏi InnerTube bằng thứ tiếng của người dùng"

    # 25) cờ CẤU TRÚC cho giới hạn tuổi: nhận ra kể cả khi không có chữ nào khớp
    ma, _ = yt._khong_xem_duoc({"playabilityStatus": {
        "status": "LOGIN_REQUIRED", "reason": "以下の動画は年齢制限があります",
        "desktopLegacyAgeGateReason": 1}})
    assert ma == "tuoi", ma

    # 26) đòi đăng nhập mà KHÔNG rõ vì sao -> nói thẳng là chưa phân biệt được, KHÔNG đoán bừa.
    #     Đoán "riêng tư" thì người dùng đi mở quyền vô ích; đoán "robot" thì họ ngồi thử lại
    #     một video không bao giờ vào được. Cả hai đều tệ hơn là nói thật.
    ma, ly_do = yt._khong_xem_duoc({"playabilityStatus": {
        "status": "LOGIN_REQUIRED", "reason": "Sign in"}})
    assert ma == "dang_nhap", ma
    assert "Hai khả năng" in ly_do and "ẩn danh" in ly_do, ly_do

    # 27) lý do nằm trong errorScreen thay vì reason thì vẫn phải đọc ra
    ma, _ = yt._khong_xem_duoc({"playabilityStatus": {
        "status": "LOGIN_REQUIRED", "errorScreen": {"playerErrorMessageRenderer": {
            "reason": {"runs": [{"text": "Sign in to confirm you"},
                                {"text": "'re not a bot"}]}}}}})
    assert ma == "robot", ma

    # 28) khi hỏng, phần chẩn đoán PHẢI hiện ra. Bản trước ghi "chỉ nói khi người dùng hỏi"
    #     nên model nuốt luôn, và sự cố thật trên VPS thành ra không có bằng chứng nào để lần.
    async with httpx.AsyncClient(transport=_transport(theo_client={"*": _bot()})) as c:
        r = await yt.read("dQw4w9WgXcQ", client=c, cho_phep_ytdlp=False)
    ra = yt.render(r)
    assert "ĐÃ THỬ NHỮNG ĐƯỜNG SAU" in ra and "chép nguyên khối" in ra, ra
    assert "chỉ nói khi người dùng hỏi" not in ra
    for ten in _THU_TU:
        assert ten in ra, f"phần chẩn đoán thiếu đường {ten}"
    assert "youtube_read.py" in ra, "phải chỉ đường tới lệnh tự kiểm"

    # 29) lệnh tự kiểm: báo cáo phải nêu ĐỦ từng đường, kể cả đường hỏng.
    #     Bơm client giả + thay nhánh yt-dlp để test KHÔNG chạm mạng thật (bản nháp đầu của
    #     chính ca này có gọi mạng, đúng lỗi vừa cấm ở vòng trước).
    async def _yt_kiem(url, notes, timeout_s=75.0):
        notes.append("yt-dlp: (giả lập) không có phụ đề")
        return None

    yt._ytdlp = _yt_kiem
    try:
        async with httpx.AsyncClient(transport=_transport(
                theo_client={"*": _bot(), "web": _player()})) as c:
            bao_cao = await yt.tu_kiem("https://youtu.be/dQw4w9WgXcQ", client=c)
    finally:
        yt._ytdlp = goc_ytdlp
    assert "TU KIEM" in bao_cao and "KET LUAN" in bao_cao and "dQw4w9WgXcQ" in bao_cao
    assert "visitorData" in bao_cao, "báo cáo phải nói lấy được visitorData hay không"
    for ten in _THU_TU:
        assert ten in bao_cao, f"báo cáo thiếu đường {ten}"
    assert "Trang watch" in bao_cao and "yt-dlp" in bao_cao
    assert "LAY DUOC phu de" in bao_cao, "client web đọc được thì kết luận phải nói vậy"
    assert "robot" in bao_cao, "phải in ra phân loại của từng đường để lần ra bệnh"

    # ============================================================
    # Nhóm chống-mù (0.41.1). Do một vòng audit đối kháng tìm ra, đều là lỗi làm hỏng
    # ĐÚNG ca thật của chủ repo mà hai vòng sửa trước không chạm tới.
    # ============================================================
    # 30) LỖI NẶNG NHẤT: response bị nghi robot của YouTube KHÔNG có videoDetails/captions.
    #     Bản trước lọc "thiếu captions/videoDetails" TRƯỚC khi phân loại, nên nó bị vứt ngay
    #     tại cửa, chan_doan rỗng, và người dùng nhận câu chung chung "chặn máy chủ hoặc mạng
    #     hỏng". Đó cũng là lý do bản vá ghim tiếng Anh trước đó không với tới được.
    bot_tran = {"responseContext": {}, "trackingParams": "x", "playabilityStatus": {
        "status": "LOGIN_REQUIRED", "reason": "Sign in to confirm you're not a bot"}}
    async with httpx.AsyncClient(transport=_transport(theo_client={"*": bot_tran})) as c:
        r = await yt.read("dQw4w9WgXcQ", client=c, cho_phep_ytdlp=False)
    assert r["code"] == "blocked" and "robot" in r["error"], r
    assert "không hề riêng tư" in r["error"], r["error"]
    assert sum(1 for n in r["notes"] if "robot" in str(n)) >= len(_THU_TU), r["notes"]

    # 31) một client ĐỌC ĐƯỢC video thì lời phàn nàn của client khác không còn là chẩn đoán:
    #     video rõ ràng không bị chặn, nó chỉ không có phụ đề.
    async with httpx.AsyncClient(transport=_transport(
            theo_client={"*": _bot(), "web": _player(captions=False)})) as c:
        r = await yt.read("dQw4w9WgXcQ", client=c, cho_phep_ytdlp=False)
    assert r["code"] == "no_captions", f'{r["code"]}: {r.get("error")}'
    assert r["title"], "đã đọc được tiêu đề mà lại đi báo bị chặn là vô lý"

    # 32) opts của yt-dlp phải có ignore_no_formats_error. Thiếu đúng một dòng này là trên
    #     máy chủ bị nghi robot, yt-dlp ném lỗi ở bước dựng format và VỨT LUÔN phụ đề nó đã
    #     trích được - tức quân dự bị vô dụng đúng lúc cần nó nhất.
    ghi_opts = {}

    class _YdlGia:
        def __init__(self, opts): ghi_opts.update(opts)
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def extract_info(self, url, download=False):
            return {"title": "T", "subtitles": {"vi": [{"ext": "json3", "url": "https://timedtext/vi"}]}}

    import types
    gia_mod = types.ModuleType("yt_dlp")
    gia_mod.YoutubeDL = _YdlGia
    cu_mod = sys.modules.get("yt_dlp")
    sys.modules["yt_dlp"] = gia_mod
    try:
        kq = yt._ytdlp_sync("https://www.youtube.com/watch?v=x")
    finally:
        if cu_mod is not None:
            sys.modules["yt_dlp"] = cu_mod
        else:
            sys.modules.pop("yt_dlp", None)
    assert ghi_opts.get("ignore_no_formats_error") is True, ghi_opts
    assert ghi_opts.get("writesubtitles") and ghi_opts.get("writeautomaticsub"), ghi_opts
    assert "extractor_args" not in ghi_opts, "đừng ghim client cho yt-dlp nữa"
    assert kq["tracks"] and kq["meta"]["title"] == "T"

    # 33) render KHÔNG được khẳng định đã thử yt-dlp khi nó chưa hề chạy. Nói sai chỗ này tốn
    #     của người dùng cả buổi: họ tin là hết cách trong khi chỉ cần cài một gói.
    assert "CHƯA CÀI" in yt._cau_ytdlp({"ytdlp": "chua_cai"}).upper()
    assert "pip install" in yt._cau_ytdlp({"ytdlp": "chua_cai"})
    assert "chưa được chạy" in yt._cau_ytdlp({"ytdlp": "bo_qua"})
    assert "đều bị từ chối" in yt._cau_ytdlp({"ytdlp": "da_chay"})
    async with httpx.AsyncClient(transport=_transport(theo_client={"*": _bot()})) as c:
        r = await yt.read("dQw4w9WgXcQ", client=c, cho_phep_ytdlp=False)
    assert r["ytdlp"] == "tat"
    assert "đã thử đủ" not in yt.render(r), "không được khoe đã thử yt-dlp khi nó bị tắt"

    # 34) đặt tham số URL phải THAY chứ không nối: baseUrl thường đã có sẵn fmt=srv3, nối thêm
    #     là YouTube lấy giá trị đầu rồi trả XML, tốn một vòng mạng thừa.
    assert yt._them_tham_so("https://a/b?fmt=srv3&v=1", fmt="json3") == "https://a/b?v=1&fmt=json3"
    assert yt._them_tham_so("https://a/b?v=1", c="WEB") == "https://a/b?v=1&c=WEB"

    # 35) track bị YouTube bắt token chứng thực: nhận ra qua exp=xpe/xpv, né nếu còn track khác
    assert yt._can_pot("https://t/x?exp=xpe&v=1") and not yt._can_pot("https://t/x?v=1")
    hai = [{"baseUrl": "https://t/a?exp=xpv", "languageCode": "vi"},
           {"baseUrl": "https://t/b", "languageCode": "vi"}]
    assert yt.pick_track(hai)["baseUrl"] == "https://t/b", "phải né track đòi token"

    print("OK - test_youtube_read: tất cả assertion pass")


if __name__ == "__main__":
    asyncio.run(main())
