"""Test connector Facebook Trang (Graph API) BYO app (v0.9.90). Chạy tay / CI:

    python tests/run.py meta_pages

KHÔNG mạng (giả _get/_post). Phủ: catalog connector hợp lệ (provider meta, scope Trang, guide
localhost), plugin nạp đủ 5 tool + đúng min_mode (đọc readonly, đăng/trả lời full), gate chưa-kết-
nối, chọn Trang (1 Trang tự lấy, nhiều Trang bắt chỉ rõ), đăng bài dùng token Trang, trả lời
bình luận, đọc bình luận suy Trang từ post_id, và fb_pages_list KHÔNG lộ access_token của Trang.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401  - nạp server/ vào sys.path (xem tests/python/_paths.py)
import asyncio
import importlib.util
import json
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-metapages-"))

_fails = []
def check(n, c):
    print(("ok  " if c else "FAIL ") + n)
    if not c: _fails.append(n)


# ---- 1. Connector: đã dọn sang kho ----
# Khuôn connector `facebook-pages` rời `system/mcp-catalog.json` ở 0.55.36 và giờ sống trong gói
# `javis.facebook-pages` của repo kho (blogminhquy/javis-store). Những assert về HÌNH DẠNG của nó
# (provider, scope, fields, default_perm, phân loại tool, chữ cảnh báo) đi theo dữ liệu sang đó:
# `tools/kiem-tra.py` của repo kho chạy đúng các phép kiểm ấy trên mọi Pull Request.
#
# Giữ lại ở đây là giả vờ: dữ liệu đổi được trong kho mà KHÔNG cần bản Javis mới, nên một test
# ở repo này chỉ canh được bản chụp lúc dọn nhà chứ không canh được thứ người dùng thật sự cài.
# Phần bên dưới - plugin đi kèm - vẫn là mã của app nên vẫn kiểm ở đây.


# ---- 2. Plugin nạp + min_mode ----
spec = importlib.util.spec_from_file_location(
    "meta_pages_graph_test", str(ROOT / "system" / "plugins" / "meta-pages-graph" / "plugin.py"))
plug = importlib.util.module_from_spec(spec)
spec.loader.exec_module(plug)


class _Ctx:
    def __init__(self): self.tools = []
    def register_tool(self, name, description, handler, schema=None, min_mode="readonly", check_fn=None, **k):
        self.tools.append({"name": name, "handler": handler, "min_mode": min_mode, "check_fn": check_fn})


ctx = _Ctx()
plug.register(ctx)
byname = {t["name"]: t for t in ctx.tools}
check("plugin: đủ 10 tool", set(byname) == {"fb_pages_list", "fb_page_posts", "fb_page_comments",
                                            "fb_page_post", "fb_page_photo", "fb_page_album",
                                            "fb_page_video", "fb_page_edit", "fb_page_delete",
                                            "fb_page_reply"})
check("plugin: tool đọc = readonly",
      all(byname[n]["min_mode"] == "readonly" for n in ("fb_pages_list", "fb_page_posts", "fb_page_comments")))
check("plugin: tool ghi (đăng/ảnh/album/video/sửa/xoá/trả lời) = full",
      all(byname[n]["min_mode"] == "full"
          for n in ("fb_page_post", "fb_page_photo", "fb_page_album", "fb_page_video",
                    "fb_page_edit", "fb_page_delete", "fb_page_reply")))

# chưa kết nối → _check chặn
plug._connected_id = lambda: None
check("plugin: _check chặn khi chưa kết nối", "Chưa kết nối" in (plug._check() or ""))


# ---- 3. Handler (giả token + _get/_post, không mạng) ----
async def handler_tests():
    plug._connected_id = lambda: "cfbp"
    async def _fake_token(): return "USERTOK"
    plug._token = _fake_token

    calls = {}
    pages_data = {"data": [{"id": "P1", "name": "Shop A", "category": "Retail",
                            "access_token": "PTOKA", "tasks": ["MANAGE", "CREATE_CONTENT"]}]}

    async def _fake_get(path, params, token):
        calls["get"] = (path, params, token)
        if path == "me/accounts":
            return pages_data
        if path.endswith("/feed"):
            return {"data": [{"id": "P1_10", "message": "hi", "permalink_url": "http://x"}]}
        if path.endswith("/comments"):
            return {"data": [{"id": "c1", "message": "hay qua", "from": {"name": "Khach"}}]}
        return {"data": []}

    async def _fake_post(path, data, token):
        calls["post"] = (path, data, token)
        return {"id": "NEWID"}

    plug._get = _fake_get
    plug._post = _fake_post

    # fb_pages_list: KHÔNG lộ access_token của Trang
    r_list = await plug._list({}, None)
    check("fb_pages_list: có tên Trang", "Shop A" in r_list)
    check("fb_pages_list: KHÔNG lộ page access_token", "PTOKA" not in r_list)

    # _resolve_page: 1 Trang → tự lấy, dùng token Trang
    pid, ptok, pname, err = await plug._resolve_page({}, "USERTOK")
    check("_resolve_page: 1 Trang tự lấy + token Trang", pid == "P1" and ptok == "PTOKA" and err is None)

    # fb_page_posts: gọi feed bằng TOKEN TRANG (không phải token cá nhân)
    await plug._posts({}, None)
    check("fb_page_posts: dùng token Trang gọi P1/feed",
          calls["get"][0] == "P1/feed" and calls["get"][2] == "PTOKA")

    # fb_page_comments: suy Trang từ post_id P1_10, đọc P1_10/comments
    await plug._comments({"post_id": "P1_10"}, None)
    check("fb_page_comments: đọc {post}/comments bằng token Trang",
          calls["get"][0] == "P1_10/comments" and calls["get"][2] == "PTOKA")
    r_noid = await plug._comments({}, None)
    check("fb_page_comments: thiếu post_id → ERROR", r_noid.startswith("ERROR"))

    # fb_page_post: POST P1/feed bằng token Trang, có message
    r_pub = await plug._publish({"message": "Xin chao ca nha"}, None)
    check("fb_page_post: POST P1/feed + token Trang + message",
          calls["post"][0] == "P1/feed" and calls["post"][2] == "PTOKA"
          and calls["post"][1].get("message") == "Xin chao ca nha")
    check("fb_page_post: trả ok + post_id", '"ok": true' in r_pub.lower() and "NEWID" in r_pub)
    r_pub_empty = await plug._publish({}, None)
    check("fb_page_post: thiếu message/link → ERROR", r_pub_empty.startswith("ERROR"))

    # fb_page_reply: POST {comment}/comments
    r_rep = await plug._reply({"comment_id": "c1", "message": "Cam on ban"}, None)
    check("fb_page_reply: POST c1/comments + token Trang",
          calls["post"][0] == "c1/comments" and calls["post"][2] == "PTOKA"
          and calls["post"][1].get("message") == "Cam on ban")
    check("fb_page_reply: trả ok + reply_id", '"ok": true' in r_rep.lower() and "NEWID" in r_rep)
    r_rep_nomsg = await plug._reply({"comment_id": "c1"}, None)
    check("fb_page_reply: thiếu message → ERROR", r_rep_nomsg.startswith("ERROR"))
    r_rep_notarget = await plug._reply({"message": "hi"}, None)
    check("fb_page_reply: thiếu comment_id/post_id → ERROR", r_rep_notarget.startswith("ERROR"))

    # fb_page_photo: URL → POST {page}/photos với url + caption (không cần vault)
    class _CtxNoVault:
        vault_root = None
    r_ph_url = await plug._publish_photo({"photo": "https://ex.com/a.jpg", "message": "cap"}, _CtxNoVault())
    check("fb_page_photo(URL): POST P1/photos + url + caption + token Trang",
          calls["post"][0] == "P1/photos" and calls["post"][1].get("url") == "https://ex.com/a.jpg"
          and calls["post"][1].get("caption") == "cap" and calls["post"][2] == "PTOKA")
    check("fb_page_photo: trả ok", '"ok": true' in r_ph_url.lower())
    r_ph_miss = await plug._publish_photo({}, _CtxNoVault())
    check("fb_page_photo: thiếu photo → ERROR", r_ph_miss.startswith("ERROR"))

    # fb_page_photo: file trong vault → upload multipart (fake _post_file, không mạng)
    vroot = Path(tempfile.mkdtemp(prefix="javis-fbvault-"))
    (vroot / "attachments").mkdir()
    (vroot / "attachments" / "a.jpg").write_bytes(b"img")

    class _CtxVault:
        vault_root = str(vroot)

    filecalls = {}

    async def _fake_post_file(pathg, fp, data, token, base=plug.GRAPH, timeout=900):
        filecalls["args"] = (pathg, str(fp), data, token, base)
        return {"id": "PH1", "post_id": "P1_PH"}

    plug._post_file = _fake_post_file
    r_ph_file = await plug._publish_photo({"photo": "attachments/a.jpg"}, _CtxVault())
    check("fb_page_photo(file): upload đúng file trong vault + token Trang",
          filecalls["args"][0] == "P1/photos" and filecalls["args"][1].endswith("a.jpg")
          and filecalls["args"][3] == "PTOKA")
    check("fb_page_photo(file): trả ok + photo_id", '"ok": true' in r_ph_file.lower() and "PH1" in r_ph_file)
    r_ph_out = await plug._publish_photo({"photo": "../ben-ngoai.jpg"}, _CtxVault())
    check("fb_page_photo: file NGOÀI vault → ERROR (sandbox)", r_ph_out.startswith("ERROR"))
    r_ph_novault = await plug._publish_photo({"photo": "attachments/a.jpg"}, _CtxNoVault())
    check("fb_page_photo: đường dẫn file mà không rõ vault/staging → ERROR",
          r_ph_novault.startswith("ERROR"))

    # File dán vào khung chat rơi vào STATE_DIR/.staging → phải đăng được (vụ 2026-07-27:
    # "không xác định được vault đang làm việc" dù ảnh do chính chủ vừa gửi).
    import config as _cfg
    staging = Path(_cfg.STATE_DIR) / ".staging" / "up_x"
    staging.mkdir(parents=True, exist_ok=True)
    (staging / "demo.jpg").write_bytes(b"img")
    r_ph_stage_abs = await plug._publish_photo({"photo": str(staging / "demo.jpg")}, _CtxNoVault())
    check("fb_page_photo: đường dẫn TUYỆT ĐỐI trong staging → đăng được",
          '"ok": true' in r_ph_stage_abs.lower())
    r_ph_stage_rel = await plug._publish_photo({"photo": "up_x/demo.jpg"}, _CtxNoVault())
    check("fb_page_photo: đường dẫn tương đối tính từ staging → đăng được",
          '"ok": true' in r_ph_stage_rel.lower())
    r_ph_state = await plug._publish_photo(
        {"photo": str(Path(_cfg.STATE_DIR) / "settings.json")}, _CtxNoVault())
    check("fb_page_photo: file trong STATE_DIR nhưng NGOÀI .staging → ERROR",
          r_ph_state.startswith("ERROR"))

    # fb_page_video: URL → file_url; file trong vault → đi host graph-video
    r_vd_url = await plug._publish_video(
        {"video": "https://ex.com/v.mp4", "message": "mo ta", "title": "T"}, _CtxNoVault())
    check("fb_page_video(URL): POST P1/videos + file_url + description + title",
          calls["post"][0] == "P1/videos" and calls["post"][1].get("file_url") == "https://ex.com/v.mp4"
          and calls["post"][1].get("description") == "mo ta" and calls["post"][1].get("title") == "T")
    check("fb_page_video: trả ok kèm ghi chú xử lý nền", '"ok": true' in r_vd_url.lower())
    (vroot / "clip.mp4").write_bytes(b"vid")
    await plug._publish_video({"video": "clip.mp4"}, _CtxVault())
    check("fb_page_video(file): upload qua host graph-video riêng",
          filecalls["args"][0] == "P1/videos" and filecalls["args"][4] == plug.GRAPH_VIDEO)
    r_vd_miss = await plug._publish_video({}, _CtxNoVault())
    check("fb_page_video: thiếu video → ERROR", r_vd_miss.startswith("ERROR"))

    # fb_page_album: up từng ảnh published=false rồi gom vào MỘT bài /feed
    seq = []

    async def _fake_post_seq(path, data, token):
        seq.append((path, dict(data or {}), token))
        return {"id": f"M{len(seq)}"}

    plug._post = _fake_post_seq
    r_alb = await plug._publish_album(
        {"photos": ["https://ex.com/1.jpg", "attachments/a.jpg"], "message": "Bộ ảnh"}, _CtxVault())
    check("fb_page_album: ảnh URL up published=false",
          seq[0][0] == "P1/photos" and seq[0][1].get("url") == "https://ex.com/1.jpg"
          and seq[0][1].get("published") == "false")
    check("fb_page_album: ảnh file up qua _post_file với published=false",
          filecalls["args"][0] == "P1/photos" and filecalls["args"][2].get("published") == "false")
    feed = seq[-1]
    check("fb_page_album: bài cuối POST P1/feed + message + đủ attached_media",
          feed[0] == "P1/feed" and feed[1].get("message") == "Bộ ảnh"
          and json.loads(feed[1].get("attached_media[0]", "{}")).get("media_fbid") == "M1"
          and json.loads(feed[1].get("attached_media[1]", "{}")).get("media_fbid") == "PH1")
    check("fb_page_album: trả ok + số ảnh", '"ok": true' in r_alb.lower() and '"photos": 2' in r_alb)
    r_alb_1 = await plug._publish_album({"photos": ["https://ex.com/1.jpg"]}, _CtxNoVault())
    check("fb_page_album: 1 ảnh → ERROR chỉ sang fb_page_photo", r_alb_1.startswith("ERROR"))
    r_alb_11 = await plug._publish_album({"photos": [f"https://ex.com/{i}.jpg" for i in range(11)]},
                                         _CtxNoVault())
    check("fb_page_album: 11 ảnh → ERROR trần 10", r_alb_11.startswith("ERROR") and "10" in r_alb_11)
    seq.clear()
    await plug._publish_album({"photos": "https://ex.com/1.jpg, https://ex.com/2.jpg"}, _CtxNoVault())
    check("fb_page_album: photos dạng chuỗi phẩy vẫn hiểu", len(seq) == 3 and seq[-1][0] == "P1/feed")

    # fb_page_edit: sửa message bài đã đăng, tự suy Trang từ post_id
    seq.clear()
    r_ed = await plug._edit_post({"post_id": "P1_10", "message": "Nội dung sửa lại"}, None)
    check("fb_page_edit: POST {post_id} + message MỚI + token Trang",
          seq[-1][0] == "P1_10" and seq[-1][1].get("message") == "Nội dung sửa lại"
          and seq[-1][2] == "PTOKA")
    check("fb_page_edit: trả ok", '"ok": true' in r_ed.lower())
    r_ed_nomsg = await plug._edit_post({"post_id": "P1_10"}, None)
    check("fb_page_edit: thiếu message → ERROR", r_ed_nomsg.startswith("ERROR"))
    r_ed_noid = await plug._edit_post({"message": "x"}, None)
    check("fb_page_edit: thiếu post_id → ERROR", r_ed_noid.startswith("ERROR"))

    # fb_page_delete: DELETE {post_id} bằng token Trang, tự suy Trang từ post_id.
    # Xoá không hoàn tác được nên phải đọc bài TRƯỚC, và bài không đọc được thì
    # KHÔNG được gọi DELETE - tránh xoá mù vào id sai.
    dels = []
    async def _fake_delete(path, token):
        dels.append((path, token))
        return {"success": True}
    plug._delete = _fake_delete

    async def _get_with_post(path, params, token):
        if path == "P1_10":
            return {"id": "P1_10", "message": "Bài cũ cần xoá", "created_time": "2026-07-28T01:00:00+0000"}
        if path == "P1_99":
            return {"error": {"message": "Unsupported get request"}}
        return await _fake_get(path, params, token)
    plug._get = _get_with_post

    r_del = await plug._delete_post({"post_id": "P1_10"}, None)
    check("fb_page_delete: gọi DELETE đúng post_id + token Trang",
          dels and dels[-1][0] == "P1_10" and dels[-1][1] == "PTOKA")
    check("fb_page_delete: trả ok + kèm nội dung vừa xoá để đối chiếu",
          '"ok": true' in r_del.lower() and "Bài cũ cần xoá" in r_del)
    check("fb_page_delete: nói rõ không khôi phục được", "KHÔNG khôi phục" in r_del)

    n_before = len(dels)
    r_del_bad = await plug._delete_post({"post_id": "P1_99"}, None)
    check("fb_page_delete: bài không đọc được → ERROR và KHÔNG gọi DELETE",
          r_del_bad.startswith("ERROR") and len(dels) == n_before)

    r_del_noid = await plug._delete_post({}, None)
    check("fb_page_delete: thiếu post_id → ERROR", r_del_noid.startswith("ERROR"))
    plug._get = _fake_get

    # Nhiều Trang: không chỉ rõ → lỗi kèm danh sách; chỉ rõ tên → chọn đúng
    pages_data["data"].append({"id": "P2", "name": "Shop B", "category": "Retail", "access_token": "PTOKB"})
    _, _, _, err_multi = await plug._resolve_page({}, "USERTOK")
    check("_resolve_page: nhiều Trang mà không chỉ rõ → ERROR liệt kê Trang",
          err_multi and err_multi.startswith("ERROR") and "Shop A" in err_multi and "Shop B" in err_multi)
    pid2, ptok2, _, err2 = await plug._resolve_page({"page": "Shop B"}, "USERTOK")
    check("_resolve_page: khớp theo tên Trang", pid2 == "P2" and ptok2 == "PTOKB" and err2 is None)

    # format lỗi Graph
    check("_fmt: lỗi Graph → ERROR message",
          plug._fmt({"error": {"message": "boom"}}).startswith("ERROR: Facebook API: boom"))

asyncio.run(handler_tests())

if _fails:
    print(f"\nFAIL - {len(_fails)} test: {_fails}")
    sys.exit(1)
print("\nOK - test_meta_pages: tất cả pass")
