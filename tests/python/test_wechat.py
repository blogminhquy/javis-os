"""WeChat channel: a dedicated bot answers the followers of a WeChat Official Account.

    python tests/run.py wechat

No network: api.weixin.qq.com is faked with httpx.MockTransport. What is guarded, in order of what
would hurt most if it broke:

  1. The webhook is a PUBLIC URL. A request whose signature was not made with Javis's own token, or
     whose timestamp is old, is refused before any bot sees it. An account that has an
     EncodingAESKey takes encrypted messages only, and only ones that open with ITS key and carry
     ITS AppID.
  2. A message reaches the bot of the account it was sent to: by key in Safe mode, by Original ID
     (pasted or learned) in Plaintext mode. WeChat's retries of one message are answered once.
  3. One full turn: the route answers "success" at once and the reply goes back through the customer
     service API as plain text, raw UTF-8, at most 2048 bytes a message.
  4. An access token WeChat calls invalid is fetched again once and the call repeated; the errors
     the owner can act on (IP whitelist, unverified account, 48-hour window) read as words.
  5. The channel is in the registry as a bot channel with a webhook, and its token is a stored secret.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import hashlib
import json
import os
import sys
import tempfile
import time
import types

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-wechat-")

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import httpx  # noqa: E402

import channel_accounts  # noqa: E402
import channels  # noqa: E402
import chatbot_store  # noqa: E402
import config as cfgmod  # noqa: E402
import wechat_bot as wc  # noqa: E402

_fails = []


def check(name, ok, detail=""):
    print(("ok   " if ok else "FAIL ") + name + ("" if ok else f"  [{detail}]"))
    if not ok:
        _fails.append(name)


def run(coro):
    return asyncio.run(coro)


APP_ID = "wx1234567890abcdef"
APP_ID_B = "wxfedcba0987654321"
APP_SECRET = "0123456789abcdef0123456789abcdef"
AES_KEY = "abcdefghijklmnopqrstuvwxyz0123456789ABCDEFG"       # 43 characters
AES_KEY_B = "ZYXWVUTSRQPONMLKJIHGFEDCBA9876543210zyxwvut"
GH = "gh_0123456789ab"
GH_B = "gh_ba9876543210"
OPENID = "oABCD1234efgh5678ijkl9012mnop"
TOKEN = "javistoken0123456789abcdef012345"

# ---- Fake WeChat -------------------------------------------------------------------------
state = {"n": 0, "access": "", "sent": [], "raw": [], "bad": set(), "whitelist": True, "typing": 0,
         "uploads": 0, "forced": 0}


async def wechat(req):
    path = req.url.path
    if path == "/cgi-bin/stable_token":
        body = json.loads(req.content)
        if not state["whitelist"]:
            return httpx.Response(200, json={"errcode": 40164, "errmsg": "invalid ip 203.0.113.9, not in whitelist"})
        if body.get("appid") not in (APP_ID, APP_ID_B) or body.get("secret") != APP_SECRET:
            return httpx.Response(200, json={"errcode": 40125, "errmsg": "invalid appsecret"})
        if body.get("force_refresh"):
            state["forced"] += 1
        if not state["access"] or state["access"] in state["bad"] and body.get("force_refresh"):
            state["n"] += 1
            state["access"] = f"tok{state['n']}_" + "y" * 60
        return httpx.Response(200, json={"access_token": state["access"], "expires_in": 7200})
    tok = req.url.params.get("access_token", "")
    if tok != state["access"] or tok in state["bad"]:
        return httpx.Response(200, json={"errcode": 40001, "errmsg": "invalid credential, access_token is invalid"})
    if path == "/cgi-bin/message/custom/typing":
        state["typing"] += 1
        return httpx.Response(200, json={"errcode": 0, "errmsg": "ok"})
    if path == "/cgi-bin/media/upload":
        state["uploads"] += 1
        return httpx.Response(200, json={"type": "image", "media_id": "MEDIA1", "created_at": 1})
    if path == "/cgi-bin/message/custom/send":
        state["raw"].append(req.content)
        state["sent"].append(json.loads(req.content))
        return httpx.Response(200, json={"errcode": 0, "errmsg": "ok"})
    return httpx.Response(404, json={"errcode": -1, "errmsg": "not faked"})


_RealClient = httpx.AsyncClient


def _client(**kw):
    kw.pop("transport", None)
    return _RealClient(transport=httpx.MockTransport(wechat), **kw)


wc.httpx = types.SimpleNamespace(AsyncClient=_client, Timeout=httpx.Timeout)


def sign(*parts):
    return hashlib.sha1("".join(sorted(parts)).encode()).hexdigest()


def text_xml(content="Giá bao nhiêu ạ?", to=GH, msg_id="6054768590064713728"):
    return (f"<xml><ToUserName><![CDATA[{to}]]></ToUserName><FromUserName><![CDATA[{OPENID}]]></FromUserName>"
            f"<CreateTime>1700000000</CreateTime><MsgType><![CDATA[text]]></MsgType>"
            f"<Content><![CDATA[{content}]]></Content><MsgId>{msg_id}</MsgId></xml>")


def plain_request(xml=None, ts=None, token=TOKEN):
    ts = str(int(time.time())) if ts is None else str(ts)
    nonce = "n0nce"
    return (xml or text_xml()).encode(), {"signature": sign(token, ts, nonce), "timestamp": ts, "nonce": nonce}


def safe_request(xml=None, key=AES_KEY, app_id=APP_ID, to=GH, token=TOKEN):
    ts, nonce = str(int(time.time())), "n0nce"
    enc = wc.encrypt(key, app_id, xml or text_xml(to=to))
    body = f"<xml><ToUserName><![CDATA[{to}]]></ToUserName><Encrypt><![CDATA[{enc}]]></Encrypt></xml>".encode()
    return body, {"msg_signature": sign(token, ts, nonce, enc), "timestamp": ts, "nonce": nonce,
                  "encrypt_type": "aes", "signature": sign(token, ts, nonce)}


# ============================================================
# 1. Credentials
# ============================================================
cr = wc.split_credentials(f"{APP_SECRET}\n{APP_ID}  {GH} {AES_KEY}")
check("pasted credentials split by shape, in any order",
      cr == {"app_id": APP_ID, "app_secret": APP_SECRET, "aes_key": AES_KEY, "original_id": GH}, cr)
cr2 = wc.split_credentials(f"appid={APP_ID} secret={APP_SECRET} EncodingAESKey={AES_KEY}")
check("key=value parts are read by name", cr2["app_id"] == APP_ID and cr2["aes_key"] == AES_KEY, cr2)
check("credentials written back read the same", wc.split_credentials(wc.dump_credentials(cr)) == cr)
check("the AES key is optional, AppID and AppSecret are not",
      wc.missing_parts(wc.split_credentials(f"{APP_ID} {APP_SECRET}")) == []
      and wc.missing_parts(wc.split_credentials(APP_ID)) == ["AppSecret"])
check("a 43-character key decodes to 32 bytes, anything else to nothing",
      len(wc.aes_key_bytes(AES_KEY)) == 32 and wc.aes_key_bytes("short") is None)

# ============================================================
# 2. Signature, freshness, encryption, XML
# ============================================================
ts0 = str(int(time.time()))
check("signature is sha1 of the sorted token, timestamp, nonce",
      wc.check_signature(TOKEN, sign(TOKEN, ts0, "abc"), ts0, "abc"))
check("wrong token refused", not wc.check_signature("other", sign(TOKEN, ts0, "abc"), ts0, "abc"))
check("empty token never matches", not wc.check_signature("", sign("", ts0, "abc"), ts0, "abc"))
check("empty signature refused", not wc.check_signature(TOKEN, "", ts0, "abc"))
check("msg_signature covers the ciphertext", wc.check_signature(TOKEN, sign(TOKEN, ts0, "abc", "ENC"), ts0, "abc", "ENC")
      and not wc.check_signature(TOKEN, sign(TOKEN, ts0, "abc", "ENC"), ts0, "abc", "ENC2"))
check("a recent timestamp is fresh, an old or absent one is not",
      wc.fresh_timestamp(ts0) and not wc.fresh_timestamp(int(time.time()) - 3600)
      and not wc.fresh_timestamp("") and not wc.fresh_timestamp("abc"))

enc0 = wc.encrypt(AES_KEY, APP_ID, text_xml())
xml0, app0 = wc.decrypt(AES_KEY, enc0)
check("encrypt then decrypt returns the message and the AppID", xml0 == text_xml() and app0 == APP_ID, (xml0, app0))
# The exact envelope from WeChat's own description, built by hand: 16 random bytes, big-endian length, message, AppID.
import base64  # noqa: E402
import struct  # noqa: E402
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes  # noqa: E402
_k = base64.b64decode(AES_KEY + "=")
_p = b"R" * 16 + struct.pack(">I", 5) + b"hello" + APP_ID.encode()
_p += bytes([32 - len(_p) % 32]) * (32 - len(_p) % 32)
_e = Cipher(algorithms.AES(_k), modes.CBC(_k[:16])).encryptor()
check("an envelope built from the published layout opens",
      wc.decrypt(AES_KEY, base64.b64encode(_e.update(_p) + _e.finalize()).decode()) == ("hello", APP_ID))
for bad_name, bad in (("another account's key", lambda: wc.decrypt(AES_KEY_B, enc0)),
                      ("garbage", lambda: wc.decrypt(AES_KEY, "!!!not base64!!!")),
                      ("a truncated ciphertext", lambda: wc.decrypt(AES_KEY, enc0[:40]))):
    try:
        r = bad()
        opened = r[1] == APP_ID
    except ValueError:
        opened = False
    check(f"{bad_name} does not open as this account", not opened)

check("flat XML reads into a dict", wc.parse_xml(text_xml())["Content"] == "Giá bao nhiêu ạ?")
check("a document with a DTD is refused unparsed",
      wc.parse_xml('<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "aaaa">]><xml><Content>&a;</Content></xml>') == {})
check("not XML, wrong root and oversized bodies are refused",
      wc.parse_xml("{}") == {} and wc.parse_xml("<a><b>1</b></a>") == {}
      and wc.parse_xml("<xml><Content>" + "x" * (wc.MAX_BODY + 1) + "</Content></xml>") == {})

# ============================================================
# 3. Text limits
# ============================================================
long_vi = ("Dạ nước mắm cốt nhỉ ủ chượp mười hai tháng ạ. " * 200).strip()
parts = wc.chunks_by_bytes(long_vi)
check("a long answer is split into pieces of at most 2000 bytes",
      len(parts) > 1 and all(len(p.encode("utf-8")) <= wc.MAX_BYTES for p in parts), [len(p.encode()) for p in parts])
check("nothing is lost and no character is cut in half", "".join(parts).replace(" ", "") == long_vi.replace(" ", ""))
check("a short answer stays one piece", wc.chunks_by_bytes("你好") == ["你好"])
check("text with no break still splits on a character boundary",
      all(len(p.encode("utf-8")) <= wc.MAX_BYTES for p in wc.chunks_by_bytes("汉" * 3000)))

# ============================================================
# 4. Errors read as words
# ============================================================
check("IP whitelist error keeps the IP WeChat names",
      "203.0.113.9" in wc._explain_error(40164, "invalid ip 203.0.113.9, not in whitelist")
      and "whitelist" in wc._explain_error(40164, "x").lower())
check("unverified account is said in words", "48001" in wc._explain_error(48001))
check("48-hour window is said in words", "48" in wc._explain_error(45015))
check("unknown code keeps WeChat's message", wc._explain_error(99999, "boom") == "boom (99999)")

# ============================================================
# 5. Registry
# ============================================================
s = channels.spec("wechat")
check("wechat is a bot channel in the registry", s is not None and s.kind == "bot")
check("wechat carries a bot, private only, sends text and images",
      s.nl("bot") and not s.nl("nhom") and s.nl("gui_chu") and s.nl("gui_file") and s.nl("tra_loi_tu_javis"), s.nang_luc)
ui = {k["id"]: k for k in channels.cho_giao_dien()}
check("UI entry carries the webhook path, a guide and a logo",
      ui.get("wechat", {}).get("webhook") == "/wechat/webhook" and ui["wechat"]["huong_dan"].get("vi") == "36-wechat.md"
      and ui["wechat"]["logo"] == "wechat", ui.get("wechat"))
for _lang, _dir in (("vi", "docs"), ("en", os.path.join("docs", "en"))):
    check(f"the {_lang} guide the form links to exists",
          os.path.isfile(os.path.join(ROOT, _dir, ui["wechat"]["huong_dan"][_lang])))
check("the logo is drawn in icons.js", "wechat: {" in open(os.path.join(ROOT, "dashboard", "icons.js"), encoding="utf-8").read())
check("bot store accepts wechat", "wechat" in chatbot_store.KENH, chatbot_store.KENH)
check("an OpenID passes the chat id check", bool(chatbot_store._CHAT_ID_RE.match(OPENID)))
check("the webhook token is encrypted at rest", "wechat.webhook_token" in cfgmod._SECRET_PATHS)

# ============================================================
# 6. Checking pasted credentials
# ============================================================
r = run(channels.module("wechat").verify_token(f"{APP_ID} {APP_SECRET}"))
check("good credentials pass and name the account by AppID", r.get("ok") and r.get("username") == APP_ID, r)
r = run(channels.module("wechat").verify_token(f"{APP_ID} " + "f" * 32))
check("a wrong AppSecret is refused in words, though a token of the right one is cached",
      not r.get("ok") and "AppSecret" in r.get("error", ""), r)


async def _other_secret():
    async with _client() as c:
        return await wc.TOKENS.get(c, {"app_id": APP_ID, "app_secret": "f" * 32})

check("a cached token is never served to another AppSecret", run(_other_secret())[0] == "")
r = run(channels.module("wechat").verify_token(APP_ID))
check("a missing AppSecret is named", not r.get("ok") and "AppSecret" in r.get("error", ""), r)
state["whitelist"] = False
r = run(channels.module("wechat").verify_token(f"{APP_ID} {APP_SECRET}"))
state["whitelist"] = True
check("an IP off the whitelist is refused with the IP to add", not r.get("ok") and "203.0.113.9" in r.get("error", ""), r)
wc.TOKENS.drop(APP_ID)

# ============================================================
# 7. Webhook: who is trusted, and which bot gets the message
# ============================================================


class Probe(wc.WeChatBot):
    def __init__(self, cred, account_id=""):
        super().__init__(cred, "", None, giau_trang_thai=True, account_id=account_id)
        self.got = []

    async def _safe_message(self, msg):
        self.got.append(msg)


def _reset(*bots):
    wc._REGISTRY.clear()
    wc._ORIGINAL.clear()
    for b in bots:
        wc._REGISTRY[b.app_id] = b
        if b.original_id:
            wc._ORIGINAL[b.original_id] = b.app_id


async def _hook(body, query, *bots, token=TOKEN):
    _reset(*bots)
    res = await wc.handle_webhook(body, query, token)
    await asyncio.sleep(0)
    return res


a = Probe(f"{APP_ID} {APP_SECRET}")
body, q = plain_request()
check("a signed plaintext message reaches the only account and is acknowledged",
      run(_hook(body, q, a)) == (200, "success") and len(a.got) == 1 and a.got[0]["Content"] == "Giá bao nhiêu ạ?", a.got)
check("the account learns its Original ID from that message", a.original_id == GH and wc._ORIGINAL.get(GH) == APP_ID)

a = Probe(f"{APP_ID} {APP_SECRET}")
check("a wrong signature is refused before any bot", run(_hook(body, {**q, "signature": "0" * 40}, a))[0] == 401 and not a.got)
check("a signature made with another token is refused", run(_hook(body, q, a, token="someone-else"))[0] == 401 and not a.got)
old_body, old_q = plain_request(ts=int(time.time()) - 3600)
check("a correctly signed but old request is refused (replay)", run(_hook(old_body, old_q, a))[0] == 401 and not a.got)
check("a body that is not WeChat XML is refused", run(_hook(b"{}", q, a))[0] == 400 and not a.got)

# Two accounts in Plaintext mode: the Original ID decides, and without it nothing is guessed.
a, b = Probe(f"{APP_ID} {APP_SECRET} {GH}"), Probe(f"{APP_ID_B} {APP_SECRET} {GH_B}")
body_b, q_b = plain_request(text_xml(to=GH_B))
run(_hook(body_b, q_b, a, b))
check("with Original IDs pasted, a plaintext message reaches its own account", not a.got and len(b.got) == 1, (a.got, b.got))
a, b = Probe(f"{APP_ID} {APP_SECRET}"), Probe(f"{APP_ID_B} {APP_SECRET}")
res = run(_hook(body, q, a, b))
check("two accounts that do not know their id: nothing is guessed, both say why",
      res == (200, "success") and not a.got and not b.got and "gh_" in a.last_error and "gh_" in b.last_error,
      (a.got, b.got, a.last_error))

# Safe mode.
a, b = Probe(f"{APP_ID} {APP_SECRET} {AES_KEY}"), Probe(f"{APP_ID_B} {APP_SECRET} {AES_KEY_B}")
sbody, sq = safe_request(text_xml(to=GH_B), key=AES_KEY_B, app_id=APP_ID_B, to=GH_B)
res = run(_hook(sbody, sq, a, b))
check("an encrypted message reaches the account whose key opens it", res == (200, "success") and not a.got
      and len(b.got) == 1 and b.got[0]["FromUserName"] == OPENID, (a.got, b.got))
a = Probe(f"{APP_ID} {APP_SECRET} {AES_KEY}")
check("a wrong msg_signature is refused", run(_hook(sbody, {**sq, "msg_signature": "0" * 40}, a))[0] == 401 and not a.got)
# The right key but another account's AppID inside the envelope: not this account's message.
xbody, xq = safe_request(key=AES_KEY, app_id=APP_ID_B)
check("an envelope that names another AppID is not handed over", run(_hook(xbody, xq, a)) == (200, "success") and not a.got)
pbody, pq = plain_request()
a = Probe(f"{APP_ID} {APP_SECRET} {AES_KEY} {GH}")
res = run(_hook(pbody, pq, a))
check("an account with a key refuses an unencrypted message and says how to fix it",
      res == (200, "success") and not a.got and ("Safe mode" in a.last_error or "an toàn" in a.last_error),
      (a.got, a.last_error))

# Compatible mode: WeChat sends the plaintext fields AND the ciphertext, with both signatures.
def compat_request(to=GH, key=AES_KEY, app_id=APP_ID):
    ts, nonce = str(int(time.time())), "n0nce"
    inner = text_xml(to=to)
    enc = wc.encrypt(key, app_id, inner)
    body = inner.replace("</xml>", f"<Encrypt><![CDATA[{enc}]]></Encrypt></xml>").encode()
    return body, {"signature": sign(TOKEN, ts, nonce), "msg_signature": sign(TOKEN, ts, nonce, enc),
                  "timestamp": ts, "nonce": nonce, "encrypt_type": "aes"}

cbody, cq = compat_request()
a = Probe(f"{APP_ID} {APP_SECRET}")
check("Compatible mode reaches an account that has no key, through the plaintext form",
      run(_hook(cbody, cq, a)) == (200, "success") and len(a.got) == 1, a.got)
a = Probe(f"{APP_ID} {APP_SECRET} {AES_KEY}")
check("Compatible mode reaches an account that has the key, through the ciphertext",
      run(_hook(cbody, cq, a)) == (200, "success") and len(a.got) == 1 and not a.last_error, (a.got, a.last_error))
a = Probe(f"{APP_ID} {APP_SECRET} {AES_KEY_B}")
check("a key that does not open WeChat's messages is said on the bot card, nothing is handed over",
      run(_hook(cbody, cq, a)) == (200, "success") and not a.got and "EncodingAESKey" in a.last_error, a.last_error)
a = Probe(f"{APP_ID} {APP_SECRET}")
sbody2, sq2 = safe_request()
check("Safe mode for an account without a key is said on the bot card",
      run(_hook(sbody2, sq2, a)) == (200, "success") and not a.got and "EncodingAESKey" in a.last_error, a.last_error)

# ============================================================
# 8. One full turn
# ============================================================
aid, loi = channel_accounts.create_account({"channel": "wechat", "token": f"{APP_ID} {APP_SECRET}", "label": "Shop"})
check("account saved with the pasted string", aid and not loi, loi)


async def _turn():
    seen = {}
    state["sent"].clear()
    state["raw"].clear()

    async def answer(text, meta, progress):
        seen["text"], seen["meta"] = text, dict(meta)
        return {"text": "**Dạ** chai 500ml giá 85.000đ ạ. 谢谢"}

    bot = wc.WeChatBot(f"{APP_ID} {APP_SECRET}", "", answer, giau_trang_thai=True, account_id=aid)
    _reset(bot)
    body, q = plain_request()
    res1 = await wc.handle_webhook(body, q, TOKEN)
    res2 = await wc.handle_webhook(body, q, TOKEN)          # WeChat retry: same MsgId
    follow = ("<xml><ToUserName><![CDATA[%s]]></ToUserName><FromUserName><![CDATA[%s]]></FromUserName>"
              "<CreateTime>1700000001</CreateTime><MsgType><![CDATA[event]]></MsgType>"
              "<Event><![CDATA[subscribe]]></Event></xml>" % (GH, OPENID))
    fbody, fq = plain_request(follow)
    await wc.handle_webhook(fbody, fq, TOKEN)                # a follow event starts no turn
    for _ in range(20):
        await asyncio.sleep(0.01)
        if state["sent"]:
            break
    for t in list(bot._current.values()):
        await t
    if bot._client:
        await bot._client.aclose()
    _reset()
    return seen, res1, res2

seen, res1, res2 = run(_turn())
check("WeChat is answered \"success\" at once, also on its retry", res1 == res2 == (200, "success"), (res1, res2))
check("customer text and meta handed to the bot",
      seen.get("text") == "Giá bao nhiêu ạ?" and seen["meta"].get("platform") == "wechat"
      and seen["meta"].get("chat_id") == OPENID and seen["meta"].get("chat_type") == "private", seen)
check("answered once, plain text, to the sender, through the customer service API",
      state["sent"] == [{"touser": OPENID, "msgtype": "text", "text": {"content": "Dạ chai 500ml giá 85.000đ ạ. 谢谢"}}],
      state["sent"])
check("the JSON goes out as raw UTF-8, never as \\u escapes",
      bool(state["raw"]) and b"\\u" not in state["raw"][0] and "谢谢".encode("utf-8") in state["raw"][0], state["raw"])
check("the learned Original ID is written to the account store",
      wc.split_credentials(channel_accounts.get_token(aid))["original_id"] == GH, channel_accounts.get_token(aid))

# A token WeChat suddenly calls invalid is fetched again once and the send repeated.
state["bad"].add(state["access"])
n0, f0 = state["n"], state["forced"]
ok, err = run(channels.gui("wechat", {"id": aid, "token": channel_accounts.get_token(aid)}, OPENID, "Dạ"))
check("40001 on send asks for a new token once and retries", ok and state["n"] == n0 + 1 and state["forced"] == f0 + 1,
      (ok, err, state["n"], state["forced"]))

# Images go out as an uploaded media; documents are refused in words.
_img = os.path.join(tempfile.mkdtemp(prefix="javis-wechat-f-"), "chai.png")
open(_img, "wb").write(b"\x89PNG\r\n\x1a\n" + b"0" * 64)
_pdf = _img[:-4] + ".pdf"
open(_pdf, "wb").write(b"%PDF-1.4")
state["sent"].clear()
bot = wc.WeChatBot(f"{APP_ID} {APP_SECRET}", "", None, giau_trang_thai=True)
ok, err = run(bot.send_file(_img, "", chat=OPENID))
check("an image is uploaded then sent by media id", ok and state["uploads"] == 1
      and state["sent"] == [{"touser": OPENID, "msgtype": "image", "image": {"media_id": "MEDIA1"}}], (ok, err, state["sent"]))
ok, err = run(bot.send_file(_pdf, "", chat=OPENID))
check("a document is refused with a reason, nothing is sent", not ok and err and len(state["sent"]) == 1, (ok, err))

# ============================================================
# 9. Endpoints (TestClient)
# ============================================================
import main  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

client = TestClient(main.app, base_url="http://localhost")
r = client.get("/channels/webhook-info", params={"channel": "wechat"})
info = r.json() if r.status_code == 200 else {}
tok = info.get("verify_token", "")
check("webhook-info gives the WeChat address and a Token WeChat's form accepts",
      info.get("webhook_url", "").endswith("/wechat/webhook") and tok.isalnum() and 3 <= len(tok) <= 32, r.text)
check("plain http is a warning in words, not a refusal", bool(info.get("warning")) and info.get("https") is True, info)
check("the same Token is given every time", client.get("/channels/webhook-info", params={"channel": "wechat"}).json()
      .get("verify_token") == tok)
_stored = json.load(open(cfgmod.SETTINGS_PATH, encoding="utf-8")).get("wechat", {}).get("webhook_token", "")
check("the Token is not in settings.json in the clear", _stored and _stored != tok, _stored)

ts = str(int(time.time()))
r = client.get("/wechat/webhook", params={"signature": sign(tok, ts, "n1"), "timestamp": ts, "nonce": "n1", "echostr": "ECHO123"})
check("URL check with the right signature echoes echostr", r.status_code == 200 and r.text == "ECHO123", (r.status_code, r.text))
r = client.get("/wechat/webhook", params={"signature": "0" * 40, "timestamp": ts, "nonce": "n1", "echostr": "ECHO123"})
check("URL check with a wrong signature is refused", r.status_code == 403 and "ECHO123" not in r.text, r.status_code)
r = client.get("/wechat/webhook")
check("URL check with nothing is refused", r.status_code == 403, r.status_code)

p = Probe(f"{APP_ID} {APP_SECRET}")
_reset(p)
body, q = plain_request(token=tok)
r = client.post("/wechat/webhook", params={**q, "signature": "0" * 40}, content=body)
check("POST with a bad signature is refused", r.status_code == 401 and not p.got, r.status_code)
r = client.post("/wechat/webhook", content=body)
check("POST without a signature is refused", r.status_code == 401 and not p.got, r.status_code)
r = client.post("/wechat/webhook", params=q, content=body)
check("POST signed with Javis's Token is handed over and answered success",
      r.status_code == 200 and r.text == "success" and len(p.got) == 1, (r.status_code, r.text))
r = client.post("/wechat/webhook", params=q, content=b"x" * (wc.MAX_BODY + 10))
check("an oversized POST is refused unread", r.status_code == 413, r.status_code)
_reset()

src = open(os.path.join(SERVER, "main.py"), encoding="utf-8").read()
check("the webhook is a public exact path", '"/wechat/webhook",' in src.split("_AUTH_PUBLIC_EXACT = (")[1].split("\n# Endpoint")[0])
import bot_shield  # noqa: E402
check("the bot shield lets WeChat's servers through", "/wechat/webhook" in bot_shield.MACHINE_EXACT)

print()
if _fails:
    print(f"{len(_fails)} FAILED: " + "; ".join(_fails))
    sys.exit(1)
print("all good")
