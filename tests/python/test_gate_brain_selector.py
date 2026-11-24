"""Javis Gate picks its brain on purpose (#1726, owner 2026-11-24: "ô chọn brain cho Javis Gate anh đồng ý").

    python tests/run.py gate_brain_selector -v      (no network)

claude.ai cannot send headers, so every Gate call fell back to "the brain used last" and a user's personal notes landed
in a secondary brain. This file runs the Gate door of the hub for real (`mcp_hub.tra_loi_jsonrpc(gate=...)`) on three
temporary brains and locks:

1. `brain` on the Gate tools, matched by name (case and accents ignored, label or folder) or by path, and only among
   the registered brains: an unknown name or an outside path is refused with the valid names.
2. `javis_brains` lists the brains, the default and the brain used last.
3. Every brain-bound result names its brain; brain-free tools carry no brain argument.
4. Without `brain`: the owner's default brain for the Gate; none picked (or picked and deleted): the brain used last,
   exactly as before.
5. Notes (`javis_chat_note`) and transcripts follow the same rules; `javis_chat_send` refuses a chat of another brain.
6. The Gate's `initialize` instructions tell the client to ask which brain before writing.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import json
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="gate-brain-"))
_BRAINS = _TMP / "brains"
for name in ("Brain Default", "Cá Nhân", "Work", "Side"):
    (_BRAINS / name / "Javis").mkdir(parents=True, exist_ok=True)
_OUTSIDE = _TMP / "outside"
_OUTSIDE.mkdir()
os.environ["JAVIS_STATE_DIR"] = str(_TMP / "state")
os.environ["JAVIS_SESSIONS_DB"] = str(_TMP / "conversations.db")
os.environ["BRAINS_DIR"] = str(_BRAINS)
(_TMP / "state").mkdir(parents=True, exist_ok=True)

import brain_label  # noqa: E402
import chat_bridge as CB  # noqa: E402
import gate_brain  # noqa: E402
import mcp_hub  # noqa: E402
import sessions  # noqa: E402

fails = []


def check(name, cond, info=None):
    print(("ok   " if cond else "FAIL ") + name + ("" if cond or info is None else f"  ({info!r})"[:600]))
    if not cond:
        fails.append(name)


PERSONAL = str((_BRAINS / "Cá Nhân").resolve())
WORK = str((_BRAINS / "Work").resolve())
DEFAULT = str((_BRAINS / "Brain Default").resolve())
SIDE = str((_BRAINS / "Side").resolve())
brain_label.write(SIDE, "Công Việc Phụ")      # a renamed brain: label differs from its folder

# The brain used last: a chat in Work, touched after one in Brain Default.
store = sessions.get_store()
old = store.create_session(brain=DEFAULT)
store.append_message(old, "user", "older chat")
time.sleep(0.02)
recent = store.create_session(brain=WORK, title="Work chat")
store.append_message(recent, "user", "the chat the owner touched last")


class Req:
    def __init__(self, body):
        self._body = body

    async def json(self):
        return self._body


async def rpc(method, params=None, mode="full"):
    mcp_hub.invalidate_cache()
    mcp_hub.quen_brain_dang_mo()
    resp = await mcp_hub.tra_loi_jsonrpc(Req({"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}}),
                                         mode, gate={"source": "claude.ai"})
    return json.loads(resp.body.decode("utf-8"))


async def call(name, args, mode="full"):
    data = await rpc("tools/call", {"name": name, "arguments": args}, mode)
    res = data.get("result") or {}
    return (res.get("content") or [{}])[0].get("text", ""), bool(res.get("isError"))


def written(brain_path, rel):
    return (Path(brain_path) / rel).is_file()


async def main_flow():
    # ── tools/list: javis_brains, and `brain` only where a brain is touched ──
    data = await rpc("tools/list")
    tools = {t["name"]: t for t in (data.get("result") or {}).get("tools") or []}
    check("javis_brains is listed at the Gate", "javis_brains" in tools)
    props = lambda n: ((tools.get(n) or {}).get("inputSchema") or {}).get("properties") or {}  # noqa: E731
    check("javis_write_file shows the optional brain argument", "brain" in props("javis_write_file"))
    check("javis_read_file and javis_list_dir show it too",
          "brain" in props("javis_read_file") and "brain" in props("javis_list_dir"))
    check("brain stays optional", "brain" not in ((tools.get("javis_write_file") or {}).get("inputSchema") or {})
          .get("required", []))
    if "javis_run_tool" in tools:
        check("the lazy javis_run_tool shows brain (Javis tools hide behind it)", "brain" in props("javis_run_tool"))
        check("javis_search_tools does not (searching touches no brain)",
              "javis_search_tools" in tools and "brain" not in props("javis_search_tools"))
    conn_spec = {"fn": "pos__orders", "schema": {"type": "object", "properties": {"day": {"type": "string"}}}}
    check("a connection tool gets no brain argument (connections are shared by every brain)",
          mcp_hub._gate_brain_spec(conn_spec, {"conn": {"id": "c1"}, "call": None}) is conn_spec)
    check("javis_connections gets none either",
          "brain" not in mcp_hub._gate_brain_spec({"fn": "javis_connections", "schema": {"type": "object"}},
                                                  {"call": None})["schema"].get("properties", {}))
    check("the Gate's chat tools take brain where it matters",
          all("brain" in props(n) for n in ("javis_chat_note", "javis_chat_send", "javis_chat_find")))
    data = await rpc("tools/list")
    check("the cached spec is not changed for Javis's own engines",
          all("brain" not in ((t.get("schema") or {}).get("properties") or {})
              for t in (await mcp_hub.discover_all("full", vault_root=WORK))[0] if t["fn"] == "javis_write_file"))

    # ── 4. no default picked: the brain used last, exactly as before ──
    txt, err = await call("javis_write_file", {"path": "notes/a.md", "content": "A"})
    check("no default and no brain: writes into the brain used last", not err and written(WORK, "notes/a.md"), txt)
    check("the result names that brain and why", '"Work"' in txt and "used last" in txt, txt)
    check("the Vietnamese X-Javis-Vault header note is not shown at the Gate", "X-Javis-Vault" not in txt, txt)

    # ── 1. by name, case and accents ignored ──
    txt, err = await call("javis_write_file", {"path": "notes/b.md", "content": "B", "brain": "ca NHAN"})
    check("brain by name without accents writes into that brain", not err and written(PERSONAL, "notes/b.md"), txt)
    check("and not into the brain used last", not written(WORK, "notes/b.md"))
    check("the write result names the brain it wrote to", '"Cá Nhân"' in txt and "named in this call" in txt, txt)
    txt, err = await call("javis_write_file", {"path": "notes/c.md", "content": "C", "brain": "cong viec phu"})
    check("a renamed brain matches by its label", not err and written(SIDE, "notes/c.md"), txt)
    txt, err = await call("javis_write_file", {"path": "notes/d.md", "content": "D", "brain": "side"})
    check("and by its folder", not err and written(SIDE, "notes/d.md"), txt)

    # ── 1. by path ──
    txt, err = await call("javis_write_file", {"path": "notes/e.md", "content": "E", "brain": PERSONAL})
    check("brain by path writes into that brain", not err and written(PERSONAL, "notes/e.md"), txt)

    # ── 1. refused ──
    txt, err = await call("javis_write_file", {"path": "x.md", "content": "X", "brain": "Nope"})
    check("an unknown brain is refused", err and txt.startswith("ERROR:"), txt)
    check("the error lists the valid names",
          all(n in txt for n in ('"Brain Default"', '"Cá Nhân"', '"Work"', '"Công Việc Phụ"')), txt)
    check("nothing was written anywhere", not any(written(b, "x.md") for b in (WORK, PERSONAL, DEFAULT, SIDE)))
    txt, err = await call("javis_write_file", {"path": "x.md", "content": "X", "brain": str(_OUTSIDE)})
    check("an existing folder that is not a brain is refused", err and "not the path of a Javis brain" in txt, txt)
    check("and nothing is written there", not (_OUTSIDE / "x.md").exists())
    txt, err = await call("javis_write_file", {"path": "x.md", "content": "X", "brain": str(_BRAINS)})
    check("BRAINS_DIR itself is not a brain", err and not (_BRAINS / "x.md").exists(), txt)
    txt, err = await call("javis_write_file", {"path": "../Work/escape.md", "content": "X", "brain": "Cá Nhân"})
    check("path traversal is still refused inside the chosen brain",
          err and not written(WORK, "escape.md") and not (_BRAINS / "escape.md").exists(), txt)

    # ── reads follow the same brain ──
    txt, err = await call("javis_read_file", {"path": "notes/b.md", "brain": "Cá Nhân"})
    check("javis_read_file reads from the named brain", not err and txt.startswith("B"), txt)
    txt, err = await call("javis_list_dir", {"path": "notes", "brain": "Cá Nhân"})
    check("javis_list_dir lists the named brain", not err and "b.md" in txt and "a.md" not in txt, txt)

    # ── permission level unchanged: read-only Gate still cannot write, whatever brain ──
    txt, err = await call("javis_write_file", {"path": "ro.md", "content": "X", "brain": "Cá Nhân"}, mode="suggest")
    check("a read-only Gate door still cannot write", not written(PERSONAL, "ro.md"), txt)

    # ── 2. javis_brains ──
    txt, err = await call("javis_brains", {})
    lst = json.loads(txt) if not err else {}
    names = [b["name"] for b in lst.get("brains") or []]
    check("javis_brains lists every brain by name", sorted(names) == sorted(
        ["Brain Default", "Cá Nhân", "Work", "Công Việc Phụ"]), names)
    check("each brain comes with its path", all(b.get("path") for b in lst.get("brains") or []))
    check("the renamed brain also shows its folder",
          any(b.get("folder") == "Side" for b in lst.get("brains") or []))
    check("no default picked: says so, and marks the brain used last",
          lst.get("default") is None and any(b.get("last_used") and b["name"] == "Work" for b in lst["brains"]), lst)
    check("several brains: the hint says to ask before writing", "ask which brain" in (lst.get("hint") or ""))
    data = await rpc("tools/call", {"name": "javis_brains", "arguments": {}}, mode="suggest")
    check("javis_brains is read-only: it works at the read-only level",
          not (data.get("result") or {}).get("isError"))

    # ── 4. the owner's default brain for the Gate ──
    ok, _ = gate_brain.set_default("Cá Nhân")
    check("the default is saved", ok and gate_brain.configured_folder() == "Cá Nhân")
    txt, err = await call("javis_write_file", {"path": "notes/f.md", "content": "F"})
    check("no brain named: the owner's default brain, not the brain used last",
          not err and written(PERSONAL, "notes/f.md") and not written(WORK, "notes/f.md"), txt)
    check("the result says it is the Gate's default brain", "default brain for Javis Gate" in txt, txt)
    txt, err = await call("javis_write_file", {"path": "notes/g.md", "content": "G", "brain": "work"})
    check("a brain named in the call beats the default", not err and written(WORK, "notes/g.md"), txt)
    txt, err = await call("javis_brains", {})
    lst = json.loads(txt)
    check("javis_brains shows the default",
          lst.get("default") == "Cá Nhân" and any(b.get("default") and b["name"] == "Cá Nhân" for b in lst["brains"]))
    ok, msg = gate_brain.set_default("Missing")
    check("an unknown folder cannot be saved as the default", not ok and msg and
          gate_brain.configured_folder() == "Cá Nhân")

    # ── 5. notes ──
    CB._HOST["runtime"] = lambda: _RT
    CB._HOST["luu"] = _save
    txt, err = await call("javis_chat_note", {"title": "Plan", "asked": "remember this"})
    note = json.loads(txt) if not err else {}
    row = store.get_session(note.get("id") or "") or {}
    check("a note without brain opens in the Gate's default brain",
          gate_brain.same_brain(row.get("brain"), PERSONAL), (txt, row.get("brain")))
    check("the note result names its brain", note.get("brain") == "Cá Nhân", note)
    txt, err = await call("javis_chat_note", {"title": "Plan", "asked": "again", "brain": "Work"})
    note2 = json.loads(txt) if not err else {}
    row2 = store.get_session(note2.get("id") or "") or {}
    check("the same title noted into another brain opens a conversation in that brain",
          note2.get("id") != note.get("id") and gate_brain.same_brain(row2.get("brain"), WORK), (txt, row2))
    txt, err = await call("javis_chat_note", {"title": "Plan", "asked": "third"})
    check("and the default brain keeps its own conversation", not err and json.loads(txt).get("id") == note.get("id"),
          txt)
    txt, err = await call("javis_chat_note", {"asked": "x", "id": recent, "brain": "Cá Nhân"})
    check("a note into a chat of another brain is refused", err and "is in the brain" in txt, txt)
    txt, err = await call("javis_chat_note", {"title": "T", "asked": "x", "brain": "nope"})
    check("a note with an unknown brain is refused", err and "Valid brains" in txt, txt)

    # ── 5. send: the conversation fixes the brain ──
    CB._HOST["chay"] = _no_run
    txt, err = await call("javis_chat_send", {"id": recent, "message": "do it", "brain": "Cá Nhân", "wait_seconds": 0})
    check("javis_chat_send refuses a chat of another brain", err and '"Work"' in txt and '"Cá Nhân"' in txt, txt)
    check("and nothing ran", not _RAN)

    # ── find: each row names its brain, and the brain filter works ──
    txt, err = await call("javis_chat_find", {"query": "", "brain": "Work"})
    found = json.loads(txt).get("results") if not err else []
    check("javis_chat_find filters by brain",
          found and all(r.get("brain") == "Work" for r in found) and any(r["id"] == recent for r in found), found)
    txt, err = await call("javis_chat_find", {"query": ""})
    found = json.loads(txt).get("results") if not err else []
    check("every result names its brain", found and all(r.get("brain") for r in found), found)

    # ── 4. a default that was deleted: back to the brain used last ──
    gate_brain.set_default("Side")
    shutil.rmtree(SIDE)
    store.append_message(recent, "user", "touch Work again")
    txt, err = await call("javis_write_file", {"path": "notes/h.md", "content": "H"})
    check("a deleted default brain falls back to the brain used last", not err and written(WORK, "notes/h.md"), txt)
    gate_brain.set_default("")
    check("clearing the default goes back to 'Brain used last'", gate_brain.configured_folder() == "")

    # ── 6. instructions ──
    data = await rpc("initialize", {"protocolVersion": "2025-06-18"})
    ins = (data.get("result") or {}).get("instructions") or ""
    check("initialize tells the client about brains and javis_brains", "javis_brains" in ins and "brain" in ins)
    check("and to ask which brain before writing when there are several",
          "more than one brain" in ins and "ask the owner which brain" in ins, ins)


class _Runtime:
    async def publish(self, ev):
        return None

    def get_job(self, sid):
        return None


_RT = _Runtime()
_RAN = []


async def _save(sid, brain, msg, reply):
    store.append_message(sid, "user", msg)
    return store.append_message(sid, "assistant", reply) or 1


async def _no_run(ws):
    _RAN.append(ws)


asyncio.run(main_flow())

# ── the lazy javis_run_tool: an inner brain of a Javis tool is lifted, a connection tool's is left alone ──
args, wanted = mcp_hub._gate_take_brain("javis_run_tool", {"name": "javis_task", "args": {"op": "list", "brain": "Work"}},
                                        None, True)
check("javis_run_tool: the brain inside the args of a Javis tool picks the brain",
      wanted == "Work" and "brain" not in args["args"], (args, wanted))
args, wanted = mcp_hub._gate_take_brain("javis_run_tool", {"name": "pos__orders", "args": {"brain": "x"}}, None, True)
check("javis_run_tool: a connection tool's own args are left alone", wanted == "" and args["args"] == {"brain": "x"})
args, wanted = mcp_hub._gate_take_brain("javis_web_search", {"query": "q", "brain": "Work"}, None, False)
check("a brain-free tool drops the argument without picking a brain", wanted == "" and "brain" not in args)
spec = {"fn": "x", "schema": {"type": "object", "properties": {"brain": {"type": "string"}}}}
args, wanted = mcp_hub._gate_take_brain("x", {"brain": "own"}, spec, True)
check("a tool with its own brain parameter keeps it", args == {"brain": "own"} and wanted == "")

# ── transcripts (Javis Sync) open in the Gate's default brain too ──
src = Path(CB.__file__).read_text(encoding="utf-8")
check("transcripts open their conversation in the Gate's brain", "brain=_gate_brain(st)" in src)

print(("FAILED: " + str(len(fails))) if fails else "all ok")
sys.exit(1 if fails else 0)
