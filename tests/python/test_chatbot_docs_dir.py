"""Per-bot documents folder (`docs_dir`): several bots share one brain, each reads only its own folder.

    python tests/run.py chatbot_docs_dir      (no network)

The owner runs two sales bots (one per branch) out of the brain he works in every day. Until now a bot's documents
were its whole brain, so both bots read both branches plus every internal report. `docs_dir` narrows that to one
folder, and the narrowing only means something if it holds everywhere the bot reads, so each path is pinned here:

1. **The setting is a relative folder inside the brain.** Absolute paths, drive letters, `..` and hidden parts are
   refused when saving; blank keeps the old behaviour (the whole brain).
2. **Fail closed.** A folder that is invalid, missing or a symlink out of the brain gives the bot NO documents, never
   the whole brain.
3. **Pre-turn search and the read_docs tools agree.** The keyword search and the three document tools open exactly
   the files inside the folder; the tools learn the folder from the host's turn, never from a tool argument.
4. **Store round trip.** Create and update keep the value, and an update can clear it.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import os
import sys
import tempfile
from pathlib import Path

_STATE = tempfile.mkdtemp(prefix="javis-docsdir-")
os.environ["JAVIS_STATE_DIR"] = _STATE
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import chatbot_doc_tools as dt  # noqa: E402
import chatbot_grounding  # noqa: E402
import chatbot_store  # noqa: E402
import turn_context  # noqa: E402

_fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(extra) + "]") if extra and not cond else ""))
    if not cond:
        _fails.append(name)


if _STATE not in str(chatbot_store.STORE_PATH):
    print(f"FAIL store is not in the temp dir: {chatbot_store.STORE_PATH}. STOP.")
    sys.exit(1)

BRAIN = Path(tempfile.mkdtemp(prefix="javis-docsdir-brain-")).resolve()
OUTSIDE = Path(tempfile.mkdtemp(prefix="javis-docsdir-outside-")).resolve()


def w(rel, text, root=BRAIN):
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


w("sale/A/tai-lieu/bang-gia.md", "# Bảng giá chi nhánh A\n\nGói cơ bản chi nhánh A giá ALPHA-111 đồng.\n")
w("sale/A/tai-lieu/sub/dia-chi.md", "# Địa chỉ chi nhánh A\n\nSố 1 phố ALPHA-ADDR.\n")
w("sale/B/tai-lieu/bang-gia.md", "# Bảng giá chi nhánh B\n\nGói cơ bản chi nhánh B giá BETA-222 đồng.\n")
w("bao-cao/doanh-thu.md", "# Báo cáo doanh thu nội bộ\n\nDoanh thu tháng NOIBO-333.\n")
w("ngoai.md", "# Ngoài brain\n\nBảng giá NGOAI-444.\n", root=OUTSIDE)
_CO_SYMLINK = True
try:
    os.symlink(OUTSIDE, BRAIN / "sale" / "lien-ket")
except (OSError, NotImplementedError):
    _CO_SYMLINK = False

# ============================================================
# 1. Validation of the setting
# ============================================================
for raw, want in (("", ""), ("  ", ""), ("sale/A/tai-lieu", "sale/A/tai-lieu"), ("./sale/A/", "sale/A"),
                  ("sale\\A\\tai-lieu", "sale/A/tai-lieu"), ("sale//A", "sale/A")):
    got, err = chatbot_store.clean_docs_dir(raw)
    check(f"accepts {raw!r} -> {want!r}", got == want and err == "", (got, err))
for raw in ("/etc", "\\\\server\\share", "C:/Users", "../ngoai", "sale/../../x", "sale/./A", ".claude",
            "sale/.hidden", "x" * 201):
    got, err = chatbot_store.clean_docs_dir(raw)
    check(f"refuses {raw[:30]!r}", got == "" and err != "", (got, err))

# ============================================================
# 2. docs_root: blank = whole brain, anything wrong = a folder that does not exist
# ============================================================
check("blank docs_dir is the whole brain", chatbot_store.docs_root(BRAIN, "") == BRAIN)
check("a folder resolves inside the brain", chatbot_store.docs_root(BRAIN, "sale/A") == BRAIN / "sale" / "A")
for bad in ("../" + OUTSIDE.name, "/etc", "C:/x"):
    r = chatbot_store.docs_root(BRAIN, bad)
    check(f"invalid {bad!r} fails closed", not r.exists() and BRAIN in r.parents, r)
if _CO_SYMLINK:
    r = chatbot_store.docs_root(BRAIN, "sale/lien-ket")
    check("a symlink out of the brain fails closed", not r.exists(), r)

# ============================================================
# 3. Pre-turn search sees only the folder
# ============================================================
A = chatbot_store.docs_root(BRAIN, "sale/A/tai-lieu")
docs_a = set(chatbot_grounding.ds_tai_lieu(A))
check("search lists the folder's documents, subfolders included",
      {"bang-gia.md", "sub/dia-chi.md"} <= docs_a, docs_a)
hits = chatbot_grounding.thu_thap(A, "bảng giá gói cơ bản")
blob = str(hits)
check("search finds the bot's own price", "ALPHA-111" in blob, blob[:200])
check("search never reaches the other branch", "BETA-222" not in blob)
check("search never reaches internal reports", "NOIBO-333" not in str(chatbot_grounding.thu_thap(A, "doanh thu")))
miss = chatbot_store.docs_root(BRAIN, "sale/C/khong-co")
check("a missing folder gives no documents", not chatbot_grounding.ds_tai_lieu(miss))

# ============================================================
# 4. The read_docs tools take the folder from the host's turn
# ============================================================
tools, route = dt.build(BRAIN)


def call(name, turn=None, **args):
    tok = turn_context.bind(turn) if turn is not None else None
    try:
        return asyncio.run(route[name]["call"](args))
    finally:
        if tok is not None:
            turn_context.reset(tok)


TA = {"kenh": "api", "chat_id": "c1", "docs_dir": "sale/A/tai-lieu"}
lst = call("javis_docs_list", TA)
check("list shows the folder's documents", "bang-gia.md" in lst and "dia-chi" in lst, lst)
check("list hides the other branch and reports", "sale/B" not in lst and "doanh-thu" not in lst, lst)
check("read opens a document in the folder", "ALPHA-111" in call("javis_docs_read", TA, path="bang-gia.md"))
for p in ("../B/tai-lieu/bang-gia.md", "sale/B/tai-lieu/bang-gia.md", "bao-cao/doanh-thu.md",
          "../../bao-cao/doanh-thu.md", str(BRAIN / "sale" / "B" / "tai-lieu" / "bang-gia.md")):
    out = call("javis_docs_read", TA, path=p)
    # A bare file name may still match the bot's OWN copy (the tools match names), but never the other folder's.
    check(f"read never opens {p[-40:]!r}", "BETA-222" not in out and "NOIBO-333" not in out, out[:120])
s = call("javis_docs_search", TA, query="bảng giá gói cơ bản chi nhánh")
check("tool search stays in the folder", "ALPHA-111" in s and "BETA-222" not in s, s[:200])

TB = {"kenh": "api", "chat_id": "c2", "docs_dir": "sale/B/tai-lieu"}
check("the other bot reads its own folder", "BETA-222" in call("javis_docs_read", TB, path="bang-gia.md"))

TX = {"kenh": "api", "chat_id": "c3", "docs_dir": "../" + OUTSIDE.name}
for name, args in (("javis_docs_list", {}), ("javis_docs_search", {"query": "bảng giá"}),
                   ("javis_docs_read", {"path": "ngoai.md"})):
    out = call(name, TX, **args)
    check(f"invalid folder: {name} opens nothing", not any(x in out for x in ("NGOAI-444", "ALPHA", "BETA", "NOIBO")),
          out[:120])

check("no docs_dir on the turn keeps the whole brain", "BETA-222" in call("javis_docs_read", {"kenh": "api"},
                                                                          path="sale/B/tai-lieu/bang-gia.md"))
check("the path argument cannot widen the folder",
      "NOIBO-333" not in call("javis_docs_read", TA, path="bao-cao/doanh-thu.md", docs_dir=""))

# ============================================================
# 5. Store round trip
# ============================================================
bid, why = chatbot_store.create_bot({"name": "Bot A", "agent_slug": "sale-a", "brain": str(BRAIN),
                                     "docs_dir": "./sale/A/tai-lieu/"})
check("create keeps a clean docs_dir", bid and chatbot_store.get_bot(bid).get("docs_dir") == "sale/A/tai-lieu",
      why or chatbot_store.get_bot(bid))
bad, why = chatbot_store.create_bot({"name": "Bot X", "agent_slug": "sale-x", "brain": str(BRAIN), "docs_dir": "../x"})
check("create refuses a folder outside the brain", bad is None and why, why)
ok, why = chatbot_store.update_bot(bid, {"docs_dir": "/etc"})
check("update refuses an absolute path and keeps the old value",
      not ok and chatbot_store.get_bot(bid).get("docs_dir") == "sale/A/tai-lieu", why)
ok, why = chatbot_store.update_bot(bid, {"docs_dir": "sale/B/tai-lieu"})
check("update changes the folder", ok and chatbot_store.get_bot(bid).get("docs_dir") == "sale/B/tai-lieu", why)
ok, why = chatbot_store.update_bot(bid, {"docs_dir": ""})
check("update can clear it back to the whole brain", ok and chatbot_store.get_bot(bid).get("docs_dir") == "", why)
ok, why = chatbot_store.update_bot(bid, {"name": "Bot A2"})
check("an update without docs_dir leaves it alone", ok and chatbot_store.get_bot(bid).get("docs_dir") == "", why)

if _fails:
    print(f"\n{len(_fails)} FAIL")
    sys.exit(1)
print("\nALL OK")
