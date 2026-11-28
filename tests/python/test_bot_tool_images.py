"""A dedicated bot sends a product photo its data source returned (a POS link), and only that (`bot_images`).

    python tests/run.py bot_tool_images      (no network: a local HTTP server stands in for the CDN)

Owner report 28/11/2026: a customer asked for pictures of cutting discs and the bot could only answer "I have no
picture to send". A POS returns a product's photo as a web link, and a bot could send only files inside its brain.
This file guards:
1. Links are read out of a tool result, and only a dedicated bot's turn records them, for its own chat.
2. `pick` sends a web image only when a tool of this chat's turn (or this turn's documents) gave the link: a link the
   customer typed, another chat's link, or an expired one stays in the text and is never fetched.
3. The fetch: public addresses only (a redirect is checked again), an image content type, at most MAX_BYTES; a link
   fetched before is reused from the cache.
4. The Agent is told where pictures come from and to say plainly when there is none.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import http.server
import os
import sys
import tempfile
import threading
import time

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-bot-tool-img-")
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import bot_images  # noqa: E402

_fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(extra) + "]") if extra and not cond else ""))
    if not cond:
        _fails.append(name)


BOT_TURN = {"kenh": "zalo_personal", "chat_id": "u1", "chat_type": "private", "sender_id": "u1", "la_chu": False}
POS = '{"products": [{"name": "Lưỡi cắt Mingyu", "image": "https://cdn.pos.example/p/mingyu.jpg"}, ' \
      '{"name": "Sói Vàng", "images": ["https://cdn.pos.example/p/soi-vang.png?w=800"]}]}'

# ============================================================
# 1. Recording
# ============================================================
check("links come out of a tool result",
      bot_images.links_in(POS) == ["https://cdn.pos.example/p/mingyu.jpg", "https://cdn.pos.example/p/soi-vang.png?w=800"])
check("trailing punctuation is not part of a link", bot_images.links_in("xem https://a.vn/x.jpg.") == ["https://a.vn/x.jpg"])

bot_images.note_tool_result(POS, BOT_TURN)
check("a bot turn records them for its chat", bot_images.remote_allowed("https://cdn.pos.example/p/mingyu.jpg", "u1"))
check("the same chat under Javis's prefix", bot_images.remote_allowed("https://cdn.pos.example/p/mingyu.jpg", "zalo:u1"))
check("not for another chat", not bot_images.remote_allowed("https://cdn.pos.example/p/mingyu.jpg", "u2"))
check("a link nobody returned is not allowed", not bot_images.remote_allowed("https://evil.example/x.jpg", "u1"))
bot_images.note_tool_result('{"image": "https://owner.example/private.jpg"}', dict(BOT_TURN, la_chu=True, chat_id="u9"))
check("the owner's own turn records nothing", not bot_images.remote_allowed("https://owner.example/private.jpg", "u9"))
bot_images.note_tool_result("ERROR: https://cdn.pos.example/err.jpg", dict(BOT_TURN, chat_id="u8"))
check("a failed call records nothing", not bot_images.remote_allowed("https://cdn.pos.example/err.jpg", "u8"))
bot_images.note_tool_result(POS, None)
check("no turn at all never raises", True)
check("a link of this turn's documents counts",
      bot_images.remote_allowed("https://docs.example/a.jpg", "u3", ["https://docs.example/a.jpg"]))
real_ttl = bot_images.REMOTE_TTL_S
bot_images.REMOTE_TTL_S = -1
check("an expired link is not allowed", not bot_images.remote_allowed("https://cdn.pos.example/p/mingyu.jpg", "u1"))
bot_images.REMOTE_TTL_S = real_ttl

# ============================================================
# 2. pick
# ============================================================
FETCHED = []
real_fetch = bot_images.fetch_remote
bot_images.fetch_remote = lambda url: (FETCHED.append(url), "/cache/" + url.rsplit("/", 1)[-1].split("?")[0])[1]
BRAIN = tempfile.mkdtemp(prefix="brain-")
reply = ("Dạ đây là mẫu Mingyu ạ ![Mingyu](https://cdn.pos.example/p/mingyu.jpg) "
         "và mẫu khách gửi ![x](https://evil.example/x.jpg)")
text, files = bot_images.pick(reply, BRAIN, "u1")
check("the POS photo is sent", [f["path"] for f in files] == ["/cache/mingyu.jpg"], files)
check("with its caption", files and files[0]["caption"] == "Mingyu")
check("and leaves the text", "cdn.pos.example" not in text, text)
check("a link the customer typed stays in the text", "https://evil.example/x.jpg" in text)
check("and is never fetched", FETCHED == ["https://cdn.pos.example/p/mingyu.jpg"], FETCHED)
FETCHED.clear()
text2, files2 = bot_images.pick(reply, BRAIN, "u2")
check("another chat sends nothing", files2 == [] and FETCHED == [] and text2 == reply)
bot_images.fetch_remote = lambda url: ""
text3, files3 = bot_images.pick(reply, BRAIN, "u1")
check("an image that does not download stays in the text", files3 == [] and text3 == reply)
bot_images.fetch_remote = real_fetch

# ============================================================
# 3. The fetch
# ============================================================
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        if self.path.startswith("/img"):
            body, ctype = PNG, "image/png"
        elif self.path == "/page":
            body, ctype = b"<html>hi</html>", "text/html"
        elif self.path == "/big":
            body, ctype = b"\x00" * (bot_images.MAX_BYTES + 10), "image/jpeg"
        elif self.path == "/redirect-private":
            self.send_response(302)
            self.send_header("Location", "http://10.0.0.5/secret.png")
            self.end_headers()
            return
        else:
            self.send_response(404)
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
threading.Thread(target=srv.serve_forever, daemon=True).start()
BASE = f"http://127.0.0.1:{srv.server_address[1]}"

check("a loopback address is refused", bot_images.fetch_remote(BASE + "/img1") == "")
check("a LAN address is refused", not bot_images._url_ok("http://192.168.1.10/a.jpg"))
check("a link with a password is refused", not bot_images._url_ok("https://u:p@cdn.pos.example/a.jpg"))
check("another scheme is refused", not bot_images._url_ok("file:///etc/passwd"))

real_public = bot_images._public_host
bot_images._public_host = lambda host, port: host == "127.0.0.1"      # the test server stands in for a public CDN
path = bot_images.fetch_remote(BASE + "/img1")
check("a public image downloads into the cache", path.endswith(".png") and open(path, "rb").read() == PNG, path)
check("outside any brain", path.startswith(str(bot_images.cache_dir())))
check("the same link is reused", bot_images.fetch_remote(BASE + "/img1") == path)
check("a web page is not an image", bot_images.fetch_remote(BASE + "/page") == "")
check("too big is refused", bot_images.fetch_remote(BASE + "/big") == "")
check("a redirect to a private address is refused", bot_images.fetch_remote(BASE + "/redirect-private") == "")
check("a missing image is refused", bot_images.fetch_remote(BASE + "/nothing") == "")
bot_images._public_host = real_public
srv.shutdown()

# ============================================================
# 4. What the Agent is told
# ============================================================
hint = bot_images.PROMPT_HINT
check("the Agent learns a tool's photo link may be sent", "tool" in hint and "POS" in hint)
check("and to say plainly when there is none", "cannot send one" in hint)
check("never a link the customer typed", "customer typed" in hint)
check("no long dash in the hint", "\u2014" not in hint and "\u2013" not in hint)

print()
if _fails:
    print(f"{len(_fails)} FAIL: {_fails}")
    sys.exit(1)
print("all ok")
