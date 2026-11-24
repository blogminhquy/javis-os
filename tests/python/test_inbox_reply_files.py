"""`inbox_reply` sends images and files that are already in the brain (issue #1802).

    python tests/run.py inbox_reply_files      (no network: channel sends and Meta's Graph API are faked)

An engine asked "send her the price list" had no way to send the picture sitting in `attachments/`. The tool now takes
`files`, and they go through `routes.conversations.owner_send_file`, the one send path of the inbox + button (#1808).
Guarded, in order of what would hurt most if it broke:

  1. Nothing outside the brain ever reaches a customer: `..`, an absolute path elsewhere, a symlink pointing out, a
     hidden folder, a folder, an empty or too large file and too many files are refused before ANY file is sent.
  2. Messenger: files go through the conversation's Page and chat, the text as the caption of the first, each recorded
     as the owner's image or file message (marked as sent by the tool) the chat can show; the bot keeps running.
  3. Messenger's 24-hour window holds as for text: Meta refuses, the model reads the reason in English, nothing is
     recorded and no copy is kept. The echo of a sent image carries the Page's echo tag, so it is not filed twice.
  4. A channel without file sending, an Instagram comment and a document on a Facebook comment are refused, also by
     the inbox route (before anything is stored).
  5. A failure after the first file says what already went, so the model never sends it twice.
  6. Personal Zalo: the image echo is remembered and the chat counts as answered, as for a text reply.
  7. The tool keeps `min_mode: full`, its schema and description are English, text stays optional with files.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import importlib.util
import json
import os
import sys
import tempfile
from pathlib import Path

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-inbox-reply-files-")
os.environ["JAVIS_ALLOWED_HOSTS"] = "testserver"
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import httpx  # noqa: E402
import channel_accounts  # noqa: E402
import channels  # noqa: E402
import conversations  # noqa: E402
import localefmt  # noqa: E402
import messenger_bot  # noqa: E402
import routes.conversations as rc  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
import main  # noqa: E402

_fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(extra) + "]") if extra and not cond else ""))
    if not cond:
        _fails.append(name)


if os.environ["JAVIS_STATE_DIR"] not in str(conversations.DB_PATH):
    print(f"FAIL the inbox store is not in the temp dir: {conversations.DB_PATH}. STOP.")
    sys.exit(1)

# ---- A brain with files, and things that must never leave it ----
BRAIN = Path(tempfile.mkdtemp(prefix="javis-brain-"))
OUTSIDE = Path(tempfile.mkdtemp(prefix="javis-outside-"))
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 64
PDF = b"%PDF-1.4 bang gia"
(BRAIN / "attachments").mkdir()
(BRAIN / "attachments" / "bang-gia.png").write_bytes(PNG)
(BRAIN / "attachments" / "catalog.pdf").write_bytes(PDF)
(BRAIN / "attachments" / "mau-2.jpg").write_bytes(PNG)
(BRAIN / "attachments" / "empty.png").write_bytes(b"")
(BRAIN / ".secrets").mkdir()
(BRAIN / ".secrets" / "key.png").write_bytes(PNG)
(OUTSIDE / "secret.png").write_bytes(PNG)
LINK_OK = True
try:
    os.symlink(OUTSIDE / "secret.png", BRAIN / "attachments" / "link-out.png")
    os.symlink(BRAIN / "attachments" / "bang-gia.png", BRAIN / "attachments" / "link-in.png")
except (OSError, NotImplementedError):
    LINK_OK = False

# ---- The plugin, as the hub loads it ----
spec = importlib.util.spec_from_file_location("inbox_reply_plugin", ROOT / "system/plugins/inbox-reply/plugin.py")
plugin = importlib.util.module_from_spec(spec)
spec.loader.exec_module(plugin)


class Ctx:
    vault_root = str(BRAIN)

    def __init__(self):
        self.tools = {}

    def register_tool(self, name, handler, min_mode, description="", schema=None, **kw):
        self.tools[name] = {"handler": handler, "min_mode": min_mode, "description": description, "schema": schema}


ctx = Ctx()
plugin.register(ctx)


def call(args, c=ctx):
    return asyncio.run(ctx.tools["inbox_reply"]["handler"](args, c))


# ---- Channel sends are faked unless a section uses the real one ----
SENT = []
FAIL_ON = {"name": ""}


async def fake_send_file(kenh, tk, chat_id, path, caption="", chat_type="private"):
    SENT.append({"kenh": kenh, "id": tk.get("id"), "token": bool(tk.get("token")), "chat": chat_id,
                 "name": Path(path).name, "exists": Path(path).is_file(), "caption": caption,
                 "in_state": os.environ["JAVIS_STATE_DIR"] in str(path)})
    if FAIL_ON["name"] and Path(path).name.endswith(FAIL_ON["name"]):
        return False, "Meta refused the upload"
    return True, ""


TEXTS = []


async def fake_gui(kenh, tk, chat_id, text, chat_type="private", **extra):
    TEXTS.append({"kenh": kenh, "chat": chat_id, "text": text})
    return True, ""


real_send_file, real_gui = channels.send_file, channels.gui
channels.send_file, channels.gui = fake_send_file, fake_gui

PAGE = "1234567890123"
TOKEN = "EAA" + "t" * 60
aid, err = channel_accounts.create_account({"channel": "messenger", "token": f"{PAGE} {TOKEN} {'c' * 32}",
                                            "external_id": PAGE, "label": "Shop", "meta": {"bot_name": "Shop"}})
check("a Messenger account to work with", bool(aid), err)


def chat(ext, channel="messenger", account=None, bot="bot-shop"):
    return conversations.ghi_su_kien({
        "channel": channel, "account_id": account or aid, "account_name": "Shop", "bot_id": bot,
        "external_chat_id": ext, "chat_type": "private", "sender_type": "customer", "sender_id": ext,
        "sender_name": "Chị Lan", "text": "Cho em xin bảng giá", "external_message_id": ext + "-1"})["conversation_id"]


def owner_rows(cid):
    return [m for m in conversations.tin_nhan(cid, limit=100) if m["sender_type"] == "human"]


def state_files(cid):
    d = rc._sent_dir(cid)
    return sorted(p.name for p in d.iterdir()) if d.is_dir() else []


# ============================================================
# 7. The tool's contract
# ============================================================
tool = ctx.tools["inbox_reply"]
props = (tool["schema"] or {}).get("properties") or {}
check("inbox_reply keeps min_mode full", tool["min_mode"] == "full", tool["min_mode"])
check("files is an optional list of strings; only conversation_id is required",
      props.get("files", {}).get("type") == "array" and tool["schema"].get("required") == ["conversation_id"], props)
model_text = json.dumps([t["description"] for t in ctx.tools.values()] + [tool["schema"], ctx.tools["inbox_find"]["schema"]],
                        ensure_ascii=False)
check("descriptions and schemas the model reads are English",
      not any(ch in model_text for ch in "ăâđêôơưạảấầẩẫậắằẳẵặẹẻẽếềểễệỉịọỏốồổỗộớờởỡợụủứừửữựỳỵỷỹ"), model_text[:300])

# ============================================================
# 2. Messenger: two files and a caption
# ============================================================
conv = chat("777")
out = call({"conversation_id": conv, "text": "Dạ em gửi chị bảng giá ạ",
            "files": ["attachments/bang-gia.png", str(BRAIN / "attachments" / "catalog.pdf")]})
d = json.loads(out) if out.startswith("{") else {}
check("two files sent", d.get("ok") is True and d.get("files_sent") == ["bang-gia.png", "catalog.pdf"], out)
check("through the conversation's Page account and chat, from copies kept in the state folder",
      len(SENT) == 2 and all(s["kenh"] == "messenger" and s["id"] == aid and s["token"] and s["chat"] == "777"
                             and s["exists"] and s["in_state"] for s in SENT), SENT)
check("the text rides as the caption of the first file only",
      [s["caption"] for s in SENT] == ["Dạ em gửi chị bảng giá ạ", ""] and not TEXTS, (SENT, TEXTS))
rows = owner_rows(conv)
check("recorded as the owner's image then file, marked as sent by the tool",
      [m["message_type"] for m in rows] == ["image", "file"]
      and all((m.get("metadata") or {}).get("via") == "tool" and (m.get("metadata") or {}).get("tu_javis") for m in rows)
      and rows[0]["text"] == "Dạ em gửi chị bảng giá ạ" and rows[1]["text"] == "[catalog.pdf]", rows)
md = (rows[0].get("metadata") or {}).get("sent_file") or {} if rows else {}
check("each record points at its kept copy, the way the + button records it",
      md.get("name") == "bang-gia.png" and md.get("size") == len(PNG) and Path(md.get("p", "")).is_file(), md)
check("the chat's bot keeps running after files sent from chat", conversations.chi_tiet(conv)["mode"] == "ai")
cl = TestClient(main.app)
g = cl.get(f"/conversations/{conv}/media", params={"p": md.get("p", "")})
check("the inbox can show the sent image", g.status_code == 200 and g.content == PNG, g.status_code)

SENT.clear()
out = call({"conversation_id": conv, "files": ["attachments/bang-gia.png"]})
check("files without text are fine", json.loads(out).get("ok") is True and SENT and SENT[0]["caption"] == "", out)
check("and recorded under the file's name", owner_rows(conv)[-1]["text"] == "[bang-gia.png]")

SENT.clear()
TEXTS.clear()
long_text = "Bảng giá chi tiết: " + "x" * (rc.MAX_CAPTION + 50)
out = call({"conversation_id": conv, "text": long_text, "files": ["attachments/bang-gia.png"]})
check("words longer than a caption follow the file as their own message",
      json.loads(out).get("ok") is True and SENT and SENT[0]["caption"] == "" and TEXTS and TEXTS[0]["text"] == long_text,
      (out, SENT, TEXTS))

TEXTS.clear()
out = call({"conversation_id": conv, "text": "Dạ shop còn ạ"})
check("a text-only reply still works as before", json.loads(out).get("ok") is True and len(TEXTS) == 1, out)
check("neither text nor files is refused", call({"conversation_id": conv, "files": []}).startswith("ERROR:"))

# ============================================================
# 1. Nothing outside the brain, nothing half sent
# ============================================================
SENT.clear()
TEXTS.clear()
n_rows = len(conversations.tin_nhan(conv, limit=200))
n_kept = len(state_files(conv))
bad = {
    "a path climbing out": ["../" + OUTSIDE.name + "/secret.png"],
    "an absolute path elsewhere": [str(OUTSIDE / "secret.png")],
    "a hidden folder": [".secrets/key.png"],
    "a folder": ["attachments"],
    "a missing file": ["attachments/nope.png"],
    "an empty file": ["attachments/empty.png"],
    "a good file next to a bad one": ["attachments/bang-gia.png", "../" + OUTSIDE.name + "/secret.png"],
    "too many files": ["attachments/bang-gia.png"] * (plugin.MAX_FILES + 1),
    "a blank path": ["attachments/bang-gia.png", "  "],
}
if LINK_OK:
    bad["a symlink pointing out of the brain"] = ["attachments/link-out.png"]
for label, files in bad.items():
    out = call({"conversation_id": conv, "text": "x", "files": files})
    check(f"refused: {label}", out.startswith("ERROR:") and "Nothing was sent" in out, out)
old_max = rc.MAX_SENT_FILE
rc.MAX_SENT_FILE = 10
out = call({"conversation_id": conv, "files": ["attachments/bang-gia.png"]})
rc.MAX_SENT_FILE = old_max
check("refused: a file over the size cap", out.startswith("ERROR:") and "larger than" in out, out)
check("no refusal sent, recorded or kept anything",
      not SENT and not TEXTS and len(conversations.tin_nhan(conv, limit=200)) == n_rows
      and len(state_files(conv)) == n_kept, (SENT, TEXTS))
out = call({"conversation_id": conv, "files": ["attachments/bang-gia.png"]}, c=type("NoBrain", (), {"vault_root": ""})())
check("a call with no brain cannot take files", out.startswith("ERROR:") and "no brain" in out, out)
if LINK_OK:
    SENT.clear()
    out = call({"conversation_id": conv, "files": ["attachments/link-in.png"]})
    check("a symlink that stays inside the brain is followed", json.loads(out).get("ok") is True
          and SENT and SENT[0]["name"].endswith("bang-gia.png"), out)
SENT.clear()
out = call({"conversation_id": conv, "files": ["attachments/bang-gia.png", "./attachments/bang-gia.png"]})
check("the same file named twice goes once", json.loads(out).get("ok") is True and len(SENT) == 1, out)

# ============================================================
# 4. What a channel or a comment cannot carry
# ============================================================
SENT.clear()
th = chat("thr:42", channel="threads", account="th1", bot="")
out = call({"conversation_id": th, "files": ["attachments/bang-gia.png"]})
check("a channel without file sending says so, and sends nothing",
      out.startswith("ERROR:") and "cannot send images or files" in out and not SENT, out)
r = cl.post(f"/conversations/{th}/send-file", files={"file": ("a.png", PNG, "image/png")})
check("the inbox route refuses it before storing anything",
      r.status_code == 400 and r.json().get("code") == "unsupported" and not state_files(th) and not SENT, r.text)
igc = chat("igc:c9")
out = call({"conversation_id": igc, "files": ["attachments/bang-gia.png"]})
check("an Instagram comment takes no file", out.startswith("ERROR:") and "Instagram" in out and not SENT, out)
cmt = chat("cmt:555_9")
out = call({"conversation_id": cmt, "files": ["attachments/bang-gia.png", "attachments/catalog.pdf"]})
check("a Facebook comment with a document: refused before the image goes", out.startswith("ERROR:") and not SENT, out)
out = call({"conversation_id": cmt, "files": ["attachments/bang-gia.png"]})
check("a Facebook comment with an image goes", json.loads(out).get("ok") is True and SENT[-1]["chat"] == "cmt:555_9", out)

# ============================================================
# 5. A failure after the first file
# ============================================================
SENT.clear()
part = chat("778")
FAIL_ON["name"] = "catalog.pdf"
out = call({"conversation_id": part, "text": "Gửi chị",
            "files": ["attachments/bang-gia.png", "attachments/catalog.pdf", "attachments/mau-2.jpg"]})
FAIL_ON["name"] = ""
check("the error names the failure and what already went",
      out.startswith("ERROR:") and "Meta refused the upload" in out and "do not send again: bang-gia.png" in out
      and "Not sent: mau-2.jpg" in out, out)
check("only the file that went is recorded", [m["message_type"] for m in owner_rows(part)] == ["image"], owner_rows(part))
check("and the failed one keeps no copy", len(state_files(part)) == 1, state_files(part))

# ============================================================
# 3. Messenger's 24-hour window, through the real channel and transport
# ============================================================
channels.send_file, channels.gui = real_send_file, real_gui
GRAPH = []
GRAPH_MODE = {"window": True}


def graph(req):
    GRAPH.append({"path": req.url.path, "body": req.content.decode("utf-8", "replace")})
    if GRAPH_MODE["window"]:
        return httpx.Response(400, json={"error": {"code": 10, "error_subcode": 2018278,
                                                   "message": "(#10) This message is sent outside of allowed window."}})
    return httpx.Response(200, json={"recipient_id": "779", "message_id": "m_1"})


_orig_client = httpx.AsyncClient


class MockClient(_orig_client):
    def __init__(self, *a, **kw):
        kw["transport"] = httpx.MockTransport(graph)
        super().__init__(*a, **kw)


httpx.AsyncClient = MockClient
late = chat("779")
n_rows = len(conversations.tin_nhan(late, limit=50))
tok = localefmt.dat_ngon_ngu_yeu_cau("vi")       # a Vietnamese screen: the model still reads English
try:
    out = call({"conversation_id": late, "text": "Dạ em gửi chị ảnh", "files": ["attachments/bang-gia.png"]})
    out_text = call({"conversation_id": late, "text": "Dạ em gửi chị ảnh"})
finally:
    localefmt.bo_ngon_ngu_yeu_cau(tok)
check("outside the 24-hour window the file is refused by Meta and the model reads why, in English",
      out.startswith("ERROR:") and "24 hours" in out and "2018278" in out and "Nothing was sent" in out, out)
check("the same rule and words as a text reply", out_text.startswith("ERROR:") and "24 hours" in out_text, out_text)
check("the upload went to the Page's Send API", GRAPH and GRAPH[0]["path"].endswith(f"/{PAGE}/messages"), GRAPH[:1])
check("nothing recorded, no copy kept", len(conversations.tin_nhan(late, limit=50)) == n_rows and not state_files(late))
r = cl.post(f"/conversations/{late}/send-file", files={"file": ("a.png", PNG, "image/png")})
check("the inbox route gives the same reason", r.status_code == 400 and r.json().get("code") == "send_failed"
      and "24" in r.json().get("error", ""), r.text)

GRAPH.clear()
GRAPH_MODE["window"] = False
out = call({"conversation_id": late, "files": ["attachments/bang-gia.png"]})
check("inside the window the image goes", json.loads(out).get("ok") is True, out)
check("carrying the Page's echo tag", GRAPH and '"metadata": "javis"' in GRAPH[0]["body"], GRAPH[:1])
STAFF = []


async def staff_event(kind, payload):
    STAFF.append((kind, payload))

bot = messenger_bot.MessengerBot(f"{PAGE} {TOKEN} {'c' * 32}", "", None, giau_trang_thai=True)
bot.event_fn = staff_event
asyncio.run(bot._on_staff({"recipient": {"id": "779"}, "message": {
    "mid": "m_1", "is_echo": True, "metadata": messenger_bot.ECHO_TAG,
    "attachments": [{"type": "image", "payload": {"url": "https://cdn.example/x.png"}}]}}))
check("so its echo is dropped, not filed as a staff message a second time", STAFF == [], STAFF)
httpx.AsyncClient = _orig_client

# ============================================================
# 6. Personal Zalo: echo remembered, chat counted as answered
# ============================================================
import channels.zalo_personal as zp  # noqa: E402
import zalo_personal_channel as zc  # noqa: E402

ZSENT = []


async def fake_gui_anh(tk, chat_id, paths, chat_type="private"):
    ZSENT.append({"account": tk.get("id"), "chat": chat_id, "paths": list(paths)})
    return True, ""

_real_conn, _real_gui_anh = zc.ket_noi_theo_id, zp.gui_anh
zc.ket_noi_theo_id = lambda conn_id: {"id": "zconn1"} if conn_id == "zconn1" else None
zp.gui_anh = fake_gui_anh
zconv = chat("u123", channel="zalo_personal", account="zconn1")
zc._CHO_CHU[("zconn1", "u123")] = {"evs": [], "dau": 0}
out = call({"conversation_id": zconv, "files": ["attachments/bang-gia.png"]})
check("a personal Zalo image goes through the account's session",
      json.loads(out).get("ok") is True and ZSENT and ZSENT[0]["account"] == "zconn1" and ZSENT[0]["chat"] == "u123", out)
check("its echo is remembered once, so the read loop does not record it again",
      zc._la_vong_anh("zconn1", "u123") and not zc._la_vong_anh("zconn1", "u123"))
check("the chat counts as answered, as after a text reply", ("zconn1", "u123") not in zc._CHO_CHU)
zc.ket_noi_theo_id, zp.gui_anh = _real_conn, _real_gui_anh

if _fails:
    print(f"\nFAIL - test_inbox_reply_files: {len(_fails)} failed: " + ", ".join(_fails))
    sys.exit(1)
print("\nOK - test_inbox_reply_files: all pass")
