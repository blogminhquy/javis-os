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
import tempfile

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-yt-test-"))

import httpx  # noqa: E402
import youtube_read as yt  # noqa: E402


# ------------------------------------------------------------------ dữ liệu giả
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


def _transport(player=None, caption_body=None, player_status=200, caption_status=200,
               ghi=None):
    """MockTransport đóng vai YouTube. `ghi` là list để test soi lại request đã gửi."""
    def handler(req: httpx.Request) -> httpx.Response:
        if ghi is not None:
            ghi.append(req)
        u = str(req.url)
        if "youtubei/v1/player" in u:
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
    assert "youtubei/v1/player" in str(ghi[0].url)
    assert "fmt=json3" in str(ghi[1].url), str(ghi[1].url)
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
        r = await yt.read("dQw4w9WgXcQ", client=c)
    assert r["ok"] is False and r["code"] == "no_captions", r
    assert r["title"], "vẫn phải có tiêu đề để Javis nói được đang bàn video nào"
    txt = yt.render(r)
    assert "KHÔNG đọc được" in txt and "ĐỪNG bịa" in txt.replace("đừng bịa", "ĐỪNG bịa")
    assert "Mô tả video" in txt

    # 8) video riêng tư / đã gỡ: nói đúng lý do, không nói chung chung
    async with httpx.AsyncClient(transport=_transport(
            player=_player(status="LOGIN_REQUIRED", reason="Sign in to confirm your age"))) as c:
        r = await yt.read("dQw4w9WgXcQ", client=c)
    assert r["code"] == "unavailable" and "đăng nhập" in r["error"], r
    async with httpx.AsyncClient(transport=_transport(player=_player(status="ERROR"))) as c:
        r = await yt.read("dQw4w9WgXcQ", client=c)
    assert r["code"] == "unavailable" and "không tồn tại" in r["error"], r

    # 9) YouTube chặn sạch (InnerTube 403 + trang watch rỗng): báo bị chặn, không im lặng
    async with httpx.AsyncClient(transport=_transport(player_status=403)) as c:
        r = await yt.read("dQw4w9WgXcQ", client=c)
    assert r["ok"] is False and r["code"] == "blocked", r
    assert any("403" in str(n) for n in r["notes"]), r["notes"]
    assert "chặn" in yt.render(r)

    # 10) link rác: trả lỗi tử tế chứ không nổ
    r = await yt.read("https://example.com/abc")
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

    print("OK - test_youtube_read: tất cả assertion pass")


if __name__ == "__main__":
    asyncio.run(main())
