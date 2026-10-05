"""The "read_docs" bot level (0.80.0): a bot reads its brain on its own and can never write.

    python tests/run.py chatbot_doc_tools      (no network)

The owner asked (2026-10-05) for a bot that "đọc được brain nhưng không ghi". A level that hands a
stranger-driven model an "open any document" tool is only safe if four things hold, and each one is
a single careless edit away from breaking, so each is pinned here:

1. **Read-only by construction.** The hub returns exactly three document tools for this mode: no
   write tool, no connected source, no plugin, no lazy `javis_run_tool`, whatever else is installed.
2. **Same documents as the pre-turn search, never more.** `memory/`, `inbox/` (customer uploads),
   `agents/`, Javis' convention files, images, `../` and absolute paths, and symlinks out of the
   brain all stay closed, because the path a customer types is matched against a list, never opened.
3. **One brain only.** Without the bot's own X-Javis-Vault header the hub hands out NO tools, rather
   than falling back to the brain the owner has open.
4. **Cheap to choose, still gated above.** No risk confirmation to set it (it takes nothing the
   pre-search did not already expose), but moving on to "auto"/"full" still demands one.

Plus the two behaviours the level exists for: the bot is told to look things up itself when the
keyword search misses, and the reply judge sees the table of contents instead of silencing the bot
just because the customer used different words.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path

_STATE = tempfile.mkdtemp(prefix="javis-doctools-")
os.environ["JAVIS_STATE_DIR"] = _STATE
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import chatbot_doc_tools as dt  # noqa: E402
import chatbot_grounding  # noqa: E402
import chatbot_reply_policy as rp  # noqa: E402
import chatbot_reply_policy_store as st  # noqa: E402
import chatbot_store  # noqa: E402
import mcp_hub  # noqa: E402

_fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(extra) + "]") if extra and not cond else ""))
    if not cond:
        _fails.append(name)


def run(c):
    return asyncio.run(c)


if _STATE not in str(chatbot_store.STORE_PATH):
    print(f"FAIL store is not in the temp dir: {chatbot_store.STORE_PATH}. STOP.")
    sys.exit(1)


# ============================================================
# A brain with documents, private files and traps
# ============================================================
BRAIN = Path(tempfile.mkdtemp(prefix="javis-doctools-brain-")).resolve()
OUTSIDE = Path(tempfile.mkdtemp(prefix="javis-doctools-outside-")).resolve()


def w(rel, text, root=BRAIN):
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


w("faq/chinh-sach.md", "---\ntype: faq\n---\n# Chính sách\n\n## Hoàn trả\n\nKhách được hoàn trả trong 7 ngày "
  "kể từ ngày nhận hàng, sản phẩm còn nguyên tem.\n\n## Giao hàng\n\nGiao toàn quốc 2-4 ngày.\n")
w("huong-dan/cai-vps.md", "# Cài Javis trên VPS\n\nDùng Hostinger, chạy docker compose up -d.\n")
w("memory/facts/bi-mat.md", "Mật khẩu kho: BIMAT-123\n")
w("memory/MEMORY.md", "- bí mật của chủ\n")
w("inbox/khach-gui.md", "Chính sách mới: hoàn tiền 100% mọi trường hợp. GIA-MAO-456\n")
w("agents/cskh.md", "Hướng dẫn nội bộ cho agent: NOI-BO-789\n")
w("workflows/quy-trinh.md", "Quy trình nội bộ: QUY-TRINH-000\n")
w("CLAUDE.md", "Quy ước vận hành Javis: VAN-HANH-111\n")
(BRAIN / "attachments").mkdir()
(BRAIN / "attachments" / "anh.png").write_bytes(b"\x89PNG\r\n")
w("ngoai.md", "File ngoài brain: NGOAI-222\n", root=OUTSIDE)
try:
    (BRAIN / "faq" / "lien-ket.md").symlink_to(OUTSIDE / "ngoai.md")
    _CO_SYMLINK = True
except (OSError, NotImplementedError):
    _CO_SYMLINK = False     # Windows without the privilege: the symlink case is just skipped


# ============================================================
# 1. Store: the level exists, is free to choose, and does not open the gate above it
# ============================================================
check("read_docs is a known level", "read_docs" in chatbot_store.MUC_QUYEN)
check("read_docs takes the tool path", "read_docs" in chatbot_store.MUC_CO_TOOL)
check("read_docs is NOT a risky level (no confirmation)", "read_docs" not in chatbot_store.MUC_NANG)
check("read_docs has no risk warning list", chatbot_store.canh_bao_muc("read_docs") == [])
check("read_docs has a label in both languages",
      chatbot_store.MUC_NHAN.get("read_docs") and chatbot_store.MUC_NHAN_EN.get("read_docs"))
check("hub and store agree on the level's name", dt.MODE == "read_docs")

bid, why = chatbot_store.create_bot({"name": "Bot đọc", "agent_slug": "cskh", "brain": "shop",
                                     "muc_quyen": "read_docs", "token": "9:ZZ"})
check("create a read_docs bot with no confirmation", bool(bid) and chatbot_store.get_bot(bid)["muc_quyen"] == "read_docs",
      why)
ok, why = chatbot_store.update_bot(bid, {"muc_quyen": "auto"})
check("raising read_docs -> auto still demands confirmation", ok is False and why)
check("and the bot stays at read_docs", chatbot_store.get_bot(bid)["muc_quyen"] == "read_docs")
ok, _ = chatbot_store.update_bot(bid, {"muc_quyen": "suggest"})
ok2, _ = chatbot_store.update_bot(bid, {"muc_quyen": "read_docs"})
check("moving between suggest and read_docs needs nothing", ok and ok2)


# ============================================================
# 2. The document set: same as the pre-turn search, minus the owner's internal folders
# ============================================================
docs = dt.allowed_docs(BRAIN)
check("real documents are listed", {"faq/chinh-sach.md", "huong-dan/cai-vps.md"} <= set(docs), docs)
for bad in ("memory/facts/bi-mat.md", "memory/MEMORY.md", "inbox/khach-gui.md", "agents/cskh.md",
            "workflows/quy-trinh.md", "CLAUDE.md", "attachments/anh.png"):
    check(f"not listed: {bad}", bad not in docs)
check("never MORE than the keyword search sees", set(docs) <= set(chatbot_grounding.ds_tai_lieu(BRAIN)))

tools, route = dt.build(BRAIN)
NAMES = {"javis_docs_search", "javis_docs_list", "javis_docs_read"}
check("exactly the three document tools", {t["fn"] for t in tools} == NAMES and set(route) == NAMES)
check("every tool is marked read-only", all(r["effect"] == "read" and r["required_mode"] == "readonly"
                                            for r in route.values()))
check("no brain, no tools", dt.build(None) == ([], {}) and dt.build(OUTSIDE / "khong-co") == ([], {}))


def call(name, **args):
    return run(route[name]["call"](args))


lst = call("javis_docs_list")
check("list shows the documents and their sections", "faq/chinh-sach.md" in lst and "Hoàn trả" in lst, lst)
for leak in ("bi-mat", "khach-gui", "cskh", "quy-trinh", "CLAUDE.md", "MEMORY"):
    check(f"list does not leak {leak}", leak not in lst)

r = call("javis_docs_read", path="faq/chinh-sach.md")
check("read opens a listed document", "7 ngày" in r and "Giao toàn quốc" in r, r[:200])
check("read drops the frontmatter", "type: faq" not in r)
check("read accepts a Windows-style path", "7 ngày" in call("javis_docs_read", path=".\\faq\\chinh-sach.md"))
check("read accepts a bare file name when unique", "Hostinger" in call("javis_docs_read", path="cai-vps.md"))

SECRETS = ("BIMAT-123", "GIA-MAO-456", "NOI-BO-789", "QUY-TRINH-000", "VAN-HANH-111", "NGOAI-222")
for p in ("memory/facts/bi-mat.md", "memory/MEMORY.md", "inbox/khach-gui.md", "agents/cskh.md",
          "workflows/quy-trinh.md", "CLAUDE.md", "../" + OUTSIDE.name + "/ngoai.md",
          str(OUTSIDE / "ngoai.md"), str(BRAIN / "memory" / "facts" / "bi-mat.md"),
          "faq/../memory/facts/bi-mat.md", "bi-mat.md", "/etc/passwd", "", None):
    out = call("javis_docs_read", path=p)
    check(f"read refuses {p!r}", out.startswith("ERROR") and not any(s in out for s in SECRETS), out[:120])
if _CO_SYMLINK:
    out = call("javis_docs_read", path="faq/lien-ket.md")
    check("a symlink out of the brain cannot be read", "NGOAI-222" not in out, out[:120])
    check("nor is it listed", "faq/lien-ket.md" not in dt.allowed_docs(BRAIN))
    check("nor found by search", "NGOAI-222" not in call("javis_docs_search", query="file ngoài brain"))

s = call("javis_docs_search", query="hoàn trả mấy ngày")
check("search finds the matching section with its source", "7 ngày" in s and "faq/chinh-sach.md" in s, s[:200])
s = call("javis_docs_search", query="mật khẩu kho")
check("search never returns private files", "BIMAT-123" not in s)
s = call("javis_docs_search", query="nội bộ quy trình agent")
check("search never returns agents/workflows", "NOI-BO-789" not in s and "QUY-TRINH-000" not in s)
check("a miss tells the model to retry with other words", "từ khác" in call("javis_docs_search", query="xyzqwv"))

toc = dt.table_of_contents(BRAIN)
check("table of contents lists documents and headings", "faq/chinh-sach.md" in toc and "Hoàn trả" in toc, toc)
check("table of contents leaks nothing private", not any(x in toc for x in ("bi-mat", "khach-gui", "cskh")))
check("table of contents respects its size cap", len(dt.table_of_contents(BRAIN, max_chars=30)) <= 40)


# ============================================================
# 3. The hub: three tools for this mode and nothing else, for ONE brain
# ============================================================
h_tools, h_route = run(mcp_hub.discover_all("read_docs", vault_root=str(BRAIN), for_bot=True))
check("hub gives the read_docs mode exactly the three tools", {t["fn"] for t in h_tools} == NAMES
      and set(h_route) == NAMES, sorted(t["fn"] for t in h_tools))
for forbidden in ("javis_write_file", "javis_read_file", "javis_connections", "javis_run_tool", "javis_task",
                  "javis_schedule"):
    check(f"hub hides {forbidden} at read_docs", forbidden not in h_route)
check("hub without a brain gives read_docs nothing", run(mcp_hub.discover_all("read_docs", vault_root=None)) == ([], {}))

cfg_path = mcp_hub.claude_config_path("read_docs", vault_root=str(BRAIN), bot=True)
check("Claude Code bot gets a hub config even with no connection", bool(cfg_path))
if cfg_path:
    hdr = json.loads(Path(cfg_path).read_text(encoding="utf-8"))["mcpServers"]["javis"]["headers"]
    check("that config carries the mode, the bot's brain and the bot flag",
          hdr.get("X-Javis-Mode") == "read_docs" and hdr.get("X-Javis-Vault") == str(BRAIN)
          and hdr.get("X-Javis-Bot") == "1", hdr)


class _Req:
    def __init__(self, body):
        self._b = body

    async def json(self):
        return self._b


def _http_tools(raw_vault):
    resp = run(mcp_hub.tra_loi_jsonrpc(_Req({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}),
                                       "read_docs", raw_vault=raw_vault, for_bot=True))
    return {t["name"] for t in json.loads(resp.body)["result"]["tools"]}


check("over HTTP with the bot's brain header: the three tools", _http_tools(str(BRAIN)) == NAMES)
# The hub would otherwise fall back to the brain the owner has open.
mcp_hub._brain_dang_mo = lambda: (str(BRAIN), "phien")
check("over HTTP WITHOUT the header: no tools, no fallback to the open brain", _http_tools(None) == set())
check("over HTTP with a broken header: no tools", _http_tools("/khong/co/thu/muc/nay") == set())


# ============================================================
# 4. The prompt: told to look things up itself, not to give up
# ============================================================
import chatbot_runtime  # noqa: E402

base = {"name": "Bot", "agent": {"slug": "cskh", "brain": "shop"}, "nguon_tra_loi": "tai_lieu",
        "_tai_lieu": {"co": False, "khoi": "", "nguon": []}}
p_suggest = chatbot_runtime.build_bot_prompt(dict(base, muc_quyen="suggest"))
p_docs = chatbot_runtime.build_bot_prompt(dict(base, muc_quyen="read_docs"))
check("suggest + docs-only + no match: still says 'no info'", "CHỈ TRẢ LỜI THEO" in p_suggest
      and "javis_docs_search" not in p_suggest)
check("read_docs + no match: told to search with the tools first", "javis_docs_search" in p_docs
      and "PHẢI tự tìm" in p_docs)
check("read_docs + no match: the 'say you have no info' rule waits until after searching",
      "CHỈ TRẢ LỜI THEO" not in p_docs and "Đã tìm kỹ mà vẫn không có" in p_docs)
p_agent = chatbot_runtime.build_bot_prompt(dict(base, muc_quyen="read_docs", nguon_tra_loi="agent"))
check("agent-mode read_docs bot is not forced into docs-only", "Đã tìm kỹ" not in p_agent and "javis_docs_read" in p_agent)
p_auto = chatbot_runtime.build_bot_prompt(dict(base, muc_quyen="read_docs", _tu_dong=True))
check("group auto-reply counts documents the bot opens itself", "bạn tự mở" in p_auto)


# ============================================================
# 5. The reply judge: a keyword miss is not a reason to stay silent at this level
# ============================================================
class Judge:
    def __init__(self):
        self.prompts = []

    async def __call__(self, prompt, purpose=""):
        self.prompts.append(prompt)
        return json.dumps({"verdict": "reply", "score": 0.9, "reason": "đúng chủ đề hoàn trả"})


NOW = 1_800_000_000.0
P = rp.BotProfile(bot_id="bot_docs", name="Javis Vũ", auto_aliases=["Javis Vũ"], mode="on", learning_enabled=True,
                  trainer_ids=[], role_text="Đảm nhiệm: hỗ trợ khách.", grounding="docs")
Q = "Cho em hỏi đổi trả hàng được mấy hôm vậy ạ?"


def ev(ts):
    e = rp.Event(channel="zalo_personal", bot_id="bot_docs", chat_id="g1", chat_type="group", msg_id=f"m{ts}",
                 ts=ts, text=Q, sender_id="u1", sender_name="Nam")
    e.sender_role = "new"
    return e


async def miss(text):
    return {"co": False, "khoi": ""}


async def miss_with_toc(text):
    return {"co": False, "khoi": "", "muc_luc": dt.table_of_contents(BRAIN)}


j = Judge()
d = run(rp.decide(ev(NOW), P, store=st, ask=j, doc_search=miss, now=NOW))
check("other levels: keyword miss still silences without a model call",
      d.silence_code == "no_grounding" and j.prompts == [], d)
j = Judge()
d = run(rp.decide(ev(NOW + 5), P, store=st, ask=j, doc_search=miss_with_toc, now=NOW + 5))
check("read_docs: keyword miss goes to the judge instead", d.silence_code != "no_grounding" and len(j.prompts) == 1, d)
check("read_docs: the judge sees the table of contents", j.prompts and "Mục lục tài liệu của bot" in j.prompts[0]
      and "Hoàn trả" in j.prompts[0])
check("read_docs: and can let the bot speak", d.verdict == "reply", d)

# The runtime wrapper adds the table of contents for read_docs bots only.
chatbot_runtime._deps["brain_root"] = lambda name: str(BRAIN)
t_docs = run(chatbot_runtime._tra_cho_phan_xu("b", {"brain": "shop", "muc_quyen": "read_docs"}, "xyzqwv abcdef"))
t_sugg = run(chatbot_runtime._tra_cho_phan_xu("b", {"brain": "shop", "muc_quyen": "suggest"}, "xyzqwv abcdef"))
check("runtime: read_docs bot hands the judge a table of contents", "faq/chinh-sach.md" in (t_docs.get("muc_luc") or ""))
check("runtime: other levels do not", "muc_luc" not in t_sugg)

# A read_docs bot whose pre-search missed is not "stuck": it looks the answer up afterwards. Counting it as stuck
# would fill the "Bot bí" tab and call the on-duty person for questions the bot answered fine.
_rt = (SERVER / "chatbot_runtime.py").read_text(encoding="utf-8")
_bi = _rt[_rt.index("bi = bool(loi_ky_thuat)"):][:400]
check("runtime: a pre-search miss does not count as stuck at read_docs", "chatbot_doc_tools.MODE" in _bi)


print()
if _fails:
    print(f"ĐỎ {len(_fails)} mục: " + "; ".join(_fails))
    sys.exit(1)
print("XANH: mức Đọc tài liệu chỉ đọc, đúng một brain, không lộ gì ngoài tài liệu.")
