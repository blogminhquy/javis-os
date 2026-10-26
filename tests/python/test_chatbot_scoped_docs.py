"""Chat-scoped documents (0.338.0): one bot, many customer groups, each group reads only its own file.

    python tests/run.py chatbot_scoped_docs      (no network)

A studio runs one "read_docs" bot in many Zalo groups, one group per signed customer, and keeps one file per
customer (contract, deposit, promises). The bot must read the whole file of the customer in the chat it answers,
and never anything of another customer: not a chunk in the prompt, not a search hit, not a file name in the list.
Proposal from a user (2026-10-26); its acceptance checks are pinned here as written:

  - files A and B both say "cọc": a search in group A shows only A, in group B only B;
  - in group A, javis_docs_read of B's path answers "không có tài liệu";
  - in group A, javis_docs_list does not name B;
  - the same through the in-process path (API engines) and the hub over HTTP (Claude Code, Codex).

Plus the rules that keep it fail-closed: the chat id comes from the turn the server bound, never from a tool
argument; no turn means no scoped document; a scoped file is never part of the shared index or the role profile.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path

_STATE = tempfile.mkdtemp(prefix="javis-scoped-")
os.environ["JAVIS_STATE_DIR"] = _STATE
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import chatbot_doc_tools as dt  # noqa: E402
import chatbot_grounding as g  # noqa: E402
import chatbot_reply_policy as rp  # noqa: E402
import mcp_hub  # noqa: E402
import turn_context  # noqa: E402

_fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(extra)[:300] + "]") if extra and not cond else ""))
    if not cond:
        _fails.append(name)


def run(c):
    return asyncio.run(c)


BRAIN = Path(tempfile.mkdtemp(prefix="javis-scoped-brain-")).resolve()
A, B, C = "7012345678901234567", "7098765432109876543", "-1001234567"


def w(rel, text):
    p = BRAIN / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


w("faq/bang-gia.md", "# Bảng giá chụp cưới\n\n## Gói cơ bản\n\nGói cơ bản 15 triệu, gồm 2 váy.\n")
w(f"rieng-theo-nhom/{A}/ho-so-lan.md", "---\ntype: ho-so\n---\n# Hồ sơ cô dâu Lan\n\n## Tiền cọc\n\n"
  "Đã cọc 5 triệu ngày 01/10. Còn lại 10 triệu.\n\n## Hẹn\n\nHẹn gửi album thử 20/10.\n")
w(f"rieng-theo-nhom/{B}/ho-so-hoa.md", "# Hồ sơ cô dâu Hoa\n\n## Tiền cọc\n\nĐã cọc 8 triệu ngày 05/10. "
  "Còn lại 12 triệu.\n")
# Frontmatter wins over the folder: this file sits under some other folder name but belongs to group A.
w("rieng-theo-nhom/tam/phu-luc-lan.md", f"---\nchat_scope: {A}\n---\n# Phụ lục Lan\n\nThêm một váy cưới đỏ.\n")
# Frontmatter outside the folder, as a list with a Telegram-style negative id kept as text.
w("khach/ho-so-minh.md", f"---\nchat_scope: [\"{C}\", 7000000000000000001]\n---\n# Hồ sơ Minh\n\n"
  "## Tiền cọc\n\nĐã cọc 3 triệu.\n")
# Block list form.
w("khach/ho-so-tuan.md", f"---\ntitle: Tuấn\nchat_scope:\n  - {B}\n  - nhom-khac\n---\n# Hồ sơ Tuấn\n\nCọc 2 triệu.\n")
# Directly in the folder, no scope: nobody sees it.
w("rieng-theo-nhom/ghi-chu-chung.md", "# Ghi chú\n\nTiền cọc của mọi khách: xem từng hồ sơ.\n")
# A folder of that name deeper down is hidden from everyone, not shared with everyone.
w("cu/rieng-theo-nhom/ho-so-cu.md", "# Hồ sơ cũ\n\nĐã cọc 1 triệu.\n")
# `chat_scope:` with nothing after it: nobody.
w("khach/rong.md", "---\nchat_scope:\n---\n# Rỗng\n\nCọc gì đó.\n")


def paths(hits):
    return {str(h.get("path") or "").replace("\\", "/") for h in hits}


# ============================================================
# 1. The frontmatter parser keeps ids as exact text
# ============================================================
check("scalar id", g._parse_scope(f"chat_scope: {A}") == (A,))
check("quoted negative id stays text", g._parse_scope('chat_scope: "-100123"') == ("-100123",))
check("leading zero kept (YAML would make it a number)", g._parse_scope("chat_scope: 0123") == ("0123",))
check("inline list", g._parse_scope("chat_scope: [a, 'b', \"c\"]") == ("a", "b", "c"))
check("block list", g._parse_scope("x: 1\nchat_scope:\n  - a\n  - b\ny: 2") == ("a", "b"))
check("empty value: nobody", g._parse_scope("chat_scope:") == ())
check("no key: not scoped", g._parse_scope("type: faq") is None)
check("an indented key is not the key", g._parse_scope("meta:\n  chat_scope: a") is None)

# ============================================================
# 2. The shared index never holds a scoped file
# ============================================================
shared = set(g.ds_tai_lieu(BRAIN))
check("shared documents: only the price list", shared == {"faq/bang-gia.md"}, shared)
check("shared keyword index has no scoped chunk",
      paths(g.chi_muc(BRAIN)["manh"]) == {"faq/bang-gia.md"}, paths(g.chi_muc(BRAIN)["manh"]))
check("search without a chat: no 'cọc' file at all", not paths(g.tim(BRAIN, "tiền cọc còn lại bao nhiêu", 10))
      & {f"rieng-theo-nhom/{A}/ho-so-lan.md", f"rieng-theo-nhom/{B}/ho-so-hoa.md"})

in_a = set(g.ds_tai_lieu(BRAIN, A))
check("group A sees the shared list plus its own two files",
      in_a == {"faq/bang-gia.md", f"rieng-theo-nhom/{A}/ho-so-lan.md", "rieng-theo-nhom/tam/phu-luc-lan.md"}, in_a)
in_b = set(g.ds_tai_lieu(BRAIN, B))
check("group B sees its folder file and the block-list file",
      in_b == {"faq/bang-gia.md", f"rieng-theo-nhom/{B}/ho-so-hoa.md", "khach/ho-so-tuan.md"}, in_b)
check("an inline-list id matches", "khach/ho-so-minh.md" in g.ds_tai_lieu(BRAIN, C))
check("the second id of a list matches", "khach/ho-so-minh.md" in g.ds_tai_lieu(BRAIN, "7000000000000000001"))
for chat in (A, B, C, "nhom-khac", "tam"):
    seen = set(g.ds_tai_lieu(BRAIN, chat))
    check(f"nobody sees the unscoped folder file ({chat})", "rieng-theo-nhom/ghi-chu-chung.md" not in seen)
    check(f"nobody sees a nested rieng-theo-nhom folder ({chat})", "cu/rieng-theo-nhom/ho-so-cu.md" not in seen)
    check(f"nobody sees an empty chat_scope ({chat})", "khach/rong.md" not in seen)
check("the folder name loses to the frontmatter line", "rieng-theo-nhom/tam/phu-luc-lan.md" not in
      g.ds_tai_lieu(BRAIN, "tam"))
check("a blank chat id is no chat", set(g.ds_tai_lieu(BRAIN, "  ")) == shared)

# ============================================================
# 3. Pre-turn search: both files say "cọc", each group gets its own
# ============================================================
Q = "Em đã cọc bao nhiêu tiền rồi, tiền cọc còn lại bao nhiêu?"
ta = g.thu_thap(BRAIN, Q, 4, None, A)
tb = g.thu_thap(BRAIN, Q, 4, None, B)
check("group A: found, from A only", ta["co"] and any("ho-so-lan" in p for p in ta["nguon"])
      and not any("ho-so-hoa" in p for p in ta["nguon"]), ta["nguon"])
check("group A: B's numbers never reach the prompt", "8 triệu" not in ta["khoi"] and "5 triệu" in ta["khoi"])
check("group B: found, from B only", tb["co"] and any("ho-so-hoa" in p for p in tb["nguon"])
      and not any("ho-so-lan" in p for p in tb["nguon"]), tb["nguon"])
check("group B: A's numbers never reach the prompt", "5 triệu" not in tb["khoi"])
check("again in A after B (per-chat cache slots do not mix)",
      "8 triệu" not in g.thu_thap(BRAIN, Q, 4, None, A)["khoi"])
t0 = g.thu_thap(BRAIN, Q, 4)
check("no chat: no customer file in the prompt", "5 triệu" not in t0["khoi"] and "8 triệu" not in t0["khoi"])
linked = [{"path": "gdoc:abc", "title": "Chính sách cọc", "text": "Cọc tối thiểu 30% giá trị gói."}]
tl = g.thu_thap(BRAIN, Q, 6, linked, A)
check("linked Google docs and the chat's file search together",
      "gdoc:abc" in tl["nguon"] or any("ho-so-lan" in p for p in tl["nguon"]), tl["nguon"])

# ============================================================
# 4. The three tools, in-process (API engines): the chat comes from the bound turn
# ============================================================
tools, route = dt.build(BRAIN)
call = lambda name, args=None: run(route[name]["call"](args or {}))  # noqa: E731


def in_turn(chat, fn):
    tok = turn_context.bind(turn_context.make("zalo_personal", "u1", "group", chat, False))
    try:
        return fn()
    finally:
        turn_context.reset(tok)


s_a = in_turn(A, lambda: call("javis_docs_search", {"query": "cọc"}))
s_b = in_turn(B, lambda: call("javis_docs_search", {"query": "cọc"}))
check("search 'cọc' in group A: A only", "ho-so-lan" in s_a and "ho-so-hoa" not in s_a and "8 triệu" not in s_a, s_a)
check("search 'cọc' in group B: B only", "ho-so-hoa" in s_b and "ho-so-lan" not in s_b and "5 triệu" not in s_b, s_b)
r_ab = in_turn(A, lambda: call("javis_docs_read", {"path": f"rieng-theo-nhom/{B}/ho-so-hoa.md"}))
check("read B's file from group A: 'không có tài liệu'", r_ab.startswith("ERROR: không có tài liệu"), r_ab)
check("read B by bare file name from group A: no", in_turn(A, lambda: call(
    "javis_docs_read", {"path": "ho-so-hoa.md"})).startswith("ERROR"))
check("read B with ../ tricks from group A: no", in_turn(A, lambda: call(
    "javis_docs_read", {"path": f"rieng-theo-nhom/{A}/../{B}/ho-so-hoa.md"})).startswith("ERROR"))
r_aa = in_turn(A, lambda: call("javis_docs_read", {"path": "ho-so-lan.md"}))
check("read own file in group A: whole file, frontmatter stripped", "Hẹn gửi album thử" in r_aa
      and "type: ho-so" not in r_aa, r_aa[:200])
l_a = in_turn(A, lambda: call("javis_docs_list"))
check("list in group A: own files, never B's name", "ho-so-lan" in l_a and "phu-luc-lan" in l_a
      and "ho-so-hoa" not in l_a and "ho-so-tuan" not in l_a and "ho-so-minh" not in l_a, l_a)
l_none = call("javis_docs_list")
check("list with no turn: shared documents only", "bang-gia" in l_none and "ho-so" not in l_none, l_none)
check("read with no turn: a scoped file does not open", call(
    "javis_docs_read", {"path": f"rieng-theo-nhom/{A}/ho-so-lan.md"}).startswith("ERROR"))
check("a 'chat_id' tool argument is ignored", "ho-so-hoa" not in call("javis_docs_search", {"query": "cọc", "chat_id": B}))
toc_a = dt.table_of_contents(BRAIN, chat_id=A)
check("reply judge's table of contents in group A: A's file, not B's", "ho-so-lan" in toc_a and "ho-so-hoa" not in toc_a,
      toc_a)
check("table of contents with no chat: no scoped file", "ho-so" not in dt.table_of_contents(BRAIN))

# ============================================================
# 5. The hub over HTTP (Claude Code / Codex): the chat comes from the X-Javis-Turn key
# ============================================================
class _HttpReq:
    def __init__(self, body, headers):
        self._b = body
        self.headers = {k.lower(): v for k, v in headers.items()}

    async def json(self):
        return self._b


def http_call(name, args, turn_key):
    hdr = {"authorization": f"Bearer {mcp_hub.hub_token()}", "x-javis-mode": "read_docs",
           "x-javis-vault": str(BRAIN), "x-javis-bot": "1"}
    if turn_key:
        hdr[turn_context.HEADER] = turn_key
    body = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": name, "arguments": args}}
    resp = run(mcp_hub.handle_http(_HttpReq(body, hdr)))
    return json.loads(resp.body)["result"]["content"][0]["text"]


def key_for(chat):
    tok = turn_context.bind(turn_context.make("zalo_personal", "u1", "group", chat, False))
    return tok, turn_context.issue_key()


tok_a, key_a = key_for(A)
try:
    h_a = http_call("javis_docs_search", {"query": "cọc"}, key_a)
    h_read = http_call("javis_docs_read", {"path": f"rieng-theo-nhom/{B}/ho-so-hoa.md"}, key_a)
    h_list = http_call("javis_docs_list", {}, key_a)
finally:
    turn_context.reset(tok_a)
check("HTTP search 'cọc' with group A's key: A only", "ho-so-lan" in h_a and "ho-so-hoa" not in h_a, h_a)
check("HTTP read of B with group A's key: 'không có tài liệu'", h_read.startswith("ERROR: không có tài liệu"), h_read)
check("HTTP list with group A's key: never B's name", "ho-so-lan" in h_list and "ho-so-hoa" not in h_list, h_list)
tok_b, key_b = key_for(B)
try:
    h_b = http_call("javis_docs_search", {"query": "cọc"}, key_b)
finally:
    turn_context.reset(tok_b)
check("HTTP search 'cọc' with group B's key: B only", "ho-so-hoa" in h_b and "ho-so-lan" not in h_b, h_b)
check("HTTP with no key: no scoped file", "ho-so" not in http_call("javis_docs_list", {}, None))
check("HTTP with a forged key: no scoped file", "ho-so" not in http_call("javis_docs_list", {}, "gia-mao-khoa"))
check("HTTP with a key whose turn ended: no scoped file", "ho-so" not in http_call("javis_docs_list", {}, key_a))

# ============================================================
# 6. The role profile (shared by every chat) never lists a customer's file
# ============================================================
titles = rp.list_doc_titles(str(BRAIN))
check("role profile titles: no scoped file", not any(t.startswith("ho-so") or t == "phu-luc-lan" or t == "rong"
                                                     for t in titles), titles)
check("role profile titles: shared file still there", "bang-gia" in titles, titles)
check("a brain whose only documents are scoped still has documents", g.has_scoped_docs(BRAIN))

# ============================================================
# 7. The bot runtime passes the chat of the message into the pre-turn search
# ============================================================
import chatbot_runtime  # noqa: E402

chatbot_runtime._deps["brain_root"] = lambda _b: str(BRAIN)
cfg = {"id": "bot_soho", "brain": "soho", "muc_quyen": "read_docs"}
rt_a = run(chatbot_runtime._tra_tai_lieu("bot_soho", cfg, Q, A))
check("runtime pre-turn search in group A: A's file", any("ho-so-lan" in p for p in rt_a["nguon"])
      and "8 triệu" not in rt_a["khoi"], rt_a["nguon"])
rt_none = run(chatbot_runtime._tra_tai_lieu("bot_soho", cfg, Q))
check("runtime pre-turn search without a chat (Try bot): no customer file",
      "5 triệu" not in rt_none["khoi"] and "8 triệu" not in rt_none["khoi"])
judge_b = run(chatbot_runtime._tra_cho_phan_xu("bot_soho", cfg, "album thử gửi chưa", B))
check("reply judge lookup in group B never shows A's file", "ho-so-lan" not in json.dumps(judge_b, ensure_ascii=False),
      judge_b)

print()
if _fails:
    print(f"{len(_fails)} FAIL: {_fails}")
    sys.exit(1)
print("all ok")
