"""Read-only document tools for a dedicated bot at the "read_docs" level (0.80.0).

Why this level exists. At the "suggest" level a bot has no tools: Javis searches the bot's brain
by keyword BEFORE the turn and pastes the best chunks into the prompt. That keeps the bot honest,
but it misses whenever the customer's words differ from the document's ("đổi trả" vs "hoàn trả").
The "auto" level fixes that by handing the bot the hub's file tools, and with them write access and
every connected data source, all steered by a stranger. The owner asked (2026-10-05) for the
middle ground: "đọc được brain nhưng không ghi".

So this module is the WHOLE tool set of that level, and it is deliberately tiny:

1. **Three tools, all read-only.** List the documents, search them, open one. No write tool, no
   MCP source, no plugin, no skill, no lazy `javis_run_tool`. `mcp_hub.discover_all` returns this
   set and nothing else for the mode, so no engine (API or Claude Code via the hub) sees more.
2. **Same document set as the pre-turn search, minus a little.** A document is readable only if
   `chatbot_grounding.ds_tai_lieu` lists it: `inbox/` (customer uploads), `memory/`, skills,
   plugins, Javis' own convention files and the data cache are already excluded there, and this
   module also drops `agents/` and `workflows/` (the owner's internal instructions). The tools
   therefore never reveal anything the keyword search could not already put in a prompt.
3. **The path a customer types never touches the filesystem.** `docs_read` matches it against
   that list and opens the LISTED file, so `../`, absolute paths and symlinks lead nowhere.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import chatbot_grounding

MODE = "read_docs"

# Folders the pre-turn search reads but a stranger with an "open any document" tool should not:
# they hold the owner's instructions to agents, not knowledge for customers.
EXTRA_SKIP = {"agents", "workflows"}

READ_MAX = 20_000          # characters returned by one docs_read call
LIST_MAX = 8_000           # characters returned by docs_list
SEARCH_K = 6               # chunks returned by docs_search
SEARCH_CHUNK = 1_200       # characters per search chunk
INDEX_MAX = 1_500          # characters of the table of contents handed to the reply judge


def _root(vault_root: Any) -> Optional[Path]:
    if not vault_root:
        return None
    try:
        r = Path(str(vault_root)).expanduser().resolve()
    except Exception:
        return None
    return r if r.is_dir() else None


def allowed_docs(vault_root: Any) -> List[str]:
    """Relative posix paths of every document the tools may show, in a stable order."""
    r = _root(vault_root)
    if r is None:
        return []
    out = []
    for rel in chatbot_grounding.ds_tai_lieu(r):
        parts = rel.split("/")
        if any(p.lower() in EXTRA_SKIP for p in parts[:-1]):
            continue
        # A symlink that points out of the brain is not a document of this brain.
        try:
            (r / rel).resolve().relative_to(r)
        except (OSError, ValueError):
            continue
        out.append(rel)
    return out


def _norm(p: Any) -> str:
    s = str(p or "").strip().replace("\\", "/")
    while s.startswith("./"):
        s = s[2:]
    return s.lstrip("/")


def _match(vault_root: Any, requested: Any) -> Optional[str]:
    """The listed document the request names, or None. Exact first, then case-insensitive, then
    a unique file-name match (models often drop the folder)."""
    want = _norm(requested)
    if not want:
        return None
    docs = allowed_docs(vault_root)
    if want in docs:
        return want
    low = want.lower()
    for d in docs:
        if d.lower() == low:
            return d
    by_name = [d for d in docs if d.rsplit("/", 1)[-1].lower() == low.rsplit("/", 1)[-1]]
    return by_name[0] if len(by_name) == 1 else None


def _headings(vault_root: Any) -> Dict[str, List[str]]:
    """{path: [section titles]} from the cached keyword index (no extra disk scan)."""
    r = _root(vault_root)
    if r is None:
        return {}
    ok = set(allowed_docs(r))
    out: Dict[str, List[str]] = {}
    for m in chatbot_grounding.chi_muc(r).get("manh") or []:
        path = str(m.get("path") or "").replace("\\", "/")
        if path not in ok:
            continue
        ds = out.setdefault(path, [])
        ten = str(m.get("ten") or "").strip()
        if ten and ten not in ds and ten != Path(path).stem:
            ds.append(ten)
    for path in ok:
        out.setdefault(path, [])
    return out


def table_of_contents(vault_root: Any, max_chars: int = INDEX_MAX) -> str:
    """One line per document ("path: heading · heading"), cut at `max_chars`. Empty when the brain
    has no documents. Used by the reply judge: a bot that can open documents itself should not be
    silenced just because the customer's words missed the keyword search."""
    rows, used = [], 0
    for path, hs in sorted(_headings(vault_root).items()):
        line = path + (": " + " · ".join(hs[:8]) if hs else "")
        if used + len(line) + 1 > max_chars:
            rows.append("…")
            break
        rows.append(line)
        used += len(line) + 1
    return "\n".join(rows)


# ============================================================
# Tools
# ============================================================
def _tool(name: str, description: str, props: dict, required: list) -> dict:
    return {"fn": name, "server": "javis", "name": name, "description": description,
            "schema": {"type": "object", "properties": props, "required": required}}


def _route(call) -> dict:
    return {"call": call, "source_type": "builtin", "source_id": "javis-bot-docs", "effect": "read",
            "required_mode": "readonly", "health": "healthy"}


def build(vault_root: Any) -> Tuple[List[dict], Dict[str, dict]]:
    """(tools_spec, route) for one bot brain. No brain, no tools."""
    r = _root(vault_root)
    if r is None:
        return [], {}

    async def _list(args):
        hs = _headings(r)
        if not hs:
            return "(brain này chưa có tài liệu nào)"
        rows, used = [], 0
        for path, ds in sorted(hs.items()):
            line = "- " + path + (" | mục: " + " · ".join(ds[:12]) if ds else "")
            if used + len(line) > LIST_MAX:
                rows.append(f"… (còn {len(hs) - len(rows)} tài liệu, dùng javis_docs_search để tìm)")
                break
            rows.append(line)
            used += len(line) + 1
        return f"{len(hs)} tài liệu:\n" + "\n".join(rows)

    async def _search(args):
        q = str((args or {}).get("query") or "").strip()
        if not q:
            return "ERROR: thiếu query"
        ok = set(allowed_docs(r))
        hits = [h for h in chatbot_grounding.tim(r, q, k=SEARCH_K * 3)
                if str(h.get("path") or "").replace("\\", "/") in ok][:SEARCH_K]
        if not hits:
            return (f"Không có đoạn nào chứa các chữ của '{q}'. Thử lại bằng từ khác (từ đồng nghĩa, "
                    f"cách gọi khác, có dấu hoặc không dấu), hoặc xem javis_docs_list để chọn tài liệu.")
        parts = []
        for h in hits:
            t = str(h.get("text") or "")
            t = t[:SEARCH_CHUNK] + ("…" if len(t) > SEARCH_CHUNK else "")
            parts.append(f"### {h.get('ten')}\n(nguồn: {str(h.get('path')).replace(chr(92), '/')})\n\n{t}")
        return "\n\n".join(parts)

    async def _read(args):
        rel = _match(r, (args or {}).get("path"))
        if not rel:
            return (f"ERROR: không có tài liệu '{(args or {}).get('path')}' trong danh sách được đọc. "
                    f"Gọi javis_docs_list để xem đường dẫn đúng.")
        p = (r / rel).resolve()
        try:
            p.relative_to(r)
        except ValueError:
            return "ERROR: tài liệu này nằm ngoài brain nên không đọc được."
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            return f"ERROR: không đọc được '{rel}': {type(e).__name__}"
        text = re.sub(r"\A---\n.*?\n---\n", "", text, flags=re.DOTALL)
        if len(text) > READ_MAX:
            text = text[:READ_MAX] + f"\n… [cắt, tài liệu dài {len(text):,} ký tự]"
        return f"# {rel}\n\n{text}"

    tools = [
        _tool("javis_docs_search",
              "Tìm trong tài liệu của bạn các đoạn chứa chữ của câu hỏi. Khách hay dùng chữ khác tài liệu, "
              "nên tìm không ra thì thử lại bằng từ đồng nghĩa hoặc cách gọi khác trước khi kết luận là "
              "không có.",
              {"query": {"type": "string", "description": "Các từ cần tìm"}}, ["query"]),
        _tool("javis_docs_list",
              "Liệt kê mọi tài liệu của bạn kèm tên các mục trong từng tài liệu. Dùng khi tìm theo chữ "
              "không ra, để tự chọn tài liệu có vẻ đúng chủ đề rồi mở ra đọc.",
              {}, []),
        _tool("javis_docs_read",
              "Mở đọc trọn một tài liệu theo đường dẫn lấy từ javis_docs_list hoặc javis_docs_search.",
              {"path": {"type": "string", "description": "Đường dẫn tài liệu, vd 'faq/doi-tra.md'"}}, ["path"]),
    ]
    route = {"javis_docs_search": _route(_search), "javis_docs_list": _route(_list),
             "javis_docs_read": _route(_read)}
    return tools, route
