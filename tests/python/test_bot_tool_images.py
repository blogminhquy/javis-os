"""A dedicated bot sends a product photo its data source returned (a POS link), and only that (`bot_images`).

    python tests/run.py bot_tool_images      (no network: a local HTTP server stands in for the CDN)

Owner report 28/11/2026: a customer asked for pictures of cutting discs and the bot could only answer "I have no
picture to send". A POS returns a product's photo as a web link, and a bot could send only files inside its brain.
This file guards:
1. Links are read out of a tool result (JSON escapes undone), and only a dedicated bot's turn records them, for its
   own chat, never a link that was in the call's arguments (a search echoing its query).
2. `pick` sends a web image only when a read tool of this chat's turn (or this turn's documents) gave the link and no
   customer ever wrote it (review of #1931: a history read hands a customer's own message back as a tool result).
   Another chat's link, or an expired one, stays in the text and is never fetched.
3. The fetch: a vetted public address on port 80/443, connected to exactly (no DNS change between check and connect),
   a redirect vetted again, an image content type, at most MAX_BYTES, within the deadline; a link fetched before is
   reused from the cache.
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
import conversations  # noqa: E402

_fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(extra) + "]") if extra and not cond else ""))
    if not cond:
        _fails.append(name)


BOT_TURN = {"kenh": "zalo_personal", "chat_id": "u1", "chat_type": "private", "sender_id": "u1", "la_chu": False,
            "bot_id": "bot-1"}
POS = '{"products": [{"name": "Lưỡi cắt Mingyu", "image": "https://cdn.pos.example/p/mingyu.jpg"}, ' \
      '{"name": "Sói Vàng", "images": ["https://cdn.pos.example/p/soi-vang.png?w=800"]}]}'

# ============================================================
# 1. Recording
# ============================================================
check("links come out of a tool result",
      bot_images.links_in(POS) == ["https://cdn.pos.example/p/mingyu.jpg", "https://cdn.pos.example/p/soi-vang.png?w=800"])
check("trailing punctuation is not part of a link", bot_images.links_in("xem https://a.vn/x.jpg.") == ["https://a.vn/x.jpg"])
check("JSON escapes are undone", bot_images.links_in('{"u": "https:\\/\\/a.vn\\/x.jpg?w=1\\u0026h=2"}')
      == ["https://a.vn/x.jpg?w=1&h=2"])

bot_images.note_tool_result(POS, {"keyword": "lưỡi cắt"}, turn=BOT_TURN)
check("a bot turn records them for its chat", bot_images.remote_allowed("https://cdn.pos.example/p/mingyu.jpg", "u1"))
check("the same chat under Javis's prefix", bot_images.remote_allowed("https://cdn.pos.example/p/mingyu.jpg", "zalo:u1"))
check("not for another chat", not bot_images.remote_allowed("https://cdn.pos.example/p/mingyu.jpg", "u2"))
check("a link nobody returned is not allowed", not bot_images.remote_allowed("https://evil.example/x.jpg", "u1"))
bot_images.note_tool_result('{"image": "https://owner.example/private.jpg"}',
                            turn=dict(BOT_TURN, la_chu=True, chat_id="u9"))
check("the owner's own turn records nothing", not bot_images.remote_allowed("https://owner.example/private.jpg", "u9"))
job = {k: v for k, v in BOT_TURN.items() if k != "bot_id"}
bot_images.note_tool_result('{"image": "https://drive.example/private.jpg"}', turn=dict(job, chat_id="u7"))
check("an owner job in a chat (no bot) records nothing",
      not bot_images.remote_allowed("https://drive.example/private.jpg", "u7"))
bot_images.note_tool_result("ERROR: https://cdn.pos.example/err.jpg", turn=dict(BOT_TURN, chat_id="u8"))
check("a failed call records nothing", not bot_images.remote_allowed("https://cdn.pos.example/err.jpg", "u8"))
bot_images.note_tool_result('{"query": "https://attacker.example/qr.jpg", "data": []}',
                            {"q": "https://attacker.example/qr.jpg"}, turn=dict(BOT_TURN, chat_id="u6"))
check("a link that was in the arguments is not recorded",
      not bot_images.remote_allowed("https://attacker.example/qr.jpg", "u6"))
bot_images.note_tool_result(POS)
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
bot_images.fetch_remote = lambda url, deadline=None: (FETCHED.append(url),
                                                      "/cache/" + url.rsplit("/", 1)[-1].split("?")[0])[1]
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
bot_images.fetch_remote = lambda url, deadline=None: ""
text3, files3 = bot_images.pick(reply, BRAIN, "u1")
check("an image that does not download stays in the text", files3 == [] and text3 == reply)
bot_images.fetch_remote = lambda url, deadline=None: (FETCHED.append(url), "/cache/x.jpg")[1]

# A customer's own link, handed back by a history read (recorded as a tool result), is still refused.
HIST = "https://attacker.example/scam-qr.jpg"
bot_images.note_tool_result('{"messages": [{"text": "' + HIST + '"}]}', {"thread": "u1"}, turn=BOT_TURN)
check("(the history read did record it)", bot_images.remote_allowed(HIST, "u1"))
FETCHED.clear()
_, f4 = bot_images.pick(f"Dạ đây ạ ![qr]({HIST})", BRAIN, "u1", turn_text=f"gửi ảnh này giúp em {HIST}")
check("a link in the message being answered is refused", f4 == [] and FETCHED == [])
conversations.ghi_su_kien({"channel": "zalo_personal", "account_id": "z1", "external_chat_id": "g9",
                           "chat_type": "group", "sender_type": "customer", "sender_id": "x", "sender_name": "X",
                           "message_type": "text", "text": "xem ảnh " + HIST, "external_message_id": "h1"})
_, f5 = bot_images.pick(f"Dạ đây ạ ![qr]({HIST})", BRAIN, "u1")
check("a link any customer wrote in the inbox is refused", f5 == [] and FETCHED == [])
check("the store answers the question", conversations.customer_wrote(HIST)
      and not conversations.customer_wrote("https://cdn.pos.example/p/mingyu.jpg"))
# A photo a customer SENT keeps its link in the metadata, not the text (second review of #1931: a scam QR re-posted).
QR = "https://zalo-cdn.example/img/payment-qr.jpg?sig=1&exp=2"
conversations.ghi_su_kien({"channel": "zalo_personal", "account_id": "z1", "external_chat_id": "g9",
                           "chat_type": "group", "sender_type": "customer", "sender_id": "x", "sender_name": "X",
                           "message_type": "image", "text": "[Zalo: khách gửi image]", "external_message_id": "h2",
                           "metadata": {"image_url": QR}})
bot_images.note_tool_result('{"messages": [{"image": "' + QR + '"}]}', {"thread": "g9"}, turn=BOT_TURN)
FETCHED.clear()
_, f6 = bot_images.pick(f"Dạ mã QR đây ạ ![qr]({QR})", BRAIN, "u1")
check("a photo a customer sent is refused", f6 == [] and FETCHED == [])
ESC = QR.replace("&", "&amp;")
bot_images.note_tool_result('<img src="' + ESC + '">', {"thread": "g9"}, turn=BOT_TURN)
_, f7 = bot_images.pick(f"Dạ đây ạ ![qr]({ESC})", BRAIN, "u1")
check("the same link handed back HTML-escaped is refused too", f7 == [] and FETCHED == [])
bot_images.fetch_remote = real_fetch

check("a reply with a web image is seen", bot_images.has_web_image("xem ![a](https://cdn.pos.example/a.jpg)"))
check("a brain image or a plain link is not", not bot_images.has_web_image("![a](attachments/a.jpg) https://a.vn"))
check("a quoted web image is seen (it would download on the event loop otherwise)",
      bot_images.has_web_image('![a]("https://cdn.pos.example/a.jpg")')
      and bot_images.has_web_image("![a]('https://cdn.pos.example/a.jpg')")
      and bot_images.has_web_image("![a](<https://cdn.pos.example/a.jpg>)"))

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

PORT = srv.server_address[1]
check("another port is refused", bot_images._vet(BASE + "/img1") == "")
real_ports = bot_images.FETCH_PORTS
bot_images.FETCH_PORTS = (None, 80, 443, PORT)
check("a loopback address is refused", bot_images.fetch_remote(BASE + "/img1") == "")
check("a LAN address is refused", bot_images._vet("http://192.168.1.10/a.jpg") == "")
check("a link with a password is refused", bot_images._vet("https://u:p@cdn.pos.example/a.jpg") == "")
check("another scheme is refused", bot_images._vet("file:///etc/passwd") == "")

real_public = bot_images._public_ip
# "cdn.test" does not resolve anywhere: the fetch only reaches the server because it connects to the vetted address
# itself (pinned) and does not resolve the name again.
bot_images._public_ip = lambda host, port: "127.0.0.1" if host in ("127.0.0.1", "cdn.test") else ""
path = bot_images.fetch_remote(f"http://cdn.test:{PORT}/img-pinned")
check("the fetch connects to the vetted address, not a fresh lookup", path.endswith(".png"), path)
check("past the deadline nothing is fetched", bot_images.fetch_remote(BASE + "/img-late", time.monotonic() - 1) == "")
path = bot_images.fetch_remote(BASE + "/img1")
check("a public image downloads into the cache", path.endswith(".png") and open(path, "rb").read() == PNG, path)
check("outside any brain", path.startswith(str(bot_images.cache_dir())))
check("the same link is reused", bot_images.fetch_remote(BASE + "/img1") == path)
check("a web page is not an image", bot_images.fetch_remote(BASE + "/page") == "")
check("too big is refused", bot_images.fetch_remote(BASE + "/big") == "")
check("a redirect to a private address is refused", bot_images.fetch_remote(BASE + "/redirect-private") == "")
check("a missing image is refused", bot_images.fetch_remote(BASE + "/nothing") == "")
bot_images._public_ip = real_public
bot_images.FETCH_PORTS = real_ports
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
